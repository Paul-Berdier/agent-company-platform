"""Diagnostics de connexions exposés sans révéler les secrets serveur."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from acp_contracts import HermesConnectionDiagnostic, HermesNativeListing

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


@router.get("/hermes/native-listing", response_model=HermesNativeListing)
async def read_hermes_native_listing(
    _context: AuthContext = Depends(get_auth_context),
    client: GatewayClient = Depends(get_gateway_client),
):
    """Affiche ce qu'Hermes annonce lui-même, sans jamais l'écrire.

    Hermes reste la source de vérité de ses skills et toolsets : cette route
    est en lecture seule et une passerelle injoignable produit un état
    explicite, jamais une liste vide présentée comme un succès.
    """

    try:
        return await client.hermes_native_listing()
    except GatewayUnavailableError:
        return HermesNativeListing(
            status="unavailable",
            message=(
                "Passerelle indisponible : les skills et toolsets natifs "
                "d'Hermes n'ont pas pu être lus."
            ),
        )
