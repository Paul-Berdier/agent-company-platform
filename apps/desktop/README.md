# Station de travail native — `apps/desktop`

Client natif C++23 / Qt 6 / Qt Quick de l'Agent Company Platform. Il parle à l'API en
HTTPS et en SSE, et à rien d'autre : jamais à la base, jamais à `event-service`, jamais à
`provider-gateway`.

## Ce qui est prouvé, et ce qui ne l'est pas

Relevé du 18 septembre 2026, sur poste Windows 10, MSVC 14.44, Qt 6.8.3, préréglage
`windows-msvc-debug` :

- la compilation passe sans erreur ; les dix suites natives passent (`ctest`), dont
  59 tests Qt Quick Test ;
- l'application a été lancée contre une API locale réelle (`uvicorn acp_api.main:app`,
  base SQLite jetable) : écran de connexion, test de lien, compatibilité par `GET /meta`,
  ouverture de session, coquille, diagnostics avec les contrôles de `/ready`. Le
  parcours a été piloté par UI Automation, donc aussi sans souris ;
- cette première confrontation a révélé quatre écarts de contrat entre le client et
  l'API (`/meta`, corps de connexion, rôle de session, `/ready`) et un aiguillage qui
  rendait la connexion inatteignable. Ils sont corrigés, et les documents d'API lus par
  les tests natifs (`tests/fixtures/`) sont gardés alignés sur l'API réelle par
  `apps/api/tests/test_desktop_contract_fixtures.py`.

Ce qui n'est **pas** prouvé :

- la compilation Release, l'empaquetage et l'installeur ne l'ont été qu'en intégration
  continue, quand elle passe (`.github/workflows/desktop-ci.yml`) ;
- la session n'est pas persistée : au redémarrage, il faut se reconnecter ;
- le coffre Windows (`WindowsCredentialVault`) compile mais n'est exercé par aucun test,
  et la station ne lui confie aucun secret aujourd'hui ;
- aucun écran métier (missions, runs, conversations…) n'est livré.

Vérifications sans chaîne d'outils native :

- la cohérence des chemins, des noms de fichiers et des URI de modules QML entre CMake,
  les sources C++ et les fichiers QML — `python apps/desktop/cmake/check_layout.py` ;
- la validité JSON des jetons de design et la fraîcheur de leur projection QML —
  `python apps/desktop/cmake/generate_design_tokens.py --check` ;
- l'absence de secret en clair, de chemin absolu et d'origine réseau codée en dur ;
- les fins de ligne LF.

## Construire (sur un poste réellement équipé)

```sh
# Qt est localisé par une variable d'environnement, jamais par un chemin codé en dur.
export QT_ROOT_DIR=/chemin/vers/Qt/6.8.x/msvc2022_64      # ou set QT_ROOT_DIR=... sous Windows

cmake --preset windows-msvc-release
cmake --build --preset windows-msvc-release
ctest --preset ci-windows
```

Préréglages disponibles : `windows-msvc-debug`, `windows-msvc-release`, `ci-windows`,
`linux-gcc-debug`.

## Jetons de design

Les couleurs, tailles, rayons et durées ne sont **jamais** recopiés à la main dans un
fichier QML. Ils sont engendrés depuis `design/tokens/*.json` :

```sh
python apps/desktop/cmake/generate_design_tokens.py \
    --tokens design/tokens --out apps/desktop/qml/theme/generated
```

La sortie est **versionnée**, pour qu'un poste sans Python puisse configurer le projet.
La cible CMake `acp_check_design_tokens` échoue si elle est périmée.

## Organisation

```
apps/desktop/
├── CMakeLists.txt          cibles, modules Qt retenus, options
├── CMakePresets.json       préréglages ; Qt vient de QT_ROOT_DIR ou Qt6_DIR
├── cmake/                  fonctions CMake, générateur de jetons, vérificateur
├── src/
│   ├── api/                transport, erreurs typées, curseurs forts, pot de cookies
│   ├── app/                assemblage, énumérations exposées à QML
│   ├── auth/               machine à états de session
│   ├── commands/           registre de commandes
│   ├── diagnostics/        expurgation des secrets
│   ├── events/             analyseur SSE, recul progressif, multiplexeur de flux
│   ├── navigation/         destinations et leur état de livraison
│   ├── services/           santé, disponibilité, compatibilité
│   ├── storage/            coffre de secrets, préférences non secrètes
│   ├── system/             thème et mouvement du système
│   └── viewmodels/         ce que QML a le droit de voir
├── qml/                    un module par répertoire, un URI par module
├── resources/              vides, et chaque README dit pourquoi
└── tests/                  Qt Test et Qt Quick Test, pour l'intégration continue
```

L'architecture, les modules Qt retenus et leur justification, le modèle de threads, la
sécurité et les sources officielles consultées sont décrits dans
[`docs/native-desktop-architecture.md`](../../docs/native-desktop-architecture.md).
