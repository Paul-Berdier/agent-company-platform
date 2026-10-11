// Apparence : famille visuelle, luminosité, profil de mouvement et préférences de lecture.
//
// Qt 6.5 a introduit QStyleHints::colorScheme() et le signal colorSchemeChanged(), qui
// exposent le thème du système sans code spécifique à une plateforme. C'est la source de
// vérité de la luminosité « suivre le système ».
// https://doc.qt.io/qt-6/qstylehints.html — consulté le 18 septembre 2026.
//
// Pour le mouvement réduit, Qt n'expose AUCUNE préférence système portable à la date de
// rédaction. Le service le dit : la préférence système est « inconnue », et seule la
// préférence applicative s'applique. Inventer une détection serait exactement le faux
// succès que la doctrine interdit.
//
// Chantier « atelier » (D165) : le thème appliqué se compose d'une FAMILLE (Pixel Atelier,
// Studio) et d'une LUMINOSITÉ (système, clair, sombre). Les identifiants des quatre thèmes
// sont ceux de design/tokens/colors.json ($themeFamilies) ; tst_design_tokens.qml vérifie
// que la table ci-dessous et les singletons générés disent la même chose.

#pragma once

#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantList>

namespace acp {

class SettingsStore;

class SystemAppearance : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString activeTheme READ activeTheme NOTIFY activeThemeChanged)
    Q_PROPERTY(QString activeFamily READ activeFamily NOTIFY activeThemeChanged)
    Q_PROPERTY(bool activeIsDark READ activeIsDark NOTIFY activeThemeChanged)
    Q_PROPERTY(QString themePreference READ themePreference WRITE setThemePreference NOTIFY
                   activeThemeChanged)
    Q_PROPERTY(QString familyPreference READ familyPreference WRITE setFamilyPreference NOTIFY
                   activeThemeChanged)
    Q_PROPERTY(QString activeMotionProfile READ activeMotionProfile NOTIFY activeMotionChanged)
    Q_PROPERTY(QString motionPreference READ motionPreference WRITE setMotionPreference NOTIFY
                   activeMotionChanged)
    Q_PROPERTY(bool concentration READ concentration WRITE setConcentration NOTIFY activeMotionChanged)
    Q_PROPERTY(QString density READ density WRITE setDensity NOTIFY readingChanged)
    Q_PROPERTY(int textScale READ textScale WRITE setTextScale NOTIFY readingChanged)
    Q_PROPERTY(bool systemMotionPreferenceKnown READ systemMotionPreferenceKnown CONSTANT)
    Q_PROPERTY(QString systemThemeLabel READ systemThemeLabel NOTIFY activeThemeChanged)
    Q_PROPERTY(QStringList families READ families CONSTANT)
    Q_PROPERTY(QStringList motionProfiles READ motionProfiles CONSTANT)
    Q_PROPERTY(QStringList densities READ densities CONSTANT)
    Q_PROPERTY(QVariantList textScales READ textScales CONSTANT)

public:
    explicit SystemAppearance(SettingsStore *settings, QObject *parent = nullptr);

    /*! Identifiant du thème appliqué : « atelier-nuit », « atelier-jour »,
        « studio-graphite » ou « studio-papier ». */
    [[nodiscard]] QString activeTheme() const;

    /*! Thème d'une famille et d'une luminosité ; chaîne vide si la famille est inconnue. */
    [[nodiscard]] static QString themeFor(const QString &family, bool dark);

    [[nodiscard]] QString activeFamily() const;
    [[nodiscard]] bool activeIsDark() const;

    /*! Luminosité : « system », « dark » ou « light ». */
    [[nodiscard]] QString themePreference() const;
    void setThemePreference(const QString &preference);

    /*! Famille visuelle : « atelier » ou « studio ». */
    [[nodiscard]] QString familyPreference() const;
    void setFamilyPreference(const QString &family);

    /*! « complet », « discret » ou « reduit » : le profil de mouvement à appliquer. */
    [[nodiscard]] QString activeMotionProfile() const;

    /*! Préférence enregistrée (même valeurs que le profil : aucune détection système). */
    [[nodiscard]] QString motionPreference() const;
    void setMotionPreference(const QString &preference);

    [[nodiscard]] bool concentration() const;
    void setConcentration(bool active);

    [[nodiscard]] QString density() const;
    void setDensity(const QString &density);

    [[nodiscard]] int textScale() const;
    void setTextScale(int percent);

    /*! Faux : Qt n'expose aucune préférence système de mouvement réduit de façon
        portable. La station le dit plutôt que de faire semblant de la lire. */
    [[nodiscard]] static bool systemMotionPreferenceKnown() { return false; }

    /*! Libellé français de la luminosité système détectée, ou « Inconnu ». */
    [[nodiscard]] QString systemThemeLabel() const;

    [[nodiscard]] static QStringList families();
    [[nodiscard]] static QStringList motionProfiles();
    [[nodiscard]] static QStringList densities();
    [[nodiscard]] static QVariantList textScales();

signals:
    void activeThemeChanged();
    void activeMotionChanged();
    void readingChanged();

private:
    [[nodiscard]] QString detectSystemTheme() const;

    SettingsStore *m_settings = nullptr;
};

} // namespace acp
