# Templates de salles

Une salle n'est pas une image : c'est un **template JSON versionné** fourni par
un module, assemblé à partir d'assets modulaires (thème + stations par `kind`).

## Emplacement et schéma

`plugins/<module>/rooms/<id>.json` — validé par `acp_agent_sdk.RoomTemplate` :

```jsonc
{
  "id": "software-office-small-v1",
  "schema_version": "1.0",
  "department_type": "software-engineering",
  "theme": "dev-floor",            // thème d'un pack d'assets
  "width": 12, "height": 9,        // tuiles 32 px
  "capacity": 12,                  // places de travail (sélection)
  "doors": [{ "x": 6, "y": 9 }],   // y = height → entrée basse ; y = 0 → mur haut
  "windows": [2, 5, 9],            // offsets x sur le mur haut
  "stations": [ { "id": "dev-desk-1", "kind": "desk", "x": 1, "y": 3 } ],
  "upgrade_to": "software-office-large-v1"  // croissance (phase campus)
}
```

## Sélection par capacité

`GET /departments/{id}/office-config?capacity=N` retourne **le plus petit
template du secteur couvrant N** places, sinon le plus grand disponible ; sans
template, repli sur les stations historiques du module. Le front demande la
capacité = effectif du secteur.

Variantes : plusieurs fichiers du même `department_type` avec des capacités
croissantes (`small-v1`, `large-v1`, ...). `upgrade_to` documente la chaîne.

## Templates livrés

| Module | Template | Capacité | Thème |
|---|---|---|---|
| software-development | software-office-small-v1 → large-v1 | 12 → 18 | dev-floor |
| data-science | data-lab-v1 | 8 | data-lab |
| research | library-v1 | 8 | library |
| game-development | game-studio-v1 | 8 | game-studio |

## Workflow Tiled (recommandé pour dessiner les salles)

1. Ouvrir Tiled ≥ 1.10, carte orthogonale 32×32, taille = dimensions de la salle.
2. Propriétés de carte : `id`, `department_type`, `theme`, `capacity`,
   `upgrade_to` (optionnel).
3. Calques d'objets : `stations` (le **nom** de l'objet = kind : desk,
   whiteboard, coffee-machine…), `doors`, `windows`.
4. Exporter en JSON (`.tmj`) puis convertir :

```powershell
node packages/pixel-office-engine/tools/tiled-to-template.mjs salle.tmj `
  plugins/software-development/rooms/salle.json
```

5. Vérifier hors navigateur :

```powershell
node packages/pixel-office-engine/tools/room-preview.mjs software-engineering out.png
```

6. Redémarrer l'API (les templates se chargent au démarrage).

Un template invalide est ignoré au chargement : il ne casse jamais la
plateforme. Pas d'éditeur navigateur prévu avant longtemps — Tiled est l'outil.
