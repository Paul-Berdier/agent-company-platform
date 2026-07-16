# Sessions et mémoire

## Sessions isolées

Quatre niveaux de session, stockés par l'API :

```text
global_provider   session globale d'un provider
workspace         session liée à un workspace
project           session liée à un projet
agent_execution   session d'exécution d'un agent sur une tâche
```

Chaque session porte le contexte complet :

```json
{
  "organization_id": "uuid",
  "workspace_id": "uuid",
  "project_id": "uuid",
  "team_id": "uuid",
  "agent_instance_id": "uuid",
  "provider_id": "uuid",
  "external_session_id": "string",
  "memory_scope": "PROJECT"
}
```

Le worker reçoit une session `agent_execution` à chaque claim ; c'est elle qui est
transmise au provider-gateway. **La plateforme n'envoie jamais automatiquement le
contexte d'un projet à un autre** : l'assemblage de contexte
(`GET /projects/{id}/context`) ne remonte que la hiérarchie du projet demandé.

## Scopes mémoire

```text
GLOBAL → WORKSPACE → PROJECT → TEAM → AGENT → TASK_RUN
```

Chaque élément mémorisé possède :

| Champ | Rôle |
|---|---|
| `scope` | niveau de visibilité |
| `owner_id` | entité propriétaire du scope |
| `source` | provenance (humain, provider, agent) |
| `classification` | public / internal / confidential |
| `ttl_seconds` | durée de vie (None = permanent, filtré à la lecture) |
| `sharing_policy` | `none`, `scope_only`, `shareable` |

Règle d'assemblage du contexte projet : mémoire `PROJECT` du projet + `TEAM`/`AGENT`
de ses équipes + éléments `WORKSPACE` et `GLOBAL` explicitement `shareable`.
Les autres projets ne sont jamais inclus.

Hermes (ou tout orchestrateur) garde sa mémoire interne via
`external_session_id` ; la plateforme décide de ce qui entre dans chaque requête.
