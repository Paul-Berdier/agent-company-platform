# Reprise du travail sur un autre poste

Date d'état : 18 septembre 2026, 15 h 20, Europe/Paris.
Objet : permettre de relancer Claude Code sur un nouveau poste Windows sans rien perdre.
Ce document décrit l'état exact des branches, ce qui reste à faire, et comment
reconstituer la chaîne d'outils. Il complète `CLAUDE.md`, que Claude Code charge
automatiquement à l'ouverture du dépôt.

## 1. Où en est le code

Le Lot H est **publié** ; le chantier desktop continue sur sa branche, dont
l'intégration continue est désormais **verte**.

### Lot H, version 0.9.0 — publié

- **PR #8 fusionnée** dans `main` le 18 septembre à 11 h 42, commit de fusion `94ce876`.
- **Intégration continue verte** sur le commit de fusion.
- **Tag annoté `v0.9.0` posé sur `94ce876`** et poussé le 18 septembre à 12 h 50.
- La branche `codex/modernization-lot-h` n'a plus d'usage : tout est dans `main`.
- Livré : migrations Alembic, moteur PostgreSQL, démarrage fermé, `GET /ready`,
  outbox transactionnelle et relais, sauvegarde et restauration, images Docker,
  piles compose, verrou de dépendances, configuration Railway, trois parcours de
  vérification, outillage de tests à deux dialectes.
- Journal des modifications 0.9.0 rédigé dans `CHANGELOG.md`.
- Tag `v0.8.0` posé sur `e71ebf6` et poussé le 18 septembre : il manquait.

Preuves locales relevées sur l'ancien poste :

| Vérification | Résultat |
|---|---|
| Suite Python complète, SQLite | 2 707 réussis, 32 ignorés |
| Tests marqués `postgres`, PostgreSQL 16.15 | 28 réussis |
| Parcours journal et flux, PostgreSQL | 77 étapes sur 77 |
| Parcours automatisations, PostgreSQL | 64 sur 64 |
| Parcours sauvegarde et restauration, PostgreSQL | 47 sur 47 |

### Branche `feat/desktop-qt-railway` — client desktop natif

Créée depuis le Lot H au commit `ac1d753`. `main` y a été **fusionnée** le 18 septembre
à 12 h 53 (commit `bc43b62`). Pas de rebase, pour ne jamais réécrire un historique déjà
poussé. **Aucune pull request n'est encore ouverte** pour cette branche, et `VERSION`
vaut encore `0.9.0`.

Commits propres au chantier desktop :

| Commit | Contenu |
|---|---|
| `b7f9587` | Audit : `docs/desktop-railway-audit.md`, étude de design, jetons `design/tokens/` |
| `65e0a4a` | API : `GET /meta` (versions, capacités calculées, bornes réelles) et `POST /auth/csrf` |
| `b4e35d0` | Fondation Qt Quick : CMake, coquille QML, thème généré depuis les jetons |
| `aca114d` | Client réseau, session, coffre d'identifiants, client SSE avec reprise |
| `d1efde5` | Intégration continue Windows, installeur Inno Setup, scripts PowerShell |
| `10e01f9` | Exposition publique Railway, documents de mise à jour et de sécurité |
| `c6b5f25` | Correctifs issus de la première vraie compilation MSVC |
| `fb8b212` | Première version de ce document et `CLAUDE.md` |
| `ee318df` | Correctifs QML : singleton de couleurs masqué par Qt, familles de polices |
| `c004380` | CI : exécuteurs épinglés sur `windows-2022` (voir section 6) |
| `721c2c0` | Accessibilité : rôles, noms et actions exposés à UI Automation |
| `ce2d83c` | Client aligné sur les contrats réels de l'API ; connexion de nouveau atteignable |
| `340e2ac` | Outillage : `dev-desktop.ps1` attend l'application, vérificateur hors `build/` |
| `bb08e1c` | Avertissements « jamais compilé » remplacés par les preuves relevées |
| `3d1e79e` | Compilation et tests Release tels que le CI les exécute ; contrat des préréglages |
| `4b3d2a6` | `setup.ps1` refuse un venv bâti sur le Python du Microsoft Store |

**Première exécution réelle, 18 septembre après-midi.** L'application a été lancée
contre une API locale (`uvicorn`, base SQLite jetable dans le répertoire de travail de
Claude, compte propriétaire amorcé par `POST /auth/bootstrap`) et pilotée par Windows UI
Automation. Elle a révélé, puis vu corriger, les défauts suivants :

- quatre écarts de contrat entre le client et l'API : `/meta` lu à plat au lieu de
  `versions.*` et `capabilities.<nom>.available` ; `email` envoyé à `POST /auth/login`
  qui exige `login` ; rôle lu dans `platform_role` au lieu de `role` ; `/ready` lu
  en `status`/`detail` au lieu de `ok`/`reason` ;
- l'écran de connexion disparaissait dès l'adresse acceptée, et la coquille n'offre
  aucune entrée de connexion : **l'authentification était inatteignable** ;
- boutons, champs, entrées de navigation et lignes de la palette invisibles ou
  inactivables pour les technologies d'assistance.

Les documents d'API lus par les tests natifs vivent dans `apps/desktop/tests/fixtures/`
et `apps/api/tests/test_desktop_contract_fixtures.py` échoue si l'API s'en écarte.

Parcours vérifié à l'écran : première ouverture, test de lien, compatibilité
« Contrat d'API 1.0, schéma d'événement 1.0 », connexion, accueil, diagnostics avec les
cinq contrôles de `/ready` et leurs raisons, navigation sans souris.

| Vérification, 18 septembre | Résultat |
|---|---|
| Suite Python complète, SQLite, Python 3.12.10 | 2 748 réussis, 35 ignorés, 0 échec |
| Compilation Debug et Release, MSVC 14.44, Qt 6.8.3 | sans erreur ni avertissement du compilateur ¹ |
| Suites natives, Debug et Release | 10 sur 10, dont 59 tests QML |
| Empaquetage à blanc local | installeur 20,3 Mo, portable 29,1 Mo, `SHA256SUMS.txt` |
| Archive portable lancée sans aucune variable Qt | démarre, DLL Qt chargées depuis l'archive |
| **Desktop CI**, run `35348431165` sur `4b3d2a6` | **vert** : 10 suites, installeur, portable |

¹ CMake émet un avertissement de Qt pour sept modules QML : leur `OUTPUT_DIRECTORY` ne se
termine pas par le chemin du module, ce qui peut gêner `qmllint`. Sans effet sur la
compilation, les tests ni l'empaquetage ; à traiter avec l'outillage QML.

Les 35 tests ignorés : 28 exigent PostgreSQL (`ACP_TEST_DATABASE_URL` absent, Docker
arrêté sur ce poste), 4 des fonctions POSIX, et 3 des liens symboliques, que Windows
n'autorise pas ici (mode développeur désactivé) : c'est l'écart avec l'ancien poste.

**Ce qui n'est toujours pas prouvé** : aucune installation sur une machine Windows
propre ; aucun binaire signé ; aucune session persistée (il faut se reconnecter à chaque
lancement, limite documentée) ; le coffre Windows n'est exercé par aucun test ; aucun
écran métier (missions, runs, conversations) n'existe ; le client n'a jamais parlé à
Railway.

## 2. Ce qui reste à faire, dans l'ordre

1. **Ouvrir la version 0.10.0** sur la branche desktop, selon la recette de `CLAUDE.md` :
   passer toutes les copies vérifiées par `scripts/check_version.py` à `0.10.0`, ouvrir
   une section `0.10.0 (préparation)` dans `CHANGELOG.md`, et changer l'en-tête
   `0.9.0 (préparation)` en `[0.9.0] - 2026-09-18`. Puis journal complet, PR, CI verte,
   fusion sur validation, tag sur le commit de fusion.
2. **Constats de revue ouverts du Lot H.** Neuf étaient annoncés ; **seuls quatre sont
   consignés**, les cinq autres étaient dans le répertoire de travail de l'ancien poste
   et sont perdus. Les quatre ont été **revérifiés et confirmés** le 18 septembre :
   - `reset_public_schema` (`packages/database/src/acp_database/testing.py:99`) efface le
     schéma `public` de n'importe quelle base PostgreSQL sans garde ;
   - la sonde de stockage de `/ready` (`apps/api/src/acp_api/readiness.py:236`) crée la
     racine, donc un volume non monté passe pour sain — et le test existant entérine ce
     comportement ;
   - le service d'événements (`apps/event-service`, `main.py:130`) diffuse deux fois un
     même identifiant quand deux livraisons se recouvrent ;
   - deux interblocages PostgreSQL (planificateur contre routes d'automatisation ; fin
     de tentative contre expiration de bail), de cause commune : le verrou consultatif
     `events.journal` est pris en milieu de transaction (`events_bus.py:584` et `:648`),
     avant d'autres verrous de lignes. Un interblocage PostgreSQL (40P01) devient un 500.
   Ordre recommandé : garde de `reset_public_schema`, sonde `/ready`, double diffusion,
   job CI PostgreSQL, puis les deux interblocages avec une règle « journal en dernier »
   et un test concurrent PostgreSQL par paire. Relancer une revue complète du Lot H pour
   retrouver les cinq constats perdus.
3. **Job d'intégration continue PostgreSQL** : il n'existe pas ; les 28 tests
   PostgreSQL ne tournent que sur un poste équipé.
4. **Test d'installation sur une machine Windows propre** (critère 8 du prompt maître),
   à partir de l'artefact `desktop-ci-<run>`.
5. **Phases suivantes du client desktop**, dans l'ordre imposé par le prompt maître :
   écrans réels (accueil, projets, conversations, missions, runs, studio, livrables),
   puis plateforme d'agents, opérations, design system, distribution, stabilisation.
   Le bureau pixel Godot reste la **dernière** phase, derrière dix critères.

## 3. Reconstituer la chaîne d'outils sur le nouveau poste

Tout s'installe sans compte Qt. Environ 10 Go au total. Seuls les Build Tools exigent
une élévation : Windows affiche alors une invite à valider. Relevé du 18 septembre :
l'ensemble s'installe en une trentaine de minutes.

### 3.1 Outils système

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --source winget --accept-package-agreements --accept-source-agreements --override "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.26100 --includeRecommended"
```

```powershell
winget install --id Kitware.CMake --exact --scope user --silent --accept-package-agreements --accept-source-agreements
```

```powershell
winget install --id Ninja-build.Ninja --exact --scope user --silent --accept-package-agreements --accept-source-agreements
```

```powershell
winget install --id JRSoftware.InnoSetup --exact --scope user --silent --accept-package-agreements --accept-source-agreements
```

```powershell
winget install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
```

```powershell
winget install --id GitHub.cli --exact --accept-package-agreements --accept-source-agreements
```

**Python : jamais celui du Microsoft Store** pour le projet (voir section 6).

### 3.2 Qt 6.8.3 pour MSVC 2022, par aqtinstall

La version est épinglée dans `packaging/windows/toolchain.json`. Qt 6.8.3 est le dernier
correctif LTS téléchargeable en source ouverte. aqtinstall s'installe dans un
environnement Python dédié, pour ne pas toucher celui du projet.

```powershell
python -m venv "$env:USERPROFILE\.acp-tools\aqt-venv"
```

```powershell
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m pip install aqtinstall
```

```powershell
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 --outputdir "$env:USERPROFILE\Qt"
```

Utiliser `python -m aqt`, **pas** `aqt.exe` : sur un poste d'entreprise, une politique de
restriction logicielle peut bloquer les exécutables placés dans le profil.

### 3.3 Variable d'environnement pour compiler

`QT_ROOT_DIR` est posée comme variable utilisateur de Windows sur ce poste :

```powershell
[Environment]::SetEnvironmentVariable('QT_ROOT_DIR', "$env:USERPROFILE\Qt\6.8.3\msvc2022_64", 'User')
```

### 3.4 Vérifier, compiler, tester, empaqueter

```powershell
./scripts/setup-desktop.ps1
```

```powershell
./scripts/build-desktop.ps1 -Configuration Release
```

```powershell
./scripts/test-desktop.ps1 -Configuration Release
```

```powershell
./scripts/package-desktop.ps1 -Configuration Release -DryRun -OutputDir "$env:TEMP\acp-dist"
```

**Toujours compiler en Release avant de pousser** : le préréglage Release traite les
avertissements comme des erreurs, pas le Debug. `setup-desktop.ps1` n'installe rien : il
constate, vérifie le contrat des préréglages CMake, et dit quoi lancer.

### 3.5 Lancer l'application contre une API locale

```powershell
./scripts/dev-desktop.ps1 -Configuration Debug
```

Le script attend la fermeture de l'application. Dans l'écran de connexion, saisir
`http://127.0.0.1:8000` et cocher « Autoriser HTTP en clair sur une adresse de
bouclage ». L'API doit tourner sur une base **dédiée** (`ACP_DATABASE_URL`), jamais sur
`./acp.db` (section 6).

## 4. Reconstituer le backend local

### 4.1 Environnement Python du projet

Créer le venv avec le Python officiel, puis lancer l'installation. `setup.ps1` refuse
désormais un venv bâti sur le Python du Store.

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
```

```powershell
./scripts/setup.ps1
```

Le script installe les paquets du dépôt en mode éditable avec les contraintes du verrou,
pilote PostgreSQL compris, puis lance `npm install`.

### 4.2 PostgreSQL de vérification par Docker

Docker Desktop doit être démarré. Le conteneur utilisé sur l'ancien poste s'appelait
`acp-pg`, sur le port local 55432.

```powershell
docker run -d --name acp-pg -e POSTGRES_USER=acp -e POSTGRES_PASSWORD=acp -e POSTGRES_DB=acp -p 55432:5432 postgres:16-alpine
```

Les tests PostgreSQL lisent :

```powershell
$env:ACP_TEST_DATABASE_URL = "postgresql+psycopg://acp:acp@127.0.0.1:55432/acp"
```

Les outils `pg_dump` et `pg_restore` n'existent que dans le conteneur. Les tests de
sauvegarde utilisent `ACP_BACKUP_PG_DUMP_COMMAND`, `ACP_BACKUP_PG_RESTORE_COMMAND` et
`ACP_BACKUP_DATABASE_URL_FOR_TOOLS` : voir `docs/persistence-and-backup.md`.

**Attention** : `reset_public_schema` et les parcours de vérification remettent le
schéma `public` à zéro. Ne jamais pointer `ACP_TEST_DATABASE_URL` ou `--database-url` sur
une base contenant des données. Les parcours refusent une base non vide ; l'outillage de
test, lui, n'a toujours pas cette garde (section 2).

### 4.3 Suites de référence

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
```

Environ 11 minutes sur ce poste. `-X utf8` évite les messages illisibles d'une console
régionale. `-rs` affiche la raison de chaque test ignoré.

## 5. GitHub

`gh` est authentifié sur ce poste (compte `Paul-Berdier`, trousseau Windows).

```powershell
gh run list --branch feat/desktop-qt-railway --limit 5
```

## 6. Pièges rencontrés

- **Python du Microsoft Store** : sur un poste neuf, `python` résout vers l'alias du
  Store, même si un Python python.org est installé. Un venv bâti dessus fait tourner
  l'interpréteur réel comme application empaquetée (MSIX), que Windows **sort du Job
  Object** du runner local : quatre tests de `apps/worker/tests/test_local_runner.py`
  échouent (`output_stream_timeout`). Correctif : venv sur python.org 3.12.
- **Image `windows-2025` de GitHub** : depuis juin 2026 elle porte Visual Studio 2026
  (`ImageOS=win25-vs2026`, https://github.com/actions/runner-images/issues/14017). Les
  deux workflows desktop sont épinglés sur `windows-2022` (Visual Studio 2022 17.14,
  le compilateur ciblé par Qt `msvc2022_64`).
- **`./acp.db` à la racine est une base de développement avec des données** (créée le
  11 septembre, 42 organisations). Tout `TestClient(app)` ou `uvicorn` lancé sans
  `ACP_DATABASE_URL` l'ouvre. La suite de tests pose sa propre base ; un script ponctuel
  doit en faire autant.
- **Docker Desktop refuse de démarrer** avec « initializing Inference manager : The file
  cannot be accessed by the system » : arrêter Docker Desktop, **renommer**
  `%LOCALAPPDATA%\Docker\run`, relancer.
- **Fins de ligne** : `core.autocrlf=true`. Les fichiers sont écrits en LF et git avertit
  de la conversion ; ce n'est pas une erreur. Une sortie redirigée depuis la console
  Windows produit du CRLF : le vérificateur `check_layout.py` le refuse dans
  `apps/desktop`.
- **Piloter le client sans souris** : Qt Quick expose l'interface à Windows UI
  Automation (`System.Windows.Automation`) ; `ValuePattern` pour les champs,
  `InvokePattern` pour les boutons, `TogglePattern` pour les cases (l'`Invoke` d'une case
  Qt ne la coche pas). Capturer la fenêtre depuis un processus déclaré « DPI-aware »,
  sinon l'image est rognée.
- **Inno Setup installé par utilisateur** va sous `%LOCALAPPDATA%\Programs\Inno Setup 6`.
- **Worktrees orphelins** sous `.claude/worktrees/` : les lister avec `git worktree list`.
- **Arbre de travail** : il contient un chantier pixel-office non commité (`apps/web`,
  `packages/pixel-office-engine`, `plugins/*/rooms`, `docs/assets`…). Ne pas le mélanger
  aux commits desktop : indexer fichier par fichier.

## 7. Phrase de reprise suggérée pour Claude Code

> Lis `CLAUDE.md` puis `docs/reprise-poste.md`. Sur `feat/desktop-qt-railway`, ouvre la
> version 0.10.0 selon la recette, rédige le journal, puis prépare la PR du client
> desktop. Ensuite, traite les constats confirmés du Lot H dans l'ordre de la section 2,
> sur une branche partie de `main`.
