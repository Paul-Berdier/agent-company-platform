// Accueil : état mesuré de la liaison et accès au contexte projet natif.

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
            textFormat: Text.PlainText
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
                    textFormat: Text.PlainText
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
            title: Workspace.projectName || qsTr("Votre espace de travail")
            body: qsTr("Choisissez un projet pour retrouver ses conversations, créer une mission, "
                       + "suivre ses runs et télécharger ses livrables. Les informations proviennent "
                       + "du serveur auquel cette session est connectée.")
            actionLabel: qsTr("Ouvrir les projets")
            actionCommandId: "navigation.projects"
        }
    }
}
