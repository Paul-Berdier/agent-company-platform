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
// Les routes des étapes suivantes (revues de P6, flux et agrégats de P7) ne sont pas
// déclarées ici tant que leur contrat n'est pas fusionné dans `refonte/hermes`.

#pragma once

#include "api/ApiRequest.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QString>

namespace acp {

class ApiCall;
class ApiClient;

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

    // --- Lectures --------------------------------------------------------------
    ApiCall *meta();
    ApiCall *projets();
    ApiCall *projet(const QString &identifiant);
    ApiCall *carteDuProjet(const QString &identifiant, const QString &carte);
    ApiCall *questions();
    ApiCall *poste();
    ApiCall *routage();
    ApiCall *quotas();

    // --- Projets ---------------------------------------------------------------
    /*!
        `POST /v1/projets` avec les champs du formulaire (`titre`, `objectif`, `profil`,
        `depot`, `reponses`, `exploration`) et une clé d'idempotence par formulaire : une
        seconde soumission rend `deja_lance`.
    */
    ApiCall *lancerProjet(const QJsonObject &formulaire, const QString &cleIdempotence);
    ApiCall *mettreProjetEnPause(const QString &identifiant);
    ApiCall *reprendreProjet(const QString &identifiant);

    // --- Questions et triage -----------------------------------------------------
    ApiCall *repondre(const QString &question, const QString &reponse);
    /*! « Prolonger », « Relancer » ou « Reprendre » : consigne facultative (vide = absente). */
    ApiCall *reprendreTriage(const QString &tableau, const QString &carte, const QString &consigne);
    ApiCall *conclureTriage(const QString &tableau, const QString &carte);

    // --- Pause générale ---------------------------------------------------------
    /*! `generale` vrai engage l'arrêt d'urgence ; raison de 200 caractères au plus. */
    ApiCall *pauseGenerale(bool generale, const QString &raison);

    // --- Poste --------------------------------------------------------------------
    ApiCall *enrolerPoste();
    ApiCall *confirmerEmpreinte(const QString &machineId, const QString &empreinte);
    ApiCall *revoquerPoste(const QString &machineId, const QString &motif);
    ApiCall *releverPoste();

    // --- Routage ------------------------------------------------------------------
    /*! Validation « tout ou rien » de la table affichée : relevés et classes tels que lus. */
    ApiCall *validerRoutage(const QJsonValue &releves, const QJsonValue &classes);
    ApiCall *accepterReleve(const QString &releveId);
    ApiCall *desactiverSurcharge(const QString &identifiant);

private:
    ApiCall *lire(const QString &relatif);
    ApiCall *ecrire(const QString &relatif, const QJsonObject &corps, const QString &cle = {});
    ApiCall *refuserIdentifiant(const QString &nature);

    ApiClient *m_client = nullptr;
};

} // namespace acp
