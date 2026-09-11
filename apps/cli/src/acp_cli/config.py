"""Configuration locale minimale et écriture atomique des secrets de session."""

from __future__ import annotations

import ipaddress
import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, TypeVar
from urllib.parse import urlsplit


DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_WEB_URL = "http://127.0.0.1:5173"
PENDING_OPERATION_VERSION = 2
CONFIG_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_RETRY_SECONDS = 0.05
T = TypeVar("T")


class ConfigError(ValueError):
    """La configuration locale est illisible ou invalide."""


@dataclass(frozen=True, repr=False)
class PendingOperation:
    """Requête d'écriture dont la réponse HTTP reste incertaine.

    Seuls des identifiants non secrets et des empreintes SHA-256 sont
    persistés. Le payload de mission et les credentials ne sont jamais
    dupliqués dans cet enregistrement.
    """

    operation: str
    api_endpoint: str
    principal_session_fingerprint: str
    payload_fingerprint: str
    idempotency_key: str
    dispatch_count: int = 1


@dataclass(frozen=True, repr=False)
class Settings:
    """Paramètres du client.

    Le ``repr`` est volontairement désactivé : cette structure transporte deux
    secrets qui ne doivent pas finir dans les journaux ou les messages d'erreur.
    """

    api_url: str = DEFAULT_API_URL
    web_url: str = DEFAULT_WEB_URL
    session_cookie: str | None = None
    csrf_token: str | None = None
    session_origin: str | None = None
    principal_id: str | None = None
    pending_operation: PendingOperation | None = None

    @property
    def authenticated(self) -> bool:
        return bool(
            self.session_cookie
            and self.session_origin
            and self.session_origin == normalized_origin(self.api_url)
        )

    def with_session(
        self,
        session_cookie: str,
        csrf_token: str,
        principal_id: str | None = None,
    ) -> "Settings":
        if not session_cookie or not csrf_token:
            raise ConfigError("credentials de session incomplets")
        clean_principal_id = principal_id.strip() if principal_id else None
        return replace(
            self,
            session_cookie=session_cookie,
            csrf_token=csrf_token,
            session_origin=normalized_origin(self.api_url),
            principal_id=clean_principal_id,
        )

    def without_session(self) -> "Settings":
        return replace(
            self,
            session_cookie=None,
            csrf_token=None,
            session_origin=None,
            principal_id=None,
        )


def default_config_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get("ACP_CONFIG_PATH")
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt" and env.get("APPDATA"):
        base = Path(env["APPDATA"])
    elif env.get("XDG_CONFIG_HOME"):
        base = Path(env["XDG_CONFIG_HOME"])
    else:
        base = Path.home() / ".config"
    return base / "agent-company-platform" / "config.json"


def _hostname(parsed, field: str) -> str:
    try:
        hostname = parsed.hostname
        # L'accès à ``port`` force également la validation de sa syntaxe.
        parsed.port
    except ValueError as exc:
        raise ConfigError(f"{field} contient un hôte ou un port invalide") from exc
    if not hostname:
        raise ConfigError(f"{field} doit contenir un hôte")
    return hostname.rstrip(".").casefold()


def _is_loopback(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _clean_url(value: str, field: str) -> str:
    value = value.strip().rstrip("/")
    if not value or any(ord(character) < 32 for character in value) or "\\" in value:
        raise ConfigError(f"{field} contient des caractères interdits")
    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{field} doit être une URL HTTP(S) absolue")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError(f"{field} ne doit pas contenir d'identifiants")
    if parsed.query or parsed.fragment:
        raise ConfigError(f"{field} ne doit pas contenir de query string ni de fragment")
    hostname = _hostname(parsed, field)
    if scheme == "http" and not _is_loopback(hostname):
        raise ConfigError(f"{field} exige HTTPS hors loopback")
    return value


def normalized_origin(value: str) -> str:
    """Retourne l'origine RFC 6454 utilisée pour lier les credentials locaux."""

    clean = _clean_url(value, "api_url")
    parsed = urlsplit(clean)
    scheme = parsed.scheme.casefold()
    hostname = _hostname(parsed, "api_url")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            canonical_host = hostname.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ConfigError("api_url contient un nom d'hôte invalide") from exc
    else:
        canonical_host = address.compressed.casefold()
        if address.version == 6:
            canonical_host = f"[{canonical_host}]"
    port = parsed.port
    default_port = 80 if scheme == "http" else 443
    suffix = "" if port is None or port == default_port else f":{port}"
    return f"{scheme}://{canonical_host}{suffix}"


def normalized_api_endpoint(value: str) -> str:
    """Lie une reprise à une base API précise, chemin compris.

    Les cookies restent correctement liés à l'origine RFC 6454, mais une clé
    d'idempotence ne doit jamais traverser deux applications montées sous des
    chemins différents de cette même origine.
    """

    clean = _clean_url(value, "api_url")
    parsed = urlsplit(clean)
    return f"{normalized_origin(clean)}{parsed.path}"


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"champ de configuration invalide : {key}")
    return value


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _pending_operation(
    data: Mapping[str, Any],
    *,
    legacy_api_url: str | None,
) -> PendingOperation | None:
    value = data.get("pending_operation")
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("version") not in {
        1,
        PENDING_OPERATION_VERSION,
    }:
        raise ConfigError("opération pending invalide")
    operation = _optional_string(value, "operation")
    version = value["version"]
    if version == 1:
        legacy_origin = _optional_string(value, "api_origin")
        if operation != "mission-create" or legacy_api_url is None:
            raise ConfigError("opération pending historique non récupérable")
        if legacy_origin != normalized_origin(legacy_api_url):
            raise ConfigError("origine d'opération pending historique invalide")
        api_endpoint = normalized_api_endpoint(legacy_api_url)
    else:
        api_endpoint = _optional_string(value, "api_endpoint")
    principal = _optional_string(value, "principal_session_fingerprint")
    payload = _optional_string(value, "payload_fingerprint")
    key = _optional_string(value, "idempotency_key")
    dispatch_count = value.get("dispatch_count", 1)
    if any(
        item is None
        for item in (operation, api_endpoint, principal, payload, key)
    ):
        raise ConfigError("opération pending incomplète")
    if operation not in {"mission-create", "mission-stop"}:
        raise ConfigError("type d'opération pending invalide")
    if api_endpoint != normalized_api_endpoint(api_endpoint):
        raise ConfigError("endpoint d'opération pending invalide")
    if not _is_sha256(principal) or not _is_sha256(payload):
        raise ConfigError("empreinte d'opération pending invalide")
    if len(key) > 200 or any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise ConfigError("clé d'opération pending invalide")
    if (
        not isinstance(dispatch_count, int)
        or isinstance(dispatch_count, bool)
        or dispatch_count < 1
    ):
        raise ConfigError("compteur d'opération pending invalide")
    return PendingOperation(
        operation=operation,
        api_endpoint=api_endpoint,
        principal_session_fingerprint=principal,
        payload_fingerprint=payload,
        idempotency_key=key,
        dispatch_count=dispatch_count,
    )


def settings_with_url_overrides(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
    api_url: str | None = None,
    web_url: str | None = None,
) -> Settings:
    """Applique les overrides à un snapshot sans relire le fichier.

    Cette séparation évite qu'une modification concurrente du fichier ne
    change silencieusement la destination réseau entre la capture servant au
    CAS et la construction du client HTTP.
    """

    env = os.environ if environ is None else environ
    selected_api_url = api_url or env.get("ACP_API_URL") or settings.api_url
    selected_web_url = web_url or env.get("ACP_WEB_URL") or settings.web_url
    if not isinstance(selected_api_url, str) or not isinstance(selected_web_url, str):
        raise ConfigError("les URL de configuration doivent être des chaînes")
    updated = replace(
        settings,
        api_url=_clean_url(selected_api_url, "api_url"),
        web_url=_clean_url(selected_web_url, "web_url"),
    )
    if (
        updated.session_cookie
        and updated.session_origin == normalized_origin(updated.api_url)
    ):
        return updated
    return updated.without_session()


def load_settings(
    path: Path,
    *,
    environ: Mapping[str, str] | None = None,
    api_url: str | None = None,
    web_url: str | None = None,
) -> Settings:
    env = os.environ if environ is None else environ
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigError(f"configuration illisible : {path}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError("la configuration doit être un objet JSON")
        data = loaded

    selected_api_url = api_url or env.get("ACP_API_URL") or data.get("api_url") or DEFAULT_API_URL
    selected_web_url = web_url or env.get("ACP_WEB_URL") or data.get("web_url") or DEFAULT_WEB_URL
    if not isinstance(selected_api_url, str) or not isinstance(selected_web_url, str):
        raise ConfigError("les URL de configuration doivent être des chaînes")
    clean_api_url = _clean_url(selected_api_url, "api_url")
    clean_web_url = _clean_url(selected_web_url, "web_url")
    session_cookie = _optional_string(data, "session_cookie")
    csrf_token = _optional_string(data, "csrf_token")
    session_origin = _optional_string(data, "session_origin")
    principal_id = _optional_string(data, "principal_id")
    stored_api_url = data.get("api_url")
    pending_operation = _pending_operation(
        data,
        legacy_api_url=stored_api_url if isinstance(stored_api_url, str) else None,
    )
    if session_cookie:
        # Les anciens fichiers étaient implicitement liés à leur ``api_url``.
        # Une origine explicite devient persistée au prochain enregistrement.
        candidate_origin = session_origin
        if candidate_origin is None and isinstance(data.get("api_url"), str):
            candidate_origin = data["api_url"]
        try:
            bound_origin = (
                normalized_origin(candidate_origin) if candidate_origin else None
            )
        except ConfigError:
            bound_origin = None
        if bound_origin != normalized_origin(clean_api_url):
            session_cookie = None
            csrf_token = None
            bound_origin = None
            principal_id = None
    else:
        csrf_token = None
        bound_origin = None
        principal_id = None
    return Settings(
        api_url=clean_api_url,
        web_url=clean_web_url,
        session_cookie=session_cookie,
        csrf_token=csrf_token,
        session_origin=bound_origin,
        principal_id=principal_id,
        pending_operation=pending_operation,
    )


def _save_settings_unlocked(path: Path, settings: Settings) -> None:
    """Écrit atomiquement la configuration ; l'appelant sérialise les mutations."""

    clean_api_url = _clean_url(settings.api_url, "api_url")
    clean_web_url = _clean_url(settings.web_url, "web_url")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            text=True,
        )
    except OSError as exc:
        raise ConfigError(f"impossible de préparer la configuration : {path}") from exc

    temporary_path = Path(temporary_name)
    credentials_are_bound = settings.authenticated
    payload = {
        "api_url": clean_api_url,
        "web_url": clean_web_url,
        "session_cookie": settings.session_cookie if credentials_are_bound else None,
        "csrf_token": settings.csrf_token if credentials_are_bound else None,
        "session_origin": (
            normalized_origin(clean_api_url) if credentials_are_bound else None
        ),
        "principal_id": settings.principal_id if credentials_are_bound else None,
        "pending_operation": (
            {
                "version": PENDING_OPERATION_VERSION,
                "operation": settings.pending_operation.operation,
                "api_endpoint": settings.pending_operation.api_endpoint,
                "principal_session_fingerprint": (
                    settings.pending_operation.principal_session_fingerprint
                ),
                "payload_fingerprint": settings.pending_operation.payload_fingerprint,
                "idempotency_key": settings.pending_operation.idempotency_key,
                "dispatch_count": settings.pending_operation.dispatch_count,
            }
            if settings.pending_operation is not None
            else None
        ),
    }
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            # Windows et certains volumes ne proposent pas les bits POSIX.
            pass
        os.replace(temporary_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConfigError(f"impossible d'enregistrer la configuration : {path}") from exc


def _lock_file(path: Path) -> BinaryIO:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.with_name(f"{path.name}.lock").open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(handle.name, 0o600)
        except OSError:
            pass
        return handle
    except OSError as exc:
        raise ConfigError(f"impossible de préparer le verrou : {path}") from exc


def _try_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _config_lock(path: Path, timeout: float):
    if timeout < 0:
        raise ConfigError("le délai du verrou de configuration doit être positif")
    handle = _lock_file(path)
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while True:
            try:
                _try_lock(handle)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ConfigError(
                        "configuration occupée par une autre commande ; réessayez"
                    ) from None
                time.sleep(_LOCK_RETRY_SECONDS)
        yield
    finally:
        if acquired:
            try:
                _unlock(handle)
            except OSError:
                pass
        handle.close()


class _PendingDispatchLock:
    """Verrou non bloquant dont ``__exit__`` accepte les exceptions gelées."""

    def __init__(self, path: Path) -> None:
        self._marker = path.with_name(f"{path.name}.pending-dispatch")
        self._handle: BinaryIO | None = None

    def __enter__(self) -> None:
        handle = _lock_file(self._marker)
        try:
            _try_lock(handle)
        except OSError:
            handle.close()
            raise ConfigError(
                "une autre mutation pending est déjà en cours ; "
                "réessayez après sa fin"
            ) from None
        self._handle = handle

    def __exit__(self, *_exception: object) -> bool:
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                _unlock(handle)
            except OSError:
                pass
            handle.close()
        return False


def pending_dispatch_lock(path: Path) -> _PendingDispatchLock:
    """Exclut un second dispatch pendant toute une mutation HTTP.

    Ce verrou est distinct du verrou court de configuration : il peut rester
    détenu pendant un appel réseau sans empêcher un rafraîchissement de session
    ou une simple lecture. Le système d'exploitation le libère si le processus
    s'arrête brutalement, tandis que le pending persistant garde la clé à
    réutiliser au prochain essai.
    """

    return _PendingDispatchLock(path)


def mutate_settings(
    path: Path,
    mutation: Callable[[Settings], tuple[Settings, T]],
    *,
    environ: Mapping[str, str] | None = None,
    api_url: str | None = None,
    web_url: str | None = None,
    lock_timeout: float = CONFIG_LOCK_TIMEOUT_SECONDS,
) -> tuple[Settings, T]:
    """Relit, transforme et écrit la configuration sous verrou interprocessus.

    La fonction de mutation doit rester locale et rapide : aucun appel réseau ni
    aucune saisie utilisateur ne doit être effectué pendant sa durée.
    """

    with _config_lock(path, lock_timeout):
        current = load_settings(
            path,
            environ=environ,
            api_url=api_url,
            web_url=web_url,
        )
        updated, result = mutation(current)
        if not isinstance(updated, Settings):
            raise ConfigError("mutation de configuration invalide")
        if updated != current:
            _save_settings_unlocked(path, updated)
        return updated, result


def save_settings(path: Path, settings: Settings) -> None:
    """Écrit la configuration atomiquement sous verrou interprocessus."""

    with _config_lock(path, CONFIG_LOCK_TIMEOUT_SECONDS):
        _save_settings_unlocked(path, settings)
