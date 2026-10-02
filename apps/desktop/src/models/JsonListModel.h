#pragma once

#include <QAbstractListModel>
#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QVariantMap>

namespace acp {

// Liste de documents déjà filtrés par le serveur selon les droits de la session.
//
// Mise à jour d'une liste relue (sondage de 15 s) : si une CLÉ est déclarée (setCle), setItems()
// compare l'ancienne et la nouvelle liste ligne par ligne, par identifiant, et ne signale que ce
// qui a changé (ligne modifiée, insérée, retirée ou déplacée). Les délégués des lignes conservées
// ne sont donc jamais détruits : un champ de saisie garde son texte et son focus, une liste garde
// son défilement. Sans clé, ou si la nouvelle liste porte une clé vide ou en double, le modèle est
// réinitialisé comme avant (jamais une ligne rattachée au délégué d'une autre).
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
    /*!
        Champs qui identifient une ligne (« id », ou « tableau » et « carte ») : avec eux,
        setItems() met à jour par différence au lieu de réinitialiser.
    */
    void setCle(const QStringList &champs) { m_cle = champs; }
    [[nodiscard]] const QStringList &cle() const { return m_cle; }
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
    [[nodiscard]] QString cleDe(const QJsonValue &item) const;
    [[nodiscard]] bool clesUtilisables(const QJsonArray &items) const;
    void reinitialiser(const QJsonArray &items);
    void fusionner(const QJsonArray &items);

    QJsonArray m_items;
    QStringList m_cle;
};
}
