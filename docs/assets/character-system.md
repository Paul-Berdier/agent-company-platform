# Système de personnages

## Deux sources, un seul format

| Source | Contenu | Clips |
|---|---|---|
| **Legacy** (Modern Interiors, feuilles par animation) | 10 personnages nommés (Adam, Amelia, les « Conference »…) | idle/walk 4 dir, sit (face), read, phone |
| **Générées** (Character Generator, couches bakées à l'import) | 12 variantes composées corps × yeux × tenue × coiffure | idle/walk 4 dir, **sit-left/right**, sit, read, phone, **error** (flash rouge) |

Les deux sont importées dans le même pack `limezu-characters` et exposées au
moteur sous le même contrat (`CharacterDef`) — le moteur ne fait aucune
différence.

## Variantes générées

Déclarées dans `limezu-mapping.json` → `packs.limezu-characters.generated` :

```jsonc
{ "id": "dev-1", "body": 1, "eyes": 1, "outfit": [1, 1], "hair": [1, 1] }
```

- `body` 1..9 (teintes de peau), `eyes` 1..7, `outfit` [famille 1..33, couleur],
  `hair` [style, couleur] — repli automatique vers la couleur 01 si la variante
  n'existe pas ;
- l'import superpose les couches dans l'ordre corps → yeux → tenue → coiffure
  (ordre officiel LimeZu) et découpe les clips depuis la méga-feuille
  (grille 32×64, régions déclarées dans `generated.clips`) ;
- ajouter une variante = une ligne de JSON + ré-import, aucun code.

## Apparence stable par agent

`resolveCharacter` choisit dans le pool du rôle (`role_characters`) par un
hash **stable de l'id de l'agent** : le même agent garde la même apparence
entre les sessions et les vues.

## Assise directionnelle

Les sièges des stations portent un `facing`. `resolveSeatedClip` :

```text
statut → animation → clip de base (famille sit ?)
  → tente sit-<facing> (clip direct ou alias sit-up→sit-left...)
  → sinon garde le clip de base (personnages legacy sans variantes)
```

## Correspondance statut → animation

`status_mapping` (plugins backend) → `animation_aliases` (packs). Alias
actuels du pack personnages : `type/chart→sit`, `write→read`,
`think/talk/play/point→phone`, `coffee/celebrate→idle-down`, `away/draw→sit`,
`sit-up→sit-left`, `sit-down→sit-right`. L'animation `error` est disponible
pour les futurs statuts/effets d'échec.
