// Pastille d'état : la couleur n'est jamais seule porteuse d'information.
//
// AVERTISSEMENT : jamais exécuté. Écrit pour l'intégration continue.

import QtQuick
import QtTest
import Acp.Design
import Acp.Components

TestCase {
    id: testCase
    name: "StatusChip"
    when: windowShown
    width: 400
    height: 200

    Component {
        id: chipComponent
        StatusChip {}
    }

    function test_unknown_state_is_the_default() {
        const chip = createTemporaryObject(chipComponent, testCase);
        verify(chip !== null);
        compare(chip.statusKey, "unknown");
        compare(chip.effectiveLabel, "Inconnu");
    }

    function test_unrecognised_key_falls_back_to_unknown() {
        const chip = createTemporaryObject(chipComponent, testCase,
                                           { statusKey: "état-qui-n-existe-pas" });
        // Un état inconnu du client ne produit ni plantage ni couleur au hasard.
        compare(chip.effectiveLabel, "Inconnu");
        compare(chip.meta.key, "unknown");
    }

    function test_every_state_carries_a_french_label_and_ascii_fallback_data() {
        return [
            { tag: "unknown", key: "unknown", label: "Inconnu" },
            { tag: "notConfigured", key: "notConfigured", label: "Non configuré" },
            { tag: "offline", key: "offline", label: "Hors ligne" },
            { tag: "pending", key: "pending", label: "En attente" },
            { tag: "running", key: "running", label: "En cours" },
            { tag: "blocked", key: "blocked", label: "Bloqué" },
            { tag: "failed", key: "failed", label: "En échec" },
            { tag: "succeeded", key: "succeeded", label: "Réussi" },
            { tag: "degraded", key: "degraded", label: "Dégradé" },
            { tag: "approvalRequired", key: "approvalRequired", label: "Approbation requise" }
        ];
    }

    function test_every_state_carries_a_french_label_and_ascii_fallback(data) {
        const chip = createTemporaryObject(chipComponent, testCase, { statusKey: data.key });
        compare(chip.effectiveLabel, data.label);
        verify(chip.meta.asciiFallback.length > 0,
               "chaque état doit porter un repli ASCII : la couleur ne suffit pas");
        verify(chip.Accessible.name.indexOf(data.label) >= 0);
    }

    function test_only_running_is_animated() {
        const running = createTemporaryObject(chipComponent, testCase, { statusKey: "running" });
        verify(running.meta.animated);
        const succeeded = createTemporaryObject(chipComponent, testCase,
                                                { statusKey: "succeeded" });
        verify(!succeeded.meta.animated);
    }

    function test_states_without_measurement_use_a_dashed_border_data() {
        return [
            { tag: "unknown", key: "unknown" },
            { tag: "notConfigured", key: "notConfigured" },
            { tag: "offline", key: "offline" }
        ];
    }

    function test_states_without_measurement_use_a_dashed_border(data) {
        const chip = createTemporaryObject(chipComponent, testCase, { statusKey: data.key });
        // Trois états se distinguent SANS la couleur : c'est une exigence de la direction.
        verify(chip.meta.dashedBorder);
        verify(chip.meta.neverFilled);
    }

    function test_explicit_label_overrides_token_label() {
        const chip = createTemporaryObject(chipComponent, testCase,
                                           { statusKey: "running", label: "Préparation" });
        compare(chip.effectiveLabel, "Préparation");
    }
}
