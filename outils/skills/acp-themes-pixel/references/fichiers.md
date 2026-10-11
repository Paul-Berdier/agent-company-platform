# Fichiers à toucher, par type de changement

Liste de contrôle relevée le 11 octobre 2026. Elle complète la skill `acp-themes-pixel` ; chaque ligne dit où la
valeur vit et qui la vérifie. Le nom de la fonction ou de la constante fait foi si une ligne a bougé.

## Une couleur d'un thème existant

| À faire | Où |
|---|---|
| Valeur dans les quatre thèmes | `design/tokens/colors.json` (ou `semantic-status.json`, `elevation.json`) |
| Régénérer le QML, le thème web, les assets | les trois générateurs (skill, étape 6) |
| Contrastes | refus automatique : `measure_contrasts`, `apps/desktop/cmake/generate_design_tokens.py:289-347` ; recalcul du thème web dans `scripts/generer_themes.py` (`construire`, `:163`) |
| Minima relevés | [docs/refonte/atelier-da.md](../../../../docs/refonte/atelier-da.md) § 3.2 |
| Thème web | change seulement si `studio-graphite` change (`THEME`, `scripts/generer_themes.py:49`), mais l'empreinte change à toute retouche des fichiers lus (`:344`) |

## Un thème ou une famille de plus

| À faire | Où |
|---|---|
| Identifiant et défaut | `$themes`, `$defaultTheme` : `design/tokens/colors.json:7-8`, `semantic-status.json:7-8`, `elevation.json:7-8` |
| Famille et libellés | `$themeFamilies` (`colors.json:243`) ; `$themeLabels` |
| Choix du thème à l'exécution | `SystemAppearance::themeFor`, `apps/desktop/src/system/SystemAppearance.cpp:102-112` |
| Valeurs admises de la préférence | `SettingsStore::families`, `apps/desktop/src/storage/SettingsStore.cpp:58-62` |
| Page Apparence | familles écrites dans `apps/desktop/qml/pages/ApparencePage.qml:80-83` |
| Tests | `apps/desktop/tests/qml/tst_design_tokens.qml:25` (quatre thèmes), `:72` (une variante sombre et une claire par famille) ; `apps/desktop/tests/cpp/tst_pages_interactions.cpp:1069-1077` (bascule de famille et de luminosité) |
| Palettes pixel qui lisent un thème | valeurs `jeton:<thème>:<jeton>` de `design/pixel/manifeste.json` (exemples : lignes 174 à 201) |

## Un profil de mouvement de plus

| À faire | Où |
|---|---|
| Profil, libellé, défaut, réduit | `design/tokens/motion.json` : `$defaultProfile` et `$reducedProfile` (`:14-15`), `$profileLabels` (`:16`), `$profiles` (`:44`) |
| Ancienne valeur relue | `$legacyProfiles` (`:21`) |
| Valeurs admises de la préférence | `SettingsStore::motionProfiles`, `SettingsStore.cpp:64-68` |
| Tests | `tst_design_tokens.qml:213-232` (profils et ambiance), `:234` (Concentration) |

## Une durée ou une courbe

| À faire | Où |
|---|---|
| Jeton | `design/tokens/motion.json`, bloc `tokens` |
| Plafond | 240 ms pour toute transition fonctionnelle : `tst_design_tokens.qml:190-196` et `:221-232` |
| Courbe | quatre points ; le générateur complète par `1, 1` (docstring, `generate_design_tokens.py:21-22`) ; test `tst_design_tokens.qml:260` |

## Un asset pixel

| À faire | Où |
|---|---|
| Grille | `design/pixel/sources/embleme.txt`, `portraits.txt`, `pictogrammes.txt`, `police.txt` |
| Palette, séquence, export | `design/pixel/manifeste.json` (`palettes`, `planches`, `embleme`, `icone`, `qml`) |
| Ressource QML | `RESOURCES` de `apps/desktop/qml/pixel/CMakeLists.txt:19-31` ; l'existence est vérifiée à la configuration (`apps/desktop/cmake/AcpQmlModule.cmake:37-44`) |
| Lecture en QML | singleton généré `PlanchesPixel` (`singleton_qml`, `scripts/generer_assets_pixel.py:476-495`) ; composants `SpritePixel`, `PortraitAgent`, `TextePixel`, `Embleme` |
| Tests | `apps/desktop/tests/qml/tst_pixel.qml` (rôles et états des portraits, capitales françaises de la police, tailles de l'emblème, animation seulement observée et admise) ; `scripts/tests/test_generer_assets_pixel.py` (sorties à jour, icône, relecture pixel par pixel, refus en français) |

## Une borne de panneau ou une densité

| À faire | Où |
|---|---|
| Jeton | `design/tokens/spacing.json`, `layout.*` et `$densities` (`:72`) |
| Copie en C++ | `SettingsStore.cpp:32-38` (bornes des largeurs et hauteurs mémorisées) |
| Tests | `tst_design_tokens.qml:243` (densité et taille du texte appliquées à chaud), `:274` |
