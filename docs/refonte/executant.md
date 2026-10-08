# Exécutant Railway (étape P6)

État du **1er octobre 2026**. Étape P6 du [plan d'autonomie](autonomie.md), transposée à Railway par décision du
propriétaire du 27 septembre 2026 (D74) : l'exécution principale se fait dans un **troisième service Railway,
`executant`**, séparé de Hermes, qui porte Codex CLI et Claude Code ; le PC devient facultatif. Hermes garde son
conteneur **sans terminal ni outil d'exécution** (garde de P2 inchangée) et reste l'orchestrateur : il sert les
cartes, choisit voie, modèle et effort, et l'exécutant n'exécute que ce qu'il reçoit, dans les bornes de sa politique.

**Rien n'est déployé.** Aucune action sur Railway, aucun compte connecté, aucun identifiant lu : tout ce qui suit est
préparé et prouvé côté dépôt. La **sonde R0** (le premier geste sur Railway) est prête, pas lancée. Le propriétaire
fournit les comptes ; Hermes gère l'exploitation. Procédure du propriétaire : [railway.md § 13](railway.md#13-exécutant-étape-p6).

Conventions : **mesuré** (observé sur un conteneur local ou en CI, avec la commande), **supposé** (à prouver sur
Railway, avec le relevé qui le tranchera). Les numéros de décision sont ceux de [plan.md](plan.md) (D74 à D92 : la
numérotation du cahier, D71 à D89, est décalée de trois).

Sommaire : § 1 en bref · § 2 architecture et identités · § 3 image · § 4 politique · § 5 sonde et régimes · § 6 une
carte · § 7 infrastructure · § 8 secrets et gestes · § 9 coût · § 10 conditions d'usage · § 11 prouvé en local et en CI
· § 12 sur Railway · § 13 non prouvé · § 14 écarts au cahier · § 15 corrections après la relecture
indépendante · § 16 étape P7, partie E : garde « dépôt privé » mesurée, quarantaine après une relance.

---

## 1. En bref

- **Service `executant`** dans le projet `acp` (`.railway/railway.ts`) : construit depuis la racine du dépôt
  (`executant/Dockerfile`, « Wait for CI »), volume `executant-donnees` de 5 Go sur `/donnees`, **ni domaine, ni port,
  ni healthcheck, ni Start Command**, Serverless coupé, `ON_FAILURE` 10 relances, **2 vCPU et 4 Gio**, 90 s pour
  s'arrêter, **aucune variable secrète** (D92).
- **Image** : `python:3.12-slim-trixie` épinglée par condensat, paquets Debian fixés, **Codex 0.156.1** et **Claude
  Code 2.1.283** téléchargés et **vérifiés au build** (SHA-256 et taille ; manifeste de Claude **signé GPG**, vérifié
  contre la clé du dépôt), un UID par agent, superviseur root sous `tini`.
- **Client** : `apps/poste` en mode Linux (deuxième partie de P6) ; mêmes routes `acp-machine/1` que le poste Windows,
  plus les six routes d'exécution (première partie). Il joint Hermes par son **URL publique HTTPS** (D75).
- **Régime** : mesuré à chaque démarrage par la sonde de plateforme. **B** (bubblewrap refusé) est probable sur
  Railway : voie Codex **fermée**, Claude seul en écriture (D79), relecture de repli par un autre modèle de la même
  voie décidée par le routage de Hermes (D91). **A** n'est pas exclu ; seule **R0** tranche.
- **Aucun push** (D82) : la branche intégrée se récupère par `git bundle` et `railway ssh`.
- **Preuves locales** : image construite et testée (binaires réels, sans compte) ; suite `apps/poste` en root dans
  l'image ; bout en bout avec le VRAI exécutant (cible factice) contre l'image Hermes : carte exécutée, committée,
  terminée ; question et reprise ; secret en quarantaine ; revue refusée puis corrigée ; relecture qui lit le code
  relu et son diff (§ 11). Une relecture indépendante de cette pointe a donné 19 constats, tous réels et corrigés
  ou dits (§ 15).

## 2. Architecture et identités

```
Téléphone / PC ──HTTPS + OIDC──► hermes (sans terminal) ◄──HTTPS sortant (long-poll reclamer)── executant
                                   │ tableaux, base du greffon                                    │ PID 1 tini
                                   │ répartiteur, émetteur de notifications                       │ superviseur root
                                   ▼                                                              ├─ codex  (UID 10001)
                              identite (Authelia)                                                 ├─ claude (UID 10002)
                                                                                                  ├─ vérif  (UID 10003)
                                                                                                  └─ git (root) ◄─ GitHub (lecture)
```

L'exécutant n'écoute sur **aucun port** : Hermes ne le joint jamais. Il n'a aucune variable partagée ni référence
vers les autres services (contrôlé par `.railway/verifier.mjs`).

| Identité | UID/GID | Possède | Lit | Rôle |
|---|---|---|---|---|
| `root` | 0 | `/donnees/acp/**` (secrets 0600, état, file de sortie, journal, bundles), clones nus | tout | `tini`, entrée, superviseur, `git` (sans crochets) |
| `acp-codex` | 10001, groupe `acp-travail` (10100) | `/donnees/codex` (0700 ; `auth.json` 0600) | worktree de la carte | Codex CLI |
| `acp-claude` | 10002, groupe 10100 | `/donnees/claude` (0700) | worktree ; jeton Claude dans **son seul** environnement | Claude Code |
| `acp-verif` | 10003, groupe 10100 | rien | worktree | commandes de vérification, sans identifiant |

Chaque agent est lancé par `setpriv --reuid --regid --groups=10100 --inh-caps=-all --bounding-set=-all
--no-new-privs` avec un environnement **calculé** (rien n'est hérité du superviseur) ; la consigne passe par
l'entrée standard (jamais l'argv, lisible par tous les UID). Le dossier d'une carte est `root:acp-travail` 2770
pendant son tour, `0700 root:root` hors de son tour ; les agents écrivent avec un umask 002 (posé par l'entrée).

## 3. Image `executant/`

Détail et commandes : [`executant/README.md`](../../executant/README.md).

| Étape du Dockerfile | Contenu |
|---|---|
| `base` | `python:3.12-slim-trixie@sha256:f77ac9e4…` (Python 3.12.14, Debian 13) ; `git 2.47.3`, `bubblewrap 0.12.0`, `socat`, `ripgrep`, `tini`, `util-linux` (setpriv, unshare, mountpoint), `ca-certificates`, `procps`, versions fixées |
| `binaires` | `gnupg` (étape de construction seulement) ; `executant/bin/verifier-binaires --telecharger` |
| `roues` | `pip download --only-binary=:all: --require-hashes -r requirements/poste-3.12.lock.txt` |
| `commun` | comptes 10001-10003 et groupe 10100, roues installées hors ligne dans `/opt/acp/lib`, sources `acp_poste` et `acp_poste_contrat` **copiées**, lanceur `/opt/acp/lancer.py`, `/etc/acp/executant.toml`, `/etc/acp/claude-settings.json`, `/etc/gitconfig` (0444), entrée, `/usr/local/bin/acp-poste` ; tout en root, rien d'inscriptible par un agent |
| `factice` | **tests seulement** : faux Codex et faux Claude pilotés par scénario |
| `finale` | binaires vérifiés copiés, empreintes recontrôlées (`verifier-binaires --controler`) ; **c'est la cible de Railway** (dernière) |

**Binaires** (`executant/binaires.toml`, relevés en ligne le 1er octobre 2026) :

| | Source | Contrôle |
|---|---|---|
| Codex 0.156.1 | `github.com/openai/codex/releases/download/rust-v0.156.1/codex-x86_64-unknown-linux-musl.tar.gz` | taille 107 380 357 octets, SHA-256 `aff46539…d14533d` (champ `digest` de l'API GitHub, égal au cahier) ; seul le membre `codex-x86_64-unknown-linux-musl` est extrait ; **signature cosign non vérifiée** (identité du certificat non établie, dit au journal de build) |
| Claude Code 2.1.283 | `downloads.claude.ai/claude-code-releases/2.1.283/` | clé `executant/cles/claude-code.asc` importée dans un trousseau jetable, empreinte `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE` exigée ; `manifest.json` vérifié par `manifest.json.sig` (`VALIDSIG` de cette clé) et par son SHA-256 ; version, taille 241 556 664 et SHA-256 `1859583c…5e804ae2` de `linux-x64` lus dans le manifeste signé ET égaux à `binaires.toml`. Jamais `install.sh` |

Aucun `EXPOSE`, aucun `HEALTHCHECK`, aucun `ARG` ni `ENV` au nom de secret ; `python -I` partout (le lanceur de P5
place `/opt/acp/lib` en tête de `sys.path`) ; `DISABLE_UPDATES`, `DISABLE_AUTOUPDATER`, `DISABLE_TELEMETRY`.

**Entrée** `acp-entree-executant` (root, sous `tini`) : refus (code 2, en français) hors `tini` en PID 1, hors root,
sans `/donnees` monté, sur un lien symbolique à la place d'un dossier du volume ou sur un fichier d'un autre
propriétaire (ou un lien) dans `/donnees/acp`, `/donnees/codex` ou `/donnees/claude` ; dossiers du volume créés et
remis aux propriétaires et modes attendus ; alias temporaires que Codex laisse sous `/donnees/codex/tmp/arg0`
retirés avant ce contrôle, sans suivre de lien (un lien à la place de `tmp` ou de `arg0` est refusé) ; `/tmp/acp` en
`root:acp-travail 1770`, `/tmp/acp/caches` et `/tmp/acp/sondes` créés en 0751 avant tout agent ; journal « [acp]
commit déployé : <RAILWAY_GIT_COMMIT_SHA ou inconnu> » ; puis `exec python3.12 -I /opt/acp/lancer.py servir --plateforme linux`.

## 4. Politique `executant/politique/executant.toml`

Versionnée, copiée en 0444 dans l'image, modifiable seulement par une PR (D78) ; Hermes ne la fournit jamais.
**Refusée tant que `[hermes] origine` vaut le gabarit** `https://<libellé-hermes>.up.railway.app` (comme Hermes et
l'IaC) : l'image telle qu'elle est committée refuse de démarrer (mesuré, § 11) ; un test exige l'égalité avec le
libellé de `.railway/railway.ts`. Décisions de conditions d'usage datées : `codex_decide_le` et `claude_decide_le` =
2026-10-01 (D83, D84). Aucun dépôt déclaré : le dépôt jetable et privé de la preuve (D87) s'ajoute par une PR une fois
créé (forme commentée dans le fichier).

## 5. Sonde de plateforme et régimes

`acp-poste sonde-plateforme --json` (code : `apps/poste/src/acp_poste/sonde_plateforme.py`) : **aucun identifiant**,
aucune politique, aucun volume, aucun réseau requis. Relevés : plateforme (architecture, noyau, distribution, cgroup,
`/dev/shm`, espace libre), `/proc/self/status` (seccomp, capacités), réglages des espaces de noms, `unshare -Ur` (root
et 10003), sonde exacte de Codex (`bwrap --unshare-user --unshare-net --ro-bind / / /bin/true`, puis `/proc` neuf),
quatre essais de `codex sandbox -P <profil> -C <dossier> -- …` (vrai, écriture hors du dossier, réseau, lecture d'un
faux `auth.json` interdite par le profil), séparation par UID (`setpriv` vers 10003 : `id -u`, `/proc/1/environ`,
fichier 0600 de root, `kill -0 1`), versions.

Verdict : **A** si tout tient ; **B** sinon ; `uid_separes` faux ⇒ aucune écriture. L'exécutant rejoue la sonde à
chaque démarrage (une migration Railway peut changer d'hôte) et publie le bloc `isolement_linux` de l'inventaire.

| Où | Régime mesuré | Détail |
|---|---|---|
| Docker Desktop (WSL2, noyau 6.18), seccomp par défaut | **B** | `unshare` et `bwrap` refusés (« No permissions to create a new namespace ») ; UID séparés |
| idem, `seccomp=unconfined`, `apparmor=unconfined` | **A** | `codex sandbox -P acp_verif` **accepté par le vrai Codex 0.156.1** : `/bin/true` 0 ; écriture hors du dossier refusée (« Read-only file system ») ; réseau coupé (`getent` 2) ; faux `auth.json` refusé (« Permission denied ») : la forme du profil supposée par le cahier tient sur ce noyau |
| lanceur GitHub `ubuntu-24.04`, seccomp par défaut | **B** | idem Docker Desktop |
| idem, protections levées et `kernel.apparmor_restrict_unprivileged_userns` passé de 1 à 0 | **A** si les chemins système de `/proc` sont aussi démasqués (`systempaths=unconfined`) ; sans eux, `bwrap` passe mais le `/proc` neuf est refusé et `codex sandbox` échoue (B) | consigné dans la CI |

**Aucun de ces relevés ne vaut pour Railway.** La sonde **R0** (D88) se lance dans un projet Railway **jetable**
`acp-sonde`, par le propriétaire, selon [railway.md § 13.2](railway.md#132-sonde-r0-projet-jetable-acp-sonde) ; son
relevé est contrôlé par `scripts/verifier_releve_r0.py` (forme, cohérence du verdict avec ses mesures, aucun
identifiant ni secret) avant d'être publié dans `docs/refonte/preuves/`.

## 6. Une carte dans l'exécutant

Détail : [`apps/poste/README.md`](../../apps/poste/README.md) (« Exécutant Linux ») et cahier § 6. En bref :
`reclamer` (long-poll, `peut_executer` et voies annoncées) → clone nu et `git fetch` en lecture seule → worktree
`hermes/<carte>` → agent sous son UID avec les options imposées (Codex : `codex exec --json …` sous un profil de
permissions nommé, `acp_agent` ou `acp_lecture`, qui interdit `/donnees/codex`, `/donnees/claude`, `/donnees/acp` et
`/etc/acp` et coupe le réseau, **sans** `--sandbox`, qui le ferait ignorer ; fonctions coupées ; Claude :
`claude -p --restricted --tools … --strict-mcp-config
--disallowedTools "mcp__*" --settings /etc/acp/claude-settings.json --json-schema …`) → battements → vérification
sous `acp-verif` (régime A : sous `codex sandbox`, réseau coupé ; régime B : seulement si le dépôt le déclare ;
une commande absente de l'image, code 127, rend « vérification impossible » sans relancer l'agent) →
**commit local par le superviseur** (auteur « ACP exécutant », sans crochets) → fichiers de pilotage (⇒ revue) et
balayage des secrets (⇒ branche `quarantaine/<carte>`, rien n'est envoyé) → `terminer`, `question` ou `bloquer` par la
file de sortie persistante. Une **relecture** part de la branche relue (`hermes/<carte relue>`, que le greffon ne
sert pas comme branche de départ) et lit son diff, écrit par le superviseur pour le groupe des agents ; branche ou
diff absents : carte bloquée, jamais une relecture à l'aveugle. Une requête que le contrat refuse avant l'envoi est
rangée dans `sortie/refusees` (la file continue) et la carte est bloquée avec une raison composée par l'exécutant.

Mesuré sur les vraies CLI sans compte (§ 11) : la commande exacte du superviseur est acceptée par Codex 0.156.1 (il
ouvre son fil) et par Claude Code 2.1.283 (`system/init` : outils demandés seulement, plus `StructuredOutput` ajouté
par `--json-schema` ; aucun serveur MCP ; `--add-dir` admis avec `--restricted`, que le cahier supposait) ; une option
ou une fonction inconnue est refusée ; Claude 2.1.283 sert `claude-opus-5-5` pour l'alias `opus` (la résolution
documentée) ; seul un suffixe de date à huit chiffres est désormais admis entre le modèle servi et la résolution
documentée.

Mesuré avec le vrai `codex exec` 0.156.1 et un **faux fournisseur de modèle** (boucle locale, aucun identifiant ;
`executant/tests/faux_fournisseur.py`), témoin du régime A : avec l'ancienne commande (`--sandbox workspace-write`
ou `read-only`), une commande de Codex lisait le faux `auth.json` et son contenu repartait vers le modèle ; avec le
profil nommé, la lecture est refusée (« Permission denied »), `/etc/acp` aussi, le réseau est coupé, `/tmp` hors de
`$TMPDIR` est en lecture seule, le worktree reste inscriptible (commande et `apply_patch`) en implémentation et ne
l'est pas en relecture (`test_codex_exec_profil_interdit_les_identifiants`, relecture de P6).

## 7. Infrastructure Railway

`.railway/railway.ts` décrit désormais **trois services et trois volumes** (une ressource omise serait supprimée à
l'apply). Ajout de P6 : le service `executant` et le volume `executant-donnees` (§ 1). Le premier plan après P6 doit
afficher, sur un projet où P2 est déjà appliqué, **« 2 to create, 0 to destroy »** (le service et son volume).
`verifier.mjs` (CI) : trois services, volumes disjoints, réglages de l'exécutant (racine `/`, `executant/Dockerfile`,
surveillance de `/executant/**`, `/apps/poste/src/**`, du lanceur, du contrat et du verrou du poste, hors tests et
factices ; 2 vCPU, 4 Gio ; aucune santé, aucun `PORT`, aucune `preserve()`), aucune référence entre services.
Supposé, prouvé au premier build (R1) : `rootDirectory: "/"` avec `RAILWAY_DOCKERFILE_PATH` relatif à la racine,
`Dockerfile.dockerignore` lu par le constructeur de Railway (l'image est de toute façon contrôlée : ni `.git`, ni
`docs/`, ni tests).

## 8. Secrets et gestes du propriétaire

| Secret | Créé par | Rangé | Lu par |
|---|---|---|---|
| Code d'enrôlement `acpe_…` | vous, page Poste | nulle part : saisi dans `acp-poste enroler` (session `railway ssh`) | le greffon (SHA-256) |
| Jeton machine `acpm_…` | le greffon | `/donnees/acp/secrets/jeton-machine` (root, 0600) | superviseur |
| `auth.json` de Codex | vous : `acp-poste connexion codex` (code d'appareil) **sur** l'exécutant | `/donnees/codex/auth.json` (`acp-codex`, 0600) | Codex ; superviseur (balayage, en mémoire) |
| Jeton Claude (`claude setup-token`) | vous, sur votre PC | `/donnees/acp/secrets/claude-oauth` (root, 0600), par `acp-poste connexion claude --stdin` | superviseur, qui le passe au **seul** processus `claude` |
| Jeton GitHub de lecture | vous (portée fine, `Contents: read`, expiration datée) | `/donnees/acp/secrets/github-lecture`, par `acp-poste connexion github --stdin` | superviseur → `git fetch` par `GIT_ASKPASS` |

Jamais dans Git, l'image, une variable Railway, un journal, l'inventaire, la base du greffon, un résumé ni l'argv
d'un processus. Le code d'appareil de Codex ne transite **jamais** par Hermes. Gestes exacts : [railway.md
§ 13.3 bis à 13.6](railway.md#133-bis-dépôt-de-preuve-jetable-et-privé-d87) ; renouvellements : § 13.8.

## 9. Coût et plafond (D85)

Supposé (aucune mesure de RAM ni de CPU de Codex, de Claude ou d'une vérification n'existe encore ; R8 tranche) :
au repos ≈ 2,6 $/mois ; léger (1 h d'agent par jour) ≈ 3,5 $ ; régulier (6 h) ≈ 7,5 $ ; avec la garde de **8 h
d'agent et 20 cartes par jour** (politique), pire cas ≈ 16 $, soit ≈ 22 à 32 $ avec `hermes` et `identite` : la
**limite dure de 30 $** peut couper tout avant la fin du mois, d'où l'**alerte à 15 $** et le relevé hebdomadaire
(`railway usage`). Une carte à la fois, 2 vCPU, 4 Gio. Réévaluation après une semaine de mesure.

## 10. Conditions d'usage (D83, D84)

Lues par le cahier (§ 2), tranchées par le propriétaire et consignées le 1er octobre 2026 :
- **Codex** avec le compte ChatGPT du propriétaire, **dépôts privés seulement** (voie Codex fermée pour un dépôt
  `public` : refus codé), un seul `auth.json` créé par code d'appareil **sur** l'exécutant, jamais copié ;
- **Claude Code** avec l'abonnement du propriétaire (`setup-token`), garde-fous tenus par Hermes et l'exécutant : une
  carte à la fois, 20 cartes et 8 h d'agent par jour, voie retirée à 90 % du quota observé ;
- usage personnel, sans revente ni service à des tiers. Ce n'est pas une preuve de conformité : une lecture et une
  décision écrite.

## 11. Prouvé en local et en CI

Windows 10, Docker 29.5.3 (Docker Desktop, noyau WSL2 6.18), Python 3.12.10 python.org, Node 24.19.0.

| Preuve | Commande | Résultat |
|---|---|---|
| Build de l'image (binaires réels, vérifiés) | `docker build -f executant/Dockerfile -t acp-executant:p6 .` | « Codex 0.156.1 vérifié », « Claude Code 2.1.283 vérifié (manifeste signé par 31DDDE24…CACE) », « signature cosign de Codex non vérifiée », empreintes recontrôlées dans la cible finale |
| `verifier-binaires` hors ligne (clé GPG d'essai) | `pytest executant/tests/test_verifier_binaires.py` (conteneur Linux avec gpg) | 10 réussis : empreinte fausse, binaire altéré, manifeste non signé, altéré après signature, signé par une autre clé, clé d'une autre empreinte, manifeste différent de `binaires.toml`, archive sans le membre : tous refusés |
| Tests statiques et de l'image construite | `ACP_IMAGE_EXECUTANT=acp-executant:p6 pytest executant/tests` | 28 réussis (image) ; voir CI ci-dessous pour le total avec `verifier-binaires` |
| Suite `apps/poste` et contrat **en root dans l'image** | `docker run --rm --entrypoint /usr/bin/tini acp-executant-essais:p6 -- python3.12 -m pytest apps/poste/tests hermes/plugins/acp-poste/contrat/tests` | 745 réussis, 20 ignorés (propres à Windows) |
| Sonde (répétition de R0) | `docker run --rm --entrypoint /usr/local/bin/acp-poste acp-executant:p6 sonde-plateforme --json` | régime B (seccomp par défaut), régime A (témoin) : § 5 ; les deux relevés passent `scripts/verifier_releve_r0.py` |
| **Bout en bout** avec Hermes | `ACP_IMAGE_TESTS=acp-hermes-tests:p6i ACP_IMAGE_EXECUTANT_FACTICE=acp-executant:p6factice pytest hermes/tests/contrat/test_executant_bout_en_bout.py` | **6 réussis** (106,84 s) : mise en service (jeton Claude déposé, enrôlement par code, empreinte confirmée, régime B, voie Codex fermée) ; carte exécutée, **committée localement** (« ACP exécutant »), vérifiée sous `acp-verif`, terminée ; le faux agent (UID 10002, environnement limité à 10 variables) ne lit ni `jeton-machine`, ni `claude-oauth`, ni `/donnees/codex/auth.json`, ni `/proc/1/environ` ; question → réponse → fil repris (`--resume`) → terminée ; secret ⇒ `quarantaine/<carte>`, carte bloquée, notification « secret » ; revue de `.github/workflows` refusée → reprise avec le motif → terminée sans le fichier ; références distantes inchangées, 25 requêtes GET/HEAD seulement vers le dépôt, aucun jeton ni secret factice dans les journaux de Hermes, de l'exécutant, sa file de sortie et la base du greffon |
| **Relecture** de bout en bout (ajoutée par la relecture, § 15) | même commande, `test_relecture_lit_le_code_relu_et_son_diff` | planification, implémentation, puis relecture de repli par la même voie (D91, régime B) : le relecteur, sous l'UID 10002, lit le diff (« +contenu relu ACP-RELU-7C2B ») et le fichier relu dans son worktree ; **témoin** : le même banc avec `execution.py` d'avant la correction échoue (diff « refusé (PermissionError) », fichier relu « (FileNotFoundError) ») ; sur la pointe `815ae6f`, les **7** scénarios réussissent (contrat complet ci-dessous) |

Intégration continue :
- `executant.yml` (nouveau), run [36889016245](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36889016245)
  sur `c20124d` : **vert** — build avec binaires réels vérifiés ; 38 tests de l'image (statiques, `verifier-binaires`,
  image construite, sonde) ; sonde B sous seccomp par défaut, témoin A (restriction AppArmor du lanceur 1 → 0,
  consignée) ; suite en root dans l'image : **750 réussis, 20 ignorés**. Les tests propres à root, ignorés par la CI
  Linux sans root depuis la deuxième partie, tournent donc en CI ici. Premier run (`3c63bec`) rouge : témoin A en B
  sur le lanceur GitHub (`/proc` neuf refusé), cause masquée par un avertissement de Codex ; corrigé par `c20124d`.
- `image.yml` run [36892387102](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36892387102)
  sur `f9b5032` : **vert** — contrat **164 réussis** (dont les 6 du bout en bout avec le vrai exécutant), navigateur
  8 réussis ; même résultat sur `32f7f85`, dernier commit qui déclenche `image.yml` (run
  [36892623742](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36892623742) : 164 et 8) ; sur
  `10dc18e` (IaC à trois services) : run
  [36888645780](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36888645780) vert, contrat 158.
- `ci.yml` vert sur chaque commit de la troisième partie ; sur `eb55afa`, run
  [36894084340](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36894084340) : Windows 898 réussis
  et 69 ignorés, Linux 919 réussis et 48 ignorés (tests de l'image et de `verifier-binaires` sous Windows : ignorés,
  avec leur raison), interface 120, moteur 74 ; `executant.yml` sur `eb55afa` :
  [36894084716](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36894084716) vert, 38 tests de
  l'image et 750 réussis, 20 ignorés en root dans l'image.
- Après les corrections de la relecture (§ 15), pointe `815ae6f` : `ci.yml`
  [36925637152](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36925637152) vert (Windows 927
  réussis et 86 ignorés, Linux 959 réussis et 54 ignorés, interface 120, moteur 74) ; `executant.yml`
  [36925637270](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36925637270) vert (43 tests de
  l'image, suite en root dans l'image 777 réussis et 20 ignorés) ; `image.yml`
  [36925637269](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36925637269) vert (682 tests dans
  l'image Hermes, contrat **165 réussis** dont les 7 du bout en bout, navigateur 8).

## 12. Sur Railway, avec vos gestes (à faire)

| N° | Preuve | Exige | État |
|---|---|---|---|
| R0 | Sonde de plateforme : verdict A ou B et relevés, publiés en entier | projet jetable `acp-sonde`, **aucun** identifiant | **à faire** (prête) |
| R1 | Déploiement : `railway config pull --json` conforme ; « [acp] commit déployé » ; aucune socket à l'écoute (`acp-poste diagnostic --isolement`) | apply de l'IaC | à faire |
| R2 | Enrôlement, empreinte confirmée, inventaire Linux avec le régime | votre session ACP | à faire |
| R3 | `model/list` réel depuis l'exécutant ; quotas Codex ; Claude « Inconnu » puis partiel | connexions (§ 8) | à faire |
| R4 | Exfiltration : les lectures interdites du bout en bout rejouées sur le vrai conteneur | R3 | à faire |
| R5 | Projet complet sur le dépôt jetable privé, depuis le téléphone ; bundle rapatrié, tête identique | D83, D84 | à faire |
| R6 | Redéploiement de l'exécutant pendant une carte : `arret`, puis `reprendre` ; coupure mesurée | R5 | à faire |
| R7 | Redéploiement de Hermes pendant une carte : battements valides | R5 | à faire |
| R8 | RAM et CPU d'une carte Codex, d'une carte Claude, d'une vérification | R5 | à faire |
| R9 | Long-poll derrière le bord sur 24 h | R2 | à faire |
| R10 | Révocation : déploiement « Active », attente d'enrôlement, aucune requête, aucune notification « hors ligne » | fin | à faire |

## 13. Non prouvé (dit tel quel)

- **Régime A ou B sur Railway** : seule R0 le tranche ; les témoins locaux ne valent pas preuve.
- Les **vraies CLI connectées** sous leur UID (aucun compte n'a été utilisé) ; la tenue de `setup-token` après une
  montée de version de Claude Code ; `claude -p "/usage"` comme source de quotas.
- **Signature cosign de Codex** : non vérifiée (identité non établie).
- Le **profil de permissions** imposé à `codex exec` (`acp_agent`, `acp_lecture`) n'est éprouvé qu'en témoin A local
  et en CI, avec un faux fournisseur de modèle (§ 6, § 15) ; sur Railway, R0 dit si la voie Codex s'ouvre.
- Prise en compte par Railway de `rootDirectory: "/"`, `RAILWAY_DOCKERFILE_PATH`, `Dockerfile.dockerignore` et des
  clés typées non documentées (`sleepApplication`, `limitOverride`, `checkSuites`, `watchPatterns`).
- `railway ssh` vers l'exécutant en attente d'enrôlement, `scp` du bundle, coupure d'un redéploiement sous 90 s.
- Coût réel (R8 et une semaine de relevés).
- Les faux CLI du bout en bout ne prouvent que la **plomberie**, jamais la qualité d'un modèle.

## 14. Écarts au cahier, justifiés (troisième partie)

- **Verrou des roues** : `requirements/poste-3.12.lock.txt` est utilisé **tel quel** dans l'image (au lieu d'un
  `requirements-executant.txt` en parité) : mêmes versions que le poste par construction, aucun fichier à tenir en
  parité ; `watchPatterns` suit ce verrou.
- **Lanceur** en `/opt/acp/lancer.py` (et non `/opt/acp/bin/lancer.py`) : le lanceur de P5 place `lib` **à côté de
  lui** en tête de `sys.path` ; `/opt/acp/lib` impose donc `/opt/acp`.
- **Sonde** dans `apps/poste` (deuxième partie) et non `executant/sonde/` : l'image l'embarque avec le client ; un
  contrôleur de relevé (`scripts/verifier_releve_r0.py`) est ajouté pour la publication.
- **Bout en bout** dans la suite de contrat de l'image Hermes (`image.yml`), sans Docker Compose : même outillage que
  les autres tests de contrat (réseau, bord TLS factice, nettoyage vérifié) ; quatre scénarios (carte complète,
  question, secret, revue refusée), cinq depuis la relecture (relecture de repli, § 15), au lieu des quatorze du
  cahier ; les autres sont couverts par les tests de la
  deuxième partie (faux agents) ou restent à faire. Le dépôt distant factice sert le protocole git « bête » en HTTPS
  (lecture seule) ; le plafond de projets actifs est relevé à 6 pour le banc (dit dans le test).
- **Workflow séparé** `executant.yml` pour l'image de production (au lieu d'un travail de plus dans `image.yml`) :
  il ne reconstruit pas Hermes (≈ 4 min au lieu de ≈ 60) ; `image.yml` construit la cible factice pour le bout en
  bout.
- **Témoin du régime A** : `systempaths=unconfined` ajouté (le lanceur GitHub refuse sinon le `/proc` neuf).
- **umask 002** posé par l'entrée (le cahier le prévoyait pour les agents sans dire où) : hérité par le superviseur,
  donc par chaque agent ; secrets et état restent protégés par des modes explicites.
- **Corrections apportées au client** en chemin, chacune testée : suffixe de date à huit chiffres seulement entre
  modèle servi et résolution documentée (`3b763ac`) ; diagnostic du `config.toml` de Codex comparé à la variante
  Linux (`32f7f85`) ; sortie de la sonde débarrassée de l'avertissement de Codex qui masquait la cause d'un refus
  (`c20124d`).
- **Non fait** : option B de push (D82) conçue, non activée. La purge des worktrees et des bundles et l'alerte à
  J-30 du jeton Claude, annoncées « non faites » ici, sont faites depuis la relecture (§ 15).

## 15. Corrections après la relecture indépendante (1er octobre 2026)

Relecture de la pointe `35c94af` en trois lentilles (exactitude, sécurité, exploitation) : 19 constats, dont deux
recoupés (profil de Codex, forme `uv`). Tous ont été **vérifiés et trouvés réels** ; trois défauts de plus ont été
trouvés en les vérifiant (marqués « trouvé »). Chaque correction de code porte un test qui échoue sans elle, rejoué
sur le code d'avant (témoin) ; la procédure du propriétaire a été reprise (railway.md § 9 et § 13).

| Constat | Gravité | Correction | Preuve | Commit |
|---|---|---|---|---|
| `diagnostic`, `quotas`, `releve`, `preuve` lancés en root dans `railway ssh` lançaient Codex et Claude **en root** : fichiers de root sous `/donnees/codex`, puis refus de démarrer au redémarrage suivant | critique | lanceur du service (UID de l'outil, son environnement, ses dossiers), verrous de Codex et de Claude pris ; remise en état documentée (railway.md § 13.8) | test d'image : ces commandes en root, puis redémarrage **accepté** (échoue sur l'image d'avant) ; tests POSIX | `a7620ac` |
| **trouvé** : Codex laisse, **même sous son UID**, des liens sous `$CODEX_HOME/tmp/arg0` (sortie par `--version`, arrêt) : l'entrée refusait tout redémarrage après un relevé | critique | l'entrée retire ces alias avant son contrôle, sans suivre de lien | même test d'image (4 liens présents, redémarrage accepté) ; un lien à la place de `arg0` reste refusé | `a7620ac` |
| **trouvé** : `acp-poste releve` levait une trace (`version_windows`) sous Linux | moyenne | inventaire Linux (isolement de la sonde du démarrage) | test ; test d'image (aucune trace, code 0) | `a7620ac` |
| **trouvé** : `quotas` et `releve` ne prenaient pas les verrous de Codex et de Claude : pendant une carte, un second processus Codex pouvait tourner sur le `CODEX_HOME` de l'agent | moyenne | verrous de Codex et de Claude pris par la CLI sous Linux | test (verrou tenu : refus, code 2) | `a7620ac` |
| Régime A : les commandes de Codex lisaient `auth.json` (même UID ; avec `--sandbox`, Codex 0.156.1 ignore `default_permissions` et lit toute la racine) | haute | profil nommé `acp_agent` / `acp_lecture` imposé par `-c`, **sans** `--sandbox` : identifiants interdits, réseau coupé, écriture du worktree et de `$TMPDIR` seulement ; sans bubblewrap (régime B), Codex refuse alors de démarrer | vrai `codex exec` contre un faux fournisseur de modèle, témoin A : contenu de `auth.json` renvoyé au modèle avant (implémentation **et** relecture), « Permission denied » après | `7dab6aa` |
| Relecture à l'aveugle : diff écrit `root:root 0640`, illisible par les agents ; worktree parti de la branche de base | haute | worktree de la relecture sur `hermes/<carte relue>`, diff au groupe `acp-travail` ; branche ou diff absents : carte bloquée | test sous les vrais UID ; **bout en bout** (planification, implémentation, relecture de repli D91) : témoin avec le code d'avant « refusé (PermissionError) » et « (FileNotFoundError) », corrigé : diff et code lus | `86e1829`, `815ae6f` |
| Root suivait un lien posé sous `/tmp/acp` (inscriptible par le groupe des agents) ; `reponse.json` lu en suivant les liens, sans borne | moyenne, basse | dossiers créés ou repris sans suivre de lien (vrai dossier, propriétaire attendu, `chown`/`chmod` sur descripteur), `/tmp/acp/caches` et `/tmp/acp/sondes` créés par l'entrée ; `reponse.json` : fichier ordinaire de `acp-codex`, `O_NOFOLLOW`, 64 Kio | tests POSIX (cible intacte, carte bloquée ; lien jamais suivi) ; modes vérifiés dans l'image | `8fa1be6` |
| Une requête refusée par le contrat **côté exécutant** (un NUL) restait en tête de la file : plus aucune réclamation ; un NUL dans le résumé faisait échouer le commit | moyenne | refus définitif (`RefusAvantEnvoi`) rangé dans `sortie/refusees`, la file continue, repli `bloquer(capacite)` ; caractères de contrôle retirés des textes de l'agent | reproduction de la relecture devenue test (aucun `reclamer` en 15 s avant) ; tests de la file et de l'exécution | `9c8f66a` |
| `AGENTS.override.md` (Codex) et `CLAUDE.local.md` (Claude Code) hors des fichiers de pilotage | moyenne | ajoutés à toute profondeur ; D90 complétée | tests ; chaînes relevées dans les binaires de l'image | `bed1b70` |
| Forme `uv` de la politique inutilisable (ni uv ni pytest dans l'image) ; code 127 traité en échec ordinaire, avec deux reprises de l'agent | moyenne | forme `python3.12 -m unittest …`, outils de l'image listés ; 127 : « vérification impossible », raison donnée, aucune reprise | tests ; forme commentée éprouvée dans l'image (0 si les tests passent, 1 sinon) | `a65ec13` |
| Contrôleur du relevé R0 exigeant pydantic (trace anglaise, code 1) | haute | bibliothèque standard seulement (motifs chargés depuis leur fichier, garde copiée en parité vérifiée) ; code 2 en français si les motifs manquent | lancé sans paquet tiers (`-S -I`) ; réel : Python 3.13 du Store du PC et `python:3.12-slim` nu, code 0 | `23a169e` |
| Verdict de la sonde et attente d'enrôlement absents des journaux de Railway | basse | lignes `[acp] …` sur stderr (sonde, attente au début puis chaque jour, révocation, suspension) | tests ; `docker logs` dans le test d'image | `6d363a4` |
| `purge_apres_jours` jamais appliqué ; aucune alerte avant l'expiration du jeton Claude | moyenne | purge **automatique** une fois par jour, hors carte (branches gardées) ; échéance estimée du jeton (dépôt + un an) publiée à Hermes, alerte de la page Poste à 30 jours, ligne quotidienne des journaux | tests (poste, contrat, image Hermes) | `197a8ea` |
| Procédure : coûts à deux services, commit de la sonde ambigu, `railway login`/`link` absents, aucune étape pour le dépôt jetable, commentaires du diagnostic inexacts, bascule vers le PC impossible si Railway est en panne | moyenne, basse | railway.md § 9 (trois services, ≈ 9 à 32 $, pire cas ≈ 159 $) et § 13 (commit à sonder, connexions, § 13.3 bis, outils de l'image, exploitation, renouvellements, bascule requalifiée, forme D68) | relecture ; commande du commit à sonder rejouée (`35c94af` → `eb55afa`) | `6c6bd6d` |

**Limites restantes, dites.**
- Le profil de Codex n'est éprouvé qu'en **témoin A local** ; sur Railway, R0 tranche (régime B probable : voie Codex
  fermée par D79, et Codex refuse maintenant de démarrer sous ce profil sans bubblewrap).
- L'alerte du jeton Claude passe par la page Poste et les journaux, **pas** par une notification téléphone (un genre
  de notification nouveau exige une migration du schéma du greffon, non faite) ; l'échéance est **estimée** (dépôt
  + un an). L'échéance du jeton GitHub n'est pas connue de l'exécutant.
- Les historiques des CLI (`/donnees/codex/sessions`, `/donnees/claude/projects`) ne sont pas purgés.
- Les fichiers non suivis qu'une vérification laisse dans le worktree sont committés s'ils ne sont pas ignorés par le
  `.gitignore` du dépôt.
- `uv` n'est pas ajouté à l'image : sa version et son empreinte ne sont pas dans le cahier (aucun téléchargement non
  prévu) ; la forme pip de railway.md § 13.6 n'est pas éprouvée.

**Rejeu final** (pointe `815ae6f`, export LF par `git archive`, images reconstruites depuis cet export ; Windows 10,
Docker 29.5.3, Python 3.12.10 python.org) :
- suite Windows (`python -m pytest`, venv avec `cryptography`) : 927 réussis, 83 ignorés, 3 échecs « not a git
  repository » propres à l'export, rejoués dans le worktree : 3 réussis ;
- `executant/tests` sur l'hôte (image finale et cible factice) : 33 réussis ; `verifier-binaires` et
  `test_dockerfile` dans un conteneur Linux avec gpg : 18 réussis ;
- `apps/poste` et contrat **en root dans l'image d'essais** : 777 réussis, 20 ignorés (propres à Windows) ;
- tests dans l'image Hermes : 682 réussis ;
- contrat `hermes/tests/contrat` (bout en bout compris) : 162 réussis et 3 erreurs d'environnement (l'export n'a pas
  le SDK de `.railway`), rejoués dans le worktree propre (SDK présent) : 3 réussis ; navigateur : 8 réussis dans le
  worktree propre (sur l'export : 4 échecs d'environnement, « axe-core absent », jamais ignorés) ;
- témoins négatifs de P6 : 27, aucune anomalie ;
- contrôles du dépôt (`check_version`, `generer_themes --check`, `verifier_catalogue`, `check_lock`,
  `check_engine_frozen`) : code 0 ; `.railway/verifier.mjs` conforme ; Vitest 120 réussis ;
- CI : trois workflows verts sur `815ae6f` (§ 11).

## 16. Étape P7, partie E : garde « dépôt privé » mesurée, quarantaine après une relance

État du **2 octobre 2026** (branche `refonte/hermes-p7e`). Cahier P7 § 11.2, § 11.3, § 12.4, § 13.5 et correction
K25. **Aucun dépôt réel n'est ajouté à `executant.toml`** : l'ajout d'un dépôt réel est une PR à part, après le
« oui » écrit du propriétaire pour ce dépôt (cahier P7 § 11.1).

### 16.1 Ce qui change

Jusqu'à P6, la voie Codex n'était refusée que si la politique **déclarait** `acces = "public"` : un dépôt public
déclaré `jeton_lecture` passait, alors que D83 n'admet Codex avec le compte ChatGPT que sur un dépôt **privé**.
Désormais l'exécutant **mesure** chaque dépôt (`apps/poste/src/acp_poste/depots.py`, `Depots.visibilite`) :

1. **accès anonyme** : `git ls-remote --heads -- <url>` avec les options imposées à toute commande
   (`credential.helper=` vide, protocoles fermés sauf `https`, crochets coupés…), l'environnement du superviseur
   (`GIT_ASKPASS=/bin/false`, `GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_GLOBAL=/dev/null`, `HOME=/nonexistent`), **aucun
   jeton**, délai de 30 s (tout le groupe de processus tué au délai), lancé **depuis la racine des clones** (jamais un
   dépôt : aucune configuration locale, `insteadOf` ou `http.extraHeader`, ne peut détourner la mesure ni le jeton) ;
2. **lecture** : la lecture que l'exécutant fera vraiment — la même commande **avec le jeton de lecture** pour un dépôt
   `jeton_lecture` (`acp-askpass`, variable `ACP_JETON_LECTURE` : jamais dans l'argv, le journal ni un message) ;
   l'accès anonyme pour un dépôt déclaré `public` ; jeton absent : « inconnue ».

| Sortie de git | `visibilite` (anonyme) | `lecture` |
|---|---|---|
| code 0 | `public` | `ok` |
| code 128 et un motif de refus composé par git (ci-dessous) | `prive` | `refusee` |
| tout le reste : délai, réseau, certificat, 403, 500, motif inconnu, git absent | `inconnue` | `inconnue` |

Motifs reconnus, **relevés sur git 2.47.3** (la version épinglée dans `executant/Dockerfile`) contre un faux serveur
HTTPS local (`apps/poste/tests/test_visibilite.py::test_messages_de_git_releves`), identiques sur git 2.42 :

```
fatal: could not read Username for 'https://<hôte>': terminal prompts disabled     (401 sans identifiant)
fatal: Authentication failed for 'https://<hôte>/<propriétaire>/<dépôt>.git/'       (401 après le jeton)
fatal: repository 'https://<hôte>/<propriétaire>/<dépôt>.git/' not found             (404 : hors de portée, inexistant)
```

Seules ces lignes, **composées par git lui-même** et en début de ligne, comptent : le texte du serveur arrive préfixé
de `remote: ` et ne peut pas forger un refus (cas `faux-refus` du faux serveur). GitHub répond de la même façon à un
dépôt privé et à un dépôt inexistant : seule la paire « anonyme refusé » **et** « lecture avec le jeton réussie »
établit le privé. La mesure n'étant pas atomique, l'accès anonyme est **refait après** une lecture réussie : `prive`
exige deux refus (un dépôt devenu lisible sans identifiant entre-temps est dit `public` ; relecture indépendante).

Le clone nu d'un dépôt est lié à l'URL mesurée : si la politique réaffecte un alias à une autre URL (par une PR), le
clone de l'ancienne n'est jamais récupéré à sa place (« vient d'une autre URL que la politique », carte bloquée) ; le
propriétaire le retire après en avoir récupéré les branches.

### 16.2 Règle, en échec fermé

- **Codex** n'est ouvert pour un dépôt que si la mesure **fraîche**, refaite **avant chaque carte Codex** (la
  visibilité peut changer entre deux inventaires), dit `prive` **et** `ok` ; sinon la carte est bloquée (`politique`)
  avant toute préparation, avec la raison : « Voie Codex fermée pour le dépôt « … » : il n'est pas prouvé privé
  (visibilité mesurée …, lecture avec le jeton …) ». Rien n'est lancé, rien n'est cloné.
- **Claude** reste ouvert sur un dépôt public (D84) ; une carte Claude d'un dépôt `jeton_lecture` ne mesure rien.
- **Déclaré `public` mais mesuré `prive`** : le dépôt est refusé avant chacune de ses cartes (« la politique dit public,
  GitHub refuse l'accès anonyme : jeton requis ») ; la correction passe par une PR de `executant.toml`.
- **Inventaire** : la mesure de chaque dépôt distant est publiée au démarrage, à chaque relevé (`sondes.intervalle_s`)
  et après chaque carte, dans les champs facultatifs du contrat `Depot` (`visibilite`, `lecture`, `verifie_le`, livrés
  par la partie A) ; jamais une mesure inventée (un dépôt non mesuré reste `{"alias"}`). La raison détaillée reste au
  journal de l'exécutant (`visibilite_depot`), jamais dans l'inventaire.
- **Double contrôle** : côté greffon, `routage.voies_fermees(…, depot_alias)` (partie A) ferme `poste-codex` pour tout
  dépôt que le dernier inventaire ne dit pas `prive` + `ok` ; `routage.depots_du_poste` en tire, par le même calcul,
  la carte « Dépôts » de la page Poste et le grisage de Codex dans « Nouveau projet » (bloc `executant.depots` de
  `GET /v1/poste`).
- Le poste Windows n'exécute aucune carte : il ne mesure rien, ses dépôts restent « jamais mesurés » (Codex fermé).

### 16.3 Relance d'une carte bloquée pour un secret (correction K25)

Après un secret, la branche `hermes/<carte>` est renommée `quarantaine/<carte>` et le worktree de la carte reste posé
dessus. Avant la partie E, une carte relancée aurait repris ce worktree (« gardé s'il existe ») : l'agent aurait
travaillé sur le commit fautif, et le balayage, sans base, n'aurait plus rien vu. Désormais :

- `Depots.worktree` ne reprend un worktree que s'il est posé sur la branche de la carte (`HEAD` lu dans son gitdir,
  root, jamais dans le `.git` du dossier) ; sinon il le retire et la carte repart de son départ sur une **branche
  neuve** ;
- branche absente alors que la carte a déjà tourné : sa base, sa **session d'agent** (dont la transcription a vu le
  travail fautif) et sa préparation sont oubliées, même si Hermes la sert en `reprise: true` ; journal `branche_neuve` ;
- la branche `quarantaine/<carte>` reste, jamais intégrée ni poussée.

Prouvé par `apps/poste/tests/test_execution.py::test_relance_apres_secret_branche_neuve_sans_le_commit_fautif` (la
branche servie ne contient pas le commit fautif, la quarantaine est intacte, la base est le départ actuel, le diff ne
porte que le travail neuf, l'agent ne voit plus le fichier) et `…::test_relance_apres_secret_jamais_l_ancienne_session`.
Le greffon **lève donc le refus** `carte_secret` **pour un exécutant de la partie E** : la carte se relance, la file
Questions dit que le travail reste en quarantaine (`quarantaine` dans `GET /v1/questions`) et la réponse de la relance
dit `branche_neuve`. Le greffon reconnaît un tel exécutant à ce qu'il publie : seul un exécutant de la partie E porte la
visibilité mesurée de ses dépôts dans son inventaire (même commit que la correction K25). Sans elle (exécutant de P6
pendant la fenêtre de déploiement, poste Windows, aucun inventaire), la relance d'une carte bloquée pour secret reste
refusée (409 `carte_secret`, « relance possible dès que l'exécutant à jour a publié son inventaire »), en échec fermé.

### 16.4 Preuve « aucune action accord requis sans geste » (premier dépôt réel)

`scripts/preuve_accord_requis.py` lit les relevés `git ls-remote` avant et après le premier projet, l'export du projet
(`GET /v1/projets/<id>`), la liste cron (`GET /api/cron/jobs`) et l'inventaire avant et après, puis imprime le tableau
« geste → preuve → verdict » (`conforme`, `NON CONFORME`, `non prouvé` : jamais un succès supposé ; codes 0, 1, 3 ; 2
pour une pièce illisible). Chaque ligne ne prouve que ce qu'elle lit : la suppression **côté dépôt distant** (références
inchangées) ; le périmètre par les dépôts, le réseau des agents déclaré par la politique (le réseau mesuré est dit), les
connexions et l'empreinte de la politique ; les revues rejouées **dans l'ordre** du journal (une carte refusée qui
repasse en revue exige sa propre décision du propriétaire), et un journal plein (l'export n'en rend que 100 lignes) vaut
« non prouvé ». Aucune référence imprimée (nombre et empreinte SHA-256 de la liste triée), nom réel du dépôt
remplacé par son alias, sortie balayée par les motifs de secrets du contrat. Ce qu'il ne lit pas est listé sous le
tableau : capture des permissions du jeton, écritures en mémoire et en skills en attente, journal de l'exécutant.
Bibliothèque standard seulement ; éprouvé sur des fixtures (`scripts/tests/test_preuve_accord_requis.py`), **jamais
lancé sur un vrai dépôt** à ce jour. Le résultat du premier dépôt réel ira dans `docs/refonte/preuves-p7/`.

### 16.5 Prouvé en local (2 et 8 octobre 2026, Windows 10, Python 3.12.10 python.org, Node 24 ; Docker 29.5.3 le 2)

| Suite | Résultat |
|---|---|
| `apps/poste/tests/test_visibilite.py` contre le faux serveur HTTPS (`faux_depot_https.py`, autorité jetable du faux Hermes) | 20 réussis sous Windows (git 2.42) et dans l'image d'essais de l'exécutant (git 2.47.3, root) |
| dépôt complet sous Windows (`python -m pytest`, 8 octobre) | 1003 réussis, 83 ignorés (propres à Linux, à root ou à une image construite) |
| `apps/poste` et contrat partagé en root dans l'image d'essais (git 2.47.3, 2 octobre) | 821 réussis, 20 ignorés (propres à Windows) avant les corrections de relecture ; après elles, 822 réussis et 1 échec de minuterie connu de P6 (`test_pause_locale_aucune_execution`, sous la charge de piles de contrat voisines ; rejoué seul trois fois : réussi) |
| tests dans l'image Hermes (greffon, 2 octobre) | 789 réussis |
| contrat ciblé (exécution, projets, interface, machine, bout en bout de l'exécutant, parcours P7 ; 2 octobre) | 54 réussis ; 1 échec d'environnement (`test_bundles_servis_identiques_au_depot` : image construite avant la dernière reconstruction des bundles) |
| Vitest (interface, 8 octobre) | 179 réussis ; bundles reconstruits, `esbuild --check` à jour |
| témoins de mutation (chaque règle de sécurité, rétablie après l'essai ; témoin sans mutation vert) | 43 mutations, **toutes rouges** : classement des sorties de git et mesure (10, dont « deux refus anonymes » et « clone d'une autre URL »), contrôle de la carte (5), inventaire (1), quarantaine côté exécutant (2), greffon (7, dans l'image, dont la garde « exécutant de la partie E »), interface (8), outil de preuve (10, dont l'ancienne logique des revues et du périmètre, remise en place) |

Les suites qui demandent Docker (image, contrat, navigateur) sont rejouées à neuf par l'intégration continue sur la
tête poussée (workflows « Image Hermes » et « Image de l'exécutant »).

### 16.6 Limites, dites

- La mesure ne voit que ce que voit git : un dépôt rendu public **après** la dernière mesure n'est vu qu'à la carte
  Codex suivante (mesure fraîche) ou au relevé suivant ; une carte Claude d'un dépôt `jeton_lecture` ne mesure rien.
- Un inventaire de P7 est refusé par un greffon de P6 (`extra="forbid"`) pendant la fenêtre de déploiement : voie
  Codex « inconnue », donc fermée (sûr) ; « Relever maintenant » le republie.
- Pendant la même fenêtre, une carte relancée après un secret et servie à un exécutant de P6 reprendrait le worktree
  en quarantaine ; elle ne pourrait rien en sortir (aucun push ; branche `hermes/<carte>` absente : intégration et
  bundle refusés ; renommage en quarantaine en échec : carte bloquée ; depuis la relecture finale de P7, bloquée pour
  un secret, § 16.7).
- Les motifs sont relevés sur git 2.47.3 et 2.42 ; une autre version de git dans l'image doit rejouer
  `test_messages_de_git_releves` (la CI de l'exécutant le fait sur l'image construite).
- Aucun appel à GitHub n'a été fait : la mesure n'est prouvée que contre le faux serveur ; sa première mesure réelle est
  celle du premier dépôt réel (cahier P7 § 13.6, n° 5). Si GitHub limite les accès anonymes depuis les adresses de
  Railway (403, 429), la mesure dit « inconnue » et Codex reste fermé : échec fermé, à surveiller au premier dépôt réel.
- La mesure de chaque dépôt se fait dans la boucle des relevés : au pire 3 × 30 s par dépôt injoignable retardent la
  publication de l'inventaire (une poignée de dépôts, un à la fois : borne acceptée).
- Le greffon ne périme pas une mesure ancienne (`verifie_le` n'est pas comparé) : une mesure « prive + ok » vieille de
  plusieurs jours garde Codex ouvert au routage ; l'exécutant remesure de toute façon avant chaque carte Codex.
- Constaté par la relecture de P6 et **corrigé par la relecture finale de P7** (§ 16.7) : le balayage des secrets ne
  portait que sur le diff cumulé de la carte (un secret d'un commit « wip » puis retiré restait dans l'historique, donc
  dans l'intégration et le bundle) ; un échec du renommage en quarantaine bloquait la carte en « capacité ».
- Un secret d'une forme inconnue des motifs du contrat partagé et absent du coffre passe toujours (barrière de plus,
  pas une garantie : balayage.py). Une branche déjà poussée par ailleurs (`--remotes`) n'est pas rebalayée : rien n'est
  jamais poussé par l'exécutant (D82).

### 16.7 Relecture finale de P7 : historique balayé, quarantaine jamais contournée (D118, D119)

Défauts (a) et (b) de P6, confirmés par la relecture finale de P7 (constats securite-1 et securite-2), corrigés dans
`apps/poste` :

- **Historique non poussé balayé** (`Depots.lignes_ajoutees_non_poussees`) : les lignes ajoutées par **chaque** commit
  absent du dépôt distant (`<tête> --not --remotes`), merges compris (diff combiné `--cc` : ce qu'une fusion ajoute à
  tous ses parents). Balayé à la conclusion de chaque carte (le diff cumulé l'est toujours), donc à l'intégration ;
  **après chaque commit « wip »** (blocage, limite de quota, interruption) : un secret y met la branche en quarantaine et
  la carte est bloquée **pour un secret** — jamais en quota (repris automatiquement), jamais rendue sur la branche
  fautive ; et par `git bundle` (`acp-poste bundle`), qui refuse d'emballer une branche dont l'historique non poussé
  porte un secret, même retiré depuis (motifs et valeurs exactes du coffre ; rien n'est écrit).
- **Quarantaine impossible** (`git branch -M` en échec) : la carte est **quand même** bloquée pour un secret (raison
  fixe, journal `secret_detecte` puis `quarantaine_impossible`), et sa session garde `quarantaine_en_attente`. Au
  service suivant, l'exécutant retente le renommage **avant tout tour d'agent** : réussi, la carte repart d'une branche
  neuve (K25) ; en échec, elle est refusée de nouveau pour un secret, sans qu'aucun agent ne tourne.
- Preuves (Windows, git 2.42) : `apps/poste/tests/test_execution.py`, sept tests de la section « relecture finale de
  P7 : secret dans l'historique » (blocage, limite de quota, interruption, commit fautif déjà dans l'historique,
  intégration, bundle, quarantaine impossible) ; l'ancien code remis en place les fait **tous rougir** (témoin).
  Linux, root, git 2.47.3 : CI « Image de l'exécutant ».
