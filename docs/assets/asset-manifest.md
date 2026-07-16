# Manifests d'assets — référence

Format complet : [`contracts/assets.ts`](../../packages/pixel-office-engine/src/contracts/assets.ts).
Guide graphiste (spritesheets, pivots, tailles) : [spritesheets.md](../spritesheets.md).

## Structure d'un pack

```text
apps/web/public/assets/<dossier>/
├── manifest.json        # déclaration validée au chargement
├── atlases/*.png|json   # TexturePacker JSON hash
├── tilesets/*.png       # tuiles 32×32
└── tilemaps/*.tmj       # Tiled JSON (optionnel)
```

## packs.json

```jsonc
{
  "packs": { "core": "core", "dept-software-engineering": "dept-software-engineering" },
  "optional_packs": {                      // packs sous licence, absents ⇒ ignorés
    "limezu-characters": "licensed/limezu/characters"
  },
  "department_packs": { "software-engineering": "dept-software-engineering", "*": "core" }
}
```

Ordre de fusion : `core` → packs requis → packs facultatifs. Le dernier gagne
par `id` (personnages, thèmes, effets), par `kind` (stations) et par clé
(`role_characters`, `animation_aliases`). C'est ainsi que `limezu-characters`
remplace les personnages placeholders sans changement de code.

## Champs notables

| Champ | Rôle |
|---|---|
| `manifest_version` | `"1.0"` — vérifié strictement |
| `extends` | héritage d'un pack parent |
| `provenance` | source, licence, crédit, date d'import (obligatoire pour les packs sous licence) |
| `grid.character` | `32×48` (placeholders) ou `32×64` (LimeZu) |
| `characters[].animations` | motifs `{a..b}`, clips `idle-down` obligatoire |
| `role_characters` | rôle métier → personnages candidats ; `"*"` = défaut |
| `animation_aliases` | nom d'animation métier → clip disponible |
| `stations[]` | par `kind`, frames back/front, footprint, sièges |
| `themes[]` | tuiles sol/mur (+ `pathTiles` pour les campus) |

## Identifiants logiques

Le moteur ne dépend jamais des noms de fichiers fournisseurs. Les frames
importées reçoivent des ids stables générés par le pipeline :

```text
office.single.modern-office-singles-42
exterior.me-singles-camping-tree-1
ui.sheet.modern-ui-style-1
limezu-adam/walk-down/3
```

La curation sémantique (`office.desk.basic` → frame précise) se fait dans les
manifests/stations au moment où un asset est réellement branché (Phase 3).
