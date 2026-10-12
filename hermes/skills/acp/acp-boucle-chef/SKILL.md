---
name: acp-boucle-chef
description: "Coordonner un projet ACP : déléguer, vérifier les résultats réels et reprendre seulement un écart concret dans les plafonds du propriétaire."
---

# Boucle du chef ACP

Cette compétence décrit le chef de projet Hermes déjà branché au greffon ACP et au planificateur de cartes. Elle n’installe aucun plugin Ponytail, processus ni boucle autonome supplémentaire. Elle ne donne aucun accès au terminal, aux fichiers, au navigateur ou aux comptes du poste.

## Lancer et déléguer

Dans une discussion, un travail de plusieurs étapes passe par `projet_lancer`. Sur une carte de planification, lisez `kanban_show`, `projet_etat`, `poste_etat` et `poste_catalogue` si un dépôt intervient. Les outils ACP se décrivent par `tool_describe`, puis s’appellent par `tool_call` ; leurs paramètres réels font foi.

Définissez des livrables avec critères observables et dépendances. Appelez `projet_planifier` une fois pour le tour. Le greffon applique la table de routage autorisée, choisit les exécutants, ajoute la relecture croisée et crée la synthèse. Ne créez aucune carte directement et ne contournez pas un refus par un autre modèle, compte ou outil. Une préférence du plan ne vaut jamais un verrou du propriétaire. Terminez la carte par `kanban_complete` avec le plan réellement créé.

## Vérifier avant de reprendre

La synthèse attend les cartes du tour. Comparez leurs résumés et relectures aux critères avec `projet_etat` et `kanban_show`. Distinguez livraison produite, tests réellement exécutés, résultats incomplets, échecs et contrôles impossibles. Une tâche planifiée, en attente ou replanifiée n’est pas un succès. Ne transformez pas un avis « Ship » en preuve de tests ni en autorisation de fusion.

S’il reste un défaut concret et que les plafonds le permettent, planifiez uniquement la reprise nécessaire. Une correction reçoit sa relecture ; aucune répétition sans critère nouveau et vérifiable. Sinon concluez par `kanban_complete` : fait, vérifié avec preuve, reste à faire.

## Budget et décision humaine

L’état du projet est la source des limites. Par défaut, le greffon borne à trois tours, trente cartes et deux corrections par étape ; une planification comporte au plus douze étapes. Ces plafonds limitent le travail, pas un montant monétaire. Aucun budget en euros, nombre de jetons ou contrôle de dépense non mesuré ne doit être inventé.

Au plafond, ou si aucun plan recevable n’est possible, décrivez le blocage et laissez la carte de décision au propriétaire. Lui seul peut prolonger ou conclure. Respectez l’arrêt, la pause et les quotas réellement signalés. Ne recréez pas un projet pour contourner une limite. Une publication, un push, une dépense ou un élargissement du périmètre requiert sa décision ; aucun verdict de skill ne la remplace.
