"""Routes du greffon acp-poste dans le tableau de bord de Hermes.

Hermes importe ce fichier par son chemin et monte ``router`` sous
``/api/plugins/acp-poste/`` au démarrage du tableau de bord
(hermes_cli/web_server_dashboard.py:798-874) ; il ne passe PAS par le paquet du greffon,
d'où le chargement explicite de ``meta.py``, (étape P3) de ``catalogue.py`` et (étape P4) du
noyau sous le nom canonique ``acp_poste_noyau`` (``meta.module_noyau``). Toutes les routes sont
derrière la porte d'authentification du tableau de bord (hermes_cli/dashboard_auth/middleware.py) :
sans session, ``401``.

La lecture des fichiers et de la base se fait hors de la boucle d'événements : le ping des WebSocket
de l'agent tourne sur cette boucle (web_server.py:1158-1164).

Étape P4 — routes des projets (cahier P4 § 11). Erreurs : ``{"detail": {"code", "message"}}`` en
français. Auteur de chaque geste : ``proprietaire:<user_id de la session>``. Toute route d'ÉCRITURE
exige ``Content-Type: application/json`` (415 sinon) et refuse un ``Origin`` présent et différent de
``HERMES_DASHBOARD_PUBLIC_URL`` (403) : le cookie de session est ``SameSite=Lax`` et
``up.railway.app`` est un suffixe public.

- ``GET  /v1/projets``                         liste, compteurs, poste, pause générale, notifications
- ``POST /v1/projets``                         lancement (``Idempotency-Key`` facultatif) → 201
- ``GET  /v1/projets/{id}``                    détail et journal → 200, 404
- ``GET  /v1/projets/{id}/cartes/{carte}``     résumé ENTIER d'une carte du projet → 200, 404
- ``POST /v1/projets/{id}/pause`` ``/reprise`` pause et reprise d'un projet → 200, 409
- ``GET  /v1/questions``                       questions ouvertes ; cartes en triage, bloquées, abandonnées
- ``POST /v1/questions/{q}/reponse``           réponse du propriétaire → 200, 404, 409
- ``POST /v1/triage/{tableau}/{carte}/reprendre`` reprise d'une carte en triage (« Prolonger » ou « Relancer »
                                               pour une carte de décision du greffon) → 200, 404, 409
- ``POST /v1/triage/{tableau}/{carte}/conclure``  « Conclure » une carte de décision du greffon → 200, 404, 409
- ``POST /v1/pause``                           pause générale (arrêt d'urgence de Hermes) ou reprise (409 tant
                                               que des crochets shell sont déclarés)
- ``GET  /v1/poste``                           présence et catalogue du poste
- ``POST /v1/notifications/test``              notification de test (envoyée par la passerelle) → 202, 409
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.parse
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

_DOSSIER_GREFFON = Path(__file__).resolve().parent.parent


def _charger(nom: str) -> ModuleType:
    cle = f"acp_poste_greffon_{nom}"
    module = sys.modules.get(cle)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(cle, _DOSSIER_GREFFON / f"{nom}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"module {nom}.py du greffon acp-poste introuvable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cle] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(cle, None)
        raise
    return module


_meta = _charger("meta")
_catalogue = _charger("catalogue")

router = APIRouter()


def mesurer_reseau(request: Request) -> Dict[str, Any]:
    """Ce que le tableau de bord voit de la requête : pair, schéma, hôte, et la seule PRÉSENCE des
    en-têtes posés par un bord (jamais la valeur de X-Forwarded-For, qui porte l'adresse du
    client). Sert à mesurer le bord Railway avant de renseigner dashboard.trusted_proxies."""
    entetes = request.headers
    return {
        "pair": request.client.host if request.client else None,
        "schema_vu": request.url.scheme,
        "hote": entetes.get("host"),
        "entetes_transmis": {nom: nom in entetes for nom in _meta.ENTETES_MESURES},
        "x_forwarded_proto": (entetes.get("x-forwarded-proto") or "")[:16] or None,
    }


@router.get("/v1/meta")
async def lire_meta(request: Request) -> Dict[str, Any]:
    """Contrat, versions (greffon, Hermes en cours et testée), OpenRPC, état du démarrage, garde
    d'exécution du processus du tableau de bord, mesure réseau, commit déployé et (P4) projets."""
    return await run_in_threadpool(_meta.construire_meta, reseau=mesurer_reseau(request))


@router.get("/v1/catalogue")
async def lire_catalogue() -> Dict[str, Any]:
    """Étape P3 : verrou du catalogue livré dans l'image et état de chaque skill et serveur MCP tel
    que le chargeur de Hermes le voit dans ce processus (lecture seule ; aucune action)."""
    return await run_in_threadpool(_catalogue.construire_catalogue)


# ============================================================ étape P4 : projets


def _n(nom: str) -> ModuleType:
    return _meta.sous_module_noyau(nom)


CODES_HTTP = {
    "projet_inconnu": 404, "question_inconnue": 404, "triage_inconnu": 404, "carte_inconnue": 404,
    "pause_generale": 409, "projets_actifs": 409, "lancements_jour": 409, "deja_en_pause": 409,
    "pas_en_pause": 409, "projet_fini": 409, "question_fermee": 409, "notifications": 409,
    "projet_en_pause": 409, "cartes_ouvertes": 409, "prolongation_p6": 409, "triage_acp": 409, "crochets": 409,
}


def _erreur(statut: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=statut, content={"detail": {"code": code, "message": message}})


def _session(request: Request) -> Optional[str]:
    session = getattr(request.state, "session", None)
    identifiant = getattr(session, "user_id", None)
    return f"proprietaire:{identifiant}" if identifiant else None


def _origine_publique() -> Optional[str]:
    url = (os.environ.get("HERMES_DASHBOARD_PUBLIC_URL") or "").strip()
    if not url:
        return None
    parties = urllib.parse.urlsplit(url)
    return f"{parties.scheme}://{parties.netloc}".lower() if parties.scheme and parties.netloc else None


async def _garde_ecriture(request: Request) -> Any:
    """(auteur, corps) d'une requête d'écriture, ou la réponse de refus (401, 403, 415, 400)."""
    auteur = _session(request)
    if auteur is None:
        return _erreur(401, "session", "Session du tableau de bord requise.")
    origine = request.headers.get("origin")
    if origine is not None and origine.strip().lower().rstrip("/") != (_origine_publique() or ""):
        return _erreur(403, "origine", f"Requête refusée : origine « {origine[:100]} » non autorisée.")
    type_ = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if type_ != "application/json":
        return _erreur(415, "json", "Requête refusée : corps JSON attendu.")
    brut = await request.body()
    if len(brut) > 64 * 1024:
        return _erreur(413, "taille", "Requête refusée : corps de plus de 64 Kio.")
    try:
        corps = json.loads(brut.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return _erreur(400, "json", "Requête refusée : corps JSON illisible.")
    if not isinstance(corps, dict):
        return _erreur(400, "json", "Requête refusée : un objet JSON est attendu.")
    return auteur, corps


async def _executer(fonction: Callable[..., Any], *args: Any, statut: int = 200, **kwargs: Any) -> JSONResponse:
    """Exécute ``fonction`` hors de la boucle ; un refus du noyau devient une erreur française."""
    textes = _n("textes")
    try:
        resultat = await run_in_threadpool(fonction, *args, **kwargs)
    except textes.RefusACP as exc:
        return _erreur(CODES_HTTP.get(exc.code, 400), exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 — jamais une trace brute au navigateur
        return _erreur(500, "echec", f"Échec d'ACP ({type(exc).__name__}) : consultez l'état avant de réessayer.")
    if isinstance(resultat, tuple):
        statut, resultat = resultat
    return JSONResponse(status_code=statut, content=json.loads(json.dumps(resultat, ensure_ascii=False, default=str)))


def _avec_base(travail: Callable[[Any], Any]) -> Callable[[], Any]:
    def enveloppe() -> Any:
        with _n("base").connexion() as conn:
            return travail(conn)
    return enveloppe


def _etat_notifications(conn) -> Dict[str, Any]:
    """État PUBLIC du canal, publié par la passerelle. Tant qu'elle ne l'a pas publié, l'état est INCONNU, et le
    message le dit (jamais « non configurées » sans le savoir)."""
    canal = _n("base").lire_emetteur(conn, "canal") or {}
    textes = _n("textes")
    message = (None if canal.get("configure") else textes.NOTIFICATIONS_NON_CONFIGUREES if canal
               else textes.NOTIFICATIONS_ETAT_INCONNU)
    return {"canal": canal.get("canal"), "configure": bool(canal.get("configure")), "connu": bool(canal),
            "message": message}


@router.get("/v1/projets")
async def lister_projets() -> JSONResponse:
    def travail(conn):
        projets = _n("projets")
        return {"projets": projets.lister(conn), "poste": _n("presence").etat_poste(conn),
                "pause_generale": projets.pause_generale(), "notifications": _etat_notifications(conn),
                "questions_ouvertes": conn.execute(
                    "SELECT COUNT(*) FROM questions WHERE etat IN ('ouverte', 'escaladee')").fetchone()[0]}
    return await _executer(_avec_base(travail))


@router.post("/v1/projets")
async def lancer_projet(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    inconnus = sorted(set(corps) - {"titre", "objectif", "profil", "depot", "reponses", "exploration"})
    if inconnus:
        return _erreur(400, "arguments", "Refusé par ACP : champ inconnu refusé : " + ", ".join(inconnus)[:200] + ".")
    cle = (request.headers.get("idempotency-key") or "").strip()[:128] or None

    def travail(conn):
        resultat = _n("projets").lancer(
            conn, titre=corps.get("titre"), objectif=corps.get("objectif"), profil=corps.get("profil"),
            depot=corps.get("depot"), reponses=corps.get("reponses"), exploration=corps.get("exploration"),
            origine="tableau_de_bord", auteur=auteur, cle_idempotence=f"tableau_de_bord:{cle}" if cle else None)
        return (200 if resultat["deja_lance"] else 201), resultat
    return await _executer(_avec_base(travail))


@router.get("/v1/projets/{identifiant}")
async def lire_projet(identifiant: str) -> JSONResponse:
    def travail(conn):
        projets = _n("projets")
        return {"projet": projets.etat(conn, projets.exiger_projet(conn, identifiant), avec_journal=True)}
    return await _executer(_avec_base(travail))


@router.get("/v1/projets/{identifiant}/cartes/{carte}")
async def lire_carte_du_projet(identifiant: str, carte: str) -> JSONResponse:
    """Résumé ENTIER d'une carte (le détail du projet n'en rend que 500 caractères, et le dit)."""
    def travail(conn):
        projets = _n("projets")
        return {"carte": projets.lire_carte(conn, projets.exiger_projet(conn, identifiant), carte)}
    return await _executer(_avec_base(travail))


@router.post("/v1/projets/{identifiant}/pause")
async def pause_projet(identifiant: str, request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, _corps = garde
    return await _executer(_avec_base(lambda conn: _n("projets").mettre_en_pause(conn, identifiant, auteur=auteur)))


@router.post("/v1/projets/{identifiant}/reprise")
async def reprise_projet(identifiant: str, request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, _corps = garde
    return await _executer(_avec_base(lambda conn: _n("projets").reprendre(conn, identifiant, auteur=auteur)))


@router.get("/v1/questions")
async def lister_questions() -> JSONResponse:
    return await _executer(_avec_base(lambda conn: _n("questions").lister(conn)))


@router.post("/v1/questions/{question}/reponse")
async def repondre_question(question: str, request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    return await _executer(_avec_base(lambda conn: _n("questions").repondre_par_proprietaire(
        conn, question, reponse=corps.get("reponse"), auteur=auteur)))


@router.post("/v1/triage/{tableau}/{carte}/reprendre")
async def reprendre_triage(tableau: str, carte: str, request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    return await _executer(_avec_base(lambda conn: _n("questions").reprendre_triage(
        conn, tableau=tableau, carte=carte, consigne=corps.get("consigne"), auteur=auteur)))


@router.post("/v1/triage/{tableau}/{carte}/conclure")
async def conclure_triage(tableau: str, carte: str, request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, _corps = garde
    return await _executer(_avec_base(lambda conn: _n("questions").conclure_triage(
        conn, tableau=tableau, carte=carte, auteur=auteur)))


@router.post("/v1/pause")
async def pause_generale(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    generale = corps.get("generale")
    if type(generale) is not bool:
        return _erreur(400, "arguments", "Refusé par ACP : « generale » doit valoir true ou false.")
    raison = corps.get("raison")
    if raison is not None and (not isinstance(raison, str) or len(raison) > 200):
        return _erreur(400, "arguments", "Refusé par ACP : la raison compte 200 caractères au plus.")

    def travail(conn):
        base, ka, textes = _n("base"), _n("kanban_adapter"), _n("textes")
        if generale:
            ka.engage(textes.RAISON_PAUSE_PROPRIETAIRE + (f" — {raison.strip()}" if raison and raison.strip() else ""))
        else:
            # Relecture de P4 : la veille des crochets shell (D34) a engagé la pause ; la lever alors qu'ils sont
            # toujours là laisserait le répartiteur lancer des workers avec --accept-hooks avant la passe suivante.
            constats = _n("emetteur").crochets_detectes()
            if constats:
                raise textes.RefusACP("crochets", textes.REPRISE_CROCHETS.format(constats="; ".join(constats)[:300]))
            ka.disengage()
        base.poser_reglage(conn, "pause_reclamations", 1 if generale else 0, auteur)
        with base.transaction(conn):
            base.journaliser(conn, auteur, "pause_generale" if generale else "reprise_generale")
        return {"pause_generale": _n("projets").pause_generale()}
    return await _executer(_avec_base(travail))


@router.get("/v1/poste")
async def lire_poste() -> JSONResponse:
    return await _executer(_avec_base(lambda conn: {"poste": _n("presence").etat_poste(conn),
                                                    "catalogue": _n("routage").catalogue(conn)}))


@router.post("/v1/notifications/test")
async def notification_de_test(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, _corps = garde

    def travail(conn):
        base, notifications, textes = _n("base"), _n("notifications"), _n("textes")
        etat = _etat_notifications(conn)
        if not etat["configure"]:
            raise textes.RefusACP("notifications", etat["message"])
        cle = f"test:{base.maintenant()}"
        notifications.enfiler(conn, cle=cle, genre="test", texte_notif=notifications.texte(textes.NOTIF_TEST))
        with base.transaction(conn):
            base.journaliser(conn, auteur, "notification_test", cible=cle)
        return 202, {"notification": cle, "etat": "en_attente",
                     "message": "Notification de test mise en file : la passerelle l'envoie à sa prochaine passe."}
    return await _executer(_avec_base(travail))
