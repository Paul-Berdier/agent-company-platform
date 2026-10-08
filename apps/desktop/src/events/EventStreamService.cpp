#include "events/EventStreamService.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/Sondage.h"
#include "events/VeilleKanban.h"
#include "gateway/GatewayClient.h"
#include "viewmodels/Libelles.h"

namespace acp {

EventStreamService::EventStreamService(ApiClient *client, ClientGreffonPoste *greffon, GatewayClient *passerelle,
                                       QObject *parent)
    : QObject(parent)
    , m_greffon(greffon)
    , m_passerelle(passerelle)
    , m_veille(new VeilleKanban(client, this))
    , m_fond(new Sondage([this] { return m_greffon->projets(); }, kIntervalleFond, this))
{
    oublierResume();
    connect(m_fond, &Sondage::lu, this, [this](const ApiResponse &reponse) { lireResume(reponse.json.object()); });
    connect(m_fond, &Sondage::etatChange, this, &EventStreamService::sourcesChange);
    connect(m_veille, &VeilleKanban::etatChange, this, &EventStreamService::sourcesChange);
    connect(m_veille, &VeilleKanban::changement, this, &EventStreamService::tableauChange);
    if (m_passerelle) {
        connect(m_passerelle, &GatewayClient::etatChange, this, &EventStreamService::sourcesChange);
        connect(m_passerelle, &GatewayClient::evenement, this,
                [this](const QString &type, const QString &, qint64, const QJsonValue &) {
                    if (type == QLatin1String("sessions.changed")) {
                        emit sessionsChangees();
                    }
                });
    }
}

EventStreamService::~EventStreamService() = default;

void EventStreamService::setIntervalleFond(std::chrono::milliseconds intervalle)
{
    m_fond->setIntervalle(intervalle);
}

void EventStreamService::demarrer()
{
    if (m_sessionOuverte) {
        return;
    }
    const bool avant = pagesActives();
    m_sessionOuverte = true;
    m_fond->setActif(true);
    if (avant != pagesActives()) {
        emit pagesActivesChange();
    }
    emit sourcesChange();
}

void EventStreamService::arreter()
{
    const bool avant = pagesActives();
    m_sessionOuverte = false;
    m_fond->setActif(false);
    m_veille->arreter();
    oublierResume();
    if (avant != pagesActives()) {
        emit pagesActivesChange();
    }
    emit sourcesChange();
}

void EventStreamService::signalerLien(bool enLigne)
{
    const bool retour = m_lienConnu && !m_lienEnLigne && enLigne;
    m_lienConnu = true;
    m_lienEnLigne = enLigne;
    if (retour && m_sessionOuverte) {
        m_fond->lireMaintenant();
        emit lienRetabli();
    }
}

void EventStreamService::setFenetreActive(bool active)
{
    if (active == m_fenetreActive) {
        return;
    }
    const bool avant = pagesActives();
    m_fenetreActive = active;
    emit fenetreActiveChange();
    if (avant != pagesActives()) {
        emit pagesActivesChange();
    }
}

void EventStreamService::noterProjets(const QJsonObject &liste)
{
    if (m_sessionOuverte) {
        lireResume(liste);
    }
}

void EventStreamService::lireResume(const QJsonObject &liste)
{
    const QJsonValue questions = liste.value(QStringLiteral("questions_ouvertes"));
    m_questionsOuvertes = libelles::estNombre(questions) ? static_cast<int>(questions.toInteger()) : -1;

    const QJsonObject poste = liste.value(QStringLiteral("poste")).toObject();
    const libelles::Libelle etat = libelles::etatPoste(poste.value(QStringLiteral("etat")));
    m_libellePoste = etat.connu() ? etat.texte : libelles::kInconnu;
    m_clePoste = etat.connu() ? etat.cle : QStringLiteral("unknown");

    // pause_generale : objet présent = engagée, null = levée ; absente ou d'un autre type = inconnue.
    const QJsonValue pause = liste.value(QStringLiteral("pause_generale"));
    m_pauseGenerale = pause.isObject() ? 1 : pause.isNull() ? 0 : kInconnu;
    emit resumeChange();
}

void EventStreamService::oublierResume()
{
    m_questionsOuvertes = -1;
    m_libellePoste = libelles::kInconnu;
    m_clePoste = QStringLiteral("unknown");
    m_pauseGenerale = kInconnu;
    emit resumeChange();
}

QString EventStreamService::libelleQuestions() const
{
    if (m_questionsOuvertes < 0) {
        return libelles::kInconnu;
    }
    if (m_questionsOuvertes == 0) {
        return QStringLiteral("Aucune question ouverte");
    }
    return m_questionsOuvertes == 1 ? QStringLiteral("1 question ouverte")
                                    : QStringLiteral("%1 questions ouvertes").arg(m_questionsOuvertes);
}

QString EventStreamService::libelleResume() const
{
    if (!m_sessionOuverte) {
        return QString();
    }
    QString pause;
    if (m_pauseGenerale == 1) {
        pause = QStringLiteral(" · Pause générale engagée");
    }
    return QStringLiteral("Poste : %1 · %2%3").arg(m_libellePoste, libelleQuestions(), pause);
}

QString EventStreamService::etatPasserelle() const
{
    if (!m_passerelle) {
        return libelles::kInconnu;
    }
    const QString raison = m_passerelle->raison();
    return raison.isEmpty() ? m_passerelle->libelleEtat()
                            : QStringLiteral("%1 : %2").arg(m_passerelle->libelleEtat(), raison);
}

QString EventStreamService::etatVeille() const
{
    if (m_veille->etat() == VeilleKanban::Etat::Arretee) {
        return QStringLiteral("Arrêtée (aucun projet affiché)");
    }
    QString texte = QStringLiteral("%1 (tableau %2)").arg(m_veille->libelleEtat(), m_veille->tableau());
    if (!m_veille->raison().isEmpty()) {
        texte += QStringLiteral(" : ") + m_veille->raison();
    }
    return texte;
}

QString EventStreamService::etatSondage() const
{
    if (!m_sessionOuverte) {
        return QStringLiteral("Arrêté (aucune session)");
    }
    QString texte = QStringLiteral("Toutes les %1 s · %2")
                        .arg(m_fond->intervalle().count() / 1000)
                        .arg(m_fond->libelleLuA());
    if (!m_fond->derniereErreur().isEmpty()) {
        texte += QStringLiteral(" · Dernière lecture impossible : ") + m_fond->derniereErreur();
    }
    return texte;
}

QString EventStreamService::etatFluxGreffon(const QString &etatFlux)
{
    if (etatFlux == QLatin1String("annonce")) {
        return QStringLiteral("Annoncé par le serveur ; non utilisé par cette station : les pages sont relues par "
                              "sondage (le navigateur, lui, l'emploie).");
    }
    if (etatFlux == QLatin1String("absent")) {
        return QStringLiteral("Non disponible sur ce serveur : le greffon acp-poste n'annonce aucun flux "
                              "d'événements ; les pages sont relues par sondage.");
    }
    if (etatFlux == QLatin1String("illisible")) {
        return QStringLiteral("Annonce illisible dans /v1/meta ; les pages sont relues par sondage.");
    }
    return QStringLiteral("Inconnu : /v1/meta n'a pas encore été lu ; les pages sont relues par sondage.");
}

} // namespace acp
