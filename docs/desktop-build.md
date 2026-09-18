# Compiler le client desktop Windows

Public : développeur du client natif C++23 / Qt 6 / Qt Quick (`apps/desktop`).
Version du produit : `0.9.0` (fichier `VERSION` à la racine).
État de ce document : 18 septembre 2026.

## Avertissement, à lire avant tout le reste

**Rien de ce qui suit n'a été compilé.** Aucun poste du projet ne dispose de Qt, de
CMake, de Ninja ni de MSVC ; le relevé figure dans
[`docs/desktop-railway-audit.md`](desktop-railway-audit.md), section 11. La seule
preuve de compilation recevable pour ce chantier vient du workflow
`.github/workflows/desktop-ci.yml`, sur un exécuteur Windows de GitHub. Tant que
ce workflow n'est pas passé au vert sur une révision, le code natif de cette
révision est du texte non vérifié, et cette chaîne d'outils est du texte non
exécuté sur une compilation réelle.

Ce qui **a** été exécuté sur un poste, et qui n'est donc pas une promesse :
l'analyse syntaxique des cinq scripts PowerShell, la validité YAML des deux
workflows, et les chemins de refus des scripts (prérequis absents, sources
absentes) — voir la section « Ce qui a été vérifié et comment » en fin de document.

## 1. Prérequis

| Outil | Rôle | Obligatoire |
|---|---|---|
| Visual Studio 2022, charge « Développement Desktop en C++ » (x64) | compilateur, éditeur de liens, `signtool` | oui |
| CMake | configuration et compilation par préréglage | oui |
| Qt `6.8.3`, architecture `win64_msvc2022_64` | Qt Quick, Qt Network, `windeployqt` | oui |
| Ninja | seulement si le préréglage MSVC emploie le générateur Ninja | selon le préréglage |
| Inno Setup 6.4 ou plus récent | fabrication du programme d'installation | empaquetage seulement |

La version de Qt est **épinglée**, au même titre que la base d'image Python par
digest et que le verrou haché des dépendances. Elle vit à un seul endroit :
`packaging/windows/toolchain.json`. Ne la recopiez nulle part.

`6.8.3` est le dernier correctif de la série LTS 6.8 publié en source ouverte ; les
versions `6.8.4` et suivantes de cette série sont réservées aux licences
commerciales et ne sont pas téléchargeables par `aqtinstall`.

### Constater ce qui manque

```powershell
./scripts/setup-desktop.ps1
```

Ce script **n'installe rien**. Il constate, et il affiche pour chaque manque la
commande exacte à lancer vous-même. Il rend `0` si tous les prérequis obligatoires
sont présents, `2` sinon. `-Json` produit le même inventaire en JSON.

Un poste vierge obtient une sortie de ce genre :

```text
[MANQUANT] CMake (>= 3.28 recommandé pour les préréglages v8)
           cmake introuvable dans le PATH
           À lancer vous-même : winget install --id Kitware.CMake
```

## 2. Où Qt est cherché

Tous les scripts résolvent Qt dans cet ordre, du plus explicite au plus deviné :

1. le paramètre `-QtDir` ;
2. la variable d'environnement `ACP_QT_DIR` ;
3. `QT_ROOT_DIR` — posée par l'action `jurplel/install-qt-action` en intégration continue ;
4. `Qt6_DIR` — pointe sur `lib/cmake/Qt6`, la racine est déduite en remontant de trois niveaux ;
5. `C:\Qt\6.8.3\msvc2022_64`.

Un répertoire n'est retenu que s'il contient `bin\windeployqt.exe`. Si aucun
candidat ne convient, les scripts refusent explicitement plutôt que de continuer
avec un Qt approximatif.

## 3. Contrat avec `apps/desktop`

Cette chaîne d'outils ne produit pas `apps/desktop` : ce répertoire appartient au
lot fondation desktop. Elle attend de lui quatre choses, et **refuse** si l'une
manque, au lieu de deviner.

| Attendu | Valeur | Vérifié par |
|---|---|---|
| Fichier de préréglages | `apps/desktop/CMakePresets.json` | `build-desktop.ps1`, code `3` |
| Noms de préréglages | `windows-msvc-debug` et `windows-msvc-release`, en configuration, compilation **et** test | `cmake --preset`, `ctest --preset` |
| Répertoire de compilation | `binaryDir` = `${sourceDir}/build/${presetName}` | présence de `CMakeCache.txt`, code `3` |
| Nom de l'exécutable | `AgentCompanyPlatform.exe` | recherche dans l'arbre de compilation, code `3` |
| Sources QML analysables | `apps/desktop/qml` | `package-desktop.ps1`, code `3` |

Ces cinq valeurs sont déclarées dans `packaging/windows/toolchain.json`. Si le lot
desktop range ses QML ailleurs ou nomme ses préréglages autrement, c'est ce fichier
qu'il faut corriger — un seul endroit, jamais les workflows ni les scripts.

**Modules Qt additionnels.** `qt.modules` est vide. Si `apps/desktop` a besoin d'un
module qui n'est pas essentiel (par exemple `qtmultimedia` ou `qtwebsockets`), il
faut l'ajouter là. Sans cela, la configuration CMake échouera en intégration
continue avec le message de Qt lui-même : c'est le comportement voulu, préférable à
une compilation qui réussirait sur un poste et pas sur un autre.

## 4. Compiler

```powershell
./scripts/build-desktop.ps1 -Configuration Debug
./scripts/build-desktop.ps1 -Configuration Release -Clean
./scripts/build-desktop.ps1 -Configuration Release -QtDir "C:\Qt\6.8.3\msvc2022_64"
```

Le script :

1. refuse si `apps/desktop/CMakePresets.json` est absent ;
2. résout Qt, refuse si rien de valide n'est trouvé ;
3. charge l'environnement MSVC x64 **dans sa seule session**, via `vswhere` puis
   `Launch-VsDevShell.ps1` — la méthode documentée par Microsoft pour initialiser
   un environnement de compilation depuis un script
   ([Microsoft Learn](https://learn.microsoft.com/en-us/visualstudio/ide/reference/command-prompt-powershell),
   consultée le 18 septembre 2026) ;
4. expose Qt à CMake par `CMAKE_PREFIX_PATH` et ses DLL au `PATH` de la session ;
5. lance `cmake --preset <préréglage>` puis `cmake --build --preset <préréglage>`.

Aucun réglage durable du poste n'est modifié : ni `PATH` machine, ni registre, ni
variable utilisateur.

## 5. Tester

```powershell
./scripts/test-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Debug -Filter "Session"
```

`ctest --preset <préréglage> --output-on-failure` est le point d'entrée : les tests
Qt Test et Qt Quick Test sont ceux que le préréglage de test déclare. Un test en
échec fait échouer le script avec le code `5`. Aucun résultat n'est converti en
avertissement, aucune suite n'est ignorée silencieusement.

## 6. Développer

```powershell
./scripts/dev-desktop.ps1
./scripts/dev-desktop.ps1 -SkipBuild
./scripts/dev-desktop.ps1 -ServerUrl "https://exemple.up.railway.app"
```

Compile puis lance l'application avec les DLL Qt exposées au seul processus lancé.
`-ServerUrl` ne fait que pré-renseigner `ACP_API_URL` pour cette exécution ;
**aucune URL de serveur n'est codée en dur nulle part** dans cette chaîne d'outils,
et aucun domaine n'a été décidé pour ce produit.

## 7. Codes de sortie

Communs aux cinq scripts, pour être exploitables par un appelant :

| Code | Signification |
|---|---|
| `0` | succès |
| `1` | erreur inattendue |
| `2` | prérequis manquant (Qt, MSVC, CMake, CTest, Inno Setup) |
| `3` | contrat absent (sources, préréglage, répertoire de compilation, binaire, QML) |
| `4` | échec de configuration ou de compilation |
| `5` | au moins un test a échoué |
| `6` | échec d'empaquetage |
| `7` | échec de signature |

## 8. Encodage et fins de ligne

Les fichiers `.ps1`, `.psm1` et `.iss` sont enregistrés en **UTF-8 avec BOM**.
Ce n'est pas une coquetterie : Windows PowerShell 5.1 lit un script sans BOM avec
la page de code ANSI du système, ce qui casse les accents et, sur certains
enchaînements, l'analyse syntaxique elle-même. Le défaut a été constaté puis
corrigé pendant l'écriture de ces scripts. Les fins de ligne restent LF.

Les fichiers `.yml`, `.json` et `.md` sont en UTF-8 **sans** BOM.

## 9. Intégration continue

`.github/workflows/desktop-ci.yml`, exécuteur `windows-2025`, `timeout-minutes: 60`,
`permissions: contents: read`.

Déclenchement : demande de fusion et poussée sur `main`, `codex/**` ou `feat/**`,
restreints aux chemins du chantier desktop, plus le déclenchement manuel. Ce filtre
répond à la question ouverte n° 20 de l'audit — le budget de minutes Windows n'est
consommé que lorsque le desktop change.

Étapes : lecture de la chaîne d'outils épinglée, contrôle de l'image de
l'exécuteur, contrôle de présence des sources, installation de Qt avec cache,
inventaire des prérequis, compilation Release, tests, **empaquetage à blanc**, dépôt
des artefacts pour inspection (7 jours).

Ce que la CI met en cache : l'installation de Qt, de loin le téléchargement le plus
lourd. Ce qu'elle ne met **pas** en cache : le répertoire de compilation C++. Un
cache natif périmé produit des résultats faux, ce qui coûte plus cher que les
minutes économisées.

**Le job échoue tant que `apps/desktop` n'existe pas.** C'est délibéré : rendre un
succès vert sans avoir rien compilé serait exactement le faux succès que la doctrine
du projet interdit. Le job deviendra vert quand le lot fondation desktop sera
fusionné — et pas avant.

L'action Qt est une action tierce, épinglée par empreinte de commit
(`bcb88e3bed2e992f5f9e24c0f9e364a231d278eb`, étiquette `v4.4.0` publiée le
14 septembre 2026, relevée sur <https://github.com/jurplel/install-qt-action> le
18 septembre 2026). Les actions first-party de GitHub suivent la convention déjà en
place dans `.github/workflows/ci.yml` : épinglage par étiquette majeure.

## 10. Ce qui a été vérifié et comment

Exécuté sur le poste de développement le 18 septembre 2026 :

- **Validité YAML des deux workflows** —
  `python -c "import yaml,sys; [yaml.safe_load(open(f,encoding='utf-8')) for f in sys.argv[1:]]"`
  sur `desktop-ci.yml` et `desktop-release.yml` : accepté.
- **Analyse syntaxique des cinq scripts et du module**, sans exécution —
  `[System.Management.Automation.Language.Parser]::ParseFile(...)` : zéro erreur.
- **Exécution réelle des chemins de refus** — `setup-desktop.ps1` rend `2` et liste
  les quatre prérequis obligatoires absents ; `build-desktop.ps1`,
  `test-desktop.ps1`, `package-desktop.ps1` et `dev-desktop.ps1` rendent `3` en
  nommant précisément le fichier attendu.

Ce qui n'a **pas** pu être vérifié ici, et ne le sera que par la CI : l'exécution de
`cmake`, de `ctest`, de `windeployqt`, d'`ISCC` et de `signtool` ; la validité du
script Inno Setup ; le comportement réel de l'action d'installation de Qt ; et
l'existence même d'un binaire.

## 11. Limites connues

1. `scripts/check_version.py` ne couvre pas encore la version du client desktop. Le
   client peut donc dériver silencieusement de `VERSION` (constat déjà porté par
   l'audit, section 6.3, point 7). Le workflow de publication, lui, refuse une
   étiquette qui ne correspond pas à `VERSION`.
2. Aucun certificat de signature de code n'existe. Les binaires produits ne sont pas
   signés : voir [`docs/desktop-release-process.md`](desktop-release-process.md).
3. L'image `windows-2025` est épinglée dans `runs-on` **et** dans
   `packaging/windows/toolchain.json`. GitHub ne permet pas de lire `runs-on` depuis
   un fichier ; une étape compare les deux et refuse la divergence, ce qui limite le
   risque sans le supprimer.
4. Le générateur employé par le préréglage MSVC n'est pas connu de cette chaîne
   d'outils. L'environnement MSVC est chargé dans tous les cas, ce qui couvre aussi
   bien Ninja que le générateur Visual Studio, mais le `-Filter` de `ctest` et
   l'emplacement exact du binaire dépendent de ce choix.
