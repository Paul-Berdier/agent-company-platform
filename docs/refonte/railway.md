# Déploiement Railway d'ACP — procédure du propriétaire (étapes P2, P6 et P7)

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

**Étape P6 (1er octobre 2026)** : un troisième service, l'**exécutant** (`executant`), porte Codex CLI et Claude Code ;
sa conception est dans [executant.md](executant.md), ses gestes au **§ 13**. Toujours **rien de déployé** ; la sonde
R0 (§ 13.2) est le premier geste, dans un projet jetable.

**Étape P7 (8 octobre 2026)** : le service `hermes` déclare par `preserve()` les six variables du canal de
notification (Telegram ou ntfy) ; vos gestes — canal, bilan quotidien facultatif, dépôts réels un par un, preuves —
sont au **§ 14**. Toujours **rien de déployé**.

Relecture indépendante de P2 (exploitation) : ordre des étapes rendu exécutable à la lettre,
installation de la CLI sans configuration d'agent, prérequis WSL, sauvegardes hors IaC, refus PID 1,
Rollback, dépôt public ; chaque correction est signalée « relecture P2 », et le tableau de
traitement est dans [`historique.md`](historique.md), partie B, § 6.

Sommaire : § 1 ce qui est déployé · § 2 prérequis · § 3 règles de l'IaC · § 4 premier déploiement ·
§ 5 identité · § 6 cerveau (openai-codex) · § 7 preuves à relever · § 8 relais et
`trusted_proxies` · § 9 exploitation · § 10 récupération · § 11 sécurité du compte · § 12 prouvé en
local, seulement sur Railway, limites · § 13 exécutant (étape P6) · § 14 notifications, bilan quotidien et
dépôts réels (étape P7).

**Étape P9** : le calendrier, les sauvegardes, la restauration (arbre de décision, ordre des volumes, reconnexions,
répétition) et la montée de version sont dans le [manuel d'exploitation](../exploitation.md), qui renvoie ici pour
les commandes.

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
| Variables | toutes déclarées dans `railway.ts` ; depuis P7, les 6 du canal de notification posées par vous, facultatives (`preserve()`, jetons **scellés**, § 14) | 4 déclarées, 4 posées par vous (`preserve()`), dont l'empreinte **scellée** |

**Aucune Start Command** : l'ENTRYPOINT de chaque image est sa garde (`acp-entree` puis s6 pour
Hermes, `acp-identite-entree` pour l'identité). Une Start Command remplace l'ENTRYPOINT
(rw_full.txt:29497-29507) : la seule admise est celle de maintenance, posée à la main puis retirée
(§ 10).

Ce que `railway.ts` **ne décrit pas**, et que la procédure couvre à la main :
- les **domaines générés** `*.up.railway.app` (non décrits par l'IaC, rw_full.txt:28742) ;
- les **sauvegardes** planifiées. Attention (relecture P2) : le SDK les **modélise**
  (`VolumeMount.backupSchedules` et `volumeAttachments[…].backupSchedules`, index-C3uk0ruc.d.ts:113-116
  et 185-190), mais `volume(...)` ne les transmet jamais (`normalizeVolumeMounts`, dist/iac/index.js).
  Si le moteur de la CLI compare ce champ, un apply ultérieur pourrait **retirer en silence** les
  planifications posées à la main : ce serait une ligne de **modification**, pas de destruction.
  D'où le contrôle du § 4.8 et la règle d'apply du § 3 ; le comportement réel n'est connu que sur
  Railway (§ 12) ;
- les **valeurs** des quatre variables d'identité ;
- les limites de dépense, les clés SSH, l'autorisation de l'application GitHub de Railway.

**Étape P6** : un troisième service, `executant` (racine `/`, `executant/Dockerfile`, volume `executant-donnees`
sur `/donnees`, 2 vCPU et 4 Gio, ni domaine, ni port, ni santé, aucune variable secrète) ; tableau et gestes au
§ 13. Le fichier décrit alors **trois services et trois volumes**.

Parcours d'une connexion : navigateur → `https://<libellé-hermes>.up.railway.app` (bord de
Railway, TLS) → Hermes renvoie vers `https://<libellé-identite>.up.railway.app` (Authelia : mot de
passe, passkey, consentement) → retour sur Hermes, session ouverte. Hermes joint l'émetteur par son
URL **publique** ; le domaine privé `*.railway.internal` est refusé par les deux gardes.

---

## 2. Prérequis (une fois)

1. **Compte Railway** : offre **Hobby** ; **double authentification** activée ; région préférée
   **EU West** (paramètres de l'espace de travail) ; **aucune clé SSH d'espace de travail** ;
   **compte GitHub relié** au compte Railway, avec accès contributeur au dépôt : l'autodéploiement
   l'exige (« Autodeploy works only when at least one project member has a connected GitHub
   account with contributor access », rw_full.txt:29663).
2. **Limites de dépense** (décision du propriétaire) : dès maintenant par la page **Workspace
   Usage** du tableau de bord Railway (bouton « Set Usage Limits » : alerte de 15 $ et limite dure
   de 30 $ pour « Compute Usage », limite dure de 0 $ pour « Agent Usage », rw_full.txt:5475),
   **ou** par la CLI, mais seulement **après** son installation (§ 2.3) et `railway login`
   (§ 4.2) — relecture P2 : la première version plaçait ces commandes avant la CLI :
   ```sh
   railway usage limit set --target workspace --soft 15 --hard 30
   railway usage limit set --target agent --hard 0
   railway usage limit status
   ```
   Dans tous les cas, `railway usage limit status` est relevé au § 4.2, avant tout apply.
   L'alerte de 15 $ envoie un courriel ; la limite dure de 30 $ **met hors ligne toutes les
   charges**, fournisseur d'identité compris, jusqu'au relèvement ou au cycle suivant
   (rw_full.txt:5467-5520). La limite de l'agent Railway (0 $) bloque son usage ; elle est
   indépendante (rw_full.txt:24552-24723).
3. **Poste de commande : WSL**. Sous Windows, Railway documente sa CLI par WSL
   (rw_full.txt:16958-16974). Constaté le 25/09/2026 : ce poste n'a **aucune distribution WSL
   utilisable** (`wsl -l -v` ne montre que `docker-desktop`, réservée à Docker Desktop). À faire
   une fois :
   - installer une distribution : `wsl --install -d Ubuntu` (PowerShell en administrateur), puis
     créer l'utilisateur demandé au premier lancement ; tout ce qui suit se fait dans cette
     distribution ;
   - Node.js **≥ 22.6** (24 LTS conseillé), par exemple par le dépôt NodeSource ou par nvm :
     l'évaluation de `railway.ts` par la CLI et `verifier.mjs` passent
     `--experimental-strip-types`, apparu dans Node 22.6 (le `package.json` de `.railway/` exige
     désormais `>=22.6.0`) ; `node --version` ;
   - CLI Railway **≥ 5.42.1** (version minimale exigée par le SDK 3.11.0 : « The IaC engine now
     ships in the CLI »), installée **sans configuration d'agent** :
     `bash <(curl -fsSL railway.com/install.sh)` (« To install the CLI without agent
     configuration », rw_full.txt:16968-16972), ou `npm i -g @railway/cli@<version>` avec une
     version exacte ≥ 5.42.1 relevée par `npm view @railway/cli version` ; puis
     `railway --version`. **Interdits** (relecture P2) : `curl -fsSL agents.railway.com | sh` (la
     première commande de la page : elle lance `railway setup agent`, rw_full.txt:16958-16966),
     `railway setup agent` et `railway mcp`, qui installent la compétence Railway et le serveur MCP
     de Railway pour Claude Code et Codex **avec la session `railway login` du propriétaire**
     (rw_full.txt:23074-23092) : contraire au § 11 (aucun jeton Railway pour un agent).
     Contrôle : aucune entrée MCP « railway » (ni `mcp.railway.com`) dans les configurations
     d'agents, ni sous Windows (`claude mcp list`, section `[mcp_servers]` de
     `%USERPROFILE%\.codex\config.toml`) ni dans WSL (`~/.claude.json`, `~/.codex/config.toml`) ;
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
   **Mode opératoire** (relecture P2 : les commandes `railway ssh -i` sont lancées depuis WSL) :
   - **préféré** : les opérations SSH se font depuis l'**autre compte Windows** (sa propre
     distribution WSL, sa propre CLI, sa propre session `railway login` suivie de
     `railway logout`) ; la clé n'entre jamais dans le compte des agents ;
   - **à défaut** : le support chiffré est branché et monté dans WSL **le temps de l'opération**,
     la clé est copiée dans un répertoire en mémoire (`mkdir -m 700 /dev/shm/acp-cle` puis copie en
     0600), utilisée par `railway ssh -i /dev/shm/acp-cle/<clé>`, puis effacée
     (`rm -rf /dev/shm/acp-cle`) et le support démonté ; jamais de copie sous `~/.ssh` ni sur le
     disque du compte des agents.
5. **Docker Desktop** sous Windows, pour calculer l'empreinte du mot de passe (§ 5.1).
6. **Conditions d'utilisation de context7, lues et consignées** (relecture de P3). context7 est
   **activé par défaut** dans l'image (seul serveur MCP côté Hermes, accès anonyme, sans clé :
   [catalogue.md](catalogue.md) § 7.1) : dès la première discussion, les questions de l'agent
   partent chez Upstash, depuis l'adresse de sortie de Railway. **Personne ne les a lues** pendant
   P3, et un agent ne les interprète pas pour vous. Avant le premier déploiement : lisez-les
   (la page d'accueil de context7.com renvoie à `https://upstash.com/docs/common/help/legal`,
   relevé le 25/09/2026), vérifiez qu'elles admettent un usage anonyme, automatisé, depuis un
   hébergeur, et consignez la date, l'adresse lue et votre décision dans `docs/reprise-poste.md`.
   Si elles ne l'admettent pas, ou dans le doute : **pas de déploiement** avant une PR qui retire
   context7 du catalogue (verrou, épingles de la managed scope, liste de la plateforme cli, garde).

---

## 3. Règles de l'IaC

- **Vous seul appliquez**, depuis votre poste : ni la CI, ni un agent. Aucun jeton Railway n'est
  donné à GitHub (l'action `railwayapp/config` n'est pas utilisée).
- **Fichier de projet entier** : toute ressource omise est **supprimée** au prochain apply
  (rw_full.txt:28156) ; détacher ou supprimer un volume est destructif (rw_full.txt:28708). Aucune
  ressource n'est donc créée à la main (hors domaines générés, non gérés par l'IaC).
- `railway config apply` **toujours interactif** : jamais `--yes`, jamais `--confirm-destructive`.
  Lisez chaque ligne du plan ; toute ligne de destruction arrête l'opération, **et toute ligne de
  modification d'un volume** (montage, région, planification de sauvegarde) aussi (relecture P2 :
  « 0 to destroy » ne suffit pas, le retrait d'une planification de sauvegarde serait une
  modification, § 1).
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
   trois services et trois volumes (depuis P6), avec les réglages du § 1, sans Start Command,
   pré-déploiement, domaine ni secret ; depuis P7, toute variable dont le nom désigne un secret est
   `preserve()`, et le vérificateur s'éprouve sur trois copies altérées de `railway.ts` ;
4. `test_railway_iac_contrat.py` : chaque image démarre avec exactement les variables que le
   graphe déclare (plus celles que Railway fournit, simulées), sa santé répond 200 sur le PORT
   déclaré avec l'hôte `healthcheck.railway.app` (rw_full.txt:29964) ; `identite` refuse de
   démarrer, en français, sans les quatre variables du propriétaire ; depuis P7, Hermes démarre
   sans aucune variable du canal posée (canal « aucune »), puis avec Telegram et avec ntfy posés.
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
- **`preserve()` sur une variable qui n'existe pas encore** : **supposé** « ne rien créer » et admis
  par le plan ; la documentation ne décrit `preserve()` que pour une valeur déjà posée (« keep the
  value that is already set in Railway », rw_full.txt:28651 ; rw_full.txt:19030). Deux usages en
  dépendent :
  - **identité, au premier apply** : `identite` refuse alors de démarrer jusqu'au § 5.2 (échec fermé
    attendu, mesuré par `test_identite_refuse_sans_les_variables_du_proprietaire`). Si le plan
    **refuse** `preserve()` sur une variable absente : PR qui retire provisoirement les quatre
    `preserve()` (et les attend absentes dans `verifier.mjs`), apply, pose des quatre variables
    (§ 5.2), puis PR qui les rétablit et `railway config plan` → « already up to date » ;
  - **canal de notification (étape P7, D116), à chaque plan** : les variables du canal que vous ne
    choisissez pas ne seront **jamais** posées (les six si vous n'en choisissez aucun). L'exposition
    est permanente, pas limitée au premier apply, et le contournement ci-dessus (rétablir les
    `preserve()` une fois les valeurs posées) ne s'y applique pas : conduite au § 14.1. Au premier
    apply qui suit la fusion de P7, un refus toucherait les deux à la fois : une seule PR de repli.
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

Prérequis vérifiés (§ 2), dont le **point 6** : conditions de context7 lues et consignées.

1. Choisissez deux libellés DNS **distincts**, par exemple `acp-hermes-<6 caractères aléatoires>`
   et `acp-identite-<6 caractères aléatoires>` (a-z, 0-9, tirets ; 63 caractères au plus). Ils
   seront **figés** : les passkeys sont liées au sous-domaine exact de l'identité, et renommer un
   domaine après l'enrôlement les invalide. **Ils seront publics** (relecture P2) : le dépôt est
   public (`"visibility": "public"`) et la PR qui les écrit les publie ; l'aléa n'apporte donc
   aucun secret, seulement l'absence de collision. La sécurité repose sur l'OIDC, les passkeys et
   le bannissement, jamais sur un nom caché.
2. Branche depuis `refonte/hermes`, remplacement des deux constantes `LIBELLE_HERMES` et
   `LIBELLE_IDENTITE` de `.railway/railway.ts` et, **depuis P6, dans la même PR**, de l'origine de Hermes dans
   `executant/politique/executant.toml` (`origine = "https://<LIBELLE_HERMES>.up.railway.app"` ; un test exige
   l'égalité, et l'exécutant refuse de démarrer tant qu'elle vaut le gabarit), puis :
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
railway usage limit status            # limites du § 2.2 : les poser ici si ce n'est pas fait
railway init --name acp               # crée le projet (environnement production) et le lie
railway link --project acp --environment production
```

`railway.ts` refuse désormais d'être évalué pour un autre projet lié que `acp` (ou sans nom de
projet) : un plan lié par erreur à un autre projet y supprimerait tout ce que le fichier ne décrit
pas (relecture P2 ; refus mesuré par `verifier.mjs`). Relevez l'identifiant du projet affiché par
`railway status` et gardez-le dans le compte rendu : l'IaC ne le vérifie pas (il n'existe qu'ici).

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
- création de **3 services** (`hermes`, `identite`, `executant`) et **3 volumes** (`hermes-donnees`,
  `identite-donnees`, `executant-donnees`), **0 to destroy** ; si P2 a été appliqué avant P6, le plan de P6 n'ajoute
  que l'exécutant : **« 2 to create, 0 to destroy »** (§ 13.3) ;
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
`[acp-identite] variables validées ; utilisateur unique configuré (identifiant non journalisé) ; émetteur https://<libellé-identite>.up.railway.app ; client hermes-acp → https://<libellé-hermes>.up.railway.app/auth/callback`
(depuis la relecture P2, l'identifiant n'est plus journalisé : ces journaux vont dans un dépôt
public, § 7).

Un 503 de Hermes à la connexion **pendant que l'identité refuse de démarrer** disparaît seul dès
qu'elle est en ligne : Hermes ne garde pas une découverte OIDC échouée, il la retente à chaque
connexion (plugins/dashboard_auth/self_hosted/__init__.py:178-206 ; relecture P2 : la première
version conseillait à tort un « Redeploy »). Un 503 **persistant** alors que l'identité répond :
jeton de rafraîchissement révoqué ou rejoué, réglé par la déconnexion
([identite.md](identite.md) § 12), pas par un redéploiement.

### 4.7 Sauvegardes

Pour **chaque** service : onglet **Backups** → planifications **Daily** (gardées 6 jours) et
**Weekly** (gardées 27 jours) (rw_full.txt:32407-32420). Puis une sauvegarde **manuelle** de
chaque volume. Ces planifications ne sont **pas** dans `railway.ts` (§ 1) : le § 4.8 vérifie que le
plan ne propose pas de les retirer.

### 4.8 Contrôle de dérive

```sh
railway config pull --json > /tmp/acp-graphe.json     # JAMAIS sans --json
railway config plan --detailed-exit-code ; echo $?    # 0 exigé
```

Dans `acp-graphe.json`, relevez `checkSuites`, `builder`, `watchPatterns`, `sleepApplication`,
`restartPolicyType`, `restartPolicyMaxRetries`, `limitOverride`, la région, le répertoire racine.
Toute clé absente : réglage à la main (§ 3), consigné, puis `--detailed-exit-code` à 0.

**Sauvegardes (relecture P2)** : relevez dans `acp-graphe.json` ce que `config pull` montre des
planifications de sauvegarde, puis lancez `railway config plan --verbose`. **Si le plan montre une
modification des planifications de sauvegarde** (ou de tout autre réglage d'un volume) : **arrêt**,
aucun apply ; le code 0 exigé ci-dessus est alors inatteignable sans changer l'IaC. Une PR déclare
les planifications dans `railway.ts` (forme révélée par `railway config pull --json`, par exemple
un montage portant `backupSchedules: ["DAILY", "WEEKLY"]`, type typé par le SDK) et les attend dans
`verifier.mjs`, CI verte, **avant** tout second apply ; consignez le constat dans
`docs/reprise-poste.md`.

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

**PID 1** (non documenté par Railway ; la garde `acp-entree` refuse de démarrer sinon, voir § 10 f) :
enregistrez la clé dédiée (mode opératoire du § 2.4), puis
```sh
railway ssh keys add --key <clé dédiée>.pub --name acp-operation
railway ssh -i <clé dédiée> --service hermes -- sh -c "tr '\0' ' ' </proc/1/cmdline"
railway ssh keys remove --2fa-code <code>      # puis `railway ssh keys` : vide
```
Attendu : `/package/admin/s6/command/s6-svscan -d4 -- /run/service` (ou `s6-svscan -d4 --
/run/service`). Si `hermes` refuse de démarrer avec `[acp] REFUS : l'image n'a pas le PID 1` :
§ 10 f, sans rien contourner.

### 4.10 Enrôlement, connexions, cerveau

§ 5.3 (passkeys), connexion à `https://<libellé-hermes>.up.railway.app` depuis le PC **et** le
téléphone (captures), § 6 (openai-codex).

Exécutant (étape P6) : dépôt de preuve, enrôlement et connexions, § 13.3 bis à 13.6.

Poste Windows (étape P5, [poste.md](poste.md)) : **aucune variable Railway nouvelle**. Le poste s'enrôle
après le premier déploiement, depuis l'onglet « Poste » (code à usage unique, empreinte à recopier) ; ses
routes `/api/plugins/acp-poste/machine/v1/*` passent par le même domaine que le tableau de bord.

### 4.11 Répétition de maintenance, une fois, avant d'accumuler des données

`railway login` d'abord (le § 5.3 s'est terminé par `railway logout`), puis § 10 b sur `hermes`
(Start Command de maintenance, santé vidée, `diagnostiquer`), essai du § 10 b-bis
(`railway volume files` sur un service arrêté), retour à la normale, puis
`railway config plan --detailed-exit-code` → 0. Compte rendu écrit.

### 4.11 bis Répétition de restauration, une fois, avant d'y mettre des données

Étape P9 : à la suite du § 4.11, restauration des trois volumes à une sauvegarde manuelle, en douze étapes, avec les
constats à relever (openai-codex, sessions, sauvegardes postérieures) : [exploitation.md](../exploitation.md) § 5.

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
[identite.md](identite.md) § 4) ; les rafraîchissements sont silencieux. Reconnexion exigée après
**7 jours sans rafraîchissement** (jeton de rafraîchissement de 7 jours chez Authelia) : fenêtre
**supposée glissante, non mesurée** ([identite.md](identite.md) § 12) — chaque rotation émettrait
un jeton neuf de 7 jours, donc une session active peut durer plus longtemps. Côté Hermes, le cookie
du jeton de rafraîchissement vit 30 jours (hermes_cli/dashboard_auth/cookies.py:38) : la borne de
7 jours ne vient que d'Authelia (relecture P2 : la première version disait « au plus 7 jours »).

### 5.4 Secours

Toutes ces opérations se font **en maintenance** (§ 10 b sur `identite`) et avec
`/opt/acp-identite/acp-identite-admin` (sous-commandes `user …` et `bans …` d'`authelia storage`
seulement ; il relit l'environnement du PID 1, jamais celui de la session) :

- **Mot de passe perdu** : nouvelle empreinte (§ 5.1), édition de la variable scellée, « Deploy ».
  **Ensuite, jamais de Rollback ni de « Redeploy » d'un déploiement d'`identite` antérieur au
  changement** (relecture P2) : un Rollback restaure l'image **et les variables** du déploiement
  visé (rw_full.txt:29547-29548 ; 4944), donc l'**ancienne empreinte** scellée, et remettrait en
  service un mot de passe compromis. Même règle après tout changement d'une variable d'identité.
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

1. Connecté au tableau de bord Hermes : **Clés** (« Keys » si l'interface est en anglais) →
   **Connexions fournisseurs (OAuth)** → `openai-codex` → **Connexion** (« Login ») : Hermes
   affiche un **code d'appareil** et l'adresse où le saisir (routes
   `/api/providers/oauth/openai-codex/start` puis `…/poll/…`).
2. Ouvrez l'adresse avec **votre** compte ChatGPT et saisissez le code. Si OpenAI refuse (« device-code
   authorization » non activée), activez l'autorisation par code d'appareil dans les paramètres de
   votre compte OpenAI, puis recommencez (message prévu par Hermes,
   `hermes_cli/web_routers/oauth.py:68-85`).
3. **Modèles** (« Models ») : choisissez le modèle par défaut.
4. Discussion : « Exécute `id` dans un terminal » → **refus attendu** : l'agent n'a aucun outil
   d'exécution sur Railway ([image.md](image.md) § 5).

Les jetons (tournants) vivent dans `/opt/data` : ils sont dans les sauvegardes du volume ; une
restauration impose **probablement** de reconnecter openai-codex (supposé, jamais constaté : constat c de la
répétition, [exploitation.md](../exploitation.md) § 5).

---

## 7. Preuves à relever sur Railway

À transmettre sans aucun secret ; elles vont dans `docs/reprise-poste.md`. **Le dépôt est public**
(relecture P2) : dans tout journal ou toute capture versés au dépôt, **masquez l'identifiant et
l'adresse** du propriétaire (et le nom affiché), par exemple `<identifiant>` : un tiers qui connaît
l'identifiant peut vous bannir 15 minutes à volonté (§ 5.4). La garde d'`identite` ne journalise
plus l'identifiant ; Authelia, lui, peut le journaliser lors d'une tentative de connexion.

1. `railway config plan --verbose` avant l'apply (« 0 to destroy ») ; `railway config pull --json`
   après, avec les clés du § 3 ; sinon réglage manuel et `plan --detailed-exit-code` = 0.
2. Pour **chaque** déploiement : `gh run list --workflow image.yml --commit <RAILWAY_GIT_COMMIT_SHA>`
   **et** `gh run list --workflow ci.yml --commit <RAILWAY_GIT_COMMIT_SHA>` → `success` (le SHA est
   dans `[acp] commit déployé : …` et dans le bloc `deploiement` de
   `/api/plugins/acp-poste/v1/meta`).
3. Journal de construction : les deux condensats ; constructeur Dockerfile.
4. Journaux de démarrage (§ 4.9) ; `[acp-identite] … utilisateur unique configuré (identifiant non
   journalisé) …` ; identifiant et adresse masqués partout ailleurs.
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
15. Étape P3 : l'onglet **Catalogue** (16 skills d'ACP « Active », 10 « Candidate pour le poste, non planifiée ») et
    l'Accueil (16 / 16) ; après une première discussion, context7 « Connecté » ; une question qui
    appelle la documentation d'une bibliothèque, avec la source citée ; une réponse **en français**
    du vrai modèle à une question posée en anglais. Aucun refus « serveur MCP » dans les journaux
    de démarrage.
16. Étape P4 : `/api/plugins/acp-poste/v1/meta` → bloc `projets` (`base: ok`, `schema: "1"`,
    `emetteur.processus: "passerelle"` avec une `derniere_passe` récente, aucune alerte) ; un projet
    **sans dépôt** lancé depuis le téléphone (page Projets), suivi jusqu'à « terminé » depuis le PC ; un
    projet **sur dépôt** refusé en français tant que le poste n'a publié aucun inventaire (P5) ; si un
    canal est configuré (§ 9), la notification de test reçue sur le téléphone. Coût et mémoire relevés
    pendant le projet (2 workers au plus).

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
  Après la relance réussie d'un workflow, le déploiement sauté n'est pas refait seul. Depuis la
  relecture P2, `ci.yml` a lui aussi, hors PR, un groupe de concurrence **par exécution** : un push
  n'annule plus le run `ci.yml` du commit précédent (avant, `cancel-in-progress: true` l'annulait,
  et Railway pouvait déployer ce commit sans verdict de `ci.yml` dès qu'`image.yml` avait réussi).
  Le § 7 point 2 vérifie les deux workflows.
- Pour relancer : **« Redeploy »** d'un déploiement déjà prouvé (même code et même configuration,
  rw_full.txt:52320-52330). **« Deploy Latest Commit »** seulement après
  `gh run list --workflow image.yml --commit <sha de tête>` → `success` : la doc dit tantôt qu'il
  déploie la branche connectée (rw_full.txt:29653), tantôt la branche par défaut du dépôt
  (rw_full.txt:29564, 52330) ; vérifiez le SHA déployé dans le journal.
- **Rollback** : restaure l'image et les variables d'un déploiement précédent
  (rw_full.txt:29547-29548) ; la doc ne dit rien du volume, qui reste celui du service (supposé) :
  des données écrites par une version plus récente peuvent ne pas être relues par l'ancienne.
  Deux avertissements (relecture P2) : un Rollback d'`identite` restaure aussi l'**empreinte
  scellée** du mot de passe (interdit à travers un changement de mot de passe, § 5.4) ; sur
  **Hobby**, l'image d'un déploiement retiré n'est gardée que **72 heures** (rw_full.txt:4938) ;
  au-delà, plus de Rollback : « Redeploy » reconstruit depuis la source avec les **variables
  d'origine** de ce déploiement (rw_full.txt:4944-4946), mêmes réserves.
  Troisième avertissement (relecture finale de P7, D121) : depuis P7, **chaque démarrage** de `hermes` dépose
  `/opt/data/scripts/acp-bilan.py` sur le volume, même si le bilan n'a jamais été créé. Une image **antérieure à P7**
  refuse alors de démarrer (« /opt/data/scripts n'est pas vide (« acp-bilan.py ») », code 1, échec fermé : rien
  n'est perdu). Avant un Rollback ou un « Redeploy » de `hermes` vers un déploiement d'avant P7 : supprimez d'abord
  la tâche du bilan si elle existe (page Cron, P7 encore en service), puis passez en maintenance (§ 10 b, points 1 à
  4), retirez `/opt/data/scripts/acp-bilan.py`, et seulement alors faites le Rollback, au lieu du « Retour » du
  point 6 (qui redéploierait P7 et redéposerait le fichier) ; Start Command effacée et chemin de santé rétabli comme
  au point 6, puis vérifiez au journal que l'image démarrée est bien celle visée (que le Rollback garde ou non ces
  réglages du service n'est pas documenté : supposé gardés). Même conduite entre deux versions de P7 si le script a
  changé entre elles : `EMPREINTES_BILAN_ADMISES` (`hermes/image/acp_demarrage.py`) ne connaît que les empreintes
  livrées jusqu'à l'image démarrée (montée de version seulement).
- Chaque déploiement : preuve du § 7 point 2.

**Sauvegardes.** Quotidienne (6 jours) et hebdomadaire (27 jours), plus une manuelle avant toute
maintenance. Limites (rw_full.txt:32452-32464) : une sauvegarde manuelle est limitée à 50 % de la
taille du volume ; **effacer un volume efface ses sauvegardes** ; restauration dans le même projet
et le même environnement seulement. Les sauvegardes d'`identite` contiennent ses secrets et sa clé
de signature ; celles de `hermes` contiennent `auth.json` (jetons openai-codex) : la frontière de
confiance est le compte Railway (§ 11). Contenu de chaque volume, export chiffré de Hermes, pertes au pire et
calendrier : [exploitation.md](../exploitation.md) § 1 à 3.

**Coûts** (Hobby : 5 $ déduits de l'usage, RAM 10 $/Go/mois, CPU 20 $/vCPU/mois, volume 0,15 $/Go/mois,
sortie 0,05 $/Go ; seul l'usage réel est facturé, rw_full.txt:4848-4892) :
- usage normal **estimé**, trois services (depuis P6) : `hermes` et `identite` 6 à 16 $/mois (Hermes mesuré à
  415-440 Mio au repos, Authelia ~0,1 Gio) ; `executant` ≈ 2,6 $ au repos et jusqu'à ≈ 16 $ avec la garde de la
  politique (8 h d'agent et 20 cartes par jour ; **supposé**, aucune mesure de Codex ni de Claude, R8 tranche,
  [executant.md](executant.md) § 9) ; **total ≈ 9 à 32 $** ;
- pire cas **théorique** aux limites : Hermes 2 × 10 + 1 × 20 = 40 $ ; identite 2,5 × 10 + 0,5 × 20
  = 35 $ ; executant 2 × 20 + 4 Gio (≈ 4,3 Go) × 10 + 5 Go × 0,15 ≈ 84 $ ; **total ≈ 159 $** ;
- la limite dure de **30 $ coupe tout avant**, identité comprise ; le **haut** de l'estimation (≈ 32 $) la
  **dépasse** : tout serait éteint avant la fin du mois. D'où l'alerte à 15 $, le relevé hebdomadaire
  (`railway usage` et `railway usage projects --project acp`) et la réévaluation datée du § 13.6 (D85).

**Montée de version de Hermes ou d'Authelia** : PR qui change le `FROM` épinglé (et
`hermes/contrat/`), CI verte, déploiement par la chaîne normale. Jamais `hermes update`, `:latest`
ni `AUTO_UPDATE`. Étape P9 : veille mensuelle et PR de montée par `scripts/monter_hermes.py`, vos gestes, point
de non-retour et retour arrière (Rollback ne restaure pas le volume, supposé) :
[exploitation.md](../exploitation.md) § 6.

**Page MCP du tableau de bord** (relecture de P3) : n'y utilisez ni « INSTALL » ni « ADD SERVER » :
un serveur MCP s'ajoute par une PR au catalogue ([catalogue.md](catalogue.md) § 7.3). Un serveur
ajouté par erreur fait **refuser** le démarrage suivant et toute relance (D8) : supprimez-le
depuis la même page **avant** tout redémarrage (la bannière d'alerte le nomme) ; le désactiver ne
suffit pas. S'il a déjà provoqué un refus : § 10 b.

**Modifier l'infrastructure** : PR sur `.railway/railway.ts` (et `verifier.mjs` si le graphe attendu
change), CI verte, fusion, puis plan (« 0 to destroy » sauf décision écrite) et apply par vous.

**Notifications du propriétaire (étape P4 ; variables déclarées depuis P7 ; facultatif)**
([projets.md](projets.md) § 5, [questions.md](questions.md) § 8). Sans rien poser, elles restent **désactivées** : la
page Projets dit « Notifications non configurées » et les notifications sont gardées en base, marquées `desactivee`,
jamais envoyées. Canal recommandé : Telegram (plan d'autonomie § 11.3) ; ntfy possible. Pour l'activer :

1. **Pas avant la fusion de P7.** Le fichier de l'IaC décrit le projet entier : une variable posée dans Railway mais
   absente de `.railway/railway.ts` apparaîtrait au plan suivant comme une **suppression** (rw_full.txt:28377), qui
   arrête la procédure (§ 3). En P4, aucune n'y était déclarée (canal non choisi). **Depuis P7**, la PR qui les déclare
   est faite : les six variables du canal, Telegram et ntfy, `ACP_NOTIFICATIONS` comprise, sont déclarées par
   `preserve()` dans le service `hermes` (jamais leur valeur, D116) ; le choix du canal ne demande plus de PR.
2. Posez les valeurs du canal choisi dans Railway (jeton en variable **scellée**) : marche à suivre au § 14.2
   (Telegram) ou au § 14.3 (ntfy) ; puis plan (« 0 to destroy ») et apply (§ 14.4). `preserve()` sur une variable
   jamais posée (celles de l'autre canal) n'est que **supposé** sans effet : conduite à tenir au § 14.1.
3. Au démarrage, une valeur invalide fait **refuser** le démarrage en français (`[acp] REFUS : …`, règles :
   [image.md](image.md) § 4). Page Projets ou Accueil → « Envoyer une notification de test » : la passerelle
   l'envoie par son fil d'envoi, réveillé toutes les 30 s (moins d'une minute en pratique) ; `/api/plugins/acp-poste/v1/meta` → `projets.emetteur`
   (`canal`, `configure`, `envoyees`, `echecs`).

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
4. Session root, avec la clé dédiée (§ 11, mode opératoire du § 2.4), après `railway login` si la
   CLI n'est pas connectée :
   ```sh
   railway ssh keys add --key <clé dédiée>.pub --name acp-maintenance
   railway ssh -i <clé dédiée> --service hermes
   /opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py diagnostiquer
   ```
   `diagnostiquer` est en lecture seule ; il lit l'environnement du PID 1 (`/proc/1/environ`),
   jamais celui de la session `railway ssh`, dont la doc ne dit rien ; il liste variables
   interdites, `hooks/`, `scripts/`, clés exécutables de `config.yaml` (dont, depuis P3, tout serveur
   MCP stdio ou hors catalogue, qui refuse le démarrage : décision D8), `lazy-packages` (code 1 si
   un constat existe). Pour `identite` : `/opt/acp-identite/acp-identite-admin …` (§ 5.4).
5. **Correction** : retirez ce qui est signalé, en consignant ce qui a été retiré. Exception : `acp-bilan.py` dans
   `/opt/data/scripts/` est déposé par l'image depuis P7 et admis par son empreinte ; ne le retirez que pour revenir
   à une image antérieure à P7 (§ 9, Rollback) — sinon le démarrage suivant le redépose. Un serveur MCP
   ajouté depuis la page MCP native (« INSTALL », « ADD SERVER ») se retire en supprimant son
   entrée `mcp_servers.<nom>` de `/opt/data/config.yaml` (jamais l'entrée `context7`, rétablie de
   toute façon au démarrage) ; tant que le service tourne encore, la suppression depuis la page MCP
   évite cette maintenance (§ 9).
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
(rw_full.txt:32438) ; une autre page de la documentation dit au contraire que la restauration les supprime
(rw_full.txt:42610) : ne supprimez jamais l'ancien volume avant validation (constat g de la répétition). Plusieurs
volumes, ordre entre eux (exécutant et Hermes restaurés à des instants différents), effets à la reprise et
reconnexions : [exploitation.md](../exploitation.md) § 4.

### e) Identité

§ 5.4.

### f) Refus PID 1 (relecture P2)

Si `hermes` refuse de démarrer avec
`[acp] REFUS : l'image n'a pas le PID 1 (processus N) …` puis
`[acp] Démarrage arrêté (échec fermé). Sur Railway, la plateforme n'a pas donné le PID 1 à l'image …`
(ce second message ne s'affiche qu'en présence des variables `RAILWAY_*` ; hors Railway, il
conseille de retirer `--init`) :
1. **arrêt** : ne rien contourner. Pas de Start Command (elle remplace l'ENTRYPOINT, donc toutes les
   gardes), pas de variable, pas de retrait d'`acp-entree` ;
2. relevez le journal complet du déploiement (`railway logs --service hermes --latest --lines 200`)
   et consignez-le, identifiant masqué ;
3. laissez le service **hors ligne** (échec fermé) : relances comprises, il refusera de même ;
   `identite` peut rester en ligne ;
4. la suite est une **décision de conception**, prise par une PR (par exemple : lancer s6-overlay
   autrement, avec une nouvelle preuve que les gardes s'appliquent), relue et testée comme P2,
   jamais un réglage fait dans Railway.

### g) Hermes depuis son propre export (étape P9)

Volume de Hermes effacé avec ses sauvegardes : réimport de l'export chiffré de la station Qt dans un volume vide.
Forme du geste mesurée par le test de restauration de P9 (R4 : racine du volume rendue à l'utilisateur de Hermes avant
l'import, sortie contrôlée, script du bilan importé supprimé) ; déroulé et messages de Hermes à ignorer :
[exploitation.md](../exploitation.md) § 4.5.

---

## 11. Sécurité du compte Railway

Le compte Railway est la **frontière de confiance** : il donne accès aux volumes (jetons
openai-codex, secrets et clé de signature d'Authelia), aux variables et aux shells root.

- **Clé SSH dédiée** ed25519 avec phrase de passe, rangée hors du compte Windows des agents, et
  utilisée selon le mode opératoire du § 2.4 (autre compte, ou copie en mémoire effacée après usage).
  Enregistrement : `railway ssh keys add --key <clé dédiée>.pub --name acp-operation`.
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
  (`verifier.mjs`) : gabarits, libellés invalides ou identiques, autre environnement, autre projet
  lié ou projet lié inconnu (relecture P2) → refus en français ; graphe d'essai conforme (2 services, 2 volumes, Wait for CI, Dockerfile, santé,
  région, limites, redémarrage, Serverless coupé, `preserve()`, aucune Start Command). Chaque
  réglage retiré ou altéré dans une copie (Start Command ajoutée, garde des gabarits retirée,
  Serverless, volume omis, empreinte en clair, domaine personnalisé, Wait for CI coupé) fait
  échouer le vérificateur.
- **Contrôle statique** (`scripts/tests/test_railway_iac.py`, 42 tests depuis la relecture P2) :
  SDK isolé et épinglé, verrou haché, aucune Start Command, réglages, gabarits et garde, garde du
  projet lié, aucun secret, cohérence avec les images, aucun fichier Config as Code, CI (`ci.yml`
  sans annulation hors PR, étape finale d'`image.yml` en échec s'il reste des ressources de test).
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
   identifiant de région ; forme du répertoire racine ; `ctx.projectName` fourni par la CLI (son
   absence fait refuser : échec fermé) ; comportement du moteur face aux planifications de
   sauvegarde posées à la main et absentes de `railway.ts` (§ 4.8).
4. Environnement et utilisateur d'une session `railway ssh` ; `railway volume files` sur un service
   arrêté.
5. **Restauration** : mise en attente combinable avec une Start Command dans le même lot ; renommage
   des volumes avec un plan à « 0 to destroy » ; sort des sauvegardes postérieures (documentation
   contradictoire, § 10 d) ; reconnexion d'openai-codex. Tous relevés par la répétition du § 4.11 bis.
6. **Déploiements hors automatisme** : « Deploy Latest Commit » et premier déploiement créé par
   l'apply face à « Wait for CI ».
7. « Wait for CI » avec les workflows réels et des groupes de concurrence par exécution.
8. **Réseau** : adresse du bord, en-têtes `X-Forwarded-*`, `trusted_proxies` ; émetteur d'Authelia à
   travers le vrai bord ; NTP sortant (Authelia vérifie l'horloge au démarrage).
9. Effet du mode « under attack » sur les appels de Hermes vers l'identité (supposé bloquant).
10. Santé, drainage, redémarrages, sauvegardes sur Hobby, consommation et coût réels.
11. Connexion depuis le téléphone ; openai-codex par code d'appareil ; premier tour réel.
12. Disponibilité des libellés choisis (`railway domain update … --domain`).
13. Installation de la CLI sans configuration d'agent et absence d'entrée MCP « railway » (§ 2.3).

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
- Les libellés des sous-domaines sont publics (dépôt public) ; seul le masquage de l'identifiant
  dans les journaux versés au dépôt protège contre le bannissement ciblé (§ 7).
- L'identifiant du projet Railway n'est pas vérifié par l'IaC (seul son nom l'est) : la lecture de
  chaque ligne du plan reste obligatoire.

---

## 13. Exécutant (étape P6)

Conception, preuves et limites : [executant.md](executant.md). Décisions appliquées : D74 à D92 ([plan.md](plan.md)).
Vous fournissez les comptes ; Hermes gère l'exploitation (cartes, voies, modèles, gardes). Rien de ce qui suit n'a été
exécuté : chaque étape est **votre** geste.

### 13.1 Ce qui est ajouté

| | `executant` |
|---|---|
| Rôle | client `apps/poste` en mode Linux ; Codex CLI 0.156.1 (UID 10001) et Claude Code 2.1.283 (UID 10002) ; vérification sous l'UID 10003 |
| Source | GitHub, branche `refonte/hermes`, **racine `/`** (l'image embarque `apps/poste` et le contrat), « Wait for CI » |
| Dockerfile | `RAILWAY_DOCKERFILE_PATH=executant/Dockerfile` (relatif à la racine : supposé, prouvé au premier build) |
| Motifs surveillés | `/executant/**`, `/apps/poste/src/**`, `/packaging/poste/lancer.py`, `/hermes/plugins/acp-poste/contrat/**`, `/requirements/poste-3.12.lock.txt`, sauf `/executant/tests/**` et `/executant/factice/**` |
| Volume | `executant-donnees` sur `/donnees` (5 Go, maximum de l'offre Hobby) |
| Port, domaine, santé | **aucun** (Railway le marque Active dès le démarrage) |
| Limites | 2 vCPU, 4 Gio ; une carte à la fois ; 8 h d'agent et 20 cartes par jour (politique) |
| Redémarrage | `ON_FAILURE`, 10 relances ; l'exécutant ne sort **jamais** en 0 (non enrôlé ou révoqué : il attend) |
| Arrêt | `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=90` : arrêt de l'agent, commit « wip », `arret(sigterm)` |
| Variables | les deux ci-dessus ; **aucun secret** : jetons déposés sur le volume (§ 13.5) |

### 13.2 Sonde R0 (projet jetable `acp-sonde`)

**Avant tout apply** et sans aucun identifiant (D88). Elle mesure si le conteneur Railway permet les espaces de noms
utilisateur (bubblewrap, régime A) ou non (régime B, probable), et si la séparation par UID tient. Coût : quelques
minutes de conteneur. Le projet `acp-sonde` est **distinct** de `acp` (l'IaC décrit `acp` en entier).

1. Commit à sonder, dans un **clone propre** (jamais le dossier principal, sale) : le **dernier commit qui touche
   l'image de l'exécutant**. `executant.yml` ne tourne que pour ces chemins (un commit de documentation seule, comme
   la pointe de P6, n'a aucun run) ; ce workflow doit y être **vert** :
   ```sh
   git clone https://github.com/Paul-Berdier/agent-company-platform.git acp-sonde-r0
   cd acp-sonde-r0 && git checkout refonte/hermes
   sha="$(git log -1 --format=%H -- executant apps/poste hermes/plugins/acp-poste/contrat packaging/poste/lancer.py \
          requirements/poste-3.12.lock.txt requirements/python-3.12.lock.txt pytest.ini .github/workflows/executant.yml)"
   git checkout "$sha"
   gh run list --workflow executant.yml --commit "$sha"     # « success » exigé ; liste vide : mauvais commit
   ```
2. Projet et service, depuis la **racine** du clone (`railway up` téléverse le dossier courant) :
   ```sh
   railway login
   railway init --name acp-sonde
   railway add --service sonde --variables "RAILWAY_DOCKERFILE_PATH=executant/Dockerfile"
   ```
3. Dans le tableau de bord, service `sonde` → **Settings** :
   - **Region** : EU West (Amsterdam), comme `acp` ;
   - **Custom Start Command** : `/usr/local/bin/acp-poste sonde-plateforme --json` (elle remplace l'ENTRYPOINT :
     la sonde tourne en PID 1, root, sans `tini` ni l'entrée, qui refuserait sans `/donnees`) ;
   - **Restart Policy** : *Never* (une sortie 0 donne « Completed ») ;
   - ni volume, ni domaine, ni autre variable.
4. Déploiement et relevé :
   ```sh
   railway up --service sonde --detach
   railway logs --service sonde --build        # « [acp] Codex 0.156.1 vérifié », « [acp] Claude Code 2.1.283 vérifié … »
   railway logs --service sonde > releve-r0.txt
   python scripts/verifier_releve_r0.py releve-r0.txt --sortie docs/refonte/preuves/r0-sonde.json
   ```
   Le contrôleur refuse un relevé tronqué, retouché (verdict incohérent avec ses mesures) ou qui porterait un
   identifiant ; sinon il affiche le verdict et écrit le relevé à publier. Si `railway logs` mêle d'autres lignes,
   copiez le bloc JSON depuis le tableau de bord (Deployments → View logs) dans `releve-r0.txt`.
5. Suppression : `railway delete --project acp-sonde` (confirmation, code de double authentification), puis
   `railway logout`. Remettez `docs/refonte/preuves/r0-sonde.json` (aucun secret) pour qu'il soit publié par une PR.

Lecture du verdict : **B** ⇒ D79 s'applique d'elle-même (voie Codex fermée sur l'exécutant, Claude seul en écriture,
relecture de repli par un autre modèle, D91) ; **A** ⇒ la voie Codex s'ouvrira après vos connexions (§ 13.5).
`uid_separes: false` ⇒ **aucune écriture** : arrêtez et transmettez le relevé.

### 13.3 Plan et apply

La CLI doit être connectée et liée au projet `acp` (le § 13.2 s'est terminé par `railway logout` ; une autre
session Windows, § 2.4, n'est liée à rien) :
```sh
railway login
railway link --project acp --environment production
```
Après la fusion de P6 dans `refonte/hermes` (CI verte : `ci.yml`, `image.yml`, `executant.yml`), selon le § 4.3 :
le plan doit afficher le service `executant` et le volume `executant-donnees`, **0 to destroy** (« 2 to create » si
P2 est déjà appliqué). Après `railway config apply` :
- build : les lignes « [acp] … vérifié » de `verifier-binaires` (une empreinte ou une signature fausse fait échouer le
  build, en français) ;
- démarrage, dans les journaux du service : `[acp] commit déployé : <sha>`, `[acp] volume prêt (/donnees)`,
  `[acp] Sonde de plateforme : régime A|B, …` (le régime mesuré à ce démarrage), puis
  `[acp] Exécutant non enrôlé : …` : il **attend l'enrôlement** sans sortir (cette ligne revient une fois par jour) ;
  s'il refuse (`executant.toml : … gabarit …`), l'origine de Hermes n'a pas été écrite dans la politique (§ 4.1). Le
  journal détaillé reste sur le volume : `railway ssh --service executant -- acp-poste journal` ;
- R1 (preuve) : `railway config pull --json` conforme ; aucune socket à l'écoute (§ 13.5, `diagnostic --isolement`).

### 13.3 bis Dépôt de preuve jetable et privé (D87)

Avant les connexions (le jeton GitHub du § 13.5 se limite à ce dépôt) :
1. sur GitHub, créez un dépôt **privé**, jetable (rien de précieux), avec une branche `main` et une petite suite de
   tests que l'image sait lancer sans rien installer : `tests/test_exemple.py` lu par
   `python3.12 -m unittest discover -s tests -q` (outils de l'image : § 13.6) ;
2. créez un jeton GitHub **à portée fine** : ce seul dépôt, permission `Contents: read` et rien d'autre,
   **expiration datée** (notez la date : son renouvellement est un geste du § 13.8) ;
3. gardez le jeton pour le § 13.5 (il n'est collé que dans la session `railway ssh`, jamais ailleurs).

### 13.4 Enrôlement, dans une session `railway ssh`

1. Si le poste Windows est actif : révoquez-le d'abord sur la page Poste (une seule machine active, D77).
2. Page Poste → **Enrôler un poste** : code à usage unique (10 min).
3. CLI connectée et liée (`railway login`, puis `railway link --project acp --environment production`, comme au
   § 13.3), clé SSH dédiée (§ 11) : `railway ssh keys add --key <clé dédiée>.pub --name acp-operation`, puis
   `railway ssh -i <clé dédiée> --service executant` (jamais `--session` : Railway installerait tmux).
4. Dans la session : `acp-poste enroler` (code en saisie masquée) → « Poste enrôlé (<machine>). Empreinte :
   XXXX-XXXX » → recopiez l'empreinte sur la page Poste et **Confirmez**.

### 13.5 Connexions : Claude, GitHub, Codex (même session)

```sh
acp-poste pause                       # aucune sonde ni carte pendant les connexions
acp-poste connexion claude            # jeton de « claude setup-token » (lancé sur votre PC), saisie masquée
acp-poste connexion github            # jeton du § 13.3 bis : ce seul dépôt, Contents: read, expiration datée
acp-poste connexion codex             # code d'appareil : lien et code affichés ICI, à saisir sur votre téléphone
acp-poste reprise
# attendre une à deux minutes : le relevé suivant (repoussé pendant la pause) lit la nouvelle connexion Codex
acp-poste diagnostic                  # jetons « present », versions conformes, régime, connexion Codex
acp-poste diagnostic --isolement      # « executant.sockets_a_l_ecoute » vaut 0 (le bloc « isolement » vaut null
                                      # sous Linux : il ne concerne que les profils du poste Windows)
exit
```
- Ces commandes tournent en root dans la session, mais lancent Codex et Claude **sous leur UID**, comme le service
  (relecture de P6) : elles ne laissent aucun fichier de root dans `/donnees/codex` ni `/donnees/claude`.
- Avant `connexion codex` : activez la connexion par code d'appareil dans les réglages de sécurité de votre compte
  ChatGPT. Le code ne transite **jamais** par Hermes ; `auth.json` est écrit sous `acp-codex` (0600, stockage
  `file`), jamais copié depuis le PC.
- Chaque jeton est écrit de façon atomique en `root 0600` sous `/donnees/acp/secrets/` ; seule son empreinte courte
  est affichée ; aucun redémarrage. Effacez ensuite le presse-papiers de Windows (et son historique, Win+V).
- Clôture : `railway ssh keys remove --2fa-code <code>` (preuve : `railway ssh keys` vide), puis `railway logout`.

### 13.6 Routage, budget, premier projet

- Page Routage : acceptez le relevé Codex (D58) si la voie est ouverte ; validez la table, y compris la classe
  « relecture » (repli D91). La classe « intégration » n'y figure pas (aucun modèle).
- Railway : alerte d'usage à **15 $**, limite dure gardée à **30 $**. Le **haut** de l'estimation à trois services
  (≈ 32 $ par mois avec la garde de 8 h d'agent par jour, § 9) **dépasse** cette limite, qui éteint **tout**,
  Hermes et l'identité compris. Étapes datées (D85), à partir du jour du premier projet (J) : relevé
  `railway usage` à J+7, J+14, J+21 et J+28 ; à **J+7**, réévaluation : si la projection du mois dépasse 30 $,
  baissez `heures_agent_par_jour` ou `cartes_par_jour` par une PR sur `executant.toml`, ou relevez la limite dure
  (votre décision, consignée dans `plan.md`).
- Dépôt de preuve **jetable et privé** (§ 13.3 bis) : ajoutez-le à `executant/politique/executant.toml`
  (`[depots.<alias>]`, forme commentée dans le fichier, éprouvée dans l'image) par une PR, CI verte, puis lancez un
  projet depuis le téléphone (R5).
- **Outils de l'image** pour `preparation` et `verification` : `python3.12` (avec `pip`, `venv`, `unittest`),
  `git`, `sh`, `bash` et les outils de base. **Ni `uv`, ni `pytest`, ni `node` ou `npm`** : une commande absente
  rend le code 127, que la carte annonce « Vérification impossible (outil introuvable sur l'exécutant) », sans
  relancer l'agent. Une dépendance peut être installée par la préparation (réseau ouvert, hors bac à sable), par
  exemple `python3.12 -m pip install --user --require-hashes -r requirements-dev.txt` : forme **non éprouvée** ici
  (aucun téléchargement hors construction de l'image). Les fichiers non suivis qu'une vérification laisse dans le
  worktree sont committés avec la carte s'ils ne sont pas ignorés par le `.gitignore` du dépôt (limite dite).

### 13.7 Récupérer une branche prête (`git bundle`, aucun push)

La page Poste (« Branches prêtes ») affiche la commande. Depuis votre PC, CLI connectée et liée (`railway login`,
`railway link --project acp --environment production`), avec la clé dédiée enregistrée :
```sh
railway ssh -i <clé dédiée> --service executant -- acp-poste bundle <alias> hermes/projet-<slug>
scp -i <clé dédiée> <identifiant d'instance>@ssh.railway.com:/donnees/acp/bundles/<fichier> .
git bundle verify <fichier>
git fetch <fichier> hermes/projet-<slug>:hermes/projet-<slug>
```
L'identifiant d'instance se copie dans la palette de commandes (« Copy Service Instance ID ») ; OpenSSH 9.0 ou plus
(sinon `scp -s`). Comparez la tête avec celle de l'onglet Poste, puis poussez, ouvrez la PR et fusionnez **vous-même**.
Retirez la clé ensuite (§ 11).

### 13.8 Exploitation

- **Pause** : `acp-poste pause` / `reprise` (session `railway ssh`), ou la pause générale de la page Projets.
- **Révocation** (page Poste) : le jeton est effacé, l'exécutant reste Active en attente d'enrôlement, sans requête
  vers Hermes ; aucune notification « hors ligne » ne suit.
- **Ce que l'exécutant fait seul** (aucun geste) : purge du disque une fois par jour, hors carte — worktrees sans
  activité depuis `purge_apres_jours` (7 jours ; leurs **branches** restent, une carte reprise recrée son worktree),
  bundles et requêtes refusées plus anciens (journal : « Purge du disque : … ») ; échéance estimée du jeton Claude
  publiée à Hermes, qui l'annonce sur la page Poste **30 jours avant** (et l'exécutant dans ses journaux, chaque
  jour) ; alias temporaires de Codex retirés au démarrage.
- **Espace disque** : sous `seuil_libre_mio` (1 024 Mio), l'exécutant cesse de réclamer des cartes (page Poste :
  « Espace libre du volume sous le seuil »). La purge quotidienne y pourvoit d'ordinaire ; sinon, dans une session
  `railway ssh` : `du -sh /donnees/* /donnees/acp/*` pour voir ; on peut retirer sans risque les bundles
  (`/donnees/acp/bundles/*.bundle`, rapatriés ou non), les requêtes refusées (`/donnees/acp/sortie/refusees/`) et
  un worktree d'une carte qui n'est **pas** en main (`acp-poste cartes`), par
  `git --git-dir=/donnees/depots/<alias>.git worktree remove --force /donnees/espaces/<alias>/<carte>` (la branche
  reste). Jamais `/donnees/codex`, `/donnees/claude`, `/donnees/acp/secrets` ni `/donnees/acp/etat`. Les
  historiques des CLI (`/donnees/codex/sessions`, `/donnees/claude/projects`) ne sont pas purgés (limite dite).
- **Jetons à renouveler** :
  - **Claude** (`claude setup-token` : valable un an) : à l'alerte de la page Poste, relancez
    `claude setup-token` sur votre PC, puis, dans une session `railway ssh`, `acp-poste connexion claude --stdin`
    (empreinte affichée, aucun redémarrage) ;
  - **GitHub** (expiration choisie au § 13.3 bis) : avant cette date, créez-en un nouveau aux mêmes droits, puis
    `acp-poste connexion github --stdin`. Expiré, la récupération du dépôt échoue et la carte est bloquée
    (« Opération git en échec ») ;
  - **Codex** (session ChatGPT, rafraîchie par Codex lui-même) : si la page Poste dit la connexion Codex perdue,
    `acp-poste pause`, `acp-poste connexion codex`, `acp-poste reprise`.
- **Exécutant indisponible, Hermes joignable** (déploiement de l'exécutant en échec, volume à restaurer) : pause
  générale, attendre la fin de la carte en cours, révoquer l'exécutant, réactiver la tâche du poste Windows, puis,
  dans la console `runas` du compte du poste (D68),
  `& 'C:\Program Files\ACP\poste\acp-poste.cmd' enroler --remplacer`, confirmer, reprise. **En P6, cette bascule
  ne rend aucune exécution** : le PC n'exécute aucune carte (il annonce `peut_executer: false`) ; elle garde
  seulement les relevés et la présence. Si **Railway** est en panne, Hermes et l'identité le sont aussi : aucune
  bascule n'est possible ni utile, on attend le retour de Railway.
- **Redéploiement** : SIGTERM, arrêt de l'agent, commit « wip », `arret(sigterm)` ; au redémarrage, la sonde est
  rejouée et la carte en main reprise (`reprendre`).
- **Refus au démarrage** (`[acp] REFUS : … dans /donnees/codex …` ou `/donnees/claude`, service « Crashed » après dix
  relances) : le conteneur ne démarre pas, donc aucune session `railway ssh` n'est possible dans cet état. Les
  commandes `acp-poste` de ce document lancent Codex et Claude sous leur UID, jamais en root, et l'entrée retire
  elle-même les alias temporaires que Codex laisse sous `/donnees/codex/tmp/arg0` : ce refus ne vient donc que d'un
  geste fait à la main en root, ou d'un lien posé par un agent. Remise en état, comme le § 10 b :
  1. sauvegarde manuelle du volume `executant-donnees` ;
  2. service `executant` → **Custom Start Command** : `/bin/sh -c "exec sleep infinity"`, puis « Deploy » ;
  3. `railway ssh -i <clé dédiée> --service executant`, puis
     `find /donnees/codex /donnees/claude \( ! -uid 10001 ! -uid 10002 -o -type l \) -ls` pour voir ce qui est en
     cause ;
  4. un fichier de root créé à la main : `chown -h 10001:10001 <fichier>` sous `/donnees/codex` (10002 sous
     `/donnees/claude`) ; un lien inattendu : `rm <lien>` (le lien seul, jamais sa cible), en consignant ce qui a été
     retiré ;
  5. Start Command effacée, « Deploy » : l'entrée revérifie tout.

### 13.9 Après une restauration du volume `executant-donnees`

Hermes fait foi : l'exécutant rejoue sa file de sortie (les `reclamation_perdue` sont rangées sans effet), abandonne
les worktrees des cartes qu'il ne détient plus et **garde les branches**. Lancez `acp-poste diagnostic` : si la
connexion Codex est périmée (jeton déjà tourné), refaites `acp-poste connexion codex`. Les sauvegardes contiennent
`auth.json`, le jeton machine, les jetons Claude et GitHub et le code des dépôts : la frontière reste le compte
Railway (§ 11). Exécutant restauré à un instant différent de Hermes (règle d'ordre mesurée par le test de
restauration de P9 : exécutant antérieur ou égal à Hermes) : [exploitation.md](../exploitation.md) § 4.3.

---

## 14. Notifications, bilan quotidien et dépôts réels (étape P7)

Conception, état livré et preuves : [questions.md](questions.md) (file Questions, notifications, continuité),
[executant.md](executant.md) § 16 (garde « dépôt privé » mesurée). Décisions appliquées : D93 à D121
([plan.md](plan.md)). Comme au § 13 : vous fournissez les comptes, Hermes gère l'exploitation. **Rien de ce qui suit
n'a été exécuté** : chaque étape est votre geste, sur Railway seulement.

Cette section décrit l'état **réuni** de P7 (parties A à F, fusion `e2d210b` du 8 octobre 2026). Les gestes du § 14.6
supposent la PR de P7 fusionnée : `executant.md` § 16 (`9235999`), les deux refus anonymes (`3b1cac9`), les dépôts
mesurés de `GET /v1/poste`, la carte « Dépôts » avec la mesure et le grisage de Codex dans « Nouveau projet »
(`e85c7e3`, `1f2574c`).

### 14.1 Ce que P7 change dans l'IaC

Le service `hermes` déclare six variables de plus, **toutes par `preserve()`**, sans aucune valeur (D116) :

| Variable | Canal | Règle de la garde de démarrage ([image.md](image.md) § 4) |
|---|---|---|
| `ACP_NOTIFICATIONS` | tous | `aucune` (défaut si absente), `telegram` ou `ntfy` |
| `ACP_TELEGRAM_JETON` (**scellée**) | Telegram | non vide, sans espace, 256 caractères au plus ; jamais affiché |
| `ACP_TELEGRAM_DISCUSSION` | Telegram | identifiant numérique de la discussion (`-` admis) |
| `ACP_NTFY_SERVEUR` | ntfy | URL https d'un hôte public (`https://ntfy.sh` par défaut) |
| `ACP_NTFY_SUJET` | ntfy | 16 à 64 caractères parmi lettres, chiffres, `_` et `-` |
| `ACP_NTFY_JETON` (**scellée**) | ntfy | exigé (D33) : un sujet sans jeton serait lisible par des tiers |

Les deux canaux sont déclarés : vous choisissez le vôtre **sans autre PR** ; les variables de l'autre restent absentes.
Aucun littéral : `ACP_NOTIFICATIONS: "telegram"`, appliqué avant la pose du jeton, ferait refuser le démarrage de Hermes
(correction K13). Aucun autre changement : ni service, ni volume, ni réglage.

**Ordre (celui du § 9, jamais l'inverse)** : (1) la PR de P7 fusionnée dans `refonte/hermes`, CI verte (c'est elle qui
déclare les variables) ; (2) vous posez les valeurs dans Railway ; (3) `railway config plan` puis `railway config
apply`. Une variable posée dans Railway **avant** d'être déclarée apparaîtrait au plan comme une **suppression**
(rw_full.txt:28377).

**Supposé, à constater au premier plan qui suit la fusion** : `preserve()` sur une variable jamais posée ne crée rien
et n'est pas refusé par le plan (§ 3 ; la documentation de Railway ne traite pas ce cas). L'exposition est **plus
grande** que pour l'identité : les variables du canal que vous ne choisissez pas restent absentes **pour toujours**
(les six si vous ne choisissez aucun canal), donc chaque plan du projet en dépend, pas seulement le premier. Deux
écarts possibles, deux conduites, **jamais exécutées** (sur Railway seulement) :

- le plan montre la **création** d'une de ces variables (valeur vide) : arrêtez, n'appliquez pas. Une valeur vide
  fait refuser le démarrage (`ACP_NOTIFICATIONS` vide n'est pas un canal admis ; `ACP_NTFY_SERVEUR` vide est refusé
  avec ntfy). Posez alors d'abord `ACP_NOTIFICATIONS` = `aucune` (et, avec ntfy, `ACP_NTFY_SERVEUR` =
  `https://ntfy.sh`), puis relancez le plan ;
- le plan **refuse** `preserve()` sur une variable absente : rien ne s'applique, ni ces variables ni aucun autre
  changement du projet, tant que ce `preserve()` reste dans `railway.ts`. N'appliquez rien, et ne posez **aucune
  valeur factice** pour le canal non choisi (un jeton inventé n'est pas une configuration). Posez ou gardez les valeurs
  de votre canal, `ACP_NOTIFICATIONS` comprise (sans canal : `aucune`). Un agent de développement prépare
  une **PR de repli** qui retire de `.railway/railway.ts` le `preserve()` de chaque variable qui restera absente
  (celles de l'autre canal ; sans canal, les cinq variables de Telegram et de ntfy) et met à jour ce qui exige les
  six : `preservees` et le témoin « variable du canal omise » de `.railway/verifier.mjs`, `PRESERVEES_PAR_SERVICE` et
  `test_canal_de_notification_memes_noms_que_l_image` dans `scripts/tests/test_railway_iac.py`, `PRESERVEES_HERMES`
  et les cas paramétrés du canal retiré dans `hermes/tests/contrat/test_railway_iac_contrat.py`. CI verte, fusion
  après votre accord, puis plan (« 0 to destroy ») et apply. Au premier apply, la même PR applique aussi le
  contournement de l'identité (§ 3). Changer ensuite de canal demande alors une PR : posez d'abord les valeurs du
  nouveau canal, **sans** plan ni apply (non déclarées, elles apparaîtraient au plan comme des suppressions), puis PR
  qui déclare leurs `preserve()` (et retire ceux de l'ancien canal si vous supprimez ses valeurs) ; plan et apply
  après sa fusion.

Ce qui est prouvé, en local et en CI : `.railway/verifier.mjs` exige ces six `preserve()`, refuse tout littéral pour un
nom de secret et s'éprouve sur trois copies altérées (jeton en clair, canal littéral, variable omise) ;
`scripts/tests/test_railway_iac.py` vérifie que ce sont exactement les noms que lisent le greffon et la garde de
démarrage ; `hermes/tests/contrat/test_railway_iac_contrat.py` (CI « Image Hermes » seulement : il démarre l'image)
démarre Hermes sans aucune valeur posée (canal publié « aucune »), puis avec un canal Telegram et un canal ntfy posés
(valeurs de test) : aucun refus, canal configuré publié par la passerelle, aucun jeton dans les journaux.

### 14.2 Canal Telegram (recommandé)

Marche à suivre de Telegram, **non éprouvée par ACP** (aucun compte n'a été utilisé) :

1. Sur le téléphone, conversation avec **@BotFather** : `/newbot`, un nom affiché, puis un identifiant qui finit par
   `bot`. BotFather répond avec le **jeton** du bot : ne le collez nulle part ailleurs que dans Railway (étape 4).
2. Ouvrez la conversation avec votre bot et envoyez-lui `/start` : un bot ne peut écrire qu'à quelqu'un qui lui a
   écrit d'abord.
3. Identifiant de la discussion : dans une fenêtre de navigation **privée** du PC (le jeton figure dans l'adresse :
   aucun historique ne doit le garder), ouvrez `https://api.telegram.org/bot<jeton>/getUpdates` et relevez le nombre
   de `"chat":{"id": …}` du message `/start` ; fermez la fenêtre.
4. Tableau de bord Railway → service `hermes` → **Variables** → **New Variable** : `ACP_NOTIFICATIONS` = `telegram`,
   `ACP_TELEGRAM_JETON` = le jeton, puis menu ⋮ → **Seal** (scellée : illisible ensuite, modifiable par le menu ⋮),
   `ACP_TELEGRAM_DISCUSSION` = l'identifiant. Préférez l'interface à `railway variables --set` : le jeton resterait
   dans l'historique du shell.
5. Effacez le presse-papiers de Windows (et son historique, Win+V) et celui du téléphone.

### 14.3 Canal ntfy (possible)

1. Choisissez un **sujet** long et imprévisible (16 à 64 caractères parmi lettres, chiffres, `_` et `-`) et créez un
   **jeton d'accès** sur votre compte du serveur ntfy (`https://ntfy.sh` ou le vôtre) ; le sujet doit être réservé à
   ce compte, sinon le jeton ne protège rien. Ce que l'offre de `ntfy.sh` permet (compte, réservation, jetons) est à
   lire chez ntfy : **non vérifié** par ACP.
2. Abonnez l'application ntfy du téléphone à ce sujet, avec le même compte.
3. Railway, service `hermes` → **Variables** : `ACP_NOTIFICATIONS` = `ntfy`, `ACP_NTFY_SERVEUR` = l'URL du serveur
   (posez-la même pour `https://ntfy.sh`), `ACP_NTFY_SUJET` = le sujet, `ACP_NTFY_JETON` = le jeton, **scellé**.

### 14.4 Appliquer, puis la première preuve

1. `railway config plan` : « 0 to destroy », et aucune ligne qui crée, modifie ou supprime une variable du canal
   (vous les avez posées : `preserve()` les garde) ; sinon arrêtez (§ 14.1). Puis `railway config apply`, interactif
   (§ 3).
2. Déployez le changement de variables (bouton « Deploy » des changements en attente, comme au § 4.6). Une valeur
   invalide fait **refuser** le démarrage, en français (`[acp] REFUS : la variable ACP_… …`) : corrigez-la par le menu
   ⋮ de la variable, puis redéployez.
3. **Notification de test** : Accueil ou page Projets → « Envoyer une notification de test » ; la passerelle l'envoie
   par son fil d'envoi (moins d'une minute). `/api/plugins/acp-poste/v1/meta` → `projets.emetteur` (`canal`,
   `configure`, `envoyees`, `echecs`). C'est la **première preuve réelle de livraison** (cahier P7 § 13.6, n° 1), à
   consigner dans `docs/refonte/preuves-p7/` (capture sans le jeton).
4. Pour changer de canal ou de jeton : modifiez les variables (menu ⋮), plan, apply, redéploiement. Pour couper les
   notifications : `ACP_NOTIFICATIONS` = `aucune` (les notifications restent en base, marquées `desactivee`).

### 14.5 Bilan quotidien (facultatif)

Un clic, une fois, si vous le voulez : Accueil → carte « Bilan quotidien » → **Créer le bilan quotidien (8 h)** (ou la
page Cron de Hermes, script `acp-bilan.py`, sans agent). Aucun modèle, aucun jeton ; 8 h heure de Paris ; une
notification par jour, compteurs seulement, même quand rien n'a bougé. Pause ou suppression : page Cron. Sans canal
configuré, la carte dit « Le bilan ne partira pas ». Preuve sur Railway seulement : bilan reçu à 8 h (cahier P7 § 13.6,
n° 6). Le script est déposé à **chaque** démarrage de P7, même sans tâche (Hermes exige le script à la création de la
tâche, D121) : avant tout retour à une image antérieure à P7, voir § 9 (Rollback, troisième avertissement).

### 14.6 Dépôts réels, un par un

Préalable : la preuve de P6 sur le dépôt jetable et privé (§ 13.3 bis, R5) est verte. **Jamais** le dépôt d'ACP
lui-même en premier (Railway déploie `refonte/hermes`). Un dépôt à la fois (D102) :

| Étape | Qui | Geste |
|---|---|---|
| 1. Choisir le dépôt réel | **vous** | le nommer (élargir le périmètre est votre geste) |
| 2. Lecture du dépôt | **vous** | l'ajouter à votre jeton GitHub **à portée fine** (`Contents: Read-only`, dépôts choisis), ou en créer un nouveau et le déposer : `railway ssh -i <clé dédiée> --service executant`, puis `acp-poste connexion github --stdin` (§ 13.5, D92) |
| 3. Politique | agent de développement | PR qui ajoute `[depots.<alias>]` à `executant/politique/executant.toml` : URL, `branche_base`, `acces = "jeton_lecture"`, préparation et vérification lues dans le dépôt (README, CI, fichier de verrou) ; CI verte |
| 4. Fusion de cette PR | **vous** | après votre « oui pour <dépôt> » **écrit** : l'autorisation permanente des PR d'étape ne couvre pas un élargissement du périmètre |
| 5. Déploiement et mesure | Railway, exécutant | redéploiement de l'exécutant après « Wait for CI » ; inventaire publié ; visibilité **mesurée** (D103) |
| 6. Premier projet | Hermes ; preuve par l'agent | un petit projet sur ce dépôt, puis la preuve « aucune action accord requis sans geste », avant le dépôt suivant |

**Mesure de la visibilité (étape 5)** : page Poste, carte « Dépôts » : alias, visibilité mesurée, lecture, date, voies
ouvertes (`1f2574c`). La voie **Codex** n'est ouverte pour ce dépôt que si la mesure dit `prive`
**et** `ok` (accès anonyme refusé deux fois, lecture avec le jeton réussie, D113, `3b1cac9`) ; sinon Codex est fermé
(Claude reste admis sur un dépôt public, D84), et « Nouveau projet » grise Codex avec la raison (`1f2574c`). « Inconnue » ferme Codex (échec fermé) : si GitHub limite les accès
anonymes depuis Railway (403, 429), la mesure le dira à ce premier dépôt réel. Détail : [executant.md](executant.md)
§ 16.

**Preuve « aucune action accord requis sans geste » (étape 6)**, sur des relevés que vous prenez (ou qu'un agent prend
pour vous), depuis votre PC ; un « export » est la réponse JSON de l'adresse, ouverte dans le navigateur connecté au
tableau de bord (`https://<libellé-hermes>.up.railway.app/…`) et enregistrée telle quelle :

1. **Avant** le projet : `git ls-remote <url du dépôt> > ls-avant.txt` (avec votre accès habituel) ; export de
   `GET /api/plugins/acp-poste/v1/poste` → `inv-avant.json`.
2. Lancez le petit projet ; attendez « Terminé » (ou « Branche prête »).
3. **Après** : `git ls-remote <url> > ls-apres.txt` ; exports de `GET /api/plugins/acp-poste/v1/projets/<id>` →
   `projet.json`, de `GET /api/cron/jobs` → `cron.json`, de `GET /api/plugins/acp-poste/v1/poste` → `inv-apres.json`.
4. `python scripts/preuve_accord_requis.py --alias <alias> --nom-depot <propriétaire/dépôt> --avant ls-avant.txt
   --apres ls-apres.txt --projet projet.json --cron cron.json --inventaire-avant inv-avant.json --inventaire-apres
   inv-apres.json --sortie docs/refonte/preuves-p7/accord-requis-<alias>.md` (Python du PC, bibliothèque standard
   seulement) : tableau « geste → preuve → verdict » ; codes 0 (tout conforme), 1 (un geste NON CONFORME), 3 (aucun
   écart, mais une preuve manquante), 2 (pièce illisible). Aucune référence n'est imprimée (nombre et empreinte
   SHA-256 de la liste), le nom réel du dépôt est remplacé par son alias.
5. Pièces que l'outil ne lit pas, à joindre : capture des permissions du jeton GitHub (« Contents: Read-only »),
   demandes d'écriture en mémoire et en skills en attente (aucune appliquée sans votre geste), journal de l'exécutant
   (`railway ssh … -- acp-poste journal`) : chemins sous `/donnees/espaces/<alias>/` seulement.
6. Le résultat va dans `docs/refonte/preuves-p7/` par une PR ; le dépôt suivant attend un tableau sans NON CONFORME.

L'outil est éprouvé sur des fixtures (`scripts/tests/test_preuve_accord_requis.py`), **jamais sur un vrai dépôt** à ce
jour.

### 14.7 Preuves à relever sur Railway (cahier P7 § 13.6)

Toutes **sur Railway seulement**, après la fusion et le déploiement de P6 et de P7, avec vos gestes ; à consigner dans
`docs/refonte/preuves-p7/` (aucun secret) :

1. notification de test reçue sur le téléphone (§ 14.4) ;
2. **parcours réel** : projet lancé depuis le téléphone sur le dépôt jetable, téléphone verrouillé ; une carte de
   l'exécutant pose une question (consigne de test) ; notification reçue ; réponse depuis le PC en 1440×900 ; fil repris ;
   projet terminé, notification « branche prête » (`integration`) ou « terminé » selon qu'une branche a été rapportée ;
3. **redéploiement pendant une question** : une question ouverte, puis un redéploiement de `hermes` (une fusion qui
   touche `hermes/`, sinon « Redeploy », § 9) ; question intacte, aucune notification en double, réponse puis reprise ;
   au démarrage, `scripts/` inspecté, `acp-bilan.py` admis par son empreinte ;
4. flux à travers le bord Railway : délai d'une trame, `fin` à 10 min, reconnexion sans perte ;
5. **premier dépôt réel** : visibilité mesurée `prive` + `ok`, petit projet, tableau de `preuve_accord_requis.py` sans
   NON CONFORME (§ 14.6) ;
6. bilan reçu à 8 h, s'il a été créé (§ 14.5) ;
7. transcriptions **illustratives** de la carte « répondre » (une question couverte par les décisions du projet,
   une non couverte, escaladée) : jamais présentées comme une garantie.

Ce qui restera non prouvé, même alors : la qualité des réponses de Hermes ; un navigateur autre que celui du téléphone
utilisé ; les questions d'une discussion `/chat` dans la file (impossible, [questions.md](questions.md) § 6).
