# Étude de référence et direction artistique — station de travail native

Statut : document de direction. Il fixe l'intention visuelle du client natif
C++23 / Qt 6 / Qt Quick et documente le format des jetons de `design/tokens/`.
Aucun écran natif n'existe encore, aucun rendu n'a été observé : ce qui suit est
une règle à appliquer, pas un constat d'application.

Ce document ne remplace pas [`design-system.md`](design-system.md), qui décrit ce
qui est **livré** dans le client web. Les deux clients partagent une identité ; ce
sont deux points de densité d'un même produit, pas deux produits.

## 1. Direction : QUIET OPERATIONS

Le produit est une station de surveillance et de conduite d'agents. L'opérateur
la garde ouverte des heures, souvent sur un demi-écran, à côté d'un éditeur et
d'un terminal. Il y revient pour répondre à trois questions, dans cet ordre :

1. est-ce que quelque chose est en échec ou attend ma décision ?
2. qu'est-ce qui tourne en ce moment, depuis combien de temps ?
3. qu'est-ce qui s'est passé pendant que je regardais ailleurs ?

La direction découle de là. **Calme** : l'interface au repos ne bouge pas et
n'attire pas l'œil ; quand elle attire l'œil, c'est qu'il se passe réellement
quelque chose. **Dense** : l'information tient à l'écran sans défilement inutile,
parce qu'un opérateur compare des lignes entre elles. **Précise** : toute valeur
affichée vient du serveur et sait dire d'où elle vient. **Rapide** : rien
n'attend une animation pour s'afficher. **Reconnaissable** : une teinte
d'accentuation unique, sarcelle, héritée du client web, et une grille de lecture
constante.

Ce qui est refusé comme identité, explicitement :

- les dégradés violet ou bleu en fond de page et de carte ;
- le glassmorphisme, le flou d'arrière-plan et la transparence de fenêtre ;
- les néons, les lueurs, les ombres colorées ;
- la mascotte robot et toute illustration de personnage ;
- les cartes flottantes partout : ici la séparation se fait au trait ;
- les grands nombres décoratifs et les tuiles de statistiques qui occupent un
  écran pour trois chiffres.

Ce n'est pas un tableau de bord SaaS. Le modèle mental est l'outil de métier :
console d'exploitation, table de logs, inspecteur.

## 2. Continuité avec l'existant

Le client web pose déjà une palette dans `apps/web/src/workspace.css:1-46` et un
jeu de variables HUD dans `packages/ui/src/tokens.css:1-42`. La station reprend
la première et s'écarte de la seconde.

Repris à l'identique : le fond `#0e1417`, la barre latérale `#111a1e`, la surface
`#172126`, la surface élevée `#1c292f`, le texte `#edf4f4`, l'accent sombre
`#38b9b0`, ainsi que les couleurs d'attente, de danger et de succès du thème
sombre. L'objectif est qu'une capture du web et une capture de la station se
reconnaissent comme le même produit.

Écarts assumés, tous documentés dans les fichiers de jetons :

| Écart | Web | Station | Raison |
|---|---|---|---|
| Accent en thème clair | `#087f79` | `#0a6d68` | `#087f79` mesure 4,34:1 sur le fond clair, sous le seuil AA pour du texte. |
| Rayons | 8 / 14 / 22 px | 5 / 8 / 12 px, défaut 0 | Les grilles de données se lisent mieux en angles francs. |
| Pastille de statut | gélule `999px` | `radius.xs` (3 px) | Gain de place à chaque ligne d'une liste dense. |
| Ombres | ombre portée large sur les panneaux | aucune ombre sous le niveau 3 | La profondeur est réservée aux couches fermables. |
| Densité | ligne de navigation de 44 px | ligne de liste de 24 à 28 px | Poste de travail au pointeur précis. |

Les variables de `packages/ui/src/tokens.css` (accent `#7c5cff`, fond `#0b0c12`)
appartiennent au HUD du bureau pixel. Elles ne sont **pas** une source pour la
station : elles sont conservées telles quelles pour leur usage d'origine, qui
n'est pas traité ici.

## 3. Ce que quatre produits enseignent

Ces observations restent au niveau du principe. Aucune capture n'a été consultée
pour rédiger cette section, aucune citation n'est reproduite, aucune mesure n'est
attribuée à ces produits. Ce sont des enseignements de conception, pas des
relevés.

### 3.1 Linear — hiérarchie et calme

Ce qu'on retient : une interface peut être extrêmement riche en objets et rester
calme si la hiérarchie est portée par le poids du texte, la couleur du texte et
l'alignement, plutôt que par des boîtes imbriquées. La liste est le composant
central ; la même ligne se lit dans plusieurs vues sans changer de forme. Les
transitions sont courtes et servent la continuité entre deux vues du même objet.
Le clavier est un chemin de première classe, pas un raccourci pour experts.

Ce qu'on en tire : une seule taille de titre par écran, la distinction par le
poids avant la couleur, et une ligne de liste canonique réutilisée pour les
missions, les tâches, les exécutions et les événements.

Ce qu'on refuse : le raffinement graphique poussé jusqu'à masquer l'état. Notre
produit doit pouvoir être laid une seconde s'il le faut pour dire qu'un run a
échoué.

### 3.2 Zed — espace de travail natif dense

Ce qu'on retient : un client natif gagne à assumer sa nature — volets
redimensionnables et persistants, barre d'état permanente, latence perçue nulle
au survol et à la sélection, typographie à chasse fixe là où la comparaison
compte. La densité n'est pas un défaut d'ergonomie, c'est le service rendu à
quelqu'un qui reste dans l'outil.

Ce qu'on en tire : une disposition à trois zones (navigation, contenu,
inspecteur), une barre d'état basse qui porte en permanence l'état du lien au
backend, le survol sans animation, et la chasse fixe obligatoire pour les
identifiants, chemins, durées et sorties brutes.

Ce qu'on refuse : transformer la station en éditeur de code. Le code et les
diff sont consultés, pas édités, tant que le produit n'a pas décidé le contraire.

### 3.3 Warp — blocs d'exécution et flux agent

Ce qu'on retient : une exécution longue se lit bien quand elle est un **bloc**
délimité — une commande, son statut, sa durée, sa sortie, ses artefacts —
plutôt qu'un flot continu de lignes. Le bloc est repliable, copiable, adressable,
et son statut reste visible même replié. C'est exactement la forme d'une
tentative d'agent.

Ce qu'on en tire : le bloc d'exécution est le composant structurant de la
station. Il porte l'identifiant du run, son état sémantique, sa durée, et sépare
visuellement trois informations que la doctrine du produit interdit de
confondre : l'état du run, la validation technique et l'acceptation utilisateur.
Un flux SSE alimente le bloc courant ; il ne fait pas défiler l'écran tout seul.

Ce qu'on refuse : l'esthétique de terminal comme décor. Fond noir pur, curseur
clignotant et couleurs ANSI ne sont employés que dans les zones qui affichent
réellement une sortie de processus, isolées du reste de la feuille de style —
règle déjà posée pour le web dans `design-system.md`.

### 3.4 Raycast — commandes et ergonomie clavier

Ce qu'on retient : une surface unique de commande, ouverte au clavier, qui
cherche à la fois dans les objets et dans les actions, supprime le besoin de
naviguer pour agir. Elle exige que chaque action du produit porte un nom stable
et une portée explicite. Les résultats affichent leur type et leur contexte, pas
seulement leur nom.

Ce qu'on en tire : une palette de commandes est prévue dès la conception, avec
un inventaire nommé des actions et de leur portée (globale, projet, mission,
exécution). Toute action accessible à la souris doit l'être au clavier.

Ce qu'on refuse : la palette comme substitut à une interface lisible. Elle
accélère ce qui est déjà visible ; elle ne cache pas des fonctions.

### 3.5 Synthèse

| Source | Enseignement retenu | Traduction ici |
|---|---|---|
| Linear | hiérarchie par le poids, calme au repos | une taille de titre par écran, ligne de liste canonique |
| Zed | volets natifs, densité, latence nulle | trois zones, barre d'état permanente, survol sans animation |
| Warp | bloc d'exécution délimité et repliable | composant bloc portant run, statut, durée, sortie, artefacts |
| Raycast | commande au clavier, actions nommées | palette de commandes et inventaire d'actions dès la conception |

## 4. Règles concrètes

### 4.1 Densité

Ligne de liste dense à 24 px, 28 px dès qu'elle porte une pastille ou deux
lignes de texte, 34 px seulement pour la configuration. Contrôles à 28 px de
haut. Cible cliquable réelle d'au moins 32 px, obtenue par une zone transparente
autour d'un contrôle plus petit si nécessaire. Trait de séparation d'un pixel.
Le vide sépare, le trait délimite, l'ombre est réservée aux couches flottantes.

Une liste ne devient pas plus lisible en s'aérant : elle le devient par
l'alignement des colonnes et par la chasse fixe des valeurs comparables.

### 4.2 Hiérarchie typographique

Trois niveaux suffisent sur un écran : titre d'écran, titre de panneau, corps.
L'écart entre deux niveaux voisins est d'un ou deux pixels ; la différence se
fait au poids (400, 500, 600) et à la couleur du texte (`text.primary`,
`text.secondary`, `text.muted`). Capitales intégrales réservées aux en-têtes de
colonne. Chasse fixe obligatoire pour tout identifiant, chemin, durée, hachage et
sortie de commande. Texte rédigé limité à 680 px de large, y compris dans un
panneau plus large.

### 4.3 Couleur réservée au statut

Le produit a **une** couleur d'identité, la sarcelle d'accentuation, et neuf
couleurs de statut. En dehors de ces dix teintes, l'interface est neutre.

Conséquences : pas de couleur par projet, pas de couleur par agent, pas de
couleur décorative dans un en-tête, pas de graphique multicolore tant qu'une
palette de visualisation n'a pas été décidée — elle ne l'est pas, et ce fichier
ne l'invente pas.

La couleur n'est jamais le seul porteur d'information : chaque état expose aussi
un libellé français et un nom de glyphe, et trois états — inconnu, non configuré,
hors ligne — se distinguent en plus par une bordure pointillée.

La teinte iris de « approbation requise » est le seul cas où une couleur désigne
une action attendue de l'opérateur et non un fait du système. Elle n'apparaît
nulle part ailleurs : ni en décor, ni en dégradé, ni en fond. C'est la raison
pour laquelle une teinte violette existe malgré l'interdit sur le violet comme
identité — l'interdit porte sur l'identité par défaut, pas sur un signal
réservé.

### 4.4 Mouvement

Aucune animation ne retarde l'affichage d'une information. Rien ne dépasse
240 ms. Le survol et le redimensionnement de volet sont instantanés. Un événement
qui arrive dans un flux apparaît en fondu sans glisser, pour que les lignes
voisines ne bougent pas sous le curseur. Le seul mouvement en boucle autorisé est
la pulsation de l'état « en cours », de période 1600 ms et d'opacité minimale
0,45 — un point qui clignote jusqu'à zéro se confond avec une donnée absente.

Le profil « mouvement réduit » est une variante complète décrite dans
`design/tokens/motion.json` : aucun déplacement, aucune boucle, fondus ramenés à
80 ms, et l'activité signalée par le libellé et un glyphe fixe. Il n'enlève
aucune information.

### 4.5 États vides

Un écran vide dit trois choses : ce qui serait affiché ici, pourquoi ce n'est pas
affiché, et quelle est l'action possible. Il ne dit jamais « tout va bien » et ne
convertit jamais une absence en réussite. Un compteur sans échantillon affiche
`Inconnu`, jamais `0` ni `100 %` — règle déjà posée pour le web et reprise telle
quelle.

Trois vides à ne pas confondre : *rien n'a encore été créé* (action possible),
*le filtre ne renvoie rien* (action : élargir le filtre), *la capacité n'est pas
configurée* (état `Non configuré`, aucun bouton factice, aucun appel externe
déclenché).

### 4.6 États d'erreur

Une erreur affiche sa cause telle que le serveur l'a donnée, l'action réellement
possible, et l'identifiant permettant de la retrouver. Elle ne se déguise pas en
état vide. Elle n'efface pas le contenu déjà affiché : le dernier état connu
reste visible, daté, et signalé comme dernier état connu.

Trois familles restent distinctes, comme dans le client web : accès refusé (une
identité a été refusée), erreur de contrat (la réponse est inexploitable, rien
n'est rendu partiellement), panne (le service ne répond pas). La couleur seule ne
les distingue pas ; le libellé le fait.

### 4.7 Mode hors ligne

Le hors ligne est l'état du lien entre la station et le backend, pas un état de
tâche. Il vit dans la barre d'état basse, en permanence, avec l'horodatage du
dernier échange réussi. Les données déjà reçues restent affichées et sont
marquées comme datées ; aucune donnée de démonstration ne comble un trou ;
aucune action d'écriture n'est proposée comme si elle allait aboutir. Une action
tentée hors ligne échoue de façon fermée et le dit, elle n'est pas mise en file
silencieusement — une file locale n'existera que si elle est conçue, testée et
documentée comme telle.

## 5. Format des jetons

Les jetons vivent dans `design/tokens/` : `colors.json`, `semantic-status.json`,
`typography.json`, `spacing.json`, `radius.json`, `elevation.json`,
`motion.json`. Ils sont destinés à un générateur qui produira des singletons QML.
Ce générateur **n'existe pas encore** ; le format ci-dessous est son contrat
d'entrée.

### 5.1 Enveloppe commune

Chaque fichier expose des métadonnées préfixées par `$` et un objet `tokens` :

```json
{
  "$schema": "acp.design-tokens/1",
  "$description": "…en français…",
  "$version": "1.0.0",
  "$file": "colors",
  "$themed": true,
  "$themes": ["dark", "light"],
  "$defaultTheme": "dark",
  "$qml": { "singleton": "Palette", "module": "Acp.Design", "namingRule": "…" },
  "tokens": { }
}
```

Règles :

- tout champ commençant par `$` est une métadonnée et ne produit pas de jeton ;
- `$description` est obligatoire au niveau du fichier et présent sur tout jeton
  dont l'usage n'est pas évident ; il est rédigé en français ;
- `$themed: true` signifie que chaque jeton porte une valeur par thème, sous les
  clés `dark` et `light` ; `$themed: false` signifie une valeur unique sous
  `$value` ;
- `$type` indique la nature de la valeur : `color`, `dimension`, `duration`,
  `number`, `fontWeight`, `fontFamilyStack`, `cubicBezier`, `elevation`,
  `scrim`.

### 5.2 Nommage et projection vers QML

Le nom d'un jeton est pointé et hiérarchique, du général au particulier :
`surface.panelRaised`, `status.running.foreground`, `density.rowHeight.compact`.
La projection vers QML supprime les points et applique le camelCase :
`surfacePanelRaised`, `statusRunningForeground`, `densityRowHeightCompact`.
Chaque fichier déclare le singleton cible dans `$qml.singleton` — `Palette`,
`Status`, `Type`, `Space`, `Radius`, `Elevation`, `Motion` — dans le module
`Acp.Design`.

Conventions de valeur choisies pour que la projection reste triviale :

- les couleurs sont **opaques**, en hexadécimal six chiffres, directement
  affectables à une propriété `color` ;
- toute valeur à canal alpha vit dans `elevation.json` et s'exprime comme un
  couple `color` opaque plus `opacity` entre 0 et 1, ce qui évite l'ambiguïté
  entre l'hexadécimal à huit chiffres de CSS (`#RRGGBBAA`) et celui de Qt
  (`#AARRGGBB`) ;
- les dimensions sont des pixels logiques, sans unité et sans facteur d'échelle :
  Qt applique lui-même l'échelle de l'écran ;
- les courbes d'accélération sont les quatre points de contrôle d'une Bézier
  cubique, à passer à `easing.bezierCurve` complété par `1, 1` ;
- les piles de polices sont des listes, destinées à `font.families` de Qt 6.

### 5.3 Blocs particuliers

`semantic-status.json` ajoute trois blocs qui ne sont pas des couleurs :

- `$priority` : ordre d'agrégation quand un en-tête résume plusieurs états. Une
  réussite ne masque jamais un échec présent dans le même groupe ;
- `$shapeRules` : ce qui distingue les états **sans** la couleur ;
- `$backendMapping` : la correspondance entre les identifiants d'état réellement
  produits par l'API et les jetons, avec la liste de ses sources. C'est la partie
  du fichier qui vieillit le plus vite ; elle doit être revérifiée à chaque
  évolution des états serveur.

`typography.json` ajoute `$roles`, des compositions prêtes à l'emploi
(`tableCell`, `columnHeader`, `logLine`, `statusChip`…). Un écran natif consomme
un rôle ; s'il en manque un, on l'ajoute ici plutôt que de composer localement.

`motion.json` ajoute `$profiles`, avec `standard` et `reduced` décrits
intégralement l'un et l'autre.

## 6. Vérification des contrastes

Méthode : calcul de la luminance relative et du rapport de contraste selon
WCAG 2.1, appliqué à chaque couleur porteuse de texte contre les quatre fonds du
thème (`surface.canvas`, `surface.panel`, `surface.panelRaised`,
`surface.sunken`), puis à chaque texte de statut contre sa propre teinte de
pastille, puis à chaque bordure d'élément interactif contre sa surface.

Résultats au moment de la rédaction :

| Mesure | Thème sombre | Thème clair | Seuil visé |
|---|---:|---:|---|
| Texte le plus faible sur le fond le plus défavorable | 5,23:1 | 4,60:1 | 4,5:1 |
| Texte de statut sur teinte de pastille, minimum | 4,75:1 | 4,87:1 | 4,5:1 |
| Bordure de pastille contre la surface, minimum | 3,01:1 | 3,01:1 | 3:1 |
| Bordure d'élément interactif contre la surface | 3,19:1 | 3,41:1 | 3:1 |
| Anneau de focus contre le canevas | 13,12:1 | 6,79:1 | 3:1 |
| Encre sur remplissage d'accent plein | 6,97:1 | 6,18:1 | 4,5:1 |

Ce que cette vérification **ne prouve pas** : elle porte sur des paires de
couleurs choisies, pas sur un rendu. Aucun écran n'a été compilé ni observé ; la
chaîne d'outils native est absente du poste. Les superpositions réelles
(pastille posée sur une ligne sélectionnée, texte sur une surface creusée elle-
même survolée) devront être remesurées sur le premier écran natif. Les jetons
non porteurs de texte — `accent.pressed`, `state.hover`, `state.pressed`,
`surface.scrimless` — ne sont pas mesurés et ne revendiquent aucun niveau ; ils
sont listés comme tels dans `colors.json`.

## 7. Limites et questions ouvertes

- Le générateur de jetons vers QML n'existe pas. Le format est un contrat
  d'entrée, il n'a été consommé par rien.
- Aucun rendu natif n'a été produit ni observé. Toutes les valeurs de densité
  (hauteur de ligne, hauteur de contrôle, largeur de barre latérale) sont des
  intentions à confirmer sur un écran réel.
- Le jeu d'icônes n'est pas choisi. `semantic-status.json` nomme des glyphes de
  façon sémantique et déclare explicitement `"resolved": false`.
- Aucune police n'est embarquée. Si Inter est absente du poste, le rendu bascule
  sur les polices système sans réglage : l'échelle typographique a été conçue
  pour rester lisible dans ce cas, ce qui n'a pas été vérifié visuellement.
- La palette de visualisation de données (séries, graphiques, cartes de chaleur)
  n'est pas définie. Elle est inconnue, et volontairement pas inventée ici.
- Les couleurs de sortie de terminal et de diff ne sont pas définies : ces zones
  conservent leurs couleurs réelles et restent isolées, conformément à la règle
  déjà posée pour le web.
- La correspondance `$backendMapping` a été relevée sur la branche
  `feat/desktop-qt-railway` aux emplacements cités dans le fichier. Elle n'est
  pas testée automatiquement ; rien n'empêche aujourd'hui qu'un nouvel état
  serveur apparaisse sans jeton correspondant.
