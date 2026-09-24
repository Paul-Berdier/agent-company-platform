# Worker Windows distant

Le worker Windows s'enregistre auprès de l'API, reçoit un jeton propre à la
machine, publie un heartbeat et ne réclame que les tâches compatibles avec ses
capacités. Hermes reste un service externe optionnel derrière le
provider-gateway : le worker ne l'importe jamais directement.

## 1. Installer

Depuis PowerShell à la racine du dépôt :

```powershell
./scripts/setup.ps1
```

L'installation expose la commande `agent-company-worker` dans `.venv\Scripts`.
On peut aussi utiliser sa forme module :

```powershell
./.venv/Scripts/python.exe -m acp_worker.cli capabilities
```

## 2. Enrôler la machine

Générer un secret temporaire et le définir dans le terminal qui lance l'API :

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:ACP_WORKER_REGISTRATION_TOKEN = [Convert]::ToBase64String($bytes)
$env:ACP_WORKER_REGISTRATION_PROJECT_ID = "<project-id>"
./scripts/dev.ps1
```

Dans un second terminal, fournir le même secret uniquement pour
l'enregistrement :

```powershell
$env:ACP_WORKER_REGISTRATION_TOKEN = "<le-secret-généré>"
./.venv/Scripts/agent-company-worker.exe register `
  --name dev-windows-01 `
  --project <project-id>
Remove-Item Env:ACP_WORKER_REGISTRATION_TOKEN
```

Le processus API conserve la valeur héritée au démarrage. Après les enrôlements
prévus, arrêter l'API, supprimer ou faire tourner ce secret dans son environnement,
puis la relancer ; sinon ce même jeton continue d'autoriser de nouveaux workers.
Pour un nouvel enrôlement ultérieur, utiliser une nouvelle valeur temporaire.

`register` ne déduit jamais Claude Code ni Codex CLI du `PATH`. Ces deux capacités
exigent l'opt-in complet décrit au § 4. Les capacités génériques
`filesystem_project` et `shell_restricted`, ainsi que la détection de `git` et Blender,
ne sont annoncées que si le runner à argv fixe est réellement configuré. Une liste
explicite peut être fournie plusieurs fois, sans rendre disponible un backend absent :

```powershell
./.venv/Scripts/agent-company-worker.exe register `
  --name build-windows-01 `
  --capability git `
  --capability asset_validation `
  --project <project-id> `
  --max-concurrency 2
```

Cette cohérence est revérifiée au démarrage contre les capacités persistées. Si Codex ou
Claude a été désactivé depuis l'enrôlement, le worker s'arrête avant tout heartbeat ou
claim et demande un nouvel enregistrement.

Un nouvel enrôlement doit choisir **exactement un** périmètre. `--project ID`
est le choix normal : l'API filtre ce projet dans la requête SQL avant le verrou et
l'attribution. `--global-access` est un privilège d'administration distinct, réservé
notamment au worker qui cadence le planificateur de toutes les routines. Les deux
options sont incompatibles. Un heartbeat ne peut jamais modifier cette frontière.
Une ligne historique sans périmètre est mise en quarantaine : elle ne réclame aucune
tâche, ne lance pas le planificateur et `doctor` affiche `scope: missing` jusqu'au
réenrôlement.

Le client ne choisit jamais seul cette portée. L'API doit avoir reçu avec le secret
d'enrôlement soit `ACP_WORKER_REGISTRATION_PROJECT_ID=<même-id>`, soit
`ACP_WORKER_REGISTRATION_GLOBAL_ACCESS=1`, jamais les deux. Une demande différente
répond `403`; une configuration absente, ambiguë ou invalide répond `503`. Le secret
n'est pas one-shot : tant qu'il reste configuré, il peut enrôler d'autres workers dans
la portée serveur autorisée. Il faut donc retirer **le secret et sa portée** puis
redémarrer l'API après l'opération, ou les faire tourner ensemble. Changer explicitement
la portée serveur autorise ensuite un réenrôlement du même nom dans cette nouvelle
portée, à condition qu'aucun run ne soit actif.

Réenregistrer le même nom renouvelle son jeton et invalide immédiatement
l'ancien. Le serveur ne conserve que son empreinte. Le jeton brut reste dans
`%USERPROFILE%\.agent-company-worker\worker.json` par défaut ; ce fichier ne
doit être ni partagé, ni committé, ni copié dans les logs. Il est lié à l'origine
API normalisée utilisée pendant l'enrôlement : tout changement d'origine, ainsi
qu'un ancien fichier sans cette liaison, impose un nouvel enregistrement. L'écriture
est atomique et reçoit le mode `0600` sur POSIX ; sous Windows, `chmod` ne remplace
pas une DACL, donc le dossier d'état doit être limité explicitement au compte worker.

## 3. Vérifier et démarrer

```powershell
./.venv/Scripts/agent-company-worker.exe doctor
./.venv/Scripts/agent-company-worker.exe start
```

Commandes d'exploitation :

```powershell
./.venv/Scripts/agent-company-worker.exe capabilities
./.venv/Scripts/agent-company-worker.exe logs --tail 50
./.venv/Scripts/agent-company-worker.exe start --once
```

Variables utiles :

| Variable | Valeur par défaut | Rôle |
|---|---:|---|
| `ACP_API_URL` | `http://localhost:8000` | API centrale |
| `ACP_PROVIDER_GATEWAY_URL` | `http://localhost:8002` | passerelle providers |
| `ACP_GATEWAY_SERVICE_TOKEN` | non défini | Bearer inter-services obligatoire en mode réel |
| `ACP_WORKER_STATE_DIR` | `%USERPROFILE%\.agent-company-worker` | état et journal locaux |
| `ACP_WORKER_MAX_CONCURRENCY` | `1` | slots annoncés, entier de 1 à 32 |
| `ACP_WORKER_SIMULATION` | `1` | `1` simulation bloquée ; `0` réel ; toute autre valeur est refusée |
| `ACP_WORKER_PROJECT_ID` | non défini | projet unique autorisé pour les claims |
| `ACP_WORKER_GLOBAL_ACCESS` | `0` | `1` donne explicitement accès à tous les projets et au planificateur |
| `ACP_ORCHESTRATOR_PROVIDER` | `mock` | simulation uniquement ; interdit en mode réel |
| `ACP_WORKER_CODEX_ENABLED` | `0` | `1` active Codex uniquement avec exécutable, profil et racines valides |
| `ACP_WORKER_CODEX_EXECUTABLE` / `ACP_WORKER_CODEX_HOME` | non définis | exécutable absolu et profil Codex séparé |
| `ACP_WORKER_CLAUDE_ENABLED` | `0` | `1` active Claude uniquement avec exécutable, profil et racines valides |
| `ACP_WORKER_CLAUDE_EXECUTABLE` / `ACP_WORKER_CLAUDE_CONFIG_DIR` | non définis | exécutable absolu et profil Claude séparé |
| `ACP_WORKER_EXECUTOR_PROJECTS_JSON` | non défini | objet JSON `project_id -> racine absolue` des projets autorisés |
| `ACP_WORKER_EXECUTOR_PATH` | vide | `PATH` minimal facultatif remis aux CLIs |
| `ACP_WORKER_EXECUTOR_TIMEOUT_SECONDS` | `1800` | délai global, plafonné à 3 600 s |
| `ACP_WORKER_SUBSCRIPTION_QUOTAS` | `0` | `1` relève les quotas réels d'abonnement Codex et Claude Code ([détail](../subscription-quotas.md)) |
| `ACP_WORKER_QUOTA_INTERVAL_SECONDS` | `300` | intervalle des relevés, entier de 60 à 86 400 |
| `ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT` | `%USERPROFILE%\.acp\quotas\claude-code.json` | fichier écrit par la ligne d'état livrée (`python -m acp_worker.claude_statusline`), qui lit la même variable |
| `ACP_WORKER_QUOTA_CODEX_HOME` / `ACP_WORKER_QUOTA_CODEX_EXECUTABLE` | `%USERPROFILE%\.acp\codex-home` / `codex` du `PATH` | profil et CLI Codex des quotas, refusés si l'exécuteur Codex est activé (son profil est réutilisé) |

Les deux URL de service sont des origines sans chemin, query, fragment ou userinfo.
HTTP est accepté uniquement pour `localhost`, `127.0.0.0/8` et `::1` ; une machine
distante doit exposer l'API et le gateway en HTTPS.

## 4. Configurer un backend réel

Le mode réel accepte soit le runner à argv fixe historique, soit au moins un exécuteur
Codex/Claude complètement configuré. Les tests web réels exigent encore le runner fixe,
car sa racine de sortie porte leurs rapports et pièces jointes.

### Runner à argv fixe

Le backend réel n'accepte jamais une commande fournie par une mission. L'opérateur
configure un tableau JSON non vide : le premier élément est le chemin absolu d'un
exécutable existant hors de la racine des runs, et les suivants sont des arguments
fixes de confiance. Le worker crée ensuite un répertoire neuf par tentative, y écrit une enveloppe
`acp.local-process.request.v1`, puis ajoute le chemin absolu de `request.json` comme
dernier argument. Aucun shell ni interpolation de données de mission n'intervient.

Exemple avec un adaptateur local contrôlé :

```powershell
$env:ACP_WORKER_RUNNER_ARGV_JSON = '["C:\\Python312\\python.exe","C:\\acp-runner\\execute.py"]'
$env:ACP_WORKER_RUN_ROOT = 'C:\acp-runs'
$env:ACP_WORKER_RUN_TIMEOUT_SECONDS = '300'
$env:ACP_WORKER_RUN_MAX_OUTPUT_BYTES = '1048576'
$env:ACP_WORKER_RUN_ENV_ALLOWLIST = ''
$env:ACP_GATEWAY_SERVICE_TOKEN = '<secret inter-services>'
$env:ACP_ORCHESTRATOR_PROVIDER = 'hermes'
$env:ACP_WORKER_SIMULATION = '0'
```

Le programme reçoit dans le JSON l'identité de la tentative, le fencing token et
un snapshot limité à des champs allowlistés de la mission. Ce contenu utilisateur
peut néanmoins être sensible et doit être protégé comme la preuve. Le programme
s'exécute dans le répertoire de tentative avec un environnement minimal.
stdout/stderr sont lus en continu, bornés et hachés.
Un code de sortie nul ne suffit pas : le verdict du provider configuré doit être un
JSON valide avec `approved: true`, sinon la tentative échoue fermée.

Enrôler ensuite explicitement le worker réel, puis le démarrer :

```powershell
./.venv/Scripts/agent-company-worker.exe register `
  --name dev-windows-01 --real --project <project-id>
./.venv/Scripts/agent-company-worker.exe doctor
./.venv/Scripts/agent-company-worker.exe start
```

`register --real` vérifie qu'au moins un backend local autorisé est disponible puis
enrôle le worker auprès de
l'API ; il ne sonde pas Hermes. Avant `start`, exécuter `doctor` : il vérifie la
liveness API/gateway, l'authentification worker et la disponibilité authentifiée du
provider configuré. Son code est non nul si l'une de ces conditions manque.

Un arrêt utilisateur, un timeout, la perte du lease ou un fencing token obsolète
arrête le groupe de processus et conserve une preuve structurée. `evidence.json`
est écrit atomiquement dans le répertoire de tentative avant le PATCH terminal ;
un conflit réseau ne supprime donc pas la preuve locale. Le répertoire existant
d'une tentative n'est jamais réutilisé implicitement.

### Codex CLI ou Claude Code

Les exécuteurs agents utilisent des chemins absolus, un profil d'authentification
séparé du profil personnel et une allowlist de racines projet :

```powershell
$env:ACP_WORKER_SIMULATION = '0'
$env:ACP_WORKER_CODEX_ENABLED = '1'
$env:ACP_WORKER_CODEX_EXECUTABLE = 'C:\outils\codex\codex.exe'
$env:ACP_WORKER_CODEX_HOME = 'C:\acp-worker-auth\codex'
$env:ACP_WORKER_EXECUTOR_PROJECTS_JSON = '{"project-id":"C:\\projets\\project-id"}'
$env:ACP_GATEWAY_SERVICE_TOKEN = '<secret inter-services>'
$env:ACP_ORCHESTRATOR_PROVIDER = 'hermes'
./.venv/Scripts/agent-company-worker.exe doctor
```

Pour créer une mission Codex en lecture seule avec le CLI plateforme :

```powershell
acp run --project project-id --goal "Auditer ce projet" `
  --resource project_workspace=project-id:read `
  --require-capability codex_cli
```

Remplacer la capacité par `claude_code` pour Claude. Codex accepte aussi `:write` ;
Claude le refuse. La mission doit rester `supervised`, sans action autorisée, interdite
ou soumise à approbation, et sans seconde ressource. Deux capacités agent simultanées
sont refusées. Les options complètes et les preuves persistées sont décrites dans
[les exécuteurs locaux](../providers-local-executors.md).

Une mission Codex `:write` conserve un verrou interprocessus adjacent à la racine
canonique pendant toute l'invocation. Plusieurs processus worker voyant le même checkout
sur le même système de fichiers se sérialisent ; protéger le dossier parent par ACL et,
sur un partage réseau, valider les garanties de verrouillage ou donner un worktree
distinct à chaque worker.

`doctor` affiche uniquement les noms d'exécuteurs activés et le nombre de racines
allowlistées. Il ne publie ni chemins, ni profils, ni secrets.

Pour le runner à argv fixe, stdout/stderr restent des contenus non fiables et
potentiellement sensibles. Ils sont bornés mais non expurgés avant `evidence.json` et
l'API : ne jamais lui allowlister un secret, restreindre l'accès à la racine des runs
et définir une politique de rétention. Les exécuteurs Codex/Claude suivent une règle
plus stricte : leur preuve conserve des métadonnées opérationnelles, le code de sortie,
le nombre d'événements, les tailles et les sha256, jamais le prompt ni les flux bruts.
Un code nul exige aussi l'événement terminal de succès propre au CLI.

## 5. Capacités exigées par une tâche

Une tâche peut déclarer :

```json
{
  "title": "Valider les assets",
  "meta": {
    "required_capabilities": ["git", "asset_validation"]
  }
}
```

L'API ignore cette tâche pour tout worker ne possédant pas l'ensemble demandé.
Le worker revérifie aussi l'attribution avant de démarrer (défense en
profondeur).

## 6. Sécurité et limites actuelles

- le secret d'enrôlement doit être long, aléatoire, retiré du terminal worker
  après `register` et remplacé en cas d'exposition ;
- en production, définir également `ACP_WORKER_TOKEN_PEPPER` uniquement sur
  l'API ; la configuration worker refuse déjà HTTP hors loopback ;
- le heartbeat expire après 45 secondes et chaque task run possède son propre
  lease renouvelé pendant l'exécution ;
- `--real` désactive la simulation et échoue fermé tant qu'aucun runner fixe ni
  exécuteur agent complet n'est configuré ;
- le programme configuré est du code de confiance de l'opérateur. Le cwd dédié,
  l'environnement minimal, les limites et l'arrêt de l'arbre de processus rendent
  l'exécution contrôlable, mais ne constituent pas une sandbox OS : le programme
  conserve les droits du compte Windows et sa politique réseau ;
- une racine projet sélectionne le cwd sans limiter les fichiers lisibles par ce compte.
  Ne pas partager un worker entre projets non mutuellement fiables : utiliser un compte,
  conteneur ou VM et un pare-feu dédiés à chaque frontière de confiance ;
- la résolution canonique ne verrouille pas l'identité d'un chemin jusqu'au spawn.
  Protéger par ACL les exécutables, profils, dossiers de `PATH`, racines et parents
  contre tout remplacement ou reparse point concurrent ;
- ACP lance un seul CLI de premier niveau mais ne bloque ni ne compte les processus ou
  agents descendants ; `spawned_agents=1` décrit seulement l'invocation gérée ;
- sous Windows, tout spawn du runner est enfermé dans un Job Object dès sa création
  (voir § 7) ; la convergence native Toolhelp reste une vérification indépendante et
  fait échouer le run si l'arrêt n'est pas prouvé ;
- utiliser un compte non privilégié, une racine dédiée et un pare-feu/une isolation
  système adaptés avant d'exécuter le backend sur des dépôts non fiables ;
- l'évaluateur Hermes doit être réellement configuré pour qu'une exécution réelle
  puisse réussir. Le provider `mock` est refusé avant enrôlement, démarrage ou appel
  direct de la boucle réelle ; un verdict provenant d'un autre provider est refusé.
  L'indisponibilité de l'évaluateur n'est jamais transformée en approbation.

## 7. Clôture d'arrêt Windows (Job Object)

### Pourquoi

Sur Windows, l'arrêt d'un arbre de processus par énumération Toolhelp
(`th32ParentProcessID`) suppose que la filiation reste observable. Or un
**lanceur** casse cette filiation : `.venv\Scripts\python.exe` exécute
l'interpréteur réel dans un processus enfant, exactement comme `npx.cmd` ou `uvx`.
L'arbre réel est alors `runner → lanceur P → programme R → descendant G`. Quand R
puis P sortent, G n'a plus de parent connu : l'énumération conclut « tout est
arrêté » alors que G survit avec les tubes hérités, la capture n'atteint jamais
EOF et un run réussi devient un `timed_out` / `output_stream_timeout`.

### Ce que fait le worker

Au spawn (`spawn_fenced_process`) :

1. `creationflags = CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED` — le programme
   est créé mais n'exécute pas encore la moindre instruction ;
2. `CreateJobObjectW` (job anonyme) avec `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` et
   **sans** `BREAKAWAY_OK` : aucun descendant ne peut quitter le job ;
3. `AssignProcessToJobObject` sur un handle ouvert par PID
   (`PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION |
   SYNCHRONIZE`), affectation revérifiée par `IsProcessInJob` ;
4. reprise du thread initial (`CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD)` →
   `OpenThread(THREAD_SUSPEND_RESUME)` → `ResumeThread`).

Toute erreur de cette séquence tue le processus suspendu et retourne
`status="spawn_failed"`, `termination_reason="job_assignment_failed"`. Il n'existe
aucun chemin où le programme s'exécute hors de son job.

À l'arrêt (`terminate_process_tree`) : éventuel `CTRL_BREAK_EVENT` de grâce, puis
`TerminateJobObject(job, 1)`, puis attente bornée de
`QueryInformationJobObject(JobObjectBasicAccountingInformation).ActiveProcesses == 0`.
La passe Toolhelp existante est conservée comme vérification indépendante :
`process_tree_stopped` n'est vrai que si **le job est vide** et que la passe native
confirme. À la fin du run, la fermeture du handle du job sert de dernier filet
(`KILL_ON_JOB_CLOSE`) sans jamais requalifier un verdict déjà figé.

Sur POSIX, rien ne change : `start_new_session=True` puis `killpg` (SIGTERM, grâce,
SIGKILL).

### Conséquences et limites

- aucun descendant ne survit à la tentative, même lancé par un lanceur `.venv`,
  `npx.cmd` ou `uvx` ; un run normal vide aussi le job avant de rendre son verdict ;
- le job ne limite ni CPU, ni mémoire, ni réseau : c'est une clôture d'arrêt, pas
  une sandbox ;
- les jobs imbriqués exigent Windows 8 / Server 2012 ou ultérieur. Sur un système
  antérieur, ou si le worker tourne déjà dans un job qui refuse l'imbrication,
  l'affectation échoue et le run est refusé (`job_assignment_failed`) — jamais
  exécuté hors clôture ;
- le compte de service du worker doit pouvoir créer un job et ouvrir ses propres
  processus avec `PROCESS_SET_QUOTA` ; une stratégie de sécurité qui l'interdit
  désactive de fait le backend réel, de façon visible.

## 8. Sonde MCP stdio (optionnelle)

Un serveur MCP en transport `stdio` s'exécute sur la machine du worker : l'API ne
peut pas l'interroger elle-même. Le worker peut prendre en charge ces sondes, mais
seulement si l'opérateur l'autorise explicitement.

| Variable | Rôle |
|---|---|
| `ACP_WORKER_MCP_STDIO_ENABLED` | `0` (défaut) ou `1` |
| `ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES` | chemins **absolus** séparés par `;` (Windows) — exigé si activé |
| `ACP_WORKER_MCP_STDIO_TIMEOUT_SECONDS` | 1 à 120, défaut 20 |

La capacité `mcp_stdio_probe` n'est annoncée que si le drapeau vaut `1` **et** que
l'allowlist n'est pas vide ; `agent-company-worker doctor` affiche
`mcp_stdio_probe: enabled|disabled` et le nombre d'exécutables autorisés (jamais
leurs chemins). La boucle de sonde ne démarre que si la capacité est annoncée par
les credentials et que le worker n'est pas en simulation.

Garanties de la sonde :

- la commande reçue doit être **strictement égale** (après `Path.resolve` et
  normalisation de casse) à une entrée de l'allowlist ; sinon échec `not_allowed`,
  **sans aucun lancement** ;
- jamais de shell : le spawn passe par la même clôture que le runner (Job Object
  Windows, session POSIX) et l'arbre est arrêté à la fin de l'échange ;
- environnement minimal (`PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, `HOME`,
  `USERPROFILE`) augmenté des seules variables envoyées par l'API ; aucun secret du
  worker n'est hérité et aucune valeur n'est journalisée ;
- **expurgation du retour** : les valeurs d'environnement injectées par l'API
  (valeurs de secrets résolues depuis le coffre) sont remplacées par `***` dans
  `stderr_tail`, `server_info`, `protocol_version` et les outils avant d'être
  postées. Un serveur MCP bavard qui réécrit un jeton reçu ne peut donc pas le
  publier dans `GET /mcp/probes/{id}`, lisible par tout utilisateur autorisé.
  **Toute valeur non vide est masquée, sans plancher de longueur** : un secret d'un à
  trois caractères rend le diagnostic bruyant, mais la règle « aucun secret ne sort du
  serveur » prime. La règle est écrite une seule fois dans
  `acp_contracts.redaction` et l'API réapplique la même expurgation au résultat posté
  par le runner : un runner bavard ou compromis ne peut pas faire écrire une valeur
  lisible ;
- répertoire de travail : celui fourni s'il est absolu et existant, sinon un
  répertoire temporaire neuf supprimé à la fin ;
- échange JSON-RPC ligne par ligne (`initialize` avec `protocolVersion`
  `2025-06-18`, `notifications/initialized`, `tools/list` paginé), `stderr` borné à
  4096 caractères, descriptions d'outils bornées à 2000 caractères ;
- réponse `initialize` **complète exigée** : la spécification MCP 2025-06-18 impose
  `protocolVersion` et `serverInfo` ; une réponse qui en manque est un `protocol`,
  jamais un succès à `protocol_version: null` (que le contrat `McpDiscovery` ne
  pourrait pas représenter) ;
- aucun faux succès : `disabled`, `invalid_request`, `not_allowed`, `spawn_error`,
  `job_assignment_failed`, `timeout`, `protocol`, `closed`, `server_error`,
  `too_many_tools` ou `process_tree_cleanup_failed` sont retournés avec
  `status="failed"`. Une pagination sans fin (plus de 20 pages ou 500 outils) est
  refusée plutôt que tronquée silencieusement, et une **page unique** contenant plus
  d'outils que la capacité restante l'est aussi : une liste tronquée présentée comme
  complète serait un faux succès.

Ce que la sonde ne fait pas : elle n'isole pas le programme. Le Job Object borne son
arbre de processus, il ne limite ni CPU, ni mémoire, ni réseau, et le programme
conserve les droits du compte Windows du worker. L'allowlist d'exécutables est donc le
contrôle qui compte : n'y inscrire que des binaires de confiance.
