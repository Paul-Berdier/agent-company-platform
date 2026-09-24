#include "storage/SettingsStore.h"

#include <QLoggingCategory>
#include <QSettings>
#include <QVariant>

namespace acp {

namespace {

Q_LOGGING_CATEGORY(lcSettings, "acp.settings")

constexpr char kServerUrl[] = "connection/serverUrl";
constexpr char kAllowInsecureLoopback[] = "connection/allowInsecureLoopback";
constexpr char kRememberSession[] = "connection/rememberSession";
constexpr char kTheme[] = "appearance/theme";
constexpr char kMotion[] = "appearance/motion";
constexpr char kInspectorWidth[] = "layout/inspectorWidth";
constexpr char kSidebarWidth[] = "layout/sidebarWidth";
constexpr char kSidebarCollapsed[] = "layout/sidebarCollapsed";

} // namespace

const QStringList &SettingsStore::allowedKeys()
{
    static const QStringList keys = {
        QLatin1String(kServerUrl),      QLatin1String(kAllowInsecureLoopback),
        QLatin1String(kTheme),          QLatin1String(kMotion),
        QLatin1String(kInspectorWidth), QLatin1String(kSidebarCollapsed),
        QLatin1String(kRememberSession),
        QLatin1String(kSidebarWidth),
    };
    return keys;
}

SettingsStore::SettingsStore(QObject *parent)
    : QObject(parent)
    , m_settings(new QSettings(this))
{
}

SettingsStore::~SettingsStore()
{
    if (m_settings) {
        m_settings->sync();
    }
}

QVariant SettingsStore::value(const QString &key, const QVariant &fallback) const
{
    Q_ASSERT_X(allowedKeys().contains(key), "SettingsStore::value",
               "clé hors liste blanche : les préférences ne doivent jamais servir de coffre");
    if (!allowedKeys().contains(key)) {
        qCWarning(lcSettings) << "clé de préférence refusée (hors liste blanche)";
        return fallback;
    }
    return m_settings->value(key, fallback);
}

void SettingsStore::setValue(const QString &key, const QVariant &newValue)
{
    Q_ASSERT_X(allowedKeys().contains(key), "SettingsStore::setValue",
               "clé hors liste blanche : les préférences ne doivent jamais servir de coffre");
    if (!allowedKeys().contains(key)) {
        qCWarning(lcSettings) << "écriture de préférence refusée (hors liste blanche)";
        return;
    }
    m_settings->setValue(key, newValue);
}

QUrl SettingsStore::serverUrl() const
{
    const QString stored = value(QLatin1String(kServerUrl), QString()).toString();
    // Aucune valeur par défaut : l'audit constate qu'aucun domaine n'est décidé. Une URL
    // codée en dur serait une invention, et la station doit demander, pas supposer.
    return stored.isEmpty() ? QUrl() : QUrl(stored);
}

void SettingsStore::setServerUrl(const QUrl &url)
{
    setValue(QLatin1String(kServerUrl), url.isEmpty() ? QString() : url.toString());
    emit serverUrlChanged();
}

QString SettingsStore::themePreference() const
{
    return value(QLatin1String(kTheme), QStringLiteral("system")).toString();
}

void SettingsStore::setThemePreference(const QString &preference)
{
    if (preference != QLatin1String("system") && preference != QLatin1String("dark")
        && preference != QLatin1String("light")) {
        qCWarning(lcSettings) << "préférence de thème inconnue, ignorée";
        return;
    }
    setValue(QLatin1String(kTheme), preference);
    emit themePreferenceChanged();
}

QString SettingsStore::motionPreference() const
{
    return value(QLatin1String(kMotion), QStringLiteral("system")).toString();
}

void SettingsStore::setMotionPreference(const QString &preference)
{
    if (preference != QLatin1String("system") && preference != QLatin1String("standard")
        && preference != QLatin1String("reduced")) {
        qCWarning(lcSettings) << "préférence de mouvement inconnue, ignorée";
        return;
    }
    setValue(QLatin1String(kMotion), preference);
    emit motionPreferenceChanged();
}

bool SettingsStore::allowInsecureLoopback() const
{
    return value(QLatin1String(kAllowInsecureLoopback), false).toBool();
}

void SettingsStore::setAllowInsecureLoopback(bool allowed)
{
    setValue(QLatin1String(kAllowInsecureLoopback), allowed);
}

bool SettingsStore::rememberSession() const
{
    return value(QLatin1String(kRememberSession), false).toBool();
}

void SettingsStore::setRememberSession(bool remember)
{
    if (rememberSession() == remember) return;
    setValue(QLatin1String(kRememberSession), remember);
    emit rememberSessionChanged();
}

int SettingsStore::inspectorWidth() const
{
    const int width = value(QLatin1String(kInspectorWidth), 0).toInt();
    return width == 0 ? 0 : qBound(320, width, 600);
}

void SettingsStore::setInspectorWidth(int width)
{
    setValue(QLatin1String(kInspectorWidth), width == 0 ? 0 : qBound(320, width, 600));
}

int SettingsStore::sidebarWidth() const
{
    const int width = value(QLatin1String(kSidebarWidth), 0).toInt();
    return width == 0 ? 0 : qBound(200, width, 360);
}

void SettingsStore::setSidebarWidth(int width)
{
    setValue(QLatin1String(kSidebarWidth), width == 0 ? 0 : qBound(200, width, 360));
}

bool SettingsStore::sidebarCollapsed() const
{
    return value(QLatin1String(kSidebarCollapsed), false).toBool();
}

void SettingsStore::setSidebarCollapsed(bool collapsed)
{
    setValue(QLatin1String(kSidebarCollapsed), collapsed);
}

void SettingsStore::flush()
{
    m_settings->sync();
}

void SettingsStore::clear()
{
    m_settings->clear();
    m_settings->sync();
    emit serverUrlChanged();
    emit themePreferenceChanged();
    emit motionPreferenceChanged();
    emit rememberSessionChanged();
}

QString SettingsStore::location() const
{
    return m_settings->fileName();
}

} // namespace acp
