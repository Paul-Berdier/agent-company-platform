// Discussions en attente (cahier P7 § 3.5) : cinquième section de la file Questions, lue par le
// JSON-RPC du tableau de bord (`session.active_list`), en LECTURE SEULE, comme la page web
// (apps/interface/src/jsonrpc/discussions.ts) :
//  - seules les entrées `status == "waiting"` (une requête au client encore ouverte : clarify,
//    approval, sudo, secret ; Hermes ne dit pas laquelle) sont gardées ; une entrée illisible
//    (sans `session_key`) est écartée, jamais complétée ;
//  - échec, refus, délai ou passerelle indisponible : « inconnu », jamais zéro ; les totaux le
//    disent (« discussions non comptées »).
// La station emploie SA passerelle (GatewayClient, déjà ouverte en session) : la seule méthode
// émise ici est `session.active_list`, sans rattacher ni activer aucune session.
//
// Une seule lecture à la fois : une demande pendant une lecture en vol est servie une fois à sa
// fin. Le sondage léger (badge), l'Accueil et la page Questions la demandent après chacune de
// leurs lectures ; le sujet `discussions` du flux d'invalidation les fait relire.

#pragma once

#include <QJsonArray>
#include <QJsonValue>
#include <QObject>
#include <QPointer>
#include <QString>

#include <chrono>
#include <optional>

namespace acp {

class AppelRpc;
class GatewayClient;

class DiscussionsEnAttente : public QObject
{
    Q_OBJECT

public:
    static constexpr char kMethode[] = "session.active_list";
    static constexpr std::chrono::milliseconds kDelai{5000};

    explicit DiscussionsEnAttente(GatewayClient *passerelle, QObject *parent = nullptr);
    ~DiscussionsEnAttente() override;

    /*!
        Entrées « waiting » d'une réponse de `session.active_list`, chacune
        `{cle, titre, apercu, derniereActivite}` (secondes depuis l'époque ou null) ; `nullopt` si la
        réponse est illisible (pas de tableau `sessions`).
    */
    [[nodiscard]] static std::optional<QJsonArray> sessionsEnAttente(const QJsonValue &resultat);

    /*! Lit (ou relira une fois à la fin de la lecture en vol). */
    void lire();
    /*! Session perdue, serveur changé : « inconnu », lecture en vol abandonnée. */
    void oublier();

    [[nodiscard]] bool connues() const { return m_connues; }
    /*! Nombre de discussions en attente, ou -1 si inconnu. */
    [[nodiscard]] int nombre() const { return m_connues ? static_cast<int>(m_sessions.size()) : -1; }
    [[nodiscard]] const QJsonArray &sessions() const { return m_sessions; }
    /*! Pourquoi c'est inconnu (« passerelle indisponible », refus de Hermes…), vide sinon. */
    [[nodiscard]] const QString &raison() const { return m_raison; }
    /*! Une lecture a abouti ou échoué depuis la création ou le dernier oubli (sinon : « pas encore lues »). */
    [[nodiscard]] bool tentee() const { return m_tentee; }

signals:
    void change();

private:
    void publier(bool connues, const QJsonArray &sessions, const QString &raison);

    QPointer<GatewayClient> m_passerelle;
    QPointer<AppelRpc> m_appel;
    bool m_relire = false;
    bool m_connues = false;
    bool m_tentee = false;
    QJsonArray m_sessions;
    QString m_raison;
};

} // namespace acp
