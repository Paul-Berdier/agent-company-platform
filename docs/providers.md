# Providers

Date d'état : 14 septembre 2026 — version publiée `0.8.0` (Lot G)

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
| `claude` | Orchestrateur non livré | aucun `ClaudeOrchestratorProvider` ; l'exécuteur CLI Lot G décrit plus bas est une intégration distincte |
| `codex` | Orchestrateur non livré | aucun `CodexOrchestratorProvider` ; l'exécuteur CLI Lot G décrit plus bas est une intégration distincte |

## Execution providers

Exécutent *concrètement* les étapes : Claude Code, Codex CLI, programme local fixe,
workers spécialisés. Le Lot C raccorde un backend générique à exécutable configuré,
sans shell et avec une politique très restrictive. Le Lot G ajoute des exécuteurs
spécialisés `codex_cli` et `claude_code`, désactivés par défaut, avec exécutable
absolu, profil d'authentification séparé, racines projet allowlistées, outils bornés,
permis avant spawn et preuve expurgée. Ils ne remplacent pas les orchestrateurs du
tableau précédent et aucun CLI authentifié n'a encore été exécuté. Voir
[Exécuteurs locaux Codex CLI et Claude Code](providers-local-executors.md).

## Tool providers

Capacités outillées déclarées par les modules : Git, filesystem, Blender MCP,
Unreal MCP, navigateur, bases de données, CI/CD. Chaque capacité d'un module
liste ses `required_providers` ; le cœur n'en connaît aucun.

Le connecteur ComfyUI du Lot G appartient lui aussi à cette frontière outillée : il
est exposé par le provider-gateway, mais n'implémente pas `OrchestratorProvider`. Il
exécute un workflow fixé par l'opérateur auquel la requête n'ajoute que le prompt,
puis borne le polling, les générations simultanées, les attentes coalescées, le cache
image en octets et le téléchargement. Après toute tentative `/prompt` dont l'issue est
incertaine, un tombstone process-local empêche la même clé de soumettre un second job
jusqu'à sa TTL. Il reste désactivé sans configuration complète et n'a pas été essayé
contre une instance ComfyUI réelle. Voir [Médias et aperçu 3D](media-and-3d.md).

## Hermes

Hermes est un service **externe, optionnel et réutilisable**. Il n'est pas dans ce
monorepo. La plateforme lui parle uniquement via l'adaptateur
`providers/hermes/` du gateway, avec un contrat versionné (`HERMES_CONTRACT_VERSION`).

L'adaptateur détecte la readiness et les capacités, puis traduit explicitement les
opérations plateforme vers `POST /v1/runs` et le polling
`GET /v1/runs/{run_id}`. Voir `docs/hermes-integration.md`.

Configuration :

```text
HERMES_BASE_URL           # URL du service ; vide = UI consultable, exécution Hermes bloquée
HERMES_API_KEY            # jeton Bearer ; HERMES_SERVICE_TOKEN = alias de migration
HERMES_TIMEOUT_SECONDS    # défaut 30
HERMES_MAX_RETRIES        # défaut 2
HERMES_RUN_TIMEOUT_SECONDS # défaut 120
HERMES_POLL_INTERVAL_SECONDS # défaut 0,5
```

Si Hermes est indisponible : `health_check` renvoie `available=false`, les appels
lèvent `ProviderUnavailableError` (HTTP 503 côté gateway) et le worker échoue. Il
n'existe plus de plan de secours local ni d'approbation implicite.

Migrer Hermes vers un autre hébergement exige de sauvegarder/restaurer son état,
conserver une version compatible, vérifier santé et capacités, puis modifier
`HERMES_BASE_URL` et faire tourner la clé si nécessaire. Changer seulement l'URL ne
déplace ni les sessions ni la mémoire. La plateforme contrôle strictement le
contexte transmis (jamais celui d'un autre projet).

Les conversations sont raccordées à Hermes par Runs et accessibles depuis le web et
le CLI. SSE, arrêt transmis à Hermes, approbations, profils, MCP, skills et jobs ne
le sont pas encore. Le provider n'est disponible qu'après configuration et
diagnostic complet ; un test mock n'est pas une connexion Hermes réelle.
