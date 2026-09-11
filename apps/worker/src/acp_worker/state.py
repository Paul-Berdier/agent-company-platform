"""État local persistant du worker (le jeton n'est jamais journalisé)."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import WorkerConfigurationError, normalize_service_origin


class CredentialStateError(RuntimeError):
    """L'état local ne peut pas être utilisé en toute sécurité."""


@dataclass(frozen=True)
class WorkerCredentials:
    worker_id: str
    token: str = field(repr=False)
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
    path = state_file(state_dir)
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=state_dir,
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        # ``mkstemp`` crée déjà le fichier en 0600 sur POSIX. L'appel explicite
        # conserve cet invariant avant le premier octet, y compris si
        # l'implémentation de la plateforme évolue.
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            # Sous Windows, ces bits POSIX ne configurent pas la DACL :
            # l'opérateur doit protéger explicitement le dossier d'état.
            pass

        handle = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
        descriptor = None
        with handle:
            json.dump(asdict(credentials), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path
    except (OSError, TypeError, ValueError) as exc:
        raise CredentialStateError(
            "Impossible d'enregistrer les credentials worker de façon sûre"
        ) from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
