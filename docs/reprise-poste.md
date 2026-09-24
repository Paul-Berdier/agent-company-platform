# Reprise du travail sur un autre poste

État du **24 septembre 2026**, Europe/Paris. Lire aussi `CLAUDE.md` et
[le plan de la refonte](refonte/plan.md).

## 1. Où en est le chantier

ACP est en pleine **refonte « Hermes au centre »** : Hermes Agent devient le seul
serveur, le seul orchestrateur et la seule source de vérité ; ACP ne garde que l'image
Railway dérivée et ses deux greffons (à construire), le poste Windows, le client Qt et
le tableau de bord de Hermes habillé. L'ancien backend ACP (API FastAPI, base, bus
d'événements, passerelle de fournisseurs, CLI `acp`, interface web Vite) est retiré ;
il reste entier sous l'étiquette annotée **`archive/acp-0.10.0-avant-hermes`**
(commit `60a49b6`, dernière fusion de `main` avant la refonte, CI `35981934303` et
Desktop CI `35981934226` vertes sur ce commit).

- Branche d'intégration : `refonte/hermes`, partie de l'étiquette d'archive, version
  **0.11.0**.
- Une branche par étape, `refonte/hermes-pN`, PR vers `refonte/hermes`. Étiquette
  `1.0.0` seulement à la fusion finale dans `main`.
- Worktree de travail : `.claude/worktrees/refonte-hermes`. **Le checkout principal
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
| P0 | Branche, élagage et gel du moteur | réalisée sur `refonte/hermes-p0`, non poussée (§ 4) |
| P1 | Image dérivée et CI de contrat, sans Railway | à faire |
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

## 5. Chaîne d'outils Windows

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

## 6. Pièges connus

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
