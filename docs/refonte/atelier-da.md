# Direction artistique de la station : Pixel Atelier et Studio

État du 11 octobre 2026, chantier « atelier » (branche `claude/wonderful-brahmagupta-rlbkuj`, partie de `main` =
`85b458b`, ACP 1.0.1). Décision : D165, dans le [plan](plan.md) § 1, sous-section « Chantier « atelier » ». État du
chantier et matrice des écarts : [atelier.md](atelier.md). Outils, réseau et skills :
[atelier-outillage.md](atelier-outillage.md).

**Statut.** Les jetons de `design/tokens` et les deux générateurs sont le contrat d'exécution. Les assets pixel
(emblème, portraits, pictogrammes, police) sont des **propositions** : le propriétaire ne les a pas validés.

**Convention de preuve.** Les fichiers cités sont ceux de l'arbre de travail du 11 octobre 2026, relus entre 19 h 40
et 20 h UTC, avant le commit du lot B. Un autre agent modifie le code en parallèle : si un numéro de ligne bouge, le
nom de fonction, de propriété ou de jeton cité fait foi. « À `85b458b` » renvoie au commit de départ
(`git show 85b458b:<chemin>`). Chaque mesure donne sa commande et sa date.

Sommaire : § 1 intention · § 2 familles et thèmes · § 3 contrastes mesurés · § 4 typographie · § 5 mouvement ·
§ 6 assets · § 7 facteurs d'échelle fractionnaires · § 8 pont Figma · § 9 références d'ergonomie · § 10 limites.

---

## 1. Intention

Le brief du propriétaire veut un **atelier numérique rétrofuturiste**. La station reste d'abord un outil de travail ;
les pixels l'habillent sans la ralentir. Trois idées guident chaque écran :

- **Le centre de travail est calme.** La mission ouverte, la saisie et les sorties se lisent en police système, sur
  des surfaces sobres.
- **Le décor vit à la périphérie.** Il est plus présent à l'Accueil et en supervision. Il se fait discret dans le
  code, les changements et les sorties.
- **Le décor ne ment jamais.** Une animation ne prouve aucune activité : elle suit un état observé, ou elle se dit
  décorative (§ 5).

Intensité voulue par zone, et ce que fait la station le 11 octobre 2026 :

| Zone | Décor voulu | Constat dans l'arbre de travail |
|---|---|---|
| Accueil | Le plus présent : emblème, scène d'accueil en profil Complet | Pas encore fait : `apps/desktop/qml/pages/HomePage.qml` n'importe pas `Acp.Pixel` (`grep -c 'Acp.Pixel'` rend 0) |
| Supervision des agents | Portraits par rôle, bulle d'état observé | `PortraitAgent` dans le panneau des agents (`apps/desktop/qml/shell/AgentsPanel.qml:86`) ; titre pixel « AGENTS » (`:28`) |
| Projets et missions (barre de gauche) | Emblème, titre pixel, pictogrammes | `FondPixel`, `Embleme`, `TextePixel` (`apps/desktop/qml/shell/SideNavigation.qml:38`, `:119-120`) ; `PictoProjet` par ligne (`apps/desktop/qml/shell/LigneArbre.qml:60`) |
| Mission (centre) | Calme : pictogramme du titre, cadres crantés | `PictoProjet` et `FondPixel` (`apps/desktop/qml/pages/MissionPage.qml:64`, `:313`) |
| Volet bas : changements, tests, sorties | Discret : surface creusée, aucun ornement | Fond `Colors.surfaceSunken` (`apps/desktop/qml/shell/BottomDrawer.qml:17`) ; le module `Acp.Pixel` y est importé (`:11`) sans composant pixel |
| Réglages | Titres pixel, aperçu de l'apparence | `apps/desktop/qml/pages/ReglagesPage.qml:58` ; `apps/desktop/qml/pages/ApparencePage.qml:65-68` et `:218-220` |

**Ce que D165 remplace.**

- La direction « QUIET OPERATIONS » : interface neutre, sans décor. Son texte reste dans
  `apps/desktop/resources/images/README.md:7-8` ; il est à mettre à jour (§ 10).
- L'interdiction générale du décor animé : « jamais décoratif » (`design/tokens/motion.json:3` à `85b458b`).
- D14 (logotype texte), **pour la station seulement**. Le tableau de bord web garde son logotype texte et le thème
  Studio Graphite (`scripts/generer_themes.py:49`) ; D18 reste inchangée pour le web.

**Ce que D165 garde.**

- Les contrastes vérifiés par le générateur, pour les quatre thèmes (§ 3).
- La couleur n'est jamais seule porteuse d'un état : libellé et glyphe l'accompagnent
  (`design/tokens/semantic-status.json:3`).
- Le profil réduit reste complet (`design/tokens/motion.json:107`).
- Aucune fausse activité (`design/tokens/motion.json:104`).
- Aucun asset sous licence (§ 6.6).

---

## 2. Familles et thèmes

Quatre thèmes en deux familles (`design/tokens/colors.json:7`, `:243-255`) :

| Famille | Sombre | Clair | Caractère |
|---|---|---|---|
| **Pixel Atelier** (par défaut) | `atelier-nuit`, thème par défaut (`colors.json:8`) | `atelier-jour` | Bleu encre, ardoise, blanc chaud, lavande et menthe (`colors.json:3`) ; coins crantés |
| **Studio** (alternative sobre) | `studio-graphite` | `studio-papier` | Graphite végétal et papier ivoire, la palette historique de la station ; coins arrondis |

Libellés affichés : « Pixel Atelier — Nuit », « Pixel Atelier — Jour », « Studio — Graphite », « Studio — Papier »
(`colors.json:256-261`). La forme suit la famille : `FondPixel` dessine des coins crantés d'une unité pixel en Pixel
Atelier, et un rectangle arrondi (`Radius.radiusMd`) en Studio (`apps/desktop/qml/pixel/FondPixel.qml:17-18`).

**Choix du thème à l'exécution.**

- L'opérateur choisit la famille (`atelier` ou `studio`, `apps/desktop/src/storage/SettingsStore.cpp:58-62`) et la
  luminosité (système, clair ou sombre, `SettingsStore.cpp:138-152`).
- `SystemAppearance::themeFor` en déduit le thème (`apps/desktop/src/system/SystemAppearance.cpp:102-112`).
  « Système » donne la variante sombre quand le système ne dit rien (`SystemAppearance.cpp:91-100`).
- `ThemeBridge` pose le thème sur `Colors`, `Status` et `Elevation` (`apps/desktop/qml/theme/ThemeBridge.qml:24-28`).
  Le changement se fait à chaud : seules des propriétés changent, aucune page n'est recréée (`ThemeBridge.qml:8-9`).
- Une famille inconnue est refusée par la couche C++ (`SettingsStore.cpp:160-164`). En QML, un thème inconnu retombe
  sur `atelier-nuit` et `Colors.known` vaut faux (`colors.json:14` ; `theme_preamble`,
  `apps/desktop/cmake/generate_design_tokens.py:236`).
- Une station 1.0.x passe à Pixel Atelier. La clé `appearance/family` est nouvelle et vaut `atelier` par défaut
  (`SettingsStore.cpp:154-158`) ; la préférence de luminosité déjà enregistrée est gardée.

**Jetons principaux** (27 jetons de couleur au total dans `design/tokens/colors.json`, version 2.0.0). Extraction :
lecture de `colors.json` par un script Python de la session, le 11 octobre 2026.

| Jeton | `atelier-nuit` | `atelier-jour` | `studio-graphite` | `studio-papier` |
|---|---|---|---|---|
| `surface.canvas` | `#151923` | `#f6f2ea` | `#191c1a` | `#f7f6f0` |
| `surface.sidebar` | `#10131b` | `#eee9f4` | `#131714` | `#eeefe7` |
| `surface.panel` | `#1a1f2d` | `#fffdf8` | `#1e2420` | `#ffffff` |
| `surface.panelRaised` | `#222839` | `#f3eef8` | `#272e29` | `#f2f3eb` |
| `surface.sunken` | `#0e1119` | `#ebe6f0` | `#111612` | `#e8ebe2` |
| `surface.overlay` | `#252b3e` | `#fffefb` | `#282f2a` | `#fffef8` |
| `text.primary` | `#f2ede4` | `#1d1a2e` | `#eef2e9` | `#1f2b23` |
| `text.secondary` | `#c3bfd3` | `#4a4563` | `#b1bcb2` | `#506154` |
| `text.muted` | `#a6a2bd` | `#5a5676` | `#a3b2a5` | `#536657` |
| `text.onAccent` | `#16122c` | `#ffffff` | `#07271c` | `#ffffff` |
| `accent.primary` | `#a99aff` | `#5b47d6` | `#65c6ae` | `#0a6d60` |
| `accent.hover` | `#c0b4ff` | `#4a36c2` | `#86dcc5` | `#085748` |
| `accent.pressed` | `#9584f5` | `#3d2aa6` | `#4eb298` | `#064637` |
| `accent.muted` | `#2c2a4c` | `#e7e2fc` | `#233e32` | `#e0ede4` |
| `accent.secondary` | `#7adbc3` | `#0d7660` | `#a9b9c6` | `#3c5a70` |
| `border.default` | `#333a52` | `#d2cade` | `#3a453c` | `#cdd5c7` |
| `border.interactive` | `#7f82a8` | `#7b7499` | `#7e8e80` | `#748771` |
| `border.focus` | `#7adbc3` | `#0d7660` | `#95e4c9` | `#0a6654` |
| `state.selected` | `#302d58` | `#e6e0fc` | `#2b4435` | `#dceadb` |

**Studio reprend la palette historique.** Comparaison jeton par jeton avec
`git show 85b458b:design/tokens/<fichier>.json` (ancien `dark` contre `studio-graphite`, ancien `light` contre
`studio-papier`) :

- `studio-papier` est identique à l'ancien thème clair, couleurs et états.
- `studio-graphite` diffère sur deux points, imposés par le contrôle automatique (§ 3) : `text.muted` passe de
  `#9aaa9d` à `#a3b2a5`, et les dix bordures d'état `status.*.border` sont un peu éclaircies.
- Quatre jetons sont nouveaux dans les quatre thèmes : `accent.secondary`, `accent.secondaryMuted`, `decor.grid` et
  `decor.outline` (`colors.json:210-241`).
- Côté web, seule la teinte `mutedForeground` change dans `hermes/theme/acp.yaml` (`git diff hermes/theme/acp.yaml`),
  comme D169 l'annonce.

---

## 3. Contrastes mesurés

### 3.1 Ce que le générateur vérifie

`measure_contrasts` (`apps/desktop/cmake/generate_design_tokens.py:289-347`) mesure, thème par thème, les paires
qu'exige la doctrine. `render_all` l'appelle avant toute écriture (`generate_design_tokens.py:939`) : une génération
ou un `--check` sous un seuil est refusé, avec la liste des paires fautives (`:346`). Les seuils sont lus dans
`$contrast` (`colors.json:16-24` ; `semantic-status.json:16-21`).

| Règle | Paires mesurées | Seuil |
|---|---|---|
| `texte` | `text.primary`, `text.secondary`, `text.muted` sur neuf surfaces : canvas, sidebar, panel, panelRaised, sunken, overlay, `state.hover`, `state.selected`, `accent.muted` (`TEXT_SURFACES`, `:282-283`) | 4,5:1 |
| `bordureInteractive` | `border.interactive` sur canvas, sidebar, panel, panelRaised (`CONTROL_SURFACES`, `:285`) | 3:1 |
| `focus` | `border.focus` sur les mêmes quatre surfaces | 3:1 |
| `accent` | `accent.primary` et `accent.secondary` sur les mêmes quatre surfaces | 3:1 |
| `encreSurAccent` | `text.onAccent` sur `accent.primary`, `accent.hover`, `accent.pressed` | 4,5:1 |
| `premierPlan` | premier plan de chacun des dix états sur canvas, panel, panelRaised, sunken (`STATUS_SURFACES`, `:286`) | 4,5:1 |
| `premierPlanSurTeinte` | premier plan de chaque état sur sa propre teinte | 4,5:1 |
| `bordureSurPanneau` | bordure de chaque état sur `surface.panel` | 3:1 |

Soit 106 paires par thème et 424 au total.

### 3.2 Minima mesurés

Mesure du **11 octobre 2026 à 19 h 55 UTC**, Python 3.12.3, depuis la racine du dépôt :

```sh
python3.12 -c "
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('gdt', 'apps/desktop/cmake/generate_design_tokens.py')
gdt = importlib.util.module_from_spec(spec); spec.loader.exec_module(gdt)
d = Path('design/tokens')
r = gdt.measure_contrasts(gdt.load_tokens(d, 'colors'), gdt.load_tokens(d, 'semantic-status'))
print('| Règle | ' + ' | '.join(r) + ' |')
for regle in next(iter(r.values())):
    print('| ' + regle + ' | ' + ' | '.join(f'{r[t][regle]:.2f}' for t in r) + ' |')
"
```

Entrées lues (SHA-256) :

- `design/tokens/colors.json` : `9d6ea83e58cca05cec09add4a99b0f057d4d12c157278095621a4b7df288ea60` ;
- `design/tokens/semantic-status.json` : `965552f6ea536cc171445a72b9cadae171209bf241363e0772381ea0958f1754` ;
- `apps/desktop/cmake/generate_design_tokens.py` : `6f9fd09cf56308c2380e8d3da35ff0d10aebcde42200210409bf1fb7c0cb7f48`.

Sortie recopiée telle quelle, rapports en notation décimale à point (seule la ligne de séparation du tableau Markdown
est ajoutée) :

| Règle | atelier-nuit | atelier-jour | studio-graphite | studio-papier |
|---|---|---|---|---|
| texte | 5.19 | 5.43 | 4.78 | 4.94 |
| bordureInteractive | 3.96 | 3.67 | 4.02 | 3.33 |
| focus | 8.91 | 4.66 | 9.42 | 5.96 |
| accent | 6.12 | 4.66 | 6.79 | 5.38 |
| encreSurAccent | 5.96 | 6.33 | 6.19 | 6.23 |
| premierPlan | 5.86 | 5.17 | 5.18 | 4.61 |
| premierPlanSurTeinte | 5.63 | 5.43 | 4.75 | 4.87 |
| bordureSurPanneau | 3.02 | 3.01 | 3.02 | 3.01 |

**Paire qui fixe chaque minimum.** Méthode : même fonction, seuils portés à 99 dans une copie en mémoire des jetons ;
chaque paire échoue alors, et le message de refus donne sa mesure. Résultat :

| Règle | atelier-nuit | atelier-jour | studio-graphite | studio-papier |
|---|---|---|---|---|
| texte | `text.muted` sur `state.selected` | `text.muted` sur `state.selected` | `text.muted` sur `state.selected` | `text.muted` sur `state.selected` |
| bordureInteractive | sur `surface.panelRaised` | sur `surface.sidebar` | sur `surface.panelRaised` | sur `surface.sidebar` |
| focus | sur `surface.panelRaised` | sur `surface.sidebar` | sur `surface.panelRaised` | sur `surface.sidebar` |
| accent | `accent.primary` sur `surface.panelRaised` | `accent.secondary` sur `surface.sidebar` | `accent.primary` sur `surface.panelRaised` | `accent.primary` sur `surface.sidebar` |
| encreSurAccent | sur `accent.pressed` | sur `accent.primary` | sur `accent.pressed` | sur `accent.primary` |
| premierPlan | `notConfigured` sur `surface.panelRaised` | `blocked` sur `surface.sunken` | `failed` sur `surface.panelRaised` | `notConfigured` sur `surface.sunken` |
| premierPlanSurTeinte | `notConfigured` | `blocked` | `notConfigured` | `notConfigured` |
| bordureSurPanneau | `offline` | `pending` | `failed` | `succeeded` |

Les bordures d'état sont au plus près du seuil (3.01 à 3.02) : une retouche de `surface.panel` ou d'une bordure peut
faire refuser la génération. Le refus arrive alors avant la livraison, pas après.

### 3.3 Ce que le générateur ne vérifie pas

- Déclarés non vérifiés : `surface.scrimless`, `state.pressed`, `decor.grid`, `decor.outline` (`colors.json:23`).
- `border.subtle` reste volontairement sous 3:1 : séparateur décoratif, jamais seul porteur d'information
  (`colors.json:147`). `border.default` n'est pas mesuré.
- Les valeurs à canal alpha (ombres et voiles de `design/tokens/elevation.json`) ne sont pas mesurées.
- Le rendu réel (lissage des polices, ornements, sprites) n'est pas mesuré : seules les couleurs des jetons le sont.

Mesures complémentaires, faites par ce document avec `contrast_ratio` du générateur, **non imposées** par lui
(11 octobre 2026) :

| Mesure | atelier-nuit | atelier-jour | studio-graphite | studio-papier |
|---|---|---|---|---|
| Pire des trois encres de texte sur `accent.secondaryMuted` | 4.97 | 5.88 | 6.12 | 5.03 |
| Pire des trois encres de texte sur `state.pressed` | 5.15 | 5.25 | 4.96 | 4.72 |
| Pire des trois encres de texte sur `state.disabled` | 6.75 | 5.77 | 6.89 | 5.01 |
| `accent.primary` en texte, sur les neuf surfaces de texte | 5.33 | 4.95 | 5.17 | 5.00 |
| `accent.secondary` sur `accent.secondaryMuted` | 7.43 | 4.72 | 6.75 | 5.93 |
| `border.default` sur `surface.panel` | 1.46 | 1.56 | 1.58 | 1.51 |

### 3.4 Avant ce chantier

À `85b458b`, les minima de `$contrast` étaient saisis à la main : 5.63 en sombre et 5.11 en clair
(`design/tokens/colors.json:21-22` à `85b458b`). Le contrôle automatique a révélé deux écarts dans l'ancien thème
sombre, mesurés ici avec la même formule :

- `text.muted` (`#9aaa9d`) sur `state.selected` (`#2b4435`) : 4.35:1, sous 4,5:1 ;
- les dix bordures d'état sur `surface.panel` (`#1e2420`) : de 2.91 à 2.96:1, sous 3:1.

Les deux ont été relevés dans `studio-graphite` (§ 2).

### 3.5 Référentiel

Les seuils s'inspirent de WCAG 2.2 : critère 1.4.3 (contraste minimal du texte, 4,5:1) et critère 1.4.11 (contraste
du contenu non textuel, 3:1). La luminance relative et le rapport suivent la formule de WCAG
(`relative_luminance` et `contrast_ratio`, `generate_design_tokens.py:268-278`). **Ce n'est pas une déclaration de
conformité** du logiciel : aucun audit d'accessibilité n'a été mené, et le rendu réel n'est pas mesuré (§ 3.3).

---

## 4. Typographie

**Piles système, inchangées.** Les deux piles de `design/tokens/typography.json` gardent leurs valeurs de `85b458b` :

- interface : Inter, Inter Variable, Segoe UI Variable Text, Segoe UI, SF Pro Text, Noto Sans, DejaVu Sans
  (`typography.json:14`) ;
- chasse fixe : Cascadia Code, Cascadia Mono, JetBrains Mono, SF Mono, SFMono-Regular, Consolas, DejaVu Sans Mono
  (`typography.json:15`).

**Aucune police tierce embarquée.** Embarquer une police est une redistribution ; aucune licence n'a été choisie
(`apps/desktop/resources/fonts/README.md:17-18`). La décision reste au propriétaire.

**Rôles.** Treize rôles composent la typographie (`typography.json:43-58`) : `pageTitle`, `panelTitle`,
`objectTitle`, `columnHeader`, `tableCell`, `tableCellEmphasis`, `metadata`, `statusChip`, `buttonLabel`, `prose`,
`identifier`, `logLine`, `emptyStateTitle`. Règles (`typography.json:59-65`) : une seule taille au-dessus de 16 px par
écran ; hiérarchie par le poids et la couleur d'abord ; chasse fixe pour tout identifiant, chemin, durée ou sortie ;
capitales intégrales réservées à `columnHeader` ; texte rédigé limité à `measure.prose` (680 px).

**Taille du texte.** Quatre valeurs : 100, 112, 125 et 140 % (`typography.json:66-70` ;
`SettingsStore.cpp:76-80`). Le facteur s'applique à la taille et à la hauteur de ligne de chaque rôle, à chaud
(`apps/desktop/qml/theme/generated/Type.qml:14-16`, `:59-63` ; `ThemeBridge.qml:35-38`).

**Densité.** Compacte, standard ou aérée : chaque densité nomme ses hauteurs de ligne et de contrôle
(`design/tokens/spacing.json:72-78`).

**Police pixel originale.** Capitales 5 × 7 dans une case de 5 × 10 : deux rangées d'accent au-dessus, une de cédille
au-dessous (`design/pixel/sources/police.txt:1-4`).

- 66 glyphes, listés dans `PlanchesPixel.police.glyphes` (singleton engendré
  `apps/desktop/qml/pixel/PlanchesPixel.qml`) :
  les 26 capitales, les 10 chiffres, l'espace et 16 signes (`. , : - / ! ? ' ( ) + # % _ < >`), et 13 capitales
  accentuées (É, È, Ê, Ë, À, Â, Î, Ï, Ô, Ù, Û, Ü, Ç).
- Les capitales accentuées sont composées : la lettre et son accent sont superposés (par exemple `["E", "aigu"]`,
  liste `glyphes` de `design/pixel/manifeste.json:212`).
- Planche `police.png` de 330 × 120 px : 66 colonnes et 12 rangs, un par thème et par couleur (texte = `text.primary`,
  atténué = `text.secondary`, accent = `accent.primary`). Ces couleurs sont lues dans `colors.json`, jamais recopiées
  (`couleur_de_jeton`, `scripts/generer_assets_pixel.py:68-79`).
- **Réservée aux libellés courts** : emblème, titres de section, pastilles. Jamais un paragraphe
  (`police.txt:2-3` ; `apps/desktop/qml/pixel/TextePixel.qml:1-2`). Exemples : « AGENTS », « RÉGLAGES »,
  « COMPTES », « APPARENCE ».
- `TextePixel` met le texte en capitales selon la langue française (`TextePixel.qml:23`) et l'expose aux lecteurs
  d'écran (`Accessible.name`, `TextePixel.qml:27-28`). Un caractère sans glyphe s'affiche « ? » (`:34-35`).
- La police pixel ne suit pas la taille du texte : elle s'agrandit par multiples entiers (`typography.json:67`),
  selon l'échelle choisie par l'écran qui l'emploie (`TextePixel.qml:16`).

---

## 5. Mouvement

### 5.1 Deux natures

`design/tokens/motion.json:3` distingue deux natures, jamais confondues :

- le mouvement **fonctionnel** (survol, appui, focus, panneau, apparition, changement d'état, attention, fin,
  transition de palette) dit d'où vient une chose ; il ne dépasse pas 240 ms et ne retarde jamais l'affichage ;
- le mouvement d'**ambiance** (sprites et scènes décoratifs) n'existe qu'en profil Complet, hors mode Concentration ;
  il se suspend hors écran ou fenêtre réduite, sans appel réseau ni LLM.

### 5.2 Profils et mode Concentration

- **Complet** (par défaut, `motion.json:14`) : fonctionnel et ambiance.
- **Discret** : fonctionnel seulement, sans ambiance. C'était le profil « standard » des versions 1.0.x
  (`motion.json:63-64`).
- **Réduit** (`motion.json:15`) : aucun déplacement, aucune boucle, aucun changement de taille ; les fondus restants
  durent 80 ms ; l'information passe par le texte et le symbole (`motion.json:81-82`).
- **Concentration** : préférence distincte du profil. Elle coupe l'ambiance quel que soit le profil
  (`motion.json:12` ; `Motion.ambianceActive`, `apps/desktop/qml/theme/generated/Motion.qml:229`). Clé
  `appearance/concentration` (`SettingsStore.cpp:21`), appliquée par `ThemeBridge.qml:30-33`.

### 5.3 Règles

Les sept règles de `motion.json:100-108` :

1. Rien ne bouge pendant qu'une donnée arrive : un flux s'allonge, il ne défile pas tout seul.
2. Aucune animation ne retarde l'affichage d'une information.
3. Aucune animation de chargement ne simule une progression inconnue.
4. Une animation n'est jamais une preuve d'activité. Sans télémétrie : « activité détaillée indisponible ».
5. L'ambiance est décorative : profil Complet seulement, suspendue hors écran, fenêtre réduite ou Concentration.
6. Le redimensionnement suit le pointeur sans interpolation.
7. Le profil réduit reste utilisable et complet.

### 5.4 Animations fonctionnelles et d'ambiance

Durées tirées des profils de `motion.json:44-99` et des jetons de durée (`motion.json:27-42`). Courbes : `standard`,
`enter`, `exit`, `linear` (`motion.json:33-36`).

| Animation | Complet | Discret | Réduit |
|---|---|---|---|
| `hover` | 0 ms | 0 ms | 0 ms |
| `press` | 80 ms, `standard` | 80 ms, `standard` | 0 ms |
| `focusRing` | 80 ms, `standard` | 80 ms, `standard` | 0 ms |
| `statusChange` | 120 ms, `standard`, couleur et opacité | idem | 80 ms, `linear`, opacité |
| `overlayEnter` | 180 ms, `enter`, opacité et position (4 px) | idem | 80 ms, `linear`, opacité, sans déplacement |
| `overlayExit` | 120 ms, `exit`, opacité | idem | 0 ms |
| `panelResize` | 0 ms | 0 ms | 0 ms |
| `panelToggle` | 180 ms, `standard`, opacité, largeur, hauteur | idem | 0 ms |
| `listInsert` | 120 ms, `standard`, opacité | idem | 0 ms |
| `activityPulse` | 1600 ms par période, `linear`, opacité, en boucle | idem | 0 ms, aucune boucle |
| `attention` | 240 ms, `standard`, opacité et échelle, deux battements | idem | 80 ms, `linear`, opacité, un seul |
| `completion` | 180 ms, `enter`, opacité et échelle | idem | 80 ms, `linear`, opacité |
| `paletteTransition` | 180 ms, `standard`, couleur | idem | 0 ms |
| `spriteActivity` | 240 ms par image, en boucle | idem | 0 ms, image fixe et libellé « En cours » |
| `ambiance` | 2600 ms par période, en boucle | 0 ms, aucune boucle | 0 ms, aucune boucle |

Sprites des portraits (`design/pixel/manifeste.json`, planche `portraits`) : au repos, 2600 ms puis un clignement de
160 ms (ambiance) ; au travail, deux images de 240 ms (`spriteActivity`). Les autres états n'ont qu'une image fixe.

**Garde-fous dans le code.**

- Un portrait « au travail » ne s'anime que si l'état est observé **et** si le profil l'admet ; au repos, seulement si
  l'ambiance est admise (`apps/desktop/qml/pixel/PortraitAgent.qml:27-29`).
- Un sprite ne tourne que s'il est visible et si la fenêtre n'est ni réduite ni cachée ; sinon la première image
  reste fixe et aucun minuteur ne tourne (`apps/desktop/qml/pixel/SpritePixel.qml:26-27`, `:48-53`).
- La transition de palette couvre la fenêtre de l'ancienne couleur du canevas, puis l'efface ; en Réduit, le
  changement est instantané (`apps/desktop/qml/App.qml:60-90`).

**Branchement au moment de la rédaction** (`grep -rn 'Motion\.' apps/desktop/qml --include=*.qml`, hors fichiers
engendrés) : `press` (`apps/desktop/qml/controls/AcpButton.qml:55-59`), `overlayEnter`
(`apps/desktop/qml/shell/CommandPalette.qml:54-60`), `paletteTransition` (`App.qml:68`, `:86`), `spriteActivity` et
`ambiance` (`PortraitAgent.qml:27-29`), pulsation d'activité (`apps/desktop/qml/components/StatusChip.qml:82-94`).
Les autres animations sont déclarées dans les jetons, pas encore employées par un composant.

### 5.5 Correspondance des anciennes valeurs

| Valeur enregistrée en 1.0.x | Relue par la station de ce chantier | Source |
|---|---|---|
| `standard` | `discret` | `motion.json:21-25` (`$legacyProfiles`) ; `SettingsStore.cpp:171-185` |
| `reduced` | `reduit` | idem |
| aucune valeur enregistrée | `complet`, nouveau défaut | `SettingsStore.cpp:173`, `:184` |

En 1.0.x, l'écran Réglages n'enregistrait que `standard` ou `reduced` (`apps/desktop/qml/pages/SettingsPage.qml:62-66`
à `85b458b`). Une station qui n'a jamais réglé le mouvement passe donc au profil Complet.

---

## 6. Assets

Tous les assets viennent de grilles texte (`design/pixel/sources/*.txt`) et d'un manifeste
(`design/pixel/manifeste.json`). `scripts/generer_assets_pixel.py` les produit, en bibliothèque standard seulement.

### 6.1 Emblème

**Concept.** Un noyau carré (la coordination) entre deux ailes géométriques (la répartition), trois agents en
dessous (`design/pixel/sources/embleme.txt:1-3`). Palette : encre, lavande, menthe, blanc chaud
(`manifeste.json:6-17`). Identique dans tous les thèmes (`apps/desktop/qml/pixel/Embleme.qml:1-2`).

**Une grille dessinée par taille** : 16, 20, 24 et 32 px (`embleme.txt:6`, `:24`, `:46`, `:72`). Les grandes tailles
sont des multiples entiers, agrandis au plus proche voisin (`agrandir`, `scripts/generer_assets_pixel.py:147-154`) :

| Export | Grille source | Échelle |
|---|---|---|
| 16, 20, 24, 32 px | la grille de même taille | × 1 |
| 40 px | 20 | × 2 |
| 48 px | 24 | × 2 |
| 64 px | 32 | × 2 |
| 128 px | 32 | × 4 |
| 256 px | 32 | × 8 |

Source : `embleme.exports` (`manifeste.json:541-616`). Le générateur refuse un export dont la taille ne correspond
pas (`generer_assets_pixel.py:327-333`).

**Icône Windows.** `apps/desktop/resources/windows/AgentCompanyPlatform.ico` : neuf entrées (16, 20, 24, 32, 40, 48,
64, 128 et 256 px ; `TAILLES_ICO`, `generer_assets_pixel.py:48`), en 32 bits : DIB (BGRA, masque ET vide) jusqu'à
128 px, PNG pour 256 px seulement, comme Microsoft le recommande (`encoder_ico`, `:264`). Relu le 11 octobre 2026 par
le générateur et, indépendamment, par Pillow : neuf entrées, pixels identiques aux PNG de l'emblème, alpha 0 ou 255
seulement ; la taille 256 est codée 0 dans le répertoire, selon la convention du format.

Branchements dans l'arbre de travail :

- exécutable : ressource `IDI_ICON1` (`apps/desktop/resources/windows/AgentCompanyPlatform.rc.in:10`), ajoutée sous
  Windows seulement (`apps/desktop/CMakeLists.txt:307-323`) ;
- fenêtre et barre des tâches : `QGuiApplication::setWindowIcon` avec les neuf PNG
  (`apps/desktop/src/main.cpp:99-106`) ;
- installeur : pas de `SetupIconFile` au moment de la rédaction ; l'icône de désinstallation vient de l'exécutable
  (`packaging/windows/AgentCompanyPlatform.iss:50`).

**Lisibilité vérifiée sur fond clair et sombre, aux tailles réelles.** Méthode : les PNG de 16, 20, 24, 32 et 48 px,
décodés par le décodeur du générateur, posés à 1:1 sur six fonds (`#f6f2ea`, `#ffffff`, `#f7f6f0`, `#151923`,
`#191c1a`, `#000000`), puis la planche agrandie × 6 pour la relecture. Compositions gardées dans le dossier de
brouillon de la session, hors dépôt. Constats :

- Fond clair : la silhouette du carreau est franche (contour `#0b0d14` à 17.38:1 sur `#f6f2ea`, 19.41:1 sur blanc).
- Fond sombre : le carreau se fond dans le fond (1.10:1 sur `#151923`, 1.13:1 sur `#191c1a`, 1.08:1 sur noir). Les
  ailes menthe (10.67:1 sur le carreau) et le noyau lavande (7.32:1) portent seuls la forme ; ils restent lisibles.
- À 16 px, les trois agents se réduisent à trois points de 1, 2 et 1 pixels (`embleme.txt:19`).
- Non vérifié : le rendu par Windows (Explorateur, barre des tâches, menu Démarrer), faute de machine Windows (§ 10).

### 6.2 Portraits d'agents

- 16 × 16 px, six rôles et six états : 36 séquences, planche `portraits.png` de 32 × 576 px (deux colonnes, un rang
  par séquence).
- Rôles et accessoires : coordinateur (casque), développeur (bandeau), relecteur (lunettes), explorateur (loupe),
  testeur (insigne), inconnu (silhouette sans accessoire).
- États : repos, travail, attente, échec, terminé, arrêté. Les bulles d'attente, d'erreur, de réussite et d'arrêt
  ont leurs propres clés de couleur (`design/pixel/sources/portraits.txt:3-4`).
- **Échange de palette** : un calque par élément ; le générateur superpose les calques et applique la palette du rôle
  (`portraits.txt:1-2` ; palettes `portrait-*` du manifeste).
- **Aucun logo de fournisseur** : le rôle se lit à l'accessoire, le fournisseur au texte (`portraits.txt:5`). La page
  Comptes nomme « Codex » et « Claude Code » en texte, à côté d'un portrait de rôle
  (`apps/desktop/qml/pages/ComptesPage.qml:86-91`, `:102-107`).
- **Images animées seulement sur état observé** : la séquence « travail » n'est pas décorative ; elle ne tourne que
  si `observe` est vrai (§ 5.4). Le clignement au repos est marqué décoratif. Un rôle inconnu retombe sur le portrait
  « inconnu » du même état (`PortraitAgent.qml:22-26`).

### 6.3 Pictogrammes de projets

- 12 × 12 px, sept motifs (fusée, cristal, feuille, livre, éclair, planète, engrenage) en cinq teintes (lavande,
  menthe, ambre, rose, ciel) : planche `pictogrammes.png` de 84 × 60 px.
- **Décoratifs** : ils ne portent aucune donnée (`design/pixel/sources/pictogrammes.txt:1-2`) et sont exclus de
  l'accessibilité (`apps/desktop/qml/pixel/PictoProjet.qml:19`).
- **Attribution stable par identifiant** : empreinte FNV-1a 32 bits de la clé, stable d'une exécution à l'autre,
  contrairement à `qHash` (`apps/desktop/src/viewmodels/EspaceTravailViewModel.cpp:64-73`), puis motif et teinte tirés
  de cette empreinte (`:365-376`). La clé vaut `g:` suivi du dépôt pour une ligne de groupe (`:230`, `:243`),
  l'identifiant de mission pour une mission (`:283`).

### 6.4 Police

Décrite au § 4. Sa planche dépend des jetons de texte : toute retouche de `text.primary`, `text.secondary` ou
`accent.primary` dans `colors.json` rend `police.png` périmée, et `--check` le signale.

### 6.5 Procédure d'export

```sh
python scripts/generer_assets_pixel.py            # écrit les sorties
python scripts/generer_assets_pixel.py --check    # échoue si une sortie est périmée, sans rien écrire
```

- 17 sorties : neuf PNG de l'emblème, l'icône `.ico`, trois planches, leurs trois fichiers de métadonnées
  (`design/pixel/generes/*.json`) et le singleton QML `PlanchesPixel`.
- **Vérification par pixels décodés, pas par octets** : deux versions de zlib peuvent compresser différemment la même
  image (`generer_assets_pixel.py:14-17`). `verifier` décode chaque PNG et chaque entrée de l'icône, et compare les
  pixels (`:470-490`) ; le JSON et le QML sont comparés en texte.
- Refus explicites, en français : caractère absent de la palette, calques de tailles différentes, durée d'image hors
  de 60 à 4000 ms (`:385`), planche de plus de 2048 px (`PLAFOND_PLANCHE`, `:50`), chemin de sortie non confiné.
- Mesure du 11 octobre 2026 : `python3.12 scripts/generer_assets_pixel.py --check` rend « 17 assets pixel à jour. »,
  code 0.
- Après une retouche de jetons : `python scripts/generer_themes.py --check` contrôle le thème web et le QML de
  `Acp.Design` ; `generer_assets_pixel.py --check` contrôle la police (§ 6.4).

### 6.6 Provenance et licence

- **Créations originales du chantier**, dessinées le 11 octobre 2026 par l'agent de développement : grilles texte
  composées à la main, puis inspectées à l'image agrandie. Ce document les a relues à l'image le même jour (§ 6.1).
- **Proposées au propriétaire, non validées par lui** (`design/pixel/manifeste.json:3` ; `embleme.txt:4`).
- **Licence** : le dépôt n'en déclare aucune. Il n'a pas de fichier `LICENSE` à la racine, et `package.json:3` dit
  seulement `"private": true`. Le choix de la licence, assets compris, appartient au propriétaire.
- **Aucun asset LimeZu, aucun asset du moteur gelé.** Le générateur ne lit que `design/pixel` et
  `design/tokens/colors.json` (`generer_assets_pixel.py:37-39`, `:304`).
  `git status --short packages apps/web plugins` ne montre aucun changement. Les packs sous licence restent exclus
  par `.gitignore:39-46`.
  `scripts/check_engine_frozen.py` est invérifiable dans ce clone : l'étiquette `archive/acp-0.10.0-avant-hermes` y
  est absente. La CI, qui la récupère, en reste juge.
- **Aseprite n'a pas été utilisé** : il est absent de la session ([atelier-outillage.md](atelier-outillage.md) § 2.1).
- **Aucune police tierce** : la police pixel est un dessin original (§ 4).

---

## 7. Facteurs d'échelle fractionnaires

**Politique de Qt mesurée.** La station ne règle pas la politique d'arrondi du facteur d'échelle (`grep` de
`RoundingPolicy` et `HighDpi` dans `apps/desktop/src` : vide). Qt 6.8.3 garde alors `PassThrough`. Sonde compilée
contre `/opt/acp-outils/qt683`, plateforme `offscreen`, le 11 octobre 2026 : politique 5 (= `PassThrough`) ; avec
`QT_SCALE_FACTOR` à 1.25 et 1.5, `devicePixelRatio` vaut 1.250 et 1.500. Sur un écran à 125 % ou 150 %, le facteur
fractionnaire passe donc tel quel.

**Sprites et police pixel.** Ils sont agrandis par **multiples entiers en pixels logiques**, sans lissage :
`SpritePixel` mesure `case × echelle` (`apps/desktop/qml/pixel/SpritePixel.qml:30-31`) avec `smooth: false` et
`mipmap: false` (`:43-44`) ; `TextePixel` agrandit aussi sans lissage (`TextePixel.qml:36-41`). En pixels
physiques, le multiple n'est entier que si `echelle × facteur` l'est. Mesure, même sonde, damier de huit pixels
affiché à l'échelle 2 avec `smooth: false` (moteur de rendu logiciel) :

| Facteur | Largeur physique de chaque pixel source |
|---|---|
| 1.00 | 2, 2, 2, 2… |
| 1.25 | 3, 2, 3, 2… : irrégulier |
| 1.50 | 3, 3, 3, 3… |
| 2.00 | 4, 4, 4, 4… |

À 125 %, un sprite à l'échelle 2 a donc des pixels de largeur inégale. Sous Windows, le moteur de rendu peut répartir
autrement les largeurs de 2 et de 3, sans pouvoir les rendre égales : non mesuré.

**Emblème.** `Embleme` choisit la plus petite taille dessinée qui couvre `taille × facteur`
(`apps/desktop/qml/pixel/Embleme.qml:13-22`). À 125 %, un emblème de 24 px logiques demande 30 px physiques : la
grille de 32 px est retenue, puis réduite à 30 px au plus proche voisin. Mesure, même sonde, avec un dégradé de
32 colonnes distinctes : 30 colonnes source sur 32 restent visibles. Deux colonnes de la grille tombent ; la même
réduction s'applique aux rangées (non mesuré séparément). À 150 %, la grille de 40 px est réduite à 36 px : non
mesuré.

**Polices et contrôles.** Ils ne sont pas pixelisés. Le texte courant reste en polices système vectorielles, mises à
l'échelle par Qt ; les contrôles sont des rectangles. Seule la taille du texte choisie par l'opérateur (§ 4) les
agrandit en plus. Les coins crantés de `FondPixel` mesurent une unité de 2 px logiques (`Space.layoutPixelUnit`,
`design/tokens/spacing.json:59`), soit 2,5 px physiques à 125 % : rendu non mesuré.

---

## 8. Pont Figma

**État.** Le serveur MCP Figma de la session est en échec de connexion : le mandataire refuse le tunnel (403). Aucun
fichier Figma n'a été lu ni écrit ([atelier-outillage.md](atelier-outillage.md) § 5).

**Ce qui fait foi.**

- Les **jetons versionnés** de `design/tokens` sont le contrat d'exécution. Le générateur les refuse sous les seuils
  de contraste (§ 3) ; aucune maquette ne les contourne.
- La **galerie native** sert de référence visuelle : des captures de la vraie application, rendues par Qt hors écran,
  gardées hors dépôt (D17). Au moment de la rédaction, elle compte les 17 captures « avant » du lot A, dans le dossier
  de brouillon de la session. Les captures « après » restent à produire.

**Procédure proposée pour un futur pont.** Rien de ceci n'est fait.

1. Avec un MCP Figma connecté, la skill `qt-figma-token-extraction` des Qt Agentic Tools produit un
   `design-tokens.json` depuis la bibliothèque Figma. Cette skill est seulement listée au README du dépôt
   `TheQtCompanyRnD/agent-skills` (ligne 42 de la copie de travail du 11 octobre 2026) : elle n'a été ni lue ni
   exécutée ([atelier-outillage.md](atelier-outillage.md) § 6.1). Les singletons QML qu'elle produit ne seraient pas
   repris : `Acp.Design` reste engendré par `generate_design_tokens.py`.
2. Un script, à écrire, convertit `design-tokens.json` vers `design/tokens/*.json` (schéma `acp.design-tokens/1`,
   quatre thèmes). Il refuse un jeton sans correspondance et ne crée jamais de thème implicite.
3. Régénération, depuis la racine du dépôt :

   ```sh
   python apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated
   python scripts/generer_themes.py
   python scripts/generer_assets_pixel.py
   ```

4. Contrôle : les trois `--check`, puis une PR relue, avec captures avant et après dans la galerie native.

Figma propose ; les jetons versionnés décident. Aucune synchronisation automatique n'est prévue. Ce pont est un outil
de développement : côté produit, Figma reste « hors-v1 » au catalogue de Hermes
(`hermes/catalogue/catalogue.lock.json:1117-1127`).

---

## 9. Références d'ergonomie

Le brief cite Claude Code Desktop et Codex comme références d'ergonomie. Elles servent de **références de parcours** :
barre des projets, saisie persistante au centre, volet des changements et des sorties. Elles ne sont pas un modèle
visuel. Aucune marque, aucun logo, aucune capture et aucun asset n'en est repris. Les assets viennent tous des sources
texte de `design/pixel` (§ 6.6). Les noms « Codex » et « Claude Code » n'apparaissent qu'en texte, pour désigner les
CLI que l'exécutant pilote réellement (§ 6.2).

---

## 10. Limites

- **Captures.** Aucune capture « après » n'existe encore, et aucun test ne compare une image de référence.
- **Pas de profilage.** Aucune mesure de cadence ni de charge GPU : la session n'a ni GPU ni machine de référence. Le
  profilage à 60 images par seconde reste au lot F ([atelier.md](atelier.md) § 6).
- **Icône non installée sous Windows.** Aucune installation de test : l'icône n'a été vue ni dans l'Explorateur, ni
  dans la barre des tâches, ni dans le menu Démarrer. L'installeur n'a pas encore de `SetupIconFile`.
- **Échelle fractionnaire.** À 125 %, les pixels des sprites ont des largeurs inégales, et l'emblème perd des
  colonnes (§ 7).
- **Emblème sur fond sombre.** Le carreau se fond dans un fond sombre ; seuls les ailes et le noyau portent la forme
  (§ 6.1).
- **Accueil sans décor.** La page d'Accueil n'emploie pas encore `Acp.Pixel` (§ 1).
- **Animations déclarées, pas toutes branchées.** `focusRing`, `statusChange`, `overlayExit`, `listInsert`,
  `panelToggle`, `attention` et `completion` n'ont pas encore de consommateur (§ 5.4).
- **Durées recopiées.** Les durées des images des portraits (2600, 160 et 240 ms) sont écrites dans le manifeste.
  Elles égalent les jetons `duration.ambiance` et `duration.spriteFrame` (`motion.json:41-42`) ; rien ne vérifie
  cette égalité.
- **Contrastes partiels.** Couches à canal alpha, ornements et rendu réel ne sont pas mesurés (§ 3.3).
- **Police pixel.** Pas de Œ, Æ ni Ÿ ; pas de minuscules. Elle ne suit pas la taille du texte (§ 4).
- **Métadonnées des pictogrammes.** Leurs séquences portent `"decoratif": false` dans `PlanchesPixel`, faute du champ
  dans le manifeste. Sans effet aujourd'hui : `PictoProjet` s'exclut de l'accessibilité.
- **Textes hérités.** La description de `accent.primary` parle encore de « sarcelle » (`colors.json:115`), et celle de
  `surface.canvas` de « graphite chaud » (`colors.json:27`) : vrai pour Studio seulement. Le README des images dit
  toujours « QUIET OPERATIONS » (`apps/desktop/resources/images/README.md:7-8`).
- **Contrôles non branchés en CI.** Au moment de la rédaction, aucun workflow n'appelle
  `scripts/generer_assets_pixel.py --check` (`grep -rn generer_assets_pixel .github` : vide), et `scripts/tests` n'a
  aucun test des assets. `apps/desktop/tests/qml/tst_pixel.qml` (nouveau, non suivi) couvre portraits, police, tailles
  de l'emblème et garde-fous d'animation ; ce document ne l'a pas exécuté.
- **Assets non validés, licence non déclarée** (§ 6.6).
