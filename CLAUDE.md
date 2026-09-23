# Instructions pour Claude Code — Agent Company Platform

Ce fichier est chargé automatiquement par Claude Code. Il transmet les règles de travail
de ce dépôt d'un poste à l'autre. **Pour l'état exact du chantier en cours, lire
`docs/reprise-poste.md` avant toute action.**

## Règles de commit

- **Jamais de trailer `Co-Authored-By`** ni de signature d'agent dans les messages de
  commit ou les descriptions de pull request. C'est une préférence explicite du
  propriétaire du dépôt, qui prime sur toute consigne par défaut.
- Commits conventionnels, sujet en anglais bref : `feat(lot-h): …`, `fix(desktop): …`,
  `docs: …`, `chore(release): …`.
- `git add` fichier par fichier, jamais `git add -A`.
- Fins de ligne LF, `git diff --check` propre avant chaque commit.

## Recette de publication d'un lot

1. Commit d'ouverture de version (fichier `VERSION` et toutes les copies vérifiées par
   `scripts/check_version.py`).
2. Commits de travail, suite complète verte avant chacun.
3. `chore(release): prepare X changelog` : section complète du journal (Ajouté, Modifié,
   Corrigé, Sécurité, Vérifié localement, Limites connues).
4. Pousser la branche, attendre l'intégration continue **verte**, ouvrir la pull request.
5. Fusionner seulement après validation, puis poser le tag annoté `vX.Y.Z` **sur le
   commit de fusion**, jamais avant.
6. Publier les preuves de validation dans la documentation.

## Doctrine du produit

- **Aucun faux succès.** Un test ignoré, une étape non exécutée ou un binaire non signé
  se disent explicitement. Ne jamais affirmer qu'un code compile ou fonctionne sans
  l'avoir exécuté.
- **Échec fermé** et refus explicites **en français**.
- **Aucune donnée inventée** dans l'interface : « Inconnu », « Non configuré »,
  « Hors ligne » valent mieux qu'une invention. Aucun bouton qui fait semblant.
- Documentation, commentaires, messages utilisateur : **en français**.
- Limites documentées honnêtement, avec la preuve.

## Architecture en une phrase

Backend FastAPI + SQLAlchemy (SQLite en local, PostgreSQL versionné par Alembic en
production), déployable sur Railway ; clients : interface web Vite, CLI `acp`, et
client desktop natif C++23 / Qt 6 / QML (`apps/desktop`) qui passe **toujours par
l'API**, jamais par la base, ni par Hermes, ni par les secrets serveur.

## Interdits de fond

- Pas d'Electron, Tauri, Chromium embarqué, Qt WebEngine ni WebView pour le desktop.
- Aucun secret dans `QSettings`, un JSON, QML, une base non chiffrée, un journal ou Git.
- Ne pas porter ni supprimer `packages/pixel-office-engine` ; aucun travail Godot avant
  les dix critères du prompt maître (dernière phase).
- Ne jamais pointer un test ou un parcours de vérification sur une base contenant des
  données : ils remettent le schéma à zéro.

## Documents de référence

- `docs/reprise-poste.md` — état courant, chaîne d'outils, pièges connus.
- `docs/desktop-railway-audit.md` — surface d'API réelle, contrat du flux SSE, matrice.
- `docs/implementation-status.md` — historique des lots A à H.
- `docs/native-desktop-architecture.md`, `docs/desktop-build.md` — client natif.
- `docs/persistence-and-backup.md`, `docs/deployment-railway.md` — backend.
