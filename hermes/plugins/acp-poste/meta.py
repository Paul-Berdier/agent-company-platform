"""Contenu de ``GET /api/plugins/acp-poste/v1/meta`` : ce que le client desktop et le
navigateur vérifient avant de parler au greffon.

Aucune valeur n'est inventée : ce qui ne peut pas être lu vaut ``None`` (« Inconnu ») et
produit une alerte en français. Les fichiers de l'image sont en lecture seule ; l'état du
démarrage vient de ``/run/acp/etat-demarrage.json``, écrit par root (05-acp) sur un tmpfs
que l'agent ne peut pas modifier.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

CONTRAT = "acp-poste/1"
NOM_GREFFON = "acp-poste"
DOSSIER_GERE_ATTENDU = "/etc/hermes"


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


def etat_environnement() -> Dict[str, Any]:
    """Contrôle vif de la portée gérée : détourne-t-on /etc/hermes ? Lu dans le processus du
    tableau de bord (donc reflète une injection de HERMES_MANAGED_DIR même après une relance
    par l'agent). Toute valeur illisible vaut ``None``."""
    resultat: Dict[str, Any] = {
        "managed_dir": None,
        "managed_dir_attendu": DOSSIER_GERE_ATTENDU,
        "managed_dir_conforme": None,
        "hermes_managed_dir_present": None,
    }
    try:
        import os

        from hermes_cli import managed_scope

        present = "HERMES_MANAGED_DIR" in os.environ
        dossier = managed_scope.get_managed_dir()
        resultat["hermes_managed_dir_present"] = present
        resultat["managed_dir"] = str(dossier) if dossier is not None else None
        # Ne conclut « non conforme » que sur un constat POSITIF de détournement : sous pytest
        # get_managed_dir() renvoie None sans que rien soit détourné (managed_scope.py:39-56).
        if present or (dossier is not None and str(dossier) != DOSSIER_GERE_ATTENDU):
            resultat["managed_dir_conforme"] = False
        elif dossier is not None:
            resultat["managed_dir_conforme"] = True
    except Exception:  # noqa: BLE001 — valeur inconnue plutôt qu'une erreur 500
        return resultat
    return resultat


LIBELLE_PROCESSUS = "processus du tableau de bord (sert /api/ws)"
ALERTE_GARDE_ABSENTE = ("Garde d'exécution absente du processus du tableau de bord : preview.restart "
                        "rendrait un terminal à l'agent.")


def _module_garde() -> ModuleType:
    """garde_execution.py de CE greffon. Le tableau de bord charge meta.py par son chemin, hors
    du paquet (dashboard/plugin_api.py) : le module est donc chargé de la même façon. La garde
    se reconnaît par son fichier, pas par le nom du module (garde_execution._est_cette_garde)."""
    module = sys.modules.get("garde_execution") or sys.modules.get("acp_poste_greffon_garde_execution")
    if module is not None and getattr(module, "__file__", None):
        return module
    cle = "acp_poste_greffon_garde_execution"
    spec = importlib.util.spec_from_file_location(cle, Path(__file__).resolve().parent / "garde_execution.py")
    if spec is None or spec.loader is None:
        raise ImportError("garde_execution.py du greffon acp-poste introuvable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cle] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(cle, None)
        raise
    return module


def etat_garde_execution(decouvrir: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
    """État de la garde d'exécution DANS LE PROCESSUS QUI SERT CETTE ROUTE, c'est-à-dire le
    tableau de bord : c'est lui qui fait tourner /api/ws et donc preview.restart
    (web_routers/chat_ws.py:583-601). Ce bloc ne prouve RIEN pour la passerelle ni pour les
    workers kanban, qui sont d'autres processus (correction R1-3).

    La découverte des greffons est d'abord demandée (idempotente ; le tableau de bord la fait
    déjà : web_server_profiles.py:348-349). Si elle lève, ou si le crochet est absent,
    ``alerte`` porte le message ; toute valeur illisible vaut ``None``."""
    bloc: Dict[str, Any] = {
        "processus": LIBELLE_PROCESSUS,
        "decouverte": None,
        "erreur_decouverte": None,
        "enregistree": None,
        "presente_dans_le_gestionnaire": None,
        "outils_admis": None,
        "outils_retires": None,
        "alerte": None,
    }
    try:
        if decouvrir is None:
            from hermes_cli.plugins import discover_plugins as decouvrir
        decouvrir()
        bloc["decouverte"] = "reussie"
    except Exception as exc:  # noqa: BLE001 — l'échec de la découverte EST l'information
        bloc["decouverte"] = "echec"
        bloc["erreur_decouverte"] = type(exc).__name__
    try:
        bloc.update(_module_garde().etat())
    except Exception:  # noqa: BLE001 — valeur inconnue plutôt qu'une erreur 500
        pass
    if bloc["decouverte"] != "reussie" or bloc["presente_dans_le_gestionnaire"] is not True:
        bloc["alerte"] = ALERTE_GARDE_ABSENTE
    return bloc


def _module_catalogue() -> ModuleType:
    """catalogue.py de CE greffon, chargé par son chemin comme meta.py (même clé que
    dashboard/plugin_api.py : un seul objet module)."""
    cle = "acp_poste_greffon_catalogue"
    module = sys.modules.get(cle)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(cle, Path(__file__).resolve().parent / "catalogue.py")
    if spec is None or spec.loader is None:
        raise ImportError("catalogue.py du greffon acp-poste introuvable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cle] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(cle, None)
        raise
    return module


def bloc_catalogue() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[str]]:
    """(bloc ``catalogue``, bloc ``interface``, alertes) de la méta, étape P3 : résumé de
    ``/v1/catalogue`` (état vu par le chargeur de skills de CE processus) et versions des greffons
    d'interface. Illisible : ``None`` et une alerte, jamais une erreur 500."""
    try:
        module = _module_catalogue()
        complet = module.construire_catalogue()
        return module.resume_pour_meta(complet), module.bloc_interface(), list(complet.get("alertes") or [])
    except Exception as exc:  # noqa: BLE001 — valeur inconnue plutôt qu'une erreur 500
        return None, None, [f"Catalogue d'ACP illisible ({type(exc).__name__}) : état inconnu."]


ENTETES_MESURES = ("x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "x-real-ip", "x-railway-edge")


def mesure_reseau(reseau: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalise la mesure faite par la route : pair, schéma vu, hôte, PRÉSENCE des en-têtes du
    bord (jamais la valeur de X-Forwarded-For) et X-Forwarded-Proto tronqué. Sert à fixer plus
    tard dashboard.trusted_proxies sur une mesure, jamais sur une supposition."""
    if reseau is None:
        return None

    def court(valeur: Any, limite: int) -> Optional[str]:
        if not isinstance(valeur, str) or not valeur:
            return None
        return "".join(c for c in valeur if c.isprintable())[:limite]

    presents = reseau.get("entetes_transmis") if isinstance(reseau.get("entetes_transmis"), Mapping) else {}
    return {
        "pair": court(reseau.get("pair"), 64),
        "schema_vu": court(reseau.get("schema_vu"), 16),
        "hote": court(reseau.get("hote"), 255),
        "entetes_transmis": {nom: bool(presents.get(nom)) for nom in ENTETES_MESURES},
        "x_forwarded_proto": court(reseau.get("x_forwarded_proto"), 16),
    }


def _commit_du_demarrage(demarrage: Any) -> Optional[str]:
    """Commit déployé tel que 05-acp l'a relevé (RAILWAY_GIT_COMMIT_SHA validé), écrit par root :
    l'environnement du tableau de bord, lui, peut être modifié par /opt/data/.env."""
    if not isinstance(demarrage, dict):
        return None
    commit = (demarrage.get("deploiement") or {}).get("commit")
    return commit if isinstance(commit, str) and commit else None


def _info_openrpc(chemin: Path) -> Dict[str, Any]:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        return {"info_version": str(donnees["info"]["version"]), "methodes": len(donnees["methods"])}
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        return {"info_version": None, "methodes": None}


def construire_meta(sources: SourcesMeta = SourcesMeta(), reseau: Optional[Mapping[str, Any]] = None,
                    decouvrir: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
    """Contenu de la route. ``reseau`` est mesuré par la route sur la requête elle-même
    (dashboard/plugin_api.py) ; ``None`` hors requête. ``decouvrir`` remplace la découverte des
    greffons de Hermes (tests)."""
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
        paresseux = (demarrage.get("lazy_packages") or {}).get("entrees") or []
        if paresseux:
            alertes.append("Paquets présents dans /opt/data/lazy-packages alors que les installations "
                           "paresseuses sont coupées : " + ", ".join(str(n) for n in paresseux[:20])
                           + ". À examiner avec « acp_demarrage.py diagnostiquer ».")
        # Étape P3 : réglages de skills écrits par 05-acp dans le config.yaml du volume.
        etat_catalogue = demarrage.get("catalogue") or {}
        reglages = etat_catalogue.get("reglages_skills") or {}
        if reglages.get("etat") == "illisible":
            alertes.append("Réglages de skills d'ACP non appliqués au démarrage : " + str(reglages.get("detail") or
                           "config.yaml illisible") + " Le catalogue d'ACP n'est peut-être pas chargé.")
        for avertissement in etat_catalogue.get("avertissements_mcp") or []:
            alertes.append(str(avertissement))
    deploiement = {"commit": _commit_du_demarrage(demarrage)}

    garde = etat_garde_execution(decouvrir)
    if garde["alerte"]:
        alertes.append(garde["alerte"])

    bloc_reseau = mesure_reseau(reseau)
    if bloc_reseau is not None and bloc_reseau.get("schema_vu") != "https":
        alertes.append(f"Le tableau de bord voit cette requête en « {bloc_reseau.get('schema_vu') or 'inconnu'} » "
                       "et non en https : ses cookies de session ne portent pas l'attribut Secure "
                       "(dashboard.trusted_proxies reste vide tant que le bord n'est pas mesuré).")

    catalogue, interface, alertes_catalogue = bloc_catalogue()
    alertes.extend(alertes_catalogue)

    environnement = etat_environnement()
    if environnement["managed_dir_conforme"] is False:
        alertes.append("Portée gérée détournée : HERMES_MANAGED_DIR est défini ou la portée gérée "
                       "n'est pas /etc/hermes. Les épingles de sécurité ne s'appliquent peut-être plus.")

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
        "environnement": environnement,
        "garde_execution": garde,
        "reseau": bloc_reseau,
        "deploiement": deploiement,
        # Étape P3 (ajouts, contrat acp-poste/1 inchangé) : résumé du catalogue et greffons d'interface.
        "catalogue": catalogue,
        "interface": interface,
        "alertes": alertes,
    }
