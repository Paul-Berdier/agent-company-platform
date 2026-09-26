"""Émetteur de notifications et passe de maintenance, DANS LA PASSERELLE (cahier P4 § 12.5).

**Où.** ``register()`` inscrit :func:`sur_tick` sur le crochet ``on_kanban_dispatch_tick`` dans tous les
processus, mais le crochet n'est tiré que par le répartiteur kanban, que la managed scope place dans la
passerelle (``kanban.dispatch_in_gateway: true``) ; et :func:`sur_tick` ne fait rien hors de la passerelle
(:func:`configurer`). Preuve : ``derniere_passe`` écrite par la passe, lue par ``/v1/meta``.

**Quand.** Le crochet est appelé une fois PAR TABLEAU et par passage du répartiteur, après la libération
de son verrou. :func:`sur_tick` note ``result.skipped_nonspawnable`` du tableau, rend la main si la dernière
passe date de moins de ``emetteur_intervalle_s`` (plancher 5 s), et ne bloque jamais (verrou non bloquant).

**Passe** : (1) réparation des créations interrompues ; (2) cartes ``poste-*`` étrangères et cartes des
projets en pause ; (3) événements de chaque tableau de projet depuis son curseur, par lots de 500, règles
ci-dessous, curseur avancé dans la MÊME transaction que les notifications ; (3 bis) filets déterministes de
la relecture de P4 : planification finie sans plan → carte de décision, question dont la carte « répondre »
s'est terminée sans suite → escaladée ; (4) questions escaladées ; (5) présence du poste ; (6) projets
terminés ; (7) veille des crochets shell (décision D34) ; (8) état de l'émetteur ; (9) réveil du fil d'envoi.

**Règles** (rien d'autre) : ``blocked`` hors ``dependency`` → ``bloquee`` ; ``block_loop_detected`` →
``triage`` ; ``gave_up`` → ``abandon`` ; synthèse du tour courant finie et plus rien d'ouvert → ``termine``
(une seule fois) ; question escaladée → ``question`` ; présence → ``hors_ligne`` ; plafond → ``plafond`` ;
planification sans plan → ``triage``. Aucune notification pour un ``completed`` intermédiaire, ``claimed``
ou ``promoted``.

**Limite dite (D31)** : pendant la pause générale (arrêt d'urgence de Hermes), le répartiteur ne tourne
plus : aucune passe, donc aucune NOUVELLE notification (celles déjà en file partent encore).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import base, cartes, etrangeres, graphe, notifications, presence, projets, questions
from . import kanban_adapter as ka
from . import textes as T

_config = notifications.Configuration()
_dans_la_passerelle = False
_transport: notifications.Transport = notifications.transport_urllib
_verrou = threading.Lock()
_derniere_passe = 0.0
_derniers_ticks: Dict[str, int] = {}
_fil: Optional[threading.Thread] = None
_reveil = threading.Event()
INTERVALLE_FIL_S = 30
LOTS_MAX = 10


def configurer(config: notifications.Configuration, *, passerelle: bool,
               transport: Optional[notifications.Transport] = None, garder_le_canal_connu: bool = False) -> None:
    """Appelée par ``register()`` : la configuration du canal n'est gardée QUE dans la passerelle."""
    global _config, _dans_la_passerelle, _transport
    _dans_la_passerelle = bool(passerelle)
    if not (garder_le_canal_connu and passerelle and _config.configure):
        _config = config if passerelle else notifications.Configuration()
    if transport is not None:
        _transport = transport


def sur_tick(board: Optional[str] = None, profile_name: Optional[str] = None, dry_run: bool = False,
             outcome: Optional[str] = None, result: Any = None, **_ignores: Any) -> None:
    """Crochet ``on_kanban_dispatch_tick`` : ne lève jamais (Hermes avale les échecs, mais on ne compte pas
    dessus), ne bloque jamais."""
    global _derniere_passe
    try:
        if not _dans_la_passerelle or dry_run:
            return
        if board:
            _derniers_ticks[str(board)] = len(getattr(result, "skipped_nonspawnable", None) or [])
        with base.connexion() as conn:
            intervalle = max(base.PLANCHER_EMETTEUR_S, int(base.reglage(conn, "emetteur_intervalle_s") or 15))
        if time.monotonic() - _derniere_passe < intervalle:
            return
        if not _verrou.acquire(blocking=False):
            return
        try:
            _derniere_passe = time.monotonic()
            passe()
        finally:
            _verrou.release()
        demarrer_fil()
    except Exception:  # noqa: BLE001
        return


def _pas(bilan: Dict[str, Any], nom: str, fonction, *args) -> Any:
    try:
        resultat = fonction(*args)
        bilan[nom] = resultat if isinstance(resultat, (int, list, dict, str)) or resultat is None else str(resultat)
        return resultat
    except Exception as exc:  # noqa: BLE001 — une étape en échec n'arrête pas les autres
        bilan.setdefault("erreurs", []).append(f"{nom} : {type(exc).__name__}")
        bilan.setdefault("traces", []).append(traceback.format_exc(limit=3)[-800:])
        return None


def _texte_carte(kc, carte: str) -> str:
    tache = ka.get_task(kc, carte)
    return tache.title if tache is not None else carte


def lire_evenements(conn) -> Dict[str, int]:
    """Étape 3 : événements de chaque tableau de projet depuis son curseur ; notifications et curseur dans
    la même transaction."""
    comptes: Dict[str, int] = {}
    for fiche in [base.ligne_en_dict(l) for l in conn.execute("SELECT * FROM projets WHERE etat != 'abandonne'")]:
        ligne = conn.execute("SELECT evenement FROM curseurs WHERE tableau = ?", (fiche["tableau"],)).fetchone()
        if ligne is None:
            continue  # projet encore en création : la réparation posera le curseur
        curseur = int(ligne[0])
        for _lot in range(LOTS_MAX):
            with ka.connexion(fiche["tableau"]) as kc:
                evenements = ka.evenements_apres(kc, curseur, 500)
                a_notifier = []
                for identifiant, carte, genre, charge, _cree in evenements:
                    try:
                        donnees = json.loads(charge) if isinstance(charge, str) and charge else (charge or {})
                    except ValueError:
                        donnees = {}
                    donnees = donnees if isinstance(donnees, dict) else {}
                    if genre == "blocked" and donnees.get("kind") != "dependency":
                        a_notifier.append(("bloquee", T.NOTIF_BLOQUEE, identifiant, _texte_carte(kc, carte)))
                    elif genre == "block_loop_detected":
                        a_notifier.append(("triage", T.NOTIF_TRIAGE, identifiant, _texte_carte(kc, carte)))
                    elif genre == "gave_up":
                        a_notifier.append(("abandon", T.NOTIF_ABANDON, identifiant, _texte_carte(kc, carte)))
            if not evenements:
                break
            with base.transaction(conn):
                for genre, modele, identifiant, titre_carte in a_notifier:
                    notifications.enfiler_dans(conn, cle=f"{genre}:{fiche['tableau']}:{identifiant}", genre=genre,
                                               projet_id=fiche["id"],
                                               texte_notif=notifications.texte(modele, titre=fiche["titre"],
                                                                               carte=titre_carte))
                curseur = evenements[-1][0]
                conn.execute("INSERT INTO curseurs (tableau, evenement, maj_le) VALUES (?, ?, ?) ON CONFLICT(tableau) "
                             "DO UPDATE SET evenement = excluded.evenement, maj_le = excluded.maj_le",
                             (fiche["tableau"], curseur, base.maintenant()))
            comptes[fiche["tableau"]] = comptes.get(fiche["tableau"], 0) + len(a_notifier)
            if len(evenements) < 500:
                break
    return comptes


def questions_escaladees(conn) -> int:
    """Étape 4 : toute question escaladée a sa notification (clé ``question:<q>``, une seule fois)."""
    n = 0
    lignes = conn.execute("SELECT q.id, q.projet_id, p.titre FROM questions q JOIN projets p ON p.id = q.projet_id "
                          "WHERE q.etat = 'escaladee'").fetchall()
    with base.transaction(conn):
        for q in lignes:
            n += notifications.enfiler_dans(conn, cle=f"question:{q['id']}", genre="question", projet_id=q["projet_id"],
                                            texte_notif=notifications.texte(T.NOTIF_QUESTION, titre=q["titre"]))
    return n


def planifications_sans_plan(conn) -> List[str]:
    """Filet déterministe (relecture de P4) : un projet actif SANS aucun tour planifié dont plus aucune carte
    n'est ouverte — la planification (ou sa relance) s'est terminée sans appel réussi à projet_planifier —
    reçoit UNE carte de décision « Planification sans plan » et UNE notification ; sans ce filet il resterait
    arrêté, affiché « en cours », sans que le propriétaire le sache."""
    adresses = []
    for fiche in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT * FROM projets WHERE etat = 'actif' AND tour = 0").fetchall()]:
        demandes = cartes.cartes_du_projet(conn, fiche["id"])
        if not demandes or any(not d["carte"] for d in demandes):
            continue  # création en cours : la réparation s'en charge
        with ka.connexion(fiche["tableau"]) as kc:
            statuts = {d["carte"]: getattr(ka.get_task(kc, d["carte"]), "status", None) for d in demandes}
        if any(s is None or s not in ("done", "archived") for s in statuts.values()):
            continue
        derniere = [d for d in demandes if d["role"] in ("planification", "triage")][-1:]
        if not derniere:
            continue
        carte = graphe.creer_triage_sans_plan(conn, fiche, T.DETAIL_SANS_PLAN.format(carte=derniere[0]["carte"]))
        if carte:
            adresses.append(fiche["id"])
    return adresses


def projets_termines(conn) -> List[str]:
    """Étape 6 : un projet actif dont la synthèse du tour courant est faite et dont plus aucune carte n'est
    ouverte passe ``termine`` ; UNE notification ``termine:<p>``."""
    termines = []
    for fiche in [base.ligne_en_dict(l) for l in conn.execute("SELECT * FROM projets WHERE etat = 'actif' AND tour > 0")]:
        synthese = conn.execute("SELECT carte FROM demandes WHERE projet_id = ? AND tour = ? AND role = 'synthese'",
                                (fiche["id"], fiche["tour"])).fetchone()
        if synthese is None or not synthese["carte"]:
            continue
        with ka.connexion(fiche["tableau"]) as kc:
            tache = ka.get_task(kc, synthese["carte"])
            if tache is None or tache.status != "done":
                continue
            toutes = ka.list_tasks(kc)
        if any(t.status not in ("done", "archived") for t in toutes):
            continue
        faites = sum(1 for t in toutes if t.status == "done")
        with base.transaction(conn):
            if conn.execute("UPDATE projets SET etat = 'termine', termine_le = ?, maj_le = ? WHERE id = ? AND "
                            "etat = 'actif'", (base.maintenant(), base.maintenant(), fiche["id"])).rowcount != 1:
                continue
            notifications.enfiler_dans(conn, cle=f"termine:{fiche['id']}", genre="termine", projet_id=fiche["id"],
                                       texte_notif=notifications.texte(T.NOTIF_TERMINE, titre=fiche["titre"],
                                                                       cartes=T.cartes(faites, "faite")))
            base.journaliser(conn, "acp-poste:emetteur", "termine", projet_id=fiche["id"], detail={"faites": faites})
        termines.append(fiche["id"])
    return termines


def crochets_detectes(home: Optional[Path] = None) -> List[str]:
    """Crochets shell apparus en cours de route : clé ``hooks`` non vide dans le config.yaml du volume ou
    d'un profil, ou ``shell-hooks-allowlist.json`` présent (agent/shell_hooks.py:141-165)."""
    import yaml

    home = Path(home or ka.get_hermes_home())
    racines = [home] + sorted(p for p in (home / "profiles").glob("*") if p.is_dir())
    constats = []
    for racine in racines:
        fichier = racine / "config.yaml"
        try:
            donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) if fichier.is_file() else None
        except Exception:  # noqa: BLE001 — illisible : signalé ailleurs (diagnostiquer)
            donnees = None
        if isinstance(donnees, dict) and donnees.get("hooks"):
            constats.append(f"{fichier} : hooks")
        if (racine / "shell-hooks-allowlist.json").exists():
            constats.append(f"{racine / 'shell-hooks-allowlist.json'}")
    return constats


def veiller_crochets(conn) -> List[str]:
    """Étape 7 (D34) : crochets shell détectés ⇒ arrêt d'urgence de Hermes et notification ``crochets``."""
    constats = crochets_detectes()
    with base.transaction(conn):
        base.ecrire_emetteur(conn, "crochets", constats)
    if constats:
        ka.engage(T.RAISON_PAUSE_CROCHETS)
        empreinte = hashlib.sha256("\n".join(constats).encode("utf-8")).hexdigest()[:16]
        with base.transaction(conn):
            if notifications.enfiler_dans(conn, cle=f"crochets:{empreinte}", genre="crochets",
                                          texte_notif=notifications.texte(T.NOTIF_CROCHETS)):
                base.journaliser(conn, "acp-poste:emetteur", "crochets", detail=constats)
    return constats


def passe(conn=None) -> Dict[str, Any]:
    """Une passe complète (voir l'en-tête du module) ; rend son bilan."""
    if conn is None:
        with base.connexion() as nouvelle:
            return passe(nouvelle)
    bilan: Dict[str, Any] = {"debut": base.maintenant()}
    _pas(bilan, "reparations", cartes.reparer, conn)
    _pas(bilan, "etrangeres", etrangeres.balayer, conn)
    _pas(bilan, "pauses", projets.replanifier_les_projets_en_pause, conn)
    _pas(bilan, "evenements", lire_evenements, conn)
    _pas(bilan, "sans_plan", planifications_sans_plan, conn)
    _pas(bilan, "sans_suite", questions.questions_sans_suite, conn)
    _pas(bilan, "questions", questions_escaladees, conn)
    _pas(bilan, "presence", presence.evaluer, conn)
    _pas(bilan, "termines", projets_termines, conn)
    _pas(bilan, "crochets", veiller_crochets, conn)
    try:
        with base.transaction(conn):
            base.ecrire_emetteur(conn, "derniere_passe", base.maintenant())
            base.ecrire_emetteur(conn, "processus", "passerelle" if _dans_la_passerelle else "test")
            base.ecrire_emetteur(conn, "derniers_ticks", dict(_derniers_ticks))
            base.ecrire_emetteur(conn, "canal", _config.publique())
            base.ecrire_emetteur(conn, "derniere_erreur", (bilan.get("erreurs") or [None])[0])
    except Exception as exc:  # noqa: BLE001
        bilan.setdefault("erreurs", []).append(f"etat : {type(exc).__name__}")
    _reveil.set()
    return bilan


def ecrire_etat_du_canal(conn) -> None:
    """Publie l'état PUBLIC du canal (jamais un jeton) pour le tableau de bord."""
    with base.transaction(conn):
        base.ecrire_emetteur(conn, "canal", _config.publique())


def envoyer_maintenant(conn=None) -> Dict[str, int]:
    if conn is None:
        with base.connexion() as nouvelle:
            return envoyer_maintenant(nouvelle)
    return notifications.envoyer_en_attente(conn, _config, _transport)


def _boucle() -> None:
    while True:
        _reveil.wait(INTERVALLE_FIL_S)
        _reveil.clear()
        try:
            envoyer_maintenant()
        except Exception:  # noqa: BLE001 — le fil ne meurt jamais sur un envoi
            time.sleep(1)


def demarrer_fil() -> None:
    """Fil démon unique d'envoi, démarré au premier passage dans la passerelle."""
    global _fil
    if _fil is not None and _fil.is_alive():
        return
    _fil = threading.Thread(target=_boucle, name="acp-poste-notifications", daemon=True)
    _fil.start()
