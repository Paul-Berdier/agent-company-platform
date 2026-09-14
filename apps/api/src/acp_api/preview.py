"""Application ASGI minimale dédiée aux aperçus de livrables privés.

Elle partage la base et le stockage de l'API, mais ne monte aucune route métier,
aucune session et aucune documentation interactive. Elle doit être publiée sur
``ACP_ARTIFACT_PUBLIC_ORIGIN`` avec une identité de service distincte.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acp_contracts import ServiceOriginError, normalize_service_origin
from acp_database import get_engine, init_db

from .access_logging import install_access_log_redaction
from .routers.artifacts import preview_router


PREVIEW_CORS_ORIGINS_ENV = "ACP_CORS_ORIGINS"


def configured_preview_cors_origins(
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Valide une allowlist exacte ; wildcard, entrée vide et URL riche sont refusées."""

    source = os.environ if environ is None else environ
    raw = source.get(PREVIEW_CORS_ORIGINS_ENV, "")
    if not raw.strip():
        return []
    entries = raw.split(",")
    if any(not entry.strip() for entry in entries):
        raise ValueError(f"{PREVIEW_CORS_ORIGINS_ENV} contient une origine vide")

    origins: list[str] = []
    for index, entry in enumerate(entries):
        candidate = entry.strip()
        if candidate == "*":
            raise ValueError("l'origine CORS générique est interdite")
        try:
            origin = normalize_service_origin(
                candidate, setting=f"{PREVIEW_CORS_ORIGINS_ENV}[{index}]"
            )
        except ServiceOriginError as exc:
            raise ValueError(
                f"{PREVIEW_CORS_ORIGINS_ENV} contient une origine invalide"
            ) from exc
        if origin not in origins:
            origins.append(origin)
    return origins


@asynccontextmanager
async def preview_lifespan(app: FastAPI):
    del app
    init_db()
    try:
        yield
    finally:
        get_engine().dispose()


def create_preview_app(
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    """Construit le service isolé ; utile aussi pour auditer son inventaire de routes."""

    install_access_log_redaction()
    preview = FastAPI(
        title="Agent Company Platform Artifact Preview",
        version="0.8.0",
        lifespan=preview_lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    preview.add_middleware(
        CORSMiddleware,
        allow_origins=configured_preview_cors_origins(environ),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Range"],
        expose_headers=[
            "Accept-Ranges",
            "Content-Disposition",
            "Content-Length",
            "Content-Range",
            "Content-Type",
        ],
    )
    preview.include_router(preview_router)

    @preview.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "artifact-preview"}

    return preview


app = create_preview_app()
