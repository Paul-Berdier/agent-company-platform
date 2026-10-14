"""Sondes Claude Code du poste (cahier P5 § 10) contre un faux ``claude`` piloté par scénario (``faux_claude.py``)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from acp_poste import sondes_claude as scl
from acp_poste.catalogue_claude import DOCUMENTATION_LUE_LE, modeles_documentes
from acp_poste.politique import SectionClaude
from acp_poste.sondes_claude import environnement_claude, sonder_claude
from acp_poste.subscription_quotas import codex_environment

PYTHON = str(Path(sys.executable).resolve())
JETON_CLAUDE = "sk-ant-oat01-" + "t" * 40
JETON_MACHINE = "acpm_" + "Zq3" * 14 + "x"


def section(poste, *, ligne_etat: Path | None = None, version_testee: str = "2.1.280") -> SectionClaude:
    return SectionClaude(executable=Path(PYTHON), config_dir=poste.emplacements.acp_local / "claude-config",
                         version_testee=version_testee, alias_permis=("opus", "sonnet"), ligne_etat=ligne_etat)


async def sonder(poste, *, jeton: str | None = JETON_CLAUDE, ligne_etat=None, delai_auth: float = 20.0, **scenario):
    poste.scenario_claude = dict(scenario)
    if jeton:
        poste.coffre.ecrire("jeton-claude", jeton)
    return await sonder_claude(section(poste, ligne_etat=ligne_etat), poste.coffre, delai_s=20,
                               prefixe=poste.lanceurs()["claude"], delai_auth_s=delai_auth)


def enregistres(fichier: Path) -> list[dict]:
    return [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]


async def test_version_parse_et_plage(poste):
    resultat = await sonder(poste, version="2.1.281 (Claude Code)")
    assert resultat.version == {"lue": "2.1.281", "testee": "2.1.280", "conforme": False}
    assert resultat.releve["etat"] == "ok" and resultat.releve["origine_liste"] == "alias_documentes"
    ancien = await sonder(poste, version="2.1.247 (Claude Code)")
    assert ancien.releve["etat"] == "cli_hors_version" and ancien.releve["modeles"] == []
    illisible = await sonder(poste, version="Claude Code (version inconnue)")
    assert illisible.releve["etat"] == "indisponible" and illisible.version["lue"] is None


async def test_auth_status_source_officielle_sans_identite_publiee(poste):
    for code, connexion in ((0, "compte_claude"), (1, "jeton_absent"), (7, "inconnu")):
        resultat = await sonder(poste, code_auth=code)
        assert resultat.connexion == connexion
        texte = json.dumps(resultat.__dict__, ensure_ascii=False, default=str)
        assert "titulaire@example.com" not in texte and "secret-de-sortie" not in texte
    for statut in ({"authMethod": "api_key"}, {"authMethod": "oauth_token"}, {"apiProvider": "bedrock"}):
        resultat = await sonder(poste, statut=statut)
        assert resultat.connexion == "refuse"
    bloque = await sonder(poste, auth_bloque=True, delai_auth=1.0)
    assert bloque.connexion == "inconnu" and bloque.releve["etat"] == "indisponible"


async def test_ancien_jeton_conserve_mais_jamais_injecte(poste, tmp_path):
    fichier = tmp_path / "claude.jsonl"
    await sonder(poste, enregistrer=str(fichier))
    version, auth = enregistres(fichier)
    assert version["argv"] == ["--version"] and version["jeton"] is None
    assert auth["argv"] == ["auth", "status"] and auth["jeton"] is None
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in auth["noms"]
    assert poste.coffre.lire("jeton-claude") == JETON_CLAUDE
    assert not {n for n in auth["noms"] if n.endswith("_API_KEY") or n.startswith("ANTHROPIC_")}


async def test_disable_updates(poste, tmp_path):
    fichier = tmp_path / "claude.jsonl"
    await sonder(poste, enregistrer=str(fichier))
    for entree in enregistres(fichier):
        assert entree["disable_updates"] == "1"
        assert entree["config_dir"] == str(poste.emplacements.acp_local / "claude-config")


async def test_magasin_officiel_verifie_sans_jeton_legacy(poste, tmp_path):
    fichier = tmp_path / "claude.jsonl"
    resultat = await sonder(poste, jeton=None, enregistrer=str(fichier), code_auth=1)
    assert resultat.connexion == "jeton_absent"
    assert [e["argv"] for e in enregistres(fichier)] == [["--version"], ["auth", "status"]]


def test_catalogue_documente_hors_plage_inconnu():
    dans = {m["id"]: m for m in modeles_documentes((2, 1, 280))}
    assert dans["opus"]["resolution_documentee"] == "claude-opus-5-5"
    assert dans["opus"]["defaultReasoningEffort"] == "medium"
    assert dans["sonnet"]["supportedReasoningEfforts"] == ["low", "medium", "high", "xhigh", "max"]
    assert dans["haiku"]["supportedReasoningEfforts"] == [] and dans["haiku"]["resolution_documentee"] is None
    assert dans["best"]["supportedReasoningEfforts"] is None
    assert all(m["isDefault"] is None and m["nature"] == "alias_documente" for m in dans.values())
    hors = modeles_documentes((2, 1, 279))
    assert all(m["supportedReasoningEfforts"] is None and m["resolution_documentee"] is None
               and m["defaultReasoningEffort"] is None for m in hors)
    assert [m["id"] for m in hors] == list(dans)


async def test_releve_hors_plage_dit_inconnu(poste):
    resultat = await sonder(poste, version="2.1.260 (Claude Code)")
    assert resultat.releve["etat"] == "ok" and "hors de la plage documentée" in resultat.releve["detail"]
    assert all(m["supportedReasoningEfforts"] is None for m in resultat.releve["modeles"])


async def test_ligne_etat_des_sessions(poste, tmp_path):
    sans = await sonder(poste)
    assert sans.releve["compteurs"][0]["status"] == "unavailable"
    assert sans.releve["compteurs"][0]["detail"] == scl.LIGNE_ETAT_NON_DECLAREE
    fichier = tmp_path / "claude-code.json"
    maintenant = int(datetime.now(UTC).timestamp())
    fichier.write_text(json.dumps({"source": "claude-code-statusline", "observed_at": datetime.now(UTC).isoformat(),
                                   "windows": {"five_hour": {"used_percentage": 12, "resets_at": maintenant + 3600},
                                               "seven_day": {"used_percentage": 40, "resets_at": maintenant + 86400}}}),
                       encoding="utf-8")
    avec = await sonder(poste, ligne_etat=fichier)
    compteur = avec.releve["compteurs"][0]
    assert compteur["status"] == "ok" and [f["used_percent"] for f in compteur["windows"]] == [12, 40]


async def test_releve_conforme_au_contrat(poste):
    from acp_poste_contrat.inventaire import valider_releve

    resultat = await sonder(poste)
    releve = valider_releve(dict(resultat.releve, depots=[]))
    assert releve.documentation_lue_le == DOCUMENTATION_LUE_LE
    assert releve.modele("opus[1m]") is not None


async def test_executable_absent(poste):
    absent = SectionClaude(executable=poste.racine / "absent.exe", config_dir=poste.racine / "c",
                           version_testee="2.1.280", alias_permis=(), ligne_etat=None)
    resultat = await sonder_claude(absent, poste.coffre, delai_s=5)
    assert resultat.releve["etat"] == "cli_absente"
    assert resultat.connexion == "inconnu"


def test_jamais_dans_argv_ni_env_enfant(poste):
    """Les environnements construits pour Codex et Claude ne portent jamais le jeton machine, même quand il est dans
    l'environnement du poste. Le compte Claude vient exclusivement du magasin officiel."""
    source = {"PATH": "x", "SYSTEMROOT": "y", "ACP_JETON": JETON_MACHINE, "OPENAI_API_KEY": "sk-proj-" + "a" * 30,
              "ANTHROPIC_API_KEY": "sk-ant-" + "b" * 30, "CLAUDE_CODE_OAUTH_TOKEN": JETON_CLAUDE, "USERPROFILE": "z"}
    codex = codex_environment(poste.emplacements.acp_local / "codex-home", source=source)
    assert JETON_MACHINE not in json.dumps(codex) and "OPENAI_API_KEY" not in codex
    claude = environnement_claude(section(poste), source=source)
    assert JETON_MACHINE not in json.dumps(claude) and "ANTHROPIC_API_KEY" not in claude
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude
    assert (claude["DISABLE_UPDATES"], claude["DISABLE_AUTOUPDATER"], claude["CLAUDE_CODE_SKIP_PROMPT_HISTORY"]) == \
        ("1", "1", "1")


async def test_arret_non_confirme_signale_au_service(poste, monkeypatch):
    from acp_poste.app_server import ArretNonConfirme
    async def survivant(*args, **kwargs):
        raise ArretNonConfirme
    monkeypatch.setattr(scl, "lire_etat_claude", survivant)
    resultat = await sonder(poste)
    assert resultat.arret_confirme is False
    assert resultat.connexion == "inconnu" and resultat.releve["etat"] == "indisponible"
    assert "arret_confirme" not in resultat.releve
