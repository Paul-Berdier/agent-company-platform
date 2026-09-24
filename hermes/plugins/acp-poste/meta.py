"""Contenu de ``GET /api/plugins/acp-poste/v1/meta`` : ce que le client desktop et le
navigateur vérifient avant de parler au greffon.

Aucune valeur n'est inventée : ce qui ne peut pas être lu vaut ``None`` (« Inconnu ») et
produit une alerte en français. Les fichiers de l'image sont en lecture seule ; l'état du
démarrage vient de ``/run/acp/etat-demarrage.json``, écrit par root (05-acp) sur un tmpfs
que l'agent ne peut pas modifier.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

CONTRAT = "acp-poste/1"
NOM_GREFFON = "acp-poste"


@dataclass(frozen=True)
class SourcesMeta:
    """Emplacements lus par la route ; les tests en passent d'autres."""

    manifeste_greffon: Path = Path(__file__).resolve().parent / "plugin.yaml"
    version_hermes_epinglee: Path = Path("/opt/acp/contrat/HERMES_VERSION")
    openrpc_epingle: Path = Path("/opt/acp/contrat/gateway-contract.openrpc.json")
    openrpc_installe: Path = Path("/opt/hermes/apps/shared/src/gateway-contract.openrpc.json")
    etat_demarrage: Path = Path("/run/acp/etat-demarrage.json")


def lire_cles_valeurs(chemin: Path) -> Optional[Dict[str, str]]:
    """Fichier ``CLE=valeur`` (lignes ``#`` ignorées) ; None s'il est illisible."""
    try:
        texte = chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    valeurs: Dict[str, str] = {}
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        valeurs[cle.strip()] = valeur.strip()
    return valeurs


def version_greffon(manifeste: Path) -> Optional[str]:
    try:
        import yaml

        donnees = yaml.safe_load(manifeste.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — valeur inconnue plutôt qu'une erreur 500
        return None
    version = donnees.get("version") if isinstance(donnees, dict) else None
    return str(version) if version else None


def version_hermes_en_cours() -> Optional[str]:
    try:
        from hermes_cli import __version__
    except Exception:  # noqa: BLE001
        return None
    return str(__version__) or None


def _empreinte(chemin: Path) -> Optional[str]:
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return None


def _info_openrpc(chemin: Path) -> Dict[str, Any]:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        return {"info_version": str(donnees["info"]["version"]), "methodes": len(donnees["methods"])}
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        return {"info_version": None, "methodes": None}


def construire_meta(sources: SourcesMeta = SourcesMeta()) -> Dict[str, Any]:
    alertes: List[str] = []
    epingle = lire_cles_valeurs(sources.version_hermes_epinglee) or {}
    if not epingle:
        alertes.append("Version de Hermes épinglée inconnue : /opt/acp/contrat/HERMES_VERSION illisible.")

    version_testee = epingle.get("HERMES_VERSION")
    version_courante = version_hermes_en_cours()
    conforme: Optional[bool] = None
    if version_testee and version_courante:
        conforme = version_testee == version_courante
        if not conforme:
            alertes.append(
                f"Hermes {version_courante} n'est pas la version testée ({version_testee}).")
    else:
        alertes.append("Version de Hermes inconnue.")

    rpc_epingle = _info_openrpc(sources.openrpc_epingle)
    rpc_installe = _info_openrpc(sources.openrpc_installe)
    empreinte_epinglee = _empreinte(sources.openrpc_epingle)
    empreinte_installee = _empreinte(sources.openrpc_installe)
    identique: Optional[bool] = None
    if empreinte_epinglee and empreinte_installee:
        identique = empreinte_epinglee == empreinte_installee
        if not identique:
            alertes.append("Le contrat JSON-RPC de Hermes diffère de la copie épinglée par ACP.")
    else:
        alertes.append("Contrat JSON-RPC de Hermes inconnu.")

    demarrage: Optional[Dict[str, Any]]
    try:
        demarrage = json.loads(sources.etat_demarrage.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        demarrage = None
        alertes.append("État du démarrage inconnu : /run/acp/etat-demarrage.json absent "
                       "(le conteneur a-t-il démarré hors de s6 ?).")
    if isinstance(demarrage, dict):
        soul = demarrage.get("soul") or {}
        if soul.get("etat") == "divergent":
            alertes.append("SOUL.md a été modifié par le propriétaire : la persona livrée n'est pas appliquée.")
        elif soul.get("etat") == "non_ordinaire":
            alertes.append("SOUL.md n'est pas un fichier ordinaire : la persona livrée n'est pas appliquée.")
        greffons = (demarrage.get("greffons_utilisateur") or {}).get("dossiers") or []
        if greffons:
            alertes.append("Greffons utilisateur présents sous /opt/data/plugins (jamais activés) : "
                           + ", ".join(greffons) + ".")

    return {
        "contrat": CONTRAT,
        "greffon": {"nom": NOM_GREFFON, "version": version_greffon(sources.manifeste_greffon)},
        "hermes": {
            "version": version_courante,
            "version_testee": version_testee,
            "conforme": conforme,
            "etiquette": epingle.get("HERMES_TAG"),
            "commit": epingle.get("HERMES_COMMIT"),
        },
        "image": {
            "base": epingle.get("HERMES_IMAGE"),
            "condensat_index": epingle.get("HERMES_IMAGE_INDEX"),
        },
        "openrpc": {
            "info_version": rpc_installe["info_version"],
            "info_version_epinglee": rpc_epingle["info_version"],
            "methodes": rpc_installe["methodes"],
            "empreinte_installee": empreinte_installee,
            "empreinte_epinglee": empreinte_epinglee,
            "identique": identique,
        },
        "demarrage": demarrage,
        "alertes": alertes,
    }
