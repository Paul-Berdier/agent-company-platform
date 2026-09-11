# Architecture cible

Statut : décision adoptée pour la modernisation 2026.
Produit : Agent Company Platform, espace personnel par défaut.

## Décision

La plateforme conserve son interface `apps/web` et son API métier. Hermes Agent est
un service externe versionné, joint uniquement côté serveur par un adaptateur de
runtime. Le dashboard Hermes reste une console native facultative ; il n'est ni
embarqué par iframe ni forké pour devenir l'interface principale.

```text
Navigateur ───────┐
                  ├── API Agent Company Platform ── PostgreSQL
CLI acp ──────────┘          │            │
                             │            ├── stockage privé des livrables
                             │            └── journal durable / outbox
                             │
                             ├── adaptateur Hermes ── Hermes Agent v0.21.1
                             │      sessions, runs, SSE, stop, approvals
                             │
                             └── planificateur ── runners enrôlés
                                    environnements de run isolés
```

## Options évaluées

| Option | Atouts | Limites | Décision |
|---|---|---|---|
| Étendre le dashboard Hermes | Réutilise chat, profils, skills et MCP natifs ; maintenance UI réduite | Ne porte pas naturellement les projets, droits, preuves, runners et données existantes de la plateforme ; le plugin hériterait fortement du cycle Hermes | Console d'administration facultative seulement |
| Conserver `apps/web` avec adaptateur | Préserve les données et contrats, autorise une isolation par projet, un web et un CLI identiques, et un historique de preuves indépendant | Nécessite de traduire et persister explicitement les sessions/runs/événements | **Retenue** |

Cette décision évite deux administrations concurrentes : les réglages natifs Hermes
peuvent être consultés ou modifiés via son API lorsque la capacité existe ; la
plateforme ne maintient pas une copie silencieuse de ces réglages.

## Sources de vérité

| Domaine | Autorité | Données de rapprochement |
|---|---|---|
| Identité, droits, projets | plateforme | `user_id`, `project_id` |
| Mission, état accepté, budget, approbation | plateforme | `task_id`, `task_run_id`, `attempt_id` |
| Preuves, artefacts, tests | plateforme et moteur ayant produit la preuve | checksum, code de sortie, reporter, provenance |
| Session, profil, modèle et skills Hermes | Hermes | `hermes_session_id`, profil et version détectée |
| Exécution Hermes | Hermes pendant le run ; plateforme pour l'historique durable | `hermes_run_id`, idempotency key |
| Processus d'un runner | runner pendant l'exécution ; plateforme pour la réservation | `worker_id`, lease, fencing token |

Un identifiant Hermes ou runner n'accorde jamais à lui seul un accès à un projet.
Le mapping appartient à la plateforme et est contrôlé côté serveur.

## Responsabilités

### Interface web et CLI

- utilisent la même API et les mêmes règles d'autorisation ;
- affichent `inconnu` lorsque la mesure n'existe pas ;
- se reconnectent par curseur sans relancer une mission ;
- ne reçoivent jamais une clé de service Hermes ou worker ;
- proposent le pixel office uniquement par un drapeau legacy désactivé par défaut.

### API métier

- authentifie le propriétaire/opérateur/lecteur ;
- applique le scope projet sur chaque lecture, écriture, flux et fichier ;
- valide la machine d'états, les approbations, budgets et idempotency keys ;
- persiste l'événement et son effet métier de façon transactionnelle ;
- délivre des URLs de fichier privées et bornées.

### Adaptateur Hermes

- détecte la surface avec `/v1/capabilities` ;
- distingue `/health` (liveness) de `/health/detailed` (readiness) ;
- traduit les opérations plateforme vers sessions et Runs officiels ;
- conserve `API_SERVER_KEY` côté serveur ;
- utilise des clés d'idempotence pour la création de run ;
- échoue fermé si une capacité ou une réponse est absente ;
- normalise les événements SSE avant persistance.

Les méthodes historiques `plan/evaluate` de la plateforme sont des traductions
explicites vers un run structuré, pas des routes supposées exister chez Hermes.

### Runners

- s'enrôlent avec une identité révocable et se connectent en sortie ;
- annoncent des capacités vérifiées et une concurrence bornée ;
- reçoivent uniquement le dossier autorisé, les références de secrets nécessaires
  et un lease lié à une tentative ;
- exécutent sans interpolation shell, sous utilisateur non privilégié et avec des
  limites de durée/ressources/réseau ;
- publient preuves et événements uniquement pour le run loué.

Un worktree Git organise les changements mais n'est pas une sandbox. Le socket Docker
hôte n'est jamais exposé à un agent.

## Modèle personnel sans supprimer l'existant

La hiérarchie existante reste compatible :

```text
Organization → Workspace → Department → Project → Team → Agent → Task → Task Run
```

L'interface masque cependant Organization/Department/Team dans le parcours courant.
Un espace personnel est sélectionné par défaut ; un projet peut être un dépôt, un
dossier de runner, une collection de documents ou un projet vide.

## Machine d'états cible

```text
queued → preparing → running ───────────────→ succeeded
             │          │                         │
             │          ├→ waiting_approval ─────┤
             │          ├→ blocked               │
             │          ├→ stopping → cancelled  │
             │          └→ interrupted           │
             └────────────────────────────→ failed
```

Trois valeurs restent séparées :

- état d'exécution du run ;
- validation technique (`passed`, `failed`, `not_run`, `unknown`) ;
- acceptation utilisateur (`pending`, `accepted`, `rejected`).

Une simulation, une sortie vide, un évaluateur indisponible ou un JSON invalide ne
peut jamais produire `succeeded`.

## Événements durables

Chaque événement cible porte : version, id, séquence monotone par run, horodatage,
projet, conversation, run, tentative, étape, exécuteur, type et payload autorisé.
Les médias sont stockés hors du flux et référencés par un artefact.

Le flux cible est : transaction métier + outbox, relay idempotent, puis WebSocket/SSE
authentifié. Une reconnexion fournit le dernier curseur ; le serveur page, déduplique
et réconcilie le statut auprès du runtime.

## Déploiement

Hermes et la plateforme sont des services distincts et peuvent partager un réseau
privé, jamais un volume implicite. PostgreSQL conserve le métier ; Hermes possède son
propre état persistant ; un stockage d'objets privé reçoit les livrables. Les runners
ne tournent pas dans le serveur de contrôle par défaut.

Voir `docs/deployment-railway.md` pour l'état réellement livré et les actions restant
à vérifier avant une mise en production.
