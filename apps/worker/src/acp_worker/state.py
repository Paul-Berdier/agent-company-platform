"""État local persistant du worker (le jeton n'est jamais journalisé)."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerCredentials:
    worker_id: str
    token: str
    name: str
    capabilities: list[str]
    max_concurrency: int
    simulation: bool
    token_expires_at: str
    heartbeat_interval_seconds: int = 15


def state_file(state_dir: Path) -> Path:
    return state_dir / "worker.json"


def load_credentials(state_dir: Path) -> WorkerCredentials | None:
    path = state_file(state_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return WorkerCredentials(**data)


def save_credentials(state_dir: Path, credentials: WorkerCredentials) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_file(state_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(credentials), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(path)
    return path
