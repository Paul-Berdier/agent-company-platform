#include "support/FauxHermes.h"

#include <QCryptographicHash>
#include <QDateTime>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QPointer>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTimer>

namespace acp::test {

namespace {

const char *const kTampon = "fauxHermesTampon";

QString cle(const QByteArray &methode, const QString &chemin)
{
    return QString::fromLatin1(methode) + QLatin1Char(' ') + chemin;
}

QByteArray libelleStatut(int statut)
{
    switch (statut) {
    case 200: return QByteArrayLiteral("OK");
    case 201: return QByteArrayLiteral("Created");
    case 202: return QByteArrayLiteral("Accepted");
    case 302: return QByteArrayLiteral("Found");
    case 400: return QByteArrayLiteral("Bad Request");
    case 401: return QByteArrayLiteral("Unauthorized");
    case 403: return QByteArrayLiteral("Forbidden");
    case 404: return QByteArrayLiteral("Not Found");
    case 409: return QByteArrayLiteral("Conflict");
    case 415: return QByteArrayLiteral("Unsupported Media Type");
    case 422: return QByteArrayLiteral("Unprocessable Entity");
    case 503: return QByteArrayLiteral("Service Unavailable");
    default: return QByteArrayLiteral("Statut");
    }
}

ReponseFaux refusPorte(const RequeteRecue &requete)
{
    // middleware.py `_unauth_response` : porteur présent mais refusé → session_expired.
    const bool porteur = requete.entete(QByteArrayLiteral("authorization")).startsWith("Bearer ");
    const QString raison = porteur ? QStringLiteral("invalid_or_expired_session")
                                   : QStringLiteral("no_cookie");
    return ReponseFaux::json(
        401, QJsonObject{{QStringLiteral("error"), porteur ? QStringLiteral("session_expired")
                                                           : QStringLiteral("unauthenticated")},
                         {QStringLiteral("detail"), QStringLiteral("Unauthorized")},
                         {QStringLiteral("reason"), raison},
                         {QStringLiteral("login_url"), QStringLiteral("/login")}});
}

} // namespace

QJsonObject RequeteRecue::json() const
{
    return QJsonDocument::fromJson(corps).object();
}

ReponseFaux ReponseFaux::json(int statut, const QJsonValue &valeur)
{
    ReponseFaux reponse;
    reponse.statut = statut;
    if (valeur.isObject()) {
        reponse.corps = QJsonDocument(valeur.toObject()).toJson(QJsonDocument::Compact);
    } else if (valeur.isArray()) {
        reponse.corps = QJsonDocument(valeur.toArray()).toJson(QJsonDocument::Compact);
    }
    reponse.entetes.append({QByteArrayLiteral("Content-Type"), QByteArrayLiteral("application/json")});
    return reponse;
}

ReponseFaux ReponseFaux::redirection(const QByteArray &cible)
{
    ReponseFaux reponse;
    reponse.statut = 302;
    reponse.entetes.append({QByteArrayLiteral("Location"), cible});
    return reponse;
}

QByteArray defiS256Reference(const QByteArray &verificateur)
{
    return QCryptographicHash::hash(verificateur, QCryptographicHash::Sha256)
        .toBase64(QByteArray::Base64UrlEncoding | QByteArray::OmitTrailingEquals);
}

FauxHermes::FauxHermes(QObject *parent)
    : QObject(parent)
    , m_serveur(new QTcpServer(this))
{
    connect(m_serveur, &QTcpServer::newConnection, this, &FauxHermes::accepter);
    if (!m_serveur->listen(QHostAddress(QHostAddress::LocalHost), 0)) {
        qFatal("Faux Hermes : bouclage de test indisponible");
    }
}

FauxHermes::~FauxHermes() = default;

QUrl FauxHermes::url() const
{
    return QUrl(QStringLiteral("http://127.0.0.1:%1").arg(m_serveur->serverPort()));
}

quint16 FauxHermes::port() const
{
    return m_serveur->serverPort();
}

void FauxHermes::route(const QByteArray &methode, const QString &chemin, Gestionnaire gestionnaire)
{
    m_routes.insert(cle(methode, chemin), std::move(gestionnaire));
}

int FauxHermes::compter(const QByteArray &methode, const QString &chemin) const
{
    return static_cast<int>(filtrer(methode, chemin).size());
}

QList<RequeteRecue> FauxHermes::filtrer(const QByteArray &methode, const QString &chemin) const
{
    QList<RequeteRecue> resultat;
    for (const RequeteRecue &requete : requetes) {
        if (requete.methode == methode && requete.chemin == chemin) {
            resultat.append(requete);
        }
    }
    return resultat;
}

void FauxHermes::accepter()
{
    while (m_serveur->hasPendingConnections()) {
        QTcpSocket *socket = m_serveur->nextPendingConnection();
        connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
        connect(socket, &QTcpSocket::readyRead, this, [this, socket] { lire(socket); });
    }
}

void FauxHermes::lire(QTcpSocket *socket)
{
    QByteArray tampon = socket->property(kTampon).toByteArray() + socket->readAll();
    for (;;) {
        const qsizetype finEntetes = tampon.indexOf("\r\n\r\n");
        if (finEntetes < 0) {
            break;
        }
        const QList<QByteArray> lignes = tampon.left(finEntetes).split('\n');
        RequeteRecue requete;
        const QList<QByteArray> premiere = lignes.value(0).trimmed().split(' ');
        requete.methode = premiere.value(0);
        const QUrl cible = QUrl::fromEncoded(premiere.value(1));
        requete.chemin = cible.path();
        requete.requete = QUrlQuery(cible.query(QUrl::FullyEncoded));
        qsizetype longueur = 0;
        for (qsizetype index = 1; index < lignes.size(); ++index) {
            const QByteArray ligne = lignes.at(index).trimmed();
            const qsizetype deuxPoints = ligne.indexOf(':');
            if (deuxPoints <= 0) {
                continue;
            }
            const QByteArray nom = ligne.left(deuxPoints).trimmed().toLower();
            const QByteArray valeur = ligne.mid(deuxPoints + 1).trimmed();
            requete.entetes.insert(nom, valeur);
            if (nom == "content-length") {
                longueur = valeur.toLongLong();
            }
        }
        if (tampon.size() < finEntetes + 4 + longueur) {
            break;
        }
        requete.corps = tampon.mid(finEntetes + 4, longueur);
        tampon.remove(0, finEntetes + 4 + longueur);
        requetes.append(requete);
        repondre(socket, traiter(requete));
    }
    socket->setProperty(kTampon, tampon);
}

void FauxHermes::repondre(QTcpSocket *socket, const ReponseFaux &reponse)
{
    QByteArray brut = "HTTP/1.1 " + QByteArray::number(reponse.statut) + ' '
        + libelleStatut(reponse.statut) + "\r\n";
    for (const auto &[nom, valeur] : reponse.entetes) {
        brut += nom + ": " + valeur + "\r\n";
    }
    brut += "Content-Length: " + QByteArray::number(reponse.corps.size()) + "\r\n";
    brut += "Connection: close\r\n\r\n";
    brut += reponse.corps;
    QPointer<QTcpSocket> garde(socket);
    const auto envoyer = [garde, brut] {
        if (garde && garde->state() == QAbstractSocket::ConnectedState) {
            garde->write(brut);
            garde->disconnectFromHost();
        }
    };
    if (reponse.delaiMs > 0) {
        QTimer::singleShot(reponse.delaiMs, this, envoyer);
    } else {
        envoyer();
    }
}

bool FauxHermes::estPublique(const QString &chemin) const
{
    // public_paths.py et middleware.py `_GATE_PUBLIC_PREFIXES` (extrait utile aux tests).
    return chemin == QStringLiteral("/api/health") || chemin == QStringLiteral("/api/status")
        || chemin == QStringLiteral("/api/auth/providers") || chemin.startsWith(QStringLiteral("/auth/"))
        || !chemin.startsWith(QStringLiteral("/api/"));
}

ReponseFaux FauxHermes::traiter(const RequeteRecue &requete)
{
    if (m_porte && !estPublique(requete.chemin)) {
        const QByteArray autorisation = requete.entete(QByteArrayLiteral("authorization"));
        const QByteArray jeton = autorisation.startsWith("Bearer ") ? autorisation.mid(7) : QByteArray();
        if (jeton.isEmpty() || !jetonsAccesValides.contains(jeton)) {
            return refusPorte(requete);
        }
    }
    const auto route = m_routes.constFind(cle(requete.methode, requete.chemin));
    if (route == m_routes.constEnd()) {
        return ReponseFaux::json(404, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Not Found")}});
    }
    return (*route)(requete);
}

QJsonObject FauxHermes::emettreJetons()
{
    ++m_compteur;
    const QByteArray acces = QByteArrayLiteral("acces-faux-") + QByteArray::number(m_compteur)
        + QByteArrayLiteral("-") + QByteArray::number(QDateTime::currentMSecsSinceEpoch());
    const QByteArray rafraichissement = QByteArrayLiteral("rafraichissement-faux-")
        + QByteArray::number(m_compteur);
    jetonsAccesValides.insert(acces);
    if (!jetonRafraichissementCourant.isEmpty()) {
        jetonsRafraichissementTournes.insert(jetonRafraichissementCourant);
    }
    jetonRafraichissementCourant = sansJetonRafraichissement ? QByteArray() : rafraichissement;
    return QJsonObject{
        {QStringLiteral("access_token"), QString::fromLatin1(acces)},
        {QStringLiteral("refresh_token"), QString::fromLatin1(jetonRafraichissementCourant)},
        {QStringLiteral("token_type"), typeJetonFaux ? QStringLiteral("cookie") : QStringLiteral("Bearer")},
        {QStringLiteral("expires_at"),
         QDateTime::currentSecsSinceEpoch() + static_cast<qint64>(dureeAccesSecondes)},
        {QStringLiteral("provider"), fournisseur},
        {QStringLiteral("user_id"), utilisateur},
    };
}

void FauxHermes::installerAuthentification()
{
    m_porte = true;

    route("GET", QStringLiteral("/api/health"), [this](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("ok"), true},
                                                  {QStringLiteral("version"), QStringLiteral("0.21.5")},
                                                  {QStringLiteral("auth_required"), authRequise}});
    });

    route("GET", QStringLiteral("/api/auth/providers"), [this](const RequeteRecue &) {
        return ReponseFaux::json(
            200, QJsonObject{{QStringLiteral("providers"),
                              QJsonArray{QJsonObject{{QStringLiteral("name"), fournisseur},
                                                     {QStringLiteral("display_name"), QStringLiteral("Authelia")},
                                                     {QStringLiteral("supports_password"), false}}}}});
    });

    route("GET", QStringLiteral("/auth/native/authorize"), [this](const RequeteRecue &requete) {
        const QUrlQuery &q = requete.requete;
        if (q.queryItemValue(QStringLiteral("code_challenge_method")).toUpper() != QStringLiteral("S256")) {
            return ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"), QStringLiteral("code_challenge_method must be S256")}});
        }
        dernierDefi = q.queryItemValue(QStringLiteral("code_challenge"), QUrl::FullyDecoded).toUtf8();
        dernierRedirectUri = q.queryItemValue(QStringLiteral("redirect_uri"), QUrl::FullyDecoded);
        dernierEtat = q.queryItemValue(QStringLiteral("state"), QUrl::FullyDecoded).toUtf8();
        const QUrl retour(dernierRedirectUri);
        if (dernierDefi.isEmpty()) {
            return ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"), QStringLiteral("code_challenge required")}});
        }
        if (retour.scheme() != QStringLiteral("http")
            || (retour.host() != QStringLiteral("127.0.0.1") && retour.host() != QStringLiteral("::1"))) {
            return ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"),
                QStringLiteral("native redirect_uri host must be a loopback IP literal (127.0.0.1 / ::1)")}});
        }
        if (q.queryItemValue(QStringLiteral("provider")) != fournisseur) {
            return ReponseFaux::json(404, QJsonObject{{QStringLiteral("detail"), QStringLiteral("Unknown provider")}});
        }
        ++m_compteur;
        const QByteArray code = QByteArrayLiteral("code-faux-") + QByteArray::number(m_compteur);
        m_codes.insert(code, dernierDefi);
        QUrlQuery retourRequete;
        retourRequete.addQueryItem(QStringLiteral("code"), QString::fromLatin1(code));
        if (!omettreEtat) {
            retourRequete.addQueryItem(QStringLiteral("state"),
                                       QString::fromUtf8(etatForce.isEmpty() ? dernierEtat : etatForce));
        }
        QUrl cible = retour;
        cible.setQuery(retourRequete);
        return ReponseFaux::redirection(cible.toEncoded());
    });

    route("POST", QStringLiteral("/auth/native/token"), [this](const RequeteRecue &requete) {
        const QJsonObject corps = requete.json();
        const QByteArray code = corps.value(QStringLiteral("code")).toString().toUtf8();
        const QByteArray verificateur = corps.value(QStringLiteral("code_verifier")).toString().toUtf8();
        // native_flow.redeem_code : le code est consommé AVANT la vérification PKCE.
        const QByteArray defi = m_codes.take(code);
        if (defi.isEmpty() || defi != defiS256Reference(verificateur)) {
            return ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"),
                                                       QStringLiteral("Invalid or expired authorization code.")}});
        }
        return ReponseFaux::json(200, emettreJetons());
    });

    route("POST", QStringLiteral("/auth/native/refresh"), [this](const RequeteRecue &requete) {
        const QByteArray jeton = requete.json().value(QStringLiteral("refresh_token")).toString().toUtf8();
        ReponseFaux reponse;
        if (jeton.isEmpty()) {
            reponse = ReponseFaux::json(400, QJsonObject{{QStringLiteral("detail"), QStringLiteral("refresh_token required")}});
        } else if (refresh503 > 0) {
            --refresh503;
            reponse = ReponseFaux::json(503, QJsonObject{{QStringLiteral("detail"),
                                                          QStringLiteral("Auth provider 'self-hosted' unreachable")}});
        } else if (jetonsRafraichissementTournes.contains(jeton)) {
            // Réutilisation détectée par Authelia (500) : Hermes rend 503 (identite.md § 12.1).
            reponse = ReponseFaux::json(503, QJsonObject{{QStringLiteral("detail"),
                                                          QStringLiteral("Auth provider 'self-hosted' unreachable")}});
        } else if (jeton != jetonRafraichissementCourant || refreshExpire) {
            refreshExpire = false;
            reponse = ReponseFaux::json(401, QJsonObject{{QStringLiteral("error"), QStringLiteral("session_expired")},
                                                         {QStringLiteral("detail"),
                                                          QStringLiteral("Refresh token expired or invalid; start a new sign-in.")}});
        } else {
            jetonsAccesValides.clear();
            reponse = ReponseFaux::json(200, emettreJetons());
        }
        reponse.delaiMs = delaiRefreshMs;
        return reponse;
    });

    route("POST", QStringLiteral("/auth/logout"), [this](const RequeteRecue &requete) {
        const QByteArray cookies = requete.entete(QByteArrayLiteral("cookie"));
        for (const QByteArray &morceau : cookies.split(';')) {
            const QByteArray propre = morceau.trimmed();
            if (propre.startsWith("hermes_session_rt=")) {
                const QByteArray jeton = propre.mid(18);
                jetonsRevoques.append(jeton);
                if (jeton == jetonRafraichissementCourant) {
                    jetonRafraichissementCourant.clear();
                    jetonsAccesValides.clear();
                }
            }
        }
        return ReponseFaux::redirection(QByteArrayLiteral("/login"));
    });

    route("GET", QStringLiteral("/api/auth/me"), [this](const RequeteRecue &) {
        return ReponseFaux::json(200, QJsonObject{
            {QStringLiteral("user_id"), utilisateur},
            {QStringLiteral("email"), QStringLiteral("proprietaire@exemple.invalid")},
            {QStringLiteral("display_name"), QStringLiteral("Propriétaire de test")},
            {QStringLiteral("org_id"), QString()},
            {QStringLiteral("provider"), fournisseur},
            {QStringLiteral("expires_at"),
             QDateTime::currentSecsSinceEpoch() + static_cast<qint64>(dureeAccesSecondes)}});
    });

    route("POST", QStringLiteral("/api/auth/ws-ticket"), [this](const RequeteRecue &) {
        ++m_compteur;
        const QByteArray ticket = QByteArrayLiteral("ticket-faux-") + QByteArray::number(m_compteur);
        ticketsEmis.append(ticket);
        return ReponseFaux::json(200, QJsonObject{{QStringLiteral("ticket"), QString::fromLatin1(ticket)},
                                                  {QStringLiteral("ttl_seconds"), 30}});
    });
}

} // namespace acp::test
