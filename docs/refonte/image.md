# Image Hermes d'ACP — étapes P1 et P2

État du **25 septembre 2026**. Étape P2 du [plan de la refonte](plan.md) : sur Railway,
l'agent n'a **aucun outil d'exécution** (ni terminal, ni fichiers, ni exécution de code, ni
navigateur, ni cron, ni délégation : décision du propriétaire du 25 septembre 2026) et Hermes
ne tourne **jamais hors des gardes d'ACP** (PID 1, s6, volume). L'exécution passe par le poste
Windows du propriétaire. Tout ce document est prouvé **en local et en CI** ; rien n'est
déployé. Le fournisseur d'identité (`identite/`, Authelia) est décrit dans
[identite.md](identite.md) ; l'infrastructure Railway (`.railway/`) et la procédure
d'exploitation et de récupération dans [railway.md](railway.md).

L'étape P1 (image dérivée, gardes de démarrage, managed scope, greffon `acp-poste`, CI de
contrat) reste valable ; ses sections sont mises à jour ci-dessous, et chaque ajout de P2 est
signalé comme tel.

Les références `fichier:ligne` désignent le source de Hermes Agent à l'étiquette
`v2026.9.24` (commit `f97608f`), sauf mention contraire.

## 1. En bref

| Élément | Emplacement dans le dépôt | Dans l'image |
|---|---|---|
| Dockerfile dérivé | `hermes/image/Dockerfile` | — |
| Gardes de démarrage (crochet s6) | `hermes/image/acp-gardes` | `/opt/acp/bin/acp-gardes` (`S6_STAGE2_HOOK`) |
| Données du volume (cont-init) | `hermes/image/cont-init.d/05-acp` | `/etc/cont-init.d/05-acp` |
| Logique commune, en Python | `hermes/image/acp_demarrage.py` | `/opt/acp/bin/acp_demarrage.py` |
| Modèle de la managed scope | `hermes/gere/config.yaml` | `/opt/acp/gere/config.yaml` → `/etc/hermes/config.yaml` |
| Contrat épinglé | `hermes/contrat/` | `/opt/acp/contrat/` |
| Persona | `hermes/persona/SOUL.md` | `/opt/acp/persona/SOUL.md` → `/opt/data/SOUL.md` |
| Thème (provisoire) | `hermes/theme/acp.yaml` | `/opt/acp/theme/` → `/opt/data/dashboard-themes/` |
| Greffon `acp-poste` | `hermes/plugins/acp-poste/` | `/opt/hermes/plugins/acp-poste/` |
| Garde d'entrée hors PID 1 (P2) | `hermes/image/acp-entree` | `/opt/acp/bin/acp-entree` (`ENTRYPOINT`) |
| Garde d'exécution de l'agent (P2) | `hermes/plugins/acp-poste/garde_execution.py` | dans le greffon |
| Image de test, outils | `hermes/tests/` | jamais dans l'image Railway |
| Workflow | `.github/workflows/image.yml` | — |
| Fournisseur d'identité (P2) | `identite/` | image séparée, voir [identite.md](identite.md) |
| Infrastructure Railway (P2) | `.railway/` | lue par le propriétaire seul, voir [railway.md](railway.md) |

Construction locale (contexte limité à `hermes/`) :

```sh
docker build -f hermes/image/Dockerfile -t acp-hermes:dev hermes
docker build -f hermes/tests/Dockerfile --build-arg IMAGE_ACP=acp-hermes:dev -t acp-hermes-tests:dev hermes/tests
```

## 2. Base épinglée

- `FROM nousresearch/hermes-agent:v2026.9.24@sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7`
  — condensat de l'**index** multi-architecture, relevé le 24 septembre 2026 par
  `docker buildx imagetools inspect nousresearch/hermes-agent:v2026.9.24` ;
  manifeste `linux/amd64` : `sha256:2fd023efbb8d3d2b0ce1a73d028b07370cff34f567cfe0e999553e8c327ea283`.
- `hermes/contrat/HERMES_VERSION` porte les mêmes valeurs ; le workflow refuse de
  construire si le condensat publié de l'étiquette a changé ou si le `FROM` diverge.
- `hermes --version` dans l'image : `Hermes Agent v0.21.5 (2026.9.24) · upstream f97608f1`.
- Une montée de version passe par une PR qui change le `FROM`, `HERMES_VERSION` et la
  copie de l'OpenRPC. Jamais `hermes update`, `git pull`, `:latest` ni `AUTO_UPDATE`.

## 3. Démarrage d'un conteneur

0. **`ENTRYPOINT` = `/opt/acp/bin/acp-entree`** (étape P2). L'`ENTRYPOINT` officiel
   (`docker/entrypoint-dispatch.sh`) lance `/init` de s6-overlay quand il est PID 1
   (entrypoint-dispatch.sh:17-19) ; sinon (`docker run --init`, plateforme qui garde le PID 1),
   il se **replie sans s6** : `stage2-hook.sh` puis la commande, **sans aucune garde d'ACP**
   (entrypoint-dispatch.sh:21-25). `acp-entree` refuse donc de démarrer hors du PID 1 (code 1,
   message français) ; au PID 1, il fait `exec` de l'entrée officielle, qui garde ce PID. Déclarer un
   `ENTRYPOINT` remet à vide le `CMD` hérité : `CMD ["gateway","run"]` est redéclaré après.
   Railway ne documente pas le PID 1 de ses conteneurs (seul indice : une PR tierce) :
   `acp-entree` tranche au premier démarrage, en refusant explicitement.
1. **Crochet `S6_STAGE2_HOOK` = `/opt/acp/bin/acp-gardes`**, en root, au tout début de
   l'étape 2, avant tout service et tout script cont-init (rc.init de s6-overlay 3.2.3.0,
   `/package/admin/s6-overlay/etc/s6-linux-init/skel/rc.init`). L'en-tête
   `#!/command/with-contenv /bin/sh` lui donne l'environnement du conteneur (même motif que
   `01-hermes-setup`, Dockerfile:402-405). Il :
   - refuse une variable interdite ou invalide (§ 4) ;
   - régénère `/etc/hermes/config.yaml` et `/etc/hermes/.env` (root, 0644, écriture
     atomique) puis les relit et vérifie chaque épingle ;
   - inspecte `/opt/data/plugins`, `/opt/data/dashboard-themes` et `/opt/data/acp`
     (noms réservés, liens symboliques) sans rien écrire ;
   - (P2) exige que `/opt/data/hooks` et `/opt/data/scripts` soient **vides** (§ 6) ;
   - (P2) sur Railway, exige le volume du service monté sur `/opt/data` (§ 4) ;
   - (P2) journalise `[acp] commit déployé : <RAILWAY_GIT_COMMIT_SHA ou « inconnu »>`, même
     en cas de refus, pour relier chaque déploiement à son run `image.yml`.
   Un refus arrête le conteneur **avec le code 1** (`S6_BEHAVIOUR_IF_STAGE2_FAILS=2`) avant
   `01-hermes-setup` (qui consommerait `HERMES_AUTH_JSON_BOOTSTRAP`, `HERMES_UID`…) et
   avant `02-reconcile-profiles` (qui démarre la passerelle).
2. `01-hermes-setup`, `015-supervise-perms`, `02-reconcile-profiles` de l'image officielle.
3. **`/etc/cont-init.d/05-acp`** : refait les contrôles du crochet (défense en
   profondeur si `S6_STAGE2_HOOK` avait été retiré), refuse une variable interdite
   injectée dans `/opt/data/.env` (§ 4.3), vérifie que la managed scope installée
   correspond aux variables de ce démarrage, rend `/opt/data/plugins`,
   `/opt/data/dashboard-themes` et `/opt/data/acp` propriété de root (répertoires 0755,
   fichiers 0644, par descripteurs `O_NOFOLLOW`), ainsi que `/opt/data/hooks` et
   `/opt/data/scripts` (P2, vides, root 0755), **reprend à root le répertoire de
   services s6 `/run/service` et les scripts des passerelles dynamiques** (§ 4.4), dépose
   le thème et `SOUL.md`, écrit `/run/acp/etat-demarrage.json` (tmpfs, root 0644).
4. Services s6 : tableau de bord (`hermes dashboard --host 0.0.0.0 --port 9119`, uid
   hermes) et `main-hermes`. Le script `run` du tableau de bord est **enveloppé par une
   garde root d'ACP** (`hermes/image/acp-run-dashboard`, posée sur
   `/etc/s6-overlay/s6-rc.d/dashboard/run` à la construction) qui refuse la (re)lance sur
   un `/opt/data/.env` porteur d'une variable interdite ; le script officiel est préservé
   tel quel dans `/opt/acp/amont/s6-dashboard-run`. `05-acp` enveloppe de même le `run` de
   `gateway-default` une fois repris par root.
5. `CMD ["gateway","run"]` : la passerelle (cron, répartiteur kanban, api_server) tourne
   supervisée par s6 sous l'uid hermes (website/docs/user-guide/docker.md:61-66).

Pourquoi un crochet plutôt que le seul `05-acp` du plan : mesuré dans l'image, un script
cont-init en échec **n'empêche pas les suivants de tourner** ; s6 n'arrête le conteneur
qu'à la fin de l'étape cont-init. Avec les gardes en `05-acp` (ou même en `00-`), une
`API_SERVER_KEY` interdite était déjà consommée par `stage2-hook.sh` et la passerelle
démarrée par `02-reconcile-profiles` avant l'arrêt. Le crochet arrête tout avant.

`S6_BEHAVIOUR_IF_STAGE2_FAILS` elle-même est contrôlée : si elle ne vaut pas `2`, les
scripts d'ACP arrêtent le conteneur eux-mêmes (`/run/s6/basedir/bin/halt`, code 1).

**Sentinelle hors s6 (P2).** Si Hermes est lancé sans passer par l'`ENTRYPOINT`
(`docker run --entrypoint hermes … gateway run`, Start Command Railway autre que la
maintenance), `acp-entree` ne tourne pas. Le greffon `acp-poste`, chargé par tout processus de
Hermes, arrête alors lui-même **`hermes gateway run` et `hermes dashboard`** de production
(`HERMES_HOME=/opt/data`) quand le PID 1 n'est pas `s6-svscan` : message français sur la sortie
d'erreur, `os._exit(78)`. Les commandes ponctuelles, les workers kanban (`-p default … chat -q`)
et les tests ne sont pas visés. La passerelle découvre les greffons dès son démarrage
(gateway/run_startup.py:1017-1020), le tableau de bord aussi (hermes_cli/main.py:2659-2673).

## 4. Variables Railway

### Attendues

| Variable | Obligatoire | Validation | Destination |
|---|---|---|---|
| `HERMES_DASHBOARD_PUBLIC_URL` | oui | https, hôte public (ni `localhost`, ni IP non publique), sans requête, fragment ni identifiants | `/etc/hermes/.env` et `dashboard.public_url` |
| `HERMES_DASHBOARD_OIDC_ISSUER` | oui | idem | `.env` géré et `dashboard.oauth.self_hosted.issuer` |
| `HERMES_DASHBOARD_OIDC_CLIENT_ID` | oui | 1 à 200 caractères `[A-Za-z0-9._:@+/-]` | `.env` géré et `dashboard.oauth.self_hosted.client_id` |
| `HERMES_DASHBOARD_OIDC_SCOPES` | non (`openid profile email`) | portées séparées par une espace, `openid` exigé | `.env` géré et `dashboard.oauth.self_hosted.scopes` |
| `HERMES_DASHBOARD_OIDC_CLIENT_SECRET` | non (client public, PKCE seul) | non vide, sans espace, ≤ 512 caractères ; jamais affiché | **jamais recopié** : lu directement dans l'environnement par Hermes |

Noms exacts relevés dans `plugins/dashboard_auth/self_hosted/__init__.py:285-310` (le
fournisseur s'appelle `self-hosted`, sa clé de greffon `dashboard_auth/self_hosted`).
L'URI de retour à déclarer chez le fournisseur d'identité est
`<HERMES_DASHBOARD_PUBLIC_URL>/auth/callback` (vérifiée par
`plugins/dashboard_auth/_shared.py:93-101`). Un client **public** est recommandé : aucun
secret n'existe alors nulle part. Un secret client fourni reste lisible par l'agent, qui
tourne sous le même uid que le tableau de bord (environnement du processus,
`/run/s6/container_environment`, rendu lisible par rc.init) : il ne protège rien contre
lui.

Fixées par l'image, refusées si Railway les change : `HERMES_HOME=/opt/data`,
`HERMES_WEB_DIST=/opt/hermes/hermes_cli/web_dist`, `HERMES_DASHBOARD=1`,
`HERMES_DASHBOARD_HOST=0.0.0.0`, `HERMES_DASHBOARD_PORT=9119`,
`S6_BEHAVIOUR_IF_STAGE2_FAILS=2`, `S6_STAGE2_HOOK=/opt/acp/bin/acp-gardes` ;
`API_SERVER_HOST` n'est admise qu'à `127.0.0.1`. Depuis P2, aussi les valeurs de l'`ENV`
officiel (Dockerfile:427-449 de Hermes) : `HERMES_WRITE_SAFE_ROOT=/opt/data`,
`HERMES_DISABLE_LAZY_INSTALLS=1`, `HERMES_LAZY_INSTALL_TARGET=/opt/data/lazy-packages`,
`HERMES_TUI_DIR=/opt/hermes/ui-tui`, `XDG_RUNTIME_DIR=/tmp/hermes-runtime`.

**Règles Railway (P2).**
- `RAILWAY_RUN_UID` n'est admise qu'absente ou égale à `0` : s6-overlay et les gardes
  exigent root.
- **Volume exigé** : si `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_DEPLOYMENT_ID` ou
  `RAILWAY_SERVICE_ID` est présente, `RAILWAY_VOLUME_MOUNT_PATH` doit valoir `/opt/data` **et**
  `/opt/data` doit être un vrai point de montage (5e champ de `/proc/self/mountinfo`) : sans
  volume, Hermes tournerait sur un disque éphémère et perdrait tout au redéploiement.
- `RAILWAY_GIT_COMMIT_SHA` (variable documentée par Railway) est journalisée et exposée par
  `/v1/meta` si elle a la forme d'un SHA git ; toute autre valeur devient « inconnu ».

### Interdites (leur seule présence, même vide, refuse le démarrage)

| Variable | Raison |
|---|---|
| `HERMES_MANAGED_DIR` | déplacerait la managed scope hors de `/etc/hermes` (managed_scope.py:45-59) |
| `API_SERVER_KEY`, `API_SERVER_ENABLED`, `API_SERVER_PORT` | l'image génère sa clé en boucle locale (stage2-hook.sh:459-540) ; l'api_server reste sur 127.0.0.1:8642 |
| `HERMES_DASHBOARD_OAUTH_CLIENT_ID`, `HERMES_DASHBOARD_PORTAL_URL` | fournisseur Nous Portal écarté (décision du propriétaire) |
| `HERMES_DASHBOARD_BASIC_AUTH_*` | fournisseur par mot de passe écarté |
| `HERMES_DASHBOARD_DRAIN_SECRET` | fournisseur drain désactivé |
| `HERMES_DASHBOARD_INSECURE` | jamais de tableau de bord sans authentification |
| `HERMES_BUNDLED_PLUGINS`, `HERMES_ENABLE_PROJECT_PLUGINS` | tout greffon vient de l'image |
| `HERMES_KANBAN_HOME`, `HERMES_KANBAN_DB`, `HERMES_KANBAN_BOARD` | emplacement et tableau courant du kanban fixes |
| `HERMES_ALLOW_ROOT_GATEWAY`, `HERMES_DOCKER_EXEC_AS_ROOT` | rien ne tourne en root hors de l'amorçage |
| `HERMES_AUTH_JSON_BOOTSTRAP`, `HERMES_AUTH_JSON_REBOOTSTRAP` | aucun identifiant injecté dans `auth.json` (stage2-hook.sh:659-696) |
| `HERMES_UID`, `HERMES_GID`, `PUID`, `PGID` | l'agent reste sous l'uid 10000 de l'image |
| `HERMES_GATEWAY_NO_SUPERVISE` | la passerelle reste supervisée par s6 |
| `AUTO_UPDATE`, `DASHBOARD_PASSWORD` | restes de l'ancien modèle Railway |
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (et minuscules), `SSL_CERT_FILE`, `SSL_CERT_DIR`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` | mandataires et autorités de certification fixés par la managed scope |
| `HERMES_TUI_TOOLSETS` (P2) | remplacerait les outils de la discussion du tableau de bord, terminal compris |
| `HERMES_BIN` (P2) | choisirait le programme lancé pour chaque worker kanban |
| `HERMES_ACCEPT_HOOKS` (P2) | inscrirait sans consentement les crochets shell de la configuration |
| `HERMES_SAFE_MODE` (P2) | sauterait la découverte des greffons, donc la garde d'exécution |
| `HERMES_YOLO_MODE` (P2) | approuverait sans demander toute commande dangereuse |
| `HERMES_COPILOT_ACP_COMMAND`, `HERMES_COPILOT_ACP_ARGS`, `COPILOT_CLI_PATH` (P2) | choisiraient un programme exécuté comme fournisseur copilot-acp |
| `HERMES_ALLOW_PRIVATE_URLS` (P2) | l'accès de l'agent au réseau privé (8642, 9119, réseau Railway) reste fermé : fixée à `false` par l'image |
| `HERMES_PORTAL_BASE_URL`, `NOUS_PORTAL_BASE_URL`, `NOUS_INFERENCE_BASE_URL` (P2) | Nous Portal écarté ; stage2-hook.sh les recopierait (stage2-hook.sh:579-610) |
| `HERMES_GATEWAY_BOOTSTRAP_STATE` (P2) | l'état initial de la passerelle n'est jamais injecté |

Le message de refus est en français, préfixé `[acp] REFUS :`, et nomme chaque variable
fautive (toutes les erreurs d'un démarrage sont listées d'un coup).

### 4.3 Variables interdites injectées dans `/opt/data/.env`

`/opt/data/.env` appartient à l'agent et Hermes le charge avec `override=True` **avant** la
managed scope (env_loader.py:433-435 puis 473). Les variables neutres (Nous, basic, drain,
mandataires, greffons de projet et groupés) sont épinglées dans `/etc/hermes/.env`,
appliquée en dernier, et gagnent donc. Mais `HERMES_MANAGED_DIR` **choisit quel `.env` géré
est lu** (managed_scope.py:52) : aucune épingle ne peut la contrer. Les gardes (`gardes` et
`05-acp`) **refusent donc de démarrer**, et la garde des scripts `run` **refuse la relance**,
si un `.env` du volume (`/opt/data/.env` ou `profiles/*/.env`) porte l'une de ces variables :

| Variable | Raison |
|---|---|
| `HERMES_MANAGED_DIR` | déplacerait la portée gérée hors de `/etc/hermes` ; aucune épingle ne la contre |
| `HERMES_BUNDLED_PLUGINS` | ferait charger le code de greffon de l'agent (aussi épinglée vide) |
| `HERMES_ENABLE_PROJECT_PLUGINS` | servirait le JS de l'agent au navigateur du propriétaire (aussi épinglée à `0`) |

La liste est **étroite à dessein** : `API_SERVER_KEY` en est exclue, car l'image la génère
et l'écrit elle-même dans `/opt/data/.env` à chaque démarrage
(docker/stage2-hook.sh:504-540) ; la refuser bloquerait tout démarrage. `.env.example`, semé
au premier démarrage, ne contient aucune de ces variables (vérifié).

### 4.4 Reprise à root des services s6

L'image officielle rend `/run/service` et les emplacements de service des passerelles
propriété de l'agent (docker/cont-init.d/02-reconcile-profiles:119 ;
docker/cont-init.d/015-supervise-perms). Or **s6-supervise tourne en root** (spawné par
s6-svscan en PID 1, hermes_cli/container_boot.py:291) : un service que l'agent créerait sous
`/run/service`, ou un script `run` qu'il réécrirait, serait exécuté **en root** avant de
retomber sous l'uid hermes — une élévation. `05-acp` reprend donc à root le répertoire
`/run/service` (l'agent ne peut plus y créer de service) et, pour chaque passerelle
dynamique, son répertoire et ses scripts (`run`, `finish`, `type`, `log/`, `log/run`,
`supervise/`). Il ne reste à l'agent que la **FIFO `supervise/control`**, pour qu'il puisse
encore relancer la passerelle par `s6-svc -r` (comportement attendu et testé). Conséquence
voulue : seul le profil `default` reste enregistrable, ce qui concorde avec
`kanban.dispatch_profiles: [default]`.

### 4.5 `PATH` des scripts root

L'image officielle met `/opt/data/.local/bin`, que l'agent possède, dans son `PATH`, **avant**
`/usr/bin` et `/bin` (Dockerfile:476). Or tous les scripts que s6 exécute en root — crochet,
scripts cont-init, scripts `run` des services — reçoivent ce `PATH` par `with-contenv`
(`/run/s6/container_environment/PATH`). Constaté sur `6b5a699` : l'agent dépose un faux `id`
dans `/opt/data/.local/bin`, relance le tableau de bord par `s6-svc -r`, et son script tourne
**en root** (`uid=0(root)`). Avec un faux binaire pour chaque commande système, quatorze
d'entre elles (`cat`, `chown`, `chmod`, `curl`, `stat`…) sont exécutées en root au cours des
relances et du redémarrage. Le fichier est sur le volume : le piège survit aux redémarrages.

**Correctif** : le `Dockerfile` d'ACP redéfinit `PATH` sans aucun répertoire du volume ; les
gardes refusent tout `PATH` qui sort de `PATH_ADMIS` (`/command`, `/opt/hermes/bin`,
`/opt/hermes/.venv/bin` et les répertoires système, tous à root) ; les scripts d'ACP
appellent `/bin/sh` et `/bin/sleep` par leur chemin absolu. Le terminal local de l'agent
rajoute lui-même `~/.local/bin`, **en fin** de `PATH`, à ses propres shells
(tools/environments/local.py:630-657) : ses outils installés par `pip --user` ou `uv tool`
restent utilisables, sans jamais masquer une commande système. En revanche, un programme
lancé par la passerelle elle-même hors du terminal (un serveur MCP stdio, par exemple) ne
cherche plus dans `~/.local/bin` : il doit être désigné par son chemin absolu, ce que fera
le catalogue épinglé de P3. Prouvé par
`test_les_scripts_root_n_executent_pas_les_binaires_de_l_agent` : sur l'ancienne image il
échoue (quatorze traces root), sur la nouvelle aucun faux binaire ne tourne en root, ni aux
relances du tableau de bord et de la passerelle par l'agent, ni au redémarrage.

Ce défaut vient de l'image officielle, pas d'ACP ; il n'avait été vu ni par l'implémentation
ni par la relecture indépendante de P1. D'autres chemins root lisent encore le volume
(`stage2-hook.sh`, `02-reconcile-profiles`) sans audit exhaustif (§ 10).

## 5. Managed scope `/etc/hermes`

Hermes l'applique en dernier, feuille par feuille, et `hermes config set` refuse toute
clé épinglée (managed_scope.py:125-147 ; config.py:3384-3391 ; env_loader.py:473 et
503-518). Ce que garantit cette portée tient à la permission : root, 0755/0644, et l'agent
tourne sous l'uid 10000 sans sudo. Un fichier géré qui ne se lit pas serait **ignoré en
silence** (managed_scope.py:86-93) : `acp_demarrage.py` le relit avec le chargeur YAML de
Hermes (`utils.fast_safe_load`, utils.py:613-615) et refuse de démarrer si une épingle
manque ou diffère. Le modèle est aussi validé à la construction de l'image.

**Ce que la portée gérée ne garantit pas.** L'agent tourne sous le **même uid** que le
tableau de bord (10000). Il ne peut pas modifier `/etc/hermes` ; depuis P2, il n'a plus aucun
outil d'exécution (ci-dessous) pour tuer le processus du tableau de bord ou écouter sur
`0.0.0.0:9119`. Il ne le pourrait plus que par une **faille de Hermes lui-même** (§ 10).

**`/etc/hermes/config.yaml`** (**40 clés** depuis P2, 28 en P1) : `kanban.auto_decompose: false`,
`kanban.dispatch_profiles: [default]`, `approvals.mode: manual` (et `cron_mode`,
`single_query_mode`, `unattended_mode` : `deny`), `plugins.enabled: []`,
`plugins.disabled: [dashboard_auth/basic, dashboard_auth/nous, dashboard_auth/drain]`,
`plugins.allow_deprecated_imports: false`, `auth.adopt_external_logins: false`,
`security.redact_secrets: true`, `display.language: fr`, `dashboard.theme: acp`,
`dashboard.trusted_proxies: []` (vide tant que le bord Railway n'est pas mesuré, décision P2),
`dashboard.public_url` et `dashboard.oauth.self_hosted.{issuer, client_id, scopes}` (valeurs
Railway validées), `dashboard.oauth.self_hosted.client_secret: ""`,
`dashboard.oauth.{client_id, portal_url}: ""`,
`dashboard.basic_auth.{username, password, password_hash, secret}: ""`,
`platforms.api_server.extra.host: 127.0.0.1` et `platforms.api_server.extra.port: 8642`
(l'agent ne peut pas déplacer l'api_server sur `0.0.0.0` par `/opt/data/config.yaml` : la
valeur de config.yaml gagne sinon sur `API_SERVER_HOST`, gateway/platforms/api_server.py:209-218,
et sans clé utilisable dans l'environnement il enrôlerait l'api_server lui-même,
gateway/config_env.py:307-315) ; et, depuis P2 :

- `agent.disabled_toolsets: [browser, terminal, file, code_execution, computer_use,
  connections, cronjob, delegation, setup]` ;
- `agent.coding_context: "off"` (guillemets obligatoires : `off` nu est un booléen pour
  PyYAML ; `focus` réduirait les outils au jeu de codage, terminal compris) ;
- `agent.service_tier: ""` (mode rapide coupé ; écart au plan P2, voir plus bas) ;
- `platform_toolsets.api_server: [web, vision, skills, todo, memory, session_search, no_mcp]`,
  `platform_toolsets.cli: [web, vision, skills, todo, memory, session_search, clarify, no_mcp]`,
  `platform_toolsets.cron: [web, vision, skills, todo, memory, session_search, no_mcp]` ;
- `skills.inline_shell: false`, `skills.write_approval: true`, `skills.guard_agent_created: true` ;
- `memory.write_approval: true` (décision du propriétaire) ;
- `hooks_auto_accept: false` ;
- `security.allow_private_urls: false` et `security.allow_lazy_installs: false`.

Aucun secret : une clé dont le nom évoque un secret et qui porte une valeur est refusée.

**`/etc/hermes/.env`** (**38 variables** depuis P2, 28 en P1) : les quatre variables OIDC et
l'URL publique validées, `API_SERVER_HOST=127.0.0.1`, `API_SERVER_PORT=8642`,
`HERMES_LANGUAGE=fr`, **`HERMES_ENABLE_PROJECT_PLUGINS=0`** et **`HERMES_BUNDLED_PLUGINS=`**
vide, `SSL_CERT_FILE` et `REQUESTS_CA_BUNDLE`/`CURL_CA_BUNDLE` sur
`/etc/ssl/certs/ca-certificates.crt`, `SSL_CERT_DIR=/etc/ssl/certs`, des valeurs **vides**
pour Nous, basic, drain, les mandataires et, en client public,
`HERMES_DASHBOARD_OIDC_CLIENT_SECRET` ; et, depuis P2, **`HERMES_ALLOW_PRIVATE_URLS=false`**
(seule protection effective contre les appels de l'agent vers le réseau privé :
tools/url_safety.py:145-173 lit cette variable et config.yaml SANS la managed scope),
`HERMES_DISABLE_LAZY_INSTALLS=1`, et des valeurs vides pour `HERMES_TUI_TOOLSETS`,
`HERMES_BIN`, `HERMES_ACCEPT_HOOKS`, `HERMES_SAFE_MODE`, `HERMES_YOLO_MODE`,
`HERMES_COPILOT_ACP_COMMAND`, `HERMES_COPILOT_ACP_ARGS` et `COPILOT_CLI_PATH`. Appliqué en
dernier, ce fichier neutralise ces variables posées dans `/opt/data/.env`.

Les autorités de certification sont épinglées **sur le magasin du système, jamais à
vide** : constaté dans l'image, `SSL_CERT_FILE=` vide prive OpenSSL de toute autorité et la
récupération du JWKS par PyJWT (urllib) échoue ; plus personne ne pourrait se connecter.
Épinglées, elles empêchent aussi un agent de faire valider par le tableau de bord un
fournisseur d'identité usurpé (autorité et mandataire posés dans `/opt/data/.env`).

### Aucun outil d'exécution pour l'agent (P2) : trois couches

Aucune couche ne suffit seule ; chacune est prouvée séparément, avec son témoin négatif (§ 8).

1. **Listes de la managed scope.** `agent.disabled_toolsets` retire les jeux outil par outil
   (model_tools.py:334-340) pour la messagerie, le cron, le CLI, les workers kanban et la
   délégation. Mais l'**api_server** (api_server.py:2231-2270) et le **tableau de bord**
   (tui_gateway/server.py:2451-2468) ne transmettent PAS cette liste à l'`AIAgent` : d'où
   `platform_toolsets`, des listes **explicites sans composite**. Mesuré : sans elles, un nom
   de jeu non configurable posé par le volume (`debugging`, qui contient terminal) passe tel
   quel (tools_config.py:614-615 et 678-690) et survit à l'élagage de `disabled_toolsets`
   parce que ses outils web y survivent (tools_config.py:635-651) : l'api_server et le tableau
   de bord recevraient terminal. Une liste `cli` **vide** ferait rendre TOUS les jeux au
   tableau de bord (tui_gateway/server.py:1942) : elle est épinglée non vide.
2. **Épingles du `.env` géré** : `HERMES_TUI_TOOLSETS` (qui remplacerait la liste du
   tableau de bord), `HERMES_BIN` (programme des workers : vide = `python -m
   hermes_cli.main`, mesuré), `HERMES_ACCEPT_HOOKS`, `HERMES_SAFE_MODE`… sont vides, et
   interdites comme variables Railway (§ 4).
3. **Crochet `pre_tool_call` en LISTE BLANCHE** (`hermes/plugins/acp-poste/garde_execution.py`),
   enregistré par le greffon. Tout `AIAgent` découvre lui-même les greffons avant de choisir
   ses outils (agent/agent_init.py:1060-1065) : passerelle (api_server, cron), chaque worker
   kanban, processus du tableau de bord (`/api/ws`, en processus : web_routers/chat_ws.py:583-601),
   `tui_gateway.entry`. C'est la **seule** couche qui ferme `preview.restart`, dont l'agent
   caché reçoit `["terminal","file"]` codés en dur (tui_gateway/agent_callbacks.py:371-374).

**Les 24 outils admis** (noms exacts) : `web_search`, `web_extract`, `vision_analyze` ;
`skills_list`, `skill_view`, `skill_manage` ; `todo_list`, `memory`, `session_search`,
`clarify` ; `tool_search`, `tool_describe` ; `kanban_show`, `kanban_list`, `kanban_complete`,
`kanban_block`, `kanban_request_review`, `kanban_request_changes`, `kanban_heartbeat`,
`kanban_comment`, `kanban_link`, `kanban_unblock`, `kanban_attach`, `kanban_attachments`.
Tout autre nom est refusé : « Refusé par ACP : l'outil « … » n'est pas autorisé sur Railway
(ni terminal, ni fichiers, ni exécution de code pour l'agent). L'exécution passe par le poste
Windows du propriétaire. » (terminal, fichiers, `execute_code`, le pont `tool_call`,
`desktop_project`, `browser_*`, noms inconnus, futurs outils).

**Retirés en P2**, avec un message dédié :
- `kanban_create` : le worker lancé recevrait les skills, le modèle, le fournisseur et
  l'espace de travail choisis par l'agent (kanban_db_dispatch.py:2676-2710 et 2820-2887).
  Réadmis en P5 seulement avec une liste blanche d'arguments (`title`, `body`, `assignee`
  limité aux profils du poste, `parents`, `priority`, `idempotency_key`, `triage`) ;
- `kanban_attach_url` : `is_safe_url` puis `httpx.stream` ordinaire, sans protection contre
  le rebinding DNS vers le réseau privé (tools/kanban_tools.py:924-958 ; url_safety.py:7-10).

La garde **ne lève jamais** (`except BaseException` → « Refusé par ACP. ») : Hermes bloque
d'ailleurs un rappel qui lève (plugins_dispatch.py:229-241), mais la couche d'appel autour
échoue ouvert (agent_runtime_helpers.py:2348-2361 ; tool_executor.py:652-667).

**Échec ouvert connu, dit** : si la découverte des greffons lève, l'agent continue **sans
aucun greffon** (agent/agent_init.py:1066-1067). Les couches 1 et 2 tiennent encore partout,
sauf pour `preview.restart`. Parades : `test_decouverte_des_greffons_reussit` sur l'image
épinglée, et l'alerte du bloc `garde_execution` de `/v1/meta` (§ 7).

**Le tableau de bord AUTHENTIFIÉ reste un shell du propriétaire** : `shell.exec`, `cli.exec`,
`/api/pty`, `/api/mcp`, `/api/env`, quick_commands, éditeur de fichiers, `preview.restart`
côté client. Un vol de session équivaut à une exécution de code (jetons ChatGPT
d'`auth.json` compris). Décision du propriétaire : gardées sous le seul OIDC en P2, filtrage
de `/api/ws` en P4.

### Écarts au plan P2 (justifiés)

- **40 clés au lieu de 39** : `agent.service_tier: ""` est épinglé en plus (mode rapide
  coupé), à la demande de l'étape et en cohérence avec le plan d'autonomie validé (§ 7 de ce
  plan) ; sans effet sur les outils.
- **Témoin « composite »** : le plan supposait qu'un composite (`hermes-api-server`) rendrait
  terminal sans `platform_toolsets`. Mesuré sur Hermes 0.21.5 : un composite seul est ramené
  aux jeux configurables puis élagué par `disabled_toolsets` ; c'est un nom **non
  configurable** passé tel quel (`debugging`) qui rend terminal. Le témoin négatif est écrit
  sur ce cas réel.

### Pourquoi `plugins.enabled: []` et non `[acp-poste]` (écart au plan)

Le tableau de bord importe l'API Python d'un greffon **utilisateur** dès qu'il figure
dans `plugins.enabled` (web_server_dashboard.py:782-795 ; web_routers/dashboard_ui.py:118-128),
et dédoublonne par le nom déclaré en lisant d'abord `/opt/data/plugins`
(web_server_dashboard.py:548-579). Avec `acp-poste` dans la liste, un homonyme déposé
dans `/opt/data/plugins` serait exécuté dans le processus du tableau de bord. Or l'agent
peut relancer le tableau de bord lui-même (`s6-svc -r /run/service/dashboard`, dont
`015-supervise-perms` lui donne le contrôle), sans que `05-acp` ne tourne.
`acp-poste` est donc un greffon groupé de type `backend`, chargé sans figurer dans
`plugins.enabled` (plugins_discovery.py:264-267), dont l'API de tableau de bord est montée
sans elle (web_server_dashboard.py:790-795) ; la liste vide garantit qu'**aucun** greffon
utilisateur n'est jamais importé.

## 6. `/opt/data`

- **Refus** (crochet et `05-acp`) : tout lien symbolique ou fichier spécial sous
  `/opt/data/plugins`, `/opt/data/dashboard-themes`, `/opt/data/acp` ; toute entrée de
  premier niveau et tout dossier de second niveau (ceux dont Hermes tire un nom de
  greffon, plugins_discovery.py:109-161) dont le nom est `acp` ou commence par
  `acp-`/`acp_` ; tout manifeste (`plugin.yaml`, `plugin.yml`,
  `plugin.json`, `dashboard/manifest.json`) qui **déclare** un nom réservé (le nom du
  dossier par défaut, comme Hermes : plugins_manifest.py:505, web_server_dashboard.py:568) ;
  tout thème autre que ceux livrés qui déclare un nom `acp…`.
- **Verrouillage** : ces trois répertoires deviennent root, 0755, fichiers 0644, à chaque
  démarrage. Les greffons utilisateur existants sont signalés dans l'état du démarrage
  (jamais activables, `plugins.enabled: []`). Conséquence voulue : `hermes plugins
  install` ne peut plus écrire dans `/opt/data/plugins` (permission refusée) et le thème
  actif est épinglé (`dashboard.theme: acp`, le choix du tableau de bord ne l'emporte
  pas) ; tout greffon et tout thème passent par l'image.
- **SOUL.md** : le SOUL livré est déposé si le fichier est absent, identique au SOUL de
  l'image officielle (semé par stage2-hook.sh:457) ou identique à la dernière version
  déposée (empreinte dans `/opt/data/acp/soul.sha256`, root). Sinon il est laissé tel quel
  et signalé « divergent » par `/v1/meta`. Un lien symbolique n'est jamais suivi.
- **`/opt/data/hooks` et `/opt/data/scripts` (P2)** : la passerelle importe chaque
  `hooks/<nom>/handler.py` **sans consentement** (gateway/hooks.py:44-72) et le cron exécute
  les scripts de `scripts/` (cron/scheduler_script.py:257-320). Rien de légitime n'y est
  déposé sur Railway : le crochet et `05-acp` les inspectent **avant toute écriture**, et toute
  entrée (ou un lien symbolique à leur place) **refuse le démarrage** en les nommant ; ensuite
  ils deviennent root 0755. `stage2-hook.sh` ne les rend pas à l'agent tant que `/opt/data`
  lui appartient (stage2-hook.sh:228-254).
- **`/opt/data/lazy-packages` (P2)** : les installations paresseuses sont coupées (§ 5) ; un
  contenu autre que `.lock` et `.python-abi` est signalé (état du démarrage, `/v1/meta`,
  `diagnostiquer`) sans refuser le démarrage.
- **Migration** : aucune (décision du propriétaire : rien n'est déployé, P2 part d'un
  volume neuf). La reprise de propriété unique du plan (`chown -R`) n'est pas écrite.

### Maintenance : `diagnostiquer` (P2)

`/opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py diagnostiquer`, en root et
en **lecture seule** (rien n'est écrit : ni le volume, ni `/etc/hermes`, ni `/run/acp`),
rassemble tout ce qui ferait refuser le démarrage ou exécuter du code depuis le volume :

- **environnement de référence** : `/proc/1/environ` (octets nuls, rien n'est exécuté) si le
  PID 1 n'est pas `s6-svscan` (maintenance : Start Command `/bin/sh -c "exec sleep infinity"`),
  `/run/s6/container_environment` sous s6, sinon « inconnue » (code 1). **Jamais**
  l'environnement de la session qui lance la commande : la doc de Railway ne dit rien de
  celui d'une session `railway ssh` (rw_full.txt:23271-23420). La source lue est affichée ;
- contrôles : variables Railway (§ 4), montage de `/opt/data`, variables interdites des `.env`
  du volume, noms réservés et liens (§ 6), `hooks/` et `scripts/`, relecture de la managed
  scope installée (celle de construction est attendue en maintenance, sans constat) ;
- **clés exécutables** de `/opt/data/config.yaml` et `/opt/data/profiles/*/config.yaml`, lues
  sans suivre de lien : `mcp_servers.*.command`, `hooks` non vide, `quick_commands` de type
  `exec`, fournisseurs TTS ou STT de type `command` ;
- contenu de `/opt/data/lazy-packages`.

Chaque constat est préfixé `[acp] DIAGNOSTIC :` ; code 0 si rien n'est trouvé, 1 sinon. Aucune
liste d'exceptions n'est lue (et jamais depuis le volume). La procédure qui l'emploie est dans
[railway.md](railway.md) (§ 10).

## 7. Greffon `acp-poste`

- `plugin.yaml` : `kind: backend`, `requires_hermes: ">=0.21.5"`, version `0.11.0`
  (vérifiée par `scripts/check_version.py`).
- `register(ctx)` (P2) : sentinelle hors s6 (§ 3), puis
  `ctx.register_hook("pre_tool_call", garde_execution.garde)` (§ 5). Toujours ni outil
  `poste_*`, ni fournisseur de jeton machine, ni route à jeton : ils arrivent en P5.
- `kanban_adapter.py` : seul module qui importe l'interne kanban, chaque fonction depuis
  son module de définition (`hermes_cli.kanban_db`, `hermes_cli.kanban_db_connect.connect`,
  `hermes_cli.kanban_db_dispatch.heartbeat_worker`), tableau `poste` toujours nommé ;
  crée le tableau et des cartes en `triage`.
- `GET /api/plugins/acp-poste/v1/meta` (session du tableau de bord obligatoire) :

```json
{
  "contrat": "acp-poste/1",
  "greffon": {"nom": "acp-poste", "version": "0.11.0"},
  "hermes": {"version": "0.21.5", "version_testee": "0.21.5", "conforme": true,
             "etiquette": "v2026.9.24", "commit": "f97608f178d1ffeca59860195ab7da295f7c8e5f"},
  "image": {"base": "nousresearch/hermes-agent", "condensat_index": "sha256:fca358f1…"},
  "openrpc": {"info_version": "1", "info_version_epinglee": "1", "methodes": 237,
              "empreinte_installee": "c89a203e…", "empreinte_epinglee": "c89a203e…", "identique": true},
  "demarrage": {"schema": 1, "scope_geree": {…}, "greffons_utilisateur": {…},
                "themes_deposes": ["acp.yaml"], "soul": {"etat": "depose", …}},
  "alertes": []
}
```

  Toute valeur illisible vaut `null` et ajoute une alerte en français (« inconnu »).

  Blocs ajoutés en P2 :
  - **`garde_execution`** : la route demande la découverte des greffons (idempotente ; le
    tableau de bord la fait déjà, web_server_profiles.py:348-349) puis lit l'état de la garde
    **dans le processus du tableau de bord** — libellé « processus du tableau de bord (sert
    /api/ws) » : ce bloc ne prouve rien pour la passerelle ni pour les workers, qui sont
    d'autres processus. Si la découverte lève ou si le crochet est absent : alerte « Garde
    d'exécution absente du processus du tableau de bord : preview.restart rendrait un terminal
    à l'agent. » ;
  - **`reseau`** : pair, schéma vu, hôte et **présence** des en-têtes `X-Forwarded-For`,
    `-Proto`, `-Host`, `X-Real-IP`, `X-Railway-Edge` (jamais la valeur de `X-Forwarded-For`),
    `X-Forwarded-Proto` tronqué ; alerte si le schéma vu n'est pas https (cookies sans
    `Secure`). C'est la mesure qui permettra de renseigner `dashboard.trusted_proxies` ;
  - alerte si `/opt/data/lazy-packages` contient des paquets ;
  - **`deploiement.commit`** : le SHA relevé par `05-acp` (écrit par root dans l'état du
    démarrage, schéma 2), `null` hors Railway — jamais l'environnement du tableau de bord,
    que `/opt/data/.env` peut modifier.

## 8. Tests

- **Dans l'image de test** (`hermes/tests/image`, pytest installé hors du venv de Hermes,
  hachés vérifiés) : gardes et refus, génération et relecture de la managed scope,
  inspection et verrouillage de `/opt/data` (avec contrôles positifs d'écriture sous l'uid
  hermes), SOUL, adaptateur kanban (modules de définition, scan de compatibilité, carte en
  triage), route meta ; et **Hermes lui-même** face à un `/opt/data` piégé
  (`load_hermes_dotenv`, `load_config`, `_settings` des fournisseurs, porte des greffons),
  avec un contrôle négatif qui montre que, sans managed scope, l'injection l'emporterait.
- **Depuis l'hôte** (`hermes/tests/contrat`, Docker) : image, refus de démarrer, conteneur
  en marche, et pile authentifiée avec un **faux fournisseur d'identité** (image de test :
  autorité de certification jetable ajoutée au magasin du système) et le **modèle
  factice** compatible OpenAI (`hermes/tests/outils/modele_factice.py`, aucun appel réseau
  réel).

### Tests ajoutés en P2

Le modèle factice sait, depuis P2, répondre par UN appel d'outil : « OUTIL:<nom> » dans le
dernier message, ou un fichier de scénarios pour les workers kanban (« work kanban task
<id> »). Ses arguments sont des **témoins** : un outil d'exécution qui tournerait vraiment
laisserait un fichier dans `/tmp/acp-temoins` (par exemple `terminal` →
`touch /tmp/acp-temoins/terminal`). Il consigne les outils **offerts** et les résultats
d'outils reçus. Outils de test ajoutés : `sonde_surfaces.py` (outils offerts par chaque
surface, calculés par le code de Hermes dans un processus neuf), `agent_neuf.py` (un
`AIAgent` construit comme une surface réelle, dans un processus neuf, **sans appel manuel à
`discover_plugins`**) et `client_ws.py` (ticket puis JSON-RPC sur `/api/ws` du vrai tableau de
bord).

- **Dans l'image** (`test_sans_shell.py`, `test_demarrage.py`, `test_meta.py`) :
  - `test_aucune_surface_n_offre_d_outil_d_execution[vide|hostile]` : api_server, CLI, cron,
    tableau de bord (sources `tui` et `desktop`), worker kanban et enfant de délégation, sur un
    volume vide et sur un volume hostile (composites, `debugging`, `coding_context: focus`,
    `.env` piégé) ; témoins négatifs `test_temoin_scope_p1_rend_terminal`,
    `test_sans_platform_toolsets_un_composite_rend_terminal`, `test_coding_context_focus_neutralise` ;
  - `test_env_gere_neutralise_le_volume` ; `test_tour_api_server_refuse_terminal_ecriture_code_cron`
    (sept outils) ; `test_le_pont_tool_call_ne_rouvre_pas_terminal` ;
  - `test_garde_dans_un_agent_neuf` et son témoin négatif (managed scope de test qui désactive
    `acp-poste` : le témoin apparaît) ;
  - **`test_preview_restart_par_tui_gateway` (BLOQUANT, jamais ignoré)** : `python -m
    tui_gateway.entry` en stdio, `session.create` puis `preview.restart` (le vrai code de
    tui_gateway/methods_prompt.py:1075-1133) ; l'agent caché reçoit terminal, le modèle le
    demande, la garde le refuse ; et son témoin négatif, où terminal s'exécute ;
  - `test_garde_liste_blanche`, `test_garde_arguments_aberrants_sans_exception`,
    `test_un_rappel_qui_leve_est_bloque_par_hermes`, `test_la_garde_est_enregistree_par_register` ;
  - recensements : `test_recensement_des_constructions_aiagent` (sites `AIAgent(` et jeux
    d'outils écrits en dur, épinglés), `test_recensement_http_des_outils_admis` (appels HTTP
    directs des modules des outils admis et de leurs fournisseurs, épinglés par fichier et
    ligne), `test_decouverte_des_greffons_reussit` ;
  - `test_sentinelle_hors_s6` (neuf cas) ;
  - démarrage : `test_epingles_p2_obligatoires` (quatorze altérations du modèle),
    `test_variables_p2_interdites` (treize), `test_valeurs_imposees_p2` (cinq),
    `test_railway_run_uid`, `test_volume_railway`, `test_hooks_et_scripts_du_volume`,
    `test_lazy_packages_non_vide_est_signale`, `test_journal_commit_deploye`, décompte 40
    clés et 38 variables ;
  - `diagnostiquer` : `test_diagnostiquer_rassemble_sans_ecrire` (volume piégé de sept façons,
    plus un paquet dans `lazy-packages` : tous les motifs, empreinte de l'arbre inchangée,
    code 1), `test_diagnostiquer_un_volume_sain_rend_0`,
    `test_diagnostiquer_en_maintenance_accepte_la_scope_de_construction`,
    `test_diagnostiquer_source_environnement` (session `env -i` ; `/proc/1/environ`, s6,
    « inconnue »), `test_diagnostiquer_exige_root` ;
  - meta : `test_meta_garde_execution_*` (découverte qui lève, crochet absent, vraie découverte
    dans un processus neuf), `test_meta_reseau` (et par la route : jamais la valeur de
    `X-Forwarded-For`), `test_meta_lazy_packages`, `test_meta_commit_deploye`.
- **Depuis l'hôte** (`test_sans_shell_contrat.py`) :
  - `test_entree_refuse_hors_pid1` (`--init`), `test_passerelle_hors_s6_arretee_par_le_greffon`
    (passerelle et tableau de bord, code 78), `test_hooks_scripts_refus`,
    `test_hooks_scripts_root_et_refus`, `test_volume_railway_simule` ;
  - `test_api_server_http_refuse_les_outils_d_execution` (HTTP réel sur 127.0.0.1:8642),
    `test_agent_cron_refuse_terminal` (terminal absent ; pont `tool_call` refusé par la garde
    dans le processus cron), `test_worker_kanban_refuse_les_outils_d_execution` (trois cartes
    du propriétaire ; `kanban_create` avec skills, modèle, fournisseur et `workspace_path:
    /opt/data`, et `kanban_attach_url`, OFFERTS au worker, refusés par la garde : preuve du
    crochet dans le processus du worker ; aucune nouvelle carte ; aucune requête vers
    `attache.acp.test`) ;
  - **`test_preview_restart_par_api_ws` (BLOQUANT, non ignorable)** et son témoin négatif
    (managed scope altérée en root, tableau de bord relancé : terminal s'exécute) ;
  - `test_session_du_tableau_de_bord_sans_outil_d_execution`,
    `test_meta_garde_execution_dans_le_tableau_de_bord`, `test_aucune_installation_paresseuse`,
    `test_volume_piege_apres_relance` (relance par l'agent et redémarrage) ;
  - `test_maintenance_sleep_infinity[cmd_herite_garde|cmd_herite_retire]` : la Start Command
    `/bin/sh -c "exec sleep infinity"` tient avec ou sans `gateway run` hérité, `docker exec`
    donne un shell root, `diagnostiquer` lit `/proc/1/environ` depuis `env -i` sans faux refus.

Lancement local :

```sh
docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site \
  acp-hermes-tests:dev -m pytest -v /opt/acp-tests/image
ACP_IMAGE=acp-hermes:dev ACP_IMAGE_TESTS=acp-hermes-tests:dev python -m pytest -s -v hermes/tests/contrat
```

Sous Windows, préfixer `PYTHONUTF8=1` (sinon des `print` échouent en UnicodeEncodeError) et,
dans Git Bash, `MSYS_NO_PATHCONV=1`.

L'image de test diffère de l'image Railway par `/opt/acp-tests` (tests, outils, pytest)
et par l'autorité de test jetable dans `/etc/ssl/certs` ; les preuves qui n'en ont pas
besoin (refus, conteneur en marche, compatibilité, versions, maintenance) tournent sur
l'image Railway.

### Chaque protection principale, retirée, fait échouer ses tests (P2)

Comme en P1 pour le `PATH`, chaque protection principale a été retirée d'une copie de
`hermes/` (image reconstruite), puis ses tests rejoués sur cette image le 25/09/2026 :

| Protection retirée | Tests dans l'image | Tests de contrat |
|---|---|---|
| Garde d'exécution (crochet non enregistré) | 4 échecs sur 4 : pont `tool_call`, agent neuf, **preview.restart en stdio**, découverte | 4 échecs sur 5 : **preview.restart par `/api/ws`**, worker kanban, cron (`tool_call`), meta ; `cron[terminal]` reste vert (tenu par la couche 1) |
| Listes `disabled_toolsets` et `platform_toolsets` | 7 échecs sur 9 : surfaces (vide et hostile), tours api_server (terminal, fichiers, code, délégation) ; `cronjob_manage` et `browser_navigate` restent verts (navigateur toujours retiré, cron non offert) | 1 échec sur 1 : api_server HTTP (terminal offert) |
| Épingles du `.env` géré | 2 échecs sur 3 : `.env` neutralisé, surfaces sur volume hostile | — |
| `acp-entree` (ENTRYPOINT officiel) | — | 1 échec sur 1 : refus hors PID 1 |
| Sentinelle (non appelée par `register()`) | `test_register_appelle_la_sentinelle` échoue (1 sur 1) ; les 9 cas de la fonction elle-même restent verts | 2 échecs sur 2 : passerelle et tableau de bord hors s6 |
| `hooks/` et `scripts/` exigés vides | 2 échecs sur 2 | 2 échecs sur 2 |
| Volume Railway exigé | 3 échecs sur 3 | 1 échec sur 1 |
| `diagnostiquer` lisant l'environnement de la session | 1 échec sur 1 : source de l'environnement | 2 échecs sur 2 : maintenance (faux refus depuis `env -i`) |

Script de preuve : copie de `hermes/`, protection retirée, images reconstruites, sélection
`pytest -k` rejouée ; images supprimées ensuite.

## 9. Ce qui est prouvé, ce qui ne l'est pas

Les preuves datées de P1 (sorties, identifiants de runs) sont dans
[`docs/reprise-poste.md`](../reprise-poste.md), § P1.

Prouvé en P1 (local et CI) : version et condensat ; `CMD`, crochet et variables s6 de
l'image ; OpenRPC identique ; `hermes plugins compat` vert sur `acp-poste`, rouge sur un
témoin qui importe `hermes_cli.kanban_db.connect` ; refus code 1 en français, avant
l'amorçage de Hermes, pour chaque cas du § 4 et pour un fichier géré invalide, y compris
si `S6_BEHAVIOUR_IF_STAGE2_FAILS` a été changée ; `/proc/1/cmdline` = s6-svscan (lancé par
`/init`) ; passerelle et tableau de bord sous l'uid hermes ; api_server sur
127.0.0.1:8642 seulement ; `/api/auth/providers` = `self-hosted` seul ; meta 401 sans
session, 200 avec un jeton OIDC valide ; jetons d'une autre clé, d'une autre audience ou
d'un autre émetteur refusés ; injection **dans `/opt/data/config.yaml`** (basic, Nous,
émetteur et client OIDC, `trusted_proxies`, `platforms.api_server`) neutralisée après
relance du tableau de bord ET de la passerelle **par l'agent** et après redémarrage du
conteneur ; écritures de l'agent refusées dans la managed scope, les greffons, le thème, le
greffon groupé et `/etc/cont-init.d` ; **`/run/service` et les scripts des passerelles
repris par root** ; **aucun binaire déposé par l'agent dans `/opt/data/.local/bin` n'est
exécuté en root** (§ 4.5) ; **api_server ramené en `127.0.0.1:8642`** même clé retirée ;
**`HERMES_MANAGED_DIR` posée dans `/opt/data/.env` refuse la relance du tableau de bord et le
redémarrage du conteneur** ; `HERMES_BUNDLED_PLUGINS` et `HERMES_ENABLE_PROJECT_PLUGINS`
ramenées à leur valeur d'image ; `/v1/meta` signale une portée gérée détournée ;
`POST /api/hermes/update` refusé, `/opt/hermes` identique ; carte en triage du tableau
`poste` jamais lancée ; un tour d'agent complet sur le modèle factice ; démarrages
idempotents ; SOUL modifié gardé et signalé.

Prouvé en P2, en local le 25/09/2026 (preuves chiffrées en fin de section) :
- **aucune surface n'offre d'outil d'exécution** (api_server, CLI, cron, tableau de bord,
  worker kanban, enfant de délégation), sur volume vide et hostile ;
- **les vrais processus refusent** : api_server en HTTP (« does not exist » pour terminal,
  fichiers, code, cron, délégation, navigateur ; pont `tool_call` refusé par la garde),
  agent cron, **workers kanban** (garde présente dans leur processus : `kanban_create` et
  `kanban_attach_url` refusés avec leur message), tableau de bord après volume piégé, relance
  et redémarrage ;
- **`preview.restart` est fermé dans le processus réel**, par les deux tests bloquants
  (`tui_gateway.entry` en stdio ; `/api/ws` du vrai tableau de bord avec ticket), chacun avec
  son témoin négatif où terminal s'exécute vraiment ;
- l'`AIAgent` charge lui-même la garde (processus neuf, sans `discover_plugins` manuel) ; la
  découverte des greffons réussit sur l'image épinglée ; `/v1/meta` rapporte l'état de la
  garde dans le processus du tableau de bord ;
- refus hors PID 1 (`--init`), arrêt en code 78 de la passerelle et du tableau de bord lancés
  hors de s6, `hooks/` et `scripts/` exigés vides puis root, volume Railway exigé (variable et
  point de montage), `RAILWAY_RUN_UID`, treize nouvelles variables interdites, cinq valeurs
  imposées, quatorze nouvelles épingles, 40 clés et 38 variables ;
- aucune installation paresseuse (`uv pip install` absent des journaux, `lazy-packages` vide) ;
- maintenance `/bin/sh -c "exec sleep infinity"` avec et sans `CMD` hérité, shell root,
  `diagnostiquer` lisant `/proc/1/environ` depuis une session vide, sans rien écrire.

Non prouvé — et non garanti :
- **rien sur Railway** : PID 1 réel de la plateforme, Start Command et `CMD` hérité,
  environnement d'une session `railway ssh`, bord (`trusted_proxies`, en-têtes), volume réel
  (voir [railway.md](railway.md)) ;
- le tableau de bord **authentifié** reste un shell du propriétaire (§ 5) ; son filtrage
  (`/api/ws`, `/api/pty`…) relève de P4 ;
- les échecs ouverts autour du crochet (§ 10) ne sont couverts que par des tests de
  l'image épinglée et par l'alerte de `/v1/meta`, pas par un mécanisme qui les fermerait ;
- l'api_server accepte une politique d'exécution de « salon » (`room_execution_policy`,
  api_server.py:2238-2241) qui choisit ses propres jeux d'outils : seule la garde la couvre
  (non éprouvé par un test dédié) ;
- aucune connexion interactive complète par le navigateur dans ces tests : elle est prouvée,
  avec le vrai fournisseur Authelia derrière un bord TLS factice, par le test navigateur de P2
  ([identite.md](identite.md) § 7 et § 10) ;
- le crochet `S6_STAGE2_HOOK` n'est pas un point d'extension de Hermes mais de s6-overlay ;
  une montée de s6-overlay dans l'image officielle devra être revérifiée.

### Preuves de P2 (local)

Images construites depuis le worktree (`docker build -f hermes/image/Dockerfile hermes`, puis
l'image de test), Docker 29.5.3 sous Windows, le 25/09/2026 :

- dans l'image : `docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e
  PYTHONPATH=/opt/acp-tests/site <image de test> -m pytest -v -rA /opt/acp-tests/image` →
  **212 réussis, 0 échec, 0 ignoré** (P1 et P2) ;
- contrat depuis l'hôte : `PYTHONUTF8=1 ACP_IMAGE=… ACP_IMAGE_TESTS=… python -m pytest -s -v
  -rA hermes/tests/contrat` (pytest 9.1.1, hachés vérifiés) → **56 réussis, 0 échec, 0
  ignoré** en 9 min 49 s, dont les deux tests bloquants `preview.restart` ;
- protections retirées une à une : tableau du § 8 ;
- nettoyage : aucun conteneur, volume ni réseau `acp-contrat-*` restant.

### Preuves de P2 (CI)

Run `image.yml` [36087965990](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36087965990)
sur `refonte/hermes-p2` (commit `efbf7b0`, 25/09/2026, conclusion **success**) : condensat de
l'image officielle confirmé, **212 tests réussis dans l'image**, **56 tests de contrat
réussis** (dont les deux tests bloquants `preview.restart`), aucun échec, aucun ignoré. Run
`ci.yml` [36087965871](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36087965871)
du même commit : success.

## 10. Limites connues

- **Même uid 10000** pour la passerelle, les agents et le tableau de bord. Depuis P2, l'agent
  n'a plus d'outil d'exécution : tuer le tableau de bord ou écouter sur `0.0.0.0:9119` lui
  demanderait une **faille de Hermes lui-même** (analyse d'un document par `web_extract`,
  `vision_analyze`, skills, mémoire). Non testable sans exécuter l'attaque ; limite de fond.
- **Échecs ouverts autour de la garde** : la couche d'appel de Hermes échoue ouvert si le
  crochet lève (agent_runtime_helpers.py:2348-2361 ; tool_executor.py:652-667) — la garde ne
  lève jamais ; la **découverte des greffons** qui lève fait continuer l'agent sans greffon
  (agent_init.py:1066-1067) ; `HERMES_SAFE_MODE` (épinglée vide, interdite) saute la
  découverte, mais reste accessible au shell du propriétaire.
- **Rebinding DNS** pour tout outil qui téléchargerait sans le client sûr de Hermes :
  `kanban_attach_url` est retiré ; `vision_analyze` et le hub de skills utilisent le client
  sûr ; `web_extract` filtre par `async_is_safe_url` puis délègue à un fournisseur (supposé
  distant). Tout nouveau site d'appel HTTP direct fait échouer
  `test_recensement_http_des_outils_admis`.
- **`--accept-hooks` est fixe côté répartiteur** (kanban_db_dispatch.py:2686-2689) : les
  workers acceptent les `hooks:` de la configuration. L'agent ne peut plus l'écrire ; une
  sauvegarde restaurée le pourrait : `diagnostiquer` l'inventorie.
- **Chemins d'exécution pilotés par la configuration ou le volume** (`mcp_servers.*.command`,
  `hooks:`, quick_commands exec, TTS/STT « command », `lazy-packages`) : il faut écrire
  `/opt/data`, ce que l'agent ne peut plus faire ; `diagnostiquer` les inventorie (code 1).
- **Exfiltration par `web_extract`** (URL publique) après une injection ; **injection
  persistante** par les skills et la mémoire, soumises à la validation du propriétaire
  (`write_approval: true`).
- **Chemins root qui lisent le volume, sans audit exhaustif** : `stage2-hook.sh`
  (01-hermes-setup) et `02-reconcile-profiles` tournent en root sur un `/opt/data` que
  l'agent pouvait écrire ; sans outil d'exécution, l'agent ne peut plus y déposer de piège,
  mais une sauvegarde restaurée le pourrait (d'où `diagnostiquer` avant tout redémarrage).
- **Relance des services par l'agent** (`s6-svc -r`) : sans outil d'exécution, l'agent ne peut
  plus écrire dans la FIFO `supervise/control` ; la garde de relance (P1) reste en place.
- **Jeton invalide → 503.** Hermes range une signature, une audience ou un émetteur
  invalides en « fournisseur injoignable » (plugins/dashboard_auth/_shared.py:192-229) :
  le client desktop (P8) devra traiter 503 comme un refus.
- **Récupération d'un volume refusé** : procédure de maintenance (Start Command
  `/bin/sh -c "exec sleep infinity"`, `diagnostiquer`, correction, retour à la normale) et
  restauration de sauvegarde : [railway.md](railway.md) § 10. On ne désactive jamais une
  garde et on n'ajoute jamais de variable de contournement.
- **Hors de s6** : refusé (`acp-entree` hors PID 1 ; sentinelle du greffon pour `gateway
  run` et `dashboard` lancés par une autre entrée). Le PID 1 réel de Railway n'est pas
  documenté : le premier démarrage le tranchera, par un refus explicite s'il le faut.
- `/proc/1/cmdline` vaut `s6-svscan` et non `/init` : `/init` s'exécute en `s6-svscan`
  (s6-linux-init) ; c'est la preuve attendue que la chaîne s6 est en PID 1.
