"""Graphe déterministe d'un projet (cahier P4 § 6) : planification d'un tour, corrections, triage.

Pour chaque étape d'un tour : implémentation (voie du poste) → relecture croisée (l'AUTRE voie) ;
ou carte Hermes (voie ``hermes``) ; puis UNE synthèse (Hermes) dont les parents sont TOUTES les
cartes du tour : elle ne part que quand tout le tour est fini (gating natif de Hermes).

Toutes les cartes d'un tour sont créées sous UNE transaction kanban externe : si une création lève,
rien n'est créé et la réservation est annulée. Plafonds vérifiés AVANT toute écriture (3 tours,
30 cartes, 2 corrections par défaut) ; un plafond de tours ou de corrections atteint, ou un plafond de
cartes qui ne laisse plus aucun plan possible, crée UNE carte de décision (triage) adressée au propriétaire.
Sa décision (décision D41) : « Prolonger » relève le plafond et laisse Hermes planifier la suite depuis cette
carte ; « Conclure » arrête le projet (:mod:`questions`, ``decider_triage``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import base, cartes, notifications, projets, routage
from . import kanban_adapter as ka
from . import textes as T
from .motifs_secrets import motif_trouve
from .textes import RefusACP, refus

REF = re.compile(r"^[a-z0-9][a-z0-9-]{0,15}$")
LIBELLES_CLASSE = {
    "architecture": "Architecture", "implementation": "Implémentation", "debogage_tests": "Débogage et tests",
    "documentation": "Documentation", "petite_tache": "Petite tâche", "recherche_web": "Recherche web",
    "integration": "Intégration",
}
CHAMPS_ETAPE = {"ref", "titre", "classe", "consigne", "voie", "modele", "effort", "relecture", "relecture_modele",
                "depend_de", "fichiers"}
VERROU_CATALOGUE = Path("/opt/acp/catalogue/catalogue.lock.json")


def _plan_invalide(detail: str) -> RefusACP:
    return refus("plan_invalide", T.PLAN_INVALIDE.format(detail=detail))


def valider_plan(resume: Any, decisions: Any, etapes: Any, *, maximum: int) -> Dict[str, Any]:
    """Validation PURE du plan (aucune base) : bornes, références, dépendances du même appel, absence de
    cycle (algorithme de Kahn), classes connues, textes sans motif de secret. Rend le plan normalisé
    (étapes en ordre topologique stable)."""
    if not isinstance(resume, str) or not 1 <= len(resume.strip()) <= 2000:
        raise _plan_invalide("le résumé doit compter de 1 à 2000 caractères")
    decisions = [] if decisions is None else decisions
    if not isinstance(decisions, list) or len(decisions) > 20:
        raise _plan_invalide("au plus 20 décisions")
    for d in decisions:
        if not isinstance(d, str) or not 1 <= len(d.strip()) <= 500:
            raise _plan_invalide("chaque décision doit compter de 1 à 500 caractères")
        motif = motif_trouve(d)
        if motif:
            raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
    if not isinstance(etapes, list) or not etapes:
        raise _plan_invalide("au moins une étape")
    if len(etapes) > maximum:
        raise _plan_invalide(f"plus de {maximum} étapes")
    refs: List[str] = []
    propres: List[Dict[str, Any]] = []
    for i, etape in enumerate(etapes, 1):
        if not isinstance(etape, dict):
            raise _plan_invalide(f"étape {i} : objet attendu")
        inconnus = sorted(set(etape) - CHAMPS_ETAPE)
        if inconnus:
            raise _plan_invalide(f"étape {i} : champ inconnu refusé ({', '.join(inconnus)})")
        ref = etape.get("ref")
        if not isinstance(ref, str) or not REF.match(ref):
            raise _plan_invalide(f"étape {i} : référence « {str(ref)[:20]} » invalide (^[a-z0-9][a-z0-9-]{{0,15}}$)")
        if ref in refs:
            raise _plan_invalide(f"références en double : {ref}")
        refs.append(ref)
        titre = etape.get("titre")
        if not isinstance(titre, str) or not 1 <= len(titre.strip()) <= 120:
            raise _plan_invalide(f"étape {ref} : le titre doit compter de 1 à 120 caractères")
        classe = etape.get("classe")
        if classe not in routage.CLASSES_ETAPE:
            raise _plan_invalide(f"étape {ref} : classe « {str(classe)[:30]} » inconnue")
        consigne = etape.get("consigne")
        if not isinstance(consigne, str) or not 1 <= len(consigne.strip()) <= 8000:
            raise _plan_invalide(f"étape {ref} : la consigne doit compter de 1 à 8000 caractères")
        for texte in (consigne, titre):
            motif = motif_trouve(texte)
            if motif:
                raise refus("secret", T.SECRET_CONSIGNE.format(ref=ref, motif=motif))
        depend = etape.get("depend_de") or []
        if not isinstance(depend, list) or not all(isinstance(x, str) for x in depend):
            raise _plan_invalide(f"étape {ref} : depend_de doit être une liste de références")
        for champ in ("voie", "modele", "effort", "relecture_modele"):
            if etape.get(champ) is not None and not isinstance(etape.get(champ), str):
                raise _plan_invalide(f"étape {ref} : « {champ} » doit être une chaîne")
        if etape.get("relecture") is not None and not isinstance(etape.get("relecture"), bool):
            raise _plan_invalide(f"étape {ref} : « relecture » doit être un booléen")
        fichiers = etape.get("fichiers") or []
        if not isinstance(fichiers, list) or len(fichiers) > 50 or not all(
                isinstance(f, str) and len(f) <= 300 for f in fichiers):
            raise _plan_invalide(f"étape {ref} : « fichiers » : au plus 50 chemins de 300 caractères")
        propres.append({"ref": ref, "titre": titre.strip(), "classe": classe, "consigne": consigne.strip(),
                        "voie": etape.get("voie") or None, "modele": etape.get("modele") or None,
                        "effort": etape.get("effort") or None, "relecture": etape.get("relecture") is not False,
                        "relecture_modele": etape.get("relecture_modele") or None,
                        "depend_de": list(dict.fromkeys(depend)), "fichiers": list(fichiers)})
    for etape in propres:
        for dep in etape["depend_de"]:
            if dep == etape["ref"]:
                raise _plan_invalide(f"étape {etape['ref']} : dépend d'elle-même")
            if dep not in refs:
                raise _plan_invalide(f"étape {etape['ref']} : dépend de « {dep} », inconnue")
    # Kahn : ordre topologique stable (ordre d'apparition), ou cycle.
    restants = {e["ref"]: set(e["depend_de"]) for e in propres}
    ordre: List[str] = []
    while restants:
        prets = [r for r in refs if r in restants and not restants[r]]
        if not prets:
            cycle = sorted(restants)
            raise _plan_invalide("cycle entre " + " et ".join(cycle[:2]) + (" …" if len(cycle) > 2 else ""))
        for r in prets:
            ordre.append(r)
            del restants[r]
            for deps in restants.values():
                deps.discard(r)
    par_ref = {e["ref"]: e for e in propres}
    return {"resume": resume.strip(), "decisions": [d.strip() for d in decisions],
            "etapes": [par_ref[r] for r in ordre]}


def empreinte(plan: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def competences_hermes(profil: str) -> List[str]:
    """Skills d'une carte Hermes : celles du profil « base » et du profil du projet (verrou du
    catalogue), plus acp-redaction. Verrou illisible : acp-redaction seule (jamais une invention)."""
    noms: List[str] = []
    try:
        profils = json.loads(VERROU_CATALOGUE.read_text(encoding="utf-8")).get("profils") or {}
        for nom in ("base", profil):
            noms += [s for s in (profils.get(nom) or {}).get("skills_hermes") or [] if isinstance(s, str)]
    except (OSError, ValueError):
        pass
    return list(dict.fromkeys([*noms, *projets.COMPETENCES_HERMES]))


def _cle(projet_id: str, tour: int, suffixe: str) -> str:
    return f"{ka.PREFIXE_CLE}{projet_id}:t{tour}:{suffixe}"


def _decisions_texte(decisions: Sequence[str]) -> str:
    return "\n".join(f"- {d}" for d in decisions) if decisions else "- (aucune)"


def composer(conn, fiche: Dict[str, Any], tour: int, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Résout chaque étape (refus exact au premier échec) puis compose les demandes du tour, dans
    l'ordre de création (parents d'abord), synthèse en dernier."""
    demandes: List[Dict[str, Any]] = []
    terminales: Dict[str, List[str]] = {}
    decisions = _decisions_texte(plan["decisions"])
    for e in plan["etapes"]:
        r = routage.resoudre(conn, classe=e["classe"], projet=fiche, voie=e["voie"], modele=e["modele"],
                             effort=e["effort"], ref=e["ref"])
        parents = [c for dep in e["depend_de"] for c in terminales[dep]]
        commun = dict(projet_id=fiche["id"], tableau=fiche["tableau"], classe=e["classe"], tour=tour, ref=e["ref"],
                      depot_alias=fiche["depot_alias"], consigne=e["consigne"])
        libelle = LIBELLES_CLASSE.get(e["classe"], e["classe"])
        if r.voie == "hermes":
            cle = _cle(fiche["id"], tour, f"{e['ref']}:hermes")
            demandes.append(dict(
                commun, cle=cle, role="hermes", voie="hermes", titre=f"{libelle} — {e['ref']} : {e['titre']}",
                modele=r.modele, effort=r.effort, palier=r.palier, modele_carte=r.modele, effort_carte=r.effort_carte,
                source_routage=r.source_routage, releve_id=r.releve_id, mention=r.mention, parents=parents,
                competences=competences_hermes(fiche["profil"]), duree_max=cartes.DUREE_HERMES_TRAVAIL,
                corps=T.CORPS_CARTE_HERMES.format(titre=fiche["titre"], r=tour, ref=e["ref"], classe=e["classe"],
                                                   consigne=e["consigne"], decisions=decisions)))
            terminales[e["ref"]] = [cle]
            continue
        cle_impl = _cle(fiche["id"], tour, f"{e['ref']}:implementation")
        demandes.append(dict(
            commun, cle=cle_impl, role="implementation", voie=r.voie, titre=f"{libelle} — {e['ref']} : {e['titre']}",
            modele=r.modele, effort=r.effort, palier=r.palier, modele_carte=r.modele, effort_carte=r.effort_carte,
            source_routage=r.source_routage, releve_id=r.releve_id, mention=r.mention, parents=parents,
            corps=T.CORPS_CARTE_POSTE.format(titre=fiche["titre"], r=tour, ref=e["ref"], classe=e["classe"], voie=r.voie,
                                             modele=r.modele, effort=r.effort or T.INCONNU, palier=r.palier,
                                             depot=fiche["depot_alias"], consigne=e["consigne"], decisions=decisions)))
        terminales[e["ref"]] = [cle_impl]
        if e["relecture"]:
            rr = routage.resoudre_relecture(conn, projet=fiche, voie_relue=r.voie, ref=e["ref"],
                                            modele=e["relecture_modele"])
            cle_rel = _cle(fiche["id"], tour, f"{e['ref']}:relecture")
            demandes.append(dict(
                commun, cle=cle_rel, role="relecture", classe="relecture", voie=rr.voie,
                titre=f"Relecture — {e['ref']} : {e['titre']}", modele=rr.modele, effort=rr.effort, palier=rr.palier,
                modele_carte=rr.modele, effort_carte=rr.effort_carte, source_routage=rr.source_routage,
                releve_id=rr.releve_id, mention=rr.mention, parents=[cle_impl], carte_relue=cle_impl,
                corps=T.CORPS_RELECTURE.format(titre=fiche["titre"], r=tour, ref=e["ref"], classe=e["classe"],
                                               voie=rr.voie, modele=rr.modele, effort=rr.effort or T.INCONNU,
                                               palier=rr.palier, depot=fiche["depot_alias"], relue=e["ref"],
                                               voie_relue=r.voie, consigne=e["consigne"])))
            terminales[e["ref"]].append(cle_rel)
    tout = [d["cle"] for d in demandes]
    demandes.append(dict(
        projet_id=fiche["id"], tableau=fiche["tableau"], cle=_cle(fiche["id"], tour, "synthese"), role="synthese",
        classe="synthese", voie="hermes", tour=tour, ref="synthese", titre=f"Synthèse du tour {tour} — {fiche['titre']}",
        modele=None, effort=None, palier="default", modele_carte=None, effort_carte=None, source_routage="profil",
        depot_alias=fiche["depot_alias"], consigne=plan["resume"], parents=tout, competences=projets.COMPETENCES_SYNTHESE,
        priorite=10, duree_max=cartes.DUREE_HERMES_SYNTHESE,
        corps=T.CORPS_SYNTHESE.format(titre=fiche["titre"], r=tour, objectif=fiche["objectif"], suivant=tour + 1)))
    return demandes


# Cartes de DÉCISION du propriétaire émises par le greffon (rôle « triage ») : leur ``ref`` dit leur genre.
# « Prolonger » (plafond) ou « Relancer » (planification sans plan) les fait exécuter par Hermes, qui peut alors
# planifier le tour suivant (projet_planifier) ; « Conclure » arrête le projet (décision D41).
PLAFONDS = {"tours": "plafond_tours", "cartes": "plafond_cartes", "corrections": "plafond_corrections"}
REF_SANS_PLAN = "sans-plan"
REFS_PLANIFICATRICES = ("plafond-tours", "plafond-cartes", REF_SANS_PLAN)


def genre_de_triage(demande: Optional[Dict[str, Any]]) -> Optional[str]:
    """``tours``, ``cartes``, ``corrections`` ou ``sans_plan`` pour une carte de décision émise par le greffon,
    None pour toute autre carte (une carte passée en triage par le disjoncteur de Hermes, par exemple)."""
    if not demande or demande.get("role") != "triage":
        return None
    ref = str(demande.get("ref") or "")
    if ref == REF_SANS_PLAN:
        return "sans_plan"
    genre = ref[len("plafond-"):] if ref.startswith("plafond-") else ""
    return genre if genre in PLAFONDS else None


def _creer_triage(conn, fiche: Dict[str, Any], *, cle: str, ref: str, titre: str, corps: str, detail: str,
                  journal: str, cle_notif: str, genre_notif: str, texte_notif: str) -> Optional[str]:
    """UNE carte en triage par clé, adressée au propriétaire (assigné ``default`` : sa décision la fait exécuter
    par Hermes, avec les compétences de la planification), et UNE notification par clé."""
    existante = conn.execute("SELECT carte FROM demandes WHERE cle = ?", (cle,)).fetchone()
    if existante is None:
        with base.transaction(conn):
            cartes.reserver(conn, [dict(
                cle=cle, projet_id=fiche["id"], tableau=fiche["tableau"], role="triage", classe="triage", voie="hermes",
                tour=fiche["tour"], ref=ref, titre=titre, source_routage="sans_objet", depot_alias=fiche["depot_alias"],
                consigne=detail, triage=True, priorite=10, competences=projets.COMPETENCES_PLANIFICATION,
                duree_max=cartes.DUREE_PLANIFICATION, corps=corps)])
            conn.execute("UPDATE projets SET cartes_creees = cartes_creees + 1, maj_le = ? WHERE id = ?",
                         (base.maintenant(), fiche["id"]))
            base.journaliser(conn, "acp-poste", journal, projet_id=fiche["id"], cible=ref, detail=detail)
    ids = cartes.creer(conn, fiche, [d for d in cartes.demandes_non_rattachees(conn, fiche["id"]) if d["cle"] == cle])
    notifications.enfiler(conn, cle=cle_notif, genre=genre_notif, projet_id=fiche["id"], texte_notif=texte_notif)
    ligne = conn.execute("SELECT carte FROM demandes WHERE cle = ?", (cle,)).fetchone()
    return ids.get(cle) or (ligne[0] if ligne else None)


def creer_triage_plafond(conn, fiche: Dict[str, Any], genre: str, detail: str) -> Optional[str]:
    """UNE carte en triage par projet, par genre de plafond et par VALEUR de ce plafond (clé
    ``acp:<p>:plafond:<genre>:<valeur>`` : après une prolongation, le nouveau plafond atteint en demande une
    nouvelle), et UNE notification ``plafond:<p>:<genre>:<valeur>``."""
    valeur = int(fiche[PLAFONDS[genre]])
    prolonger = T.PROLONGER_PAR_GENRE[genre].format(n=int(base.reglage(conn, "prolongation_cartes") or 10))
    return _creer_triage(
        conn, fiche, cle=f"{ka.PREFIXE_CLE}{fiche['id']}:plafond:{genre}:{valeur}", ref=f"plafond-{genre}",
        titre=T.TITRE_TRIAGE_PLAFOND.format(genre=genre), detail=detail, journal="plafond",
        corps=T.CORPS_TRIAGE_PLAFOND.format(titre=fiche["titre"], genre=genre, detail=detail, prolonger=prolonger),
        cle_notif=f"plafond:{fiche['id']}:{genre}:{valeur}", genre_notif="plafond",
        texte_notif=notifications.texte(T.NOTIF_PLAFOND, titre=fiche["titre"], genre=genre))


def creer_triage_sans_plan(conn, fiche: Dict[str, Any], detail: str) -> Optional[str]:
    """Filet de l'émetteur (constat de la relecture de P4) : la planification — ou sa relance — s'est terminée
    sans plan. UNE carte de décision de plus par occurrence (clé ``acp:<p>:sans-plan:<n>``) et UNE
    notification ``sans_plan:<p>:<n>`` (genre ``triage``)."""
    n = conn.execute("SELECT COUNT(*) FROM demandes WHERE projet_id = ? AND role = 'triage' AND ref = ?",
                     (fiche["id"], REF_SANS_PLAN)).fetchone()[0] + 1
    return _creer_triage(
        conn, fiche, cle=f"{ka.PREFIXE_CLE}{fiche['id']}:sans-plan:{n}", ref=REF_SANS_PLAN,
        titre=T.TITRE_TRIAGE_SANS_PLAN, detail=detail, journal="sans_plan",
        corps=T.CORPS_TRIAGE_SANS_PLAN.format(titre=fiche["titre"], detail=detail),
        cle_notif=f"sans_plan:{fiche['id']}:{n}", genre_notif="triage",
        texte_notif=notifications.texte(T.NOTIF_SANS_PLAN, titre=fiche["titre"]))


def _resultat(conn, fiche: Dict[str, Any], tour: int, deja: bool) -> Dict[str, Any]:
    fiche = projets.projet(conn, fiche["id"])
    lignes = [base.ligne_en_dict(l) for l in conn.execute(
        "SELECT * FROM demandes WHERE projet_id = ? AND tour = ? AND role IN ('implementation', 'relecture', 'hermes', "
        "'synthese') ORDER BY cree_le, rowid", (fiche["id"], tour))]
    par_cle = {l["cle"]: l for l in lignes}
    relue_par = {l["carte_relue"]: l["carte"] for l in lignes if l["role"] == "relecture"}
    return {
        "ok": True, "tour": tour, "deja_planifie": deja,
        "cartes": [{"ref": l["ref"], "role": l["role"], "carte": l["carte"], "voie": l["voie"],
                    "modele": l["modele"] or (T.MODELE_DU_PROFIL if l["voie"] == "hermes" else None),
                    "effort": l["effort"], "effort_carte": l["effort_carte"], "palier": l["palier"],
                    "source_routage": l["source_routage"], "mention": l["mention"],
                    "relue_par": relue_par.get(l["cle"]),
                    "relit": par_cle[l["carte_relue"]]["carte"] if l["carte_relue"] in par_cle else None}
                   for l in lignes if l["role"] != "synthese"],
        "synthese": next((l["carte"] for l in lignes if l["role"] == "synthese"), None),
        "plafonds_restants": {"tours": max(0, fiche["plafond_tours"] - fiche["tour"]),
                              "cartes": max(0, fiche["plafond_cartes"] - fiche["cartes_creees"])},
    }


def planifier(conn, *, tableau: str, carte: str, resume: Any, decisions: Any, etapes: Any,
              kc_pour_tests: Optional[Any] = None) -> Dict[str, Any]:
    """Planifie le tour suivant depuis la carte de planification (tour 1), de synthèse du tour ``n``
    (tour ``n+1``), ou de décision (triage) que le propriétaire a prolongée ou relancée (tour courant + 1).
    Le tableau et la carte viennent de l'ENVIRONNEMENT du worker, jamais du modèle."""
    fiche = projets.projet(conn, tableau)
    demande = projets.demande_de_la_carte(conn, tableau, carte) if fiche else None
    decision = demande is not None and demande["role"] == "triage" and demande["ref"] in REFS_PLANIFICATRICES
    if fiche is None or demande is None or (demande["role"] not in ("planification", "synthese") and not decision):
        raise refus("contexte", T.CONTEXTE_PLANIFIER)
    if decision:
        # Seulement après la décision du propriétaire (« Prolonger » ou « Relancer » : journalisée).
        decidee = conn.execute("SELECT 1 FROM journal WHERE projet_id = ? AND cible = ? AND action IN "
                               "('prolongation', 'relance_planification')", (fiche["id"], carte)).fetchone()
        if decidee is None:
            raise refus("contexte", T.CONTEXTE_PLANIFIER_TRIAGE)
    if demande["role"] == "planification":
        tour = 1
    elif demande["role"] == "synthese":
        tour = int(demande["tour"]) + 1
    else:
        existant_decision = conn.execute("SELECT tour FROM tours WHERE projet_id = ? AND carte_origine = ?",
                                         (fiche["id"], carte)).fetchone()
        tour = int(existant_decision[0]) if existant_decision else int(fiche["tour"]) + 1
    plan = valider_plan(resume, decisions, etapes, maximum=int(base.reglage(conn, "etapes_par_appel_max") or 12))
    empreinte_plan = empreinte(plan)
    existant = conn.execute("SELECT * FROM tours WHERE projet_id = ? AND tour = ?", (fiche["id"], tour)).fetchone()
    if existant is not None:
        if existant["carte_origine"] != carte:
            raise refus("carte_non_courante", T.CARTE_NON_COURANTE.format(titre=fiche["titre"]))
        if existant["empreinte_plan"] != empreinte_plan:
            raise refus("deja_planifie_autrement", T.DEJA_PLANIFIE_AUTREMENT.format(r=tour))
        # Rejeu du même plan (worker relancé après une coupure) : on complète ce qui manquerait.
        manquantes = [d for d in cartes.demandes_non_rattachees(conn, fiche["id"]) if d["tour"] == tour]
        if manquantes:
            cartes.creer(conn, fiche, manquantes)
        return _resultat(conn, fiche, tour, True)
    if fiche["etat"] in ("termine", "abandonne"):
        raise refus("carte_non_courante", T.PROJET_FINI.format(titre=fiche["titre"], etat=fiche["etat"]))
    if int(fiche["tour"]) != tour - 1:
        raise refus("carte_non_courante", T.CARTE_NON_COURANTE.format(titre=fiche["titre"]))
    if tour > int(fiche["plafond_tours"]):
        creer_triage_plafond(conn, fiche, "tours", f"{fiche['plafond_tours']} tours planifiés")
        raise refus("plafond_tours", T.PLAFOND_TOURS.format(n=fiche["plafond_tours"], titre=fiche["titre"]))
    demandes = composer(conn, fiche, tour, plan)
    if int(fiche["cartes_creees"]) + len(demandes) > int(fiche["plafond_cartes"]):
        if int(fiche["plafond_cartes"]) - int(fiche["cartes_creees"]) < 2:
            # Plus aucun plan ne tient (une étape et sa synthèse font deux cartes) : c'est un plafond atteint,
            # pas une fin ; la décision revient au propriétaire (relecture de P4).
            creer_triage_plafond(conn, fiche, "cartes", f"{fiche['cartes_creees']} cartes créées sur "
                                                         f"{fiche['plafond_cartes']}")
            raise refus("plafond_cartes", T.PLAFOND_CARTES_ATTEINT.format(
                titre=fiche["titre"], m=fiche["cartes_creees"], n=fiche["plafond_cartes"]))
        raise refus("plafond_cartes", T.PLAFOND_CARTES.format(k=len(demandes), m=fiche["cartes_creees"],
                                                               n=fiche["plafond_cartes"]))
    with base.transaction(conn):
        conn.execute("INSERT INTO tours (projet_id, tour, carte_origine, empreinte_plan, resume, decisions, cree_le) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)", (fiche["id"], tour, carte, empreinte_plan, plan["resume"],
                                                      json.dumps(plan["decisions"], ensure_ascii=False),
                                                      base.maintenant()))
        cartes.reserver(conn, demandes)
        conn.execute("UPDATE projets SET tour = ?, cartes_creees = cartes_creees + ?, maj_le = ? WHERE id = ?",
                     (tour, len(demandes), base.maintenant(), fiche["id"]))
        base.journaliser(conn, f"carte:{carte}", "planification", projet_id=fiche["id"], cible=f"tour {tour}",
                         detail={"etapes": [e["ref"] for e in plan["etapes"]], "cartes": len(demandes)})
    cles = [d["cle"] for d in demandes]
    try:
        ids = cartes.creer(conn, fiche, cartes.demandes_non_rattachees(conn, fiche["id"], cles), kc=kc_pour_tests)
    except Exception as exc:
        # Aucune carte n'existe (transaction kanban annulée) : on annule aussi la réservation.
        with base.transaction(conn):
            conn.execute("DELETE FROM demandes WHERE projet_id = ? AND tour = ? AND carte IS NULL", (fiche["id"], tour))
            conn.execute("DELETE FROM tours WHERE projet_id = ? AND tour = ?", (fiche["id"], tour))
            conn.execute("UPDATE projets SET tour = ?, cartes_creees = cartes_creees - ?, maj_le = ? WHERE id = ?",
                         (tour - 1, len(demandes), base.maintenant(), fiche["id"]))
            base.journaliser(conn, f"carte:{carte}", "planification_annulee", projet_id=fiche["id"],
                             detail=type(exc).__name__)
        raise RefusACP("echec_creation", T.ECHEC_CREATION.format(type=type(exc).__name__)) from None
    with base.transaction(conn):
        conn.execute("UPDATE tours SET carte_synthese = ? WHERE projet_id = ? AND tour = ?",
                     (ids.get(_cle(fiche["id"], tour, "synthese")), fiche["id"], tour))
    fiche = projets.projet(conn, fiche["id"])
    if fiche["etat"] == "en_pause":
        cartes.planifier_pour_la_pause(conn, fiche, list(ids.values()))
    return _resultat(conn, fiche, tour, False)


# ------------------------------------------------------------------ corrections (préparées en P4, câblées en P6)


def inserer_correction(conn, *, tableau: str, carte_relecture: str, run_id_relecture: Optional[int], consigne: str,
                       sonde: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Insère une correction après une relecture EN COURS, dans l'ordre du plan (§ 2.8) :

    1. contrôle du plafond de corrections (carte de triage et refus au-delà) ;
    2. sous une transaction kanban : carte ``correction`` (voie de l'implémentation, parent : la
       relecture) et nouvelle ``relecture`` (l'autre voie, parent : la correction) ;
    3. ``link_tasks(correction → synthèse)`` puis ``link_tasks(nouvelle relecture → synthèse)`` (deux
       transactions : link_tasks n'est pas composable) ; la synthèse reste gardée par la relecture en
       cours ;
    4. ``complete_task(relecture, expected_run_id)``, dont le ``recompute_ready`` libère la correction
       mais pas la synthèse.

    ``sonde`` (tests) est appelée après chaque étape avec son nom."""
    fiche = projets.projet(conn, tableau)
    relecture = projets.demande_de_la_carte(conn, tableau, carte_relecture) if fiche else None
    if fiche is None or relecture is None or relecture["role"] != "relecture":
        raise refus("contexte", T.CORRECTION_CARTE.format(carte=carte_relecture))
    motif = motif_trouve(consigne)
    if motif:
        raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
    ref, tour = relecture["ref"], int(relecture["tour"])
    impl = conn.execute("SELECT * FROM demandes WHERE projet_id = ? AND tour = ? AND ref = ? AND role = 'implementation'",
                        (fiche["id"], tour, ref)).fetchone()
    synthese = conn.execute("SELECT * FROM demandes WHERE projet_id = ? AND tour = ? AND role = 'synthese'",
                            (fiche["id"], tour)).fetchone()
    if impl is None or synthese is None or not synthese["carte"]:
        raise refus("contexte", T.CORRECTION_CARTE.format(carte=carte_relecture))
    n = conn.execute("SELECT COUNT(*) FROM demandes WHERE projet_id = ? AND tour = ? AND ref = ? AND role = 'correction'",
                     (fiche["id"], tour, ref)).fetchone()[0] + 1
    if n > int(fiche["plafond_corrections"]):
        creer_triage_plafond(conn, fiche, "corrections", f"{fiche['plafond_corrections']} corrections pour « {ref} »")
        raise refus("plafond_corrections", T.CORRECTIONS_PLAFOND.format(n=fiche["plafond_corrections"], ref=ref))
    if int(fiche["cartes_creees"]) + 2 > int(fiche["plafond_cartes"]):
        creer_triage_plafond(conn, fiche, "cartes", f"{fiche['cartes_creees']} cartes créées")
        raise refus("plafond_cartes", T.PLAFOND_CARTES.format(k=2, m=fiche["cartes_creees"], n=fiche["plafond_cartes"]))
    if sonde:
        sonde("controle")
    cle_corr = _cle(fiche["id"], tour, f"{ref}:correction{n}")
    cle_rel = _cle(fiche["id"], tour, f"{ref}:relecture{n + 1}")
    commun = dict(projet_id=fiche["id"], tableau=tableau, tour=tour, ref=ref, depot_alias=fiche["depot_alias"])
    demandes = [
        dict(commun, cle=cle_corr, role="correction", classe=impl["classe"], voie=impl["voie"],
             titre=f"Correction {n} — {ref}", modele=impl["modele"], effort=impl["effort"], palier=impl["palier"],
             modele_carte=impl["modele_carte"], effort_carte=impl["effort_carte"], source_routage=impl["source_routage"],
             releve_id=impl["releve_id"], consigne=consigne, correction_n=n, carte_relue=relecture["cle"],
             parents=[relecture["cle"]],
             corps=T.CORPS_CORRECTION.format(titre=fiche["titre"], r=tour, n=n, ref=ref, classe=impl["classe"],
                                             voie=impl["voie"], modele=impl["modele"], effort=impl["effort"] or T.INCONNU,
                                             palier=impl["palier"], depot=fiche["depot_alias"], consigne=consigne)),
        dict(commun, cle=cle_rel, role="relecture", classe="relecture", voie=relecture["voie"],
             titre=f"Relecture {n + 1} — {ref}", modele=relecture["modele"], effort=relecture["effort"],
             palier=relecture["palier"], modele_carte=relecture["modele_carte"], effort_carte=relecture["effort_carte"],
             source_routage=relecture["source_routage"], releve_id=relecture["releve_id"], consigne=consigne,
             carte_relue=cle_corr, parents=[cle_corr],
             corps=T.CORPS_RELECTURE.format(titre=fiche["titre"], r=tour, ref=ref, classe=impl["classe"],
                                            voie=relecture["voie"], modele=relecture["modele"],
                                            effort=relecture["effort"] or T.INCONNU, palier=relecture["palier"],
                                            depot=fiche["depot_alias"], relue=f"correction {n}",
                                            voie_relue=impl["voie"], consigne=consigne)),
    ]
    with base.transaction(conn):
        cartes.reserver(conn, demandes)
        conn.execute("UPDATE projets SET cartes_creees = cartes_creees + 2, maj_le = ? WHERE id = ?",
                     (base.maintenant(), fiche["id"]))
        base.journaliser(conn, "poste", "correction", projet_id=fiche["id"], cible=carte_relecture, detail={"n": n})
    ids = cartes.creer(conn, fiche, cartes.demandes_non_rattachees(conn, fiche["id"], [cle_corr, cle_rel]))
    if sonde:
        sonde("cartes")
    with ka.connexion(tableau) as kc:
        ka.link_tasks(kc, ids[cle_corr], synthese["carte"])
        if sonde:
            sonde("liaison_correction")
        ka.link_tasks(kc, ids[cle_rel], synthese["carte"])
        if sonde:
            sonde("liaison_relecture")
        fini = ka.complete_task(kc, carte_relecture, summary=consigne, expected_run_id=run_id_relecture)
    if sonde:
        sonde("fin")
    return {"ok": True, "correction": ids[cle_corr], "relecture": ids[cle_rel], "n": n, "relecture_terminee": fini}
