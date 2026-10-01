// Compatibilité de la station avec le Hermes servi, lue dans `GET /api/plugins/acp-poste/v1/meta`.
//
// Référence : hermes/contrat/HERMES_VERSION, recopié à la compilation dans BuildConfig.h
// (version de Hermes testée, version et empreinte du contrat JSON-RPC épinglé, contrat du
// greffon). Règles (cahier P8 § 4.2) :
//
//   - `contrat` d'une autre majeure que `acp-poste/1` : REFUS, pages du greffon bloquées ;
//   - `openrpc.info_version` différent de la version épinglée : REFUS de la Discussion seule ;
//   - `openrpc.identique` faux, ou empreinte installée différente de l'empreinte épinglée par
//     la station : avertissement, Discussion maintenue ;
//   - `hermes.version` différente de la version testée : avertissement ;
//   - `alertes` non vide : nombre et détail publiés ;
//   - `/v1/meta` en 404 : greffon absent, seules Discussion et Diagnostics restent.
//
// Les étapes déployées se détectent sans supposition : `machine.executant` présent signale
// l'exécutant Railway (P6). Une clé absente reste « Inconnu », jamais devinée.

#pragma once

#include "app/QmlEnums.h"

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

namespace acp {

class ApiError;
class ClientGreffonPoste;

class CompatibiliteHermes : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int etat READ etatValeur NOTIFY change)
    Q_PROPERTY(QString libelle READ libelle NOTIFY change)
    Q_PROPERTY(QString explication READ explication NOTIFY change)
    Q_PROPERTY(bool greffonDisponible READ greffonDisponible NOTIFY change)
    Q_PROPERTY(bool discussionDisponible READ discussionDisponible NOTIFY change)
    Q_PROPERTY(QString versionHermes READ versionHermes NOTIFY change)
    Q_PROPERTY(QString versionTestee READ versionTestee NOTIFY change)
    Q_PROPERTY(QString contratRecu READ contratRecu NOTIFY change)
    Q_PROPERTY(QString versionGreffon READ versionGreffon NOTIFY change)
    Q_PROPERTY(QString empreinteOpenRpc READ empreinteOpenRpc NOTIFY change)
    Q_PROPERTY(QStringList avertissements READ avertissements NOTIFY change)
    Q_PROPERTY(QStringList alertes READ alertes NOTIFY change)
    Q_PROPERTY(bool executantPresent READ executantPresent NOTIFY change)

public:
    /*! Résultat de l'évaluation d'un document /v1/meta : fonction pure, testable seule. */
    struct Evaluation
    {
        CompatibilityStatus::State etat = CompatibilityStatus::NonVerifiee;
        QString explication;
        bool greffonDisponible = false;
        bool discussionDisponible = false;
        QString versionHermes;
        QString contratRecu;
        QString versionGreffon;
        QString empreinteOpenRpc;
        QStringList avertissements;
        QStringList alertes;
        bool executantPresent = false;
    };

    explicit CompatibiliteHermes(ClientGreffonPoste *greffon, QObject *parent = nullptr);

    /*! Évalue un document /v1/meta contre les constantes épinglées de la station. */
    [[nodiscard]] static Evaluation evaluer(const QJsonObject &meta);

    /*! Lit /v1/meta et publie l'évaluation. */
    Q_INVOKABLE void verifier();

    /*! Revient à « Non vérifiée » (session perdue, serveur changé). */
    void oublier();

    [[nodiscard]] CompatibilityStatus::State etat() const { return m_evaluation.etat; }
    [[nodiscard]] int etatValeur() const { return static_cast<int>(m_evaluation.etat); }
    [[nodiscard]] QString libelle() const;
    [[nodiscard]] const QString &explication() const { return m_evaluation.explication; }
    [[nodiscard]] bool greffonDisponible() const { return m_evaluation.greffonDisponible; }
    [[nodiscard]] bool discussionDisponible() const { return m_evaluation.discussionDisponible; }
    [[nodiscard]] QString versionHermes() const;
    [[nodiscard]] QString versionTestee() const;
    [[nodiscard]] QString contratRecu() const;
    [[nodiscard]] QString versionGreffon() const;
    [[nodiscard]] QString empreinteOpenRpc() const;
    [[nodiscard]] const QStringList &avertissements() const { return m_evaluation.avertissements; }
    [[nodiscard]] const QStringList &alertes() const { return m_evaluation.alertes; }
    [[nodiscard]] bool executantPresent() const { return m_evaluation.executantPresent; }

signals:
    void change();

private:
    void publier(Evaluation evaluation);

    ClientGreffonPoste *m_greffon = nullptr;
    Evaluation m_evaluation;
    quint64 m_generation = 0;
};

} // namespace acp
