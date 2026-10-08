# Reprise du travail sur un autre poste

État du **8 octobre 2026**, Europe/Paris. Notes remises à plat à l'étape P9 (part E, préparation de 1.0.0) :
l'historique de chaque étape, avec ses preuves, ses écarts et ses pièges, est recopié sans modification dans
[l'historique de la refonte](refonte/historique.md) (partie B : ces notes telles qu'au 8 octobre 2026, avant leur
remise à plat). Lire aussi `CLAUDE.md` (règles de travail), [le plan](refonte/plan.md) (décisions, § 1) et
[le manuel d'exploitation](exploitation.md).

## 1. État courant

ACP est la **refonte « Hermes au centre »** : Hermes Agent 0.21.5, épinglé par condensat, est le seul serveur,
le seul orchestrateur et la seule source de vérité ; ACP fournit son image dérivée et ses greffons, l'identité
(Authelia), l'exécutant Railway, le poste Windows facultatif, la station Qt et l'interface du tableau de bord.
L'ancienne plateforme reste entière sous l'étiquette annotée `archive/acp-0.10.0-avant-hermes` (`60a49b6`).

- **Version 0.11.0**. **1.0.0 en préparation, non ouverte** : le commit d'ouverture et le journal daté viendront à
  la fin de P9 (D129) ; la fusion dans `main` et l'étiquette `v1.0.0` attendront l'accord du propriétaire.
- **Rien n'est déployé sur Railway**. Le premier déploiement est un geste du propriétaire
  ([railway.md](refonte/railway.md) § 4).
- **Branches** : `main` = `60a49b6` (ancienne plateforme) ; `refonte/hermes`, branche d'intégration et branche
  déployée par l'IaC, porte P0 à P8 et P7 (dernière fusion : PR #21, `b9779f1`, 8 octobre 2026) ; P9 vit sur
  `refonte/hermes-p9` (parts A et D et leur relecture, tête `2243923`), `refonte/hermes-p9bc` (intégration : P7 finale,
  parts B et C ; tête `e448b7a` au 8 octobre), `refonte/hermes-p9c` (témoin, fusionnée dans `-p9bc` par `b867810`) et
  `refonte/hermes-p9e` (part E, documentation), **sans PR** ; `refonte/hermes-p8b` (partie de `b9779f1`, 8 octobre) :
  autre chantier de la station Qt, en cours, hors de ces notes.
- **Étiquettes** : `v0.2.0` à `v0.9.0` et `archive/acp-0.10.0-avant-hermes` ; ni `v0.10.0` ni `v0.11.0` (jamais
  publiées) ; aucune `v1.0.0`.
- **Intégration continue** sur `refonte/hermes` après la fusion de P7 (`b9779f1`) : CI `37795932683`, Image de
  l'exécutant `37795932983`, Desktop CI `37795932742` et Image Hermes `37795932814` : **vertes**. Runs de chaque
  étape : [preuves de 1.0.0](refonte/preuves-1.0.0.md).
- **Docker** : Docker Desktop est **arrêté** sur le poste de travail depuis le 8 octobre 2026 (souhait du
  propriétaire, D134). Aucune commande Docker en local : images, contrat, navigateur, restauration, témoin et montée
  de données se prouvent par la CI GitHub (`gh workflow run <fichier> --ref <branche>` pour les jobs manuels).

| Étape | Objet | État |
|---|---|---|
| P0 | branche, élagage, gel du moteur | fusionnée (PR #13, `29c95b5`) |
| P1 | image dérivée et CI de contrat | fusionnée (PR #14, `21d13ee`) |
| P2 | agent sans outil d'exécution, Authelia, Railway en code | fusionnée (PR #15, `21ac337`) ; rien de déployé |
| P3 | identité visuelle, français, catalogue | fusionnée (PR #16, `f59f384`) |
| P4 | projets autonomes sur Hermes | fusionnée (PR #17, `6c31522`) |
| P5 | poste connecté (protocole, inventaire, poste Windows) | fusionnée (PR #18, `b3faac0`) ; rien d'installé |
| P6 | exécutant Railway | fusionnée (PR #19, `7697a1c`) ; sonde R0 prête, non lancée |
| P8 | station Qt rebranchée sur Hermes | fusionnée (PR #20, `b715edb`) ; MCP côté poste reporté |
| P7 | questions, notifications, continuité ; dépôts réels | fusionnée (PR #21, `b9779f1`) ; aucun dépôt réel ajouté |
| P9 | exploitation, montée de version, publication 1.0.0 | **en cours**, sans PR : parts A (outillage de version, montée de Hermes répétée à blanc à chaque construction) et D (procédures, manuel) relues ; B (test de restauration R1 à R4) et C (témoin `v2026.9.21`, montée de données) exécutées par la CI, encore ouvertes ; E (documentation finale) en préparation ; F (publication) après accord |

Détail de chaque étape : [historique](refonte/historique.md), partie A (tableau des fusions) et partie B ; P9 :
[plan](refonte/plan.md) § 1 (D122 à D155) et [manuel](exploitation.md).

## 2. Décisions du propriétaire

Elles priment sur le plan (détail et dates : [plan](refonte/plan.md) § 1).

- Connexion au tableau de bord par **OIDC auto-hébergé** (fournisseur `self_hosted`), **pas** Nous Portal ; Hermes
  n'a aucune liste blanche, le fournisseur d'identité n'accepte que le propriétaire : **Authelia 4.39.28** (service
  `identite`, un seul utilisateur, passkeys).
- Cerveau de Hermes : abonnement **ChatGPT** (`openai-codex`). Approbations **manuelles**.
- Railway **Hobby**, plafond dur de 30 $ par mois (alerte à 15 $), région Europe, sans domaine personnalisé ; IaC
  `.railway/railway.ts` appliquée par le propriétaire seul ; branche déployée `refonte/hermes`.
- **Aucun outil d'exécution pour l'agent sur Railway** (ni terminal, ni fichiers, ni code, ni navigateur, ni cron, ni
  délégation, ni connexions) ; écritures de l'agent en mémoire et dans les skills soumises à validation.
- Phases P4 à P8 **remplacées** par le [plan d'autonomie](refonte/autonomie.md) : Hermes chef de projet autonome,
  aucune signature par tâche, accord explicite pour l'irréversible (push, fusion, PR, publication, dépense,
  élargissement du périmètre).
- Exécution principale sur un service Railway séparé, l'**exécutant** (D74) ; le poste Windows devient facultatif.
- Le propriétaire **fournit les comptes**, Hermes gère l'exploitation : décisions de conception **appliquées** depuis
  P6 (D74 à D155) ; les choix par défaut de P3 à P5 (D1 à D73) restent **à confirmer**. Ne lui sont soumis que les
  comptes, la dépense et l'irréversible ; pour 1.0.0, une seule question : fusion dans `main`, étiquette et branche
  déployée.

## 3. Où trouver quoi

| Besoin | Où |
|---|---|
| Règles de travail, recette de publication, interdits | `CLAUDE.md` |
| Plan validé et décisions D1 à D155 | [refonte/plan.md](refonte/plan.md) ; plan d'autonomie : [refonte/autonomie.md](refonte/autonomie.md) |
| Gestes du propriétaire : sauvegardes, restauration, montée de version, incidents | [exploitation.md](exploitation.md), puis [refonte/railway.md](refonte/railway.md) |
| Image Hermes, variables Railway, managed scope | [refonte/image.md](refonte/image.md) |
| Identité, interface, catalogue, projets, poste, exécutant, questions | [identite.md](refonte/identite.md), [interface.md](refonte/interface.md), [catalogue.md](refonte/catalogue.md), [projets.md](refonte/projets.md), [poste.md](refonte/poste.md), [executant.md](refonte/executant.md), [questions.md](refonte/questions.md) |
| Station Qt | [refonte/desktop.md](refonte/desktop.md), [desktop-build.md](desktop-build.md), [native-desktop-architecture.md](native-desktop-architecture.md), [desktop-security.md](desktop-security.md) |
| Historique des étapes P0 à P9 | [refonte/historique.md](refonte/historique.md) |
| Preuves de 1.0.0 | [refonte/preuves-1.0.0.md](refonte/preuves-1.0.0.md) |
| Journal des changements | `CHANGELOG.md` (section 1.0.0 préparée, non datée) |

**Worktrees** (sous `.claude/worktrees/`) : `refonte-hermes` (P0), `refonte-hermes-p1` à `-p8` (une par étape),
`-p7e` et `-p7f` (parts E et F de P7), `-p8b`, `-p9`, `-p9bc`, `-p9c`, `-p9e`. Les autres (`lot-*`, `desktop-*`,
`subscription-chat`, `wf_*`) datent de l'ancienne plateforme et peuvent contenir des travaux partiels : ne pas les
supprimer ni les réinitialiser sans examen. Branche locale `essai/hermes-v2026.9.21` (part C de P9, jamais poussée) :
gardée. **Le checkout principal porte un chantier Pixel Office non commité** (moteur, salles, `apps/web`) : ne rien
y modifier depuis un worktree de la refonte.

## 4. Chaîne d'outils Windows

Référence : `packaging/windows/toolchain.json` : Qt **6.8.3** `win64_msvc2022_64` (avec `qtwebsockets`), MSVC 2022,
CMake et Ninja ; Inno Setup pour l'empaquetage. Desktop CI tourne sur `windows-2022` (`windows-2025` sert Visual
Studio 2026 depuis juin 2026).

**Python** : un venv de **python.org**, jamais l'alias Microsoft Store (son interpréteur réel sort du Job Object ;
`scripts/setup.ps1` le refuse), et **hors de `%TEMP%`** (un nettoyage y a abîmé des venvs). Venv des suites du
8 octobre 2026 : `.claude/worktrees/lot-h-hardening/.venv` (Python 3.12.10, pytest 9.1.1), avec `cryptography`
47.0.0 au lieu de 50.0.1 du verrou (aucun test n'en dépend autrement) : sur un nouveau poste, refaire le venv par
`scripts/setup.ps1`.

Qt dans un environnement d'outillage séparé :

```powershell
python -m venv "$env:USERPROFILE\.acp-tools\aqt-venv"
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m pip install aqtinstall
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 -m qtwebsockets --outputdir "$env:USERPROFILE\Qt"
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
```

Contrôles courants depuis la racine du worktree (sans Docker) :

```powershell
./scripts/setup.ps1                                   # venv python.org, poste, contrat, npm
$env:PYTHONUTF8 = '1'
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider   # poste, contrat, outillage, scripts
.venv\Scripts\python.exe scripts/check_version.py
.venv\Scripts\python.exe scripts/check_engine_frozen.py
.venv\Scripts\python.exe scripts/check_lock.py
.venv\Scripts\python.exe scripts/balayer_secrets.py --arbre
npm ci ; npm run test:engine
npm ci --prefix apps/interface ; npm test --prefix apps/interface   # greffons d'interface (Vitest)
./scripts/build-desktop.ps1 -Configuration Release    # ou -QtDir <Qt>/6.8.3/msvc2022_64
./scripts/test-desktop.ps1 -Configuration Release     # 34 suites ; lire aussi les totaux Qt
git diff --check
```

Le verrou Python se recompile dans un conteneur `python:3.12-slim` (`scripts/lock_python.ps1`), jamais sur le
poste ; il produit aussi le verrou d'exécution du poste (`requirements/poste-3.12.lock.txt`). Ce qui demande Docker
(images, contrat, navigateur, bout en bout du poste et de la station, restauration, témoin, montée) passe par la CI
(`image.yml`, `executant.yml`) ; les scripts locaux `scripts/e2e-poste-windows.ps1` et
`scripts/e2e-desktop-windows.ps1` restent décrits dans l'[historique](refonte/historique.md), partie B, § 7, comme les
témoins négatifs `scripts/temoins_negatifs_p4.sh` à `_p6.sh` (Docker requis).

## 5. Pièges connus

Datés par l'étape qui les a trouvés ; détail et contexte : [historique](refonte/historique.md), partie B (§ 8, et
« Pièges (P7) » au § 6 undecies).

**Dépôt et Git**
- `core.autocrlf=true` : documents en CRLF dans l'arbre de travail, LF dans l'index ; garder ces fins de ligne à
  l'écriture, puis `git diff --check` (et `--cached`). `identite/**`, `executant/**`, `.railway/**`, `hermes/**` et
  `apps/interface/**` sont en LF (`.gitattributes`). Aucun fichier suivi ne finit par une ligne vide
  (`scripts/tests/test_fins_de_fichier.py`).
- `git stash` est commun à tous les worktrees : mettre de côté dans des fichiers, jamais dans la pile (P7).
- Branches parallèles : une branche partie d'une autre ne voit pas ce qui y est poussé ensuite ; avant d'écrire
  qu'un comportement existe, `git merge-base --is-ancestor` (P7).
- Sous Git Bash, `git show <étiquette>:<chemin>` et `docker run … /opt/…` voient leurs chemins convertis :
  préfixer par `MSYS_NO_PATHCONV=1`.
- L'outil Bash des agents réduit les barres obliques inverses d'un heredoc (`\\n` devient un vrai saut de ligne,
  `\\b` un retour arrière) : tout correctif qui en contient s'écrit par l'éditeur, puis on balaie les caractères de
  contrôle (P6, P7, P8).
- Un témoin de mutation laissé actif par une session interrompue est un piège : le marquer (`// TEMOIN`) et le
  chercher à la reprise (P8) ; les témoins de P9 vivent sur des branches jetables, jamais dans le code (D140, D155).
- Les tests ne visent jamais un Hermes, un volume ou une base contenant des données.

**Python et tests**
- Sous Windows, lancer les suites avec `PYTHONUTF8=1` (sinon `UnicodeEncodeError` dans les `print` de preuve).
- Tests de contrat : Node.js ≥ 22 et `npm ci --ignore-scripts --prefix .railway` (sans eux ils **échouent**) ;
  tests navigateur : Node ≥ 22 et `npm ci --ignore-scripts --prefix apps/interface` ; Hermes ajoute
  `?profile=default` à l'URL de « / » : comparer le chemin.
- Tests temporisés du poste sous forte charge (compilation MSVC, piles parallèles) : échecs sans rapport avec le
  code ; ne pas lancer pytest pendant une compilation (P0) ; test Windows instable connu :
  `apps/poste/tests/contrat/test_enrolement.py:78` (`ssl.SSLEOFError` du faux serveur TLS, P9).
- Greffons d'interface : bundles **committés** ; après toute modification de `apps/interface/src`,
  `npm run build --prefix apps/interface` ; une image construite avant les bundles fait échouer
  `test_bundles_servis_identiques_au_depot` ; `src/chaines.ts` emploie des espaces insécables réelles (P3, P7).
- Trames SSE d'exemple rangées en chaînes JSON (P7) ; tests qui comptent les notifications d'une pile partagée :
  filtrer **leur** projet (P7).
- Banc local des tests d'image (sans Docker) : racine au format `C:/…` ; échecs propres à Windows sans lien avec le
  code (`test_flux.py`, six de `test_meta.py`, worker de `test_cloture.py`) ; la preuve reste la CI (P7).
- L'authentificateur virtuel de Chromium est lié à sa page : recopier la passkey (CDP) avant de fermer la page ; une
  seule passkey résidente par authentificateur virtuel (P7, P9).

**Image Hermes et exécutant**
- L'image refuse de démarrer sans les trois variables OIDC ; commande ponctuelle :
  `docker run --rm --init --entrypoint /opt/hermes/.venv/bin/hermes <image> --version` (en CI) ; `--init` avec
  l'entrée de l'image est refusé (`acp-entree` exige le PID 1).
- Un script cont-init en échec ne stoppe pas les suivants : toute garde d'avant l'amorçage va dans
  `S6_STAGE2_HOOK` ; déclarer un `ENTRYPOINT` remet à vide le `CMD` hérité (garder `CMD ["gateway","run"]` après).
- Hermes diffère les outils de greffon derrière `tool_search` (appel par `tool_call`) ; le crochet
  `on_kanban_dispatch_tick` est tiré par tableau et par passage, dans la passerelle seulement (P4).
- Couture d'authentification par jeton (`token_auth_middleware`) : chemin comparé à l'identique, aucun paramètre de
  chemin sur une route machine ; son 401 est en anglais et ambigu ; derrière `BaseHTTPMiddleware`, une lecture
  bornée de `request.receive()` voit le départ du client ; fournisseur OIDC nommé `self-hosted` dans la liste,
  `dashboard.oauth.self_hosted` dans la configuration ; un exemple capturé qui porte une date d'expiration se
  redate depuis l'instant du test (P5).
- Tests de l'image : les routes de `pile_machine` appellent la copie canonique du noyau
  (`meta.sous_module_noyau(...)`), qu'un `monkeypatch` sur `pile.noyau` ne touche pas (P6).
- Exécutant : `/etc/gitconfig` ferme tout protocole sauf `https` ; URL d'un dépôt de la politique
  `https://<hôte>/<propriétaire>/<dépôt>` ; plafond de 3 projets actifs du greffon ; journal partagé entre UID : un
  fichier par UID ; avertissement « could not create PATH aliases » de Codex sous `/tmp`, sans conséquence (P6).
- `hermes import` sur un `/opt/data` à root échoue **en silence** (code 0) : forme mesurée et contrôle de sortie
  dans le manuel, § 4.5 (D137, P9).
- Montée de données : du travail en cours à l'instant de l'arrêt fait diverger la montée de son contrôle ; attendre
  le repos (D150, P9).

**Railway**
- Maintenance : Start Command `/bin/sh -c "exec sleep infinity"`, jamais `sleep infinity` nu ; chemin de santé vidé
  pendant la maintenance ([railway.md](refonte/railway.md) § 10).
- Clé SSH Railway dédiée, retirée après chaque opération (`railway ssh keys` vide), puis `railway logout`.
- Ne jamais annuler `image.yml` à la main sur la branche déployée (« Wait for CI ») ; aucun `railway config apply`
  entre une restauration et la PR qui réaligne `railway.ts` ; jamais `railway config pull` sans `--json`.
- La CLI Railway se lance sous **WSL** ; `node_modules` de `.railway/` s'installe sur la plateforme qui évalue le
  fichier.

**Poste Windows et station Qt**
- Installeur du poste : Python 3.12 de python.org installé pour tous les utilisateurs ; scripts PowerShell en UTF-8
  avec BOM ; Codex appelé par son binaire natif, jamais `codex.cmd` ; Claude Code ≥ 2.1.248 (`--restricted`),
  alors que celui de ce PC était en 2.1.239 au relevé de P5 ; ligne d'état Claude Code : module
  `acp_poste.claude_statusline` (P5).
- Ne jamais arrêter un arbre de processus Windows par le seul parent déclaré : comparer les instants de création,
  garder le Job Object ; garder une référence au `Verrou` pris (`LockFileEx`) ; tests du poste sur des emplacements
  jetables seulement (P5).
- Release traite les avertissements comme des erreurs (`/W4 /WX`, `QStringLiteral`) ; `LNK1168`/`LNK1104` :
  relancer, conclure seulement sur un build complet ; `VSLANG=1033` pour Ninja (voir
  `docs/desktop-msvc-cache-recovery.md`) ; Inno Setup par utilisateur sous `%LOCALAPPDATA%\Programs\Inno Setup 6`.
- Un exécutable Qt Test peut échouer sans rien écrire : `-o <rapport>,txt` ; CTest compte « Passed » un `QSKIP` :
  lire les totaux Qt ; la sortie d'une suite rouge ne passe pas par CTest (P8).
- Captures QML hors écran : `QT_QPA_FONTDIR` et une fenêtre construite comme `App.qml` ; une liste dont les délégués
  portent un état déclare sa clé (`JsonListModel::setCle`) ; Qt Test n'a pas de `keyClicks` pour une `QWindow` ;
  les tests QML contiennent des espaces insécables (P8).
- Au bout en bout, `/api/auth/me` rend le `sub` opaque d'Authelia ; le rejeu d'un jeton de rafraîchissement révoqué
  donne 503 ; la station ne joint `hermes-acp.test` que par le mandataire CONNECT du script (P8).

## 6. Prochaines étapes réelles

1. Avant tout : instruire le constat intermittent de la défense de P2 (session du tableau de bord qui a reçu, une
   fois, les outils du `.env` piégé après un redémarrage du conteneur : Image Hermes `37784838264`, tentative 1 ;
   détail : [preuves](refonte/preuves-1.0.0.md) § 5). Il est dit dans les limites du journal 1.0.0 préparé.
2. Fin de P9 : clore les parts B et C (preuves finales relevées), finaliser le manuel, relecture indépendante de
   toute P9, commit d'ouverture 1.0.0 puis journal daté, PR de `refonte/hermes-p9` vers `refonte/hermes`, quatre
   workflows verts, fusion.
3. PR de `refonte/hermes` vers `main` ; une seule question au propriétaire (fusion, étiquette `v1.0.0` sur le commit
   de fusion, branche déployée) ; premier run de `Desktop Release` (brouillon non signé).
4. Gestes du propriétaire sur Railway : premier déploiement ([railway.md](refonte/railway.md) § 4), répétition de
   maintenance puis de restauration avant d'y mettre des données ([exploitation.md](exploitation.md) § 5), sonde R0
   de l'exécutant (railway.md § 13.2), canal de notification et premier dépôt réel (railway.md § 14).
5. Ensuite : MCP côté exécutant (reporté depuis P8), première montée réelle de Hermes par la procédure du manuel
   (§ 6), confirmation par le propriétaire des choix D1 à D73.
