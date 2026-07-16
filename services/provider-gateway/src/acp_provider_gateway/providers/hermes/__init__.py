"""Intégration Hermes — service externe optionnel.

Tout ce qui concerne Hermes vit dans ce dossier : client HTTP, contrat de
communication versionné et adaptateur vers `OrchestratorProvider`. Le reste
de la plateforme n'importe jamais rien d'interne à Hermes.
"""

from .adapter import HermesOrchestratorProvider  # noqa: F401
from .client import HermesClient, HermesSettings  # noqa: F401
from .contracts import HERMES_CONTRACT_VERSION  # noqa: F401
