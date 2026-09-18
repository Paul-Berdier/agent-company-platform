// Modèle de navigation latérale.
//
// L'audit relève que le shell web déclare « sept routes, toutes configured: true », et
// que `docs/design-system.md` est périmé sur ce point. La station ne recopie pas cette
// liste : elle déclare ses propres destinations, avec pour chacune un état HONNÊTE.
//
// Une destination peut être :
//   - Ready        : l'écran existe et fonctionne dans cette fondation ;
//   - Planned      : la destination est prévue mais aucun écran n'est encore livré.
//                    Elle apparaît, désactivée, avec « Indisponible pour l'instant ».
//                    Elle n'est pas masquée : masquer ferait croire à une absence de
//                    projet, et la montrer active serait un bouton qui fait semblant ;
//   - OutOfScope   : explicitement hors périmètre, avec la raison.

#pragma once

#include <QAbstractListModel>
#include <QList>
#include <QString>

namespace acp {

class NavigationModel : public QAbstractListModel
{
    Q_OBJECT
    Q_PROPERTY(QString currentRoute READ currentRoute WRITE setCurrentRoute NOTIFY currentRouteChanged)
    Q_PROPERTY(QString currentTitle READ currentTitle NOTIFY currentRouteChanged)

public:
    enum class Readiness {
        Ready,      //!< Écran livré et opérationnel.
        Planned,    //!< Destination prévue, écran non livré : désactivée et expliquée.
        OutOfScope, //!< Hors périmètre assumé, avec sa raison.
    };
    Q_ENUM(Readiness)

    enum Roles {
        RouteRole = Qt::UserRole + 1,
        TitleRole,
        GlyphRole,
        ReadinessRole,
        ReadinessLabelRole,
        DetailRole,
        EnabledRole,
    };
    Q_ENUM(Roles)

    struct Destination
    {
        QString route;
        QString title;
        QString glyph;  //!< Nom sémantique ; le jeu d'icônes n'est PAS choisi (voir les
                        //!< jetons : `$iconSet.resolved` vaut false).
        Readiness readiness = Readiness::Planned;
        QString detail; //!< Explication française, affichée pour tout état non Ready.
    };

    explicit NavigationModel(QObject *parent = nullptr);

    [[nodiscard]] int rowCount(const QModelIndex &parent = {}) const override;
    [[nodiscard]] QVariant data(const QModelIndex &index, int role) const override;
    [[nodiscard]] QHash<int, QByteArray> roleNames() const override;

    [[nodiscard]] const QString &currentRoute() const { return m_currentRoute; }
    void setCurrentRoute(const QString &route);
    [[nodiscard]] QString currentTitle() const;

    /*! Vrai si la route existe ET est prête. Une route prévue n'est pas navigable. */
    [[nodiscard]] Q_INVOKABLE bool isNavigable(const QString &route) const;

    /*! Explication de l'indisponibilité, ou chaîne vide si la route est prête. */
    [[nodiscard]] Q_INVOKABLE QString detailFor(const QString &route) const;

signals:
    void currentRouteChanged();

    /*! Émis quand une route non navigable est demandée. L'interface affiche le détail. */
    void navigationRefused(const QString &route, const QString &detail);

private:
    [[nodiscard]] int indexOfRoute(const QString &route) const;

    QList<Destination> m_destinations;
    QString m_currentRoute;
};

} // namespace acp
