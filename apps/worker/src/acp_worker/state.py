"""État local persistant du worker (le jeton n'est jamais journalisé)."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import WorkerConfigurationError, normalize_service_origin


class CredentialStateError(RuntimeError):
    """L'état local ne peut pas être utilisé en toute sécurité."""


@dataclass(frozen=True)
class WorkerCredentials:
    worker_id: str
    token: str
    api_origin: str
    name: str
    capabilities: list[str]
    max_concurrency: int
    simulation: bool
    token_expires_at: str
    heartbeat_interval_seconds: int = 15

    def __post_init__(self) -> None:
        try:
            origin = normalize_service_origin(
                self.api_origin, setting="origine API des credentials"
            )
        except WorkerConfigurationError as exc:
            raise CredentialStateError(str(exc)) from exc
        object.__setattr__(self, "api_origin", origin)


def state_file(state_dir: Path) -> Path:
    return state_dir / "worker.json"


def load_credentials(state_dir: Path, api_origin: str) -> WorkerCredentials | None:
    path = state_file(state_dir)
    if not path.exists():
        return None
    try:
        expected_origin = normalize_service_origin(api_origin, setting="ACP_API_URL")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, WorkerConfigurationError) as exc:
        raise CredentialStateError("Fichier de credentials worker invalide") from exc
    if not isinstance(data, dict):
        raise CredentialStateError("Fichier de credentials worker invalide")
    if "api_origin" not in data:
        raise CredentialStateError(
            "Credentials antérieurs non liés à une origine; réenregistrement requis"
        )
    try:
        credentials = WorkerCredentials(**data)
    except (TypeError, CredentialStateError) as exc:
        raise CredentialStateError("Fichier de credentials worker invalide") from exc
    if credentials.api_origin != expected_origin:
        raise CredentialStateError(
            "Credentials liés à une autre origine API; réenregistrement requis"
        )
    return credentials


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
