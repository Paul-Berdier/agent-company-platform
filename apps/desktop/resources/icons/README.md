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

## Emblème ACP

`acp-atelier.svg` contient le noyau carré et les ailes en pixels de l'identité ACP,
avec un centre transparent et une teinte lavande `#9B8BC6`. C'est une géométrie
originale, sans ressource tierce. `acp-atelier.png` est son export transparent
256 × 256 et `acp-atelier.ico` contient les tailles 16, 24, 32, 48, 64, 128 et 256.

Pour les régénérer sans dépendance externe sur Windows :

```powershell
./apps/desktop/tools/generate-atelier-brand.ps1
```

Le script définit une grille entière et n'applique aucun lissage. Ces trois
fichiers peuvent être versionnés et embarqués dans l'exécutable.
