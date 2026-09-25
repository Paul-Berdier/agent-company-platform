"""Garde d'exécution de l'agent : crochet ``pre_tool_call`` en LISTE BLANCHE (étape P2).

Décision du propriétaire (25 septembre 2026) : sur Railway, l'agent n'a AUCUN outil
d'exécution — ni terminal, ni fichiers, ni exécution de code, ni navigateur. L'exécution
passe par le poste Windows du propriétaire. Cette garde est la troisième couche, après les
listes de la managed scope (``agent.disabled_toolsets``, ``platform_toolsets``) et les
épingles de ``/etc/hermes/.env`` ; aucune ne suffit seule.

Elle est la SEULE à fermer ``preview.restart`` : l'agent caché qu'il lance reçoit
``["terminal", "file"]`` codés en dur (tui_gateway/agent_callbacks.py:371-374), sans les
retraits de la configuration.

Fonctionnement (source de Hermes f97608f) :

- le greffon enregistre :func:`garde` par ``ctx.register_hook("pre_tool_call", …)`` ; tout
  ``AIAgent`` découvre lui-même les greffons avant de choisir ses outils
  (agent/agent_init.py:1060-1065) : passerelle, workers kanban, processus du tableau de bord
  (``/api/ws``), ``tui_gateway.entry`` ;
- Hermes appelle le crochet avec le nom et les arguments de l'outil
  (hermes_cli/plugins.py:1854-1974) ; un retour ``{"action": "block", "message": …}``
  remplace l'exécution par ce message ;
- un rappel qui LÈVE est traité par Hermes comme un blocage (plugins_dispatch.py:229-241),
  mais la couche d'appel autour échoue ouvert (agent_runtime_helpers.py:2348-2361 ;
  tool_executor.py:652-667) : :func:`garde` ne lève donc JAMAIS ;
- échec ouvert connu et dit : si la découverte des greffons lève, l'agent continue sans
  aucun greffon (agent/agent_init.py:1066-1067). Parades : test de découverte sur l'image
  épinglée et alerte de ``/v1/meta`` (processus du tableau de bord).

Règle d'extension (P5) : les outils du poste seront nommés ``poste_*`` et ajoutés ici un par
un. ``kanban_create`` ne sera réadmis qu'avec une liste blanche d'ARGUMENTS : ``title``,
``body``, ``assignee`` limité aux profils du poste, ``parents``, ``priority``,
``idempotency_key``, ``triage`` ; seront refusés ``skills``, ``model``, ``provider``,
``workspace_kind`` autre que ``scratch``, ``workspace_path``, ``project``, ``tenant``,
``goal_mode``, ``goal_max_turns``, ``completion_contract`` et ``initial_status``. Le crochet
reçoit déjà ces arguments (paramètre ``args``).

Ce module n'importe rien de Hermes au chargement.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, FrozenSet, Optional

# Les 24 seuls outils que l'agent peut appeler sur Railway (noms exacts, aucun préfixe).
OUTILS_ADMIS: FrozenSet[str] = frozenset({
    # Recherche et lecture du web, analyse d'image (client sûr : tools/vision_tools.py:167-178).
    "web_search", "web_extract", "vision_analyze",
    # Skills (écriture soumise à validation : skills.write_approval).
    "skills_list", "skill_view", "skill_manage",
    # Planification, mémoire (écriture soumise à validation : memory.write_approval), historique.
    "todo_list", "memory", "session_search", "clarify",
    # Recherche d'outils différés ; le pont « tool_call » reste refusé.
    "tool_search", "tool_describe",
    # Cycle de vie d'une carte kanban, côté worker.
    "kanban_show", "kanban_list", "kanban_complete", "kanban_block", "kanban_request_review",
    "kanban_request_changes", "kanban_heartbeat", "kanban_comment", "kanban_link", "kanban_unblock",
    "kanban_attach", "kanban_attachments",
})

# Outils retirés en P2, avec la raison donnée à l'agent.
MOTIFS_DEDIES: Dict[str, str] = {
    # hermes_cli/kanban_db_dispatch.py:2676-2710 et 2820-2887 : le worker lancé recevrait les
    # skills, le modèle, le fournisseur et l'espace de travail choisis par l'agent.
    "kanban_create": (
        "Refusé par ACP : la création de carte par l'agent arrive en P5, avec contrôle des "
        "arguments (compétences, modèle, fournisseur, espace de travail)."),
    # tools/kanban_tools.py:924-958 : is_safe_url puis httpx.stream ordinaire, sans protection
    # contre le rebinding DNS (tools/url_safety.py:7-10).
    "kanban_attach_url": (
        "Refusé par ACP : ce téléchargement ne résiste pas au rebinding DNS vers le réseau privé ; "
        "joignez le fichier en base64 (kanban_attach)."),
}

MESSAGE_GENERAL = (
    "Refusé par ACP : l'outil « {nom} » n'est pas autorisé sur Railway (ni terminal, ni fichiers, "
    "ni exécution de code pour l'agent). L'exécution passe par le poste Windows du propriétaire.")
MESSAGE_SECOURS = "Refusé par ACP."

# Posé à True par register() dans le processus qui a chargé le greffon.
ENREGISTRE_DANS_CE_PROCESSUS = False

_FICHIER = os.path.realpath(__file__)


def _nom_affichable(nom: Any) -> str:
    """Nom d'outil tronqué à 64 caractères imprimables (jamais d'échappement de terminal)."""
    texte = nom if isinstance(nom, str) else repr(nom)
    propre = "".join(c for c in texte if c.isprintable())[:64]
    return propre or "(sans nom)"


def garde(tool_name: str = "", args: Any = None, **_ignores: Any) -> Optional[Dict[str, str]]:
    """Crochet ``pre_tool_call`` : None pour un outil admis, sinon un blocage. Ne lève jamais."""
    try:
        if type(tool_name) is str and tool_name in OUTILS_ADMIS:
            return None
        if type(tool_name) is str and tool_name in MOTIFS_DEDIES:
            return {"action": "block", "message": MOTIFS_DEDIES[tool_name]}
        return {"action": "block", "message": MESSAGE_GENERAL.format(nom=_nom_affichable(tool_name))}
    except BaseException:  # noqa: BLE001 — une garde qui lève serait contournée (échec ouvert)
        return {"action": "block", "message": MESSAGE_SECOURS}


def _est_cette_garde(rappel: Any) -> bool:
    """Vrai si ``rappel`` est la fonction :func:`garde` de CE fichier, quel que soit le nom sous
    lequel Hermes a importé le paquet du greffon (``hermes_plugins.acp_poste…``)."""
    code = getattr(rappel, "__code__", None)
    if getattr(rappel, "__name__", "") != "garde" or code is None:
        return False
    try:
        return os.path.realpath(code.co_filename) == _FICHIER
    except (OSError, ValueError):
        return False


def etat() -> Dict[str, Any]:
    """État de la garde DANS LE PROCESSUS APPELANT : présente dans le gestionnaire de greffons
    de Hermes (``_hooks["pre_tool_call"]``), enregistrée par ``register()``. ``None`` signifie
    « illisible », jamais « oui »."""
    resultat: Dict[str, Any] = {
        "enregistree": None,
        "presente_dans_le_gestionnaire": None,
        "outils_admis": sorted(OUTILS_ADMIS),
        "outils_retires": sorted(MOTIFS_DEDIES),
    }
    try:
        from hermes_cli.plugins import get_plugin_manager

        rappels = list(getattr(get_plugin_manager(), "_hooks", {}).get("pre_tool_call", []) or [])
    except Exception:  # noqa: BLE001 — valeur inconnue plutôt qu'une erreur
        return resultat
    gardes = [r for r in rappels if _est_cette_garde(r)]
    resultat["presente_dans_le_gestionnaire"] = bool(gardes)
    resultat["enregistree"] = any(
        getattr(sys.modules.get(getattr(r, "__module__", "") or ""), "ENREGISTRE_DANS_CE_PROCESSUS", False) is True
        for r in gardes)
    return resultat
