// Pot de cookies de la station : un seul pour tout le processus.
//
// L'audit relève le piège : « si le pot de cookies n'est pas partagé entre les requêtes
// courtes et les flux, les routes SSE répondront 401 pendant que le reste de
// l'application fonctionne » (section 10.3). Le pot est donc porté par l'unique
// QNetworkAccessManager de l'application, et les flux longs passent par ce même manager.
//
// Deux écarts assumés avec le comportement par défaut de Qt :
//
//  1. Le pot expose `allCookies()` et `setAllCookies()`, que QNetworkCookieJar déclare
//     `protected`. Ils sont nécessaires pour purger la session à la déconnexion et pour
//     savoir si un cookie de session est présent — sans jamais exposer sa VALEUR.
//  2. Rien n'est écrit sur disque. Le cookie de session est un secret : sa persistance
//     éventuelle passe par CredentialVault, jamais par un fichier de cookies.

#pragma once

// Le type complet est exigé : moc génère les métadonnées des signatures qui
// transportent QList<QNetworkCookie>, ce qu'une déclaration anticipée ne permet pas.
#include <QNetworkCookie>
#include <QNetworkCookieJar>
#include <QString>

namespace acp {

//! Nom du cookie de session posé par l'API (apps/api, `acp_session`).
inline constexpr char kSessionCookieName[] = "acp_session";

class SessionCookieJar : public QNetworkCookieJar
{
    Q_OBJECT

public:
    explicit SessionCookieJar(QObject *parent = nullptr);

    /*! Vrai si un cookie nommé `acp_session` est actuellement détenu, quelle qu'en soit
        la valeur. Ne révèle jamais la valeur elle-même. */
    [[nodiscard]] bool hasSessionCookie() const;

    /*! Supprime tous les cookies détenus. Appelé à la déconnexion, à l'expiration, à la
        révocation et au changement d'URL de serveur. */
    void clearAll();

    /*! Nombre de cookies détenus, pour l'écran de diagnostics. Aucune valeur n'est
        publiée, seulement un compte. */
    [[nodiscard]] int cookieCount() const;

signals:
    /*! Émis quand la présence du cookie de session change. Permet à AuthManager de
        détecter une purge côté serveur (Set-Cookie d'expiration sur /auth/logout). */
    void sessionCookiePresenceChanged(bool present);

public:
    // Surcharges du pot : elles enregistrent le changement de présence, sans journaliser
    // la moindre valeur de cookie.
    //
    // Elles sont PUBLIQUES alors que QNetworkCookieJar les déclare protégées, pour que les
    // tests puissent injecter un cookie sans passer par une pile réseau réelle. Élargir la
    // visibilité d'une méthode virtuelle dans une classe dérivée est licite, et le coût est
    // nul : ces méthodes ne divulguent aucune valeur.
    bool setCookiesFromUrl(const QList<QNetworkCookie> &cookies, const QUrl &url) override;
    bool insertCookie(const QNetworkCookie &cookie) override;
    bool updateCookie(const QNetworkCookie &cookie) override;
    bool deleteCookie(const QNetworkCookie &cookie) override;

private:
    void notifyPresence();

    bool m_lastKnownPresence = false;
};

} // namespace acp
