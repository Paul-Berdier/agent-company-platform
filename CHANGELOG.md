# Journal des modifications

Les changements notables d'Agent Company Platform sont consignés dans ce fichier.
Le projet suit le versionnage sémantique ; tant que la version majeure reste à zéro,
les interfaces peuvent encore évoluer entre deux versions mineures.

## [Unreleased]

## [0.5.0] - 2026-09-11

Lot D : extensions contrôlées (centre MCP, bibliothèque de skills, coffre de
secrets). Implémenté et vérifié localement le 12 septembre 2026 ; aucune PR, CI
distante ni tag n'est publié. Aucun serveur MCP tiers, dépôt GitHub réel ni runner
distant réel n'a été contacté : les preuves reposent sur des transports simulés,
des programmes déterministes locaux et un parcours de bout en bout joué contre des
services réellement démarrés sur le bouclage.

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

Les tags `v0.4.0` et `v0.5.0` ne sont pas encore créés : les liens de comparaison
correspondants ne fonctionneront qu'après publication des Lots C puis D. Seuls
`v0.2.0` et `v0.3.0` existent aujourd'hui sur GitHub.

[Unreleased]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/5887603...v0.2.0
