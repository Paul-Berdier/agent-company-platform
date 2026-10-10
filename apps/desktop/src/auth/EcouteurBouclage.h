// Écouteur de bouclage de la connexion native (RFC 8252 § 7.3).
//
// Il reçoit, une seule fois, la redirection que Hermes envoie au navigateur après la
// connexion : `http://127.0.0.1:<port>/rappel?code=…&state=…`. Ce qu'il garantit :
//
//  - écoute sur 127.0.0.1 seulement (IPv4), port éphémère choisi par le système ; jamais
//    `localhost` (Hermes le refuse, RFC 8252 § 8.3), jamais `::1`, jamais une interface
//    réseau ;
//  - un pair autre que 127.0.0.1 est coupé sans réponse ;
//  - en-têtes lus jusqu'à 8 Kio au plus, 10 secondes par connexion ;
//  - seule la ligne `GET /rappel?… HTTP/1.x` est interprétée ; tout autre chemin
//    (`/favicon.ico` compris) reçoit 404 sans effet sur le flux ;
//  - l'état est comparé à temps constant ; différent ou absent, le flux est ABANDONNÉ
//    (échec fermé) ; la première requête utile, valide ou non, ferme l'écouteur ;
//  - la page rendue au navigateur est statique, en français, sans aucun paramètre
//    recopié, avec `Cache-Control: no-store`, `Content-Security-Policy: default-src
//    'none'`, `Referrer-Policy: no-referrer` et `Connection: close`.
//
// Le code reçu n'est jamais journalisé ; il est remis une fois au flux, qui l'efface.

#pragma once

#include <QByteArray>
#include <QHostAddress>
#include <QObject>
#include <QString>
#include <QUrl>

#include <chrono>

class QTcpServer;
class QTcpSocket;

namespace acp {

class EcouteurBouclage : public QObject
{
    Q_OBJECT

public:
    //! Taille maximale de la ligne de requête et des en-têtes lus.
    static constexpr qsizetype kTailleMaxEntetes = 8 * 1024;
    //! Chemin de rappel annoncé à Hermes dans `redirect_uri`.
    static constexpr char kCheminRappel[] = "/rappel";

    explicit EcouteurBouclage(QObject *parent = nullptr);
    ~EcouteurBouclage() override;

    /*!
        Ouvre l'écoute sur 127.0.0.1. `etatAttendu` est copié, puis effacé à la fermeture.
        Renvoie faux, avec la raison française dans `raison`, si l'écoute est refusée.
    */
    bool ouvrir(const QByteArray &etatAttendu, QString *raison = nullptr);

    /*! Ferme l'écoute et toutes les connexions ; efface l'état attendu. Idempotent. */
    void fermer();

    [[nodiscard]] bool estOuvert() const;
    [[nodiscard]] QHostAddress adresse() const;
    [[nodiscard]] quint16 port() const;

    /*! `http://127.0.0.1:<port>/rappel`, ou une URL vide si l'écoute est fermée. */
    [[nodiscard]] QUrl redirectUri() const;

    /*! Délai de lecture d'une connexion (10 s par défaut). Réservé aux tests. */
    void setDelaiConnexion(std::chrono::milliseconds delai) { m_delaiConnexion = delai; }

signals:
    /*! Code reçu avec un état identique. L'écouteur est déjà fermé. */
    void codeRecu(const QByteArray &code);

    /*! Réponse inutilisable : état différent ou absent, erreur, code absent. Écouteur fermé. */
    void refuse(const QString &raison);

private:
    void accepterConnexions();
    void lire(QTcpSocket *socket);
    void traiterRequete(QTcpSocket *socket, const QByteArray &ligne);
    void repondre(QTcpSocket *socket, int statut, const QByteArray &motif, const QString &titre,
                  const QString &message);

    QTcpServer *m_serveur = nullptr;
    QByteArray m_etatAttendu;
    bool m_termine = false;
    std::chrono::milliseconds m_delaiConnexion{10000};
};

} // namespace acp
