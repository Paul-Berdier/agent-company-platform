#include "viewmodels/AccueilViewModel.h"

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

const QStringList kOrdreVoies = {QStringLiteral("poste-codex"), QStringLiteral("poste-claude"),
                                 QStringLiteral("hermes")};

QString libelleVoieOuBrut(const QString &cle)
{
    const QString libelle = libelles::voie(cle);
    return libelle.isEmpty() ? cle : libelle;
}

} // namespace

AccueilViewModel::AccueilViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                                   QObject *parent)
    : PageViewModel(flux, parent)
    , m_client(client)
    , m_greffon(greffon)
    , m_projets(new Sondage([this] { return m_greffon->projets(); }, Sondage::kIntervallePage, this))
    , m_quotas(new Sondage([this] { return m_greffon->quotas(); }, Sondage::kIntervallePage, this))
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
    , m_sessions(new JsonListModel(this))
{
    lireProjets({});
    m_carteQuotas = construireCarteQuotas({});
    for (Sondage *sondage : {m_projets, m_quotas, m_sondageSessions}) {
        connect(sondage, &Sondage::etatChange, this, &AccueilViewModel::lectureChange);
    }
    connect(m_projets, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        const QJsonObject liste = reponse.json.object();
        lireProjets(liste);
        this->flux()->noterProjets(liste);
    });
    connect(m_quotas, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        m_carteQuotas = construireCarteQuotas(reponse.json.object());
        emit quotasChange();
    });
    connect(m_sondageSessions, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        m_sessions->setItems(construireSessions(reponse.json.object()));
        m_sessionsLues = true;
        emit lectureChange();
    });
}

AccueilViewModel::~AccueilViewModel() = default;

void AccueilViewModel::surActivite(bool actif)
{
    for (Sondage *sondage : {m_projets, m_quotas, m_sondageSessions}) {
        sondage->setActif(actif);
    }
}

void AccueilViewModel::surLienRetabli()
{
    actualiser();
}

void AccueilViewModel::surOubli()
{
    for (Sondage *sondage : {m_projets, m_quotas, m_sondageSessions}) {
        sondage->oublier();
    }
    lireProjets({});
    m_carteQuotas = construireCarteQuotas({});
    emit quotasChange();
    m_sessions->clear();
    m_sessionsLues = false;
    emit lectureChange();
}

void AccueilViewModel::actualiser()
{
    for (Sondage *sondage : {m_projets, m_quotas, m_sondageSessions}) {
        sondage->lireMaintenant();
    }
}

QString AccueilViewModel::lectureProjets() const { return m_projets->libelleLuA(); }
QString AccueilViewModel::erreurProjets() const { return m_projets->derniereErreur(); }
QString AccueilViewModel::lectureQuotas() const { return m_quotas->libelleLuA(); }
QString AccueilViewModel::erreurQuotas() const { return m_quotas->derniereErreur(); }
QString AccueilViewModel::lectureSessions() const { return m_sondageSessions->libelleLuA(); }
QString AccueilViewModel::erreurSessions() const { return m_sondageSessions->derniereErreur(); }

void AccueilViewModel::lireProjets(const QJsonObject &liste)
{
    m_carteProjets = construireCarteProjets(liste);
    m_carteQuestions = construireCarteQuestions(liste);
    m_cartePoste = construireCartePoste(liste);
    m_cartePause = construireCartePause(liste);
    emit projetsChange();
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
        m_projets->lireMaintenant();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        m_projets->lireMaintenant();
    });
}

// --- Fonctions pures -------------------------------------------------------------------

QVariantMap AccueilViewModel::construireCarteProjets(const QJsonObject &liste)
{
    const QJsonValue valeur = liste.value(QStringLiteral("projets"));
    const bool lisible = valeur.isArray();
    int total = 0;
    int actifs = 0;
    int enPause = 0;
    qint64 faites = 0;
    qint64 cartes = 0;
    bool faitesConnues = true;
    qint64 attente = 0;
    bool attenteConnue = true;
    QString note;
    QString noteProjet;
    bool noteTronquee = false;
    for (const QJsonValue &element : valeur.toArray()) {
        const QJsonObject projet = element.toObject();
        ++total;
        const QString etat = projet.value(QStringLiteral("etat")).toString();
        if (etat == QLatin1String("creation") || etat == QLatin1String("actif")) {
            ++actifs;
        } else if (etat == QLatin1String("en_pause")) {
            ++enPause;
        }
        const QJsonObject compteurs = projet.value(QStringLiteral("compteurs")).toObject();
        const QJsonValue f = compteurs.value(QStringLiteral("faites"));
        const QJsonValue t = compteurs.value(QStringLiteral("total"));
        if (libelles::estNombre(f) && libelles::estNombre(t)) {
            faites += f.toInteger();
            cartes += t.toInteger();
        } else {
            faitesConnues = false; // tableau illisible : compteurs inconnus, jamais inventés
        }
        const QJsonValue a = compteurs.value(QStringLiteral("en_attente_du_poste"));
        if (libelles::estNombre(a)) {
            attente += a.toInteger();
        } else {
            attenteConnue = false;
        }
        // La liste vient du plus récent au plus ancien : la première note trouvée est celle du
        // projet le plus récent qui en a une.
        if (note.isEmpty() && libelles::estTexte(projet.value(QStringLiteral("derniere_note")))) {
            note = projet.value(QStringLiteral("derniere_note")).toString();
            noteProjet = libelles::texte(projet.value(QStringLiteral("titre")));
            noteTronquee = projet.value(QStringLiteral("derniere_note_tronquee")).toBool();
        }
    }
    return QVariantMap{
        {QStringLiteral("lisible"), lisible},
        {QStringLiteral("aucunProjet"), lisible && total == 0},
        {QStringLiteral("total"), lisible ? QString::number(total) : libelles::kInconnu},
        {QStringLiteral("actifs"), lisible ? QString::number(actifs) : libelles::kInconnu},
        {QStringLiteral("enPause"), lisible ? QString::number(enPause) : libelles::kInconnu},
        {QStringLiteral("cartesFaites"), lisible && faitesConnues
             ? QStringLiteral("%1 sur %2").arg(faites).arg(cartes) : libelles::kInconnu},
        {QStringLiteral("attentePoste"), lisible && attenteConnue ? QString::number(attente) : libelles::kInconnu},
        {QStringLiteral("derniereNote"), note},
        {QStringLiteral("derniereNoteProjet"), noteProjet},
        {QStringLiteral("derniereNoteTronquee"), noteTronquee},
    };
}

QVariantMap AccueilViewModel::construireCarteQuestions(const QJsonObject &liste)
{
    const QJsonValue valeur = liste.value(QStringLiteral("questions_ouvertes"));
    if (!libelles::estNombre(valeur)) {
        return QVariantMap{{QStringLiteral("nombre"), libelles::kInconnu}, {QStringLiteral("connu"), false},
                           {QStringLiteral("attente"), false}, {QStringLiteral("libelle"), libelles::kInconnu}};
    }
    const qint64 nombre = valeur.toInteger();
    const QString libelle = nombre == 0 ? QStringLiteral("Aucune question en attente.")
        : nombre == 1             ? QStringLiteral("1 question attend votre réponse ou celle de Hermes.")
                                  : QStringLiteral("%1 questions attendent votre réponse ou celle de Hermes.").arg(nombre);
    return QVariantMap{{QStringLiteral("nombre"), QString::number(nombre)}, {QStringLiteral("connu"), true},
                       {QStringLiteral("attente"), nombre > 0}, {QStringLiteral("libelle"), libelle}};
}

QVariantMap AccueilViewModel::construireCartePoste(const QJsonObject &liste)
{
    const QJsonValue valeur = liste.value(QStringLiteral("poste"));
    const QJsonObject poste = valeur.toObject();
    const QJsonValue etatBrut = poste.value(QStringLiteral("etat"));
    const libelles::Libelle etat = libelles::etatPoste(etatBrut);

    const QJsonValue machine = poste.value(QStringLiteral("machine"));
    const QJsonValue vue = poste.value(QStringLiteral("derniere_vue"));
    QString vuA;
    if (libelles::estTexte(poste.value(QStringLiteral("derniere_vue_lisible")))) {
        vuA = poste.value(QStringLiteral("derniere_vue_lisible")).toString();
    } else if (vue.isDouble()) {
        vuA = libelles::date(vue);
    } else {
        vuA = vue.isNull() ? QStringLiteral("Jamais") : libelles::kInconnu;
    }
    const QJsonValue horsLigne = poste.value(QStringLiteral("hors_ligne_depuis"));
    return QVariantMap{
        {QStringLiteral("etat"), etat.connu() ? etat.texte : libelles::texte(etatBrut)},
        {QStringLiteral("cle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
        {QStringLiteral("connu"), etat.connu()},
        {QStringLiteral("machine"), libelles::estTexte(machine) ? machine.toString()
                                    : machine.isNull() && valeur.isObject() ? QStringLiteral("Aucune")
                                                                            : libelles::kInconnu},
        {QStringLiteral("vuA"), valeur.isObject() ? vuA : libelles::kInconnu},
        {QStringLiteral("horsLigneDepuis"), horsLigne.isDouble() ? libelles::date(horsLigne) : QString()},
        {QStringLiteral("cartesEnAttente"), libelles::nombre(poste.value(QStringLiteral("cartes_en_attente")))},
        {QStringLiteral("message"), libelles::estTexte(poste.value(QStringLiteral("message")))
             ? poste.value(QStringLiteral("message")).toString() : QString()},
    };
}

QVariantMap AccueilViewModel::construireCartePause(const QJsonObject &liste)
{
    const QJsonValue pause = liste.value(QStringLiteral("pause_generale"));
    // Objet présent : engagée ; null : levée ; absente ou d'un autre type : inconnue.
    const int etat = pause.isObject() ? 1 : pause.isNull() ? 0 : -1;
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
    };
}

QVariantMap AccueilViewModel::construireCarteQuotas(const QJsonObject &quotas)
{
    QStringList cles = kOrdreVoies;
    for (const QString &cle : quotas.keys()) {
        if (!cles.contains(cle)) {
            cles.append(cle);
        }
    }
    double pire = -1;
    QString voie;
    QJsonObject retenue;
    for (const QString &cle : std::as_const(cles)) {
        const QJsonObject entree = quotas.value(cle).toObject();
        const QJsonValue utilise = entree.value(QStringLiteral("resume")).toObject().value(QStringLiteral("pourcentage_utilise"));
        if (utilise.isDouble() && utilise.toDouble() > pire) {
            pire = utilise.toDouble();
            voie = cle;
            retenue = entree;
        }
    }
    if (voie.isEmpty()) {
        return QVariantMap{
            {QStringLiteral("connu"), false},
            {QStringLiteral("libelle"), libelles::kInconnu},
            {QStringLiteral("detail"), quotas.isEmpty() ? QString()
                                                        : QStringLiteral("Aucune voie n'a de relevé de quota.")},
            {QStringLiteral("cle"), QStringLiteral("unknown")},
            {QStringLiteral("etat"), libelles::kInconnu},
            {QStringLiteral("remise"), QString()},
        };
    }
    const QJsonObject resume = retenue.value(QStringLiteral("resume")).toObject();
    const QJsonValue seuil = retenue.value(QStringLiteral("seuil_pct"));
    const QString cle = seuil.isDouble() ? (pire >= seuil.toDouble() ? QStringLiteral("degraded") : QStringLiteral("succeeded"))
                                         : QStringLiteral("pending");
    // La pastille dit ce qu'elle mesure : la position par rapport au seuil d'alerte du greffon.
    const QString etat = !seuil.isDouble()           ? QStringLiteral("Seuil inconnu")
        : cle == QLatin1String("degraded")          ? QStringLiteral("Seuil d'alerte atteint")
                                                    : QStringLiteral("Sous le seuil d'alerte");
    const QJsonValue remise = resume.value(QStringLiteral("remise_a_zero"));
    return QVariantMap{
        {QStringLiteral("connu"), true},
        {QStringLiteral("libelle"), QStringLiteral("%1 : %2 utilisés")
                                        .arg(libelleVoieOuBrut(voie), libelles::pourcentage(resume.value(QStringLiteral("pourcentage_utilise"))))},
        {QStringLiteral("detail"), seuil.isDouble() ? QStringLiteral("Seuil d'alerte : %1").arg(libelles::pourcentage(seuil))
                                                    : QString()},
        {QStringLiteral("cle"), cle},
        {QStringLiteral("etat"), etat},
        {QStringLiteral("remise"), libelles::estTexte(remise)
             ? QStringLiteral("Remise à zéro : %1").arg(libelles::dateIso(remise)) : QString()},
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
