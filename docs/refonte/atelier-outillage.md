# Outillage du chantier « atelier »

Manifeste d'outillage du chantier « atelier » (brief du propriétaire du 11 octobre 2026, décisions D165 à D169 de
[plan.md](plan.md) ; état et matrice des écarts : [atelier.md](atelier.md)). Relevé le **11 octobre 2026** dans la
session cloud Linux du chantier, sur la branche `claude/wonderful-brahmagupta-rlbkuj` partie de `main` (`85b458b`,
ACP 1.0.1).

Conventions : **mesuré** veut dire observé dans cette session, avec la commande ; une citation `chemin:ligne` vaut
pour l'arbre de travail du 11 octobre, sauf mention « à `85b458b` » (fichier relu au commit de base, parce que le
chantier le modifie en parallèle). Les fichiers encore en cours d'écriture sont cités par le nom de la constante ou
de la fonction, qui fait foi si la ligne bouge.

Sommaire : § 1 deux outillages · § 2 outillage A · § 3 référence Windows · § 4 outillage B · § 5 joignabilité réseau ·
§ 6 skills consultées · § 7 relevé de recherches · § 8 limites.

---

## 1. Deux outillages à ne pas confondre

- **A — outils de l'agent de développement.** Ils servent à écrire, construire, tester et relire ce chantier dans
  la session cloud. Rien de A n'entre dans un produit livré, n'est déployé ni n'est appelé par un workflow. Deux
  éléments de A sont versionnés : `scripts/installer_qt_linux.py`, pour reproduire l'installation de Qt (§ 2.3),
  et les trois skills de travail du dépôt sous [`outils/skills/`](../../outils/skills/README.md) (§ 6.2).
- **B — outils des agents exécutés par ACP en production.** L'agent Hermes sur Railway et les CLI lancées par
  l'exécutant. **Ce chantier ne les change pas** (§ 4).

Règle tenue : rien ne passe de A à B. Aucune skill consultée en A n'est vendorisée ni inscrite au catalogue de Hermes,
aucun outil n'est ajouté à la garde d'exécution, aucun serveur MCP n'est ouvert.

---

## 2. Outillage A : outils de l'agent de développement

### 2.1 Outils présents dans la session (mesurés le 11 octobre 2026)

Mesure : `command -v <outil>` puis `<outil> --version` (`convert -version` pour ImageMagick).

| Outil | Chemin | Version mesurée | Usage dans le chantier |
|---|---|---|---|
| git | `/usr/bin/git` | 2.43.0 | Branche, différences ; `git add` fichier par fichier (`CLAUDE.md`). |
| gh | `/usr/local/bin/gh` | 2.89.0 | API GitHub limitée aux dépôts rattachés à la session : 403 pour les autres (§ 5). |
| python3.12 | `/usr/bin/python3.12` | 3.12.3 | Générateurs et tests ; c'est la version de la CI (`desktop-ci.yml:152`, `ci.yml:134`). Sans pytest (`No module named pytest`). |
| python3 | `/usr/bin/python3` | 3.13.16 | Interpréteur par défaut du système ; ce n'est pas la version de la CI. |
| node | `/opt/node22/bin/node` | v22.22.0 | Présent ; aucun code JavaScript n'est touché par ce chantier. |
| npm | `/opt/node22/bin/npm` | 10.9.4 | Idem. |
| cmake | `/usr/bin/cmake` | 3.28.3 | Préréglage `linux-gcc-debug` (CMake 3.24 exigé : `apps/desktop/CMakePresets.json:3-7`). |
| ninja | `/usr/bin/ninja` | 1.11.1 | Générateur du préréglage (`CMakePresets.json:79`). |
| g++ | `/usr/bin/g++` | 13.3.0 (Ubuntu 24.04) | Compilateur du préréglage Linux : `CMAKE_CXX_COMPILER:UNINITIALIZED=g++` dans le cache (`apps/desktop/build/linux-gcc-debug/CMakeCache.txt:35`), résolu en `/usr/bin/g++` (`CMakeFiles/3.28.3/CMakeCXXCompiler.cmake:1`). |
| clang++ | `/usr/bin/clang++` | 18.1.3 | Présent, non utilisé par le préréglage. |
| docker | `/usr/bin/docker` | 29.8.2 | Présent ; ce chantier n'en a pas besoin (D160 le permet avec sobriété). |
| claude | `/opt/node22/bin/claude` | 2.1.296 (Claude Code) | L'agent de développement lui-même. L'exécutant épingle 2.1.283 (§ 4.2). |
| codex | — | **absent** | Aucun essai de Codex ni de son App Server dans cette session (§ 7). |
| aseprite | — | **absent** | Non utilisé : les assets viennent de sources texte (§ 7). |
| convert (ImageMagick) | `/usr/bin/convert` | 6.9.12-98 Q16 | Présent ; `magick` (ImageMagick 7) absent. Le générateur d'assets n'en dépend pas : il n'importe que la bibliothèque standard (`scripts/generer_assets_pixel.py`, en-tête d'imports, lignes 26-35). |

Environnements de test Python de la session : deux environnements virtuels, hors dépôt, portent pytest
9.1.1 et pytest-asyncio 1.4.0, les versions de `requirements/constraints.txt:18-19`. L'un, `venv312`, est dans le
dossier de brouillon de la session et tourne sous Python 3.12.3, la version de la CI. L'autre,
`/opt/acp-outils/py-venv`, tourne sous Python 3.13.16 (§ 2.2). Ce relevé ne dit pas lequel a servi à chaque
suite : seule une suite lancée sous 3.12 vaut pour la version de la CI.

### 2.2 Installé hors du dépôt

Qt n'est pas installé dans l'image de la session (`which qmake qmake6 qmllint` ne rend rien), et download.qt.io est
bloqué (§ 5). Qt 6.8.3 a donc été pris chez conda-forge, joignable.

| Élément | Emplacement | Relevé |
|---|---|---|
| Qt 6.8.3 | `/opt/acp-outils/qt683` | `qt6-main` 6.8.3, build `hb82b983_5`, n° 5, SHA-256 `9e410da286149f4b560da7b8a299caa96ff495b5b8ddf01b8e6680598331e691`, MD5 `0c81df24c1d3cf70497817311e9ee9bc`, 53 189 626 octets, licence LGPL-3.0-only, construit le 30 janvier 2026 (horodatage conda-forge), installé le 11 octobre 2026 à 18 h 58 UTC (`conda-meta/qt6-main-6.8.3-hb82b983_5.json`). 100 paquets dans `conda-meta`, dont `libgl-devel`, `libegl-devel`, `fontconfig` et les polices de `fonts-conda-ecosystem`. `QT_VERSION_STR` vaut « 6.8.3 » (`include/qt6/QtCore/qconfig.h:56`). |
| Outils Qt | `/opt/acp-outils/qt683/lib/qt6/bin` | `qmllint`, `qmlformat`, `qmltestrunner`, `qmlprofiler`, `qmlpreview`, `qmlls` présents. |
| py-rattler 0.27.1 | `/opt/acp-outils/rattler-venv` | Environnement virtuel créé par `/usr/bin/python3.12 -m venv` (`pyvenv.cfg`) ; `pip show` : py-rattler 0.27.1, aucune dépendance. PyPI : licence BSD-3-Clause, Python 3.10 ou plus, publié le 6 octobre 2026. |
| Environnement de test 3.13 | `/opt/acp-outils/py-venv` | Créé par `/usr/bin/python3 -m venv` (`pyvenv.cfg` : Python 3.13.16) ; `pip list` : pytest 9.1.1, pytest-asyncio 1.4.0. |
| Cache rattler | `~/.cache/rattler` | 1,2 Go (archives et métadonnées de conda-forge). |
| Premier script | `/opt/acp-outils/installer_qt.py` | Script ad hoc non versionné. Il listait `qt6-wayland` par défaut, absent du préfixe : il a été lancé avec d'autres spécifications, que rien ne consigne (`conda-meta/history` vide). Remplacé par le script versionné du § 2.3. |

### 2.3 Reproduire l'installation : `scripts/installer_qt_linux.py`

[`scripts/installer_qt_linux.py`](../../scripts/installer_qt_linux.py) reproduit l'installation de façon idempotente.
C'est un outil A : jamais en CI, jamais pour le poste Windows. Aucun workflow ne l'appelle.

```sh
python3.12 scripts/installer_qt_linux.py                 # préfixe par défaut /opt/acp-outils/qt683
python3.12 scripts/installer_qt_linux.py /autre/prefixe   # autre préfixe, vide ou absent
python3.12 scripts/installer_qt_linux.py --verifier       # constate seulement, ne télécharge rien
python3.12 scripts/installer_qt_linux.py --simuler        # résout et contrôle l'épingle, rien dans le préfixe
```

Ce qu'il fait (détail dans sa docstring) :

- il refuse tout autre système que Linux x86_64 ;
- il lit d'abord `<préfixe>/conda-meta` avec la seule bibliothèque standard : si `qt6-main` 6.8.3 y figure avec
  le build et le condensat épinglés, et ses trois compagnons avec lui, il dit « déjà installé », affiche les
  commandes CMake et sort en 0 sans rien télécharger ;
- tout autre préfixe non vide est refusé, jamais complété ni écrasé : autre version, autre build, autre condensat,
  compagnon manquant, dossier sans `conda-meta` ;
- py-rattler 0.27.1 manquant : il crée `<parent du préfixe>/rattler-venv` (ou le dossier de `--venv`) et y installe
  la roue manylinux x86_64 par `pip --require-hashes` (condensat de PyPI), puis se relance sous cet interpréteur.
  Cela vaut aussi pour `--simuler`, qui n'écrit rien dans le préfixe ;
- il résout `qt6-main ==6.8.3 hb82b983_5`, `libgl-devel`, `libegl-devel` et `fontconfig` sur conda-forge, puis
  refuse la résolution si la version, le build ou le SHA-256 de `qt6-main` diffèrent de l'épingle ;
- tout échec sort en code 1 avec un message en français.

Essais faits le 11 octobre 2026, rejoués à la relecture sur le script corrigé (aucune installation dans un autre
préfixe) :

| Essai | Résultat |
|---|---|
| `python3.12 scripts/installer_qt_linux.py --help` | Aide en français, code 0. |
| Préfixe existant, avec `HTTPS_PROXY` pointé vers un port fermé | « Qt 6.8.3 déjà installé dans /opt/acp-outils/qt683 : rien à faire, rien n'a été téléchargé », code 0 ; dates de `rattler-venv`, du cache et de `conda-meta` inchangées. |
| `python3 -I … --verifier` (3.13, sans py-rattler) | Code 0 : le constat n'a pas besoin de py-rattler. |
| `--simuler` vers un préfixe absent, venv existant | « Résolu : qt6-main 6.8.3 hb82b983_5 (condensat vérifié), 100 paquets au total », rien créé, code 0. |
| `--simuler` avec un venv neuf (jetable, supprimé ensuite) | venv créé, py-rattler installé par `--require-hashes` (roue tirée du cache de pip, condensat vérifié), même résolution, code 0. |
| Préfixe non conda (`docs`), conda sans Qt, `--verifier` sur un préfixe absent, option inconnue | Refus explicite, code 1 dans chaque cas. |
| Préfixe factice (dossier de brouillon) : `qt6-main` 6.8.3 d'un autre build et d'un autre condensat, compagnons présents | Refus explicite, code 1. Avant la relecture, le script le disait « déjà installé » avec un simple avertissement, code 0 : corrigé. |

Limites : seul `qt6-main` est épinglé ; ses compagnons et ses dépendances suivent conda-forge au jour de
l'installation. L'étape d'installation du script versionné n'a pas été exécutée (consigne : aucune installation dans
un autre préfixe) ; elle reprend l'appel `install(…, target_prefix=…)` du script ad hoc `/opt/acp-outils/installer_qt.py`.

### 2.4 Construire et tester sous Linux

Commandes affichées par le script, depuis la racine du dépôt :

```sh
export QT_ROOT_DIR=/opt/acp-outils/qt683
export QT_QPA_PLATFORM=offscreen
export QT_QPA_FONTDIR=/opt/acp-outils/qt683/fonts
cd apps/desktop
cmake --preset linux-gcc-debug
cmake --build --preset linux-gcc-debug
ctest --preset linux-gcc-debug
```

- `QT_ROOT_DIR` alimente `CMAKE_PREFIX_PATH` (`apps/desktop/CMakePresets.json:19-25`) ; le cache CMake de la session
  pointe bien `Qt6_DIR` vers `/opt/acp-outils/qt683/lib/cmake/Qt6`.
- `QT_QPA_FONTDIR` évite les carrés à la place du texte dans les captures hors écran
  ([historique.md](historique.md), lignes 2686-2687).
- Le préréglage Linux est secondaire : le coffre de secrets y refuse de stocker (`CMakePresets.json:77`), et hors
  Windows le chiffrement des sauvegardes n'a qu'un protecteur indisponible à la place de DPAPI
  (`apps/desktop/src/storage/ChiffrementSauvegarde.cpp:68-69` et `:90-93`). Ce qui exige DPAPI ne se prouve que sous
  Windows.

---

## 3. Référence Windows : ce qui fait foi

La chaîne Windows est décrite par [`packaging/windows/toolchain.json`](../../packaging/windows/toolchain.json),
« source unique des versions » de la compilation, de l'empaquetage et de la publication (ligne 3) :

- Qt 6.8.3, hôte `windows`, architecture `win64_msvc2022_64`, module additionnel `qtwebsockets` (lignes 14-21) ;
- image d'exécuteur `windows-2022`, Qt installé par `jurplel/install-qt-action` épinglé par commit (lignes 32-36) ;
- préréglages `windows-msvc-debug` et `windows-msvc-release` (lignes 26-29).

Le workflow **Desktop CI** ([`.github/workflows/desktop-ci.yml`](../../.github/workflows/desktop-ci.yml), ligne 1)
tourne sur `windows-2022` (ligne 74), qui porte Visual Studio 2022 17.14 (ligne 72), compile en Release et lance les
tests Qt Test et Qt Quick Test (lignes 157-161). Le préréglage `ci-windows` est « le SEUL endroit d'où une preuve de
compilation peut venir » (`CMakePresets.json:68`) ; la Release traite les avertissements comme des erreurs
(`CMakePresets.json:61`).

**La preuve qui fait foi est la Desktop CI Windows.** Une compilation Linux ne vaut que pour cette session.

| Point | Session Linux (A) | Référence Windows |
|---|---|---|
| Compilateur | GCC 13.3.0 | MSVC de Visual Studio 2022 |
| Qt | conda-forge `qt6-main` 6.8.3 `hb82b983_5` | Qt 6.8.3 `win64_msvc2022_64` par install-qt-action |
| Préréglage | `linux-gcc-debug` (Debug) | `ci-windows` (Release, avertissements en erreurs) |
| Coffre et DPAPI | absents : refus | Gestionnaire d'identification Windows, DPAPI |
| Installeur et icône | non testables | Inno Setup, `windeployqt` |

---

## 4. Outillage B : agents exécutés par ACP en production (inchangé)

### 4.1 Hermes sur Railway

- Garde d'exécution en liste blanche de 33 noms exacts, sans terminal, fichier ni exécution de code
  ([`hermes/plugins/acp-poste/garde_execution.py`](../../hermes/plugins/acp-poste/garde_execution.py),
  lignes 63-86).
- Catalogue verrouillé ([`hermes/catalogue/catalogue.lock.json`](../../hermes/catalogue/catalogue.lock.json)),
  contrôlé par `scripts/verifier_catalogue.py` en CI (`ci.yml:146`). Un seul serveur MCP actif, context7, distant en
  HTTP (lignes 1077-1101). Playwright est « reporte-p8 » (lignes 1102-1116), Figma « hors-v1 » (lignes 1117-1127).
- Les skills `frontend-design` et `skill-creator` d'`anthropics/skills` y restent **exclues** (lignes 1302-1307 et
  1318-1323, D12).

### 4.2 Exécutant

- Binaires épinglés : Codex CLI 0.156.1 et Claude Code 2.1.283
  ([`executant/binaires.toml`](../../executant/binaires.toml), lignes 38-39 et 52-53).
- Commandes imposées ([`apps/poste/src/acp_poste/commandes_agents.py`](../../apps/poste/src/acp_poste/commandes_agents.py)) :
  fonctions Codex coupées, dont `multi_agent` (lignes 48-50) ; outils Claude limités à `Read,Glob,Grep,Edit,Write`
  ou `Read,Glob,Grep` (lignes 51-52) ; `--strict-mcp-config` et `--disallowedTools "mcp__*"` (lignes 116-119) ;
  jeton par `CLAUDE_CODE_OAUTH_TOKEN`, jamais `--bare` (lignes 29-30 et 123).
- Outils Claude interdits, dont `Task` (`apps/poste/src/acp_poste/evenements.py:33`).

### 4.3 Ce que ce chantier ne touche pas

Relevé `git diff --stat 85b458b 4ea8eee -- hermes/ apps/poste/ executant/` du 11 octobre 2026 : aucune
modification sous `hermes/plugins/`, `hermes/catalogue/`, `apps/poste/` ni `executant/`. Seul
`hermes/theme/acp.yaml` est régénéré depuis les jetons de design : la teinte `mutedForeground` passe de `#9aaa9d` à
`#a3b2a5`, avec l'en-tête et les contrastes en commentaire (D165 et D169). Ce relevé couvre les commits `067acd0`
et `4ea8eee` du chantier ; il est à refaire avant la PR.

---

## 5. Joignabilité réseau (mesurée le 11 octobre 2026, 19 h 32 à 19 h 33 UTC)

Commande : `curl -sS -o /dev/null -m 25 -w '%{http_code} %{http_connect}' <URL>`, à travers le mandataire de la
session. « CONNECT 403 » : le mandataire refuse le tunnel (politique de sortie de la session). « CONNECT 000 » :
aucun tunnel, l'hôte figure dans `NO_PROXY` (c'est le cas de pypi.org, files.pythonhosted.org et
registry.npmjs.org). Mesure rejouée à la relecture, de 20 h 23 à 20 h 24 UTC : mêmes codes pour chaque ligne.

| Source | URL mesurée | HTTP | CONNECT | Lecture |
|---|---|---|---|---|
| Qt Agentic Tools | `https://github.com/TheQtCompanyRnD/agent-skills` | 403 | 200 | Refus de la session : « GitHub access to this repository is not enabled for this session ». |
| API GitHub | `https://api.github.com/repos/TheQtCompanyRnD/agent-skills/commits/main` | 403 | 200 | Même refus ; `gh api` aussi. |
| Fichiers GitHub bruts | `https://raw.githubusercontent.com/TheQtCompanyRnD/agent-skills/main/README.md` | 200 | 200 | Joignable. |
| Qt Docs MCP | `https://qt-docs-mcp.qt.io/` | 000 | 403 | Bloqué. |
| Documentation Qt | `https://doc.qt.io/qt-6/` | 000 | 403 | Bloqué. |
| Documentation des skills Qt | `https://doc.qt.io/agentictools/` | 000 | 403 | Bloqué. |
| Téléchargement Qt | `https://download.qt.io/` | 000 | 403 | Bloqué. |
| conda-forge | `https://conda.anaconda.org/conda-forge/linux-64/repodata.json` | 200 | 200 | Joignable. |
| PyPI | `https://pypi.org/project/py-rattler/0.27.1/` | 200 | 000 | Joignable, hors mandataire. |
| npm | `https://registry.npmjs.org/@openai/codex` | 200 | 000 | Joignable, hors mandataire. |
| OpenAI (Codex) | `https://developers.openai.com/codex` | 000 | 403 | Bloqué. |
| Claude Code | `https://code.claude.com/docs/en/authentication` | 200 | 200 | Joignable. |
| Claude Code | `https://code.claude.com/docs/en/legal-and-compliance` | 200 | 200 | Joignable. |
| Claude Code | `https://code.claude.com/docs/en/headless` | 200 | 200 | Joignable. |
| anthropics/skills | `https://github.com/anthropics/skills` | 403 | 200 | Même refus que pour les skills Qt. |
| anthropics/skills, bruts | `https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md` | 200 | 200 | Joignable (de même pour `skill-creator`). |
| Google Fonts | `https://fonts.google.com/` | 000 | 403 | Bloqué. |
| WCAG | `https://www.w3.org/TR/WCAG22/` | 000 | 403 | Bloqué. |
| Microsoft Learn | `https://learn.microsoft.com/en-us/windows/apps/design/style/iconography/app-icon-construction` | 000 | 403 | Bloqué. |
| Aseprite | `https://www.aseprite.org/` | 000 | 403 | Bloqué. |
| MCP Figma | `https://mcp.figma.com/mcp` | 000 | 403 | Bloqué ; le serveur MCP Figma de la session est en échec de connexion (« Proxy refused to open a tunnel: 403 Forbidden »). |
| MCP Context7 | `https://mcp.context7.com/mcp` | 000 | 403 | Bloqué depuis la session ; non utilisé. |

`git ls-remote` répond, lui, pour `TheQtCompanyRnD/agent-skills`, `anthropics/skills` et `openai/codex` (§ 6, § 7).

**MCP non utilisés.** Figma : en échec de connexion. Context7 : pas nécessaire, la documentation Qt a été vérifiée
contre les en-têtes installés (§ 7). Playwright MCP : pas nécessaire, aucun code d'interface web n'est modifié (seule
une teinte du thème web généré change). Côté B, context7 reste le serveur MCP actif de Hermes (§ 4.1) : ce chantier
n'y touche pas.

---

## 6. Skills de développement consultées

Lues comme des consignes de travail de l'agent (A). Aucune n'est copiée dans le dépôt, vendorisée ni ajoutée au
catalogue de Hermes (B).

### 6.1 `TheQtCompanyRnD/agent-skills`

- **Licence** : `LicenseRef-Qt-Commercial OR BSD-3-Clause` (fichier `LICENSE`, ligne 1) ; le README la résume en
  « BSD-3-Clause » (ligne 343). Les conditions « Qt AI Services » visent l'usage sous licence commerciale Qt
  (README, lignes 21-23) ; ce chantier s'en tient à BSD-3-Clause.
- **Lecture** : par raw.githubusercontent.com ; github.com et l'API GitHub répondent 403 (§ 5).
- **Commit** : l'API GitHub étant refusée, il n'a pas pu être lu par elle. `git ls-remote` donne `HEAD` =
  `a784c48445e34f126760f17ba0600a25f2d19968`. Les huit fichiers copiés (`LICENSE`, `README.md` et six `SKILL.md`) sont
  identiques, condensat SHA-256 par condensat, aux mêmes fichiers relus à ce commit.
- **Copies de travail** : dossier de brouillon de la session, `qt-agent-skills/` (non versionné). Seuls les `SKILL.md`
  ont été copiés : les dossiers `references/` (scripts de lint, listes de contrôle) ne l'ont pas été.

| Skill | Ce qu'elle apporte | Application dans ce chantier |
|---|---|---|
| `qt-qml` 1.2 | Règles QML : imports sans version, style précis importé seulement là où l'on personnalise, `Loader` pour l'optionnel, animations arrêtées hors écran et `Animator` pour opacité, échelle et position, `sourceSize` des images, `Accessible.*` sur les contrôles faits main, `qsTr()`. | Grille de rédaction et de relecture du QML du chantier. Le style `Basic` est déjà imposé à l'exécution (`apps/desktop/src/main.cpp:96` à `85b458b`). La prévisualisation en direct par MCP (`run_qmlPreview`) exige Qt 6.12 ou plus (`qt-qml/SKILL.md:30-31`) : non utilisée, le projet est en 6.8.3. |
| `qt-ui-design` 1.1 | Contexte à établir avant de dessiner ; échelle typographique modulaire ; navigation au clavier ; couleur jamais seule porteuse d'état ; WCAG 2.2 (contraste 4,5:1 et 3:1, ligne 205) ; chemin sans animation quand l'utilisateur réduit le mouvement (ligne 92). | Rejoint les protections de D165 : contrastes vérifiés par le générateur de jetons (`apps/desktop/cmake/generate_design_tokens.py`, fonction `measure_contrasts`, contrôles `require(...)`, lignes 317-346), profil de mouvement Réduit complet. |
| `qt-qml-review` 1.0 | Relecture en lecture seule : linter déterministe (47 règles et plus), `qmllint` facultatif, six analyses (liaisons, mise en page, chargement, délégués, états, performance). | Les six analyses servent de grille de relecture. Le linter Python (`references/lint-scripts/qt_qml_lint.py`) n'a pas été récupéré : **non exécuté**. `qmllint` 6.8.3 est disponible dans le préfixe (§ 2.2). |
| `qt-qml-test` 1.0 | Écriture de `tst_*.qml` : `TestCase`, `SignalSpy`, `tryCompare`, aides souris et clavier ; hors périmètre : CMake et lancement. | Grille pour les tests QML du chantier. Le lanceur existe déjà : `QUICK_TEST_MAIN_WITH_SETUP` (`apps/desktop/tests/qml/tst_qml_shell.cpp:36` à `85b458b`). |
| `qt-cmake-project` 1.0.1 | Commandes Qt 6 (`qt_add_qml_module`, jamais de `.qrc` pour le QML), `qt_standard_project_setup()`, version minimale explicite, politique `QTP0005`, standard C++ posé avant `find_package`. | La base s'y conforme : `find_package(Qt6 6.8 …)` et `qt_standard_project_setup(REQUIRES 6.8)` (`apps/desktop/CMakeLists.txt:58` et `:60` à `85b458b`), modules QML par `qt_add_qml_module` via `acp_add_qml_module` (`apps/desktop/cmake/AcpQmlModule.cmake:12` et `:37` à `85b458b`). Écart relevé à la règle 9 : `CMAKE_CXX_STANDARD` vient après `find_package` (`CMakeLists.txt:62-63`), mais les préréglages le posent déjà en cache (`CMakePresets.json:14`). |
| `qt-qml-profiler` 1.1 | Lance `qmlprofiler` sur une application Qt Quick 2D, analyse la trace `.qtd` (temps de trame, mémoire, cache d'images). | **Non exécutée** : ni machine de référence ni GPU dans la session (rendu hors écran). `qmlprofiler` est présent dans le préfixe. Le profilage à 60 images par seconde reste au lot F. |

### 6.2 `anthropics/skills`

Lues par raw.githubusercontent.com au commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44` (`HEAD` donné par
`git ls-remote` le 11 octobre 2026). Copies de travail : dossier de brouillon de la session, `anthropic-skills/`
(`SKILL.md` et `LICENSE.txt` des deux skills, un double du `SKILL.md` de `skill-creator` à la racine, `README.md`
du dépôt, `quick_validate.py`) ; chaque copie a le même condensat SHA-256 que le fichier relu à ce commit.
Le README du dépôt dit : « Many skills in this repo are open source (Apache 2.0) » ; `docx`, `pdf`, `pptx` et `xlsx`
sont « source-available, not open source » (ligne 20).

| Skill | Licence lue | SHA-256 du `SKILL.md` | Ce qu'elle apporte | Application |
|---|---|---|---|---|
| `frontend-design` | Apache 2.0 (`skills/frontend-design/LICENSE.txt` ; en-tête : « license: Complete terms in LICENSE.txt ») | `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3` | Direction visuelle tirée du sujet ; audace en un seul endroit ; mouvement non déclenché rare et délibéré ; mouvement réduit respecté ; textes d'interface à la voix active, erreurs qui disent quoi faire, écrans vides qui invitent à agir. | Lecture seule, comme grille de critique. Écrite pour le web : rien de son code ne s'applique au QML. Reste exclue du catalogue de Hermes (D12). |
| `skill-creator` | Apache 2.0 (`skills/skill-creator/LICENSE.txt` ; pas de champ `license` dans l'en-tête) | `dcd4803e61e913e6fc27294184cd3a71f09f5e924ff20c8a9a20173e7b3c2bcf` | Méthode pour écrire une skill, l'évaluer et ajuster sa description. | **Appliquée** aux trois skills de travail d'[`outils/skills/`](../../outils/skills/README.md) : en-tête `name` et `description`, corps court, `references/` à part. Son `scripts/quick_validate.py` (SHA-256 `67cf5703402013936c8fb75ad6a1afecd8841d45cc5e606b634eb05825fde365` au même commit), lancé hors dépôt à la relecture, rend « Skill is valid! » pour chacune. Aucun fichier de la skill n'est copié dans le dépôt. Évaluations et réglage de la description : non exécutés. Reste exclue du catalogue de Hermes (D12). |

Le verrou du catalogue relevait ces deux skills au commit `33375500bcea98d610eb30ce10ac4e59b89c390d`
(`catalogue.lock.json:1305` et `:1321`). La lecture de ce chantier porte sur un commit plus récent ; elle ne change
pas le verrou.

---

## 7. Relevé de recherches

Toutes les lectures datent du **11 octobre 2026**. Les pages de code.claude.com ont été lues dans leur version
Markdown (même adresse suivie de `.md`).

| Question | URL | Version | Conclusion | Limite |
|---|---|---|---|---|
| Authentification de Claude Code : `setup-token` | https://code.claude.com/docs/en/authentication | Page non versionnée ; Claude Code 2.1.296 dans la session, 2.1.283 à l'exécutant | `claude setup-token` ouvre le même parcours navigateur que `/login`, imprime un jeton OAuth d'un an et ne l'enregistre nulle part ; il se pose dans `CLAUDE_CODE_OAUTH_TOKEN` ; il exige un abonnement Pro, Max, Team ou Enterprise ; il ne sert qu'aux requêtes de modèle (ni Remote Control ni connecteurs claude.ai). Le mode `--bare` ne lit pas ce jeton. Cohérent avec l'exécutant (`commandes_agents.py:29-30`). | Documentation vivante, sans numéro de version ; relue à la date indiquée seulement. |
| Connexion de l'abonnement et usage par un tiers | https://code.claude.com/docs/en/legal-and-compliance | Page non versionnée | L'authentification OAuth est réservée aux souscripteurs Free, Pro, Max, Team et Enterprise, pour l'usage ordinaire de Claude Code et des applications d'Anthropic. Un développeur tiers ne peut ni offrir la connexion claude.ai dans son application, ni faire passer des requêtes par les identifiants Free, Pro ou Max pour le compte de ses utilisateurs, ni collecter, stocker ou intermédier ces identifiants ou jetons de session ; la connexion passe par le parcours d'Anthropic. Cela n'empêche pas un utilisateur final de se connecter au binaire Claude Code non modifié avec son propre abonnement. Les limites annoncées de Pro et Max supposent un usage individuel ordinaire. | Lecture littérale, pas un avis juridique. Ce relevé ne tranche pas l'application à ACP. |
| Mode sans interface, `stream-json`, `parent_tool_use_id` | https://code.claude.com/docs/en/headless | Seuils cités par la page : `--forward-subagent-text` dès 2.1.211, transfert à toute profondeur dès 2.1.219 | `--output-format stream-json` avec `--verbose` (`--include-partial-messages` pour les jetons au fil de l'eau). Les messages des sous-agents et des skills forkées portent `parent_tool_use_id` ; ceux de la conversation principale portent `null`. La page annonce que `--bare` deviendra le défaut de `-p` dans une version future. | L'exécutant coupe la délégation (`Task` interdit, outils limités : § 4.2) : `parent_tool_use_id` n'y est pas observé (D166). Si `--bare` devient le défaut de `-p`, le jeton ne sera plus lu : point à vérifier à la prochaine montée de Claude Code (D162). |
| Codex : App Server et connexion par code d'appareil | https://registry.npmjs.org/@openai/codex ; https://raw.githubusercontent.com/openai/codex/rust-v0.162.1/codex-rs/cli/src/main.rs ; https://raw.githubusercontent.com/openai/codex/rust-v0.162.1/codex-rs/app-server/README.md | `latest` = 0.162.1 (publiée le 9 octobre 2026, Apache-2.0) ; étiquette `rust-v0.162.1` = commit `092d3acd6bec3e3a14bdc7e7a2810ab628ab759d` | developers.openai.com est bloqué. Le champ `readme` du registre est vide. Le `README.md` de l'archive 0.162.1 (81 lignes) parle de `codex app`, de « Sign in with ChatGPT » et renvoie à developers.openai.com pour la clé d'API ; il ne dit rien de l'App Server ni du code d'appareil. Les sources à l'étiquette montrent une sous-commande `app-server` marquée « [experimental] » (`main.rs:173-174`) et l'option `codex login --device-auth` (`main.rs:542-543`). Le `README.md` de l'App Server décrit des méthodes JSON-RPC, dont plusieurs « experimental », sans mention d'un code d'appareil. | Lecture de sources, pas de documentation officielle. Codex absent de la session : rien n'a été exécuté. L'exécutant épingle 0.156.1, pas 0.162.1. |
| Qt : `QQuickStyle`, `AnimatedSprite`, Qt Quick Test | doc.qt.io (bloqué) ; vérification locale dans `/opt/acp-outils/qt683` | Qt 6.8.3 (`qconfig.h:56`) | `QQuickStyle::name()`, `setStyle()`, `setFallbackStyle()` (`include/qt6/QtQuickControls2/qquickstyle.h:16-18`). `AnimatedSprite` est `QQuickAnimatedSprite` (`include/qt6/QtQuick/6.8.3/QtQuick/private/qquickanimatedsprite_p.h:34` et `:59`), avec `running`, `interpolate`, `source`, `frameCount`, `frameWidth`, `frameHeight`, `frameDuration`, `frameRate`, `loops`, `paused`, `currentFrame` (lignes 37-57). Qt Quick Test : `QUICK_TEST_MAIN` et `QUICK_TEST_MAIN_WITH_SETUP` (`include/qt6/QtQuickTest/quicktest.h:20` et `:34`), module QML `QtTest` (`lib/qt6/qml/QtTest/TestCase.qml`, `SignalSpy.qml`). | En-têtes, pas la documentation : valeurs par défaut et comportements non relus. `qquickanimatedsprite_p.h` est un en-tête privé, sans garantie de stabilité en C++ : seul le type QML `AnimatedSprite` est en cause. |
| Contraste WCAG | https://www.w3.org/TR/WCAG22/ (bloqué) | WCAG 2.2, d'après le brief | Seuils repris du brief : 4,5:1 et 3:1. Le générateur de jetons les applique : 4,5:1 au texte et à l'encre sur accent, 3:1 aux bordures interactives, au focus et aux accents (seuils `$contrast` de `design/tokens/colors.json`, contrôlés par `measure_contrasts` dans `apps/desktop/cmake/generate_design_tokens.py`, lignes 317-346). La skill `qt-ui-design` donne 4,5:1 pour le texte et 3:1 pour les composants (ligne 205). | Texte de la norme non relu à la source. |
| Icône Windows | https://learn.microsoft.com/en-us/windows/apps/design/style/iconography/app-icon-construction (bloqué) | — | Tailles reprises du brief : 16, 20, 24, 32, 40, 48, 64 et 256 px ; 128 ajoutée pour les grandes icônes de l'explorateur (`scripts/generer_assets_pixel.py`, constante `TAILLES_ICO`, lignes 46-48). | Page non relue. Aucune installation Windows de test : rendu de l'icône non vérifié. |
| Aseprite | https://www.aseprite.org/ (bloqué) | — | Non installé, non utilisé. Les assets pixel sont tirés de sources texte (`design/pixel/sources/`) par `scripts/generer_assets_pixel.py`, sans dépendance externe. | Aucun export Aseprite à comparer. |
| Qt pour Linux et py-rattler | https://conda.anaconda.org/conda-forge/ ; https://pypi.org/pypi/py-rattler/0.27.1/json | `qt6-main` 6.8.3 `hb82b983_5` ; py-rattler 0.27.1 | download.qt.io étant bloqué, conda-forge fournit Qt 6.8.3 (LGPL-3.0-only) ; py-rattler 0.27.1 (BSD-3-Clause, Python 3.10 ou plus, publié le 6 octobre 2026) l'installe sans conda. | Build Linux, compilé pour conda-forge : ce n'est pas le Qt de la CI Windows (§ 3). |

---

## 8. Limites

- La seule preuve de compilation qui fait foi est la Desktop CI Windows. Les essais de la session (§ 2.3, § 2.4)
  ne valent que pour Linux.
- `qt6-main` est épinglé par version, build et condensat ; ses 99 autres paquets ne le sont pas.
- py-rattler 0.27.1 a été publié cinq jours avant ce relevé.
- Non exécutés dans ce chantier : le linter de `qt-qml-review`, `qt-qml-profiler`, la prévisualisation QML par MCP,
  les évaluations de `skill-creator`, Codex, Aseprite, l'installation de l'icône sous Windows.
- Les pages de documentation lues sont vivantes et non versionnées : le relevé vaut pour le 11 octobre 2026.
