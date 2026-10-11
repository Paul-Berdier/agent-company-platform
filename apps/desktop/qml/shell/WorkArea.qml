// Zone de travail : l'écran de la route courante.
//
// Une route « prévue » ne peut pas devenir courante — NavigationModel le refuse — donc
// cette zone n'a jamais à afficher une coquille vide. Le cas par défaut reste néanmoins
// traité : une route inconnue produit un état d'erreur explicite, pas un écran blanc.
//
// Espace de travail (D167) : « projects » montre la mission ouverte (ou la liste et le
// formulaire de nouvelle mission) ; les pages techniques partagent UN écran Réglages, gardé
// en vie d'une section à l'autre (même composant pour toutes leurs routes).

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
            case "home": return homeComponent;
            case "projects": return missionComponent;
            case "questions": return questionsComponent;
            case "chat": return discussionComponent;
            case "settings":
            case "station":
            case "quotas":
            case "routing":
            case "backup":
            case "diagnostics": return reglagesComponent;
            default: return unknownComponent;
            }
        }
    }

    Component { id: homeComponent; HomePage {} }
    Component { id: missionComponent; MissionPage {} }
    Component { id: questionsComponent; QuestionsPage {} }
    Component { id: discussionComponent; DiscussionPage {} }
    Component { id: reglagesComponent; ReglagesPage {} }

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
