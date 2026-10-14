// Comptes des moteurs distants : aucun binaire ni jeton fournisseur sur le client.
#pragma once
#include "viewmodels/PageViewModel.h"
#include <QJsonObject>
#include <QPointer>
#include <QUrl>
#include <QVariantList>
#include <functional>
class QTimer;
namespace acp {
class ApiCall;
class ClientGreffonPoste;
class ComptesViewModel : public PageViewModel {
    Q_OBJECT
    Q_PROPERTY(QVariantList comptes READ comptes NOTIFY change)
    Q_PROPERTY(QVariantMap serveur READ serveur NOTIFY change)
    Q_PROPERTY(QVariantMap connexion READ connexion NOTIFY change)
    Q_PROPERTY(QString erreur READ erreur NOTIFY change)
    Q_PROPERTY(bool lue READ lue NOTIFY change)
    Q_PROPERTY(bool chargement READ chargement NOTIFY change)
    Q_PROPERTY(bool attente READ attente NOTIFY change)
    Q_PROPERTY(bool peutConnecter READ peutConnecter NOTIFY change)
    Q_PROPERTY(bool peutConnecterClaude READ peutConnecterClaude NOTIFY change)
    Q_PROPERTY(bool peutSaisirCode READ peutSaisirCode NOTIFY change)
    Q_PROPERTY(bool peutOuvrirVerification READ peutOuvrirVerification NOTIFY change)
public:
    ComptesViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent = nullptr);
    ~ComptesViewModel() override;
    QVariantList comptes() const { return m_comptes; }
    QVariantMap serveur() const { return m_serveur; }
    QVariantMap connexion() const { return m_connexion.toVariantMap(); }
    QString erreur() const { return m_erreur; }
    bool lue() const { return m_lue; }
    bool chargement() const { return !m_appel.isNull(); }
    bool attente() const;
    bool peutConnecter() const;
    bool peutConnecterClaude() const;
    bool peutSaisirCode() const;
    bool peutOuvrirVerification() const;
    void setOuvreur(std::function<bool(const QUrl &)> ouvreur) { m_ouvreur = std::move(ouvreur); }
    void setIntervalleTest(int ms) { m_intervalleTest = ms; }
    Q_INVOKABLE void actualiser();
    Q_INVOKABLE void connecterCodex();
    Q_INVOKABLE void connecterClaude();
    Q_INVOKABLE void soumettreCode(const QString &code);
    Q_INVOKABLE void annulerConnexion();
    Q_INVOKABLE bool ouvrirVerification();
    static bool urlVerificationAdmise(const QUrl &url, const QString &moteur = QStringLiteral("codex"));
    static bool identifiantConnexionValide(const QString &id);
    static QString libelleEtat(const QString &etat);
signals:
    void change();
    void effacerCodeTemporaire();
protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;
private:
    bool lireComptes(const QJsonObject &document);
    bool lireConnexion(const QJsonObject &document, const QString &identifiantAttendu = {});
    bool peutConnecterMoteur(const QString &moteur) const;
    void programmer();
    void abandonnerLecture();
    void geste(bool annulation, const QString &moteur = {});
    ClientGreffonPoste *m_greffon;
    QTimer *m_timer;
    QPointer<ApiCall> m_appel;
    QPointer<ApiCall> m_mutation;
    quint64 m_generation = 0;
    QVariantList m_comptes;
    QVariantMap m_serveur;
    QJsonObject m_connexion;
    QString m_erreur;
    QString m_cle;
    QString m_moteurCle;
    // Aucun code dans le ViewModel : seuls les identifiants permettent de relire le reçu.
    QString m_defiSoumission;
    QString m_soumission;
    QUrl m_verificationUrl;
    bool m_lue = false;
    int m_intervalleTest = 0;
    std::function<bool(const QUrl &)> m_ouvreur;
};
}
