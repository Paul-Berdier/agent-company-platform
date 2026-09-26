"""Section de prompt « acp-projets » (cahier P4 § 10) : parade aux consignes kanban génériques de Hermes.

``KANBAN_GUIDANCE`` (agent/prompt_builder.py:264-352), injecté à tout worker, lui dit de créer des cartes
(``kanban_create``), de lister les profils (``hermes profile list``) et de travailler dans
``$HERMES_KANBAN_WORKSPACE``. Pour une carte ACP, c'est faux : l'agent n'a ni fichiers ni terminal, ne crée
jamais de carte (``kanban_create`` est refusé par la garde) et ``poste-codex``/``poste-claude`` ne sont
pas des profils. Cette section, placée APRÈS les consignes d'outils (``after_memory``,
agent/system_prompt.py:562, 779), le dit et prime.

L'en-tête « ## Plugin Context: acp-projets » est imposé par Hermes, en anglais
(hermes_cli/plugins_dispatch.py:74) : limite dite. Longueur bornée à 4 000 caractères.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from . import base, projets
from . import kanban_adapter as ka

MAXIMUM = 4000
PLATEFORMES_SANS_OUTILS = ("api_server", "cron")

COMMUN_WORKER = (
    "Protocole ACP pour cette carte. Il PRIME sur les consignes kanban génériques ci-dessus :\n"
    "- aucun espace de travail ni fichier : n'utilisez ni $HERMES_KANBAN_WORKSPACE ni chemin local ;\n"
    "- ne créez JAMAIS de carte (ni kanban_create ni autre moyen) et n'appelez pas « hermes profile list » : "
    "poste-codex et poste-claude sont les deux exécutants du poste Windows, pas des profils ;\n"
    "- n'écrivez pas en mémoire (memory est refusé dans une carte) : mettez ce qui est utile dans le résumé de "
    "kanban_complete ;\n"
    "- ne bloquez pas pour une préférence : tranchez selon l'objectif et les décisions du projet ; kanban_block "
    "seulement pour un manque réel, avec sa raison ;\n"
    "- n'annoncez jamais un résultat du poste avant qu'il existe, ni un push, ni une fusion ;\n"
    "- les outils ACP (projet_planifier, projet_etat, poste_catalogue, poste_etat, question_repondre, "
    "question_escalader) sont chargés à la demande : appelez-les par tool_call (tool_describe d'abord pour leurs "
    "paramètres), sans tool_search.\n")
PAR_ROLE = {
    "planification": (
        "Votre rôle : découper l'objectif en étapes vérifiables. Lisez kanban_show (résultat de l'exploration "
        "s'il existe) et poste_catalogue, puis appelez projet_planifier UNE fois ; le greffon crée lui-même les "
        "cartes, la relecture croisée et la synthèse. Terminez par kanban_complete avec un résumé, sans "
        "created_cards inventés. Si projet_planifier refuse, corrigez le plan d'après le message ; si aucun plan "
        "n'est possible, dites pourquoi dans le résumé : le propriétaire recevra une carte de décision."),
    "synthese": (
        "Votre rôle : juger le tour sur les résumés (projet_etat, kanban_show). S'il reste un écart concret et "
        "que les plafonds le permettent, appelez projet_planifier pour le tour suivant ; sinon concluez. "
        "Terminez toujours par kanban_complete (fait, vérifié, reste à faire)."),
    "repondre": (
        "Votre rôle : répondre à la question d'une carte du poste par question_repondre SEULEMENT si les "
        "décisions du projet ou son objectif la couvrent (citez le fondement) ; sinon question_escalader avec "
        "un motif. Périmètre, dépense ou push : toujours escalader. Terminez par kanban_complete."),
    "hermes": (
        "Votre rôle : exécuter l'étape par la recherche, la lecture du web et la rédaction seulement, puis "
        "kanban_complete avec le résultat."),
    "triage": (
        "Votre rôle : le propriétaire a décidé de cette carte (plafond prolongé, ou planification à relancer) ; sa "
        "consigne est à la fin de la carte. Lisez projet_etat et kanban_show, puis appelez projet_planifier UNE "
        "fois pour le tour suivant si la consigne demande de continuer ; sinon concluez. Terminez toujours par "
        "kanban_complete : ce qui est planifié, ou pourquoi rien ne l'est."),
}
DISCUSSION = (
    "Projets ACP : un travail de plusieurs étapes passe par projet_lancer ; son suivi, par projet_etat et "
    "poste_etat (outils chargés à la demande : tool_describe puis tool_call).\n"
    "Ne présentez jamais un résultat du poste avant qu'il existe.\n"
    "Un projet sur dépôt exige un poste connecté (étape P5) ; sans lui, lancez-le sans dépôt.\n"
    "Vous ne créez jamais de carte kanban vous-même.")


def _borne(texte: str) -> str:
    return texte[:MAXIMUM]


def rendre(session_info: Mapping[str, Any] = None) -> str:
    """Texte de la section, selon le contexte (worker d'une carte ACP, autre worker, discussion). Ne lève
    jamais : un échec rend le texte de discussion, sans rien inventer du projet."""
    # Surfaces sans les outils du greffon (décision D24 : known_plugin_toolsets) : aucune section.
    if str((session_info or {}).get("platform") or "") in PLATEFORMES_SANS_OUTILS:
        return ""
    try:
        carte = ka.owned_kanban_task()
    except Exception:  # noqa: BLE001
        carte = ""
    if not carte:
        return _borne(DISCUSSION)
    try:
        tableau = (os.environ.get("HERMES_KANBAN_BOARD") or "").strip()
        with base.connexion() as conn:
            fiche = projets.projet(conn, tableau) if tableau else None
            demande = projets.demande_de_la_carte(conn, tableau, carte) if fiche else None
        if fiche is None or demande is None:
            return _borne(COMMUN_WORKER)
        role = demande["role"]
        entete = (f"Carte ACP : rôle « {role} » — projet « {fiche['titre']} » (tour {demande['tour']}, "
                  f"type {fiche['profil']}, dépôt {fiche['depot_alias'] or 'aucun'}).\n")
        return _borne(entete + COMMUN_WORKER + PAR_ROLE.get(role, ""))
    except Exception:  # noqa: BLE001 — base illisible : les règles communes, sans rien inventer du projet
        return _borne(COMMUN_WORKER)
