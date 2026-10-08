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

**Fin de la refonte « Hermes au centre » (en cours, étape P9).** Les étapes P0 à P8 ont été publiées une à une
vers `refonte/hermes` (recette d'alors : `docs/refonte/historique.md`, partie D). Pour finir :

1. Les branches de P9 (`refonte/hermes-p9*`) suivent la même voie : commits de travail, suite complète verte
   avant chacun, CI verte, PR vers `refonte/hermes`, fusion par commit de fusion, **sans étiquette** ; preuves de
   l'étape publiées dans la documentation.
2. Une fois P9 prouvée : commit d'ouverture `chore(release): open 1.0.0` (fichier `VERSION` et toutes les copies
   vérifiées par `scripts/check_version.py`, fichier par fichier), puis `chore(release): prepare 1.0.0 changelog`
   (section du journal datée, déjà préparée dans `CHANGELOG.md`).
3. PR de `refonte/hermes` vers `main` ; fusion par commit de fusion **après l'accord explicite du propriétaire**,
   puis étiquette annotée `v1.0.0` **sur le commit de fusion**, jamais avant ; preuves publiées dans
   `docs/refonte/preuves-1.0.0.md` par une PR de documentation seule.

**Après 1.0.0, pour chaque lot :**

1. Branche ouverte depuis `main` ; commit d'ouverture de version (fichier `VERSION` et
   toutes les copies vérifiées par `scripts/check_version.py`).
2. Commits de travail, suite complète verte avant chacun.
3. `chore(release): prepare X changelog` : section complète du journal (Ajouté, Modifié,
   Corrigé, Sécurité, Vérifié localement, Limites connues).
4. Pousser la branche, attendre l'intégration continue **verte**, ouvrir la pull request
   vers `main`.
5. Fusionner par commit de fusion seulement après validation, puis poser l'étiquette
   annotée `vX.Y.Z` **sur le commit de fusion**, jamais avant.
6. Publier les preuves de validation dans la documentation.

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
source de vérité, étendu par le greffon serveur `acp-poste` (projets, questions, routage des modèles, quotas,
notifications, flux d'invalidation, protocole `acp-machine/1`) et les greffons d'interface `acp-interface`,
`acp-catalogue`, `acp-projets`, `acp-poste-vues` et `acp-discussion`, tous livrés dans l'image ; sur Railway,
l'agent n'a **aucun outil d'exécution** (ni terminal, ni fichiers, ni code) : tout ce qui s'exécute passe par
l'**exécutant** (service Railway `executant`, image `executant/`, client `apps/poste` en mode Linux, un UID par
agent ; le **poste Windows** est facultatif), qui réclame son travail en HTTPS sortant sans écouter aucun port, y
lance Codex et Claude Code et ne pousse jamais ; le **client desktop natif** C++23 / Qt 6 / QML (`apps/desktop`)
**ne parle qu'au Hermes authentifié du propriétaire** (tableau de bord, JSON-RPC, façade versionnée du greffon),
**jamais directement au PC** ni aux fichiers, à la base ou aux secrets du serveur.

## Interdits de fond

- Pas d'Electron, Tauri, Chromium embarqué, Qt WebEngine ni WebView pour **notre**
  client desktop (le desktop officiel de Hermes, en Electron, n'est pas repris).
- Aucun secret dans `QSettings`, un JSON, QML, une base non chiffrée, un journal ou
  Git. Les jetons vont dans le Gestionnaire d'identification Windows ou sous DPAPI ; sur
  l'exécutant Railway, en fichiers 0600 de root sur son volume, déposés par `railway ssh`
  (D92), jamais en variable Railway.
- **Hermes épinglé** : image par condensat, montée de version uniquement par une PR
  qui change ce condensat (`scripts/monter_hermes.py`, procédure de `docs/exploitation.md` § 6). Jamais de
  `git pull` de Hermes, jamais de `hermes update`, jamais de `:latest`, jamais d'`AUTO_UPDATE`. Même règle
  pour l'image d'Authelia.
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
  sauvegardes, restaurations) sont faits par lui, jamais par un agent ni par la CI ; aucun jeton
  Railway dans GitHub. Un agent prépare, teste et documente (`docs/refonte/railway.md`).
- Une restauration ou une montée de version suit `docs/exploitation.md` ; jamais une garde désactivée, jamais un
  volume supprimé pour « repartir ».
- **Moteur Pixel Office gelé** : `packages/pixel-office-engine` reste identique octet
  pour octet à l'étiquette `archive/acp-0.10.0-avant-hermes`, avec
  `apps/web/public/assets`, `plugins/`, son bloc `.gitignore`, son workspace npm et
  les versions verrouillées de ses dépendances (`scripts/check_engine_frozen.py`, en
  CI). Ne pas le porter ni le supprimer ; toute intégration du travail moteur non
  commité passe par une PR dédiée qui met à jour cette garde. Aucun travail Godot avant
  les dix critères du prompt maître (dernière phase).
- Ne jamais pointer un test ou un parcours de vérification sur un Hermes, un volume
  ou une base contenant des données, ni sur un volume restauré : `HERMES_HOME` jetable et
  volume nommé jetable seulement.
- Sur le poste de travail, **aucune commande Docker ni Docker Desktop** (souhait du propriétaire, 8 octobre 2026,
  D134) : ce qui demande Docker (images, contrat, navigateur, restauration, montée) se prouve par la CI GitHub.
- Le checkout principal du dépôt porte un chantier Pixel Office non commité : ne rien
  y modifier depuis un worktree de la refonte.

## Documents de référence

- `docs/reprise-poste.md` — état courant, chaîne d'outils, pièges connus.
- `docs/exploitation.md` — manuel du propriétaire : sauvegardes, restauration, montée de version, incidents.
- `docs/refonte/plan.md` — plan de la refonte et décisions du propriétaire (font foi), décisions D1 à D155.
- `docs/refonte/autonomie.md` — plan d'autonomie qui remplace les phases P4 à P8.
- `docs/refonte/historique.md` — historique figé des étapes P0 à P9 (notes de reprise et journal par étape).
- `docs/refonte/preuves-1.0.0.md` — preuves de 1.0.0 (PR, runs, relevés ; en préparation).
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
- `docs/refonte/questions.md` — file Questions, notifications et continuité entre appareils (P7).
- `docs/refonte/identite.md` — fournisseur d'identité (Authelia) : garde, configuration,
  compatibilité OIDC avec Hermes, mémoire mesurée, limites.
- `docs/refonte/railway.md` — infrastructure Railway (`.railway/railway.ts`) et
  procédure du propriétaire : premier déploiement, exploitation, récupération.
- `docs/refonte/executant.md` — exécutant Railway (P6) : image, binaires vérifiés, identités par UID, sonde R0,
  régimes A et B, garde « dépôt privé » (P7), preuves et limites ; gestes du propriétaire dans
  `docs/refonte/railway.md` § 13 et § 14.
- `apps/poste/README.md` — poste Windows et exécutant Linux : modules, configuration, limites.
- `hermes/plugins/acp-poste/contrat/README.md` — contrat Python partagé.
- `apps/desktop/README.md`, `docs/refonte/desktop.md`, `docs/desktop-build.md` — station de travail Qt (P8).
