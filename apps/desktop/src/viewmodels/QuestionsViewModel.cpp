#include "viewmodels/QuestionsViewModel.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "gateway/DiscussionsEnAttente.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "viewmodels/Libelles.h"

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

QString identifiantOuVide(const QJsonValue &valeur)
{
    const QString texte = valeur.toString();
    return ClientGreffonPoste::identifiantValide(texte) ? texte : QString();
}

bool vrai(const QJsonValue &valeur)
{
    return valeur == QJsonValue(true);
}

// Textes de la page web (apps/interface/src/chaines.ts, T.projets), mot pour mot.
const QString kNonRelancee = QStringLiteral("La carte n'a pas été relancée.");
const QString kReponseSansReprise =
    QStringLiteral("Réponse enregistrée ; la carte n'a pas été relancée (voir le kanban de Hermes).");
const QString kCarteNonReprise = QStringLiteral("La carte n'a pas été reprise (voir le kanban de Hermes).");

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
{
    // Mise à jour par identifiant : une relecture ne détruit jamais le champ où le propriétaire
    // écrit sa réponse, sa consigne ou son motif (le délégué de la ligne est conservé).
    m_questions->setCle({QStringLiteral("id")});
    // Étape P7 : mêmes sujets que la file de la page web (Projets.tsx, lireQuestions).
    m_sondage->suivre(flux->invalidation(),
                      {QStringLiteral("questions"), QStringLiteral("projets"), QStringLiteral("discussions")});
    m_triage->setCle({QStringLiteral("tableau"), QStringLiteral("carte")});
    m_bloquees->setCle({QStringLiteral("tableau"), QStringLiteral("carte")});
    m_revues->setCle({QStringLiteral("tableau"), QStringLiteral("carte")});
    m_resume = construireResume({});
    m_discussions = construireDiscussions({});
    connect(m_sondage, &Sondage::etatChange, this, &QuestionsViewModel::lectureChange);
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        lire(reponse.json.object());
        // Cinquième section : les discussions en attente, lues par la passerelle avec la file.
        this->flux()->discussions()->lire();
    });
    connect(flux->discussions(), &DiscussionsEnAttente::change, this, &QuestionsViewModel::majDiscussions);
}

void QuestionsViewModel::majDiscussions()
{
    const DiscussionsEnAttente *lecture = flux()->discussions();
    m_resume = construireResume(m_derniereListe, lecture->nombre());
    m_discussions = construireDiscussions(m_derniereListe.value(QStringLiteral("discussions")),
                                          lecture->connues() ? std::optional<QJsonArray>(lecture->sessions()) : std::nullopt);
    emit listeChange();
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
    m_relancables.clear();
    m_revuesOuvertes.clear();
    m_derniereListe = {};
    m_resume = construireResume({});
    m_discussions = construireDiscussions({});
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
    m_relancables.clear();
    for (const QJsonValue &element : liste.value(QStringLiteral("bloquees")).toArray()) {
        const QJsonObject carte = element.toObject();
        const QJsonObject ligne = construireBloquee(carte);
        bloquees.append(ligne);
        if (ligne.value(QStringLiteral("peutRelancer")).toBool()) {
            m_relancables.insert(cle(ligne.value(QStringLiteral("tableau")).toString(), ligne.value(QStringLiteral("carte")).toString()),
                                 ligne.value(QStringLiteral("integration")).toBool());
        }
    }
    m_bloquees->setItems(bloquees);

    // Revues des fichiers de pilotage (P6) : seulement si le serveur en publie la clé.
    m_revuesPresentes = liste.contains(QStringLiteral("revues"));
    QJsonArray revues;
    m_revuesOuvertes.clear();
    for (const QJsonValue &element : liste.value(QStringLiteral("revues")).toArray()) {
        const QJsonObject ligne = construireRevue(element.toObject());
        revues.append(ligne);
        if (ligne.value(QStringLiteral("adressable")).toBool()) {
            m_revuesOuvertes.insert(cle(ligne.value(QStringLiteral("tableau")).toString(), ligne.value(QStringLiteral("carte")).toString()),
                                    true);
        }
    }
    m_revues->setItems(revues);

    m_illisibles = chaines(liste.value(QStringLiteral("tableaux_illisibles")));
    m_derniereListe = liste;
    m_lue = true;
    majDiscussions();
}

QJsonObject QuestionsViewModel::construireQuestion(const QJsonObject &question)
{
    const QJsonValue etat = question.value(QStringLiteral("etat"));
    const QJsonValue chez = question.value(QStringLiteral("chez"));
    const libelles::Libelle libelle = libelles::etatQuestion(etat, chez);
    const QString identifiant = question.value(QStringLiteral("id")).toString();
    const QString carte = texteOuVide(question.value(QStringLiteral("carte")));
    const QString carteTitre = texteOuVide(question.value(QStringLiteral("carte_titre")));
    // « Qui répond » (étape P7, règle unique du greffon) : « Hermes y répond », avec le statut de sa carte
    // « répondre », ou « À vous » ; toute autre valeur est une donnée brute, jamais traduite au hasard.
    QString quiRepond;
    QString quiRepondCle = QStringLiteral("unknown");
    if (chez.toString() == QLatin1String("hermes")) {
        quiRepond = QStringLiteral("Hermes y répond");
        quiRepondCle = QStringLiteral("running");
        const libelles::Libelle statut = libelles::statutCarte(question.value(QStringLiteral("carte_repondre_statut")));
        if (statut.connu()) {
            quiRepond += QStringLiteral(" · carte « répondre » : %1").arg(statut.texte);
        }
    } else if (chez.toString() == QLatin1String("proprietaire")) {
        quiRepond = QStringLiteral("À vous");
        quiRepondCle = QStringLiteral("degraded");
    } else {
        quiRepond = libelles::texte(chez);
    }
    return QJsonObject{
        {QStringLiteral("id"), identifiant},
        {QStringLiteral("peutRepondre"), ClientGreffonPoste::identifiantValide(identifiant)},
        {QStringLiteral("texte"), libelles::texte(question.value(QStringLiteral("texte")))},
        {QStringLiteral("contexte"), texteOuVide(question.value(QStringLiteral("contexte")))},
        {QStringLiteral("projet"), identifiantOuVide(question.value(QStringLiteral("projet")))},
        {QStringLiteral("projetTitre"), libelles::texte(question.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("carte"), carteTitre.isEmpty() ? libelles::texte(question.value(QStringLiteral("carte")))
                                  : carte.isEmpty() ? carteTitre
                                                    : QStringLiteral("%1 (%2)").arg(carteTitre, carte)},
        {QStringLiteral("etatLibelle"), libelle.connu() ? libelle.texte : libelles::texte(etat)},
        {QStringLiteral("etatCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
        {QStringLiteral("quiRepond"), quiRepond},
        {QStringLiteral("quiRepondCle"), quiRepondCle},
        {QStringLiteral("chezHermesAide"), chez.toString() == QLatin1String("hermes")
             ? QStringLiteral("Hermes prépare la réponse par sa carte « répondre » ; vous pouvez répondre vous-même avant lui.")
             : QString()},
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
        // Relecture finale de P7 : le greffon refuse cette prolongation pour de bon (textes.PROLONGATION_P6).
        aide = QStringLiteral("Le plafond de corrections ne se prolonge pas : la relecture qui l'a atteint est close ; "
                              "concluez le projet depuis cette carte.");
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
    return QJsonObject{
        {QStringLiteral("tableau"), tableau},
        {QStringLiteral("carte"), identifiant},
        {QStringLiteral("adressable"), adressable},
        {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
        {QStringLiteral("projet"), identifiantOuVide(carte.value(QStringLiteral("projet")))},
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
    const bool abandonnee = vrai(carte.value(QStringLiteral("abandonnee")));
    const QString tableau = carte.value(QStringLiteral("tableau")).toString();
    const QString identifiant = carte.value(QStringLiteral("carte")).toString();
    const bool adressable = ClientGreffonPoste::identifiantValide(tableau) && ClientGreffonPoste::identifiantValide(identifiant);
    // Étape P7 : la relance n'est offerte que si le greffon la dit possible (`relancable` vrai, jamais déduit) ;
    // sinon la raison qu'il donne (`refus_relance`), ou « Inconnu ».
    const bool relancable = vrai(carte.value(QStringLiteral("relancable")));
    const bool integration = vrai(carte.value(QStringLiteral("integration")));
    const bool quarantaine = vrai(carte.value(QStringLiteral("quarantaine")));
    const bool executant = vrai(carte.value(QStringLiteral("executant")));
    QString aide;
    bool aideAlerte = false;
    if (quarantaine) {
        aide = QStringLiteral("Bloquée pour un secret détecté. Le travail fautif reste en quarantaine sur l'exécutant, jamais "
                              "intégré ni poussé. La relance repart du départ de la carte, sur une branche neuve et en session "
                              "neuve.");
        aideAlerte = true;
    } else if (integration) {
        aide = QStringLiteral("Carte d'intégration, sans agent : « Relancer » rejoue la même fusion des branches, sans consigne. "
                              "Un conflit revient tant qu'aucune branche ne change : récupérez les branches sur l'exécutant "
                              "(git bundle) pour trancher, ou clôturez le projet.");
    } else if (executant) {
        aide = QStringLiteral("L'agent repart d'une session neuve, sur la branche déjà commencée.");
    }
    return QJsonObject{
        {QStringLiteral("tableau"), tableau},
        {QStringLiteral("carte"), identifiant},
        {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
        {QStringLiteral("projet"), identifiantOuVide(carte.value(QStringLiteral("projet")))},
        {QStringLiteral("projetTitre"), libelles::texte(carte.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("etatLibelle"), abandonnee ? QStringLiteral("Abandonnée après plusieurs échecs") : QStringLiteral("Bloquée")},
        {QStringLiteral("assigne"), libelles::texte(carte.value(QStringLiteral("assigne")))},
        {QStringLiteral("raison"), libelles::texte(carte.value(QStringLiteral("raison")))},
        {QStringLiteral("peutRelancer"), relancable && adressable},
        {QStringLiteral("integration"), integration},
        {QStringLiteral("avecConsigne"), relancable && adressable && !integration},
        {QStringLiteral("aide"), relancable && adressable ? aide : QString()},
        {QStringLiteral("aideAlerte"), relancable && adressable && aideAlerte},
        {QStringLiteral("refusRelance"), relancable && adressable ? QString()
                                         : relancable ? QStringLiteral("identifiant de carte illisible.")
                                                      : libelles::texte(carte.value(QStringLiteral("refus_relance")))},
    };
}

QJsonObject QuestionsViewModel::construireRevue(const QJsonObject &revue)
{
    const QString tableau = revue.value(QStringLiteral("tableau")).toString();
    const QString identifiant = revue.value(QStringLiteral("carte")).toString();
    const bool adressable = ClientGreffonPoste::identifiantValide(tableau) && ClientGreffonPoste::identifiantValide(identifiant);
    const QJsonValue diffstat = revue.value(QStringLiteral("diffstat"));
    QString modification = libelles::kInconnu;
    if (diffstat.isObject()) {
        const QJsonObject d = diffstat.toObject();
        modification = QStringLiteral("%1 fichier(s) · %2 ajout(s) · %3 retrait(s)")
                           .arg(libelles::nombre(d.value(QStringLiteral("fichiers"))),
                                libelles::nombre(d.value(QStringLiteral("ajouts"))),
                                libelles::nombre(d.value(QStringLiteral("retraits"))));
    }
    const QStringList chemins = chaines(revue.value(QStringLiteral("chemins")));
    return QJsonObject{
        {QStringLiteral("tableau"), tableau},
        {QStringLiteral("carte"), identifiant},
        {QStringLiteral("adressable"), adressable},
        {QStringLiteral("titre"), libelles::texte(revue.value(QStringLiteral("titre")))},
        {QStringLiteral("projet"), identifiantOuVide(revue.value(QStringLiteral("projet")))},
        {QStringLiteral("projetTitre"), libelles::texte(revue.value(QStringLiteral("projet_titre")))},
        {QStringLiteral("chemins"), chemins.isEmpty() ? libelles::kInconnu : chemins.join(QLatin1Char('\n'))},
        {QStringLiteral("modification"), modification},
        {QStringLiteral("branche"), libelles::texte(revue.value(QStringLiteral("branche")))},
        {QStringLiteral("tete"), libelles::texte(revue.value(QStringLiteral("tete")))},
        {QStringLiteral("resume"), libelles::texte(revue.value(QStringLiteral("resume")))},
        // Le diff reste sur l'exécutant : le greffon le dit (textes.DIFF_SUR_L_EXECUTANT), la page le rend tel quel.
        {QStringLiteral("diff"), texteOuVide(revue.value(QStringLiteral("diff")))},
    };
}

QVariantMap QuestionsViewModel::construireResume(const QJsonObject &liste, int discussions)
{
    // Étape P7 : « À traiter par vous » = compteurs du greffon (questions à vous, décisions, revues, cartes
    // arrêtées), plus les discussions en attente quand elles ont pu être lues (Questions.tsx, aTraiter) ; sinon le
    // total le dit, jamais zéro par défaut.
    const QJsonObject compteurs = liste.value(QStringLiteral("compteurs")).toObject();
    const QJsonValue totalGreffon = compteurs.value(QStringLiteral("a_traiter"));
    const QJsonValue chezHermes = compteurs.value(QStringLiteral("chez_hermes"));
    const bool connu = libelles::estNombre(totalGreffon);
    const bool discussionsConnues = discussions >= 0;
    const int total = connu ? static_cast<int>(totalGreffon.toInteger()) + (discussionsConnues ? discussions : 0) : -1;
    return QVariantMap{
        {QStringLiteral("connu"), connu},
        {QStringLiteral("total"), connu ? QString::number(total) : libelles::kInconnu},
        {QStringLiteral("nombre"), total},
        {QStringLiteral("mention"), connu && !discussionsConnues ? QStringLiteral("(discussions en attente : état inconnu, non comptées)")
                                                                 : QString()},
        {QStringLiteral("chezHermes"), libelles::nombre(chezHermes)},
        {QStringLiteral("questions"), libelles::nombre(compteurs.value(QStringLiteral("questions")))},
        {QStringLiteral("decisions"), libelles::nombre(compteurs.value(QStringLiteral("decisions")))},
        {QStringLiteral("revues"), libelles::nombre(compteurs.value(QStringLiteral("revues")))},
        {QStringLiteral("arretees"), libelles::nombre(compteurs.value(QStringLiteral("arretees")))},
    };
}

QVariantMap QuestionsViewModel::construireDiscussions(const QJsonValue &serveur, const std::optional<QJsonArray> &sessions)
{
    const QJsonObject d = serveur.toObject();
    if (sessions) {
        // Lues par la passerelle (session.active_list) : chaque discussion dont une demande attend votre réponse.
        QVariantList liste;
        for (const QJsonValue &element : *sessions) {
            const QJsonObject s = element.toObject();
            liste.append(QVariantMap{
                {QStringLiteral("cle"), s.value(QStringLiteral("cle")).toString()},
                {QStringLiteral("titre"), libelles::estTexte(s.value(QStringLiteral("titre")))
                                              ? s.value(QStringLiteral("titre")).toString()
                                              : QStringLiteral("Sans titre")},
                {QStringLiteral("etat"), QStringLiteral("En attente d'une réponse")},
                {QStringLiteral("activite"), libelles::date(s.value(QStringLiteral("derniereActivite")))},
                {QStringLiteral("apercu"), libelles::texte(s.value(QStringLiteral("apercu")))},
            });
        }
        return QVariantMap{
            {QStringLiteral("connues"), true},
            {QStringLiteral("etat"), liste.isEmpty() ? QStringLiteral("Aucune discussion en attente.") : QString()},
            {QStringLiteral("sessions"), liste},
            {QStringLiteral("limite"), texteOuVide(d.value(QStringLiteral("limite")))},
        };
    }
    // Illisibles par la passerelle : nombre de requêtes du serveur au client ouvertes dans le processus du tableau de
    // bord (`questions.discussions_en_attente`) s'il le publie ; sinon son message ; jamais zéro.
    const bool suivies = vrai(d.value(QStringLiteral("suivies")));
    const QJsonValue requetes = d.value(QStringLiteral("requetes_ouvertes"));
    QString etat;
    if (suivies && libelles::estNombre(requetes)) {
        etat = QStringLiteral("Requêtes ouvertes dans le tableau de bord : %1").arg(requetes.toInteger());
    } else if (libelles::estTexte(d.value(QStringLiteral("message")))) {
        etat = d.value(QStringLiteral("message")).toString();
    } else {
        etat = QStringLiteral("Discussions : état inconnu (le tableau de bord n'a pas pu être interrogé).");
    }
    return QVariantMap{
        {QStringLiteral("connues"), false},
        {QStringLiteral("etat"), etat},
        {QStringLiteral("sessions"), QVariantList{}},
        {QStringLiteral("limite"), texteOuVide(d.value(QStringLiteral("limite")))},
    };
}

QString QuestionsViewModel::messageReponse(const QJsonObject &resultat)
{
    // Relecture de P4 : le message suit la réponse du greffon, jamais une supposition.
    if (vrai(resultat.value(QStringLiteral("reprise_differee")))) {
        return QStringLiteral("Réponse enregistrée : la carte reprendra à la reprise du projet.");
    }
    if (vrai(resultat.value(QStringLiteral("carte_debloquee")))) {
        return QStringLiteral("Réponse envoyée : la carte reprend.");
    }
    return kReponseSansReprise;
}

QString QuestionsViewModel::messageTriage(const QJsonObject &resultat)
{
    if (!vrai(resultat.value(QStringLiteral("reprise")))) {
        return kCarteNonReprise;
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

QString QuestionsViewModel::messageRelance(const QJsonObject &resultat, bool integration)
{
    // Même règle que la page web (messageRelance de Questions.tsx) : d'après la réponse de l'API seulement.
    if (!vrai(resultat.value(QStringLiteral("relancee")))) {
        return kNonRelancee;
    }
    if (vrai(resultat.value(QStringLiteral("branche_neuve")))) {
        return QStringLiteral("La carte repart sur une branche neuve, en session neuve. Le travail en quarantaine n'est pas repris.");
    }
    if (integration) {
        return QStringLiteral("La carte repart : l'exécutant rejoue la même fusion.");
    }
    return vrai(resultat.value(QStringLiteral("session_neuve")))
        ? QStringLiteral("La carte repart : l'agent reprend d'une session neuve, sur la branche déjà commencée.")
        : QStringLiteral("La carte repart.");
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
        const QString message = messageReponse(reponseServeur.json.object());
        terminerGeste(message, message == kReponseSansReprise);
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
            const bool conclu = vrai(resultat.value(QStringLiteral("conclu")));
            terminerGeste(conclu ? QStringLiteral("Projet conclu.")
                                 : QStringLiteral("Le projet n'a pas été conclu : la carte n'a pas été archivée (voir le kanban de Hermes)."),
                          !conclu);
        } else {
            const QString message = messageTriage(resultat);
            terminerGeste(message, message == kCarteNonReprise);
        }
        effacerBrouillon(QStringLiteral("t:") + cle(tableau, carte));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

void QuestionsViewModel::relancer(const QString &tableau, const QString &carte, const QString &consigne)
{
    if (gesteEnCours()) {
        return;
    }
    const auto relancable = m_relancables.constFind(cle(tableau, carte));
    if (relancable == m_relancables.constEnd()) {
        // Carte qui n'est plus servie relançable (relancée ailleurs, débloquée, projet en pause…) : rien ne part.
        echouerGeste(QStringLiteral("Cette carte n'est pas relançable selon la dernière lecture : la liste est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    const bool integration = *relancable;
    // Carte d'intégration : aucune consigne n'est jamais envoyée (le greffon la refuserait, `consigne_sans_objet`).
    const QString texte = integration ? QString() : consigne.trimmed();
    if (texte.size() > 4000) {
        echouerGeste(QStringLiteral("La consigne compte 4 000 caractères au plus."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->relancerCarte(tableau, carte, texte);
    connect(appel, &ApiCall::succeeded, this, [this, tableau, carte, integration](const ApiResponse &reponse) {
        const QJsonObject resultat = reponse.json.object();
        QString message = messageRelance(resultat, integration);
        const libelles::Libelle statut = libelles::statutCarte(resultat.value(QStringLiteral("statut_apres")));
        if (statut.connu()) {
            message += QStringLiteral(" Statut : %1.").arg(statut.texte);
        } else if (libelles::estTexte(resultat.value(QStringLiteral("statut_apres")))) {
            message += QStringLiteral(" Statut : %1.").arg(resultat.value(QStringLiteral("statut_apres")).toString());
        }
        terminerGeste(message, !vrai(resultat.value(QStringLiteral("relancee"))));
        effacerBrouillon(QStringLiteral("r:") + cle(tableau, carte));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // Refus du greffon (409 projet en pause, carte non arrêtée, quarantaine…) : son message tel quel.
        echouerGeste(erreur);
        apresGeste();
    });
}

void QuestionsViewModel::accepterRevue(const QString &tableau, const QString &carte)
{
    if (gesteEnCours()) {
        return;
    }
    if (!m_revuesOuvertes.contains(cle(tableau, carte))) {
        echouerGeste(QStringLiteral("Cette revue n'est plus en attente selon la dernière lecture : la liste est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->accepterRevue(tableau, carte);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &) {
        terminerGeste(QStringLiteral("Revue acceptée : la carte est terminée."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

void QuestionsViewModel::refuserRevue(const QString &tableau, const QString &carte, const QString &motif)
{
    if (gesteEnCours()) {
        return;
    }
    if (!m_revuesOuvertes.contains(cle(tableau, carte))) {
        echouerGeste(QStringLiteral("Cette revue n'est plus en attente selon la dernière lecture : la liste est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    const QString texte = motif.trimmed();
    if (texte.isEmpty() || texte.size() > 1000) {
        echouerGeste(QStringLiteral("Le motif du refus doit compter de 1 à 1 000 caractères."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->refuserRevue(tableau, carte, texte);
    connect(appel, &ApiCall::succeeded, this, [this, tableau, carte](const ApiResponse &) {
        terminerGeste(QStringLiteral("Revue refusée : la carte revient à l'exécutant avec votre motif."));
        effacerBrouillon(QStringLiteral("m:") + cle(tableau, carte));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

} // namespace acp
