# Providers

La plateforme distingue trois familles de providers. Un agent logique peut en
combiner plusieurs.

## Orchestrator providers

Décident *quoi faire* : planification, révision, évaluation, synthèse de contexte.
Tous implémentent la même interface :

```python
class OrchestratorProvider:
    async def health_check(self) -> ProviderHealth: ...
    async def create_plan(self, request: PlanningRequest) -> PlanningResult: ...
    async def revise_plan(self, request: PlanRevisionRequest) -> PlanningResult: ...
    async def evaluate_result(self, request: EvaluationRequest) -> EvaluationResult: ...
    async def summarize_context(self, request: ContextSummaryRequest) -> ContextSummary: ...
```

| Provider | État | Description |
|---|---|---|
| `mock` | Fixture de test | plans déterministes ; ne pas utiliser comme preuve d'exécution |
| `manual` | Partiel | file en mémoire ; une demande en attente reste non approuvée |
| `hermes` | Adaptateur testé | Runs officiels `0.21.1`, sans connexion réelle dans ce lot |
| `claude` | Non livré | aucun `ClaudeOrchestratorProvider` opérationnel |
| `codex` | Non livré | aucun `CodexOrchestratorProvider` opérationnel |

## Execution providers

Exécutent *concrètement* les étapes : Claude Code, Codex CLI, shell restreint,
workers spécialisés. Le MVP embarque un worker simulé ; les exécuteurs réels se
brancheront au même endroit (claim → run → événements).

## Tool providers

Capacités outillées déclarées par les modules : Git, filesystem, Blender MCP,
Unreal MCP, navigateur, bases de données, CI/CD. Chaque capacité d'un module
liste ses `required_providers` ; le cœur n'en connaît aucun.

## Hermes

Hermes est un service **externe, optionnel et réutilisable**. Il n'est pas dans ce
monorepo. La plateforme lui parle uniquement via l'adaptateur
`providers/hermes/` du gateway, avec un contrat versionné (`HERMES_CONTRACT_VERSION`).

L'adaptateur détecte la readiness et les capacités, puis traduit explicitement les
opérations plateforme vers `POST /v1/runs` et le polling
`GET /v1/runs/{run_id}`. Voir `docs/hermes-integration.md`.

Configuration :

```text
HERMES_BASE_URL           # URL du service (vide = provider indisponible, jamais bloquant)
HERMES_API_KEY            # jeton Bearer ; HERMES_SERVICE_TOKEN = alias de migration
HERMES_TIMEOUT_SECONDS    # défaut 30
HERMES_MAX_RETRIES        # défaut 2
HERMES_RUN_TIMEOUT_SECONDS # défaut 120
HERMES_POLL_INTERVAL_SECONDS # défaut 0,5
```

Si Hermes est indisponible : `health_check` renvoie `available=false`, les appels
lèvent `ProviderUnavailableError` (HTTP 503 côté gateway) et le worker échoue. Il
n'existe plus de plan de secours local ni d'approbation implicite.

Migrer Hermes vers un autre hébergement = changer `HERMES_BASE_URL`, rien d'autre.
Hermes conserve sa mémoire interne ; la plateforme contrôle strictement le contexte
transmis (jamais celui d'un autre projet).

Cette tranche ne raccorde pas encore conversations, SSE, arrêt, approbations,
profils, MCP, skills ou jobs. Le provider n'est disponible qu'après configuration
et diagnostic complet ; un test mock n'est pas une connexion Hermes réelle.
