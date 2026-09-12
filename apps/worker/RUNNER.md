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

## Tests web (Playwright)

Le worker peut exécuter une suite de tests web à la place du programme local
lorsque la mission déclare une ressource `kind = "web_test_suite"` **et** que la
capacité `web_tests` est annoncée. Sans l'une des deux, le comportement du Lot C
reste strictement inchangé.

**La plateforme n'installe jamais Playwright.** L'opérateur l'installe lui-même
sur le runner (`npm i -D @playwright/test && npx playwright install`) et déclare
l'argv absolu à lancer. Le processus de test ne reçoit **jamais** un credential
de la plateforme : il écrit un rapport NDJSON local que le worker authentifié
ingère ensuite.

### Configuration

- `ACP_WORKER_WEBTEST_ENABLED` : `0` (défaut) ou `1` ;
- `ACP_WORKER_WEBTEST_ARGV_JSON` : tableau JSON non vide. Le premier élément est
  le chemin absolu d'un exécutable existant, par exemple
  `["C:\\Program Files\\nodejs\\node.exe","C:\\projets\\app\\node_modules\\@playwright\\test\\cli.js","test"]` ;
- `ACP_WORKER_WEBTEST_CWD` : racine de projet absolue et existante ;
- `ACP_WORKER_WEBTEST_TIMEOUT_SECONDS` : 900 par défaut, 7200 au maximum. La
  `duration_seconds` de la mission peut seulement réduire ce délai ;
- `ACP_WORKER_WEBTEST_MAX_ARTIFACT_BYTES` : 200 Mio par défaut. C'est le budget
  **cumulé** de pièces jointes d'une tentative : une fois épuisé, les pièces
  jointes suivantes sont refusées explicitement, sans perdre le rapport ;
- `ACP_WORKER_WEBTEST_ENV_ALLOWLIST` : noms séparés par des virgules. Ce sont les
  seules variables de l'environnement du worker transmises à la suite, et la
  liste d'expurgation appliquée à tout ce que le rapport republie. Un secret de
  contrôle de la plateforme (`ACP_GATEWAY_SERVICE_TOKEN`, `HERMES_API_KEY`, …) y
  est refusé à la configuration. N'y placez jamais un secret dans
  `ACP_WORKER_WEBTEST_ARGV_JSON` : `doctor` affiche l'argv en clair.

La capacité `web_tests` n'est annoncée que si la configuration est complète **et**
que le mode enregistré est le mode réel. Ce mode est celui que `register`
enregistre : `agent-company-worker register --real` suffit, même si
`ACP_WORKER_SIMULATION` vaut encore `1`.

`agent-company-worker doctor` affiche `web_tests`, l'argv, la racine de projet,
le délai, le plafond d'artefacts et le **nombre** de noms allowlistés — jamais
une valeur d'environnement. Trois états sont possibles :

| `web_tests` | Signification |
|---|---|
| `disabled` | `ACP_WORKER_WEBTEST_ENABLED` absent ou `0`, ou configuration incomplète. |
| `enabled` | Configuration complète **et** capacité `web_tests` présente dans `capabilities` : une mission `web_test_suite` sera exécutée par la suite Playwright. |
| `enabled_not_announced` | Configuration complète mais mode simulé : la capacité n'est **pas** annoncée et une mission `web_test_suite` repartirait vers le programme local du Lot C. Enregistrez le worker avec `--real` (ou posez `ACP_WORKER_SIMULATION=0`). |

```powershell
$env:ACP_WORKER_SIMULATION = '0'
$env:ACP_WORKER_WEBTEST_ENABLED = '1'
$env:ACP_WORKER_WEBTEST_ARGV_JSON = '["C:\\Program Files\\nodejs\\node.exe","C:\\projets\\app\\node_modules\\@playwright\\test\\cli.js","test"]'
$env:ACP_WORKER_WEBTEST_CWD = 'C:\projets\app'
agent-company-worker doctor
```

### Déroulement d'une tentative

1. Un répertoire de sortie **neuf** est créé sous
   `<ACP_WORKER_RUN_ROOT>\web-tests\<task_run_id>\attempt-<n>`. S'il existe déjà,
   la tentative échoue plutôt que d'écraser un rejeu.
2. L'environnement transmis est le socle minimal (`PATH`, `TEMP`, `SYSTEMROOT`,
   `APPDATA`, …) augmenté de l'allowlist, plus
   `ACP_REPORT_FILE=<sortie>\report.ndjson` et `PLAYWRIGHT_HTML_OPEN=never`.
   Configurez `reporter: [['@acp/playwright-reporter']]` dans
   `playwright.config.ts` pour que ce fichier soit écrit.
3. Le lancement passe par **exactement la même clôture** que le runner local
   (`spawn_fenced_process` / `terminate_process_tree`) : aucun shell, session
   POSIX ou Job Object Windows, arrêt d'arbre vérifié. `stdout.log` et
   `stderr.log` sont écrits dans le répertoire de sortie ; aucun tube hérité ne
   peut donc bloquer la fin de la tentative.
4. Le NDJSON est lu ligne par ligne. Une ligne illisible est **comptée et
   signalée** sans faire échouer le reste du rapport.
5. Chaque pièce jointe est résolue canoniquement : seul un fichier réellement
   situé sous le répertoire de sortie est téléversé. Les `..`, les chemins
   absolus et **tout lien symbolique**, même pointant à l'intérieur, sont refusés
   et listés dans la preuve.
6. Le rapport est transmis à `POST /workers/{id}/test-runs` avec le fencing token
   de la tentative, après expurgation des valeurs allowlistées.
7. Une preuve de mission `web_tests` résume les totaux, le code de sortie et
   l'identifiant du `test_run`. **Jamais une image** : les médias restent des
   artefacts référencés par empreinte.

### Verdict

Le succès technique exige **cumulativement** : un code de sortie nul, un rapport
`run_end` complet, au moins un cas exécuté, aucun `unexpected`, `interrupted` ni
`timedOut`, aucune ligne de rapport illisible, aucune pièce jointe refusée, une
ingestion API acceptée et un arrêt d'arbre prouvé. `flaky` et `skipped`
n'empêchent pas le succès mais restent affichés distinctement : les statuts
`passed`, `failed`, `timedOut`, `skipped` et `interrupted` ne sont jamais réduits
à vert/rouge.

Un NDJSON absent ou vide est un échec explicite — « aucun résultat de test
produit » — jamais un succès. Un rapport partiel et des pièces jointes refusées
sont transmis quand même : la preuve incomplète est visible, elle n'est pas
effacée.

## Limites de sécurité

Ce backend est une frontière locale contrôlée et testable, pas une sandbox de système
d'exploitation. Il ne fournit pas encore de quota CPU, mémoire ou disque, ni de
filtrage réseau sortant. Le programme configuré et le compte Windows qui exécute
le worker restent dans la base de confiance. La racine des runs doit donc être
privée à ce compte et l'exécutable ainsi que ses scripts fixes doivent résider
dans un emplacement non modifiable par les projets ou missions.

Sous Windows, le spawn est désormais **fencé par un Job Object** : le processus est
créé suspendu, affecté à un job anonyme `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` sans
`BREAKAWAY_OK`, puis repris. Aucune instruction du programme ne s'exécute hors du
job, et aucun descendant ne peut en sortir — y compris sous un lanceur
intermédiaire (`python.exe` d'un `.venv`, `npx.cmd`, `uvx`) qui casse la filiation
observable par Toolhelp. À l'arrêt, `TerminateJobObject` puis l'attente de
`ActiveProcesses == 0` constituent la preuve ; la passe Toolhelp est conservée comme
vérification indépendante. Si le job ne peut pas être créé, l'affectation refusée ou
la reprise impossible, le processus suspendu est tué et le run échoue en
`spawn_failed` / `job_assignment_failed` : jamais une exécution hors clôture.

La sonde MCP stdio optionnelle (`ACP_WORKER_MCP_STDIO_*`) réutilise exactement la
même clôture de spawn et d'arrêt ; elle est documentée dans
`docs/workers/windows-worker.md` § 8. Les tests web (`ACP_WORKER_WEBTEST_*`)
réutilisent eux aussi cette clôture : un navigateur Playwright et ses processus
enfants appartiennent au même Job Object que le processus de test, et un arrêt
d'arbre non prouvé interdit tout succès.

La terminaison d'arbre reste une frontière d'arrêt, pas une primitive d'isolation :
le job ne limite ni le CPU, ni la mémoire, ni le réseau, et un descendant POSIX qui
appelle `setsid()` sort du groupe de session. Un déploiement acceptant un exécutable
non fiable doit donc y ajouter un cgroup, des quotas de job ou une portée de service
supervisée.

En conséquence, la politique mission est volontairement conservatrice et
vérifiée avant tout spawn : seul le mode `supervised` est accepté, avec
`allowed_actions`, `forbidden_actions` et `approval_required_actions` vides et uniquement des
ressources déclarées en lecture. Toute ressource en écriture, délégation d'action
ou action soumise à approbation est refusée. Le worker n'implémente pas de circuit
d'approbation et ne prétend pas isoler les droits du programme approuvé sur l'OS.
