# Compiler le client desktop Windows

Public : développeur du client natif C++23 / Qt 6 / Qt Quick (`apps/desktop`).
Version du produit : `0.11.0` (fichier `VERSION` à la racine), refonte « Hermes au
centre », étape **P8** : la station parle à Hermes (connexion native RFC 8252, porteur,
JSON-RPC `/api/ws`, greffon `acp-poste`). État de ce document : 2 octobre 2026. Les
relevés de l'ancien client (0.10.0, ancienne API ACP) restent sous l'étiquette
`archive/acp-0.10.0-avant-hermes`.

## État des preuves

Sur la branche `refonte/hermes-p8` : compilation Release (`/W4 /WX`) et **34 suites**
déclarées à CTest (31 avant les corrections de la relecture, 34 depuis), totaux Qt relevés sans échec ni test ignoré, localement et par la
**Desktop CI** sur `windows-2022` (identifiants des runs dans
[l'historique de la refonte](refonte/historique.md), partie B, § 6 decies). Un **bout en bout local** contre la
pile de test (vrai Authelia, Hermes de test, bord TLS factice) a réussi (§ 12). Ni
Railway, ni une vraie passkey, ni une installation sur un Windows propre ne sont prouvés.

## 1. Prérequis

| Outil | Rôle | Obligatoire |
|---|---|---|
| Visual Studio 2022, charge « Développement Desktop en C++ » (x64) | compilateur, éditeur de liens, `signtool` | oui |
| CMake | configuration et compilation par préréglage | oui |
| Qt `6.8.3`, architecture `win64_msvc2022_64`, module additionnel `qtwebsockets` | Qt Quick, Qt Network, Qt WebSockets, `windeployqt` | oui |
| Ninja | seulement si le préréglage MSVC emploie le générateur Ninja | selon le préréglage |
| Inno Setup 6.4 ou plus récent | fabrication du programme d'installation | empaquetage seulement |

La version de Qt est **épinglée**, au même titre que la base d'image Python par
digest et que le verrou haché des dépendances. Elle vit à un seul endroit :
`packaging/windows/toolchain.json`. Ne la recopiez nulle part.

Qt 6.8.3 est la version effectivement retenue et installée pour ce dépôt. Un
changement de version doit mettre à jour la chaîne épinglée et ses preuves.

Qt WebSockets (LGPLv3, comme les autres modules employés) porte la passerelle JSON-RPC
de Hermes et la veille du kanban ; aucune autre voie native n'existe pour `/api/ws`.
Installation par aqtinstall, dans l'environnement d'outillage séparé
([`reprise-poste.md`](reprise-poste.md), § 4) :

```powershell
aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 -m qtwebsockets --outputdir "$env:USERPROFILE\Qt"
```

`setup-desktop.ps1` vérifie la présence de `Qt6WebSockets.dll` et refuse sinon, avec
cette commande.

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

**Modules Qt additionnels.** `qt.modules` vaut `["qtwebsockets"]` depuis P8. Un autre
module non essentiel devrait être ajouté là ; sans cela, la configuration CMake
échouerait en intégration continue avec le message de Qt lui-même : c'est le
comportement voulu, préférable à une compilation qui réussirait sur un poste et pas sur
un autre. `windeployqt` embarque `Qt6WebSockets.dll` par analyse des dépendances
(vérifié dans l'archive à blanc de la Desktop CI).

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

Depuis P8 et ses corrections après relecture, 34 suites :

| Domaine | Suites |
|---|---|
| Connexion et coffre | `tst_pkce`, `tst_flux_natif`, `tst_session_hermes`, `tst_jetons_coffre`, `tst_instance_unique`, `tst_reglages_sans_secret` |
| Transport, compatibilité, santé | `tst_api_porteur`, `tst_api_errors`, `tst_client_greffon`, `tst_compatibilite_hermes`, `tst_sante` |
| JSON-RPC et temps réel | `tst_canal_jsonrpc`, `tst_client_passerelle`, `tst_openrpc_conformite`, `tst_temps_reel`, `tst_sse_parser`, `tst_backoff` |
| Pages | `tst_accueil`, `tst_projets`, `tst_questions`, `tst_discussion`, `tst_poste`, `tst_quotas`, `tst_routage`, `tst_sauvegarde`, `tst_diagnostics`, `tst_pages_bureau` |
| Gestes réels et oubli | `tst_pages_interactions` (frappes et clics de souris sur les vrais contrôles QML : réponse à une question, consigne, message de la discussion, raccourcis de la palette, dialogue des réglages), `tst_oubli_local` (session perdue, changement de serveur, greffon bloqué), `tst_modele_liste` (mise à jour des listes par identifiant) |
| Socle | `tst_command_registry`, `tst_redaction`, `tst_updates`, `tst_qml_shell` (Qt Quick Test) |

CTest compte « Passed » un test ignoré par `QSKIP` : lire les totaux de Qt Test
(`Totals: N passed, 0 failed, 0 skipped`) en lançant chaque exécutable avec
`-o <rapport-absolu>,txt`. `tst_jetons_coffre` et `tst_sauvegarde` font un aller-retour
réel dans le coffre Windows et DPAPI (ignorés, avec la raison, hors Windows).

## 6. Développer

```powershell
./scripts/dev-desktop.ps1
./scripts/dev-desktop.ps1 -SkipBuild
```

Compile puis lance l'application avec les DLL Qt exposées au seul processus lancé, et
attend sa fermeture : le code de sortie rendu est celui de l'application. L'adresse du
serveur se saisit dans l'écran de connexion ; **aucune URL de serveur n'est codée en dur
nulle part** dans cette chaîne d'outils, et aucun domaine n'a été décidé pour ce produit.

Depuis P8, la station se connecte à un Hermes ACP (image `hermes/image`, fournisseur
`self-hosted`) par le navigateur du système. Rien n'étant déployé, le seul Hermes
joignable aujourd'hui est la pile de test locale, par le bout en bout (§ 12). Le HTTP en
clair reste refusé hors adresse de bouclage.

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

Déclenchement : demande de fusion et poussée (dont `refonte/**`), restreintes aux
chemins du chantier desktop — y compris `hermes/contrat/**`, dont la compilation lit
`HERMES_VERSION` et l'OpenRPC épinglé —, plus le déclenchement manuel. Ce filtre répond
à la question ouverte n° 20 de l'audit — le budget de minutes Windows n'est consommé que
lorsque le desktop change. Un run en cours sur la même branche est annulé par le
suivant : attendre la fin d'un run avant de pousser le commit suivant.

Étapes : lecture de la chaîne d'outils épinglée, contrôle de l'image de
l'exécuteur, contrôle de présence des sources, installation de Qt avec cache,
inventaire des prérequis, compilation Release, tests, **empaquetage à blanc**, dépôt
des artefacts pour inspection (7 jours).

Ce que la CI met en cache : l'installation de Qt, de loin le téléchargement le plus
lourd. Ce qu'elle ne met **pas** en cache : le répertoire de compilation C++. Un
cache natif périmé produit des résultats faux, ce qui coûte plus cher que les
minutes économisées.

La garde de présence de `apps/desktop` reste utile et les sources existent. Chaque
révision doit obtenir son propre verdict ; le journal de la CI ne montre que le résumé
de CTest (pas les totaux de Qt Test), relevés localement.

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
exécutés, en local et en CI. Pour P8 : la suite complète (34 suites) et le bout en bout
local (§ 12). `signtool` avec un certificat de production, l'installation sur un
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

## 12. Bout en bout local (jamais en CI)

Les exécuteurs Windows de GitHub ne font pas tourner de conteneurs Linux : ce parcours se
lance sur un poste avec Docker Desktop, contre la pile de test des greffons.

```powershell
docker build -f hermes/image/Dockerfile -t acp-hermes:p8 hermes
docker build -f hermes/tests/Dockerfile --build-arg IMAGE_ACP=acp-hermes:p8 -t acp-hermes-tests:p8 hermes/tests
docker build -t acp-identite:p8 identite
./scripts/build-desktop.ps1 -Configuration Release
./scripts/e2e-desktop-windows.ps1 -Python <venv>\Scripts\python.exe `
    -ImageTests acp-hermes-tests:p8 -ImageIdentite acp-identite:p8 `
    -QtDir "$env:USERPROFILE\Qt\6.8.3\msvc2022_64" -Preuves "$env:TEMP\e2e-desktop.json"
```

Le venv est un Python 3.12 de python.org avec le verrou haché
`hermes/tests/requirements-e2e.txt` (Playwright 1.62.0) et Chromium de Playwright.
Codes : 0 parcours réussi, 1 écart (voir le rapport), 2 prérequis manquant.

Ce que fait le parcours (`apps/desktop/tests/e2e/e2e_desktop_windows.py`) :

- **Pile** : vrai Authelia, Hermes de test avec le modèle factice, bord TLS factice
  publié sur `127.0.0.1` (`hermes/tests/contrat/pile_identite.py`), poste simulé.
- **Station** : `acp_desktop_e2e`, la VRAIE station (Application, services, ViewModels,
  pages QML) pilotée par lignes JSON ; coffre `AcpDesktopE2E-<uuid>` et portée de
  préférences `ACP E2E <uuid>` de test, supprimés à la fin ; elle ne joint la pile que par
  un mandataire CONNECT du script, limité aux deux noms de la pile ; autorité de test du
  bord ajoutée au seul processus.
- **Navigateur** : Chromium (Playwright) remplace celui du système, avec un
  authentificateur WebAuthn virtuel : mot de passe, passkey, consentement.

Relevé du **2 octobre 2026** (Windows 10, Docker 29.5.3, images `:p8` construites depuis
la branche), **réussi, 0 écart** :

| Étape | Constat |
|---|---|
| Connexion native | URL d'autorisation de `https://hermes-acp.test/auth/native/authorize`, `provider=self-hosted`, S256, défi et état de 43 caractères, retour `http://127.0.0.1:<port>/rappel`, **aucun vérificateur** dans l'URL ; page de l'écouteur « Connexion transmise à la station » ; identité « Propriétaire d'ACP » par `/api/auth/me` ; jeton au coffre de test |
| Rotation | deux rafraîchissements, trois empreintes distinctes (jamais les valeurs) |
| JSON-RPC | passerelle prête (sous-protocole `hermes-gateway-v1`), `session.create`, `prompt.submit` → « Réponse du modèle factice ACP. » ; 4 événements hors du sous-ensemble comptés, ignorés |
| Projet | lancé depuis la page Projets (dépôt `jetable`, exécutant poste Claude, « Moi » répond) : « Projet lancé : Hermes le planifie. », état `actif` relu par l'API |
| Veille du kanban | carte réclamée par le poste simulé : invalidation reçue, détail relu 44 ms après elle |
| **Question** | posée par le poste simulé (escaladée), vue dans la page Questions, **répondue depuis la station** (« Réponse envoyée : la carte reprend. ») ; relue par l'API : plus ouverte, carte `ready` ; captures avant et après. Depuis les corrections de la relecture, la réponse est **tapée dans le champ de la carte et envoyée par un clic réel sur « Répondre »**, et le message de la discussion par le champ et le bouton « Envoyer » (`par_le_bouton` exigé par le script) |
| Sauvegarde | 15,8 Mio exportés, chiffrés (`ACPB1`), déchiffrés à l'identique (SHA-256), archive **supprimée** du volume de Hermes ; 7 s |
| Redémarrage | session reprise du coffre **sans navigateur** en 0,24 s, jeton tourné |
| Déconnexion | `POST /auth/logout` → 302, coffre vidé ; rejeu de l'ancien jeton → **503** (Authelia rend 500 pour un jeton révoqué) |
| Hygiène | aucune forme de secret dans le journal de la station, l'export du registre de la portée, le journal du bord ni celui de Hermes ; aucune entrée de coffre de test restante ; 57 tunnels du mandataire, tous vers `hermes-acp.test`, **aucun** vers le fournisseur d'identité, aucun refus ; WebSockets `/api/ws` et `/api/plugins/kanban/events` sous l'hôte public |
| Documents de référence | 9 documents des tests natifs, 434 clés, servis par l'image avec le même type (voir `apps/desktop/tests/fixtures/hermes/README.md`) |

Rejoué après les corrections de la relecture (2 octobre 2026, `c22c8b9` puis `1f3696a`) :
**réussi, 0 écart**, contre `acp-hermes-tests:p8` et contre `acp-hermes-tests:rv8p6`
(construite depuis `7697a1c`, P6 fusionnée) ; la page Poste de ce second serveur affiche
« Aucun exécutant connu pour l'instant : l'étape P6 est en place sur ce serveur… ».

Captures relues (pages réelles dans une fenêtre construite comme `App.qml`) : rappel du
navigateur, discussion, nouveau projet, questions avant et après, sauvegarde, accueil,
détail du projet, poste, quotas, routage, diagnostics. Ce parcours ne prouve ni Railway, ni une vraie passkey, ni le navigateur du
système (remplacé par Chromium), ni une installation sur un Windows propre.
