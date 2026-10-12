// Rendu natif des réponses : Markdown sans HTML ni chargement de ressources.
#pragma once
#include <QObject>
#include <QVariantList>
#include <QUrl>
namespace acp {
class TexteDiscussion : public QObject
{
    Q_OBJECT
public:
    explicit TexteDiscussion(QObject *parent = nullptr) : QObject(parent) {}
    Q_INVOKABLE QVariantList blocs(const QString &texte) const;
    Q_INVOKABLE bool copier(const QString &texte) const;
    Q_INVOKABLE bool ouvrirLien(const QString &lien) const;
    static QString htmlSur(const QString &texte);
    static bool lienAutorise(const QUrl &url);
};
} // namespace acp
