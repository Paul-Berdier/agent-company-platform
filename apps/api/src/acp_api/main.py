import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_agent_sdk import load_modules
from acp_database import get_engine

from . import db_errors, readiness
from .access_logging import install_access_log_redaction
from .webhook_ingress import RequestIngressGuardMiddleware

from .routers import (
    artifacts,
    alerts,
    auth,
    automations,
    budgets,
    connections,
    conversations,
    crud,
    events,
    mcp,
    meta,
    missions,
    onboarding,
    operations,
    platform,
    scheduler,
    secrets,
    skills,
    streams,
    testing,
    work,
    workers,
)


# Uvicorn inclut par défaut la query string dans son journal d'accès. Installer le
# filtre après sa configuration CLI mais avant la première requête empêche qu'un lien
# signé ``?token=...`` devienne un bearer récupérable dans les logs.
install_access_log_redaction()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage fermé : base initialisée puis sonde de readiness ; tout refus est
    # une RuntimeError française laissée remonter, uvicorn ne sert alors rien.
    readiness.prepare_service_at_startup()
    try:
        app.state.modules = load_modules(os.environ.get("ACP_PLUGINS_DIR"))
        yield
    finally:
        # Uvicorn's graceful shutdown must release SQLite file handles before
        # verification scripts (and Windows service managers) remove the DB.
        get_engine().dispose()


app = FastAPI(
    title="Agent Company Platform API",
    version="0.10.0",
    lifespan=lifespan,
)

db_errors.install(app)
readiness.mount(app, service="api")

app.add_middleware(RequestIngressGuardMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "ACP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(alerts.router)
app.include_router(automations.router)
app.include_router(budgets.router)
app.include_router(connections.router)
app.include_router(conversations.router)
app.include_router(onboarding.router)
app.include_router(crud.router)
app.include_router(missions.router)
app.include_router(work.router)
app.include_router(workers.router)
app.include_router(operations.router)
app.include_router(platform.router)
app.include_router(scheduler.router)
app.include_router(secrets.router)
app.include_router(mcp.router)
app.include_router(skills.router)
app.include_router(skills.extensions_router)
app.include_router(events.router)
app.include_router(streams.router)
app.include_router(artifacts.router)
app.include_router(testing.router)


@app.middleware("http")
async def prevent_private_response_caching(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/auth"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    elif request.cookies.get("acp_session"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/health")
def health():
    """Liveness pure : le processus répond. La readiness est servie par ``/ready``."""

    return {"status": "ok", "service": "api"}
