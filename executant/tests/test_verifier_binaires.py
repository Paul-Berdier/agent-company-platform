"""verifier-binaires (cahier P6 § 8.2, § 14.1) : refus d'une empreinte fausse, d'un manifeste non signé ou signé par
une autre clé, d'une archive sans le membre attendu ; contrôle rejouable des binaires installés.

Hors ligne : une clé GPG d'ESSAI est créée dans un trousseau jetable, de faux binaires et un faux manifeste sont
signés par elle, et ``--source`` remplace le réseau. Exige ``gpg`` (présent sur les lanceurs Linux de la CI et dans
l'étape « binaires » de l'image) ; sans lui, ignoré avec sa raison, sauf ``ACP_EXECUTANT_OBLIGATOIRE=1`` (CI) où
l'absence fait échouer.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "verifier-binaires"
OBLIGATOIRE = os.environ.get("ACP_EXECUTANT_OBLIGATOIRE") == "1"
BASE = "https://exemple.invalid/publications"


def _gpg_present() -> bool:
    if shutil.which("gpg") and os.name == "posix":
        return True
    if OBLIGATOIRE:
        pytest.fail("gpg absent alors que ACP_EXECUTANT_OBLIGATOIRE=1 : les refus de signature ne sont pas prouvés.")
    return False


pytestmark = pytest.mark.skipif(not (shutil.which("gpg") and os.name == "posix") and not OBLIGATOIRE,
                                reason="gpg sous Linux exigé (lanceur Linux de la CI, conteneur local)")


def _gpg(homedir: Path, *arguments: str, entree: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gpg", "--batch", "--no-tty", "--homedir", str(homedir), "--pinentry-mode", "loopback",
                           "--passphrase", "", *arguments], input=entree, capture_output=True, check=True)


class Cle:
    """Clé d'essai dans un trousseau jetable (chemin court : la socket de gpg-agent est limitée à 108 octets)."""

    def __init__(self, nom: str) -> None:
        self.homedir = Path(tempfile.mkdtemp(prefix="g", dir="/tmp"))
        os.chmod(self.homedir, 0o700)
        _gpg(self.homedir, "--quick-gen-key", f"{nom} <essai@acp.invalid>", "rsa2048", "sign", "never")
        sortie = _gpg(self.homedir, "--with-colons", "--fingerprint").stdout.decode()
        self.empreinte = next(l.split(":")[9] for l in sortie.splitlines() if l.startswith("fpr:"))
        self.publique = _gpg(self.homedir, "--armor", "--export").stdout

    def signer(self, fichier: Path, signature: Path) -> None:
        _gpg(self.homedir, "--yes", "--detach-sign", "-o", str(signature), str(fichier))

    def fermer(self) -> None:
        subprocess.run(["gpgconf", "--homedir", str(self.homedir), "--kill", "gpg-agent"], capture_output=True,
                       check=False)
        shutil.rmtree(self.homedir, ignore_errors=True)


@pytest.fixture(scope="module")
def cles():
    _gpg_present()
    bonne, autre = Cle("Essai ACP"), Cle("Autre clé")
    yield bonne, autre
    bonne.fermer()
    autre.fermer()


def _sha(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def _archive(membres: dict[str, bytes], lien: str | None = None) -> bytes:
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w:gz") as tar:
        for nom, contenu in membres.items():
            info = tarfile.TarInfo(nom)
            info.size = len(contenu)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(contenu))
        if lien:
            info = tarfile.TarInfo(lien)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
    return tampon.getvalue()


class Publication:
    """Dossier source (faux réseau), binaires.toml d'essai et clé publique, prêts à être altérés par un test."""

    def __init__(self, racine: Path, cle: Cle, *, signataire: Cle | None = None) -> None:
        self.racine = racine
        self.source = racine / "source"
        self.source.mkdir()
        self.codex = b"\x7fELF faux codex " + os.urandom(64)
        self.claude = b"\x7fELF faux claude " + os.urandom(64)
        self.archive = _archive({"codex-x86_64-unknown-linux-musl": self.codex})
        (self.source / "codex.tar.gz").write_bytes(self.archive)
        (self.source / "claude").write_bytes(self.claude)
        self.manifeste = {"version": "9.9.9", "platforms": {"linux-x64": {
            "binary": "claude", "checksum": _sha(self.claude), "size": len(self.claude)}}}
        self.ecrire_manifeste(signataire or cle)
        (racine / "cles").mkdir()
        (racine / "cles" / "essai.asc").write_bytes(cle.publique)
        self.empreinte = cle.empreinte
        self.ecrire_toml()

    def ecrire_manifeste(self, signataire: Cle, contenu: bytes | None = None) -> None:
        brut = contenu or json.dumps(self.manifeste, indent=2).encode()
        (self.source / "manifest.json").write_bytes(brut)
        signataire.signer(self.source / "manifest.json", self.source / "manifest.json.sig")

    def ecrire_toml(self, **surcharges: object) -> Path:
        manifeste = (self.source / "manifest.json").read_bytes()
        valeurs = {"codex_sha": _sha(self.archive), "codex_taille": len(self.archive),
                   "membre": "codex-x86_64-unknown-linux-musl", "claude_sha": _sha(self.claude),
                   "claude_taille": len(self.claude), "manifeste_sha": _sha(manifeste), "empreinte": self.empreinte}
        valeurs.update(surcharges)
        texte = f"""version = 1
[codex]
version = "0.0.1"
url = "{BASE}/codex.tar.gz"
sha256 = "{valeurs['codex_sha']}"
taille = {valeurs['codex_taille']}
membre = "{valeurs['membre']}"
installe = "codex/codex"
cosign = "identite_non_etablie"
[claude]
version = "9.9.9"
cle = "cles/essai.asc"
empreinte_cle = "{valeurs['empreinte']}"
manifeste = "{BASE}/manifest.json"
signature = "{BASE}/manifest.json.sig"
sha256_manifeste = "{valeurs['manifeste_sha']}"
plateforme = "linux-x64"
url = "{BASE}/claude"
sha256 = "{valeurs['claude_sha']}"
taille = {valeurs['claude_taille']}
installe = "claude/claude"
"""
        chemin = self.racine / "binaires.toml"
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def lancer(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *arguments, "--binaires",
                               str(self.racine / "binaires.toml")], capture_output=True, text=True, check=False)

    def telecharger(self) -> subprocess.CompletedProcess:
        return self.lancer("--telecharger", "--sortie", str(self.racine / "outils"), "--source", str(self.source))


def _refus(resultat: subprocess.CompletedProcess, fragment: str) -> None:
    assert resultat.returncode == 1, (resultat.stdout, resultat.stderr)
    assert "[acp] REFUS : " in resultat.stderr and fragment in resultat.stderr, resultat.stderr
    print(f"refus attendu : {resultat.stderr.strip()}")


def test_publication_conforme_installee_puis_controlee(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    resultat = pub.telecharger()
    assert resultat.returncode == 0, resultat.stderr
    outils = tmp_path / "outils"
    assert (outils / "codex" / "codex").read_bytes() == pub.codex
    assert (outils / "claude" / "claude").read_bytes() == pub.claude
    assert os.stat(outils / "claude" / "claude").st_mode & 0o777 == 0o755
    assert "signature cosign de Codex non vérifiée : identité du certificat non établie" in resultat.stdout
    provenance = json.loads((outils / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["claude"]["manifeste_signe_par"] == cles[0].empreinte
    assert pub.lancer("--controler", str(outils)).returncode == 0
    binaire = outils / "claude" / "claude"
    contenu = bytearray(binaire.read_bytes())
    contenu[-1] ^= 0x01
    binaire.write_bytes(bytes(contenu))
    _refus(pub.lancer("--controler", str(outils)), "empreinte fausse")


def test_verifier_binaires_refuse_empreinte_fausse(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    archive = bytearray(pub.archive)
    archive[len(archive) // 2] ^= 0x01
    (pub.source / "codex.tar.gz").write_bytes(bytes(archive))
    _refus(pub.telecharger(), "empreinte fausse")
    assert not (tmp_path / "outils").exists()


def test_verifier_binaires_refuse_binaire_claude_altere(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    (pub.source / "claude").write_bytes(pub.claude[:-1] + b"X")
    _refus(pub.telecharger(), "empreinte fausse")
    assert not (tmp_path / "outils").exists()


def test_manifeste_claude_signature_exigee(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    (pub.source / "manifest.json.sig").unlink()
    _refus(pub.telecharger(), "manifest.json.sig absent")


def test_manifeste_claude_altere_apres_signature(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    brut = (pub.source / "manifest.json").read_bytes().replace(b"9.9.9", b"9.9.8")
    (pub.source / "manifest.json").write_bytes(brut)
    pub.ecrire_toml(manifeste_sha=_sha(brut))
    _refus(pub.telecharger(), "Signature du manifeste de Claude Code absente ou invalide")


def test_manifeste_signe_par_une_autre_cle(tmp_path, cles):
    pub = Publication(tmp_path, cles[0], signataire=cles[1])
    _refus(pub.telecharger(), "Signature du manifeste de Claude Code absente ou invalide")


def test_cle_publique_d_une_autre_empreinte(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    pub.ecrire_toml(empreinte=cles[1].empreinte)
    _refus(pub.telecharger(), "Clé publique de Claude Code d'empreinte")


def test_manifeste_signe_mais_different_de_binaires_toml(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    pub.manifeste["platforms"]["linux-x64"]["checksum"] = "0" * 64
    pub.ecrire_manifeste(cles[0])
    pub.ecrire_toml()
    _refus(pub.telecharger(), "différent de binaires.toml")


def test_archive_codex_sans_le_membre_ou_avec_un_lien(tmp_path, cles):
    pub = Publication(tmp_path, cles[0])
    archive = _archive({"autre-binaire": b"x"}, lien="codex-x86_64-unknown-linux-musl")
    (pub.source / "codex.tar.gz").write_bytes(archive)
    pub.ecrire_toml(codex_sha=_sha(archive), codex_taille=len(archive))
    _refus(pub.telecharger(), "absent ou non ordinaire")


def test_binaires_toml_du_depot_complet_et_https():
    """Le vrai binaires.toml se lit, ne désigne que des adresses https et les versions du cahier (D86)."""
    import tomllib

    regles = tomllib.loads((SCRIPT.parents[1] / "binaires.toml").read_text(encoding="utf-8"))
    assert regles["codex"]["version"] == "0.156.1" and regles["claude"]["version"] == "2.1.283"
    assert regles["claude"]["empreinte_cle"] == "31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE"
    assert regles["codex"]["sha256"] == "aff46539a83aff86e3c62c592bce2c50d95391f9df289afaf03a50c01d14533d"
    assert regles["claude"]["sha256"] == "1859583ce32920595c61ef868bee52e1b1594f7486db209935e01f1e5e804ae2"
    assert (SCRIPT.parents[1] / regles["claude"]["cle"]).is_file()
