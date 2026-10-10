// Veille du kanban du projet affiché : un SIGNAL D'INVALIDATION, jamais interprété
// (cahier P8 § 6.2).
//
// Hermes 0.21.5 (plugins/kanban/dashboard/plugin_api.py) :
//   - `GET /api/plugins/kanban/board?board=<tableau>` rend `latest_event_id` ;
//   - le WebSocket `/api/plugins/kanban/events?since=<id>&board=<tableau>` pousse des lots
//     `{events, cursor}` (sondage de la base toutes les 300 ms) ;
//   - sa garde est celle de `/api/ws` (`web_server_chat._ws_auth_ok`) : ticket à usage unique
//     de 30 s, présenté en sous-protocole avec `hermes-gateway-v1` (jamais dans l'URL ni un
//     journal) ; la route accepte SANS choisir de sous-protocole (`ws.accept()` nu).
//
// La station n'emploie que le fait « quelque chose a changé » : un lot qui avance le curseur
// relance une minuterie de regroupement (1 s) ; à son échéance, `changement` est émis UNE fois.
// Le contenu des événements, surface interne de Hermes, n'est jamais lu.
//
// Un seul tableau à la fois. Coupure : nouveau ticket, reprise à `since=<dernier curseur>`,
// avec recul (1 s à 30 s, gigue). Poignée de main refusée deux fois de suite : « Refusée ».

#pragma once

#include "events/Backoff.h"

#include <QDateTime>
#include <QObject>
#include <QPointer>
#include <QString>

#include <chrono>

class QTimer;
class QWebSocket;

namespace acp {

class ApiCall;
class ApiClient;

class VeilleKanban : public QObject
{
    Q_OBJECT

public:
    enum class Etat {
        Arretee,
        Preparation, //!< Lecture du tableau, ticket, poignée de main.
        Prete,
        Reconnexion,
        Refusee,
    };
    Q_ENUM(Etat)

    static constexpr char kCheminTableau[] = "/api/plugins/kanban/board";
    static constexpr char kCheminEvenements[] = "/api/plugins/kanban/events";

    explicit VeilleKanban(ApiClient *client, QObject *parent = nullptr);
    ~VeilleKanban() override;

    // --- Réglages (tests) -----------------------------------------------------------
    void setRegroupement(std::chrono::milliseconds delai) { m_regroupement = delai; }
    void setRecul(const Backoff &recul) { m_recul = recul; }

    /*! Surveille ce tableau (et lui seul). Sans effet s'il est déjà surveillé. */
    void surveiller(const QString &tableau);
    /*! Ferme la veille ; plus aucun signal ensuite. */
    void arreter();

    [[nodiscard]] const QString &tableau() const { return m_tableau; }
    [[nodiscard]] Etat etat() const { return m_etat; }
    [[nodiscard]] QString libelleEtat() const;
    [[nodiscard]] const QString &raison() const { return m_raison; }
    [[nodiscard]] qint64 curseur() const { return m_curseur; }
    [[nodiscard]] int reconnexions() const { return m_reconnexions; }
    [[nodiscard]] int lots() const { return m_lots; }
    [[nodiscard]] const QDateTime &dernierSigneDeVie() const { return m_dernierSigne; }

signals:
    /*! Le tableau a bougé : relire la vérité par les routes du greffon. */
    void changement(const QString &tableau);
    void etatChange();

private:
    void lireTableau();
    void demanderTicket();
    void ouvrir(QByteArray ticket);
    void surMessage(const QString &message);
    void surFermeture();
    void surErreur();
    void programmerReconnexion(const QString &raison);
    void refuser(const QString &raison);
    void fermerSocket();
    void changerEtat(Etat etat, const QString &raison = {});

    ApiClient *m_client = nullptr;
    QPointer<QWebSocket> m_socket;
    QPointer<ApiCall> m_appel;
    QTimer *m_minuterieRegroupement = nullptr;
    QTimer *m_relance = nullptr;
    Backoff m_recul{std::chrono::milliseconds(1000), std::chrono::milliseconds(30000), 25};
    std::chrono::milliseconds m_regroupement{1000};
    QString m_tableau;
    qint64 m_curseur = -1;
    Etat m_etat = Etat::Arretee;
    QString m_raison;
    int m_reconnexions = 0;
    int m_lots = 0;
    bool m_ticketReessaye = false;
    bool m_curseurConnu = false;
    quint64 m_generation = 0;
    QDateTime m_dernierSigne;
};

} // namespace acp
