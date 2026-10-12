#include "viewmodels/PreparationHermesViewModel.h"

#include "api/ApiClient.h"
#include "diagnostics/Redaction.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"

#include <QClipboard>
#include <QDesktopServices>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QTimer>

#include <algorithm>
#include <cmath>
#include <utility>

namespace acp {
namespace {
const QString kDebut = QStringLiteral("/api/providers/oauth/openai-codex/start");
const QString kSuivi = QStringLiteral("/api/providers/oauth/openai-codex/poll/");
const QString kAnnulation = QStringLiteral("/api/providers/oauth/sessions/");
const QUrl kVerification(QStringLiteral("https://auth.openai.com/codex/device"));

bool identifiantValide(const QString &valeur)
{
    // secrets.token_urlsafe(16) dans le Hermes épinglé. Aucune interpolation de chemin libre.
    static const QRegularExpression forme(QStringLiteral("^[A-Za-z0-9_-]{22}$"));
    return forme.match(valeur).hasMatch();
}

bool entierEntre(const QJsonValue &valeur, int minimum, int maximum)
{
    if (!valeur.isDouble()) return false;
    const double n = valeur.toDouble();
    return std::isfinite(n) && n == std::floor(n) && n >= minimum && n <= maximum;
}
} // namespace

PreparationHermesViewModel::PreparationHermesViewModel(ApiClient *client, GatewayClient *passerelle, QObject *parent)
    : QObject(parent), m_client(client), m_passerelle(passerelle),
      m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); }),
      m_suivi(new QTimer(this)), m_decompte(new QTimer(this))
{
    m_suivi->setSingleShot(true);
    m_decompte->setInterval(1000);
    connect(m_suivi, &QTimer::timeout, this, &PreparationHermesViewModel::suivre);
    connect(m_decompte, &QTimer::timeout, this, [this] {
        if (m_etat == QLatin1String("attente") && secondesRestantes() == 0) {
            arreterFlux(QStringLiteral("expire"), QStringLiteral("Le code a expiré. Demandez une nouvelle connexion."));
        } else {
            emit change();
        }
    });
    connect(m_client, &ApiClient::baseUrlChanged, this, &PreparationHermesViewModel::oublier);
    connect(m_passerelle, &GatewayClient::prete, this, [this] {
        if (m_active && !occupe()) verifier();
    });
    connect(m_passerelle, &GatewayClient::etatChange, this, [this] {
        if (m_active && !passerellePrete() && m_etat == QLatin1String("lecture")) {
            ++m_generation;
            poser(QStringLiteral("erreur"), QStringLiteral("Le contrôle a été interrompu par la perte du lien avec Hermes. Réessayez après reconnexion."));
        } else {
            emit change();
        }
    });
}

PreparationHermesViewModel::~PreparationHermesViewModel()
{
    ++m_generation;
    interrompreAppel();
    effacerDefi();
}

bool PreparationHermesViewModel::passerellePrete() const
{
    return m_passerelle->etat() == GatewayClient::Etat::Pret;
}

void PreparationHermesViewModel::activer()
{
    m_active = true;
    m_serveur = m_client->baseUrl();
    if (passerellePrete() && !occupe()) verifier();
    else if (!occupe()) poser(QStringLiteral("inconnu"), QStringLiteral("La session ACP est ouverte. En attente du lien avec Hermes pour vérifier sa configuration."));
}

void PreparationHermesViewModel::oublier()
{
    ++m_generation;
    m_active = false;
    m_serveur.clear();
    interrompreAppel();
    effacerDefi();
    m_autorisationRecue = false;
    m_fournisseur.clear();
    m_modele.clear();
    m_luA = {};
    poser(QStringLiteral("inconnu"), QStringLiteral("Connectez votre session ACP pour retrouver la configuration de Hermes."));
}

void PreparationHermesViewModel::poser(const QString &etat, const QString &detail)
{
    m_etat = etat;
    m_detail = detail;
    emit change();
}

QString PreparationHermesViewModel::libelle() const
{
    if (m_etat == QLatin1String("lecture")) return QStringLiteral("Vérification de Hermes");
    if (m_etat == QLatin1String("manquant")) return QStringLiteral("Compte fournisseur à connecter");
    if (m_etat == QLatin1String("pret")) return QStringLiteral("Configuration retrouvée");
    if (m_etat == QLatin1String("demarrage")) return QStringLiteral("Préparation de la connexion");
    if (m_etat == QLatin1String("attente")) return QStringLiteral("Autorisation attendue");
    if (m_etat == QLatin1String("annulation")) return QStringLiteral("Annulation en cours");
    if (m_etat == QLatin1String("annule")) return QStringLiteral("Connexion annulée");
    if (m_etat == QLatin1String("expire")) return QStringLiteral("Code expiré");
    if (m_etat == QLatin1String("erreur")) return QStringLiteral("Vérification nécessaire");
    return QStringLiteral("État inconnu");
}

QString PreparationHermesViewModel::prochaineAction() const
{
    if (!m_active) return QStringLiteral("Reconnectez-vous à ACP.");
    if (m_etat == QLatin1String("pret"))
        return QStringLiteral("Vous pouvez ouvrir Discussion. Aucun appel au modèle n'a été effectué par ce contrôle.");
    if (m_etat == QLatin1String("attente"))
        return QStringLiteral("Ouvrez la page officielle OpenAI et saisissez ce code avec le compte que vous souhaitez utiliser pour Hermes.");
    if (m_etat == QLatin1String("manquant"))
        return QStringLiteral("Connectez votre compte ChatGPT pour le coordinateur Hermes. Les comptes des exécutants se configurent séparément.");
    if (m_autorisationRecue)
        return QStringLiteral("La connexion a été enregistrée par Hermes. Vérifiez son modèle dans le tableau de bord, puis relancez le contrôle.");
    if (!passerellePrete()) return QStringLiteral("Attendez le rétablissement du lien avec Hermes.");
    if (occupe()) return QStringLiteral("Attendez le résultat du serveur.");
    return QStringLiteral("Vérifiez de nouveau l'état, ou ouvrez le tableau de bord pour choisir le modèle de Hermes.");
}

QString PreparationHermesViewModel::lecture() const
{
    return m_luA.isValid() ? QStringLiteral("Contrôlé à %1").arg(m_luA.toLocalTime().toString(QStringLiteral("HH:mm:ss")))
                          : QStringLiteral("Pas encore vérifié");
}

bool PreparationHermesViewModel::occupe() const
{
    return m_etat == QLatin1String("lecture") || m_etat == QLatin1String("demarrage")
        || m_etat == QLatin1String("attente") || m_etat == QLatin1String("annulation");
}

bool PreparationHermesViewModel::peutVerifier() const { return m_active && m_client->baseUrl() == m_serveur && passerellePrete() && !occupe(); }
bool PreparationHermesViewModel::peutConnecter() const { return peutVerifier(); }
bool PreparationHermesViewModel::defiActif() const { return m_etat == QLatin1String("attente") && !m_code.isEmpty(); }

int PreparationHermesViewModel::secondesRestantes() const
{
    if (!m_attente.isValid() || m_dureeMs <= 0) return 0;
    return static_cast<int>(std::max<qint64>(0, (m_dureeMs - m_attente.elapsed() + 999) / 1000));
}

QString PreparationHermesViewModel::texteSur(const QString &texte) const
{
    QString sur = redactSecrets(texte.left(1500));
    if (!m_code.isEmpty()) sur.replace(m_code, QStringLiteral("[code masqué]"));
    if (!m_sessionId.isEmpty()) sur.replace(m_sessionId, QStringLiteral("[session masquée]"));
    return sur;
}

void PreparationHermesViewModel::verifier()
{
    if (!peutVerifier()) return;
    const quint64 generation = ++m_generation;
    m_fournisseur.clear();
    m_modele.clear();
    poser(QStringLiteral("lecture"), QStringLiteral("Lecture de la configuration déjà présente sur votre serveur."));
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("setup.status"), {}, std::chrono::seconds(20));
    connect(appel, &AppelRpc::reussi, this, [this, generation](const QJsonValue &resultat) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        const QJsonObject objet = resultat.toObject();
        if (!resultat.isObject() || !objet.value(QStringLiteral("provider_configured")).isBool()
            || objet.value(QStringLiteral("ok")) == QJsonValue(false)) {
            poser(QStringLiteral("erreur"), QStringLiteral("Hermes n'a pas rendu un état de configuration exploitable. Aucun compte n'est supposé connecté."));
            return;
        }
        lireResolution(generation, objet.value(QStringLiteral("provider_configured")).toBool());
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation == m_generation && m_active && m_client->baseUrl() == m_serveur)
            poser(QStringLiteral("erreur"), QStringLiteral("État de Hermes non vérifiable : %1").arg(texteSur(erreur.message)));
    });
}

void PreparationHermesViewModel::lireResolution(quint64 generation, bool fournisseurConfigure)
{
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("setup.runtime_check"), {}, std::chrono::seconds(30));
    connect(appel, &AppelRpc::reussi, this, [this, generation, fournisseurConfigure](const QJsonValue &resultat) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        const QJsonObject objet = resultat.toObject();
        if (!resultat.isObject() || !objet.value(QStringLiteral("ok")).isBool()) {
            poser(QStringLiteral("erreur"), QStringLiteral("La réponse au contrôle du modèle est illisible. Aucune disponibilité n'est présumée."));
            return;
        }
        m_luA = QDateTime::currentDateTimeUtc();
        if (!objet.value(QStringLiteral("ok")).toBool()) {
            const QString cause = texteSur(objet.value(QStringLiteral("error")).toString());
            poser(fournisseurConfigure ? QStringLiteral("erreur") : QStringLiteral("manquant"),
                  (m_autorisationRecue ? QStringLiteral("Autorisation enregistrée. ") : QString())
                  + (cause.isEmpty() ? QStringLiteral("Le modèle configuré dans Hermes n'est pas disponible pour le moment.")
                                     : QStringLiteral("Le modèle de Hermes nécessite votre attention : %1").arg(cause)));
            return;
        }
        const QString fournisseur = objet.value(QStringLiteral("provider")).toString().trimmed();
        const QString modele = objet.value(QStringLiteral("model")).toString().trimmed();
        if (fournisseur.isEmpty() || modele.isEmpty() || ressembleAUnSecret(fournisseur) || ressembleAUnSecret(modele)) {
            poser(QStringLiteral("erreur"), QStringLiteral("Le contrôle de Hermes ne précise pas un fournisseur et un modèle lisibles."));
            return;
        }
        m_fournisseur = fournisseur.left(120);
        m_modele = modele.left(180);
        poser(QStringLiteral("pret"), (m_autorisationRecue ? QStringLiteral("Autorisation enregistrée par Hermes. ") : QString())
              + QStringLiteral("Compte et modèle retrouvés sur votre serveur. La prochaine discussion confirmera leur accès au modèle."));
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation == m_generation && m_active && m_client->baseUrl() == m_serveur)
            poser(QStringLiteral("erreur"), QStringLiteral("Contrôle du modèle impossible : %1").arg(texteSur(erreur.message)));
    });
}

void PreparationHermesViewModel::connecter()
{
    if (!peutConnecter()) return;
    const quint64 generation = ++m_generation;
    m_autorisationRecue = false;
    m_fournisseur.clear();
    m_modele.clear();
    m_annulationDemandee = false;
    poser(QStringLiteral("demarrage"), QStringLiteral("Hermes prépare le code d'appareil de votre compte ChatGPT."));
    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = kDebut;
    requete.body = QJsonDocument(QJsonObject{});
    requete.timeout = std::chrono::seconds(20);
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        m_appel = nullptr;
        const QJsonObject objet = reponse.json.object();
        const QString id = objet.value(QStringLiteral("session_id")).toString();
        if (!identifiantValide(id)) {
            poser(QStringLiteral("erreur"), QStringLiteral("La réponse de connexion ne contient pas d'identifiant de flux valide. Aucun code n'a été affiché ; l'annulation distante n'est pas confirmée."));
            return;
        }
        m_sessionId = id;
        if (m_annulationDemandee) {
            arreterFlux(QStringLiteral("annule"), QStringLiteral("La demande de connexion a été annulée. Un compte déjà autorisé n'est pas déconnecté."));
            return;
        }
        const QString code = objet.value(QStringLiteral("user_code")).toString();
        static const QRegularExpression formeCode(QStringLiteral("^[A-Za-z0-9-]{4,32}$"));
        const QUrl url(objet.value(QStringLiteral("verification_url")).toString());
        if (objet.value(QStringLiteral("flow")) != QJsonValue(QStringLiteral("device_code"))
            || !formeCode.match(code).hasMatch() || url != kVerification
            || !entierEntre(objet.value(QStringLiteral("expires_in")), 1, 900)
            || !entierEntre(objet.value(QStringLiteral("poll_interval")), 1, 60)) {
            arreterFlux(QStringLiteral("erreur"), QStringLiteral("Le défi reçu de Hermes est invalide. La connexion a été arrêtée sans ouvrir d'adresse externe."));
            return;
        }
        m_code = code;
        m_url = url;
        m_dureeMs = static_cast<qint64>(objet.value(QStringLiteral("expires_in")).toInt()) * 1000;
        if (m_dureeTest > 0) m_dureeMs = std::min(m_dureeMs, m_dureeTest);
        m_intervalleMs = m_intervalleTest > 0 ? m_intervalleTest : objet.value(QStringLiteral("poll_interval")).toInt() * 1000;
        m_attente.start();
        m_decompte->start();
        poser(QStringLiteral("attente"), QStringLiteral("Saisissez le code sur la page officielle OpenAI. ACP attend la confirmation de Hermes ; aucun jeton fournisseur ne passe par l'application."));
        m_suivi->start(m_intervalleMs);
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        m_appel = nullptr;
        if (erreur.kind() == ApiFailure::Cancelled) { oublier(); return; }
        poser(QStringLiteral("erreur"), QStringLiteral("Connexion non confirmée : %1. Si Hermes a créé un défi sans pouvoir le transmettre, celui-ci expirera ; aucun succès n'est présumé.").arg(texteSur(erreur.message())));
    });
}

void PreparationHermesViewModel::suivre()
{
    if (!m_active || !defiActif() || m_appel) return;
    if (secondesRestantes() == 0) {
        arreterFlux(QStringLiteral("expire"), QStringLiteral("Le code a expiré. Demandez une nouvelle connexion."));
        return;
    }
    const quint64 generation = m_generation;
    ApiRequest requete;
    requete.path = kSuivi + m_sessionId;
    requete.timeout = std::chrono::seconds(15);
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        m_appel = nullptr;
        const QJsonObject objet = reponse.json.object();
        const QString etat = objet.value(QStringLiteral("status")).toString();
        if (secondesRestantes() == 0) {
            arreterFlux(QStringLiteral("expire"), QStringLiteral("Le code a expiré. Demandez une nouvelle connexion."));
            return;
        }
        if (objet.value(QStringLiteral("session_id")).toString() != m_sessionId) {
            arreterFlux(QStringLiteral("erreur"), QStringLiteral("Hermes a répondu pour un autre flux de connexion. Aucune autorisation n'est retenue."));
            return;
        }
        if (etat == QLatin1String("pending")) {
            m_suivi->start(m_intervalleMs);
            return;
        }
        if (etat == QLatin1String("approved")) {
            effacerDefi();
            m_autorisationRecue = true;
            poser(QStringLiteral("inconnu"), QStringLiteral("Autorisation enregistrée par Hermes. Vérification de son modèle…"));
            if (peutVerifier()) verifier();
            else poser(QStringLiteral("erreur"), QStringLiteral("Autorisation enregistrée par Hermes. Le lien de contrôle est interrompu : vérifiez le modèle après reconnexion."));
            return;
        }
        if (etat == QLatin1String("denied") || etat == QLatin1String("expired") || etat == QLatin1String("error")) {
            const QString cause = texteSur(objet.value(QStringLiteral("error_message")).toString());
            effacerDefi();
            poser(etat == QLatin1String("expired") ? QStringLiteral("expire") : QStringLiteral("erreur"),
                  cause.isEmpty() ? QStringLiteral("L'autorisation n'a pas abouti. Vérifiez votre compte puis recommencez.")
                                  : QStringLiteral("L'autorisation n'a pas abouti : %1").arg(cause));
            return;
        }
        arreterFlux(QStringLiteral("erreur"), QStringLiteral("Hermes a rendu un état de connexion inconnu. Aucun succès n'est présumé."));
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        m_appel = nullptr;
        if (erreur.kind() == ApiFailure::Cancelled) { oublier(); return; }
        arreterFlux(QStringLiteral("erreur"), QStringLiteral("Le suivi de la connexion a échoué : %1").arg(texteSur(erreur.message())));
    });
}

void PreparationHermesViewModel::annuler()
{
    if (m_etat == QLatin1String("demarrage")) {
        // On attend l'identifiant rendu par /start pour annuler le vrai flux serveur.
        m_annulationDemandee = true;
        poser(QStringLiteral("annulation"), QStringLiteral("Annulation demandée ; en attente de l'identifiant créé par Hermes."));
    } else if (defiActif()) {
        arreterFlux(QStringLiteral("annule"), QStringLiteral("La demande de connexion a été annulée. Un compte déjà autorisé n'est pas déconnecté."));
    }
}

void PreparationHermesViewModel::arreterFlux(const QString &etatFinal, const QString &detailFinal)
{
    const QString id = m_sessionId;
    const quint64 generation = ++m_generation;
    interrompreAppel();
    effacerDefi();
    if (!m_active || m_client->baseUrl() != m_serveur || !identifiantValide(id)) {
        poser(QStringLiteral("erreur"), detailFinal + QStringLiteral(" L'annulation distante n'est pas confirmée."));
        return;
    }
    poser(QStringLiteral("annulation"), QStringLiteral("Arrêt de la demande auprès de Hermes…"));
    ApiRequest requete;
    requete.method = QByteArrayLiteral("DELETE");
    requete.path = kAnnulation + id;
    requete.body = QJsonDocument(QJsonObject{});
    requete.timeout = std::chrono::seconds(15);
    m_appel = m_client->send(requete);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation, id, etatFinal, detailFinal](const ApiResponse &reponse) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        m_appel = nullptr;
        const QJsonObject objet = reponse.json.object();
        if (objet.value(QStringLiteral("ok")) == QJsonValue(true) && objet.value(QStringLiteral("session_id")).toString() == id) {
            poser(etatFinal, detailFinal);
        } else {
            poser(QStringLiteral("erreur"), detailFinal + QStringLiteral(" Hermes n'a pas confirmé l'annulation. Vérifiez l'état du compte avant de recommencer."));
        }
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation, detailFinal](const ApiError &) {
        if (generation != m_generation || !m_active || m_client->baseUrl() != m_serveur) return;
        m_appel = nullptr;
        poser(QStringLiteral("erreur"), detailFinal + QStringLiteral(" L'annulation distante n'a pas pu être confirmée ; le défi éventuel reste soumis à son expiration côté serveur."));
    });
}

void PreparationHermesViewModel::interrompreAppel()
{
    if (m_appel) {
        disconnect(m_appel, nullptr, this, nullptr);
        m_appel->abort();
        m_appel = nullptr;
    }
}

void PreparationHermesViewModel::effacerDefi()
{
    m_suivi->stop();
    m_decompte->stop();
    if (!m_code.isEmpty() && qobject_cast<QGuiApplication *>(QCoreApplication::instance())) {
        QClipboard *presse = QGuiApplication::clipboard();
        if (presse && presse->text() == m_code) presse->clear();
    }
    m_code.clear();
    m_sessionId.clear();
    m_url.clear();
    m_attente.invalidate();
    m_dureeMs = 0;
    m_annulationDemandee = false;
}

bool PreparationHermesViewModel::ouvrirVerification()
{
    if (!defiActif() || m_url != kVerification || secondesRestantes() == 0) return false;
    const bool ouvert = m_ouvreur && m_ouvreur(m_url);
    if (!ouvert) {
        m_detail = QStringLiteral("Le navigateur ne s'est pas ouvert. Ouvrez https://auth.openai.com/codex/device dans votre navigateur et saisissez le code affiché.");
        emit change();
    }
    return ouvert;
}

bool PreparationHermesViewModel::copierCode()
{
    if (!defiActif() || secondesRestantes() == 0 || !qobject_cast<QGuiApplication *>(QCoreApplication::instance())) return false;
    QClipboard *presse = QGuiApplication::clipboard();
    if (!presse) return false;
    presse->setText(m_code);
    m_detail = QStringLiteral("Code copié. Collez-le sur la page officielle OpenAI.");
    emit change();
    return true;
}

bool PreparationHermesViewModel::ouvrirTableauDeBord()
{
    if (!m_active || m_client->baseUrl() != m_serveur || !m_client->isConfigured()) return false;
    const bool ouvert = m_ouvreur && m_ouvreur(m_client->resolve(QStringLiteral("/")));
    if (!ouvert) {
        m_detail = QStringLiteral("Le navigateur ne s'est pas ouvert. Retrouvez l'adresse de votre Hermes dans Réglages.");
        emit change();
    }
    return ouvert;
}

void PreparationHermesViewModel::setDelaisTest(std::chrono::milliseconds suivi, std::chrono::milliseconds duree)
{
    m_intervalleTest = static_cast<int>(std::max<qint64>(1, suivi.count()));
    m_dureeTest = std::max<qint64>(1, duree.count());
    m_decompte->setInterval(std::min(1000, m_intervalleTest));
}
} // namespace acp