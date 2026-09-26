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

Pont des outils différés (``tool_call``, correction de la relecture P2) : Hermes le DÉBALLE
AVANT d'appeler le crochet (agent/tool_executor.py:390-431, ``_unwrap_tool_search_call``) ;
la garde reçoit donc le nom de l'outil appelé à travers le pont (``todo_list``,
``session_search``…) et le juge comme un appel direct. Elle ne voit « tool_call » que si Hermes
n'a pas su le résoudre : outil non différable comme ``terminal``
(tools/tool_search.py:543-571), arguments invalides, lot de connecteurs ; elle le refuse alors,
puisque « tool_call » n'est pas dans la liste blanche.

Extension de l'étape P4 (plan d'autonomie, docs/refonte/autonomie.md § 8) : les HUIT outils du
greffon (``projet_lancer``, ``projet_planifier``, ``projet_etat``, ``poste_etat``,
``poste_catalogue``, ``question_repondre``, ``question_escalader``, ``routage_surcharger``) sont
ajoutés ici un par un, par leur nom exact ; la liste était passée de 26 à 34 noms, 33 depuis le
retrait de ``kanban_link`` ci-dessous (``test_garde_admet_exactement_les_outils_du_greffon`` compare
les ajouts à ``noyau.outils.SCHEMAS``).
``kanban_create`` n'est PAS réadmis : les cartes des projets sont créées par le greffon lui-même
(``projet_lancer``, ``projet_planifier``), sur le tableau qu'il choisit, avec les compétences, le
modèle et l'effort qu'il fixe ; l'agent ne les choisit jamais.

Isolation des projets (relecture de P4, décision D44) : dans un worker kanban (``HERMES_KANBAN_TASK``
posée par le répartiteur), un outil ``kanban_*`` qui nomme un AUTRE tableau que le sien
(``HERMES_KANBAN_BOARD``) est refusé, et ``kanban_comment`` ne vise que la carte du worker : Hermes
0.21.5 laisse le modèle choisir ``board`` et ``task_id`` (tools/kanban_tools.py:875-893), et un
commentaire est injecté dans le contexte du worker suivant de la carte visée. ``kanban_link`` est retiré
(les dépendances d'un projet sont posées par le greffon seul) : la liste passe à 33 noms.

Ce module n'importe rien de Hermes au chargement.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, FrozenSet, Optional

# Les 33 seuls outils que l'agent peut appeler sur Railway (noms exacts, aucun préfixe).
OUTILS_ADMIS: FrozenSet[str] = frozenset({
    # Étape P3 : les deux outils du serveur MCP DISTANT context7 (documentation des bibliothèques),
    # sous le nom que leur donne Hermes (mcp__<serveur>__<outil>, tirets remplacés par « _ » :
    # tools/mcp_tool_schema.py:147-185). Aucun autre outil MCP n'est admis, quel que soit le serveur.
    "mcp__context7__resolve_library_id", "mcp__context7__query_docs",
    # Recherche et lecture du web, analyse d'image (client sûr : tools/vision_tools.py:167-178).
    "web_search", "web_extract", "vision_analyze",
    # Skills (écriture soumise à validation : skills.write_approval).
    "skills_list", "skill_view", "skill_manage",
    # Planification, mémoire (écriture soumise à validation : memory.write_approval), historique.
    "todo_list", "memory", "session_search", "clarify",
    # Recherche d'outils différés. Le pont « tool_call » n'est pas admis en tant que tel : Hermes
    # le déballe avant le crochet (la garde juge l'outil appelé à travers lui) ; non résolu, il
    # arrive ici sous son propre nom et il est refusé.
    "tool_search", "tool_describe",
    # Cycle de vie d'une carte kanban, côté worker (sur son seul tableau : voir garde()).
    "kanban_show", "kanban_list", "kanban_complete", "kanban_block", "kanban_request_review",
    "kanban_request_changes", "kanban_heartbeat", "kanban_comment", "kanban_unblock",
    "kanban_attach", "kanban_attachments",
    # Étape P4 : les huit outils du greffon acp-poste (jeu acp_poste, noyau/outils.py), et eux seuls.
    "projet_lancer", "projet_planifier", "projet_etat", "poste_etat", "poste_catalogue",
    "question_repondre", "question_escalader", "routage_surcharger",
})

# Outils retirés en P2, avec la raison donnée à l'agent.
MOTIFS_DEDIES: Dict[str, str] = {
    # hermes_cli/kanban_db_dispatch.py:2676-2710 et 2820-2887 : le worker lancé recevrait les
    # skills, le modèle, le fournisseur et l'espace de travail choisis par l'agent.
    "kanban_create": (
        "Refusé par ACP : l'agent ne crée pas de carte kanban lui-même ; les projets passent par "
        "les outils du greffon acp-poste (projet_lancer, projet_planifier), qui fixent compétences, "
        "modèle, effort et exécutant."),
    # tools/kanban_tools.py:924-958 : is_safe_url puis httpx.stream ordinaire, sans protection
    # contre le rebinding DNS (tools/url_safety.py:7-10).
    "kanban_attach_url": (
        "Refusé par ACP : ce téléchargement ne résiste pas au rebinding DNS vers le réseau privé ; "
        "joignez le fichier en base64 (kanban_attach)."),
    # Relecture de P4 : tools/kanban_tools.py:1165-1178 n'exige pas que les cartes liées soient celles du
    # worker ; une dépendance ajoutée changerait le graphe déterministe d'un projet.
    "kanban_link": (
        "Refusé par ACP : les dépendances entre cartes sont posées par le greffon acp-poste (graphe "
        "déterministe du projet) ; l'agent n'en ajoute pas."),
}

# Relecture de P4 (décision D44) : un worker ne touche que SON tableau, et ne commente que SA carte.
MOTIF_AUTRE_TABLEAU = (
    "Refusé par ACP : une carte ne touche que le tableau de son projet ; les autres projets ne lui sont "
    "pas accessibles.")
MOTIF_COMMENTAIRE_AUTRE_CARTE = (
    "Refusé par ACP : une carte ne commente que sa propre carte ; mettez l'information utile dans le "
    "résumé de kanban_complete.")


def _hors_de_sa_carte(tool_name: str, args: Any) -> Optional[str]:
    """Motif de refus d'un outil kanban_* qui sortirait du tableau ou de la carte du worker, sinon None."""
    if not tool_name.startswith("kanban_") or not _dans_un_worker_kanban():
        return None
    arguments = args if isinstance(args, dict) else {}
    tableau = arguments.get("board")
    if tableau not in (None, ""):
        if not isinstance(tableau, str) or tableau.strip() != (os.environ.get("HERMES_KANBAN_BOARD") or "").strip():
            return MOTIF_AUTRE_TABLEAU
    if tool_name == "kanban_comment":
        carte = arguments.get("task_id")
        if not isinstance(carte, str) or carte.strip() != (os.environ.get("HERMES_KANBAN_TASK") or "").strip():
            return MOTIF_COMMENTAIRE_AUTRE_CARTE
    return None

# Étape P4 : outils admis, mais refusés DANS UN WORKER KANBAN (HERMES_KANBAN_TASK posée par le
# répartiteur : kanban_db_dispatch.py:2821-2862). Mesuré au contrat de P4 : dans un worker « chat -q »,
# une écriture en mémoire (memory.write_approval épinglé) ouvre l'invite d'approbation en ligne du CLI
# (tools/write_approval.py:170-213), qui attend 300 s sans personne puis met l'écriture en attente de
# validation (tools/approval_prompt.py:163-164) : la carte reste bloquée cinq minutes pour rien. En
# discussion, l'outil reste admis (écriture mise en validation).
MOTIFS_DANS_UN_WORKER: Dict[str, str] = {
    "memory": (
        "Refusé par ACP : une carte kanban n'écrit pas en mémoire (l'approbation du propriétaire attendrait "
        "cinq minutes sans personne avant de la mettre en attente) ; mettez l'information utile dans le "
        "résumé de la carte (kanban_complete)."),
}


def _dans_un_worker_kanban() -> bool:
    return bool((os.environ.get("HERMES_KANBAN_TASK") or "").strip())


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
            if tool_name in MOTIFS_DANS_UN_WORKER and _dans_un_worker_kanban():
                return {"action": "block", "message": MOTIFS_DANS_UN_WORKER[tool_name]}
            motif = _hors_de_sa_carte(tool_name, args)
            if motif is not None:
                return {"action": "block", "message": motif}
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
