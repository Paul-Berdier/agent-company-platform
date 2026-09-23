# Icônes

**Ce dossier est vide, et c'est un fait, pas un oubli.**

Le jeu d'icônes du produit **n'est pas choisi**. `design/tokens/semantic-status.json`
le déclare explicitement : `"$iconSet": { "resolved": false }`. Les noms de glyphe portés
par les jetons (`question`, `unplugged`, `link-broken`, `queue`, `activity`, `barrier`,
`cross`, `check`, `warning`, `hand-raised`) sont **sémantiques** ; leur correspondance
vers des ressources réelles sera décidée avec le premier écran métier.

En attendant, l'interface n'affiche **aucune icône** : les contrôles emploient un
caractère ou l'initiale du nom sémantique, et chaque état porte son libellé français et
son repli ASCII. Aucune icône d'emprunt n'est embarquée, parce qu'une icône embarquée est
une redistribution et engage une licence.

Quand le jeu sera décidé, les fichiers déposés ici devront être déclarés dans le
`qt_add_qml_module` correspondant, via `RESOURCES`.
