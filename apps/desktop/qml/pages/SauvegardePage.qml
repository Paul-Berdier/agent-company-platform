// Page Sauvegarde (cahier P8 § 7.9) : exporter une sauvegarde de Hermes chiffrée sur ce PC
// (DPAPI, format ACPB1), sans que l'archive en clair touche son disque ; la déchiffrer pour une
// restauration. Chaque étape affichée est celle que le serveur a réellement franchie.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: {
        Sauvegarde.pageVisible = true;
        destination.text = Sauvegarde.proposerDestination();
    }
    Component.onDestruction: Sauvegarde.pageVisible = false

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    component Alerte: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Status.statusDegradedForeground
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }

    ScrollView {
        id: defilement
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: Math.min(defilement.availableWidth - Space.space8 * 2, Space.layoutContentMaxWidth)
            x: Math.max(Space.space8, (defilement.availableWidth - width) / 2)
            spacing: Space.space5

            Item { Layout.preferredHeight: Space.space4 }

            Text {
                Layout.fillWidth: true
                text: qsTr("Sauvegarde")
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
            }
            Discret {
                text: qsTr("Exporte une sauvegarde de Hermes, chiffrée pour votre session Windows : l'archive en clair "
                           + "ne touche jamais le disque de ce PC. Elle contient .env et auth.json : une restauration "
                           + "impose de reconnecter le fournisseur openai-codex. Le fichier chiffré est lié à ce profil "
                           + "Windows et disparaît avec lui : la sauvegarde du volume Railway reste la sauvegarde principale.")
            }
            Alerte {
                visible: !Sauvegarde.chiffrementDisponible
                text: qsTr("Le chiffrement DPAPI n'est disponible que sous Windows : l'export est désactivé sur ce système.")
            }
            BandeauMessage {
                Layout.fillWidth: true
                message: Sauvegarde.messageGeste
                erreur: Sauvegarde.erreurGeste
            }

            // --- Export -----------------------------------------------------------------------------
            Carte {
                objectName: "sauvegarde-export"
                Layout.fillWidth: true
                titre: qsTr("Exporter une sauvegarde chiffrée")
                cle: Sauvegarde.etapeCle
                libelleEtat: Sauvegarde.etape
                Discret { text: qsTr("Fichier chiffré à écrire sur ce PC") }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Space.space4
                    AcpTextField {
                        id: destination
                        objectName: "sauvegarde-destination"
                        Layout.fillWidth: true
                        enabled: !Sauvegarde.enCours
                        accessibleName: qsTr("Fichier chiffré à écrire")
                    }
                    AcpButton {
                        label: qsTr("Choisir…")
                        manualEnabled: !Sauvegarde.enCours
                        onTriggered: choixDestination.open()
                    }
                }
                RowLayout {
                    spacing: Space.space4
                    AcpButton {
                        objectName: "sauvegarde-exporter"
                        primary: true
                        label: qsTr("Exporter et chiffrer")
                        manualEnabled: Sauvegarde.chiffrementDisponible && !Sauvegarde.enCours
                                       && destination.text.trim().length > 0
                        onTriggered: Sauvegarde.exporter(destination.text)
                    }
                    AcpButton {
                        objectName: "sauvegarde-annuler"
                        visible: Sauvegarde.interruptible
                        label: qsTr("Annuler l'export")
                        onTriggered: Sauvegarde.annuler()
                    }
                    AcpButton {
                        visible: !Sauvegarde.enCours && (Sauvegarde.phase === 5 || Sauvegarde.phase === 6)
                        label: qsTr("Nouvel export")
                        onTriggered: {
                            Sauvegarde.reinitialiser();
                            destination.text = Sauvegarde.proposerDestination();
                        }
                    }
                }
                Discret { visible: Sauvegarde.progression.length > 0; text: Sauvegarde.progression }
                BlocTexte {
                    Layout.fillWidth: true
                    visible: Sauvegarde.journal.length > 0
                    libelle: qsTr("Dernières lignes du journal de la sauvegarde (expurgées)")
                    texte: Sauvegarde.journal
                    monospace: true
                }
            }

            // --- Résultat ---------------------------------------------------------------------------
            Carte {
                objectName: "sauvegarde-resultat"
                Layout.fillWidth: true
                visible: (Sauvegarde.resultat.fichier || "").length > 0 || (Sauvegarde.resultat.suppression || "").length > 0
                titre: qsTr("Résultat")
                KeyValueRow { Layout.fillWidth: true; visible: (Sauvegarde.resultat.fichier || "").length > 0; label: qsTr("Fichier chiffré"); value: Sauvegarde.resultat.fichier || ""; monospace: true }
                KeyValueRow { Layout.fillWidth: true; visible: (Sauvegarde.resultat.taille || "").length > 0; label: qsTr("Taille du fichier chiffré"); value: Sauvegarde.resultat.taille || "" }
                KeyValueRow { Layout.fillWidth: true; visible: (Sauvegarde.resultat.tailleArchive || "").length > 0; label: qsTr("Taille de l'archive"); value: Sauvegarde.resultat.tailleArchive || "" }
                BlocTexte {
                    Layout.fillWidth: true
                    visible: (Sauvegarde.resultat.empreinte || "").length > 0
                    libelle: qsTr("Empreinte SHA-256 du fichier chiffré")
                    texte: Sauvegarde.resultat.empreinte || ""
                    monospace: true
                }
                KeyValueRow { Layout.fillWidth: true; visible: (Sauvegarde.resultat.duree || "").length > 0; label: qsTr("Durée"); value: Sauvegarde.resultat.duree || "" }
                Text {
                    Layout.fillWidth: true
                    visible: (Sauvegarde.resultat.suppression || "").length > 0
                    text: Sauvegarde.resultat.suppression || ""
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: (Sauvegarde.resultat.archiveRestante || "").length > 0 ? Status.statusFailedForeground
                                                                                 : Colors.textSecondary
                    font.family: Type.tableCell.family
                    font.pixelSize: Type.tableCell.pixelSize
                }
            }

            // --- Déchiffrement (restauration, étape P9) ---------------------------------------------------
            Carte {
                objectName: "sauvegarde-dechiffrer"
                Layout.fillWidth: true
                titre: qsTr("Déchiffrer une sauvegarde")
                sousTitre: qsTr("Pour une restauration : écrit l'archive de Hermes EN CLAIR à l'endroit choisi. Seule la "
                                + "session Windows qui a fait l'export peut la déchiffrer.")
                Discret { text: qsTr("Sauvegarde chiffrée (.acpb)") }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Space.space4
                    AcpTextField {
                        id: source
                        objectName: "sauvegarde-source"
                        Layout.fillWidth: true
                        accessibleName: qsTr("Sauvegarde chiffrée à lire")
                    }
                    AcpButton {
                        label: qsTr("Choisir…")
                        onTriggered: choixSource.open()
                    }
                }
                Discret { text: qsTr("Archive à écrire (.zip)") }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Space.space4
                    AcpTextField {
                        id: archive
                        objectName: "sauvegarde-archive"
                        Layout.fillWidth: true
                        accessibleName: qsTr("Archive en clair à écrire")
                    }
                    AcpButton {
                        label: qsTr("Choisir…")
                        onTriggered: choixArchive.open()
                    }
                }
                AcpButton {
                    objectName: "sauvegarde-dechiffrer-bouton"
                    label: qsTr("Déchiffrer")
                    manualEnabled: Sauvegarde.chiffrementDisponible && !Sauvegarde.enCours && !Sauvegarde.gesteEnCours
                                   && source.text.trim().length > 0 && archive.text.trim().length > 0
                    onTriggered: confirmationDechiffrement.open()
                }
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }

    FileDialog {
        id: choixDestination
        title: qsTr("Fichier de sauvegarde chiffrée")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "acpb"
        nameFilters: [qsTr("Sauvegarde chiffrée (*.acpb)")]
        onAccepted: destination.text = Sauvegarde.versCheminLocal(selectedFile.toString())
    }
    FileDialog {
        id: choixSource
        title: qsTr("Sauvegarde chiffrée à déchiffrer")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Sauvegarde chiffrée (*.acpb)")]
        onAccepted: source.text = Sauvegarde.versCheminLocal(selectedFile.toString())
    }
    FileDialog {
        id: choixArchive
        title: qsTr("Archive en clair à écrire")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "zip"
        nameFilters: [qsTr("Archive de Hermes (*.zip)")]
        onAccepted: archive.text = Sauvegarde.versCheminLocal(selectedFile.toString())
    }

    Dialog {
        id: confirmationDechiffrement
        objectName: "sauvegarde-dechiffrement-confirmation"
        anchors.centerIn: parent
        modal: true
        title: qsTr("Écrire l'archive de Hermes en clair ?")
        width: Math.min(page.width - Space.space8 * 2, 560)
        contentItem: ColumnLayout {
            spacing: Space.space4
            Text {
                Layout.fillWidth: true
                text: qsTr("L'archive contient .env et auth.json en clair : gardez-la hors de tout dossier partagé ou "
                           + "synchronisé, et supprimez-la après la restauration.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textSecondary
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }
            RowLayout {
                spacing: Space.space4
                AcpButton {
                    objectName: "sauvegarde-dechiffrer-confirmer"
                    primary: true
                    label: qsTr("Déchiffrer")
                    onTriggered: {
                        confirmationDechiffrement.close();
                        Sauvegarde.dechiffrer(source.text, archive.text);
                    }
                }
                AcpButton {
                    label: qsTr("Annuler")
                    onTriggered: confirmationDechiffrement.close()
                }
            }
        }
    }
}
