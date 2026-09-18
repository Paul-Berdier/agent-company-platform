"""Contrat de compatibilité serveur / client, servi par ``GET /meta``.

Un client installé sur un poste — la station de travail native, le CLI — survit aux
déploiements du serveur. Avant d'ouvrir une session il doit pouvoir lire, en un appel
public : la version du produit servie, la version du contrat d'API (versionnée
indépendamment du produit), la version du schéma d'événement, les capacités
**réellement** activées sur ce serveur, les bornes qu'il applique, et le plancher de
version qu'il exige de chaque client connu.

Trois règles gouvernent ce contrat, et elles sont la raison d'être du module :

1. **Rien n'est recopié.** Ce module ne porte aucune version de produit, aucune borne
   de flux, aucune taille de page : ce sont des champs, remplis par le serveur depuis
   la source qui fait foi au moment de l'appel. La seule constante versionnée ici est
   ``API_CONTRACT_VERSION``, qui n'a pas d'autre source.
2. **Une capacité est calculée, jamais déclarée.** ``ServerCapability.available``
   rapporte le résultat d'une vérification exécutée pendant l'appel (clé de signature
   lisible, coffre configuré, relais actif, origine d'aperçu valide), pas une intention
   de configuration.
3. **Aucun secret, aucun chemin, aucune URL interne.** Le document est public comme
   ``/health`` et ``/ready`` : ``ServerCapability.detail`` explique une indisponibilité
   en français sans jamais nommer une valeur de configuration.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field

__all__ = [
    "API_CONTRACT_VERSION",
    "CLIENT_HEADER",
    "CLIENT_HEADER_HELP",
    "KNOWN_CLIENTS",
    "ClientAnnouncement",
    "ClientRequirement",
    "ClientRequirements",
    "ClientVersionError",
    "CompatibilityDocument",
    "ServerCapabilities",
    "ServerCapability",
    "ServerLimits",
    "ServerVersions",
    "compare_versions",
    "parse_client_header",
    "parse_version",
]


API_CONTRACT_VERSION = "1.0"
"""Version du contrat d'API exposé aux clients, indépendante de la version du produit.

Elle ne suit pas ``VERSION`` : un correctif de produit ne change pas le contrat, et un
changement de contrat peut survenir sans nouvelle version de produit. Elle augmente en
partie mineure pour un ajout compatible, en partie majeure pour un retrait ou un
changement de sens d'un champ déjà publié.
"""

CLIENT_HEADER = "X-ACP-Client"
"""En-tête facultatif par lequel un client s'annonce : ``<client>/<version>``."""

CLIENT_HEADER_HELP = (
    "En-tête « X-ACP-Client » attendu sous la forme « client/version », par exemple "
    "« desktop/0.9.0 » : un nom en minuscules et une version numérique séparée par "
    "des points."
)

KNOWN_CLIENTS: tuple[str, ...] = ("desktop", "cli")
"""Clients pour lesquels ce serveur publie un plancher de version."""


_CLIENT_HEADER_PATTERN = re.compile(
    r"^(?P<client>[a-z][a-z0-9-]{0,31})/(?P<version>[0-9][0-9A-Za-z.\-]{0,31})$"
)
_VERSION_PATTERN = re.compile(
    r"^(?P<release>\d{1,6}(?:\.\d{1,6}){0,3})(?:-(?P<prerelease>[0-9A-Za-z.\-]{1,32}))?$"
)
_RELEASE_SEGMENTS = 4


class ClientVersionError(ValueError):
    """Une version ou une annonce de client est hors format : refus, jamais devinette."""


def parse_version(value: str, *, label: str) -> tuple[tuple[int, ...], str | None]:
    """Décompose ``1.2.3`` ou ``1.2.3-rc1`` en ``((1, 2, 3, 0), "rc1")``.

    Aucune tolérance : une chaîne hors grammaire lève ``ClientVersionError`` plutôt que
    de se voir attribuer un rang arbitraire. Comparer des versions mal lues, c'est
    refuser ou accepter un client au hasard.
    """

    if not isinstance(value, str):
        raise ClientVersionError(f"{label} doit être une chaîne de caractères.")
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ClientVersionError(
            f"{label} n'est pas une version reconnue : « {value} » attendu sous la "
            "forme « 1.2.3 », éventuellement suivie de « -préversion »."
        )
    release = tuple(int(part) for part in match.group("release").split("."))
    padded = release + (0,) * (_RELEASE_SEGMENTS - len(release))
    return padded, match.group("prerelease")


def compare_versions(left: str, right: str, *, label: str = "La version") -> int:
    """Ordonne deux versions : ``-1``, ``0`` ou ``1``.

    Une préversion est **inférieure** à la version finale correspondante : ``0.9.0-rc1``
    ne satisfait pas un plancher de ``0.9.0``. Deux préversions du même numéro se
    comparent par leur étiquette, faute de meilleur ordre.
    """

    left_release, left_pre = parse_version(left, label=label)
    right_release, right_pre = parse_version(right, label=label)
    if left_release != right_release:
        return -1 if left_release < right_release else 1
    if left_pre == right_pre:
        return 0
    if left_pre is None:
        return 1
    if right_pre is None:
        return -1
    return -1 if left_pre < right_pre else 1


def parse_client_header(value: str) -> tuple[str, str]:
    """Lit ``desktop/0.9.0`` et rend ``("desktop", "0.9.0")``.

    Le nom est exigé en minuscules — il n'est pas replié, parce qu'un serveur qui
    accepterait « Desktop » et « desktop » indifféremment inviterait deux écritures du
    même client. La version est validée par ``parse_version``, de sorte qu'une annonce
    illisible soit refusée avant toute comparaison.
    """

    if not isinstance(value, str):
        raise ClientVersionError(CLIENT_HEADER_HELP)
    match = _CLIENT_HEADER_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ClientVersionError(CLIENT_HEADER_HELP)
    client = match.group("client")
    version = match.group("version")
    parse_version(version, label="La version annoncée par le client")
    return client, version


class ServerVersions(BaseModel):
    """Les quatre versions qu'un client doit connaître avant de se connecter."""

    product: str = Field(
        description="Version du produit servie, lue du fichier VERSION au moment de l'appel."
    )
    product_source: str = Field(
        description="Origine de la version du produit, en français, sans chemin ni URL."
    )
    api_contract: str = Field(
        description="Version du contrat d'API, indépendante de la version du produit."
    )
    event_schema: str = Field(
        description="Version du schéma des événements transportés par le flux SSE."
    )
    contracts: str = Field(
        description="Version des contrats de données partagés par les services."
    )


class ClientRequirement(BaseModel):
    """Plancher de version exigé d'un client connu, avec sa justification."""

    client: str
    minimum_version: str
    source: str = Field(
        description="Ce qui détermine ce plancher : la version du produit, ou la configuration du serveur."
    )
    reason: str = Field(description="Justification en français, affichable telle quelle.")


class ClientRequirements(BaseModel):
    """Planchers publiés, un champ nommé par client connu (lisible par un client natif)."""

    desktop: ClientRequirement
    cli: ClientRequirement


class ClientAnnouncement(BaseModel):
    """Écho de l'en-tête ``X-ACP-Client`` reçu, et verdict du serveur.

    ``known`` vaut ``false`` pour un client dont ce serveur ne publie aucun plancher :
    il est alors accepté sans exigence, parce qu'affirmer une incompatibilité sans
    référence serait une invention.
    """

    client: str
    version: str
    known: bool
    accepted: bool
    minimum_version: str | None = None
    detail: str


class ServerCapability(BaseModel):
    """Résultat d'une vérification exécutée pendant l'appel, jamais une déclaration."""

    available: bool
    detail: str = Field(
        description="Ce que le client peut en conclure, en français, sans nom de variable ni secret."
    )


class ServerCapabilities(BaseModel):
    """Bascules réellement observées sur ce serveur au moment de l'appel."""

    artifact_signing: ServerCapability
    secrets_vault: ServerCapability
    event_relay: ServerCapability
    artifact_preview: ServerCapability
    legacy_worker_claim: ServerCapability
    session_cookie_secure: ServerCapability
    interactive_docs: ServerCapability
    csrf_endpoint: ServerCapability


class ServerLimits(BaseModel):
    """Bornes réelles du serveur, lues de la source qui fait foi à chaque appel.

    Une borne dont ce dépôt ne possède pas de source unique n'est pas publiée : la
    recopier ici en ferait une deuxième vérité, qui dériverait sans que rien n'échoue.
    """

    session_ttl_seconds: int
    stream_max_seconds: float
    stream_keepalive_seconds: float
    stream_poll_interval_ms: float
    stream_batch: int
    stream_max_connections_per_user: int
    stream_connection_limit_scope: str = Field(
        description=(
            "Portée réelle du compteur de flux simultanés. « process » signifie que la "
            "borne ne vaut globalement que tant que le service tourne en une réplique."
        )
    )
    event_page_default_limit: int
    event_page_max_limit: int
    event_retention_days: int = Field(
        description="Fenêtre de conservation du journal annoncée aux lecteurs ; 0 signifie illimitée."
    )
    mission_page_max_limit: int | None = Field(
        default=None,
        description=(
            "Borne haute de « limit » sur GET /missions, lue de la signature de la route ; "
            "null quand ce serveur ne peut pas la déterminer."
        ),
    )
    artifact_page_default_limit: int
    artifact_page_max_limit: int
    artifact_link_default_ttl_seconds: int
    artifact_link_max_ttl_seconds: int
    max_request_body_bytes: int
    skill_source_max_body_bytes: int


class CompatibilityDocument(BaseModel):
    """Corps de ``GET /meta`` : tout ce qu'un client doit savoir avant de se connecter."""

    service: str
    checked_at: datetime = Field(
        description="Instant de l'évaluation, en UTC : le document n'est pas mis en cache."
    )
    versions: ServerVersions
    clients: ClientRequirements
    capabilities: ServerCapabilities
    limits: ServerLimits
    client_announcement: ClientAnnouncement | None = Field(
        default=None,
        description="Présent uniquement si la requête portait l'en-tête X-ACP-Client.",
    )
