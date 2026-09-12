# Rapport d'acceptation

Date d'état : 12 septembre 2026
Périmètre évalué : Lot D (version `0.5.0`) implémenté localement sur la base du
Lot C `0.4.0`, sans service externe ni dépense réelle. Les publications GitHub —
PR, CI distante et tags — n'ont pas encore été effectuées.

## Verdict

**0 scénario sur 20 est encore accepté de bout en bout.** Treize scénarios
disposent d'une brique réelle et de tests ciblés ; sept restent non satisfaits. Le
Lot D rend le centre MCP, la bibliothèque de skills et le coffre de secrets
utilisables et testés, mais un `httpx.MockTransport` n'est pas un serveur MCP tiers,
un programme déterministe de test n'est pas une exécution Hermes réelle, et un cwd
dédié n'est pas une sandbox.

Le scénario 7 a toutefois été rejoué contre des services réellement démarrés (API
métier dans son propre processus, serveur MCP Streamable HTTP sur le bouclage) :
**24 étapes sur 24 réussies**. Son script est versionné
(`scripts/verify_mcp_journey.py`) et rejouable par un tiers. Ce parcours n'est
toutefois pas retenu comme « Accepté » : il ne couvre que le transport `http`, le
serveur interrogé a été écrit pour la vérification — ce n'est pas un serveur MCP
tiers — et il n'exerce aucun parcours navigateur.

Statuts : **Accepté** exige le parcours complet et reproductible ; **Partiel**
signifie qu'une brique réelle existe mais qu'un élément bloquant manque ; **Non
satisfait** signifie que le parcours principal n'est pas livré.

## Matrice des vingt scénarios

| # | Scénario | Statut | Preuve disponible et manque bloquant |
|---:|---|---|---|
| 1 | Première connexion sécurisée et reconnexion | **Partiel** | Bootstrap unique, Argon2id, session révocable/expirable, cookie `HttpOnly`, CSRF, restauration web et login CLI sont testés. Pas d'E2E navigateur sur services démarrés. |
| 2 | Connexion Hermes avec diagnostic d'échec exploitable | **Partiel** | Diagnostic typé et frontière serveur testés avec transports simulés. Aucune instance ni clé Hermes réelle. |
| 3 | Conversation persistante et reprise depuis web/CLI | **Partiel** | Conversations et tours sont persistés ; web et CLI reprennent par `GET`. Pas de streaming ni E2E Hermes réel. |
| 4 | Import d'un projet sans écrasement du travail existant | **Non satisfait** | Création de projet disponible, mais pas d'import de dépôt/dossier ni test produit de conflit. |
| 5 | Mission réellement exécutée par au moins un agent configuré | **Partiel** | Le worker lance un vrai processus local configuré, produit une preuve et échoue fermé. Seuls des programmes déterministes de test ont été lancés, pas un agent réel. |
| 6 | Isolation des fichiers, secrets et contexte entre deux projets | **Partiel** | RBAC et conversations inter-projets sont testés ; le runner filtre son enveloppe et son environnement ; le coffre du Lot D chiffre les secrets, limite une portée `project` à son projet et n'expose aucune valeur. Pas de sandbox OS ni de stockage privé. |
| 7 | Ajout, test, activation et révocation d'un MCP | **Partiel** | Parcours complet testé sur les deux transports : déclaration, refus d'un secret en clair, diagnostic HTTP épinglé, autorisation puis diagnostic `stdio` sur le runner désigné, rattachement limité à un sous-ensemble d'outils, activation, rollback, révocation et audit (`apps/api/tests/test_mcp_servers.py`, `apps/worker/tests/test_mcp_probe.py`). Le transport `http` a en outre été rejoué contre des services réellement démarrés : **24/24 étapes**, injection du secret observée côté serveur MCP et jamais republiée. Le script de ce parcours est versionné (`scripts/verify_mcp_journey.py`). Manque bloquant : aucun serveur MCP **tiers** contacté, aucun parcours navigateur, et le transport `stdio` reste prouvé par un serveur déterministe local. |
| 8 | Import d'un skill, affichage des fichiers et activation limitée | **Partiel** | Import manuel, dossier autorisé, archive et GitHub épinglé ; arborescence, `SKILL.md`, dépendances, licence et contrôle indicatif affichés ; approbation exigée quand la portée augmente ; activation sur le projet A absente des extensions du projet B ; révocation auditée (`apps/api/tests/test_skills.py`, `test_extensions.py`). Manque bloquant : aucun dépôt GitHub réel ni archive de skill tierce ; le transport GitHub est prouvé sur `httpx.MockTransport`. |
| 9 | Refus d'une installation ou d'une action non autorisée | **Partiel** | CSRF/RBAC et frontières worker sont testés ; le runner refuse avant spawn les autonomies non garanties et toute commande hors allowlist ; un opérateur ou un lecteur est refusé sur `/mcp/servers`, `/skills/import` et `/secrets`, un membre d'un autre projet sur un rattachement, un lancement `stdio` non autorisé n'est jamais distribué, et `GET /mcp/servers/{id}` ne nomme que les rattachements des projets accessibles. Manque bloquant : les refus sont prouvés sur des sources locales et un parcours API, pas sur une installation réelle ni un parcours navigateur. |
| 10 | Tests web avec résultat structuré et capture de la session réelle | **Non satisfait** | Reporté au Lot E ; les captures du shell ne sont pas une session Playwright observée. |
| 11 | Consultation d'une trace et d'une capture après échec | **Non satisfait** | Reporté au Lot E. |
| 12 | Déconnexion/reconnexion sans perte d'historique ni double lancement | **Partiel** | Idempotence durable des conversations et missions, commandes liées aux tentatives et reprise par lecture sont testées. Pas d'E2E de coupure réelle ni d'outbox. |
| 13 | Approbation, refus, expiration et arrêt réel d'une exécution | **Partiel** | Acceptation/refus, empreinte et expiration d'approbation, stop et arrêt d'arbre sont couverts. Le runner local refuse les actions nécessitant approbation au lieu de les demander. |
| 14 | Runner perdu puis reprise contrôlée sans double effet | **Partiel** | Lease, fencing, worker obsolète, interruption et nouvelle tentative sont testés. Aucun effet tiers réel ne permet de prouver l'absence de double effet externe. |
| 15 | Routine planifiée sans doublon et fuseau Europe/Paris | **Non satisfait** | Reporté au Lot F. |
| 16 | Livrable téléchargeable et aperçu 3D réel | **Non satisfait** | Métadonnées de preuve seulement ; reporté aux Lots E/G. |
| 17 | Génération d'image réelle si backend configuré | **Non satisfait** | Reporté au Lot G. |
| 18 | Budget atteint, fournisseur indisponible et stockage saturé | **Partiel** | Durée globale et panne provider échouent fermées ; coûts/tokens, appels outils et saturation ne sont pas encore appliqués de bout en bout. |
| 19 | Authentification des médias, événements et fichiers privés | **Partiel** | Écritures worker et ingestion d'événements sont authentifiées ; WebSocket anonyme fermé. Pas encore de média/fichier privé ou flux utilisateur. |
| 20 | Sauvegarde/restauration et migration de données existantes | **Non satisfait** | Upgrade SQLite ad hoc et non versionné, avec reconstruction contrôlée de tables et sauvegarde préalable requise ; PostgreSQL versionné et restauration reportés au Lot H. |

## Preuves de tests du Lot D

Les résultats ci-dessous proviennent du worktree `lot-d`, sans les modifications
Pixel/LimeZu locales hors périmètre. Ils ont été réexécutés le 12 septembre 2026
après les corrections de revue et la synchronisation des versions sur `0.5.0`.

### Environnement exact

| Élément | Valeur |
|---|---|
| Système | Windows 10 Pro `10.0.19045` |
| Interpréteur des suites | `.venv\Scripts\python.exe` — **lanceur d'environnement virtuel Windows**, Python `3.12.0` |
| Interpréteur de contrôle croisé | `.venv312\Scripts\python.exe`, Python `3.12.14` |
| Node.js / npm | `v24.19.0` / `11.17.0` |
| CI GitHub Actions (non exécutée pour ce lot) | `ubuntu-latest`, Python `3.12`, Node `22` (`.github/workflows/ci.yml`) |

L'interpréteur retenu n'est pas un détail : sous Windows, le `python.exe` d'un
environnement virtuel est un **lanceur** qui exécute l'interpréteur réel dans un
processus enfant. C'est exactement la topologie que le correctif Job Object devait
couvrir (voir plus bas).

### Suites exécutées

| Commande ou suite | Résultat | Ce que cela prouve | Limite |
|---|---:|---|---|
| `./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **1 033/1 033 réussis ; 2 avertissements de dépréciation connus** | API, worker, CLI, services et contrats Python | pas de service externe |
| tests API (`apps/api/tests`) | **389 tests** | coffre, politique de sortie, client MCP, parcours MCP et skills, extensions, RBAC | transports `httpx.MockTransport` et résolveur DNS injecté |
| tests worker (`apps/worker/tests`) | **164 tests** | processus réel, arrêt d'arbre, fencing, sonde MCP stdio, allowlist, environnement minimal et expurgation | serveur MCP stdio déterministe local |
| tests CLI (`apps/cli/tests`) | **280 tests** | groupes `secrets`, `mcp`, `skills`, `projects extensions`, refus de `--value` en argument, codes de sortie | client HTTP simulé |
| contrats, event-service et gateway | **200 tests** (104 contrats, 87 gateway, 9 event-service) | contrats partagés, règle d'expurgation, adaptateur Hermes et lecture native | transports simulés |
| `npm exec tsc -- --noEmit -p apps/web/tsconfig.json` | **réussi** | cohérence TypeScript | pas le comportement runtime |
| `npm test --workspace @acp/web` | **149/149 réussis (12 fichiers)** | clients et écrans MCP, skills, secrets et primitives d'interface | pas de navigateur réel |
| `npm test --workspace @acp/pixel-office-engine` | **74/74 réussis (7 fichiers)** | non-régression du moteur legacy | hors parcours principal |
| `npm run build:web` | **réussi** | bundle Vite productible | pas un déploiement |
| `./.venv/Scripts/python.exe scripts/check_version.py` | **réussi** | tous les composants publiables portent `0.5.0` | n'implique aucune publication |

Les deux avertissements Python proviennent de dépréciations Starlette/AnyIO dans les
dépendances et sont non bloquants. Le build Vite se termine avec un seul
avertissement, sur la taille du chunk Phaser (`1 231 kB` avant compression) ; ce n'est
pas un échec de compilation.

### Parcours de bout en bout contre des services réellement démarrés

`scripts/verify_mcp_journey.py` démarre l'API métier dans un processus séparé (base
SQLite isolée, clé de coffre éphémère) et un **serveur MCP Streamable HTTP réel** sur
le bouclage, puis rejoue le scénario 7 : **24 étapes sur 24 réussies**. Il n'est pas
exécuté en intégration continue ; il se lance à la demande :

```text
.venv/Scripts/python.exe scripts/verify_mcp_journey.py
```

Il prouve notamment que le serveur MCP a bien reçu l'en-tête `Authorization` portant
la valeur déchiffrée — l'injection n'est donc pas simulée — que cette valeur
n'apparaît ni dans la réponse de création du secret, ni dans la liste, ni dans la
configuration relue, ni dans l'export Hermes ; qu'un secret en clair dans un en-tête
est refusé (`422`) ; que l'activation est refusée sans découverte à jour (`409`) ;
qu'un outil non découvert est refusé (`422`) ; que le projet B ne voit pas le serveur
rattaché au projet A ; et qu'après révocation le projet A ne le voit plus alors que
l'historique reste consultable.

La politique de sortie n'a pas été désactivée pour ce test : l'hôte de bouclage a été
explicitement inscrit dans `ACP_OUTBOUND_PRIVATE_ALLOWLIST` et
`ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP=1` a été posé, ce qui exerce le chemin d'allowlist
auditée et l'opt-in `http` documentés, au lieu de contourner le contrôle. Ces deux
variables restent vides ou à `0` par défaut.

Limite assumée : ce script vit dans l'espace de travail de vérification, pas dans le
dépôt. Tant qu'il n'y est pas versionné, le scénario 7 reste **Partiel** et non
« Accepté ».

### Correctif Job Object et tests d'arbre de processus

Avec le lanceur d'environnement virtuel,
`apps/worker/tests/test_local_runner.py::test_normal_parent_exit_cannot_leave_a_background_child`
échouait **systématiquement** et
`::test_asyncio_cancellation_terminates_the_process_tree` par intermittence : un
petit-fils survivait, conservait les tubes hérités et le résultat devenait
`timed_out` / `output_stream_timeout`. L'énumération par filiation (Toolhelp,
`th32ParentProcessID`) ne rattache plus un petit-fils dont le parent intermédiaire —
le lanceur — a déjà quitté.

Le Lot D enferme désormais tout spawn du runner, et de la sonde MCP `stdio`, dans un
Job Object Windows : création suspendue, affectation revérifiée, `KILL_ON_JOB_CLOSE`
sans `BREAKAWAY_OK`, vacuité du job contrôlée à l'arrêt, et échec fermé en
`spawn_failed` / `job_assignment_failed` si l'affectation échoue. Les deux tests
passent désormais ; trois exécutions consécutives de
`apps/worker/tests/test_local_runner.py` ont rendu **34 tests réussis** à chaque fois.

Ces preuves sont locales, sur Windows. L'intégration continue les rejoue sur Ubuntu
avec Python `3.12.14` et Node `22` à chaque poussée ; c'est elle qui a révélé une
assertion d'environnement trop stricte, invisible sous Windows. Les Lots C et D sont
publiés (PR #3 et #4, tags `v0.4.0` et `v0.5.0`).

## Vérifications explicitement non exécutées

- serveur MCP **tiers** (HTTP ou stdio) : le seul serveur MCP réellement interrogé a
  été écrit pour la vérification et tournait sur le bouclage ;
- sonde `stdio` contre un serveur MCP tiers : les tests utilisent un serveur stdio
  déterministe local, et aucun runner distant réel n'a été enrôlé ;
- dépôt GitHub réel ou archive de skill tierce ;
- instance, modèle, mémoire, outils ou clé Hermes réels ;
- exécuteur Codex/Claude réel et effet externe sur un dépôt utilisateur ;
- E2E navigateur du bootstrap, d'une conversation, d'une mission, du centre MCP ou de
  la bibliothèque de skills ;
- PostgreSQL existant, migration versionnée, sauvegarde ou restauration ;
- sandbox OS/réseau, quotas CPU/mémoire/disque ou compte non privilégié dédié : le Job
  Object borne l'arbre de processus, il n'impose ni quota ni politique réseau ;
- appel d'outil MCP pendant une mission, Playwright, trace, stockage privé, média, 3D
  et automatisation ;
- CI distante, PR et tags des Lots C et D ;
- Railway, HTTPS public, charge ou audit offensif.

## Conditions avant exposition réseau

- terminer la matrice RBAC sur chaque ressource enfant, flux et fichier ;
- ajouter migrations PostgreSQL, stockage privé, sauvegarde/restauration et rotation ;
- isoler le runner au niveau OS/réseau et raccorder un circuit d'approbation worker ;
- exécuter les scénarios E2E contre les services réellement démarrés ;
- verser dans le dépôt le parcours de bout en bout du scénario 7, l'étendre au
  transport `stdio` et le rejouer contre un serveur MCP tiers, condition nécessaire
  pour passer ce scénario de **Partiel** à **Accepté** ;
- activer les tests externes uniquement par opt-in, avec secrets et budgets bornés.
