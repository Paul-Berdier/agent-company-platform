# Reprise du travail sur un autre poste

État du **24 septembre 2026**, Europe/Paris. Lire aussi `CLAUDE.md` et
[le plan de la refonte](refonte/plan.md).

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
- Worktrees de travail : `.claude/worktrees/refonte-hermes` et, pour P1,
  `.claude/worktrees/refonte-hermes-p1`. **Le checkout principal
  porte un chantier Pixel Office non commité (moteur, salles, `apps/web`) : ne rien y
  modifier.** Les autres worktrees historiques peuvent contenir des travaux partiels ;
  ne pas les supprimer ni les réinitialiser sans examen.

## 2. Décisions du propriétaire

Elles priment sur les recommandations du plan (détail : `docs/refonte/plan.md`, § 1).

- Connexion au tableau de bord par **OIDC auto-hébergé** (fournisseur `self_hosted`
  de Hermes), **pas** Nous Portal. Le flux natif RFC 8252 du desktop fonctionne avec
  lui. Hermes n'a aucune liste blanche : le fournisseur d'identité ne devra accepter
  que le propriétaire. Choix du fournisseur d'identité en P2.
- Cerveau de Hermes : abonnement **ChatGPT** (`openai-codex`).
- **Rien n'est déployé sur Railway** : aucune migration de données.
- Railway **Hobby**, 2 Go, plafond de 30 $ par mois, région Europe, sans domaine
  personnalisé au départ.
- Approbations **manuelles**.

## 3. Étapes

| Étape | Objet | État |
|---|---|---|
| P0 | Branche, élagage et gel du moteur | réalisée sur `refonte/hermes-p0`, poussée ; PR #13 vers `refonte/hermes` ouverte, CI `36018143912` et Desktop CI `36018143728` vertes (§ 4) |
| P1 | Image dérivée et CI de contrat, sans Railway | réalisée sur `refonte/hermes-p1` (empilée sur P0), poussée, CI verte, sans PR (§ 5) |
| P2 | Premier déploiement Railway authentifié (OIDC) | à faire |
| P3 | Identité, français et réglages prêts | à faire |
| P4 | Discussion mobile | à faire |
| P5 | Poste en lecture et délégation kanban | à faire |
| P6 | Quotas | à faire |
| P7 | Écritures validées et signées | à faire |
| P8 | Desktop Qt rebranché | à faire |
| P9 | Exploitation, montée de version et publication | à faire |

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
  fins de ligne de l'arbre de travail diffèrent (`core.autocrlf=true`, § 6).
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

## 6. Chaîne d'outils Windows

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

## 7. Pièges connus

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
