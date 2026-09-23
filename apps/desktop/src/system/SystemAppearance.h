// Apparence système : thème clair/sombre et préférence de mouvement réduit.
//
// Qt 6.5 a introduit QStyleHints::colorScheme() et le signal colorSchemeChanged(), qui
// exposent le thème du système sans code spécifique à une plateforme. C'est la source de
// vérité du thème « suivre le système ».
// https://doc.qt.io/qt-6/qstylehints.html — consulté le 18 septembre 2026.
//
// Pour le mouvement réduit, Qt n'expose AUCUNE préférence système portable à la date de
// rédaction. Le service le dit : la préférence système est « inconnue », et seule la
// préférence applicative s'applique. Inventer une détection serait exactement le faux
// succès que la doctrine interdit.

#pragma once

#include <QObject>
#include <QString>

namespace acp {

class SettingsStore;

class SystemAppearance : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString activeTheme READ activeTheme NOTIFY activeThemeChanged)
    Q_PROPERTY(QString themePreference READ themePreference WRITE setThemePreference NOTIFY
                   activeThemeChanged)
    Q_PROPERTY(QString activeMotionProfile READ activeMotionProfile NOTIFY activeMotionChanged)
    Q_PROPERTY(QString motionPreference READ motionPreference WRITE setMotionPreference NOTIFY
                   activeMotionChanged)
    Q_PROPERTY(bool systemMotionPreferenceKnown READ systemMotionPreferenceKnown CONSTANT)
    Q_PROPERTY(QString systemThemeLabel READ systemThemeLabel NOTIFY activeThemeChanged)

public:
    explicit SystemAppearance(SettingsStore *settings, QObject *parent = nullptr);

    /*! « dark » ou « light » : ce que l'interface doit réellement appliquer. */
    [[nodiscard]] QString activeTheme() const;

    /*! « system », « dark » ou « light ». */
    [[nodiscard]] QString themePreference() const;
    void setThemePreference(const QString &preference);

    /*! « standard » ou « reduced » : le profil de mouvement à appliquer. */
    [[nodiscard]] QString activeMotionProfile() const;

    /*! « system », « standard » ou « reduced ». */
    [[nodiscard]] QString motionPreference() const;
    void setMotionPreference(const QString &preference);

    /*! Faux : Qt n'expose aucune préférence système de mouvement réduit de façon
        portable. La station le dit plutôt que de faire semblant de la lire. */
    [[nodiscard]] static bool systemMotionPreferenceKnown() { return false; }

    /*! Libellé français du thème système détecté, ou « Inconnu ». */
    [[nodiscard]] QString systemThemeLabel() const;

signals:
    void activeThemeChanged();
    void activeMotionChanged();

private:
    [[nodiscard]] QString detectSystemTheme() const;

    SettingsStore *m_settings = nullptr;
};

} // namespace acp
