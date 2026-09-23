#include "services/UpdateService.h"
#include <QDesktopServices>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QTimer>

namespace acp {
namespace {
constexpr qsizetype MaximumResponse = 2 * 1024 * 1024;
const QString Repository = QStringLiteral("/Paul-Berdier/agent-company-platform");
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
}
UpdateService::UpdateService(QString version, QObject *parent)
    : QObject(parent), m_current(std::move(version)) {}
UpdateService::~UpdateService() {
    if (m_reply) { disconnect(m_reply, nullptr, this, nullptr); m_reply->abort(); }
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
    if (!release.value(QStringLiteral("draft")).isBool() || release.value(QStringLiteral("draft")).toBool()
        || !release.value(QStringLiteral("prerelease")).isBool()
        || (!prereleases && release.value(QStringLiteral("prerelease")).toBool())) return false;
    const auto tag = release.value(QStringLiteral("tag_name")).toString();
    Version version;
    if (!parseVersion(tag, version) || (!prereleases && !version.suffix.isEmpty())) return false;
    const QUrl url(release.value(QStringLiteral("html_url")).toString());
    return url.isValid() && url.scheme() == QStringLiteral("https")
        && url.host() == QStringLiteral("github.com") && url.port(-1) == -1
        && url.userInfo().isEmpty() && !url.hasQuery() && !url.hasFragment()
        && url.path() == Repository + QStringLiteral("/releases/tag/") + tag;
}
void UpdateService::setIncludePrereleases(bool enabled) {
    if (busy() || m_prereleases == enabled) return;
    m_prereleases = enabled;
    m_latest.clear(); m_notes.clear(); m_releaseUrl.clear(); m_available = false;
    m_status = QStringLiteral("Canal modifié ; lancez une nouvelle vérification.");
    emit changed();
}
void UpdateService::check() {
    if (busy()) return;
    m_latest.clear(); m_notes.clear(); m_releaseUrl.clear(); m_available = false;
    m_status = QStringLiteral("Vérification des publications GitHub…");
    const auto suffix = m_prereleases ? QStringLiteral("/releases?per_page=100") : QStringLiteral("/releases/latest");
    QNetworkRequest request(QUrl(QStringLiteral("https://api.github.com/repos") + Repository + suffix));
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
        if (!validateRelease(candidate, m_prereleases)) continue;
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
    emit changed();
}
void UpdateService::openRelease() {
    if (!m_available || m_releaseUrl.isEmpty()) return;
    if (!QDesktopServices::openUrl(m_releaseUrl)) fail(QStringLiteral("Impossible d'ouvrir la publication dans le navigateur."));
}
}
