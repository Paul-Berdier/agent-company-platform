# Sécurité et frontières de confiance

Date d'état : 11 septembre 2026
Statut : frontières utilisateur/inter-services fermées et runner local contrôlé au
Lot C ; production interdite sans isolation OS/réseau, stockage et exploitation

## Conclusion

Le Lot C conserve le bootstrap propriétaire, les sessions serveur révocables et
expirables, une protection CSRF et des rôles appliqués aux routes utilisateur. Les
frontières API → provider-gateway et API → event-service utilisent des secrets
inter-services distincts ; les surfaces sans secret configuré échouent fermées.

Le worker réel est désormais un opt-in : seul un exécutable absolu via un argv local
fixe et configuré peut démarrer, avec tentative/fencing, cwd neuf, environnement
minimal, durée et sorties bornées, et arrêt de l'arbre de processus. Une politique
d'autonomie que ce backend ne peut pas appliquer est refusée avant le spawn.

Ces garanties ne rendent pas encore la plateforme exploitable sur Internet. Il
reste notamment à compléter la matrice d'autorisation exhaustive, les en-têtes web
de production, le flux temps réel utilisateur, l'isolation OS/réseau du runner, le
stockage privé, les migrations, la rotation et la restauration.

L'infrastructure pcIA et les systèmes Prooftag sont hors périmètre. Ils ne doivent
être ni découverts, ni configurés, ni proposés comme runner ou ressource personnelle.

## Actifs et frontières

Les actifs principaux sont les identités et sessions, secrets de fournisseurs,
sources des projets, mémoire et conversations, permissions, runs et approbations,
événements, preuves, artefacts et identités de runners.

```text
Navigateur / CLI
      │ frontière utilisateur non fiable
      ▼
API de contrôle ── base métier ── stockage privé
      │
      ├── frontière de service ── Hermes
      ├── frontière de service ── événements
      └── frontière d'exécution ── runner ── projet et outils non fiables
```

Un `project_id`, une instruction de prompt, un worktree Git ou un manifest de plugin
n'est pas une frontière de sécurité. Chaque contrôle doit être appliqué par l'API,
le stockage ou le runner qui détient effectivement la ressource.

## Corrections critiques héritées du Lot A

- Les échecs HTTP, réponses non JSON, plans vides et verdicts absents ou invalides
  du gateway échouent fermés ; aucun plan ou verdict positif n'est inventé.
- Le provider manuel conserve une évaluation en attente et non approuvée.
- La terminaison nominale d'une simulation worker est bloquée, avec validation
  technique non exécutée et acceptation utilisateur en attente ; une erreur de
  préparation peut échouer, mais une simulation ne peut jamais annoncer un succès.
- Le client HTTP de la plateforme et celui du provider-gateway sont séparés : le
  Bearer du worker n'est plus envoyé au gateway.
- La mise à jour d'un task run par un worker exige son Bearer, `X-Worker-Id` et un
  lease actif et non expiré sur le run.
- Un statut `succeeded` exige `technical_validation=passed` et au moins une preuve ;
  l'API met à jour tâche/agent, libère le lease et persiste elle-même l'événement
  terminal dans la transaction, au lieu d'accepter un succès séparé du worker.
- L'ingestion publique d'un événement de tâche exige l'identité worker, un lease
  actif, un scope canonique dérivé du run et un type non terminal explicitement
  autorisé.
- Lorsqu'une expiration de lease est réconciliée par l'API, le run devient
  `interrupted`, la tâche et l'agent `blocked`, la capacité est libérée et
  `task.interrupted` est persisté ; la plateforme n'effectue aucun replay
  automatique et refuse de réanimer le lease après son échéance.
- Les trois services HTTP n'acceptent plus `*` par défaut pour CORS ; leurs seules
  origines par défaut sont les deux URLs de développement du web.

Ces garanties ont des tests ciblés. Le Lot C ajoute un fencing token par tentative
et protège les transitions de la machine d'états mission ; toutes les routes enfant,
les effets tiers et le flux WebSocket utilisateur ne sont pas encore couverts.

## Accès utilisateur et frontière Hermes (Lot B)

- Le bootstrap n'est disponible qu'avant la création du premier propriétaire et
  exige `ACP_BOOTSTRAP_TOKEN` ; aucune inscription publique n'est exposée.
- Les mots de passe sont hachés avec Argon2id. Seul le SHA-256 d'un jeton de session
  opaque est stocké ; la session expire, peut être révoquée et voyage dans un cookie
  `HttpOnly` `SameSite=Strict` (`Secure` exigé derrière HTTPS).
- Le jeton CSRF est tourné lors de la restauration de session et exigé sur les
  mutations web. Les réponses d'authentification sont `no-store`.
- `X-User-Id` n'établit aucune identité. Les ressources utilisateur sont résolues à
  partir de la session puis filtrées par projet/workspace et rôle propriétaire,
  opérateur/membre ou lecteur.
- Le navigateur ne reçoit ni `HERMES_API_KEY`, ni Bearer worker ou gateway. Hors
  `GET /health`, le provider-gateway exige `ACP_GATEWAY_SERVICE_TOKEN`.
- Conversations et tours sont persistés avant l'appel provider ; les répétitions
  conservent une clé d'idempotence durable et une conversation générale reste privée
  à son créateur, sauf pouvoir d'administration global explicitement testé.

## Durcissement du service d'événements (lot B)

- `POST /internal/events` échoue fermé lorsque `ACP_EVENT_SERVICE_TOKEN` est absent,
  et exige un Bearer comparé en temps constant lorsqu'il est configuré. L'API ne
  transmet ce secret que dans l'en-tête `Authorization`, jamais dans l'URL.
- Le WebSocket navigateur anonyme est fermé par défaut avec le code applicatif
  `4403`. Seul l'opt-in explicitement dangereux
  `ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET=1` rétablit le comportement historique
  pour un développement local isolé.
- Ce verrouillage ne constitue pas encore un flux temps réel utilisateur : une voie
  authentifiée et scoppée, avec reprise par curseur, reste à construire avant toute
  exposition réseau.

## Écarts bloquants

### Identité et autorisation

- Les routes utilisateur principales sont protégées et scoppées, mais aucune matrice
  exhaustive ne couvre encore chaque relation enfant, événement, fichier, export et
  future route de plugin.
- Le propriétaire global possède volontairement un pouvoir d'administration large ;
  sa journalisation, les changements de membership et les actions sensibles doivent
  encore recevoir un audit d'autorisation complet.
- Le CLI ouvre et conserve sa propre session cookie/CSRF ; il n'existe pas encore de
  jeton utilisateur court et scoppé dédié aux usages non interactifs.
- La limitation des tentatives de connexion, la récupération de compte et une
  politique de mot de passe d'exploitation ne sont pas livrées.

### Réseau, événements et navigateur

- La configuration CORS de production, les méthodes/en-têtes permis et le modèle
  d'authentification restent à tester ; CORS ne constitue pas un contrôle d'accès.
- Le service d'événements conserve les sockets en mémoire ; l'ingestion interne est
  authentifiée et le WebSocket anonyme est fermé par défaut, mais il n'existe pas
  encore de flux navigateur authentifié, scoppé, séquencé ou rejouable.
- Il n'existe pas d'origine séparée pour les aperçus de projets non fiables.
- Le CSRF et la politique de cookie sont couverts localement ; CSP, HSTS, autres
  en-têtes de sécurité, limitations d'upload et configuration HTTPS restent à
  valider en déploiement.

### Exécution, secrets et stockage

- Le backend local réel est configuré, borné et testable, mais il conserve les droits
  du compte worker et n'impose ni sandbox OS ni politique réseau forte. Il refuse
  tout mode non supervisé, toute liste d'actions non vide et toute ressource en
  écriture, faute de pouvoir appliquer ces promesses.
- Les sorties stdout/stderr persistées comme preuves sont bornées mais non expurgées.
  La racine des runs doit être protégée et aucun secret ne doit être allowlisté vers
  un programme susceptible de l'imprimer.
- Les origines qui reçoivent les Bearers gateway, événements, Hermes ou worker sont
  validées : HTTP uniquement sur loopback, HTTPS ailleurs, sans userinfo, chemin,
  query ni fragment. Ces clients internes ignorent aussi les variables proxy de
  l'environnement afin qu'un Bearer loopback ne soit pas détourné par `HTTP_PROXY`.
- Les secrets ne passent pas encore par un coffre avec références, rotation et
  portées minimales.
- Les artefacts sont des métadonnées ou chemins ; il n'existe pas de stockage privé,
  d'URL signée ou de contrôle de téléchargement de bout en bout.
- Les migrations PostgreSQL, sauvegardes, restaurations et procédures de rotation
  ne sont pas livrées.

## Politique cible

### Sessions et rôles

Le premier démarrage crée un propriétaire par un secret à usage unique ou un flux
local explicitement borné ; aucune inscription publique n'est ouverte. Les sessions
sont stockées côté serveur, révocables, expirables et renouvelées avec rotation.
Les cookies web sont `HttpOnly`, `Secure` en production et `SameSite` adapté ; les
clients non navigateur utilisent des jetons courts et scoppés.

| Rôle | Portée cible |
|---|---|
| Propriétaire | configuration de l'espace, connexions, membres, politiques et actions sensibles |
| Opérateur | projets autorisés, missions, approbations permises et artefacts associés |
| Lecture seule | consultation des objets explicitement autorisés, aucune exécution ni secret |

Le contrôle porte sur l'organisation/espace et le projet à chaque requête, flux et
objet. Une ressource enfant est résolue côté serveur avant la décision ; le client
ne choisit pas librement son scope.

### Autonomie et approbations

Trois niveaux sont visibles : lecture, travail en environnement isolé, actions
sensibles sur validation. Une approbation contient l'action canonique, la cible, les
conséquences, la portée, l'empreinte des paramètres et une expiration. Toute
modification invalide l'approbation. Un refus, une expiration et un arrêt produisent
un état durable et un événement d'audit.

### Runners et événements

- enrôlement par jeton limité et à usage borné, identité propre, révocation et
  rotation ;
- connexion sortante authentifiée, lease par tentative, renouvellement et fencing
  token monotone ;
- utilisateur non privilégié, répertoire canonique, limites de temps/ressources et
  politique réseau ; aucun socket Docker hôte ;
- enveloppe d'événement signée ou authentifiée, schéma versionné, séquence,
  idempotence et vérification run/tentative/projet ;
- transaction métier et outbox, puis diffusion authentifiée et reprise par curseur.

### Contenus et intégrations non fiables

- Les fichiers, dépôts, README, skills, réponses MCP et sorties de modèle sont des
  données non fiables et ne peuvent modifier les politiques.
- Les chemins sont résolus dans une racine autorisée ; archives, liens et fichiers
  spéciaux sont contrôlés avant extraction.
- Les contenus HTML, SVG, traces et aperçus s'exécutent sur une origine isolée avec
  CSP et sandbox appropriées.
- Les connexions sortantes contrôlent SSRF, redirections, DNS rebinding, adresses
  privées et métadonnées cloud côté serveur et runner.
- Les secrets sont référencés, injectés au dernier moment et absents des URL, logs,
  événements, réponses frontend et exports.

## Validation restant requise avant exposition réseau

- E2E navigateur de bootstrap, reconnexion, expiration, révocation et CSRF sur les
  services réellement démarrés ;
- matrice RBAC exhaustive par route, projet, flux et fichier, en complément des tests
  inter-projets négatifs déjà présents ;
- compléter les tests de concurrence lease/fencing par une validation multi-processus ;
- tests SSRF, traversée de chemins, archive malveillante, XSS et limites d'upload ;
- rotation des clés de service, révocation runner et absence de secrets dans les
  journaux ;
- tests d'artefacts privés et d'URLs expirées ;
- reprise d'événements par curseur sans perte ni double effet ;
- analyse statique, audit de dépendances et revue de configuration de production ;
- restauration testée sur une copie de données.

## État réel

### Réalisé/vérifié

- Les comportements fail-closed historiques du worker/gateway et du provider manuel,
  ainsi que les écritures worker critiques, restent couverts ; les nombres de la
  release courante sont consignés dans le rapport d'acceptation.
- La réconciliation d'un lease expiré, le fencing par tentative et l'arrêt de
  l'arbre d'un processus local réel sont couverts par des tests déterministes ;
  l'absence de double effet externe sur un outil tiers n'est pas démontrée.
- La séparation des clients empêche la transmission accidentelle du Bearer worker au
  provider-gateway.
- Le bootstrap, les sessions, l'expiration/révocation, le CSRF, l'isolation de
  conversations et les rôles projet sont couverts dans la suite propre du Lot B.
- Les frontières gateway/event-service refusent un appel sans Bearer interne valide,
  et le WebSocket anonyme est fermé par défaut.
- Le lockfile Node versionné utilise Vite `8.3.0` et Vitest `5.0.0` ; un `npm ci`
  propre suivi de `npm audit` ne signale aucune vulnérabilité connue au moment de la
  préparation de `0.3.0`.

### Réalisé, non testé réel

- L'adaptateur Hermes conserve son secret côté serveur par conception, mais aucune
  connexion Hermes réelle n'a été effectuée.
- Le web utilise une session cookie/CSRF réelle dans les tests API et TypeScript,
  mais le parcours complet n'a pas encore été rejoué dans un navigateur contre les
  services et une instance Hermes réellement lancés.

### Non configuré

- matrice RBAC exhaustive et journal d'administration ;
- coffre de secrets et rotation ;
- CORS de production, HTTPS/HSTS, CSP et origine d'aperçu ;
- sandbox OS et politique réseau du runner, endpoint worker pour les approbations ;
- stockage privé, URLs signées et rétention ;
- outbox, authentification des flux et reprise par curseur.

### Restant

Les prochaines tranches doivent isoler plus fortement le runner et raccorder ses
demandes d'approbation. Elles doivent aussi compléter la
matrice de scopes, les événements durables, MCP/skills, les médias privés, les
migrations et la restauration. Tant que ces points ne sont pas testés, le produit
reste réservé au développement local sur une machine de confiance.
