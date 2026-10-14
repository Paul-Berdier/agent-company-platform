// Notes Markdown du coffre ACP, échangées uniquement avec Hermes.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    objectName: "coffre-page"
    readonly property bool disponible: Coffre.etat === "pret" && Coffre.actif && !Coffre.occupe
    property bool guideVisible: false
    Component.onCompleted: Coffre.pageVisible = visible
    onVisibleChanged: {
        Coffre.pageVisible = visible
        if (!visible) confirmation.close()
    }
    Connections {
        target: Coffre
        function onActifChange() { if (!Coffre.actif) confirmation.close() }
    }
    Component.onDestruction: Coffre.pageVisible = false

    component Paragraphe: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }
    function confirmer(action, titre, message, destination) {
        confirmation.action = action
        confirmation.title = titre
        confirmation.message = message
        confirmation.destination = destination || ""
        confirmation.chemin = Coffre.chemin
        confirmation.open()
    }
    ScrollView {
        id: defilement
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: contenu
            width: Math.min(defilement.availableWidth - Space.space8 * 2, Space.layoutContentMaxWidth)
            x: Math.max(Space.space8, (defilement.availableWidth - width) / 2)
            spacing: Space.space5
            Item { Layout.preferredHeight: Space.space4 }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Coffre ACP")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton { objectName: "coffre-actualiser"; label: qsTr("Actualiser l’état"); manualEnabled: Coffre.actif && !Coffre.occupe; onTriggered: Coffre.actualiser() }
            }
            Paragraphe { text: qsTr("Écrivez vos notes et retrouvez leurs liens. Le bridge de votre ordinateur garde les fichiers dans le coffre ACP ; Obsidian peut rester fermé.") }
            Paragraphe { objectName: "coffre-etat"; text: Coffre.etatLibelle + " · " + Coffre.lecture; color: Colors.textPrimary }
            Paragraphe { visible: Coffre.operation.length > 0; text: Coffre.operation }
            BandeauMessage { Layout.fillWidth: true; erreur: Coffre.erreur; message: Coffre.messageGeste }
            AcpButton {
                visible: Coffre.occupe && Coffre.erreur.length > 0
                label: qsTr("Fermer le suivi incertain")
                onTriggered: page.confirmer("suivi", qsTr("Fermer uniquement le suivi local ?"), qsTr("Cela n’annule pas l’opération distante. Son résultat reste inconnu ; relisez la note avant toute nouvelle écriture. Votre brouillon reste conservé."))
            }

            Carte {
                Layout.fillWidth: true
                visible: Coffre.etat === "non_configure" || Coffre.etat === "revoque" || page.guideVisible
                titre: qsTr("Préparer un nouveau coffre")
                Paragraphe { text: qsTr("Le serveur ACP doit lui aussi être en version 1.2.0 ou ultérieure. La mise à jour du client Windows seule n’ajoute pas cette fonction au serveur.") }
                Paragraphe { text: qsTr("Ouvrez le menu Démarrer de Windows, puis « Coffre ACP - Obsidian ». Le lanceur est inclus avec ACP 1.2.0 ; aucun Python à installer.") }
                Paragraphe { text: qsTr("1. Dans le lanceur, choisissez « Créer mon nouveau coffre ACP » et un dossier neuf. Avec l’archive portable, ouvrez coffre/Lancer-Coffre-ACP.cmd.") }
                Paragraphe { text: qsTr("2. Créez un code ci-dessous, puis choisissez « Associer ce coffre à Hermes » dans le lanceur. Saisissez cette origine et collez le code dans sa saisie masquée.") }
                BlocTexte { Layout.fillWidth: true; libelle: qsTr("Origine Hermes · sélectionnable et copiable"); texte: Shell.serverUrl }
                Paragraphe { text: qsTr("3. Comparez l’empreinte du lanceur avec celle affichée ici, puis confirmez. Choisissez enfin « Démarrer le bridge » dans le lanceur et laissez sa fenêtre ouverte. Son identité reste distincte de l’exécutant ACP.") }
                RowLayout {
                    AcpButton { objectName: "coffre-creer-code"; label: qsTr("Créer un code d’association"); manualEnabled: Coffre.actif && !Coffre.occupe; onTriggered: Coffre.creerCode() }
                    AcpButton { objectName: "coffre-copier-code"; label: qsTr("Copier le code"); visible: Coffre.codeSecondes > 0; onTriggered: Coffre.copierCode() }
                }
                Paragraphe { visible: Coffre.codeSecondes > 0; text: qsTr("Code à usage unique, encore valable %1 s. Il reste uniquement en mémoire.").arg(Coffre.codeSecondes) }
            }
            AcpButton { label: page.guideVisible ? qsTr("Masquer le guide") : qsTr("Guide de préparation"); visible: Coffre.etat !== "non_configure" && Coffre.etat !== "revoque"; onTriggered: page.guideVisible = !page.guideVisible }
            Carte {
                Layout.fillWidth: true
                visible: Coffre.etat === "a_confirmer"
                titre: qsTr("Confirmer l’ordinateur du coffre")
                Paragraphe { text: qsTr("Empreinte reçue : %1. Saisissez celle affichée par le lanceur local après comparaison.").arg(Coffre.coffre.empreinte || "") }
                AcpTextField { id: empreinte; Layout.fillWidth: true; placeholder: qsTr("Empreinte affichée par le lanceur local") }
                AcpButton { objectName: "coffre-confirmer"; label: qsTr("Confirmer l’empreinte"); manualEnabled: !Coffre.occupe && empreinte.text.length > 0; onTriggered: Coffre.confirmerEmpreinte(empreinte.text) }
            }
            Paragraphe { visible: Coffre.etat === "hors_ligne"; text: qsTr("Ouvrez « Coffre ACP - Obsidian » dans le menu Démarrer, puis choisissez « Démarrer le bridge » et laissez sa fenêtre ouverte. Les notes déjà ouvertes restent consultables ; aucune écriture n’est annoncée réussie sans réponse du bridge.") }

            GridLayout {
                Layout.fillWidth: true
                columns: contenu.width >= 800 ? 2 : 1
                columnSpacing: Space.space5
                rowSpacing: Space.space5
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 260
                    Layout.maximumWidth: contenu.width >= 800 ? 300 : -1
                    Layout.alignment: Qt.AlignTop
                    spacing: Space.space3
                    AcpTextField { id: recherche; Layout.fillWidth: true; objectName: "coffre-recherche"; placeholder: qsTr("Chercher dans le coffre"); text: Coffre.recherche; onTextChanged: Coffre.recherche = text; onAccepted: if (page.disponible) Coffre.chercher() }
                    RowLayout {
                        AcpButton { objectName: "coffre-chercher"; label: qsTr("Rechercher"); manualEnabled: page.disponible && Coffre.capacite("rechercher"); onTriggered: Coffre.chercher() }
                        AcpButton { objectName: "coffre-lister"; label: qsTr("Lister les notes"); manualEnabled: page.disponible && Coffre.capacite("lister"); onTriggered: Coffre.lister() }
                    }
                    Paragraphe { text: qsTr("%1 entrée(s) affichée(s)%2").arg(Coffre.notes.count).arg(Coffre.tronque ? qsTr(" · résultats limités") : "") }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 360
                        color: Colors.surfacePanel
                        border.color: Colors.borderDefault
                        radius: Radius.radiusMd
                        ListView {
                            id: notes
                            anchors.fill: parent
                            anchors.margins: Space.space2
                            clip: true
                            model: Coffre.notes
                            ScrollBar.vertical: ScrollBar {}
                            delegate: ItemDelegate {
                                id: entree
                                required property var item
                                width: notes.width
                                implicitHeight: noteResume.implicitHeight + Space.space4 * 2
                                enabled: !Coffre.occupe
                                padding: Space.space4
                                onClicked: Coffre.ouvrirNote(item.chemin)
                                Accessible.name: item.chemin
                                background: Rectangle { color: Coffre.chemin === entree.item.chemin ? Colors.stateSelected : entree.hovered ? Colors.surfacePanelRaised : "transparent"; radius: Radius.radiusSm; border.width: entree.activeFocus ? 2 : 0; border.color: Colors.borderFocus }
                                contentItem: ColumnLayout {
                                    id: noteResume
                                    Paragraphe { text: entree.item.chemin; color: Colors.textPrimary; wrapMode: Text.WrapAnywhere }
                                    Paragraphe { text: entree.item.extrait || ""; visible: text.length > 0; maximumLineCount: 3; elide: Text.ElideRight }
                                }
                            }
                        }
                    }
                    AcpTextField { id: nouveauChemin; Layout.fillWidth: true; objectName: "coffre-nouveau-chemin"; placeholder: qsTr("Projets/Nouvelle note.md") }
                    AcpButton { objectName: "coffre-nouvelle"; label: qsTr("Préparer une note"); manualEnabled: !Coffre.occupe && nouveauChemin.text.trim().length > 0; onTriggered: Coffre.nouvelleNote(nouveauChemin.text.trim()) }
                    Paragraphe { text: qsTr("Une note préparée reste un brouillon jusqu’à sa sauvegarde. Les brouillons restent en mémoire pendant la navigation, pas après fermeture ou perte de session.") }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 650
                    Layout.alignment: Qt.AlignTop
                    spacing: Space.space3
                    Text {
                        Layout.fillWidth: true
                        text: Coffre.noteOuverte ? Coffre.chemin : qsTr("Ouvrir ou préparer une note")
                        textFormat: Text.PlainText
                        wrapMode: Text.WrapAnywhere
                        color: Colors.textPrimary
                        font.family: Type.panelTitle.family
                        font.pixelSize: Type.panelTitle.pixelSize
                    }
                    Paragraphe { visible: Coffre.noteOuverte; text: Coffre.modifie ? qsTr("Brouillon non enregistré") : Coffre.noteLue ? qsTr("Version lue du coffre") : qsTr("Lecture non confirmée") }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 430
                        visible: Coffre.noteOuverte
                        clip: true
                        TextArea {
                            id: editeur
                            objectName: "coffre-editeur"
                            text: Coffre.brouillon
                            onTextChanged: Coffre.brouillon = text
                            textFormat: TextEdit.PlainText
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
                            color: Colors.textPrimary
                            selectionColor: Colors.stateSelected
                            selectedTextColor: Colors.textPrimary
                            font.family: Type.identifier.family
                            font.pixelSize: Type.prose.pixelSize
                            padding: Space.space5
                            background: Rectangle { color: Colors.surfacePanel; border.color: editeur.activeFocus ? Colors.borderFocus : Colors.borderDefault; radius: Radius.radiusSm }
                            Accessible.name: qsTr("Contenu Markdown de la note")
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: Space.space2
                        visible: Coffre.noteOuverte
                        AcpButton { objectName: "coffre-sauvegarder"; primary: true; label: qsTr("Sauvegarder"); manualEnabled: page.disponible && !Coffre.conflit && Coffre.capacite(Coffre.nouvelle ? "creer" : "ecrire"); onTriggered: Coffre.sauvegarder() }
                        AcpButton { objectName: "coffre-relire"; label: qsTr("Relire pour comparer"); manualEnabled: page.disponible && Coffre.capacite("lire"); onTriggered: Coffre.relire() }
                        AcpButton { objectName: "coffre-backlinks"; label: qsTr("Liens entrants"); manualEnabled: page.disponible && !Coffre.nouvelle && Coffre.capacite("backlinks"); onTriggered: Coffre.lireBacklinks() }
                        AcpButton { objectName: "coffre-archiver"; label: qsTr("Archiver"); manualEnabled: page.disponible && !Coffre.modifie && !Coffre.nouvelle && Coffre.capacite("archiver"); onTriggered: page.confirmer("archive", qsTr("Archiver cette note ?"), qsTr("La note sera déplacée dans l’archive récupérable ACP du coffre. Elle ne sera plus dans la liste active.")) }
                    }
                    Paragraphe { visible: Coffre.conflit; text: qsTr("La note a changé dans le coffre. Votre brouillon est conservé. Relisez la version distante puis comparez les deux textes avant de continuer."); color: Colors.textPrimary }
                    Carte {
                        Layout.fillWidth: true
                        visible: Coffre.versionServeurDisponible
                        titre: qsTr("Version relue du coffre")
                        BlocTexte { Layout.fillWidth: true; texte: Coffre.versionServeur; monospace: true }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Space.space2
                            AcpButton { label: qsTr("Utiliser ce texte"); manualEnabled: !Coffre.occupe; onTriggered: page.confirmer("distant", qsTr("Remplacer le brouillon ?"), qsTr("Le brouillon local sera remplacé par le texte relu ci-dessus.")) }
                            AcpButton { label: qsTr("Garder mon texte après comparaison"); manualEnabled: !Coffre.occupe; onTriggered: page.confirmer("local", qsTr("Reprendre le brouillon sur cette version ?"), qsTr("La prochaine sauvegarde remplacera la version relue par votre brouillon. Cette action prépare seulement la nouvelle révision de référence.")) }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: Coffre.noteOuverte && !Coffre.nouvelle
                        AcpTextField { id: destination; Layout.fillWidth: true; placeholder: qsTr("Nouveau chemin relatif .md") }
                        AcpButton { objectName: "coffre-renommer"; label: qsTr("Renommer"); manualEnabled: page.disponible && !Coffre.modifie && Coffre.capacite("renommer") && destination.text.trim().length > 0; onTriggered: page.confirmer("renommer", qsTr("Déplacer cette note ?"), qsTr("La destination ne sera pas écrasée. Les liens des autres notes ne seront pas réécrits automatiquement."), destination.text.trim()) }
                    }
                    Repeater {
                        model: Coffre.backlinks
                        delegate: AcpButton { required property var item; label: qsTr("Depuis %1").arg(item.source); manualEnabled: !Coffre.occupe; onTriggered: Coffre.ouvrirNote(item.source) }
                    }
                }
            }
            Carte {
                Layout.fillWidth: true
                titre: qsTr("Liens du coffre")
                AcpButton { objectName: "coffre-graphe"; label: qsTr("Lire le graphe des liens"); manualEnabled: page.disponible && Coffre.capacite("graphe"); onTriggered: Coffre.lireGraphe() }
                Paragraphe { text: Coffre.graphe.portee || qsTr("Graphe non lu. Seuls les liens réellement relevés seront affichés.") }
                Paragraphe { visible: Coffre.graphe.tronque === true; text: qsTr("Le graphe est limité aux résultats renvoyés par le bridge.") }
                Item {
                    id: dessinGraphe
                    objectName: "coffre-graphe-visuel"
                    Layout.fillWidth: true
                    Layout.preferredHeight: visibles.length > 0 ? Math.ceil(visibles.length / colonnes) * 100 + 30 : 0
                    visible: visibles.length > 0
                    readonly property var visibles: (Coffre.graphe.noeuds || []).slice(0, 16)
                    readonly property int colonnes: width >= 700 ? 4 : 3
                    readonly property real largeurNoeud: Math.min(155, width / colonnes - 24)
                    function centre(index) { return { x: (index % colonnes + 0.5) * width / colonnes, y: 40 + Math.floor(index / colonnes) * 100 } }
                    onWidthChanged: arcs.requestPaint()
                    onVisiblesChanged: arcs.requestPaint()
                    Canvas {
                        id: arcs
                        anchors.fill: parent
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            ctx.strokeStyle = Colors.borderInteractive
                            ctx.fillStyle = Colors.textMuted
                            ctx.lineWidth = 1.5
                            const positions = Object.create(null)
                            for (let i = 0; i < dessinGraphe.visibles.length; ++i)
                                positions[dessinGraphe.visibles[i].chemin] = i
                            const liens = Coffre.graphe.liens || []
                            for (let j = 0; j < liens.length; ++j) {
                                const lien = liens[j]
                                if (positions[lien.source] === undefined || positions[lien.cible] === undefined) continue
                                const a = dessinGraphe.centre(positions[lien.source])
                                const b = dessinGraphe.centre(positions[lien.cible])
                                if (lien.source === lien.cible) {
                                    ctx.beginPath(); ctx.arc(a.x, a.y + 26, 20, 0, Math.PI); ctx.stroke(); continue
                                }
                                const dx = b.x - a.x, dy = b.y - a.y
                                const longueur = Math.sqrt(dx * dx + dy * dy)
                                const facteur = Math.min(Math.abs(dx) > 0 ? dessinGraphe.largeurNoeud / (2 * Math.abs(dx)) : 1000,
                                                         Math.abs(dy) > 0 ? 24 / Math.abs(dy) : 1000)
                                const x = b.x - dx * facteur, y = b.y - dy * facteur
                                const ux = dx / longueur, uy = dy / longueur
                                ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(x, y); ctx.stroke()
                                ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - ux * 8 - uy * 4, y - uy * 8 + ux * 4)
                                ctx.lineTo(x - ux * 8 + uy * 4, y - uy * 8 - ux * 4); ctx.closePath(); ctx.fill()
                            }
                        }
                        Connections { target: Coffre; function onGrapheChange() { arcs.requestPaint() } }
                    }
                    Repeater {
                        model: dessinGraphe.visibles
                        delegate: ItemDelegate {
                            id: noeud
                            required property var modelData
                            required property int index
                            objectName: "coffre-noeud-" + index
                            x: dessinGraphe.centre(index).x - width / 2
                            y: dessinGraphe.centre(index).y - height / 2
                            width: dessinGraphe.largeurNoeud
                            height: 48
                            enabled: !Coffre.occupe
                            onClicked: Coffre.ouvrirNote(modelData.chemin)
                            Accessible.name: qsTr("Ouvrir %1").arg(modelData.chemin)
                            background: Rectangle { color: noeud.hovered ? Colors.surfacePanelRaised : Colors.surfacePanel; radius: Radius.radiusSm; border.width: noeud.activeFocus ? 2 : 1; border.color: noeud.activeFocus ? Colors.borderFocus : Colors.borderInteractive }
                            contentItem: Text { text: noeud.modelData.chemin; textFormat: Text.PlainText; elide: Text.ElideMiddle; verticalAlignment: Text.AlignVCenter; color: Colors.textPrimary; font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize }
                            ToolTip.visible: hovered
                            ToolTip.text: modelData.chemin
                        }
                    }
                }
                Paragraphe { visible: (Coffre.graphe.noeuds || []).length > 16; text: qsTr("Vue limitée aux 16 premières notes. Les liens renvoyés restent listés ci-dessous.") }
                Repeater {
                    model: Coffre.graphe.liens || []
                    delegate: Flow {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Space.space2
                        AcpButton { label: modelData.source; manualEnabled: !Coffre.occupe; onTriggered: Coffre.ouvrirNote(modelData.source) }
                        Paragraphe { width: implicitWidth; text: "→" }
                        AcpButton { label: modelData.cible; manualEnabled: !Coffre.occupe; onTriggered: Coffre.ouvrirNote(modelData.cible) }
                    }
                }
                Repeater {
                    model: Coffre.graphe.non_resolus || []
                    delegate: Paragraphe { required property var modelData; text: qsTr("Non résolu ou ambigu : %1 → %2").arg(modelData.source).arg(modelData.cible) }
                }
            }
            AcpButton { objectName: "coffre-revoquer"; visible: !!Coffre.coffre.coffre_id && Coffre.etat !== "revoque"; label: qsTr("Révoquer l’association du coffre"); manualEnabled: Coffre.actif && !Coffre.occupe; onTriggered: page.confirmer("revoquer", qsTr("Révoquer le bridge ?"), qsTr("Son jeton sera refusé. Les notes restent sur votre ordinateur ; une nouvelle association sera nécessaire pour les retrouver ici.")) }
            Item { Layout.preferredHeight: Space.space8 }
        }
    }
    Dialog {
        id: confirmation
        objectName: "coffre-confirmation"
        property string action: ""
        property string message: ""
        property string destination: ""
        property string chemin: ""
        anchors.centerIn: parent
        modal: true
        width: Math.min(page.width - Space.space8 * 2, 600)
        contentItem: ColumnLayout {
            spacing: Space.space4
            Paragraphe { text: confirmation.message }
            RowLayout {
                AcpButton {
                    objectName: "coffre-confirmation-accepter"
                    label: qsTr("Confirmer")
                    primary: true
                    onTriggered: {
                        if (confirmation.action === "suivi") Coffre.fermerSuivi(true)
                        else if (confirmation.action === "revoquer") Coffre.revoquer(true)
                        else if (confirmation.chemin === Coffre.chemin) {
                            if (confirmation.action === "archive") Coffre.archiver(true)
                            else if (confirmation.action === "renommer") Coffre.renommer(confirmation.destination, true)
                            else if (confirmation.action === "distant") Coffre.utiliserVersionServeur(true)
                            else if (confirmation.action === "local") Coffre.garderBrouillonSurVersionServeur(true)
                        }
                        confirmation.close()
                    }
                }
                AcpButton { label: qsTr("Annuler"); onTriggered: confirmation.close() }
            }
        }
    }
}
