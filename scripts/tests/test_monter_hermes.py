"""Outil de montée de version de Hermes (scripts/monter_hermes.py, cahier P9 § 5.2).

Aucun Docker ni réseau ici : l'exécuteur de commandes et la lecture d'URL sont INJECTÉS (``FauxAmont`` joue le
registre, le dépôt amont et l'image). Le dépôt est une copie des épingles fortes dans un dossier jetable. Prouvé :
la répétition à blanc (« Aucun écart »), chaque champ altéré nommé, l'écriture d'une autre release conforme aux
gabarits de référence ET à la concordance statique (scripts/tests/test_epingles_hermes.py, implémentation
indépendante), l'idempotence, les refus, LF et fin de fichier, l'inventaire et la veille ``derniere``.
Le relevé réel (« Aucun écart » sur la release épinglée) est fait par image.yml à chaque construction."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pytest

RACINE = Path(__file__).resolve().parents[2]


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module  # dataclasses : le module doit être enregistré avant son exécution
    spec.loader.exec_module(module)
    return module


mh = _charger("monter_hermes", RACINE / "scripts" / "monter_hermes.py")
concordance = _charger("test_epingles_hermes_pour_mh", RACINE / "scripts" / "tests" / "test_epingles_hermes.py")


# =========================================================================== banc


class FauxAmont:
    """Exécuteur injecté : registre, dépôt amont, image et git local, pour UNE release décrite en Python."""

    def __init__(self, valeurs, openrpc: bytes, licence: bytes, livrees: List[str], optionnelles: List[str],
                 racine: Path):
        self.valeurs = valeurs
        self.openrpc: Optional[bytes] = openrpc
        self.licence: Optional[bytes] = licence
        self.livrees, self.optionnelles = livrees, optionnelles
        self.racine = racine
        self.modifies: List[str] = []
        self.version_affichee: Optional[str] = None
        self.provenance: Optional[Dict] = None  # None : celle de la release ; {} : absente
        self.inspect_code = 0
        self.grep = ""
        self.grep_code: Optional[int] = None
        self.tags_git: List[str] = []
        self.variante_arm64: Dict[str, str] = {}
        self.avec_arm64 = True
        self.appels: List[List[str]] = []

    def __call__(self, arguments: Sequence[str], delai: int) -> "mh.Resultat":
        a = list(arguments)
        self.appels.append(a)
        v = self.valeurs
        if a[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            if a[4] != f"{v.image}:{v.etiquette}" or self.inspect_code:
                return mh.Resultat(1, b"", b"ERROR: not found")
            arm64 = {"digest": v.arm64, "platform": {"architecture": "arm64", "os": "linux", **self.variante_arm64}}
            manifeste = {"digest": v.index, "manifests": [
                {"digest": v.amd64, "platform": {"architecture": "amd64", "os": "linux"}},
                {"digest": "sha256:" + "e" * 64, "platform": {"architecture": "unknown", "os": "unknown"}},
                *([arm64] if self.avec_arm64 else [])]}
            return mh.Resultat(0, json.dumps(manifeste).encode())
        if a[:2] == ["git", "ls-remote"] and "--tags" in a:
            lignes = "".join(f"{'0' * 40}\trefs/tags/{t}\n{'1' * 40}\trefs/tags/{t}^{{}}\n" for t in self.tags_git)
            return mh.Resultat(0, lignes.encode())
        if a[:2] == ["git", "ls-remote"]:
            if a[3] != f"refs/tags/{v.etiquette}":
                return mh.Resultat(0, b"")
            return mh.Resultat(0, f"{'a' * 40}\trefs/tags/{v.etiquette}\n{v.commit}\trefs/tags/{v.etiquette}^{{}}\n"
                               .encode())
        if a[:2] == ["docker", "pull"]:
            return mh.Resultat(0 if a[-1] == f"{v.image}@{v.index}" else 1)
        if a[:2] == ["docker", "run"]:
            assert a[2:5] == ["--rm", "--network", "none"], a
            entree, reference, reste = a[a.index("--entrypoint") + 1], a[a.index("--entrypoint") + 2], \
                a[a.index("--entrypoint") + 3:]
            assert reference == f"{v.image}@{v.index}", "l'image est toujours lancée PAR CONDENSAT"
            if entree == mh.HERMES_IMAGE_BIN and reste == ["--version"]:
                ligne = self.version_affichee or (f"Hermes Agent v{v.version} ({v.date_de_release}) · upstream "
                                                  f"{v.commit[:8]}")
                return mh.Resultat(0, f"{ligne}\nInstall directory: /opt/hermes\n".encode())
            if entree == "cat":
                contenu = {mh.CHEMIN_OPENRPC_IMAGE: self.openrpc, mh.CHEMIN_LICENCE_IMAGE: self.licence,
                           mh.CHEMIN_PROVENANCE_IMAGE: None if self.provenance == {} else json.dumps(
                               self.provenance or {"version": v.version, "revision": v.commit}).encode()}.get(reste[0])
                return mh.Resultat(0, contenu) if contenu is not None else mh.Resultat(1, b"", b"No such file")
            if entree == "sh":
                return mh.Resultat(0, json.dumps({"livrees": self.livrees,
                                                  "optionnelles": self.optionnelles}).encode())
        if a[:2] == ["git", "-C"] and a[3] == "status":
            return mh.Resultat(0, "".join(f" M {f}\n" for f in self.modifies).encode())
        if a[:2] == ["git", "-C"] and a[3] == "grep":
            if self.grep_code is not None:
                return mh.Resultat(self.grep_code, b"", b"fatal: erreur simulee")
            return mh.Resultat(0 if self.grep else 1, self.grep.encode())
        raise AssertionError(f"commande inattendue : {a}")


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    for relatif in (*mh.EPINGLES_FORTES, mh.GREFFON):
        (tmp_path / relatif).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RACINE / relatif, tmp_path / relatif)
    return tmp_path


def _verrou(racine: Path) -> Dict:
    return json.loads((racine / mh.VERROU).read_text(encoding="utf-8"))


@pytest.fixture
def amont(depot: Path) -> FauxAmont:
    """La release épinglée, telle que l'amont la publie (répétition à blanc)."""
    livrees = _verrou(depot)["livrees"]
    return FauxAmont(mh.lire_epingle(depot).valeurs, (depot / mh.OPENRPC).read_bytes(),
                     (depot / mh.LICENCE).read_bytes(), list(livrees["noms"]), list(livrees["optionnelles"]), depot)


def _instantane(racine: Path) -> Dict[str, bytes]:
    return {r: (racine / r).read_bytes() for r in (*mh.EPINGLES_FORTES, mh.GREFFON)}


def _lancer(fonction, *arguments, **options):
    lignes: List[str] = []
    code = fonction(*arguments, sortie=lignes.append, **options)
    return code, "\n".join(lignes)


# =========================================================================== verifier


def test_le_rendu_hors_ligne_reproduit_le_depot_reel_a_l_octet_pres():
    ep = mh.lire_epingle(RACINE)
    rendu = mh.rendre(RACINE, ep.valeurs, ep.date, (RACINE / mh.OPENRPC).read_bytes(),
                      (RACINE / mh.LICENCE).read_bytes())
    assert sorted(rendu) == sorted(mh.EPINGLES_FORTES)
    assert {r: c == (RACINE / r).read_bytes() for r, c in rendu.items()} == {r: True for r in rendu}


def test_verifier_sans_ecart_sur_la_release_epinglee(depot, amont):
    avant = _instantane(depot)
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 0, journal
    assert "Aucun écart" in journal
    assert _instantane(depot) == avant, "verifier n'écrit rien"
    assert not any("update" in a or "push" in a for appel in amont.appels for a in appel)


@pytest.mark.parametrize("champ, nom", [
    ("index", "HERMES_IMAGE_INDEX"), ("amd64", "HERMES_IMAGE_LINUX_AMD64"), ("arm64", "HERMES_IMAGE_LINUX_ARM64"),
    ("commit", "HERMES_COMMIT"), ("version", "HERMES_VERSION")])
def test_verifier_nomme_chaque_valeur_relevee_qui_differe(depot, amont, champ, nom):
    v = amont.valeurs
    nouvelle = {"index": "sha256:" + "1" * 64, "amd64": "sha256:" + "2" * 64, "arm64": "sha256:" + "3" * 64,
                "commit": "4" * 40, "version": "9.9.9"}[champ]
    amont.valeurs = replace(v, **{champ: nouvelle})
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 1, journal
    assert f"- {nom} : épinglé {getattr(v, champ)}, relevé {nouvelle}" in journal


def test_verifier_nomme_une_copie_de_l_openrpc_ou_une_licence_qui_differe(depot, amont):
    amont.openrpc = amont.openrpc.replace(b'"methods"', b'"x-acp": 1, "methods"', 1)
    amont.licence = amont.licence + b"Ajout.\n"
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 1
    assert "- OPENRPC_SHA256 : épinglé" in journal
    assert f"- {mh.OPENRPC} : diffère du rendu depuis le relevé" in journal
    assert f"- {mh.LICENCE} : diffère du rendu depuis le relevé" in journal


@pytest.mark.parametrize("relatif, avant, apres", [
    (mh.VERROU, '"instantane_hermes": "{version}"', '"instantane_hermes": "0.0.1"'),
    (mh.VERROU, '"commit": "{commit}"', '"commit": "' + "5" * 40 + '"'),
    (mh.FIXTURE_DESKTOP, '"methodes": {methodes}', '"methodes": 1'),
    (mh.FIXTURE_INTERFACE, 'commit: "{commit7}"', 'commit: "0000000"'),
    (mh.README_CONTRAT, "SHA-256 `{sha}`", "SHA-256 `" + "6" * 64 + "`"),
    (mh.TIERS, "(étiquette `{etiquette}`)", "(étiquette `v2000.1.1`)"),
    (mh.DOCKERFILE, "(Hermes Agent {version},", "(Hermes Agent 0.0.1,"),
    (mh.EPINGLE, "# Condensats relevés le ", "# Condensats relevés le 1er "),
])
def test_verifier_nomme_chaque_epingle_forte_qui_diverge(depot, amont, relatif, avant, apres):
    v = amont.valeurs
    valeurs = {"version": v.version, "commit": v.commit, "commit7": v.commit[:7], "methodes": v.openrpc_methodes,
               "sha": v.openrpc_sha256, "etiquette": v.etiquette}
    chemin = depot / relatif
    texte = chemin.read_bytes().decode("utf-8")
    cible = avant.format(**valeurs)
    assert texte.count(cible) == 1, cible
    chemin.write_bytes(texte.replace(cible, apres.format(**valeurs)).encode("utf-8"))
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 1, journal
    if relatif == mh.EPINGLE:
        # La date du relevé est lue dans HERMES_VERSION : changée seule, ce sont l'en-tête du Dockerfile et la
        # provenance du contrat, restés à l'ancienne date, qui divergent.
        assert f"- {mh.DOCKERFILE} : diffère du rendu depuis le relevé" in journal
        assert f"- {mh.README_CONTRAT} : diffère du rendu depuis le relevé" in journal
        return
    assert f"- {relatif} : diffère du rendu depuis le relevé" in journal
    # Extrait du diff : la ligne du dépôt (-) et celle du rendu (+).
    assert "\n    -" in journal and "\n    +" in journal


def test_verifier_signale_des_skills_livrees_nouvelles_ou_retirees(depot, amont):
    amont.livrees = [*amont.livrees[1:], "zz-nouvelle"]
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 1
    assert f"ajoutées ['zz-nouvelle'], retirées ['{_verrou(depot)['livrees']['noms'][0]}']" in journal


def test_verifier_signale_une_borne_requires_hermes_qui_exclut_la_release(depot, amont):
    chemin = depot / mh.GREFFON
    texte, n = re.subn(r"^requires_hermes: .*$", 'requires_hermes: ">=99.0.0"', chemin.read_text(encoding="utf-8"),
                       flags=re.M)
    assert n == 1
    chemin.write_text(texte, encoding="utf-8", newline="\n")
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 1 and f"requires_hermes >=99.0.0 exclut Hermes {amont.valeurs.version}" in journal


# =========================================================================== ecrire


def _release_suivante(amont: FauxAmont) -> FauxAmont:
    """Une release fictive postérieure : autre version, commit, condensats ; OpenRPC avec une méthode retirée, une
    ajoutée et info.version 2 ; une skill livrée de plus."""
    contrat = json.loads(amont.openrpc)
    retiree = contrat["methods"].pop(0)["name"]
    contrat["methods"].append({"name": "acp.essai.ajoutee", "params": [], "result": {"name": "r", "schema": {}}})
    contrat["info"]["version"] = "2"
    openrpc = (json.dumps(contrat, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    v = replace(amont.valeurs, version="0.22.0", etiquette="v2026.10.15", commit="b" * 40,
                index="sha256:" + "c" * 64, amd64="sha256:" + "d" * 64, arm64="sha256:" + "f" * 64,
                openrpc_sha256=hashlib.sha256(openrpc).hexdigest(), openrpc_info_version="2",
                openrpc_methodes=len(contrat["methods"]))
    suivante = FauxAmont(v, openrpc, amont.licence, sorted([*amont.livrees, "zz-nouvelle"]), amont.optionnelles,
                         amont.racine)
    suivante.retiree = retiree  # type: ignore[attr-defined]
    return suivante


def _gabarits(depot: Path, ancien, nouveau, date: str, openrpc: bytes) -> Dict[str, bytes]:
    """Gabarits de référence écrits SANS les motifs de l'outil : remplacements exacts des anciennes valeurs."""
    a, n = ancien.valeurs, nouveau

    def remplacer(relatif: str, paires) -> bytes:
        texte = (depot / relatif).read_bytes().decode("utf-8")
        for avant, apres in paires:
            assert avant in texte, (relatif, avant)
            texte = texte.replace(avant, apres)
        return texte.encode("utf-8")

    return {
        mh.EPINGLE: remplacer(mh.EPINGLE, [
            (f"HERMES_VERSION={a.version}\n", f"HERMES_VERSION={n.version}\n"),
            (f"HERMES_TAG={a.etiquette}\n", f"HERMES_TAG={n.etiquette}\n"),
            (f"HERMES_COMMIT={a.commit}\n", f"HERMES_COMMIT={n.commit}\n"),
            (f"HERMES_IMAGE_INDEX={a.index}\n", f"HERMES_IMAGE_INDEX={n.index}\n"),
            (f"HERMES_IMAGE_LINUX_AMD64={a.amd64}\n", f"HERMES_IMAGE_LINUX_AMD64={n.amd64}\n"),
            (f"HERMES_IMAGE_LINUX_ARM64={a.arm64}\n", f"HERMES_IMAGE_LINUX_ARM64={n.arm64}\n"),
            (f"OPENRPC_INFO_VERSION={a.openrpc_info_version}\n", f"OPENRPC_INFO_VERSION={n.openrpc_info_version}\n"),
            (f"OPENRPC_METHODES={a.openrpc_methodes}\n", f"OPENRPC_METHODES={n.openrpc_methodes}\n"),
            (f"OPENRPC_SHA256={a.openrpc_sha256}\n", f"OPENRPC_SHA256={n.openrpc_sha256}\n"),
            (f"relevés le {ancien.date} par", f"relevés le {date} par"),
            (f"inspect {a.image}:{a.etiquette}\n", f"inspect {n.image}:{n.etiquette}\n")]),
        mh.DOCKERFILE: remplacer(mh.DOCKERFILE, [
            (f"FROM {a.image}:{a.etiquette}@{a.index}\n", f"FROM {n.image}:{n.etiquette}@{n.index}\n"),
            (f"de l'étiquette {a.etiquette}\n", f"de l'étiquette {n.etiquette}\n"),
            (f"(Hermes Agent {a.version}, commit {a.commit[:7]}), relevé le {ancien.date} par",
             f"(Hermes Agent {n.version}, commit {n.commit[:7]}), relevé le {date} par"),
            (f"inspect {a.image}:{a.etiquette}\n", f"inspect {n.image}:{n.etiquette}\n")]),
        mh.OPENRPC: openrpc,
        mh.LICENCE: (depot / mh.LICENCE).read_bytes(),
        mh.README_CONTRAT: remplacer(mh.README_CONTRAT, [
            (f"étiquette `{a.etiquette}`", f"étiquette `{n.etiquette}`"), (f"`{a.commit}`", f"`{n.commit}`"),
            (ancien.date, date), (f"SHA-256 `{a.openrpc_sha256}`", f"SHA-256 `{n.openrpc_sha256}`"),
            (f"`info.version` = `{a.openrpc_info_version}`, {a.openrpc_methodes} méthodes",
             f"`info.version` = `{n.openrpc_info_version}`, {n.openrpc_methodes} méthodes")]),
        mh.TIERS: remplacer(mh.TIERS, [(f"`{a.commit}` (étiquette `{a.etiquette}`)",
                                        f"`{n.commit}` (étiquette `{n.etiquette}`)")]),
        mh.VERROU: remplacer(mh.VERROU, [
            (f'"version": "{a.version}"', f'"version": "{n.version}"'),
            (f'"etiquette": "{a.etiquette}"', f'"etiquette": "{n.etiquette}"'),
            (f'"commit": "{a.commit}"', f'"commit": "{n.commit}"'),
            (f'"condensat_index": "{a.index}"', f'"condensat_index": "{n.index}"'),
            (f'"instantane_hermes": "{a.version}"', f'"instantane_hermes": "{n.version}"')]),
        mh.FIXTURE_DESKTOP: remplacer(mh.FIXTURE_DESKTOP, [
            (f'"{a.version}"', f'"{n.version}"'), (f'"{a.etiquette}"', f'"{n.etiquette}"'),
            (f'"{a.commit}"', f'"{n.commit}"'), (f'"{a.index}"', f'"{n.index}"'),
            (f'"{a.openrpc_sha256}"', f'"{n.openrpc_sha256}"'),
            (f'"methodes": {a.openrpc_methodes}', f'"methodes": {n.openrpc_methodes}'),
            (f'"info_version": "{a.openrpc_info_version}"', f'"info_version": "{n.openrpc_info_version}"'),
            (f'"info_version_epinglee": "{a.openrpc_info_version}"',
             f'"info_version_epinglee": "{n.openrpc_info_version}"')]),
        mh.FIXTURE_INTERFACE: remplacer(mh.FIXTURE_INTERFACE, [
            (f'"{a.version}"', f'"{n.version}"'), (f'"{a.etiquette}"', f'"{n.etiquette}"'),
            (f'"{a.commit[:7]}"', f'"{n.commit[:7]}"'), (f'"{a.image}:{a.etiquette}"', f'"{n.image}:{n.etiquette}"'),
            (f'"{a.index}"', f'"{n.index}"')]),
    }


def test_ecrire_la_meme_release_ne_change_rien(depot, amont):
    avant = _instantane(depot)
    code, journal = _lancer(mh.ecrire, depot, amont, amont.valeurs.etiquette)
    assert code == 0, journal
    assert "aucun changement" in journal
    assert _instantane(depot) == avant
    assert "ajoutées : aucune ; retirées : aucune" in journal


def test_ecrire_une_autre_release_suit_les_gabarits_et_la_concordance(depot, amont):
    ancien = mh.lire_epingle(depot)
    suivante = _release_suivante(amont)
    attendus = _gabarits(depot, ancien, suivante.valeurs, "15 octobre 2026", suivante.openrpc)
    greffon_avant = (depot / mh.GREFFON).read_bytes()
    suivante.grep = (f"{mh.FIXTURE_INTERFACE}:7:  hermes: {{ version: \"{ancien.valeurs.version}\" }}\n"
                     f"apps/desktop/src/x.h:3:// Hermes {ancien.valeurs.version} (routes.py:12)\n"
                     f"docs/refonte/plan.md:9:Hermes {ancien.valeurs.version}\n")
    code, journal = _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    assert code == 0, journal
    for relatif, contenu in attendus.items():
        assert (depot / relatif).read_bytes() == contenu, relatif
    assert (depot / mh.GREFFON).read_bytes() == greffon_avant, "requires_hermes n'est jamais réécrit"
    # Implémentation indépendante : la concordance statique du dépôt accepte l'ensemble écrit.
    assert concordance.ecarts(depot) == []
    # Rapport.
    assert f"retirées : {suivante.retiree}" in journal  # type: ignore[attr-defined]
    assert "ajoutées : acp.essai.ajoutee" in journal
    assert "info.version de l'OpenRPC passe de 1 à 2" in journal
    assert "Skills livrées face à livrees.noms du verrou : ajoutées zz-nouvelle" in journal
    assert "Inventaire des anciennes valeurs" in journal and "apps/desktop/src/x.h:3" in journal
    # Idempotence : un second passage (fichiers committés) ne change rien.
    apres = _instantane(depot)
    code, journal = _lancer(mh.ecrire, depot, suivante, "v2026.10.15")
    assert code == 0 and "aucun changement" in journal
    assert _instantane(depot) == apres


def test_ecrire_prend_la_date_du_jour_quand_une_valeur_change(depot, amont, monkeypatch):
    suivante = _release_suivante(amont)
    monkeypatch.setattr(mh, "date_du_jour", lambda aujourd_hui=None: "3 novembre 2026")
    assert _lancer(mh.ecrire, depot, suivante, "v2026.10.15")[0] == 0
    assert "# Condensats relevés le 3 novembre 2026 par\n" in (depot / mh.EPINGLE).read_text(encoding="utf-8")


def test_ecrire_n_ecrit_que_du_lf_et_une_seule_fin_de_ligne(depot, amont):
    for relatif in (mh.README_CONTRAT, mh.VERROU):
        chemin = depot / relatif
        chemin.write_bytes(chemin.read_bytes().replace(b"\n", b"\r\n"))
    suivante = _release_suivante(amont)
    assert _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")[0] == 0
    for relatif in mh.EPINGLES_FORTES:
        contenu = (depot / relatif).read_bytes()
        assert b"\r\n" not in contenu, relatif
        assert contenu.endswith(b"\n") and not contenu.endswith(b"\n\n"), relatif


def test_ecrire_une_release_sous_la_borne_requires_hermes_le_dit_sans_toucher_la_borne(depot, amont):
    v = amont.valeurs
    amont.valeurs = replace(v, version="0.21.4", etiquette="v2026.9.21",
                            commit="d337b736aa1e8ebecfab043842d13e4a2d2f48a3", index="sha256:" + "7" * 64)
    greffon_avant = (depot / mh.GREFFON).read_bytes()
    code, journal = _lancer(mh.ecrire, depot, amont, "v2026.9.21", date="2 octobre 2026")
    assert code == 0
    borne = mh.borne_requires_hermes(depot)
    assert f"requires_hermes \">={borne}\", qui exclut Hermes 0.21.4" in journal
    assert (depot / mh.GREFFON).read_bytes() == greffon_avant


def test_ecrire_refuse_des_changements_non_committes(depot, amont):
    suivante = _release_suivante(amont)
    suivante.modifies = [mh.VERROU]
    avant = _instantane(depot)
    with pytest.raises(mh.Refus, match="Changements non committés .*catalogue.lock.json"):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15")
    assert _instantane(depot) == avant
    statut = next(a for a in suivante.appels if "status" in a)
    assert statut[statut.index("--") + 1:] == list(mh.EPINGLES_FORTES)
    assert not any("docker" in a for a in suivante.appels), "refus avant tout relevé"


def _fichiers(racine: Path) -> List[str]:
    return sorted(p.relative_to(racine).as_posix() for p in racine.rglob("*") if p.is_file())


def test_ecrire_un_echec_d_ecriture_ne_modifie_aucun_fichier_du_depot(depot, amont, monkeypatch):
    """Relecture P9 : les épingles étaient écrites une à une ; un échec au troisième fichier (disque plein, droit
    refusé) laissait deux fichiers réécrits sur neuf et sortait en trace Python, sans dire lesquels."""
    suivante = _release_suivante(amont)
    avant, fichiers_avant = _instantane(depot), _fichiers(depot)
    ecrire_octets = Path.write_bytes
    appels: List[Path] = []

    def ecrire_puis_echouer(self, donnees):
        appels.append(self)
        if len(appels) == 3:
            raise OSError(28, "No space left on device")
        return ecrire_octets(self, donnees)

    monkeypatch.setattr(Path, "write_bytes", ecrire_puis_echouer)
    with pytest.raises(mh.Refus, match="aucun fichier du dépôt n'a été modifié"):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    monkeypatch.undo()
    assert len(appels) == 3
    assert _instantane(depot) == avant
    assert _fichiers(depot) == fichiers_avant, "aucun fichier temporaire laissé"


def test_ecrire_un_remplacement_interrompu_nomme_les_fichiers_deja_reecrits(depot, amont, monkeypatch):
    """Au second temps (remplacements), un échec (fichier ouvert ailleurs sous Windows) nomme ce qui est déjà
    réécrit et ce qui ne l'est pas, et dit comment revenir à l'état committé ; aucun temporaire ne reste."""
    suivante = _release_suivante(amont)
    fichiers_avant = _fichiers(depot)
    remplacer = mh.os.replace
    faits: List[object] = []

    def remplacer_puis_echouer(source, cible):
        if len(faits) == 1:
            raise PermissionError(13, "fichier ouvert par un autre programme")
        faits.append(cible)
        return remplacer(source, cible)

    monkeypatch.setattr(mh.os, "replace", remplacer_puis_echouer)
    with pytest.raises(mh.Refus, match=rf"déjà réécrits : {mh.EPINGLE} ; non réécrits : {mh.DOCKERFILE}, .*"
                                       r"git checkout -- "):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    assert _fichiers(depot) == fichiers_avant


@pytest.mark.parametrize("alteration", ["borne", "openrpc_avant"])
def test_ecrire_controle_tout_ce_que_le_rapport_lit_avant_la_premiere_ecriture(depot, amont, alteration):
    """Relecture P9 : la borne requires_hermes et la copie d'avant de l'OpenRPC étaient lues APRÈS l'écriture : leur
    refus (code 2, « rien n'est écrit » pour l'utilisateur) tombait sur un dépôt déjà réécrit."""
    suivante = _release_suivante(amont)
    if alteration == "borne":
        chemin = depot / mh.GREFFON
        texte, n = re.subn(r"^requires_hermes: .*\n", "", chemin.read_text(encoding="utf-8"), flags=re.M)
        assert n == 1
        chemin.write_text(texte, encoding="utf-8", newline="\n")
    else:
        (depot / mh.OPENRPC).write_bytes(b"{}\n")
    avant = _instantane(depot)
    with pytest.raises(mh.Refus):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    assert _instantane(depot) == avant


def test_ecrire_un_inventaire_impossible_apres_l_ecriture_le_dit(depot, amont):
    """Seul l'inventaire (git grep des anciennes valeurs) vient après l'écriture : s'il échoue, le refus dit que les
    épingles fortes, elles, sont écrites (et l'ensemble écrit concorde)."""
    suivante = _release_suivante(amont)
    suivante.grep_code = 128
    with pytest.raises(mh.Refus, match="épingles fortes ont pourtant été écrites"):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    assert concordance.ecarts(depot) == []


def test_ecrire_refuse_une_structure_inattendue_sans_rien_ecrire(depot, amont):
    chemin = depot / mh.DOCKERFILE
    chemin.write_bytes(chemin.read_bytes().replace(b"\nFROM ", b"\nFROM scratch\nFROM ", 1))
    avant = _instantane(depot)
    with pytest.raises(mh.StructureInattendue, match="ligne FROM trouvé 2 fois"):
        _lancer(mh.ecrire, depot, _release_suivante(amont), "v2026.10.15")
    assert _instantane(depot) == avant


# =========================================================================== refus


@pytest.mark.parametrize("etiquette", ["latest", "main", "2026.9.24", "v2026.9", "v2026.9.24-desktop", "v26.9.24"])
def test_les_etiquettes_hors_release_sont_refusees(depot, amont, etiquette, capsys):
    assert mh.main(["verifier", "--etiquette", etiquette], racine=depot, executer=amont) == 2
    assert "Refus : Étiquette" in capsys.readouterr().err
    assert amont.appels == []
    assert mh.main(["ecrire", etiquette], racine=depot, executer=amont) == 2


def test_refus_condensat_introuvable(depot, amont, capsys):
    amont.inspect_code = 1
    assert mh.main(["verifier"], racine=depot, executer=amont) == 2
    assert "Condensat introuvable pour nousresearch/hermes-agent:" in capsys.readouterr().err


def test_une_variante_arm64_est_admise_une_plate_forme_absente_refusee(depot, amont, capsys):
    amont.variante_arm64 = {"variant": "v8"}
    assert _lancer(mh.verifier, depot, amont)[0] == 0
    amont.avec_arm64 = False
    assert mh.main(["verifier"], racine=depot, executer=amont) == 2
    assert "plate-forme (linux/amd64, linux/arm64) introuvable" in capsys.readouterr().err


def test_refus_commit_de_hermes_version_different_de_l_etiquette(depot, amont, capsys):
    v = amont.valeurs
    amont.version_affichee = f"Hermes Agent v{v.version} ({v.date_de_release}) · upstream 0badc0de"
    assert mh.main(["verifier"], racine=depot, executer=amont) == 2
    assert "n'est pas celui de l'étiquette" in capsys.readouterr().err


@pytest.mark.parametrize("absent, message", [("openrpc", "OpenRPC absent de l'image"),
                                             ("licence", "LICENSE absent de l'image")])
def test_refus_openrpc_ou_licence_absents(depot, amont, capsys, absent, message):
    setattr(amont, absent, None)
    assert mh.main(["verifier"], racine=depot, executer=amont) == 2
    assert message in capsys.readouterr().err


def test_refus_provenance_de_l_image_differente_de_l_etiquette(depot, amont, capsys):
    amont.provenance = {"version": amont.valeurs.version, "revision": "9" * 40}
    assert mh.main(["verifier"], racine=depot, executer=amont) == 2
    assert "différente de « hermes --version » et de l'étiquette" in capsys.readouterr().err


def test_date_affichee_ou_provenance_absente_sont_des_ecarts_pas_des_refus(depot, amont):
    v = amont.valeurs
    amont.version_affichee = f"Hermes Agent v{v.version} (2001.1.1) · upstream {v.commit[:8]}"
    amont.provenance = {}
    code, journal = _lancer(mh.verifier, depot, amont)
    assert code == 1
    assert "- date de release affichée par « hermes --version » (2001.1.1) différente de l'étiquette" in journal
    assert f"- provenance de l'image ({mh.CHEMIN_PROVENANCE_IMAGE}) absente ou illisible" in journal
    code, journal = _lancer(mh.ecrire, depot, amont, v.etiquette)
    assert code == 0 and "ATTENTION : date de release affichée" in journal


def test_un_champ_de_fixture_disparu_est_une_structure_inattendue_nommee(depot, amont):
    chemin = depot / mh.FIXTURE_DESKTOP
    texte, n = re.subn(r'\n\s*"methodes": \d+,', "", chemin.read_text(encoding="utf-8"))
    assert n == 1
    chemin.write_text(texte, encoding="utf-8", newline="\n")
    with pytest.raises(mh.StructureInattendue, match=r"meta\.json : champ openrpc\.methodes trouvé 0 fois"):
        _lancer(mh.verifier, depot, amont)


def test_refus_docker_ou_git_absents():
    with pytest.raises(mh.Refus, match="introuvable sur cet hôte"):
        mh.executer_reel(["acp-binaire-qui-n-existe-pas-docker"], 5)


def test_ecarts_constates_rendent_le_code_1_par_la_ligne_de_commande(depot, amont, capsys):
    amont.valeurs = replace(amont.valeurs, arm64="sha256:" + "8" * 64)
    assert mh.main(["verifier"], racine=depot, executer=amont) == 1
    assert "HERMES_IMAGE_LINUX_ARM64" in capsys.readouterr().out


# =========================================================================== relecture : forme vérifiée avant usage


def _poser_cle(racine: Path, cle: str, valeur: str) -> None:
    chemin = racine / mh.EPINGLE
    texte, n = re.subn(rf"^{cle}=.*$", lambda _m: f"{cle}={valeur}", chemin.read_text(encoding="utf-8"), flags=re.M)
    assert n == 1, cle
    chemin.write_text(texte, encoding="utf-8", newline="\n")


@pytest.mark.parametrize("cle, valeur", [
    ("HERMES_IMAGE", "-v/:/hote"), ("HERMES_IMAGE", "nousresearch/hermes-agent --privileged"),
    ("HERMES_TAG", "latest-v2026.9.24"), ("HERMES_COMMIT", ""), ("HERMES_VERSION", "0.21.5 ; x"),
    ("HERMES_IMAGE_INDEX", "sha256:court"), ("HERMES_IMAGE_LINUX_ARM64", "sha256:" + "a" * 63),
    ("OPENRPC_METHODES", "²"), ("OPENRPC_SHA256", "z" * 64), ("OPENRPC_INFO_VERSION", '1"'),
    ("CONTRAT_ACP_POSTE", "acp-poste/")])
def test_une_epingle_hors_forme_est_refusee_avant_toute_commande_externe(depot, amont, capsys, cle, valeur):
    """Relecture P9 : chaque valeur de HERMES_VERSION est validée AVANT d'être passée à docker ou git (une image
    « -v/:/hote » devenait une option de « docker run ») ou réécrite dans un fichier."""
    _poser_cle(depot, cle, valeur)
    amont.tags_git = [amont.valeurs.etiquette]
    page = json.dumps({"results": [{"name": amont.valeurs.etiquette}], "next": None}).encode()
    for commande in (["verifier"], ["inventaire"], ["ecrire", "v2026.10.15"], ["derniere"]):
        amont.appels.clear()
        assert mh.main(commande, racine=depot, executer=amont, lire_url=lambda _url: page) == 2, commande
        assert f"{cle}" in capsys.readouterr().err, commande
        # Seul « git status » (liste fixe de fichiers) précède la lecture de l'épingle dans « ecrire ».
        assert all(a[:4] == ["git", "-C", str(depot), "status"] for a in amont.appels), (commande, amont.appels)


def test_une_cle_en_double_dans_l_epingle_est_refusee(depot, amont, capsys):
    chemin = depot / mh.EPINGLE
    chemin.write_bytes(chemin.read_bytes() + b"HERMES_TAG=v2026.9.21\n")
    assert mh.main(["verifier"], racine=depot, executer=amont) == 2
    assert "HERMES_TAG" in capsys.readouterr().err and amont.appels == []


@pytest.mark.parametrize("champ, valeur", [
    ("arm64", "sha256:" + "f" * 64 + "\nHERMES_TAG=latest"), ("amd64", "sha256:abc"), ("amd64", 12)])
def test_un_condensat_de_plate_forme_hors_forme_est_refuse_sans_rien_ecrire(depot, amont, champ, valeur):
    """Relecture P9 : les condensats par plate-forme lus dans le manifeste du registre étaient seulement « non
    vides » ; un saut de ligne y injectait une clé dans HERMES_VERSION à l'écriture."""
    suivante = _release_suivante(amont)
    suivante.valeurs = replace(suivante.valeurs, **{champ: valeur})
    avant = _instantane(depot)
    with pytest.raises(mh.Refus, match="plate-forme"):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    assert _instantane(depot) == avant


@pytest.mark.parametrize("info", ['1"', "1`", "", "1\n2", "x" * 65])
def test_une_info_version_de_l_openrpc_hors_forme_est_refusee_sans_rien_ecrire(depot, amont, info):
    """Relecture P9 : info.version est écrite telle quelle dans une chaîne JSON (fixture du desktop), entre
    accents graves (README du contrat) et dans HERMES_VERSION ; « 1\" » cassait la fixture JSON."""
    suivante = _release_suivante(amont)
    assert suivante.openrpc is not None
    contrat = json.loads(suivante.openrpc)
    contrat["info"]["version"] = info
    suivante.openrpc = (json.dumps(contrat, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    avant = _instantane(depot)
    with pytest.raises(mh.Refus, match="info.version"):
        _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="15 octobre 2026")
    assert _instantane(depot) == avant


@pytest.mark.parametrize("date", ["1er octobre 2026", "le 2 octobre 2026", "2 oct. 2026", "32 octobre 2026",
                                  "2 octobre 2026\nHERMES_TAG=latest", "2 Octobre 2026", ""])
def test_une_date_hors_forme_est_refusee_avant_tout_releve(depot, amont, capsys, date):
    """Relecture P9 : « --date » était écrit tel quel ; « 1er octobre 2026 » produisait un README de contrat que
    l'outil lui-même refusait ensuite (motif « J mois AAAA ») et que la concordance déclarait illisible."""
    suivante = _release_suivante(amont)
    avant = _instantane(depot)
    assert mh.main(["ecrire", "v2026.10.15", "--date", date], racine=depot, executer=suivante) == 2
    assert "Date" in capsys.readouterr().err
    assert _instantane(depot) == avant
    assert not any(a[0] == "docker" for a in suivante.appels), "refus avant tout relevé"


def test_une_date_en_toutes_lettres_est_acceptee(depot, amont):
    suivante = _release_suivante(amont)
    assert _lancer(mh.ecrire, depot, suivante, "v2026.10.15", date="1 octobre 2026")[0] == 0
    assert concordance.ecarts(depot) == []


# =========================================================================== relecture : données illisibles


@pytest.mark.parametrize("relatif, alteration", [
    (mh.EPINGLE, "absent"), (mh.EPINGLE, "non_utf8"), (mh.FIXTURE_DESKTOP, "absent"),
    (mh.FIXTURE_DESKTOP, "non_utf8"), (mh.OPENRPC, "absent"), (mh.LICENCE, "absent"), (mh.GREFFON, "absent"),
    (mh.GREFFON, "non_utf8"), (mh.VERROU, "json"), (mh.VERROU, "liste")])
def test_un_fichier_illisible_est_un_refus_nomme_code_2(depot, amont, capsys, relatif, alteration):
    """Relecture P9 : un fichier absent, non UTF-8 ou un verrou JSON abîmé sortait en trace Python anglaise, code 1
    (celui des « écarts ») ; c'est un refus nommé, code 2, en français."""
    chemin = depot / relatif
    if alteration == "absent":
        chemin.unlink()
    elif alteration == "non_utf8":
        chemin.write_bytes(b"\xff" + chemin.read_bytes())
    elif alteration == "json":
        chemin.write_bytes(chemin.read_bytes() + b"}\n")
    else:
        chemin.write_bytes(b"[]\n" if relatif == mh.VERROU else b"")
    for commande in (["verifier"], ["ecrire", "v2026.10.15"]):
        assert mh.main(commande, racine=depot, executer=_release_suivante(amont) if commande[0] == "ecrire"
                       else amont) == 2, commande
        erreur = capsys.readouterr().err
        assert erreur.startswith("Refus : ") and relatif in erreur, (commande, erreur)


@pytest.mark.parametrize("page", [b"[]", b'"texte"', b'{"results": {"name": "v2026.9.24"}, "next": null}'])
def test_derniere_refuse_une_page_de_docker_hub_qui_n_est_pas_un_objet(depot, amont, page):
    amont.tags_git = ["v2026.9.24"]
    with pytest.raises(mh.Refus, match="Docker Hub illisible"):
        mh.derniere(depot, amont, lambda _url: page, sortie=lambda _l: None)


# =========================================================================== relecture : lectures réseau bornées


@pytest.mark.parametrize("suivante", [
    "file:///etc/passwd", "http://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags?page=2",
    "https://hub.docker.com.exemple.test/v2/repositories/nousresearch/hermes-agent/tags?page=2",
    "https://hub.docker.com/v2/repositories/autre/image/tags?page=2", 5])
def test_derniere_ne_suit_que_les_pages_de_l_api_de_docker_hub(depot, amont, suivante):
    """Relecture P9 : le lien « next » d'une page était suivi tel quel (urllib ouvre aussi file:// et http://) ;
    seule une page suivante de la même API, en https, est lue."""
    amont.tags_git = ["v2026.9.24"]
    lus: List[object] = []

    def lire(url: str) -> bytes:
        lus.append(url)
        return json.dumps({"results": [{"name": "v2026.9.24"}], "next": suivante}).encode()

    with pytest.raises(mh.Refus, match="page suivante"):
        mh.derniere(depot, amont, lire, sortie=lambda _l: None)
    assert lus == [mh.API_DOCKER_HUB]


def test_lire_url_reel_borne_la_lecture_et_ne_lit_que_l_api_de_docker_hub(monkeypatch):
    """Relecture P9 : ``reponse.read()`` lisait le corps entier, sans borne ; la lecture est arrêtée au-delà de
    LIMITE_PAGE octets (une page réelle de 100 étiquettes pèse de l'ordre de 100 Ko)."""
    ouvertes: List[str] = []
    tailles_lues: List[int] = []

    class Reponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, n: int = -1) -> bytes:
            tailles_lues.append(n)
            corps = 16 * 1024 * 1024
            return b" " * (corps if n is None or n < 0 else min(n, corps))

    def ouvrir(requete, timeout):
        ouvertes.append(requete.full_url)
        return Reponse()

    monkeypatch.setattr(mh.urllib.request, "urlopen", ouvrir)
    with pytest.raises(mh.Refus, match="octets"):
        mh.lire_url_reel(mh.API_DOCKER_HUB)
    assert tailles_lues and all(0 < n <= 16 * 1024 * 1024 for n in tailles_lues), tailles_lues
    for url in ("file:///etc/passwd", "http://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags",
                "https://exemple.test/v2/repositories/nousresearch/hermes-agent/tags"):
        with pytest.raises(mh.Refus, match="hors de l'API"):
            mh.lire_url_reel(url)
    assert ouvertes == [mh.API_DOCKER_HUB]


# =========================================================================== inventaire et derniere


@pytest.mark.parametrize("relatif, groupe", [
    (mh.EPINGLE, "fortes"), (mh.FIXTURE_DESKTOP, "fortes"), (mh.FIXTURE_INTERFACE, "fortes"),
    ("apps/desktop/tests/cpp/support/FauxHermes.cpp", "fixtures"),
    ("apps/interface/tests/accueil.test.tsx", "fixtures"), ("hermes/tests/image/test_sans_shell.py", "fixtures"), ("apps/desktop/src/auth/NativeAuthFlow.h", "citations"),
    ("hermes/plugins/acp-poste/noyau/kanban_adapter.py", "citations"), ("scripts/generer_themes.py", "citations"),
    ("docs/refonte/plan.md", "documentation"), ("CHANGELOG.md", "documentation"), ("README.md", "documentation")])
def test_inventaire_classe_chaque_fichier(relatif, groupe):
    assert mh.classer(relatif) == groupe


def test_inventaire_regroupe_les_lignes_de_git_grep(depot, amont):
    v = amont.valeurs
    amont.grep = (f"{mh.EPINGLE}:10:HERMES_VERSION={v.version}\n"
                  f"apps/desktop/tests/cpp/tst_sante.cpp:45:    QCOMPARE(x, QStringLiteral(\"{v.version}\"));\n"
                  f"hermes/plugins/acp-poste/garde_execution.py:13:Fonctionnement (source de Hermes {v.commit[:7]}) :\n"
                  f"docs/refonte/plan.md:1:{v.etiquette}\ndocs/refonte/plan.md:2:{v.version}\n")
    code, journal = _lancer(mh.inventaire, depot, amont)
    assert code == 0
    grep = next(a for a in amont.appels if "grep" in a)
    assert grep[grep.index("-F") + 1:] == ["-e", v.version, "-e", v.etiquette, "-e", v.commit[:7], "-e",
                                           v.index.removeprefix("sha256:")[:12]]
    assert "Épingles fortes (réécrites par « ecrire ») : 1 ligne(s) dans 1 fichier(s)" in journal
    assert "Fixtures et tests (faux serveurs : à mettre à jour à la main) : 1 ligne(s)" in journal
    assert "Citations dans le code et ses commentaires (à revérifier dans la PR de montée) : 1 ligne(s)" in journal
    assert "Documentation (historique : jamais réécrite) : 2 ligne(s) dans 1 fichier(s)" in journal
    assert "  docs/refonte/plan.md (2)" in journal


def test_derniere_release_commune_a_git_et_docker_hub(depot, amont):
    amont.tags_git = ["v2026.9.7", "v2026.9.21", "v2026.9.24", "v2026.10.2", "v2026.10.1", "nightly"]
    # Forme réelle du lien « next » de l'API (relevée le 02/10/2026, page_size=2).
    page2 = "https://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags?name=v&page=2&page_size=100"
    pages = {
        mh.API_DOCKER_HUB: {"results": [{"name": "latest"}, {"name": "v2026.10.1"}, {"name": "v2026.9.24-desktop"}],
                            "next": page2},
        page2: {"results": [{"name": "v2026.9.24"}, {"name": "main"}], "next": None},
    }
    lus: List[str] = []

    def lire(url: str) -> bytes:
        lus.append(url)
        return json.dumps(pages[url]).encode()

    lignes: List[str] = []
    assert mh.derniere(depot, amont, lire, sortie=lignes.append) == 0
    journal = "\n".join(lignes)
    assert lus == [mh.API_DOCKER_HUB, page2]
    assert "Dernière release publiée (git et Docker Hub) : v2026.10.1." in journal
    assert "Étiquette git sans image sur Docker Hub (ignorée) : v2026.10.2." in journal
    assert "Une release plus récente existe : préparer la PR de montée (ecrire v2026.10.1)." in journal


def test_derniere_sans_release_plus_recente(depot, amont):
    amont.tags_git = [amont.valeurs.etiquette]
    lignes: List[str] = []
    page = {"results": [{"name": amont.valeurs.etiquette}], "next": None}
    assert mh.derniere(depot, amont, lambda url: json.dumps(page).encode(), sortie=lignes.append) == 0
    assert "Aucune release plus récente que celle épinglée." in lignes


def test_derniere_refuse_une_api_illisible(depot, amont):
    amont.tags_git = ["v2026.9.24"]

    def illisible(url: str) -> bytes:
        raise OSError("réseau coupé")

    with pytest.raises(mh.Refus, match="Docker Hub illisible"):
        mh.derniere(depot, amont, illisible, sortie=lambda _l: None)


# =========================================================================== intégration continue


def test_image_yml_repete_la_montee_a_blanc_a_chaque_construction():
    """Cahier P9 § 5.4 (A5) : l'étape qui relevait le seul condensat d'index est remplacée par ``verifier``, son
    sur-ensemble ; code 0 ET « Aucun écart » exigés ; l'outil seul modifié relance le workflow (deux filtres)."""
    flux = (RACINE / ".github" / "workflows" / "image.yml").read_text(encoding="utf-8")
    assert flux.count('- "scripts/monter_hermes.py"') == 2, "pull_request ET push"
    debut = flux.index("      - name: Répétition à blanc de la montée de Hermes")
    etape = flux[debut:flux.index("\n      - name: ", debut + 1)]
    assert "set -euo pipefail" in etape
    assert "python3 scripts/monter_hermes.py verifier | tee /tmp/repetition-montee.txt" in etape
    assert 'grep -q "^Aucun écart : " /tmp/repetition-montee.txt' in etape
    # Avant la construction de l'image (la base est tirée par condensat une seule fois).
    assert debut < flux.index("      - name: Construire l'image ACP")
    assert "Relever le condensat de l'image officielle" not in flux


def _filtres_de_chemins(flux: str, declencheur: str) -> List[str]:
    """Motifs ``paths`` d'un déclencheur d'image.yml, lus ligne à ligne (bibliothèque standard, sans YAML)."""
    lignes = flux.splitlines()
    debut = lignes.index(f"  {declencheur}:")
    motifs: List[str] = []
    dans_paths = False
    for ligne in lignes[debut + 1:]:
        if ligne and not ligne.startswith("   "):
            break
        if ligne.strip() == "paths:":
            dans_paths = True
        elif dans_paths and ligne.strip().startswith("- "):
            motifs.append(ligne.strip()[2:].strip('"'))
        elif dans_paths and ligne.strip() and not ligne.strip().startswith("#"):
            break
    return motifs


def _correspond(motif: str, chemin: str) -> bool:
    """Motif de filtre de GitHub Actions : « ** » traverse les dossiers, « * » non."""
    expression = "".join(".*" if morceau == "**" else "[^/]*" if morceau == "*" else re.escape(morceau)
                         for morceau in re.split(r"(\*\*|\*)", motif))
    return re.fullmatch(expression, chemin) is not None


def test_image_yml_se_declenche_pour_chaque_fichier_lu_par_la_repetition():
    """Relecture P9 : la répétition à blanc compare chaque épingle forte au dépôt ; la fixture /v1/meta du desktop
    (apps/desktop/tests/fixtures/hermes/meta.json) n'était dans aucun filtre : une PR qui ne changeait qu'elle (un
    bloc imbriqué que « verifier » refuse, par exemple) ne relançait pas la répétition, et le rouge tombait plus tard
    sur une PR sans rapport."""
    flux = (RACINE / ".github" / "workflows" / "image.yml").read_text(encoding="utf-8")
    lus = (*mh.EPINGLES_FORTES, mh.GREFFON, "scripts/monter_hermes.py")
    for declencheur in ("pull_request", "push"):
        motifs = _filtres_de_chemins(flux, declencheur)
        assert "hermes/**" in motifs and "apps/interface/**" in motifs, (declencheur, motifs)
        assert [f for f in lus if not any(_correspond(m, f) for m in motifs)] == [], declencheur
    # Témoins du lecteur de motifs.
    assert _correspond("hermes/**", "hermes/contrat/HERMES_VERSION")
    assert not _correspond("apps/poste/src/**", "apps/desktop/tests/fixtures/hermes/meta.json")
    assert not _correspond("scripts/*.py", "scripts/tests/test_x.py")
