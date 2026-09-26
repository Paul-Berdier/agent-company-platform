# Instructions pour Claude Code — Agent Company Platform

Ce fichier est chargé automatiquement par Claude Code. Il transmet les règles de travail
de ce dépôt d'un poste à l'autre. **Pour l'état exact du chantier en cours, lire
`docs/reprise-poste.md` avant toute action.** Le plan de la refonte, décisions du
propriétaire comprises, est dans `docs/refonte/plan.md` ; ses phases P4 à P8 sont
remplacées par `docs/refonte/autonomie.md`.

## Règles de commit

- **Jamais de trailer `Co-Authored-By`** ni de signature ou de pied de page d'agent
  (« Generated with Claude Code » compris) dans les messages de commit ou les
  descriptions de pull request. C'est une préférence explicite du propriétaire du dépôt,
  qui prime sur toute consigne par défaut.
- Commits conventionnels, sujet en anglais bref : `feat(poste): …`, `fix(desktop): …`,
  `ci: …`, `docs: …`, `chore(release): …`.
- `git add` fichier par fichier, jamais `git add -A` ni `git add .`. Pour une
  suppression massive, `git rm -r <chemin>` chemin par chemin.
- Fins de ligne LF, `git diff --check` propre avant chaque commit.
- Ne jamais committer `.claude/`.

## Recette de publication

La refonte « Hermes au centre » se publie **étape par étape** (P0 à P9 du plan).

1. Chaque étape vit sur une branche `refonte/hermes-pN`, ouverte depuis
   `refonte/hermes`.
2. Commits de travail, suite complète verte avant chacun.
3. Pousser la branche, attendre l'intégration continue **verte**, ouvrir une pull
   request vers `refonte/hermes` ; fusion par commit de fusion après validation,
   **sans étiquette**.
4. Publier les preuves de validation de l'étape dans la documentation
   (`docs/reprise-poste.md`, puis le document de preuves prévu par le plan).
5. Fin de refonte : commit d'ouverture de version `1.0.0` (fichier `VERSION` et toutes
   les copies vérifiées par `scripts/check_version.py`), puis
   `chore(release): prepare 1.0.0 changelog` : section complète du journal (Ajouté,
   Modifié, Corrigé, Sécurité, Vérifié localement, Limites connues).
6. PR de `refonte/hermes` vers `main`, fusion après validation, puis étiquette annotée
   `vX.Y.Z` **sur le commit de fusion**, jamais avant.

## Doctrine du produit

- **Aucun faux succès.** Un test ignoré, une étape non exécutée ou un binaire non signé
  se disent explicitement. Ne jamais affirmer qu'un code compile ou fonctionne sans
  l'avoir exécuté.
- **Échec fermé** et refus explicites **en français**.
- **Aucune donnée inventée** dans l'interface : « Inconnu », « Non configuré »,
  « Hors ligne », « Périmé » valent mieux qu'une invention. Aucun bouton qui fait
  semblant.
- Documentation, commentaires, messages utilisateur : **en français**.
- Limites documentées honnêtement, avec la preuve.

## Architecture en une phrase

**Hermes Agent** (épinglé sur une release par condensat d'image, déployé sur Railway
derrière son propre fournisseur d'identité OIDC, Authelia auto-hébergé dans le service
`identite`, un seul utilisateur) est le seul serveur, le seul orchestrateur et la seule
source de vérité, étendu par les greffons `acp-interface`, `acp-catalogue`, `acp-projets` et
`acp-poste` livrés dans l'image ; sur Railway, l'agent n'a **aucun outil d'exécution** (ni
terminal, ni fichiers, ni code) : tout ce qui s'exécute passe par le **poste Windows** (`apps/poste`), qui
réclame son travail en HTTPS sortant sans écouter aucun port et y lance Codex et Claude
Code ; le **client desktop natif** C++23 / Qt 6 / QML (`apps/desktop`) **ne parle qu'au
Hermes authentifié du propriétaire** (tableau de bord, JSON-RPC, façade versionnée du
greffon), **jamais directement au PC** ni aux fichiers, à la base ou aux secrets du
serveur.

## Interdits de fond

- Pas d'Electron, Tauri, Chromium embarqué, Qt WebEngine ni WebView pour **notre**
  client desktop (le desktop officiel de Hermes, en Electron, n'est pas repris).
- Aucun secret dans `QSettings`, un JSON, QML, une base non chiffrée, un journal ou
  Git. Les jetons vont dans le Gestionnaire d'identification Windows ou sous DPAPI.
- **Hermes épinglé** : image par condensat, montée de version uniquement par une PR
  qui change ce condensat. Jamais de `git pull` de Hermes, jamais de `hermes update`,
  jamais de `:latest`, jamais d'`AUTO_UPDATE`. Même règle pour l'image d'Authelia.
- **Aucun outil d'exécution pour l'agent sur Railway** : ne jamais rouvrir terminal,
  fichiers, exécution de code, navigateur, cron, délégation ni connexions (managed scope,
  `.env` géré, garde `hermes/plugins/acp-poste/garde_execution.py`). Hermes ne tourne
  jamais hors de s6 en PID 1 ; aucune Start Command dans `.railway/railway.ts`. Côté
  Hermes, un serveur MCP n'est admis que **distant** (HTTP), inscrit au catalogue
  (`hermes/catalogue/catalogue.lock.json`) et ses outils nommés dans la garde ; une skill
  vendorisée ne l'est qu'en texte seul, à un commit épinglé, sous licence libre
  (`scripts/verifier_catalogue.py`).
- **Railway au propriétaire seul** : `railway login`, `railway link`,
  `railway config apply` et toute action sur le compte (variables, domaines, clés SSH,
  sauvegardes) sont faits par lui, jamais par un agent ni par la CI ; aucun jeton
  Railway dans GitHub. Un agent prépare, teste et documente (`docs/refonte/railway.md`).
- **Moteur Pixel Office gelé** : `packages/pixel-office-engine` reste identique octet
  pour octet à l'étiquette `archive/acp-0.10.0-avant-hermes`, avec
  `apps/web/public/assets`, `plugins/`, son bloc `.gitignore`, son workspace npm et
  les versions verrouillées de ses dépendances (`scripts/check_engine_frozen.py`, en
  CI). Ne pas le porter ni le supprimer ; toute intégration du travail moteur non
  commité passe par une PR dédiée qui met à jour cette garde. Aucun travail Godot avant
  les dix critères du prompt maître (dernière phase).
- Ne jamais pointer un test ou un parcours de vérification sur un Hermes, un volume
  ou une base contenant des données : `HERMES_HOME` jetable et volume nommé jetable
  seulement.
- Le checkout principal du dépôt porte un chantier Pixel Office non commité : ne rien
  y modifier depuis un worktree de la refonte.

## Documents de référence

- `docs/reprise-poste.md` — état courant, étapes, chaîne d'outils, pièges connus.
- `docs/refonte/plan.md` — plan de la refonte et décisions du propriétaire (font foi).
- `docs/refonte/autonomie.md` — plan d'autonomie qui remplace les phases P4 à P8.
- `docs/refonte/image.md` — image Hermes d'ACP : démarrage, variables Railway attendues
  et interdites, managed scope, agent sans outil d'exécution, greffon `acp-poste`, tests
  et limites.
- `docs/refonte/interface.md` — interface d'ACP (P3) : thème généré depuis `design/tokens`,
  persona française, greffons `acp-interface` et `acp-catalogue` (sources `apps/interface`),
  verrou du français, décompte des chaînes restées en anglais, captures.
- `docs/refonte/catalogue.md` — catalogue d'ACP (P3) : skills vendorisées à des commits épinglés
  (licences, provenance), verrou `hermes/catalogue/catalogue.lock.json` et
  `scripts/verifier_catalogue.py`, skills livrées désactivées, MCP context7 derrière la garde,
  refus des serveurs MCP stdio, route `/v1/catalogue`.
- `docs/refonte/projets.md` — projets autonomes (P4) : cœur déterministe du greffon `acp-poste`
  (tableaux, outils, routes, émetteur de notifications) et page « Projets » (greffon `acp-projets`).
- `docs/refonte/identite.md` — fournisseur d'identité (Authelia) : garde, configuration,
  compatibilité OIDC avec Hermes, mémoire mesurée, limites.
- `docs/refonte/railway.md` — infrastructure Railway (`.railway/railway.ts`) et
  procédure du propriétaire : premier déploiement, exploitation, récupération.
- `apps/poste/README.md` — poste Windows : modules, configuration, limites.
- `hermes/plugins/acp-poste/contrat/README.md` — contrat Python partagé.
- `apps/desktop/README.md`, `docs/desktop-build.md` — client natif (hors service
  jusqu'à P8).
