# Campus et croissance de l'entreprise

## Vue campus (Company View)

La vue entreprise est un **campus extérieur** : sol herbe/trottoirs
(Modern Exteriors), allées, arbres/bancs/buissons, et un **bâtiment en façade
par département** — cliquer dessus ouvre l'intérieur (Department View).

- Les façades sont des assets data-driven : le moteur résout
  `facade-<theme>` dans les packs (`facade-dev-floor` → immeuble de bureaux,
  `facade-data-lab` → centrale, `facade-library` → serre,
  `facade-game-studio` → villa ; `facade-default` en repli). Aucun bâtiment
  n'est codé dans le moteur.
- Une salle `facade: true` n'a ni intérieur ni stations ; son lot est bloqué
  (on n'y entre pas à pied) et son enseigne (nom, « N EN LIGNE »,
  « X au travail ») est posée devant l'entrée.
- **Les agents au travail sont dans les bâtiments** (invisibles en vue
  campus, comptés sur l'enseigne) ; les agents inactifs flânent sur le campus.
- Les vues intérieures (workspace/département/projet) gardent le rendu
  complet salles + agents + stations.

## Croissance data-driven

Les niveaux sont déclarés par les modules (`ModuleManifest.growth`, le module
`core` fournit les 5 niveaux du MVP) et calculés par le backend depuis les
**métriques réelles** — jamais depuis une affirmation libre :

`GET /company/level` → niveau courant, métriques (projets actifs, agents,
tâches terminées), débloqués, prochain palier.

| Niveau | Nom | Conditions (min) | Débloque |
|---|---|---|---|
| 1 | Startup Office | — | Réception |
| 2 | Small Company | 2 projets, 4 agents, 3 tâches | Lounge |
| 3 | Multi-Department Office | 3 / 8 / 8 | Meeting Rooms |
| 4 | Corporate Building | 4 / 12 / 25 | Place centrale (fontaine, lampadaires) |
| 5 | Company Campus | 6 / 20 / 60 | Jardins denses |

Effets visuels côté campus : espaces communs affichés seulement une fois
débloqués, densité d'arbres croissante, place centrale au niveau 4. Le HUD
affiche le niveau et le prochain palier dans le bandeau de la vue campus.
Rien n'est pay-to-win : purement symbolique, alimenté par le travail réel
des agents.

## Extensions prévues

- `upgrade_to` des templates de salles : agrandissement des bâtiments avec
  l'effectif (déjà en place pour software small→large).
- Transitions caméra campus → bâtiment → salle → agent (zoom animé).
- Véhicules décoratifs et routes (assets Modern Exteriors disponibles).
