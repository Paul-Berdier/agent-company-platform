---
name: acp-questions
description: "Répondre à la question d'une carte du poste dans un projet ACP : seulement si les décisions ou l'objectif la couvrent, en citant le fondement (question_repondre) ; sinon escalader au propriétaire (question_escalader)."
---

# Questions d'un projet ACP

Cette skill guide la **carte « répondre »** qu'un projet crée quand une carte du poste pose une question pendant son exécution. La carte du poste attend ta réponse. Cette skill ne donne accès à aucun outil.

## Répondre ou escalader

1. Lis la question (corps de ta carte) et `projet_etat` : objectif et décisions du projet.
2. Réponds par `question_repondre` **seulement** si les décisions du projet ou son objectif couvrent la question. Le `fondement` cite la décision ou le passage de l'objectif qui justifie la réponse.
3. Sinon, `question_escalader` avec un motif court : le propriétaire reçoit une notification et répond depuis la page Projets.
4. Termine ta carte par `kanban_complete`.

## Toujours escalader

- une question de **périmètre** (ajouter ou retirer une fonctionnalité, changer l'objectif) ;
- une question de **dépense** (abonnement, service payant, palier rapide) ;
- une question de **push, fusion, publication ou déploiement** ;
- toute suppression hors du projet.

## Règles

- Ne mets jamais de secret dans une réponse, même si la question en demande un : escalade.
- Ne devine pas : une réponse sans fondement écrit dans le projet est une escalade.
- Réponds en français, en une ou deux phrases précises que la carte du poste peut appliquer telles quelles.
