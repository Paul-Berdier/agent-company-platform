// Vérification de compatibilité client / serveur.
//
// Le serveur publie `GET /meta` (audit, section 9.1, point 1 — livré), dont le contrat
// fait foi : `packages/contracts/src/acp_contracts/compatibility.py`. Un serveur antérieur
// à cette route répond 404 ; le client reste donc prudent :
//
//   - il sonde les chemins candidats, dans l'ordre `/meta`, `/capabilities`, `/version`,
//     et retient le premier qui répond 200 avec un corps reconnaissable ;
//   - il s'annonce par `X-ACP-Client: desktop/<version>` : un serveur qui le juge trop
//     ancien répond 426 avec le document complet, et ce verdict du serveur l'emporte ;
//   - si les trois répondent 404, l'état est FeatureUnavailable — PAS « compatible ».
//     L'application continue de fonctionner, mais elle dit qu'elle ne sait pas, et
//     l'écran de diagnostics le montre ;
//   - si la route répond mais sans le champ de version de contrat, l'état est
//     FeatureUnavailable également, avec une raison distincte ;
//   - aucune fonction récente ne fait planter l'application quand elle manque : les
//     capacités absentes valent « Inconnu », et un écran qui en dépend affiche
//     « Indisponible pour l'instant » plutôt qu'un bouton qui fait semblant.
//
// Champs lus dans le corps (CompatibilityDocument côté serveur) :
//
//   versions.product                  version du produit, lue de VERSION côté serveur
//   versions.api_contract             version du contrat d'API, indépendante du produit
//   versions.event_schema             EVENT_SCHEMA_VERSION, « 1.0 » à la date du relevé
//   clients.desktop.minimum_version   version cliente minimale exigée pour ce client
//   capabilities.<nom>.available      capacités CALCULÉES, jamais déclarées
//   limits.<nom>                      bornes réelles du serveur

#pragma once

#include "api/ApiError.h"
#include "app/QmlEnums.h"
#include "events/EventStreamService.h"

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

namespace acp {

class ApiClient;

class CompatibilityService : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int state READ stateValue NOTIFY stateChanged)
    Q_PROPERTY(QString stateLabel READ stateLabel NOTIFY stateChanged)
    Q_PROPERTY(QString explanation READ explanation NOTIFY stateChanged)
    Q_PROPERTY(QString serverVersion READ serverVersion NOTIFY stateChanged)
    Q_PROPERTY(QString apiContractVersion READ apiContractVersion NOTIFY stateChanged)
    Q_PROPERTY(QString eventSchemaVersion READ eventSchemaVersion NOTIFY stateChanged)
    Q_PROPERTY(QString clientVersion READ clientVersion CONSTANT)
    Q_PROPERTY(QString endpointUsed READ endpointUsed NOTIFY stateChanged)
    Q_PROPERTY(bool blocking READ isBlocking NOTIFY stateChanged)

public:
    CompatibilityService(ApiClient *client, QString clientVersion, QObject *parent = nullptr);

    /*! Chemins candidats, dans l'ordre de sondage. Exposé pour les tests. */
    static const QStringList &candidateEndpoints();

    /*! Versions du schéma d'événement que ce client sait lire. */
    static const QStringList &supportedEventSchemaVersions();

    /*! Partie majeure du contrat d'API que ce client sait lire. Le contrat augmente sa
        partie majeure pour un retrait ou un changement de sens d'un champ publié. */
    static constexpr int supportedApiContractMajor = 1;

    [[nodiscard]] CompatibilityStatus::State state() const { return m_state; }
    [[nodiscard]] int stateValue() const { return static_cast<int>(m_state); }
    [[nodiscard]] QString stateLabel() const;
    [[nodiscard]] const QString &explanation() const { return m_explanation; }
    [[nodiscard]] const QString &serverVersion() const { return m_serverVersion; }
    [[nodiscard]] const QString &apiContractVersion() const { return m_apiContractVersion; }
    [[nodiscard]] const QString &eventSchemaVersion() const { return m_eventSchemaVersion; }
    [[nodiscard]] const QString &clientVersion() const { return m_clientVersion; }
    [[nodiscard]] const QString &endpointUsed() const { return m_endpointUsed; }

    /*! Vrai quand l'application doit REFUSER de travailler : client ou serveur trop
        ancien. L'indisponibilité de la route, elle, n'est jamais bloquante. */
    [[nodiscard]] bool isBlocking() const;

    /*! Bornes annoncées par le serveur, ou celles relevées par l'audit si la route
        n'annonce rien. L'origine de chaque valeur est exposée par `limitsAreAnnounced`. */
    [[nodiscard]] const StreamLimits &streamLimits() const { return m_limits; }
    [[nodiscard]] bool limitsAreAnnounced() const { return m_limitsAnnounced; }

    /*! Capacité calculée par le serveur. Renvoie `false` ET pose `known` à faux quand le
        serveur n'en dit rien : l'interface doit alors afficher « Inconnu », jamais
        « désactivé ». */
    [[nodiscard]] Q_INVOKABLE bool capability(const QString &name, bool *known = nullptr) const;
    [[nodiscard]] Q_INVOKABLE bool capabilityIsKnown(const QString &name) const;

    /*! Lance ou relance la vérification. */
    Q_INVOKABLE void check();

    /*! Évalue un document de compatibilité déjà reçu. Appelé par la sonde ; public pour
        que les tests l'éprouvent sur la forme réellement servie par l'API. */
    void evaluate(const QJsonObject &payload, const QString &endpoint);

    /*!
        Compare deux versions « majeur.mineur.correctif ».

        Renvoie -1, 0 ou 1. Un segment non numérique ou absent vaut zéro ; une version
        vide est considérée comme la plus ancienne. La fonction ne prétend PAS
        implémenter la norme SemVer complète : les suffixes de pré-publication ne sont ni
        lus ni ordonnés, et cela est documenté plutôt que deviné.
    */
    [[nodiscard]] static int compareVersions(const QString &left, const QString &right);

signals:
    void stateChanged();

private:
    void probe(int candidateIndex);
    void setState(CompatibilityStatus::State state, const QString &explanation);

    ApiClient *m_client = nullptr;
    QString m_clientVersion;

    CompatibilityStatus::State m_state = CompatibilityStatus::NotChecked;
    QString m_explanation;
    QString m_serverVersion;
    QString m_apiContractVersion;
    QString m_eventSchemaVersion;
    QString m_endpointUsed;
    QJsonObject m_capabilities;
    bool m_capabilitiesKnown = false;
    StreamLimits m_limits;
    bool m_limitsAnnounced = false;
};

} // namespace acp
