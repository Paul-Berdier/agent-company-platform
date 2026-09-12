"""Coffre de secrets : chiffrement Fernet au repos avec rotation de clés.

``ACP_SECRETS_KEYS`` contient des clés Fernet séparées par des virgules. La
première est la clé primaire (chiffrement) ; les suivantes ne servent qu'au
déchiffrement, ce qui permet une rotation sans interruption.

Aucune valeur en clair n'est journalisée. ``decrypt`` n'est appelé que par le
probe HTTP (en-têtes) et par le claim d'un probe stdio par un worker authentifié
(variables d'environnement), jamais par une route utilisateur.

Usage en ligne de commande : ``python -m acp_api.secrets_vault generate-key``.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping, Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from acp_contracts import SecretsStatus

SECRETS_KEYS_ENV = "ACP_SECRETS_KEYS"
KEY_ID_LENGTH = 12

NOT_CONFIGURED_MESSAGE = (
    "Coffre de secrets non configuré : définissez ACP_SECRETS_KEYS avec une clé Fernet "
    "(générez-en une avec « python -m acp_api.secrets_vault generate-key »)."
)


class VaultNotConfigured(RuntimeError):
    """Le coffre ne peut pas fonctionner : clés absentes ou invalides."""


class VaultDecryptionFailed(RuntimeError):
    """Le jeton ne correspond à aucune clé connue ou a été altéré."""


def key_id(key: bytes) -> str:
    """Identifiant public et stable d'une clé (jamais la clé elle-même)."""

    return hashlib.sha256(key).hexdigest()[:KEY_ID_LENGTH]


def load_keys(environ: Mapping[str, str]) -> list[bytes]:
    """Lit et valide les clés Fernet de ``ACP_SECRETS_KEYS`` (primaire en premier)."""

    raw = environ.get(SECRETS_KEYS_ENV, "")
    parts = [part.strip() for part in raw.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        raise VaultNotConfigured(NOT_CONFIGURED_MESSAGE)
    keys: list[bytes] = []
    for position, part in enumerate(parts, start=1):
        try:
            encoded = part.encode("ascii")
            Fernet(encoded)
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise VaultNotConfigured(
                f"ACP_SECRETS_KEYS : la clé n°{position} est invalide "
                "(clé Fernet attendue : 32 octets encodés en base64 URL-safe)."
            ) from exc
        keys.append(encoded)
    return keys


class SecretsVault:
    """Chiffre avec la clé primaire, déchiffre avec toutes les clés connues."""

    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise VaultNotConfigured(NOT_CONFIGURED_MESSAGE)
        self._multi = MultiFernet([Fernet(key) for key in keys])
        self._key_ids = [key_id(key) for key in keys]

    def __repr__(self) -> str:
        return (
            f"SecretsVault(key_count={len(self._key_ids)}, "
            f"primary_key_id={self._key_ids[0]!r})"
        )

    @property
    def primary_key_id(self) -> str:
        return self._key_ids[0]

    @property
    def key_count(self) -> int:
        return len(self._key_ids)

    def encrypt(self, value: str) -> tuple[str, str]:
        """Retourne ``(key_id, jeton)`` ; le jeton est chiffré avec la clé primaire."""

        token = self._multi.encrypt(value.encode("utf-8")).decode("ascii")
        return self.primary_key_id, token

    def decrypt(self, token: str) -> str:
        try:
            return self._multi.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, TypeError, UnicodeEncodeError, UnicodeDecodeError) as exc:
            raise VaultDecryptionFailed(
                "Déchiffrement impossible : le jeton ne correspond à aucune clé de "
                "ACP_SECRETS_KEYS ou a été altéré."
            ) from exc

    def status(self) -> SecretsStatus:
        return SecretsStatus(
            configured=True,
            primary_key_id=self.primary_key_id,
            key_count=self.key_count,
            message=(
                f"Coffre configuré ({self.key_count} clé(s) ; "
                f"clé primaire {self.primary_key_id})."
            ),
        )


def get_vault(environ: Mapping[str, str] = os.environ) -> SecretsVault:
    """Construit le coffre depuis l'environnement ; lève ``VaultNotConfigured``."""

    return SecretsVault(load_keys(environ))


def vault_status(environ: Mapping[str, str] = os.environ) -> SecretsStatus:
    """État du coffre sans jamais lever : ``configured=False`` avec message actionnable."""

    try:
        return get_vault(environ).status()
    except VaultNotConfigured as exc:
        return SecretsStatus(
            configured=False, primary_key_id=None, key_count=0, message=str(exc)
        )


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["generate-key"]:
        print(generate_key())
        return 0
    print("Usage : python -m acp_api.secrets_vault generate-key", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
