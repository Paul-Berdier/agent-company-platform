// Quotas réels d'abonnement (Codex CLI par compte ChatGPT, Claude Code), lus par
// GET /subscription-quotas.
//
// Ce que cet écran garantit, et pourquoi :
//
//  - AUCUNE estimation. Chaque valeur affichée vient telle quelle du dernier relevé
//    transmis par un worker à l'API ; le seul calcul est le « reste » servi par l'API
//    elle-même (100 − part utilisée), que le client vérifie sans le recalculer. Une
//    valeur nulle s'affiche « Inconnu ».
//  - Échec fermé. La réponse est validée champ par champ : un champ inattendu, absent
//    ou mal typé fait refuser TOUTE la réponse avec la raison en français, et les
//    valeurs précédentes disparaissent au lieu de rester affichées comme actuelles.
//  - Réservé au propriétaire. L'usage d'un abonnement est personnel à son titulaire :
//    une session d'un autre rôle ne demande rien au serveur, et un 403 du serveur est
//    présenté comme tel, sans relecture en boucle.
//  - Aucun secret. La route ne transporte ni identifiant de compte ni jeton ; le client
//    ne lit que l'API, jamais le poste du worker, un fichier local ou la base.

#pragma once

#include "api/ApiRequest.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QObject>
#include <QPointer>
#include <QTimeZone>
#include <QTimer>

#include <chrono>
#include <functional>

namespace acp {
class ApiCall;
class ApiClient;
class ApiError;
class AuthManager;
class JsonListModel;

class SubscriptionQuotasViewModel final : public QObject
{
    Q_OBJECT
    //! Vrai tant que l'écran des quotas est affiché : il porte le chargement et
    //! l'actualisation automatique.
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY changed)
    //! « idle », « signedOut », « loading », « ready », « empty », « error »,
    //! « forbidden », « offline » ou « unsupported ».
    Q_PROPERTY(QString state READ state NOTIFY changed)
    Q_PROPERTY(QString stateLabel READ stateLabel NOTIFY changed)
    Q_PROPERTY(QString stateStatusKey READ stateStatusKey NOTIFY changed)
    Q_PROPERTY(QString message READ message NOTIFY changed)
    Q_PROPERTY(bool loading READ loading NOTIFY changed)
    Q_PROPERTY(bool canRefresh READ canRefresh NOTIFY changed)
    Q_PROPERTY(QObject *reports READ reports CONSTANT)
    Q_PROPERTY(QString servedLabel READ servedLabel NOTIFY changed)
    Q_PROPERTY(QString staleAfterLabel READ staleAfterLabel NOTIFY changed)
    Q_PROPERTY(int refreshIntervalSeconds READ refreshIntervalSeconds CONSTANT)

public:
    SubscriptionQuotasViewModel(ApiClient *client, AuthManager *auth, QObject *parent = nullptr);
    ~SubscriptionQuotasViewModel() override;

    [[nodiscard]] bool active() const { return m_active; }
    void setActive(bool value);
    [[nodiscard]] QString state() const { return m_state; }
    [[nodiscard]] QString stateLabel() const;
    [[nodiscard]] QString stateStatusKey() const;
    [[nodiscard]] QString message() const { return m_message; }
    [[nodiscard]] bool loading() const { return !m_call.isNull(); }
    [[nodiscard]] bool canRefresh() const;
    [[nodiscard]] QObject *reports() const;
    [[nodiscard]] QString servedLabel() const { return m_servedLabel; }
    [[nodiscard]] QString staleAfterLabel() const { return m_staleAfterLabel; }
    //! Période d'actualisation automatique annoncée à l'écran, en secondes.
    [[nodiscard]] static int refreshIntervalSeconds() { return 60; }

    /*! Relit GET /subscription-quotas. Sans effet hors de l'écran, pendant un appel en
        vol, ou pour une session qui n'est pas celle du propriétaire. */
    Q_INVOKABLE void refresh();

    // --- Points d'injection des tests ------------------------------------------
    //! Horloge utilisée pour « il y a », « dans » et « aujourd'hui ».
    void setClockForTesting(std::function<QDateTime()> clock);
    //! Fuseau d'affichage des heures locales ; par défaut, celui du système.
    void setTimeZoneForTesting(const QTimeZone &zone);
    //! Période de l'actualisation automatique ; 60 s en production.
    void setRefreshIntervalForTesting(std::chrono::milliseconds interval);

signals:
    void changed();

private:
    void updateSession();
    void invalidate();
    void setState(const QString &next, const QString &message = {});
    void applyDocument(const QJsonDocument &document);
    void applyFailure(const ApiError &error);
    void updateTimer();
    [[nodiscard]] bool sessionReady() const;
    [[nodiscard]] bool isOwner() const;
    [[nodiscard]] QString identity() const;
    [[nodiscard]] QDateTime now() const;

    ApiClient *m_client;
    AuthManager *m_auth;
    JsonListModel *m_reports;
    QTimer m_timer;
    QPointer<ApiCall> m_call;
    std::function<QDateTime()> m_clock;
    QTimeZone m_zone;
    QString m_identity;
    QString m_state = QStringLiteral("idle");
    QString m_message;
    QString m_servedLabel;
    QString m_staleAfterLabel;
    quint64 m_generation = 0;
    bool m_active = false;
};

} // namespace acp
