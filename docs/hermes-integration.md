# Intégration Hermes Agent

Date de référence : 11 septembre 2026
Version supportée : Hermes Agent `0.21.1`, tag de publication `v2026.9.7`
Statut : adaptateur Runs livré et testé sur transport simulé ; aucune instance réelle
n'a été jointe pendant ce lot.

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
worker.

## Architecture et traduction

```text
worker → provider-gateway → readiness + capacités Hermes
                           → création d'un Run idempotent
                           → polling borné du statut
                           → validation stricte de la sortie
                           → contrat plateforme
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

Cette traduction synchrone est une étape de migration. Elle ne remplace pas encore
la conversation persistante ou le flux d'événements natif.

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
```

`HERMES_BASE_URL` reste volontairement vide dans `.env.example`. Une URL loopback
serait fausse pour des services séparés. `HERMES_API_KEY` doit contenir la même
valeur que `API_SERVER_KEY`. `HERMES_SERVICE_TOKEN` reste accepté comme alias de
migration, mais ne doit plus être utilisé dans une nouvelle configuration.

Le diagnostic public du gateway est :

```text
GET /v1/providers/hermes/health
```

Il renvoie `available=false` avec la configuration manquante ou la cause de
readiness ; il ne déclenche aucun Run. Ne journaliser ni la clé ni l'en-tête
Authorization lors d'un diagnostic.

## Tests réalisés

Les tests de contrat dans `services/provider-gateway/tests/test_hermes_adapter.py`
utilisent `httpx.MockTransport` et couvrent les chemins heureux, la readiness, les
capacités, l'idempotence, les états terminaux, délais et sorties mal formées. La
suite ciblée stabilisée compte **58 tests réussis**.

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

- conversations et sessions REST exposées dans le web/CLI ;
- streaming SSE et persistance de ses événements ;
- stop/cancel transmis à Hermes ;
- demandes et décisions d'approbation Hermes ;
- profils, modèles, MCP, skills et toolsets consultables/configurables ;
- jobs et automatisations ;
- délégations rapprochées des missions métier.

Un timeout local n'envoie actuellement pas `/stop`. Le gateway cesse d'attendre,
mais le Run peut continuer côté Hermes. Ce point doit être corrigé avec la capacité
`run_stop` avant de présenter l'arrêt comme opérationnel.

## Prochaine tranche

1. Lancer exactement Hermes `0.21.1` dans un environnement local isolé et exécuter
   le test réel opt-in.
2. Persister un mapping explicite `project_id` / conversation plateforme /
   `hermes_session_id`.
3. Ajouter streaming, reconnexion et réconciliation par statut durable.
4. Implémenter stop et approbations uniquement après détection de capacité.
5. Exposer modèles, profils, MCP et skills dans Connexions sans dupliquer leur
   configuration native.
