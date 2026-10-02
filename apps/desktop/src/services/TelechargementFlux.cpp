#include "services/TelechargementFlux.h"

#include "api/ApiClient.h"

#include <QNetworkReply>

namespace acp {

namespace {

constexpr qsizetype kCorpsErreurMaximal = 64 * 1024;

QString taille(qint64 octets)
{
    return QStringLiteral("%1 Gio").arg(static_cast<double>(octets) / (1024.0 * 1024.0 * 1024.0), 0, 'f', 1);
}

} // namespace

TelechargementFlux::TelechargementFlux(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
{
}

TelechargementFlux::~TelechargementFlux()
{
    if (m_reponse) {
        m_reponse->disconnect(this);
        m_reponse->abort();
        m_reponse->deleteLater();
    }
}

int TelechargementFlux::statut() const
{
    if (!m_reponse) {
        return 0;
    }
    const QVariant valeur = m_reponse->attribute(QNetworkRequest::HttpStatusCodeAttribute);
    return valeur.isValid() ? valeur.toInt() : 0;
}

void TelechargementFlux::demarrer(const QString &chemin, const QUrlQuery &requete, Puits puits)
{
    if (m_reponse) {
        m_reponse->disconnect(this);
        m_reponse->abort();
        m_reponse->deleteLater();
        m_reponse = nullptr;
    }
    m_puits = std::move(puits);
    m_recus = 0;
    m_corpsErreur.clear();
    m_fini = false;
    ApiError refus;
    QNetworkReply *reponse = m_client->ouvrirFlux(chemin, requete, &refus);
    if (!reponse) {
        // Signal différé : l'appelant a fini de se brancher avant d'apprendre l'échec.
        QMetaObject::invokeMethod(this, [this, message = refus.message()] { echouer(message); }, Qt::QueuedConnection);
        return;
    }
    m_reponse = reponse;
    connect(reponse, &QNetworkReply::readyRead, this, &TelechargementFlux::lire);
    connect(reponse, &QNetworkReply::finished, this, &TelechargementFlux::finir);
}

void TelechargementFlux::lire()
{
    if (!m_reponse || m_fini) {
        return;
    }
    const QByteArray morceau = m_reponse->readAll();
    if (statut() != 200) {
        // Corps d'erreur : gardé (borné) pour le message, jamais livré au puits.
        if (m_corpsErreur.size() < kCorpsErreurMaximal) {
            m_corpsErreur.append(morceau.left(kCorpsErreurMaximal - m_corpsErreur.size()));
        }
        return;
    }
    m_recus += morceau.size();
    if (m_recus > m_plafond) {
        echouer(QStringLiteral("L'archive dépasse le plafond de %1 : téléchargement arrêté.").arg(taille(m_plafond)));
        return;
    }
    QString erreur;
    if (!m_puits || !m_puits(QByteArrayView(morceau), &erreur)) {
        echouer(erreur.isEmpty() ? QStringLiteral("Écriture locale refusée.") : erreur);
        return;
    }
    emit progression(m_recus, m_reponse ? m_reponse->header(QNetworkRequest::ContentLengthHeader).toLongLong() : -1);
}

void TelechargementFlux::finir()
{
    if (!m_reponse || m_fini) {
        return;
    }
    lire();
    if (m_fini || !m_reponse) {
        return;
    }
    const int code = statut();
    const QNetworkReply::NetworkError erreurReseau = m_reponse->error();
    if (code == 200 && erreurReseau == QNetworkReply::NoError) {
        m_fini = true;
        m_reponse->deleteLater();
        m_reponse = nullptr;
        emit termine(m_recus);
        return;
    }
    if (code >= 300) {
        echouer(ApiError::fromResponse(code, m_corpsErreur).message());
        return;
    }
    echouer(QStringLiteral("Téléchargement interrompu : %1").arg(libelleErreurReseau(erreurReseau)));
}

void TelechargementFlux::annuler()
{
    if (!m_reponse || m_fini) {
        return;
    }
    echouer(QStringLiteral("Téléchargement annulé."));
}

void TelechargementFlux::echouer(const QString &message)
{
    m_fini = true;
    if (m_reponse) {
        m_reponse->disconnect(this);
        m_reponse->abort();
        m_reponse->deleteLater();
        m_reponse = nullptr;
    }
    emit echoue(message);
}

} // namespace acp
