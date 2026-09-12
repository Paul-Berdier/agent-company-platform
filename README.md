# Agent Company Platform

Poste de travail personnel pour organiser des projets et des missions, raccorder
Hermes Agent et, à terme, piloter des runners et outils spécialisés depuis le web et
un CLI commun.

La modernisation est engagée par tranches. Le Lot C ajoute aux fondations sécurisées
et aux conversations du Lot B une ressource mission durable, des tentatives
clôturées par fencing token, un backend de processus local configuré et le CLI
`acp`. Une instance Hermes réelle, le streaming utilisateur et une isolation OS du
runner ne sont toutefois pas encore validés. Le détail exact se trouve dans
[l'état d'implémentation](docs/implementation-status.md).

Version du Lot C : **0.4.0**. Les changements versionnés sont décrits dans
[CHANGELOG.md](CHANGELOG.md).

![Accueil sombre du Lot A](docs/assets/screenshots/lot-a-home-dark.png)

## Ce qui fonctionne aujourd'hui

- accueil, projets et composition d'une mission raccordés à l'API métier ;
- états chargement, vide, hors ligne, refus et non configuré sans données factices ;
- thèmes sombre/clair et disposition responsive ;
- bootstrap unique du propriétaire protégé par un secret dédié, mots de passe
  Argon2id et aucune inscription publique ;
- sessions opaques, hachées en base, expirables et révocables dans un cookie
  `HttpOnly` `SameSite=Strict`, avec jeton CSRF requis sur les mutations ;
- routes utilisateur fermées par défaut et lectures/écritures filtrées par les rôles
  propriétaire, opérateur/membre et lecteur au niveau du projet ;
- onboarding court avec diagnostic de préparation et création d'un projet dans un
  espace personnel masquant la hiérarchie historique ;
- conversations générales privées et conversations de projet persistées ; une clé
  d'idempotence durable conserve un seul Run logique même si l'admission est répétée,
  puis le tour est repris par consultation `GET` sans dépendre de l'onglet ouvert ;
- tâches, runs, workers enrôlés, leases, locks, approbations, événements persistés et
  métadonnées d'artefacts dans le socle FastAPI/SQLAlchemy ;
- missions atomiques avec objectif, critères, autonomie, budget et durée ; arrêt,
  relance idempotente, commentaires, preuves, validation technique et acceptation
  utilisateur séparées ;
- worker réel opt-in exécutant exclusivement un argv local configuré, sans shell,
  dans un cwd neuf, avec environnement/captures/timeout bornés, arrêt de l'arbre de
  processus et verdict fail-closed ; ce backend n'accepte que les missions
  supervisées dont les trois listes d'actions sont vides et les ressources en
  lecture seule ;
- CLI `acp` connecté à la même API pour l'accès, les projets, conversations,
  missions, runs, approbations, artefacts et workers, avec JSON et codes de sortie ;
- provider Hermes `0.21.1` via `/health/detailed`, `/v1/capabilities` et
  `/v1/runs` ;
- diagnostic Hermes typé visible dans Connexions, sans clé dans le navigateur ;
- surface métier du provider-gateway privée derrière un Bearer inter-services ;
  ingestion du service d'événements protégée et WebSocket anonyme fermé par défaut ;
- terminaison nominale d'une simulation worker en `blocked` (ou `failed` si sa
  préparation échoue), jamais présentée comme une exécution réussie ;
- refus d'un succès de run sans validation technique `passed` et preuve ;
- bureau pixel historique préservé mais non chargé par défaut.

Ce qui ne fonctionne pas encore est visible comme `Non configuré` et recensé dans
[le rapport d'acceptation](docs/acceptance-report.md). Le projet n'est pas prêt à
être exposé sur Internet.

## Architecture

```text
Web (Vite/TypeScript) ─┐
                      ├── API métier (FastAPI) ── base plateforme
CLI acp ───────────────┘         │
                                ├── provider-gateway ── Hermes Agent séparé
                                ├── service d'événements
                                └── workers enrôlés ── backend local configuré
```

La plateforme est la source de vérité des projets, droits, missions et preuves.
Hermes reste la source de vérité de ses sessions, profils, modèles et skills. Les
identifiants doivent être rapprochés explicitement. Voir
[docs/architecture.md](docs/architecture.md) et
[docs/hermes-integration.md](docs/hermes-integration.md).

## Démarrage local de développement

Prérequis actuels : Python 3.11 ou supérieur, Node 22.12 ou supérieur, npm. Les
dépendances Python ne sont pas encore verrouillées et les scripts créent les tables
avec `create_all()` ; utiliser uniquement une machine de développement de confiance.

Sous Windows PowerShell :

```powershell
./scripts/setup.ps1
./scripts/dev.ps1
```

Sous Linux/macOS :

```bash
bash scripts/setup.sh
bash scripts/dev.sh
```

L'interface est ensuite disponible sur `http://localhost:5173`. Services locaux :

| Service | Port | Rôle |
|---|---:|---|
| web | 5173 | shell utilisateur |
| api | 8000 | projets, missions, droits et historique métier |
| event-service | 8001 | ingestion interne protégée ; temps réel utilisateur encore à livrer |
| provider-gateway | 8002 | frontière privée des providers, dont Hermes |

Copier les valeurs utiles de `.env.example` dans l'environnement du processus. Avant
le premier accès, générer au minimum un `ACP_BOOTSTRAP_TOKEN` long et aléatoire. Les
appels API/worker vers le gateway nécessitent aussi `ACP_GATEWAY_SERVICE_TOKEN` ;
l'ingestion d'événements utilise un `ACP_EVENT_SERVICE_TOKEN` distinct. Ne jamais
committer `.env`, une clé Hermes ou un jeton worker. Aucun secret par défaut n'est
fourni.

Les URL inter-services qui transportent ces Bearers doivent être des origines sans
userinfo, chemin, query ni fragment ; HTTP est accepté uniquement sur loopback et
HTTPS est obligatoire ailleurs.

Au premier affichage, le formulaire « Sécuriser le premier accès » consomme le jeton
de bootstrap et crée l'unique propriétaire initial. Les visites suivantes restaurent
la session ou affichent la connexion ; elles ne rouvrent pas l'inscription. En HTTP
local uniquement, `ACP_SESSION_COOKIE_SECURE=0` est nécessaire ; utiliser `1` derrière
HTTPS.

Le seed local reste un jeu de démonstration et `create_all()` ne remplace pas des
migrations de production. Un worker doit être enregistré séparément selon
[la procédure Windows](docs/workers/windows-worker.md). Son mode simulation termine
nominalement en `blocked` et ne peut jamais réussir. Le mode réel exige un argv, une
racine et un provider non simulé configurés localement ; le programme autorisé
conserve les droits OS du compte worker et n'est donc pas une sandbox pour du code
non fiable.

## CLI et missions

Après `setup`, activer l'environnement (`. .\.venv\Scripts\Activate.ps1` sous
PowerShell ou `source .venv/bin/activate` sous POSIX), ou appeler directement
`.venv\Scripts\acp.exe` / `.venv/bin/acp`. Sous WSL, les scripts utilisent
`.venv-wsl` afin de ne jamais mélanger les exécutables Linux et Windows ; activer
`source .venv-wsl/bin/activate`. La configuration/session WSL vit par défaut dans
`~/.config`, séparément de `%APPDATA%` côté Windows. Les commandes principales
utilisent la même API et le même modèle de session que le web ; chaque client ouvre
sa propre session :

```powershell
acp login
acp doctor
acp projects list
acp run --project <project-id> --goal "Vérifier le dépôt" `
  --expected "Rapport vérifiable" `
  --accept "La vérification termine avec le code 0"
acp runs watch <mission-id>
```

Quitter `runs watch` n'arrête pas la mission ; `acp runs stop <mission-id>` est une
action distincte. Voir [Missions, runner local et CLI](docs/missions-and-cli.md).

## Hermes

Version attendue : Hermes Agent `0.21.1` (`v2026.9.7`). Sur Hermes, activer l'API
Server et générer une clé :

```text
API_SERVER_ENABLED=true
API_SERVER_KEY=<secret>
```

Sur le provider-gateway :

```text
HERMES_BASE_URL=<URL joignable depuis le gateway>
HERMES_API_KEY=<même secret>
ACP_GATEWAY_SERVICE_TOKEN=<secret inter-services partagé avec API et worker>
```

L'URL locale native est généralement `http://127.0.0.1:8642`, mais elle n'est pas
un défaut valable entre conteneurs ou services Railway. Le provider reste donc
indisponible tant que l'URL et la clé ne sont pas configurées. Aucun basculement
automatique vers un provider payant ou un plan local n'a lieu.

## Bureau pixel historique

Le moteur, les scènes et les données existantes sont conservés. Ils sont hors du
parcours principal et chargés uniquement avec :

```text
http://localhost:5173/?legacy-office=1
```

ou au build avec `VITE_ACP_LEGACY_OFFICE=1`. Les assets LimeZu restent des achats
séparés et ne doivent pas être redistribués. Voir
[la documentation d'installation](docs/assets/limezu-installation.md).

## Vérifications

Commandes principales :

```powershell
npm exec tsc -- --noEmit -p apps/web/tsconfig.json
npm test --workspace @acp/web
npm test --workspace @acp/pixel-office-engine
npm run build:web
python -m pytest -q
python -m pytest -q apps/cli/tests
```

Les résultats réellement obtenus, l'environnement Python utilisé, les warnings et
les limites sont consignés dans [docs/acceptance-report.md](docs/acceptance-report.md).
Les tests Hermes, de conversation et de diagnostic utilisent un transport HTTP
simulé ; ils ne constituent pas une connexion à une instance Hermes réelle. La
reprise web actuelle repose sur un polling `GET`, pas sur un streaming SSE/WebSocket.

## Documentation

- [Audit de modernisation](docs/audit-modernisation.md)
- [Architecture et sources de vérité](docs/architecture.md)
- [Décisions de réutilisation](docs/reuse-decisions.md)
- [Système visuel](docs/design-system.md)
- [Intégration Hermes](docs/hermes-integration.md)
- [Missions, runner local et CLI](docs/missions-and-cli.md)
- [Sécurité](docs/security.md)
- [Centre MCP et skills — cible](docs/mcp-and-skills.md)
- [Studio en direct — cible](docs/live-studio.md)
- [Déploiement Railway](docs/deployment-railway.md)
- [Rapport d'acceptation](docs/acceptance-report.md)
- [État d'implémentation et reprise](docs/implementation-status.md)
