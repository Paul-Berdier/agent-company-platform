"""Diagnostics de connexions exposés sans révéler les secrets serveur."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from acp_contracts import HermesConnectionDiagnostic

from ..deps import get_auth_context, require_csrf
from ..gateway import GatewayClient, GatewayUnavailableError, get_gateway_client
from ..security import AuthContext

router = APIRouter(prefix="/connections", tags=["connections"])


async def _diagnose(client: GatewayClient) -> HermesConnectionDiagnostic:
    try:
        diagnostic = await client.diagnose_hermes()
        if diagnostic.ready:
            status = "connected"
        elif diagnostic.status in {
            "unauthorized",
            "incompatible_version",
            "invalid_response",
        }:
            status = "degraded"
        else:
            status = "unavailable"
        capabilities = ["runs"] if diagnostic.ready else []
        if diagnostic.ready and diagnostic.model:
            capabilities.append(f"model:{diagnostic.model}")
        return HermesConnectionDiagnostic(
            status=status,
            healthy=diagnostic.ready,
            message=diagnostic.detail,
            capabilities=capabilities,
            checked_at=datetime.now(timezone.utc),
        )
    except GatewayUnavailableError:
        return HermesConnectionDiagnostic(
            status="unavailable",
            healthy=False,
            message=(
                "La passerelle Hermes est indisponible ou son jeton de service "
                "n'est pas configuré."
            ),
            capabilities=[],
            checked_at=datetime.now(timezone.utc),
        )


@router.get("/hermes/diagnostic", response_model=HermesConnectionDiagnostic)
async def read_hermes_diagnostic(
    _context: AuthContext = Depends(get_auth_context),
    client: GatewayClient = Depends(get_gateway_client),
):
    return await _diagnose(client)


@router.post("/hermes/diagnostic", response_model=HermesConnectionDiagnostic)
async def run_hermes_diagnostic(
    _context: AuthContext = Depends(require_csrf),
    client: GatewayClient = Depends(get_gateway_client),
):
    return await _diagnose(client)
