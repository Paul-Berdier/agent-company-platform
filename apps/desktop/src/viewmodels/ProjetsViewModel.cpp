#include "viewmodels/ProjetsViewModel.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "api/IdempotencyKey.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "events/VeilleKanban.h"
#include "models/JsonListModel.h"
#include "viewmodels/AccueilViewModel.h"
#include "viewmodels/Libelles.h"

#include <QDesktopServices>
#include <QJsonDocument>
#include <QSet>

#include <algorithm>

namespace acp {

namespace {

const QStringList kProfilsConnus = {QStringLiteral("base"), QStringLiteral("web"), QStringLiteral("recherche"),
                                    QStringLiteral("donnees")};

//! Ordre d'affichage des rôles (graphe du cahier P4 § 6), comme ORDRE_DES_ROLES du web.
const QStringList kOrdreDesRoles = {QStringLiteral("exploration"), QStringLiteral("planification"),
                                    QStringLiteral("implementation"), QStringLiteral("relecture"),
                                    QStringLiteral("correction"), QStringLiteral("hermes"),
                                    QStringLiteral("synthese"), QStringLiteral("repondre"),
                                    QStringLiteral("triage")};

QString libelleOuBrut(const QString &libelle, const QJsonValue &brut)
{
    return libelle.isEmpty() ? libelles::texte(brut) : libelle;
}

QString depot(const QJsonValue &valeur)
{
    if (valeur.isNull()) {
        return QStringLiteral("Sans dépôt");
    }
    return libelles::texte(valeur);
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

QString sur(const QJsonValue &a, const QJsonValue &b)
{
    if (!libelles::estNombre(a) || !libelles::estNombre(b)) {
        return libelles::kInconnu;
    }
    return QStringLiteral("%1 sur %2").arg(a.toInteger()).arg(b.toInteger());
}

bool releveExiste(const QJsonObject &voie)
{
    // Un relevé, même périmé : état connu et date de relevé présente (NouveauProjet.tsx).
    const QJsonValue releve = voie.value(QStringLiteral("releve_le"));
    const bool date = releve.isDouble() ? releve.toDouble() != 0 : libelles::estTexte(releve);
    return !voie.isEmpty() && voie.value(QStringLiteral("etat")).toString() != QLatin1String("inconnu") && date;
}

} // namespace

ProjetsViewModel::ProjetsViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                                   QObject *parent)
    : PageViewModel(flux, parent)
    , m_client(client)
    , m_greffon(greffon)
    , m_liste(new Sondage([this] { return m_greffon->projets(); }, Sondage::kIntervallePage, this))
    , m_detailSondage(new Sondage([this] { return m_greffon->projet(m_projetOuvert); }, Sondage::kIntervallePage, this))
    , m_projets(new JsonListModel(this))
    , m_cartes(new JsonListModel(this))
    , m_questionsDuProjet(new JsonListModel(this))
    , m_tours(new JsonListModel(this))
    , m_journal(new JsonListModel(this))
    , m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); })
{
    // Liste relue par identifiant : la liste garde son défilement et ses délégués.
    m_projets->setCle({QStringLiteral("id")});
    // Étape P7 : mêmes sujets que la page web (Projets.tsx pour la liste, DetailProjet.tsx pour le détail).
    m_liste->suivre(flux->invalidation(), {QStringLiteral("projets"), QStringLiteral("questions"), QStringLiteral("poste"),
                                           QStringLiteral("notifications"), QStringLiteral("pause")});
    m_detailSondage->suivre(flux->invalidation(),
                            {QStringLiteral("projets"), QStringLiteral("questions"), QStringLiteral("pause")});
    m_pause = AccueilViewModel::construireCartePause({});
    viderDetail();
    majFormulaire();
    for (Sondage *sondage : {m_liste, m_detailSondage}) {
        connect(sondage, &Sondage::etatChange, this, &ProjetsViewModel::lectureChange);
    }
    connect(m_liste, &Sondage::lu, this, [this](const ApiResponse &reponse) { lireListe(reponse.json.object()); });
    connect(m_detailSondage, &Sondage::lu, this, [this](const ApiResponse &reponse) { lireDetail(reponse.json.object()); });

    // Veille du kanban du projet affiché : une relecture par changement du tableau, et un
    // sondage du détail ralenti à 60 s tant qu'elle est prête.
    VeilleKanban *veille = flux->veille();
    connect(veille, &VeilleKanban::etatChange, this, [this, veille] {
        m_detailSondage->setIntervalle(veille->etat() == VeilleKanban::Etat::Prete ? m_intervalleVeille
                                                                                    : m_intervallePage);
        emit veilleChange();
    });
    connect(flux, &EventStreamService::tableauChange, this, [this](const QString &tableau) {
        if (m_vue == QLatin1String("detail") && tableau == m_tableauOuvert) {
            m_detailSondage->lireMaintenant();
        }
    });
}

ProjetsViewModel::~ProjetsViewModel() = default;

void ProjetsViewModel::setIntervalles(std::chrono::milliseconds page, std::chrono::milliseconds detailVeille)
{
    m_intervallePage = page;
    m_intervalleVeille = detailVeille;
    m_liste->setIntervalle(page);
    m_detailSondage->setIntervalle(flux()->veille()->etat() == VeilleKanban::Etat::Prete ? detailVeille : page);
}

QString ProjetsViewModel::lectureListe() const { return m_liste->libelleLuA(); }
QString ProjetsViewModel::erreurListe() const { return m_liste->derniereErreur(); }
QString ProjetsViewModel::lectureDetail() const { return m_detailSondage->libelleLuA(); }
QString ProjetsViewModel::erreurDetail() const { return m_detailSondage->derniereErreur(); }

QString ProjetsViewModel::etatVeille() const
{
    const VeilleKanban *veille = flux()->veille();
    const QString page = QStringLiteral("relecture toutes les %1 s").arg(m_intervallePage.count() / 1000);
    switch (veille->etat()) {
    case VeilleKanban::Etat::Arretee:
        return QStringLiteral("Veille du kanban arrêtée : %1.").arg(page);
    case VeilleKanban::Etat::Prete:
        return QStringLiteral("Veille du kanban prête : le projet est relu à chaque changement de son tableau.");
    case VeilleKanban::Etat::Preparation:
        return QStringLiteral("Veille du kanban en cours d'ouverture : %1.").arg(page);
    case VeilleKanban::Etat::Reconnexion:
        return QStringLiteral("Veille du kanban en reconnexion (%1) : %2.").arg(veille->raison(), page);
    case VeilleKanban::Etat::Refusee:
        return QStringLiteral("Veille du kanban refusée (%1) : %2.").arg(veille->raison(), page);
    }
    return libelles::kInconnu;
}

// --- Activité et navigation ---------------------------------------------------------------

void ProjetsViewModel::surActivite(bool)
{
    majSondages();
    majVeille();
}

void ProjetsViewModel::surLienRetabli()
{
    actualiser();
}

void ProjetsViewModel::majSondages()
{
    m_liste->setActif(actif() && m_vue == QLatin1String("liste"));
    m_detailSondage->setActif(actif() && m_vue == QLatin1String("detail") && !m_projetOuvert.isEmpty());
}

void ProjetsViewModel::majVeille()
{
    VeilleKanban *veille = flux()->veille();
    if (actif() && m_vue == QLatin1String("detail") && !m_tableauOuvert.isEmpty()) {
        veille->surveiller(m_tableauOuvert);
    } else if (veille->etat() != VeilleKanban::Etat::Arretee) {
        veille->arreter();
    }
}

void ProjetsViewModel::changerVue(const QString &vue)
{
    if (vue == m_vue) {
        return;
    }
    m_vue = vue;
    emit vueChange();
    majSondages();
    majVeille();
}

void ProjetsViewModel::surOubli()
{
    m_liste->oublier();
    m_detailSondage->oublier();
    m_projets->clear();
    m_listeLue = false;
    m_pause = AccueilViewModel::construireCartePause({});
    viderDetail();
    m_projetOuvert.clear();
    // Formulaire : catalogue, relevé du poste, choix et clé d'idempotence de l'ancien serveur.
    m_cle.clear();
    m_catalogue = {};
    m_poste = {};
    m_catalogueLu = false;
    m_posteLu = false;
    m_erreurCatalogue.clear();
    m_erreurPoste.clear();
    m_depot.clear();
    m_voie.clear();
    m_modele.clear();
    majFormulaire();
    changerVue(QStringLiteral("liste"));
    emit listeChange();
}

void ProjetsViewModel::afficherListe()
{
    effacerGeste();
    changerVue(QStringLiteral("liste"));
}

void ProjetsViewModel::ouvrirProjet(const QString &identifiant)
{
    if (!ClientGreffonPoste::identifiantValide(identifiant)) {
        echouerGeste(QStringLiteral("Identifiant de projet illisible : ouverture refusée par la station."));
        return;
    }
    const bool memeProjet = identifiant == m_projetOuvert;
    if (!memeProjet) {
        viderDetail();
        m_projetOuvert = identifiant;
    }
    const bool dejaActif = m_detailSondage->actif();
    if (m_vue != QLatin1String("detail")) {
        m_vue = QStringLiteral("detail");
        majSondages();
        majVeille();
    }
    emit vueChange();
    if (dejaActif && !memeProjet) {
        m_detailSondage->lireMaintenant();
    }
}

void ProjetsViewModel::afficherNouveau()
{
    effacerGeste();
    if (m_cle.isEmpty()) {
        m_cle = makeIdempotencyKey(QStringLiteral("projet"));
    }
    m_depot.clear();
    m_voie.clear();
    m_modele.clear();
    changerVue(QStringLiteral("nouveau"));
    lireFormulaire();
}

void ProjetsViewModel::actualiser()
{
    if (m_vue == QLatin1String("liste")) {
        m_liste->lireMaintenant();
    } else if (m_vue == QLatin1String("detail")) {
        m_detailSondage->lireMaintenant();
    } else {
        lireFormulaire();
    }
}

// --- Liste ----------------------------------------------------------------------------------

void ProjetsViewModel::lireListe(const QJsonObject &liste)
{
    QJsonArray lignes;
    for (const QJsonValue &element : liste.value(QStringLiteral("projets")).toArray()) {
        const QJsonObject projet = element.toObject();
        if (ClientGreffonPoste::identifiantValide(projet.value(QStringLiteral("id")).toString())) {
            lignes.append(construireLigneProjet(projet));
        }
    }
    m_projets->setItems(lignes);
    m_pause = AccueilViewModel::construireCartePause(liste);
    m_listeLue = true;
    flux()->noterProjets(liste);
    emit listeChange();
}

QJsonObject ProjetsViewModel::construireLigneProjet(const QJsonObject &projet)
{
    const QJsonValue etat = projet.value(QStringLiteral("etat"));
    const libelles::Libelle libelle = libelles::etatProjet(etat, projet.value(QStringLiteral("etat_derive")));
    const QJsonObject compteurs = projet.value(QStringLiteral("compteurs")).toObject();
    const QJsonObject plafonds = projet.value(QStringLiteral("plafonds")).toObject();
    const QJsonValue questions = projet.value(QStringLiteral("questions_ouvertes"));
    const QJsonValue note = projet.value(QStringLiteral("derniere_note"));
    QString tour = libelles::kInconnu;
    if (libelles::estNombre(projet.value(QStringLiteral("tour")))) {
        tour = libelles::estNombre(plafonds.value(QStringLiteral("tours")))
            ? QStringLiteral("Tour %1 sur %2").arg(projet.value(QStringLiteral("tour")).toInteger())
                  .arg(plafonds.value(QStringLiteral("tours")).toInteger())
            : QStringLiteral("Tour %1").arg(projet.value(QStringLiteral("tour")).toInteger());
    }
    return QJsonObject{
        {QStringLiteral("id"), projet.value(QStringLiteral("id")).toString()},
        {QStringLiteral("titre"), libelles::texte(projet.value(QStringLiteral("titre")))},
        {QStringLiteral("etatLibelle"), libelle.connu() ? libelle.texte : libelles::texte(etat)},
        {QStringLiteral("etatCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
        {QStringLiteral("etatConnu"), libelle.connu()},
        {QStringLiteral("profil"), libelleOuBrut(libelles::profil(projet.value(QStringLiteral("profil"))),
                                                 projet.value(QStringLiteral("profil")))},
        {QStringLiteral("depot"), depot(projet.value(QStringLiteral("depot")))},
        {QStringLiteral("cartes"), sur(compteurs.value(QStringLiteral("faites")), compteurs.value(QStringLiteral("total")))},
        {QStringLiteral("enCours"), libelles::nombre(compteurs.value(QStringLiteral("en_cours")))},
        {QStringLiteral("attentePoste"), libelles::nombre(compteurs.value(QStringLiteral("en_attente_du_poste")))},
        {QStringLiteral("bloquees"), libelles::nombre(compteurs.value(QStringLiteral("bloquees")))},
        {QStringLiteral("triage"), libelles::nombre(compteurs.value(QStringLiteral("triage")))},
        {QStringLiteral("questions"), libelles::nombre(questions)},
        {QStringLiteral("questionsEnAttente"), libelles::estNombre(questions) && questions.toInteger() > 0},
        {QStringLiteral("derniereNote"), libelles::estTexte(note) ? note.toString() : QString()},
        {QStringLiteral("noteTronquee"), projet.value(QStringLiteral("derniere_note_tronquee")).toBool()},
        {QStringLiteral("tour"), tour},
        {QStringLiteral("creeLe"), libelles::date(projet.value(QStringLiteral("cree_le")))},
    };
}

// --- Détail ---------------------------------------------------------------------------------

void ProjetsViewModel::viderDetail()
{
    ++m_generationDetail;
    m_detailLu = false;
    m_tableauOuvert.clear();
    m_etatProjet.clear();
    m_detail = construireDetail({});
    m_cartes->clear();
    m_questionsDuProjet->clear();
    m_tours->clear();
    m_journal->clear();
    m_carteLue.clear();
    emit detailChange();
    emit carteLueChange();
}

void ProjetsViewModel::lireDetail(const QJsonObject &reponse)
{
    const QJsonObject projet = reponse.value(QStringLiteral("projet")).toObject();
    if (projet.value(QStringLiteral("id")).toString() != m_projetOuvert) {
        return; // réponse d'un projet quitté entre-temps
    }
    m_detail = construireDetail(projet);
    m_cartes->setItems(construireCartes(projet.value(QStringLiteral("cartes")).toArray()));
    QJsonArray questions;
    for (const QJsonValue &element : projet.value(QStringLiteral("questions_ouvertes")).toArray()) {
        const QJsonObject question = element.toObject();
        const libelles::Libelle etat = libelles::etatQuestion(question.value(QStringLiteral("etat")),
                                                              question.value(QStringLiteral("chez")));
        questions.append(QJsonObject{
            {QStringLiteral("id"), libelles::texte(question.value(QStringLiteral("id")))},
            {QStringLiteral("texte"), libelles::texte(question.value(QStringLiteral("texte")))},
            {QStringLiteral("etatLibelle"), etat.connu() ? etat.texte : libelles::texte(question.value(QStringLiteral("etat")))},
            {QStringLiteral("etatCle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
        });
    }
    m_questionsDuProjet->setItems(questions);
    QJsonArray tours;
    for (const QJsonValue &element : projet.value(QStringLiteral("tours")).toArray()) {
        const QJsonObject tour = element.toObject();
        tours.append(QJsonObject{
            {QStringLiteral("tour"), QStringLiteral("Tour %1").arg(libelles::nombre(tour.value(QStringLiteral("tour"))))},
            {QStringLiteral("resume"), libelles::texte(tour.value(QStringLiteral("resume")))},
            {QStringLiteral("decisions"), chaines(tour.value(QStringLiteral("decisions"))).join(QLatin1Char('\n'))},
        });
    }
    m_tours->setItems(tours);
    m_journal->setItems(construireJournal(projet.value(QStringLiteral("journal")).toArray()));
    m_detailLu = true;
    m_etatProjet = projet.value(QStringLiteral("etat")).toString();
    const QString tableau = projet.value(QStringLiteral("tableau")).toString();
    const bool nouveauTableau = tableau != m_tableauOuvert;
    m_tableauOuvert = ClientGreffonPoste::identifiantValide(tableau) ? tableau : QString();
    emit detailChange();
    if (nouveauTableau) {
        majVeille();
    }
}

QVariantMap ProjetsViewModel::construireDetail(const QJsonObject &projet)
{
    const QJsonValue etat = projet.value(QStringLiteral("etat"));
    const libelles::Libelle libelle = libelles::etatProjet(etat, projet.value(QStringLiteral("etat_derive")));
    const QJsonObject plafonds = projet.value(QStringLiteral("plafonds")).toObject();
    const QJsonObject restants = projet.value(QStringLiteral("restants")).toObject();
    const QJsonObject compteurs = projet.value(QStringLiteral("compteurs")).toObject();
    const QJsonValue resultat = projet.value(QStringLiteral("resultat"));
    const QJsonObject detailResultat = resultat.toObject();
    const QString origine = libelles::origine(projet.value(QStringLiteral("origine")));
    const QJsonValue termine = projet.value(QStringLiteral("termine_le"));
    const QJsonValue exploration = projet.value(QStringLiteral("exploration"));
    const QString etatCode = etat.toString();
    const QString reponses = projet.value(QStringLiteral("reponses")).toString();
    const bool avecDepot = libelles::estTexte(projet.value(QStringLiteral("depot")));
    const bool adressable = ClientGreffonPoste::identifiantValide(projet.value(QStringLiteral("id")).toString());
    return QVariantMap{
        {QStringLiteral("id"), libelles::texte(projet.value(QStringLiteral("id")))},
        {QStringLiteral("titre"), libelles::texte(projet.value(QStringLiteral("titre")))},
        {QStringLiteral("tableau"), libelles::texte(projet.value(QStringLiteral("tableau")))},
        {QStringLiteral("objectif"), libelles::texte(projet.value(QStringLiteral("objectif")))},
        {QStringLiteral("etatLibelle"), libelle.connu() ? libelle.texte : libelles::texte(etat)},
        {QStringLiteral("etatCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
        {QStringLiteral("profil"), libelleOuBrut(libelles::profil(projet.value(QStringLiteral("profil"))),
                                                 projet.value(QStringLiteral("profil")))},
        {QStringLiteral("depot"), depot(projet.value(QStringLiteral("depot")))},
        // « Qui répond » se lit « Vous » dans le détail (« Moi » reste le choix du formulaire, relecture finale de
        // P7) ; sans dépôt, il est sans objet (aucune question ne naît d'un projet sans dépôt, D42).
        {QStringLiteral("reponses"), !avecDepot ? QStringLiteral("Sans objet (projet sans dépôt)")
                                     : reponses == QLatin1String("proprietaire") ? QStringLiteral("Vous")
                                     : reponses == QLatin1String("hermes_d_abord") ? QStringLiteral("Hermes d'abord")
                                                                                   : libelles::texte(projet.value(QStringLiteral("reponses")))},
        {QStringLiteral("reponsesCode"), reponses == QLatin1String("proprietaire") ? reponses : QStringLiteral("hermes_d_abord")},
        {QStringLiteral("peutChangerReponses"), adressable && avecDepot
                                                    && (etatCode == QLatin1String("creation") || etatCode == QLatin1String("actif")
                                                        || etatCode == QLatin1String("en_pause"))},
        {QStringLiteral("peutClore"), adressable && (etatCode == QLatin1String("actif") || etatCode == QLatin1String("en_pause"))},
        {QStringLiteral("origine"), origine.isEmpty() ? libelles::texte(projet.value(QStringLiteral("origine")))
                                                      : QStringLiteral("Lancé depuis %1").arg(origine)},
        {QStringLiteral("tour"), sur(projet.value(QStringLiteral("tour")), plafonds.value(QStringLiteral("tours")))},
        {QStringLiteral("cartesCreees"), sur(projet.value(QStringLiteral("cartes_creees")), plafonds.value(QStringLiteral("cartes")))},
        {QStringLiteral("corrections"), libelles::nombre(plafonds.value(QStringLiteral("corrections")))},
        {QStringLiteral("restants"), libelles::estNombre(restants.value(QStringLiteral("tours")))
                                             && libelles::estNombre(restants.value(QStringLiteral("cartes")))
             ? QStringLiteral("%1 tours, %2 cartes").arg(restants.value(QStringLiteral("tours")).toInteger())
                   .arg(restants.value(QStringLiteral("cartes")).toInteger())
             : libelles::kInconnu},
        {QStringLiteral("cartesFaites"), sur(compteurs.value(QStringLiteral("faites")), compteurs.value(QStringLiteral("total")))},
        {QStringLiteral("exploration"), libelles::estTexte(exploration) ? exploration.toString() : QString()},
        {QStringLiteral("resultat"), resultat.isObject() ? libelles::texte(detailResultat.value(QStringLiteral("texte"))) : QString()},
        {QStringLiteral("resultatTronque"), detailResultat.value(QStringLiteral("tronque")).toBool()},
        {QStringLiteral("resultatTour"), resultat.isObject() ? libelles::nombre(detailResultat.value(QStringLiteral("tour"))) : QString()},
        {QStringLiteral("creeLe"), libelles::date(projet.value(QStringLiteral("cree_le")))},
        {QStringLiteral("termineLe"), termine.isDouble() ? libelles::date(termine) : QString()},
        {QStringLiteral("peutMettreEnPause"), etat.toString() == QLatin1String("actif")},
        {QStringLiteral("peutReprendre"), etat.toString() == QLatin1String("en_pause")},
    };
}

QJsonArray ProjetsViewModel::construireCartes(const QJsonArray &cartes)
{
    QList<QJsonObject> lignes;
    for (const QJsonValue &element : cartes) {
        const QJsonObject carte = element.toObject();
        const QJsonValue role = carte.value(QStringLiteral("role"));
        const QJsonValue statut = carte.value(QStringLiteral("statut"));
        const libelles::Libelle libelle = libelles::statutCarte(statut);
        const QJsonValue resume = carte.value(QStringLiteral("resume"));
        const QJsonValue effort = carte.value(QStringLiteral("effort"));
        const QJsonValue palier = carte.value(QStringLiteral("palier"));
        const QJsonValue mention = carte.value(QStringLiteral("mention"));
        const QJsonValue identifiant = carte.value(QStringLiteral("carte"));
        const int rang = static_cast<int>(kOrdreDesRoles.indexOf(role.toString()));
        lignes.append(QJsonObject{
            {QStringLiteral("rang"), rang < 0 ? static_cast<int>(kOrdreDesRoles.size()) : rang},
            {QStringLiteral("carte"), libelles::estTexte(identifiant) ? identifiant.toString() : QString()},
            {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
            {QStringLiteral("groupe"), libelleOuBrut(libelles::role(role), role)},
            {QStringLiteral("statutLibelle"), libelle.connu() ? libelle.texte : libelles::texte(statut)},
            {QStringLiteral("statutCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
            {QStringLiteral("voie"), libelleOuBrut(libelles::voie(carte.value(QStringLiteral("voie"))),
                                                   carte.value(QStringLiteral("voie")))},
            {QStringLiteral("tour"), libelles::nombre(carte.value(QStringLiteral("tour")))},
            {QStringLiteral("modele"), libelles::texte(carte.value(QStringLiteral("modele")))},
            {QStringLiteral("modeleServi"), libelles::texte(carte.value(QStringLiteral("modele_servi")))},
            {QStringLiteral("effort"), libelles::estTexte(effort) ? effort.toString() : QStringLiteral("Par défaut")},
            {QStringLiteral("palier"), libelleOuBrut(libelles::palier(palier), palier)},
            {QStringLiteral("mention"), libelles::estTexte(mention) ? mention.toString() : QString()},
            {QStringLiteral("resume"), libelles::estTexte(resume) ? resume.toString() : QString()},
            {QStringLiteral("resumeTronque"), carte.value(QStringLiteral("resume_tronque")).toBool()},
            {QStringLiteral("resumeLongueur"), libelles::nombre(carte.value(QStringLiteral("resume_longueur")))},
        });
    }
    std::stable_sort(lignes.begin(), lignes.end(), [](const QJsonObject &a, const QJsonObject &b) {
        return a.value(QStringLiteral("rang")).toInt() < b.value(QStringLiteral("rang")).toInt();
    });
    QJsonArray resultat;
    for (const QJsonObject &ligne : std::as_const(lignes)) {
        resultat.append(ligne);
    }
    return resultat;
}

QJsonArray ProjetsViewModel::construireJournal(const QJsonArray &journal)
{
    QJsonArray lignes;
    for (const QJsonValue &element : journal) {
        const QJsonObject entree = element.toObject();
        const QJsonValue action = entree.value(QStringLiteral("action"));
        const QJsonValue cible = entree.value(QStringLiteral("cible"));
        const QJsonValue detail = entree.value(QStringLiteral("detail"));
        QString texteDetail;
        if (libelles::estTexte(detail)) {
            texteDetail = detail.toString();
        } else if (detail.isObject() || detail.isArray()) {
            texteDetail = QString::fromUtf8(detail.isObject() ? QJsonDocument(detail.toObject()).toJson(QJsonDocument::Compact)
                                                              : QJsonDocument(detail.toArray()).toJson(QJsonDocument::Compact));
        }
        lignes.append(QJsonObject{
            {QStringLiteral("quand"), libelles::date(entree.value(QStringLiteral("quand")))},
            {QStringLiteral("acteur"), libelles::acteurJournal(entree.value(QStringLiteral("acteur")))},
            {QStringLiteral("action"), libelleOuBrut(libelles::actionJournal(action), action)},
            {QStringLiteral("cible"), libelles::estTexte(cible) ? cible.toString() : QString()},
            {QStringLiteral("detail"), texteDetail},
        });
    }
    return lignes;
}

void ProjetsViewModel::lireCarteEnEntier(const QString &carte)
{
    const quint64 generation = m_generationDetail;
    m_carteLue = QVariantMap{{QStringLiteral("carte"), carte}, {QStringLiteral("chargement"), true}};
    emit carteLueChange();
    ApiCall *appel = m_greffon->carteDuProjet(m_projetOuvert, carte);
    connect(appel, &ApiCall::succeeded, this, [this, generation, carte](const ApiResponse &reponse) {
        if (generation != m_generationDetail) {
            return;
        }
        const QJsonObject lue = reponse.json.object().value(QStringLiteral("carte")).toObject();
        const libelles::Libelle statut = libelles::statutCarte(lue.value(QStringLiteral("statut")));
        const QJsonValue resume = lue.value(QStringLiteral("resume"));
        const bool tronque = lue.value(QStringLiteral("tronque")).toBool();
        m_carteLue = QVariantMap{
            {QStringLiteral("carte"), carte},
            {QStringLiteral("chargement"), false},
            {QStringLiteral("titre"), libelles::texte(lue.value(QStringLiteral("titre")))},
            {QStringLiteral("statut"), statut.connu() ? statut.texte : libelles::texte(lue.value(QStringLiteral("statut")))},
            {QStringLiteral("resume"), libelles::estTexte(resume) ? resume.toString() : QString()},
            {QStringLiteral("aucunResume"), !libelles::estTexte(resume)},
            {QStringLiteral("longueur"), libelles::nombre(lue.value(QStringLiteral("longueur")))},
            {QStringLiteral("tronque"), tronque},
            {QStringLiteral("borne"), tronque ? QStringLiteral("Texte borné à 100 000 caractères par le greffon.") : QString()},
            {QStringLiteral("erreur"), QString()},
        };
        emit carteLueChange();
    });
    connect(appel, &ApiCall::failed, this, [this, generation, carte](const ApiError &erreur) {
        if (generation != m_generationDetail) {
            return;
        }
        m_carteLue = QVariantMap{{QStringLiteral("carte"), carte},
                                 {QStringLiteral("chargement"), false},
                                 {QStringLiteral("erreur"), messageDuRefus(erreur)}};
        emit carteLueChange();
    });
}

void ProjetsViewModel::fermerCarteLue()
{
    m_carteLue.clear();
    emit carteLueChange();
}

void ProjetsViewModel::apresGesteProjet(const QString &message)
{
    terminerGeste(message);
    m_detailSondage->lireMaintenant();
}

void ProjetsViewModel::mettreEnPause()
{
    if (gesteEnCours() || m_projetOuvert.isEmpty()) {
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->mettreProjetEnPause(m_projetOuvert);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const qsizetype n = reponse.json.object().value(QStringLiteral("cartes_planifiees")).toArray().size();
        apresGesteProjet(QStringLiteral("Projet mis en pause : %1 carte(s) suspendue(s) jusqu'à la reprise.").arg(n));
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        m_detailSondage->lireMaintenant();
    });
}

void ProjetsViewModel::reprendre()
{
    if (gesteEnCours() || m_projetOuvert.isEmpty()) {
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->reprendreProjet(m_projetOuvert);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const qsizetype n = reponse.json.object().value(QStringLiteral("cartes_reveillees")).toArray().size();
        apresGesteProjet(QStringLiteral("Projet repris : %1 carte(s) réveillée(s).").arg(n));
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        m_detailSondage->lireMaintenant();
    });
}

QString ProjetsViewModel::messageReglageReponses(const QJsonObject &resultat)
{
    return QStringLiteral("Réglage enregistré pour les questions suivantes. Questions ouvertes qui gardent leur traitement : %1")
        .arg(libelles::nombre(resultat.value(QStringLiteral("questions_ouvertes_inchangees"))));
}

QString ProjetsViewModel::messageCloture(const QJsonObject &resultat)
{
    // Même lecture que la page web (Cloture de DetailProjet.tsx), d'après la réponse seulement.
    const QString etat = resultat.value(QStringLiteral("etat")).toString();
    QString message = etat == QLatin1String("termine")
        ? QStringLiteral("Projet clos : terminé.")
        : etat == QLatin1String("abandonne")
            ? QStringLiteral("Projet clos : abandonné (la synthèse du tour en cours n'était pas faite).")
            : QStringLiteral("Projet clos : état %1.").arg(libelles::texte(resultat.value(QStringLiteral("etat"))));
    const QJsonValue archivees = resultat.value(QStringLiteral("cartes_archivees"));
    message += QStringLiteral(" Cartes archivées : %1 · Questions annulées : %2.")
                   .arg(archivees.isArray() ? QString::number(archivees.toArray().size()) : libelles::kInconnu,
                        libelles::nombre(resultat.value(QStringLiteral("questions_annulees"))));
    const QStringList nonArchivees = chaines(resultat.value(QStringLiteral("cartes_non_archivees")));
    if (!nonArchivees.isEmpty()) {
        message += QStringLiteral(" Cartes que Hermes n'a pas archivées : %1.").arg(nonArchivees.join(QStringLiteral(", ")));
    }
    const QStringList branches = chaines(resultat.value(QStringLiteral("branches_rapportees")));
    if (!branches.isEmpty()) {
        message += QStringLiteral(" Branches restées sur l'exécutant (purgées après 7 jours) : %1.").arg(branches.join(QStringLiteral(", ")));
    }
    return message;
}

void ProjetsViewModel::changerReponses(const QString &reponses)
{
    if (gesteEnCours() || m_projetOuvert.isEmpty()) {
        return;
    }
    if (!m_detail.value(QStringLiteral("peutChangerReponses")).toBool()) {
        echouerGeste(QStringLiteral("« Qui répond » ne se change que pour un projet sur dépôt, pas encore fini."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->changerReponses(m_projetOuvert, reponses);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        apresGesteProjet(messageReglageReponses(reponse.json.object()));
        emit reglageReponsesEnregistre();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // Refus du greffon (409 projet fini, sans dépôt ; 400 valeur) ou de la station : tel quel.
        echouerGeste(erreur);
        m_detailSondage->lireMaintenant();
    });
}

void ProjetsViewModel::clore()
{
    if (gesteEnCours() || m_projetOuvert.isEmpty()) {
        return;
    }
    if (!m_detail.value(QStringLiteral("peutClore")).toBool()) {
        echouerGeste(QStringLiteral("Seul un projet actif ou en pause se clôt."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->clore(m_projetOuvert);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        apresGesteProjet(messageCloture(reponse.json.object()));
        m_liste->lireMaintenant();
        emit clotureFaite();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // 409 `projet_fini` (l'émetteur l'a terminé au même instant) ou autre refus : tel quel, puis relu.
        echouerGeste(erreur);
        m_detailSondage->lireMaintenant();
    });
}

bool ProjetsViewModel::ouvrirKanban()
{
    // Sous le préfixe éventuel du serveur, comme l'API (ApiClient::resolve).
    const QUrl url = m_client->resolve(QStringLiteral("/kanban"));
    if (url.isEmpty()) {
        echouerGeste(QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return false;
    }
    if (!m_ouvreur || !m_ouvreur(url)) {
        echouerGeste(QStringLiteral("Le navigateur du système n'a pas pu être ouvert : %1").arg(url.toString()));
        return false;
    }
    // La page kanban de Hermes n'accepte pas de tableau dans son adresse : le propriétaire
    // le choisit dans la page.
    terminerGeste(m_tableauOuvert.isEmpty()
                      ? QStringLiteral("Kanban de Hermes ouvert dans le navigateur.")
                      : QStringLiteral("Kanban de Hermes ouvert dans le navigateur : choisissez le tableau « %1 ».")
                            .arg(m_tableauOuvert));
    return true;
}

// --- Formulaire « Nouveau projet » ------------------------------------------------------------

void ProjetsViewModel::lireFormulaire()
{
    m_catalogueLu = false;
    m_posteLu = false;
    m_erreurCatalogue.clear();
    m_erreurPoste.clear();
    majFormulaire();
    ApiCall *catalogue = m_greffon->catalogue();
    connect(catalogue, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        m_catalogue = reponse.json.object();
        m_catalogueLu = true;
        majFormulaire();
    });
    connect(catalogue, &ApiCall::failed, this, [this](const ApiError &erreur) {
        m_catalogue = {};
        m_catalogueLu = true;
        m_erreurCatalogue = QStringLiteral("Catalogue ACP indisponible : le greffon acp-poste ne sert pas la route "
                                           "/v1/catalogue (%1). Types de projet connus de la station proposés.")
                                .arg(erreur.message());
        majFormulaire();
    });
    ApiCall *poste = m_greffon->poste();
    connect(poste, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        m_poste = reponse.json.object();
        m_posteLu = true;
        majFormulaire();
    });
    connect(poste, &ApiCall::failed, this, [this](const ApiError &erreur) {
        m_poste = {};
        m_posteLu = true;
        m_erreurPoste = QStringLiteral("L'inventaire du poste est indisponible : le greffon acp-poste ne répond pas "
                                       "sur /v1/poste (%1).").arg(erreur.message());
        majFormulaire();
    });
}

QStringList ProjetsViewModel::voiesRelevees(const QJsonObject &cataloguePoste)
{
    const QJsonObject voies = cataloguePoste.value(QStringLiteral("voies")).toObject();
    const QStringList ordre = chaines(cataloguePoste.value(QStringLiteral("politique")).toObject()
                                          .value(QStringLiteral("voies_par_classe")).toObject()
                                          .value(QStringLiteral("exploration")));
    const QStringList candidates = ordre.isEmpty() ? voies.keys() : ordre;
    QStringList resultat;
    for (const QString &voie : candidates) {
        if (releveExiste(voies.value(voie).toObject())) {
            resultat.append(voie);
        }
    }
    return resultat;
}

QJsonObject ProjetsViewModel::voiesFermeesPourDepot(const QJsonObject &vuePoste, const QString &depot)
{
    if (depot.isEmpty()) {
        return {};
    }
    for (const QJsonValue &element : vuePoste.value(QStringLiteral("executant")).toObject().value(QStringLiteral("depots")).toArray()) {
        const QJsonObject mesure = element.toObject();
        if (mesure.value(QStringLiteral("alias")).toString() == depot) {
            return mesure.value(QStringLiteral("voies_fermees")).toObject();
        }
    }
    return {};
}

std::optional<QStringList> ProjetsViewModel::depotsConnus(const QJsonObject &cataloguePoste)
{
    const QJsonObject voies = cataloguePoste.value(QStringLiteral("voies")).toObject();
    QList<QJsonObject> relevees;
    for (auto it = voies.constBegin(); it != voies.constEnd(); ++it) {
        if (releveExiste(it.value().toObject())) {
            relevees.append(it.value().toObject());
        }
    }
    if (cataloguePoste.value(QStringLiteral("etat")).toString() != QLatin1String("connu") || relevees.isEmpty()) {
        return std::nullopt;
    }
    QSet<QString> alias;
    for (const QJsonObject &voie : std::as_const(relevees)) {
        for (const QString &depot : chaines(voie.value(QStringLiteral("depots")))) {
            alias.insert(depot);
        }
    }
    QStringList tries(alias.cbegin(), alias.cend());
    tries.sort();
    return tries;
}

QStringList ProjetsViewModel::effortsAdmis(const QJsonObject &voie, const QString &modele, const QStringList &interdits)
{
    // Efforts relevés du modèle choisi, ou du modèle MARQUÉ par défaut ; aucun si le relevé
    // n'en marque pas (le premier modèle n'est pas un défaut, D73). Efforts interdits exclus.
    QJsonObject choisi;
    for (const QJsonValue &element : voie.value(QStringLiteral("modeles")).toArray()) {
        const QJsonObject candidat = element.toObject();
        const bool retenu = modele.isEmpty() ? candidat.value(QStringLiteral("isDefault")) == QJsonValue(true)
                                             : candidat.value(QStringLiteral("id")).toString() == modele;
        if (retenu) {
            choisi = candidat;
            break;
        }
    }
    QStringList efforts;
    for (const QString &effort : chaines(choisi.value(QStringLiteral("supportedReasoningEfforts")))) {
        if (!interdits.contains(effort)) {
            efforts.append(effort);
        }
    }
    return efforts;
}

void ProjetsViewModel::majFormulaire()
{
    const QJsonObject cataloguePoste = m_poste.value(QStringLiteral("catalogue")).toObject();
    const std::optional<QStringList> depots = depotsConnus(cataloguePoste);
    const QStringList voies = voiesRelevees(cataloguePoste);
    const QStringList interdits = chaines(cataloguePoste.value(QStringLiteral("politique")).toObject()
                                              .value(QStringLiteral("efforts_interdits")));

    QStringList profils = m_catalogue.value(QStringLiteral("profils")).toObject().keys();
    if (profils.isEmpty()) {
        profils = kProfilsConnus;
    }
    QVariantList listeProfils;
    for (const QString &profil : std::as_const(profils)) {
        const QString libelle = libelles::profil(profil);
        listeProfils.append(QVariantMap{{QStringLiteral("valeur"), profil},
                                        {QStringLiteral("libelle"), libelle.isEmpty() ? profil : libelle}});
    }

    if (!depots || !depots->contains(m_depot)) {
        m_depot.clear();
    }
    if (m_voie.isEmpty() || !voies.contains(m_voie)) {
        m_voie = voies.value(0);
    }
    // Étape P7 : un exécutant fermé pour le dépôt choisi n'est jamais retenu ; le premier ouvert le remplace (le choix
    // du propriétaire est gardé et revient avec un dépôt où il est ouvert).
    const QJsonObject fermees = voiesFermeesPourDepot(m_poste, m_depot);
    QString voieChoisie = m_voie;
    if (voieChoisie.isEmpty() || fermees.contains(voieChoisie)) {
        voieChoisie.clear();
        for (const QString &voie : voies) {
            if (!fermees.contains(voie)) {
                voieChoisie = voie;
                break;
            }
        }
    }
    const QJsonObject releveVoie = cataloguePoste.value(QStringLiteral("voies")).toObject().value(voieChoisie).toObject();
    QStringList modeles;
    bool modeleParDefaut = false;
    for (const QJsonValue &element : releveVoie.value(QStringLiteral("modeles")).toArray()) {
        const QJsonObject modele = element.toObject();
        if (libelles::estTexte(modele.value(QStringLiteral("id")))) {
            modeles.append(modele.value(QStringLiteral("id")).toString());
            modeleParDefaut = modeleParDefaut || modele.value(QStringLiteral("isDefault")) == QJsonValue(true);
        }
    }
    if (!m_modele.isEmpty() && !modeles.contains(m_modele)) {
        m_modele.clear();
    }
    const bool avecExploration = !m_depot.isEmpty() && !voies.isEmpty();
    const bool modeleExige = avecExploration && !voieChoisie.isEmpty() && m_modele.isEmpty() && !modeleParDefaut;
    QVariantList listeVoies;
    QStringList voiesFermees;
    for (const QString &voie : voies) {
        const QString libelle = libelles::voie(voie).isEmpty() ? voie : libelles::voie(voie);
        const bool fermee = fermees.contains(voie);
        listeVoies.append(QVariantMap{{QStringLiteral("valeur"), voie},
                                      {QStringLiteral("libelle"), fermee ? QStringLiteral("%1 — fermé pour ce dépôt").arg(libelle) : libelle},
                                      {QStringLiteral("fermee"), fermee}});
        if (fermee) {
            voiesFermees.append(QStringLiteral("%1 : Fermé pour ce dépôt (grisé dans la liste) — %2")
                                    .arg(libelle, libelles::texte(fermees.value(voie))));
        }
    }
    const bool posteIllisible = m_posteLu && !m_erreurPoste.isEmpty();
    m_formulaire = QVariantMap{
        {QStringLiteral("pret"), m_catalogueLu && m_posteLu},
        {QStringLiteral("erreurCatalogue"), m_erreurCatalogue},
        {QStringLiteral("erreurPoste"), m_erreurPoste},
        {QStringLiteral("profils"), listeProfils},
        {QStringLiteral("profilDefaut"), profils.contains(QStringLiteral("base")) ? QStringLiteral("base") : profils.value(0)},
        {QStringLiteral("depotsConnus"), depots.has_value()},
        {QStringLiteral("depots"), depots.value_or(QStringList())},
        {QStringLiteral("aideDepot"), depots ? QString()
             : posteIllisible ? QStringLiteral("Dépôts inconnus : l'inventaire du poste est illisible (voir l'erreur ci-dessus).")
                              : QStringLiteral("Aucun dépôt connu : le poste n'a encore publié aucun inventaire (page Poste).")},
        {QStringLiteral("depot"), m_depot},
        {QStringLiteral("reponsesSansObjet"), m_depot.isEmpty()},
        {QStringLiteral("releveFactice"), cataloguePoste.value(QStringLiteral("releve_factice")) == QJsonValue(true)},
        {QStringLiteral("avecExploration"), avecExploration},
        {QStringLiteral("voies"), listeVoies},
        {QStringLiteral("voie"), voieChoisie},
        {QStringLiteral("voiesFermees"), voiesFermees},
        {QStringLiteral("aucuneVoieOuverte"), avecExploration && voieChoisie.isEmpty()},
        {QStringLiteral("modeles"), modeles},
        {QStringLiteral("modeleParDefaut"), modeleParDefaut},
        {QStringLiteral("libelleModeleVide"), modeleParDefaut
             ? QStringLiteral("Modèle par défaut du relevé")
             : QStringLiteral("Choisissez un modèle (le relevé n'en désigne aucun par défaut)")},
        {QStringLiteral("modele"), m_modele},
        {QStringLiteral("efforts"), effortsAdmis(releveVoie, m_modele, interdits)},
        {QStringLiteral("releveDu"), libelles::texte(releveVoie.value(QStringLiteral("releve_le_lisible")))},
        {QStringLiteral("relevePerime"), releveVoie.value(QStringLiteral("perime")) == QJsonValue(true)},
        {QStringLiteral("modeleExige"), modeleExige},
    };
    emit formulaireChange();
}

void ProjetsViewModel::choisirDepot(const QString &depot)
{
    m_depot = depot;
    majFormulaire();
}

void ProjetsViewModel::choisirVoie(const QString &voie)
{
    const QJsonObject fermees = voiesFermeesPourDepot(m_poste, m_depot);
    if (fermees.contains(voie)) {
        // Jamais retenu : le greffon le refuserait (`voie_fermee`), sans faux succès.
        echouerGeste(QStringLiteral("Cet exécutant est fermé pour ce dépôt : %1").arg(libelles::texte(fermees.value(voie))));
        majFormulaire();
        return;
    }
    m_voie = voie;
    m_modele.clear();
    majFormulaire();
}

void ProjetsViewModel::choisirModele(const QString &modele)
{
    m_modele = modele;
    majFormulaire();
}

void ProjetsViewModel::lancer(const QString &titre, const QString &objectif, const QString &profil,
                              const QString &reponses, const QString &effort)
{
    if (gesteEnCours()) {
        return;
    }
    if (!m_formulaire.value(QStringLiteral("pret")).toBool()) {
        echouerGeste(QStringLiteral("Le formulaire n'est pas encore prêt : le catalogue et l'inventaire du poste sont en cours de lecture."));
        return;
    }
    if (titre.trimmed().isEmpty() || objectif.trimmed().isEmpty()) {
        echouerGeste(QStringLiteral("Le titre et l'objectif sont obligatoires."));
        return;
    }
    if (m_formulaire.value(QStringLiteral("modeleExige")).toBool()) {
        echouerGeste(QStringLiteral("Choisissez un modèle pour l'exploration : le relevé de cet exécutant n'en désigne "
                                    "aucun par défaut."));
        return;
    }
    QJsonObject corps{
        {QStringLiteral("titre"), titre.trimmed()},
        {QStringLiteral("objectif"), objectif.trimmed()},
        {QStringLiteral("profil"), profil},
        {QStringLiteral("depot"), m_depot.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(m_depot)},
        {QStringLiteral("reponses"), reponses},
    };
    const QString voieChoisie = m_formulaire.value(QStringLiteral("voie")).toString();
    if (m_formulaire.value(QStringLiteral("avecExploration")).toBool() && !voieChoisie.isEmpty()) {
        QJsonObject exploration{{QStringLiteral("voie"), voieChoisie}};
        if (!m_modele.isEmpty()) {
            exploration.insert(QStringLiteral("modele"), m_modele);
        }
        if (!effort.isEmpty()) {
            exploration.insert(QStringLiteral("effort"), effort);
        }
        corps.insert(QStringLiteral("exploration"), exploration);
    }
    if (m_cle.isEmpty()) {
        m_cle = makeIdempotencyKey(QStringLiteral("projet"));
    }
    debuterGeste();
    ApiCall *appel = m_greffon->lancerProjet(corps, m_cle);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const QJsonObject resultat = reponse.json.object();
        const QString identifiant = resultat.value(QStringLiteral("projet")).toObject().value(QStringLiteral("id")).toString();
        const bool dejaLance = resultat.value(QStringLiteral("deja_lance")).toBool();
        // Lancement accepté : le prochain formulaire aura sa propre clé.
        m_cle = makeIdempotencyKey(QStringLiteral("projet"));
        terminerGeste(dejaLance ? QStringLiteral("Ce projet était déjà lancé par ce formulaire : aucun doublon n'a été créé.")
                                : QStringLiteral("Projet lancé : Hermes le planifie."));
        m_liste->lireMaintenant();
        if (ClientGreffonPoste::identifiantValide(identifiant)) {
            ouvrirProjet(identifiant);
        } else {
            changerVue(QStringLiteral("liste"));
        }
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // La clé est gardée : un nouvel envoi du même formulaire ne créera pas de doublon.
        echouerGeste(erreur);
    });
}

} // namespace acp
