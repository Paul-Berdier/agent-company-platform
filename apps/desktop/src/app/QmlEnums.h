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
        Degraded,     //!< Le service répond mais signale un défaut (`ok` absent ou faux).
        Offline,      //!< Aucune réponse : le lien manque, le travail n'a pas raté.
    };
    Q_ENUM(State)

    using QObject::QObject;
};

/*!
    États explicites de la session auprès de Hermes (connexion native, RFC 8252).

    Aucun état implicite, aucun « peut-être ». Toute transition vers un état non connecté
    est accompagnée de sa raison, en français.
*/
class SessionStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        NonConfiguree,          //!< Aucune adresse de serveur.
        Deconnectee,            //!< Aucune session ; la connexion par le navigateur est le seul chemin.
        AttenteNavigateur,      //!< Écouteur de bouclage ouvert, navigateur système en cours.
        Echange,                //!< Code reçu, échange contre les jetons en cours.
        Connectee,              //!< Jeton d'accès valide détenu en mémoire.
        Rafraichissement,       //!< Rotation du jeton de rafraîchissement en cours.
        FournisseurInjoignable, //!< 503 au rafraîchissement : jeton gardé, nouvel essai.
        HorsLigne,              //!< Serveur injoignable : jeton gardé, nouvel essai.
        Expiree,                //!< Jeton refusé par le fournisseur : reconnexion nécessaire.
        Refusee,                //!< Connexion refusée (raison française).
    };
    Q_ENUM(State)

    using QObject::QObject;
};

/*! Compatibilité de la station avec le Hermes et le greffon acp-poste servis. */
class CompatibilityStatus : public QObject
{
    Q_OBJECT

public:
    enum State {
        NonVerifiee,   //!< Aucune lecture de /v1/meta encore.
        Verification,  //!< Lecture en cours.
        Compatible,    //!< Contrat, OpenRPC et version de Hermes conformes.
        Avertissement, //!< Utilisable, mais un écart est signalé (version, empreinte, alertes).
        Incompatible,  //!< Contrat du greffon d'une autre majeure : pages du greffon bloquées.
        GreffonAbsent, //!< /v1/meta en 404 : seules Discussion et Diagnostics restent.
        Injoignable,   //!< Lecture impossible : rien n'est supposé.
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
        Forbidden,          //!< 403 : identité connue, droit ou origine refusés.
        NotFound,           //!< 404 : hors portée ou inexistant ; l'API ne distingue pas.
        Conflict,           //!< 409 : état incompatible avec l'action demandée.
        Unprocessable,      //!< 422 : le corps envoyé est refusé par le contrat.
        RateLimited,        //!< 429 : trop de flux ou trop d'appels ; Retry-After est lu.
        ServerError,        //!< 5xx hors 503.
        ServiceUnavailable, //!< 503 : dépendance indisponible.
        Incompatible,       //!< Version de contrat refusée par le service de compatibilité.
        InvalidResponse,    //!< Réponse hors contrat : rien n'est rendu partiellement.
        IdentityProviderUnavailable, //!< 503 de Hermes « Auth provider … unreachable ».
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
