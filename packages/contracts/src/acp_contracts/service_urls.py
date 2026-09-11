"""Validation commune des origines qui reçoivent des secrets inter-services."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class ServiceOriginError(ValueError):
    """Une URL de service pourrait détourner ou exposer un credential."""


def normalize_service_origin(value: str, *, setting: str) -> str:
    """Retourne une origine HTTP(S) canonique, sûre pour porter un secret.

    HTTP est volontairement limité au loopback. Les chemins, userinfo, queries et
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
