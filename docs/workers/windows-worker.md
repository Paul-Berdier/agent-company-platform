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
doit être ni partagé, ni committé, ni copié dans les logs.

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
| `ACP_WORKER_MAX_CONCURRENCY` | `1` | slots annoncés lors de l'enrôlement |
| `ACP_WORKER_SIMULATION` | `1` | simulation explicite du MVP |
| `ACP_ORCHESTRATOR_PROVIDER` | `mock` | provider de planification |

## 4. Capacités exigées par une tâche

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

## 5. Sécurité et limites actuelles

- le secret d'enrôlement doit être long, aléatoire, retiré du terminal worker
  après `register` et remplacé en cas d'exposition ;
- en production, définir également `ACP_WORKER_TOKEN_PEPPER` uniquement sur
  l'API et utiliser HTTPS ;
- le heartbeat expire après 45 secondes et chaque task run possède son propre
  lease renouvelé pendant l'exécution ;
- `--real` désactive la simulation mais échoue volontairement tant qu'aucun
  exécuteur réel sécurisé n'est configuré ; aucune commande arbitraire n'est
  exécutée par ce socle.
