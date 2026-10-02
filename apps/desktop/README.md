# Station de travail native — `apps/desktop`

Client C++23 / Qt 6.8.3 / QML du propriétaire d'ACP, rebranché sur **Hermes** par l'étape
P8 de la refonte « Hermes au centre » : connexion native RFC 8252 par le navigateur du
système (fournisseur `self-hosted`), porteur sur les API du tableau de bord, JSON-RPC sur
`/api/ws`, façade versionnée du greffon `acp-poste`. Pages : Accueil, Projets, Questions,
Discussion, Poste, Quotas, Routage, Diagnostics, Sauvegarde, Réglages.

Règle de la refonte : la station ne parle qu'au Hermes authentifié du propriétaire, par ses
API, jamais au fournisseur d'identité, au poste Windows, ni aux fichiers, à la base ou aux
secrets du serveur. Aucun WebView ni WebEngine n'est embarqué. Le seul transport externe
distinct est la vérification GitHub des mises à jour, à la demande.

L'ancien client (cookie `acp_session`, ancienne API ACP, pages Missions, Operations,
Artifacts, Platform, Workspace, Conversations, Studio…) a été retiré en P8 ; il reste
consultable sous l'étiquette `archive/acp-0.10.0-avant-hermes`.

## Construire et tester depuis la racine du dépôt

Installer MSVC 2022, Qt 6.8.3 **avec le module `qtwebsockets`**, CMake et Ninja selon
[la construction Windows](../../docs/desktop-build.md). Le préréglage Release traite les
avertissements comme des erreurs ; un succès Debug seul ne le remplace pas.

```powershell
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
./scripts/setup-desktop.ps1
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
```

Les préréglages sont `windows-msvc-debug`, `windows-msvc-release`, `ci-windows` et
`linux-gcc-debug`. La preuve de référence est le workflow `Desktop CI` (windows-2022) :
une compilation sur un poste ne vaut que pour ce poste. Le bout en bout contre la pile de
test locale (Authelia, Hermes de test) se lance par `scripts/e2e-desktop-windows.ps1`
(jamais en CI ; [construction](../../docs/desktop-build.md), § 12).

## Organisation

- `src/auth` : flux natif RFC 8252, jetons, session, rotation.
- `src/api` : transport en porteur, erreurs, client du greffon `acp-poste`.
- `src/gateway` : canal et passerelle JSON-RPC, demandes de l'agent.
- `src/events` : sondages, veille du kanban, état du temps réel.
- `src/services` : compatibilité, santé, lecture en flux, mises à jour.
- `src/storage` : coffre Windows, préférences sans secret, sauvegarde chiffrée.
- `src/viewmodels`, `src/models` : une `PageViewModel` par page, modèles de listes.
- `qml` : pages, composants, contrôles, thème et coquille native.
- `tests` : Qt Test (`tests/cpp`, banc `support/FauxHermes`), Qt Quick Test
  (`tests/qml`), documents de référence (`tests/fixtures/hermes`), pilote du bout en
  bout (`tests/e2e`, jamais déclaré à CTest).

## Contrôles

Depuis la racine du dépôt :

```powershell
python apps/desktop/cmake/check_layout.py
python apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated --check
```

`check_layout.py` (hors CI) signale aujourd'hui **13 constats**, tous connus : chemins
côté serveur ou conteneur (`/opt/…`) et conversion d'un chemin Windows dans des tests,
l'origine GitHub d'`UpdateService` (héritée) et les URL des tests de mise à jour et du flux
natif. Les noms de la pile de test (`*.test`, domaine réservé comme `.invalid`) ne sont
plus signalés.

Les jetons de `design/tokens` alimentent les singletons QML versionnés ; la cible
`acp_check_design_tokens` contrôle leur fraîcheur. Garder les fichiers en UTF-8/LF.

Documents : [construction](../../docs/desktop-build.md),
[architecture](../../docs/native-desktop-architecture.md),
[sécurité](../../docs/desktop-security.md),
[étape P8](../../docs/refonte/desktop.md),
[publication](../../docs/desktop-release-process.md),
[mises à jour](../../docs/desktop-update-process.md),
[reprise](../../docs/reprise-poste.md).
