// Session de la station auprès de Hermes : jetons, rafraîchissement, coffre, déconnexion.
//
// Remplace l'ancienne session à cookie. Ce qu'elle garantit :
//
//  - le jeton d'accès ne vit qu'en mémoire ; il est fourni au transport au moment de chaque
//    requête et n'est publié ni en propriété QML, ni dans un journal ;
//  - le jeton de rafraîchissement va au coffre Windows, et SEULEMENT si le propriétaire l'a
//    demandé (« Mémoriser la connexion sur ce poste ») ;
//  - UN SEUL rafraîchissement en vol : les demandes suivantes attendent le même résultat ;
//    Authelia fait tourner le jeton à chaque usage et révoque la session entière s'il voit
//    un ancien jeton rejoué (identite.md § 12.1) ;
//  - le nouveau jeton de rafraîchissement est écrit au coffre AVANT tout usage du nouveau
//    jeton d'accès ; si l'écriture échoue, l'ancienne entrée (désormais périmée) est effacée
//    et l'écran le dit ;
//  - 401 `session_expired` au rafraîchissement : entrée effacée, « Session expirée » ;
//  - 503 : AMBIGU (fournisseur injoignable OU jeton réutilisé) ; le jeton est GARDÉ, nouvel
//    essai avec recul ; après 3 échecs sur au moins 2 minutes, l'écran propose de se
//    reconnecter. Jamais d'effacement automatique sur un 503 ;
//  - déconnexion : `POST /auth/logout` avec le cookie `hermes_session_rt` (seule voie de
//    révocation chez le fournisseur), puis oubli local quoi qu'il arrive.

#pragma once

#include "app/QmlEnums.h"
#include "auth/JetonsHermes.h"
#include "events/Backoff.h"
#include "storage/JetonsCoffre.h"

#include <QDateTime>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QUrl>

#include <functional>

class QTimer;

namespace acp {

class ApiCall;
class ApiClient;
class ApiError;
class CredentialVault;
class NativeAuthFlow;
class SettingsStore;

class SessionHermes : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int etat READ etatValeur NOTIFY etatChange)
    Q_PROPERTY(QString libelleEtat READ libelleEtat NOTIFY etatChange)
    Q_PROPERTY(bool connectee READ estConnectee NOTIFY etatChange)
    Q_PROPERTY(bool occupee READ estOccupee NOTIFY etatChange)
    Q_PROPERTY(QString derniereErreur READ derniereErreur NOTIFY etatChange)
    Q_PROPERTY(bool navigateurNonOuvert READ navigateurNonOuvert NOTIFY etatChange)
    Q_PROPERTY(int secondesRestantes READ secondesRestantes NOTIFY attenteChange)
    Q_PROPERTY(QString avertissement READ avertissement NOTIFY etatChange)
    Q_PROPERTY(QString identifiant READ identifiant NOTIFY identiteChange)
    Q_PROPERTY(QString nomAffiche READ nomAffiche NOTIFY identiteChange)
    Q_PROPERTY(QString courriel READ courriel NOTIFY identiteChange)
    Q_PROPERTY(QString fournisseur READ fournisseur NOTIFY identiteChange)
    Q_PROPERTY(QString expiration READ expiration NOTIFY identiteChange)
    Q_PROPERTY(bool memoriser READ memoriser WRITE setMemoriser NOTIFY memoriserChange)
    Q_PROPERTY(QString avisCoffre READ avisCoffre NOTIFY avisCoffreChange)
    Q_PROPERTY(QString bilanDeconnexion READ bilanDeconnexion NOTIFY avisCoffreChange)

public:
    using Horloge = std::function<QDateTime()>;

    SessionHermes(ApiClient *client, CredentialVault *coffre, SettingsStore *reglages,
                  QObject *parent = nullptr);
    ~SessionHermes() override;

    // --- Pour les tests seulement --------------------------------------------
    void setHorloge(Horloge horloge);
    void setRecul(const Backoff &recul) { m_recul = recul; }
    [[nodiscard]] NativeAuthFlow *flux() const { return m_flux; }

    // --- État ------------------------------------------------------------------
    [[nodiscard]] SessionStatus::State etat() const { return m_etat; }
    [[nodiscard]] int etatValeur() const { return static_cast<int>(m_etat); }
    [[nodiscard]] QString libelleEtat() const;
    [[nodiscard]] bool estConnectee() const { return m_etat == SessionStatus::Connectee; }
    [[nodiscard]] bool estOccupee() const;
    [[nodiscard]] const QString &derniereErreur() const { return m_derniereErreur; }
    [[nodiscard]] bool navigateurNonOuvert() const;
    [[nodiscard]] int secondesRestantes() const;
    [[nodiscard]] QString avertissement() const;

    [[nodiscard]] QString identifiant() const;
    [[nodiscard]] QString nomAffiche() const;
    [[nodiscard]] QString courriel() const;
    [[nodiscard]] QString fournisseur() const;
    [[nodiscard]] QString expiration() const;

    [[nodiscard]] bool memoriser() const;
    void setMemoriser(bool memoriser);
    [[nodiscard]] const QString &avisCoffre() const { return m_avisCoffre; }
    [[nodiscard]] const QString &bilanDeconnexion() const { return m_bilanDeconnexion; }

    /*! Jeton d'accès courant, pour le transport seulement. Jamais vers QML. */
    [[nodiscard]] QByteArray jetonAcces() const { return m_jetons.acces; }
    /*! Échéance du jeton d'accès (UTC), invalide hors session. */
    [[nodiscard]] QDateTime echeanceAcces() const { return m_jetons.expireLe; }

    // --- Gestes ----------------------------------------------------------------
    /*! Démarrage : jeton mémorisé pour ce serveur ⇒ rafraîchissement immédiat. */
    void restaurer();
    /*! Connexion par le navigateur système. */
    Q_INVOKABLE void seConnecter();
    Q_INVOKABLE void annulerConnexion();
    /*! Révocation chez Hermes puis oubli local, quoi qu'il arrive. */
    Q_INVOKABLE void seDeconnecter();
    /*! Copie le lien d'autorisation dans le presse-papiers, depuis le C++. */
    Q_INVOKABLE bool copierLienConnexion();
    /*! Nouvel essai immédiat du rafraîchissement (après une panne). */
    Q_INVOKABLE void reessayer();
    /*! Rotation des jetons ; un seul vol à la fois. */
    void rafraichir();

signals:
    void etatChange();
    void identiteChange();
    void memoriserChange();
    void avisCoffreChange();
    void attenteChange();
    /*! Identité lue : la session est établie (connexion ou restauration). */
    void sessionEtablie();
    /*! Toute transition vers un état non connecté, avec sa raison. */
    void sessionPerdue(const QString &raison);
    /*! Rotation réussie, nouveau jeton déjà mémorisé s'il devait l'être. */
    void jetonsRenouveles();

private:
    void changerEtat(SessionStatus::State etat, const QString &erreur = {});
    void suivreFlux();
    void adopter(const JetonsHermes &jetons);
    void lireIdentite();
    void etablir();
    void planifierRafraichissement();
    void echecRafraichissement(const ApiError &erreur);
    void perdre(SessionStatus::State etat, const QString &raison, bool oublierCoffre);
    void effacerSession();
    void setAvisCoffre(const QString &avis);
    void ecrireCoffre(const JetonsHermes &jetons);
    [[nodiscard]] QDateTime maintenant() const;

    ApiClient *m_client = nullptr;
    JetonsCoffre m_coffre;
    SettingsStore *m_reglages = nullptr;
    NativeAuthFlow *m_flux = nullptr;
    QTimer *m_minuterie = nullptr;   //!< Rafraichissement avant échéance.
    QTimer *m_relance = nullptr;     //!< Nouvel essai après panne.
    QTimer *m_tic = nullptr;         //!< Décompte de l'attente du navigateur.
    Backoff m_recul{std::chrono::milliseconds(1000), std::chrono::milliseconds(60000), 25};
    Horloge m_horloge;

    SessionStatus::State m_etat = SessionStatus::NonConfiguree;
    QString m_derniereErreur;
    QString m_avisCoffre;
    QString m_bilanDeconnexion;
    JetonsHermes m_jetons;
    QUrl m_serveur;
    QString m_nomAffiche;
    QString m_courriel;
    bool m_identiteLue = false;
    bool m_rafraichissementEnVol = false;
    QPointer<ApiCall> m_appelRafraichissement;
    int m_echecsConsecutifs = 0;
    QDateTime m_premierEchec;
    quint64 m_generation = 0;
};

} // namespace acp
