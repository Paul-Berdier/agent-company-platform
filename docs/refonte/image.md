# Image Hermes d'ACP — étape P1

État du **24 septembre 2026**. Étape P1 du [plan de la refonte](plan.md) : image dérivée
de l'image officielle de Hermes Agent et CI de contrat, **en local et en CI, sans
Railway**. Rien n'est déployé ; le premier déploiement est l'étape P2.

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
| Greffon `acp-poste` (squelette) | `hermes/plugins/acp-poste/` | `/opt/hermes/plugins/acp-poste/` |
| Image de test, outils | `hermes/tests/` | jamais dans l'image Railway |
| Workflow | `.github/workflows/image.yml` | — |

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

L'`ENTRYPOINT` officiel (`docker/entrypoint-dispatch.sh`) est conservé : quand il est
PID 1, il lance `/init` de s6-overlay (entrypoint-dispatch.sh:17-19).

1. **Crochet `S6_STAGE2_HOOK` = `/opt/acp/bin/acp-gardes`**, en root, au tout début de
   l'étape 2, avant tout service et tout script cont-init (rc.init de s6-overlay 3.2.3.0,
   `/package/admin/s6-overlay/etc/s6-linux-init/skel/rc.init`). L'en-tête
   `#!/command/with-contenv sh` lui donne l'environnement du conteneur (même motif que
   `01-hermes-setup`, Dockerfile:402-405). Il :
   - refuse une variable interdite ou invalide (§ 4) ;
   - régénère `/etc/hermes/config.yaml` et `/etc/hermes/.env` (root, 0644, écriture
     atomique) puis les relit et vérifie chaque épingle ;
   - inspecte `/opt/data/plugins`, `/opt/data/dashboard-themes` et `/opt/data/acp`
     (noms réservés, liens symboliques) sans rien écrire.
   Un refus arrête le conteneur **avec le code 1** (`S6_BEHAVIOUR_IF_STAGE2_FAILS=2`) avant
   `01-hermes-setup` (qui consommerait `HERMES_AUTH_JSON_BOOTSTRAP`, `HERMES_UID`…) et
   avant `02-reconcile-profiles` (qui démarre la passerelle).
2. `01-hermes-setup`, `015-supervise-perms`, `02-reconcile-profiles` de l'image officielle.
3. **`/etc/cont-init.d/05-acp`** : refait les contrôles du crochet (défense en
   profondeur si `S6_STAGE2_HOOK` avait été retiré), vérifie que la managed scope
   installée correspond aux variables de ce démarrage, rend `/opt/data/plugins`,
   `/opt/data/dashboard-themes` et `/opt/data/acp` propriété de root (répertoires 0755,
   fichiers 0644, par descripteurs `O_NOFOLLOW`), dépose le thème et `SOUL.md`, écrit
   `/run/acp/etat-demarrage.json` (tmpfs, root 0644).
4. Services s6 : tableau de bord (`hermes dashboard --host 0.0.0.0 --port 9119`, uid
   hermes) et `main-hermes`.
5. `CMD ["gateway","run"]` : la passerelle (cron, répartiteur kanban, api_server) tourne
   supervisée par s6 sous l'uid hermes (website/docs/user-guide/docker.md:61-66).

Pourquoi un crochet plutôt que le seul `05-acp` du plan : mesuré dans l'image, un script
cont-init en échec **n'empêche pas les suivants de tourner** ; s6 n'arrête le conteneur
qu'à la fin de l'étape cont-init. Avec les gardes en `05-acp` (ou même en `00-`), une
`API_SERVER_KEY` interdite était déjà consommée par `stage2-hook.sh` et la passerelle
démarrée par `02-reconcile-profiles` avant l'arrêt. Le crochet arrête tout avant.

`S6_BEHAVIOUR_IF_STAGE2_FAILS` elle-même est contrôlée : si elle ne vaut pas `2`, les
scripts d'ACP arrêtent le conteneur eux-mêmes (`/run/s6/basedir/bin/halt`, code 1).

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
secret n'existe alors nulle part.

Fixées par l'image, refusées si Railway les change : `HERMES_HOME=/opt/data`,
`HERMES_WEB_DIST=/opt/hermes/hermes_cli/web_dist`, `HERMES_DASHBOARD=1`,
`HERMES_DASHBOARD_HOST=0.0.0.0`, `HERMES_DASHBOARD_PORT=9119`,
`S6_BEHAVIOUR_IF_STAGE2_FAILS=2`, `S6_STAGE2_HOOK=/opt/acp/bin/acp-gardes` ;
`API_SERVER_HOST` n'est admise qu'à `127.0.0.1`.

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

Le message de refus est en français, préfixé `[acp] REFUS :`, et nomme chaque variable
fautive (toutes les erreurs d'un démarrage sont listées d'un coup).

## 5. Managed scope `/etc/hermes`

Hermes l'applique en dernier, feuille par feuille, et `hermes config set` refuse toute
clé épinglée (managed_scope.py:125-147 ; config.py:3384-3391 ; env_loader.py:473 et
503-518). La seule garantie est la permission : root, 0755/0644, et l'agent tourne sous
l'uid 10000 sans sudo. Un fichier géré qui ne se lit pas serait **ignoré en silence**
(managed_scope.py:86-93) : `acp_demarrage.py` le relit avec le chargeur YAML de Hermes
(`utils.fast_safe_load`, utils.py:613-615) et refuse de démarrer si une épingle manque ou
diffère. Le modèle est aussi validé à la construction de l'image.

**`/etc/hermes/config.yaml`** (26 clés) : `kanban.auto_decompose: false`,
`kanban.dispatch_profiles: [default]`, `approvals.mode: manual` (et `cron_mode`,
`single_query_mode`, `unattended_mode` : `deny`), `plugins.enabled: []`,
`plugins.disabled: [dashboard_auth/basic, dashboard_auth/nous, dashboard_auth/drain]`,
`plugins.allow_deprecated_imports: false`, `auth.adopt_external_logins: false`,
`security.redact_secrets: true`, `display.language: fr`,
`agent.disabled_toolsets: [browser]`, `dashboard.theme: acp`,
`dashboard.trusted_proxies: []`, `dashboard.public_url` et
`dashboard.oauth.self_hosted.{issuer, client_id, scopes}` (valeurs Railway validées),
`dashboard.oauth.self_hosted.client_secret: ""`, `dashboard.oauth.{client_id,
portal_url}: ""`, `dashboard.basic_auth.{username, password, password_hash, secret}: ""`.
Aucun secret : une clé dont le nom évoque un secret et qui porte une valeur est refusée.

**`/etc/hermes/.env`** (26 variables) : les quatre variables OIDC et l'URL publique
validées, `API_SERVER_HOST=127.0.0.1`, `API_SERVER_PORT=8642`, `HERMES_LANGUAGE=fr`,
`SSL_CERT_FILE` et `REQUESTS_CA_BUNDLE`/`CURL_CA_BUNDLE` sur
`/etc/ssl/certs/ca-certificates.crt`, `SSL_CERT_DIR=/etc/ssl/certs`, et des valeurs
**vides** pour Nous, basic, drain, les mandataires et, en client public,
`HERMES_DASHBOARD_OIDC_CLIENT_SECRET`.

Les autorités de certification sont épinglées **sur le magasin du système, jamais à
vide** : constaté dans l'image, `SSL_CERT_FILE=` vide prive OpenSSL de toute autorité et la
récupération du JWKS par PyJWT (urllib) échoue ; plus personne ne pourrait se connecter.
Épinglées, elles empêchent aussi un agent de faire valider par le tableau de bord un
fournisseur d'identité usurpé (autorité et mandataire posés dans `/opt/data/.env`).

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
- **Migration** : aucune (décision du propriétaire : rien n'est déployé, P2 part d'un
  volume neuf). La reprise de propriété unique du plan (`chown -R`) n'est pas écrite.

## 7. Greffon `acp-poste` (squelette)

- `plugin.yaml` : `kind: backend`, `requires_hermes: ">=0.21.5"`, version `0.11.0`
  (vérifiée par `scripts/check_version.py`).
- `register(ctx)` n'enregistre **rien** en P1 : ni outil `poste_*`, ni fournisseur de
  jeton machine, ni route à jeton (écart au plan, qui citait le fournisseur de jeton en P1 ;
  sans enrôlement ni route, il aurait été inerte). Ils arrivent en P5.
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

Lancement local :

```sh
docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site \
  acp-hermes-tests:dev -m pytest -v /opt/acp-tests/image
ACP_IMAGE=acp-hermes:dev ACP_IMAGE_TESTS=acp-hermes-tests:dev python -m pytest -s -v hermes/tests/contrat
```

L'image de test diffère de l'image Railway par `/opt/acp-tests` (tests, outils, pytest)
et par l'autorité de test jetable dans `/etc/ssl/certs` ; les preuves qui n'en ont pas
besoin (refus, conteneur en marche, compatibilité, versions) tournent sur l'image Railway.

## 9. Ce qui est prouvé, ce qui ne l'est pas

Les preuves datées (sorties, identifiants de runs) sont dans
[`docs/reprise-poste.md`](../reprise-poste.md), § P1.

Prouvé en P1 (local et CI) : version et condensat ; `CMD`, crochet et variables s6 de
l'image ; OpenRPC identique ; `hermes plugins compat` vert sur `acp-poste`, rouge sur un
témoin qui importe `hermes_cli.kanban_db.connect` ; refus code 1 en français, avant
l'amorçage de Hermes, pour chaque cas du § 4 et pour un fichier géré invalide, y compris
si `S6_BEHAVIOUR_IF_STAGE2_FAILS` a été changée ; `/proc/1/cmdline` = s6-svscan (lancé par
`/init`) ; passerelle et tableau de bord sous l'uid hermes ; api_server sur
127.0.0.1:8642 seulement ; `/api/auth/providers` = `self-hosted` seul ; meta 401 sans
session, 200 avec un jeton OIDC valide ; jetons d'une autre clé, d'une autre audience ou
d'un autre émetteur refusés ; injection dans `/opt/data/config.yaml` et `/opt/data/.env`
neutralisée après relance du tableau de bord **par l'agent** et après redémarrage du
conteneur (fournisseur, émetteur, identifiant client, redirection de connexion) ;
écritures de l'agent refusées dans la managed scope, les greffons, le thème, le greffon
groupé et `/etc/cont-init.d` ; `POST /api/hermes/update` refusé, `/opt/hermes` identique ;
carte en triage du tableau `poste` intacte après plus de quatre ticks du répartiteur,
sans aucun appel au modèle ; un tour d'agent complet sur le modèle factice ; deux
démarrages successifs donnent une managed scope, un thème et un SOUL identiques ; SOUL
modifié gardé et signalé.

Non prouvé en P1 :
- rien sur Railway : PID 1 sur la plateforme, proxy, `trusted_proxies`, variables réelles
  (P2) ;
- aucune connexion interactive complète par le navigateur (le faux fournisseur n'a pas de
  page d'autorisation ni d'échange de code) : seul le chemin « jeton porteur » est éprouvé ;
  le **refus d'un second compte** relève du fournisseur d'identité choisi en P2, Hermes ne
  tenant aucune liste blanche (self_hosted/__init__.py:258-280) ;
- le crochet `S6_STAGE2_HOOK` n'est pas un point d'extension de Hermes mais de s6-overlay ;
  une montée de s6-overlay dans l'image officielle devra être revérifiée ;
- aucun test Playwright (P3-P4) ; le thème `acp` est provisoire (P3).

## 10. Limites connues

- **Remplacement d'un répertoire root.** `/opt/data` appartient à l'agent : il peut
  renommer `/opt/data/plugins` ou `/opt/data/dashboard-themes` et en recréer un à lui. Le
  crochet et `05-acp` le détectent au démarrage suivant (nom réservé, lien) et reprennent
  la propriété ; entre-temps, `plugins.enabled: []` empêche tout greffon utilisateur d'être
  importé, mais un thème substitué serait servi (Hermes relit les thèmes à chaque requête,
  web_server_dashboard.py:414-432). Une sentinelle root continue n'est pas écrite.
- **Relance du tableau de bord par l'agent** (`s6-svc -r`) : sans `05-acp` ; seule la
  managed scope protège alors, ce qu'éprouvent les tests.
- **Jeton invalide → 503.** Hermes range une signature, une audience ou un émetteur
  invalides en « fournisseur injoignable » (plugins/dashboard_auth/_shared.py:192-229) :
  le client desktop (P8) devra traiter 503 comme un refus.
- **Récupération.** Un refus au démarrage empêche le conteneur de tourner ; sur Railway,
  on ne peut pas y entrer pour nettoyer le volume. La procédure (volume monté par un
  service de maintenance) est à écrire en P2.
- **Hors de s6** (plateforme qui ne donne pas le PID 1) : ni crochet ni `05-acp` ; seule
  la managed scope de base posée à la construction s'applique (valeurs OIDC vides : aucun
  fournisseur, le tableau de bord refuse de se lier hors du bouclage local ; il ne
  démarre d'ailleurs pas sans s6). À vérifier sur Railway en P2.
- `/proc/1/cmdline` vaut `s6-svscan` et non `/init` : `/init` s'exécute en `s6-svscan`
  (s6-linux-init) ; c'est la preuve attendue que la chaîne s6 est en PID 1.
