# Déploiement Railway d'ACP — procédure du propriétaire (étape P2)

État du **25 septembre 2026**. Étape P2 du [plan de la refonte](plan.md). **Rien n'est déployé**,
aucun compte n'a été utilisé : tout ce qui suit est **préparé et prouvé côté dépôt**, puis
**exécuté par le propriétaire seul**, étape par étape. L'image Hermes est décrite dans
[image.md](image.md), le fournisseur d'identité dans [identite.md](identite.md).

Conventions :
- **vérifié** : lu dans la documentation de Railway (copie locale `rw_full.txt`, relevée le
  24/09/2026 ; les numéros de ligne y renvoient) ou dans le SDK `railway@3.11.0` ;
- **mesuré** : observé sur un conteneur local ou en CI ;
- **supposé** : à prouver sur Railway, au premier déploiement. Rien de supposé n'est présenté comme
  acquis.

Sommaire : § 1 ce qui est déployé · § 2 prérequis · § 3 règles de l'IaC · § 4 premier déploiement ·
§ 5 identité · § 6 cerveau (openai-codex) · § 7 preuves à relever · § 8 relais et
`trusted_proxies` · § 9 exploitation · § 10 récupération · § 11 sécurité du compte · § 12 prouvé en
local, seulement sur Railway, limites.

---

## 1. Ce qui est déployé

Un projet Railway **`acp`**, environnement **`production`**, offre **Hobby**, décrit en entier par
[`.railway/railway.ts`](../../.railway/railway.ts) :

| | `hermes` | `identite` |
|---|---|---|
| Rôle | Hermes Agent 0.21.5, image dérivée d'ACP (tableau de bord, passerelle, greffon `acp-poste`) | Authelia 4.39.28, un seul utilisateur, client OIDC `hermes-acp` |
| Source | GitHub `Paul-Berdier/agent-company-platform`, branche **`refonte/hermes`** | idem |
| Répertoire racine / Dockerfile | `/hermes`, `RAILWAY_DOCKERFILE_PATH=image/Dockerfile` | `/identite`, `Dockerfile` |
| Constructeur | `DOCKERFILE` | `DOCKERFILE` |
| Wait for CI | oui (`checkSuites: true`) | oui |
| Motifs surveillés | `/hermes/**` sauf `/hermes/tests/**` | `/identite/**` |
| Volume | `hermes-donnees` sur `/opt/data` | `identite-donnees` sur `/config` |
| Port (santé et domaine) | `9119` | `9091` |
| Santé | `/api/health`, 300 s | `/api/health`, 120 s |
| Région, répliques | `europe-west4-drams3a` (EU West, Amsterdam), 1 | idem |
| Limites | 1 vCPU, 2 Gio | 0,5 vCPU, **2,5 Gio** (mesurés : [identite.md](identite.md) § 8) |
| Redémarrage | `ON_FAILURE`, 10 relances | `ON_FAILURE`, 100 relances |
| Serverless (mise en veille) | coupé | coupé |
| Domaine public | `<libellé-hermes>.up.railway.app` | `<libellé-identite>.up.railway.app` |
| Variables | toutes déclarées dans `railway.ts` | 4 déclarées, 4 posées par vous (`preserve()`), dont l'empreinte **scellée** |

**Aucune Start Command** : l'ENTRYPOINT de chaque image est sa garde (`acp-entree` puis s6 pour
Hermes, `acp-identite-entree` pour l'identité). Une Start Command remplace l'ENTRYPOINT
(rw_full.txt:29497-29507) : la seule admise est celle de maintenance, posée à la main puis retirée
(§ 10).

Ce que `railway.ts` **ne décrit pas**, et que la procédure couvre à la main :
- les **domaines générés** `*.up.railway.app` (non décrits par l'IaC, rw_full.txt:28742) ;
- les **sauvegardes** planifiées (le type `VolumeMount.backupSchedules` existe dans le SDK, sans
  forme documentée pour un `volume(...)`) ;
- les **valeurs** des quatre variables d'identité ;
- les limites de dépense, les clés SSH, l'autorisation de l'application GitHub de Railway.

Parcours d'une connexion : navigateur → `https://<libellé-hermes>.up.railway.app` (bord de
Railway, TLS) → Hermes renvoie vers `https://<libellé-identite>.up.railway.app` (Authelia : mot de
passe, passkey, consentement) → retour sur Hermes, session ouverte. Hermes joint l'émetteur par son
URL **publique** ; le domaine privé `*.railway.internal` est refusé par les deux gardes.

---

## 2. Prérequis (une fois)

1. **Compte Railway** : offre **Hobby** ; **double authentification** activée ; région préférée
   **EU West** (paramètres de l'espace de travail) ; **aucune clé SSH d'espace de travail**.
2. **Limites de dépense** (décision du propriétaire) :
   ```sh
   railway usage limit set --target workspace --soft 15 --hard 30
   railway usage limit set --target agent --hard 0
   railway usage limit status
   ```
   L'alerte de 15 $ envoie un courriel ; la limite dure de 30 $ **met hors ligne toutes les
   charges**, fournisseur d'identité compris, jusqu'au relèvement ou au cycle suivant
   (rw_full.txt:5467-5520). La limite de l'agent Railway (0 $) bloque son usage ; elle est
   indépendante (rw_full.txt:24552-24723).
3. **Poste de commande : WSL**. Sous Windows, Railway documente sa CLI par WSL
   (rw_full.txt:16958-16974). Dans WSL :
   - Node.js **≥ 22** (le SDK l'exige, et la CLI évalue `railway.ts` avec Node) ;
   - CLI Railway **≥ 5.42.1** (version minimale exigée par le SDK 3.11.0 : « The IaC engine now
     ships in the CLI ») ; `railway --version` ;
   - `gh` (GitHub CLI), connecté à votre compte ;
   - un **clone propre** de la branche déployée, dans le système de fichiers de WSL (pas le checkout
     Windows, qui porte un chantier Pixel Office non commité) :
     ```sh
     git clone --branch refonte/hermes https://github.com/Paul-Berdier/agent-company-platform.git ~/acp-railway
     cd ~/acp-railway
     npm ci --ignore-scripts --prefix .railway
     npm run --prefix .railway verifier     # tsc, puis l'évaluation locale (§ 3)
     ```
4. **Clé SSH dédiée** (ed25519, **avec phrase de passe**), créée et rangée **hors du compte Windows
   où tournent Claude Code et Codex** : un autre compte Windows local, une autre machine, ou un
   support amovible chiffré branché le temps d'une opération. WSL dans le même compte ne compte pas
   comme « hors du compte ». Elle n'est enregistrée chez Railway que pendant une opération (§ 11).
5. **Docker Desktop** sous Windows, pour calculer l'empreinte du mot de passe (§ 5.1).

---

## 3. Règles de l'IaC

- **Vous seul appliquez**, depuis votre poste : ni la CI, ni un agent. Aucun jeton Railway n'est
  donné à GitHub (l'action `railwayapp/config` n'est pas utilisée).
- **Fichier de projet entier** : toute ressource omise est **supprimée** au prochain apply
  (rw_full.txt:28156) ; détacher ou supprimer un volume est destructif (rw_full.txt:28708). Aucune
  ressource n'est donc créée à la main (hors domaines générés, non gérés par l'IaC).
- `railway config apply` **toujours interactif** : jamais `--yes`, jamais `--confirm-destructive`.
  Lisez chaque ligne du plan ; toute ligne de destruction arrête l'opération.
- **Railway ne lit jamais `.railway/`** au déploiement (rw_full.txt, « Multi-repo projects ») : le
  fichier ne sert qu'au plan et à l'apply.
- **Jamais `railway config pull` sans `--json`** : sans lui, la commande **réécrit**
  `.railway/railway.ts` (gardes et commentaires perdus). `railway config pull --json` affiche le
  graphe sans rien écrire. Si le fichier a été réécrit par erreur :
  `git checkout -- .railway/railway.ts`.
- **Aucun apply entre une restauration de sauvegarde et la PR qui réaligne le fichier** (§ 10 d).
- `.railway/.gitignore` n'autorise que les fichiers de l'IaC : ce qu'une commande `railway`
  écrirait dans `.railway/` (lien de projet, README généré) n'entre jamais dans Git.

**Échec fermé.** Tant que `LIBELLE_HERMES` et `LIBELLE_IDENTITE` valent leur gabarit
(`<libellé-hermes>`, `<libellé-identite>`), l'évaluation du fichier refuse :

```text
[acp] REFUS (.railway/railway.ts) : LIBELLE_HERMES vaut encore le gabarit « <libellé-hermes> ». Choisissez le libellé du sous-domaine *.up.railway.app et remplacez-le par une PR, CI verte (docs/refonte/railway.md § 4). Rien n'est planifié ni appliqué.
```

Sont refusés de même : un libellé qui n'est pas un libellé DNS (majuscule, point, tiret en tête ou
en fin, vide, plus de 63 caractères), deux libellés identiques, et tout environnement lié autre que
`production` (mesuré par `.railway/verifier.mjs`, en local et en CI).

**Ce que la CI vérifie à chaque changement de `.railway/**`** (`image.yml`) :
1. `npm ci --ignore-scripts --prefix .railway` : SDK `railway@3.11.0` et `typescript@7.0.2`
   installés depuis leur verrou haché, sans script d'installation ;
2. `tsc` : `railway.ts` typé contre le SDK (options strictes, `erasableSyntaxOnly`) ;
3. `verifier.mjs` : le fichier est évalué comme le fait la CLI (Node, suppression des types) ; les
   gabarits DOIVENT être refusés ; avec des libellés d'essai, le graphe doit compter exactement
   deux services et deux volumes, avec les réglages du § 1, sans Start Command, pré-déploiement,
   domaine ni secret ;
4. `test_railway_iac_contrat.py` : chaque image démarre avec exactement les variables que le
   graphe déclare (plus celles que Railway fournit, simulées), sa santé répond 200 sur le PORT
   déclaré avec l'hôte `healthcheck.railway.app` (rw_full.txt:29964) ; `identite` refuse de
   démarrer, en français, sans les quatre variables du propriétaire.
La suite du dépôt (`ci.yml`) lance en plus `scripts/tests/test_railway_iac.py`, contrôle statique
sans Node.

**Clés typées par le SDK mais absentes de la documentation de l'IaC** : `checkSuites`,
`build.builder`, `build.watchPatterns`, `deploy.sleepApplication`, `deploy.restartPolicyType`,
`deploy.restartPolicyMaxRetries`, `deploy.limitOverride`. Leur prise en compte par la CLI et par
Railway est **supposée**. Après l'apply, `railway config pull --json` doit les montrer ; sinon,
réglez-les à la main dans les paramètres du service (Wait for CI, constructeur, motifs, Serverless,
politique de redémarrage, limites des répliques), consignez-le dans `docs/reprise-poste.md`, puis
`railway config plan --detailed-exit-code` doit rendre **0**.

**Ambiguïtés documentées, à trancher au premier plan** (aucune n'est contournée à la main) :
- **Région** : `europe-west4-drams3a` est l'identifiant de la page « Regions », donné pour la
  configuration (rw_full.txt:30283-30294) ; la référence de l'IaC montre aussi `europe-west4`
  (rw_full.txt:28596). Si le plan refuse le premier, le repli `europe-west4` passe par une PR
  (`REGION` dans `railway.ts` **et** dans `verifier.mjs`, CI verte).
- **SDK isolé dans `.railway/`** : la doc dit d'installer le SDK « depuis la racine du dépôt »
  (rw_full.txt:19036). Node résout `railway/iac` depuis l'emplacement de `railway.ts`, donc depuis
  `.railway/node_modules` : c'est ainsi que `verifier.mjs` l'évalue (mesuré) ; que la CLI fasse de
  même est **supposé**. Si le plan échoue sur l'import, ne pas installer le SDK à la racine sans
  PR : le workspace racine est gelé (`scripts/check_engine_frozen.py`).
- **`preserve()` sur une variable qui n'existe pas encore** (premier apply) : **supposé** « ne rien
  créer » ; `identite` refuse alors de démarrer jusqu'au § 5.2 (échec fermé attendu, mesuré par
  `test_identite_refuse_sans_les_variables_du_proprietaire`). Si le plan **refuse** `preserve()`
  sur une variable absente : PR qui retire provisoirement les quatre `preserve()` (et les attend
  absentes dans `verifier.mjs`), apply, pose des quatre variables (§ 5.2), puis PR qui les rétablit
  et `railway config plan` → « already up to date ».
- **`RAILWAY_DOCKERFILE_PATH=image/Dockerfile`** relatif au répertoire racine `/hermes` : supposé.
  Si le premier build ne trouve pas le Dockerfile, le build **échoue** (constructeur `DOCKERFILE`) ;
  corriger par une PR (`/hermes/image/Dockerfile`, ou la clé typée `build.dockerfilePath`).
- **Répertoire racine** écrit `/hermes` (forme des réglages Railway) ; la référence IaC montre
  `apps/api` sans barre initiale (rw_full.txt:28790). `railway config pull --json` dira ce que
  Railway a retenu.

---

## 4. Premier déploiement, étape par étape

Chaque étape se termine par un contrôle ; au moindre écart, arrêt et retour au § 10.

### 4.1 Choisir les deux libellés, puis les écrire par une PR

1. Choisissez deux libellés DNS **distincts** et **peu devinables**, par exemple
   `acp-hermes-<6 caractères aléatoires>` et `acp-identite-<6 caractères aléatoires>` (a-z, 0-9,
   tirets ; 63 caractères au plus). Ils seront **figés** : les passkeys sont liées au sous-domaine
   exact de l'identité, et renommer un domaine après l'enrôlement les invalide.
2. Branche depuis `refonte/hermes`, remplacement des deux constantes `LIBELLE_HERMES` et
   `LIBELLE_IDENTITE` de `.railway/railway.ts`, puis :
   ```sh
   npm run --prefix .railway verifier     # « graphe du fichier committé conforme »
   ```
3. PR vers `refonte/hermes`, CI verte (`image.yml` tourne : `.railway/**` a changé), fusion.
4. Contrôle : `gh run list --workflow image.yml --commit <sha de tête de refonte/hermes>` →
   `success`.

### 4.2 Créer le projet vide et le lier

```sh
cd ~/acp-railway && git pull --ff-only
railway login                         # navigateur ; `--browserless` sinon
railway init --name acp               # crée le projet (environnement production) et le lie
railway link --project acp --environment production
```

Autorisez l'**application GitHub de Railway** sur **ce seul dépôt**, et acceptez ses permissions
mises à jour (exigées par « Wait for CI », rw_full.txt:29670-29680) : c'est un consentement OAuth
que vous seul pouvez donner.

### 4.3 Vérifier la CI, puis planifier

```sh
gh run list --workflow image.yml --commit "$(git rev-parse HEAD)"   # success exigé
npm ci --ignore-scripts --prefix .railway
railway config plan --verbose
```

Contrôlez le plan, ligne à ligne :
- création de **2 services** (`hermes`, `identite`) et **2 volumes** (`hermes-donnees`,
  `identite-donnees`), **0 to destroy** ;
- région, répertoires racines, constructeur, `sleepApplication`, politique de redémarrage, limites,
  santé, **aucune Start Command** ;
- variables : les valeurs sont masquées par défaut (« «hidden» ») ; n'utilisez `--show-values` que
  pour relire des valeurs non secrètes.
Gardez la sortie (elle ne contient aucun secret) pour la joindre au compte rendu.

### 4.4 Appliquer

```sh
railway config apply        # confirmation interactive ; jamais --yes
```

**Attendu** (mesuré en local par les tests de contrat, à constater sur Railway) :
- `hermes` construit et démarre (toutes ses variables sont déclarées) ; journaux du § 4.9 ;
- `identite` **refuse de démarrer** tant que ses quatre variables manquent :
  `[acp-identite] REFUS : la variable ACP_IDP_UTILISATEUR est obligatoire et absente (ou vide).`
  (et de même pour les trois autres), puis `Démarrage arrêté (échec fermé).`, relances comprises.
  C'est voulu.

Le premier déploiement créé par l'apply n'attend peut-être pas la CI (« Wait for CI » est décrit
pour les déploiements automatiques, rw_full.txt:29700) : d'où la vérification du § 4.3 **avant**.

### 4.5 Domaines, AVANT tout enrôlement

```sh
railway domain --service hermes --port 9119
railway domain update <domaine généré pour hermes> --domain <libellé-hermes>
railway domain --service identite --port 9091
railway domain update <domaine généré pour identite> --domain <libellé-identite>
railway domain list --service hermes ; railway domain list --service identite
```

(`--domain` accepte un libellé seul, rw_full.txt:19845-19852.) Si un libellé est **refusé** (déjà
pris) : choisissez-en un autre, retour au § 4.1 (PR, CI, apply), **avant** tout enrôlement.

### 4.6 Identité : empreinte, variables, redéploiement

Suivez le § 5.1 et le § 5.2, puis :
```sh
railway config plan          # « Your Railway configuration is already up to date. »
```
Déployez le changement de variables (bouton « Deploy » des changements en attente,
rw_full.txt:30166-30200). Journal attendu :
`[acp-identite] variables validées ; utilisateur unique « <vous> » ; émetteur https://<libellé-identite>.up.railway.app ; client hermes-acp → https://<libellé-hermes>.up.railway.app/auth/callback`.

Si Hermes répond 503 à la connexion alors qu'`identite` est en ligne (sa première découverte OIDC a
échoué pendant que l'identité refusait de démarrer) : « Redeploy » du déploiement actif de
`hermes`.

### 4.7 Sauvegardes

Pour **chaque** service : onglet **Backups** → planifications **Daily** (gardées 6 jours) et
**Weekly** (gardées 27 jours) (rw_full.txt:32407-32420). Puis une sauvegarde **manuelle** de
chaque volume.

### 4.8 Contrôle de dérive

```sh
railway config pull --json > /tmp/acp-graphe.json     # JAMAIS sans --json
railway config plan --detailed-exit-code ; echo $?    # 0 exigé
```

Dans `acp-graphe.json`, relevez `checkSuites`, `builder`, `watchPatterns`, `sleepApplication`,
`restartPolicyType`, `restartPolicyMaxRetries`, `limitOverride`, la région, le répertoire racine.
Toute clé absente : réglage à la main (§ 3), consigné, puis `--detailed-exit-code` à 0.

### 4.9 Journaux et PID 1

```sh
railway logs --service hermes --latest --lines 200     # journal de déploiement
railway logs --service identite --latest --lines 200
```

Attendus pour `hermes` :
- `[acp] commit déployé : <sha>` — puis `gh run list --workflow image.yml --commit <sha>` →
  `success` ;
- `[acp] variables validées ; émetteur OIDC https://<libellé-identite>.up.railway.app, client hermes-acp, URL publique https://<libellé-hermes>.up.railway.app (client public).` ;
- `info: hook /opt/acp/bin/acp-gardes exited 0` et `05-acp exited 0`.

Journal de construction (`railway logs --service hermes --build --latest --lines 400`, idem pour
`identite`) : la ligne `FROM …@sha256:…` avec le condensat épinglé de chaque image.

**PID 1** (non documenté par Railway ; la garde `acp-entree` refuse de démarrer sinon) : enregistrez
la clé dédiée (§ 11), puis
```sh
railway ssh -i <clé dédiée> --service hermes -- sh -c "tr '\0' ' ' </proc/1/cmdline"
```
Attendu : `/package/admin/s6/command/s6-svscan -d4 -- /run/service` (ou `s6-svscan -d4 --
/run/service`). Retirez ensuite la clé (§ 11).

### 4.10 Enrôlement, connexions, cerveau

§ 5.3 (passkeys), connexion à `https://<libellé-hermes>.up.railway.app` depuis le PC **et** le
téléphone (captures), § 6 (openai-codex).

### 4.11 Répétition de maintenance, une fois, avant d'accumuler des données

§ 10 b sur `hermes` (Start Command de maintenance, santé vidée, `diagnostiquer`), essai du § 10 b-bis
(`railway volume files` sur un service arrêté), retour à la normale, puis
`railway config plan --detailed-exit-code` → 0. Compte rendu écrit.

### 4.12 Clôture

`railway ssh keys remove --2fa-code <code>` (preuve : `railway ssh keys` vide), puis
`railway logout`. Transmettez les sorties (sans secret) : elles vont dans `docs/reprise-poste.md`.

---

## 5. Identité (service `identite`)

### 5.1 Empreinte Argon2id du mot de passe, sur votre poste

Dans **PowerShell** (sous Git Bash, les chemins `/app/…` seraient convertis) :

```powershell
docker run --rm -it --entrypoint /app/authelia docker.io/authelia/authelia:4.39.28@sha256:bd97cff4fcbf715b5ff1f9ae286afbe6033afce385302520b0368122d43a6f54 crypto hash generate argon2
```

La commande demande le mot de passe deux fois (il n'apparaît ni à l'écran ni dans l'historique) et
affiche `Digest: $argon2id$v=19$m=65536,t=3,p=4$…`. Gardez le mot de passe et l'empreinte (la valeur
après `Digest: `) dans votre gestionnaire de mots de passe. Ce `docker run` **télécharge** l'image :
c'est à vous de le lancer.

Paramètres par défaut : 64 Mio par vérification (`m=65536`), 3 passes, 4 fils. La garde admet
19 456 ≤ m ≤ 65 536 Kio ; la limite mémoire de 2,5 Gio a été **mesurée** avec m = 65 536
([identite.md](identite.md) § 8). Une empreinte à `m` plus faible réduit la mémoire par tentative en
proportion.

### 5.2 Variables d'identité, posées dans Railway

Tableau de bord Railway → service `identite` → **Variables** → **New Variable** :

| Variable | Valeur | Règle de la garde |
|---|---|---|
| `ACP_IDP_UTILISATEUR` | votre identifiant | `^[a-z][a-z0-9._-]{0,31}$` |
| `ACP_IDP_NOM` | nom affiché | 1 à 64 caractères, sans `"`, `\` ni caractère de contrôle |
| `ACP_IDP_EMAIL` | votre adresse | adresse électronique |
| `ACP_IDP_MOT_DE_PASSE_ARGON2` | l'empreinte du § 5.1 | puis menu ⋮ → **Seal** : **scellée** |

Une variable scellée n'est plus lisible, ni dans l'interface ni par l'API, et ne peut pas être
« descellée » (rw_full.txt:26066-26093) ; elle se modifie par le menu ⋮. Préférez l'interface à
`railway variables --set` pour l'empreinte : elle contient des `$` (interprétés par PowerShell hors
guillemets simples) et resterait dans l'historique du shell.

### 5.3 Enrôlement des passkeys (WebAuthn)

1. `https://<libellé-identite>.up.railway.app` : connexion par identifiant et mot de passe.
2. Authelia demande d'enregistrer une passkey et envoie un **code à usage unique** dans
   `/config/notification.txt` (notificateur « fichier »). Lisez-le :
   ```sh
   railway ssh keys add --key <clé dédiée>.pub --name acp-operation
   railway ssh -i <clé dédiée> --service identite -- cat /config/notification.txt
   ```
   À essayer aussi, et à consigner : `railway volume files --volume identite-donnees download /notification.txt ./notification.txt`
   (puis supprimez la copie locale).
3. Enregistrez **deux** authentificateurs (PC et téléphone). Vérification de l'utilisateur exigée.
4. Clôture : `railway ssh keys remove --2fa-code <code>`, `railway ssh keys` vide, `railway logout`.

Le consentement est demandé à **chaque connexion complète** (portée `offline_access`,
[identite.md](identite.md) § 4) ; les rafraîchissements sont silencieux. La session Hermes dure au
plus 7 jours sans reconnexion (jeton de rafraîchissement de 7 jours).

### 5.4 Secours

Toutes ces opérations se font **en maintenance** (§ 10 b sur `identite`) et avec
`/opt/acp-identite/acp-identite-admin` (sous-commandes `user …` et `bans …` d'`authelia storage`
seulement ; il relit l'environnement du PID 1, jamais celui de la session) :

- **Mot de passe perdu** : nouvelle empreinte (§ 5.1), édition de la variable scellée, « Deploy ».
- **Passkeys perdues** : `acp-identite-admin user webauthn delete <utilisateur> --all`, retour à la
  normale, nouvel enrôlement (§ 5.3).
- **Propriétaire banni** (5 échecs en 10 minutes bannissent 15 minutes ; un tiers peut donc vous
  verrouiller) : attendre, ou `acp-identite-admin bans user revoke <utilisateur>`.
- **Volume ou clé de stockage perdus** : restauration (§ 10 d) ; à défaut, nouveau volume par PR
  (secrets et clé de signature régénérés, sessions Hermes invalidées, nouvel enrôlement). La garde
  refuse de régénérer en silence une clé de stockage absente alors que la base existe.
- **Attaque par premiers facteurs** (chaque tentative coûte 64 Mio) : la limite de 2,5 Gio tient
  20 tentatives simultanées (mesuré) ; au-delà d'environ 37, le service est tué avant que le
  bannissement ne tombe ([identite.md](identite.md) § 8). Dernier recours :
  `railway waf under-attack enable --service identite --duration 1h` (rw_full.txt:25101-25184).
  **Supposé** : le défi du bord pourrait aussi bloquer les appels de Hermes vers l'identité
  (découverte, jetons, JWKS). À éprouver hors incident.

---

## 6. Cerveau de Hermes : openai-codex

1. Connecté au tableau de bord Hermes : **Clés** → **Connexions fournisseurs (OAuth)** →
   `openai-codex` → **Connexion** : Hermes affiche un **code d'appareil** et l'adresse où le saisir.
2. Ouvrez l'adresse avec **votre** compte ChatGPT et saisissez le code. Si OpenAI refuse (« device-code
   authorization » non activée), activez l'autorisation par code d'appareil dans les paramètres de
   votre compte OpenAI, puis recommencez (message prévu par Hermes,
   `hermes_cli/web_routers/oauth.py:68-85`).
3. **Modèles** : choisissez le modèle par défaut.
4. Discussion : « Exécute `id` dans un terminal » → **refus attendu** : l'agent n'a aucun outil
   d'exécution sur Railway ([image.md](image.md) § 5).

Les jetons (tournants) vivent dans `/opt/data` : ils sont dans les sauvegardes du volume ; une
restauration impose de reconnecter openai-codex.

---

## 7. Preuves à relever sur Railway

À transmettre sans aucun secret ; elles vont dans `docs/reprise-poste.md`.

1. `railway config plan --verbose` avant l'apply (« 0 to destroy ») ; `railway config pull --json`
   après, avec les clés du § 3 ; sinon réglage manuel et `plan --detailed-exit-code` = 0.
2. Pour **chaque** déploiement : `gh run list --workflow image.yml --commit <RAILWAY_GIT_COMMIT_SHA>`
   → `success` (le SHA est dans `[acp] commit déployé : …` et dans le bloc `deploiement` de
   `/api/plugins/acp-poste/v1/meta`).
3. Journal de construction : les deux condensats ; constructeur Dockerfile.
4. Journaux de démarrage (§ 4.9) ; `[acp-identite] … utilisateur unique …`.
5. PID 1 : `s6-svscan -d4 -- /run/service` (§ 4.9).
6. Sans session :
   ```sh
   curl -s https://<libellé-hermes>.up.railway.app/api/health          # ok, 0.21.5, auth_required: true
   curl -s https://<libellé-hermes>.up.railway.app/api/auth/providers  # self-hosted seul
   curl -s -o /dev/null -w '%{http_code}\n' https://<libellé-hermes>.up.railway.app/api/config   # 401
   curl -s https://<libellé-identite>.up.railway.app/.well-known/openid-configuration  # issuer, RS256, revocation_endpoint
   ```
   et `/api/ws` sans ticket refusé.
7. En-têtes falsifiés (§ 8) : comportement consigné.
8. Connexion depuis le PC et le téléphone (captures) ; refus d'un autre identifiant ; refus d'une
   `redirect_uri` altérée ; rafraîchissement sans 503.
9. openai-codex connecté ; « Exécute `id` dans un terminal » → refus.
10. Après un redéploiement : sessions, `state.db` et passkeys conservés.
11. États `WAITING` puis déploiement après CI verte ; **aucun run `image.yml` annulé** sur
    `refonte/hermes`.
12. Métriques d'une semaine (mémoire, CPU) et coût constaté (`railway usage`) ; sauvegardes listées.
13. Compte rendu de la répétition de maintenance (§ 4.11), avec le résultat de
    `railway volume files` sur un service arrêté.
14. `railway ssh keys` **vide** hors opération (sortie datée).

---

## 8. Relais de Railway et `trusted_proxies`

**Mesuré en local** (bord TLS factice, [identite.md](identite.md) § 7) : avec
`dashboard.trusted_proxies: []` (managed scope), Hermes voit les requêtes en **http** ; ses cookies
de session n'ont donc **pas** l'attribut `Secure` (atténué par le préchargement HSTS de `.app`), et
`/v1/meta` le signale en alerte. L'URL de retour OIDC vient de `HERMES_DASHBOARD_PUBLIC_URL`, pas
des en-têtes.

**À mesurer sur Railway, sur plusieurs jours** :
1. Connecté, ouvrez `https://<libellé-hermes>.up.railway.app/api/plugins/acp-poste/v1/meta` : bloc
   `reseau` (pair, schéma vu, hôte, **présence** des en-têtes transmis — jamais la valeur de
   `X-Forwarded-For`). Relevez l'adresse du pair à chaque fois.
2. Retrait des en-têtes falsifiés par le bord : Authelia n'accepte un `X-Forwarded-Host` que s'il
   désigne son propre domaine (mesuré : 400 sinon). Donc
   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Forwarded-Host: intrus.example' https://<libellé-identite>.up.railway.app/
   ```
   **400** : le bord transmet l'en-tête du client ; **200** : il le retire ou le remplace. Consignez
   le résultat.

**Règle** : `trusted_proxies` reste `[]` tant que la plage du bord n'est pas **mesurée et stable**.
Le changer passe par une PR sur `hermes/gere/config.yaml` (managed scope), avec la mesure ; jamais
`/0` (Hermes le refuse). Sans cela, l'adresse journalisée par `client_ip` reste falsifiable.

---

## 9. Exploitation courante

**Chaîne de déploiement.** PR vers `refonte/hermes` → fusion → Railway voit le push (motifs
surveillés) → déploiement **`WAITING`** jusqu'à la fin de **tous** les workflows GitHub Actions du
commit (rw_full.txt:29696-29707) : un échec saute le déploiement ; un run annulé n'est ignoré que si
un autre a réussi ; au-delà de 2 heures, le déploiement est sauté.

- **Ne jamais annuler `image.yml` à la main** sur `refonte/hermes` : un run annulé ne prouve rien et
  « Wait for CI » l'ignore dès qu'un autre workflow a réussi. Hors PR, `image.yml` a un groupe de
  concurrence **par exécution** : aucun run n'est jamais remplacé.
- `ci.yml` et, s'il se déclenche, Desktop CI comptent aussi : un rouge saute le déploiement.
  Après la relance réussie d'un workflow, le déploiement sauté n'est pas refait seul.
- Pour relancer : **« Redeploy »** d'un déploiement déjà prouvé (même code et même configuration,
  rw_full.txt:52320-52330). **« Deploy Latest Commit »** seulement après
  `gh run list --workflow image.yml --commit <sha de tête>` → `success` : la doc dit tantôt qu'il
  déploie la branche connectée (rw_full.txt:29653), tantôt la branche par défaut du dépôt
  (rw_full.txt:29564, 52330) ; vérifiez le SHA déployé dans le journal.
- **Rollback** : restaure l'image et les variables d'un déploiement précédent, pas le volume.
- Chaque déploiement : preuve du § 7 point 2.

**Sauvegardes.** Quotidienne (6 jours) et hebdomadaire (27 jours), plus une manuelle avant toute
maintenance. Limites (rw_full.txt:32452-32464) : une sauvegarde manuelle est limitée à 50 % de la
taille du volume ; **effacer un volume efface ses sauvegardes** ; restauration dans le même projet
et le même environnement seulement. Les sauvegardes d'`identite` contiennent ses secrets et sa clé
de signature ; celles de `hermes` contiennent `auth.json` (jetons openai-codex) : la frontière de
confiance est le compte Railway (§ 11).

**Coûts** (Hobby : 5 $ déduits de l'usage, RAM 10 $/Go/mois, CPU 20 $/vCPU/mois, volume 0,15 $/Go/mois,
sortie 0,05 $/Go ; seul l'usage réel est facturé, rw_full.txt:4848-4892) :
- usage normal **estimé** 6 à 16 $/mois (Hermes mesuré à 415-440 Mio au repos, Authelia ~0,1 Gio) ;
- pire cas **théorique** aux limites : Hermes 2 × 10 + 1 × 20 = 40 $ ; identite 2,5 × 10 + 0,5 × 20
  = 35 $ ; total 75 $ ;
- la limite dure de **30 $ coupe tout avant**, identité comprise. Relevé hebdomadaire :
  `railway usage` et `railway usage projects --project acp`.

**Montée de version de Hermes ou d'Authelia** : PR qui change le `FROM` épinglé (et
`hermes/contrat/`), CI verte, déploiement par la chaîne normale. Jamais `hermes update`, `:latest`
ni `AUTO_UPDATE`.

**Modifier l'infrastructure** : PR sur `.railway/railway.ts` (et `verifier.mjs` si le graphe attendu
change), CI verte, fusion, puis plan (« 0 to destroy » sauf décision écrite) et apply par vous.

---

## 10. Récupération

On ne désactive **jamais** une garde, on n'ajoute **jamais** de variable de contournement, on ne
supprime jamais un volume pour « repartir ».

### a) Lire le refus

Journaux du déploiement (`railway logs --service hermes`) : `[acp] REFUS : …` ou
`[acp-identite] REFUS : …` nomment le fichier ou la variable en cause.

### b) Maintenance sur place (volume piégé, refus au démarrage)

1. **Sauvegarde manuelle** du volume (onglet Backups).
2. Paramètres du service → **Custom Start Command** : `/bin/sh -c "exec sleep infinity"`. Jamais
   `sleep infinity` nu : la Start Command remplace l'ENTRYPOINT, et Railway ne dit pas s'il garde
   le `CMD` hérité (`gateway run` pour Hermes) ; sous cette forme, d'éventuels arguments hérités
   deviennent `$0` et `$1` du shell et sont ignorés (mesuré en local dans les deux cas).
3. **Chemin de santé vidé** (rien n'écoute en maintenance), puis « Deploy » des changements en
   attente.
4. Session root, avec la clé dédiée (§ 11) :
   ```sh
   railway ssh keys add --key <clé dédiée>.pub --name acp-maintenance
   railway ssh -i <clé dédiée> --service hermes
   /opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py diagnostiquer
   ```
   `diagnostiquer` est en lecture seule ; il lit l'environnement du PID 1 (`/proc/1/environ`),
   jamais celui de la session `railway ssh`, dont la doc ne dit rien ; il liste variables
   interdites, `hooks/`, `scripts/`, clés exécutables de `config.yaml`, `lazy-packages` (code 1 si
   un constat existe). Pour `identite` : `/opt/acp-identite/acp-identite-admin …` (§ 5.4).
5. **Correction** : retirez ce qui est signalé, en consignant ce qui a été retiré.
6. **Retour** : Start Command effacée, chemin de santé `/api/health` rétabli, « Deploy » : les gardes
   revérifient tout.
7. `railway config plan --detailed-exit-code` → **0**.
8. `railway ssh keys remove --2fa-code <code>` (preuve : `railway ssh keys` vide), `railway logout`.

### b-bis) À éprouver pendant la répétition

`railway volume files --volume hermes-donnees list /` sur un service **arrêté**. Si cela fonctionne,
c'est une voie de lecture sans toucher aux gardes. La suppression de fichiers par cette voie reste
réservée à un humain (la CLI la refuse à un agent, rw_full.txt:25069).

### c) Supprimée

Déplacer un volume vers un autre environnement pour l'examiner n'est pas documenté
(rw_full.txt:24922-24925 ; restauration « same project + environment », rw_full.txt:32464).

### d) Restauration d'une sauvegarde

1. Onglet **Backups** → **Restore** sur la sauvegarde choisie : le changement est **mis en
   attente** ; un **nouveau volume**, nommé d'après la date, est monté au même endroit ; l'ancien
   est démonté et conservé (rw_full.txt:32432-32442).
2. Dans le **même lot** de changements en attente : Start Command de maintenance (b.2) et chemin de
   santé vidé (b.3), **puis** « Deploy ». Hermes ne redémarre donc jamais sur des données non
   diagnostiquées.
3. `diagnostiquer` (b.4), correction (b.5).
4. `railway config pull --json` : relevez le nom daté du nouveau volume.
5. **PR qui réaligne `railway.ts`** (et `verifier.mjs`). Proposition, **à prouver par le plan** :
   - l'ancien volume renommé `hermes-donnees-avant-AAAAMMJJ`
     (`railway volume update --volume hermes-donnees --name hermes-donnees-avant-AAAAMMJJ`) et
     déclaré, sans montage, tant que vous n'avez pas décidé de le supprimer ;
   - le volume restauré renommé `hermes-donnees` ;
   - `railway config plan --verbose` → **0 to destroy**.
6. **Seulement ensuite** : retour (b.6), puis `plan --detailed-exit-code` → 0.

**Aucun `railway config apply` entre la restauration et cette PR** : le fichier désignerait encore
l'ancien volume, et un apply pourrait détacher le volume restauré. Même traitement pour `/config`
d'`identite`. Les sauvegardes plus récentes que celle restaurée restent sur l'ancien volume
(rw_full.txt:32438).

### e) Identité

§ 5.4.

---

## 11. Sécurité du compte Railway

Le compte Railway est la **frontière de confiance** : il donne accès aux volumes (jetons
openai-codex, secrets et clé de signature d'Authelia), aux variables et aux shells root.

- **Clé SSH dédiée** ed25519 avec phrase de passe, rangée hors du compte Windows des agents (§ 2).
  Toujours `railway ssh -i <clé dédiée>` (la CLI saute alors l'examen de `~/.ssh`,
  rw_full.txt:23298, 23344).
- **Interdits** : la clé par défaut de `~/.ssh`, `railway ssh keys github`, toute clé d'espace de
  travail (elle donne accès à tous les services de l'espace).
- **Après chaque opération** : `railway ssh keys remove --2fa-code <code>`. Preuve :
  `railway ssh keys` vide. Une clé enregistrée suffit, **sans session CLI**, pour `ssh`, `scp`,
  `sftp` et la redirection de port vers le `127.0.0.1` du conteneur (api_server 8642, tableau de
  bord 9119) (rw_full.txt:23279-23420). Une clé matérielle `sk-ssh-ed25519` n'est à envisager que si
  Railway l'accepte (non documenté).
- **Accès équivalents par la seule session CLI** : `railway volume files` et `volume browse`
  (lecture et écriture de tout le volume), `railway service files`, `railway service source connect
  --image` (remplacer la source du service). D'où **`railway logout` après chaque opération**, en
  plus du retrait de la clé : le jeton de session vit dans le compte où tournent aussi les agents.
- Aucun jeton Railway (`RAILWAY_TOKEN`, `RAILWAY_API_TOKEN`) n'est donné à la CI ni à un agent.
- Retirer une clé SSH ou supprimer un volume se fait avec un code de double authentification
  (`--2fa-code`).

---

## 12. Prouvé en local, seulement sur Railway, limites

### Prouvé en local et en CI (25/09/2026)

- **IaC** : `railway.ts` typé par `tsc` 7.0.2 contre `railway@3.11.0` ; évalué comme la CLI
  (`verifier.mjs`) : gabarits, libellés invalides ou identiques, autre environnement → refus en
  français ; graphe d'essai conforme (2 services, 2 volumes, Wait for CI, Dockerfile, santé,
  région, limites, redémarrage, Serverless coupé, `preserve()`, aucune Start Command). Chaque
  réglage retiré ou altéré dans une copie (Start Command ajoutée, garde des gabarits retirée,
  Serverless, volume omis, empreinte en clair, domaine personnalisé, Wait for CI coupé) fait
  échouer le vérificateur.
- **Contrôle statique** (`scripts/tests/test_railway_iac.py`, 39 tests) : SDK isolé et épinglé,
  verrou haché, aucune Start Command, réglages, gabarits et garde, aucun secret, cohérence avec les
  images, aucun fichier Config as Code, CI.
- **Images et IaC** (`test_railway_iac_contrat.py`) : Hermes démarre avec les variables déclarées
  et celles que Railway fournit (message de commit sur deux lignes avec `$HOME`, `` `id` `` et
  `$(id)` compris), journalise le commit déployé ; santé 200 sur 9119 avec l'hôte
  `healthcheck.railway.app` ; `identite` idem sur 9091 ; `identite` sans ses quatre variables :
  quatre refus nommés en français, code 1, `/config` laissé vide.
- **Images** : tout ce qui est listé dans [image.md](image.md) § 9 (agent sans outil d'exécution,
  gardes, maintenance `sleep infinity` avec et sans `CMD` hérité, `diagnostiquer`) et
  [identite.md](identite.md) § 13 (gardes, OIDC à travers un bord factice, navigateur, mémoire).

### Seulement sur Railway (non prouvé ici)

1. **PID 1** : non documenté ; indice tiers seulement (PR mobius-os #1165 du 14/09/2026 : Railway
   « runs its CMD directly »). `acp-entree` refuse sinon : le premier démarrage le tranchera.
2. **Start Command** : Railway garde-t-il le `CMD` hérité ? La forme `/bin/sh -c` couvre les deux cas.
3. **IaC** : évaluation par la CLI avec le SDK dans `.railway/` (sous WSL) ; prise en compte des clés
   non documentées ; `preserve()` sur une variable neuve ; `RAILWAY_DOCKERFILE_PATH` relatif ;
   identifiant de région ; forme du répertoire racine.
4. Environnement et utilisateur d'une session `railway ssh` ; `railway volume files` sur un service
   arrêté.
5. **Restauration** : mise en attente combinable avec une Start Command dans le même lot ; renommage
   des volumes avec un plan à « 0 to destroy ».
6. **Déploiements hors automatisme** : « Deploy Latest Commit » et premier déploiement créé par
   l'apply face à « Wait for CI ».
7. « Wait for CI » avec les workflows réels et des groupes de concurrence par exécution.
8. **Réseau** : adresse du bord, en-têtes `X-Forwarded-*`, `trusted_proxies` ; émetteur d'Authelia à
   travers le vrai bord ; NTP sortant (Authelia vérifie l'horloge au démarrage).
9. Effet du mode « under attack » sur les appels de Hermes vers l'identité (supposé bloquant).
10. Santé, drainage, redémarrages, sauvegardes sur Hobby, consommation et coût réels.
11. Connexion depuis le téléphone ; openai-codex par code d'appareil ; premier tour réel.
12. Disponibilité des libellés choisis (`railway domain update … --domain`).

### Limites connues

- Le tableau de bord **authentifié** reste un **shell du propriétaire** (terminal, fichiers, MCP,
  variables) : un vol de session équivaut à une exécution de code avec accès aux jetons ChatGPT.
  Filtrage prévu plus tard ([autonomie.md](autonomie.md)).
- Cookies de Hermes sans `Secure` tant que `trusted_proxies` est vide (§ 8).
- Jeton de rafraîchissement révoqué ou rejoué → 503 persistant jusqu'à la déconnexion
  ([identite.md](identite.md) § 12).
- Rafale de premiers facteurs non bornée ([identite.md](identite.md) § 8).
- Passkeys liées au sous-domaine exact de l'identité : renommer ce domaine oblige à les réenrôler.
- Une limite dure atteinte met **tout** hors ligne, identité comprise.
- Un `ci.yml` ou une Desktop CI rouge sur un commit saute son déploiement.
