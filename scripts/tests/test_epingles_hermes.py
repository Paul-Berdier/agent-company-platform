"""Concordance statique de toutes les épingles de Hermes Agent (cahier P9 § 5.3), hors ligne, sous Linux et Windows.

Source unique : ``hermes/contrat/HERMES_VERSION``. Chaque autre copie d'une valeur épinglée doit lui être égale :
ligne ``FROM`` et en-tête de ``hermes/image/Dockerfile``, copie de l'OpenRPC (SHA-256, ``info.version``, nombre de
méthodes), provenance de ``hermes/contrat/README.md`` et de ``hermes/THIRD_PARTY.md``, bloc ``hermes`` et
``livrees.instantane_hermes`` du verrou du catalogue (comparés à rien jusqu'à P9), borne ``requires_hermes`` du
greffon (borne inférieure, au plus la version épinglée), fixtures ``/v1/meta`` du desktop et de l'interface.

Les tests de l'image et de contrat LISENT la version épinglée au lieu de la figer (dernier test) : une montée par
``scripts/monter_hermes.py ecrire`` puis une reconstruction suffit pour les épingles fortes. Les fixtures de faux
serveur et les citations « Hermes 0.21.5 … fichier:ligne » relèvent d'un travail humain listé par
``monter_hermes.py inventaire``.

Chaque règle rougit sur une copie altérée (témoins en fin de fichier). Bibliothèque standard seulement."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import shutil
import tokenize
from pathlib import Path
from typing import Dict, List

import pytest

RACINE = Path(__file__).resolve().parents[2]

EPINGLE_REL = "hermes/contrat/HERMES_VERSION"
DOCKERFILE_REL = "hermes/image/Dockerfile"
OPENRPC_REL = "hermes/contrat/gateway-contract.openrpc.json"
LICENCE_REL = "hermes/contrat/LICENSE-hermes-agent.txt"
README_CONTRAT_REL = "hermes/contrat/README.md"
TIERS_REL = "hermes/THIRD_PARTY.md"
VERROU_REL = "hermes/catalogue/catalogue.lock.json"
GREFFON_REL = "hermes/plugins/acp-poste/plugin.yaml"
FIXTURE_DESKTOP_REL = "apps/desktop/tests/fixtures/hermes/meta.json"
FIXTURE_INTERFACE_REL = "apps/interface/tests/fixtures.ts"
FICHIERS = (EPINGLE_REL, DOCKERFILE_REL, OPENRPC_REL, LICENCE_REL, README_CONTRAT_REL, TIERS_REL, VERROU_REL,
            GREFFON_REL, FIXTURE_DESKTOP_REL, FIXTURE_INTERFACE_REL)

CLES = ("HERMES_VERSION", "HERMES_TAG", "HERMES_COMMIT", "HERMES_IMAGE", "HERMES_IMAGE_INDEX",
        "HERMES_IMAGE_LINUX_AMD64", "HERMES_IMAGE_LINUX_ARM64", "OPENRPC_INFO_VERSION", "OPENRPC_METHODES",
        "OPENRPC_SHA256", "CONTRAT_ACP_POSTE")
FORMES = {
    "HERMES_VERSION": r"\d+\.\d+\.\d+",
    "HERMES_TAG": r"v\d{4}\.\d{1,2}\.\d{1,2}(?:\.\d+)?",
    "HERMES_COMMIT": r"[0-9a-f]{40}",
    "HERMES_IMAGE": r"nousresearch/hermes-agent",
    "HERMES_IMAGE_INDEX": r"sha256:[0-9a-f]{64}",
    "HERMES_IMAGE_LINUX_AMD64": r"sha256:[0-9a-f]{64}",
    "HERMES_IMAGE_LINUX_ARM64": r"sha256:[0-9a-f]{64}",
    "OPENRPC_INFO_VERSION": r"\S+",
    "OPENRPC_METHODES": r"[1-9]\d*",
    "OPENRPC_SHA256": r"[0-9a-f]{64}",
    "CONTRAT_ACP_POSTE": r"acp-poste/\d+",
}
DATE_RELEVE = re.compile(r"^# Condensats relevés le (\d{1,2} \S+ \d{4}) par$", re.M)


def lire_epingle(racine: Path) -> Dict[str, str]:
    valeurs: Dict[str, str] = {}
    for ligne in (racine / EPINGLE_REL).read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            valeurs[cle] = valeur
    return valeurs


def _version(texte: str):
    return tuple(int(p) for p in texte.split("."))


def ecarts(racine: Path) -> List[str]:
    """Écarts entre HERMES_VERSION et chaque autre copie d'une valeur épinglée (liste vide : concordance)."""
    e: List[str] = []
    ep = lire_epingle(racine)
    texte_epingle = (racine / EPINGLE_REL).read_text(encoding="utf-8")
    if sorted(ep) != sorted(CLES):
        e.append(f"{EPINGLE_REL} : clés {sorted(ep)}, attendu {sorted(CLES)}")
        return e
    for cle, forme in FORMES.items():
        if not re.fullmatch(forme, ep[cle]):
            e.append(f"{EPINGLE_REL} : {cle}={ep[cle]!r} hors de la forme {forme}")
    if len(DATE_RELEVE.findall(texte_epingle)) != 1:
        e.append(f"{EPINGLE_REL} : ligne « # Condensats relevés le <date> par » absente ou en double")
    reference = f"{ep['HERMES_IMAGE']}:{ep['HERMES_TAG']}"
    if f"#   docker buildx imagetools inspect {reference}\n" not in texte_epingle:
        e.append(f"{EPINGLE_REL} : la commande de relevé ne cite pas {reference}")

    # Dockerfile : ligne FROM (seule ligne FROM) et en-tête.
    dockerfile = (racine / DOCKERFILE_REL).read_text(encoding="utf-8")
    lignes_from = [l for l in dockerfile.splitlines() if l.startswith("FROM ")]
    attendu_from = f"FROM {reference}@{ep['HERMES_IMAGE_INDEX']}"
    if lignes_from != [attendu_from]:
        e.append(f"{DOCKERFILE_REL} : lignes FROM {lignes_from}, attendu [{attendu_from!r}]")
    for fragment in (f"de l'étiquette {ep['HERMES_TAG']}\n",
                     f"# (Hermes Agent {ep['HERMES_VERSION']}, commit {ep['HERMES_COMMIT'][:7]}), relevé le ",
                     f"#   docker buildx imagetools inspect {reference}\n"):
        if fragment not in dockerfile:
            e.append(f"{DOCKERFILE_REL} : l'en-tête ne contient pas {fragment.strip()!r}")

    # Copie de l'OpenRPC.
    brut = (racine / OPENRPC_REL).read_bytes()
    if hashlib.sha256(brut).hexdigest() != ep["OPENRPC_SHA256"]:
        e.append(f"{OPENRPC_REL} : SHA-256 {hashlib.sha256(brut).hexdigest()}, épinglé {ep['OPENRPC_SHA256']}")
    try:
        contrat = json.loads(brut)
        info, methodes = str(contrat["info"]["version"]), len(contrat["methods"])
    except (ValueError, KeyError, TypeError) as exc:
        e.append(f"{OPENRPC_REL} : illisible ({type(exc).__name__})")
    else:
        if info != ep["OPENRPC_INFO_VERSION"]:
            e.append(f"{OPENRPC_REL} : info.version {info!r}, épinglé {ep['OPENRPC_INFO_VERSION']!r}")
        if methodes != int(ep["OPENRPC_METHODES"]):
            e.append(f"{OPENRPC_REL} : {methodes} méthodes, épinglé {ep['OPENRPC_METHODES']}")
    if not (racine / LICENCE_REL).read_text(encoding="utf-8").startswith("MIT License"):
        e.append(f"{LICENCE_REL} : n'est pas la licence MIT de Hermes Agent")

    # Provenance (README du contrat et THIRD_PARTY.md), espaces et retours à la ligne indifférents.
    readme = " ".join((racine / README_CONTRAT_REL).read_text(encoding="utf-8").split())
    for fragment in (f"étiquette `{ep['HERMES_TAG']}`, commit `{ep['HERMES_COMMIT']}`",
                     f"SHA-256 `{ep['OPENRPC_SHA256']}`",
                     f"`info.version` = `{ep['OPENRPC_INFO_VERSION']}`, {ep['OPENRPC_METHODES']} méthodes"):
        if fragment not in readme:
            e.append(f"{README_CONTRAT_REL} : la provenance ne contient pas {fragment!r}")
    tiers = (racine / TIERS_REL).read_text(encoding="utf-8")
    debut = tiers.find("## NousResearch/hermes-agent\n")
    # Espace insécable avant le deux-points (typographie française) : ramené à une espace simple.
    section = " ".join(tiers[debut:tiers.find("\n## ", debut + 1)].split()) if debut >= 0 else ""
    attendu_tiers = f"- Commit : `{ep['HERMES_COMMIT']}` (étiquette `{ep['HERMES_TAG']}`)"
    if attendu_tiers not in section:
        e.append(f"{TIERS_REL} : la section NousResearch/hermes-agent ne contient pas {attendu_tiers!r}")

    # Verrou du catalogue : bloc hermes et instantané des skills livrées.
    verrou = json.loads((racine / VERROU_REL).read_text(encoding="utf-8"))
    attendu_bloc = {"version": ep["HERMES_VERSION"], "etiquette": ep["HERMES_TAG"], "commit": ep["HERMES_COMMIT"],
                    "condensat_index": ep["HERMES_IMAGE_INDEX"]}
    if verrou.get("hermes") != attendu_bloc:
        e.append(f"{VERROU_REL} : bloc hermes {verrou.get('hermes')}, attendu {attendu_bloc}")
    instantane = (verrou.get("livrees") or {}).get("instantane_hermes")
    if instantane != ep["HERMES_VERSION"]:
        e.append(f"{VERROU_REL} : livrees.instantane_hermes {instantane!r}, épinglé {ep['HERMES_VERSION']!r}")

    # Borne requires_hermes du greffon : borne inférieure, satisfaite par la version épinglée.
    bornes = re.findall(r'^requires_hermes:\s*"?>=\s*(\d+\.\d+\.\d+)"?\s*$',
                        (racine / GREFFON_REL).read_text(encoding="utf-8"), re.M)
    if len(bornes) != 1:
        e.append(f"{GREFFON_REL} : requires_hermes absent ou hors de la forme \">=X.Y.Z\"")
    elif re.fullmatch(FORMES["HERMES_VERSION"], ep["HERMES_VERSION"]) and \
            _version(bornes[0]) > _version(ep["HERMES_VERSION"]):
        e.append(f"{GREFFON_REL} : requires_hermes >={bornes[0]} exclut la version épinglée {ep['HERMES_VERSION']}")

    # Fixture /v1/meta du desktop.
    meta = json.loads((racine / FIXTURE_DESKTOP_REL).read_text(encoding="utf-8"))
    attendus_desktop = {
        ("hermes", "version"): ep["HERMES_VERSION"], ("hermes", "version_testee"): ep["HERMES_VERSION"],
        ("hermes", "etiquette"): ep["HERMES_TAG"], ("hermes", "commit"): ep["HERMES_COMMIT"],
        ("image", "base"): ep["HERMES_IMAGE"], ("image", "condensat_index"): ep["HERMES_IMAGE_INDEX"],
        ("openrpc", "info_version"): ep["OPENRPC_INFO_VERSION"],
        ("openrpc", "info_version_epinglee"): ep["OPENRPC_INFO_VERSION"],
        ("openrpc", "methodes"): int(ep["OPENRPC_METHODES"]) if ep["OPENRPC_METHODES"].isdigit() else None,
        ("openrpc", "empreinte_installee"): ep["OPENRPC_SHA256"],
        ("openrpc", "empreinte_epinglee"): ep["OPENRPC_SHA256"],
    }
    for (bloc, cle), attendu in attendus_desktop.items():
        trouve = (meta.get(bloc) or {}).get(cle)
        if trouve != attendu:
            e.append(f"{FIXTURE_DESKTOP_REL} : {bloc}.{cle} = {trouve!r}, attendu {attendu!r}")

    # Fixture META de l'interface (TypeScript) : valeurs de chaîne des blocs hermes et image.
    ts = (racine / FIXTURE_INTERFACE_REL).read_text(encoding="utf-8")
    bloc_meta = re.search(r"export const META = \{(.*?)\n\};", ts, re.S)
    champs: Dict[str, Dict[str, str]] = {}
    for nom in ("hermes", "image"):
        bloc = re.search(rf"\n  {nom}: \{{(.*?)\}}", bloc_meta.group(1), re.S) if bloc_meta else None
        champs[nom] = dict(re.findall(r'(\w+): "([^"]*)"', bloc.group(1))) if bloc else {}
    attendus_interface = {
        ("hermes", "version"): ep["HERMES_VERSION"], ("hermes", "version_testee"): ep["HERMES_VERSION"],
        ("hermes", "etiquette"): ep["HERMES_TAG"], ("hermes", "commit"): ep["HERMES_COMMIT"][:7],
        ("image", "base"): reference, ("image", "condensat_index"): ep["HERMES_IMAGE_INDEX"],
    }
    for (bloc, cle), attendu in attendus_interface.items():
        trouve = champs[bloc].get(cle)
        if trouve != attendu:
            e.append(f"{FIXTURE_INTERFACE_REL} : META.{bloc}.{cle} = {trouve!r}, attendu {attendu!r}")
    return e


def valeurs_figees(racine: Path) -> List[str]:
    """Valeurs épinglées écrites en dur dans les tests Python de hermes/tests (au lieu d'être lues dans
    HERMES_VERSION). Commentaires exclus ; les docstrings (chaînes à triples guillemets) peuvent citer « Hermes
    0.21.5 » ou un fichier:ligne, jamais un commit complet ni un condensat."""
    ep = lire_epingle(racine)
    longs = [ep["HERMES_COMMIT"], ep["HERMES_IMAGE_INDEX"].removeprefix("sha256:"),
             ep["HERMES_IMAGE_LINUX_AMD64"].removeprefix("sha256:"),
             ep["HERMES_IMAGE_LINUX_ARM64"].removeprefix("sha256:"), ep["OPENRPC_SHA256"]]
    date = ep["HERMES_TAG"].removeprefix("v")
    types_chaine = {tokenize.STRING} | ({getattr(tokenize, "FSTRING_MIDDLE")} if hasattr(tokenize, "FSTRING_MIDDLE")
                                         else set())
    trouvees: List[str] = []
    for chemin in sorted((racine / "hermes" / "tests").rglob("*.py")):
        relatif = chemin.relative_to(racine).as_posix()
        source = chemin.read_text(encoding="utf-8")
        for jeton in tokenize.generate_tokens(io.StringIO(source).readline):
            if jeton.type == tokenize.COMMENT or jeton.type not in types_chaine:
                continue
            lieu = f"{relatif}:{jeton.start[0]}"
            texte = jeton.string
            if any(valeur in texte for valeur in longs):
                trouvees.append(f"{lieu} : commit ou condensat épinglé en dur")
            triple = texte.lstrip("rbfuRBFU").startswith(('"""', "'''"))
            if jeton.type == tokenize.STRING and not triple:
                try:
                    litteral = ast.literal_eval(texte)
                except (ValueError, SyntaxError):
                    litteral = None
                if litteral == ep["HERMES_VERSION"]:
                    trouvees.append(f"{lieu} : version {ep['HERMES_VERSION']} en dur")
            if not triple and re.search(rf"(?<![\d.]){re.escape(date)}(?![\d.])", texte):
                trouvees.append(f"{lieu} : date de release {date} en dur")
    return trouvees


# =========================================================================== le dépôt


def test_toutes_les_epingles_de_hermes_concordent():
    assert ecarts(RACINE) == []


def test_les_tests_de_l_image_et_de_contrat_lisent_la_version_epinglee():
    """Cahier P9 § 5.3 : test_contrat_image.py (hermes --version, /api/status, /v1/meta) et test_meta.py (version,
    commit, condensat, OpenRPC) lisaient 0.21.5, le commit et le condensat en dur."""
    assert valeurs_figees(RACINE) == []


# =========================================================================== témoins (copie altérée)


@pytest.fixture
def copie(tmp_path: Path) -> Path:
    for relatif in FICHIERS:
        (tmp_path / relatif).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RACINE / relatif, tmp_path / relatif)
    return tmp_path


def _remplacer(racine: Path, relatif: str, avant: str, apres: str, compte: int = 1) -> None:
    chemin = racine / relatif
    texte = chemin.read_bytes().decode("utf-8")
    assert texte.count(avant) == compte, (relatif, avant, texte.count(avant))
    chemin.write_bytes(texte.replace(avant, apres).encode("utf-8"))


def test_la_copie_intacte_concorde(copie):
    assert ecarts(copie) == []


def test_temoin_bloc_hermes_du_verrou_du_catalogue(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, VERROU_REL, f'"etiquette": "{ep["HERMES_TAG"]}"', '"etiquette": "v2026.9.21"')
    assert [x for x in ecarts(copie) if "bloc hermes" in x] and len(ecarts(copie)) == 1


def test_temoin_instantane_des_skills_livrees(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, VERROU_REL, f'"instantane_hermes": "{ep["HERMES_VERSION"]}"', '"instantane_hermes": "0.21.4"')
    assert ecarts(copie) == [f"{VERROU_REL} : livrees.instantane_hermes '0.21.4', épinglé '{ep['HERMES_VERSION']}'"]


def test_temoin_condensat_de_la_ligne_from(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, DOCKERFILE_REL, f"@{ep['HERMES_IMAGE_INDEX']}", "@sha256:" + "0" * 64)
    assert len(ecarts(copie)) == 1 and "lignes FROM" in ecarts(copie)[0]


def test_temoin_en_tete_du_dockerfile(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, DOCKERFILE_REL, f"(Hermes Agent {ep['HERMES_VERSION']},", "(Hermes Agent 0.21.4,")
    assert len(ecarts(copie)) == 1 and "en-tête" in ecarts(copie)[0]


def test_temoin_copie_de_l_openrpc_modifiee(copie):
    chemin = copie / OPENRPC_REL
    chemin.write_bytes(chemin.read_bytes() + b"\n")
    assert len(ecarts(copie)) == 1 and "SHA-256" in ecarts(copie)[0]


def test_temoin_provenance_du_contrat(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, README_CONTRAT_REL, f"`{ep['HERMES_COMMIT']}`", "`" + "a" * 40 + "`")
    assert len(ecarts(copie)) == 1 and README_CONTRAT_REL in ecarts(copie)[0]


def test_temoin_third_party(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, TIERS_REL, f"(étiquette `{ep['HERMES_TAG']}`)", "(étiquette `v2026.9.21`)")
    assert len(ecarts(copie)) == 1 and TIERS_REL in ecarts(copie)[0]


def test_temoin_borne_requires_hermes_au_dela_de_la_version_epinglee(copie):
    ep = lire_epingle(copie)
    chemin = copie / GREFFON_REL
    texte = chemin.read_bytes().decode("utf-8")
    altere, nombre = re.subn(r'^requires_hermes: .*$', 'requires_hermes: ">=99.0.0"', texte, flags=re.M)
    assert nombre == 1
    chemin.write_bytes(altere.encode("utf-8"))
    assert ecarts(copie) == [f"{GREFFON_REL} : requires_hermes >=99.0.0 exclut la version épinglée "
                             f"{ep['HERMES_VERSION']}"]


def test_temoin_fixture_du_desktop(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, FIXTURE_DESKTOP_REL, f'"version_testee": "{ep["HERMES_VERSION"]}"', '"version_testee": "0.21.4"')
    assert ecarts(copie) == [f"{FIXTURE_DESKTOP_REL} : hermes.version_testee = '0.21.4', attendu "
                             f"'{ep['HERMES_VERSION']}'"]


def test_temoin_fixture_de_l_interface(copie):
    ep = lire_epingle(copie)
    _remplacer(copie, FIXTURE_INTERFACE_REL, f'etiquette: "{ep["HERMES_TAG"]}"', 'etiquette: "v2026.9.21"')
    assert ecarts(copie) == [f"{FIXTURE_INTERFACE_REL} : META.hermes.etiquette = 'v2026.9.21', attendu "
                             f"'{ep['HERMES_TAG']}'"]


def test_temoin_epingle_hors_forme(copie):
    _remplacer(copie, EPINGLE_REL, "HERMES_TAG=v", "HERMES_TAG=latest-v")
    assert any("HERMES_TAG='latest-v" in x for x in ecarts(copie))


def test_temoin_valeur_figee_dans_un_test(copie):
    ep = lire_epingle(copie)
    test = copie / "hermes" / "tests" / "image" / "test_exemple.py"
    test.parent.mkdir(parents=True)
    test.write_text(
        '"""Citation permise : Hermes ' + ep["HERMES_VERSION"] + ' (fichier.py:12)."""\n'
        "# Commentaire permis : " + ep["HERMES_COMMIT"] + "\n"
        'VERSION = "' + ep["HERMES_VERSION"] + '"\n'
        'COMMIT = "' + ep["HERMES_COMMIT"] + '"\n'
        'LIGNE = f"Hermes Agent v{VERSION} (' + ep["HERMES_TAG"].removeprefix("v") + ')"\n',
        encoding="utf-8")
    assert valeurs_figees(copie) == [
        f"hermes/tests/image/test_exemple.py:3 : version {ep['HERMES_VERSION']} en dur",
        "hermes/tests/image/test_exemple.py:4 : commit ou condensat épinglé en dur",
        f"hermes/tests/image/test_exemple.py:5 : date de release {ep['HERMES_TAG'].removeprefix('v')} en dur",
    ]
