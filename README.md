# Agent Company Platform

Poste de travail personnel pour organiser des projets et des missions, raccorder
Hermes Agent et, à terme, piloter des runners et outils spécialisés depuis le web et
un CLI commun.

La modernisation est engagée par tranches. Le Lot C ajoute aux fondations sécurisées
et aux conversations du Lot B une ressource mission durable, des tentatives
clôturées par fencing token, un backend de processus local configuré et le CLI
`acp`. Le Lot D y ajoute les extensions contrôlées : coffre de secrets chiffrés,
politique de sortie anti-SSRF, centre MCP versionné avec diagnostics autorisés,
bibliothèque de skills relisibles et révocation de bout en bout. Le Lot E y ajoute
l'observation et les livrables : journal d'événements ordonné, flux temps réel
authentifié avec reprise par curseur, reporter Playwright, exécution de tests web sur
un runner authentifié, résultats de tests structurés, stockage privé de livrables avec
liens signés, Studio en lecture seule et bibliothèque de livrables. Le Lot F ajoute
les routines planifiées, le calendrier IANA, un planificateur avec bail et fencing,
les budgets réellement appliqués, la détection de saturation, les alertes in-app et
les surfaces web/CLI correspondantes. Le Lot G ajoute un parcours E2E Playwright
strictement opt-in, l'aperçu de GLB validés sur une origine séparée, un connecteur
ComfyUI privé et deux exécuteurs worker explicites pour Codex CLI et Claude Code.

Une instance Hermes réelle, un serveur MCP tiers et une isolation OS du runner ne sont
toujours pas validés. Le harnais E2E a été exécuté localement dans un vrai Edge contre
une API et un serveur Vite isolés ; il prouve le shell et le Studio en lecture, pas la
chaîne reporter → worker, un rendu GLB WebGL ni une reprise en main humaine.
PostgreSQL, Railway et les sauvegardes restent au Lot H. Le détail exact se trouve dans
[l'état d'implémentation](docs/implementation-status.md).

Version publiée : **0.8.0** (Lot G). Son socle a été intégré sur `main` au commit
`004a4f8`, puis durci et publié par la PR
[#7](https://github.com/Paul-Berdier/agent-company-platform/pull/7) et le tag annoté
`v0.8.0`, après observation d'une CI verte. Les changements sont décrits dans
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
- routines créées désactivées, cron en heure locale ou intervalle, fuseau IANA,
  politiques de rattrapage, déclenchements manuel et webhook entrant, et calendrier
  exposant ensemble l'instant UTC, l'heure locale et son décalage ;
- planificateur porté uniquement par un worker au privilège global explicite, élu par
  un bail singleton de 45 s
  et protégé par un fencing token ; clé de tir unique en base, rejeu sans seconde
  mission, limite de concurrence et désactivation après trois échecs consécutifs ;
- budgets par mission, journée et fournisseur avec permis avant effet, rapports
  idempotents et valeurs inconnues distinctes de zéro ; l'exécuteur Lot G lance au plus
  une invocation CLI de premier niveau par tentative, sans compter ses descendants ni
  prétendre démontrer `max_spawned_agents_per_run` globalement ;
- alertes durables dédupliquées et à sévérité monotone pour les budgets, les routines
  et la saturation du stockage ; préférences personnelles et canal in-app uniquement ;
- worker réel opt-in exécutant exclusivement un argv local configuré, sans shell,
  dans un cwd neuf, avec environnement/captures/timeout bornés, arrêt de l'arbre de
  processus et verdict fail-closed ; ce backend n'accepte que les missions
  supervisées dont les trois listes d'actions sont vides et les ressources en
  lecture seule ;
- exécuteurs Codex CLI et Claude Code raccordés à la boucle réelle du worker : opt-in
  par chemins absolus, profils d'authentification séparés, racines projet allowlistées,
  mission supervisée et une seule invocation CLI fencée de premier niveau ; Codex reçoit
  le mode lecture/écriture déclaré, Claude des outils de lecture, sans isolation OS
  supplémentaire fournie par ACP ; les capacités persistées sont revérifiées contre le
  backend actif avant tout heartbeat/claim, et les écritures Codex visant une même racine
  sont sérialisées par un verrou interprocessus coopératif adjacent au projet ; un
  nettoyage incertain publie une quarantaine durable, jamais levée automatiquement ;
- clôture d'arrêt Windows : tout processus lancé par le runner, sonde MCP `stdio`
  comprise, est enfermé dès sa création dans un Job Object ; plus aucun descendant ne
  survit à une tentative, même derrière un lanceur (`.venv`, `npx.cmd`, `uvx`), et une
  affectation impossible échoue fermé au lieu de s'exécuter hors clôture ;
- CLI `acp` connecté à la même API pour l'accès, les projets, conversations,
  missions, runs, approbations, artefacts, workers, secrets, serveurs MCP et skills,
  avec JSON et codes de sortie ;
- coffre de secrets chiffrés à références : portées plateforme ou projet, rotation de
  clé, révocation, et aucune valeur renvoyée par l'API, un export, un événement ou le
  navigateur ;
- centre MCP : catalogue vérifié, import Hermes/Claude/Codex, révisions immuables,
  diagnostic HTTP exécuté par la plateforme, diagnostic `stdio` lancé uniquement après
  autorisation explicite sur un runner désigné, sélection des outils par projet,
  activation, rollback et révocation auditée ;
- sorties réseau de l'API contrôlées côté serveur : bouclage, réseaux privés,
  métadonnée cloud et équivalents IPv6 bloqués, adresse épinglée, redirections
  revalidées et usage d'une allowlist privée audité ;
- bibliothèque de skills : import borné (SKILL.md, dossier autorisé, archive, commit
  GitHub épinglé), relecture des fichiers comme texte, dépendances, contrôle
  automatique indicatif, approbation d'une portée accrue, activation par projet et
  révocation ;
- extensions résolues par projet et figées dans l'instantané d'une mission ;
- provider Hermes `0.21.1` via `/health/detailed`, `/v1/capabilities` et
  `/v1/runs` ;
- diagnostic Hermes typé visible dans Connexions, sans clé dans le navigateur ;
- surface métier du provider-gateway privée derrière un Bearer inter-services ;
  ingestion du service d'événements protégée et WebSocket anonyme fermé par défaut ;
- terminaison nominale d'une simulation worker en `blocked` (ou `failed` si sa
  préparation échoue), jamais présentée comme une exécution réussie ;
- refus d'un succès de run sans validation technique `passed` et preuve ;
- journal d'événements durable et ordonné : deux compteurs monotones alloués dans la
  transaction métier, pages par curseur sans perte ni doublon, et aucun média dans un
  événement (référence d'artefact, empreinte, type et taille seulement) ;
- flux temps réel **authentifié** servi par l'API métier (`GET /streams/runs/{id}`,
  `GET /streams/projects/{id}`), avec reprise par `Last-Event-ID` ou `?after_seq=`,
  keep-alive, rotation annoncée, limite de connexions par utilisateur et RBAC
  revérifié à chaque page ; côté client, les états `connected`, `reconnecting`,
  `polling` et `offline` sont affichés tels quels et une coupure n'invente aucun état ;
- reporter Playwright `@acp/playwright-reporter` sans dépendance ni appel réseau : il
  écrit un NDJSON local, et c'est le worker authentifié qui l'ingère ; les statuts
  `passed`, `failed`, `timedOut`, `skipped`, `interrupted` et `flaky` restent
  distincts ;
- paquet E2E Playwright isolé des workspaces, qui ne charge aucun navigateur sans
  `ACP_E2E=1` exact ; le parcours réel se connecte, ouvre Missions puis le Studio d'une
  tentative existante, avec trafic limité aux origines web/API déclarées ; chaque
  requête HTTP réelle est non retentée, ne suit aucune redirection et tout `3xx` est
  refusé avant d'atteindre le navigateur. `Worker`, `SharedWorker` et `EventSource`
  sont neutralisés dans cette preuve, qui exerce donc le vrai repli polling du Studio ;
  Playwright `1.63.0` accepte un canal explicite `chromium`, `chrome` ou `msedge`, et le
  lanceur local reproductible a réussi avec Edge contre de vrais services isolés ;
- exécution de tests web sur un runner opt-in : argv absolu configuré par l'opérateur,
  aucun credential de la plateforme remis au processus de test, clôture d'arrêt Job
  Object, rapport vide ou arrêt d'arbre non prouvé ⇒ échec explicite, jamais un succès ;
- livrables privés adressés par contenu : téléversement worker idempotent par sha256
  avec plafond et quota, téléchargement par session ou par lien signé borné et
  révocable, `Range` supporté, et HTML/SVG/archives jamais servis en ligne ; chaque
  écriture worker exige le fencing token courant, revérifié sous verrou après lecture
  du corps afin qu'un worker remplacé ne puisse pas publier tardivement ;
- aperçu 3D à la demande avec `@google/model-viewer` pour les seuls `.glb` v2
  auto-contenus, cohérents et scellés par leur sha256 ; `.gltf`, URI externes, chunks
  inconnus et extensions nécessitant un décodeur externe restent refusés ou en
  téléchargement ; buffers, vues, accessors/strides et images sont validés sous des
  budgets mémoire/pixels avant que le fichier puisse atteindre le moteur WebGL ;
- connecteur ComfyUI optionnel derrière le Bearer inter-services du gateway : workflow
  JSON fixé par l'opérateur, prompt seul injecté, appels `/prompt`, `/history` et
  `/view` bornés, réponse PNG/JPEG/WebP vérifiée, concurrence/cache mémoire bornés et
  tombstone après toute soumission `/prompt` incertaine ; une exécution distante
  incertaine place le connecteur en quarantaine, avec suppression ciblée d'un prompt en
  file et interruption globale seulement sur une instance explicitement exclusive ;
- Studio en lecture seule dans le détail d'une mission (`/missions?run=<id>&vue=studio`)
  et onglet « Livrables » de la bibliothèque ;
- commandes `acp runs events`, `acp runs tests`, `acp artifacts list | get | link` et
  `acp open --run <id> --studio`, plus le groupe complet `acp automations` ;
- bureau pixel historique préservé mais non chargé par défaut.

Ce qui ne fonctionne pas encore est visible comme `Non configuré` et recensé dans
[le rapport d'acceptation](docs/acceptance-report.md). En particulier : aucune
capture ni trace produite par la chaîne reporter → worker dans un vrai navigateur,
aucun rendu GLB WebGL réel, aucune reprise en main humaine, et aucune origine d'aperçu
déployée. Une demande d'aperçu échoue donc explicitement en `424`, sans repli sur
l'origine de l'API ; le téléchargement reste disponible. Le stockage d'artefacts reste
local et aucun adaptateur objet externe n'a été éprouvé. Le projet n'est pas prêt à
être exposé sur Internet.

## Architecture

```text
Web (Vite/TypeScript) ─┐
                      ├── API métier (FastAPI) ── base plateforme
CLI acp ───────────────┘         │
                                ├── provider-gateway ── Hermes / ComfyUI séparés
                                ├── service d'événements
                                └── workers enrôlés ── runner fixe ou CLI agent opt-in
                                      └── bail du planificateur de routines
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
| api | 8000 | projets, missions, droits, historique métier, **flux SSE utilisateur et livrables privés** |
| event-service | 8001 | relais interne protégé ; ce n'est pas la voie temps réel utilisateur |
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

Pour utiliser le coffre de secrets et le centre MCP, définir `ACP_SECRETS_KEYS` avec
au moins une clé Fernet (`python -m acp_api.secrets_vault generate-key` ; la première
clé chiffre, les suivantes permettent la rotation). Sans clé, l'état est annoncé
`non configuré` au lieu d'un stockage en clair. Les autres variables du Lot D —
allowlist de sortie, stockage et sources de skills, sonde MCP stdio du worker — sont
documentées dans `.env.example` et dans
[docs/mcp-and-skills.md](docs/mcp-and-skills.md).

Pour les liens de téléchargement signés, définir `ACP_ARTIFACT_SIGNING_KEYS`
(`python -m acp_api.signing generate-key` ; même discipline de rotation par liste).
Sans clé, la création d'un lien répond `503` explicite et le téléchargement par session
reste possible. Avant d'exposer le Studio sur un réseau, définir explicitement
`ACP_API_URL` et `ACP_ARTIFACT_PUBLIC_ORIGIN`, cette dernière avec une origine HTTPS
distincte de l'API et du shell : tant qu'une de ces valeurs est vide ou invalide, la
création d'un lien d'aperçu répond `424` avant d'émettre le jeton. Les autres
variables du Lot E — flux SSE, rétention, stockage et quotas de livrables, tests web du
worker — sont documentées dans `.env.example` et dans
[docs/live-studio.md](docs/live-studio.md).

Au premier affichage, le formulaire « Sécuriser le premier accès » consomme le jeton
de bootstrap et crée l'unique propriétaire initial. Les visites suivantes restaurent
la session ou affichent la connexion ; elles ne rouvrent pas l'inscription. En HTTP
local uniquement, `ACP_SESSION_COOKIE_SECURE=0` est nécessaire ; utiliser `1` derrière
HTTPS.

Le seed local reste un jeu de démonstration et `create_all()` ne remplace pas des
migrations de production. Un worker doit être enregistré séparément selon
[la procédure Windows](docs/workers/windows-worker.md). Son mode simulation termine
nominalement en `blocked` et ne peut jamais réussir. Le mode réel exige un argv, une
racine et un provider non simulé lorsqu'il utilise le runner fixe ; le programme autorisé
conserve les droits OS du compte worker et n'est donc pas une sandbox pour du code
non fiable.

Le runner fixe n'est plus l'unique backend réel : un worker peut aussi activer Codex
CLI ou Claude Code par une configuration locale complète. Voir
[les exécuteurs locaux](docs/providers-local-executors.md) ; aucune découverte fortuite
depuis le `PATH` n'active ces capacités. L'enregistrement et chaque démarrage refusent
également une capacité agent explicite ou persistée si son backend local correspondant
n'est plus complètement configuré. Les capacités agent exigent un scope projet dont la
racine est allowlistée ; elles sont refusées en scope global tant que le claim ne sait
pas filtrer cette allowlist locale.

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
acp automations list --project <project-id>
acp automations calendar --project <project-id>
```

Quitter `runs watch` n'arrête pas la mission ; `acp runs stop <mission-id>` est une
action distincte. Une routine naît désactivée ; sa création puis son activation sont
deux gestes. Voir [Missions, runner local et CLI](docs/missions-and-cli.md) et
[Automatisations, budgets et alertes](docs/automations.md).

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
./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
npm run typecheck --workspace @acp/web
npm test --workspace @acp/web
npm test --workspace @acp/playwright-reporter
npm run test:e2e:unit
npm test --workspace @acp/pixel-office-engine
npm run build:web
./.venv/Scripts/python.exe scripts/check_version.py
# opt-in explicite, avec Chromium installé ou ACP_E2E_BROWSER_CHANNEL=msedge
$env:ACP_E2E="1"; ./.venv/Scripts/python.exe scripts/verify_live_studio_journey.py
```

Sous Windows, appeler l'interpréteur de l'environnement virtuel
(`./.venv/Scripts/python.exe`) plutôt que le `python` du `PATH` : c'est celui avec
lequel les résultats publiés ont été obtenus.

Pour la version publiée `0.6.0`, les résultats obtenus le 13 septembre 2026 sur la
machine de vérification (Windows 10 Pro `10.0.19045`, Python `3.12.0`, Node
`v24.19.0`, npm `11.17.0`) étaient : **1 627 tests Python réussis et 4 ignorés**,
**262 tests web**, **59 tests du reporter**, **74 tests du moteur legacy** ; typecheck,
build et `check_version.py` réussis. La CI de sa PR #5 a été observée verte avant
fusion. Ces nombres décrivent le Lot E publié, pas l'arbre de travail du Lot F.

Pour la version publiée `0.7.0` du Lot F, vérifiée le 14 septembre 2026 dans le même
environnement, le relevé global est : **2 291 tests Python réussis, 7 ignorés et 2
avertissements connus**, **295 tests web sur 23 fichiers**, **59 tests du reporter** et
**74 tests du moteur legacy**. Le typecheck TypeScript, le build Vite,
`scripts/check_version.py` et le parcours d'automatisation **62/62** réussissent. Les
quatre jobs Python 3.12 et Node 22 déclenchés par le dernier push et la PR ont été
observés verts avant la fusion ; le tag annoté distant `v0.7.0` pointe sur `0b4d904`.

Pour la version publiée `0.8.0` du Lot G, vérifiée le 14 septembre 2026 avec Python
`3.12.0`, Node `v24.19.0` et npm `11.17.0`, la passe globale donne **2 498 tests Python
réussis, 7 ignorés et 2 avertissements connus**. Les suites JavaScript donnent **311
tests web sur 24 fichiers**, **59 tests du reporter**, **74 tests du moteur** et **34
tests des garde-fous E2E**. Le typecheck, le build Vite, la synchronisation de version
et le parcours d'automatisation **62/62** réussissent également. Enfin, le parcours
shell/Studio opt-in a réussi dans un vrai Edge : **1 test en 11,6 s**.

Les suites déterministes ne lancent aucun navigateur. Le parcours réel du paquet isolé
`e2e/` reste désactivé tant que `ACP_E2E` ne vaut pas exactement `1`. Le script
`scripts/verify_live_studio_journey.py` crée une API, un shell, un compte et une mission
temporaires sur le bouclage, puis exécute ce parcours ; il a réussi avec le canal
`msedge` pendant la validation du Lot G. Une cible de staging existante reste également
possible avec les variables détaillées dans [e2e/README.md](e2e/README.md).

Un parcours de bout en bout, hors intégration continue, démarre l'API et un vrai
serveur MCP local puis rejoue l'ajout, le diagnostic, le rattachement, l'activation,
l'isolation entre projets, l'export et la révocation :

```powershell
./.venv/Scripts/python.exe scripts/verify_mcp_journey.py
./.venv/Scripts/python.exe scripts/verify_automation_journey.py
```

Ces parcours n'effectuent aucun appel sortant vers Internet et n'utilisent aucune
donnée réelle. Celui des automatisations démarre l'API sur une base SQLite temporaire
et a rendu **62 étapes sur 62 réussies** le 14 septembre 2026 ; il n'appelle ni
Hermes, ni fournisseur payant, ni navigateur.

Les résultats réellement obtenus, l'environnement Python utilisé, les warnings et
les limites sont consignés dans [docs/acceptance-report.md](docs/acceptance-report.md).
Les tests Hermes, de conversation et de diagnostic utilisent un transport HTTP
simulé ; ils ne constituent pas une connexion à une instance Hermes réelle. Depuis le
Lot E, le suivi d'une tentative repose sur un flux SSE authentifié avec reprise par
curseur, avec repli automatique sur l'interrogation `GET` ; les conversations, elles,
reprennent toujours par polling `GET`.

## Documentation

- [Audit de modernisation](docs/audit-modernisation.md)
- [Architecture et sources de vérité](docs/architecture.md)
- [Décisions de réutilisation](docs/reuse-decisions.md)
- [Système visuel](docs/design-system.md)
- [Intégration Hermes](docs/hermes-integration.md)
- [Missions, runner local et CLI](docs/missions-and-cli.md)
- [Automatisations, budgets et alertes](docs/automations.md)
- [Centre MCP et bibliothèque de skills](docs/mcp-and-skills.md)
- [Studio, journal d'événements, tests web et livrables](docs/live-studio.md)
- [Médias, aperçu 3D et ComfyUI](docs/media-and-3d.md)
- [Exécuteurs locaux Codex CLI et Claude Code](docs/providers-local-executors.md)
- [Parcours E2E Playwright réel, opt-in](e2e/README.md)
- [CLI `acp` — référence des commandes](apps/cli/README.md)
- [Worker Windows distant](docs/workers/windows-worker.md)
- [Contrat du runner worker](apps/worker/RUNNER.md)
- [Sécurité](docs/security.md)
- [Modèle de menace par actif](docs/security/threat-model.md)
- [Déploiement Railway](docs/deployment-railway.md)
- [Rapport d'acceptation](docs/acceptance-report.md)
- [État d'implémentation et reprise](docs/implementation-status.md)
