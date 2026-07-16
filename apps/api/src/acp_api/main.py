import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_agent_sdk import load_modules
from acp_database import init_db

from .routers import crud, platform, work


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.modules = load_modules(os.environ.get("ACP_PLUGINS_DIR"))
    yield


app = FastAPI(
    title="Agent Company Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ACP_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crud.router)
app.include_router(work.router)
app.include_router(platform.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "api"}
