# Déploiement local et Railway

Date d'état : 13 septembre 2026 — version `0.6.0`
Statut : architecture et procédure préparatoire ; aucun déploiement réel effectué,
configuration de production non livrée.

## Verdict actuel

Le dépôt ne contient encore ni Dockerfile, ni manifeste Railway complet, ni job de
migration, ni test PostgreSQL/sauvegarde-restauration. La CI exécute les suites
locales, le typecheck et le build, mais aucun déploiement. Les commandes ci-dessous
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

Ne pas déployer `apps/worker` dans le serveur de contrôle : son backend local réel
est borné et contrôlé, mais il conserve les droits OS/réseau du compte worker et
n'est pas une sandbox. L'exécuter sur une machine dédiée et non privilégiée.

## Variables plateforme

Valeurs indicatives, à fournir via le gestionnaire de secrets et les références
privées Railway :

```text
ACP_DATABASE_URL=postgresql+psycopg://...
ACP_API_URL=https://api.<domaine>
ACP_EVENT_SERVICE_URL=https://events.<domaine>
ACP_PROVIDER_GATEWAY_URL=https://gateway.<domaine>
ACP_PLUGINS_DIR=./plugins
ACP_CORS_ORIGINS=https://app.<domaine>

VITE_ACP_API_URL=https://api.<domaine>
VITE_ACP_EVENTS_WS_URL=wss://events.<domaine>/ws
VITE_ACP_LEGACY_OFFICE=0
```

`psycopg` et les migrations versionnées ne sont pas encore fournis : cette
configuration PostgreSQL est donc une cible, pas une recette validée.

`VITE_ACP_EVENTS_WS_URL` ne concerne que le WebSocket **legacy** du service
d'événements, fermé par défaut. Le flux utilisateur du Lot E passe par l'API métier
(`VITE_ACP_API_URL`) en SSE, avec le cookie de session : aucune variable
supplémentaire n'est nécessaire côté web.

Les endpoints internes et les flux temps réel doivent rester sur le réseau privé ou
être authentifiés avant toute exposition. CORS n'est pas un contrôle d'accès.

## Variables du Lot D (extensions contrôlées)

Sur le service **api** uniquement :

```text
ACP_SECRETS_KEYS=<clé Fernet>[,<clé précédente>…]
ACP_OUTBOUND_PRIVATE_ALLOWLIST=
ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP=0
ACP_SKILLS_STORAGE_DIR=/data/skills
ACP_SKILLS_ALLOWED_DIRS=
ACP_SKILLS_GITHUB_ENABLED=0
ACP_GITHUB_TOKEN=
```

Points à tenir, dans cet ordre :

1. `ACP_SECRETS_KEYS` est la clé du coffre : sans elle, l'API annonce honnêtement
   `configured=false` et refuse (`503`) toute route qui chiffre ou déchiffre, mais
   **la perdre rend illisibles tous les secrets déjà enregistrés**. Elle doit être une
   référence privée sauvegardée hors du projet, jamais une valeur en clair dans un
   manifeste. La première clé chiffre, les suivantes déchiffrent encore : une rotation
   consiste à préfixer la nouvelle clé, faire tourner les secrets, puis retirer
   l'ancienne. Il n'y a ni KMS, ni HSM, ni rotation planifiée.
2. `ACP_OUTBOUND_PRIVATE_ALLOWLIST` doit rester **vide** par défaut. Chez un
   hébergeur, le réseau privé et la métadonnée d'instance sont précisément ce que la
   politique de sortie bloque ; n'y inscrire une adresse qu'après avoir mesuré ce
   qu'elle rend joignable. Chaque usage produit un événement d'audit
   `outbound.private_allowlist_used`. `ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP` reste `0` hors
   développement local.
3. `ACP_SKILLS_STORAGE_DIR` doit pointer vers un **volume persistant** : les révisions
   de skills y vivent, et un système de fichiers éphémère les perdrait au redéploiement
   alors que la base continuerait de les référencer. Ce stockage n'est ni privé, ni
   servi par URL signée, ni soumis à rétention : c'est une limite connue.
4. `ACP_SKILLS_ALLOWED_DIRS` n'a de sens que si un dossier de confiance est monté dans
   le conteneur ; vide, l'import par dossier est refusé (`403`), ce qui est le bon
   défaut en production.
5. `ACP_SKILLS_GITHUB_ENABLED=1` ouvre une sortie réseau vers `api.github.com` (et la
   redirection vers `codeload.github.com`), sous la même politique de sortie. Ne
   définir `ACP_GITHUB_TOKEN` que si un dépôt privé est réellement nécessaire.

Sur la **machine du worker**, jamais sur le serveur de contrôle :

```text
ACP_WORKER_MCP_STDIO_ENABLED=0
ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES=
ACP_WORKER_MCP_STDIO_TIMEOUT_SECONDS=20
```

La capacité `mcp_stdio_probe` n'est annoncée que si le drapeau vaut `1` **et** que
l'allowlist d'exécutables absolus n'est pas vide. Activer cette sonde revient à
autoriser le lancement de programmes listés sur cette machine : la traiter comme une
décision d'exploitation, pas comme un réglage de confort.

## Variables du Lot E (flux, livrables et tests web)

Sur le service **api** uniquement :

```text
ACP_ARTIFACT_STORAGE_DIR=/data/artifacts
ACP_ARTIFACT_SIGNING_KEYS=<clé>[,<clé précédente>…]
ACP_ARTIFACT_PUBLIC_ORIGIN=https://apercu.<domaine>
ACP_ARTIFACT_MAX_BYTES=209715200
ACP_ARTIFACT_MAX_BYTES_PER_RUN=1073741824
ACP_ARTIFACT_RETENTION_DAYS=180
ACP_EVENT_RETENTION_DAYS=90
ACP_STREAM_POLL_INTERVAL_MS=400
ACP_STREAM_KEEPALIVE_SECONDS=15
ACP_STREAM_MAX_SECONDS=900
ACP_STREAM_MAX_CONNECTIONS_PER_USER=4
```

Points à tenir, dans cet ordre :

1. `ACP_ARTIFACT_STORAGE_DIR` doit pointer vers un **volume persistant**, comme
   `ACP_SKILLS_STORAGE_DIR`. Les blobs y vivent ; un système de fichiers éphémère les
   perdrait au redéploiement alors que la base continuerait de les référencer. Le
   stockage est local : **aucun adaptateur objet distant n'est livré**.
2. `ACP_ARTIFACT_PUBLIC_ORIGIN` est le **prérequis de sécurité de ce lot**. Tant
   qu'elle est vide, les liens signés pointent vers l'origine de l'API et le Studio
   affiche l'avertissement correspondant. Un contenu rapporté par un test est du
   contenu tiers : il ne doit pas être servi depuis l'origine qui porte le cookie de
   session. Le service qui répond sur cette origine doit atteindre la même API — c'est
   une origine, pas un second stockage.
3. `ACP_ARTIFACT_SIGNING_KEYS` suit la même discipline que `ACP_SECRETS_KEYS` : la
   première clé signe, les suivantes vérifient encore. **La perdre n'est pas grave**
   (les liens deviennent invalides, le téléchargement par session reste possible) ; la
   divulguer permet de forger un lien vers n'importe quel artefact jusqu'à expiration.
   Sans clé, la création de lien répond `503` explicite.
4. Les deux durées de rétention (`ACP_ARTIFACT_RETENTION_DAYS`,
   `ACP_EVENT_RETENTION_DAYS`) ne sont appliquées par **aucun ordonnanceur** :
   `python -m acp_api.retention` est une commande à déclencher, et elle ne supprime
   rien sans `--apply`. Tant qu'elle n'est pas planifiée, le stockage croît sans limite.
5. Le flux SSE tient une connexion longue par onglet et interroge la base toutes les
   `ACP_STREAM_POLL_INTERVAL_MS`. Derrière un proxy, vérifier que la mise en tampon est
   désactivée (l'API envoie déjà `X-Accel-Buffering: no`) et que le délai d'inactivité
   du proxy dépasse `ACP_STREAM_KEEPALIVE_SECONDS`, sans quoi chaque keep-alive arrivera
   trop tard et le client vivra en reconnexion permanente.

Sur la **machine du runner de tests**, jamais sur le serveur de contrôle :

```text
ACP_WORKER_WEBTEST_ENABLED=0
ACP_WORKER_WEBTEST_ARGV_JSON=
ACP_WORKER_WEBTEST_CWD=
ACP_WORKER_WEBTEST_TIMEOUT_SECONDS=900
ACP_WORKER_WEBTEST_MAX_ARTIFACT_BYTES=209715200
ACP_WORKER_WEBTEST_ENV_ALLOWLIST=
```

La plateforme n'installe jamais Playwright : c'est l'opérateur qui l'installe sur le
runner et qui déclare l'argv absolu à lancer. La capacité `web_tests` n'est annoncée que
si la configuration est complète **et** que le worker n'est pas en simulation. Ne jamais
allowlister un credential de la plateforme dans `ACP_WORKER_WEBTEST_ENV_ALLOWLIST` : le
processus de test n'en reçoit aucun, et les valeurs qui y sont injectées servent de
liste d'expurgation pour ce que le rapport republie.

**Aucune de ces variables n'a été éprouvée en déploiement** : aucun navigateur réel n'a
été lancé, aucune suite Playwright n'a tourné, aucune origine d'aperçu n'a été
provisionnée et aucun volume persistant n'a été monté.

## Variables Hermes

Sur Hermes :

```text
API_SERVER_ENABLED=true
API_SERVER_KEY=<secret>
```

Sur le provider-gateway :

```text
HERMES_BASE_URL=https://<service-hermes-prive>
HERMES_API_KEY=<même secret>
HERMES_TIMEOUT_SECONDS=30
HERMES_MAX_RETRIES=2
HERMES_RUN_TIMEOUT_SECONDS=120
HERMES_POLL_INTERVAL_SECONDS=0.5
```

Épingler Hermes sur `v2026.9.7` et conserver son stockage persistant. La vérification
de santé du gateway appelle `/health/detailed` puis `/v1/capabilities`; un simple
200 sur `/health` n'autorise pas un Run.

Ces URL sont des cibles de sécurité, pas la preuve qu'un domaine ou TLS a été
provisionné. Le worker Lot C refuse HTTP hors loopback afin de ne jamais envoyer ses
jetons en clair ; une éventuelle adresse interne Railway doit donc être placée derrière
une terminaison TLS vérifiée avant de raccorder un worker distant.

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
- authentification de `/internal/events` ; le flux utilisateur authentifié et la reprise
  par curseur sont livrés depuis le Lot E, l'outbox ne l'est pas ;
- migrations Alembic et driver PostgreSQL verrouillé, test de montée et retour ; la
  migration additive des compteurs d'événements est propre à SQLite et une base
  PostgreSQL **existante** ne la reçoit pas ;
- sauvegarde et rotation documentées de `ACP_SECRETS_KEYS` et
  `ACP_ARTIFACT_SIGNING_KEYS`, et volumes persistants pour `ACP_SKILLS_STORAGE_DIR` et
  `ACP_ARTIFACT_STORAGE_DIR` ;
- **origine d'aperçu séparée configurée** (`ACP_ARTIFACT_PUBLIC_ORIGIN`) : les URLs
  signées et les politiques de rétention existent, l'origine dédiée non ;
- purge de rétention planifiée : la commande existe, aucun ordonnanceur ne l'exécute ;
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
   mission. Depuis le Lot E, vérifier aussi que le client bascule en interrogation après
   trois échecs, puis reprend le direct, sans doublon ni trou dans le journal.
7. Tester rotation/révocation des clés et absence de secrets dans les logs.
8. Vérifier qu'un livrable de type `text/html` ou une trace `.zip` part bien en
   téléchargement (`Content-Disposition: attachment`, `nosniff`) et jamais en rendu
   inline, et qu'un lien signé expiré ou révoqué est refusé.
9. Exécuter `python -m acp_api.retention` sans `--apply` et lire ce qu'elle annoncerait
   avant de la planifier.

Aucun projet Railway, ressource payante, migration de production ou DNS n'a été créé
ou modifié pendant cette intervention.
