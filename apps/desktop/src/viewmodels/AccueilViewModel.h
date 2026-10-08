// Accueil de la station (cahier P8 § 7.1 ; Accueil agrégé de l'étape P7, cahier P7 § 8).
//
// Sources, relues toutes les 15 s tant que la page est affichée :
//   - `GET /v1/accueil` du greffon : UNE lecture, la même que l'Accueil du navigateur (forme
//     partagée : hermes/tests/outils/fixtures_accueil/accueil.json) — à traiter par vous, chez
//     Hermes, discussions en attente, projets en cours, exécutant, quotas, canal de notifications,
//     pause générale. Un bloc illisible vaut `null` avec sa raison dans `illisibles` : la carte le
//     dit (« Bloc illisible : … »), jamais une valeur par défaut ni un zéro inventé ;
//   - `GET /api/sessions?limit=5&offset=0&order=recent` de Hermes : discussions récentes
//     (même appel que la page d'accueil web) ;
//   - `GET /v1/meta` du greffon (dès que la compatibilité est branchée, setCompatibilite) : la
//     carte « Hermes » (version en service, verdict, alertes), datée « Lu à » comme les autres.
//
// Chaque carte est une table de valeurs DÉJÀ libellées en français, aux clés fixes : une
// valeur absente ou d'un autre type vaut « Inconnu ». Un échec de lecture garde la dernière
// valeur, datée, avec l'erreur à côté.
//
// Gestes : « Mettre en pause » / « Reprendre » Hermes (pause générale) → `POST /v1/pause` après
// confirmation de la page ; « Envoyer une notification de test » → `POST /v1/notifications/test`,
// offert seulement si un canal est configuré. Le refus du greffon (409 `crochets`,
// `notifications`…) est rendu tel quel.

#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QVariantMap>

#include <chrono>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class CompatibiliteHermes;
class Sondage;

class AccueilViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(bool lue READ lue NOTIFY accueilChange)
    Q_PROPERTY(QVariantMap carteATraiter READ carteATraiter NOTIFY accueilChange)
    Q_PROPERTY(QVariantMap carteProjets READ carteProjets NOTIFY accueilChange)
    Q_PROPERTY(JsonListModel *projetsEnCours READ projetsEnCours CONSTANT)
    Q_PROPERTY(QVariantMap carteExecutant READ carteExecutant NOTIFY accueilChange)
    Q_PROPERTY(QVariantMap carteQuotas READ carteQuotas NOTIFY accueilChange)
    Q_PROPERTY(QVariantMap carteNotifications READ carteNotifications NOTIFY accueilChange)
    Q_PROPERTY(QVariantMap cartePause READ cartePause NOTIFY accueilChange)
    Q_PROPERTY(JsonListModel *sessions READ sessions CONSTANT)
    Q_PROPERTY(QString lectureAccueil READ lectureAccueil NOTIFY lectureChange)
    Q_PROPERTY(QString erreurAccueil READ erreurAccueil NOTIFY lectureChange)
    Q_PROPERTY(QString lectureSessions READ lectureSessions NOTIFY lectureChange)
    Q_PROPERTY(QString erreurSessions READ erreurSessions NOTIFY lectureChange)
    Q_PROPERTY(bool sessionsLues READ sessionsLues NOTIFY lectureChange)

public:
    AccueilViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                     QObject *parent = nullptr);
    ~AccueilViewModel() override;

    /*! Branche la compatibilité : `/v1/meta` est alors relu avec les autres sources. */
    void setCompatibilite(CompatibiliteHermes *compatibilite);
    /*! Intervalle des lectures de la page (15 s ; réglable pour les tests). */
    void setIntervalle(std::chrono::milliseconds intervalle);

    [[nodiscard]] bool lue() const { return m_lue; }
    [[nodiscard]] const QVariantMap &carteATraiter() const { return m_carteATraiter; }
    [[nodiscard]] const QVariantMap &carteProjets() const { return m_carteProjets; }
    [[nodiscard]] JsonListModel *projetsEnCours() const { return m_projetsEnCours; }
    [[nodiscard]] const QVariantMap &carteExecutant() const { return m_carteExecutant; }
    [[nodiscard]] const QVariantMap &carteQuotas() const { return m_carteQuotas; }
    [[nodiscard]] const QVariantMap &carteNotifications() const { return m_carteNotifications; }
    [[nodiscard]] const QVariantMap &cartePause() const { return m_cartePause; }
    [[nodiscard]] JsonListModel *sessions() const { return m_sessions; }

    [[nodiscard]] QString lectureAccueil() const;
    [[nodiscard]] QString erreurAccueil() const;
    [[nodiscard]] QString lectureSessions() const;
    [[nodiscard]] QString erreurSessions() const;
    [[nodiscard]] bool sessionsLues() const { return m_sessionsLues; }

    /*! Relit toutes les sources tout de suite. */
    Q_INVOKABLE void actualiser();
    /*! Engage (vrai) ou lève (faux) la pause générale de Hermes ; raison facultative. */
    Q_INVOKABLE void basculerPause(bool generale, const QString &raison);
    /*! « Envoyer une notification de test » (canal configuré seulement). */
    Q_INVOKABLE void envoyerNotificationDeTest();

    // --- Fonctions pures (tests) : chacune lit le document entier de `GET /v1/accueil` ----------
    /*!
        Carte « À traiter par vous » : compteurs du greffon, plus les `discussions` en attente lues
        par la passerelle (-1 : inconnues, le total le dit ; « Rien n'attend votre décision »
        seulement si elles sont connues et que rien n'attend).
    */
    [[nodiscard]] static QVariantMap construireCarteATraiter(const QJsonObject &accueil, int discussions = -1);
    [[nodiscard]] static QVariantMap construireCarteProjets(const QJsonObject &accueil);
    [[nodiscard]] static QJsonArray construireProjetsEnCours(const QJsonObject &accueil);
    [[nodiscard]] static QVariantMap construireCarteExecutant(const QJsonObject &accueil);
    [[nodiscard]] static QVariantMap construireCarteQuotas(const QJsonObject &accueil);
    [[nodiscard]] static QVariantMap construireCarteNotifications(const QJsonObject &accueil);
    [[nodiscard]] static QVariantMap construireCartePause(const QJsonObject &accueil);
    [[nodiscard]] static QJsonArray construireSessions(const QJsonObject &page);

signals:
    void accueilChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lireAccueil(const QJsonObject &accueil);
    [[nodiscard]] QList<Sondage *> sondages() const;

    ApiClient *m_client = nullptr;
    ClientGreffonPoste *m_greffon = nullptr;
    Sondage *m_accueil = nullptr;
    Sondage *m_sondageSessions = nullptr;
    Sondage *m_meta = nullptr; //!< `/v1/meta`, une fois la compatibilité branchée.
    CompatibiliteHermes *m_compatibilite = nullptr;
    JsonListModel *m_projetsEnCours = nullptr;
    JsonListModel *m_sessions = nullptr;
    bool m_lue = false;
    QVariantMap m_carteATraiter;
    QJsonObject m_dernierAccueil;
    QVariantMap m_carteProjets;
    QVariantMap m_carteExecutant;
    QVariantMap m_carteQuotas;
    QVariantMap m_carteNotifications;
    QVariantMap m_cartePause;
    bool m_sessionsLues = false;
};

} // namespace acp
