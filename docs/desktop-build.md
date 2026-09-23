# Compiler le client desktop Windows

Public : développeur du client natif C++23 / Qt 6 / Qt Quick (`apps/desktop`).
Version du produit : `0.10.0` en préparation (fichier `VERSION` à la racine).
État de ce document : 23 septembre 2026.

## État des preuves

La fondation a compilé en Debug/Release sur Windows, passé dix suites natives et
produit un portable et un installeur local. Son CI historique est vert. Le nouvel
arbre métier 0.10.0 a compilé en Release et passé 21 suites sur 21 en 54,82 s.
Les résultats du CI sont consignés dans le relevé daté ci-dessous.
Un parcours Qt contre une vraie API locale et SQLite jetable a réussi le
23 septembre : connexion, projets, conversation avec fournisseur indisponible,
mission, budget, automatisation et téléchargement authentifié. Il ne prouve pas
Railway, une instance Hermes réelle ou une installation Windows propre.
Voir [les preuves datées](desktop-validation-2026-09-23.md).

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

Qt 6.8.3 est la version effectivement retenue et installée pour ce dépôt. Un
changement de version doit mettre à jour la chaîne épinglée et ses preuves.

### Constater ce qui manque

```powershell
./scripts/setup-desktop.ps1
```

Ce script **n'installe rien**. Il constate, et il affiche pour chaque manque la
commande exacte à lancer vous-même. Il rend `0` si tous les prérequis obligatoires
sont présents, `2` sinon. `-Json` produit le même inventaire en JSON.

Un poste vierge obtient une sortie de ce genre :

```text
[MANQUANT] CMake
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

Les scripts vérifient le contrat du répertoire `apps/desktop` existant. Une valeur
manquante ou incohérente conduit à un refus explicite.

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
```

Compile puis lance l'application avec les DLL Qt exposées au seul processus lancé, et
attend sa fermeture : le code de sortie rendu est celui de l'application. L'adresse du
serveur se saisit dans l'écran de connexion ; **aucune URL de serveur n'est codée en dur
nulle part** dans cette chaîne d'outils, et aucun domaine n'a été décidé pour ce produit.

Pour une API locale (`python -m uvicorn acp_api.main:app --port 8000`), saisir
`http://127.0.0.1:8000` et cocher « Autoriser HTTP en clair sur une adresse de
bouclage » : le HTTP en clair est refusé partout ailleurs. Affecter une base
jetable explicite à `ACP_DATABASE_URL` avant un parcours de vérification ; la
base `./acp.db` de développement ne doit jamais servir aux tests destructifs.
L'API locale nécessite `ACP_SESSION_COOKIE_SECURE=0` et un compte déjà amorcé.

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

`.github/workflows/desktop-ci.yml`, exécuteur `windows-2022` (Visual Studio 2022 17.14), `timeout-minutes: 60`,
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

La garde de présence de `apps/desktop` reste utile et les sources existent.
Le CI de la fondation a déjà été observé vert ; chaque nouvelle révision doit
obtenir son propre verdict. Les compléments 0.10.0 sont encore en validation
locale et n'ont pas encore leur run distant.

L'action Qt est une action tierce, épinglée par empreinte de commit
(`bcb88e3bed2e992f5f9e24c0f9e364a231d278eb`, étiquette `v4.4.0` publiée le
14 septembre 2026, relevée sur <https://github.com/jurplel/install-qt-action> le
18 septembre 2026). Les actions first-party de GitHub suivent la convention déjà en
place dans `.github/workflows/ci.yml` : épinglage par étiquette majeure.

## 10. Ce qui a été vérifié et comment

Premiers contrôles historiques du 18 septembre 2026, avant installation des outils :

- **Validité YAML des deux workflows** —
  `python -c "import yaml,sys; [yaml.safe_load(open(f,encoding='utf-8')) for f in sys.argv[1:]]"`
  sur `desktop-ci.yml` et `desktop-release.yml` : accepté.
- **Analyse syntaxique des cinq scripts et du module**, sans exécution —
  `[System.Management.Automation.Language.Parser]::ParseFile(...)` : zéro erreur.
- **Exécution réelle des chemins de refus** — `setup-desktop.ps1` rend `2` et liste
  les quatre prérequis obligatoires absents ; `build-desktop.ps1`,
  `test-desktop.ps1`, `package-desktop.ps1` et `dev-desktop.ps1` rendent `3` en
  nommant précisément le fichier attendu.

Depuis ce premier relevé, CMake, CTest, `windeployqt` et Inno Setup ont été
exécutés sur la fondation et un binaire a démarré. Le parcours API réel du
23 septembre est passé ; la suite native complète du nouvel arbre est encore
en cours. `signtool` avec un certificat de production, l'installation sur un
Windows propre et Railway restent non prouvés.

Pour diagnostiquer un test Qt silencieux sur ce poste, lancer son exécutable avec
`-o <rapport-absolu>,txt` et lire le rapport. Les exécutables résident directement
dans `apps/desktop/build/windows-msvc-release`. Éviter les builds simultanés
dans ce répertoire.

## 11. Limites connues

L'empaquetage Release place les DLL redistribuables **VC143 x64** à côté de
l'exécutable. Le premier essai du 23 septembre 2026 a montré que
`windeployqt --compiler-runtime` ne copiait que `vc_redist.x64.exe` ; ni l'archive
portable ni l'installeur n'exécutaient ce programme. Cet ancien paquet est non
conforme et ne doit pas être distribué. Le script utilise maintenant le CRT de
l'installation Visual Studio identifiée dans le cache CMake, vérifie sa version
contre le toolset et le linker Qt, son architecture et ses DLL obligatoires,
puis le copie dans les deux formats sans installation système ni élévation.

Le contrôle `packaging/windows/tests/Test-DesktopRuntime.ps1` utilise le build
Release existant et des copies jetables sous `.test-tmp` ; il vérifie le
déploiement réel et le refus d'un runtime ancien, incomplet ou x86. Il ne modifie
aucune DLL système. Cette vérification sur un poste de développement ne remplace
pas une recette sur Windows propre. Le déploiement local, documenté par
[Microsoft](https://learn.microsoft.com/en-us/cpp/windows/choosing-a-deployment-method?view=msvc-170),
implique de reconstruire et redistribuer le client pour actualiser ces DLL ;
elles ne bénéficient pas de la maintenance d'un CRT installé centralement.

1. Le client lit sa version depuis `VERSION` à la configuration CMake. Reconfigurer
   et reconstruire après un changement de version ; un ancien binaire n'est pas
   mis à jour par une modification du fichier. La publication rapproche aussi le tag.
2. Aucun certificat de signature de code n'existe. Les binaires produits ne sont pas
   signés : voir [`docs/desktop-release-process.md`](desktop-release-process.md).
3. L'image `windows-2022` est épinglée dans `runs-on` **et** dans
   `packaging/windows/toolchain.json`. GitHub ne permet pas de lire `runs-on` depuis
   un fichier ; une étape compare les deux et refuse la divergence, ce qui limite le
   risque sans le supprimer.
4. Les préréglages MSVC actuels utilisent Ninja. Leur contrat, le filtre CTest et
   les chemins doivent rester cohérents si ce générateur change.
