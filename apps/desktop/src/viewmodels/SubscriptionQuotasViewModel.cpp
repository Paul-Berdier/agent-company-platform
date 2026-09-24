#include "viewmodels/SubscriptionQuotasViewModel.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "auth/AuthManager.h"
#include "diagnostics/Redaction.h"
#include "models/JsonListModel.h"

#include <QHash>
#include <QLocale>
#include <QRegularExpression>
#include <QSet>
#include <QStringList>

#include <algorithm>
#include <cmath>
#include <numeric>
#include <optional>
#include <tuple>
#include <utility>

namespace acp {
namespace {

constexpr int kRefreshMs = 60 * 1000;
constexpr qsizetype kMaxItems = 200;
constexpr qsizetype kMaxWindows = 8;
constexpr double kMaxWindowMinutes = 527040; // 366 jours, comme le contrat serveur.
// L'API arrondit le reste à quatre décimales : l'écart toléré couvre cet arrondi et
// rien de plus. Un reste qui ne correspond pas est refusé, jamais recalculé.
constexpr double kRemainingTolerance = 0.0001;

const QString kUnknown = QStringLiteral("Inconnu");
// Identifiant réservé par le contrat serveur à une lecture en échec : ce n'est pas un
// compteur de la source, il n'est jamais affiché comme tel.
const QString kProbeLimitId = QStringLiteral("probe");
// Compteur unique d'une source qui n'en nomme aucun (ligne d'état Claude Code).
const QString kDefaultLimitId = QStringLiteral("default");
// Valeur par laquelle l'app-server Codex dit ignorer l'offre : elle reste « Inconnu ».
const QString kSourceUnknownPlan = QStringLiteral("unknown");
const QString kOwnerOnly = QStringLiteral(
    "Quotas d'abonnement réservés au propriétaire de la plateforme : l'usage d'un "
    "abonnement est personnel à son titulaire.");

// --- Forme validée de GET /subscription-quotas ------------------------------------

struct QuotaWindow {
    QString key;
    std::optional<double> used;
    std::optional<qint64> minutes;
    std::optional<QDateTime> resetsAt;
    std::optional<double> remaining;
};
struct QuotaCredits {
    bool hasCredits = false;
    bool unlimited = false;
    std::optional<QString> balance;
};
struct QuotaReport {
    QString provider;
    QString status;
    QString limitId;
    QString workerId;
    QString workerName;
    std::optional<QString> plan;
    std::optional<QString> reachedType;
    std::optional<QString> detail;
    QList<QuotaWindow> windows;
    std::optional<QuotaCredits> credits;
    std::optional<bool> limitReached;
    QDateTime observedAt;
    QDateTime receivedAt;
    bool stale = false;
};
struct QuotaListing {
    QList<QuotaReport> items;
    qint64 staleAfterSeconds = 0;
    QDateTime generatedAt;
};

/*!
    Lecteur strict : la première anomalie arrête tout et donne sa raison en français.
    Rien n'est rendu partiellement, rien n'est complété par défaut.
*/
class Reader
{
public:
    QString error;

    std::optional<QuotaListing> listing(const QJsonDocument &document)
    {
        if (!document.isObject()) {
            fail(QStringLiteral("objet JSON attendu à la racine"));
            return std::nullopt;
        }
        const QJsonObject root = document.object();
        if (!keys(root, {QStringLiteral("items"), QStringLiteral("stale_after_seconds"),
                         QStringLiteral("generated_at")}, QStringLiteral("la réponse"))) {
            return std::nullopt;
        }
        QuotaListing result;
        const QJsonValue staleAfter = root.value(QStringLiteral("stale_after_seconds"));
        if (!integer(staleAfter, 60, 604800)) {
            fail(QStringLiteral("« stale_after_seconds » doit être un entier de 60 à 604800"));
            return std::nullopt;
        }
        result.staleAfterSeconds = static_cast<qint64>(staleAfter.toDouble());
        const auto generated = instant(root.value(QStringLiteral("generated_at")));
        if (!generated) {
            fail(QStringLiteral("« generated_at » doit être un horodatage ISO 8601 avec fuseau"));
            return std::nullopt;
        }
        result.generatedAt = *generated;
        const QJsonValue items = root.value(QStringLiteral("items"));
        if (!items.isArray()) {
            fail(QStringLiteral("« items » doit être une liste"));
            return std::nullopt;
        }
        const QJsonArray array = items.toArray();
        if (array.size() > kMaxItems) {
            fail(QStringLiteral("liste trop longue : plus de %1 relevés").arg(kMaxItems));
            return std::nullopt;
        }
        QSet<QString> seen;
        for (qsizetype index = 0; index < array.size(); ++index) {
            const QString where = QStringLiteral("items[%1]").arg(index);
            auto item = report(array.at(index), where);
            if (!item) { return std::nullopt; }
            const QString identity = item->provider + QLatin1Char('/') + item->limitId
                + QLatin1Char('/') + item->workerId;
            if (seen.contains(identity)) {
                fail(QStringLiteral("relevé en double pour %1/%2 sur le worker « %3 » (%4)")
                         .arg(item->provider, item->limitId, item->workerName, where));
                return std::nullopt;
            }
            seen.insert(identity);
            result.items.append(*item);
        }
        return result;
    }

private:
    bool fail(const QString &message)
    {
        if (error.isEmpty()) { error = message; }
        return false;
    }

    //! Nom de champ cité dans un refus, borné : un serveur ne dicte pas la taille du message.
    static QString shown(const QString &key)
    {
        constexpr qsizetype limit = 64;
        return key.size() <= limit ? key : key.left(limit) + QStringLiteral("…");
    }

    bool keys(const QJsonObject &object, const QStringList &expected, const QString &where)
    {
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            if (!expected.contains(it.key())) {
                return fail(QStringLiteral("champ inattendu « %1 » dans %2").arg(shown(it.key()), where));
            }
        }
        for (const auto &key : expected) {
            if (!object.contains(key)) {
                return fail(QStringLiteral("champ absent « %1 » dans %2").arg(key, where));
            }
        }
        return true;
    }

    static bool integer(const QJsonValue &value, double lower, double upper)
    {
        if (!value.isDouble()) { return false; }
        const double number = value.toDouble();
        return std::isfinite(number) && std::floor(number) == number && number >= lower
            && number <= upper;
    }

    static bool percent(const QJsonValue &value)
    {
        if (!value.isDouble()) { return false; }
        const double number = value.toDouble();
        return std::isfinite(number) && number >= 0.0 && number <= 100.0;
    }

    //! Texte non vide borné par la longueur maximale du contrat serveur.
    static std::optional<QString> text(const QJsonValue &value, qsizetype maxLength)
    {
        if (!value.isString() || value.toString().trimmed().isEmpty() || value.toString().size() > maxLength) {
            return std::nullopt;
        }
        return value.toString();
    }

    /*! Horodatage ISO 8601 AVEC fuseau (« Z » ou ±hh:mm). Une heure sans fuseau serait
        lue comme locale : c'est précisément l'erreur que l'on refuse de commettre. */
    static std::optional<QDateTime> instant(const QJsonValue &value)
    {
        static const QRegularExpression pattern(QStringLiteral(
            "^(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,9}))?(Z|[+-]\\d{2}:\\d{2})$"));
        if (!value.isString()) { return std::nullopt; }
        const auto match = pattern.match(value.toString());
        if (!match.hasMatch()) { return std::nullopt; }
        // Fraction ramenée aux millisecondes par troncature : aucune précision inventée.
        const QString fraction = (match.captured(2) + QStringLiteral("000")).left(3);
        const QDateTime parsed = QDateTime::fromString(
            match.captured(1) + QLatin1Char('.') + fraction + match.captured(3), Qt::ISODateWithMs);
        if (!parsed.isValid()) { return std::nullopt; }
        return parsed.toUTC();
    }

    std::optional<QuotaReport> report(const QJsonValue &value, const QString &where)
    {
        if (!value.isObject()) {
            fail(QStringLiteral("%1 doit être un objet").arg(where));
            return std::nullopt;
        }
        const QJsonObject object = value.toObject();
        if (!keys(object, {QStringLiteral("provider"), QStringLiteral("status"), QStringLiteral("source"),
                           QStringLiteral("plan"), QStringLiteral("limit_id"), QStringLiteral("windows"),
                           QStringLiteral("credits"), QStringLiteral("limit_reached"),
                           QStringLiteral("reached_type"), QStringLiteral("observed_at"),
                           QStringLiteral("detail"), QStringLiteral("worker_id"),
                           QStringLiteral("worker_name"), QStringLiteral("received_at"),
                           QStringLiteral("stale")}, where)) {
            return std::nullopt;
        }
        QuotaReport result;
        result.provider = object.value(QStringLiteral("provider")).toString();
        if (!object.value(QStringLiteral("provider")).isString()
            || (result.provider != QLatin1String("codex") && result.provider != QLatin1String("claude_code"))) {
            fail(QStringLiteral("« provider » inconnu dans %1 : codex ou claude_code attendu").arg(where));
            return std::nullopt;
        }
        result.status = object.value(QStringLiteral("status")).toString();
        static const QStringList statuses{QStringLiteral("ok"), QStringLiteral("not_signed_in"),
            QStringLiteral("cli_missing"), QStringLiteral("cli_too_old"), QStringLiteral("unavailable")};
        if (!object.value(QStringLiteral("status")).isString() || !statuses.contains(result.status)) {
            fail(QStringLiteral("« status » inconnu dans %1").arg(where));
            return std::nullopt;
        }
        const QString expectedSource = result.provider == QLatin1String("codex")
            ? QStringLiteral("codex_app_server") : QStringLiteral("claude_code_statusline");
        if (object.value(QStringLiteral("source")) != QJsonValue(expectedSource)) {
            fail(QStringLiteral("« source » incohérente avec le fournisseur dans %1").arg(where));
            return std::nullopt;
        }
        // Longueurs maximales du contrat serveur (packages/contracts/.../subscriptions.py).
        if (!optionalText(object, QStringLiteral("plan"), 40, where, result.plan)
            || !optionalText(object, QStringLiteral("reached_type"), 64, where, result.reachedType)
            || !optionalText(object, QStringLiteral("detail"), 300, where, result.detail)
            || !requiredText(object, QStringLiteral("limit_id"), 64, where, result.limitId)
            || !requiredText(object, QStringLiteral("worker_id"), 36, where, result.workerId)
            || !requiredText(object, QStringLiteral("worker_name"), 200, where, result.workerName)) {
            return std::nullopt;
        }
        const auto observed = instant(object.value(QStringLiteral("observed_at")));
        if (!observed) {
            fail(QStringLiteral("« observed_at » doit être un horodatage ISO 8601 avec fuseau (%1)").arg(where));
            return std::nullopt;
        }
        result.observedAt = *observed;
        const auto received = instant(object.value(QStringLiteral("received_at")));
        if (!received) {
            fail(QStringLiteral("« received_at » doit être un horodatage ISO 8601 avec fuseau (%1)").arg(where));
            return std::nullopt;
        }
        result.receivedAt = *received;
        const QJsonValue stale = object.value(QStringLiteral("stale"));
        if (!stale.isBool()) {
            fail(QStringLiteral("« stale » doit être un booléen (%1)").arg(where));
            return std::nullopt;
        }
        result.stale = stale.toBool();
        const QJsonValue reached = object.value(QStringLiteral("limit_reached"));
        if (!reached.isNull() && !reached.isBool()) {
            fail(QStringLiteral("« limit_reached » doit être un booléen ou null (%1)").arg(where));
            return std::nullopt;
        }
        if (reached.isBool()) { result.limitReached = reached.toBool(); }
        if (result.reachedType && result.limitReached != std::optional<bool>(true)) {
            fail(QStringLiteral("« reached_type » exige « limit_reached » à true (%1)").arg(where));
            return std::nullopt;
        }
        if (!credits(object.value(QStringLiteral("credits")), where, result.credits)
            || !windows(object.value(QStringLiteral("windows")), where, result.windows)) {
            return std::nullopt;
        }
        if (result.status != QLatin1String("ok")) {
            if (!result.windows.isEmpty() || result.credits || result.limitReached || result.reachedType) {
                fail(QStringLiteral("un relevé à l'état %1 ne porte aucune mesure (%2)").arg(result.status, where));
                return std::nullopt;
            }
            if (!result.detail) {
                fail(QStringLiteral("un relevé à l'état %1 doit porter son explication « detail » (%2)")
                         .arg(result.status, where));
                return std::nullopt;
            }
        }
        return result;
    }

    bool optionalText(const QJsonObject &object, const QString &key, qsizetype maxLength,
                      const QString &where, std::optional<QString> &target)
    {
        const QJsonValue value = object.value(key);
        if (value.isNull()) { return true; }
        const auto content = text(value, maxLength);
        if (!content) {
            return fail(QStringLiteral("« %1 » doit être un texte non vide de %2 caractères au plus, ou null (%3)")
                            .arg(key).arg(maxLength).arg(where));
        }
        target = *content;
        return true;
    }

    bool requiredText(const QJsonObject &object, const QString &key, qsizetype maxLength,
                      const QString &where, QString &target)
    {
        const auto content = text(object.value(key), maxLength);
        if (!content) {
            return fail(QStringLiteral("« %1 » doit être un texte non vide de %2 caractères au plus (%3)")
                            .arg(key).arg(maxLength).arg(where));
        }
        target = *content;
        return true;
    }

    bool credits(const QJsonValue &value, const QString &where, std::optional<QuotaCredits> &target)
    {
        if (value.isNull()) { return true; }
        if (!value.isObject()) {
            return fail(QStringLiteral("« credits » doit être un objet ou null (%1)").arg(where));
        }
        const QJsonObject object = value.toObject();
        const QString place = where + QStringLiteral(".credits");
        if (!keys(object, {QStringLiteral("has_credits"), QStringLiteral("unlimited"),
                           QStringLiteral("balance")}, place)) {
            return false;
        }
        const QJsonValue has = object.value(QStringLiteral("has_credits"));
        const QJsonValue unlimited = object.value(QStringLiteral("unlimited"));
        if (!has.isBool() || !unlimited.isBool()) {
            return fail(QStringLiteral("« has_credits » et « unlimited » doivent être des booléens (%1)").arg(place));
        }
        QuotaCredits result;
        result.hasCredits = has.toBool();
        result.unlimited = unlimited.toBool();
        if (!optionalText(object, QStringLiteral("balance"), 32, place, result.balance)) { return false; }
        target = result;
        return true;
    }

    bool windows(const QJsonValue &value, const QString &where, QList<QuotaWindow> &target)
    {
        if (!value.isArray() || value.toArray().size() > kMaxWindows) {
            return fail(QStringLiteral("« windows » doit être une liste d'au plus %1 fenêtres (%2)")
                            .arg(kMaxWindows).arg(where));
        }
        const QJsonArray array = value.toArray();
        QSet<QString> seen;
        for (qsizetype index = 0; index < array.size(); ++index) {
            const QString place = QStringLiteral("%1.windows[%2]").arg(where).arg(index);
            if (!array.at(index).isObject()) {
                return fail(QStringLiteral("%1 doit être un objet").arg(place));
            }
            const QJsonObject object = array.at(index).toObject();
            if (!keys(object, {QStringLiteral("key"), QStringLiteral("used_percent"),
                               QStringLiteral("window_minutes"), QStringLiteral("resets_at"),
                               QStringLiteral("remaining_percent")}, place)) {
                return false;
            }
            QuotaWindow window;
            const auto key = text(object.value(QStringLiteral("key")), 32);
            if (!key) {
                return fail(QStringLiteral("« key » doit être un texte non vide de 32 caractères au plus (%1)").arg(place));
            }
            window.key = *key;
            if (seen.contains(window.key)) {
                return fail(QStringLiteral("fenêtre « %1 » en double (%2)").arg(window.key, place));
            }
            seen.insert(window.key);
            const QJsonValue used = object.value(QStringLiteral("used_percent"));
            if (!used.isNull() && !percent(used)) {
                return fail(QStringLiteral("« used_percent » doit être un nombre de 0 à 100 ou null (%1)").arg(place));
            }
            if (!used.isNull()) { window.used = used.toDouble(); }
            const QJsonValue minutes = object.value(QStringLiteral("window_minutes"));
            if (!minutes.isNull() && !integer(minutes, 1, kMaxWindowMinutes)) {
                return fail(QStringLiteral("« window_minutes » doit être un entier positif ou null (%1)").arg(place));
            }
            if (!minutes.isNull()) { window.minutes = static_cast<qint64>(minutes.toDouble()); }
            const QJsonValue resets = object.value(QStringLiteral("resets_at"));
            if (!resets.isNull()) {
                window.resetsAt = instant(resets);
                if (!window.resetsAt) {
                    return fail(QStringLiteral("« resets_at » doit être un horodatage ISO 8601 avec fuseau, ou null (%1)")
                                    .arg(place));
                }
            }
            const QJsonValue remaining = object.value(QStringLiteral("remaining_percent"));
            if (!remaining.isNull() && !percent(remaining)) {
                return fail(QStringLiteral("« remaining_percent » doit être un nombre de 0 à 100 ou null (%1)").arg(place));
            }
            if (!remaining.isNull()) { window.remaining = remaining.toDouble(); }
            const bool coherent = window.used
                ? window.remaining && std::abs(*window.remaining - (100.0 - *window.used)) <= kRemainingTolerance
                : !window.remaining;
            if (!coherent) {
                return fail(QStringLiteral("« remaining_percent » ne correspond pas à 100 − « used_percent » (%1)")
                                .arg(place));
            }
            target.append(window);
        }
        return true;
    }
};

// --- Présentation en français ------------------------------------------------------

QString duration(qint64 seconds)
{
    const qint64 minutes = seconds / 60;
    if (minutes < 60) { return QStringLiteral("%1 min").arg(minutes); }
    const qint64 hours = minutes / 60;
    if (hours < 48) {
        const qint64 rest = minutes % 60;
        return rest == 0 ? QStringLiteral("%1 h").arg(hours)
                         : QStringLiteral("%1 h %2").arg(hours).arg(rest, 2, 10, QLatin1Char('0'));
    }
    const qint64 days = hours / 24;
    const qint64 rest = hours % 24;
    return rest == 0 ? QStringLiteral("%1 j").arg(days) : QStringLiteral("%1 j %2 h").arg(days).arg(rest);
}

QString percentText(double value)
{
    static const QLocale french(QLocale::French, QLocale::France);
    return french.toString(value, 'f', QLocale::FloatingPointShortest) + QChar(0x00A0) + QLatin1Char('%');
}

QString localMoment(const QDateTime &instant, const QDateTime &now, const QTimeZone &zone, bool seconds = false)
{
    const QDateTime local = instant.toTimeZone(zone);
    const QDate today = now.toTimeZone(zone).date();
    const QString time = local.toString(seconds ? QStringLiteral("HH:mm:ss") : QStringLiteral("HH:mm"));
    if (local.date() == today) { return QStringLiteral("aujourd'hui à %1").arg(time); }
    if (local.date() == today.addDays(1)) { return QStringLiteral("demain à %1").arg(time); }
    if (local.date() == today.addDays(-1)) { return QStringLiteral("hier à %1").arg(time); }
    const QString day = local.toString(local.date().year() == today.year() ? QStringLiteral("dd/MM")
                                                                           : QStringLiteral("dd/MM/yyyy"));
    return QStringLiteral("le %1 à %2").arg(day, time);
}

QString freshness(const QDateTime &observed, const QDateTime &now)
{
    const qint64 age = observed.secsTo(now);
    if (age < -60) {
        // L'API tolère cinq minutes d'avance : le dire plutôt que d'écrire « à l'instant ».
        return QStringLiteral("relevé daté de %1 dans le futur (horloge du worker en avance)").arg(duration(-age));
    }
    return age < 60 ? QStringLiteral("relevé à l'instant") : QStringLiteral("relevé il y a %1").arg(duration(age));
}

QString providerLabel(const QString &provider)
{
    return provider == QLatin1String("codex") ? QStringLiteral("Codex (compte ChatGPT)") : QStringLiteral("Claude Code");
}

QString statusLabel(const QString &status)
{
    if (status == QLatin1String("ok")) { return QStringLiteral("Connecté"); }
    if (status == QLatin1String("not_signed_in")) { return QStringLiteral("Non connecté"); }
    if (status == QLatin1String("cli_missing")) { return QStringLiteral("CLI absente"); }
    if (status == QLatin1String("cli_too_old")) { return QStringLiteral("CLI trop ancienne"); }
    return QStringLiteral("Indisponible");
}

QString statusKey(const QString &status)
{
    if (status == QLatin1String("ok")) { return QStringLiteral("succeeded"); }
    if (status == QLatin1String("not_signed_in") || status == QLatin1String("cli_missing")) {
        return QStringLiteral("notConfigured");
    }
    if (status == QLatin1String("cli_too_old")) { return QStringLiteral("blocked"); }
    return QStringLiteral("failed");
}

QString windowLabel(const QuotaWindow &window)
{
    if (!window.minutes) { return QStringLiteral("Fenêtre « %1 » (durée inconnue)").arg(window.key); }
    if (*window.minutes == 300) { return QStringLiteral("Fenêtre 5 h"); }
    if (*window.minutes == 10080) { return QStringLiteral("Semaine"); }
    return QStringLiteral("Fenêtre de %1 min").arg(*window.minutes);
}

//! Compteur affiché : les identifiants propres à la plateforme sont traduits, ceux de la
//! source (par exemple « codex ») restent tels quels.
QString counterLabel(const QString &limitId)
{
    if (limitId == kProbeLimitId) { return QStringLiteral("aucun (lecture en échec)"); }
    if (limitId == kDefaultLimitId) { return QStringLiteral("unique"); }
    return limitId;
}

std::optional<QString> knownPlan(const std::optional<QString> &plan)
{
    if (!plan || *plan == kSourceUnknownPlan) { return std::nullopt; }
    return plan;
}

/*! Cause d'une limite atteinte (``RateLimitReachedType`` de Codex), en français. Un type
    d'une version future reste cité tel quel, signalé comme non reconnu. */
QString reachedCause(const QString &type)
{
    static const QHash<QString, QString> causes{
        {QStringLiteral("rate_limit_reached"), QStringLiteral("limite d'utilisation de l'abonnement")},
        {QStringLiteral("workspace_owner_credits_depleted"),
         QStringLiteral("crédits du propriétaire de l'espace de travail épuisés")},
        {QStringLiteral("workspace_member_credits_depleted"),
         QStringLiteral("crédits du membre de l'espace de travail épuisés")},
        {QStringLiteral("workspace_owner_usage_limit_reached"),
         QStringLiteral("plafond d'utilisation du propriétaire de l'espace de travail")},
        {QStringLiteral("workspace_member_usage_limit_reached"),
         QStringLiteral("plafond d'utilisation du membre de l'espace de travail")},
    };
    return causes.value(type, QStringLiteral("type non reconnu « %1 »").arg(type));
}

QString creditsLabel(const std::optional<QuotaCredits> &credits)
{
    if (!credits) { return kUnknown; }
    if (credits->unlimited) { return QStringLiteral("Illimités"); }
    if (!credits->hasCredits) { return QStringLiteral("Aucun crédit"); }
    return credits->balance ? QStringLiteral("Solde : %1").arg(*credits->balance)
                            : QStringLiteral("Crédits disponibles, solde inconnu");
}

QJsonObject windowRow(const QuotaWindow &window, const QDateTime &now, const QTimeZone &zone)
{
    QJsonObject row{{QStringLiteral("key"), window.key}, {QStringLiteral("label"), windowLabel(window)}};
    row.insert(QStringLiteral("usedKnown"), window.used.has_value());
    row.insert(QStringLiteral("usedPercent"), window.used ? QJsonValue(*window.used) : QJsonValue(QJsonValue::Null));
    row.insert(QStringLiteral("usedText"), window.used ? percentText(*window.used) : kUnknown);
    row.insert(QStringLiteral("remainingPercent"),
               window.remaining ? QJsonValue(*window.remaining) : QJsonValue(QJsonValue::Null));
    row.insert(QStringLiteral("remainingText"), window.remaining ? percentText(*window.remaining) : kUnknown);
    QString level = QStringLiteral("unknown");
    if (window.remaining) {
        level = *window.remaining <= 10.0 ? QStringLiteral("critical")
            : *window.remaining <= 25.0   ? QStringLiteral("warning")
                                          : QStringLiteral("normal");
    }
    row.insert(QStringLiteral("level"), level);
    row.insert(QStringLiteral("resetKnown"), window.resetsAt.has_value());
    QString countdown;
    bool passed = false;
    if (window.resetsAt) {
        const qint64 remaining = now.secsTo(*window.resetsAt);
        passed = *window.resetsAt <= now;
        countdown = passed          ? QStringLiteral("déjà passée")
            : remaining < 60        ? QStringLiteral("dans moins d'une minute")
                                    : QStringLiteral("dans %1").arg(duration(remaining));
    }
    row.insert(QStringLiteral("resetText"), window.resetsAt ? localMoment(*window.resetsAt, now, zone) : kUnknown);
    row.insert(QStringLiteral("countdownText"), countdown);
    row.insert(QStringLiteral("resetPassed"), passed);
    return row;
}

QString windowSummary(const QJsonObject &window)
{
    const QString remaining = window.value(QStringLiteral("remainingPercent")).isNull()
        ? QStringLiteral("reste Inconnu")
        : window.value(QStringLiteral("remainingText")).toString() + QStringLiteral(" restant");
    QString reset = window.value(QStringLiteral("resetText")).toString();
    const QString countdown = window.value(QStringLiteral("countdownText")).toString();
    if (!countdown.isEmpty()) { reset += QStringLiteral(" (%1)").arg(countdown); }
    return QStringLiteral("%1 : %2, remise à zéro %3").arg(window.value(QStringLiteral("label")).toString(),
                                                           remaining, reset);
}

int providerRank(const QString &provider) { return provider == QLatin1String("codex") ? 0 : 1; }

/*!
    Une ligne par relevé. Pour un même worker et un même fournisseur, le relevé le plus
    récent donne l'état courant ; un compteur plus ancien reste affiché avec sa date et
    la mention « Relevé antérieur », jamais comme l'état actuel.
*/
QJsonArray buildRows(const QuotaListing &listing, const QDateTime &now, const QTimeZone &zone)
{
    QHash<QString, QDateTime> latest;
    const auto group = [](const QuotaReport &report) { return report.workerId + QLatin1Char('\n') + report.provider; };
    for (const auto &report : listing.items) {
        const QString key = group(report);
        if (!latest.contains(key) || latest.value(key) < report.observedAt) { latest.insert(key, report.observedAt); }
    }
    QList<qsizetype> order(listing.items.size());
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](qsizetype left, qsizetype right) {
        const auto &a = listing.items.at(left);
        const auto &b = listing.items.at(right);
        const bool currentA = a.observedAt == latest.value(group(a));
        const bool currentB = b.observedAt == latest.value(group(b));
        return std::make_tuple(providerRank(a.provider), a.workerName, a.workerId, !currentA, a.limitId)
            < std::make_tuple(providerRank(b.provider), b.workerName, b.workerId, !currentB, b.limitId);
    });
    // État courant de chaque groupe : le premier relevé courant dans l'ordre d'affichage.
    QHash<QString, const QuotaReport *> currentOf;
    for (const auto index : order) {
        const auto &report = listing.items.at(index);
        if (report.observedAt == latest.value(group(report)) && !currentOf.contains(group(report))) {
            currentOf.insert(group(report), &report);
        }
    }
    QJsonArray rows;
    for (const auto index : order) {
        const auto &report = listing.items.at(index);
        const bool current = report.observedAt == latest.value(group(report));
        const std::optional<QString> plan = knownPlan(report.plan);
        const QString counter = counterLabel(report.limitId);
        QJsonObject row{
            {QStringLiteral("id"), report.provider + QLatin1Char('/') + report.limitId + QLatin1Char('/') + report.workerId},
            {QStringLiteral("provider"), report.provider},
            {QStringLiteral("providerLabel"), providerLabel(report.provider)},
            {QStringLiteral("workerName"), report.workerName},
            {QStringLiteral("limitId"), report.limitId},
            {QStringLiteral("counterLabel"), counter},
            {QStringLiteral("plan"), plan.value_or(kUnknown)},
            {QStringLiteral("planKnown"), plan.has_value()},
            {QStringLiteral("status"), report.status},
            {QStringLiteral("statusKey"), statusKey(report.status)},
            {QStringLiteral("statusLabel"), statusLabel(report.status)},
            {QStringLiteral("sourceLabel"), report.provider == QLatin1String("codex")
                 ? QStringLiteral("relevé officiel app-server") : QStringLiteral("ligne d'état Claude Code")},
            {QStringLiteral("detail"), report.detail.value_or(QString())},
            {QStringLiteral("observedText"), localMoment(report.observedAt, now, zone)},
            {QStringLiteral("receivedText"), localMoment(report.receivedAt, now, zone)},
            {QStringLiteral("freshness"), freshness(report.observedAt, now)},
            {QStringLiteral("stale"), report.stale},
            {QStringLiteral("staleLabel"), report.stale ? QStringLiteral("Périmé") : QString()},
            {QStringLiteral("current"), current},
            {QStringLiteral("limitReached"), report.limitReached.value_or(false)},
            {QStringLiteral("creditsLabel"), creditsLabel(report.credits)},
        };
        QString reached = kUnknown;
        QString alert;
        if (report.limitReached) {
            reached = *report.limitReached ? QStringLiteral("Atteinte") : QStringLiteral("Non atteinte");
        }
        if (report.limitReached.value_or(false)) {
            alert = report.reachedType
                ? QStringLiteral("Limite atteinte : %1").arg(reachedCause(*report.reachedType))
                : QStringLiteral("Limite atteinte");
        }
        row.insert(QStringLiteral("limitReachedLabel"), reached);
        row.insert(QStringLiteral("limitReachedAlert"), alert);
        QString superseded;
        if (!current) {
            const QuotaReport *head = currentOf.value(group(report));
            superseded = QStringLiteral("Relevé antérieur : le relevé le plus récent de ce worker pour ce fournisseur (%1) indique « %2 ».")
                             .arg(freshness(head->observedAt, now), statusLabel(head->status));
        }
        row.insert(QStringLiteral("supersededNote"), superseded);
        QJsonArray windows;
        QStringList summaries;
        for (const auto &window : report.windows) {
            const QJsonObject item = windowRow(window, now, zone);
            summaries.append(windowSummary(item));
            windows.append(item);
        }
        row.insert(QStringLiteral("windows"), windows);
        QString name = QStringLiteral("%1, worker « %2 », compteur %3 : %4.")
                           .arg(providerLabel(report.provider), report.workerName, counter,
                                statusLabel(report.status));
        if (!summaries.isEmpty()) { name += QLatin1Char(' ') + summaries.join(QStringLiteral(" ; ")) + QLatin1Char('.'); }
        name += QStringLiteral(" Offre : %1. Crédits : %2. %3.")
                    .arg(plan.value_or(kUnknown), creditsLabel(report.credits), freshness(report.observedAt, now));
        if (!alert.isEmpty()) { name += QLatin1Char(' ') + alert + QLatin1Char('.'); }
        if (report.stale) { name += QStringLiteral(" Périmé."); }
        if (!current) { name += QStringLiteral(" Relevé antérieur."); }
        row.insert(QStringLiteral("accessibleName"), name);
        rows.append(row);
    }
    return rows;
}

} // namespace

SubscriptionQuotasViewModel::SubscriptionQuotasViewModel(ApiClient *client, AuthManager *auth, QObject *parent)
    : QObject(parent), m_client(client), m_auth(auth), m_reports(new JsonListModel(this)),
      m_zone(QTimeZone::systemTimeZone())
{
    m_timer.setInterval(kRefreshMs);
    connect(&m_timer, &QTimer::timeout, this, &SubscriptionQuotasViewModel::refresh);
    connect(m_auth, &AuthManager::stateChanged, this, &SubscriptionQuotasViewModel::updateSession);
    connect(m_auth, &AuthManager::userChanged, this, &SubscriptionQuotasViewModel::updateSession);
    connect(m_client, &ApiClient::baseUrlChanged, this, &SubscriptionQuotasViewModel::updateSession);
    m_identity = identity();
}

SubscriptionQuotasViewModel::~SubscriptionQuotasViewModel()
{
    m_timer.stop();
    ++m_generation;
    if (m_call) {
        disconnect(m_call, nullptr, this, nullptr);
        m_call->abort();
    }
}

QObject *SubscriptionQuotasViewModel::reports() const { return m_reports; }

QString SubscriptionQuotasViewModel::identity() const
{
    if (m_auth->userId().isEmpty()) { return {}; }
    return m_client->baseUrl().toString() + QLatin1Char('\n') + m_auth->userId() + QLatin1Char('\n')
        + m_auth->platformRole();
}

bool SubscriptionQuotasViewModel::sessionReady() const
{
    return m_client->isConfigured() && m_auth->state() == SessionStatus::Connected && !m_auth->userId().isEmpty();
}

bool SubscriptionQuotasViewModel::isOwner() const { return m_auth->platformRole() == QLatin1String("owner"); }

QDateTime SubscriptionQuotasViewModel::now() const
{
    return m_clock ? m_clock().toUTC() : QDateTime::currentDateTimeUtc();
}

bool SubscriptionQuotasViewModel::canRefresh() const
{
    return m_active && sessionReady() && isOwner() && !loading();
}

QString SubscriptionQuotasViewModel::stateLabel() const
{
    static const QHash<QString, QString> labels{
        {QStringLiteral("signedOut"), QStringLiteral("Connexion requise")},
        {QStringLiteral("loading"), QStringLiteral("Chargement…")},
        {QStringLiteral("ready"), QStringLiteral("Relevés reçus")},
        {QStringLiteral("empty"), QStringLiteral("Aucun relevé")},
        {QStringLiteral("error"), QStringLiteral("Erreur")},
        {QStringLiteral("forbidden"), QStringLiteral("Réservé au propriétaire de la plateforme")},
        {QStringLiteral("offline"), QStringLiteral("Hors ligne")},
        {QStringLiteral("unsupported"), QStringLiteral("Non disponible sur ce serveur")},
    };
    return labels.value(m_state, kUnknown);
}

QString SubscriptionQuotasViewModel::stateStatusKey() const
{
    static const QHash<QString, QString> keys{
        {QStringLiteral("signedOut"), QStringLiteral("notConfigured")},
        {QStringLiteral("loading"), QStringLiteral("pending")},
        {QStringLiteral("ready"), QStringLiteral("succeeded")},
        {QStringLiteral("empty"), QStringLiteral("unknown")},
        {QStringLiteral("error"), QStringLiteral("failed")},
        {QStringLiteral("forbidden"), QStringLiteral("blocked")},
        {QStringLiteral("offline"), QStringLiteral("offline")},
        {QStringLiteral("unsupported"), QStringLiteral("notConfigured")},
    };
    return keys.value(m_state, QStringLiteral("unknown"));
}

void SubscriptionQuotasViewModel::setClockForTesting(std::function<QDateTime()> clock) { m_clock = std::move(clock); }
void SubscriptionQuotasViewModel::setTimeZoneForTesting(const QTimeZone &zone) { m_zone = zone; }
void SubscriptionQuotasViewModel::setRefreshIntervalForTesting(std::chrono::milliseconds interval)
{
    m_timer.setInterval(interval);
}

void SubscriptionQuotasViewModel::invalidate()
{
    ++m_generation;
    if (m_call) {
        disconnect(m_call, nullptr, this, nullptr);
        m_call->abort();
    }
    m_call = nullptr;
    m_reports->clear();
    m_servedLabel.clear();
    m_staleAfterLabel.clear();
}

void SubscriptionQuotasViewModel::setState(const QString &next, const QString &message)
{
    m_state = next;
    m_message = redactSecrets(message);
    updateTimer();
    emit changed();
}

void SubscriptionQuotasViewModel::updateTimer()
{
    const bool run = m_active && sessionReady() && isOwner() && m_state != QLatin1String("forbidden")
        && m_state != QLatin1String("unsupported");
    if (!run) {
        m_timer.stop();
    } else if (!m_timer.isActive()) {
        m_timer.start();
    }
}

void SubscriptionQuotasViewModel::setActive(bool value)
{
    if (m_active == value) { return; }
    m_active = value;
    invalidate();
    m_state = QStringLiteral("idle");
    m_message.clear();
    if (m_active) {
        updateSession();
    } else {
        updateTimer();
        emit changed();
    }
}

void SubscriptionQuotasViewModel::updateSession()
{
    const QString current = identity();
    if (current != m_identity) {
        // Autre utilisateur, autre rôle ou autre serveur : rien de l'ancien contexte ne
        // reste affiché, et aucune réponse en vol ne sera appliquée.
        invalidate();
        m_identity = current;
    }
    if (!m_active) {
        updateTimer();
        emit changed();
        return;
    }
    const auto session = m_auth->state();
    if (session == SessionStatus::Connecting && !m_identity.isEmpty()) {
        // Reprise de session de la même identité : l'affichage reste, rien n'est relancé.
        if (m_state == QLatin1String("idle")) {
            setState(QStringLiteral("loading"), QStringLiteral("Reprise de la session en cours…"));
            return;
        }
        updateTimer();
        emit changed();
        return;
    }
    if (session == SessionStatus::Offline) {
        invalidate();
        setState(QStringLiteral("offline"),
                 m_auth->lastError().isEmpty() ? QStringLiteral("Serveur injoignable : les quotas ne peuvent pas être relus.")
                                               : m_auth->lastError());
        return;
    }
    if (!sessionReady()) {
        invalidate();
        setState(QStringLiteral("signedOut"),
                 QStringLiteral("Connectez-vous avec le compte propriétaire de la plateforme pour consulter les quotas d'abonnement."));
        return;
    }
    if (!isOwner()) {
        invalidate();
        setState(QStringLiteral("forbidden"),
                 kOwnerOnly + QStringLiteral(" Rôle de votre session : %1.").arg(m_auth->platformRole().isEmpty()
                     ? kUnknown : m_auth->platformRole()));
        return;
    }
    static const QStringList reload{QStringLiteral("idle"), QStringLiteral("signedOut"),
                                    QStringLiteral("offline"), QStringLiteral("loading")};
    if (reload.contains(m_state) && !loading()) {
        refresh();
        return;
    }
    updateTimer();
    emit changed();
}

void SubscriptionQuotasViewModel::refresh()
{
    if (!m_active || loading()) { return; }
    if (!sessionReady() || !isOwner()) {
        updateSession();
        return;
    }
    // Seul un écran encore sans état affiche « Chargement… » : une relecture périodique
    // garde l'état et son explication (« Aucun relevé », « Hors ligne »…) jusqu'à la réponse.
    if (m_state == QLatin1String("idle") || m_state == QLatin1String("signedOut")) {
        m_state = QStringLiteral("loading");
        m_message = QStringLiteral("Lecture des derniers relevés auprès de l'API…");
    }
    const quint64 generation = m_generation;
    const QString expected = m_identity;
    ApiRequest request;
    request.path = QStringLiteral("/subscription-quotas");
    ApiCall *call = m_client->send(request);
    m_call = call;
    connect(call, &ApiCall::succeeded, this, [this, generation, expected](const ApiResponse &response) {
        if (generation != m_generation || expected != identity()) { return; }
        m_call = nullptr;
        applyDocument(response.json);
    });
    connect(call, &ApiCall::failed, this, [this, generation, expected](const ApiError &error) {
        if (generation != m_generation || expected != identity()) { return; }
        m_call = nullptr;
        applyFailure(error);
    });
    updateTimer();
    emit changed();
}

void SubscriptionQuotasViewModel::applyDocument(const QJsonDocument &document)
{
    Reader reader;
    const auto listing = reader.listing(document);
    if (!listing) {
        m_reports->clear();
        m_servedLabel.clear();
        m_staleAfterLabel.clear();
        setState(QStringLiteral("error"),
                 QStringLiteral("Réponse des quotas refusée : %1. Aucune valeur n'est affichée.").arg(reader.error));
        return;
    }
    const QDateTime instant = now();
    m_reports->setItems(buildRows(*listing, instant, m_zone));
    const QDateTime served = listing->generatedAt.toTimeZone(m_zone);
    m_servedLabel = served.date() == instant.toTimeZone(m_zone).date()
        ? QStringLiteral("Liste servie par l'API à %1").arg(served.toString(QStringLiteral("HH:mm:ss")))
        : QStringLiteral("Liste servie par l'API %1").arg(localMoment(listing->generatedAt, instant, m_zone, true));
    m_staleAfterLabel = QStringLiteral("Un relevé devient « Périmé » après %1.").arg(duration(listing->staleAfterSeconds));
    if (listing->items.isEmpty()) {
        setState(QStringLiteral("empty"),
                 QStringLiteral("Aucun relevé n'a encore été transmis. Sur le poste du titulaire, lancez le worker avec "
                                "ACP_WORKER_SUBSCRIPTION_QUOTAS=1 et attendez son premier passage (5 min par défaut)."));
        return;
    }
    setState(QStringLiteral("ready"));
}

void SubscriptionQuotasViewModel::applyFailure(const ApiError &error)
{
    m_reports->clear();
    m_servedLabel.clear();
    m_staleAfterLabel.clear();
    switch (error.kind()) {
    case ApiFailure::Network:
    case ApiFailure::Timeout:
        setState(QStringLiteral("offline"), error.message());
        return;
    case ApiFailure::Forbidden:
        setState(QStringLiteral("forbidden"), error.detail().isEmpty() ? kOwnerOnly : error.detail());
        return;
    case ApiFailure::NotFound:
        setState(QStringLiteral("unsupported"),
                 QStringLiteral("Ce serveur ne publie pas GET /subscription-quotas : mettez l'API à jour pour "
                                "consulter les quotas d'abonnement."));
        return;
    case ApiFailure::Unauthorized:
        setState(QStringLiteral("signedOut"), error.message());
        return;
    default:
        setState(QStringLiteral("error"), error.message());
        return;
    }
}

} // namespace acp
