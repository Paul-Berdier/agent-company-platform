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

    color: Colors.surfaceCanvas

    Loader {
        anchors.fill: parent
        sourceComponent: {
            switch (Navigation.currentRoute) {
            case "home":
                return homeComponent;
            case "diagnostics":
                return diagnosticsComponent;
            case "projects": return projectsComponent;
            case "conversations": return conversationsComponent;
            case "missions": return missionsComponent;
            case "library": return artifactsComponent;
            case "platform": return platformComponent;
            case "extensions": return extensionsComponent;
            case "approvals": return operationsComponent;
            case "settings": return settingsComponent;
            case "studio": return studioComponent;
            case "quotas": return quotasComponent;
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

    Component { id: projectsComponent; ProjectsPage {} }
    Component { id: conversationsComponent; ConversationsPage {} }
    Component { id: missionsComponent; MissionsPage {} }
    Component { id: artifactsComponent; ArtifactsPage {} }
    Component { id: platformComponent; PlatformPage {} }
    Component { id: extensionsComponent; ExtensionsPage {} }
    Component { id: operationsComponent; OperationsPage {} }
    Component { id: settingsComponent; SettingsPage {} }
    Component { id: studioComponent; StudioPage {} }
    Component { id: quotasComponent; QuotasPage {} }

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
