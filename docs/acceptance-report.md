# Rapport d'acceptation

Date d'état : 11 septembre 2026
Périmètre évalué : Lot B `0.3.0` vérifié localement, sans service externe réel

## Verdict

**0 scénario sur 20 est accepté de bout en bout.** Dix scénarios disposent désormais
d'une brique partielle ou d'un test d'intégration ciblé pertinent, sans satisfaire
leur parcours complet. Les dix autres ne sont pas livrés. En particulier, les tests
API et TypeScript séparés ne constituent pas un E2E navigateur, et les transports
Hermes simulés ne constituent pas une connexion réelle.

Statuts utilisés :

- **Accepté** : parcours complet, stockage, contrôle d'accès, erreurs, tests et
  documentation vérifiés ;
- **Partiel** : une brique réelle existe ou un invariant ciblé est testé, mais le
  scénario complet échoue à la définition d'acceptation ;
- **Non satisfait** : parcours absent ou aucune preuve pertinente.

## Matrice des vingt scénarios

| # | Scénario | Statut | Preuve disponible et manque bloquant |
|---:|---|---|---|
| 1 | Première connexion sécurisée et reconnexion | **Partiel** | Bootstrap propriétaire unique, Argon2id, session opaque hachée/révocable/expirable, cookie `HttpOnly`, rotation CSRF, restauration web et déconnexion sont implémentés et couverts séparément côté API et client TypeScript. Aucun E2E navigateur n'enchaîne encore le premier accès, le rechargement puis la reconnexion sur les services démarrés. |
| 2 | Connexion Hermes avec diagnostic d'échec exploitable | **Partiel** | Le diagnostic typé distingue absence de configuration, refus, timeout, incompatibilité et réponse invalide ; le web passe par l'API authentifiée et n'obtient aucun secret. Les tests utilisent un faux gateway ou `MockTransport` : aucune instance Hermes ni clé réelle n'a été utilisée. |
| 3 | Conversation persistante et reprise depuis web/CLI | **Partiel** | Conversation générale/projet, tours, réponse, usage et identifiants provider sont persistés ; l'interface web envoie puis reprend par polling `GET`. Le CLI `acp`, le streaming, les pièces jointes et un E2E avec Hermes réel sont absents. |
| 4 | Import d'un projet sans écrasement du travail existant | **Non satisfait** | Le worktree modifié a été préservé pendant le lot A, mais aucun parcours d'import de projet ou test de conflit n'existe dans le produit. |
| 5 | Mission réellement exécutée par au moins un agent configuré | **Non satisfait** | Le worker n'a pas de backend réel raccordé ; la simulation finit désormais bloquée. |
| 6 | Isolation des fichiers, secrets et contexte entre deux projets | **Partiel** | Les listes métier sont filtrées par membership, les conversations projet exigent le rôle adapté et une conversation générale d'un autre utilisateur est masquée dans les tests ciblés. Il n'existe encore ni fichier privé, coffre de secrets, sandbox runner, ni test d'isolation de ces ressources entre deux projets. |
| 7 | Ajout, test, activation et révocation d'un MCP | **Non satisfait** | Centre MCP non implémenté. |
| 8 | Import d'un skill, affichage des fichiers et activation limitée | **Non satisfait** | Bibliothèque de skills non implémentée. |
| 9 | Refus d'une installation ou d'une action non autorisée | **Partiel** | Les mutations web sans session/CSRF ou avec rôle lecteur sont refusées ; les identités worker et les appels au gateway sont séparément authentifiés. Aucune installation MCP/skill ni politique générale d'action sensible n'est encore raccordée. |
| 10 | Tests web avec résultat structuré et capture de la session réelle | **Non satisfait** | Deux captures réelles du shell existent, mais aucun runner Playwright, reporter ou capture de la session de test. Les 19 tests web versionnés sont unitaires et ne couvrent pas ce parcours. |
| 11 | Consultation d'une trace et d'une capture après échec | **Non satisfait** | Pas de trace, capture, stockage d'objets ou replay. |
| 12 | Déconnexion/reconnexion sans perte d'historique ni double lancement | **Partiel** | La déconnexion révoque la session sans supprimer les conversations. Un `client_request_id` unique et une clé d'idempotence persistée permettent de reprendre une soumission incertaine avec le même Run logique ; le statut est relu par `GET`. Il manque un E2E déconnexion/reconnexion complet, l'outbox, un curseur d'événements et la preuve contre Hermes réel. |
| 13 | Approbation, refus, expiration et arrêt réel d'une exécution | **Partiel** | Modèles d'approbation et leases existent ; le provider manuel n'approuve plus par défaut. Aucun cycle complet ni arrêt d'un runner réel n'est testé. |
| 14 | Runner perdu puis reprise contrôlée sans double effet | **Partiel** | L'expiration d'un lease est testée : renouvellement tardif refusé puis, lors de la réconciliation, run `interrupted`, tâche et agent `blocked`, événement durable `task.interrupted`, capacité libérée, sans reprise automatique. Restent runner réel, fencing token, reprise contrôlée et preuve d'absence de double effet externe. |
| 15 | Routine planifiée sans doublon, avec tests de fuseau horaire | **Non satisfait** | Automatisations et scheduler propriétaire unique non livrés. |
| 16 | Livrable téléchargeable et aperçu 3D avec un fichier de test réel | **Non satisfait** | Artefacts limités à des métadonnées/chemins ; aucun téléchargement privé ou visualiseur 3D. |
| 17 | Génération d'image réelle lorsque le backend est configuré | **Non satisfait** | Aucun backend média raccordé. |
| 18 | Budget atteint, fournisseur indisponible et stockage saturé | **Partiel** | Le fournisseur indisponible échoue fermé dans les 7 tests ciblés ; budgets et saturation du stockage ne sont pas implémentés. |
| 19 | Authentification des médias, événements et fichiers privés | **Partiel** | L'ingestion `task.*` exige identité/lease côté API, l'appel API → event-service exige un Bearer interne et le WebSocket anonyme est fermé par défaut. Aucun canal temps réel utilisateur authentifié ni média/fichier privé avec URL bornée n'est livré. |
| 20 | Sauvegarde/restauration et migration sur des données de test existantes | **Non satisfait** | Pas de migrations versionnées, sauvegarde ou restauration testée. |

## Preuves de tests disponibles

La vérification finale a été exécutée dans un worktree détaché sur le commit de
code/version `df39634`, sans les modifications Pixel/LimeZu non commitées du
worktree principal. Les résultats ci-dessous appartiennent donc à la branche du Lot
B et non à l'état local élargi.

| Commande ou suite | Résultat connu | Ce que cela prouve | Ce que cela ne prouve pas |
|---|---:|---|---|
| `npm test --workspace @acp/web` | **28/28 réussis, 5 fichiers** | shell, clients auth/conversation, cookies inclus, absence de Bearer navigateur, CSRF, contrats et polling | rendu navigateur et chaîne web → API → gateway → Hermes réel |
| `npm test --workspace @acp/pixel-office-engine` | **74/74 versionnés réussis** | absence de régression détectée dans le moteur legacy publié avec le lot | chantier pixel local non inclus, Studio ou parcours moderne |
| `python -m pytest -q apps/api/tests/test_workers.py` | **5/5 réussis** | identité worker, claims/leases et refus ciblés du parcours testé | RBAC utilisateur, toutes les routes ou concurrence de production |
| `apps/api/tests/test_auth.py` | **réussis dans la suite 121/121** | bootstrap, hachages, session, expiration, CSRF, révocation et refus de l'en-tête d'identité forgé | navigateur, HTTPS ou déploiement multi-processus |
| `apps/api/tests/test_conversations.py` | **réussis dans la suite 121/121** | persistance SQLite, relecture, idempotence, confidentialité générale, rôle lecteur, diagnostic et onboarding | Hermes réel, CLI, streaming, fichiers/secrets inter-projets ou PostgreSQL |
| `services/provider-gateway/tests/test_gateway_hermes_runs.py` | **réussis dans la suite 121/121** | Bearer inter-services, diagnostic typé, idempotence fournie par l'appelant et lecture unitaire de Run | instance, modèle, mémoire ou outils Hermes réels |
| `apps/event-service/tests/test_security.py` | **réussis dans la suite 121/121** | Bearer d'ingestion, fermeture sans secret et refus du WebSocket anonyme par défaut | flux utilisateur authentifié, historique durable ou reprise par curseur |
| `python -m pytest -q apps/worker/tests/test_gateway_fail_closed.py services/provider-gateway/tests/test_manual_provider.py` | **7/7 réussis** | panne/JSON invalide/absence de verdict sans faux succès, simulation bloquée, manuel non approuvé | service Hermes réel ou exécution réelle |
| tests du provider Hermes | **58/58 réussis** | contrats Runs, readiness/capacités, idempotence, délais et sorties strictes sur transport simulé | instance, modèle, mémoire ou outils Hermes réels |
| `python -m pytest -q` | **121/121 réussis, 2 warnings** | suite Python complète du Lot B dans le worktree propre | service externe, E2E, PostgreSQL ou production |
| `npm exec tsc -- --noEmit -p apps/web/tsconfig.json` | **réussi** | cohérence TypeScript du web et des contrats importés | comportement navigateur ou API réelle |
| `npm run build:web` | **réussi, 40 modules** | production du shell, écrans Lot B et séparation du chunk Phaser legacy | déploiement ou présence locale des assets LimeZu licenciés |
| `npm audit` après `npm ci` | **0 vulnérabilité connue** | lockfile Vite `8.3.0` / Vitest `5.0.0` contrôlé par le registre npm | vulnérabilités futures ou dépendances Python |
| parcours navigateur local | **réussi sur les états ciblés** | accueil sombre, Missions mobile clair, non configuré et panne API ; deux PNG conservés | E2E de mission, accessibilité complète ou Studio |

La suite Python du Lot B a émis **deux warnings de dépendances Starlette/FastAPI** : usage
transitoire de `httpx` au lieu de `httpx2` par `TestClient`, et alias AnyIO déprécié.
Ils ne rendent pas les tests rouges, mais doivent être éliminés par un jeu de versions
de test verrouillé plutôt que masqués.

Le build propre conserve six URLs d'assets d'interface LimeZu non résolues au build.
Ces fichiers licenciés ne sont volontairement pas versionnés ; le shell moderne ne
les requiert pas, mais le mode legacy doit les installer localement pour les afficher.

## Vérifications explicitement non exécutées

- aucune connexion à une instance Hermes réelle ;
- aucun lancement d'un agent ou runner réel ;
- aucun E2E navigateur du bootstrap, de la reconnexion, d'une mission ou d'une
  conversation ; le shell du Lot A seul a été vérifié dans un navigateur local ;
- aucun test de conversation contre Hermes réel, ni test CLI, MCP, skill, média, 3D
  ou automatisation ;
- aucun test PostgreSQL, migration, sauvegarde ou restauration ;
- aucun déploiement Railway ou autre déploiement externe ;
- aucun test de charge ou audit de sécurité offensif.

## État réel

### Réalisé/vérifié

- Le Lot B compte 28 tests web, 74 tests moteur et 121 tests Python réussis sur le
  worktree propre ; le typecheck, le build web à 40 modules et la synchronisation de
  version `0.3.0` réussissent aussi.
- `npm ci` suivi de `npm audit` signale zéro vulnérabilité connue au moment de cette
  vérification.
- Les vingt scénarios sont inventoriés avec un manque bloquant explicite.

### Réalisé, non testé réel

- Le shell moderne du Lot A a été validé dans un navigateur local. Les écrans Lot B,
  le diagnostic et la conversation existent au niveau code, sans E2E navigateur ni
  connexion Hermes réelle.

### Non configuré

- clé/instance Hermes, runner réel, stockage privé, PostgreSQL validé, migrations,
  Railway, CLI, MCP/skills, Playwright et fournisseurs médias.

### Restant

- corriger les deux warnings Starlette ;
- ajouter le contrat réel opt-in Hermes et les E2E navigateur/CLI ;
- ne passer un scénario à **Accepté** qu'après preuve complète et reproductible.
