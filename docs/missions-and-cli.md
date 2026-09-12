# Missions, runner local et CLI

Date d'état : 12 septembre 2026, Europe/Paris — version `0.5.0`

Le Lot C fournit une mission durable dans l'API métier, une exécution locale
configurée côté worker et le client `acp`. Le web et le CLI utilisent la même
ressource `/missions` : fermer l'un ou l'autre n'annule pas une tentative.

## Cycle d'une mission

Une mission contient un objectif, un résultat attendu, au moins un critère
d'acceptation, une autonomie explicite, ses ressources, un budget borné et une
durée maximale. Sa première tentative est créée atomiquement avec elle.

Les états d'exécution sont `queued`, `preparing`, `running`,
`waiting_approval`, `blocked`, `stopping`, `succeeded`, `failed`, `cancelled` et
`interrupted`. Trois notions restent distinctes :

- l'état technique de la tentative ;
- la validation technique (`pending`, `passed` ou `failed`) ;
- l'acceptation utilisateur (`pending`, `accepted` ou `rejected`).

Un succès exige un code de sortie nul, un évaluateur configuré qui répond
explicitement `approved: true` et au moins une preuve structurée. Une relance crée
une nouvelle tentative et un nouveau fencing token ; elle ne rejoue jamais la
tentative précédente. Une réussite ne peut être relancée qu'après rejet explicite
par l'utilisateur.

## Installer et utiliser `acp`

Les scripts `scripts/setup.ps1` et `bash scripts/setup.sh` installent le CLI en mode
développement dans `.venv`. Sous WSL, le script shell choisit `.venv-wsl` pour ne
pas réutiliser un environnement Windows incompatible ; `bash scripts/dev.sh` fait
le même choix. Activer l'environnement (`. .\.venv\Scripts\Activate.ps1` sous
Windows, `source .venv/bin/activate` sous Linux/macOS ou
`source .venv-wsl/bin/activate` sous WSL), ou appeler son exécutable directement.
La configuration/session WSL est stockée par défaut sous `~/.config` et reste
distincte de `%APPDATA%` côté Windows. Exemples :

```powershell
acp login
acp doctor
acp projects list
acp chat --project <project-id>
acp run --project <project-id> --goal "Vérifier le dépôt" `
  --expected "Rapport et code de sortie" `
  --accept "La commande configurée termine avec le code 0" `
  --max-tool-calls 10 --duration 300
acp runs watch <mission-id>
acp artifacts list --run <run-id>
acp open --run <run-id>
```

`Ctrl+C` quitte uniquement l'observation ; il n'arrête pas la mission. L'arrêt est
une commande séparée :

```powershell
acp runs stop <mission-id>
```

`--json` produit un objet JSON pour une commande ponctuelle et n'ouvre jamais
d'invite interactive ; `runs watch --json` émet les changements en NDJSON.
La configuration est écrite atomiquement dans le profil utilisateur, avec des
permissions `0600` lorsque le système les supporte. Elle contient la session et le
jeton CSRF : ne pas la partager ni la committer.

Le client HTTP ignore les variables proxy de l'environnement : une session liée à
une API loopback ne doit jamais transiter par un proxy implicite.

`acp run` et `acp runs stop` réservent leur clé d'idempotence sous verrou
interprocessus avant l'appel. Après une coupure, un `5xx`, une redirection ou une
réponse invalide, relancer exactement la même commande reprend la même opération.
`acp pending show` l'inspecte sans exposer de credential ; `acp pending discard`
l'abandonne avec confirmation (`--yes` est obligatoire sans invite), au risque
explicitement signalé de répéter un effet déjà appliqué.

Les commandes `automations` restent visibles comme capacité future et retournent un
code « non supporté » dans cette version ; elles seront raccordées au Lot F, sans
résultat simulé.

## Secrets, serveurs MCP et skills depuis le CLI

Le Lot D raccorde trois groupes supplémentaires à la même API et au même modèle de
session. Une valeur de secret n'est jamais acceptée en argument : seule l'entrée
standard est lue (`--value-stdin`), et une tentative avec `--value` est refusée.

```powershell
acp secrets status
acp secrets set GITHUB_TOKEN --value-stdin
acp secrets list
acp secrets rotate <secret-id> --value-stdin
acp secrets revoke <secret-id>

acp mcp catalog
acp mcp add github --url https://api.githubcopilot.com/mcp/ --header Authorization=@<secret-id>
acp mcp add local-fs --command /usr/local/bin/mcp-fs --arg --root --arg /data --runner <worker-id>
acp mcp test <server-id> --wait
acp mcp probes list
acp mcp probes approve <probe-id> --comment "lancement vérifié"
acp mcp tools <server-id>
acp mcp bind <server-id> --project <project-id> --tool search
acp mcp activate <server-id>
acp mcp export --format hermes --project <project-id>
acp mcp import ./config.toml --format codex

acp skills search rapport
acp skills install github:owner/repo@<sha40>:skills/rapport
acp skills files <skill-id>
acp skills cat <skill-id> SKILL.md
acp skills approve <skill-id> --revision 2
acp skills bind <skill-id> --project <project-id>
acp skills activate <skill-id>

acp projects extensions <project-id>
```

`acp mcp test` se comporte différemment selon le transport : en `http` le diagnostic
est exécuté immédiatement et le résultat est retourné ; en `stdio` il crée une
demande d'autorisation de lancement — rien n'est lancé avant `acp mcp probes approve`
et le claim du runner désigné. `--wait` interroge jusqu'à un état terminal et
retourne `0` seulement si le diagnostic a réussi ; `Ctrl+C` interrompt l'attente sans
annuler le diagnostic en cours.

`acp mcp import` lit le fichier localement (1 Mio au maximum) et envoie son contenu :
le serveur ne lit jamais un chemin fourni par le client. Sans `--apply`, la commande
affiche seulement l'aperçu normalisé, avec les secrets masqués.

## Contrat du backend local

Le worker réel n'exécute jamais un argv transmis par l'API. L'argv autorisé, la
racine des runs, le timeout, la limite de sortie et l'allowlist d'environnement sont
une configuration locale. Le programme reçoit seulement le chemin de l'enveloppe
JSON versionnée. Voir [Worker Windows distant](workers/windows-worker.md) pour la
configuration complète.

Le runner crée un cwd neuf par tentative, filtre l'environnement, capture et hache
stdout/stderr, borne la sortie et arrête l'arbre de processus en cas d'arrêt,
timeout, perte de lease ou fencing obsolète. Sous Windows, cet arrêt ne repose plus sur
la filiation des processus : le programme est créé suspendu et affecté à un Job Object
`KILL_ON_JOB_CLOSE` avant d'exécuter la moindre instruction, ce qui couvre le cas d'un
lanceur intermédiaire (`.venv`, `npx.cmd`, `uvx`) qui quitte avant son descendant. Voir
[Worker Windows distant](workers/windows-worker.md), § 7.

Ces contrôles ne sont pas une sandbox OS : l'adaptateur local configuré conserve les
droits et l'accès réseau du compte qui lance le worker, et le Job Object n'impose ni
quota CPU/mémoire ni politique réseau. L'emploi sur du code non fiable nécessite une
isolation système supplémentaire.

La politique Lot C est volontairement restrictive : seul le mode `supervised`, avec
`allowed_actions`, `forbidden_actions` et `approval_required_actions` toutes vides,
et avec des ressources éventuelles en lecture seule, peut atteindre le spawn. Une
interdiction déclarée est elle aussi refusée puisque ce backend sans sandbox ne peut
pas la garantir. Les autres missions restent visibles et échouent fermées jusqu'à la
livraison d'un backend capable d'appliquer leur politique.
Le mode réel refuse aussi `ACP_ORCHESTRATOR_PROVIDER=mock` avant enrôlement,
démarrage ou exécution programmée, puis exige que le verdict retourné identifie le
provider non simulé demandé.

## Limites vérifiées

- l'intégration est couverte avec transports et programmes déterministes locaux ;
  seule exception : le parcours MCP `http` a été rejoué contre une API et un serveur
  MCP réellement démarrés sur le bouclage, hors dépôt ;
- aucune instance Hermes réelle ni commande agentique payante n'a été lancée pour
  cette release ;
- l'autorisation d'un lancement MCP `stdio` est distincte du circuit d'approbation des
  missions : elle n'apparaît ni dans `acp approvals`, ni dans l'écran Missions ;
- SQLite et `create_all()` restent le chemin local ; les migrations PostgreSQL et
  la restauration sont reportées au Lot H ;
- le suivi web/CLI interroge l'API ; le flux authentifié et rejouable arrive au Lot E ;
- le backend local contrôlé n'applique pas encore une isolation OS ou réseau forte.
