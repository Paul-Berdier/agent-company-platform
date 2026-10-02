// Jauge de quota : la barre dit la part UTILISÉE, avec un repère au seuil du routage (même sens
// que la page web) ; une part inconnue n'est jamais dessinée comme zéro, et la couleur n'est
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
    function thresholdOf(gauge) { return findChild(gauge, "quotaGaugeThreshold"); }

    // Constat de relecture P8 : la barre du bureau se remplissait de la part RESTANTE, celle
    // du web de la part UTILISÉE ; elle suit désormais le web, avec le repère du seuil.
    function test_known_share_fills_the_used_part() {
        const gauge = createTemporaryObject(gaugeComponent, testCase, {
            label: "Fenêtre 5 h", usedPercent: 42, thresholdPercent: 90, remainingText: "58 %",
            usedText: "42 %", resetText: "aujourd'hui à 14:00",
            countdownText: "dans 3 h 57", level: "normal"
        });
        verify(gauge !== null);
        verify(gauge.known);
        const fill = fillOf(gauge);
        verify(fill.visible);
        fuzzyCompare(fill.width, trackOf(gauge).width * 0.42, 0.5);
        const seuil = thresholdOf(gauge);
        verify(seuil.visible);
        fuzzyCompare(seuil.x + seuil.width / 2, trackOf(gauge).width * 0.90, 1);
        compare(gauge.Accessible.role, Accessible.ProgressBar);
        verify(gauge.Accessible.name.indexOf("Fenêtre 5 h") === 0);
        verify(gauge.Accessible.name.indexOf("42 % utilisé") >= 0);
        verify(gauge.Accessible.name.indexOf("58 % restant") >= 0);
        verify(gauge.Accessible.name.indexOf("aujourd'hui à 14:00 (dans 3 h 57)") >= 0);
    }

    function test_unknown_share_is_never_drawn_as_zero() {
        const gauge = createTemporaryObject(gaugeComponent, testCase, {
            label: "Semaine", usedPercent: null, level: "unknown"
        });
        verify(!gauge.known);
        verify(!fillOf(gauge).visible);
        // Sans seuil connu, aucun repère.
        verify(!thresholdOf(gauge).visible);
        // Défauts du composant : « Inconnu » partout, jamais 0 %.
        compare(gauge.remainingText, "Inconnu");
        compare(gauge.resetText, "Inconnu");
        verify(gauge.Accessible.name.indexOf("part utilisée Inconnue") >= 0);
        verify(gauge.Accessible.name.indexOf("0 %") < 0);
    }

    function test_level_colour_accompanies_the_text_data() {
        return [
            { tag: "critical", level: "critical", used: 95 },
            { tag: "warning", level: "warning", used: 80 },
            { tag: "normal", level: "normal", used: 20 }
        ];
    }

    function test_level_colour_accompanies_the_text(data) {
        const gauge = createTemporaryObject(gaugeComponent, testCase, {
            label: "Fenêtre 5 h", usedPercent: data.used,
            usedText: data.used + " %", level: data.level
        });
        const expected = data.level === "critical" ? Status.statusFailedForeground
            : data.level === "warning" ? Status.statusDegradedForeground
            : Status.statusSucceededForeground;
        compare(Qt.colorEqual(fillOf(gauge).color, expected), true);
        verify(gauge.Accessible.name.indexOf(data.used + " % utilisé") >= 0);
    }

    function test_out_of_range_values_are_clamped_for_drawing() {
        const full = createTemporaryObject(gaugeComponent, testCase, { usedPercent: 140, thresholdPercent: 150 });
        fuzzyCompare(fillOf(full).width, trackOf(full).width, 0.5);
        verify(thresholdOf(full).x + thresholdOf(full).width <= trackOf(full).width + 0.5);
        const empty = createTemporaryObject(gaugeComponent, testCase, { usedPercent: 0 });
        verify(empty.known);
        verify(!fillOf(empty).visible);
    }
}
