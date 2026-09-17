import os
import secrets
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from acp_contracts import (
    ContextSummaryRequest,
    EvaluationRequest,
    HermesNativeListing,
    PlanningRequest,
    PlanRevisionRequest,
)
from acp_provider_sdk import ProviderRegistry, ProviderUnavailableError

from .providers.comfyui import (
    ComfyUIBusyError,
    ComfyUIConfigurationError,
    ComfyUIConnector,
    ComfyUIDiagnostic,
    ComfyUIDisabledError,
    ComfyUIIdempotencyConflict,
    ComfyUIImageRequest,
    ComfyUIInvalidResponseError,
    ComfyUITimeoutError,
    ComfyUIUpstreamError,
)
from .providers.hermes import (
    HermesConversationRunRequest,
    HermesDiagnostic,
    HermesOrchestratorProvider,
    HermesRunView,
)
from .providers.manual import ManualOrchestratorProvider
from .providers.mock import MockOrchestratorProvider

app = FastAPI(title="Agent Company Platform — Provider Gateway", version="0.9.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "ACP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = ProviderRegistry()
manual_provider = ManualOrchestratorProvider()
hermes_provider = HermesOrchestratorProvider()
comfyui_connector = ComfyUIConnector()
registry.register(MockOrchestratorProvider())
registry.register(manual_provider)
registry.register(hermes_provider)  # indisponible tant que non configuré


@app.middleware("http")
async def require_internal_bearer(request: Request, call_next):
    """Ne laisse publique que la liveness, y compris si le secret est absent."""

    if request.url.path == "/health":
        return await call_next(request)

    expected = os.environ.get("ACP_GATEWAY_SERVICE_TOKEN", "").strip()
    if not expected:
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentification interne du gateway non configurée"},
        )

    authorization = request.headers.get("Authorization", "")
    scheme, separator, credential = authorization.partition(" ")
    authenticated = (
        separator == " "
        and scheme.lower() == "bearer"
        and bool(credential)
        and secrets.compare_digest(credential, expected)
    )
    if not authenticated:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentification Bearer requise"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


def _get(provider_id: str):
    try:
        return registry.get(provider_id)
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok", "service": "provider-gateway"}


@app.get("/v1/providers")
def list_providers():
    return [p.descriptor.model_dump(mode="json") for p in registry.all()]


@app.get("/v1/providers/{provider_id}/health")
async def provider_health(provider_id: str):
    return (await _get(provider_id).health_check()).model_dump(mode="json")


@app.get(
    "/v1/providers/hermes/diagnostic",
    response_model=HermesDiagnostic,
    response_model_exclude_none=True,
)
async def hermes_diagnostic():
    return await hermes_provider.diagnostic()


@app.get(
    "/v1/providers/comfyui/diagnostic",
    response_model=ComfyUIDiagnostic,
)
async def comfyui_diagnostic():
    """Vérifie la configuration opérateur et la disponibilité de ComfyUI."""

    return await comfyui_connector.diagnostic()


@app.get(
    "/v1/providers/hermes/native-listing",
    response_model=HermesNativeListing,
)
async def hermes_native_listing():
    """Lecture seule des skills et toolsets annoncés par Hermes.

    Aucune écriture n'est faite côté Hermes et aucune indisponibilité ne
    devient un 500 : l'état est explicite dans le corps de la réponse.
    """

    return await hermes_provider.native_listing()


def _idempotency_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= 255:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key doit contenir de 1 à 255 caractères ASCII visibles",
        )
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key doit contenir de 1 à 255 caractères ASCII visibles",
        )
    return value


@app.post("/v1/providers/comfyui/images")
async def generate_comfyui_image(
    request: ComfyUIImageRequest,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
):
    """Génère une image depuis le seul workflow local approuvé par l'opérateur.

    Ce contrat reste volontairement indépendant du worker tant que son contrat
    d'exécution image n'est pas stabilisé.
    """

    try:
        image = await comfyui_connector.generate(
            request,
            idempotency_key=_idempotency_key(idempotency_key),
        )
    except ComfyUIIdempotencyConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key déjà utilisée pour une autre génération",
        ) from exc
    except ComfyUIBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail="Trop de générations ComfyUI simultanées",
            headers={"Retry-After": "1"},
        ) from exc
    except (ComfyUIDisabledError, ComfyUIConfigurationError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Connecteur ComfyUI non configuré",
        ) from exc
    except ComfyUITimeoutError as exc:
        raise HTTPException(status_code=504, detail="Délai ComfyUI dépassé") from exc
    except (ComfyUIInvalidResponseError, ComfyUIUpstreamError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Réponse ComfyUI indisponible ou invalide",
        ) from exc

    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{image.filename}"',
            "Idempotency-Replayed": "true" if image.replayed else "false",
            "X-ACP-Idempotency-Scope": "bounded-process-memory",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post(
    "/v1/providers/hermes/runs",
    response_model=HermesRunView,
    response_model_exclude_none=True,
    status_code=202,
)
async def submit_hermes_run(
    request: HermesConversationRunRequest,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
):
    try:
        return await hermes_provider.submit_conversation_run(
            request,
            idempotency_key=_idempotency_key(idempotency_key),
        )
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/v1/providers/hermes/runs/{run_id}",
    response_model=HermesRunView,
    response_model_exclude_none=True,
)
async def read_hermes_run(
    run_id: Annotated[str, Path(pattern=r"^run_[0-9a-f]{32}$")],
):
    try:
        return await hermes_provider.read_conversation_run(run_id)
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/providers/{provider_id}/plan")
async def plan(provider_id: str, request: PlanningRequest):
    try:
        return (await _get(provider_id).create_plan(request)).model_dump(mode="json")
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/providers/{provider_id}/revise")
async def revise(provider_id: str, request: PlanRevisionRequest):
    try:
        return (await _get(provider_id).revise_plan(request)).model_dump(mode="json")
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/providers/{provider_id}/evaluate")
async def evaluate(provider_id: str, request: EvaluationRequest):
    try:
        return (await _get(provider_id).evaluate_result(request)).model_dump(mode="json")
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/providers/{provider_id}/summarize")
async def summarize(provider_id: str, request: ContextSummaryRequest):
    try:
        return (await _get(provider_id).summarize_context(request)).model_dump(mode="json")
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class ManualResolution(BaseModel):
    resolution: dict


@app.get("/v1/manual/pending")
def manual_pending():
    return list(manual_provider.pending.values())


@app.post("/v1/manual/pending/{request_id}/resolve")
def manual_resolve(request_id: str, body: ManualResolution):
    if not manual_provider.resolve(request_id, body.resolution):
        raise HTTPException(status_code=404, detail="Demande inconnue ou déjà résolue")
    return {"ok": True}
