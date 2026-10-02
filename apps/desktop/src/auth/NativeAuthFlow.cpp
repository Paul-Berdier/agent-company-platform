#include "auth/NativeAuthFlow.h"

#include "api/ApiClient.h"
#include "auth/EcouteurBouclage.h"
#include "storage/CredentialVault.h"

#include <QDesktopServices>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QTimer>

namespace acp {

NativeAuthFlow::NativeAuthFlow(ApiClient *client, QObject *parent)
    : QObject(parent)
    , m_client(client)
    , m_ecouteur(new EcouteurBouclage(this))
    , m_delai(new QTimer(this))
{
    m_delai->setSingleShot(true);
    connect(m_delai, &QTimer::timeout, this, [this] {
        echouer(QStringLiteral("La connexion a expiré : aucune réponse du navigateur dans le "
                               "délai imparti. Recommencez depuis la station."));
    });
    connect(m_ecouteur, &EcouteurBouclage::codeRecu, this, [this](const QByteArray &code) {
        if (m_etape != Etape::AttenteNavigateur) {
            return;
        }
        m_delai->stop();
        echanger(QByteArray(code.constData(), code.size()));
    });
    connect(m_ecouteur, &EcouteurBouclage::refuse, this, [this](const QString &raison) {
        if (m_etape == Etape::AttenteNavigateur) {
            echouer(raison);
        }
    });
}

NativeAuthFlow::~NativeAuthFlow()
{
    m_ecouteur->fermer();
    m_paire.effacer();
}

void NativeAuthFlow::setOuvreurNavigateur(OuvreurNavigateur ouvreur)
{
    m_ouvreur = std::move(ouvreur);
}

void NativeAuthFlow::setDelaiAttente(std::chrono::milliseconds delai)
{
    m_delaiAttente = delai;
}

void NativeAuthFlow::setHorloge(Horloge horloge)
{
    m_horloge = std::move(horloge);
}

QDateTime NativeAuthFlow::maintenant() const
{
    return m_horloge ? m_horloge() : QDateTime::currentDateTimeUtc();
}

QUrl NativeAuthFlow::redirectUri() const
{
    return m_ecouteur->redirectUri();
}

int NativeAuthFlow::secondesRestantes() const
{
    if (m_etape != Etape::AttenteNavigateur || !m_finAttente.isValid()) {
        return 0;
    }
    return static_cast<int>(qMax<qint64>(0, QDateTime::currentDateTimeUtc().secsTo(m_finAttente)));
}

void NativeAuthFlow::changerEtape(Etape etape)
{
    if (m_etape == etape) {
        return;
    }
    m_etape = etape;
    emit etapeChangee();
}

void NativeAuthFlow::demarrer()
{
    if (enCours()) {
        return;
    }
    if (!m_client->isConfigured()) {
        emit echoue(QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return;
    }
    const quint64 generation = ++m_generation;
    m_avertissement.clear();
    changerEtape(Etape::Prerequis);

    ApiRequest sante;
    sante.path = QStringLiteral("/api/health");
    sante.publicEndpoint = true;
    sante.timeout = std::chrono::milliseconds(15000);
    m_appel = m_client->send(sante);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        const QJsonValue authRequise = reponse.json.object().value(QStringLiteral("auth_required"));
        if (!authRequise.isBool() || !authRequise.toBool()) {
            echouer(QStringLiteral("Ce Hermes n'exige aucune connexion : il n'est pas déployé "
                                   "comme ACP l'attend. Connexion refusée."));
            return;
        }
        lireFournisseurs(generation);
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation == m_generation) {
            echouer(QStringLiteral("Hermes injoignable : %1").arg(erreur.message()));
        }
    });
}

void NativeAuthFlow::lireFournisseurs(quint64 generation)
{
    ApiRequest fournisseurs;
    fournisseurs.path = QStringLiteral("/api/auth/providers");
    fournisseurs.publicEndpoint = true;
    fournisseurs.timeout = std::chrono::milliseconds(15000);
    m_appel = m_client->send(fournisseurs);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        const QJsonArray liste = reponse.json.object().value(QStringLiteral("providers")).toArray();
        bool trouve = false;
        for (const QJsonValue &entree : liste) {
            if (entree.toObject().value(QStringLiteral("name")).toString()
                == QLatin1String(kFournisseur)) {
                trouve = true;
            }
        }
        if (!trouve) {
            echouer(QStringLiteral("Le fournisseur OIDC auto-hébergé (« self-hosted ») n'est pas "
                                   "configuré sur ce serveur. Connexion refusée."));
            return;
        }
        if (liste.size() > 1) {
            // La portée gérée d'ACP n'en déclare qu'un : l'écart est signalé, et
            // self-hosted reste choisi explicitement.
            m_avertissement = QStringLiteral("Ce serveur déclare %1 fournisseurs de connexion ; "
                                             "« self-hosted » est choisi explicitement.")
                                  .arg(liste.size());
        }
        ouvrirAttente();
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation == m_generation) {
            echouer(QStringLiteral("Fournisseurs de connexion illisibles : %1").arg(erreur.message()));
        }
    });
}

void NativeAuthFlow::ouvrirAttente()
{
    m_paire = PairePkce::generer();
    QString raison;
    if (!m_ecouteur->ouvrir(m_paire.etat(), &raison)) {
        echouer(raison);
        return;
    }
    const QByteArray redirection = m_ecouteur->redirectUri().toEncoded();
    QByteArray requete;
    requete += "provider=" + QUrl::toPercentEncoding(QString::fromLatin1(kFournisseur));
    requete += "&code_challenge=" + QUrl::toPercentEncoding(QString::fromLatin1(m_paire.defi()));
    requete += "&code_challenge_method=S256";
    requete += "&redirect_uri=" + QUrl::toPercentEncoding(QString::fromLatin1(redirection));
    requete += "&state=" + QUrl::toPercentEncoding(QString::fromLatin1(m_paire.etat()));
    m_lien = m_client->resolve(QStringLiteral("/auth/native/authorize"));
    m_lien.setQuery(QString::fromLatin1(requete), QUrl::StrictMode);
    CredentialVault::wipe(requete);

    m_finAttente = QDateTime::currentDateTimeUtc().addMSecs(m_delaiAttente.count());
    m_delai->start(m_delaiAttente);
    changerEtape(Etape::AttenteNavigateur);
    m_navigateurOuvert = m_ouvreur ? m_ouvreur(m_lien) : QDesktopServices::openUrl(m_lien);
    emit etapeChangee();
}

void NativeAuthFlow::echanger(QByteArray code)
{
    const quint64 generation = m_generation;
    changerEtape(Etape::Echange);
    ApiRequest echange;
    echange.method = QByteArrayLiteral("POST");
    echange.path = QStringLiteral("/auth/native/token");
    echange.publicEndpoint = true;
    echange.body = QJsonDocument(QJsonObject{
        {QStringLiteral("code"), QString::fromLatin1(code)},
        {QStringLiteral("code_verifier"), QString::fromLatin1(m_paire.verificateur())},
    });
    CredentialVault::wipe(code);
    m_appel = m_client->send(echange);
    connect(m_appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generation) {
            return;
        }
        JetonsHermes jetons;
        const QString refus = JetonsHermes::lire(reponse.json.object(),
                                                 QString::fromLatin1(kFournisseur), maintenant(),
                                                 jetons, JetonsHermes::dateHttp(reponse.header("date")));
        if (!refus.isEmpty()) {
            echouer(refus);
            return;
        }
        terminer();
        emit reussi(jetons);
        jetons.effacer();
    });
    connect(m_appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generation) {
            return;
        }
        if (erreur.httpStatus() == 400) {
            // routes.py : code inconnu, expiré, rejoué ou PKCE faux, sans distinction.
            echouer(QStringLiteral("Code de connexion refusé ou expiré ; recommencez depuis la "
                                   "station."));
            return;
        }
        echouer(QStringLiteral("Échange du code de connexion impossible : %1").arg(erreur.message()));
    });
}

void NativeAuthFlow::terminer()
{
    ++m_generation;
    m_delai->stop();
    m_ecouteur->fermer();
    m_paire.effacer();
    m_lien = QUrl();
    m_finAttente = QDateTime();
    m_navigateurOuvert = false;
    if (m_appel) {
        m_appel->abort();
        m_appel = nullptr;
    }
    changerEtape(Etape::Inactif);
}

void NativeAuthFlow::echouer(const QString &raison)
{
    terminer();
    emit echoue(raison);
}

void NativeAuthFlow::annuler()
{
    if (enCours()) {
        terminer();
    }
}

} // namespace acp
