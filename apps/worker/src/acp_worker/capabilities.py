"""Détection prudente des capacités réellement disponibles sur la machine."""

import os
import shutil

from acp_contracts import WorkerCapability

from .mcp_probe import McpProbeConfigurationError, McpStdioProbeConfig
from .web_tests import SIMULATION_ENV, WebTestConfig, WebTestConfigurationError


def _web_tests_available() -> bool:
    """Les tests web exigent une configuration complète **et** le mode réel.

    Un worker en simulation ne lance aucun programme : annoncer ``web_tests``
    l'exposerait à des missions qu'il ne peut pas exécuter. Le drapeau lu est
    ``ACP_WORKER_SIMULATION``, fermé par défaut comme dans ``WorkerConfig``.
    """

    if os.environ.get(SIMULATION_ENV, "1").strip() != "0":
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


def detect_capabilities() -> list[str]:
    capabilities = {
        WorkerCapability.FILESYSTEM_PROJECT.value,
        WorkerCapability.SHELL_RESTRICTED.value,
    }
    commands = {
        WorkerCapability.GIT: ("git",),
        WorkerCapability.CLAUDE_CODE: ("claude",),
        WorkerCapability.CODEX_CLI: ("codex",),
        WorkerCapability.BLENDER: ("blender",),
    }
    for capability, executables in commands.items():
        if any(shutil.which(executable) for executable in executables):
            capabilities.add(capability.value)
    if os.environ.get("ACP_BLENDER_MCP_URL"):
        capabilities.add(WorkerCapability.BLENDER_MCP.value)
    if os.environ.get("UNREAL_EDITOR") or os.environ.get("UE_EDITOR"):
        capabilities.add(WorkerCapability.UNREAL_ENGINE.value)
    if os.environ.get("ACP_UNREAL_MCP_URL"):
        capabilities.add(WorkerCapability.UNREAL_MCP.value)
    if os.environ.get("ACP_NANOSWORLD_COOK_COMMAND"):
        capabilities.add(WorkerCapability.NANOSWORLD_COOK.value)
    if os.environ.get("ACP_ASSET_VALIDATION_COMMAND"):
        capabilities.add(WorkerCapability.ASSET_VALIDATION.value)
    if os.environ.get("ACP_IMAGE_CAPTURE_COMMAND"):
        capabilities.add(WorkerCapability.IMAGE_CAPTURE.value)
    if _mcp_stdio_probe_available():
        capabilities.add(WorkerCapability.MCP_STDIO_PROBE.value)
    if _web_tests_available():
        capabilities.add(WorkerCapability.WEB_TESTS.value)
    return sorted(capabilities)


def missing_capabilities(required: list[str], available: list[str]) -> list[str]:
    return sorted(set(required) - set(available))
