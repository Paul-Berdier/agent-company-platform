"""Point d'entrée de compatibilité (``GET /meta``) et obtention dédiée du jeton CSRF.

Pourquoi ce routeur existe
--------------------------

Un client installé sur un poste — la station de travail native, le CLI — survit aux
déploiements du serveur. Jusqu'ici, aucune route ne publiait la version servie, la
version du contrat d'API, la version du schéma d'événement, les capacités activées ni
le plancher de version exigé d'un client : le seul signal était ``info.version`` du
document OpenAPI. Un client ne pouvait donc que **deviner**, ce que la doctrine du
projet interdit (``docs/desktop-railway-audit.md``, section 9.1).

Trois règles de construction, qui expliquent la forme du code ci-dessous :

1. **Aucune valeur n'est recopiée.** Chaque nombre publié est lu, pendant l'appel, du
   module qui en est la source : ``security.session_ttl_seconds`` pour la session,
   ``streams.stream_policy`` pour les bornes du flux, ``signing`` pour les liens,
   ``webhook_ingress`` pour le plafond de corps. Une constante dupliquée ici
   dériverait un jour de la vraie sans que rien n'échoue.
2. **Une capacité est calculée.** ``ACP_ARTIFACT_SIGNING_KEYS`` n'est pas « lue » : les
   clés sont réellement chargées et validées ; l'origine d'aperçu est réellement
   normalisée. Une configuration présente mais invalide se voit donc comme
   indisponible, et non comme disponible.
3. **Le document est public** — comme ``/health`` et ``/ready`` — donc il ne contient
   ni secret, ni chemin de fichier, ni URL interne, ni nom de variable
   d'environnement. Les explications restent des phrases françaises actionnables.

Décision sur le refus fermé d'un client trop ancien
--------------------------------------------------

Le plancher est **publié dans le corps** et **vérifié sur un en-tête facultatif**
``X-ACP-Client: <client>/<version>``. Un client qui s'annonce trop ancien reçoit un
**426 Upgrade Required** en français, portant tout de même le document : il peut
afficher la version servie et la version exigée plutôt qu'un message vide.

Ce choix, plutôt qu'un contrôle global à l'entrée de l'API :

- **aucun client existant ne casse** : le web et le CLI n'envoient pas cet en-tête, et
  une requête sans en-tête n'est jamais refusée ;
- **aucune mission en cours n'est coupée** : le refus n'a lieu que sur l'appel de
  compatibilité, que le client natif exécute au lancement. Un serveur mis à jour
  pendant qu'une mission tourne ne ferme donc pas le flux SSE au nom des versions ;
- le plancher par défaut est **la version du produit servie**, faute de matrice de
  compatibilité prouvée contre des versions antérieures. Un exploitant qui possède
  cette preuve l'abaisse par ``ACP_MIN_CLIENT_VERSION_DESKTOP`` /
  ``ACP_MIN_CLIENT_VERSION_CLI`` ; une valeur illisible est un refus 503, jamais un
  repli silencieux.

Ce qui n'est pas publié, et pourquoi
------------------------------------

La longueur maximale d'une ``Idempotency-Key`` n'a pas de constante partagée dans ce
dépôt (elle est écrite dans deux routeurs). La publier ici en créerait une troisième
copie : elle est donc omise tant qu'une source unique n'existe pas.
"""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from acp_contracts import (
    API_CONTRACT_VERSION,
    CLIENT_HEADER,
    CONTRACTS_VERSION,
    EVENT_SCHEMA_VERSION,
    KNOWN_CLIENTS,
    WEBHOOK_MAX_BODY_BYTES,
    ClientAnnouncement,
    ClientRequirement,
    ClientRequirements,
    ClientVersionError,
    CompatibilityDocument,
    CsrfTokenResponse,
    ServerCapabilities,
    ServerCapability,
    ServerLimits,
    ServerVersions,
    ServiceOriginError,
    compare_versions,
    normalize_service_origin,
    parse_client_header,
    parse_version,
)

from ..deps import get_auth_context, get_db
from ..outbox import relay_enabled
from ..secrets_vault import vault_status
from ..security import (
    CSRF_HEADER_NAME,
    AuthContext,
    csrf_token_is_valid,
    rotate_csrf_token,
    session_cookie_secure,
    session_ttl_seconds,
    utcnow,
)
from ..signing import (
    DEFAULT_LINK_TTL_SECONDS,
    MAX_LINK_TTL_SECONDS,
    ArtifactSigningNotConfigured,
    load_signing_keys,
)
from ..streams import (
    DEFAULT_EVENT_PAGE_LIMIT,
    MAX_EVENT_PAGE_LIMIT,
    event_retention_days,
    stream_policy,
)
from ..webhook_ingress import SKILL_SOURCE_MAX_BODY_BYTES
from . import missions as missions_router
from .artifacts import (
    ARTIFACT_PUBLIC_ORIGIN_ENV,
    DEFAULT_PAGE_SIZE as ARTIFACT_DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE as ARTIFACT_MAX_PAGE_SIZE,
)

router = APIRouter(tags=["meta"])

SERVICE_NAME = "api"

#: Emplacement explicite du fichier ``VERSION`` quand l'exploitant l'a déplacé.
VERSION_FILE_ENV = "ACP_VERSION_FILE"

#: Planchers de version relevables par l'exploitant, un par client connu.
MINIMUM_CLIENT_VERSION_ENV: dict[str, str] = {
    "desktop": "ACP_MIN_CLIENT_VERSION_DESKTOP",
    "cli": "ACP_MIN_CLIENT_VERSION_CLI",
}

#: Bascule du claim worker hérité. La route qui la lit (``routers/work.py``) n'expose
#: pas de constante ; le nom est donc répété ici, et seulement ici.
LEGACY_WORKER_CLAIM_ENV = "ACP_ALLOW_LEGACY_WORKER_CLAIM"

#: Le fichier ``VERSION`` du dépôt tient sur une ligne, sans préfixe ni suffixe.
_VERSION_FILE_PATTERN = re.compile(r"^\d{1,6}(?:\.\d{1,6}){0,3}(?:-[0-9A-Za-z.\-]{1,32})?$")

#: Racine de dépôt reconnue par ses répertoires, pour ne pas confondre le ``VERSION``
#: du produit avec un fichier homonyme rencontré en remontant l'arborescence.
_REPOSITORY_MARKERS = ("apps", "packages")

_DISTRIBUTION_NAME = "acp-api"


class ProductVersionUnavailable(RuntimeError):
    """La version du produit n'a aucune source lisible : refus, jamais de valeur inventée."""


@dataclass(frozen=True, slots=True)
class ProductVersionReading:
    """Version du produit et origine de la lecture, dite en français et sans chemin."""

    value: str
    source: str


def _clean_version_file(text: str) -> str | None:
    value = text.strip()
    if not value or _VERSION_FILE_PATTERN.fullmatch(value) is None:
        return None
    return value


def _read_version_file(path: Path) -> str | None:
    try:
        return _clean_version_file(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def _repository_version() -> str | None:
    """Remonte depuis ce module jusqu'à la racine du dépôt (cas d'une copie de travail)."""

    for parent in Path(__file__).resolve().parents:
        if not all((parent / marker).is_dir() for marker in _REPOSITORY_MARKERS):
            continue
        version = _read_version_file(parent / "VERSION")
        if version is not None:
            return version
    return None


def product_version(environ: Mapping[str, str] | None = None) -> ProductVersionReading:
    """Version du produit, lue du fichier ``VERSION`` à chaque appel.

    Quatre sources, dans l'ordre : l'emplacement explicitement configuré, la racine du
    dépôt au-dessus de ce module, le répertoire de travail du service (l'image Docker
    copie ``VERSION`` dans son ``WORKDIR``), puis les métadonnées de la distribution
    ``acp-api`` — que ``scripts/check_version.py`` maintient alignées sur ``VERSION``.

    Aucune valeur de repli codée en dur : sans source lisible, la fonction refuse.
    """

    environ = os.environ if environ is None else environ

    configured = str(environ.get(VERSION_FILE_ENV, "")).strip()
    if configured:
        version = _read_version_file(Path(configured))
        if version is not None:
            return ProductVersionReading(version, "fichier VERSION désigné par la configuration")

    version = _repository_version()
    if version is not None:
        return ProductVersionReading(version, "fichier VERSION du dépôt")

    try:
        working_directory = Path.cwd()
    except OSError:
        working_directory = None
    if working_directory is not None:
        version = _read_version_file(working_directory / "VERSION")
        if version is not None:
            return ProductVersionReading(
                version, "fichier VERSION du répertoire de travail du service"
            )

    try:
        distribution_version = _clean_version_file(
            importlib_metadata.version(_DISTRIBUTION_NAME)
        )
    except importlib_metadata.PackageNotFoundError:
        distribution_version = None
    if distribution_version is not None:
        return ProductVersionReading(
            distribution_version, "métadonnées de la distribution installée"
        )

    raise ProductVersionUnavailable(
        "Version du produit indéterminée : le fichier VERSION est introuvable ou "
        "illisible sur ce serveur. Aucune version n'est publiée plutôt qu'une version "
        "supposée."
    )


def _minimum_client_version(
    client: str, product: str, environ: Mapping[str, str]
) -> ClientRequirement:
    """Plancher exigé d'un client : la configuration si elle existe, sinon le produit."""

    variable = MINIMUM_CLIENT_VERSION_ENV[client]
    configured = str(environ.get(variable, "")).strip()
    if not configured:
        return ClientRequirement(
            client=client,
            minimum_version=product,
            source="version du produit servie",
            reason=(
                "Aucune compatibilité avec une version antérieure n'est prouvée pour ce "
                "serveur : le plancher est la version du produit servie."
            ),
        )
    try:
        parse_version(configured, label=f"Le plancher de version du client « {client} »")
    except ClientVersionError as exc:
        # La valeur lue n'est jamais renvoyée : ce document est public, et rien ne
        # garantit qu'une variable mal remplie ne contienne pas autre chose qu'une
        # version. Le nom de la variable suffit à l'exploitant pour corriger.
        raise HTTPException(
            status_code=503,
            detail=(
                f"Compatibilité indisponible : {variable} ne contient pas une version "
                "lisible, attendue sous la forme « 1.2.3 »."
            ),
        ) from exc
    return ClientRequirement(
        client=client,
        minimum_version=configured,
        source="configuration du serveur",
        reason=(
            "L'exploitant a déclaré ce plancher pour ce client ; il remplace la version "
            "du produit servie."
        ),
    )


def _capabilities(request: Request, environ: Mapping[str, str]) -> ServerCapabilities:
    """Vérifie chaque bascule maintenant : une capacité n'est jamais une déclaration."""

    try:
        load_signing_keys(environ)
        signing = ServerCapability(
            available=True,
            detail="Les liens signés de livrable peuvent être créés et révoqués.",
        )
    except ArtifactSigningNotConfigured:
        signing = ServerCapability(
            available=False,
            detail=(
                "Signature des liens de livrable non configurée : le téléchargement "
                "authentifié par session reste disponible."
            ),
        )

    vault = vault_status(environ)
    secrets = ServerCapability(
        available=bool(vault.configured),
        detail=(
            "Le coffre de secrets accepte l'écriture et la rotation."
            if vault.configured
            else "Coffre de secrets non configuré : l'écriture d'un secret est refusée."
        ),
    )

    relay = ServerCapability(
        available=relay_enabled(environ),
        detail=(
            "Les événements sont publiés au relais par l'outbox."
            if relay_enabled(environ)
            else "Relais d'événements inactif : la diffusion reste directe."
        ),
    )

    raw_origin = str(environ.get(ARTIFACT_PUBLIC_ORIGIN_ENV, "")).strip()
    if not raw_origin:
        preview = ServerCapability(
            available=False,
            detail=(
                "Aucune origine d'aperçu n'est configurée : les aperçus signés sont "
                "indisponibles."
            ),
        )
    else:
        try:
            normalize_service_origin(raw_origin, setting="origine d'aperçu")
        except ServiceOriginError:
            preview = ServerCapability(
                available=False,
                detail=(
                    "L'origine d'aperçu configurée n'est pas une origine HTTPS "
                    "exploitable : les aperçus signés sont indisponibles."
                ),
            )
        else:
            preview = ServerCapability(
                available=True,
                detail=(
                    "Une origine d'aperçu distincte est configurée ; l'aperçu reste "
                    "refusé si elle coïncide avec celle de la requête."
                ),
            )

    legacy_claim = environ.get(LEGACY_WORKER_CLAIM_ENV) == "1"
    legacy = ServerCapability(
        available=legacy_claim,
        detail=(
            "La route de claim worker héritée répond encore ; aucun client humain ne "
            "doit l'appeler."
            if legacy_claim
            else "La route de claim worker héritée est retirée (410)."
        ),
    )

    secure_cookie = session_cookie_secure()
    cookie = ServerCapability(
        available=secure_cookie,
        detail=(
            "Le cookie de session est marqué « Secure » : il exige HTTPS."
            if secure_cookie
            else (
                "Le cookie de session n'est pas marqué « Secure » : ce serveur n'est "
                "utilisable qu'en développement local."
            )
        ),
    )

    docs_published = bool(request.app.openapi_url) and bool(request.app.docs_url)
    docs = ServerCapability(
        available=docs_published,
        detail=(
            "La documentation interactive et le document OpenAPI sont publics."
            if docs_published
            else "La documentation interactive n'est pas publiée par ce serveur."
        ),
    )

    csrf = ServerCapability(
        available=True,
        detail=(
            "POST /auth/csrf confirme un jeton encore valide sans le faire tourner ; "
            "GET /auth/session, lui, fait tourner le jeton à chaque appel."
        ),
    )

    return ServerCapabilities(
        artifact_signing=signing,
        secrets_vault=secrets,
        event_relay=relay,
        artifact_preview=preview,
        legacy_worker_claim=legacy,
        session_cookie_secure=cookie,
        interactive_docs=docs,
        csrf_endpoint=csrf,
    )


def _declared_upper_bound(function, parameter: str) -> int | None:
    """Borne haute déclarée par une route pour un paramètre de requête.

    Lire la signature évite de recopier ici une borne écrite là-bas. Si la route change
    de forme, la valeur devient ``null`` — une inconnue affichable — plutôt qu'un
    chiffre périmé.
    """

    try:
        default = inspect.signature(function).parameters[parameter].default
    except (KeyError, TypeError, ValueError):
        return None
    for constraint in getattr(default, "metadata", ()) or ():
        bound = getattr(constraint, "le", None)
        if isinstance(bound, int):
            return bound
    return None


def _limits(environ: Mapping[str, str]) -> ServerLimits:
    """Bornes réelles, relues à chaque appel de leur module d'origine."""

    # Les champs d'identité de ``StreamPolicy`` ne servent qu'à une connexion réelle ;
    # seules les bornes temporelles sont lues ici, et elles ne dépendent d'aucun
    # utilisateur.
    policy = stream_policy(
        user_id="", session_token="", project_id="", environ=environ
    )
    return ServerLimits(
        session_ttl_seconds=session_ttl_seconds(),
        stream_max_seconds=policy.max_seconds,
        stream_keepalive_seconds=policy.keepalive_seconds,
        stream_poll_interval_ms=policy.poll_interval_seconds * 1000,
        stream_batch=policy.batch,
        stream_max_connections_per_user=policy.max_connections_per_user,
        stream_connection_limit_scope="process",
        event_page_default_limit=DEFAULT_EVENT_PAGE_LIMIT,
        event_page_max_limit=MAX_EVENT_PAGE_LIMIT,
        event_retention_days=event_retention_days(environ),
        mission_page_max_limit=_declared_upper_bound(
            missions_router.list_missions, "limit"
        ),
        artifact_page_default_limit=ARTIFACT_DEFAULT_PAGE_SIZE,
        artifact_page_max_limit=ARTIFACT_MAX_PAGE_SIZE,
        artifact_link_default_ttl_seconds=DEFAULT_LINK_TTL_SECONDS,
        artifact_link_max_ttl_seconds=MAX_LINK_TTL_SECONDS,
        max_request_body_bytes=WEBHOOK_MAX_BODY_BYTES,
        skill_source_max_body_bytes=SKILL_SOURCE_MAX_BODY_BYTES,
    )


def _announcement(
    header_value: str, requirements: ClientRequirements
) -> ClientAnnouncement:
    """Compare l'annonce du client au plancher publié pour ce client."""

    try:
        client, version = parse_client_header(header_value)
    except ClientVersionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Jamais un ``getattr`` libre : un nom de client comme « json » ou « copy »
    # désignerait une méthode du modèle Pydantic et produirait une erreur serveur là
    # où la réponse attendue est « client inconnu ».
    requirement = getattr(requirements, client) if client in KNOWN_CLIENTS else None
    if requirement is None:
        return ClientAnnouncement(
            client=client,
            version=version,
            known=False,
            accepted=True,
            minimum_version=None,
            detail=(
                "Ce serveur ne publie aucun plancher de version pour ce client : il ne "
                "peut donc ni le garantir ni le refuser."
            ),
        )

    accepted = compare_versions(version, requirement.minimum_version) >= 0
    return ClientAnnouncement(
        client=client,
        version=version,
        known=True,
        accepted=accepted,
        minimum_version=requirement.minimum_version,
        detail=(
            "Version acceptée par ce serveur."
            if accepted
            else (
                f"Version {version} refusée : ce serveur exige au moins la version "
                f"{requirement.minimum_version} du client « {client} ». "
                f"{requirement.reason}"
            )
        ),
    )


@router.get(
    "/meta",
    response_model=CompatibilityDocument,
    responses={
        400: {"description": "En-tête X-ACP-Client hors format"},
        426: {"description": "Client trop ancien pour ce serveur"},
        503: {"description": "Version du produit ou plancher de version indéterminable"},
    },
)
def read_meta(
    request: Request,
    client_header: str | None = Header(default=None, alias=CLIENT_HEADER),
) -> JSONResponse:
    """Publie versions, capacités et bornes de ce serveur. Public, sans secret.

    Chaque valeur est lue au moment de l'appel : redémarrer le service avec une autre
    configuration change la réponse sans redéploiement du client.
    """

    environ = os.environ
    try:
        version_reading = product_version(environ)
    except ProductVersionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    requirements = ClientRequirements(
        desktop=_minimum_client_version("desktop", version_reading.value, environ),
        cli=_minimum_client_version("cli", version_reading.value, environ),
    )
    announcement = (
        _announcement(client_header, requirements) if client_header is not None else None
    )

    document = CompatibilityDocument(
        service=SERVICE_NAME,
        checked_at=datetime.now(timezone.utc),
        versions=ServerVersions(
            product=version_reading.value,
            product_source=version_reading.source,
            api_contract=API_CONTRACT_VERSION,
            event_schema=EVENT_SCHEMA_VERSION,
            contracts=CONTRACTS_VERSION,
        ),
        clients=requirements,
        capabilities=_capabilities(request, environ),
        limits=_limits(environ),
        client_announcement=announcement,
    )

    refused = announcement is not None and not announcement.accepted
    payload = document.model_dump(mode="json")
    if refused:
        # 426 « Upgrade Required » : le refus est fermé et explicite, mais il porte le
        # document complet pour que le client affiche la version servie et la version
        # exigée au lieu d'un message vide.
        payload = {"detail": announcement.detail, **payload}
    return JSONResponse(
        status_code=426 if refused else 200,
        content=payload,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/auth/csrf", response_model=CsrfTokenResponse, tags=["auth"])
def issue_csrf_token(
    request: Request,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
) -> CsrfTokenResponse:
    """Confirme le jeton CSRF détenu, ou en émet un quand il n'y en a pas de valide.

    ``GET /auth/session`` fait tourner le jeton à **chaque** lecture : deux appels
    concurrents d'un client multi-thread se volent alors leur jeton et produisent des
    403 « Requête refusée » intermittents, indiscernables d'un vrai refus de droits
    (``docs/desktop-railway-audit.md``, section 9.2, point 2).

    Cette route est le point de sérialisation dédié. Elle est **additive** : le web et
    le CLI ne l'appellent pas et gardent exactement le comportement qu'ils avaient. Le
    comportement de ``GET /auth/session`` n'est pas modifié — le supprimer aurait
    demandé de rendre le jeton courant, que le serveur ne détient pas (il n'en conserve
    que l'empreinte), ou de garder l'ancien jeton valide pendant une fenêtre de grâce,
    ce qui suppose une colonne supplémentaire et une migration.

    Le jeton présenté est vérifié en temps constant ; s'il est valide, rien ne tourne et
    aucun jeton ne circule. La route n'exige pas elle-même le jeton CSRF — ce serait
    circulaire — mais le cookie de session est ``SameSite=strict`` : une page tierce ne
    peut pas la déclencher au nom de l'utilisateur.
    """

    presented = request.headers.get(CSRF_HEADER_NAME)
    if csrf_token_is_valid(context.session, presented):
        return CsrfTokenResponse(
            rotated=False, csrf_token=None, expires_at=context.session.expires_at
        )
    csrf_token = rotate_csrf_token(context.session)
    context.session.last_seen_at = utcnow()
    db.commit()
    return CsrfTokenResponse(
        rotated=True, csrf_token=csrf_token, expires_at=context.session.expires_at
    )
