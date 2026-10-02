// Page Questions de la station (cahier P8 § 7.3), sur `GET /v1/questions` du greffon, relu
// toutes les 15 s tant que la page est affichée.
//
//  - Questions ouvertes ou escaladées : texte, contexte, projet, carte, motif d'escalade, date ;
//    « Répondre » → `POST /v1/questions/{q}/reponse {reponse}` (1 à 4 000 caractères). Le
//    message de réussite suit la RÉPONSE du greffon (`carte_debloquee`, `reprise_differee`),
//    jamais une supposition ; une question fermée entre-temps (409) est dite, puis relue.
//  - Cartes en triage : les gestes sont construits DEPUIS `actions` rendues par le greffon
//    (« Prolonger », « Relancer la planification », « Reprendre » → `/reprendre` avec une
//    consigne facultative ; « Conclure le projet » → `/conclure`), jamais une liste fixe ; un
//    geste qui n'est pas offert pour cette carte est refusé par la station.
//  - Cartes bloquées ou abandonnées : lecture seule (relancer relève de P7).
//  - Revues des fichiers de pilotage (P6) : affichées SEULEMENT si la clé `revues` existe, en
//    lecture seule tant que leur contrat n'est pas fusionné dans `refonte/hermes` ; elles se
//    traitent dans le navigateur.
//  - Tableaux illisibles : signalés tels quels.

#pragma once

#include "viewmodels/PageViewModel.h"

#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QUrl>

#include <functional>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class JsonListModel;
class Sondage;

class QuestionsViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *questions READ questions CONSTANT)
    Q_PROPERTY(JsonListModel *triage READ triage CONSTANT)
    Q_PROPERTY(JsonListModel *bloquees READ bloquees CONSTANT)
    Q_PROPERTY(JsonListModel *revues READ revues CONSTANT)
    Q_PROPERTY(bool lue READ lue NOTIFY listeChange)
    Q_PROPERTY(bool revuesPresentes READ revuesPresentes NOTIFY listeChange)
    Q_PROPERTY(QStringList tableauxIllisibles READ tableauxIllisibles NOTIFY listeChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)

public:
    QuestionsViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                       QObject *parent = nullptr);
    ~QuestionsViewModel() override;

    using Ouvreur = std::function<bool(const QUrl &)>;
    void setOuvreur(Ouvreur ouvreur) { m_ouvreur = std::move(ouvreur); }

    [[nodiscard]] JsonListModel *questions() const { return m_questions; }
    [[nodiscard]] JsonListModel *triage() const { return m_triage; }
    [[nodiscard]] JsonListModel *bloquees() const { return m_bloquees; }
    [[nodiscard]] JsonListModel *revues() const { return m_revues; }
    [[nodiscard]] bool lue() const { return m_lue; }
    [[nodiscard]] bool revuesPresentes() const { return m_revuesPresentes; }
    [[nodiscard]] const QStringList &tableauxIllisibles() const { return m_illisibles; }
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] QString erreur() const;

    Q_INVOKABLE void actualiser();
    /*! Répond à une question ouverte ou escaladée (1 à 4 000 caractères). */
    Q_INVOKABLE void repondre(const QString &question, const QString &reponse);
    /*!
        Geste sur une carte en triage : « reprise » (prolonger, relancer ou reprendre, selon ce
        que le greffon offre, avec une consigne facultative) ou « conclure ».
    */
    Q_INVOKABLE void agirTriage(const QString &tableau, const QString &carte, const QString &geste,
                                const QString &consigne);
    /*! Ouvre la page Questions du tableau de bord (revues de P6) dans le navigateur. */
    Q_INVOKABLE bool traiterDansLeNavigateur();

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construireQuestion(const QJsonObject &question);
    [[nodiscard]] static QJsonObject construireTriage(const QJsonObject &carte);
    [[nodiscard]] static QJsonObject construireBloquee(const QJsonObject &carte);
    [[nodiscard]] static QJsonObject construireRevue(const QJsonObject &revue);
    [[nodiscard]] static QString messageReponse(const QJsonObject &resultat);
    [[nodiscard]] static QString messageTriage(const QJsonObject &resultat);
    /*! Gestes offerts : `actions` lisibles, sinon « reprendre » (comme la page web). */
    [[nodiscard]] static QStringList gestesOfferts(const QJsonObject &carte);

signals:
    void listeChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;

private:
    void lire(const QJsonObject &liste);
    void apresGeste();

    ClientGreffonPoste *m_greffon = nullptr;
    ApiClient *m_client = nullptr;
    Sondage *m_sondage = nullptr;
    JsonListModel *m_questions = nullptr;
    JsonListModel *m_triage = nullptr;
    JsonListModel *m_bloquees = nullptr;
    JsonListModel *m_revues = nullptr;
    Ouvreur m_ouvreur;
    bool m_lue = false;
    bool m_revuesPresentes = false;
    QStringList m_illisibles;
    QHash<QString, QStringList> m_gestes; //!< « tableau/carte » → gestes offerts par le greffon.
};

} // namespace acp
