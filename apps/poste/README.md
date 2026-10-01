# Poste Windows d'ACP (`apps/poste`)

Étape P5 de la refonte « Hermes au centre » (cahier de conception P5, décisions **D48 à D73** de
[`docs/refonte/plan.md`](../../docs/refonte/plan.md) § 1, **non confirmées**). Le poste **se connecte à Hermes sans
rien exécuter** : il s'enrôle, garde son jeton sous DPAPI, attend ses ordres en HTTPS sortant (attente longue de
25 s, jamais un port en écoute), relève ce que Codex CLI et Claude Code déclarent (modèles, efforts, connexion, mode
du bac à sable, quotas) et publie un **inventaire**. Il annonce `peut_executer: false` : la réclamation de cartes et
l'exécution arrivent en **P6**. Référence côté Hermes et preuves : [`docs/refonte/poste.md`](../../docs/refonte/poste.md).

## Modules

| Module | Rôle |
|---|---|
| `chemins.py` | emplacements : `%ProgramData%\ACP` (politique, quotas Claude), `%LOCALAPPDATA%\ACP` du compte du poste (coffre, état, journal, preuves), `%ProgramFiles%\ACP` (poste, binaires des CLI) ; lus par `SHGetKnownFolderPath`, jamais dans l'environnement |
| `politique.py` | lecture et validation de `poste.toml` (clés inconnues refusées, HTTPS partout, chemins absolus, alias de dépôts, racines disjointes) ; droits de `poste.toml` et des binaires (`CreateFileW` avec `GENERIC_WRITE`, `DELETE`, `WRITE_DAC`, `WRITE_OWNER`, puis le dossier) ; compte courant par `GetUserNameW` |
| `coffre.py`, `credentials_protection.py` | coffre DPAPI : un fichier `ACPD1` + blob par usage (jeton machine, jeton Claude), entropie **propre à chaque usage**, écriture atomique, refus français d'un blob illisible |
| `jeton.py` | jeton machine `acpm_…` et code d'enrôlement `acpe_…` au `repr` masqué, empreinte `XXXX-XXXX` |
| `verrou.py` | verrou d'instance et verrou des sondes (`LockFileEx`) |
| `journal.py` | journal JSONL local masqué (valeurs exactes, motifs de secrets, profils, adresses), rotation 5 × 1 Mio |
| `client_hermes.py` | HTTPS sortant par la bibliothèque standard (D61) : TLS 1.2+, nom d'hôte vérifié, magasin de Windows, aucune redirection suivie, aucun mandataire d'environnement, réponse bornée à 64 Kio |
| `protocole.py` | routes `acp-machine/1` validées par le contrat partagé ; classement des refus (401 `poste_revoque` : jeton effacé ; 401 de la couture : jeton **gardé**, arrêt code 4, D65 ; 409 protocole ; 429 ; 5xx) |
| `enrolement.py` | `acp-poste enroler` : code lu par saisie masquée, jeton au coffre, empreinte affichée |
| `app_server.py` | session JSON-RPC avec `codex app-server` à **liste blanche de méthodes** ; `-32601` à toute requête du serveur |
| `sondes_codex.py` | profil dédié, surcharges `-c` imposées, extraction par liste blanche, « Liste de secours », mode du bac à sable lu par `config/read` (D60), quotas |
| `sondes_claude.py`, `catalogue_claude.py` | version, **code de sortie seul** de `claude auth status`, alias et efforts **documentés** (datés, plage de versions), ligne d'état |
| `inventaire.py` | inventaire au contrat D21 étendu, garde « aucun identifiant » avant l'envoi |
| `service.py` | boucle `servir` : une seule boucle asyncio, attente longue, ordres, relevés, repli exponentiel |
| `diagnostic.py` | état du poste sans chemin ni secret ; `--reseau`, `--isolement` |
| `connexions.py`, `preuves.py` | gestes manuels (`connexion codex|claude|bac-a-sable`) ; preuve n° 1 (`model/list`) |
| `executors.py`, `local_runner.py` | exécuteurs Codex et Claude Code et runner sous Job Object, **inutilisés avant P6** ; `ExecutorConfig.depuis_politique` lit `poste.toml` |
| `subscription_quotas.py`, `claude_statusline.py` | forme des quotas (Codex, ligne d'état Claude Code) ; écrivain de la ligne d'état de **vos** sessions |

Le contrat partagé avec le greffon est `hermes/plugins/acp-poste/contrat` (`acp_poste_contrat.machine`,
`inventaire`, `quotas`, `motifs_secrets`).

## Exécutant Linux (étape P6)

Le même paquet sert l'**exécutant Railway** (cahier P6 § 7, décision D76) : la plateforme est choisie par
`sys.platform`, jamais par une variable. Le poste Windows reste celui de P5 (`peut_executer: false`). Sous Linux, le
superviseur (root, sous `tini`) lit `/etc/acp/executant.toml` (versionné : `executant/politique/executant.toml`,
D78), rejoue la **sonde de plateforme** à chaque démarrage, attend son enrôlement **sans sortir**, puis réclame des
cartes et les exécute une à une, chaque agent sous **son UID** (`acp-codex` 10001, `acp-claude` 10002,
`acp-verif` 10003). Rien n'est poussé : la branche intégrée se récupère par `acp-poste bundle` (§ 12.2).

| Module | Rôle |
|---|---|
| `plateforme/` | choix Windows ou Linux ; Linux : emplacements sous `/donnees`, coffre en fichiers 0600 de root (`CoffreFichiers`), `setpriv` vers l'UID de l'agent avec un environnement calculé, arrêt par groupe puis **par UID** (balayage de `/proc`, cahier § 7.5) |
| `politique.py` | aussi `executant.toml` : `uid_dedie`, origine au gabarit refusée, conditions D83/D84 datées, dépôts distants HTTPS sur hôte admis, droits root vérifiés au démarrage |
| `sonde_plateforme.py` | sonde R0 (§ 4.1) : espaces de noms, bubblewrap, `codex sandbox`, séparation par UID ; verdict régime A ou B → `isolement_linux` |
| `depots.py` | clone nu, `fetch` en lecture seule (jeton par `GIT_ASKPASS`), worktree et branche `hermes/<carte>`, commit local sans crochets ni `fsmonitor` avec `--git-dir` explicite, diff brut, quarantaine, intégration `--no-ff`, `git bundle` |
| `pilotage.py`, `balayage.py` | fichiers de pilotage touchés (→ revue, D90) ; secrets (valeurs exactes du coffre et d'`auth.json`, puis motifs du contrat) |
| `commandes_agents.py`, `evenements.py`, `garde_quota.py` | commandes imposées de `codex exec` et `claude -p` (consigne par l'entrée standard) ; lecture des flux ; garde à 90 % et plafonds du jour |
| `execution.py` | une carte : contrôle, préparation, agent, battements, vérification et reprise du fil, commit, contrôles, issue |
| `sortie.py` | file de sortie persistante (§ 5.9) : écrite avant l'envoi, rejouée dans l'ordre avant toute réclamation |
| `service_executant.py` | boucle de l'exécutant : attente d'enrôlement, `peut_executer`, tâches A/B/C, SIGTERM, reprise après un redémarrage |
| `gestes_executant.py` | `connexion claude|github --stdin`, `connexion codex` (code d'appareil), `bundle`, `pause`, `reprise`, `cartes` |

Commandes de l'exécutant (dans une session `railway ssh`, `acp-poste` est sur le `PATH`) :
`acp-poste sonde-plateforme --json`, `acp-poste enroler`, `acp-poste pause`, `acp-poste connexion codex`,
`acp-poste connexion claude --stdin`, `acp-poste connexion github --stdin`, `acp-poste reprise`,
`acp-poste diagnostic --isolement`, `acp-poste cartes`, `acp-poste bundle <alias> <branche>`. Sans jeton ou après
une révocation, l'exécutant attend sans sortir ; un 401 ambigu garde le jeton et retente toutes les 15 min ; SIGTERM
arrête la carte proprement (`arret`) et sort en 0.

## Installation (vous seul, sous l'UAC)

Le poste tourne sous un **compte Windows local dédié** `acp-poste` (D51), lancé par une **tâche planifiée** au
démarrage et toutes les 15 minutes (garde, D66), avec un Python python.org « pour tous les utilisateurs » en mode
isolé, **sans venv** (D53). `poste.toml` vit sous `%ProgramData%\ACP\`, en **lecture seule** pour le compte du
poste (D52). Les binaires de Codex et de Claude Code sont **copiés depuis vos installations** sous
`C:\Program Files\ACP\outils\` (D54), hors d'atteinte du compte du poste.

**À savoir avant de commencer.** Le chemin réel de l'installeur (création du compte, ACL, `pip --target`, tâche
planifiée, `secedit`) n'a **jamais été exécuté**, ni sur votre PC ni en CI : la répétition à blanc et la CI ne
lancent que `-Simulation`, qui ne couvre ni le compte, ni les ACL, ni la tâche. Vous serez le premier à l'exécuter.
En cas d'échec, corrigez la cause dite en français et relancez l'installeur : le compte existant est conservé (son
mot de passe vous est redemandé), les dossiers sont recréés à l'identique, `poste.toml` n'est jamais remplacé.

### a. Prérequis

1. **Hermes déployé sur Railway avec l'étape P5** : l'onglet **Poste** est visible dans votre tableau de bord. Sans
   lui, les gestes « Réseau » et « Enrôlement » échouent (rien n'est déployé à ce jour : premier déploiement,
   [`docs/refonte/railway.md`](../../docs/refonte/railway.md)).
2. Python **3.12** de python.org, installé **pour tous les utilisateurs** (option de l'installeur ; par exemple
   `C:\Program Files\Python312\python.exe`). Un Python « pour moi seul » (sous votre profil) ou celui du Microsoft
   Store est refusé : le compte du poste ne pourrait pas l'exécuter, ou son interpréteur sortirait du Job Object. Un
   Python que le compte du poste ou l'un de ses groupes peut **modifier** (par exemple installé directement sous
   `C:\`, qui accorde la modification aux Utilisateurs authentifiés) est refusé aussi : le service détient les jetons
   déchiffrés, et `python -I` exécute encore les `.pth` de `site-packages` (D67).
3. Codex CLI (paquet npm `@openai/codex`) et Claude Code (binaire natif `claude.exe`) installés dans votre session.
   Claude Code **2.1.280 ou plus récent** recommandé : en dessous de **2.1.248** (`--restricted`), l'installeur refuse
   (simulation comprise) ; entre les deux, il avertit que la voie Claude sera refusée au routage (efforts inconnus,
   D71). Mettez-le à jour par `claude update` dans votre session avant d'installer.
4. Un checkout de ce dépôt.

### b. Répétition à blanc (aucun effet)

Dans un PowerShell (élevé ou non), depuis la racine du dépôt :

```powershell
.\packaging\poste\Installer-PosteAcp.ps1 -Simulation `
    -Origine https://<domaine de HERMES_DASHBOARD_PUBLIC_URL> `
    -Python 'C:\Program Files\Python312\python.exe' -Depot (Get-Location) `
    -CodexSource "$env:APPDATA\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc" `
    -ClaudeSource "$env:USERPROFILE\.local\bin\claude.exe"
```

Elle imprime les neuf étapes et **tous** les refus, sans rien écrire (code 2 s'il y a un refus). Elle lance seulement
`--version` sur vos sources de Codex et de Claude Code (profil jetable sous `%TEMP%`, supprimé aussitôt) pour en
contrôler la version.

### c. Installation

Même commande **sans** `-Simulation`, dans un PowerShell **élevé** (Windows PowerShell 5.1 recommandé :
`New-LocalUser` y est natif). L'installeur :

1. contrôle Python (y compris ses droits), le dépôt, l'origine HTTPS, les sources et leur version ;
2. crée le compte `acp-poste` (mot de passe **saisi par vous**, deux fois, jamais écrit ; il n'expire pas et le
   compte ne peut pas le changer), membre du seul groupe Utilisateurs, groupes désignés par SID ;
3. crée `C:\Program Files\ACP\{poste,outils}`, `C:\ProgramData\ACP\{,quotas}`, `C:\ACP\{depots,espaces}` avec des ACL
   explicites (héritage coupé) ;
4. installe les dépendances d'exécution hachées (`requirements/poste-3.12.lock.txt`, `pip --require-hashes
   --target`) et copie les sources du poste et du contrat sous `C:\Program Files\ACP\poste\lib`, avec `lancer.py` et
   `acp-poste.cmd` ;
5. copie Codex (dossier `vendor\x86_64-pc-windows-msvc` entier : `bin\codex.exe` et ses assistants) et
   `claude.exe`, consigne leurs SHA-256 dans `C:\ProgramData\ACP\installation.jsonl`, relance `--version` sur les
   copies ;
6. écrit `C:\ProgramData\ACP\poste.toml` depuis le modèle s'il n'existe pas (sinon affiche la différence et signale
   chaque `version_testee` qui ne correspond plus à la CLI copiée) ;
7. enregistre la tâche `\ACP\Poste ACP` (compte `acp-poste`, mot de passe enregistré, niveau limité) ;
8. propose, **chacune sur confirmation**, de couper le démarrage rapide, de désactiver la veille sur secteur et de
   masquer `acp-poste` de l'écran d'accueil (D57 ; seule la valeur `acp-poste` est ajoutée à la clé `UserList`, dont
   les autres valeurs, comme les comptes `CodexSandbox*` masqués par Codex, restent) ;
9. vérifie la tâche et le droit « Ouvrir une session en tant que tâche », puis imprime les gestes restants.

**Mettre à jour une CLI** (Codex ou Claude Code) : mettez-la à jour dans votre session, relancez l'installeur (il
recopie les binaires et relit leur version), puis, comme `poste.toml` n'est jamais remplacé, ouvrez-le dans un
éditeur **lancé en administrateur** et reportez la nouvelle version dans `[codex] version_testee` ou
`[claude] version_testee` (l'installeur affiche l'écart à l'étape 6). Sans cela, le poste déclare la CLI hors version.

**Mot de passe définitif** : une réinitialisation par un administrateur rend illisibles pour ce compte ses blobs
DPAPI et son Gestionnaire d'identifiants (jeton machine, jeton Claude, clé du coffre de Codex) : il faut alors
refaire les connexions, l'enrôlement, et réenregistrer la tâche (refus : « Coffre DPAPI illisible : … »).

### d. Gestes manuels (dans l'ordre)

Le dossier du poste n'est dans aucun PATH : dans la console du compte (un PowerShell, qui démarre dans `System32`),
chaque commande s'écrit **avec l'opérateur `&`** et le chemin complet entre apostrophes, comme ci-dessous (D68). La page
Poste donne la même commande sous la forme `& "$env:ProgramFiles\ACP\poste\acp-poste.cmd" …`, équivalente.

| Étape | Où | Commande |
|---|---|---|
| Console du compte du poste | votre session | `runas /user:acp-poste "powershell -NoProfile"` (D55 ; le profil se crée au premier usage) |
| Connexion par code d'appareil | navigateur | activez-la dans les réglages de sécurité de votre compte ChatGPT (prérequis de `codex login --device-auth`) |
| Connexion de Codex | console `acp-poste` | `& 'C:\Program Files\ACP\poste\acp-poste.cmd' connexion codex` : écrit le `config.toml` du profil dédié, puis `codex login --device-auth` (code à valider avec **votre** compte ChatGPT) ; le poste ne lit rien de ce dialogue |
| Jeton de Claude Code | votre session, puis console `acp-poste` | `claude setup-token` dans **votre** session ; copiez le jeton ; `& 'C:\Program Files\ACP\poste\acp-poste.cmd' connexion claude` (collage masqué) ; puis `cls`, videz le presse-papiers et, si l'historique du presse-papiers de Windows (Win+V) est actif, supprimez-y l'entrée |
| Bac à sable de Codex | console `acp-poste` + UAC | `& 'C:\Program Files\ACP\poste\acp-poste.cmd' connexion bac-a-sable` : `windowsSandbox/setupStart {mode: "elevated"}` **sans dossier de travail** ; l'UAC demande des identifiants administrateur ; Codex crée ses comptes `CodexSandboxOffline` et `CodexSandboxOnline` |
| Réseau | console `acp-poste` | `& 'C:\Program Files\ACP\poste\acp-poste.cmd' diagnostic --reseau` : `GET /api/health` en HTTPS ; un refus TLS se dit en français (racine absente du magasin de Windows) |
| Enrôlement | navigateur + console | page **Poste**, section « Enrôler un poste » : bouton « Générer un code d'enrôlement » ; `& 'C:\Program Files\ACP\poste\acp-poste.cmd' enroler` ; collez le code (saisie masquée) ; comparez l'empreinte affichée à celle de la page ; recopiez-la puis « Confirmer le poste » |
| Démarrage | PowerShell élevé | `Start-ScheduledTask -TaskPath '\ACP\' -TaskName 'Poste ACP'` (ou redémarrez) |
| Facultatif : quotas Claude | votre session | ligne d'état de **vos** sessions Claude Code vers `C:\ProgramData\ACP\quotas\claude-code.json` (ci-dessous, D56) |

Désinstallation : `.\packaging\poste\Desinstaller-PosteAcp.ps1` (élevé ; `-Simulation` pour la répétition) retire la
tâche puis, chacun sur confirmation, les dossiers (dont `C:\ACP\espaces`, puis `C:\ACP` s'il est vide), la seule
valeur `acp-poste` des comptes masqués de l'écran d'accueil et le compte ; `C:\ACP\depots` n'est supprimé qu'après
une confirmation **nominative**. Révoquez aussi le poste sur la page Poste, et retirez la ligne d'état (`statusLine`)
de votre `~/.claude/settings.json` : elle appelait `ligne_etat.py`, supprimé avec le poste.

## `poste.toml`

Modèle commenté : [`packaging/poste/poste.toml.modele`](../../packaging/poste/poste.toml.modele). Sections :
`[poste]` (nom affiché, `compte = "dedie" | "proprietaire"`, `compte_attendu`), `[hermes]` (origine **HTTPS
obligatoire**, attente, délai de connexion), `[sondes]` (accords `codex`, `claude`, intervalle 600-86 400 s, délai
par sonde), `[codex]` (exécutable, profil, version testée, modèles permis, `bac_a_sable = "elevated"`), `[claude]`
(exécutable, dossier de configuration, version testée ≥ 2.1.248, alias permis, ligne d'état), `[politique]` (ce que
le PC refuse toujours : exécutants, efforts interdits, paliers admis, P6 : concurrence, durée, cartes par jour,
réseau), `[quotas]`, `[isolement]`, `[journal]`, `[depots.<alias>]`. Seule `%LOCALAPPDATA%` (celui du compte du
poste) est admise, et seulement dans `[codex] home` et `[claude] config_dir`. Toute clé inconnue, tout type ou toute
borne hors schéma est refusé en français, avec la clé et jamais la valeur. Relu à chaque cycle : devenu invalide,
il est annoncé (`politique_valide: false`) et plus rien n'est publié. En mode `compte = "dedie"`, le poste refuse
de démarrer s'il peut modifier ou remplacer `poste.toml` ou un binaire de CLI.

## Commandes

Dans la console du compte, `acp-poste` ci-dessous s'écrit `& 'C:\Program Files\ACP\poste\acp-poste.cmd'` (D68).

| Commande | Rôle | Réseau |
|---|---|---|
| `acp-poste servir` | boucle du service (tâche planifiée) | Hermes ; OpenAI et Anthropic par les CLI |
| `acp-poste enroler [--code-stdin] [--remplacer]` | enrôlement ; refusé si déjà enrôlé sans `--remplacer` | Hermes |
| `acp-poste connexion codex` / `claude` / `bac-a-sable` | gestes manuels (ci-dessus) | OpenAI / aucun / UAC |
| `acp-poste releve [--publier]` | sondes une fois, inventaire imprimé (et publié) | comme `servir` |
| `acp-poste preuve model-list` | archive du relevé `model/list` (preuve n° 1), sans identifiant, dans `%LOCALAPPDATA%\ACP\preuves` | OpenAI |
| `acp-poste diagnostic [--reseau] [--isolement]` | état du poste en JSON, sans chemin ni secret | `--reseau` : `/api/health` |
| `acp-poste journal [--lignes N]` | fin du journal ; « Aucun journal : le service n'a encore rien écrit. » s'il manque | aucun |
| `acp-poste oublier-jeton` | efface le jeton machine local (la révocation reste un geste sur la page Poste) | aucun |
| `acp-poste quotas` | relevés de quotas par voie (Codex, ligne d'état Claude Code) | comme `releve` |

Codes de sortie : **0** normal, non enrôlé, révoqué ; **1** erreur imprévue ou Hermes injoignable ; **2**
configuration refusée ; **3** autre instance dans ce compte ; **4** jeton gardé mais refusé par la couture de Hermes
(401 ambigu : révocation pendant une absence, ou fournisseur absent côté Hermes ; la tâche retente toutes les
15 minutes). Les commandes qui lancent Codex tiennent le **verrou des sondes** : pendant un cycle du service, elles
répondent « Une sonde est en cours dans le service : réessayez dans une minute. ».

## Ce que le poste relève et publie

- **Codex** : `codex app-server` lancé avec `-c windows.sandbox="elevated" -c cli_auth_credentials_store="keyring"
  -c service_tier="default"`, environnement sans clé d'API, `CODEX_HOME` = profil dédié dont le `config.toml` est
  vérifié octet pour octet. Méthodes : `initialize`, `account/read`, `config/read`, `windowsSandbox/readiness`,
  `model/list`, `account/rateLimits/read` (compte ChatGPT seulement) — **jamais** une méthode qui consomme un crédit,
  envoie un e-mail, connecte un compte ou écrit la configuration. L'adresse du compte est jetée au décodage. Sans
  compte, la liste est le **catalogue embarqué** (« Liste de secours ») ; un compte par clé d'API ou Bedrock est
  refusé ; une liste de compte identique au catalogue embarqué (second app-server sur un `CODEX_HOME` vide, en
  stockage `ephemeral`) est une « Liste de secours probable », refusée au routage tant que vous ne l'acceptez pas
  (D58). L'écriture Codex (P6) n'est admise que si `config/read` lit le mode `elevated` **posé par le poste**
  (origine `sessionFlags`), la readiness `ready` et le stockage `keyring` (D60).
- **Claude Code** : `claude --version` ; `claude auth status` avec le jeton du coffre dans son seul environnement,
  sorties **jetées sans lecture**, code 0 → « jeton reconnu » (jamais « valide ») ; alias et efforts **documentés**
  (lus le 26/09/2026, rendus seulement à partir de 2.1.280 ; sinon « Inconnu ») ; quotas par la ligne d'état de vos
  sessions (D56).
- **Inventaire** : relevés, bac à sable, connexions, versions (lue, testée, conforme), politique, alias des dépôts,
  Windows et Python ; validé par le contrat, puis balayé : aucune adresse, aucun chemin de lecteur ou de profil,
  aucun motif de secret ni valeur du coffre. Un inventaire refusé n'est pas envoyé (« inventaire retenu »).

## Ligne d'état Claude Code (quotas, D56)

Dans `~/.claude/settings.json` de **votre** compte (barres obliques sous Windows) :

```json
{"statusLine": {"type": "command",
  "command": "\"C:/Program Files/Python312/python.exe\" -I \"C:/Program Files/ACP/poste/ligne_etat.py\""}}
```

`ligne_etat.py` (copié par l'installeur) appelle `acp_poste.claude_statusline` : il recopie `rate_limits.five_hour`
et `rate_limits.seven_day` de vos sessions, sous Windows par défaut dans `C:\ProgramData\ACP\quotas\claude-code.json`
(lisible par le compte du poste ; dossier ouvert en modification à votre compte par l'installeur), ou au chemin
absolu de `ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT` (seul réglage `ACP_WORKER_*` restant, lu dans vos sessions et non par le
poste). Une ligne d'état existante se place après `--`. Déclarez ce fichier dans `poste.toml` (`[claude] ligne_etat`,
déjà rempli par le modèle). Une ligne d'état réglée sur l'ancien `acp_worker.claude_statusline` doit être changée.

## Développement et tests

Le venv de développement doit être bâti sur le Python de **python.org**, jamais sur celui du Microsoft Store
(`scripts/setup.ps1` le refuse).

```powershell
./scripts/setup.ps1
.venv\Scripts\python.exe -m pytest -q                          # poste, contrat du poste, outillage
pwsh -File packaging/poste/tests/Test-InstallationPoste.ps1    # installeur en simulation (Windows ; aussi sous powershell.exe 5.1)
$env:ACP_IMAGE_TESTS = 'acp-hermes-tests:<étiquette>'
./scripts/e2e-poste-windows.ps1                                # bout en bout local (Docker Desktop)
```

- `tests/` : unitaires (Windows : DPAPI, ACL, verrous réels ; Linux : ignorés et dits) ; faux Codex et faux Claude
  pilotés par scénario (`faux_codex.py`, `faux_claude.py`), dont les réponses suivent les schémas de Codex 0.156.1
  (`fixtures/codex_app_server_0_156_1`, régénérés et comparés) ;
- `tests/contrat/` : le vrai poste contre un **faux Hermes HTTPS** (autorité de test générée par `cryptography`,
  jamais installé sur le poste) qui applique le contrat partagé et répond depuis les mêmes exemples que le vrai
  greffon ;
- `tests/e2e/` : bout en bout **local** avec l'image Hermes (jamais en CI) ;
- étape P6 : `faux_agents.py` (faux `codex exec`/`codex sandbox` et faux `claude -p` pilotés par scénario) et des
  dépôts « distants » locaux ; les tests qui changent d'UID (`setpriv`, `chown`) exigent Linux et **root** : ils
  sont ignorés, et dits, ailleurs ; ils tournent dans un conteneur Linux jetable (Python 3.12, git, bubblewrap,
  verrou haché du dépôt) lancé en root.

## Limites

- **Poste Windows : aucune exécution** (`peut_executer: false`, P6 § 18) ; l'exécution vit sur l'exécutant Linux.
- Exécutant Linux : sans bubblewrap (régime B, probable sur Railway), la voie Codex est fermée (D79) et la
  vérification ne tourne que si le dépôt l'accepte sans bac à sable (D80, réseau ouvert) ; la forme du profil de
  permissions de `codex sandbox` (0.156.1) est **supposée** tant que le binaire réel ne l'a pas lue ; `codex exec
  --json` ne publie ni le modèle servi ni le palier (rapportés « inconnus ») ; les faux CLI ne prouvent que la
  plomberie.
- Le Job Object est une frontière d'arrêt, pas une sandbox. Le compte `acp-poste` lit son propre coffre DPAPI :
  un exécutant mal confiné (P6) le pourrait aussi ; il ne peut ni réécrire `poste.toml` ni remplacer les CLI.
- Les bacs à sable de Codex et de Claude Code sous Windows natif ne sont pas prouvés avec de vrais comptes ; le
  mode élevé a été lu par `config/read` (origine `sessionFlags`) sur un profil vide, pas installé.
- La documentation de Claude Code est figée dans `catalogue_claude.py` (26/09/2026) : à relire à chaque montée de
  version.
- Veille de Windows : au-delà de 3 minutes, « Poste hors ligne » (une notification par veille) ; parade D57.
- `LocalRunnerConfig.from_environment` (réglages `ACP_WORKER_RUN_*`) n'est plus appelé par aucune commande : P6
  le remplacera par `poste.toml`.
