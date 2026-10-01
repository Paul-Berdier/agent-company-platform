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
- ``GET  /v1/poste``                           présence et catalogue du poste (étape P5 : état, poste courant,
                                               dernier inventaire, alertes, ordres en attente)
- ``POST /v1/notifications/test``              notification de test (envoyée par la passerelle) → 202, 409

Étape P5 — poste connecté (cahier P5 § 4, § 12.3) :

- ``POST /machine/v1/enrolement``              porteur : code d'enrôlement → 201 (jeton machine, une fois)
- ``POST /machine/v1/reclamer``                porteur : jeton machine ; long-poll ≤ 50 s, ordres, présence
- ``POST /machine/v1/inventaire``              porteur : jeton machine ; inventaire tout ou rien → 200, 429
- ``POST /v1/poste/enrolement``                code d'enrôlement (10 min), rendu une fois → 201, 409
- ``POST /v1/poste/confirmation`` ``/revocation`` ``/releve``  confirmer l'empreinte, révoquer, relever maintenant
- ``GET  /v1/routage`` ; ``POST /v1/routage``  vue et validation de la table (tout ou rien) → 200, 409, 422
- ``POST /v1/routage/politique`` ``/surcharges`` ``/surcharges/{id}/desactiver`` ``/releve-accepte``
- ``GET  /v1/quotas``                          quotas par voie (relevés, jamais estimés)

Les trois routes machine ne sont jamais servies à une session de navigateur : la couture de Hermes les réserve au
porteur d'un jeton reconnu (chemins exacts enregistrés par register()).
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
    profondeur = _contrat_machine().PROFONDEUR_MAX_CORPS
    try:
        corps = json.loads(brut.decode("utf-8") or "{}")
    except RecursionError:  # n'hérite pas de ValueError (relecture de P5)
        return _erreur(400, "json", "Requête refusée : " + _n("textes").CORPS_TROP_IMBRIQUE.format(n=profondeur))
    except (UnicodeDecodeError, ValueError):
        return _erreur(400, "json", "Requête refusée : corps JSON illisible.")
    if not isinstance(corps, dict):
        return _erreur(400, "json", "Requête refusée : un objet JSON est attendu.")
    if _profondeur_depasse(corps, profondeur):
        return _erreur(400, "json", "Requête refusée : " + _n("textes").CORPS_TROP_IMBRIQUE.format(n=profondeur))
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
        # Étape P5 : le poste actif reçoit l'ordre (affichage seulement en P5 ; en P6, plus de réclamation).
        actif = _n("machines").machine_active(conn)
        if actif is not None:
            ordonner(actif["id"], "pause" if generale else "reprise", auteur)
        return {"pause_generale": _n("projets").pause_generale()}
    return await _executer(_avec_base(travail))


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


# ============================================================ étape P5 : routes machine du poste (acp-machine/1)
#
# Trois chemins EXACTS, enregistrés comme chemins à jeton par register() (noyau/jeton_machine.py) : la couture de
# Hermes (hermes_cli/dashboard_auth/token_auth.py:75-96) authentifie le porteur AVANT ces gestionnaires et y
# attache ``request.state.token_principal`` ; sans porteur reconnu, elle répond elle-même 401 (anglais, ambigu)
# ou 503. Chaque gestionnaire revérifie, dans cet ordre (cahier P5 § 4.2) : principal présent (401), fournisseur
# acp-poste-machine (403), portée (403), JSON, taille et protocole (415, 413, 409), puis relit l'état du poste DANS
# sa transaction (une révocation entre la couture et le gestionnaire est vue : 401 poste_revoque).

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import logging  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

_log = logging.getLogger(__name__)
FOURNISSEUR_MACHINE = "acp-poste-machine"
SANS_CACHE = {"Cache-Control": "no-store"}
CODES_HTTP_MACHINE = {
    "non_authentifie": 401, "poste_revoque": 401, "mauvais_fournisseur": 403, "code_enrolement_seulement": 403,
    "jeton_machine_ici": 403, "poste_a_confirmer": 403, "poste_deja_enrole": 409, "protocole_incompatible": 409,
    "trop_volumineux": 413, "json_attendu": 415, "requete_refusee": 422, "trop_frequent": 429, "echec": 500,
}
ATTENTE_A_CONFIRMER_S = 15
RELECTURE_S = 2.0
REMPLACEMENTS_ALERTE = 5


def _contrat_machine() -> ModuleType:
    _n("contrat_partage")
    import acp_poste_contrat.machine as machine

    return machine


def _profondeur_depasse(corps: Any, maximum: int) -> bool:
    _n("contrat_partage")
    from acp_poste_contrat.inventaire import profondeur_depasse

    return profondeur_depasse(corps, maximum)


def _erreur_machine(code: str, message: str, entetes: Optional[Dict[str, str]] = None) -> JSONResponse:
    return JSONResponse(status_code=CODES_HTTP_MACHINE.get(code, 400), content={"detail": {"code": code,
                        "message": message}}, headers=dict(SANS_CACHE, **(entetes or {})))


def _reponse_machine(statut: int, contenu: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=statut, content=contenu, headers=SANS_CACHE)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _garde_machine(request: Request, portee: str, taille_max: int) -> Any:
    """(principal, corps) d'une requête du poste, ou la réponse de refus. ``portee`` : ``enrolement`` ou ``machine``."""
    textes = _n("textes")
    principal = getattr(request.state, "token_principal", None)
    if principal is None:
        return _erreur_machine("non_authentifie", textes.MACHINE_NON_AUTHENTIFIE)
    if getattr(principal, "provider", None) != FOURNISSEUR_MACHINE:
        return _erreur_machine("mauvais_fournisseur", textes.MAUVAIS_FOURNISSEUR)
    portees = tuple(getattr(principal, "scopes", ()) or ())
    if portee == "enrolement" and "enrolement" not in portees:
        return _erreur_machine("jeton_machine_ici", textes.JETON_MACHINE_ICI)
    if portee == "machine" and "machine" not in portees:
        return _erreur_machine("code_enrolement_seulement", textes.CODE_ENROLEMENT_SEULEMENT)
    type_ = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if type_ != "application/json":
        return _erreur_machine("json_attendu", textes.JSON_ATTENDU)
    kio = taille_max // 1024
    longueur = request.headers.get("content-length")
    if longueur is not None and (not longueur.isdigit() or int(longueur) > taille_max):
        return _erreur_machine("trop_volumineux", textes.TROP_VOLUMINEUX.format(n=kio))
    brut = b""
    async for morceau in request.stream():
        brut += morceau
        if len(brut) > taille_max:
            return _erreur_machine("trop_volumineux", textes.TROP_VOLUMINEUX.format(n=kio))
    profondeur = _contrat_machine().PROFONDEUR_MAX_CORPS
    trop_imbrique = textes.REQUETE_REFUSEE.format(detail=textes.CORPS_TROP_IMBRIQUE.format(n=profondeur))
    try:
        corps = json.loads(brut.decode("utf-8"))
    except RecursionError:  # n'hérite pas de ValueError : 500 en texte brut sans ce cas (relecture de P5)
        return _erreur_machine("requete_refusee", trop_imbrique)
    except (UnicodeDecodeError, ValueError):
        return _erreur_machine("requete_refusee", textes.REQUETE_REFUSEE.format(detail="corps JSON illisible."))
    if not isinstance(corps, dict):
        return _erreur_machine("requete_refusee", textes.REQUETE_REFUSEE.format(detail="un objet JSON est attendu."))
    if _profondeur_depasse(corps, profondeur):  # borne AVANT le balayage et le contrat (relecture de P5)
        return _erreur_machine("requete_refusee", trop_imbrique)
    protocole = corps.get("protocole")
    if isinstance(protocole, str) and _contrat_machine().majeure(protocole) not in (None, 1):
        return _erreur_machine("protocole_incompatible", textes.PROTOCOLE_INCOMPATIBLE.format(p=protocole[:20]))
    return principal, corps


def _valider(modele_nom: str, corps: Dict[str, Any]) -> Any:
    """Requête validée par le contrat partagé, ou la réponse 422 en français."""
    machine = _contrat_machine()
    try:
        return machine.valider(getattr(machine, modele_nom), corps, quoi="Requête refusée")
    except ValueError as exc:
        detail = str(exc).removeprefix("Requête refusée : ")
        return _erreur_machine("requete_refusee", _n("textes").REQUETE_REFUSEE.format(detail=detail[:400]))


def _machine_du_principal(principal: Any) -> str:
    return str(getattr(principal, "principal", "")).removeprefix("acp-poste:")


def _refus_revoque(ligne: Optional[Dict[str, Any]]) -> JSONResponse:
    textes, routage = _n("textes"), _n("routage")
    if ligne is None:
        return _erreur_machine("poste_revoque", textes.POSTE_INCONNU_MACHINE)
    return _erreur_machine("poste_revoque", textes.POSTE_REVOQUE.format(date=routage.date_lisible(ligne["revoque_le"])))


async def _executer_machine(fonction: Callable[..., Any], *args: Any) -> Any:
    """``fonction`` hors de la boucle ; un refus du noyau devient l'erreur machine ; jamais une trace brute."""
    textes = _n("textes")
    try:
        return await run_in_threadpool(fonction, *args)
    except textes.RefusACP as exc:
        entetes = {"Retry-After": str(exc.retry_after)} if hasattr(exc, "retry_after") else None
        return _erreur_machine(exc.code, exc.message, entetes)
    except Exception as exc:  # noqa: BLE001
        _log.warning("acp-poste : route machine en échec (%s).", type(exc).__name__)
        return _erreur_machine("echec", textes.ECHEC_MACHINE.format(type=type(exc).__name__))


@router.post("/machine/v1/enrolement")
async def machine_enrolement(request: Request) -> JSONResponse:
    """Porteur : code d'enrôlement ``acpe_…`` (usage unique). 201 : le SEUL message qui contienne le jeton."""
    garde = await _garde_machine(request, "enrolement", _contrat_machine().TAILLE_MAX_REQUETE)
    if isinstance(garde, JSONResponse):
        return garde
    principal, corps = garde
    requete = _valider("RequeteEnrolement", corps)
    if isinstance(requete, JSONResponse):
        return requete
    porteur = request.headers.get("authorization", "").split(" ", 1)[-1].strip()
    empreinte = hashlib.sha256(porteur.encode("ascii", "replace")).hexdigest()
    if str(getattr(principal, "principal", "")) != f"enrolement:{empreinte[:12]}":
        return _erreur_machine("non_authentifie", _n("textes").CODE_REFUSE)

    def travail():
        base, machines = _n("base"), _n("machines")
        with base.connexion() as conn:
            with base.transaction(conn):
                return machines.enroler_dans(conn, empreinte, nom=requete.nom, version_poste=requete.version_poste,
                                             protocole=requete.protocole)
    resultat = await _executer_machine(travail)
    if isinstance(resultat, JSONResponse):
        return resultat
    return _reponse_machine(201, resultat)


class _Attente:
    """Attente en cours d'un poste : sa boucle et son événement (réveil sûr depuis un fil : call_soon_threadsafe)."""

    def __init__(self, boucle: asyncio.AbstractEventLoop) -> None:
        self.boucle = boucle
        self.evenement = asyncio.Event()
        self.remplacee = False

    def reveiller(self) -> None:
        try:
            self.boucle.call_soon_threadsafe(self.evenement.set)
        except RuntimeError:  # boucle fermée : l'attente est déjà finie
            pass


# Attentes par poste : UNE copie de ce dictionnaire, dans ce module, que partagent les routes machine et les routes
# du propriétaire (toutes ici). La plus récente attente gagne : elle réveille l'ancienne, qui rend « remplace ».
_attentes: Dict[str, _Attente] = {}
_verrou_attentes = threading.Lock()


def reveiller_le_poste(machine_id: Optional[str]) -> bool:
    """Réveille l'attente en cours du poste (ordre, révocation, pause) ; sûr depuis n'importe quel fil."""
    if not machine_id:
        return False
    with _verrou_attentes:
        attente = _attentes.get(machine_id)
    if attente is None:
        return False
    attente.reveiller()
    return True


def attentes_en_cours() -> Dict[str, int]:
    with _verrou_attentes:
        return {m: 1 for m in _attentes}


def ordonner(machine_id: str, genre: str, auteur: str) -> int:
    """Crée un ordre pour le poste puis réveille son attente (appelée DANS un fil : routes du propriétaire)."""
    base, ordres = _n("base"), _n("ordres")
    with base.connexion() as conn:
        identifiant = ordres.creer(conn, machine_id, genre, auteur)
    reveiller_le_poste(machine_id)
    return identifiant


def revoquer(machine_id: Any, motif: Any, auteur: str) -> Dict[str, Any]:
    """Révoque le poste puis réveille son attente, qui rend 401 ``poste_revoque`` (appelée DANS un fil)."""
    base, machines = _n("base"), _n("machines")
    with base.connexion() as conn:
        etat = machines.revoquer(conn, machine_id, motif, auteur)
    reveiller_le_poste(str(machine_id))
    return etat


def _premier_passage(machine_id: str, requete: Any, remplacement: bool) -> Dict[str, Any]:
    """Sous UNE transaction : état relu, dernière requête, politique annoncée, acquittements, présence (poste
    confirmé seulement), ordres dus livrés, compteur de remplacements."""
    base, machines, ordres, presence = _n("base"), _n("machines"), _n("ordres"), _n("presence")
    with base.connexion() as conn:
        with base.transaction(conn):
            ligne = machines.machine(conn, machine_id)
            if ligne is None or ligne["etat"] == "revoque":
                return {"revoque": ligne}
            maintenant = base.maintenant()
            depuis = ligne["remplacements_depuis"] or 0
            compte = int(ligne["remplacements_minute"] or 0)
            if remplacement:
                compte, depuis = (compte + 1, depuis) if maintenant - depuis < 60 else (1, maintenant)
            conn.execute("UPDATE machines SET derniere_requete = ?, politique_valide = ?, remplacements_minute = ?, "
                         "remplacements_depuis = ? WHERE id = ?",
                         (maintenant, 1 if requete.politique_valide else 0, compte, depuis, machine_id))
            ordres.acquitter_dans(conn, machine_id, requete.ordres_acquittes)
            pause = bool(base.reglage(conn, "pause_reclamations"))
            if ligne["etat"] != "actif":
                return {"etat": ligne["etat"], "ordres": [], "pause": pause}
            presence.enregistrer_dans(conn, machine_id, "longpoll")
            dus = ordres.dus(conn, machine_id)
            ordres.livrer_dans(conn, [o["id"] for o in dus])
            return {"etat": "actif", "ordres": dus, "pause": pause,
                    "attente_s": int(base.reglage(conn, "longpoll_attente_s") or 25)}


def _relecture(machine_id: str) -> Dict[str, Any]:
    """Relecture périodique pendant l'attente : état (révocation) et ordres dus (écrits par un autre processus)."""
    base, machines, ordres = _n("base"), _n("machines"), _n("ordres")
    with base.connexion() as conn:
        with base.transaction(conn):
            ligne = machines.machine(conn, machine_id)
            if ligne is None or ligne["etat"] == "revoque":
                return {"revoque": ligne}
            pause = bool(base.reglage(conn, "pause_reclamations"))
            if ligne["etat"] != "actif":
                return {"etat": ligne["etat"], "ordres": [], "pause": pause}
            dus = ordres.dus(conn, machine_id)
            ordres.livrer_dans(conn, [o["id"] for o in dus])
            return {"etat": "actif", "ordres": dus, "pause": pause}


async def _deconnecte(request: Request) -> bool:
    """Le poste a-t-il coupé la connexion ? ``request.is_disconnected()`` seul ne le voit pas derrière les intergiciels
    HTTP empilés de Hermes (BaseHTTPMiddleware : sa lecture pré-annulée n'atteint jamais le serveur) ; une lecture
    bornée à 50 ms, elle, reçoit le ``http.disconnect`` du serveur (le corps est déjà lu : rien d'autre n'arrive)."""
    if await request.is_disconnected():
        return True
    import anyio

    try:
        with anyio.move_on_after(0.05):
            message = await request.receive()
            return message.get("type") == "http.disconnect"
    except Exception:  # noqa: BLE001 — dans le doute, l'attente reste bornée par son échéance
        return False
    return False


def _reponse_reclamer(etat: str, ordres: list, pause: bool, *, remplace: bool = False,
                      prochaine: int = 0) -> JSONResponse:
    contenu = {"maintenant": _iso(time.time()), "etat_machine": etat, "pause_reclamations": bool(pause),
               "ordres": ordres, "carte": None, "remplace": remplace, "prochaine_attente_s": prochaine}
    return _reponse_machine(200, contenu)


@router.post("/machine/v1/reclamer")
async def machine_reclamer(request: Request) -> JSONResponse:
    """Long-poll du poste (cahier P5 § 4.5) : présence, ordres ; ``carte`` toujours ``null`` en P5. Jamais un fil
    tenu pendant l'attente : la boucle attend un ``asyncio.Event`` et relit la base toutes les 2 s en fil."""
    garde = await _garde_machine(request, "machine", _contrat_machine().TAILLE_MAX_REQUETE)
    if isinstance(garde, JSONResponse):
        return garde
    principal, corps = garde
    requete = _valider("RequeteReclamer", corps)
    if isinstance(requete, JSONResponse):
        return requete
    machine_id = _machine_du_principal(principal)
    attente = _Attente(asyncio.get_running_loop())
    with _verrou_attentes:
        ancienne = _attentes.get(machine_id)
        _attentes[machine_id] = attente
    if ancienne is not None:
        ancienne.remplacee = True
        ancienne.reveiller()
    try:
        etat = await _executer_machine(_premier_passage, machine_id, requete, ancienne is not None)
        if isinstance(etat, JSONResponse):
            return etat
        if "revoque" in etat:
            return _refus_revoque(etat["revoque"])
        if etat["etat"] != "actif":
            return _reponse_reclamer(etat["etat"], [], etat["pause"], prochaine=ATTENTE_A_CONFIRMER_S)
        if etat["ordres"]:
            return _reponse_reclamer("actif", etat["ordres"], etat["pause"])
        boucle = asyncio.get_running_loop()
        echeance = boucle.time() + min(requete.attente_max_s, max(5, min(50, etat["attente_s"])))
        pause = etat["pause"]
        while True:
            reste = echeance - boucle.time()
            if reste <= 0:
                return _reponse_reclamer("actif", [], pause)
            try:
                await asyncio.wait_for(attente.evenement.wait(), timeout=min(RELECTURE_S, reste))
            except asyncio.TimeoutError:
                pass
            if attente.remplacee:
                return _reponse_reclamer("actif", [], pause, remplace=True)
            attente.evenement.clear()
            if await _deconnecte(request):
                return _reponse_reclamer("actif", [], pause)
            etat = await _executer_machine(_relecture, machine_id)
            if isinstance(etat, JSONResponse):
                return etat
            if "revoque" in etat:
                return _refus_revoque(etat["revoque"])
            if etat["etat"] != "actif":
                return _reponse_reclamer(etat["etat"], [], etat["pause"], prochaine=ATTENTE_A_CONFIRMER_S)
            pause = etat["pause"]
            if etat["ordres"]:
                return _reponse_reclamer("actif", etat["ordres"], pause)
    finally:
        with _verrou_attentes:
            if _attentes.get(machine_id) is attente:
                del _attentes[machine_id]


@router.post("/machine/v1/inventaire")
async def machine_inventaire(request: Request) -> JSONResponse:
    """Inventaire du poste (cahier P5 § 4.3) : tout ou rien, sous UNE transaction ``IMMEDIATE``."""
    garde = await _garde_machine(request, "machine", _contrat_machine().TAILLE_MAX_INVENTAIRE)
    if isinstance(garde, JSONResponse):
        return garde
    principal, corps = garde
    machine_id = _machine_du_principal(principal)
    textes = _n("textes")

    def valider():
        return _n("inventaire").valider_corps(corps)
    inventaire = await _executer_machine(valider)
    if isinstance(inventaire, JSONResponse):
        return inventaire

    def travail():
        base, machines, module_inventaire = _n("base"), _n("machines"), _n("inventaire")
        with base.connexion() as conn:
            with base.transaction(conn):
                ligne = machines.machine(conn, machine_id)
                if ligne is None or ligne["etat"] == "revoque":
                    return {"revoque": ligne}
                if ligne["etat"] == "a_confirmer":
                    raise textes.RefusACP("poste_a_confirmer", textes.POSTE_A_CONFIRMER.format(
                        empreinte=machines.empreinte_affichee(ligne)))
                delai = module_inventaire.delai_avant_prochain(conn, machine_id)
                if delai > 0:
                    raise module_inventaire.TropFrequent(delai)
                return module_inventaire.recevoir_dans(conn, machine_id, corps, inventaire=inventaire)
    resultat = await _executer_machine(travail)
    if isinstance(resultat, JSONResponse):
        return resultat
    if "revoque" in resultat:
        return _refus_revoque(resultat["revoque"])
    return _reponse_machine(200, resultat)


def _ecrire_demarrage() -> None:
    """Grâce de redémarrage (cahier P5 § 4.7) : date de démarrage du tableau de bord, écrite à l'import."""
    try:
        with _n("base").connexion() as conn:
            _n("presence").ecrire_demarrage_tableau_de_bord(conn)
    except Exception as exc:  # noqa: BLE001 — la passerelle se fie alors à son propre démarrage
        _log.warning("acp-poste : date de démarrage du tableau de bord non écrite (%s).", type(exc).__name__)


_ecrire_demarrage()


# ============================================================ étape P5 : routes du propriétaire (pages Poste, Routage, Quotas)
#
# Session du tableau de bord et règles d'écriture de P4 (JSON exigé, Origin contrôlé : _garde_ecriture). Cahier P5
# § 12.3. Un refus de routage d'une surcharge ou d'une table rend 422 (entrée refusée), jamais une entrée admise en
# silence ; la table refusée rend la liste des refus, entrée par entrée.

CODES_HTTP.update({
    "machine_inconnue": 404, "releve_inconnu": 404, "surcharge_inconnue": 404,
    "empreinte_differente": 409, "pas_a_confirmer": 409, "deja_revoque": 409, "poste_deja_enrole": 409,
    "aucun_poste_actif": 409, "releve_change": 409, "releve_non_acceptable": 409, "releve_plus_le_dernier": 409,
    "table_refusee": 422, "table_invalide": 422, "politique_invalide": 422, "confirmation_requise": 422,
})
# Refus de la résolution (routage.valider_choix) : 422 sur les routes de la page Routage.
REFUS_DE_ROUTAGE = ("classe_voie", "sans_depot", "effort_interdit", "palier_interdit", "modele_absent",
                    "effort_non_pris_en_charge", "aucun_modele", "voie_indisponible", "voie_non_connectee",
                    "liste_de_secours", "cli_hors_version", "interdit_par_le_poste", "efforts_inconnus")


def _champs(corps: Dict[str, Any], admis: set) -> Optional[JSONResponse]:
    inconnus = sorted(set(corps) - admis)
    if inconnus:
        return _erreur(400, "arguments", "Refusé par ACP : champ inconnu refusé : " + ", ".join(inconnus)[:200] + ".")
    return None


async def _executer_routage(travail: Callable[[Any], Any], *, statut: int = 200) -> JSONResponse:
    """Comme _executer, avec les refus de routage en 422 et la liste des refus d'une table refusée."""
    textes = _n("textes")

    def enveloppe():
        with _n("base").connexion() as conn:
            return travail(conn)
    try:
        resultat = await run_in_threadpool(enveloppe)
    except textes.RefusACP as exc:
        code_http = 422 if exc.code in REFUS_DE_ROUTAGE else CODES_HTTP.get(exc.code, 400)
        contenu: Dict[str, Any] = {"code": exc.code, "message": exc.message}
        if getattr(exc, "refus", None):
            contenu["refus"] = exc.refus
        return JSONResponse(status_code=code_http, content={"detail": contenu})
    except Exception as exc:  # noqa: BLE001 — jamais une trace brute au navigateur
        return _erreur(500, "echec", f"Échec d'ACP ({type(exc).__name__}) : consultez l'état avant de réessayer.")
    return JSONResponse(status_code=statut, content=json.loads(json.dumps(resultat, ensure_ascii=False, default=str)))


def _vue_poste(conn) -> Dict[str, Any]:
    """GET /v1/poste : état (non configuré, à confirmer, en ligne, hors ligne, révoqué), poste courant, dernier
    inventaire (sans les relevés, rangés à part), ses alertes, ordres en attente, catalogue."""
    presence, machines, inventaire, ordres, routage = (_n("presence"), _n("machines"), _n("inventaire"), _n("ordres"),
                                                       _n("routage"))
    courante = machines.machine_courante(conn)
    dernier = inventaire.dernier(conn, courante["id"]) if courante else None
    return {"poste": presence.etat_poste(conn), "machine": machines.etat(conn),
            "inventaire": dernier, "alertes": (dernier or {}).get("alertes") or [],
            "ordres": ordres.en_attente(conn, courante["id"]) if courante and courante["etat"] == "actif" else [],
            "catalogue": routage.catalogue(conn)}


@router.get("/v1/poste")
async def lire_poste() -> JSONResponse:
    return await _executer(_avec_base(_vue_poste))


@router.post("/v1/poste/enrolement")
async def creer_code_enrolement(request: Request) -> JSONResponse:
    """Code à usage unique (10 min) rendu UNE fois ; la base n'en garde que le SHA-256 (décision D48)."""
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, set())
    if refus_champs is not None:
        return refus_champs

    def travail(conn):
        cree = _n("machines").creer_code(conn, auteur)
        # Forme exécutable dans la console du compte du poste, sans lettre de lecteur (décision D68).
        return dict(cree, commande=_contrat_machine().commande_publiee("enroler"))
    reponse = await _executer_routage(travail, statut=201)
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


@router.post("/v1/poste/confirmation")
async def confirmer_poste(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, {"machine_id", "empreinte"})
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: _n("machines").confirmer(conn, corps.get("machine_id"),
                                                                         corps.get("empreinte"), auteur))


@router.post("/v1/poste/revocation")
async def revoquer_poste(request: Request) -> JSONResponse:
    """Révocation : état en base, présence supprimée, attente en cours réveillée (401 poste_revoque au poste)."""
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, {"machine_id", "motif"})
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: revoquer(corps.get("machine_id"), corps.get("motif"), auteur))


@router.post("/v1/poste/releve")
async def relever_maintenant(request: Request) -> JSONResponse:
    """« Relever maintenant » : ordre ``releve`` au poste actif ; 202, et le dit s'il est hors ligne."""
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, set())
    if refus_champs is not None:
        return refus_champs

    def travail(conn):
        machines, presence, textes, base = _n("machines"), _n("presence"), _n("textes"), _n("base")
        actif = machines.machine_active(conn)
        if actif is None:
            raise textes.RefusACP("aucun_poste_actif", textes.PREFIXE_REFUS + textes.AUCUN_POSTE_ACTIF)
        hors_ligne = presence.etat_poste(conn)["etat"] != "en_ligne"
        identifiant = ordonner(actif["id"], "releve", auteur)
        minutes = int(base.reglage(conn, "ordre_expiration_s") or 3600) // 60
        return {"ordre": identifiant, "en_attente_du_poste": hors_ligne,
                "message": textes.ORDRE_RELEVE_HORS_LIGNE.format(n=minutes) if hors_ligne
                else textes.ORDRE_RELEVE_EN_FILE}
    return await _executer_routage(travail, statut=202)


@router.get("/v1/routage")
async def lire_routage() -> JSONResponse:
    return await _executer_routage(lambda conn: _n("routage").vue_routage(conn))


@router.post("/v1/routage")
async def valider_routage(request: Request) -> JSONResponse:
    """Validation de la table, complète ou rien : 409 si un relevé a changé depuis l'ouverture de la page, 422 avec
    la liste des refus par entrée."""
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, {"releves", "classes"})
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: _n("routage").valider_table(
        conn, releves=corps.get("releves"), classes=corps.get("classes"), auteur=auteur))


@router.post("/v1/routage/politique")
async def poser_politique(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, {"efforts_interdits", "paliers_admis", "motif", "confirmation"})
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: _n("routage").poser_politique(
        conn, efforts_interdits=corps.get("efforts_interdits"), paliers_admis=corps.get("paliers_admis"),
        motif=corps.get("motif"), confirmation=corps.get("confirmation"), auteur=auteur))


@router.post("/v1/routage/surcharges")
async def creer_surcharge(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, {"classe", "voie", "modele", "effort", "palier", "motif"})
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: _n("routage").creer_surcharge_globale(
        conn, classe=corps.get("classe"), voie=corps.get("voie"), modele=corps.get("modele"),
        effort=corps.get("effort"), palier=corps.get("palier"), motif=corps.get("motif"), auteur=auteur), statut=201)


@router.post("/v1/routage/surcharges/{identifiant}/desactiver")
async def desactiver_surcharge(identifiant: str, request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, set())
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: _n("routage").desactiver_surcharge(conn, identifiant, auteur))


@router.post("/v1/routage/releve-accepte")
async def accepter_releve(request: Request) -> JSONResponse:
    garde = await _garde_ecriture(request)
    if isinstance(garde, JSONResponse):
        return garde
    auteur, corps = garde
    refus_champs = _champs(corps, {"releve_id"})
    if refus_champs is not None:
        return refus_champs
    return await _executer_routage(lambda conn: _n("routage").accepter_releve(conn, corps.get("releve_id"), auteur))


@router.get("/v1/quotas")
async def lire_quotas() -> JSONResponse:
    return await _executer_routage(lambda conn: _n("quotas").vue(conn))
