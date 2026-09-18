# État d'implémentation et reprise

Date d'état : 18 septembre 2026, Europe/Paris
Portée : Lot H `0.9.0` publié (PR #8, fusion `94ce876`, tag `v0.9.0`, CI verte
observée) ; ouverture du durcissement `0.9.1`. Le tag `v0.8.0` a été posé sur `e71ebf6`
le 18 septembre 2026.

## Résumé

La modernisation complète n'est pas terminée. Le Lot C livre la tranche mission :
ressource durable, tentatives explicites, arrêt et relance contrôlés, preuves,
validation technique, acceptation utilisateur, backend de processus local et CLI
`acp` utilisant la même API que le web.

Le Lot D livre la tranche extensions : coffre de secrets chiffrés à références,
politique de sortie réseau anti-SSRF, centre MCP versionné avec diagnostics HTTP et
`stdio` autorisés, bibliothèque de skills importés et relisibles, rattachements par
projet, révocation de bout en bout, import/export des configurations MCP, écrans web
et groupes CLI `acp secrets | mcp | skills`. Aucun serveur MCP réel, dépôt GitHub réel
ou runner distant réel n'a été contacté : les preuves reposent sur des transports et
programmes déterministes locaux.

Le Lot E livre la tranche observation et livrables : journal d'événements ordonné par
deux compteurs monotones, flux SSE authentifié par curseur servi par l'API métier,
reporter Playwright sans dépendance ni appel réseau, exécution de tests web sur un
runner authentifié, résultats de tests structurés, stockage privé de livrables adressé
par contenu avec liens signés bornés et révocables, Studio en lecture seule et onglet
« Livrables » de la bibliothèque, plus les commandes CLI correspondantes.
**Aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été exécuté**
pour cette version : le reporter est prouvé sur des objets Playwright synthétiques et
l'exécuteur du worker sur un programme déterministe. La reprise en main humaine du
navigateur n'est pas livrée et l'interface le dit.

Le Lot F livre la tranche routines : calendrier cron en heure locale IANA ou
intervalle, gestion explicite des bascules DST, matérialisation sans doublon, bail
singleton et fencing du planificateur, politiques de rattrapage et de concurrence,
déclenchements manuels et webhook entrant, budgets appliqués par mission/jour/provider,
saturation du stockage et boîte d'alertes in-app. Le web et `acp automations` utilisent
les mêmes contrats. Les détails et limites sont dans
[Automatisations, budgets et alertes](automations.md).

Le Lot G livre quatre briques opt-in et fermées par défaut : un paquet E2E Playwright
isolé, un aperçu de GLB v2 validés avec `@google/model-viewer`, un connecteur ComfyUI
privé au provider-gateway, et des exécuteurs Codex CLI / Claude Code raccordés à la
boucle worker. Le parcours shell/Studio a réussi dans un vrai Edge contre des services
locaux isolés. Aucun serveur ComfyUI, modèle 3D dans WebGL, CLI agent authentifié ni
chaîne reporter → worker avec médias réels n'a été exécuté en conditions réelles.

Le backend réel exécute uniquement un exécutable absolu via un argv fixe configuré
par l'opérateur. Il ne prend jamais une commande dans la mission, crée un cwd neuf,
transmet un snapshot borné, filtre l'environnement, borne le temps et les sorties,
et arrête l'arbre de processus lors d'un stop, timeout ou lease perdu. Il reste un
processus avec les droits OS du compte worker : ce n'est pas une sandbox pour du
code non fiable.

Aucune instance Hermes réelle, dépense externe, migration de production ou
déploiement n'a été lancé. Les preuves locales reposent sur des programmes et
transports déterministes de test.

## Réalisé et testé dans le Lot C

### Missions et tentatives

- création atomique d'une mission et de sa première tentative avec objectif,
  résultat attendu, critères, autonomie, ressources, budget et durée ;
- `Idempotency-Key` obligatoire pour créer, arrêter et relancer ; la clé de création
  est liée au principal et à l'empreinte du payload ;
- replay d'un arrêt lié à sa tentative d'origine, sans risque d'arrêter une relance
  ultérieure ;
- états `queued`, `preparing`, `running`, `waiting_approval`, `blocked`, `stopping`,
  `succeeded`, `failed`, `cancelled` et `interrupted` ;
- numéro de tentative et fencing token monotones ; ancien worker refusé lors d'un
  renew, PATCH ou événement ;
- succès accepté seulement avec validation technique `passed` et preuve structurée ;
- décision utilisateur séparée (`pending`, `accepted`, `rejected`), commentaires et
  relance possible après rejet explicite ;
- lecture directe d'une mission par identifiant de run pour les liens profonds ;
- worker simulé exclu des missions réelles.

### Backend worker local

- configuration fail-closed par `ACP_WORKER_RUNNER_ARGV_JSON` et
  `ACP_WORKER_RUN_ROOT` ; exécutable absolu et situé hors de la racine inscriptible ;
- enveloppe `acp.local-process.request.v1` et preuve
  `acp.local-process.evidence.v1` à champs structurés allowlistés ; stdout/stderr
  sont bornés et hachés, mais leur texte non expurgé peut contenir des secrets ;
- création exclusive d'un répertoire par tentative, aucun rejeu implicite d'un cwd
  existant et aucun shell ;
- environnement minimal et allowlisté, stdout/stderr lus en continu, captures
  bornées et SHA-256 de la totalité ;
- deadline de mission, timeout, arrêt explicite, perte de lease et fencing obsolète
  reliés à l'arrêt du groupe/arbre de processus ;
- sortie du parent détectée indépendamment des pipes hérités et succès refusé si le
  nettoyage de l'arbre ne peut pas être confirmé ;
- code de sortie nul insuffisant : l'évaluateur doit répondre explicitement
  `approved: true`, sinon l'état reste non réussi et la preuve technique est gardée ;
- mode non supervisé, listes d'actions non vides, ressources en écriture et provider
  `mock` refusés avant le spawn ; verdict lié au provider réel configuré ;
- `doctor` exige liveness API/gateway, authentification worker et readiness
  authentifiée du provider.

### Web et CLI synchronisés

- écran Missions relié à l'API, avec état d'exécution, validation technique,
  acceptation, critères, preuves, arrêt, relance et commentaires ;
- lien `/missions?run=<id>` qui ouvre la mission et la tentative demandées, y compris
  une tentative historique ;
- clé de création web conservée après un timeout afin qu'un nouvel essai logique ne
  duplique pas la mission ;
- CLI installable : `login`, `logout`, `doctor`, projets, chat, création/suivi/arrêt
  de missions, approbations, artefacts, workers, ouverture web et complétion shell ;
- JSON/NDJSON, codes de sortie stables et `Ctrl+C` sur `runs watch` sans arrêt
  implicite de la mission ;
- configuration CLI atomique, session liée à l'origine API, HTTPS obligatoire hors
  loopback et aucun Cookie/CSRF réutilisé après changement d'origine ;
- dans l'état historique du Lot C, commandes d'automatisations explicitement non
  supportées ; elles sont désormais livrées par le Lot F décrit plus bas.

## Réalisé et testé dans le Lot D

### Coffre de secrets et sorties réseau

- secrets chiffrés (Fernet) avec `key_id`, rotation de clé sans perte via
  `ACP_SECRETS_KEYS`, portées `platform`/`project`, révocation et `last_used_at` ;
  valeur jamais retournée par une route, un export, un événement ou le frontend ;
- coffre absent : état explicite `configured=false` et `503` sur les routes qui
  chiffrent ou déchiffrent, jamais de repli en clair ;
- politique de sortie appliquée côté serveur : `https` exigé hors allowlist, userinfo
  refusé, toutes les adresses résolues contrôlées (une seule bloquée suffit à
  refuser), adresse épinglée pendant la requête, redirections revalidées, corps borné,
  usage d'une allowlist privée audité.

### Centre MCP

- serveurs versionnés (révision immuable, empreinte, diff, risques), catalogue de
  trois entrées vérifiées sur documentation et jamais exécutées ;
- refus `422` d'une valeur littérale ressemblant à un secret, d'un paquet non épinglé,
  d'une commande relative ou d'une URL refusée par la politique ;
- diagnostic HTTP exécuté par l'API ; diagnostic `stdio` soumis à une autorisation
  explicite portant l'empreinte, exécuté par un runner authentifié doté de la capacité
  `mcp_stdio_probe`, avec lease, invalidation, expiration et refus hors lease ;
- expurgation des contenus renvoyés par le serveur sondé, appliquée par le runner et
  par l'API (`acp_contracts.redaction`) ;
- rattachements par projet limités à un sous-ensemble d'outils découverts, activation
  refusée sans découverte courante, désactivation réversible, révocation irréversible
  avec raison, rollback et historique conservé ;
- import Hermes/Claude/Codex avec aperçu normalisé et secrets masqués, export avec
  placeholders `${ACP_SECRET_…}` et notes de compatibilité partielle.

### Bibliothèque de skills et extensions

- import borné depuis un `SKILL.md` saisi, un dossier explicitement autorisé, une
  archive ZIP ou un commit GitHub épinglé ; traversées, liens et fichiers spéciaux
  refusés ;
- révisions avec manifeste SHA-256, frontmatter, licence, dépendances et contrôle
  automatique indicatif ; contenus affichés comme texte, jamais rendus ;
- approbation obligatoire quand une révision augmente la portée (script, réseau,
  permission) ; rattachement par projet, activation, rollback et révocation ;
- extensions résolues par projet (`GET /projects/{id}/extensions`) et instantané figé
  dans `meta["extensions"]` d'une mission : une révision ultérieure ne change pas une
  mission déjà démarrée ;
- lecture des skills et toolsets natifs Hermes dans Connexions, sans recopie dans le
  registre.

### Clôture d'arrêt du runner (correctif d'un défaut du Lot C)

- sous Windows, tout spawn du runner et de la sonde `stdio` est créé suspendu, affecté
  à un Job Object `KILL_ON_JOB_CLOSE` sans `BREAKAWAY_OK`, vérifié par `IsProcessInJob`
  puis repris : aucune instruction du programme ne s'exécute hors de sa clôture ;
- une affectation impossible devient `spawn_failed` / `job_assignment_failed`, jamais
  une exécution non bornée ;
- `process_tree_stopped` n'est vrai que si le job est vide **et** que la passe Toolhelp
  existante le confirme : la vérification native est conservée, pas remplacée ;
- ce correctif traite un défaut réel du Lot C : avec un lanceur d'environnement
  virtuel, un petit-fils survivait à l'arrêt et transformait un run réussi en
  `timed_out` / `output_stream_timeout` ;
- sur POSIX, le comportement est inchangé (`start_new_session` puis `killpg`).

## Réalisé et testé dans le Lot E

### Journal d'événements et flux authentifié

- `events` porte `schema_version`, `conversation_id`, `step_id`, `executor`,
  `emitted_by` et **deux compteurs monotones** alloués dans la transaction métier :
  `sequence` (par tentative, exposée comme `StreamEvent.sequence`) et `journal_seq`
  (le journal entier, curseur de la portée projet), chacun sous index unique partiel ;
- `GET /runs/{id}/events` et `GET /projects/{id}/events` rendent un `EventPage`
  (`next_cursor`, `has_more`, `retention_days`) ; une page ne dépasse jamais sa limite
  et `has_more` vaut exactement « il existe une ligne de rang supérieur » ;
- `GET /streams/runs/{id}` et `GET /streams/projects/{id}` servent du
  `text/event-stream` depuis l'**API métier**, avec reprise par `Last-Event-ID` ou
  `?after_seq=`, keep-alive `: ping`, rotation propre annoncée avec son curseur,
  limite de connexions par utilisateur et RBAC **revérifié à chaque page** ;
- le flux relit la base par curseur (interrogation bornée + réveil intra-processus) :
  la base est la seule source de vérité, donc une reconnexion ne duplique ni ne perd
  d'événement et plusieurs processus d'API peuvent servir la même tentative ;
- un événement écrit hors de `publish` — les producteurs du Lot C et les écritures
  d'audit MCP/skills/secrets/workers — reçoit ses numéros de façon transparente ; un
  test structurel interdit à tout autre module d'`acp_api` de construire un
  `EventModel` à la main ;
- aucun média dans un événement : le payload d'une pièce jointe ne porte que
  `artifact_id`, `content_type`, `size_bytes`, `sha256`, `stream_kind`.

### Livrables privés

- stockage adressé par contenu sur disque (`ACP_ARTIFACT_STORAGE_DIR`, clé
  `<sha256[0:2]>/<sha256>`), écriture atomique, nom d'origine jamais dans le chemin,
  derrière une interface `ArtifactStorage` prête pour un adaptateur objet non livré ;
- `POST /workers/{id}/artifacts/content` : identité worker vérifiée **avant** la
  lecture du corps, plafond par fichier et quota par tentative appliqués pendant le
  flux, idempotence par sha256 sur la même tentative ;
- `GET /artifacts`, `/artifacts/{id}`, `/artifacts/{id}/content` : lecture filtrée par
  les projets accessibles, support des requêtes `Range`, allowlist de types sans
  reniflage, `nosniff`, CSP `default-src 'none'; sandbox`, `private, no-store`, et
  `text/html` / `image/svg+xml` / archives jamais servis en ligne ;
- `POST /artifacts/{id}/link` et `DELETE /artifacts/links/{link_id}` : lien HMAC borné
  (≤ 900 s), lié à l'artefact et au demandeur, révocable, `503` explicite sans clé ;
- `python -m acp_api.retention` : purge à blanc par défaut, conservation des événements
  terminaux et des artefacts cités par une preuve de mission, comptage de références
  avant l'effacement d'un blob.

### Tests web structurés

- `packages/playwright-reporter` (`@acp/playwright-reporter`) : workspace npm **sans
  dépendance runtime**, NDJSON local dans `ACP_REPORT_FILE`, aucun appel réseau,
  statuts et `flaky` conservés distinctement, troncature à 8 000 caractères sans couper
  une paire de substituts UTF-16, séquences ANSI retirées ;
- `apps/worker/src/acp_worker/web_tests.py` : capacité `web_tests` désactivée par
  défaut, argv absolu et racine configurés par l'opérateur, lancement par
  `spawn_fenced_process` et arrêt par `terminate_process_tree`, arrêt non prouvé ⇒ pas
  de succès, NDJSON absent ou vide ⇒ échec explicite, pièce jointe hors du répertoire
  de sortie refusée, expurgation des messages et extraits, preuve `web_tests` sans
  image ;
- `apps/api/src/acp_api/testing_service.py` : ingestion idempotente sous identité
  worker, lease et fencing ; `test_runs` / `test_cases` ; événements `test.run.started`,
  `test.case.finished`, `test.run.finished` ; validation technique dérivée
  (`passed` seulement avec code de sortie nul, aucun `unexpected`/`interrupted`/
  `timedOut` et au moins un cas exécuté), jamais `succeeded` ;
- le verdict du serveur ne peut qu'**aggraver** celui du worker, et le code de sortie
  annoncé par le rapport ne peut jamais effacer celui mesuré.

### Web et CLI

- `studio-ui.ts` : bandeau de mode et de connexion en libellés textuels, chronologie
  par curseur, arbre des tests avec statuts distincts et étapes dépliables, dernière
  capture référencée par les pièces jointes, aperçus par lien signé, trace et rapport
  HTML en téléchargement explicite avec avertissement, **aucun bouton de prise de
  contrôle** ;
- `library-ui.ts` : route « Bibliothèque » à deux onglets, `Skills` (délégué tel quel
  au module du Lot D) et `Livrables` (filtres projet/mission/type, recherche, aperçu,
  téléchargement, métadonnées, provenance, taille, empreinte) ; aucun nouvel élément de
  navigation ;
- règle du Lot D conservée : client HTTP fourni par le shell, aucune lecture de
  `/auth/session`, purge d'état à la connexion et à la déconnexion — celle du Studio
  ferme aussi l'`EventSource` ;
- CLI : `acp runs events` (`--after-seq`, `--limit`, `--follow`, `--json`),
  `acp runs tests` (même dérivation que le serveur, code `4` si la validation est en
  échec), `acp artifacts list | get | link`, `acp open --run <id> --studio`.

## Réalisé et testé dans le Lot F

### Contrats, calendrier et persistance

- contrats Pydantic stricts et miroir TypeScript pour les calendriers, gabarits,
  routines, déclenchements, webhooks, budgets, consommations et alertes ; champs
  inconnus, booléens pris pour des nombres, dates naïves et valeurs non finies refusés ;
- cron à cinq champs en heure locale IANA, sémantique POSIX des jours, recherche bornée
  à quatre ans ; heure inexistante omise et première occurrence retenue pour une heure
  ambiguë ; intervalle fixe de 60 à 31 536 000 secondes ;
- tables et contraintes des routines, occurrences, rotations webhook, bail du
  planificateur, politiques/ledger budgétaires et alertes/préférences ; clés étrangères
  SQLite activées à chaque connexion ;
- upgrade SQLite transactionnel piloté par la parité du modèle pour les onze tables
  concernées par le Lot F : reconstruction des schémas partiels, préservation des
  index/triggers locaux, contrôle final des clés étrangères et annulation atomique de
  la reconstruction d'un ledger historique ambigu ; `create_all()` peut avoir créé
  auparavant de nouvelles tables vides ;
- `fire_key` déterministe et contrainte unique `(automation_id, fire_key)` vérifiées
  sous vraie concurrence sur une base SQLite fichier.

### Routes et planificateur

- API utilisateur pour créer, lister, lire, modifier, activer, suspendre et déclencher
  une routine, lire ses runs et son calendrier ; création et tir manuel idempotents,
  RBAC par projet et CSRF sur les mutations de session ;
- webhook entrant : secret client de 256 bits au minimum, empreinte seule persistée,
  journal de rotation sans secret, rotation idempotente, révocation et tir dédupliqué
  par `event_id` ;
- boucle worker persistante et routes internes de bail/tick/libération : bail singleton
  de 45 secondes, fencing monotone revérifié entre transactions, limite de tick bornée,
  rejeu sûr après réponse perdue et absence d'affamement par une routine invalide ;
- rattrapage `skip` ou `run_once`, historique des refus, plafond de 1 à 5 runs actifs,
  réconciliation des états terminaux et désactivation avec alerte après trois échecs
  consécutifs ; un succès remet le compteur à zéro.

### Budgets, stockage et alertes

- politique de projet : plafond journalier et par fournisseur, missions concurrentes,
  relances et plafond d'agents ; permis avant effet et rapport idempotent avec identité
  worker, lease et fence revérifiés ;
- application raccordée aux phases de planification, exécution et évaluation du worker,
  avec coût décimal, jetons et appels d'outils, distinction `unknown`/zéro,
  jour comptable figé au permis et agrégats par mission/jour/fournisseur ;
- fuseau comptable immuable après le premier permis, bornes communes Python/TypeScript/
  SQL et cache agrégé saturant plutôt que débordant ; ledger exact conservé ;
- dans l'état publié du Lot F, `max_spawned_agents_per_run` était seulement validé,
  persisté et affiché ; le Lot G limite l'exécution à une invocation CLI de premier niveau gérée
  par ACP, sans fan-out ni comptage des processus ou agents descendants ;
- saturation ou indisponibilité du stockage classée en `507`/`503`, alerte expurgée
  lorsque le projet et le run sont déjà résolus, réparation atomique d'un blob
  corrompu et quotas conservés sous concurrence ;
- boîte d'alertes durable, cause ouverte unique, escalade monotone, acquittement
  idempotent, préférences personnelles par projet ; canal in-app uniquement.

### Frontières worker et HTTP

- enrôlement worker fermé si l'API n'autorise pas exactement une portée : un projet
  précis ou le privilège global ; le client ne peut pas élargir cette portée ; les
  workers historiques sans portée restent en quarantaine ;
- claims de travail filtrés par projet avant verrou et capacité réservée atomiquement ;
  planificateur réservé aux workers globaux, sondes MCP ciblées au worker nommé et
  sondes non ciblées réservées à la portée globale ;
- corps HTTP borné à 1 Mio avant parsing, 32 Mio pour les sources de skills, et upload
  de livrable authentifié puis borné en flux ; webhook limité à 120 requêtes/minute par
  source TCP et processus, avec cache d'adresses lui-même borné.

### Web et CLI

- écran Automatisations à quatre vues : routines, calendrier, alertes et réglages ;
  création/modification, activation/suspension, tir manuel, historique, rotation du
  webhook avec confirmation, politiques et consommations budgétaires ;
- états de chargement/erreur séparés, listes bornées annoncées, mesure absente distincte
  de zéro, protection contre les réponses obsolètes lors d'un changement de projet ;
- proposition de routine préremplie depuis une mission réussie, techniquement validée
  et acceptée, mais toujours créée désactivée ;
- groupe `acp automations` complet avec JSON strict, gabarit fichier ou inline,
  intervalles normalisés, calendrier RFC 3339, codes de sortie et rejeu explicite des
  opérations incertaines ; secret webhook généré par défaut ou lu depuis fichier ou
  environnement, jamais accepté en argument clair.

## Réalisé et testé dans le Lot G

### Harnais E2E Playwright

- paquet autonome `e2e/`, hors workspaces npm, avec `@playwright/test` `1.63.0` et
  installation de Chromium séparée ; sans `ACP_E2E=1` exact, le lanceur sort
  `[E2E SKIPPED]` avant de résoudre Playwright ;
- configuration complète et bornée : origines web/API, confirmation exacte de
  l'origine web, compte de test et `run_id` existant ; HTTP distant, userinfo,
  sous-chemin, query, fragment et hôte d'écoute sont refusés ;
- parcours en lecture seule après l'unique `POST /auth/login` : `GET`/`HEAD`/`OPTIONS`
  seulement, shell, Missions et Studio de la tentative déclarée ; réponses réelles
  exigées, aucune interception substitutive ; chaque requête admise est envoyée une
  seule fois avec redirections et retries coupés, puis tout `3xx` est refusé avant
  remise de la réponse inchangée au navigateur ;
- trafic HTTP(S) et WebSocket limité aux deux origines au niveau du contexte navigateur,
  première requête d'une popup comprise ; toute nouvelle fenêtre est refusée, les
  service workers ainsi que `Worker`, `SharedWorker` et `EventSource` sont neutralisés,
  avec un seul worker Playwright, traces/vidéos coupées et capture seulement sur échec ;
  le Studio utilise donc son vrai polling HTTP, pas son flux SSE ;
- avant toute saisie d'identifiant sur deux origines, une vraie requête `OPTIONS` hors
  routage navigateur prouve le contrat CORS credentialed ; la réponse du `POST` réel est
  elle aussi contrôlée avant `fulfill`, et une seconde tentative de login est refusée ;
- job CI séparé, exécutable seulement via `workflow_dispatch` sur `refs/heads/main`
  avec `vars.ACP_E2E == '1'` au niveau dépôt ou organisation — la condition précède
  l'ouverture de l'environnement ; il cible ensuite `acp-e2e-staging`, à protéger dans
  GitHub par reviewer requis et branche de déploiement limitée à `main` avant d'y
  enregistrer les identifiants. Ces secrets ne sont injectés que dans l'étape de test,
  et le groupe de concurrence distingue un déclenchement manuel d'un push.
- canal navigateur strict `chromium`, `chrome` ou `msedge` et lanceur local
  `scripts/verify_live_studio_journey.py` : API/Vite, compte et mission temporaires ;
  preuve réellement passée avec Edge sans service tiers ni dépense.

### Livrables 3D et ComfyUI

- validation GLB 2 stricte au téléversement : type et extension cohérents, chunks
  JSON/BIN bornés et ordonnés, UTF-8/JSON strict, URI externes et décodeurs
  Draco/Meshopt/Basisu refusés ; mapping de `buffers[0]`, vues, alignements et strides
  vérifiés, accessors sparse refusés ; budgets cumulés sur vues, spans physiques et
  décodage ; marqueur réservé lié au sha256 du contenu ;
- images embarquées strictement PNG/JPEG/WebP avec source XOR, MIME/conteneur et en-têtes
  validés sans décompression ; dimension, pixels, octets compressés et estimation
  RGBA+mipmaps sont tous plafonnés avant le scellement ;
- seul un `.glb` scellé peut être annoncé et servi en aperçu ; `.gltf` et anciens GLB
  non scellés restent en téléchargement. `@google/model-viewer` `4.3.1` est importé à
  la demande, avec contrôles caméra et états accessibles, sans AR ni autorotation ;
- `purpose=preview` exige une `ACP_API_URL` explicite et une
  `ACP_ARTIFACT_PUBLIC_ORIGIN` valide, distincte de l'API et des origines CORS ; sinon
  `424` avant émission du jeton. `acp_api.preview:app` ne monte que santé et contenu
  signé d'aperçu, sans session, routes métier ou docs. Le téléchargement reste disponible ;
- les écritures d'artefact worker exigent le fence exact ; pour le multipart, lease et
  fence sont revérifiés sous verrou après lecture du corps et avant toute persistance ;
- connecteur ComfyUI derrière le Bearer gateway : diagnostic `/system_stats`, workflow
  JSON local fixe, prompt seul injecté, `/prompt` puis polling `/history/{id}` et
  téléchargement `/view` ;
- réponses et durées bornées, redirections/proxies ambiants coupés, HTTP limité au
  loopback, image PNG/JPEG/WebP vérifiée par type, extension et signature ; générations,
  waiters et cache LRU/TTL bornés séparément et en octets ; tombstone jusqu'à la TTL
  après toute soumission `/prompt` incertaine, mais idempotence process-local et non
  durable ; quarantaine avant toute nouvelle soumission, réconciliation ciblée de la
  file, suppression d'un prompt en attente connu et `/interrupt` uniquement sur une
  instance exclusive avec concurrence à un.

### Exécuteurs agents du worker

- capacités `codex_cli` et `claude_code` uniquement hors simulation et après opt-in
  complet : exécutable absolu, profil d'authentification séparé et mapping JSON de
  racines projet non chevauchantes ; aucune détection depuis le `PATH` ; une liste
  explicite et les capacités persistées sont revérifiées contre les backends actifs
  avant enregistrement, diagnostic, heartbeat ou claim ;
- une capacité agent exige un scope projet présent dans l'allowlist locale ; le scope
  global agent est refusé. Les capacités de mission génériques exigent le runner fixe ;
  `mcp_stdio_probe` exige en plus sa configuration stdio et, tant que les claims partagent
  la même liste, un runner local. Un scope hérité absent est refusé avant réseau ;
- mission supervisée, listes d'actions vides, exactement une ressource
  `project_workspace` du projet et exactement un CLI ; Codex suit `read`/`write`,
  Claude refuse l'écriture ;
- Codex lancé en JSON éphémère sans approbation, web, MCP, navigateur, plugins,
  mémoire, skills ni multi-agent ; Claude limité à `Read,Glob,Grep`, sans MCP,
  persistance ni commande slash ; il s'agit d'options demandées aux CLIs, pas d'une
  isolation OS créée par ACP ; prompt sur stdin et environnement minimal ;
- même clôture Job Object/session POSIX que le runner, deadline et drainage bornés ;
  le Job Object vérifie la vidange sous Windows, tandis que la limite POSIX décrite plus
  bas subsiste. JSONL strict (10 000 événements maximum), événement terminal de succès
  propre au CLI obligatoire et sortie 2 Mio par flux ; preuve persistée limitée au
  code, au nombre d'événements, aux tailles et sha256 ;
- permis de budget avant spawn et un appel d'outil rapporté. Une borne de coût ou de
  jetons exigée refuse l'effet, ces CLI n'offrant pas de limite dure fiable ;
- toute écriture Codex consomme sa deadline en attendant un verrou interprocessus dérivé
  de la racine canonique et adjacent au projet ; erreur, timeout ou annulation le
  libèrent lorsque le nettoyage est confirmé. Sinon, un marqueur `.poison` atomique
  interdit durablement toute nouvelle écriture jusqu'à inspection et levée manuelle.
  Ce verrou reste coopératif : les ACL du parent et la sémantique de verrouillage des
  partages réseau doivent être garanties, sinon chaque worker reçoit son worktree ;
- ACP lance au plus une invocation CLI de premier niveau ; `spawned_agents=1` ne compte
  pas les descendants, ce que `spawned_agents_scope=worker_managed_top_level_cli_only`
  rend explicite, et ne prouve donc pas le plafond global
  `max_spawned_agents_per_run`. Aucun fan-out dynamique n'est livré.
- la racine choisie fixe le cwd sans isoler les fichiers lisibles par le compte worker.
  L'identité des chemins n'étant pas épinglée entre validation et spawn, des projets
  non mutuellement fiables exigent des workers isolés, et les chemins doivent être
  protégés par des ACL d'opérateur.

## Hérité des Lots A et B

- shell moderne français, thèmes, responsive, états vides/erreur/hors ligne et
  pixel office historique désactivé par défaut ;
- bootstrap propriétaire unique, Argon2id, session opaque révocable/expirable,
  cookie `HttpOnly`, CSRF et rôles par projet ;
- onboarding personnel et conversations persistantes ;
- adaptateur Hermes `0.21.1` fondé sur `/health/detailed`, `/v1/capabilities` et
  `/v1/runs`, avec réponses strictes et frontière inter-services ;
- service d'événements protégé en ingestion et WebSocket anonyme fermé par défaut.

## Vérifications

### Référence publiée du Lot E

Les résultats détaillés sont consignés dans
[le rapport d'acceptation](acceptance-report.md). Le Lot E a été vérifié dans le
worktree `lot-e` sous Windows 10 Pro `10.0.19045`, Node.js `v24.19.0` et npm
`11.17.0`. Les suites Python ont été exécutées avec `.venv\Scripts\python.exe`, le
**lanceur d'environnement virtuel Windows** (Python `3.12.0`). Ce choix compte : sous
Windows, ce lanceur exécute l'interpréteur réel dans un processus enfant, la topologie
même que le correctif Job Object du Lot D devait couvrir et que l'exécution de tests
web réutilise.

La suite Python compte **1 627 tests réussis, 4 ignorés et 2 avertissements de
dépréciation connus** (`751` API, `223` worker, `365` CLI, `288` en contrats,
gateway et event-service). Le web compte **262 tests Vitest sur 17 fichiers**, le
reporter Playwright **59 tests** et le moteur legacy **74 tests**. Le typecheck
TypeScript, le build Vite et `scripts/check_version.py` (toutes les versions
publiables sur `0.6.0`) réussissent ; le build n'émet que l'avertissement attendu sur
la taille du chunk Phaser.

Dans cette référence historique du Lot E, les quatre tests ignorés sont des limites de
la machine, pas des opt-in : un contrôle
de permissions POSIX inapplicable sous Windows
(`apps/api/tests/test_artifacts_storage.py`) et trois tests de refus de lien
symbolique (`apps/worker/tests/test_web_tests.py`) que le compte de vérification ne
peut pas créer. **À cette révision, aucun opt-in Playwright réel n'existait encore.**

La référence publiée du scénario d'acceptation 7 a été rejouée contre des services
réellement démarrés — API métier dans son propre processus et serveur MCP Streamable
HTTP sur le bouclage — avec **24 étapes sur 24 réussies**. Son script est désormais
versionné (`scripts/verify_mcp_journey.py`). Aucun parcours navigateur réel n'était inclus.

Ces tests prouvent les invariants locaux. Ils ne prouvent pas un navigateur réel, une
exécution Playwright réelle, un serveur MCP tiers, un dépôt GitHub réel, une instance
Hermes, un fournisseur payant, PostgreSQL existant, une sandbox OS, un E2E navigateur,
ni un déploiement Railway. Le Lot E a ensuite été publié par la PR #5, fusion
`b7d8a44`, tag `v0.6.0`, après observation d'une CI verte.

### Vérification du Lot F publié

Les suites ciblées couvrent les contrats, la base, les routes, le planificateur, le
worker, les budgets, les alertes, le stockage, le CLI et les modules web du Lot F.
Le 14 septembre 2026, l'arbre final local a rendu **2 291 tests Python réussis, 7
ignorés et 2 avertissements connus** (`867/1` API, `253/3` worker, `430/3` CLI et
`741/0` pour contrats, base et services). Le web a rendu **295 tests sur 23 fichiers**,
le reporter **59** et le moteur legacy **74**. Le typecheck TypeScript, le build Vite
et `scripts/check_version.py` réussissent, avec tous les composants sur `0.7.0`. Les
quatre jobs CI Python 3.12 et Node 22 du dernier push et de la PR ont été observés
verts avant la fusion ; le tag distant a ensuite été vérifié sur `0b4d904`.

`scripts/verify_automation_journey.py` a rendu **62 étapes sur 62 réussies**. Il lance
une API réelle dans un processus séparé sur une base SQLite temporaire, vérifie la
provenance de ses imports, puis redémarre la même API de la portée worker globale à la
portée projet. Il rejoue les routes HTTP : création/rejeu/conflit, activation,
calendrier, bail et tick, tir manuel, webhook, historique, permis/usage de budget et
alerte. Il n'appelle ni Internet, ni Hermes, ni fournisseur payant et ne constitue pas
un E2E navigateur.

### Vérification locale finale du Lot G

La passe Python complète finale donne **2 498 réussis, 7 ignorés et 2 avertissements de
dépréciation connus** sous Python 3.12.0. Les validations JavaScript donnent **34 tests**
des garde-fous E2E, sortie par défaut `[E2E SKIPPED]`, **311 tests web sur 24 fichiers**,
**59 tests reporter** et **74 tests moteur**. Le typecheck TypeScript, le build Vite et
la synchronisation de version réussissent. Les suites ciblées finales donnent aussi
**263 tests API/worker réussis, 3 ignorés** pour le fencing, les livrables et l'aperçu,
ainsi que **62 tests ComfyUI**.

Le parcours automatisations réussit **62/62**. Le lanceur local reproductible démarre
l'API et Vite, initialise ses données par HTTP et réussit le parcours shell/Studio dans
un vrai Edge : **1 test en 11,6 s**. La commande Codex générée est acceptée par l'aide
du CLI installé ; ce contrôle de syntaxe n'a invoqué aucun modèle. Ces preuves locales
ne constituent ni un appel de service externe ni une validation de PostgreSQL/Railway.

## Réalisé, non testé en conditions réelles

- l'appel plan/évaluation passe par le provider-gateway et échoue fermé, mais aucune
  instance Hermes `0.21.1`, clé, modèle, mémoire ou outil réel n'a été utilisé ;
- le backend lance et arrête de vrais processus locaux dans les tests, y compris le
  chemin d'exécuteur agent raccordé, sans authentifier Codex/Claude ni effectuer
  d'effet sur un projet utilisateur ;
- le web et le CLI partagent les routes et contrats testés séparément, sans E2E
  navigateur → API → worker → Hermes ;
- la compatibilité locale SQLite est un upgrade ad hoc non versionné qui peut
  reconstruire des tables ; une sauvegarde préalable est requise. La migration d'une
  base PostgreSQL existante n'est pas fournie dans ce lot ;
- l'import d'un skill depuis GitHub, l'import d'archive et les refus de traversée sont
  prouvés sur transport simulé et sources locales : aucun dépôt ni archive tierce
  réelle n'a été téléchargée ;
- la sonde `stdio` est prouvée contre un serveur MCP déterministe écrit pour les tests,
  lancé par `sys.executable` sur la machine de vérification : aucun runner distant
  enrôlé, aucun serveur MCP tiers ;
- les écrans web du centre MCP et de la bibliothèque de skills sont couverts par des
  tests Vitest sur le DOM, pas par un parcours navigateur réel ;
- le chemin reporter/worker du Lot E reste prouvé sur des objets
  Playwright synthétiques et l'exécuteur du worker sur
  `apps/worker/tests/fake_playwright_runner.py`, un programme déterministe lancé par
  `sys.executable`. Le harnais E2E a ouvert le shell et le Studio dans un vrai Edge,
  mais n'a produit aucune capture, vidéo ou trace via la chaîne reporter/worker ;
- le validateur et le composant d'aperçu GLB sont testés sans rendu WebGL réel et sans
  origine d'aperçu déployée ;
- le connecteur ComfyUI est testé par transport HTTP simulé et n'est ni appelé contre
  un GPU réel ni raccordé au worker ou au stockage de livrables ;
- le Studio est couvert par Vitest et par le parcours Edge réel ; l'onglet
  « Livrables » reste sans parcours navigateur ;
- le flux SSE n'a été éprouvé que par un client de test ASGI : aucune coupure réseau
  réelle, aucun proxy intermédiaire, aucun `EventSource` de navigateur ;
- la purge de rétention est testée, mais n'a jamais été exécutée avec `--apply` sur des
  données d'exploitation, et aucun ordonnanceur ne la déclenche ;
- la migration additive de `events.sequence` et `events.journal_seq` n'est exercée que
  sur SQLite.

## Bloqué

Ces points ne dépendent pas d'un développement supplémentaire mais d'une ressource ou
d'une décision qui manque aujourd'hui.

- **Passage des scénarios 10, 11, 16 et 19 à « Accepté »** : le parcours navigateur
  shell/Studio existe, mais la chaîne reporter → worker avec médias réels, le rendu GLB
  et l'origine d'aperçu déployée manquent encore.
- **Origine d'aperçu séparée** : bloquée par l'absence d'un second domaine ou
  sous-domaine dédié. Tant que `ACP_ARTIFACT_PUBLIC_ORIGIN` est vide, la création d'un
  lien d'aperçu échoue en `424` avant jeton ; le téléchargement continue sur l'API.
- **Passage des scénarios 7 et 8 à « Accepté »** : bloqué par l'absence d'un serveur
  MCP tiers et d'un dépôt GitHub réel autorisés pour la vérification, et par le fait
  que le parcours versionné ne couvre que le transport `http`.
- **Vérification Hermes réelle** : bloquée par l'absence d'instance, de clé et de
  modèle ; toute la lecture native est prouvée sur transport simulé.
- **Vérification PostgreSQL, sauvegarde et restauration** : bloquée par l'absence d'une
  base existante et d'une procédure de migration versionnée. La migration des deux
  compteurs d'événements est propre à SQLite.

## Non configuré ou restant

- sandbox OS, utilisateur non privilégié dédié et politique réseau vérifiée : sous
  Windows, le Job Object livré au Lot D borne l'arbre de processus du runner et de la
  sonde `stdio`, mais il n'impose ni quota CPU/mémoire, ni politique réseau ; c'est
  une clôture d'arrêt, pas une isolation ;
- scope cgroup ou unité de service POSIX équivalente au Job Object Windows : sur
  POSIX, l'arrêt repose encore sur `start_new_session` + `killpg`, qu'un descendant
  peut quitter en changeant volontairement de session ;
- l'autorisation d'un lancement `stdio` est un objet propre au centre MCP
  (`mcp_probes.authorization`) : elle n'est **pas** reliée à `ApprovalModel` ni au
  circuit d'approbation des missions, et n'apparaît donc ni dans `/approvals` ni dans
  `acp approvals` ;
- endpoint worker d'approbation d'une action exacte et exécution sensible ;
- le contrôle automatique d'un skill est une heuristique explicitement indicative :
  aucun scan certifiant, aucune signature vérifiée, aucun bac à sable d'analyse ;
- aucune installation automatique côté Hermes : la plateforme **exporte** une
  configuration `mcp_servers` et des placeholders `ACP_SECRET_*` à appliquer
  manuellement ; aucune API HTTP d'Hermes 0.21.1 ne permet d'écrire cette
  configuration ;
- migrations PostgreSQL versionnées, rollback et restauration ;
- exécution Playwright réelle de la chaîne reporter → worker → API ; le harnais
  shell/Studio `ACP_E2E=1` a, lui, été exécuté dans Edge ;
- prise de contrôle humaine du navigateur : **non livrée** ; le
  Studio est en lecture seule et l'interface le dit ;
- diffusion d'images de session en direct : la plateforme ne produit aucune image ; les
  seules images disponibles sont les captures téléversées par le lanceur de tests ;
- trace viewer intégré : une trace Playwright se télécharge et s'ouvre hors de la
  plateforme ;
- déploiement d'une origine d'aperçu séparée, adaptateur de stockage objet distant et
  purge de rétention planifiée ;
- raccordement ComfyUI aux missions, persistance de sa file/idempotence et versement
  automatique de ses images comme livrables ;
- courtier d'appels d'outils MCP pendant une mission : le Lot D livre le registre, la
  découverte, l'autorisation et la résolution des extensions, pas l'appel à
  l'exécution ;
- gestion des clés du coffre par un KMS/HSM et rotation planifiée ; les secrets de
  service (`HERMES_API_KEY`, Bearers inter-services) restent hors coffre ;
- livraison de notifications hors application : aucun courriel, SMS, push système ou
  webhook sortant n'est implémenté ;
- fan-out et comptabilité multi-agent dynamiques : le Lot G borne uniquement à une
  l'invocation CLI de premier niveau gérée par ACP, sans observer ses descendants ;
- exécution réelle de ComfyUI, du rendu 3D, de Codex/Claude et du harnais E2E sur staging ;
- Hermes réel opt-in, Railway et observabilité de production.

## Lots

| Lot | Capacité verticale | État |
|---|---|---|
| A | audit, shell moderne, Hermes Runs strict et exécution fail-closed | **Publié : PR #1, tag `v0.2.0`** |
| B | accès propriétaire, RBAC, onboarding et conversation persistante | **Publié : PR #2, tag `v0.3.0`** |
| C | runner réel contrôlé, missions, preuves, validations et CLI | **Publié : PR #3, tag `v0.4.0`** |
| D | MCP/skills versionnés, coffre de secrets, diagnostics et révocation | **Publié : PR #4, tag `v0.5.0` ; aucun serveur MCP tiers contacté** |
| E | événements durables, flux authentifié, Playwright, livrables privés et Studio | **Publié : PR #5, fusion `b7d8a44`, tag `v0.6.0`, CI verte observée avant fusion ; aucun navigateur réel lancé, aucun test Playwright réel exécuté** |
| F | automatisations, calendrier Europe/Paris, budgets et alertes | **Publié : PR #6, fusion `0b4d904`, tag `v0.7.0`, CI verte observée avant fusion** |
| G | médias/3D, exécuteurs complémentaires et durcissement | **Publié : socle `004a4f8`, PR #7 de durcissement fusionnée en `e71ebf6`, tag `v0.8.0`, CI verte observée** |
| H | migrations, Railway, sauvegarde-restauration et validation finale | **Publié : PR #8, fusion `94ce876`, tag `v0.9.0`, CI verte observée ; durcissement `0.9.1` en cours** |

## Reprise : livrer le Lot H

Ordre de reprise pour la personne ou l'agent qui prend la suite.

1. **Verser dans le dépôt un parcours de bout en bout du Lot E**, comme
   `scripts/verify_mcp_journey.py` l'a fait pour le scénario 7 : services démarrés,
   worker authentifié, ingestion d'une exécution de tests, flux SSE consommé avec
   reprise par curseur, téléchargement d'un livrable par lien signé puis révocation.
   Sans lui, aucun scénario de ce lot ne peut passer à « Accepté ».
2. **Déployer une origine d'aperçu séparée**, y router les contenus, puis vérifier un
   vrai GLB dans Chromium. Sans cela, l'API doit continuer à répondre `424` aux aperçus.
3. **Éprouver les intégrations externes sous autorisation explicite** : ComfyUI local,
   puis une mission Codex ou Claude sur un dépôt jetable, avec budgets et profils dédiés.
4. **Livrer le Lot H** : PostgreSQL et migrations versionnées, Railway, sauvegarde,
   restauration et validation finale. SQLite `create_all()` et son upgrade ad hoc ne
   sont pas une migration de production.

Deux dettes du Lot D restent ouvertes et n'ont pas été traitées par le Lot F :
raccorder un serveur MCP tiers et un dépôt GitHub réel, et construire le courtier
d'appels d'outils MCP à l'exécution d'une mission. Le sort de l'autorisation `stdio`
(circuit propre au centre MCP ou circuit d'approbation des missions) reste lui aussi à
trancher.
