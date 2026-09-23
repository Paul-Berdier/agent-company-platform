# Exécuteurs locaux Codex CLI et Claude Code

Date d’état : 23 septembre 2026 — complétion fonctionnelle en validation

Le worker peut désormais exécuter Codex CLI ou Claude Code après attribution d'une
mission compatible. Ce chemin est raccordé à la boucle réelle ; il reste distinct du
runner à argv fixe du Lot C et du provider-gateway. Aucun CLI découvert fortuitement
dans le `PATH` n'active une capacité.

## Activation explicite

Chaque CLI exige un drapeau exact `0|1`, un exécutable absolu existant et un dossier
d'authentification séparé :

```text
ACP_WORKER_CODEX_ENABLED=1
ACP_WORKER_CODEX_EXECUTABLE=C:\outils\codex\codex.exe
ACP_WORKER_CODEX_HOME=C:\acp-worker-auth\codex

ACP_WORKER_CLAUDE_ENABLED=1
ACP_WORKER_CLAUDE_EXECUTABLE=C:\outils\claude\claude.exe
ACP_WORKER_CLAUDE_CONFIG_DIR=C:\acp-worker-auth\claude

ACP_WORKER_EXECUTOR_PROJECTS_JSON={"project-id":"C:\\projets\\project-id"}
```

Le JSON des projets est une allowlist `project_id -> racine absolue`. Les racines ne
peuvent pas se chevaucher. Exécutables, profils d'authentification et éventuels dossiers
de `ACP_WORKER_EXECUTOR_PATH` doivent rester hors de ces racines. Un profil Codex qui
contient `AGENTS.md` ou `AGENTS.override.md` est refusé : une instruction globale
extérieure au budget documentaire du projet contournerait la politique.

Cette allowlist choisit le cwd ; elle ne restreint pas les droits de lecture du compte
worker aux seuls fichiers de cette racine. La résolution canonique ne verrouille pas
non plus l'identité des fichiers jusqu'au spawn : exécutables, profils, chemins d'outils,
racines et tous leurs parents doivent être contrôlés par l'opérateur et protégés par ACL
contre remplacement, lien ou reparse point concurrent.

Limites communes : `ACP_WORKER_EXECUTOR_TIMEOUT_SECONDS` vaut 1 800 s par défaut et ne
peut dépasser 3 600 s ; `ACP_WORKER_EXECUTOR_TERMINATE_GRACE_SECONDS` vaut 1 s et ne
peut dépasser 30 s. La sortie de chaque flux est plafonnée à 2 Mio et le stdout doit
être un JSONL UTF-8 contenant au plus 10 000 objets. Un code zéro ne suffit pas : la
dernière ligne doit être `turn.completed` pour Codex, ou un `result` Claude de sous-type
`success` avec `is_error=false`.

Le worker doit être enregistré en mode réel. `capabilities` et `doctor` n'annoncent
`codex_cli` ou `claude_code` que lorsque cette configuration est complète ; `doctor`
n'affiche que les noms d'exécuteurs et le nombre de racines, jamais leurs chemins ni
leurs credentials.

Une liste `--capability` explicite ne contourne pas cette règle. L'enregistrement refuse
un identifiant agent sans backend correspondant, et chaque démarrage revérifie les
capacités conservées dans `worker.json` contre la configuration courante avant le
premier heartbeat ou claim. Un agent exige un scope projet et la racine correspondante ;
le scope global est refusé tant que le claim ne filtre pas l'allowlist locale. Toute
capacité générique exige le runner fixe. `mcp_stdio_probe` exige sa sonde configurée et,
tant que les capacités de probe/mission restent communes, ce runner local lui aussi.

## Contrat de mission

Une tentative simple doit demander **exactement un identifiant d'exécuteur** parmi les deux
dans `required_capabilities` ; d'autres capacités peuvent être présentes. Elle doit
aussi être `supervised`, avoir les trois listes
`allowed_actions`, `forbidden_actions` et `approval_required_actions` vides, et déclarer
exactement une ressource :

```json
{
  "kind": "project_workspace",
  "identifier": "project-id",
  "access": "read"
}
```

L'identifiant doit être celui du projet attribué. Codex accepte `read` ou `write` et
passe respectivement en sandbox `read-only` ou `workspace-write`. Claude refuse toute
ressource `write` dans le Lot G. Il n'existe pas de circuit d'approbation interactif :
une politique ambiguë est rejetée avant la planification et avant le spawn.

Pour `write`, ACP prend avant le spawn un verrou interprocessus dont le nom dérive de la
racine canonique et dont le fichier persiste dans son dossier parent. Le délai d'attente
consomme la deadline de l'exécuteur ; erreur, timeout et annulation dont le nettoyage est
confirmé libèrent le verrou.
Deux jobs ou workers ACP qui voient la même racine sur le même système de fichiers ne
modifient donc pas simultanément ce checkout.

Si la clôture d'une écriture n'est pas confirmée, ACP publie avant libération un marqueur
atomique `.acp-worker-write-<sha256>.poison` adjacent au verrou. Toute acquisition,
y compris une attente déjà engagée, échoue ensuite fermée. ACP ne supprime jamais ce
marqueur : arrêter tous les workers concernés, inspecter processus et checkout, puis le
lever manuellement seulement lorsque l'opérateur a rétabli un état sûr.

## Équipe explicite

Une mission peut porter `execution={"mode":"multi_agent","executors":["codex_cli",
"claude_code"],"max_concurrency":2}` avec la capacité `agent_team` et celles de ses
exécuteurs. Le worker n'annonce `agent_team` qu'avec un exécuteur configuré et Git
présent. Hermes doit affecter chaque étape à un exécuteur autorisé et renseigner ses
`depends_on`. Identifiants dupliqués, cycle, dépendance absente ou dépassement du
plafond `execution_limits.max_agents` transmis par l'API sont refusés avant le spawn.
Le plafond absolu est huit étapes, limité aussi par la politique du projet.

Deux étapes indépendantes au maximum s'exécutent simultanément dans une tentative.
Chaque étape possède un worktree et une branche Git distincts sous le répertoire
d'état du worker. Le dépôt source doit être propre et sa configuration ne doit pas
contenir de filtre, d'inclusion Git ni de configuration propre aux worktrees. Codex
peut écrire si la mission l'autorise ; Claude reçoit toujours une ressource en lecture
seule. Les résultats et diffs bornés des dépendances sont transmis aux étapes
suivantes. Aucune fusion ni suppression automatique n'est effectuée : chemins,
branches, commit de départ et diff restent dans les preuves pour une revue humaine.

Le worker sérialise les mises à jour API et conserve un checkpoint local par équipe.
Un arrêt annule tous les enfants puis attend leur nettoyage. Après redémarrage, une
équipe ayant déjà commencé est **bloquée avec ses preuves conservées**, même si une
partie des étapes est terminée : la reprise automatique des étapes restantes n'est
pas livrée. Examiner les worktrees et le ledger avant une nouvelle tentative.

`spawned_agents` compte les invocations de premier niveau engagées par ACP. Le worker
interdit le fan-out intégré connu des CLIs et n'expose pas l'outil Agent de Claude.
Il ne mesure pas les descendants arbitraires du binaire ; le quota n'est pas une
sandbox OS. Plusieurs tentatives/plusieurs workers peuvent fonctionner en parallèle,
chacun sous son lease et les permis budgétaires du projet.

## Invocation Codex

Le worker lance `codex exec` sans shell, avec `--json`, `--ephemeral`, approbations
désactivées et le prompt sur stdin. Il demande au CLI d'ignorer la configuration et les
règles utilisateur, fixe le projet en `untrusted`, coupe la découverte documentaire du
projet et remplace la configuration MCP par une table vide ou par les seuls proxys
HTTP autorisés pour cette tentative. Il lui demande aussi de
désactiver web, apps, navigateur, computer use, hooks, génération d'image, multi-agent,
mémoire, plugins et recherche de skills. Le réseau du mode Codex `workspace-write` est
configuré à faux et les répertoires temporaires globaux en sont exclus ; ces options ne
constituent pas une sandbox indépendante fournie ou vérifiée par ACP.

## Invocation Claude Code

Le worker lance `claude -p` avec sortie `stream-json`, douze tours maximum,
`--permission-mode dontAsk`, `--safe-mode`, aucun Chrome, une configuration MCP vide et
stricte, aucune persistance de session ni commande slash. Les seuls outils autorisés
sont demandés comme `Read,Glob,Grep` et `mcp__*` est explicitement interdit. Cette
configuration n'empêche pas le processus de lire un chemin accessible à son compte OS.

Avec des MCP liés, `--safe-mode` serait incompatible : il désactive aussi les serveurs
explicites. Ce chemin utilise `--restricted`, les sources de réglages utilisateur/projet
vides, les hooks et plugins désactivés, la configuration MCP stricte et une allowlist
exacte des outils proxy. Agent, Task, shells et outils d'écriture restent interdits.
Les politiques gérées de l'installation Claude restent applicables.

## Compétences, MCP et Hermes

Avant la planification, l'API relit les droits des liaisons et livre le `SKILL.md` de
chaque révision épinglée. Le worker vérifie les révisions, les empreintes SHA-256 et
la limite cumulée de 24 000 caractères. Ces documents sont transmis à Hermes puis
au prompt CLI, sans leur permettre d'ajouter des capacités. Le prompt total est
limité à 64 000 caractères ; un dépassement est refusé sans troncature des compétences.

Les MCP HTTP passent uniquement par le proxy API ACP. Le worker demande une autorisation
éphémère par étape stable ; son jeton atteint seulement l'environnement du CLI. Il
n'est pas placé dans les arguments, les checkpoints ou les preuves. Le proxy conserve
les secrets amont, vérifie outils/révision/droits/lease et le budget. Une origine,
révision ou expiration incohérente est refusée ; l'expiration borne aussi le CLI.
Les serveurs MCP stdio ne sont pas pris en charge par cette voie d'exécution.
Configuration officielle : [MCP Codex](https://developers.openai.com/codex/mcp/) et
[variables MCP Claude](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcp-json).

Hermes est admis via les opérations asynchrones `plan` et `evaluate`. Clé d'idempotence,
empreinte du corps et date d'admission sont conservées avant l'appel, puis le `run_id`
avant son suivi. Chaque HTTP est borné à 15 secondes au plus, dans la durée globale.
Après perte de réponse, la même clé est rejouée pendant la rétention garantie de 24 h ;
une admission ambiguë plus ancienne est refusée. Un `run_id` connu se lit directement.
Une demande d'approbation non exposée provoque un arrêt explicite. Lors d'un arrêt ou
d'un délai dépassé, le worker exige un état terminal distant dans une fenêtre de
nettoyage de cinq secondes ; sinon il s'arrête en erreur fatale sans annoncer un faux
arrêt. Les checkpoints ne réinitialisent pas la durée globale après redémarrage.

## Processus, secrets, budget et preuve

Le prompt borné est transmis par stdin, jamais dans l'argv. Le sous-processus reçoit un
environnement minimal, un `PATH` explicitement allowlisté, et seulement `CODEX_HOME` ou
`CLAUDE_CONFIG_DIR` selon le CLI. Les secrets du worker, du gateway et d'Hermes ne sont
pas hérités.

Le spawn réutilise la clôture du runner : Job Object Windows créé avant la reprise du
processus, ou nouvelle session POSIX. Sous Windows, le Job Object permet de vérifier sa
vidange ; un arrêt ou drainage incertain devient une erreur fatale et arrête le processus
worker avant son claim suivant. Ce verrou n'est pas persisté : un superviseur ne doit pas
redémarrer automatiquement le worker avant vérification opérateur. Un POST de claim déjà
en vol peut avoir créé un lease distant, sans spawn local ; il expirera ou sera réconcilié.
Sous POSIX, `killpg` termine le groupe connu mais ne peut prouver
l'absence d'un descendant qui a changé de session avec `setsid()`.

Le permis budgétaire est obtenu avant le spawn et rapporte un appel d'outil. Les CLI ne
fournissant pas de limite dure fiable de coût ou de jetons, toute mission qui exige une
telle borne est refusée avant effet. Le délai effectif est le minimum du plafond local
et de la durée de mission restante, attente du verrou comprise.

La preuve technique garde les métadonnées opérationnelles, le code de sortie, le
nombre d'événements, les tailles et les sha256 des flux bruts. Le résultat métier
contient séparément le dernier message d'agent Codex ou le champ `result` Claude,
limité à 16 000 caractères, avec marqueurs de troncature et de terminaison. Il est
transmis à l'évaluation et à l'API : cette réponse peut contenir des données du projet.
Les autres événements, le prompt et stderr ne sont pas copiés. Les mesures présentes
du provider sont rapportées ; un coût ou un nombre de jetons absent reste inconnu.

La preuve et le résultat sont écrits atomiquement dans le répertoire d'état worker
avant le rapport d'usage. Celui-ci effectue au plus trois essais sur incident réseau
ou erreur HTTP transitoire, avec un corps et des identifiants identiques. Une panne
persistante bloque la tentative en gardant la validation technique, les preuves et
la réservation active ; elle ne relance jamais l'effet. Un redémarrage sur une
tentative dont le checkpoint indique un effet terminé refuse aussi sa réexécution.
Le rapprochement non confirmé doit être résolu par l'opérateur ; aucune file cachée
ne le rejoue après le blocage. Protéger le répertoire d'état avec les ACL du compte
worker : les checkpoints contiennent la réponse métier, jamais les jetons du worker.

## Limites

Les tests utilisent des dépôts Git temporaires, des CLIs synthétiques et des transports
HTTP simulés pour la concurrence, le fencing, les refus et la conservation des preuves.
Un démarrage natif Claude 2.1.267 a initialisé un MCP HTTP et obtenu une réponse de modèle
simulé, tous deux sur loopback, avec un profil et des identifiants de fixture isolés.
Codex a validé sa configuration native MCP HTTP par `mcp list --json`. Ces preuves
n'établissent pas un appel de modèle payant ni une exécution de tool métier réelle. Aucun run Codex CLI ou Claude
Code authentifié n'a été lancé sur un dépôt utilisateur pendant cette validation. La
clôture de processus n'est pas une sandbox OS : le compte worker, le pare-feu, les
permissions des racines et les profils d'authentification restent dans la base de
confiance.

Un worker qui traite du code non fiable doit être dédié à un seul projet, sous un compte,
conteneur ou VM qui ne peut pas lire les autres projets, avec filtrage réseau externe.
Partager le même compte worker entre projets qui ne se font pas confiance n'assure
aucune isolation fichiers. ACP ne mesure pas les descendants du CLI et n'épingle pas
l'identité d'un exécutable ou d'une racine contre une substitution après validation.
Le verrou et sa quarantaine sont coopératifs : protéger leur parent par ACL et vérifier
les garanties de verrouillage/durabilité d'un partage réseau ; à défaut, fournir un
checkout ou worktree distinct par worker.
