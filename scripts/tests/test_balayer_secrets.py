"""Balayage des secrets (scripts/balayer_secrets.py) : chaque motif est trouvé dans un dépôt git
jetable, dans l'arbre comme dans l'historique, l'extrait est masqué, et l'en-tête PEM cité par une
commande n'est pas pris pour une clé. Les faux secrets sont ASSEMBLÉS à l'exécution : ce fichier n'en
contient aucun littéral (le balayage du dépôt le lit aussi)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("balayer_secrets", RACINE / "scripts" / "balayer_secrets.py")
assert _SPEC is not None and _SPEC.loader is not None
bs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bs)

TIRETS = "-" * 5
FAUX = {
    "clé privée PEM": f"{TIRETS}BEGIN PRIVATE KEY{TIRETS}",
    "clé privée PEM en ligne": f'cle = "{TIRETS}BEGIN RSA PRIVATE KEY{TIRETS}\\n' + "MIIEow" + "A" * 40 + '"',
    "clé d'API Anthropic": "sk-" + "ant-" + "api03-" + "a1B2" * 8,
    "clé d'API OpenAI": "sk-" + "proj-" + "Z9y8" * 8,
    "clé d'API Google": "AI" + "za" + "S" * 35,
    "jeton GitHub": "gh" + "p_" + "q" * 36,
    "clé d'accès AWS": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "jeton Slack": "xo" + "xb-" + "1234567890-abcdef",
    "empreinte argon2id": "$argon2id$v=19$m=65536,t=3,p=4$" + "c2VsZHVzZWxkdXNlbA" + "$" + "aGFjaGVoYWNoZWhhY2hl",
    "jeton JWT": "ey" + "JhbGciOiJIUzI1NiJ9." + "ey" + "JzdWIiOiJhY3AifQ." + "c2lnbmF0dXJlc2ln",
}


def _git(depot: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(depot), *arguments], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": __import__("os").environ["PATH"],
                        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "propre.txt").write_text("Aucun secret ici.\n", encoding="utf-8")
    _git(tmp_path, "add", "propre.txt")
    _git(tmp_path, "commit", "-q", "-m", "depart")
    return tmp_path


def test_tous_les_motifs_ont_un_temoin():
    assert set(FAUX) == set(bs.MOTIFS)


@pytest.mark.parametrize("nom", sorted(FAUX))
def test_chaque_motif_est_trouve_dans_l_arbre_et_masque(depot, nom):
    (depot / "fuite.txt").write_text(f"avant\n{FAUX[nom]}\n", encoding="utf-8")
    _git(depot, "add", "fuite.txt")
    constats = bs.balayer_arbre(depot)
    assert [(c[0], c[1]) for c in constats] == [("fuite.txt:2", nom)]
    # Jamais le secret entier dans la sortie : quatre caractères, puis la longueur.
    assert FAUX[nom] not in constats[0][2] and "caractères" in constats[0][2]


def test_un_secret_retire_reste_trouve_dans_l_historique(depot):
    (depot / "fuite.txt").write_text(FAUX["jeton GitHub"] + "\n", encoding="utf-8")
    _git(depot, "add", "fuite.txt")
    _git(depot, "commit", "-q", "-m", "fuite")
    _git(depot, "rm", "-q", "fuite.txt")
    _git(depot, "commit", "-q", "-m", "retrait")
    assert bs.balayer_arbre(depot) == []
    constats = bs.balayer_plage("HEAD~2..HEAD", depot)
    assert len(constats) == 1 and constats[0][1] == "jeton GitHub" and constats[0][0].endswith(" fuite.txt")


def test_l_en_tete_pem_cite_par_une_commande_n_est_pas_une_cle(depot):
    (depot / "entree.sh").write_text(f"grep -q -- '{FAUX['clé privée PEM']}' \"$CLE\" || refuser\n",
                                     encoding="utf-8")
    _git(depot, "add", "entree.sh")
    assert bs.balayer_arbre(depot) == []


def test_un_fichier_binaire_est_ignore(depot):
    (depot / "image.png").write_bytes(b"\x89PNG\0" + FAUX["clé d'accès AWS"].encode())
    _git(depot, "add", "image.png")
    assert bs.balayer_arbre(depot) == []


def test_le_depot_ne_contient_aucun_motif():
    """Le dépôt lui-même, arbre suivi : la preuve publiée dans docs/reprise-poste.md."""
    assert bs.balayer_arbre(RACINE) == []


def test_main_code_et_message(capsys, monkeypatch, depot):
    monkeypatch.setattr(bs, "RACINE", depot)
    assert bs.main([]) == 0
    assert "Aucun motif de secret (fichiers suivis" in capsys.readouterr().out
    (depot / "fuite.txt").write_text(FAUX["jeton Slack"] + "\n", encoding="utf-8")
    _git(depot, "add", "fuite.txt")
    assert bs.main(["--arbre", "--plage", "HEAD~0..HEAD"]) == 1
    erreur = capsys.readouterr().err
    assert "Secrets possibles : 1 constat(s)" in erreur and "fuite.txt:1 : jeton Slack" in erreur
    assert FAUX["jeton Slack"] not in erreur
    assert bs.main(["--plage", "pas-une-revision"]) == 1
    assert "Balayage impossible" in capsys.readouterr().err


def test_la_ci_execute_le_balayage():
    ci = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python3 scripts/balayer_secrets.py --arbre --plage "$plage"' in ci
    assert 'plage="origin/main..HEAD"' in ci
