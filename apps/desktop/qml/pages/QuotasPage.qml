// Quotas réels d'abonnement : reste relevé aux sources officielles, jamais estimé.
//
// Chaque valeur vient de GET /subscription-quotas, lui-même alimenté par le worker du
// titulaire (app-server Codex, ligne d'état Claude Code). L'écran ne lit rien d'autre :
// ni fichier local, ni poste du worker, ni base. Réservé au propriétaire de la
// plateforme, parce que l'usage d'un abonnement est personnel à son titulaire.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    readonly property bool hasRows: SubscriptionQuotas.reports.count > 0

    Component.onCompleted: SubscriptionQuotas.active = true
    Component.onDestruction: SubscriptionQuotas.active = false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4

        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space4
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("Quotas d'abonnement")
                subtitle: qsTr("Reste réel relevé aux sources officielles, jamais estimé · actualisation automatique toutes les %1 s")
                    .arg(SubscriptionQuotas.refreshIntervalSeconds)
            }
            BusyIndicator {
                running: SubscriptionQuotas.loading
                visible: running
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                Accessible.name: qsTr("Lecture des quotas en cours")
            }
            StatusChip {
                objectName: "quotasStateChip"
                statusKey: SubscriptionQuotas.stateStatusKey
                label: SubscriptionQuotas.stateLabel
            }
            AcpButton {
                objectName: "quotasRefreshButton"
                label: qsTr("Actualiser")
                manualEnabled: SubscriptionQuotas.canRefresh
                onTriggered: SubscriptionQuotas.refresh()
            }
        }

        Rectangle {
            objectName: "quotasPersonalUseNotice"
            Layout.fillWidth: true
            implicitHeight: noticeColumn.implicitHeight + Space.space4 * 2
            radius: Radius.radiusMd
            color: Colors.surfaceSunken
            border.width: Space.layoutBorderWidth
            border.color: Colors.borderSubtle
            Accessible.role: Accessible.StaticText
            Accessible.name: noticeTitle.text + ". " + noticeBody.text
            Column {
                id: noticeColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Space.space4
                spacing: Space.space1
                Text {
                    id: noticeTitle
                    objectName: "quotasPersonalUseTitle"
                    width: parent.width
                    text: qsTr("Abonnements personnels du propriétaire — usage personnel uniquement")
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    color: Colors.textPrimary
                    font.family: Type.tableCellEmphasis.family
                    font.pixelSize: Type.tableCellEmphasis.pixelSize
                    font.weight: Type.tableCellEmphasis.weight
                }
                Text {
                    id: noticeBody
                    width: parent.width
                    text: qsTr("Codex (compte ChatGPT) et Claude Code sont des abonnements personnels : leurs conditions en réservent l'usage au titulaire. Seul le propriétaire de la plateforme voit ces relevés ; ils ne doivent pas servir à faire travailler d'autres personnes sur son abonnement.")
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    color: Colors.textSecondary
                    font.family: Type.metadata.family
                    font.pixelSize: Type.metadata.pixelSize
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: page.hasRows && text.length > 0
            text: [SubscriptionQuotas.servedLabel, SubscriptionQuotas.staleAfterLabel]
                .filter(function (part) { return part.length > 0; }).join(" · ")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colors.textMuted
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }

        ListView {
            id: quotaList
            objectName: "quotasList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: page.hasRows
            clip: true
            spacing: Space.space4
            model: SubscriptionQuotas.reports
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                id: card
                required property var item
                required property int index
                objectName: "quotaCard-" + card.index
                width: quotaList.width
                implicitHeight: cardColumn.implicitHeight + Space.space5 * 2
                radius: Radius.radiusMd
                color: Colors.surfacePanel
                border.width: card.activeFocus ? Space.layoutFocusRingWidth : Space.layoutBorderWidth
                border.color: card.activeFocus ? Colors.borderFocus
                    : card.item.limitReached ? Status.statusFailedBorder : Colors.borderDefault
                activeFocusOnTab: true
                Accessible.role: Accessible.Grouping
                Accessible.name: card.item.accessibleName
                Accessible.focusable: true

                ColumnLayout {
                    id: cardColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Space.space5
                    spacing: Space.space3

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Space.space3
                        Text {
                            objectName: "quotaProvider-" + card.index
                            text: card.item.providerLabel
                            textFormat: Text.PlainText
                            color: Colors.textPrimary
                            font.family: Type.objectTitle.family
                            font.pixelSize: Type.objectTitle.pixelSize
                            font.weight: Type.objectTitle.weight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("worker « %1 »").arg(card.item.workerName)
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: Colors.textMuted
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }
                        StatusChip {
                            objectName: "quotaStale-" + card.index
                            visible: card.item.stale
                            statusKey: "degraded"
                            label: card.item.staleLabel
                            detail: qsTr("Relevé plus ancien que le seuil de fraîcheur de l'API : cette valeur n'est pas actuelle.")
                        }
                        StatusChip {
                            objectName: "quotaState-" + card.index
                            statusKey: card.item.statusKey
                            label: card.item.statusLabel
                            detail: card.item.detail
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Offre : %1 · Source : %2 · Compteur : %3")
                            .arg(card.item.plan).arg(card.item.sourceLabel).arg(card.item.limitId)
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textSecondary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("%1 (%2) · reçu par l'API %3")
                            .arg(card.item.freshness).arg(card.item.observedText).arg(card.item.receivedText)
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: card.item.stale ? Status.statusDegradedForeground : Colors.textMuted
                        font.family: Type.metadata.family
                        font.pixelSize: Type.metadata.pixelSize
                    }

                    Rectangle {
                        objectName: "quotaLimitReached-" + card.index
                        Layout.fillWidth: true
                        visible: card.item.limitReached
                        implicitHeight: limitText.implicitHeight + Space.space3 * 2
                        radius: Radius.radiusSm
                        color: Status.statusFailedTint
                        border.width: Space.layoutBorderWidth
                        border.color: Status.statusFailedBorder
                        Accessible.role: Accessible.AlertMessage
                        Accessible.name: limitText.text
                        Text {
                            id: limitText
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: Space.space4
                            text: qsTr("Limite atteinte : %1").arg(card.item.limitReachedLabel)
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Status.statusFailedForeground
                            font.family: Type.tableCellEmphasis.family
                            font.pixelSize: Type.tableCellEmphasis.pixelSize
                            font.weight: Type.tableCellEmphasis.weight
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: card.item.status !== "ok" && card.item.detail.length > 0
                        text: card.item.detail
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textSecondary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: !card.item.current
                        text: card.item.supersededNote
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Status.statusDegradedForeground
                        font.family: Type.metadata.family
                        font.pixelSize: Type.metadata.pixelSize
                    }

                    Repeater {
                        model: card.item.windows
                        delegate: QuotaGauge {
                            required property var modelData
                            required property int index
                            objectName: "quotaGauge-" + card.index + "-" + index
                            Layout.fillWidth: true
                            label: modelData.label
                            remainingPercent: modelData.remainingPercent
                            remainingText: modelData.remainingText
                            usedText: modelData.usedText
                            resetText: modelData.resetText
                            countdownText: modelData.countdownText
                            level: modelData.level
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: card.item.status === "ok"
                        text: qsTr("Crédits : %1 · Limite : %2")
                            .arg(card.item.creditsLabel).arg(card.item.limitReachedLabel)
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textSecondary
                        font.family: Type.metadata.family
                        font.pixelSize: Type.metadata.pixelSize
                    }
                }
            }
        }

        EmptyState {
            objectName: "quotasEmptyState"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.hasRows
            title: SubscriptionQuotas.stateLabel
            body: SubscriptionQuotas.message
        }
    }
}
