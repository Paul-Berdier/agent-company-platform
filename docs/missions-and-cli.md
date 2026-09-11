# Missions, runner local et CLI

Date d'état : 11 septembre 2026, Europe/Paris

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

Les commandes `mcp`, `skills` et `automations` sont visibles comme capacités futures
mais retournent un code « non supporté » dans cette version ; elles seront raccordées
dans les Lots D et F, sans résultat simulé.

## Contrat du backend local

Le worker réel n'exécute jamais un argv transmis par l'API. L'argv autorisé, la
racine des runs, le timeout, la limite de sortie et l'allowlist d'environnement sont
une configuration locale. Le programme reçoit seulement le chemin de l'enveloppe
JSON versionnée. Voir [Worker Windows distant](workers/windows-worker.md) pour la
configuration complète.

Le runner crée un cwd neuf par tentative, filtre l'environnement, capture et hache
stdout/stderr, borne la sortie et arrête l'arbre de processus en cas d'arrêt,
timeout, perte de lease ou fencing obsolète. Ces contrôles ne sont pas une sandbox
OS : l'adaptateur local configuré conserve les droits et l'accès réseau du compte
qui lance le worker. L'emploi sur du code non fiable nécessite une isolation système
supplémentaire.

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
- aucune instance Hermes réelle ni commande agentique payante n'a été lancée pour
  cette release ;
- SQLite et `create_all()` restent le chemin local ; les migrations PostgreSQL et
  la restauration sont reportées au Lot H ;
- le suivi web/CLI interroge l'API ; le flux authentifié et rejouable arrive au Lot E ;
- le backend local contrôlé n'applique pas encore une isolation OS ou réseau forte.
