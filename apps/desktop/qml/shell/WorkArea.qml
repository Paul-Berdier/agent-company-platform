// Zone de travail : elle affiche l'écran de la route courante.
//
// Une route « prévue » ne peut pas devenir courante — NavigationModel le refuse — donc
// cette zone n'a jamais à afficher une coquille vide. Le cas par défaut reste néanmoins
// traité : une route inconnue produit un état d'erreur explicite, pas un écran blanc.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Pages

Rectangle {
    id: work

    color: Palette.surfaceCanvas

    Loader {
        anchors.fill: parent
        sourceComponent: {
            switch (Navigation.currentRoute) {
            case "home":
                return homeComponent;
            case "diagnostics":
                return diagnosticsComponent;
            default:
                return unknownComponent;
            }
        }
    }

    Component {
        id: homeComponent
        HomePage {}
    }

    Component {
        id: diagnosticsComponent
        DiagnosticsPage {}
    }

    Component {
        id: unknownComponent
        EmptyState {
            title: qsTr("Écran indisponible")
            body: qsTr("La route « %1 » n'a pas d'écran dans cette version de la station.")
                .arg(Navigation.currentRoute)
            actionLabel: qsTr("Revenir à l'accueil")
            onActionTriggered: Commands.execute("navigation.home")
        }
    }
}
