"""Configuration du worker chargée depuis l'environnement."""

import os
import platform
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerConfig:
    api_url: str
    gateway_url: str
    provider_id: str
    poll_interval: float
    step_seconds: float
    state_dir: Path
    name: str
    max_concurrency: int
    simulation: bool
    registration_token: str | None

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        state_dir = Path(
            os.environ.get("ACP_WORKER_STATE_DIR", Path.home() / ".agent-company-worker")
        ).expanduser()
        return cls(
            api_url=os.environ.get("ACP_API_URL", "http://localhost:8000").rstrip("/"),
            gateway_url=os.environ.get(
                "ACP_PROVIDER_GATEWAY_URL", "http://localhost:8002"
            ).rstrip("/"),
            provider_id=os.environ.get("ACP_ORCHESTRATOR_PROVIDER", "mock"),
            poll_interval=float(os.environ.get("ACP_WORKER_POLL_INTERVAL", "2.0")),
            step_seconds=float(os.environ.get("ACP_WORKER_STEP_SECONDS", "3.0")),
            state_dir=state_dir,
            name=os.environ.get("ACP_WORKER_NAME", socket.gethostname()),
            max_concurrency=max(1, int(os.environ.get("ACP_WORKER_MAX_CONCURRENCY", "1"))),
            simulation=os.environ.get("ACP_WORKER_SIMULATION", "1") == "1",
            registration_token=os.environ.get("ACP_WORKER_REGISTRATION_TOKEN"),
        )

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
