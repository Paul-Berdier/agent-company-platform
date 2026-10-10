// Navigateur de test : il suit la redirection 302 du faux Hermes jusqu'à l'écouteur de
// bouclage de la station, comme le navigateur système, sans cookie ni redirection automatique.

#pragma once

#include "auth/NativeAuthFlow.h"

#include <QHash>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

#include <functional>

namespace acp::test {

//! Navigateur de test : suit la redirection de Hermes jusqu'au bouclage, sans cookie.
class Navigateur
{
public:
    QNetworkAccessManager reseau;
    bool visiterBouclage = true;
    QList<QByteArray> cheminsPrealables; //!< Visités sur le bouclage avant le rappel.
    std::function<QUrl(const QUrl &)> alterer;

    QUrl lienRecu;
    QUrl bouclageVisite;
    int statutBouclage = 0;
    QByteArray pageBouclage;
    QHash<QByteArray, QByteArray> entetesBouclage;
    QList<int> statutsPrealables;
    bool termine = false;

    NativeAuthFlow::OuvreurNavigateur ouvreur()
    {
        return [this](const QUrl &lien) {
            lienRecu = lien;
            QTimer::singleShot(0, &reseau, [this, lien] { suivre(lien); });
            return true;
        };
    }

private:
    static QNetworkRequest requete(const QUrl &url)
    {
        QNetworkRequest r(url);
        r.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                       QVariant::fromValue(QNetworkRequest::ManualRedirectPolicy));
        return r;
    }

    void suivre(const QUrl &lien)
    {
        QNetworkReply *autorisation = reseau.get(requete(lien));
        QObject::connect(autorisation, &QNetworkReply::finished, autorisation, [this, autorisation] {
            autorisation->deleteLater();
            const QUrl location = QUrl::fromEncoded(autorisation->rawHeader("Location"));
            if (!visiterBouclage || location.isEmpty()) {
                termine = true;
                return;
            }
            bouclageVisite = alterer ? alterer(location) : location;
            visiterPrealables(0);
        });
    }

    void visiterPrealables(int index)
    {
        if (index >= cheminsPrealables.size()) {
            visiterRappel();
            return;
        }
        QUrl prealable = bouclageVisite;
        prealable.setPath(QString::fromLatin1(cheminsPrealables.at(index)));
        prealable.setQuery(QString());
        QNetworkReply *reponse = reseau.get(requete(prealable));
        QObject::connect(reponse, &QNetworkReply::finished, reponse, [this, reponse, index] {
            reponse->deleteLater();
            statutsPrealables.append(reponse->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt());
            visiterPrealables(index + 1);
        });
    }

    void visiterRappel()
    {
        QNetworkReply *rappel = reseau.get(requete(bouclageVisite));
        QObject::connect(rappel, &QNetworkReply::finished, rappel, [this, rappel] {
            rappel->deleteLater();
            statutBouclage = rappel->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            pageBouclage = rappel->readAll();
            for (const auto &[nom, valeur] : rappel->rawHeaderPairs()) {
                entetesBouclage.insert(nom.toLower(), valeur);
            }
            termine = true;
        });
    }
};

} // namespace acp::test
