# Pièges QML mesurés sur Qt 6.8.3

Essais faits le 11 octobre 2026 dans la session cloud Linux du chantier « atelier », avec le Qt 6.8.3 installé hors
dépôt (`/opt/acp-outils/qt683`, voir [atelier-outillage.md](../../../../docs/refonte/atelier-outillage.md) § 2.2),
plateforme `offscreen`. Fichiers d'essai écrits dans le dossier de brouillon de la session, jamais dans le dépôt.
Outils : `qml` et `qmllint` de `/opt/acp-outils/qt683/lib/qt6/bin`.

## 1. Propriété `on` suivie d'une majuscule

Origine de la règle : skill `qt-qml` des Qt Agentic Tools, lue pendant le chantier
([atelier-outillage.md](../../../../docs/refonte/atelier-outillage.md) § 6.1).

| Essai | Résultat mesuré |
|---|---|
| `property bool onLigne: true` seule dans un `Item`, lue par `Component.onCompleted` | chargé ; valeur `true` |
| même propriété affectée par l'utilisateur du composant (`onLigne: false`), sans propriété `ligne` | chargé ; valeur `false` |
| composant `QtObject { property color accent: … ; property color onAccent: … }` | **refusé au chargement** : « Cannot assign a value to a signal (expecting a script to be run) », puis « Type Jetons unavailable » |
| `qmllint` sur ce dernier cas | code 0, aucun avertissement |

Conclusion : le nom passe tant qu'aucune propriété de base homonyme n'existe, puis casse sans que `qmllint` le
signale. Règle retenue : aucun nom `on` suivi d'une majuscule. Le générateur de jetons préfixe déjà
(`text.onAccent` donne `textOnAccent`, `apps/desktop/qml/theme/generated/Colors.qml:36`).

## 2. Ancrages et tailles dans un layout

Essai : un `Rectangle` avec `anchors.left: parent.left; width: 50; height: 20`, enfant d'un `ColumnLayout`.

| Outil | Résultat mesuré |
|---|---|
| `qml` (exécution) | avertissement du moteur : « Detected anchors on an item that is managed by a layout. This is undefined behavior; use Layout.alignment instead. » |
| `qmllint` | deux avertissements `[Quick.layout-positioning]` : ancrage, puis largeur (« use implicitWidth or Layout.preferredWidth instead ») |

Dans la station, `tst_pages_bureau` recueille les avertissements du moteur (`QQmlEngine::warnings`,
`apps/desktop/tests/cpp/tst_pages_bureau.cpp:236-238`) et fait échouer l'étape qui en reçoit un
(`tst_pages_bureau.cpp:267-269`).

Règle retenue : dans un `RowLayout`, `ColumnLayout` ou `GridLayout`, un enfant se dimensionne par
`Layout.preferredWidth`, `Layout.fillWidth`, `Layout.minimumHeight`, etc., et s'aligne par `Layout.alignment`.

## 3. Portée de `qmllint` sur la station

Essai : `qmllint -I build/linux-gcc-debug qml/pixel/SpritePixel.qml`, depuis `apps/desktop`, après une construction
Linux.

Résultat mesuré : « Failed to import Acp.Design. Are your import paths set up properly? », plus un avertissement sur
le singleton `PlanchesPixel` ; code 0.

Raison probable, non vérifiée plus avant : les dossiers des modules ne suivent pas le chemin de leur URI
(`qml/theme/generated` porte `Acp.Design`, `qml/shell` porte `Acp.Station`). `qmllint` reste utile sur un extrait
isolé ; il ne prouve rien sur un fichier de la station. Aucun workflow ne le lance.

## 4. Ce qui n'a pas été mesuré

- Le comportement sous Windows et MSVC : seule la Desktop CI le dit.
- La cadence d'image d'une animation : profilage au lot F
  ([atelier.md](../../../../docs/refonte/atelier.md), section 6).
