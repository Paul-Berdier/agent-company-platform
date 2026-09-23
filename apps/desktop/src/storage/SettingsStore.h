// Préférences NON SECRÈTES de la station.
//
// QSettings est employé ici, et uniquement ici. Ce qu'il a le droit de contenir est
// énuméré par une liste blanche appliquée à l'exécution : adresse du serveur, thème,
// disposition des volets, dernier projet ouvert. Toute autre clé est refusée par
// assertion en débogage et ignorée en production, plutôt que d'ouvrir une porte par
// laquelle un secret finirait un jour par passer.
//
// L'adresse du serveur n'est pas un secret : elle est publique par nature, et l'audit
// signale qu'aucun domaine n'est décidé — il n'y a donc aucune valeur par défaut.

#pragma once

#include <QObject>
#include <QString>
#include <QStringList>
#include <QUrl>

class QSettings;

namespace acp {

class SettingsStore : public QObject
{
    Q_OBJECT

public:
    explicit SettingsStore(QObject *parent = nullptr);
    ~SettingsStore() override;

    //! Clés autorisées. Toute autre clé est refusée.
    static const QStringList &allowedKeys();

    /*! Adresse du serveur mémorisée. URL vide si aucune n'a jamais été saisie : la
        station affiche alors son écran de première ouverture, elle n'invente rien. */
    [[nodiscard]] QUrl serverUrl() const;
    void setServerUrl(const QUrl &url);

    /*! « system », « dark » ou « light ». « system » par défaut. */
    [[nodiscard]] QString themePreference() const;
    void setThemePreference(const QString &preference);

    /*! « system », « standard » ou « reduced » pour le profil de mouvement. */
    [[nodiscard]] QString motionPreference() const;
    void setMotionPreference(const QString &preference);

    /*! Vrai si l'opérateur a explicitement accepté le bouclage local en clair. */
    [[nodiscard]] bool allowInsecureLoopback() const;
    void setAllowInsecureLoopback(bool allowed);

    /*! Consentement de mémorisation dans le coffre système ; faux par défaut.
        Cette préférence ne contient ni cookie, ni mot de passe, ni jeton. */
    [[nodiscard]] bool rememberSession() const;
    void setRememberSession(bool remember);

    /*! Largeur du panneau d'inspection, en pixels logiques. Zéro = valeur par défaut. */
    [[nodiscard]] int inspectorWidth() const;
    void setInspectorWidth(int width);
    [[nodiscard]] int sidebarWidth() const;
    void setSidebarWidth(int width);

    /*! Barre latérale repliée. */
    [[nodiscard]] bool sidebarCollapsed() const;
    void setSidebarCollapsed(bool collapsed);

    /*! Écrit les changements en attente. Appelé à la fermeture. */
    void flush();

    /*! Efface toutes les préférences. N'efface aucun secret : les secrets ne sont pas
        ici, et ne l'ont jamais été. */
    void clear();

    /*! Emplacement du fichier ou de la clé de registre, pour l'écran de diagnostics. */
    [[nodiscard]] QString location() const;

signals:
    void serverUrlChanged();
    void themePreferenceChanged();
    void motionPreferenceChanged();
    void rememberSessionChanged();

private:
    [[nodiscard]] QVariant value(const QString &key, const QVariant &fallback) const;
    void setValue(const QString &key, const QVariant &value);

    QSettings *m_settings = nullptr;
};

} // namespace acp
