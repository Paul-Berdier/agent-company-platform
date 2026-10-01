"""Fichiers de pilotage (cahier P6 § 6.6, point 2 ; D90) et balayage des secrets (point 3), scénario E3 compris."""

from __future__ import annotations

import json

import pytest

from acp_poste.balayage import RAISON_SECRET, jetons_de_auth_json, secret_dans, valeurs_exactes
from acp_poste.depots import Changement
from acp_poste.pilotage import chemins_de_pilotage, composants, est_pilotage


def _c(statut: str, *chemins: str, avant: str = "100644", apres: str = "100644") -> Changement:
    return Changement(statut=statut, mode_avant=avant, mode_apres=apres, chemins=chemins)


@pytest.mark.parametrize("chemin", [
    "CLAUDE.md", "AGENTS.md", "sous/AGENTS.md", "a/b/claude.md", "CLAUDE.md.", "CLAUDE.md ", "Claude.MD",
    ".claude/settings.json", ".claude", "x/.codex/config.toml", ".agents/regles.md", ".github/workflows/ci.yml",
    ".GitHub/Workflows/x.yml", ".github/actions/a/action.yml", "hermes/gere/projet.toml", "sous\\.husky\\pre-commit",
    ".gitmodules", ".gitattributes", "lib/.gitattributes", ".pre-commit-config.yaml", ".devcontainer/devcontainer.json",
    ".vscode/settings.json", ".mcp.json", ".npmrc", "web/.npmrc", ".envrc",
    # Relecture de P6 : instructions lues par les CLI de l'image (Codex 0.156.1, Claude Code 2.1.283).
    "AGENTS.override.md", "sous/AGENTS.override.md", "Agents.Override.MD.", "CLAUDE.local.md", "a/b/claude.LOCAL.md",
    "CLAUDÉ.md".replace("CLAUDÉ", "CLAUDE"),
])
def test_chemins_vises_a_toute_profondeur(chemin):
    assert est_pilotage(chemin), chemin


@pytest.mark.parametrize("chemin", [
    "README.md", "src/claude.py", "docs/agents.md.txt", "github/workflows.md", "hermes/gerer/x", "gere/hermes/x",
    "src/vscode.py", "notes/CLAUDE.md.bak",
])
def test_chemins_ordinaires(chemin):
    assert not est_pilotage(chemin), chemin


def test_normalisation_unicode_et_points():
    assert composants("Dossier\\Sous/ CLAUDE.MD. ") == ["dossier", "sous", "claude.md"]
    # « é » composé (NFD) et précomposé (NFC) : même composant.
    assert composants("éte/x") == composants("éte/x")


def test_supplementaire_de_la_politique():
    assert est_pilotage("config/secrets.yml", ["config/secrets.yml"])
    assert est_pilotage("Infra/Terraform/main.tf", ["infra/terraform"])
    assert not est_pilotage("infra/autre.tf", ["infra/terraform"])


def test_scenario_e3_revue():
    changements = [
        _c("A", ".GitHub/Workflows/x.yml"),
        _c("A", "sous/AGENTS.md"),
        _c("M", "CLAUDE.md."),
        _c("R", "docs/notes.md", ".claude/notes.md"),
        _c("M", "src/app.py"),
    ]
    assert chemins_de_pilotage(changements) == [".GitHub/Workflows/x.yml", "sous/AGENTS.md", "CLAUDE.md.",
                                                ".claude/notes.md"]


def test_suppression_renommage_lien_et_sous_module():
    assert chemins_de_pilotage([_c("D", "AGENTS.md", apres="000000")]) == ["AGENTS.md"]
    # Renommage HORS d'un fichier de pilotage : l'ancien chemin compte.
    assert chemins_de_pilotage([_c("R", "CLAUDE.md", "docs/vieux.md")]) == ["CLAUDE.md"]
    assert chemins_de_pilotage([_c("A", "lien", avant="000000", apres="120000")]) == ["lien"]
    assert chemins_de_pilotage([_c("A", "vendor/x", avant="000000", apres="160000")]) == ["vendor/x"]
    assert chemins_de_pilotage([_c("D", "ancien-lien", avant="120000", apres="000000")]) == []
    assert chemins_de_pilotage([_c("M", "src/a.py"), _c("A", "README.md")]) == []


def test_limite_du_contrat():
    changements = [_c("A", f"d{i}/AGENTS.md") for i in range(80)]
    assert len(chemins_de_pilotage(changements)) == 50


# ------------------------------------------------------------------ balayage


class _Coffre:
    def __init__(self, valeurs):
        self.valeurs = valeurs

    def lire(self, usage):
        return self.valeurs.get(usage)


def test_valeurs_exactes_du_coffre_et_de_auth_json(tmp_path):
    (tmp_path / "auth.json").write_text(json.dumps({
        "auth_mode": "chatgpt", "OPENAI_API_KEY": None,
        "tokens": {"access_token": "acces-factice-" + "a" * 30, "refresh_token": "rafraichi-" + "r" * 30,
                   "id_token": "identite-" + "i" * 30, "account_id": "compte-court"},
        "last_refresh": "2026-10-01T10:00:00Z"}), encoding="utf-8")
    valeurs = valeurs_exactes(_Coffre({"jeton-machine": "acpm_" + "m" * 43, "jeton-claude": "court"}), tmp_path)
    assert set(valeurs) == {"jeton-machine", "codex:access_token", "codex:refresh_token", "codex:id_token"}
    assert jetons_de_auth_json(tmp_path / "absent.json") == {}


def test_secret_valeur_exacte_puis_motifs_sans_jamais_la_valeur():
    valeurs = {"jeton-claude": "valeur-opaque-du-coffre-1234"}
    trouve = secret_dans(["rien", "ligne avec valeur-opaque-du-coffre-1234 dedans"], valeurs)
    assert trouve == "valeur exacte : jeton-claude" and "1234" not in trouve
    assert secret_dans(["CLE = 'sk-ant-api03-" + "x" * 30 + "'"], {}) == "clé d'API Anthropic"
    assert secret_dans(["token: ghp_" + "a" * 36], {}) == "jeton GitHub"
    assert secret_dans(["print('bonjour')", None, ""], valeurs) is None
    assert "rien n'a été envoyé" in RAISON_SECRET and len(RAISON_SECRET) <= 500
