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
./scripts/dev.ps1
```

Dans un second terminal, fournir le même secret uniquement pour
l'enregistrement :

```powershell
$env:ACP_WORKER_REGISTRATION_TOKEN = "<le-secret-généré>"
./.venv/Scripts/agent-company-worker.exe register --name dev-windows-01
Remove-Item Env:ACP_WORKER_REGISTRATION_TOKEN
```

Le processus API conserve la valeur héritée au démarrage. Après les enrôlements
prévus, arrêter l'API, supprimer ou faire tourner ce secret dans son environnement,
puis la relancer ; sinon ce même jeton continue d'autoriser de nouveaux workers.
Pour un nouvel enrôlement ultérieur, utiliser une nouvelle valeur temporaire.

`register` détecte automatiquement `git`, Claude Code, Codex CLI et Blender
lorsqu'ils sont présents dans le `PATH`. Les capacités de base
`filesystem_project` et `shell_restricted` sont toujours annoncées. Une liste
explicite peut être fournie plusieurs fois :

```powershell
./.venv/Scripts/agent-company-worker.exe register `
  --name build-windows-01 `
  --capability git `
  --capability asset_validation `
  --max-concurrency 2
```

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
| `ACP_WORKER_STATE_DIR` | `%USERPROFILE%\.agent-company-worker` | état et journal locaux |
| `ACP_WORKER_MAX_CONCURRENCY` | `1` | slots annoncés, entier de 1 à 32 |
| `ACP_WORKER_SIMULATION` | `1` | `1` simulation bloquée ; `0` réel ; toute autre valeur est refusée |
| `ACP_ORCHESTRATOR_PROVIDER` | `mock` | simulation uniquement ; interdit en mode réel |

Les deux URL de service sont des origines sans chemin, query, fragment ou userinfo.
HTTP est accepté uniquement pour `localhost`, `127.0.0.0/8` et `::1` ; une machine
distante doit exposer l'API et le gateway en HTTPS.

## 4. Configurer le backend de processus réel

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
./.venv/Scripts/agent-company-worker.exe register --name dev-windows-01 --real
./.venv/Scripts/agent-company-worker.exe doctor
./.venv/Scripts/agent-company-worker.exe start
```

`register --real` vérifie la configuration locale puis enrôle le worker auprès de
l'API ; il ne sonde pas Hermes. Avant `start`, exécuter `doctor` : il vérifie la
liveness API/gateway, l'authentification worker et la disponibilité authentifiée du
provider configuré. Son code est non nul si l'une de ces conditions manque.

Un arrêt utilisateur, un timeout, la perte du lease ou un fencing token obsolète
arrête le groupe de processus et conserve une preuve structurée. `evidence.json`
est écrit atomiquement dans le répertoire de tentative avant le PATCH terminal ;
un conflit réseau ne supprime donc pas la preuve locale. Le répertoire existant
d'une tentative n'est jamais réutilisé implicitement.

stdout/stderr restent des contenus non fiables et potentiellement sensibles. Ils
sont bornés mais non expurgés avant `evidence.json` et l'API. Ne jamais allowlister
un secret destiné au programme ; restreindre l'accès à la racine des runs et définir
une politique de rétention.

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
- `--real` désactive la simulation et échoue fermé tant que l'argv et la racine du
  backend local ne sont pas configurés ;
- le programme configuré est du code de confiance de l'opérateur. Le cwd dédié,
  l'environnement minimal, les limites et l'arrêt de l'arbre de processus rendent
  l'exécution contrôlable, mais ne constituent pas une sandbox OS : le programme
  conserve les droits du compte Windows et sa politique réseau ;
- la convergence native Toolhelp confirme le nettoyage ou fait échouer le run,
  mais ne remplace pas un Job Object attaché dès le spawn ; fournir cette isolation
  système avant d'autoriser un programme susceptible d'échapper volontairement à
  son arbre ;
- utiliser un compte non privilégié, une racine dédiée et un pare-feu/une isolation
  système adaptés avant d'exécuter le backend sur des dépôts non fiables ;
- l'évaluateur Hermes doit être réellement configuré pour qu'une exécution réelle
  puisse réussir. Le provider `mock` est refusé avant enrôlement, démarrage ou appel
  direct de la boucle réelle ; un verdict provenant d'un autre provider est refusé.
  L'indisponibilité de l'évaluateur n'est jamais transformée en approbation.
