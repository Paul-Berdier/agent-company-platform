# Agent Company Platform (ACP)

Espace de travail personnel d'agents IA, en pleine **refonte « Hermes au centre »**
(version **0.11.0**, branche `refonte/hermes`). Le plan complet et les décisions du
propriétaire sont dans [`docs/refonte/plan.md`](docs/refonte/plan.md) ; l'état du
chantier, étape par étape, dans [`docs/reprise-poste.md`](docs/reprise-poste.md).

## L'idée

Hermes Agent (Nous Research, licence MIT), épinglé sur une release par condensat
d'image (image `nousresearch/hermes-agent`, tag `v2026.9.24` visé par le plan) et
déployé sur Railway, devient le seul serveur, le seul
orchestrateur et la seule source de vérité. ACP n'a plus de backend propre : pas
d'API, pas de base, pas de bus d'événements, pas de CLI. Il reste quatre pièces.

1. **Une image Railway dérivée de l'image officielle de Hermes** : réglages gérés,
   greffons `acp-interface` (identité, pages, discussion mobile) et `acp-poste`
   (délégation, jeton machine, quotas), skills vendorisées, persona française.
   *À construire à partir de P1.*
2. **Le poste Windows** ([`apps/poste`](apps/poste/README.md)) : il exécute Codex CLI
   et Claude Code avec les connexions du propriétaire, sous Job Object, et réclame son
   travail en HTTPS sortant sans écouter aucun port. *Réduit en P0 ; la voie de
   délégation arrive en P5.*
3. **Le client desktop natif** C++23 / Qt 6 / QML ([`apps/desktop`](apps/desktop/README.md)),
   sans WebView : il ne parle qu'au Hermes authentifié du propriétaire. *Conservé
   intact, hors service jusqu'à P8 : il parle encore l'ancienne API ACP.*
4. **Le navigateur et le téléphone** : le tableau de bord de Hermes habillé, plus les
   pages du greffon, sur la même URL. *À partir de P3.*

L'ancienne plateforme (API FastAPI, base SQLite/PostgreSQL, interface web Vite, CLI
`acp`, passerelle de fournisseurs, déploiement Railway multi-services) reste
consultable sous l'étiquette `archive/acp-0.10.0-avant-hermes`.

## Contenu du dépôt

| Chemin | Rôle |
|---|---|
| `apps/poste/` | poste Windows : exécuteurs Codex et Claude Code, runner sous Job Object, DPAPI, sondes de quotas, ligne d'état Claude Code |
| `hermes/plugins/acp-poste/contrat/` | contrat Python partagé par le poste et le futur greffon `acp-poste` |
| `apps/desktop/` | client Qt natif (hors service jusqu'à P8) |
| `packages/pixel-office-engine/` | moteur Pixel Office, **gelé** sur l'étiquette d'archive, avec `apps/web/public/assets/` et `plugins/` |
| `design/tokens/` | jetons de design, source du thème QML |
| `packaging/windows/` | chaîne d'outils et installeur du desktop |
| `scripts/` | construction et tests du desktop, gardes (`check_engine_frozen.py`, `check_version.py`, `check_lock.py`), installation |
| `docs/` | plan de la refonte, reprise, guides desktop, documentation du moteur |

## Vérifier

Sous Windows, avec un Python 3.12 de python.org (jamais celui du Microsoft Store) :

```powershell
./scripts/setup.ps1
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/check_engine_frozen.py
npm run test:engine
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
```

L'intégration continue a trois volets : le moteur (gel et tests npm), le poste
(pytest sous Linux et Windows) et le desktop (`Desktop CI`, windows-2022).

## Règles

Doctrine, règles de commit et de publication : [`CLAUDE.md`](CLAUDE.md). En bref :
aucun faux succès, échec fermé, refus en français, aucune donnée inventée, aucun
secret hors du coffre Windows ou de DPAPI, Hermes toujours épinglé, moteur gelé.

Binaires du desktop : **non signés** tant qu'aucun certificat de signature de code
n'est configuré.
