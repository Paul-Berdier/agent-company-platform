"""Détection prudente des capacités réellement disponibles sur la machine."""

import os
import shutil

from acp_contracts import WorkerCapability

from .executors import ExecutorConfig, ExecutorConfigurationError
from .local_runner import LocalRunnerConfig, RunnerConfigurationError
from .mcp_probe import McpProbeConfigurationError, McpStdioProbeConfig
from .web_tests import SIMULATION_ENV, WebTestConfig, WebTestConfigurationError


def simulation_from_environ() -> bool:
    """Mode de simulation déduit de l'environnement, fermé par défaut.

    Repli utilisé quand l'appelant ne connaît pas encore le mode effectif.
    ``register --real`` et ``doctor``, eux, le connaissent et le passent.
    """

    return os.environ.get(SIMULATION_ENV, "1").strip() != "0"


def _web_tests_available(*, simulation: bool) -> bool:
    """Les tests web exigent une configuration complète **et** le mode réel.

    Un worker en simulation ne lance aucun programme : annoncer ``web_tests``
    l'exposerait à des missions qu'il ne peut pas exécuter. Le mode est celui
    que l'appelant enregistre réellement, jamais une seconde lecture de
    ``ACP_WORKER_SIMULATION`` : ``register --real`` enregistre
    ``simulation=False`` sans que la variable change, et un worker déclaré réel
    qui n'annonce pas ``web_tests`` reroute silencieusement ses missions
    ``web_test_suite`` vers le programme local du Lot C.
    """

    if simulation:
        return False
    try:
        config = WebTestConfig.from_environ()
    except (WebTestConfigurationError, ValueError, OSError):
        return False
    return config.enabled and config.configured


def _mcp_stdio_probe_available() -> bool:
    """La sonde stdio n'est annoncée qu'avec son drapeau ET son allowlist.

    Une configuration refusée n'est jamais une capacité : annoncer une sonde
    que le worker refusera d'exécuter serait un faux succès.
    """

    try:
        config = McpStdioProbeConfig.from_environ()
    except McpProbeConfigurationError:
        return False
    return config.enabled and bool(config.allowed_executables)


def _agent_executor_capabilities(*, simulation: bool) -> set[str]:
    """N'annonce jamais un CLI trouvé fortuitement dans le ``PATH``.

    Les chemins de programme, les dossiers d'authentification et au moins une
    racine projet doivent former une configuration opt-in valide. Une
    configuration partielle est traitée comme indisponible ici ; le chargement
    de ``WorkerConfig`` remontera, lui, l'erreur précise à l'opérateur.
    """

    if simulation:
        return set()
    try:
        config = ExecutorConfig.from_environ()
    except (ExecutorConfigurationError, OSError, ValueError):
        return set()
    capabilities: set[str] = set()
    if "codex_cli" in config.enabled_executors:
        capabilities.add(WorkerCapability.CODEX_CLI.value)
    if "claude_code" in config.enabled_executors:
        capabilities.add(WorkerCapability.CLAUDE_CODE.value)
    return capabilities


def _local_runner_available() -> bool:
    """Ne publie les capacités génériques qu'avec leur backend réel.

    Les exécuteurs Codex/Claude ont leur propre capacité explicite. Sans cette
    distinction, un worker configuré uniquement pour un agent pouvait réclamer
    une mission ``shell_restricted`` puis échouer après attribution.
    """

    try:
        return LocalRunnerConfig.from_environment() is not None
    except (RunnerConfigurationError, OSError, ValueError):
        return False


def detect_capabilities(
    *,
    simulation: bool | None = None,
    local_runner_configured: bool | None = None,
) -> list[str]:
    """Capacités annonçables dans le mode d'exécution réellement enregistré.

    ``simulation`` vaut le drapeau que l'appelant s'apprête à enregistrer ;
    ``None`` retombe sur l'environnement pour les appels qui n'ont pas de mode
    à leur disposition.
    """

    if simulation is None:
        simulation = simulation_from_environ()
    if local_runner_configured is None:
        local_runner_configured = _local_runner_available()
    if not isinstance(local_runner_configured, bool):
        raise TypeError("local_runner_configured doit être un booléen")

    # Une simulation peut annoncer le socle historique sans lancer de programme.
    # En mode réel, chaque capacité de mission générique exige le runner local.
    local_mission_backend = simulation or local_runner_configured
    capabilities: set[str] = set()
    if local_mission_backend:
        capabilities.update(
            {
                WorkerCapability.FILESYSTEM_PROJECT.value,
                WorkerCapability.SHELL_RESTRICTED.value,
            }
        )
        commands = {
            WorkerCapability.GIT: ("git",),
            WorkerCapability.BLENDER: ("blender",),
        }
        for capability, executables in commands.items():
            if any(shutil.which(executable) for executable in executables):
                capabilities.add(capability.value)
    capabilities.update(_agent_executor_capabilities(simulation=simulation))
    if local_mission_backend and os.environ.get("ACP_BLENDER_MCP_URL"):
        capabilities.add(WorkerCapability.BLENDER_MCP.value)
    if local_mission_backend and (
        os.environ.get("UNREAL_EDITOR") or os.environ.get("UE_EDITOR")
    ):
        capabilities.add(WorkerCapability.UNREAL_ENGINE.value)
    if local_mission_backend and os.environ.get("ACP_UNREAL_MCP_URL"):
        capabilities.add(WorkerCapability.UNREAL_MCP.value)
    if local_mission_backend and os.environ.get("ACP_NANOSWORLD_COOK_COMMAND"):
        capabilities.add(WorkerCapability.NANOSWORLD_COOK.value)
    if local_mission_backend and os.environ.get("ACP_ASSET_VALIDATION_COMMAND"):
        capabilities.add(WorkerCapability.ASSET_VALIDATION.value)
    if local_mission_backend and os.environ.get("ACP_IMAGE_CAPTURE_COMMAND"):
        capabilities.add(WorkerCapability.IMAGE_CAPTURE.value)
    if _mcp_stdio_probe_available():
        capabilities.add(WorkerCapability.MCP_STDIO_PROBE.value)
    if local_mission_backend and _web_tests_available(simulation=simulation):
        capabilities.add(WorkerCapability.WEB_TESTS.value)
    return sorted(capabilities)


def missing_capabilities(required: list[str], available: list[str]) -> list[str]:
    return sorted(set(required) - set(available))
