#include "viewmodels/AccueilViewModel.h"

#include "services/CompatibiliteHermes.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "gateway/DiscussionsEnAttente.h"
#include "models/JsonListModel.h"
#include "viewmodels/Libelles.h"

#include <QDesktopServices>
#include <QJsonArray>
#include <QUrl>

namespace acp {

namespace {

//! Raison posée par la veille des crochets shell (noyau/textes.RAISON_PAUSE_CROCHETS) : la
//! reprise est alors refusée par le greffon tant qu'ils existent.
const QString kRaisonCrochets = QStringLiteral("ACP : crochets shell détectés en cours de route");

//! Voies dont l'Accueil du navigateur montre les quotas (CarteQuotas de CarteExecutant.tsx).
const QStringList kVoiesQuotas = {QStringLiteral("poste-codex"), QStringLiteral("poste-claude")};

QString libelleVoieOuBrut(const QString &cle)
{
    const QString libelle = libelles::voie(cle);
    return libelle.isEmpty() ? cle : libelle;
}

/*! Raison d'un bloc illisible servie par le greffon (`illisibles`), ou « Inconnu ». */
QString raisonIllisible(const QJsonObject &accueil, const QString &bloc)
{
    return libelles::texte(accueil.value(QStringLiteral("illisibles")).toObject().value(bloc));
}

/*! Le bloc est lisible : un objet servi (jamais `null`, jamais absent). */
bool lisible(const QJsonObject &accueil, const QString &bloc)
{
    return accueil.value(bloc).isObject();
}

QString texteOuVide(const QJsonValue &valeur)
{
    return libelles::estTexte(valeur) ? valeur.toString() : QString();
}

QString pourcentageBorne(const QJsonValue &valeur)
{
    // Comme la page web : un pourcentage n'est rendu que s'il est entre 0 et 100.
    return valeur.isDouble() && valeur.toDouble() >= 0 && valeur.toDouble() <= 100 ? libelles::pourcentage(valeur)
                                                                                    : libelles::kInconnu;
}

/*! Horodatage servi en secondes (nombre) ou en ISO 8601 (chaîne) ; sinon « Inconnu ». */
QString dateServie(const QJsonValue &valeur)
{
    return valeur.isString() ? libelles::dateIso(valeur) : libelles::date(valeur);
}

} // namespace

AccueilViewModel::AccueilViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                                   QObject *parent)
    : PageViewModel(flux, parent)
    , m_client(client)
    , m_greffon(greffon)
    , m_accueil(new Sondage([this] { return m_greffon->accueil(); }, Sondage::kIntervallePage, this))
    , m_sondageSessions(new Sondage(
          [this] {
              // Même appel que la page d'accueil web (apps/interface/src/api.ts, ROUTE_SESSIONS).
              ApiRequest requete;
              requete.path = QStringLiteral("/api/sessions");
              requete.query.addQueryItem(QStringLiteral("limit"), QStringLiteral("5"));
              requete.query.addQueryItem(QStringLiteral("offset"), QStringLiteral("0"));
              requete.query.addQueryItem(QStringLiteral("order"), QStringLiteral("recent"));
              return m_client->send(requete);
          },
          Sondage::kIntervallePage, this))
    , m_sondageBilan(new Sondage(
          [this] {
              // Route NATIVE de Hermes (accueil-api.ts, ROUTE_CRON), avec la session du propriétaire.
              ApiRequest requete;
              requete.path = QStringLiteral("/api/cron/jobs");
              return m_client->send(requete);
          },
          Sondage::kIntervallePage, this))
    , m_projetsEnCours(new JsonListModel(this))
    , m_sessions(new JsonListModel(this))
    , m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); })
{
    // Comme la page web (useDonnees(lireTachesCron, …, [])) : aucun sujet du flux ; relecture de sûreté en temps réel.
    m_sondageBilan->suivre(flux->invalidation(), {});
    connect(m_sondageBilan, &Sondage::etatChange, this, &AccueilViewModel::lectureChange);
    connect(m_sondageBilan, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        m_tachesBilan = tachesDuBilan(reponse.json.isArray() ? QJsonValue(reponse.json.array()) : QJsonValue(reponse.json.object()));
        majBilan();
    });
    connect(m_sondageBilan, &Sondage::echec, this, [this](const ApiError &) { majBilan(); });
    m_projetsEnCours->setCle({QStringLiteral("id")});
    connect(flux->discussions(), &DiscussionsEnAttente::change, this, [this] {
        m_carteATraiter = construireCarteATraiter(m_dernierAccueil, this->flux()->discussions()->nombre());
        emit accueilChange();
    });
    // Étape P7 : l'Accueil agrégé couvre tous les sujets du flux (Accueil.tsx, useDonnees(lireAccueil, …, SUJETS)).
    m_accueil->suivre(flux->invalidation(), FluxInvalidation::sujets());
    suivreCadence(m_accueil);
    for (Sondage *sondage : {m_sondageSessions, m_sondageBilan}) {
        connect(sondage, &Sondage::cadenceChange, this, &AccueilViewModel::cadenceChange);
    }
    lireAccueil({});
    m_lue = false;
    for (Sondage *sondage : {m_accueil, m_sondageSessions}) {
        connect(sondage, &Sondage::etatChange, this, &AccueilViewModel::lectureChange);
    }
    connect(m_accueil, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        const QJsonObject accueil = reponse.json.object();
        lireAccueil(accueil);
        m_lue = true;
        emit accueilChange();
        // La barre d'état et le badge de la file Questions suivent sans attendre le sondage léger.
        this->flux()->noterAccueil(accueil);
        // Discussions en attente : lues par la passerelle, comme la page web (Accueil.tsx).
        this->flux()->discussions()->lire();
    });
    connect(m_sondageSessions, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        m_sessions->setItems(construireSessions(reponse.json.object()));
        m_sessionsLues = true;
        emit lectureChange();
    });
}

AccueilViewModel::~AccueilViewModel() = default;

QList<Sondage *> AccueilViewModel::sondages() const
{
    QList<Sondage *> liste{m_accueil, m_sondageSessions, m_sondageBilan};
    if (m_meta) {
        liste.append(m_meta);
    }
    return liste;
}

void AccueilViewModel::setCompatibilite(CompatibiliteHermes *compatibilite)
{
    if (m_meta || !compatibilite) {
        return;
    }
    m_compatibilite = compatibilite;
    m_meta = new Sondage([this] { return m_greffon->meta(); }, m_accueil->intervalle(), this);
    connect(m_meta, &Sondage::lu, this,
            [this](const ApiResponse &reponse) { m_compatibilite->appliquerLecture(reponse.json.object()); });
    connect(m_meta, &Sondage::echec, this, [this](const ApiError &erreur) { m_compatibilite->appliquerEchec(erreur); });
    connect(m_meta, &Sondage::cadenceChange, this, &AccueilViewModel::cadenceChange);
    m_meta->setActif(actif());
    emit cadenceChange(); // la carte Hermes est désormais relue avec la page
}

QString AccueilViewModel::cadence() const
{
    // Comme EtatActualisation portee="accueil" de la page web : la portée exacte du temps réel.
    if (m_accueil->tempsReel()) {
        return QStringLiteral("Accueil relu à chaque changement signalé par le serveur (temps réel) et %1 par sûreté ; "
                              "bilan quotidien relu %2 ; %3 %4 ; tant que la page est affichée.")
            .arg(Sondage::toutesLes(m_accueil->intervalleEffectif()), Sondage::toutesLes(m_sondageBilan->intervalleEffectif()),
                 m_meta ? QStringLiteral("discussions récentes et carte Hermes relues") : QStringLiteral("discussions récentes relues"),
                 Sondage::toutesLes(m_sondageSessions->intervalleEffectif()));
    }
    // Hors temps réel, toutes les lectures de la page partagent le même intervalle (setIntervalle).
    return QStringLiteral("%1 : %2 relus %3%4 tant que la page est affichée.")
        .arg(m_accueil->etatHorsTempsReel(),
             m_meta ? QStringLiteral("Accueil, bilan quotidien, discussions récentes et carte Hermes")
                    : QStringLiteral("Accueil, bilan quotidien et discussions récentes"),
             Sondage::toutesLes(m_accueil->intervalleEffectif()),
             m_accueil->connexionTempsReel() ? QStringLiteral(" en attendant,") : QString());
}

void AccueilViewModel::setIntervalle(std::chrono::milliseconds intervalle)
{
    for (Sondage *sondage : sondages()) {
        sondage->setIntervalle(intervalle);
    }
}

void AccueilViewModel::surActivite(bool actif)
{
    for (Sondage *sondage : sondages()) {
        sondage->setActif(actif);
    }
}

void AccueilViewModel::surLienRetabli()
{
    actualiser();
}

void AccueilViewModel::surOubli()
{
    for (Sondage *sondage : sondages()) {
        sondage->oublier();
    }
    m_tachesBilan.reset();
    lireAccueil({});
    m_lue = false;
    emit accueilChange();
    m_sessions->clear();
    m_sessionsLues = false;
    emit lectureChange();
}

void AccueilViewModel::actualiser()
{
    for (Sondage *sondage : sondages()) {
        sondage->lireMaintenant();
    }
}

QString AccueilViewModel::lectureAccueil() const { return m_accueil->libelleLuA(); }
QString AccueilViewModel::erreurAccueil() const { return m_accueil->derniereErreur(); }
QString AccueilViewModel::lectureSessions() const { return m_sondageSessions->libelleLuA(); }
QString AccueilViewModel::erreurSessions() const { return m_sondageSessions->derniereErreur(); }

void AccueilViewModel::majBilan()
{
    m_carteBilan = construireCarteBilan(m_tachesBilan, m_dernierAccueil, m_sondageBilan->derniereErreur());
    emit accueilChange();
}

QString AccueilViewModel::lectureBilan() const { return m_sondageBilan->libelleLuA(); }
QString AccueilViewModel::erreurBilan() const { return m_sondageBilan->derniereErreur(); }

void AccueilViewModel::creerBilanQuotidien()
{
    if (gesteEnCours()) {
        return;
    }
    // Jamais un doublon : offert seulement si la liste LUE n'en contient aucun.
    if (!m_tachesBilan || !m_tachesBilan->isEmpty()) {
        echouerGeste(m_tachesBilan ? QStringLiteral("Le bilan quotidien existe déjà : rien n'est créé.")
                                   : QStringLiteral("État du bilan inconnu : rien n'est créé tant que la liste des tâches "
                                                    "cron de Hermes n'est pas lue."));
        return;
    }
    debuterGeste();
    ApiRequest requete;
    requete.method = QByteArrayLiteral("POST");
    requete.path = QStringLiteral("/api/cron/jobs");
    requete.body = QJsonDocument(tacheBilan());
    ApiCall *appel = m_client->send(requete);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &) {
        terminerGeste(QStringLiteral("Bilan quotidien créé."));
        m_sondageBilan->lireMaintenant();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // La route native répond en anglais : refus dit en français, le détail de Hermes à la suite.
        echouerGeste(QStringLiteral("Le bilan n'a pas été créé : Hermes a refusé la tâche (%1).").arg(messageDuRefus(erreur)));
        m_sondageBilan->lireMaintenant();
    });
}

bool AccueilViewModel::ouvrirCron()
{
    const QUrl url = m_client->resolve(QStringLiteral("/cron"));
    if (url.isEmpty() || !m_ouvreur || !m_ouvreur(url)) {
        echouerGeste(QStringLiteral("La page Cron de Hermes n'a pas pu être ouverte dans le navigateur."));
        return false;
    }
    terminerGeste(QStringLiteral("Page Cron de Hermes ouverte dans le navigateur."));
    return true;
}

void AccueilViewModel::lireAccueil(const QJsonObject &accueil)
{
    m_dernierAccueil = accueil;
    m_carteBilan = construireCarteBilan(m_tachesBilan, accueil, m_sondageBilan->derniereErreur());
    m_carteATraiter = construireCarteATraiter(accueil, flux()->discussions()->nombre());
    m_carteProjets = construireCarteProjets(accueil);
    m_projetsEnCours->setItems(construireProjetsEnCours(accueil));
    m_carteExecutant = construireCarteExecutant(accueil);
    m_carteQuotas = construireCarteQuotas(accueil);
    m_carteNotifications = construireCarteNotifications(accueil);
    m_cartePause = construireCartePause(accueil);
}

void AccueilViewModel::basculerPause(bool generale, const QString &raison)
{
    if (gesteEnCours()) {
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->pauseGenerale(generale, raison);
    connect(appel, &ApiCall::succeeded, this, [this, generale](const ApiResponse &) {
        terminerGeste(generale ? QStringLiteral("Pause générale engagée : aucune nouvelle carte ne part.")
                               : QStringLiteral("Pause générale levée : Hermes reprend son travail autonome."));
        m_accueil->lireMaintenant();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        m_accueil->lireMaintenant();
    });
}

void AccueilViewModel::envoyerNotificationDeTest()
{
    if (gesteEnCours()) {
        return;
    }
    if (!m_carteNotifications.value(QStringLiteral("configure")).toBool()) {
        echouerGeste(QStringLiteral("Aucun canal de notifications configuré : rien n'est envoyé."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->notificationDeTest();
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        // Le message du greffon (« mise en file : la passerelle l'envoie à sa prochaine passe »), tel quel.
        const QJsonValue message = reponse.json.object().value(QStringLiteral("message"));
        terminerGeste(libelles::estTexte(message) ? message.toString()
                                                  : QStringLiteral("Notification de test acceptée par le greffon."));
        m_accueil->lireMaintenant();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        m_accueil->lireMaintenant();
    });
}

// --- Fonctions pures -------------------------------------------------------------------

QVariantMap AccueilViewModel::construireCarteATraiter(const QJsonObject &accueil, int discussions)
{
    const QString bloc = QStringLiteral("a_traiter");
    if (!lisible(accueil, bloc)) {
        return QVariantMap{{QStringLiteral("lisible"), false},
                           {QStringLiteral("raison"), raisonIllisible(accueil, bloc)},
                           {QStringLiteral("total"), libelles::kInconnu},
                           {QStringLiteral("premieres"), QVariantList{}}};
    }
    const QJsonObject a = accueil.value(bloc).toObject();
    QVariantList premieres;
    for (const QJsonValue &element : a.value(QStringLiteral("premieres")).toArray()) {
        const QJsonObject demande = element.toObject();
        const QString genre = demande.value(QStringLiteral("genre")).toString();
        const QString libelleGenre = genre == QLatin1String("question") ? QStringLiteral("Question :")
            : genre == QLatin1String("decision")                       ? QStringLiteral("Décision :")
            : genre == QLatin1String("revue")                          ? QStringLiteral("Revue :")
            : genre == QLatin1String("arretee")                        ? QStringLiteral("Carte arrêtée :")
                                                                       : QString();
        premieres.append(QVariantMap{
            {QStringLiteral("genre"), libelleGenre},
            {QStringLiteral("titre"), libelles::texte(demande.value(QStringLiteral("titre")))},
            {QStringLiteral("projet"), libelles::texte(demande.value(QStringLiteral("projet_titre")))},
        });
    }
    const QJsonValue totalGreffon = a.value(QStringLiteral("total"));
    const QJsonValue chezHermes = accueil.value(QStringLiteral("chez_hermes"));
    // Discussions en attente lues par la passerelle (session.active_list) et ajoutées au total, comme la page web ;
    // inconnues : le total le dit, et « Rien n'attend votre décision » n'est jamais affiché (jamais zéro par défaut).
    const bool connues = discussions >= 0;
    const bool totalConnu = libelles::estNombre(totalGreffon);
    const qint64 total = totalConnu ? totalGreffon.toInteger() + (connues ? discussions : 0) : -1;
    return QVariantMap{
        {QStringLiteral("lisible"), true},
        {QStringLiteral("raison"), QString()},
        {QStringLiteral("total"), totalConnu ? QString::number(total) : libelles::kInconnu},
        {QStringLiteral("mention"), connues ? QString() : QStringLiteral("(discussions en attente : état inconnu, non comptées)")},
        {QStringLiteral("rien"), connues && total == 0 && a.value(QStringLiteral("premieres")).toArray().isEmpty()},
        {QStringLiteral("questions"), libelles::nombre(a.value(QStringLiteral("questions")))},
        {QStringLiteral("decisions"), libelles::nombre(a.value(QStringLiteral("decisions")))},
        {QStringLiteral("revues"), libelles::nombre(a.value(QStringLiteral("revues")))},
        {QStringLiteral("arretees"), libelles::nombre(a.value(QStringLiteral("arretees")))},
        {QStringLiteral("discussions"), connues ? QString::number(discussions) : QStringLiteral("Inconnues")},
        {QStringLiteral("chezHermes"), libelles::nombre(chezHermes)},
        {QStringLiteral("attente"), total > 0},
        {QStringLiteral("premieres"), premieres},
    };
}

QVariantMap AccueilViewModel::construireCarteProjets(const QJsonObject &accueil)
{
    const QString bloc = QStringLiteral("projets");
    if (!lisible(accueil, bloc)) {
        return QVariantMap{{QStringLiteral("lisible"), false}, {QStringLiteral("raison"), raisonIllisible(accueil, bloc)},
                           {QStringLiteral("enCours"), libelles::kInconnu}, {QStringLiteral("enPause"), libelles::kInconnu},
                           {QStringLiteral("termines7j"), libelles::kInconnu}, {QStringLiteral("aucunOuvert"), false}};
    }
    const QJsonObject p = accueil.value(bloc).toObject();
    const QJsonValue liste = p.value(QStringLiteral("liste"));
    return QVariantMap{
        {QStringLiteral("lisible"), true},
        {QStringLiteral("raison"), QString()},
        {QStringLiteral("enCours"), libelles::nombre(p.value(QStringLiteral("en_cours")))},
        {QStringLiteral("enPause"), libelles::nombre(p.value(QStringLiteral("en_pause")))},
        {QStringLiteral("termines7j"), libelles::nombre(p.value(QStringLiteral("termines_7j")))},
        {QStringLiteral("aucunOuvert"), liste.isArray() && liste.toArray().isEmpty()},
    };
}

QJsonArray AccueilViewModel::construireProjetsEnCours(const QJsonObject &accueil)
{
    QJsonArray lignes;
    for (const QJsonValue &element : accueil.value(QStringLiteral("projets")).toObject().value(QStringLiteral("liste")).toArray()) {
        const QJsonObject projet = element.toObject();
        const QString identifiant = projet.value(QStringLiteral("id")).toString();
        if (!ClientGreffonPoste::identifiantValide(identifiant)) {
            continue; // sans identifiant lisible, la ligne ne désigne rien
        }
        const libelles::Libelle etat = libelles::etatProjet(projet.value(QStringLiteral("etat")),
                                                            projet.value(QStringLiteral("etat_derive")));
        const QJsonValue faites = projet.value(QStringLiteral("faites"));
        const QJsonValue total = projet.value(QStringLiteral("total"));
        const QString note = texteOuVide(projet.value(QStringLiteral("derniere_note")));
        lignes.append(QJsonObject{
            {QStringLiteral("id"), identifiant},
            {QStringLiteral("titre"), libelles::texte(projet.value(QStringLiteral("titre")))},
            {QStringLiteral("etatLibelle"), etat.connu() ? etat.texte : libelles::texte(projet.value(QStringLiteral("etat")))},
            {QStringLiteral("etatCle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
            {QStringLiteral("avancement"), libelles::estNombre(faites) && libelles::estNombre(total)
                 ? QStringLiteral("%1 sur %2 cartes faites").arg(faites.toInteger()).arg(total.toInteger())
                 : libelles::kInconnu},
            {QStringLiteral("note"), note.isEmpty() ? QString()
                                     : projet.value(QStringLiteral("derniere_note_tronquee")) == QJsonValue(true)
                                         ? note + QStringLiteral(" […] (extrait)")
                                         : note},
        });
    }
    return lignes;
}

QVariantMap AccueilViewModel::construireCarteExecutant(const QJsonObject &accueil)
{
    const QString bloc = QStringLiteral("executant");
    if (!lisible(accueil, bloc)) {
        return QVariantMap{{QStringLiteral("lisible"), false}, {QStringLiteral("raison"), raisonIllisible(accueil, bloc)},
                           {QStringLiteral("etat"), libelles::kInconnu}, {QStringLiteral("cle"), QStringLiteral("unknown")},
                           {QStringLiteral("voiesFermees"), QString()}};
    }
    const QJsonObject e = accueil.value(bloc).toObject();
    const libelles::Libelle etat = libelles::etatPoste(e.value(QStringLiteral("etat")));
    const QJsonValue enCours = e.value(QStringLiteral("carte_en_cours"));
    QString carte = QStringLiteral("Aucune carte en cours");
    if (enCours.isObject()) {
        const QJsonObject c = enCours.toObject();
        const libelles::Libelle statut = libelles::statutCarte(c.value(QStringLiteral("statut")));
        carte = QStringLiteral("%1 (projet « %2 ») · %3")
                    .arg(libelles::texte(c.value(QStringLiteral("titre"))), libelles::texte(c.value(QStringLiteral("projet_titre"))),
                         statut.connu() ? statut.texte : libelles::texte(c.value(QStringLiteral("statut"))));
    } else if (!enCours.isNull()) {
        carte = libelles::kInconnu;
    }
    QStringList fermees;
    const QJsonValue voies = e.value(QStringLiteral("voies_fermees"));
    const QJsonObject parVoie = voies.toObject();
    for (auto it = parVoie.constBegin(); it != parVoie.constEnd(); ++it) {
        fermees.append(QStringLiteral("%1 : %2").arg(libelleVoieOuBrut(it.key()), libelles::texte(it.value())));
    }
    return QVariantMap{
        {QStringLiteral("lisible"), true},
        {QStringLiteral("raison"), QString()},
        {QStringLiteral("etat"), etat.connu() ? etat.texte : libelles::texte(e.value(QStringLiteral("etat")))},
        {QStringLiteral("cle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
        {QStringLiteral("machine"), libelles::texte(e.value(QStringLiteral("nom")))},
        {QStringLiteral("plateforme"), libelles::texte(e.value(QStringLiteral("plateforme")))},
        {QStringLiteral("derniereVue"), dateServie(e.value(QStringLiteral("derniere_vue")))},
        {QStringLiteral("horsLigneDepuis"), e.value(QStringLiteral("hors_ligne_depuis")).isDouble()
             ? libelles::date(e.value(QStringLiteral("hors_ligne_depuis"))) : QString()},
        {QStringLiteral("carteEnCours"), carte},
        {QStringLiteral("cartesEnAttente"), libelles::nombre(e.value(QStringLiteral("cartes_en_attente")))},
        {QStringLiteral("message"), texteOuVide(e.value(QStringLiteral("message")))},
        // Objet servi `{voie: raison}` (constat desktop-3 de P7) ; autre forme : « Inconnu ». Vide : rien, comme la page
        // web — le greffon sert aussi `{}` quand AUCUN exécutant n'est connu, et « Aucune » y inventerait une absence
        // de fermeture (relecture de P8b, constat desktop-6).
        {QStringLiteral("voiesFermees"), !voies.isObject() ? libelles::kInconnu : fermees.join(QLatin1Char('\n'))},
    };
}

QVariantMap AccueilViewModel::construireCarteQuotas(const QJsonObject &accueil)
{
    const QString bloc = QStringLiteral("quotas");
    if (!lisible(accueil, bloc)) {
        return QVariantMap{{QStringLiteral("lisible"), false}, {QStringLiteral("raison"), raisonIllisible(accueil, bloc)},
                           {QStringLiteral("voies"), QVariantList{}}, {QStringLiteral("hermes"), libelles::kInconnu}};
    }
    const QJsonObject q = accueil.value(bloc).toObject();
    QVariantList voies;
    for (const QString &cle : kVoiesQuotas) {
        const QJsonObject voie = q.value(cle).toObject();
        const libelles::Libelle etat = libelles::etatQuotas(voie.value(QStringLiteral("etat")));
        const QJsonObject resume = voie.value(QStringLiteral("resume")).toObject();
        voies.append(QVariantMap{
            {QStringLiteral("nom"), libelleVoieOuBrut(cle)},
            {QStringLiteral("etat"), etat.connu() ? etat.texte : libelles::texte(voie.value(QStringLiteral("etat")))},
            {QStringLiteral("cle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
            {QStringLiteral("utilise"), pourcentageBorne(resume.value(QStringLiteral("pourcentage_utilise")))},
            {QStringLiteral("remise"), libelles::dateIso(resume.value(QStringLiteral("remise_a_zero")))},
            {QStringLiteral("source"), libelles::texte(voie.value(QStringLiteral("source_libelle")))},
            {QStringLiteral("releveLe"), dateServie(voie.value(QStringLiteral("releve_le")))},
        });
    }
    return QVariantMap{
        {QStringLiteral("lisible"), true},
        {QStringLiteral("raison"), QString()},
        {QStringLiteral("voies"), voies},
        {QStringLiteral("hermes"), libelles::texte(q.value(QStringLiteral("hermes")).toObject().value(QStringLiteral("libelle")))},
    };
}

QVariantMap AccueilViewModel::construireCarteNotifications(const QJsonObject &accueil)
{
    const QString bloc = QStringLiteral("notifications");
    if (!lisible(accueil, bloc)) {
        return QVariantMap{{QStringLiteral("lisible"), false}, {QStringLiteral("raison"), raisonIllisible(accueil, bloc)},
                           {QStringLiteral("canal"), libelles::kInconnu}, {QStringLiteral("etat"), libelles::kInconnu},
                           {QStringLiteral("cle"), QStringLiteral("unknown")}, {QStringLiteral("configure"), false},
                           {QStringLiteral("note"), QString()}};
    }
    const QJsonObject n = accueil.value(bloc).toObject();
    const bool connu = n.value(QStringLiteral("connu")) == QJsonValue(true);
    const bool configure = n.value(QStringLiteral("configure")) == QJsonValue(true);
    const QString canal = n.value(QStringLiteral("canal")).toString();
    QString libelleCanal = canal == QLatin1String("telegram") ? QStringLiteral("Telegram")
        : canal == QLatin1String("ntfy")                     ? QStringLiteral("ntfy")
        : canal == QLatin1String("aucune")                   ? QStringLiteral("Aucun")
                                                             : libelles::texte(n.value(QStringLiteral("canal")));
    if (!connu) {
        libelleCanal = libelles::kInconnu;
    }
    return QVariantMap{
        {QStringLiteral("lisible"), true},
        {QStringLiteral("raison"), QString()},
        {QStringLiteral("canal"), libelleCanal},
        {QStringLiteral("etat"), !connu ? libelles::kInconnu : configure ? QStringLiteral("Configurées") : QStringLiteral("Non configurées")},
        {QStringLiteral("cle"), !connu ? QStringLiteral("unknown") : configure ? QStringLiteral("succeeded") : QStringLiteral("notConfigured")},
        {QStringLiteral("configure"), configure},
        // Message du greffon (canal non configuré, ou état inconnu tant que la passerelle ne l'a pas publié).
        {QStringLiteral("note"), texteOuVide(n.value(QStringLiteral("message")))},
    };
}

QJsonObject AccueilViewModel::tacheBilan()
{
    return QJsonObject{{QStringLiteral("name"), QStringLiteral("Bilan ACP")},
                       {QStringLiteral("schedule"), QStringLiteral("0 8 * * *")},
                       {QStringLiteral("prompt"), QString()},
                       {QStringLiteral("no_agent"), true},
                       {QStringLiteral("script"), QStringLiteral("acp-bilan.py")},
                       {QStringLiteral("deliver"), QStringLiteral("local")}};
}

std::optional<QJsonArray> AccueilViewModel::tachesDuBilan(const QJsonValue &reponse)
{
    const QJsonValue liste = reponse.isArray() ? reponse : reponse.toObject().value(QStringLiteral("jobs"));
    if (!liste.isArray()) {
        return std::nullopt;
    }
    QJsonArray taches;
    for (const QJsonValue &element : liste.toArray()) {
        const QJsonObject tache = element.toObject();
        // Le script de l'image, SANS agent (comme le diagnostic de l'image les admet).
        if (tache.value(QStringLiteral("script")).toString() == QLatin1String("acp-bilan.py")
            && tache.value(QStringLiteral("no_agent")) == QJsonValue(true)) {
            taches.append(tache);
        }
    }
    return taches;
}

QVariantMap AccueilViewModel::construireCarteBilan(const std::optional<QJsonArray> &taches, const QJsonObject &accueil,
                                                   const QString &erreur)
{
    const QJsonObject notifications = accueil.value(QStringLiteral("notifications")).toObject();
    const bool sansCanal = notifications.value(QStringLiteral("connu")) == QJsonValue(true)
        && notifications.value(QStringLiteral("configure")) != QJsonValue(true);
    QVariantMap carte{
        {QStringLiteral("lu"), taches.has_value()},
        {QStringLiteral("illisible"), !taches && !erreur.isEmpty()
                                          ? QStringLiteral("État du bilan inconnu : la liste des tâches cron de Hermes ne répond pas.")
                                          : QString()},
        {QStringLiteral("sansCanal"), sansCanal ? QStringLiteral("Le bilan ne partira pas : notifications non configurées.") : QString()},
        {QStringLiteral("peutCreer"), false},
        {QStringLiteral("etat"), libelles::kInconnu},
        {QStringLiteral("cle"), QStringLiteral("unknown")},
        {QStringLiteral("explication"), QString()},
        {QStringLiteral("prochaine"), QString()},
        {QStringLiteral("derniere"), QString()},
        {QStringLiteral("alerte"), QString()},
        {QStringLiteral("statut"), QString()},
        {QStringLiteral("message"), QString()},
        {QStringLiteral("plusieurs"), QString()},
    };
    if (!taches) {
        return carte;
    }
    if (taches->isEmpty()) {
        carte.insert(QStringLiteral("etat"), QStringLiteral("Non créé"));
        carte.insert(QStringLiteral("cle"), QStringLiteral("notConfigured"));
        carte.insert(QStringLiteral("peutCreer"), true);
        carte.insert(QStringLiteral("explication"),
                     QStringLiteral("Une notification par jour, à 8 h (heure de Paris) : des compteurs seulement, sans "
                                    "modèle ni jeton. Vous seul pouvez la créer."));
        return carte;
    }
    const QJsonObject tache = taches->first().toObject();
    const bool pause = tache.value(QStringLiteral("enabled")) == QJsonValue(false)
        || tache.value(QStringLiteral("state")).toString() == QLatin1String("paused");
    const bool enErreur = !pause && tache.value(QStringLiteral("state")).toString() == QLatin1String("error");
    // Hermes date last_run_at même en échec : seule une issue PUBLIÉE autre que « ok » est un échec (jamais supposé).
    const QJsonValue statut = tache.value(QStringLiteral("last_status"));
    const bool executee = libelles::estTexte(tache.value(QStringLiteral("last_run_at")));
    const bool echec = executee && statut.isString() && statut.toString() != QLatin1String("ok");
    carte.insert(QStringLiteral("etat"), pause ? QStringLiteral("En pause") : enErreur ? QStringLiteral("En erreur") : QStringLiteral("Actif"));
    carte.insert(QStringLiteral("cle"), pause ? QStringLiteral("pending") : enErreur ? QStringLiteral("failed") : QStringLiteral("succeeded"));
    carte.insert(QStringLiteral("prochaine"), pause || enErreur ? QString() : libelles::dateIso(tache.value(QStringLiteral("next_run_at"))));
    carte.insert(QStringLiteral("derniere"), executee ? libelles::dateIso(tache.value(QStringLiteral("last_run_at"))) : QStringLiteral("Jamais"));
    carte.insert(QStringLiteral("alerte"),
                 enErreur ? QStringLiteral("Hermes a mis la tâche en erreur : elle ne s'exécutera plus d'elle-même. Détail "
                                           "ci-dessous et sur la page Cron.")
                 : echec  ? QStringLiteral("Dernière exécution en échec : le bilan de ce jour n'est pas garanti. Détail "
                                           "ci-dessous et sur la page Cron.")
                          : QString());
    if (enErreur || echec) {
        carte.insert(QStringLiteral("statut"), libelles::texte(statut));
        carte.insert(QStringLiteral("message"), libelles::texte(tache.value(QStringLiteral("last_error"))));
    }
    if (taches->size() > 1) {
        carte.insert(QStringLiteral("plusieurs"), QStringLiteral("Plusieurs tâches du bilan existent : gardez-en une depuis la page Cron."));
    }
    return carte;
}

QVariantMap AccueilViewModel::construireCartePause(const QJsonObject &accueil)
{
    const QJsonValue pause = accueil.value(QStringLiteral("pause_generale"));
    // Objet présent : engagée ; null : levée — sauf si le greffon dit le bloc illisible ; absente ou d'un autre type :
    // inconnue.
    const bool illisible = accueil.value(QStringLiteral("illisibles")).toObject().contains(QStringLiteral("pause_generale"));
    const int etat = illisible ? -1 : pause.isObject() ? 1 : pause.isNull() ? 0 : -1;
    const QJsonObject detail = pause.toObject();
    const bool crochets = detail.value(QStringLiteral("reason")).toString() == kRaisonCrochets;
    QString libelle = libelles::kInconnu;
    if (etat == 1) {
        libelle = QStringLiteral("Hermes est en pause générale");
    } else if (etat == 0) {
        libelle = QStringLiteral("Aucune pause générale");
    }
    return QVariantMap{
        {QStringLiteral("etat"), etat},
        {QStringLiteral("libelle"), libelle},
        {QStringLiteral("raison"), etat == 1 ? libelles::texte(detail.value(QStringLiteral("reason"))) : QString()},
        {QStringLiteral("depuis"), etat == 1 ? libelles::dateIso(detail.value(QStringLiteral("engaged_at"))) : QString()},
        {QStringLiteral("crochets"), crochets},
        // La reprise est refusée par le greffon tant que les crochets shell existent : aucun
        // bouton qui échouerait n'est proposé, la page dit comment en sortir.
        {QStringLiteral("reprisePossible"), etat == 1 && !crochets},
        {QStringLiteral("pausePossible"), etat == 0},
        {QStringLiteral("raisonIllisible"), illisible ? raisonIllisible(accueil, QStringLiteral("pause_generale")) : QString()},
    };
}

QJsonArray AccueilViewModel::construireSessions(const QJsonObject &page)
{
    QJsonArray lignes;
    for (const QJsonValue &element : page.value(QStringLiteral("sessions")).toArray()) {
        const QJsonObject session = element.toObject();
        if (!libelles::estTexte(session.value(QStringLiteral("id")))) {
            continue; // sans identifiant, la ligne ne désigne rien
        }
        const QJsonValue actif = session.value(QStringLiteral("last_active"));
        lignes.append(QJsonObject{
            {QStringLiteral("id"), session.value(QStringLiteral("id")).toString()},
            {QStringLiteral("titre"), libelles::estTexte(session.value(QStringLiteral("title")))
                 ? session.value(QStringLiteral("title")).toString() : QStringLiteral("Sans titre")},
            {QStringLiteral("source"), libelles::texte(session.value(QStringLiteral("source")))},
            {QStringLiteral("messages"), libelles::nombre(session.value(QStringLiteral("message_count")))},
            {QStringLiteral("actifA"), actif.isDouble() ? libelles::date(actif)
                                                                  : libelles::date(session.value(QStringLiteral("started_at")))},
        });
    }
    return lignes;
}

} // namespace acp
