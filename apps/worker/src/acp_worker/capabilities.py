"""Détection prudente des capacités réellement disponibles sur la machine."""

import os
import shutil

from acp_contracts import WorkerCapability


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
    return sorted(capabilities)


def missing_capabilities(required: list[str], available: list[str]) -> list[str]:
    return sorted(set(required) - set(available))
