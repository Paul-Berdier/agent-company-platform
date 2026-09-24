# Station de travail native — `apps/desktop`

Client C++23 / Qt 6.8.3 / QML d'Agent Company Platform, **0.10.0 en préparation**.
Il utilise l'API métier pour les données ACP, jamais la base, le provider-gateway
ou les agents directement. Le seul transport externe distinct est la vérification
GitHub des mises à jour, à la demande. Aucun WebView/WebEngine n'est embarqué.

## Écrans et limites

Les écrans comprennent projets, conversations, missions, tentatives et Studio,
livrables, agents/workers/fournisseurs, MCP/compétences, approbations, alertes,
budgets, automatisations et quotas réels d'abonnement (propriétaire seulement,
voir [les quotas d'abonnement](../../docs/subscription-quotas.md)). Voir [la matrice de parité](../../docs/native-desktop-parity.md)
pour les opérations réellement proposées et les écarts au web/CLI.

Les réglages comprennent la mémorisation facultative de session dans le coffre
Windows. La vérification des mises à jour compare les versions stable/préversion,
présente les notes brutes et ouvre une publication GitHub officielle ; aucun
téléchargeur/installateur n'est intégré.

## Preuves

La fondation du 18 septembre a compilé en Debug/Release et passé **10 suites
natives sur 10**, dont les tests Qt Quick. Le lancement contre une API SQLite
jetable et l'empaquetage local sont des preuves historiques acquises.

Le 23 septembre, un nouveau parcours Qt contre **une vraie API locale** et
SQLite jetable a réussi : cookie/CSRF, création des organisations/espaces/projets,
conversation persistée avec fournisseur indisponible explicitement annoncé,
mission et tentative en file, remplacement du budget, création d'automatisation
en pause, téléchargement authentifié exact de **180 224 octets** avec SHA-256,
puis purge locale après déconnexion.

Le rapport du lanceur est `.test-tmp/desktop-journey-e9c4c89486b240f49017bb16aae70c47/result.json`
à la racine du worktree ; il annonce `passed`, `qt_executed=true` et code de
sortie 0. Le rapport `qt-journey.log` donne **3 réussis, 0 échec, 0 ignoré,
1 663 ms** (initialisation, parcours, nettoyage). Le lancement complet a pris
9,7 secondes. Cela ne prouve ni Hermes réel, ni Railway, ni les parcours
visuels de tous les écrans.

Le build Release et les **21 suites natives sur 21 en 54,82 s** passent. Les
**24 tests de session passent sans ignoré hors sandbox**, dont le vrai coffre
Windows. Les preuves de paquet, d'installation et du CI sont tenues dans
[le relevé daté](../../docs/desktop-validation-2026-09-23.md).

Restent Windows propre, signature, Railway réel, recette visuelle complète et
[26 constats Lot H](../../docs/lot-h-091-review-status.md). Cette version en
préparation n'est pas une V1 complète ni une publication finalisée.

## Construire depuis la racine du dépôt

Installer MSVC 2022, Qt 6.8.3, CMake et Ninja selon
[la construction Windows](../../docs/desktop-build.md). Le préréglage Release
traite les avertissements comme des erreurs.

```powershell
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
./scripts/setup-desktop.ps1
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
./scripts/dev-desktop.ps1 -Configuration Release
```

L'API doit être démarrée et le premier compte amorcé via API/web/CLI. Son URL
se saisit dans l'écran de connexion. HTTP n'est accepté que sur le bouclage avec
l'option explicite ; l'API locale utilise alors `ACP_SESSION_COOKIE_SECURE=0`.
Tout parcours de test doit pointer sur une base dédiée, jamais `./acp.db`.

Les préréglages sont `windows-msvc-debug`, `windows-msvc-release`,
`ci-windows` et `linux-gcc-debug`. Depuis `apps/desktop`, l'équivalent direct
Release dans une console MSVC préparée est :

```powershell
cmake --preset windows-msvc-release
cmake --build --preset windows-msvc-release
ctest --preset windows-msvc-release
```

## Organisation et contrôles

- `src/api`, `auth`, `events` : transport, session et flux.
- `src/models`, `viewmodels` : modèles de listes et contrats métier.
- `src/services` : disponibilité, compatibilité, téléchargements, session et mises à jour.
- `src/storage` : coffre système et préférences non secrètes.
- `qml` : pages, contrôles, thème et coquille native.
- `tests` : Qt Test, Qt Quick Test, transport HTTP local et parcours API réel.

Depuis la racine du dépôt :

```powershell
python apps/desktop/cmake/check_layout.py
python apps/desktop/cmake/generate_design_tokens.py --check
```

Les jetons de `design/tokens` alimentent les singletons QML versionnés ; la cible
`acp_check_design_tokens` contrôle leur fraîcheur. Garder les fichiers en UTF-8/LF.
Architecture et sécurité : [architecture](../../docs/native-desktop-architecture.md),
[sécurité](../../docs/desktop-security.md), [reprise](../../docs/reprise-poste.md).
