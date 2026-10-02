#include "services/CompatibiliteHermes.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "app/BuildConfig.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QVariant>

namespace acp {

namespace {

QString texte(const QJsonValue &valeur)
{
    if (valeur.isString()) {
        return valeur.toString();
    }
    if (valeur.isDouble()) {
        return QString::number(valeur.toDouble());
    }
    return {};
}

//! Nom et majeure d'un contrat « acp-poste/1 » ; majeure −1 si illisible.
QPair<QString, int> contrat(const QString &brut)
{
    const qsizetype barre = brut.indexOf(QLatin1Char('/'));
    if (barre <= 0) {
        return {brut, -1};
    }
    const QString version = brut.mid(barre + 1);
    const QString majeure = version.section(QLatin1Char('.'), 0, 0);
    bool lu = false;
    const int numero = majeure.toInt(&lu);
    return {brut.left(barre), lu ? numero : -1};
}

} // namespace

CompatibiliteHermes::CompatibiliteHermes(ClientGreffonPoste *greffon, QObject *parent)
    : QObject(parent)
    , m_greffon(greffon)
{
}

CompatibiliteHermes::Evaluation CompatibiliteHermes::evaluer(const QJsonObject &meta)
{
    Evaluation resultat;
    const QString contratAttendu = QString::fromLatin1(ACP_CONTRAT_ACP_POSTE);
    const QString versionTestee = QString::fromLatin1(ACP_HERMES_VERSION);
    const QString infoEpinglee = QString::fromLatin1(ACP_OPENRPC_INFO_VERSION);
    const QString empreinteEpinglee = QString::fromLatin1(ACP_OPENRPC_SHA256);

    const QJsonObject hermes = meta.value(QStringLiteral("hermes")).toObject();
    const QJsonObject openrpc = meta.value(QStringLiteral("openrpc")).toObject();
    const QJsonObject greffon = meta.value(QStringLiteral("greffon")).toObject();
    resultat.contratRecu = texte(meta.value(QStringLiteral("contrat")));
    resultat.versionHermes = texte(hermes.value(QStringLiteral("version")));
    resultat.versionGreffon = texte(greffon.value(QStringLiteral("version")));
    resultat.empreinteOpenRpc = texte(openrpc.value(QStringLiteral("empreinte_installee")));
    for (const QJsonValue &alerte : meta.value(QStringLiteral("alertes")).toArray()) {
        if (alerte.isString()) {
            resultat.alertes.append(alerte.toString());
        }
    }
    const QJsonObject machine = meta.value(QStringLiteral("machine")).toObject();
    const QJsonValue executant = machine.value(QStringLiteral("executant"));
    if (executant.isObject()) {
        resultat.etatExecutant = QStringLiteral("annonce");
    } else if (executant.isNull()) {
        resultat.etatExecutant = QStringLiteral("aucun"); // étape P6 en place, aucun exécutant connu
    } else if (machine.value(QStringLiteral("base")) == QJsonValue(QStringLiteral("illisible"))) {
        resultat.etatExecutant = QStringLiteral("illisible");
    } else {
        resultat.etatExecutant = QStringLiteral("absent"); // clé absente : étape non déployée
    }
    resultat.executantPresent = executant.isObject();
    resultat.executant = executant.toObject();

    // Contrat du greffon : une autre majeure bloque toutes les pages du greffon.
    const auto [nomRecu, majeureRecue] = contrat(resultat.contratRecu);
    const auto [nomAttendu, majeureAttendue] = contrat(contratAttendu);
    if (resultat.contratRecu.isEmpty() || nomRecu != nomAttendu || majeureRecue != majeureAttendue) {
        resultat.etat = CompatibilityStatus::Incompatible;
        resultat.greffonDisponible = false;
        resultat.explication = QStringLiteral("Contrat du greffon incompatible : %1, attendu %2. Pages "
                                              "du greffon bloquées par la station.")
                                   .arg(resultat.contratRecu.isEmpty() ? QStringLiteral("Inconnu")
                                                                       : resultat.contratRecu,
                                        contratAttendu);
    } else {
        resultat.greffonDisponible = true;
    }

    // Contrat JSON-RPC : une autre version d'information coupe la Discussion seule.
    const QString infoInstallee = texte(openrpc.value(QStringLiteral("info_version")));
    if (infoInstallee != infoEpinglee) {
        resultat.discussionDisponible = false;
        resultat.avertissements.append(
            QStringLiteral("Discussion coupée : contrat JSON-RPC de Hermes en version %1, la station "
                           "attend %2.")
                .arg(infoInstallee.isEmpty() ? QStringLiteral("Inconnu") : infoInstallee, infoEpinglee));
    } else {
        resultat.discussionDisponible = true;
        const QJsonValue identique = openrpc.value(QStringLiteral("identique"));
        if ((identique.isBool() && !identique.toBool()) || resultat.empreinteOpenRpc != empreinteEpinglee) {
            resultat.avertissements.append(
                QStringLiteral("Le contrat JSON-RPC servi diffère de celui contre lequel la station a "
                               "été construite (empreinte %1, attendue %2) : la Discussion reste "
                               "ouverte, sous réserve.")
                    .arg(resultat.empreinteOpenRpc.isEmpty() ? QStringLiteral("Inconnu")
                                                             : resultat.empreinteOpenRpc.left(12),
                         empreinteEpinglee.left(12)));
        }
    }

    if (resultat.versionHermes.isEmpty()) {
        resultat.avertissements.append(QStringLiteral("Version de Hermes inconnue."));
    } else if (resultat.versionHermes != versionTestee) {
        resultat.avertissements.append(QStringLiteral("Hermes %1 n'est pas la version testée (%2).")
                                           .arg(resultat.versionHermes, versionTestee));
    }

    if (resultat.etat != CompatibilityStatus::Incompatible) {
        const bool ecart = !resultat.avertissements.isEmpty() || !resultat.alertes.isEmpty();
        resultat.etat = ecart ? CompatibilityStatus::Avertissement : CompatibilityStatus::Compatible;
        if (!resultat.avertissements.isEmpty()) {
            resultat.explication = resultat.avertissements.join(QLatin1Char(' '));
        } else if (!resultat.alertes.isEmpty()) {
            resultat.explication = QStringLiteral("%1 alerte(s) signalée(s) par Hermes : voir les "
                                                  "diagnostics.")
                                       .arg(resultat.alertes.size());
        } else {
            resultat.explication = QStringLiteral("Hermes %1 et le greffon %2 sont ceux contre lesquels "
                                                  "la station a été testée.")
                                       .arg(resultat.versionHermes, resultat.contratRecu);
        }
    }
    return resultat;
}

void CompatibiliteHermes::verifier()
{
    const quint64 generation = ++m_generation;
    Evaluation enCours = m_evaluation;
    enCours.etat = CompatibilityStatus::Verification;
    publier(enCours);
    ApiCall *appel = m_greffon->meta();
    connect(appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation == m_generation) {
            m_luA = QDateTime::currentDateTimeUtc();
            m_erreurLecture.clear();
            publier(evaluer(reponse.json.object()));
        }
    });
    connect(appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        Evaluation echec;
        if (erreur.httpStatus() == 404) {
            echec.etat = CompatibilityStatus::GreffonAbsent;
            echec.discussionDisponible = true;
            echec.explication = QStringLiteral("Greffon acp-poste absent de ce Hermes : seules la "
                                               "Discussion et les Diagnostics restent disponibles.");
        } else {
            echec.etat = CompatibilityStatus::Injoignable;
            echec.explication = QStringLiteral("Compatibilité non vérifiée : %1").arg(erreur.message());
            m_erreurLecture = erreur.message();
        }
        publier(echec);
    });
}

void CompatibiliteHermes::oublier()
{
    ++m_generation;
    m_luA = QDateTime();
    m_erreurLecture.clear();
    publier(Evaluation{});
}

void CompatibiliteHermes::appliquerLecture(const QJsonObject &meta)
{
    ++m_generation; // une vérification plus ancienne encore en vol ne l'écrasera pas
    m_luA = QDateTime::currentDateTimeUtc();
    m_erreurLecture.clear();
    publier(evaluer(meta));
}

void CompatibiliteHermes::appliquerEchec(const ApiError &erreur)
{
    if (erreur.kind() == ApiFailure::Cancelled) {
        return;
    }
    if (erreur.httpStatus() == 404) {
        ++m_generation;
        Evaluation absent;
        absent.etat = CompatibilityStatus::GreffonAbsent;
        absent.discussionDisponible = true;
        absent.explication = QStringLiteral("Greffon acp-poste absent de ce Hermes : seules la "
                                            "Discussion et les Diagnostics restent disponibles.");
        m_erreurLecture.clear();
        publier(absent);
        return;
    }
    m_erreurLecture = erreur.message();
    emit change();
}

QString CompatibiliteHermes::lecture() const
{
    return m_luA.isValid() ? QStringLiteral("Lu à %1").arg(m_luA.toLocalTime().toString(QStringLiteral("HH:mm:ss")))
                           : QStringLiteral("Jamais lu");
}

void CompatibiliteHermes::publier(Evaluation evaluation)
{
    m_evaluation = std::move(evaluation);
    // Échec fermé : le verdict rendu s'applique au client du greffon, pas seulement à l'écran.
    switch (m_evaluation.etat) {
    case CompatibilityStatus::Incompatible:
    case CompatibilityStatus::GreffonAbsent:
        m_greffon->bloquer(m_evaluation.explication);
        break;
    case CompatibilityStatus::Compatible:
    case CompatibilityStatus::Avertissement:
    case CompatibilityStatus::NonVerifiee:
        m_greffon->debloquer();
        break;
    case CompatibilityStatus::Verification:
    case CompatibilityStatus::Injoignable:
        break; // le verdict précédent reste appliqué
    }
    emit change();
}

QString CompatibiliteHermes::libelle() const
{
    switch (m_evaluation.etat) {
    case CompatibilityStatus::NonVerifiee: return QStringLiteral("Non vérifiée");
    case CompatibilityStatus::Verification: return QStringLiteral("Vérification");
    case CompatibilityStatus::Compatible: return QStringLiteral("Compatible");
    case CompatibilityStatus::Avertissement: return QStringLiteral("Compatible avec réserves");
    case CompatibilityStatus::Incompatible: return QStringLiteral("Incompatible");
    case CompatibilityStatus::GreffonAbsent: return QStringLiteral("Greffon absent");
    case CompatibilityStatus::Injoignable: return QStringLiteral("Non vérifiable");
    }
    return QStringLiteral("Inconnu");
}

QString CompatibiliteHermes::versionHermes() const
{
    return m_evaluation.versionHermes.isEmpty() ? QStringLiteral("Inconnu") : m_evaluation.versionHermes;
}

QString CompatibiliteHermes::versionTestee() const
{
    return QString::fromLatin1(ACP_HERMES_VERSION);
}

QString CompatibiliteHermes::contratRecu() const
{
    return m_evaluation.contratRecu.isEmpty() ? QStringLiteral("Inconnu") : m_evaluation.contratRecu;
}

QString CompatibiliteHermes::versionGreffon() const
{
    return m_evaluation.versionGreffon.isEmpty() ? QStringLiteral("Inconnu") : m_evaluation.versionGreffon;
}

QString CompatibiliteHermes::empreinteOpenRpc() const
{
    return m_evaluation.empreinteOpenRpc.isEmpty() ? QStringLiteral("Inconnu")
                                                   : m_evaluation.empreinteOpenRpc;
}

} // namespace acp
