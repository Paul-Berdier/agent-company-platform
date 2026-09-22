"""Validation commune des origines qui reçoivent des secrets inter-services."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class ServiceOriginError(ValueError):
    """Une URL de service pourrait détourner ou exposer un credential."""


def _internal_hosts(value: str) -> set[str]:
    """Liste exacte de noms privés ; aucun domaine public ni motif générique."""
    hosts = set()
    for entry in value.split(","):
        host = entry.strip().casefold().rstrip(".")
        if not host:
            continue
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            private = (
                ("." not in host or host.endswith(".railway.internal"))
                and len(host) <= 253
                and all(_DNS_LABEL.fullmatch(label) for label in host.split("."))
            )
        else:
            private = any(address in network for network in (
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
                ipaddress.ip_network("fc00::/7"),
            ))
        if not private:
            raise ServiceOriginError(
                "ACP_INTERNAL_HTTP_HOSTS exige des hôtes privés exacts, sans URL ni joker"
            )
        hosts.add(host)
    return hosts


def normalize_service_origin(
    value: str, *, setting: str, internal_http_hosts: str = ""
) -> str:
    """Retourne une origine HTTP(S) canonique, sûre pour porter un secret.

    HTTP est limité au loopback et à la liste explicite d'hôtes privés fournie
    par les clients internes du serveur. Les chemins, userinfo, queries et
    fragments sont interdits afin que les clients n'envoient jamais leur Bearer à
    une destination ambiguë ou à une URL construite avec des données d'autorité.
    """

    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ServiceOriginError(f"{setting} doit être une URL absolue sans espaces")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ServiceOriginError(f"{setting} contient une URL invalide") from exc

    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise ServiceOriginError(
            f"{setting} doit utiliser une origine HTTP(S) absolue"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ServiceOriginError(f"{setting} ne doit pas contenir de userinfo")
    if parsed.query or parsed.fragment or "?" in value or "#" in value:
        raise ServiceOriginError(
            f"{setting} ne doit pas contenir de query ni de fragment"
        )
    if parsed.path not in {"", "/"}:
        raise ServiceOriginError(f"{setting} doit être une origine sans chemin")
    if port == 0:
        raise ServiceOriginError(f"{setting} doit utiliser un port valide")

    hostname = parsed.hostname.rstrip(".").casefold()
    if not hostname:
        raise ServiceOriginError(f"{setting} doit contenir un hôte")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None

    if scheme == "http" and not (
        hostname == "localhost" or bool(address and address.is_loopback)
        or hostname in _internal_hosts(internal_http_hosts)
    ):
        raise ServiceOriginError(f"{setting} doit utiliser HTTPS hors loopback")

    if address is not None:
        canonical_host = address.compressed.casefold()
        if address.version == 6:
            canonical_host = f"[{canonical_host}]"
    else:
        try:
            canonical_host = hostname.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ServiceOriginError(f"{setting} contient un hôte invalide") from exc
        if len(canonical_host) > 253 or any(
            _DNS_LABEL.fullmatch(label) is None for label in canonical_host.split(".")
        ):
            raise ServiceOriginError(f"{setting} contient un hôte invalide")

    default_port = 80 if scheme == "http" else 443
    authority = (
        canonical_host if port in {None, default_port} else f"{canonical_host}:{port}"
    )
    return f"{scheme}://{authority}"
