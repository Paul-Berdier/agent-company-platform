#include "events/FluxInvalidation.h"

#include "api/ApiError.h"
#include "api/ClientGreffonPoste.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>

#include <algorithm>

namespace acp {

namespace {

using std::chrono::milliseconds;

QDateTime maintenant() { return QDateTime::currentDateTimeUtc(); }

QString heure(const QDateTime &instant)
{
    return instant.toLocalTime().toString(QStringLiteral("HH:mm:ss"));
}

//! Corps gardé d'une réponse refusée (message du greffon), borné.
constexpr qint64 kCorpsRefusMax = 4096;

} // namespace

const QStringList &FluxInvalidation::sujets()
{
    static const QStringList liste{QStringLiteral("projets"),       QStringLiteral("questions"), QStringLiteral("poste"),
                                   QStringLiteral("quotas"),        QStringLiteral("notifications"),
                                   QStringLiteral("pause"),         QStringLiteral("discussions")};
    return liste;
}

QString FluxInvalidation::raisonAnnonce(const QString &etat, const QJsonValue &annonce)
{
    if (etat == QLatin1String("absent")) {
        return QStringLiteral("le greffon acp-poste n'annonce aucun flux d'invalidation (/v1/meta)");
    }
    if (etat == QLatin1String("illisible")) {
        return QStringLiteral("annonce du flux illisible dans /v1/meta");
    }
    if (etat != QLatin1String("annonce")) {
        return QStringLiteral("/v1/meta n'a pas encore été lu");
    }
    const QJsonObject objet = annonce.toObject();
    const QString chemin = objet.value(QStringLiteral("chemin")).toString();
    if (chemin != QLatin1String(kChemin)) {
        return QStringLiteral("flux annoncé sur un autre chemin (%1) : non ouvert").arg(chemin);
    }
    const QJsonValue version = objet.value(QStringLiteral("version"));
    if (!version.isDouble() || version.toDouble() != static_cast<double>(kVersion)) {
        return QStringLiteral("version du flux non prise en charge (%1 ; attendue : %2) : non ouvert")
            .arg(version.isDouble() ? QString::number(version.toDouble()) : QStringLiteral("Inconnu"))
            .arg(kVersion);
    }
    return {};
}

FluxInvalidation::FluxInvalidation(ClientGreffonPoste *greffon, QObject *parent)
    : QObject(parent)
    , m_greffon(greffon)
    , m_chien(new QTimer(this))
    , m_reprise(new QTimer(this))
{
    m_chien->setSingleShot(true);
    m_reprise->setSingleShot(true);
    m_reprise->setTimerType(Qt::PreciseTimer);
    m_raison = raisonAnnonce(QStringLiteral("inconnu"), {});
    connect(m_chien, &QTimer::timeout, this, [this] {
        // Connexion muette (veille, réseau changé, connexion à moitié ouverte) : jamais « temps réel ».
        if (m_reponse) {
            m_chienEchu = true;
            m_reponse->abort();
        }
    });
    connect(m_reprise, &QTimer::timeout, this, [this] {
        m_prochainEssai = QDateTime();
        m_repliJusqua = QDateTime(); // la reprise planifiée était celle du repli, s'il y en avait un
        m_raisonRepli.clear();
        ouvrir();
    });
}

FluxInvalidation::~FluxInvalidation()
{
    if (m_reponse) {
        QNetworkReply *reponse = m_reponse;
        m_reponse = nullptr;
        reponse->disconnect(this);
        reponse->abort();
        reponse->deleteLater();
    }
}

void FluxInvalidation::setAnnonce(const QString &etat, const QJsonValue &annonce)
{
    m_etatAnnonce = etat;
    // Échec fermé (relecture de P8b, constat desktop-1) : le verdict qui bloque le greffon ferme aussi un flux DÉJÀ
    // ouvert, même quand l'annonce n'a pas changé ; rien ne se rouvre avant un verdict qui lève le blocage. Il prime
    // sur l'annonce QUELLE QU'ELLE SOIT (seconde relecture, constat desktop-9 : un 404 de /v1/meta garde l'annonce
    // « inconnu », et la station disait alors « /v1/meta n'a pas encore été lu »).
    m_bloque = m_greffon && m_greffon->bloque();
    const QString raison = m_bloque ? m_greffon->raisonBlocage() : raisonAnnonce(etat, annonce);
    if (!raison.isEmpty()) {
        const bool change = m_annonceUtilisable || m_mode != Mode::Indisponible || m_raison != raison;
        m_annonceUtilisable = false;
        fermer();
        m_raison = raison;
        m_discussionsSuivies.reset();
        if (change) {
            changerMode(Mode::Indisponible);
            emit etatChange();
        }
        return;
    }
    if (!m_annonceUtilisable) {
        m_annonceUtilisable = true;
        m_raison.clear();
        changerMode(Mode::Ferme);
        emit etatChange();
    }
    // Aussi après un refus local (greffon bloqué) : un nouveau verdict peut l'avoir levé.
    ouvrir();
}

void FluxInvalidation::setActif(bool actif)
{
    if (actif == m_actif) {
        return;
    }
    m_actif = actif;
    if (!m_actif) {
        fermer();
        if (m_mode != Mode::Indisponible) {
            changerMode(Mode::Ferme);
        }
        emit etatChange();
        return;
    }
    ouvrir();
}

void FluxInvalidation::relancer()
{
    if (!m_actif || m_reponse) {
        return;
    }
    if (m_repliJusqua.isValid() && maintenant() < m_repliJusqua) {
        return; // le repli de 5 min reste : trois échecs viennent d'avoir lieu
    }
    m_reprise->stop();
    m_prochainEssai = QDateTime();
    ouvrir();
}

void FluxInvalidation::oublierRepli()
{
    // Relecture de P8b (constat desktop-2) : le repli (401, trois échecs) appartenait à la session perdue ; une session
    // neuve retente aussitôt. L'annonce et la révision restent : elles sont celles du serveur, qui n'a pas changé.
    m_echecs.clear();
    m_repliJusqua = QDateTime();
    m_raisonRepli.clear();
}

void FluxInvalidation::oublier()
{
    fermer();
    m_dernierId.clear();
    m_echecs.clear();
    m_repliJusqua = QDateTime();
    m_raisonRepli.clear();
    m_discussionsSuivies.reset();
    m_journal.clear();
    m_trames = 0;
    m_connexions = 0;
    m_tramesIllisibles = 0;
    // L'annonce appartenait à l'ancien serveur : rien ne s'ouvre avant le verdict du nouveau (setAnnonce).
    m_annonceUtilisable = false;
    m_etatAnnonce = QStringLiteral("inconnu");
    m_bloque = false;
    m_raison = raisonAnnonce(m_etatAnnonce, {});
    changerMode(Mode::Indisponible);
    emit etatChange();
}

void FluxInvalidation::ouvrir()
{
    if (!m_actif || !m_annonceUtilisable || m_reponse || m_reprise->isActive()) {
        return;
    }
    const QDateTime instant = maintenant();
    if (m_repliJusqua.isValid() && instant < m_repliJusqua) {
        // Fenêtre réduite puis rouverte pendant le repli : le nouvel essai garde son heure, et le repli sa raison (une
        // annonce relue entre-temps l'avait effacée : jamais « Temps réel indisponible () »).
        m_raison = m_raisonRepli;
        changerMode(Mode::Sondage);
        planifier(milliseconds(std::max<qint64>(0, instant.msecsTo(m_repliJusqua))));
        emit etatChange();
        return;
    }
    ApiError refus;
    QNetworkReply *reponse = m_greffon->ouvrirFlux(m_dernierId, &refus);
    if (!reponse) {
        // Refus local (greffon bloqué par le verdict, aucune session) : rien n'est émis.
        m_bloque = m_greffon->bloque();
        m_raison = m_bloque ? m_greffon->raisonBlocage() : refus.message();
        changerMode(Mode::Indisponible);
        emit etatChange();
        return;
    }
    m_reponse = reponse;
    ++m_connexions;
    m_fin = false;
    m_chienEchu = false;
    m_statutLu = false;
    m_statutValide = false;
    m_analyseur = SseParser();
    // Une réouverture après `fin` (toutes les 10 min) ou une reprise isolée garde le temps réel : la trame `etat` dira
    // ce qui a changé entre-temps. Seuls trois échecs le font tomber.
    if (m_mode == Mode::Ferme || m_mode == Mode::Indisponible) {
        changerMode(Mode::Connexion);
    }
    connect(reponse, &QNetworkReply::readyRead, this, [this, reponse] { lireOctets(reponse); });
    connect(reponse, &QNetworkReply::finished, this, [this, reponse] { terminer(reponse); });
    m_chien->start(m_reglages.chienDeGarde);
    emit etatChange();
}

void FluxInvalidation::fermer()
{
    m_reprise->stop();
    m_chien->stop();
    m_prochainEssai = QDateTime();
    if (m_reponse) {
        QNetworkReply *reponse = m_reponse;
        m_reponse = nullptr;
        reponse->disconnect(this);
        reponse->abort();
        reponse->deleteLater();
    }
}

void FluxInvalidation::lireOctets(QNetworkReply *reponse)
{
    if (reponse != m_reponse) {
        return;
    }
    if (!m_statutLu) {
        m_statutLu = true;
        const int statut = reponse->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QByteArray type = reponse->rawHeader(QByteArrayLiteral("Content-Type")).trimmed().toLower();
        m_statutValide = statut == 200 && type.startsWith("text/event-stream");
    }
    if (!m_statutValide) {
        return; // corps d'un refus : lu à la fin (message du greffon)
    }
    // Tout octet (trame ou battement) prouve que la connexion vit.
    m_chien->start(m_reglages.chienDeGarde);
    const QList<SseEvent> trames = m_analyseur.consume(reponse->readAll());
    for (const SseEvent &trame : trames) {
        traiter(trame);
        if (reponse != m_reponse) {
            return; // fermé pendant le traitement (une page a fermé la session)
        }
    }
}

void FluxInvalidation::terminer(QNetworkReply *reponse)
{
    if (reponse != m_reponse) {
        return; // ancienne connexion, fermée par la station
    }
    if (reponse->bytesAvailable() > 0 && (!m_statutLu || m_statutValide)) {
        lireOctets(reponse);
        if (reponse != m_reponse) {
            return;
        }
    }
    m_reponse = nullptr;
    m_chien->stop();
    reponse->disconnect(this);
    reponse->deleteLater();
    const int statut = reponse->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (m_chienEchu) {
        echec(QStringLiteral("aucun octet reçu du flux depuis %1 s").arg(m_reglages.chienDeGarde.count() / 1000.0));
        return;
    }
    if (m_statutValide && m_fin) {
        // Fin propre (durée maximale) : réouverture aussitôt, avec Last-Event-ID.
        ouvrir();
        return;
    }
    // Message français du greffon (`{"detail": {"code", "message"}}`), s'il y en a un.
    QString message;
    if (!m_statutValide) {
        const QJsonObject detail = QJsonDocument::fromJson(reponse->read(kCorpsRefusMax)).object()
                                       .value(QStringLiteral("detail")).toObject();
        message = detail.value(QStringLiteral("message")).toString();
    }
    if (statut == 401) {
        // Décision P8b-1 : jamais réessayé aussitôt ; nouvel essai dans 5 min (voir l'en-tête).
        m_raison = QStringLiteral("session refusée par le flux (401)");
        m_raisonRepli = m_raison;
        m_echecs.clear();
        m_repliJusqua = maintenant().addMSecs(m_reglages.nouvelEssai.count());
        changerMode(Mode::Sondage);
        planifier(m_reglages.nouvelEssai);
        emit etatChange();
        return;
    }
    if (statut == 429) {
        bool lu = false;
        const int secondes = reponse->rawHeader(QByteArrayLiteral("Retry-After")).trimmed().toInt(&lu);
        echec(message.isEmpty() ? QStringLiteral("trop de flux ouverts sur ce serveur (429)") : message,
              milliseconds(lu && secondes > 0 ? qint64(secondes) * 1000 : 0));
        return;
    }
    if (statut == 0) {
        echec(libelleErreurReseau(reponse->error()));
        return;
    }
    if (statut != 200) {
        echec(message.isEmpty() ? QStringLiteral("refusé par le serveur (HTTP %1)").arg(statut)
                                : QStringLiteral("%1 (HTTP %2)").arg(message).arg(statut));
        return;
    }
    if (!m_statutValide) {
        echec(QStringLiteral("la réponse n'est pas un flux d'événements"));
        return;
    }
    echec(reponse->error() == QNetworkReply::NoError ? QStringLiteral("flux terminé sans trame de fin")
                                                      : libelleErreurReseau(reponse->error()));
}

void FluxInvalidation::traiter(const SseEvent &trame)
{
    if (!trame.lastEventId.isEmpty()) {
        m_dernierId = trame.lastEventId;
    }
    if (trame.type == QLatin1String("fin")) {
        m_fin = true;
        noter(QStringLiteral("fin"), {});
        emit etatChange();
        return;
    }
    const bool etat = trame.type == QLatin1String("etat");
    if (!etat && trame.type != QLatin1String("changement")) {
        return; // événement inconnu : ignoré, comme la page web
    }
    QJsonParseError erreur;
    const QJsonDocument document = QJsonDocument::fromJson(trame.data.toUtf8(), &erreur);
    if (erreur.error != QJsonParseError::NoError || !document.isObject()) {
        ++m_tramesIllisibles;
        emit etatChange();
        return;
    }
    const QJsonObject donnees = document.object();
    QStringList changes;
    for (const QJsonValue &sujet : donnees.value(QStringLiteral("sujets")).toArray()) {
        // Un sujet inconnu de la station (greffon plus récent) est ignoré : la relecture de sûreté le couvre.
        if (sujet.isString() && sujets().contains(sujet.toString()) && !changes.contains(sujet.toString())) {
            changes.append(sujet.toString());
        }
    }
    ++m_trames;
    noter(trame.type, changes);
    if (etat) {
        m_echecs.clear();
        m_repliJusqua = QDateTime();
        m_raisonRepli.clear();
        m_raison.clear();
        const QJsonValue suivies = donnees.value(QStringLiteral("discussions_suivies"));
        m_discussionsSuivies = suivies.isBool() ? std::optional<bool>(suivies.toBool()) : std::nullopt;
        changerMode(Mode::TempsReel);
    }
    emit etatChange();
    if (!changes.isEmpty()) {
        emit invalidation(changes);
    }
}

void FluxInvalidation::echec(const QString &raison, milliseconds delaiMinimal)
{
    m_raison = raison;
    const QDateTime instant = maintenant();
    const qint64 fenetre = m_reglages.fenetreEchecs.count();
    m_echecs.erase(std::remove_if(m_echecs.begin(), m_echecs.end(),
                                  [&](const QDateTime &t) { return t.msecsTo(instant) > fenetre; }),
                   m_echecs.end());
    m_echecs.append(instant);
    if (m_echecs.size() >= kEchecsAvantRepli) {
        m_echecs.clear();
        const milliseconds delai = std::max(m_reglages.nouvelEssai, delaiMinimal);
        m_repliJusqua = instant.addMSecs(delai.count());
        m_raisonRepli = raison;
        changerMode(Mode::Sondage);
        planifier(delai);
        emit etatChange();
        return;
    }
    const QList<milliseconds> &reprises = m_reglages.reprises;
    const milliseconds palier = reprises.isEmpty() ? milliseconds(1000)
                                                   : reprises.value(std::min<qsizetype>(m_echecs.size() - 1, reprises.size() - 1));
    planifier(std::max(palier, delaiMinimal));
    emit etatChange();
}

void FluxInvalidation::planifier(milliseconds delai)
{
    m_prochainEssai = maintenant().addMSecs(delai.count());
    m_reprise->start(delai);
}

void FluxInvalidation::changerMode(Mode mode)
{
    m_mode = mode;
}

void FluxInvalidation::noter(const QString &evenement, const QStringList &sujets)
{
    m_journal.append(QStringLiteral("%1 %2 : %3")
                         .arg(heure(maintenant()), evenement,
                              sujets.isEmpty() ? QStringLiteral("aucun sujet") : sujets.join(QStringLiteral(", "))));
    while (m_journal.size() > kTramesGardees) {
        m_journal.removeFirst();
    }
}

std::chrono::milliseconds FluxInvalidation::intervalleRelecture(milliseconds repli, const QStringList &sujetsSuivis) const
{
    if (m_mode != Mode::TempsReel) {
        return repli;
    }
    const bool discussionsNonPubliees = sujetsSuivis.contains(QStringLiteral("discussions")) && m_discussionsSuivies == false;
    return std::max(repli, discussionsNonPubliees ? m_reglages.relectureDiscussions : m_reglages.relectureSurete);
}

QString FluxInvalidation::libelleCourt() const
{
    switch (m_mode) {
    case Mode::Ferme:
        return QStringLiteral("Temps réel : fermé");
    case Mode::Indisponible:
        return m_bloque ? QStringLiteral("Aucun flux (greffon bloqué)") : QStringLiteral("Sondage (aucun flux)");
    case Mode::Connexion:
        return QStringLiteral("Temps réel : connexion…");
    case Mode::TempsReel:
        return QStringLiteral("Temps réel");
    case Mode::Sondage:
        return QStringLiteral("Sondage (temps réel indisponible)");
    }
    return QStringLiteral("Inconnu");
}

QString FluxInvalidation::libelleEtat() const
{
    const QString essai = m_prochainEssai.isValid() ? QStringLiteral(" ; nouvel essai à %1").arg(heure(m_prochainEssai))
                                                    : QString();
    switch (m_mode) {
    case Mode::Ferme:
        return QStringLiteral("Fermé : aucune page ne lit (session absente ou fenêtre réduite).");
    case Mode::Indisponible:
        if (m_bloque) {
            // Greffon bloqué : ses pages ne lisent rien (refus local de la station), le flux non plus.
            QString raison = m_raison;
            if (raison.endsWith(QLatin1Char('.'))) {
                raison.chop(1);
            }
            return QStringLiteral("Non utilisé : %1 ; les pages du greffon ne lisent rien tant que ce verdict le bloque.")
                .arg(raison);
        }
        // Rien de lu : « Inconnu », jamais « non disponible » affirmé sans avoir lu /v1/meta.
        return QStringLiteral("%1 : %2 ; les pages sont relues par sondage.")
            .arg(!m_annonceUtilisable && m_etatAnnonce != QLatin1String("annonce") && m_etatAnnonce != QLatin1String("absent")
                         && m_etatAnnonce != QLatin1String("illisible")
                     ? QStringLiteral("Inconnu")
                     : QStringLiteral("Non utilisé"),
                 m_raison);
    case Mode::Connexion:
        return m_raison.isEmpty()
            ? QStringLiteral("Connexion en cours : les pages sont relues par sondage en attendant.")
            : QStringLiteral("Connexion en cours (dernier échec : %1%2) : les pages sont relues par sondage en attendant.")
                  .arg(m_raison, essai);
    case Mode::TempsReel: {
        QString texte = QStringLiteral("Temps réel : chaque page affichée est relue au changement signalé, et toutes "
                                       "les %1 min par sûreté (révision %2, %3 trames reçues).")
                            .arg(m_reglages.relectureSurete.count() / 60000.0)
                            .arg(m_dernierId.isEmpty() ? QStringLiteral("Inconnu") : m_dernierId)
                            .arg(m_trames);
        if (m_discussionsSuivies == false) {
            texte += QStringLiteral(" Discussions en attente non publiées par le serveur : relues toutes les %1 min.")
                         .arg(m_reglages.relectureDiscussions.count() / 60000.0);
        }
        if (!m_reponse && m_prochainEssai.isValid()) {
            texte += QStringLiteral(" Coupé (%1)%2.").arg(m_raison, essai);
        }
        return texte;
    }
    case Mode::Sondage:
        return QStringLiteral("Temps réel indisponible (%1) : les pages sont relues par sondage%2.").arg(m_raison, essai);
    }
    return QStringLiteral("Inconnu");
}

} // namespace acp
