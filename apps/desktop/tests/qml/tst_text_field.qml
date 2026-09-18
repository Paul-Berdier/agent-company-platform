// Champ de saisie : ce que les technologies d'assistance en voient.

import QtQuick
import QtTest
import Acp.Controls
import Acp.Design

TestCase {
    id: testCase
    name: "AcpTextField"
    when: windowShown
    width: 400
    height: 200

    Component {
        id: fieldComponent
        AcpTextField {}
    }

    function inputOf(field) {
        const input = findChild(field, "acpTextFieldInput");
        verify(input !== null, "le TextInput interne doit être trouvable");
        return input;
    }

    function test_placeholder_is_the_default_accessible_name() {
        const field = createTemporaryObject(fieldComponent, testCase,
                                            { placeholder: "Identifiant" });
        const input = inputOf(field);
        compare(input.Accessible.role, Accessible.EditableText);
        compare(input.Accessible.name, "Identifiant");
        compare(input.Accessible.passwordEdit, false);
    }

    function test_explicit_accessible_name_overrides_an_example_placeholder() {
        const field = createTemporaryObject(fieldComponent, testCase, {
            placeholder: "https://exemple.invalid",
            accessibleName: "Adresse du serveur"
        });
        compare(inputOf(field).Accessible.name, "Adresse du serveur");
    }

    function test_masked_field_is_announced_as_a_password() {
        const field = createTemporaryObject(fieldComponent, testCase,
                                            { placeholder: "Mot de passe", masked: true });
        const input = inputOf(field);
        compare(input.Accessible.passwordEdit, true);
        compare(input.echoMode, TextInput.Password);
    }

    function test_hidden_helper_stays_in_the_accessible_description() {
        const field = createTemporaryObject(fieldComponent, testCase,
                                            { helperText: "Aide", helperVisible: false });
        compare(inputOf(field).Accessible.description, "Aide");
        // Seul le champ occupe la hauteur : rien n'est dessiné sous lui.
        compare(field.implicitHeight, Space.densityControlHeightRegular);
    }

    function test_error_replaces_helper_in_the_accessible_description() {
        const field = createTemporaryObject(fieldComponent, testCase,
                                            { helperText: "Aide", errorText: "" });
        const input = inputOf(field);
        compare(input.Accessible.description, "Aide");
        field.errorText = "Adresse refusée";
        compare(input.Accessible.description, "Adresse refusée");
    }
}
