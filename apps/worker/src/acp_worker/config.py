"""Configuration du worker chargée depuis l'environnement."""

import ipaddress
import math
import os
import platform
import re
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from acp_contracts import WorkerCapability

from .executors import ExecutorConfig, ExecutorConfigurationError
from .local_runner import LocalRunnerConfig
from .mcp_probe import McpStdioProbeConfig
from .subscription_quotas import (
    SubscriptionQuotaConfig,
    SubscriptionQuotaConfigurationError,
)
from .web_tests import WebTestConfig


MIN_POLL_INTERVAL_SECONDS = 0.01
MAX_POLL_INTERVAL_SECONDS = 300.0
MAX_STEP_SECONDS = 3600.0
MAX_CONCURRENCY = 32
_AGENT_EXECUTOR_CAPABILITIES = frozenset({"codex_cli", "claude_code"})
_MCP_PROBE_CAPABILITY = WorkerCapability.MCP_STDIO_PROBE.value
_KNOWN_WORKER_CAPABILITIES = frozenset(
    capability.value for capability in WorkerCapability
)
_LOCAL_RUNNER_CAPABILITIES = (
    _KNOWN_WORKER_CAPABILITIES
    - _AGENT_EXECUTOR_CAPABILITIES
    - {_MCP_PROBE_CAPABILITY, "agent_team"}
)
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_PROVIDER_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?")


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


def _global_access_flag(value: object) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise WorkerConfigurationError(
        "ACP_WORKER_GLOBAL_ACCESS accepte uniquement 0 ou 1"
    )


@dataclass(frozen=True)
class WorkerConfig:
    api_url: str
    gateway_url: str
    gateway_service_token: str | None = field(repr=False)
    provider_id: str
    poll_interval: float
    step_seconds: float
    state_dir: Path
    name: str
    max_concurrency: int
    simulation: bool
    registration_token: str | None = field(repr=False)
    project_id: str | None = None
    global_access: bool = False
    local_runner: LocalRunnerConfig | None = None
    executors: ExecutorConfig = field(default_factory=ExecutorConfig.disabled)
    mcp_probe: McpStdioProbeConfig = field(default_factory=McpStdioProbeConfig.disabled)
    web_tests: WebTestConfig = field(default_factory=WebTestConfig.disabled)
    subscription_quotas: SubscriptionQuotaConfig = field(
        default_factory=SubscriptionQuotaConfig.disabled
    )

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
        if (
            not isinstance(self.provider_id, str)
            or _PROVIDER_ID.fullmatch(self.provider_id) is None
        ):
            raise WorkerConfigurationError(
                "ACP_ORCHESTRATOR_PROVIDER doit être un identifiant ASCII minuscule"
            )
        if not isinstance(self.simulation, bool):
            raise WorkerConfigurationError("simulation doit être un booléen")
        if self.project_id is not None:
            if not isinstance(self.project_id, str):
                raise WorkerConfigurationError(
                    "ACP_WORKER_PROJECT_ID doit être un identifiant de projet"
                )
            project_id = self.project_id.strip()
            if not project_id or len(project_id) > 36:
                raise WorkerConfigurationError(
                    "ACP_WORKER_PROJECT_ID doit contenir entre 1 et 36 caractères"
                )
            object.__setattr__(self, "project_id", project_id)
        if not isinstance(self.global_access, bool):
            raise WorkerConfigurationError(
                "ACP_WORKER_GLOBAL_ACCESS doit être un booléen"
            )
        if self.global_access and self.project_id is not None:
            raise WorkerConfigurationError(
                "un worker global ne peut pas être limité simultanément à un projet"
            )
        if not isinstance(self.executors, ExecutorConfig):
            raise WorkerConfigurationError("executors doit être une ExecutorConfig")
        if not isinstance(self.mcp_probe, McpStdioProbeConfig):
            raise WorkerConfigurationError(
                "mcp_probe doit être une McpStdioProbeConfig"
            )
        if not isinstance(self.web_tests, WebTestConfig):
            raise WorkerConfigurationError("web_tests doit être une WebTestConfig")
        if not isinstance(self.subscription_quotas, SubscriptionQuotaConfig):
            raise WorkerConfigurationError(
                "subscription_quotas doit être une SubscriptionQuotaConfig"
            )

    def validate_execution_mode(self, *, simulation: bool) -> None:
        """Refuse toute exécution dite réelle qui dépend encore d'un simulacre."""

        if not isinstance(simulation, bool):
            raise WorkerConfigurationError("simulation doit être un booléen")
        if simulation:
            return
        if self.local_runner is None and not self.executors.enabled_executors:
            raise WorkerConfigurationError(
                "Aucun exécuteur réel sécurisé n'est configuré; configurez le runner "
                "local ou activez explicitement Codex/Claude avec une racine projet"
            )
        if self.web_tests.enabled and self.local_runner is None:
            raise WorkerConfigurationError(
                "les tests web réels exigent un runner local pour leur racine de sortie"
            )
        if self.provider_id == "mock":
            raise WorkerConfigurationError(
                "ACP_ORCHESTRATOR_PROVIDER=mock est interdit en mode réel"
            )

    def validate_advertised_capabilities(
        self,
        capabilities: list[str],
        *,
        simulation: bool,
        project_id: str | None,
        global_access: bool,
    ) -> None:
        """Refuse une annonce que le backend ou le périmètre ne peut pas servir.

        La vérification s'applique à l'enregistrement comme au redémarrage avec des
        credentials persistés : une configuration devenue incomplète ne doit jamais
        laisser le worker réclamer une mission qu'il échouera seulement après son claim.
        """

        self.validate_execution_mode(simulation=simulation)
        if not isinstance(capabilities, list) or any(
            not isinstance(capability, str) or not capability
            for capability in capabilities
        ):
            raise WorkerConfigurationError("capacités worker invalides")
        advertised = set(capabilities)
        unknown = sorted(advertised - _KNOWN_WORKER_CAPABILITIES)
        if unknown:
            raise WorkerConfigurationError(
                "capacités worker inconnues: " + ", ".join(unknown)
            )
        if not isinstance(global_access, bool):
            raise WorkerConfigurationError("périmètre global worker invalide")
        if project_id is not None and (
            not isinstance(project_id, str) or not project_id.strip()
        ):
            raise WorkerConfigurationError("périmètre projet worker invalide")
        if project_id is None and not global_access:
            raise WorkerConfigurationError(
                "périmètre worker absent; réenregistrement avec un projet ou l'accès global requis"
            )
        if project_id is not None and global_access:
            raise WorkerConfigurationError(
                "un worker ne peut pas cumuler périmètre projet et accès global"
            )

        advertised_local = advertised & _LOCAL_RUNNER_CAPABILITIES
        if not simulation and advertised_local and self.local_runner is None:
            raise WorkerConfigurationError(
                "capacités de mission annoncées sans runner local: "
                + ", ".join(sorted(advertised_local))
            )

        advertised_agents = advertised & _AGENT_EXECUTOR_CAPABILITIES
        if "agent_team" in advertised and (simulation or not advertised_agents or shutil.which("git") is None):
            raise WorkerConfigurationError("agent_team exige un exécuteur réel annoncé et Git disponible")
        available_agents = (
            set() if simulation else set(self.executors.enabled_executors)
        )
        unavailable = sorted(advertised_agents - available_agents)
        if unavailable:
            raise WorkerConfigurationError(
                "capacité agent annoncée sans exécuteur activé: "
                + ", ".join(unavailable)
            )
        if advertised_agents:
            if global_access or project_id is None:
                raise WorkerConfigurationError(
                    "une capacité agent exige un périmètre projet explicite; "
                    "l'accès global est refusé tant que les claims ne filtrent pas "
                    "l'allowlist des racines locales"
                )
            if project_id not in self.executors.project_roots:
                raise WorkerConfigurationError(
                    f"le projet {project_id!r} n'a pas de racine d'exécuteur autorisée"
                )

        if not simulation and _MCP_PROBE_CAPABILITY in advertised:
            if not self.mcp_probe.enabled or not self.mcp_probe.allowed_executables:
                raise WorkerConfigurationError(
                    "capacité mcp_stdio_probe annoncée sans sonde stdio configurée"
                )
            # Les capacités enregistrées servent aussi au claim de missions. Tant que
            # l'API ne sépare pas ces deux canaux, une sonde ajoutée à un worker agent
            # sans runner rendrait celui-ci éligible à une mission non-agent qu'il ne
            # peut pas servir.
            if self.local_runner is None:
                raise WorkerConfigurationError(
                    "mcp_stdio_probe exige aussi un runner local tant que les claims "
                    "de sonde et de mission partagent les capacités du worker"
                )

        if not simulation and self.local_runner is None and not advertised_agents:
            raise WorkerConfigurationError(
                "aucune capacité d'exécuteur agent annoncée et aucun runner local; "
                "le worker ne peut servir aucun claim de mission"
            )

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        state_dir = Path(
            os.environ.get("ACP_WORKER_STATE_DIR", Path.home() / ".agent-company-worker")
        ).expanduser()
        try:
            executors = ExecutorConfig.from_environ()
        except ExecutorConfigurationError as exc:
            raise WorkerConfigurationError(str(exc)) from exc
        try:
            subscription_quotas = SubscriptionQuotaConfig.from_environ(executors=executors)
        except SubscriptionQuotaConfigurationError as exc:
            raise WorkerConfigurationError(str(exc)) from exc
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
            project_id=os.environ.get("ACP_WORKER_PROJECT_ID"),
            global_access=_global_access_flag(
                os.environ.get("ACP_WORKER_GLOBAL_ACCESS", "0")
            ),
            local_runner=LocalRunnerConfig.from_environment(),
            executors=executors,
            mcp_probe=McpStdioProbeConfig.from_environ(),
            web_tests=WebTestConfig.from_environ(),
            subscription_quotas=subscription_quotas,
        )

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
