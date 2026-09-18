# Station de travail native — `apps/desktop`

Client natif C++23 / Qt 6 / Qt Quick de l'Agent Company Platform. Il parle à l'API en
HTTPS et en SSE, et à rien d'autre : jamais à la base, jamais à `event-service`, jamais à
`provider-gateway`.

## Ce qui n'a pas été compilé

**Rien de ce répertoire n'a jamais été compilé ni exécuté.**

Le poste de rédaction ne dispose ni de Qt, ni de CMake, ni de Ninja, ni de MSVC, ni
d'aucun compilateur C++ (relevé du 18 septembre 2026, `docs/desktop-railway-audit.md`,
section 11.1). Aucune cible n'a été configurée, aucun test n'a été exécuté, aucune fenêtre
n'a été rendue. **La seule preuve de compilation recevable viendra d'un job d'intégration
continue Windows, qui n'existe pas encore.**

Ce qui a été vérifié localement, et cela seul :

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
