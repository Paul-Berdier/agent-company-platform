// Lecture cursorielle du journal distant ; aucune exécution ni relance côté client.
#pragma once
#include "viewmodels/PageViewModel.h"
#include "models/JsonListModel.h"
#include <QPointer>
#include <QSet>
class QTimer;
namespace acp {
class ApiCall;
class ClientGreffonPoste;
class JournalExecutionViewModel : public PageViewModel {
    Q_OBJECT
    Q_PROPERTY(acp::JsonListModel *evenements READ evenements CONSTANT)
    Q_PROPERTY(QString projet READ projet NOTIFY change)
    Q_PROPERTY(QString erreur READ erreur NOTIFY change)
    Q_PROPERTY(bool lue READ lue NOTIFY change)
    Q_PROPERTY(bool chargement READ chargement NOTIFY change)
    Q_PROPERTY(bool historiqueBorne READ historiqueBorne NOTIFY change)
    Q_PROPERTY(qint64 curseur READ curseur NOTIFY change)
public:
    JournalExecutionViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent = nullptr);
    ~JournalExecutionViewModel() override;
    JsonListModel *evenements() { return &m_evenements; }
    QString projet() const { return m_projet; }
    QString erreur() const { return m_erreur; }
    bool lue() const { return m_lue; }
    bool chargement() const { return !m_appel.isNull(); }
    bool historiqueBorne() const { return m_historiqueBorne; }
    qint64 curseur() const { return m_curseur; }
    void setIntervalleTest(int ms) { m_intervalle = ms; }
    Q_INVOKABLE void choisirProjet(const QString &projet);
    Q_INVOKABLE void actualiser();
signals:
    void change();
protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;
private:
    void abandonnerLecture();
    bool lire(const QJsonObject &document, bool *encore);
    ClientGreffonPoste *m_greffon;
    QTimer *m_timer;
    QPointer<ApiCall> m_appel;
    JsonListModel m_evenements;
    QSet<QString> m_ids;
    QString m_projet, m_erreur;
    qint64 m_curseur = 0;
    quint64 m_generation = 0;
    bool m_lue = false, m_historiqueBorne = false;
    int m_intervalle = 2500;
};
}
