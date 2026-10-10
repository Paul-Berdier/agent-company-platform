"""Exécution des cartes du poste par l'exécutant (étape P6, cahier P6 § 5 et § 9.2) : sélection et réclamation d'une
carte servie par ``reclamer``, puis les six routes de l'exécution — ``battement``, ``terminer``, ``question``,
``bloquer``, ``reprendre`` et ``arret``.

**Garde de P2 inchangée** : rien ici n'exécute quoi que ce soit dans Hermes. Le greffon ne fait que réclamer une carte
pour l'exécutant (``claim_task``) et enregistrer ce qu'il rapporte (``heartbeat_*``, ``complete_task``,
``request_review``, ``schedule_task``, ``block_task``, ``reclaim_task``), par les fonctions de Hermes.

Règles communes (cahier P6 § 5.1) :

- **émise par le greffon** : une carte inconnue de ``demandes`` vaut 404 ``carte_inconnue`` ; une carte dont la clé,
  le créateur ou l'assigné ne sont pas ceux du greffon vaut 403 ``carte_non_emise`` ;
- **preuve de propriété** : la carte doit être ``running``, son ``claim_lock`` valoir ``acp-poste:<machine du jeton>``
  et son run courant ``run_id`` ; sinon 409 ``reclamation_perdue`` sans aucun effet — sauf ``battement``
  (``valide: false``), ``reprendre`` et ``arret`` (``deja_libre``) ;
- **idempotence** : la réponse 2xx de chaque ``id_envoi`` est gardée 7 jours (table ``envois``) ; un renvoi du même
  corps rend la même réponse avec ``deja_recu: true`` ; un ``id_envoi`` réemployé pour un AUTRE corps est refusé ;
- **un seul fil à la fois** (verrou du processus du tableau de bord, le seul qui sert ces routes) : deux renvois
  simultanés du même envoi ne produisent jamais deux effets.

Les textes reçus sont balayés AVANT (route : ``secret_trouve``) et masqués à l'écriture (``ka.masquer``).
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import base, contrat_partage, etrangeres, graphe, projets, questions, routage  # noqa: F401
from . import kanban_adapter as ka
from . import textes as T
from .textes import RefusACP

from acp_poste_contrat.machine import (  # noqa: E402
    BRANCHE_PROJET,
    PARENTS_MAX,
    RESUME_PARENT_MAX,
    TAILLE_MAX_CARTE,
    DemandeCarte,
    taille_json,
)

ROLES_SERVIS = ("exploration", "implementation", "relecture", "correction", "integration")
ROLES_A_BRANCHE = ("implementation", "correction")
# Issues après lesquelles l'exécutant reprend le fil local de la carte (cahier P6 § 5.2, point 6).
ISSUES_REPRISE = ("question", "bloquee:quota", "arret", "rendue", "revue_refusee")
VOIE_INTEGRATION = ka.VOIE_INTEGRATION
_verrou = threading.RLock()


def verrou() -> threading.RLock:
    """Verrou des routes de l'exécution (contrôle d'envoi, effet et mise en mémoire de la réponse sous lui seul)."""
    return _verrou


def claimer(machine_id: str) -> str:
    """Réclamant stable de l'exécutant : jamais le préfixe d'hôte de Hermes (``kanban_db.py:1086-1098``)."""
    return f"acp-poste:{machine_id}"


def _json(valeur: Any) -> Optional[str]:
    return None if valeur is None else json.dumps(valeur, ensure_ascii=False, sort_keys=True)


def empreinte_requete(corps: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(corps, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ idempotence (table envois)


def envoi_connu(conn, *, id_envoi: str, machine_id: str, route: str, empreinte: str) -> Optional[Dict[str, Any]]:
    """Réponse déjà rendue pour cet ``id_envoi`` (``deja_recu: true``), ``None`` s'il est neuf ; un ``id_envoi``
    réemployé pour un autre corps, une autre route ou une autre machine est refusé (422)."""
    ligne = conn.execute("SELECT * FROM envois WHERE id_envoi = ?", (id_envoi,)).fetchone()
    if ligne is None:
        return None
    if ligne["machine_id"] != machine_id or ligne["route"] != route or ligne["empreinte"] != empreinte:
        raise RefusACP("requete_refusee", T.REQUETE_REFUSEE.format(detail=T.ENVOI_REEMPLOYE))
    reponse = json.loads(ligne["reponse"])
    reponse["deja_recu"] = True
    return reponse


def garder_envoi(conn, *, id_envoi: str, machine_id: str, route: str, empreinte: str, requete: Any,
                 reponse: Dict[str, Any]) -> None:
    """Garde la réponse 2xx d'un envoi (sous sa propre transaction) et purge ceux de plus de 7 jours."""
    maintenant = base.maintenant()
    conservation = int(base.reglage(conn, "envois_conservation_s") or 7 * 24 * 3600)
    with base.transaction(conn):
        conn.execute("DELETE FROM envois WHERE recu_le < ?", (maintenant - conservation,))
        conn.execute("INSERT OR IGNORE INTO envois (id_envoi, machine_id, route, tableau, carte, run_id, empreinte, "
                     "statut, reponse, recu_le) VALUES (?, ?, ?, ?, ?, ?, ?, 200, ?, ?)",
                     (id_envoi, machine_id, route, requete.tableau, requete.carte, requete.run_id, empreinte,
                      json.dumps(reponse, ensure_ascii=False), maintenant))


# ------------------------------------------------------------------ carte émise et preuve de propriété


def _carte_emise(conn, kc, tableau: str, carte: str) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    """(fiche du projet, demande, tâche) d'une carte du poste émise par le greffon, ou le refus 404/403."""
    fiche = projets.projet(conn, tableau)
    demande = projets.demande_de_la_carte(conn, tableau, carte) if fiche else None
    tache = ka.get_task(kc, carte) if demande else None
    if fiche is None or demande is None or tache is None:
        raise RefusACP("carte_inconnue", T.CARTE_INCONNUE_MACHINE.format(c=carte, t=tableau))
    if (demande["role"] not in ROLES_SERVIS or demande["voie"] == "hermes"
            or etrangeres.demande_de_la_carte(conn, tableau, tache) is None):
        raise RefusACP("carte_non_emise", T.CARTE_NON_EMISE.format(c=carte))
    return fiche, demande, tache


def _a_nous(tache, machine_id: str, run_id: int) -> bool:
    return (tache is not None and tache.status == "running" and tache.claim_lock == claimer(machine_id)
            and tache.current_run_id is not None and int(tache.current_run_id) == int(run_id))


def _reclamation_perdue(carte: str, run_id: int) -> RefusACP:
    return RefusACP("reclamation_perdue", T.RECLAMATION_PERDUE.format(c=carte, n=run_id))


def _noter_demande(conn, demande: Dict[str, Any], **colonnes: Any) -> None:
    affectations = ", ".join(f"{nom} = ?" for nom in colonnes)
    with base.transaction(conn):
        conn.execute(f"UPDATE demandes SET {affectations} WHERE cle = ?", (*colonnes.values(), demande["cle"]))


# ------------------------------------------------------------------ voies fermées (cahier P6 § 4.3, § 6.1)
#
# Le calcul vit dans le routage (routage.voies_fermees : dernier inventaire du poste actif) ; ici, la carte prête
# d'une voie fermée.

voies_fermees = routage.voies_fermees
dernier_inventaire = routage.dernier_inventaire


def signaler_voies_fermees(conn) -> List[str]:
    """Passe de l'émetteur (cahier P6 § 4.3) : une carte PRÊTE dont la voie est fermée n'est jamais réassignée en
    silence ; elle est notée « en attente d'une voie fermée » (page Poste) et, au-delà de ``voie_fermee_delai_s``
    (30 min), bloquée avec la raison (notification « bloquée », décision du propriétaire). Rend les cartes bloquées."""
    fermees = voies_fermees(conn)
    maintenant = base.maintenant()
    delai = int(base.reglage(conn, "voie_fermee_delai_s") or 1800)
    vues: set = set()
    bloquees: List[str] = []
    if fermees:
        for fiche in [base.ligne_en_dict(l) for l in conn.execute("SELECT * FROM projets WHERE etat = 'actif'")]:
            try:
                with ka.connexion(fiche["tableau"]) as kc:
                    for tache in ka.list_tasks(kc, status="ready"):
                        if tache.assignee not in fermees:
                            continue
                        demande = etrangeres.demande_de_la_carte(conn, fiche["tableau"], tache)
                        if demande is None:
                            continue
                        vues.add(demande["cle"])
                        depuis = demande.get("voie_fermee_depuis")
                        if depuis is None:
                            _noter_demande(conn, demande, voie_fermee_depuis=maintenant)
                        elif maintenant - int(depuis) >= delai:
                            raison = T.RAISON_VOIE_FERMEE_CARTE.format(v=tache.assignee, n=delai // 60,
                                                                       raison=fermees[tache.assignee])
                            if ka.block_task(kc, tache.id, kind="capability", reason=raison[:500]):
                                bloquees.append(tache.id)
                                _noter_demande(conn, demande, voie_fermee_depuis=None)
                                with base.transaction(conn):
                                    base.journaliser(conn, "acp-poste:emetteur", "carte_voie_fermee",
                                                     projet_id=fiche["id"], cible=tache.id,
                                                     detail={"voie": tache.assignee})
            except Exception:  # noqa: BLE001 — un tableau illisible n'arrête pas la passe
                continue
    with base.transaction(conn):
        for (cle,) in conn.execute("SELECT cle FROM demandes WHERE voie_fermee_depuis IS NOT NULL").fetchall():
            if cle not in vues:
                conn.execute("UPDATE demandes SET voie_fermee_depuis = NULL WHERE cle = ?", (cle,))
    return bloquees


def cartes_en_attente_de_voie(conn) -> List[Dict[str, Any]]:
    """Page Poste : cartes prêtes d'une voie fermée, avec la raison et depuis quand (jamais réassignées)."""
    fermees = voies_fermees(conn)
    return [{"projet": l["projet_id"], "tableau": l["tableau"], "carte": l["carte"], "voie": l["voie"],
             "titre": l["titre"], "depuis": l["voie_fermee_depuis"], "raison": fermees.get(l["voie"])}
            for l in conn.execute("SELECT * FROM demandes WHERE voie_fermee_depuis IS NOT NULL ORDER BY "
                                  "voie_fermee_depuis").fetchall()]


# ------------------------------------------------------------------ sélection et réclamation (reclamer, § 5.2)


def _controle_quadruplet(conn, fiche: Dict[str, Any], demande: Dict[str, Any]) -> Optional[str]:
    """Double contrôle de la demande contre le DERNIER relevé et la politique publiée (P5 § 12.4). Rend la raison
    d'un écart DURABLE (modèle retiré du relevé, effort ou palier refusé, interdit par la politique), sinon None.
    Une voie indisponible ou un quota haut ne sont pas des écarts durables : la carte attend (rien n'est bloqué)."""
    if demande["voie"] == VOIE_INTEGRATION:
        if demande["modele"] is not None or demande["effort"] is not None:
            return T.INTEGRATION_SANS_MODELE
        return None if branches_a_integrer(conn, fiche) else T.INTEGRATION_SANS_BRANCHE
    dernier = routage.dernier_releve(conn, demande["voie"])
    if dernier is None:
        return None
    releve_id, releve, releve_le = dernier
    if releve.etat not in (None, "ok"):
        return None
    fiche_modele = releve.modele(demande["modele"] or "")
    if fiche_modele is None:
        return T.MODELE_ABSENT.format(m=demande["modele"], v=demande["voie"], date=routage.date_lisible(releve_le))
    interdits = list(base.reglage(conn, "efforts_interdits") or [])
    paliers = list(base.reglage(conn, "paliers_admis") or [])
    effort, palier = demande["effort"], demande["palier"] or routage.PALIER_PAR_DEFAUT
    if effort and effort in interdits:
        return T.EFFORT_INTERDIT.format(e=effort)
    if palier not in paliers:
        return T.PALIER_INTERDIT.format(p=palier)
    if effort and fiche_modele.supportedReasoningEfforts is not None and effort not in fiche_modele.supportedReasoningEfforts:
        return T.EFFORT_NON_PRIS.format(e=effort, m=demande["modele"], efforts=T.liste(
            fiche_modele.supportedReasoningEfforts))
    try:
        routage.verifier_politique_du_poste(routage.contexte_poste(conn, releve_id), demande["voie"],
                                            demande["modele"], effort, palier)
    except RefusACP as exc:
        return exc.message.removeprefix(T.PREFIXE_REFUS)
    return None


def _parents(conn, kc, fiche: Dict[str, Any], carte: str) -> List[Dict[str, Any]]:
    ids = list(ka.parent_ids(kc, carte))[:PARENTS_MAX]
    resumes = ka.latest_summaries(kc, ids) if ids else {}
    resultat = []
    for parent in ids:
        demande = projets.demande_de_la_carte(conn, fiche["tableau"], parent)
        if demande is None:
            continue
        texte = ka.masquer(resumes.get(parent)) if resumes.get(parent) else None
        resultat.append({"carte": parent, "role": demande["role"],
                         "resume": texte[:RESUME_PARENT_MAX] if texte else None,
                         "tronque": bool(texte) and len(texte) > RESUME_PARENT_MAX,
                         "branche": f"hermes/{parent}" if demande["role"] in ROLES_A_BRANCHE else None,
                         "_cree_le": demande["cree_le"]})
    return resultat


def _demande_par_cle(conn, cle: Optional[str]) -> Optional[Dict[str, Any]]:
    if not cle:
        return None
    return base.ligne_en_dict(conn.execute("SELECT * FROM demandes WHERE cle = ?", (cle,)).fetchone())


def branche_projet(fiche: Dict[str, Any]) -> str:
    """``hermes/projet-<slug>`` : le tableau sans son préfixe ``acp-`` (slug kanban : minuscules, chiffres, tirets)."""
    slug = str(fiche["tableau"]).removeprefix("acp-").replace("_", "-").strip("-")[:62].strip("-") or "projet"
    branche = f"hermes/projet-{slug}"
    return branche if BRANCHE_PROJET.fullmatch(branche) else "hermes/projet-acp"


def branches_a_integrer(conn, fiche: Dict[str, Any]) -> List[str]:
    """Branches des cartes ``done`` du projet qui ont committé (implémentations et corrections de TOUS les tours),
    dans l'ordre du graphe (tour, création) ; une branche déjà contenue sera sans effet côté exécutant. Seules les
    branches RAPPORTÉES par l'exécutant (``terminer`` : ``demandes.branche``) comptent : une carte terminée hors de lui
    (poste simulé des tests de P4) n'a aucune branche sur son volume."""
    branches: List[str] = []
    lignes = [base.ligne_en_dict(l) for l in conn.execute(
        "SELECT * FROM demandes WHERE projet_id = ? AND role IN ('implementation', 'correction') AND carte IS NOT NULL "
        "AND branche IS NOT NULL ORDER BY tour, cree_le, rowid", (fiche["id"],))]
    if not lignes:
        return []
    with ka.connexion(fiche["tableau"]) as kc:
        for ligne in lignes:
            tache = ka.get_task(kc, ligne["carte"])
            if tache is not None and tache.status == "done":
                branche = ligne["branche"]
                if branche not in branches and not BRANCHE_PROJET.fullmatch(branche):
                    branches.append(branche)
    return branches[:64]


def _branche_depart(conn, demande: Dict[str, Any], parents: List[Dict[str, Any]]) -> Optional[str]:
    """Branche locale dont part la carte : pour une correction, celle de la carte que sa relecture a relue ; sinon la
    plus récente des cartes parentes qui ont committé ; ``None`` : la branche de base de la politique."""
    if demande["role"] == "correction":
        relecture = _demande_par_cle(conn, demande["carte_relue"])
        relue = _demande_par_cle(conn, (relecture or {}).get("carte_relue"))
        if relue and relue.get("carte"):
            return f"hermes/{relue['carte']}"
    if demande["role"] in ("relecture", "integration", "exploration"):
        return None
    avec_branche = sorted((p for p in parents if p["branche"]), key=lambda p: p["_cree_le"])
    return avec_branche[-1]["branche"] if avec_branche else None


def _reponses_a_livrer(conn, demande: Dict[str, Any], tableau: str, carte: str) -> List[Dict[str, Any]]:
    reponses = [{"genre": "question", "question": q["id"], "texte": ka.masquer(q["reponse"])[:4000],
                 "repondu_par": q["repondu_par"], "le": _iso(q["repondue_le"])}
                for q in conn.execute("SELECT * FROM questions WHERE tableau = ? AND carte = ? AND etat = 'repondue' "
                                      "AND livree_le IS NULL AND reponse IS NOT NULL ORDER BY repondue_le, id",
                                      (tableau, carte)).fetchall()]
    if demande.get("revue_refusee_le") and not demande.get("refus_livre_le") and demande.get("motif_refus"):
        reponses.append({"genre": "refus_revue", "question": None,
                         "texte": T.CONSIGNE_REFUS_REVUE.format(
                             motif=ka.masquer(demande["motif_refus"]).rstrip(" .!"))[:4000],
                         "repondu_par": "proprietaire", "le": _iso(demande["revue_refusee_le"])})
    return reponses[-8:]


def _iso(epoch: Optional[int]) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(int(epoch or 0), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def construire_carte(conn, kc, fiche: Dict[str, Any], demande: Dict[str, Any], tache, machine_id: str) -> Dict[str, Any]:
    """Demande de carte (contrat ``DemandeCarte``) : la demande enregistrée fait foi ; résumés des parents tronqués à
    2 000 caractères, puis réduits (et la consigne en dernier, avec la mention) jusqu'à tenir dans 60 Kio."""
    parents = _parents(conn, kc, fiche, tache.id)
    integration = demande["role"] == "integration"
    carte_relue = None
    if demande["role"] == "relecture":
        relue = _demande_par_cle(conn, demande["carte_relue"])
        carte_relue = (relue or {}).get("carte")
    carte = {
        "tableau": fiche["tableau"], "carte": tache.id, "run_id": int(tache.current_run_id),
        "projet_id": fiche["id"], "role": demande["role"], "voie": demande["voie"],
        "modele": None if integration else demande["modele"],
        "effort": None if integration else demande["effort"],
        "palier": None if integration else (demande["palier"] or routage.PALIER_PAR_DEFAUT),
        "depot_alias": demande["depot_alias"] or fiche["depot_alias"], "branche_base": None,
        "branche": branche_projet(fiche) if integration else f"hermes/{tache.id}",
        "branche_depart": _branche_depart(conn, demande, parents),
        "consigne": ka.masquer(demande["consigne"]), "consigne_tronquee": False,
        "parents": [{k: v for k, v in p.items() if not k.startswith("_")} for p in parents],
        "carte_relue": carte_relue, "correction_n": int(demande["correction_n"] or 0),
        "branches_a_integrer": branches_a_integrer(conn, fiche) if integration else [],
        "duree_max_s": max(60, min(86_400, int(demande["duree_max"] or 3600))),
        "ttl_s": int(base.reglage(conn, "reclamation_ttl_s") or 2700),
        "reponses": _reponses_a_livrer(conn, demande, fiche["tableau"], tache.id),
        "reprise": demande.get("machine_id") == machine_id and (demande.get("issue") or "") in ISSUES_REPRISE,
    }
    for borne in (1000, 500, 200, 0):
        if taille_json(carte) <= TAILLE_MAX_CARTE:
            break
        for parent in carte["parents"]:
            if parent["resume"] and len(parent["resume"]) > borne:
                parent["resume"], parent["tronque"] = (parent["resume"][:borne] or None), True
    consigne = carte["consigne"]
    while taille_json(carte) > TAILLE_MAX_CARTE and len(consigne) > 200:
        # Un caractère pèse au moins un octet : retirer l'excédent en caractères suffit, à la mention près.
        excedent = taille_json(carte) - TAILLE_MAX_CARTE
        consigne = consigne[:max(200, len(consigne) - excedent - len(T.MENTION_TRONQUE.encode("utf-8")) - 16)]
        carte["consigne"], carte["consigne_tronquee"] = consigne + T.MENTION_TRONQUE, True
    # Au-delà (réponses démesurées), le contrat refuse la carte : elle est alors bloquée, jamais servie tronquée en
    # silence (_reclamer_une).
    return DemandeCarte.model_validate(carte).model_dump(mode="json")


def _candidates(conn, voies: List[str]) -> List[Tuple[int, int, str, str]]:
    """(priorité, création, tableau, carte) des cartes prêtes des projets ACTIFS assignées à une voie annoncée."""
    resultat = []
    for fiche in conn.execute("SELECT tableau FROM projets WHERE etat = 'actif' ORDER BY cree_le").fetchall():
        try:
            with ka.connexion(fiche["tableau"]) as kc:
                for tache in ka.list_tasks(kc, status="ready"):
                    if tache.assignee in voies:
                        resultat.append((int(tache.priority or 0), int(tache.created_at or 0), fiche["tableau"],
                                         tache.id))
        except Exception:  # noqa: BLE001 — un tableau illisible n'empêche pas de servir les autres
            continue
    resultat.sort(key=lambda c: (-c[0], c[1]))
    return resultat


def _reclamer_une(conn, machine_id: str, tableau: str, carte: str, ttl: int) -> Optional[Dict[str, Any]]:
    """Contrôle, réclame et construit UNE carte ; ``None`` si elle n'est plus réclamable. Toute erreur après la
    réclamation la rend aussitôt (``reclaim_task``) : jamais une carte retenue sans exécutant."""
    fiche = projets.projet(conn, tableau)
    with ka.connexion(tableau) as kc:
        tache = ka.get_task(kc, carte)
        demande = etrangeres.demande_de_la_carte(conn, tableau, tache) if tache is not None else None
        if fiche is None or fiche["etat"] != "actif" or demande is None or demande["role"] not in ROLES_SERVIS:
            return None
        ecart = _controle_quadruplet(conn, fiche, demande)
        if ecart is not None:
            if ka.block_task(kc, carte, kind="capability", reason=T.RAISON_ECART_QUADRUPLET.format(raison=ecart)[:500]):
                with base.transaction(conn):
                    base.journaliser(conn, f"poste:{machine_id}", "carte_bloquee_ecart", projet_id=fiche["id"],
                                     cible=carte, detail=ecart)
            return None
        reclamee = ka.claim_task(kc, carte, ttl_seconds=ttl, claimer=claimer(machine_id))
        if reclamee is None:
            return None
        try:
            servie = construire_carte(conn, kc, fiche, demande, reclamee, machine_id)
        except Exception as exc:  # noqa: BLE001 — rendue puis bloquée : jamais servie en boucle, jamais retenue
            ka.reclaim_task(kc, carte, reason="acp-poste : carte non construite")
            ka.block_task(kc, carte, kind="capability", reason=T.RAISON_CARTE_NON_CONSTRUITE.format(
                type=type(exc).__name__)[:500])
            with base.transaction(conn):
                base.journaliser(conn, f"poste:{machine_id}", "carte_non_construite", projet_id=fiche["id"],
                                 cible=carte, detail=type(exc).__name__)
            return None
    with base.transaction(conn):
        conn.execute("UPDATE demandes SET machine_id = ?, reclamee_le = ?, voie_fermee_depuis = NULL WHERE cle = ?",
                     (machine_id, base.maintenant(), demande["cle"]))
        base.journaliser(conn, f"poste:{machine_id}", "carte_servie", projet_id=fiche["id"], cible=carte,
                         detail={"run": servie["run_id"], "role": servie["role"], "voie": servie["voie"],
                                 "reprise": servie["reprise"]})
    return servie


def noter_reclamation(conn, machine_id: str, requete) -> None:
    """Ce que l'exécutant a annoncé (page Poste), SOUS la transaction de l'appelant."""
    conn.execute("UPDATE machines SET peut_executer = ?, voies_disponibles = ?, carte_en_cours = ?, "
                 "espace_libre_mio = ? WHERE id = ?",
                 (1 if requete.peut_executer else 0, json.dumps(list(requete.voies_disponibles)),
                  _json(requete.carte_en_cours.model_dump(mode="json")) if requete.carte_en_cours else None,
                  requete.espace_libre_mio, machine_id))


def servir(machine_id: str, requete) -> Optional[Dict[str, Any]]:
    """Carte à servir à cet exécutant, réclamée pour lui (``claim_task(ttl_seconds=2700,
    claimer="acp-poste:<machine>")``), ou ``None``. Rien sans ``peut_executer``, sans voie annoncée, en pause générale,
    pour une machine non active, ni tant que l'exécutant a une carte en main (concurrence 1) — sauf la carte qu'il
    vient de rendre (``reprendre``), resservie en priorité."""
    if not requete.peut_executer or not requete.voies_disponibles:
        return None
    if ka.get_state() is not None:
        return None
    with _verrou, base.connexion() as conn:
        machine = conn.execute("SELECT etat FROM machines WHERE id = ?", (machine_id,)).fetchone()
        if machine is None or machine["etat"] != "actif" or base.reglage(conn, "pause_reclamations"):
            return None
        ttl = int(base.reglage(conn, "reclamation_ttl_s") or 2700)
        voies = list(requete.voies_disponibles)
        en_cours = requete.carte_en_cours
        if en_cours is not None:
            demande = projets.demande_de_la_carte(conn, en_cours.tableau, en_cours.carte)
            if demande is None or demande.get("machine_id") != machine_id or demande["voie"] not in voies:
                return None
            try:
                with ka.connexion(en_cours.tableau) as kc:
                    tache = ka.get_task(kc, en_cours.carte)
            except Exception:  # noqa: BLE001
                return None
            if tache is None or tache.status != "ready":
                return None  # encore en main (running) ou finie : rien d'autre n'est servi
            return _reclamer_une(conn, machine_id, en_cours.tableau, en_cours.carte, ttl)
        for _priorite, _cree, tableau, carte in _candidates(conn, voies):
            servie = _reclamer_une(conn, machine_id, tableau, carte, ttl)
            if servie is not None:
                return servie
    return None


# ------------------------------------------------------------------ battement (§ 5.3)


def battement(machine_id: str, requete) -> Dict[str, Any]:
    """Prolonge la réclamation et note le battement ; ``valide: false`` si la carte n'est plus à cet exécutant,
    ``annuler: true`` si son projet n'est plus actif (pause, fin). Livre les réponses envoyées avec la carte."""
    with _verrou, base.connexion() as conn:
        with ka.connexion(requete.tableau) as kc:
            fiche, demande, tache = _carte_emise(conn, kc, requete.tableau, requete.carte)
            pause = bool(base.reglage(conn, "pause_reclamations")) or ka.get_state() is not None
            if not _a_nous(tache, machine_id, requete.run_id):
                return {"valide": False, "pause": pause, "annuler": False}
            ttl = int(base.reglage(conn, "reclamation_ttl_s") or 2700)
            if not ka.heartbeat_claim(kc, requete.carte, ttl_seconds=ttl, claimer=claimer(machine_id)):
                return {"valide": False, "pause": pause, "annuler": False}
            ka.heartbeat_worker(kc, requete.carte, note=ka.masquer(requete.note)[:500], expected_run_id=requete.run_id)
        maintenant = base.maintenant()
        with base.transaction(conn):
            from . import presence

            presence.enregistrer_dans(conn, machine_id, "battement")
            # Réponses servies avec la carte : livrées au premier battement de ce run.
            conn.execute("UPDATE questions SET livree_le = ? WHERE tableau = ? AND carte = ? AND etat = 'repondue' "
                         "AND livree_le IS NULL AND repondue_le <= ?",
                         (maintenant, requete.tableau, requete.carte, demande.get("reclamee_le") or maintenant))
            conn.execute("UPDATE demandes SET refus_livre_le = ? WHERE cle = ? AND revue_refusee_le IS NOT NULL AND "
                         "refus_livre_le IS NULL AND revue_refusee_le <= ?",
                         (maintenant, demande["cle"], demande.get("reclamee_le") or maintenant))
        return {"valide": True, "pause": pause, "annuler": fiche["etat"] != "actif"}


# ------------------------------------------------------------------ terminer (§ 5.4)


def _verifier_issue(demande: Dict[str, Any], requete) -> None:
    role = demande["role"]
    if requete.verdict is not None and role != "relecture":
        raise RefusACP("issue_invalide", T.ISSUE_INVALIDE.format(chemin="verdict", raison=T.VERDICT_RESERVE))
    if role == "relecture" and requete.verdict is None:
        raise RefusACP("issue_invalide", T.ISSUE_INVALIDE.format(chemin="verdict", raison=T.VERDICT_EXIGE))
    branche = requete.metadonnees.branche
    if (role == "integration") != bool(BRANCHE_PROJET.fullmatch(branche)):
        raise RefusACP("issue_invalide", T.ISSUE_INVALIDE.format(chemin="metadonnees.branche",
                                                                  raison=T.BRANCHE_INATTENDUE))


def terminer(machine_id: str, requete) -> Dict[str, Any]:
    """Issue d'une carte, dans l'ordre du cahier : enregistrement ; fichiers de pilotage touchés → revue
    (``request_review``) ; relecture avec corrections → ``graphe.inserer_correction`` (correction, lien, puis
    ``complete_task`` de la relecture) ; sinon ``complete_task`` avec preuve de propriété."""
    with _verrou, base.connexion() as conn:
        with ka.connexion(requete.tableau) as kc:
            fiche, demande, tache = _carte_emise(conn, kc, requete.tableau, requete.carte)
            if not _a_nous(tache, machine_id, requete.run_id):
                raise _reclamation_perdue(requete.carte, requete.run_id)
        _verifier_issue(demande, requete)
        meta = requete.metadonnees
        metadonnees = meta.model_dump(mode="json")
        resume = ka.masquer(requete.resume)
        # Ce que l'exécutant a observé, enregistré APRÈS l'effet seulement (un refus ne laisse aucune trace).
        observation = dict(
            modele_servi=meta.modele_servi, palier_servi=meta.palier_servi,
            observe_le=base.maintenant() if meta.modele_servi else demande.get("observe_le"),
            branche=meta.branche, tete=meta.tete, session_locale=1 if meta.session_locale else 0,
            verification=_json(meta.verification.model_dump(mode="json")) if meta.verification else None,
            pilotage=_json(meta.pilotage.model_dump(mode="json")),
            diffstat=_json(meta.diffstat.model_dump(mode="json")) if meta.diffstat else None)
        if meta.pilotage.touche:
            with ka.connexion(requete.tableau) as kc:
                fait = ka.request_review(kc, requete.carte, summary=resume, metadata=metadonnees,
                                         expected_run_id=requete.run_id)
            if not fait:
                raise _reclamation_perdue(requete.carte, requete.run_id)
            _noter_demande(conn, demande, issue="revue", revue_refusee_le=None, motif_refus=None, refus_livre_le=None,
                           **observation)
            _journal(conn, machine_id, fiche, requete.carte, "carte_en_revue", {"chemins": meta.pilotage.chemins[:10]})
            return {"etat": "review", "deja_recu": False}
        if demande["role"] == "relecture" and requete.verdict == "corrections":
            try:
                resultat = graphe.inserer_correction(conn, tableau=requete.tableau, carte_relecture=requete.carte,
                                                     run_id_relecture=requete.run_id,
                                                     consigne=ka.masquer(requete.corrections))
            except RefusACP as exc:
                if exc.code not in ("plafond_corrections", "plafond_cartes"):
                    raise
                # Plafond : la carte de décision est adressée (graphe) ; la relecture se termine avec son verdict.
                resultat = None
            if resultat is not None:
                if not resultat.get("relecture_terminee"):
                    raise _reclamation_perdue(requete.carte, requete.run_id)
                _noter_demande(conn, demande, issue="correction", **observation)
                _journal(conn, machine_id, fiche, requete.carte, "correction_creee",
                         {"correction": resultat["correction"], "n": resultat["n"]})
                return {"etat": "correction_creee", "deja_recu": False}
        texte = resume if requete.verdict is None else f"{T.VERDICTS[requete.verdict]}\n\n{resume}"
        if requete.verdict == "corrections":
            texte += "\n\n" + T.CORRECTIONS_DEMANDEES.format(corrections=ka.masquer(requete.corrections))
        with ka.connexion(requete.tableau) as kc:
            fait = ka.complete_task(kc, requete.carte, summary=texte[:8000], metadata=metadonnees,
                                    expected_run_id=requete.run_id)
        if not fait:
            raise _reclamation_perdue(requete.carte, requete.run_id)
        _noter_demande(conn, demande, issue="termine", **observation)
        _journal(conn, machine_id, fiche, requete.carte, "carte_terminee",
                 {"verification": (meta.verification.etat if meta.verification else None), "role": demande["role"]})
        return {"etat": "done", "deja_recu": False}


def _journal(conn, machine_id: str, fiche: Dict[str, Any], carte: str, action: str, detail: Any = None) -> None:
    with base.transaction(conn):
        base.journaliser(conn, f"poste:{machine_id}", action, projet_id=fiche["id"], cible=carte, detail=detail)


# ------------------------------------------------------------------ question (§ 5.5)


def question(machine_id: str, requete) -> Dict[str, Any]:
    """``questions.poser`` de P4, inchangé : question enregistrée, ``schedule_task(expected_run_id)``, puis carte
    « répondre » ou escalade."""
    with _verrou, base.connexion() as conn:
        with ka.connexion(requete.tableau) as kc:
            fiche, demande, tache = _carte_emise(conn, kc, requete.tableau, requete.carte)
            if not _a_nous(tache, machine_id, requete.run_id):
                raise _reclamation_perdue(requete.carte, requete.run_id)
        resultat = questions.poser(conn, tableau=requete.tableau, carte=requete.carte, run_id=requete.run_id,
                                   texte=ka.masquer(requete.texte),
                                   contexte=ka.masquer(requete.contexte) if requete.contexte else None)
        _noter_demande(conn, demande, issue="question", session_locale=1)
        return {"question": resultat["question"], "etat": resultat["etat"],
                "carte_repondre": resultat.get("carte_repondre"), "deja_recu": False}


# ------------------------------------------------------------------ bloquer (§ 5.6)


def bloquer(machine_id: str, requete) -> Dict[str, Any]:
    """``quota`` → ``schedule_task`` et une attente (déblocage à l'heure de remise à zéro par l'émetteur) ;
    ``secret`` → ``block_task(needs_input)`` à raison FIXE ; tout autre genre → ``block_task(capability)``. Au second
    blocage du même genre après un déblocage, Hermes envoie la carte en triage (``BLOCK_RECURRENCE_LIMIT``)."""
    with _verrou, base.connexion() as conn:
        with ka.connexion(requete.tableau) as kc:
            fiche, demande, tache = _carte_emise(conn, kc, requete.tableau, requete.carte)
            if not _a_nous(tache, machine_id, requete.run_id):
                raise _reclamation_perdue(requete.carte, requete.run_id)
            raison = ka.masquer(requete.raison)[:400]
            if requete.genre == "quota":
                reprise = (int(requete.reprise_le.timestamp()) if requete.reprise_le is not None
                           else base.maintenant() + 3600)
                fait = ka.schedule_task(kc, requete.carte, reason=T.RAISON_QUOTA_ATTENTE.format(
                    heure=routage.date_lisible(reprise), raison=raison)[:500], expected_run_id=requete.run_id)
            elif requete.genre == "secret":
                fait = ka.block_task(kc, requete.carte, kind="needs_input", reason=T.RAISON_SECRET_EXECUTANT,
                                     expected_run_id=requete.run_id)
            else:
                fait = ka.block_task(kc, requete.carte, kind="capability",
                                     reason=T.RAISON_BLOCAGE_EXECUTANT.format(genre=T.GENRES_BLOCAGE[requete.genre],
                                                                              raison=raison)[:500],
                                     expected_run_id=requete.run_id)
            if not fait:
                raise _reclamation_perdue(requete.carte, requete.run_id)
            statut = getattr(ka.get_task(kc, requete.carte), "status", None)
        with base.transaction(conn):
            if requete.genre == "quota":
                conn.execute("INSERT INTO attentes (tableau, carte, motif, reprise_le, machine_id, raison, cree_le) "
                             "VALUES (?, ?, 'quota', ?, ?, ?, ?) ON CONFLICT(tableau, carte) DO UPDATE SET "
                             "reprise_le = excluded.reprise_le, machine_id = excluded.machine_id, "
                             "raison = excluded.raison, cree_le = excluded.cree_le",
                             (requete.tableau, requete.carte, reprise, machine_id, raison, base.maintenant()))
            conn.execute("UPDATE demandes SET issue = ?, session_locale = 1 WHERE cle = ?",
                         (f"bloquee:{requete.genre}", demande["cle"]))
            base.journaliser(conn, f"poste:{machine_id}", "carte_bloquee", projet_id=fiche["id"], cible=requete.carte,
                             detail={"genre": requete.genre, "statut": statut})
        etat = {"scheduled": "planifiee", "triage": "triage"}.get(statut or "", "bloquee")
        return {"etat": etat, "deja_recu": False}


# ------------------------------------------------------------------ reprendre et arret (§ 5.7, § 5.8)


def _rendre(machine_id: str, requete, *, issue: str, motif: str) -> Dict[str, Any]:
    with _verrou, base.connexion() as conn:
        with ka.connexion(requete.tableau) as kc:
            fiche, demande, tache = _carte_emise(conn, kc, requete.tableau, requete.carte)
            if not _a_nous(tache, machine_id, requete.run_id):
                return {"etat": "deja_libre", "deja_recu": False}
            # Réclamation distante : worker_pid nul et verrou hors du préfixe d'hôte de Hermes ; aucun processus de
            # Hermes n'est visé (kanban_db_dispatch.py:463-466).
            fait = ka.reclaim_task(kc, requete.carte, reason=f"acp-poste : {motif}")
        if not fait:
            return {"etat": "deja_libre", "deja_recu": False}
        _noter_demande(conn, demande, issue=issue, session_locale=1)
        _journal(conn, machine_id, fiche, requete.carte, "carte_rendue", {"motif": motif})
        return {"etat": "rendue", "deja_recu": False}


def reprendre(machine_id: str, requete) -> Dict[str, Any]:
    return _rendre(machine_id, requete, issue="rendue", motif=requete.motif)


def arret(machine_id: str, requete) -> Dict[str, Any]:
    """Comme ``reprendre`` ; la présence note en plus un arrêt propre (grâce de la notification « hors ligne »)."""
    resultat = _rendre(machine_id, requete, issue="arret", motif=requete.motif)
    with base.connexion() as conn:
        with base.transaction(conn):
            conn.execute("UPDATE presence SET arret_propre_le = ? WHERE machine_id = ?", (base.maintenant(), machine_id))
    return resultat


# ------------------------------------------------------------------ revues des fichiers de pilotage (§ 5.4)


def _revue(conn, kc, tableau: str, carte: str) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    fiche = projets.projet(conn, tableau)
    demande = projets.demande_de_la_carte(conn, tableau, carte) if fiche else None
    tache = ka.get_task(kc, carte) if demande else None
    if (fiche is None or demande is None or tache is None or demande["issue"] != "revue"
            or etrangeres.demande_de_la_carte(conn, tableau, tache) is None):
        raise RefusACP("revue_inconnue", T.PREFIXE_REFUS + T.REVUE_INCONNUE.format(c=carte[:40], t=tableau[:64]))
    if tache.status != "review":
        raise RefusACP("revue_changee", T.PREFIXE_REFUS + T.REVUE_CHANGEE.format(c=carte, s=tache.status))
    return fiche, demande, tache


def accepter_revue(conn, *, tableau: str, carte: str, auteur: str) -> Dict[str, Any]:
    """« Accepter » : ``complete_task`` SANS preuve de run (``review → done`` ; ``request_review`` a clos le run). Le
    résumé de l'exécutant est repris, suivi de la mention de l'acceptation : la synthèse le lit tel quel."""
    with _verrou:
        with ka.connexion(tableau) as kc:
            fiche, demande, _tache = _revue(conn, kc, tableau, carte)
            resume = ka.latest_summaries(kc, [carte]).get(carte) or ""
            texte = (resume + "\n\n" if resume else "") + T.REVUE_ACCEPTEE
            fait = ka.complete_task(kc, carte, summary=texte[:8000], metadata={"revue_pilotage": "acceptee"})
        if not fait:
            raise RefusACP("revue_changee", T.PREFIXE_REFUS + T.REVUE_CHANGEE.format(c=carte, s="inconnu"))
        _noter_demande(conn, demande, issue="termine")
        with base.transaction(conn):
            base.journaliser(conn, auteur, "revue_acceptee", projet_id=fiche["id"], cible=carte)
    return {"carte": carte, "etat": "done"}


def refuser_revue(conn, *, tableau: str, carte: str, motif: Any, auteur: str) -> Dict[str, Any]:
    """« Refuser » : commentaire du motif (auteur ``acp-poste``), puis ``reopen_review_task`` (``review → ready`` ou
    ``todo``, implémenteur rétabli) ; au ``reclamer`` suivant, la carte revient à l'exécutant avec ``reprise`` et le
    motif dans ``reponses``. Jamais ``block_task`` : sans effet sur une carte en revue (kanban_db.py:3277-3283)."""
    from .motifs_secrets import motif_trouve

    if not isinstance(motif, str) or not 1 <= len(motif.strip()) <= 1000:
        raise RefusACP("motif", T.PREFIXE_REFUS + T.MOTIF_REFUS_REVUE)
    trouve = motif_trouve(motif)
    if trouve:
        raise RefusACP("secret", T.PREFIXE_REFUS + T.SECRET_TEXTE.format(motif=trouve))
    motif = motif.strip()
    with _verrou:
        with ka.connexion(tableau) as kc:
            fiche, demande, _tache = _revue(conn, kc, tableau, carte)
            ka.add_comment(kc, carte, ka.CREATEUR, T.COMMENTAIRE_REFUS_REVUE.format(motif=motif))
            fait = ka.reopen_review_task(kc, carte)
            statut = getattr(ka.get_task(kc, carte), "status", None)
        if not fait:
            raise RefusACP("revue_changee", T.PREFIXE_REFUS + T.REVUE_CHANGEE.format(c=carte, s=statut or T.INCONNU))
        _noter_demande(conn, demande, issue="revue_refusee", revue_refusee_le=base.maintenant(),
                       motif_refus=ka.masquer(motif)[:1000], refus_livre_le=None)
        with base.transaction(conn):
            base.journaliser(conn, auteur, "revue_refusee", projet_id=fiche["id"], cible=carte, detail=motif)
    return {"carte": carte, "etat": statut}


def revues_en_cours(conn) -> List[Dict[str, Any]]:
    """Cartes en revue pour fichiers de pilotage (onglet Questions) : chemins, diffstat, résumé ; le diff lui-même
    reste sur l'exécutant (jamais un faux aperçu)."""
    revues = []
    for d in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT d.*, p.titre AS projet_titre FROM demandes d JOIN projets p ON p.id = d.projet_id "
            "WHERE d.issue = 'revue' AND d.carte IS NOT NULL ORDER BY d.reclamee_le, d.rowid").fetchall()]:
        try:
            with ka.connexion(d["tableau"]) as kc:
                tache = ka.get_task(kc, d["carte"])
                resume = ka.latest_summaries(kc, [d["carte"]]).get(d["carte"]) if tache is not None else None
        except Exception:  # noqa: BLE001 — tableau illisible : la revue n'est pas listée, jamais inventée
            continue
        if tache is None or tache.status != "review":
            continue
        try:
            pilotage = json.loads(d["pilotage"]) if d["pilotage"] else {}
            diffstat = json.loads(d["diffstat"]) if d["diffstat"] else None
        except ValueError:
            pilotage, diffstat = {}, None
        revues.append({"projet": d["projet_id"], "projet_titre": d["projet_titre"], "tableau": d["tableau"],
                       "carte": d["carte"], "titre": ka.masquer(tache.title)[:200], "role": d["role"],
                       "voie": d["voie"], "chemins": [ka.masquer(c)[:300] for c in (pilotage.get("chemins") or [])],
                       "diffstat": diffstat, "branche": d["branche"], "tete": d["tete"],
                       "resume": (ka.masquer(resume)[:2000] or None) if resume else None,
                       "diff": T.DIFF_SUR_L_EXECUTANT})
    return revues


FONCTIONS: Dict[str, Callable[[str, Any], Dict[str, Any]]] = {
    "battement": battement, "terminer": terminer, "question": question, "bloquer": bloquer,
    "reprendre": reprendre, "arret": arret,
}


# ------------------------------------------------------------------ page Poste et /v1/meta (cahier P6 § 4.4, § 9.3)

COMMANDE_RECUPERATION = "railway ssh -i <clé dédiée> --service executant -- acp-poste bundle {alias} {branche}"


def _charger(texte: Optional[str]) -> Any:
    try:
        return json.loads(texte) if texte else None
    except ValueError:
        return None


def _carte_en_main(conn, machine: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Carte en main de l'exécutant : celle qu'il ANNONCE (dernière réclamation), décrite par la demande et la carte
    kanban (modèle demandé et servi, dernier battement) ; ``None`` s'il n'en annonce aucune."""
    annonce = _charger(machine.get("carte_en_cours"))
    if not isinstance(annonce, dict):
        return None
    demande = projets.demande_de_la_carte(conn, str(annonce.get("tableau")), str(annonce.get("carte")))
    fiche = projets.projet(conn, str(annonce.get("tableau"))) if demande else None
    resultat: Dict[str, Any] = {"tableau": annonce.get("tableau"), "carte": annonce.get("carte"),
                                "run_id": annonce.get("run_id"), "connue": demande is not None}
    if demande is None or fiche is None:
        return resultat
    tache = None
    try:
        with ka.connexion(fiche["tableau"]) as kc:
            tache = ka.get_task(kc, demande["carte"])
    except Exception:  # noqa: BLE001 — tableau illisible : statut inconnu, jamais inventé
        tache = None
    resultat.update(projet=fiche["id"], projet_titre=fiche["titre"], titre=demande["titre"], role=demande["role"],
                    voie=demande["voie"], modele_demande=demande["modele"], modele_servi=demande["modele_servi"],
                    effort=demande["effort"], statut=getattr(tache, "status", None),
                    dernier_battement=getattr(tache, "last_heartbeat_at", None),
                    a_nous=bool(tache is not None and tache.claim_lock == claimer(machine["id"])))
    return resultat


def branches_pretes(conn) -> List[Dict[str, Any]]:
    """Branches intégrées (cartes d'intégration terminées), avec la commande de récupération à copier (cahier P6
    § 12.2) ; aucun bouton « Pousser » (D82 : aucun identifiant d'écriture en P6)."""
    resultat = []
    for d in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT d.*, p.titre AS projet_titre FROM demandes d JOIN projets p ON p.id = d.projet_id WHERE "
            "d.role = 'integration' AND d.issue = 'termine' AND d.branche IS NOT NULL ORDER BY d.rowid DESC "
            "LIMIT 20").fetchall()]:
        fini = None
        try:
            with ka.connexion(d["tableau"]) as kc:
                fini = getattr(ka.get_task(kc, d["carte"]), "completed_at", None)
        except Exception:  # noqa: BLE001
            fini = None
        resultat.append({"projet": d["projet_id"], "projet_titre": d["projet_titre"], "depot": d["depot_alias"],
                         "branche": d["branche"], "tete": d["tete"], "termine_le": fini,
                         "commande": COMMANDE_RECUPERATION.format(alias=d["depot_alias"], branche=d["branche"])})
    return resultat


def vue_executant(conn) -> Dict[str, Any]:
    """Bloc ``executant`` de ``/v1/poste`` : plateforme, isolement MESURÉ (« inconnu » sans sonde), conditions
    d'usage, annonce de la dernière réclamation, voies fermées et cartes qui les attendent, carte en main, branches
    prêtes, revues en attente. Rien n'est inventé : sans inventaire, chaque bloc le dit."""
    from . import machines

    machine = machines.machine_courante(conn)
    if machine is None:
        return {"connu": False}
    inventaire = routage.dernier_inventaire(conn, machine["id"]) or {}
    politique = inventaire.get("politique") or {}
    voies = _charger(machine.get("voies_disponibles"))
    return {
        "connu": True,
        "plateforme": machine.get("plateforme") or "windows",
        "hote": machine.get("hote") or "pc",
        "noyau": (inventaire.get("poste") or {}).get("noyau"),
        "isolement": inventaire.get("isolement_linux"),
        "bac_a_sable_codex": inventaire.get("bac_a_sable_codex"),
        "conditions": politique.get("conditions") if "conditions" in politique else None,
        "bornes": {k: politique.get(k) for k in ("cartes_par_jour", "duree_max_carte_s", "concurrence")},
        "peut_executer": None if machine.get("peut_executer") is None else bool(machine["peut_executer"]),
        "voies_disponibles": voies if isinstance(voies, list) else None,
        "espace_libre_mio": machine.get("espace_libre_mio"),
        "voies_fermees": routage.voies_fermees(conn),
        # Étape P7 (cahier P7 § 11.2) : visibilité mesurée de chaque dépôt et voies fermées pour lui.
        "depots": routage.depots_du_poste(conn, inventaire),
        "cartes_en_attente_de_voie": cartes_en_attente_de_voie(conn),
        "carte_en_cours": _carte_en_main(conn, machine),
        "branches_pretes": branches_pretes(conn),
        "revues": len(revues_en_cours(conn)),
    }
