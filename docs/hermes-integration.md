# Intégration Hermes Agent

Date de référence : 11 septembre 2026
Version supportée : Hermes Agent `0.21.1`, tag de publication `v2026.9.7`
Statut : adaptateur Runs, diagnostic et conversation web persistante livrés sur
transport simulé ; aucune instance réelle n'a été jointe pendant ce lot.

## Surface retenue

La plateforme n'appelle plus les anciennes routes supposées `/v1/plans`,
`/v1/evaluations` ou `/v1/summaries`. Le provider `hermes` utilise uniquement :

```text
GET  /health/detailed
GET  /v1/capabilities
POST /v1/runs
GET  /v1/runs/{run_id}
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
                              → traduction plan/évaluation synchrone
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

La traduction synchrone demeure pour les opérations historiques de planification et
d'évaluation. Le Lot B ajoute séparément l'admission asynchrone d'un tour de
conversation et la lecture d'un état de Run. L'API plateforme persiste conversation,
tour, clé d'idempotence, `run_id`, sortie et usage ; elle utilise un identifiant de
session Hermes stable par conversation.

La reprise actuelle est volontairement simple : le web interroge
`GET /conversations/{conversation_id}/turns/{turn_id}`. Cette lecture peut
réconcilier un tour `submitting`/`running` puis persiste l'état reçu. Ce mécanisme ne
doit pas être présenté comme du streaming, du SSE ou un journal d'événements durable.

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
- soumission et consultation de Runs disponibles ;
- idempotence annoncée comme supportée et durable.

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

## Tests réalisés

Les tests de contrat historiques dans
`services/provider-gateway/tests/test_hermes_adapter.py` utilisent
`httpx.MockTransport` et couvrent les chemins heureux, la readiness, les capacités,
l'idempotence, les états terminaux, délais et sorties mal formées. Leur baseline du
Lot A compte **58 tests réussis**.

Le Lot B ajoute `test_gateway_hermes_runs.py`, `test_conversations.py` et les tests
TypeScript du client de conversation pour le Bearer interne, le diagnostic typé,
l'admission asynchrone, la lecture unitaire, la persistance, la confidentialité et la
reprise de clé. Dans le worktree propre du Lot B, la suite Python complète compte
**121 tests réussis** et la suite web **28 tests réussis**. Ces résultats ne prouvent
pas une intégration externe.

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

- conversation et reprise dans le CLI `acp` ;
- streaming SSE et persistance de ses événements ;
- stop/cancel transmis à Hermes ;
- demandes et décisions d'approbation Hermes ;
- pièces jointes ;
- profils, modèles, MCP, skills et toolsets consultables/configurables ;
- jobs et automatisations ;
- délégations rapprochées des missions métier.

Un timeout local n'envoie actuellement pas `/stop`. Le gateway cesse d'attendre,
mais le Run peut continuer côté Hermes. Ce point doit être corrigé avec la capacité
`run_stop` avant de présenter l'arrêt comme opérationnel.

## Prochaine tranche

1. Lancer exactement Hermes `0.21.1` dans un environnement local isolé et exécuter
   le test réel opt-in : diagnostic puis tour borné, sans fournisseur payant
   implicite.
2. Vérifier après redémarrage la correspondance persistée `project_id` /
   conversation plateforme / `provider_session_id` / `run_id`.
3. Ajouter streaming authentifié, journal durable, reconnexion par curseur et
   réconciliation de statut.
4. Raccorder la conversation au CLI `acp` avec la même idempotence.
5. Implémenter stop et approbations uniquement après détection de capacité.
6. Exposer modèles, profils, MCP et skills dans Connexions sans dupliquer leur
   configuration native.
