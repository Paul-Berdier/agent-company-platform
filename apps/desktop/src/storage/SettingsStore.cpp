#include "storage/SettingsStore.h"

#include "diagnostics/Redaction.h"

#include <QLoggingCategory>
#include <QSettings>
#include <QVariant>

namespace acp {

namespace {

Q_LOGGING_CATEGORY(lcSettings, "acp.settings")

constexpr char kServerUrl[] = "connection/serverUrl";
constexpr char kAllowInsecureLoopback[] = "connection/allowInsecureLoopback";
constexpr char kConnexionMemorisee[] = "connexion/memorisee";
constexpr char kTheme[] = "appearance/theme";
constexpr char kFamily[] = "appearance/family";
constexpr char kMotion[] = "appearance/motion";
constexpr char kConcentration[] = "appearance/concentration";
constexpr char kDensity[] = "appearance/density";
constexpr char kTextScale[] = "appearance/textScale";
constexpr char kInspectorWidth[] = "layout/inspectorWidth";
constexpr char kSidebarWidth[] = "layout/sidebarWidth";
constexpr char kSidebarCollapsed[] = "layout/sidebarCollapsed";
constexpr char kAgentsVisible[] = "layout/agentsPanelVisible";
constexpr char kDrawerVisible[] = "layout/bottomDrawerVisible";
constexpr char kDrawerHeight[] = "layout/bottomDrawerHeight";
constexpr char kDrawerTab[] = "layout/bottomDrawerTab";

// Bornes des panneaux (design/tokens/spacing.json : layout.*.min et .max).
constexpr int kSidebarMin = 220;
constexpr int kSidebarMax = 420;
constexpr int kAgentsMin = 260;
constexpr int kAgentsMax = 600;
constexpr int kDrawerMin = 120;
constexpr int kDrawerMax = 520;

} // namespace

const QStringList &SettingsStore::allowedKeys()
{
    static const QStringList keys = {
        QLatin1String(kServerUrl),      QLatin1String(kAllowInsecureLoopback),
        QLatin1String(kTheme),          QLatin1String(kMotion),
        QLatin1String(kInspectorWidth), QLatin1String(kSidebarCollapsed),
        QLatin1String(kConnexionMemorisee),
        QLatin1String(kSidebarWidth),
        QLatin1String(kFamily),         QLatin1String(kConcentration),
        QLatin1String(kDensity),        QLatin1String(kTextScale),
        QLatin1String(kAgentsVisible),  QLatin1String(kDrawerVisible),
        QLatin1String(kDrawerHeight),   QLatin1String(kDrawerTab),
    };
    return keys;
}

const QStringList &SettingsStore::families()
{
    static const QStringList valeurs = {QStringLiteral("atelier"), QStringLiteral("studio")};
    return valeurs;
}

const QStringList &SettingsStore::motionProfiles()
{
    static const QStringList valeurs = {QStringLiteral("complet"), QStringLiteral("discret"), QStringLiteral("reduit")};
    return valeurs;
}

const QStringList &SettingsStore::densities()
{
    static const QStringList valeurs = {QStringLiteral("compacte"), QStringLiteral("standard"), QStringLiteral("aeree")};
    return valeurs;
}

const QList<int> &SettingsStore::textScales()
{
    static const QList<int> valeurs = {100, 112, 125, 140};
    return valeurs;
}

const QStringList &SettingsStore::bottomDrawerTabs()
{
    static const QStringList valeurs = {QStringLiteral("activite"), QStringLiteral("changements"), QStringLiteral("tests"),
                                        QStringLiteral("sorties"), QStringLiteral("services")};
    return valeurs;
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

QString SettingsStore::familyPreference() const
{
    const QString famille = value(QLatin1String(kFamily), families().constFirst()).toString();
    return families().contains(famille) ? famille : families().constFirst();
}

void SettingsStore::setFamilyPreference(const QString &family)
{
    if (!families().contains(family)) {
        qCWarning(lcSettings) << "famille visuelle inconnue, ignorée";
        return;
    }
    if (familyPreference() == family) return;
    setValue(QLatin1String(kFamily), family);
    emit familyPreferenceChanged();
}

QString SettingsStore::motionPreference() const
{
    const QString lu = value(QLatin1String(kMotion), motionProfiles().constFirst()).toString();
    if (motionProfiles().contains(lu)) {
        return lu;
    }
    // Valeurs des versions 1.0.x (design/tokens/motion.json, $legacyProfiles).
    if (lu == QLatin1String("standard")) {
        return QStringLiteral("discret");
    }
    if (lu == QLatin1String("reduced")) {
        return QStringLiteral("reduit");
    }
    return motionProfiles().constFirst();
}

void SettingsStore::setMotionPreference(const QString &preference)
{
    if (!motionProfiles().contains(preference)) {
        qCWarning(lcSettings) << "préférence de mouvement inconnue, ignorée";
        return;
    }
    setValue(QLatin1String(kMotion), preference);
    emit motionPreferenceChanged();
}

bool SettingsStore::concentration() const
{
    return value(QLatin1String(kConcentration), false).toBool();
}

void SettingsStore::setConcentration(bool active)
{
    if (concentration() == active) return;
    setValue(QLatin1String(kConcentration), active);
    emit concentrationChanged();
}

QString SettingsStore::density() const
{
    const QString lu = value(QLatin1String(kDensity), QStringLiteral("standard")).toString();
    return densities().contains(lu) ? lu : QStringLiteral("standard");
}

void SettingsStore::setDensity(const QString &density)
{
    if (!densities().contains(density)) {
        qCWarning(lcSettings) << "densité inconnue, ignorée";
        return;
    }
    if (this->density() == density) return;
    setValue(QLatin1String(kDensity), density);
    emit densityChanged();
}

int SettingsStore::textScale() const
{
    const int lu = value(QLatin1String(kTextScale), 100).toInt();
    return textScales().contains(lu) ? lu : 100;
}

void SettingsStore::setTextScale(int percent)
{
    if (!textScales().contains(percent)) {
        qCWarning(lcSettings) << "taille de texte inconnue, ignorée";
        return;
    }
    if (textScale() == percent) return;
    setValue(QLatin1String(kTextScale), percent);
    emit textScaleChanged();
}

bool SettingsStore::allowInsecureLoopback() const
{
    return value(QLatin1String(kAllowInsecureLoopback), false).toBool();
}

void SettingsStore::setAllowInsecureLoopback(bool allowed)
{
    setValue(QLatin1String(kAllowInsecureLoopback), allowed);
}

bool SettingsStore::connexionMemorisee() const
{
    return value(QLatin1String(kConnexionMemorisee), false).toBool();
}

void SettingsStore::setConnexionMemorisee(bool memoriser)
{
    if (connexionMemorisee() == memoriser) return;
    setValue(QLatin1String(kConnexionMemorisee), memoriser);
    emit connexionMemoriseeChanged();
}

int SettingsStore::inspectorWidth() const
{
    const int width = value(QLatin1String(kInspectorWidth), 0).toInt();
    return width == 0 ? 0 : qBound(kAgentsMin, width, kAgentsMax);
}

void SettingsStore::setInspectorWidth(int width)
{
    setValue(QLatin1String(kInspectorWidth), width == 0 ? 0 : qBound(kAgentsMin, width, kAgentsMax));
}

int SettingsStore::sidebarWidth() const
{
    const int width = value(QLatin1String(kSidebarWidth), 0).toInt();
    return width == 0 ? 0 : qBound(kSidebarMin, width, kSidebarMax);
}

void SettingsStore::setSidebarWidth(int width)
{
    setValue(QLatin1String(kSidebarWidth), width == 0 ? 0 : qBound(kSidebarMin, width, kSidebarMax));
}

bool SettingsStore::sidebarCollapsed() const
{
    return value(QLatin1String(kSidebarCollapsed), false).toBool();
}

void SettingsStore::setSidebarCollapsed(bool collapsed)
{
    setValue(QLatin1String(kSidebarCollapsed), collapsed);
}

bool SettingsStore::agentsPanelVisible() const
{
    return value(QLatin1String(kAgentsVisible), true).toBool();
}

void SettingsStore::setAgentsPanelVisible(bool visible)
{
    setValue(QLatin1String(kAgentsVisible), visible);
}

bool SettingsStore::bottomDrawerVisible() const
{
    return value(QLatin1String(kDrawerVisible), false).toBool();
}

void SettingsStore::setBottomDrawerVisible(bool visible)
{
    setValue(QLatin1String(kDrawerVisible), visible);
}

int SettingsStore::bottomDrawerHeight() const
{
    const int height = value(QLatin1String(kDrawerHeight), 0).toInt();
    return height == 0 ? 0 : qBound(kDrawerMin, height, kDrawerMax);
}

void SettingsStore::setBottomDrawerHeight(int height)
{
    setValue(QLatin1String(kDrawerHeight), height == 0 ? 0 : qBound(kDrawerMin, height, kDrawerMax));
}

QString SettingsStore::bottomDrawerTab() const
{
    const QString lu = value(QLatin1String(kDrawerTab), bottomDrawerTabs().constFirst()).toString();
    return bottomDrawerTabs().contains(lu) ? lu : bottomDrawerTabs().constFirst();
}

void SettingsStore::setBottomDrawerTab(const QString &tab)
{
    if (!bottomDrawerTabs().contains(tab)) {
        qCWarning(lcSettings) << "onglet du volet bas inconnu, ignoré";
        return;
    }
    setValue(QLatin1String(kDrawerTab), tab);
}

void SettingsStore::resetLayout()
{
    for (const char *cle : {kInspectorWidth, kSidebarWidth, kSidebarCollapsed, kAgentsVisible, kDrawerVisible,
                            kDrawerHeight, kDrawerTab}) {
        m_settings->remove(QLatin1String(cle));
    }
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
    emit familyPreferenceChanged();
    emit motionPreferenceChanged();
    emit concentrationChanged();
    emit densityChanged();
    emit textScaleChanged();
    emit connexionMemoriseeChanged();
}

SettingsStore::Controle SettingsStore::controler() const
{
    Controle controle;
    // Relit le stockage : une clé écrite par un autre programme doit aussi être vue.
    m_settings->sync();
    const QStringList cles = m_settings->allKeys();
    controle.cles = static_cast<int>(cles.size());
    for (const QString &cle : cles) {
        if (!allowedKeys().contains(cle)) {
            controle.horsListe.append(cle);
        }
        const QVariant valeur = m_settings->value(cle);
        const QString texte = valeur.typeId() == QMetaType::QStringList
            ? valeur.toStringList().join(QLatin1Char(' '))
            : valeur.toString();
        if (ressembleAUnSecret(texte) || ressembleAUnSecret(cle)) {
            controle.suspectes.append(cle);
        }
    }
    return controle;
}

QString SettingsStore::location() const
{
    return m_settings->fileName();
}

} // namespace acp
