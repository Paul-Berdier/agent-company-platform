# Refonte graphique du Pixel Office Engine — audit et plan de migration Phaser 3

> Statut : **proposition, en attente de validation**. Aucune implémentation commencée.
> Périmètre : frontend uniquement (`packages/pixel-office-engine`, `packages/ui`, `apps/web`).
> Le backend n'est pas modifié.

---

## 1. Audit du moteur actuel

### 1.1 Inventaire

| Élément | Localisation | État |
|---|---|---|
| Moteur | `packages/pixel-office-engine/src/index.ts` (~450 lignes) | Canvas 2D procédural |
| Contrats publics | même fichier : `SceneSpec`, `RoomSpec`, `StationSpec`, `EntitySpec`, `EngineCallbacks` | sains, à préserver |
| Construction des scènes | `apps/web/src/scene.ts` | data-driven (overview API + office-configs des modules) |
| Orchestration UI | `apps/web/src/main.ts` | appelle `setScene`, `updateEntityStatus`, `emote`, `pulseRoom` |

### 1.2 API publique actuelle (à préserver)

```ts
class PixelOfficeEngine {
  constructor(canvas: HTMLCanvasElement, callbacks?: EngineCallbacks)
  setScene(scene: SceneSpec): void
  updateEntityStatus(entityId: string, status: string): void
  emote(entityId: string, glyph: string, durationMs?: number): void
  pulseRoom(roomId: string): void
  destroy(): void
}
```

### 1.3 Points forts

- **Frontière domaine/rendu propre** : le moteur ne connaît ni départements ni rôles ;
  `scene.ts` traduit le métier en `SceneSpec`. Cette frontière est le socle de la migration.
- Mapping statut→animation déjà externalisé (`status_mapping` des plugins).
- API événementielle (`updateEntityStatus`, `emote`, `pulseRoom`) directement transposable.
- Rendu synchrone de la première frame (robuste aux onglets cachés).

### 1.4 Dettes et limites (motifs de la refonte)

| Dette | Détail |
|---|---|
| **Visuels codés en dur** | `THEMES` (5 palettes), `SKIN/HAIR/SHIRT`, dessin des stations par `switch(kind)` : desk, whiteboard, server-rack, bookshelf, couch, art-station. Ajouter un meuble = modifier le moteur. |
| **Emojis** | glyphes de statut (`⌨ ☕ 📖 🎮…`) et émotes (`⚙ ✔ ✖`) dépendants de la police système, rendu incohérent selon OS. |
| **Pas de pipeline d'assets** | aucune image, aucun atlas, aucune animation de frames. |
| **Grille non fixe** | taille de tuile recalculée depuis le canvas (`tile = min(w/cols, h/rows)`), pas de 32×32 stable. |
| **Déplacement naïf** | interpolation directe vers la cible, errance aléatoire, traversée des murs et meubles, pas de pathfinding. |
| **Pas de réservation de stations** | attribution round-robin dans `scene.ts` ; deux agents peuvent occuper le même siège. |
| **Pas de caméra** | ni pan, ni zoom, ni sélection persistante, ni surbrillance. |
| **Profondeur simpliste** | tri par `y` des seules entités ; pas de couches meubles avant/arrière. |
| **`setScene` destructif** | reconstruction complète à chaque refresh d'overview (positions préservées manuellement). |
| **Aucun test** | ni sur le moteur ni sur la construction de scènes. |

---

## 2. Architecture de migration

### 2.1 Principe

Introduire une interface de rendu commune `IOfficeRenderer`, extraire les contrats,
déplacer le moteur actuel en **renderer legacy (fallback)** et ajouter un
**renderer Phaser 3** derrière une couche d'adaptation. `apps/web` ne dépend plus
d'une classe mais d'une factory.

```text
apps/web (main.ts, scene.ts)
        │  SceneSpec (contrat inchangé, étendu par champs optionnels)
        ▼
createOfficeRenderer({ mode: "phaser" | "canvas" | "auto", ... })
        │
        ├── legacy/CanvasRenderer      ← moteur actuel, fallback temporaire
        │
        └── phaser/PhaserRenderer
             ├── adapter/scene-adapter    SceneSpec → objets Phaser (diff, pas rebuild)
             ├── assets/manifest-loader   charge et valide les packs d'assets
             ├── assets/animation-mapper  statut → animation → clip d'atlas
             ├── grid/pathfinding         A* sur grille 32×32
             ├── grid/reservations        occupation des stations
             ├── camera/camera-controller pan, zoom, sélection, surbrillance
             ├── scenes/OfficeScene       rendu du bureau (6 couches)
             └── scenes/GalleryScene      galerie de tous les assets/animations
```

### 2.2 Arborescence cible du package

```text
packages/pixel-office-engine/
├── package.json                  # + phaser (import dynamique), + vitest
├── src/
│   ├── index.ts                  # barrel : contrats + createOfficeRenderer
│   ├── contracts/
│   │   ├── scene.ts              # SceneSpec, RoomSpec, StationSpec, EntitySpec (+ extensions)
│   │   ├── assets.ts             # AssetManifest, AtlasDef, CharacterDef, StationAssetDef...
│   │   └── renderer.ts           # IOfficeRenderer, RendererOptions, EngineCallbacks
│   ├── legacy/
│   │   └── canvas-renderer.ts    # moteur actuel déplacé tel quel (fallback)
│   ├── phaser/
│   │   ├── phaser-renderer.ts
│   │   ├── layers.ts             # ordre des 6 couches
│   │   ├── adapter/scene-adapter.ts
│   │   ├── assets/manifest-loader.ts     # sans dépendance Phaser (testable)
│   │   ├── assets/animation-mapper.ts    # sans dépendance Phaser (testable)
│   │   ├── grid/pathfinding.ts           # A* pur (testable)
│   │   ├── grid/reservations.ts          # pur (testable)
│   │   ├── camera/camera-controller.ts
│   │   └── scenes/{OfficeScene,GalleryScene}.ts
│   └── fallback.ts               # sélection auto + bascule sur échec de chargement
├── tests/
│   ├── manifest-loader.test.ts
│   ├── animation-mapper.test.ts
│   ├── pathfinding.test.ts
│   └── reservations.test.ts
└── tools/
    └── generate-placeholders.mjs # génère les PNG placeholders originaux
```

Les modules `manifest-loader`, `animation-mapper`, `pathfinding`, `reservations`
sont écrits **sans import Phaser** pour être testés en Node avec vitest.

### 2.3 Sélection du renderer et fallback

- `?renderer=phaser|canvas` dans l'URL, sinon `auto`.
- `auto` : tente Phaser (import dynamique) ; en cas d'échec (chargement, manifest
  invalide, WebGL absent), bascule sur le renderer canvas et journalise la raison.
- Le renderer canvas legacy est conservé tel quel pendant toute la migration puis
  retiré dans une étape finale distincte, jamais avant.

---

## 3. Nouveaux contrats

### 3.1 Extensions des contrats existants (champs **optionnels** uniquement)

```ts
interface StationSpec {
  id: string; name: string; kind: string; x: number; y: number;   // inchangé
  assetId?: string;          // id d'asset station dans un pack (sinon résolu par kind)
  facing?: "up" | "down" | "left" | "right";
  footprint?: { w: number; h: number };  // en tuiles, défaut 1×1
  capacity?: number;         // sièges, défaut 1
  layerHint?: "furniture-back" | "furniture-front";
}

interface RoomSpec {
  id: string; name: string; theme: string; x: number; y: number;
  w: number; h: number; badge?: string; stations: StationSpec[];  // inchangé
  themeId?: string;          // thème d'un pack d'assets (prioritaire sur theme)
  tilemapId?: string;        // salle dessinée dans une tilemap Tiled dédiée
}

interface EntitySpec {
  id: string; name: string; role: string; status: string;
  roomId: string; stationId?: string; sprite?: string;            // inchangé
  characterId?: string;      // personnage d'un pack (sinon résolu par sprite/role)
  speedTilesPerSec?: number; // défaut 3
}

interface SceneSpec {
  cols: number; rows: number; rooms: RoomSpec[]; entities: EntitySpec[];
  statusMapping?: Record<string, string>;
  animationGlyphs?: Record<string, string>;                       // legacy only
  assetPackIds?: string[];   // packs à charger pour cette scène
  gridTile?: number;         // défaut 32
}

interface EngineCallbacks {
  onRoomClick?: (roomId: string) => void;
  onEntityClick?: (entityId: string) => void;
  onEntityHover?: (entityId: string | null) => void;              // nouveau
  onRendererFallback?: (reason: string) => void;                  // nouveau
}
```

Aucun champ existant n'est renommé ni supprimé : les scènes actuelles restent
valides pour les deux renderers.

### 3.2 Interface de rendu commune

```ts
interface IOfficeRenderer {
  setScene(scene: SceneSpec): void;
  updateEntityStatus(entityId: string, status: string): void;
  emote(entityId: string, effectId: string, durationMs?: number): void; // effectId d'un pack ; glyphe texte accepté en legacy
  pulseRoom(roomId: string): void;
  selectEntity(entityId: string | null): void;    // nouveau
  focusRoom(roomId: string): void;                // nouveau (caméra)
  showGallery(): void;                            // nouveau
  destroy(): void;
}
```

---

## 4. Format des manifests d'assets

### 4.1 Principes

- **Tout le visuel vient des manifests** : personnages, meubles, sols, murs,
  effets, thèmes, alias d'animations. Le moteur ne contient plus aucun `switch`
  visuel par kind ni aucune palette métier.
- Un **pack** = un dossier avec `manifest.json` + images. Le pack `core` est
  toujours chargé ; les packs de départements s'y ajoutent (`"extends": "core"`).
- Grille **32×32**, personnages **32×48** (pivot aux pieds).

### 4.2 `manifest.json` (version 1.0)

```jsonc
{
  "manifest_version": "1.0",
  "pack_id": "dept-software-engineering",
  "extends": "core",                       // héritage : le pack complète core
  "grid": { "tile": 32, "character": { "w": 32, "h": 48 } },

  "atlases": [
    { "id": "furniture-dev", "image": "atlases/furniture-dev.png",
      "data": "atlases/furniture-dev.json" }        // JSON hash TexturePacker-compatible
  ],

  "tilesets": [
    { "id": "floors-dev", "image": "tilesets/floors-dev.png",
      "tile": 32, "margin": 0, "spacing": 0 }
  ],

  "tilemaps": [
    { "id": "demo-office", "file": "tilemaps/demo-office.tmj", "format": "tiled-json" }
  ],

  "characters": [
    {
      "id": "dev-male-a",
      "atlas": "characters-core",
      "size": { "w": 32, "h": 48 },
      "pivot": { "x": 0.5, "y": 0.9 },     // ancre : pieds
      "animations": {
        "idle-down":  { "frames": "dev-a/idle-down/{0..3}",  "frameRate": 4, "repeat": -1 },
        "walk-down":  { "frames": "dev-a/walk-down/{0..5}",  "frameRate": 8, "repeat": -1 },
        "walk-up":    { "frames": "dev-a/walk-up/{0..5}",    "frameRate": 8, "repeat": -1 },
        "walk-left":  { "frames": "dev-a/walk-left/{0..5}",  "frameRate": 8, "repeat": -1 },
        "walk-right": { "frames": "dev-a/walk-right/{0..5}", "frameRate": 8, "repeat": -1 },
        "type":       { "frames": "dev-a/type/{0..3}",       "frameRate": 6, "repeat": -1 },
        "think":      { "frames": "dev-a/think/{0..1}",      "frameRate": 2, "repeat": -1 }
      }
    }
  ],

  "stations": [
    {
      "kind": "desk",                       // résolution par kind (compat scènes actuelles)
      "id": "desk-dev",                     // ou par assetId explicite
      "atlas": "furniture-dev",
      "frames": { "back": "desk/basic-back", "front": "desk/basic-front" },
      "footprint": { "w": 2, "h": 1 },
      "pivot": { "x": 0, "y": 1 },
      "seats": [ { "dx": 0, "dy": 1, "facing": "up" } ],
      "blocking": true                      // participe à la grille de collision
    }
  ],

  "themes": [
    { "id": "dev-floor", "tileset": "floors-dev",
      "floorTiles": [1, 2], "wallTiles": [17], "accentColor": "#2b6cb0" }
  ],

  "effects": [
    { "id": "task-complete", "atlas": "fx-core",
      "animation": { "frames": "fx/check/{0..5}", "frameRate": 12, "repeat": 0 } }
  ],

  "role_characters": {                      // rôle métier → personnage (data, pas code)
    "frontend-developer": ["dev-male-a", "dev-female-a"],
    "*": ["worker-default"]
  },

  "animation_aliases": {                    // noms d'animations des plugins → clips
    "coffee": "idle-down",
    "chart": "type",
    "point": "think"
  }
}
```

### 4.3 Chaîne de résolution d'une animation

```text
statut agent ("working")
  → status_mapping du département (plugin backend)   → "type"
  → animation_aliases du pack                          → "type" (ou alias)
  → clip du personnage ; absent ? → alias ; absent ? → "idle-down" (garanti par core)
```

Cette chaîne est implémentée dans `animation-mapper.ts` et couverte par les tests.

### 4.4 Format des spritesheets (résumé — doc complète : `docs/spritesheets.md`)

- **Personnages** : frames 32×48 px, PNG transparent, regroupées en atlas
  (JSON hash, noms `"<character>/<animation>/<index>"`). 4 directions pour walk
  (down/up/left/right, 6 frames), idle 4 frames, animations métier libres.
  Pivot recommandé (0.5, 0.9) = pieds. Marge 0, pas d'anti-aliasing, palette libre.
- **Meubles** : découpe en `back` (derrière le personnage) et `front`
  (devant, ex. dossier de chaise), footprint en tuiles entières, pivot bas-gauche.
- **Tilesets** : tuiles 32×32, PNG, sans espacement (margin 0, spacing 0),
  premier gid géré par la tilemap Tiled.
- **Tilemaps** : Tiled ≥ 1.10, export JSON (`.tmj`), orientation orthogonale,
  couches nommées `floor`, `walls`, `collision` (calque objet ou tile layer avec
  propriété `collides=true`).

---

## 5. Arborescence des assets

Les assets sont servis statiquement par le front (aucun changement backend).
Les packs de départements sont **découverts via un index**, donc chargeables
comme plugins sans toucher au moteur :

```text
apps/web/public/assets/
├── packs.json                      # index des packs disponibles (id → chemin)
├── core/
│   ├── manifest.json
│   ├── atlases/
│   │   ├── characters-core.png / .json
│   │   ├── furniture-core.png  / .json
│   │   └── fx-core.png         / .json
│   ├── tilesets/office-base.png
│   └── tilemaps/demo-office.tmj    # tilemap Tiled de démonstration
├── dept-software-engineering/
│   ├── manifest.json               # extends: core
│   ├── atlases/furniture-dev.png / .json
│   └── tilesets/floors-dev.png
├── dept-data-science/…
├── dept-research/…
└── dept-game-development/…
```

- `packs.json` mappe `department_type` → `pack_id`, ce qui permet à `scene.ts`
  de remplir `assetPackIds` sans rien coder en dur.
- **Placeholders** : tous les PNG initiaux sont générés par
  `tools/generate-placeholders.mjs` (dessins originaux : silhouettes, meubles
  géométriques stylisés, damiers) — aucun asset tiers. Remplacer un placeholder
  = déposer un PNG du même nom, sans changement de code.
- Plus tard (hors périmètre) : servir les packs depuis `plugins/<module>/assets/`
  via l'API ; le format du manifest ne changera pas.

---

## 6. Système de couches

Ordre de rendu dans `OfficeScene` (du fond vers l'avant) :

```text
1. floor            tilemap layer (sol, tapis)
2. walls            tilemap layer (murs, plinthes)
3. furniture-back   sprites de meubles derrière les personnages
4. entities         personnages + labels, tri dynamique par y (depth = y)
5. furniture-front  parties de meubles devant (dossiers, comptoirs)
6. effects          émotes, pulses, particules, surbrillance de sélection
```

Les couches 3–6 sont des `Phaser.GameObjects.Layer` ; `entities` utilise
`depth = y` pour l'occlusion naturelle entre personnages et meubles découpés.

---

## 7. Pathfinding et réservation des stations

- **Grille de collision** : construite par salle à partir de la tilemap
  (couche `collision`) + footprints des stations `blocking`.
- **A\*** 4-directions sur cette grille (implémentation maison ~120 lignes,
  pure, testée). Chemin converti en waypoints ; animation `walk-<direction>`
  choisie selon le segment courant.
- **Réservations** (`reservations.ts`) : registre `stationId → seats[]` ;
  `reserve(entityId, stationId)` retourne un siège libre (dx, dy, facing) ou
  `null` si complet → l'adaptateur choisit une autre station du même kind, sinon
  l'agent reste en errance. `release()` à chaque changement de statut non ancré
  ou disparition de l'entité. Corrige le partage de siège actuel.

---

## 8. Caméra, zoom, sélection

- **Pan** : drag souris / touche molette pressée ; bornes = rectangle de la scène.
- **Zoom** : molette, paliers ×0.5 à ×3 avec arrondi de position pour garder le
  rendu pixel-perfect (`roundPixels: true`, `pixelArt: true`).
- **Sélection** : clic entité → contour de surbrillance (couche effects) +
  callback `onEntityClick` (inspecteur existant inchangé) ; clic salle → `onRoomClick` ;
  `focusRoom()` anime la caméra vers une salle (utilisé au changement de vue).
- **Hover** : tint léger + `onEntityHover` (tooltip futur).

---

## 9. Scène galerie

`GalleryScene`, accessible via `?gallery=1` ou `renderer.showGallery()` :

- liste tous les packs chargés, et pour chacun : personnages (cycle automatique
  de toutes leurs animations, nom du clip affiché), stations (back+front
  assemblés), tuiles des thèmes, effets ;
- navigation clavier/clic entre packs, retour au bureau ;
- sert de banc de validation visuelle pour chaque nouveau pack ou asset définitif.

---

## 10. Plan de migration par étapes

| Étape | Contenu | Livrable vérifiable | Risque de régression |
|---|---|---|---|
| **0 — Refactor neutre** | extraire `contracts/`, déplacer le moteur actuel en `legacy/canvas-renderer.ts`, créer `IOfficeRenderer` + `createOfficeRenderer` (mode `canvas` seul), adapter `apps/web` | UI strictement identique | quasi nul |
| **1 — Socle assets** | contrats manifests, `manifest-loader` + validation, `packs.json`, `tools/generate-placeholders.mjs`, `docs/spritesheets.md`, **tests loader** | `npm test` vert ; placeholders générés | nul (rien de branché) |
| **2 — Renderer Phaser MVP** | boot Phaser (import dynamique), tilemap démo, salles par thèmes, stations en sprites, personnages 32×48 idle/walk, 6 couches, adaptateur diff, flag `?renderer=phaser`, fallback auto | les 4 vues rendues en Phaser derrière le flag ; canvas par défaut intact | moyen, confiné au flag |
| **3 — Déplacement** | grille de collision, A*, réservation des stations, walk directionnel, **tests pathfinding/réservations** | agents contournent murs/meubles, un siège par agent | faible |
| **4 — Interaction** | caméra pan/zoom, sélection/surbrillance, hover, émotes en effets de sprites (fin des emojis en mode Phaser), pulse de salle | parité fonctionnelle complète avec le canvas | faible |
| **5 — Galerie + mapper** | `GalleryScene`, `animation-mapper` finalisé, **tests mapping animations** | `?gallery=1` montre tout ; tests verts | nul |
| **6 — Bascule** | Phaser par défaut, `?renderer=canvas` conservé comme fallback temporaire, purge des chemins emoji/rect hors `legacy/` | démo complète validée par toi | contrôlé (retour arrière = flag) |

Chaque étape = un commit dédié, testable indépendamment. La suppression
définitive du renderer legacy est **hors plan** et fera l'objet d'une décision
séparée après une période de stabilité.

---

## 11. Risques et mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| Poids de Phaser (~1,1 Mo min, ~350 Ko gzip) | temps de chargement | import dynamique uniquement en mode phaser ; le fallback canvas ne le charge jamais |
| `setScene` appelé à chaque refresh d'overview | flicker, fuites d'objets Phaser | adaptateur **diff** (objets indexés par id, création/mise à jour/destruction ciblées) |
| Onglet caché : boucle Phaser suspendue | déjà rencontré avec rAF | comportement identique à l'existant, accepté ; re-synchronisation à la reprise |
| Coordonnées legacy (stations ≤ 8×6 tuiles, salles 12×9) | layouts décalés en 32 px fixes | mapping 1:1 tuile legacy → tuile 32 px ; la caméra gère l'ajustement à l'écran (fini l'étirement du tile size) |
| Emojis supprimés avant que les effets soient prêts | perte de lisibilité des statuts | ordre du plan : les effets sprites arrivent (étape 4) avant la bascule (étape 6) |
| Manifest invalide ou image manquante en prod | écran vide | validation stricte au chargement + fallback automatique canvas + `onRendererFallback` |
| Multi-agents > sièges disponibles | agents « sans place » | règle explicite : errance en salle + statut visuel inchangé ; capacité configurable par manifest |
| Écart de version Tiled | tilemap illisible | format figé : Tiled ≥ 1.10, export `.tmj`, propriétés documentées |
| Tests d'un package TS sans bundler | friction CI | modules purs sans import Phaser + vitest en environnement Node |
| Divergence des deux renderers pendant la migration | double maintenance | legacy gelé (bugfix uniquement), parité pilotée par la même suite de scènes de démo |

---

## 12. Fichiers à modifier / créer

### Modifiés (aucun fichier backend)

| Fichier | Nature du changement |
|---|---|
| `packages/pixel-office-engine/package.json` | dépendances `phaser`, `vitest`, script `test` |
| `packages/pixel-office-engine/src/index.ts` | devient barrel d'export + factory (le code actuel part dans `legacy/`) |
| `apps/web/src/main.ts` | factory + flag `?renderer=`, route `?gallery=1`, `emote()` avec ids d'effets |
| `apps/web/src/scene.ts` | remplit `assetPackIds` (via `packs.json`) et `characterId` (via `role_characters`) — champs optionnels |
| `apps/web/tsconfig.json` | includes des nouveaux dossiers |
| `apps/web/package.json` | rien attendu (Phaser vient du package engine) — à confirmer |
| `package.json` (racine) | script `test` agrégé |

### Créés

```text
packages/pixel-office-engine/src/contracts/{scene,assets,renderer}.ts
packages/pixel-office-engine/src/legacy/canvas-renderer.ts        (déplacement)
packages/pixel-office-engine/src/fallback.ts
packages/pixel-office-engine/src/phaser/phaser-renderer.ts
packages/pixel-office-engine/src/phaser/layers.ts
packages/pixel-office-engine/src/phaser/adapter/scene-adapter.ts
packages/pixel-office-engine/src/phaser/assets/{manifest-loader,animation-mapper}.ts
packages/pixel-office-engine/src/phaser/grid/{pathfinding,reservations}.ts
packages/pixel-office-engine/src/phaser/camera/camera-controller.ts
packages/pixel-office-engine/src/phaser/scenes/{OfficeScene,GalleryScene}.ts
packages/pixel-office-engine/tests/{manifest-loader,animation-mapper,pathfinding,reservations}.test.ts
packages/pixel-office-engine/tools/generate-placeholders.mjs
apps/web/public/assets/packs.json
apps/web/public/assets/core/**                                    (manifest + placeholders + demo-office.tmj)
apps/web/public/assets/dept-{software-engineering,data-science,research,game-development}/**
docs/spritesheets.md
docs/pixel-engine-phaser-migration.md                             (ce document)
```

---

## 13. Points ouverts à trancher avant l'étape 2

1. **Zoom pixel-perfect strict** (paliers entiers uniquement) ou zoom libre avec
   léger lissage ? Proposition : paliers 1×/2×/3× + 0.5× pour la vue entreprise.
2. **Labels de noms** : bitmap font pixel dédiée (asset à générer) ou texte DOM
   superposé ? Proposition : bitmap font placeholder dans le pack core.
3. Conserver `emote(glyphe_texte)` en compat pendant la migration, ou basculer
   immédiatement `main.ts` sur des ids d'effets ? Proposition : les deux acceptés
   jusqu'à l'étape 6.
