import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_agent_sdk import load_modules
from acp_database import init_db

from .routers import (
    auth,
    connections,
    conversations,
    crud,
    mcp,
    missions,
    onboarding,
    operations,
    platform,
    secrets,
    skills,
    work,
    workers,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.modules = load_modules(os.environ.get("ACP_PLUGINS_DIR"))
    yield


app = FastAPI(
    title="Agent Company Platform API",
    version="0.4.0",
    lifespan=lifespan,
)

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
app.include_router(connections.router)
app.include_router(conversations.router)
app.include_router(onboarding.router)
app.include_router(crud.router)
app.include_router(missions.router)
app.include_router(work.router)
app.include_router(workers.router)
app.include_router(operations.router)
app.include_router(platform.router)
app.include_router(secrets.router)
app.include_router(mcp.router)
app.include_router(skills.router)
app.include_router(skills.extensions_router)


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
