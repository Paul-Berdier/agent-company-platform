// Une commande de la station, son contexte d'exécution et son résultat.
//
// Le registre est le seul point d'entrée des actions de l'application : un bouton, un
// raccourci clavier et la palette de commandes exécutent tous LA MÊME commande. C'est ce
// qui permet de tenir la règle « aucun bouton qui fait semblant » : la disponibilité est
// calculée une fois, dans le prédicat de la commande, et l'interface se contente de la
// refléter — bouton absent, désactivé avec explication, ou « Indisponible pour l'instant ».

#pragma once

#include <QString>
#include <QStringList>
#include <QVariantMap>

#include <functional>

namespace acp {

/*! Pourquoi une commande n'est pas exécutable maintenant. */
enum class CommandAvailability {
    Available,     //!< Exécutable.
    NeedsSession,  //!< Une session est requise et il n'y en a pas.
    NeedsRole,     //!< Le rôle de l'utilisateur ne suffit pas pour cette portée.
    NeedsSelection,//!< Une cible doit être sélectionnée.
    Offline,       //!< Le serveur est injoignable ; l'écriture échouerait.
    NotConfigured, //!< La capacité serveur n'est pas configurée.
    Unavailable,   //!< Fonction absente de ce serveur (compatibilité).
};

/*! Ce qu'une commande peut consulter pour décider de sa disponibilité. */
struct CommandContext
{
    bool sessionConnected = false;
    bool online = false;
    QString platformRole;   //!< « owner », « operator », « member », « viewer » ou vide.
    QString currentRoute;   //!< Route affichée, pour les commandes contextuelles.
    QString selectionId;    //!< Objet sélectionné, s'il y en a un.
    QVariantMap extra;      //!< Données supplémentaires posées par un module.
};

/*! Ce qu'une exécution rend. Jamais un booléen nu : la raison est affichée. */
struct CommandResult
{
    bool accepted = false;
    QString message; //!< Message français, affiché tel quel quand il est non vide.

    static CommandResult accept(QString message = {})
    {
        return CommandResult{true, std::move(message)};
    }
    static CommandResult reject(QString message)
    {
        return CommandResult{false, std::move(message)};
    }
};

/*! Définition d'une commande. Les modules en enregistrent, ils n'en câblent pas. */
struct Command
{
    //! Identifiant stable, en points : « mission.create », « session.logout ».
    QString id;

    //! Libellé français affiché dans la palette et dans les menus.
    QString title;

    //! Groupe d'appartenance, pour le classement de la palette.
    QString category;

    //! Mots-clés supplémentaires pour la recherche, en français.
    QStringList keywords;

    //! Séquence de touches, au format Qt (« Ctrl+K »). Vide si aucune.
    QString shortcut;

    /*! Prédicat de disponibilité. Il doit être PUR et rapide : il est évalué à chaque
        ouverture de la palette et à chaque changement de contexte. */
    std::function<CommandAvailability(const CommandContext &)> availability;

    /*! Exécution. Elle n'est appelée QUE si `availability` a renvoyé Available ; le
        registre le garantit, la commande n'a donc pas à revérifier. */
    std::function<CommandResult(const CommandContext &)> run;
};

/*! Libellé français de l'indisponibilité, affiché à côté d'un contrôle désactivé. */
[[nodiscard]] QString describeAvailability(CommandAvailability availability);

} // namespace acp
