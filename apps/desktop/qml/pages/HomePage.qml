// Accueil : l'état réel du lien, de la session et des flux. Rien d'autre.
//
// Cette fondation ne consomme aucune route métier : il n'y a donc ni compteur de
// missions, ni file d'approbations, ni graphique. Les afficher vides ou à zéro serait
// exactement l'invention que la doctrine interdit. L'écran dit ce qui viendra, et où.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space8
        spacing: Space.space8

        Text {
            Layout.fillWidth: true
            text: qsTr("Accueil")
            color: Colors.textPrimary
            font.family: Type.pageTitle.family
            font.pixelSize: Type.pageTitle.pixelSize
            font.weight: Type.pageTitle.weight
            font.letterSpacing: Type.pageTitle.letterSpacing
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: statusColumn.implicitHeight + Space.space6 * 2
            color: Colors.surfacePanel
            radius: Radius.radiusMd
            border.width: Space.layoutBorderWidth
            border.color: Colors.borderDefault

            ColumnLayout {
                id: statusColumn
                anchors.fill: parent
                anchors.margins: Space.space6
                spacing: Space.space5

                SectionHeader {
                    Layout.fillWidth: true
                    title: qsTr("État de la liaison")
                    subtitle: qsTr("Chaque valeur est mesurée ; « Inconnu » signifie qu'aucune "
                                   + "mesure n'a encore eu lieu.")
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Space.space5

                    StatusChip {
                        statusKey: Health.linkStatus === LinkStatus.Online ? "succeeded"
                            : Health.linkStatus === LinkStatus.Degraded ? "degraded"
                            : Health.linkStatus === LinkStatus.Offline ? "offline"
                            : Health.linkStatus === LinkStatus.Probing ? "running"
                            : "unknown"
                        label: Health.linkStatusLabel
                        detail: Health.detail
                    }

                    StatusChip {
                        statusKey: {
                            switch (Compatibility.state) {
                            case CompatibilityStatus.Compatible: return "succeeded";
                            case CompatibilityStatus.ClientTooOld:
                            case CompatibilityStatus.ServerTooOld: return "failed";
                            case CompatibilityStatus.FeatureUnavailable: return "notConfigured";
                            case CompatibilityStatus.Unreachable: return "offline";
                            case CompatibilityStatus.Checking: return "running";
                            default: return "unknown";
                            }
                        }
                        label: Compatibility.stateLabel
                        detail: Compatibility.explanation
                    }

                    StatusChip {
                        statusKey: Session.state === SessionStatus.Connected ? "succeeded"
                            : Session.state === SessionStatus.Connecting ? "running"
                            : Session.state === SessionStatus.Offline ? "offline"
                            : Session.state === SessionStatus.Disconnected ? "unknown"
                            : "failed"
                        label: Session.stateLabel
                        detail: Session.lastError
                    }

                    Item { Layout.fillWidth: true }

                    AcpButton {
                        label: qsTr("Vérifier maintenant")
                        commandId: "connection.probe"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: Compatibility.explanation.length > 0
                    wrapMode: Text.WordWrap
                    text: Compatibility.explanation
                    color: Colors.textSecondary
                    lineHeight: Type.prose.lineHeight
                    lineHeightMode: Text.FixedHeight
                    font.family: Type.prose.family
                    font.pixelSize: Type.prose.pixelSize
                }
            }
        }

        EmptyState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: qsTr("Aucune donnée métier n'est encore affichée")
            body: qsTr("Cette version est la fondation de la station : transport, session, "
                       + "flux d'événements, compatibilité et coquille. Les écrans des "
                       + "missions, des approbations et de la bibliothèque ne sont pas "
                       + "livrés, et leurs compteurs ne sont donc pas affichés plutôt que "
                       + "d'être montrés à zéro.")
            actionLabel: qsTr("Ouvrir les diagnostics")
            actionCommandId: "navigation.diagnostics"
        }
    }
}
