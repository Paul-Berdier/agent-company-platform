# Polices

**Ce dossier est vide, et c'est un fait, pas un oubli.**

`design/tokens/typography.json` le dit lui-même : « Aucune police n'est téléchargée : les
piles listées reposent sur ce qui est installé. » Les deux piles employées sont

- interface : `Inter`, `Inter Variable`, `Segoe UI Variable Text`, `Segoe UI`,
  `SF Pro Text`, `Noto Sans`, `DejaVu Sans` ;
- chasse fixe : `Cascadia Code`, `Cascadia Mono`, `JetBrains Mono`, `SF Mono`,
  `SFMono-Regular`, `Consolas`, `DejaVu Sans Mono`.

Elles sont fournies à `font.families`, qui essaie chaque nom dans l'ordre. Si `Inter` est
absente du poste, le rendu bascule sur la police système **sans réglage** — et **cela n'a
jamais été observé**, aucun écran natif n'ayant été rendu.

Embarquer une police est une redistribution : elle engage une licence, et aucune n'a été
choisie. Tant que ce choix n'est pas fait, ce dossier reste vide.
