// Connexion native de la station à Hermes (RFC 8252 : navigateur système, bouclage, PKCE).
//
// Séquence (hermes_cli/dashboard_auth/routes.py, Hermes 0.21.5) :
//   1. `GET /api/health` : `auth_required` doit valoir vrai ;
//   2. `GET /api/auth/providers` : le fournisseur `self-hosted` (Authelia) doit y figurer ; il
//      est choisi EXPLICITEMENT, même si d'autres fournisseurs sont déclarés ;
//   3. paire PKCE S256 et état tirés du générateur du système, écouteur ouvert sur
//      127.0.0.1, navigateur système ouvert sur `/auth/native/authorize?provider=self-hosted&
//      code_challenge=…&code_challenge_method=S256&redirect_uri=http://127.0.0.1:<port>/rappel&
//      state=…` ; Hermes mène la connexion chez Authelia puis renvoie le navigateur vers le
//      bouclage avec un code à usage unique (120 s) ;
//   4. `POST /auth/native/token {code, code_verifier}` : jetons en porteur, contrôlés.
//
// Ce que ce flux ne fait JAMAIS : décoder le JWT, parler à Authelia, lire un cookie,
// journaliser le code, le vérificateur ou l'état. Un seul flux à la fois ; délai global de
// 600 s (l'attente de Hermes), puis échec explicite.

#pragma once

#include "auth/JetonsHermes.h"
#include "auth/PairePkce.h"

#include <QDateTime>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QUrl>

#include <chrono>
#include <functional>

class QTimer;

namespace acp {

class ApiCall;
class ApiClient;
class EcouteurBouclage;

class NativeAuthFlow : public QObject
{
    Q_OBJECT

public:
    enum class Etape {
        Inactif,
        Prerequis,          //!< Lecture de /api/health et /api/auth/providers.
        AttenteNavigateur,  //!< Écouteur ouvert, navigateur système en cours.
        Echange,            //!< Code reçu, échange contre les jetons.
    };

    //! Nom du fournisseur OIDC auto-hébergé de Hermes (avec un tiret : docs/reprise-poste.md § 5, « Image Hermes et
    //! exécutant »).
    static constexpr char kFournisseur[] = "self-hosted";

    using OuvreurNavigateur = std::function<bool(const QUrl &)>;
    using Horloge = std::function<QDateTime()>;

    explicit NativeAuthFlow(ApiClient *client, QObject *parent = nullptr);
    ~NativeAuthFlow() override;

    /*! Remplace l'ouverture du navigateur système (QDesktopServices). Tests seulement. */
    void setOuvreurNavigateur(OuvreurNavigateur ouvreur);
    /*! Délai global d'attente (600 s par défaut, l'attente de Hermes). Tests seulement. */
    void setDelaiAttente(std::chrono::milliseconds delai);
    /*! Horloge UTC (contrôle d'échéance des jetons). Tests seulement. */
    void setHorloge(Horloge horloge);

    /*! Démarre un flux. Sans effet si un flux est déjà en cours. */
    void demarrer();

    /*! Abandonne le flux en cours sans signal : écouteur fermé, secrets effacés. */
    void annuler();

    [[nodiscard]] Etape etape() const { return m_etape; }
    [[nodiscard]] bool enCours() const { return m_etape != Etape::Inactif; }

    /*!
        Lien d'autorisation à ouvrir dans un navigateur, vide hors attente. Il ne contient
        ni code ni vérificateur, mais porte l'état : il ne quitte jamais le C++ (la copie
        vers le presse-papiers est faite par la session).
    */
    [[nodiscard]] const QUrl &lienAutorisation() const { return m_lien; }
    [[nodiscard]] QUrl redirectUri() const;
    [[nodiscard]] bool navigateurOuvert() const { return m_navigateurOuvert; }
    [[nodiscard]] int secondesRestantes() const;
    [[nodiscard]] const QString &avertissement() const { return m_avertissement; }

signals:
    void etapeChangee();
    /*! Jetons reçus et contrôlés. Le flux est déjà terminé et ses secrets effacés. */
    void reussi(const acp::JetonsHermes &jetons);
    /*! Échec, raison en français. Le flux est déjà terminé. */
    void echoue(const QString &raison);

private:
    void lireFournisseurs(quint64 generation);
    void ouvrirAttente();
    void echanger(QByteArray code);
    void terminer();
    void echouer(const QString &raison);
    void changerEtape(Etape etape);
    [[nodiscard]] QDateTime maintenant() const;

    ApiClient *m_client = nullptr;
    EcouteurBouclage *m_ecouteur = nullptr;
    QTimer *m_delai = nullptr;
    PairePkce m_paire;
    QUrl m_lien;
    QPointer<ApiCall> m_appel;
    Etape m_etape = Etape::Inactif;
    OuvreurNavigateur m_ouvreur;
    Horloge m_horloge;
    QDateTime m_finAttente;
    std::chrono::milliseconds m_delaiAttente{600000};
    bool m_navigateurOuvert = false;
    QString m_avertissement;
    quint64 m_generation = 0;
};

} // namespace acp
