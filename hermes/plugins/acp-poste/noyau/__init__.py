"""Noyau du greffon acp-poste (étape P4, décision D22) : projets autonomes sur Hermes.

Sous-paquet chargé de deux façons, sans état partagé en mémoire (tout est dans la base du greffon) :

- par le paquet du greffon (``from . import noyau`` dans ``__init__.py``), dans chaque processus de Hermes
  qui découvre les greffons (passerelle, tableau de bord, workers kanban, CLI) : outils de l'agent, section
  de prompt, crochet de tick de l'émetteur ;
- par ``dashboard/plugin_api.py``, que Hermes charge par son chemin : sous le nom canonique
  ``acp_poste_noyau`` (:func:`charger_par_chemin`), pour les routes ``/v1/projets``, ``/v1/questions``…

Aucun module du noyau n'importe Hermes au chargement, sauf par :mod:`kanban_adapter` (seul point de contact
avec l'interne de Hermes, couvert par ``hermes plugins compat``). Modules :

- :mod:`base` : base propre du greffon, schéma, réglages, journal ;
- :mod:`routage` : relevés du poste, table de routage, surcharges, résolution déterministe ;
- :mod:`cartes`, :mod:`projets`, :mod:`graphe` : création des cartes, projets, tours, corrections ;
- :mod:`questions`, :mod:`presence`, :mod:`etrangeres` : questions, présence du poste, cartes refusées ;
- :mod:`notifications`, :mod:`emetteur` : file, canaux Telegram et ntfy, passe de la passerelle ;
- :mod:`outils`, :mod:`invite` : les huit outils de l'agent et la section de prompt.
"""

from __future__ import annotations

NOM_CANONIQUE = "acp_poste_noyau"
