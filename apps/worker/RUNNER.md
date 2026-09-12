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
envoyé. `ACP_WORKER_SIMULATION` accepte exclusivement `1` ou `0`. Le mode réel
refuse `ACP_ORCHESTRATOR_PROVIDER=mock` avant l'enrôlement et le démarrage. Les
clients inter-services du worker ignorent `HTTP_PROXY`/`HTTPS_PROXY` pour empêcher
le détournement d'un Bearer loopback par la configuration ambiante.

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

stdout/stderr sont des données non fiables et potentiellement sensibles : ils sont
bornés mais ne peuvent pas être expurgés automatiquement. Ne jamais allowlister un
secret destiné au programme, protéger la racine des runs et définir une rétention
adaptée aux preuves locales.

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

Le renouvellement du lease pilote l'arrêt. Sous POSIX, le worker termine le groupe
de processus avec `SIGTERM` puis `SIGKILL`. Sous Windows, il accorde d'abord la
grâce configurée via `CTRL_BREAK`, puis utilise `taskkill.exe /T /F` par argv
absolu, sans shell. Une vérification native Toolhelp épingle les handles de la
famille et converge sur plusieurs snapshots bornés. Le nettoyage est aussi
effectué après la sortie normale du parent ; s'il ne peut pas être confirmé, un
code de sortie zéro devient `exit_process_tree_cleanup_failed`, jamais un succès.

## Limites de sécurité

Ce backend est une frontière locale contrôlée et testable, pas une sandbox de système
d'exploitation. Il ne fournit pas encore de quota CPU, mémoire ou disque, ni de
filtrage réseau sortant. Le programme configuré et le compte Windows qui exécute
le worker restent dans la base de confiance. La racine des runs doit donc être
privée à ce compte et l'exécutable ainsi que ses scripts fixes doivent résider
dans un emplacement non modifiable par les projets ou missions.

La terminaison d'arbre n'est pas une primitive d'isolation : Toolhelp ne remplace
pas un Job Object Windows attribué au spawn, et un descendant POSIX qui appelle
`setsid()` sort du groupe. Un déploiement acceptant un exécutable non fiable doit
donc ajouter un Job Object, un cgroup ou une portée de service supervisée ; ce cas
reste hors du backend local actuel et échoue la frontière de confiance annoncée.

En conséquence, la politique mission est volontairement conservatrice et
vérifiée avant tout spawn : seul le mode `supervised` est accepté, avec
`allowed_actions`, `forbidden_actions` et `approval_required_actions` vides et uniquement des
ressources déclarées en lecture. Toute ressource en écriture, délégation d'action
ou action soumise à approbation est refusée. Le worker n'implémente pas de circuit
d'approbation et ne prétend pas isoler les droits du programme approuvé sur l'OS.
