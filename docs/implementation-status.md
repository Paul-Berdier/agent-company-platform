# État d'implémentation et reprise

Date d'état : 11 septembre 2026, Europe/Paris
Portée : candidat de release local du Lot C `0.4.0`, construit sur le Lot B publié.
La publication GitHub du Lot C — PR, CI distante et tag — n'a pas encore été
effectuée.

## Résumé

La modernisation complète n'est pas terminée. Le Lot C livre la tranche mission :
ressource durable, tentatives explicites, arrêt et relance contrôlés, preuves,
validation technique, acceptation utilisateur, backend de processus local et CLI
`acp` utilisant la même API que le web.

Le backend réel exécute uniquement un exécutable absolu via un argv fixe configuré
par l'opérateur. Il ne prend jamais une commande dans la mission, crée un cwd neuf,
transmet un snapshot borné, filtre l'environnement, borne le temps et les sorties,
et arrête l'arbre de processus lors d'un stop, timeout ou lease perdu. Il reste un
processus avec les droits OS du compte worker : ce n'est pas une sandbox pour du
code non fiable.

Aucune instance Hermes réelle, dépense externe, migration de production ou
déploiement n'a été lancé. Les preuves locales reposent sur des programmes et
transports déterministes de test.

## Réalisé et testé dans le Lot C

### Missions et tentatives

- création atomique d'une mission et de sa première tentative avec objectif,
  résultat attendu, critères, autonomie, ressources, budget et durée ;
- `Idempotency-Key` obligatoire pour créer, arrêter et relancer ; la clé de création
  est liée au principal et à l'empreinte du payload ;
- replay d'un arrêt lié à sa tentative d'origine, sans risque d'arrêter une relance
  ultérieure ;
- états `queued`, `preparing`, `running`, `waiting_approval`, `blocked`, `stopping`,
  `succeeded`, `failed`, `cancelled` et `interrupted` ;
- numéro de tentative et fencing token monotones ; ancien worker refusé lors d'un
  renew, PATCH ou événement ;
- succès accepté seulement avec validation technique `passed` et preuve structurée ;
- décision utilisateur séparée (`pending`, `accepted`, `rejected`), commentaires et
  relance possible après rejet explicite ;
- lecture directe d'une mission par identifiant de run pour les liens profonds ;
- worker simulé exclu des missions réelles.

### Backend worker local

- configuration fail-closed par `ACP_WORKER_RUNNER_ARGV_JSON` et
  `ACP_WORKER_RUN_ROOT` ; exécutable absolu et situé hors de la racine inscriptible ;
- enveloppe `acp.local-process.request.v1` et preuve
  `acp.local-process.evidence.v1` à champs structurés allowlistés ; stdout/stderr
  sont bornés et hachés, mais leur texte non expurgé peut contenir des secrets ;
- création exclusive d'un répertoire par tentative, aucun rejeu implicite d'un cwd
  existant et aucun shell ;
- environnement minimal et allowlisté, stdout/stderr lus en continu, captures
  bornées et SHA-256 de la totalité ;
- deadline de mission, timeout, arrêt explicite, perte de lease et fencing obsolète
  reliés à l'arrêt du groupe/arbre de processus ;
- sortie du parent détectée indépendamment des pipes hérités et succès refusé si le
  nettoyage de l'arbre ne peut pas être confirmé ;
- code de sortie nul insuffisant : l'évaluateur doit répondre explicitement
  `approved: true`, sinon l'état reste non réussi et la preuve technique est gardée ;
- mode non supervisé, listes d'actions non vides, ressources en écriture et provider
  `mock` refusés avant le spawn ; verdict lié au provider réel configuré ;
- `doctor` exige liveness API/gateway, authentification worker et readiness
  authentifiée du provider.

### Web et CLI synchronisés

- écran Missions relié à l'API, avec état d'exécution, validation technique,
  acceptation, critères, preuves, arrêt, relance et commentaires ;
- lien `/missions?run=<id>` qui ouvre la mission et la tentative demandées, y compris
  une tentative historique ;
- clé de création web conservée après un timeout afin qu'un nouvel essai logique ne
  duplique pas la mission ;
- CLI installable : `login`, `logout`, `doctor`, projets, chat, création/suivi/arrêt
  de missions, approbations, artefacts, workers, ouverture web et complétion shell ;
- JSON/NDJSON, codes de sortie stables et `Ctrl+C` sur `runs watch` sans arrêt
  implicite de la mission ;
- configuration CLI atomique, session liée à l'origine API, HTTPS obligatoire hors
  loopback et aucun Cookie/CSRF réutilisé après changement d'origine ;
- commandes MCP, skills et automatisations explicitement non supportées tant que
  leurs lots respectifs ne sont pas livrés.

## Hérité des Lots A et B

- shell moderne français, thèmes, responsive, états vides/erreur/hors ligne et
  pixel office historique désactivé par défaut ;
- bootstrap propriétaire unique, Argon2id, session opaque révocable/expirable,
  cookie `HttpOnly`, CSRF et rôles par projet ;
- onboarding personnel et conversations persistantes ;
- adaptateur Hermes `0.21.1` fondé sur `/health/detailed`, `/v1/capabilities` et
  `/v1/runs`, avec réponses strictes et frontière inter-services ;
- service d'événements protégé en ingestion et WebSocket anonyme fermé par défaut.

## Vérification du candidat de release

Les résultats définitifs sont consignés dans
[le rapport d'acceptation](acceptance-report.md). Le commit de code
`5ff6aa78a232a721ae14353e907baefc548b4ccb`, arbre Git
`e697087938aa7ba0247b39cf00b4a3ed9266fcb7`, a été vérifié dans un worktree
propre sous Windows `10.0.19045` avec Python `3.12.14`, Node.js `v24.19.0` et npm
`11.17.0`.

La suite Python compte **323 tests réussis et 2 avertissements de dépréciation
connus**. Les suites worker et CLI comptent **192 tests réussis** (`122` worker,
`70` CLI), le web **29** et le moteur Pixel Office **74**. Le typecheck
TypeScript, le build Vite, le contrôle des versions et la validation syntaxique
des scripts POSIX réussissent également.

Ces tests prouvent les invariants locaux. Ils ne prouvent pas une instance Hermes,
un fournisseur payant, PostgreSQL existant, une sandbox OS, un E2E navigateur ou un
déploiement Railway, ni une CI distante.

## Réalisé, non testé en conditions réelles

- l'appel plan/évaluation passe par le provider-gateway et échoue fermé, mais aucune
  instance Hermes `0.21.1`, clé, modèle, mémoire ou outil réel n'a été utilisé ;
- le backend lance et arrête de vrais processus locaux dans les tests, sans lancer
  d'agent externe ni effectuer d'effet sur un projet utilisateur ;
- le web et le CLI partagent les routes et contrats testés séparément, sans E2E
  navigateur → API → worker → Hermes ;
- la compatibilité locale SQLite est un upgrade ad hoc non versionné qui peut
  reconstruire des tables ; une sauvegarde préalable est requise. La migration d'une
  base PostgreSQL existante n'est pas fournie dans ce lot.

## Non configuré ou restant

- sandbox OS, utilisateur non privilégié dédié et politique réseau vérifiée ;
- Job Object Windows ou scope cgroup/service POSIX empêchant un programme approuvé
  de détacher volontairement un descendant ;
- endpoint worker d'approbation d'une action exacte et exécution sensible ;
- migrations PostgreSQL versionnées, rollback et restauration ;
- flux utilisateur authentifié/rejouable, Playwright, captures, traces et fichiers
  privés ;
- centre MCP, bibliothèque de skills et coffre de secrets ;
- automatisations, budgets agrégés, notifications et calendrier Europe/Paris ;
- médias, image, aperçu 3D et exécuteurs complémentaires ;
- E2E navigateur, Hermes réel opt-in, Railway et observabilité de production.

## Lots

| Lot | Capacité verticale | État |
|---|---|---|
| A | audit, shell moderne, Hermes Runs strict et exécution fail-closed | **Publié : PR #1, tag `v0.2.0`** |
| B | accès propriétaire, RBAC, onboarding et conversation persistante | **Publié : PR #2, tag `v0.3.0`** |
| C | runner réel contrôlé, missions, preuves, validations et CLI | **Implémenté et vérifié localement ; PR, CI distante et tag non publiés** |
| D | MCP/skills versionnés, installation contrôlée, diagnostics et révocation | **À réaliser ensuite** |
| E | Playwright, flux authentifié, traces, captures et livrables | **Non commencé** |
| F | automatisations, calendrier Europe/Paris, budgets et alertes | **Non commencé** |
| G | médias/3D, exécuteurs complémentaires et durcissement | **Non commencé** |
| H | migrations, Railway, sauvegarde-restauration et validation finale | **Non commencé** |

## Reprise après publication du Lot C

1. Construire le Lot D sur le commit de fonctionnalité du Lot C, sans absorber les
   modifications Pixel/LimeZu locales hors périmètre.
2. Implémenter d'abord les modèles/versionnements MCP et skills, les scopes projet,
   le masquage des secrets et les contrôles SSRF/path/archive.
3. Ajouter les parcours test/activation/révocation et leurs diagnostics avant les
   écrans de catalogue.
4. Publier uniquement après suite propre, PR verte et tag annoté `v0.5.0` sur le
   commit mergé de `main`.
