# Poste Windows d'ACP (`apps/poste`)

Ancien `apps/worker`, renommé et réduit à l'étape P0 de la refonte « Hermes au centre »
(`docs/refonte/plan.md`). Dans l'architecture cible, le poste n'écoute sur aucun port :
il réclamera en HTTPS sortant les demandes créées par l'outil `poste_deleguer` du
greffon Hermes `acp-poste`, sur le tableau kanban dédié `poste`, et les exécutera avec
Codex CLI ou Claude Code sous les connexions du propriétaire. **Cette voie n'existe pas
encore : elle arrive en P5.** Aujourd'hui, le poste ne parle à aucun serveur.

## Ce qui reste

| Module | Rôle |
|---|---|
| `executors.py` | commandes Codex et Claude Code bornées (lecture seule par défaut, Codex en `workspace-write` seulement sur demande explicite), validation des chemins projet, verrou d'écriture interprocessus |
| `local_runner.py` | clôture de processus : Job Object Windows (`KILL_ON_JOB_CLOSE`, processus créé suspendu), environnement par liste blanche, captures bornées, preuve `evidence.json` |
| `credentials_protection.py` | chiffrement DPAPI lié au compte Windows courant (servira au jeton machine en P5) |
| `subscription_quotas.py` | sondes des quotas réels : `codex app-server` et fichier de la ligne d'état Claude Code |
| `claude_statusline.py` | ligne d'état Claude Code qui recopie `rate_limits.five_hour` et `seven_day` |
| `config.py` | `PosteConfig` ; `normalize_service_origin` impose HTTPS hors boucle locale (pour l'origine de Hermes en P5) |
| `local_log.py` | journal JSONL local, sans secret |
| `cli.py` | commande `acp-poste` (ci-dessous) |

Le contrat Python des quotas est partagé avec le greffon :
`hermes/plugins/acp-poste/contrat` (distribution `acp-poste-contrat`).

## Ce qui a été retiré

Tout ce qui ne servait qu'à l'API ACP : boucle de claims (`main.py`), enrôlement et
état du worker (`state.py`, commandes `register`, `start`, `doctor` de l'ancienne CLI),
capacités annoncées (`capabilities.py`), cycle de vie Hermes piloté par l'API
(`hermes_lifecycle.py`), équipes (`multi_agent.py`), planificateur
(`automation_scheduler.py`), budgets (`budget.py`), sonde et passage de serveurs MCP
(`mcp_probe.py`, `mcp_execution.py`), tests web Playwright (`web_tests.py`),
extensions (`extensions.py`), points de reprise (`checkpoints.py`), la boucle d'envoi
des quotas à l'API et la lecture des « claims » par le runner local. Le code reste
consultable sous l'étiquette `archive/acp-0.10.0-avant-hermes`.

## Installation et tests

Sous Windows, le venv doit être bâti sur le Python de **python.org**, jamais sur celui
du Microsoft Store : l'interpréteur réel d'un venv Store sort du Job Object et les tests
d'arbre de processus échouent. `scripts/setup.ps1` le refuse explicitement.

```powershell
./scripts/setup.ps1
.venv\Scripts\python.exe -m pytest -q
```

`pytest.ini` place les sources de l'arbre courant (`apps/poste/src`,
`hermes/plugins/acp-poste/contrat`) en tête du chemin d'import : un worktree teste son
propre code, jamais celui d'un autre checkout.

## Commande `acp-poste`

Aucune de ces commandes n'ouvre de connexion réseau.

- `acp-poste diagnostic` : configuration reconnue (exécuteurs activés, nombre de racines
  projet, runner local, état du relevé des quotas), sans chemin ni secret ;
- `acp-poste quotas` : relève maintenant Codex et Claude Code et affiche les relevés
  JSON. Une source absente devient un état explicite (`cli_missing`, `not_signed_in`,
  `unavailable`…), jamais une valeur inventée ;
- `acp-poste journal --fin N` : fin du journal local.

Une configuration invalide est refusée en français, code de sortie 2.

## Configuration

Jusqu'à P5, la configuration vient de l'environnement. Les noms `ACP_WORKER_*` sont
conservés tels quels pour les modules repris sans changement ; P5 les remplace par la
politique locale `%LOCALAPPDATA%\ACP\poste.toml` décrite dans le plan.

| Variable | Rôle |
|---|---|
| `ACP_POSTE_STATE_DIR` | dossier d'état (journal) ; défaut `%USERPROFILE%\.acp-poste` |
| `ACP_WORKER_CODEX_ENABLED`, `ACP_WORKER_CODEX_EXECUTABLE`, `ACP_WORKER_CODEX_HOME` | exécuteur Codex : opt-in, exécutable absolu, profil dédié |
| `ACP_WORKER_CLAUDE_ENABLED`, `ACP_WORKER_CLAUDE_EXECUTABLE`, `ACP_WORKER_CLAUDE_CONFIG_DIR` | exécuteur Claude Code, mêmes règles |
| `ACP_WORKER_EXECUTOR_PROJECTS_JSON` | racines projet autorisées (`{"alias": "C:/chemin"}`) |
| `ACP_WORKER_EXECUTOR_PATH`, `ACP_WORKER_EXECUTOR_TIMEOUT_SECONDS`, `ACP_WORKER_EXECUTOR_TERMINATE_GRACE_SECONDS` | `PATH` des exécuteurs, délai, grâce avant arrêt forcé |
| `ACP_WORKER_RUNNER_ARGV_JSON`, `ACP_WORKER_RUN_ROOT` et `ACP_WORKER_RUN_*` | runner local à argv fixe (absent tant que ces deux variables manquent) |
| `ACP_WORKER_SUBSCRIPTION_QUOTAS`, `ACP_WORKER_QUOTA_INTERVAL_SECONDS` | relevé des quotas (`0`/`1`) et intervalle prévu pour l'envoi (P6) |
| `ACP_WORKER_QUOTA_CODEX_HOME`, `ACP_WORKER_QUOTA_CODEX_EXECUTABLE` | profil et exécutable Codex des quotas, si l'exécuteur Codex n'est pas activé (refusés sinon) |
| `ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT` | fichier de la ligne d'état ; défaut `%USERPROFILE%\.acp\quotas\claude-code.json` |

## Profil Codex dédié

Le poste n'utilise jamais `~/.codex`. Profil par défaut : `%USERPROFILE%\.acp\codex-home`,
ou celui de l'exécuteur Codex s'il est activé. La connexion est faite par le
propriétaire lui-même :

```powershell
New-Item -ItemType Directory -Force "$HOME\.acp\codex-home" | Out-Null
# Recommandé : identifiants dans le coffre du système plutôt qu'en clair (auth.json).
if (-not (Test-Path "$HOME\.acp\codex-home\config.toml")) {
  Set-Content "$HOME\.acp\codex-home\config.toml" 'cli_auth_credentials_store = "keyring"'
}
$env:CODEX_HOME="$HOME\.acp\codex-home"; codex login
```

Limite connue, reprise du plan : l'exécuteur Codex passe `--ignore-user-config`, qui
ignore ce réglage de `config.toml` ; P5 le passera en `-c` sur la ligne de commande.

## Ligne d'état Claude Code

Dans `~/.claude/settings.json` du propriétaire (barres obliques sous Windows) :

```json
{
  "statusLine": {
    "type": "command",
    "command": "C:/chemin/du/depot/.venv/Scripts/python.exe -m acp_poste.claude_statusline"
  }
}
```

Une ligne d'état existante se place après `--` : elle reçoit la même entrée et son
affichage est repris tel quel
(`… -m acp_poste.claude_statusline -- powershell -NoProfile -File C:/…/statusline.ps1`).
Le module ne recopie que `rate_limits.five_hour` et `rate_limits.seven_day`, par
écriture atomique, dans `%USERPROFILE%\.acp\quotas\claude-code.json` (ou
`ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT`, à définir alors pour le poste **et** pour Claude
Code). Il ne lève jamais et sort toujours avec le code 0.

**Changement de module** : une ligne d'état réglée sur l'ancien
`python -m acp_worker.claude_statusline` doit être réglée sur `acp_poste`.

## Limites

- Le Job Object est une frontière d'arrêt, pas une sandbox : il ne limite ni le CPU, ni
  la mémoire, ni le réseau ; le compte Windows qui exécute le poste reste dans la base
  de confiance. Le plan recommande un compte Windows local dédié (P5).
- Les bacs à sable de Codex et de Claude Code sous Windows natif ne sont pas prouvés ;
  la preuve est attendue en P5 et P7.
- Le chemin Codex « compte connecté » n'a été éprouvé que contre un faux app-server
  dont les réponses suivent le schéma publié par Codex 0.156.1
  (`tests/fixtures/codex_app_server_0_156_1`).
