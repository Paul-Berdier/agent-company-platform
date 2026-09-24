"""Configuration du poste chargée depuis l'environnement.

Refonte « Hermes au centre » : l'API ACP a disparu, et avec elle l'enrôlement, les
claims, la passerelle de fournisseurs et les capacités annoncées. Il reste ce que le
poste exécute localement : les exécuteurs Codex et Claude Code, le runner local sous
Job Object et le relevé des quotas d'abonnement.

``normalize_service_origin`` impose HTTPS hors adresse de bouclage. Elle validera
l'origine de Hermes quand la voie kanban du poste arrivera (P5, docs/refonte/plan.md) ;
d'ici là, aucune origine réseau n'est lue.
"""

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .executors import ExecutorConfig, ExecutorConfigurationError
from .local_runner import LocalRunnerConfig
from .subscription_quotas import (
    SubscriptionQuotaConfig,
    SubscriptionQuotaConfigurationError,
)


STATE_DIR_ENV = "ACP_POSTE_STATE_DIR"
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class PosteConfigurationError(ValueError):
    """Configuration refusée avant toute exécution."""


def default_state_dir() -> Path:
    return Path.home() / ".acp-poste"


def normalize_service_origin(value: str, *, setting: str) -> str:
    """Valide et canonicalise une origine de service sans chemin ni secrets."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise PosteConfigurationError(f"{setting} doit être une URL absolue sans espaces")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PosteConfigurationError(f"{setting} contient une URL invalide") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise PosteConfigurationError(
            f"{setting} doit utiliser une origine HTTP(S) absolue"
        )
    if parsed.username is not None or parsed.password is not None:
        raise PosteConfigurationError(f"{setting} ne doit pas contenir de userinfo")
    if "?" in value or "#" in value:
        raise PosteConfigurationError(
            f"{setting} ne doit pas contenir de query ni de fragment"
        )
    if parsed.path not in {"", "/"}:
        raise PosteConfigurationError(f"{setting} doit être une origine sans chemin")

    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname:
        raise PosteConfigurationError(f"{setting} doit contenir un hôte")
    if port == 0:
        raise PosteConfigurationError(f"{setting} doit utiliser un port valide")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    is_loopback = hostname == "localhost" or bool(address and address.is_loopback)
    if scheme != "https" and not is_loopback:
        raise PosteConfigurationError(
            f"{setting} doit utiliser HTTPS hors d'une adresse loopback"
        )

    if address and address.version == 6:
        canonical_host = f"[{address.compressed}]"
    elif address:
        canonical_host = address.compressed
    else:
        try:
            canonical_host = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise PosteConfigurationError(f"{setting} contient un hôte invalide") from exc
        if len(canonical_host) > 253 or any(
            _DNS_LABEL.fullmatch(label) is None for label in canonical_host.split(".")
        ):
            raise PosteConfigurationError(f"{setting} contient un hôte invalide")
    default_port = 80 if scheme == "http" else 443
    authority = (
        canonical_host
        if port in {None, default_port}
        else f"{canonical_host}:{port}"
    )
    return f"{scheme}://{authority}"


@dataclass(frozen=True)
class PosteConfig:
    """Réglages locaux du poste, fermés par défaut."""

    state_dir: Path
    local_runner: LocalRunnerConfig | None = None
    executors: ExecutorConfig = field(default_factory=ExecutorConfig.disabled)
    subscription_quotas: SubscriptionQuotaConfig = field(
        default_factory=SubscriptionQuotaConfig.disabled
    )

    def __post_init__(self) -> None:
        if not isinstance(self.state_dir, Path):
            raise PosteConfigurationError(f"{STATE_DIR_ENV} doit être un chemin")
        if self.local_runner is not None and not isinstance(
            self.local_runner, LocalRunnerConfig
        ):
            raise PosteConfigurationError("local_runner doit être une LocalRunnerConfig")
        if not isinstance(self.executors, ExecutorConfig):
            raise PosteConfigurationError("executors doit être une ExecutorConfig")
        if not isinstance(self.subscription_quotas, SubscriptionQuotaConfig):
            raise PosteConfigurationError(
                "subscription_quotas doit être une SubscriptionQuotaConfig"
            )

    @classmethod
    def from_env(cls) -> "PosteConfig":
        raw_state_dir = os.environ.get(STATE_DIR_ENV)
        state_dir = (
            Path(raw_state_dir).expanduser() if raw_state_dir else default_state_dir()
        )
        try:
            executors = ExecutorConfig.from_environ()
        except ExecutorConfigurationError as exc:
            raise PosteConfigurationError(str(exc)) from exc
        try:
            subscription_quotas = SubscriptionQuotaConfig.from_environ(executors=executors)
        except SubscriptionQuotaConfigurationError as exc:
            raise PosteConfigurationError(str(exc)) from exc
        return cls(
            state_dir=state_dir,
            local_runner=LocalRunnerConfig.from_environment(),
            executors=executors,
            subscription_quotas=subscription_quotas,
        )

    def diagnostic(self) -> dict[str, object]:
        """État local, sans chemin, secret ni valeur d'environnement."""

        report: dict[str, object] = {
            "local_runner": "configured" if self.local_runner is not None else "missing",
            "agent_executors": sorted(self.executors.enabled_executors),
            "executor_project_roots": len(self.executors.project_roots),
        }
        report.update(self.subscription_quotas.doctor_report())
        return report
