#include "auth/SessionHermes.h"

#include "api/ApiClient.h"
#include "api/ApiError.h"
#include "auth/NativeAuthFlow.h"
#include "storage/SettingsStore.h"

#include <QClipboard>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QTimer>

#include <algorithm>
#include <cmath>

namespace acp {

namespace {

QString fournisseurAttendu()
{
    return QString::fromLatin1(NativeAuthFlow::kFournisseur);
}

QString ouInconnu(const QString &valeur)
{
    return valeur.isEmpty() ? QStringLiteral("Inconnu") : valeur;
}

} // namespace

SessionHermes::SessionHermes(ApiClient *client, CredentialVault *coffre, SettingsStore *reglages,
                             QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_coffre(coffre)
    , m_reglages(reglages)
    , m_flux(new NativeAuthFlow(client, this))
    , m_minuterie(new QTimer(this))
    , m_relance(new QTimer(this))
    , m_tic(new QTimer(this))
{
    m_minuterie->setSingleShot(true);
    m_relance->setSingleShot(true);
    m_tic->setInterval(1000);
    connect(m_minuterie, &QTimer::timeout, this, &SessionHermes::rafraichir);
    connect(m_relance, &QTimer::timeout, this, &SessionHermes::rafraichir);
    connect(m_tic, &QTimer::timeout, this, &SessionHermes::attenteChange);

    // Le transport lit le jeton d'accès au moment de chaque requête, et jamais ailleurs.
    m_client->setBearerProvider([this] { return m_jetons.acces; });
    connect(m_client, &ApiClient::refreshRequested, this, &SessionHermes::rafraichir);
    connect(m_client, &ApiClient::bearerRejected, this, [this](const ApiError &erreur) {
        if (m_jetons.estVide()) {
            return;
        }
        perdre(SessionStatus::Expiree,
               QStringLiteral("Hermes a refusé la session (%1) : reconnectez-vous.").arg(erreur.message()),
               false);
    });
    connect(m_client, &ApiClient::baseUrlChanged, this, [this] {
        const QUrl ancien = m_serveur;
        const QUrl nouveau = m_client->baseUrl();
        if (ancien == nouveau) {
            return;
        }
        m_flux->annuler();
        if (!ancien.isEmpty()) {
            // Une session n'appartient jamais à deux serveurs : l'entrée de l'ancien est purgée.
            m_coffre.oublier(ancien);
            const bool avaitSession = !m_jetons.estVide() || !m_jetons.rafraichissement.isEmpty();
            ++m_generation;
            m_minuterie->stop();
            m_relance->stop();
            m_rafraichissementEnVol = false;
            effacerSession();
            if (avaitSession) {
                emit sessionPerdue(QStringLiteral("Adresse du serveur changée : session oubliée."));
            }
        }
        m_serveur = nouveau;
        changerEtat(nouveau.isEmpty() ? SessionStatus::NonConfiguree : SessionStatus::Deconnectee);
        emit identiteChange();
    });

    m_serveur = m_client->baseUrl();
    m_etat = m_serveur.isEmpty() ? SessionStatus::NonConfiguree : SessionStatus::Deconnectee;
    suivreFlux();
}

SessionHermes::~SessionHermes()
{
    m_jetons.effacer();
}

void SessionHermes::setHorloge(Horloge horloge)
{
    m_horloge = horloge;
    m_flux->setHorloge(std::move(horloge));
}

QDateTime SessionHermes::maintenant() const
{
    return m_horloge ? m_horloge() : QDateTime::currentDateTimeUtc();
}

// --- État -----------------------------------------------------------------------

QString SessionHermes::libelleEtat() const
{
    switch (m_etat) {
    case SessionStatus::NonConfiguree: return QStringLiteral("Non configurée");
    case SessionStatus::Deconnectee: return QStringLiteral("Déconnectée");
    case SessionStatus::AttenteNavigateur: return QStringLiteral("En attente du navigateur");
    case SessionStatus::Echange: return QStringLiteral("Connexion en cours");
    case SessionStatus::Connectee: return QStringLiteral("Connectée");
    case SessionStatus::Rafraichissement: return QStringLiteral("Renouvellement de la session");
    case SessionStatus::FournisseurInjoignable: return QStringLiteral("Fournisseur d'identité injoignable");
    case SessionStatus::HorsLigne: return QStringLiteral("Hors ligne");
    case SessionStatus::Expiree: return QStringLiteral("Session expirée");
    case SessionStatus::Refusee: return QStringLiteral("Connexion refusée");
    }
    return QStringLiteral("Inconnu");
}

bool SessionHermes::estOccupee() const
{
    return m_etat == SessionStatus::AttenteNavigateur || m_etat == SessionStatus::Echange
        || m_etat == SessionStatus::Rafraichissement;
}

bool SessionHermes::navigateurNonOuvert() const
{
    return m_etat == SessionStatus::AttenteNavigateur && m_flux->etape() == NativeAuthFlow::Etape::AttenteNavigateur
        && !m_flux->navigateurOuvert();
}

int SessionHermes::secondesRestantes() const
{
    return m_flux->secondesRestantes();
}

QString SessionHermes::avertissement() const
{
    return m_flux->avertissement();
}

QString SessionHermes::identifiant() const { return ouInconnu(m_jetons.utilisateur); }
QString SessionHermes::nomAffiche() const { return ouInconnu(m_nomAffiche); }
QString SessionHermes::courriel() const { return ouInconnu(m_courriel); }
QString SessionHermes::fournisseur() const { return ouInconnu(m_jetons.fournisseur); }

QString SessionHermes::expiration() const
{
    return m_jetons.expireLe.isValid()
        ? m_jetons.expireLe.toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm"))
        : QStringLiteral("Inconnu");
}

QString SessionHermes::nomDuCoffre() const
{
    return m_coffre.coffre() ? m_coffre.coffre()->backendName() : QStringLiteral("Aucun coffre");
}

bool SessionHermes::memoriser() const
{
    return m_reglages && m_reglages->connexionMemorisee();
}

void SessionHermes::setMemoriser(bool memoriser)
{
    if (!m_reglages || this->memoriser() == memoriser) {
        return;
    }
    m_reglages->setConnexionMemorisee(memoriser);
    m_reglages->flush();
    if (!memoriser) {
        // Consentement retiré : l'entrée disparaît tout de suite.
        const VaultResult effacement = m_coffre.oublier(m_serveur);
        setAvisCoffre(effacement.ok ? QString()
                                    : QStringLiteral("Entrée du coffre non effacée : %1").arg(effacement.reason));
    } else if (estConnectee()) {
        ecrireCoffre(m_jetons);
    }
    emit memoriserChange();
}

void SessionHermes::changerEtat(SessionStatus::State etat, const QString &erreur)
{
    const bool attente = etat == SessionStatus::AttenteNavigateur;
    if (attente && !m_tic->isActive()) {
        m_tic->start();
    } else if (!attente) {
        m_tic->stop();
    }
    if (m_etat == etat && m_derniereErreur == erreur) {
        return;
    }
    m_etat = etat;
    m_derniereErreur = erreur;
    emit etatChange();
}

void SessionHermes::setAvisCoffre(const QString &avis)
{
    if (m_avisCoffre == avis) {
        return;
    }
    m_avisCoffre = avis;
    emit avisCoffreChange();
}

// --- Connexion ------------------------------------------------------------------

void SessionHermes::suivreFlux()
{
    connect(m_flux, &NativeAuthFlow::etapeChangee, this, [this] {
        switch (m_flux->etape()) {
        case NativeAuthFlow::Etape::Prerequis:
        case NativeAuthFlow::Etape::AttenteNavigateur:
            changerEtat(SessionStatus::AttenteNavigateur);
            emit etatChange();
            break;
        case NativeAuthFlow::Etape::Echange:
            changerEtat(SessionStatus::Echange);
            break;
        case NativeAuthFlow::Etape::Inactif:
            break;
        }
    });
    connect(m_flux, &NativeAuthFlow::reussi, this, &SessionHermes::adopter);
    connect(m_flux, &NativeAuthFlow::echoue, this, [this](const QString &raison) {
        changerEtat(SessionStatus::Refusee, raison);
    });
}

void SessionHermes::seConnecter()
{
    if (!m_client->isConfigured()) {
        changerEtat(SessionStatus::NonConfiguree,
                    QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    if (m_flux->enCours()) {
        return;
    }
    if (!m_jetons.estVide() || !m_jetons.rafraichissement.isEmpty()) {
        // Reconnexion demandée sur une session existante (par exemple après des 503
        // persistants) : l'ancienne session et son entrée du coffre sont oubliées d'abord,
        // pour qu'aucun ancien jeton ne soit jamais rejoué.
        perdre(SessionStatus::Deconnectee, QString(), true);
    }
    m_derniereErreur.clear();
    m_flux->demarrer();
}

void SessionHermes::annulerConnexion()
{
    if (!m_flux->enCours()) {
        return;
    }
    m_flux->annuler();
    changerEtat(SessionStatus::Deconnectee);
}

void SessionHermes::adopter(const JetonsHermes &jetons)
{
    ++m_generation;
    m_jetons.effacer();
    m_jetons = jetons;
    m_identiteLue = false;
    changerEtat(SessionStatus::Echange);
    lireIdentite();
}

void SessionHermes::lireIdentite()
{
    const quint64 generation = m_generation;
    ApiRequest moi;
    moi.path = QStringLiteral("/api/auth/me");
    ApiCall *appel = m_client->send(moi);
    connect(appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        const QJsonObject identite = reponse.json.object();
        const QString utilisateur = identite.value(QStringLiteral("user_id")).toString();
        if (utilisateur.isEmpty() || utilisateur != m_jetons.utilisateur) {
            perdre(SessionStatus::Refusee,
                   QStringLiteral("L'identité rendue par Hermes ne correspond pas aux jetons reçus : "
                                  "connexion refusée."),
                   true);
            return;
        }
        m_nomAffiche = identite.value(QStringLiteral("display_name")).toString();
        m_courriel = identite.value(QStringLiteral("email")).toString();
        if (memoriser()) {
            ecrireCoffre(m_jetons);
        }
        etablir();
    });
    connect(appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation || erreur.kind() == ApiFailure::Cancelled) {
            return;
        }
        perdre(SessionStatus::Refusee,
               QStringLiteral("Identité illisible : %1").arg(erreur.message()), false);
    });
}

void SessionHermes::etablir()
{
    m_identiteLue = true;
    m_echecsConsecutifs = 0;
    m_premierEchec = QDateTime();
    m_recul.reset();
    if (m_jetons.rafraichissement.isEmpty()) {
        setAvisCoffre(QStringLiteral("Hermes n'a remis aucun jeton de rafraîchissement : la session "
                                     "prendra fin à l'échéance du jeton d'accès (%1).")
                          .arg(expiration()));
    }
    planifierRafraichissement();
    changerEtat(SessionStatus::Connectee);
    emit identiteChange();
    emit sessionEtablie();
}

void SessionHermes::restaurer()
{
    if (!m_client->isConfigured()) {
        changerEtat(SessionStatus::NonConfiguree);
        return;
    }
    m_serveur = m_client->baseUrl();
    if (m_flux->enCours() || m_rafraichissementEnVol || !m_jetons.estVide()) {
        return;
    }
    if (!memoriser()) {
        changerEtat(SessionStatus::Deconnectee);
        return;
    }
    EntreeJetons entree;
    bool introuvable = false;
    const VaultResult lecture = m_coffre.relire(m_serveur, fournisseurAttendu(), entree, &introuvable);
    if (!lecture.ok) {
        if (!introuvable) {
            setAvisCoffre(QStringLiteral("Connexion mémorisée inutilisable : %1.").arg(lecture.reason));
        }
        changerEtat(SessionStatus::Deconnectee);
        return;
    }
    m_jetons.effacer();
    m_jetons.rafraichissement = entree.jeton;
    m_jetons.fournisseur = entree.fournisseur;
    m_jetons.utilisateur = entree.utilisateur;
    entree.effacer();
    m_identiteLue = false;
    rafraichir();
}

// --- Rafraîchissement -----------------------------------------------------------

void SessionHermes::planifierRafraichissement()
{
    m_minuterie->stop();
    if (!m_jetons.expireLe.isValid()) {
        return;
    }
    // Cinq minutes avant l'échéance, jamais moins de 30 s. Sans jeton de rafraîchissement,
    // à l'échéance elle-même : la session prend fin, et l'écran le dit.
    qint64 secondes = maintenant().secsTo(m_jetons.expireLe);
    if (!m_jetons.rafraichissement.isEmpty()) {
        secondes -= 300;
    }
    secondes = std::clamp<qint64>(secondes, 30, 24 * 3600);
    m_minuterie->start(std::chrono::milliseconds(secondes * 1000));
}

void SessionHermes::rafraichir()
{
    if (m_rafraichissementEnVol) {
        return; // Vol unique : l'appel en cours servira tout le monde.
    }
    if (m_jetons.rafraichissement.isEmpty()) {
        const QString raison = QStringLiteral(
            "Session expirée : aucun jeton de rafraîchissement n'est détenu ; reconnectez-vous.");
        m_client->refreshFinished(false, ApiError(ApiFailure::Unauthorized, raison, 401));
        if (!m_jetons.estVide()) {
            perdre(SessionStatus::Expiree, raison, false);
        }
        return;
    }
    m_minuterie->stop();
    m_relance->stop();
    m_rafraichissementEnVol = true;
    const quint64 generation = m_generation;
    changerEtat(SessionStatus::Rafraichissement);

    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = QStringLiteral("/auth/native/refresh");
    requete.publicEndpoint = true;
    requete.timeout = std::chrono::milliseconds(30000);
    requete.body = QJsonDocument(QJsonObject{
        {QStringLiteral("refresh_token"), QString::fromUtf8(m_jetons.rafraichissement)},
        {QStringLiteral("provider"), fournisseurAttendu()},
    });
    m_appelRafraichissement = m_client->send(requete);
    connect(m_appelRafraichissement, &ApiCall::succeeded, this,
            [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        m_rafraichissementEnVol = false;
        JetonsHermes nouveaux;
        const QString refus = JetonsHermes::lire(reponse.json.object(), fournisseurAttendu(),
                                                 maintenant(), nouveaux,
                                                 JetonsHermes::dateHttp(reponse.header("date")));
        if (!refus.isEmpty()) {
            // Réponse 200 : Hermes a DÉJÀ fait tourner le jeton, celui du coffre est consommé.
            // Le garder le ferait rejouer au prochain démarrage (Authelia révoquerait la
            // famille de jetons, Hermes rendrait 503 en boucle) : l'entrée est effacée.
            const QString raison = refus + QStringLiteral(" Le jeton mémorisé est effacé : reconnectez-vous.");
            m_client->refreshFinished(false, ApiError(ApiFailure::InvalidResponse, raison));
            perdre(SessionStatus::Refusee, raison, true);
            return;
        }
        if (!m_jetons.utilisateur.isEmpty() && nouveaux.utilisateur != m_jetons.utilisateur) {
            nouveaux.effacer();
            const QString raison = QStringLiteral("Le rafraîchissement a rendu une autre identité : "
                                                  "session refusée.");
            m_client->refreshFinished(false, ApiError(ApiFailure::InvalidResponse, raison));
            perdre(SessionStatus::Refusee, raison, true);
            return;
        }
        if (nouveaux.rafraichissement.isEmpty()) {
            // Fournisseur qui ne fait pas tourner le jeton (self_hosted le reprend alors tel quel).
            nouveaux.rafraichissement =
                QByteArray(m_jetons.rafraichissement.constData(), m_jetons.rafraichissement.size());
        }
        // Le nouveau jeton est mémorisé AVANT tout usage du nouveau jeton d'accès.
        if (memoriser()) {
            ecrireCoffre(nouveaux);
        }
        m_jetons.effacer();
        m_jetons = nouveaux;
        nouveaux.effacer();
        m_echecsConsecutifs = 0;
        m_premierEchec = QDateTime();
        m_recul.reset();
        emit jetonsRenouveles();
        m_client->refreshFinished(true);
        if (!m_identiteLue) {
            changerEtat(SessionStatus::Echange);
            lireIdentite();
            return;
        }
        planifierRafraichissement();
        changerEtat(SessionStatus::Connectee);
        emit identiteChange();
    });
    connect(m_appelRafraichissement, &ApiCall::failed, this,
            [this, generation](const ApiError &erreur) {
        if (generation != m_generation) {
            return;
        }
        m_rafraichissementEnVol = false;
        echecRafraichissement(erreur);
    });
}

void SessionHermes::echecRafraichissement(const ApiError &erreur)
{
    if (erreur.kind() == ApiFailure::Cancelled) {
        m_client->refreshFinished(false, erreur);
        return;
    }
    if (erreur.httpStatus() == 401) {
        // Tous les fournisseurs refusent le jeton : `session_expired` (routes.py).
        const QString raison = QStringLiteral(
            "Session expirée chez le fournisseur d'identité : reconnectez-vous.");
        m_client->refreshFinished(false, ApiError(ApiFailure::Unauthorized, raison, 401));
        perdre(SessionStatus::Expiree, raison, true);
        return;
    }
    const bool fournisseur = erreur.httpStatus() == 503
        || erreur.kind() == ApiFailure::IdentityProviderUnavailable;
    const bool reseau = erreur.httpStatus() == 0
        && (erreur.kind() == ApiFailure::Network || erreur.kind() == ApiFailure::Timeout);
    if (fournisseur || reseau) {
        // Le jeton est GARDÉ : un 503 peut venir d'un fournisseur en panne comme d'une
        // réutilisation détectée ; l'effacer ici détruirait une session peut-être saine.
        ++m_echecsConsecutifs;
        const QDateTime instant = maintenant();
        if (!m_premierEchec.isValid()) {
            m_premierEchec = instant;
        }
        const auto delai = m_recul.nextDelay();
        const int secondes = static_cast<int>(std::ceil(static_cast<double>(delai.count()) / 1000.0));
        QString message;
        if (fournisseur && m_echecsConsecutifs >= 3 && m_premierEchec.secsTo(instant) >= 120) {
            message = QStringLiteral("Le fournisseur d'identité refuse le rafraîchissement depuis %1. "
                                     "S'il est en ligne, reconnectez-vous : le jeton mémorisé sera "
                                     "effacé.")
                          .arg(m_premierEchec.toLocalTime().toString(QStringLiteral("HH:mm")));
        } else if (fournisseur) {
            message = QStringLiteral("Fournisseur d'identité injoignable ; nouvel essai dans %1 s. "
                                     "Le jeton est gardé.")
                          .arg(secondes);
        } else {
            message = QStringLiteral("Hermes injoignable ; nouvel essai dans %1 s. Le jeton est gardé.")
                          .arg(secondes);
        }
        m_client->refreshFinished(false, erreur);
        changerEtat(fournisseur ? SessionStatus::FournisseurInjoignable : SessionStatus::HorsLigne,
                    message);
        m_relance->start(delai);
        return;
    }
    m_client->refreshFinished(false, erreur);
    perdre(SessionStatus::Refusee,
           QStringLiteral("Rafraîchissement refusé : %1").arg(erreur.message()), false);
}

void SessionHermes::reessayer()
{
    if (m_rafraichissementEnVol || m_jetons.rafraichissement.isEmpty()) {
        return;
    }
    m_relance->stop();
    rafraichir();
}

void SessionHermes::ecrireCoffre(const JetonsHermes &jetons)
{
    if (jetons.rafraichissement.isEmpty()) {
        return;
    }
    const VaultResult ecriture = m_coffre.memoriser(m_serveur, jetons.fournisseur, jetons.utilisateur,
                                                    jetons.rafraichissement);
    if (ecriture.ok) {
        setAvisCoffre(QString());
        return;
    }
    // L'entrée existante porte désormais un jeton périmé : la garder ferait rejouer un ancien
    // jeton au prochain démarrage, et Authelia révoquerait la session.
    const VaultResult effacement = m_coffre.oublier(m_serveur);
    setAvisCoffre(QStringLiteral("Connexion non mémorisée : %1.%2")
                      .arg(ecriture.reason,
                           effacement.ok ? QString()
                                         : QStringLiteral(" L'ancienne entrée n'a pas pu être "
                                                          "effacée : %1.")
                                               .arg(effacement.reason)));
}

// --- Fin de session -------------------------------------------------------------

void SessionHermes::seDeconnecter()
{
    m_flux->annuler();
    QByteArray jeton(m_jetons.rafraichissement.constData(), m_jetons.rafraichissement.size());
    if (!jeton.isEmpty() && m_client->isConfigured()) {
        ApiRequest deconnexion;
        deconnexion.method = QByteArrayLiteral("POST");
        deconnexion.path = QStringLiteral("/auth/logout");
        deconnexion.publicEndpoint = true;
        deconnexion.redirectionAttendue = true;
        deconnexion.cookieDeconnexion = jeton;
        deconnexion.timeout = std::chrono::milliseconds(15000);
        ApiCall *appel = m_client->send(deconnexion);
        connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
            m_bilanDeconnexion = QStringLiteral("Révocation demandée à Hermes le %1 (réponse %2).")
                                     .arg(QDateTime::currentDateTime().toString(QStringLiteral("dd/MM/yyyy HH:mm")))
                                     .arg(reponse.httpStatus);
            emit avisCoffreChange();
        });
        connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
            m_bilanDeconnexion = QStringLiteral("Révocation non confirmée par Hermes (%1) : le jeton "
                                                "reste valable chez le fournisseur jusqu'à son "
                                                "expiration.")
                                     .arg(erreur.message());
            emit avisCoffreChange();
        });
    } else {
        m_bilanDeconnexion = QStringLiteral("Aucun jeton à révoquer : session oubliée sur ce poste.");
        emit avisCoffreChange();
    }
    CredentialVault::wipe(jeton);
    perdre(SessionStatus::Deconnectee, QString(), true);
}

void SessionHermes::perdre(SessionStatus::State etat, const QString &raison, bool oublierCoffre)
{
    ++m_generation;
    m_minuterie->stop();
    m_relance->stop();
    if (m_rafraichissementEnVol && m_appelRafraichissement) {
        m_appelRafraichissement->abort();
    }
    m_rafraichissementEnVol = false;
    m_client->refreshFinished(false, ApiError(ApiFailure::Unauthorized,
                                              raison.isEmpty() ? QStringLiteral("session fermée")
                                                               : raison,
                                              401));
    if (oublierCoffre) {
        const VaultResult effacement = m_coffre.oublier(m_serveur);
        if (!effacement.ok) {
            setAvisCoffre(QStringLiteral("Entrée du coffre non effacée : %1").arg(effacement.reason));
        }
    }
    effacerSession();
    changerEtat(etat, raison);
    emit identiteChange();
    emit sessionPerdue(raison.isEmpty() ? QStringLiteral("Session fermée sur ce poste.") : raison);
}

void SessionHermes::effacerSession()
{
    m_jetons.effacer();
    m_nomAffiche.clear();
    m_courriel.clear();
    m_identiteLue = false;
    m_echecsConsecutifs = 0;
    m_premierEchec = QDateTime();
    m_recul.reset();
}

bool SessionHermes::copierLienConnexion()
{
    const QUrl lien = m_flux->lienAutorisation();
    if (lien.isEmpty() || !qobject_cast<QGuiApplication *>(QCoreApplication::instance())) {
        return false;
    }
    QGuiApplication::clipboard()->setText(QString::fromLatin1(lien.toEncoded()));
    return true;
}

} // namespace acp
