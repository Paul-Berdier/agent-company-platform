#include "models/JsonListModel.h"
#include <QJsonObject>

namespace acp {
int JsonListModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : count();
}
QVariant JsonListModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= count()) return {};
    const auto row = get(index.row());
    if (role == ItemRole) return row;
    if (role == IdRole) return row.value(QStringLiteral("id"));
    if (role == NameRole) return row.value(QStringLiteral("name"));
    return {};
}
QHash<int, QByteArray> JsonListModel::roleNames() const
{
    return {{ItemRole, QByteArrayLiteral("item")}, {IdRole, QByteArrayLiteral("recordId")},
            {NameRole, QByteArrayLiteral("recordName")}};
}
QVariantMap JsonListModel::get(int index) const
{
    return index >= 0 && index < count() ? m_items.at(index).toObject().toVariantMap()
                                         : QVariantMap();
}
void JsonListModel::setItems(const QJsonArray &items)
{
    beginResetModel();
    m_items = items;
    endResetModel();
    emit countChanged();
}
}
