# Suites à lancer selon les chemins touchés

Relevé du 11 octobre 2026 dans l'arbre de travail du chantier « atelier », depuis `pytest.ini` et les workflows ;
le chantier modifie lui-même `ci.yml` et `desktop-ci.yml`. Une étape de workflow est citée par son nom et sa ligne :
le nom fait foi si la ligne bouge. Commandes depuis la racine du dépôt, sous Linux, avec le Python 3.12 de la CI
(`.github/workflows/ci.yml:134`). Sous Windows : [docs/reprise-poste.md](../../../../docs/reprise-poste.md) § 4.

## Table

| Chemins touchés | Commandes locales | Ce que la CI lance |
|---|---|---|
| Tout changement | `git diff --check` ; `python3.12 scripts/balayer_secrets.py --arbre` ; pytest de `scripts/tests` | « Vérifier les blancs des commits » et « Balayer les secrets » (`ci.yml:53-72`) |
| `apps/poste/**` | pytest de `apps/poste/tests` | « Exécuter les tests Python » (`ci.yml:158-161`, Ubuntu et Windows) ; en root dans l'image d'essais (`.github/workflows/executant.yml:134-137`) |
| `hermes/plugins/acp-poste/contrat/**` | pytest de `hermes/plugins/acp-poste/contrat/tests` | idem ; et `image.yml`, puisque le chemin est sous `hermes/**` |
| `executant/**` | pytest de `executant/tests` ; `test_image.py` pilote Docker (`executant/tests/test_image.py:1`) | `executant.yml:106-107` |
| `hermes/**` hors contrat | sans Docker, seuls les tests statiques de `scripts/tests` (ligne « Tout changement ») ; `hermes/tests/image` ne tourne que dans l'image de test (`hermes/tests/image/conftest.py:1-10`), `hermes/tests/contrat` pilote Docker (`hermes/tests/contrat/conftest.py:1`) | `image.yml:315-344`, déclenché par `hermes/**` (`image.yml:134-135`) |
| `apps/interface/**` | `npm ci --ignore-scripts --prefix apps/interface` ; `npm test --prefix apps/interface` ; `npm run build --prefix apps/interface`, puis `git diff --exit-code -- hermes/plugins` | job « interface » (`ci.yml:97-113`) ; les bundles sont committés |
| `design/tokens/**` | `python3.12 apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated --check` ; `python3.12 scripts/generer_themes.py --check` ; `python3.12 scripts/generer_assets_pixel.py --check` (des palettes pixel lisent des jetons) ; pytest de `scripts/tests/test_generer_themes.py` ; ctest de la station | « Vérifier le thème généré et le QML du desktop » (`ci.yml:139-140`) ; Desktop CI (`desktop-ci.yml:25`, `:44`) ; `image.yml` si `hermes/theme/acp.yaml` change |
| `design/pixel/**`, `scripts/generer_assets_pixel.py` | `python3.12 scripts/generer_assets_pixel.py --check` ; pytest de `scripts/tests/test_generer_assets_pixel.py` ; ctest de la station (`tst_qml_shell` lit `tst_pixel.qml`) | « Vérifier les assets pixel générés » (`ci.yml:141-143`) ; Desktop CI (`desktop-ci.yml:26-27`, `:45-46`) |
| `apps/desktop/**` | construction et ctest Linux (ci-dessous) ; `python3.12 apps/desktop/cmake/check_layout.py` | Desktop CI : « Configurer et compiler » et « Exécuter les tests Qt Test et Qt Quick Test » (`desktop-ci.yml:157-161`), « Empaqueter à blanc » (`:166-167`) |
| `VERSION` et copies | `python3.12 scripts/check_version.py` ; pytest de `scripts/tests/test_version_complete.py` | « Vérifier les versions publiables » (`ci.yml:137-138`) |
| `docs/refonte/*.md`, `docs/reprise-poste.md`, `CHANGELOG.md`, `docs/exploitation.md` | pytest de `scripts/tests/test_decisions_documentees.py` | « Exécuter les tests Python » (`ci.yml:158-161`) |
| `packages/pixel-office-engine`, `apps/web/public/assets`, `plugins` | **ne pas toucher** ; `python3.12 scripts/check_engine_frozen.py` ; `npm ci` puis `npm run test:engine` | job « moteur » (`ci.yml:48-52`, `:79-80`) |
| `requirements/**`, dépendances d'un `pyproject.toml` | `python3.12 scripts/check_lock.py` (verrou haché et contraintes du poste : `scripts/check_lock.py:1-8`) | « Vérifier les déclarations et le verrou Python » (`ci.yml:156-157`) |
| `hermes/catalogue/**` | `python3.12 scripts/verifier_catalogue.py` | « Vérifier le catalogue de skills et de MCP » (`ci.yml:144-146`) |

## Python

`pytest.ini:9-13` collecte quatre dossiers : `apps/poste/tests`, `hermes/plugins/acp-poste/contrat/tests`,
`scripts/tests` et `executant/tests`. `pytest.ini:6-8` pose le `pythonpath` : l'installation éditable de la CI n'est
pas nécessaire en local.

```sh
python3.12 -m venv <hors-du-dépôt>/venv
<hors-du-dépôt>/venv/bin/python -m pip install --require-hashes --no-deps -r requirements/python-3.12.lock.txt
PYTHONUTF8=1 <hors-du-dépôt>/venv/bin/python -m pytest -q -rs -p no:cacheprovider
```

Le verrou haché est celui de la CI (`ci.yml:151`). Un venv sans `cryptography` produit des erreurs d'environnement
dans les tests du poste (`docs/reprise-poste.md`, § 5, « Python et tests »).

## Station Qt sous Linux

Préréglage secondaire `linux-gcc-debug` (`apps/desktop/CMakePresets.json:75-87`, test : `:144`). Qt se trouve par
`QT_ROOT_DIR` (`CMakePresets.json:19-25`). Installation reproductible hors dépôt :
[scripts/installer_qt_linux.py](../../../../scripts/installer_qt_linux.py), décrite dans
[docs/refonte/atelier-outillage.md](../../../../docs/refonte/atelier-outillage.md) § 2.3.

```sh
export QT_ROOT_DIR=/opt/acp-outils/qt683          # préfixe de la session cloud du 11 octobre 2026
export QT_QPA_PLATFORM=offscreen
export QT_QPA_FONTDIR=/opt/acp-outils/qt683/fonts
cd apps/desktop
cmake --preset linux-gcc-debug
cmake --build --preset linux-gcc-debug
ctest --preset linux-gcc-debug
```

- Chaque test C++ et `tst_qml_shell` reçoivent déjà `QT_QPA_PLATFORM=offscreen` (`apps/desktop/tests/CMakeLists.txt:34`,
  `:141`).
- La cible `acp_check_design_tokens` n'a pas le mot-clé `ALL` (`apps/desktop/CMakeLists.txt:94-101`) : la construire
  à part (`cmake --build --preset linux-gcc-debug --target acp_check_design_tokens`). En CI, la fraîcheur du QML
  généré vient de `generer_themes.py --check` (`ci.yml:139-140`).
- `check_layout.py` est hors CI. Il signale 13 constats connus (`apps/desktop/README.md:60-64`) ; mesuré à 13 le
  11 octobre 2026, avec le code de sortie 1 que rend tout constat. Viser 13 ou moins, jamais plus.
- Lire les totaux de Qt Test, pas seulement le compte CTest : un `QSKIP` compte « Passed »
  (`docs/desktop-build.md:163`).

## Ce qui ne se prouve qu'ailleurs

- Windows : DPAPI, coffre, compilation MSVC et empaquetage à blanc, par la Desktop CI sur `windows-2022`
  (`desktop-ci.yml:74`). L'icône vue dans l'Explorateur et l'installeur installé ne sont prouvés nulle part : c'est le
  lot F, au backlog ([docs/refonte/atelier.md](../../../../docs/refonte/atelier.md), section 6).
- Docker : tests d'image, de contrat et de bout en bout (`image.yml`, `executant.yml`) ; en local seulement sous D160.
- Les bouts en bout locaux `scripts/e2e-desktop-windows.ps1` et `scripts/e2e-poste-windows.ps1` ne sont appelés par
  aucun workflow (`docs/reprise-poste.md`, § 4).
