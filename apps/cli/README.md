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
compatibilité. `acp automations` reste honnêtement « non raccordé » et sort avec le
code `UNSUPPORTED`.

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
