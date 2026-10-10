"""Inventaire publié par le poste (cahier P5 § 11) : relevés Codex et Claude, bac à sable, connexions, versions,
politique de ``poste.toml`` et alias des dépôts, au contrat ``InventairePoste`` (D21 étendu).

Avant tout envoi, l'inventaire est validé par le contrat partagé **puis** balayé par la garde « aucun
identifiant » (§ 11.3) : chaque valeur de chaîne **décodée** est refusée si elle contient un motif de secret, une
adresse (« @ »), un chemin de lecteur (``C:\\``, ``D:/``…), un chemin réseau, un chemin de profil, ``acpm_``/``acpe_``
ou une valeur exacte du coffre. Un inventaire refusé n'est pas envoyé (« inventaire retenu », journalisé). Les
``detail`` sont des phrases françaises composées par le poste, jamais une sortie brute de CLI.

Exécutant Linux (étape P6, cahier P6 § 7.3) : bloc ``poste`` en plateforme ``linux`` (``compte`` ``uid_dedie``, ``hote``,
``noyau``, sans ``windows``), bloc ``isolement_linux`` tiré de la sonde de plateforme (« inconnu » sans sonde : aucune
écriture) à la place de ``bac_a_sable_codex``, politique avec les conditions d'usage et les plafonds. Étape P7 (cahier P7
§ 11.2) : chaque dépôt distant porte sa visibilité MESURÉE (``visibilite``, ``lecture``, ``verifie_le``) ; le poste
Windows, qui n'exécute aucune carte, publie toujours l'alias seul.
"""

from __future__ import annotations

import asyncio
import platform
import sys
from datetime import UTC, datetime
from typing import Any

from acp_poste_contrat.inventaire import PROTOCOLE, identifiant_trouve, valider_inventaire

from . import __version__
from .politique import Politique
from .sondes_claude import ResultatClaude, sonder_claude
from .sondes_codex import ResultatCodex, sonder_codex


class InventaireRetenu(Exception):
    """Inventaire refusé par le contrat ou par la garde « aucun identifiant » : rien n'est envoyé (français)."""


def version_windows() -> str:
    """``10.0.19045`` : version du noyau Windows (jamais le nom réseau du PC)."""
    if not hasattr(sys, "getwindowsversion"):
        raise RuntimeError("Le poste ne publie son inventaire que sous Windows.")
    version = sys.getwindowsversion()
    return f"{version.major}.{version.minor}.{version.build}"


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


BAC_NON_SONDE = "Sonde Codex désactivée par poste.toml ([sondes] codex = false) : écriture refusée."


def _depot_publie(depot: Any, mesures: dict[str, Any]) -> dict[str, Any]:
    """``{"alias"}``, plus la visibilité MESURÉE (étape P7 : ``visibilite``, ``lecture``, ``verifie_le``) si le dépôt
    a été mesuré ; jamais une mesure inventée pour un dépôt qui ne l'a pas été (le greffon ferme alors Codex)."""
    publie: dict[str, Any] = {"alias": depot.alias}
    mesure = mesures.get(depot.alias)
    if mesure is not None:
        publie.update(mesure.contrat())
    return publie


def construire(politique: Politique, codex: ResultatCodex | None, claude: ResultatClaude | None, *,
               windows: str | None = None, valeurs_exactes: list[str], maintenant: datetime | None = None,
               infos: dict[str, Any] | None = None, isolement: dict[str, Any] | None = None,
               echeance_claude: Any = None, mesures: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inventaire validé et balayé, prêt à l'envoi ; lève :class:`InventaireRetenu` sinon. Sous Linux, ``infos``
    (plateforme, hôte, noyau) et ``isolement`` (bloc ``isolement_linux``) remplacent ``windows`` et le bac à sable ;
    ``mesures`` (alias → :class:`acp_poste.depots.Visibilite`, étape P7) porte la visibilité mesurée des dépôts."""

    instant = maintenant or datetime.now(UTC)
    linux = politique.plateforme == "linux"
    depots = [_depot_publie(depot, mesures or {}) for depot in politique.depots]
    releves = [dict(resultat.releve, depots=list(depots)) for resultat in (codex, claude) if resultat is not None]
    if not releves:
        raise InventaireRetenu("Aucune sonde active ([sondes] codex et claude à false dans poste.toml) : rien à publier.")
    if linux:
        bac = None
    else:
        bac = codex.bac_a_sable if codex is not None else {
            "readiness": "inconnu", "mode_lu": "inconnu", "origine_mode": "inconnu", "palier_lu": None,
            "stockage_identifiants_lu": None, "ecriture_admise": False, "raison": BAC_NON_SONDE,
            "lu_le": _iso(instant)}
    versions = {}
    if codex is not None:
        versions["codex"] = codex.version
    if claude is not None:
        versions["claude"] = claude.version
    inventaire = {
        "protocole": PROTOCOLE,
        "version_poste": __version__,
        "releve_le": _iso(instant),
        "poste": {"nom": politique.poste.nom, "compte": politique.poste.compte, "windows": windows,
                  "python": platform.python_version(), "politique_empreinte": politique.empreinte,
                  "hermes_meme_enveloppe_que_codex": politique.hermes_meme_enveloppe_que_codex},
        "depots": depots,
        "releves": releves,
        "bac_a_sable_codex": bac,
        "isolement_linux": None,
        "connexions": {"codex": codex.connexion if codex is not None else "inconnu",
                       "plan_codex": codex.plan if codex is not None else None,
                       "claude": claude.connexion if claude is not None else "inconnu",
                       "claude_echeance": echeance_claude.isoformat() if echeance_claude else None},
        "versions": versions,
        "politique": politique.resume_contrat(),
    }
    if linux:
        from .sonde_plateforme import isolement as bloc_isolement

        details = dict(infos or {"plateforme": "linux", "hote": "pc", "noyau": None})
        inventaire["poste"].update({"windows": None, "plateforme": "linux", "hote": details.get("hote", "pc"),
                                    "noyau": details.get("noyau")})
        sans = politique.codex.sans_bac_a_sable if politique.codex else "refuse"
        inventaire["isolement_linux"] = isolement or bloc_isolement(None, sans_bac_a_sable=sans, maintenant=instant)
    try:
        valide = valider_inventaire(inventaire)
    except ValueError as exc:
        raise InventaireRetenu(str(exc)[:500]) from None
    corps = valide.model_dump(mode="json")
    trouve = identifiant_trouve(corps, valeurs_exactes=[v for v in valeurs_exactes if v])
    if trouve:
        raise InventaireRetenu(f"Inventaire retenu par la garde « aucun identifiant » : {trouve}.")
    return corps


async def relever(politique: Politique, *, emplacements, coffre, lanceurs: dict[str, list[str]] | None = None,
                  environnement: dict[str, str] | None = None,
                  environnements: dict[str, dict[str, str] | None] | None = None,
                  dossiers: dict[str, Any] | None = None,
                  compteur_claude: Any = None) -> tuple[ResultatCodex | None, ResultatClaude | None]:
    """Sondes Codex et Claude en parallèle, chacune bornée par ``[sondes] delai_sonde_s``. ``environnements`` et
    ``dossiers`` (par outil) servent l'exécutant Linux : environnement de l'UID de l'agent, dossiers à son UID."""

    lanceurs = lanceurs or {}
    environnements = environnements or {}
    dossiers = dossiers or {}
    delai = float(politique.sondes.delai_sonde_s)
    taches = []
    if politique.sondes.codex and politique.codex is not None:
        taches.append(sonder_codex(politique.codex, emplacements, delai_s=delai, prefixe=lanceurs.get("codex"),
                                   environnement=environnements.get("codex", environnement),
                                   plateforme=politique.plateforme, dossiers=dossiers.get("codex")))
    else:
        taches.append(_rien())
    if politique.sondes.claude and politique.claude is not None:
        taches.append(sonder_claude(politique.claude, coffre, delai_s=delai, prefixe=lanceurs.get("claude"),
                                    environnement=environnements.get("claude", environnement),
                                    dossiers=dossiers.get("claude"), compteur=compteur_claude))
    else:
        taches.append(_rien())
    codex, claude = await asyncio.gather(*taches)
    return codex, claude


async def _rien() -> None:
    return None
