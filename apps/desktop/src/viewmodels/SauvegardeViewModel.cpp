#include "viewmodels/SauvegardeViewModel.h"

#include "api/ApiClient.h"
#include "diagnostics/Redaction.h"
#include "events/EventStreamService.h"
#include "services/TelechargementFlux.h"
#include "storage/ChiffrementSauvegarde.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonObject>
#include <QLocale>
#include <QSaveFile>
#include <QStandardPaths>
#include <QTimer>
#include <QUrl>

namespace acp {

namespace {

const QString kRouteLancement = QStringLiteral("/api/ops/backup");
const QString kRouteEtat = QStringLiteral("/api/actions/backup/status");
const QString kRouteTelechargement = QStringLiteral("/api/ops/backup/download");
const QString kRouteFichiers = QStringLiteral("/api/files");

QString archiveRestante(const QString &archive)
{
    return QStringLiteral("L'archive non chiffrée reste sur le volume de Hermes : %1. Elle contient .env et auth.json : "
                          "supprimez-la.")
        .arg(archive);
}

} // namespace

SauvegardeViewModel::SauvegardeViewModel(ApiClient *client, EventStreamService *flux,
                                         std::unique_ptr<ProtecteurDonnees> protecteur, QObject *parent)
    : PageViewModel(flux, parent)
    , m_client(client)
    , m_protecteur(std::move(protecteur))
    , m_flux(new TelechargementFlux(client, this))
    , m_minuterie(new QTimer(this))
{
    m_minuterie->setSingleShot(true);
    connect(m_minuterie, &QTimer::timeout, this, &SauvegardeViewModel::suivre);
    connect(m_flux, &TelechargementFlux::progression, this, [this](qint64 recus, qint64) {
        m_progression = QStringLiteral("%1 reçus et chiffrés").arg(formaterTaille(recus));
        emit progressionChange();
    });
    connect(m_flux, &TelechargementFlux::termine, this, &SauvegardeViewModel::apresTelechargement);
    connect(m_flux, &TelechargementFlux::echoue, this, &SauvegardeViewModel::echouer);
    // Session perdue (déconnexion, jeton refusé) : l'export s'arrête, sans fichier partiel. La
    // suppression de l'archive, déjà envoyée avec son porteur, est laissée finir : l'interrompre
    // rendrait son résultat inconnu.
    if (flux) {
        connect(flux, &EventStreamService::sourcesChange, this, [this] {
            if (interruptible() && !this->flux()->sessionOuverte()) {
                echouer(QStringLiteral("Session perdue : l'export est arrêté, aucun fichier n'est écrit sur ce PC."));
            }
        });
    }
}

SauvegardeViewModel::~SauvegardeViewModel()
{
    m_flux->disconnect(this);
    nettoyer();
}

void SauvegardeViewModel::setPlafond(qint64 octets)
{
    m_flux->setPlafond(octets);
}

bool SauvegardeViewModel::chiffrementDisponible() const
{
    return m_protecteur && m_protecteur->disponible();
}

QString SauvegardeViewModel::etape() const
{
    switch (m_phase) {
    case Phase::Repos: return QStringLiteral("Aucun export en cours");
    case Phase::Lancement: return QStringLiteral("Demande de sauvegarde envoyée à Hermes…");
    case Phase::Archivage: return QStringLiteral("Hermes crée l'archive…");
    case Phase::Telechargement: return QStringLiteral("Téléchargement et chiffrement…");
    case Phase::Suppression: return QStringLiteral("Suppression de l'archive non chiffrée du volume de Hermes…");
    case Phase::Termine: return QStringLiteral("Export terminé");
    case Phase::Echec: return QStringLiteral("Export échoué");
    }
    return QStringLiteral("Inconnu");
}

QString SauvegardeViewModel::etapeCle() const
{
    switch (m_phase) {
    case Phase::Repos: return QStringLiteral("pending");
    case Phase::Termine: return QStringLiteral("succeeded");
    case Phase::Echec: return QStringLiteral("failed");
    default: return QStringLiteral("running");
    }
}

bool SauvegardeViewModel::interruptible() const
{
    return m_phase == Phase::Lancement || m_phase == Phase::Archivage || m_phase == Phase::Telechargement;
}

bool SauvegardeViewModel::enCours() const
{
    return m_phase == Phase::Lancement || m_phase == Phase::Archivage || m_phase == Phase::Telechargement
        || m_phase == Phase::Suppression;
}

void SauvegardeViewModel::passer(Phase phase)
{
    m_phase = phase;
    emit etatChange();
}

// --- Fonctions pures ---------------------------------------------------------------------------

QString SauvegardeViewModel::cheminLocal(const QString &saisie)
{
    const QString texte = saisie.trimmed();
    if (texte.startsWith(QLatin1String("file:"), Qt::CaseInsensitive)) {
        return QDir::toNativeSeparators(QUrl(texte).toLocalFile());
    }
    return texte.isEmpty() ? QString() : QDir::toNativeSeparators(texte);
}

QString SauvegardeViewModel::formaterTaille(qint64 octets)
{
    const QLocale francais(QLocale::French);
    if (octets < 1024) {
        return QStringLiteral("%1 o").arg(octets);
    }
    const QStringList unites = {QStringLiteral("Kio"), QStringLiteral("Mio"), QStringLiteral("Gio")};
    double valeur = static_cast<double>(octets) / 1024.0;
    qsizetype rang = 0;
    while (valeur >= 1024.0 && rang + 1 < unites.size()) {
        valeur /= 1024.0;
        ++rang;
    }
    return QStringLiteral("%1 %2").arg(francais.toString(valeur, 'f', 1), unites.at(rang));
}

QString SauvegardeViewModel::formaterDuree(qint64 millisecondes)
{
    const qint64 secondes = millisecondes / 1000;
    if (secondes < 60) {
        return QStringLiteral("%1 s").arg(secondes);
    }
    return QStringLiteral("%1 min %2 s").arg(secondes / 60).arg(secondes % 60);
}

QString SauvegardeViewModel::journalExpurge(const QJsonValue &lignes)
{
    QStringList texte;
    for (const QJsonValue &ligne : lignes.toArray()) {
        if (ligne.isString()) {
            texte.append(ligne.toString());
        }
    }
    if (texte.size() > 20) {
        texte = texte.mid(texte.size() - 20);
    }
    return redactSecrets(texte.join(QLatin1Char('\n')));
}

QString SauvegardeViewModel::proposerDestination() const
{
    QString dossier = QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation);
    if (dossier.isEmpty()) {
        dossier = QDir::homePath();
    }
    const QString nom = QStringLiteral("hermes-sauvegarde-%1.acpb")
                            .arg(QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd-HHmmss")));
    return QDir::toNativeSeparators(QDir(dossier).filePath(nom));
}

// --- Export ------------------------------------------------------------------------------------

void SauvegardeViewModel::exporter(const QString &destination)
{
    if (enCours() || gesteEnCours()) {
        return;
    }
    const QString chemin = cheminLocal(destination);
    if (chemin.isEmpty()) {
        echouerGeste(QStringLiteral("Choisissez le fichier où écrire la sauvegarde chiffrée."));
        return;
    }
    if (!chiffrementDisponible()) {
        echouerGeste(QStringLiteral("Le chiffrement DPAPI n'est disponible que sous Windows : aucun export n'est lancé."));
        return;
    }
    nettoyer();
    m_destination = chemin;
    m_archive.clear();
    m_journal.clear();
    m_progression.clear();
    m_resultat.clear();
    m_empreinteArchive.clear();
    m_echecsSuivi = 0;
    m_chrono.start();
    debuterGeste();
    passer(Phase::Lancement);

    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = kRouteLancement;
    requete.body = QJsonDocument(QJsonObject{});
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const QJsonValue archive = reponse.json.object().value(QStringLiteral("archive"));
        if (!archive.isString() || archive.toString().trimmed().isEmpty()) {
            echouer(QStringLiteral("Hermes n'a pas indiqué l'archive produite : rien n'est téléchargé."));
            return;
        }
        m_archive = archive.toString();
        passer(Phase::Archivage);
        programmerSuivi();
    });
    connect(m_appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        if (erreur.kind() != ApiFailure::Cancelled) {
            echouer(messageDuRefus(erreur));
        }
    });
}

void SauvegardeViewModel::programmerSuivi()
{
    m_minuterie->start(m_intervalle);
}

void SauvegardeViewModel::suivre()
{
    if (m_phase != Phase::Archivage) {
        return;
    }
    if (m_chrono.elapsed() > std::chrono::duration_cast<std::chrono::milliseconds>(kDureeMaximale).count()) {
        echouer(QStringLiteral("La sauvegarde de Hermes dure plus de 30 minutes : le suivi est arrêté."));
        return;
    }
    ApiRequest requete;
    requete.path = kRouteEtat;
    requete.query.addQueryItem(QStringLiteral("lines"), QStringLiteral("40"));
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        if (m_phase != Phase::Archivage) {
            return;
        }
        m_echecsSuivi = 0;
        const QJsonObject etat = reponse.json.object();
        if (etat.value(QStringLiteral("running")) == QJsonValue(true)) {
            programmerSuivi();
            return;
        }
        const QJsonValue code = etat.value(QStringLiteral("exit_code"));
        if (code.isDouble() && code.toInt() == 0) {
            telecharger();
            return;
        }
        m_journal = journalExpurge(etat.value(QStringLiteral("lines")));
        echouer(code.isDouble()
                    ? QStringLiteral("La sauvegarde de Hermes a échoué (code de sortie %1) : voir le journal ci-dessous.")
                          .arg(code.toInt())
                    : QStringLiteral("La sauvegarde de Hermes s'est arrêtée sans code de sortie connu : voir le journal "
                                     "ci-dessous."));
    });
    connect(m_appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        if (m_phase != Phase::Archivage || erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        if (++m_echecsSuivi >= 3) {
            echouer(QStringLiteral("Suivi de la sauvegarde impossible : %1").arg(messageDuRefus(erreur)));
            return;
        }
        programmerSuivi();
    });
}

void SauvegardeViewModel::telecharger()
{
    m_fichier = std::make_unique<QSaveFile>(m_destination);
    if (!m_fichier->open(QIODevice::WriteOnly)) {
        echouer(QStringLiteral("Impossible d'écrire %1 : %2").arg(m_destination, m_fichier->errorString()));
        return;
    }
    m_chiffreur = std::make_unique<ChiffreurSauvegarde>(*m_protecteur, m_fichier.get());
    QString erreur;
    if (!m_chiffreur->commencer(&erreur)) {
        echouer(erreur);
        return;
    }
    passer(Phase::Telechargement);
    QUrlQuery requete;
    requete.addQueryItem(QStringLiteral("archive"), m_archive);
    m_flux->demarrer(kRouteTelechargement, requete, [this](QByteArrayView morceau, QString *erreurPuits) {
        return m_chiffreur && m_chiffreur->ajouter(morceau, erreurPuits);
    });
}

void SauvegardeViewModel::apresTelechargement()
{
    if (m_phase != Phase::Telechargement || !m_chiffreur || !m_fichier) {
        return;
    }
    QString erreur;
    if (!m_chiffreur->terminer(&erreur)) {
        echouer(erreur);
        return;
    }
    if (!m_fichier->commit()) {
        echouer(QStringLiteral("Écriture finale de %1 impossible : %2").arg(m_destination, m_fichier->errorString()));
        return;
    }
    m_empreinteArchive = m_chiffreur->empreinteClaire();
    m_resultat = QVariantMap{
        {QStringLiteral("fichier"), m_destination},
        {QStringLiteral("taille"), formaterTaille(m_chiffreur->octetsEcrits())},
        {QStringLiteral("tailleArchive"), formaterTaille(m_chiffreur->octetsClairs())},
        {QStringLiteral("empreinte"), QString::fromLatin1(m_chiffreur->empreinteChiffree())},
        {QStringLiteral("archiveRestante"), QString()},
        {QStringLiteral("suppression"), QString()},
    };
    m_chiffreur.reset();
    m_fichier.reset();
    supprimerArchive();
}

void SauvegardeViewModel::supprimerArchive()
{
    passer(Phase::Suppression);
    ApiRequest requete;
    requete.method = QByteArrayLiteral("DELETE");
    requete.path = kRouteFichiers;
    requete.body = QJsonDocument(QJsonObject{{QStringLiteral("path"), m_archive}});
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this](const ApiResponse &) {
        m_resultat.insert(QStringLiteral("suppression"), QStringLiteral("Archive non chiffrée supprimée du volume de Hermes."));
        conclure();
    });
    connect(m_appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        if (erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        m_resultat.insert(QStringLiteral("archiveRestante"), m_archive);
        m_resultat.insert(QStringLiteral("suppression"),
                          archiveRestante(m_archive) + QStringLiteral(" Refus de Hermes : %1").arg(messageDuRefus(erreur)));
        conclure();
    });
}

void SauvegardeViewModel::conclure()
{
    m_resultat.insert(QStringLiteral("duree"), formaterDuree(m_chrono.elapsed()));
    passer(Phase::Termine);
    terminerGeste(m_resultat.value(QStringLiteral("archiveRestante")).toString().isEmpty()
                      ? QStringLiteral("Sauvegarde exportée et chiffrée sur ce PC.")
                      : QStringLiteral("Sauvegarde exportée et chiffrée sur ce PC ; l'archive non chiffrée reste sur le "
                                       "volume de Hermes (voir ci-dessous)."));
}

void SauvegardeViewModel::nettoyer()
{
    m_minuterie->stop();
    if (m_appel) {
        m_appel->disconnect(this);
        m_appel->abort();
    }
    if (m_flux->enCours()) {
        const QSignalBlocker bloqueur(m_flux);
        m_flux->annuler();
    }
    m_chiffreur.reset();
    if (m_fichier) {
        // Aucun fichier partiel : QSaveFile n'écrit la destination qu'à commit().
        m_fichier->cancelWriting();
        m_fichier.reset();
    }
}

void SauvegardeViewModel::echouer(const QString &message)
{
    if (m_phase == Phase::Echec || m_phase == Phase::Termine || m_phase == Phase::Repos) {
        return;
    }
    nettoyer();
    if (!m_archive.isEmpty()) {
        // Insertion, pas remplacement : après l'écriture du fichier, son résultat reste dit.
        m_resultat.insert(QStringLiteral("archiveRestante"), m_archive);
        m_resultat.insert(QStringLiteral("suppression"), archiveRestante(m_archive));
    }
    passer(Phase::Echec);
    echouerGeste(message);
}

void SauvegardeViewModel::annuler()
{
    // La suppression de l'archive n'est pas interrompue : son résultat serait inconnu.
    if (!interruptible()) {
        return;
    }
    echouer(QStringLiteral("Export annulé. Une sauvegarde déjà lancée continue côté Hermes jusqu'à son terme, et son "
                           "archive non chiffrée reste sur le volume de Hermes."));
}

void SauvegardeViewModel::reinitialiser()
{
    if (enCours()) {
        return;
    }
    nettoyer();
    m_resultat.clear();
    m_journal.clear();
    m_progression.clear();
    effacerGeste();
    passer(Phase::Repos);
    emit progressionChange();
}

// --- Déchiffrement -----------------------------------------------------------------------------

void SauvegardeViewModel::dechiffrer(const QString &source, const QString &destination)
{
    if (enCours() || gesteEnCours()) {
        return;
    }
    const QString cheminSource = cheminLocal(source);
    const QString cheminDestination = cheminLocal(destination);
    if (cheminSource.isEmpty() || cheminDestination.isEmpty()) {
        echouerGeste(QStringLiteral("Choisissez la sauvegarde chiffrée et l'archive à écrire."));
        return;
    }
    if (QDir::cleanPath(QDir::fromNativeSeparators(cheminSource)).compare(QDir::cleanPath(QDir::fromNativeSeparators(cheminDestination)),
                                                                          Qt::CaseInsensitive)
        == 0) {
        echouerGeste(QStringLiteral("L'archive déchiffrée doit être écrite dans un autre fichier que la sauvegarde."));
        return;
    }
    QFile entree(cheminSource);
    if (!entree.open(QIODevice::ReadOnly)) {
        echouerGeste(QStringLiteral("Lecture de %1 impossible : %2").arg(cheminSource, entree.errorString()));
        return;
    }
    QSaveFile sortie(cheminDestination);
    if (!sortie.open(QIODevice::WriteOnly)) {
        echouerGeste(QStringLiteral("Écriture de %1 impossible : %2").arg(cheminDestination, sortie.errorString()));
        return;
    }
    QString erreur;
    if (!m_protecteur || !dechiffrerSauvegarde(*m_protecteur, &entree, &sortie, &erreur)) {
        sortie.cancelWriting();
        echouerGeste(erreur.isEmpty() ? QStringLiteral("Déchiffrement indisponible sur ce système.") : erreur);
        return;
    }
    if (!sortie.commit()) {
        echouerGeste(QStringLiteral("Écriture finale de %1 impossible : %2").arg(cheminDestination, sortie.errorString()));
        return;
    }
    terminerGeste(QStringLiteral("Archive déchiffrée : %1. Elle contient .env et auth.json en clair : gardez-la hors de "
                                 "tout partage et supprimez-la après la restauration.")
                      .arg(cheminDestination));
}

} // namespace acp
