#pragma once

#include <QAbstractListModel>
#include <QJsonArray>
#include <QJsonObject>
#include <QVariantMap>

namespace acp {

// Liste de documents déjà filtrés par le serveur selon les droits de la session.
class JsonListModel : public QAbstractListModel
{
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY countChanged)
public:
    enum Role { ItemRole = Qt::UserRole + 1, IdRole, NameRole };
    explicit JsonListModel(QObject *parent = nullptr) : QAbstractListModel(parent) {}
    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    int count() const { return static_cast<int>(m_items.size()); }
    Q_INVOKABLE QVariantMap get(int index) const;
    void setItems(const QJsonArray &items);
    void clear() { setItems({}); }
    //! Ajoute une ligne à la fin (insertion signalée, sans réinitialiser le modèle).
    void appendItem(const QJsonObject &item);
    //! Remplace une ligne existante (changement signalé) ; sans effet hors bornes.
    void setItem(int index, const QJsonObject &item);
    [[nodiscard]] QJsonObject itemAt(int index) const;
signals:
    void countChanged();
private:
    QJsonArray m_items;
};
}
