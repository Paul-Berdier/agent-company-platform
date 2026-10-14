"""Sondes Claude Code : version épinglée, compte officiel et alias documentés.

Le statut vient du JSON borné de ``auth status`` dans le magasin officiel distant.
Un ancien setup-token conservé au coffre n'est jamais injecté dans le processus.
Aucun compte, code, URL OAuth ou contenu brut du CLI n'est publié dans le relevé.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Sequence

from .app_server import ArretNonConfirme
from .catalogue_claude import DOCUMENTATION_LUE_LE, PLAGE_MINIMALE, dans_la_plage, modeles_documentes
from .coffre import Coffre
from .comptes_claude import lire_etat_claude
from .local_runner import FencedSpawnError
from .politique import VERSION_CLAUDE_MINIMALE, SectionClaude, version_numerique
from .sondes_codex import lire_version
from .subscription_quotas import _failure, probe_claude_snapshot

DELAI_AUTH_STATUS_S = 20.0
PLATEFORME = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
              "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA", "HTTPS_PROXY", "HTTP_PROXY",
              "NO_PROXY")

CLAUDE_ABSENT = "Claude Code introuvable : [claude] executable de poste.toml ne désigne aucun fichier."
VERSION_ILLISIBLE = "Version de Claude Code illisible : relevé refusé."
LIGNE_ETAT_NON_DECLAREE = ("Ligne d'état non déclarée dans poste.toml ([claude] ligne_etat) : quotas Claude "
                           "inconnus.")


def environnement_claude(section: SectionClaude, *, source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environnement minimal ; authentification par le seul magasin officiel du CLI."""
    valeurs = os.environ if source is None else source
    env = {nom: valeurs[nom] for nom in PLATEFORME if nom in valeurs}
    env.update({"CLAUDE_CONFIG_DIR": str(section.config_dir), "DISABLE_UPDATES": "1", "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"})
    return env


@dataclass
class ResultatClaude:
    releve: dict[str, Any]
    connexion: str
    version: dict[str, Any]
    alertes: list[str] = field(default_factory=list)
    mesures: dict[str, Any] = field(default_factory=dict)
    arret_confirme: bool = True  # Interne : jamais envoyé dans l’inventaire.


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def sonder_claude(section: SectionClaude, coffre: Coffre, *, delai_s: float,
                        prefixe: Sequence[str] | None = None, environnement: Mapping[str, str] | None = None,
                        delai_auth_s: float = DELAI_AUTH_STATUS_S, dossiers: Callable[..., Any] | None = None,
                        compteur: Callable[[], Any] | None = None) -> ResultatClaude:
    """Relevé de la voie Claude ; ne lève jamais.

    Exécutant Linux (étape P6) : ``dossiers`` fabrique des dossiers temporaires à l'UID ``acp-claude`` ; ``compteur``
    rend le relevé de quotas tiré du dernier ``rate_limit_event`` observé (aucune ligne d'état sur Railway)."""

    instant = datetime.now(UTC)
    alertes: list[str] = []
    mesures: dict[str, Any] = {}
    connexion = "inconnu"
    arret_confirme = True

    def releve(etat: str, *, version: str | None, detail: str | None, modeles: list | None = None,
               compteurs: list | None = None) -> dict[str, Any]:
        return {"voie": "poste-claude", "source": "poste", "version_cli": version, "releve_le": _iso(instant),
                "modeles": modeles or [], "quotas": None, "compteurs": compteurs or [],
                "origine_liste": "alias_documentes" if modeles else "aucune", "etat": etat, "detail": detail,
                "documentation_lue_le": DOCUMENTATION_LUE_LE.isoformat() if modeles else None,
                "resolutions_observees": []}

    def resultat(r: dict[str, Any], version: str | None) -> ResultatClaude:
        return ResultatClaude(releve=r, connexion=connexion, alertes=alertes, mesures=mesures,
                              arret_confirme=arret_confirme, version={"lue": version, "testee": section.version_testee,
                                       "conforme": version == section.version_testee})

    argv = list(prefixe) if prefixe else [str(section.executable)]
    if not prefixe and not section.executable.is_file():
        return resultat(releve("cli_absente", version=None, detail=CLAUDE_ABSENT), None)
    env = environnement_claude(section, source=environnement)
    debut = time.monotonic()
    version = None
    try:
        fabrique = dossiers or (lambda prefix: tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True))
        with fabrique(prefix="acp-sonde-") as dossier:
            async with asyncio.timeout(delai_s):
                version = await lire_version(argv, env, dossier)
            if version is None:
                return resultat(releve("indisponible", version=None, detail=VERSION_ILLISIBLE), None)
            numerique = version_numerique(version)
            if numerique < VERSION_CLAUDE_MINIMALE:
                return resultat(releve("cli_hors_version", version=version, detail=(
                    f"Claude Code {version} trop ancien : le poste exige la version 2.1.248 ou plus récente "
                    "(--restricted).")), version)
            etat_compte = await lire_etat_claude(argv, env, dossier, delai_auth_s)
            connexion = ("compte_claude" if etat_compte.reconnu else
                         "jeton_absent" if etat_compte.type_auth == "none" else "refuse")
    except TimeoutError:
        return resultat(releve("indisponible", version=version, detail=(
            f"Claude Code n'a pas répondu dans le délai de {delai_s:g} s : relevé refusé.")), version)
    except FencedSpawnError as exc:
        if exc.reason == "spawn_error":
            return resultat(releve("cli_absente", version=None, detail=CLAUDE_ABSENT), None)
        return resultat(releve("indisponible", version=version, detail=(
            "Isolation du processus Claude Code impossible (Job Object) : sonde non lancée.")), version)
    except ArretNonConfirme:
        arret_confirme = False
        return resultat(releve("indisponible", version=version, detail=(
            "Arrêt de Claude Code non confirmé : relevé écarté par prudence.")), version)
    except ValueError:
        return resultat(releve("indisponible", version=version,
                              detail="État du compte Claude illisible ou incompatible : relevé refusé."), version)
    except OSError:
        return resultat(releve("indisponible", version=version, detail=VERSION_ILLISIBLE), version)
    mesures["duree_s"] = round(time.monotonic() - debut, 3)
    if compteur is not None:
        releve_quotas = compteur()
    elif section.ligne_etat is not None:
        releve_quotas = await probe_claude_snapshot(section.ligne_etat)
    else:
        releve_quotas = _failure("claude_code", "unavailable", LIGNE_ETAT_NON_DECLAREE)
    detail = None
    if not dans_la_plage(numerique):
        detail = (f"Claude Code {version} hors de la plage documentée (à partir de "
                  f"{'.'.join(map(str, PLAGE_MINIMALE))}) : alias publiés sans résolution ni efforts (Inconnu).")
    return resultat(releve("ok", version=version, detail=detail, modeles=modeles_documentes(numerique),
                           compteurs=[releve_quotas.model_dump(mode="json")]), version)
