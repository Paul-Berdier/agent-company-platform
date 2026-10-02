// Demandes de l'agent aux sessions ouvertes DANS la station (cahier P8 § 5.3, § 7.3, § 7.4).
//
// Hermes envoie des requêtes serveur JSON-RPC à la connexion attachée à une session
// (tui_gateway/server_requests.py) ; la station en traite DEUX :
//   - `approval` : une commande dangereuse attend votre décision (commande expurgée par
//     Hermes, description, outil, choix offerts parmi once / session / always / deny) ;
//     réponse `{choice}` ;
//   - `clarify` : une question (choix éventuels, sélection multiple) ou un lot de questions ;
//     réponse `{answer}` (vide = passer) ou `{answers}` pour le lot entier.
// Toute autre requête (secret, sudo, coffre…) est refusée en -32601 par le canal : la station
// ne saisit jamais de secret ni de mot de passe pour l'agent.
//
// Les boutons de choix sont construits DEPUIS les choix offerts par Hermes, jamais une liste
// fixe ; un choix non offert est refusé par la station sans rien envoyer.
//
// Non durables : ces demandes vivent dans la mémoire de Hermes. À la coupure, la liste est
// vidée ; à la reprise, Hermes repropose celles qu'il attend encore (`open_requests`). Un
// redéploiement de Hermes les perd.

#pragma once

#include "models/JsonListModel.h"
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantMap>

namespace acp {

class GatewayClient;
struct RequeteServeur;

class DemandesAgent : public QObject
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *demandes READ demandes CONSTANT)
    Q_PROPERTY(int nombre READ nombre NOTIFY demandesChange)
    Q_PROPERTY(QString message READ message NOTIFY messageChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY messageChange)

public:
    explicit DemandesAgent(GatewayClient *passerelle, QObject *parent = nullptr);
    ~DemandesAgent() override;

    [[nodiscard]] JsonListModel *demandes() const { return m_demandes; }
    [[nodiscard]] int nombre() const;
    [[nodiscard]] const QString &message() const { return m_message; }
    [[nodiscard]] const QString &erreur() const { return m_erreur; }

    /*! Répond à une demande `approval` par un des choix offerts. */
    Q_INVOKABLE bool approuver(const QString &identifiant, const QString &choix);
    /*! Répond à une question `clarify` simple ; vide = passer la question. */
    Q_INVOKABLE bool clarifier(const QString &identifiant, const QString &reponse);
    /*!
        Répond à une question `clarify` à sélection multiple : les choix retenus, tous parmi ceux
        offerts, envoyés comme Hermes les attend (tableau JSON des libellés, dans `answer`).
    */
    Q_INVOKABLE bool clarifierSelection(const QString &identifiant, const QStringList &selection);
    /*! Répond au lot entier d'une demande `clarify` : une réponse par question (`qid`). */
    Q_INVOKABLE bool clarifierLot(const QString &identifiant, const QVariantMap &reponses);

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construire(const RequeteServeur &requete);
    [[nodiscard]] static QString libelleChoix(const QString &choix);

signals:
    void demandesChange();
    void messageChange();

private:
    void recevoir(const RequeteServeur &requete);
    void retirer(const QString &identifiant);
    [[nodiscard]] QJsonObject trouver(const QString &identifiant) const;
    bool envoyer(const QString &identifiant, const QJsonObject &resultat, const QString &message);
    void dire(const QString &message, const QString &erreur);

    GatewayClient *m_passerelle = nullptr;
    JsonListModel *m_demandes = nullptr;
    QString m_message;
    QString m_erreur;
};

} // namespace acp
