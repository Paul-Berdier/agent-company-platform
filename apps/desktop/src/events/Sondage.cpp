#include "events/Sondage.h"

#include "api/ApiClient.h"
#include "events/FluxInvalidation.h"

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
    emit cadenceChange();
}

void Sondage::suivre(FluxInvalidation *flux, const QStringList &sujets)
{
    if (m_flux || !flux) {
        return;
    }
    m_flux = flux;
    m_sujets = sujets;
    m_regroupement = new QTimer(this);
    m_regroupement->setSingleShot(true);
    connect(m_regroupement, &QTimer::timeout, this, [this] {
        if (m_actif) {
            ++m_relecturesSurSignal;
            lireMaintenant();
        }
    });
    connect(flux, &FluxInvalidation::invalidation, this, [this](const QStringList &changes) {
        if (!m_actif) {
            return; // la page relit à son activation, de toute façon
        }
        for (const QString &sujet : changes) {
            if (m_sujets.contains(sujet)) {
                // Une rafale de trames, une lecture.
                if (!m_regroupement->isActive()) {
                    m_regroupement->start(m_flux->reglages().regroupement);
                }
                return;
            }
        }
    });
    connect(flux, &FluxInvalidation::etatChange, this, &Sondage::reprogrammer);
    connect(flux, &FluxInvalidation::etatChange, this, &Sondage::cadenceChange);
    emit cadenceChange();
}

std::chrono::milliseconds Sondage::intervalleEffectif() const
{
    return m_flux ? m_flux->intervalleRelecture(m_intervalle, m_sujets) : m_intervalle;
}

QString Sondage::toutesLes(std::chrono::milliseconds intervalle)
{
    const qint64 ms = intervalle.count();
    if (ms >= 120000 && ms % 60000 == 0) {
        return QStringLiteral("toutes les %1 minutes").arg(ms / 60000);
    }
    if (ms % 1000 == 0) {
        return QStringLiteral("toutes les %1 secondes").arg(ms / 1000);
    }
    return QStringLiteral("toutes les %1 secondes")
        .arg(QString::number(static_cast<double>(ms) / 1000.0, 'g', 3).replace(QLatin1Char('.'), QLatin1Char(',')));
}

bool Sondage::tempsReel() const
{
    return m_flux && m_flux->tempsReel();
}

bool Sondage::connexionTempsReel() const
{
    return m_flux && m_flux->mode() == FluxInvalidation::Mode::Connexion;
}

QString Sondage::etatHorsTempsReel() const
{
    if (m_flux && m_flux->mode() == FluxInvalidation::Mode::Connexion) {
        return QStringLiteral("Connexion au temps réel en cours");
    }
    if (m_flux && m_flux->mode() == FluxInvalidation::Mode::Sondage) {
        return QStringLiteral("Temps réel indisponible");
    }
    return QStringLiteral("Sans temps réel");
}

QString Sondage::libelleCadence() const
{
    const QString intervalle = toutesLes(intervalleEffectif());
    if (tempsReel()) {
        return m_sujets.isEmpty()
            ? QStringLiteral("Page relue %1 (temps réel : relecture de sûreté seulement), tant qu'elle est affichée.")
                  .arg(intervalle)
            : QStringLiteral("Page relue à chaque changement signalé par le serveur (temps réel) et %1 par sûreté, tant "
                             "qu'elle est affichée.")
                  .arg(intervalle);
    }
    return connexionTempsReel()
        ? QStringLiteral("%1 : page relue %2 en attendant, tant qu'elle est affichée.").arg(etatHorsTempsReel(), intervalle)
        : QStringLiteral("%1 : page relue %2 tant qu'elle est affichée.").arg(etatHorsTempsReel(), intervalle);
}

void Sondage::reprogrammer()
{
    // Le mode du flux a changé (temps réel gagné ou perdu) : la prochaine lecture suit le nouvel intervalle.
    if (m_actif && m_minuterie->isActive() && intervalleEffectif() != m_intervalleApplique) {
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
        if (m_regroupement) {
            m_regroupement->stop();
        }
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
    if (m_regroupement) {
        m_regroupement->stop();
    }
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
        m_intervalleApplique = intervalleEffectif();
        m_minuterie->start(m_intervalleApplique);
    }
}

} // namespace acp
