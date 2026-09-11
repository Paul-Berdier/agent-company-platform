"""Configuration du worker chargée depuis l'environnement."""

import ipaddress
import math
import os
import platform
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .local_runner import LocalRunnerConfig


MIN_POLL_INTERVAL_SECONDS = 0.01
MAX_POLL_INTERVAL_SECONDS = 300.0
MAX_STEP_SECONDS = 3600.0
MAX_CONCURRENCY = 32
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class WorkerConfigurationError(ValueError):
    """Configuration refusée avant toute communication ou exécution."""


def normalize_service_origin(value: str, *, setting: str) -> str:
    """Valide et canonicalise une origine de service sans chemin ni secrets."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise WorkerConfigurationError(f"{setting} doit être une URL absolue sans espaces")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise WorkerConfigurationError(f"{setting} contient une URL invalide") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise WorkerConfigurationError(
            f"{setting} doit utiliser une origine HTTP(S) absolue"
        )
    if parsed.username is not None or parsed.password is not None:
        raise WorkerConfigurationError(f"{setting} ne doit pas contenir de userinfo")
    if "?" in value or "#" in value:
        raise WorkerConfigurationError(
            f"{setting} ne doit pas contenir de query ni de fragment"
        )
    if parsed.path not in {"", "/"}:
        raise WorkerConfigurationError(f"{setting} doit être une origine sans chemin")

    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname:
        raise WorkerConfigurationError(f"{setting} doit contenir un hôte")
    if port == 0:
        raise WorkerConfigurationError(f"{setting} doit utiliser un port valide")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    is_loopback = hostname == "localhost" or bool(address and address.is_loopback)
    if scheme != "https" and not is_loopback:
        raise WorkerConfigurationError(
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
            raise WorkerConfigurationError(f"{setting} contient un hôte invalide") from exc
        if len(canonical_host) > 253 or any(
            _DNS_LABEL.fullmatch(label) is None for label in canonical_host.split(".")
        ):
            raise WorkerConfigurationError(f"{setting} contient un hôte invalide")
    default_port = 80 if scheme == "http" else 443
    authority = (
        canonical_host
        if port in {None, default_port}
        else f"{canonical_host}:{port}"
    )
    return f"{scheme}://{authority}"


def _bounded_float(
    value: object, *, setting: str, minimum: float, maximum: float
) -> float:
    if isinstance(value, bool):
        raise WorkerConfigurationError(f"{setting} doit être un nombre")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise WorkerConfigurationError(f"{setting} doit être un nombre") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise WorkerConfigurationError(
            f"{setting} doit être fini et compris entre {minimum} et {maximum}"
        )
    return parsed


def _bounded_concurrency(value: object) -> int:
    if isinstance(value, bool):
        raise WorkerConfigurationError("ACP_WORKER_MAX_CONCURRENCY doit être un entier")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkerConfigurationError(
            "ACP_WORKER_MAX_CONCURRENCY doit être un entier"
        ) from exc
    if str(value).strip() != str(parsed) or not 1 <= parsed <= MAX_CONCURRENCY:
        raise WorkerConfigurationError(
            f"ACP_WORKER_MAX_CONCURRENCY doit être compris entre 1 et {MAX_CONCURRENCY}"
        )
    return parsed


def _simulation_flag(value: object) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise WorkerConfigurationError("ACP_WORKER_SIMULATION accepte uniquement 0 ou 1")


@dataclass(frozen=True)
class WorkerConfig:
    api_url: str
    gateway_url: str
    gateway_service_token: str | None
    provider_id: str
    poll_interval: float
    step_seconds: float
    state_dir: Path
    name: str
    max_concurrency: int
    simulation: bool
    registration_token: str | None
    local_runner: LocalRunnerConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "api_url",
            normalize_service_origin(self.api_url, setting="ACP_API_URL"),
        )
        object.__setattr__(
            self,
            "gateway_url",
            normalize_service_origin(
                self.gateway_url, setting="ACP_PROVIDER_GATEWAY_URL"
            ),
        )
        object.__setattr__(
            self,
            "poll_interval",
            _bounded_float(
                self.poll_interval,
                setting="ACP_WORKER_POLL_INTERVAL",
                minimum=MIN_POLL_INTERVAL_SECONDS,
                maximum=MAX_POLL_INTERVAL_SECONDS,
            ),
        )
        object.__setattr__(
            self,
            "step_seconds",
            _bounded_float(
                self.step_seconds,
                setting="ACP_WORKER_STEP_SECONDS",
                minimum=0.0,
                maximum=MAX_STEP_SECONDS,
            ),
        )
        object.__setattr__(
            self, "max_concurrency", _bounded_concurrency(self.max_concurrency)
        )
        if not isinstance(self.simulation, bool):
            raise WorkerConfigurationError("simulation doit être un booléen")

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        state_dir = Path(
            os.environ.get("ACP_WORKER_STATE_DIR", Path.home() / ".agent-company-worker")
        ).expanduser()
        return cls(
            api_url=os.environ.get("ACP_API_URL", "http://localhost:8000"),
            gateway_url=os.environ.get(
                "ACP_PROVIDER_GATEWAY_URL", "http://localhost:8002"
            ),
            gateway_service_token=os.environ.get("ACP_GATEWAY_SERVICE_TOKEN"),
            provider_id=os.environ.get("ACP_ORCHESTRATOR_PROVIDER", "mock"),
            poll_interval=os.environ.get("ACP_WORKER_POLL_INTERVAL", "2.0"),
            step_seconds=os.environ.get("ACP_WORKER_STEP_SECONDS", "3.0"),
            state_dir=state_dir,
            name=os.environ.get("ACP_WORKER_NAME", socket.gethostname()),
            max_concurrency=os.environ.get("ACP_WORKER_MAX_CONCURRENCY", "1"),
            simulation=_simulation_flag(os.environ.get("ACP_WORKER_SIMULATION", "1")),
            registration_token=os.environ.get("ACP_WORKER_REGISTRATION_TOKEN"),
            local_runner=LocalRunnerConfig.from_environment(),
        )

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
