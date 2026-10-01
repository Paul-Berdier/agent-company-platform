#include "gateway/JsonRpcChannel.h"

#include "diagnostics/Redaction.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QLoggingCategory>
#include <QTimer>

namespace acp {

namespace {

Q_LOGGING_CATEGORY(lcRpc, "acp.passerelle")

//! Pings sans réponse gardés au plus (en « toute trame entrante », un serveur qui diffuse
//! sans jamais répondre aux pings ne doit pas faire grossir l'ensemble).
constexpr int kPingsEnVolMax = 8;

} // namespace

// --- AppelRpc --------------------------------------------------------------------

AppelRpc::AppelRpc(QString identifiant, QString methode, QObject *parent)
    : QObject(parent)
    , m_identifiant(std::move(identifiant))
    , m_methode(std::move(methode))
{
}

// --- JsonRpcChannel ----------------------------------------------------------------

JsonRpcChannel::JsonRpcChannel(QObject *parent)
    : QObject(parent)
    , m_battement(new QTimer(this))
{
    connect(m_battement, &QTimer::timeout, this, &JsonRpcChannel::tic);
}

JsonRpcChannel::~JsonRpcChannel()
{
    m_transport = nullptr;
    m_battement->stop();
}

void JsonRpcChannel::setBattement(std::chrono::milliseconds intervalle, std::chrono::milliseconds echeance)
{
    m_intervalleBattement = intervalle;
    m_echeanceBattement = echeance;
}

void JsonRpcChannel::attacher(Transport transport)
{
    arreterBattement();
    m_transport = std::move(transport);
    m_derniereTrame.start();
}

void JsonRpcChannel::detacher(const QString &raison)
{
    arreterBattement();
    m_transport = nullptr;
    // Les requêtes serveur ouvertes appartenaient à cette connexion : Hermes les reproposera
    // par `open_requests` à la reprise, s'il les attend encore.
    m_ouvertes.clear();
    const auto enAttente = m_enAttente;
    m_enAttente.clear();
    for (QTimer *delai : std::as_const(m_delais)) {
        delai->stop();
        delai->deleteLater();
    }
    m_delais.clear();
    const ErreurRpc perdue{0, QStringLiteral("Connexion perdue : %1").arg(raison), {}, true};
    for (const QPointer<AppelRpc> &appel : enAttente) {
        if (appel) {
            terminer(appel, nullptr, &perdue);
        }
    }
}

AppelRpc *JsonRpcChannel::requete(const QString &methode, const QJsonObject &params,
                                  std::chrono::milliseconds delai)
{
    const QString identifiant = QStringLiteral("d%1").arg(++m_compteur);
    auto *appel = new AppelRpc(identifiant, methode, this);
    if (!m_transport) {
        QTimer::singleShot(0, appel, [this, appel] {
            const ErreurRpc erreur{0, QStringLiteral("Passerelle de Hermes non connectée."), {}, true};
            terminer(appel, nullptr, &erreur);
        });
        return appel;
    }
    m_enAttente.insert(identifiant, appel);
    const auto echeance = delai.count() > 0 ? delai : m_delaiRequete;
    auto *minuteur = new QTimer(this);
    minuteur->setSingleShot(true);
    connect(minuteur, &QTimer::timeout, this, [this, identifiant, methode] {
        QTimer *fini = m_delais.take(identifiant);
        if (fini) {
            fini->deleteLater();
        }
        const QPointer<AppelRpc> appel = m_enAttente.take(identifiant);
        if (appel) {
            const ErreurRpc erreur{0, QStringLiteral("Hermes n'a pas répondu à %1.").arg(methode), {}, true};
            terminer(appel, nullptr, &erreur);
        }
    });
    m_delais.insert(identifiant, minuteur);
    minuteur->start(echeance);
    envoyerTrame(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                             {QStringLiteral("id"), identifiant},
                             {QStringLiteral("method"), methode},
                             {QStringLiteral("params"), params}});
    return appel;
}

void JsonRpcChannel::envoyerTrame(const QJsonObject &trame)
{
    if (!m_transport) {
        return;
    }
    if (!m_transport(QJsonDocument(trame).toJson(QJsonDocument::Compact))) {
        qCWarning(lcRpc) << "trame refusée par le transport de la passerelle";
    }
}

void JsonRpcChannel::terminer(AppelRpc *appel, const QJsonValue *resultat, const ErreurRpc *erreur)
{
    if (!appel || appel->m_termine) {
        return;
    }
    appel->m_termine = true;
    if (resultat) {
        emit appel->reussi(*resultat);
    } else if (erreur) {
        emit appel->echoue(*erreur);
    }
    appel->deleteLater();
}

void JsonRpcChannel::definirGestionnaire(const QString &methode, Gestionnaire gestionnaire)
{
    m_gestionnaires.insert(methode, std::move(gestionnaire));
}

bool JsonRpcChannel::requeteOuverte(const QString &identifiant) const
{
    return m_ouvertes.contains(identifiant);
}

bool JsonRpcChannel::repondre(const QString &identifiant, const QJsonObject &resultat)
{
    if (!m_ouvertes.remove(identifiant)) {
        return false; // déjà répondue, retirée par Hermes, ou d'une connexion perdue
    }
    envoyerTrame(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                             {QStringLiteral("id"), identifiant},
                             {QStringLiteral("result"), resultat}});
    return true;
}

bool JsonRpcChannel::refuser(const QString &identifiant, int code, const QString &message)
{
    if (!m_ouvertes.remove(identifiant)) {
        return false;
    }
    envoyerTrame(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                             {QStringLiteral("id"), identifiant},
                             {QStringLiteral("error"), QJsonObject{{QStringLiteral("code"), code},
                                                                   {QStringLiteral("message"), message}}}});
    return true;
}

void JsonRpcChannel::remettre(const RequeteServeur &requete)
{
    m_ouvertes.insert(requete.identifiant);
    const auto gestionnaire = m_gestionnaires.constFind(requete.methode);
    if (gestionnaire == m_gestionnaires.constEnd() || !*gestionnaire) {
        // Aucun gestionnaire : refus immédiat, pour que l'agent n'attende pas son échéance.
        ++m_methodesRefusees;
        refuser(requete.identifiant, kMethodeIntrouvable,
                QStringLiteral("Méthode non prise en charge par la station : %1").arg(requete.methode));
        emit requeteNonPriseEnCharge(requete.methode);
        return;
    }
    (*gestionnaire)(requete);
}

void JsonRpcChannel::recevoir(const QByteArray &texte)
{
    // Toute trame entrante, même illisible, prouve que le lien vit.
    m_derniereTrame.start();
    const QList<QByteArray> lignes = texte.contains('\n') ? texte.split('\n') : QList<QByteArray>{texte};
    for (const QByteArray &ligne : lignes) {
        if (ligne.trimmed().isEmpty()) {
            continue;
        }
        QJsonParseError erreur{};
        const QJsonDocument document = QJsonDocument::fromJson(ligne, &erreur);
        if (erreur.error != QJsonParseError::NoError || !document.isObject()) {
            ++m_tramesIllisibles;
            qCWarning(lcRpc).noquote() << "trame illisible ignorée :"
                                       << redactSecrets(QString::fromUtf8(ligne.left(200)));
            continue;
        }
        traiterObjet(document.object());
    }
}

void JsonRpcChannel::traiterObjet(const QJsonObject &trame)
{
    const QJsonValue identifiant = trame.value(QStringLiteral("id"));
    const QJsonValue methode = trame.value(QStringLiteral("method"));

    // Requête du serveur vers la station.
    if (identifiant.isString() && methode.isString() && methode.toString() != QLatin1String("event")) {
        remettre(RequeteServeur{identifiant.toString(), methode.toString(),
                                trame.value(QStringLiteral("params")).toObject(), false});
        return;
    }
    // Réponse à une requête de la station.
    if (!identifiant.isUndefined() && !identifiant.isNull()) {
        traiterReponse(trame);
        return;
    }
    // Notification.
    if (methode.toString() == QLatin1String("event")) {
        const QJsonObject params = trame.value(QStringLiteral("params")).toObject();
        const QString type = params.value(QStringLiteral("type")).toString();
        if (type.isEmpty()) {
            ++m_tramesIllisibles;
            return;
        }
        if (type == QLatin1String("gateway.ready")) {
            annoncerCapacites();
            if (params.value(QStringLiteral("payload")).toObject().value(QStringLiteral("heartbeat")).toBool()) {
                demarrerBattement();
            }
        }
        const QJsonValue seq = params.value(QStringLiteral("seq"));
        emit evenement(type, params.value(QStringLiteral("session_id")).toString(),
                       seq.isDouble() ? static_cast<qint64>(seq.toDouble()) : -1,
                       params.value(QStringLiteral("payload")), params);
        return;
    }
    ++m_tramesIllisibles;
}

void JsonRpcChannel::traiterReponse(const QJsonObject &trame)
{
    const QJsonValue brut = trame.value(QStringLiteral("id"));
    const QString identifiant = brut.isString() ? brut.toString()
                                                : QString::number(static_cast<qint64>(brut.toDouble()));
    if (m_pingsEnVol.removeOne(identifiant)) {
        return;
    }
    QTimer *delai = m_delais.take(identifiant);
    if (delai) {
        delai->stop();
        delai->deleteLater();
    }
    const QPointer<AppelRpc> appel = m_enAttente.take(identifiant);
    if (!appel) {
        ++m_reponsesInconnues;
        return;
    }
    if (trame.contains(QStringLiteral("error"))) {
        const QJsonObject contenu = trame.value(QStringLiteral("error")).toObject();
        const ErreurRpc erreur{contenu.value(QStringLiteral("code")).toInt(),
                               contenu.value(QStringLiteral("message")).toString(),
                               contenu.value(QStringLiteral("data")), false};
        terminer(appel, nullptr, &erreur);
        return;
    }
    const QJsonValue resultat = trame.value(QStringLiteral("result"));
    // Contrat de reprise : `open_requests` est remis AVANT que l'appelant ne voie le résultat.
    redistribuerOuvertes(resultat);
    terminer(appel, &resultat, nullptr);
}

void JsonRpcChannel::redistribuerOuvertes(const QJsonValue &resultat)
{
    const QJsonArray ouvertes = resultat.toObject().value(QStringLiteral("open_requests")).toArray();
    for (const QJsonValue &entree : ouvertes) {
        const QJsonObject requete = entree.toObject();
        const QJsonValue identifiant = requete.value(QStringLiteral("id"));
        const QJsonValue methode = requete.value(QStringLiteral("method"));
        if (identifiant.isString() && methode.isString()) {
            remettre(RequeteServeur{identifiant.toString(), methode.toString(),
                                    requete.value(QStringLiteral("params")).toObject(), true});
        }
    }
}

void JsonRpcChannel::annoncerCapacites()
{
    // La station répond aux requêtes serveur (gestionnaire ou -32601) : sans cette annonce,
    // Hermes ferait attendre l'agent jusqu'à son échéance (server_requests.py).
    AppelRpc *appel = requete(QStringLiteral("client.capabilities"),
                              QJsonObject{{QStringLiteral("server_requests"), true}});
    Q_UNUSED(appel)
}

void JsonRpcChannel::demarrerBattement()
{
    arreterBattement();
    if (!m_transport || m_intervalleBattement.count() <= 0 || m_echeanceBattement.count() <= 0) {
        return;
    }
    m_derniereTrame.start();
    m_battement->start(m_intervalleBattement);
}

void JsonRpcChannel::arreterBattement()
{
    m_pingsEnVol.clear();
    m_battement->stop();
}

bool JsonRpcChannel::battementActif() const
{
    return m_battement->isActive();
}

void JsonRpcChannel::tic()
{
    if (!m_transport) {
        arreterBattement();
        return;
    }
    if (m_derniereTrame.isValid() && m_derniereTrame.elapsed() >= m_echeanceBattement.count()) {
        arreterBattement();
        emit battementEchoue(QStringLiteral("aucune trame reçue de Hermes depuis %1 s")
                                 .arg(m_echeanceBattement.count() / 1000.0, 0, 'f', 1));
        return;
    }
    const QString identifiant = QStringLiteral("battement-%1").arg(++m_compteurBattement);
    m_pingsEnVol.append(identifiant);
    if (m_pingsEnVol.size() > kPingsEnVolMax) {
        m_pingsEnVol.removeFirst(); // le plus ancien, jamais le dernier émis
    }
    envoyerTrame(QJsonObject{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")},
                             {QStringLiteral("id"), identifiant},
                             {QStringLiteral("method"), QStringLiteral("gateway.ping")},
                             {QStringLiteral("params"), QJsonObject{}}});
}

} // namespace acp
