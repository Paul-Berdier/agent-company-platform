#include "viewmodels/PageViewModel.h"

#include "api/ApiError.h"
#include "events/EventStreamService.h"

#include <QTimer>

namespace acp {

PageViewModel::PageViewModel(EventStreamService *flux, QObject *parent)
    : QObject(parent)
    , m_flux(flux)
{
    connect(m_flux, &EventStreamService::pagesActivesChange, this, &PageViewModel::majActivite);
    connect(m_flux, &EventStreamService::lienRetabli, this, [this] {
        if (m_actif) {
            surLienRetabli();
        }
    });
}

void PageViewModel::setPageVisible(bool visible)
{
    if (visible == m_pageVisible) {
        return;
    }
    m_pageVisible = visible;
    emit pageVisibleChange();
    // Différé : la page QML pose ce drapeau pendant sa construction ; la lecture part une
    // fois le composant prêt, jamais au milieu d'une liaison.
    QTimer::singleShot(0, this, &PageViewModel::majActivite);
}

void PageViewModel::majActivite()
{
    const bool actif = m_pageVisible && m_flux->pagesActives();
    if (actif == m_actif) {
        return;
    }
    m_actif = actif;
    emit actifChange();
    surActivite(m_actif);
}

void PageViewModel::effacerGeste()
{
    if (m_messageGeste.isEmpty() && m_erreurGeste.isEmpty()) {
        return;
    }
    m_messageGeste.clear();
    m_erreurGeste.clear();
    emit gesteChange();
}

void PageViewModel::debuterGeste()
{
    m_gesteEnCours = true;
    m_messageGeste.clear();
    m_erreurGeste.clear();
    emit gesteChange();
}

void PageViewModel::terminerGeste(const QString &message)
{
    m_gesteEnCours = false;
    m_messageGeste = message;
    m_erreurGeste.clear();
    emit gesteChange();
}

void PageViewModel::echouerGeste(const ApiError &erreur)
{
    echouerGeste(messageDuRefus(erreur));
}

QString PageViewModel::messageDuRefus(const ApiError &erreur)
{
    // Refus du greffon (`{"detail": {"code", "message"}}`) : son message français est rendu
    // TEL QUEL, comme sur la page web (messageDuRefus de apps/interface/src/projets/api.ts).
    // Toute autre erreur garde le titre de sa famille.
    if (!erreur.code().isEmpty() && !erreur.isGateRejection() && !erreur.detail().isEmpty()) {
        return erreur.detail();
    }
    return erreur.message();
}

void PageViewModel::echouerGeste(const QString &message)
{
    m_gesteEnCours = false;
    m_messageGeste.clear();
    m_erreurGeste = message;
    emit gesteChange();
}

} // namespace acp
