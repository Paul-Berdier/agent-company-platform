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
| `mock` | ✅ MVP | plans déterministes, toujours disponible |
| `manual` | ✅ MVP | un humain valide via `/v1/manual/pending` |
| `hermes` | ✅ adaptateur | service externe optionnel, voir ci-dessous |
| `claude` | 🔜 | ClaudeOrchestratorProvider |
| `codex` | 🔜 | CodexOrchestratorProvider |

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

Configuration :

```text
HERMES_BASE_URL           # URL du service (vide = provider indisponible, jamais bloquant)
HERMES_SERVICE_TOKEN      # jeton Bearer
HERMES_TIMEOUT_SECONDS    # défaut 30
HERMES_MAX_RETRIES        # défaut 2
```

Si Hermes est indisponible : `health_check` renvoie `available=false`, les appels
lèvent `ProviderUnavailableError` (HTTP 503 côté gateway) et le worker bascule sur
un plan de secours local. La plateforme reste pleinement utilisable.

Migrer Hermes vers un autre hébergement = changer `HERMES_BASE_URL`, rien d'autre.
Hermes conserve sa mémoire interne ; la plateforme contrôle strictement le contexte
transmis (jamais celui d'un autre projet).
