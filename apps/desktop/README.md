# Station de travail native — `apps/desktop`

> **Hors service jusqu'à P8.** Le client C++23 / Qt 6.8.3 / QML est conservé intact,
> mais il parle encore l'ancienne API ACP (cookie `acp_session`, CSRF, routes
> `/health`, `/ready`, `/meta`…), retirée par la refonte « Hermes au centre »
> (`docs/refonte/plan.md`). Il compile et ses tests passent ; il n'a aucun serveur
> auquel se connecter. L'étape P8 le rebranche sur Hermes : flux natif RFC 8252,
> JSON-RPC sur `/api/ws`, façade versionnée du greffon `acp-poste`.

Règle de la refonte : le desktop ne parle qu'au Hermes authentifié du propriétaire
(tableau de bord, JSON-RPC, façade du greffon), jamais directement au poste Windows,
ni aux fichiers, à la base ou aux secrets du serveur. Aucun WebView ni WebEngine
n'est embarqué. Le seul transport externe distinct est la vérification GitHub des
mises à jour, à la demande.

## Ce que P8 garde et retire

Gardés (plan, section 5) : `src/api` (sans cookie ni CSRF), `src/events`
(`SseParser`, `EventStreamService` adapté au bearer, `Backoff`, `StreamScope`),
`src/storage` (coffre Windows, préférences sans secret), `SystemAppearance`,
`CommandRegistry`, `NavigationModel`, `Redaction`, `JsonListModel`, `UpdateService`,
`ArtifactDownload`, `HealthService` adapté, les quotas (`QuotasPage`,
`SubscriptionQuotasViewModel`, `QuotaGauge`), les contrôles, composants, coquille et
thème QML, et les tests génériques.

Retirés en P8 : `AuthManager`, `SessionCookieJar`, `CompatibilityService`, et les
ViewModels et pages métier Missions, Operations, Artifacts, Platform, Workspace,
Conversations, Studio, Run, Extensions et Projects. Le test `tst_api_journey` se
déclare ignoré (`QSKIP`) : son message cite encore `scripts/verify-desktop-journey.py`,
lanceur retiré avec l'API qu'il visait. CTest le compte « Passed » ; c'est un test
ignoré, pas une preuve.

## Construire et tester depuis la racine du dépôt

Installer MSVC 2022, Qt 6.8.3, CMake et Ninja selon
[la construction Windows](../../docs/desktop-build.md). Le préréglage Release
traite les avertissements comme des erreurs ; un succès Debug seul ne le remplace
pas.

```powershell
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
./scripts/setup-desktop.ps1
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
```

Les préréglages sont `windows-msvc-debug`, `windows-msvc-release`,
`ci-windows` et `linux-gcc-debug`. Depuis `apps/desktop`, l'équivalent direct
Release dans une console MSVC préparée est :

```powershell
cmake --preset windows-msvc-release
cmake --build --preset windows-msvc-release
ctest --preset windows-msvc-release
```

La preuve de référence est le workflow `Desktop CI` (windows-2022) : une
compilation sur un poste ne vaut que pour ce poste.

## Organisation et contrôles

- `src/api`, `auth`, `events` : transport, session et flux.
- `src/models`, `viewmodels` : modèles de listes et contrats métier.
- `src/services` : disponibilité, compatibilité, téléchargements, session et mises à jour.
- `src/storage` : coffre système et préférences non secrètes.
- `qml` : pages, contrôles, thème et coquille native.
- `tests` : Qt Test et Qt Quick Test.

Depuis la racine du dépôt :

```powershell
python apps/desktop/cmake/check_layout.py
python apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated --check
```

`check_layout.py` signale aujourd'hui 10 constats hérités de l'étiquette
`archive/acp-0.10.0-avant-hermes` (origines codées en dur dans `UpdateService` et
dans des tests, un chemin absolu littéral dans un test) ; ils ne sont pas traités en
P0, qui ne modifie pas le code du client.

Les jetons de `design/tokens` alimentent les singletons QML versionnés ; la cible
`acp_check_design_tokens` contrôle leur fraîcheur. Garder les fichiers en UTF-8/LF.
Documents : [construction](../../docs/desktop-build.md),
[architecture avant P8](../../docs/native-desktop-architecture.md),
[sécurité avant P8](../../docs/desktop-security.md),
[publication](../../docs/desktop-release-process.md),
[mises à jour](../../docs/desktop-update-process.md),
[reprise](../../docs/reprise-poste.md).
