#include "navigation/NavigationModel.h"

namespace acp {

namespace {

QString readinessLabel(NavigationModel::Readiness readiness)
{
    switch (readiness) {
    case NavigationModel::Readiness::Ready:
        return QStringLiteral("Disponible");
    case NavigationModel::Readiness::Planned:
        return QStringLiteral("Indisponible pour l'instant");
    case NavigationModel::Readiness::OutOfScope:
        return QStringLiteral("Hors périmètre");
    }
    return QStringLiteral("Inconnu");
}

} // namespace

NavigationModel::NavigationModel(QObject *parent)
    : QAbstractListModel(parent)
{
    // Cette fondation livre trois écrans réels : l'accueil (état du lien et de la
    // session), les diagnostics, et l'écran de première ouverture. Tout le reste est
    // déclaré « prévu » et le dit, plutôt que d'afficher une coquille vide.
    m_destinations = {
        {QStringLiteral("home"), QStringLiteral("Accueil"), QStringLiteral("home"),
         Readiness::Ready, QString()},
        {QStringLiteral("diagnostics"), QStringLiteral("Diagnostics"),
         QStringLiteral("stethoscope"), Readiness::Ready, QString()},
        {QStringLiteral("missions"), QStringLiteral("Missions"), QStringLiteral("target"),
         Readiness::Planned,
         QStringLiteral("L'écran des missions n'est pas livré par cette fondation. Les "
                        "routes serveur existent ; l'écran natif viendra dans un lot "
                        "ultérieur.")},
        {QStringLiteral("approvals"), QStringLiteral("Approbations"),
         QStringLiteral("hand-raised"), Readiness::Planned,
         QStringLiteral("La décision d'approbation existe côté serveur et n'a encore aucun "
                        "client. Cet écran en sera le premier ; il n'est pas livré ici.")},
        {QStringLiteral("library"), QStringLiteral("Bibliothèque"), QStringLiteral("archive"),
         Readiness::Planned,
         QStringLiteral("Le gestionnaire de livrables n'est pas livré par cette fondation.")},
        {QStringLiteral("conversations"), QStringLiteral("Conversations"),
         QStringLiteral("message"), Readiness::Planned,
         QStringLiteral("Aucun flux temps réel n'existe pour les conversations : l'écran "
                        "devra interroger périodiquement, ce qui est à décider avant de le "
                        "livrer.")},
        {QStringLiteral("extensions"), QStringLiteral("Extensions"), QStringLiteral("plug"),
         Readiness::Planned,
         QStringLiteral("Centre MCP et bibliothèque de skills : non livrés par cette "
                        "fondation.")},
        {QStringLiteral("office"), QStringLiteral("Bureau de département"),
         QStringLiteral("building"), Readiness::OutOfScope,
         QStringLiteral("Hors périmètre : les ressources graphiques du bureau ne sont pas "
                        "redistribuables, et le moteur existant n'a aucun équivalent natif "
                        "direct. Cette destination ne sera pas ouverte par ce chantier.")},
    };
    m_currentRoute = QStringLiteral("home");
}

int NavigationModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_destinations.size());
}

QVariant NavigationModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_destinations.size()) {
        return {};
    }
    const Destination &destination = m_destinations.at(index.row());
    switch (role) {
    case RouteRole:
        return destination.route;
    case TitleRole:
        return destination.title;
    case GlyphRole:
        return destination.glyph;
    case ReadinessRole:
        return static_cast<int>(destination.readiness);
    case ReadinessLabelRole:
        return readinessLabel(destination.readiness);
    case DetailRole:
        return destination.detail;
    case EnabledRole:
        return destination.readiness == Readiness::Ready;
    default:
        return {};
    }
}

QHash<int, QByteArray> NavigationModel::roleNames() const
{
    return {
        {RouteRole, QByteArrayLiteral("route")},
        {TitleRole, QByteArrayLiteral("title")},
        {GlyphRole, QByteArrayLiteral("glyph")},
        {ReadinessRole, QByteArrayLiteral("readiness")},
        {ReadinessLabelRole, QByteArrayLiteral("readinessLabel")},
        {DetailRole, QByteArrayLiteral("detail")},
        // « navigable » et non « enabled » : un délégué QML hérite déjà d'une propriété
        // `enabled`, qu'un rôle de modèle ne peut pas redéclarer.
        {EnabledRole, QByteArrayLiteral("navigable")},
    };
}

int NavigationModel::indexOfRoute(const QString &route) const
{
    for (int index = 0; index < m_destinations.size(); ++index) {
        if (m_destinations.at(index).route == route) {
            return index;
        }
    }
    return -1;
}

bool NavigationModel::isNavigable(const QString &route) const
{
    const int index = indexOfRoute(route);
    return index >= 0 && m_destinations.at(index).readiness == Readiness::Ready;
}

QString NavigationModel::detailFor(const QString &route) const
{
    const int index = indexOfRoute(route);
    if (index < 0) {
        return QStringLiteral("Destination inconnue : « %1 ».").arg(route);
    }
    return m_destinations.at(index).detail;
}

void NavigationModel::setCurrentRoute(const QString &route)
{
    if (route == m_currentRoute) {
        return;
    }
    if (!isNavigable(route)) {
        // Refus explicite : la destination reste celle en cours, et l'interface affiche
        // la raison. Elle ne bascule pas vers un écran vide.
        emit navigationRefused(route, detailFor(route));
        return;
    }
    m_currentRoute = route;
    emit currentRouteChanged();
}

QString NavigationModel::currentTitle() const
{
    const int index = indexOfRoute(m_currentRoute);
    return index < 0 ? QStringLiteral("Inconnu") : m_destinations.at(index).title;
}

} // namespace acp
