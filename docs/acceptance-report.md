# Rapport d'acceptation

Date d'état : 11 septembre 2026
Périmètre évalué : lot A en cours, sans service externe réel

## Verdict

**0 scénario sur 20 est accepté de bout en bout.** Six scénarios disposent d'une
brique partielle ou d'un test négatif pertinent, sans satisfaire leur parcours
complet. Les quatorze autres ne sont pas livrés. Les réussites unitaires ci-dessous
ne doivent pas être additionnées comme si elles formaient un test E2E.

Statuts utilisés :

- **Accepté** : parcours complet, stockage, contrôle d'accès, erreurs, tests et
  documentation vérifiés ;
- **Partiel** : une brique réelle existe ou un invariant ciblé est testé, mais le
  scénario complet échoue à la définition d'acceptation ;
- **Non satisfait** : parcours absent ou aucune preuve pertinente.

## Matrice des vingt scénarios

| # | Scénario | Statut | Preuve disponible et manque bloquant |
|---:|---|---|---|
| 1 | Première connexion sécurisée et reconnexion | **Non satisfait** | Aucun bootstrap propriétaire, système de session révocable ou reconnexion authentifiée. |
| 2 | Connexion Hermes avec diagnostic d'échec exploitable | **Partiel** | Adaptateur aligné sur les capacités, la santé détaillée et les Runs officiels avec 58 tests simulés ; aucune instance Hermes ni clé réelle n'a été utilisée. |
| 3 | Conversation persistante et reprise depuis web/CLI | **Non satisfait** | Conversations et CLI `acp` absents. |
| 4 | Import d'un projet sans écrasement du travail existant | **Non satisfait** | Le worktree modifié a été préservé pendant le lot A, mais aucun parcours d'import de projet ou test de conflit n'existe dans le produit. |
| 5 | Mission réellement exécutée par au moins un agent configuré | **Non satisfait** | Le worker n'a pas de backend réel raccordé ; la simulation finit désormais bloquée. |
| 6 | Isolation des fichiers, secrets et contexte entre deux projets | **Non satisfait** | Aucun test inter-projets, coffre de secrets ou sandbox runner. |
| 7 | Ajout, test, activation et révocation d'un MCP | **Non satisfait** | Centre MCP non implémenté. |
| 8 | Import d'un skill, affichage des fichiers et activation limitée | **Non satisfait** | Bibliothèque de skills non implémentée. |
| 9 | Refus d'une installation ou d'une action non autorisée | **Partiel** | Des appels worker non authentifiés sont refusés dans les 5 tests API ciblés ; aucune installation MCP/skill ni politique générale d'action n'est raccordée. |
| 10 | Tests web avec résultat structuré et capture de la session réelle | **Non satisfait** | Deux captures réelles du shell existent, mais aucun runner Playwright, reporter ou capture de la session de test. Les 27 tests web sont unitaires et ne couvrent pas ce parcours. |
| 11 | Consultation d'une trace et d'une capture après échec | **Non satisfait** | Pas de trace, capture, stockage d'objets ou replay. |
| 12 | Déconnexion/reconnexion sans perte d'historique ni double lancement | **Non satisfait** | Pas de curseur durable, outbox ni test de reconnexion E2E. |
| 13 | Approbation, refus, expiration et arrêt réel d'une exécution | **Partiel** | Modèles d'approbation et leases existent ; le provider manuel n'approuve plus par défaut. Aucun cycle complet ni arrêt d'un runner réel n'est testé. |
| 14 | Runner perdu puis reprise contrôlée sans double effet | **Partiel** | L'expiration d'un lease est testée : renouvellement tardif refusé puis, lors de la réconciliation, run `interrupted`, tâche et agent `blocked`, événement durable `task.interrupted`, capacité libérée, sans reprise automatique. Restent runner réel, fencing token, reprise contrôlée et preuve d'absence de double effet externe. |
| 15 | Routine planifiée sans doublon, avec tests de fuseau horaire | **Non satisfait** | Automatisations et scheduler propriétaire unique non livrés. |
| 16 | Livrable téléchargeable et aperçu 3D avec un fichier de test réel | **Non satisfait** | Artefacts limités à des métadonnées/chemins ; aucun téléchargement privé ou visualiseur 3D. |
| 17 | Génération d'image réelle lorsque le backend est configuré | **Non satisfait** | Aucun backend média raccordé. |
| 18 | Budget atteint, fournisseur indisponible et stockage saturé | **Partiel** | Le fournisseur indisponible échoue fermé dans les 7 tests ciblés ; budgets et saturation du stockage ne sont pas implémentés. |
| 19 | Authentification des médias, événements et fichiers privés | **Partiel** | L'ingestion `task.*` d'un worker exige identité et lease ; les flux, médias et fichiers privés restent non protégés de bout en bout. |
| 20 | Sauvegarde/restauration et migration sur des données de test existantes | **Non satisfait** | Pas de migrations versionnées, sauvegarde ou restauration testée. |

## Preuves de tests disponibles

| Commande ou suite | Résultat connu | Ce que cela prouve | Ce que cela ne prouve pas |
|---|---:|---|---|
| `npm test --workspace @acp/web` | **27/27 réussis** | logique du shell moderne, API web et états couverts par ses tests | navigateur réel, accessibilité automatisée, E2E ou capture |
| `npm test --workspace @acp/pixel-office-engine` | **117/117 réussis** | absence de régression détectée dans le moteur legacy | chargement par défaut, Studio ou parcours moderne |
| `python -m pytest -q apps/api/tests/test_workers.py` | **5/5 réussis** | identité worker, claims/leases et refus ciblés du parcours testé | RBAC utilisateur, toutes les routes ou concurrence de production |
| `python -m pytest -q apps/worker/tests/test_gateway_fail_closed.py services/provider-gateway/tests/test_manual_provider.py` | **7/7 réussis** | panne/JSON invalide/absence de verdict sans faux succès, simulation bloquée, manuel non approuvé | service Hermes réel ou exécution réelle |
| tests du provider Hermes | **58/58 réussis** | contrats Runs, readiness/capacités, idempotence, délais et sorties strictes sur transport simulé | instance, modèle, mémoire ou outils Hermes réels |
| `python -m pytest -q` sur l'état final du lot | **78/78 réussis** | ensemble des tests Python, dont Hermes, API worker, fail-closed et event-sdk | service externe, E2E, PostgreSQL ou production |
| `npm exec tsc -- --noEmit -p apps/web/tsconfig.json` | **réussi** | cohérence TypeScript du web et des contrats importés | comportement navigateur ou API réelle |
| `npm run build:web` | **réussi, 45 modules** | production du shell et séparation du chunk Phaser legacy | déploiement ou absence de chargement réseau dans tous les navigateurs |
| parcours navigateur local | **réussi sur les états ciblés** | accueil sombre, Missions mobile clair, non configuré et panne API ; deux PNG conservés | E2E de mission, accessibilité complète ou Studio |

La suite Python a émis **deux warnings de dépendances Starlette/FastAPI** : usage
transitoire de `httpx` au lieu de `httpx2` par `TestClient`, et alias AnyIO déprécié.
Ils ne rendent pas les tests rouges, mais doivent être éliminés par un jeu de versions
de test verrouillé plutôt que masqués.

## Vérifications explicitement non exécutées

- aucune connexion à une instance Hermes réelle ;
- aucun lancement d'un agent ou runner réel ;
- aucun navigateur de mission, test E2E ou capture du Studio ; le shell seul a été
  vérifié dans un navigateur local ;
- aucun test MCP, skill, conversation, CLI, média, 3D ou automatisation ;
- aucun test PostgreSQL, migration, sauvegarde ou restauration ;
- aucun déploiement Railway ou autre déploiement externe ;
- aucun test de charge, sécurité offensive ou audit de dépendances final.

## État réel

### Réalisé/vérifié

- 27 tests web, 117 tests du moteur legacy et 78 tests Python sont réussis sur le
  même état du dépôt ; typecheck et build web réussissent.
- Les scénarios sont inventoriés avec un manque bloquant explicite.

### Réalisé, non testé réel

- Le shell moderne a été validé dans un navigateur local ; l'adaptateur Hermes
  officiel existe au niveau code, sans connexion Hermes réelle.

### Non configuré

- identités externes, clé Hermes, runner réel, stockage privé, PostgreSQL,
  migrations, Railway, MCP/skills, Playwright et fournisseurs médias.

### Restant

- corriger les deux warnings Starlette ;
- ajouter les tests intégration, contrats réels opt-in et E2E par lot ;
- ne passer un scénario à **Accepté** qu'après preuve complète et reproductible.
