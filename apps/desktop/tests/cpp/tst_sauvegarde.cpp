// Sauvegarde chiffrée de Hermes (cahier P8 § 7.9, § 8) :
//  - format ACPB1 sur le VRAI DPAPI de la session Windows : aller-retour, empreintes ;
//    troncature, altération, morceaux déplacés, drapeau final retourné, morceau d'une autre
//    sauvegarde : tous refusés ;
//  - parcours complet contre le faux Hermes : lancement, suivi, téléchargement en flux,
//    chiffrement au fil de l'eau, suppression de l'archive du volume ; corps et requêtes exacts ;
//    AUCUN fichier du dossier de destination ne contient l'octet-témoin de l'archive en clair ;
//  - échecs dits tels quels, sans fichier partiel : archivage échoué (journal expurgé),
//    téléchargement refusé, plafond dépassé, annulation, session perdue ; suppression refusée :
//    chemin dit ; suppression en vol jamais interrompue (ni par l'annulation ni par la session) ;
//  - déchiffrement depuis la page.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "storage/ChiffrementSauvegarde.h"
#include "support/FauxHermes.h"
#include "viewmodels/SauvegardeViewModel.h"

#include <QBuffer>
#include <QCryptographicHash>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QTest>
#include <QtEndian>

using namespace acp;
using namespace acp::test;

namespace {

const QByteArray kTemoin = QByteArrayLiteral("TEMOIN-CLAIR-ACPB-ARCHIVE-HERMES");
const QString kArchive = QStringLiteral("/opt/data/backups/hermes-backup-2026-10-02-101500-ab12cd34.zip");

//! Archive factice : octets pseudo-aléatoires semés de l'octet-témoin tous les 64 Kio.
QByteArray archiveFactice(qsizetype taille)
{
    QByteArray octets(taille, '\0');
    quint32 graine = 0x2545F491u;
    for (qsizetype index = 0; index < taille; ++index) {
        graine = graine * 1664525u + 1013904223u;
        octets[index] = static_cast<char>(graine >> 24);
    }
    for (qsizetype position = 0; position + kTemoin.size() <= taille; position += 64 * 1024) {
        octets.replace(position, kTemoin.size(), kTemoin);
    }
    return octets;
}

QByteArray chiffrer(const ProtecteurDonnees &protecteur, const QByteArray &clair, QByteArray *empreinteClaire = nullptr)
{
    QBuffer sortie;
    sortie.open(QIODevice::WriteOnly);
    ChiffreurSauvegarde chiffreur(protecteur, &sortie);
    QString erreur;
    if (!chiffreur.commencer(&erreur)) {
        qFatal("commencer : %s", qPrintable(erreur));
    }
    // Livré par morceaux irréguliers, comme un flux réseau.
    for (qsizetype position = 0; position < clair.size(); position += 300001) {
        if (!chiffreur.ajouter(QByteArrayView(clair).mid(position, 300001), &erreur)) {
            qFatal("ajouter : %s", qPrintable(erreur));
        }
    }
    if (!chiffreur.terminer(&erreur)) {
        qFatal("terminer : %s", qPrintable(erreur));
    }
    if (empreinteClaire) {
        *empreinteClaire = chiffreur.empreinteClaire();
    }
    if (chiffreur.empreinteChiffree() != QCryptographicHash::hash(sortie.data(), QCryptographicHash::Sha256).toHex()) {
        qFatal("empreinte du fichier chiffré incohérente");
    }
    return sortie.data();
}

bool dechiffrer(const ProtecteurDonnees &protecteur, const QByteArray &fichier, QByteArray *clair, QString *erreur)
{
    QBuffer entree;
    entree.setData(fichier);
    entree.open(QIODevice::ReadOnly);
    QBuffer sortie;
    sortie.open(QIODevice::WriteOnly);
    const bool ok = dechiffrerSauvegarde(protecteur, &entree, &sortie, erreur);
    *clair = sortie.data();
    return ok;
}

//! Positions (début) des cadres d'un fichier ACPB1.
QList<qsizetype> cadres(const QByteArray &fichier)
{
    QList<qsizetype> positions;
    qsizetype position = ChiffreurSauvegarde::kTailleEnTete;
    while (position + 5 <= fichier.size()) {
        positions.append(position);
        position += 5 + qFromBigEndian<quint32>(fichier.constData() + position + 1);
    }
    return positions;
}

bool dossierContient(const QString &dossier, const QByteArray &motif)
{
    QDirIterator parcours(dossier, QDir::Files | QDir::Hidden | QDir::System, QDirIterator::Subdirectories);
    while (parcours.hasNext()) {
        QFile fichier(parcours.next());
        if (fichier.open(QIODevice::ReadOnly) && fichier.readAll().contains(motif)) {
            return true;
        }
    }
    return false;
}

struct Banc
{
    FauxHermes serveur;
    ApiClient client;
    ClientGreffonPoste greffon{&client};
    EventStreamService flux{&client, &greffon, nullptr};
    SauvegardeViewModel sauvegarde{&client, &flux, makeProtecteurUtilisateur()};
    QTemporaryDir dossier;
    QByteArray archive = archiveFactice(3 * 1024 * 1024 + 512 * 1024);
    QList<QJsonObject> etats{
        QJsonObject{{QStringLiteral("name"), QStringLiteral("backup")}, {QStringLiteral("running"), true},
                    {QStringLiteral("exit_code"), QJsonValue::Null}, {QStringLiteral("pid"), 4242},
                    {QStringLiteral("lines"), QJsonArray{QStringLiteral("Sauvegarde en cours")}}},
        QJsonObject{{QStringLiteral("name"), QStringLiteral("backup")}, {QStringLiteral("running"), false},
                    {QStringLiteral("exit_code"), 0}, {QStringLiteral("pid"), 4242},
                    {QStringLiteral("lines"), QJsonArray{QStringLiteral("Backup written")}}},
    };
    ReponseFaux lancement = ReponseFaux::json(200, QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("pid"), 4242},
                                                               {QStringLiteral("name"), QStringLiteral("backup")},
                                                               {QStringLiteral("archive"), kArchive}});
    ReponseFaux suppression = ReponseFaux::json(200, QJsonObject{{QStringLiteral("ok"), true}, {QStringLiteral("path"), kArchive}});
    std::optional<ReponseFaux> telechargement;

    Banc()
    {
        serveur.installerAuthentification();
        serveur.jetonsAccesValides.insert(QByteArrayLiteral("jeton-a"));
        client.setAllowInsecureLoopback(true);
        if (client.setBaseUrl(serveur.url()).isError()) {
            qFatal("URL du faux Hermes refusée");
        }
        client.setBearerProvider([] { return QByteArrayLiteral("jeton-a"); });
        sauvegarde.setIntervalleSuivi(std::chrono::milliseconds(20));
        serveur.route("POST", QStringLiteral("/api/ops/backup"), [this](const RequeteRecue &) { return lancement; });
        serveur.route("GET", QStringLiteral("/api/actions/backup/status"), [this](const RequeteRecue &) {
            return ReponseFaux::json(200, etats.size() > 1 ? etats.takeFirst() : etats.constFirst());
        });
        serveur.route("GET", QStringLiteral("/api/ops/backup/download"), [this](const RequeteRecue &) {
            if (telechargement) {
                return *telechargement;
            }
            ReponseFaux reponse;
            reponse.corps = archive;
            reponse.entetes.append({QByteArrayLiteral("Content-Type"), QByteArrayLiteral("application/zip")});
            return reponse;
        });
        serveur.route("DELETE", QStringLiteral("/api/files"), [this](const RequeteRecue &) { return suppression; });
    }

    QString destination() const { return QDir(dossier.path()).filePath(QStringLiteral("hermes.acpb")); }

    void attendreFin()
    {
        QTRY_VERIFY_WITH_TIMEOUT(sauvegarde.phase() == SauvegardeViewModel::Phase::Termine
                                     || sauvegarde.phase() == SauvegardeViewModel::Phase::Echec,
                                 15000);
    }
};

} // namespace

class TestSauvegarde : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void formatAllerRetour();
    void troncatureEtAlterationRefusees();
    void entropieLieeAuRangEtALExport();
    void exportCompletSansClairSurLeDisque();
    void suppressionRefuseeDite();
    void echecDeLArchivageJournalExpurge();
    void telechargementRefuseAucunFichier();
    void plafondDepasseAucunFichier();
    void annulationPendantLArchivage();
    void sessionPerduePendantLArchivage();
    void suppressionEnVolJamaisInterrompue();
    void dechiffrerDepuisLaPage();
    void cheminsTaillesEtDurees();
};

void TestSauvegarde::initTestCase()
{
    if (!makeProtecteurUtilisateur()->disponible()) {
        QSKIP("DPAPI n'existe que sous Windows : format ACPB1 non éprouvé sur ce système.");
    }
}

void TestSauvegarde::formatAllerRetour()
{
    const auto protecteur = makeProtecteurUtilisateur();
    for (const qsizetype taille : {qsizetype(0), qsizetype(1), ChiffreurSauvegarde::kTailleMorceau,
                                   ChiffreurSauvegarde::kTailleMorceau * 2 + 512 * 1024}) {
        const QByteArray clair = archiveFactice(taille);
        QByteArray empreinte;
        const QByteArray fichier = chiffrer(*protecteur, clair, &empreinte);
        QVERIFY(fichier.startsWith(QByteArrayLiteral("ACPB1\x01")));
        QVERIFY2(!fichier.contains(kTemoin), "l'octet-témoin du clair figure dans le fichier chiffré");
        QCOMPARE(empreinte, QCryptographicHash::hash(clair, QCryptographicHash::Sha256).toHex());
        // Morceaux de 1 Mio au plus ; le dernier porte toujours le drapeau final.
        const QList<qsizetype> positions = cadres(fichier);
        const qsizetype attendus = std::max<qsizetype>(1, (taille + ChiffreurSauvegarde::kTailleMorceau - 1)
                                                               / ChiffreurSauvegarde::kTailleMorceau);
        QCOMPARE(positions.size(), attendus);
        for (qsizetype rang = 0; rang < positions.size(); ++rang) {
            QCOMPARE(fichier.at(positions.at(rang)) == '\x01', rang == positions.size() - 1);
        }
        QByteArray relu;
        QString erreur;
        QVERIFY2(dechiffrer(*protecteur, fichier, &relu, &erreur), qPrintable(erreur));
        QCOMPARE(relu, clair);
    }
}

void TestSauvegarde::troncatureEtAlterationRefusees()
{
    const auto protecteur = makeProtecteurUtilisateur();
    const QByteArray clair = archiveFactice(ChiffreurSauvegarde::kTailleMorceau * 2 + 512 * 1024);
    const QByteArray fichier = chiffrer(*protecteur, clair);
    const QList<qsizetype> positions = cadres(fichier);
    QCOMPARE(positions.size(), 3);
    QByteArray relu;
    QString erreur;

    // Morceau final retiré : tronquée.
    QVERIFY(!dechiffrer(*protecteur, fichier.left(positions.at(2)), &relu, &erreur));
    QVERIFY2(erreur.startsWith(QStringLiteral("Sauvegarde tronquée : le morceau final manque")), qPrintable(erreur));
    // Coupée au milieu d'un morceau.
    QVERIFY(!dechiffrer(*protecteur, fichier.left(positions.at(1) + 100), &relu, &erreur));
    QVERIFY2(erreur.startsWith(QStringLiteral("Sauvegarde tronquée au morceau 2")), qPrintable(erreur));
    // Octets après le morceau final.
    QVERIFY(!dechiffrer(*protecteur, fichier + QByteArrayLiteral("x"), &relu, &erreur));
    QCOMPARE(erreur, QStringLiteral("Sauvegarde altérée : des octets suivent le morceau final."));
    // Un octet du premier bloc retourné.
    QByteArray altere = fichier;
    altere[positions.at(0) + 200] = static_cast<char>(altere.at(positions.at(0) + 200) ^ 0x5A);
    QVERIFY(!dechiffrer(*protecteur, altere, &relu, &erreur));
    QVERIFY2(erreur.contains(QStringLiteral("le morceau 1 ne se déchiffre pas")), qPrintable(erreur));
    // Deux morceaux intermédiaires échangés (même taille) : le rang ne correspond plus.
    QByteArray permute = fichier.left(ChiffreurSauvegarde::kTailleEnTete);
    permute += fichier.mid(positions.at(1), positions.at(2) - positions.at(1));
    permute += fichier.mid(positions.at(0), positions.at(1) - positions.at(0));
    permute += fichier.mid(positions.at(2));
    QCOMPARE(permute.size(), fichier.size());
    QVERIFY(!dechiffrer(*protecteur, permute, &relu, &erreur));
    // Drapeau final retourné : l'entropie ne correspond plus.
    QByteArray drapeau = fichier;
    drapeau[positions.at(2)] = '\x00';
    QVERIFY(!dechiffrer(*protecteur, drapeau, &relu, &erreur));
    // En-tête inconnu.
    QByteArray tete = fichier;
    tete[0] = 'X';
    QVERIFY(!dechiffrer(*protecteur, tete, &relu, &erreur));
    QCOMPARE(erreur, QStringLiteral("Ce fichier n'est pas une sauvegarde chiffrée par la station (format ACPB1 attendu)."));
    // Morceau d'une AUTRE sauvegarde du même clair : refusé (identifiant d'export).
    const QByteArray autre = chiffrer(*protecteur, clair);
    QVERIFY(autre.mid(6, 16) != fichier.mid(6, 16));
    QByteArray greffe = fichier.left(positions.at(1)) + autre.mid(cadres(autre).at(1));
    QVERIFY(!dechiffrer(*protecteur, greffe, &relu, &erreur));
}

void TestSauvegarde::entropieLieeAuRangEtALExport()
{
    const QByteArray a(16, 'a');
    const QByteArray b(16, 'b');
    QVERIFY(entropieMorceau(a, 0, false) != entropieMorceau(a, 1, false));
    QVERIFY(entropieMorceau(a, 3, false) != entropieMorceau(a, 3, true));
    QVERIFY(entropieMorceau(a, 3, true) != entropieMorceau(b, 3, true));
    QCOMPARE(entropieMorceau(a, 3, true), entropieMorceau(a, 3, true));
}

void TestSauvegarde::exportCompletSansClairSurLeDisque()
{
    Banc banc;
    QVERIFY(banc.sauvegarde.chiffrementDisponible());
    banc.sauvegarde.exporter(QUrl::fromLocalFile(banc.destination()).toString());
    banc.attendreFin();
    QCOMPARE(banc.sauvegarde.erreurGeste(), QString());
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Termine);
    QCOMPARE(banc.sauvegarde.messageGeste(), QStringLiteral("Sauvegarde exportée et chiffrée sur ce PC."));

    // Requêtes exactes : lancement JSON vide, suivi jusqu'à la fin, flux de l'archive annoncée,
    // suppression de CETTE archive ; toutes en porteur, aucune avec Origin ni cookie.
    const auto lancements = banc.serveur.filtrer("POST", QStringLiteral("/api/ops/backup"));
    QCOMPARE(lancements.size(), 1);
    QCOMPARE(lancements.first().json(), QJsonObject{});
    QCOMPARE(lancements.first().entete("content-type"), QByteArrayLiteral("application/json"));
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/actions/backup/status")), 2);
    const auto flux = banc.serveur.filtrer("GET", QStringLiteral("/api/ops/backup/download"));
    QCOMPARE(flux.size(), 1);
    QCOMPARE(flux.first().requete.queryItemValue(QStringLiteral("archive"), QUrl::FullyDecoded), kArchive);
    const auto suppressions = banc.serveur.filtrer("DELETE", QStringLiteral("/api/files"));
    QCOMPARE(suppressions.size(), 1);
    QCOMPARE(suppressions.first().json(), (QJsonObject{{QStringLiteral("path"), kArchive}}));
    for (const RequeteRecue &requete : banc.serveur.requetes) {
        QCOMPARE(requete.entete("authorization"), QByteArrayLiteral("Bearer jeton-a"));
        QVERIFY(!requete.aEntete("origin"));
        QVERIFY(!requete.aEntete("cookie"));
    }

    // Le fichier se déchiffre en l'archive servie ; rien en clair dans le dossier.
    QFile fichier(banc.destination());
    QVERIFY(fichier.open(QIODevice::ReadOnly));
    const QByteArray chiffre = fichier.readAll();
    QByteArray relu;
    QString erreur;
    QVERIFY2(dechiffrer(*makeProtecteurUtilisateur(), chiffre, &relu, &erreur), qPrintable(erreur));
    QCOMPARE(relu, banc.archive);
    QVERIFY2(!dossierContient(banc.dossier.path(), kTemoin), "l'archive en clair a touché le disque");
    QCOMPARE(QDir(banc.dossier.path()).entryList(QDir::Files | QDir::Hidden).size(), 1);

    const QVariantMap resultat = banc.sauvegarde.resultat();
    QCOMPARE(resultat.value(QStringLiteral("fichier")).toString(), QDir::toNativeSeparators(banc.destination()));
    QCOMPARE(resultat.value(QStringLiteral("empreinte")).toString(),
             QString::fromLatin1(QCryptographicHash::hash(chiffre, QCryptographicHash::Sha256).toHex()));
    QCOMPARE(resultat.value(QStringLiteral("tailleArchive")).toString(), QStringLiteral("3,5\u00A0Mio"));
    QCOMPARE(resultat.value(QStringLiteral("suppression")).toString(),
             QStringLiteral("Archive non chiffrée supprimée du volume de Hermes."));
    QCOMPARE(resultat.value(QStringLiteral("archiveRestante")).toString(), QString());
    QVERIFY(!resultat.value(QStringLiteral("duree")).toString().isEmpty());
    QCOMPARE(banc.sauvegarde.empreinteArchive(), QCryptographicHash::hash(banc.archive, QCryptographicHash::Sha256).toHex());
    QVERIFY(banc.sauvegarde.progression().endsWith(QStringLiteral("reçus et chiffrés")));
}

void TestSauvegarde::suppressionRefuseeDite()
{
    Banc banc;
    banc.suppression = ReponseFaux::json(403, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Path outside managed files root")}});
    banc.sauvegarde.exporter(banc.destination());
    banc.attendreFin();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Termine);
    QVERIFY(QFile::exists(banc.destination()));
    const QVariantMap resultat = banc.sauvegarde.resultat();
    QCOMPARE(resultat.value(QStringLiteral("archiveRestante")).toString(), kArchive);
    const QString suppression = resultat.value(QStringLiteral("suppression")).toString();
    QVERIFY2(suppression.startsWith(QStringLiteral("L'archive non chiffrée reste sur le volume de Hermes : ") + kArchive
                                    + QStringLiteral(". Elle contient .env et auth.json : supprimez-la.")),
             qPrintable(suppression));
    QVERIFY2(suppression.contains(QStringLiteral("chemin hors de la racine des fichiers gérés par Hermes")), qPrintable(suppression));
    QVERIFY(banc.sauvegarde.messageGeste().contains(QStringLiteral("l'archive non chiffrée reste sur le volume")));
}

void TestSauvegarde::echecDeLArchivageJournalExpurge()
{
    Banc banc;
    banc.etats = {QJsonObject{{QStringLiteral("running"), false}, {QStringLiteral("exit_code"), 2},
                              {QStringLiteral("lines"), QJsonArray{QStringLiteral("Traceback (most recent call last):"),
                                                                   QStringLiteral("Authorization: Bearer abcdef123456"),
                                                                   QStringLiteral("OSError: No space left on device")}}}};
    banc.sauvegarde.exporter(banc.destination());
    banc.attendreFin();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Echec);
    QCOMPARE(banc.sauvegarde.erreurGeste(),
             QStringLiteral("La sauvegarde de Hermes a échoué (code de sortie 2) : voir le journal ci-dessous."));
    QVERIFY(banc.sauvegarde.journal().contains(QStringLiteral("No space left on device")));
    QVERIFY(!banc.sauvegarde.journal().contains(QStringLiteral("abcdef123456")));
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/ops/backup/download")), 0);
    QVERIFY(!QFile::exists(banc.destination()));
    // L'archive a pu être commencée côté Hermes : son chemin est dit.
    QCOMPARE(banc.sauvegarde.resultat().value(QStringLiteral("archiveRestante")).toString(), kArchive);
}

void TestSauvegarde::telechargementRefuseAucunFichier()
{
    Banc banc;
    banc.telechargement = ReponseFaux::json(404, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Backup not found")}});
    banc.sauvegarde.exporter(banc.destination());
    banc.attendreFin();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Echec);
    QVERIFY2(banc.sauvegarde.erreurGeste().contains(QStringLiteral("archive de sauvegarde introuvable sur le serveur")),
             qPrintable(banc.sauvegarde.erreurGeste()));
    QVERIFY(!QFile::exists(banc.destination()));
    QCOMPARE(QDir(banc.dossier.path()).entryList(QDir::Files | QDir::Hidden).size(), 0);
    QCOMPARE(banc.serveur.compter("DELETE", QStringLiteral("/api/files")), 0);
}

void TestSauvegarde::plafondDepasseAucunFichier()
{
    Banc banc;
    banc.sauvegarde.setPlafond(1024 * 1024);
    banc.sauvegarde.exporter(banc.destination());
    banc.attendreFin();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Echec);
    QVERIFY2(banc.sauvegarde.erreurGeste().startsWith(QStringLiteral("L'archive dépasse le plafond")),
             qPrintable(banc.sauvegarde.erreurGeste()));
    QVERIFY(!QFile::exists(banc.destination()));
    QVERIFY(!dossierContient(banc.dossier.path(), kTemoin));
}

void TestSauvegarde::annulationPendantLArchivage()
{
    Banc banc;
    banc.etats = {banc.etats.constFirst()}; // toujours en cours
    banc.sauvegarde.exporter(banc.destination());
    QTRY_COMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Archivage);
    QTRY_VERIFY(banc.serveur.compter("GET", QStringLiteral("/api/actions/backup/status")) >= 2);
    QVERIFY(banc.sauvegarde.enCours());
    banc.sauvegarde.annuler();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Echec);
    QVERIFY(banc.sauvegarde.erreurGeste().startsWith(QStringLiteral("Export annulé.")));
    const int suivis = banc.serveur.compter("GET", QStringLiteral("/api/actions/backup/status"));
    QTest::qWait(150);
    QVERIFY(banc.serveur.compter("GET", QStringLiteral("/api/actions/backup/status")) <= suivis + 1);
    QVERIFY(!QFile::exists(banc.destination()));
    // Revenir au repos permet un nouvel export.
    banc.sauvegarde.reinitialiser();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Repos);
    QVERIFY(banc.sauvegarde.resultat().isEmpty());
}

void TestSauvegarde::sessionPerduePendantLArchivage()
{
    Banc banc;
    banc.flux.demarrer();
    banc.etats = {banc.etats.constFirst()}; // toujours en cours
    banc.sauvegarde.exporter(banc.destination());
    QTRY_COMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Archivage);
    QVERIFY(banc.sauvegarde.interruptible());
    banc.flux.arreter(); // déconnexion, jeton refusé
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Echec);
    QCOMPARE(banc.sauvegarde.erreurGeste(),
             QStringLiteral("Session perdue : l'export est arrêté, aucun fichier n'est écrit sur ce PC."));
    QCOMPARE(banc.sauvegarde.resultat().value(QStringLiteral("archiveRestante")).toString(), kArchive);
    const int suivis = banc.serveur.compter("GET", QStringLiteral("/api/actions/backup/status"));
    QTest::qWait(150);
    QVERIFY(banc.serveur.compter("GET", QStringLiteral("/api/actions/backup/status")) <= suivis + 1);
    QCOMPARE(banc.serveur.compter("GET", QStringLiteral("/api/ops/backup/download")), 0);
    QVERIFY(!QFile::exists(banc.destination()));
}

void TestSauvegarde::suppressionEnVolJamaisInterrompue()
{
    Banc banc;
    banc.flux.demarrer();
    banc.suppression.delaiMs = 400;
    banc.sauvegarde.exporter(banc.destination());
    QTRY_COMPARE_WITH_TIMEOUT(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Suppression, 15000);
    QVERIFY(banc.sauvegarde.enCours());
    QVERIFY(!banc.sauvegarde.interruptible());
    // Ni l'annulation ni la perte de session n'interrompent la suppression déjà envoyée : son
    // résultat réel est attendu puis dit.
    banc.sauvegarde.annuler();
    banc.flux.arreter();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Suppression);
    banc.attendreFin();
    QCOMPARE(banc.sauvegarde.phase(), SauvegardeViewModel::Phase::Termine);
    QCOMPARE(banc.sauvegarde.resultat().value(QStringLiteral("suppression")).toString(),
             QStringLiteral("Archive non chiffrée supprimée du volume de Hermes."));
    QVERIFY(QFile::exists(banc.destination()));
    QCOMPARE(banc.serveur.compter("DELETE", QStringLiteral("/api/files")), 1);
}

void TestSauvegarde::dechiffrerDepuisLaPage()
{
    Banc banc;
    const QByteArray clair = archiveFactice(1500 * 1024);
    const QString source = QDir(banc.dossier.path()).filePath(QStringLiteral("export.acpb"));
    const QString zip = QDir(banc.dossier.path()).filePath(QStringLiteral("restauration.zip"));
    {
        QFile fichier(source);
        QVERIFY(fichier.open(QIODevice::WriteOnly));
        fichier.write(chiffrer(*makeProtecteurUtilisateur(), clair));
    }
    banc.sauvegarde.dechiffrer(source, source);
    QCOMPARE(banc.sauvegarde.erreurGeste(), QStringLiteral("L'archive déchiffrée doit être écrite dans un autre fichier que la sauvegarde."));
    banc.sauvegarde.dechiffrer(QUrl::fromLocalFile(source).toString(), zip);
    QVERIFY2(banc.sauvegarde.erreurGeste().isEmpty(), qPrintable(banc.sauvegarde.erreurGeste()));
    QVERIFY(banc.sauvegarde.messageGeste().startsWith(QStringLiteral("Archive déchiffrée : ")));
    QFile relu(zip);
    QVERIFY(relu.open(QIODevice::ReadOnly));
    QCOMPARE(relu.readAll(), clair);
    relu.close();

    // Fichier altéré : refus, et aucune archive écrite.
    QFile::remove(zip);
    {
        QFile fichier(source);
        QVERIFY(fichier.open(QIODevice::ReadWrite));
        fichier.seek(ChiffreurSauvegarde::kTailleEnTete + 400);
        fichier.write("XYZ");
    }
    banc.sauvegarde.dechiffrer(source, zip);
    QVERIFY(banc.sauvegarde.erreurGeste().contains(QStringLiteral("ne se déchiffre pas")));
    QVERIFY(!QFile::exists(zip));
}

void TestSauvegarde::cheminsTaillesEtDurees()
{
    QCOMPARE(SauvegardeViewModel::cheminLocal(QStringLiteral("file:///C:/Sauvegardes/h.acpb")),
             QDir::toNativeSeparators(QStringLiteral("C:/Sauvegardes/h.acpb")));
    QCOMPARE(SauvegardeViewModel::cheminLocal(QStringLiteral("  ")), QString());
    QCOMPARE(SauvegardeViewModel::formaterTaille(512), QStringLiteral("512\u00A0o"));
    QCOMPARE(SauvegardeViewModel::formaterTaille(1536), QStringLiteral("1,5\u00A0Kio"));
    QCOMPARE(SauvegardeViewModel::formaterTaille(3LL * 1024 * 1024 * 1024), QStringLiteral("3,0\u00A0Gio"));
    QCOMPARE(SauvegardeViewModel::formaterDuree(9500), QStringLiteral("9\u00A0s"));
    QCOMPARE(SauvegardeViewModel::formaterDuree(72000), QStringLiteral("1\u00A0min 12\u00A0s"));
    QJsonArray lignes;
    for (int index = 0; index < 30; ++index) {
        lignes.append(QStringLiteral("ligne %1").arg(index));
    }
    const QString journal = SauvegardeViewModel::journalExpurge(lignes);
    QVERIFY(journal.startsWith(QStringLiteral("ligne 10\n")));
    QVERIFY(journal.endsWith(QStringLiteral("ligne 29")));
    Banc banc;
    QVERIFY(banc.sauvegarde.proposerDestination().endsWith(QStringLiteral(".acpb")));
    banc.sauvegarde.exporter(QString());
    QCOMPARE(banc.sauvegarde.erreurGeste(), QStringLiteral("Choisissez le fichier où écrire la sauvegarde chiffrée."));
    QCOMPARE(banc.serveur.requetes.size(), 0);
}

QTEST_MAIN(TestSauvegarde)
#include "tst_sauvegarde.moc"
