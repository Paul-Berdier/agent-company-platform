"""Sondes Codex du poste (cahier P5 § 9) : catalogue du compte, connexion, bac à sable, quotas.

Un seul ``codex app-server`` par relevé, lancé sur le profil dédié (``[codex] home``) avec trois surcharges imposées
sur la ligne de commande (jamais par ``config.toml``, que ``--ignore-user-config`` des exécuteurs ignorerait) :

    <codex.exe> -c windows.sandbox="elevated" -c cli_auth_credentials_store="keyring" -c service_tier="default" app-server

Séquence stricte (liste blanche de :mod:`app_server`) : ``initialize``/``initialized``, ``account/read``,
``config/read {includeLayers: false}``, ``windowsSandbox/readiness``, ``model/list {includeHidden: false}`` (au plus
10 pages et 64 modèles), puis ``account/rateLimits/read {excludeResetCreditDetails: true}`` pour un compte ChatGPT
seulement. Les champs sont extraits par **liste blanche** : l'``email`` d'``account/read``, les descriptions et le
reste sont jetés au décodage ; aucun fichier du profil n'est lu (``models_cache.json`` porte l'identité du compte).

Origine de la liste (``origine_liste``, § 9.4) : sans compte, ``model/list`` rend le **catalogue embarqué** de Codex
(« Liste de secours ») ; un compte par clé d'API ou Bedrock est refusé (facturation hors abonnement) ; un compte
ChatGPT dont la liste est **identique** à celle d'un second app-server lancé sur un ``CODEX_HOME`` vide et temporaire
en stockage ``ephemeral`` (jamais connecté, relevé une fois par version) est « Liste de secours probable ».

Mode du bac à sable (§ 9.5) : ``ecriture_admise`` n'est vrai que si la readiness est ``ready``, le mode lu par
``config/read`` est ``elevated``, posé par le poste (origine ``sessionFlags``), et le stockage des identifiants
``keyring`` ; la readiness seule ne prouve jamais le mode élevé (décision D60).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from acp_poste_contrat.inventaire import ModeleReleve
from acp_poste_contrat.machine import commande_publiee
from acp_poste_contrat.quotas import SubscriptionQuotaReport

from .app_server import (
    ArretNonConfirme,
    ErreurRpc,
    MethodeRefusee,
    ReponseMalFormee,
    Session,
    SessionFermee,
    _vider,
    arreter,
)
from .chemins import Emplacements
from .coffre import ecrire_atomiquement
from .local_runner import FencedSpawnError, spawn_fenced_process
from .politique import SectionCodex, version_numerique
from .subscription_quotas import (
    CODEX_API_KEY_ACCOUNT,
    CODEX_MALFORMED,
    QuotaMalForme,
    _failure,
    codex_environment,
    codex_reports_from_rate_limits,
)

CONFIG_TOML = ("# Écrit par le poste ACP ; toute modification est refusée (acp-poste diagnostic).\n"
               "cli_auth_credentials_store = \"keyring\"\n"
               "[windows]\n"
               "sandbox = \"elevated\"\n").encode("utf-8")
SURCHARGES = ("-c", 'windows.sandbox="elevated"', "-c", 'cli_auth_credentials_store="keyring"',
              "-c", 'service_tier="default"')
SURCHARGES_EMBARQUE = ("-c", 'cli_auth_credentials_store="ephemeral"')
VERSION_MINIMALE = (0, 100, 0)
MODELES_MAX = 64
PAGES_MAX = 10
VERSION_OCTETS_MAX = 4096
CLES_CONFIG = ("windows.sandbox", "service_tier", "cli_auth_credentials_store")

CODEX_ABSENT = "Codex CLI introuvable : [codex] executable de poste.toml ne désigne aucun fichier."
# Textes publiés dans l'inventaire : commandes sous la forme exécutable SANS lettre de lecteur (décision D68).
PROFIL_ABSENT = f"Profil Codex non préparé : lancez « {commande_publiee('connexion codex')} » dans le compte du poste."
CONFIG_MODIFIEE = ("config.toml du profil Codex modifié hors du poste : supprimez-le puis relancez "
                   f"« {commande_publiee('connexion codex')} ».")
AGENTS_DANS_LE_PROFIL = "Le profil Codex contient un fichier AGENTS.md : relevé refusé (instructions hors du poste)."
VERSION_ILLISIBLE = "Version de Codex CLI illisible : relevé refusé."
SANS_COMPTE = ("Codex n'est connecté à aucun compte sur le poste : liste de secours (catalogue embarqué de Codex) ; "
               f"connectez-le ({commande_publiee('connexion codex')}).")
COMPTE_HORS_ABONNEMENT = ("Codex est connecté par clé d'API ou par Bedrock : refusé par ACP (facturation hors "
                          "abonnement) ; reconnectez-le avec votre compte ChatGPT "
                          f"({commande_publiee('connexion codex')}).")
CATALOGUE_LOCAL = "Un catalogue de modèles local (model_catalog_json) remplace celui du compte : relevé refusé."
TROP_DE_MODELES = f"Codex liste plus de {MODELES_MAX} modèles : relevé refusé plutôt que tronqué."
EMBARQUE_ILLISIBLE = ("Catalogue embarqué de Codex non relevé : impossible de distinguer la liste du compte d'une "
                      "liste de secours ; nouvel essai au prochain relevé.")
ARRET_NON_CONFIRME = "Arrêt de l'app-server Codex non confirmé : relevé écarté par prudence."
CLOTURE_IMPOSSIBLE = "Isolation du processus Codex impossible (Job Object) : sonde non lancée."
FERME = "L'app-server Codex s'est arrêté avant de répondre : relevé refusé."
MAL_FORME = "Réponse de l'app-server Codex mal formée : relevé refusé."

RAISONS_BAC = {
    "illisible": "Mode du bac à sable non lisible par config/read : écriture refusée par prudence.",
    "non_configure": "Bac à sable Codex non configuré.",
    "mxc": "Implémentation MXC non retenue par ACP.",
    "unelevated": "Bac à sable Codex non élevé (unelevated) : l'écriture est refusée.",
    "installation": f"Installation élevée du bac à sable à faire : {commande_publiee('connexion bac-a-sable')} (UAC).",
    "readiness": "Readiness du bac à sable Codex illisible : écriture refusée par prudence.",
    "couche": "Mode du bac à sable fixé par une couche {type} et non par le poste : écriture refusée.",
    "stockage": "Stockage des identifiants Codex lu : {valeur} ; attendu : keyring : écriture refusée.",
    "sonde": "Bac à sable non lu (relevé Codex en échec) : écriture refusée.",
}


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================ profil


def etat_config_toml(home: Path) -> str:
    """« conforme », « absent » (profil ou fichier) ou « modifie » : octet pour octet (§ 9.1)."""
    try:
        contenu = (home / "config.toml").read_bytes()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "modifie"
    return "conforme" if contenu.replace(b"\r\n", b"\n") == CONFIG_TOML else "modifie"


def ecrire_config_toml(home: Path) -> str:
    """Écrit ``config.toml`` du profil s'il manque (« cree ») ; « conforme » s'il est déjà celui du poste ; lève
    ``ValueError`` (français) s'il a été modifié hors du poste (jamais écrasé)."""
    etat = etat_config_toml(home)
    if etat == "conforme":
        return "conforme"
    if etat == "modifie":
        raise ValueError(CONFIG_MODIFIEE)
    home.mkdir(parents=True, exist_ok=True)
    ecrire_atomiquement(home / "config.toml", CONFIG_TOML)
    return "cree"


def _agents_dans(home: Path) -> bool:
    return any((home / nom).is_file() for nom in ("AGENTS.md", "AGENTS.override.md"))


# ============================================================ extraction (liste blanche)


def _texte_ou_none(valeur: Any) -> str | None:
    return valeur if isinstance(valeur, str) and valeur else None


def extraire_compte(resultat: dict[str, Any]) -> tuple[str, str | None]:
    """(``connexion``, ``plan``) depuis ``account/read`` : ``email`` et le reste sont jetés."""
    if "account" not in resultat:
        raise ReponseMalFormee
    compte = resultat["account"]
    if compte is None:
        return "non_connecte", None
    if not isinstance(compte, dict) or not isinstance(compte.get("type"), str):
        raise ReponseMalFormee
    genre = compte["type"]
    if genre == "chatgpt":
        plan = compte.get("planType")
        plan = plan if isinstance(plan, str) and plan and plan != "unknown" and len(plan) <= 40 else None
        return "compte_chatgpt", plan
    if genre == "apiKey":
        return "cle_api", None
    return "autre", None


def _origine(origines: Any, cle: str) -> str:
    if not isinstance(origines, dict):
        return "inconnu"
    entree = origines.get(cle)
    if not isinstance(entree, dict) or not isinstance(entree.get("name"), dict):
        return "inconnu"
    genre = entree["name"].get("type")
    if genre in ("sessionFlags", "user", "system"):
        return genre
    return "autre" if isinstance(genre, str) else "inconnu"


def extraire_config(resultat: dict[str, Any]) -> dict[str, Any]:
    """Seuls ``windows.sandbox``, ``service_tier``, ``cli_auth_credentials_store``, la PRÉSENCE de
    ``model_catalog_json`` et l'origine (type de couche) de ces clés : ni chemins ni autres valeurs."""
    config = resultat.get("config")
    if not isinstance(config, dict):
        raise ReponseMalFormee
    windows = config.get("windows")
    if isinstance(windows, dict) and "sandbox" in windows:
        mode = windows["sandbox"]
        mode = mode if mode in ("elevated", "unelevated", "mxc") else "inconnu"
    else:
        mode = "absent"
    origines = resultat.get("origins")
    return {
        "mode": mode,
        "origine_mode": _origine(origines, "windows.sandbox"),
        "palier": _texte_ou_none(config.get("service_tier")),
        "stockage": _texte_ou_none(config.get("cli_auth_credentials_store")),
        "catalogue_local": config.get("model_catalog_json") is not None,
    }


def extraire_modele(brut: Any) -> dict[str, Any]:
    """Un modèle de ``model/list`` réduit aux champs de la liste blanche, validé par le contrat (``ModeleReleve``)."""
    if not isinstance(brut, dict) or not isinstance(brut.get("id"), str):
        raise ReponseMalFormee
    efforts = brut.get("supportedReasoningEfforts")
    if not isinstance(efforts, list):
        raise ReponseMalFormee
    paliers = brut.get("serviceTiers") or []
    if not isinstance(paliers, list):
        raise ReponseMalFormee
    info = brut.get("upgradeInfo")
    retrait = info.get("retirementAt") if isinstance(info, dict) else None
    modele = {
        "id": brut["id"],
        "modele": _texte_ou_none(brut.get("model")),
        "displayName": _texte_ou_none(brut.get("displayName")),
        "isDefault": brut.get("isDefault") is True,
        "supportedReasoningEfforts": [e.get("reasoningEffort") if isinstance(e, dict) else None for e in efforts],
        "defaultReasoningEffort": _texte_ou_none(brut.get("defaultReasoningEffort")),
        "serviceTiers": [t.get("id") if isinstance(t, dict) else None for t in paliers],
        "defaultServiceTier": _texte_ou_none(brut.get("defaultServiceTier")),
        "cache": brut.get("hidden") is True,
        "remplace_par": _texte_ou_none(brut.get("upgrade")),
        "retrait_le": (_iso(datetime.fromtimestamp(retrait, UTC)) if type(retrait) is int and retrait > 0 else None),
        "nature": "catalogue_compte",
        "resolution_documentee": None,
        "source_efforts": "releve",
    }
    return ModeleReleve.model_validate(modele).model_dump(mode="json")


async def lister_modeles(session: Session) -> list[dict[str, Any]]:
    """``model/list`` paginé (≤ 10 pages, ≤ 64 modèles), extrait par liste blanche ; ``ValueError`` au-delà."""
    modeles: list[dict[str, Any]] = []
    curseur = None
    for _page in range(PAGES_MAX):
        params: dict[str, Any] = {"includeHidden": False}
        if curseur is not None:
            params["cursor"] = curseur
        resultat = await session.appeler("model/list", params)
        donnees = resultat.get("data")
        if not isinstance(donnees, list):
            raise ReponseMalFormee
        for brut in donnees:
            modeles.append(extraire_modele(brut))
            if len(modeles) > MODELES_MAX:
                raise ValueError(TROP_DE_MODELES)
        curseur = resultat.get("nextCursor")
        if curseur is None:
            return modeles
        if not isinstance(curseur, str):
            raise ReponseMalFormee
    raise ValueError(TROP_DE_MODELES)


def bac_a_sable(readiness: str, config: dict[str, Any] | None, lu_le: datetime) -> dict[str, Any]:
    """Matrice du § 9.5 → bloc ``BacASableCodex`` de l'inventaire (raison française si l'écriture est refusée)."""
    if config is None:
        return {"readiness": readiness, "mode_lu": "inconnu", "origine_mode": "inconnu", "palier_lu": None,
                "stockage_identifiants_lu": None, "ecriture_admise": False, "raison": RAISONS_BAC["sonde"],
                "lu_le": _iso(lu_le)}
    mode, origine, stockage = config["mode"], config["origine_mode"], config["stockage"]
    if mode in ("absent", "inconnu"):
        raison = RAISONS_BAC["illisible"]
    elif readiness == "notConfigured":
        raison = RAISONS_BAC["non_configure"]
    elif mode == "mxc":
        raison = RAISONS_BAC["mxc"]
    elif mode == "unelevated":
        raison = RAISONS_BAC["unelevated"]
    elif readiness == "updateRequired":
        raison = RAISONS_BAC["installation"]
    elif readiness != "ready":
        raison = RAISONS_BAC["readiness"]
    elif origine != "sessionFlags":
        raison = RAISONS_BAC["couche"].format(type=origine)
    elif stockage != "keyring":
        raison = RAISONS_BAC["stockage"].format(valeur=stockage or "inconnu")
    else:
        raison = None
    return {"readiness": readiness, "mode_lu": mode, "origine_mode": origine, "palier_lu": config["palier"],
            "stockage_identifiants_lu": stockage, "ecriture_admise": raison is None, "raison": raison,
            "lu_le": _iso(lu_le)}


# ============================================================ résultat


@dataclass
class ResultatCodex:
    """Ce que la sonde Codex rend à l'inventaire : relevé de la voie (sans les dépôts), bac à sable, connexion,
    version, alertes (françaises, sans valeur lue brute) et mesures (durées, nombres)."""

    releve: dict[str, Any]
    bac_a_sable: dict[str, Any]
    connexion: str
    plan: str | None
    version: dict[str, Any]
    alertes: list[str] = field(default_factory=list)
    mesures: dict[str, Any] = field(default_factory=dict)


def _releve(etat: str, origine: str, *, version: str | None, modeles: list | None = None, detail: str | None = None,
            compteurs: list | None = None, instant: datetime) -> dict[str, Any]:
    return {"voie": "poste-codex", "source": "poste", "version_cli": version, "releve_le": _iso(instant),
            "modeles": modeles or [], "quotas": None, "compteurs": compteurs or [], "origine_liste": origine,
            "etat": etat, "detail": detail, "documentation_lue_le": None, "resolutions_observees": []}


def _echec(etat: str, detail: str, section: SectionCodex, *, version: str | None, instant: datetime,
           connexion: str = "inconnu", plan: str | None = None, config: dict | None = None,
           readiness: str = "inconnu", compteurs: list | None = None) -> ResultatCodex:
    return ResultatCodex(
        releve=_releve(etat, "aucune", version=version, detail=detail, compteurs=compteurs, instant=instant),
        bac_a_sable=bac_a_sable(readiness, config, instant), connexion=connexion, plan=plan,
        version={"lue": version, "testee": section.version_testee, "conforme": version == section.version_testee})


async def lire_version(argv: Sequence[str], env: dict[str, str], cwd: str) -> str | None:
    """``<codex> --version`` sous clôture ; sortie bornée ; ``None`` si illisible. L'arbre est toujours arrêté."""
    processus = await spawn_fenced_process([*argv, "--version"], cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
                                           stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def lire() -> bytes:
        donnees = bytearray()
        flux = processus.stdout
        while flux is not None:
            morceau = await flux.read(4096)
            if not morceau:
                break
            donnees.extend(morceau[: max(0, VERSION_OCTETS_MAX - len(donnees))])
        return bytes(donnees)

    sortie = asyncio.create_task(lire())
    erreur = asyncio.create_task(_vider(processus.stderr))
    propre = False
    try:
        brut = await sortie
        propre = True
    finally:
        arrete = await asyncio.shield(arreter(processus, [sortie, erreur], propre=propre))
    if not arrete:
        raise ArretNonConfirme
    trouve = version_numerique(brut.decode("utf-8", errors="replace"))
    return ".".join(str(x) for x in trouve) if trouve else None


# ============================================================ catalogue embarqué


async def catalogue_embarque(prefixe: Sequence[str], version: str, emplacements: Emplacements, *,
                             environnement: dict[str, str] | None = None, delai_s: float = 30.0) -> list | None:
    """Liste de ``model/list`` d'un app-server sur un ``CODEX_HOME`` vide et temporaire, en stockage ``ephemeral``
    (jamais connecté : ``account/read`` doit rendre ``null``, sinon ``None``). Gardée par version de la CLI."""
    cache = emplacements.catalogue_embarque(version)
    try:
        garde = json.loads(cache.read_text(encoding="utf-8"))
        if isinstance(garde, dict) and garde.get("version") == version and isinstance(garde.get("modeles"), list):
            return garde["modeles"]
    except (OSError, ValueError):
        pass
    with tempfile.TemporaryDirectory(prefix="acp-codex-vide-", ignore_cleanup_errors=True) as home, \
            tempfile.TemporaryDirectory(prefix="acp-sonde-", ignore_cleanup_errors=True) as dossier:
        env = codex_environment(Path(home), source=environnement)
        async with asyncio.timeout(delai_s):
            async with Session([*prefixe, *SURCHARGES_EMBARQUE, "app-server"], env=env, cwd=dossier) as session:
                await session.initialiser()
                connexion, _plan = extraire_compte(await session.appeler("account/read", {}))
                if connexion != "non_connecte":
                    return None
                modeles = await lister_modeles(session)
    ecrire_atomiquement(cache, json.dumps({"version": version, "releve_le": _iso(datetime.now(UTC)),
                                           "modeles": modeles}, ensure_ascii=False).encode("utf-8"))
    return modeles


def _cle(modeles: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(m, sort_keys=True, ensure_ascii=False) for m in modeles)


# ============================================================ sonde


async def sonder_codex(section: SectionCodex, emplacements: Emplacements, *, delai_s: float,
                       prefixe: Sequence[str] | None = None, environnement: dict[str, str] | None = None,
                       ) -> ResultatCodex:
    """Relevé complet de la voie Codex ; ne lève jamais (un échec devient un relevé en échec, en français).

    ``prefixe`` : argv de lancement de la CLI (défaut : ``[executable]``) ; les tests y placent un faux app-server,
    jamais ``poste.toml``. ``environnement`` : environnement source (défaut : celui du processus)."""

    instant = datetime.now(UTC)
    argv = list(prefixe) if prefixe else [str(section.executable)]
    if not prefixe and not section.executable.is_file():
        return _echec("cli_absente", CODEX_ABSENT, section, version=None, instant=instant)
    etat_profil = etat_config_toml(section.home)
    if etat_profil == "absent":
        return _echec("non_connecte", PROFIL_ABSENT, section, version=None, instant=instant, connexion="non_connecte")
    if etat_profil == "modifie":
        return _echec("indisponible", CONFIG_MODIFIEE, section, version=None, instant=instant)
    if _agents_dans(section.home):
        return _echec("indisponible", AGENTS_DANS_LE_PROFIL, section, version=None, instant=instant)

    env = codex_environment(section.home, source=environnement)
    mesures: dict[str, Any] = {}
    version = None
    debut = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="acp-sonde-", ignore_cleanup_errors=True) as dossier:
            async with asyncio.timeout(delai_s):
                version = await lire_version(argv, env, dossier)
                if version is None:
                    return _echec("indisponible", VERSION_ILLISIBLE, section, version=None, instant=instant)
                if version_numerique(version) < VERSION_MINIMALE:
                    return _echec("cli_hors_version", f"Codex CLI {version} trop ancien : le poste exige la version "
                                  f"{'.'.join(map(str, VERSION_MINIMALE))} ou plus récente.", section,
                                  version=version, instant=instant)
                async with Session([*argv, *SURCHARGES, "app-server"], env=env, cwd=dossier) as session:
                    await session.initialiser()
                    connexion, plan = extraire_compte(await session.appeler("account/read", {}))
                    config = extraire_config(await session.appeler("config/read", {"includeLayers": False}))
                    avant = time.monotonic()
                    readiness_brute = (await session.appeler("windowsSandbox/readiness", avec_params=False)).get("status")
                    mesures["readiness_s"] = round(time.monotonic() - avant, 3)
                    readiness = readiness_brute if readiness_brute in ("ready", "notConfigured", "updateRequired") \
                        else "inconnu"
                    if connexion in ("cle_api", "autre"):
                        return _echec("indisponible", COMPTE_HORS_ABONNEMENT, section, version=version,
                                      instant=instant, connexion=connexion, config=config, readiness=readiness,
                                      compteurs=[_failure("codex", "not_signed_in", CODEX_API_KEY_ACCOUNT)
                                                 .model_dump(mode="json")])
                    if config["catalogue_local"]:
                        return _echec("indisponible", CATALOGUE_LOCAL, section, version=version, instant=instant,
                                      connexion=connexion, plan=plan, config=config, readiness=readiness)
                    modeles = await lister_modeles(session)
                    if connexion == "compte_chatgpt":
                        try:
                            limites = await session.appeler("account/rateLimits/read",
                                                            {"excludeResetCreditDetails": True})
                            compteurs = [r.model_dump(mode="json") for r in codex_reports_from_rate_limits(
                                limites, account_plan=plan, observed_at=datetime.now(UTC))]
                        except ErreurRpc as exc:
                            compteurs = [_failure("codex", "unavailable", f"L'app-server Codex a refusé la lecture des "
                                                  f"limites (code {exc.code}) : quotas non relevés.", plan=plan)
                                         .model_dump(mode="json")]
                        except QuotaMalForme:
                            compteurs = [_failure("codex", "unavailable", CODEX_MALFORMED, plan=plan)
                                         .model_dump(mode="json")]
                    else:
                        compteurs = [_failure("codex", "not_signed_in", SANS_COMPTE).model_dump(mode="json")]
                    mesures["requetes_du_serveur"] = session.requetes_du_serveur
            if connexion == "non_connecte":
                origine, detail = "catalogue_embarque", SANS_COMPTE
            else:
                try:
                    embarque = await catalogue_embarque(argv, version, emplacements, environnement=environnement,
                                                        delai_s=delai_s)
                except (TimeoutError, FencedSpawnError, ErreurRpc, ArretNonConfirme, SessionFermee,
                        ReponseMalFormee, ValidationError, MethodeRefusee, ValueError, OSError):
                    embarque = None
                if embarque is None:
                    return _echec("indisponible", EMBARQUE_ILLISIBLE, section, version=version, instant=instant,
                                  connexion=connexion, plan=plan, config=config, readiness=readiness,
                                  compteurs=compteurs)
                identique = _cle(embarque) == _cle(modeles)
                origine = "identique_au_catalogue_embarque" if identique else "compte"
                detail = (f"Liste identique au catalogue embarqué de Codex {version} : liste de secours probable."
                          if identique else None)
    except TimeoutError:
        return _echec("indisponible", f"L'app-server Codex n'a pas répondu dans le délai de {delai_s:g} s : relevé "
                      "refusé.", section, version=version, instant=instant)
    except FencedSpawnError as exc:
        if exc.reason == "spawn_error":
            return _echec("cli_absente", CODEX_ABSENT, section, version=None, instant=instant)
        return _echec("indisponible", CLOTURE_IMPOSSIBLE, section, version=version, instant=instant)
    except ErreurRpc as exc:
        return _echec("indisponible", f"L'app-server Codex a refusé la lecture ({exc.methode}, code {exc.code}) : "
                      "relevé refusé.", section, version=version, instant=instant)
    except ArretNonConfirme:
        return _echec("indisponible", ARRET_NON_CONFIRME, section, version=version, instant=instant)
    except SessionFermee:
        return _echec("indisponible", FERME, section, version=version, instant=instant)
    except (ReponseMalFormee, ValidationError, MethodeRefusee):
        return _echec("indisponible", MAL_FORME, section, version=version, instant=instant)
    except ValueError as exc:
        return _echec("indisponible", str(exc)[:300], section, version=version, instant=instant)
    except OSError:
        return _echec("indisponible", MAL_FORME, section, version=version, instant=instant)
    mesures["duree_s"] = round(time.monotonic() - debut, 3)
    mesures["modeles"] = len(modeles)
    bac = bac_a_sable(readiness, config, instant)
    alertes = []
    if config["palier"] != "default":
        alertes.append(f"Palier Codex lu : {config['palier'] or 'inconnu'} ; attendu : default.")
    if config["stockage"] != "keyring":
        alertes.append(f"Stockage des identifiants Codex lu : {config['stockage'] or 'inconnu'} ; attendu : keyring.")
    releve = _releve("ok", origine, version=version, modeles=modeles, detail=detail, compteurs=compteurs,
                     instant=instant)
    return ResultatCodex(releve=releve, bac_a_sable=bac, connexion=connexion, plan=plan,
                         version={"lue": version, "testee": section.version_testee,
                                  "conforme": version == section.version_testee},
                         alertes=alertes, mesures=mesures)


async def installer_bac_a_sable(argv: list[str], env: dict[str, str], dossier: str, delai_s: float) -> dict:
    """Session **interactive** (seule à admettre ``windowsSandbox/setupStart``), sans ``cwd``."""
    async with asyncio.timeout(delai_s):
        async with Session(argv, env=env, cwd=dossier, interactive=True) as session:
            await session.initialiser()
            fin = asyncio.ensure_future(session.attendre_notification("windowsSandbox/setupCompleted"))
            try:
                await session.appeler("windowsSandbox/setupStart", {"mode": "elevated"})
                return await fin
            finally:
                if not fin.done():
                    fin.cancel()


def compteurs_valides(compteurs: list[dict[str, Any]]) -> list[SubscriptionQuotaReport]:
    """Relit les compteurs d'un relevé par le contrat (pour ``acp-poste quotas``)."""
    return [SubscriptionQuotaReport.model_validate(c) for c in compteurs]
