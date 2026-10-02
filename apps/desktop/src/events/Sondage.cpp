#include "events/Sondage.h"

#include "api/ApiClient.h"

#include <QTimer>

namespace acp {

Sondage::Sondage(Lecteur lecteur, std::chrono::milliseconds intervalle, QObject *parent)
    : QObject(parent)
    , m_lecteur(std::move(lecteur))
    , m_intervalle(intervalle)
    , m_minuterie(new QTimer(this))
{
    m_minuterie->setSingleShot(true);
    connect(m_minuterie, &QTimer::timeout, this, &Sondage::lancer);
}

Sondage::~Sondage()
{
    if (m_appel) {
        m_appel->disconnect(this);
        m_appel->abort();
    }
}

void Sondage::setIntervalle(std::chrono::milliseconds intervalle)
{
    if (intervalle == m_intervalle) {
        return;
    }
    m_intervalle = intervalle;
    if (m_actif && m_minuterie->isActive()) {
        programmer();
    }
}

void Sondage::setActif(bool actif)
{
    if (actif == m_actif) {
        return;
    }
    m_actif = actif;
    if (!m_actif) {
        m_minuterie->stop();
        m_relire = false;
        emit etatChange();
        return;
    }
    emit etatChange();
    lireMaintenant();
}

void Sondage::lireMaintenant()
{
    if (m_appel) {
        m_relire = true; // une seule relecture, servie à la fin de celle en vol
        return;
    }
    lancer();
}

void Sondage::oublier()
{
    if (m_appel) {
        ApiCall *appel = m_appel;
        m_appel = nullptr;
        appel->disconnect(this);
        appel->abort();
    }
    m_relire = false;
    m_luA = QDateTime();
    m_derniereErreur.clear();
    m_minuterie->stop();
    if (m_actif) {
        // Toujours affichée : la page relit aussitôt (le nouveau serveur, ou le refus du greffon
        // bloqué, qui s'affiche alors à la place des données oubliées).
        m_minuterie->start(0);
    }
    emit etatChange();
}

QString Sondage::libelleLuA() const
{
    return m_luA.isValid() ? QStringLiteral("Lu à %1").arg(m_luA.toLocalTime().toString(QStringLiteral("HH:mm:ss")))
                           : QStringLiteral("Jamais lu");
}

void Sondage::lancer()
{
    m_minuterie->stop();
    if (m_appel || !m_lecteur) {
        return;
    }
    m_relire = false;
    ApiCall *appel = m_lecteur();
    m_appel = appel;
    emit etatChange();
    connect(appel, &ApiCall::succeeded, this, [this, appel](const ApiResponse &reponse) {
        if (m_appel != appel) {
            return;
        }
        m_appel = nullptr;
        ++m_lectures;
        m_luA = QDateTime::currentDateTimeUtc();
        m_derniereErreur.clear();
        emit lu(reponse);
        emit etatChange();
        programmer();
    });
    connect(appel, &ApiCall::failed, this, [this, appel](const ApiError &erreur) {
        if (m_appel != appel) {
            return;
        }
        m_appel = nullptr;
        ++m_lectures;
        m_derniereErreur = erreur.message();
        emit echec(erreur);
        emit etatChange();
        programmer();
    });
}

void Sondage::programmer()
{
    if (m_relire) {
        m_relire = false;
        QTimer::singleShot(0, this, &Sondage::lancer);
        return;
    }
    if (m_actif) {
        m_minuterie->start(m_intervalle);
    }
}

} // namespace acp
