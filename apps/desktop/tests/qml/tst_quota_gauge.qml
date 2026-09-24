// Jauge de quota : un reste inconnu n'est jamais dessiné comme zéro, et la couleur n'est
// jamais seule porteuse d'information.

import QtQuick
import QtTest
import Acp.Design
import Acp.Components

TestCase {
    id: testCase
    name: "QuotaGauge"
    when: windowShown
    // TestCase est invisible par défaut : la visibilité de la barre ne serait pas éprouvée.
    visible: true
    width: 420
    height: 200

    Component {
        id: gaugeComponent
        QuotaGauge { width: 320 }
    }

    function fillOf(gauge) { return findChild(gauge, "quotaGaugeFill"); }
    function trackOf(gauge) { return findChild(gauge, "quotaGaugeTrack"); }

    function test_known_share_fills_the_remaining_part() {
        const gauge = createTemporaryObject(gaugeComponent, testCase, {
            label: "Fenêtre 5 h", remainingPercent: 58, remainingText: "58 %",
            usedText: "42 %", resetText: "aujourd'hui à 14:00",
            countdownText: "dans 3 h 57", level: "normal"
        });
        verify(gauge !== null);
        verify(gauge.known);
        const fill = fillOf(gauge);
        verify(fill.visible);
        fuzzyCompare(fill.width, trackOf(gauge).width * 0.58, 0.5);
        compare(gauge.Accessible.role, Accessible.ProgressBar);
        verify(gauge.Accessible.name.indexOf("Fenêtre 5 h") === 0);
        verify(gauge.Accessible.name.indexOf("58 % restant") >= 0);
        verify(gauge.Accessible.name.indexOf("42 % utilisé") >= 0);
        verify(gauge.Accessible.name.indexOf("aujourd'hui à 14:00 (dans 3 h 57)") >= 0);
    }

    function test_unknown_share_is_never_drawn_as_zero() {
        const gauge = createTemporaryObject(gaugeComponent, testCase, {
            label: "Semaine", remainingPercent: null, level: "unknown"
        });
        verify(!gauge.known);
        verify(!fillOf(gauge).visible);
        // Défauts du composant : « Inconnu » partout, jamais 0 %.
        compare(gauge.remainingText, "Inconnu");
        compare(gauge.resetText, "Inconnu");
        verify(gauge.Accessible.name.indexOf("reste Inconnu") >= 0);
        verify(gauge.Accessible.name.indexOf("0 %") < 0);
    }

    function test_level_colour_accompanies_the_text_data() {
        return [
            { tag: "critical", level: "critical", remaining: 5 },
            { tag: "warning", level: "warning", remaining: 20 },
            { tag: "normal", level: "normal", remaining: 80 }
        ];
    }

    function test_level_colour_accompanies_the_text(data) {
        const gauge = createTemporaryObject(gaugeComponent, testCase, {
            label: "Fenêtre 5 h", remainingPercent: data.remaining,
            remainingText: data.remaining + " %", level: data.level
        });
        const expected = data.level === "critical" ? Status.statusFailedForeground
            : data.level === "warning" ? Status.statusDegradedForeground
            : Status.statusSucceededForeground;
        compare(Qt.colorEqual(fillOf(gauge).color, expected), true);
        verify(gauge.Accessible.name.indexOf(data.remaining + " % restant") >= 0);
    }

    function test_out_of_range_values_are_clamped_for_drawing() {
        const full = createTemporaryObject(gaugeComponent, testCase, { remainingPercent: 140 });
        fuzzyCompare(fillOf(full).width, trackOf(full).width, 0.5);
        const empty = createTemporaryObject(gaugeComponent, testCase, { remainingPercent: 0 });
        verify(empty.known);
        verify(!fillOf(empty).visible);
    }
}
