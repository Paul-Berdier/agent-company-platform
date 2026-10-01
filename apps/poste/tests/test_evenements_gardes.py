"""Flux des agents, sortie structurée, commandes imposées (cahier P6 § 6.3) et gardes de quota et de budget (§ 6.1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest

from acp_poste.commandes_agents import FONCTIONS_CODEX_COUPEES, commande_claude, commande_codex, schema_json
from acp_poste.evenements import (
    SCHEMA_SORTIE,
    SortieInvalide,
    lire_flux_claude,
    lire_flux_codex,
    sortie_claude,
    valider_sortie,
)
from acp_poste.garde_quota import Budget, QuotasClaude, codex_ouverte
from acp_poste_contrat.quotas import SubscriptionQuotaReport

MAINTENANT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


# ------------------------------------------------------------------ flux Codex


def test_flux_codex_session_jetons_et_message():
    lignes = [
        b'{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
        b'{"type":"turn.started"}',
        b'{"type":"item.completed","item":{"id":"i1","type":"command_execution","command":"ls"}}',
        b'{"type":"item.completed","item":{"id":"i2","type":"agent_message","text":"{\\"issue\\":\\"termine\\"}"}}',
        b'{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":7,'
        b'"reasoning_output_tokens":0}}',
        b"pas du json",
        b'{"type":"turn.completed","usage":{"input_tokens":5,"cached_input_tokens":0,"output_tokens":1}}',
    ]
    flux = lire_flux_codex(lignes)
    assert flux.session == "0199a213-81c0-7800-8aa1-bbab2a035a53"
    assert flux.jetons == {"entree": 105, "sortie": 8, "cache": 40}
    assert flux.dernier_message == '{"issue":"termine"}' and flux.commandes == 1 and flux.tours_termines == 2
    assert flux.erreur is None and not flux.limite_atteinte


def test_flux_codex_limite_atteinte():
    flux = lire_flux_codex(['{"type":"turn.failed","error":{"message":"You\'ve hit your usage limit."}}'])
    assert flux.limite_atteinte and "usage limit" in flux.erreur
    assert lire_flux_codex(['{"type":"error","message":"stream disconnected"}']).limite_atteinte is False
    assert lire_flux_codex([]).jetons == {"entree": None, "sortie": None, "cache": None}


# ------------------------------------------------------------------ flux Claude


def test_flux_claude_init_limites_et_resultat():
    lignes = [
        json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-5", "session_id": "s-1",
                    "tools": ["Read", "Glob", "Grep", "Edit", "Write"]}),
        json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning",
                                                                    "resetsAt": 1790000000, "utilization": 0.82,
                                                                    "rateLimitType": "five_hour"}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
                    "result": "fini", "structured_output": {"issue": "termine", "resume": "Fait."},
                    "usage": {"input_tokens": 10, "output_tokens": 3, "cache_read_input_tokens": 50,
                              "cache_creation_input_tokens": 5}}),
    ]
    flux = lire_flux_claude(lignes, maintenant=MAINTENANT)
    assert (flux.modele_servi, flux.session) == ("claude-sonnet-5", "s-1")
    assert flux.outils_interdits == [] and flux.jetons == {"entree": 10, "sortie": 3, "cache": 55}
    assert flux.limite.statut == "allowed_warning" and flux.limite.fenetre == "five_hour"
    assert flux.limite.utilisation == 0.82 and flux.limite.remise == datetime.fromtimestamp(1790000000, tz=UTC)
    assert sortie_claude(flux) == {"issue": "termine", "resume": "Fait."} and not flux.limite_atteinte


def test_flux_claude_rejet_outils_interdits_et_erreur():
    flux = lire_flux_claude([
        json.dumps({"type": "system", "subtype": "init", "model": "x", "tools": ["Read", "Bash", "mcp__x__y"]}),
        json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1790000000}}),
        json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                    "errors": ["API Error: 429"], "api_error_status": 429}),
    ], maintenant=MAINTENANT)
    assert flux.outils_interdits == ["Bash", "mcp__x__y"]
    assert flux.limite_atteinte and flux.limite.fenetre is None and flux.erreur == "API Error: 429"


# ------------------------------------------------------------------ sortie structurée


def test_sortie_valide_et_refus():
    assert valider_sortie('{"issue":"termine","resume":"Fait.","question":null,"verdict":null,'
                          '"corrections":null}', relecture=False).resume == "Fait."
    question = valider_sortie({"issue": "question", "resume": "Bloqué.", "question": "Quelle base ?"},
                              relecture=False)
    assert question.question == "Quelle base ?"
    relue = valider_sortie({"issue": "termine", "resume": "Relu.", "verdict": "corrections",
                            "corrections": "Ajouter un test."}, relecture=True)
    assert relue.verdict == "corrections" and relue.corrections == "Ajouter un test."
    # Verdict hors relecture : ignoré.
    assert valider_sortie({"issue": "termine", "resume": "x", "verdict": "accepte"}, relecture=False).verdict is None
    for mauvais, motif, relecture in (
            ({"issue": "fini", "resume": "x"}, "issue", False),
            ({"issue": "termine", "resume": " "}, "vide", False),
            ({"issue": "question", "resume": "x"}, "question", False),
            ("pas du json", "illisible", False),
            ({"issue": "termine", "resume": "x"}, "verdict absent", True),
            ({"issue": "termine", "resume": "x", "verdict": "corrections"}, "consigne", True)):
        with pytest.raises(SortieInvalide, match=motif):
            valider_sortie(mauvais, relecture=relecture)
    long = valider_sortie({"issue": "termine", "resume": "a" * 5000}, relecture=False).resume
    assert len(long) <= 4000 and long.endswith("[tronqué]")


def test_schema_impose_strict():
    assert SCHEMA_SORTIE["additionalProperties"] is False
    assert set(SCHEMA_SORTIE["required"]) == set(SCHEMA_SORTIE["properties"])
    assert json.loads(schema_json()) == SCHEMA_SORTIE


# ------------------------------------------------------------------ commandes imposées


def test_commande_codex_ecriture_puis_reprise():
    base = dict(prefixe=["/usr/bin/setpriv", "--reuid=10001", "--"], executable="/opt/acp/outils/codex/codex",
                worktree=Path("/donnees/espaces/jetable/t_abcd"), modele="gpt-test", effort="medium",
                role="implementation", schema=Path("/tmp/acp/t_abcd/schema.json"),
                reponse=Path("/tmp/acp/t_abcd/reponse.json"), codex_home=Path("/donnees/codex"),
                home=PurePosixPath("/home/acp-codex"), tmpdir=Path("/tmp/acp/t_abcd/codex"))
    commande = commande_codex(**base)
    argv = commande.argv
    assert argv[:5] == ["/usr/bin/setpriv", "--reuid=10001", "--", "/opt/acp/outils/codex/codex", "exec"]
    for attendu in ("--json", "--ignore-user-config", "--ignore-rules", 'service_tier="default"',
                    'cli_auth_credentials_store="file"', "sandbox_workspace_write.network_access=false",
                    'web_search="disabled"', 'model_reasoning_effort="medium"'):
        assert attendu in argv
    assert argv[argv.index("--sandbox") + 1] == "workspace-write" and argv[-1] == "-"
    assert "--ephemeral" not in argv and "resume" not in argv
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--disable"] == list(FONCTIONS_CODEX_COUPEES)
    assert commande.env == {"HOME": "/home/acp-codex", "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                            "LC_ALL": "C.UTF-8", "TMPDIR": "/tmp/acp/t_abcd/codex", "CODEX_HOME": "/donnees/codex"}
    reprise = commande_codex(**{**base, "session": "0199-session", "role": "relecture"}).argv
    assert reprise[-3:] == ["resume", "0199-session", "-"]
    assert reprise[reprise.index("--sandbox") + 1] == "read-only"


def test_commande_claude_sans_bare_ni_historique():
    commande = commande_claude(prefixe=["setpriv"], executable="/opt/acp/outils/claude/claude", modele="sonnet",
                               effort="high", role="implementation", lecture=Path("/tmp/acp/t_abcd/lecture"),
                               config_dir=Path("/donnees/claude"), jeton="sk-ant-oat01-factice",
                               home=PurePosixPath("/home/acp-claude"), tmpdir=Path("/tmp/acp/t_abcd/claude"))
    argv = commande.argv
    assert argv[1:4] == ["/opt/acp/outils/claude/claude", "-p", "--restricted"]
    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep,Edit,Write"
    for attendu in ("--strict-mcp-config", "mcp__*", "acceptEdits", "none", "/etc/acp/claude-settings.json",
                    "stream-json", "--verbose", "--json-schema"):
        assert attendu in argv
    assert "--bare" not in argv and "--fallback-model" not in argv and "--resume" not in argv
    assert not any("sk-ant" in a for a in argv)
    assert commande.env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-factice"
    assert "CLAUDE_CODE_SKIP_PROMPT_HISTORY" not in commande.env
    assert commande.env["DISABLE_UPDATES"] == commande.env["DISABLE_TELEMETRY"] == "1"
    lecture = commande_claude(prefixe=[], executable="claude", modele="opus", effort=None, role="relecture",
                              lecture=Path("/l"), config_dir=Path("/c"), jeton="j", home="/h", tmpdir=Path("/t"),
                              session="s-1").argv
    assert lecture[lecture.index("--tools") + 1] == "Read,Glob,Grep" and lecture[-2:] == ["--resume", "s-1"]
    assert "--effort" not in lecture


# ------------------------------------------------------------------ gardes


def test_garde_codex_a_90_pourcent():
    assert codex_ouverte(None) == (True, None)
    releve = [{"status": "ok", "windows": [{"used_percent": 41}, {"used_percent": 89.9}]}]
    assert codex_ouverte(releve)[0] is True
    releve[0]["windows"][1]["used_percent"] = 90
    ouverte, raison = codex_ouverte(releve)
    assert ouverte is False and "90 %" in raison
    assert codex_ouverte([{"status": "ok", "windows": [], "limit_reached": True}])[0] is False
    assert codex_ouverte([{"status": "unavailable", "windows": [{"used_percent": 99}]}])[0] is True


def test_garde_claude_et_releve_publie(tmp_path):
    from acp_poste.evenements import LimiteClaude

    quotas = QuotasClaude(tmp_path / "quotas-claude.json")
    assert quotas.ouverte(MAINTENANT) == (True, None, None)
    inconnu = quotas.releve()
    assert inconnu.status == "unavailable" and "garde inopérante" in inconnu.detail
    remise = MAINTENANT + timedelta(hours=2)
    quotas.noter(LimiteClaude("allowed_warning", remise, 0.93, "five_hour", MAINTENANT))
    ouverte, raison, quand = quotas.ouverte(MAINTENANT)
    assert ouverte is False and "93 %" in raison and quand == remise
    assert quotas.ouverte(remise + timedelta(seconds=1))[0] is True
    releve = quotas.releve()
    assert isinstance(releve, SubscriptionQuotaReport) and releve.source == "claude_code_rate_limit_event"
    assert releve.windows[0].key == "five_hour" and releve.windows[0].used_percent == 93.0
    assert releve.limit_reached is False
    quotas.noter(LimiteClaude("rejected", None, None, None, MAINTENANT))
    assert quotas.ouverte(MAINTENANT)[0] is False
    assert quotas.releve().windows[0].key == "sans_type" and quotas.releve().limit_reached is True


def test_budget_du_jour(tmp_path):
    budget = Budget(tmp_path / "compteurs.json", cartes_par_jour=2, heures_par_jour=1)
    assert budget.ouvert(MAINTENANT) == (True, None)
    budget.compter(carte=True, secondes=1200, maintenant=MAINTENANT)
    budget.compter(carte=True, secondes=600, maintenant=MAINTENANT)
    ouvert, raison = budget.ouvert(MAINTENANT)
    assert ouvert is False and "2 cartes" in raison
    budget = Budget(tmp_path / "compteurs.json", cartes_par_jour=20, heures_par_jour=1)
    budget.compter(secondes=1800, maintenant=MAINTENANT)
    assert budget.ouvert(MAINTENANT)[0] is False and "1 h" in budget.ouvert(MAINTENANT)[1]
    assert budget.ouvert(MAINTENANT + timedelta(days=1)) == (True, None)
