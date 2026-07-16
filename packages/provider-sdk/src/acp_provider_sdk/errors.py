class ProviderError(Exception):
    """Erreur générique côté provider (le cœur reste fonctionnel)."""


class ProviderUnavailableError(ProviderError):
    """Provider injoignable ou non configuré — la plateforme continue sans lui."""
