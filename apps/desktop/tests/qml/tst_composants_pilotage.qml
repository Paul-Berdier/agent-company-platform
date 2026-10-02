// Composants de présentation des pages de pilotage : état de lecture, bandeau de résultat,
// texte long et carte. Ils n'affichent que ce qu'on leur donne, en texte brut, et ne
// présentent jamais une erreur comme une réussite.

import QtQuick
import QtTest
import Acp.Design
import Acp.Components

TestCase {
    id: testCase
    name: "ComposantsPilotage"
    when: windowShown
    width: 600
    height: 400
    // TestCase est invisible par défaut : la visibilité des composants ne serait pas éprouvée.
    visible: true

    Component { id: etatComponent; EtatLecture {} }
    Component { id: bandeauComponent; BandeauMessage {} }
    Component { id: blocComponent; BlocTexte {} }
    Component { id: compteurComponent; PastilleCompteur {} }
    Component {
        id: carteComponent
        Carte {
            width: 500
            Text { objectName: "contenu-de-test"; text: "Contenu" }
        }
    }

    function enfantNomme(racine, nom) {
        if (racine.objectName === nom)
            return racine;
        const enfants = racine.children || [];
        for (let i = 0; i < enfants.length; ++i) {
            const trouve = enfantNomme(enfants[i], nom);
            if (trouve)
                return trouve;
        }
        return null;
    }

    function test_etat_lecture_absent_est_invisible() {
        const etat = createTemporaryObject(etatComponent, testCase);
        verify(!etat.visible);
        verify(!etat.enErreur);
    }

    function test_etat_lecture_garde_l_heure_et_dit_l_erreur() {
        const etat = createTemporaryObject(etatComponent, testCase,
                                           { lecture: "Lu à 12:00:00", erreur: "Serveur injoignable" });
        verify(etat.visible);
        verify(etat.enErreur);
        compare(enfantNomme(etat, "etat-lecture").text, "Lu à 12:00:00");
        const erreur = enfantNomme(etat, "etat-lecture-erreur");
        verify(erreur.visible);
        compare(erreur.text, "Dernière lecture impossible : Serveur injoignable");
    }

    function test_bandeau_vide_ne_prend_aucune_place() {
        const bandeau = createTemporaryObject(bandeauComponent, testCase, { width: 400 });
        verify(!bandeau.visible);
        compare(bandeau.implicitHeight, 0);
    }

    function test_bandeau_reussite() {
        const bandeau = createTemporaryObject(bandeauComponent, testCase,
                                              { width: 400, message: "Projet lancé : Hermes le planifie." });
        verify(bandeau.visible);
        verify(!bandeau.enErreur);
        compare(bandeau.texte, "Projet lancé : Hermes le planifie.");
        compare(bandeau.Accessible.role, Accessible.StaticText);
    }

    function test_bandeau_refus_rendu_tel_quel_et_annonce() {
        const bandeau = createTemporaryObject(bandeauComponent, testCase,
                                              { width: 400, message: "ignoré", erreur: "Refusé par ACP : projet déjà en pause." });
        verify(bandeau.enErreur);
        // Le refus l'emporte sur un message de réussite, et sa forme ne dépend pas de la couleur.
        compare(bandeau.texte, "Refusé : Refusé par ACP : projet déjà en pause.");
        compare(bandeau.Accessible.role, Accessible.AlertMessage);
    }

    function test_bloc_texte_vide_affiche_le_remplacement() {
        const bloc = createTemporaryObject(blocComponent, testCase,
                                           { width: 400, libelle: "Dernière note", texte: "", vide: "Aucune carte finie pour l'instant." });
        const valeur = enfantNomme(bloc, "bloc-texte-valeur");
        compare(valeur.text, "Aucune carte finie pour l'instant.");
    }

    function test_bloc_texte_ne_rend_jamais_de_balisage() {
        const bloc = createTemporaryObject(blocComponent, testCase,
                                           { width: 400, texte: "<b>gras</b> <a href='x'>lien</a>" });
        const valeur = enfantNomme(bloc, "bloc-texte-valeur");
        compare(valeur.textFormat, TextEdit.PlainText);
        compare(valeur.text, "<b>gras</b> <a href='x'>lien</a>");
        verify(valeur.readOnly);
    }

    function test_compteur_invisible_a_zero_ou_inconnu() {
        verify(!createTemporaryObject(compteurComponent, testCase, { nombre: 0 }).visible);
        // Un nombre inconnu (négatif) n'est jamais affiché comme « 0 ».
        verify(!createTemporaryObject(compteurComponent, testCase, { nombre: -1 }).visible);
    }

    function test_compteur_borne_et_nom_accessible() {
        const trois = createTemporaryObject(compteurComponent, testCase, { nombre: 3, description: "questions ouvertes" });
        verify(trois.visible);
        compare(trois.texte, "3");
        compare(trois.Accessible.name, "3 questions ouvertes");
        const beaucoup = createTemporaryObject(compteurComponent, testCase, { nombre: 140, description: "questions ouvertes" });
        compare(beaucoup.texte, "99+");
        compare(beaucoup.Accessible.name, "140 questions ouvertes");
    }

    function test_carte_sans_pastille_et_avec_contenu() {
        const carte = createTemporaryObject(carteComponent, testCase, { titre: "Projets" });
        verify(carte.implicitHeight > 0);
        verify(enfantNomme(carte, "contenu-de-test") !== null);
        compare(carte.Accessible.name, "Projets");
    }

    function test_carte_relaie_l_erreur_de_lecture() {
        const carte = createTemporaryObject(carteComponent, testCase,
                                            { titre: "Poste", cle: "offline", libelleEtat: "Hors ligne",
                                              lecture: "Lu à 08:00:00", erreurLecture: "Délai dépassé" });
        const erreur = enfantNomme(carte, "etat-lecture-erreur");
        verify(erreur !== null);
        verify(erreur.visible);
        compare(erreur.text, "Dernière lecture impossible : Délai dépassé");
    }
}
