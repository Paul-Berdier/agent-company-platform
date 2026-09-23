// Registre des commandes, et modèle de liste consommé par la palette QML.

#pragma once

#include "commands/Command.h"

#include <QAbstractListModel>
#include <QHash>
#include <QList>
#include <QObject>
#include <QString>

namespace acp {

class CommandRegistry : public QAbstractListModel
{
    Q_OBJECT
    Q_PROPERTY(QString filter READ filter WRITE setFilter NOTIFY filterChanged)
    Q_PROPERTY(int count READ rowCount NOTIFY countChanged)
    Q_PROPERTY(int totalCount READ totalCount NOTIFY countChanged)

public:
    enum Roles {
        IdRole = Qt::UserRole + 1,
        TitleRole,
        CategoryRole,
        ShortcutRole,
        AvailableRole,
        AvailabilityReasonRole,
    };
    Q_ENUM(Roles)

    explicit CommandRegistry(QObject *parent = nullptr);

    /*!
        Enregistre une commande. Un identifiant déjà pris est REFUSÉ : deux modules qui
        revendiquent la même commande est un défaut de conception, pas une préférence de
        dernier arrivé.

        Renvoie faux et laisse le registre intact en cas de refus.
    */
    bool registerCommand(Command command);

    /*! Retire une commande. Utile au déchargement d'un module. */
    bool unregisterCommand(const QString &id);

    [[nodiscard]] bool contains(const QString &id) const;
    [[nodiscard]] int totalCount() const { return static_cast<int>(m_commands.size()); }

    /*! Met à jour le contexte et réévalue toutes les disponibilités. */
    void setContext(const CommandContext &context);
    [[nodiscard]] const CommandContext &context() const { return m_context; }

    /*! Disponibilité courante d'une commande. Unavailable si l'identifiant est inconnu. */
    [[nodiscard]] Q_INVOKABLE int availabilityOf(const QString &id) const;
    [[nodiscard]] Q_INVOKABLE QString availabilityReasonOf(const QString &id) const;

    /*!
        Exécute une commande.

        Refuse si l'identifiant est inconnu, ou si la commande n'est pas disponible — avec
        dans les deux cas un message français explicite. Une commande indisponible n'est
        JAMAIS exécutée « pour voir ».
    */
    Q_INVOKABLE QString execute(const QString &id);

    /*! Identifiant de la commande portant ce raccourci, ou chaîne vide. */
    [[nodiscard]] Q_INVOKABLE QString commandForShortcut(const QString &shortcut) const;

    // QAbstractListModel
    [[nodiscard]] int rowCount(const QModelIndex &parent = {}) const override;
    [[nodiscard]] QVariant data(const QModelIndex &index, int role) const override;
    [[nodiscard]] QHash<int, QByteArray> roleNames() const override;

    /*! Filtre de recherche appliqué au titre, à la catégorie et aux mots-clés. */
    [[nodiscard]] const QString &filter() const { return m_filter; }
    void setFilter(const QString &filter);

signals:
    void filterChanged();
    void countChanged();

    /*! Émis après chaque exécution, réussie ou refusée. L'interface l'affiche. */
    void commandExecuted(const QString &id, bool accepted, const QString &message);

private:
    struct Entry
    {
        Command command;
        CommandAvailability availability = CommandAvailability::Unavailable;
    };

    void rebuildVisible();
    [[nodiscard]] bool matchesFilter(const Command &command) const;

    QList<Entry> m_commands;
    QHash<QString, int> m_indexById;
    QList<int> m_visible; //!< Index dans m_commands des commandes passant le filtre.
    CommandContext m_context;
    QString m_filter;
};

} // namespace acp
