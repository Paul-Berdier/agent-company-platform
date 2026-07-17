# Déploiement (Railway ou équivalent)

La plateforme et Hermes se déploient **indépendamment** : deux projets distincts,
reliés uniquement par HTTP et des variables d'environnement.

## Railway Project 1 — plateforme

```text
- web               (apps/web — build statique Vite)
- api               (uvicorn acp_api.main:app)
- event-service     (uvicorn acp_event_service.main:app)
- worker            (python -m acp_worker.main)
- provider-gateway  (uvicorn acp_provider_gateway.main:app)
- PostgreSQL
- Redis             (optionnel, futur bus d'événements)
```

Le service statique doit appliquer un fallback SPA vers `index.html` pour les
routes inconnues. Le fichier `apps/web/public/_redirects` couvre les hébergeurs
compatibles ; sur Railway, configurer la même réécriture afin que `/ambient` et
`/projects/:id/ambient` soient servis par le point d'entrée web.

Variables clés :

```text
ACP_DATABASE_URL=postgresql+psycopg://...
ACP_API_URL=https://api.<domaine>
ACP_EVENT_SERVICE_URL=https://events.<domaine>
ACP_PROVIDER_GATEWAY_URL=https://gateway.<domaine>
ACP_PLUGINS_DIR=./plugins
ACP_CORS_ORIGINS=https://app.<domaine>
VITE_ACP_API_URL / VITE_ACP_EVENTS_WS_URL   (build du web)
```

## Railway Project 2 — Hermes (optionnel)

```text
- hermes-service
- hermes-database / stockage persistant
```

Côté plateforme, seul le gateway est configuré :

```text
HERMES_BASE_URL=https://hermes.<domaine>
HERMES_SERVICE_TOKEN=...
HERMES_TIMEOUT_SECONDS=30
HERMES_MAX_RETRIES=2
```

## Migration de Hermes vers un serveur personnel

1. Déployer Hermes sur le nouveau serveur.
2. Mettre à jour `HERMES_BASE_URL` (et le token) sur le provider-gateway.
3. Redémarrer le gateway. Aucun changement de code, aucune migration de la plateforme.

Si Hermes est éteint, le provider `hermes` devient indisponible (503) ; `mock` et
`manual` restent utilisables et le worker garde son plan de secours local.
