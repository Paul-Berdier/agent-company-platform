#include "viewmodels/QuotasViewModel.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "viewmodels/Libelles.h"

#include <QJsonArray>

namespace acp {

namespace {

QString texteOuVide(const QJsonValue &valeur)
{
    return libelles::estTexte(valeur) ? valeur.toString() : QString();
}

//! Part de 0 à 100 telle que rendue, sinon absente : jamais déduite d'une autre valeur.
bool estPart(const QJsonValue &valeur)
{
    return valeur.isDouble() && valeur.toDouble() >= 0 && valeur.toDouble() <= 100;
}

} // namespace

QuotasViewModel::QuotasViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent)
    : PageViewModel(flux, parent)
    , m_greffon(greffon)
    , m_sondage(new Sondage([this] { return m_greffon->quotas(); }, kIntervalle, this))
    , m_voies(new JsonListModel(this))
    , m_hermes(libelles::kInconnu)
{
    // Étape P7 : mêmes sujets que la page web (Quotas.tsx).
    m_sondage->suivre(flux->invalidation(), {QStringLiteral("quotas"), QStringLiteral("poste")});
    connect(m_sondage, &Sondage::etatChange, this, &QuotasViewModel::lectureChange);
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) { lire(reponse.json.object()); });
}

QuotasViewModel::~QuotasViewModel() = default;

QString QuotasViewModel::lecture() const { return m_sondage->libelleLuA(); }
QString QuotasViewModel::erreur() const { return m_sondage->derniereErreur(); }

void QuotasViewModel::surActivite(bool actif)
{
    m_sondage->setActif(actif);
}

void QuotasViewModel::surLienRetabli()
{
    actualiser();
}

void QuotasViewModel::surOubli()
{
    m_sondage->oublier();
    m_voies->clear();
    m_hermes = libelles::kInconnu;
    m_lue = false;
    emit quotasChange();
}

void QuotasViewModel::actualiser()
{
    m_sondage->lireMaintenant();
}

void QuotasViewModel::lire(const QJsonObject &vue)
{
    QJsonArray voies;
    for (const QString &voie : {QStringLiteral("poste-codex"), QStringLiteral("poste-claude")}) {
        voies.append(construireVoie(voie, vue.value(voie).toObject()));
    }
    m_voies->setItems(voies);
    m_hermes = libelles::texte(vue.value(QStringLiteral("hermes")).toObject().value(QStringLiteral("libelle")));
    m_lue = true;
    emit quotasChange();
}

QJsonObject QuotasViewModel::construireVoie(const QString &voie, const QJsonObject &quotas)
{
    const libelles::Libelle etat = libelles::etatQuotas(quotas.value(QStringLiteral("etat")));
    const QJsonValue seuil = quotas.value(QStringLiteral("seuil_pct"));
    QJsonArray compteurs;
    for (const QJsonValue &compteur : quotas.value(QStringLiteral("compteurs")).toArray()) {
        compteurs.append(construireCompteur(compteur.toObject(), seuil));
    }
    const QString titre = libelles::voie(QJsonValue(voie));
    return QJsonObject{
        {QStringLiteral("voie"), voie},
        {QStringLiteral("titre"), titre.isEmpty() ? voie : titre},
        {QStringLiteral("etatLibelle"), etat.connu() ? etat.texte : libelles::texte(quotas.value(QStringLiteral("etat")))},
        {QStringLiteral("etatCle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
        {QStringLiteral("releveLe"), quotas.value(QStringLiteral("releve_le")).isDouble()
                                         ? libelles::date(quotas.value(QStringLiteral("releve_le")))
                                         : QString()},
        {QStringLiteral("seuil"), estPart(seuil) ? libelles::pourcentage(seuil) : libelles::kInconnu},
        {QStringLiteral("source"), texteOuVide(quotas.value(QStringLiteral("source_libelle")))},
        {QStringLiteral("detail"), texteOuVide(quotas.value(QStringLiteral("detail")))},
        {QStringLiteral("compteurs"), compteurs},
    };
}

QJsonObject QuotasViewModel::construireCompteur(const QJsonObject &compteur, const QJsonValue &seuil)
{
    QJsonArray fenetres;
    for (const QJsonValue &fenetre : compteur.value(QStringLiteral("windows")).toArray()) {
        fenetres.append(construireFenetre(fenetre.toObject(), seuil));
    }
    const bool enEchec = compteur.value(QStringLiteral("status")) != QJsonValue(QStringLiteral("ok"));
    return QJsonObject{
        {QStringLiteral("compteur"), libelles::texte(compteur.value(QStringLiteral("limit_id")))},
        {QStringLiteral("limiteAtteinte"), compteur.value(QStringLiteral("limit_reached")) == QJsonValue(true)},
        {QStringLiteral("offre"), libelles::texte(compteur.value(QStringLiteral("plan")))},
        {QStringLiteral("releveLe"), libelles::dateIso(compteur.value(QStringLiteral("observed_at")))},
        {QStringLiteral("detail"), enEchec ? texteOuVide(compteur.value(QStringLiteral("detail"))) : QString()},
        {QStringLiteral("fenetres"), fenetres},
    };
}

QJsonObject QuotasViewModel::construireFenetre(const QJsonObject &fenetre, const QJsonValue &seuil)
{
    const QJsonValue utilise = fenetre.value(QStringLiteral("used_percent"));
    const QJsonValue restant = fenetre.value(QStringLiteral("remaining_percent"));
    const QJsonValue minutes = fenetre.value(QStringLiteral("window_minutes"));
    // Niveau : seuil du routage atteint (« critical ») ou non (« normal ») ; sans part utilisée
    // ou sans seuil, « unknown » — jamais une estimation.
    QString niveau = QStringLiteral("unknown");
    if (estPart(utilise) && estPart(seuil)) {
        niveau = utilise.toDouble() >= seuil.toDouble() ? QStringLiteral("critical") : QStringLiteral("normal");
    }
    QString libelle = QStringLiteral("Fenêtre %1").arg(libelles::texte(fenetre.value(QStringLiteral("key"))));
    if (libelles::estNombre(minutes)) {
        libelle += QStringLiteral(" · %1 min").arg(minutes.toInteger());
    }
    return QJsonObject{
        {QStringLiteral("libelle"), libelle},
        {QStringLiteral("utilise"), estPart(utilise) ? libelles::pourcentage(utilise) : libelles::kInconnu},
        {QStringLiteral("restant"), estPart(restant) ? libelles::pourcentage(restant) : libelles::kInconnu},
        {QStringLiteral("restantPct"), estPart(restant) ? restant : QJsonValue(QJsonValue::Null)},
        // Jauge : part UTILISÉE et repère du seuil, comme la page web ; absents ⇒ null.
        {QStringLiteral("utilisePct"), estPart(utilise) ? utilise : QJsonValue(QJsonValue::Null)},
        {QStringLiteral("seuilPct"), estPart(seuil) ? seuil : QJsonValue(QJsonValue::Null)},
        {QStringLiteral("remise"), libelles::dateIso(fenetre.value(QStringLiteral("resets_at")))},
        {QStringLiteral("niveau"), niveau},
        {QStringLiteral("seuilAtteint"), niveau == QLatin1String("critical")},
    };
}

void QuotasViewModel::relever()
{
    if (gesteEnCours()) {
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->releverPoste();
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const QJsonValue message = reponse.json.object().value(QStringLiteral("message"));
        terminerGeste(libelles::estTexte(message) ? message.toString() : QStringLiteral("Ordre de relevé envoyé au poste."));
        m_sondage->lireMaintenant();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        m_sondage->lireMaintenant();
    });
}

} // namespace acp
