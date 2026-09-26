"""Base propre du greffon acp-poste (étape P4) : ``<HERMES_HOME>/plugin-data/acp-poste/data.db``.

Ouverte par ``plugins.plugin_storage.plugin_db`` de Hermes (plugins/plugin_storage.py:27-47 : WAL,
``check_same_thread=False``), elle suit ``HERMES_HOME`` : ``/opt/data`` sur Railway (le volume,
donc les sauvegardes), un répertoire jetable dans les tests. La passerelle, le tableau de bord et
les workers kanban (profil ``default``, même ``HERMES_HOME``) partagent le même fichier ; aucun état
en mémoire ne porte la correction, tout est en base.

Chaque écriture se fait sous une transaction ``BEGIN IMMEDIATE`` (:func:`transaction`) : un seul
écrivain à la fois, attente bornée par ``busy_timeout`` (5 s). L'agent ne peut pas lire ce fichier :
il n'a aucun outil de fichiers sur Railway.

Schéma v1 : les cinq tables du plan (projets, demandes, questions, présence, curseurs) et huit tables
techniques (tours, notifications, releves, routage, surcharges, reglages, journal, emetteur).
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

from . import kanban_adapter as ka

NOM_GREFFON = "acp-poste"
VERSION_SCHEMA = "1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_schema (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projets (
  id               TEXT PRIMARY KEY,
  tableau          TEXT NOT NULL UNIQUE,
  titre            TEXT NOT NULL CHECK (length(titre) BETWEEN 1 AND 120),
  objectif         TEXT NOT NULL CHECK (length(objectif) BETWEEN 1 AND 4000),
  profil           TEXT NOT NULL CHECK (profil IN ('base','web','recherche','donnees')),
  depot_alias      TEXT,
  reponses         TEXT NOT NULL CHECK (reponses IN ('hermes_d_abord','proprietaire')),
  etat             TEXT NOT NULL CHECK (etat IN ('creation','actif','en_pause','termine','abandonne')),
  tour             INTEGER NOT NULL DEFAULT 0,
  plafond_tours    INTEGER NOT NULL,
  plafond_cartes   INTEGER NOT NULL,
  plafond_corrections INTEGER NOT NULL,
  cartes_creees    INTEGER NOT NULL DEFAULT 0,
  origine          TEXT NOT NULL CHECK (origine IN ('tableau_de_bord','discussion')),
  auteur           TEXT NOT NULL,
  cle_idempotence  TEXT UNIQUE,
  cree_le INTEGER NOT NULL, maj_le INTEGER NOT NULL, termine_le INTEGER
);
CREATE TABLE IF NOT EXISTS releves (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  voie TEXT NOT NULL CHECK (voie IN ('poste-codex','poste-claude')),
  source TEXT NOT NULL CHECK (source IN ('poste','releve_factice')),
  version_cli TEXT, releve_le INTEGER NOT NULL, recu_le INTEGER NOT NULL,
  contenu TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tours (
  projet_id TEXT NOT NULL REFERENCES projets(id), tour INTEGER NOT NULL,
  carte_origine TEXT NOT NULL,
  empreinte_plan TEXT NOT NULL,
  resume TEXT NOT NULL, decisions TEXT NOT NULL,
  carte_synthese TEXT, cree_le INTEGER NOT NULL,
  PRIMARY KEY (projet_id, tour)
);
CREATE TABLE IF NOT EXISTS demandes (
  cle        TEXT PRIMARY KEY,
  projet_id  TEXT NOT NULL REFERENCES projets(id),
  tableau    TEXT NOT NULL,
  carte      TEXT,
  role       TEXT NOT NULL CHECK (role IN ('exploration','planification','implementation','relecture',
                                           'correction','hermes','synthese','repondre','triage')),
  classe     TEXT NOT NULL,
  voie       TEXT NOT NULL CHECK (voie IN ('poste-codex','poste-claude','hermes')),
  tour       INTEGER NOT NULL, ref TEXT, titre TEXT NOT NULL DEFAULT '',
  modele TEXT, effort TEXT, palier TEXT,
  modele_carte TEXT, effort_carte TEXT,
  source_routage TEXT NOT NULL CHECK (source_routage IN ('surcharge_carte','surcharge_projet',
                  'surcharge_globale','choix_explicite','table','profil','sans_objet')),
  releve_id  INTEGER REFERENCES releves(id),
  depot_alias TEXT, consigne TEXT NOT NULL,
  carte_relue TEXT, correction_n INTEGER NOT NULL DEFAULT 0,
  modele_servi TEXT, palier_servi TEXT, observe_le INTEGER,
  mention TEXT,
  -- Ajouts : ce qu'il faut pour (re)créer la carte à l'identique (réparation d'une création interrompue).
  parents TEXT NOT NULL DEFAULT '[]', competences TEXT, priorite INTEGER NOT NULL DEFAULT 0,
  duree_max INTEGER, triage INTEGER NOT NULL DEFAULT 0, corps TEXT NOT NULL DEFAULT '',
  cree_le INTEGER NOT NULL,
  UNIQUE (tableau, carte)
);
CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY,
  projet_id TEXT NOT NULL REFERENCES projets(id),
  tableau TEXT NOT NULL, carte TEXT NOT NULL, run_id INTEGER,
  texte TEXT NOT NULL CHECK (length(texte) BETWEEN 1 AND 4000), contexte TEXT,
  etat TEXT NOT NULL CHECK (etat IN ('ouverte','escaladee','repondue','annulee')),
  carte_repondre TEXT,
  reponse TEXT, repondu_par TEXT CHECK (repondu_par IN ('hermes','proprietaire')),
  fondement TEXT, motif_escalade TEXT,
  cree_le INTEGER NOT NULL, maj_le INTEGER NOT NULL, repondue_le INTEGER,
  UNIQUE (tableau, carte, run_id)
);
CREATE TABLE IF NOT EXISTS presence (
  machine_id TEXT PRIMARY KEY CHECK (length(machine_id) BETWEEN 1 AND 64),
  derniere_vue INTEGER NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('longpoll','battement','simule')),
  passage INTEGER NOT NULL DEFAULT 0,
  hors_ligne_depuis INTEGER, hors_ligne_notifie INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS curseurs (tableau TEXT PRIMARY KEY, evenement INTEGER NOT NULL, maj_le INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cle TEXT NOT NULL UNIQUE,
  genre TEXT NOT NULL CHECK (genre IN ('question','bloquee','triage','abandon','termine','hors_ligne',
                                       'plafond','test','crochets')),
  projet_id TEXT, texte TEXT NOT NULL CHECK (length(texte) <= 500), lien TEXT,
  etat TEXT NOT NULL CHECK (etat IN ('en_attente','envoyee','desactivee','echec')),
  tentatives INTEGER NOT NULL DEFAULT 0, prochaine_tentative INTEGER, derniere_erreur TEXT,
  cree_le INTEGER NOT NULL, envoyee_le INTEGER
);
CREATE TABLE IF NOT EXISTS routage (classe TEXT PRIMARY KEY, entrees TEXT NOT NULL, valide_le INTEGER,
  valide_par TEXT, source TEXT NOT NULL CHECK (source IN ('proprietaire','releve_factice')));
CREATE TABLE IF NOT EXISTS surcharges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  portee TEXT NOT NULL CHECK (portee IN ('globale','projet','carte')), cible TEXT, classe TEXT NOT NULL,
  voie TEXT NOT NULL, modele TEXT, effort TEXT, palier TEXT, motif TEXT NOT NULL,
  auteur TEXT NOT NULL, cree_le INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS reglages (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL, maj_le INTEGER NOT NULL,
  auteur TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY AUTOINCREMENT, quand INTEGER NOT NULL,
  acteur TEXT NOT NULL, action TEXT NOT NULL, projet_id TEXT, cible TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS emetteur (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL, maj_le INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS demandes_par_projet ON demandes (projet_id, tour);
CREATE INDEX IF NOT EXISTS questions_par_etat ON questions (etat);
CREATE INDEX IF NOT EXISTS notifications_par_etat ON notifications (etat, prochaine_tentative);
CREATE INDEX IF NOT EXISTS journal_par_projet ON journal (projet_id, id);
"""

TABLES = ("meta_schema", "projets", "releves", "tours", "demandes", "questions", "presence", "curseurs",
          "notifications", "routage", "surcharges", "reglages", "journal", "emetteur")

# Réglages par défaut (table ``reglages``) : lus à chaque usage, modifiables par le propriétaire
# (P5, P7) ; les tests les posent par la même fonction (:func:`poser_reglage`).
REGLAGES_PAR_DEFAUT: Dict[str, Any] = {
    "plafond_tours": 3,
    "plafond_cartes": 30,
    "plafond_corrections": 2,
    "projets_actifs_max": 3,
    "lancements_discussion_par_jour": 5,
    "etapes_par_appel_max": 12,
    "seuil_hors_ligne_s": 180,
    "emetteur_intervalle_s": 15,
    "pause_reclamations": 0,
    "releve_perime_s": 7200,
    "seuil_quota_pct": 90,
    "efforts_interdits": ["max", "ultra", "ultracode"],
    "paliers_admis": ["default"],
}
PLANCHER_EMETTEUR_S = 5

_horloge: Callable[[], float] = time.time
_initialisees: set = set()
_verrou_init = threading.Lock()


def maintenant() -> int:
    """Instant courant en secondes (remplaçable dans les tests par :func:`fixer_horloge`)."""
    return int(_horloge())


def fixer_horloge(horloge: Optional[Callable[[], float]]) -> None:
    global _horloge
    _horloge = horloge or time.time


def chemin_base() -> Path:
    return Path(ka.get_hermes_home()) / "plugin-data" / NOM_GREFFON / "data.db"


def ouvrir() -> sqlite3.Connection:
    """Connexion à la base du greffon, schéma à jour. L'appelant la referme (:func:`connexion`)."""
    conn = ka.plugin_db(NOM_GREFFON)
    try:
        conn.isolation_level = None  # transactions explicites seulement (BEGIN IMMEDIATE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        cle = str(chemin_base())
        if cle not in _initialisees:
            with _verrou_init:
                if cle not in _initialisees:
                    migrer(conn)
                    _initialisees.add(cle)
    except BaseException:
        conn.close()
        raise
    return conn


@contextlib.contextmanager
def connexion() -> Iterator[sqlite3.Connection]:
    conn = ouvrir()
    try:
        yield conn
    finally:
        with contextlib.suppress(Exception):
            conn.close()


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transaction ``BEGIN IMMEDIATE`` : validée à la sortie, annulée sur exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrer(conn: sqlite3.Connection) -> None:
    """Schéma v1, idempotent (``IF NOT EXISTS``), version dans ``meta_schema``."""
    with transaction(conn):
        for instruction in SCHEMA.split(";"):
            if instruction.strip():
                conn.execute(instruction)
        conn.execute("INSERT OR IGNORE INTO meta_schema (cle, valeur) VALUES ('version', ?)", (VERSION_SCHEMA,))


def version_schema(conn: sqlite3.Connection) -> Optional[str]:
    ligne = conn.execute("SELECT valeur FROM meta_schema WHERE cle = 'version'").fetchone()
    return str(ligne[0]) if ligne else None


def reglage(conn: sqlite3.Connection, cle: str) -> Any:
    """Valeur d'un réglage (JSON en base), sinon le défaut ; une valeur illisible vaut le défaut."""
    ligne = conn.execute("SELECT valeur FROM reglages WHERE cle = ?", (cle,)).fetchone()
    if ligne is not None:
        try:
            return json.loads(ligne[0])
        except ValueError:
            pass
    return REGLAGES_PAR_DEFAUT.get(cle)


def poser_reglage(conn: sqlite3.Connection, cle: str, valeur: Any, auteur: str) -> None:
    if cle not in REGLAGES_PAR_DEFAUT:
        raise ValueError(f"réglage inconnu : {cle}")
    with transaction(conn):
        conn.execute("INSERT INTO reglages (cle, valeur, maj_le, auteur) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, maj_le = excluded.maj_le, "
                     "auteur = excluded.auteur", (cle, json.dumps(valeur), maintenant(), auteur))
        journaliser(conn, auteur, "reglage", cible=cle, detail=json.dumps(valeur))


def journaliser(conn: sqlite3.Connection, acteur: str, action: str, *, projet_id: Optional[str] = None,
                cible: Optional[str] = None, detail: Any = None) -> None:
    """Ligne du journal (à appeler DANS une transaction). Le détail est masqué et borné."""
    texte = detail if isinstance(detail, str) or detail is None else json.dumps(detail, ensure_ascii=False)
    if texte is not None:
        texte = ka.masquer(texte)[:2000]
    conn.execute("INSERT INTO journal (quand, acteur, action, projet_id, cible, detail) VALUES (?, ?, ?, ?, ?, ?)",
                 (maintenant(), str(acteur)[:200], action, projet_id, cible, texte))


def lire_emetteur(conn: sqlite3.Connection, cle: str) -> Any:
    ligne = conn.execute("SELECT valeur FROM emetteur WHERE cle = ?", (cle,)).fetchone()
    if ligne is None:
        return None
    try:
        return json.loads(ligne[0])
    except ValueError:
        return None


def ecrire_emetteur(conn: sqlite3.Connection, cle: str, valeur: Any) -> None:
    """État de l'émetteur (à appeler DANS une transaction)."""
    conn.execute("INSERT INTO emetteur (cle, valeur, maj_le) VALUES (?, ?, ?) ON CONFLICT(cle) DO UPDATE SET "
                 "valeur = excluded.valeur, maj_le = excluded.maj_le",
                 (cle, json.dumps(valeur, ensure_ascii=False), maintenant()))


def ligne_en_dict(ligne: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return {k: ligne[k] for k in ligne.keys()} if ligne is not None else None
