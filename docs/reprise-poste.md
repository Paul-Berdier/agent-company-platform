# Reprise du travail sur un autre poste

État du **25 septembre 2026**, Europe/Paris. Lire aussi `CLAUDE.md`,
[le plan de la refonte](refonte/plan.md) et [le plan d'autonomie](refonte/autonomie.md), qui
remplace ses phases P4 à P8.

## 1. Où en est le chantier

ACP est en pleine **refonte « Hermes au centre »** : Hermes Agent devient le seul
serveur, le seul orchestrateur et la seule source de vérité ; ACP ne garde que l'image
Railway dérivée et ses deux greffons (image et squelette d'`acp-poste` depuis P1,
`acp-interface` à construire), le poste Windows, le client Qt et
le tableau de bord de Hermes habillé. L'ancien backend ACP (API FastAPI, base, bus
d'événements, passerelle de fournisseurs, CLI `acp`, interface web Vite) est retiré ;
il reste entier sous l'étiquette annotée **`archive/acp-0.10.0-avant-hermes`**
(commit `60a49b6`, dernière fusion de `main` avant la refonte, CI `35981934303` et
Desktop CI `35981934226` vertes sur ce commit).

- Branche d'intégration : `refonte/hermes`, partie de l'étiquette d'archive, version
  **0.11.0**.
- Une branche par étape, `refonte/hermes-pN`, PR vers `refonte/hermes`. Étiquette
  `1.0.0` seulement à la fusion finale dans `main`.
- Worktrees de travail : `.claude/worktrees/refonte-hermes`, pour P1
  `.claude/worktrees/refonte-hermes-p1`, pour P2 `.claude/worktrees/refonte-hermes-p2`.
  **Le checkout principal
  porte un chantier Pixel Office non commité (moteur, salles, `apps/web`) : ne rien y
  modifier.** Les autres worktrees historiques peuvent contenir des travaux partiels ;
  ne pas les supprimer ni les réinitialiser sans examen.
- Depuis P2 (côté dépôt), Hermes est prêt à être déployé sur Railway derrière son propre
  fournisseur d'identité (Authelia, service `identite`), et l'agent n'y a **aucun outil
  d'exécution**. **Rien n'est encore déployé** : le premier déploiement est fait par le
  propriétaire, selon [`docs/refonte/railway.md`](refonte/railway.md).

## 2. Décisions du propriétaire

Elles priment sur les recommandations du plan (détail : `docs/refonte/plan.md`, § 1).

- Connexion au tableau de bord par **OIDC auto-hébergé** (fournisseur `self_hosted`
  de Hermes), **pas** Nous Portal. Le flux natif RFC 8252 du desktop fonctionne avec
  lui. Hermes n'a aucune liste blanche : le fournisseur d'identité ne devra accepter
  que le propriétaire. Fournisseur retenu en P2 : **Authelia 4.39.28** (service
  `identite`, un seul utilisateur, passkeys) ; Pocket ID écarté.
- Cerveau de Hermes : abonnement **ChatGPT** (`openai-codex`).
- **Rien n'est déployé sur Railway** : aucune migration de données.
- Railway **Hobby**, 2 Go, plafond de 30 $ par mois, région Europe, sans domaine
  personnalisé au départ.
- Approbations **manuelles**.
- Décisions du 25 septembre 2026 (détail : `docs/refonte/plan.md`, § 1) :
  - **aucun outil d'exécution pour l'agent sur Railway** (ni terminal, ni fichiers, ni code, ni
    navigateur, ni cron, ni délégation, ni connexions) ; `kanban_create` et `kanban_attach_url`
    retirés à l'agent ; `web_extract` et `vision_analyze` gardés ; écritures de l'agent en mémoire
    et dans les skills soumises à validation ;
  - surfaces shell du tableau de bord gardées sous le seul OIDC en P2 ; session de 7 jours ;
  - branche déployée `refonte/hermes` après la fusion de P2 ; IaC `.railway/railway.ts`,
    appliquée par le propriétaire seul ; libellés des sous-domaines en gabarit qui échouent
    fermé ; plafond dur 30 $, alerte 15 $, agent Railway 0 $ ; Hermes 2 Go et 1 vCPU ; identite
    0,5 vCPU, 2,5 Gio mesurés, 100 relances ; sauvegardes quotidienne et hebdomadaire ;
    `railway ssh` avec une clé dédiée retirée après usage ; `trusted_proxies: []` tant que non
    mesuré ;
  - **phases P4 à P8 remplacées** par le plan d'autonomie
    ([`docs/refonte/autonomie.md`](refonte/autonomie.md)).

## 3. Étapes

| Étape | Objet | État |
|---|---|---|
| P0 | Branche, élagage et gel du moteur | **fusionnée** dans `refonte/hermes` (PR #13, `29c95b5`) (§ 4) |
| P1 | Image dérivée et CI de contrat, sans Railway | **fusionnée** dans `refonte/hermes` (PR #14, `21d13ee`) (§ 5) |
| P2 | Premier déploiement Railway authentifié (OIDC), agent sans terminal | **réalisée côté dépôt** sur `refonte/hermes-p2`, relecture indépendante traitée, poussée ; sans PR ; **rien de déployé** (§ 6) |
| P3 | Identité, français et réglages prêts | à faire |
| P4 | Projets autonomes sur Hermes (plan d'autonomie) | à faire |
| P5 | Poste connecté : présence, catalogue, quotas (plan d'autonomie) | à faire |
| P6 | Exécution autonome sur un dépôt jetable (plan d'autonomie) | à faire |
| P7 | Questions, notifications, continuité ; dépôts réels (plan d'autonomie) | à faire |
| P8 | Desktop Qt et MCP côté poste (plan d'autonomie) | à faire |
| P9 | Exploitation, montée de version et publication | à faire |

Les anciennes P4 à P8 du plan (discussion mobile, poste en lecture, quotas, écritures signées,
desktop) sont remplacées par celles du plan d'autonomie ; leur texte reste dans `plan.md` pour
mémoire.

## 4. P0 — ce qui a été fait

Commits, dans l'ordre, sur `refonte/hermes-p0` :

1. `4ce2aa4` `chore(release): open 0.11.0` — `VERSION` et copies ;
   `scripts/check_version.py` réduit aux composants conservés, **sans** le moteur.
2. `da5bbc7` `chore: remove pre-Hermes domains` — retrait de `apps/api`,
   `packages/database`, `apps/event-service`, `packages/event-sdk`,
   `services/provider-gateway`, `packages/provider-sdk`, `apps/cli`, des sources et
   tests d'`apps/web` (seul `apps/web/public/assets` reste), `packages/ui`, du miroir
   TypeScript des contrats, `packages/agent-sdk`, `packages/playwright-reporter`,
   `e2e/`, du déploiement ACP (`deploy/railway`, `docker/`, `.dockerignore`,
   `.env.example`, `.21st/`) et des scripts liés à l'API ou à sa pile locale ;
   workspaces npm réduits au moteur ; verrou Python recompilé.
3. `3f51126` `refactor(poste): rename worker to poste and drop API-bound modules` —
   `apps/worker` devient `apps/poste` (distribution `acp-poste`, commande
   `acp-poste`), élagué ; le contrat Python des quotas passe dans
   `hermes/plugins/acp-poste/contrat` ; le reste de `packages/contracts` part.
4. `0def013` `ci: guard the frozen Pixel Office engine and reduce CI to three lanes` —
   `scripts/check_engine_frozen.py` et CI en trois volets (moteur, poste, desktop).
5. `805ca4c` `docs: rewrite CLAUDE.md and handoff notes for the Hermes architecture` —
   ce document, `CLAUDE.md`, `README.md`, `docs/refonte/plan.md`, README du desktop ;
   documentation datée des lots A à H retirée.
6. à 10. `25c9e59`, `9f12fa5`, `c991ecf`, `92ce76a`, `ce91bbb` — corrections de la
   relecture indépendante (ci-dessous).
11. `docs: record the P0 review fixes and fresh evidence` — ce document et le journal
    des modifications, preuves rejouées.

### Corrections après la relecture indépendante

Cinq défauts confirmés, chacun vérifié avant correction :

- `25c9e59` `fix(contract): keep the NUL byte out of its own refusal message` — le
  message de `refuse_nul` (`_validation.py`) contenait un vrai octet NUL (chaîne non
  brute ; l'étiquette écrivait `"\\x00"`). Les modèles de quotas n'y arrivaient pas
  (leurs validateurs de champ refusent le NUL avant, avec un message échappé), mais le
  filet commun `ContratValide` si. Tests : aucun message de refus, de champ ou commun,
  ne contient l'octet ; les trois cas du filet commun échouaient avant la correction.
- `9f12fa5` `test(poste): restore real DPAPI tests for credentials_protection` — les
  tests du DPAPI vivaient dans `test_state.py` du worker, retiré avec l'enrôlement ;
  plus aucun test n'importait le module. `tests/test_credentials_protection.py` :
  aller-retour DPAPI réel, blob altéré ou jamais protégé refusé, charge vide ou de
  plus de 1 Mio refusée (Windows) ; hors Windows, refus avant tout appel natif.
- `c991ecf` `fix(poste): drop the journal command that nothing feeds` — `acp-poste
  journal` lisait un fichier que plus rien n'écrit et sortait en 0 sans rien dire.
  Commande retirée, avec `ACP_POSTE_STATE_DIR`, qui ne servait qu'à elle.
  `local_log.py` reste (le plan le garde) avec ses propres tests ; la commande
  reviendra en P5 avec un écrivain réel.
- `92ce76a` `fix(poste): make the quota switch govern acp-poste quotas` —
  `ACP_WORKER_SUBSCRIPTION_QUOTAS` ne gouvernait que le diagnostic. `collect_reports`
  refuse désormais sans rien lancer ni lire tant qu'il ne vaut pas `1`, et
  `acp-poste quotas` le dit en français, code 2. `ACP_WORKER_QUOTA_INTERVAL_SECONDS`,
  validé mais lu par rien depuis le retrait de la boucle d'envoi, est retiré.
- `ce91bbb` `docs(poste): say that acp-poste quotas reaches OpenAI through Codex CLI` —
  « aucune connexion réseau » était inexact : le poste n'en ouvre aucune lui-même, mais
  Codex CLI, qu'il lance, interroge le serveur d'OpenAI (`account/rateLimits/read`).

### Ce qui a dû être gardé, et pourquoi

- `apps/web/public/assets`, `plugins/*` (salles et `plugin.json`) et le bloc
  `.gitignore` des assets sous licence : le moteur et ses outils les lisent ; ils font
  partie du gel. Les `plugin.json` servaient à l'API retirée mais `plugins/` est gelé
  en entier par la garde du plan.
- Documentation du moteur (`docs/assets/*.md`, `docs/spritesheets.md`,
  `docs/pixel-engine-phaser-migration.md`, `docs/architecture/campus-growth.md`) :
  inchangée, pour ne pas entrer en conflit avec le chantier Pixel Office ; certains
  passages y citent encore l'API retirée.
- Guides desktop encore justes : `docs/desktop-build.md`,
  `docs/desktop-msvc-cache-recovery.md`, `docs/desktop-release-process.md`,
  `docs/desktop-update-process.md`, et, pour le client tel qu'il est avant P8,
  `docs/native-desktop-architecture.md` et `docs/desktop-security.md`, avec un bandeau
  « hors service jusqu'à P8 ». 45 fichiers de `docs/` ont été retirés (le plan en
  annonçait 44 ; la différence vient des captures datées retirées et des guides
  desktop gardés).
- `scripts/setup-claude-cli.ps1` (installation épinglée de Claude Code, sans lien avec
  l'API) et `scripts/lock_python.*`, `scripts/check_lock.py`, `scripts/setup.*`,
  adaptés.
- `design/tokens`, `packaging/windows`, `desktop-release.yml` : inchangés.
- Dans `apps/poste`, `local_runner.py` garde sa structure de requête versionnée
  (`request.json`, jeton de clôture) ; seule la lecture des « claims » de l'API est
  retirée. `executors.py` garde `invocation_from_mission`, qui ne dépend de rien de
  retiré : P5 le remplacera par l'invocation depuis la table `demandes`.
- `credentials_protection.py` (DPAPI, pour le jeton machine de P5) et `local_log.py`
  (journal de P5) sont gardés sans utilisateur en production, chacun avec ses tests.

### Écarts au plan, assumés

- Un cinquième commit (`ci: …`) sépare la garde du moteur et la CI réduite du retrait
  des domaines.
- Les workspaces npm et le verrou sont réduits dans le commit de retrait (et non avec
  la CI) pour que chaque commit reste cohérent.
- `capabilities.py`, `state.py` et l'ancienne `cli.py` du worker, absents des deux
  listes du plan, sont retirés : ils n'existaient que pour l'enrôlement auprès de
  l'API. La nouvelle `acp-poste` n'offre que `diagnostic`, entièrement local, et
  `quotas`, sur accord `ACP_WORKER_SUBSCRIPTION_QUOTAS=1` : le poste n'ouvre lui-même
  aucune connexion, mais Codex CLI, qu'il lance, interroge le serveur d'OpenAI. Aucune
  commande ne simule la délégation ; `journal` attend son écrivain (P5).
- La passerelle MCP des exécuteurs est retirée (aucun MCP côté poste en v1, selon le
  plan) ; la boucle qui envoyait les quotas à l'API aussi.
- Le verrou Python ne garde que `pydantic`, pytest et leurs dépendances ; `colorama`
  y est ajouté pour installer pytest sous Windows avec le même verrou haché. `httpx`
  en sort (plus aucun import) : il reviendra avec le client HTTPS de P5. Les épingles
  de base du Lot H ne sont plus imposées par `check_lock.py`.
- Desktop CI perd l'étape « parcours Qt contre une vraie API locale » (API retirée) et
  se déclenche aussi sur `design/tokens/**`.
- Les variables d'environnement du poste gardent leur préfixe `ACP_WORKER_*` ; P5 les
  remplace par `%LOCALAPPDATA%\ACP\poste.toml`. `ACP_POSTE_STATE_DIR` et
  `ACP_WORKER_QUOTA_INTERVAL_SECONDS` sont retirées : elles ne gouvernaient plus rien.
- Écart à la relecture : elle proposait de retirer aussi `PosteLogger` ; il reste,
  parce que le plan garde `local_log.py`.

### Preuves relevées le 24 septembre 2026 (Windows 10, poste de reprise)

Rejouées après les corrections de la relecture, sur `ce91bbb` (seuls `apps/poste`,
le contrat, `CHANGELOG.md` et ce document diffèrent de `805ca4c`).

- Garde du moteur : `git diff --exit-code archive/acp-0.10.0-avant-hermes --
  packages/pixel-office-engine apps/web/public/assets plugins` → sortie vide, code 0,
  pour l'arbre de travail comme pour `HEAD` ; `python scripts/check_engine_frozen.py`
  → code 0. Ses refus ont été éprouvés un par un lors de la première passe (fichier du
  moteur modifié, fichier non suivi dans `plugins`, bloc `.gitignore` altéré, version
  de `phaser` changée dans le verrou : code 1 et motif en français) ; les deux premiers
  ont été rejoués ici, puis l'arbre restauré (`git checkout`). Les 68 fichiers suivis
  des trois chemins gelés ont le contenu exact des blobs de l'étiquette ; seules les
  fins de ligne de l'arbre de travail diffèrent (`core.autocrlf=true`, § 8).
- `npm ci` puis `npm run test:engine` (Node 24.19.0, Vitest 5.0.0) : **7 fichiers,
  74 tests réussis**, comme avant et après la réduction des workspaces.
- Verrou npm, inchangé depuis `da5bbc7` : 31 entrées retirées, toutes propres aux
  workspaces retirés ; les 67 paquets de la fermeture du moteur gardent version, URL
  et intégrité (10 entrées ne gagnent que l'attribut `"peer": true`).
- pytest sous Windows : **240 réussis, 0 ignoré** (`apps/poste` 175, contrat 60,
  outillage 5), dans le venv du poste et dans un venv neuf Python 3.12.10 de
  python.org installé depuis le seul verrou haché (rejeu des étapes du volet CI
  Windows : `check_version.py`, `pip install --require-hashes --no-deps`,
  installations éditables sans dépendances, `pip check` propre, `check_lock.py`).
- pytest sous Linux, rejeu des mêmes étapes dans un conteneur `python:3.12-slim` sur
  `git archive HEAD` : **231 réussis, 9 ignorés** (8 « DPAPI réel propre à Windows »,
  1 « Job Object Windows uniquement »).
- Sous forte charge processeur, des tests temporisés repris sans changement de
  l'étiquette échouent : une première exécution lancée **pendant** une compilation
  MSVC complète a donné 1 échec (`FileNotFoundError` sur `hang.pid` dans
  `test_a_hanging_app_server_times_out_and_its_process_tree_is_stopped`) ; sous charge
  artificielle (24 à 36 processus actifs pour 12 cœurs logiques), ce test,
  `test_stop_terminates_a_spawned_child_process`,
  `test_timeout_terminates_the_real_process` et
  `test_request_duration_can_only_reduce_the_local_timeout` échouent tour à tour.
  Sans charge : 240 sur 240 à chaque exécution. Non traité en P0.
- Desktop Debug : compilation **complète** (`build-desktop.ps1 -Clean`, 433 étapes
  Ninja, code 0) ; `test-desktop.ps1` **25 suites sur 25** ; détail Qt Test, chaque
  exécutable lancé avec un rapport `-o …,txt` : **406 réussis, 0 échec, 1 ignoré**
  (`tst_api_journey`, qui n'a plus de parcours). Release n'a pas été recompilé sur ce
  poste.
- `check_version.py` : versions synchronisées sur 0.11.0 ; `check_lock.py` :
  14 épingles cohérentes ; `git diff --check archive/acp-0.10.0-avant-hermes HEAD`
  propre ; aucun `Co-Authored-By` ni pied de page d'agent dans les commits de P0.
- `acp-poste` lancé à la main : `journal` refusé par argparse (code 2) ; `quotas`
  sans accord refusé en français (code 2) ; `diagnostic` annonce
  `"subscription_quotas": "disabled"` et rien d'autre sur les quotas.

### Non vérifié

- **Aucune CI n'a tourné** : rien n'est poussé. Le volet Windows du poste
  (`windows-2022`) n'a jamais tourné en CI ; Desktop CI n'a pas d'identifiant de run
  pour P0. Pousser `refonte/hermes-p0`, attendre les trois volets verts, puis ouvrir
  la PR vers `refonte/hermes`.
- `apps/desktop/cmake/check_layout.py` sort en code 1 sur 10 constats hérités de
  l'étiquette (origines codées en dur, chemin absolu dans un test) : non traités, le
  code du client n'est pas modifié en P0.
- La tenue sous charge des tests temporisés du poste (ci-dessus) : ils bornent des
  délais de 0,15 à 3 s qui comptent le démarrage d'un interpréteur Python. À durcir
  (attendre le fichier témoin avant de le lire, délais relatifs) dans une PR dédiée.

## 5. P1 — image dérivée et CI de contrat

Branche `refonte/hermes-p1`, empilée sur `refonte/hermes-p0` : sa PR vers
`refonte/hermes` s'ouvrira après la fusion de P0. Référence complète :
[`docs/refonte/image.md`](refonte/image.md) (démarrage, variables Railway attendues et
interdites, managed scope, greffon, tests, ce qui est prouvé et ce qui ne l'est pas).

Commits, dans l'ordre :

1. `feat(hermes): pin the official Hermes image and its gateway contract` —
   `hermes/contrat/` (`HERMES_VERSION`, copie exacte de l'OpenRPC, licence MIT) ;
   `hermes/**` en LF (`.gitattributes`).
2. `feat(hermes): derive the Railway image with boot guards and a managed scope` —
   `hermes/image/` (Dockerfile, crochet `acp-gardes`, `cont-init.d/05-acp`,
   `acp_demarrage.py`), `hermes/gere/config.yaml`, persona et thème provisoires.
3. `feat(poste): add the acp-poste plugin skeleton with meta route and kanban adapter` —
   `hermes/plugins/acp-poste/` ; `check_version.py` couvre ses manifestes.
4. `test(hermes): add in-image tests, host contract tests and offline fakes` —
   `hermes/tests/` (image de test, pytest dans l'image, tests de contrat depuis l'hôte,
   modèle factice compatible OpenAI, faux fournisseur OIDC, greffon témoin).
5. `ci: build the Hermes image and run its contract on every push` — `image.yml`.
6. `docs: document the Hermes image and record P1 evidence` — ce document,
   `docs/refonte/image.md`, `CLAUDE.md`, journal des modifications.
7. `test(hermes): wait for the gateway api_server before contract checks` — un run
   local a lu `/api/status` avant que la passerelle n'ait branché son api_server
   (`KeyError: 'api_server'`) ; les fixtures attendent désormais la passerelle.
8. `docs: record the P1 CI runs` — identifiants des runs ci-dessous.

### Corrections après la relecture indépendante de P1

Cinq constats de la relecture indépendante, corrigés dans l'image et éprouvés. Détail
complet dans [`docs/refonte/image.md`](refonte/image.md) (§ 4.3, § 4.4, § 5, § 9, § 10).

1. **Élévation par `/run/service` (critique).** L'image officielle laisse `/run/service` et
   le `run` des passerelles à l'agent ; s6-supervise tournant en root, un service créé ou un
   `run` réécrit par l'agent s'exécuterait en root. **Correctif** : `05-acp` reprend à root le
   répertoire et les scripts des passerelles (`reprendre_services_s6`), ne laissant à l'agent
   que la FIFO `supervise/control`. Prouvé : l'uid hermes ne peut plus créer de service, ni
   réécrire `run`/`.acp-amont-run`, ni déplacer la passerelle ; `s6-svc -r` marche toujours.
2. **`/opt/data/.env` échappe à la managed scope (critique).** `HERMES_MANAGED_DIR` déplace
   la portée gérée et aucune épingle ne la contre. **Correctif** : `HERMES_ENABLE_PROJECT_PLUGINS=0`
   et `HERMES_BUNDLED_PLUGINS=` épinglés dans `/etc/hermes/.env` ; les gardes de démarrage
   **et** une garde root en tête des `run` (tableau de bord et passerelle) refusent tout
   `/opt/data/.env` (ou `profiles/*/.env`) porteur de `HERMES_MANAGED_DIR`,
   `HERMES_BUNDLED_PLUGINS` ou `HERMES_ENABLE_PROJECT_PLUGINS`. Liste étroite : `API_SERVER_KEY`,
   que l'image écrit elle-même dans ce fichier, est exclue. `/v1/meta` signale une portée
   détournée. Prouvé : relance et redémarrage refusés (échec fermé, message français).
3. **Prise du port 9119 sous le même uid (haute).** Non corrigeable en P1 : l'agent partage
   l'uid du tableau de bord. **Traitement** : documenté honnêtement (image.md § 5, § 9, § 10 ;
   `hermes/gere/config.yaml`) comme limite assumée, parade portée à P2 ; aucun test ne
   prétend le contraire (l'éprouver reviendrait à exécuter l'attaque).
4. **api_server déplaçable sur `0.0.0.0` par `config.yaml` (moyenne).** **Correctif** :
   `platforms.api_server.extra.host: 127.0.0.1` et `.port: 8642` épinglés dans la managed
   scope. Prouvé : même clé retirée de `/opt/data/.env` et api_server enrôlé sur `0.0.0.0` par
   `config.yaml`, l'écoute reste `127.0.0.1:8642`.
5. **Faux succès en CI/doc (moyenne).** **Correctif** : tests de contrat négatifs ajoutés
   pour chaque vecteur ci-dessus ; en-tête d'`image.yml`, § 5/§ 9/§ 10 d'`image.md`,
   commentaire de `gere/config.yaml` et cette note ne revendiquent que le prouvé et listent
   la limite du même uid.
6. **Élévation par le `PATH` (critique, trouvée à la vérification finale, après la
   relecture).** L'image officielle place `/opt/data/.local/bin`, que l'agent possède, avant
   `/usr/bin` dans le `PATH` que reçoivent tous les scripts root de s6. Sur `6b5a699`, un faux
   `id` déposé par l'agent tournait en root à la relance du tableau de bord (`uid=0(root)`) ;
   avec un faux binaire par commande système, quatorze tournaient en root. **Correctif** :
   `PATH` redéfini sans répertoire du volume, refusé par les gardes s'il sort de `PATH_ADMIS`,
   `/bin/sh` et `/bin/sleep` en chemin absolu dans les scripts d'ACP (image.md § 4.5).
   Prouvé : le nouveau test de contrat échoue sur l'ancienne image et passe sur la nouvelle.

Preuves rejouées le 24 septembre 2026 (Windows 10, Docker 29.5.3), après reconstruction :

- Construction de l'image Railway et de l'image de test : réussie ; managed scope de base
  « **28 clés épinglées** ».
- pytest dans l'image de test : **103 réussis**, 0 ignoré (89 auparavant ; +14 : gardes de
  `/opt/data/.env`, reprise `/run/service`, épingle api_server, greffons neutralisés, alerte
  de portée dans la meta).
- Tests de contrat depuis l'hôte : **35 réussis**, 0 ignoré (≈ 4 min 35 s ; 32 auparavant),
  dont : reprise root de `/run/service` et refus de création de service ; api_server ramené
  en `127.0.0.1:8642` malgré retrait de clé + enrôlement `0.0.0.0` ; `HERMES_MANAGED_DIR`
  dans `/opt/data/.env` → relance du tableau de bord et redémarrage du conteneur refusés
  (code 1, `[acp] REFUS`) ; `hermes config` : bandeau de **28 clés et 28 variables** gérées.
- `hermes plugins compat /opt/hermes/plugins/acp-poste` → code 0 (« No enabled plugin
  imports paths scheduled for removal »).
- `scripts/check_engine_frozen.py` → code 0 ; `scripts/check_version.py` → code 0 (0.11.0).

Preuves du correctif `PATH` (point 6), le même jour, image reconstruite :

- Sur l'ancienne image (`6b5a699`), un faux `id` posé par l'uid hermes dans
  `/opt/data/.local/bin` puis `s6-svc -r /run/service/dashboard` : le faux binaire écrit
  `uid=0(root) gid=0(root)`. Le nouveau test de contrat échoue sur cette image, d'abord
  sur le `PATH` reçu par les scripts root, puis, cette assertion retirée, sur quatorze
  faux binaires exécutés en root (`basename`, `cat`, `chmod`, `chown`, `curl`, `dirname`,
  `stat`…).
- Sur la nouvelle image : `PATH` des scripts root =
  `/command:/opt/hermes/bin:/opt/hermes/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` ;
  598 faux binaires posés, **aucun** exécuté en root après relance du tableau de bord et
  de la passerelle par l'agent puis redémarrage du conteneur ; un `PATH` qui contient
  `/opt/data/.local/bin` fait refuser le démarrage (code 1, message français).
- pytest dans l'image : **108 réussis** (+5). Tests de contrat : **37 réussis** (+2).
  Au premier passage local, 31 réussis et 5 en échec sur `UnicodeEncodeError 'charmap'` :
  la console Windows, sortie redirigée vers un fichier, n'encodait pas les `print` de
  preuve. Relancés avec `PYTHONUTF8=1`, les 5 passent. Ce n'est pas un défaut de l'image.

### Écarts au plan, assumés

- **Gardes dans un crochet `S6_STAGE2_HOOK`** (`/opt/acp/bin/acp-gardes`) en plus de
  `05-acp`. Mesuré dans l'image : un script cont-init en échec n'empêche pas les suivants
  de tourner, s6 n'arrête le conteneur qu'à la fin de l'étape ; avec les gardes en
  cont-init, `stage2-hook.sh` consommait déjà une `API_SERVER_KEY` interdite et
  `02-reconcile-profiles` démarrait la passerelle avant l'arrêt. Le crochet s'exécute
  avant tout script cont-init ; `05-acp` refait ses contrôles.
- **`plugins.enabled: []`** et `acp-poste` de type `backend`, au lieu de
  `plugins.enabled: [acp-poste]` : avec son nom dans la liste, un homonyme déposé sous
  `/opt/data/plugins` serait importé par le tableau de bord, que l'agent peut relancer
  lui-même (`s6-svc -r`) sans passer par `05-acp`.
- **OIDC auto-hébergé** au lieu de Nous partout (décision du propriétaire) : variables
  attendues `HERMES_DASHBOARD_OIDC_ISSUER`, `_CLIENT_ID`, `_SCOPES` (facultative),
  `_CLIENT_SECRET` (facultative, jamais recopiée) ; variables Nous interdites ;
  `dashboard_auth/nous` désactivé avec `basic` et `drain`.
- **Autorités de certification épinglées sur le magasin du système**, pas à vide :
  constaté, `SSL_CERT_FILE=` vide fait échouer la récupération du JWKS (urllib) et
  bloquerait toute connexion.
- Variables interdites en plus de la liste du plan : `HERMES_UID`, `HERMES_GID`, `PUID`,
  `PGID`, `HERMES_KANBAN_BOARD`, `HERMES_AUTH_JSON_REBOOTSTRAP`,
  `HERMES_GATEWAY_NO_SUPERVISE`, `HERMES_DASHBOARD_INSECURE`, `API_SERVER_PORT`,
  mandataires et variables d'autorités de certification.
- Pas de migration unique (volume neuf, décision du propriétaire) ; pas de fournisseur de
  jeton machine en P1 (sans enrôlement ni route, il aurait été inerte : P5).
- Thème `acp` provisoire écrit à la main depuis `design/tokens/colors.json` (P3 le
  génère).
- `/proc/1/cmdline` vaut `s6-svscan -d4 -- /run/service`, pas la chaîne `/init` :
  `/init` s'exécute en s6-svscan ; c'est bien s6 en PID 1.
- `ss` n'existe pas dans l'image : les sockets en écoute sont lues dans
  `/proc/net/tcp*`.
- Un jeton OIDC mal signé, d'une autre audience ou d'un autre émetteur reçoit **503**
  (« fournisseur injoignable ») et non 401 : comportement de Hermes
  (plugins/dashboard_auth/_shared.py:192-229), sans donnée renvoyée.

### Preuves relevées le 24 septembre 2026 (Windows 10, Docker 29.5.3)

- `docker buildx imagetools inspect nousresearch/hermes-agent:v2026.9.24` → index
  `sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7`, `linux/amd64`
  `sha256:2fd023efbb8d3d2b0ce1a73d028b07370cff34f567cfe0e999553e8c327ea283` ; image
  tirée par ce condensat.
- Construction locale de l'image Railway et de l'image de test : réussie (la managed scope
  de base est validée au build : « 26 clés épinglées »).
- `hermes --version` dans l'image : `Hermes Agent v0.21.5 (2026.9.24) · upstream
  f97608f1` ; `/etc/hermes/image-provenance.json` : version 0.21.5, révision
  `f97608f178d1ffeca59860195ab7da295f7c8e5f`.
- pytest dans l'image de test : **89 réussis**, 0 ignoré (dont le contrôle négatif : sans
  managed scope, l'injection l'emporterait).
- Tests de contrat depuis l'hôte : **32 réussis**, 0 ignoré (≈ 3 min 20 s), dont :
  - refus code 1, message `[acp] REFUS : …` en français, `fatal: hook
    /opt/acp/bin/acp-gardes exited 1`, **aucune** ligne `[stage2]` ni cont-init :
    `API_SERVER_KEY`, `HERMES_MANAGED_DIR`, `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`,
    émetteur `http://`, émetteur `https://127.0.0.1`, émetteur absent, manifeste
    `name: acp-poste` sous `/opt/data/plugins/nimportequoi/`, manifeste de tableau de bord
    `acp-interface`, lien symbolique ; modèle géré au YAML invalide ; et, avec
    `S6_BEHAVIOUR_IF_STAGE2_FAILS=0`, arrêt explicite code 1 sans tableau de bord ;
  - `/proc/1/cmdline` = `/package/admin/s6/command/s6-svscan -d4 -- /run/service`,
    `info: hook /opt/acp/bin/acp-gardes exited 0`, `05-acp exited 0` ;
  - `hermes dashboard --host 0.0.0.0 --port 9119` et `hermes gateway run` sous l'uid
    hermes ; `/api/status` : 0.21.5, passerelle en marche, api_server
    `http://127.0.0.1:8642` ; écoutes : `0.0.0.0 9119` et `127.0.0.1 8642` seulement ;
  - `/api/auth/providers` = `self-hosted` seul ; meta et `/api/config` : 401 sans
    session ;
  - `hermes config` : bandeau de 26 clés et 26 variables gérées ; `hermes config get
    kanban.auto_decompose` → `false` ; `hermes config set approvals.mode off` → code 1,
    « managed by your administrator » ;
  - l'uid hermes ne peut écrire ni `/etc/hermes`, ni `/opt/data/plugins`, ni
    `/opt/data/dashboard-themes/acp.yaml`, ni le greffon groupé, ni `/etc/cont-init.d`
    (contrôle positif : il écrit dans `/opt/data`) ;
  - `hermes plugins compat /opt/hermes/plugins/acp-poste` → code 0 ; témoin → code 1,
    `hermes_cli.kanban_db.connect` → `hermes_cli.kanban_db_connect.connect` ;
  - meta avec un jeton du faux fournisseur OIDC : 200, contrat `acp-poste/1`, Hermes
    0.21.5 conforme, OpenRPC identique, SOUL déposé, aucune alerte ; jetons d'une autre
    clé, audience ou émetteur : 503 ;
  - injection (`/opt/data/config.yaml` et `.env` : basic, Nous, émetteur et client
    « intrus », mandataire, autorité) puis relance du tableau de bord par l'agent
    (`s6-svc -r`), puis redémarrage du conteneur : `self-hosted` seul, redirection de
    connexion vers `https://idp.acp.test:8443/authorize?…client_id=acp-tableau…`,
    `provider=basic` 404, jeton du propriétaire 200 ; managed scope, thème et SOUL
    identiques d'un démarrage à l'autre ;
  - `POST /api/hermes/update` → `ok: false` (`dashboard_update_managed_externally`),
    empreinte de `/opt/hermes` identique avant et après ;
  - carte `triage` du tableau `poste` intacte après 24 s (répartiteur à 5 s), aucune
    complétion demandée au modèle factice (seules des sondes de métadonnées) ;
  - `hermes chat -q` : « Réponse du modèle factice ACP. », requête
    `POST /v1/chat/completions` reçue par le modèle factice en boucle locale.
- Suite du dépôt : `pytest` **240 réussis** ; `check_engine_frozen.py` code 0 et
  `git diff --exit-code archive/acp-0.10.0-avant-hermes -- packages/pixel-office-engine
  apps/web/public/assets plugins` vide ; `check_version.py` : 0.11.0 partout (dérive du
  `plugin.yaml` détectée quand on la provoque).

### Intégration continue (commit `860fc04`, branche poussée le 24 septembre 2026)

- **Image Hermes** `36025999003` : verte. Condensat publié confirmé
  (`Digest: sha256:fca358f1…52b7`), `Hermes Agent v0.21.5 (2026.9.24) · upstream
  f97608f1`, `hermes plugins compat` : « No enabled plugin imports paths scheduled for
  removal » pour `acp-poste`, code 1 pour le témoin ; pytest dans l'image **89 réussis** ;
  tests de contrat **32 réussis** (2 min 43 s), `/proc/1/cmdline` =
  `s6-svscan -d4 -- /run/service`.
- **CI** `36025998703` : verte à la **deuxième tentative**. La première a échoué sur le
  seul volet Windows du poste :
  `apps/poste/tests/test_subscription_quotas.py::test_an_unreadable_version_is_unavailable`
  (« Arrêt de l'app-server Codex non confirmé » au lieu d'un détail sur la version),
  test temporisé de P0 que P1 ne touche pas (aucun fichier sous `apps/` modifié). La
  relance du seul volet en échec est passée ; les volets moteur et poste Linux étaient
  verts dès la première tentative. Même famille que les tests temporisés notés au § 4,
  à durcir dans une PR dédiée.
- **Desktop CI** `36026018926` (déclenchée à la main, `workflow_dispatch`, P1 ne touchant
  aucun chemin du desktop) : verte.
- Localement, après reconstruction depuis `860fc04` : pytest dans l'image 89 réussis ;
  tests de contrat 31 réussis et 1 échec (la course décrite au commit 7), puis, avec
  l'attente de la passerelle, 32 réussis (3 min 43 s). Les commits 7 et 8 sont vérifiés
  par leurs propres runs.

### Non vérifié

- Rien sur Railway (PID 1 sur la plateforme, proxy, `trusted_proxies`, variables
  réelles) : P2.
- Aucune connexion interactive complète dans un navigateur (le faux fournisseur n'a ni
  page d'autorisation ni échange de code) ; le refus d'un second compte relève du
  fournisseur d'identité choisi en P2.
- La procédure de récupération d'un volume qui fait refuser le démarrage n'est pas
  écrite (P2).

## 6. P2 — agent sans terminal, identité et infrastructure Railway

Branche `refonte/hermes-p2`, ouverte depuis `refonte/hermes` (`21d13ee`, P0 et P1 fusionnées),
poussée ; **ni PR, ni fusion, ni étiquette** à ce jour. Version 0.11.0 inchangée. **Rien n'est
déployé** : le premier déploiement est fait par le propriétaire seul, selon
[`docs/refonte/railway.md`](refonte/railway.md). Références : [`image.md`](refonte/image.md)
(image Hermes), [`identite.md`](refonte/identite.md) (Authelia), [`railway.md`](refonte/railway.md)
(IaC et procédure), [`autonomie.md`](refonte/autonomie.md) (P4 à P8 remplacées).

### Commits (aucun `Co-Authored-By`)

Partie 1 — image Hermes sans outil d'exécution :

| Commit | Sujet |
|---|---|
| `565e37b` | feat(hermes): leave the agent no execution tool and refuse to run outside the guards |
| `5274649` | test(hermes): prove no execution tool reaches the agent, preview.restart included |
| `93d9ac9` | chore(hermes): mark acp-entree executable like acp-gardes |
| `efbf7b0` | docs: document the P2 Hermes image without execution tools |
| `ba278ac` | docs: record the P2 image CI run |

Partie 2 — fournisseur d'identité :

| Commit | Sujet |
|---|---|
| `6413a2e` | feat(identite): add the pinned Authelia identity provider image and its root guard |
| `822d6e6` | feat(hermes): refuse a Railway private domain for the dashboard URLs |
| `0d2e40e` | test(identite): prove the identity image and its OIDC compatibility with Hermes |
| `9fbe433` | test(identite): add the browser login test with a virtual WebAuthn authenticator |
| `0f21080` | ci: build the identity image and run its contract and browser tests |
| `69b81a7` | docs: document the identity provider and its measured limits |
| `8232688` | docs: record the identity CI run |

Partie 3 — infrastructure Railway, CI et procédures :

| Commit | Sujet |
|---|---|
| `e9c3014` | feat(railway): declare the Railway project as code with fail-closed domain labels |
| `2acf0b7` | ci: type-check and evaluate the Railway IaC in the image workflow |
| `fb4c442` | test(railway): check the IaC statically and against both images |
| `1f6a35b` | docs: write the owner's Railway procedure for the first deployment and recovery |
| `8c02f6b` | docs: replace phases P4 to P8 with the autonomy plan and record the P2 decisions |
| `a4e2d86` | docs: record P2 in the handoff notes, CLAUDE.md and the changelog |
| `dafad76` | docs(railway): name the dashboard labels in both languages and qualify rollback |
| (ce commit) | docs: record the P2 CI runs of the Railway part |

### Ce qui est en place

- **Agent sans outil d'exécution** sur Railway, en trois couches (managed scope à 40 clés, `.env`
  géré à 38 variables, garde `pre_tool_call` en liste blanche de 24 outils) ; `kanban_create` et
  `kanban_attach_url` refusés ; `preview.restart` fermé dans le processus réel.
- **Gardes** : refus hors PID 1 (`acp-entree`, qui renvoie sur Railway à `railway.md` § 10 f),
  sentinelle hors s6 (code 78), `hooks/` et `scripts/` exigés vides à la racine du volume **et dans
  chaque profil** (liens sous `profiles/` refusés), volume Railway exigé, `RAILWAY_RUN_UID`, domaine
  privé refusé, commit déployé journalisé ; `diagnostiquer` en maintenance (sain sous s6 : code 0).
- **Identité** : `identite/` (Authelia 4.39.28 épinglé, garde root, un seul utilisateur, client
  public `hermes-acp`, passkeys), limite mémoire mesurée à 2,5 Gio.
- **IaC** : `.railway/railway.ts` (projet entier, deux services, deux volumes, aucune Start
  Command, gabarits qui échouent fermé), SDK `railway@3.11.0` isolé et verrouillé,
  `verifier.mjs` ; procédure complète du propriétaire (`railway.md`).
- **CI** : `image.yml` construit les deux images, relève les deux condensats, type et évalue l'IaC,
  lance les tests dans l'image, de contrat (Hermes, identité, IaC) et navigateur ; groupe de
  concurrence par exécution hors PR.

### Écarts au plan, justifiés

Partie 1 :
1. **40 clés au lieu de 39** : `agent.service_tier: ""` épinglée aussi (cohérente avec le plan
   d'autonomie).
2. **Témoin négatif « composite » corrigé** : sur Hermes 0.21.5, un composite comme
   `hermes-api-server` est développé puis élagué et ne rend pas terminal ; le vrai contournement
   mesuré est un nom non configurable comme `debugging` (tools_config.py:614-615).
3. Test P1 ajusté : un journal du modèle factice absent valait « aucune requête ». **Corrigé
   après la relecture** : la fixture attend que le modèle réponde (sonde `GET /v1/models`, qui crée
   le journal) et le test exige ce journal (`0a13f63`).

Partie 2 :
1. Noms de test `hermes-acp.test` et `identite-acp.test` (deux domaines enregistrables distincts,
   comme deux sous-domaines de `up.railway.app`).
2. **HEALTHCHECK Docker de l'image amont retiré** : `/app/.healthcheck.env` en 0666, réécrit par
   Authelia et sourcé en root, ouvrait une élévation.
3. Garde plus stricte : liens symboliques et fichiers spéciaux refusés sous `/config` ; empreinte
   bornée 19 456 ≤ m ≤ 65 536 Kio ; empreinte, nom et adresse retirés de l'environnement d'Authelia.
4. `acp-identite-admin` admet aussi `storage bans` (lever le bannissement du propriétaire).
5. Consentement explicite à chaque connexion complète (imposé par Authelia avec `offline_access`).
6. Mémoire mesurée par `VmHWM` et `memory.peak` (pics exacts du noyau), plus un témoin à 1 Gio.
7. Hermes refuse `*.railway.internal` pour l'URL publique et l'émetteur.
8. Documentation dans `identite.md` (renvoi depuis `image.md`).

Partie 3 :
1. **Branche déployée `refonte/hermes`** dans `railway.ts` (décision du propriétaire), au lieu de
   `refonte/hermes-p2` puis d'une PR de bascule : le premier apply suit la fusion de P2.
2. **Libellés en gabarit qui échouent fermé** (décision du propriétaire) au lieu de libellés
   remplacés avant le commit : `railway.ts` refuse, en français, tant qu'ils valent
   `<libellé-…>`, s'ils ne sont pas des libellés DNS, s'ils sont identiques, et tout environnement
   autre que `production` (ajout). Le test statique « aucun `<libellé` résiduel » du plan devient
   « gabarit détecté, garde présente » ; l'effet réel est prouvé par `verifier.mjs`.
3. **Limite mémoire d'identite : 2,5 Gio** (mesure de la partie 2) au lieu d'1 Go.
4. **`verifier.mjs` et `test_railway_iac_contrat.py` ajoutés** au plan : évaluation de `railway.ts`
   comme la CLI (au-delà du seul `tsc`), et démarrage des deux images avec les variables déclarées,
   santé sur le PORT déclaré avec l'hôte `healthcheck.railway.app` (mesuré avant : 200 pour les
   deux ; Authelia rend 400 à un en-tête Host vide). Les tests de contrat exigent donc Node ≥ 22 et
   `npm ci --ignore-scripts --prefix .railway`.
5. **Motifs surveillés de Hermes** : `["/hermes/**", "!/hermes/tests/**"]` (les tests ne sont pas
   dans l'image) ; `typescript@7.0.2`, version courante, épinglée.
6. **`.railway/.gitignore` en liste blanche** : ce qu'une commande `railway` écrirait dans
   `.railway/` n'entre jamais dans Git ; `railway config pull` sans `--json`, qui réécrirait
   `railway.ts`, est proscrit par la procédure.
7. **Poste de commande WSL** dans la procédure : la doc Railway documente sa CLI sous Windows par
   WSL, et le SDK exige une CLI ≥ 5.42.1 qu'il interroge au moment de l'évaluation.
8. `ci.yml` inchangé : le test statique y tourne par `scripts/tests` (déjà dans `testpaths`).
9. La correction « `client_ip` à request_utils.py:46-49 » du plan structuré est **fausse** :
   revérifié à `f97608f`, `client_ip` est à `hermes_cli/dashboard_auth/request_utils.py:19-21`,
   comme le disait déjà le plan ; rien n'a été changé sur ce point.

### Preuves locales (Windows 10, Docker 29.5.3, pytest 9.1.1, Python 3.12.10)

Partie 1 (25/09/2026, images `acp-hermes:p2a`, `acp-hermes-tests:p2a`) :
- dans l'image : **212 réussis**, 0 échec, 0 ignoré ;
- contrat : **56 réussis**, 0 échec, 0 ignoré, 9 min 49 s, dont les deux tests bloquants
  `preview.restart` avec leur témoin négatif ;
- chaque protection principale retirée d'une copie fait échouer ses tests (détail :
  `image.md` § 8).

Partie 2 (25/09/2026, images `acp-hermes:p2b`, `acp-hermes-tests:p2b`, `acp-identite:p2b`) :
- dans l'image : **216 réussis** ; contrat : **96 réussis** (56 Hermes, 40 identité), 11 min 15 s ;
  navigateur : **1 réussi** (Chromium 1234 déjà présent, rien téléchargé) ; 0 échec, 0 ignoré ;
- mémoire d'Authelia : 0,726 Gio à 10 premiers facteurs simultanés, **1,346 à 1,348 Gio** à 20 ;
  témoin sous 1 Gio tué (OOM) ;
- deux protections d'identité retirées : leurs tests échouent (`identite.md` § 13).

Partie 3 (25/09/2026) :
- IaC : `npm ci --ignore-scripts --prefix .railway` (8 paquets, verrou haché) puis
  `npm run --prefix .railway verifier` (Node 24.19.0 local) : `tsc` 7.0.2 sans erreur ; évaluation du
  fichier committé **refusée** (gabarits), neuf autres refus attendus (chaque gabarit, majuscules,
  point, tiret initial, vide, 64 caractères, libellés identiques, environnement `staging`) ; graphe
  d'essai conforme. Sept altérations d'une copie de `railway.ts` (Start Command ajoutée, garde des
  gabarits retirée, Serverless, volume omis, empreinte en clair, domaine personnalisé, Wait for CI
  coupé) font chacune **échouer** `verifier.mjs` ; `tsc` refuse `builder: "DOCKER"` et un nombre
  de relances en chaîne.
- Mesuré à la main avant d'écrire le test : `/api/health` répond **200** avec
  `Host: healthcheck.railway.app` sur les deux images (et avec `X-Forwarded-Host` ou
  `X-Forwarded-Proto` ajoutés pour Authelia) ; un en-tête Host vide rend 400 chez Authelia.
- Suite du dépôt (`python -m pytest -q`, venv Python 3.12.10 du verrou) : **279 réussis**, 0 ignoré
  (240 + 39 de `scripts/tests/test_railway_iac.py`) ; quatre altérations (Start Command, gabarit
  altéré, hôte écrit en dur, `cancel-in-progress: true`) font chacune échouer le test statique.
  `check_engine_frozen.py` et `check_version.py` : code 0.
- Images **reconstruites depuis le worktree** au commit `fb4c442` (`acp-hermes:p2c`,
  `acp-hermes-tests:p2c`, `acp-identite:p2c`) :
  - dans l'image : `docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site acp-hermes-tests:p2c -m pytest -v -rA /opt/acp-tests/image`
    → **216 réussis**, 0 échec, 0 ignoré (1 min 28 s) ;
  - contrat : `PYTHONUTF8=1 ACP_IMAGE=acp-hermes:p2c ACP_IMAGE_TESTS=acp-hermes-tests:p2c ACP_IMAGE_IDENTITE=acp-identite:p2c python -m pytest -s -v -rA hermes/tests/contrat`
    → **99 réussis** (56 Hermes, 40 identité, 3 IaC), 0 échec, 0 ignoré, 11 min 41 s ; mémoire
    d'Authelia 0,722 Gio à 10, 1,356 Gio à 20 (54,2 % de la limite), témoin sous 1 Gio tué (OOM) ;
  - navigateur : `PYTHONUTF8=1 ACP_IMAGE_TESTS=… ACP_IMAGE_IDENTITE=… ACP_E2E_OBLIGATOIRE=1 python -m pytest -s -v -rA hermes/tests/e2e`
    → **1 réussi** (35 s) ; Chromium de Playwright révision 1234 **déjà présent** sur le poste
    (répertoire daté du 04/08/2026), rien téléchargé ;
  - aucun conteneur, volume ni réseau `acp-contrat-*` restant.

### Intégration continue

- Partie 1 : `image.yml` 36087965990 (`efbf7b0`) **succès** (212 dans l'image, 56 au contrat) ;
  `ci.yml` 36087965871 (`efbf7b0`) et 36088738040 (`ba278ac`) **succès**.
- Partie 2 : `image.yml` 36094807793 (`69b81a7`) **succès** (216, 96, 1 ; condensats de Hermes et
  d'Authelia confirmés ; Chromium 1234 téléchargé par la CI ; mémoire 0,729 Gio à 10, 1,297 Gio à
  20) ; `ci.yml` 36094807754 (`69b81a7`) et 36095716568 (`8232688`) **succès**.
- Partie 3 : `image.yml` 36098262650 (`fb4c442`) **succès** : Node v22.23.2, `npm ci` du verrou
  (8 paquets), `tsc` et `verifier.mjs` verts (gabarits refusés, graphe d'essai conforme) ;
  condensats de Hermes et d'Authelia confirmés ; **216** dans l'image, **99** au contrat (dont les 3
  de `test_railway_iac_contrat.py`), **1** au navigateur ; 0 échec, 0 ignoré ; mémoire d'Authelia
  0,740 Gio à 10, 1,166 Gio à 20 (46,6 % de la limite), témoin sous 1 Gio tué. `ci.yml`
  36098262486 (`fb4c442`) **succès** : poste Windows **279 réussis** ; poste Linux **270 réussis,
  9 ignorés** (les 9 tests propres à Windows déjà notés en P0 : DPAPI réel et Job Object) ; moteur
  gelé, 74 tests. Commits de documentation qui suivent : `ci.yml` 36099417097 (`a4e2d86`)
  **succès** (poste Windows 279 réussis, Linux 270 réussis et 9 ignorés, moteur 74) ; `image.yml`
  ne se déclenche pas (aucun chemin surveillé touché) : son dernier run, 36098262650, porte sur
  `fb4c442`, dont `hermes/`, `identite/` et `.railway/` sont identiques au sommet de la branche.

### Preuves Railway

**Aucune** : rien n'est déployé. La liste à relever par le propriétaire est au § 7 de
[`railway.md`](refonte/railway.md) ; les sorties (sans secret) seront consignées ici.

### Non vérifié

- **Tout ce qui dépend de Railway** ([`railway.md`](refonte/railway.md) § 12) : PID 1 réel ; sort du
  `CMD` hérité sous une Start Command ; environnement d'une session `railway ssh` ; évaluation de
  `railway.ts` par la vraie CLI avec le SDK dans `.railway/` ; prise en compte des clés typées
  mais non documentées (`checkSuites`, `builder`, `watchPatterns`, `sleepApplication`,
  `restartPolicy*`, `limitOverride`) ; `preserve()` sur une variable neuve ;
  `RAILWAY_DOCKERFILE_PATH` relatif ; identifiant de région ; « Deploy Latest Commit » et premier
  déploiement face à « Wait for CI » ; bord réel (`X-Forwarded-*`, `trusted_proxies`), NTP
  sortant d'Authelia ; disponibilité des libellés ; coûts réels.
- Côté Hermes : la politique d'exécution de « salon » de l'api_server (`room_execution_policy`)
  n'est couverte que par la garde, sans test dédié ; l'échec ouvert de la découverte des greffons
  n'est couvert que par un test sur l'image épinglée et l'alerte de `/v1/meta` ; même uid pour
  l'agent et le tableau de bord (faille de Hermes elle-même) ; le tableau de bord authentifié reste
  un shell du propriétaire.
- Côté identité : un jeton de rafraîchissement révoqué ou rejoué laisse le navigateur en 503
  (Authelia répond 500) ; expiration à 7 jours et fenêtre glissante non mesurées ; rafale de
  premiers facteurs non bornée ; effet du mode « under attack » sur Hermes supposé.
- Côté CI : l'absence d'annulation des runs en attente par le groupe de concurrence par exécution
  ne se voit que sur GitHub, sur plusieurs pushs rapprochés (vaut aussi pour `ci.yml` depuis
  `7a088c7`).

### Relecture indépendante de P2 : traitement

Trois relectures (sécurité offensive, exactitude, exploitation) sur `21eeb5d` ; 21 constats. Chaque
constat a été **revérifié** (source de Hermes `f97608f`, doc Railway locale, image construite),
puis corrigé avec un test qui échoue sans la correction, ou documenté. Aucun n'a été réfuté :
tous sont réels ; deux sont traités par la documentation seule, par décision du propriétaire ou
faute de pouvoir mesurer hors de Railway (n° 10 et 11).

Commits (aucun `Co-Authored-By`) :

| Commit | Sujet |
|---|---|
| `c241257` | fix(hermes): guard hooks and scripts of every profile and read s6 values like with-contenv |
| `5609313` | fix(hermes): point the Railway PID 1 refusal to the recovery procedure |
| `dd9c628` | fix(identite): stop logging the owner's identifier |
| `0a13f63` | test(hermes): wait for the fake model before concluding that no request was sent |
| `98d50a8` | fix(acp-poste): close sentinel bypasses and describe the tool_call bridge as Hermes runs it |
| `9022608` | fix(railway): refuse any linked project other than acp and require Node 22.6 |
| `7a088c7` | ci: never cancel ci.yml runs outside PRs and fail on leftover test resources |
| (commits de documentation qui suivent) | docs: … |

| N° | Constat (gravité) | Traitement | Preuve |
|---|---|---|---|
| 1 | Garde des `hooks/`/`scripts/` limitée à la racine ; script cron de profil exécuté sous l'uid 10000 (haute) | **corrigé** : `hooks/` et `scripts/` de chaque profil inspectés, exigés vides puis root 0755 ; lien sous `profiles/` refusé ; tâches cron à script signalées par `diagnostiquer` | reproduit sur l'image d'avant (`acp-hermes:p2fix0`, `21eeb5d`) : volume avec profil `intrus` et tâche cron à script, redémarrage sans refus, témoin `uid=10000(hermes)` ; image corrigée : `scripts/` du profil à root, injection refusée (« Permission denied »), démarrage sur un volume restauré qui en contient refusé (`test_hooks_scripts_refus[profil_scripts\|profil_hooks]`) ; 5 tests de l'image échouent sur l'ancien module |
| 2 | `diagnostiquer` sous s6 : 29 faux constats sur un conteneur sain (moyenne) | **corrigé** : un seul « \n » final retiré, comme `with-contenv` ; test unitaire réécrit avec des fichiers terminés par « \n » | avant : « 29 constat(s) ; code 1 » sur un conteneur sain (relevé ici aussi) ; après : `test_diagnostiquer_sous_s6_sur_un_conteneur_sain` → « aucun constat ; code 0 » ; `test_diagnostiquer_source_environnement` et `test_lire_env_s6_…` échouent sur l'ancien module |
| 3 | Pont `tool_call` mal décrit : Hermes le déballe avant la garde (moyenne) | **corrigé** (description et tests) : commentaire, `image.md` § 5 et § 8 ; test renommé `test_pont_tool_call_non_resolu_refuse` ; ajout `…_vers_un_outil_admis` (todo_list s'exécute) et `…_juge_l_outil_sous_jacent` avec témoin négatif | 4 tests verts ; le témoin négatif exécute terminal à travers le pont sans `acp-poste`. Pas de faille (la garde juge l'outil réel) : ces tests passent aussi sur l'ancien code, ce qui est attendu |
| 4 | Sentinelle contournable (options à valeur, `HERMES_HOME` non normalisé) (basse) | **corrigé**, plus deux contournements trouvés ici : `hermes gateway` nu et `hermes serve` ; recensement contre l'analyseur réel de Hermes | 16 nouveaux cas + lien + recensement : 14 échouent sur l'ancien `__init__.py` |
| 5 | Feuille de route « P5 » contraire au plan d'autonomie (basse) | **corrigé** : message de refus de `kanban_create`, commentaires, `plugin.yaml`, `image.md` alignés sur P4 ; réadmission abandonnée | `test_garde_liste_blanche` et le test de contrat du worker kanban exigent le nouveau message |
| 6 | Session « au plus 7 jours » contredite (basse) | **documenté** : `railway.md` § 5.3 (7 jours sans rafraîchissement, fenêtre supposée glissante, cookie Hermes de 30 jours) | lecture de `cookies.py:38` |
| 7 | Preuves périmées dans `image.md` (basse) | **documenté** : chiffres rattachés à `efbf7b0` (partie 1), renvoi ici | — |
| 8 | Test P1 affaibli (`\|\| true`) sans contrôle de vie du modèle (basse) | **corrigé** : attente du modèle factice, journal exigé | contrat vert ; un modèle absent fait désormais échouer la fixture |
| 9 | Étape finale d'`image.yml` qui ne fait que nettoyer (basse) | **corrigé** : nettoyage puis `exit 1` s'il restait des ressources | `test_image_yml_echoue_s_il_reste_des_ressources_de_test` (échoue sur l'ancien `image.yml`) ; run CI ci-dessous |
| 10 | `vision_analyze` lit toute image locale (basse) | **documenté** (décision du propriétaire : outil gardé) : `image.md` § 10, avec la parade possible | lecture de la source (`vision_tools.py:875`, `image_source.py:71-99` et `173-177`), non exécuté |
| 11 | Sauvegardes posées à la main, absentes de l'IaC (moyenne) | **documenté** : `railway.md` § 1, § 3 (lire aussi les modifications de volume), § 4.7, § 4.8 (arrêt si le plan touche aux sauvegardes, PR qui les déclare), § 12 | comportement du moteur non mesurable hors de Railway |
| 12 | Installation de la CLI qui configurerait les agents (moyenne) | **documenté** : `railway.md` § 2.3 (installation sans agent, interdits, contrôle des MCP) | `rw_full.txt:16958-16972`, `23074-23092` |
| 13 | Refus PID 1 sans procédure (moyenne) | **corrigé** : message d'`acp-entree` adapté sur Railway + `railway.md` § 10 f | `test_entree_refuse_hors_pid1_sur_railway` |
| 14 | Procédure non exécutable dans l'ordre (basse) | **documenté** : limites via la page Workspace Usage ou après `railway login`, commande `ssh keys add` au § 4.9 et § 11, `railway login` au § 4.11 et § 10 b | — |
| 15 | Prérequis WSL incomplets (basse) | **documenté** et `engines` à `>=22.6.0` : distribution à installer (constaté : seule `docker-desktop`), Node ≥ 22.6, compte GitHub relié | `wsl -l -v` relevé ici |
| 16 | Dépôt public : libellés et identifiant publiés (basse) | **corrigé** (identifiant retiré du journal d'`identite`) et **documenté** (libellés publics, masquage § 7) | `test_demarrage_nominal_et_config_valide` et `test_railway_iac_…` exigent l'absence de l'identifiant |
| 17 | Garde d'environnement, pas de projet (basse) | **corrigé** : refus si le projet lié n'est pas `acp` (ou inconnu) ; identifiant du projet non vérifié (n'existe qu'après `railway init`, dit) | `verifier.mjs` : 2 refus de plus ; sur l'ancien `railway.ts`, « 2 écart(s) » |
| 18 | Rollback sans avertissements (basse) | **documenté** : § 5.4 et § 9 (empreinte scellée restaurée, 72 h sur Hobby) | `rw_full.txt:4938-4946`, `29547` |
| 19 | `ci.yml` annulé par un push suivant (basse) | **corrigé** : groupe par exécution hors PR ; § 7.2 vérifie aussi `ci.yml` | `test_ci_yml_n_annule_aucun_run_hors_pr` (échoue sur l'ancien `ci.yml`) |
| 20 | « Redeploy » conseillé à tort sur 503 (basse) | **documenté** : § 4.6 (découverte non mise en cache si elle échoue) | lecture de `self_hosted/__init__.py:178-206` |
| 21 | Clé SSH dédiée utilisée depuis le WSL des agents (basse) | **documenté** : mode opératoire au § 2.4 et § 11 | — |

Écarts au plan de correction, justifiés :
- n° 1 : les tâches cron à script sont **signalées** par `diagnostiquer`, pas refusées au démarrage :
  sans script dans des `scripts/` exigés vides et à root, elles échouent (« Script not found »), et
  refuser un volume pour une tâche inerte bloquerait sans rien protéger ;
- n° 4 : au-delà du constat, `hermes gateway` nu (qui lance la passerelle) et `hermes serve` (le
  serveur du tableau de bord) sont visés ; un `HERMES_HOME` de profil (`/opt/data/profiles/x`) aussi ;
- n° 10 : aucune restriction d'argument ajoutée à la garde (elle casserait les images jointes par
  chemin local) ; la décision reste au propriétaire ;
- n° 17 : l'identifiant du projet n'est pas vérifié (il exigerait une PR de plus entre `railway
  init` et le premier plan) ; la lecture du plan reste la garde.

Preuves locales (25/09/2026 ; images **reconstruites depuis le worktree** au commit `7a088c7`,
`acp-hermes:p2fix`, `acp-hermes-tests:p2fix`, `acp-identite:p2fix` ; Windows 10, Docker 29.5.3,
pytest 9.1.1, Python 3.12.10, Node 24.19.0) :
- dans l'image : `docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site acp-hermes-tests:p2fix -m pytest -v -rA /opt/acp-tests/image`
  → **242 réussis**, 0 échec, 0 ignoré (1 min 43 s) ; 26 de plus qu'avant la relecture ;
- contrat : `PYTHONUTF8=1 ACP_IMAGE=acp-hermes:p2fix ACP_IMAGE_TESTS=acp-hermes-tests:p2fix ACP_IMAGE_IDENTITE=acp-identite:p2fix python -m pytest -s -v -rA hermes/tests/contrat`
  → **103 réussis**, 0 échec, 0 ignoré (12 min 18 s) ; mémoire d'Authelia 0,721 Gio à 10 premiers
  facteurs, 1,350 Gio à 20 (54,0 % de la limite), témoin sous 1 Gio tué (OOM, 137) ;
- navigateur : `ACP_E2E_OBLIGATOIRE=1 … python -m pytest -s -v -rA hermes/tests/e2e` → **1 réussi**
  (43 s) ; Chromium de Playwright révision 1234 déjà présent, rien téléchargé ;
- suite du dépôt (`python -m pytest -q`, venv Python 3.12.10) : **282 réussis**, 0 ignoré (dont 42
  de `test_railway_iac.py`) ; `check_version.py`, `check_engine_frozen.py`, `check_lock.py` : code 0 ;
- IaC : `npm run --prefix .railway verifier` : `tsc` sans erreur, gabarits refusés, **onze** autres
  refus attendus (dont « autre projet lié » et « projet lié inconnu »), graphe d'essai conforme ;
- **chaque correction rejouée sur le code d'avant** (nouveaux tests, ancien code) : 7 échecs dans
  `test_demarrage.py`, 15 dans `test_sans_shell.py` (sentinelle et message de `kanban_create`),
  4 dans `test_railway_iac.py`, 2 écarts de `verifier.mjs` ; reproduction du n° 1 ci-dessus ;
- `git diff --check` propre ; aucun conteneur, volume ni réseau restant (comparaison avant et
  après).

Intégration continue des corrections (branche poussée le 25/09/2026, sommet `5e77686`) :
- `image.yml` [36104820150](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36104820150)
  **succès** : Node v22.23.2, `tsc` et `verifier.mjs` verts (dont « autre projet lié » et « projet
  lié inconnu » refusés) ; condensats de Hermes et d'Authelia confirmés ; **242** réussis dans
  l'image, **103** au contrat, **1** au navigateur (Chromium téléchargé par la CI) ; 0 échec,
  0 ignoré ; mémoire d'Authelia 0,727 Gio à 10, 1,287 Gio à 20 (51,5 % de la limite) ; étape
  finale : « Aucun conteneur, volume ni réseau acp-contrat-* ne restait. » ;
- `ci.yml` [36104820007](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36104820007)
  **succès** : poste Windows **282 réussis** ; poste Linux **273 réussis, 9 ignorés** (les 9 tests
  propres à Windows déjà notés en P0) ; moteur gelé, 74 tests.
- Un seul push pour les neuf commits : la CI n'a tourné que sur le sommet, pas sur chaque commit
  intermédiaire (les suites locales complètes aussi, sur l'arbre final).

Non vérifié après la relecture (en plus de la liste ci-dessus) : aucune des attaques en direct sur
Authelia que la relecture de sécurité a laissées de côté (second sujet, jeton d'une autre audience,
rafraîchissement : couvertes par les tests existants, non rejouées en attaque) ; la recherche de
secrets dans l'historique Docker et Git ; le contournement de la sentinelle par un point d'entrée
qui ne passe pas par `sys.argv` de `hermes` (limite dite, `image.md` § 10) ; le comportement réel du
moteur de la CLI face aux sauvegardes et à `ctx.projectName` (Railway seulement).

## 7. Chaîne d'outils Windows

La référence est `packaging/windows/toolchain.json` : Qt **6.8.3**
`win64_msvc2022_64`, MSVC 2022, CMake et Ninja. Desktop CI utilise `windows-2022`
(l'étiquette `windows-2025` sert Visual Studio 2026 depuis juin 2026). Inno Setup sert
à l'empaquetage.

**Python** : le venv doit venir de python.org, jamais de l'alias Microsoft Store :
l'interpréteur réel d'un venv Store sort du Job Object et les tests d'arbre de
processus du poste échouent. `scripts/setup.ps1` le refuse.

Installation de Qt dans un environnement d'outillage séparé :

```powershell
python -m venv "$env:USERPROFILE\.acp-tools\aqt-venv"
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m pip install aqtinstall
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 --outputdir "$env:USERPROFILE\Qt"
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
```

Contrôles courants depuis la racine du worktree :

```powershell
./scripts/setup.ps1                                   # venv python.org, poste, contrat, npm
.venv\Scripts\python.exe -m pytest -q                 # poste, contrat, outillage
.venv\Scripts\python.exe scripts/check_engine_frozen.py
.venv\Scripts\python.exe scripts/check_version.py
.venv\Scripts\python.exe scripts/check_lock.py
npm ci ; npm run test:engine
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
```

Le verrou Python se recompile dans un conteneur `python:3.12-slim`
(`scripts/lock_python.ps1`), jamais sur le poste.

## 8. Pièges connus

- `core.autocrlf=true` sur ce poste : l'arbre de travail est en CRLF, l'index en LF.
  Vérifier `git diff --cached --check` et l'absence de `\r` dans les blobs indexés.
- Sous Git Bash, `git show <étiquette>:<chemin>` est mal converti en chemin Windows :
  préfixer par `MSYS_NO_PATHCONV=1` ou passer par PowerShell.
- Release traite les avertissements du compilateur comme des erreurs ; un succès Debug
  ne le remplace pas. MSVC Release applique `/W4 /WX` : employer `QStringLiteral`.
- Éditions de liens MSVC `LNK1168`/`LNK1104` sur un exécutable de test : relancer la
  compilation incrémentale ; ne pas conclure sans un build complet réussi.
- Ne pas lancer pytest pendant une compilation MSVC : sous forte charge, des tests
  temporisés du runner local et de la sonde Codex échouent (voir § 4, preuves).
- Un exécutable Qt Test peut échouer sans rien écrire : le lancer avec
  `-o <rapport-absolu>,txt` et lire le rapport. CTest compte « Passed » un test qui se
  déclare ignoré (`QSKIP`) : lire les totaux Qt pour les ignorés.
- Pour Ninja/MSVC, garder la langue des sorties `/showIncludes` cohérente
  (`VSLANG=1033`) ; voir `docs/desktop-msvc-cache-recovery.md`.
- Inno Setup installé par utilisateur se trouve sous
  `%LOCALAPPDATA%\Programs\Inno Setup 6`.
- Une ligne d'état Claude Code réglée sur l'ancien module
  `acp_worker.claude_statusline` doit passer à `acp_poste.claude_statusline`.
- Les tests ne visent jamais un Hermes, un volume ou une base contenant des données.
- Sous Git Bash, `docker run … /opt/…` voit ses chemins convertis en chemins Windows :
  préfixer par `MSYS_NO_PATHCONV=1`.
- L'image ACP refuse de démarrer sans les trois variables OIDC : pour une commande
  ponctuelle, `docker run --rm --init --entrypoint /opt/hermes/.venv/bin/hermes <image>
  --version` ; pour un conteneur complet, voir `hermes/tests/contrat/conftest.py`.
- Un script cont-init en échec ne stoppe pas les suivants : toute garde qui doit agir
  avant l'amorçage de Hermes va dans le crochet `S6_STAGE2_HOOK`.
- **Déclarer un `ENTRYPOINT` remet à vide le `CMD` hérité** : dans `hermes/image/Dockerfile`,
  `CMD ["gateway","run"]` doit rester après `ENTRYPOINT`.
- **`docker run --init` avec l'entrée de l'image est refusé** (`acp-entree` exige le PID 1) ; pour
  une commande ponctuelle, passer `--entrypoint` explicitement (ci-dessus).
- **Maintenance** : Start Command `/bin/sh -c "exec sleep infinity"`, jamais `sleep infinity` nu
  (arguments hérités) ; chemin de santé vidé pendant la maintenance (`railway.md` § 10).
- **Clé SSH Railway dédiée, retirée après chaque opération** (`railway ssh keys remove --2fa-code`,
  preuve : `railway ssh keys` vide), puis `railway logout`.
- **Ne jamais annuler `image.yml` à la main** sur la branche déployée : « Wait for CI » ignore un
  run annulé dès qu'un autre workflow a réussi.
- **Aucun `railway config apply` entre une restauration de sauvegarde et la PR qui réaligne
  `railway.ts`** ; jamais `railway config pull` sans `--json` (il réécrit `railway.ts`).
- `identite/**` et `.railway/**` sont en LF (`.gitattributes`), comme `hermes/**`.
- Les tests de contrat exigent aussi Node.js ≥ 22 et `npm ci --ignore-scripts --prefix .railway`
  (`test_railway_iac_contrat.py` évalue `railway.ts`) ; sans eux ils **échouent**, jamais ignorés.
  Sous Windows, les lancer avec `PYTHONUTF8=1` (sinon des `UnicodeEncodeError` dans les `print` de
  preuve).
- La CLI Railway se lance sous **WSL** (doc Railway) ; `node_modules` de `.railway/` s'installe sur
  la plateforme qui évalue le fichier (WSL pour la CLI, Windows pour `verifier.mjs` local).
