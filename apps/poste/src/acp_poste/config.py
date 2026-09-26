"""Origine de service du poste : ``normalize_service_origin`` (repris de P0).

Étape P5 : la configuration du poste vient de ``poste.toml`` (:mod:`politique`) ; ``PosteConfig.from_env`` et les
réglages ``ACP_WORKER_*`` ont disparu. Cette fonction canonicalise une origine sans chemin, sans ``userinfo``, sans
requête ni fragment. Elle admet ``http://`` sur la boucle locale ; :mod:`politique` exige en plus HTTPS **partout**
pour l'origine de Hermes (cahier P5 § 7.3).
"""

import ipaddress
import re
from urllib.parse import urlsplit



_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class PosteConfigurationError(ValueError):
    """Configuration refusée avant toute exécution."""


def normalize_service_origin(value: str, *, setting: str) -> str:
    """Valide et canonicalise une origine de service sans chemin ni secrets."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise PosteConfigurationError(f"{setting} doit être une URL absolue sans espaces")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PosteConfigurationError(f"{setting} contient une URL invalide") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise PosteConfigurationError(
            f"{setting} doit utiliser une origine HTTP(S) absolue"
        )
    if parsed.username is not None or parsed.password is not None:
        raise PosteConfigurationError(f"{setting} ne doit pas contenir de userinfo")
    if "?" in value or "#" in value:
        raise PosteConfigurationError(
            f"{setting} ne doit pas contenir de query ni de fragment"
        )
    if parsed.path not in {"", "/"}:
        raise PosteConfigurationError(f"{setting} doit être une origine sans chemin")

    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname:
        raise PosteConfigurationError(f"{setting} doit contenir un hôte")
    if port == 0:
        raise PosteConfigurationError(f"{setting} doit utiliser un port valide")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    is_loopback = hostname == "localhost" or bool(address and address.is_loopback)
    if scheme != "https" and not is_loopback:
        raise PosteConfigurationError(
            f"{setting} doit utiliser HTTPS hors d'une adresse loopback"
        )

    if address and address.version == 6:
        canonical_host = f"[{address.compressed}]"
    elif address:
        canonical_host = address.compressed
    else:
        try:
            canonical_host = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise PosteConfigurationError(f"{setting} contient un hôte invalide") from exc
        if len(canonical_host) > 253 or any(
            _DNS_LABEL.fullmatch(label) is None for label in canonical_host.split(".")
        ):
            raise PosteConfigurationError(f"{setting} contient un hôte invalide")
    default_port = 80 if scheme == "http" else 443
    authority = (
        canonical_host
        if port in {None, default_port}
        else f"{canonical_host}:{port}"
    )
    return f"{scheme}://{authority}"
