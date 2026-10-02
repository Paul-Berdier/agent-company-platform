"""Questions posées par une carte du poste pendant son exécution (cahier P4 § 8.6, 8.7 ; décision D28).

``poser`` (appelée en P4 par le poste simulé des tests, en P6 par la route du poste) : la carte passe en
``scheduled`` (raison « Question ouverte (ACP) : q_… »), la question est enregistrée, puis selon la
politique du projet :

- ``hermes_d_abord`` : UNE carte « répondre » (Hermes, skill acp-questions, priorité 10) ;
- ``proprietaire`` : escalade directe (notification ``question:<q>``).

Hermes répond par ``question_repondre`` (commentaire + ``unblock_task``) ou escalade par
``question_escalader`` ; le propriétaire répond par la route ``POST /v1/questions/{q}/reponse``. Sur un projet
en pause, la réponse est enregistrée et commentée, mais la carte ne reprend qu'à la reprise du projet. Poser
deux questions de suite sur la même carte ne la fait jamais passer en triage (``schedule_task`` n'est pas un
blocage). Filet de l'émetteur : une question dont la carte « répondre » s'est terminée sans suite est
escaladée (:func:`questions_sans_suite`).

Cartes en triage (vue Questions) : « Reprendre » ; pour une carte de décision du greffon, « Prolonger » ou
« Relancer la planification », et « Conclure » (décision D41).

Étape P7 (cahier P7 § 3) : file Questions à cinq sections (:func:`file_questions` : questions avec ``chez``, décisions,
revues, cartes arrêtées avec « Relancer », discussions en attente en lecture seule) et ses compteurs ; « Relancer » une
carte bloquée ou abandonnée (:func:`relancer_carte`).
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from . import base, cartes, graphe, notifications, projets, routage
from . import kanban_adapter as ka
from . import textes as T
from .motifs_secrets import motif_trouve
from .textes import refus

AUTEUR_HERMES = "hermes (acp-questions)"
AUTEUR_PROPRIETAIRE = "proprietaire"
ROLES_DU_POSTE = ("exploration", "implementation", "relecture", "correction")


def question(conn, identifiant: str) -> Optional[Dict[str, Any]]:
    return base.ligne_en_dict(conn.execute("SELECT * FROM questions WHERE id = ?", (identifiant,)).fetchone())


def _escalader(conn, fiche: Dict[str, Any], q: Dict[str, Any], motif: str, acteur: str) -> None:
    with base.transaction(conn):
        conn.execute("UPDATE questions SET etat = 'escaladee', motif_escalade = ?, maj_le = ? WHERE id = ?",
                     (ka.masquer(motif)[:1000], base.maintenant(), q["id"]))
        notifications.enfiler_dans(conn, cle=f"question:{q['id']}", genre="question", projet_id=fiche["id"],
                                   texte_notif=notifications.texte(T.NOTIF_QUESTION, titre=fiche["titre"]))
        base.journaliser(conn, acteur, "question_escaladee", projet_id=fiche["id"], cible=q["id"], detail=motif)


def poser(conn, *, tableau: str, carte: str, run_id: Optional[int], texte: str,
          contexte: Optional[str] = None) -> Dict[str, Any]:
    fiche = projets.projet(conn, tableau)
    demande = projets.demande_de_la_carte(conn, tableau, carte) if fiche else None
    if fiche is None or demande is None or demande["role"] not in ROLES_DU_POSTE or demande["voie"] == "hermes":
        raise refus("question_carte", T.QUESTION_CARTE.format(carte=carte))
    if not isinstance(texte, str) or not 1 <= len(texte.strip()) <= 4000:
        raise refus("question_texte", "le texte de la question doit compter de 1 à 4000 caractères.")
    for valeur in (texte, contexte):
        motif = motif_trouve(valeur)
        if motif:
            raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
    existante = conn.execute("SELECT * FROM questions WHERE tableau = ? AND carte = ? AND run_id IS ?",
                             (tableau, carte, run_id)).fetchone()
    if existante is not None:
        return {"ok": True, "question": existante["id"], "etat": existante["etat"],
                "carte_repondre": existante["carte_repondre"], "deja_posee": True}
    with ka.connexion(tableau) as kc:
        tache = ka.get_task(kc, carte)
        if tache is None or tache.status != "running":
            raise refus("question_carte_etat", T.QUESTION_CARTE_ETAT.format(
                carte=carte, statut=tache.status if tache else T.INCONNU))
    identifiant = "q_" + secrets.token_hex(6)
    maintenant = base.maintenant()
    with base.transaction(conn):
        conn.execute("INSERT INTO questions (id, projet_id, tableau, carte, run_id, texte, contexte, etat, cree_le, maj_le) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, 'ouverte', ?, ?)",
                     (identifiant, fiche["id"], tableau, carte, run_id, texte.strip(),
                      (contexte or "")[:4000] or None, maintenant, maintenant))
        base.journaliser(conn, "poste", "question", projet_id=fiche["id"], cible=identifiant, detail={"carte": carte})
    with ka.connexion(tableau) as kc:
        ka.schedule_task(kc, carte, reason=T.RAISON_QUESTION.format(q=identifiant), expected_run_id=run_id)
    q = question(conn, identifiant)
    if fiche["reponses"] == "proprietaire":
        _escalader(conn, fiche, q, "politique du projet : le propriétaire répond lui-même", "acp-poste")
        return {"ok": True, "question": identifiant, "etat": "escaladee", "carte_repondre": None, "deja_posee": False}
    if int(fiche["cartes_creees"]) + 1 > int(fiche["plafond_cartes"]):
        _escalader(conn, fiche, q, f"plafond de {fiche['plafond_cartes']} cartes atteint : pas de carte « répondre »",
                   "acp-poste")
        return {"ok": True, "question": identifiant, "etat": "escaladee", "carte_repondre": None, "deja_posee": False}
    cle = f"{ka.PREFIXE_CLE}{fiche['id']}:q:{identifiant}:repondre"
    with base.transaction(conn):
        cartes.reserver(conn, [dict(
            cle=cle, projet_id=fiche["id"], tableau=tableau, role="repondre", classe="repondre", voie="hermes",
            tour=fiche["tour"], ref=identifiant, titre=T.TITRE_REPONDRE.format(q=identifiant), source_routage="profil",
            palier="default", depot_alias=fiche["depot_alias"], consigne=texte.strip(),
            competences=projets.COMPETENCES_REPONDRE, priorite=10, duree_max=cartes.DUREE_HERMES_SYNTHESE,
            corps=T.CORPS_REPONDRE.format(titre=fiche["titre"], texte=texte.strip()))])
        conn.execute("UPDATE projets SET cartes_creees = cartes_creees + 1, maj_le = ? WHERE id = ?",
                     (base.maintenant(), fiche["id"]))
    ids = cartes.creer(conn, fiche, cartes.demandes_non_rattachees(conn, fiche["id"], [cle]))
    with base.transaction(conn):
        conn.execute("UPDATE questions SET carte_repondre = ?, maj_le = ? WHERE id = ?",
                     (ids.get(cle), base.maintenant(), identifiant))
    fiche = projets.projet(conn, fiche["id"])
    if fiche["etat"] == "en_pause" and ids.get(cle):
        cartes.planifier_pour_la_pause(conn, fiche, [ids[cle]])
    return {"ok": True, "question": identifiant, "etat": "ouverte", "carte_repondre": ids.get(cle), "deja_posee": False}


def _question_de_la_carte(conn, *, tableau: str, carte: str, identifiant: Optional[str], outil: str) -> Dict[str, Any]:
    """Question dont ``carte`` est la carte « répondre » (et ``identifiant`` s'il est donné)."""
    demande = projets.demande_de_la_carte(conn, tableau, carte)
    q = base.ligne_en_dict(conn.execute("SELECT * FROM questions WHERE tableau = ? AND carte_repondre = ?",
                                        (tableau, carte)).fetchone()) if demande else None
    if demande is None or demande["role"] != "repondre" or q is None or (identifiant and q["id"] != identifiant):
        raise refus("contexte", T.CONTEXTE_QUESTION.format(outil=outil))
    return q


def repondre_par_hermes(conn, *, tableau: str, carte: str, identifiant: Optional[str], reponse: str,
                        fondement: str) -> Dict[str, Any]:
    q = _question_de_la_carte(conn, tableau=tableau, carte=carte, identifiant=identifiant, outil="question_repondre")
    if q["etat"] != "ouverte":
        raise refus("question_fermee", T.QUESTION_FERMEE.format(q=q["id"], etat=q["etat"]))
    for valeur, borne, nom in ((reponse, 4000, "la réponse"), (fondement, 1000, "le fondement")):
        if not isinstance(valeur, str) or not 1 <= len(valeur.strip()) <= borne:
            raise refus("arguments", f"{nom} doit compter de 1 à {borne} caractères.")
        motif = motif_trouve(valeur)
        if motif:
            raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
    fiche = projets.projet(conn, tableau)
    debloquee, differee = _commenter_et_reprendre(conn, fiche, q, AUTEUR_HERMES,
                                                  f"{reponse.strip()}\n\nFondement : {fondement.strip()}")
    with base.transaction(conn):
        conn.execute("UPDATE questions SET etat = 'repondue', reponse = ?, repondu_par = 'hermes', fondement = ?, "
                     "maj_le = ?, repondue_le = ? WHERE id = ?",
                     (reponse.strip(), fondement.strip(), base.maintenant(), base.maintenant(), q["id"]))
        base.journaliser(conn, f"carte:{carte}", "question_repondue", projet_id=fiche["id"], cible=q["id"],
                         detail={"par": "hermes", "carte_debloquee": debloquee, "reprise_differee": differee})
    return {"question": q["id"], "etat": "repondue", "carte_debloquee": debloquee, "reprise_differee": differee}


def _commenter_et_reprendre(conn, fiche: Dict[str, Any], q: Dict[str, Any], auteur: str, texte: str):
    """Commentaire de la réponse sur la carte du poste, puis reprise de la carte — sauf si le projet est en
    pause : la carte reste alors planifiée et ne reprendra qu'à la reprise du projet (``projets.reprendre``
    réveille les cartes dont la question a reçu sa réponse). Rend ``(carte_debloquee, reprise_differee)``."""
    with ka.connexion(q["tableau"]) as kc:
        ka.add_comment(kc, q["carte"], auteur, texte)
        if fiche is not None and fiche["etat"] == "en_pause":
            return False, True
        return bool(ka.unblock_task(kc, q["carte"])), False


def escalader(conn, *, tableau: str, carte: str, identifiant: Optional[str], motif: str) -> Dict[str, Any]:
    q = _question_de_la_carte(conn, tableau=tableau, carte=carte, identifiant=identifiant, outil="question_escalader")
    if q["etat"] != "ouverte":
        raise refus("question_fermee", T.QUESTION_FERMEE.format(q=q["id"], etat=q["etat"]))
    if not isinstance(motif, str) or not 1 <= len(motif.strip()) <= 1000:
        raise refus("arguments", "le motif doit compter de 1 à 1000 caractères.")
    trouve = motif_trouve(motif)
    if trouve:
        raise refus("secret", T.SECRET_TEXTE.format(motif=trouve))
    _escalader(conn, projets.projet(conn, tableau), q, motif.strip(), f"carte:{carte}")
    return {"question": q["id"], "etat": "escaladee"}


def repondre_par_proprietaire(conn, identifiant: str, *, reponse: Any, auteur: str) -> Dict[str, Any]:
    q = question(conn, identifiant)
    if q is None:
        raise refus("question_inconnue", T.QUESTION_INCONNUE.format(q=identifiant))
    if q["etat"] not in ("ouverte", "escaladee"):
        raise refus("question_fermee", T.QUESTION_FERMEE.format(q=q["id"], etat=q["etat"]))
    if not isinstance(reponse, str) or not 1 <= len(reponse.strip()) <= 4000:
        raise refus("arguments", "la réponse doit compter de 1 à 4000 caractères.")
    motif = motif_trouve(reponse)
    if motif:
        raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
    debloquee, differee = _commenter_et_reprendre(conn, projets.projet(conn, q["projet_id"]), q, AUTEUR_PROPRIETAIRE,
                                                  reponse.strip())
    with base.transaction(conn):
        conn.execute("UPDATE questions SET etat = 'repondue', reponse = ?, repondu_par = 'proprietaire', maj_le = ?, "
                     "repondue_le = ? WHERE id = ?", (reponse.strip(), base.maintenant(), base.maintenant(), q["id"]))
        base.journaliser(conn, auteur, "question_repondue", projet_id=q["projet_id"], cible=q["id"],
                         detail={"par": "proprietaire", "carte_debloquee": debloquee, "reprise_differee": differee})
    return {"question": q["id"], "etat": "repondue", "carte_debloquee": debloquee, "reprise_differee": differee}


def _raison(tache, evenements) -> Optional[str]:
    """Raison lisible d'une carte bloquée ou en triage : celle du DERNIER événement ``blocked`` ou
    ``block_loop_detected`` (``block_task`` de Hermes la range dans la charge de l'événement, jamais dans
    ``last_failure_error`` : kanban_db.py:3302-3328) ; pour un abandon, l'erreur retenue par le disjoncteur.
    None seulement si ni l'une ni l'autre n'existe."""
    raison = None
    abandon = [e for e in evenements if e.kind == "gave_up"]
    if abandon:
        charge = abandon[-1].payload if isinstance(abandon[-1].payload, dict) else {}
        raison = tache.last_failure_error or charge.get("error")
    if not raison:
        for evenement in reversed(evenements):
            if evenement.kind in ("blocked", "block_loop_detected"):
                charge = evenement.payload if isinstance(evenement.payload, dict) else {}
                raison = charge.get("reason")
                break
    raison = raison or tache.last_failure_error
    return (ka.masquer(raison)[:300] or None) if raison else None


# Gestes offerts sur une carte en triage, selon ce qu'elle est (décision D41) ; « reprendre » pour une carte
# que Hermes a passée en triage (boucle de blocages) ou qu'une autre voie y a mise.
ACTIONS_PAR_GENRE = {"tours": ["prolonger", "conclure"], "cartes": ["prolonger", "conclure"],
                     "corrections": ["conclure"], "sans_plan": ["relancer", "conclure"]}


def _titre_de_carte(conn, tableau: str, carte: str) -> Optional[str]:
    demande = projets.demande_de_la_carte(conn, tableau, carte)
    try:
        with ka.connexion(tableau) as kc:
            tache = ka.get_task(kc, carte)
        if tache is not None:
            return ka.masquer(tache.title)[:200] or None
    except Exception:  # noqa: BLE001 — tableau illisible : titre de la demande, sinon inconnu (jamais inventé)
        pass
    return (demande or {}).get("titre") or None


def chez(q: Dict[str, Any]) -> str:
    """Qui doit répondre à une question ouverte ou escaladée — RÈGLE UNIQUE (cahier P7 § 3.1, correction K6) :
    ``hermes`` si elle est ``ouverte`` ET que sa carte « répondre » existe, sinon ``proprietaire``. Jamais d'après le
    réglage courant du projet : les questions ouvertes gardent leur traitement quand il change. Une question ouverte
    sans carte « répondre » (création interrompue) n'est pas rattrapée par le filet :func:`questions_sans_suite`, qui
    ne lit que ``carte_repondre IS NOT NULL`` : elle est donc comptée « à vous », jamais cachée."""
    return "hermes" if q.get("etat") == "ouverte" and q.get("carte_repondre") else "proprietaire"


def _statut_de_carte(tableau: str, carte: Optional[str]) -> Optional[str]:
    if not carte:
        return None
    try:
        with ka.connexion(tableau) as kc:
            tache = ka.get_task(kc, carte)
    except Exception:  # noqa: BLE001 — tableau illisible : statut inconnu, jamais inventé
        return None
    return tache.status if tache is not None else None


def _emise_par_acp(demande: Optional[Dict[str, Any]], tache: Any) -> bool:
    """Carte émise par le greffon : sa demande existe, et la carte kanban porte la clé et le créateur du greffon."""
    return (demande is not None and tache is not None and getattr(tache, "idempotency_key", None) == demande["cle"]
            and getattr(tache, "created_by", None) == ka.CREATEUR)


def _bloquee_pour_secret(demande: Optional[Dict[str, Any]], evenements: List[Any]) -> bool:
    if demande is not None and demande.get("issue") == "bloquee:secret":
        return True
    for evenement in reversed(evenements):
        if evenement.kind in ("blocked", "block_loop_detected"):
            charge = evenement.payload if isinstance(evenement.payload, dict) else {}
            return charge.get("reason") == T.RAISON_SECRET_EXECUTANT
    return False


def refus_de_relance(fiche: Dict[str, Any], demande: Optional[Dict[str, Any]], tache: Any,
                     evenements: List[Any]) -> Optional[tuple]:
    """``(code, message, raison lisible)`` qui interdit de relancer une carte arrêtée, dans l'ordre du cahier P7
    § 3.4 (carte émise par ACP, projet actif, carte arrêtée, revue, secret) ; ``None`` si elle se relance."""
    carte = getattr(tache, "id", None) or (demande or {}).get("carte") or "?"
    if not _emise_par_acp(demande, tache):
        return ("carte_non_acp", T.CARTE_NON_ACP.format(carte=carte, t=fiche["tableau"]), T.REFUS_RELANCE_NON_ACP)
    if fiche["etat"] == "en_pause":
        return ("projet_en_pause", T.RELANCE_PROJET_EN_PAUSE.format(titre=fiche["titre"]), T.REFUS_RELANCE_PAUSE)
    if fiche["etat"] != "actif":
        etat = T.ETATS_LISIBLES.get(fiche["etat"], fiche["etat"])
        return ("projet_fini", T.PROJET_FINI.format(titre=fiche["titre"], etat=etat),
                T.REFUS_RELANCE_FINI.format(etat=etat))
    if tache.status == "review":
        return ("carte_en_revue", T.CARTE_EN_REVUE.format(carte=carte), T.REFUS_RELANCE_REVUE)
    if tache.status != "blocked":
        return ("carte_non_arretee", T.CARTE_NON_ARRETEE.format(carte=carte, statut=tache.status),
                T.CARTE_NON_ARRETEE.format(carte=carte, statut=tache.status))
    if _bloquee_pour_secret(demande, evenements):
        return ("carte_secret", T.CARTE_SECRET.format(carte=carte), T.REFUS_RELANCE_SECRET)
    return None


def lister(conn) -> Dict[str, Any]:
    """Questions ouvertes et escaladées (avec le titre de la carte qui les pose, leur contexte, ``chez`` et le statut de
    leur carte « répondre ») ; cartes en triage (avec les gestes possibles), bloquées et abandonnées des tableaux de
    projet, chacune avec sa raison connue — étape P7 : une carte arrêtée dit si elle se relance (``relancable``) ou
    pourquoi non (``refus_relance``)."""
    ouvertes = []
    titres: Dict[tuple, Optional[str]] = {}
    for q in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT q.*, p.titre AS projet_titre FROM questions q JOIN projets p ON p.id = q.projet_id "
            "WHERE q.etat IN ('ouverte', 'escaladee') ORDER BY q.cree_le")]:
        cle = (q["tableau"], q["carte"])
        if cle not in titres:
            titres[cle] = _titre_de_carte(conn, q["tableau"], q["carte"])
        ouvertes.append({"id": q["id"], "projet": q["projet_id"], "projet_titre": q["projet_titre"],
                         "tableau": q["tableau"], "carte": q["carte"], "carte_titre": titres[cle],
                         "etat": q["etat"], "texte": ka.masquer(q["texte"])[:4000],
                         "contexte": (ka.masquer(q["contexte"])[:1000] or None) if q["contexte"] else None,
                         "carte_repondre": q["carte_repondre"], "motif_escalade": q["motif_escalade"],
                         "cree_le": q["cree_le"], "chez": chez(q),
                         "carte_repondre_statut": _statut_de_carte(q["tableau"], q["carte_repondre"])})
    triage: List[Dict[str, Any]] = []
    bloquees: List[Dict[str, Any]] = []
    illisibles: List[str] = []
    for p in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT * FROM projets WHERE etat != 'abandonne' ORDER BY cree_le").fetchall()]:
        try:
            with ka.connexion(p["tableau"]) as kc:
                for statut, cible in (("triage", triage), ("blocked", bloquees)):
                    for tache in ka.list_tasks(kc, status=statut):
                        evenements = ka.list_events(kc, tache.id)
                        demande = projets.demande_de_la_carte(conn, p["tableau"], tache.id)
                        entree = {"projet": p["id"], "projet_titre": p["titre"], "tableau": p["tableau"],
                                  "carte": tache.id, "titre": ka.masquer(tache.title)[:200],
                                  "assigne": tache.assignee,
                                  "abandonnee": statut == "blocked" and any(e.kind == "gave_up" for e in evenements),
                                  "raison": _raison(tache, evenements)}
                        if statut == "triage":
                            genre = graphe.genre_de_triage(demande)
                            entree.update(genre=genre, actions=ACTIONS_PAR_GENRE.get(genre, ["reprendre"]))
                            if genre and not entree["raison"]:
                                entree["raison"] = ka.masquer(demande["consigne"])[:300] or None
                        else:
                            refus_ = refus_de_relance(p, demande, tache, evenements)
                            entree.update(relancable=refus_ is None, refus_relance=refus_[2] if refus_ else None,
                                          executant=bool(demande) and demande["voie"] != "hermes")
                        cible.append(entree)
        except Exception:  # noqa: BLE001 — tableau illisible : dit, jamais inventé
            illisibles.append(p["tableau"])
    return {"questions": ouvertes, "triage": triage, "bloquees": bloquees, "tableaux_illisibles": illisibles}


def discussions_en_attente() -> Dict[str, Any]:
    """Cinquième section de la file (cahier P7 § 3.5), en LECTURE SEULE : nombre de requêtes du serveur au client
    encore sans réponse dans le processus du tableau de bord (sessions ouvertes par /api/ws). Le détail (titre, clé,
    aperçu) se lit côté client par ``session.active_list`` ; rien n'est rattaché ici. Inconnu → ``None`` et le
    message, jamais zéro."""
    n = ka.requetes_ouvertes()
    return {"suivies": n is not None, "requetes_ouvertes": n,
            "message": None if n is not None else T.DISCUSSIONS_NON_SUIVIES, "limite": T.DISCUSSIONS_LIMITE}


def compteurs(file: Dict[str, Any]) -> Dict[str, int]:
    """« À traiter par vous » (questions dont ``chez`` vaut ``proprietaire``, décisions, revues, cartes arrêtées) et
    « Chez Hermes » ; les discussions en attente sont comptées à part (section 5, ``discussions``)."""
    questions = [q for q in file["questions"] if q["chez"] == "proprietaire"]
    resultat = {"questions": len(questions), "decisions": len(file["triage"]), "revues": len(file.get("revues") or []),
                "arretees": len(file["bloquees"]),
                "chez_hermes": sum(1 for q in file["questions"] if q["chez"] == "hermes")}
    resultat["a_traiter"] = resultat["questions"] + resultat["decisions"] + resultat["revues"] + resultat["arretees"]
    return resultat


def file_questions(conn) -> Dict[str, Any]:
    """Route ``GET /v1/questions`` (cahier P7 § 3.2) : les cinq sections — questions, décisions (triage), revues
    (P6), cartes arrêtées, discussions en attente (lecture seule) — et les compteurs ; aucun champ de P4-P6 retiré."""
    from . import execution  # import différé : execution importe ce module

    file = lister(conn)
    file["revues"] = execution.revues_en_cours(conn)
    file["discussions"] = discussions_en_attente()
    file["compteurs"] = compteurs(file)
    return file


# ------------------------------------------------------------------ « Relancer » une carte arrêtée (étape P7)


def _composer_consigne(initiale: str, consigne: str, quand: int) -> str:
    """Consigne servie à l'exécutant après une relance (correction K4) : la section du propriétaire EN TÊTE (la
    réduction à 60 Kio de ``execution.construire_carte`` coupe la FIN de la consigne : la section n'est jamais la
    première coupée), puis la consigne d'origine tronquée pour que le tout tienne dans ``CONSIGNE_MAX`` (16 000
    caractères, contrat ``DemandeCarte``) ; une carte trop longue serait refusée par le contrat, puis rebloquée."""
    from . import contrat_partage  # noqa: F401 — met le contrat sur sys.path
    from acp_poste_contrat.machine import CONSIGNE_MAX

    section = T.SECTION_RELANCE.format(date=routage.date_lisible(quand, "%d/%m à %H:%M"), consigne=consigne)
    place = CONSIGNE_MAX - MARGE_MASQUAGE - len(section)
    if len(initiale) > place:
        mention = T.MENTION_TRONQUE_RELANCE.format(n=f"{CONSIGNE_MAX:,}".replace(",", " "))
        initiale = initiale[:max(0, place - len(mention))] + mention
    return section + initiale


# Marge laissée sous CONSIGNE_MAX : le masquage des secrets de Hermes, appliqué à la construction de la carte, peut
# allonger un texte de quelques caractères.
MARGE_MASQUAGE = 200


def relancer_carte(conn, *, tableau: str, carte: str, consigne: Any, auteur: str) -> Dict[str, Any]:
    """Bouton « Relancer » d'une carte bloquée ou abandonnée (cahier P7 § 3.4, décision P7-2 ; corrections K4, K5,
    K25). Contrôles dans l'ordre : projet ACP connu, carte émise par le greffon, projet ACTIF, carte arrêtée (une carte
    en revue se traite par Accepter ou Refuser), carte non bloquée pour un secret (avant la partie E). Aucune carte
    n'est créée : le plafond de cartes du projet n'est pas touché.

    Effet : carte Hermes → la consigne éventuelle en commentaire (le worker la lit par ``build_worker_context``) ;
    carte de l'exécutant → ``issue = 'relancee'`` (hors ``ISSUES_REPRISE`` : l'exécutant repart d'une SESSION NEUVE,
    qui lit la consigne entière, sur la branche gardée) et, avec une consigne, la consigne servie recomposée
    (:func:`_composer_consigne`) ; puis ``unblock_task`` (compteur d'échecs remis à zéro ; ``block_recurrences``
    gardé : un second blocage de même raison repart en triage). Journal ``relance`` ; aucune notification."""
    if consigne is not None:
        if not isinstance(consigne, str) or not 1 <= len(consigne.strip()) <= 4000:
            raise refus("arguments", T.CONSIGNE_RELANCE)
        motif = motif_trouve(consigne)
        if motif:
            raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
        consigne = consigne.strip()
    fiche = projets.projet(conn, tableau)
    if fiche is None or fiche["tableau"] != tableau:
        raise refus("projet_inconnu", T.PROJET_INTROUVABLE.format(t=tableau))
    from . import execution  # import différé : execution importe ce module

    with execution.verrou():  # aucune carte servie à l'exécutant entre la relecture de la demande et le déblocage
        demande = projets.demande_de_la_carte(conn, tableau, carte)
        with ka.connexion(tableau) as kc:
            tache = ka.get_task(kc, carte)
            evenements = ka.list_events(kc, carte) if tache is not None else []
        if tache is None and demande is None:
            raise refus("carte_inconnue", T.CARTE_DU_PROJET_INCONNUE.format(carte=carte[:40], titre=fiche["titre"]))
        refus_ = refus_de_relance(fiche, demande, tache, evenements)
        if refus_ is not None:
            raise refus(refus_[0], refus_[1])
        executant = demande["voie"] != "hermes"
        maintenant = base.maintenant()
        avant = {c: demande.get(c) for c in ("issue", "consigne", "consigne_relance", "relancee_le",
                                             "consigne_initiale")}
        apres: Dict[str, Any] = {"relancee_le": maintenant}
        if consigne is not None:
            apres["consigne_relance"] = consigne
        if executant:
            apres["issue"] = "relancee"
            if consigne is not None:
                initiale = demande.get("consigne_initiale") or demande["consigne"]
                apres.update(consigne_initiale=initiale, consigne=_composer_consigne(initiale, consigne, maintenant))
        _ecrire_demande(conn, demande["cle"], apres)
        try:
            with ka.connexion(tableau) as kc:
                if consigne is not None and not executant:
                    ka.add_comment(kc, carte, AUTEUR_PROPRIETAIRE, T.COMMENTAIRE_RELANCE.format(consigne=consigne))
                relancee = bool(ka.unblock_task(kc, carte))
                statut_apres = getattr(ka.get_task(kc, carte), "status", None)
        except BaseException:
            _ecrire_demande(conn, demande["cle"], avant)
            raise
        if not relancee:
            _ecrire_demande(conn, demande["cle"], avant)
        with base.transaction(conn):
            base.journaliser(conn, auteur, "relance", projet_id=fiche["id"], cible=carte,
                             detail={"avec_consigne": consigne is not None, "executant": executant,
                                     "relancee": relancee, "statut_apres": statut_apres})
    return {"carte": carte, "relancee": relancee, "statut_apres": statut_apres,
            "session_neuve": relancee and executant}


def _ecrire_demande(conn, cle: str, colonnes: Dict[str, Any]) -> None:
    affectations = ", ".join(f"{nom} = ?" for nom in colonnes)
    with base.transaction(conn):
        conn.execute(f"UPDATE demandes SET {affectations} WHERE cle = ?", (*colonnes.values(), cle))


def _carte_en_triage(conn, tableau: str, carte: str) -> Dict[str, Any]:
    fiche = projets.projet(conn, tableau)
    if fiche is None:
        raise refus("projet_inconnu", T.PROJET_INTROUVABLE.format(t=tableau))
    with ka.connexion(tableau) as kc:
        tache = ka.get_task(kc, carte)
    if tache is None or tache.status != "triage":
        raise refus("triage_inconnu", T.TRIAGE_INCONNU.format(carte=carte, t=tableau))
    if fiche["etat"] == "en_pause":
        raise refus("projet_en_pause", T.TRIAGE_PROJET_EN_PAUSE.format(titre=fiche["titre"]))
    return {"fiche": fiche, "tache": tache, "demande": projets.demande_de_la_carte(conn, tableau, carte)}


def reprendre_triage(conn, *, tableau: str, carte: str, consigne: Optional[str], auteur: str) -> Dict[str, Any]:
    """Bouton « Reprendre » d'une carte en triage — « Prolonger » ou « Relancer la planification » pour une
    carte de décision du greffon (décision D41) : ``specify_triage_task`` (triage → todo) avec la consigne du
    propriétaire ; au plafond, le plafond est d'abord relevé (tours + 1, cartes + ``prolongation_cartes``),
    et journalisé. La carte est alors exécutée par Hermes, qui peut planifier la suite depuis elle
    (``graphe.planifier``). Refusé sur un projet en pause (la carte partirait avant la reprise)."""
    if consigne is not None:
        if not isinstance(consigne, str) or not 1 <= len(consigne.strip()) <= 8000:
            raise refus("arguments", "la consigne doit compter de 1 à 8000 caractères.")
        motif = motif_trouve(consigne)
        if motif:
            raise refus("secret", T.SECRET_TEXTE.format(motif=motif))
    lu = _carte_en_triage(conn, tableau, carte)
    fiche, tache, demande = lu["fiche"], lu["tache"], lu["demande"]
    genre = graphe.genre_de_triage(demande)
    if genre == "corrections":
        raise refus("prolongation_p6", T.PROLONGATION_P6)
    action = {"tours": "prolongation", "cartes": "prolongation", "sans_plan": "relance_planification"}.get(genre,
                                                                                                           "reprise")
    corps = None if consigne is None else f"{tache.body or ''}\n\n## Décision du propriétaire\n{consigne.strip()}"
    with ka.connexion(tableau) as kc:
        fait = bool(ka.specify_triage_task(kc, carte, body=corps, author=AUTEUR_PROPRIETAIRE))
    plafond = None
    with base.transaction(conn):
        if fait and action == "prolongation":
            colonne = graphe.PLAFONDS[genre]
            pas = 1 if genre == "tours" else int(base.reglage(conn, "prolongation_cartes") or 10)
            avant = int(conn.execute(f"SELECT {colonne} FROM projets WHERE id = ?", (fiche["id"],)).fetchone()[0])
            conn.execute(f"UPDATE projets SET {colonne} = ?, maj_le = ? WHERE id = ?",
                         (avant + pas, base.maintenant(), fiche["id"]))
            plafond = {"genre": genre, "avant": avant, "apres": avant + pas}
        if fait and action != "reprise":
            base.journaliser(conn, auteur, action, projet_id=fiche["id"], cible=carte, detail=plafond)
        base.journaliser(conn, auteur, "triage_repris", projet_id=fiche["id"], cible=carte)
    return {"carte": carte, "reprise": fait, "action": action if fait else None, "plafond": plafond}


def conclure_triage(conn, *, tableau: str, carte: str, auteur: str) -> Dict[str, Any]:
    """Bouton « Conclure » d'une carte de décision du greffon (plafond atteint, planification sans plan) :
    la carte est archivée et le projet s'arrête — « termine » s'il a au moins un tour planifié, sinon
    « abandonne » (rien n'a été fait : ce n'est pas un succès). Aucune notification : c'est le geste du
    propriétaire. Refusé tant qu'une autre carte du projet est ouverte (une synthèse en cours, par exemple)."""
    lu = _carte_en_triage(conn, tableau, carte)
    fiche = lu["fiche"]
    if graphe.genre_de_triage(lu["demande"]) is None:
        raise refus("triage_acp", T.TRIAGE_ACP_SEULEMENT.format(carte=carte))
    with ka.connexion(tableau) as kc:
        autres = [t for t in ka.list_tasks(kc) if t.id != carte and t.status in projets.STATUTS_OUVERTS]
        if autres:
            raise refus("cartes_ouvertes", T.CONCLURE_CARTES_OUVERTES.format(n=len(autres), titre=fiche["titre"]))
        archivee = bool(ka.archive_task(kc, carte))
    etat = "termine" if int(fiche["tour"] or 0) >= 1 else "abandonne"
    with base.transaction(conn):
        conn.execute("UPDATE projets SET etat = ?, termine_le = ?, maj_le = ? WHERE id = ? AND etat = 'actif'",
                     (etat, base.maintenant(), base.maintenant(), fiche["id"]))
        base.journaliser(conn, auteur, "conclusion", projet_id=fiche["id"], cible=carte,
                         detail={"etat": etat, "carte_archivee": archivee})
    return {"carte": carte, "conclu": archivee,
            "projet": projets.resume_projet(conn, projets.projet(conn, fiche["id"]))}


def questions_sans_suite(conn) -> List[str]:
    """Filet de l'émetteur (relecture de P4) : une question « ouverte » dont la carte « répondre » est finie,
    archivée ou bloquée sans question_repondre ni question_escalader est escaladée au propriétaire, avec la
    notification « question » ; sinon la carte du poste resterait planifiée en silence."""
    escaladees = []
    for q in [base.ligne_en_dict(l) for l in conn.execute(
            "SELECT * FROM questions WHERE etat = 'ouverte' AND carte_repondre IS NOT NULL").fetchall()]:
        fiche = projets.projet(conn, q["tableau"])
        if fiche is None:
            continue
        with ka.connexion(q["tableau"]) as kc:
            tache = ka.get_task(kc, q["carte_repondre"])
        if tache is None or tache.status not in ("done", "archived", "blocked"):
            continue
        if question(conn, q["id"])["etat"] != "ouverte":
            continue  # répondue ou escaladée entre-temps
        _escalader(conn, fiche, q, T.MOTIF_SANS_SUITE.format(statut=tache.status), "acp-poste:emetteur")
        escaladees.append(q["id"])
    return escaladees
