"""Points de reprise locaux atomiques, liés à l'API et à la tentative."""

import json
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any

from .config import WorkerConfig


def checkpoint_path(config: WorkerConfig, attempt_id: str, phase: str) -> Path:
    key = sha256(f"{config.api_url}\0{attempt_id}\0{phase}".encode()).hexdigest()
    return config.state_dir / "attempt-checkpoints" / f"{key}.json"


def read_checkpoint(config: WorkerConfig, attempt_id: str, phase: str) -> dict[str, Any] | None:
    path = checkpoint_path(config, attempt_id, phase)
    if not path.exists():
        return None
    if path.stat().st_size > 2_000_000:
        raise RuntimeError("point de reprise trop volumineux; reprise refusée")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("point de reprise illisible; reprise refusée") from exc
    if not isinstance(data, dict) or data.get("api_url") != config.api_url or data.get("attempt_id") != attempt_id or data.get("phase") != phase:
        raise RuntimeError("point de reprise hors contexte; reprise refusée")
    return data


def write_checkpoint(config: WorkerConfig, attempt_id: str, phase: str, payload: dict[str, Any]) -> None:
    path = checkpoint_path(config, attempt_id, phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({**payload, "api_url": config.api_url, "attempt_id": attempt_id, "phase": phase}, ensure_ascii=False, allow_nan=False)
    if len(body.encode("utf-8")) > 2_000_000:
        raise RuntimeError("point de reprise trop volumineux")
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
