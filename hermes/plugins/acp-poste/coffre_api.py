"""Routes du coffre propriétaire et de son bridge, sans accès serveur aux notes."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse


def creer_router(n, session, origine_publique):
    noyau, base = n("coffres"), n("base")
    from acp_poste_contrat import coffre as C
    from pydantic import ValidationError
    router = APIRouter()

    def reponse(statut, obj):
        return JSONResponse(status_code=statut, content=obj, headers={"Cache-Control": "no-store"})

    def erreur(statut, code, message):
        return reponse(statut, {"detail": {"code": code, "message": message}})

    async def corps(request, maximum=C.TAILLE_MAX_CORPS):
        if (request.headers.get("content-type") or "").split(";")[0].strip().lower() != "application/json":
            return erreur(415, "json_attendu", "Un corps JSON est requis.")
        taille = request.headers.get("content-length")
        if taille is not None and (not taille.isdigit() or int(taille) > maximum):
            return erreur(413, "trop_volumineux", "Corps du coffre trop volumineux.")
        brut = bytearray()
        async for bloc in request.stream():
            brut.extend(bloc)
            if len(brut) > maximum:
                return erreur(413, "trop_volumineux", "Corps du coffre trop volumineux.")
        try:
            obj = json.loads(brut.decode("utf-8"))
            if not isinstance(obj, dict):
                raise ValueError()
            C.borner_json(obj)
            return obj
        except (UnicodeError, ValueError, RecursionError):
            return erreur(400, "requete_refusee", "Corps JSON du coffre invalide ou hors limites.")

    async def owner(request, maximum=64 * 1024):
        auteur = session(request)
        if auteur is None:
            return erreur(401, "session", "Session du propriétaire requise.")
        origine = request.headers.get("origin")
        if origine is not None and origine.strip().lower().rstrip("/") != (origine_publique() or ""):
            return erreur(403, "origine", "Origine de la requête non autorisée.")
        obj = await corps(request, maximum)
        return obj if isinstance(obj, JSONResponse) else (auteur, obj)

    async def bridge(request, portee):
        p = getattr(request.state, "token_principal", None)
        if p is None:
            return erreur(401, "non_authentifie", "Jeton du bridge requis.")
        if getattr(p, "provider", None) != "acp-coffre" or portee not in tuple(getattr(p, "scopes", ()) or ()):
            return erreur(403, "portee_refusee", "Ce jeton ne donne pas accès à cette route du coffre.")
        identifiant = getattr(p, "principal", "")
        if not isinstance(identifiant, str) or not identifiant.startswith("coffre:"):
            return erreur(403, "portee_refusee", "Identité du coffre invalide.")
        cle = identifiant[len("coffre:"):]
        generation = None
        if portee == "coffre":
            morceaux = cle.split(":")
            try:
                if len(morceaux) != 2 or len(morceaux[1]) != 64 or any(x not in "0123456789abcdef" for x in morceaux[1]):
                    raise ValueError()
                cle, generation = C.identifiant(morceaux[0]), morceaux[1]
            except ValueError:
                return erreur(403, "portee_refusee", "Génération de l’identité du coffre invalide.")
        obj = await corps(request)
        return obj if isinstance(obj, JSONResponse) else (cle, generation, obj)

    async def executer(fn, *args, statut=200):
        def travail():
            with base.connexion() as conn:
                return fn(conn, *args)
        try:
            resultat = await run_in_threadpool(travail)
            return reponse(statut, resultat)
        except n("textes").RefusACP as exc:
            status = {"coffre_revoque": 401, "code_refuse": 401, "coffre_interdit": 403,
                      "operation_inconnue": 404, "secret": 400}.get(exc.code, 409)
            return erreur(status, exc.code, exc.message)
        except (ValueError, ValidationError, TypeError, KeyError):
            return erreur(400, "requete_refusee", "Les champs du coffre sont invalides ou hors limites.")
        except Exception:
            return erreur(503, "indisponible", "Le service du coffre est temporairement indisponible.")

    def valider(modele, obj):
        try:
            return modele.model_validate(obj)
        except (ValueError, TypeError):
            return erreur(400, "requete_refusee", "Les champs du coffre sont invalides ou hors limites.")

    @router.get("/v1/coffre")
    async def etat(request: Request):
        if session(request) is None:
            return erreur(401, "session", "Session du propriétaire requise.")
        return await executer(noyau.etat)

    @router.post("/v1/coffre/enrolement")
    async def code(request: Request):
        garde = await owner(request)
        if isinstance(garde, JSONResponse):
            return garde
        auteur, obj = garde
        if obj:
            return erreur(400, "requete_refusee", "Aucun paramètre n’est attendu.")
        return await executer(noyau.creer_code, auteur, statut=201)

    @router.post("/v1/coffre/confirmer")
    async def confirmer(request: Request):
        garde = await owner(request)
        if isinstance(garde, JSONResponse):
            return garde
        auteur, obj = garde
        if set(obj) != {"coffre_id", "empreinte"}:
            return erreur(400, "requete_refusee", "Identifiant et empreinte du coffre requis.")
        try:
            identifiant = C.identifiant(obj["coffre_id"])
        except ValueError:
            return erreur(400, "requete_refusee", "Identifiant du coffre invalide.")
        return await executer(noyau.confirmer, identifiant, obj["empreinte"], auteur)

    @router.post("/v1/coffre/revoquer")
    async def revoquer(request: Request):
        garde = await owner(request)
        if isinstance(garde, JSONResponse):
            return garde
        auteur, obj = garde
        if set(obj) != {"coffre_id", "motif"}:
            return erreur(400, "requete_refusee", "Identifiant et motif du coffre requis.")
        try:
            identifiant = C.identifiant(obj["coffre_id"])
        except ValueError:
            return erreur(400, "requete_refusee", "Identifiant du coffre invalide.")
        return await executer(noyau.revoquer, identifiant, obj["motif"], auteur)

    @router.post("/v1/coffre/operations")
    async def creer(request: Request):
        garde = await owner(request, C.TAILLE_MAX_CORPS)
        if isinstance(garde, JSONResponse):
            return garde
        auteur, obj = garde
        demande = valider(C.DemandeOperation, obj)
        if isinstance(demande, JSONResponse):
            return demande
        return await executer(noyau.creer_operation, demande, auteur, statut=202)

    @router.get("/v1/coffre/operations/{identifiant}")
    async def operation(request: Request, identifiant: str):
        if session(request) is None:
            return erreur(401, "session", "Session du propriétaire requise.")
        return await executer(noyau.operation, identifiant)

    @router.post("/coffre/v1/enrolement")
    async def enroler(request: Request):
        garde = await bridge(request, "coffre_enrolement")
        if isinstance(garde, JSONResponse):
            return garde
        cle, generation, obj = garde
        demande = valider(C.Enrolement, obj)
        return demande if isinstance(demande, JSONResponse) else await executer(noyau.enroler, cle, demande, statut=201)

    @router.post("/coffre/v1/reclamer")
    async def reclamer(request: Request):
        garde = await bridge(request, "coffre")
        if isinstance(garde, JSONResponse):
            return garde
        cle, generation, obj = garde
        demande = valider(C.RequeteReclamer, obj)
        if isinstance(demande, JSONResponse):
            return demande
        limite = time.monotonic() + demande.attente_max_s
        while True:
            rendu = await executer(noyau.reclamer, cle, demande, generation)
            if rendu.status_code != 200:
                return rendu
            resultat = json.loads(rendu.body)
            if resultat["operation"] is not None or resultat["etat"] != "actif" or time.monotonic() >= limite:
                return rendu
            if await request.is_disconnected():
                return rendu
            await asyncio.sleep(min(1, max(0, limite - time.monotonic())))

    @router.post("/coffre/v1/resultat")
    async def resultat(request: Request):
        garde = await bridge(request, "coffre")
        if isinstance(garde, JSONResponse):
            return garde
        cle, generation, obj = garde
        demande = valider(C.Resultat, obj)
        return demande if isinstance(demande, JSONResponse) else await executer(noyau.resultat, cle, demande, generation)

    return router
