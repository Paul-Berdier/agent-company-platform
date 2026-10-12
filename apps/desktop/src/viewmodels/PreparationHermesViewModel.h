// Préparation du coordinateur Hermes et connexion OAuth du propriétaire.
// Hermes 0.21.5, f97608f : web_routers/oauth.py (471-492, 720-795),
// web_server.py (431-445), dashboard_auth/middleware.py (porteur natif).
// Seuls le défi et l'identifiant de flux vivent en mémoire ; aucun jeton fournisseur
// n'est reçu. setup.runtime_check vérifie la résolution, pas un appel d'inférence.
#pragma once

#include <QDateTime>
#include <QElapsedTimer>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QUrl>

#include <chrono>
#include <functional>
#include <utility>

class QTimer;

namespace acp {
class ApiCall;
class ApiClient;
class GatewayClient;

class PreparationHermesViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString etat READ etat NOTIFY change)
    Q_PROPERTY(QString libelle READ libelle NOTIFY change)
    Q_PROPERTY(QString detail READ detail NOTIFY change)
    Q_PROPERTY(QString prochaineAction READ prochaineAction NOTIFY change)
    Q_PROPERTY(QString fournisseur READ fournisseur NOTIFY change)
    Q_PROPERTY(QString modele READ modele NOTIFY change)
    Q_PROPERTY(QString lecture READ lecture NOTIFY change)
    Q_PROPERTY(bool occupe READ occupe NOTIFY change)
    Q_PROPERTY(bool peutVerifier READ peutVerifier NOTIFY change)
    Q_PROPERTY(bool peutConnecter READ peutConnecter NOTIFY change)
    Q_PROPERTY(bool defiActif READ defiActif NOTIFY change)
    Q_PROPERTY(QString codeAppareil READ codeAppareil NOTIFY change)
    Q_PROPERTY(int secondesRestantes READ secondesRestantes NOTIFY change)

public:
    using Ouvreur = std::function<bool(const QUrl &)>;
    PreparationHermesViewModel(ApiClient *client, GatewayClient *passerelle, QObject *parent = nullptr);
    ~PreparationHermesViewModel() override;

    // À relier respectivement à SessionHermes::sessionEtablie / sessionPerdue.
    void activer();
    void oublier();

    [[nodiscard]] QString etat() const { return m_etat; }
    [[nodiscard]] QString libelle() const;
    [[nodiscard]] QString detail() const { return m_detail; }
    [[nodiscard]] QString prochaineAction() const;
    [[nodiscard]] QString fournisseur() const { return m_fournisseur; }
    [[nodiscard]] QString modele() const { return m_modele; }
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] bool occupe() const;
    [[nodiscard]] bool peutVerifier() const;
    [[nodiscard]] bool peutConnecter() const;
    [[nodiscard]] bool defiActif() const;
    [[nodiscard]] QString codeAppareil() const { return m_code; }
    [[nodiscard]] int secondesRestantes() const;

    Q_INVOKABLE void verifier();
    Q_INVOKABLE void connecter();
    Q_INVOKABLE void annuler();
    Q_INVOKABLE bool ouvrirVerification();
    Q_INVOKABLE bool copierCode();
    Q_INVOKABLE bool ouvrirTableauDeBord();

    // Injection du navigateur et délais courts, uniquement pour les tests.
    void setOuvreur(Ouvreur ouvreur) { m_ouvreur = std::move(ouvreur); }
    void setDelaisTest(std::chrono::milliseconds suivi, std::chrono::milliseconds duree);

signals:
    void change();

private:
    void poser(const QString &etat, const QString &detail);
    void lireResolution(quint64 generation, bool fournisseurConfigure);
    void suivre();
    void arreterFlux(const QString &etatFinal, const QString &detailFinal);
    void effacerDefi();
    void interrompreAppel();
    [[nodiscard]] bool passerellePrete() const;
    [[nodiscard]] QString texteSur(const QString &texte) const;

    ApiClient *m_client;
    GatewayClient *m_passerelle;
    Ouvreur m_ouvreur;
    QTimer *m_suivi;
    QTimer *m_decompte;
    QPointer<ApiCall> m_appel;
    quint64 m_generation = 0;
    bool m_active = false;
    QUrl m_serveur;
    bool m_annulationDemandee = false;
    bool m_autorisationRecue = false;
    QString m_etat = QStringLiteral("inconnu");
    QString m_detail;
    QString m_fournisseur;
    QString m_modele;
    QDateTime m_luA;
    QString m_sessionId;
    QString m_code;
    QUrl m_url;
    QElapsedTimer m_attente;
    qint64 m_dureeMs = 0;
    int m_intervalleMs = 5000;
    int m_intervalleTest = 0;
    qint64 m_dureeTest = 0;
};
} // namespace acp