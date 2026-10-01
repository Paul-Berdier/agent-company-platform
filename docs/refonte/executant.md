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
· § 12 sur Railway · § 13 non prouvé · § 14 écarts au cahier.

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
  terminée ; question et reprise ; secret en quarantaine ; revue refusée puis corrigée (§ 11).

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
remis aux propriétaires et modes attendus ; `/tmp/acp` en `root:acp-travail 1770` ; journal « [acp] commit déployé :
<RAILWAY_GIT_COMMIT_SHA ou inconnu> » ; puis `exec python3.12 -I /opt/acp/lancer.py servir --plateforme linux`.

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
  question, secret, revue refusée) au lieu des quatorze du cahier ; les autres sont couverts par les tests de la
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
