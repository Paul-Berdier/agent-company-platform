---
name: acp-espace-travail-qml
description: "Conventions du shell QML de la station de travail Qt d'ACP (apps/desktop) : modules Acp.Design, Acp.Theme, Acp.Pixel, Acp.Controls, Acp.Components, Acp.Pages, Acp.Station et Acp.Desktop, un dossier pour un URI, déclaration CMake obligatoire et check_layout.py, singletons Acp.Runtime enregistrés en C++, objectName lus par les tests, refus de tout texte anglais visible et de tout AcpButton sans nom accessible, animations gatées par Motion et suspendues hors écran, aucun Canvas animé, Layout.* dans les layouts, aucune propriété on suivie d'une majuscule. À utiliser dès qu'on crée, modifie, renomme ou déplace un fichier .qml, une page, un panneau, un composant ou un ViewModel exposé au QML de la station, même pour une petite retouche visuelle."
---

# Espace de travail QML de la station

Agencement fixé par D167 (projets et missions à gauche, mission au centre, agents à droite, volet bas, pages
techniques sous Réglages) ; vocabulaire par D166 ; l'Accueil garde ses sept blocs (D99). Lignes relevées le
11 octobre 2026 dans l'arbre de travail : le shell change pendant le chantier, le nom de la fonction ou de l'objet
fait foi si une ligne a bougé. Règles générales de commit et de test : skill `acp-changement-sur`. Pièges vérifiés
sur Qt 6.8.3 : [references/pieges-qml.md](references/pieges-qml.md).

## Déclencheur

- Un fichier `.qml` de `apps/desktop/qml` est créé, modifié, renommé ou déplacé.
- Un ViewModel, une préférence ou une commande est exposé au QML.
- Une animation, un sprite ou un contrôle fait main est ajouté.

## Entrées

- Le module visé et son dossier (table ci-dessous).
- Les tests qui chargent ce fichier ou cherchent ses `objectName`.

## Modules

Un module par dossier, un URI par module (`apps/desktop/qml/CMakeLists.txt:3-4`) :

| Dossier | URI | Rôle |
|---|---|---|
| `qml/theme/generated` | `Acp.Design` | singletons **générés** (skill `acp-themes-pixel`) |
| `qml/theme` | `Acp.Theme` | `ThemeBridge`, seul endroit qui choisit thème et profil (`qml/theme/ThemeBridge.qml:1-9`) |
| `qml/pixel` | `Acp.Pixel` | planches et composants pixel |
| `qml/controls` | `Acp.Controls` | contrôles faits main (`AcpButton`, `AcpIcon`…) |
| `qml/components` | `Acp.Components` | composants de présentation |
| `qml/pages` | `Acp.Pages` | écrans |
| `qml/shell` | `Acp.Station` | coquille : barres, navigation, panneaux, palette |
| `qml` | `Acp.Desktop` | `App.qml` seul, chargé par `loadFromModule` (`src/app/Application.cpp:277`) |

`Acp.Runtime` n'a pas de dossier : ses singletons sont des objets C++ (`kQmlUri`, `Application.cpp:51`).

## Étapes

1. **Déclarer chaque fichier.** Ajouter le `.qml` aux `QML_FILES` du `CMakeLists.txt` de son dossier. Un fichier
   absent du disque fait échouer la configuration (`apps/desktop/cmake/AcpQmlModule.cmake:25-33`) ; un fichier non
   déclaré est un constat de `check_layout.py` (`check_every_file_is_declared`,
   `apps/desktop/cmake/check_layout.py:159-168`).
2. **Un nouveau module** : `add_subdirectory` dans `qml/CMakeLists.txt:9-14` ; `URI Acp.X` seul sur sa ligne
   (sinon invisible pour `check_layout.py:176`) ; greffon `<cible>plugin` lié à l'exécutable
   (`apps/desktop/CMakeLists.txt:292-299`) et aux tests (`apps/desktop/tests/CMakeLists.txt:40-42`, `:46-48`,
   `:113-115`, `:127-138`).
3. **Un singleton QML** : `pragma Singleton` **et** `acp_mark_qml_singletons(<fichier>.qml)` avant
   `acp_add_qml_module` (`AcpQmlModule.cmake:60-69` ; exemple : `qml/pixel/CMakeLists.txt:6`). `check_layout.py`
   vérifie les deux sens (`check_singletons`, `check_layout.py:202-232`).
4. **Un singleton `Acp.Runtime`** (ViewModel ou service) : le construire dans `Application::Application`,
   l'enregistrer par `qmlRegisterSingletonInstance` dans `Application::registerQmlTypes` (`Application.cpp:210`,
   `:244-264`), et l'ajouter aux listes d'oubli s'il lit le serveur : `oublierLesPages` (`:146`) et la liste du
   greffon bloqué (`:175`). Les singletons ne s'enregistrent qu'une fois par processus : d'où un seul cas de
   test qui charge toutes les pages (`apps/desktop/tests/cpp/tst_pages_bureau.cpp:7-8`).
5. **Ne pas importer `Acp.Runtime`** dans un composant testé par `tst_qml_shell` : ce harnais n'injecte aucun
   singleton C++ (`apps/desktop/tests/qml/tst_qml_shell.cpp:27-33`).
6. **Garder les `objectName`.** Les tests trouvent les éléments par nom : `parNom`
   (`apps/desktop/tests/cpp/tst_pages_interactions.cpp:71-81`), le bout en bout Windows aussi
   (`apps/desktop/tests/e2e/acp_desktop_e2e.cpp:771`, hors CI). Les pages se chargent par module et nom ; la
   coquille par `charger("Acp.Station", "ShellRoot")` (`apps/desktop/tests/cpp/tst_pages_bureau.cpp:653`). Un
   renommage se fait dans le QML **et** dans tous ces tests, dans le même commit.
7. **Écrire en français, nommer chaque bouton.** `tst_pages_bureau` refuse dans tout texte visible `undefined`,
   `NaN`, `Loading`, `Error`, `Unknown`, `Cancel`, `Submit`, `Retry`, `Close`, `Connection refused`, `not found`,
   `timed out` (`kInterdits`, `tst_pages_bureau.cpp:58-64`), et tout `AcpButton` dont `Accessible.name` est vide
   (`tst_pages_bureau.cpp:72-78`). Tout avertissement du moteur QML pendant le chargement fait aussi échouer
   l'étape (`tst_pages_bureau.cpp:236-238`, `:267-269`). `AcpButton` annonce son `label`
   (`qml/controls/AcpButton.qml:152`) : un bouton à icône seule pose `Accessible.name`. Les boutons standard de Qt
   s'affichent en anglais : les éviter.
8. **Animer seulement ce qui est admis.**
   - Durées et courbes lues dans `Motion.active.<entrée>`, jamais en dur (exemple :
     `qml/controls/AcpButton.qml:54-58`).
   - Ambiance gatée par `Motion.ambianceActive`, activité par `Motion.spriteActivityActive` et un état **observé**
     (`qml/pixel/PortraitAgent.qml:27-29`). Aucune animation ne prouve une activité (D165).
   - Suspendue hors écran : un minuteur ne tourne que si l'élément est visible et la fenêtre ni réduite ni cachée
     (`qml/pixel/SpritePixel.qml:26-27`, `:48-53`).
   - Profil réduit : aucune boucle (`qml/components/StatusChip.qml:81-82`).
   - **Aucun Canvas animé.** Le seul Canvas est `AcpIcon` (`qml/controls/AcpIcon.qml:5`), redessiné quand une
     propriété change (`:13-17`). Préférer des `Rectangle` ou une planche pixel (`qml/pixel/FondPixel.qml:3-5`).
9. **Dans un layout, `Layout.*` seulement.** Ni `anchors` ni `width`/`height` sur un enfant de `RowLayout`,
   `ColumnLayout` ou `GridLayout` : Qt 6.8.3 émet alors un avertissement QML à l'exécution (mesure dans
   [references/pieges-qml.md](references/pieges-qml.md)), et `tst_pages_bureau` échoue sur tout avertissement du
   moteur (étape 7).
10. **Aucune propriété `on` suivie d'une majuscule** (`onAccent`, `onSurface`) : avec la propriété de base dans le
    même objet, le chargement échoue (« Cannot assign a value to a signal »), et `qmllint` 6.8.3 ne le voit pas
    (mesure dans la référence). Le générateur écrit déjà `textOnAccent` (`qml/theme/generated/Colors.qml:36`).
11. **Préférences sans secret.** Toute clé nouvelle entre dans `SettingsStore::allowedKeys`
    (`apps/desktop/src/storage/SettingsStore.cpp:42-56`) ; hors liste, `Q_ASSERT` en Debug et refus en Release
    (`:104-110`, `:115-120`). `tst_reglages_sans_secret.cpp:117` le vérifie. Les brouillons restent en mémoire (D167).
12. **Pages qui lisent le serveur** : poser `pageVisible` à la création et le retirer à la destruction (exemple :
    `qml/pages/QuestionsPage.qml:18-19`) ; une liste à délégués avec état déclare sa clé (`setCle`,
    `src/models/JsonListModel.h:13`, `:35`).

## Sorties

- Le QML, son `CMakeLists.txt` et les tests touchés, dans le même commit.
- Le nombre de constats de `check_layout.py`, comparé à la base de 13 (`apps/desktop/README.md:60-64`).
- Les suites lancées, avec les totaux de Qt Test.

## Limites

- Style `Basic` imposé (`src/main.cpp:97`) : les contrôles de Qt Quick Controls ne prennent les jetons que par la
  palette. Chaînes C++ par `QStringLiteral` (`QT_NO_CAST_FROM_ASCII`, `apps/desktop/CMakeLists.txt:270-271`).
- Sous Linux, préréglage Debug sans avertissements en erreurs ; la preuve est la Desktop CI Windows.
- Aucun test ne mesure la cadence d'image ni ne compare de capture : la fluidité reste au lot F
  ([atelier.md](../../../docs/refonte/atelier.md), section 6).
- `qmllint` ne résout pas les modules `Acp.*` depuis le dossier de construction (mesure dans la référence) : son
  verdict ne remplace pas les tests.

## Vérification

```sh
python3.12 apps/desktop/cmake/check_layout.py          # 13 constats connus au plus
cd apps/desktop && cmake --build --preset linux-gcc-debug && ctest --preset linux-gcc-debug
```

Suites à lire en premier : `tst_pages_bureau`, `tst_pages_interactions`, `tst_espace_travail`, `tst_qml_shell`,
`tst_reglages_sans_secret`, `tst_oubli_local`, `tst_command_registry`. Environnement Linux : skill
`acp-changement-sur`, référence `suites-par-chemin.md`.
