#include "services/ArtifactDownload.h"
#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "diagnostics/Redaction.h"

#include <QCryptographicHash>
#include <QFileInfo>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QSaveFile>
#include <QTimer>

namespace acp {
ArtifactDownload::ArtifactDownload(ApiClient *client, QObject *parent)
    : QObject(parent), m_client(client), m_deadline(new QTimer(this))
{
    m_deadline->setSingleShot(true);
    connect(m_deadline, &QTimer::timeout, this, [this] {
        fail(QStringLiteral("Téléchargement interrompu : durée maximale de dix minutes dépassée."));
    });
    connect(client, &ApiClient::baseUrlChanged, this, &ArtifactDownload::reset);
    connect(client, &ApiClient::sessionStateCleared, this, &ArtifactDownload::reset);
}

ArtifactDownload::~ArtifactDownload()
{
    releaseReply();
}

QString ArtifactDownload::safeFileName(const QString &name)
{
    QString safe = name;
    safe.replace(QLatin1Char('\\'), QLatin1Char('/'));
    safe = safe.section(QLatin1Char('/'), -1);
    safe.replace(QRegularExpression(QStringLiteral("[<>:\"/\\\\|?*\\x00-\\x1f\\x7f\\x{202a}-\\x{202e}\\x{2066}-\\x{2069}]")), QStringLiteral("_"));
    safe = safe.trimmed().left(160);
    while (safe.endsWith(QLatin1Char('.')) || safe.endsWith(QLatin1Char(' ')))
        safe.chop(1);
    if (safe.isEmpty() || safe == QStringLiteral(".") || safe == QStringLiteral(".."))
        safe = QStringLiteral("livrable.bin");
    const QString stem = safe.section(QLatin1Char('.'), 0, 0);
    if (QRegularExpression(QStringLiteral("^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])$"),
                           QRegularExpression::CaseInsensitiveOption).match(stem).hasMatch())
        safe.prepend(QLatin1Char('_'));
    return safe;
}

void ArtifactDownload::start(const QString &artifactId, const QUrl &destination,
                             qint64 expectedBytes, const QString &checksum)
{
    reset();
    static const QRegularExpression identifier(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9_-]{0,199}$"));
    static const QRegularExpression digest(QStringLiteral("^[a-fA-F0-9]{64}$"));
    if (!m_client->isConfigured() || !identifier.match(artifactId).hasMatch()) {
        fail(QStringLiteral("Serveur ou identifiant de livrable invalide."));
        return;
    }
    if (!destination.isLocalFile() || destination.toLocalFile().isEmpty()
        || QFileInfo(destination.toLocalFile()).isDir()) {
        fail(QStringLiteral("Choisissez un fichier local de destination."));
        return;
    }
    if (expectedBytes < 0 || expectedBytes > MaximumBytes) {
        fail(QStringLiteral("Export refusé : la limite de la station est de 512 Mio."));
        return;
    }
    if (!checksum.isEmpty() && !digest.match(checksum).hasMatch()) {
        fail(QStringLiteral("Empreinte du livrable illisible ; export refusé."));
        return;
    }
    m_expected = expectedBytes;
    m_checksum = checksum.toLower();
    m_destination = destination;
    m_file = std::make_unique<QSaveFile>(destination.toLocalFile());
    m_file->setDirectWriteFallback(false);
    if (!m_file->open(QIODevice::WriteOnly)) {
        fail(QStringLiteral("Impossible de préparer le fichier de destination : %1").arg(m_file->errorString()));
        return;
    }
    m_hash = std::make_unique<QCryptographicHash>(QCryptographicHash::Sha256);
    QNetworkRequest request(m_client->resolve(QStringLiteral("/artifacts/%1/content").arg(artifactId)));
    request.setAttribute(QNetworkRequest::CookieSaveControlAttribute, QNetworkRequest::Manual);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setRawHeader(QByteArrayLiteral("Accept"), QByteArrayLiteral("application/octet-stream"));
    request.setRawHeader(QByteArrayLiteral("Accept-Encoding"), QByteArrayLiteral("identity"));
    request.setTransferTimeout(30000);
    // Le gestionnaire unique conserve le cookie de session. Aucun jeton ni URL signée.
    m_reply = m_client->networkAccessManager()->get(request);
    m_reply->setReadBufferSize(128 * 1024);
    connect(m_reply, &QNetworkReply::readyRead, this, &ArtifactDownload::consume);
    connect(m_reply, &QNetworkReply::finished, this, &ArtifactDownload::finish);
    m_deadline->start(10 * 60 * 1000);
    emit changed();
}

void ArtifactDownload::consume()
{
    if (!m_reply || !m_file)
        return;
    const int status = m_reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (status != 200) {
        // Une page d'erreur, un fragment 206 ou une redirection n'est jamais un fichier.
        const QByteArray body = m_reply->read(4096);
        const QString detail = redactSecrets(extractProblemDetail(body));
        fail(ApiError::fromHttpStatus(status, detail).message());
        if (status == 401)
            emit m_client->unauthorizedObserved();
        return;
    }
    bool lengthOk = false;
    const QByteArray lengthHeader = m_reply->rawHeader(QByteArrayLiteral("Content-Length"));
    const qint64 announced = lengthHeader.toLongLong(&lengthOk);
    if (!lengthHeader.isEmpty() && (!lengthOk || announced != m_expected)) {
        fail(QStringLiteral("Taille annoncée différente des métadonnées ; export interrompu."));
        return;
    }
    while (m_reply && m_reply->bytesAvailable() > 0) {
        const QByteArray block = m_reply->read(64 * 1024);
        if (block.isEmpty())
            break;
        if (m_received + block.size() > m_expected || m_received + block.size() > MaximumBytes) {
            fail(QStringLiteral("Le contenu dépasse la taille annoncée ; export interrompu."));
            return;
        }
        if (m_file->write(block) != block.size()) {
            fail(QStringLiteral("Écriture du fichier impossible ; export interrompu."));
            return;
        }
        m_hash->addData(block);
        m_received += block.size();
    }
    emit changed();
}

void ArtifactDownload::finish()
{
    if (!m_reply)
        return;
    if (m_reply->error() != QNetworkReply::NoError) {
        const int status = m_reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QString detail = redactSecrets(extractProblemDetail(m_reply->read(4096)));
        fail(status ? ApiError::fromHttpStatus(status, detail).message()
                    : QStringLiteral("Téléchargement interrompu par le réseau."));
        if (status == 401)
            emit m_client->unauthorizedObserved();
        return;
    }
    consume();
    if (!m_reply)
        return;
    if (m_received != m_expected) {
        fail(QStringLiteral("Contenu incomplet : le fichier de destination est conservé intact."));
        return;
    }
    if (!m_checksum.isEmpty() && QString::fromLatin1(m_hash->result().toHex()) != m_checksum) {
        fail(QStringLiteral("Empreinte SHA-256 différente ; export refusé."));
        return;
    }
    releaseReply();
    if (!m_file->commit()) {
        fail(QStringLiteral("Impossible de finaliser le fichier de destination."));
        return;
    }
    m_file.reset();
    m_hash.reset();
    m_savedFile = m_destination;
    emit changed();
    emit succeeded(m_savedFile);
}

void ArtifactDownload::releaseReply()
{
    m_deadline->stop();
    if (m_reply) {
        QNetworkReply *reply = m_reply;
        m_reply = nullptr;
        disconnect(reply, nullptr, this, nullptr);
        if (!reply->isFinished())
            reply->abort();
        reply->deleteLater();
    }
}

void ArtifactDownload::fail(const QString &reason)
{
    releaseReply();
    if (m_file)
        m_file->cancelWriting();
    m_file.reset();
    m_hash.reset();
    m_error = redactSecrets(reason);
    emit changed();
    emit failed(m_error);
}

void ArtifactDownload::cancel()
{
    if (busy())
        fail(QStringLiteral("Téléchargement annulé ; aucun fichier partiel conservé."));
}

void ArtifactDownload::reset()
{
    releaseReply();
    if (m_file)
        m_file->cancelWriting();
    m_file.reset();
    m_hash.reset();
    m_received = 0;
    m_expected = 0;
    m_error.clear();
    m_savedFile.clear();
    emit changed();
}
} // namespace acp
