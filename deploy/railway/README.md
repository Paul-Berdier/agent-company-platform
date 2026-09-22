# Railway « config as code » (Lot H5)

Ce dossier déclare, pour chacun des six services, ce que Railway accepte de lire
depuis le dépôt : constructeur, Dockerfile, motifs de rebuild, commande de démarrage,
commande de pré-déploiement, readiness, politique de redémarrage et nombre de
répliques. Tout le reste (base PostgreSQL managée, volumes, domaines, variables,
secrets) se règle dans le tableau de bord et n'est **pas** déclarable dans ces
fichiers. `python scripts/check_railway_config.py` refuse toute clé hors schéma et
toute entorse aux règles ci-dessous.

Aucun projet Railway n'a été créé ni modifié : ces fichiers sont une préparation,
pas la preuve d'un déploiement.

## Ce que la documentation Railway dit (lecture du 17 septembre 2026)

Sources lues : `docs.railway.com/reference/config-as-code`,
`docs.railway.com/guides/config-as-code`, `docs.railway.com/guides/pre-deploy-command`,
`docs.railway.com/reference/volumes`, `docs.railway.com/guides/healthchecks`,
`docs.railway.com/infrastructure-as-code` et le schéma
`https://railway.com/railway.schema.json` (redirigé en 301 vers
`https://backboard.railway.app/railway.schema.json`).

- **Dépréciation.** La page de référence annonce : « Config as Code is deprecated.
  Prefer Infrastructure as Code. Existing files keep working for legacy services
  until 2026-12-01 ». La page Infrastructure as Code ajoute que les fichiers
  existants cessent d'être lus à cette date, que les nouveaux services ne peuvent
  plus utiliser Config as Code, et que la commande de migration « In a monorepo,
  `migrate` finds every CaC file in the repository and writes them into a single
  `.railway/railway.ts` ». Les fichiers de ce dossier sont donc un intermédiaire
  honnête : ils fixent la configuration voulue dans un format vérifiable et servent
  d'entrée à cette migration. **Le fichier `.railway/railway.ts` n'est pas livré**
  (format non lu en détail, hors périmètre de ce lot).
- **Fichier par service.** Railway cherche `railway.json` ou `railway.toml` à la
  racine ; pour un monorepo : « You can use a custom config file by setting it on the
  service settings page. You should provide the absolute path to the file in your
  repository, for example: `/backend/railway.toml` ». « Configuration defined in
  code will always override values from the dashboard. »
- **Pré-déploiement.** La commande s'exécute « between building and deploying »,
  « in a separate container from your application », a accès aux variables du
  service, mais « Changes to the filesystem are not persisted and volumes are not
  mounted ». « If your command fails, it will not be retried and the deployment will
  not proceed. » Un délai (1 à 3600 s) peut être fixé ; sans délai, pas de limite.
- **Volumes.** « Each service can only have a single volume » ; « Replicas cannot be
  used with volumes » ; les services avec volume subissent une brève interruption au
  redéploiement même avec readiness. Sur les images non-root : « Docker images that
  run as a non-root UID by default will have permissions issues when performing
  operations within an attached volume. If you are affected by this, you can set
  `RAILWAY_RUN_UID=0` environment variable in your service. » La documentation lue ne
  mentionne aucune autre solution (ni `chown` automatique, ni variable de nom ou de
  chemin de montage) et ne dit pas qu'un volume peut être partagé entre services.
- **Readiness.** Railway interroge le chemin configuré sur le port `PORT` injecté,
  attend un `2xx` avant de basculer le trafic, avec 300 s par défaut ; les sondes
  viennent de `healthcheck.railway.app` et « are only called at the start of the
  deployment » (aucune surveillance continue ensuite).
- **Clés admises** (schéma, toutes optionnelles et nullables) : `$schema`, `build`
  (`builder` ∈ {NIXPACKS, DOCKERFILE, RAILPACK, HEROKU, PAKETO}, `watchPatterns`,
  `buildCommand`, `dockerfilePath`, `nixpacksConfigPath`, `nixpacksPlan`,
  `nixpacksVersion`, `railpackVersion`), `deploy` (`startCommand`, `preDeployCommand`
  — chaîne ou tableau —, `preDeployTimeoutSeconds` 1–3600, `numReplicas` 1–200,
  `healthcheckPath`, `healthcheckTimeout`, `sleepApplication`, `runtime`,
  `registryCredentials`, `restartPolicyType` ∈ {ON_FAILURE, ALWAYS, NEVER},
  `restartPolicyMaxRetries`, `cronSchedule`, `region`, `multiRegionConfig`,
  `limitOverride`, `requiredMountPath`, `overlapSeconds`, `drainingSeconds`,
  `ipv6EgressEnabled`) et `environments`. `scripts/check_railway_config.py` porte
  exactement cette liste.

## Procédure

1. Créer un projet et, dans le même environnement, une base **PostgreSQL managée**
   (ressource Railway, hors dépôt) et six services connectés au dépôt GitHub :
   `api`, `artifact-preview`, `provider-gateway`, `event-service`, `relay`, `web`.
2. Sur chaque service, dans *Settings*, renseigner le chemin **absolu** du fichier
   de config : `/deploy/railway/<service>/railway.json`. Laisser le *root directory*
   à la racine : les Dockerfiles utilisent tout le monorepo comme contexte.
3. Attacher **un volume** au service `api` sur `/data` (une seule réplique ; la
   config le fixe). Voir plus bas pour l'aperçu.
4. Renseigner les variables (section suivante), sans jamais mettre une valeur
   secrète dans ce dépôt.
5. Déployer `api` en premier : sa commande de pré-déploiement applique les
   migrations (`/app/docker/entrypoint.sh migrate` →
   `python -m acp_database.migrate upgrade`) ; en cas d'échec, Railway ne déploie
   pas. Aucun autre service ne migre : c'est la seule commande exclusive.
6. Déployer ensuite `event-service`, `provider-gateway`, `relay`,
   `artifact-preview`, puis `web` (son build fige `VITE_ACP_API_URL`).
7. Ajouter les domaines publics (`api`, `artifact-preview`, `web`) ; `event-service`,
   `provider-gateway` et `relay` restent sur le réseau privé.

Readiness : `/ready` sur `api` et `artifact-preview` (Lot H2a), `/health` sur
`provider-gateway` et `event-service`, `/` sur `web`. `relay` n'expose pas de HTTP et
n'a pas de sonde. `numReplicas: 1` est fixé sur `api` (volume), `artifact-preview`
(volume) et `relay` (un recouvrement reste possible au redéploiement). `web` n'a pas de `startCommand` : l'image
nginx fournit la sienne ; renseigner `PORT=8080` sur ce service, car nginx n'écoute
que sur 8080 et Railway sonde le port `PORT`.

## Variables par service (noms seulement)

`ACP_DATABASE_URL` se dérive de la référence `${{Postgres.DATABASE_URL}}` : cette
valeur commence par `postgresql://` ; SQLAlchemy exige le pilote explicite. Écrire
donc, dans chaque service qui accède à la base, une variable
`ACP_DATABASE_URL=postgresql+psycopg://<utilisateur>:<mot de passe>@<hôte>:<port>/<base>?sslmode=require`
composée à partir des références `${{Postgres.PGUSER}}`, `${{Postgres.PGPASSWORD}}`,
`${{Postgres.PGHOST}}`, `${{Postgres.PGPORT}}`, `${{Postgres.PGDATABASE}}` (ou en
réécrivant le préfixe de `DATABASE_URL` et en ajoutant `?sslmode=require`).

| Service | Variables |
| --- | --- |
| `api` | `ACP_DATABASE_URL`, `ACP_DATABASE_POOL_SIZE`, `ACP_DATABASE_MAX_OVERFLOW`, `ACP_DATABASE_POOL_TIMEOUT_SECONDS`, `ACP_DATABASE_CONNECT_TIMEOUT_SECONDS`, `ACP_DATABASE_LOCK_TIMEOUT_MS`, `ACP_DATABASE_STATEMENT_TIMEOUT_MS`, `ACP_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS`, `ACP_EVENT_RELAY_ENABLED`, `ACP_API_URL`, `ACP_EVENT_SERVICE_URL`, `ACP_PROVIDER_GATEWAY_URL`, `ACP_INTERNAL_HTTP_HOSTS`, `ACP_GATEWAY_SERVICE_TOKEN`, `ACP_EVENT_SERVICE_TOKEN`, `ACP_CORS_ORIGINS`, `ACP_BOOTSTRAP_TOKEN`, `ACP_SESSION_TTL_SECONDS`, `ACP_SESSION_COOKIE_SECURE=1`, `ACP_PLUGINS_DIR=/app/plugins`, `ACP_SECRETS_KEYS`, `ACP_ARTIFACT_SIGNING_KEYS`, `ACP_ARTIFACT_PUBLIC_ORIGIN`, `ACP_ARTIFACT_STORAGE_DIR=/data/artifacts`, `ACP_SKILLS_STORAGE_DIR=/data/skills`, `ACP_ARTIFACT_MAX_BYTES`, `ACP_ARTIFACT_MAX_BYTES_PER_RUN`, `ACP_ARTIFACT_RETENTION_DAYS`, `ACP_EVENT_RETENTION_DAYS`, `ACP_STREAM_*`, `ACP_OUTBOUND_PRIVATE_ALLOWLIST`, `ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP`, `ACP_SKILLS_ALLOWED_DIRS`, `ACP_SKILLS_GITHUB_ENABLED`, `ACP_GITHUB_TOKEN` |
| `artifact-preview` | `ACP_DATABASE_URL` (+ les `ACP_DATABASE_*` de pool), `ACP_CORS_ORIGINS`, `ACP_ARTIFACT_SIGNING_KEYS`, `ACP_ARTIFACT_STORAGE_DIR` |
| `provider-gateway` | `ACP_GATEWAY_SERVICE_TOKEN`, `ACP_CORS_ORIGINS`, `HERMES_BASE_URL`, `HERMES_API_KEY`, `HERMES_TIMEOUT_SECONDS`, `HERMES_MAX_RETRIES`, `HERMES_RUN_TIMEOUT_SECONDS`, `HERMES_POLL_INTERVAL_SECONDS`, `ACP_COMFYUI_*` |
| `event-service` | `ACP_EVENT_SERVICE_TOKEN`, `ACP_CORS_ORIGINS`, `ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET=0` |
| `relay` | `ACP_DATABASE_URL` (+ pool), `ACP_EVENT_SERVICE_URL`, `ACP_INTERNAL_HTTP_HOSTS`, `ACP_EVENT_SERVICE_TOKEN`, `ACP_OUTBOX_MAX_ATTEMPTS`, `ACP_EVENT_RELAY_ENABLED` |
| `web` | `PORT=8080` ; au build : `VITE_ACP_API_URL`, `VITE_ACP_LEGACY_OFFICE=0` (déclarées comme variables de service : Railway les transmet comme arguments de build Docker si le Dockerfile les déclare en `ARG`, ce qui est le cas) |

Pour les appels privés en HTTP, renseigner `ACP_INTERNAL_HTTP_HOSTS` sur l'API et
le relais : noms exacts séparés par des virgules, par exemple
`event-service.railway.internal,provider-gateway.railway.internal`. Les noms
mono-label de compose et les adresses RFC 1918/ULA sont également admis explicitement.
Aucun joker ni domaine public n'est admis ; les autres origines exigent HTTPS.
Cette exception reste réservée aux clients internes du serveur : les workers
conservent leur exigence HTTPS hors loopback. Un worker distant qui appelle la
passerelle nécessite donc une origine HTTPS accessible ; l'origine privée du
serveur ne lui est pas transmissible telle quelle.

Le relais attend le schéma courant et la connexion pendant au plus 900 s avant de
rendre le code 4 (`--schema-wait-seconds` règle cette borne). Il ne migre jamais.
Les pannes réseau, 5xx, 401/403 et 429 retiennent la tête de file sans la passer en
lettre morte. Seuls les refus de message (400/413/422), les erreurs déterministes
ou un transport défectueux peuvent produire une lettre morte ; surveiller les
compteurs `pending` et `dead` exposés par `/ready` et les journaux du relais.

Les variables de test `ACP_TEST_DATABASE_URL` et `ACP_TEST_DATABASE_REQUIRED` ne se
déploient jamais : elles appartiennent à la CI et à `docker/compose.test.yml`.

## Ce qui n'est pas déclarable et ses conséquences

- **Un volume par service, non partageable.** L'API écrit les livrables et les skills
  sous `/data`. Sur Railway, `artifact-preview` est un service distinct avec, au
  mieux, son propre volume vide : **il ne peut pas lire le volume de l'API**. Aucun
  stockage objet n'est livré. Conséquence honnête : sur Railway, l'aperçu signé
  (`purpose=preview`) ne fonctionne pas tant qu'un adaptateur de stockage partagé
  n'existe pas ; le téléchargement par l'API reste disponible. Avec
  `docker/compose.yml`, les deux services montent le même volume nommé et l'aperçu
  fonctionne : c'est une différence de plateforme, pas de code.
- **Image non-root et volume.** L'image tourne en uid 10001 et l'entrypoint refuse
  de démarrer (code 3) si `/data` n'est pas inscriptible, sans `chown`. La seule
  réponse documentée par Railway est `RAILWAY_RUN_UID=0`, c'est-à-dire exécuter le
  conteneur en root, ce qui annule la protection non-root de l'image. Aucune autre
  méthode n'a été lue ; le comportement réel d'un volume Railway face à l'uid 10001
  **n'a pas été testé**. Deux issues possibles, à décider à l'exploitation :
  accepter `RAILWAY_RUN_UID=0` sur `api` seulement, ou constater au premier
  déploiement que le volume est inscriptible et ne rien changer.
- **Volume réellement monté (0.9.1).** L'image crée `/data` elle-même : sans volume, le
  répertoire existe et reste inscriptible, et les livrables écrits disparaîtraient au
  redéploiement pendant que la base les référence encore. `api`, `artifact-preview` et
  `backup` refusent donc de démarrer (code 3) si `/data` et les racines de stockage ne
  sont sur aucun volume monté. `ACP_DATA_DIR_EPHEMERAL=1` lève ce refus pour un usage
  jetable assumé : c'est acceptable sur `artifact-preview` tant qu'il ne peut de toute
  façon pas lire le volume de l'API, jamais sur `api`. Vérification sans lancer de
  service : `/app/docker/entrypoint.sh check-data`.
- **Pré-déploiement sans volume.** La migration n'a besoin que de la base ; elle
  n'accède pas à `/data`, ce que l'entrypoint respecte (`migrate` ne vérifie pas le
  répertoire de données).
- **PostgreSQL managé, domaines, secrets, références `${{…}}`** : tableau de bord
  uniquement. Le `sslmode=require` de `ACP_DATABASE_URL` est un choix de sécurité,
  pas une exigence lue dans la documentation.
- **Réseau privé.** `ACP_EVENT_SERVICE_URL` et `ACP_PROVIDER_GATEWAY_URL` doivent
  viser les noms privés Railway ; le worker distant refuse HTTP hors bouclage et
  exige une terminaison TLS.

## Vérification

```text
python scripts/check_railway_config.py   # 0 : conforme ; 1 : écarts en français
python scripts/check_lock.py             # verrou et contraintes cohérents
```

`apps/api/tests/test_deploy_config.py` exerce ces deux scripts (fichiers valides
acceptés, fichiers altérés refusés).
