# ACP CLI

Client en ligne de commande de l'Agent Company Platform.

```console
acp login --login owner
acp doctor
acp projects list
acp run --project PROJECT_ID --goal "Livrer la fonctionnalité"
acp runs watch MISSION_ID
acp pending show
```

## Secrets, serveurs MCP et skills

```console
acp secrets status
printf %s "$TOKEN" | acp secrets set CONTEXT7_API_KEY --value-stdin --description "Clé Context7"
acp mcp add context7 --url https://mcp.context7.com/mcp --header CONTEXT7_API_KEY=@SECRET_ID
acp mcp test context7-ID --wait
acp mcp bind SERVER_ID --project PROJECT_ID --tool resolve --tool query
acp mcp activate SERVER_ID
acp mcp export --format hermes > ~/.hermes/mcp.yaml
acp mcp import ~/.claude.json
acp mcp import ~/.claude.json --apply --name context7 --map CONTEXT7_CONTEXT7_API_KEY=SECRET_ID
acp skills install github:anthropics/skills@<sha40>:skills/pdf
acp skills approve SKILL_ID --revision 2
acp skills bind SKILL_ID --project PROJECT_ID
acp projects extensions PROJECT_ID
```

## Événements, validation technique et livrables

```console
acp runs events RUN_ID --after-seq 120 --limit 200
acp runs events RUN_ID --follow --json
acp runs tests RUN_ID --json
acp artifacts list --run RUN_ID --kind screenshot --type image/png
acp artifacts get ARTIFACT_ID --output ./rapport.zip
acp artifacts get ARTIFACT_ID --stdout > trace.zip
acp artifacts link ARTIFACT_ID --ttl 300
acp open --run RUN_ID --studio
```

## Automatisations

```console
acp automations list --project PROJECT_ID --enabled
acp automations create --project PROJECT_ID --name "Rapport quotidien" --schedule-kind cron --expression "0 9 * * 1-5" --timezone Europe/Paris --template-file apps/cli/examples/automation-mission-template.json --idempotency-key CREATE_KEY
acp automations show AUTOMATION_ID
acp automations update AUTOMATION_ID --catchup run_once --max-concurrent-runs 2 --idempotency-key UPDATE_KEY
acp automations enable AUTOMATION_ID --idempotency-key ENABLE_KEY
acp automations trigger AUTOMATION_ID
acp automations runs AUTOMATION_ID --limit 25
acp automations calendar --project PROJECT_ID --start 2026-09-01T00:00:00+02:00 --end 2026-10-01T00:00:00+02:00
acp automations webhook status AUTOMATION_ID
acp automations webhook rotate AUTOMATION_ID --secret-env ACP_WEBHOOK_SECRET --idempotency-key ROTATE_KEY
acp automations webhook rotate AUTOMATION_ID --secret-file ./webhook.secret
acp automations webhook disable AUTOMATION_ID --idempotency-key DISABLE_WEBHOOK_KEY
```

Une automatisation est créée désactivée. Le gabarit complet de mission est fourni
soit comme objet JSON avec `--template` (alias `--template-json`), soit comme fichier
UTF-8 (BOM accepté) avec `--template-file` ; ces deux formes sont exclusives. Le fichier
versionné `apps/cli/examples/automation-mission-template.json` constitue un exemple
complet et directement utilisable depuis la racine du dépôt. Une modification de
calendrier exige `--schedule-kind`, `--expression` et `--timezone` ensemble afin de
ne jamais remplacer silencieusement le fuseau courant. À la création, le fuseau vaut
`Europe/Paris` par défaut. Un intervalle accepte des secondes ou une durée telle que
`15m`, `2h` ou `1d`, normalisée en secondes avant l'envoi.

Toutes les mutations d'automatisation (`create`, `update`, `enable`, `disable`,
`trigger`, `webhook rotate` et `webhook disable`) envoient un en-tête
`Idempotency-Key`. Sans `--idempotency-key`, le CLI génère une clé et l’inclut dans
le résultat. Une coupure réseau, une réponse invalide, un HTTP 408 ou un HTTP 5xx
laisse le résultat incertain : l'erreur rend la même clé et demande de rejouer
exactement la commande et son payload avec `--idempotency-key`. Un autre HTTP 4xx
reste un refus certain de l'API ; un `409` peut notamment signaler qu'une intention
plus récente a remplacé la commande rejouée, qui n'est alors jamais réappliquée.

Le sous-groupe `webhook` utilise les routes réelles de la routine. `status` et
`disable` ne rendent jamais de secret ; `disable` possède sa propre clé de rejeu.
`rotate` génère par défaut un secret
cryptographiquement aléatoire et URL-safe ; pour imposer une valeur, utilisez
`--secret-env NOM` ou `--secret-file CHEMIN`. Le secret n'est jamais accepté dans
`argv`, ni conservé dans la configuration du CLI. La rotation envoie elle aussi une
clé d'idempotence et n'affiche normalement le secret qu'après validation stricte du
succès. Si son résultat est incertain, stderr rend exceptionnellement la clé **et**
le secret nécessaires au rejeu ; conservez-les dans un canal sûr puis rejouez avec
la même paire. Un HTTP 4xx certain masque tout écho éventuel du secret.

`acp runs events` et `acp runs tests` acceptent un identifiant de run **ou** de mission :
la mission n'est résolue (`GET /missions/{id}`) qu'après un 404 franc sur le run, pour ne pas
payer un appel supplémentaire dans le cas courant.

`acp runs events` lit **une seule page** du journal durable
(`GET /runs/{id}/events?after_seq=&limit=`, `--limit` entre 1 et 500). Chaque événement sort
sur une ligne : NDJSON brut avec `--json`, sinon `séquence horodatage type identifiant`. Si la
page est incomplète, la sortie standard ne contient **que** des événements et la reprise
(`--after-seq`) est annoncée sur la sortie d'erreur, avec `next_cursor` en JSON.

`--follow` observe la mission en trois temps : lecture du journal durable jusqu'au bout, flux
SSE (`GET /streams/runs/{id}`, `after_seq` et `Last-Event-ID` alignés sur le dernier curseur
reçu), puis réconciliation par curseur à la fermeture du flux. La sortie est du NDJSON même
sans `--json`. Seules les trames `acp.event` y arrivent : les trames de contrôle du serveur
n'y figurent jamais. Une rotation (`acp.stream.rotate`, émise au bout de
`ACP_STREAM_MAX_SECONDS`) signifie que **la mission continue** : le CLI l'annonce
(`stream_rotated`) et rouvre le flux au curseur porté par la trame, au plus huit fois avant
d'arrêter l'observation (`stream_rotations_exhausted`). Une fermeture annoncée
(`acp.stream.closed`) est dite sur la sortie d'erreur, sauf `unauthorized` — une session ou un
membership révoqué en cours d'observation — qui sort avec le code `AUTH`. La
déduplication se fait par séquence, puis par identifiant pour les événements qui n'en
portent pas : un recouvrement entre la relecture et le flux ne duplique rien, et une
coupure ne perd rien. Si le flux échoue — coupure réseau, données illisibles, route
indisponible (404 ou 5xx) — le CLI le signale sur la sortie d'erreur (`stream_degraded`) puis
draine le journal durable par curseur ; un refus d'accès (401/403) ou une requête invalide
reste au contraire visible et ne devient jamais une interrogation silencieuse.

`Ctrl+C` pendant `--follow` quitte l'observation avec le code `INTERRUPTED` : **la mission
n'est pas arrêtée**, aucune requête d'annulation n'est envoyée, et le curseur de reprise est
affiché. Utilisez `acp runs stop` pour demander réellement un arrêt.

`acp runs tests` lit `GET /runs/{id}/test-run` et dérive la validation technique **avec la
règle exacte du serveur** (`testing_service.py::derive_technical_validation`, spec §5.4), sans
jamais forcer un succès : elle est `passed` seulement si le code de sortie annoncé vaut `0` —
un code de sortie **absent** est un refus —, qu'au moins un cas a été exécuté et que les totaux
`unexpected`, `interrupted` et `timedOut` sont nuls. Le statut de l'exécution est affiché mais
n'ajoute aucune cause : la porte franchie par une CI et la validation technique de la tentative
ne doivent diverger dans aucun des deux sens. La commande sort avec `0` si la validation est
`passed` et `4` sinon, en nommant la cause (`reasons`). `flaky` et `skipped` sont conservés
et affichés distinctement, jamais réduits à vert/rouge : un test instable ne fait pas
échouer la validation mais reste visible dans les totaux.

`acp artifacts list --run` demande `task_run_id` au serveur et suit son curseur. `--kind`
accepte les deux vocabulaires du modèle : un genre de flux du §3.2 (`screenshot`, `video`,
`trace`, `report`, `file`) est envoyé au serveur comme `stream_kind` — le seul filtre de genre
qu'il expose — et un genre d'artefact (`test_attachment`, `test_report`) reste un filtre local.
Le résultat est de toute façon refiltré localement : le run, `--kind` (comparé à `kind` **et** à
`stream_kind`) et `--type` (type MIME exact, insensible à la casse). Ce filtre local est
volontaire — un serveur qui ignorerait la requête ne peut pas faire apparaître un artefact d'un
autre run.

`acp artifacts get` lit d'abord les métadonnées (`GET /artifacts/{id}`) puis écrit le contenu
**par flux borné** de 1 MiB, sans jamais le charger entièrement en mémoire. Le nombre d'octets
ne peut pas dépasser la taille annoncée (à défaut 200 MiB) et l'empreinte sha256 reçue est
recalculée : une empreinte différente écarte le contenu et sort avec `4`. Sans `--output`, le
nom d'origine est utilisé **réduit à son dernier segment** — il vient d'un worker et n'est
jamais traité comme un chemin ; un nom inutilisable retombe sur l'identifiant de l'artefact.
Un fichier existant n'est jamais écrasé sans `--force`, et avec `--force` l'écriture passe par
un fichier temporaire voisin remplacé atomiquement : un téléchargement raté laisse le fichier
précédent intact. `--stdout` écrit le contenu brut sur la sortie standard (les métadonnées
`--json` partent alors sur la sortie d'erreur) et **refuse un contenu binaire sur un terminal
interactif** sans `--force`. Ce refus est décidé sur le `Content-Type` **servi** par l'API,
déjà ramené à son allowlist (§7), et non sur le type déclaré dans les métadonnées : celui-ci
vient d'un worker et ne peut que faire refuser plus tôt, jamais autoriser. Les métadonnées
`--json` portent les deux (`content_type` servi, `declared_content_type`). Avec `--stdout`,
une empreinte invalide est détectée après émission : le CLI le dit explicitement et sort
avec `4`.

`acp artifacts link` crée un lien signé temporaire (`POST /artifacts/{id}/link?ttl_seconds=`,
1 à 900 secondes, 300 par défaut) et imprime l'URL seule, l'échéance étant rappelée sur la
sortie d'erreur. Cette URL porte un jeton : elle est nominative, bornée dans le temps et
révocable, mais ne doit pas être publiée. Sans clé de signature côté serveur, la commande
remonte le `503` tel quel.

`acp open --run ID --studio` produit le lien profond `/missions?run=<id>&vue=studio` (§2.5 et
§10 : le shell web ne lit que `vue`, `view` appartenant déjà à une autre vue) et se contente de
l'afficher ; `--browser` demande explicitement l'ouverture.

La valeur d'un secret n'est **jamais** acceptée en argument : `--value-stdin` est
obligatoire pour `acp secrets set` et `acp secrets rotate`, et une valeur placée en
argument (positionnel ou `--value`) est refusée avec le code `USAGE` sans être
recopiée dans la sortie d'erreur. Le CLI n'affiche jamais une valeur de secret : les
en-têtes et variables d'environnement d'un serveur MCP se réfèrent à un secret avec
`K=@SECRET_ID` (`--header`, `--env`), tandis que `K=V` reste une valeur littérale non
secrète, refusée par l'API si elle ressemble à un identifiant.

`acp mcp test` lance une sonde de découverte. Sur un transport stdio elle reste en
attente d'autorisation ; `--wait` interroge `GET /mcp/probes/{id}` jusqu'à un état
terminal et sort avec 0 seulement si la sonde a réussi. `Ctrl+C` pendant `--wait`
n'annule rien : la sonde continue côté serveur et le CLI le dit explicitement avant de
sortir avec le code `INTERRUPTED`. Un état de sonde inconnu est refusé plutôt
qu'attendu indéfiniment.

`acp skills install` accepte `dir:/chemin/absolu`, `archive:/chemin.zip` (lu localement,
25 MiB au plus, transmis en base64), `github:owner/repo@SHA[:sous/chemin]` (commit
épinglé sur 40 caractères hexadécimaux exigé) et `skill-md:/chemin/SKILL.md` (fichier lu
localement, UTF-8 exigé, envoyé comme source `manual`). Le serveur ne lit jamais un
chemin fourni par le client. `acp skills cat` écrit le texte tel quel, comme une donnée :
son contenu n'est jamais interprété.

`acp mcp export` écrit la configuration sur la sortie standard, sans rien ajouter, et
réserve la sortie d'erreur aux variables `ACP_SECRET_*` à définir et aux limites de
compatibilité.

`acp mcp import FILE` lit le fichier **localement** (1 MiB au plus, UTF-8, fichier
régulier) et n'envoie que son contenu : le serveur ne lit jamais un chemin fourni par le
client. Sans `--apply`, la commande se limite à un aperçu — un tableau `NOM / TRANSPORT /
IMPORTABLE / CONFLIT / SECRETS / SOURCE`, puis pour chaque entrée les secrets détectés
(nom de secret proposé et valeur **masquée**), ce que la plateforme ne reprend pas et les
avertissements ; `--json` rend l'aperçu tel quel. Rien n'est créé tant que
`--apply --name <entrée>` n'est pas passé : `--name`, `--map` et `--on-conflict` sont
refusés sans `--apply`, et `--map SECRET_NAME=SECRET_ID` relie un candidat à un secret
**déjà** présent dans le coffre (aucune valeur ne transite par le CLI). `--on-conflict
new_revision` ajoute une révision au serveur existant — l'ancienne est conservée et reste
la sauvegarde. Les serveurs importés arrivent en brouillon : diagnostic et activation
restent à faire. La commande sort avec `REMOTE` si aucune entrée n'a pu être appliquée, et
avec 0 en cas de succès partiel, chaque refus étant détaillé sur la sortie d'erreur.

Le mot de passe n'est jamais accepté comme argument. Utilisez l'invite masquée ou
`--password-stdin` dans un environnement non interactif. `--json` peut être placé
avant ou après la commande et n'ouvre jamais d'invite ; `runs watch --json` émet du
NDJSON. La configuration (URL, cookie de session et jeton CSRF) est écrite
atomiquement avec des permissions restreintes au mieux du système.
HTTP n'est accepté que pour `localhost`, le réseau `127.0.0.0/8` et `::1`. Les
credentials sont liés à l'origine API qui les a émis et sont ignorés dès qu'une
surcharge d'URL change cette origine.

Le transport ignore les variables proxy de l'environnement. Sous WSL, utiliser un
environnement Python et une configuration séparés de Windows, comme documenté dans
le README racine.

`acp runs watch` peut être interrompu avec `Ctrl+C` sans arrêter la mission. La
commande `acp open --run ...` affiche seulement l'URL ; ajoutez `--browser` pour
demander explicitement l'ouverture du navigateur.

`acp run` et `acp runs stop` réservent leur clé d'idempotence avant l'appel. Les
mutations de configuration sont sérialisées par un verrou interprocessus, puis
écrites par remplacement atomique. Un second verrou, détenu jusqu'à la fin de
l'appel HTTP, refuse immédiatement tout dispatch concurrent afin qu'une seule
requête puisse utiliser la réservation active. Si le réseau, un 5xx, une
redirection ou une réponse métier invalide laisse le résultat incertain, le CLI
conserve une
opération `pending`, liée à la base API exacte (chemin compris), au principal (ou
à la session) et à l'empreinte canonique de la requête. Relancer exactement la
même commande réutilise automatiquement la clé, également affichée dans l'erreur
et dans la réponse réussie. Une commande ou une clé divergente est refusée tant
que cette reprise n'a pas reçu de résultat certain.

`acp pending show` inspecte localement cette reprise sans afficher de credential.
`acp pending discard` demande une confirmation explicite et avertit qu'un effet
déjà appliqué pourrait être dupliqué ; en mode non interactif ou JSON, `--yes`
est obligatoire. Le payload, le cookie, le jeton CSRF et l'identifiant du
principal ne sont pas copiés dans l'enregistrement `pending`.
`--idempotency-key` reste disponible pour fournir explicitement une clé stable.
