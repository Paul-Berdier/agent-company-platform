// Accueil de la station (cahier P8 § 7.1).
//
// Sources, relues toutes les 15 s tant que la page est affichée :
//   - `GET /v1/projets` du greffon : projets, poste, pause générale, questions ouvertes ;
//   - `GET /v1/quotas` du greffon : la voie la plus entamée ;
//   - `GET /api/sessions?limit=5&offset=0&order=recent` de Hermes : discussions récentes
//     (même appel que la page d'accueil web).
//   - `GET /v1/meta` du greffon (dès que la compatibilité est branchée, setCompatibilite) : la
//     carte « Hermes » (version en service, verdict, alertes) est relue au même rythme, par
//     « Actualiser » et au retour du lien, et datée « Lu à » comme les autres cartes.
//
// Chaque carte est une table de valeurs DÉJÀ libellées en français, aux clés fixes : une
// valeur absente ou d'un autre type vaut « Inconnu », le poste jamais vu « Non configuré ».
// Un échec de lecture garde la dernière valeur, datée, avec l'erreur à côté.
//
// Geste : « Mettre en pause » / « Reprendre » Hermes (pause générale) → `POST /v1/pause`
// après confirmation de la page ; le refus du greffon (409 `crochets`…) est rendu tel quel.

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
    Q_PROPERTY(QVariantMap carteProjets READ carteProjets NOTIFY projetsChange)
    Q_PROPERTY(QVariantMap carteQuestions READ carteQuestions NOTIFY projetsChange)
    Q_PROPERTY(QVariantMap cartePoste READ cartePoste NOTIFY projetsChange)
    Q_PROPERTY(QVariantMap cartePause READ cartePause NOTIFY projetsChange)
    Q_PROPERTY(QVariantMap carteQuotas READ carteQuotas NOTIFY quotasChange)
    Q_PROPERTY(JsonListModel *sessions READ sessions CONSTANT)
    Q_PROPERTY(QString lectureProjets READ lectureProjets NOTIFY lectureChange)
    Q_PROPERTY(QString erreurProjets READ erreurProjets NOTIFY lectureChange)
    Q_PROPERTY(QString lectureQuotas READ lectureQuotas NOTIFY lectureChange)
    Q_PROPERTY(QString erreurQuotas READ erreurQuotas NOTIFY lectureChange)
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

    [[nodiscard]] const QVariantMap &carteProjets() const { return m_carteProjets; }
    [[nodiscard]] const QVariantMap &carteQuestions() const { return m_carteQuestions; }
    [[nodiscard]] const QVariantMap &cartePoste() const { return m_cartePoste; }
    [[nodiscard]] const QVariantMap &cartePause() const { return m_cartePause; }
    [[nodiscard]] const QVariantMap &carteQuotas() const { return m_carteQuotas; }
    [[nodiscard]] JsonListModel *sessions() const { return m_sessions; }

    [[nodiscard]] QString lectureProjets() const;
    [[nodiscard]] QString erreurProjets() const;
    [[nodiscard]] QString lectureQuotas() const;
    [[nodiscard]] QString erreurQuotas() const;
    [[nodiscard]] QString lectureSessions() const;
    [[nodiscard]] QString erreurSessions() const;
    [[nodiscard]] bool sessionsLues() const { return m_sessionsLues; }

    /*! Relit les trois sources tout de suite. */
    Q_INVOKABLE void actualiser();
    /*! Engage (vrai) ou lève (faux) la pause générale de Hermes ; raison facultative. */
    Q_INVOKABLE void basculerPause(bool generale, const QString &raison);

    // --- Fonctions pures (tests) --------------------------------------------------------
    [[nodiscard]] static QVariantMap construireCarteProjets(const QJsonObject &liste);
    [[nodiscard]] static QVariantMap construireCarteQuestions(const QJsonObject &liste);
    [[nodiscard]] static QVariantMap construireCartePoste(const QJsonObject &liste);
    [[nodiscard]] static QVariantMap construireCartePause(const QJsonObject &liste);
    [[nodiscard]] static QVariantMap construireCarteQuotas(const QJsonObject &quotas);
    [[nodiscard]] static QJsonArray construireSessions(const QJsonObject &page);

signals:
    void projetsChange();
    void quotasChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lireProjets(const QJsonObject &liste);
    [[nodiscard]] QList<Sondage *> sondages() const;

    ApiClient *m_client = nullptr;
    ClientGreffonPoste *m_greffon = nullptr;
    Sondage *m_projets = nullptr;
    Sondage *m_quotas = nullptr;
    Sondage *m_sondageSessions = nullptr;
    Sondage *m_meta = nullptr; //!< `/v1/meta`, une fois la compatibilité branchée.
    CompatibiliteHermes *m_compatibilite = nullptr;
    JsonListModel *m_sessions = nullptr;
    QVariantMap m_carteProjets;
    QVariantMap m_carteQuestions;
    QVariantMap m_cartePoste;
    QVariantMap m_cartePause;
    QVariantMap m_carteQuotas;
    bool m_sessionsLues = false;
};

} // namespace acp
