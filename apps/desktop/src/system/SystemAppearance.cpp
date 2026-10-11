#include "system/SystemAppearance.h"

#include "storage/SettingsStore.h"

#include <QGuiApplication>
#include <QStyleHints>
#include <QVariantList>

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
        connect(m_settings, &SettingsStore::familyPreferenceChanged, this,
                &SystemAppearance::activeThemeChanged);
        connect(m_settings, &SettingsStore::motionPreferenceChanged, this,
                &SystemAppearance::activeMotionChanged);
        connect(m_settings, &SettingsStore::concentrationChanged, this,
                &SystemAppearance::activeMotionChanged);
        connect(m_settings, &SettingsStore::densityChanged, this, &SystemAppearance::readingChanged);
        connect(m_settings, &SettingsStore::textScaleChanged, this, &SystemAppearance::readingChanged);
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

QString SystemAppearance::familyPreference() const
{
    return m_settings ? m_settings->familyPreference() : families().constFirst();
}

void SystemAppearance::setFamilyPreference(const QString &family)
{
    if (m_settings) {
        m_settings->setFamilyPreference(family);
    }
}

QString SystemAppearance::activeFamily() const
{
    return familyPreference();
}

bool SystemAppearance::activeIsDark() const
{
    const QString preference = themePreference();
    if (preference == QLatin1String("dark") || preference == QLatin1String("light")) {
        return preference == QLatin1String("dark");
    }
    // « system » : thème sombre quand le système ne dit rien, comme les jetons le déclarent
    // ($defaultTheme : atelier-nuit).
    return detectSystemTheme() != QLatin1String("light");
}

QString SystemAppearance::themeFor(const QString &family, bool dark)
{
    // Même table que design/tokens/colors.json, $themeFamilies (vérifiée par tst_design_tokens.qml).
    if (family == QLatin1String("atelier")) {
        return dark ? QStringLiteral("atelier-nuit") : QStringLiteral("atelier-jour");
    }
    if (family == QLatin1String("studio")) {
        return dark ? QStringLiteral("studio-graphite") : QStringLiteral("studio-papier");
    }
    return QString();
}

QString SystemAppearance::activeTheme() const
{
    const QString theme = themeFor(activeFamily(), activeIsDark());
    return theme.isEmpty() ? themeFor(families().constFirst(), true) : theme;
}

QString SystemAppearance::motionPreference() const
{
    return m_settings ? m_settings->motionPreference() : motionProfiles().constFirst();
}

void SystemAppearance::setMotionPreference(const QString &preference)
{
    if (m_settings) {
        m_settings->setMotionPreference(preference);
    }
}

QString SystemAppearance::activeMotionProfile() const
{
    // Aucune préférence système lisible par Qt : la préférence de l'opérateur s'applique
    // telle quelle, et l'écran Apparence le dit.
    return motionPreference();
}

bool SystemAppearance::concentration() const
{
    return m_settings && m_settings->concentration();
}

void SystemAppearance::setConcentration(bool active)
{
    if (m_settings) {
        m_settings->setConcentration(active);
    }
}

QString SystemAppearance::density() const
{
    return m_settings ? m_settings->density() : QStringLiteral("standard");
}

void SystemAppearance::setDensity(const QString &density)
{
    if (m_settings) {
        m_settings->setDensity(density);
    }
}

int SystemAppearance::textScale() const
{
    return m_settings ? m_settings->textScale() : 100;
}

void SystemAppearance::setTextScale(int percent)
{
    if (m_settings) {
        m_settings->setTextScale(percent);
    }
}

QStringList SystemAppearance::families()
{
    return SettingsStore::families();
}

QStringList SystemAppearance::motionProfiles()
{
    return SettingsStore::motionProfiles();
}

QStringList SystemAppearance::densities()
{
    return SettingsStore::densities();
}

QVariantList SystemAppearance::textScales()
{
    QVariantList valeurs;
    for (const int valeur : SettingsStore::textScales()) {
        valeurs.append(valeur);
    }
    return valeurs;
}

} // namespace acp
