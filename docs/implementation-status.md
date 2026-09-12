# État d'implémentation et reprise

Date d'état : 12 septembre 2026, Europe/Paris
Portée : Lot D (version `0.5.0`) construit sur le Lot C `0.4.0`. Le Lot C est publié
(PR #3 fusionnée par commit de merge, tag annoté `v0.4.0`). Le Lot D est publié par la
PR #4 après intégration continue verte, puis étiqueté `v0.5.0`.

## Résumé

La modernisation complète n'est pas terminée. Le Lot C livre la tranche mission :
ressource durable, tentatives explicites, arrêt et relance contrôlés, preuves,
validation technique, acceptation utilisateur, backend de processus local et CLI
`acp` utilisant la même API que le web.

Le Lot D livre la tranche extensions : coffre de secrets chiffrés à références,
politique de sortie réseau anti-SSRF, centre MCP versionné avec diagnostics HTTP et
`stdio` autorisés, bibliothèque de skills importés et relisibles, rattachements par
projet, révocation de bout en bout, import/export des configurations MCP, écrans web
et groupes CLI `acp secrets | mcp | skills`. Aucun serveur MCP réel, dépôt GitHub réel
ou runner distant réel n'a été contacté : les preuves reposent sur des transports et
programmes déterministes locaux.

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
- commandes d'automatisations explicitement non supportées tant que le Lot F n'est
  pas livré.

## Réalisé et testé dans le Lot D

### Coffre de secrets et sorties réseau

- secrets chiffrés (Fernet) avec `key_id`, rotation de clé sans perte via
  `ACP_SECRETS_KEYS`, portées `platform`/`project`, révocation et `last_used_at` ;
  valeur jamais retournée par une route, un export, un événement ou le frontend ;
- coffre absent : état explicite `configured=false` et `503` sur les routes qui
  chiffrent ou déchiffrent, jamais de repli en clair ;
- politique de sortie appliquée côté serveur : `https` exigé hors allowlist, userinfo
  refusé, toutes les adresses résolues contrôlées (une seule bloquée suffit à
  refuser), adresse épinglée pendant la requête, redirections revalidées, corps borné,
  usage d'une allowlist privée audité.

### Centre MCP

- serveurs versionnés (révision immuable, empreinte, diff, risques), catalogue de
  trois entrées vérifiées sur documentation et jamais exécutées ;
- refus `422` d'une valeur littérale ressemblant à un secret, d'un paquet non épinglé,
  d'une commande relative ou d'une URL refusée par la politique ;
- diagnostic HTTP exécuté par l'API ; diagnostic `stdio` soumis à une autorisation
  explicite portant l'empreinte, exécuté par un runner authentifié doté de la capacité
  `mcp_stdio_probe`, avec lease, invalidation, expiration et refus hors lease ;
- expurgation des contenus renvoyés par le serveur sondé, appliquée par le runner et
  par l'API (`acp_contracts.redaction`) ;
- rattachements par projet limités à un sous-ensemble d'outils découverts, activation
  refusée sans découverte courante, désactivation réversible, révocation irréversible
  avec raison, rollback et historique conservé ;
- import Hermes/Claude/Codex avec aperçu normalisé et secrets masqués, export avec
  placeholders `${ACP_SECRET_…}` et notes de compatibilité partielle.

### Bibliothèque de skills et extensions

- import borné depuis un `SKILL.md` saisi, un dossier explicitement autorisé, une
  archive ZIP ou un commit GitHub épinglé ; traversées, liens et fichiers spéciaux
  refusés ;
- révisions avec manifeste SHA-256, frontmatter, licence, dépendances et contrôle
  automatique indicatif ; contenus affichés comme texte, jamais rendus ;
- approbation obligatoire quand une révision augmente la portée (script, réseau,
  permission) ; rattachement par projet, activation, rollback et révocation ;
- extensions résolues par projet (`GET /projects/{id}/extensions`) et instantané figé
  dans `meta["extensions"]` d'une mission : une révision ultérieure ne change pas une
  mission déjà démarrée ;
- lecture des skills et toolsets natifs Hermes dans Connexions, sans recopie dans le
  registre.

### Clôture d'arrêt du runner (correctif d'un défaut du Lot C)

- sous Windows, tout spawn du runner et de la sonde `stdio` est créé suspendu, affecté
  à un Job Object `KILL_ON_JOB_CLOSE` sans `BREAKAWAY_OK`, vérifié par `IsProcessInJob`
  puis repris : aucune instruction du programme ne s'exécute hors de sa clôture ;
- une affectation impossible devient `spawn_failed` / `job_assignment_failed`, jamais
  une exécution non bornée ;
- `process_tree_stopped` n'est vrai que si le job est vide **et** que la passe Toolhelp
  existante le confirme : la vérification native est conservée, pas remplacée ;
- ce correctif traite un défaut réel du Lot C : avec un lanceur d'environnement
  virtuel, un petit-fils survivait à l'arrêt et transformait un run réussi en
  `timed_out` / `output_stream_timeout` ;
- sur POSIX, le comportement est inchangé (`start_new_session` puis `killpg`).

## Hérité des Lots A et B

- shell moderne français, thèmes, responsive, états vides/erreur/hors ligne et
  pixel office historique désactivé par défaut ;
- bootstrap propriétaire unique, Argon2id, session opaque révocable/expirable,
  cookie `HttpOnly`, CSRF et rôles par projet ;
- onboarding personnel et conversations persistantes ;
- adaptateur Hermes `0.21.1` fondé sur `/health/detailed`, `/v1/capabilities` et
  `/v1/runs`, avec réponses strictes et frontière inter-services ;
- service d'événements protégé en ingestion et WebSocket anonyme fermé par défaut.

## Vérification du Lot D

Les résultats détaillés sont consignés dans
[le rapport d'acceptation](acceptance-report.md). Le Lot D a été vérifié dans le
worktree `lot-d` sous Windows 10 Pro `10.0.19045`, Node.js `v24.19.0` et npm
`11.17.0`. Les suites Python ont été exécutées avec `.venv\Scripts\python.exe`, le
**lanceur d'environnement virtuel Windows** (Python `3.12.0`) ; un interpréteur de
contrôle croisé `.venv312\Scripts\python.exe` (Python `3.12.14`) reste disponible.
Ce choix compte : sous Windows, ce lanceur exécute l'interpréteur réel dans un
processus enfant, la topologie même que le correctif Job Object devait couvrir.

La suite Python compte **1 033 tests réussis et 2 avertissements de dépréciation
connus** (`389` API, `164` worker, `280` CLI, `200` en contrats, event-service et
gateway). Le web compte **149 tests Vitest sur 12 fichiers** et le moteur legacy
**74 tests**. Le typecheck TypeScript, le build Vite et
`scripts/check_version.py` (toutes les versions publiables sur `0.5.0`) réussissent ;
le build n'émet que l'avertissement attendu sur la taille du chunk Phaser.

Le scénario d'acceptation 7 a en outre été rejoué contre des services réellement
démarrés — API métier dans son propre processus et serveur MCP Streamable HTTP sur le
bouclage — avec **24 étapes sur 24 réussies**, dont la preuve que le secret déchiffré
atteint bien le serveur MCP sans jamais être republié. Le script de ce parcours n'est
pas versionné dans le dépôt : il ne rend donc pas le scénario reproductible par un
tiers.

Ces tests prouvent les invariants locaux. Ils ne prouvent pas un serveur MCP tiers, un
dépôt GitHub réel, une instance Hermes, un fournisseur payant, PostgreSQL existant,
une sandbox OS, un E2E navigateur ou un déploiement Railway, ni une CI distante.

## Réalisé, non testé en conditions réelles

- l'appel plan/évaluation passe par le provider-gateway et échoue fermé, mais aucune
  instance Hermes `0.21.1`, clé, modèle, mémoire ou outil réel n'a été utilisé ;
- le backend lance et arrête de vrais processus locaux dans les tests, sans lancer
  d'agent externe ni effectuer d'effet sur un projet utilisateur ;
- le web et le CLI partagent les routes et contrats testés séparément, sans E2E
  navigateur → API → worker → Hermes ;
- la compatibilité locale SQLite est un upgrade ad hoc non versionné qui peut
  reconstruire des tables ; une sauvegarde préalable est requise. La migration d'une
  base PostgreSQL existante n'est pas fournie dans ce lot ;
- l'import d'un skill depuis GitHub, l'import d'archive et les refus de traversée sont
  prouvés sur transport simulé et sources locales : aucun dépôt ni archive tierce
  réelle n'a été téléchargée ;
- la sonde `stdio` est prouvée contre un serveur MCP déterministe écrit pour les tests,
  lancé par `sys.executable` sur la machine de vérification : aucun runner distant
  enrôlé, aucun serveur MCP tiers ;
- les écrans web du centre MCP et de la bibliothèque de skills sont couverts par des
  tests Vitest sur le DOM, pas par un parcours navigateur réel.

## Bloqué

Ces points ne dépendent pas d'un développement supplémentaire mais d'une ressource ou
d'une décision qui manque aujourd'hui.

- **Publication des Lots C et D** : le code est prêt et vérifié, mais aucune PR n'est
  ouverte, aucune CI distante n'a tourné et aucun tag n'existe. C'est une décision, pas
  un travail restant.
- **Passage des scénarios 7 et 8 à « Accepté »** : bloqué par l'absence d'un serveur
  MCP tiers et d'un dépôt GitHub réel autorisés pour la vérification, et par le fait
  que le parcours de bout en bout n'est pas versionné dans le dépôt.
- **Vérification Hermes réelle** : bloquée par l'absence d'instance, de clé et de
  modèle ; toute la lecture native est prouvée sur transport simulé.
- **Vérification PostgreSQL, sauvegarde et restauration** : bloquée par l'absence d'une
  base existante et d'une procédure de migration versionnée.

## Non configuré ou restant

- sandbox OS, utilisateur non privilégié dédié et politique réseau vérifiée : sous
  Windows, le Job Object livré au Lot D borne l'arbre de processus du runner et de la
  sonde `stdio`, mais il n'impose ni quota CPU/mémoire, ni politique réseau ; c'est
  une clôture d'arrêt, pas une isolation ;
- scope cgroup ou unité de service POSIX équivalente au Job Object Windows : sur
  POSIX, l'arrêt repose encore sur `start_new_session` + `killpg`, qu'un descendant
  peut quitter en changeant volontairement de session ;
- l'autorisation d'un lancement `stdio` est un objet propre au centre MCP
  (`mcp_probes.authorization`) : elle n'est **pas** reliée à `ApprovalModel` ni au
  circuit d'approbation des missions, et n'apparaît donc ni dans `/approvals` ni dans
  `acp approvals` ;
- endpoint worker d'approbation d'une action exacte et exécution sensible ;
- le contrôle automatique d'un skill est une heuristique explicitement indicative :
  aucun scan certifiant, aucune signature vérifiée, aucun bac à sable d'analyse ;
- aucune installation automatique côté Hermes : la plateforme **exporte** une
  configuration `mcp_servers` et des placeholders `ACP_SECRET_*` à appliquer
  manuellement ; aucune API HTTP d'Hermes 0.21.1 ne permet d'écrire cette
  configuration ;
- migrations PostgreSQL versionnées, rollback et restauration ;
- flux utilisateur authentifié/rejouable, Playwright, captures, traces et fichiers
  privés ;
- courtier d'appels d'outils MCP pendant une mission : le Lot D livre le registre, la
  découverte, l'autorisation et la résolution des extensions, pas l'appel à
  l'exécution ;
- gestion des clés du coffre par un KMS/HSM et rotation planifiée ; les secrets de
  service (`HERMES_API_KEY`, Bearers inter-services) restent hors coffre ;
- automatisations, budgets agrégés, notifications et calendrier Europe/Paris ;
- médias, image, aperçu 3D et exécuteurs complémentaires ;
- E2E navigateur, Hermes réel opt-in, Railway et observabilité de production.

## Lots

| Lot | Capacité verticale | État |
|---|---|---|
| A | audit, shell moderne, Hermes Runs strict et exécution fail-closed | **Publié : PR #1, tag `v0.2.0`** |
| B | accès propriétaire, RBAC, onboarding et conversation persistante | **Publié : PR #2, tag `v0.3.0`** |
| C | runner réel contrôlé, missions, preuves, validations et CLI | **Publié : PR #3, tag `v0.4.0`** |
| D | MCP/skills versionnés, coffre de secrets, diagnostics et révocation | **Publié : PR #4, tag `v0.5.0` ; aucun serveur MCP tiers contacté** |
| E | Playwright, flux authentifié, traces, captures et livrables | **Non commencé** |
| F | automatisations, calendrier Europe/Paris, budgets et alertes | **Non commencé** |
| G | médias/3D, exécuteurs complémentaires et durcissement | **Non commencé** |
| H | migrations, Railway, sauvegarde-restauration et validation finale | **Non commencé** |

## Reprise : du Lot D au Lot E

Ordre de reprise pour la personne ou l'agent qui prend la suite.

1. **Étendre le parcours de bout en bout** : `scripts/verify_mcp_journey.py` couvre le
   transport `http`. L'étendre au transport `stdio` (runner enrôlé, autorisation, claim,
   résultat) et le raccorder à la CI en opt-in.
2. **Raccorder un serveur MCP tiers** (un `http` public et un `stdio` local) et rejouer
   le parcours hors tests simulés, y compris l'expurgation face à un serveur bavard
   réel et un dépôt GitHub réel pour un skill épinglé.
3. **Construire le courtier d'appels d'outils** à l'exécution d'une mission, sur les
   extensions déjà résolues et figées dans `meta["extensions"]` : c'est la brique qui
   transforme le registre du Lot D en capacité utilisable par un agent.
4. **Décider du sort de l'autorisation `stdio`** : la relier au circuit
   d'approbation des missions (`ApprovalModel`, `/approvals`, `acp approvals`) ou
   assumer durablement deux circuits distincts et le documenter comme tel.
5. **Enchaîner sur le Lot E** (Playwright, flux authentifié, traces, captures et
   livrables) une fois les points 1 et 2 tenus : le Lot E a besoin d'un parcours
   navigateur reproductible, que le Lot D n'a pas produit.
