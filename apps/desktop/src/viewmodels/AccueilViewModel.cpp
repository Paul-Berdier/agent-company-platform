#include "viewmodels/AccueilViewModel.h"

#include "services/CompatibiliteHermes.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "viewmodels/Libelles.h"

#include <QJsonArray>

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
    , m_projetsEnCours(new JsonListModel(this))
    , m_sessions(new JsonListModel(this))
{
    m_projetsEnCours->setCle({QStringLiteral("id")});
    lireAccueil({});
    m_lue = false;
    for (Sondage *sondage : {m_accueil, m_sondageSessions}) {
        connect(sondage, &Sondage::etatChange, this, &AccueilViewModel::lectureChange);
    }
    connect(m_accueil, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        lireAccueil(reponse.json.object());
        m_lue = true;
        emit accueilChange();
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
    QList<Sondage *> liste{m_accueil, m_sondageSessions};
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
    m_meta->setActif(actif());
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

void AccueilViewModel::lireAccueil(const QJsonObject &accueil)
{
    m_carteATraiter = construireCarteATraiter(accueil);
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

QVariantMap AccueilViewModel::construireCarteATraiter(const QJsonObject &accueil)
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
    const QJsonValue total = a.value(QStringLiteral("total"));
    const QJsonValue chezHermes = accueil.value(QStringLiteral("chez_hermes"));
    // Les discussions en attente ne sont pas lues par la station (session.active_list) : le total le dit, et
    // « Rien n'attend votre décision » n'est jamais affiché (relecture finale de P7 : jamais zéro par défaut).
    return QVariantMap{
        {QStringLiteral("lisible"), true},
        {QStringLiteral("raison"), QString()},
        {QStringLiteral("total"), libelles::nombre(total)},
        {QStringLiteral("mention"), QStringLiteral("(discussions en attente : état inconnu, non comptées)")},
        {QStringLiteral("questions"), libelles::nombre(a.value(QStringLiteral("questions")))},
        {QStringLiteral("decisions"), libelles::nombre(a.value(QStringLiteral("decisions")))},
        {QStringLiteral("revues"), libelles::nombre(a.value(QStringLiteral("revues")))},
        {QStringLiteral("arretees"), libelles::nombre(a.value(QStringLiteral("arretees")))},
        {QStringLiteral("discussions"), QStringLiteral("Inconnues")},
        {QStringLiteral("chezHermes"), libelles::nombre(chezHermes)},
        {QStringLiteral("attente"), libelles::estNombre(total) && total.toInteger() > 0},
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
        // Objet servi `{voie: raison}` ; vide : « Aucune » ; autre forme : « Inconnu » (constat desktop-3 de P7).
        {QStringLiteral("voiesFermees"), !voies.isObject() ? libelles::kInconnu
                                         : fermees.isEmpty() ? QStringLiteral("Aucune")
                                                             : fermees.join(QLatin1Char('\n'))},
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
