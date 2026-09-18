# Reprise du travail sur un autre poste

Date d'état : 18 septembre 2026, 13 h, Europe/Paris.
Objet : permettre de relancer Claude Code sur un nouveau poste Windows sans rien perdre.
Ce document décrit l'état exact des branches, ce qui reste à faire, et comment
reconstituer la chaîne d'outils. Il complète `CLAUDE.md`, que Claude Code charge
automatiquement à l'ouverture du dépôt.

## 1. Où en est le code

Deux chantiers coexistent. Aucun n'est fusionné dans `main`.

### Branche `codex/modernization-lot-h` — Lot H, version 0.9.0

- **Pull request ouverte** : Paul-Berdier/agent-company-platform#8, vers `main`.
- **Intégration continue verte** sur Python 3.12 et Node 22 au commit `af08c4b`.
- Livré : migrations Alembic, moteur PostgreSQL, démarrage fermé, `GET /ready`,
  outbox transactionnelle et relais, sauvegarde et restauration, images Docker,
  piles compose, verrou de dépendances, configuration Railway, trois parcours de
  vérification, outillage de tests à deux dialectes.
- Journal des modifications 0.9.0 rédigé dans `CHANGELOG.md`.
- Tag `v0.8.0` posé sur `e71ebf6` et poussé le 18 septembre. **Le tag `v0.9.0` n'est
  pas posé** : il doit l'être seulement après la fusion de la PR #8, sur le commit de
  fusion.

Preuves locales relevées sur ce poste :

| Vérification | Résultat |
|---|---|
| Suite Python complète, SQLite | 2 707 réussis, 32 ignorés |
| Tests marqués `postgres`, PostgreSQL 16.15 | 28 réussis |
| Parcours journal et flux, PostgreSQL | 77 étapes sur 77 |
| Parcours automatisations, PostgreSQL | 64 sur 64 |
| Parcours sauvegarde et restauration, PostgreSQL | 47 sur 47 |

### Branche `feat/desktop-qt-railway` — client desktop natif

Créée depuis `codex/modernization-lot-h` au commit `ac1d753`. Elle ne contient donc
**pas** les deux derniers commits du Lot H (`d88c2f8` journal 0.9.0 et `af08c4b`
correctif d'intégration continue). Après la fusion de la PR #8, rebaser cette branche
sur `main`.

Commits propres au chantier desktop :

| Commit | Contenu |
|---|---|
| `b7f9587` | Audit : `docs/desktop-railway-audit.md`, étude de design, jetons `design/tokens/` |
| `65e0a4a` | API : `GET /meta` (versions, capacités calculées, bornes réelles) et `POST /auth/csrf` |
| `b4e35d0` | Fondation Qt Quick : CMake, coquille QML, thème généré depuis les jetons |
| `aca114d` | Client réseau, session, coffre d'identifiants, client SSE avec reprise |
| `d1efde5` | Intégration continue Windows, installeur Inno Setup, scripts PowerShell |
| `10e01f9` | Exposition publique Railway, documents de mise à jour et de sécurité |
| `c6b5f25` | Correctifs issus de la **première vraie compilation MSVC** |

Suite Python de cette branche : 2 745 réussis, 32 ignorés.

**Premier passage réel de la compilation native, 18 septembre 12 h 26** : l'application
et ses tests compilent et se lient avec MSVC 14.44 et Qt 6.8.3, zéro erreur.

| Suite native | Résultat |
|---|---|
| `tst_sse_parser` | 20 réussis sur 20 |
| `tst_api_errors`, `tst_command_registry`, `tst_session_state` | réussis |
| `tst_compatibility`, `tst_cursors`, `tst_redaction`, `tst_backoff` | réussis |
| `tst_qml_shell` | **29 réussis, 4 échecs** |

Les quatre échecs QML sont le prochain travail, décrit plus bas.

## 2. Ce qui reste à faire, dans l'ordre

1. **Corriger les quatre échecs du test QML** (`apps/desktop/tests/qml/`). Symptômes
   relevés : `tst_design_tokens.qml` lit une palette `undefined` (propriété
   `surfaceCanvas` introuvable) et `tst_status_chip.qml` ne trouve pas le type
   `StatusChip`. Cause probable : enregistrement des modules QML de thème et de
   composants dans l'exécutable de test, ou chemin d'import. Commencer par exécuter
   `tst_qml_shell.exe -o resultat.txt,txt` et lire les erreurs de compilation QML.
2. **Faire passer le workflow `desktop-ci.yml`** sur GitHub Actions : il n'a encore jamais
   tourné. Pousser la branche et lire le résultat.
3. **Fusionner la PR #8** quand la décision est prise, puis poser le tag annoté `v0.9.0`
   sur le commit de fusion, puis rebaser `feat/desktop-qt-railway` sur `main`.
4. **Neuf constats de revue de sévérité moyenne** restent ouverts sur le Lot H. Le script
   de correction prêt à l'emploi est décrit dans la section 6. Les plus importants :
   - deux ordres de verrous inverses pouvant provoquer un interblocage sous PostgreSQL :
     planificateur contre routes d'automatisation, et fin de tentative contre expiration
     de bail ;
   - le service d'événements diffuse deux fois un même identifiant si deux livraisons se
     recouvrent ;
   - la sonde de stockage de `/ready` crée la racine, donc un volume non monté passe pour
     sain ;
   - `reset_public_schema` de l'outillage de test efface le schéma de n'importe quelle
     base sans garde.
5. **Job d'intégration continue PostgreSQL et images** pour le Lot H : il n'existe pas.
6. **Phases suivantes du client desktop**, dans l'ordre imposé par le prompt maître :
   écrans réels (accueil, projets, conversations, missions, runs, studio, livrables),
   puis plateforme d'agents, opérations, design system, distribution, stabilisation.
   Le bureau pixel Godot reste la **dernière** phase, derrière dix critères.

## 3. Reconstituer la chaîne d'outils sur le nouveau poste

Tout s'installe sans compte Qt. Environ 10 Go au total. Seuls les Build Tools exigent
une élévation : Windows affiche alors une invite à valider.

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
winget install --id GitHub.cli --exact --accept-package-agreements --accept-source-agreements
```

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
restriction logicielle peut bloquer les exécutables placés dans le profil. C'est arrivé
ici.

### 3.3 Variables d'environnement pour compiler

```powershell
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
```

Pour les rendre permanentes, les poser dans les variables utilisateur de Windows.

### 3.4 Vérifier puis compiler

```powershell
./scripts/setup-desktop.ps1
```

```powershell
./scripts/build-desktop.ps1 -Configuration Debug
```

```powershell
./scripts/test-desktop.ps1 -Configuration Debug
```

`setup-desktop.ps1` n'installe rien : il constate et dit quoi lancer. Pour exécuter les
tests QML sans écran, poser `$env:QT_QPA_PLATFORM = "offscreen"`.

## 4. Reconstituer le backend local

### 4.1 Environnement Python du projet

```powershell
python -m venv .venv
```

```powershell
./scripts/setup.ps1
```

Le script installe les paquets du dépôt en mode éditable avec les contraintes du verrou.
Vérifier que le pilote PostgreSQL est présent : sans lui, 23 tests s'ignorent avec une
raison explicite.

```powershell
.venv\Scripts\python.exe -m pip install -e "packages/database[postgresql]"
```

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
une base contenant des données. Les parcours refusent désormais une base non vide ;
l'outillage de test, lui, n'a pas encore cette garde.

### 4.3 Suites de référence

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
```

Environ 15 minutes. `-X utf8` évite les messages illisibles d'une console régionale.

## 5. GitHub

```powershell
gh auth login
```

Sur l'ancien poste, l'authentification passait par le gestionnaire d'identifiants de
git, qui fournissait un jeton avec les droits `repo` et `workflow`. Sur le nouveau poste,
`gh auth login` suffit.

La PR #8 porte le Lot H. Pour suivre l'intégration continue :

```powershell
gh run list --branch codex/modernization-lot-h --limit 5
```

## 6. Pièges rencontrés sur l'ancien poste

- **Docker Desktop refuse de démarrer** avec l'erreur « initializing Inference manager :
  The file cannot be accessed by the system ». Cause : un fichier de socket obsolète
  `%LOCALAPPDATA%\Docker\run\dockerInference` impossible à supprimer. Solution qui a
  fonctionné : arrêter Docker Desktop, **renommer** le répertoire
  `%LOCALAPPDATA%\Docker\run`, relancer Docker Desktop.
- **Fins de ligne** : `core.autocrlf=true` sur ce poste. Les fichiers sont écrits en LF et
  git avertit de la conversion ; ce n'est pas une erreur. `.gitattributes` force LF sur
  les scripts, les Dockerfile et les fichiers compose.
- **Inno Setup installé par utilisateur** va sous
  `%LOCALAPPDATA%\Programs\Inno Setup 6`. Le module `DesktopToolchain.psm1` le cherche
  désormais à cet endroit aussi.
- **Limites de session Claude** : plusieurs agents parallèles ont été coupés en plein
  travail. Les worktrees orphelins se trouvent sous `.claude/worktrees/` ; les lister
  avec `git worktree list` et les supprimer après avoir récupéré leurs commits.
- Les scripts de correction de la revue du Lot H étaient prêts sur l'ancien poste dans le
  répertoire de travail de Claude, qui ne voyage pas. La liste des constats est dans la
  section 2 ci-dessus et suffit à les relancer.

## 7. Phrase de reprise suggérée pour Claude Code

> Lis `CLAUDE.md` puis `docs/reprise-poste.md`. Reprends le chantier desktop sur la
> branche `feat/desktop-qt-railway` : reconstitue la chaîne d'outils si elle manque,
> recompile, corrige les quatre échecs du test QML, puis pousse et fais passer
> `desktop-ci.yml`. Ensuite, propose-moi l'ordre pour la PR #8 et les constats de revue
> ouverts du Lot H.
