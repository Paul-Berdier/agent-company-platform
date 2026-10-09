// Page Routage (cahier P8 § 7.7, décision D8-6) : listes relevées, table de routage par
// classe avec son brouillon (suggestion, retrait, retour à la table enregistrée), validation
// complète ou rien, interdits en lecture seule, surcharges actives. L'édition libre se fait dans
// le tableau de bord : la station n'invente aucun modèle ni aucun effort.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: Routage.pageVisible = true
    Component.onDestruction: Routage.pageVisible = false

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    component Separateur: Rectangle {
        Layout.fillWidth: true
        height: Space.layoutBorderWidth
        color: Colors.borderSubtle
    }

    component Ligne: KeyValueRow {
        Layout.fillWidth: true
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

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space4
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Routage")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton {
                    objectName: "routage-navigateur"
                    label: qsTr("Modifier dans le navigateur")
                    onTriggered: Routage.modifierDansLeNavigateur()
                }
                AcpButton {
                    objectName: "routage-actualiser"
                    label: qsTr("Actualiser")
                    onTriggered: Routage.actualiser()
                }
            }

            Discret {
                text: qsTr("Une étape d'un projet suit, dans cet ordre : la surcharge active du projet ou de la "
                           + "carte ; sinon le choix explicite (exécutant et modèle de l'exploration choisis dans "
                           + "« Nouveau projet », ou fixés par Hermes dans son plan) ; sinon la première entrée admise "
                           + "de sa classe dans cette table, Hermes faisant lui-même les étapes d'un projet sans dépôt "
                           + "qui l'admettent. Les listes viennent du relevé du poste ; rien n'est deviné, et ce que le "
                           + "poste interdit reste interdit. La station applique les suggestions et valide la table ; "
                           + "l'édition libre, les nouvelles surcharges et les interdits côté Hermes se modifient dans "
                           + "le navigateur.")
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Routage.lecture
                erreur: Routage.erreur
            }
            BandeauMessage {
                Layout.fillWidth: true
                message: Routage.messageGeste
                erreur: Routage.erreurGeste
            }
            Text {
                visible: !Routage.lue && Routage.erreur.length === 0
                text: qsTr("Chargement…")
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }
            Text {
                Layout.fillWidth: true
                visible: Routage.releveFactice
                text: qsTr("Relevé factice : ces listes viennent d'un poste simulé, pas de votre compte.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Status.statusDegradedForeground
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }

            // --- Listes relevées ------------------------------------------------------------------------
            Repeater {
                model: Routage.listes
                delegate: Carte {
                    id: liste
                    required property var item
                    objectName: "routage-liste-" + liste.item.voie
                    Layout.fillWidth: true
                    visible: Routage.lue
                    titre: qsTr("Liste relevée : %1").arg(liste.item.titre)
                    cle: liste.item.badgeCle
                    libelleEtat: liste.item.badgeLibelle
                    Ligne { visible: liste.item.releveLe.length > 0; label: qsTr("Relevé"); value: liste.item.releveLe }
                    Ligne { visible: liste.item.versionCli.length > 0; label: qsTr("Version de la CLI"); value: liste.item.versionCli; monospace: true }
                    BlocTexte { Layout.fillWidth: true; visible: liste.item.detail.length > 0; texte: liste.item.detail }
                    Ligne { visible: liste.item.documentation.length > 0; label: qsTr("Documentation lue"); value: liste.item.documentation; monospace: true }
                    Discret { visible: liste.item.aucunModele.length > 0; text: liste.item.aucunModele }
                    Repeater {
                        model: liste.item.modeles
                        delegate: ColumnLayout {
                            id: modele
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Space.space1
                            RowLayout {
                                Layout.fillWidth: true
                                Ligne { label: qsTr("Modèle"); value: modele.modelData.id; monospace: true }
                                StatusChip { visible: modele.modelData.parDefaut; statusKey: "running"; label: qsTr("par défaut") }
                            }
                            Discret { text: modele.modelData.efforts }
                            Discret {
                                visible: modele.modelData.resolution.length > 0
                                text: qsTr("Résolution documentée : %1").arg(modele.modelData.resolution)
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: liste.item.peutAccepter
                        spacing: Space.space2
                        Discret {
                            text: qsTr("La liste est identique au catalogue embarqué de Codex. Acceptez-la seulement si "
                                       + "vous savez que c'est bien celle de votre compte ; l'acceptation vaut pour ce "
                                       + "relevé seulement.")
                        }
                        AcpButton {
                            objectName: "routage-accepter-" + liste.item.voie
                            label: qsTr("Accepter ce relevé comme celui de mon compte")
                            manualEnabled: !Routage.gesteEnCours
                            onTriggered: Routage.accepterReleve(liste.item.voie)
                        }
                    }
                }
            }

            // --- Table de routage -----------------------------------------------------------------------
            Carte {
                objectName: "routage-table"
                Layout.fillWidth: true
                visible: Routage.lue
                titre: qsTr("Table de routage")
                sousTitre: Routage.brouillonModifie
                    ? qsTr("Brouillon modifié : rien n'est enregistré avant « Valider la table ».")
                    : qsTr("Table telle qu'enregistrée par le greffon.")
                Repeater {
                    model: Routage.classes
                    delegate: ColumnLayout {
                        id: classe
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: classe.item.titre
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                color: Colors.textPrimary
                                font.family: Type.tableCellEmphasis.family
                                font.pixelSize: Type.tableCellEmphasis.pixelSize
                                font.weight: Type.tableCellEmphasis.weight
                            }
                            StatusChip { statusKey: classe.item.etatCle; label: classe.item.etatLibelle }
                        }
                        Discret { text: qsTr("Exécutants possibles : %1").arg(classe.item.voies) }
                        Discret { visible: classe.item.valideLe.length > 0; text: qsTr("Validée le %1").arg(classe.item.valideLe) }
                        Discret { visible: classe.item.vide; text: qsTr("Aucune entrée : la classe n'a pas de table.") }
                        Repeater {
                            model: classe.item.entrees
                            delegate: ColumnLayout {
                                id: entree
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: Space.space1
                                RowLayout {
                                    Layout.fillWidth: true
                                    Ligne {
                                        label: qsTr("Entrée %1").arg(entree.modelData.rang + 1)
                                        value: entree.modelData.texte
                                    }
                                    StatusChip {
                                        visible: entree.modelData.verdict.length > 0
                                        statusKey: entree.modelData.verdictCle.length > 0 ? entree.modelData.verdictCle : "unknown"
                                        label: entree.modelData.verdict
                                    }
                                    AcpButton {
                                        objectName: "routage-retirer-" + classe.item.classe + "-" + entree.modelData.rang
                                        label: qsTr("Retirer")
                                        manualEnabled: !Routage.gesteEnCours
                                        onTriggered: Routage.retirerEntree(classe.item.classe, entree.modelData.rang)
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: entree.modelData.message.length > 0
                                    text: entree.modelData.message
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WordWrap
                                    color: Status.statusFailedForeground
                                    font.family: Type.metadata.family
                                    font.pixelSize: Type.metadata.pixelSize
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: classe.item.aSuggestion
                            spacing: Space.space1
                            BlocTexte {
                                Layout.fillWidth: true
                                libelle: classe.item.suggestionLibelle.length > 0 ? classe.item.suggestionLibelle : qsTr("Suggestion du greffon")
                                texte: classe.item.suggestion
                            }
                            AcpButton {
                                objectName: "routage-suggestion-" + classe.item.classe
                                label: qsTr("Appliquer la suggestion")
                                manualEnabled: !Routage.gesteEnCours
                                onTriggered: Routage.appliquerSuggestion(classe.item.classe)
                            }
                        }
                        Discret { visible: classe.item.remarques.length > 0; text: classe.item.remarques }
                    }
                }
                BlocTexte {
                    Layout.fillWidth: true
                    visible: Routage.refusTable.length > 0
                    libelle: qsTr("Entrées refusées")
                    texte: Routage.refusTable.join("\n")
                }
                RowLayout {
                    spacing: Space.space4
                    AcpButton {
                        objectName: "routage-valider"
                        primary: true
                        label: qsTr("Valider la table")
                        manualEnabled: !Routage.brouillonVide && !Routage.gesteEnCours
                        onTriggered: Routage.valider()
                    }
                    AcpButton {
                        objectName: "routage-revenir"
                        visible: Routage.brouillonModifie
                        label: qsTr("Revenir à la table enregistrée")
                        onTriggered: Routage.revenir()
                    }
                }
            }

            // --- Interdits ------------------------------------------------------------------------------
            Carte {
                objectName: "routage-politique-hermes"
                Layout.fillWidth: true
                visible: Routage.lue
                titre: qsTr("Interdits côté Hermes")
                sousTitre: qsTr("Lecture seule dans la station : ils se modifient dans le navigateur.")
                Ligne { label: qsTr("Efforts interdits"); value: Routage.politiqueHermes.effortsInterdits; monospace: true }
                Ligne { label: qsTr("Paliers admis"); value: Routage.politiqueHermes.paliersAdmis; monospace: true }
                Ligne { label: qsTr("Efforts hors enveloppe"); value: Routage.politiqueHermes.horsEnveloppe; monospace: true }
            }
            Carte {
                objectName: "routage-politique-poste"
                Layout.fillWidth: true
                visible: Routage.lue
                titre: qsTr("Interdit par le poste (poste.toml)")
                sousTitre: qsTr("Lecture seule : seule une modification locale sur le PC peut le lever.")
                Discret { visible: !Routage.politiquePoste.presente; text: qsTr("Inconnu : le poste n'a encore publié aucune politique.") }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Routage.politiquePoste.presente === true
                    spacing: Space.space1
                    Ligne { label: qsTr("Exécutants"); value: Routage.politiquePoste.executants || ""; monospace: true }
                    Ligne { label: qsTr("Efforts interdits"); value: Routage.politiquePoste.effortsInterdits || ""; monospace: true }
                    Ligne { label: qsTr("Paliers admis"); value: Routage.politiquePoste.paliersAdmis || ""; monospace: true }
                    Ligne { label: qsTr("Modèles Codex permis"); value: Routage.politiquePoste.modelesCodex || ""; monospace: true }
                    Ligne { label: qsTr("Alias Claude permis"); value: Routage.politiquePoste.aliasClaude || ""; monospace: true }
                    Ligne { label: qsTr("Réseau des exécutants"); value: Routage.politiquePoste.reseau || "" }
                }
            }

            // --- Surcharges globales --------------------------------------------------------------------
            Carte {
                objectName: "routage-surcharges"
                Layout.fillWidth: true
                visible: Routage.lue
                titre: qsTr("Surcharges globales")
                sousTitre: qsTr("Une surcharge globale passe avant la table pour toute sa classe, jusqu'à sa désactivation. "
                                + "Une nouvelle surcharge se crée dans le navigateur.")
                Discret { visible: Routage.surcharges.count === 0; text: qsTr("Aucune surcharge active.") }
                Repeater {
                    model: Routage.surcharges
                    delegate: ColumnLayout {
                        id: surcharge
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space1
                        Separateur {}
                        Ligne { label: surcharge.item.classe; value: surcharge.item.entree }
                        Ligne { label: qsTr("Créée"); value: surcharge.item.creeLe }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Motif"); texte: surcharge.item.motif }
                        AcpButton {
                            objectName: "routage-desactiver-" + surcharge.item.id
                            visible: surcharge.item.id.length > 0
                            label: qsTr("Désactiver")
                            manualEnabled: !Routage.gesteEnCours
                            onTriggered: Routage.desactiverSurcharge(surcharge.item.id)
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
