// Module Acp.Pixel : planches engendrées, police pixel, portraits et règles d'animation.
//
// Ces tests ne jugent pas le dessin. Ils vérifient que les métadonnées engendrées par
// scripts/generer_assets_pixel.py sont complètes, que la police couvre le français des
// libellés courts, et qu'aucun sprite ne s'anime sans y être autorisé (état observé, profil
// de mouvement, Concentration, visibilité).

import QtQuick
import QtTest
import Acp.Design
import Acp.Pixel

TestCase {
    id: testCase
    name: "Pixel"
    width: 400
    height: 300
    visible: true
    when: windowShown

    function init() {
        Motion.profile = "complet";
        Motion.concentration = false;
        Colors.theme = "atelier-nuit";
    }

    function test_portraits_cover_every_role_and_state() {
        const roles = ["coordinateur", "developpeur", "relecteur", "explorateur", "testeur", "inconnu"];
        const etats = ["repos", "travail", "attente", "echec", "termine", "arrete"];
        for (let r = 0; r < roles.length; ++r) {
            for (let e = 0; e < etats.length; ++e) {
                const seq = PlanchesPixel.portraits.sequences[roles[r] + "." + etats[e]];
                verify(seq !== undefined, roles[r] + "." + etats[e] + " manquant");
                verify(seq.durees.length >= 1);
            }
        }
        // Seule l'activité observée et l'ambiance au repos bouclent.
        verify(PlanchesPixel.portraits.sequences["developpeur.travail"].boucle);
        verify(!PlanchesPixel.portraits.sequences["developpeur.travail"].decoratif);
        verify(PlanchesPixel.portraits.sequences["developpeur.repos"].decoratif);
        verify(!PlanchesPixel.portraits.sequences["developpeur.echec"].boucle);
    }

    function test_police_covers_french_capitals() {
        const caracteres = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ÉÈÊËÀÂÎÏÔÙÛÜÇ.,:-/!?'()+#%_<>";
        for (let i = 0; i < caracteres.length; ++i)
            verify(PlanchesPixel.police.glyphes[caracteres[i]] !== undefined, "glyphe absent : " + caracteres[i]);
        for (let t = 0; t < Colors.themes.length; ++t)
            verify(PlanchesPixel.police.sequences[Colors.themes[t] + ".texte"] !== undefined);
    }

    function test_embleme_sizes_match_windows_icon() {
        compare(PlanchesPixel.embleme.tailles, [16, 20, 24, 32, 40, 48, 64, 128, 256]);
    }

    Component { id: texteComposant; TextePixel {} }
    Component { id: portraitComposant; PortraitAgent {} }

    function test_texte_pixel_says_its_text() {
        const texte = createTemporaryObject(texteComposant, testCase, { text: "À traiter", echelle: 2 });
        verify(texte !== null);
        compare(texte.Accessible.name, "À traiter");
        compare(texte.caracteres.join(""), "À TRAITER");
        // Neuf cases de 5 px agrandies deux fois, plus l'espacement.
        compare(texte.width, 9 * 5 * 2 + 8 * 2);
    }

    function test_unknown_role_falls_back_to_unknown_portrait() {
        const portrait = createTemporaryObject(portraitComposant, testCase, { role: "role-absent", etat: "attente" });
        verify(portrait !== null);
        compare(portrait.sequenceRetenue, "inconnu.attente");
    }

    function test_activity_animates_only_when_observed_and_allowed() {
        const portrait = createTemporaryObject(portraitComposant, testCase, { role: "developpeur", etat: "travail" });
        verify(portrait !== null);
        verify(portrait.anime);
        portrait.observe = false;
        verify(!portrait.anime, "sans télémétrie, aucune activité n'est mimée");
        portrait.observe = true;
        Motion.profile = "reduit";
        verify(!portrait.anime, "profil réduit : image fixe");
        Motion.profile = "complet";
        verify(portrait.anime);
    }

    function test_ambiance_stops_in_concentration_and_discreet() {
        const portrait = createTemporaryObject(portraitComposant, testCase, { role: "coordinateur", etat: "repos" });
        verify(portrait.anime);
        Motion.concentration = true;
        verify(!portrait.anime);
        Motion.concentration = false;
        Motion.profile = "discret";
        verify(!portrait.anime);
    }

    function test_hidden_sprite_does_not_run() {
        const portrait = createTemporaryObject(portraitComposant, testCase, { role: "developpeur", etat: "travail" });
        verify(portrait.anime);
        const sprite = portrait.children[0];
        verify(sprite.tourne);
        portrait.visible = false;
        verify(!sprite.tourne, "un sprite caché n'a aucun minuteur actif");
    }
}
