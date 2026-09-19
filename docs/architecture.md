# Architecture cible

Statut : décision adoptée pour la modernisation 2026.
Date d'état : 14 septembre 2026 — version publiée `0.8.0` (Lot G).
Produit : Agent Company Platform, espace personnel par défaut.

Le schéma principal de ce document reste la cible. L'état concret des Lots C à G
utilise SQLAlchemy avec SQLite par défaut et `create_all()` complété d'un upgrade
additif ad hoc ; PostgreSQL, migrations versionnées, outbox et déploiement ne sont pas
encore validés. Les Lots E à G livrent en revanche le **stockage privé des
livrables** sur disque local, le **flux utilisateur authentifié par curseur**, les
**routines planifiées**, leur ledger budgétaire, l'**aperçu GLB**, le connecteur
**ComfyUI** et les exécuteurs agents bornés : ces lignes ne sont plus des cibles.

## Décision

La plateforme conserve son interface `apps/web` et son API métier. Hermes Agent est
un service externe versionné, joint uniquement côté serveur par un adaptateur de
runtime. Le dashboard Hermes reste une console native facultative ; il n'est ni
embarqué par iframe ni forké pour devenir l'interface principale.

```text
Navigateur ───────┐
                  ├── API Agent Company Platform ── base plateforme
CLI acp ──────────┘          │            │
                             │            ├── stockage privé des livrables
                             │            └── journal durable / outbox
                             │
                             ├── provider-gateway ── Hermes / ComfyUI optionnel
                             │      sessions, runs, SSE, stop, approvals
                             │
                             └── planificateur ── runners enrôlés
                                    runner fixe / Codex CLI / Claude Code
```

## Options évaluées

| Option | Atouts | Limites | Décision |
|---|---|---|---|
| Étendre le dashboard Hermes | Réutilise chat, profils, skills et MCP natifs ; maintenance UI réduite | Ne porte pas naturellement les projets, droits, preuves, runners et données existantes de la plateforme ; le plugin hériterait fortement du cycle Hermes | Console d'administration facultative seulement |
| Conserver `apps/web` avec adaptateur | Préserve les données et contrats, autorise une isolation par projet, un web et un CLI identiques, et un historique de preuves indépendant | Nécessite de traduire et persister explicitement les sessions/runs/événements | **Retenue** |

Cette décision évite deux administrations concurrentes : les réglages natifs Hermes
peuvent être consultés ou modifiés via son API lorsque la capacité existe ; la
plateforme ne maintient pas une copie silencieuse de ces réglages.

## Tranche verticale livrée au Lot C

```text
Navigateur
  │ cookie de session HttpOnly + CSRF sur mutations
  ▼
API plateforme ── utilisateurs/sessions/memberships/projets
  │              └─ conversations/tours/idempotence/résultats
  │ Bearer ACP_GATEWAY_SERVICE_TOKEN
  ▼
provider-gateway ── Bearer HERMES_API_KEY ── Hermes Agent 0.21.1

API plateforme ── Bearer ACP_EVENT_SERVICE_TOKEN ── event-service
                                                     └─ WebSocket anonyme fermé
```

L'accès initial est un bootstrap unique protégé par un secret d'environnement. Il
crée le propriétaire et une session révocable ; il ne crée pas une inscription
publique. L'identité métier provient exclusivement de cette session serveur, jamais
d'un `X-User-Id` fourni par le client. Les identités et jetons des workers restent
une frontière distincte.

Le parcours personnel crée au besoin une organisation et un workspace `personal`
internes, puis n'expose que le projet dans l'expérience courante. Leur conservation
évite de casser le modèle historique sans imposer sa complexité à l'utilisateur.

Le Lot C ajoute une ressource mission au-dessus de `tasks` et une tentative
distincte au-dessus de `task_runs`. Son état évolue, mais son identité, son numéro,
son appartenance et son fencing token ne sont jamais réutilisés. La création persiste
mission et première tentative dans la même transaction. Chaque relance obtient un
numéro et un fencing token strictement supérieurs ; les commandes de création, arrêt
et relance sont dédupliquées afin qu'un replay réseau ne vise jamais une autre
tentative.

## Tranche verticale livrée au Lot E

```text
Navigateur / CLI
  │ session HttpOnly + CSRF sur mutations
  ▼
API métier ── events (sequence par tentative + journal_seq global)
  │         ├─ test_runs / test_cases (résultat structuré par tentative)
  │         ├─ artifacts (métadonnées) ── stockage local adressé par contenu
  │         └─ artifact_links (liens signés bornés et révocables)
  │
  ├── GET /runs/{id}/events, GET /projects/{id}/events      page par curseur
  ├── GET /streams/runs/{id}, GET /streams/projects/{id}    SSE authentifié
  ├── GET /artifacts, /artifacts/{id}, /artifacts/{id}/content
  └── GET /runs/{id}/test-run, GET /test-runs/{id}
        ▲
        │ POST /workers/{id}/artifacts/content   (multipart, worker + lease + fence)
        │ POST /workers/{id}/test-runs           (ingestion NDJSON normalisé)
        │
   worker authentifié ── argv Playwright de l'opérateur + @acp/playwright-reporter
                          (NDJSON local ; le test ne reçoit aucun credential)
```

Trois décisions structurent cette tranche.

1. **Le flux utilisateur est servi par l'API métier, pas par `apps/event-service`.**
   L'API détient la base, les sessions et le RBAC ; le service d'événements reste un
   relais interne sans accès aux données. Le WebSocket anonyme de ce service reste
   fermé par défaut et n'a pas été rouvert.
2. **Le curseur est un compteur monotone attribué au commit de la transaction
   métier**, pas un horodatage. `events.sequence` ordonne une tentative,
   `events.journal_seq` ordonne le journal entier. Une horloge ne donne pas d'ordre
   total — la granularité réelle mesurée sur la machine de vérification est
   d'environ 1,5 ms — et une pagination sur une valeur non unique perd des lignes ou
   dépasse sa limite. Le flux « tail » la base par curseur (interrogation bornée +
   réveil intra-processus) : durable, multi-processus, sans courtier externe.
   Depuis 0.9.1, les numéros sont attribués **au commit**, sous un verrou consultatif
   PostgreSQL tenu jusqu'à la fin de ce commit : c'est le dernier verrou de la
   transaction, si bien qu'il ne forme plus de cycle avec un verrou de ligne, et le
   journal visible reste un préfixe sans trou, dans l'ordre des commits.
3. **Le reporter de tests n'émet pas vers le réseau.** Il écrit un NDJSON local ; le
   worker authentifié l'ingère, téléverse les pièces jointes et publie les événements
   avec sa propre identité. Aucun média ne transite dans un événement : le payload
   ne porte qu'une référence d'artefact, une empreinte, un type MIME et une taille.

La prise de contrôle humaine du navigateur n'est **pas** livrée. Le Studio reste en
lecture seule ; voir [docs/live-studio.md](live-studio.md) pour l'état détaillé.

## Tranche verticale livrée au Lot F

```text
Web / CLI ── session + CSRF + RBAC ── API métier
                                         │
                                         ├─ automations / automation_runs
                                         ├─ scheduler_leases
                                         ├─ project_budget_policies / budget_usage_reports
                                         └─ alerts / notification_preferences
                                                ▲
                                                │ Bearer worker + fences
                                  workers persistants en concurrence
```

Le gabarit d'une routine produit une mission normale : le planificateur n'a pas de
machine d'états parallèle. L'API reste l'autorité du calendrier, du curseur
`next_run_at`, de la concurrence et de la matérialisation. Les workers ne lisent
jamais la base. Un worker est enrôlé soit pour un projet précis, soit avec un privilège
global explicite choisi côté serveur ; seuls les workers globaux concourent au bail
singleton de 45 secondes et appellent le tick avec le `fencing_token` obtenu.

Le calendrier cron est calculé en heure locale à partir de la base IANA. Une heure
inexistante est omise et seule la première occurrence d'une heure ambiguë est retenue.
L'intervalle est au contraire une durée fixe. Chaque tir nominal reçoit une
`fire_key` déterministe et une contrainte unique SQL garantit une seule ligne et une
seule mission sous concurrence ou après rejeu.

Les budgets sont des décisions transactionnelles, pas des indicateurs décoratifs :
le worker réserve un permis avant les phases consommatrices et rapporte ensuite la
mesure. Les plafonds de mission, de journée et de fournisseur s'appliquent sur un
ledger idempotent. Le fuseau comptable est figé dès sa première ligne ; le cache
agrégé sature à la capacité commune Python/SQL/JavaScript tandis que le ledger exact
reste la preuve. Dans le Lot F publié, `max_spawned_agents_per_run` reste seulement
contractuel et persisté. Le Lot G ajoute un point de spawn qui lance au plus une
invocation CLI de premier niveau ; les descendants du binaire ne sont ni interdits ni
comptés, donc le plafond global n'est pas démontré et aucun fan-out dynamique n'est livré.

Les alertes restent un état métier in-app. Une cause ouverte est unique par projet,
sa sévérité ne peut que monter, et les préférences personnelles filtrent la boîte sans
altérer l'alerte canonique. Le webhook du Lot F est un déclencheur **entrant** ; il ne
constitue pas un canal de notification sortant. Voir
[Automatisations, budgets et alertes](automations.md).

## Tranche verticale livrée au Lot G

```text
Studio / Bibliothèque ── POST link?purpose=preview ── API artefacts
                                                        │ jeton signé
                                                        ▼
                                              acp_api.preview:app
                                              origine séparée, sans session
                                                        │
                                              image / vidéo / model-viewer

API / worker ── Bearer inter-services ── provider-gateway ── ComfyUI optionnel

mission (une capacité + un project_workspace)
             └── worker fencé ── Codex CLI ou Claude Code
```

L'aperçu n'est jamais un repli implicite. `purpose=preview` exige une `ACP_API_URL`
explicite et une origine canonique distincte de l'API et des origines web ; sinon l'API
répond `424` avant le jeton. L'application ASGI minimale d'aperçu partage base et
stockage, mais ne monte que santé et contenu signé `purpose=preview`, sans session ni
route métier. Seul
un `.glb` v2 auto-contenu, validé au téléversement et scellé par son sha256, atteint
`@google/model-viewer`. Les `.gltf`, lignes historiques non scellées, URI externes et
extensions de décodeur restent en téléchargement ou sont refusés.

ComfyUI est un connecteur média interne, pas un orchestrateur : l'opérateur choisit le
workflow, le nœud prompt et la sortie ; la requête ne fournit que le texte. Les appels
et corps sont bornés, le résultat est vérifié, mais l'idempotence reste en mémoire et
l'image n'est pas encore versée dans les artefacts d'une mission. Une exécution
incertaine ferme les nouvelles soumissions jusqu'à réconciliation ciblée ;
`/interrupt` reste réservé à une instance explicitement exclusive et sérialisée.

Les CLIs agents sont activés seulement par chemins absolus, profils d'authentification
séparés et racines projet allowlistées. Une mission supervisée sélectionne exactement
un CLI et un `project_workspace`. Codex peut suivre un accès `write`; Claude reste en
lecture seule selon les options demandées. Le prompt passe par stdin, les fonctions
web/MCP/multi-agent connues sont demandées désactivées et la preuve ne conserve que
tailles, empreintes et nombre d'événements. Ces options ne créent pas une sandbox ACP :
le compte worker conserve ses droits fichiers/réseau et ses descendants restent hors
de la métrique d'agents.

## Sources de vérité

| Domaine | Autorité | Données de rapprochement |
|---|---|---|
| Identité, droits, projets | plateforme | `user_id`, `project_id` |
| Mission, état accepté, budget, approbation | plateforme | `task_id`, `task_run_id`, `attempt_id` |
| Preuves, artefacts, tests | plateforme et moteur ayant produit la preuve | checksum, code de sortie, reporter, provenance |
| Session, profil, modèle, skills et toolsets natifs Hermes | Hermes ; la plateforme les lit sans les recopier | `hermes_session_id`, profil et version détectée |
| Serveur MCP, skill importé, révision, rattachement projet | plateforme | `mcp_server_id`, `skill_id`, `revision_id`, `project_id` |
| Valeur d'un secret | plateforme, chiffrée au repos et jamais servie | `secret_id`, `key_id` |
| Exécution Hermes | Hermes pendant le run ; plateforme pour l'historique durable | `hermes_run_id`, idempotency key |
| Conversation plateforme et droits associés | plateforme | `conversation_id`, `project_id`, `created_by_user_id`, `provider_session_id` |
| Processus d'un runner | runner pendant l'exécution ; plateforme pour la réservation | `worker_id`, lease, fencing token |
| Routine et occurrence nominale | plateforme | `automation_id`, `next_run_at`, `fire_key` |
| Politique et ledger budgétaires | plateforme ; fournisseur pour les mesures rapportées | `permit_id`, `report_id`, jour comptable, provider |
| Alerte et préférences personnelles | plateforme | cause dédupliquée par projet, `user_id` pour les préférences |
| Workflow, modèles et file ComfyUI | opérateur / service ComfyUI ; la plateforme ne garde que sa configuration locale | workflow épinglé par chemin, `prompt_id`, empreinte de requête process-local |
| Processus Codex/Claude et profil d'authentification | worker pendant la tentative | capacité, `project_id`, racine allowlistée, code de sortie et empreintes |

Un identifiant Hermes ou runner n'accorde jamais à lui seul un accès à un projet.
Le mapping appartient à la plateforme et est contrôlé côté serveur.

## Responsabilités cibles et état

Les responsabilités ci-dessous définissent la cible. Au Lot C, les contrôles métier,
missions, polling et frontières de services sont livrés ; le Lot D ajoute le coffre
de secrets, la politique de sortie réseau et les registres MCP/skills ; le Lot E
ajoute le scope de flux et de fichiers, les URLs privées signées et le flux SSE
authentifié ; le Lot F ajoute routines, budgets et alertes. L'outbox et la
normalisation des événements SSE **d'Hermes** restent explicitement à réaliser.

### Interface web et CLI

- utilisent la même API et les mêmes règles d'autorisation ;
- affichent `inconnu` lorsque la mesure n'existe pas ;
- reprennent par lecture `GET` identifiée sans relancer une mission ; depuis le
  Lot E, ils consomment aussi un flux SSE authentifié et reprennent par curseur
  (`Last-Event-ID` ou `?after_seq=`), avec un état de connexion explicite
  (`connected`, `reconnecting`, `polling`, `offline`) et un repli automatique sur
  l'interrogation `GET` ; une reconnexion ne relance jamais une mission ;
- ne reçoivent jamais une clé de service Hermes ou worker ;
- gèrent les routines avec la même API : le web affiche calendrier, alertes et
  consommation, tandis que le CLI expose des commandes scriptables et des clés de
  rejeu explicites ;
- proposent le pixel office uniquement par un drapeau legacy désactivé par défaut.

### API métier

- authentifie le propriétaire/opérateur/lecteur ;
- applique le scope projet sur chaque lecture, écriture, flux et fichier ;
- valide la machine d'états, les approbations, budgets et idempotency keys ;
- persiste l'événement et son effet métier de façon transactionnelle ;
- calcule les occurrences, arbitre les `fire_key`, les baux du planificateur et les
  permis budgétaires ; aucune décision de calendrier ou de budget ne dépend de l'état
  mémoire d'un worker ;
- délivre des URLs de fichier privées et bornées.

### Extensions : MCP, skills et secrets (Lot D)

- le registre plateforme conserve les serveurs MCP et les skills sous forme de
  révisions immuables, avec empreinte, découverte, risques et rattachements par
  projet ; une mission fige les extensions résolues à son démarrage ;
- une configuration ne contient jamais une valeur de secret, seulement une référence ;
  la valeur est chiffrée au repos et déchiffrée uniquement pour un appel autorisé ;
- la découverte d'un serveur `http` est exécutée par l'API à travers un client à
  destination épinglée et politique de sortie stricte ; celle d'un serveur `stdio`
  est exécutée par un runner autorisé, après une autorisation explicite portant
  l'empreinte exacte de la révision ;
- ce que renvoie un serveur MCP est du contenu non fiable : borné, expurgé des
  valeurs injectées, affiché comme donnée et sans effet sur une politique ;
- Hermes reste l'autorité de ses skills et toolsets natifs : ils sont lus et affichés,
  jamais recopiés dans le registre.

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

### Conversation du Lot B

La conversation générale est privée à son créateur, sous réserve du pouvoir
d'administration du propriétaire global. Une conversation de projet hérite des
memberships du projet : lecture pour un lecteur autorisé, écriture pour un membre ou
propriétaire. Ces contrôles sont recalculés côté serveur à chaque requête.

Le `POST` d'un tour persiste d'abord le contenu, le `client_request_id` et une clé
d'idempotence. Le gateway admet ensuite un Run Hermes et retourne immédiatement son
identifiant. Les `GET` suivants lisent un seul snapshot du Run et mettent à jour la
réponse persistée. Cette reprise par polling survit à un rechargement de page, mais
ne remplace ni un flux d'événements durable ni une preuve de reprise après incident
sur une instance Hermes réelle.

### Runners

- s'enrôlent avec une identité révocable et se connectent en sortie ;
- annoncent des capacités vérifiées et une concurrence bornée ;
- reçoivent uniquement un snapshot de mission autorisé et un lease lié à une
  tentative ;
- le backend local du Lot C exécute un argv configuré par l'opérateur, jamais une
  commande issue de la mission, sans interpolation shell, dans un cwd neuf avec un
  environnement, une durée et des captures bornés ;
- la sonde MCP `stdio` du Lot D suit les mêmes règles : capacité désactivée par
  défaut, allowlist locale d'exécutables absolus, aucun héritage des variables du
  worker, et expurgation des valeurs injectées avant tout retour à l'API ;
- l'exécution de tests web du Lot E suit les mêmes règles : capacité `web_tests`
  désactivée par défaut, argv absolu et racine de projet configurés par l'opérateur,
  fichier de rapport NDJSON imposé, aucun credential de la plateforme remis au
  processus de test, pièces jointes refusées hors du répertoire de sortie de la
  tentative, et expurgation des messages et extraits avant envoi à l'API. Le runner et
  les workspaces racine n'installent jamais Playwright ; seul le paquet E2E isolé du
  Lot G porte sa propre dépendance, installée explicitement ;
- depuis le Lot F, le processus worker persistant concourt aussi au bail du
  planificateur et appelle ses ticks authentifiés ; le worker ponctuel `--once` n'en
  démarre pas la boucle. Le fence du planificateur est distinct du fence d'une
  tentative et les deux sont vérifiés par l'API ;
- avant chaque phase consommatrice raccordée, le worker demande un permis budgétaire
  puis rapporte la consommation avec un identifiant stable ; un refus ou une mesure
  inconnue échoue fermé selon le verdict serveur ;
- depuis le Lot G, `codex_cli` et `claude_code` ne sont annoncés qu'après opt-in
  complet. Une mission supervisée les sélectionne exclusivement avec une seule racine
  `project_workspace` allowlistée ; Codex peut recevoir l'écriture explicite, Claude
  reçoit des outils de lecture, et tout second CLI géré par ACP est refusé. Le worker
  ne bloque ni ne compte les processus ou agents descendants du binaire ;
- sous Windows, tout processus lancé — mission comme sonde — est créé suspendu puis
  affecté à un Job Object `KILL_ON_JOB_CLOSE` avant d'exécuter la moindre instruction :
  l'arrêt d'un arbre ne dépend plus d'une filiation observable, qu'un lanceur
  intermédiaire casse. Une affectation impossible échoue fermé ;
- publient preuves et événements uniquement pour le run loué.

Le processus local conserve les droits OS et la politique réseau du compte worker :
son cwd dédié n'isole pas les autres fichiers accessibles, et le Job Object est une clôture d'arrêt, pas une
limite de ressources. Les autonomies que ce backend ne sait pas
garantir sont refusées avant spawn. La plateforme ne monte pas elle-même le socket
Docker, mais le backend ne peut pas garantir son absence si le compte ou l'hôte le
rend déjà accessible ; l'opérateur doit l'isoler avant toute charge non fiable.

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
- validation technique (`pending`, `passed`, `failed`) ;
- acceptation utilisateur (`pending`, `accepted`, `rejected`).

Une simulation, une sortie vide, un évaluateur indisponible ou un JSON invalide ne
peut jamais produire `succeeded`.

## Événements durables

Chaque événement porte depuis le Lot E : `schema_version`, id, séquence monotone par
tentative, compteur monotone du journal, horodatage, projet, conversation, tâche,
tentative, étape, exécuteur (`platform`, `worker:<id>`, `playwright`, `hermes`),
émetteur (`api`, `worker`, `reporter`), type et payload autorisé. Les médias sont
stockés hors du flux et référencés par un artefact : `artifact_id`, `content_type`,
`size_bytes`, `sha256`, `stream_kind`.

Les deux compteurs sont alloués **dans la transaction métier** qui écrit l'événement,
avec réessai borné sur collision d'index unique. Ils définissent deux espaces de
curseurs disjoints, que le client ne mélange jamais : la portée tentative
(`/runs/{id}/events`, `/streams/runs/{id}`) pagine sur `sequence`, la portée projet
(`/projects/{id}/events`, `/streams/projects/{id}`) sur `journal_seq`. Une ligne
historique sans numéro est exclue de la page plutôt que de la faire échouer ; la
migration additive les numérote dans leur ordre d'insertion.

Le flux utilisateur relit la base par curseur au lieu de dépendre d'un relais : la
base est la seule source de vérité, donc une reconnexion ne duplique ni ne perd
d'événement, et plusieurs processus d'API peuvent servir la même tentative. Un hub
local ne transporte que des numéros de séquence, jamais des données.

Le Lot H ajoute une **outbox transactionnelle** pour la diffusion vers le service
d'événements, distincte de ce flux. Quand `ACP_EVENT_RELAY_ENABLED` vaut exactement
`1`, chaque écriture du journal insère dans la même transaction une ligne
`event_outbox` ; un processus séparé, `python -m acp_api.outbox_relay --follow`,
livre ces lignes dans l'ordre du journal et reprend là où il s'est arrêté après une
coupure. La sémantique est **au moins une fois**, jamais exactement une fois : le
service d'événements déduplique par identifiant dans une fenêtre bornée en mémoire,
qu'un redémarrage vide. Une ligne qui échoue `ACP_OUTBOX_MAX_ATTEMPTS` fois devient
une lettre morte, listée par `--list-dead` et rejouable par `--requeue-dead` ; la
purge de rétention n'efface jamais un événement dont la livraison est encore due.
Le relais doit tourner en **une seule réplique** : deux relais ne livrent jamais la
même ligne, mais l'ordre entre eux n'est pas garanti. Sans la variable, le
comportement historique (relais direct, sans reprise) est conservé.

`forward_event` continue de recopier l'événement vers `apps/event-service` en
best effort, pour les consommateurs internes historiques. L'ingestion de ce service
exige toujours un Bearer interne, et son WebSocket navigateur anonyme reste fermé par
défaut : le Lot E ne l'a pas rouvert, il a livré une voie authentifiée ailleurs. Le
drapeau de réactivation porte toujours le nom
`ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET` et reste réservé au développement local.

## Livrables et résultats de tests

Les livrables sont adressés par contenu sur disque (`ACP_ARTIFACT_STORAGE_DIR`, clé
`<sha256[0:2]>/<sha256>`), derrière une interface `ArtifactStorage` prévue pour
accueillir un adaptateur objet **non livré dans ce lot**. Le nom d'origine d'un
fichier n'entre jamais dans un chemin. Le contenu n'est servi qu'à un membre du projet
ou via un lien signé borné et révocable ; un type actif (`text/html`,
`image/svg+xml`, archive) n'est jamais servi en ligne, et le type est déterminé par
une allowlist serveur sans reniflage.

Depuis le Lot G, un `.glb` n'entre dans cette allowlist qu'après validation structurelle
GLB 2 au téléversement et scellement lié au sha256. Le stockage vérifie l'empreinte à
l'écriture mais n'est pas re-haché à chaque `Range` ; son intégrité après ingestion
reste une responsabilité opérationnelle. La route d'aperçu exige une origine séparée
et une origine API explicite avant de signer, puis vérifie que le jeton HMAC v2, lié à
`purpose=preview`, arrive réellement sur cette origine ; `.gltf` et tout GLB historique
non scellé ne sont jamais rendus. Les sessions et liens de téléchargement restent
forcés en pièce jointe.

Les écritures d'artefact venant d'un worker exigent en outre le fencing token exact de
la tentative. Pour un corps multipart, le lease et le fence sont contrôlés une première
fois puis revérifiés sous verrou après réception : un worker remplacé pendant le flux ne
peut ni créer le blob ni la ligne de métadonnées.

Un résultat d'exécution de tests est une ressource propre (`test_runs`, `test_cases`)
rattachée à une tentative, avec une exécution par tentative et par runner. Les statuts
`passed`, `failed`, `timedOut`, `skipped`, `interrupted` et le caractère `flaky` sont
conservés distinctement. La validation technique en est dérivée par le serveur ; elle
ne peut jamais valoir `succeeded` : conclure une tentative reste la décision du Lot C,
et l'acceptation utilisateur reste séparée.

## Déploiement

Hermes et la plateforme sont des services distincts et peuvent partager un réseau
privé, jamais un volume implicite. PostgreSQL conserve le métier ; Hermes possède son
propre état persistant ; un stockage privé reçoit les livrables. Les runners ne
tournent pas dans le serveur de contrôle par défaut.

Au Lot G ce stockage est toujours un **répertoire local**
(`ACP_ARTIFACT_STORAGE_DIR`) : sur un
hébergeur, il doit pointer vers un volume persistant, sans quoi les blobs disparaissent
au redéploiement alors que la base continue de les référencer. Une origine d'aperçu
séparée (`ACP_ARTIFACT_PUBLIC_ORIGIN`) est prévue par le code mais n'est configurée
nulle part aujourd'hui. Le processus `acp_api.preview:app` est livré, mais le domaine,
TLS et le partage de stockage restent à déployer : tant qu'ils ne le sont pas, toute
demande `purpose=preview` échoue en `424` avant création du jeton. Les téléchargements restent
servis par l'API, mais aucun contenu n'est promu en aperçu même origine.

Voir `docs/deployment-railway.md` pour l'état réellement livré et les actions restant
à vérifier avant une mise en production.
