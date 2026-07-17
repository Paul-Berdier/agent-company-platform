# Agent Company Platform

Plateforme générique multi-projets représentant une **entreprise virtuelle** dans laquelle
des agents IA travaillent dans différents départements, sur plusieurs projets, visualisée
comme un bureau **pixel art vu du dessus**.

Le cœur est totalement agnostique du métier : jeux vidéo, data science, recherche,
développement logiciel, etc. sont fournis par des **modules (plugins)**, des **adaptateurs**
et des **providers** optionnels. Hermes est un service externe optionnel, jamais importé
par le cœur.

## Architecture

```text
Organization → Workspace → Department → Project → Team → Agent Instance → Task → Task Run
```

```text
agent-company-platform/
├── apps/
│   ├── web/                  # Interface pixel art (Vite + TypeScript)
│   ├── api/                  # API REST cœur (FastAPI)
│   ├── event-service/        # Diffusion temps réel des événements (WebSocket)
│   └── worker/               # Worker distant authentifié (simulation disponible)
├── services/
│   └── provider-gateway/     # Passerelle providers (mock / manual / hermes)
├── packages/
│   ├── contracts/            # Contrats Pydantic + types TypeScript versionnés
│   ├── database/             # Modèles SQLAlchemy + accès base
│   ├── event-sdk/            # SDK d'émission d'événements
│   ├── provider-sdk/         # Abstraction OrchestratorProvider
│   ├── agent-sdk/            # Définitions d'agents logiques et capacités
│   ├── pixel-office-engine/  # Moteur pixel art data-driven (TypeScript)
│   └── ui/                   # Composants UI partagés
├── plugins/
│   ├── software-development/
│   ├── data-science/
│   ├── game-development/
│   └── research/
└── docs/
```

## Démarrage rapide (MVP, sans Hermes)

Prérequis : Python ≥ 3.11, Node ≥ 20.

```powershell
# 1. Installation (crée .venv, installe les packages Python et npm)
./scripts/setup.ps1

# 2. Lancer les services (le worker démarre s'il a déjà été enregistré)
./scripts/dev.ps1

# 3. Ouvrir http://localhost:5173
```

Sous Linux/macOS : `./scripts/setup.sh` puis `./scripts/dev.sh`.

Services par défaut :

| Service          | Port | Rôle                                   |
|------------------|------|----------------------------------------|
| api              | 8000 | CRUD, sessions, mémoire, permissions   |
| event-service    | 8001 | WebSocket `/ws` + ingestion événements |
| provider-gateway | 8002 | Orchestrateurs mock / manual / hermes  |
| web              | 5173 | Bureau pixel art                       |

La base est SQLite par défaut (`ACP_DATABASE_URL` pour PostgreSQL). Le seed de
démonstration est appliqué via `python -m acp_api.seed`.

Pour la première installation d'un worker Windows, définir
`ACP_WORKER_REGISTRATION_TOKEN` côté API puis exécuter
`agent-company-worker register`, `doctor` et `start`. Procédure détaillée :
[docs/workers/windows-worker.md](docs/workers/windows-worker.md).

## Assets graphiques

Le dépôt embarque uniquement des **placeholders originaux libres**. Les
graphismes premium (personnages, mobilier, extérieurs, UI) proviennent des
packs **[LimeZu](https://limezu.itch.io/)** (Modern Interiors, Modern Office,
Modern Exteriors, Modern User Interface), achetés séparément et importés en
local — jamais redistribués ici. Installation :
[docs/assets/limezu-installation.md](docs/assets/limezu-installation.md).

**Crédits : pixel art par [LimeZu](https://limezu.itch.io/).**

## Documentation

- [docs/architecture.md](docs/architecture.md) — vue d'ensemble et frontières
- [docs/providers.md](docs/providers.md) — orchestrator / execution / tool providers, Hermes
- [docs/providers-local-executors.md](docs/providers-local-executors.md) — garde-fous Claude Code et Codex CLI
- [docs/plugins.md](docs/plugins.md) — écrire un module métier
- [docs/sessions-memory.md](docs/sessions-memory.md) — sessions isolées et scopes mémoire
- [docs/deployment-railway.md](docs/deployment-railway.md) — déploiement indépendant plateforme / Hermes
- [docs/workers/windows-worker.md](docs/workers/windows-worker.md) — enrôler et exploiter un worker Windows
