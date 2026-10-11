---
name: acp-themes-pixel
description: "Modifier la direction artistique de la station ACP sans rien casser : un thème (atelier-nuit, atelier-jour, studio-graphite, studio-papier), une couleur ou tout autre jeton de design/tokens, un profil de mouvement (complet, discret, réduit, mode Concentration), une densité, ou un asset pixel de design/pixel (emblème, icône Windows, portraits d'agents, pictogrammes, police pixel). À utiliser dès qu'un fichier de design/tokens ou de design/pixel change, qu'une couleur, un contraste, une durée d'animation, un sprite ou l'icône est en cause, ou qu'une sortie générée semble à retoucher (qml/theme/generated, qml/pixel/assets, PlanchesPixel.qml, hermes/theme/acp.yaml, fichier .ico) : ces sorties ne se modifient jamais à la main."
---

# Thèmes, jetons, mouvement et assets pixel

Direction fixée par D165 : Pixel Atelier par défaut (Nuit, Jour), Studio en alternative sobre (Graphite, Papier),
profils Complet, Discret et Réduit, mode Concentration, assets originaux tirés de sources texte. Référence complète :
[docs/refonte/atelier-da.md](../../../docs/refonte/atelier-da.md). Les règles de commit et de test générales sont dans
la skill `acp-changement-sur`. Lignes relevées le 11 octobre 2026 ; le nom de la fonction ou de la constante fait foi
si une ligne a bougé.

## Déclencheur

- Un fichier de `design/tokens` ou de `design/pixel` va changer.
- Une couleur, un contraste, une durée, un sprite, l'emblème ou l'icône est en cause.
- Une sortie générée paraît fausse : on corrige la source, jamais la sortie.

## Entrées

- Le changement voulu, dit en jetons (`surface.panel`, `text.muted`, `duration.fast`) ou en séquences
  (`coordinateur.travail`).
- Les thèmes ou profils visés. Une couleur porte une valeur **par thème** : les quatre se décident ensemble.

## Sources, générateurs, sorties

| Source | Générateur | Sorties versionnées | Contrôle |
|---|---|---|---|
| `design/tokens/*.json` (sept fichiers, `EXPECTED_SINGLETONS`, `apps/desktop/cmake/generate_design_tokens.py:40-51`) | `apps/desktop/cmake/generate_design_tokens.py` | `apps/desktop/qml/theme/generated/` : sept singletons et un `qmldir` (module `Acp.Design`) | `--check` ; `tst_design_tokens.qml` |
| six de ces fichiers (`FICHIERS`, `scripts/generer_themes.py:56`), thème `studio-graphite` (`THEME`, `:49`) | `scripts/generer_themes.py` | `hermes/theme/acp.yaml` (tableau de bord web) | `--check`, qui contrôle aussi le QML (`verifier_qml`, `scripts/generer_themes.py:364-367`) ; `scripts/tests/test_generer_themes.py` |
| `design/pixel/manifeste.json`, `design/pixel/sources/*.txt`, et `colors.json` pour les palettes `jeton:<thème>:<jeton>` (`scripts/generer_assets_pixel.py:68-79`) | `scripts/generer_assets_pixel.py` | PNG sous `apps/desktop/qml/pixel/assets/`, `apps/desktop/resources/windows/AgentCompanyPlatform.ico`, `design/pixel/generes/*.json`, `apps/desktop/qml/pixel/PlanchesPixel.qml` | `--check` par pixels décodés (`verifier`, `scripts/generer_assets_pixel.py:501-521`) ; `scripts/tests/test_generer_assets_pixel.py` ; `tst_pixel.qml` |

Ces sorties portent la mention « ne pas modifier à la main » (`apps/desktop/qml/theme/generated/CMakeLists.txt:1-8` ;
`apps/desktop/qml/pixel/CMakeLists.txt:1-4`).

## Étapes

1. **Changer une couleur.**
   - Couleur opaque `#rrggbb` seulement (`_HEX_COLOR`, `generate_design_tokens.py:65`) ; le canal alpha ne vit que
     dans `elevation.json` (docstring, `generate_design_tokens.py:17-20`).
   - Les contrastes sont **vérifiés** par `measure_contrasts` (`generate_design_tokens.py:289-347`), appelée avant
     toute écriture comme en `--check` (`generate_design_tokens.py:939`). Seuils : 4,5:1 pour le texte et l'encre sur
     accent ; 3:1 pour la bordure interactive, le focus et les accents ; pour chaque état métier, 4,5:1 au premier
     plan et 3:1 à la bordure. Ils sont lus dans `$contrast` (`design/tokens/colors.json:16-24` ;
     `design/tokens/semantic-status.json:16-21`).
   - Sous un seuil, la génération est refusée avec la liste des paires. Changer la couleur ; ne jamais baisser un
     seuil pour passer.
   - `measure_contrasts` ne mesure pas huit des 27 jetons de couleur : les quatre que nomme `unverified`
     (`colors.json:23`, liste déclarative que le générateur ne lit pas), plus `border.subtle`, `border.default`,
     `state.disabled` et `accent.secondaryMuted` (atelier-da.md § 3.3). Les regarder sur capture.
   - Le générateur n'imprime pas les minima : ils sont la valeur de retour de `measure_contrasts`.
2. **Ajouter ou renommer un thème.**
   - Jetons : `$themes` et `$defaultTheme` (`colors.json:7-8`), la même liste dans `semantic-status.json:7` et
     `elevation.json:7` (refus sinon : `generate_design_tokens.py:359`, `:863`), une famille avec variante sombre et
     claire dans `$themeFamilies` (`theme_metadata`, `:210-233`), et `$themeLabels` (`colors.json:256`).
   - Station : `SystemAppearance::themeFor` (`apps/desktop/src/system/SystemAppearance.cpp:102-112`),
     `SettingsStore::families` (`apps/desktop/src/storage/SettingsStore.cpp:58-62`), les familles écrites dans
     `apps/desktop/qml/pages/ApparencePage.qml:80-83`, et les tests (`tst_design_tokens.qml:25`, `:36-41` ; liste
     complète dans [references/fichiers.md](references/fichiers.md)).
   - En QML, un nom inconnu retombe sur le thème par défaut et `Colors.known` devient faux (`theme_preamble`,
     `generate_design_tokens.py:236-255`).
3. **Changer le mouvement.**
   - `design/tokens/motion.json` : `$defaultProfile` et `$reducedProfile` (`:14-15`), `$profileLabels` (`:16`),
     `$legacyProfiles` (`:21`), `$profiles` (`:44`), `$rules` (`:100`).
   - Chaque profil déclare les mêmes entrées que le profil par défaut (refus : `generate_design_tokens.py:836-841`).
   - Aucune transition fonctionnelle au-delà de 240 ms, dans chaque profil (`tst_design_tokens.qml:190-196`,
     `:221-232`). Le profil réduit n'a ni déplacement, ni ambiance, ni activité de sprite (`:198-211`).
   - L'ambiance ne tourne qu'en profil Complet, hors Concentration (`ambianceActive`,
     `generate_design_tokens.py:849-852`). Une animation n'est jamais une preuve d'activité (D165).
   - Un nouveau profil : aussi `SettingsStore::motionProfiles` (`SettingsStore.cpp:64-68`) et les données de
     `tst_design_tokens.qml:213-219`.
   - Les durées des trames de portraits sont **écrites** dans `design/pixel/manifeste.json` (2600, 160 et 240 ms).
     Changer `duration.ambiance` ou `duration.spriteFrame` (`motion.json:41-42`) ne les change pas, et rien ne
     vérifie leur égalité (atelier-da.md § 10).
4. **Changer la disposition ou la densité.** `design/tokens/spacing.json` : jetons `layout.*` et `$densities`
   (`:72`). Sont **recopiés** en C++ : les bornes des panneaux (`SettingsStore.cpp:32-38`) et les noms des densités
   (`SettingsStore::densities`, `:70-74`). Les comparer à la main après toute retouche.
5. **Changer un asset pixel.**
   - Grille texte : un caractère par pixel, `.` pour la transparence, `== nom` ouvre une image, `#` commente
     (`lire_images`, `generer_assets_pixel.py:106-132`). Toutes les lignes d'une image ont la même largeur.
   - Palette du manifeste : clés d'un caractère, valeurs `#rrggbb`, `#rrggbbaa` ou `jeton:<thème>:<jeton>`
     (`charger_palettes`, `:82-103`).
   - Séquence : `etat`, `boucle`, `decoratif` (`construire`, `:432-434`), durées de 60 à 4000 ms (`:416-417`).
     Décoratif veut dire ambiance ; sinon, la séquence suit un état **observé**.
   - Icône : exactement les tailles `TAILLES_ICO` (`:48`), refus sinon (`:375-376`) ; les exports de l'emblème,
     listés au manifeste, en reprennent les neuf tailles. Planche de 2048 px au plus de côté (`PLAFOND_PLANCHE`,
     `:50`, contrôlé `:398-399`).
   - Un nouveau PNG s'ajoute aux `RESOURCES` d'`Acp.Pixel` (`apps/desktop/qml/pixel/CMakeLists.txt:19-31`).
   - Création originale seulement : rien de LimeZu, rien des chemins gelés (atelier-da.md § 6.6). La police pixel
     reste réservée aux libellés courts (D165).
6. **Régénérer**, depuis la racine, dans cet ordre :

   ```sh
   python3.12 apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated
   python3.12 scripts/generer_themes.py          # écrit hermes/theme/acp.yaml seulement
   python3.12 scripts/generer_assets_pixel.py
   ```

   `generer_themes.py` sans `--check` n'écrit pas le QML (`main`, `scripts/generer_themes.py:370-402`).
7. **Capturer** (facultatif, jamais en CI). `ACP_CAPTURES_DIR=<dossier hors dépôt>` sur `tst_pages_bureau` enregistre
   une image par étape (`apps/desktop/tests/cpp/tst_pages_bureau.cpp:271-277`). Poser aussi `QT_QPA_FONTDIR`
   ([atelier-outillage.md](../../../docs/refonte/atelier-outillage.md) § 2.4). Les captures ne se committent pas
   (D17).

## Sorties

- Sources et sorties régénérées dans le **même** commit.
- Les minima de contraste, à reporter dans atelier-da.md § 3.2 s'ils changent.
- Une mention explicite si `hermes/theme/acp.yaml` change (voir Limites).

## Limites

- `acp.yaml` porte l'empreinte des six fichiers lus (`scripts/generer_themes.py:344`) : même une `$description`
  retouchée le change. Il vit sous `hermes/**`, qui déclenche `image.yml` (`.github/workflows/image.yml:134-135`) ; la
  fusion redéploie Hermes (D169). Le thème web reste Studio Graphite, sans clair (D18).
- `scripts/tests/test_generer_themes.py:68-72` fige les piles de polices, la taille de base, l'interligne et le rayon
  du thème web.
- La CI contrôle les assets par l'étape « Vérifier les assets pixel générés » (`.github/workflows/ci.yml:141-143`),
  et Desktop CI se déclenche sur `design/pixel/**` (`.github/workflows/desktop-ci.yml:26-27`). Ces deux ajouts du
  chantier ne sont prouvés qu'à la première exécution de CI qui les porte.
- Aucun test ne compare une image de référence (atelier-da.md § 10). Le rendu hors écran sous Linux diffère de
  Windows. Le rendu de l'icône dans l'Explorateur, la barre des tâches et l'installeur n'est pas vérifié sans
  Windows : c'est le lot F, au backlog ([atelier.md](../../../docs/refonte/atelier.md), section 6).
- `tst_pages_interactions` compare la barre latérale à `surface.sidebar` écrit en dur (`#10131b` et `#eee9f4`,
  `apps/desktop/tests/cpp/tst_pages_interactions.cpp:1072`, `:1078`, `:1082` ; `colors.json:37-38`) : changer ces
  valeurs oblige à changer le test.
- `tst_pages_bureau` passe l'espace de travail dans les quatre thèmes (boucle `themes`,
  `apps/desktop/tests/cpp/tst_pages_bureau.cpp:400-411`) : une capture par thème. Les autres étapes suivent la
  préférence d'apparence en vigueur à ce moment du test.

## Vérification

```sh
python3.12 apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated --check
python3.12 scripts/generer_themes.py --check
python3.12 scripts/generer_assets_pixel.py --check
PYTHONUTF8=1 <venv>/bin/python -m pytest -q -p no:cacheprovider scripts/tests/test_generer_themes.py \
  scripts/tests/test_generer_assets_pixel.py
```

Puis ctest de la station (`tst_qml_shell`, qui lit `tst_design_tokens.qml` et `tst_pixel.qml` ; `tst_pages_bureau` ;
`tst_pages_interactions`), et la table des fichiers de [references/fichiers.md](references/fichiers.md).
