# Modules métier (plugins)

Un module ajoute un secteur complet sans toucher au cœur. Il est décrit par un
fichier `plugins/<nom>/plugin.json` validé par `acp_agent_sdk.ModuleManifest`.

## Ce qu'un module peut fournir

- **departments** : types de départements avec thème de bureau pixel art ;
- **roles** : rôles d'agents et leurs capacités (aucun rôle n'est codé en dur) ;
- **capabilities** : capacités et providers outils requis ;
- **workflows** : étapes de tâches par type de projet, avec validateurs ;
- **stations** : mobilier pixel art (desk, whiteboard, server-rack, bookshelf...) ;
- **available_animations** et **status_mapping** : statut d'agent → animation ;
- **indicators** : indicateurs affichés par l'interface ;
- **adapters** : intégrations optionnelles (ex. Blender MCP pour le jeu vidéo).

## Exemple minimal

```json
{
  "module": "content-creation",
  "departments": [
    {
      "department_type": "content-creation",
      "name": "Content Studio",
      "office_theme": "default",
      "stations": [
        { "id": "writing-desk", "name": "Writing Desk", "kind": "desk", "x": 3, "y": 3 }
      ],
      "available_animations": ["sit", "write", "think", "coffee"],
      "status_mapping": { "working": "write", "idle": "coffee" },
      "roles": [
        { "id": "writer", "name": "Writer", "capabilities": ["write"] }
      ]
    }
  ]
}
```

Déposez le dossier dans `plugins/`, redémarrez l'API : le module apparaît dans
`GET /modules` et ses bureaux sont disponibles pour les départements qui
référencent son `department_type`.

Un module peut aussi fournir des **templates de salles** (`rooms/*.json`,
sélectionnés par capacité, dessinables dans Tiled) — voir
[assets/room-templates.md](assets/room-templates.md).

## Modules livrés

`core` (intégré au SDK), `software-development`, `data-science`, `research`,
`game-development` (qui accueillera plus tard Blender, Unreal Engine, nanos world,
asset validation, build & cook — le cœur fonctionne sans lui).

## Règles

- Un module cassé ou absent est ignoré : le cœur démarre toujours.
- Le moteur pixel art ne lit que des données ; un nouveau secteur = zéro code moteur.
- Les validateurs et adaptateurs référencés par un workflow sont résolus au moment
  de l'exécution ; s'ils manquent, l'étape est simplement non validée.
