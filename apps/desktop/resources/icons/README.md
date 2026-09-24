# Pictogrammes du desktop

La navigation utilise le composant natif `Acp.Controls/AcpIcon.qml`. Ses tracés
Canvas originaux (grille de 24 unités) sont embarqués avec le code QML : aucune
police d'icônes, ressource distante ou bibliothèque tierce n'est redistribuée.
Le composant expose `name`, `color` et `size` ; les boutons conservent un libellé
accessible distinct du dessin.

Le jeu couvre conversation, dossier, ajout, recherche, chevrons, fermeture,
envoi, code, validation, menu, activité, archive, grille et réglages. Les boutons
ACP l'emploient via `iconName`. Les couleurs viennent des jetons du thème.

Le champ `$iconSet.resolved` de `design/tokens/semantic-status.json` concerne
encore la correspondance complète des **états métier**. Il ne décrit pas le jeu
de navigation. Les statuts conservent un libellé français ; ce premier jeu ne
prétend pas remplacer l'ensemble des glyphes sémantiques prévus.
