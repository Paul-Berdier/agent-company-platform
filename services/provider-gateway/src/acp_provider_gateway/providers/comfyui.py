"""Connecteur image ComfyUI optionnel et volontairement isolé du worker.

Le workflow est une configuration opérateur locale. La requête interne ne peut
fournir que le texte à injecter dans un emplacement JSON déjà configuré.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from acp_contracts import ServiceOriginError, normalize_service_origin


_MAX_WORKFLOW_BYTES = 2 * 1024 * 1024
_MAX_UPSTREAM_JSON_BYTES = 2 * 1024 * 1024
_MAX_CACHE_IMAGE_BYTES = 256 * 1024 * 1024
_MAX_INFLIGHT_GENERATIONS = 32
_MAX_INFLIGHT_IMAGE_BYTES = 128 * 1024 * 1024
_MAX_INFLIGHT_WAITERS = 64
_PROMPT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SAFE_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._() -]{0,254}$")
_SAFE_FOLDER_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._() -]{0,127}$")
_MEDIA_EXTENSIONS = {
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/webp": frozenset({".webp"}),
}
_COMFYUI_CONFIGURATION_ENV = frozenset(
    {
        "ACP_COMFYUI_ORIGIN",
        "ACP_COMFYUI_BASE_URL",
        "ACP_COMFYUI_WORKFLOW_PATH",
        "ACP_COMFYUI_PROMPT_NODE_ID",
        "ACP_COMFYUI_PROMPT_INPUT",
        "ACP_COMFYUI_OUTPUT_NODE_ID",
        "ACP_COMFYUI_API_TOKEN",
        "ACP_COMFYUI_TIMEOUT_SECONDS",
        "ACP_COMFYUI_POLL_INTERVAL_SECONDS",
        "ACP_COMFYUI_MAX_POLLS",
        "ACP_COMFYUI_MAX_IMAGE_BYTES",
        "ACP_COMFYUI_MAX_INFLIGHT_GENERATIONS",
        "ACP_COMFYUI_MAX_INFLIGHT_WAITERS",
        "ACP_COMFYUI_IDEMPOTENCY_MAX_ENTRIES",
        "ACP_COMFYUI_IDEMPOTENCY_MAX_BYTES",
        "ACP_COMFYUI_IDEMPOTENCY_TTL_SECONDS",
    }
)


class ComfyUIConfigurationError(ValueError):
    """Configuration locale absente ou dangereuse, sans recopier sa valeur."""


class ComfyUIDisabledError(RuntimeError):
    """Le connecteur n'a pas été activé explicitement."""


class ComfyUIUpstreamError(RuntimeError):
    """Échec amont expurgé de toute URL, réponse ou credential."""


class ComfyUITimeoutError(ComfyUIUpstreamError):
    """Le budget d'attente local est épuisé."""


class ComfyUIInvalidResponseError(ComfyUIUpstreamError):
    """ComfyUI a renvoyé une structure ou une image non fiable."""


class ComfyUIHTTPError(ComfyUIUpstreamError):
    """Réponse HTTP amont refusée sans conserver son corps."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("ComfyUI a refusé la requête")


class ComfyUIIdempotencyConflict(RuntimeError):
    """Une même clé process-local désigne une autre génération."""


class ComfyUIBusyError(RuntimeError):
    """La capacité bornée de générations simultanées est atteinte."""


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ComfyUIConfigurationError("Configuration numérique ComfyUI invalide") from exc
    if not minimum <= value <= maximum:
        raise ComfyUIConfigurationError("Configuration numérique ComfyUI hors limites")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ComfyUIConfigurationError("Configuration numérique ComfyUI invalide") from exc
    if not minimum <= value <= maximum:
        raise ComfyUIConfigurationError("Configuration numérique ComfyUI hors limites")
    return value


def _operator_key(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise ComfyUIConfigurationError(f"{label} ComfyUI invalide")
    return value


@dataclass(repr=False, frozen=True)
class ComfyUISettings:
    """Configuration chargée côté opérateur, jamais depuis une requête HTTP."""

    enabled: bool = False
    origin: str = ""
    workflow_path: str = ""
    prompt_node_id: str = ""
    prompt_input: str = ""
    output_node_id: str = ""
    api_token: str = field(default="", repr=False)
    timeout_seconds: float = 120.0
    poll_interval_seconds: float = 0.25
    max_polls: int = 480
    max_image_bytes: int = 20 * 1024 * 1024
    max_inflight_generations: int = 4
    max_inflight_waiters: int = 16
    idempotency_max_entries: int = 128
    idempotency_max_bytes: int = 64 * 1024 * 1024
    idempotency_ttl_seconds: float = 900.0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ComfyUIConfigurationError("Activation ComfyUI invalide")
        if not self.enabled:
            return

        try:
            normalized = normalize_service_origin(
                self.origin, setting="ACP_COMFYUI_ORIGIN"
            )
        except ServiceOriginError as exc:
            raise ComfyUIConfigurationError("Origine ComfyUI invalide") from exc
        object.__setattr__(self, "origin", normalized)

        path = Path(self.workflow_path)
        if not path.is_absolute():
            raise ComfyUIConfigurationError(
                "Le chemin du workflow ComfyUI doit être absolu"
            )
        object.__setattr__(self, "workflow_path", str(path))
        object.__setattr__(
            self,
            "prompt_node_id",
            _operator_key(self.prompt_node_id, label="Identifiant du nœud prompt"),
        )
        object.__setattr__(
            self,
            "prompt_input",
            _operator_key(self.prompt_input, label="Entrée du nœud prompt"),
        )
        object.__setattr__(
            self,
            "output_node_id",
            _operator_key(self.output_node_id, label="Identifiant du nœud de sortie"),
        )
        if (
            not isinstance(self.api_token, str)
            or len(self.api_token) > 4096
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in self.api_token
            )
        ):
            raise ComfyUIConfigurationError("Jeton ComfyUI invalide")

        if not 0.01 <= self.timeout_seconds <= 900:
            raise ComfyUIConfigurationError("Timeout ComfyUI hors limites")
        if not 0 <= self.poll_interval_seconds <= 30:
            raise ComfyUIConfigurationError("Intervalle de polling ComfyUI hors limites")
        if not 1 <= self.max_polls <= 10_000:
            raise ComfyUIConfigurationError("Nombre de polls ComfyUI hors limites")
        if not 1 <= self.max_image_bytes <= 100 * 1024 * 1024:
            raise ComfyUIConfigurationError("Taille image ComfyUI hors limites")
        if (
            not isinstance(self.max_inflight_generations, int)
            or isinstance(self.max_inflight_generations, bool)
            or not 1 <= self.max_inflight_generations <= _MAX_INFLIGHT_GENERATIONS
        ):
            raise ComfyUIConfigurationError("Concurrence ComfyUI hors limites")
        if (
            not isinstance(self.max_inflight_waiters, int)
            or isinstance(self.max_inflight_waiters, bool)
            or not 1 <= self.max_inflight_waiters <= _MAX_INFLIGHT_WAITERS
        ):
            raise ComfyUIConfigurationError("Attentes ComfyUI hors limites")
        if not 1 <= self.idempotency_max_entries <= 1_024:
            raise ComfyUIConfigurationError("Cache d'idempotence ComfyUI hors limites")
        if (
            not isinstance(self.idempotency_max_bytes, int)
            or isinstance(self.idempotency_max_bytes, bool)
            or not 1 <= self.idempotency_max_bytes <= _MAX_CACHE_IMAGE_BYTES
        ):
            raise ComfyUIConfigurationError("Budget mémoire ComfyUI hors limites")
        if self.idempotency_max_bytes < self.max_image_bytes:
            raise ComfyUIConfigurationError(
                "Le budget mémoire ComfyUI doit contenir au moins une image"
            )
        if (
            self.max_inflight_generations * self.max_image_bytes
            > _MAX_INFLIGHT_IMAGE_BYTES
        ):
            raise ComfyUIConfigurationError(
                "Le produit concurrence/taille ComfyUI dépasse la limite sûre"
            )
        if not 1 <= self.idempotency_ttl_seconds <= 86_400:
            raise ComfyUIConfigurationError("Durée d'idempotence ComfyUI hors limites")

    @classmethod
    def from_environment(cls) -> "ComfyUISettings":
        raw_enabled = os.environ.get("ACP_COMFYUI_ENABLED", "0")
        if raw_enabled not in {"0", "1"}:
            raise ComfyUIConfigurationError(
                "ACP_COMFYUI_ENABLED accepte uniquement 0 ou 1"
            )
        enabled = raw_enabled == "1"
        if not enabled:
            if any(os.environ.get(name) for name in _COMFYUI_CONFIGURATION_ENV):
                raise ComfyUIConfigurationError(
                    "ACP_COMFYUI_ENABLED=1 est requis avec la configuration ComfyUI"
                )
            return cls(enabled=False)

        origin = os.environ.get("ACP_COMFYUI_ORIGIN", "")
        base_url_alias = os.environ.get("ACP_COMFYUI_BASE_URL", "")
        if origin and base_url_alias and origin != base_url_alias:
            raise ComfyUIConfigurationError("Origines ComfyUI contradictoires")

        return cls(
            enabled=True,
            origin=origin or base_url_alias,
            workflow_path=os.environ.get("ACP_COMFYUI_WORKFLOW_PATH", ""),
            prompt_node_id=os.environ.get("ACP_COMFYUI_PROMPT_NODE_ID", ""),
            prompt_input=os.environ.get("ACP_COMFYUI_PROMPT_INPUT", ""),
            output_node_id=os.environ.get("ACP_COMFYUI_OUTPUT_NODE_ID", ""),
            api_token=os.environ.get("ACP_COMFYUI_API_TOKEN", ""),
            timeout_seconds=_bounded_float(
                "ACP_COMFYUI_TIMEOUT_SECONDS", 120.0, 0.01, 900
            ),
            poll_interval_seconds=_bounded_float(
                "ACP_COMFYUI_POLL_INTERVAL_SECONDS", 0.25, 0, 30
            ),
            max_polls=_bounded_int("ACP_COMFYUI_MAX_POLLS", 480, 1, 10_000),
            max_image_bytes=_bounded_int(
                "ACP_COMFYUI_MAX_IMAGE_BYTES",
                20 * 1024 * 1024,
                1,
                100 * 1024 * 1024,
            ),
            max_inflight_generations=_bounded_int(
                "ACP_COMFYUI_MAX_INFLIGHT_GENERATIONS",
                4,
                1,
                _MAX_INFLIGHT_GENERATIONS,
            ),
            max_inflight_waiters=_bounded_int(
                "ACP_COMFYUI_MAX_INFLIGHT_WAITERS",
                16,
                1,
                _MAX_INFLIGHT_WAITERS,
            ),
            idempotency_max_entries=_bounded_int(
                "ACP_COMFYUI_IDEMPOTENCY_MAX_ENTRIES", 128, 1, 1_024
            ),
            idempotency_max_bytes=_bounded_int(
                "ACP_COMFYUI_IDEMPOTENCY_MAX_BYTES",
                64 * 1024 * 1024,
                1,
                _MAX_CACHE_IMAGE_BYTES,
            ),
            idempotency_ttl_seconds=_bounded_float(
                "ACP_COMFYUI_IDEMPOTENCY_TTL_SECONDS", 900.0, 1, 86_400
            ),
        )


class ComfyUIImageRequest(BaseModel):
    """Seul le prompt utilisateur traverse la frontière interne."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=100_000)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


ComfyUIDiagnosticState = Literal[
    "not_configured",
    "invalid_configuration",
    "ready",
    "unauthorized",
    "timeout",
    "unavailable",
]


class ComfyUIDiagnostic(BaseModel):
    """Diagnostic volontairement sans origine, chemin, workflow ni token."""

    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["comfyui"] = "comfyui"
    status: ComfyUIDiagnosticState
    configured: bool
    ready: bool
    detail: str
    idempotency_scope: Literal["bounded_process_memory"] = "bounded_process_memory"
    idempotency_durable: Literal[False] = False
    worker_integration: Literal[False] = False


@dataclass(frozen=True)
class ComfyUIImage:
    content: bytes
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    filename: str
    replayed: bool = False


@dataclass(frozen=True)
class _PreparedWorkflow:
    document: dict[str, Any]
    digest: str


@dataclass(frozen=True)
class _CacheEntry:
    fingerprint: str
    image: ComfyUIImage
    expires_at: float


_FailureKind = Literal["timeout", "upstream"]


@dataclass(frozen=True)
class _FailureCacheEntry:
    fingerprint: str
    failure_kind: _FailureKind
    expires_at: float


@dataclass(frozen=True)
class _FailureOutcome:
    failure_kind: _FailureKind


@dataclass(frozen=True)
class _InflightEntry:
    fingerprint: str
    future: concurrent.futures.Future[ComfyUIImage | _FailureOutcome]


@dataclass
class _GenerationAttempt:
    prompt_attempted: bool = False


def _read_workflow(settings: ComfyUISettings, prompt: str) -> _PreparedWorkflow:
    path = Path(settings.workflow_path)
    try:
        if not path.is_file():
            raise ComfyUIConfigurationError("Workflow ComfyUI introuvable")
        with path.open("rb") as workflow_file:
            raw = workflow_file.read(_MAX_WORKFLOW_BYTES + 1)
    except ComfyUIConfigurationError:
        raise
    except OSError as exc:
        raise ComfyUIConfigurationError("Workflow ComfyUI illisible") from exc

    if not raw or len(raw) > _MAX_WORKFLOW_BYTES:
        raise ComfyUIConfigurationError("Taille du workflow ComfyUI invalide")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComfyUIConfigurationError("Workflow ComfyUI JSON invalide") from exc
    if not isinstance(document, dict):
        raise ComfyUIConfigurationError("Workflow ComfyUI doit être un objet JSON")

    workflow = copy.deepcopy(document)
    prompt_node = workflow.get(settings.prompt_node_id)
    if not isinstance(prompt_node, dict):
        raise ComfyUIConfigurationError("Nœud prompt ComfyUI introuvable")
    inputs = prompt_node.get("inputs")
    if not isinstance(inputs, dict):
        raise ComfyUIConfigurationError("Entrées du nœud prompt ComfyUI invalides")
    if settings.prompt_input not in inputs or not isinstance(
        inputs[settings.prompt_input], str
    ):
        raise ComfyUIConfigurationError("Entrée prompt ComfyUI introuvable")
    if not isinstance(workflow.get(settings.output_node_id), dict):
        raise ComfyUIConfigurationError("Nœud de sortie ComfyUI introuvable")

    inputs[settings.prompt_input] = prompt
    digest = hashlib.sha256(raw).hexdigest()
    return _PreparedWorkflow(document=workflow, digest=digest)


def _request_fingerprint(
    settings: ComfyUISettings, workflow_digest: str, prompt: str
) -> str:
    token_digest = hashlib.sha256(settings.api_token.encode("utf-8")).hexdigest()
    material = json.dumps(
        {
            "origin": settings.origin,
            "workflow": workflow_digest,
            "prompt_node": settings.prompt_node_id,
            "prompt_input": settings.prompt_input,
            "output_node": settings.output_node_id,
            "token": token_digest,
            "prompt": prompt,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


async def _bounded_body(response: httpx.Response, maximum: int) -> bytes:
    length_header = response.headers.get("Content-Length")
    if length_header is not None:
        try:
            declared = int(length_header)
        except ValueError as exc:
            raise ComfyUIInvalidResponseError("Taille amont invalide") from exc
        if declared < 0 or declared > maximum:
            raise ComfyUIInvalidResponseError("Réponse amont trop volumineuse")

    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > maximum:
            raise ComfyUIInvalidResponseError("Réponse amont trop volumineuse")
        chunks.append(chunk)
    return b"".join(chunks)


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComfyUIInvalidResponseError("Réponse JSON ComfyUI invalide") from exc
    if not isinstance(value, dict):
        raise ComfyUIInvalidResponseError("Réponse JSON ComfyUI invalide")
    return value


def _safe_prompt_id(payload: dict[str, Any]) -> str:
    prompt_id = payload.get("prompt_id")
    if not isinstance(prompt_id, str) or _PROMPT_ID_PATTERN.fullmatch(prompt_id) is None:
        raise ComfyUIInvalidResponseError("Identifiant ComfyUI invalide")
    return prompt_id


def _safe_output_metadata(
    history: dict[str, Any], prompt_id: str, output_node_id: str
) -> tuple[str, str, str]:
    if set(history) != {prompt_id}:
        raise ComfyUIInvalidResponseError("Historique ComfyUI invalide")
    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        raise ComfyUIInvalidResponseError("Historique ComfyUI invalide")
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        raise ComfyUIInvalidResponseError("Sorties ComfyUI invalides")
    output = outputs.get(output_node_id)
    if not isinstance(output, dict):
        raise ComfyUIInvalidResponseError("Nœud de sortie ComfyUI absent")
    images = output.get("images")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict):
        raise ComfyUIInvalidResponseError("Image ComfyUI absente")
    metadata = images[0]
    if set(metadata) != {"filename", "subfolder", "type"}:
        raise ComfyUIInvalidResponseError("Métadonnées de sortie ComfyUI invalides")

    filename = metadata.get("filename")
    subfolder = metadata.get("subfolder")
    output_type = metadata.get("type")
    if (
        not isinstance(filename, str)
        or _SAFE_FILE_PATTERN.fullmatch(filename) is None
        or filename in {".", ".."}
        or filename.endswith((" ", "."))
    ):
        raise ComfyUIInvalidResponseError("Nom de sortie ComfyUI invalide")
    if output_type != "output":
        raise ComfyUIInvalidResponseError("Type de sortie ComfyUI invalide")
    if not isinstance(subfolder, str) or len(subfolder) > 512 or "\\" in subfolder:
        raise ComfyUIInvalidResponseError("Sous-dossier ComfyUI invalide")
    if subfolder:
        segments = subfolder.split("/")
        if any(
            segment in {"", ".", ".."}
            or _SAFE_FOLDER_SEGMENT_PATTERN.fullmatch(segment) is None
            or segment.endswith((" ", "."))
            for segment in segments
        ):
            raise ComfyUIInvalidResponseError("Sous-dossier ComfyUI invalide")
    return filename, subfolder, output_type


def _validated_image(content: bytes, media_type: str, filename: str) -> ComfyUIImage:
    normalized_type = media_type.partition(";")[0].strip().lower()
    if normalized_type not in _MEDIA_EXTENSIONS:
        raise ComfyUIInvalidResponseError("Type d'image ComfyUI interdit")

    magic_matches = (
        normalized_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")
    ) or (
        normalized_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")
    ) or (
        normalized_type == "image/webp"
        and len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP"
    )
    if not magic_matches:
        raise ComfyUIInvalidResponseError("Signature d'image ComfyUI incohérente")

    extension = Path(filename).suffix.casefold()
    if extension not in _MEDIA_EXTENSIONS[normalized_type]:
        raise ComfyUIInvalidResponseError("Extension d'image ComfyUI incohérente")
    return ComfyUIImage(
        content=content,
        media_type=normalized_type,  # type: ignore[arg-type]
        filename=filename,
    )


class ComfyUIConnector:
    """Client ComfyUI avec cache d'idempotence borné et non durable."""

    def __init__(
        self,
        settings: ComfyUISettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._cache: OrderedDict[str, _CacheEntry | _FailureCacheEntry] = OrderedDict()
        self._cache_image_bytes = 0
        self._inflight: dict[str, _InflightEntry] = {}
        self._inflight_waiters = 0
        self._cache_lock = threading.Lock()

    def _current_settings(self) -> ComfyUISettings:
        return self._settings or ComfyUISettings.from_environment()

    def _client(self, settings: ComfyUISettings) -> httpx.AsyncClient:
        headers = (
            {"Authorization": f"Bearer {settings.api_token}"}
            if settings.api_token
            else None
        )
        return httpx.AsyncClient(
            base_url=settings.origin,
            headers=headers,
            timeout=settings.timeout_seconds,
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
        )

    def _remove_cache_entry_locked(self, key: str) -> None:
        entry = self._cache.pop(key, None)
        if isinstance(entry, _CacheEntry):
            self._cache_image_bytes -= len(entry.image.content)

    def _prune_cache_locked(
        self, settings: ComfyUISettings, *, now: float
    ) -> None:
        expired = [
            key for key, entry in self._cache.items() if entry.expires_at <= now
        ]
        for key in expired:
            self._remove_cache_entry_locked(key)
        while (
            len(self._cache) > settings.idempotency_max_entries
            or self._cache_image_bytes > settings.idempotency_max_bytes
        ):
            oldest_image_key = next(
                (
                    key
                    for key, entry in self._cache.items()
                    if isinstance(entry, _CacheEntry)
                ),
                None,
            )
            if oldest_image_key is None:
                break
            self._remove_cache_entry_locked(oldest_image_key)

    def _failure_count_locked(self) -> int:
        return sum(
            isinstance(entry, _FailureCacheEntry) for entry in self._cache.values()
        )

    def _store_failure_locked(
        self,
        settings: ComfyUISettings,
        *,
        idempotency_key: str,
        fingerprint: str,
        failure_kind: _FailureKind,
        now: float,
    ) -> None:
        self._remove_cache_entry_locked(idempotency_key)
        self._cache[idempotency_key] = _FailureCacheEntry(
            fingerprint=fingerprint,
            failure_kind=failure_kind,
            expires_at=now + settings.idempotency_ttl_seconds,
        )
        self._cache.move_to_end(idempotency_key)
        self._prune_cache_locked(settings, now=now)

    def _store_image_locked(
        self,
        settings: ComfyUISettings,
        *,
        idempotency_key: str,
        fingerprint: str,
        image: ComfyUIImage,
        now: float,
    ) -> None:
        self._remove_cache_entry_locked(idempotency_key)
        self._cache[idempotency_key] = _CacheEntry(
            fingerprint=fingerprint,
            image=image,
            expires_at=now + settings.idempotency_ttl_seconds,
        )
        self._cache_image_bytes += len(image.content)
        self._cache.move_to_end(idempotency_key)
        self._prune_cache_locked(settings, now=now)

    @staticmethod
    def _safe_failure(failure_kind: _FailureKind) -> ComfyUIUpstreamError:
        if failure_kind == "timeout":
            return ComfyUITimeoutError("Délai ComfyUI dépassé")
        return ComfyUIUpstreamError(
            "Résultat ComfyUI indéterminé pour cette clé d'idempotence"
        )

    async def _await_inflight(
        self,
        future: concurrent.futures.Future[ComfyUIImage | _FailureOutcome],
    ) -> ComfyUIImage:
        waiter = asyncio.wrap_future(future)
        outcome = await asyncio.shield(waiter)
        if isinstance(outcome, _FailureOutcome):
            raise self._safe_failure(outcome.failure_kind)
        return outcome

    async def diagnostic(self) -> ComfyUIDiagnostic:
        try:
            settings = self._current_settings()
        except ComfyUIConfigurationError:
            return ComfyUIDiagnostic(
                status="invalid_configuration",
                configured=False,
                ready=False,
                detail="Configuration ComfyUI invalide",
            )
        if not settings.enabled:
            return ComfyUIDiagnostic(
                status="not_configured",
                configured=False,
                ready=False,
                detail="Connecteur ComfyUI non activé",
            )
        try:
            _read_workflow(settings, "diagnostic")
        except ComfyUIConfigurationError:
            return ComfyUIDiagnostic(
                status="invalid_configuration",
                configured=False,
                ready=False,
                detail="Configuration ComfyUI invalide",
            )

        try:
            async with asyncio.timeout(settings.timeout_seconds):
                async with self._client(settings) as client:
                    async with client.stream("GET", "/system_stats") as response:
                        if response.status_code in {401, 403}:
                            return ComfyUIDiagnostic(
                                status="unauthorized",
                                configured=True,
                                ready=False,
                                detail="Authentification ComfyUI refusée",
                            )
                        if not 200 <= response.status_code < 300:
                            return ComfyUIDiagnostic(
                                status="unavailable",
                                configured=True,
                                ready=False,
                                detail="Service ComfyUI indisponible",
                            )
        except (TimeoutError, httpx.TimeoutException):
            return ComfyUIDiagnostic(
                status="timeout",
                configured=True,
                ready=False,
                detail="Délai ComfyUI dépassé",
            )
        except httpx.RequestError:
            return ComfyUIDiagnostic(
                status="unavailable",
                configured=True,
                ready=False,
                detail="Service ComfyUI indisponible",
            )
        return ComfyUIDiagnostic(
            status="ready",
            configured=True,
            ready=True,
            detail="ComfyUI prêt pour la génération d'images",
        )

    async def generate(
        self, request: ComfyUIImageRequest, *, idempotency_key: str
    ) -> ComfyUIImage:
        settings = self._current_settings()
        if not settings.enabled:
            raise ComfyUIDisabledError("Connecteur ComfyUI non activé")
        prepared = _read_workflow(settings, request.prompt)
        fingerprint = _request_fingerprint(settings, prepared.digest, request.prompt)

        owner = False
        waiter_registered = False
        future: concurrent.futures.Future[ComfyUIImage | _FailureOutcome]
        now = time.monotonic()
        with self._cache_lock:
            self._prune_cache_locked(settings, now=now)

            cached = self._cache.get(idempotency_key)
            if cached is not None:
                if cached.fingerprint != fingerprint:
                    raise ComfyUIIdempotencyConflict(
                        "Clé d'idempotence déjà utilisée pour une autre requête"
                    )
                self._cache.move_to_end(idempotency_key)
                if isinstance(cached, _FailureCacheEntry):
                    raise self._safe_failure(cached.failure_kind)
                return replace(cached.image, replayed=True)

            inflight = self._inflight.get(idempotency_key)
            if inflight is not None:
                if inflight.fingerprint != fingerprint:
                    raise ComfyUIIdempotencyConflict(
                        "Clé d'idempotence déjà utilisée pour une autre requête"
                    )
                if self._inflight_waiters >= settings.max_inflight_waiters:
                    raise ComfyUIBusyError(
                        "Capacité d'attentes ComfyUI simultanées atteinte"
                    )
                self._inflight_waiters += 1
                waiter_registered = True
                future = inflight.future
            else:
                if len(self._inflight) >= settings.max_inflight_generations:
                    raise ComfyUIBusyError(
                        "Capacité de générations ComfyUI simultanées atteinte"
                    )
                if (
                    self._failure_count_locked() + len(self._inflight)
                    >= settings.idempotency_max_entries
                ):
                    raise ComfyUIBusyError(
                        "Capacité d'idempotence ComfyUI temporairement atteinte"
                    )
                future = concurrent.futures.Future()
                self._inflight[idempotency_key] = _InflightEntry(fingerprint, future)
                owner = True

        if not owner:
            del prepared
            try:
                image = await self._await_inflight(future)
            finally:
                if waiter_registered:
                    with self._cache_lock:
                        self._inflight_waiters -= 1
            return replace(image, replayed=True)

        attempt = _GenerationAttempt()
        try:
            image = await self._generate_uncached(
                settings, prepared.document, attempt=attempt
            )
        except BaseException as exc:
            failure_kind: _FailureKind = (
                "timeout" if isinstance(exc, ComfyUITimeoutError) else "upstream"
            )
            with self._cache_lock:
                self._inflight.pop(idempotency_key, None)
                if attempt.prompt_attempted:
                    self._store_failure_locked(
                        settings,
                        idempotency_key=idempotency_key,
                        fingerprint=fingerprint,
                        failure_kind=failure_kind,
                        now=time.monotonic(),
                    )
                if not future.done():
                    future.set_result(_FailureOutcome(failure_kind))
            raise

        with self._cache_lock:
            self._inflight.pop(idempotency_key, None)
            self._store_image_locked(
                settings,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                image=image,
                now=time.monotonic(),
            )
            if not future.done():
                future.set_result(image)
        return image

    async def _generate_uncached(
        self,
        settings: ComfyUISettings,
        workflow: dict[str, Any],
        *,
        attempt: _GenerationAttempt,
    ) -> ComfyUIImage:
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                async with self._client(settings) as client:
                    attempt.prompt_attempted = True
                    prompt_response = await self._request_json(
                        client, "POST", "/prompt", payload={"prompt": workflow}
                    )
                    prompt_id = _safe_prompt_id(prompt_response)
                    filename, subfolder, output_type = await self._poll_output(
                        client, settings, prompt_id
                    )
                    async with client.stream(
                        "GET",
                        "/view",
                        params={
                            "filename": filename,
                            "subfolder": subfolder,
                            "type": output_type,
                        },
                    ) as response:
                        if not 200 <= response.status_code < 300:
                            raise ComfyUIHTTPError(response.status_code)
                        content = await _bounded_body(response, settings.max_image_bytes)
                        return _validated_image(
                            content, response.headers.get("Content-Type", ""), filename
                        )
        except ComfyUIUpstreamError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ComfyUITimeoutError("Délai ComfyUI dépassé") from exc
        except httpx.RequestError as exc:
            raise ComfyUIUpstreamError("Service ComfyUI indisponible") from exc

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with client.stream(method, path, json=payload) as response:
            if not 200 <= response.status_code < 300:
                raise ComfyUIHTTPError(response.status_code)
            raw = await _bounded_body(response, _MAX_UPSTREAM_JSON_BYTES)
        return _json_object(raw)

    async def _poll_output(
        self,
        client: httpx.AsyncClient,
        settings: ComfyUISettings,
        prompt_id: str,
    ) -> tuple[str, str, str]:
        for poll_index in range(settings.max_polls):
            history = await self._request_json(
                client, "GET", f"/history/{prompt_id}"
            )
            if history:
                return _safe_output_metadata(
                    history, prompt_id, settings.output_node_id
                )
            if poll_index + 1 < settings.max_polls:
                await asyncio.sleep(settings.poll_interval_seconds)
        raise ComfyUITimeoutError("Historique ComfyUI non disponible à temps")


__all__ = [
    "ComfyUIBusyError",
    "ComfyUIConfigurationError",
    "ComfyUIConnector",
    "ComfyUIDiagnostic",
    "ComfyUIDisabledError",
    "ComfyUIHTTPError",
    "ComfyUIIdempotencyConflict",
    "ComfyUIImage",
    "ComfyUIImageRequest",
    "ComfyUIInvalidResponseError",
    "ComfyUISettings",
    "ComfyUITimeoutError",
    "ComfyUIUpstreamError",
]
