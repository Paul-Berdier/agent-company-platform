// Lecture au fil de l'eau d'un corps volumineux d'une route protégée de Hermes (archive de
// sauvegarde), remplaçant ArtifactDownload de l'ancienne station.
//
//  - les octets ne sont livrés au « puits » qu'après un statut 200 : un corps d'erreur n'est
//    jamais pris pour des données ;
//  - plafond de taille (4 Gio par défaut) contrôlé à chaque morceau ; au-delà, refus ;
//  - un refus du puits (écriture impossible) arrête le flux ;
//  - annulation propre : un seul signal terminal (`termine` ou `echoue`), jamais un silence.
//
// Aucune donnée n'est conservée par cet objet : il ne fait que relayer.

#pragma once

#include "api/ApiError.h"

#include <QByteArray>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QUrlQuery>

#include <functional>

class QNetworkReply;

namespace acp {

class ApiClient;

class TelechargementFlux : public QObject
{
    Q_OBJECT

public:
    //! Consomme un morceau ; rend faux et remplit `erreur` pour arrêter le flux.
    using Puits = std::function<bool(QByteArrayView, QString *erreur)>;

    static constexpr qint64 kPlafondDefaut = 4LL * 1024 * 1024 * 1024;

    explicit TelechargementFlux(ApiClient *client, QObject *parent = nullptr);
    ~TelechargementFlux() override;

    void setPlafond(qint64 octets) { m_plafond = octets; }
    [[nodiscard]] qint64 plafond() const { return m_plafond; }

    /*! Lance `GET <chemin>?<requete>` en porteur. Un flux déjà en cours est annulé. */
    void demarrer(const QString &chemin, const QUrlQuery &requete, Puits puits);
    /*! Annule le flux en cours ; émet `echoue` avec « Téléchargement annulé. ». */
    void annuler();

    [[nodiscard]] bool enCours() const { return !m_reponse.isNull(); }
    [[nodiscard]] qint64 recus() const { return m_recus; }

signals:
    void progression(qint64 recus, qint64 total);
    void termine(qint64 recus);
    void echoue(const QString &message);

private:
    void lire();
    void finir();
    void echouer(const QString &message);
    [[nodiscard]] int statut() const;

    ApiClient *m_client = nullptr;
    QPointer<QNetworkReply> m_reponse;
    Puits m_puits;
    qint64 m_plafond = kPlafondDefaut;
    qint64 m_recus = 0;
    QByteArray m_corpsErreur;
    bool m_fini = true;
};

} // namespace acp
