"""Contrôles STATIQUES de l'image de l'exécutant (cahier P6 § 8.2, § 10.2 point 4), sans Docker : ils tournent avec
la suite du dépôt (ci.yml, Linux et Windows). Les contrôles sur l'image construite sont dans test_image.py.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
EXECUTANT = RACINE / "executant"
DOCKERFILE = (EXECUTANT / "Dockerfile").read_text(encoding="utf-8")
BINAIRES = tomllib.loads((EXECUTANT / "binaires.toml").read_text(encoding="utf-8"))
SENSIBLES = re.compile(r"JETON|TOKEN|SECRET|KEY|CLE|PASSWORD", re.IGNORECASE)


def _instructions(texte: str) -> list[tuple[str, str]]:
    """(instruction, arguments) du Dockerfile, lignes de continuation jointes, commentaires retirés."""
    lignes, courante = [], ""
    for ligne in texte.splitlines():
        if not courante and (not ligne.strip() or ligne.lstrip().startswith("#")):
            continue
        courante += ligne.rstrip("\\").rstrip() + " "
        if not ligne.rstrip().endswith("\\"):
            lignes.append(courante.strip())
            courante = ""
    return [(l.split(None, 1)[0].upper(), l.split(None, 1)[1] if " " in l else "") for l in lignes]


INSTRUCTIONS = _instructions(DOCKERFILE)


def test_base_epinglee_par_condensat_egal_a_binaires_toml():
    bases = [a for i, a in INSTRUCTIONS if i == "FROM" and not a.split()[0] in ("base", "commun")]
    assert bases == [f"{BINAIRES['base']['image']}@{BINAIRES['base']['condensat']} AS base"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", BINAIRES["base"]["condensat"])


def test_derniere_cible_est_la_finale_de_railway():
    etapes = [a.split()[-1] for i, a in INSTRUCTIONS if i == "FROM"]
    assert etapes == ["base", "binaires", "roues", "commun", "factice", "finale"]
    assert "--from=binaires" in DOCKERFILE.split("AS finale", 1)[1]
    assert "--from=binaires" not in DOCKERFILE.split("AS factice", 1)[1].split("AS finale", 1)[0]


def test_versions_apt_egales_a_binaires_toml():
    installes = dict(re.findall(r"^\s+([a-z0-9.+-]+)=([^\s\\;]+)", DOCKERFILE.split("AS binaires", 1)[0], re.MULTILINE))
    assert installes == BINAIRES["apt"]


def test_aucun_arg_ni_env_sensible_ni_curl_sh_ni_port():
    for instruction, arguments in INSTRUCTIONS:
        if instruction in ("ARG", "ENV"):
            noms = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=", arguments) or [arguments.split()[0]]
            for nom in noms:
                assert not SENSIBLES.search(nom), f"{instruction} {nom} : nom de secret interdit dans l'image"
        assert instruction not in ("EXPOSE", "HEALTHCHECK"), instruction
    assert not re.search(r"curl[^\n]*\|\s*(ba)?sh", DOCKERFILE)
    assert "install.sh" not in DOCKERFILE.replace("Jamais install.sh", "")
    entree = [a for i, a in INSTRUCTIONS if i == "ENTRYPOINT"]
    assert entree == ['["/usr/bin/tini", "--", "/opt/acp/bin/acp-entree-executant"]']


def test_contexte_en_liste_blanche():
    lignes = [l for l in (EXECUTANT / "Dockerfile.dockerignore").read_text(encoding="utf-8").splitlines()
              if l and not l.startswith("#")]
    assert lignes[0] == "*"
    admis = {l[1:] for l in lignes if l.startswith("!")}
    for interdit in (".git", "docs", ".claude", ".env", "hermes/tests", "apps/poste/tests", "executant/tests"):
        assert not any(a == interdit or a.startswith(interdit + "/") for a in admis), interdit


def test_reglages_claude_alignes_sur_la_politique():
    reglages = json.loads((EXECUTANT / "claude-settings.json").read_text(encoding="utf-8"))
    politique = tomllib.loads((EXECUTANT / "politique" / "executant.toml").read_text(encoding="utf-8"))
    assert reglages["availableModels"] == politique["claude"]["alias_permis"]
    assert "fallbackModel" not in json.dumps(reglages) and "apiKeyHelper" not in json.dumps(reglages)
    refus = reglages["permissions"]["deny"]
    for chemin in ("//donnees/codex/**", "//donnees/claude/**", "//donnees/acp/**", "//etc/acp/**", "//proc/**"):
        assert f"Read({chemin})" in refus


def test_gitconfig_coupe_crochets_et_protocoles():
    texte = (EXECUTANT / "gitconfig").read_text(encoding="utf-8")
    for attendu in ("hooksPath = /dev/null", "fsmonitor = false", "symlinks = false", "allow = never",
                    "[protocol \"https\"]", "directory = /donnees/depots/*", "directory = /donnees/espaces/*"):
        assert attendu in texte, attendu


def test_scripts_executables_et_en_lf():
    for nom in ("acp-entree-executant", "acp-askpass", "acp-poste", "verifier-binaires"):
        contenu = (EXECUTANT / "bin" / nom).read_bytes()
        assert contenu.startswith(b"#!") and b"\r\n" not in contenu, nom
    for nom in ("faux-claude", "faux-codex"):
        assert (EXECUTANT / "factice" / nom).read_bytes().startswith(b"#!/usr/local/bin/python3.12 -I\n")
