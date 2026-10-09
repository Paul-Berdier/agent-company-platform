# Agent Company Platform (ACP)

Espace de travail personnel d'agents IA, bâti autour de **Hermes Agent** (Nous Research, licence MIT) : c'est la
refonte « Hermes au centre ». Version **0.11.0** ; **1.0.0 est en préparation** (étape P9) : rien n'est encore
publié ni **déployé**. L'ancienne plateforme (API FastAPI, base SQLite et PostgreSQL, interface web Vite, CLI `acp`,
déploiement Railway multi-services) reste entière sous l'étiquette `archive/acp-0.10.0-avant-hermes`.

## Ce que c'est

Hermes, épinglé sur la release `v2026.9.24` (Hermes 0.21.5) par le condensat de son image, est le **seul serveur, le
seul orchestrateur et la seule source de vérité**. Le propriétaire lui confie des projets ; Hermes les découpe en
cartes, les fait exécuter par des agents de code (Codex CLI et Claude Code, avec les abonnements du propriétaire),
fait relire, pose ses questions et notifie. ACP n'a plus de backend propre ; il fournit les pièces autour de Hermes :

1. **L'image Railway dérivée de Hermes** ([`hermes/`](hermes)) : réglages gérés (managed scope), gardes de
   démarrage, persona française, skills vendorisées à des commits épinglés, greffon serveur `acp-poste` (projets,
   questions, routage des modèles, quotas, notifications, protocole des machines) et greffons d'interface. Sur
   Railway, l'agent ne doit avoir **aucun outil d'exécution** (ni terminal, ni fichiers, ni code) : trois couches
   de défense, chacune prouvée en local et en intégration continue ; un défaut intermittent de l'une d'elles reste
   **ouvert** (voir les limites ci-dessous). Détail : [`docs/refonte/image.md`](docs/refonte/image.md) § 5.
2. **L'identité** ([`identite/`](identite)) : Authelia 4.39.28 épinglé, un seul utilisateur, passkeys ; Hermes
   n'accepte que ce fournisseur OIDC auto-hébergé. Détail : [`docs/refonte/identite.md`](docs/refonte/identite.md).
3. **L'exécutant Railway** ([`executant/`](executant)) : un service séparé, sans port en écoute, qui réclame ses
   cartes à Hermes en HTTPS et lance Codex CLI 0.156.1 et Claude Code 2.1.283 sous un UID par agent, dans des
   worktrees de dépôts autorisés par une politique versionnée ; il committe en local, ne pousse jamais. Détail :
   [`docs/refonte/executant.md`](docs/refonte/executant.md).
4. **Le poste Windows**, facultatif ([`apps/poste`](apps/poste/README.md)) : le même client en mode Windows, sous
   un compte dédié et un Job Object ; il s'enrôle et publie l'inventaire de ses CLI. Détail :
   [`docs/refonte/poste.md`](docs/refonte/poste.md).
5. **La station de travail native** C++23 / Qt 6 / QML ([`apps/desktop`](apps/desktop/README.md)), sans WebView :
   connexion OIDC native, pages Accueil, Projets, Questions, Discussion, Poste, Quotas, Routage, Diagnostics,
   Sauvegarde (export chiffré de Hermes) ; elle ne parle qu'au Hermes authentifié. Détail :
   [`docs/refonte/desktop.md`](docs/refonte/desktop.md).
6. **Le navigateur et le téléphone** : le tableau de bord de Hermes habillé en français, avec les pages d'ACP
   (Accueil, Projets et sa file Questions, Poste, Discussion, Catalogue) sur la même URL. Détail :
   [`docs/refonte/interface.md`](docs/refonte/interface.md), [`docs/refonte/questions.md`](docs/refonte/questions.md).

L'infrastructure Railway (trois services, trois volumes) est déclarée en code dans
[`.railway/railway.ts`](.railway/railway.ts) et appliquée par le propriétaire seul.

## État réel (8 octobre 2026)

- Étapes P0 à P8 de la refonte fusionnées dans `refonte/hermes` ; P9 (exploitation, montée de version, publication)
  en cours. Historique : [`docs/refonte/historique.md`](docs/refonte/historique.md).
- **Prêt à déployer, non déployé** : aucun service ne tourne sur Railway ; tout ce qui ne se prouve que là
  (bord réel, sauvegardes réelles, coût, notifications réelles, sonde de l'exécutant) reste **non prouvé**.
- Prouvé en local et en intégration continue : les images et leurs gardes, les tests de contrat de Hermes et de
  l'identité, les parcours dans un navigateur, l'exécutant de bout en bout avec des CLI factices, la station Qt.
  Les tests de P9 (restauration des volumes, témoin d'une release antérieure de Hermes, montée de données) tournent
  en intégration continue seulement ; leurs preuves finales restent à relever. Relevés :
  [`docs/refonte/preuves-1.0.0.md`](docs/refonte/preuves-1.0.0.md) (en préparation).
- Binaires de la station : **non signés** (aucun certificat de signature de code) ; aucune installation éprouvée sur
  un Windows propre.

## Limites connues, en bref

- **Constat de sécurité ouvert, à instruire avant la publication** : une fois, après un redémarrage du conteneur
  sur un volume piégé, la session du tableau de bord a reçu les outils d'exécution (`terminal`, `write_file`…)
  posés par le `.env` du volume, alors que l'api_server les refusait : deuxième des trois couches vue en défaut,
  troisième (garde `pre_tool_call`) non mesurée pour cette session. Non reproduit, non expliqué, non corrigé
  ([preuves](docs/refonte/preuves-1.0.0.md) § 5).
- Rien n'est déployé : la [procédure Railway](docs/refonte/railway.md) § 12 liste ce qui ne se prouve que là.
- Tant que `trusted_proxies` reste vide, les cookies de Hermes n'ont pas l'attribut `Secure` ; un jeton de
  rafraîchissement rejoué laisse une erreur 503 jusqu'à la déconnexion ou l'effacement des cookies du site
  ([`docs/refonte/identite.md`](docs/refonte/identite.md) § 12).
- Pages natives de Hermes en partie en anglais (comptées, non traduites) ; rendu éprouvé dans Chromium seulement.
- Serveurs MCP côté exécutant reportés ; aucun dépôt réel encore confié à l'exécutant.

## Ce que 1.0.0 engagera

Le versionnage sémantique portera sur **nos** interfaces (D130 du [plan](docs/refonte/plan.md)) : contrat
`acp-poste/1` (routes `/api/plugins/acp-poste/v1/*`), protocole `acp-machine/1`, format `ACPB1` des exports
chiffrés, commandes `acp-poste`, formats de `poste.toml` et d'`executant.toml`, variables Railway documentées. Les
surfaces de Hermes (API du tableau de bord, JSON-RPC, SDK des greffons) suivent la version épinglée et restent hors
de cet engagement ; une rupture de nos interfaces appellera 2.0.0.

## Par où commencer

- **Propriétaire** : le [manuel d'exploitation](docs/exploitation.md) (calendrier, sauvegardes, restauration,
  montée de version, incidents), puis la [procédure Railway](docs/refonte/railway.md), § 4 pour le premier
  déploiement. Tout geste sur le compte Railway est le vôtre ; un agent prépare, teste et documente.
- **Agent ou développeur** : [`CLAUDE.md`](CLAUDE.md) (règles, doctrine, interdits), puis les
  [notes de reprise](docs/reprise-poste.md) (état courant, chaîne d'outils, pièges) et le
  [plan](docs/refonte/plan.md) (décisions, § 1).

## Vérifier

Sous Windows, depuis la racine d'un clone, avec un Python 3.12 de **python.org** (jamais celui du Microsoft
Store, que `scripts/setup.ps1` refuse, même s'il est le premier du `PATH`), sans Docker. `scripts/setup.ps1`
n'installe que pytest, pytest-asyncio, le contrat et le poste : la troisième ligne complète le venv par le verrou
haché de la CI, dont `cryptography`, sans lequel des dizaines de tests du poste sont en erreur.

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
./scripts/setup.ps1
.venv\Scripts\python.exe -m pip install --require-hashes --no-deps -r requirements/python-3.12.lock.txt
$env:PYTHONUTF8 = '1'
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\python.exe scripts/check_version.py
.venv\Scripts\python.exe scripts/check_engine_frozen.py
.venv\Scripts\python.exe scripts/balayer_secrets.py --arbre
npm ci ; npm run test:engine
npm ci --prefix apps/interface ; npm test --prefix apps/interface
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
```

Ce qui demande Docker passe par l'intégration continue (GitHub Actions, dépôt public) :

| Workflow | Ce qu'il prouve |
|---|---|
| `ci.yml` (CI) | suites du dépôt sous Linux et Windows, installeur du poste en simulation, greffons d'interface, moteur gelé, balayage des secrets |
| `image.yml` (Image Hermes) | images Hermes et identité, tests dans l'image, contrat depuis l'hôte, navigateur, IaC, répétition à blanc de la montée de Hermes ; job `restauration` ; jobs manuels `temoin` et `montee` |
| `executant.yml` (Image de l'exécutant) | image réelle, binaires vérifiés, sonde locale, suite du client en root |
| `desktop-ci.yml` (Desktop CI) | construction Release MSVC, tests Qt et empaquetage à blanc sur `windows-2022` |
| `desktop-release.yml` (Desktop Release) | à l'étiquette `v*` : brouillon de publication non signé ; jamais encore exécuté |

## Carte du dépôt

| Chemin | Rôle |
|---|---|
| `hermes/` | image Railway de Hermes : `image/` (Dockerfile, gardes, démarrage), `gere/` (managed scope), `persona/`, `theme/`, `catalogue/` et `skills/` (skills vendorisées et verrou), `plugins/` (greffon `acp-poste` et greffons d'interface), `contrat/` (version épinglée, OpenRPC), `tests/` (image, contrat, navigateur) |
| `identite/` | image du fournisseur d'identité (Authelia épinglé, garde root, configuration) |
| `executant/` | image de l'exécutant Railway : binaires vérifiés, politique versionnée, CLI factices de test |
| `.railway/` | infrastructure Railway en code (`railway.ts`, vérificateur, SDK isolé) |
| `apps/poste/` | client des machines (poste Windows et exécutant Linux) : protocole `acp-machine/1`, sondes, exécution des cartes |
| `apps/interface/` | sources TypeScript des greffons d'interface (bundles committés sous `hermes/plugins`) |
| `apps/desktop/` | station de travail Qt |
| `apps/web/public/assets/`, `plugins/`, `packages/pixel-office-engine/` | moteur Pixel Office et ses ressources, **gelés** sur l'étiquette d'archive |
| `design/tokens/` | jetons de design, source du thème du tableau de bord et du QML |
| `packaging/poste/`, `packaging/windows/` | installation du poste ; chaîne d'outils et installeur de la station |
| `requirements/` | verrous Python hachés (dépôt, poste) |
| `scripts/` | gardes (`check_version.py`, `check_engine_frozen.py`, `check_lock.py`, `balayer_secrets.py`), montée de Hermes (`monter_hermes.py`), construction et tests de la station, installation |
| `docs/` | manuel d'exploitation, notes de reprise, documentation de la refonte (`docs/refonte/`) et de la station |
| `.github/workflows/` | intégration continue (ci-dessus) |

## Règles

Doctrine, règles de commit et de publication : [`CLAUDE.md`](CLAUDE.md). En bref : aucun faux succès, échec
fermé, refus en français, aucune donnée inventée, aucun secret dans Git, Hermes et Authelia toujours épinglés par
condensat, aucun outil d'exécution pour l'agent sur Railway, moteur Pixel Office gelé. Journal des changements :
[`CHANGELOG.md`](CHANGELOG.md).
