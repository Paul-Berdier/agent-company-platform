import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_agent_sdk import load_modules
from acp_database import get_engine, init_db

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        app.state.modules = load_modules(os.environ.get("ACP_PLUGINS_DIR"))
        yield
    finally:
        # Uvicorn's graceful shutdown must release SQLite file handles before
        # verification scripts (and Windows service managers) remove the DB.
        get_engine().dispose()


app = FastAPI(
    title="Agent Company Platform API",
    version="0.8.0",
    lifespan=lifespan,
)

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
    return {"status": "ok", "service": "api"}
