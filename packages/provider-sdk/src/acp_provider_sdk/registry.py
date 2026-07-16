from .errors import ProviderUnavailableError
from .orchestrator import OrchestratorProvider


class ProviderRegistry:
    """Registre des providers actifs d'un gateway."""

    def __init__(self) -> None:
        self._orchestrators: dict[str, OrchestratorProvider] = {}

    def register(self, provider: OrchestratorProvider) -> None:
        self._orchestrators[provider.descriptor.id] = provider

    def get(self, provider_id: str) -> OrchestratorProvider:
        try:
            return self._orchestrators[provider_id]
        except KeyError:
            raise ProviderUnavailableError(
                f"Orchestrator provider inconnu ou non configuré: {provider_id}"
            ) from None

    def all(self) -> list[OrchestratorProvider]:
        return list(self._orchestrators.values())
