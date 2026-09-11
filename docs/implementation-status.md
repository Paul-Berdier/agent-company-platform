# État d'implémentation et reprise

Date d'état : 11 septembre 2026, Europe/Paris
Portée : première tranche du lot A uniquement

## Résumé

La modernisation complète n'est pas terminée. Le travail actuel établit un audit,
une architecture, un shell moderne non pixel par défaut et des invariants de vérité
sur le worker/API. L'adaptateur Hermes est aligné sur la partie synchrone de l'API
Runs officielle et testé sur transport simulé. Les lots B à H restent à construire.

Le code pixel existant et les modifications antérieures du worktree sont conservés.
Le moteur devient une option legacy désactivée par défaut ; il n'est pas supprimé.

## Réalisé/vérifié

### Audit et décisions

- audit du dépôt, de l'environnement, des faux succès, de l'accès ouvert, des
  événements et du déploiement ;
- architecture retenue : web/API plateforme comme plan de contrôle et source de
  vérité métier, Hermes comme service versionné séparé ;
- inventaire des composants à réutiliser et risques de licence/maintenance ;
- architecture et critères cibles documentés pour MCP/skills, Studio et sécurité.

### Interface du lot A

- shell moderne en français, navigation compacte et états explicites ;
- aperçu et file de travail raccordés à l'API web existante ;
- erreurs, absence de configuration et indisponibilités affichées sans inventer de
  résultat ;
- thème clair/sombre, dispositions responsives, focus et réduction d'animation
  prévus par le nouveau système visuel ;
- moteur pixel conservé derrière une activation legacy et non chargé par défaut ;
- **19/19 tests web versionnés** réussis et **74/74 tests du moteur versionnés**
  réussis ; le complément pixel local 27/117 reste hors de la branche ;
- Vite `8.3.0` et Vitest `5.0.0`, avec `npm ci` et `npm audit` à zéro
  vulnérabilité connue au moment de la release ;
- parcours réel dans le navigateur intégré : bureau sombre, mobile clair, Missions,
  capacité non configurée et panne API ; deux captures PNG conservées.

### Vérité d'exécution et écritures worker

- suppression des plans et approbations de secours positifs ;
- validation stricte des réponses plan/évaluation ;
- simulation explicitement bloquée, validation technique `not_executed` et
  acceptation utilisateur `pending` ;
- provider manuel en attente et non approuvé ;
- clients API et gateway séparés pour ne pas transmettre le Bearer worker ;
- mise à jour d'un task run et ingestion d'un événement `task.*` liées à l'identité
  et au lease actif du worker ;
- succès refusé sans validation technique `passed` et preuve, état métier et
  événement terminal produits par l'API ;
- expiration réconciliée d'un lease : run `interrupted`, tâche et agent `blocked`,
  capacité libérée, événement durable `task.interrupted`, renouvellement tardif
  refusé et aucun replay automatique ;
- **7/7 tests fail-closed** et **5/5 tests API workers** ciblés réussis ; la suite
  Python complète compte **78/78 tests réussis**.

## Réalisé, non testé réel

- L'adaptateur Hermes utilise la découverte de capacités, la santé
  détaillée et les Runs officiels au lieu de routes supposées. Les tests sont fondés
  sur des transports simulés (**58 réussis**) ; aucune instance Hermes réelle n'a
  été jointe.
- Le shell moderne a été parcouru et capturé, mais aucune vérification E2E de mission
  ou exécution réelle n'a été produite.
- Le durcissement worker couvre des routes critiques ciblées, pas l'ensemble des
  routes, transitions, flux et scénarios concurrents.
- Deux warnings de dépendances Starlette/FastAPI subsistent : transition vers
  `httpx2` pour `TestClient` et alias AnyIO déprécié.

## Non configuré

- propriétaire initial, authentification utilisateur, sessions révocables et RBAC ;
- instance, version déployée et clé de service Hermes ;
- premier runner réel, sandbox, réseau borné et exécuteur Codex/Claude raccordé ;
- conversations persistantes et mapping de sessions Hermes ;
- centre MCP, bibliothèque de skills et coffre de secrets ;
- Playwright, Studio direct/replay et stockage d'objets ;
- PostgreSQL, migrations versionnées, outbox et reprise par curseur ;
- CLI `acp`, artefacts téléchargeables, médias, 3D et automatisations ;
- images de services, CI et configuration Railway vérifiée ;
- sauvegarde, restauration, rotation et observabilité de production.

## Restant

| Lot | Prochaine capacité verticale | État |
|---|---|---|
| A | corriger les warnings puis fermer l'accès utilisateur et les scopes restants | **En cours** |
| B | accès propriétaire fermé, RBAC projet, Hermes réel, onboarding, projets et conversation persistante | **Non commencé** |
| C | runner isolé réel, machine d'états validée, preuves, approbations/arrêt et CLI synchronisé | **Non commencé** |
| D | MCP/skills versionnés, installation contrôlée, diagnostics, révocation et tests SSRF | **Non commencé** |
| E | reporter Playwright, flux authentifié, traces, captures et bibliothèque de livrables | **Non commencé** |
| F | automatisations à propriétaire unique, calendrier Europe/Paris, budgets et alertes | **Non commencé** |
| G | images/3D et exécuteurs complémentaires, uniquement lorsque les backends sont configurés | **Non commencé** |
| H | PostgreSQL/migrations, Railway, sauvegarde-restauration et validation finale | **Non commencé** |

## Ordre de reprise recommandé

1. Corriger les deux warnings Starlette sans masquer les erreurs.
2. Fermer le premier accès et appliquer le RBAC/scoping projet avant d'exposer un
   service réseau.
3. Démarrer une instance Hermes versionnée en environnement local, vérifier
   `/health/detailed` et `/v1/capabilities`, puis tester un Run borné sans secret
   dans les logs.
4. Livrer une conversation persistante de bout en bout avant de raccorder un runner
   réel isolé.

## Conditions pour annoncer le lot A terminé

- aucune simulation, panne provider ou réponse mal formée n'apparaît comme succès ;
- le shell moderne est le chemin par défaut et le moteur pixel n'est pas téléchargé
  sans activation explicite ;
- les tests web, moteur, Python ciblés et Python complets sont tous verts sur le même
  état du dépôt ;
- le typecheck et le build web réussissent ;
- les deux warnings Starlette sont expliqués ou corrigés ;
- un parcours navigateur réel vérifie thèmes, responsive, navigation accessible et
  état hors ligne, avec captures conservées ;
- documentation et exemples de configuration ne prétendent ni auth, ni runner, ni
  Hermes, ni Railway opérationnels sans preuve.

## Références de suivi

- `docs/audit-modernisation.md` : constats et risques initiaux ;
- `docs/architecture.md` : frontières et sources de vérité ;
- `docs/acceptance-report.md` : matrice des vingt scénarios ;
- `docs/security.md` : bloqueurs avant exposition réseau ;
- `docs/mcp-and-skills.md` et `docs/live-studio.md` : architectures des lots D et E.
