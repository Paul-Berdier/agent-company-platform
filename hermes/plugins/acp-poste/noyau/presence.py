"""Présence du poste Windows (cahier P4 § 12.4, étendue en P5 § 4.7) et état du poste (outil ``poste_etat``,
route ``/v1/poste``).

- :func:`enregistrer_dans` : appelée SOUS la transaction de la route ``/machine/v1/reclamer`` pour chaque
  réclamation d'un poste CONFIRMÉ (source ``longpoll``) ; :func:`enregistrer` (transaction propre) sert au poste
  simulé des tests (source ``simule``).
- :func:`evaluer` : dans chaque passe de l'émetteur (passerelle). Au-delà de ``seuil_hors_ligne_s`` sans vue, le
  poste passe ``hors_ligne`` et UNE notification part (clé ``hors_ligne:<machine>:<passage>``). Un retour en ligne
  ouvre un nouveau passage. Étape P5 : seuls les postes ``actif`` sont évalués (et la source ``simule`` des tests) —
  un poste révoqué, donc arrêté, ne déclenche jamais « Poste hors ligne » ; et une **grâce de redémarrage** :
  hors ligne seulement si ``maintenant − max(dernière vue, démarrage du tableau de bord, démarrage de CE processus)``
  dépasse le seuil (un redéploiement qui coupe les attentes ne notifie pas à tort, même si la passerelle repart avant
  le tableau de bord).
- Jamais vu : ``non_configure``, AUCUNE notification. ``stranded_in_ready`` n'émet aucun événement : la
  présence est la seule source (plan § 6).
- Étape P6 (cahier P6 § 5.3, § 5.8) : le ``battement`` de l'exécutant vaut présence ; un ``arret`` propre (SIGTERM d'un
  redéploiement) retarde la notification de ``grace_arret_propre_s`` (10 min) et l'état se lit « Exécutant en
  redéploiement » ; tout retour (long-poll ou battement) efface la marque. Libellé « Exécutant Railway » quand
  l'inventaire dit ``hote = railway``.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from . import base, machines, notifications, routage
from . import kanban_adapter as ka
from . import textes as T

SOURCES = ("longpoll", "battement", "simule")
_MACHINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
# Instant de démarrage de CE processus (import du noyau) : la passerelle, qui évalue la présence, peut repartir
# avant que le tableau de bord ait réécrit sa date de démarrage (cahier P5 § 4.7).
DEMARRAGE_DU_PROCESSUS = int(time.time())
CLE_DEMARRAGE_TABLEAU_DE_BORD = "demarrage_tableau_de_bord"


def enregistrer_dans(conn, machine_id: str, source: str) -> Dict[str, Any]:
    """Présence vue maintenant, SOUS la transaction de l'appelant."""
    if not isinstance(machine_id, str) or not _MACHINE.match(machine_id):
        raise ValueError("identifiant de machine invalide")
    if source not in SOURCES:
        raise ValueError(f"source de présence inconnue : {source}")
    maintenant = base.maintenant()
    ligne = conn.execute("SELECT * FROM presence WHERE machine_id = ?", (machine_id,)).fetchone()
    if ligne is not None and ligne["arret_propre_le"] is not None:
        conn.execute("UPDATE presence SET arret_propre_le = NULL WHERE machine_id = ?", (machine_id,))
    if ligne is None:
        conn.execute("INSERT INTO presence (machine_id, derniere_vue, source, passage) VALUES (?, ?, ?, 1)",
                     (machine_id, maintenant, source))
    elif ligne["hors_ligne_depuis"] is not None:
        conn.execute("UPDATE presence SET derniere_vue = ?, source = ?, passage = passage + 1, "
                     "hors_ligne_depuis = NULL, hors_ligne_notifie = 0 WHERE machine_id = ?",
                     (maintenant, source, machine_id))
        base.journaliser(conn, f"poste:{machine_id}", "retour_en_ligne", cible=machine_id)
    else:
        conn.execute("UPDATE presence SET derniere_vue = ?, source = ? WHERE machine_id = ?",
                     (maintenant, source, machine_id))
    return base.ligne_en_dict(conn.execute("SELECT * FROM presence WHERE machine_id = ?", (machine_id,)).fetchone())


def enregistrer(conn, machine_id: str, source: str) -> Dict[str, Any]:
    with base.transaction(conn):
        return enregistrer_dans(conn, machine_id, source)


def cartes_en_attente(conn) -> int:
    """Cartes du poste prêtes et non réclamées, sur tous les tableaux de projet (lecture kanban)."""
    total = 0
    for p in conn.execute("SELECT tableau FROM projets WHERE etat IN ('actif', 'en_pause', 'creation')").fetchall():
        try:
            with ka.connexion(p["tableau"]) as kc:
                total += sum(1 for t in ka.list_tasks(kc, status="ready") if ka.est_voie_poste(t.assignee))
        except Exception:  # noqa: BLE001 — tableau illisible : non compté (le compte est un minimum)
            continue
    return total


def ecrire_demarrage_tableau_de_bord(conn) -> None:
    """Écrit par ``dashboard/plugin_api.py`` à son import (processus du tableau de bord)."""
    with base.transaction(conn):
        base.ecrire_emetteur(conn, CLE_DEMARRAGE_TABLEAU_DE_BORD, base.maintenant())


def reference_de_grace(conn) -> int:
    """Le plus récent des démarrages connus (tableau de bord, processus courant) : aucune absence n'est comptée
    avant lui."""
    tableau = base.lire_emetteur(conn, CLE_DEMARRAGE_TABLEAU_DE_BORD)
    return max(int(tableau) if isinstance(tableau, int) else 0, DEMARRAGE_DU_PROCESSUS)


def _lignes_evaluees(conn) -> List[Any]:
    return conn.execute(
        "SELECT p.* FROM presence p LEFT JOIN machines m ON m.id = p.machine_id "
        "WHERE (m.etat = 'actif') OR (m.id IS NULL AND p.source = 'simule')").fetchall()


def en_redeploiement(conn, ligne) -> bool:
    """Arrêt propre annoncé (route ``arret``) depuis moins de ``grace_arret_propre_s`` (étape P6, § 5.8)."""
    arret = ligne["arret_propre_le"] if "arret_propre_le" in ligne.keys() else None
    grace = int(base.reglage(conn, "grace_arret_propre_s") or 600)
    return arret is not None and base.maintenant() - int(arret) <= grace


def est_executant_railway(conn, machine_id: str) -> bool:
    ligne = conn.execute("SELECT hote FROM machines WHERE id = ?", (machine_id,)).fetchone()
    return ligne is not None and ligne["hote"] == "railway"


def evaluer(conn) -> List[str]:
    """Passe les postes actifs silencieux en ``hors_ligne`` et enfile UNE notification par passage."""
    maintenant = base.maintenant()
    seuil = int(base.reglage(conn, "seuil_hors_ligne_s") or 180)
    grace = reference_de_grace(conn)
    notifiees: List[str] = []
    for ligne in _lignes_evaluees(conn):
        if ligne["hors_ligne_notifie"] or maintenant - max(int(ligne["derniere_vue"]), grace) <= seuil:
            continue
        if en_redeploiement(conn, ligne):
            continue  # arrêt propre : la notification attend la fin de la grâce (P6 § 5.8)
        depuis = int(ligne["derniere_vue"])
        modele = (T.NOTIF_HORS_LIGNE_EXECUTANT if est_executant_railway(conn, ligne["machine_id"])
                  else T.NOTIF_HORS_LIGNE)
        texte = notifications.texte(modele, heure=routage.date_lisible(depuis, "%H:%M"),
                                    cartes=T.cartes(cartes_en_attente(conn)))
        with base.transaction(conn):
            # Relu dans la transaction : une révocation ou un retour entre la lecture et l'écriture est vu.
            encore = conn.execute(
                "SELECT p.derniere_vue FROM presence p LEFT JOIN machines m ON m.id = p.machine_id WHERE "
                "p.machine_id = ? AND p.hors_ligne_notifie = 0 AND ((m.etat = 'actif') OR (m.id IS NULL AND "
                "p.source = 'simule'))", (ligne["machine_id"],)).fetchone()
            if encore is None or int(encore[0]) != depuis:
                continue
            conn.execute("UPDATE presence SET hors_ligne_depuis = ?, hors_ligne_notifie = 1 WHERE machine_id = ?",
                         (depuis, ligne["machine_id"]))
            notifications.enfiler_dans(conn, cle=f"hors_ligne:{ligne['machine_id']}:{ligne['passage']}",
                                       genre="hors_ligne", texte_notif=texte)
            base.journaliser(conn, "acp-poste:emetteur", "hors_ligne", cible=ligne["machine_id"])
        notifiees.append(ligne["machine_id"])
    return notifiees


def _etat_presence(conn, ligne) -> Dict[str, Any]:
    seuil = int(base.reglage(conn, "seuil_hors_ligne_s") or 180)
    en_ligne = base.maintenant() - int(ligne["derniere_vue"]) <= seuil
    return {"etat": "en_ligne" if en_ligne else "hors_ligne", "derniere_vue": ligne["derniere_vue"],
            "derniere_vue_lisible": routage.date_lisible(ligne["derniere_vue"]),
            "hors_ligne_depuis": None if en_ligne else int(ligne["hors_ligne_depuis"] or ligne["derniere_vue"]),
            "source": ligne["source"]}


def etat_poste(conn) -> Dict[str, Any]:
    """``non_configure`` (jamais vu), ``a_confirmer``, ``en_ligne``, ``hors_ligne`` ou ``revoque`` ; jamais une valeur
    inventée. Sans poste enrôlé, la présence SIMULÉE des tests de P4 garde son sens (en ligne, hors ligne)."""
    resultat: Dict[str, Any] = {"pause_reclamations": bool(base.reglage(conn, "pause_reclamations"))}
    try:
        resultat["cartes_en_attente"] = cartes_en_attente(conn)
    except Exception:  # noqa: BLE001
        resultat["cartes_en_attente"] = None
    courante = machines.machine_courante(conn)
    resultat["poste"] = machines.vue(courante)
    vide = {"derniere_vue": None, "hors_ligne_depuis": None}
    if courante is not None and courante["etat"] == "actif":
        ligne = conn.execute("SELECT * FROM presence WHERE machine_id = ?", (courante["id"],)).fetchone()
        if ligne is None:
            resultat.update(etat="hors_ligne", machine=courante["id"], message=T.POSTE_JAMAIS_VU_DEPUIS, **vide)
        else:
            resultat.update(machine=courante["id"], message=None, **_etat_presence(conn, ligne))
            if resultat["etat"] == "hors_ligne" and en_redeploiement(conn, ligne):
                resultat.update(etat="redeploiement", message=T.POSTE_ETAT_REDEPLOIEMENT.format(
                    heure=routage.date_lisible(ligne["arret_propre_le"], "%H:%M")))
        if not courante["politique_valide"]:
            resultat["message"] = T.POSTE_ETAT_POLITIQUE_INVALIDE
        return resultat
    if courante is not None and courante["etat"] == "a_confirmer":
        resultat.update(etat="a_confirmer", machine=courante["id"], **vide,
                        message=T.POSTE_ETAT_A_CONFIRMER.format(empreinte=machines.empreinte_affichee(courante)))
        return resultat
    simulee = conn.execute("SELECT p.* FROM presence p LEFT JOIN machines m ON m.id = p.machine_id WHERE m.id IS NULL "
                           "ORDER BY p.derniere_vue DESC LIMIT 1").fetchone()
    if simulee is not None:
        resultat.update(machine=simulee["machine_id"], message=None, **_etat_presence(conn, simulee))
        return resultat
    if courante is not None:  # révoqué
        resultat.update(etat="revoque", machine=courante["id"], **vide,
                        message=T.POSTE_ETAT_REVOQUE.format(date=routage.date_lisible(courante["revoque_le"]),
                                                            motif=courante["motif_revocation"] or T.INCONNU))
        return resultat
    resultat.update(etat="non_configure", machine=None, message=T.POSTE_JAMAIS_VU, **vide)
    return resultat
