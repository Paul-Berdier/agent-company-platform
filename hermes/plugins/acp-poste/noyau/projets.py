"""Projets autonomes (étape P4) : lancement, état, liste, pause et reprise.

Un projet = un tableau kanban créé par le greffon, une ligne ``projets`` et des ``demandes``.
Lancement (cahier P4 § 6.1) : contrôles (aucune écriture avant qu'ils passent), réservation, tableau,
cartes [exploration par le poste si dépôt] puis planification par Hermes, rattachement.

Réalité de production en P4 (décision D25) : sans inventaire du poste, un projet SUR DÉPÔT est refusé
en français ; un projet SANS dépôt (recherche, rédaction, conception) avance jusqu'au bout sur Railway
avec les seules cartes Hermes.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import base, cartes, routage
from . import kanban_adapter as ka
from . import textes as T
from .motifs_secrets import motif_trouve
from .textes import RefusACP, refus

PROFILS = ("base", "web", "recherche", "donnees")
POLITIQUES_REPONSE = ("hermes_d_abord", "proprietaire")
ORIGINES = ("tableau_de_bord", "discussion")
# Compétences des cartes Hermes (cahier P4 § 6 et § 14). Les skills du profil viennent du verrou
# du catalogue ; ACP y ajoute ses skills maison.
COMPETENCES_PLANIFICATION = ["acp-orchestration", "acp-routage", "acp-exploration"]
COMPETENCES_SYNTHESE = ["acp-synthese", "acp-routage"]
COMPETENCES_REPONDRE = ["acp-questions"]
COMPETENCES_HERMES = ["acp-redaction"]
ETATS_OUVERTS = ("creation", "actif", "en_pause")
STATUTS_OUVERTS = ("triage", "todo", "scheduled", "ready", "running", "blocked", "review")
# Longueurs rendues : le résumé d'une carte dans le détail (coupé, et il le dit), la dernière note de la liste
# (coupée, et elle le dit), un texte « complet » (résultat du projet, lecture d'une carte) borné très haut.
LONGUEUR_RESUME = 500
LONGUEUR_NOTE = 200
LONGUEUR_TEXTE_COMPLET = 100_000


def _texte_borne(valeur: Any, *, maximum: int, code: str, message: str) -> str:
    if not isinstance(valeur, str) or not 1 <= len(valeur.strip()) <= maximum:
        raise refus(code, message)
    return valeur.strip()


def slug_tableau(titre: str) -> str:
    """``acp-<titre normalisé, 40 caractères au plus>-<4 hex>`` (slug kanban : kanban_db.py:372)."""
    ascii_ = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode("ascii").lower()
    propre = re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")[:40].strip("-") or "projet"
    return f"acp-{propre}-{secrets.token_hex(2)}"


def debut_du_jour_paris(instant: int) -> int:
    """Minuit du jour courant à Paris (UTC si la base des fuseaux manque, limite dite)."""
    try:
        from zoneinfo import ZoneInfo

        fuseau = ZoneInfo("Europe/Paris")
    except Exception:  # noqa: BLE001
        fuseau = timezone.utc
    local = datetime.fromtimestamp(instant, tz=fuseau)
    return int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def projet(conn, identifiant: str) -> Optional[Dict[str, Any]]:
    """Projet par identifiant (``p_…``) ou par tableau (``acp-…``)."""
    ligne = conn.execute("SELECT * FROM projets WHERE id = ? OR tableau = ?", (identifiant, identifiant)).fetchone()
    return base.ligne_en_dict(ligne)


def exiger_projet(conn, identifiant: str) -> Dict[str, Any]:
    trouve = projet(conn, identifiant)
    if trouve is None:
        raise refus("projet_inconnu", T.PROJET_INCONNU.format(x=identifiant))
    return trouve


def demande_de_la_carte(conn, tableau: str, carte: str) -> Optional[Dict[str, Any]]:
    ligne = conn.execute("SELECT * FROM demandes WHERE tableau = ? AND carte = ?", (tableau, carte)).fetchone()
    return base.ligne_en_dict(ligne)


def pause_generale() -> Optional[Dict[str, Any]]:
    """État de l'arrêt d'urgence de Hermes (``hermes pause``), ou None s'il n'est pas engagé."""
    return ka.get_state()


def lancer(conn, *, titre: Any, objectif: Any, profil: Any = "base", depot: Any = None,
           reponses: Any = "hermes_d_abord", exploration: Optional[Dict[str, Any]] = None, origine: str,
           auteur: str, cle_idempotence: Optional[str] = None) -> Dict[str, Any]:
    """Lance un projet ; rend ``{"projet": {...}, "deja_lance": bool}`` ou lève :class:`RefusACP`."""
    if origine not in ORIGINES:
        raise ValueError(f"origine inconnue : {origine}")
    titre = _texte_borne(titre, maximum=120, code="titre", message=T.TITRE)
    objectif = _texte_borne(objectif, maximum=4000, code="objectif", message=T.OBJECTIF)
    profil = profil or "base"
    if profil not in PROFILS:
        raise refus("profil", T.PROFIL.format(x=str(profil)[:40]))
    reponses = reponses or "hermes_d_abord"
    if reponses not in POLITIQUES_REPONSE:
        raise refus("reponses", T.REPONSES.format(x=str(reponses)[:40]))
    for texte, message in ((titre, T.SECRET_TITRE), (objectif, T.SECRET_OBJECTIF)):
        motif = motif_trouve(texte)
        if motif:
            raise refus("secret", message.format(motif=motif))
    if cle_idempotence:
        existant = conn.execute("SELECT * FROM projets WHERE cle_idempotence = ?", (cle_idempotence,)).fetchone()
        if existant is not None:
            return {"projet": resume_projet(conn, base.ligne_en_dict(existant)), "deja_lance": True}
    if pause_generale() is not None:
        raise refus("pause_generale", T.PAUSE_GENERALE_LANCER)
    maximum = int(base.reglage(conn, "projets_actifs_max") or 3)
    actifs = conn.execute("SELECT COUNT(*) FROM projets WHERE etat IN ('creation', 'actif')").fetchone()[0]
    if actifs >= maximum:
        raise refus("projets_actifs", T.PROJETS_ACTIFS.format(n=maximum))
    if origine == "discussion":
        par_jour = int(base.reglage(conn, "lancements_discussion_par_jour") or 5)
        lances = conn.execute("SELECT COUNT(*) FROM projets WHERE origine = 'discussion' AND cree_le >= ?",
                              (debut_du_jour_paris(base.maintenant()),)).fetchone()[0]
        if lances >= par_jour:
            raise refus("lancements_jour", T.LANCEMENTS_JOUR.format(n=par_jour))
    depot = depot or None
    if depot is not None:
        if not isinstance(depot, str):
            raise refus("depot_inconnu", T.DEPOT_INCONNU.format(x=str(depot)[:40], liste=T.INCONNU))
        autorises = routage.depots_autorises(conn)
        if autorises is None:
            raise refus("aucun_inventaire", T.AUCUN_INVENTAIRE)
        if depot not in autorises:
            raise refus("depot_inconnu", T.DEPOT_INCONNU.format(x=depot[:40], liste=T.liste(autorises)))
    elif exploration:
        raise refus("exploration", T.EXPLORATION_SANS_DEPOT)
    ebauche = {"id": None, "titre": titre, "depot_alias": depot}
    resolution_exploration = None
    if depot is not None:
        exploration = exploration or {}
        try:
            resolution_exploration = routage.resoudre(
                conn, classe="exploration", projet=ebauche, voie=exploration.get("voie"),
                modele=exploration.get("modele"), effort=exploration.get("effort"), ref="exploration")
        except RefusACP as exc:
            raison = exc.message[len(T.PREFIXE_REFUS):] if exc.message.startswith(T.PREFIXE_REFUS) else exc.message
            raise refus("exploration", T.EXPLORATION.format(raison=raison)) from None
    resolution_planif = routage.resoudre(conn, classe="planification", projet=ebauche, ref="planification")

    maintenant = base.maintenant()
    identifiant = "p_" + secrets.token_hex(6)
    tableau = slug_tableau(titre)
    plafonds = {k: int(base.reglage(conn, k)) for k in ("plafond_tours", "plafond_cartes", "plafond_corrections")}
    fiche = {"id": identifiant, "tableau": tableau, "titre": titre, "objectif": objectif, "profil": profil,
             "depot_alias": depot, "reponses": reponses}
    demandes: List[Dict[str, Any]] = []
    cle_exploration = f"{ka.PREFIXE_CLE}{identifiant}:t0:exploration"
    if resolution_exploration is not None:
        r = resolution_exploration
        demandes.append(dict(
            cle=cle_exploration, projet_id=identifiant, tableau=tableau, role="exploration", classe="exploration",
            voie=r.voie, tour=0, ref="exploration", titre=f"Exploration du dépôt « {depot} »", modele=r.modele,
            effort=r.effort, palier=r.palier, modele_carte=r.modele, effort_carte=r.effort_carte,
            source_routage=r.source_routage, releve_id=r.releve_id, depot_alias=depot, mention=r.mention,
            consigne=T.CONSIGNE_EXPLORATION.format(depot=depot, titre=titre, objectif=objectif), priorite=10,
            corps=T.CONSIGNE_EXPLORATION.format(depot=depot, titre=titre, objectif=objectif)))
    r = resolution_planif
    corps_planif = T.CORPS_PLANIFICATION.format(
        titre=titre, profil=profil, depot=depot or "aucun", reponses=reponses, objectif=objectif,
        tours=plafonds["plafond_tours"], cartes=plafonds["plafond_cartes"], corrections=plafonds["plafond_corrections"])
    demandes.append(dict(
        cle=f"{ka.PREFIXE_CLE}{identifiant}:t0:planification", projet_id=identifiant, tableau=tableau,
        role="planification", classe="planification", voie="hermes", tour=0, ref="planification",
        titre=f"Planification — {titre}", modele=r.modele, effort=r.effort, palier=r.palier, modele_carte=r.modele,
        effort_carte=r.effort_carte, source_routage=r.source_routage, releve_id=r.releve_id, depot_alias=depot,
        consigne=objectif, parents=[cle_exploration] if resolution_exploration is not None else [],
        competences=COMPETENCES_PLANIFICATION, priorite=10, duree_max=cartes.DUREE_PLANIFICATION, corps=corps_planif))
    with base.transaction(conn):
        conn.execute(
            "INSERT INTO projets (id, tableau, titre, objectif, profil, depot_alias, reponses, etat, tour, plafond_tours, "
            "plafond_cartes, plafond_corrections, cartes_creees, origine, auteur, cle_idempotence, cree_le, maj_le) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'creation', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (identifiant, tableau, titre, objectif, profil, depot, reponses, plafonds["plafond_tours"],
             plafonds["plafond_cartes"], plafonds["plafond_corrections"], len(demandes), origine, auteur,
             cle_idempotence, maintenant, maintenant))
        cartes.reserver(conn, demandes)
        base.journaliser(conn, auteur, "lancement", projet_id=identifiant, cible=tableau,
                         detail={"origine": origine, "depot": depot, "profil": profil})
    ids = cartes.creer(conn, fiche, cartes.demandes_non_rattachees(conn, identifiant), creer_tableau=True)
    with ka.connexion(tableau) as kc:
        dernier = ka.dernier_evenement(kc)
    with base.transaction(conn):
        conn.execute("UPDATE projets SET etat = 'actif', maj_le = ? WHERE id = ? AND etat = 'creation'",
                     (base.maintenant(), identifiant))
        conn.execute("INSERT OR IGNORE INTO curseurs (tableau, evenement, maj_le) VALUES (?, ?, ?)",
                     (tableau, dernier, base.maintenant()))
    trouve = projet(conn, identifiant)
    resume = resume_projet(conn, trouve)
    resume["cartes"] = {"exploration": ids.get(cle_exploration),
                        "planification": ids.get(f"{ka.PREFIXE_CLE}{identifiant}:t0:planification")}
    return {"projet": resume, "deja_lance": False}


def cle_idempotence_discussion(session_id: Optional[str], titre: Any, objectif: Any, depot: Any) -> str:
    brut = "\x1f".join(str(v or "") for v in (session_id, titre, objectif, depot))
    return "discussion:" + hashlib.sha256(brut.encode("utf-8")).hexdigest()


def resume_projet(conn, fiche: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if fiche is None:
        return {}
    return {"id": fiche["id"], "titre": fiche["titre"], "tableau": fiche["tableau"], "etat": fiche["etat"],
            "profil": fiche["profil"], "depot": fiche["depot_alias"], "reponses": fiche["reponses"],
            "tour": fiche["tour"], "origine": fiche["origine"]}


# ------------------------------------------------------------------ état d'un projet


def _statuts(fiche: Dict[str, Any], demandes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """{carte: Task} des cartes rattachées (lecture du tableau du projet)."""
    taches: Dict[str, Any] = {}
    with ka.connexion(fiche["tableau"]) as kc:
        for d in demandes:
            if d["carte"]:
                tache = ka.get_task(kc, d["carte"])
                if tache is not None:
                    taches[d["carte"]] = tache
        resumes = ka.latest_summaries(kc, list(taches)) if taches else {}
    return {"taches": taches, "resumes": resumes}


def etat_derive(fiche: Dict[str, Any], demandes: List[Dict[str, Any]], taches: Dict[str, Any]) -> str:
    """État lisible d'un projet actif. « a_decider » : une décision du propriétaire est attendue (planification
    finie sans plan, carte passée en triage par Hermes) ; jamais « en_cours » pour un projet arrêté."""
    if fiche["etat"] in ("creation", "en_pause", "termine", "abandonne"):
        return fiche["etat"]
    statut = {d["cle"]: (taches[d["carte"]].status if d["carte"] in taches else None) for d in demandes}
    ouvertes = [d for d in demandes if statut[d["cle"]] in STATUTS_OUVERTS]
    en_triage = [d for d in demandes if statut[d["cle"]] == "triage"]
    if any(d["role"] == "triage" and str(d["ref"] or "").startswith("plafond-") for d in en_triage):
        return "plafond_atteint"
    if en_triage:
        return "a_decider"
    if any(d["role"] == "exploration" and statut[d["cle"]] not in ("done", "archived") for d in demandes):
        return "exploration"
    if any(d["role"] == "planification" and statut[d["cle"]] not in ("done", "archived") for d in demandes):
        return "planification"
    if any(d["role"] == "triage" and statut[d["cle"]] in ("todo", "ready", "running") for d in demandes):
        return "planification"  # carte de décision prolongée ou relancée : Hermes planifie la suite
    if int(fiche["tour"] or 0) == 0 and demandes and not ouvertes:
        return "a_decider"  # planification finie sans plan (la passe suivante de l'émetteur adresse la décision)
    if any(d["role"] == "synthese" and d["tour"] == fiche["tour"] and statut[d["cle"]] in ("ready", "running")
           for d in demandes):
        return "synthese"
    if ouvertes and not any(statut[d["cle"]] == "running" for d in ouvertes) and any(
            d["voie"] != "hermes" and statut[d["cle"]] == "ready" for d in ouvertes):
        return "en_attente_du_poste"
    return "en_cours"


def etat(conn, fiche: Dict[str, Any], *, avec_journal: bool = False) -> Dict[str, Any]:
    """État complet d'un projet (outil ``projet_etat``, route ``GET /v1/projets/{id}``). Tous les textes
    passent par le masquage des secrets de Hermes ; le modèle servi reste « Non observé » avant P6."""
    demandes = cartes.cartes_du_projet(conn, fiche["id"])
    lu = _statuts(fiche, demandes)
    taches, resumes = lu["taches"], lu["resumes"]
    liste_cartes = []
    exploration = None
    resultat_projet = None
    for d in demandes:
        tache = taches.get(d["carte"]) if d["carte"] else None
        resume = ka.masquer(resumes.get(d["carte"])) if d["carte"] and resumes.get(d["carte"]) else None
        if d["role"] == "exploration" and resume:
            exploration = resume[:4000]
        if d["role"] == "synthese" and resume and tache is not None and tache.status == "done" and (
                resultat_projet is None or d["tour"] >= resultat_projet["tour"]):
            # Résultat du projet : la synthèse faite du dernier tour, EN ENTIER (borne haute dite).
            resultat_projet = {"tour": d["tour"], "carte": d["carte"], "texte": resume[:LONGUEUR_TEXTE_COMPLET],
                               "longueur": len(resume), "tronque": len(resume) > LONGUEUR_TEXTE_COMPLET}
        liste_cartes.append({
            "carte": d["carte"], "titre": ka.masquer(tache.title if tache else d["titre"])[:200], "role": d["role"],
            "classe": d["classe"], "tour": d["tour"], "ref": d["ref"], "voie": d["voie"],
            "statut": tache.status if tache else ("a_creer" if not d["carte"] else T.INCONNU),
            "modele": d["modele"] or (T.MODELE_DU_PROFIL if d["voie"] == "hermes" else None),
            "effort": d["effort"], "effort_carte": d["effort_carte"], "palier": d["palier"],
            "source_routage": d["source_routage"], "mention": d["mention"],
            "modele_servi": d["modele_servi"] or T.NON_OBSERVE,
            "relue": d["carte_relue"], "resume": resume[:LONGUEUR_RESUME] if resume else None,
            # Un résumé coupé le dit : longueur totale, et le texte entier par GET /v1/projets/{id}/cartes/{carte}.
            "resume_longueur": len(resume) if resume else None,
            "resume_tronque": bool(resume) and len(resume) > LONGUEUR_RESUME,
        })
    tours = [{"tour": t["tour"], "resume": ka.masquer(t["resume"])[:2000], "decisions": [
        ka.masquer(x) for x in json.loads(t["decisions"])]} for t in conn.execute(
        "SELECT * FROM tours WHERE projet_id = ? ORDER BY tour", (fiche["id"],))]
    questions = [{"id": q["id"], "carte": q["carte"], "etat": q["etat"], "texte": ka.masquer(q["texte"])[:1000],
                  "carte_repondre": q["carte_repondre"]}
                 for q in conn.execute("SELECT * FROM questions WHERE projet_id = ? AND etat IN ('ouverte', 'escaladee') "
                                       "ORDER BY cree_le", (fiche["id"],))]
    faites = sum(1 for c in liste_cartes if c["statut"] == "done")
    resultat = {
        **resume_projet(conn, fiche),
        "objectif": ka.masquer(fiche["objectif"]),
        "etat_derive": etat_derive(fiche, demandes, taches),
        "plafonds": {"tours": fiche["plafond_tours"], "cartes": fiche["plafond_cartes"],
                     "corrections": fiche["plafond_corrections"]},
        "restants": {"tours": max(0, fiche["plafond_tours"] - fiche["tour"]),
                     "cartes": max(0, fiche["plafond_cartes"] - fiche["cartes_creees"])},
        "cartes_creees": fiche["cartes_creees"],
        "compteurs": {"faites": faites, "total": len(liste_cartes)},
        "exploration": exploration,
        "resultat": resultat_projet,
        "tours": tours,
        "cartes": liste_cartes,
        "questions_ouvertes": questions,
        "cree_le": fiche["cree_le"], "termine_le": fiche["termine_le"],
    }
    if avec_journal:
        resultat["journal"] = [{"quand": j["quand"], "acteur": j["acteur"], "action": j["action"], "cible": j["cible"],
                                "detail": j["detail"]} for j in conn.execute(
            "SELECT * FROM journal WHERE projet_id = ? ORDER BY id DESC LIMIT 100", (fiche["id"],))]
    return resultat


def lister(conn) -> List[Dict[str, Any]]:
    """Liste résumée des projets (route ``GET /v1/projets``, outil ``projet_etat`` sans paramètre)."""
    resultat = []
    for ligne in conn.execute("SELECT * FROM projets ORDER BY cree_le DESC"):
        fiche = base.ligne_en_dict(ligne)
        demandes = cartes.cartes_du_projet(conn, fiche["id"])
        try:
            lu = _statuts(fiche, demandes)
        except Exception:  # noqa: BLE001 — tableau illisible : compteurs inconnus, jamais inventés
            lu = None
        compteurs: Dict[str, Any] = {"faites": None, "total": len(demandes), "en_cours": None,
                                     "en_attente_du_poste": None, "bloquees": None, "triage": None}
        derniere_note = None
        note_tronquee = False
        etat_calcule = fiche["etat"]
        if lu is not None:
            taches = lu["taches"]
            statuts = [taches[d["carte"]].status if d["carte"] in taches else None for d in demandes]
            compteurs.update(
                faites=statuts.count("done"), en_cours=statuts.count("running"), bloquees=statuts.count("blocked"),
                triage=statuts.count("triage"),
                en_attente_du_poste=sum(1 for d, s in zip(demandes, statuts) if s == "ready" and d["voie"] != "hermes"))
            notes = [(taches[c].completed_at or 0, lu["resumes"][c]) for c in lu["resumes"] if c in taches
                     and taches[c].status == "done"]
            if notes:
                entiere = ka.masquer(max(notes)[1])
                derniere_note, note_tronquee = entiere[:LONGUEUR_NOTE], len(entiere) > LONGUEUR_NOTE
            etat_calcule = etat_derive(fiche, demandes, taches)
        questions = conn.execute("SELECT COUNT(*) FROM questions WHERE projet_id = ? AND etat IN ('ouverte', 'escaladee')",
                                 (fiche["id"],)).fetchone()[0]
        resultat.append({**resume_projet(conn, fiche), "etat_derive": etat_calcule, "compteurs": compteurs,
                         "derniere_note": derniere_note, "derniere_note_tronquee": note_tronquee,
                         "questions_ouvertes": questions,
                         "plafonds": {"tours": fiche["plafond_tours"], "cartes": fiche["plafond_cartes"]},
                         "cartes_creees": fiche["cartes_creees"], "cree_le": fiche["cree_le"]})
    return resultat


def lire_carte(conn, fiche: Dict[str, Any], carte: str) -> Dict[str, Any]:
    """Résumé ENTIER d'une carte du projet (route ``GET /v1/projets/{id}/cartes/{carte}``) : le détail n'en
    rend que les 500 premiers caractères. Masqué ; borné à 100 000 caractères, et il le dit."""
    demande = demande_de_la_carte(conn, fiche["tableau"], carte)
    if demande is None:
        raise refus("carte_inconnue", T.CARTE_DU_PROJET_INCONNUE.format(carte=carte[:40], titre=fiche["titre"]))
    with ka.connexion(fiche["tableau"]) as kc:
        tache = ka.get_task(kc, carte)
        brut = ka.latest_summaries(kc, [carte]).get(carte) if tache is not None else None
    texte = ka.masquer(brut) if brut else None
    return {"carte": carte, "titre": ka.masquer(tache.title if tache else demande["titre"])[:200],
            "role": demande["role"], "statut": tache.status if tache else T.INCONNU,
            "resume": texte[:LONGUEUR_TEXTE_COMPLET] if texte else None, "longueur": len(texte) if texte else 0,
            "tronque": bool(texte) and len(texte) > LONGUEUR_TEXTE_COMPLET}


# ------------------------------------------------------------------ pause et reprise d'un projet


def mettre_en_pause(conn, identifiant: str, *, auteur: str) -> Dict[str, Any]:
    fiche = exiger_projet(conn, identifiant)
    if fiche["etat"] == "en_pause":
        raise refus("deja_en_pause", T.PROJET_DEJA_EN_PAUSE.format(titre=fiche["titre"]))
    if fiche["etat"] != "actif":
        raise refus("projet_fini", T.PROJET_FINI.format(titre=fiche["titre"], etat=fiche["etat"]))
    with base.transaction(conn):
        conn.execute("UPDATE projets SET etat = 'en_pause', maj_le = ? WHERE id = ?", (base.maintenant(), fiche["id"]))
        base.journaliser(conn, auteur, "pause", projet_id=fiche["id"])
    fiche["etat"] = "en_pause"
    planifiees = cartes.planifier_pour_la_pause(
        conn, fiche, [d["carte"] for d in cartes.cartes_du_projet(conn, fiche["id"]) if d["carte"]], acteur=auteur)
    return {"projet": resume_projet(conn, projet(conn, fiche["id"])), "cartes_planifiees": planifiees}


def _derniere_raison_planifiee(kc, carte: str) -> Optional[str]:
    raison = None
    for evenement in ka.list_events(kc, carte):
        if evenement.kind == "scheduled":
            raison = (evenement.payload or {}).get("reason") if isinstance(evenement.payload, dict) else None
    return raison


def reprendre(conn, identifiant: str, *, auteur: str) -> Dict[str, Any]:
    """Reprise : ``unblock_task`` sur les cartes planifiées PAR LA PAUSE (raison exacte) et sur celles dont la
    question a reçu sa réponse pendant la pause (reprise différée) ; une carte planifiée pour une question
    encore ouverte reste en attente de sa réponse. Le plafond de projets actifs vaut aussi à la reprise."""
    fiche = exiger_projet(conn, identifiant)
    if fiche["etat"] != "en_pause":
        raise refus("pas_en_pause", T.PROJET_PAS_EN_PAUSE.format(titre=fiche["titre"]))
    maximum = int(base.reglage(conn, "projets_actifs_max") or 3)
    with base.transaction(conn):
        actifs = conn.execute("SELECT COUNT(*) FROM projets WHERE etat IN ('creation', 'actif')").fetchone()[0]
        if actifs >= maximum:
            raise refus("projets_actifs", T.PROJETS_ACTIFS_REPRISE.format(n=maximum, titre=fiche["titre"]))
        conn.execute("UPDATE projets SET etat = 'actif', maj_le = ? WHERE id = ?", (base.maintenant(), fiche["id"]))
        base.journaliser(conn, auteur, "reprise", projet_id=fiche["id"])
    repondues = {T.RAISON_QUESTION.format(q=q[0]) for q in conn.execute(
        "SELECT id FROM questions WHERE projet_id = ? AND etat = 'repondue'", (fiche["id"],))}
    reveillees = []
    with ka.connexion(fiche["tableau"]) as kc:
        for d in cartes.cartes_du_projet(conn, fiche["id"]):
            if not d["carte"]:
                continue
            tache = ka.get_task(kc, d["carte"])
            if tache is None or tache.status != "scheduled":
                continue
            raison = _derniere_raison_planifiee(kc, d["carte"])
            if (raison == T.RAISON_PAUSE_PROJET or raison in repondues) and ka.unblock_task(kc, d["carte"]):
                reveillees.append(d["carte"])
    if reveillees:
        with base.transaction(conn):
            for carte in reveillees:
                base.journaliser(conn, auteur, "reprise_carte", projet_id=fiche["id"], cible=carte)
    return {"projet": resume_projet(conn, projet(conn, fiche["id"])), "cartes_reveillees": reveillees}


def replanifier_les_projets_en_pause(conn) -> List[str]:
    """Passe de l'émetteur : toute carte ``todo``/``ready`` d'un projet en pause repasse en
    ``scheduled`` (une carte finie pendant la pause laisse des enfants à réveiller). Idempotent."""
    planifiees: List[str] = []
    for ligne in conn.execute("SELECT * FROM projets WHERE etat = 'en_pause'").fetchall():
        fiche = base.ligne_en_dict(ligne)
        planifiees += cartes.planifier_pour_la_pause(
            conn, fiche, [d["carte"] for d in cartes.cartes_du_projet(conn, fiche["id"]) if d["carte"]],
            acteur="acp-poste:emetteur")
    return planifiees
