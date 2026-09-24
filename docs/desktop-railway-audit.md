# Audit préalable : station de travail desktop (C++23 / Qt 6 / QML) sur backend Railway

> Relevé historique du 18 septembre : ses états Git, versions et absences de code
> valent pour la révision auditée. Pour la livraison native du 23 septembre,
> consulter [la reprise](reprise-poste.md) et [les preuves actuelles](desktop-validation-2026-09-23.md).

Date d'état : 18 septembre 2026, Europe/Paris
Branche auditée : `feat/desktop-qt-railway`, tête `ac1d753`, dérivée de
`codex/modernization-lot-h`. Le Lot H n'est pas fusionné dans `main` : tout ce qui
suit décrit la branche courante, pas `main`.
Version du produit : `0.9.0` (fichier `VERSION`), en préparation, non publiée — aucun
tag `v0.8.0` ni `v0.9.0` n'existe dans `git tag` (derniers tags présents : `v0.2.0` à
`v0.7.0`).

## 1. Portée et engagement de ce document

### Ce que ce document engage

Ce document est un **relevé de l'existant**, pas un plan. Chaque affirmation qui suit
a été vérifiée en lisant le code de cette branche, en exécutant `git` ou en exécutant
le Python du dépôt sur cette machine, le 18 septembre 2026. Les chemins et numéros de
ligne cités valent pour la tête `ac1d753` et pour elle seule : un `git rebase` les
périme.

Il engage trois choses :

1. **La surface d'API réellement disponible** pour un client natif, avec son mode
   d'authentification exact. Elle est obtenue par énumération programmatique du
   document OpenAPI, pas par lecture de documentation.
2. **La liste des changements backend imposés** par un client installé sur un poste,
   chacun justifié par un fait de code et non par une préférence d'architecture.
3. **La séparation nette entre ce qui est prouvé et ce qui ne l'est pas.** Une
   fonction « livrée » n'est pas une fonction « éprouvée en réel » ; le dépôt fait
   déjà cette distinction (`docs/implementation-status.md`), ce document la conserve.

### Ce que ce document n'engage pas

Aucune décision d'architecture desktop, aucun découpage de lots, aucun calendrier,
aucune estimation de coût. La phase suivante — fondation desktop — s'appuie sur ce
relevé mais tranche seule ses choix.

### Portée technique

- **Dans le périmètre** : `apps/api`, `packages/contracts`, `packages/database`,
  `apps/event-service`, `services/provider-gateway`, `apps/cli`, `apps/web`,
  `packages/ui`, `deploy/railway`, `docker/`, `.github/workflows`.
- **Hors périmètre, explicitement** : `packages/pixel-office-engine` et le mode
  wallpaper (`apps/web/src/ambient.ts`). Ils sont décrits en section 7 pour expliquer
  pourquoi ils restent la dernière phase, et pour cette seule raison. Aucun travail
  Godot n'est engagé.

## 2. Architecture réelle observée

### 2.1 Services et paquets

Le dépôt est un monorepo à trois niveaux : `apps/` (applications déployables),
`packages/` (bibliothèques partagées), `services/` (passerelles).

| Unité | Chemin | Nature |
|---|---|---|
| API métier | `apps/api` | FastAPI, détient la base, les sessions, le RBAC, le journal |
| Service d'événements | `apps/event-service` | Relais interne, sans accès aux données |
| Passerelle de providers | `services/provider-gateway` | Hermes, ComfyUI ; joignable par l'API seule |
| Worker | `apps/worker` | Exécution des tentatives, s'authentifie par jeton porteur |
| CLI | `apps/cli` | Client tiers non-navigateur, déjà en production |
| Interface web | `apps/web` | Vite/TypeScript sans framework |
| Contrats | `packages/contracts` | Modèles Pydantic + une génération TypeScript |
| Base de données | `packages/database` | Modèles SQLAlchemy, Alembic, moteur |
| Moteur pixel | `packages/pixel-office-engine` | Hors périmètre |
| Jetons `@acp/ui` | `packages/ui` | Jetons du bureau pixel, **pas** du shell métier |

L'API est une **application FastAPI unique** (`apps/api/src/acp_api/main.py`) qui
assemble 22 routeurs (`app.include_router`, lignes 80 à 101). Sa version déclarée est
`0.9.0` (`main.py:61`), et cette valeur n'apparaît que comme métadonnée OpenAPI.

Le démarrage est fermé : `readiness.prepare_service_at_startup()` est appelé dans le
`lifespan` avant le `yield` ; tout refus est une `RuntimeError` française laissée
remonter, et uvicorn ne sert alors rien.

### 2.2 Flux réel

```text
                      ┌──────────────────────────────────────────────┐
                      │        Poste opérateur (Windows)             │
                      │                                              │
   HTTPS + SSE        │   ┌────────────────────────┐                 │
   cookie acp_session │   │  apps/desktop (à créer)│                 │
   X-CSRF-Token       │   │  C++23 / Qt 6 / QML    │                 │
        ┌─────────────┼───┤  pot de cookies propre │                 │
        │             │   └────────────────────────┘                 │
        │             │   ┌────────────────────────┐                 │
        │             │   │  apps/cli  « acp »     │ (existant)      │
        │             │   └────────────────────────┘                 │
        │             └──────────────────────────────────────────────┘
        │
        │             ┌──────────────────────────────────────────────┐
        │  HTTPS+SSE  │   Navigateur : apps/web (SPA nginx)          │
        ├─────────────┤   VITE_ACP_API_URL figée au build            │
        │             └──────────────────────────────────────────────┘
        v
╔═══════════════════════════════════════════════════════════════════════════╗
║  Réseau public Railway (TLS terminé en amont — domaine à générer)         ║
╚═══════════════════════════════════════════════════════════════════════════╝
        │
        v
┌───────────────────────────────────────────────────────────────────────────┐
│  service « api »  —  apps/api  —  numReplicas 1  —  /ready                │
│                                                                           │
│  auth + RBAC   missions   approbations   artefacts   MCP   skills         │
│  secrets   automations   budgets   alertes   workers   événements         │
│                                                                           │
│  SSE : GET /streams/runs/{id}      (curseur = EventModel.sequence)        │
│        GET /streams/projects/{id}  (curseur = EventModel.journal_seq)     │
│                                                                           │
│  volume /data : livrables + skills (un volume = un service)               │
└───────────┬──────────────────────┬────────────────────────┬───────────────┘
            │                      │                        │
   réseau privé Railway     PostgreSQL managé          jeton de service
            │                      │                        │
            v                      v                        v
  ┌───────────────────┐   ┌──────────────────┐   ┌────────────────────────┐
  │ event-service     │   │  base de données │   │ provider-gateway       │
  │ relais interne    │   │  source unique   │   │ Hermes / ComfyUI       │
  │ /ws — PAS pour    │   │  de vérité du    │   │ jamais joint par un    │
  │ le desktop        │   │  journal         │   │ client                 │
  └───────────────────┘   └──────────────────┘   └────────────────────────┘
            ^                      ^
            │                      │
  ┌─────────┴──────────┐   ┌───────┴────────────┐   ┌────────────────────┐
  │ relay (outbox)     │   │ worker(s)          │   │ artifact-preview   │
  │ aucune sonde       │   │ bearer + bail +    │   │ origine séparée    │
  │ numReplicas 1      │   │ fencing token      │   │ ne voit PAS /data  │
  └────────────────────┘   └────────────────────┘   └────────────────────┘
```

Trois règles structurent ce schéma, et le desktop les hérite sans négociation :

1. **La base est l'unique source de vérité du journal.** Les flux SSE la « tailent »
   par curseur (`apps/api/src/acp_api/streams.py:1-32`) : une reconnexion ne perd ni
   ne duplique d'événement.
2. **Le desktop ne parle qu'à l'API.** Jamais à la base, jamais à `event-service`
   (le flux utilisateur est servi par l'API, pas par lui), jamais à
   `provider-gateway` (joignable par l'API seule, via un jeton de service).
3. **Aucun secret serveur ne franchit le réseau public.** Le coffre ne renvoie jamais
   une valeur (`routers/secrets.py`), le worker seul obtient des secrets résolus.

## 3. Surface d'API utile au client natif

### 3.1 Mesure

L'énumération du document OpenAPI a été exécutée sur cette machine avec le Python du
dépôt (`.venv/Scripts/python.exe`, Python 3.13.3) :

- **136 chemins**, **164 opérations HTTP**, `info.version = "0.9.0"`.
- **22 étiquettes de routeur** : `alerts`, `artifacts`, `auth`, `automation-scheduler`,
  `automations`, `budgets`, `connections`, `conversations`, `events`, `extensions`,
  `hierarchy`, `mcp`, `missions`, `onboarding`, `operations`, `platform`, `secrets`,
  `skills`, `streams`, `testing`, `work`, `workers`.
- **`/meta`, `/version` et `/capabilities` sont absents** de l'énumération.

### 3.2 Modes d'authentification, exhaustivement

Il n'existe que quatre modes dans tout le produit :

| Mode | Porté par | Où |
|---|---|---|
| **public** | rien | `/health`, `/ready`, `/openapi.json`, `/docs`, `/auth/status` |
| **session humaine** | cookie `acp_session` (HttpOnly, `SameSite=strict`, `Secure` conditionné par `ACP_SESSION_COOKIE_SECURE`) | tout le reste de la surface humaine |
| **jeton porteur worker** | en-tête `Authorization` du worker | routes `/workers/**`, `/events` en écriture, `/task-runs/{id}`, budget, sondes MCP, dépôt des quotas d'abonnement |
| **secret dédié** | `X-ACP-Bootstrap-Token`, `X-Worker-Registration-Token`, `Bearer` de webhook, jeton signé `?token=` | amorçage, enrôlement, webhook entrant, téléchargement de livrable |

**Il n'existe aucun bearer utilisateur, aucune clé d'API personnelle, aucun OAuth.**
`get_auth_context` lit `request.cookies.get("acp_session")` et rien d'autre
(`apps/api/src/acp_api/deps.py:42`). Les deux routes SSE lisent le même cookie
(`routers/streams.py:86` et `:112`).

Sur les méthodes non sûres (`POST`, `PUT`, `PATCH`, `DELETE`), l'en-tête
`X-CSRF-Token` est **obligatoire** : `require_csrf` (`deps.py:48-52`) et
`get_principal` (`deps.py:60-68`) refusent en 403 « Requête refusée ».

Le RBAC est hiérarchique, `_ROLE_ORDER = {"viewer": 0, "member": 1, "operator": 1,
"owner": 2}` (`deps.py:20`) — `operator` et `member` sont de **même rang**. Un
`platform_role == "owner"` court-circuite tout contrôle de portée (`deps.py:80-81`).

### 3.3 Surface par domaine

Seules les routes utiles au client natif sont listées. Les routes worker sont
regroupées en fin de tableau, en tant qu'**interdits explicites**.

#### Santé et compatibilité

| Méthode et chemin | Objet | Auth |
|---|---|---|
| `GET /health` | liveness pure, `{"status":"ok","service":"api"}` (`main.py:117-120`) ; **ne porte aucune version** | public |
| `GET /ready` | readiness : base, migrations, stockage livrables, stockage skills, outbox ; 200 ou 503, raisons en français, ni chemin ni URL ni secret | public |
| `GET /openapi.json` | document complet ; `info.version` = `0.9.0` | public |

Il n'existe **aucune route de compatibilité**. Le seul signal de version est
`info.version` du document OpenAPI, servi sans authentification.

#### Authentification et session

| Méthode et chemin | Objet | Auth |
|---|---|---|
| `GET /auth/status` | `bootstrap_required` | public |
| `POST /auth/bootstrap` | crée l'unique propriétaire et ouvre sa session | `X-ACP-Bootstrap-Token` |
| `POST /auth/login` | Argon2 ; pose le cookie, renvoie `user`, `csrf_token`, `expires_at` | public |
| `GET /auth/session` | relit la session, met `last_seen_at` à jour et **fait tourner le jeton CSRF** (`routers/auth.py:137`) ; **n'allonge pas** `expires_at` | session |
| `POST /auth/logout` | révoque la session courante et purge le cookie | session + CSRF |

Le routeur d'authentification n'expose que ces cinq routes. **Aucun changement de mot
de passe, aucune création d'un second compte, aucune désactivation, aucun listage ni
révocation des autres sessions.**

#### Hiérarchie, projets, contexte

`GET /overview` · `GET|POST /organizations` · `GET|POST /workspaces` ·
`GET|POST /departments` · `GET|POST /projects` · `GET /projects/{id}/context` ·
`GET /projects/{id}/extensions` · `GET|POST /teams` · `GET|POST /teams/{id}/members` ·
`GET|POST|PATCH /agents` · `GET|POST /memberships` · `GET /company/level` ·
`GET /modules` — toutes en **session + CSRF**.

`GET /departments/{id}/office-config` existe mais **ne doit pas être consommée avant
la dernière phase** : c'est l'entrée du bureau pixel.

#### Missions — la ressource centrale

| Méthode et chemin | Objet | Auth |
|---|---|---|
| `GET /missions` | filtres `project_id`, `status`, `limit` 1..500 | session + CSRF |
| `POST /missions` | crée atomiquement mission + tentative n°1 ; **`Idempotency-Key` obligatoire** | session + CSRF |
| `GET /missions/{id}` | détail : tentatives, preuves, validation technique, acceptation | session + CSRF |
| `GET /missions/by-run/{run_id}` | même détail, résolu depuis une tentative | session + CSRF |
| `GET /missions/{id}/runs` | tentatives par `attempt_number` | session + CSRF |
| `POST /missions/{id}/stop` | `queued` → `cancelled`, sinon → `stopping` ; **`Idempotency-Key` obligatoire** | session + CSRF |
| `POST /missions/{id}/retry` | nouvelle tentative, `fencing_token` incrémenté ; motif obligatoire ; **`Idempotency-Key` obligatoire** | session + CSRF |
| `POST /missions/{id}/runs/{run_id}/acceptance` | décision humaine sur une tentative techniquement réussie | session + CSRF |
| `GET|POST /missions/{id}/comments` | fil de commentaires ; `Idempotency-Key` facultative mais, si fournie, `run_id` devient obligatoire | session + CSRF |

La clé d'idempotence est de 1 à 200 caractères ASCII visibles, liée au principal **et**
à l'empreinte canonique du payload : rejouer la même clé avec un corps différent est
un refus, pas un doublon.

#### Journal et flux

| Méthode et chemin | Objet | Auth |
|---|---|---|
| `GET /runs/{run_id}/events` | page du journal d'**une tentative**, curseur exclusif `after_seq` sur `EventModel.sequence`, `limit` 1..500 | session + CSRF |
| `GET /projects/{project_id}/events` | page du journal d'un **projet**, curseur sur `EventModel.journal_seq` | session + CSRF |
| `GET /streams/runs/{run_id}` | SSE portée tentative | **session (cookie seul)** |
| `GET /streams/projects/{project_id}` | SSE portée projet | **session (cookie seul)** |
| `GET /events` | liste plate filtrable, ordonnée par `occurred_at` décroissant | session + CSRF |

`GET /events` **n'est pas un mécanisme de reprise** : pas de curseur d'ordre total,
ordre par horloge. La réconciliation passe par les deux routes paginées.

#### Décisions humaines

| Méthode et chemin | Objet | Auth |
|---|---|---|
| `GET /approvals` | file d'attente ; expire d'abord les approbations dépassées | session + CSRF |
| `POST /approvals` | crée une demande ; cible, conséquences, portée et empreinte obligatoires pour une mission | session + CSRF |
| `POST /approvals/{id}/decision` | **décision humaine**, rôle `owner` sur le projet (`routers/operations.py:451`) | session + CSRF |
| `GET /locks` | verrous à lease actifs, pour diagnostic de contention | session + CSRF |
| `POST /mcp/probes/{probe_id}/decision` | autorise ou refuse un lancement MCP `stdio` | session + CSRF |

**Fait vérifié, et contraire à ce qu'affirmait le rapport clients** :
`POST /approvals/{id}/decision` **existe** et est exposée à un humain. Ce qui manque,
c'est un **client** : `grep` sur `apps/cli/src/acp_cli/` ne trouve aucun appel à
`/approvals/…`, et `apps/web/src/api.ts:42-46` ne consomme que
`GET /approvals?status=WAITING_APPROVAL`. Le CLI n'expose qu'`acp approvals list`
(`cli.py:951-956`, dispatch `cli.py:4739-4741`). **Le desktop serait donc le premier
client capable de décider d'une approbation.**

#### Livrables

| Méthode et chemin | Objet | Auth |
|---|---|---|
| `GET /artifacts` | bibliothèque paginée par **curseur opaque** (`artifacts.py:1293`) | session + CSRF |
| `GET /artifacts/{id}` | métadonnées ; 404 — jamais 403 — hors portée | session + CSRF |
| `GET /artifacts/{id}/content` | contenu en flux, **support `Range` (206)**, 410 si purgé (`artifacts.py:1509`) | session **ou** jeton signé `?token=` |
| `POST /artifacts/{id}/link` | lien signé borné (`ttl_seconds` 1..900, défaut 300) et révocable (`artifacts.py:1794`) | session + CSRF |
| `DELETE /artifacts/links/{link_id}` | révoque un lien (`artifacts.py:1848`) | session + CSRF |

Ces cinq routes sont **les seules** du routeur artefacts côté humain. **Il n'existe
aucune route de listage des liens signés actifs** : un lien dont l'identifiant a été
perdu ne peut plus être révoqué avant son expiration.

Sans `ACP_ARTIFACT_SIGNING_KEYS`, la création de lien renvoie un 503 explicite ; le
message dit lui-même que « le téléchargement authentifié par session reste disponible »
(`apps/api/src/acp_api/signing.py:43-49`).

#### Conversations Hermes

Huit routes (`routers/conversations.py`, lignes 163, 187, 220, 242, 258, 285, 301,
377) : liste, création, patch, détail, export JSON, tours, création de tour idempotente
par `client_request_id`, relecture d'un tour.

**Aucun flux SSE n'existe pour les conversations** : `grep` sur le routeur ne trouve
aucune route de streaming. L'avancement d'un tour n'a lieu que lors d'un `GET` du tour.
Un client est donc condamné à l'interrogation périodique.

#### Extensions, sécurité, exploitation

- **MCP** : 24 routes `/mcp/**` — catalogue, serveurs versionnés, révisions, sondes
  HTTP et `stdio`, décisions, rattachements par projet, import/export. La mutation
  d'un serveur exige `platform_role == "owner"`.
- **Skills** : 15 routes `/skills/**` — recherche, catalogue, import, révisions et
  fichiers, approbation, activation, désactivation, révocation, rollback,
  rattachements. Les fichiers sont servis **en texte brut dans un champ JSON, jamais
  rendus**.
- **Secrets** : `GET /secrets/status` (ne renvoie jamais 503 : `configured=false` porte
  le message), `GET|POST /secrets`, `POST /secrets/{id}/rotate`,
  **`DELETE /secrets/{secret_id}`** (`routers/secrets.py:207` — et non un `POST
  /revoke`, contrairement à ce qu'affirmait le rapport clients).
- **Automatisations** : 14 routes utilisateur, dont `GET /automations/calendar`.
- **Budgets** : `GET|PUT /projects/{id}/budget-policy`, `GET /projects/{id}/budget-usage`.
- **Quotas réels d'abonnement** (ajout du 24 septembre 2026) : `GET /subscription-quotas`,
  **session du propriétaire de la plateforme uniquement** ; tout autre rôle reçoit un 403
  explicite en français, car l'usage d'un abonnement est personnel à son titulaire.
  Réponse `SubscriptionQuotaList` : `items[]` (dernier relevé par worker, fournisseur
  `codex`|`claude_code` et compteur `limit_id`, avec `status`, `windows[]` portant
  `used_percent`, `remaining_percent`, `window_minutes`, `resets_at`, et `stale`),
  `stale_after_seconds`, `generated_at`. Valeurs relevées par les workers aux sources
  officielles, jamais estimées : `null` s'affiche « Inconnu », `stale` « Périmé ».
  Lecture périodique, sans flux temps réel ; un serveur antérieur répond 404. Forme
  figée par `apps/desktop/tests/fixtures/subscription-quotas.json` ; détail dans
  [les quotas d'abonnement](subscription-quotas.md).
- **Alertes** : `GET /alerts`, `POST /alerts/{id}/acknowledge`, préférences par projet.
- **Workers** : `GET /workers`, `GET /workers/{id}` — réservées aux rôles plateforme
  `owner` ou `operator`. **Aucune route de révocation d'un worker depuis l'interface.**
- **Connexions** : `GET|POST /connections/hermes/diagnostic`,
  `GET /connections/hermes/native-listing`.
- **Onboarding** : `GET /onboarding/status`, `POST /onboarding/projects`.

#### Interdits explicites au desktop

Ces routes portent une authentification worker (jeton porteur + bail + fencing) et
**ne doivent jamais être appelées par le client natif**, quelles que soient les
facilités qu'elles sembleraient offrir :

`POST /events` · `POST /approvals/{id}/validate` ·
`POST /workers/{id}/heartbeat|claim|artifacts|artifacts/content|test-runs` ·
`POST /workers/{id}/leases/{run_id}/renew` · `PATCH /task-runs/{run_id}` ·
`POST /workers/{id}/automation-scheduler/**` ·
`POST /work/workers/{id}/runs/{run_id}/budget/**` · `POST /mcp/worker/probes/**` ·
`POST /work/workers/{id}/subscription-quotas` ·
`POST /worker/claim` (410 sauf `ACP_ALLOW_LEGACY_WORKER_CLAIM=1`).

**Conséquence directe et lourde** : le seul chemin d'entrée de contenu binaire est
`POST /workers/{id}/artifacts/content`. **Il n'existe aucune route de téléversement de
fichier par un humain.**

## 4. Temps réel : ce que le client devra implémenter exactement

### 4.1 Deux portées, deux espaces de curseurs incompatibles

C'est le point le plus dangereux de tout le protocole, et il est documenté dans le code
lui-même (`apps/api/src/acp_api/streams.py:8-24`) :

- portée **tentative** — `GET /streams/runs/{id}` et `GET /runs/{id}/events` : le
  curseur est `EventModel.sequence`, monotone **par run** ;
- portée **projet** — `GET /streams/projects/{id}` et `GET /projects/{id}/events` : le
  curseur est `EventModel.journal_seq`, monotone **à l'échelle du journal**.

Les deux voyagent dans le même champ SSE `id:` et sont **deux entiers indiscernables**.
Rien, au niveau du protocole, n'empêche de réutiliser l'un pour l'autre ; un client qui
le fait saute ou rejoue des événements **sans aucune erreur visible**.

Règle à graver dans la fondation desktop : deux types C++ distincts et non
convertibles (par exemple `RunCursor` et `ProjectCursor`), jamais un `int` nu, jamais
un `qint64` partagé.

### 4.2 Trames émises par le serveur

Quatre formes, et quatre seulement (`streams.py:410-431`) :

| Trame | Forme | Signification |
|---|---|---|
| `acp.event` | `id: <curseur>` + `event: acp.event` + `data: <StreamEvent JSON>` | un événement du journal |
| `acp.stream.rotate` | `id: <curseur>` (si > 0) + `data: {"cursor":…,"reason":"max_seconds"}` | durée maximale atteinte ; reconnecter au curseur porté |
| `acp.stream.closed` | `event: acp.stream.closed` + `data: {"reason":…}` | fermeture serveur ; `reason=unauthorized` si session ou membership révoqués |
| keep-alive | `: ping` | commentaire SSE, toutes les 15 s |

**Le serveur n'émet aucun champ `retry`.** Toute la politique de reconnexion est à la
charge du client.

Une trame sans nom doit être traitée comme un événement : c'est la valeur par défaut
de la spécification SSE, et le CLI l'implémente ainsi (`apps/cli/src/acp_cli/cli.py`,
`_iter_stream_events`, ligne 3903 et suivantes).

### 4.3 Bornes réelles, vérifiées

Toutes lues dans `apps/api/src/acp_api/streams.py`, lignes 92 à 99 :

| Constante | Valeur par défaut | Variable d'environnement |
|---|---|---|
| intervalle d'interrogation | 400 ms | `ACP_STREAM_POLL_INTERVAL_MS` |
| keep-alive | 15 s | `ACP_STREAM_KEEPALIVE_SECONDS` |
| durée maximale d'un flux | 900 s | `ACP_STREAM_MAX_SECONDS` |
| lot de lecture | 200 | `ACP_STREAM_BATCH` |
| **flux simultanés par utilisateur** | **4** | `ACP_STREAM_MAX_CONNECTIONS_PER_USER` |
| limite de page d'événements | 500 | — |

Le dépassement de la borne de connexions renvoie **429** avec un message français et
un en-tête `Retry-After: 5` (`routers/streams.py:62-68`).

**Le compteur est un dictionnaire local au processus**, protégé par un verrou de thread
(`streams.py:204-236`). Il ne vaut comme borne globale que parce que le service `api`
est déclaré à `numReplicas: 1` (`deploy/railway/api/railway.json`). Cette borne cesse
de tenir dès la première réplique supplémentaire.

La libération du jeton dépend d'un bloc `finally` sur le générateur : **un flux que le
client n'a pas fermé proprement reste compté jusqu'à 900 s.**

### 4.4 Séquence obligatoire du client

1. **Rattrapage** : lire le journal durable par la route paginée de la portée voulue,
   jusqu'à `has_more == false`. Retenir le dernier curseur.
2. **Ouverture** : ouvrir le flux SSE avec `Last-Event-ID` (prioritaire) ou
   `?after_seq=`, en portant le cookie de session.
3. **Consommation** : traiter `acp.event` ; sur `acp.stream.rotate`, reconnecter au
   curseur porté par la trame ; sur `acp.stream.closed`, arrêter et informer
   honnêtement — une fermeture de flux **n'est pas** un arrêt de mission.
4. **Coupure** : ne jamais rejouer une mutation. La reprise se fait **par curseur de
   lecture**, jamais par réémission. Le repli est le journal durable, pas la mémoire
   du client.
5. **Multiplexage** : une connexion par portée réellement affichée, réutilisée par
   tous les panneaux. Jamais une par fenêtre, jamais une par onglet.

Le CLI est la référence exécutable de cette séquence : `_watch_run_events`
(`cli.py:4030-4065`) fait journal durable → flux → réconciliation par curseur, et traite
explicitement un refus d'accès autrement qu'une indisponibilité.

### 4.5 Revalidation permanente du RBAC

Le serveur revérifie session **et** membership à chaque tour de boucle
(`streams.py:437-448`). Une révocation ferme la connexion au plus tard à
l'interrogation suivante, avec `acp.stream.closed` / `reason=unauthorized`. Le desktop
doit traiter cette trame comme une déconnexion, pas comme une erreur réseau.

### 4.6 Ce qui n'a pas de temps réel

- **Les conversations.** Aucun flux. L'avancement d'un tour n'a lieu que lors d'un
  `GET /conversations/{id}/turns/{turn_id}`. Sans requête du client, un tour reste
  indéfiniment `submitting` ou `running`.
- **Le shell web** n'ouvre aucun flux global : `grep setInterval
  apps/web/src/workspace.ts` ne renvoie rien, et aucun `EventSource` n'y est ouvert.
  Seul le Studio en ouvre un, sur une tentative (`apps/web/src/events-api.ts`).
- **La portée projet n'a aucun consommateur d'interface.** Vérifié par recherche sur
  tout le dépôt : `/streams/projects/` n'apparaît que dans le routeur, sa
  documentation, `apps/api/tests/test_events_stream.py` et
  `scripts/verify_events_journey.py:1130`. **Le desktop en sera le premier
  consommateur applicatif.**

## 5. État de la préparation Railway

### 5.1 Ce qui est livré

Six manifestes `deploy/railway/<service>/railway.json` : `api`, `artifact-preview`,
`provider-gateway`, `event-service`, `relay`, `web`.

| Service | Commande | Sonde | Réplique | Particularité |
|---|---|---|---|---|
| `api` | `entrypoint.sh api` | `/ready`, 120 s | 1 | **seul** à porter `preDeployCommand` : `entrypoint.sh migrate`, `preDeployTimeoutSeconds` 900 |
| `artifact-preview` | `entrypoint.sh preview` | `/ready` | 1 | volume prévu — mais il ne peut pas être celui de l'API |
| `provider-gateway` | `entrypoint.sh gateway` | `/health`, 60 s | non contrainte | idempotence ComfyUI documentée comme locale au processus |
| `event-service` | `entrypoint.sh event-service` | `/health`, 60 s | — | reste sur le réseau privé |
| `relay` | `entrypoint.sh relay` | **aucune** | 1 | pas de serveur HTTP |
| `web` | (image nginx) | `/`, 60 s | — | exige `PORT=8080` en variable de service |

Deux images : `docker/python.Dockerfile` (base `python:3.12-slim-bookworm` épinglée par
digest, dépendances installées depuis un verrou haché avec `--require-hashes --no-deps`,
utilisateur non privilégié uid/gid 10001) et `docker/web.Dockerfile` (build Vite puis
nginx non privilégié sur 8080, `VITE_ACP_API_URL` obligatoire au build).

Un entrypoint sélecteur de sept commandes. `require_data_dir` refuse de démarrer avec
le **code 3** si `ACP_DATA_DIR` n'existe pas ou n'est pas inscriptible, **sans tenter
de `chown`** (`docker/entrypoint.sh:19-27`), et ancre `ACP_ARTIFACT_STORAGE_DIR` et
`ACP_SKILLS_STORAGE_DIR` sous `/data`.

Trois vérificateurs : `scripts/check_railway_config.py`, `scripts/check_lock.py`,
`scripts/check_version.py`.

### 5.2 Ce qui manque

1. **Aucun déploiement n'a jamais eu lieu.** Le dépôt l'écrit lui-même :
   `deploy/railway/README.md:11-12` — « Aucun projet Railway n'a été créé ni
   modifié : ces fichiers sont une préparation, pas la preuve d'un déploiement. »
2. **Aucun domaine n'est décidé.** Un domaine public se génère au tableau de bord et
   n'est déclarable dans aucun fichier du dépôt. Sans domaine, `ACP_API_URL`,
   `ACP_ARTIFACT_PUBLIC_ORIGIN`, `ACP_CORS_ORIGINS`, `VITE_ACP_API_URL` et l'URL par
   défaut du desktop restent indéterminés.
3. **`uvicorn` n'est pas lancé avec `--proxy-headers` ni `--forwarded-allow-ips`.**
   L'entrypoint accepte des arguments supplémentaires (`entrypoint.sh:43`, `:47`) mais
   aucun manifeste ne les passe. Derrière une terminaison TLS en amont, l'application
   verra le schéma `http` et l'adresse du proxy.
4. **Le stockage n'est pas partageable.** `artifact-preview` est un service distinct
   et ne peut pas lire le volume de `api` ; l'aperçu signé restera donc indisponible
   tant qu'aucun stockage objet n'existera. Seul le **téléchargement authentifié par
   l'API** reste praticable — ce qui suffit à un client natif.
5. **La sauvegarde n'est pas exécutable depuis l'image.** `docker/python.Dockerfile`
   n'appelle **aucun `apt-get`** (vérifié par recherche) : ni `pg_dump`, ni
   `pg_restore`. La commande refusera proprement sur une base PostgreSQL, sauf à
   fournir `ACP_BACKUP_PG_DUMP_COMMAND` / `ACP_BACKUP_PG_RESTORE_COMMAND` /
   `ACP_BACKUP_DATABASE_URL_FOR_TOOLS`.
6. **Ni rétention ni sauvegarde ne sont planifiées.** La clé `deploy.cronSchedule` est
   admise par le validateur (`scripts/check_railway_config.py:57`) et **n'est utilisée
   par aucun des six manifestes**.
7. **Le comportement du volume face à l'uid 10001 n'est pas testé.** L'échec serait net
   (code 3), mais il aurait lieu au premier déploiement.
8. **Config as Code est déprécié**, avec une échéance citée dans le dépôt
   (`deploy/railway/README.md:23-32`) : le fichier de remplacement `.railway/railway.ts`
   n'est pas livré. Passé l'échéance, des services démarreraient **sans
   `preDeployCommand` — donc sans migration — et sans `healthcheckPath`**, sans que
   rien n'échoue bruyamment. C'est le scénario de faux succès le plus dangereux du
   chantier.
9. **Le CORS de l'API n'est pas validé** : `allow_origins` est un `split(",")` brut
   (`main.py:72`), avec `allow_methods=["*"]`, `allow_headers=["*"]` et
   `allow_credentials=True`. L'application d'aperçu, elle, valide strictement
   (`preview.py:28-56`).
10. **La documentation interactive de l'API est publique.** `main.py:59-63` ne coupe ni
    `docs_url`, ni `redoc_url`, ni `openapi_url`, alors que `preview.py:80-82` les
    coupe explicitement. Dès qu'un domaine sera généré, toute la surface — y compris
    les chemins worker — sera publiée sans authentification.
11. **`docs/deployment-railway.md` est périmé et trompeur.** Daté du 14 septembre 2026
    pour la version `0.8.0` (ligne 3), il affirme encore lignes 9-10 que « Le dépôt ne
    contient encore ni Dockerfile, ni manifeste Railway complet, ni job de migration,
    ni test PostgreSQL/sauvegarde-restauration ». Les quatre existent depuis le Lot H.
12. **Le CHANGELOG ne consigne pas le Lot H.** La section `0.9.0` tient en trois lignes
    de résumé (`CHANGELOG.md:9-13`), sans les rubriques « Ajouté », « Sécurité »,
    « Vérifié localement » et « Limites connues » présentes pour `0.8.0` et `0.7.0`.

## 6. Intégration continue et distribution Windows

### 6.1 État réel de l'intégration continue

Un seul fichier : `.github/workflows/ci.yml`. `git diff --stat main...HEAD -- .github/`
renvoie **vide** : le Lot H n'a rien ajouté à la CI, alors qu'il a modifié 134 fichiers.

Trois jobs :

- **`python`** (`ubuntu-latest`, Python 3.12) : `scripts/check_version.py`, puis
  `pip install -e` de dix distributions, puis `python -m pytest -q`, puis
  `scripts/verify_automation_journey.py`.
- **`web`** (`ubuntu-latest`, Node 22) : `npm ci`, contrôle d'espaces, typecheck,
  tests web / reporter / e2e-unit / moteur pixel, build.
- **`e2e`** : opt-in strict — `workflow_dispatch` **et** `main` **et**
  `vars.ACP_E2E == '1'`.

`permissions: contents: read` au niveau du workflow.

### 6.2 Ce que la CI ne prouve pas

1. **Elle n'exerce jamais PostgreSQL.** Le job `python` n'installe pas l'extra
   `[postgresql]` et ne pose jamais `ACP_TEST_DATABASE_URL`. Toutes les suites marquées
   `postgres` — c'est-à-dire **le cœur du Lot H** — sont ignorées. La preuve PostgreSQL
   n'existe que sur un poste.
2. **Elle n'utilise pas le verrou haché** : `pip install -e` sans `-c
   requirements/constraints.txt` ni `--require-hashes`. La CI teste donc d'autres
   versions que l'image de production.
3. **Elle ne nomme ni `check_railway_config.py` ni `check_lock.py`** comme étapes : ils
   ne passent qu'indirectement, via `pytest`. Un échec apparaîtra comme un échec de
   test anonyme.
4. **Elle ne construit aucune image et n'en publie aucune.** La première construction
   de `docker/python.Dockerfile` hors du poste de développement aura lieu **sur
   l'infrastructure Railway, au premier déploiement**.
5. **Elle n'exécute aucun des parcours de vérification lourds** hormis
   `verify_automation_journey.py`. `verify_backup_restore.py`,
   `verify_events_journey.py`, `verify_mcp_journey.py` et
   `verify_live_studio_journey.py` restent des outils de poste.
6. **Elle ne contient rien de natif** : pas de runner Windows, pas de CMake, pas de
   MSVC, pas de Qt, pas de `ctest`, pas de téléversement d'artefact de build, pas de
   déclenchement par tag, pas de publication de release, pas de somme de contrôle,
   pas de signature.

### 6.3 Ce qu'exige une distribution Windows

Rien de ce qui suit n'existe dans le dépôt ; tout est à créer.

1. **Un job Windows** : configuration CMake, compilation MSVC, exécution des tests
   natifs et QML. **C'est la seule preuve de compilation possible sur ce chantier**
   (section 11).
2. **Un provisionnement de Qt épinglé**, avec cache. Le projet épingle tout le reste
   (base d'image par digest, verrou haché, `check_version.py` sur 10 `pyproject.toml`,
   6 `package.json` et 4 applications FastAPI) ; la version de Qt doit l'être aussi.
3. **Un workflow de publication distinct, déclenché par tag**, avec
   `permissions: contents: write`. Le workflow actuel est en `contents: read` et ne
   peut donc rien publier. Aucun tag `v0.8.0` ni `v0.9.0` n'existe : **le mécanisme de
   publication n'a jamais été exercé**.
4. **Un choix d'installeur** et une collecte de dépendances Qt. Rien n'est décidé.
5. **Un certificat de signature de code Windows.** Aucun certificat, aucun secret de
   signature, aucune procédure n'existent dans le dépôt. C'est un délai
   d'approvisionnement externe, pas une tâche de développement.
6. **Une décision de licence Qt.** Elle contraint le format du paquet et le contenu
   des notes de version, pas seulement la page juridique.
7. **`scripts/check_version.py` devra couvrir la version du desktop**, sans quoi le
   client dérivera silencieusement de `VERSION`.

## 7. Clients existants

### 7.1 Interface web — `apps/web`

Application Vite/TypeScript **sans framework** : le DOM est construit à la main, l'état
est un ensemble de variables de module re-rendues après mutation. Trois applications
cohabitent derrière `apps/web/src/entry.ts` : le shell métier (défaut), le bureau pixel
historique (`?legacy-office=1`) et le mode wallpaper (`/ambient`).

Le shell déclare **sept routes, toutes `configured: true`**
(`apps/web/src/workspace-model.ts:20-29`) : Accueil, Projets, Conversations, Missions,
Automatisations, Bibliothèque, Connexions.

Ce qu'il apporte de transférable :

- une **grammaire d'états** à six tonalités (`loading`, `empty`, `offline`,
  `forbidden`, `error`, `unconfigured`) appliquée à chaque écran ;
- un **validateur de forme obligatoire par appel** : une réponse hors contrat lève
  `invalid_response` et n'est jamais rendue partiellement ;
- des **règles métier honnêtes** : `taskOutcomeRate` renvoie `percentage: null` quand
  l'échantillon est vide — « Inconnu » plutôt que 100 %.

Ce qu'il n'apporte pas :

- **aucune bibliothèque de composants réutilisable** ; rien n'est transposable
  mécaniquement vers QML ;
- **aucun rafraîchissement automatique** : les données ne bougent que sur clic
  « Actualiser » ;
- un timeout HTTP de 8 000 ms (`apps/web/src/workspace-api.ts:451`), calibré pour du
  loopback et qui produira de faux « hors ligne » contre un hébergement distant.

`docs/design-system.md` est **périmé** : il affirme encore que « Les écrans
Conversations, Automatisations, Bibliothèque et Connexions sont présents dans la
navigation mais affichent volontairement `Non configuré` ». C'est faux, et vérifiable
en une ligne dans `workspace-model.ts`. Ce document ne peut pas servir de référence
visuelle en l'état.

### 7.2 CLI `acp` — `apps/cli`

**C'est la meilleure spécification fonctionnelle disponible pour un client
non-navigateur**, parce que c'en est déjà un, en production.

`apps/cli/src/acp_cli/client.py:83-104` est le modèle exact du transport à reproduire :
cookie `acp_session` posé à la main, `X-CSRF-Token` sur les seules méthodes non sûres,
`Idempotency-Key` validée côté client avant l'envoi (1..200 caractères ASCII visibles,
refus `ProtocolError` sinon), timeout de 20 s, `trust_env=False` — donc **aucun proxy
implicite** — et `follow_redirects=False`.

Le CLI dépasse le web sur deux points décisifs pour une station de travail :

- **réservation durable de la clé d'idempotence** sous verrou interprocessus, avec
  `acp pending show` / `acp pending discard` ; le web la garde en mémoire et la perd au
  rechargement ;
- **consommation SSE avec reprise par curseur**, décodage de trames nommées et repli
  sur le journal durable.

Il est en revanche **en lecture seule sur les approbations** : `acp approvals list` est
son unique sous-commande de ce groupe.

### 7.3 Moteur pixel — `packages/pixel-office-engine`, hors périmètre

Hors périmètre pour **trois raisons cumulatives**, et non par simple priorisation :

1. **Juridique.** `git ls-files apps/web/public/assets/licensed` renvoie **0 fichier** ;
   `.gitignore:41-42` exclut `apps/web/public/assets/licensed/` et
   `packages/pixel-office-engine/assets/licensed/`. La licence des assets interdit la
   redistribution. **Un binaire desktop qui les embarquerait serait une
   redistribution.**
2. **Technique.** Le moteur repose sur Phaser et un canevas WebGL. Il n'a aucun
   équivalent Qt Quick direct : ce serait une réécriture, pas un portage.
3. **Fonctionnelle.** Il n'est chargé que par import dynamique (`?legacy-office=1`,
   `/ambient`) et ne pèse rien sur le shell métier. Le laisser intact ne coûte rien.

**Consigne opérationnelle : ne pas le porter, ne pas le supprimer, ne pas le modifier.**
La route `GET /departments/{id}/office-config` est son entrée : elle ne doit pas être
consommée par le desktop avant la dernière phase.

## 8. Matrice de capacités

Fusion des trois relevés. « API existante » cite le contrat réellement servi.
« UI web » et « CLI » décrivent l'existant, pas l'intention. Priorités : **P0**
fondation sans laquelle le client ne fonctionne pas honnêtement, **P1** station
utilisable au quotidien, **P2** parité fonctionnelle, **P3** hors périmètre de ce
chantier.

| Capacité | API existante | UI web | CLI | Desktop requis | Changement backend | Risque | Priorité |
|---|---|---|---|---|---|---|---|
| Connexion et session persistante | `POST /auth/login`, `GET /auth/session`, `POST /auth/logout`, `GET /auth/status` | oui, portail avant le shell | oui (`acp login/logout/doctor`) | Écran natif, magasin de cookie chiffré par le poste, reprise silencieuse au lancement, verrouillage à l'expiration | Non pour fonctionner ; oui pour une session glissante ou un jeton d'appareil | élevé | P0 |
| Amorçage du propriétaire de plateforme | `POST /auth/bootstrap` + `X-ACP-Bootstrap-Token` | oui | non | Assistant de première ouverture, jeton en champ masqué, **jamais persisté** | Aucun | faible | P1 |
| Protection CSRF des écritures | `X-CSRF-Token` exigé (`deps.py:48-68`) | oui | oui (`client.py:88-93`) | **Un seul** jeton pour tout le processus, injecté par l'intercepteur réseau ; l'appel qui le renouvelle strictement sérialisé | Recommandé : cesser la rotation sur lecture, ou `POST /auth/csrf` dédié | élevé | P0 |
| Compatibilité client / serveur | **aucune route** ; seul `info.version` d'OpenAPI | non | `check_version.py` couvre `acp_cli.__version__` | Vérification au lancement : version serveur, version de contrat d'événement, capacités, version cliente minimale ; refus fermé en français | **Oui, bloquant** : créer le point d'entrée | élevé | P0 |
| Santé et readiness du serveur | `GET /health`, `GET /ready` | partiel | oui (`acp doctor`) | Bandeau d'état permanent, écran des 5 contrôles avec raisons françaises, écritures bloquées en 503 | Aucun | faible | P0 |
| URL de serveur configurable | `uvicorn` sur `0.0.0.0:$PORT` | non — figée au build | oui (configuration locale) | URL saisissable et mémorisable, HTTPS imposé, **aucune origine codée en dur** | Domaine à générer ; `--proxy-headers` à ajouter | moyen | P0 |
| RBAC et portées de projet | `ensure_access`, `require_platform_role`, `accessible_*_ids` | partiel (masquage) | partiel | Modèle de droits client pour griser plutôt que laisser échouer ; le 403 serveur reste la vérité | Utile : route de droits effectifs | moyen | P1 |
| Gestion des utilisateurs humains | **aucune** hors `bootstrap` et `POST /memberships` | non | non | Écran « équipe » : inviter, désactiver, changer un mot de passe | **Oui, entièrement absent** | élevé | P1 |
| Gestion des sessions et appareils | **aucune** ; `UserSessionModel` n'est exposé par aucun routeur | non | non | « Mes appareils connectés » avec révocation à distance | **Oui** : listage et révocation | moyen | P2 |
| Navigation hiérarchie et vue d'ensemble | `GET /overview`, `GET|POST` organisations / workspaces / départements / projets | oui | partiel | Arbre natif à chargement paresseux par niveau, plutôt qu'un `/overview` global | À terme oui : `/overview` non paginé charge toutes les tâches accessibles (`crud.py:390`) | moyen | P1 |
| Projets : lister, créer | `GET /projects`, `POST /projects`, `POST /onboarding/projects` | oui, création réservée au rôle adéquat | oui | Liste et création, avec le même refus explicite | Aucun | faible | P0 |
| Missions : liste et détail | `GET /missions`, `/missions/{id}`, `/missions/by-run/{id}`, `/missions/{id}/runs` | oui, sans filtre ni pagination, avec N+1 sur les commentaires | oui | Liste triable, filtrable, paginée ; détail avec tentatives, preuves, critères | Oui : le filtre `status` est appliqué après construction complète (`missions.py:368-372`) ; pagination réelle et compteur de commentaires | élevé | P0 |
| Missions : création idempotente | `POST /missions`, `Idempotency-Key` obligatoire | oui, clé en mémoire, perdue au rechargement | oui, clé réservée sous verrou interprocessus | **File d'envoi persistée sur disque** : clé et payload survivent à une fermeture et sont rejoués à l'identique | Aucun | moyen | P0 |
| Missions : arrêt et relance | `POST /missions/{id}/stop`, `/retry` | oui | oui | Confirmation, motif de relance obligatoire, affichage honnête d'`already_stopped` et des 409 | Aucun | faible | P0 |
| Missions : acceptation et commentaires | `POST /missions/{id}/runs/{run}/acceptance`, `GET|POST /missions/{id}/comments` | oui | non | Écran de recette (critères, preuves, décision) et fil de commentaires | Aucun | faible | P0 |
| Tâches non-mission | `GET|POST /tasks`, `PATCH /tasks/{id}`, `POST /tasks/{id}/queue`, `GET /task-runs` | partiel | partiel | Vue backlog ; ne jamais appeler ces routes sur une mission (409 explicite) | Aucun | faible | P2 |
| Flux SSE portée tentative | `GET /streams/runs/{id}` + `GET /runs/{id}/events` | oui (`events-api.ts`) | oui, référence de reprise | Client SSE natif : lecture continue, analyseur incrémental, `rotate`/`closed`, repli sur journal durable, backoff propre | Non ; optionnel : champ `retry` | élevé | P0 |
| Flux SSE portée projet | `GET /streams/projects/{id}` + `GET /projects/{id}/events` | **non — aucun consommateur** | non | Flux principal de la station : alertes, missions, budgets, agents ; espace de curseurs `journal_seq` strictement séparé | Non, mais **à valider en réel** : le desktop en sera le premier consommateur | élevé | P0 |
| Limite de flux simultanés | 429 au-delà de 4 par utilisateur (`streams.py:99`) | implicite | un seul flux | Multiplexeur interne : une connexion par portée affichée, fermeture propre garantie | Non ; documenter que le compteur est local au processus | élevé | P0 |
| Reprise durable des mutations | `Idempotency-Key` sur missions, stop, retry, commentaires, automatisations | en mémoire seulement | durable et verrouillé | Reprendre le modèle CLI, pas celui du web : une station a un disque et un cycle de vie long | Aucun | élevé | P1 |
| Approbations : lecture | `GET /approvals` | oui, 6 dernières sur l'Accueil | oui (`acp approvals list`) | File d'attente prioritaire, affichage intégral de cible, conséquences, portée, empreinte | Aucun | moyen | P0 |
| Approbations : décision | `POST /approvals/{id}/decision` (**existe**, `operations.py:451`) | **non** | **non** | **Le desktop serait le premier client à décider** : décision en deux temps, empreinte affichée avant le bouton | Aucun — la route existe | moyen | P0 |
| Décision de sonde MCP `stdio` | `POST /mcp/probes/{probe_id}/decision` | oui | oui | File distincte de celle des approbations ; empreinte affichée avant le bouton | Non ; à décider : unifier les deux files ou les garder séparées | moyen | P2 |
| Alertes et notifications | `GET /alerts`, `POST /alerts/{id}/acknowledge`, préférences par projet | oui | non | Notifications système natives, centre de notifications, acquittement, respect des préférences serveur | Aucun | faible | P1 |
| Livrables : bibliothèque et téléchargement | `GET /artifacts` (curseur opaque), `/artifacts/{id}`, `/artifacts/{id}/content` (Range 206) | oui | oui | Gestionnaire natif avec reprise par `Range`, vérification d'empreinte, ouverture système | Aucun — c'est le chemin qui reste disponible sans stockage partagé | faible | P1 |
| Livrables : aperçu sur origine séparée | service `artifact-preview` livré | oui, conditionné à une origine séparée | non | **Interdit d'embarquer un moteur web** : ouvrir le navigateur système, ou se limiter aux types rendus nativement | Stockage partagé ou objet : sur Railway l'aperçu ne voit pas le volume de l'API | élevé | P2 |
| Livrables : liens signés | `POST /artifacts/{id}/link`, `DELETE /artifacts/links/{id}` | oui | partiel | Création, copie, révocation ; refus honnête si la signature n'est pas configurée | Oui, utile : **aucune route de listage des liens actifs** | moyen | P2 |
| Téléversement de fichier par un humain | **aucune** — seul `POST /workers/{id}/artifacts/content` existe | non | non | Glisser-déposer vers une mission ou une conversation, attendu d'une application de bureau | **Oui, entièrement absent** | élevé | P2 |
| Conversations | 8 routes `/conversations` ; avancement d'un tour par `GET` du tour uniquement | oui, interrogation jusqu'à 60 fois | oui (`acp chat`) | Fil natif ; interrogation adaptative, suspendue quand la fenêtre n'a pas le focus | Oui à terme : **aucun flux SSE** pour les conversations | élevé | P1 |
| Tests structurés | `GET /runs/{id}/test-run`, `GET /test-runs/{id}` | oui | oui | Onglet tests d'une tentative, arbre de suites et de cas, liens vers les traces | Aucun | faible | P2 |
| Automatisations et calendrier | 14 routes utilisateur dont `GET /automations/calendar` | oui | oui, parité quasi complète | Vue calendrier native, éditeur cron avec fuseau IANA, secret webhook affiché une seule fois | Aucun — le CLI prouve que tout passe par l'API | moyen | P2 |
| Budgets par projet | `GET|PUT /projects/{id}/budget-policy`, `GET /projects/{id}/budget-usage` | oui | non | Jauges de dépense, alerte avant saturation, édition de politique (remplacement complet) | Aucun | faible | P2 |
| Quotas réels d'abonnement (Codex, Claude Code) | `GET /subscription-quotas` (propriétaire seulement) | non | non | Reste par fenêtre, heure de remise à zéro, « Inconnu », « Périmé », « Non connecté » ; aucune estimation | Aucun — livré le 24 septembre 2026 (worker opt-in) | moyen | P2 |
| Centre MCP | 24 routes `/mcp/**` | oui, module le plus volumineux du web | oui, parité complète | Centre d'extensions natif ; import/export de fichiers locaux plus naturel qu'en navigateur | Aucun | moyen | P2 |
| Bibliothèque de skills | 15 routes `/skills/**` | oui | oui, parité complète | Visionneuse **en lecture seule, sans rendu riche ni exécution** ; import → relecture → approbation → activation | À vérifier : l'import « dossier autorisé » désigne un chemin **côté serveur**, inutilisable depuis un poste distant | moyen | P2 |
| Coffre de secrets | `GET /secrets/status`, `GET|POST /secrets`, `POST /secrets/{id}/rotate`, `DELETE /secrets/{id}` | oui, aucune valeur affichée | oui, valeur lue sur l'entrée standard uniquement | Champ masqué, jamais en argv, jamais journalisé, jamais en cache disque, jamais dans un rapport de plantage | Aucun | élevé | P1 |
| Parc de workers | `GET /workers`, `GET /workers/{id}` (owner ou operator) | lecture auxiliaire | oui (`acp workers list`) | Écran d'exploitation : présence, capacités, concurrence, expiration des jetons, alerte avant péremption | Non ; il manque une route de révocation d'un worker | moyen | P2 |
| Thème et préférences d'affichage | aucune — purement local | oui, persisté localement, robuste au stockage bloqué | sans objet | Thème natif Qt Quick, persisté par le poste, suivant le thème système par défaut | Aucun | faible | P1 |
| Preuve de compilation native | sans objet | sans objet | sans objet | Job CI Windows : configuration CMake, compilation MSVC, tests natifs et QML | Aucun ; **création d'un job CI, seule preuve possible** | élevé | P0 |
| Provisionnement de Qt en CI | sans objet | sans objet | sans objet | Installation de Qt avec cache, **version épinglée** comme l'est le verrou Python | Aucun ; job CI et fichier de version Qt | moyen | P0 |
| Preuve PostgreSQL en CI | suites marquées `postgres` livrées | sans objet | `docker/compose.test.yml` | Aucun besoin propre, mais le desktop parlera à une base PostgreSQL hébergée | **La CI n'installe pas l'extra `[postgresql]` et ne pose pas `ACP_TEST_DATABASE_URL` : ces suites sont toutes ignorées** | élevé | P0 |
| Construction et publication des images | `docker/python.Dockerfile`, `docker/web.Dockerfile` | image `acp-web` livrée | `docker compose` | Aucun besoin propre | **Aucun job CI ne construit ni ne publie ces images** ; premier build distant = premier déploiement | élevé | P1 |
| Distribution Windows | sans objet | sans objet | sans objet | Installeur, archive portable, somme de contrôle, signature, notes de version, publication sur tag | Aucun ; workflow de release en `contents: write` (l'actuel est `contents: read`) | élevé | P1 |
| Vérification de mise à jour du client | aucune | sans objet | aucune | Comparer la version locale à un flux de versions, proposer le téléchargement, **jamais de mise à jour silencieuse** | Route de version cliente minimale, ou source externe ; rien n'existe | moyen | P2 |
| Persistance des livrables entre déploiements | chemins ancrés sous `/data` par l'entrypoint | sans objet | sans objet | Aucun besoin propre | Volume Railway sur `api` seul ; comportement face à l'uid 10001 non testé | élevé | P0 |
| Migrations au déploiement | `preDeployCommand` sur `api` seul, 900 s, verrou consultatif | sans objet | `python -m acp_database.migrate` | Savoir lire un 503 de `/ready` « schéma hors version » | Aucun | faible | P0 |
| Sauvegarde et restauration | `python -m acp_api.backup create/verify/inspect/restore` | aucune | oui, via l'entrypoint | Aucun besoin propre à court terme | `pg_dump`/`pg_restore` absents de l'image ; aucun ordonnanceur ; aucun dépôt distant | élevé | P1 |
| Bureau pixel d'un département | `GET /departments/{id}/office-config` | oui (moteur Phaser) | non | **Rien** : dernière phase, hors périmètre ; assets non redistribuables | Aucun | faible | P3 |

## 9. Changements backend imposés par le client natif

Chaque entrée est justifiée par un fait de code vérifié, et par ce que le client ne
peut pas faire honnêtement sans elle.

### 9.1 Bloquant

**1. Point d'entrée de compatibilité — LIVRÉ.**

> **État au 18 septembre 2026 : livré** par `apps/api/src/acp_api/routers/meta.py`
> (`GET /meta`, public, sans authentification, `Cache-Control: no-store`), contrat
> `packages/contracts/src/acp_contracts/compatibility.py`, tests
> `apps/api/tests/test_compatibility.py`. L'énumération OpenAPI passe de 136 à
> 138 chemins.
>
> Ce qui est publié, et d'où chaque valeur est lue **au moment de l'appel** : version
> du produit depuis le fichier `VERSION` (quatre sources ordonnées, aucune valeur de
> repli codée en dur — sans source lisible, c'est un 503, jamais une version
> supposée) ; `API_CONTRACT_VERSION`, versionnée indépendamment du produit ;
> `EVENT_SCHEMA_VERSION` ; `CONTRACTS_VERSION` ; les planchers de version des clients
> `desktop` et `cli` ; huit capacités **calculées** (clés de signature réellement
> chargées, coffre réellement construit, relais, origine d'aperçu réellement
> normalisée, claim worker hérité, cookie `Secure`, documentation interactive, point
> d'obtention CSRF) ; et les bornes réelles lues de `security`, `streams`, `signing`,
> `webhook_ingress`, `artifacts` et de la signature de `GET /missions`. La borne de
> flux simultanés est publiée avec sa portée réelle, `process` — ce qui répond aussi
> au point 18 de la section 9.3.
>
> **Refus fermé.** Le plancher est publié dans le corps *et* vérifié sur l'en-tête
> facultatif `X-ACP-Client: <client>/<version>` : un client qui s'annonce trop ancien
> reçoit un **426** en français portant le document complet. Aucune requête sans cet
> en-tête n'est refusée — le web et le CLI ne l'envoient pas — et le contrôle ne vit
> que sur `/meta`, donc aucune mission en cours n'est coupée par une mise à jour du
> serveur. Le plancher par défaut est la version du produit servie, faute de matrice
> de compatibilité prouvée ; `ACP_MIN_CLIENT_VERSION_DESKTOP` et
> `ACP_MIN_CLIENT_VERSION_CLI` l'abaissent, et une valeur illisible est un 503.
>
> **Compagnon livré dans le même lot** : `POST /auth/csrf`, qui confirme un jeton CSRF
> encore valide **sans le faire tourner** et n'en émet un que s'il n'y en a pas de
> valide. `GET /auth/session` n'est pas modifié : le web et le CLI gardent exactement
> leur comportement, ce que prouvent les tests de non-régression. Le point 2 de la
> section 9.2 n'est donc que **contourné**, pas résolu : supprimer la rotation sur
> lecture exigerait de conserver l'ancien jeton pendant une fenêtre de grâce, c'est-à-dire
> une colonne supplémentaire et une migration, hors du périmètre de ce lot.
>
> **Non publiée volontairement** : la longueur maximale d'une `Idempotency-Key`, qui
> n'a pas de source unique dans ce dépôt (elle est écrite dans deux routeurs) ; la
> republier en aurait fait une troisième copie.

Vérifié avant la livraison : aucun des 136 chemins énumérés n'offrait `/meta`,
`/version` ni `/capabilities` ; la seule version était `main.py:61`, exposée par
`/openapi.json`.
Contenu utile : version du serveur (lue de `VERSION` plutôt que de la constante
dupliquée), version de contrat d'API versionnée indépendamment du produit, version de
schéma d'événement (`EVENT_SCHEMA_VERSION = "1.0"`,
`packages/contracts/src/acp_contracts/events.py:36`), versions clientes minimales par
client connu, capacités **calculées et non déclarées** (signature de livrables
configurée, coffre configuré, relais actif, origine d'aperçu configurée, claim worker
hérité activé) et bornes réelles (TTL de session, durée maximale de flux, keep-alive,
connexions simultanées par utilisateur, intervalle d'interrogation, limites de page,
plafond de corps de requête).
**Raison** : le desktop est installé sur un poste et survit aux déploiements du serveur.
Sans ce contrat il ne peut ni refuser proprement une version incompatible, ni adapter
sa pression de reconnexion, ni masquer une fonction non configurée. Il ne peut que
deviner — ce que la doctrine du projet interdit.

### 9.2 Fortement recommandé

**2. Cesser de faire tourner le jeton CSRF sur une lecture, ou ajouter un point
d'entrée dédié.** `GET /auth/session` appelle `rotate_csrf_token`
(`routers/auth.py:137`). Un client multi-thread ne peut garantir l'unicité de cet appel
sans sérialisation globale, et le prix de l'erreur est un 403 « Requête refusée »
intermittent, indiscernable d'un vrai refus de droits.

**3. Session glissante, ou jeton d'appareil renouvelable.** `expires_at` est figé à la
création (`security.py:90`) et le défaut est 43 200 s, soit 12 h (`security.py:62`) ;
`GET /auth/session` ne met à jour que `last_seen_at`. Une station ouverte en continu
est déconnectée au bout de 12 h, potentiellement au milieu d'une mission.

**4. Documenter et tester l'usage non-navigateur du couple cookie + CSRF.** Le CLI le
pratique déjà (`client.py:83-104`), mais rien ne le documente comme mode supporté.
Laisser l'ambiguïté produirait un client qui « marche par accident ».

**5. Pagination réelle de `GET /missions` et de `GET /overview`.** `missions.py:368-372`
charge toutes les missions accessibles, construit un contrat par mission, **puis**
filtre et tronque : le paramètre `limit` ne borne pas le travail serveur.
`crud.py:390` charge toutes les tâches de tous les projets accessibles. Le curseur
opaque de `GET /artifacts` est le modèle déjà présent dans le dépôt.

**6. Compteur de commentaires dans le résumé de mission.** L'interface web charge les
commentaires mission par mission ; contre un hébergement distant, c'est N+1 requêtes
transcontinentales à chaque ouverture d'écran.

**7. `--proxy-headers` et `--forwarded-allow-ips` sur les services exposés.**
L'entrypoint accepte déjà des arguments supplémentaires ; aucun manifeste ne les passe.
Sans eux, toute URL construite depuis la requête et toute adresse client sont fausses
derrière une terminaison TLS en amont.

**8. Limitation de débit sur `POST /auth/login`.** `webhook_ingress.py:201` ne limite
que `_is_webhook_trigger`. Un client de bureau publie l'adresse de l'API à tous ses
utilisateurs : l'absence de frein sur l'authentification devient un risque
d'exploitation dès la mise en ligne.

**9. Décider de la publicité de `/docs`, `/redoc` et `/openapi.json`.** `main.py:59-63`
les laisse publics ; `preview.py:80-82` les coupe explicitement. C'est un choix, pas un
oubli à répéter par défaut.

**10. Valider `ACP_CORS_ORIGINS` sur l'API comme le fait l'aperçu.** `main.py:72` fait
un `split(",")` sans nettoyage ni contrôle, avec `allow_credentials=True`. Le desktop
n'a pas besoin de CORS, mais le web reste déployé.

### 9.3 Nécessaire à une station complète

**11. Routes de gestion des sessions** (listage des sessions actives du demandeur,
révocation individuelle ou globale) et **libellé d'appareil fourni au login**. Sans
elles, l'écran « mes appareils » est impossible et un accès perdu ne se coupe qu'en
changeant le mot de passe.

**12. Routes de gestion des utilisateurs** : création d'un compte par un propriétaire,
changement de mot de passe, désactivation. `POST /memberships` exige que l'utilisateur
cible existe déjà, et le seul chemin de création est `POST /auth/bootstrap`, limité à
un unique propriétaire. Sans ces routes, un écran « équipe » serait un mensonge.

**13. Route de droits effectifs** pour une portée donnée. Dupliquer la logique de
`ensure_access` et de `_ROLE_ORDER` dans un client natif est la meilleure façon de la
voir diverger.

**14. Téléversement de fichier authentifié par session**, réutilisant le stockage
adressé par contenu et les quotas existants, et exclu du plafond général comme l'est
déjà la route worker.

**15. Listage des liens signés d'un livrable.** Sans lui, la promesse de révocabilité
n'est pas tenable depuis une interface.

**16. Champ SSE `retry` dans les trames.** C'est le mécanisme standard pour qu'un
serveur pilote la pression de reconnexion d'une flotte de clients installés, plutôt que
de la subir.

**17. Temps réel pour les conversations, ou à défaut publication des transitions de
tour comme événements du journal de projet** — ce qui les rendrait visibles par le flux
existant sans créer de mécanisme nouveau.

**18. Borne de flux simultanés partagée entre répliques, ou assumée explicitement dans
le point d'entrée de compatibilité.** Elle vit dans un dictionnaire de processus et ne
tient que par `numReplicas: 1`. Le desktop dimensionnera son multiplexeur sur la valeur
annoncée : celle-ci doit être vraie.

### 9.4 Exploitation

**19. Adaptateur de stockage partagé pour les livrables**, ou renoncement documenté à
l'aperçu signé sur Railway.
**20. `pg_dump` / `pg_restore` disponibles au service qui sauvegarde**, par installation
dans l'image ou par les variables de substitution prévues.
**21. Rétention et sauvegarde planifiées** (`deploy.cronSchedule` est admis et
inutilisé).
**22. Migration vers `.railway/railway.ts`** avant l'échéance de dépréciation.
**23. Génération de types pour un client C++**, ou engagement documenté de stabilité
des contrats. `packages/contracts` publie du Python et du TypeScript ; la génération
TypeScript est elle-même écrite à la main et rien ne la tient synchronisée des modèles
Pydantic.

## 10. Limites connues, dette technique, risques, questions ouvertes

### 10.1 Limites structurelles du produit

1. Aucun point d'entrée de compatibilité.
2. Authentification humaine **exclusivement** par cookie, y compris sur les flux longs.
3. Jeton CSRF renouvelé à chaque lecture de session.
4. Durée de session jamais prolongée (12 h par défaut).
5. Aucune limitation de débit sur l'authentification.
6. Documentation interactive publique.
7. Limiteur de flux local au processus.
8. Deux espaces de curseurs indiscernables au niveau du protocole.
9. Les lignes sans numérotation sont exclues des portées : une base ancienne montre des
   trous, que l'interface doit présenter honnêtement plutôt que masquer.
10. Aucun champ SSE `retry`.
11. Aucun temps réel pour les conversations.
12. `GET /overview` et `GET /missions` non bornés côté serveur.
13. Aucune gestion des utilisateurs, des mots de passe, des sessions.
14. Aucun téléversement humain, aucun listage des liens signés.
15. Plafond de corps de requête de 1 Mio pour presque tout.
16. Aucun générateur de contrats pour un client C++.

### 10.2 Ce qui est livré mais jamais éprouvé en réel

`docs/implementation-status.md` le dit déjà pour les lots D, E et G, et ce document
le confirme : **aucun serveur MCP réel, aucun dépôt GitHub réel, aucune instance Hermes
réelle, aucun navigateur réel, aucun runner distant réel n'a jamais été contacté.**
Les zones MCP, skills, conversations et tests sont donc « livrées, non testées en
réel ». Aucun projet Railway n'a été créé. Aucune image n'a été construite hors du
poste de développement. Le flux SSE n'a jamais été éprouvé contre une coupure réseau
réelle ni derrière un proxy d'hébergeur.

### 10.3 Risques de migration

**Protocole**

- **Confusion de curseurs** : deux entiers indiscernables dans le même champ. Un client
  qui les mélange saute ou rejoue des événements sans erreur visible.
- **Rejeu de mutation à la reconnexion** : la tentation d'un client natif est de
  « refaire ce qui n'a pas abouti ». Le protocole l'interdit. Une mission relancée deux
  fois est un dégât réel, pas une gêne d'interface.
- **Épuisement de la borne de 4 flux** : plusieurs fenêtres, plusieurs panneaux ou une
  fermeture non propre suffisent à provoquer un 429 persistant jusqu'à 900 s.
- **Collision de jeton CSRF** : deux appels concurrents à `GET /auth/session` produisent
  des 403 sporadiques, non reproductibles, très coûteux à diagnostiquer.
- **Cookie non transmis sur les flux longs** : si le pot de cookies n'est pas partagé
  entre les requêtes courtes et les flux, les routes SSE répondront 401 pendant que le
  reste de l'application fonctionne.

**Architecture du client**

- **Portage mécanique du web** : le shell reconstruit tout le DOM de la route à chaque
  changement d'état. Transposé tel quel, cela donne une application qui clignote et
  perd le focus et la position de défilement. La couche de présentation est une
  réécriture, pas un portage.
- **Routage plat** : sept chemins, vues secondaires encodées en paramètres de requête.
  Le modèle « une page = un écran » est inadapté à une station qui doit afficher
  plusieurs panneaux simultanés.
- **États de chargement plein écran** : remplacer une vue entière par « Chargement… » à
  chaque rafraîchissement est inacceptable en natif. Il faut des états locaux, un
  contenu périmé conservé et marqué comme tel, un indicateur de fraîcheur — ce que le
  web ne fait nulle part.
- **Délais calibrés pour du loopback** : 8 000 ms côté web contre 20 s côté CLI. Contre
  un hébergement à démarrage à froid, le premier produira de faux « hors ligne ».
- **Dérive des structures C++** : sans génération, tout ajout de champ dans les
  contrats passera inaperçu jusqu'à un incident.

**Sécurité**

- **Fuite de jeton signé** : le jeton de téléchargement voyage en paramètre de requête.
  Un filtre de journalisation existe côté serveur ; **rien ne protège les journaux, les
  rapports de plantage et les fichiers de diagnostic du poste client**.
- **Changement de nature de la menace sur les contenus** : la règle web « aucun contenu
  d'artefact rendu dans l'origine de la plateforme » est une parade au XSS de
  navigateur. En natif, il n'y a plus d'origine, mais il y a un décodeur d'image ou de
  vidéo exposé à un fichier produit par un agent. La politique doit être **repensée**,
  pas recopiée, et surtout pas relâchée.
- **Rendu riche des fichiers de skills** : ils sont servis en texte brut, explicitement
  jamais rendus. Un client natif qui les afficherait dans un composant de rendu riche
  réintroduirait le risque que le serveur a écarté.
- **Cookie non sécurisé** : `ACP_SESSION_COOKIE_SECURE` vaut `0` par défaut
  (`security.py:71`). La procédure de déploiement impose `1`, mais c'est une variable
  de tableau de bord, donc non vérifiable par le dépôt.

**Exploitation**

- **Coupures à chaque déploiement** : `numReplicas: 1` sur `api` signifie une brève
  interruption à chaque redéploiement. Pour le desktop, **la reconnexion par curseur
  est un chemin nominal, pas un cas d'erreur**.
- **Premier build distant = premier déploiement** : toute dérive de l'image se
  découvrira là.
- **Dépréciation silencieuse de Config as Code** : des services qui démarrent sans
  migration et sans sonde, sans que rien n'échoue bruyamment.
- **Montée en répliques** : le limiteur cesse d'être global et le réveil du hub local
  ne couvre plus que le processus servant ; la latence de rattrapage passe au pas
  d'interrogation (400 ms). Ce n'est pas une perte d'événement, mais c'est un
  changement de comportement observable.

### 10.4 Questions ouvertes

**Authentification et session**

1. Le desktop conserve-t-il le couple cookie + CSRF (aucun changement serveur, modèle
   déjà prouvé par le CLI) ou faut-il introduire un credential d'appareil ? La réponse
   conditionne les routes SSE, qui ne lisent aujourd'hui que le cookie.
2. Quelle durée de session pour une station de travail ? Relever la configuration, ou
   session glissante côté code ?
3. Faut-il transmettre un identifiant d'appareil au login pour alimenter un futur écran
   « mes appareils » ? Cela suppose une colonne supplémentaire et un champ de contrat.

**Temps réel**

4. Un flux de portée projet par projet affiché, ou un seul flux sur le projet actif ?
   La borne de 4 impose de trancher avant d'écrire le multiplexeur.
5. Quelle politique de reconnexion après `acp.stream.rotate` : immédiate comme le CLI,
   ou temporisée pour une flotte de postes ?
6. L'hébergement supportera-t-il des connexions SSE longues sans coupure imposée par la
   passerelle ? Jamais éprouvé.

**Compatibilité et versions**

7. Le point d'entrée de compatibilité doit-il être public comme `/health` et `/ready`,
   ou exiger une session ? Public, il révèle version et capacités à un inconnu ;
   authentifié, il ne peut pas servir à refuser une connexion avant d'ouvrir une
   session.
8. Quelle politique de version cliente minimale : refus dur au lancement, mode dégradé
   en lecture seule, ou avertissement ? La doctrine « échec fermé » plaide pour le
   refus ; il faut décider ce qui se passe quand un serveur est mis à jour **pendant
   qu'une mission tourne**.
9. `apps/api/src/acp_api/preview.py:78` code en dur sa propre version `0.9.0` : une
   version pour l'ensemble, ou une version par service ?

**Périmètre**

10. Le desktop porte-t-il la gestion des utilisateurs et des appartenances ? Si oui,
    les routes manquantes deviennent bloquantes et non P1.
11. Les conversations sont-elles dans le périmètre de la première version ? Si oui,
    l'interrogation est la seule voie et son coût serveur doit être accepté
    explicitement.
12. Le desktop vise-t-il la parité avec le web (moins riche à la création de mission :
    ni ressources, ni budget en coût ou en jetons, ni capacités requises) ou avec le
    CLI (plus riche, et mieux éprouvé) ?
13. Le desktop stocke-t-il des données hors ligne ? Cela change la gestion du curseur,
    celle de la rétention (annoncée dans chaque page d'événements) et les obligations de
    purge à la déconnexion.
14. Le desktop doit-il fonctionner contre une pile locale en plus de l'hébergement ? Si
    oui, il devra accepter du HTTP en bouclage, ce qui contredit une discipline
    « HTTPS obligatoire » : à trancher explicitement plutôt qu'à laisser en repli
    silencieux.
15. Faut-il conserver et déployer l'interface web une fois le desktop livré ?

**Contrats et outillage**

16. Quelle source de vérité pour les types C++ : générateur depuis `/openapi.json`,
    génération depuis les modèles Pydantic, ou écriture manuelle ? Aucun générateur
    n'existe aujourd'hui, pour aucun langage.
17. Quelle version de Qt 6 et quel jeu d'outils, et par quel mécanisme Qt est-il
    provisionné en intégration continue ? Rien n'est épinglé, alors que le projet
    épingle tout le reste.
18. Quelle licence Qt, et quelle technologie d'installeur ? Les deux décident du format
    du paquet et de ce que la CI doit installer.
19. Un certificat de signature de code Windows est-il disponible ou en cours
    d'acquisition ?
20. Le budget de minutes d'intégration continue accepte-t-il un job Windows sur chaque
    demande de fusion, ou faut-il le réserver aux tags et aux déclenchements manuels,
    comme le fait déjà le job e2e ?

**Hébergement**

21. Un projet et un environnement existent-ils déjà, ou faut-il partir de zéro ?
22. Quels noms de domaine pour `api`, `artifact-preview` et `web` ?
23. Un stockage objet est-il budgété ? Sans réponse, l'aperçu signé est **à retirer de
    la feuille de route plutôt qu'à promettre**.
24. Faut-il tester l'inscriptibilité du volume par l'uid 10001 avant d'envisager
    d'exécuter le conteneur en root ?
25. Qui exécute la sauvegarde périodique, et où ? Les mécanismes natifs de la plateforme
    et le format de sauvegarde du produit ne produisent pas le même artefact ; les
    mélanger sans le décider, c'est croire sauvegardé un état qui ne l'est pas de façon
    cohérente.

## 11. Chaîne d'outils du poste et stratégie de preuve

### 11.1 Relevé, exécuté le 18 septembre 2026 sur cette machine

Recherche de chaque exécutable dans le `PATH` :

| Outil | État |
|---|---|
| `qmake`, `qmake6` | **absent** |
| `cmake` | **absent** |
| `ninja` | **absent** |
| `cl` (MSVC), `msbuild` | **absent** |
| `gcc`, `g++`, `clang` | **absent** |
| `godot` | **absent** |
| `python` | présent — `C:\Python313\python.exe`, Python 3.13.3 |
| `node` | présent — Node v22.15.0 |
| `docker` | présent — client Docker 28.3.2 (présence du binaire seule ; aucun démon vérifié) |

Le dépôt fournit en outre `.venv/Scripts/python.exe`, utilisé pour l'énumération
OpenAPI de la section 3.

### 11.2 Conséquence sur la stratégie de preuve

**Aucun code natif ne peut être compilé sur ce poste.** Il n'y a ni Qt, ni système de
construction, ni compilateur C++, ni générateur.

Trois règles en découlent, et elles ne sont pas négociables pour la suite du chantier :

1. **Aucune affirmation de compilation locale ne sera jamais écrite.** Ni dans un
   message, ni dans un commit, ni dans une documentation. Écrire « le client compile »
   sans preuve serait exactement le faux succès que la doctrine du projet interdit.
2. **La seule preuve de compilation recevable vient de l'intégration continue.** Un job
   Windows qui configure, compile et exécute les tests natifs et QML est donc une
   **dépendance de la fondation desktop**, pas un raffinement ultérieur. Tant qu'il
   n'existe pas, le code natif écrit est du texte non vérifié, et doit être présenté
   comme tel.
3. **Ce qui est vérifiable localement doit l'être, et l'être seul** : contenu des
   fichiers, cohérence des contrats avec le document OpenAPI, scripts Python du dépôt,
   vérificateurs existants, tests Python et Node. C'est le périmètre de preuve du
   poste, et il s'arrête là.

Le même relevé vaut pour Godot : absent. **Aucun travail Godot n'est engagé par ce
chantier**, et le moteur pixel existant n'est ni porté, ni supprimé, ni modifié.

## Ce que cet audit ne prouve pas

Cet audit prouve ce qui est **écrit** dans le dépôt à la tête `ac1d753`, et ce que le
Python du dépôt **répond** quand on l'interroge sur cette machine. Il ne prouve rien
d'autre, et en particulier : il ne prouve pas qu'un déploiement fonctionne, puisque
aucun n'a jamais eu lieu et qu'aucune image n'a été construite ailleurs que sur un poste
de développement ; il ne prouve pas que les flux SSE tiennent derrière la passerelle
d'un hébergeur, ni qu'une coupure réseau réelle est correctement reprise, toute la
logique de reconnexion n'étant éprouvée que par des tests à minuteries injectées ; il ne
prouve pas que les zones MCP, skills, conversations et tests fonctionnent, aucun serveur
MCP réel, dépôt réel, instance Hermes réelle ni navigateur réel n'ayant jamais été
contacté ; il ne prouve pas que la migration, la sauvegarde ou la restauration se
comportent correctement sur une base hébergée, la CI ignorant l'intégralité des suites
PostgreSQL ; il ne prouve pas que le couple cookie + jeton CSRF se comporte comme prévu
depuis un client Qt, aucun client Qt n'existant ; il ne prouve pas que le volume de
l'hébergeur sera inscriptible par l'utilisateur non privilégié de l'image ; et il ne
prouve **rien du tout** sur la compilation, l'exécution ou la distribution d'un binaire
natif, puisque ce poste ne dispose d'aucun des outils nécessaires pour en produire un.
Les chiffres de tests cités par les relevés d'origine n'ont pas été rejoués ici et ne
sont donc pas repris. Tout ce qui est marqué « à vérifier », « inconnu » ou « non
décidé » dans ce document l'est parce que la preuve manque, et non parce que la
recherche a été écourtée : ces mentions doivent être traitées comme des tâches, pas
comme des réserves de style.
