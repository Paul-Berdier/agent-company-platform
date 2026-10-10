"""Outils communs des tests du poste (étape P5) : racine jetable, ``poste.toml`` de test, coffre en mémoire, faux
Codex et faux Claude pilotés par scénario.

Aucun test ne touche les vrais emplacements d'une installation (``C:\\ProgramData\\ACP``, le coffre, le profil Codex
ou Claude du propriétaire) : tout vit sous ``tmp_path`` (:meth:`Emplacements.de_test`), et les CLI sont de faux
processus locaux lancés par ``sys.executable -I``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from acp_poste.chemins import Emplacements

ICI = Path(__file__).resolve().parent
PYTHON = str(Path(sys.executable).resolve())
FAUX_CODEX = str(ICI / "faux_codex.py")
FAUX_CLAUDE = str(ICI / "faux_claude.py")
WINDOWS_SEULEMENT = pytest.mark.skipif(os.name != "nt", reason="propre à Windows (exécuté sur windows-2022)")


class CoffreMemoire:
    """Coffre de test en mémoire (jamais une option de production : le coffre DPAPI refuse hors Windows)."""

    def __init__(self, valeurs: dict[str, str] | None = None) -> None:
        self.valeurs = dict(valeurs or {})

    def lire(self, usage: str) -> str | None:
        return self.valeurs.get(usage)

    def ecrire(self, usage: str, valeur: str) -> None:
        self.valeurs[usage] = valeur

    def effacer(self, usage: str) -> bool:
        return self.valeurs.pop(usage, None) is not None

    def present(self, usage: str) -> bool:
        return usage in self.valeurs


def toml_chaine(valeur: str) -> str:
    return "'" + valeur + "'"


class Poste:
    """Un poste de test : racine jetable, ``poste.toml`` écrit à la demande, contexte prêt à l'emploi."""

    def __init__(self, racine: Path) -> None:
        self.racine = racine
        self.emplacements = Emplacements.de_test(racine)
        for dossier in (self.emplacements.acp_programdata, self.emplacements.acp_local, self.emplacements.outils):
            dossier.mkdir(parents=True, exist_ok=True)
        self.coffre = CoffreMemoire()
        self.scenario_codex: dict[str, Any] = {}
        self.scenario_claude: dict[str, Any] = {}
        self.origine = "https://hermes-acp.test"
        self.options = None  # OptionsClient de test (autorité, résolution), posé par les tests du protocole

    # ------------------------------------------------------------------ poste.toml
    def toml(self, *, compte: str = "proprietaire", sections: dict[str, dict[str, Any]] | None = None,
             supprimer: tuple[str, ...] = (), brut_en_plus: str = "") -> str:
        codex_home = self.emplacements.acp_local / "codex-home"
        claude_config = self.emplacements.acp_local / "claude-config"
        base: dict[str, dict[str, Any]] = {
            "poste": {"nom": "Poste de test", "compte": compte, "compte_attendu": "acp-poste"},
            "hermes": {"origine": self.origine, "attente_max_s": 5, "delai_connexion_s": 5},
            "sondes": {"codex": True, "claude": True, "intervalle_s": 600, "delai_sonde_s": 30},
            "codex": {"executable": PYTHON, "home": str(codex_home), "version_testee": "0.156.1",
                      "modeles_permis": [], "bac_a_sable": "elevated"},
            "claude": {"executable": PYTHON, "config_dir": str(claude_config), "version_testee": "2.1.280",
                       "alias_permis": ["opus", "sonnet", "haiku", "fable"]},
            "politique": {"executants": ["codex", "claude"], "efforts_interdits": ["max", "ultra", "ultracode"],
                          "paliers_admis": ["default"], "concurrence": 1, "duree_max_carte_s": 3600,
                          "cartes_par_jour": 20, "reseau_executants": False},
            "quotas": {"hermes_meme_enveloppe_que_codex": False},
            "journal": {"niveau": "detail", "taille_max_mo": 1, "fichiers": 5},
        }
        for section, valeurs in (sections or {}).items():
            base.setdefault(section, {}).update(valeurs)
        lignes = ["# poste.toml de test (valeurs factices)", "version = 1", ""]
        for section, valeurs in base.items():
            if section in supprimer:
                continue
            lignes.append(f"[{section}]")
            for cle, valeur in valeurs.items():
                if f"{section}.{cle}" in supprimer:
                    continue
                lignes.append(f"{cle} = {self._valeur(valeur)}")
            lignes.append("")
        return "\n".join(lignes) + brut_en_plus

    @staticmethod
    def _valeur(valeur: Any) -> str:
        if isinstance(valeur, bool):
            return "true" if valeur else "false"
        if isinstance(valeur, (int, float)):
            return str(valeur)
        if isinstance(valeur, str):
            return toml_chaine(valeur)
        if isinstance(valeur, list):
            return "[" + ", ".join(Poste._valeur(v) for v in valeur) + "]"
        raise TypeError(valeur)

    def ecrire_politique(self, texte: str | None = None, **options: Any) -> Path:
        chemin = self.emplacements.politique
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte if texte is not None else self.toml(**options), encoding="utf-8")
        return chemin

    def preparer_profil_codex(self) -> Path:
        from acp_poste.sondes_codex import ecrire_config_toml

        home = self.emplacements.acp_local / "codex-home"
        ecrire_config_toml(home)
        return home

    # ------------------------------------------------------------------ faux CLI
    def lanceurs(self) -> dict[str, list[str]]:
        dossier = self.racine / "scenarios"
        dossier.mkdir(exist_ok=True)
        codex = dossier / "codex.json"
        claude = dossier / "claude.json"
        codex.write_text(json.dumps(self.scenario_codex), encoding="utf-8")
        claude.write_text(json.dumps(self.scenario_claude), encoding="utf-8")
        return {"codex": [PYTHON, "-I", FAUX_CODEX, str(codex)], "claude": [PYTHON, "-I", FAUX_CLAUDE, str(claude)]}

    def contexte(self, **options: Any):
        from acp_poste.client_hermes import OptionsClient
        from acp_poste.contexte import Contexte

        return Contexte(emplacements=self.emplacements, coffre=self.coffre,
                        options_client=self.options or OptionsClient(),
                        lanceurs=self.lanceurs(), environnement=options.pop("environnement", None),
                        compte_courant=options.pop("compte_courant", lambda: "proprietaire-de-test"),
                        version_windows=options.pop("version_windows", lambda: "10.0.19045"), **options)


@pytest.fixture
def poste(tmp_path: Path) -> Poste:
    return Poste(tmp_path / "racine")


# ------------------------------------------------------------------ faux dépôt git HTTPS (étape P7, visibilité mesurée)


def _module_faux_depot():
    import importlib.util

    spec = importlib.util.spec_from_file_location("faux_depot_https", ICI / "faux_depot_https.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def autorite_depot(tmp_path_factory):
    """Autorité de certification jetable du faux serveur git (jamais committée, détruite avec la session)."""
    return _module_faux_depot().autorite_de_test(tmp_path_factory.mktemp("autorite-depot"))


@pytest.fixture(scope="session")
def faux_depot(autorite_depot, tmp_path_factory):
    """Faux serveur git HTTPS local (``faux_depot_https.py``) : public, privé, hors de portée, pannes, délai."""
    import subprocess

    module = _module_faux_depot()
    depot = tmp_path_factory.mktemp("depot-annonce")
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "initial"]):
        if argv[0] == "add":
            (depot / "README.md").write_text("annonce\n", encoding="utf-8")
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c",
                        "commit.gpgsign=false", "-c", "init.defaultBranch=main", *argv], cwd=depot,
                       capture_output=True, check=True)
    faux = module.FauxDepotHttps(autorite_depot, module.annonce_de(depot / ".git")).demarrer()
    try:
        yield faux
    finally:
        faux.arreter()


@pytest.fixture
def avec_autorite(autorite_depot, monkeypatch):
    """Ajoute l'autorité de test aux options IMPOSÉES de git (jamais en production : le magasin du système fait foi)."""
    from acp_poste import depots as module_depots

    originale = module_depots.options_git

    def options(*args, **kwargs):
        supplement = ["-c", f"http.sslCAInfo={autorite_depot.fichier_ac.as_posix()}"]
        if os.name == "nt":
            supplement += ["-c", "http.sslBackend=openssl"]
        return originale(*args, **kwargs) + supplement

    monkeypatch.setattr(module_depots, "options_git", options)
    return autorite_depot
