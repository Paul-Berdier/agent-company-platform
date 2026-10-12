// Résultats rapportés par l'exécutant pour un run vérifié ; aucun journal ni diff inventé.
import QtQuick
import QtQuick.Layouts
import Acp.Design

ColumnLayout {
    id: root
    objectName: "execution-details"
    property var execution: ({})
    readonly property var observation: execution || ({})
    readonly property bool observed: observation.etat === "observe"
    readonly property var details: observation.metadonnees || ({})
    readonly property var verification: details.verification || ({})
    readonly property var tokens: details.jetons || ({})
    readonly property var changes: details.diffstat || ({})
    spacing: Space.space3

    function value(v, absent) {
        return v !== undefined && v !== null && String(v).length > 0 ? String(v) : (absent || "Non observé")
    }
    function date(v) {
        return typeof v === "number" ? Qt.formatDateTime(new Date(v * 1000), "dd/MM/yyyy HH:mm:ss") : "Non observée"
    }
    function verificationText() {
        const labels = { "reussie": "Réussie", "echouee": "Échouée", "non_executee": "Non exécutée" }
        let text = labels[verification.etat] || "Non rapportée"
        if (verification.tentatives !== undefined) text += " · " + verification.tentatives + " tentative(s)"
        if (verification.code !== undefined && verification.code !== null) text += " · code " + verification.code
        if (verification.duree_s !== undefined && verification.duree_s !== null) text += " · " + verification.duree_s + " s"
        if (verification.raison) text += "\n" + verification.raison
        return text
    }

    Text {
        Layout.fillWidth: true
        text: root.observed ? (root.observation.portee === "courante" ? "Exécution courante" : "Dernière exécution") : "Exécution"
        textFormat: Text.PlainText
        color: Colors.textPrimary
        font.family: Type.panelTitle.family
        font.pixelSize: Type.panelTitle.pixelSize
        font.weight: Type.panelTitle.weight
        wrapMode: Text.Wrap
    }
    BlocTexte {
        Layout.fillWidth: true
        visible: !root.observed
        texte: root.observation.etat === "aucune" ? "Aucune exécution enregistrée pour cette carte."
             : root.observation.etat === "non_pris_en_charge" ? "Cette voie ne rapporte pas encore de résultats détaillés d’exécution."
             : "L’observation de cette exécution est indisponible."
    }
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.observed
        spacing: Space.space3
        StatusChip {
            objectName: "execution-statut"
            statusKey: root.observation.statut === "running" ? "running"
                     : root.observation.statut === "scheduled" ? "pending"
                     : root.observation.statut === "done" ? "succeeded"
                     : root.observation.statut === "review" ? "approvalRequired"
                     : root.observation.statut === "blocked" ? "blocked" : "unknown"
            label: root.observation.statut === "running" ? "En cours"
                 : root.observation.statut === "scheduled" ? "En attente"
                 : root.observation.statut === "done" ? "Terminée"
                 : root.observation.statut === "review" ? "En revue"
                 : root.observation.statut === "blocked" ? "Bloquée"
                 : root.observation.fin !== null && root.observation.fin !== undefined ? "Arrêtée" : "État inconnu"
        }
        BlocTexte {
            Layout.fillWidth: true
            texte: "Exécution #" + root.value(root.observation.run_id) + " · machine " + root.value(root.observation.machine_id)
            monospace: true
        }
        BlocTexte {
            Layout.fillWidth: true
            libelle: "Historique enregistré par Hermes"
            texte: "Début : " + root.date(root.observation.debut)
                 + (root.observation.fin !== null && root.observation.fin !== undefined ? "\nFin : " + root.date(root.observation.fin) : "")
        }
        BlocTexte {
            Layout.fillWidth: true
            visible: !root.observation.metadonnees
            texte: root.observation.motif_metadonnees === "invalides"
                ? "Les résultats de cette exécution ne peuvent pas être validés."
                : "Aucun résultat détaillé n’a été rapporté pour cette exécution."
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: !!root.observation.metadonnees
            spacing: Space.space3
            BlocTexte {
                Layout.fillWidth: true
                objectName: "execution-verification"
                libelle: "Vérification rapportée par l’exécutant"
                texte: root.verificationText()
            }
            GridLayout {
                Layout.fillWidth: true
                columns: width >= 480 ? 2 : 1
                columnSpacing: Space.space4
                rowSpacing: Space.space3
                BlocTexte { Layout.fillWidth: true; libelle: "Modèle demandé"; texte: root.value(root.details.modele_demande); monospace: true }
                BlocTexte { Layout.fillWidth: true; libelle: "Modèle observé"; texte: root.value(root.details.modele_servi); monospace: true }
                BlocTexte { Layout.fillWidth: true; libelle: "Effort demandé"; texte: root.value(root.details.effort); monospace: true }
                BlocTexte { Layout.fillWidth: true; libelle: "Palier demandé / observé"; texte: root.value(root.details.palier_demande) + " / " + root.value(root.details.palier_servi); monospace: true }
            }
            BlocTexte { Layout.fillWidth: true; libelle: "Branche locale"; texte: root.value(root.details.branche); monospace: true }
            BlocTexte { Layout.fillWidth: true; libelle: "Commit final"; texte: root.value(root.details.tete); monospace: true }
            BlocTexte { Layout.fillWidth: true; libelle: "Commit de base"; texte: root.value(root.details.base); monospace: true }
            BlocTexte {
                Layout.fillWidth: true
                objectName: "execution-diffstat"
                libelle: "Résumé chiffré des changements"
                texte: root.details.diffstat ? root.value(root.changes.fichiers) + " fichier(s) · " + root.value(root.changes.ajouts)
                    + " ligne(s) ajoutée(s) · " + root.value(root.changes.retraits) + " retirée(s)" : "Non rapporté"
            }
            BlocTexte {
                Layout.fillWidth: true
                libelle: "Jetons rapportés"
                texte: "Entrée : " + root.value(root.tokens.entree) + " · sortie : " + root.value(root.tokens.sortie)
                    + " · cache : " + root.value(root.tokens.cache)
            }
            BlocTexte {
                Layout.fillWidth: true
                visible: !!root.details.pilotage && root.details.pilotage.touche === true
                libelle: "Fichiers de pilotage touchés"
                texte: root.details.pilotage && Array.isArray(root.details.pilotage.chemins) ? root.details.pilotage.chemins.join("\n") : "Non rapportés"
                monospace: true
            }
        }
    }
}
