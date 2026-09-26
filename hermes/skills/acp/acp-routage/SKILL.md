---
name: acp-routage
description: "Choisir l'exécutant, le modèle et l'effort d'une étape ACP d'après le catalogue relevé du poste (poste_catalogue) : seulement des valeurs relevées, jamais un palier, jamais un effort interdit, relecture par l'autre exécutant."
---

# Routage des étapes ACP

Cette skill aide à remplir `voie`, `modele` et `effort` des étapes de `projet_planifier`. Elle ne donne accès à aucun outil. Le greffon résout de toute façon chaque étape de façon déterministe : surcharge du propriétaire, puis ton choix explicite, puis la table de routage ; sans solution, il refuse.

## Lire le catalogue

Appelle `poste_catalogue`. Pour chaque exécutant du poste (`poste-codex`, `poste-claude`) il donne la date du relevé, les modèles relevés, leurs efforts pris en charge et leur palier, les quotas s'ils sont connus. « Inconnu » veut dire que le poste n'a rien publié : aucune étape du poste n'est alors possible.

## Choisir

- Propose **seulement** un modèle et un effort qui figurent dans le relevé de l'exécutant choisi. Sans choix, le greffon prend la table de routage, sinon le modèle par défaut du relevé.
- Ne demande **jamais** de palier (`priority`, `fast`…) : il est fixé par la politique du propriétaire.
- Les efforts interdits par défaut (`max`, `ultra`, `ultracode`) sont refusés ; seul le propriétaire peut les lever.
- Un relevé périmé ou un quota inconnu est admis mais signalé ; un quota au-delà du seuil fait refuser le modèle.
- Pour une étape Hermes (`voie: hermes`), laisse le modèle vide : Hermes garde le modèle de son profil.

## Relecture croisée

Chaque étape du poste est relue par **l'autre** exécutant (`poste-codex` relu par `poste-claude`, et inversement). Si l'autre exécutant n'a pas de relevé, l'étape est refusée : ne contourne pas en demandant la même voie. `relecture_modele` choisit le modèle de la relecture, parmi ceux relevés de l'autre exécutant.

## Lire un refus

Un refus du greffon nomme la valeur fautive et ce qui est admis (efforts relevés, voies admises par la classe). Corrige le plan d'après lui plutôt que de réessayer la même chose.
