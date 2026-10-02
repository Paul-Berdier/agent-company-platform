#include "models/JsonListModel.h"
#include <QJsonObject>
#include <QSet>

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
void JsonListModel::appendItem(const QJsonObject &item)
{
    const int rang = count();
    beginInsertRows({}, rang, rang);
    m_items.append(item);
    endInsertRows();
    emit countChanged();
}

void JsonListModel::setItem(int index, const QJsonObject &item)
{
    if (index < 0 || index >= count()) return;
    m_items.replace(index, item);
    const QModelIndex cible = this->index(index);
    emit dataChanged(cible, cible);
}

QJsonObject JsonListModel::itemAt(int index) const
{
    return index >= 0 && index < count() ? m_items.at(index).toObject() : QJsonObject();
}

QString JsonListModel::cleDe(const QJsonValue &item) const
{
    const QJsonObject objet = item.toObject();
    QStringList parties;
    for (const QString &champ : m_cle) {
        const QJsonValue valeur = objet.value(champ);
        if (!valeur.isString() || valeur.toString().isEmpty()) {
            return {};
        }
        parties.append(valeur.toString());
    }
    // Séparateur hors de tout identifiant lisible : deux paires distinctes ne se confondent pas.
    return parties.join(QChar(0x1f));
}

bool JsonListModel::clesUtilisables(const QJsonArray &items) const
{
    QSet<QString> vues;
    for (const QJsonValue &item : items) {
        const QString cle = cleDe(item);
        if (cle.isEmpty() || vues.contains(cle)) {
            return false;
        }
        vues.insert(cle);
    }
    return true;
}

void JsonListModel::setItems(const QJsonArray &items)
{
    if (m_cle.isEmpty() || !clesUtilisables(items) || !clesUtilisables(m_items)) {
        reinitialiser(items);
        return;
    }
    fusionner(items);
}

void JsonListModel::reinitialiser(const QJsonArray &items)
{
    beginResetModel();
    m_items = items;
    endResetModel();
    emit countChanged();
}

void JsonListModel::fusionner(const QJsonArray &items)
{
    const int avant = count();
    QSet<QString> nouvelles;
    for (const QJsonValue &item : items) {
        nouvelles.insert(cleDe(item));
    }
    // 1. Lignes disparues : retirées une à une, du bas vers le haut.
    for (int rang = count() - 1; rang >= 0; --rang) {
        if (!nouvelles.contains(cleDe(m_items.at(rang)))) {
            beginRemoveRows({}, rang, rang);
            m_items.removeAt(rang);
            endRemoveRows();
        }
    }
    // 2. Dans l'ordre de la nouvelle liste : ligne en place (modifiée si besoin), déplacée
    //    depuis plus bas, ou insérée.
    for (int rang = 0; rang < items.size(); ++rang) {
        const QJsonValue nouvelle = items.at(rang);
        const QString cle = cleDe(nouvelle);
        if (rang >= count() || cleDe(m_items.at(rang)) != cle) {
            int source = -1;
            for (int autre = rang + 1; autre < count(); ++autre) {
                if (cleDe(m_items.at(autre)) == cle) {
                    source = autre;
                    break;
                }
            }
            if (source < 0) {
                beginInsertRows({}, rang, rang);
                m_items.insert(rang, nouvelle);
                endInsertRows();
                continue;
            }
            beginMoveRows({}, source, source, {}, rang);
            const QJsonValue deplacee = m_items.takeAt(source);
            m_items.insert(rang, deplacee);
            endMoveRows();
        }
        if (m_items.at(rang) != nouvelle) {
            m_items.replace(rang, nouvelle);
            const QModelIndex cible = index(rang);
            emit dataChanged(cible, cible);
        }
    }
    if (avant != count()) {
        emit countChanged();
    }
}
}
