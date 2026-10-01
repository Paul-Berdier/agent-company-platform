#include "api/ClientGreffonPoste.h"

#include "api/ApiClient.h"

#include <QJsonDocument>
#include <QRegularExpression>

namespace acp {

ClientGreffonPoste::ClientGreffonPoste(ApiClient *client)
    : m_client(client)
{
}

bool ClientGreffonPoste::identifiantValide(const QString &identifiant)
{
    // Identifiants du greffon et du kanban : lettres, chiffres, « _ », « - », « . », « : ».
    // Jamais de « / », de « .. », d'espace ni de caractère à encoder.
    static const QRegularExpression forme(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9._:~-]{0,199}$"));
    return forme.match(identifiant).hasMatch() && !identifiant.contains(QStringLiteral(".."));
}

QString ClientGreffonPoste::chemin(const QString &relatif)
{
    return QString::fromLatin1(kPrefixe) + relatif;
}

ApiCall *ClientGreffonPoste::refuserIdentifiant(const QString &nature)
{
    return m_client->reject(ApiError::refusal(
        QStringLiteral("Identifiant de %1 illisible : requête refusée par la station.").arg(nature)));
}

ApiCall *ClientGreffonPoste::lire(const QString &relatif)
{
    ApiRequest requete;
    requete.path = chemin(relatif);
    return m_client->send(requete);
}

ApiCall *ClientGreffonPoste::ecrire(const QString &relatif, const QJsonObject &corps, const QString &cle)
{
    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = chemin(relatif);
    requete.body = QJsonDocument(corps);
    requete.idempotencyKey = cle;
    return m_client->send(requete);
}

ApiCall *ClientGreffonPoste::meta() { return lire(QStringLiteral("/v1/meta")); }
ApiCall *ClientGreffonPoste::projets() { return lire(QStringLiteral("/v1/projets")); }
ApiCall *ClientGreffonPoste::questions() { return lire(QStringLiteral("/v1/questions")); }
ApiCall *ClientGreffonPoste::poste() { return lire(QStringLiteral("/v1/poste")); }
ApiCall *ClientGreffonPoste::routage() { return lire(QStringLiteral("/v1/routage")); }
ApiCall *ClientGreffonPoste::quotas() { return lire(QStringLiteral("/v1/quotas")); }

ApiCall *ClientGreffonPoste::projet(const QString &identifiant)
{
    if (!identifiantValide(identifiant)) {
        return refuserIdentifiant(QStringLiteral("projet"));
    }
    return lire(QStringLiteral("/v1/projets/%1").arg(identifiant));
}

ApiCall *ClientGreffonPoste::carteDuProjet(const QString &identifiant, const QString &carte)
{
    if (!identifiantValide(identifiant)) {
        return refuserIdentifiant(QStringLiteral("projet"));
    }
    if (!identifiantValide(carte)) {
        return refuserIdentifiant(QStringLiteral("carte"));
    }
    return lire(QStringLiteral("/v1/projets/%1/cartes/%2").arg(identifiant, carte));
}

ApiCall *ClientGreffonPoste::lancerProjet(const QJsonObject &formulaire, const QString &cleIdempotence)
{
    static const QStringList admis = {QStringLiteral("titre"), QStringLiteral("objectif"),
                                      QStringLiteral("profil"), QStringLiteral("depot"),
                                      QStringLiteral("reponses"), QStringLiteral("exploration")};
    for (auto it = formulaire.constBegin(); it != formulaire.constEnd(); ++it) {
        if (!admis.contains(it.key())) {
            return m_client->reject(ApiError::refusal(
                QStringLiteral("Champ « %1 » inconnu du greffon : lancement refusé par la station.")
                    .arg(it.key().left(64))));
        }
    }
    if (cleIdempotence.isEmpty()) {
        return m_client->reject(ApiError::refusal(QStringLiteral(
            "Clé d'idempotence absente : un lancement de projet n'est jamais émis sans elle.")));
    }
    return ecrire(QStringLiteral("/v1/projets"), formulaire, cleIdempotence);
}

ApiCall *ClientGreffonPoste::mettreProjetEnPause(const QString &identifiant)
{
    if (!identifiantValide(identifiant)) {
        return refuserIdentifiant(QStringLiteral("projet"));
    }
    return ecrire(QStringLiteral("/v1/projets/%1/pause").arg(identifiant), {});
}

ApiCall *ClientGreffonPoste::reprendreProjet(const QString &identifiant)
{
    if (!identifiantValide(identifiant)) {
        return refuserIdentifiant(QStringLiteral("projet"));
    }
    return ecrire(QStringLiteral("/v1/projets/%1/reprise").arg(identifiant), {});
}

ApiCall *ClientGreffonPoste::repondre(const QString &question, const QString &reponse)
{
    if (!identifiantValide(question)) {
        return refuserIdentifiant(QStringLiteral("question"));
    }
    return ecrire(QStringLiteral("/v1/questions/%1/reponse").arg(question),
                  QJsonObject{{QStringLiteral("reponse"), reponse}});
}

ApiCall *ClientGreffonPoste::reprendreTriage(const QString &tableau, const QString &carte,
                                             const QString &consigne)
{
    if (!identifiantValide(tableau)) {
        return refuserIdentifiant(QStringLiteral("tableau"));
    }
    if (!identifiantValide(carte)) {
        return refuserIdentifiant(QStringLiteral("carte"));
    }
    QJsonObject corps;
    if (!consigne.trimmed().isEmpty()) {
        corps.insert(QStringLiteral("consigne"), consigne);
    }
    return ecrire(QStringLiteral("/v1/triage/%1/%2/reprendre").arg(tableau, carte), corps);
}

ApiCall *ClientGreffonPoste::conclureTriage(const QString &tableau, const QString &carte)
{
    if (!identifiantValide(tableau)) {
        return refuserIdentifiant(QStringLiteral("tableau"));
    }
    if (!identifiantValide(carte)) {
        return refuserIdentifiant(QStringLiteral("carte"));
    }
    return ecrire(QStringLiteral("/v1/triage/%1/%2/conclure").arg(tableau, carte), {});
}

ApiCall *ClientGreffonPoste::pauseGenerale(bool generale, const QString &raison)
{
    if (raison.size() > 200) {
        return m_client->reject(ApiError::refusal(
            QStringLiteral("La raison compte 200 caractères au plus.")));
    }
    QJsonObject corps{{QStringLiteral("generale"), generale}};
    if (!raison.trimmed().isEmpty()) {
        corps.insert(QStringLiteral("raison"), raison);
    }
    return ecrire(QStringLiteral("/v1/pause"), corps);
}

ApiCall *ClientGreffonPoste::enrolerPoste()
{
    return ecrire(QStringLiteral("/v1/poste/enrolement"), {});
}

ApiCall *ClientGreffonPoste::confirmerEmpreinte(const QString &machineId, const QString &empreinte)
{
    return ecrire(QStringLiteral("/v1/poste/confirmation"),
                  QJsonObject{{QStringLiteral("machine_id"), machineId},
                              {QStringLiteral("empreinte"), empreinte}});
}

ApiCall *ClientGreffonPoste::revoquerPoste(const QString &machineId, const QString &motif)
{
    return ecrire(QStringLiteral("/v1/poste/revocation"),
                  QJsonObject{{QStringLiteral("machine_id"), machineId},
                              {QStringLiteral("motif"), motif}});
}

ApiCall *ClientGreffonPoste::releverPoste()
{
    return ecrire(QStringLiteral("/v1/poste/releve"), {});
}

ApiCall *ClientGreffonPoste::validerRoutage(const QJsonValue &releves, const QJsonValue &classes)
{
    return ecrire(QStringLiteral("/v1/routage"),
                  QJsonObject{{QStringLiteral("releves"), releves}, {QStringLiteral("classes"), classes}});
}

ApiCall *ClientGreffonPoste::accepterReleve(const QString &releveId)
{
    return ecrire(QStringLiteral("/v1/routage/releve-accepte"),
                  QJsonObject{{QStringLiteral("releve_id"), releveId}});
}

ApiCall *ClientGreffonPoste::desactiverSurcharge(const QString &identifiant)
{
    if (!identifiantValide(identifiant)) {
        return refuserIdentifiant(QStringLiteral("surcharge"));
    }
    return ecrire(QStringLiteral("/v1/routage/surcharges/%1/desactiver").arg(identifiant), {});
}

} // namespace acp
