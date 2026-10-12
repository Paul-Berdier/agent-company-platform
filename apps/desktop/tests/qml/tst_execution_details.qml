// Un run replanifié attend une suite ; sa date de fin ne prouve pas un succès.
import QtQuick
import QtTest
import Acp.Components

TestCase {
    id: testCase
    name: "ExecutionDetails"
    when: windowShown
    width: 600
    height: 500

    Component {
        id: detailsComponent
        ExecutionDetails {}
    }

    function test_scheduled_is_pending_without_successful_result() {
        const details = createTemporaryObject(detailsComponent, testCase, {
            execution: {
                etat: "observe", portee: "derniere", run_id: 12,
                machine_id: "m0123456789a", statut: "scheduled", issue: "scheduled",
                debut: 1790451600, fin: 1790451700, metadonnees: null
            }
        })
        verify(details !== null)
        const chip = findChild(details, "execution-statut")
        verify(chip !== null)
        compare(chip.statusKey, "pending")
        compare(chip.effectiveLabel, "En attente")
        verify(!chip.meta.animated)
        compare(details.verificationText(), "Non rapportée")
    }
}
