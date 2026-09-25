---
name: acp-profils
description: "Réglages prêts d'ACP par type de projet (base, site web, recherche, données) : quelles skills et quels serveurs MCP utiliser sur Railway, et ce qui relève du poste Windows (reporté). À charger avant de choisir des skills pour un projet."
---

# Profils de projet ACP

Le catalogue d'ACP est épinglé dans l'image (fichier `catalogue.lock.json`) et change seulement par une modification relue du dépôt. Cette skill dit quelles skills charger selon le type de projet. Elle ne donne accès à aucun outil.

Sur Railway, tu n'as **aucun outil d'exécution** (ni terminal, ni fichiers, ni code, ni navigateur) : les skills ci-dessous servent à concevoir, relire, cadrer et rédiger. Tout ce qui exige d'exécuter, de lire un dépôt ou de piloter un navigateur relève du **poste** Windows du propriétaire, qui n'est pas encore branché : dis-le, ne le simule pas.

Une skill citée ici n'est utilisable que si elle figure dans ta liste de skills ; sinon, dis qu'elle est absente. Les skills vendorisées sont en anglais : tu réponds quand même en français.

## Base (tous les projets)

- Skills : `acp-redaction`, `acp-profils`, `hermes-agent`.
- MCP : `context7` (documentation à jour des bibliothèques), si ses outils te sont proposés.

## Site web

Base, plus :

- conception et finition : `emil-design-eng`, `apple-design`, `mobile-native` ;
- mouvement : `animate`, `animation-vocabulary` ;
- choix de bibliothèques : `pick-ui-library`, `ask-sonner` ;
- direction visuelle : `design-taste-frontend`, `minimalist-ui`, `high-end-visual-design` ;
- maquette HTML autonome : `claude-design` ;
- solidité : `security-review`, `accessibility`.

Reporté au poste (étape P8, pas encore disponible) : `find-animation-opportunities`, `improve-animations`, `review-animations`, `prototype`, `redesign-existing-projects`, `production-audit`, `browser-qa`, `e2e-testing`, `canary-watch`, `benchmark`, et les serveurs MCP Playwright et Figma. Ils lisent le code d'un dépôt, pilotent un navigateur ou mesurent un site déployé.

## Recherche

Base, plus : `arxiv`, `competitor-news-monitor`.

Cite chaque source par son adresse et distingue ce qui est établi de ce qui est supposé. Une veille planifiée (tâche récurrente) n'est pas disponible sur Railway : propose un compte rendu ponctuel.

## Données

Base, plus : `mle-workflow`, `python-patterns`.

L'exécution d'un code d'analyse ou d'entraînement relève de l'environnement Python du poste (étape P6, pas encore branché) : sur Railway, tu cadres la démarche, les contrôles et les critères d'évaluation.

## Choisir

1. Identifie le type de projet ; s'il est mixte, cumule les profils.
2. Charge seulement les skills utiles à la question posée, pas tout le profil.
3. Si la demande exige une skill ou un outil du poste, dis-le clairement et propose ce qui est faisable ici.
