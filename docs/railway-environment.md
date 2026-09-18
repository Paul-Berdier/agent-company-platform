# Variables d'environnement par service — noms seulement

Date d'état : 18 septembre 2026, Europe/Paris. Branche `feat/desktop-qt-railway`,
version `0.9.0`.

**Ce document ne contient aucune valeur.** Ni exemple réaliste, ni gabarit de secret,
ni URL de projet. Il donne des **noms**, leur rôle, leur caractère obligatoire ou
secret, et ce qui se passe quand ils manquent. Les valeurs se renseignent dans le
tableau de bord de l'hébergeur et nulle part dans ce dépôt.

Convention des colonnes :

- **Obligatoire** : le service ne rend pas le service attendu sans elle.
- **Secret** : la valeur est un identifiant, une clé ou un jeton. Elle ne doit jamais
  être versionnée, journalisée, ni copiée dans un ticket.
- **Si absente** : comportement **vérifié dans le code de cette branche**, avec la
  référence. « Échoue fermé » signifie un refus explicite, pas une dégradation
  silencieuse.

---

## Avertissement : la variable la plus dangereuse est `ACP_DATABASE_URL`

Elle **n'échoue pas fermé**. `packages/database/src/acp_database/engine.py:25` et
`:147` retombent sur `sqlite:///./acp.db` quand la variable est absente, c'est-à-dire
sur un fichier de la couche éphémère du conteneur.

Vérifié par exécution sur ce poste le 18 septembre 2026, dans un répertoire
temporaire, sans aucune variable `ACP_*` : `readiness.prepare_service_at_startup()`
**n'a levé aucune erreur** et `GET /ready` aurait répondu **200** avec les cinq
contrôles au vert (`database: base joignable`, `migrations: schéma à la révision
attendue`, `artifact_storage: non configuré`, `skills_storage: non configuré`,
`outbox: relais désactivé`). Un fichier `acp.db` a été créé.

Conséquence à l'exploitation : un service déployé sans `ACP_DATABASE_URL` démarre,
passe sa sonde, accepte des écritures — et perd tout au redéploiement suivant, sans
qu'aucun signal ne soit émis. C'est le seul faux succès possible de cette liste, et
il doit être vérifié à la main après chaque création de service.

---

## Service `api`

### Obligatoires

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_DATABASE_URL` | Base de données, avec pilote explicite | **oui** | **N'échoue pas fermé** : repli SQLite éphémère (voir ci-dessus) |
| `ACP_SESSION_COOKIE_SECURE` | Pose l'attribut `Secure` sur le cookie de session | non | Défaut `0` (`security.py:71`) : le cookie de session part **sans** `Secure`. Faux dès qu'il y a du HTTPS |
| `ACP_CORS_ORIGINS` | Origines navigateur autorisées | non | Défaut `localhost:5173` et `127.0.0.1:5173` (`main.py:71-73`), origines de développement. Voir `docs/railway-architecture.md` §3 |
| `ACP_PLUGINS_DIR` | Répertoire des modules chargés au démarrage | non | Aucun module chargé |
| `ACP_DATA_DIR` | Racine du volume ; ancre les deux stockages | non | Défaut `/data` ; **refus de démarrer, code 3**, si le répertoire n'existe pas ou n'est pas inscriptible (`docker/entrypoint.sh:19-33`) |

### Fortement recommandées

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_TRUSTED_PROXY_IPS` | Adresses autorisées à poser `X-Forwarded-Proto` / `X-Forwarded-For` | non | Boucle locale seulement : schéma vu en `http` et adresse client égale à celle du proxy (`docker/README.md`) |
| `ACP_API_URL` | Origine canonique de l'API pour les liens signés | non | Le lien de téléchargement est relatif (`routers/artifacts.py:1764-1772`) ; l'aperçu est refusé en **424** |
| `ACP_BOOTSTRAP_TOKEN` | Autorise la création de l'unique propriétaire | **oui** | `POST /auth/bootstrap` répond **503 « Initialisation indisponible »** (`routers/auth.py:76-78`). Échoue fermé |
| `ACP_SECRETS_KEYS` | Clés Fernet du coffre de secrets | **oui** | Le coffre est « non configuré » : `GET /secrets/status` porte le message et ne renvoie jamais 503 (`secrets_vault.py:29`) |
| `ACP_ARTIFACT_SIGNING_KEYS` | Clés de signature des liens de livrables | **oui** | `POST /artifacts/{id}/link` répond **503** avec un message qui rappelle que le téléchargement par session reste disponible (`signing.py:43-49`). Échoue fermé |
| `ACP_WORKER_REGISTRATION_TOKEN` | Enrôlement d'un worker | **oui** | L'enrôlement est refusé, message explicite (`routers/workers.py:310-314`). Échoue fermé |
| `ACP_SESSION_TTL_SECONDS` | Durée de vie d'une session | non | Défaut 43 200 s (12 h), borné à [300 s, 2 592 000 s] (`security.py:62-66`) |

### Réseau interne et événements

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_EVENT_SERVICE_URL` | Nom privé du service d'événements | non | Défaut de bouclage ; l'appel échouera hors poste |
| `ACP_EVENT_SERVICE_TOKEN` | Jeton de service vers le service d'événements | **oui** | L'envoi direct est **silencieusement abandonné** (`events_bus.py:755-757`) ; le relais, lui, refuse explicitement (`outbox.py:233-237`) |
| `ACP_PROVIDER_GATEWAY_URL` | Nom privé de la passerelle de providers | non | Défaut de bouclage |
| `ACP_GATEWAY_SERVICE_TOKEN` | Jeton de service vers la passerelle | **oui** | La passerelle répond **503** à tout sauf `/health` (`provider-gateway/main.py:67-72`) |
| `ACP_EVENT_RELAY_ENABLED` | Bascule la boîte d'envoi comme unique chemin | non | Relais désactivé : les événements partent par envoi direct |

### Stockage, quotas, rétention

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_ARTIFACT_STORAGE_DIR` | Racine des livrables | non | Ancrée sous `ACP_DATA_DIR` par l'entrypoint ; sinon `./acp-data/artifacts`, donc **éphémère** |
| `ACP_SKILLS_STORAGE_DIR` | Racine des fichiers de skills | non | Idem |
| `ACP_ARTIFACT_PUBLIC_ORIGIN` | Origine du service d'aperçu | non | L'aperçu est refusé en **424**, message explicite (`routers/artifacts.py:1697-1706`). Échoue fermé |
| `ACP_ARTIFACT_MAX_BYTES` | Taille maximale d'un livrable | non | Défaut 200 Mio (`artifacts_storage.py:40`) |
| `ACP_ARTIFACT_MAX_BYTES_PER_RUN` | Quota par tentative | non | Défaut du code |
| `ACP_ARTIFACT_RETENTION_DAYS` | Rétention des livrables | non | Défaut 180 jours (`retention.py:68`) |
| `ACP_EVENT_RETENTION_DAYS` | Rétention du journal | non | Défaut 90 jours (`retention.py:67`) |

### Base de données : pool et délais

`ACP_DATABASE_POOL_SIZE`, `ACP_DATABASE_MAX_OVERFLOW`,
`ACP_DATABASE_POOL_TIMEOUT_SECONDS`, `ACP_DATABASE_CONNECT_TIMEOUT_SECONDS`,
`ACP_DATABASE_LOCK_TIMEOUT_MS`, `ACP_DATABASE_STATEMENT_TIMEOUT_MS`,
`ACP_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS`, `ACP_DATABASE_APPLICATION_NAME`.
Aucune n'est secrète ; toutes ont un défaut dans `packages/database`. Elles
n'échouent pas fermé : une valeur absente donne le défaut du code.

### Flux temps réel

`ACP_STREAM_POLL_INTERVAL_MS`, `ACP_STREAM_KEEPALIVE_SECONDS`,
`ACP_STREAM_MAX_SECONDS`, `ACP_STREAM_BATCH`,
`ACP_STREAM_MAX_CONNECTIONS_PER_USER`. Non secrètes, toutes avec un défaut
(`streams.py:92-99`). **Le client desktop dimensionne son multiplexeur sur ces
valeurs** : les modifier sans le dire à la flotte de postes produit des 429 que le
client ne saura pas expliquer, aucun point d'entrée de capacités n'existant encore.

### Sorties réseau et skills

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_OUTBOUND_PRIVATE_ALLOWLIST` | Hôtes privés joignables en sortie | non | Aucune destination privée autorisée (`outbound.py:10-11`) |
| `ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP` | Autorise le bouclage en HTTP | non | Interdit |
| `ACP_SKILLS_ALLOWED_DIRS` | Dossiers d'import de skills, **côté serveur** | non | Import de dossier refusé, message explicite (`skills/sources.py:235`). Échoue fermé |
| `ACP_SKILLS_GITHUB_ENABLED` | Autorise l'import d'une archive GitHub | non | Import refusé, message explicite (`skills/sources.py:443`). Échoue fermé |
| `ACP_GITHUB_TOKEN` | Jeton d'accès pour cet import | **oui** | Import anonyme, soumis aux limites de débit publiques |

### À laisser hors production

`ACP_ALLOW_LEGACY_WORKER_CLAIM` (rouvre une route retirée, `410` sinon),
`ACP_ALLOW_SEED` (autorise l'injection de données de démonstration hors SQLite,
`seed.py:35-42`), `ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET`,
`ACP_TEST_DATABASE_URL`, `ACP_TEST_DATABASE_REQUIRED`, toutes les `ACP_E2E_*`.
Aucune ne doit figurer dans un service déployé.

---

## Service `artifact-preview`

Rappel : sur cet hébergement, ce service **ne lit pas** le volume de l'API et n'a rien
à servir (`docs/railway-architecture.md` §4). Les variables ci-dessous ne valent que
pour une pile où le stockage est réellement partagé, par exemple `docker/compose.yml`.

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_DATABASE_URL` + les `ACP_DATABASE_*` de pool | Même base que l'API | **oui** | Même repli SQLite silencieux que l'API |
| `ACP_ARTIFACT_SIGNING_KEYS` | Vérification des jetons signés | **oui** | Aucun jeton n'est vérifiable |
| `ACP_ARTIFACT_STORAGE_DIR` | Racine des livrables | non | Ancrée sous `ACP_DATA_DIR` par l'entrypoint |
| `ACP_CORS_ORIGINS` | Origines navigateur autorisées | non | Aucune origine : le service **valide strictement** et refuse le joker et l'entrée vide (`preview.py:28-56`). Échoue fermé |
| `ACP_TRUSTED_PROXY_IPS` | En-têtes de proxy | non | Boucle locale seulement |

---

## Service `provider-gateway`

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_GATEWAY_SERVICE_TOKEN` | Authentification interne obligatoire | **oui** | **503** sur tout sauf `/health` (`provider-gateway/main.py:67-72`). Échoue fermé |
| `HERMES_BASE_URL` | Instance Hermes | non | Le provider reste indisponible |
| `HERMES_API_KEY` | Identifiant Hermes | **oui** | Idem |
| `HERMES_TIMEOUT_SECONDS`, `HERMES_MAX_RETRIES`, `HERMES_RUN_TIMEOUT_SECONDS`, `HERMES_POLL_INTERVAL_SECONDS` | Délais et reprises | non | Défauts du code |
| `ACP_COMFYUI_ENABLED` et les autres `ACP_COMFYUI_*` | Provider d'images | `ACP_COMFYUI_API_TOKEN` : **oui** | Provider désactivé |
| `ACP_CORS_ORIGINS` | Origines navigateur | non | Aucun navigateur ne doit joindre ce service : le laisser vide est le comportement voulu |

---

## Service `event-service`

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_EVENT_SERVICE_TOKEN` | Authentification interne obligatoire | **oui** | **503** explicite sur l'ingestion (`event-service/main.py:91-96`). Échoue fermé |
| `ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET` | Ouvre le WebSocket sans authentification | non | Fermé par défaut. **Ne jamais l'activer en production** |
| `ACP_EVENT_INGEST_DEDUPE_SIZE` | Taille du registre de déduplication du processus | non | Défaut du code |

---

## Service `relay`

| Nom | Rôle | Secret | Si absente |
| --- | --- | --- | --- |
| `ACP_DATABASE_URL` + pool | Lecture de la boîte d'envoi | **oui** | Même repli SQLite silencieux : le relais lirait une base vide et ne livrerait **rien**, sans erreur |
| `ACP_EVENT_SERVICE_URL` | Destination privée | non | Défaut de bouclage |
| `ACP_EVENT_SERVICE_TOKEN` | Authentification de la livraison | **oui** | Refus explicite : « le relais ne peut pas s'authentifier » (`outbox.py:233-237`). Échoue fermé |
| `ACP_EVENT_RELAY_ENABLED` | Doit valoir la même chose que sur l'API | non | Incohérence possible entre les deux services : à vérifier à la main |
| `ACP_OUTBOX_MAX_ATTEMPTS`, `ACP_OUTBOX_HTTP_TIMEOUT_SECONDS` | Bornes de réémission | non | Défauts du code |

---

## Service `web`

| Nom | Moment | Rôle | Secret | Si absente |
| --- | --- | --- | --- | --- |
| `PORT` | exécution | nginx n'écoute que sur 8080 et la sonde interroge `PORT` | non | La sonde échoue |
| `VITE_ACP_API_URL` | **build** | Origine de l'API, figée dans le bundle | non | **Le build est refusé** (`docker/web.Dockerfile`). Échoue fermé |
| `VITE_ACP_LEGACY_OFFICE` | **build** | Charge le bureau pixel historique | non | Non chargé |

Ces deux variables `VITE_*` sont figées au build : changer l'URL de l'API exige de
reconstruire l'image. C'est la limite signalée par l'audit et elle n'est pas traitée
ici (`docs/railway-architecture.md` §2.3, point 1).

---

## Variables injectées par la plateforme

`PORT` (port d'écoute, lu par `docker/entrypoint.sh`) et `RAILWAY_RUN_UID`
(exécution du conteneur sous un autre uid). Cette dernière n'est à envisager que si
le volume se révèle non inscriptible par l'uid 10001 de l'image : la poser à `0`
revient à exécuter le conteneur en root et annule la protection non privilégiée de
l'image. Le besoin réel n'a **pas** été testé.

## Ce que cette liste ne prouve pas

Les comportements « si absente » ont été lus dans le code de cette branche, et un seul
d'entre eux a été **exécuté** : le repli SQLite de `ACP_DATABASE_URL`, mesuré sur ce
poste le 18 septembre 2026. Aucun service n'a été déployé, aucune variable n'a été
renseignée sur une plateforme, aucune image n'a été construite dans ce lot.
