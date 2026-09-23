# Images

**Ce dossier est vide, et c'est un fait, pas un oubli.**

La fondation n'affiche aucune illustration. Deux raisons, toutes deux structurelles :

1. la direction artistique du produit est « QUIET OPERATIONS » : l'interface est neutre,
   sans décor, et les seules couleurs sont l'accentuation et les neuf états ;
2. les ressources graphiques du bureau pixel sont **non redistribuables** — `.gitignore`
   exclut `apps/web/public/assets/licensed/` et
   `packages/pixel-office-engine/assets/licensed/`, et `git ls-files` n'y trouve aucun
   fichier. **Un binaire qui les embarquerait serait une redistribution.** Aucune d'elles
   ne doit jamais atterrir ici.
