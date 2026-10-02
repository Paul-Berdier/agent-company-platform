#include "gateway/DemandesAgent.h"

#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "models/JsonListModel.h"

#include <QJsonArray>
#include <QJsonDocument>

namespace acp {

namespace {

QString chaine(const QJsonValue &valeur)
{
    return valeur.isString() ? valeur.toString() : QString();
}

QJsonArray choixTexte(const QJsonValue &valeur)
{
    QJsonArray resultat;
    for (const QJsonValue &choix : valeur.toArray()) {
        if (choix.isString() && !choix.toString().trimmed().isEmpty()) {
            resultat.append(QJsonObject{{QStringLiteral("valeur"), choix.toString()},
                                        {QStringLiteral("libelle"), choix.toString()}});
        }
    }
    return resultat;
}

QStringList valeurs(const QJsonArray &choix)
{
    QStringList resultat;
    for (const QJsonValue &element : choix) {
        resultat.append(element.toObject().value(QStringLiteral("valeur")).toString());
    }
    return resultat;
}

} // namespace

DemandesAgent::DemandesAgent(GatewayClient *passerelle, QObject *parent)
    : QObject(parent)
    , m_passerelle(passerelle)
    , m_demandes(new JsonListModel(this))
{
    // Par identifiant : une nouvelle demande ne détruit pas le champ d'une autre carte.
    m_demandes->setCle({QStringLiteral("id")});
    JsonRpcChannel *canal = m_passerelle->canal();
    canal->definirGestionnaire(QStringLiteral("approval"), [this](const RequeteServeur &requete) { recevoir(requete); });
    canal->definirGestionnaire(QStringLiteral("clarify"), [this](const RequeteServeur &requete) { recevoir(requete); });
    connect(m_passerelle, &GatewayClient::evenement, this,
            [this](const QString &type, const QString &, qint64, const QJsonValue &payload) {
                if (type != QLatin1String("request.cancel")) {
                    return;
                }
                // Hermes a retiré la demande (délai, interruption, session fermée…) : la carte
                // disparaît, et la raison est dite.
                const QJsonObject retrait = payload.toObject();
                const QString identifiant = chaine(retrait.value(QStringLiteral("id")));
                if (trouver(identifiant).isEmpty()) {
                    return;
                }
                retirer(identifiant);
                const QString raison = chaine(retrait.value(QStringLiteral("reason")));
                dire(raison.isEmpty() ? QStringLiteral("Demande retirée par Hermes.")
                                      : QStringLiteral("Demande retirée par Hermes (%1).").arg(raison.left(80)),
                     QString());
            });
    connect(m_passerelle, &GatewayClient::etatChange, this, [this] {
        const GatewayClient::Etat etat = m_passerelle->etat();
        if (etat == GatewayClient::Etat::Pret || etat == GatewayClient::Etat::Rejeu) {
            return;
        }
        // Les demandes ouvertes appartenaient à la connexion perdue : Hermes reproposera, à la
        // reprise, celles qu'il attend encore.
        if (m_demandes->count() > 0) {
            m_demandes->clear();
            emit demandesChange();
        }
    });
}

DemandesAgent::~DemandesAgent() = default;

int DemandesAgent::nombre() const
{
    return m_demandes->count();
}

QString DemandesAgent::libelleChoix(const QString &choix)
{
    if (choix == QLatin1String("once")) return QStringLiteral("Autoriser une fois");
    if (choix == QLatin1String("session")) return QStringLiteral("Autoriser pour cette session");
    if (choix == QLatin1String("always")) return QStringLiteral("Toujours autoriser");
    if (choix == QLatin1String("deny")) return QStringLiteral("Refuser");
    return {};
}

QJsonObject DemandesAgent::construire(const RequeteServeur &requete)
{
    const QJsonObject &params = requete.params;
    QJsonObject ligne{
        {QStringLiteral("id"), requete.identifiant},
        {QStringLiteral("methode"), requete.methode},
        {QStringLiteral("sessionId"), chaine(params.value(QStringLiteral("session_id")))},
        {QStringLiteral("rejouee"), requete.rejouee},
    };
    if (requete.methode == QLatin1String("approval")) {
        QJsonArray choix;
        for (const QJsonValue &valeur : params.value(QStringLiteral("choices")).toArray()) {
            const QString libelle = libelleChoix(valeur.toString());
            if (!libelle.isEmpty()) {
                choix.append(QJsonObject{{QStringLiteral("valeur"), valeur.toString()}, {QStringLiteral("libelle"), libelle}});
            }
        }
        ligne.insert(QStringLiteral("titre"), QStringLiteral("Autorisation demandée par Hermes"));
        // La commande est expurgée par Hermes avant l'envoi (`_approval_request_payload`).
        ligne.insert(QStringLiteral("commande"), chaine(params.value(QStringLiteral("command"))));
        ligne.insert(QStringLiteral("description"), chaine(params.value(QStringLiteral("description"))));
        ligne.insert(QStringLiteral("outil"), chaine(params.value(QStringLiteral("tool_name"))));
        ligne.insert(QStringLiteral("choix"), choix);
        ligne.insert(QStringLiteral("sansChoix"), choix.isEmpty());
        ligne.insert(QStringLiteral("question"), QString());
        ligne.insert(QStringLiteral("multiple"), false);
        ligne.insert(QStringLiteral("estLot"), false);
        ligne.insert(QStringLiteral("lot"), QJsonArray{});
        return ligne;
    }
    // clarify : question simple, ou lot (`questions`), avec les réponses déjà verrouillées.
    const QJsonObject verrouillees = params.value(QStringLiteral("answers")).toObject();
    QJsonArray lot;
    for (const QJsonValue &element : params.value(QStringLiteral("questions")).toArray()) {
        const QJsonObject question = element.toObject();
        const QString qid = chaine(question.value(QStringLiteral("qid")));
        if (qid.isEmpty()) {
            continue;
        }
        const QJsonArray choix = choixTexte(question.value(QStringLiteral("choices")));
        lot.append(QJsonObject{{QStringLiteral("qid"), qid},
                               {QStringLiteral("question"), chaine(question.value(QStringLiteral("question")))},
                               {QStringLiteral("choix"), choix},
                               {QStringLiteral("multiple"), question.value(QStringLiteral("multi_select")) == QJsonValue(true)
                                                                && !choix.isEmpty()},
                               {QStringLiteral("verrouillee"), chaine(verrouillees.value(qid))}});
    }
    const QJsonArray choix = choixTexte(params.value(QStringLiteral("choices")));
    ligne.insert(QStringLiteral("titre"), lot.isEmpty() ? QStringLiteral("Question de Hermes") : QStringLiteral("Questions de Hermes"));
    ligne.insert(QStringLiteral("commande"), QString());
    ligne.insert(QStringLiteral("description"), QString());
    ligne.insert(QStringLiteral("outil"), QString());
    ligne.insert(QStringLiteral("question"), chaine(params.value(QStringLiteral("question"))));
    ligne.insert(QStringLiteral("choix"), choix);
    ligne.insert(QStringLiteral("sansChoix"), choix.isEmpty());
    ligne.insert(QStringLiteral("multiple"), params.value(QStringLiteral("multi_select")) == QJsonValue(true) && !choix.isEmpty());
    ligne.insert(QStringLiteral("estLot"), !lot.isEmpty());
    ligne.insert(QStringLiteral("lot"), lot);
    return ligne;
}

void DemandesAgent::recevoir(const RequeteServeur &requete)
{
    // Une demande reproposée à la reprise remplace la précédente de même identifiant.
    QJsonArray lignes;
    for (int index = 0; index < m_demandes->count(); ++index) {
        const QJsonObject ligne = m_demandes->itemAt(index);
        if (ligne.value(QStringLiteral("id")).toString() != requete.identifiant) {
            lignes.append(ligne);
        }
    }
    lignes.append(construire(requete));
    m_demandes->setItems(lignes);
    emit demandesChange();
}

QJsonObject DemandesAgent::trouver(const QString &identifiant) const
{
    for (int index = 0; index < m_demandes->count(); ++index) {
        const QJsonObject ligne = m_demandes->itemAt(index);
        if (ligne.value(QStringLiteral("id")).toString() == identifiant) {
            return ligne;
        }
    }
    return {};
}

void DemandesAgent::retirer(const QString &identifiant)
{
    QJsonArray lignes;
    for (int index = 0; index < m_demandes->count(); ++index) {
        const QJsonObject ligne = m_demandes->itemAt(index);
        if (ligne.value(QStringLiteral("id")).toString() != identifiant) {
            lignes.append(ligne);
        }
    }
    m_demandes->setItems(lignes);
    emit demandesChange();
}

void DemandesAgent::dire(const QString &message, const QString &erreur)
{
    m_message = message;
    m_erreur = erreur;
    emit messageChange();
}

bool DemandesAgent::envoyer(const QString &identifiant, const QJsonObject &resultat, const QString &message)
{
    if (!m_passerelle->canal()->repondre(identifiant, resultat)) {
        retirer(identifiant);
        dire(QString(), QStringLiteral("Cette demande n'est plus ouverte : déjà répondue, retirée par Hermes ou perdue "
                                       "avec la connexion."));
        return false;
    }
    retirer(identifiant);
    dire(message, QString());
    return true;
}

bool DemandesAgent::approuver(const QString &identifiant, const QString &choix)
{
    const QJsonObject demande = trouver(identifiant);
    if (demande.value(QStringLiteral("methode")).toString() != QLatin1String("approval")) {
        dire(QString(), QStringLiteral("Demande d'autorisation inconnue de la station."));
        return false;
    }
    if (!valeurs(demande.value(QStringLiteral("choix")).toArray()).contains(choix)) {
        dire(QString(), QStringLiteral("Ce choix n'est pas offert par Hermes pour cette demande."));
        return false;
    }
    return envoyer(identifiant, QJsonObject{{QStringLiteral("choice"), choix}},
                   QStringLiteral("Décision transmise à Hermes : %1.").arg(libelleChoix(choix).toLower()));
}

bool DemandesAgent::clarifier(const QString &identifiant, const QString &reponse)
{
    const QJsonObject demande = trouver(identifiant);
    if (demande.value(QStringLiteral("methode")).toString() != QLatin1String("clarify")
        || demande.value(QStringLiteral("estLot")).toBool()) {
        dire(QString(), QStringLiteral("Question inconnue de la station."));
        return false;
    }
    const QString texte = reponse.trimmed();
    return envoyer(identifiant, QJsonObject{{QStringLiteral("answer"), texte}},
                   texte.isEmpty() ? QStringLiteral("Question passée : Hermes continue sans réponse.")
                                   : QStringLiteral("Réponse transmise à Hermes."));
}

bool DemandesAgent::clarifierSelection(const QString &identifiant, const QStringList &selection)
{
    const QJsonObject demande = trouver(identifiant);
    if (demande.value(QStringLiteral("methode")).toString() != QLatin1String("clarify")
        || !demande.value(QStringLiteral("multiple")).toBool()) {
        dire(QString(), QStringLiteral("Question à choix multiples inconnue de la station."));
        return false;
    }
    const QStringList offerts = valeurs(demande.value(QStringLiteral("choix")).toArray());
    if (selection.isEmpty()) {
        dire(QString(), QStringLiteral("Choisissez au moins une réponse, ou passez la question."));
        return false;
    }
    for (const QString &choix : selection) {
        if (!offerts.contains(choix)) {
            dire(QString(), QStringLiteral("Ce choix n'est pas offert par Hermes pour cette question."));
            return false;
        }
    }
    // tools/clarify_gateway.py : une sélection multiple voyage comme un tableau JSON de libellés.
    const QString reponse = QString::fromUtf8(QJsonDocument(QJsonArray::fromStringList(selection)).toJson(QJsonDocument::Compact));
    return envoyer(identifiant, QJsonObject{{QStringLiteral("answer"), reponse}}, QStringLiteral("Réponse transmise à Hermes."));
}

bool DemandesAgent::clarifierLot(const QString &identifiant, const QVariantMap &reponses)
{
    const QJsonObject demande = trouver(identifiant);
    if (!demande.value(QStringLiteral("estLot")).toBool()) {
        dire(QString(), QStringLiteral("Lot de questions inconnu de la station."));
        return false;
    }
    QJsonObject answers;
    for (const QJsonValue &element : demande.value(QStringLiteral("lot")).toArray()) {
        const QString qid = element.toObject().value(QStringLiteral("qid")).toString();
        if (!reponses.contains(qid)) {
            dire(QString(), QStringLiteral("Chaque question du lot attend une réponse (vide pour la passer)."));
            return false;
        }
        answers.insert(qid, reponses.value(qid).toString().trimmed());
    }
    return envoyer(identifiant, QJsonObject{{QStringLiteral("answers"), answers}},
                   QStringLiteral("Réponses transmises à Hermes."));
}

} // namespace acp
