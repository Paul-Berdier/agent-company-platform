# Journal des modifications

Les changements notables d'Agent Company Platform sont consignés dans ce fichier.
Le projet suit le versionnage sémantique ; tant que la version majeure reste à zéro,
les interfaces peuvent encore évoluer entre deux versions mineures.

## [Unreleased]

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

[Unreleased]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/5887603...v0.2.0
