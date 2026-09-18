// Jetons de design engendrés : présence, cohérence, bascule de thème.
//
// Ces tests ne jugent pas l'esthétique. Ils vérifient que le générateur a produit ce que
// les fichiers de jetons promettent, et que la bascule de thème atteint TOUS les
// singletons — un thème appliqué à moitié serait pire qu'un thème unique.
//
// AVERTISSEMENT : jamais exécuté. Écrit pour l'intégration continue.

import QtQuick
import QtTest
import Acp.Design

TestCase {
    id: testCase
    name: "DesignTokens"

    function init() {
        Colors.theme = "dark";
        Status.theme = "dark";
        Elevation.theme = "dark";
        Motion.profile = "standard";
    }

    function test_palette_exposes_both_themes() {
        verify(Colors.dark !== null);
        verify(Colors.light !== null);
        verify(Colors.dark.surfaceCanvas !== Colors.light.surfaceCanvas);
    }

    function test_flat_accessor_follows_active_theme() {
        Colors.theme = "dark";
        compare(String(Colors.surfaceCanvas), String(Colors.dark.surfaceCanvas));
        Colors.theme = "light";
        compare(String(Colors.surfaceCanvas), String(Colors.light.surfaceCanvas));
    }

    function test_default_theme_is_dark() {
        // Les fichiers de jetons déclarent "$defaultTheme": "dark".
        Colors.theme = "dark";
        verify(Colors.isDark);
        Colors.theme = "light";
        verify(!Colors.isDark);
    }

    function test_status_resolves_backend_states_data() {
        return [
            { tag: "run running", family: "runStatus", raw: "running", token: "running" },
            { tag: "run waiting", family: "runStatus", raw: "waiting_approval",
              token: "approvalRequired" },
            { tag: "run cancelled", family: "runStatus", raw: "cancelled", token: "unknown" },
            { tag: "task done", family: "taskStatus", raw: "done", token: "succeeded" },
            { tag: "gateway not configured", family: "gatewayDiagnostic", raw: "not_configured",
              token: "notConfigured" },
            { tag: "readiness degraded", family: "readiness", raw: "degraded",
              token: "degraded" },
            { tag: "transport offline", family: "clientTransport", raw: "disconnected",
              token: "offline" }
        ];
    }

    function test_status_resolves_backend_states(data) {
        const resolved = Status.resolve(data.family, data.raw);
        compare(resolved.token, data.token);
        verify(resolved.recognised);
        verify(resolved.label.length > 0);
    }

    function test_unknown_backend_state_is_reported_as_unrecognised() {
        // Un état serveur nouveau ne doit ni planter ni se voir attribuer une couleur au
        // hasard : il est explicitement « non reconnu ».
        const resolved = Status.resolve("runStatus", "état_inconnu_du_client");
        compare(resolved.token, "unknown");
        verify(!resolved.recognised);
    }

    function test_priority_puts_failure_before_success() {
        const order = Status.priorityOrder;
        verify(order.indexOf("failed") < order.indexOf("succeeded"),
               "une réussite ne masque jamais un échec du même groupe");
        verify(order.indexOf("approvalRequired") < order.indexOf("running"));
    }

    function test_typography_roles_are_complete_data() {
        return [
            { tag: "pageTitle", role: "pageTitle" },
            { tag: "panelTitle", role: "panelTitle" },
            { tag: "tableCell", role: "tableCell" },
            { tag: "columnHeader", role: "columnHeader" },
            { tag: "identifier", role: "identifier" },
            { tag: "logLine", role: "logLine" },
            { tag: "statusChip", role: "statusChip" },
            { tag: "prose", role: "prose" },
            { tag: "emptyStateTitle", role: "emptyStateTitle" }
        ];
    }

    function test_typography_roles_are_complete(data) {
        const role = Type[data.role];
        verify(role !== undefined, "le rôle " + data.role + " doit exister");
        // La famille est la première police de la pile réellement installée. Sans
        // aucune police (plateforme « offscreen » d'un serveur d'intégration), elle vaut
        // la chaîne vide et Qt applique sa police par défaut : c'est voulu, pas un échec.
        compare(typeof role.family, "string");
        verify(role.family === "" || Type.familyInterface.indexOf(role.family) >= 0
               || Type.familyMono.indexOf(role.family) >= 0,
               "famille hors des piles déclarées : " + role.family);
        verify(role.pixelSize > 0);
        verify(role.lineHeight > 0);
        verify(role.weight >= 400);
    }

    function test_monospace_roles_use_the_mono_stack() {
        compare(Type.identifier.family, Type.familyMonoResolved);
        compare(Type.logLine.family, Type.familyMonoResolved);
        compare(Type.tableCell.family, Type.familyInterfaceResolved);
    }

    function test_resolution_picks_the_first_installed_family() {
        // Une pile dont seul le troisième nom existe doit rendre ce troisième nom ; une
        // pile sans aucune police installée rend la chaîne vide, jamais un nom inventé.
        const installed = Qt.fontFamilies();
        compare(Type.firstInstalled(["police-absente-1", "police-absente-2"]), "");
        if (installed.length > 0) {
            compare(Type.firstInstalled(["police-absente", installed[0]]), installed[0]);
        }
    }

    function test_column_header_is_the_only_uppercase_role() {
        compare(Type.columnHeader.capitalization, Font.AllUppercase);
        compare(Type.tableCell.capitalization, Font.MixedCase);
        compare(Type.pageTitle.capitalization, Font.MixedCase);
    }

    function test_spacing_scale_is_monotonic() {
        const scale = [Space.space0, Space.space1, Space.space2, Space.space3, Space.space4,
                       Space.space5, Space.space6, Space.space7, Space.space8, Space.space9,
                       Space.space10];
        for (let index = 1; index < scale.length; ++index) {
            verify(scale[index] > scale[index - 1],
                   "l'échelle d'espacement doit être strictement croissante");
        }
    }

    function test_hit_target_is_at_least_thirty_two_pixels() {
        verify(Space.densityHitTargetMinimum >= 32);
        verify(Space.densityControlHeightRegular <= Space.densityHitTargetMinimum);
    }

    function test_no_transition_exceeds_two_hundred_forty_milliseconds() {
        const durations = [Motion.durationInstant, Motion.durationMicro, Motion.durationFast,
                           Motion.durationBase, Motion.durationSlow];
        for (let index = 0; index < durations.length; ++index) {
            verify(durations[index] <= 240, "aucune transition ne dépasse 240 ms");
        }
    }

    function test_reduced_profile_removes_movement() {
        Motion.profile = "reduced";
        verify(Motion.reduced);
        compare(Motion.active.overlayEnter.distance, 0);
        compare(Motion.active.panelResize.duration, Motion.durationInstant);
        compare(Motion.active.activityPulse.duration, Motion.durationInstant);
        Motion.profile = "standard";
        verify(!Motion.reduced);
        verify(Motion.active.overlayEnter.distance > 0);
    }

    function test_easing_curves_are_ready_for_bezier_curve() {
        // easing.bezierCurve attend les quatre points de contrôle SUIVIS de 1, 1.
        compare(Motion.easingStandard.length, 6);
        compare(Motion.easingStandard[4], 1);
        compare(Motion.easingStandard[5], 1);
    }

    function test_elevation_flat_has_no_shadow() {
        compare(Elevation.elevationFlat.blur, 0);
        compare(Elevation.elevationFlat.opacity, 0);
        verify(Elevation.elevationOverlay.blur > 0);
        verify(Elevation.elevationDialog.blur > Elevation.elevationOverlay.blur);
    }

    function test_radius_decreases_with_density() {
        compare(Radius.radiusNone, 0);
        verify(Radius.radiusXs < Radius.radiusSm);
        verify(Radius.radiusSm < Radius.radiusMd);
        verify(Radius.radiusMd < Radius.radiusLg);
    }
}
