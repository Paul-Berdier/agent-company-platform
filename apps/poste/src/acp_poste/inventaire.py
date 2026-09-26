"""Inventaire publié par le poste (cahier P5 § 11) : relevés Codex et Claude, bac à sable, connexions, versions,
politique de ``poste.toml`` et alias des dépôts, au contrat ``InventairePoste`` (D21 étendu).

Avant tout envoi, l'inventaire est validé par le contrat partagé **puis** balayé par la garde « aucun
identifiant » (§ 11.3) : chaque valeur de chaîne **décodée** est refusée si elle contient un motif de secret, une
adresse (« @ »), un chemin de lecteur (``C:\\``, ``D:/``…), un chemin réseau, un chemin de profil, ``acpm_``/``acpe_``
ou une valeur exacte du coffre. Un inventaire refusé n'est pas envoyé (« inventaire retenu », journalisé). Les
``detail`` sont des phrases françaises composées par le poste, jamais une sortie brute de CLI.
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


def construire(politique: Politique, codex: ResultatCodex | None, claude: ResultatClaude | None, *,
               windows: str, valeurs_exactes: list[str], maintenant: datetime | None = None) -> dict[str, Any]:
    """Inventaire validé et balayé, prêt à l'envoi ; lève :class:`InventaireRetenu` sinon."""

    instant = maintenant or datetime.now(UTC)
    depots = [{"alias": depot.alias} for depot in politique.depots]
    releves = [dict(resultat.releve, depots=list(depots)) for resultat in (codex, claude) if resultat is not None]
    if not releves:
        raise InventaireRetenu("Aucune sonde active ([sondes] codex et claude à false dans poste.toml) : rien à publier.")
    bac = codex.bac_a_sable if codex is not None else {
        "readiness": "inconnu", "mode_lu": "inconnu", "origine_mode": "inconnu", "palier_lu": None,
        "stockage_identifiants_lu": None, "ecriture_admise": False, "raison": BAC_NON_SONDE, "lu_le": _iso(instant)}
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
        "connexions": {"codex": codex.connexion if codex is not None else "inconnu",
                       "plan_codex": codex.plan if codex is not None else None,
                       "claude": claude.connexion if claude is not None else "inconnu"},
        "versions": versions,
        "politique": politique.resume_contrat(),
    }
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
                  environnement: dict[str, str] | None = None) -> tuple[ResultatCodex | None, ResultatClaude | None]:
    """Sondes Codex et Claude en parallèle, chacune bornée par ``[sondes] delai_sonde_s``."""

    lanceurs = lanceurs or {}
    delai = float(politique.sondes.delai_sonde_s)
    taches = []
    if politique.sondes.codex and politique.codex is not None:
        taches.append(sonder_codex(politique.codex, emplacements, delai_s=delai, prefixe=lanceurs.get("codex"),
                                   environnement=environnement))
    else:
        taches.append(_rien())
    if politique.sondes.claude and politique.claude is not None:
        taches.append(sonder_claude(politique.claude, coffre, delai_s=delai, prefixe=lanceurs.get("claude"),
                                    environnement=environnement))
    else:
        taches.append(_rien())
    codex, claude = await asyncio.gather(*taches)
    return codex, claude


async def _rien() -> None:
    return None
