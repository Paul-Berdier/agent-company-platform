#include "commands/CommandRegistry.h"

namespace acp {

QString describeAvailability(CommandAvailability availability)
{
    switch (availability) {
    case CommandAvailability::Available:
        return QString();
    case CommandAvailability::NeedsSession:
        return QStringLiteral("Connectez-vous pour utiliser cette commande.");
    case CommandAvailability::NeedsRole:
        return QStringLiteral("Votre rôle ne permet pas cette action sur cette portée.");
    case CommandAvailability::NeedsSelection:
        return QStringLiteral("Sélectionnez d'abord l'élément concerné.");
    case CommandAvailability::Offline:
        return QStringLiteral("Hors ligne : l'action échouerait et n'est pas mise en file.");
    case CommandAvailability::NotConfigured:
        return QStringLiteral("Cette capacité n'est pas configurée sur le serveur.");
    case CommandAvailability::Unavailable:
        return QStringLiteral("Indisponible pour l'instant.");
    }
    return QStringLiteral("Indisponible pour l'instant.");
}

CommandRegistry::CommandRegistry(QObject *parent)
    : QAbstractListModel(parent)
{
}

bool CommandRegistry::registerCommand(Command command)
{
    if (command.id.isEmpty() || command.title.isEmpty()) {
        return false;
    }
    if (!command.availability || !command.run) {
        // Une commande sans prédicat ni exécution serait un bouton qui fait semblant.
        return false;
    }
    if (m_indexById.contains(command.id)) {
        return false;
    }

    Entry entry;
    entry.availability = command.availability(m_context);
    entry.command = std::move(command);

    m_indexById.insert(entry.command.id, static_cast<int>(m_commands.size()));
    m_commands.append(std::move(entry));
    rebuildVisible();
    emit countChanged();
    return true;
}

bool CommandRegistry::unregisterCommand(const QString &id)
{
    const auto iterator = m_indexById.constFind(id);
    if (iterator == m_indexById.constEnd()) {
        return false;
    }
    const int removed = iterator.value();
    m_commands.removeAt(removed);
    // Les index qui suivaient reculent d'un cran : la table est reconstruite plutôt que
    // corrigée à la main, ce qui écarte toute divergence.
    m_indexById.clear();
    for (int index = 0; index < m_commands.size(); ++index) {
        m_indexById.insert(m_commands.at(index).command.id, index);
    }
    rebuildVisible();
    emit countChanged();
    return true;
}

bool CommandRegistry::contains(const QString &id) const
{
    return m_indexById.contains(id);
}

void CommandRegistry::setContext(const CommandContext &context)
{
    m_context = context;
    for (Entry &entry : m_commands) {
        entry.availability = entry.command.availability(m_context);
    }
    rebuildVisible();
    if (!m_visible.isEmpty()) {
        emit dataChanged(index(0), index(m_visible.size() - 1),
                         {AvailableRole, AvailabilityReasonRole});
    }
}

int CommandRegistry::availabilityOf(const QString &id) const
{
    const auto iterator = m_indexById.constFind(id);
    if (iterator == m_indexById.constEnd()) {
        return static_cast<int>(CommandAvailability::Unavailable);
    }
    return static_cast<int>(m_commands.at(iterator.value()).availability);
}

QString CommandRegistry::availabilityReasonOf(const QString &id) const
{
    const auto iterator = m_indexById.constFind(id);
    if (iterator == m_indexById.constEnd()) {
        return QStringLiteral("Commande inconnue : « %1 ».").arg(id);
    }
    return describeAvailability(m_commands.at(iterator.value()).availability);
}

QString CommandRegistry::execute(const QString &id)
{
    const auto iterator = m_indexById.constFind(id);
    if (iterator == m_indexById.constEnd()) {
        const QString message = QStringLiteral("Commande inconnue : « %1 ».").arg(id);
        emit commandExecuted(id, false, message);
        return message;
    }
    Entry &entry = m_commands[iterator.value()];
    // La disponibilité est réévaluée AU MOMENT de l'exécution : le contexte a pu changer
    // entre l'affichage de la palette et le clic.
    entry.availability = entry.command.availability(m_context);
    if (entry.availability != CommandAvailability::Available) {
        const QString message = describeAvailability(entry.availability);
        emit commandExecuted(id, false, message);
        return message;
    }
    const CommandResult result = entry.command.run(m_context);
    emit commandExecuted(id, result.accepted, result.message);
    return result.message;
}

QString CommandRegistry::commandForShortcut(const QString &shortcut) const
{
    if (shortcut.isEmpty()) {
        return {};
    }
    for (const Entry &entry : m_commands) {
        if (entry.command.shortcut.compare(shortcut, Qt::CaseInsensitive) == 0) {
            return entry.command.id;
        }
    }
    return {};
}

int CommandRegistry::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_visible.size());
}

QVariant CommandRegistry::data(const QModelIndex &modelIndex, int role) const
{
    if (!modelIndex.isValid() || modelIndex.row() < 0 || modelIndex.row() >= m_visible.size()) {
        return {};
    }
    const Entry &entry = m_commands.at(m_visible.at(modelIndex.row()));
    switch (role) {
    case IdRole:
        return entry.command.id;
    case TitleRole:
        return entry.command.title;
    case CategoryRole:
        return entry.command.category;
    case ShortcutRole:
        return entry.command.shortcut;
    case AvailableRole:
        return entry.availability == CommandAvailability::Available;
    case AvailabilityReasonRole:
        return describeAvailability(entry.availability);
    default:
        return {};
    }
}

QHash<int, QByteArray> CommandRegistry::roleNames() const
{
    return {
        {IdRole, QByteArrayLiteral("commandId")},
        {TitleRole, QByteArrayLiteral("title")},
        {CategoryRole, QByteArrayLiteral("category")},
        {ShortcutRole, QByteArrayLiteral("shortcut")},
        {AvailableRole, QByteArrayLiteral("available")},
        {AvailabilityReasonRole, QByteArrayLiteral("availabilityReason")},
    };
}

void CommandRegistry::setFilter(const QString &filter)
{
    if (m_filter == filter) {
        return;
    }
    m_filter = filter;
    rebuildVisible();
    emit filterChanged();
}

bool CommandRegistry::matchesFilter(const Command &command) const
{
    if (m_filter.isEmpty()) {
        return true;
    }
    if (command.title.contains(m_filter, Qt::CaseInsensitive)
        || command.category.contains(m_filter, Qt::CaseInsensitive)
        || command.id.contains(m_filter, Qt::CaseInsensitive)) {
        return true;
    }
    for (const QString &keyword : command.keywords) {
        if (keyword.contains(m_filter, Qt::CaseInsensitive)) {
            return true;
        }
    }
    return false;
}

void CommandRegistry::rebuildVisible()
{
    beginResetModel();
    m_visible.clear();
    for (int index = 0; index < m_commands.size(); ++index) {
        if (matchesFilter(m_commands.at(index).command)) {
            m_visible.append(index);
        }
    }
    // Les commandes indisponibles RESTENT visibles, désactivées et accompagnées de leur
    // raison. Les masquer laisserait croire qu'elles n'existent pas.
    endResetModel();
    emit countChanged();
}

} // namespace acp
