#include "viewmodels/QuestionsViewModel.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "viewmodels/Libelles.h"

#include <QDesktopServices>
#include <QUrlQuery>

namespace acp {

namespace {

QString cle(const QString &tableau, const QString &carte)
{
    return tableau + QLatin1Char('/') + carte;
}

QString texteOuVide(const QJsonValue &valeur)
{
    return libelles::estTexte(valeur) ? valeur.toString() : QString();
}

QStringList chaines(const QJsonValue &valeur)
{
    QStringList resultat;
    for (const QJsonValue &element : valeur.toArray()) {
        if (libelles::estTexte(element)) {
            resultat.append(element.toString());
        }
    }
    return resultat;
}

} // namespace

QuestionsViewModel::QuestionsViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                                       QObject *parent)
    : PageViewModel(flux, parent)
    , m_greffon(greffon)
    , m_client(client)
    , m_sondage(new Sondage([this] { return m_greffon->questions(); }, Sondage::kIntervallePage, this))
    , m_questions(new JsonListModel(this))
    , m_triage(new JsonListModel(this))
    , m_bloquees(new JsonListModel(this))
    , m_revues(new JsonListModel(this))
    , m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); })
{
    // Mise à jour par identifiant : une relecture ne détruit jamais le champ où le propriétaire
    // écrit sa réponse ou sa consigne (le délégué de la ligne est conservé).
    m_questions->setCle({QStringLiteral("id")});
    m_triage->setCle({QStringLiteral("tableau"), QStringLiteral("carte")});
    connect(m_sondage, &Sondage::etatChange, this, &QuestionsViewModel::lectureChange);
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) { lire(reponse.json.object()); });
}

QuestionsViewModel::~QuestionsViewModel() = default;

void QuestionsViewModel::setIntervalle(std::chrono::milliseconds intervalle)
{
    m_sondage->setIntervalle(intervalle);
}

QString QuestionsViewModel::lecture() const { return m_sondage->libelleLuA(); }
QString QuestionsViewModel::erreur() const { return m_sondage->derniereErreur(); }

void QuestionsViewModel::surActivite(bool actif)
{
    m_sondage->setActif(actif);
}

void QuestionsViewModel::surLienRetabli()
{
    actualiser();
}

void QuestionsViewModel::surOubli()
{
    m_sondage->oublier();
    for (JsonListModel *modele : {m_questions, m_triage, m_bloquees, m_revues}) {
        modele->clear();
    }
    m_lue = false;
    m_revuesPresentes = false;
    m_illisibles.clear();
    m_gestes.clear();
    const QStringList brouillons = m_brouillons.keys();
    m_brouillons.clear();
    for (const QString &cle : brouillons) {
        emit brouillonEfface(cle);
    }
    emit listeChange();
}

void QuestionsViewModel::actualiser()
{
    m_sondage->lireMaintenant();
}

void QuestionsViewModel::lire(const QJsonObject &liste)
{
    QJsonArray questions;
    for (const QJsonValue &element : liste.value(QStringLiteral("questions")).toArray()) {
        questions.append(construireQuestion(element.toObject()));
    }
    m_questions->setItems(questions);

    QJsonArray triage;
    m_gestes.clear();
    for (const QJsonValue &element : liste.value(QStringLiteral("triage")).toArray()) {
        const QJsonObject carte = element.toObject();
        triage.append(construireTriage(carte));
        m_gestes.insert(cle(carte.value(QStringLiteral("tableau")).toString(), carte.value(QStringLiteral("carte")).toString()),
                        gestesOfferts(carte));
    }
    m_triage->setItems(triage);

    QJsonArray bloquees;
    for (const QJsonValue &element : liste.value(QStringLiteral("bloquees")).toArray()) {
        bloquees.append(construireBloquee(element.toObject()));
    }
    m_bloquees->setItems(bloquees);

    // Revues des fichiers de pilotage (P6) : seulement si le serveur en publie la clé.
    m_revuesPresentes = liste.contains(QStringLiteral("revues"));
    QJsonArray revues;
    for (const QJsonValue &element : liste.value(QStringLiteral("revues")).toArray()) {
        revues.append(construireRevue(element.toObject()));
    }
    m_revues->setItems(revues);

    m_illisibles = chaines(liste.value(QStringLiteral("tableaux_illisibles")));
    m_lue = true;
    emit listeChange();
}

QJsonObject QuestionsViewModel::construireQuestion(const QJsonObject &question)
{
    const QJsonValue etat = question.value(QStringLiteral("etat"));
    const libelles::Libelle libelle = libelles::etatQuestion(etat);
    const QString identifiant = question.value(QStringLiteral("id")).toString();
    const QString carte = texteOuVide(question.value(QStringLiteral("carte")));
    const QString carteTitre = texteOuVide(question.value(QStringLiteral("carte_titre")));
    const QString projet = question.value(QStringLiteral("projet")).toString();
    return QJsonObject{
        {QStringLiteral("id"), identifiant},
        {QStringLiteral("peutRepondre"), ClientGreffonPoste::identifiantValide(identifiant)},
        {QStringLiteral("texte"), libelles::texte(question.value(QStringLiteral("texte")))},
        {QStringLiteral("contexte"), texteOuVide(question.value(QStringLiteral("contexte")))},
        {QStringLiteral("projet"), ClientGreffonPoste::identifiantValide(projet) ? projet : QString()},
        {QStringLiteral("projetTitre"), libelles::texte(question.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("carte"), carteTitre.isEmpty() ? libelles::texte(question.value(QStringLiteral("carte")))
                                  : carte.isEmpty() ? carteTitre
                                                    : QStringLiteral("%1 (%2)").arg(carteTitre, carte)},
        {QStringLiteral("etatLibelle"), libelle.connu() ? libelle.texte : libelles::texte(etat)},
        {QStringLiteral("etatCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
        {QStringLiteral("motif"), texteOuVide(question.value(QStringLiteral("motif_escalade")))},
        {QStringLiteral("poseeLe"), libelles::date(question.value(QStringLiteral("cree_le")))},
    };
}

QStringList QuestionsViewModel::gestesOfferts(const QJsonObject &carte)
{
    // Sans liste lisible, le geste historique : « reprendre » (la route refuse ce qui ne
    // s'applique pas), comme la page web.
    const QStringList actions = chaines(carte.value(QStringLiteral("actions")));
    return actions.isEmpty() ? QStringList{QStringLiteral("reprendre")} : actions;
}

QJsonObject QuestionsViewModel::construireTriage(const QJsonObject &carte)
{
    const QStringList gestes = gestesOfferts(carte);
    const bool avecConsigne = gestes.contains(QStringLiteral("prolonger")) || gestes.contains(QStringLiteral("relancer"))
        || gestes.contains(QStringLiteral("reprendre"));
    // Un seul bouton de reprise, nommé d'après le geste offert (prolonger > relancer > reprendre).
    const QString libelleReprise = !avecConsigne ? QString()
        : gestes.contains(QStringLiteral("prolonger")) ? libelles::actionTriage(QStringLiteral("prolonger"))
        : gestes.contains(QStringLiteral("relancer"))  ? libelles::actionTriage(QStringLiteral("relancer"))
                                                       : libelles::actionTriage(QStringLiteral("reprendre"));
    const QString genre = carte.value(QStringLiteral("genre")).toString();
    QString aide;
    if (genre == QLatin1String("tours")) {
        aide = QStringLiteral("« Prolonger » accorde un tour de plus : Hermes planifie la suite avec votre consigne.");
    } else if (genre == QLatin1String("cartes")) {
        aide = QStringLiteral("« Prolonger » relève le plafond de cartes : Hermes planifie la suite avec votre consigne.");
    } else if (genre == QLatin1String("sans_plan")) {
        aide = QStringLiteral("« Relancer la planification » fait replanifier Hermes avec votre consigne.");
    } else if (genre == QLatin1String("corrections")) {
        aide = QStringLiteral("Prolonger le plafond de corrections arrivera à l'étape P6.");
    }
    QStringList inconnus;
    for (const QString &geste : gestes) {
        if (libelles::actionTriage(geste).isEmpty()) {
            inconnus.append(geste);
        }
    }
    const QString tableau = carte.value(QStringLiteral("tableau")).toString();
    const QString identifiant = carte.value(QStringLiteral("carte")).toString();
    const bool adressable = ClientGreffonPoste::identifiantValide(tableau) && ClientGreffonPoste::identifiantValide(identifiant);
    const QString projet = carte.value(QStringLiteral("projet")).toString();
    return QJsonObject{
        {QStringLiteral("tableau"), tableau},
        {QStringLiteral("carte"), identifiant},
        {QStringLiteral("adressable"), adressable},
        {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
        {QStringLiteral("projet"), ClientGreffonPoste::identifiantValide(projet) ? projet : QString()},
        {QStringLiteral("projetTitre"), libelles::texte(carte.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("raison"), texteOuVide(carte.value(QStringLiteral("raison")))},
        {QStringLiteral("aide"), aide},
        {QStringLiteral("avecConsigne"), adressable && avecConsigne},
        {QStringLiteral("libelleReprise"), libelleReprise},
        {QStringLiteral("peutConclure"), adressable && gestes.contains(QStringLiteral("conclure"))},
        {QStringLiteral("aideConclure"), gestes.contains(QStringLiteral("conclure"))
             ? QStringLiteral("« Conclure le projet » l'arrête ici : « Terminé » s'il a au moins un tour, sinon « Abandonné ».")
             : QString()},
        {QStringLiteral("gestesInconnus"), inconnus.isEmpty()
             ? QString()
             : QStringLiteral("Geste non pris en charge par la station : %1.").arg(inconnus.join(QStringLiteral(", ")))},
    };
}

QJsonObject QuestionsViewModel::construireBloquee(const QJsonObject &carte)
{
    const bool abandonnee = carte.value(QStringLiteral("abandonnee")) == QJsonValue(true);
    const QString projet = carte.value(QStringLiteral("projet")).toString();
    return QJsonObject{
        {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
        {QStringLiteral("projet"), ClientGreffonPoste::identifiantValide(projet) ? projet : QString()},
        {QStringLiteral("projetTitre"), libelles::texte(carte.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("etatLibelle"), abandonnee ? QStringLiteral("Abandonnée après plusieurs échecs") : QStringLiteral("Bloquée")},
        {QStringLiteral("assigne"), libelles::texte(carte.value(QStringLiteral("assigne")))},
        {QStringLiteral("raison"), libelles::texte(carte.value(QStringLiteral("raison")))},
        {QStringLiteral("carte"), libelles::texte(carte.value(QStringLiteral("carte")))},
    };
}

QJsonObject QuestionsViewModel::construireRevue(const QJsonObject &revue)
{
    const QString projet = revue.value(QStringLiteral("projet")).toString();
    return QJsonObject{
        {QStringLiteral("titre"), libelles::texte(revue.value(QStringLiteral("titre")))},
        {QStringLiteral("projet"), ClientGreffonPoste::identifiantValide(projet) ? projet : QString()},
        {QStringLiteral("projetTitre"), libelles::texte(revue.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("carte"), libelles::texte(revue.value(QStringLiteral("carte")))},
        {QStringLiteral("chemins"), chaines(revue.value(QStringLiteral("chemins"))).join(QLatin1Char('\n'))},
        {QStringLiteral("resume"), texteOuVide(revue.value(QStringLiteral("resume")))},
    };
}

QString QuestionsViewModel::messageReponse(const QJsonObject &resultat)
{
    // Relecture de P4 : le message suit la réponse du greffon, jamais une supposition.
    if (resultat.value(QStringLiteral("reprise_differee")) == QJsonValue(true)) {
        return QStringLiteral("Réponse enregistrée : la carte reprendra à la reprise du projet.");
    }
    if (resultat.value(QStringLiteral("carte_debloquee")) == QJsonValue(true)) {
        return QStringLiteral("Réponse envoyée : la carte reprend.");
    }
    return QStringLiteral("Réponse enregistrée ; la carte n'a pas été relancée (voir le kanban de Hermes).");
}

QString QuestionsViewModel::messageTriage(const QJsonObject &resultat)
{
    if (resultat.value(QStringLiteral("reprise")) != QJsonValue(true)) {
        return QStringLiteral("La carte n'a pas été reprise (voir le kanban de Hermes).");
    }
    const QString action = resultat.value(QStringLiteral("action")).toString();
    if (action == QLatin1String("prolongation")) {
        return QStringLiteral("Plafond relevé : Hermes planifie la suite avec votre consigne.");
    }
    if (action == QLatin1String("relance_planification")) {
        return QStringLiteral("Planification relancée : Hermes planifie avec votre consigne.");
    }
    return QStringLiteral("Carte reprise : elle repart dans le graphe du projet.");
}

void QuestionsViewModel::setBrouillon(const QString &cle, const QString &texte)
{
    if (cle.isEmpty()) {
        return;
    }
    if (texte.isEmpty()) {
        m_brouillons.remove(cle);
    } else {
        m_brouillons.insert(cle, texte);
    }
}

void QuestionsViewModel::effacerBrouillon(const QString &cle)
{
    m_brouillons.remove(cle);
    emit brouillonEfface(cle);
}

void QuestionsViewModel::apresGeste()
{
    m_sondage->lireMaintenant();
    // Le badge des questions suit sans attendre le sondage léger.
    flux()->sondageFond()->lireMaintenant();
}

void QuestionsViewModel::repondre(const QString &question, const QString &reponse)
{
    if (gesteEnCours()) {
        return;
    }
    const QString texte = reponse.trimmed();
    if (texte.isEmpty() || texte.size() > 4000) {
        echouerGeste(QStringLiteral("La réponse doit compter de 1 à 4 000 caractères."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->repondre(question, texte);
    connect(appel, &ApiCall::succeeded, this, [this, question](const ApiResponse &reponseServeur) {
        terminerGeste(messageReponse(reponseServeur.json.object()));
        effacerBrouillon(QStringLiteral("q:") + question);
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // Question fermée entre-temps (409 `question_fermee`) ou autre refus : le message du
        // greffon tel quel, puis la liste relue.
        echouerGeste(erreur);
        apresGeste();
    });
}

void QuestionsViewModel::agirTriage(const QString &tableau, const QString &carte, const QString &geste,
                                    const QString &consigne)
{
    if (gesteEnCours()) {
        return;
    }
    const auto offerts = m_gestes.constFind(cle(tableau, carte));
    if (offerts == m_gestes.constEnd()) {
        echouerGeste(QStringLiteral("Cette carte n'est plus en triage : la liste est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    const bool conclure = geste == QLatin1String("conclure");
    const bool reprise = geste == QLatin1String("reprise");
    const bool offert = conclure ? offerts->contains(QStringLiteral("conclure"))
                                 : offerts->contains(QStringLiteral("prolonger")) || offerts->contains(QStringLiteral("relancer"))
                                       || offerts->contains(QStringLiteral("reprendre"));
    if ((!conclure && !reprise) || !offert) {
        echouerGeste(QStringLiteral("Ce geste n'est pas offert par le greffon pour cette carte."));
        return;
    }
    if (consigne.size() > 8000) {
        echouerGeste(QStringLiteral("La consigne compte 8 000 caractères au plus."));
        return;
    }
    debuterGeste();
    ApiCall *appel = conclure ? m_greffon->conclureTriage(tableau, carte)
                              : m_greffon->reprendreTriage(tableau, carte, consigne.trimmed());
    connect(appel, &ApiCall::succeeded, this, [this, conclure, tableau, carte](const ApiResponse &reponse) {
        const QJsonObject resultat = reponse.json.object();
        if (conclure) {
            terminerGeste(resultat.value(QStringLiteral("conclu")) == QJsonValue(true)
                              ? QStringLiteral("Projet conclu.")
                              : QStringLiteral("Le projet n'a pas été conclu : la carte n'a pas été archivée (voir le kanban de Hermes)."));
        } else {
            terminerGeste(messageTriage(resultat));
        }
        effacerBrouillon(QStringLiteral("t:") + cle(tableau, carte));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

bool QuestionsViewModel::traiterDansLeNavigateur()
{
    // Page Projets du tableau de bord, vue « questions » (apps/interface/src/projets/vue.ts),
    // sous le préfixe éventuel du serveur, comme l'API (ApiClient::resolve).
    QUrlQuery vue;
    vue.addQueryItem(QStringLiteral("vue"), QStringLiteral("questions"));
    const QUrl url = m_client->resolve(QStringLiteral("/projets"), vue);
    if (url.isEmpty()) {
        echouerGeste(QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return false;
    }
    if (!m_ouvreur || !m_ouvreur(url)) {
        echouerGeste(QStringLiteral("Le navigateur du système n'a pas pu être ouvert : %1").arg(url.toString()));
        return false;
    }
    terminerGeste(QStringLiteral("Page Questions du tableau de bord ouverte dans le navigateur."));
    return true;
}

} // namespace acp
