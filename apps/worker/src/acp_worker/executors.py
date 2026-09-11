"""Adaptateurs historiques de processus locaux pour Codex CLI et Claude Code.

Ce module construit et exécute uniquement des listes d'arguments (jamais de
shell). Ils ne sont pas le backend réel du worker, qui vit dans
``local_runner.py``. Un appel direct échoue fermé tant qu'un chemin d'exécutable
absolu et vérifié n'est pas fourni explicitement.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_runner import _BoundedCapture, _process_group_options, _terminate_process


MAX_OUTPUT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ExecutorResult:
    executor: str
    exit_code: int
    events: list[dict[str, Any]]
    stderr: str


def resolve_project_path(project_root: Path, requested_path: str) -> Path:
    root = project_root.expanduser().resolve(strict=True)
    candidate = (root / requested_path).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("le projet demandé sort de ACP_WORKER_PROJECT_ROOT") from exc
    if not candidate.is_dir():
        raise ValueError("le chemin projet doit désigner un dossier")
    return candidate


def codex_command(project_path: Path, prompt: str) -> list[str]:
    return [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
        "--cd",
        str(project_path),
        prompt,
    ]


def claude_command(project_path: Path, prompt: str, *, max_turns: int = 12) -> list[str]:
    if not 1 <= max_turns <= 50:
        raise ValueError("max_turns doit être compris entre 1 et 50")
    return [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        "plan",
        "--add-dir",
        str(project_path),
    ]


def restricted_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "COMSPEC",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _parse_json_lines(raw: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            item = {"type": "text", "text": line}
        if isinstance(item, dict):
            events.append(item)
    return events


async def run_executor(
    executor: str,
    project_root: Path,
    requested_path: str,
    prompt: str,
    *,
    timeout_seconds: int = 1800,
    executable_path: Path | None = None,
) -> ExecutorResult:
    project_path = resolve_project_path(project_root, requested_path)
    if executable_path is None:
        raise RuntimeError("chemin absolu de l'exécutable requis")
    executable = executable_path.expanduser()
    if not executable.is_absolute():
        raise ValueError("le chemin de l'exécutable doit être absolu")
    executable = executable.resolve(strict=True)
    if not executable.is_file():
        raise ValueError("l'exécutable doit être un fichier")
    try:
        executable.relative_to(project_path)
    except ValueError:
        pass
    else:
        raise ValueError("l'exécutable ne peut pas provenir du projet non fiable")
    if executor == "codex_cli":
        command = codex_command(project_path, prompt)
    elif executor == "claude_code":
        command = claude_command(project_path, prompt)
    else:
        raise ValueError(f"exécuteur non autorisé: {executor}")
    command[0] = str(executable)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=project_path,
        env=restricted_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_process_group_options(),
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_task = asyncio.create_task(_BoundedCapture(MAX_OUTPUT_BYTES).read(process.stdout))
    stderr_task = asyncio.create_task(_BoundedCapture(MAX_OUTPUT_BYTES).read(process.stderr))
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except TimeoutError:
        await _terminate_process(process, 1.0)
        await asyncio.gather(stdout_task, stderr_task)
        raise TimeoutError(f"{executor} a dépassé {timeout_seconds} secondes") from None
    except asyncio.CancelledError:
        await _terminate_process(process, 1.0)
        await asyncio.gather(stdout_task, stderr_task)
        raise
    stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    if stdout.truncated or stderr.truncated:
        raise RuntimeError("sortie de l'exécuteur supérieure à la limite de 2 Mio")
    return ExecutorResult(
        executor=executor,
        exit_code=process.returncode,
        events=_parse_json_lines(stdout.text.encode("utf-8")),
        stderr=stderr.text,
    )
