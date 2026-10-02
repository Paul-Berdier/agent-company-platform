"""Aucune copie de la version du produit n'échappe à scripts/check_version.py (cahier P9 § 6.2, garde préalable à
l'ouverture 1.0.0).

Tout fichier suivi qui PORTE une version (champ ``version`` de premier niveau d'un ``package.json`` ou d'un
``manifest.json``, ``[project].version`` d'un ``pyproject.toml``, ``version`` d'un ``plugin.yaml``, version racine
d'un ``package-lock.json``, ``__version__`` d'un module Python) figure dans une liste de ``check_version.py``, ou
dans les exclusions MOTIVÉES ci-dessous. Un nouveau greffon (par exemple le manifeste d'``acp-discussion`` de P7)
oublié dans les listes fait donc échouer ce test au lieu de garder 0.11.0 en silence à l'ouverture 1.0.0.
Bibliothèque standard seulement, comme le script."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Dict, Iterable, List, Optional

RACINE = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("check_version", RACINE / "scripts" / "check_version.py")
assert _SPEC is not None and _SPEC.loader is not None
cv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cv)

# Fichiers qui portent une version sans être une copie de celle du produit. Chaque entrée dit pourquoi.
EXCLUSIONS: Dict[str, str] = {
    "packages/pixel-office-engine/package.json":
        "moteur gelé octet pour octet sur archive/acp-0.10.0-avant-hermes (scripts/check_engine_frozen.py) : "
        "le monter romprait le gel (voir l'en-tête de scripts/check_version.py)",
    "hermes/tests/outils/temoin_compat/plugin.yaml":
        "greffon témoin des tests de contrat, que « hermes plugins compat » doit refuser ; jamais livré",
}

NOMS_JSON = {"package.json", "manifest.json"}
_VERSION_PYTHON = re.compile(r"^__version__\s*=", re.MULTILINE)


def _fichiers_suivis() -> List[str]:
    sortie = subprocess.run(["git", "ls-files", "-z"], cwd=RACINE, capture_output=True, check=True).stdout
    return [nom for nom in sortie.decode("utf-8").split("\0") if nom]


def version_portee(relatif: str, texte: str) -> Optional[str]:
    """Version que porte le fichier, ou ``None`` s'il n'en porte pas (ou si ce n'est pas un fichier de version)."""
    nom = relatif.rsplit("/", 1)[-1]
    if nom in NOMS_JSON or nom == "package-lock.json":
        try:
            donnees = json.loads(texte)
        except ValueError:
            return None
        version = donnees.get("version") if isinstance(donnees, dict) else None
        return version if isinstance(version, str) else None
    if nom == "pyproject.toml":
        version = tomllib.loads(texte).get("project", {}).get("version")
        return version if isinstance(version, str) else None
    if nom == "plugin.yaml":
        trouvees = cv._VERSION_YAML.findall(texte)
        return trouvees[0] if trouvees else None
    if nom.endswith(".py") and _VERSION_PYTHON.search(texte):
        trouvees = cv._VERSION_PYTHON.findall(texte)
        return trouvees[0] if trouvees else "(forme non reconnue par check_version)"
    return None


def fichiers_versionnes(fichiers: Iterable[str], lire) -> Dict[str, str]:
    versionnes: Dict[str, str] = {}
    for relatif in fichiers:
        nom = relatif.rsplit("/", 1)[-1]
        if nom not in NOMS_JSON | {"package-lock.json", "pyproject.toml", "plugin.yaml"} and not nom.endswith(".py"):
            continue
        texte = lire(relatif)
        if texte is None:
            continue
        version = version_portee(relatif, texte)
        if version is not None:
            versionnes[relatif] = version
    return versionnes


def couverts(module) -> List[str]:
    return [*module.PYPROJECTS, *module.PACKAGE_JSONS, *module.PLUGIN_YAMLS, *module.PYTHON_MODULES, *module.LOCKS]


def oublis(versionnes: Iterable[str], listes: Iterable[str], exclusions: Iterable[str]) -> List[str]:
    connus = set(listes) | set(exclusions)
    return sorted(f for f in versionnes if f not in connus)


def _lire(relatif: str) -> Optional[str]:
    try:
        return (RACINE / relatif).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def test_chaque_fichier_versionne_est_controle_ou_exclu_avec_un_motif():
    versionnes = fichiers_versionnes(_fichiers_suivis(), _lire)
    manquants = oublis(versionnes, couverts(cv), EXCLUSIONS)
    assert manquants == [], (
        "version portée mais contrôlée par aucune liste de scripts/check_version.py ni exclue avec un motif : "
        + ", ".join(f"{f} ({versionnes[f]})" for f in manquants))
    # Témoin positif : l'inventaire voit bien les copies connues (sinon le test passerait pour une mauvaise raison).
    assert set(couverts(cv)) <= set(versionnes), sorted(set(couverts(cv)) - set(versionnes))


def test_les_exclusions_sont_motivees_et_toujours_utiles():
    versionnes = fichiers_versionnes(_fichiers_suivis(), _lire)
    for relatif, motif in EXCLUSIONS.items():
        assert len(motif) > 20, relatif
        assert relatif in versionnes, f"exclusion périmée (fichier absent ou sans version) : {relatif}"
        assert relatif not in couverts(cv), f"exclu ET contrôlé : {relatif}"


def test_le_verrou_des_sources_de_l_interface_est_controle(tmp_path, monkeypatch, capsys):
    """Étape P9 : apps/interface/package-lock.json porte la version (racine et paquet racine) et n'était comparé à
    rien ; check_version.py le lit désormais comme le verrou de la racine. Témoin rouge sur une copie."""
    assert "apps/interface/package-lock.json" in cv.LOCKS
    assert cv.main() == 0
    for relatif in couverts(cv):
        (tmp_path / relatif).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relatif).write_bytes((RACINE / relatif).read_bytes())
    verrou = json.loads((tmp_path / "apps/interface/package-lock.json").read_text(encoding="utf-8"))
    verrou["packages"][""]["version"] = "0.0.1"
    (tmp_path / "apps/interface/package-lock.json").write_text(json.dumps(verrou), encoding="utf-8")
    monkeypatch.setattr(cv, "ROOT", tmp_path)
    capsys.readouterr()
    assert cv.main() == 1
    assert "apps/interface/package-lock.json#packages/<root>: version '0.0.1'" in capsys.readouterr().err


def test_un_manifeste_retire_des_listes_est_signale():
    """Témoin rouge sur une copie : on retire un manifeste de greffon des listes, l'oubli est nommé."""
    versionnes = fichiers_versionnes(_fichiers_suivis(), _lire)
    retire = "hermes/plugins/acp-projets/dashboard/manifest.json"
    listes = [f for f in couverts(cv) if f != retire]
    assert oublis(versionnes, listes, EXCLUSIONS) == [retire]


def test_un_nouveau_greffon_non_declare_est_signale():
    """Témoin : un greffon ajouté (manifeste et plugin.yaml) sans entrée dans check_version.py est trouvé."""
    contenus = {
        "hermes/plugins/acp-nouveau/dashboard/manifest.json": json.dumps({"name": "acp-nouveau", "version": "0.11.0"}),
        "hermes/plugins/acp-nouveau/plugin.yaml": "name: acp-nouveau\nversion: 0.11.0\n",
        "apps/nouveau/src/nouveau/__init__.py": '__version__ = "0.11.0"\n',
        "apps/nouveau/pyproject.toml": '[project]\nname = "nouveau"\nversion = "0.11.0"\n',
        "apps/nouveau/package-lock.json": json.dumps({"name": "n", "version": "0.11.0", "packages": {}}),
        # Sans version : ignorés.
        "apps/web/public/assets/core/manifest.json": json.dumps({"manifest_version": 1}),
        "apps/nouveau/src/nouveau/outil.py": "VERSION = 3\n",
    }
    versionnes = fichiers_versionnes(contenus, contenus.get)
    assert oublis(versionnes, couverts(cv), EXCLUSIONS) == sorted([
        "hermes/plugins/acp-nouveau/dashboard/manifest.json", "hermes/plugins/acp-nouveau/plugin.yaml",
        "apps/nouveau/src/nouveau/__init__.py", "apps/nouveau/pyproject.toml", "apps/nouveau/package-lock.json"])
