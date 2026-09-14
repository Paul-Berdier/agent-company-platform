"""Jetons signés des liens de téléchargement et d'aperçu de livrables.

Un lien de partage n'ouvre jamais un projet : le jeton est lié à **un** artefact et
à **un** utilisateur, il expire, et la ligne ``artifact_links`` qui le porte permet
de le révoquer. L'identifiant d'utilisateur entre dans le message signé sans figurer
dans le jeton : le serveur retrouve le titulaire par l'empreinte du jeton
(``token_hash``) puis exige que la signature corresponde à ce couple.

Les clés viennent de ``ACP_ARTIFACT_SIGNING_KEYS`` (liste séparée par des virgules,
la première signe, les suivantes vérifient encore : rotation sans interruption).
Sans clé, les liens signés sont indisponibles et la route répond explicitement
« non configuré » — le téléchargement authentifié par session reste possible.

Génération d'une clé : ``python -m acp_api.signing generate-key``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

ARTIFACT_SIGNING_KEYS_ENV = "ACP_ARTIFACT_SIGNING_KEYS"
LEGACY_TOKEN_VERSION = "v1"
TOKEN_VERSION = "v2"
TOKEN_NONCE_BYTES = 18
TOKEN_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}")
MIN_SIGNING_KEY_CHARS = 32
KEY_ID_LENGTH = 12
IDENTIFIER_MAX_CHARS = 64
TOKEN_MAX_CHARS = 512

DEFAULT_LINK_TTL_SECONDS = 300
MAX_LINK_TTL_SECONDS = 900

NOT_CONFIGURED_MESSAGE = (
    "Signature des liens de livrables non configurée : définissez "
    f"{ARTIFACT_SIGNING_KEYS_ENV} avec au moins une clé de "
    f"{MIN_SIGNING_KEY_CHARS} caractères (générez-en une avec "
    "« python -m acp_api.signing generate-key »). Le téléchargement authentifié "
    "par session reste disponible."
)


class ArtifactSigningNotConfigured(RuntimeError):
    """Aucune clé de signature exploitable : les liens signés sont indisponibles."""


class ArtifactTokenInvalid(RuntimeError):
    """Le jeton est illisible, altéré, ou lié à un autre artefact ou utilisateur."""


class ArtifactTokenExpired(ArtifactTokenInvalid):
    """Le jeton était authentique mais sa validité est passée."""


@dataclass(frozen=True, slots=True)
class ArtifactTokenClaims:
    """Contenu vérifié d'un jeton ; ``key_id`` sert au suivi de rotation."""

    artifact_id: str
    user_id: str
    expires_at: datetime
    key_id: str
    purpose: Literal["download", "preview"]


def generate_signing_key() -> str:
    """Nouvelle clé aléatoire, à placer dans ``ACP_ARTIFACT_SIGNING_KEYS``."""

    return secrets.token_urlsafe(48)


def signing_key_id(key: str) -> str:
    """Identifiant public et stable d'une clé (jamais la clé elle-même)."""

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:KEY_ID_LENGTH]


def load_signing_keys(environ: Mapping[str, str]) -> list[str]:
    """Lit les clés de signature (primaire en premier) ou refuse explicitement."""

    raw = environ.get(ARTIFACT_SIGNING_KEYS_ENV, "")
    keys = [part.strip() for part in raw.split(",")]
    keys = [key for key in keys if key]
    if not keys:
        raise ArtifactSigningNotConfigured(NOT_CONFIGURED_MESSAGE)
    for position, key in enumerate(keys, start=1):
        if len(key) < MIN_SIGNING_KEY_CHARS:
            raise ArtifactSigningNotConfigured(
                f"{ARTIFACT_SIGNING_KEYS_ENV} : la clé n°{position} fait moins de "
                f"{MIN_SIGNING_KEY_CHARS} caractères ; une clé aussi courte ne "
                "protège pas un lien de téléchargement."
            )
    return keys


def token_hash(token: str) -> str:
    """Empreinte stockée dans ``artifact_links`` ; le jeton n'est jamais conservé.

    La valeur vient d'une requête : une chaîne que l'UTF-8 ne peut pas encoder — un
    substitut isolé, par exemple — doit produire une empreinte qui ne correspondra à
    aucune ligne, jamais une exception qui remonterait en erreur serveur.
    """

    return hashlib.sha256(token.encode("utf-8", errors="surrogatepass")).hexdigest()


def _checked_identifier(value: str, label: str) -> str:
    if not value:
        raise ValueError(f"{label} est obligatoire pour signer un lien.")
    if "." in value:
        raise ValueError(
            f"{label} ne peut pas contenir « . » : ce caractère sépare les champs du jeton."
        )
    if len(value) > IDENTIFIER_MAX_CHARS:
        raise ValueError(
            f"{label} dépasse {IDENTIFIER_MAX_CHARS} caractères : identifiant inattendu."
        )
    return value


def _signature(
    artifact_id: str,
    user_id: str,
    expires_at: int,
    purpose: Literal["download", "preview"],
    nonce: str,
    key: str,
) -> str:
    message = (
        f"{TOKEN_VERSION}.{artifact_id}.{user_id}.{expires_at}.{purpose}.{nonce}"
    ).encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _legacy_signature(artifact_id: str, user_id: str, expires_at: int, key: str) -> str:
    """Signature v1 conservée uniquement pour lire les liens déjà distribués."""

    message = (
        f"{LEGACY_TOKEN_VERSION}.{artifact_id}.{user_id}.{expires_at}"
    ).encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def sign_artifact_token(
    artifact_id: str,
    user_id: str,
    expires_at: datetime,
    key: str,
    *,
    purpose: Literal["download", "preview"] = "download",
) -> str:
    """Signe un lien ``v2.<artifact_id>.<exp>.<purpose>.<nonce>.<sig>``.

    Le nonce empêche deux liens créés la même seconde pour le même couple
    artefact/utilisateur d'entrer en collision dans la colonne ``token_hash`` unique.
    """

    if not key:
        raise ArtifactSigningNotConfigured(NOT_CONFIGURED_MESSAGE)
    if purpose not in ("download", "preview"):
        raise ValueError("L'usage du lien doit être « download » ou « preview ».")
    artifact_id = _checked_identifier(artifact_id, "L'identifiant d'artefact")
    user_id = _checked_identifier(user_id, "L'identifiant d'utilisateur")
    if expires_at.tzinfo is None:
        raise ValueError(
            "L'expiration d'un lien doit être une date avec fuseau horaire (UTC)."
        )
    expiry = int(expires_at.timestamp())
    nonce = secrets.token_urlsafe(TOKEN_NONCE_BYTES)
    signature = _signature(artifact_id, user_id, expiry, purpose, nonce, key)
    return f"{TOKEN_VERSION}.{artifact_id}.{expiry}.{purpose}.{nonce}.{signature}"


def verify_artifact_token(
    token: str,
    keys: Sequence[str],
    *,
    artifact_id: str,
    user_id: str,
    now: datetime | None = None,
) -> ArtifactTokenClaims:
    """Vérifie un jeton pour un couple artefact/utilisateur donné.

    L'expiration n'est examinée qu'après une signature valide : un jeton forgé est
    toujours rapporté comme invalide, jamais comme « expiré ».
    """

    usable = [key for key in keys if key]
    if not usable:
        raise ArtifactSigningNotConfigured(NOT_CONFIGURED_MESSAGE)
    if len(token or "") > TOKEN_MAX_CHARS:
        # Refus avant toute empreinte : un jeton absurde ne doit pas coûter un
        # HMAC par clé encore en rotation.
        raise ArtifactTokenInvalid("Lien invalide : jeton hors format.")
    parts = (token or "").split(".")
    nonce: str | None
    if len(parts) == 6 and parts[0] == TOKEN_VERSION:
        version, token_artifact_id, raw_expiry, raw_purpose, nonce, signature = parts
        if raw_purpose not in ("download", "preview"):
            raise ArtifactTokenInvalid("Lien invalide : usage hors format.")
        purpose: Literal["download", "preview"] = raw_purpose
        if TOKEN_NONCE_PATTERN.fullmatch(nonce) is None:
            raise ArtifactTokenInvalid("Lien invalide : nonce hors format.")
    elif len(parts) == 4 and parts[0] == LEGACY_TOKEN_VERSION:
        version, token_artifact_id, raw_expiry, signature = parts
        nonce = None
        purpose = "download"
    else:
        raise ArtifactTokenInvalid("Lien invalide : version ou format inconnu.")
    if not token_artifact_id or not signature:
        raise ArtifactTokenInvalid("Lien invalide : jeton incomplet.")
    try:
        candidate = signature.encode("ascii")
    except UnicodeEncodeError as exc:
        # ``hmac.compare_digest`` lève un ``TypeError`` sur deux ``str`` dont l'un
        # sort de l'ASCII. La signature est du base64url : tout autre caractère
        # est un jeton hors format, refusé ici plutôt qu'en plantage — « %C3%A9 »
        # dans la chaîne de requête suffirait sinon à provoquer un 500.
        raise ArtifactTokenInvalid("Lien invalide : signature hors format.") from exc
    try:
        expiry = int(raw_expiry)
    except ValueError as exc:
        raise ArtifactTokenInvalid("Lien invalide : expiration illisible.") from exc
    if token_artifact_id != artifact_id:
        raise ArtifactTokenInvalid("Lien invalide : jeton lié à un autre livrable.")

    matched: str | None = None
    for key in usable:
        expected_signature = (
            _signature(artifact_id, user_id, expiry, purpose, nonce, key)
            if version == TOKEN_VERSION and nonce is not None
            else _legacy_signature(artifact_id, user_id, expiry, key)
        )
        expected = expected_signature.encode("ascii")
        if hmac.compare_digest(expected, candidate):
            matched = key
    if matched is None:
        raise ArtifactTokenInvalid(
            "Lien invalide : signature inconnue, altérée, ou jeton destiné à un "
            "autre utilisateur."
        )
    expires_at = datetime.fromtimestamp(expiry, tz=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("La date de vérification doit porter un fuseau horaire (UTC).")
    if moment >= expires_at:
        raise ArtifactTokenExpired("Lien expiré : demandez-en un nouveau.")
    return ArtifactTokenClaims(
        artifact_id=artifact_id,
        user_id=user_id,
        expires_at=expires_at,
        key_id=signing_key_id(matched),
        purpose=purpose,
    )


def _main(argv: Sequence[str]) -> int:  # pragma: no cover - utilitaire de console
    if len(argv) != 1 or argv[0] != "generate-key":
        print("Usage : python -m acp_api.signing generate-key", file=sys.stderr)
        return 2
    print(generate_signing_key())
    return 0


if __name__ == "__main__":  # pragma: no cover - utilitaire de console
    raise SystemExit(_main(sys.argv[1:]))
