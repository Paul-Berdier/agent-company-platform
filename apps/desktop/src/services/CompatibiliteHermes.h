// Compatibilité de la station avec le Hermes servi, lue dans `GET /api/plugins/acp-poste/v1/meta`.
//
// Référence : hermes/contrat/HERMES_VERSION, recopié à la compilation dans BuildConfig.h
// (version de Hermes testée, version et empreinte du contrat JSON-RPC épinglé, contrat du
// greffon). Règles (cahier P8 § 4.2) :
//
//   - `contrat` d'une autre majeure que `acp-poste/1` : REFUS, pages du greffon bloquées :
//     le verdict est APPLIQUÉ au client du greffon (ClientGreffonPoste::bloquer), qui refuse
//     alors toute lecture et toute écriture sans rien émettre ;
//   - `openrpc.info_version` différent de la version épinglée : REFUS de la Discussion seule ;
//   - `openrpc.identique` faux, ou empreinte installée différente de l'empreinte épinglée par
//     la station : avertissement, Discussion maintenue ;
//   - `hermes.version` différente de la version testée : avertissement ;
//   - `alertes` non vide : nombre et détail publiés ;
//   - `/v1/meta` en 404 : greffon absent, client du greffon bloqué de même : seules Discussion
//     et Diagnostics restent.
//
// Le blocage suit le dernier verdict rendu : « Compatible » ou « Compatible avec réserves » le
// lève, l'oubli (session perdue, serveur changé) aussi ; une revérification en cours ou un
// `/v1/meta` injoignable laissent le verdict précédent en place.
//
// Les étapes déployées se détectent sans supposition, d'après `machine.executant` (étape P6,
// meta.py `_resume_executant`) : clé ABSENTE = étape non déployée (« absent »), sauf base du
// greffon illisible (`machine.base` = « illisible » : « illisible ») ; `null` = étape en place
// mais aucun exécutant connu pour l'instant (« aucun ») ; objet = exécutant annoncé
// (« annonce »). Avant toute lecture de /v1/meta : « inconnu ».

#pragma once

#include "app/QmlEnums.h"

#include <QDateTime>
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
    Q_PROPERTY(QString lecture READ lecture NOTIFY change)
    Q_PROPERTY(QString erreurLecture READ erreurLecture NOTIFY change)

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
        //! « inconnu », « absent », « illisible », « aucun » ou « annonce » (voir l'en-tête).
        QString etatExecutant = QStringLiteral("inconnu");
        //! Bloc `machine.executant` tel que servi (étape P6), vide s'il est absent.
        QJsonObject executant;
        /*!
            Flux d'invalidation du greffon (clé `flux` de /v1/meta, étape P7) : « annonce » (objet avec
            un chemin), « absent » (clé absente), « illisible », « inconnu » (rien de lu). La station ne
            l'ouvre pas : elle le DIT (relecture finale de P7, constat desktop-1).
        */
        QString etatFlux = QStringLiteral("inconnu");
    };

    explicit CompatibiliteHermes(ClientGreffonPoste *greffon, QObject *parent = nullptr);

    /*! Évalue un document /v1/meta contre les constantes épinglées de la station. */
    [[nodiscard]] static Evaluation evaluer(const QJsonObject &meta);

    /*! Lit /v1/meta et publie l'évaluation. */
    Q_INVOKABLE void verifier();

    /*! Revient à « Non vérifiée » (session perdue, serveur changé). */
    void oublier();

    /*!
        Lecture de /v1/meta faite par un sondage (page d'accueil, relue toutes les 15 s) : le
        verdict suit, sans passer par « Vérification ».
    */
    void appliquerLecture(const QJsonObject &meta);
    /*!
        Échec d'une lecture de fond : 404 ⇒ greffon absent ; sinon le dernier verdict RESTE,
        daté, et l'erreur est publiée à côté (comme toute lecture de page).
    */
    void appliquerEchec(const ApiError &erreur);

    /*! « Lu à HH:MM:SS » (dernière lecture réussie de /v1/meta) ou « Jamais lu ». */
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] const QString &erreurLecture() const { return m_erreurLecture; }

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
    [[nodiscard]] const QString &etatExecutant() const { return m_evaluation.etatExecutant; }
    [[nodiscard]] const QJsonObject &executant() const { return m_evaluation.executant; }
    [[nodiscard]] const QString &etatFlux() const { return m_evaluation.etatFlux; }

signals:
    void change();

private:
    void publier(Evaluation evaluation);

    ClientGreffonPoste *m_greffon = nullptr;
    Evaluation m_evaluation;
    quint64 m_generation = 0;
    QDateTime m_luA;
    QString m_erreurLecture;
};

} // namespace acp
