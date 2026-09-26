"""Adaptateur Hermes du noyau d'acp-poste contre le kanban de Hermes à la version épinglée (étape P4)."""

from __future__ import annotations

from pathlib import Path

GREFFON = Path("/opt/hermes/plugins/acp-poste")
TEMOIN = Path("/opt/acp-tests/outils/temoin_compat")


def test_chaque_fonction_vient_de_son_module_de_definition(noyau):
    ka = noyau.ka
    for nom, module_attendu in ka.MODULES_DE_DEFINITION.items():
        objet = getattr(ka, nom)
        assert objet.__module__ == module_attendu, (nom, objet.__module__)
    # Les deux pointeurs de compatibilité connus ne sont pas empruntés.
    assert ka.connect.__module__ == "hermes_cli.kanban_db_connect"
    assert ka.heartbeat_worker.__module__ == "hermes_cli.kanban_db_dispatch"
    # La liste couvre tout ce que le cahier P4 § 5 exige.
    assert {"create_board", "list_boards", "create_task", "link_tasks", "schedule_task", "unblock_task",
            "specify_triage_task", "block_task", "claim_task", "complete_task", "write_txn", "owned_kanban_task",
            "engage", "disengage", "get_state", "plugin_db", "redact_sensitive_text"} <= set(ka.MODULES_DE_DEFINITION)
    from hermes_constants import VALID_REASONING_EFFORTS

    assert ka.VALID_REASONING_EFFORTS is VALID_REASONING_EFFORTS


def test_seul_l_adaptateur_importe_hermes_dans_le_noyau():
    """Aucun autre module du noyau n'importe Hermes (ni hermes_cli, ni agent, ni tools, ni plugins…)."""
    import ast

    interdits = ("hermes_cli", "agent", "tools", "plugins", "hermes_constants", "gateway", "tui_gateway", "run_agent",
                 "model_tools", "cron")
    fautifs = []
    for fichier in sorted((GREFFON / "noyau").glob("*.py")):
        if fichier.name == "kanban_adapter.py":
            continue
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            noms = []
            if isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                noms = [noeud.module]
            fautifs += [f"{fichier.name}: {n}" for n in noms if n.split(".")[0] in interdits]
    assert fautifs == []


def test_le_scan_de_compatibilite_de_hermes_ne_trouve_rien_dans_le_greffon():
    from hermes_cli.plugin_compat import scan_plugin

    assert (GREFFON / "noyau" / "kanban_adapter.py").is_file()
    assert scan_plugin(GREFFON) == []


def test_le_scan_de_compatibilite_repere_le_greffon_temoin():
    from hermes_cli.plugin_compat import scan_plugin

    impacts = scan_plugin(TEMOIN)
    assert [h.old for h in impacts] == ["hermes_cli.kanban_db.connect"]
    assert impacts[0].new == "hermes_cli.kanban_db_connect.connect"


def test_schema_des_evenements_attendu(noyau):
    """La seule lecture SQL directe du greffon (task_events après un identifiant) suppose ce schéma."""
    noyau.ka.create_board("acp-schema-evenements", name="Schéma")
    with noyau.ka.connexion("acp-schema-evenements") as kc:
        colonnes = [l[1] for l in kc.execute("PRAGMA table_info(task_events)")]
        assert colonnes == ["id", "task_id", "run_id", "kind", "payload", "created_at"]
        assert noyau.ka.dernier_evenement(kc) == 0
        tache = noyau.ka.create_task(kc, title="Carte", assignee="default", created_by="test")
        evenements = noyau.ka.evenements_apres(kc, 0)
        assert [e[1:3] for e in evenements] == [(tache, "created")]
        assert noyau.ka.dernier_evenement(kc) == evenements[-1][0]
        assert noyau.ka.evenements_apres(kc, evenements[-1][0]) == []


def test_plus_de_tableau_poste_ni_de_poste_windows(noyau):
    ka = noyau.ka
    for ancien in ("TABLEAU", "ASSIGNE", "assurer_tableau", "creer_carte_triage"):
        assert not hasattr(ka, ancien), ancien
    assert not (GREFFON / "kanban_adapter.py").exists()
    for fichier in GREFFON.rglob("*.py"):
        if "tests" in fichier.parts:  # le contrat REFUSE « poste-windows » : ses tests le citent
            continue
        assert '"poste-windows"' not in fichier.read_text(encoding="utf-8"), fichier
    assert ka.VOIES_POSTE == ("poste-codex", "poste-claude") and ka.CREATEUR == "acp-poste"


def test_effort_hermes_et_voies(noyau):
    ka = noyau.ka
    assert ka.effort_hermes("high") == "high" and ka.effort_hermes("none") == "none"
    assert ka.effort_hermes("extreme") is None and ka.effort_hermes("") is None
    assert ka.est_voie_poste("poste-codex") and ka.est_voie_poste("poste-inconnu") and not ka.est_voie_poste("default")


def test_connexion_rejoue_la_seule_course_du_controle_d_ecriture(noyau, monkeypatch, tmp_path):
    """Course de Hermes 0.21.5 (hermes_state_repair.py:537-573) : le -wal d'un tableau disparaît entre is_file() et
    os.access() ; le faux « read-only » est rejoué. Un -wal VRAIMENT présent et illisible lève tout de suite, et la
    course répétée au-delà des tentatives finit par lever : rien n'est masqué."""
    import sqlite3

    import pytest

    ka = noyau.ka
    vrai_connect = ka.connect
    disparu = tmp_path / "boards" / "acp-x" / "kanban.db-wal"
    present = tmp_path / "present-kanban.db-wal"
    present.write_text("", encoding="utf-8")

    def refus(chemin):
        return sqlite3.OperationalError(
            f"kanban.db (kanban.db) is not writable: file {chemin} is read-only for this user. Hermes needs "
            "read-write access to open the database.")

    appels = []

    def une_course_puis_ok(board=None):
        appels.append(board)
        if len(appels) == 1:
            raise refus(disparu)
        return vrai_connect(board=board)

    monkeypatch.setattr(ka, "connect", une_course_puis_ok)
    ka.create_board("acp-course-wal", name="Course")
    with ka.connexion("acp-course-wal") as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    assert appels == ["acp-course-wal", "acp-course-wal"]

    def toujours(exc):
        def connect(board=None):
            appels.append(board)
            raise exc
        return connect

    appels.clear()
    monkeypatch.setattr(ka, "connect", toujours(refus(present)))
    with pytest.raises(sqlite3.OperationalError):
        with ka.connexion("acp-course-wal"):
            pass
    assert len(appels) == 1  # vraiment illisible : aucune nouvelle tentative
    appels.clear()
    monkeypatch.setattr(ka, "connect", toujours(refus(disparu)))
    with pytest.raises(sqlite3.OperationalError):
        with ka.connexion("acp-course-wal"):
            pass
    assert len(appels) == ka.TENTATIVES_DE_CONNEXION
    assert not ka.course_du_wal(sqlite3.OperationalError("database is locked"))

