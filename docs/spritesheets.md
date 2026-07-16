# Format des spritesheets et des packs d'assets

Ce document décrit précisément ce qu'un graphiste (ou un générateur) doit livrer
pour remplacer les placeholders. Référence des types : `packages/pixel-office-engine/src/contracts/assets.ts`.

## Conventions générales

| Règle | Valeur |
|---|---|
| Grille | tuile **32×32 px** |
| Personnages | frames **32×48 px** (1 tuile de large, 1,5 de haut) |
| Format d'image | PNG, fond transparent, **aucun anti-aliasing** |
| Échelle | 1:1 (le zoom est géré par la caméra, jamais par les assets) |
| Marges atlas | 0 px de margin et de spacing |
| Nommage des frames | `"<id>/<animation>/<index>"` (ex. `worker-a/walk-down/2`) |

## Atlas (personnages, meubles, effets)

Un atlas = un PNG + un JSON **TexturePacker "JSON hash"** :

```json
{
  "frames": {
    "worker-a/walk-down/0": {
      "frame": { "x": 0, "y": 0, "w": 32, "h": 48 },
      "rotated": false, "trimmed": false,
      "sourceSize": { "w": 32, "h": 48 },
      "spriteSourceSize": { "x": 0, "y": 0, "w": 32, "h": 48 }
    }
  },
  "meta": { "image": "characters-core.png", "size": { "w": 256, "h": 144 }, "scale": "1" }
}
```

`rotated` et `trimmed` doivent rester `false` (non supportés par le moteur).

## Personnages (32×48)

### Animations attendues

| Clip | Frames | frameRate conseillé | Obligatoire |
|---|---|---|---|
| `idle-down` | 2–4 | 3 | **oui** (repli universel) |
| `walk-down` / `walk-up` / `walk-left` / `walk-right` | 4–6 | 8 | oui pour le déplacement |
| `type` | 4 | 6 | recommandé |
| `think` | 2 | 2 | recommandé |
| `sit` | 2 | 2 | recommandé |
| autres (métier : `read`, `draw`, `chart`…) | libre | libre | non — mappés par `animation_aliases` |

Un clip manquant est résolu par `animation_aliases`, puis par `idle-down`.
**`idle-down` est le seul clip strictement obligatoire.**

### Pivot

Le pivot est déclaré dans le manifest, en coordonnées normalisées [0,1] :
`{ "x": 0.5, "y": 0.9 }` = ancre au centre-pieds (48 × 0.9 ≈ 43 px). Le moteur
positionne ce point sur la tuile occupée — dessinez les pieds vers y≈42–44.

### Déclaration dans le manifest

```json
{
  "id": "dev-a",
  "atlas": "characters-dev",
  "size": { "w": 32, "h": 48 },
  "pivot": { "x": 0.5, "y": 0.9 },
  "animations": {
    "walk-down": { "frames": "dev-a/walk-down/{0..3}", "frameRate": 8, "repeat": -1 }
  }
}
```

`frames` accepte le motif `{a..b}` (bornes incluses) ou un nom de frame unique.
`repeat` : `-1` = boucle, `0` = une seule fois.

## Meubles (stations)

- Découpe en deux frames : **`back`** (derrière les personnages — plateau,
  dossier de meuble) et **`front`** optionnelle (devant — bord avant d'un
  bureau, comptoir). Le moteur place `back` sous la couche entités et `front`
  au-dessus.
- Taille = footprint × 32 px (ex. bureau 2×1 tuiles → back 64×32).
  La frame `front` peut être plus petite (bande basse).
- `pivot` en coordonnées normalisées de la frame ; `{x:0, y:0}` = la frame est
  posée telle quelle sur l'origine tuile de la station.
- `seats` : positions assises en offsets de tuiles depuis l'origine de la
  station + direction du regard. `blocking: true` = participe à la collision.

```json
{
  "kind": "desk", "id": "desk-dev", "atlas": "furniture-dev",
  "frames": { "back": "desk/back", "front": "desk/front" },
  "footprint": { "w": 2, "h": 1 }, "pivot": { "x": 0, "y": 0 },
  "seats": [{ "dx": 1, "dy": 1, "facing": "up" }], "blocking": true
}
```

Le champ `kind` fait le lien avec les stations déclarées par les **plugins
backend** (desk, whiteboard, server-rack…) : aucun code moteur à modifier pour
un nouveau kind, il suffit d'une entrée de manifest.

## Tilesets et thèmes

- PNG en bande horizontale ou grille, tuiles 32×32, `margin: 0`, `spacing: 0`,
  `columns` déclaré dans le manifest.
- Un **thème** référence son tileset et des index de tuiles (0-basés) :
  `floorTiles` (alternées en damier), `wallTiles` (rangée haute des salles),
  plus `accentColor` (surbrillances, badges).

## Tilemaps (Tiled)

- Tiled **≥ 1.10**, export **JSON** (`.tmj`), orientation orthogonale,
  tuiles 32×32.
- Couches reconnues : `floor`, `walls`, `collision` (toute tuile non vide de
  `collision` bloque le pathfinding).
- Le chemin d'image du tileset est résolu relativement au fichier `.tmj`
  dans le dossier du pack.

## Effets (émotes)

Frames libres (16×16 conseillé), affichées au-dessus de la tête. Ids réservés
utilisés par l'application : `task-progress`, `task-complete`, `task-failed`,
`room-pulse`.

## Packs et héritage

```text
apps/web/public/assets/<pack>/
├── manifest.json
├── atlases/*.png + *.json
├── tilesets/*.png
└── tilemaps/*.tmj
```

- `packs.json` (à la racine des assets) déclare les packs et le mapping
  `department_type → pack` : c'est là qu'un nouveau département branche ses
  assets, jamais dans le code.
- `"extends": "core"` : le pack hérite de tout ; ses définitions **écrasent**
  par `id` (personnages, thèmes, effets) ou par `kind` (stations).
- Le pack `core` doit toujours fournir : un personnage par défaut avec
  `idle-down`, une station `desk`, un thème `default` et les 4 effets réservés.

## Régénérer les placeholders

```bash
npm run generate-placeholders -w @acp/pixel-office-engine
```

Le script `tools/generate-placeholders.mjs` réécrit PNG, atlas JSON, tilemap de
démo et manifests — utile comme référence exécutable du format.
