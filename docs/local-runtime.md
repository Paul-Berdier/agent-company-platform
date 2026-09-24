# Poste local : ACP, Hermes, Claude, Codex et notes

État du 23 septembre 2026. Le code, les outils installés et l'accès à un modèle
sont trois prérequis distincts. Les commandes ci-dessous préparent un poste Windows
sans recopier de comptes ni de données personnelles. PowerShell 7 est requis.

Sur le poste de cette recette, le code à jour et les outils sont dans
`.claude/worktrees/desktop-completion` ; ouvrir un terminal dans ce dossier.
Le dossier principal conserve le chantier Pixel Office. Sur une nouvelle copie
du dépôt, exécuter les commandes depuis la racine de la version intégrée.

## Installation et première connexion

Le backend utilise Python 3.12 hors Microsoft Store. `setup.ps1` installe les
dépendances ACP ; les deux autres scripts téléchargent les outils dans le dossier
ignoré `acp-data/tools/`, sans modifier le PATH global.

```powershell
./scripts/setup.ps1
./scripts/setup-hermes.ps1 -Python python
./scripts/setup-claude-cli.ps1
./scripts/start-local-stack.ps1 -BootstrapOwner
```

Le dernier script demande **dans le terminal local** l'identifiant et le mot de
passe du premier propriétaire. Il crée une base dédiée
`acp-data/local-stack/platform.db`, jamais le fichier historique `acp.db`, et lance
API, service d'événements et provider-gateway sur `127.0.0.1:8000–8002`.
Il ne crée aucun projet fictif. Après l'amorçage, relancer sans `-BootstrapOwner`.
Un port déjà utilisé provoque un refus ; `-ApiPort 18000` choisit un autre triplet.
Ctrl+C arrête seulement l'arbre des processus lancés par ce script ; la base reste.

Les secrets techniques sont générés une fois dans
`acp-data/local-stack/service-secrets.dpapi`, chiffrés pour l'utilisateur Windows.
Ils ne sont pas imprimés ni écrits dans un `.env` ou un JSON clair. Ce fichier
n'est pas portable sur un autre compte Windows. Les sauvegardes et clés serveur
doivent suivre [la procédure de persistance](persistence-and-backup.md).

Dans un second terminal, lancer le desktop construit avec
`./scripts/dev-desktop.ps1 -Configuration Release`,
saisir `http://127.0.0.1:8000`, autoriser explicitement HTTP en bouclage et utiliser
le compte créé. Pour compiler : [desktop-build.md](desktop-build.md).
Le desktop ne démarre pas lui-même Hermes ou un worker.

## Hermes et les authentifications

Hermes est épinglé sur `v2026.9.7`, version `0.21.1`, commit
`2237be355906fbe6065ce1815711eee52b2d646e`. L'installation utilise `uv sync --locked`
avec les extras MCP et messaging : cette version a besoin d'`aiohttp` pour l'API
Runs. Les installations automatiques de dépendances pendant l'exécution sont
désactivées par les lanceurs ; une extension supplémentaire doit être installée
explicitement puis vérifiée.

```powershell
./scripts/hermes-local.ps1 -Action setup
./scripts/start-local-stack.ps1 -WithHermes
```

`setup` ouvre l'assistant officiel dans le profil dédié `acp-data/hermes-profile`.
Choisir et authentifier son fournisseur localement. Aucun accès payant n'est
sélectionné par les scripts ACP. `-WithHermes` relie ensuite le provider-gateway au
serveur Hermes loopback `8642`, avec un secret partagé chiffré au repos.
Consulter **Connexions / diagnostic Hermes** avant de soumettre une mission.

Les lanceurs refusent un `.env` dans le checkout Hermes et les réglages du profil
qui remplaceraient l'adresse d'écoute, le port, la clé technique ou les chemins
imposés. Les sources externes de secrets dans `config.yaml` ne sont pas prises en
charge par ces lanceurs ; utiliser le profil dédié. Les clés du fournisseur peuvent
rester dans ce profil local, sans être copiées dans ACP ni dans le dépôt.

Le serveur Hermes réel a répondu à la santé et aux capacités pendant la recette,
sans soumission de Run. Il annonçait bien la version attendue, l'arrêt de Run et
l'idempotence durable de 86 400 secondes. Sa readiness était **dégradée** : aucun
modèle configuré et disque rempli à 97,9 % (environ 20,6 Go libres). La plateforme
refuse les admissions dans cet état. Ni cette réponse HTTP ni un test simulé ne
prouvent une génération réelle. Aucun nettoyage de disque automatique n'est prévu.

Claude Code `2.1.267` est téléchargé depuis la distribution officielle Windows x64,
avec taille et SHA256 vérifiés. Codex CLI doit être installé séparément ; le poste
de recette disposait déjà de cet exécutable. Authentifier **des profils CLI dédiés**
hors des racines projet, avec les procédures officielles
[Codex](https://developers.openai.com/codex/auth/)
et [Claude Code](https://code.claude.com/docs/en/authentication).
Hermes et les deux CLI possèdent des authentifications distinctes ; installer les
binaires ne les connecte pas automatiquement aux comptes.

## Worker et mission à deux exécuteurs

Créer un projet dans ACP et relever son identifiant. Arrêter puis relancer la pile
en autorisant uniquement ce projet à l'enrôlement :

```powershell
./scripts/start-local-stack.ps1 -WithHermes -WorkerProjectId <identifiant-projet>
```

Dans un second terminal, utiliser `worker-local.ps1`, en remplaçant les chemins
par ceux du dépôt de travail et des profils CLI dédiés déjà authentifiés :

```powershell
$workerOptions = @{
    ProjectId = '<identifiant-projet>'
    ProjectPath = 'C:/Projets/mon-projet'
    CodexProfile = 'C:/ACP-auth/codex'
    ClaudeProfile = 'C:/ACP-auth/claude'
}
./scripts/worker-local.ps1 @workerOptions -Action doctor
./scripts/worker-local.ps1 @workerOptions -Action register
./scripts/worker-local.ps1 @workerOptions -Action start
```

L'enrôlement utilise le secret chiffré du lanceur local, sans le copier dans le
terminal. Ce script est destiné au même poste et au même compte Windows. Pour un
worker distant, suivre [son installation](workers/windows-worker.md).
Le dépôt doit être propre et sa racine Git explicitement autorisée.
Choisir des chemins courts pour les dépôts, l'état worker et les tests. Git Windows
2.42 peut refuser les métadonnées d'un worktree trop profond, même avec l'option
de chemins longs ; Windows peut aussi refuser un répertoire de processus trop long.
Ces refus ne constituent pas une exécution réussie.
Sur Windows, le fichier d'état worker est chiffré par DPAPI pour le compte courant.
Un ancien fichier clair valide est migré atomiquement avant utilisation ; un échec
de chiffrement arrête le chargement, sans repli en clair.

Le formulaire Qt propose **Standard**, **Codex**, **Claude** et **Équipe Claude +
Codex**. Les CLI utilisent le mode supervisé et la ressource `project_workspace`
du projet. Les outils de fichiers de Claude restent limités à la lecture ;
l'écriture du dépôt est réservée à Codex. Un outil MCP explicitement autorisé
peut avoir ses propres effets externes, contrôlés séparément par le proxy ACP.
Une équipe exige la capacité worker `agent_team`, les deux exécuteurs configurés,
au plus deux étapes simultanées et le plafond d'agents de la politique projet
(4 par défaut, maximum technique 8 étapes).

Chaque étape s'exécute dans un worktree dédié conservé avec branche, diff et
réponse. Les dépendances attendent les sorties des étapes précédentes ; leur
contexte transmis est borné et une troncature est signalée. **Aucune fusion
automatique des branches produites** n'est effectuée. Après un redémarrage avec
une étape déjà commencée, le checkpoint conserve les preuves et bloque la
réexécution : la reprise automatique d'un DAG partiellement terminé n'est pas livrée.

Les limites monétaires et de jetons restent appliquées. Comme les effets CLI et
Hermes n'annoncent pas de borne fiable avant l'appel, une limite sur ces dimensions
entraîne un refus. Le formulaire propose explicitement un budget en appels d'outils
et en durée, sans plafond de coût ; cela ne désactive aucune politique du projet.

## Compétences, MCP et Obsidian

Les compétences ACP sont figées à la création d'une mission puis relues sous le
bail actif avant transmission. Désactivation, révocation, nouvelle révision de
liaison ou empreinte incohérente empêchent leur usage. Elles fournissent des
instructions de travail et ne relèvent aucun droit du processus.

Les outils MCP **Streamable HTTP** liés au projet passent par le proxy ACP. Le CLI
reçoit une délégation courte limitée à la tentative, l'étape, la révision et les
outils autorisés. L'API conserve les secrets amont, contrôle le bail et les droits
à chaque appel et réserve son budget avant l'effet. Un résultat réseau incertain
est déclaré indéterminé ; il n'est jamais relancé automatiquement. Le MCP stdio
reste disponible pour les diagnostics autorisés, mais son exécution dans une
mission est refusée explicitement.

`setup-hermes.ps1` crée `acp-data/obsidian/Accueil.md`. Ce dossier est un coffre
Markdown ouvrable dans Obsidian ; l'application Obsidian n'est pas installée par
ce script. Le lanceur Hermes fixe `OBSIDIAN_VAULT_PATH` sur ce coffre dédié. La
[compétence Obsidian fournie par Hermes](https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.7/skills/note-taking/obsidian/SKILL.md)
utilise les outils de fichiers sans exiger de serveur MCP. Aucun coffre personnel
n'est importé. Missions, décisions et preuves restent dans ACP ; les notes sont
un complément. Un Hermes distant exige une copie ou un partage explicitement organisé.

## Vérifications sans compte payant

```powershell
./scripts/setup-hermes.ps1 -CheckOnly
./scripts/setup-claude-cli.ps1 -CheckOnly
./scripts/start-local-stack.ps1 -CheckStartup
./.venv/Scripts/python.exe scripts/verify-hermes-local.py
```

La dernière commande utilise un profil jetable sous `.test-tmp`, un port libre et
un secret éphémère. Elle lit la santé et les capacités, ne soumet aucun Run puis
arrête son arbre de processus. `server_reachable` signifie uniquement « serveur
joignable » ; lire également la readiness conservée dans `result.json`.
Les preuves desktop et les limites restantes figurent dans
[la validation fonctionnelle](functional-completion-2026-09-23.md).
