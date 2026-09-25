# Fournisseur d'identité d'ACP (Authelia) — étape P2

État du **25 septembre 2026**. Étape P2 du [plan de la refonte](plan.md) : le tableau de bord de
Hermes est protégé par un fournisseur OIDC **auto-hébergé**, le service Railway `identite`
(Authelia 4.39.28, décision du propriétaire du 25 septembre 2026 ; Pocket ID écarté), avec **un
seul utilisateur** et **un seul client**, `hermes-acp`. Tout ce document est prouvé **en local**
(Docker 29.5.3, poste Windows) ; les exécutions de CI sont consignées au § 13. Rien n'est déployé.
Le déploiement, l'exploitation
et la récupération sont décrits dans [railway.md](railway.md) ; l'image Hermes dans
[image.md](image.md).

Conventions : **mesuré** (observé sur un conteneur ou un navigateur réels), **vérifié** (lu dans
la source ou la documentation citée), **supposé** (à prouver sur Railway). Les références
`fichier:ligne` sans autre précision désignent le source d'Authelia à l'étiquette `v4.39.28`
(commit `8da42b2`).

## 1. En bref

| Élément | Emplacement dans le dépôt | Dans l'image |
|---|---|---|
| Dockerfile dérivé | `identite/Dockerfile` | — |
| Configuration (gabarit, sans secret) | `identite/configuration.yml` | `/etc/authelia/configuration.yml` (root, 0644) |
| Garde root (ENTRYPOINT) | `identite/acp-identite-entree` | `/opt/acp-identite/acp-identite-entree` |
| Administration en maintenance | `identite/acp-identite-admin` | `/opt/acp-identite/acp-identite-admin` |
| Tests de contrat | `hermes/tests/contrat/test_identite.py`, `pile_identite.py` | — |
| Bord TLS factice, client de test | `hermes/tests/outils/bord_factice.py`, `client_identite.py` | image de TEST seulement |
| Test navigateur | `hermes/tests/e2e/test_connexion_navigateur.py` | — |

```sh
docker build -t acp-identite:dev identite
```

Parcours de connexion (mesuré de bout en bout, §7) :

1. `https://<hermes>/` → Hermes renvoie vers `https://<identite>/api/oidc/authorization`
   (code + PKCE S256, client public, portées `openid profile email offline_access`) ;
2. portail Authelia : mot de passe, puis **passkey** (WebAuthn, vérification de l'utilisateur
   exigée) ; consentement explicite ;
3. retour `https://<hermes>/auth/callback?code=…` ; Hermes échange le code, vérifie l'`id_token`
   (RS256, `iss` et `aud` épinglés) et ouvre sa session (cookies `hermes_session_*`).

## 2. Image

- **Base** : `docker.io/authelia/authelia:4.39.28@sha256:bd97cff4fcbf715b5ff1f9ae286afbe6033afce385302520b0368122d43a6f54`,
  condensat de l'**index** revérifié le 25/09/2026 par `docker buildx imagetools inspect`
  (manifeste linux/amd64 `sha256:a9931f44…2178`). La CI relève ce condensat à chaque exécution
  et refuse s'il a changé (étape « Relever le condensat de l'image Authelia » d'`image.yml`) ; un
  test vérifie que les couches de notre image commencent exactement par celles de la base.
- **ENV fixes**, revérifiées par la garde : `X_AUTHELIA_CONFIG=/etc/authelia/configuration.yml`,
  `X_AUTHELIA_CONFIG_FILTERS=template`, `PUID=1000`, `PGID=1000` (l'image amont vaut 0:0 :
  Authelia tournerait en root).
- **Aucun CMD** ; l'ENTRYPOINT est la garde, qui refuse tout argument.
- **HEALTHCHECK Docker retiré** (`HEALTHCHECK NONE`, `/app/.healthcheck.env` supprimé,
  `server.disable_healthcheck: true`). L'image amont livre ce fichier en 0666 ; Authelia (uid
  1000) le réécrit (`internal/middlewares/startup.go:133-150`) et `/app/healthcheck.sh` le
  **source en root** : une voie d'élévation de l'uid 1000 vers root sous Docker. La santé
  Railway est une requête HTTP sur `/api/health` (rw_full.txt:29918).
- **Aucun secret** dans l'image ni dans Git : vérifié par test (fichiers, variables, gabarit).

## 3. Démarrage : garde root `acp-identite-entree`

Exécutée en root à chaque démarrage, avant Authelia. **Échec fermé** : toute anomalie est
refusée en français (`[acp-identite] REFUS : …`), les erreurs de variables sont **toutes**
rassemblées, puis `[acp-identite] Démarrage arrêté (échec fermé).` et code 1. L'empreinte du mot
de passe n'est jamais affichée.

1. root exigé ; **aucun argument** admis.
2. **Variables** :

   | Variable | Règle |
   |---|---|
   | `ACP_IDP_DOMAINE` | nom d'hôte public en minuscules, sans schéma ni port ; refusé s'il porte encore la valeur de gabarit (`<libellé-identite>…`), s'il finit par `.railway.internal` ou `.localhost` |
   | `ACP_HERMES_URL` | `https://<hôte public>`, sans port, chemin ni barre finale ; gabarit, domaine privé et hôte identique à `ACP_IDP_DOMAINE` refusés |
   | `ACP_IDP_UTILISATEUR` | `^[a-z][a-z0-9._-]{0,31}$` |
   | `ACP_IDP_NOM` | 1 à 64 caractères, sans guillemet double, barre oblique inverse, saut de ligne ni caractère de contrôle |
   | `ACP_IDP_EMAIL` | adresse électronique |
   | `ACP_IDP_MOT_DE_PASSE_ARGON2` (**scellée**) | `$argon2id$v=19$m=…,t=…,p=…$sel$empreinte`, avec **19456 ≤ m ≤ 65536** Kio (plancher OWASP ; plafond = valeur pour laquelle la mémoire a été mesurée, §8), t ≤ 10, p ≤ 16 |
   | toute `AUTHELIA_*` | **interdite** (surchargerait la configuration figée) |
   | `X_AUTHELIA_*` | seules les deux valeurs de l'image |
   | `PUID`, `PGID` | 1000 exactement |
   | `UMASK` | **interdite** (l'entrée amont l'appliquerait aux secrets) |
   | `RAILWAY_RUN_UID` | absente ou `0` |

3. **Sur Railway** (une des variables `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_DEPLOYMENT_ID`,
   `RAILWAY_SERVICE_ID` présente) : `RAILWAY_VOLUME_MOUNT_PATH=/config` **et** `/config` point de
   montage réel (5e champ de `/proc/self/mountinfo`).
4. **`/config`** : vrai répertoire, **sans lien symbolique ni fichier spécial**. L'entrée amont
   fait `chown -R` en root (`entrypoint.sh:14`), et le `chown` de busybox suit les liens : un lien
   posé par un processus Authelia compromis donnerait un fichier système à l'uid 1000.
5. **Secrets** (§5), générés s'ils sont absents.
6. **Utilisateur unique** (§6).
7. Journal : `[acp-identite] variables validées ; utilisateur unique configuré (identifiant non
   journalisé) ; émetteur https://… ; client hermes-acp → https://…/auth/callback`, puis la liste des
   secrets générés et conservés. Depuis la relecture P2, l'identifiant n'est plus écrit : ces
   journaux sont versés au dépôt, qui est public, et un tiers qui connaît l'identifiant peut bannir
   le propriétaire (régulation, § 4 ; [railway.md](railway.md) § 7).
8. `ACP_IDP_MOT_DE_PASSE_ARGON2`, `ACP_IDP_NOM` et `ACP_IDP_EMAIL` sont retirées de
   l'environnement, puis `exec /app/entrypoint.sh` : `chown -R 1000:1000 /config`,
   `su-exec 1000:1000 authelia`. Authelia est le PID 1, sous l'uid 1000, `umask 077` (fichiers du
   volume en 0600, mesuré).

## 4. Configuration (`identite/configuration.yml`)

Gabarit rendu par Authelia (`X_AUTHELIA_CONFIG_FILTERS=template`) : secrets lus par
`{{ secret "/config/secrets/…" }}`, variables par `mustEnv` (une variable absente fait échouer le
rendu). Validé par `authelia config validate` dans les tests (un seul avertissement, attendu :
`access_control` sans règle, car aucun proxy n'utilise l'autorisation par relais).

- Premier facteur par fichier (`/run/acp-identite/utilisateurs.yml`, `watch: false`), aucune
  réinitialisation ni changement de mot de passe ; TOTP désactivé ; WebAuthn avec vérification de
  l'utilisateur exigée, connexion par passkey seule désactivée.
- Session Authelia : 15 minutes d'inactivité, 1 heure au plus ; cookie limité à `ACP_IDP_DOMAINE`.
- Régulation : 5 échecs en 10 minutes bannissent l'identifiant 15 minutes.
- Notifications dans `/config/notification.txt` (code à usage unique de l'enrôlement).
- OIDC : clé RS256 `acp-rs256-1` ; PKCE `always`, `plain` interdit ; politique `proprietaire`
  **deny par défaut**, une seule règle `two_factor` pour `user:<ACP_IDP_UTILISATEUR>` ; durées :
  code 1 minute, `id_token` et jeton d'accès 1 heure, **jeton de rafraîchissement 7 jours**
  (décision du propriétaire) ; `id_token` porteur de `email`, `name`, `preferred_username`.
- Client unique `hermes-acp` : public (`token_endpoint_auth_method: none`), retour unique
  `<ACP_HERMES_URL>/auth/callback`, réponse `query`, octrois `authorization_code` et
  `refresh_token`.

**Écarts au plan, justifiés :**
- `server.disable_healthcheck: true` ajouté (§2).
- `consent_mode: 'pre-configured'` reste écrit, mais **ne joue pas** : Authelia impose un
  consentement **explicite** à toute demande qui porte `offline_access`
  (`internal/oidc/util.go:646-669` ; constaté dans le navigateur). Le propriétaire clique donc
  « Accepter » à chaque connexion complète ; les rafraîchissements, eux, sont silencieux.

## 5. Secrets et clé de signature

Générés **dans le conteneur**, au premier démarrage, s'ils sont absents :
`authelia crypto rand --length 64 --charset alphanumeric` pour `session`, `stockage`,
`jwt-reinitialisation`, `oidc-hmac` ; `authelia crypto pair rsa generate --bits 4096` pour
`oidc-rs256.pem`. Écriture dans un fichier temporaire puis renommage atomique ; répertoire
`/config/secrets` en 0700, fichiers en 0600, uid 1000 (mesuré).

- **Conservés** tels quels aux démarrages suivants (mesuré : empreintes SHA-256 et JWKS
  identiques après redémarrage).
- **Jamais régénérés en silence** : un secret vide, une clé qui n'est pas une clé privée PEM, ou la
  clé `stockage` absente alors que `/config/db.sqlite3` existe (une nouvelle clé rendrait la base
  illisible) : refus.
- Jamais dans Git ni dans une variable. Les **sauvegardes du volume les contiennent** : la
  frontière de confiance est le compte Railway.

## 6. Un seul utilisateur

- Écrit à **chaque démarrage** par la garde dans `/run/acp-identite/utilisateurs.yml` (hors
  volume, `root:1000` 0640, répertoire `root:1000` 0750, écriture atomique) depuis les variables
  `ACP_IDP_*`. L'uid 1000 (Authelia) ne peut ni le modifier ni créer de fichier à côté (mesuré).
- Un second compte glissé dans ce fichier (en root) **disparaît au redémarrage** (mesuré).
- Ni inscription, ni interface d'administration, ni assistant : rien qu'un premier visiteur
  puisse « réclamer ».
- **Défense en profondeur** : Hermes n'a aucune liste blanche de sujets
  (`plugins/dashboard_auth/self_hosted/__init__.py` de Hermes). Une variante de TEST qui
  contourne la garde pour poser un second compte prouve que la politique du client refuse tout
  autre sujet après son premier facteur (`error=access_denied` vers le retour de Hermes, aucun
  code), alors que le propriétaire est renvoyé vers son second facteur.

## 7. Compatibilité avec Hermes (mesurée à travers le bord factice)

Pile de test (`pile_identite.py`) : `identite` (alias privé `identite-interne`), Hermes (image de
test, alias `hermes-interne`) et le **bord factice**, qui porte les noms publics
`hermes-acp.test` et `identite-acp.test`. Ces deux noms ont des **domaines enregistrables
distincts**, comme deux sous-domaines de `up.railway.app` (suffixe public) : le navigateur les
traite en sites différents, comme sur Railway.

| Point | Résultat |
|---|---|
| Découverte par Hermes (`{issuer}/.well-known/openid-configuration`, contrôle d'origine, émetteur épinglé, https) | **acceptée** ; émetteur `https://identite-acp.test` ; S256 seul annoncé ; `none` admis au jeton |
| URL d'autorisation construite par Hermes | acceptée par Authelia (renvoi vers le portail) |
| `redirect_uri` altérée (autre hôte, http, remontée `..`, requête ajoutée, barre finale, sous-domaine) | **refusée** par Authelia (`invalid_request` sur sa propre page, jamais de redirection vers l'URI altérée) ; client inconnu : `invalid_client` |
| PKCE `plain` ou absent, session ouverte chez Authelia | **refusé** (`invalid_request`, aucun code) |
| Connexion complète (mot de passe, passkey, consentement) | session Hermes ouverte ; `amr` contient `mfa` ; compteur de la passkey incrémenté |
| **Rafraîchissement** (cookie du jeton d'accès retiré) | **`id_token` réémis** par Authelia, page servie en 200, jeton de rafraîchissement **tourné** : le point « à prouver avant Railway » du plan est prouvé en local |
| Déconnexion | Hermes **révoque** le jeton de rafraîchissement (`POST /api/oidc/revocation` → 200) ; réinjecté, il n'ouvre plus aucune session |
| Autre identifiant au portail | refusé (« Nom d'utilisateur ou mot de passe incorrect »), aucune session Hermes |

**Ce que voient les services derrière le bord (mesuré) :**
- **Authelia** croit `X-Forwarded-Proto` et `X-Forwarded-Host` de **tout** pair direct
  (`internal/middlewares/authelia_context.go:136-165, 584-616`), mais n'accepte que le domaine
  de son cookie : `X-Forwarded-Host: intrus.test` → 400. Sur Railway, seul le bord et les
  services du projet (réseau privé) l'atteignent.
- **Hermes** (`dashboard.trusted_proxies: []`) ne croit pas le bord : il voit la requête en
  **http**, le pair est l'adresse du bord, `X-Forwarded-Proto/Host`, `X-Real-IP` et
  `X-Railway-Edge` arrivent, `X-Forwarded-For` non. Conséquence mesurée : ses cookies de session
  sont **sans attribut `Secure`** (nom sans préfixe `__Host-`, `SameSite=Lax`) ; la méta le
  signale en alerte. L'URL de retour vient de `HERMES_DASHBOARD_PUBLIC_URL`, pas des en-têtes.
  Le cookie PKCE `Lax` survit au retour en `query` (GET de premier niveau), comme prévu.
- Le cookie de session d'Authelia est `Secure`, `HttpOnly`, `SameSite=Lax`.

**Bord factice** (`hermes/tests/outils/bord_factice.py`). Imite ce que documente Railway
(rw_full.txt:33403) : terminaison TLS, relais HTTP avec le `Host` d'origine,
`X-Forwarded-Proto: https`, `X-Forwarded-Host`, `X-Real-IP`, `X-Railway-Edge`,
`X-Request-Start`, `X-Railway-Request-Id`, hôte inconnu → 404, WebSocket relayé. **Supposé**
(non documenté) : les en-têtes `X-Forwarded-*`, `X-Real-IP`, `Forwarded` et `X-Railway-*`
envoyés par le client sont retirés avant d'être reposés ; aucun `X-Forwarded-For`. Seul un essai
sur Railway tranchera (`railway.md`).

## 8. Mémoire sous premiers facteurs simultanés (correction R2-6)

`/api/firstfactor` est public et chaque vérification argon2id alloue `m` Kio (64 Mio avec les
paramètres par défaut). Le bannissement est vérifié **avant** le hachage et un identifiant
inconnu n'est jamais haché (`internal/handlers/handler_firstfactor_password.go:44-70`) : seul
l'identifiant du propriétaire coûte de la mémoire, mais des demandes **simultanées** passent
toutes avant que le bannissement ne tombe.

Mesure (`test_memoire_premier_facteur_concurrent`) : conteneur neuf limité à **0,5 vCPU** comme
sur Railway, sans limite mémoire ; rafale simultanée à travers le bord, identifiant du
propriétaire, mauvais mot de passe ; relevés du noyau (pas d'échantillonnage) : `VmHWM` du PID 1
(RSS maximal d'Authelia) et `memory.peak` du cgroup (ce que compare le tueur OOM).

| Rafale | RSS maximal (VmHWM) | Pic du cgroup | Réponse la plus lente |
|---|---|---|---|
| 10 simultanés | 0,726 Gio | 0,689 à 0,690 Gio | 8 à 12 s |
| 20 simultanés | **1,346 à 1,348 Gio** | 1,311 à 1,313 Gio | 14 à 16 s |
| 20 simultanés, **témoin sous 1 Gio** sans échange (jusqu'à 3 essais) | — | — | Authelia **tué** (OOM, code 137), le bord rend 502 |

Relevés du 25/09/2026 sur le poste Windows (Docker Desktop), trois exécutions concordantes ; au
repos, Authelia occupe ~0,1 Gio. Pente mesurée : ~64 Mio par vérification simultanée.

Le témoin n'est **pas déterministe** : le pic dépend de l'entrelacement des vérifications sur
0,5 vCPU. Tué à chaque exécution sur le poste et dans les runs de P2, il a **survécu** une fois sur la
CI (`image.yml` 36118860946, étape P3 : état « true false 0 », réponses 401). Depuis, le test fait
jusqu'à **trois essais**, chacun sur un conteneur neuf, rapporte chacun et exige au moins une mort
(OOM) : 1 Go ne tient donc pas **toujours**, et cela suffit à l'écarter.

Une rafale n'est pas toujours simultanée : sur la CI (`image.yml` 36134351025, seconde partie de P3),
la rafale de 20 n'a culminé qu'à **0,538 Gio**, soit ~7 vérifications de 64 Mio au-dessus du repos
(celle de 10 : 0,725 Gio). Les vérifications s'y sont succédé, ou la régulation a banni le compte
après 5 échecs avant que les autres ne soient hachées : ce pic ne mesure pas 20 premiers facteurs
simultanés. Le commit `ec43987` avait remplacé l'exigence « pic à 20 > pic à 10 » par « chaque
rafale consomme de la mémoire », qu'une seule vérification satisfait : le critère de la limite
pouvait alors passer sans rien mesurer à 20 (relecture de P3). Depuis, une rafale de n ne compte que
si le `VmHWM` d'Authelia a monté d'au moins **les trois quarts de n × 64 Mio**
(`rafale_simultanee`) ; sinon elle est refaite sur un conteneur neuf, jusqu'à **trois essais**, tous
rapportés, et aucun essai simultané fait **échouer** le test (mesure non établie). Le test
`test_critere_de_simultaneite_…` vérifie ce critère sur les relevés réels : il refuse la rafale de
36134351025 et accepte celles du poste (10,0 et 20,1 × 64 Mio le 25/09/2026). L'ordre des deux pics
n'est pas exigé ; le **plus haut** des deux doit rester sous les deux tiers de la limite retenue.

**Limite retenue pour `railway.ts` (service identite) : 2,5 Gio** (`limitOverride.containers.memoryBytes
= 2684354560`). Critère du plan : le pic à 20 doit rester sous les deux tiers de la limite ; il en
vaut 53,9 %. La limite de 1 Go envisagée au départ ne tient pas (témoin mesuré ci-dessus ; par
calcul, ~0,1 Gio + n × 64 Mio l'atteint dès ~14 vérifications simultanées) ; 2 Gio ne tient pas
le critère des deux tiers (1,333 Gio < 1,346 Gio). Le test échoue si la mesure dépasse ce seuil.
Coût : seul l'usage réel est facturé (rw_full.txt:4885) ; au pire théorique aux limites, identite
passe de 20 $ (1 Go) à 2,5 × 10 + 0,5 × 20 = **35 $/mois** ; le plafond dur de 30 $ du compte
coupe tout avant d'atteindre ce pire cas. La limite par service de l'offre Hobby est 8 Go
(rw_full.txt:30848).

**Risque résiduel, dit :** la taille d'une rafale n'est pas bornée. Au-delà d'environ 37
vérifications simultanées, le service est tué (OOM) **avant** d'avoir enregistré les échecs :
aucun bannissement ne tombe, et l'attaque peut se répéter jusqu'à épuiser les 100 relances
(`ON_FAILURE`). Parades : `railway waf under-attack` en dernier recours (**supposé** : pourrait
bloquer les appels de Hermes vers l'IdP) ; une empreinte à `m` plus faible (≥ 19456 Kio,
admise par la garde) réduit la mémoire en proportion.

## 9. Maintenance et administration

Start Command de maintenance **`/bin/sh -c "exec sleep infinity"`** (jamais `sleep infinity`
nu) : elle remplace l'ENTRYPOINT, la garde ne tourne pas, d'éventuels arguments en trop
deviennent `$0` et `$1` du shell (mesuré avec et sans). Puis, dans la session root
(`railway ssh -i <clé dédiée> --service identite`, voir `railway.md`) :

```sh
/opt/acp-identite/acp-identite-admin user webauthn list <utilisateur>
/opt/acp-identite/acp-identite-admin user webauthn delete <utilisateur> --all
/opt/acp-identite/acp-identite-admin bans user list
/opt/acp-identite/acp-identite-admin bans user revoke <utilisateur>
```

- Seules les sous-commandes `authelia storage user …` et `authelia storage bans …` sont admises
  (le préfixe `storage` est toléré). `bans` s'ajoute au plan (`user` seul) : c'est la voie pour
  lever le bannissement du propriétaire après une attaque (§8). Migration, rotation de la clé de
  chiffrement et cache sont refusés en français.
- L'environnement de la **session** n'est jamais utilisé : les trois variables ACP du gabarit
  sont relues dans `/proc/1/environ` (PID 1 de maintenance, posé par Railway), les deux
  `X_AUTHELIA_*` sont les constantes de l'image (le PID 1 doit porter les mêmes), puis
  `env -i … su-exec 1000:1000 /app/authelia storage "$@"`. Mesuré depuis une session `env -i`.
- **Hors maintenance, le script refuse** : le PID 1 est alors Authelia sous l'uid 1000 et le noyau
  refuse la lecture de son environnement à root sans `CAP_SYS_PTRACE` (mesuré).
- La syntaxe des sous-commandes est celle d'Authelia 4.39.28 (`internal/commands/storage.go`) :
  `webauthn list [username]`, `webauthn delete [username] --all|--kid|--description`.

Secours (détail dans `railway.md`) : mot de passe perdu → nouvelle empreinte scellée puis
redéploiement ; passkeys perdues → maintenance, `acp-identite-admin user webauthn delete …`,
retour, nouvel enrôlement ; volume perdu → nouveau volume, secrets régénérés, nouvel enrôlement.

## 10. Tests

**Contrat** (`hermes/tests/contrat/test_identite.py`, depuis l'hôte, images réellement
construites ; tout ce qui est créé porte le préfixe `acp-contrat-` et est supprimé) :

```sh
PYTHONUTF8=1 ACP_IMAGE=acp-hermes:ci ACP_IMAGE_TESTS=acp-hermes-tests:ci ACP_IMAGE_IDENTITE=acp-identite:ci \
    python -m pytest -s -v -rA hermes/tests/contrat/test_identite.py
```

| Test | Prouve |
|---|---|
| `test_image_identite_epinglee_sans_secret` | FROM épinglé, couches de la base en préfixe, ENV exactes, ENTRYPOINT, aucun CMD, HEALTHCHECK retiré, fichiers root, ni `/config` ni clé dans l'image, configuration identique au dépôt, `authelia --version` |
| `test_gabarit_sans_secret_et_client_unique` | aucun secret en clair, un seul client public, PKCE S256, `query`, politique deny, un seul retour, 7 jours |
| `test_refus_identite_en_francais[27 cas]` | chaque refus de la garde (§3), en français, erreurs rassemblées, empreinte jamais affichée, Authelia jamais lancé |
| `test_demarrage_nominal_et_config_valide` | démarrage « comme sur Railway », PID 1 = Authelia uid 1000, empreinte absente de son environnement, `authelia config validate`, fichiers en 0600 |
| `test_secrets_generes_une_fois` | 5 secrets 0600 uid 1000, clé RSA 4096 `acp-rs256-1`, conservés au redémarrage |
| `test_un_seul_utilisateur` | fichier hors volume `root:1000` 0640, non modifiable par Authelia, second compte effacé au redémarrage, premier facteur d'un autre identifiant refusé |
| `test_sujet_autre_refuse_par_la_politique_oidc` | politique du client (§6) |
| `test_maintenance_sleep_infinity_identite[2 cas]` | maintenance et `acp-identite-admin` depuis une session sans environnement, sous-commandes interdites refusées |
| `test_admin_refuse_hors_maintenance` | refus hors maintenance |
| `test_decouverte_acceptee_par_hermes` | découverte acceptée par le vrai Hermes à travers le bord (§7) |
| `test_redirect_uri_alteree_refusee` | six altérations et un client inconnu refusés |
| `test_entetes_du_bord_mesures` | en-têtes vus par Authelia et Hermes, en-têtes falsifiés retirés par le bord, hôte inconnu 404 |
| `test_memoire_premier_facteur_concurrent` | §8, avec le témoin tué sous 1 Gio |

**Navigateur** (`hermes/tests/e2e/test_connexion_navigateur.py`) : Chromium de Playwright
(1.62.0, révision 1234, hachés vérifiés par `hermes/tests/requirements-e2e.txt`), authentificateur
WebAuthn **virtuel** (CDP), parcours du §7. Chromium joint les deux noms par
`--host-resolver-rules` vers le bord publié sur 127.0.0.1 et ne fait confiance qu'au certificat du
bord (`--ignore-certificate-errors-spki-list`) : aucune modification du système. En CI,
`ACP_E2E_OBLIGATOIRE=1` : l'absence de Playwright ou de Chromium est un **échec**, jamais un test
ignoré ; en local, le test n'est lancé que si un Chromium de Playwright est déjà présent (rien
n'est téléchargé).

```sh
python -m pip install --require-hashes --no-deps -r hermes/tests/requirements-e2e.txt
PYTHONUTF8=1 ACP_IMAGE_TESTS=acp-hermes-tests:ci ACP_IMAGE_IDENTITE=acp-identite:ci \
    python -m pytest -s -v -rA hermes/tests/e2e
```

Verrou : `uv pip compile hermes/tests/requirements-e2e.in --universal --python-version 3.12
--generate-hashes --no-header --output-file hermes/tests/requirements-e2e.txt`.

## 11. Ce qui ne se prouve que sur Railway

- Le comportement réel du bord : en-têtes posés, **retrait ou non** d'un `X-Forwarded-Host`
  falsifié par le client, présence d'un `X-Forwarded-For` ; l'émetteur d'Authelia à travers le
  vrai bord ; la plage d'adresses du bord (pour `trusted_proxies`, donc le `Secure` des cookies).
- Le NTP sortant (Authelia vérifie l'horloge au démarrage et refuse une dérive).
- La prise en compte de `limitOverride`, de la politique de redémarrage et de la santé ;
  l'enrôlement réel (téléphone, PC) ; la lecture de `/config/notification.txt` par `railway ssh`
  ou `railway volume files`.

## 12. Limites connues

1. **Jeton révoqué ou réutilisé → 503 persistant** (mesuré) : Authelia répond **500**
   (« error revoking oauth2 access token session … no rows affected », détection de
   réutilisation) au lieu de 400 `invalid_grant`, et Hermes traduit tout statut autre que 400 en
   503 **sans effacer ses cookies**. Cas normal épargné (la déconnexion efface les cookies), mais un
   jeton de rafraîchissement rejoué ou perdu lors d'une rotation laisserait le navigateur en 503
   jusqu'à la déconnexion (`POST /auth/logout`) ou l'effacement des cookies du site. L'expiration
   à 7 jours devrait, elle, rendre 400 (**déduit** du code de fosite, non mesuré : il faudrait
   attendre 7 jours ou changer la durée).
2. Les cookies de Hermes sont sans `Secure` tant que `trusted_proxies` reste vide (§7).
3. Rafale de premiers facteurs non bornée (§8).
4. Consentement explicite à chaque connexion complète (§4).
5. La fenêtre de 7 jours du jeton de rafraîchissement est **supposée glissante** (chaque rotation
   émet un jeton neuf de 7 jours) : non mesuré.
6. Le mode « under attack » du WAF pourrait bloquer les appels serveur à serveur de Hermes vers
   l'IdP (supposé, à éprouver hors incident).

## 13. Preuves

**Locales, 25/09/2026** (images construites depuis le worktree : `acp-hermes:p2b`,
`acp-hermes-tests:p2b`, `acp-identite:p2b` ; pytest 9.1.1, Python 3.12 ; aucun test ignoré) :

| Suite | Commande | Résultat |
|---|---|---|
| Dans l'image Hermes | `docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site acp-hermes-tests:p2b -m pytest -v -rA /opt/acp-tests/image` | **216 réussis**, 0 échec, 0 ignoré |
| Contrat (Hermes et identité) | `PYTHONUTF8=1 ACP_IMAGE=acp-hermes:p2b ACP_IMAGE_TESTS=acp-hermes-tests:p2b ACP_IMAGE_IDENTITE=acp-identite:p2b python -m pytest -s -v -rA hermes/tests/contrat` | **96 réussis** (56 Hermes, 40 identité), 0 échec, 0 ignoré, 11 min 15 s |
| Navigateur | `PYTHONUTF8=1 ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… ACP_E2E_OBLIGATOIRE=1 python -m pytest -s -v -rA hermes/tests/e2e` | **1 réussi**, 33 s ; Chromium 151.0.7922.34 (révision 1234) DÉJÀ présent sur le poste, rien téléchargé |

Chaque protection d'identité retirée d'une copie de `identite/` fait échouer son test (images
jetables, supprimées ensuite) :
- politique `authorization_policy: 'proprietaire'` retirée du client → le « second compte » n'est
  plus refusé : `test_sujet_autre_refuse_par_la_politique_oidc` échoue ;
- fichier des utilisateurs conservé au redémarrage au lieu d'être réécrit →
  `test_un_seul_utilisateur` échoue (le second compte survit).

**CI**, commit `69b81a7` (branche `refonte/hermes-p2`, 25/09/2026) :
- `image.yml`, run **36094807793** : **succès** en 12 min 30 s. Condensats de Hermes et
  d'Authelia confirmés ; 216 réussis dans l'image ; contrat **96 réussis** (0 échec, 0 ignoré) ;
  navigateur **1 réussi** (Chrome for Testing 151.0.7922.34, révision 1234, téléchargé par la CI).
  Mémoire mesurée sur le coureur GitHub : 0,729 Gio à 10, **1,297 Gio** à 20 (51,9 % de la limite
  de 2,5 Gio) ; témoin sous 1 Gio tué (OOM, code 137).
- `ci.yml`, run **36094807754** : **succès**.
