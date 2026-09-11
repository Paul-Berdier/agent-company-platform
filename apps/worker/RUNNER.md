# Runner local réel

Le worker peut lancer un unique programme local approuvé par l'opérateur. La
mission ne fournit jamais de commande, d'exécutable ou d'arguments. Elle arrive
au programme sous la forme d'un fichier `request.json` versionné, placé dans un
répertoire neuf propre à la tentative.

## Configuration

Le mode réel échoue fermé tant que les deux variables suivantes ne sont pas
définies :

- `ACP_WORKER_RUNNER_ARGV_JSON` : tableau JSON non vide. Le premier élément doit
  être le chemin absolu d'un exécutable existant, situé hors de la racine des
  runs. Les autres éléments sont des arguments fixes de confiance.
- `ACP_WORKER_RUN_ROOT` : racine locale dédiée aux répertoires de tentative.

Limites facultatives :

- `ACP_WORKER_RUN_TIMEOUT_SECONDS` : 300 secondes par défaut, 24 heures maximum ;
- `ACP_WORKER_RUN_MAX_OUTPUT_BYTES` : 1 Mio par défaut et par flux, 16 Mio maximum ;
- `ACP_WORKER_RUN_ENV_ALLOWLIST` : noms de variables supplémentaires séparés par
  des virgules ; aucun secret worker, gateway, Codex ou Claude n'est transmis
  implicitement ;
- `ACP_WORKER_RUN_TERMINATE_GRACE_SECONDS` : délai avant arrêt forcé, 1 seconde
  par défaut et 10 secondes maximum.

`ACP_API_URL` et `ACP_PROVIDER_GATEWAY_URL` doivent être des origines sans chemin.
HTTP est accepté uniquement sur une adresse loopback ; tout service distant exige
HTTPS avant qu'un secret d'enrôlement, un Bearer worker ou un jeton gateway soit
envoyé. `ACP_WORKER_SIMULATION` accepte exclusivement `1` ou `0`.

Exemple PowerShell avec un programme local déjà installé dans un emplacement de
confiance :

```powershell
$env:ACP_WORKER_RUNNER_ARGV_JSON = '["C:\\Python\\python.exe","C:\\acp-runner\\runner.py"]'
$env:ACP_WORKER_RUN_ROOT = 'C:\acp-runs'
agent-company-worker register --real
agent-company-worker start
```

Le chemin absolu de `request.json` est ajouté comme dernier argument. Le
programme reçoit aussi `ACP_RUN_REQUEST_PATH`, `ACP_RUN_DIRECTORY`, `ACP_RUN_ID`,
`ACP_RUN_ATTEMPT_ID` et `ACP_RUN_FENCING_TOKEN`. Son répertoire courant est le
répertoire de tentative ; stdin est fermé.

Les répertoires et preuves locales sont conservés. `request.json` est créé avant le
spawn ; `evidence.json` est écrit atomiquement et synchronisé sur disque avant tout
envoi du verdict à l'API. Si le répertoire d'une même tentative existe déjà, le
worker refuse un rejeu implicite au lieu de l'écraser.

Pour une mission, `duration_seconds` est une deadline globale calculée dès la
prise en charge du claim. Elle couvre la planification, les mises à jour de
progression, le processus et l'évaluation ; chaque opération reçoit seulement
le temps restant. Elle peut uniquement réduire le timeout local et ne peut
jamais augmenter la limite configurée par l'opérateur. Les quelques appels de
terminaison nécessaires pour enregistrer le verdict restent effectués après
l'expiration de ce budget.

## Verdict et preuve

Le runner capture stdout et stderr en continu sans conserver plus que la limite
configurée, tout en calculant le SHA-256 du flux complet. La preuve structurée
contient notamment la tentative et son fencing token, les heures, la durée, le
code de sortie, la cause de terminaison, les limites, les tailles, les indicateurs
de troncature et les empreintes.

Un succès exige cumulativement un processus réellement lancé, un code de sortie
zéro, une preuve structurée et un verdict positif explicite du provider-gateway.
Un spawn impossible, un code non nul, un timeout, une perte de lease, un fencing
token discordant ou une demande d'arrêt ne peut jamais devenir un succès. Une
simulation reste `blocked` avec validation technique non exécutée.

Si l'évaluation du provider échoue après un processus réussi, le worker conserve
et transmet la preuve réelle et marque la validation technique du processus
comme réussie, mais termine le run en `blocked` : une indisponibilité ne vaut
jamais approbation.

Le renouvellement du lease pilote l'arrêt. Sous POSIX, le worker termine la
session de processus avec `SIGTERM` puis `SIGKILL`. Sous Windows, il cible le
nouveau groupe puis utilise `taskkill.exe /T /F` par argv absolu, sans shell, pour
forcer l'arrêt de l'arbre. Ce nettoyage est aussi effectué après la sortie normale
du parent afin qu'un descendant ne survive pas à une tentative déclarée terminée.

## Limites de sécurité

Ce backend est une frontière locale reproductible, pas une sandbox de système
d'exploitation. Il ne fournit pas encore de quota CPU, mémoire ou disque, ni de
filtrage réseau sortant. Le programme configuré et le compte Windows qui exécute
le worker restent dans la base de confiance. La racine des runs doit donc être
privée à ce compte et l'exécutable ainsi que ses scripts fixes doivent résider
dans un emplacement non modifiable par les projets ou missions.

En conséquence, la politique mission est volontairement conservatrice et
vérifiée avant tout spawn : seul le mode `supervised` est accepté, avec
`allowed_actions` et `approval_required_actions` vides et uniquement des
ressources déclarées en lecture. Toute ressource en écriture, délégation d'action
ou action soumise à approbation est refusée. Le worker n'implémente pas de circuit
d'approbation et ne prétend pas isoler les droits du programme approuvé sur l'OS.
