# Audit de modernisation

Date de vérification : 11 septembre 2026, fuseau Europe/Paris
Révision auditée : `5887603b7623c062fcfd79109acec93398266692` (`main`)

## Résumé exécutif

Le dépôt contient un socle métier utile (FastAPI, modèles SQLAlchemy, contrats,
workers enrôlables, leases, locks, approbations et journal d'événements), mais le
produit principal est encore un bureau pixel art et plusieurs fonctions présentées
comme opérationnelles sont des simulations.

Les quatre risques prioritaires sont :

1. une panne du provider peut être convertie en plan de secours puis en succès ;
2. l'accès utilisateur est ouvert par défaut et `X-User-Id` est usurpable ;
3. l'adaptateur Hermes utilise des routes qui ne font pas partie de l'API officielle ;
4. un client non authentifié peut injecter un événement ou modifier un task run.

La modernisation conserve les briques métier et le code pixel existant, mais retire
ce dernier du chargement par défaut. L'architecture retenue garde la plateforme
comme plan de contrôle et connecte un service Hermes versionné par un adaptateur
serveur explicite.

## État du dépôt et de l'environnement

- Dépôt Git : `origin` pointe vers
  `https://github.com/Paul-Berdier/agent-company-platform.git`.
- Le worktree était déjà fortement modifié avant cette intervention, principalement
  dans le moteur, les scènes et les assets pixel. Ces fichiers sont préservés ; aucun
  reset ou nettoyage global n'a été exécuté.
- Node `24.19.0`, npm `11.17.0`. Les dépendances npm sont présentes et le
  `package-lock.json` résout notamment Vite `5.4.21`, TypeScript `5.9.3`, Vitest
  `2.1.9` et Phaser `3.90.0`.
- Aucun Python système utilisable ni `.venv` n'était présent. Le runtime de travail
  Python `3.12.14` a servi à installer les packages éditables déclarés par le dépôt
  et à exécuter les tests ; cela ne constitue pas un environnement local livré.
- Les contraintes Python utilisent des bornes larges et aucun lock Python n'est
  versionné.
- Aucun Dockerfile, manifeste Railway moderne ou pipeline CI versionné n'a été
  trouvé.

## Constats par composant

### Interface web

Le chemin principal importait `@acp/pixel-office-engine` et initialisait Phaser dès
le démarrage (`apps/web/src/main.ts`). L'interface utilise de vraies données pour
`/overview` et `/events`, mais masque plusieurs pannes en listes vides ou valeurs
nulles (`apps/web/src/api.ts`). La création de tâche n'inspecte pas la réponse de la
mise en file et le titre saisi est remplacé par un libellé de démonstration.

Les indicateurs confondent statut de tâche, validation technique et succès d'un run.
En l'absence d'échantillon, l'ancien HUD calcule même 100 % de réussite
(`apps/web/src/ui/hud.ts`). Il n'existe pas de routeur, d'onboarding, de conversation,
de bibliothèque ou de centre de connexions utilisable.

À conserver : Vite/TypeScript, les contrats partagés et le moteur pixel complet,
désormais traité comme fonctionnalité legacy désactivée par défaut.

### API métier et base

Les modèles couvrent projets, tâches, runs, sessions, mémoires, workers, leases,
locks, approbations et artefacts (`packages/database/.../models.py`). Le journal
d'événements est bien durable côté API, contrairement au premier constat historique.

Écarts critiques :

- `apps/api/src/acp_api/deps.py` ouvre l'accès sans principal et accepte une identité
  déclarative `X-User-Id` ;
- plusieurs routes ne vérifient aucun scope ; la création de membership peut accorder
  le rôle owner ;
- `PATCH /task-runs/{id}` accepte publiquement statut, résultat, plan et logs ;
- les états sont stockés comme chaînes libres et les transitions ne sont pas validées ;
- `create_all()` remplace encore un vrai système de migrations ;
- SQLite n'active pas explicitement les clés étrangères ; `psycopg` n'est pas une
  dépendance alors que la documentation propose PostgreSQL ;
- un artefact est seulement un chemin déclaré, sans stockage ni téléchargement.

À conserver : les contrats Pydantic, les identités de worker distinctes, le hachage
des jetons, les leases, les locks et les modèles d'approbation/artefact comme point
de départ.

### Worker et exécuteurs

`apps/worker/src/acp_worker/main.py` ne raccorde aucun exécuteur réel. Le mode réel
est refusé et la simulation dort entre des étapes. Avant correction, le worker :

- inventait un plan lorsque la passerelle était indisponible ;
- retournait `approved: true` lorsque l'évaluation échouait ;
- interprétait l'absence du champ `approved` comme vraie ;
- envoyait son Bearer API au provider-gateway en réutilisant le même client HTTP.

`executors.py` construit des listes d'arguments et borne le répertoire projet, ce qui
est une base utile. Ces adaptateurs ne sont toutefois pas câblés, ne streament rien et
le mode Claude est lecture seule. La commande Codex construite n'a pas été validée
contre la version installée et l'authentification Codex n'est pas configurée.

### Hermes et provider-gateway

L'ancien adaptateur appelle `/v1/plans`, `/v1/evaluations`, `/v1/summaries` et une
route de révision propres au dépôt. Ses tests reproduisent ces mêmes routes avec
`httpx.MockTransport` et ne démontrent donc aucune compatibilité Hermes.

Au 11 septembre 2026, la dernière version publiée vérifiée est Hermes Agent
`v0.21.1`, tag `v2026.9.7`. La surface officielle utile comprend
`/v1/capabilities`, `/health/detailed`, les Runs (`/v1/runs` et événements SSE),
les sessions REST, l'arrêt, les approbations, les skills/toolsets et les jobs. Le
simple `/health` n'est qu'une liveness probe.

Le provider manuel conservait ses demandes uniquement en mémoire et renvoyait une
approbation provisoire positive. Le provider mock reste acceptable uniquement comme
fixture de test explicitement identifiée.

### Événements

L'API écrit les événements en base avant de tenter leur diffusion
(`apps/api/src/acp_api/events_bus.py`). La diffusion échoue toutefois silencieusement
et n'utilise pas d'outbox transactionnelle. Le service d'événements garde seulement
une table de sockets en mémoire et ne gère ni curseur, ni séquence, ni rattrapage.

`POST /internal/events` et `/ws` sont actuellement non authentifiés. Le contrat
événement ne porte pas de séquence, tentative, exécuteur ou version de schéma par
événement. Les médias lourds ne sont pas encore séparés dans un stockage d'objets.

### Déploiement et exploitation

Les scripts locaux installent des versions Python non verrouillées, resèment la base
à chaque lancement et n'orchestrent pas la readiness ni l'arrêt de tous les services.
La documentation Railway existante est une intention, pas une configuration testée.
Aucun déploiement ou service payant n'a été lancé pendant l'audit.

## Vérifications exécutées avant modification

| Commande | Résultat |
|---|---|
| `npm test --workspace @acp/web` | 3 fichiers, 16 tests réussis |
| `npm test --workspace @acp/pixel-office-engine` | 12 fichiers, 117 tests réussis |
| `python -m pytest -q` avant installation de l'extra de test | 14 réussis, 6 non démarrés faute de `pytest-asyncio` |
| suite Python après installation des extras déclarés | 20 tests réussis (audit secondaire) |

La réussite de tests mock ne prouve ni une connexion Hermes réelle, ni un runner
réel, ni un déploiement Railway. Aucun test externe payant n'a été exécuté.

## Plan de migration ordonné

1. **Lot A — vérité et surface sûre** : supprimer les faux succès, séparer clients
   API/gateway, désactiver le pixel art par défaut, livrer un shell accessible avec
   diagnostics honnêtes, documenter les frontières et ajouter les tests négatifs.
2. **Lot B — accès et conversation Hermes** : bootstrap propriétaire fermé, sessions
   révocables, RBAC serveur, mapping plateforme/Hermes, conversation persistante,
   streaming et reprise.
3. **Lot C — exécution prouvée** : machine d'états stricte, endpoint worker avec
   lease/attempt/fencing, premier runner isolé réel, preuves et CLI synchronisé.
4. **Lots D à G** : MCP/skills contrôlés, studio Playwright, bibliothèque, routines,
   budgets, médias et exécuteurs complémentaires.
5. **Lot H** : migrations PostgreSQL, outbox/reprise, sauvegarde-restauration,
   images de services, configuration Railway et rapport d'acceptation complet.

## Première tranche appliquée après l'audit

- Le shell moderne devient l'entrée par défaut ; le bureau pixel reste disponible
  uniquement par `?legacy-office=1` ou `VITE_ACP_LEGACY_OFFICE=1`.
- La saisie de mission conserve le titre et les critères utilisateur, valide les
  réponses de création/mise en file et montre les échecs sans données de secours.
- Le worker n'invente plus plan ou approbation, sépare ses clients API/gateway et
  termine une simulation en `blocked`.
- Les mises à jour de run et événements worker exigent identité et lease. Les
  événements terminaux viennent de l'API ; `succeeded` exige validation technique et
  preuve.
- Lorsqu'une expiration de lease est réconciliée par l'API, le run passe en
  `interrupted`, la tâche et l'agent en `blocked`, la capacité est libérée et un
  événement durable `task.interrupted` est persisté sans reprise automatique ; un
  renouvellement arrivé après l'échéance est refusé.
- Le provider manuel n'approuve plus une demande encore en attente.
- L'adaptateur Hermes traduit les quatre opérations vers les Runs officiels
  `0.21.1`, avec detailed health, capabilities, idempotence, polling borné et sorties
  strictes.

Vérification finale sur le même worktree : **78 tests Python**, **27 tests web** et
**117 tests du moteur legacy** réussis ; typecheck TypeScript et build Vite réussis.
Deux warnings de dépendances Starlette/FastAPI subsistent. Deux captures navigateur
réelles sont conservées dans `docs/assets/screenshots`.

## Risques restant bloquants pour une production

- authentification propriétaire et RBAC complets ;
- autorisation par projet sur chaque route et flux ;
- fencing token ou identifiant de tentative pour rejeter un ancien worker après
  expiration ou réattribution ; la vérification du lease actif est déjà appliquée ;
- migrations Alembic et tests PostgreSQL ;
- événements authentifiés, séquencés et rejouables ;
- stockage privé réel des artefacts ;
- sandbox d'exécution démontrée ;
- déploiement, sauvegarde et restauration réellement testés.

L'infrastructure pcIA et les systèmes Prooftag sont explicitement hors périmètre et
ne doivent jamais être proposés comme runner ou ressource personnelle.
