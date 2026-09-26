---
name: acp-orchestration
description: "Planifier un projet ACP : découper l'objectif en 1 à 12 étapes vérifiables, décider soi-même et l'écrire, appeler projet_planifier une seule fois puis kanban_complete. À charger sur la carte de planification."
---

# Orchestration d'un projet ACP

Cette skill guide la **carte de planification** d'un projet ACP. Tu travailles seul : le propriétaire a lancé le projet et suit son avancement plus tard. Tu ne crées **jamais** de carte toi-même : seul l'outil `projet_planifier` le fait, et le greffon fixe lui-même les exécutants, les modèles, la relecture croisée et la synthèse.

## Démarche

1. Lis la carte (`kanban_show`) : objectif, type de projet, dépôt, et, s'il y en a un, le résultat de l'exploration (la « carte du dépôt », voir `acp-exploration`).
2. Lis le catalogue du poste (`poste_catalogue`) si une étape doit être confiée au poste : exécutants, modèles et efforts **relevés** (voir `acp-routage`).
3. Découpe l'objectif en **1 à 12 étapes vérifiables**. Une étape = un livrable relisible (un module, une page, une note de recherche), avec une consigne précise et un critère de fin.
4. Décide toi-même tout ce qui peut l'être (noms, schémas, formats, bibliothèques, ordre) et écris-le dans `decisions` : chaque carte les reçoit. Ne reporte pas une préférence au propriétaire.
5. Ordonne par `depend_de` (références du même appel seulement) : une étape qui consomme le résultat d'une autre en dépend.
6. Appelle `projet_planifier` **une seule fois**, puis termine ta carte par `kanban_complete` avec un résumé du plan, sans `created_cards` inventés.

## Classes d'étapes

- `recherche_web`, et `architecture` ou `documentation` sans dépôt : exécutées par Hermes (recherche, lecture du web, rédaction).
- `implementation`, `debogage_tests`, `petite_tache` : exécutées par le poste, **sur dépôt seulement** ; chacune reçoit une relecture croisée par l'autre exécutant.
- `integration` (fusion locale des branches) : prévue à l'étape P6, refusée aujourd'hui.

## Sans poste

Tant que le poste n'est pas connecté, un projet sans dépôt n'a que des étapes Hermes : recherche, conception, rédaction. Ne planifie pas d'étape du poste « pour plus tard » : elle serait refusée.

## Plafonds

Par défaut : 3 tours de synthèse, 30 cartes par projet, 12 étapes par appel, 2 corrections par étape. Un plan qui les dépasse est refusé en entier : réduis-le. Au plafond des tours, ou quand plus aucun plan ne tient dans le plafond de cartes, une carte de décision (triage) est adressée au propriétaire : n'essaie pas de la contourner.

## Carte de décision

Si tu exécutes une carte de **triage** d'un projet ACP, c'est que le propriétaire a décidé : il a prolongé le plafond, ou relancé une planification restée sans plan. Sa consigne est à la fin de la carte (« Décision du propriétaire »). Si elle demande de continuer, planifie le tour suivant depuis cette carte avec `projet_planifier`, en suivant la même démarche ; sinon conclus. Termine toujours par `kanban_complete`.

Si aucun plan n'est possible (refus que tu ne peux pas lever), termine par `kanban_complete` en disant pourquoi : le greffon adresse alors une carte de décision au propriétaire.

## Refus

Si `projet_planifier` refuse, lis le message : il dit exactement quoi changer (référence inconnue, cycle, modèle absent du relevé, effort interdit…). Corrige le plan et rappelle l'outil ; ne force jamais un choix refusé.
