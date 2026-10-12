// Catalogue natif en lecture seule : états lus de Hermes, registre externe descriptif.
// Une skill chargée n'atteste jamais l'installation ni la connexion d'un service tiers.
#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QUrl>
#include <QVariantMap>
#include <functional>

namespace acp {
class ClientGreffonPoste;
class Sondage;

class CatalogueViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *entrees READ entrees CONSTANT)
    Q_PROPERTY(QString recherche READ recherche WRITE setRecherche NOTIFY filtresChange)
    Q_PROPERTY(QString typeFiltre READ typeFiltre WRITE setTypeFiltre NOTIFY filtresChange)
    Q_PROPERTY(QVariantMap selection READ selection NOTIFY selectionChange)
    Q_PROPERTY(bool lue READ lue NOTIFY lectureChange)
    Q_PROPERTY(bool chargement READ chargement NOTIFY lectureChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)
    Q_PROPERTY(QStringList alertes READ alertes NOTIFY lectureChange)

public:
    CatalogueViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent = nullptr);
    ~CatalogueViewModel() override;
    JsonListModel *entrees() const { return m_entrees; }
    QString recherche() const { return m_recherche; }
    QString typeFiltre() const { return m_typeFiltre; }
    QVariantMap selection() const;
    bool lue() const { return m_lue; }
    bool chargement() const;
    QString lecture() const;
    QString erreur() const;
    QStringList alertes() const { return m_alertes; }
    void setRecherche(const QString &texte);
    void setTypeFiltre(const QString &type);
    void setOuvreur(std::function<bool(const QUrl &)> ouvreur) { m_ouvreur = std::move(ouvreur); }
    void setPressePapier(std::function<bool(const QString &)> presse) { m_presse = std::move(presse); }

    Q_INVOKABLE void actualiser();
    Q_INVOKABLE void selectionner(const QString &id);
    Q_INVOKABLE bool ouvrirSource(const QString &id);
    Q_INVOKABLE bool copierConfiguration(const QString &id);
    Q_INVOKABLE QString consignePour(const QString &id) const;

    static bool urlSourceAdmise(const QUrl &url);
    static bool catalogueValide(const QJsonObject &catalogue);
    static QJsonArray construireEntrees(const QJsonObject &catalogue, const QJsonArray &registre);

signals:
    void filtresChange();
    void selectionChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void filtrer();
    QJsonObject trouver(const QString &id) const;
    Sondage *m_sondage;
    JsonListModel *m_entrees;
    QJsonArray m_registre;
    QJsonArray m_toutes;
    QString m_recherche;
    QString m_typeFiltre = QStringLiteral("tous");
    QString m_selection;
    QString m_erreurSchema;
    QStringList m_alertes;
    bool m_lue = false;
    QDateTime m_luA;
    std::function<bool(const QUrl &)> m_ouvreur;
    std::function<bool(const QString &)> m_presse;
};
} // namespace acp
