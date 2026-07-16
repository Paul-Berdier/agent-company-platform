import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from acp_contracts import (
    ContextSummaryRequest,
    EvaluationRequest,
    PlanningRequest,
    PlanRevisionRequest,
)
from acp_provider_sdk import ProviderRegistry, ProviderUnavailableError

from .providers.hermes import HermesOrchestratorProvider
from .providers.manual import ManualOrchestratorProvider
from .providers.mock import MockOrchestratorProvider

app = FastAPI(title="Agent Company Platform — Provider Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ACP_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = ProviderRegistry()
manual_provider = ManualOrchestratorProvider()
registry.register(MockOrchestratorProvider())
registry.register(manual_provider)
registry.register(HermesOrchestratorProvider())  # indisponible tant que non configuré


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
