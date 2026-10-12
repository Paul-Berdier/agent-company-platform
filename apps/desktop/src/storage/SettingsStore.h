// Préférences NON SECRÈTES de la station.
//
// QSettings est employé ici, et uniquement ici. Ce qu'il a le droit de contenir est
// énuméré par une liste blanche appliquée à l'exécution : adresse du serveur, thème,
// disposition des volets, dernier projet ouvert. Toute autre clé est refusée par
// assertion en débogage et ignorée en production, plutôt que d'ouvrir une porte par
// laquelle un secret finirait un jour par passer. Chantier « atelier » (D165, D167) : les
// préférences d'apparence (famille, luminosité, mouvement, Concentration, densité, taille du
// texte) et la disposition des panneaux s'y ajoutent ; aucun brouillon ni aucune donnée
// métier n'y entre (oubli local).
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

    /*! Résultat du contrôle des préférences réellement présentes (jamais leurs valeurs). */
    struct Controle
    {
        int cles = 0;
        QStringList horsListe; //!< Clés présentes hors de la liste blanche.
        QStringList suspectes; //!< Clés dont la valeur ressemble à un jeton.
        [[nodiscard]] bool conforme() const { return horsListe.isEmpty() && suspectes.isEmpty(); }
    };

    /*!
        Énumère TOUTES les clés présentes (pas seulement celles que la station écrit) : une clé
        hors liste blanche, ou une valeur qui ressemble à un jeton (acp::ressembleAUnSecret),
        est signalée par son nom. La valeur n'est jamais rendue.
    */
    [[nodiscard]] Controle controler() const;

    /*! Adresse du serveur mémorisée. URL vide si aucune n'a jamais été saisie : la
        station affiche alors son écran de première ouverture, elle n'invente rien. */
    [[nodiscard]] QUrl serverUrl() const;
    void setServerUrl(const QUrl &url);

    /*! Luminosité : « system », « dark » ou « light ». « system » par défaut. */
    [[nodiscard]] QString themePreference() const;
    void setThemePreference(const QString &preference);

    /*! Famille visuelle (D165) : « atelier » (par défaut) ou « studio ». */
    [[nodiscard]] QString familyPreference() const;
    void setFamilyPreference(const QString &family);

    /*!
        Profil de mouvement : « complet » (par défaut), « discret » ou « reduit ». Les valeurs
        des versions 1.0.x sont relues sans perte : « standard » (mouvement fonctionnel sans
        décor) devient « discret », « reduced » devient « reduit », « system » (l'ancienne
        valeur par défaut, jamais choisie) prend la valeur par défaut.
    */
    [[nodiscard]] QString motionPreference() const;
    void setMotionPreference(const QString &preference);

    /*! Mode Concentration : coupe l'ambiance quel que soit le profil. Faux par défaut. */
    [[nodiscard]] bool concentration() const;
    void setConcentration(bool active);

    /*! Densité : « compacte », « standard » (par défaut) ou « aeree ». */
    [[nodiscard]] QString density() const;
    void setDensity(const QString &density);

    /*! Taille du texte en pour cent : 100 (par défaut), 112, 125 ou 140. */
    [[nodiscard]] int textScale() const;
    void setTextScale(int percent);

    //! Valeurs admises, dans l'ordre d'affichage.
    static const QStringList &families();
    static const QStringList &motionProfiles();
    static const QStringList &densities();
    static const QList<int> &textScales();

    /*! Vrai si l'opérateur a explicitement accepté le bouclage local en clair. */
    //! Mise à jour automatique de la station (D170), active par défaut.
    [[nodiscard]] bool autoInstallUpdates() const;
    void setAutoInstallUpdates(bool enabled);
    [[nodiscard]] bool allowInsecureLoopback() const;
    void setAllowInsecureLoopback(bool allowed);

    /*! Consentement « Mémoriser la connexion sur ce poste » (coffre Windows) ; faux par
        défaut. Cette préférence ne contient AUCUN jeton : seulement le consentement. */
    [[nodiscard]] bool connexionMemorisee() const;
    void setConnexionMemorisee(bool memoriser);

    /*! Largeur du panneau d'inspection, en pixels logiques. Zéro = valeur par défaut. */
    [[nodiscard]] int inspectorWidth() const;
    void setInspectorWidth(int width);
    [[nodiscard]] int sidebarWidth() const;
    void setSidebarWidth(int width);

    /*! Barre latérale repliée. */
    [[nodiscard]] bool sidebarCollapsed() const;
    void setSidebarCollapsed(bool collapsed);

    /*! Panneau des agents (à droite) affiché ; vrai par défaut. */
    [[nodiscard]] bool agentsPanelVisible() const;
    void setAgentsPanelVisible(bool visible);

    /*! Volet bas (Activité, Changements, Tests, Sorties, Services) : affiché, hauteur, onglet. */
    [[nodiscard]] bool bottomDrawerVisible() const;
    void setBottomDrawerVisible(bool visible);
    [[nodiscard]] int bottomDrawerHeight() const;
    void setBottomDrawerHeight(int height);
    [[nodiscard]] QString bottomDrawerTab() const;
    void setBottomDrawerTab(const QString &tab);
    static const QStringList &bottomDrawerTabs();

    /*! Efface la disposition mémorisée (largeurs, visibilités, onglet) : retour au défaut. */
    void resetLayout();

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
    void familyPreferenceChanged();
    void motionPreferenceChanged();
    void concentrationChanged();
    void densityChanged();
    void textScaleChanged();
    void connexionMemoriseeChanged();

private:
    [[nodiscard]] QVariant value(const QString &key, const QVariant &fallback) const;
    void setValue(const QString &key, const QVariant &value);

    QSettings *m_settings = nullptr;
};

} // namespace acp
