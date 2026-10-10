#include "gateway/DiscussionsEnAttente.h"

#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"

#include <QJsonObject>
#include <QTimer>

#include <cmath>

namespace acp {

namespace {

constexpr qsizetype kApercuMax = 160;

//! Texte non vide, tronqué ; null sinon (jamais complété).
QJsonValue chaine(const QJsonValue &valeur, qsizetype max = 200)
{
    const QString texte = valeur.toString().trimmed();
    return valeur.isString() && !texte.isEmpty() ? QJsonValue(texte.left(max)) : QJsonValue(QJsonValue::Null);
}

} // namespace

DiscussionsEnAttente::DiscussionsEnAttente(GatewayClient *passerelle, QObject *parent)
    : QObject(parent)
    , m_passerelle(passerelle)
{
    m_raison = QStringLiteral("pas encore lues");
}

DiscussionsEnAttente::~DiscussionsEnAttente()
{
    if (m_appel) {
        m_appel->disconnect(this);
    }
}

std::optional<QJsonArray> DiscussionsEnAttente::sessionsEnAttente(const QJsonValue &resultat)
{
    const QJsonValue sessions = resultat.toObject().value(QStringLiteral("sessions"));
    if (!sessions.isArray()) {
        return std::nullopt;
    }
    QJsonArray garde;
    for (const QJsonValue &brut : sessions.toArray()) {
        const QJsonObject s = brut.toObject();
        const QJsonValue cle = chaine(s.value(QStringLiteral("session_key")));
        if (s.value(QStringLiteral("status")).toString() != QLatin1String("waiting") || cle.isNull()) {
            continue;
        }
        const QJsonValue activite = s.value(QStringLiteral("last_active"));
        garde.append(QJsonObject{
            {QStringLiteral("cle"), cle},
            {QStringLiteral("titre"), chaine(s.value(QStringLiteral("title")))},
            {QStringLiteral("apercu"), chaine(s.value(QStringLiteral("preview")), kApercuMax)},
            {QStringLiteral("derniereActivite"),
             activite.isDouble() && std::isfinite(activite.toDouble()) ? activite : QJsonValue(QJsonValue::Null)},
        });
    }
    return garde;
}

void DiscussionsEnAttente::lire()
{
    if (m_appel) {
        m_relire = true;
        return;
    }
    m_relire = false;
    if (!m_passerelle || m_passerelle->etat() != GatewayClient::Etat::Pret) {
        m_tentee = true;
        publier(false, {}, m_passerelle
                               ? QStringLiteral("passerelle de Hermes indisponible (%1)").arg(m_passerelle->libelleEtat())
                               : QStringLiteral("passerelle de Hermes absente"));
        return;
    }
    AppelRpc *appel = m_passerelle->canal()->requete(QString::fromLatin1(kMethode), {}, kDelai);
    m_appel = appel;
    connect(appel, &AppelRpc::reussi, this, [this, appel](const QJsonValue &resultat) {
        if (m_appel != appel) {
            return;
        }
        m_appel = nullptr;
        m_tentee = true;
        const std::optional<QJsonArray> sessions = sessionsEnAttente(resultat);
        if (sessions) {
            publier(true, *sessions, QString());
        } else {
            publier(false, {}, QStringLiteral("réponse illisible de « %1 »").arg(QString::fromLatin1(kMethode)));
        }
        if (m_relire) {
            QTimer::singleShot(0, this, &DiscussionsEnAttente::lire);
        }
    });
    connect(appel, &AppelRpc::echoue, this, [this, appel](const ErreurRpc &erreur) {
        if (m_appel != appel) {
            return;
        }
        m_appel = nullptr;
        m_tentee = true;
        publier(false, {}, erreur.locale ? erreur.message
                                         : QStringLiteral("Hermes a refusé « %1 » : %2 (code %3)")
                                               .arg(QString::fromLatin1(kMethode), erreur.message)
                                               .arg(erreur.code));
        if (m_relire) {
            QTimer::singleShot(0, this, &DiscussionsEnAttente::lire);
        }
    });
}

void DiscussionsEnAttente::oublier()
{
    if (m_appel) {
        m_appel->disconnect(this);
        m_appel = nullptr;
    }
    m_relire = false;
    m_tentee = false;
    publier(false, {}, QStringLiteral("pas encore lues"));
}

void DiscussionsEnAttente::publier(bool connues, const QJsonArray &sessions, const QString &raison)
{
    if (connues == m_connues && sessions == m_sessions && raison == m_raison) {
        return;
    }
    m_connues = connues;
    m_sessions = sessions;
    m_raison = raison;
    emit change();
}

} // namespace acp
