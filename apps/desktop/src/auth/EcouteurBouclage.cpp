#include "auth/EcouteurBouclage.h"

#include "auth/PairePkce.h"
#include "storage/CredentialVault.h"

#include <QList>
#include <QPointer>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTimer>
#include <QUrlQuery>

namespace acp {

namespace {

const char *const kProprieteTampon = "acpTamponRappel";
const char *const kProprieteRepondu = "acpRepondu";

QHostAddress adresseBouclage()
{
    return QHostAddress(QHostAddress::LocalHost);
}

bool pairEstBouclage(const QHostAddress &pair)
{
    // L'écoute est en IPv4 seul : un pair légitime est exactement 127.0.0.1. La forme
    // IPv4 projetée (::ffff:127.0.0.1) est admise par prudence, rien d'autre.
    return pair.isEqual(adresseBouclage(), QHostAddress::ConvertV4MappedToIPv4);
}

//! Un code d'erreur rendu par le serveur, réduit à un jeton lisible : jamais recopié tel
//! quel dans un message (pas de texte arbitraire venu d'une URL).
QString jetonErreur(const QString &brut)
{
    QString propre;
    for (const QChar caractere : brut) {
        if (propre.size() >= 64) {
            break;
        }
        if (caractere.isLetterOrNumber() || caractere == QLatin1Char('_')
            || caractere == QLatin1Char('-') || caractere == QLatin1Char('.')) {
            if (caractere.unicode() < 128) {
                propre.append(caractere);
            }
        }
    }
    return propre.isEmpty() ? QStringLiteral("inconnue") : propre;
}

} // namespace

EcouteurBouclage::EcouteurBouclage(QObject *parent)
    : QObject(parent)
    , m_serveur(new QTcpServer(this))
{
    m_serveur->setMaxPendingConnections(8);
    connect(m_serveur, &QTcpServer::newConnection, this, &EcouteurBouclage::accepterConnexions);
}

EcouteurBouclage::~EcouteurBouclage()
{
    fermer();
}

bool EcouteurBouclage::ouvrir(const QByteArray &etatAttendu, QString *raison)
{
    fermer();
    if (etatAttendu.isEmpty()) {
        if (raison) {
            *raison = QStringLiteral("État de connexion vide : écoute refusée.");
        }
        return false;
    }
    if (!m_serveur->listen(adresseBouclage(), 0)) {
        if (raison) {
            *raison = QStringLiteral("Écoute sur 127.0.0.1 impossible : %1.")
                          .arg(m_serveur->errorString());
        }
        return false;
    }
    // Copie privée : effacer cette copie ne doit dépendre d'aucun autre détenteur.
    m_etatAttendu = QByteArray(etatAttendu.constData(), etatAttendu.size());
    m_termine = false;
    return true;
}

void EcouteurBouclage::fermer()
{
    if (m_serveur->isListening()) {
        m_serveur->close();
    }
    CredentialVault::wipe(m_etatAttendu);
    const QList<QTcpSocket *> connexions = findChildren<QTcpSocket *>();
    for (QTcpSocket *connexion : connexions) {
        QByteArray tampon = connexion->property(kProprieteTampon).toByteArray();
        CredentialVault::wipe(tampon);
        connexion->setProperty(kProprieteTampon, QVariant());
        if (connexion->property(kProprieteRepondu).toBool()) {
            // La page de réponse part encore : la connexion se ferme d'elle-même
            // (disconnectFromHost) une fois la page écrite.
            continue;
        }
        connexion->abort();
        connexion->deleteLater();
    }
}

bool EcouteurBouclage::estOuvert() const
{
    return m_serveur->isListening();
}

QHostAddress EcouteurBouclage::adresse() const
{
    return m_serveur->isListening() ? m_serveur->serverAddress() : QHostAddress();
}

quint16 EcouteurBouclage::port() const
{
    return m_serveur->isListening() ? m_serveur->serverPort() : 0;
}

QUrl EcouteurBouclage::redirectUri() const
{
    if (!m_serveur->isListening()) {
        return {};
    }
    QUrl url;
    url.setScheme(QStringLiteral("http"));
    // Littéral IP, jamais « localhost » : RFC 8252 § 8.3, et Hermes refuse tout autre hôte.
    url.setHost(QStringLiteral("127.0.0.1"));
    url.setPort(m_serveur->serverPort());
    url.setPath(QString::fromLatin1(kCheminRappel));
    return url;
}

void EcouteurBouclage::accepterConnexions()
{
    while (m_serveur->hasPendingConnections()) {
        QTcpSocket *connexion = m_serveur->nextPendingConnection();
        if (!connexion) {
            break;
        }
        connexion->setParent(this);
        if (m_termine || !pairEstBouclage(connexion->peerAddress())) {
            connexion->abort();
            connexion->deleteLater();
            continue;
        }
        auto *delai = new QTimer(connexion);
        delai->setSingleShot(true);
        delai->setInterval(m_delaiConnexion);
        QPointer<QTcpSocket> garde(connexion);
        connect(delai, &QTimer::timeout, this, [garde] {
            if (garde) {
                garde->abort();
                garde->deleteLater();
            }
        });
        connect(connexion, &QTcpSocket::readyRead, this, [this, garde] {
            if (garde) {
                lire(garde);
            }
        });
        connect(connexion, &QTcpSocket::disconnected, connexion, &QObject::deleteLater);
        delai->start();
    }
}

void EcouteurBouclage::lire(QTcpSocket *connexion)
{
    QByteArray tampon = connexion->property(kProprieteTampon).toByteArray();
    tampon += connexion->read(kTailleMaxEntetes + 1 - tampon.size());
    if (tampon.size() > kTailleMaxEntetes) {
        CredentialVault::wipe(tampon);
        connexion->setProperty(kProprieteTampon, QVariant());
        repondre(connexion, 431, QByteArrayLiteral("Request Header Fields Too Large"),
                 QStringLiteral("Requête refusée"),
                 QStringLiteral("En-têtes trop volumineux pour la station."));
        return;
    }
    const qsizetype finEntetes = tampon.indexOf("\r\n\r\n");
    if (finEntetes < 0) {
        connexion->setProperty(kProprieteTampon, tampon);
        return;
    }
    connexion->setProperty(kProprieteTampon, QVariant());
    QByteArray ligne = tampon.left(tampon.indexOf("\r\n"));
    CredentialVault::wipe(tampon);
    traiterRequete(connexion, ligne);
    CredentialVault::wipe(ligne);
}

void EcouteurBouclage::traiterRequete(QTcpSocket *connexion, const QByteArray &ligne)
{
    const QList<QByteArray> parties = ligne.split(' ');
    if (parties.size() != 3 || !parties.at(2).startsWith("HTTP/1.")) {
        repondre(connexion, 400, QByteArrayLiteral("Bad Request"), QStringLiteral("Requête illisible"),
                 QStringLiteral("La station n'attend ici que la redirection de connexion."));
        return;
    }
    const QUrl cible = QUrl::fromEncoded(parties.at(1), QUrl::StrictMode);
    const bool estRappel = cible.isValid() && cible.isRelative()
        && cible.path(QUrl::FullyDecoded) == QString::fromLatin1(kCheminRappel);
    if (!estRappel || parties.at(0) != "GET") {
        // /favicon.ico et tout autre chemin : aucun effet sur le flux.
        repondre(connexion, 404, QByteArrayLiteral("Not Found"), QStringLiteral("Introuvable"),
                 QStringLiteral("Cette adresse ne sert qu'à la connexion de la station."));
        return;
    }
    if (m_termine) {
        repondre(connexion, 404, QByteArrayLiteral("Not Found"), QStringLiteral("Introuvable"),
                 QStringLiteral("Cette connexion a déjà été traitée par la station."));
        return;
    }

    const QUrlQuery requete(cible.query(QUrl::FullyEncoded));
    QByteArray etat = requete.queryItemValue(QStringLiteral("state"), QUrl::FullyDecoded).toUtf8();
    const QString erreur = requete.queryItemValue(QStringLiteral("error"), QUrl::FullyDecoded);
    QByteArray code = requete.queryItemValue(QStringLiteral("code"), QUrl::FullyDecoded).toUtf8();

    // Première requête utile : le flux se termine ici, quelle qu'en soit l'issue.
    m_termine = true;
    const bool etatValide = egalATempsConstant(m_etatAttendu, etat);
    CredentialVault::wipe(etat);
    m_serveur->close();
    CredentialVault::wipe(m_etatAttendu);

    if (!etatValide) {
        CredentialVault::wipe(code);
        repondre(connexion, 400, QByteArrayLiteral("Bad Request"), QStringLiteral("Connexion refusée"),
                 QStringLiteral("Réponse inattendue (état différent). Recommencez depuis la station."));
        emit refuse(QStringLiteral("Connexion refusée : réponse inattendue (état différent ou "
                                   "absent). Recommencez depuis la station."));
        return;
    }
    if (!erreur.isEmpty()) {
        CredentialVault::wipe(code);
        repondre(connexion, 400, QByteArrayLiteral("Bad Request"), QStringLiteral("Connexion refusée"),
                 QStringLiteral("Le serveur a refusé la connexion. Recommencez depuis la station."));
        emit refuse(QStringLiteral("Connexion refusée par le serveur (erreur « %1 »). Recommencez "
                                   "depuis la station.")
                        .arg(jetonErreur(erreur)));
        return;
    }
    if (code.isEmpty()) {
        repondre(connexion, 400, QByteArrayLiteral("Bad Request"), QStringLiteral("Connexion refusée"),
                 QStringLiteral("Réponse sans code de connexion. Recommencez depuis la station."));
        emit refuse(QStringLiteral("Connexion refusée : la réponse ne porte aucun code de "
                                   "connexion. Recommencez depuis la station."));
        return;
    }
    repondre(connexion, 200, QByteArrayLiteral("OK"), QStringLiteral("Connexion transmise"),
             QStringLiteral("Connexion transmise à la station ; vous pouvez fermer cet onglet."));
    emit codeRecu(code);
    CredentialVault::wipe(code);
}

void EcouteurBouclage::repondre(QTcpSocket *connexion, int statut, const QByteArray &motif,
                                const QString &titre, const QString &message)
{
    // Page statique : aucun paramètre de la requête n'y est recopié.
    const QByteArray corps =
        QStringLiteral("<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
                       "<title>%1</title></head><body><h1>%1</h1><p>%2</p></body></html>")
            .arg(titre.toHtmlEscaped(), message.toHtmlEscaped())
            .toUtf8();
    QByteArray reponse;
    reponse += "HTTP/1.1 " + QByteArray::number(statut) + ' ' + motif + "\r\n";
    reponse += "Content-Type: text/html; charset=utf-8\r\n";
    reponse += "Content-Length: " + QByteArray::number(corps.size()) + "\r\n";
    reponse += "Cache-Control: no-store\r\n";
    reponse += "Pragma: no-cache\r\n";
    reponse += "Content-Security-Policy: default-src 'none'\r\n";
    reponse += "Referrer-Policy: no-referrer\r\n";
    reponse += "X-Content-Type-Options: nosniff\r\n";
    reponse += "Connection: close\r\n\r\n";
    reponse += corps;
    connexion->setProperty(kProprieteRepondu, true);
    connexion->write(reponse);
    connexion->disconnectFromHost();
}

} // namespace acp
