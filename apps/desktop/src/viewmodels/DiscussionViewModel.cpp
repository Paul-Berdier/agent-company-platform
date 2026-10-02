#include "viewmodels/DiscussionViewModel.h"

#include "events/EventStreamService.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "models/JsonListModel.h"
#include "viewmodels/Libelles.h"

#include <QLocale>

namespace acp {

namespace {

QString chaine(const QJsonValue &valeur)
{
    return valeur.isString() ? valeur.toString() : QString();
}

QString nomOutil(const QJsonObject &payload)
{
    const QString nom = chaine(payload.value(QStringLiteral("name")));
    return nom.isEmpty() ? QStringLiteral("inconnu") : nom;
}

} // namespace

DiscussionViewModel::DiscussionViewModel(GatewayClient *passerelle, EventStreamService *flux, QObject *parent)
    : PageViewModel(flux, parent)
    , m_passerelle(passerelle)
    , m_sessions(new JsonListModel(this))
    , m_transcription(new JsonListModel(this))
{
    // Liste des sessions relue par identifiant : elle garde son défilement et sa sélection.
    m_sessions->setCle({QStringLiteral("id")});
    connect(m_passerelle, &GatewayClient::evenement, this, &DiscussionViewModel::surEvenement);
    connect(m_passerelle, &GatewayClient::etatChange, this, &DiscussionViewModel::passerelleChange);
    connect(m_passerelle, &GatewayClient::relectureRequise, this, [this](const QString &sessionId, const QString &raison) {
        if (sessionId == m_vivante && !m_stockee.isEmpty()) {
            m_avis = raison;
            emit tourChange();
            ouvrir(m_stockee);
        }
    });
    connect(m_passerelle, &GatewayClient::prete, this, [this] {
        // Reconnexion : la session affichée est reprise (rattachée à la nouvelle connexion et
        // relue en entier) ; le rejeu par `seq` a déjà rendu ce qui manquait.
        if (m_dejaPrete && !m_stockee.isEmpty()) {
            ouvrir(m_stockee);
        }
        m_dejaPrete = true;
        if (actif()) {
            actualiserSessions();
        }
    });
    connect(flux, &EventStreamService::sessionsChangees, this, [this] {
        if (actif()) {
            actualiserSessions();
        }
    });
}

DiscussionViewModel::~DiscussionViewModel() = default;

bool DiscussionViewModel::passerellePrete() const
{
    return m_passerelle->etat() == GatewayClient::Etat::Pret;
}

QString DiscussionViewModel::etatPasserelle() const
{
    const QString raison = m_passerelle->raison();
    return raison.isEmpty() ? m_passerelle->libelleEtat() : QStringLiteral("%1 : %2").arg(m_passerelle->libelleEtat(), raison);
}

void DiscussionViewModel::surActivite(bool actif)
{
    if (actif) {
        actualiserSessions();
    }
}

void DiscussionViewModel::surLienRetabli()
{
    actualiserSessions();
}

void DiscussionViewModel::echecRpc(const QString &methode, const ErreurRpc &erreur)
{
    // Message de Hermes rendu comme une donnée, avec la méthode et le code.
    echouerGeste(erreur.locale ? QStringLiteral("« %1 » : %2").arg(methode, erreur.message)
                               : QStringLiteral("Hermes a refusé « %1 » : %2 (code %3)").arg(methode, erreur.message).arg(erreur.code));
}

// --- Liste des sessions -----------------------------------------------------------------------

void DiscussionViewModel::actualiserSessions()
{
    if (!passerellePrete()) {
        m_erreurSessions = QStringLiteral("Passerelle de Hermes indisponible (%1) : la liste n'est pas lue.").arg(etatPasserelle());
        emit sessionsChange();
        return;
    }
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.list"), QJsonObject{{QStringLiteral("limit"), 50}});
    connect(appel, &AppelRpc::reussi, this, [this](const QJsonValue &resultat) {
        QJsonArray lignes;
        for (const QJsonValue &element : resultat.toObject().value(QStringLiteral("sessions")).toArray()) {
            const QJsonObject ligne = construireSession(element.toObject());
            if (!ligne.isEmpty()) {
                lignes.append(ligne);
            }
        }
        m_sessions->setItems(lignes);
        m_sessionsLues = true;
        m_erreurSessions.clear();
        emit sessionsChange();
    });
    connect(appel, &AppelRpc::echoue, this, [this](const ErreurRpc &erreur) {
        m_erreurSessions = erreur.locale ? erreur.message
                                         : QStringLiteral("Hermes a refusé la liste des sessions : %1 (code %2)").arg(erreur.message).arg(erreur.code);
        emit sessionsChange();
    });
}

QJsonObject DiscussionViewModel::construireSession(const QJsonObject &ligne)
{
    const QString identifiant = chaine(ligne.value(QStringLiteral("id")));
    if (identifiant.trimmed().isEmpty()) {
        return {};
    }
    const QString titre = chaine(ligne.value(QStringLiteral("title")));
    return QJsonObject{
        {QStringLiteral("id"), identifiant},
        {QStringLiteral("titre"), titre.trimmed().isEmpty() ? QStringLiteral("Sans titre") : titre},
        {QStringLiteral("apercu"), chaine(ligne.value(QStringLiteral("preview")))},
        {QStringLiteral("source"), libelles::texte(ligne.value(QStringLiteral("source")))},
        {QStringLiteral("date"), libelles::date(ligne.value(QStringLiteral("started_at")))},
        {QStringLiteral("messages"), libelles::nombre(ligne.value(QStringLiteral("message_count")))},
    };
}

// --- Ouverture, création, sortie ----------------------------------------------------------------

void DiscussionViewModel::laisserSession()
{
    if (m_vivante.isEmpty()) {
        return;
    }
    m_passerelle->oublierSession(m_vivante);
    // Une session sans tour en cours est fermée côté Hermes ; un tour en cours n'est jamais
    // interrompu par un simple changement de session.
    if (!m_tourEnCours && passerellePrete()) {
        m_passerelle->canal()->requete(QStringLiteral("session.close"), QJsonObject{{QStringLiteral("session_id"), m_vivante}});
    }
    m_vivante.clear();
}

void DiscussionViewModel::ouvrir(const QString &identifiantStocke)
{
    if (identifiantStocke.trimmed().isEmpty()) {
        return;
    }
    if (!passerellePrete()) {
        echouerGeste(QStringLiteral("Passerelle de Hermes indisponible (%1) : la session ne peut pas être ouverte.")
                         .arg(etatPasserelle()));
        return;
    }
    if (identifiantStocke != m_stockee) {
        laisserSession();
        m_transcription->clear();
        m_titre.clear();
        majTour(false);
    }
    const quint64 generation = ++m_generation;
    m_stockee = identifiantStocke;
    m_ouverture = true;
    m_erreurSession.clear();
    emit sessionChange();
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.resume"),
                                                     QJsonObject{{QStringLiteral("session_id"), identifiantStocke}});
    connect(appel, &AppelRpc::reussi, this, [this, generation, identifiantStocke](const QJsonValue &resultat) {
        if (generation == m_generation) {
            adopter(resultat.toObject(), identifiantStocke);
        }
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation != m_generation) {
            return;
        }
        m_ouverture = false;
        emit sessionChange();
        echecRpc(QStringLiteral("session.resume"), erreur);
    });
}

void DiscussionViewModel::nouvelle()
{
    if (!passerellePrete()) {
        echouerGeste(QStringLiteral("Passerelle de Hermes indisponible (%1) : aucune discussion ne peut être créée.")
                         .arg(etatPasserelle()));
        return;
    }
    laisserSession();
    m_transcription->clear();
    m_titre.clear();
    m_stockee.clear();
    majTour(false);
    const quint64 generation = ++m_generation;
    m_ouverture = true;
    emit sessionChange();
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.create"), QJsonObject{});
    connect(appel, &AppelRpc::reussi, this, [this, generation](const QJsonValue &resultat) {
        if (generation != m_generation) {
            return;
        }
        const QJsonObject creee = resultat.toObject();
        adopter(creee, chaine(creee.value(QStringLiteral("stored_session_id"))));
        actualiserSessions();
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation != m_generation) {
            return;
        }
        m_ouverture = false;
        emit sessionChange();
        echecRpc(QStringLiteral("session.create"), erreur);
    });
}

void DiscussionViewModel::adopter(const QJsonObject &resultat, const QString &stockee)
{
    const QString vivante = chaine(resultat.value(QStringLiteral("session_id")));
    m_ouverture = false;
    if (vivante.isEmpty()) {
        emit sessionChange();
        echouerGeste(QStringLiteral("Réponse de Hermes illisible : aucun identifiant de session vivante."));
        return;
    }
    if (!m_vivante.isEmpty() && m_vivante != vivante) {
        m_passerelle->oublierSession(m_vivante);
    }
    m_vivante = vivante;
    m_stockee = stockee.isEmpty() ? chaine(resultat.value(QStringLiteral("stored_session_id"))) : stockee;
    const QJsonObject info = resultat.value(QStringLiteral("info")).toObject();
    const QString titre = chaine(info.value(QStringLiteral("title")));
    if (!titre.isEmpty()) {
        m_titre = titre;
    }
    // Suivie dès maintenant : la transcription relue tient lieu de point de départ, le rejeu
    // ne reprendra que ce qui viendra après.
    m_passerelle->suivreSession(m_vivante);

    QJsonArray lignes;
    int rang = 0;
    for (const QJsonValue &element : resultat.value(QStringLiteral("messages")).toArray()) {
        lignes.append(construireMessage(element.toObject(), rang++));
    }
    const bool enCours = resultat.value(QStringLiteral("running")) == QJsonValue(true);
    const QJsonObject vol = resultat.value(QStringLiteral("inflight")).toObject();
    if (enCours && !vol.isEmpty()) {
        // Tour en vol à la reprise : la réponse partielle déjà produite est montrée en cours.
        const QString partiel = chaine(vol.value(QStringLiteral("assistant")));
        lignes.append(QJsonObject{{QStringLiteral("cle"), QStringLiteral("vol-%1").arg(++m_compteur)},
                                  {QStringLiteral("role"), QStringLiteral("assistant")},
                                  {QStringLiteral("auteur"), QStringLiteral("Hermes")},
                                  {QStringLiteral("texte"), partiel},
                                  {QStringLiteral("enCours"), true},
                                  {QStringLiteral("statut"), QString()},
                                  {QStringLiteral("avertissement"), QString()},
                                  {QStringLiteral("heure"), QString()}});
    }
    m_transcription->setItems(lignes);
    majTour(enCours);
    emit sessionChange();
}

void DiscussionViewModel::quitter()
{
    ++m_generation;
    laisserSession();
    m_stockee.clear();
    m_titre.clear();
    m_ouverture = false;
    m_transcription->clear();
    majTour(false);
    emit sessionChange();
}

QJsonObject DiscussionViewModel::construireMessage(const QJsonObject &message, int rang)
{
    const QString role = chaine(message.value(QStringLiteral("role")));
    QString auteur;
    QString texte = chaine(message.value(QStringLiteral("text")));
    QString genre;
    if (role == QLatin1String("user")) {
        auteur = QStringLiteral("Vous");
        genre = QStringLiteral("utilisateur");
    } else if (role == QLatin1String("assistant")) {
        auteur = QStringLiteral("Hermes");
        genre = QStringLiteral("assistant");
    } else if (role == QLatin1String("tool")) {
        // Une ligne d'outil dit son nom, jamais son contenu brut (arguments, sortie).
        auteur = QStringLiteral("Outil");
        genre = QStringLiteral("outil");
        texte = QStringLiteral("Outil « %1 »").arg(nomOutil(message));
    } else if (role == QLatin1String("system")) {
        auteur = QStringLiteral("Système");
        genre = QStringLiteral("systeme");
    } else {
        auteur = role.isEmpty() ? libelles::kInconnu : role;
        genre = QStringLiteral("autre");
    }
    const QJsonValue heure = message.value(QStringLiteral("timestamp"));
    return QJsonObject{
        {QStringLiteral("cle"), QStringLiteral("h-%1").arg(rang)},
        {QStringLiteral("role"), genre},
        {QStringLiteral("auteur"), auteur},
        {QStringLiteral("texte"), texte},
        {QStringLiteral("enCours"), false},
        {QStringLiteral("statut"), QString()},
        {QStringLiteral("avertissement"), QString()},
        {QStringLiteral("heure"), heure.isDouble() ? libelles::date(heure) : QString()},
    };
}

// --- Tour ---------------------------------------------------------------------------------------

QString DiscussionViewModel::messageEnvoi(const QJsonValue &statut)
{
    const QString s = chaine(statut);
    if (s == QLatin1String("streaming")) return QStringLiteral("Message envoyé : Hermes répond.");
    if (s == QLatin1String("queued")) return QStringLiteral("Message mis en file : Hermes le traitera après le tour en cours.");
    if (s == QLatin1String("steered")) return QStringLiteral("Message transmis à Hermes pendant le tour en cours.");
    if (s == QLatin1String("redirected")) return QStringLiteral("Message redirigé par Hermes.");
    return QStringLiteral("Message envoyé.");
}

QString DiscussionViewModel::issueDuTour(const QJsonObject &fin)
{
    const QString statut = chaine(fin.value(QStringLiteral("status")));
    if (statut == QLatin1String("interrupted")) {
        return QStringLiteral("Tour interrompu.");
    }
    if (statut == QLatin1String("error")) {
        QString raison = chaine(fin.value(QStringLiteral("error")));
        if (raison.isEmpty()) {
            raison = chaine(fin.value(QStringLiteral("failure_reason")));
        }
        return raison.isEmpty() ? QStringLiteral("Tour en échec (raison non donnée par Hermes).")
                                : QStringLiteral("Tour en échec : %1").arg(raison);
    }
    return {};
}

void DiscussionViewModel::majTour(bool enCours)
{
    m_tourEnCours = enCours;
    if (!enCours) {
        m_ligneEtat.clear();
    }
    emit tourChange();
}

void DiscussionViewModel::ajouter(QJsonObject ligne)
{
    if (!ligne.contains(QStringLiteral("cle"))) {
        ligne.insert(QStringLiteral("cle"), QStringLiteral("l-%1").arg(++m_compteur));
    }
    for (const char *champ : {"texte", "statut", "avertissement", "heure"}) {
        if (!ligne.contains(QString::fromLatin1(champ))) {
            ligne.insert(QString::fromLatin1(champ), QString());
        }
    }
    if (!ligne.contains(QStringLiteral("enCours"))) {
        ligne.insert(QStringLiteral("enCours"), false);
    }
    m_transcription->appendItem(ligne);
}

int DiscussionViewModel::dernierEnCours(const QString &role) const
{
    for (int index = m_transcription->count() - 1; index >= 0; --index) {
        const QJsonObject ligne = m_transcription->itemAt(index);
        if (ligne.value(QStringLiteral("role")).toString() == role && ligne.value(QStringLiteral("enCours")).toBool()) {
            return index;
        }
    }
    return -1;
}

int DiscussionViewModel::ligneDeCle(const QString &cle) const
{
    for (int index = m_transcription->count() - 1; index >= 0; --index) {
        if (m_transcription->itemAt(index).value(QStringLiteral("cle")).toString() == cle) {
            return index;
        }
    }
    return -1;
}

bool DiscussionViewModel::envoyer(const QString &texte)
{
    if (m_vivante.isEmpty()) {
        echouerGeste(QStringLiteral("Ouvrez ou créez une discussion avant d'écrire."));
        return false;
    }
    if (texte.trimmed().isEmpty()) {
        echouerGeste(QStringLiteral("Le message est vide."));
        return false;
    }
    if (!passerellePrete()) {
        echouerGeste(QStringLiteral("Passerelle de Hermes indisponible (%1) : le message n'est pas envoyé.").arg(etatPasserelle()));
        return false;
    }
    // Le message apparaît tout de suite, à sa place, avec son état réel d'envoi.
    const QString cle = QStringLiteral("envoi-%1").arg(++m_compteur);
    ajouter(QJsonObject{{QStringLiteral("cle"), cle},
                        {QStringLiteral("role"), QStringLiteral("utilisateur")},
                        {QStringLiteral("auteur"), QStringLiteral("Vous")},
                        {QStringLiteral("texte"), texte},
                        {QStringLiteral("statut"), QStringLiteral("Envoi…")}});
    debuterGeste();
    const QString vivante = m_vivante;
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("prompt.submit"),
                                                     QJsonObject{{QStringLiteral("session_id"), vivante},
                                                                 {QStringLiteral("text"), texte}});
    connect(appel, &AppelRpc::reussi, this, [this, cle](const QJsonValue &resultat) {
        const int index = ligneDeCle(cle);
        if (index >= 0) {
            QJsonObject ligne = m_transcription->itemAt(index);
            ligne.insert(QStringLiteral("statut"), QString());
            m_transcription->setItem(index, ligne);
        }
        terminerGeste(messageEnvoi(resultat.toObject().value(QStringLiteral("status"))));
    });
    connect(appel, &AppelRpc::echoue, this, [this, cle](const ErreurRpc &erreur) {
        const int index = ligneDeCle(cle);
        if (index >= 0) {
            QJsonObject ligne = m_transcription->itemAt(index);
            ligne.insert(QStringLiteral("statut"), QStringLiteral("Non envoyé"));
            m_transcription->setItem(index, ligne);
        }
        echecRpc(QStringLiteral("prompt.submit"), erreur);
    });
    return true;
}

void DiscussionViewModel::arreter()
{
    if (m_vivante.isEmpty() || !passerellePrete()) {
        return;
    }
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.interrupt"),
                                                     QJsonObject{{QStringLiteral("session_id"), m_vivante}});
    connect(appel, &AppelRpc::reussi, this, [this](const QJsonValue &) {
        terminerGeste(QStringLiteral("Arrêt demandé à Hermes."));
    });
    connect(appel, &AppelRpc::echoue, this, [this](const ErreurRpc &erreur) { echecRpc(QStringLiteral("session.interrupt"), erreur); });
}

void DiscussionViewModel::surEvenement(const QString &type, const QString &sessionId, qint64, const QJsonValue &valeur)
{
    const QJsonObject payload = valeur.toObject();
    if (type == QLatin1String("session.title")) {
        // `session_id` du titre est l'identifiant STOCKÉ.
        const QString cible = chaine(payload.value(QStringLiteral("session_id")));
        if ((!cible.isEmpty() && cible == m_stockee) || (cible.isEmpty() && sessionId == m_vivante)) {
            m_titre = chaine(payload.value(QStringLiteral("title")));
            emit sessionChange();
        }
        return;
    }
    if (m_vivante.isEmpty() || sessionId != m_vivante) {
        return; // autre session : rien n'est rendu ici
    }
    if (type == QLatin1String("message.start")) {
        ajouter(QJsonObject{{QStringLiteral("role"), QStringLiteral("assistant")},
                            {QStringLiteral("auteur"), QStringLiteral("Hermes")},
                            {QStringLiteral("enCours"), true}});
        majTour(true);
    } else if (type == QLatin1String("message.delta")) {
        int index = dernierEnCours(QStringLiteral("assistant"));
        if (index < 0) {
            ajouter(QJsonObject{{QStringLiteral("role"), QStringLiteral("assistant")},
                                {QStringLiteral("auteur"), QStringLiteral("Hermes")},
                                {QStringLiteral("enCours"), true}});
            index = m_transcription->count() - 1;
            majTour(true);
        }
        QJsonObject ligne = m_transcription->itemAt(index);
        ligne.insert(QStringLiteral("texte"), ligne.value(QStringLiteral("texte")).toString() + chaine(payload.value(QStringLiteral("text"))));
        m_transcription->setItem(index, ligne);
    } else if (type == QLatin1String("message.complete")) {
        int index = dernierEnCours(QStringLiteral("assistant"));
        if (index < 0) {
            ajouter(QJsonObject{{QStringLiteral("role"), QStringLiteral("assistant")}, {QStringLiteral("auteur"), QStringLiteral("Hermes")}});
            index = m_transcription->count() - 1;
        }
        QJsonObject ligne = m_transcription->itemAt(index);
        const QString final = chaine(payload.value(QStringLiteral("text")));
        if (!final.isEmpty()) {
            ligne.insert(QStringLiteral("texte"), final);
        }
        ligne.insert(QStringLiteral("enCours"), false);
        ligne.insert(QStringLiteral("statut"), issueDuTour(payload));
        ligne.insert(QStringLiteral("avertissement"), chaine(payload.value(QStringLiteral("warning"))));
        m_transcription->setItem(index, ligne);
        majTour(false);
    } else if (type == QLatin1String("tool.start")) {
        const QString cle = QStringLiteral("outil-") + chaine(payload.value(QStringLiteral("tool_id")));
        ajouter(QJsonObject{{QStringLiteral("cle"), cle},
                            {QStringLiteral("role"), QStringLiteral("outil")},
                            {QStringLiteral("auteur"), QStringLiteral("Outil")},
                            {QStringLiteral("texte"), QStringLiteral("Outil « %1 » en cours…").arg(nomOutil(payload))},
                            {QStringLiteral("enCours"), true}});
    } else if (type == QLatin1String("tool.complete")) {
        const QString cle = QStringLiteral("outil-") + chaine(payload.value(QStringLiteral("tool_id")));
        const QString resume = chaine(payload.value(QStringLiteral("summary")));
        const QJsonValue duree = payload.value(QStringLiteral("duration_s"));
        QString texte = resume.isEmpty() ? QStringLiteral("Outil « %1 » terminé").arg(nomOutil(payload))
                                         : QStringLiteral("Outil « %1 » : %2").arg(nomOutil(payload), resume);
        if (duree.isDouble()) {
            texte += QStringLiteral(" (%1 s)").arg(QLocale(QLocale::French).toString(duree.toDouble(), 'f', 1));
        }
        const int index = ligneDeCle(cle);
        QJsonObject ligne{{QStringLiteral("cle"), cle},
                          {QStringLiteral("role"), QStringLiteral("outil")},
                          {QStringLiteral("auteur"), QStringLiteral("Outil")},
                          {QStringLiteral("texte"), texte},
                          {QStringLiteral("enCours"), false},
                          {QStringLiteral("statut"), QString()},
                          {QStringLiteral("avertissement"), QString()},
                          {QStringLiteral("heure"), QString()}};
        if (index >= 0) {
            m_transcription->setItem(index, ligne);
        } else {
            ajouter(ligne);
        }
    } else if (type == QLatin1String("status.update")) {
        m_ligneEtat = chaine(payload.value(QStringLiteral("text")));
        emit tourChange();
    } else if (type == QLatin1String("error")) {
        m_erreurSession = chaine(payload.value(QStringLiteral("message")));
        emit tourChange();
    } else if (type == QLatin1String("notice")) {
        m_avis = chaine(payload.value(QStringLiteral("message")));
        emit tourChange();
    } else if (type == QLatin1String("session.info") || type == QLatin1String("request.cancel")) {
        // session.info : informations d'état non rendues ; request.cancel : DemandesAgent.
    } else {
        ++m_ignores; // événement hors du sous-ensemble traité : compté, jamais deviné
        emit tourChange();
    }
}

} // namespace acp
