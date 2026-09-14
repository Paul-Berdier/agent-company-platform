"""Bornes pré-authentification des corps HTTP et de l'entrée webhook publique."""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable
from time import monotonic

from acp_contracts import WEBHOOK_MAX_BODY_BYTES
from starlette.responses import JSONResponse

WEBHOOK_RATE_LIMIT_REQUESTS = 120
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS = 60.0
_MAX_TRACKED_CLIENTS = 10_000
SKILL_SOURCE_MAX_BODY_BYTES = 32 * 1024 * 1024


class _RequestBodyTooLarge(RuntimeError):
    pass


def _is_webhook_trigger(scope: dict) -> bool:
    if scope.get("type") != "http" or scope.get("method") != "POST":
        return False
    parts = [part for part in str(scope.get("path", "")).split("/") if part]
    return (
        len(parts) == 4
        and parts[0] == "automations"
        and bool(parts[1])
        and parts[2:] == ["webhook", "trigger"]
    )


def _is_streamed_artifact_upload(scope: dict) -> bool:
    if scope.get("type") != "http" or scope.get("method") != "POST":
        return False
    parts = [part for part in str(scope.get("path", "")).split("/") if part]
    return (
        len(parts) == 4
        and parts[0] == "workers"
        and bool(parts[1])
        and parts[2:] == ["artifacts", "content"]
    )


def _is_skill_source_request(scope: dict) -> bool:
    if scope.get("type") != "http" or scope.get("method") != "POST":
        return False
    parts = [part for part in str(scope.get("path", "")).split("/") if part]
    return parts == ["skills", "import"] or (
        len(parts) == 3
        and parts[0] == "skills"
        and bool(parts[1])
        and parts[2] == "revisions"
    )


class RequestIngressGuardMiddleware:
    """Refuse les corps excessifs et les rafales avant le parsing applicatif.

    Le compteur est volontairement fondé sur l'adresse TCP observée, jamais sur
    ``X-Forwarded-For`` qui n'est fiable qu'avec une configuration explicite de
    proxy. Chaque worker possède sa propre fenêtre : cette borne protège le
    processus, tandis qu'un reverse proxy peut imposer une limite globale.

    Le téléversement de livrable est exclu de la borne générale : son endpoint
    authentifie d'abord le worker puis consomme le multipart en flux avec ses
    propres limites. Les deux routes d'import de skill ont une borne dédiée.
    """

    def __init__(
        self,
        app,
        *,
        max_body_bytes: int = WEBHOOK_MAX_BODY_BYTES,
        skill_source_max_body_bytes: int = SKILL_SOURCE_MAX_BODY_BYTES,
        max_requests: int = WEBHOOK_RATE_LIMIT_REQUESTS,
        window_seconds: float = WEBHOOK_RATE_LIMIT_WINDOW_SECONDS,
        max_tracked_clients: int = _MAX_TRACKED_CLIENTS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.skill_source_max_body_bytes = skill_source_max_body_bytes
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_clients = max(1, max_tracked_clients)
        self._clock = clock
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._overflow_requests: deque[float] = deque()

    async def _respond(self, scope, receive, send, status: int, detail: str) -> None:
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)

    @staticmethod
    def _purge_expired(requests: deque[float], cutoff: float) -> None:
        while requests and requests[0] <= cutoff:
            requests.popleft()

    def _client_key(self, scope: dict) -> str:
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    def _request_bucket(self, scope: dict, cutoff: float) -> tuple[deque[float], str | None]:
        key = self._client_key(scope)
        existing = self._requests.get(key)
        if existing is not None:
            self._purge_expired(existing, cutoff)
            self._requests.move_to_end(key)
            return existing, key

        # L'ordre du dictionnaire est un LRU. Si le client le moins récent est
        # expiré, tous les seaux vides consécutifs peuvent être oubliés sans
        # parcourir les 10 000 entrées à chaque nouvelle adresse.
        while len(self._requests) >= self.max_tracked_clients:
            oldest_key, oldest = next(iter(self._requests.items()))
            self._purge_expired(oldest, cutoff)
            if oldest:
                break
            del self._requests[oldest_key]

        if len(self._requests) < self.max_tracked_clients:
            requests: deque[float] = deque()
            self._requests[key] = requests
            return requests, key

        # Les adresses excédentaires partagent une fenêtre bornée, sans occuper
        # durablement le cache. Dès qu'un seau LRU expire, elles redeviennent
        # individuellement suivies.
        self._purge_expired(self._overflow_requests, cutoff)
        return self._overflow_requests, None

    def _rate_allowed(self, scope: dict) -> bool:
        now = self._clock()
        cutoff = now - self.window_seconds
        requests, key = self._request_bucket(scope, cutoff)
        if len(requests) >= self.max_requests:
            return False
        requests.append(now)
        if key is not None:
            self._requests.move_to_end(key)
        return True

    def _body_limit(self, scope: dict) -> int | None:
        if scope.get("type") != "http":
            return None
        if _is_streamed_artifact_upload(scope):
            return None
        if _is_skill_source_request(scope):
            return self.skill_source_max_body_bytes
        return self.max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        body_limit = self._body_limit(scope)
        if body_limit is None:
            await self.app(scope, receive, send)
            return

        content_lengths = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if content_lengths:
            # ``int`` accepte des formes qui ne font pas partie de la grammaire
            # HTTP ``Content-Length = 1*DIGIT`` (``+1``, espaces, underscores).
            # Valider les octets bruts empêche deux intermédiaires d'interpréter
            # différemment une longueur pourtant acceptée par cette garde.
            if any(
                not value
                or any(byte < ord("0") or byte > ord("9") for byte in value)
                for value in content_lengths
            ):
                await self._respond(
                    scope, receive, send, 400, "Content-Length invalide"
                )
                return
            try:
                parsed_lengths = {int(value) for value in content_lengths}
            except ValueError:
                await self._respond(
                    scope, receive, send, 400, "Content-Length invalide"
                )
                return
            if len(parsed_lengths) != 1 or next(iter(parsed_lengths)) < 0:
                await self._respond(
                    scope, receive, send, 400, "Content-Length invalide"
                )
                return
            if next(iter(parsed_lengths)) > body_limit:
                await self._respond(
                    scope,
                    receive,
                    send,
                    413,
                    "Le corps de la requête dépasse la limite autorisée",
                )
                return

        if _is_webhook_trigger(scope) and not self._rate_allowed(scope):
            response = JSONResponse(
                {"detail": "Trop de déclenchements webhook"},
                status_code=429,
                headers={"Retry-After": str(int(self.window_seconds))},
            )
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._respond(
                scope,
                receive,
                send,
                413,
                "Le corps de la requête dépasse la limite autorisée",
            )


# Compatibilité des imports internes créés pendant le développement du Lot F.
WebhookIngressGuardMiddleware = RequestIngressGuardMiddleware
