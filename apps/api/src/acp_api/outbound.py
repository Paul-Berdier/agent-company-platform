"""Politique de sortie réseau (anti-SSRF) et client HTTP épinglé.

Toute requête sortante initiée par l'API (probe MCP HTTP, téléchargement GitHub)
passe par ``PinnedHttpClient`` : URL validée, toutes les adresses résolues
contrôlées (une seule adresse bloquée suffit à refuser), connexion vers l'adresse
IP validée avec l'en-tête ``Host`` et le SNI de l'hôte d'origine, redirections
revalidées de bout en bout, corps de réponse borné.

Une adresse privée n'est jointe que si elle (ou le nom d'hôte exact qui la résout)
figure dans ``ACP_OUTBOUND_PRIVATE_ALLOWLIST`` (ou, pour le bouclage en http, si
``ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP=1``) ; l'appelant est alors prévenu via
``on_private_allowlist_used`` pour journaliser l'usage (``outbound.private_allowlist_used``).

Une redirection vers une autre origine (schéma, hôte ou port différent) abandonne les
en-têtes de l'appelant — ``Authorization``, ``Cookie``, en-têtes secrets… — et ne conserve
que les en-têtes de négociation (``CROSS_ORIGIN_SAFE_HEADERS``) : un secret injecté pour
l'appel autorisé n'est jamais réémis vers un hôte choisi par le serveur distant.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

ALLOWLIST_ENV = "ACP_OUTBOUND_PRIVATE_ALLOWLIST"
LOOPBACK_HTTP_ENV = "ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP"

ERROR_CODES = frozenset(
    {
        "invalid_url",
        "scheme_forbidden",
        "userinfo_forbidden",
        "host_blocked",
        "resolution_failed",
        "redirect_blocked",
        "too_many_redirects",
        "response_too_large",
    }
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
DEFAULT_PORTS = {"http": 80, "https": 443}

# Seuls en-têtes de l'appelant réémis après une redirection vers une autre origine.
CROSS_ORIGIN_SAFE_HEADERS = frozenset(
    {"accept", "accept-encoding", "accept-language", "content-type", "user-agent"}
)
# En-têtes qui décrivent le corps *encodé* : périmés une fois le flux décodé et lu en entier.
_ENCODED_BODY_HEADERS = frozenset({b"content-encoding", b"content-length", b"transfer-encoding"})

CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")
ULA_NETWORK = ipaddress.ip_network("fc00::/7")
LINK_LOCAL_V6_NETWORK = ipaddress.ip_network("fe80::/10")
SIX_TO_FOUR_NETWORK = ipaddress.ip_network("2002::/16")
TEREDO_NETWORK = ipaddress.ip_network("2001::/32")
NAT64_NETWORK = ipaddress.ip_network("64:ff9b::/96")

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,62})(?:\.[a-z0-9](?:[a-z0-9-]{0,62}))*$"
)

_REASON_LABELS = {
    "loopback": "une adresse de bouclage",
    "private": "une adresse privée",
    "link_local": "une adresse lien-local (métadonnées cloud incluses)",
    "multicast": "une adresse multicast",
    "reserved": "une adresse réservée",
    "unspecified": "une adresse non spécifiée",
    "cgnat": "une adresse CGNAT (100.64.0.0/10)",
    "ula": "une adresse IPv6 locale unique (fc00::/7)",
    "teredo": "une adresse Teredo non décodable",
    "not_global": "une adresse non routable publiquement",
}


class OutboundPolicyError(ValueError):
    """Refus de la politique de sortie ; ``code`` est stable, le message est en français."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"code d'erreur de politique inconnu : {code!r}")
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedTarget:
    scheme: str
    host: str  # nom IDNA (ASCII, minuscules) ou adresse IP littérale sans crochets
    port: int
    path_query: str


def _describe(reason: str) -> str:
    return _REASON_LABELS.get(reason, reason)


def _embedded_ipv4(ip: ipaddress.IPv6Address, network: IPNetwork) -> ipaddress.IPv4Address:
    """IPv4 embarquée dans les 32 derniers bits (NAT64)."""

    return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)


def blocked_address_reason(ip: IPAddress) -> str | None:
    """Raison brute du blocage d'une adresse, sans tenir compte d'une allowlist.

    Les formes IPv6 qui embarquent une IPv4 (mappée, 6to4, Teredo, NAT64) sont
    évaluées via l'IPv4 embarquée.
    """

    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return blocked_address_reason(mapped)
        if ip in SIX_TO_FOUR_NETWORK:
            embedded = ip.sixtofour
            return blocked_address_reason(embedded) if embedded is not None else "reserved"
        if ip in TEREDO_NETWORK:
            teredo = ip.teredo
            if teredo is None:
                return "teredo"
            server, client = teredo
            return blocked_address_reason(server) or blocked_address_reason(client)
        if ip in NAT64_NETWORK:
            return blocked_address_reason(_embedded_ipv4(ip, NAT64_NETWORK))
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_multicast:
        return "multicast"
    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT_NETWORK:
        return "cgnat"
    if isinstance(ip, ipaddress.IPv6Address):
        if ip in ULA_NETWORK:
            return "ula"
        if ip in LINK_LOCAL_V6_NETWORK:
            return "link_local"
    if ip.is_private:
        return "private"
    if ip.is_reserved:
        return "reserved"
    if not ip.is_global:
        return "not_global"
    return None


def _normalize_hostname(value: str) -> str | None:
    """Nom d'hôte IDNA en minuscules, sans point final ; ``None`` si invalide."""

    candidate = value.strip().rstrip(".").lower()
    if not candidate:
        return None
    try:
        ascii_name = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    return ascii_name if _HOSTNAME_RE.fullmatch(ascii_name) else None


def _parse_ip(value: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


class OutboundPolicy:
    """Règles de sortie : schémas, hôtes, adresses et allowlist privée explicite."""

    def __init__(
        self, allowlist: Iterable[str] = (), allow_loopback_http: bool = False
    ) -> None:
        self.allowlist: list[str] = []
        self._networks: list[IPNetwork] = []
        self._hosts: set[str] = set()
        for raw in allowlist:
            entry = raw.strip()
            if not entry:
                continue
            try:
                network = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                host = _normalize_hostname(entry)
                if host is None:
                    raise ValueError(
                        f"{ALLOWLIST_ENV} : entrée invalide {entry!r} "
                        "(CIDR IPv4/IPv6 ou nom d'hôte exact attendu)"
                    ) from None
                self._hosts.add(host)
                self.allowlist.append(host)
            else:
                self._networks.append(network)
                self.allowlist.append(str(network))
        self.allow_loopback_http = bool(allow_loopback_http)

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] = os.environ) -> "OutboundPolicy":
        entries = environ.get(ALLOWLIST_ENV, "").split(",")
        # Une variable vide (ligne « VAR= » d'un .env) vaut le défaut « 0 ».
        flag = environ.get(LOOPBACK_HTTP_ENV, "").strip() or "0"
        if flag not in {"0", "1"}:
            raise ValueError(f"{LOOPBACK_HTTP_ENV} : valeur {flag!r} refusée (0 ou 1 attendu)")
        return cls(entries, flag == "1")

    # --- allowlist ---------------------------------------------------------------

    def is_host_allowlisted(self, host: str) -> bool:
        normalized = _normalize_hostname(host)
        return normalized is not None and normalized in self._hosts

    def is_address_allowlisted(self, ip: IPAddress) -> bool:
        return any(ip in network for network in self._networks if network.version == ip.version)

    # --- contrôles -----------------------------------------------------------------

    def is_blocked_address(self, ip: IPAddress) -> str | None:
        """Raison du blocage, ou ``None`` si l'adresse est publique ou explicitement permise."""

        if self.is_address_allowlisted(ip):
            return None
        if self.allow_loopback_http and ip.is_loopback:
            return None
        return blocked_address_reason(ip)

    def _is_loopback_host(self, host: str, literal: IPAddress | None) -> bool:
        if literal is not None:
            return literal.is_loopback
        return host == "localhost" or host.endswith(".localhost")

    def validate_url(self, url: str) -> ParsedTarget:
        if not isinstance(url, str) or not url.strip():
            raise OutboundPolicyError("invalid_url", "URL vide : une URL absolue est attendue.")
        raw = url.strip()
        if "#" in raw:
            raise OutboundPolicyError("invalid_url", "URL refusée : un fragment (#) n'est pas accepté.")
        try:
            parts = urlsplit(raw)
        except ValueError as exc:
            raise OutboundPolicyError("invalid_url", f"URL illisible : {exc}") from exc
        scheme = parts.scheme.lower()
        if not scheme:
            raise OutboundPolicyError(
                "invalid_url", "URL absolue attendue (par exemple https://hote.example/chemin)."
            )
        if scheme not in DEFAULT_PORTS:
            raise OutboundPolicyError(
                "scheme_forbidden", f"schéma « {scheme} » refusé : seuls http et https sont autorisés."
            )
        if not parts.netloc:
            raise OutboundPolicyError(
                "invalid_url", "URL absolue attendue (par exemple https://hote.example/chemin)."
            )
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            raise OutboundPolicyError(
                "userinfo_forbidden",
                "URL refusée : les identifiants dans l'URL (user:mot-de-passe@hôte) ne sont pas acceptés ; "
                "utilisez un en-tête référençant un secret.",
            )
        try:
            hostname = parts.hostname
            port = parts.port
        except ValueError as exc:
            raise OutboundPolicyError("invalid_url", f"port invalide dans l'URL : {exc}") from exc
        if not hostname:
            raise OutboundPolicyError("invalid_url", "URL refusée : hôte manquant.")
        literal = _parse_ip(hostname)
        if literal is not None:
            host = str(literal)
        else:
            normalized = _normalize_hostname(hostname)
            if normalized is None:
                raise OutboundPolicyError("invalid_url", f"nom d'hôte invalide : {hostname!r}.")
            host = normalized
        port = port or DEFAULT_PORTS[scheme]
        if scheme == "http":
            permitted = (
                self.is_host_allowlisted(host)
                or (literal is not None and self.is_address_allowlisted(literal))
                or (self.allow_loopback_http and self._is_loopback_host(host, literal))
            )
            if not permitted:
                raise OutboundPolicyError(
                    "scheme_forbidden",
                    f"http refusé pour « {host} » : utilisez https, ajoutez l'hôte à "
                    f"{ALLOWLIST_ENV}, ou activez {LOOPBACK_HTTP_ENV}=1 pour une cible de bouclage.",
                )
        path = parts.path or "/"
        path_query = f"{path}?{parts.query}" if parts.query else path
        return ParsedTarget(scheme=scheme, host=host, port=port, path_query=path_query)

    def resolve(
        self, host: str, resolver: Callable[..., object] = socket.getaddrinfo
    ) -> list[IPAddress]:
        """Résout ``host`` et contrôle **toutes** les adresses : une seule bloquée suffit à refuser.

        Un nom d'hôte exact présent dans l'allowlist est exempté du contrôle d'adresse (ses
        adresses privées sont joignables) ; l'exemption vaut pour ce nom uniquement, jamais pour
        l'adresse elle-même. ``PinnedHttpClient`` signale l'usage via ``on_private_allowlist_used``.
        """

        literal = _parse_ip(host)
        if literal is not None:
            candidates: list[IPAddress] = [literal]
        else:
            try:
                infos = resolver(host, None)
            except OSError as exc:
                raise OutboundPolicyError(
                    "resolution_failed", f"résolution DNS impossible pour « {host} » : {exc}"
                ) from exc
            candidates = []
            for info in infos or ():
                sockaddr = info[4] if isinstance(info, tuple) and len(info) >= 5 else None
                address = sockaddr[0] if isinstance(sockaddr, tuple) and sockaddr else None
                if not isinstance(address, str) or not address:
                    continue
                parsed = _parse_ip(address.split("%", 1)[0])
                if parsed is not None and parsed not in candidates:
                    candidates.append(parsed)
            if not candidates:
                raise OutboundPolicyError(
                    "resolution_failed", f"aucune adresse IP obtenue pour « {host} »."
                )
            if self.is_host_allowlisted(host):
                return candidates
        for ip in candidates:
            reason = self.is_blocked_address(ip)
            if reason is not None:
                raise OutboundPolicyError(
                    "host_blocked",
                    f"hôte « {host} » refusé : l'adresse {ip} est {_describe(reason)} "
                    "(toutes les adresses résolues doivent être publiques ou allowlistées).",
                )
        return candidates


def _host_literal(host: str) -> str:
    """Forme de l'hôte utilisable dans une URL ou un en-tête Host (crochets pour IPv6)."""

    return f"[{host}]" if ":" in host else host


def _host_header(target: ParsedTarget) -> str:
    literal = _host_literal(target.host)
    if target.port == DEFAULT_PORTS[target.scheme]:
        return literal
    return f"{literal}:{target.port}"


def _logical_url(target: ParsedTarget) -> str:
    return f"{target.scheme}://{_host_header(target)}{target.path_query}"


def _pinned_url(target: ParsedTarget, address: IPAddress) -> str:
    return f"{target.scheme}://{_host_literal(str(address))}:{target.port}{target.path_query}"


def _origin(target: ParsedTarget) -> tuple[str, str, int]:
    return (target.scheme, target.host, target.port)


def _cross_origin_headers(headers: httpx.Headers) -> httpx.Headers:
    """En-têtes conservés vers une autre origine : uniquement ``CROSS_ORIGIN_SAFE_HEADERS``."""

    return httpx.Headers(
        [(name, value) for name, value in headers.raw if name.decode("ascii").lower() in CROSS_ORIGIN_SAFE_HEADERS]
    )


class PinnedHttpClient:
    """Client HTTP synchrone qui applique la politique à chaque saut, redirections comprises."""

    def __init__(
        self,
        policy: OutboundPolicy,
        resolver: Callable[..., object] = socket.getaddrinfo,
        transport: httpx.BaseTransport | None = None,
        max_redirects: int = 3,
        max_body_bytes: int = 2_000_000,
        timeout: float = 15.0,
        on_private_allowlist_used: Callable[[str, str], None] | None = None,
    ) -> None:
        if max_redirects < 0:
            raise ValueError("max_redirects doit être positif ou nul")
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes doit être strictement positif")
        self.policy = policy
        self.resolver = resolver
        self.transport = transport
        self.max_redirects = max_redirects
        self.max_body_bytes = max_body_bytes
        self.timeout = timeout
        self.on_private_allowlist_used = on_private_allowlist_used

    def _pin(self, target: ParsedTarget) -> IPAddress:
        """Résout, contrôle et choisit l'adresse à contacter ; signale un usage d'allowlist."""

        address = self.policy.resolve(target.host, self.resolver)[0]
        if self.on_private_allowlist_used is not None and blocked_address_reason(address) is not None:
            self.on_private_allowlist_used(target.host, str(address))
        return address

    def _read_bounded(self, response: httpx.Response) -> httpx.Response:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_body_bytes:
            raise OutboundPolicyError(
                "response_too_large",
                f"réponse refusée : {declared} octets annoncés, limite {self.max_body_bytes}.",
            )
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > self.max_body_bytes:
                raise OutboundPolicyError(
                    "response_too_large",
                    f"réponse refusée : corps supérieur à {self.max_body_bytes} octets.",
                )
        # ``iter_bytes`` a déjà décodé le flux : les en-têtes Content-Encoding / Content-Length /
        # Transfer-Encoding décrivent le corps encodé et provoqueraient un second décodage.
        headers = httpx.Headers(
            [(name, value) for name, value in response.headers.raw if name.lower() not in _ENCODED_BODY_HEADERS]
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            content=bytes(body),
            request=response.request,
            extensions=dict(response.extensions),
        )

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        method = method.upper()
        body = content
        hop_headers = httpx.Headers(dict(headers or {}))
        target = self.policy.validate_url(url)
        address = self._pin(target)
        with httpx.Client(
            transport=self.transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(self.timeout),
        ) as client:
            for hop in range(self.max_redirects + 1):
                request_headers = httpx.Headers(hop_headers)
                request_headers["Host"] = _host_header(target)
                request = client.build_request(
                    method,
                    _pinned_url(target, address),
                    headers=request_headers,
                    content=body,
                    extensions={"sni_hostname": target.host},
                )
                response = client.send(request, stream=True)
                try:
                    if response.status_code not in REDIRECT_STATUSES:
                        return self._read_bounded(response)
                    if hop >= self.max_redirects:
                        raise OutboundPolicyError(
                            "too_many_redirects",
                            f"plus de {self.max_redirects} redirections : requête abandonnée.",
                        )
                    location = response.headers.get("location")
                    if not location:
                        raise OutboundPolicyError(
                            "redirect_blocked",
                            f"redirection {response.status_code} sans en-tête Location : refusée.",
                        )
                    next_url = urljoin(_logical_url(target), location)
                    try:
                        next_target = self.policy.validate_url(next_url)
                        next_address = self._pin(next_target)
                    except OutboundPolicyError as exc:
                        raise OutboundPolicyError(
                            "redirect_blocked",
                            f"redirection vers « {next_url} » refusée ({exc.code}) : {exc}",
                        ) from exc
                    if _origin(next_target) != _origin(target):
                        # Changement d'origine : les identifiants et en-têtes de l'appelant sont
                        # abandonnés définitivement (revenir sur l'origine initiale ne les restaure pas).
                        hop_headers = _cross_origin_headers(hop_headers)
                    target, address = next_target, next_address
                    if response.status_code == 303 or (
                        response.status_code in (301, 302) and method == "POST"
                    ):
                        method = "GET"
                        body = None
                finally:
                    response.close()
        raise OutboundPolicyError(  # pragma: no cover - garde-fou, la boucle retourne ou lève
            "too_many_redirects", "redirections épuisées."
        )
