# Studio en direct : journal, tests et livrables

Date d'état : 14 septembre 2026 — base `0.6.0` (Lot E), complétée par le Lot G
`0.8.0` publié.
Statut : module livré et couvert par des tests déterministes ; le harnais E2E opt-in a
réussi dans un vrai Edge contre une API et un Vite locaux isolés. La chaîne
reporter → worker, les captures/vidéos/traces réelles et le rendu WebGL d'un GLB ne
sont pas prouvés par ce parcours de lecture.

Ce document décrit ce qui est **réellement dans le dépôt**, pas une architecture cible.
Les capacités absentes sont nommées comme absentes.

## Ce que le Studio est, et ce qu'il n'est pas

Le Studio montre, pour **une tentative** (`task_run_id`), le journal d'événements
ordonné, les résultats de tests structurés, les pièces jointes produites par
l'exécution et la dernière capture référencée par ces pièces jointes. Il ne pilote
rien : c'est une vue en lecture seule.

Il **n'est pas** un flux vidéo de navigateur. Aucune image de session n'est produite
par la plateforme : les seules images affichables sont des captures téléversées comme
pièces jointes par le lanceur de tests. Sans exécution de tests, le panneau d'image
affiche explicitement qu'aucune capture n'a été reçue plutôt que d'inventer un état.

## Chaîne livrée

```text
Runner de l'opérateur                    Plateforme
  argv Playwright configuré
  + reporter @acp/playwright-reporter
        │ écrit un NDJSON local (ACP_REPORT_FILE)
        ▼
  worker authentifié (web_tests.py)
        │ POST /workers/{id}/artifacts/content   (multipart + fencing token)
        │ POST /workers/{id}/test-runs           (ingestion NDJSON normalisé)
        ▼
  API métier ── events (sequence + journal_seq) ── test_runs / test_cases
        │                                       └── artifacts (blobs sha256 sur disque)
        ├── GET /runs/{id}/events   (page par curseur)
        ├── GET /streams/runs/{id}  (SSE authentifié par session)
        ├── GET /artifacts/{id}/content  (session ou lien de téléchargement)
        ├── origine séparée acp_api.preview:app (lien d'aperçu uniquement)
        └── GET /runs/{id}/test-run
                   │
                   ├── Studio web (/missions?run=<id>&vue=studio)
                   └── CLI : acp runs events / runs tests / artifacts / open --studio
```

Le processus de test ne reçoit **jamais** un credential de la plateforme. Le reporter
n'effectue aucun appel réseau : il écrit un fichier local, et c'est le worker
authentifié qui ingère ce fichier avec sa propre identité.

## Réalisé et vérifié

Vérifié en lisant le code cité et en exécutant les suites (chiffres au §
« Vérification », et dans [le rapport d'acceptation](acceptance-report.md)).

### Journal d'événements ordonné et durable

- `events` porte deux compteurs monotones distincts, tous deux alloués dans la
  transaction métier (`apps/api/src/acp_api/events_bus.py`) :
  - `sequence`, séquence **par tentative**, exposée comme `StreamEvent.sequence` ;
  - `journal_seq`, compteur **global du journal**, curseur de la portée projet.
- La portée projet ne pagine plus sur l'horloge. La granularité réelle de l'horloge
  sur la machine de vérification est d'environ 1,5 ms : des écritures successives
  partageaient couramment un horodatage, une page pouvait alors dépasser sa limite
  annoncée ou avancer le curseur au-delà de lignes jamais rendues. Les deux portées
  filtrent désormais strictement après un compteur à ordre total
  (`apps/api/src/acp_api/streams.py`).
- Un événement écrit sans passer par `publish` — les producteurs du Lot C
  (`routers/work.py`, `routers/missions.py`, `routers/platform.py`, `routers/crud.py`,
  `routers/secrets.py`, `routers/workers.py`, `mcp/service.py`, `skills/service.py`)
  — reçoit ses numéros de façon transparente : il entre dans la page de tentative et
  dans la page projet. Un test structurel interdit à tout autre module d'`acp_api` de
  construire un `EventModel` à la main.
- Aucun média ne transite dans un événement. Le `payload` d'un événement de pièce
  jointe ne porte qu'une référence : `artifact_id`, `content_type`, `size_bytes`,
  `sha256`, `stream_kind`.

### Flux authentifié par curseur

- `GET /streams/runs/{run_id}` et `GET /streams/projects/{project_id}` servent du
  `text/event-stream` depuis l'**API métier**, avec la session utilisateur et le RBAC
  du projet — pas depuis `apps/event-service`, qui reste un relais interne sans accès
  aux données.
- Reprise par `Last-Event-ID` (prioritaire) ou `?after_seq=`. Le flux relit la base
  par curseur : interrogation bornée par `ACP_STREAM_POLL_INTERVAL_MS` (défaut
  400 ms, latence nominale annoncée), réveillée plus tôt par un hub local qui ne
  transporte que des numéros de séquence. La base reste la seule source de vérité,
  donc une reconnexion ne duplique ni ne perd d'événement, et plusieurs processus
  d'API peuvent servir la même tentative.
- Commentaire keep-alive `: ping` toutes les `ACP_STREAM_KEEPALIVE_SECONDS`
  (défaut 15 s) ; rotation propre après `ACP_STREAM_MAX_SECONDS` (défaut 900 s) avec
  un événement nommé `acp.stream.rotate` portant le curseur, pour que le client se
  reconnecte sans trou. `ACP_STREAM_MAX_CONNECTIONS_PER_USER` borne le nombre de
  connexions simultanées (défaut 4).
- Le RBAC résolu à l'ouverture est revérifié à chaque page : une révocation de session
  ou une perte de membership ferme la connexion au plus tard à l'interrogation
  suivante, avec un événement `acp.stream.closed`.
- En-têtes : `Cache-Control: no-store`, `X-Accel-Buffering: no`.
- Côté web, `apps/web/src/events-api.ts` expose un état de connexion explicite —
  `connected`, `reconnecting`, `polling`, `offline` — avec reconnexion exponentielle
  bornée, déduplication par séquence (et par identifiant pour les lignes sans
  séquence) et bascule automatique en interrogation `GET` après trois échecs
  consécutifs. Une coupure n'invente aucun état.

### Reporter Playwright

- `packages/playwright-reporter` est un workspace npm **sans dépendance runtime** :
  il implémente l'interface Reporter de Playwright sans l'importer. Le paquet racine
  ne dépend pas de Playwright ; depuis le Lot G, le workspace isolé `e2e/` fixe en
  revanche `@playwright/test` à la version `1.63.0`.
- Sortie : NDJSON ligne par ligne dans `process.env.ACP_REPORT_FILE`, écrit en
  `appendFileSync` pour survivre à une interruption. Sans cette variable, le reporter
  signale l'erreur sur `stderr` et ne fait pas échouer la suite de tests.
- Les statuts `passed`, `failed`, `timedOut`, `skipped`, `interrupted` et le caractère
  `flaky` sont conservés distinctement, jamais réduits à vert/rouge. Messages et
  extraits d'erreur sont tronqués à 8 000 caractères et débarrassés des séquences
  ANSI ; la troncature ne coupe pas une paire de substituts UTF-16.
- Le reporter n'effectue aucun appel réseau et ne journalise ni l'environnement ni les
  en-têtes de requête.
- Configuration côté runner : `reporter: [['@acp/playwright-reporter']]`. Voir
  `packages/playwright-reporter/README.md`.

### Exécution de tests web sur le runner

- `apps/worker/src/acp_worker/web_tests.py` lance l'argv absolu configuré par
  l'opérateur (`ACP_WORKER_WEBTEST_ARGV_JSON`, `ACP_WORKER_WEBTEST_CWD`) par les deux
  points d'entrée publics du runner du Lot D — `spawn_fenced_process` puis
  `terminate_process_tree` — jamais par un `create_subprocess_exec` direct, jamais par
  un shell. Sous Windows, le processus est donc enfermé dans un Job Object dès sa
  création.
- Un arrêt d'arbre non prouvé (`terminate_process_tree` renvoie `False`) **interdit**
  le verdict `passed`. Cette preuve complète vaut pour le Job Object Windows ; sous
  POSIX, `killpg` ne peut pas détecter un descendant ayant quitté la session.
- Un NDJSON absent ou vide est un échec explicite (« aucun résultat de test
  produit »), jamais un succès. Une ligne corrompue est ignorée, comptée et signalée ;
  le reste du rapport est conservé.
- Une pièce jointe n'est téléversée que si sa résolution canonique reste sous le
  répertoire de sortie de la tentative : liens et `..` sont refusés et signalés, et un
  refus interdit le verdict `passed`.
- Messages d'erreur et extraits de code remontés par le rapport passent par
  `redact_text` / `redact_data` avec les valeurs injectées dans l'environnement du
  processus de test comme liste d'expurgation : une suite qui imprime une variable ne
  la republie pas.
- Le verdict local ne peut qu'être **aggravé** par celui que l'API calcule à partir
  des totaux fusionnés : compteurs bloquants relevés au maximum des deux, code de
  sortie non nul du serveur adopté, `case_count` abaissé au nombre réellement
  enregistré. Le worker retire en outre l'`exit_code` que le rapport s'attribue :
  seul le code **mesuré** compte.
- La preuve de mission `web_tests` résume totaux, code de sortie et identifiant du
  `test_run` — jamais une image.
- La capacité `web_tests` n'est annoncée que si la configuration est complète **et**
  que le worker n'est pas en simulation.

### Résultats de tests structurés côté serveur

- `apps/api/src/acp_api/testing_service.py` ingère un `TestIngestRequest` après
  vérification de l'identité worker, du lease actif sur la tentative et du
  `fencing_token`. L'ingestion est idempotente
  (`UniqueConstraint(task_run_id, runner)`, déduplication sur
  `(test_run_id, test_id, attempt)`), et publie `test.run.started`,
  `test.case.finished` et `test.run.finished` avec leurs séquences.
- `derive_technical_validation` rend `passed` **seulement** si le code de sortie vaut
  zéro, si `unexpected`, `interrupted` et `timedOut` sont nuls et si au moins un cas a
  réellement été exécuté ; zéro cas exécuté rend `failed` (« aucune assertion
  exécutée »). `flaky` et `skipped` n'empêchent pas `passed` mais restent affichés.
  Cette fonction ne rend jamais `succeeded` : conclure une tentative reste du ressort
  du Lot C (acceptation utilisateur et évaluateur inchangés).
- Un code de sortie annoncé par le rapport ne peut **signaler** un échec, jamais en
  effacer un : le code mesuré par le worker est retenu sauf s'il vaut `0` et que le
  rapport en déclare un non nul.

### Stockage privé des livrables

- Blobs adressés par contenu sur disque, sous `ACP_ARTIFACT_STORAGE_DIR` (défaut
  `./acp-data/artifacts`), clé `<sha256[0:2]>/<sha256>` : écriture atomique dans un
  fichier temporaire du même volume puis `os.replace`, permissions restreintes
  lorsque le système les applique, et **aucun nom fourni par le client dans le
  chemin**. L'interface `ArtifactStorage` existe pour accueillir un adaptateur objet
  (S3) ; cet adaptateur n'est pas livré.
- `POST /workers/{id}/artifacts/content` (multipart) vérifie l'identité worker
  et exige le `X-Attempt-Fencing-Token` courant **avant** de lire le corps. Il borne
  chaque fichier à `ACP_ARTIFACT_MAX_BYTES`
  (défaut 200 Mio) et le cumul par tentative à `ACP_ARTIFACT_MAX_BYTES_PER_RUN`
  (défaut 1 Gio), et rend le même artefact pour un même sha256 sur la même tentative.
  Le lease et le fence sont revérifiés sous le verrou d'écriture après réception du
  corps et avant quota, déduplication, blob ou ligne : une reprise concurrente invalide
  donc l'ancien téléversement tardif.
- `GET /artifacts/{id}/content` sert le blob à un membre du projet (session) **ou**
  via un lien signé, avec `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox`,
  `Cache-Control: private, no-store`, `Accept-Ranges: bytes` et support des requêtes
  `Range`.
- Type de contenu déterminé par une **allowlist serveur** (extension + type déclaré),
  sans aucun reniflage. `text/html`, `image/svg+xml` et les archives — dont la trace
  Playwright — ne sont **jamais** servis en ligne : ils partent en
  `application/octet-stream` avec `Content-Disposition: attachment`. Un type non
  reconnu devient `application/octet-stream`.
- Depuis le Lot G, un `.glb` n'est affichable qu'après validation stricte du conteneur
  GLB v2 auto-contenu et scellement de cette validation par le sha256 du blob. Un
  `.gltf`, une ligne antérieure au Lot G ou un sceau incohérent reste téléchargeable
  sans être rendu.
- `POST /artifacts/{id}/link` crée un lien signé HMAC-SHA256 borné dans le temps
  (`ttl_seconds` ≤ 900, défaut 300), lié à l'artefact **et** au demandeur, révocable
  par `DELETE /artifacts/links/{link_id}`. Sans `ACP_ARTIFACT_SIGNING_KEYS`, la route
  répond `503` avec l'action à effectuer ; le téléchargement authentifié par session
  reste possible. Aucun projet ne devient public.
- Rétention : `python -m acp_api.retention` est une purge **à blanc par défaut** ;
  `--apply` est nécessaire pour supprimer. Elle conserve les événements terminaux
  d'une tentative, ne supprime jamais un blob encore référencé par un autre artefact
  (adressage par contenu ⇒ comptage de références) ni un artefact cité par une preuve
  de mission — la citation est détectée en balayant **toutes** les chaînes de
  `evidence.data` à profondeur bornée, et non une liste de noms de clés.

### Studio et bibliothèque web

- `apps/web/src/studio-ui.ts` se rend dans le détail d'une mission et sur le lien
  profond `/missions?run=<id>&vue=studio`. Il affiche :
  bandeau de mode (`Direct`, `Aperçu intermédiaire`, `Replay`,
  `Hors ligne / inconnu`) et état de connexion en **libellés textuels** en plus de la
  couleur ; chronologie du journal avec chargement du passé par curseur ; arbre des
  tests (suites, cas, statuts distincts, durée, message d'erreur en `<pre>` inséré par
  `textContent`, étapes dépliables) ; dernière capture référencée par les pièces
  jointes, avec son horodatage ; pièces jointes en aperçu image/vidéo par lien signé,
  trace et rapport HTML en téléchargement explicite avec avertissement.
- Aucun contenu d'artefact n'est rendu dans l'origine de la plateforme : pas
  d'`iframe`, pas de `srcdoc`, aucune exécution. Depuis le Lot G,
  `ACP_ARTIFACT_PUBLIC_ORIGIN` doit être une origine distincte de l'API et des origines
  CORS ; sinon la création du lien d'aperçu répond `424` avant jeton, sans repli même
  origine. Le service `acp_api.preview:app` monté sur cette origine ne possède que
  santé et lecture par jeton `purpose=preview`, sans session, routes métier ni docs.
  Le téléchargement authentifié reste possible sur l'API de contrôle.
- Les GLB validés utilisent `@google/model-viewer`, chargé à la demande, sans AR,
  lecture ni rotation automatiques. Images et vidéos conservent leur aperçu signé ;
  les autres formats restent en téléchargement explicite.
- Aucun bouton de prise de contrôle. Un panneau dit explicitement que la capacité
  n'est pas livrée.
- `apps/web/src/library-ui.ts` donne à la route « Bibliothèque » deux onglets,
  `Skills` (délégué tel quel au module du Lot D) et `Livrables` (liste filtrable par
  projet, mission et type, recherche, aperçu, téléchargement, métadonnées, provenance,
  taille, empreinte). Aucun nouvel élément de navigation n'a été ajouté.
- Comme au Lot D, ces modules reçoivent le client HTTP du shell, ne lisent jamais
  `/auth/session` et exposent une purge d'état (`resetStudioUiState`,
  `resetLibraryUiState`) appelée par le shell à la connexion et à la déconnexion ;
  la purge du Studio ferme aussi l'`EventSource` ouvert.

### CLI

```text
acp runs events <mission-id|run-id> [--after-seq N] [--limit N] [--follow] [--json]
acp runs tests  <mission-id|run-id> [--json]
acp artifacts list --run <id> [--kind K] [--type T]
acp artifacts get  <artifact-id> [--output CHEMIN] [--stdout] [--force]
acp artifacts link <artifact-id> [--ttl 300]
acp open --run <id> [--studio] [--browser]
```

`--follow` consomme le flux SSE, ou bascule sur l'interrogation par curseur s'il
échoue, et écrit une ligne NDJSON par événement ; `Ctrl+C` quitte l'observation sans
arrêter la mission (code `INTERRUPTED`). `acp artifacts get` écrit par flux borné,
vérifie le sha256 reçu et refuse d'écraser un fichier existant sans `--force`.
`acp runs tests` applique la **même** règle de dérivation que le serveur et sort `4`
lorsque la validation technique est en échec. `acp open --studio` produit le lien
profond `?vue=studio`, le seul paramètre que le shell web interprète. Détails dans
[apps/cli/README.md](../apps/cli/README.md).

## Réalisé, non testé en conditions réelles

- Un vrai Edge/Playwright a exercé connexion → Missions → Studio contre une API et un
  Vite réellement démarrés par `scripts/verify_live_studio_journey.py`. Le reporter
  reste prouvé sur des objets Playwright synthétiques ; l'exécuteur du worker sur
  `apps/worker/tests/fake_playwright_runner.py`, un programme déterministe lancé par
  `sys.executable` qui écrit un NDJSON réaliste et des fichiers de pièces jointes. La
  chaîne reporter → worker n'a jamais été exercée avec un vrai runner Playwright.
- Aucune capture d'écran d'une session de test réelle n'existe : les panneaux
  d'image du Studio n'ont donc jamais affiché autre chose qu'une pièce jointe
  synthétique de test.
- Le Studio a été observé dans le parcours Edge ; la Bibliothèque reste couverte par
  Vitest sur le DOM, sans parcours navigateur réel.
- Le paquet `e2e/` du Lot G couvre uniquement le parcours connexion → Missions → Studio
  contre une tentative existante ; il ne traverse pas la Bibliothèque. Son garde exact
  `ACP_E2E=1` reste désactivé par défaut, mais a été activé localement avec le canal
  `msedge` pour la publication `0.8.0`.
- Aucun GLB n'a été rendu avec un vrai moteur de navigateur et aucune origine
  d'aperçu séparée n'a été déployée.
- Le flux SSE est exercé par la suite API sur un client de test ; aucune coupure
  réseau réelle, aucun proxy intermédiaire et aucune reconnexion depuis un vrai
  `EventSource` de navigateur n'ont été éprouvés.
- La migration additive de `sequence` et `journal_seq` est exercée sur SQLite
  uniquement.

## Non configuré

- `ACP_ARTIFACT_SIGNING_KEYS` : sans clé, les liens signés sont indisponibles
  (`503` explicite) et l'aperçu du Studio le dit ; le téléchargement par session reste
  possible.
- `ACP_ARTIFACT_PUBLIC_ORIGIN` : **aucune origine d'aperçu séparée n'est configurée**
  dans cet environnement. La création d'un lien d'aperçu échoue en `424` avant jeton,
  sans repli vers l'API ; les téléchargements par session continuent de fonctionner.
- Aucun stockage d'objets distant : l'interface existe, l'adaptateur n'est pas écrit.
- `ACP_WORKER_WEBTEST_*` : aucun runner réel n'est configuré dans cet environnement de
  vérification ; la capacité `web_tests` n'a jamais été annoncée par un worker réel.

## Non livré dans ce lot

- **Reprise en main humaine du navigateur.** Le Studio est en lecture seule et
  l'interface le dit ; aucun lease de contrôle, aucune suspension de l'automate,
  aucun bouton. Cette capacité reste absente après le Lot G.
- **Diffusion d'images de la session en direct.** La plateforme ne produit aucune
  image de session : les seules images disponibles sont les captures téléversées par
  le lanceur de tests. Il n'y a ni cadence, ni qualité adaptative, ni backpressure
  d'images à régler, parce qu'il n'y a pas de flux d'images.
- Trace viewer intégré : une trace Playwright est un fichier à télécharger et à ouvrir
  avec l'outil Playwright, hors de la plateforme.
- Registre de ports, tunnel de runner et comptes de test dédiés.

## Restant à réaliser

- Exécuter une vraie suite sur un runner afin de traverser reporter → worker → API avec
  capture, vidéo et trace ; la preuve shell/Studio seule ne suffit pas à faire passer
  les scénarios d'acceptation 10 et 11 à **Accepté**.
- Rejouer le parcours navigateur sur un staging autorisé, puis l'étendre à la
  Bibliothèque avant de revendiquer une couverture navigateur de cet écran.
- Configurer une origine d'aperçu séparée et la vérifier.
- Migration `journal_seq` / `sequence` sur une base PostgreSQL existante.
- Adaptateur de stockage objet et politique de rétention exercée sur un volume réel.

## Menaces et contrôles

| Menace | Contrôle livré | Écart restant |
|---|---|---|
| Contenu actif produit par un test (HTML, SVG, trace) | allowlist serveur sans reniflage, téléchargement forcé, `nosniff`, CSP `default-src 'none'; sandbox`, jamais d'`iframe` ni de `srcdoc` ; origine d'aperçu distincte obligatoire avant émission d'un jeton | aucune origine séparée n'a été déployée ni testée dans un navigateur réel |
| URL de média partagée ou durable | lien signé HMAC borné (≤ 900 s), lié à l'artefact et au demandeur, révocable, rotation de clés par liste | pas de journal de consultation par lien ; le compteur d'usage existe mais n'est pas exposé |
| Lecture du flux ou d'un fichier d'un autre projet | RBAC serveur sur chaque ouverture **et** à chaque page du flux ; un `project_id` client n'élargit jamais la portée | matrice RBAC exhaustive toujours incomplète (écart hérité) |
| Traversée de chemin | clé de stockage dérivée du sha256, nom d'origine jamais dans le chemin, résolution canonique des pièces jointes, refus des liens et des `..` | les 3 tests de lien symbolique sont ignorés sur cette machine faute de privilège |
| Fuite de secret par une sortie de test | expurgation `redact_text` / `redact_data` avec les valeurs injectées ; le processus de test ne reçoit aucun credential de la plateforme | un filtre de texte ne masque pas des pixels ; une valeur dérivée (encodée, tronquée, hachée) n'est pas couverte |
| Faux succès | verdict dérivé des codes de sortie et des compteurs, jamais d'une image ; arrêt d'arbre signalé comme non prouvé ⇒ pas de succès ; rapport vide ⇒ échec ; le rapport ne peut qu'aggraver le verdict | preuve de vidange complète limitée au Job Object Windows ; POSIX ne détecte pas un descendant sorti de session ; aucune chaîne Playwright réelle reporter → worker |
| Coupure de flux interprétée comme un état | états `connected`/`reconnecting`/`polling`/`offline` explicites, réconciliation par `GET`, aucune relance de mission | pas de test de coupure réseau réelle |
| Saturation stockage | plafond par fichier et quota par tentative, rétention avec comptage de références ; le Lot F ouvre une alerte in-app locale expurgée sur `507`/`503` lorsque projet et run sont résolus | pas de quota par projet ni de preuve de saturation et d'alerte sur un volume hébergé |
| Prise de contrôle concurrente | sans objet : la capacité n'est pas livrée | reste à concevoir après le Lot G |

## Vérification

Suites exécutées le 13 septembre 2026 dans le worktree `lot-e`, sous Windows 10 Pro
`10.0.19045`, avec `.venv\Scripts\python.exe` (Python `3.12.0`), Node `v24.19.0` et
npm `11.17.0` :

| Commande | Résultat |
|---|---|
| `./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **1 627 réussis, 4 ignorés**, 2 avertissements de dépréciation |
| `npm run typecheck --workspace @acp/web` | réussi |
| `npm test --workspace @acp/web` | **262 réussis** (17 fichiers) |
| `npm test --workspace @acp/playwright-reporter` | **59 réussis** (1 fichier) |

Les fichiers de test propres au Lot E côté Python totalisent **509 tests collectés** :
`test_events_stream.py`, `test_artifacts_content.py`, `test_testing_service.py`,
`test_retention.py`, `test_artifact_signing.py`, `test_artifacts_storage.py`,
`test_lot_e_models.py`, `apps/worker/tests/test_web_tests.py` et
`apps/cli/tests/test_cli_events_artifacts.py`. Côté web, les cinq fichiers du lot
(`events-api`, `artifacts-api`, `testing-api`, `library-ui`, `studio-wiring`)
totalisent **113 tests**.

Les 4 tests ignorés sont : un contrôle de permissions POSIX inapplicable sous Windows
(`test_artifacts_storage.py`) et trois tests de lien symbolique
(`apps/worker/tests/test_web_tests.py`) que le compte de vérification ne peut pas
créer sur cette machine. Pour cet instantané Lot E, aucun test n'était ignoré faute
d'opt-in Playwright parce que celui-ci n'existait pas encore ; le Lot G l'ajoute et le
garde désactivé par défaut.
