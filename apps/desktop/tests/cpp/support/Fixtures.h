// Lecture des documents de référence du greffon et de Hermes (tests/fixtures/hermes).
//
// Ils reprennent les formes relevées sur l'image de test par l'interface web (voir
// tests/fixtures/hermes/README.md) : les tests de la station lisent les MÊMES réponses que
// ceux du tableau de bord.

#pragma once

#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QString>

#ifndef ACP_TEST_FIXTURE_DIR
#error "ACP_TEST_FIXTURE_DIR doit désigner tests/fixtures"
#endif

// ACP_FIXTURES_PARTAGEES_DIR (tests/CMakeLists.txt) désigne hermes/tests/outils.

namespace acp::test {

inline QByteArray brutFixture(const QString &nom)
{
    QFile fichier(QStringLiteral(ACP_TEST_FIXTURE_DIR "/hermes/") + nom);
    if (!fichier.open(QIODevice::ReadOnly)) {
        qFatal("Document de référence introuvable : %s", qPrintable(nom));
    }
    return fichier.readAll();
}

inline QJsonObject fixture(const QString &nom)
{
    QJsonParseError erreur;
    const QJsonDocument document = QJsonDocument::fromJson(brutFixture(nom), &erreur);
    if (erreur.error != QJsonParseError::NoError || !document.isObject()) {
        qFatal("Document de référence illisible : %s", qPrintable(nom));
    }
    return document.object();
}

#ifdef ACP_FIXTURES_PARTAGEES_DIR
/*!
    Fixture PARTAGÉE avec le greffon et l'interface web, lue à sa place sous
    hermes/tests/outils (« fixtures_accueil/accueil.json », « fixtures_flux/trames.json »,
    « fixtures_poste/depots.json ») : jamais recopiée dans la station.
*/
inline QJsonDocument fixturePartagee(const QString &chemin)
{
    QFile fichier(QStringLiteral(ACP_FIXTURES_PARTAGEES_DIR "/") + chemin);
    if (!fichier.open(QIODevice::ReadOnly)) {
        qFatal("Fixture partagée introuvable : %s", qPrintable(chemin));
    }
    QJsonParseError erreur;
    const QJsonDocument document = QJsonDocument::fromJson(fichier.readAll(), &erreur);
    if (erreur.error != QJsonParseError::NoError) {
        qFatal("Fixture partagée illisible : %s", qPrintable(chemin));
    }
    return document;
}
#endif

} // namespace acp::test
