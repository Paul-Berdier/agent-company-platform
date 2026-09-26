"""Les HUIT outils de l'agent (jeu ``acp_poste``, cahier P4 § 8) — et ce sont les seuls moyens pour
l'agent de faire créer des cartes : ``kanban_create`` reste refusé par la garde, qui admet exactement ces
huit noms en plus des 26 de P2-P3.

Chaque gestionnaire :

- a la forme ``gestionnaire(args, session_id=None, **_)`` (Hermes filtre les kwargs de contexte par
  signature : tools/registry.py:887-903) ;
- rend TOUJOURS une chaîne JSON ``{"ok": true, …}`` ou ``{"ok": false, "code": …, "message": "Refusé par
  ACP : …"}`` ; il ne lève jamais (sinon Hermes rendrait « Tool execution failed » en anglais) ;
- revérifie le contexte : le tableau et la carte d'un worker viennent de son ENVIRONNEMENT
  (``HERMES_KANBAN_BOARD``, ``owned_kanban_task()``), jamais des arguments du modèle.

Visibilité (décision D23, ``check_fn`` non mis en cache) : en discussion, ``projet_lancer``,
``projet_etat``, ``poste_etat``, ``poste_catalogue`` et ``routage_surcharger`` ; dans le worker d'une carte,
``projet_planifier``, ``projet_etat``, ``poste_etat``, ``poste_catalogue``, ``question_repondre`` et
``question_escalader``. Aucun de ces outils n'ouvre de connexion réseau.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional, Tuple

from . import base, graphe, presence, projets, questions, routage
from . import kanban_adapter as ka
from . import textes as T
from .motifs_secrets import motif_trouve
from .textes import RefusACP, refus

JEU = "acp_poste"
_CHAINE = {"type": "string"}

SCHEMAS: Dict[str, Dict[str, Any]] = {
    "projet_lancer": {
        "name": "projet_lancer",
        "description": ("Lance un projet ACP : crée son tableau, fait explorer le dépôt par le poste (si un dépôt "
                        "est donné) puis planifier par Hermes. Le projet avance ensuite sans vous ; suivez-le par "
                        "projet_etat."),
        "parameters": {"type": "object", "additionalProperties": False, "required": ["titre", "objectif"],
                       "properties": {
                           "titre": {"type": "string", "minLength": 1, "maxLength": 120},
                           "objectif": {"type": "string", "minLength": 1, "maxLength": 4000},
                           "profil": {"type": "string", "enum": list(projets.PROFILS)},
                           "depot": {"type": ["string", "null"],
                                     "description": "Alias d'un dépôt autorisé par le poste, ou null."},
                           "reponses": {"type": "string", "enum": list(projets.POLITIQUES_REPONSE)},
                           "exploration": {"type": "object", "additionalProperties": False, "properties": {
                               "voie": {"type": "string", "enum": ["poste-codex", "poste-claude"]},
                               "modele": _CHAINE, "effort": _CHAINE}}}},
    },
    "projet_planifier": {
        "name": "projet_planifier",
        "description": ("Découpe le projet en étapes (tour courant) ; le greffon crée lui-même les cartes, la "
                        "relecture croisée et la synthèse. À appeler une seule fois par carte de planification ou "
                        "de synthèse, puis terminer par kanban_complete."),
        "parameters": {"type": "object", "additionalProperties": False, "required": ["resume", "etapes"],
                       "properties": {
                           "resume": {"type": "string", "minLength": 1, "maxLength": 2000},
                           "decisions": {"type": "array", "maxItems": 20,
                                         "items": {"type": "string", "minLength": 1, "maxLength": 500}},
                           "etapes": {"type": "array", "minItems": 1, "maxItems": 12, "items": {
                               "type": "object", "additionalProperties": False,
                               "required": ["ref", "titre", "classe", "consigne"],
                               "properties": {
                                   "ref": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,15}$"},
                                   "titre": {"type": "string", "minLength": 1, "maxLength": 120},
                                   "classe": {"type": "string", "enum": list(routage.CLASSES_ETAPE)},
                                   "consigne": {"type": "string", "minLength": 1, "maxLength": 8000},
                                   "voie": {"type": "string", "enum": ["poste-codex", "poste-claude", "hermes"]},
                                   "modele": _CHAINE, "effort": _CHAINE,
                                   "relecture": {"type": "boolean"}, "relecture_modele": _CHAINE,
                                   "depend_de": {"type": "array", "items": _CHAINE},
                                   "fichiers": {"type": "array", "maxItems": 50,
                                                "items": {"type": "string", "maxLength": 300}}}}}}},
    },
    "projet_etat": {
        "name": "projet_etat",
        "description": ("État d'un projet ACP : étape en cours, tour, plafonds restants, cartes (exécutant, modèle "
                        "demandé, effort, résumé), questions ouvertes. Sans paramètre en discussion : la liste des "
                        "projets ; depuis une carte : son propre projet seulement."),
        "parameters": {"type": "object", "additionalProperties": False, "properties": {
            "projet": {"type": "string", "description": "Identifiant (p_…) ou tableau (acp-…) du projet."}}},
    },
    "poste_etat": {
        "name": "poste_etat",
        "description": ("État du poste Windows qui exécute les étapes sur dépôt : non configuré, en ligne ou hors "
                        "ligne, depuis quand, cartes en attente."),
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    "poste_catalogue": {
        "name": "poste_catalogue",
        "description": ("Catalogue relevé du poste : modèles, efforts et paliers de chaque exécutant (poste-codex, "
                        "poste-claude), âge du relevé, quotas, table de routage et politique (efforts interdits, "
                        "paliers admis, voies par classe). « Inconnu » tant que le poste n'a rien publié."),
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    "question_repondre": {
        "name": "question_repondre",
        "description": ("Répond, au nom de Hermes, à la question posée par une carte du poste, en citant la "
                        "décision du projet qui la fonde ; la carte reprend. Seulement depuis la carte « répondre » "
                        "de cette question."),
        "parameters": {"type": "object", "additionalProperties": False, "required": ["reponse", "fondement"],
                       "properties": {
                           "question": {"type": "string", "description": "q_… (facultatif : la question de cette "
                                                                         "carte)."},
                           "reponse": {"type": "string", "minLength": 1, "maxLength": 4000},
                           "fondement": {"type": "string", "minLength": 1, "maxLength": 1000}}},
    },
    "question_escalader": {
        "name": "question_escalader",
        "description": ("Transmet la question au propriétaire (notification) quand les décisions du projet ne la "
                        "couvrent pas. Seulement depuis la carte « répondre » de cette question."),
        "parameters": {"type": "object", "additionalProperties": False, "required": ["motif"],
                       "properties": {
                           "question": {"type": "string", "description": "q_… (facultatif : la question de cette "
                                                                         "carte)."},
                           "motif": {"type": "string", "minLength": 1, "maxLength": 1000}}},
    },
    "routage_surcharger": {
        "name": "routage_surcharger",
        "description": ("Fixe, pour les prochaines cartes d'un projet, l'exécutant, le modèle et l'effort d'une "
                        "classe d'étapes, avec un motif. Une carte existante garde les siens (surcharge d'une carte : "
                        "étape P6). Ne lève jamais un interdit (effort, palier) : seul le propriétaire le fait."),
        "parameters": {"type": "object", "additionalProperties": False,
                       "required": ["portee", "cible", "classe", "voie", "motif"],
                       "properties": {
                           "portee": {"type": "string", "enum": ["projet"]},
                           "cible": {"type": "string", "description": "Projet (p_… ou acp-…)."},
                           "classe": {"type": "string", "enum": sorted(routage.VOIES_PAR_CLASSE)},
                           "voie": {"type": "string", "enum": ["poste-codex", "poste-claude", "hermes"]},
                           "modele": _CHAINE, "effort": _CHAINE,
                           "motif": {"type": "string", "minLength": 1, "maxLength": 500}}},
    },
}
ACTIONS = {"projet_lancer": "le lancement du projet", "projet_planifier": "la planification du tour",
           "projet_etat": "la lecture de l'état du projet", "poste_etat": "la lecture de l'état du poste",
           "poste_catalogue": "la lecture du catalogue", "question_repondre": "la réponse à la question",
           "question_escalader": "l'escalade de la question", "routage_surcharger": "la surcharge de routage"}
LECTURE_SEULE = {"projet_etat", "poste_etat", "poste_catalogue"}
DISCUSSION_SEULE = {"projet_lancer", "routage_surcharger"}
WORKER_SEUL = {"projet_planifier", "question_repondre", "question_escalader"}


# ------------------------------------------------------------------ contexte et visibilité


def contexte() -> Tuple[str, Optional[str], Optional[str]]:
    """(``"discussion"`` | ``"worker"``, tableau, carte) — lus dans l'environnement du processus."""
    carte = ka.owned_kanban_task()
    if not carte:
        return "discussion", None, None
    return "worker", (os.environ.get("HERMES_KANBAN_BOARD") or "").strip() or None, carte


def visible_en_discussion() -> bool:
    return not ka.owned_kanban_task()


def visible_dans_un_worker() -> bool:
    return bool(ka.owned_kanban_task())


def toujours_visible() -> bool:
    return True


ka.no_cache_check_fn(visible_en_discussion)
ka.no_cache_check_fn(visible_dans_un_worker)
ka.no_cache_check_fn(toujours_visible)


def check_fn(nom: str) -> Callable[[], bool]:
    if nom in DISCUSSION_SEULE:
        return visible_en_discussion
    if nom in WORKER_SEUL:
        return visible_dans_un_worker
    return toujours_visible


# ------------------------------------------------------------------ gestionnaires


def _arguments(nom: str, args: Any) -> Dict[str, Any]:
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise refus("arguments", T.ARGUMENTS.format(outil=nom, detail="objet JSON attendu"))
    permis = set(SCHEMAS[nom]["parameters"].get("properties") or {})
    inconnus = sorted(str(k)[:40] for k in args if k not in permis)
    if inconnus:
        raise refus("arguments", T.ARGUMENTS.format(outil=nom, detail="champ inconnu refusé : " + ", ".join(inconnus)))
    for requis in SCHEMAS[nom]["parameters"].get("required") or []:
        if requis not in args:
            raise refus("arguments", T.ARGUMENTS.format(outil=nom, detail=f"« {requis} » manque"))
    return args


def _projet_lancer(args, session_id, conn) -> Dict[str, Any]:
    mode, _tableau, _carte = contexte()
    if mode != "discussion":
        raise refus("contexte", T.CONTEXTE_LANCER)
    exploration = args.get("exploration")
    if exploration is not None and not isinstance(exploration, dict):
        raise refus("arguments", T.ARGUMENTS.format(outil="projet_lancer", detail="« exploration » doit être un objet"))
    resultat = projets.lancer(
        conn, titre=args.get("titre"), objectif=args.get("objectif"), profil=args.get("profil"),
        depot=args.get("depot"), reponses=args.get("reponses"), exploration=exploration, origine="discussion",
        auteur=f"discussion:{session_id or 'inconnue'}",
        cle_idempotence=projets.cle_idempotence_discussion(session_id, args.get("titre"), args.get("objectif"),
                                                           args.get("depot")))
    return resultat


def _projet_planifier(args, session_id, conn) -> Dict[str, Any]:
    mode, tableau, carte = contexte()
    if mode != "worker" or not tableau:
        raise refus("contexte", T.CONTEXTE_PLANIFIER)
    resultat = graphe.planifier(conn, tableau=tableau, carte=carte, resume=args.get("resume"),
                                decisions=args.get("decisions"), etapes=args.get("etapes"))
    resultat.pop("ok", None)
    return resultat


def _projet_etat(args, session_id, conn) -> Dict[str, Any]:
    mode, tableau, _carte = contexte()
    demande = args.get("projet")
    if demande is not None and not isinstance(demande, str):
        raise refus("arguments", T.ARGUMENTS.format(outil="projet_etat", detail="« projet » doit être une chaîne"))
    if mode == "worker":
        fiche = projets.projet(conn, tableau) if tableau else None
        if fiche is None:
            raise refus("contexte", T.PROJET_INTROUVABLE.format(t=tableau or T.INCONNU))
        if demande and demande not in (fiche["id"], fiche["tableau"]):
            raise refus("autre_projet", T.ETAT_AUTRE_PROJET)
        return {"projet": projets.etat(conn, fiche)}
    if demande:
        return {"projet": projets.etat(conn, projets.exiger_projet(conn, demande))}
    return {"projets": projets.lister(conn), "pause_generale": projets.pause_generale() is not None}


def _poste_etat(args, session_id, conn) -> Dict[str, Any]:
    return {"poste": presence.etat_poste(conn)}


def _poste_catalogue(args, session_id, conn) -> Dict[str, Any]:
    return {"catalogue": routage.catalogue(conn)}


def _question_repondre(args, session_id, conn) -> Dict[str, Any]:
    mode, tableau, carte = contexte()
    if mode != "worker" or not tableau:
        raise refus("contexte", T.CONTEXTE_QUESTION.format(outil="question_repondre"))
    return questions.repondre_par_hermes(conn, tableau=tableau, carte=carte, identifiant=args.get("question"),
                                         reponse=args.get("reponse"), fondement=args.get("fondement"))


def _question_escalader(args, session_id, conn) -> Dict[str, Any]:
    mode, tableau, carte = contexte()
    if mode != "worker" or not tableau:
        raise refus("contexte", T.CONTEXTE_QUESTION.format(outil="question_escalader"))
    return questions.escalader(conn, tableau=tableau, carte=carte, identifiant=args.get("question"),
                               motif=args.get("motif"))


def _routage_surcharger(args, session_id, conn) -> Dict[str, Any]:
    mode, _tableau, _carte = contexte()
    if mode != "discussion":
        raise refus("contexte", T.CONTEXTE_SURCHARGER)
    if projets.pause_generale() is not None:
        raise refus("pause_generale", T.PAUSE_GENERALE_LANCER)
    portee = args.get("portee")
    if portee == "globale":
        raise refus("globale", T.SURCHARGE_GLOBALE)
    if portee == "carte":
        # Aucune carte existante ne relit sa surcharge (ni sa correction, préparée pour P6) : répondre « ok »
        # annoncerait un changement qui n'a pas lieu (relecture de P4). Refus explicite jusqu'à P6.
        raise refus("surcharge_carte", T.SURCHARGE_CARTE)
    if portee != "projet":
        raise refus("arguments", T.ARGUMENTS.format(outil="routage_surcharger", detail="portée « projet »"))
    cible = args.get("cible")
    if not isinstance(cible, str) or not cible:
        raise refus("arguments", T.ARGUMENTS.format(outil="routage_surcharger", detail="« cible » manque"))
    fiche = projets.exiger_projet(conn, cible)
    cible_stockee = fiche["id"]
    classe = args.get("classe")
    if classe not in routage.VOIES_PAR_CLASSE:
        raise refus("arguments", T.ARGUMENTS.format(outil="routage_surcharger", detail="classe inconnue"))
    motif = args.get("motif")
    if not isinstance(motif, str) or not 1 <= len(motif.strip()) <= 500:
        raise refus("arguments", T.ARGUMENTS.format(outil="routage_surcharger", detail="motif de 1 à 500 caractères"))
    trouve = motif_trouve(motif)
    if trouve:
        raise refus("secret", T.SECRET_TEXTE.format(motif=trouve))
    resolution = routage.valider_choix(conn, classe=classe, projet=fiche, voie=args.get("voie"),
                                       modele=args.get("modele"), effort=args.get("effort"), palier=None,
                                       source="surcharge_" + portee)
    auteur = f"discussion:{session_id or 'inconnue'}"
    with base.transaction(conn):
        curseur = conn.execute(
            "INSERT INTO surcharges (portee, cible, classe, voie, modele, effort, palier, motif, auteur, cree_le) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (portee, cible_stockee, classe, resolution.voie, args.get("modele") or None, args.get("effort") or None,
             None, motif.strip(), auteur, base.maintenant()))
        base.journaliser(conn, auteur, "surcharge", projet_id=fiche["id"], cible=cible_stockee,
                         detail={"classe": classe, "voie": resolution.voie, "modele": resolution.modele,
                                 "effort": resolution.effort, "motif": motif.strip()})
    return {"surcharge": int(curseur.lastrowid), "resolution": resolution.en_dict()}


FONCTIONS = {"projet_lancer": _projet_lancer, "projet_planifier": _projet_planifier, "projet_etat": _projet_etat,
             "poste_etat": _poste_etat, "poste_catalogue": _poste_catalogue, "question_repondre": _question_repondre,
             "question_escalader": _question_escalader, "routage_surcharger": _routage_surcharger}


def _json(valeur: Dict[str, Any]) -> str:
    return json.dumps(valeur, ensure_ascii=False, default=str)


def executer(nom: str, args: Any, session_id: Optional[str] = None) -> str:
    """Exécute l'outil ``nom`` et rend sa chaîne JSON ; ne lève jamais."""
    try:
        propres = _arguments(nom, args)
        with base.connexion() as conn:
            resultat = FONCTIONS[nom](propres, session_id, conn)
        return _json({"ok": True, **resultat})
    except RefusACP as exc:
        return _json({"ok": False, "code": exc.code, "message": exc.message})
    except BaseException as exc:  # noqa: BLE001 — un outil qui lève rendrait un message anglais de Hermes
        modele = T.ECHEC_OUTIL if nom in LECTURE_SEULE else T.ECHEC_OUTIL_INCERTAIN
        return _json({"ok": False, "code": "echec", "message": modele.format(action=ACTIONS.get(nom, nom),
                                                                              type=type(exc).__name__)})


def _fabriquer(nom: str):
    def gestionnaire(args: Any = None, session_id: Optional[str] = None, **_contexte: Any) -> str:
        return executer(nom, args, session_id)

    gestionnaire.__name__ = f"acp_{nom}"
    return gestionnaire


GESTIONNAIRES = {nom: _fabriquer(nom) for nom in SCHEMAS}


def enregistrer(ctx) -> None:
    """Inscrit les huit outils dans le jeu ``acp_poste`` (hermes_cli/plugins.py:455-499)."""
    for nom, schema in SCHEMAS.items():
        ctx.register_tool(name=nom, toolset=JEU, schema=schema, handler=GESTIONNAIRES[nom], check_fn=check_fn(nom),
                          description=schema["description"], emoji="")
