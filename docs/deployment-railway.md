# Déploiement local et Railway

Date d'état : 11 septembre 2026
Statut : architecture et procédure préparatoire ; aucun déploiement réel effectué,
configuration de production non livrée.

## Verdict actuel

Le dépôt ne contient encore ni Dockerfile, ni manifeste Railway complet, ni job de
migration, ni CI, ni test PostgreSQL/sauvegarde-restauration. Les commandes ci-dessous
décrivent les processus attendus ; elles ne prouvent pas que le produit est prêt à
être publié. L'API, le gateway et le service d'événements ne doivent pas être exposés
sur Internet dans leur état actuel.

## Séparation des services

Hermes et la plateforme sont déployés séparément et ne partagent pas implicitement
un volume :

```text
Projet / environnement plateforme
  ├── web statique Vite
  ├── api FastAPI
  ├── provider-gateway FastAPI
  ├── event-service FastAPI
  ├── PostgreSQL
  └── stockage d'objets privé (à livrer)

Projet / environnement Hermes
  ├── Hermes Agent 0.21.1, image/tag v2026.9.7
  └── état natif et volume persistant propres à Hermes

Machines d'exécution
  └── workers/runners sortants, hors serveur de contrôle par défaut
```

La base PostgreSQL conserve uniquement les données métier de la plateforme. L'état
natif Hermes doit suivre les mécanismes supportés par sa version ; il ne passe pas
automatiquement dans PostgreSQL. Les livrables volumineux vont dans un stockage
d'objets, jamais dans le bus d'événements.

## Commandes de processus attendues

Après installation des packages Python du monorepo :

```text
api:              python -m uvicorn acp_api.main:app --host 0.0.0.0 --port $PORT
provider-gateway: python -m uvicorn acp_provider_gateway.main:app --host 0.0.0.0 --port $PORT
event-service:    python -m uvicorn acp_event_service.main:app --host 0.0.0.0 --port $PORT
web build:        npm run build:web
```

Le web produit un SPA statique. L'hébergeur doit réécrire les routes comme
`/projects`, `/missions` et `/connections` vers `index.html`. Le fichier
`apps/web/public/_redirects` ne garantit pas à lui seul cette règle sur Railway.

Ne pas déployer `apps/worker` comme pseudo-runner dans le serveur de contrôle : la
boucle actuelle ne raccorde encore aucun exécuteur réel isolé.

## Variables plateforme

Valeurs indicatives, à fournir via le gestionnaire de secrets et les références
privées Railway :

```text
ACP_DATABASE_URL=postgresql+psycopg://...
ACP_API_URL=https://api.<domaine>
ACP_EVENT_SERVICE_URL=http://event-service.railway.internal:<port>
ACP_PROVIDER_GATEWAY_URL=http://provider-gateway.railway.internal:<port>
ACP_PLUGINS_DIR=./plugins
ACP_CORS_ORIGINS=https://app.<domaine>

VITE_ACP_API_URL=https://api.<domaine>
VITE_ACP_EVENTS_WS_URL=wss://events.<domaine>/ws
VITE_ACP_LEGACY_OFFICE=0
```

`psycopg` et les migrations versionnées ne sont pas encore fournis : cette
configuration PostgreSQL est donc une cible, pas une recette validée.

Les endpoints internes et les flux temps réel doivent rester sur le réseau privé ou
être authentifiés avant toute exposition. CORS n'est pas un contrôle d'accès.

## Variables Hermes

Sur Hermes :

```text
API_SERVER_ENABLED=true
API_SERVER_KEY=<secret>
```

Sur le provider-gateway :

```text
HERMES_BASE_URL=http://<service-hermes-prive>:<port>
HERMES_API_KEY=<même secret>
HERMES_TIMEOUT_SECONDS=30
HERMES_MAX_RETRIES=2
HERMES_RUN_TIMEOUT_SECONDS=120
HERMES_POLL_INTERVAL_SECONDS=0.5
```

Épingler Hermes sur `v2026.9.7` et conserver son stockage persistant. La vérification
de santé du gateway appelle `/health/detailed` puis `/v1/capabilities`; un simple
200 sur `/health` n'autorise pas un Run.

## Santé, arrêt et migration

Chaque service doit disposer d'une liveness et d'une readiness distinctes avant la
production. Les endpoints `/health` actuels de la plateforme sont seulement des
liveness rudimentaires. Le démarrage cible est : migrations exclusives, API,
services internes, puis web. L'arrêt doit cesser les admissions, attendre les
transactions bornées et réconcilier les runs encore actifs.

Pour déplacer Hermes :

1. sauvegarder et restaurer son état avec la procédure supportée et testée ;
2. lancer la même version sur le nouvel hôte ;
3. vérifier detailed health et capabilities sur le réseau privé ;
4. modifier `HERMES_BASE_URL` et, si nécessaire, faire tourner la clé ;
5. tester un Run idempotent, puis seulement retirer l'ancienne instance.

Changer l'URL sans migrer l'état ne déplace ni les sessions ni la mémoire.

## Bloqueurs avant un premier déploiement privé

- bootstrap propriétaire fermé, sessions révocables et RBAC projet complet ;
- authentification du WebSocket et de `/internal/events`, reprise par curseur et
  outbox ;
- migrations Alembic et driver PostgreSQL verrouillé, test de montée et retour ;
- stockage d'objets privé, URLs signées et politiques de rétention ;
- images reproductibles, utilisateur non privilégié et fichiers de lock ;
- secrets de service tournants, CSP/CSRF/en-têtes de sécurité et CORS explicite ;
- liveness, readiness, timeouts et arrêt propre ;
- sauvegarde et restauration testées sur des données existantes ;
- runner réel séparé et isolé ; aucun socket Docker hôte ;
- CI avec tests, analyse statique et audit de dépendances.

## Vérifications à exécuter sans dépense

1. Construire chaque image localement depuis un commit propre ou un worktree dédié.
2. Lancer PostgreSQL et les services sur un réseau de test, sans secrets réels.
3. Appliquer les migrations deux fois et restaurer une sauvegarde de fixtures.
4. Vérifier qu'aucun service interne d'administration n'est publiquement routé.
5. Couper Hermes : la plateforme reste consultable et les appels Hermes échouent
   explicitement sans fallback.
6. Couper le runner et le flux : afficher `inconnu`/reconnexion, sans relancer une
   mission.
7. Tester rotation/révocation des clés et absence de secrets dans les logs.

Aucun projet Railway, ressource payante, migration de production ou DNS n'a été créé
ou modifié pendant cette intervention.
