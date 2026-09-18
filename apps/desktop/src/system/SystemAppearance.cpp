#include "system/SystemAppearance.h"

#include "storage/SettingsStore.h"

#include <QGuiApplication>
#include <QStyleHints>

namespace acp {

SystemAppearance::SystemAppearance(SettingsStore *settings, QObject *parent)
    : QObject(parent)
    , m_settings(settings)
{
    if (QStyleHints *hints = QGuiApplication::styleHints()) {
        connect(hints, &QStyleHints::colorSchemeChanged, this,
                [this](Qt::ColorScheme) { emit activeThemeChanged(); });
    }
    if (m_settings) {
        connect(m_settings, &SettingsStore::themePreferenceChanged, this,
                &SystemAppearance::activeThemeChanged);
        connect(m_settings, &SettingsStore::motionPreferenceChanged, this,
                &SystemAppearance::activeMotionChanged);
    }
}

QString SystemAppearance::detectSystemTheme() const
{
    QStyleHints *hints = QGuiApplication::styleHints();
    if (!hints) {
        return QString();
    }
    switch (hints->colorScheme()) {
    case Qt::ColorScheme::Dark:
        return QStringLiteral("dark");
    case Qt::ColorScheme::Light:
        return QStringLiteral("light");
    case Qt::ColorScheme::Unknown:
        break;
    }
    return QString();
}

QString SystemAppearance::systemThemeLabel() const
{
    const QString detected = detectSystemTheme();
    if (detected == QLatin1String("dark")) {
        return QStringLiteral("Sombre");
    }
    if (detected == QLatin1String("light")) {
        return QStringLiteral("Clair");
    }
    return QStringLiteral("Inconnu");
}

QString SystemAppearance::themePreference() const
{
    return m_settings ? m_settings->themePreference() : QStringLiteral("system");
}

void SystemAppearance::setThemePreference(const QString &preference)
{
    if (m_settings) {
        m_settings->setThemePreference(preference);
    }
}

QString SystemAppearance::activeTheme() const
{
    const QString preference = themePreference();
    if (preference == QLatin1String("dark") || preference == QLatin1String("light")) {
        return preference;
    }
    const QString detected = detectSystemTheme();
    // Thème par défaut du produit quand le système ne dit rien : sombre, comme les jetons
    // le déclarent ($defaultTheme).
    return detected.isEmpty() ? QStringLiteral("dark") : detected;
}

QString SystemAppearance::motionPreference() const
{
    return m_settings ? m_settings->motionPreference() : QStringLiteral("system");
}

void SystemAppearance::setMotionPreference(const QString &preference)
{
    if (m_settings) {
        m_settings->setMotionPreference(preference);
    }
}

QString SystemAppearance::activeMotionProfile() const
{
    const QString preference = motionPreference();
    if (preference == QLatin1String("reduced")) {
        return QStringLiteral("reduced");
    }
    if (preference == QLatin1String("standard")) {
        return QStringLiteral("standard");
    }
    // « system » : faute de préférence système lisible par Qt, le profil standard
    // s'applique. L'écran de préférences dit explicitement que la détection n'existe pas,
    // pour que l'opérateur sache qu'il doit choisir lui-même.
    return QStringLiteral("standard");
}

} // namespace acp
