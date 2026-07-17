# Adaptateurs locaux Claude Code et Codex

La Phase 9 prépare deux exécuteurs locaux derrière le worker Windows. Ils ne
sont jamais importés par le cœur ni par le provider-gateway : le worker lance
un processus local seulement après attribution d'un run compatible.

Le socle actuel construit des commandes sans shell, limite leur environnement,
refuse tout projet hors de `ACP_WORKER_PROJECT_ROOT`, plafonne la durée et la
sortie, et parse les événements JSONL. Il n'est pas encore branché à la boucle
réelle : l'activation attend l'orchestration automatique des locks, des
approbations et d'un worktree Git isolé par run.

## Codex CLI

Mode préparé : `codex exec --json --ephemeral`, sandbox
`workspace-write`, approbations CLI désactivées pour éviter un processus bloqué
sans terminal. Les actions sensibles doivent donc avoir été approuvées par la
plateforme avant lancement. `danger-full-access` n'est jamais utilisé.

## Claude Code

Mode préparé : `claude -p`, sortie `stream-json`, nombre de tours borné et
`permission-mode plan`. Ce mode est volontairement en lecture/planification :
le passage à un mode d'édition exigera d'abord le worktree isolé et les règles
d'approbation de la plateforme.

## Secrets

Le sous-processus reçoit une allowlist de variables. Les variables `ACP_*` et
les secrets Hermes ne sont pas transmis. Seuls les identifiants propres à
l'exécuteur (`CODEX_API_KEY` ou `ANTHROPIC_API_KEY`) peuvent être propagés.
