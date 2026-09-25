"""Démarrage ACP de l'image Hermes : gardes, managed scope et données du volume.

Commandes, exécutées en root par l'interpréteur de Hermes
(``/opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py <commande>``) :

``construire``
    Appelée par le Dockerfile. Valide le modèle ``/opt/acp/gere/config.yaml`` et pose une
    première managed scope (valeurs de déploiement vides) : les épingles s'appliquent
    même à un processus lancé hors de s6. Un modèle invalide fait échouer la construction.

``gardes``
    Crochet ``S6_STAGE2_HOOK`` (``/opt/acp/bin/acp-gardes``), exécuté par s6-overlay au tout
    début de l'étape 2, AVANT tout service et tout script cont-init
    (``/package/admin/s6-overlay/etc/s6-linux-init/skel/rc.init``) : refuse de démarrer si
    une variable interdite est présente ou si une variable attendue est absente ou
    invalide, régénère ``/etc/hermes/.env`` et ``/etc/hermes/config.yaml`` et vérifie qu'ils
    se relisent, puis inspecte ``/opt/data/plugins`` (noms réservés ``acp-*``, liens). Un
    refus à ce stade arrête le conteneur (code 1) avant que ``01-hermes-setup`` ne
    consomme une variable interdite et avant que ``02-reconcile-profiles`` ne lance la
    passerelle : un script cont-init en échec, lui, n'empêche pas les suivants de tourner.

``donnees``
    ``/etc/cont-init.d/05-acp``, APRÈS ``02-reconcile-profiles`` : refait les contrôles du
    crochet (défense en profondeur), vérifie la managed scope installée, rend
    ``/opt/data/plugins``, ``/opt/data/dashboard-themes`` et ``/opt/data/acp`` propriété de
    root (0755, fichiers 0644), dépose le thème ``acp`` et ``SOUL.md`` selon son empreinte,
    puis écrit l'état du démarrage dans ``/run/acp/etat-demarrage.json`` (lu par
    ``/api/plugins/acp-poste/v1/meta``). Depuis P2, rend aussi ``/opt/data/hooks`` et
    ``/opt/data/scripts`` propriété de root après avoir exigé qu'ils soient vides.

``verifier-relance``
    Garde root en tête des scripts ``run`` du tableau de bord et des passerelles.

``diagnostiquer``
    Maintenance (étape P2), en LECTURE SEULE et en root : rassemble tout ce qui ferait
    refuser le démarrage ou ce qui ferait exécuter du code depuis le volume (clés
    exécutables de ``config.yaml``, ``hooks/``, ``scripts/``, ``lazy-packages``), sans rien
    écrire. L'environnement de référence est celui du PID 1 (``/proc/1/environ`` hors de
    s6, ``/run/s6/container_environment`` sous s6), JAMAIS celui de la session qui lance la
    commande (``railway ssh`` ne documente pas le sien). Code 0 si rien n'est trouvé, 1
    sinon.

Tout écart lève :class:`Refus` : message en français sur la sortie d'erreur, code 1. Avec
``S6_BEHAVIOUR_IF_STAGE2_FAILS=2``, s6-overlay arrête alors le conteneur avec le code 1.

Ce module n'importe rien de Hermes (il tourne en root, avant que Hermes n'ait amorcé son
volume) : seulement la bibliothèque standard, PyYAML et python-dotenv de l'environnement
virtuel de l'image. Le chargeur YAML est celui de ``utils.fast_safe_load`` de Hermes
(utils.py:613-615) : ``yaml.load`` avec le chargeur C sûr.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import ipaddress
import json
import os
import pwd
import re
import stat
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

PREFIXE = "[acp]"

# ---------------------------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Chemins:
    """Emplacements utilisés au démarrage. Les valeurs par défaut sont celles de l'image ;
    les tests en passent d'autres. Aucune variable d'environnement ne peut les changer."""

    modele_gere: Path = Path("/opt/acp/gere/config.yaml")
    dossier_gere: Path = Path("/etc/hermes")
    hermes_home: Path = Path("/opt/data")
    theme_livre: Path = Path("/opt/acp/theme")
    soul_livre: Path = Path("/opt/acp/persona/SOUL.md")
    soul_amont: Path = Path("/opt/hermes/docker/SOUL.md")
    dossier_etat: Path = Path("/run/acp")
    scandir_s6: Path = Path("/run/service")
    # Lus par `diagnostiquer` et la règle du volume Railway (étape P2) ; les tests passent des
    # fichiers factices.
    montages: Path = Path("/proc/self/mountinfo")
    proc_pid1: Path = Path("/proc/1")
    env_s6: Path = Path("/run/s6/container_environment")

    @property
    def greffons_utilisateur(self) -> Path:
        return self.hermes_home / "plugins"

    @property
    def themes(self) -> Path:
        return self.hermes_home / "dashboard-themes"

    @property
    def donnees_acp(self) -> Path:
        return self.hermes_home / "acp"

    @property
    def crochets_passerelle(self) -> Path:
        """``handler.py`` exécutés par la passerelle sans consentement (gateway/hooks.py:44-72)."""
        return self.hermes_home / "hooks"

    @property
    def scripts_cron(self) -> Path:
        """Scripts des tâches cron (cron/scheduler_script.py:257-320)."""
        return self.hermes_home / "scripts"

    @property
    def paquets_paresseux(self) -> Path:
        """Cible des installations paresseuses (HERMES_LAZY_INSTALL_TARGET)."""
        return self.hermes_home / "lazy-packages"


class Refus(Exception):
    """Refus de démarrer, avec un message en français destiné au propriétaire."""


# ---------------------------------------------------------------------------------------------
# Variables d'environnement
# ---------------------------------------------------------------------------------------------

# Variables dont la seule PRÉSENCE refuse le démarrage (même vide). La raison est affichée.
VARIABLES_INTERDITES: Dict[str, str] = {
    "HERMES_MANAGED_DIR": (
        "elle déplacerait la managed scope hors de /etc/hermes et la mettrait à la merci "
        "de celui qui contrôle ce répertoire (hermes_cli/managed_scope.py:45-59)"),
    "API_SERVER_KEY": (
        "l'image génère sa propre clé pour l'api_server en boucle locale "
        "(docker/stage2-hook.sh:459-540) ; une clé fournie de l'extérieur est inutile"),
    "API_SERVER_ENABLED": "l'api_server reste en boucle locale, géré par l'image",
    "API_SERVER_PORT": "le port de l'api_server est fixé à 8642 par la managed scope",
    "HERMES_DASHBOARD_OAUTH_CLIENT_ID": (
        "le fournisseur Nous Portal est écarté : la connexion passe par l'OIDC auto-hébergé"),
    "HERMES_DASHBOARD_PORTAL_URL": (
        "le fournisseur Nous Portal est écarté : la connexion passe par l'OIDC auto-hébergé"),
    "HERMES_DASHBOARD_DRAIN_SECRET": "le fournisseur drain est désactivé",
    "HERMES_DASHBOARD_INSECURE": "le tableau de bord n'est jamais exposé sans authentification",
    "HERMES_BUNDLED_PLUGINS": "les greffons groupés viennent de /opt/hermes/plugins, dans l'image",
    "HERMES_ENABLE_PROJECT_PLUGINS": "aucun greffon de projet n'est admis",
    "HERMES_KANBAN_HOME": "l'emplacement du kanban est celui de /opt/data",
    "HERMES_KANBAN_DB": "l'emplacement du kanban est celui de /opt/data",
    "HERMES_KANBAN_BOARD": (
        "le tableau courant reste « default » ; le tableau « poste » est toujours nommé "
        "explicitement"),
    "HERMES_ALLOW_ROOT_GATEWAY": "la passerelle ne tourne jamais en root",
    "HERMES_DOCKER_EXEC_AS_ROOT": "les commandes hermes lancées par docker exec restent sous l'uid hermes",
    "HERMES_AUTH_JSON_BOOTSTRAP": (
        "aucun identifiant n'est injecté dans auth.json au démarrage "
        "(docker/stage2-hook.sh:659-670)"),
    "HERMES_AUTH_JSON_REBOOTSTRAP": "aucun identifiant n'est injecté dans auth.json au démarrage",
    "HERMES_UID": "l'agent tourne sous l'uid 10000 de l'image, sans remappage",
    "HERMES_GID": "l'agent tourne sous le gid 10000 de l'image, sans remappage",
    "PUID": "l'agent tourne sous l'uid 10000 de l'image, sans remappage",
    "PGID": "l'agent tourne sous le gid 10000 de l'image, sans remappage",
    "HERMES_GATEWAY_NO_SUPERVISE": "la passerelle reste supervisée par s6",
    "AUTO_UPDATE": "Hermes n'est jamais mis à jour en place : une montée passe par une PR",
    "DASHBOARD_PASSWORD": "reste de l'ancien modèle Railway, sans effet et interdit",
    # Mandataires et autorités de certification : l'agent ne doit pas pouvoir détourner les
    # appels du tableau de bord vers le fournisseur d'identité (découverte OIDC, JWKS) ; la
    # managed scope les épingle (mandataires vides, magasin de certificats du système).
    "HTTP_PROXY": "aucun mandataire réseau n'est admis",
    "HTTPS_PROXY": "aucun mandataire réseau n'est admis",
    "ALL_PROXY": "aucun mandataire réseau n'est admis",
    "http_proxy": "aucun mandataire réseau n'est admis",
    "https_proxy": "aucun mandataire réseau n'est admis",
    "all_proxy": "aucun mandataire réseau n'est admis",
    "SSL_CERT_FILE": "les autorités de certification sont celles de l'image",
    "SSL_CERT_DIR": "les autorités de certification sont celles de l'image",
    "REQUESTS_CA_BUNDLE": "les autorités de certification sont celles de l'image",
    "CURL_CA_BUNDLE": "les autorités de certification sont celles de l'image",
    # Étape P2 : aucun outil d'exécution pour l'agent. Chacune de ces variables rouvrirait un
    # chemin d'exécution ou de contournement ; elles sont aussi épinglées dans /etc/hermes/.env.
    "HERMES_TUI_TOOLSETS": (
        "elle remplacerait les outils de la discussion du tableau de bord, terminal compris "
        "(tui_gateway/server.py:1866-1928)"),
    "HERMES_BIN": (
        "elle choisirait le programme lancé pour chaque worker kanban "
        "(hermes_cli/kanban_db_dispatch.py:2510-2530)"),
    "HERMES_ACCEPT_HOOKS": (
        "elle ferait inscrire sans consentement les crochets shell de la configuration "
        "(config_defaults.py:1710-1714)"),
    "HERMES_SAFE_MODE": (
        "elle sauterait la découverte des greffons, donc la garde d'exécution d'acp-poste "
        "(hermes_cli/plugins.py, discover_and_load)"),
    "HERMES_YOLO_MODE": "elle approuverait sans demander toute commande dangereuse",
    "HERMES_COPILOT_ACP_COMMAND": "elle choisirait un programme exécuté comme fournisseur copilot-acp",
    "HERMES_COPILOT_ACP_ARGS": "elle choisirait les arguments d'un programme exécuté comme fournisseur copilot-acp",
    "COPILOT_CLI_PATH": "elle choisirait un programme exécuté comme fournisseur copilot-acp",
    "HERMES_ALLOW_PRIVATE_URLS": (
        "l'accès de l'agent au réseau privé (api_server 8642, tableau de bord 9119, réseau "
        "Railway) reste fermé : la valeur est fixée à false par l'image"),
    "HERMES_PORTAL_BASE_URL": (
        "le fournisseur Nous Portal est écarté ; stage2-hook.sh recopierait cette adresse "
        "(docker/stage2-hook.sh:579-610)"),
    "NOUS_PORTAL_BASE_URL": (
        "le fournisseur Nous Portal est écarté ; stage2-hook.sh recopierait cette adresse "
        "(docker/stage2-hook.sh:579-610)"),
    "NOUS_INFERENCE_BASE_URL": (
        "le fournisseur Nous Portal est écarté ; stage2-hook.sh recopierait cette adresse "
        "(docker/stage2-hook.sh:579-610)"),
    "HERMES_GATEWAY_BOOTSTRAP_STATE": "l'état initial de la passerelle n'est jamais injecté au démarrage",
}

PREFIXES_INTERDITS: Dict[str, str] = {
    "HERMES_DASHBOARD_BASIC_AUTH_": (
        "le fournisseur par mot de passe est désactivé : la connexion passe par l'OIDC "
        "auto-hébergé"),
}

# Variables fixées par l'image (Dockerfile) : une autre valeur est refusée.
# (valeur attendue, obligatoire)
VALEURS_IMPOSEES: Dict[str, Tuple[str, bool]] = {
    "HERMES_HOME": ("/opt/data", True),
    "HERMES_WEB_DIST": ("/opt/hermes/hermes_cli/web_dist", True),
    "HERMES_DASHBOARD": ("1", True),
    "HERMES_DASHBOARD_HOST": ("0.0.0.0", True),
    "HERMES_DASHBOARD_PORT": ("9119", True),
    "S6_BEHAVIOUR_IF_STAGE2_FAILS": ("2", True),
    "S6_STAGE2_HOOK": ("/opt/acp/bin/acp-gardes", True),
    "API_SERVER_HOST": ("127.0.0.1", False),
    # Valeurs de l'ENV de l'image officielle (Dockerfile:427-449 de Hermes), fixées depuis P2.
    "HERMES_WRITE_SAFE_ROOT": ("/opt/data", True),
    "HERMES_DISABLE_LAZY_INSTALLS": ("1", True),
    "HERMES_LAZY_INSTALL_TARGET": ("/opt/data/lazy-packages", True),
    "HERMES_TUI_DIR": ("/opt/hermes/ui-tui", True),
    "XDG_RUNTIME_DIR": ("/tmp/hermes-runtime", True),
}

# Marqueurs posés par Railway dans chaque déploiement (rw/variables_reference.md) : leur
# présence signifie « sur Railway », où le volume du service est exigé sur /opt/data.
MARQUEURS_RAILWAY: Tuple[str, ...] = ("RAILWAY_ENVIRONMENT_ID", "RAILWAY_DEPLOYMENT_ID", "RAILWAY_SERVICE_ID")
POINT_DE_MONTAGE = "/opt/data"
_SHA_COMMIT = re.compile(r"[0-9a-f]{7,64}")

# Seuls répertoires admis dans le PATH du conteneur, que tous les scripts root lancés par s6
# reçoivent par with-contenv (s6-overlay y ajoute /command). Tous appartiennent à root. Un
# répertoire du volume (l'image officielle y met /opt/data/.local/bin, Dockerfile:476) ferait
# exécuter en root les binaires que l'agent y dépose (`id`, `sh`, `sleep`…).
PATH_ADMIS = ("/command", "/opt/hermes/bin", "/opt/hermes/.venv/bin", "/usr/local/sbin",
              "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin")

PORTEES_PAR_DEFAUT = "openid profile email"

_URL_CARACTERES = re.compile(r"^[A-Za-z0-9._~:/%-]+$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+/-]{0,199}$")
_PORTEE = re.compile(r"^[A-Za-z0-9._:/-]{1,64}$")
_EMPREINTE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ValeursDeploiement:
    """Variables Railway validées, recopiées dans la managed scope."""

    url_publique: str
    oidc_emetteur: str
    oidc_client: str
    oidc_portees: str
    secret_client_fourni: bool = False

    def marqueurs(self) -> Dict[str, str]:
        return {
            "HERMES_DASHBOARD_PUBLIC_URL": self.url_publique,
            "HERMES_DASHBOARD_OIDC_ISSUER": self.oidc_emetteur,
            "HERMES_DASHBOARD_OIDC_CLIENT_ID": self.oidc_client,
            "HERMES_DASHBOARD_OIDC_SCOPES": self.oidc_portees,
        }


# Valeurs vides pour la construction de l'image : aucun fournisseur ne s'enregistre, le
# tableau de bord refuse alors de se lier hors du bouclage local (web_server.py:1135-1138).
VALEURS_VIDES = ValeursDeploiement(url_publique="", oidc_emetteur="", oidc_client="", oidc_portees="")


def raison_interdiction(nom: str) -> Optional[str]:
    """Raison du refus d'une variable, ou None si elle est admise."""
    if nom in VARIABLES_INTERDITES:
        return VARIABLES_INTERDITES[nom]
    for prefixe, raison in PREFIXES_INTERDITS.items():
        if nom.startswith(prefixe):
            return raison
    return None


def _hote_interdit(hote: str) -> Optional[str]:
    """Raison du refus d'un nom d'hôte, ou None. Refuse le bouclage local, les adresses non
    publiques et les noms « localhost » : un émetteur servi depuis le conteneur serait sous
    le contrôle de l'agent. Refuse aussi le domaine privé de Railway : le navigateur doit
    joindre l'émetteur et l'URL publique, et l'émetteur que publie le fournisseur d'identité est
    son domaine PUBLIC (docs/refonte/identite.md)."""
    nom = hote.lower().rstrip(".")
    if not nom:
        return "hôte absent"
    if nom == "localhost" or nom.endswith(".localhost"):
        return "hôte local interdit"
    if nom == "railway.internal" or nom.endswith(".railway.internal"):
        return "domaine privé de Railway interdit : utilisez le domaine public *.up.railway.app du service"
    try:
        adresse = ipaddress.ip_address(nom)
    except ValueError:
        return None
    if not adresse.is_global:
        return "adresse IP non publique interdite"
    return None


def valider_url_https(nom: str, valeur: str) -> str:
    """Valide une URL https (émetteur OIDC, URL publique) ; renvoie la valeur inchangée."""
    if valeur != valeur.strip() or not valeur:
        raise Refus(f"{nom} est vide ou entourée d'espaces.")
    if len(valeur) > 2048:
        raise Refus(f"{nom} dépasse 2 048 caractères.")
    if not _URL_CARACTERES.match(valeur):
        raise Refus(
            f"{nom} contient un caractère refusé (seuls lettres, chiffres et « . _ ~ : / % - » "
            "sont admis : ni requête, ni fragment, ni identifiants).")
    parts = urllib.parse.urlsplit(valeur)
    if parts.scheme != "https":
        raise Refus(f"{nom} doit être une URL en https, reçu « {valeur} ».")
    if not parts.netloc or parts.hostname is None:
        raise Refus(f"{nom} n'a pas d'hôte : « {valeur} ».")
    try:
        port = parts.port
    except ValueError as exc:
        raise Refus(f"{nom} a un port invalide : « {valeur} ».") from exc
    if port is not None and not 1 <= port <= 65535:
        raise Refus(f"{nom} a un port invalide : « {valeur} ».")
    raison = _hote_interdit(parts.hostname)
    if raison:
        raise Refus(f"{nom} : {raison} (« {parts.hostname} »).")
    segments = parts.path.split("/")
    if any(s in {".", ".."} for s in segments) or "//" in parts.path:
        raise Refus(f"{nom} a un chemin ambigu : « {valeur} ».")
    return valeur


def valider_client_id(nom: str, valeur: str) -> str:
    if not _CLIENT_ID.match(valeur):
        raise Refus(
            f"{nom} doit compter de 1 à 200 caractères parmi lettres, chiffres et « . _ : @ + / - », "
            "en commençant par une lettre ou un chiffre.")
    return valeur


def valider_portees(nom: str, valeur: str) -> str:
    jetons = valeur.split(" ")
    if not valeur or any(not _PORTEE.match(j) for j in jetons):
        raise Refus(f"{nom} doit être une liste de portées séparées par une espace simple.")
    if "openid" not in jetons:
        raise Refus(f"{nom} doit contenir la portée « openid » (sans elle, aucun jeton d'identité).")
    if len(set(jetons)) != len(jetons):
        raise Refus(f"{nom} contient une portée en double.")
    return valeur


def sur_railway(env: Mapping[str, str]) -> bool:
    """Vrai si l'un des marqueurs posés par Railway est présent dans l'environnement."""
    return any(nom in env for nom in MARQUEURS_RAILWAY)


def _desechapper_mountinfo(champ: str) -> str:
    """Le noyau échappe espace, tabulation, saut de ligne et barre oblique inverse en octal
    (\\040, \\011, \\012, \\134) dans /proc/self/mountinfo."""
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), champ)


def point_de_montage_present(mountinfo: Path, point: str = POINT_DE_MONTAGE) -> Optional[bool]:
    """Vrai si ``point`` est un point de montage (5e champ de /proc/self/mountinfo) ; None si
    le fichier est illisible."""
    try:
        texte = mountinfo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for ligne in texte.splitlines():
        champs = ligne.split(" ")
        if len(champs) >= 5 and _desechapper_mountinfo(champs[4]) == point:
            return True
    return False


def verifier_montage(env: Mapping[str, str], mountinfo: Path = Path("/proc/self/mountinfo")) -> None:
    """Sur Railway, /opt/data doit être un vrai point de montage (le volume du service) : la
    variable RAILWAY_VOLUME_MOUNT_PATH ne suffit pas, elle ne dit rien de ce qui est monté."""
    if not sur_railway(env):
        return
    present = point_de_montage_present(mountinfo)
    if present is None:
        raise Refus(f"{mountinfo} est illisible : impossible de vérifier que le volume du service est "
                    f"monté sur {POINT_DE_MONTAGE}.")
    if not present:
        raise Refus(f"sur Railway, {POINT_DE_MONTAGE} n'est pas un point de montage ({mountinfo}) : sans "
                    "volume, Hermes tournerait sur un disque éphémère et perdrait tout au redéploiement. "
                    "Attachez le volume du service sur /opt/data.")


def commit_deploye(env: Mapping[str, str]) -> Optional[str]:
    """RAILWAY_GIT_COMMIT_SHA (rw/variables_reference.md:59) s'il a la forme d'un SHA git, sinon
    None : une valeur inattendue n'est jamais recopiée dans les journaux."""
    valeur = env.get("RAILWAY_GIT_COMMIT_SHA", "")
    return valeur if _SHA_COMMIT.fullmatch(valeur) else None


def verifier_environnement(env: Mapping[str, str]) -> ValeursDeploiement:
    """Contrôle complet de l'environnement du conteneur. Rassemble toutes les erreurs avant
    de refuser, pour qu'un seul redéploiement suffise à les corriger."""
    if "HERMES_MANAGED_DIR" in env:
        raise Refus(
            "la variable HERMES_MANAGED_DIR est interdite : "
            + VARIABLES_INTERDITES["HERMES_MANAGED_DIR"] + ". Retirez-la des variables Railway.")
    erreurs: List[str] = []
    for nom in sorted(env):
        raison = raison_interdiction(nom)
        if raison:
            erreurs.append(f"la variable {nom} est interdite : {raison}. Retirez-la des variables Railway.")
    for nom, (attendu, obligatoire) in VALEURS_IMPOSEES.items():
        if nom not in env:
            if obligatoire:
                erreurs.append(f"la variable {nom} manque ; l'image la fixe à « {attendu} ».")
            continue
        if env[nom] != attendu:
            erreurs.append(
                f"la variable {nom} vaut « {env[nom]} » ; seule la valeur « {attendu} » est admise.")
    if "PATH" in env:
        etrangers = [entree for entree in env["PATH"].split(":") if entree not in PATH_ADMIS]
        if etrangers:
            erreurs.append(
                "la variable PATH contient " + ", ".join(f"« {e} »" for e in etrangers)
                + " ; seuls les répertoires système de l'image sont admis ("
                + ":".join(PATH_ADMIS) + ") : un répertoire du volume ferait exécuter en root "
                "les binaires de l'agent.")
    # RAILWAY_RUN_UID fait tourner le conteneur sous un autre uid (rw/variables_reference.md) :
    # s6-overlay, les gardes et la reprise à root des répertoires exigent root.
    if "RAILWAY_RUN_UID" in env and env["RAILWAY_RUN_UID"] != "0":
        erreurs.append(
            f"la variable RAILWAY_RUN_UID vaut « {env['RAILWAY_RUN_UID']} » ; seule la valeur « 0 » "
            "(ou son absence) est admise : les gardes d'ACP et s6-overlay exigent root.")
    if sur_railway(env) and env.get("RAILWAY_VOLUME_MOUNT_PATH") != POINT_DE_MONTAGE:
        recu = env.get("RAILWAY_VOLUME_MOUNT_PATH")
        erreurs.append(
            f"sur Railway, le volume du service doit être monté sur {POINT_DE_MONTAGE} (reçu "
            f"« {recu if recu is not None else 'aucun volume'} ») : sans lui, Hermes tournerait sur "
            "un disque éphémère. Attachez le volume du service sur /opt/data.")

    def lire(nom: str, validateur: Callable[[str, str], str], *, defaut: Optional[str] = None) -> str:
        if nom not in env:
            if defaut is not None:
                return defaut
            erreurs.append(f"la variable {nom} est obligatoire et absente.")
            return ""
        try:
            return validateur(nom, env[nom])
        except Refus as exc:
            erreurs.append(str(exc))
            return ""

    url_publique = lire("HERMES_DASHBOARD_PUBLIC_URL", valider_url_https)
    emetteur = lire("HERMES_DASHBOARD_OIDC_ISSUER", valider_url_https)
    client = lire("HERMES_DASHBOARD_OIDC_CLIENT_ID", valider_client_id)
    portees = lire("HERMES_DASHBOARD_OIDC_SCOPES", valider_portees, defaut=PORTEES_PAR_DEFAUT)
    secret_fourni = "HERMES_DASHBOARD_OIDC_CLIENT_SECRET" in env
    if secret_fourni:
        secret = env["HERMES_DASHBOARD_OIDC_CLIENT_SECRET"]
        # Jamais affiché : seule sa forme est contrôlée.
        if not secret or len(secret) > 512 or any(c.isspace() or ord(c) < 32 for c in secret):
            erreurs.append(
                "la variable HERMES_DASHBOARD_OIDC_CLIENT_SECRET est vide, trop longue ou contient "
                "des espaces ; retirez-la pour un client public (PKCE seul) ou corrigez-la.")
    if erreurs:
        raise Refus("\n".join(erreurs))
    return ValeursDeploiement(url_publique=url_publique, oidc_emetteur=emetteur, oidc_client=client,
                              oidc_portees=portees, secret_client_fourni=secret_fourni)


# ---------------------------------------------------------------------------------------------
# Managed scope : /etc/hermes/config.yaml
# ---------------------------------------------------------------------------------------------

_MARQUEUR = re.compile(r'"@@ACP:([A-Z0-9_]+)@@"')

# Épingles de sécurité exigées dans la managed scope (clé pointée, valeur exacte).
EPINGLES_OBLIGATOIRES: Tuple[Tuple[str, Any], ...] = (
    ("kanban.auto_decompose", False),
    ("kanban.dispatch_profiles", ["default"]),
    ("approvals.mode", "manual"),
    ("approvals.cron_mode", "deny"),
    ("approvals.single_query_mode", "deny"),
    ("approvals.unattended_mode", "deny"),
    ("plugins.enabled", []),
    ("plugins.disabled", ["dashboard_auth/basic", "dashboard_auth/nous", "dashboard_auth/drain",
                          "hermes-achievements"]),
    ("plugins.allow_deprecated_imports", False),
    ("auth.adopt_external_logins", False),
    ("security.redact_secrets", True),
    ("security.allow_private_urls", False),
    ("security.allow_lazy_installs", False),
    ("display.language", "fr"),
    # Étape P2 : aucun outil d'exécution pour l'agent (docs/refonte/image.md §5).
    ("agent.disabled_toolsets", ["browser", "terminal", "file", "code_execution", "computer_use",
                                 "connections", "cronjob", "delegation", "setup"]),
    ("agent.coding_context", "off"),
    ("agent.service_tier", ""),
    ("platform_toolsets.api_server", ["web", "vision", "skills", "todo", "memory", "session_search", "no_mcp"]),
    ("platform_toolsets.cli", ["web", "vision", "skills", "todo", "memory", "session_search", "clarify",
                               "no_mcp"]),
    ("platform_toolsets.cron", ["web", "vision", "skills", "todo", "memory", "session_search", "no_mcp"]),
    ("skills.inline_shell", False),
    ("skills.write_approval", True),
    ("skills.guard_agent_created", True),
    ("memory.write_approval", True),
    ("hooks_auto_accept", False),
    ("dashboard.theme", "acp"),
    # Étape P3 : police du thème (aucune feuille de style distante) ; aucun greffon masqué.
    ("dashboard.font", "theme"),
    ("dashboard.hidden_plugins", []),
    ("dashboard.trusted_proxies", []),
    ("dashboard.oauth.client_id", ""),
    ("dashboard.oauth.portal_url", ""),
    ("dashboard.oauth.self_hosted.client_secret", ""),
    ("dashboard.basic_auth.username", ""),
    ("dashboard.basic_auth.password", ""),
    ("dashboard.basic_auth.password_hash", ""),
    ("dashboard.basic_auth.secret", ""),
    # api_server de la passerelle épinglé en boucle locale : l'agent ne peut pas le
    # déplacer sur 0.0.0.0 par /opt/data/config.yaml. La valeur de config.yaml gagne sinon
    # sur API_SERVER_HOST (gateway/platforms/api_server.py:209-218), et sans clé utilisable
    # dans l'environnement l'agent enrôle l'api_server directement par config.yaml
    # (gateway/config_env.py:307-315) : la managed scope, appliquée par-dessus la config du
    # volume (managed_scope.apply_managed_overlay), impose l'hôte et le port.
    ("platforms.api_server.extra.host", "127.0.0.1"),
    ("platforms.api_server.extra.port", 8642),
)

EPINGLES_DEPLOIEMENT: Dict[str, str] = {
    "dashboard.public_url": "HERMES_DASHBOARD_PUBLIC_URL",
    "dashboard.oauth.self_hosted.issuer": "HERMES_DASHBOARD_OIDC_ISSUER",
    "dashboard.oauth.self_hosted.client_id": "HERMES_DASHBOARD_OIDC_CLIENT_ID",
    "dashboard.oauth.self_hosted.scopes": "HERMES_DASHBOARD_OIDC_SCOPES",
}

_MOTS_SECRETS = ("secret", "password", "token", "api_key", "apikey", "private_key")


def charger_yaml(texte: str) -> Any:
    """Même chargeur que ``utils.fast_safe_load`` de Hermes (utils.py:613-615)."""
    chargeur = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    return yaml.load(texte, Loader=chargeur)


def _valeur_pointee(donnees: Any, cle: str) -> Tuple[bool, Any]:
    courant = donnees
    for morceau in cle.split("."):
        if not isinstance(courant, dict) or morceau not in courant:
            return False, None
        courant = courant[morceau]
    return True, courant


def _meme_valeur(obtenu: Any, attendu: Any) -> bool:
    """Égalité stricte, types compris (``false`` n'est pas ``0``, ``"0"`` n'est pas ``0``)."""
    if type(obtenu) is not type(attendu):
        return False
    if isinstance(attendu, list):
        return len(obtenu) == len(attendu) and all(_meme_valeur(a, b) for a, b in zip(obtenu, attendu))
    return obtenu == attendu


def cles_feuilles(donnees: Any, prefixe: str = "") -> List[str]:
    """Clés pointées des feuilles, comme ``managed_scope._flatten_keys`` (managed_scope.py:153-161)."""
    cles: List[str] = []
    if isinstance(donnees, dict):
        for cle, valeur in donnees.items():
            pointee = f"{prefixe}.{cle}" if prefixe else str(cle)
            if isinstance(valeur, dict) and valeur:
                cles.extend(cles_feuilles(valeur, pointee))
            else:
                cles.append(pointee)
    return sorted(cles)


def verifier_config_geree(donnees: Any, valeurs: ValeursDeploiement) -> None:
    """Refuse une managed scope incomplète, modifiée ou porteuse d'un secret."""
    if not isinstance(donnees, dict):
        raise Refus("le fichier géré doit contenir une table YAML à sa racine.")
    erreurs: List[str] = []
    for cle, attendu in EPINGLES_OBLIGATOIRES:
        present, obtenu = _valeur_pointee(donnees, cle)
        if not present:
            erreurs.append(f"l'épingle {cle} manque (attendu {json.dumps(attendu)}).")
        elif not _meme_valeur(obtenu, attendu):
            erreurs.append(f"l'épingle {cle} vaut {json.dumps(obtenu)}, attendu {json.dumps(attendu)}.")
    marqueurs = valeurs.marqueurs()
    for cle, nom in EPINGLES_DEPLOIEMENT.items():
        present, obtenu = _valeur_pointee(donnees, cle)
        if not present or not _meme_valeur(obtenu, marqueurs[nom]):
            erreurs.append(f"l'épingle {cle} ne reprend pas la variable {nom} validée.")
    for cle in cles_feuilles(donnees):
        feuille = cle.rsplit(".", 1)[-1].lower()
        _, valeur = _valeur_pointee(donnees, cle)
        if any(mot in feuille for mot in _MOTS_SECRETS) and isinstance(valeur, str) and valeur:
            erreurs.append(f"la clé {cle} porte une valeur : aucun secret n'est admis dans le fichier géré.")
    if erreurs:
        raise Refus("fichier géré refusé :\n" + "\n".join(f"  - {e}" for e in erreurs))


def generer_config_geree(modele: str, valeurs: ValeursDeploiement) -> str:
    """Remplace les marqueurs du modèle par les valeurs validées et vérifie le résultat."""
    marqueurs = valeurs.marqueurs()
    trouves = _MARQUEUR.findall(modele)
    if sorted(set(trouves)) != sorted(marqueurs) or len(trouves) != len(set(trouves)):
        raise Refus(
            "le modèle du fichier géré doit contenir exactement une fois chacun des marqueurs "
            + ", ".join(f"@@ACP:{n}@@" for n in sorted(marqueurs)) + ".")
    texte = _MARQUEUR.sub(lambda m: json.dumps(marqueurs[m.group(1)], ensure_ascii=False), modele)
    if "@@ACP:" in texte:
        raise Refus("le modèle du fichier géré contient un marqueur mal formé.")
    try:
        donnees = charger_yaml(texte)
    except yaml.YAMLError as exc:
        raise Refus(f"le fichier géré ne se lit pas comme du YAML : {exc}") from exc
    verifier_config_geree(donnees, valeurs)
    return texte


# ---------------------------------------------------------------------------------------------
# Managed scope : /etc/hermes/.env
# ---------------------------------------------------------------------------------------------

# Épinglées vides : le fournisseur correspondant ne peut pas être configuré par
# /opt/data/.env, chargé avec override=True (hermes_cli/env_loader.py:433-435) avant la
# managed scope, appliquée en dernier (env_loader.py:473 et 503-518).
ENV_VIDES: Tuple[str, ...] = (
    "HERMES_DASHBOARD_OAUTH_CLIENT_ID",
    "HERMES_DASHBOARD_PORTAL_URL",
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET",
    "HERMES_DASHBOARD_BASIC_AUTH_TTL_SECONDS",
    "HERMES_DASHBOARD_DRAIN_SECRET",
    # Greffons groupés épinglés sur /opt/hermes/plugins : une valeur vide fait retomber
    # get_bundled_plugins_dir sur le chemin de l'image (hermes_cli/plugins.py:68-75), donc un
    # HERMES_BUNDLED_PLUGINS posé dans /opt/data/.env est neutralisé (managed .env appliqué en
    # dernier, override=True : env_loader.py:473 et 503-518). Sans cette épingle, l'agent
    # ferait exécuter son propre code de greffon dans le tableau de bord et la passerelle.
    "HERMES_BUNDLED_PLUGINS",
    # Aucun mandataire : une valeur vide est ignorée par urllib et httpx
    # (urllib.request.getproxies_environment ne retient que les valeurs non vides).
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    # Étape P2 : une valeur vide vaut « non défini » pour chacune (outils de la discussion,
    # programme des workers kanban, crochets shell, mode sans greffon, approbation sans
    # demande, fournisseur copilot-acp). Posées dans /opt/data/.env, elles sont neutralisées.
    "HERMES_TUI_TOOLSETS",
    "HERMES_BIN",
    "HERMES_ACCEPT_HOOKS",
    "HERMES_SAFE_MODE",
    "HERMES_YOLO_MODE",
    "HERMES_COPILOT_ACP_COMMAND",
    "HERMES_COPILOT_ACP_ARGS",
    "COPILOT_CLI_PATH",
)

# Magasin de certificats du système (paquet ca-certificates de l'image officielle,
# Dockerfile:71-74). Épinglé à sa valeur réelle, JAMAIS vide : OpenSSL lit ces variables
# telles quelles, et une valeur vide le prive de toute autorité ; la récupération du JWKS
# par PyJWT (urllib) échouerait alors et plus personne ne pourrait se connecter (constaté
# dans l'image le 24 septembre 2026).
MAGASIN_CERTIFICATS = "/etc/ssl/certs/ca-certificates.crt"
REPERTOIRE_CERTIFICATS = "/etc/ssl/certs"

ENV_FIXES: Tuple[Tuple[str, str], ...] = (
    ("API_SERVER_HOST", "127.0.0.1"),
    ("API_SERVER_PORT", "8642"),
    ("HERMES_LANGUAGE", "fr"),
    # Aucun greffon de projet (./.hermes/plugins) : sans cette épingle, l'agent servirait
    # son propre JS au navigateur authentifié du propriétaire (web_server_dashboard.py:502-503 ;
    # plugins_discovery.py:187). « 0 » n'est pas une valeur vraie (utils.is_truthy_value).
    ("HERMES_ENABLE_PROJECT_PLUGINS", "0"),
    ("SSL_CERT_FILE", MAGASIN_CERTIFICATS),
    ("SSL_CERT_DIR", REPERTOIRE_CERTIFICATS),
    ("REQUESTS_CA_BUNDLE", MAGASIN_CERTIFICATS),
    ("CURL_CA_BUNDLE", MAGASIN_CERTIFICATS),
    # Étape P2. Seule protection effective contre les appels de l'agent vers le réseau privé
    # (api_server 8642, tableau de bord 9119) : tools/url_safety.py:145-173 lit cette variable
    # et config.yaml SANS la managed scope.
    ("HERMES_ALLOW_PRIVATE_URLS", "false"),
    # Aucune installation paresseuse de paquet (tools/lazy_deps.py:325-338) ; déjà dans l'ENV
    # de l'image officielle, épinglée ici contre /opt/data/.env.
    ("HERMES_DISABLE_LAZY_INSTALLS", "1"),
)


def valeurs_env_gere(valeurs: ValeursDeploiement, *, construction: bool = False) -> Dict[str, str]:
    """Contenu attendu de /etc/hermes/.env. Aucun secret : le fichier est lisible par tous."""
    contenu: Dict[str, str] = {}
    if not construction:
        contenu.update(valeurs.marqueurs())
    contenu.update(ENV_FIXES)
    for nom in ENV_VIDES:
        contenu[nom] = ""
    if not valeurs.secret_client_fourni:
        # Client public : un secret posé plus tard dans /opt/data/.env est neutralisé.
        contenu["HERMES_DASHBOARD_OIDC_CLIENT_SECRET"] = ""
    return contenu


def texte_env_gere(contenu: Mapping[str, str]) -> str:
    lignes = [
        "# Managed scope de Hermes pour ACP : régénéré à chaque démarrage (acp-gardes).",
        "# Appliqué en dernier, il gagne sur /opt/data/.env et sur l'environnement du conteneur.",
        "# Aucun secret ici : ce fichier est lisible par tous (0644).",
    ]
    for nom, valeur in contenu.items():
        if any(c in valeur for c in "'\n\r\\$#\"") or valeur != valeur.strip():
            raise Refus(f"valeur refusée pour {nom} dans le .env géré.")
        lignes.append(f"{nom}='{valeur}'" if valeur else f"{nom}=")
    return "\n".join(lignes) + "\n"


def relire_env(chemin: Path) -> Dict[str, Optional[str]]:
    """Relit un .env avec python-dotenv, l'analyseur que Hermes emploie (env_loader.py:284-287)."""
    from dotenv import dotenv_values

    return dict(dotenv_values(chemin, interpolate=False))


# ---------------------------------------------------------------------------------------------
# Variables interdites injectées dans /opt/data (défense contre l'agent)
# ---------------------------------------------------------------------------------------------

# /opt/data/.env est écrit par l'agent et Hermes le charge avec override=True AVANT la managed
# scope (env_loader.py:433-435 puis 473). Les variables neutres (greffons, mandataires…) sont
# épinglées à vide dans /etc/hermes/.env et gagnent donc. Mais HERMES_MANAGED_DIR, elle, choisit
# QUELLE managed scope est lue (managed_scope.py:52) : aucune épingle ne peut la contrer, puisque
# la managed .env qui la contrerait n'est plus consultée. On refuse donc, au démarrage ET à chaque
# relance des services, toute variable de cette liste trouvée dans /opt/data/.env (et profiles/*/.env).
#
# La liste est étroite À DESSEIN : elle ne contient QUE des variables qui font échapper l'agent à la
# managed scope ou lui font exécuter du code, et que Hermes n'écrit JAMAIS lui-même dans un .env du
# volume. En particulier, API_SERVER_KEY est exclue : l'image la génère et l'écrit dans
# /opt/data/.env à chaque démarrage (docker/stage2-hook.sh:504-540) ; la refuser bloquerait tout
# démarrage. HERMES_BUNDLED_PLUGINS et HERMES_ENABLE_PROJECT_PLUGINS sont déjà épinglées dans la
# managed .env (neutralisées) ; les refuser ici est une défense en profondeur, échec fermé.
VARIABLES_VOLUME_INTERDITES: Dict[str, str] = {
    "HERMES_MANAGED_DIR": (
        "elle déplacerait la portée gérée hors de /etc/hermes (managed_scope.py:45-59) ; "
        "aucune épingle ne peut la contrer, puisque c'est elle qui choisit le .env géré lu"),
    "HERMES_BUNDLED_PLUGINS": (
        "elle ferait charger le code de greffon de l'agent dans le tableau de bord et la passerelle "
        "(hermes_cli/plugins.py:68-75)"),
    "HERMES_ENABLE_PROJECT_PLUGINS": (
        "elle servirait le JS de l'agent au navigateur authentifié du propriétaire "
        "(web_server_dashboard.py:502-503)"),
}


def fichiers_env_du_volume(chemins: Chemins) -> List[Path]:
    """Fichiers .env lus par Hermes sur le volume : racine et un par profil."""
    fichiers = [chemins.hermes_home / ".env"]
    profils = chemins.hermes_home / "profiles"
    try:
        entrees = sorted(profils.iterdir())
    except OSError:
        entrees = []
    for entree in entrees:
        try:
            st = os.lstat(entree)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode):
            fichiers.append(entree / ".env")
    return fichiers


def _relire_env_sans_lien(chemin: Path) -> Dict[str, Optional[str]]:
    """Analyse un .env sans suivre de lien symbolique, avec l'analyseur de Hermes."""
    import io

    from dotenv import dotenv_values

    donnees = lire_sans_lien(chemin)
    if donnees is None:
        return {}
    texte = donnees.decode("utf-8", errors="replace")
    return dict(dotenv_values(stream=io.StringIO(texte), interpolate=False))


def variables_interdites_dans_le_volume(chemins: Chemins) -> List[Tuple[Path, str, str]]:
    """(fichier, variable, raison) pour chaque variable de VARIABLES_VOLUME_INTERDITES posée dans un
    .env du volume."""
    trouvees: List[Tuple[Path, str, str]] = []
    for fichier in fichiers_env_du_volume(chemins):
        try:
            valeurs = _relire_env_sans_lien(fichier)
        except Refus:
            # Un lien symbolique ou un fichier spécial à la place d'un .env est déjà suspect.
            trouvees.append((fichier, "(fichier)", "n'est pas un fichier ordinaire"))
            continue
        for nom in sorted(valeurs):
            raison = VARIABLES_VOLUME_INTERDITES.get(nom)
            if raison:
                trouvees.append((fichier, nom, raison))
    return trouvees


def refuser_variables_du_volume(chemins: Chemins) -> None:
    """Lève :class:`Refus` si un .env du volume porte une variable interdite."""
    trouvees = variables_interdites_dans_le_volume(chemins)
    if trouvees:
        lignes = [f"{fichier} définit la variable interdite {nom} : {raison}."
                  for fichier, nom, raison in trouvees]
        raise Refus(
            "des variables interdites ont été injectées dans le volume (/opt/data) ; "
            "elles échapperaient à la managed scope :\n" + "\n".join(f"  - {l}" for l in lignes)
            + "\nSupprimez-les de ces fichiers avant de redémarrer.")


# ---------------------------------------------------------------------------------------------
# Reprise à root des services s6 (empêche l'élévation par /run/service)
# ---------------------------------------------------------------------------------------------

# L'image officielle rend /run/service et les emplacements de service des passerelles propriété de
# l'agent (docker/cont-init.d/02-reconcile-profiles:119 ; docker/cont-init.d/015-supervise-perms).
# Or s6-supervise tourne en root (spawné par s6-svscan en PID 1) : un service que l'agent crée là,
# ou un script `run` qu'il réécrit, est exécuté EN ROOT avant de retomber sous l'uid hermes
# (hermes_cli/container_boot.py:291 ; service_manager.py:_render_run_script). On reprend donc à
# root le répertoire de services (l'agent ne peut plus y créer de service) et, pour chaque
# passerelle dynamique, son répertoire et ses scripts ; on ne laisse à l'agent que la FIFO
# supervise/control, pour qu'il puisse encore relancer la passerelle par `s6-svc -r`.

_SERVICES_S6_INTERNES = {".s6-svscan", "s6-linux-init-shutdownd"}
_PREFIXE_PASSERELLE = "gateway-"
_MARQUEUR_RUN_ACP = "# acp-garde-relance"


def _fchown_fchmod(fd: int, mode: int) -> None:
    os.fchown(fd, 0, 0)
    os.fchmod(fd, mode)


def _reprendre_fichier(fd_parent: int, nom: str, *, mode: int) -> None:
    """Rend un fichier ordinaire root:root sans suivre de lien ; ignore ce qui n'existe pas."""
    try:
        st = os.lstat(nom, dir_fd=fd_parent)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(st.st_mode):
        return
    fd = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd_parent)
    try:
        _fchown_fchmod(fd, mode)
    finally:
        os.close(fd)


def _reprendre_repertoire(fd_parent: int, nom: str, *, mode: int = 0o755) -> None:
    """Rend un sous-répertoire root:root 0755 sans suivre de lien ; ignore ce qui n'existe pas."""
    try:
        st = os.lstat(nom, dir_fd=fd_parent)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(st.st_mode):
        return
    fd = os.open(nom, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd_parent)
    try:
        _fchown_fchmod(fd, mode)
    finally:
        os.close(fd)


def _envelopper_run_passerelle(svc: Path) -> bool:
    """Enveloppe le script `run` d'une passerelle (déjà repris par root) d'une garde ACP qui refuse
    la relance si un .env du volume porte une variable interdite. Idempotent."""
    contenu = lire_sans_lien(svc / "run")
    if contenu is None:
        return False
    lignes = contenu.split(b"\n", 2)
    if len(lignes) >= 2 and lignes[1].strip() == _MARQUEUR_RUN_ACP.encode("utf-8"):
        return False  # déjà enveloppé : ne pas ré-envelopper ni écraser l'amont sauvé
    # Le reconciler reconstruit tout le répertoire à chaque démarrage (container_boot:310-312),
    # donc `run` est toujours le script amont ici : on le sauve puis on installe l'enveloppe.
    ecrire_atomique(svc / ".acp-amont-run", contenu, mode=0o755, uid=0, gid=0)
    enveloppe = (
        "#!/command/with-contenv /bin/sh\n"
        f"{_MARQUEUR_RUN_ACP}\n"
        "# Vérifie /opt/data/.env avant de relancer la passerelle amont (correctif P1).\n"
        "/opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py verifier-relance "
        "|| { /bin/sleep 5; exit 1; }\n"
        f"exec /command/with-contenv /bin/sh {svc / '.acp-amont-run'}\n"
    ).encode("utf-8")
    ecrire_atomique(svc / "run", enveloppe, mode=0o755, uid=0, gid=0)
    return True


def reprendre_service_passerelle(scandir: Path, nom: str) -> None:
    """Reprend à root une passerelle dynamique ; laisse la FIFO supervise/control à l'agent."""
    svc = scandir / nom
    fd_svc = os.open(svc, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _fchown_fchmod(fd_svc, 0o755)
        _reprendre_fichier(fd_svc, "run", mode=0o755)
        _reprendre_fichier(fd_svc, "finish", mode=0o755)
        _reprendre_fichier(fd_svc, "type", mode=0o644)
        _reprendre_repertoire(fd_svc, "supervise")
        # Sous-service log : run root aussi (exécuté en root avant de retomber sous hermes).
        try:
            fd_log = os.open("log", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd_svc)
        except FileNotFoundError:
            fd_log = None
        if fd_log is not None:
            try:
                _fchown_fchmod(fd_log, 0o755)
                _reprendre_fichier(fd_log, "run", mode=0o755)
                _reprendre_repertoire(fd_log, "supervise")
            finally:
                os.close(fd_log)
    finally:
        os.close(fd_svc)
    _envelopper_run_passerelle(svc)


def reprendre_services_s6(scandir: Path = Path("/run/service")) -> Dict[str, Any]:
    """Reprend à root le répertoire de services s6 et les passerelles dynamiques.

    Renvoie un résumé pour l'état du démarrage. Hors de s6 (répertoire absent), ne fait rien."""
    resume: Dict[str, Any] = {"present": False, "passerelles": []}
    try:
        st = os.lstat(scandir)
    except FileNotFoundError:
        return resume
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise Refus(f"{scandir} n'est pas un répertoire réel : démarrage refusé.")
    resume["present"] = True
    fd_scandir = os.open(scandir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        passerelles: List[str] = []
        for nom in sorted(os.listdir(fd_scandir)):
            if nom in _SERVICES_S6_INTERNES:
                continue
            st_e = os.lstat(nom, dir_fd=fd_scandir)
            # Les services statiques (dashboard, main-hermes) sont des liens vers des
            # servicedirs déjà root : on ne les suit pas. Seules les passerelles dynamiques
            # sont de vrais répertoires que l'agent possède.
            if stat.S_ISLNK(st_e.st_mode) or not stat.S_ISDIR(st_e.st_mode):
                continue
            if not nom.startswith(_PREFIXE_PASSERELLE):
                continue
            reprendre_service_passerelle(scandir, nom)
            passerelles.append(nom)
        # Le répertoire lui-même en dernier : l'agent ne peut plus y créer de service supervisé.
        _fchown_fchmod(fd_scandir, 0o755)
        resume["passerelles"] = passerelles
    finally:
        os.close(fd_scandir)
    return resume


# ---------------------------------------------------------------------------------------------
# Écritures sûres
# ---------------------------------------------------------------------------------------------


def empreinte(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def ecrire_atomique(chemin: Path, contenu: bytes, *, mode: int, uid: int, gid: int) -> None:
    """Écrit dans un fichier temporaire du même répertoire puis le renomme : jamais d'écriture
    à travers un lien symbolique, jamais de fichier à moitié écrit."""
    descripteur, temporaire = tempfile.mkstemp(prefix=f".{chemin.name}.", dir=chemin.parent)
    try:
        with os.fdopen(descripteur, "wb") as flux:
            flux.write(contenu)
            flux.flush()
            os.fchmod(flux.fileno(), mode)
            os.fchown(flux.fileno(), uid, gid)
            os.fsync(flux.fileno())
        os.replace(temporaire, chemin)
    except BaseException:
        try:
            os.unlink(temporaire)
        except FileNotFoundError:
            pass
        raise


def lire_sans_lien(chemin: Path, *, limite: int = 4 * 1024 * 1024) -> Optional[bytes]:
    """Contenu d'un fichier ordinaire, sans suivre de lien symbolique ; None s'il est absent."""
    try:
        fd = os.open(chemin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise Refus(f"{chemin} ne peut pas être lu sans suivre de lien : {exc.strerror}.") from exc
    with os.fdopen(fd, "rb") as flux:
        if not stat.S_ISREG(os.fstat(flux.fileno()).st_mode):
            raise Refus(f"{chemin} n'est pas un fichier ordinaire.")
        donnees = flux.read(limite + 1)
    if len(donnees) > limite:
        raise Refus(f"{chemin} dépasse {limite} octets.")
    return donnees


def assurer_repertoire_root(chemin: Path) -> None:
    """Crée ou vérifie un répertoire réel (pas un lien) ; le rend root:root 0755."""
    try:
        st = os.lstat(chemin)
    except FileNotFoundError:
        os.mkdir(chemin, 0o755)
        st = os.lstat(chemin)
    if stat.S_ISLNK(st.st_mode):
        raise Refus(f"{chemin} est un lien symbolique ; démarrage refusé (supprimez le lien).")
    if not stat.S_ISDIR(st.st_mode):
        raise Refus(f"{chemin} existe mais n'est pas un répertoire.")
    fd = os.open(chemin, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o755)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------------------------
# Commande « construire » et « gardes » : managed scope
# ---------------------------------------------------------------------------------------------


def verifier_magasin_certificats(chemin: Path = Path(MAGASIN_CERTIFICATS)) -> None:
    """Le magasin épinglé doit exister, appartenir à root et contenir des certificats."""
    try:
        st = os.stat(chemin)
    except FileNotFoundError as exc:
        raise Refus(f"le magasin de certificats {chemin} est absent : l'image est incomplète.") from exc
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022 or st.st_size < 1024:
        raise Refus(f"le magasin de certificats {chemin} doit être un fichier non vide de root.")


def verifier_dossier_gere(dossier: Path) -> None:
    try:
        st = os.lstat(dossier)
    except FileNotFoundError as exc:
        raise Refus(f"{dossier} n'existe pas : l'image est incomplète.") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise Refus(f"{dossier} doit être un répertoire réel.")
    if st.st_uid != 0 or st.st_mode & 0o022:
        raise Refus(f"{dossier} doit appartenir à root et n'être inscriptible que par lui.")


@dataclass(frozen=True)
class ScopeGeree:
    """Contenu attendu de la managed scope pour des valeurs de déploiement données."""

    config: bytes
    env: Dict[str, str]
    texte_env: bytes

    def resume(self) -> Dict[str, Any]:
        return {
            "config_sha256": empreinte(self.config),
            "env_sha256": empreinte(self.texte_env),
            "cles_config": cles_feuilles(charger_yaml(self.config.decode("utf-8"))),
            "cles_env": sorted(self.env),
        }


def preparer_scope_geree(chemins: Chemins, valeurs: ValeursDeploiement, *, construction: bool = False
                         ) -> ScopeGeree:
    """Génère en mémoire /etc/hermes/config.yaml et /etc/hermes/.env et les vérifie."""
    try:
        modele = chemins.modele_gere.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refus(f"le modèle {chemins.modele_gere} ne se lit pas : {exc}.") from exc
    try:
        texte = generer_config_geree(modele, valeurs)
    except Refus as exc:
        raise Refus(f"le modèle {chemins.modele_gere} est invalide ; {exc}") from exc
    env = valeurs_env_gere(valeurs, construction=construction)
    return ScopeGeree(config=texte.encode("utf-8"), env=env, texte_env=texte_env_gere(env).encode("utf-8"))


def verifier_scope_installee(chemins: Chemins, attendue: ScopeGeree, valeurs: ValeursDeploiement) -> None:
    """Relit ce qui est réellement installé : un fichier géré qui ne se relirait pas serait
    ignoré en silence par Hermes (managed_scope.py:86-93)."""
    verifier_dossier_gere(chemins.dossier_gere)
    config = chemins.dossier_gere / "config.yaml"
    fichier_env = chemins.dossier_gere / ".env"
    for fichier in (config, fichier_env):
        st = os.lstat(fichier) if fichier.exists() or fichier.is_symlink() else None
        if st is None:
            raise Refus(f"{fichier} est absent : la managed scope n'a pas été régénérée "
                        "(le crochet S6_STAGE2_HOOK a-t-il été retiré ?).")
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise Refus(f"{fichier} doit être un fichier ordinaire de root, non inscriptible par l'agent.")
    installe = lire_sans_lien(config)
    if installe != attendue.config:
        raise Refus(f"{config} ne correspond pas aux variables de ce démarrage "
                    "(le crochet S6_STAGE2_HOOK a-t-il été retiré ?).")
    try:
        verifier_config_geree(charger_yaml(installe.decode("utf-8")), valeurs)
    except yaml.YAMLError as exc:
        raise Refus(f"{config} installé ne se relit pas : {exc}") from exc
    if lire_sans_lien(fichier_env) != attendue.texte_env or relire_env(fichier_env) != dict(attendue.env):
        raise Refus(f"{fichier_env} ne correspond pas aux valeurs attendues.")


def installer_scope_geree(chemins: Chemins, valeurs: ValeursDeploiement, *, construction: bool = False
                          ) -> Dict[str, Any]:
    """Génère, écrit (root 0644, écriture atomique) et relit la managed scope."""
    attendue = preparer_scope_geree(chemins, valeurs, construction=construction)
    verifier_magasin_certificats()
    verifier_dossier_gere(chemins.dossier_gere)
    ecrire_atomique(chemins.dossier_gere / "config.yaml", attendue.config, mode=0o644, uid=0, gid=0)
    ecrire_atomique(chemins.dossier_gere / ".env", attendue.texte_env, mode=0o644, uid=0, gid=0)
    verifier_scope_installee(chemins, attendue, valeurs)
    return attendue.resume()


# ---------------------------------------------------------------------------------------------
# Commande « donnees » : greffons, thèmes, SOUL
# ---------------------------------------------------------------------------------------------

_FICHIERS_MANIFESTE = {"plugin.yaml", "plugin.yml", "plugin.json"}
_MAX_ENTREES = 20000


def est_nom_reserve(nom: Any) -> bool:
    texte = str(nom).strip().casefold()
    return texte == "acp" or texte.startswith("acp-") or texte.startswith("acp_")


@dataclass
class Inspection:
    """Ce que contient une arborescence de /opt/data (greffons ou thèmes)."""

    entrees: int = 0
    dossiers_premier_niveau: List[str] = field(default_factory=list)
    noms_declares: List[Tuple[str, str]] = field(default_factory=list)  # (chemin relatif, nom)
    illisibles: List[str] = field(default_factory=list)


def _nom_manifeste(relatif: str, contenu: bytes) -> Tuple[Optional[Any], bool]:
    """Nom déclaré par un manifeste ; (None, False) s'il est illisible. Hermes prend le nom du
    dossier quand ``name`` manque (plugins_manifest.py:505 ; web_server_dashboard.py:568)."""
    morceaux = relatif.split("/")
    if morceaux[-1] == "manifest.json":
        defaut = morceaux[-3] if len(morceaux) >= 3 else ""
    else:
        defaut = morceaux[-2] if len(morceaux) >= 2 else ""
    try:
        texte = contenu.decode("utf-8")
        donnees = json.loads(texte) if relatif.endswith(".json") else charger_yaml(texte)
    except (UnicodeDecodeError, ValueError, yaml.YAMLError):
        return None, False
    if not isinstance(donnees, dict):
        return None, False
    return donnees.get("name", defaut), True


def _nom_theme(contenu: bytes) -> Optional[str]:
    try:
        donnees = charger_yaml(contenu.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return None
    if isinstance(donnees, dict) and isinstance(donnees.get("name"), str):
        return donnees["name"]
    return None


def inspecter(racine: Path, *, themes_livres: Optional[Iterable[str]] = None) -> Inspection:
    """Parcourt une arborescence sans suivre aucun lien. Refuse un lien symbolique, un fichier
    spécial, un nom réservé ``acp-*`` (nom de dossier ou nom déclaré par un manifeste).

    Avec ``themes_livres`` (répertoire des thèmes), refuse aussi un fichier ``*.yaml`` de
    premier niveau qui déclare un thème ``acp…`` sans être l'un des fichiers livrés : Hermes
    relit ce répertoire à chaque requête (web_server_dashboard.py:414-432) et un homonyme
    pourrait maquiller le thème épinglé."""
    livres = set(themes_livres) if themes_livres is not None else None
    resultat = Inspection()
    try:
        st = os.lstat(racine)
    except FileNotFoundError:
        return resultat
    if stat.S_ISLNK(st.st_mode):
        raise Refus(f"{racine} est un lien symbolique ; démarrage refusé (supprimez le lien).")
    if not stat.S_ISDIR(st.st_mode):
        raise Refus(f"{racine} existe mais n'est pas un répertoire.")

    def visiter(fd: int, relatif: str) -> None:
        for nom in sorted(os.listdir(fd)):
            resultat.entrees += 1
            if resultat.entrees > _MAX_ENTREES:
                raise Refus(f"{racine} contient plus de {_MAX_ENTREES} entrées ; démarrage refusé.")
            chemin_rel = f"{relatif}/{nom}" if relatif else nom
            st_e = os.lstat(nom, dir_fd=fd)
            if stat.S_ISLNK(st_e.st_mode):
                raise Refus(f"{racine}/{chemin_rel} est un lien symbolique ; démarrage refusé.")
            # Hermes tire le nom d'un greffon de son dossier (premier ou second niveau :
            # plugins_discovery.py:109-161) ; plus bas, un nom de fichier ne compte pas.
            profondeur = chemin_rel.count("/") + 1
            if est_nom_reserve(nom) and (profondeur == 1 or (stat.S_ISDIR(st_e.st_mode) and profondeur <= 2)):
                raise Refus(
                    f"{racine}/{chemin_rel} porte un nom réservé à ACP ; un greffon utilisateur ne "
                    "peut pas se faire passer pour acp-poste ou acp-interface. Supprimez-le.")
            if stat.S_ISDIR(st_e.st_mode):
                if not relatif:
                    resultat.dossiers_premier_niveau.append(nom)
                enfant = os.open(nom, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    visiter(enfant, chemin_rel)
                finally:
                    os.close(enfant)
            elif stat.S_ISREG(st_e.st_mode):
                if livres is not None and not relatif and nom.endswith(".yaml") and nom not in livres:
                    fichier = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    with os.fdopen(fichier, "rb") as flux:
                        declare_theme = _nom_theme(flux.read(1024 * 1024 + 1))
                    if declare_theme is not None and declare_theme.strip().casefold().startswith("acp"):
                        raise Refus(
                            f"le thème {racine}/{chemin_rel} déclare le nom réservé « {declare_theme} » ; "
                            "seul le thème livré par l'image peut porter ce nom. Supprimez-le.")
                    continue
                est_manifeste = nom in _FICHIERS_MANIFESTE or (
                    nom == "manifest.json" and relatif.split("/")[-1] == "dashboard")
                if est_manifeste:
                    fichier = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    with os.fdopen(fichier, "rb") as flux:
                        contenu = flux.read(1024 * 1024 + 1)
                    declare, lisible = _nom_manifeste(chemin_rel, contenu)
                    if not lisible:
                        resultat.illisibles.append(chemin_rel)
                        continue
                    resultat.noms_declares.append((chemin_rel, str(declare)))
                    if est_nom_reserve(declare):
                        raise Refus(
                            f"le manifeste {racine}/{chemin_rel} déclare le nom réservé "
                            f"« {declare} » ; un greffon utilisateur ne peut pas se faire passer "
                            "pour un greffon d'ACP. Supprimez-le.")
            else:
                raise Refus(f"{racine}/{chemin_rel} est un fichier spécial ; démarrage refusé.")

    fd_racine = os.open(racine, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        visiter(fd_racine, "")
    finally:
        os.close(fd_racine)
    return resultat


def verrouiller(racine: Path) -> None:
    """Rend une arborescence propriété de root : répertoires 0755, fichiers 0644. Travaille par
    descripteurs (O_NOFOLLOW) : un lien apparu entre-temps fait refuser, jamais suivre."""
    assurer_repertoire_root(racine)

    def traiter(fd: int, relatif: str) -> None:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o755)
        for nom in os.listdir(fd):
            chemin_rel = f"{relatif}/{nom}" if relatif else nom
            st_e = os.lstat(nom, dir_fd=fd)
            if stat.S_ISDIR(st_e.st_mode):
                enfant = os.open(nom, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    traiter(enfant, chemin_rel)
                finally:
                    os.close(enfant)
            elif stat.S_ISREG(st_e.st_mode):
                fichier = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    os.fchown(fichier, 0, 0)
                    os.fchmod(fichier, 0o644)
                finally:
                    os.close(fichier)
            else:
                raise Refus(f"{racine}/{chemin_rel} n'est ni un répertoire ni un fichier ordinaire.")

    fd_racine = os.open(racine, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        traiter(fd_racine, "")
    finally:
        os.close(fd_racine)


def deposer_theme(source: Path, destination: Path) -> List[str]:
    """Copie les thèmes livrés (``*.yaml``) dans le répertoire root des thèmes, root 0644."""
    deposes: List[str] = []
    for fichier in sorted(source.glob("*.yaml")):
        contenu = fichier.read_bytes()
        try:
            donnees = charger_yaml(contenu.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise Refus(f"le thème livré {fichier} ne se lit pas : {exc}") from exc
        if not isinstance(donnees, dict) or not isinstance(donnees.get("name"), str):
            raise Refus(f"le thème livré {fichier} n'a pas de champ « name ».")
        cible = destination / fichier.name
        if lire_sans_lien(cible) != contenu:
            ecrire_atomique(cible, contenu, mode=0o644, uid=0, gid=0)
        deposes.append(fichier.name)
    return deposes


def gerer_soul(chemins: Chemins, *, uid: int, gid: int) -> Dict[str, Any]:
    """Dépose le SOUL.md livré si le propriétaire n'a pas modifié celui du volume.

    Le fichier est remplacé seulement s'il est absent, identique au SOUL de l'image
    officielle (semé par stage2-hook.sh:457) ou identique à la dernière version déposée par
    ACP (empreinte dans /opt/data/acp/soul.sha256). Sinon il est laissé tel quel et signalé
    comme divergent dans l'état du démarrage (route /v1/meta)."""
    cible = chemins.hermes_home / "SOUL.md"
    marqueur = chemins.donnees_acp / "soul.sha256"
    livre = chemins.soul_livre.read_bytes()
    h_livre = empreinte(livre)
    amont = chemins.soul_amont.read_bytes() if chemins.soul_amont.is_file() else None
    h_amont = empreinte(amont) if amont is not None else None
    try:
        st = os.lstat(cible)
    except FileNotFoundError:
        st = None
    if st is not None and not stat.S_ISREG(st.st_mode):
        return {"etat": "non_ordinaire", "empreinte_livree": h_livre, "empreinte_actuelle": None,
                "detail": "SOUL.md n'est pas un fichier ordinaire (lien symbolique ?) : laissé tel quel."}
    actuel = lire_sans_lien(cible) if st is not None else None
    h_actuel = empreinte(actuel) if actuel is not None else None
    h_marqueur: Optional[str] = None
    brut = lire_sans_lien(marqueur)
    if brut is not None:
        texte = brut.decode("ascii", errors="replace").strip()
        h_marqueur = texte if _EMPREINTE.match(texte) else None

    if h_actuel is not None and h_actuel == h_livre:
        etat = "a_jour"
    elif h_actuel is None or h_actuel == h_amont or (h_marqueur is not None and h_actuel == h_marqueur):
        ecrire_atomique(cible, livre, mode=0o644, uid=uid, gid=gid)
        etat = "depose"
        h_actuel = h_livre
    else:
        return {"etat": "divergent", "empreinte_livree": h_livre, "empreinte_actuelle": h_actuel,
                "detail": "SOUL.md a été modifié par le propriétaire : la persona livrée n'est pas appliquée."}
    ecrire_atomique(marqueur, (h_livre + "\n").encode("ascii"), mode=0o644, uid=0, gid=0)
    return {"etat": etat, "empreinte_livree": h_livre, "empreinte_actuelle": h_actuel, "detail": None}


def themes_livres(chemins: Chemins) -> List[str]:
    return sorted(f.name for f in chemins.theme_livre.glob("*.yaml"))


def inspecter_donnees(chemins: Chemins) -> Inspection:
    """Inspection en lecture seule des répertoires de /opt/data que protège ACP."""
    greffons = inspecter(chemins.greffons_utilisateur)
    inspecter(chemins.themes, themes_livres=themes_livres(chemins))
    inspecter(chemins.donnees_acp)
    return greffons


# ---------------------------------------------------------------------------------------------
# hooks/ et scripts/ de /opt/data et de chaque profil, /opt/data/lazy-packages (étape P2)
# ---------------------------------------------------------------------------------------------

# Répertoires du volume dont le contenu est EXÉCUTÉ par Hermes. Ils doivent rester vides : sur
# Railway, rien de légitime n'y est déposé (l'agent n'a plus d'outil fichier) ; une entrée ne
# peut venir que d'une ancienne injection ou d'une sauvegarde restaurée.
REPERTOIRES_EXECUTES: Tuple[Tuple[str, str], ...] = (
    ("crochets_passerelle",
     "la passerelle y importe chaque handler.py sans demander de consentement (gateway/hooks.py:44-72)"),
    ("scripts_cron",
     "les tâches cron y exécutent leurs scripts (cron/scheduler_script.py:257-320)"),
)

# Les MÊMES répertoires dans chaque profil de /opt/data/profiles (correction de la relecture P2).
# Une seule passerelle sert tous les profils (hermes_cli/container_boot.py:100-110 ;
# hermes_cli/profiles.py:1050-1075) : elle exécute les scripts cron du scripts/ PROPRE au profil
# (cron/scheduler_script.py:257-298, chemin résolu sous le HERMES_HOME du profil) et charge les
# crochets de son hooks/ (gateway/hooks.py:28-35). Mesuré sur 21eeb5d : un script cron de
# profiles/<nom>/scripts tournait sous l'uid 10000 sans aucun refus.
REPERTOIRES_EXECUTES_PAR_PROFIL: Tuple[Tuple[str, str], ...] = (
    ("hooks", "la passerelle y importe chaque handler.py du profil sans demander de consentement "
              "(gateway/hooks.py:28-72)"),
    ("scripts", "les tâches cron du profil y exécutent leurs scripts (cron/scheduler_script.py:257-298)"),
)

# Fichiers de service d'une cible d'installation paresseuse (tools/lazy_deps.py:248-285).
_FICHIERS_LAZY_ADMIS = {".lock", ".python-abi"}


def entrees_du_repertoire(racine: Path) -> Optional[List[str]]:
    """Noms des entrées d'un répertoire, sans suivre de lien ; None s'il est absent. Refuse un
    lien symbolique ou autre chose qu'un répertoire à la place de ``racine``."""
    try:
        st = os.lstat(racine)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        raise Refus(f"{racine} est un lien symbolique ; démarrage refusé (supprimez le lien).")
    if not stat.S_ISDIR(st.st_mode):
        raise Refus(f"{racine} existe mais n'est pas un répertoire.")
    fd = os.open(racine, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return sorted(os.listdir(fd))
    finally:
        os.close(fd)


def _affichable(nom: str, limite: int = 80) -> str:
    return "".join(c for c in nom if c.isprintable())[:limite]


def profils_du_volume(chemins: Chemins) -> Tuple[List[Path], List[str]]:
    """(répertoires des profils, problèmes) sous /opt/data/profiles, SANS suivre de lien.

    Hermes tient pour profil tout répertoire de ``profiles/`` (hermes_cli/profiles.py:349-366,
    ``is_dir()`` suit les liens) : un lien symbolique y ferait exécuter les ``hooks/`` et
    ``scripts/`` de sa cible, il est donc refusé. Tout répertoire réel est examiné, même sans
    marqueur d'identité (plus strict que Hermes)."""
    racine = chemins.hermes_home / "profiles"
    try:
        noms = entrees_du_repertoire(racine)
    except Refus as exc:
        return [], [str(exc)]
    profils: List[Path] = []
    problemes: List[str] = []
    for nom in noms or []:
        chemin = racine / nom
        try:
            st = os.lstat(chemin)
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            problemes.append(
                f"{racine}/{_affichable(nom)} est un lien symbolique : Hermes le prendrait pour un profil "
                "et exécuterait les hooks/ et scripts/ de sa cible ; démarrage refusé (supprimez le lien).")
        elif stat.S_ISDIR(st.st_mode):
            profils.append(chemin)
    return profils, problemes


def repertoires_executes(chemins: Chemins) -> Tuple[List[Tuple[Path, str]], List[str]]:
    """((répertoire exécuté, raison), problèmes) : ceux de la racine, puis ceux de chaque profil."""
    liste: List[Tuple[Path, str]] = [(getattr(chemins, attribut), raison)
                                     for attribut, raison in REPERTOIRES_EXECUTES]
    profils, problemes = profils_du_volume(chemins)
    for profil in profils:
        liste.extend((profil / sous, raison) for sous, raison in REPERTOIRES_EXECUTES_PAR_PROFIL)
    return liste, problemes


def problemes_repertoires_executes(chemins: Chemins) -> List[str]:
    """Une ligne par répertoire exécuté qui n'est pas vide (ou qui n'est pas un répertoire), à la
    racine du volume comme dans chaque profil, et par lien symbolique sous ``profiles/``."""
    repertoires, problemes = repertoires_executes(chemins)
    for racine, raison in repertoires:
        try:
            entrees = entrees_du_repertoire(racine)
        except Refus as exc:
            problemes.append(str(exc))
            continue
        if entrees:
            montre = ", ".join(f"« {_affichable(n)} »" for n in entrees[:20])
            reste = f" et {len(entrees) - 20} autre(s)" if len(entrees) > 20 else ""
            problemes.append(
                f"{racine} n'est pas vide ({montre}{reste}) : {raison}. Ce répertoire doit rester vide sur "
                "Railway ; supprimez ces entrées (maintenance : docs/refonte/railway.md §10).")
    return problemes


def refuser_repertoires_executes(chemins: Chemins) -> None:
    problemes = problemes_repertoires_executes(chemins)
    if problemes:
        raise Refus("\n".join(problemes))


def contenu_paquets_paresseux(chemins: Chemins) -> Optional[List[str]]:
    """Entrées de /opt/data/lazy-packages hors fichiers de service ; None si le répertoire est
    absent ou illisible sans suivre de lien."""
    try:
        entrees = entrees_du_repertoire(chemins.paquets_paresseux)
    except Refus:
        return None
    if entrees is None:
        return None
    return [n for n in entrees if n not in _FICHIERS_LAZY_ADMIS]


def preparer_donnees(chemins: Chemins, scope: ScopeGeree, *, uid: int, gid: int,
                     commit: Optional[str] = None) -> Dict[str, Any]:
    """Toutes les opérations de 05-acp sur /opt/data ; renvoie l'état du démarrage."""
    if not chemins.hermes_home.is_dir():
        raise Refus(f"{chemins.hermes_home} est absent : le volume n'est pas monté.")
    livres = themes_livres(chemins)
    # 1. Inspection avant toute écriture : un refus laisse le volume intact.
    inspecter_donnees(chemins)
    refuser_repertoires_executes(chemins)
    # 2. Verrouillage, puis nouvelle inspection (rien ne doit être apparu entre-temps). Les
    #    hooks/ et scripts/ de chaque profil sont repris comme ceux de la racine.
    executes, _ = repertoires_executes(chemins)
    for racine in (chemins.greffons_utilisateur, chemins.themes, chemins.donnees_acp,
                   *(r for r, _ in executes)):
        verrouiller(racine)
    refuser_repertoires_executes(chemins)
    profils = sorted(_affichable(p.name, 60) for p in profils_du_volume(chemins)[0])
    greffons = inspecter(chemins.greffons_utilisateur)
    inspecter(chemins.themes, themes_livres=livres)
    # 3. Thème et persona.
    themes = deposer_theme(chemins.theme_livre, chemins.themes)
    soul = gerer_soul(chemins, uid=uid, gid=gid)
    # 4. Reprise à root des services s6 : l'agent ne peut plus enregistrer un service supervisé
    #    en root ni réécrire le script d'exécution d'une passerelle (empêche l'élévation).
    services = reprendre_services_s6(chemins.scandir_s6)
    return {
        # Schéma 2 (étape P2) : repertoires_executes, lazy_packages et deploiement.
        "schema": 2,
        "genere_le": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "deploiement": {"commit": commit},
        "repertoires_executes": {
            "hooks": {"vide": True, "proprietaire": "root", "mode": "0755"},
            "scripts": {"vide": True, "proprietaire": "root", "mode": "0755"},
            # Profils dont hooks/ et scripts/ ont été inspectés vides puis repris par root.
            "profils": profils,
        },
        "lazy_packages": {"entrees": contenu_paquets_paresseux(chemins)},
        "scope_geree": scope.resume(),
        "greffons_utilisateur": {
            "dossiers": greffons.dossiers_premier_niveau,
            "noms_declares": [nom for _, nom in greffons.noms_declares],
            "manifestes_illisibles": greffons.illisibles,
            "activables": False,
        },
        "themes_deposes": themes,
        "soul": soul,
        "services_s6": services,
    }


def ecrire_etat(chemins: Chemins, etat: Mapping[str, Any]) -> Path:
    assurer_repertoire_root(chemins.dossier_etat)
    cible = chemins.dossier_etat / "etat-demarrage.json"
    contenu = (json.dumps(etat, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ecrire_atomique(cible, contenu, mode=0o644, uid=0, gid=0)
    return cible


# ---------------------------------------------------------------------------------------------
# Commande « diagnostiquer » : maintenance, en lecture seule (étape P2)
# ---------------------------------------------------------------------------------------------

PREFIXE_DIAGNOSTIC = f"{PREFIXE} DIAGNOSTIC :"
_LIMITE_ENVIRONNEMENT = 1024 * 1024


def _lire_octets(chemin: Path, limite: int = _LIMITE_ENVIRONNEMENT) -> Optional[bytes]:
    """Contenu d'un fichier de /proc ou de /run (tronqué à ``limite``) ; None s'il est illisible."""
    try:
        with open(chemin, "rb") as flux:
            return flux.read(limite)
    except OSError:
        return None


def lire_environ(donnees: bytes) -> Dict[str, str]:
    """Analyse un /proc/<pid>/environ : entrées « NOM=valeur » séparées par des octets nuls.
    Rien n'est exécuté ni interprété (ni guillemets, ni substitution)."""
    env: Dict[str, str] = {}
    for morceau in donnees.split(b"\0"):
        if not morceau or b"=" not in morceau:
            continue
        nom, _, valeur = morceau.partition(b"=")
        env[nom.decode("utf-8", errors="replace")] = valeur.decode("utf-8", errors="replace")
    return env


def lire_env_s6(dossier: Path) -> Optional[Dict[str, str]]:
    """Environnement du conteneur tel que s6-overlay le garde (un fichier par variable, lu sans
    suivre de lien) ; None si le répertoire est illisible.

    s6-overlay termine chaque fichier par un saut de ligne (mesuré : « /opt/data\\n ») et
    ``with-contenv`` le retire (``s6-envdir -Lf``, sans ``-n`` : un seul « \\n » final ôté). On
    retire donc exactement UN « \\n » final, comme lui : la valeur comparée est celle que voient
    les scripts root et les services."""
    try:
        fd = os.open(dossier, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return None
    env: Dict[str, str] = {}
    try:
        for nom in sorted(os.listdir(fd)):
            try:
                fichier = os.open(nom, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            except OSError:
                continue
            with os.fdopen(fichier, "rb") as flux:
                if not stat.S_ISREG(os.fstat(flux.fileno()).st_mode):
                    continue
                valeur = flux.read(_LIMITE_ENVIRONNEMENT).decode("utf-8", errors="replace")
                env[nom] = valeur[:-1] if valeur.endswith("\n") else valeur
    finally:
        os.close(fd)
    return env


def environnement_de_reference(chemins: Chemins) -> Tuple[Optional[Dict[str, str]], str]:
    """(environnement, source) du conteneur, JAMAIS celui de la session qui lance la commande :
    la doc de Railway ne dit rien de l'environnement d'une session « railway ssh »
    (rw_full.txt:23271-23420). Hors de s6 (maintenance : PID 1 = « sleep infinity »), c'est
    /proc/1/environ ; sous s6, /run/s6/container_environment ; sinon « inconnue »."""
    cmdline = chemins.proc_pid1 / "cmdline"
    brut = _lire_octets(cmdline, 4096)
    if not brut or not brut.strip(b"\0"):
        return None, f"inconnue ({cmdline} illisible)"
    morceaux = [m.decode("utf-8", errors="replace") for m in brut.split(b"\0") if m]
    programme = os.path.basename(morceaux[0])
    affiche = "".join(c for c in " ".join(morceaux) if c.isprintable())[:160]
    if programme == "s6-svscan":
        env = lire_env_s6(chemins.env_s6)
        if env is None:
            return None, f"inconnue ({chemins.env_s6} illisible alors que le PID 1 est s6-svscan)"
        return env, f"{chemins.env_s6} (PID 1 : {affiche})"
    environ = chemins.proc_pid1 / "environ"
    donnees = _lire_octets(environ)
    if donnees is None:
        return None, f"inconnue ({environ} illisible : root exigé)"
    return lire_environ(donnees), f"{environ} (PID 1 hors de s6 : {affiche})"


def _tronquer(valeur: Any, limite: int = 120) -> str:
    texte = valeur if isinstance(valeur, str) else json.dumps(valeur, ensure_ascii=False, default=str)
    texte = "".join(c for c in texte if c.isprintable())
    return texte if len(texte) <= limite else texte[:limite] + "…"


def cles_executables(donnees: Any) -> List[str]:
    """Clés d'un config.yaml qui font exécuter un programme ou du code par Hermes : serveurs MCP
    stdio (hermes_cli/mcp_config.py:209-213), crochets shell ``hooks`` (config_defaults.py:1706-1710),
    quick_commands de type exec (gateway/run_inbound.py:1044), fournisseurs TTS ou STT de type
    command (tools/tts_command_provider.py:220-240)."""
    trouvees: List[str] = []
    if not isinstance(donnees, dict):
        return trouvees
    serveurs = donnees.get("mcp_servers")
    if isinstance(serveurs, dict):
        for nom, conf in serveurs.items():
            if isinstance(conf, dict) and isinstance(conf.get("command"), str) and conf["command"].strip():
                trouvees.append(f"mcp_servers.{_tronquer(nom, 60)}.command = « {_tronquer(conf['command'])} »")
    crochets = donnees.get("hooks")
    if crochets:
        noms = ", ".join(_tronquer(k, 40) for k in crochets) if isinstance(crochets, dict) else _tronquer(crochets)
        trouvees.append(f"hooks non vide ({noms}) : crochets shell de la configuration")
    rapides = donnees.get("quick_commands")
    if isinstance(rapides, dict):
        for nom, conf in rapides.items():
            if isinstance(conf, dict) and str(conf.get("type") or "").strip().lower() == "exec":
                trouvees.append(f"quick_commands.{_tronquer(nom, 60)} de type exec = "
                                f"« {_tronquer(conf.get('command', ''))} »")
    for section in ("tts", "stt"):
        bloc = donnees.get(section)
        if not isinstance(bloc, dict):
            continue
        candidats: List[Tuple[str, Any]] = []
        fournisseurs = bloc.get("providers")
        if isinstance(fournisseurs, dict):
            candidats += [(f"{section}.providers.{_tronquer(n, 60)}", c) for n, c in fournisseurs.items()]
        candidats += [(f"{section}.{_tronquer(n, 60)}", c) for n, c in bloc.items() if n != "providers"]
        for cle, conf in candidats:
            if not isinstance(conf, dict):
                continue
            genre = str(conf.get("type") or "").strip().lower()
            commande = conf.get("command")
            if genre in ("", "command") and isinstance(commande, str) and commande.strip():
                trouvees.append(f"{cle}.command (fournisseur de type command) = « {_tronquer(commande)} »")
    return trouvees


def fichiers_config_du_volume(chemins: Chemins) -> List[Path]:
    """config.yaml de la racine et de chaque profil (répertoires réels seulement)."""
    fichiers = [chemins.hermes_home / "config.yaml"]
    profils = chemins.hermes_home / "profiles"
    try:
        entrees = sorted(profils.iterdir())
    except OSError:
        entrees = []
    for entree in entrees:
        try:
            if stat.S_ISDIR(os.lstat(entree).st_mode):
                fichiers.append(entree / "config.yaml")
        except OSError:
            continue
    return fichiers


def inventaire_cles_executables(chemins: Chemins) -> List[str]:
    constats: List[str] = []
    for fichier in fichiers_config_du_volume(chemins):
        try:
            brut = lire_sans_lien(fichier)
        except Refus as exc:
            constats.append(str(exc))
            continue
        if brut is None:
            continue
        try:
            donnees = charger_yaml(brut.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            constats.append(f"{fichier} ne se lit pas comme du YAML ({type(exc).__name__}) : à examiner.")
            continue
        for cle in cles_executables(donnees):
            constats.append(f"{fichier} : {cle}.")
    return constats


def taches_cron_a_script(chemins: Chemins) -> List[str]:
    """Tâches cron qui exécutent un script (champs ``script`` et ``monitor_script`` :
    cron/scheduler.py:1498, cron/monitor.py:109-114), dans ``cron/jobs.json`` de la racine et de
    chaque profil. Sans script dans les ``scripts/`` (exigés vides), elles échouent ; elles restent
    signalées : leur présence dit qu'une sauvegarde restaurée ou une ancienne injection en a posé.
    Lecture tolérante comme Hermes (BOM, caractères de contrôle, liste nue ou dictionnaire par
    identifiant : cron/jobs.py:1322-1375), sans suivre de lien."""
    constats: List[str] = []
    fichiers = [chemins.hermes_home / "cron" / "jobs.json"]
    fichiers += [p / "cron" / "jobs.json" for p in profils_du_volume(chemins)[0]]
    for fichier in fichiers:
        try:
            brut = lire_sans_lien(fichier)
        except Refus as exc:
            constats.append(str(exc))
            continue
        if brut is None:
            continue
        try:
            texte = brut.decode("utf-8-sig")
            try:
                donnees = json.loads(texte)
            except ValueError:
                donnees = json.loads(texte, strict=False)
        except (UnicodeDecodeError, ValueError) as exc:
            constats.append(f"{fichier} ne se lit pas comme du JSON ({type(exc).__name__}) : à examiner.")
            continue
        taches = donnees.get("jobs", []) if isinstance(donnees, dict) else donnees
        if isinstance(taches, dict):
            taches = [dict(v, id=v.get("id") or k) for k, v in taches.items() if isinstance(v, dict)]
        if not isinstance(taches, list):
            constats.append(f"{fichier} n'a pas la forme attendue ({{\"jobs\": [...]}}) : à examiner.")
            continue
        for tache in taches:
            if not isinstance(tache, dict):
                continue
            for champ in ("script", "monitor_script"):
                valeur = tache.get(champ)
                if isinstance(valeur, str) and valeur.strip():
                    constats.append(
                        f"{fichier} : la tâche cron « {_tronquer(tache.get('id') or tache.get('name') or '?', 60)} » "
                        f"exécute un script ({champ} = « {_tronquer(valeur)} »).")
    return constats


def relire_scope_pour_diagnostic(chemins: Chemins, env: Optional[Mapping[str, str]]
                                 ) -> Tuple[Optional[str], str]:
    """(problème, forme) de la managed scope installée. En maintenance, acp-gardes n'a pas tourné :
    la scope de CONSTRUCTION (valeurs vides) est alors attendue et n'est pas un problème."""
    candidats: List[Tuple[str, ValeursDeploiement, bool]] = []
    if env is not None:
        try:
            candidats.append(("déploiement", verifier_environnement(env), False))
        except Refus:
            pass
    candidats.append(("construction (valeurs de déploiement vides)", VALEURS_VIDES, True))
    dernier = ""
    for forme, valeurs, construction in candidats:
        try:
            attendue = preparer_scope_geree(chemins, valeurs, construction=construction)
            verifier_scope_installee(chemins, attendue, valeurs)
            return None, forme
        except Refus as exc:
            dernier = str(exc)
    return f"managed scope installée non conforme : {dernier}", "non conforme"


def diagnostic(chemins: Chemins) -> Tuple[List[str], List[str]]:
    """(informations, constats). Ne modifie RIEN : ni le volume, ni /etc/hermes, ni /run/acp.
    Aucune liste d'exceptions n'est lue (et jamais depuis le volume)."""
    infos: List[str] = []
    constats: List[str] = []
    env, source = environnement_de_reference(chemins)
    infos.append(f"source de l'environnement de référence : {source}.")
    if env is None:
        constats.append(f"source de l'environnement inconnue ({source}) : les variables Railway ne peuvent "
                        "pas être vérifiées.")
    else:
        infos.append(f"commit déployé : {commit_deploye(env) or 'inconnu'}.")
        try:
            verifier_environnement(env)
        except Refus as exc:
            constats.extend(str(exc).splitlines())
        try:
            verifier_montage(env, chemins.montages)
        except Refus as exc:
            constats.append(str(exc))
    for fichier, nom, raison in variables_interdites_dans_le_volume(chemins):
        constats.append(f"{fichier} définit la variable interdite {nom} : {raison}.")
    try:
        inspecter_donnees(chemins)
    except Refus as exc:
        constats.append(str(exc))
    constats.extend(problemes_repertoires_executes(chemins))
    constats.extend(inventaire_cles_executables(chemins))
    constats.extend(taches_cron_a_script(chemins))
    try:
        paresseux = entrees_du_repertoire(chemins.paquets_paresseux)
    except Refus as exc:
        constats.append(str(exc))
        paresseux = None
    paquets = [n for n in (paresseux or []) if n not in _FICHIERS_LAZY_ADMIS]
    if paquets:
        constats.append(f"{chemins.paquets_paresseux} contient des paquets ("
                        + ", ".join(_tronquer(n, 60) for n in paquets[:20])
                        + ") : Hermes pourrait les importer (fin de sys.path).")
    probleme, forme = relire_scope_pour_diagnostic(chemins, env)
    infos.append(f"managed scope installée : {forme}.")
    if probleme:
        constats.append(probleme)
    return infos, constats


def commande_diagnostiquer(chemins: Chemins) -> int:
    _exiger_root()
    infos, constats = diagnostic(chemins)
    print(f"{PREFIXE} diagnostic en lecture seule : rien n'est modifié.", flush=True)
    for info in infos:
        print(f"{PREFIXE} diagnostic : {info}", flush=True)
    for constat in constats:
        for ligne in constat.splitlines():
            print(f"{PREFIXE_DIAGNOSTIC} {ligne}", flush=True)
    if constats:
        print(f"{PREFIXE} diagnostic : {len(constats)} constat(s) ; code 1.", flush=True)
        return 1
    print(f"{PREFIXE} diagnostic : aucun constat ; code 0.", flush=True)
    return 0


# ---------------------------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------------------------


def _informer(message: str) -> None:
    print(f"{PREFIXE} {message}", flush=True)


def _refuser(message: str, *, construction: bool = False) -> int:
    for ligne in message.splitlines():
        print(f"{PREFIXE} REFUS : {ligne}", file=sys.stderr, flush=True)
    if construction:
        print(f"{PREFIXE} Construction de l'image refusée (échec fermé).", file=sys.stderr, flush=True)
    else:
        print(f"{PREFIXE} Démarrage arrêté (échec fermé). Corrigez la cause ci-dessus puis redéployez.",
              file=sys.stderr, flush=True)
    return 1


def _exiger_root() -> None:
    if os.geteuid() != 0:
        raise Refus(
            "ce script doit tourner en root (le conteneur a-t-il été lancé avec --user ?) : "
            "sans root, la managed scope ne peut pas être protégée.")


def commande_construire(chemins: Chemins) -> None:
    _exiger_root()
    resume = installer_scope_geree(chemins, VALEURS_VIDES, construction=True)
    _informer(f"managed scope de base installée ({len(resume['cles_config'])} clés épinglées, "
              f"config {resume['config_sha256'][:12]}).")


def commande_gardes(chemins: Chemins, env: Mapping[str, str]) -> None:
    _exiger_root()
    # Relie ce démarrage à son run CI image.yml (docs/refonte/railway.md), même s'il est refusé.
    _informer(f"commit déployé : {commit_deploye(env) or 'inconnu'}")
    valeurs = verifier_environnement(env)
    verifier_montage(env, chemins.montages)
    # Une variable interdite posée dans /opt/data/.env échapperait à la managed scope
    # (HERMES_MANAGED_DIR la déplacerait carrément) : un volume ainsi piégé refuse de démarrer.
    refuser_variables_du_volume(chemins)
    # hooks/ et scripts/ du volume sont exécutés par Hermes : inspectés avant toute écriture.
    refuser_repertoires_executes(chemins)
    resume = installer_scope_geree(chemins, valeurs)
    _informer(f"variables validées ; émetteur OIDC {valeurs.oidc_emetteur}, client {valeurs.oidc_client}, "
              f"URL publique {valeurs.url_publique}"
              + (" (secret client fourni, non recopié)" if valeurs.secret_client_fourni else " (client public)")
              + ".")
    _informer(f"managed scope régénérée : {len(resume['cles_config'])} clés de configuration et "
              f"{len(resume['cles_env'])} variables épinglées dans {chemins.dossier_gere}.")
    greffons = inspecter_donnees(chemins)
    _informer(f"{chemins.greffons_utilisateur} inspecté : aucun nom réservé ni lien symbolique"
              + (f" ({len(greffons.dossiers_premier_niveau)} dossier(s) utilisateur, jamais activés)."
                 if greffons.dossiers_premier_niveau else "."))
    profils = [_affichable(p.name, 60) for p in profils_du_volume(chemins)[0]]
    _informer(f"{chemins.crochets_passerelle} et {chemins.scripts_cron} inspectés : vides"
              + (f", ainsi que hooks/ et scripts/ de {len(profils)} profil(s) ({', '.join(profils)})."
                 if profils else "."))


def commande_donnees(chemins: Chemins, env: Mapping[str, str]) -> None:
    _exiger_root()
    # Défense en profondeur : si le crochet S6_STAGE2_HOOK avait été retiré, ce script de
    # cont-init refait les mêmes contrôles et vérifie la managed scope installée.
    valeurs = verifier_environnement(env)
    verifier_montage(env, chemins.montages)
    refuser_variables_du_volume(chemins)
    scope = preparer_scope_geree(chemins, valeurs)
    verifier_scope_installee(chemins, scope, valeurs)
    compte = pwd.getpwnam("hermes")
    etat = preparer_donnees(chemins, scope, uid=compte.pw_uid, gid=compte.pw_gid, commit=commit_deploye(env))
    cible = ecrire_etat(chemins, etat)
    _informer(f"{chemins.greffons_utilisateur}, {chemins.themes}, {chemins.donnees_acp}, "
              f"{chemins.crochets_passerelle} et {chemins.scripts_cron} appartiennent à root (0755)"
              + (f", ainsi que hooks/ et scripts/ des profils {', '.join(etat['repertoires_executes']['profils'])}."
                 if etat["repertoires_executes"]["profils"] else "."))
    paresseux = etat["lazy_packages"]["entrees"]
    if paresseux:
        _informer("ATTENTION : " + str(chemins.paquets_paresseux) + " contient des paquets ("
                  + ", ".join(paresseux[:20]) + ") alors que les installations paresseuses sont coupées ; "
                  "signalé par /v1/meta, à examiner avec `diagnostiquer`.")
    services = etat.get("services_s6") or {}
    if services.get("present"):
        _informer("services s6 repris par root : /run/service et "
                  + (", ".join(services.get("passerelles") or []) or "aucune passerelle")
                  + " (l'agent ne peut plus enregistrer de service supervisé).")
    _informer(f"thèmes déposés : {', '.join(etat['themes_deposes']) or 'aucun'} ; "
              f"SOUL.md : {etat['soul']['etat']}.")
    if etat["greffons_utilisateur"]["dossiers"]:
        _informer("greffons utilisateur présents mais non activables : "
                  + ", ".join(etat["greffons_utilisateur"]["dossiers"]) + ".")
    _informer(f"état du démarrage écrit dans {cible}.")


def commande_verifier_relance(chemins: Chemins) -> None:
    """Garde exécutée en root en tête des scripts `run` du tableau de bord et de la passerelle :
    refuse la relance si l'agent a injecté une variable interdite dans un .env du volume."""
    _exiger_root()
    refuser_variables_du_volume(chemins)


COMMANDES = ("construire", "gardes", "donnees", "verifier-relance", "diagnostiquer")


def main(argv: Optional[Iterable[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1 or arguments[0] not in COMMANDES:
        print(f"{PREFIXE} usage : acp_demarrage.py {'|'.join(COMMANDES)}", file=sys.stderr)
        return 2
    chemins = Chemins()
    if arguments[0] == "diagnostiquer":
        # Jamais os.environ : l'environnement de référence est celui du PID 1 (correction R2-7).
        try:
            return commande_diagnostiquer(chemins)
        except Refus as exc:
            print(f"{PREFIXE_DIAGNOSTIC} {exc}", file=sys.stderr, flush=True)
            return 1
        except Exception as exc:  # noqa: BLE001 — un diagnostic incomplet ne conclut jamais « sain »
            print(f"{PREFIXE_DIAGNOSTIC} erreur inattendue ({type(exc).__name__} : {exc}) ; diagnostic "
                  "incomplet.", file=sys.stderr, flush=True)
            return 1
    try:
        if arguments[0] == "construire":
            commande_construire(chemins)
        elif arguments[0] == "gardes":
            commande_gardes(chemins, dict(os.environ))
        elif arguments[0] == "verifier-relance":
            commande_verifier_relance(chemins)
        else:
            commande_donnees(chemins, dict(os.environ))
    except Refus as exc:
        return _refuser(str(exc), construction=arguments[0] == "construire")
    except Exception as exc:  # noqa: BLE001 — échec fermé : toute erreur inattendue refuse
        return _refuser(f"erreur inattendue ({type(exc).__name__} : {exc}) ; refus par précaution.",
                        construction=arguments[0] == "construire")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
