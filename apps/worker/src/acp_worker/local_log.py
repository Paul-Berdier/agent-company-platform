"""Journal JSONL local, volontairement sans secrets."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkerLogger:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "worker.log.jsonl"

    def write(self, level: str, message: str, **context: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            **context,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{level}] {message}")


def tail_logs(state_dir: Path, count: int) -> list[str]:
    path = state_dir / "worker.log.jsonl"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()[-count:]
