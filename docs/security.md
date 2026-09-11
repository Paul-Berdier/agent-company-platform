# Sécurité et frontières de confiance

Date d'état : 11 septembre 2026
Statut : durcissement critique partiel du lot A ; production interdite

## Conclusion

Le dépôt ne possède pas encore de premier accès sécurisé, de session utilisateur
révocable ni de RBAC complet. Plusieurs routes métier et flux restent ouverts ou
insuffisamment scoppés. Les corrections du lot A empêchent certains faux succès et
protègent les écritures worker les plus critiques, mais elles ne rendent pas la
plateforme exploitable sur Internet.

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

## Corrections critiques du lot A

- Les échecs HTTP, réponses non JSON, plans vides et verdicts absents ou invalides
  du gateway échouent fermés ; aucun plan ou verdict positif n'est inventé.
- Le provider manuel conserve une évaluation en attente et non approuvée.
- Une simulation worker produit un état bloqué, avec validation technique non
  exécutée et acceptation utilisateur en attente ; elle ne peut plus annoncer un
  succès.
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

Ces garanties ont des tests ciblés. Elles ne couvrent pas encore un fencing token
par tentative, toute la machine d'états, toutes les routes ou le flux WebSocket.

## Écarts bloquants

### Identité et autorisation

- L'identité utilisateur peut encore être absente ou déclarée via `X-User-Id` ; cet
  en-tête est usurpable et ne prouve pas un principal.
- Il n'existe ni bootstrap propriétaire fermé, ni session révocable, ni protection
  contre l'inscription publique, ni rôles propriétaire/opérateur/lecture seule
  appliqués partout.
- Les scopes projet ne sont pas contrôlés sur chaque route, événement et fichier.
- Les changements de membership et autres écritures métier nécessitent un audit
  d'autorisation complet.

### Réseau, événements et navigateur

- La configuration CORS de production, les méthodes/en-têtes permis et le modèle
  d'authentification restent à tester ; CORS ne constitue pas un contrôle d'accès.
- Le service d'événements conserve les sockets en mémoire ; ses points internes et
  WebSocket ne sont pas tous authentifiés, scoppés, séquencés ou rejouables.
- Il n'existe pas d'origine séparée pour les aperçus de projets non fiables.
- CSRF, CSP, en-têtes de sécurité, limitations d'upload et politique de cookies ne
  sont pas encore validés.

### Exécution, secrets et stockage

- Aucun runner réel isolé et reproductible n'est raccordé. Un worktree ne suffit
  pas à isoler un processus.
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

## Validation requise avant exposition réseau

- tests d'intégration de bootstrap, reconnexion, expiration, révocation et CSRF ;
- matrice RBAC par route, projet, flux et fichier, avec tests inter-projets négatifs ;
- tests de concurrence lease/fencing et worker obsolète ;
- tests SSRF, traversée de chemins, archive malveillante, XSS et limites d'upload ;
- rotation des clés de service, révocation runner et absence de secrets dans les
  journaux ;
- tests d'artefacts privés et d'URLs expirées ;
- reprise d'événements par curseur sans perte ni double effet ;
- analyse statique, audit de dépendances et revue de configuration de production ;
- restauration testée sur une copie de données.

## État réel

### Réalisé/vérifié

- Les comportements fail-closed du worker/gateway et du provider manuel ont 7 tests
  ciblés réussis.
- Les écritures worker critiques, les leases, le refus d'un succès sans preuve et
  l'événement terminal canonique ont 5 tests API ciblés réussis.
- La réconciliation d'un lease expiré et son passage durable en état incertain sont
  couverts ; sans runner réel ni fencing token, l'absence de double effet externe
  n'est pas démontrée.
- La séparation des clients empêche la transmission accidentelle du Bearer worker au
  provider-gateway.
- Le lockfile Node versionné utilise Vite `8.3.0` et Vitest `5.0.0` ; un `npm ci`
  propre suivi de `npm audit` ne signale aucune vulnérabilité connue au moment de la
  préparation de `0.2.0`.

### Réalisé, non testé réel

- L'adaptateur Hermes conserve son secret côté serveur par conception, mais aucune
  connexion Hermes réelle n'a été effectuée.
- Le shell prévoit un Bearer de session optionnel, sans implémenter le mécanisme de
  connexion qui le délivre.

### Non configuré

- propriétaire initial, sessions, RBAC et matrice de scopes ;
- coffre de secrets et rotation ;
- CORS de production, CSRF, CSP et origine d'aperçu ;
- runner isolé, réseau sortant et fencing token ;
- stockage privé, URLs signées et rétention ;
- outbox, authentification des flux et reprise par curseur.

### Restant

La prochaine tranche de sécurité doit fermer l'accès utilisateur avant toute
exposition réseau, puis appliquer le scope projet à toutes les routes et tous les
flux. Les lots suivants doivent compléter l'isolation du runner, les événements
durables, MCP/skills, les médias privés et la restauration. Tant que ces points ne
sont pas testés, le produit reste réservé au développement local sur une machine de
confiance.
