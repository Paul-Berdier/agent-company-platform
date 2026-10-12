#include "services/UpdateService.h"
#include "storage/SettingsStore.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QProcess>
#include <QRegularExpression>
#include <QSaveFile>
#include <QStandardPaths>
#include <QTimer>

namespace acp {
namespace {
constexpr qsizetype MaximumResponse = 2 * 1024 * 1024;
constexpr qsizetype MaximumSums = 64 * 1024;
constexpr qint64 MaximumInstaller = 512LL * 1024 * 1024;
constexpr int PremiereVerificationMs = 30 * 1000;
constexpr int IntervalleVerificationMs = 6 * 60 * 60 * 1000;
const QString Repository = QStringLiteral("/Paul-Berdier/agent-company-platform");
const QString FichierSommes = QStringLiteral("SHA256SUMS.txt");
const QString FichierEtat = QStringLiteral("attente.json");
struct Version { QStringList core; QStringList suffix; };
bool parseVersion(QString value, Version &out) {
    if (value.startsWith(QLatin1Char('v'))) value.remove(0, 1);
    static const QRegularExpression pattern(QStringLiteral(
        "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$"));
    const auto match = pattern.match(value);
    if (!match.hasMatch() || value.size() > 128) return false;
    out.core = {match.captured(1), match.captured(2), match.captured(3)};
    if (!match.captured(4).isEmpty()) out.suffix = match.captured(4).split(QLatin1Char('.'));
    const QRegularExpression numeric(QStringLiteral("^[0-9]+$"));
    for (const auto &part : out.suffix)
        if (numeric.match(part).hasMatch() && part.size() > 1 && part.startsWith(QLatin1Char('0'))) return false;
    return true;
}
int compareNumeric(const QString &a, const QString &b) {
    if (a.size() != b.size()) return a.size() < b.size() ? -1 : 1;
    return QString::compare(a, b, Qt::CaseSensitive);
}
QString sansV(QString tag) {
    if (tag.startsWith(QLatin1Char('v'))) tag.remove(0, 1);
    return tag;
}
//! Nom exact de l'installeur d'une version (scripts/package-desktop.ps1) : rien d'autre n'est lancé.
QString nomInstalleur(const QString &tag) {
    return QStringLiteral("AgentCompanyPlatform-Setup-%1-x64.exe").arg(sansV(tag));
}
}
UpdateService::UpdateService(QString version, QObject *parent)
    : UpdateService(std::move(version), nullptr, Sources{}, parent) {}
UpdateService::UpdateService(QString version, SettingsStore *settings, Sources sources, QObject *parent)
    : QObject(parent), m_settings(settings), m_sources(std::move(sources)), m_current(std::move(version)) {
    if (!m_sources.lanceur)
        m_sources.lanceur = [](const QString &programme, const QStringList &arguments) {
            return QProcess::startDetached(programme, arguments);
        };
}
UpdateService::~UpdateService() {
    if (m_reply) { disconnect(m_reply, nullptr, this, nullptr); m_reply->abort(); }
    if (m_file) m_file->cancelWriting();
    delete m_hash;
}
int UpdateService::compareVersions(const QString &left, const QString &right, bool *valid) {
    Version a, b;
    *valid = parseVersion(left, a) && parseVersion(right, b);
    if (!*valid) return 0;
    for (int i = 0; i < 3; ++i) {
        const int result = compareNumeric(a.core.at(i), b.core.at(i));
        if (result) return result;
    }
    if (a.suffix.isEmpty() || b.suffix.isEmpty())
        return a.suffix.isEmpty() ? (b.suffix.isEmpty() ? 0 : 1) : -1;
    const QRegularExpression numeric(QStringLiteral("^[0-9]+$"));
    for (qsizetype i = 0; i < qMin(a.suffix.size(), b.suffix.size()); ++i) {
        const auto aa = a.suffix.at(i), bb = b.suffix.at(i);
        const bool an = numeric.match(aa).hasMatch(), bn = numeric.match(bb).hasMatch();
        const int result = an && bn ? compareNumeric(aa, bb)
            : an != bn ? (an ? -1 : 1) : QString::compare(aa, bb, Qt::CaseSensitive);
        if (result) return result;
    }
    return a.suffix.size() < b.suffix.size() ? -1 : a.suffix.size() == b.suffix.size() ? 0 : 1;
}
bool UpdateService::validateRelease(const QJsonObject &release, bool prereleases) {
    return validateRelease(release, prereleases, QStringLiteral("https://github.com") + Repository);
}
bool UpdateService::validateRelease(const QJsonObject &release, bool prereleases, const QString &depot) {
    if (!release.value(QStringLiteral("draft")).isBool() || release.value(QStringLiteral("draft")).toBool()
        || !release.value(QStringLiteral("prerelease")).isBool()
        || (!prereleases && release.value(QStringLiteral("prerelease")).toBool())) return false;
    const auto tag = release.value(QStringLiteral("tag_name")).toString();
    Version version;
    if (!parseVersion(tag, version) || (!prereleases && !version.suffix.isEmpty())) return false;
    const QUrl attendue(depot + QStringLiteral("/releases/tag/") + tag);
    const QUrl url(release.value(QStringLiteral("html_url")).toString());
    return url.isValid() && url.scheme() == attendue.scheme() && url.host() == attendue.host()
        && url.port(-1) == attendue.port(-1) && url.userInfo().isEmpty() && !url.hasQuery() && !url.hasFragment()
        && url.path() == attendue.path();
}
QString UpdateService::empreinteDans(const QByteArray &sommes, const QString &nom) {
    static const QRegularExpression ligne(QStringLiteral("^([0-9a-fA-F]{64})[ \\t]+\\*?(.+)$"));
    QString trouvee;
    for (const QByteArray &brute : sommes.split('\n')) {
        const auto match = ligne.match(QString::fromUtf8(brute).trimmed());
        if (!match.hasMatch() || match.captured(2).trimmed() != nom) continue;
        const QString empreinte = match.captured(1).toLower();
        if (!trouvee.isEmpty() && trouvee != empreinte) return {}; // deux empreintes pour un fichier : refus
        trouvee = empreinte;
    }
    return trouvee;
}
QStringList UpdateService::argumentsInstalleur() {
    // Inno Setup : installation sans fenêtre ni question, fermeture de la station si elle tourne,
    // relance par l'installeur une fois les fichiers remplacés (ACPRELANCER, AgentCompanyPlatform.iss).
    return {QStringLiteral("/VERYSILENT"), QStringLiteral("/SUPPRESSMSGBOXES"), QStringLiteral("/NORESTART"),
            QStringLiteral("/CLOSEAPPLICATIONS"), QStringLiteral("/ACPRELANCER=1")};
}
bool UpdateService::autoInstall() const {
    return m_settings ? m_settings->autoInstallUpdates() : m_autoInstallMemoire;
}
void UpdateService::setAutoInstall(bool enabled) {
    if (autoInstall() == enabled) return;
    if (m_settings) m_settings->setAutoInstallUpdates(enabled); else m_autoInstallMemoire = enabled;
    if (enabled) startAutomaticChecks();
    else if (m_timer) m_timer->stop();
    emit changed();
}
bool UpdateService::installationPossible() const {
    if (m_sources.installationPermise.has_value()) return *m_sources.installationPermise;
#ifdef Q_OS_WIN
    // Seule une station posée par son installeur se met à jour ainsi ; la version portable, non.
    return QFileInfo::exists(QCoreApplication::applicationDirPath() + QStringLiteral("/unins000.exe"));
#else
    return false;
#endif
}
QString UpdateService::dossierTelechargements() const {
    if (!m_sources.dossier.isEmpty()) return m_sources.dossier;
    return QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + QStringLiteral("/mises-a-jour");
}
void UpdateService::setIncludePrereleases(bool enabled) {
    if (busy() || m_downloading || m_prereleases == enabled) return;
    m_prereleases = enabled;
    m_latest.clear(); m_notes.clear(); m_releaseUrl.clear(); m_available = false;
    m_status = QStringLiteral("Canal modifié ; lancez une nouvelle vérification.");
    emit changed();
}
void UpdateService::startAutomaticChecks() {
    if (!autoInstall()) return;
    if (!m_timer) {
        m_timer = new QTimer(this);
        connect(m_timer, &QTimer::timeout, this, [this] {
            m_timer->setInterval(IntervalleVerificationMs);
            if (!autoInstall()) { m_timer->stop(); return; }
            if (!busy() && !m_downloading) check();
        });
    }
    if (!m_timer->isActive()) { m_timer->setInterval(PremiereVerificationMs); m_timer->start(); }
}
QNetworkReply *UpdateService::get(const QUrl &url, const QByteArray &accept, int transferTimeoutMs) {
    QNetworkRequest request(url);
    request.setRawHeader("Accept", accept);
    request.setRawHeader("User-Agent", QByteArrayLiteral("acp-desktop/") + m_current.toUtf8());
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::UserVerifiedRedirectPolicy);
    request.setMaximumRedirectsAllowed(5);
    request.setAttribute(QNetworkRequest::CookieLoadControlAttribute, QNetworkRequest::Manual);
    request.setAttribute(QNetworkRequest::CookieSaveControlAttribute, QNetworkRequest::Manual);
    request.setTransferTimeout(transferTimeoutMs);
    auto *reply = m_network.get(request);
    // GitHub sert les fichiers joints par une redirection : seuls les hôtes admis sont suivis.
    connect(reply, &QNetworkReply::redirected, this, [this, reply](const QUrl &cible) {
        if (urlAdmise(cible)) reply->redirectAllowed();
        else if (m_reply == reply) abandonDownload(QStringLiteral("Redirection vers un hôte non admis : téléchargement refusé."));
    });
    return reply;
}
bool UpdateService::urlAdmise(const QUrl &url) const {
    const bool schemaAdmis = url.scheme() == QStringLiteral("https")
        || (m_sources.httpAutorise && url.scheme() == QStringLiteral("http"));
    return url.isValid() && schemaAdmis && url.userInfo().isEmpty() && m_sources.hotes.contains(url.host())
        && (url.port(-1) == -1 || m_sources.httpAutorise);
}
void UpdateService::check() {
    if (busy() || m_downloading) return;
    m_latest.clear(); m_notes.clear(); m_releaseUrl.clear(); m_available = false;
    m_installerUrl.clear(); m_sumsUrl.clear(); m_installerDigest.clear(); m_installerSize = -1;
    m_status = QStringLiteral("Vérification des publications GitHub…");
    const auto suffix = m_prereleases ? QStringLiteral("/releases?per_page=100") : QStringLiteral("/releases/latest");
    QNetworkRequest request(QUrl(m_sources.api.toString() + suffix));
    request.setRawHeader("Accept", "application/vnd.github+json");
    request.setRawHeader("User-Agent", QByteArrayLiteral("acp-desktop/") + m_current.toUtf8());
    request.setRawHeader("X-GitHub-Api-Version", "2022-11-28");
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setAttribute(QNetworkRequest::CookieLoadControlAttribute, QNetworkRequest::Manual);
    request.setAttribute(QNetworkRequest::CookieSaveControlAttribute, QNetworkRequest::Manual);
    request.setTransferTimeout(15000);
    m_reply = m_network.get(request);
    auto *reply = m_reply.data();
    reply->setReadBufferSize(MaximumResponse + 1);
    auto *deadline = new QTimer(reply);
    deadline->setSingleShot(true);
    connect(deadline, &QTimer::timeout, this, [this, reply] {
        if (m_reply == reply) fail(QStringLiteral("Délai de vérification dépassé."));
    });
    deadline->start(20000);
    connect(reply, &QNetworkReply::readyRead, this, [this, reply] {
        if (reply->bytesAvailable() > MaximumResponse) fail(QStringLiteral("Réponse GitHub trop volumineuse."));
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        if (m_reply != reply) return;
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (status == 404) { fail(QStringLiteral("Aucune publication publique accessible pour ce canal.")); return; }
        if (status == 403 || status == 429) { fail(QStringLiteral("GitHub a refusé la vérification ; réessayez plus tard.")); return; }
        if (reply->error() != QNetworkReply::NoError || status != 200) {
            fail(QStringLiteral("Vérification indisponible : réponse réseau ou TLS non valide.")); return;
        }
        const auto body = reply->readAll();
        m_reply = nullptr;
        reply->deleteLater();
        if (body.size() > MaximumResponse) { fail(QStringLiteral("Réponse GitHub trop volumineuse.")); return; }
        accept(body);
    });
    emit changed();
}
void UpdateService::fail(const QString &reason) {
    if (m_reply) {
        auto *reply = m_reply.data(); m_reply = nullptr;
        disconnect(reply, nullptr, this, nullptr); reply->abort(); reply->deleteLater();
    }
    m_available = false; m_releaseUrl.clear(); m_status = reason;
    emit changed();
}
void UpdateService::accept(const QByteArray &body) {
    const auto document = QJsonDocument::fromJson(body);
    QJsonArray candidates;
    if (m_prereleases && document.isArray()) candidates = document.array();
    else if (!m_prereleases && document.isObject()) candidates.append(document.object());
    else { fail(QStringLiteral("Réponse de publication illisible.")); return; }
    QJsonObject selected;
    for (const auto &value : candidates) {
        const auto candidate = value.toObject();
        if (!validateRelease(candidate, m_prereleases, m_sources.depot)) continue;
        bool valid = false;
        if (selected.isEmpty() || compareVersions(candidate.value(QStringLiteral("tag_name")).toString(), selected.value(QStringLiteral("tag_name")).toString(), &valid) > 0)
            selected = candidate;
    }
    if (selected.isEmpty()) { fail(QStringLiteral("Aucune publication admissible ; version actuelle non vérifiée.")); return; }
    m_latest = selected.value(QStringLiteral("tag_name")).toString();
    bool valid = false;
    const int comparison = compareVersions(m_latest, m_current, &valid);
    if (!valid) { fail(QStringLiteral("Version locale illisible ; comparaison impossible.")); return; }
    m_available = comparison > 0;
    m_releaseUrl = QUrl(selected.value(QStringLiteral("html_url")).toString());
    m_notes = selected.value(QStringLiteral("body")).toString().left(100000);
    m_status = m_available ? QStringLiteral("Une version plus récente est publiée.")
        : comparison == 0 ? QStringLiteral("La version installée correspond à la publication vérifiée.")
        : QStringLiteral("La version installée est plus récente que la publication vérifiée.");
    if (m_available) {
        // Fichiers joints admis : nom exact, adresse exacte de téléchargement de CETTE publication.
        m_installerName = nomInstalleur(m_latest);
        for (const auto &valeur : selected.value(QStringLiteral("assets")).toArray()) {
            const QJsonObject fichier = valeur.toObject();
            const QString nom = fichier.value(QStringLiteral("name")).toString();
            const QUrl url(fichier.value(QStringLiteral("browser_download_url")).toString());
            if (url != QUrl(m_sources.depot + QStringLiteral("/releases/download/") + m_latest + QLatin1Char('/') + nom))
                continue;
            if (nom == m_installerName) {
                const qint64 taille = fichier.value(QStringLiteral("size")).toInteger(-1);
                if (taille <= 0 || taille > MaximumInstaller) continue;
                m_installerUrl = url;
                m_installerSize = taille;
                const QString digest = fichier.value(QStringLiteral("digest")).toString();
                m_installerDigest = digest.startsWith(QStringLiteral("sha256:")) ? digest.mid(7).toLower() : QString();
            } else if (nom == FichierSommes) {
                m_sumsUrl = url;
            }
        }
        if (m_installerUrl.isEmpty() || m_sumsUrl.isEmpty()) {
            m_status = QStringLiteral("Une version plus récente est publiée, sans installeur ni SHA256SUMS.txt "
                                      "vérifiables : installez-la à la main depuis sa page.");
        } else if (m_ready && m_pendingVersion == m_latest) {
            m_status = QStringLiteral("Version %1 déjà téléchargée et vérifiée.").arg(m_latest);
        } else if (autoInstall() && installationPossible()) {
            emit changed();
            download(false);
            return;
        }
    }
    emit changed();
}
void UpdateService::openRelease() {
    if (!m_available || m_releaseUrl.isEmpty()) return;
    if (!QDesktopServices::openUrl(m_releaseUrl)) fail(QStringLiteral("Impossible d'ouvrir la publication dans le navigateur."));
}
void UpdateService::downloadAndInstall() {
    download(true);
}
void UpdateService::download(bool installAfter) {
    if (m_downloading) { m_installAfter = m_installAfter || installAfter; return; }
    if (m_ready && m_pendingVersion == m_latest) { if (installAfter) installNow(); return; }
    if (!installationPossible()) {
        m_status = QStringLiteral("Installation automatique impossible : seulement sous Windows, pour une station "
                                  "posée par son installeur (pas la version portable).");
        emit changed();
        return;
    }
    if (!m_available || m_installerUrl.isEmpty() || m_sumsUrl.isEmpty()) return;
    m_downloading = true;
    m_installAfter = installAfter;
    m_progress = 0;
    m_status = QStringLiteral("Téléchargement de la version %1…").arg(m_latest);
    m_reply = get(m_sumsUrl, "application/octet-stream", 30000);
    auto *reply = m_reply.data();
    connect(reply, &QNetworkReply::readyRead, this, [this, reply] {
        if (m_reply == reply && reply->bytesAvailable() > MaximumSums)
            abandonDownload(QStringLiteral("SHA256SUMS.txt trop volumineux : téléchargement refusé."));
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        if (m_reply != reply) return;
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (reply->error() != QNetworkReply::NoError || status != 200) {
            abandonDownload(QStringLiteral("SHA256SUMS.txt illisible : rien n'est téléchargé.")); return;
        }
        const QByteArray sommes = reply->readAll();
        m_reply = nullptr;
        reply->deleteLater();
        const QString empreinte = empreinteDans(sommes, m_installerName);
        if (sommes.size() > MaximumSums || empreinte.isEmpty()) {
            abandonDownload(QStringLiteral("SHA256SUMS.txt ne donne pas une empreinte unique pour %1 : rien n'est "
                                           "téléchargé.").arg(m_installerName));
            return;
        }
        if (!m_installerDigest.isEmpty() && m_installerDigest != empreinte) {
            abandonDownload(QStringLiteral("L'empreinte annoncée par GitHub diffère de SHA256SUMS.txt : rien n'est "
                                           "téléchargé."));
            return;
        }
        m_expectedSha256 = empreinte;
        downloadInstaller();
    });
    emit changed();
}
void UpdateService::downloadInstaller() {
    const QString dossier = dossierTelechargements();
    if (!QDir().mkpath(dossier)) { abandonDownload(QStringLiteral("Dossier des mises à jour impossible à créer.")); return; }
    m_file = new QSaveFile(dossier + QLatin1Char('/') + m_installerName, this);
    m_file->setDirectWriteFallback(false);
    if (!m_file->open(QIODevice::WriteOnly)) {
        abandonDownload(QStringLiteral("Écriture de l'installeur impossible : %1").arg(m_file->errorString()));
        return;
    }
    m_hash = new QCryptographicHash(QCryptographicHash::Sha256);
    m_received = 0;
    m_reply = get(m_installerUrl, "application/octet-stream", 60000);
    auto *reply = m_reply.data();
    const auto lire = [this, reply] {
        if (m_reply != reply || !m_file) return;
        const QByteArray morceau = reply->readAll();
        m_received += morceau.size();
        if (m_received > m_installerSize) {
            abandonDownload(QStringLiteral("Installeur plus volumineux qu'annoncé : téléchargement refusé."));
            return;
        }
        if (m_file->write(morceau) != morceau.size()) {
            abandonDownload(QStringLiteral("Écriture de l'installeur impossible : %1").arg(m_file->errorString()));
            return;
        }
        m_hash->addData(morceau);
        const int progression = int(m_received * 100 / m_installerSize);
        if (progression != m_progress) { m_progress = progression; emit changed(); }
    };
    connect(reply, &QNetworkReply::readyRead, this, lire);
    connect(reply, &QNetworkReply::finished, this, [this, reply, lire] {
        if (m_reply != reply) return;
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (reply->error() != QNetworkReply::NoError || status != 200) {
            abandonDownload(QStringLiteral("Téléchargement interrompu : rien n'est installé.")); return;
        }
        lire();
        if (m_reply == reply) finishDownload();
    });
    emit changed();
}
void UpdateService::finishDownload() {
    auto *reply = m_reply.data();
    m_reply = nullptr;
    if (reply) reply->deleteLater();
    if (m_received != m_installerSize) {
        abandonDownload(QStringLiteral("Taille de l'installeur différente de l'annonce : fichier supprimé, rien n'est installé."));
        return;
    }
    const QString obtenue = QString::fromLatin1(m_hash->result().toHex());
    if (obtenue != m_expectedSha256) {
        abandonDownload(QStringLiteral("Empreinte SHA-256 de l'installeur différente de SHA256SUMS.txt : fichier "
                                       "supprimé, rien n'est installé."));
        return;
    }
    const QString chemin = m_file->fileName();
    if (!m_file->commit()) {
        delete m_file; m_file = nullptr;
        abandonDownload(QStringLiteral("Enregistrement de l'installeur impossible."));
        return;
    }
    delete m_file; m_file = nullptr;
    delete m_hash; m_hash = nullptr;
    if (!m_pendingFile.isEmpty() && m_pendingFile != chemin) QFile::remove(m_pendingFile);
    const QJsonObject etat{{QStringLiteral("version"), m_latest}, {QStringLiteral("fichier"), m_installerName},
                           {QStringLiteral("sha256"), obtenue}, {QStringLiteral("tentatives"), 0}};
    if (!ecrireEtat(etat)) {
        QFile::remove(chemin);
        m_downloading = false; m_installAfter = false; m_progress = 0;
        m_status = QStringLiteral("Enregistrement de la mise à jour impossible : rien n'est installé.");
        emit changed();
        return;
    }
    m_downloading = false;
    m_progress = 100;
    m_ready = true;
    m_pendingVersion = m_latest;
    m_pendingFile = chemin;
    m_pendingSha256 = obtenue;
    m_status = autoInstall()
        ? QStringLiteral("Version %1 téléchargée et vérifiée (SHA-256) : elle s'installera au prochain démarrage de la "
                         "station, ou tout de suite avec « Installer maintenant ».").arg(m_latest)
        : QStringLiteral("Version %1 téléchargée et vérifiée (SHA-256) : « Installer maintenant » pour l'installer.")
              .arg(m_latest);
    const bool installer = m_installAfter;
    m_installAfter = false;
    emit changed();
    emit updateReady(m_latest);
    if (installer) installNow();
}
void UpdateService::abandonDownload(const QString &reason) {
    if (m_reply) {
        auto *reply = m_reply.data(); m_reply = nullptr;
        disconnect(reply, nullptr, this, nullptr); reply->abort(); reply->deleteLater();
    }
    if (m_file) { m_file->cancelWriting(); delete m_file; m_file = nullptr; }
    delete m_hash; m_hash = nullptr;
    m_downloading = false; m_installAfter = false; m_progress = 0; m_received = 0;
    m_status = reason;
    emit changed();
}
void UpdateService::installNow() {
    if (!m_ready || m_pendingFile.isEmpty()) return;
    if (!installationPossible()) {
        m_status = QStringLiteral("Installation automatique impossible sur ce poste : installez la version à la main.");
        emit changed();
        return;
    }
    // Le fichier est relu juste avant le lancement : une copie modifiée depuis le téléchargement est refusée.
    if (empreinteFichier(m_pendingFile) != m_pendingSha256) {
        clearPending();
        m_status = QStringLiteral("Installeur téléchargé absent ou modifié : supprimé, rien n'est installé.");
        emit changed();
        return;
    }
    QJsonObject etat = lireEtat();
    etat.insert(QStringLiteral("tentatives"), etat.value(QStringLiteral("tentatives")).toInt() + 1);
    if (!ecrireEtat(etat)) {
        m_status = QStringLiteral("Enregistrement de la tentative impossible : installation annulée.");
        emit changed();
        return;
    }
    if (!m_sources.lanceur(m_pendingFile, argumentsInstalleur())) {
        m_status = QStringLiteral("Impossible de lancer l'installeur de la version %1.").arg(m_pendingVersion);
        emit changed();
        return;
    }
    m_status = QStringLiteral("Installation de la version %1 : la station redémarre.").arg(m_pendingVersion);
    emit changed();
    emit quitRequested();
}
bool UpdateService::installPendingAtStartup() {
    const QJsonObject etat = lireEtat();
    if (etat.isEmpty()) return false;
    const QString version = etat.value(QStringLiteral("version")).toString();
    const QString fichier = etat.value(QStringLiteral("fichier")).toString();
    const QString sha256 = etat.value(QStringLiteral("sha256")).toString();
    bool valide = false;
    const int comparaison = compareVersions(version, m_current, &valide);
    static const QRegularExpression hex(QStringLiteral("^[0-9a-f]{64}$"));
    // État illisible, nom inattendu ou version déjà installée (ou plus ancienne) : tout est effacé.
    if (!valide || comparaison <= 0 || fichier != nomInstalleur(version) || !hex.match(sha256).hasMatch()) {
        // Seul un installeur nommé comme le produit les nomme est supprimé, jamais un autre fichier.
        static const QRegularExpression nomAdmis(QStringLiteral("^AgentCompanyPlatform-Setup-[0-9A-Za-z.+-]{1,128}-x64\\.exe$"));
        m_pendingFile = nomAdmis.match(fichier).hasMatch() ? dossierTelechargements() + QLatin1Char('/') + fichier : QString();
        clearPending();
        return false;
    }
    m_ready = true;
    m_pendingVersion = version;
    m_pendingFile = dossierTelechargements() + QLatin1Char('/') + fichier;
    m_pendingSha256 = sha256;
    m_status = QStringLiteral("Version %1 téléchargée et vérifiée : « Installer maintenant » pour l'installer.").arg(version);
    if (!autoInstall() || !installationPossible()) { emit changed(); return false; }
    if (etat.value(QStringLiteral("tentatives")).toInt() >= 1) {
        // L'installeur a déjà été lancé pour cette version et la station n'a pas changé : pas de boucle.
        m_status = QStringLiteral("L'installation automatique de la version %1 n'a pas abouti : « Installer "
                                  "maintenant » pour réessayer, ou installez-la à la main.").arg(version);
        emit changed();
        return false;
    }
    bool lancee = false;
    const auto connexion = connect(this, &UpdateService::quitRequested, this, [&lancee] { lancee = true; });
    installNow();
    disconnect(connexion);
    return lancee;
}
void UpdateService::clearPending() {
    if (!m_pendingFile.isEmpty()) QFile::remove(m_pendingFile);
    QFile::remove(cheminEtat());
    m_ready = false;
    m_pendingVersion.clear(); m_pendingFile.clear(); m_pendingSha256.clear();
}
QString UpdateService::cheminEtat() const {
    return dossierTelechargements() + QLatin1Char('/') + FichierEtat;
}
QJsonObject UpdateService::lireEtat() const {
    QFile fichier(cheminEtat());
    if (!fichier.open(QIODevice::ReadOnly) || fichier.size() > 4096) return {};
    const QJsonDocument document = QJsonDocument::fromJson(fichier.readAll());
    return document.isObject() ? document.object() : QJsonObject();
}
bool UpdateService::ecrireEtat(const QJsonObject &etat) const {
    QSaveFile fichier(cheminEtat());
    return QDir().mkpath(dossierTelechargements()) && fichier.open(QIODevice::WriteOnly)
        && fichier.write(QJsonDocument(etat).toJson(QJsonDocument::Compact)) > 0 && fichier.commit();
}
QString UpdateService::empreinteFichier(const QString &chemin) {
    QFile fichier(chemin);
    if (!fichier.open(QIODevice::ReadOnly)) return {};
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if (!hash.addData(&fichier)) return {};
    return QString::fromLatin1(hash.result().toHex());
}
}
