# Architecture

## Vue d'ensemble

L'Agent Company Platform est une entreprise virtuelle générique. Le cœur ne connaît
aucun métier : les secteurs (dev, data, recherche, jeu vidéo...) sont fournis par des
**modules**, les intelligences externes par des **providers**, et l'interface pixel art
est entièrement pilotée par les **données** et les **événements réels** du backend.

## Hiérarchie organisationnelle

```text
Organization      entreprise virtuelle globale
└─ Workspace      contexte isolé (personnel, professionnel, scolaire, expérimental)
   └─ Department  secteur réutilisable (défini par un module)
      └─ Project  projet concret d'un workspace
         └─ Team  groupe temporaire d'agents affecté au projet
            └─ Agent Instance  agent logique avec rôle et capacités
               └─ Task         unité de travail
                  └─ Task Run  exécution concrète d'une tâche
```

## Services

| Service | Rôle | Dépend de |
|---|---|---|
| `apps/api` | source de vérité : CRUD, sessions, mémoire, permissions, journal d'événements, chargement des modules | PostgreSQL/SQLite |
| `apps/event-service` | diffusion WebSocket des événements vers l'interface | api (push HTTP) |
| `apps/worker` | exécute les task runs (simulation dans le MVP) | api, provider-gateway |
| `services/provider-gateway` | héberge les orchestrator providers derrière un contrat unique | providers externes optionnels |
| `apps/web` | bureau pixel art multi-vues | api, event-service |

Flux d'un run : `web → api (queue) → worker (claim) → gateway (plan) → worker (simulation,
événements) → api (journal) → event-service → web (animations)`.

## Frontières strictes

- Le cœur n'importe **jamais** une classe interne d'un provider externe (Hermes, Claude...).
  Seul le dossier `services/provider-gateway/src/acp_provider_gateway/providers/hermes/`
  connaît le protocole Hermes, à travers un contrat versionné.
- Le moteur pixel art (`packages/pixel-office-engine`) ne contient aucun rôle, salle ou
  animation métier : tout est décrit par les manifestes des modules.
- Aucun contexte d'un projet n'est transmis automatiquement à un autre : chaque appel
  provider embarque une `SessionContext` bornée à sa hiérarchie.

## Packages partagés

- `contracts` : modèles Pydantic + types TypeScript, versionnés (`CONTRACTS_VERSION`).
- `database` : modèles SQLAlchemy, unique point d'accès à la base.
- `provider-sdk` : interface `OrchestratorProvider`, registre, erreurs.
- `event-sdk` : émission d'événements résiliente.
- `agent-sdk` : définitions déclaratives (rôles, stations, workflows) et chargeur de modules.
