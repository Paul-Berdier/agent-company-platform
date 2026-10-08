#include "events/EventStreamService.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "events/VeilleKanban.h"
#include "gateway/DiscussionsEnAttente.h"
#include "gateway/GatewayClient.h"
#include "viewmodels/Libelles.h"

#include <algorithm>

namespace acp {

EventStreamService::EventStreamService(ApiClient *client, ClientGreffonPoste *greffon, GatewayClient *passerelle,
                                       QObject *parent)
    : QObject(parent)
    , m_greffon(greffon)
    , m_passerelle(passerelle)
    , m_veille(new VeilleKanban(client, this))
    , m_invalidation(new FluxInvalidation(greffon, this))
    , m_discussions(new DiscussionsEnAttente(passerelle, this))
    , m_fond(new Sondage([this] { return m_greffon->accueil(); }, kIntervalleFond, this))
{
    oublierResume();
    // Le badge et la barre d'état suivent tous les sujets (l'Accueil agrégé les couvre tous).
    m_fond->suivre(m_invalidation, FluxInvalidation::sujets());
    connect(m_invalidation, &FluxInvalidation::etatChange, this, &EventStreamService::sourcesChange);
    connect(m_discussions, &DiscussionsEnAttente::change, this, &EventStreamService::resumeChange);
    connect(m_fond, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        lireResume(reponse.json.object());
        m_discussions->lire(); // le badge compte aussi les discussions en attente, comme la page web
    });
    connect(m_fond, &Sondage::etatChange, this, &EventStreamService::sourcesChange);
    connect(m_veille, &VeilleKanban::etatChange, this, &EventStreamService::sourcesChange);
    connect(m_veille, &VeilleKanban::changement, this, &EventStreamService::tableauChange);
    if (m_passerelle) {
        connect(m_passerelle, &GatewayClient::etatChange, this, &EventStreamService::sourcesChange);
        // Passerelle prête (après le premier sondage, ou après une coupure) : les discussions se relisent.
        connect(m_passerelle, &GatewayClient::prete, this, [this] {
            if (m_sessionOuverte) {
                m_discussions->lire();
            }
        });
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

void EventStreamService::setAnnonceFlux(const QString &etat, const QJsonObject &annonce)
{
    m_invalidation->setAnnonce(etat, annonce);
}

void EventStreamService::demarrer()
{
    if (m_sessionOuverte) {
        return;
    }
    const bool avant = pagesActives();
    m_sessionOuverte = true;
    m_fond->setActif(true);
    m_invalidation->setActif(pagesActives());
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
    m_invalidation->setActif(false);
    m_invalidation->oublierRepli(); // le repli (401, échecs) était celui de la session perdue
    m_veille->arreter();
    m_discussions->oublier();
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
        m_invalidation->relancer();
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
    // Fenêtre réduite : flux fermé, comme une page web cachée ; rouverte : il se rouvre.
    m_invalidation->setActif(pagesActives());
    emit fenetreActiveChange();
    if (avant != pagesActives()) {
        emit pagesActivesChange();
    }
}

void EventStreamService::noterAccueil(const QJsonObject &accueil)
{
    if (m_sessionOuverte) {
        lireResume(accueil);
    }
}

void EventStreamService::noterProjets(const QJsonObject &liste)
{
    if (m_sessionOuverte) {
        lirePosteEtPause(liste.value(QStringLiteral("poste")).toObject().value(QStringLiteral("etat")),
                         liste.value(QStringLiteral("pause_generale")), false);
        emit resumeChange();
    }
}

void EventStreamService::lirePosteEtPause(const QJsonValue &etatPoste, const QJsonValue &pause, bool pauseIllisible)
{
    const libelles::Libelle etat = libelles::etatPoste(etatPoste);
    m_libellePoste = etat.connu() ? etat.texte : libelles::kInconnu;
    m_clePoste = etat.connu() ? etat.cle : QStringLiteral("unknown");
    // pause_generale : objet présent = engagée, null = levée — sauf bloc dit illisible par le greffon ; absente ou
    // d'un autre type = inconnue.
    m_pauseGenerale = pauseIllisible ? kInconnu : pause.isObject() ? 1 : pause.isNull() ? 0 : kInconnu;
}

void EventStreamService::lireResume(const QJsonObject &accueil)
{
    // Accueil agrégé (noyau/accueil.construire) : un bloc illisible vaut `null`, sa raison est dans `illisibles`.
    const QJsonValue total = accueil.value(QStringLiteral("a_traiter")).toObject().value(QStringLiteral("total"));
    m_aTraiterGreffon = libelles::estNombre(total) ? static_cast<int>(total.toInteger()) : -1;
    const bool pauseIllisible = accueil.value(QStringLiteral("illisibles")).toObject().contains(QStringLiteral("pause_generale"));
    lirePosteEtPause(accueil.value(QStringLiteral("executant")).toObject().value(QStringLiteral("etat")),
                     accueil.value(QStringLiteral("pause_generale")), pauseIllisible);
    emit resumeChange();
}

void EventStreamService::oublierResume()
{
    m_aTraiterGreffon = -1;
    m_discussions->oublier();
    m_libellePoste = libelles::kInconnu;
    m_clePoste = QStringLiteral("unknown");
    m_pauseGenerale = kInconnu;
    emit resumeChange();
}

int EventStreamService::aTraiter() const
{
    if (m_aTraiterGreffon < 0) {
        return -1;
    }
    return m_aTraiterGreffon + std::max(0, m_discussions->nombre());
}

QString EventStreamService::libelleATraiter() const
{
    if (m_aTraiterGreffon < 0) {
        return QStringLiteral("À traiter par vous : Inconnu");
    }
    // Discussions en attente illisibles (passerelle indisponible, refus) : le libellé le dit, jamais zéro deviné.
    return m_discussions->connues() ? QStringLiteral("À traiter par vous : %1").arg(aTraiter())
                                    : QStringLiteral("À traiter par vous : %1 (discussions non comptées)").arg(aTraiter());
}

QString EventStreamService::descriptionATraiter() const
{
    return m_discussions->connues() ? QStringLiteral("demandes à traiter par vous")
                                    : QStringLiteral("demandes à traiter par vous (discussions non comptées)");
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
    return QStringLiteral("Poste : %1 · %2%3").arg(m_libellePoste, libelleATraiter(), pause);
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
                        .arg(m_fond->intervalleEffectif().count() / 1000)
                        .arg(m_fond->libelleLuA());
    if (!m_fond->derniereErreur().isEmpty()) {
        texte += QStringLiteral(" · Dernière lecture impossible : ") + m_fond->derniereErreur();
    }
    return texte;
}

QString EventStreamService::etatFlux() const
{
    return m_invalidation->libelleEtat();
}

bool EventStreamService::tempsReel() const
{
    return m_invalidation->tempsReel();
}

QString EventStreamService::libelleTempsReel() const
{
    return m_sessionOuverte ? m_invalidation->libelleCourt() : QString();
}

} // namespace acp
