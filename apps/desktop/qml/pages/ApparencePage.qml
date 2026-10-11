// Apparence (D165) : famille visuelle, luminosité, mouvement, Concentration, densité et taille
// du texte, avec un aperçu. Tout s'applique à chaud : aucun écran, aucune session ni aucun
// modèle n'est recréé. Les préférences sont gardées sans secret (liste blanche QSettings).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

ScrollView {
    id: page
    objectName: "page-apparence"
    clip: true
    contentWidth: availableWidth

    component Titre: Text {
        Layout.fillWidth: true
        Layout.topMargin: Space.space4
        textFormat: Text.PlainText
        color: Colors.textPrimary
        font.family: Type.panelTitle.family
        font.pixelSize: Type.panelTitle.pixelSize
        font.weight: Type.panelTitle.weight
    }
    component Aide: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textSecondary
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }
    // Choix exclusif : boutons dont un seul est « primaire » (sélectionné), nom accessible explicite.
    component Choix: RowLayout {
        id: choix
        property var options: []
        property var valeur
        property string nom: ""
        signal choisi(var valeur)
        spacing: Space.space2
        Repeater {
            model: choix.options
            delegate: AcpButton {
                required property var modelData
                objectName: "apparence-" + choix.nom + "-" + modelData.valeur
                label: modelData.libelle
                primary: choix.valeur === modelData.valeur
                onTriggered: choix.choisi(modelData.valeur)
                Accessible.name: choix.nom + " : " + modelData.libelle + (choix.valeur === modelData.valeur ? qsTr(" (choisi)") : "")
            }
        }
    }

    ColumnLayout {
        width: Math.min(page.availableWidth - Space.space7 * 2, 960)
        x: Space.space7
        spacing: Space.space4

        RowLayout {
            Layout.topMargin: Space.space6
            spacing: Space.space4
            Embleme { taille: 32 }
            ColumnLayout {
                spacing: Space.space1
                TextePixel { text: qsTr("APPARENCE"); couleur: "accent"; echelle: 2 }
                Aide { text: qsTr("Thème appliqué : %1.").arg(Colors.themeLabels[Colors.theme] || Colors.theme) }
            }
        }

        // --- Famille -----------------------------------------------------------------------
        Titre { text: qsTr("Famille visuelle") }
        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space5
            Repeater {
                model: [
                    { "valeur": "atelier", "nuit": Colors.atelierNuit, "jour": Colors.atelierJour,
                      "description": qsTr("Atelier numérique rétrofuturiste : encre, lavande et menthe, ornements pixel. Par défaut.") },
                    { "valeur": "studio", "nuit": Colors.studioGraphite, "jour": Colors.studioPapier,
                      "description": qsTr("Sobre : graphite végétal et papier ivoire, sans ornement, angles arrondis.") }
                ]
                delegate: Item {
                    id: famille
                    required property var modelData
                    readonly property bool choisie: Appearance.familyPreference === modelData.valeur
                    objectName: "apparence-famille-" + modelData.valeur
                    Layout.fillWidth: true
                    Layout.preferredHeight: carteFamille.implicitHeight + Space.space5 * 2
                    activeFocusOnTab: true
                    FondPixel {
                        anchors.fill: parent
                        couleur: famille.choisie ? Colors.accentMuted : Colors.surfacePanel
                        bordure: famille.activeFocus ? Colors.borderFocus : famille.choisie ? Colors.accentPrimary : Colors.borderDefault
                        epaisseur: famille.activeFocus || famille.choisie ? Space.layoutFocusRingWidth : Space.layoutBorderWidth
                        cran: famille.modelData.valeur === "atelier" ? Space.layoutPixelUnit : 0
                        rayon: Radius.radiusMd
                    }
                    ColumnLayout {
                        id: carteFamille
                        anchors.fill: parent
                        anchors.margins: Space.space5
                        spacing: Space.space3
                        Text {
                            text: Colors.families[famille.modelData.valeur].label
                            textFormat: Text.PlainText
                            color: Colors.textPrimary
                            font.family: Type.panelTitle.family
                            font.pixelSize: Type.panelTitle.pixelSize
                            font.weight: Type.panelTitle.weight
                        }
                        // Nuancier lu dans les jetons du thème lui-même, pas dans le thème actif.
                        Row {
                            spacing: Space.space2
                            Repeater {
                                model: [famille.modelData.nuit, famille.modelData.jour]
                                delegate: Row {
                                    required property var modelData
                                    spacing: 0
                                    Repeater {
                                        model: [modelData.surfaceCanvas, modelData.surfacePanel, modelData.textPrimary,
                                                modelData.accentPrimary, modelData.accentSecondary]
                                        delegate: Rectangle {
                                            required property color modelData
                                            width: 18; height: 18
                                            color: modelData
                                            border.width: Space.layoutBorderWidth
                                            border.color: Colors.borderSubtle
                                        }
                                    }
                                }
                            }
                        }
                        Aide { text: famille.modelData.description }
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: Appearance.familyPreference = famille.modelData.valeur }
                    Keys.onReturnPressed: Appearance.familyPreference = famille.modelData.valeur
                    Keys.onSpacePressed: Appearance.familyPreference = famille.modelData.valeur
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: Colors.families[famille.modelData.valeur].label + (famille.choisie ? qsTr(" (choisie)") : "")
                    Accessible.description: famille.modelData.description
                    Accessible.focusable: true
                    Accessible.onPressAction: Appearance.familyPreference = famille.modelData.valeur
                }
            }
        }

        Titre { text: qsTr("Luminosité") }
        Choix {
            nom: qsTr("Luminosité")
            options: [{ "valeur": "system", "libelle": qsTr("Suivre Windows") },
                      { "valeur": "light", "libelle": qsTr("Clair") },
                      { "valeur": "dark", "libelle": qsTr("Sombre") }]
            valeur: Appearance.themePreference
            onChoisi: function(v) { Appearance.themePreference = v }
        }
        Aide { text: qsTr("Luminosité détectée sur ce poste : %1.").arg(Appearance.systemThemeLabel) }

        Titre { text: qsTr("Mouvement") }
        Choix {
            nom: qsTr("Mouvement")
            options: [{ "valeur": "complet", "libelle": Motion.profileLabels["complet"] },
                      { "valeur": "discret", "libelle": Motion.profileLabels["discret"] },
                      { "valeur": "reduit", "libelle": Motion.profileLabels["reduit"] }]
            valeur: Appearance.motionPreference
            onChoisi: function(v) { Appearance.motionPreference = v }
        }
        Aide {
            text: qsTr("Complet : mouvement fonctionnel et ambiance pixel (portraits, emblème), suspendue hors écran. "
                       + "Discret : mouvement fonctionnel seulement. Réduit : aucun déplacement ni boucle, l'information "
                       + "passe par le texte et le symbole. Qt n'expose pas la préférence de mouvement de Windows : "
                       + "choisissez ici.")
        }
        Titre { text: qsTr("Concentration") }
        Choix {
            nom: qsTr("Concentration")
            options: [{ "valeur": false, "libelle": qsTr("Désactivée") },
                      { "valeur": true, "libelle": qsTr("Activée") }]
            valeur: Appearance.concentration
            onChoisi: function(v) { Appearance.concentration = v }
        }
        Aide {
            text: qsTr("Coupe toute ambiance décorative (portraits au repos, emblème) sans toucher au mouvement "
                       + "fonctionnel ni à l'activité observée. Raccourci : Ctrl+Maj+F.")
        }

        Titre { text: qsTr("Lecture") }
        RowLayout {
            spacing: Space.space6
            ColumnLayout {
                Aide { text: qsTr("Densité") }
                Choix {
                    nom: qsTr("Densité")
                    options: Space.densities.map(d => ({ "valeur": d, "libelle": Space.densityLabels[d] }))
                    valeur: Appearance.density
                    onChoisi: function(v) { Appearance.density = v }
                }
            }
            ColumnLayout {
                Aide { text: qsTr("Taille du texte") }
                Choix {
                    nom: qsTr("Taille du texte")
                    options: Type.textScales.map(t => ({ "valeur": t, "libelle": t + " %" }))
                    valeur: Appearance.textScale
                    onChoisi: function(v) { Appearance.textScale = v }
                }
            }
        }

        // --- Aperçu ------------------------------------------------------------------------
        Titre { text: qsTr("Aperçu") }
        Carte {
            objectName: "apparence-apercu"
            Layout.fillWidth: true
            titre: qsTr("Mission d'exemple (aperçu, aucune donnée)")
            cle: "running"
            libelleEtat: qsTr("Exécute")
            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space5
                PortraitAgent { role: "developpeur"; etat: "travail"; echelle: 4; description: qsTr("Portrait d'aperçu : développeur au travail") }
                PortraitAgent { role: "relecteur"; etat: "attente"; echelle: 4; description: qsTr("Portrait d'aperçu : relecteur en attente") }
                PortraitAgent { role: "coordinateur"; etat: "repos"; echelle: 4; description: qsTr("Portrait d'aperçu : coordinateur au repos") }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space3
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Texte courant : la lecture reste en police système, le pixel ne sert qu'aux libellés courts.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textPrimary
                        font.family: Type.prose.family
                        font.pixelSize: Type.prose.pixelSize
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: code.implicitHeight + Space.space4 * 2
                        color: Colors.surfaceSunken
                        Text {
                            id: code
                            anchors.fill: parent
                            anchors.margins: Space.space4
                            text: "git diff --stat  ·  3 fichiers, +42 −7"
                            textFormat: Text.PlainText
                            color: Colors.textSecondary
                            font.family: Type.logLine.family
                            font.pixelSize: Type.logLine.pixelSize
                        }
                    }
                    RowLayout {
                        spacing: Space.space3
                        AcpButton { label: qsTr("Action principale"); primary: true }
                        AcpButton { label: qsTr("Action secondaire") }
                        StatusChip { statusKey: "failed"; label: qsTr("Échec") }
                        StatusChip { statusKey: "approvalRequired"; label: qsTr("Décision attendue") }
                    }
                }
            }
        }

        AcpButton {
            objectName: "apparence-retablir-disposition"
            label: qsTr("Rétablir la disposition par défaut des panneaux")
            commandId: "shell.resetLayout"
        }
        Item { Layout.preferredHeight: Space.space8 }
    }
}
