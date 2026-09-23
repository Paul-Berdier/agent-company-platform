// Énumérations partagées entre le C++ et QML.
//
// Elles vivent dans des classes QObject qui ne portent QUE des énumérations. Elles sont
// enregistrées auprès du moteur QML comme types NON instanciables, par appel explicite à
// qmlRegisterUncreatableType() dans acp::Application::registerQmlTypes(). QML peut alors
// écrire `SessionStatus.Connected` sans jamais pouvoir instancier l'objet.
//
// Choix assumé : aucune macro QML_ELEMENT dans cette bibliothèque. Les macros de
// déclaration exigent que le fichier appartienne aux SOURCES d'un qt_add_qml_module ;
// l'enregistrement impératif garde `acp_core` indépendant du module QML, ce qui permet
// aux cibles de test de lier la logique sans embarquer la scène graphique.

#pragma once

#include <QObject>

namespace acp {

/*! États du lien entre la station et l'API. Ce n'est PAS un état de tâche. */
class LinkStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        Unknown,      //!< Aucune mesure encore effectuée : « Inconnu », jamais « OK ».
        Probing,      //!< Un contrôle est en cours.
        Online,       //!< Dernier échange réussi, horodaté.
        Degraded,     //!< Le service répond mais un contrôle a échoué (/ready en 503).
        Offline,      //!< Aucune réponse : le lien manque, le travail n'a pas raté.
    };
    Q_ENUM(State)

    using QObject::QObject;
};

/*! États explicites de la session humaine. Aucun état implicite, aucun « peut-être ». */
class SessionStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        Disconnected, //!< Aucune session ; l'écran d'authentification est le seul chemin.
        Connecting,   //!< Authentification ou reprise en cours.
        Connected,    //!< Session valide, jeton CSRF détenu.
        Expired,      //!< La durée de session est écoulée (12 h par défaut côté serveur).
        Revoked,      //!< Le serveur a refusé la session ou l'appartenance (401/403, SSE closed).
        Offline,      //!< Session peut-être valide, mais le serveur est injoignable.
    };
    Q_ENUM(State)

    using QObject::QObject;
};

/*! Résultat de la vérification de compatibilité client / serveur. */
class CompatibilityStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        NotChecked,         //!< Aucune vérification encore tentée.
        Checking,           //!< Vérification en cours.
        Compatible,         //!< Contrat d'API et version cliente acceptés par le serveur.
        ClientTooOld,       //!< Le serveur exige une version cliente supérieure.
        ServerTooOld,       //!< Le serveur sert un contrat que ce client ne sait plus lire.
        FeatureUnavailable, //!< Le point d'entrée de compatibilité n'existe pas (404).
        Unreachable,        //!< Le serveur n'a pas répondu ; rien n'est supposé.
    };
    Q_ENUM(State)

    using QObject::QObject;
};

/*! États publiés par le service de flux d'événements. */
class StreamStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        Idle,         //!< Aucun abonnement demandé.
        Connecting,   //!< Ouverture du flux.
        Live,         //!< Flux ouvert, événements reçus au fil de l'eau.
        Reconnecting, //!< Coupure détectée, attente du prochain essai.
        Polling,      //!< Repli sur l'interrogation périodique du journal durable.
        Offline,      //!< Ni le flux ni l'interrogation ne passent.
        Refused,      //!< Refus serveur définitif (403, ou fermeture pour révocation).
    };
    Q_ENUM(State)

    using QObject::QObject;
};

/*! Familles d'échec d'un appel d'API. La couleur ne les distingue pas, le libellé si. */
class ApiFailure : public QObject
{
    Q_OBJECT

public:
    enum Kind {
        None,               //!< Succès.
        ClientRefusal,      //!< Le client refuse d'émettre (URL absente, schéma non sûr, clé invalide).
        Network,            //!< Transport : DNS, TCP, TLS, coupure.
        Timeout,            //!< Délai dépassé.
        Cancelled,          //!< Annulé par l'application ou par l'opérateur.
        Unauthorized,       //!< 401 : la session n'est pas (ou plus) valide.
        Forbidden,          //!< 403 : identité connue, droit refusé — ou jeton CSRF rejeté.
        NotFound,           //!< 404 : hors portée ou inexistant ; l'API ne distingue pas.
        Conflict,           //!< 409 : état incompatible avec l'action demandée.
        Unprocessable,      //!< 422 : le corps envoyé est refusé par le contrat.
        RateLimited,        //!< 429 : trop de flux ou trop d'appels ; Retry-After est lu.
        ServerError,        //!< 5xx hors 503.
        ServiceUnavailable, //!< 503 : dépendance indisponible, /ready en échec.
        Incompatible,       //!< Version de contrat refusée par le service de compatibilité.
        InvalidResponse,    //!< Réponse hors contrat : rien n'est rendu partiellement.
    };
    Q_ENUM(Kind)

    using QObject::QObject;
};

/*! Familles d'états du coffre de secrets du poste. */
class VaultStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        Available,   //!< Un coffre système est disponible et opérationnel.
        Refusing,    //!< Aucun coffre système : le repli REFUSE de stocker, il n'écrit rien.
        Failed,      //!< Le coffre système existe mais a renvoyé une erreur.
    };
    Q_ENUM(State)

    using QObject::QObject;
};

} // namespace acp
