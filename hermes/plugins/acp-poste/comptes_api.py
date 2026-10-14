"""Routes propriétaire et canal machine pour l’authentification officielle distante."""
from __future__ import annotations
import json
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse


def creer_router(n, session, origine_publique):
    from acp_poste_contrat import comptes as C
    noyau, base = n("comptes"), n("base")
    router = APIRouter()

    def reponse(statut, obj):
        return JSONResponse(status_code=statut,content=obj,headers={"Cache-Control":"no-store"})

    def erreur(statut, code, message):
        return reponse(statut,{"detail":{"code":code,"message":message}})

    async def corps(request, limite=4096):
        if (request.headers.get("content-type") or "").split(";")[0].strip().lower() != "application/json":
            return erreur(415,"json_attendu","Un corps JSON est requis.")
        brut = bytearray()
        async for bloc in request.stream():
            brut.extend(bloc)
            if len(brut)>limite:
                return erreur(413,"trop_volumineux","Requête de connexion trop volumineuse.")
        try:
            obj=json.loads(brut.decode("utf-8"))
            if not isinstance(obj,dict): raise ValueError()
            return obj
        except (ValueError,UnicodeError,RecursionError):
            return erreur(400,"requete_refusee","Corps JSON invalide.")

    async def owner(request):
        auteur=session(request)
        if auteur is None: return erreur(401,"session","Session du propriétaire requise.")
        origine=request.headers.get("origin")
        if origine is not None and origine.strip().lower().rstrip("/") != (origine_publique() or ""):
            return erreur(403,"origine","Origine de la requête non autorisée.")
        obj=await corps(request)
        return obj if isinstance(obj,JSONResponse) else (auteur,obj)

    async def executer(fn,*args,statut=200):
        def travail():
            with base.connexion() as conn: return fn(conn,*args)
        try:
            return reponse(statut,await run_in_threadpool(travail))
        except n("textes").RefusACP as exc:
            return erreur(404 if exc.code=="connexion_inconnue" else 409,exc.code,exc.message)
        except (ValueError,TypeError,KeyError):
            return erreur(400,"requete_refusee","Champs de connexion invalides ou hors limites.")
        except Exception:
            return erreur(503,"indisponible","Le service des comptes est temporairement indisponible.")

    @router.get("/v1/comptes")
    async def etat(request:Request):
        if session(request) is None: return erreur(401,"session","Session du propriétaire requise.")
        return await executer(noyau.etat)

    @router.post("/v1/comptes/codex/connexions")
    async def demarrer(request:Request):
        garde=await owner(request)
        if isinstance(garde,JSONResponse): return garde
        auteur,obj=garde
        if set(obj)!={"idempotency_key"}: return erreur(400,"requete_refusee","Une clé d’idempotence est requise.")
        return await executer(noyau.creer,obj["idempotency_key"],auteur,statut=202)

    @router.post("/v1/comptes/claude/connexions")
    async def demarrer_claude(request:Request):
        garde=await owner(request)
        if isinstance(garde,JSONResponse): return garde
        auteur,obj=garde
        if set(obj)!={"idempotency_key"}: return erreur(400,"requete_refusee","Une clé d’idempotence est requise.")
        return await executer(noyau.creer,obj["idempotency_key"],auteur,"claude_code",statut=202)

    @router.get("/v1/comptes/connexions/{identifiant}")
    async def lire(request:Request,identifiant:str):
        if session(request) is None: return erreur(401,"session","Session du propriétaire requise.")
        if (set(request.query_params)-{"defi_id","soumission_id"}
                or len(request.query_params.multi_items()) != len(request.query_params)):
            return erreur(400,"requete_refusee","Paramètres de réception invalides.")
        return await executer(noyau.lire,identifiant,request.query_params.get("defi_id"),request.query_params.get("soumission_id"))

    @router.post("/v1/comptes/connexions/{identifiant}/code")
    async def code(request:Request,identifiant:str):
        garde=await owner(request)
        if isinstance(garde,JSONResponse): return garde
        auteur,obj=garde
        if set(obj)!={"defi_id","soumission_id","code"}:
            return erreur(400,"requete_refusee","Une remise de code complète est requise.")
        return await executer(noyau.soumettre_code,identifiant,obj["defi_id"],obj["soumission_id"],obj["code"],auteur,statut=202)

    @router.post("/v1/comptes/connexions/{identifiant}/annuler")
    async def annuler(request:Request,identifiant:str):
        garde=await owner(request)
        if isinstance(garde,JSONResponse): return garde
        auteur,obj=garde
        if obj: return erreur(400,"requete_refusee","Aucun paramètre attendu.")
        return await executer(noyau.annuler,identifiant,auteur)

    @router.post("/machine/v1/comptes")
    async def machine(request:Request):
        principal=getattr(request.state,"token_principal",None)
        if principal is None: return erreur(401,"non_authentifie","Jeton machine requis.")
        if getattr(principal,"provider",None)!="acp-poste-machine" or "machine" not in tuple(getattr(principal,"scopes",()) or ()):
            return erreur(403,"portee_refusee","Jeton d’exécutant requis.")
        identite=getattr(principal,"principal","")
        if not isinstance(identite,str) or not identite.startswith("acp-poste:"):
            return erreur(403,"portee_refusee","Identité d’exécutant invalide.")
        obj=await corps(request,limite=16384)
        if isinstance(obj,JSONResponse): return obj
        try: demande=C.Echange.model_validate(obj)
        except ValueError: return erreur(400,"requete_refusee","Échange des comptes invalide ou hors limites.")
        return await executer(noyau.echanger,identite[len("acp-poste:"):],demande)

    return router
