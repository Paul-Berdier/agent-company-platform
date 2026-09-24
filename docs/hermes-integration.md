# Intégration Hermes Agent

Date de référence : 23 septembre 2026
Version supportée : Hermes Agent `0.21.1`, tag de publication `v2026.9.7`
Statut : admission durable, lecture et arrêt des Runs implémentés et testés sur
transport simulé. Une instance locale isolée a été jointe en diagnostic uniquement,
sans modèle configuré ni création de Run.

## Surface retenue

La plateforme n'appelle plus les anciennes routes supposées `/v1/plans`,
`/v1/evaluations` ou `/v1/summaries`. Le provider `hermes` utilise uniquement :

```text
GET  /health/detailed
GET  /v1/capabilities
POST /v1/runs
GET  /v1/runs/{run_id}
POST /v1/runs/{run_id}/stop
```

La surface a été vérifiée dans la
[documentation API Server officielle](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
et la version dans les
[releases Hermes Agent](https://github.com/NousResearch/hermes-agent/releases).
L'API Runs est une frontière serveur : la clé Hermes ne va ni au navigateur, ni au
worker. Le worker et l'API appellent le provider-gateway avec un jeton inter-services
distinct ; seul le gateway détient `HERMES_API_KEY`.

## Architecture et traduction

```text
navigateur → API authentifiée → conversation et tour persistés
                              → provider-gateway (Bearer interne)
                                  → readiness + capacités Hermes
                                  → création d'un Run idempotent
                              ← identifiant et état d'admission
navigateur → API (polling GET) → lecture unique du Run via le gateway
                              → réponse et usage persistés

worker ───────────────────────→ provider-gateway (Bearer interne)
                              → admission plan/évaluation, puis lecture du résultat
```

Le gateway conserve son contrat d'orchestration historique pour limiter la migration
du métier. Chaque opération devient toutefois explicitement un Run Hermes :

| Opération plateforme | Run Hermes | Sortie requise |
|---|---|---|
| `plan` | instructions de planification + objectif/contexte JSON non fiable | objet JSON strict contenant au moins une étape et un graphe acyclique |
| `revise` | plan courant + retour + contexte | plan complet révisé, même validation |
| `evaluate` | résultat, critères et preuves fournis | booléen JSON strict, score 0..1 et retour |
| `summarize` | items de contexte autorisés | texte non vide |

Hermes reste la source de vérité de son Run et de sa session pendant l'exécution. La
plateforme conserve les identifiants de rapprochement et son propre historique
métier. En l'absence d'`external_session_id`, l'adaptateur construit un identifiant
déterministe namespacé par organisation, espace, projet, équipe, agent et session ;
il ne réutilise pas un transcript d'un autre scope.

L'admission asynchrone couvre les conversations et les opérations `plan` et
`evaluate`. Le worker conserve la clé par tentative et opération, puis le `run_id`
avant de lire son résultat. Les routes historiques synchrones restent disponibles,
mais exigent elles aussi une clé stable fournie par l'appelant : une répétition ne
crée plus une nouvelle identité d'opération.

L'API plateforme persiste conversation, tour, clé d'idempotence, `run_id`, sortie et
usage ; elle utilise un identifiant de session Hermes stable par conversation.
`GET /conversations/{conversation_id}/turns/{turn_id}` réconcilie les états
`submitting`, `running`, `waiting_for_approval` et `stopping`. Ce mécanisme n'est
ni du streaming, ni un journal d'événements Hermes.

Le flux SSE et le journal durable livrés au Lot E portent sur les **tentatives de
mission**, pas sur les conversations Hermes : ils diffusent les événements que la
plateforme écrit elle-même. Aucun événement SSE d'Hermes n'est consommé ni normalisé à
ce jour.

## Frontière interne du provider-gateway

Seul `GET /health` est public. Toutes les routes `/v1/*`, y compris le diagnostic,
les providers manuels et les Runs, exigent exactement :

```text
Authorization: Bearer <ACP_GATEWAY_SERVICE_TOKEN>
```

Sans jeton configuré, le gateway renvoie `503` ; avec un jeton absent ou incorrect,
il renvoie `401`. Le navigateur n'appelle pas cette surface. Les routes utilisateur
de l'API plateforme exigent une session valide, et les mutations un jeton CSRF.

## Admission fail-closed

Avant chaque Run, l'adaptateur exige :

- une configuration URL + clé complète ;
- `/health/detailed` globalement `ok`, readiness `ok`, gateway `running` ;
- les checks `state_db`, `config`, `model`, `disk`, `gateway` et
  `background_queues`, tous `ok` ;
- la version exacte `0.21.1` ;
- authentification Bearer requise ;
- soumission, consultation et arrêt de Runs disponibles (`run_stop`) ;
- idempotence annoncée comme durable, avec au moins 86 400 secondes de conservation.

Un serveur vivant sur `/health` mais sans modèle, mémoire ou gateway prêt est donc
indisponible pour la plateforme. Une capacité manquante, un redirect, un 4xx, un
429, un terminal `failed/cancelled/interrupted`, un timeout ou une réponse invalide
échoue explicitement. Les 5xx et erreurs réseau sont relancés dans la limite
configurée en conservant la même `Idempotency-Key`.

Les sorties structurées refusent les fences Markdown, clés dupliquées, `NaN`,
coercitions booléennes, champs supplémentaires, scores hors bornes, étapes
dupliquées, dépendances inconnues et cycles. Une sortie vide n'est jamais un succès.

## Configuration

Sur le service Hermes :

```text
API_SERVER_ENABLED=true
API_SERVER_KEY=<secret généré et stocké côté service>
```

Les valeurs natives par défaut documentées sont `API_SERVER_HOST=127.0.0.1` et
`API_SERVER_PORT=8642`. Dans un conteneur ou sur Railway, l'adresse d'écoute et
l'adresse jointe par le gateway doivent être adaptées au réseau privé ; ne recopier
ni `127.0.0.1` ni une URL publique par réflexe.

Sur le provider-gateway :

```text
HERMES_BASE_URL=
HERMES_API_KEY=
HERMES_TIMEOUT_SECONDS=30
HERMES_MAX_RETRIES=2
HERMES_RUN_TIMEOUT_SECONDS=120
HERMES_POLL_INTERVAL_SECONDS=0.5
ACP_GATEWAY_SERVICE_TOKEN=<secret inter-services>
```

`HERMES_BASE_URL` reste volontairement vide dans `.env.example`. Une URL loopback
serait fausse pour des services séparés. `HERMES_API_KEY` doit contenir la même
valeur que `API_SERVER_KEY`. `HERMES_SERVICE_TOKEN` reste accepté comme alias de
migration, mais ne doit plus être utilisé dans une nouvelle configuration.

Le diagnostic interne du gateway est :

```text
GET /v1/providers/hermes/diagnostic
```

Il renvoie un contrat typé avec `configured`, `ready`, version attendue/détectée,
modèle, latence et une cause expurgée. Les états distinguent notamment
`not_configured`, `unauthorized`, `timeout`, `incompatible_version`,
`invalid_response` et `unavailable`. Il ne déclenche aucun Run. L'interface utilise
`GET` ou `POST /connections/hermes/diagnostic` sur l'API métier, jamais cette route
interne. Ne journaliser ni clé ni en-tête `Authorization` lors d'un diagnostic.

## Skills et toolsets natifs

Hermes reste la source de vérité de ses skills et de ses toolsets. La plateforme
les **lit** et ne les écrit jamais :

```text
GET /v1/skills     → liste de {name, description, category}
GET /v1/toolsets   → liste de {name, label, description, enabled, configured, tools[]}
```

Les deux routes exigent le Bearer `API_SERVER_KEY`. Le gateway les expose, après
contrôle de readiness (`/health/detailed`, même exigence que le diagnostic), sur :

```text
GET /v1/providers/hermes/native-listing
```

protégée par `ACP_GATEWAY_SERVICE_TOKEN`. L'API métier la relaie en lecture seule
sur `GET /connections/hermes/native-listing` (session requise, aucune mutation).
Le contrat `HermesNativeListing` porte un statut explicite :

| Statut | Signification |
|---|---|
| `available` | les deux listes ont été lues ; `read_at` porte la date de lecture |
| `not_configured` | `HERMES_BASE_URL`/`HERMES_API_KEY` incomplète : rien n'a été lu |
| `unsupported` | l'instance Hermes ne sert pas ces routes (404) |
| `unavailable` | readiness dégradée, authentification refusée, délai dépassé ou réponse invalide |

Aucun contenu n'est affiché hors d'une lecture réussie : le contrat refuse une
liste non vide sans `read_at`, et une indisponibilité ne devient jamais une liste
vide présentée comme un succès. Les deux formes de réponse documentées sont
acceptées (tableau JSON nu ou objet `{"skills": [...]}` / `{"toolsets": [...]}`) ;
toute autre forme est une réponse invalide. Le contenu reçu est une donnée non
fiable : textes bornés à 500 caractères, sans caractère de contrôle, listes
bornées à 200 entrées, et il n'influence aucune politique ni instruction.

L'interface « Connexions » affiche cette lecture après le diagnostic, avec la
mention « Source : Hermes, lu le … » et **aucun bouton d'édition**. Configurer
les serveurs MCP natifs d'Hermes reste une opération côté service Hermes :
exporter la configuration depuis la plateforme (`GET /mcp/export?format=hermes`),
l'appliquer dans `~/.hermes/config.yaml`, définir les variables `ACP_SECRET_*`
dans l'environnement d'Hermes, puis attendre le rechargement automatique (~30 s)
ou déclencher `/reload-mcp`. Aucune API HTTP Hermes 0.21.1 ne permet d'écrire
cette configuration, et la plateforme ne prétend pas le faire.

## Conversation et idempotence

L'API métier crée une conversation générale privée ou une conversation explicitement
rattachée à un projet. Les droits sont vérifiés avant chaque lecture et mutation ;
un lecteur peut consulter une conversation projet autorisée mais ne peut pas ajouter
de tour.

Un tour porte deux identifiants distincts :

- `client_request_id`, fourni par le web et unique dans la conversation, empêche de
  créer deux tours lors d'une répétition HTTP ;
- `idempotency_key`, générée et persistée côté API, est transmise sans changement au
  gateway puis à Hermes dans `Idempotency-Key`.

Si l'admission a un résultat réseau incertain, le tour reste `submitting`, conserve
son message et son erreur exploitable, puis une répétition avec le même
`client_request_id` réutilise exactement la même clé. Un message différent avec le
même identifiant est refusé en conflit. Le gateway rend la main après l'admission ;
il ne masque pas une boucle de polling dans la requête `POST`.

## Contrat asynchrone et reprise

Les routes internes suivantes exigent le Bearer inter-services. Les deux admissions
exigent aussi `Idempotency-Key` (1 à 255 caractères ASCII visibles, sans espace).
Le corps reste celui de `PlanningRequest` ou `EvaluationRequest`.

| Méthode et route | Réponse |
|---|---|
| `POST /v1/providers/hermes/operations/plan` | `202`, opération admise |
| `POST /v1/providers/hermes/operations/evaluate` | `202`, opération admise |
| `GET /v1/providers/hermes/operations/{plan\|evaluate}/{run_id}` | `200`, une lecture et un résultat validé si terminé |
| `POST /v1/providers/hermes/runs/{run_id}/stop` | `202`, Run `stopping` ou terminal déjà observé |

L'opération porte `provider_id`, `operation`, `run_id`, `status`, `replayed`,
`result` et `error`. `result` est `null` à l'admission : même un replay annonçant
`completed` doit être suivi d'un GET. Sur ce GET, le résultat reprend exactement
le contrat historique `PlanningResult` ou `EvaluationResult`. Une sortie JSON
invalide devient `failed`, avec une erreur explicite et aucun résultat utilisable.

Les états sont `started`, `queued`, `running`, `waiting_for_approval`, `stopping`,
`completed`, `failed`, `cancelled`, `interrupted`. Seuls les quatre derniers sont
terminaux. Le suivi et l'arrêt d'un Run connu ne dépendent pas d'un nouveau contrôle
de readiness : une dégradation ultérieure ne doit pas empêcher de tenter l'arrêt.

La garantie de reprise dépend du stockage durable et du même profil Hermes. La
clé doit être enregistrée **avant** la première admission et réutilisée avec un
corps identique. Après 24 heures, une admission dont le `run_id` reste inconnu est
refusée ; elle ne reçoit jamais automatiquement une nouvelle clé. Un identifiant
connu continue à être consulté sans nouvelle admission. Le redémarrage d'un client
ne remplace pas la conservation du stockage et du profil Hermes côté serveur.

Pour les conversations, `POST /conversations/{conversation_id}/turns/{turn_id}/stop`
exige CSRF et droits d'écriture, sans corps supplémentaire. L'API enregistre
`stopping` avant le réseau ; le GET suivant reprend cette intention si la réponse
se perd. Une lecture concurrente ne peut revenir de `stopping` à `running`, ni
écraser un résultat terminal. L'arrêt d'un tour déjà terminal est sans nouvel effet.
Une attente d'approbation porte `waiting_for_approval` et explique que la décision
n'est pas exposée ; le client peut demander l'arrêt.

## Recette locale volontaire

Préparer un profil Hermes `0.21.1` isolé et un modèle local explicitement configuré.
Dans ce profil seulement, activer `API_SERVER_ENABLED=true`, fixer
`API_SERVER_HOST=127.0.0.1` et `API_SERVER_PORT=8642`, et définir `API_SERVER_KEY`
dans l'environnement du processus. Le gateway utilise alors
`HERMES_BASE_URL=http://127.0.0.1:8642` et la même clé sous `HERMES_API_KEY`, avec
un autre secret pour `ACP_GATEWAY_SERVICE_TOKEN`. Ne recopier aucun secret de
production et ne laisser aucun fournisseur payant choisi implicitement.

1. Lancer Hermes et le gateway avec cet environnement explicite ; appeler seulement
   le diagnostic jusqu'à `ready`. Ce contrôle ne crée pas de Run.
2. Pour exercer volontairement un Run, créer et conserver une clé de recette,
   soumettre un plan minimal puis enregistrer le `run_id` avant le polling.
3. Recréer le client puis relire ce même identifiant ; réadmettre exactement le
   même corps et la même clé doit rapprocher le même Run.
4. Sur un Run actif, demander l'arrêt puis relire jusqu'à un terminal. Un délai
   dépassé est un résultat indéterminé, jamais une preuve d'annulation.

Le 23 septembre, un profil Hermes `0.21.1` jetable a répondu aux lectures de santé
et de capacités : `run_stop=true`, conservation d'idempotence de 86 400 secondes.
Il annonce une santé dégradée (modèle absent, disque occupé à 97,9 %). Aucun Run
n'a été soumis. Preuve locale :
`.test-tmp/hermes-local-3dcd28c722a042538ecffb04f808d06d/result.json`.
La recette complète avec modèle et arrêt réel reste non exécutée. Les tests
automatiques cités ci-dessous simulent le transport.

## Tests réalisés

Le 23 septembre 2026, après la correction des reprises et arrêts, la commande
suivante a donné **192 réussis, 0 ignoré, 2 avertissements de dépréciation** :

```text
python -B -m pytest services/provider-gateway/tests apps/api/tests/test_conversations.py apps/api/tests/test_gateway_client.py -q --basetemp .test-tmp/hermes-fixes/pytest-complete
```

Elle couvre notamment la reprise après recréation du gateway simulé, l'identité
stable entre deux délais dépassés, l'arrêt non confirmé, l'attente d'approbation,
les lectures tardives et l'absence de sortie terminale. Preuve locale :
`.test-tmp/hermes-fixes/targeted-complete.log`. La base des conversations est
SQLite en mémoire ; le transport Hermes est simulé, sans appel fournisseur.


Les tests de contrat historiques dans
`services/provider-gateway/tests/test_hermes_adapter.py` utilisent
`httpx.MockTransport` et couvrent les chemins heureux, la readiness, les capacités,
l'idempotence, les états terminaux, délais et sorties mal formées. Leur baseline du
Lot A compte **58 tests réussis**.

Le Lot B ajoute `test_gateway_hermes_runs.py`, `test_conversations.py` et les tests
TypeScript du client de conversation pour le Bearer interne, le diagnostic typé,
l'admission asynchrone, la lecture unitaire, la persistance, la confidentialité et la
reprise de clé. Dans le worktree propre du Lot B, la suite Python complète comptait
**121 tests réussis** et la suite web **28 tests réussis**. Ces résultats ne prouvent
pas une intégration externe.

Le Lot D ajoute la lecture des skills et toolsets natifs
(`services/provider-gateway/tests/test_hermes_native_listing.py`,
`apps/api/tests/test_connections_hermes_native.py`) : statut explicite
`available` / `not_configured` / `unsupported` / `unavailable`, refus d'une réponse mal
formée, bornes sur les textes et les listes, et absence de mutation. Réexécutées le
13 septembre 2026 dans le worktree `lot-e` (version `0.6.0`), la suite du gateway
compte **87 tests réussis** et la suite Python complète **1 627 réussis et 4 ignorés**,
avec 2 avertissements de dépréciation connus. Le Lot E n'a rien changé à l'adaptateur
Hermes. Ces tests utilisent un transport simulé : aucune instance Hermes réelle n'a été
contactée.

Ce résultat valide la traduction et les invariants locaux. Il ne prouve pas :

- la compatibilité avec une instance réellement lancée ;
- la disponibilité d'un modèle, d'une mémoire ou d'outils réels ;
- la persistance après redémarrage ;
- les quotas, coûts et limites d'un fournisseur de modèle ;
- un déploiement Railway.

Le test réel doit être opt-in, borné et sans fournisseur payant implicite : vérifier
d'abord le diagnostic, créer un Run minimal avec une clé d'idempotence, rapprocher
son `run_id`, redémarrer le client puis relire le statut. Un test sans instance ou
clé est `non exécuté`, jamais vert.

## Capacités non livrées dans cette tranche

- consommation du streaming SSE **d'Hermes** et persistance de ses événements (le flux
  SSE du Lot E diffuse les événements écrits par la plateforme, pas ceux d'Hermes) ;
- décisions d'approbation Hermes : l'attente est affichée explicitement et le tour
  peut être arrêté, mais aucun bouton n'approuve une action à l'aveugle ;
- pièces jointes ;
- profils, modèles et MCP natifs consultables ; configuration native écrivable
  depuis la plateforme (les skills et toolsets natifs sont désormais lisibles,
  mais rien n'est écrit côté Hermes) ;
- jobs et automatisations ;
- délégations rapprochées des missions métier.

Les anciennes routes synchrones demandent `/stop` après leur délai local ou une
annulation reçue pendant le suivi. Une erreur d'arrêt reste « non confirmé » et
conserve l'identifiant de run. Les appels asynchrones délèguent au worker la durée
globale et la confirmation d'arrêt. Un accusé `stopping` ne prouve jamais la fin du
travail distant ; il faut relire un état terminal.

## Prochaine tranche

1. Lancer exactement Hermes `0.21.1` dans un environnement local isolé et exécuter
   le test réel opt-in : diagnostic puis tour borné, sans fournisseur payant
   implicite.
2. Vérifier après redémarrage la correspondance persistée `project_id` /
   conversation plateforme / `provider_session_id` / `run_id`.
3. Brancher le streaming d'Hermes sur le journal durable et le flux authentifié
   livrés au Lot E : la reprise par curseur et la réconciliation de statut existent
   déjà côté plateforme, il reste à normaliser et persister les événements d'un Run
   Hermes avec le même schéma.
4. Exercer l'arrêt réel puis définir un contrat de décision d'approbation avec la
   description exacte de l'action concernée, avant de l'exposer dans le client.
5. Exposer modèles, profils, MCP et skills dans Connexions sans dupliquer leur
   configuration native.
