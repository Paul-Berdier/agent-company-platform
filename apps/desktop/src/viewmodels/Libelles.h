// Libellés français des codes renvoyés par le greffon acp-poste et par Hermes.
//
// Même table que l'interface web (apps/interface/src/projets/libelles.ts et chaines.ts) : la
// station et le tableau de bord disent la même chose du même état. Un code INCONNU n'est
// jamais traduit au hasard : la fonction rend un libellé vide, et la page montre la valeur
// brute comme une donnée, avec la pastille « Inconnu ».
//
// La clé de pastille (`cle`) est celle des jetons d'état de la station (StatusChip) : la
// couleur n'est jamais seule porteuse du sens, le libellé l'accompagne toujours.

#pragma once

#include <QJsonValue>
#include <QString>
#include <QStringList>

namespace acp::libelles {

//! Libellé d'un état et clé de sa pastille (« succeeded », « running », « degraded »…).
struct Libelle
{
    QString texte;
    QString cle;

    [[nodiscard]] bool connu() const { return !texte.isEmpty(); }
};

inline const QString kInconnu = QStringLiteral("Inconnu");

// --- Valeurs ------------------------------------------------------------------------

/*! Chaîne non vide, sinon « Inconnu ». */
[[nodiscard]] QString texte(const QJsonValue &valeur);
/*! Vrai si la valeur est une chaîne non vide. */
[[nodiscard]] bool estTexte(const QJsonValue &valeur);
/*! Entier positif ou nul, sinon « Inconnu ». */
[[nodiscard]] QString nombre(const QJsonValue &valeur);
/*! Vrai si la valeur est un entier positif ou nul. */
[[nodiscard]] bool estNombre(const QJsonValue &valeur);
/*! Horodatage en secondes depuis l'époque → « 26/09/2026 13:43 » (heure locale), sinon « Inconnu ». */
[[nodiscard]] QString date(const QJsonValue &secondes);
/*! Date ISO 8601 (« 2026-09-26T11:44:00.073871+00:00 ») → « 26/09/2026 13:44 » (heure locale) ;
    une chaîne illisible est rendue telle quelle (donnée), une absence vaut « Inconnu ». */
[[nodiscard]] QString dateIso(const QJsonValue &iso);
/*! Pourcentage → « 41 % » (espace insécable), sinon « Inconnu ». */
[[nodiscard]] QString pourcentage(const QJsonValue &valeur);
/*! Booléen → « Oui » ou « Non », sinon « Inconnu ». */
[[nodiscard]] QString ouiNon(const QJsonValue &valeur);

// --- États --------------------------------------------------------------------------

[[nodiscard]] Libelle etatProjet(const QJsonValue &etat, const QJsonValue &derive);
[[nodiscard]] Libelle statutCarte(const QJsonValue &statut);
[[nodiscard]] Libelle etatPoste(const QJsonValue &etat);
[[nodiscard]] Libelle etatQuestion(const QJsonValue &etat);
//! Relecture finale de P7 : `chez` (règle unique du greffon) ; une question « ouverte » qui attend le propriétaire
//! (carte « répondre » jamais créée) se dit « Votre réponse est attendue », jamais « Hermes cherche la réponse ».
[[nodiscard]] Libelle etatQuestion(const QJsonValue &etat, const QJsonValue &chez);
// Étape P5 (apps/interface/src/poste/libelles.ts) : connexions du poste, badges des listes
// relevées, états de la table de routage et des quotas.
[[nodiscard]] Libelle connexionCodex(const QJsonValue &etat);
[[nodiscard]] Libelle connexionClaude(const QJsonValue &etat);
[[nodiscard]] Libelle badgeListe(const QJsonValue &badge);
[[nodiscard]] Libelle etatTable(const QJsonValue &etat);
[[nodiscard]] Libelle etatQuotas(const QJsonValue &etat);

// --- Codes -----------------------------------------------------------------------------

[[nodiscard]] QString role(const QJsonValue &role);
[[nodiscard]] QString voie(const QJsonValue &voie);
[[nodiscard]] QString profil(const QJsonValue &profil);
[[nodiscard]] QString reponses(const QJsonValue &reponses);
[[nodiscard]] QString origine(const QJsonValue &origine);
[[nodiscard]] QString palier(const QJsonValue &palier);
[[nodiscard]] QString actionJournal(const QJsonValue &action);
/*! « Vous », « ACP », « Poste », « Hermes (discussion) », « Carte <id> » ; sinon la valeur brute. */
[[nodiscard]] QString acteurJournal(const QJsonValue &acteur);
/*! Geste offert sur une carte en triage : « Prolonger », « Relancer la planification »… */
[[nodiscard]] QString actionTriage(const QString &action);
/*! Ordre envoyé au poste : « Relevé », « Pause », « Reprise ». */
[[nodiscard]] QString genreOrdre(const QJsonValue &genre);
/*! Classe de routage : « Exploration du dépôt », « Implémentation »… */
[[nodiscard]] QString classe(const QJsonValue &classe);
/*! Classes de routage dans l'ordre de la page web (les classes inconnues suivent). */
[[nodiscard]] const QStringList &ordreDesClasses();

} // namespace acp::libelles
