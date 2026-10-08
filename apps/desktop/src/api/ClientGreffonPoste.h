// Client REST du greffon acp-poste de Hermes (`/api/plugins/acp-poste/…`).
//
// Une méthode par route du propriétaire (hermes/plugins/acp-poste/dashboard/plugin_api.py,
// contrat acp-poste/1), qui construit EXACTEMENT le corps attendu par le greffon : aucun
// champ inventé, aucun champ inconnu (le greffon refuse tout champ hors liste, 400
// `arguments`). Les identifiants placés dans un chemin sont contrôlés avant l'envoi : un
// identifiant illisible est refusé par la station, jamais encodé au hasard.
//
// Toutes les routes passent par la porte de Hermes : elles partent en porteur, en JSON,
// sans en-tête `Origin` (ApiClient). Seul le lancement d'un projet accepte une clé
// d'idempotence : il est alors le seul appel d'écriture rejouable.
//
// Routes de P6 et P7 (fusionnées dans `refonte/hermes`) : revues des fichiers de pilotage
// (accepter, refuser avec un motif), relance d'une carte arrêtée, « qui répond », clôture d'un
// projet, accueil agrégé `GET /v1/accueil` et flux d'invalidation `GET /v1/flux` (ouvert en
// lecture au fil de l'eau, voir ouvrirFlux). Corps et bornes d'après le greffon
// (dashboard/plugin_api.py, noyau/questions.py, projets.py, execution.py).
//
// Échec fermé (cahier P8 § 4.2) : tant que le verdict de compatibilité dit le greffon
// incompatible (contrat d'une autre majeure) ou absent (`/v1/meta` en 404), CompatibiliteHermes
// le BLOQUE : toute lecture et toute écriture est refusée par la station, sans rien émettre,
// avec l'explication du verdict. Seul `/v1/meta` reste lisible, pour revérifier.

#pragma once

#include "api/ApiRequest.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QString>

class QNetworkReply;

namespace acp {

class ApiCall;
class ApiClient;
class ApiError;

class ClientGreffonPoste
{
public:
    //! Préfixe de montage du greffon dans le tableau de bord de Hermes.
    static constexpr char kPrefixe[] = "/api/plugins/acp-poste";

    explicit ClientGreffonPoste(ApiClient *client);

    /*! Vrai si l'identifiant peut figurer tel quel dans un segment de chemin. */
    [[nodiscard]] static bool identifiantValide(const QString &identifiant);

    /*! Chemin complet d'une route relative du greffon (« /v1/meta »). */
    [[nodiscard]] static QString chemin(const QString &relatif);

    // --- Verdict de compatibilité ---------------------------------------------------
    /*! Refuse désormais toute route du greffon sauf `/v1/meta`, avec cette raison. */
    void bloquer(const QString &raison);
    /*! Lève le blocage (verdict compatible, session ou serveur oubliés). */
    void debloquer() { m_blocage.clear(); }
    [[nodiscard]] bool bloque() const { return !m_blocage.isEmpty(); }
    [[nodiscard]] const QString &raisonBlocage() const { return m_blocage; }

    // --- Lectures --------------------------------------------------------------
    ApiCall *meta();
    /*! Verrou du catalogue (`/v1/catalogue`) : types de projet offerts au lancement. */
    ApiCall *catalogue();
    ApiCall *projets();
    ApiCall *projet(const QString &identifiant);
    ApiCall *carteDuProjet(const QString &identifiant, const QString &carte);
    ApiCall *questions();
    ApiCall *poste();
    ApiCall *routage();
    ApiCall *quotas();
    /*! Accueil agrégé (étape P7) : à traiter, projets, exécutant, quotas, canal, pause. */
    ApiCall *accueil();

    /*!
        Ouvre le flux d'invalidation `GET /v1/flux` (étape P7) en lecture au fil de l'eau, avec
        `Last-Event-ID` s'il est connu. Rend nullptr et remplit `refus` si le greffon est bloqué,
        si l'adresse ou la session manque : rien n'est alors émis.
    */
    [[nodiscard]] QNetworkReply *ouvrirFlux(const QString &dernierId, ApiError *refus);

    // --- Projets ---------------------------------------------------------------
    /*!
        `POST /v1/projets` avec les champs du formulaire (`titre`, `objectif`, `profil`,
        `depot`, `reponses`, `exploration`) et une clé d'idempotence par formulaire : une
        seconde soumission rend `deja_lance`.
    */
    ApiCall *lancerProjet(const QJsonObject &formulaire, const QString &cleIdempotence);
    ApiCall *mettreProjetEnPause(const QString &identifiant);
    ApiCall *reprendreProjet(const QString &identifiant);
    /*!
        « Qui répond » (étape P7) : `hermes_d_abord` ou `proprietaire`, pour les questions
        SUIVANTES ; toute autre valeur est refusée par la station sans envoi.
    */
    ApiCall *changerReponses(const QString &identifiant, const QString &reponses);
    /*! « Clore le projet » (étape P7) : `{"confirmation": true}`, après la confirmation de la page. */
    ApiCall *clore(const QString &identifiant);

    // --- Questions et triage -----------------------------------------------------
    ApiCall *repondre(const QString &question, const QString &reponse);
    /*! « Prolonger », « Relancer » ou « Reprendre » : consigne facultative (vide = absente). */
    ApiCall *reprendreTriage(const QString &tableau, const QString &carte, const QString &consigne);
    ApiCall *conclureTriage(const QString &tableau, const QString &carte);
    /*!
        « Relancer » une carte bloquée ou abandonnée (étape P7) : consigne facultative (vide =
        absente ; une carte d'intégration n'en reçoit jamais).
    */
    ApiCall *relancerCarte(const QString &tableau, const QString &carte, const QString &consigne);

    // --- Revues des fichiers de pilotage (étape P6) -------------------------------------
    ApiCall *accepterRevue(const QString &tableau, const QString &carte);
    /*! Motif exigé (1 à 1 000 caractères, contrôlé par le greffon). */
    ApiCall *refuserRevue(const QString &tableau, const QString &carte, const QString &motif);

    // --- Pause générale ---------------------------------------------------------
    /*! `generale` vrai engage l'arrêt d'urgence ; raison de 200 caractères au plus. */
    ApiCall *pauseGenerale(bool generale, const QString &raison);
    /*! Notification de test (202 : mise en file ; 409 `notifications` : aucun canal configuré). */
    ApiCall *notificationDeTest();

    // --- Poste --------------------------------------------------------------------
    ApiCall *enrolerPoste();
    ApiCall *confirmerEmpreinte(const QString &machineId, const QString &empreinte);
    ApiCall *revoquerPoste(const QString &machineId, const QString &motif);
    ApiCall *releverPoste();

    // --- Routage ------------------------------------------------------------------
    /*! Validation « tout ou rien » de la table affichée : relevés et classes tels que lus. */
    ApiCall *validerRoutage(const QJsonValue &releves, const QJsonValue &classes);
    /*! « Accepter ce relevé comme celui de mon compte » : identifiant numérique du relevé. */
    ApiCall *accepterReleve(qint64 releveId);
    ApiCall *desactiverSurcharge(const QString &identifiant);

private:
    ApiCall *lire(const QString &relatif);
    ApiCall *ecrire(const QString &relatif, const QJsonObject &corps, const QString &cle = {});
    ApiCall *refuserIdentifiant(const QString &nature);
    //! Refus local si le tableau ou la carte ne peut figurer dans un chemin, sinon nul.
    ApiCall *controlerCarte(const QString &tableau, const QString &carte);

    ApiClient *m_client = nullptr;
    QString m_blocage;
};

} // namespace acp
