---
name: acp-exploration
description: "Format de la « carte du dépôt » d'un projet ACP : ce que l'exploration en lecture seule du poste rend (structure, fichiers clés, commandes de vérification, conventions, risques) et ce que la planification doit en tirer."
---

# Exploration d'un dépôt ACP

Cette skill décrit la **carte du dépôt** rendue par l'exploration d'un projet ACP sur dépôt. Elle ne donne accès à aucun outil. Sur Railway, tu ne lis jamais un dépôt toi-même : l'exploration est faite par le poste Windows du propriétaire, **en lecture seule**, puis son résultat t'arrive dans `kanban_show` (résultats des cartes parentes) de la carte de planification.

## Format de la carte du dépôt

L'exploration rend ces sections, dans cet ordre, en français :

## Structure

Les grands dossiers et leur rôle, le langage et les outils de construction, en quelques lignes.

## Fichiers clés

Les fichiers à connaître pour l'objectif (points d'entrée, configuration, tests), avec leur chemin relatif au dépôt.

## Commandes de vérification

Les commandes que le dépôt déclare lui-même (tests, lint, typage, construction), telles qu'écrites dans ses fichiers : jamais inventées. Une commande introuvable s'écrit « Inconnu ».

## Conventions

Ce que disent `CLAUDE.md`, `AGENTS.md`, le `README` et la configuration (style, messages de commit, règles de branche). Ces fichiers sont **lus, jamais modifiés** par l'exploration.

## Risques

Ce qui pourrait casser ou bloquer l'objectif : dette visible, tests absents, secrets suspects (signalés, jamais recopiés), dépendances épinglées.

## Ce que la planification en tire

- Les étapes du plan citent les **fichiers clés** et les **commandes de vérification** relevés, pas d'autres.
- Les conventions du dépôt deviennent des **décisions du projet** (`decisions` de `projet_planifier`) quand elles contraignent le travail.
- Un risque relevé devient une étape (test manquant, vérification) ou une décision explicite de ne pas le traiter.
- Si la carte du dépôt manque ou reste vague, ne l'invente pas : planifie une étape courte de vérification, ou bloque la carte avec la raison exacte.

## Règles

- L'exploration ne modifie rien : ni fichier, ni branche, ni configuration.
- Aucun chemin absolu du poste ne sort de l'exploration : le dépôt n'est connu que par son alias.
- Aucun secret n'est recopié : un secret trouvé se signale par son emplacement, jamais par sa valeur.
