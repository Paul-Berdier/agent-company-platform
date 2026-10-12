// Page Poste (cahier P8 § 7.5) : état du poste Windows, enrôlement, confirmation de
// l'empreinte, révocation, relevé, dernier inventaire et ordres en attente ; exécutant Railway
// seulement si le serveur le publie. Tout vient de `GET /v1/poste` ; aucun bouton n'agit sans
// appel, et chaque résultat est celui que le greffon a rendu.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    property bool diagnosticsOuverts: false
    property bool resultatsDeveloppes: false

    Component.onCompleted: Poste.pageVisible = visible
    onVisibleChanged: Poste.pageVisible = visible
    Component.onDestruction: Poste.pageVisible = false

    Connections {
        target: Poste
        function onGuideChange() {
            if ((Poste.guide.titre || "").length > 0)
                Qt.callLater(function() { defilement.contentItem.contentY = Math.max(0, guideCarte.y - Space.space4); });
        }
    }

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
                    text: qsTr("Assistants et machine")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton {
                    objectName: "poste-actualiser"
                    label: qsTr("Actualiser")
                    onTriggered: Poste.actualiser()
                }
            }

            Discret {
                text: qsTr("Connectez les outils qui travaillent sur vos projets, puis vérifiez ce que votre machine publie réellement.")
            }
            // Cadence RÉELLE (temps réel ou sondage), jamais écrite en dur (relecture de P8b, constat desktop-4).
            Discret {
                objectName: "poste-cadence"
                text: Poste.cadence
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Poste.lecture
                erreur: Poste.erreur
            }
            BandeauMessage {
                Layout.fillWidth: true
                message: Poste.messageGeste
                erreur: Poste.erreurGeste
            }
            Text {
                visible: !Poste.lue && Poste.erreur.length === 0
                text: qsTr("Chargement…")
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }

            // --- État ------------------------------------------------------------------------------
            Carte {
                objectName: "poste-etat"
                Layout.fillWidth: true
                visible: Poste.lue
                titre: Poste.machine.presente ? Poste.assistantMachine.nom : qsTr("Machine active")
                cle: Poste.etat.cle
                libelleEtat: Poste.etat.libelle
                Discret { visible: Poste.etat.detail.length > 0; text: Poste.etat.detail; color: Colors.textSecondary }
                BlocTexte { Layout.fillWidth: true; visible: Poste.etat.message.length > 0; texte: Poste.etat.message }
                Alerte {
                    visible: Poste.etat.politiqueInvalide
                    text: qsTr("Politique locale invalide : le poste reste joignable mais ne publie plus rien.")
                }
                Alerte {
                    visible: Poste.etat.pauseReclamations
                    text: qsTr("Pause générale : le poste n'exécutera rien.")
                }
                Ligne { label: qsTr("Environnement"); value: Poste.assistantMachine.type }
                Ligne { label: qsTr("Dernier relevé des assistants"); value: Poste.assistantMachine.releve }
                Ligne { label: qsTr("Cartes du poste en attente"); value: Poste.etat.cartesEnAttente }
                Discret { text: qsTr("Une seule machine active est prise en charge : un PC Windows ou un exécutant Linux/Railway. Se connecter sur votre PC ne connecte pas l'exécutant Railway.") }
            }

            // Trois identités distinctes : ACP, le coordinateur, puis les outils de la machine.
            GridLayout {
                Layout.fillWidth: true
                columns: page.width >= 900 ? 2 : 1
                columnSpacing: Space.space4
                rowSpacing: Space.space4
                Carte {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Votre accès ACP")
                    sousTitre: qsTr("L'identité qui vous permet d'ouvrir ce workspace et de piloter Hermes.")
                    Discret { text: qsTr("Elle est indépendante de vos comptes ChatGPT et Claude Code. Les réglages de connexion ACP ne changent pas les comptes de la machine.") }
                    AcpButton { label: qsTr("Réglages ACP"); onTriggered: Navigation.setCurrentRoute("settings") }
                }
                Carte {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Hermes · coordinateur")
                    sousTitre: qsTr("Son compte fournisseur et son modèle se configurent dans votre tableau de bord Hermes.")
                    Discret { text: qsTr("L'état de ce compte n'est pas publié par l'inventaire de la machine. Le catalogue des exécutants ne décrit pas le modèle du coordinateur.") }
                    AcpButton { objectName: "assistants-guide-hermes"; label: qsTr("Configurer Hermes"); onTriggered: Poste.ouvrirGuide("hermes") }
                }
            }

            SectionHeader { Layout.fillWidth: true; title: qsTr("Sur votre machine d'exécution") }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width >= 900 ? 2 : 1
                columnSpacing: Space.space4
                rowSpacing: Space.space4
                Repeater {
                    model: Poste.assistants
                    delegate: Carte {
                        required property var modelData
                        objectName: "assistant-" + modelData.fournisseur
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        titre: modelData.nom
                        cle: modelData.cle
                        libelleEtat: modelData.etat
                        Ligne { label: qsTr("Mode observé"); value: modelData.mode }
                        Ligne { label: qsTr("Version lue"); value: modelData.version; monospace: true }
                        Ligne { label: qsTr("Offre observée"); value: modelData.offre }
                        Discret { text: modelData.detail }
                        AcpButton {
                            objectName: "assistants-guide-" + modelData.fournisseur
                            label: qsTr("Configurer / reconnecter")
                            manualEnabled: Poste.assistantMachine.guideDisponible === true
                            onTriggered: Poste.ouvrirGuide(modelData.fournisseur)
                        }
                    }
                }
            }
            Discret {
                visible: !Poste.assistantMachine.guideDisponible
                text: qsTr("Le guide de connexion devient disponible quand une machine active et sa plateforme sont connues. Enrôlez-la ou actualisez son état.")
            }

            Carte {
                objectName: "poste-releve"
                Layout.fillWidth: true
                visible: Poste.lue && Poste.peutRelever
                titre: qsTr("Vérifier les connexions")
                sousTitre: qsTr("Après la configuration, demandez un relevé. Un compte reconnu et une voie d'exécution disponible sont deux états distincts.")
                Discret {
                    objectName: "assistants-verification"
                    visible: Poste.verificationMessage.length > 0
                    text: Poste.verificationMessage
                    color: Poste.verificationEtat === "echec" || Poste.verificationEtat === "retard"
                           || Poste.verificationEtat === "interrompue" ? Status.statusDegradedForeground : Colors.textSecondary
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Space.space3
                    AcpButton {
                        objectName: "poste-relever"
                        label: Poste.verificationEnCours ? qsTr("Vérification en attente…") : qsTr("Vérifier maintenant")
                        primary: true
                        manualEnabled: !Poste.gesteEnCours && !Poste.verificationEnCours
                        onTriggered: Poste.relever()
                    }
                    AcpButton { label: qsTr("Quotas et limites"); onTriggered: Navigation.setCurrentRoute("quotas") }
                    AcpButton { label: qsTr("Modèles d'exécution"); onTriggered: Navigation.setCurrentRoute("routing") }
                }
            }

            Carte {
                objectName: "poste-resultats"
                Layout.fillWidth: true
                visible: Poste.lue
                titre: qsTr("Résultats à récupérer")
                sousTitre: qsTr("Branches signalées terminées par Hermes. Leur présence sur l'exécutant est contrôlée lors de la génération du bundle.")
                Discret {
                    objectName: "poste-resultats-message"
                    visible: Poste.resultatsMessage.length > 0
                    text: Poste.resultatsMessage
                }
                Repeater {
                    model: Poste.resultats
                    delegate: ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        visible: index < 3 || page.resultatsDeveloppes
                        spacing: Space.space2
                        SectionHeader { Layout.fillWidth: true; title: modelData.titre; subtitle: qsTr("Dépôt %1 · terminé le %2").arg(modelData.depot).arg(modelData.termineLe) }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Branche locale"); texte: modelData.branche; monospace: true }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Commit attendu"); texte: modelData.tete; monospace: true }
                        AcpButton {
                            objectName: "poste-recuperer-resultat-" + index
                            label: qsTr("Préparer la récupération")
                            manualEnabled: Poste.erreur.length === 0
                            onTriggered: Poste.ouvrirGuideRecuperation(modelData.projet, modelData.branche, modelData.tete)
                        }
                        Item { Layout.preferredHeight: Space.space3 }
                    }
                }
                AcpButton {
                    objectName: "poste-resultats-tous"
                    visible: Poste.resultats.length > 3
                    label: page.resultatsDeveloppes ? qsTr("Réduire la liste") : qsTr("Afficher les %1 résultats").arg(Poste.resultats.length)
                    onTriggered: page.resultatsDeveloppes = !page.resultatsDeveloppes
                }
            }

            Carte {
                id: guideCarte
                objectName: "assistants-guide"
                Layout.fillWidth: true
                visible: (Poste.guide.titre || "").length > 0
                titre: Poste.guide.titre || ""
                sousTitre: qsTr("Ces étapes se font dans vos consoles. Copier une commande ne l'exécute pas. Aucun jeton n'est demandé dans cette page.")
                Repeater {
                    model: Poste.guide.etapes || []
                    delegate: ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: Space.space2
                        SectionHeader { Layout.fillWidth: true; title: (index + 1) + ". " + modelData.titre }
                        Discret { text: modelData.texte; color: Colors.textSecondary }
                        BlocTexte { Layout.fillWidth: true; visible: modelData.commande.length > 0; texte: modelData.commande; monospace: true }
                        AcpButton {
                            visible: modelData.commande.length > 0
                            objectName: "assistants-copier-etape-" + index
                            label: modelData.aCompleter === true ? qsTr("Copier la commande à compléter") : qsTr("Copier la commande")
                            onTriggered: Poste.copierEtape(index)
                        }
                        Item { Layout.preferredHeight: Space.space2 }
                    }
                }
                Discret { visible: Poste.copieGuide.length > 0; text: Poste.copieGuide }
                AcpButton { objectName: "assistants-fermer-guide"; label: qsTr("Fermer le guide"); onTriggered: Poste.fermerGuide() }
            }
            // --- Enrôlement ----------------------------------------------------------------------------
            Carte {
                objectName: "poste-enroler"
                Layout.fillWidth: true
                visible: Poste.lue && Poste.peutEnroler
                titre: qsTr("Enrôler un poste")
                sousTitre: qsTr("Génère un code à usage unique, valable 10 minutes, à coller dans la commande "
                                + "d'enrôlement ci-dessous, lancée dans la console du compte du poste. Le jeton du "
                                + "poste n'est jamais affiché.")
                AcpButton {
                    objectName: "poste-generer-code"
                    primary: true
                    label: qsTr("Générer un code d'enrôlement")
                    manualEnabled: !Poste.gesteEnCours
                    onTriggered: Poste.enroler()
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Poste.code.length > 0
                    spacing: Space.space2
                    Discret { text: qsTr("Code d'enrôlement") }
                    TextEdit {
                        objectName: "poste-code"
                        Layout.fillWidth: true
                        readOnly: true
                        selectByMouse: true
                        text: Poste.code
                        textFormat: TextEdit.PlainText
                        color: Colors.textPrimary
                        font.family: Type.identifier.family
                        font.pixelSize: Type.pageTitle.pixelSize
                        Accessible.name: qsTr("Code d'enrôlement")
                    }
                    Discret { text: qsTr("Ce code ne s'affiche qu'une fois : il disparaît quand vous quittez la page.") }
                    RowLayout {
                        spacing: Space.space4
                        AcpButton {
                            objectName: "poste-copier-code"
                            label: qsTr("Copier le code")
                            onTriggered: Poste.copierCode()
                        }
                        Discret { visible: Poste.messageCopie.length > 0; text: Poste.messageCopie }
                    }
                    BlocTexte {
                        Layout.fillWidth: true
                        libelle: qsTr("Commande à lancer sur le poste")
                        texte: Poste.commande
                        monospace: true
                    }
                    Ligne {
                        label: qsTr("Expire dans")
                        value: Poste.secondesRestantes < 0 ? qsTr("Inconnu") : qsTr("%1 s").arg(Poste.secondesRestantes)
                    }
                }
                Alerte { visible: Poste.codeExpire; text: qsTr("Code expiré : générez-en un nouveau.") }
            }

            // --- Confirmation de l'empreinte -----------------------------------------------------------------
            Carte {
                objectName: "poste-confirmation"
                Layout.fillWidth: true
                visible: Poste.lue && Poste.peutConfirmer
                titre: qsTr("Confirmer le poste")
                Ligne { label: qsTr("Empreinte annoncée par le poste"); value: Poste.machine.empreinte; monospace: true }
                Ligne { label: qsTr("Nom"); value: Poste.machine.nom }
                Discret {
                    text: qsTr("Comparez-la à celle qu'affiche la commande d'enrôlement sur le poste, puis recopiez-la. "
                               + "Si elles diffèrent, révoquez ce poste.")
                }
                AcpTextField {
                    id: empreinte
                    objectName: "poste-empreinte"
                    Layout.fillWidth: true
                    placeholder: qsTr("Empreinte affichée par le poste")
                }
                AcpButton {
                    objectName: "poste-confirmer"
                    primary: true
                    label: qsTr("Confirmer le poste")
                    manualEnabled: empreinte.text.trim().length > 0 && !Poste.gesteEnCours
                    onTriggered: Poste.confirmer(empreinte.text)
                }
            }

            AcpButton {
                objectName: "poste-diagnostics-basculer"
                label: page.diagnosticsOuverts ? qsTr("Masquer les diagnostics avancés") : qsTr("Diagnostics avancés et enrôlement")
                onTriggered: page.diagnosticsOuverts = !page.diagnosticsOuverts
            }
            // --- Poste enrôlé ---------------------------------------------------------------------------
            Carte {
                objectName: "poste-machine"
                Layout.fillWidth: true
                visible: page.diagnosticsOuverts && Poste.lue && Poste.machine.presente
                titre: qsTr("Poste enrôlé")
                Ligne { label: qsTr("Nom"); value: Poste.machine.nom }
                Ligne { label: qsTr("Empreinte"); value: Poste.machine.empreinte; monospace: true }
                Ligne { label: qsTr("Version du poste"); value: Poste.machine.versionPoste; monospace: true }
                Ligne { label: qsTr("Protocole"); value: Poste.machine.protocole; monospace: true }
                Ligne { label: qsTr("Enrôlé"); value: Poste.machine.enroleLe }
                Ligne { label: qsTr("Confirmé"); value: Poste.machine.confirmeLe }
                Ligne { label: qsTr("Dernier échange"); value: Poste.machine.derniereRequete }
            }

            // --- Alertes et ordres ---------------------------------------------------------------------------
            Carte {
                Layout.fillWidth: true
                visible: Poste.lue && Poste.alertes.length > 0
                titre: qsTr("Alertes du dernier inventaire")
                BlocTexte { Layout.fillWidth: true; texte: Poste.alertes.join("\n") }
            }
            Carte {
                objectName: "poste-ordres"
                Layout.fillWidth: true
                visible: page.diagnosticsOuverts && Poste.lue && Poste.peutRelever
                titre: qsTr("Ordres en attente")
                Discret { visible: Poste.ordres.count === 0; text: qsTr("Aucun ordre en attente.") }
                Repeater {
                    model: Poste.ordres
                    delegate: KeyValueRow {
                        required property var item
                        Layout.fillWidth: true
                        label: item.genre
                        value: qsTr("%1 · %2").arg(item.creeLe).arg(item.livraison)
                    }
                }
            }

            // --- Dernier inventaire -------------------------------------------------------------------------
            Carte {
                objectName: "poste-inventaire"
                Layout.fillWidth: true
                visible: page.diagnosticsOuverts && Poste.lue
                titre: qsTr("Dernier inventaire")
                Discret { visible: !Poste.inventaire.present; text: qsTr("Aucun inventaire reçu.") }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Poste.inventaire.present === true
                    spacing: Space.space2
                    Ligne { label: qsTr("Reçu"); value: Poste.inventaire.recuLe || "" }
                    Ligne { label: qsTr("Relevé"); value: Poste.inventaire.releveLe || "" }
                    Ligne { label: qsTr("Version du poste"); value: Poste.inventaire.versionPoste || ""; monospace: true }
                    SectionHeader { Layout.fillWidth: true; title: qsTr("Compte d'exécution") }
                    Ligne { label: qsTr("Compte"); value: Poste.inventaire.compte || "" }
                    Ligne { label: Poste.assistantMachine.plateforme === "linux" ? qsTr("Noyau Linux") : qsTr("Windows"); value: Poste.assistantMachine.plateforme === "linux" ? (Poste.inventaire.noyau || qsTr("Inconnu")) : (Poste.inventaire.windows || ""); monospace: true }
                    Ligne { label: qsTr("Python"); value: Poste.inventaire.python || ""; monospace: true }
                    Ligne { label: qsTr("Empreinte de poste.toml"); value: Poste.inventaire.empreintePolitique || ""; monospace: true }
                    SectionHeader { Layout.fillWidth: true; title: qsTr("Versions des CLI") }
                    Repeater {
                        model: Poste.inventaire.versions || []
                        delegate: KeyValueRow {
                            required property var modelData
                            Layout.fillWidth: true
                            label: modelData.nom
                            value: qsTr("Lue %1 · testée %2 · conforme : %3").arg(modelData.lue).arg(modelData.testee)
                                .arg(modelData.conforme)
                        }
                    }
                    SectionHeader { Layout.fillWidth: true; title: qsTr("Bac à sable Codex") }
                    Ligne { label: qsTr("État de préparation"); value: Poste.inventaire.readiness || ""; monospace: true }
                    Ligne { label: qsTr("Mode lu"); value: Poste.inventaire.modeLu || ""; monospace: true }
                    Ligne { label: qsTr("Origine du mode"); value: Poste.inventaire.origineMode || ""; monospace: true }
                    Ligne { label: qsTr("Palier lu"); value: Poste.inventaire.palierLu || ""; monospace: true }
                    Ligne { label: qsTr("Stockage des identifiants"); value: Poste.inventaire.stockage || ""; monospace: true }
                    Ligne { label: qsTr("Écriture admise"); value: Poste.inventaire.ecritureAdmise || "" }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: (Poste.inventaire.raison || "").length > 0
                        libelle: qsTr("Raison")
                        texte: Poste.inventaire.raison || ""
                    }
                    SectionHeader { Layout.fillWidth: true; title: qsTr("Connexions") }
                    RowLayout {
                        Layout.fillWidth: true
                        Ligne { label: qsTr("Codex"); value: Poste.inventaire.offre ? qsTr("offre %1").arg(Poste.inventaire.offre) : "" }
                        StatusChip { statusKey: Poste.inventaire.codexCle || "unknown"; label: Poste.inventaire.codexLibelle || "" }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Ligne { label: qsTr("Claude Code"); value: "" }
                        StatusChip { statusKey: Poste.inventaire.claudeCle || "unknown"; label: Poste.inventaire.claudeLibelle || "" }
                    }
                    // Étape P7 (partie E) : visibilité MESURÉE de chaque dépôt et voies ouvertes ou fermées pour lui.
                    SectionHeader { Layout.fillWidth: true; title: qsTr("Dépôts autorisés") }
                    Discret {
                        text: qsTr("Visibilité mesurée par l'exécutant à chaque inventaire et avant chaque carte Codex. Privé "
                                   + "veut dire accès anonyme refusé et lecture avec le jeton réussie. Codex ne travaille que "
                                   + "sur un dépôt prouvé privé (D83), Claude sur tout dépôt (D84).")
                    }
                    Discret {
                        visible: Poste.depots.length === 0
                        text: qsTr("Aucun dépôt déclaré par le poste.")
                    }
                    Repeater {
                        model: Poste.depots
                        delegate: ColumnLayout {
                            id: depot
                            required property var modelData
                            objectName: "poste-depot-" + modelData.alias
                            Layout.fillWidth: true
                            spacing: Space.space1
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: depot.modelData.alias
                                    textFormat: Text.PlainText
                                    color: Colors.textPrimary
                                    font.family: Type.identifier.family
                                    font.pixelSize: Type.identifier.pixelSize
                                }
                                StatusChip { statusKey: depot.modelData.visibiliteCle; label: depot.modelData.visibilite }
                            }
                            Ligne { label: qsTr("Visibilité mesurée"); value: depot.modelData.visibilite }
                            Ligne { label: qsTr("Lecture par l'exécutant"); value: depot.modelData.lecture }
                            Ligne { label: qsTr("Mesurée"); value: depot.modelData.verifieLe }
                            BlocTexte { Layout.fillWidth: true; libelle: qsTr("Voies pour ce dépôt"); texte: depot.modelData.voies }
                        }
                    }
                }
            }

            // --- Exécutant Railway (étape P6) -----------------------------------------------------------------
            Carte {
                objectName: "poste-executant"
                visible: page.diagnosticsOuverts
                Layout.fillWidth: true
                titre: qsTr("Capacités de la machine active")
                Discret {
                    objectName: "poste-executant-etat"
                    visible: !Poste.executant.present
                    text: Poste.executant.message || ""
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: Poste.executant.present === true
                    spacing: Space.space2
                    Discret { text: qsTr("Lu de la description du greffon, en lecture seule.") }
                    Ligne { label: qsTr("Plateforme"); value: Poste.executant.plateforme || ""; monospace: true }
                    Ligne { label: qsTr("Hôte"); value: Poste.executant.hote || ""; monospace: true }
                    Ligne { label: qsTr("Régime d'isolement mesuré"); value: Poste.executant.regime || ""; monospace: true }
                    Ligne { label: qsTr("Peut exécuter"); value: Poste.executant.peutExecuter || "" }
                    Ligne { label: qsTr("Voies disponibles"); value: Poste.executant.voiesDisponibles || "" }
                    Ligne { label: qsTr("Voies fermées"); value: Poste.executant.voiesFermees || "" }
                    Ligne { label: qsTr("Carte en main"); value: Poste.executant.carteEnCours || "" }
                    Alerte {
                        visible: (Poste.executant.erreur || "").length > 0
                        text: qsTr("Lecture de l'exécutant impossible côté serveur : %1").arg(Poste.executant.erreur || "")
                    }
                }
            }

            // --- Révocation ----------------------------------------------------------------------------------
            Carte {
                objectName: "poste-revocation"
                Layout.fillWidth: true
                visible: page.diagnosticsOuverts && Poste.lue && Poste.peutRevoquer
                titre: qsTr("Révoquer le poste")
                sousTitre: qsTr("Le jeton du poste est refusé dès le prochain échange ; un nouvel enrôlement devient "
                                + "possible.")
                AcpButton {
                    objectName: "poste-revoquer"
                    label: qsTr("Révoquer")
                    manualEnabled: !Poste.gesteEnCours
                    onTriggered: confirmationRevocation.open()
                }
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }

    Dialog {
        id: confirmationRevocation
        objectName: "poste-revocation-confirmation"
        anchors.centerIn: parent
        modal: true
        title: qsTr("Révoquer ce poste ?")
        width: Math.min(page.width - Space.space8 * 2, 520)
        onOpened: motif.text = ""
        contentItem: ColumnLayout {
            spacing: Space.space4
            AcpTextField {
                id: motif
                Layout.fillWidth: true
                placeholder: qsTr("Motif (200 caractères au plus)")
                accessibleName: qsTr("Motif de la révocation")
            }
            RowLayout {
                spacing: Space.space4
                AcpButton {
                    objectName: "poste-revocation-confirmer"
                    primary: true
                    label: qsTr("Confirmer la révocation")
                    manualEnabled: motif.text.trim().length > 0
                    onTriggered: {
                        Poste.revoquer(motif.text);
                        confirmationRevocation.close();
                    }
                }
                AcpButton {
                    label: qsTr("Annuler")
                    onTriggered: confirmationRevocation.close()
                }
            }
        }
    }
}
