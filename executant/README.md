# Exécutant Railway d'ACP (`executant/`)

Image du service Railway **`executant`** (refonte « Hermes au centre », étape P6) : le client `apps/poste` en mode
Linux, qui réclame les cartes de Hermes en `acp-machine/1` et y lance **Codex CLI 0.156.1** et **Claude Code
2.1.283**, chacun sous son UID. Hermes garde son conteneur sans terminal ni outil d'exécution. Conception :
`docs/refonte/executant.md` ; gestes du propriétaire : `docs/refonte/railway.md`.

## Contenu

| Fichier | Rôle |
|---|---|
| `Dockerfile` | image amd64 multi-étapes ; base `python:3.12-slim-trixie` épinglée par condensat ; cible finale = celle de Railway |
| `Dockerfile.dockerignore` | liste blanche du contexte (racine du dépôt) |
| `binaires.toml` | versions, adresses, SHA-256, taille, clé de signature ; versions apt et condensat de la base |
| `cles/claude-code.asc` | clé publique de publication de Claude Code (empreinte `31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE`) |
| `bin/verifier-binaires` | téléchargement et contrôle au build (tailles, SHA-256, signature GPG du manifeste) ; `--controler` rejouable dans le conteneur |
| `bin/acp-entree-executant` | entrée root sous `tini` : refus hors tini ou sans volume, dossiers du volume, puis superviseur |
| `bin/acp-poste` | `/usr/local/bin/acp-poste` : `python3.12 -I /opt/acp/lancer.py` (gestes `railway ssh`, sonde R0) |
| `bin/acp-askpass` | `GIT_ASKPASS` du seul `git fetch` du superviseur (jeton GitHub de lecture) |
| `politique/executant.toml` | politique versionnée, `/etc/acp/executant.toml` (0444) ; refusée tant que l'origine vaut le gabarit |
| `claude-settings.json` | `/etc/acp/claude-settings.json` : modèles admis et lectures interdites (ceinture en plus de `--restricted`) |
| `gitconfig` | `/etc/gitconfig` : crochets coupés, `https` seul, `safe.directory` des clones et des worktrees |
| `factice/` | **tests seulement** (cible `factice`) : faux Codex et faux Claude pilotés par scénario |
| `tests/` | tests statiques, tests de l'image construite (Docker), image d'essais (suite `apps/poste` en root) |

## Construire et tester en local

```sh
docker build -f executant/Dockerfile -t acp-executant:local .                       # télécharge et vérifie
docker build -f executant/Dockerfile --target factice -t acp-executant:factice .   # sans binaires réels
docker build -f executant/tests/Dockerfile --build-arg IMAGE_EXECUTANT=acp-executant:local \
    -t acp-executant-essais:local .
ACP_IMAGE_EXECUTANT=acp-executant:local ACP_IMAGE_EXECUTANT_FACTICE=acp-executant:factice \
    python -m pytest executant/tests                                              # depuis la racine du dépôt
docker run --rm --entrypoint /usr/bin/tini acp-executant-essais:local -- \
    python3.12 -m pytest -q -rs apps/poste/tests hermes/plugins/acp-poste/contrat/tests
```

Répétition locale de la sonde R0 (même commande que la Start Command du projet jetable `acp-sonde`) :

```sh
docker run --rm --entrypoint /usr/local/bin/acp-poste acp-executant:local sonde-plateforme --json
```

Sous le seccomp par défaut de Docker, elle rend le **régime B** (bubblewrap refusé) ; avec
`--security-opt seccomp=unconfined`, le régime A. **Aucun de ces relevés ne vaut pour Railway** : seule la sonde
lancée sur Railway tranche (`docs/refonte/executant.md`, R0).

## Identités dans le conteneur

| Compte | UID/GID | Possède | Rôle |
|---|---|---|---|
| `root` | 0 | `/donnees/acp` (secrets 0600, état, file de sortie, journal, bundles), clones nus | `tini`, entrée, superviseur, `git` |
| `acp-codex` | 10001, groupe 10100 | `/donnees/codex` (`auth.json`) | Codex CLI |
| `acp-claude` | 10002, groupe 10100 | `/donnees/claude` | Claude Code (jeton passé à ce seul processus) |
| `acp-verif` | 10003, groupe 10100 | rien | commandes de vérification, sans identifiant |

## Limites (dites, pas parées)

- **Signature cosign de Codex non vérifiée** : l'identité du certificat n'est pas établie ; le SHA-256 de l'archive,
  relevé dans l'API GitHub, est obligatoire. Le journal de build le dit.
- **Versions apt fixées** : une version intermédiaire de Debian qui retire un paquet du miroir fait échouer le build ;
  la montée de version passe par une PR (`binaires.toml` et `Dockerfile` ensemble).
- **Régime B probable sur Railway** : sans espaces de noms utilisateur, la voie Codex est fermée sur l'exécutant
  (décision D79 du dépôt) et la séparation par UID est la seule barrière entre agents et identifiants.
- La cible `factice` ne prouve que la plomberie, jamais la qualité d'un modèle.
