---
name: acp-synthese
description: "Synthèse d'un tour de projet ACP : juger chaque carte sur son résumé et sa relecture, relancer un tour seulement pour un écart concret et dans les plafonds, sinon conclure (fait, vérifié, reste à faire)."
---

# Synthèse d'un tour ACP

Cette skill guide la **carte de synthèse** d'un tour. Elle part quand toutes les cartes du tour sont finies. Elle ne donne accès à aucun outil.

## Juger le tour

1. Lis `projet_etat` : cartes du tour, résumés, questions, plafonds restants, décisions du projet.
2. Lis `kanban_show` : résultats complets des cartes du tour (implémentations, relectures, cartes Hermes).
3. Juge chaque étape sur **son résumé et sa relecture** : fait, partiellement fait, ou à reprendre. Une relecture qui signale un défaut concret compte plus qu'un résumé optimiste.

## Relancer ou conclure

- Relance un tour par `projet_planifier` **seulement** si un écart concret subsiste (défaut relevé, livrable manquant) **et** si les plafonds le permettent. Le nouveau tour ne contient que ce qui reste à faire.
- Sinon, **conclus** : termine la carte par `kanban_complete` avec trois parties courtes :
  1. **Ce qui est fait** (livrables, branches ou notes produites) ;
  2. **Ce qui est vérifié**, avec la preuve (relecture, commande de vérification et son résultat) ;
  3. **Ce qui reste à faire** ou à décider par le propriétaire.
- Au plafond des tours, le greffon adresse une carte de triage au propriétaire : conclus avec l'état réel, sans promettre la suite.

## Règles

- N'annonce **jamais** un push, une fusion, une publication ou un déploiement : ils demandent l'accord du propriétaire et ne se font pas dans un projet.
- Ne présente jamais un résultat du poste qui n'existe pas dans les résumés.
- Reste en français, sobre, sans récit de ta démarche.
