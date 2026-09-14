# Journal des modifications

Les changements notables d'Agent Company Platform sont consignés dans ce fichier.
Le projet suit le versionnage sémantique ; tant que la version majeure reste à zéro,
les interfaces peuvent encore évoluer entre deux versions mineures.

## [Unreleased]

## [0.7.0] - 2026-09-14

Lot F : automatisations, calendrier IANA, budgets appliqués, saturation du stockage,
alertes in-app et surfaces web/CLI.

### Ajouté

- contrats Python et miroir TypeScript stricts pour les routines, calendriers,
  déclenchements, webhooks, budgets, consommations et alertes ;
- cron à cinq champs interprété dans un fuseau IANA et intervalles fixes de 60 secondes
  à un an ; une heure locale inexistante est omise, une heure ambiguë ne produit que sa
  première occurrence, et la recherche est bornée à quatre ans ;
- modèles persistants `automations`, `automation_runs`,
  `automation_webhook_rotations`, `automation_commands`, `scheduler_leases`,
  `project_budget_policies`, `budget_usage`, `budget_usage_reports`, `alerts` et
  `notification_preferences` ;
- extension de la table existante `workers` avec une portée d'enrôlement globale ou
  limitée à un projet, exclusive et explicite ;
- routes de création, liste, détail, modification, activation, suspension, tir manuel,
  historique et calendrier des routines ; création et tir manuel idempotents ;
- webhook entrant avec secret fourni par le client, 256 bits au minimum, empreinte
  seule en base, rotation idempotente, révocation et déduplication par `event_id` ;
- planificateur worker à bail singleton de 45 secondes, fencing monotone, traitement
  transactionnel, rattrapage `skip`/`run_once`, plafond de concurrence et
  réconciliation des missions terminales ;
- permis de budget avant les phases de planification, exécution et évaluation, ledger
  idempotent et lecture de consommation par mission, jour et fournisseur ;
- alertes durables, dédupliquées par cause, escalade monotone, acquittement et
  préférences personnelles ; canal `in_app` uniquement ;
- détection explicite de la saturation (`507`) et de l'indisponibilité (`503`) du
  stockage local, avec alerte expurgée lorsque le projet et le run sont déjà résolus ;
  réparation atomique d'un blob adressé par contenu devenu incohérent ;
- écran Automatisations à quatre vues — routines, calendrier, alertes, réglages — avec
  assistant de création, historique, webhook, politique et consommation budgétaires ;
- proposition de routine préremplie depuis une mission réussie, techniquement validée
  et acceptée ; elle reste désactivée jusqu'à activation explicite ;
- groupe CLI `acp automations` : `list`, `create`, `show`, `update`, `enable`,
  `disable`, `trigger`, `runs`, `calendar` et `webhook status|rotate|disable`, plus un
  gabarit de mission d'exemple ;
- parcours `scripts/verify_automation_journey.py` démarrant une API réelle sur SQLite
  temporaire : **62/62 étapes réussies** localement, sans Internet ni dépense.

### Modifié

- seuls les workers enrôlés avec un privilège global explicite concourent au
  planificateur ; les workers ordinaires sont limités au projet autorisé côté API et
  le mode `--once` ne démarre pas la boucle ;
- les créations et rotations pouvant avoir abouti malgré une réponse perdue conservent
  leur clé d'idempotence côté web et CLI afin de rejouer la même opération ;
- les budgets conservent la différence entre mesure absente et zéro, utilisent des
  montants décimaux, figent le jour comptable d'un permis jusqu'à son rapport et
  interdisent de changer le fuseau après la première ligne du ledger ;
- l'upgrade SQLite reconstruit transactionnellement tout schéma partiel des dix
  nouvelles tables et de la table `workers` étendue vers la parité du modèle, préserve
  les index/triggers locaux compatibles et refuse de reconstruire un ledger historique
  impossible à compléter honnêtement ;
- l'interface annonce les limites de page et les mesures inconnues, sans inventer un
  total global ou un coût nul ; les compteurs agrégés au-delà de l'entier sûr sont
  plafonnés sur le wire et nommés dans `saturated_metrics`, tandis que le ledger reste
  exact.

### Sécurité

- la `fire_key` déterministe et une contrainte unique SQL arbitrent les tirs
  concurrents ; le verrouillage ne dépend pas d'une vérification en mémoire ;
- le bail et le `fencing_token` sont revérifiés entre les transactions ; un détenteur
  expiré ne peut ni lancer une occurrence ni libérer le bail d'un successeur ;
- trois échecs terminaux consécutifs désactivent la routine et ouvrent une alerte ; une
  routine invalide produit un verdict durable expurgé au lieu d'affamer la file ;
- les mutations de session restent protégées par CSRF et RBAC ; le webhook entrant
  transporte son secret uniquement dans `Authorization: Bearer`, jamais dans l'URL ;
- les préférences filtrent la boîte personnelle sans supprimer ni modifier l'alerte
  canonique du projet ;
- les rapports de budget exigent l'identité worker, un lease actif et le fence de la
  tentative, et les dépassements échouent fermés ; les compteurs et coûts partagent
  les mêmes bornes Python/TypeScript/SQL et le cache agrégé sature sans perdre le
  ledger exact ;
- les relances verrouillent et relisent tentative, policy et compteur avant un CAS ;
  un fence futur inventé est refusé, et les workers historiques sans portée explicite
  restent en quarantaine ;
- une borne de coût worker est arrondie vers le haut avant son transport JSON : une
  conversion binaire ne peut jamais sous-réserver le montant décimal ;
- les corps HTTP sont bornés avant parsing (1 Mio en général, 32 Mio pour les sources
  de skills), avec `Content-Length` décimal strict et limites multipart appliquées
  même en chunk monobloc ; le téléversement de livrable reste authentifié et borné en
  flux, et le webhook entrant est limité à 120 requêtes/minute par adresse TCP et
  processus ;
- les sondes MCP non ciblées exigent un worker global ; une sonde ciblée ne peut être
  réclamée que par le worker nommé, avec transition atomique et TTL relu après verrou
  avant divulgation de ses références de secrets ; expiration, claim et rapport final
  s'arbitrent par transitions conditionnelles.

### Limites connues

- `max_spawned_agents_per_run` est validé, persisté et affiché, mais son application
  attend le point de spawn des exécuteurs du Lot G ;
- aucun navigateur réel, fournisseur payant, Hermes réel ou service externe n'a été
  utilisé pour les preuves de ce lot ;
- le stockage reste local ; aucun adaptateur objet externe n'a été testé ;
- PostgreSQL, Alembic, Railway, sauvegarde et restauration restent au Lot H.

## [0.6.0] - 2026-09-13

Lot E : événements durables, flux authentifié, tests web structurés, livrables privés
et Studio en lecture seule. Vérifié localement le 13 septembre 2026, puis publié par
la PR #5 après observation d'une CI verte ; commit de fusion `b7d8a44`, tag `v0.6.0`.

**Aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été exécuté** :
le reporter est prouvé sur des objets Playwright synthétiques, et l'exécuteur du worker
sur un programme déterministe (`apps/worker/tests/fake_playwright_runner.py`). La
reprise en main humaine du navigateur n'est pas livrée et l'interface le dit.

### Ajouté

- journal d'événements durable : `events` gagne `schema_version`, `conversation_id`,
  `step_id`, `executor`, `emitted_by`, une séquence monotone **par tentative** et un
  compteur monotone **du journal** (`journal_seq`), tous deux alloués dans la
  transaction métier et protégés par un index unique partiel ;
- lecture par curseur `GET /runs/{id}/events` et `GET /projects/{id}/events`
  (`EventPage` avec `next_cursor`, `has_more`, `retention_days`) ;
- flux SSE authentifié servi par l'API métier : `GET /streams/runs/{id}` et
  `GET /streams/projects/{id}`, reprise par `Last-Event-ID` ou `?after_seq=`,
  keep-alive `: ping`, rotation propre annoncée avec son curseur, limite de connexions
  par utilisateur, `Cache-Control: no-store` et `X-Accel-Buffering: no` ;
- stockage de livrables adressé par contenu sur disque (`ACP_ARTIFACT_STORAGE_DIR`,
  clé `<sha256[0:2]>/<sha256>`) derrière une interface `ArtifactStorage`, avec
  téléversement worker `POST /workers/{id}/artifacts/content` (multipart, idempotent
  par sha256, plafond par fichier et quota par tentative appliqués pendant le flux) ;
- routes de bibliothèque `GET /artifacts`, `GET /artifacts/{id}` et
  `GET /artifacts/{id}/content` (support des requêtes `Range`), liens signés
  `POST /artifacts/{id}/link` et révocation `DELETE /artifacts/links/{link_id}` ;
- résultats de tests structurés : tables `test_runs` et `test_cases`, ingestion
  worker `POST /workers/{id}/test-runs`, lectures `GET /runs/{id}/test-run` et
  `GET /test-runs/{id}`, événements `test.run.started`, `test.case.finished` et
  `test.run.finished` ;
- workspace npm `@acp/playwright-reporter` : reporter Playwright **sans dépendance
  runtime** et sans appel réseau, qui écrit un NDJSON local dans `ACP_REPORT_FILE` ;
- capacité worker `web_tests` (désactivée par défaut) et module
  `acp_worker/web_tests.py` : lancement de l'argv configuré par l'opérateur dans la
  clôture d'arrêt du runner, ingestion du NDJSON, téléversement des pièces jointes et
  preuve de mission `web_tests` résumant totaux, code de sortie et identifiant du
  `test_run` ;
- commande de rétention `python -m acp_api.retention` (purge à blanc par défaut,
  `--apply` pour supprimer) ;
- Studio web en lecture seule dans le détail d'une mission et sur
  `/missions?run=<id>&vue=studio`, et onglet « Livrables » de la bibliothèque ;
- commandes CLI `acp runs events`, `acp runs tests`, `acp artifacts list | get | link`
  et `acp open --run <id> --studio` ;
- contrats partagés `StreamEvent`, `EventPage`, `TestRunSummary`, `TestRunDetail`,
  `TestCaseResult`, `TestStep`, `TestTotals`, `ArtifactSummary`, `ArtifactLink`,
  `ArtifactPage`, en Python et en TypeScript.

### Modifié

- le flux temps réel utilisateur est servi par l'**API métier**, pas par
  `apps/event-service` : l'API détient la base, les sessions et le RBAC. Le service
  d'événements reste un relais interne, son ingestion reste authentifiée et son
  WebSocket anonyme reste fermé par défaut ;
- `events_bus.store_event` n'effectue plus de `commit()` implicite quand l'appelant
  fournit sa transaction ; les appelants existants passent `commit=True` et conservent
  le comportement du Lot C ;
- quatre écritures directes d'`EventModel` (`routers/secrets.py`, `routers/workers.py`,
  `mcp/service.py`, `skills/service.py`) passent par `events_bus.store_event` : sans
  numéro, ces lignes sortaient de la page projet et du flux projet ;
- la route web « Bibliothèque » devient un écran à deux onglets, `Skills` (délégué tel
  quel au module du Lot D) et `Livrables` ; aucun élément de navigation n'est ajouté ;
- `GET /artifacts` est servi par le nouveau routeur paginé ; la version « liste
  complète » qui vivait dans `routers/operations.py` est supprimée plutôt que dupliquée ;
- les versions des composants publiables sont synchronisées sur `0.6.0`, y compris le
  nouveau workspace `packages/playwright-reporter` ;
- aucune dépendance runtime n'a été ajoutée : ni en Python, ni côté web, CLI, worker ou
  reporter.

### Sécurité

- un contenu produit par un test est traité comme non fiable : le type servi vient
  d'une allowlist serveur (extension + type déclaré) sans aucun reniflage, `text/html`,
  `image/svg+xml` et les archives — dont la trace Playwright — ne sont **jamais**
  servis en ligne, et toute réponse porte `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox` et
  `Cache-Control: private, no-store` ; le Studio n'utilise ni `iframe`, ni `srcdoc`, ni
  `innerHTML` pour un contenu venu de l'API ;
- les liens de téléchargement sont signés (HMAC-SHA256), bornés à 900 secondes au
  maximum, liés à l'artefact **et** au demandeur, enregistrés par empreinte et
  révocables ; sans `ACP_ARTIFACT_SIGNING_KEYS`, la création répond `503` explicite et
  le téléchargement par session reste possible ; aucun projet ne devient public ;
- le processus de test ne reçoit **aucun credential de la plateforme** : le reporter
  écrit un fichier local et n'appelle jamais le réseau ; messages d'erreur et extraits
  de code sont expurgés (`redact_text` / `redact_data`) avec les valeurs injectées dans
  son environnement avant d'être envoyés à l'API ;
- l'exécution de tests web réutilise `spawn_fenced_process` et
  `terminate_process_tree` : jamais de shell, jamais de spawn direct, et un arrêt
  d'arbre non prouvé interdit tout verdict `passed` ;
- une pièce jointe n'est téléversée que si sa résolution canonique reste sous le
  répertoire de sortie de la tentative ; liens et `..` sont refusés, comptés et
  signalés, et un refus interdit le verdict `passed` ;
- le nom d'origine d'un fichier n'entre jamais dans un chemin de stockage : la clé est
  dérivée du sha256 ;
- le RBAC d'un flux est revérifié **à chaque page**, pas seulement à l'ouverture : une
  révocation de session ou une perte de membership ferme la connexion au plus tard à
  l'interrogation suivante ;
- la rétention ne supprime jamais un événement terminal de tentative, ni un blob encore
  référencé par un autre artefact, ni un artefact cité par une preuve de mission — la
  citation est détectée en balayant toutes les chaînes de `evidence.data`, pas une
  liste de noms de clés ;
- écart assumé et affiché : `ACP_ARTIFACT_PUBLIC_ORIGIN` n'est configurée nulle part.
  Les aperçus signés sont donc servis par l'origine de l'API, et le Studio l'annonce.
  Une instance dans cet état ne doit pas être exposée sur Internet.

### Corrigé

- **la page projet du journal perdait des événements.** Son curseur dérivait de
  `created_at` en microsecondes ; la granularité réelle de l'horloge (environ 1,5 ms
  sur la machine de vérification) rend les égalités courantes, une page pouvait donc
  dépasser la limite annoncée **et** avancer au-delà de lignes jamais rendues, tout en
  annonçant `has_more: false`. Le compteur `journal_seq` donne un ordre total : une
  page ne dépasse plus sa limite, `has_more` est exact, et 300 publications sans pause
  sortent exactement une fois chacune. Les `time.sleep` que les tests inséraient pour
  éviter l'égalité — et qui masquaient le défaut — sont retirés ;
- **le journal et le flux de tentative perdaient tous les événements du Lot C.** Seul
  `publish` allouait une séquence de tentative, alors que les producteurs du Lot C
  écrivent par `store_event` : leurs événements terminaux n'entraient ni dans
  `GET /runs/{id}/events` ni dans le flux SSE ;
- **le reporter pouvait annoncer un faux succès** : ses totaux étaient indexés par une
  identité de test pouvant entrer en collision, et un test réussi écrasait un test
  échoué ;
- une pièce jointe fournie en ligne produisait une forme que le contrat d'ingestion
  refusait, et le worker écartait alors toute la ligne du test — donc son statut et son
  erreur ;
- une troncature tombant au milieu d'une paire de substituts UTF-16 produisait un
  caractère isolé que le contrat rejetait ensuite ;
- **le worker écrivait un second verdict par-dessus celui de l'API** : un rapport qui
  sous-déclarait ses échecs transformait un `failed` serveur en `passed` mission.
  L'adoption du verdict serveur est désormais à sens unique — elle ne peut
  qu'aggraver ;
- **le code de sortie annoncé par le rapport écrasait celui mesuré par le worker** :
  n'importe quelle ligne NDJSON ajoutée par le processus de test obtenait une
  validation technique verte pour un processus réellement sorti en `1` ;
- une seconde ingestion ne portant qu'un `run_end` à code de sortie nul écrasait le
  code non nul déjà enregistré d'une exécution terminale ;
- la rétention effaçait le rapport Playwright cité par une preuve `web_tests` ;
- `payload.attachments[]` n'était jamais lu par le Studio : le panneau « dernière
  capture » affichait toujours « aucune capture », même pour une exécution qui en
  téléversait une ;
- un en-tête `Range` de plus de 4 300 chiffres provoquait un `500` au lieu d'être
  ignoré comme le demande la RFC 9110 ;
- `acp runs tests` annonçait « validation technique : réussie » et sortait `0` pour une
  exécution que la plateforme considère en échec ; `acp open --studio` émettait un
  paramètre que l'interface n'interprète pas ; `acp artifacts list --kind` filtrait le
  mauvais champ ;
- la disponibilité de la capacité `web_tests` lisait la variable d'environnement de
  simulation au lieu du mode d'exécution effectif ;
- un `Content-Disposition` contenant un point-virgule dans le nom de fichier déviait
  l'analyse, et un type déclaré « jamais en ligne » pouvait encore être servi avec une
  disposition d'affichage.

## [0.5.0] - 2026-09-12

Lot D : extensions contrôlées (centre MCP, bibliothèque de skills, coffre de
secrets). Vérifié localement le 12 septembre 2026, puis publié après intégration
continue verte. Aucun serveur MCP tiers, dépôt GitHub réel ni runner distant réel
n'a été contacté : les preuves reposent sur des transports simulés, des programmes
déterministes locaux et un parcours de bout en bout joué contre des services
réellement démarrés sur le bouclage.

### Ajouté

- coffre de secrets chiffrés (Fernet) à références : portées `platform`/`project`,
  `key_id`, rotation de clé sans perte par `ACP_SECRETS_KEYS`, révocation, dernier
  usage, routes `/secrets` et groupe CLI `acp secrets` (valeur uniquement par
  `--value-stdin`) ;
- politique de sortie réseau `outbound.py` : `https` exigé hors allowlist, blocage du
  bouclage, des réseaux privés, de la métadonnée cloud, du CGNAT et des plages IPv6
  équivalentes, contrôle de toutes les adresses résolues, épinglage de l'adresse
  pendant la requête, revalidation des redirections, corps borné et audit de chaque
  usage d'une allowlist privée ;
- centre MCP : catalogue vérifié, serveurs versionnés (empreinte, diff, risques,
  rollback), diagnostic HTTP exécuté par l'API et diagnostic `stdio` soumis à une
  autorisation explicite exécutée par un runner authentifié, rattachements par projet
  limités à un sous-ensemble d'outils, activation, désactivation et révocation
  auditées, import Hermes/Claude/Codex et export avec placeholders
  `${ACP_SECRET_…}` ;
- bibliothèque de skills : import borné depuis un `SKILL.md`, un dossier autorisé, une
  archive ZIP ou un commit GitHub épinglé, révisions avec manifeste SHA-256,
  frontmatter, licence, dépendances et contrôle automatique indicatif, approbation
  d'une portée accrue, rattachements par projet, rollback et révocation ;
- extensions résolues par projet (`GET /projects/{id}/extensions`) et instantané figé
  dans `meta["extensions"]` d'une mission ;
- capacité worker `mcp_stdio_probe` (désactivée par défaut, allowlist d'exécutables
  absolus obligatoire) et sonde MCP stdio sans shell, à environnement minimal, durée
  et sorties bornées ;
- écrans web du centre MCP et de la bibliothèque de skills, groupes CLI `acp mcp`,
  `acp skills` et `acp projects extensions`, lecture des skills et toolsets natifs
  Hermes dans Connexions.

### Modifié

- la route web « Bibliothèque » devient une capacité configurée et « Connexions »
  accueille le centre MCP et le panneau des secrets ; les helpers d'interface partagés
  sont extraits dans `apps/web/src/ui-primitives.ts` sans changement de comportement ;
- le shell web transmet son client HTTP et son jeton CSRF aux modules Connexions et
  Bibliothèque au lieu de les laisser ouvrir leur propre session : un seul jeton CSRF
  est en circulation, réinitialisé à la connexion comme à la déconnexion ;
- les groupes CLI `mcp` et `skills`, jusqu'ici des stubs « non supporté », sont
  raccordés à l'API ; le script de complétion liste `secrets`, `mcp` et `skills`
  (`automations` reste explicitement non supporté) ;
- la création d'une mission fige les extensions résolues du projet dans
  `TaskModel.meta["extensions"]` ; le contrat `MissionSummary` est inchangé ;
- le provider-gateway expose `GET /v1/providers/hermes/native-listing` et l'API métier
  la relaie en lecture seule sur `GET /connections/hermes/native-listing` ;
- `apps/api` dépend désormais de `cryptography>=45,<48` et `pyyaml>=6,<7` ; aucune
  dépendance ajoutée côté web, CLI ou worker ;
- les versions des composants publiables sont synchronisées sur `0.5.0`.

### Corrigé

- arrêt déterministe d'un arbre de processus sous Windows : tout spawn du runner et de
  la sonde MCP `stdio` est créé suspendu, affecté à un Job Object
  `KILL_ON_JOB_CLOSE` sans `BREAKAWAY_OK`, puis repris ; l'affectation est revérifiée
  et un échec devient `spawn_failed` / `job_assignment_failed` au lieu d'une exécution
  hors clôture. L'énumération par filiation ne suffisait pas lorsqu'un **lanceur**
  (`.venv\Scripts\python.exe`, `npx.cmd`, `uvx`) quittait avant son descendant : le
  petit-fils survivait avec les tubes hérités et un run réussi devenait
  `timed_out` / `output_stream_timeout`. Les deux tests concernés
  (`test_normal_parent_exit_cannot_leave_a_background_child`, systématiquement en
  échec, et `test_asyncio_cancellation_terminates_the_process_tree`, intermittent)
  passent désormais, y compris sur trois exécutions consécutives ;
- la sonde `stdio` refuse une page unique d'outils plus grande que sa capacité au lieu
  de la tronquer silencieusement ;
- un diagnostic HTTP ne réclame plus le coffre lorsque la configuration ne référence
  aucun secret ; il échoue explicitement, avec l'action à effectuer, seulement quand un
  secret est référencé et que le coffre est absent ;
- l'aperçu d'import Hermes ne recopie plus la valeur d'un bloc `auth` ou `timeout` dans
  la liste des éléments non supportés, et un document YAML multiple n'est plus
  diagnostiqué comme « étiquette ou ancre ».

### Sécurité

- aucune valeur de secret ne sort du serveur : ni réponse d'API, ni export, ni
  événement, ni URL, ni frontend ; le déchiffrement n'a lieu que pour un diagnostic
  HTTP ou le claim d'un diagnostic `stdio` approuvé par un runner authentifié, avec
  `Cache-Control: no-store` ;
- tout ce qu'un serveur MCP renvoie (`serverInfo`, capacités, outils, `stderr`,
  messages d'erreur) est expurgé des valeurs injectées avant écriture en base, par le
  runner **et** par l'API, selon une règle unique `acp_contracts.redaction` ;
- une valeur littérale ressemblant à un secret, un paquet non épinglé, une commande
  relative ou une URL refusée par la politique sont rejetés à l'enregistrement ;
- un lancement `stdio` exige une autorisation portant l'empreinte exacte de la
  révision ; une révision modifiée l'invalide, une expiration ou un lease perdu
  produisent un état explicite, jamais un succès supposé ;
- une liste d'outils tronquée n'est jamais présentée comme complète : la sonde stdio
  refuse aussi bien une pagination sans fin qu'une page unique surdimensionnée ;
- un rattachement n'est visible que des utilisateurs ayant accès au projet concerné ;
  le compteur global reste affiché sans nommer les projets.

## [0.4.0] - 2026-09-11

### Ajouté

- ressource mission durable et atomique, avec objectif, résultat attendu, critères,
  autonomie, ressources, budget, durée et première tentative ;
- machine d'états explicite, arrêt et relance idempotents par tentative, fencing
  monotone, commentaires, preuves structurées et acceptation utilisateur séparée ;
- backend worker local opt-in à argv configuré, cwd neuf, environnement minimal,
  capture bornée et hachée, timeout et arrêt de l'arbre de processus ;
- CLI `acp` installable pour l'accès, les diagnostics, projets, conversations,
  missions, suivi/arrêt, approbations, artefacts, workers et ouverture d'un run ;
- écran Missions raccordé aux tentatives, preuves, validations, commentaires et
  liens directs de run.

### Modifié

- le claim worker transporte une identité de tentative, un fencing token et un
  snapshot de mission explicitement autorisé ;
- la CI installe et teste le CLI, et le contrôle de version inclut son paquet et son
  module Python ;
- les versions des composants publiables sont synchronisées sur `0.4.0`.

### Sécurité

- aucun argv de mission n'est interprété et aucun shell n'est utilisé par le backend
  local ; une politique d'autonomie non garantie est refusée avant le spawn ;
- perte de lease, arrêt, timeout, fencing obsolète, évaluateur indisponible ou sortie
  mal formée échouent fermés sans perdre la preuve technique déjà produite ;
- les workers simulés ne peuvent pas voler les missions réelles ;
- le mode réel refuse le provider `mock` avant enrôlement ou démarrage et vérifie
  que chaque verdict provient du provider non simulé configuré ;
- `worker doctor` exige l'API, le gateway, l'identité worker et la readiness
  authentifiée du provider configuré avant de rendre un succès ;
- les credentials worker sont liés à l'origine API normalisée, et les clients qui
  portent les Bearers gateway, événements ou Hermes refusent une origine ambiguë ou
  HTTP hors loopback avant toute requête et ignorent les proxies d'environnement ;
- le CLI refuse HTTP hors loopback et ne réutilise pas une session sur une autre
  origine API ; un verrou interprocessus sérialise ses mutations incertaines, qui
  sont reprises avec la même clé d'idempotence.

## [0.3.0] - 2026-09-11

### Ajouté

- bootstrap unique du propriétaire, mots de passe Argon2id et sessions opaques
  révocables/expirables avec cookie `HttpOnly` et protection CSRF ;
- rôles propriétaire, opérateur/membre et lecteur, avec filtrage des ressources par
  projet et espace accessible ;
- onboarding personnel reprenable et création du premier projet ;
- conversations privées ou rattachées à un projet, tours persistés, recherche,
  renommage, archivage, réactivation et export JSON ;
- diagnostic Hermes typé côté serveur et Runs conversationnels asynchrones avec clé
  d'idempotence persistée et reprise par consultation de statut ;
- interfaces web de bootstrap, connexion, onboarding, Connexions et Conversations.

### Modifié

- le navigateur utilise exclusivement la session API et ne transmet plus de Bearer
  métier ni de secret provider ;
- la reprise d'un tour conversationnel conserve son identifiant de requête et sa clé
  d'idempotence après une admission réseau incertaine ;
- les versions des composants publiables sont synchronisées sur `0.3.0`.

### Sécurité

- les routes métier échouent fermées sans session et les mutations exigent un jeton
  CSRF ainsi qu'un rôle suffisant ;
- seul le liveness du provider-gateway reste public, sa surface `/v1/*` exigeant un
  Bearer inter-services distinct ;
- l'ingestion event-service exige son propre Bearer et le WebSocket anonyme est fermé
  par défaut ;
- l'en-tête `X-User-Id` ne peut plus forger une identité utilisateur.

## [0.2.0] - 2026-09-11

### Ajouté

- shell web professionnel français, responsive et accessible, chargé par défaut ;
- client web relié aux projets et à la création/mise en file des missions ;
- adaptateur Hermes Agent `0.21.1` fondé sur l'API Runs officielle ;
- tests de contrats Hermes, de fermeture en cas d'échec et d'identité worker ;
- audit, décisions d'architecture, rapport d'acceptation et captures navigateur ;
- CI GitHub pour Python, TypeScript, Vitest et le build Vite.

### Modifié

- bureau pixel historique conservé derrière un opt-in explicite ;
- configuration locale sans secret ou provider de secours implicite ;
- versions des composants internes synchronisées sur la version produit.
- Vite `8.3.0` et Vitest `5.0.0`, versions corrigées vérifiées par `npm audit`.

### Sécurité

- une simulation ne peut plus produire un succès ;
- les écritures worker exigent une identité et un lease actif ;
- un succès exige une validation technique et une preuve ;
- un lease expiré ne peut pas être réanimé et interrompt durablement le run ;
- les événements terminaux sont produits par l'API métier ;
- CORS n'accepte plus toutes les origines par défaut.

Les tags `v0.2.0` à `v0.6.0` existent ; le Lot E a été fusionné par la PR #5 au commit
`b7d8a44`, après observation d'une CI verte.

[Unreleased]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/5887603...v0.2.0
