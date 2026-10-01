"""Coffre des secrets du poste sous DPAPI, un usage par secret (cahier P5 § 5.4).

Fichiers sous ``%LOCALAPPDATA%\\ACP\\secrets\\`` du compte du poste (ACL héritée du profil : le compte, SYSTEM,
Administrateurs) :

- ``jeton-machine.dpapi`` : jeton machine remis par Hermes à l'enrôlement ;
- ``claude-oauth.dpapi`` : jeton de ``claude setup-token`` (``acp-poste connexion claude``).

Contenu : l'en-tête ``ACPD1`` puis le blob DPAPI (portée utilisateur, entropie propre à l'usage). Écriture
atomique (fichier temporaire du même dossier, puis ``os.replace``). Un blob illisible (mot de passe du compte
réinitialisé par un administrateur, fichier altéré) est refusé en français, jamais contourné.

Il n'existe qu'un coffre de production, et il exige Windows : les tests sous Linux injectent le leur (jamais une
option de ``poste.toml``).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Callable, Protocol

from .chemins import commande_poste
from .credentials_protection import CredentialProtectionError, protect_credentials, unprotect_credentials

ENTETE = b"ACPD1"
TAILLE_MAX = 64 * 1024
USAGES = {
    "jeton-machine": ("jeton-machine.dpapi", b"ACP poste jeton machine v1"),
    "jeton-claude": ("claude-oauth.dpapi", b"ACP poste jeton Claude v1"),
}
COFFRE_ILLISIBLE = ("Coffre DPAPI illisible : le mot de passe du compte a probablement été réinitialisé ; refaites "
                    "les connexions et l'enrôlement.")
COFFRE_WINDOWS = "Le coffre du poste exige DPAPI Windows : aucun secret n'est écrit ni lu ici."


class CoffreErreur(RuntimeError):
    """Coffre indisponible ou illisible (message français, jamais la valeur)."""


class Coffre(Protocol):
    def lire(self, usage: str) -> str | None: ...

    def ecrire(self, usage: str, valeur: str) -> None: ...

    def effacer(self, usage: str) -> bool: ...

    def present(self, usage: str) -> bool: ...


def _usage(usage: str) -> tuple[str, bytes]:
    try:
        return USAGES[usage]
    except KeyError:
        raise CoffreErreur(f"Usage du coffre inconnu : {usage}.") from None


def ecrire_atomiquement(cible: Path, contenu: bytes) -> None:
    """Fichier temporaire du même dossier (création exclusive), ``fsync``, puis ``os.replace``."""

    cible.parent.mkdir(parents=True, exist_ok=True)
    temporaire = cible.parent / f".{cible.name}.{secrets.token_hex(6)}.tmp"
    descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(descripteur, "wb") as flux:
            flux.write(contenu)
            flux.flush()
            os.fsync(flux.fileno())
        os.replace(temporaire, cible)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


class CoffreDPAPI:
    """Coffre de production : DPAPI du compte courant, un fichier par usage."""

    def __init__(self, dossier: Path, *, proteger: Callable[..., bytes] = protect_credentials,
                 deproteger: Callable[..., bytes] = unprotect_credentials) -> None:
        self.dossier = Path(dossier)
        self._proteger = proteger
        self._deproteger = deproteger

    def _fichier(self, usage: str) -> tuple[Path, bytes]:
        nom, entropie = _usage(usage)
        return self.dossier / nom, entropie

    def ecrire(self, usage: str, valeur: str) -> None:
        fichier, entropie = self._fichier(usage)
        if not isinstance(valeur, str) or not valeur:
            raise CoffreErreur("Secret vide refusé par le coffre.")
        try:
            blob = self._proteger(valeur.encode("utf-8"), usage=entropie)
        except CredentialProtectionError:
            raise CoffreErreur(COFFRE_WINDOWS if os.name != "nt" else
                               "DPAPI Windows a refusé de protéger le secret : rien n'a été écrit.") from None
        ecrire_atomiquement(fichier, ENTETE + blob)

    def lire(self, usage: str) -> str | None:
        fichier, entropie = self._fichier(usage)
        try:
            with fichier.open("rb") as flux:
                contenu = flux.read(TAILLE_MAX + 1)
        except FileNotFoundError:
            return None
        except OSError:
            raise CoffreErreur(COFFRE_ILLISIBLE) from None
        if len(contenu) > TAILLE_MAX or not contenu.startswith(ENTETE):
            raise CoffreErreur(f"Coffre : fichier « {fichier.name} » au format inconnu : effacez-le "
                               f"(« {commande_poste('oublier-jeton')} » pour le jeton machine) puis refaites la "
                               "connexion.")
        try:
            clair = self._deproteger(contenu[len(ENTETE):], usage=entropie)
        except CredentialProtectionError:
            raise CoffreErreur(COFFRE_WINDOWS if os.name != "nt" else COFFRE_ILLISIBLE) from None
        try:
            return clair.decode("utf-8")
        except UnicodeDecodeError:
            raise CoffreErreur(COFFRE_ILLISIBLE) from None

    def effacer(self, usage: str) -> bool:
        fichier, _ = self._fichier(usage)
        try:
            fichier.unlink()
            return True
        except FileNotFoundError:
            return False

    def present(self, usage: str) -> bool:
        fichier, _ = self._fichier(usage)
        return fichier.is_file()
