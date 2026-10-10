#include "viewmodels/Libelles.h"

#include <QDateTime>
#include <QHash>
#include <QLocale>
#include <QRegularExpression>

#include <cmath>

namespace acp::libelles {

namespace {

QString chaine(const QJsonValue &valeur)
{
    return valeur.isString() ? valeur.toString() : QString();
}

QString depuisTable(const QHash<QString, QString> &table, const QJsonValue &valeur)
{
    return valeur.isString() ? table.value(valeur.toString()) : QString();
}

} // namespace

QString texte(const QJsonValue &valeur)
{
    return estTexte(valeur) ? valeur.toString() : kInconnu;
}

bool estTexte(const QJsonValue &valeur)
{
    return valeur.isString() && !valeur.toString().trimmed().isEmpty();
}

bool estNombre(const QJsonValue &valeur)
{
    if (!valeur.isDouble()) {
        return false;
    }
    const double nombre = valeur.toDouble();
    return nombre >= 0 && std::floor(nombre) == nombre;
}

QString nombre(const QJsonValue &valeur)
{
    return estNombre(valeur) ? QString::number(valeur.toInteger()) : kInconnu;
}

QString date(const QJsonValue &secondes)
{
    // Horodatages de Hermes : secondes, parfois fractionnaires (time.time() en Python).
    if (!secondes.isDouble() || secondes.toDouble() <= 0) {
        return kInconnu;
    }
    return QDateTime::fromSecsSinceEpoch(static_cast<qint64>(secondes.toDouble()))
        .toLocalTime()
        .toString(QStringLiteral("dd/MM/yyyy HH:mm"));
}

QString dateIso(const QJsonValue &iso)
{
    if (!estTexte(iso)) {
        return kInconnu;
    }
    const QString brut = iso.toString().trimmed();
    QDateTime instant = QDateTime::fromString(brut, Qt::ISODateWithMs);
    if (!instant.isValid()) {
        // Fractions de seconde au-delà de la milliseconde (Python les écrit en microsecondes).
        static const QRegularExpression fraction(QStringLiteral("\\.\\d+"));
        QString sansFraction = brut;
        sansFraction.remove(fraction);
        instant = QDateTime::fromString(sansFraction, Qt::ISODate);
    }
    return instant.isValid() ? instant.toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm")) : brut;
}

QString pourcentage(const QJsonValue &valeur)
{
    if (!valeur.isDouble() || valeur.toDouble() < 0) {
        return kInconnu;
    }
    // \u00C9criture fran\u00E7aise : virgule d\u00E9cimale, espace ins\u00E9cable avant le signe.
    const double nombre = valeur.toDouble();
    return QStringLiteral("%1\u00A0%").arg(QLocale(QLocale::French).toString(nombre, 'f', nombre == std::floor(nombre) ? 0 : 1));
}

QString ouiNon(const QJsonValue &valeur)
{
    if (!valeur.isBool()) {
        return kInconnu;
    }
    return valeur.toBool() ? QStringLiteral("Oui") : QStringLiteral("Non");
}

Libelle etatProjet(const QJsonValue &etat, const QJsonValue &derive)
{
    const QString e = chaine(etat);
    if (e == QLatin1String("creation")) return {QStringLiteral("Création en cours"), QStringLiteral("pending")};
    if (e == QLatin1String("en_pause")) return {QStringLiteral("En pause"), QStringLiteral("pending")};
    if (e == QLatin1String("termine")) return {QStringLiteral("Terminé"), QStringLiteral("succeeded")};
    if (e == QLatin1String("abandonne")) return {QStringLiteral("Abandonné"), QStringLiteral("failed")};
    if (e != QLatin1String("actif")) return {};
    const QString d = chaine(derive);
    if (d == QLatin1String("exploration")) return {QStringLiteral("Exploration du dépôt"), QStringLiteral("running")};
    if (d == QLatin1String("planification")) return {QStringLiteral("Planification"), QStringLiteral("running")};
    if (d == QLatin1String("synthese")) return {QStringLiteral("Synthèse"), QStringLiteral("running")};
    if (d == QLatin1String("en_cours")) return {QStringLiteral("En cours"), QStringLiteral("running")};
    if (d == QLatin1String("en_attente_du_poste")) return {QStringLiteral("En attente du poste"), QStringLiteral("degraded")};
    if (d == QLatin1String("plafond_atteint"))
        return {QStringLiteral("Plafond atteint : votre décision est attendue"), QStringLiteral("approvalRequired")};
    if (d == QLatin1String("a_decider")) return {QStringLiteral("Votre décision est attendue"), QStringLiteral("approvalRequired")};
    return {QStringLiteral("Actif"), QStringLiteral("running")};
}

Libelle statutCarte(const QJsonValue &statut)
{
    const QString s = chaine(statut);
    if (s == QLatin1String("triage")) return {QStringLiteral("En triage"), QStringLiteral("approvalRequired")};
    if (s == QLatin1String("todo")) return {QStringLiteral("En attente"), QStringLiteral("pending")};
    if (s == QLatin1String("scheduled")) return {QStringLiteral("Suspendue"), QStringLiteral("pending")};
    if (s == QLatin1String("ready")) return {QStringLiteral("Prête"), QStringLiteral("pending")};
    if (s == QLatin1String("running")) return {QStringLiteral("En cours"), QStringLiteral("running")};
    if (s == QLatin1String("blocked")) return {QStringLiteral("Bloquée"), QStringLiteral("blocked")};
    if (s == QLatin1String("review")) return {QStringLiteral("En relecture"), QStringLiteral("running")};
    if (s == QLatin1String("done")) return {QStringLiteral("Faite"), QStringLiteral("succeeded")};
    if (s == QLatin1String("archived")) return {QStringLiteral("Archivée"), QStringLiteral("pending")};
    if (s == QLatin1String("a_creer")) return {QStringLiteral("À créer"), QStringLiteral("pending")};
    return {};
}

Libelle etatPoste(const QJsonValue &etat)
{
    // presence.etat_poste : les cinq états possibles, jamais une valeur inventée.
    const QString e = chaine(etat);
    if (e == QLatin1String("non_configure")) return {QStringLiteral("Non configuré"), QStringLiteral("notConfigured")};
    if (e == QLatin1String("a_confirmer")) return {QStringLiteral("À confirmer"), QStringLiteral("approvalRequired")};
    if (e == QLatin1String("en_ligne")) return {QStringLiteral("En ligne"), QStringLiteral("succeeded")};
    if (e == QLatin1String("hors_ligne")) return {QStringLiteral("Hors ligne"), QStringLiteral("offline")};
    if (e == QLatin1String("revoque")) return {QStringLiteral("Révoqué"), QStringLiteral("failed")};
    return {};
}

Libelle etatQuestion(const QJsonValue &etat)
{
    const QString e = chaine(etat);
    if (e == QLatin1String("ouverte")) return {QStringLiteral("Hermes cherche la réponse"), QStringLiteral("running")};
    if (e == QLatin1String("escaladee")) return {QStringLiteral("Votre réponse est attendue"), QStringLiteral("approvalRequired")};
    return {};
}

Libelle etatQuestion(const QJsonValue &etat, const QJsonValue &chez)
{
    if (chaine(etat) == QLatin1String("ouverte") && chaine(chez) == QLatin1String("proprietaire")) {
        return etatQuestion(QJsonValue(QStringLiteral("escaladee")));
    }
    return etatQuestion(etat);
}

// Familles de la page web → pastilles de la station : succès « succeeded », échec « failed »,
// dégradé « degraded », neutre « pending », actif « running », inconnu « unknown ».

Libelle connexionCodex(const QJsonValue &etat)
{
    const QString e = chaine(etat);
    if (e == QLatin1String("compte_chatgpt")) return {QStringLiteral("Compte ChatGPT"), QStringLiteral("succeeded")};
    if (e == QLatin1String("cle_api")) return {QStringLiteral("Clé d'API (refusée)"), QStringLiteral("failed")};
    if (e == QLatin1String("autre")) return {QStringLiteral("Autre"), QStringLiteral("degraded")};
    if (e == QLatin1String("non_connecte")) return {QStringLiteral("Non connecté"), QStringLiteral("pending")};
    if (e == QLatin1String("inconnu")) return {kInconnu, QStringLiteral("unknown")};
    return {};
}

Libelle connexionClaude(const QJsonValue &etat)
{
    const QString e = chaine(etat);
    if (e == QLatin1String("jeton_reconnu")) return {QStringLiteral("Jeton reconnu"), QStringLiteral("succeeded")};
    if (e == QLatin1String("jeton_present_non_verifie"))
        return {QStringLiteral("Jeton présent, non vérifié"), QStringLiteral("degraded")};
    if (e == QLatin1String("refuse")) return {QStringLiteral("Refusé"), QStringLiteral("failed")};
    if (e == QLatin1String("jeton_absent")) return {QStringLiteral("Jeton absent"), QStringLiteral("pending")};
    if (e == QLatin1String("inconnu")) return {kInconnu, QStringLiteral("unknown")};
    return {};
}

Libelle badgeListe(const QJsonValue &badge)
{
    const QString b = chaine(badge);
    if (b == QLatin1String("releve_du_compte")) return {QStringLiteral("Relevé du compte"), QStringLiteral("succeeded")};
    if (b == QLatin1String("liste_de_secours")) return {QStringLiteral("Liste de secours"), QStringLiteral("failed")};
    if (b == QLatin1String("liste_de_secours_probable"))
        return {QStringLiteral("Liste de secours probable"), QStringLiteral("degraded")};
    if (b == QLatin1String("liste_acceptee")) return {QStringLiteral("Relevé accepté par vous"), QStringLiteral("succeeded")};
    if (b == QLatin1String("alias_documentes")) return {QStringLiteral("Alias documentés"), QStringLiteral("running")};
    if (b == QLatin1String("perime")) return {QStringLiteral("Périmé"), QStringLiteral("degraded")};
    if (b == QLatin1String("inconnu")) return {kInconnu, QStringLiteral("unknown")};
    if (b == QLatin1String("releve_factice")) return {QStringLiteral("Relevé factice"), QStringLiteral("degraded")};
    if (b == QLatin1String("indisponible")) return {QStringLiteral("Indisponible"), QStringLiteral("failed")};
    return {};
}

Libelle etatTable(const QJsonValue &etat)
{
    const QString e = chaine(etat);
    if (e == QLatin1String("non_validee")) return {QStringLiteral("Non validée"), QStringLiteral("pending")};
    if (e == QLatin1String("validee")) return {QStringLiteral("Validée"), QStringLiteral("succeeded")};
    if (e == QLatin1String("a_revalider")) return {QStringLiteral("À revalider"), QStringLiteral("degraded")};
    return {};
}

Libelle etatQuotas(const QJsonValue &etat)
{
    const QString e = chaine(etat);
    if (e == QLatin1String("releve")) return {QStringLiteral("Relevé"), QStringLiteral("succeeded")};
    if (e == QLatin1String("perime")) return {QStringLiteral("Périmé"), QStringLiteral("degraded")};
    if (e == QLatin1String("inconnu")) return {kInconnu, QStringLiteral("unknown")};
    return {};
}

QString role(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("exploration"), QStringLiteral("Exploration du dépôt")},
        {QStringLiteral("planification"), QStringLiteral("Planification")},
        {QStringLiteral("implementation"), QStringLiteral("Implémentation")},
        {QStringLiteral("relecture"), QStringLiteral("Relecture croisée")},
        {QStringLiteral("correction"), QStringLiteral("Corrections")},
        {QStringLiteral("hermes"), QStringLiteral("Étapes de Hermes")},
        {QStringLiteral("synthese"), QStringLiteral("Synthèse")},
        {QStringLiteral("repondre"), QStringLiteral("Réponses aux questions")},
        {QStringLiteral("triage"), QStringLiteral("Triage")},
    };
    return depuisTable(table, valeur);
}

QString voie(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("hermes"), QStringLiteral("Hermes")},
        {QStringLiteral("poste-codex"), QStringLiteral("Poste (Codex)")},
        {QStringLiteral("poste-claude"), QStringLiteral("Poste (Claude)")},
    };
    return depuisTable(table, valeur);
}

QString profil(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("base"), QStringLiteral("Base")},
        {QStringLiteral("web"), QStringLiteral("Site web")},
        {QStringLiteral("recherche"), QStringLiteral("Recherche")},
        {QStringLiteral("donnees"), QStringLiteral("Données")},
    };
    return depuisTable(table, valeur);
}

QString reponses(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("hermes_d_abord"), QStringLiteral("Hermes d'abord")},
        {QStringLiteral("proprietaire"), QStringLiteral("Moi")},
    };
    return depuisTable(table, valeur);
}

QString origine(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("tableau_de_bord"), QStringLiteral("la page Projets")},
        {QStringLiteral("discussion"), QStringLiteral("la discussion")},
    };
    return depuisTable(table, valeur);
}

QString palier(const QJsonValue &valeur)
{
    return chaine(valeur) == QLatin1String("default") ? QStringLiteral("Standard") : QString();
}

QString actionJournal(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("lancement"), QStringLiteral("Lancement")},
        {QStringLiteral("planification"), QStringLiteral("Tour planifié")},
        {QStringLiteral("planification_annulee"), QStringLiteral("Planification annulée")},
        {QStringLiteral("pause"), QStringLiteral("Mise en pause")},
        {QStringLiteral("reprise"), QStringLiteral("Reprise")},
        {QStringLiteral("pause_carte"), QStringLiteral("Carte suspendue par la pause")},
        {QStringLiteral("reprise_carte"), QStringLiteral("Carte reprise")},
        {QStringLiteral("question"), QStringLiteral("Question du poste")},
        {QStringLiteral("question_escaladee"), QStringLiteral("Question transmise au propriétaire")},
        {QStringLiteral("question_repondue"), QStringLiteral("Question répondue")},
        {QStringLiteral("triage_repris"), QStringLiteral("Décision appliquée")},
        {QStringLiteral("prolongation"), QStringLiteral("Plafond prolongé")},
        {QStringLiteral("relance_planification"), QStringLiteral("Planification relancée")},
        {QStringLiteral("conclusion"), QStringLiteral("Projet conclu")},
        {QStringLiteral("plafond"), QStringLiteral("Plafond atteint")},
        {QStringLiteral("sans_plan"), QStringLiteral("Planification finie sans plan")},
        {QStringLiteral("termine"), QStringLiteral("Projet terminé")},
        {QStringLiteral("reparation"), QStringLiteral("Création réparée")},
        {QStringLiteral("surcharge"), QStringLiteral("Surcharge de routage")},
        {QStringLiteral("correction"), QStringLiteral("Correction insérée")},
    };
    return depuisTable(table, valeur);
}

QString acteurJournal(const QJsonValue &valeur)
{
    if (!valeur.isString()) {
        return kInconnu;
    }
    const QString acteur = valeur.toString();
    if (acteur.startsWith(QLatin1String("proprietaire:"))) return QStringLiteral("Vous");
    if (acteur == QLatin1String("acp-poste") || acteur.startsWith(QLatin1String("acp-poste:"))) return QStringLiteral("ACP");
    if (acteur == QLatin1String("poste")) return QStringLiteral("Poste");
    if (acteur.startsWith(QLatin1String("discussion:"))) return QStringLiteral("Hermes (discussion)");
    if (acteur.startsWith(QLatin1String("carte:"))) {
        const QString carte = acteur.mid(6);
        return carte.isEmpty() ? QStringLiteral("Carte") : QStringLiteral("Carte %1").arg(carte);
    }
    return acteur.isEmpty() ? kInconnu : acteur;
}

QString actionTriage(const QString &action)
{
    if (action == QLatin1String("prolonger")) return QStringLiteral("Prolonger");
    if (action == QLatin1String("relancer")) return QStringLiteral("Relancer la planification");
    if (action == QLatin1String("reprendre")) return QStringLiteral("Reprendre");
    if (action == QLatin1String("conclure")) return QStringLiteral("Conclure le projet");
    return {};
}

QString genreOrdre(const QJsonValue &genre)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("releve"), QStringLiteral("Relevé")},
        {QStringLiteral("pause"), QStringLiteral("Pause")},
        {QStringLiteral("reprise"), QStringLiteral("Reprise")},
    };
    return depuisTable(table, genre);
}

QString classe(const QJsonValue &valeur)
{
    static const QHash<QString, QString> table = {
        {QStringLiteral("exploration"), QStringLiteral("Exploration du dépôt")},
        {QStringLiteral("planification"), QStringLiteral("Planification")},
        {QStringLiteral("synthese"), QStringLiteral("Synthèse")},
        {QStringLiteral("repondre"), QStringLiteral("Réponses aux questions")},
        {QStringLiteral("recherche_web"), QStringLiteral("Recherche web")},
        {QStringLiteral("architecture"), QStringLiteral("Architecture")},
        {QStringLiteral("implementation"), QStringLiteral("Implémentation")},
        {QStringLiteral("debogage_tests"), QStringLiteral("Débogage et tests")},
        {QStringLiteral("petite_tache"), QStringLiteral("Petite tâche")},
        {QStringLiteral("documentation"), QStringLiteral("Documentation")},
        {QStringLiteral("relecture"), QStringLiteral("Relecture croisée")},
    };
    return depuisTable(table, valeur);
}

const QStringList &ordreDesClasses()
{
    static const QStringList ordre = {
        QStringLiteral("exploration"), QStringLiteral("planification"), QStringLiteral("synthese"),
        QStringLiteral("repondre"), QStringLiteral("recherche_web"), QStringLiteral("architecture"),
        QStringLiteral("implementation"), QStringLiteral("debogage_tests"), QStringLiteral("petite_tache"),
        QStringLiteral("documentation"), QStringLiteral("relecture"),
    };
    return ordre;
}

} // namespace acp::libelles
