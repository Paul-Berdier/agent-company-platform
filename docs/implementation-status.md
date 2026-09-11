# État d'implémentation et reprise

Date d'état : 11 septembre 2026, Europe/Paris
Portée : release candidate locale du Lot B `0.3.0`, construite sur la branche du Lot A

## Résumé

La modernisation complète n'est pas terminée. Le Lot B livre la première tranche
personnelle sécurisée : bootstrap propriétaire, session web révocable, filtrage par
projet, onboarding, diagnostic Hermes côté serveur et conversation web persistante.
Un rechargement ou une nouvelle consultation reprend le même tour par `GET` et une
nouvelle soumission incertaine conserve sa clé d'idempotence.

Cette tranche n'a pas été reliée à une instance Hermes réellement lancée. Les tests
du diagnostic et des Runs utilisent des doubles ou `httpx.MockTransport`. Il n'y a
toujours ni runner réel, ni CLI `acp`, ni streaming utilisateur authentifié, ni
migration versionnée. Le moteur pixel historique reste une option legacy désactivée
par défaut ; le chantier pixel local préexistant est préservé et hors du Lot B.

## Réalisé dans le code et couvert par des tests ciblés

### Accès propriétaire et session

- bootstrap unique conditionné par `ACP_BOOTSTRAP_TOKEN`, sans mot de passe ou compte
  fourni par défaut et sans inscription publique ;
- normalisation de l'identifiant et mot de passe haché avec Argon2id ;
- jeton de session opaque dont seul le SHA-256 est persisté, expiration et révocation
  serveur, cookie `HttpOnly` et `SameSite=Strict` ;
- restauration de session avec rotation du jeton CSRF ; le frontend le conserve en
  mémoire et l'envoie sur les mutations ;
- réponses d'authentification `no-store`, erreurs de connexion génériques et refus
  d'une identité forgée dans `X-User-Id` ;
- tests API ciblant bootstrap, unicité, stockage des seuls hachages, connexion,
  expiration, rotation CSRF, déconnexion et révocation ; tests TypeScript du client
  d'authentification et des en-têtes.

### Autorisation, espace personnel et frontières de service

- les routes utilisateur utilisent la session serveur ; les listes de workspaces,
  projets, tâches, locks, approbations et artefacts sont filtrées par les scopes
  accessibles ; les mutations exigent un rôle suffisant ;
- le propriétaire global conserve l'administration, un membre/opérateur peut
  travailler dans ses projets et un lecteur ne peut pas écrire ;
- état d'onboarding authentifié et création d'un projet dans un workspace personnel
  créé au besoin, avec memberships explicites ;
- seul `/health` reste public sur le provider-gateway ; toutes ses autres routes
  exigent `ACP_GATEWAY_SERVICE_TOKEN`. L'API et le worker utilisent ce jeton, jamais
  le navigateur ;
- ingestion du service d'événements protégée par `ACP_EVENT_SERVICE_TOKEN` ; le
  WebSocket anonyme historique est fermé par défaut et ne peut être réactivé que par
  un drapeau explicitement dangereux de développement ;
- tests ciblés de refus/acceptation Bearer, fermeture sans configuration, isolation
  lecteur/projet et WebSocket anonyme fermé.

### Hermes, Connexions et conversations

- diagnostic Hermes typé : configuration, readiness, version attendue/détectée,
  modèle, latence et cause exploitable, sans champ secret ;
- diagnostic exposé au web uniquement via l'API authentifiée ; le navigateur ne
  parle pas directement au provider-gateway et ne reçoit pas `HERMES_API_KEY` ;
- admission asynchrone d'un Run conversationnel avec `Idempotency-Key` imposée par
  l'appelant, puis lecture unitaire de `/v1/runs/{run_id}` sans boucle cachée dans le
  gateway ;
- conversation générale privée à son créateur (hors pouvoir d'administration du
  propriétaire global) et conversation projet contrôlée par membership ;
- conversations, tours, identifiant de session provider, identifiant de Run, sortie,
  modèle, usage et erreur persistés en base ; unicité de `client_request_id` dans une
  conversation et clé d'idempotence stable après résultat de soumission incertain ;
- interface française pour bootstrap/connexion, Connexions et Conversations : liste,
  création, brouillon local, envoi et polling `GET` jusqu'à un état terminal ;
- tests API de persistance après relecture, reprise avec la même clé, conflit de
  requête, confidentialité générale, droits lecteur et diagnostic ; tests TypeScript
  du client de conversation, du CSRF et du contrat de polling.

## Hérité du Lot A

- shell moderne par défaut, thèmes clair/sombre, responsive et états explicites ;
- moteur pixel conservé derrière l'activation legacy ;
- exécution fail-closed : simulation `blocked`, succès refusé sans validation
  technique et preuve, lease expiré réconcilié en `interrupted` ;
- adaptateur Hermes `0.21.1` fondé sur `/health/detailed`, `/v1/capabilities` et
  `/v1/runs`, avec validation stricte des sorties ;
- baseline propre du Lot A : 19 tests web, 74 tests moteur et 78 tests Python
  réussis, typecheck/build web réussis et audit npm sans vulnérabilité connue ; sa
  publication reste conditionnée à la PR, à la CI verte et au tag `v0.2.0`.

## Vérification finale propre du Lot B

Un worktree détaché sur le commit de code/version `df39634` a exclu tout le chantier
Pixel/LimeZu local non commité. Sur cet état :

- **121/121 tests Python réussis**, avec les deux warnings Starlette/AnyIO connus ;
- **28/28 tests web réussis** dans 5 fichiers ;
- **74/74 tests du moteur legacy réussis** dans 7 fichiers ;
- synchronisation `0.3.0`, typecheck TypeScript et build Vite réussis ;
- build web à **40 modules** et `npm audit` à **0 vulnérabilité connue**.

Ces résultats prouvent la tranche locale versionnée, pas un E2E navigateur, une
instance Hermes réelle ou un déploiement.

## Réalisé, non testé en conditions réelles

- le diagnostic, l'admission et la reprise Hermes sont câblés sur les routes
  officielles, mais aucune instance Hermes `0.21.1`, clé, modèle, mémoire ou outil
  réel n'a été utilisé ;
- les écrans d'authentification et de conversation sont implémentés, mais aucun test
  navigateur E2E n'enchaîne encore bootstrap → rechargement → conversation sur des
  services réellement démarrés ;
- la persistance est testée sur SQLite et via SQLAlchemy `create_all()` ; elle ne
  prouve ni migration d'une base existante, ni concurrence PostgreSQL ;
- la reprise est un polling de statut à la demande. Il n'existe pas encore de flux
  SSE/WebSocket utilisateur authentifié, outbox ou curseur durable ;
- les deux warnings de dépendances Starlette/FastAPI identifiés au Lot A restent à
  éliminer avec des versions de test verrouillées plutôt qu'en les masquant.

## Non configuré ou non livré

- instance Hermes, clé de service et test réel opt-in ;
- premier runner réel, sandbox, réseau borné et exécuteur Codex/Claude raccordé ;
- CLI `acp`, streaming, stop/cancel Hermes, approbations Hermes et pièces jointes ;
- import de dépôts/dossiers/documents et isolation de leurs fichiers/secrets ;
- centre MCP, bibliothèque de skills et coffre de secrets ;
- Playwright, Studio direct/replay et stockage d'objets privé ;
- PostgreSQL validé, migrations versionnées, outbox et reprise par curseur ;
- artefacts téléchargeables, médias, 3D et automatisations ;
- images de services, déploiement Railway, sauvegarde, restauration, rotation et
  observabilité de production.

## Restant

| Lot | Capacité verticale | État |
|---|---|---|
| A | audit, shell moderne, Hermes Runs strict et exécution fail-closed | **Vérifié ; publication PR/CI/tag en attente** |
| B | accès propriétaire, RBAC, onboarding, diagnostic et conversation persistante | **Vérifié localement ; Hermes réel et E2E navigateur manquants** |
| C | runner isolé réel, machine d'états validée, preuves, approbations/arrêt et CLI synchronisé | **Non commencé** |
| D | MCP/skills versionnés, installation contrôlée, diagnostics, révocation et tests SSRF | **Non commencé** |
| E | reporter Playwright, flux authentifié, traces, captures et bibliothèque de livrables | **Non commencé** |
| F | automatisations à propriétaire unique, calendrier Europe/Paris, budgets et alertes | **Non commencé** |
| G | images/3D et exécuteurs complémentaires, uniquement lorsque les backends sont configurés | **Non commencé** |
| H | PostgreSQL/migrations, Railway, sauvegarde-restauration et validation finale | **Non commencé** |

## Ordre de reprise recommandé

1. Démarrer exactement Hermes `0.21.1` dans un environnement local isolé, vérifier
   le diagnostic puis un tour conversationnel borné avec une clé d'idempotence, sans
   secret dans les logs et sans fournisseur payant implicite.
2. Ajouter un E2E navigateur des écrans bootstrap/connexion/rechargement,
   onboarding, diagnostic et reprise d'une conversation.
3. Introduire des migrations versionnées avant tout test sur une base existante ou
   déploiement partagé.
4. Livrer le runner réel et le CLI du Lot C ; ne pas présenter le polling web actuel
   comme un streaming ou une reprise CLI.

## Conditions pour annoncer le Lot B terminé

- bootstrap unique, expiration, révocation, CSRF, refus d'identité forgée et RBAC
  inter-projets sont verts dans la suite finale ;
- le navigateur restaure une session et une conversation après rechargement sans
  créer un second Run ;
- un diagnostic et un Run borné réussissent contre une instance Hermes
  `0.21.1` réellement lancée, ou le lot reste explicitement « non testé réel » ;
- hors liveness explicitement publique, aucune donnée provider, événement,
  conversation ou donnée métier n'est exposée anonymement ; le flux utilisateur
  temps réel reste désactivé tant qu'il n'est pas authentifié et filtré ;
- la documentation distingue les tests simulés, l'exécution réelle et les capacités
  encore absentes.

## Références de suivi

- `docs/audit-modernisation.md` : constats et risques initiaux ;
- `docs/architecture.md` : frontières et sources de vérité ;
- `docs/hermes-integration.md` : contrat Runs, diagnostic et configuration ;
- `docs/acceptance-report.md` : matrice des vingt scénarios ;
- `docs/security.md` : contrôles livrés et bloqueurs avant exposition réseau ;
- `docs/mcp-and-skills.md` et `docs/live-studio.md` : architectures des lots D et E.
