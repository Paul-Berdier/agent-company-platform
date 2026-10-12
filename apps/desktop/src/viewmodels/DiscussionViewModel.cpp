#include "viewmodels/DiscussionViewModel.h"

#include "events/EventStreamService.h"
#include "gateway/DiscussionsEnAttente.h"
#include "gateway/GatewayClient.h"
#include "gateway/JsonRpcChannel.h"
#include "models/JsonListModel.h"
#include "viewmodels/Libelles.h"

#include <QLocale>
#include <QRegularExpression>

#include <algorithm>

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
    , m_modelesSession(new JsonListModel(this))
{
    // Liste des sessions relue par identifiant : elle garde son défilement et sa sélection.
    m_sessions->setCle({QStringLiteral("id")});
    m_modelesSession->setCle({QStringLiteral("fournisseur"), QStringLiteral("modele")});
    connect(this, &DiscussionViewModel::sessionChange, this, &DiscussionViewModel::brouillonChange);
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
    // État d'attente partagé avec le badge, l'Accueil et la file Questions : la liste suit chacune de ses lectures.
    connect(flux->discussions(), &DiscussionsEnAttente::change, this, &DiscussionViewModel::appliquerAttente);
}

DiscussionViewModel::~DiscussionViewModel() = default;

QString DiscussionViewModel::brouillon() const
{
    const QString cle = m_stockee.isEmpty() ? m_vivante : m_stockee;
    return cle.isEmpty() ? m_consigneEnAttente : m_brouillons.value(cle);
}

void DiscussionViewModel::setBrouillon(const QString &texte)
{
    const QString cle = m_stockee.isEmpty() ? m_vivante : m_stockee;
    if (cle.isEmpty()) {
        if (m_consigneEnAttente == texte) return;
        m_consigneEnAttente = texte;
        emit brouillonChange();
        return;
    }
    if (m_brouillons.value(cle) == texte) return;
    if (texte.isEmpty()) m_brouillons.remove(cle);
    else m_brouillons.insert(cle, texte);
    emit brouillonChange();
}

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

void DiscussionViewModel::surOubli()
{
    m_brouillons.clear();
    m_consigneEnAttente.clear();
    m_generationConsigne = 0;
    ++m_generationListe;
    m_chargementSessions = false;
    m_peutChargerPlus = false;
    m_limiteSessions = 50;
    m_rechercheSessions.clear();
    m_dejaPrete = false;
    quitter();
    m_sessions->clear();
    m_lignes = {};
    m_sessionsLues = false;
    m_erreurSessions.clear();
    emit sessionsChange();
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

void DiscussionViewModel::setRechercheSessions(const QString &texte)
{
    if (m_rechercheSessions == texte) return;
    m_rechercheSessions = texte;
    appliquerAttente();
}

void DiscussionViewModel::actualiserSessions()
{
    lireSessions(m_limiteSessions);
}

void DiscussionViewModel::chargerPlusSessions()
{
    if (!m_peutChargerPlus || m_chargementSessions) return;
    lireSessions(std::min(m_limiteSessions + 50, 500));
}

void DiscussionViewModel::lireSessions(int limite)
{
    const quint64 generation = ++m_generationListe;
    if (!passerellePrete()) {
        m_chargementSessions = false;
        m_erreurSessions = QStringLiteral("Passerelle de Hermes indisponible (%1) : la liste n'est pas lue.").arg(etatPasserelle());
        emit sessionsChange();
        return;
    }
    m_chargementSessions = true;
    emit sessionsChange();
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.list"), QJsonObject{{QStringLiteral("limit"), limite}});
    connect(appel, &AppelRpc::reussi, this, [this, generation, limite](const QJsonValue &resultat) {
        if (generation != m_generationListe) return;
        m_chargementSessions = false;
        const QJsonValue sessions = resultat.toObject().value(QStringLiteral("sessions"));
        if (!sessions.isArray()) {
            m_erreurSessions = QStringLiteral("Réponse de Hermes illisible : aucune liste de discussions.");
            emit sessionsChange();
            return;
        }
        QJsonArray lignes;
        for (const QJsonValue &element : sessions.toArray()) {
            const QJsonObject ligne = construireSession(element.toObject());
            if (!ligne.isEmpty()) lignes.append(ligne);
        }
        m_lignes = lignes;
        m_limiteSessions = limite;
        m_peutChargerPlus = limite < 500 && sessions.toArray().size() >= limite;
        m_sessionsLues = true;
        m_erreurSessions.clear();
        appliquerAttente();
        flux()->discussions()->lire();
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation != m_generationListe) return;
        m_chargementSessions = false;
        m_erreurSessions = erreur.locale ? erreur.message
                                         : QStringLiteral("Hermes a refusé la liste des sessions : %1 (code %2)").arg(erreur.message).arg(erreur.code);
        emit sessionsChange();
    });
}

QJsonArray DiscussionViewModel::marquerEnAttente(const QJsonArray &lignes, const QJsonArray &enAttente, bool connues)
{
    QStringList cles;
    if (connues) {
        for (const QJsonValue &session : enAttente) {
            cles.append(session.toObject().value(QStringLiteral("cle")).toString());
        }
    }
    QJsonArray marquees;
    for (const QJsonValue &element : lignes) {
        QJsonObject ligne = element.toObject();
        ligne.insert(QStringLiteral("enAttente"), cles.contains(ligne.value(QStringLiteral("id")).toString()));
        marquees.append(ligne);
    }
    return marquees;
}

void DiscussionViewModel::appliquerAttente()
{
    const DiscussionsEnAttente *attente = flux()->discussions();
    QJsonArray visibles;
    const QString recherche = m_rechercheSessions.trimmed();
    for (const QJsonValue &element : m_lignes) {
        const QJsonObject ligne = element.toObject();
        if (recherche.isEmpty() || ligne.value(QStringLiteral("titre")).toString().contains(recherche, Qt::CaseInsensitive)
            || ligne.value(QStringLiteral("apercu")).toString().contains(recherche, Qt::CaseInsensitive)
            || ligne.value(QStringLiteral("id")).toString().contains(recherche, Qt::CaseInsensitive)) visibles.append(ligne);
    }
    m_sessions->setItems(marquerEnAttente(visibles, attente->sessions(), attente->connues()));
    emit sessionsChange();
}

QString DiscussionViewModel::attenteInconnue() const
{
    const DiscussionsEnAttente *attente = flux()->discussions();
    // Comme la page web (T.discussion.attenteInconnue, relecture finale de P7, constat produit-4) : dit seulement après une
    // lecture ratée, jamais pendant la première ; sans état lu, l'absence de marque ne prouve rien.
    if (!m_sessionsLues || attente->connues() || !attente->tentee()) {
        return {};
    }
    return QStringLiteral("Discussions en attente : état inconnu (le tableau de bord n'a pas pu être interrogé) ; l'absence de "
                          "la marque « En attente d'une réponse » ne veut rien dire.");
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

// --- Gestes et informations de la session ------------------------------------------------------

void DiscussionViewModel::reinitialiserOptionsSession()
{
    ++m_generationModeles;
    m_infosSession = {};
    m_modelesSession->clear();
    m_modelesCharges = false;
    m_chargementModeles = false;
    m_erreurModeles.clear();
    annulerChoixModele();
    if (gesteEnCours()) terminerGeste(QString());
    else effacerGeste();
    emit infosSessionChange();
}

void DiscussionViewModel::mettreAJourInfos(const QJsonObject &info)
{
    QJsonObject rendues;
    for (const char *champ : {"model", "provider", "profile_name", "reasoning_effort", "reasoning_effort_wire"}) {
        const QString cle = QString::fromLatin1(champ);
        if (info.value(cle).isString()) rendues.insert(cle, info.value(cle));
    }
    QJsonObject usage;
    const QJsonObject source = info.value(QStringLiteral("usage")).toObject();
    for (const char *champ : {"input", "output", "reasoning", "prompt", "completion", "total", "calls", "compressions",
                             "context_used", "context_max", "context_percent", "cost_usd"}) {
        const QString cle = QString::fromLatin1(champ);
        if (source.value(cle).isDouble() && source.value(cle).toDouble() >= 0) usage.insert(cle, source.value(cle));
    }
    for (const char *champ : {"context_source", "cost_status"}) {
        const QString cle = QString::fromLatin1(champ);
        if (source.value(cle).isString()) usage.insert(cle, source.value(cle));
    }
    if (source.value(QStringLiteral("context_estimated")).isBool())
        usage.insert(QStringLiteral("context_estimated"), source.value(QStringLiteral("context_estimated")));
    if (!usage.isEmpty()) rendues.insert(QStringLiteral("usage"), usage);
    if (rendues == m_infosSession) return;
    m_infosSession = rendues;
    emit infosSessionChange();
}

bool DiscussionViewModel::sessionModifiable()
{
    if (gesteEnCours()) return false;
    if (m_ouverture || m_vivante.isEmpty()) {
        echouerGeste(QStringLiteral("Ouvrez une discussion avant cette action."));
        return false;
    }
    if (!passerellePrete()) {
        echouerGeste(QStringLiteral("Passerelle de Hermes indisponible : cette action n'a pas été envoyée."));
        return false;
    }
    return true;
}

void DiscussionViewModel::renommer(const QString &titre)
{
    if (!sessionModifiable()) return;
    const QString choisi = titre.trimmed();
    if (choisi.isEmpty()) {
        echouerGeste(QStringLiteral("Le titre ne peut pas être vide."));
        return;
    }
    debuterGeste();
    const quint64 generation = m_generation;
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.title"),
        QJsonObject{{QStringLiteral("session_id"), m_vivante}, {QStringLiteral("title"), choisi}});
    connect(appel, &AppelRpc::reussi, this, [this, generation](const QJsonValue &valeur) {
        if (generation != m_generation) return;
        const QJsonObject resultat = valeur.toObject();
        const QString titreRendu = chaine(resultat.value(QStringLiteral("title")));
        if (titreRendu.trimmed().isEmpty()) {
            echouerGeste(QStringLiteral("Réponse de Hermes illisible : le nouveau titre n'est pas confirmé."));
            return;
        }
        m_titre = titreRendu;
        for (qsizetype i = 0; i < m_lignes.size(); ++i) {
            QJsonObject ligne = m_lignes.at(i).toObject();
            if (ligne.value(QStringLiteral("id")).toString() == m_stockee) {
                ligne.insert(QStringLiteral("titre"), titreRendu);
                m_lignes.replace(i, ligne);
            }
        }
        appliquerAttente();
        emit sessionChange();
        const bool enAttente = resultat.value(QStringLiteral("pending")).toBool();
        terminerGeste(enAttente ? QStringLiteral("Titre accepté par Hermes, en attente de son enregistrement.")
                               : QStringLiteral("Discussion renommée."), enAttente);
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation == m_generation) echecRpc(QStringLiteral("session.title"), erreur);
    });
}

void DiscussionViewModel::dupliquer()
{
    if (!sessionModifiable()) return;
    if (m_stockee.isEmpty()) {
        echouerGeste(QStringLiteral("Cette discussion n'a pas encore d'identifiant enregistré."));
        return;
    }
    debuterGeste();
    const quint64 generation = m_generation;
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.branch_stored"),
        QJsonObject{{QStringLiteral("parent_session_id"), m_stockee}});
    connect(appel, &AppelRpc::reussi, this, [this, generation](const QJsonValue &valeur) {
        if (generation != m_generation) return;
        const QJsonObject resultat = valeur.toObject();
        const QString stockee = chaine(resultat.value(QStringLiteral("stored_session_id")));
        if (stockee.isEmpty() || chaine(resultat.value(QStringLiteral("session_id"))).isEmpty()) {
            echouerGeste(QStringLiteral("Réponse de Hermes illisible : la copie n'est pas identifiée."));
            return;
        }
        // branch_stored omet le transcript : seule sa reprise peut rendre l'historique copié.
        ouvrir(stockee);
        actualiserSessions();
        terminerGeste(QStringLiteral("Copie créée par Hermes ; ouverture de son historique."));
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation == m_generation) echecRpc(QStringLiteral("session.branch_stored"), erreur);
    });
}

void DiscussionViewModel::preparerConsigne(const QString &texte)
{
    if (texte.trimmed().isEmpty()) return;
    const auto annoncer = [this](const QString &message, bool alerte = false) {
        // Préparer un brouillon ne termine pas une mutation indépendante déjà en vol.
        if (gesteEnCours()) {
            m_avis = message;
            emit tourChange();
        } else terminerGeste(message, alerte);
    };
    if (!m_vivante.isEmpty() && !m_ouverture) {
        const QString existant = brouillon();
        setBrouillon(existant.isEmpty() ? texte : existant + QStringLiteral("\n\n") + texte);
        annoncer(QStringLiteral("Consigne ajoutée au brouillon. Relisez-la avant de l'envoyer."));
        return;
    }
    m_consigneEnAttente += (m_consigneEnAttente.isEmpty() ? QString() : QStringLiteral("\n\n")) + texte;
    emit brouillonChange();
    if (m_ouverture) {
        m_generationConsigne = m_generation;
        annoncer(QStringLiteral("Consigne conservée ; elle sera ajoutée après l'ouverture de la discussion."));
    } else if (passerellePrete()) {
        nouvelle();
        annoncer(QStringLiteral("Consigne conservée pour la nouvelle discussion. Aucun message envoyé."));
    } else {
        annoncer(QStringLiteral("Consigne conservée en mémoire. Reconnectez Hermes puis ouvrez une nouvelle discussion pour la retrouver."), true);
    }
}

void DiscussionViewModel::actualiserModeles()
{
    const quint64 lecture = ++m_generationModeles;
    const quint64 generation = m_generation;
    if (m_vivante.isEmpty() || m_ouverture || !passerellePrete()) {
        m_chargementModeles = false;
        m_erreurModeles = QStringLiteral("Ouvrez une discussion connectée pour lire ses modèles disponibles.");
        emit modelesChange();
        return;
    }
    m_chargementModeles = true;
    m_erreurModeles.clear();
    emit modelesChange();
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("model.options"),
        QJsonObject{{QStringLiteral("session_id"), m_vivante}, {QStringLiteral("include_unconfigured"), false}});
    connect(appel, &AppelRpc::reussi, this, [this, generation, lecture](const QJsonValue &valeur) {
        if (generation != m_generation || lecture != m_generationModeles) return;
        m_chargementModeles = false;
        const QJsonValue fournisseurs = valeur.toObject().value(QStringLiteral("providers"));
        if (!fournisseurs.isArray()) {
            m_erreurModeles = QStringLiteral("Réponse de Hermes illisible : aucun inventaire de modèles.");
            emit modelesChange();
            return;
        }
        QJsonArray lignes;
        for (const QJsonValue &element : fournisseurs.toArray()) {
            const QJsonObject fournisseur = element.toObject();
            const QString slug = chaine(fournisseur.value(QStringLiteral("slug")));
            if (slug.isEmpty() || fournisseur.value(QStringLiteral("authenticated")) == QJsonValue(false)) continue;
            const QJsonArray indisponibles = fournisseur.value(QStringLiteral("unavailable_models")).toArray();
            for (const QJsonValue &modele : fournisseur.value(QStringLiteral("models")).toArray()) {
                if (!modele.isString() || modele.toString().isEmpty() || indisponibles.contains(modele)) continue;
                const QString nom = chaine(fournisseur.value(QStringLiteral("name")));
                lignes.append(QJsonObject{{QStringLiteral("fournisseur"), slug}, {QStringLiteral("modele"), modele},
                    {QStringLiteral("libelle"), QStringLiteral("%1 · %2").arg(nom.isEmpty() ? slug : nom, modele.toString())},
                    {QStringLiteral("avertissement"), chaine(fournisseur.value(QStringLiteral("warning")))}});
            }
        }
        m_modelesSession->setItems(lignes);
        m_modelesCharges = true;
        m_erreurModeles.clear();
        emit modelesChange();
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation, lecture](const ErreurRpc &erreur) {
        if (generation != m_generation || lecture != m_generationModeles) return;
        m_chargementModeles = false;
        m_erreurModeles = erreur.locale ? erreur.message
            : QStringLiteral("Hermes a refusé l'inventaire : %1 (code %2)").arg(erreur.message).arg(erreur.code);
        emit modelesChange();
    });
}

void DiscussionViewModel::annulerChoixModele()
{
    m_confirmationModele.clear();
    m_fournisseurAConfirmer.clear();
    m_modeleAConfirmer.clear();
    emit modelesChange();
}

void DiscussionViewModel::choisirModele(const QString &fournisseur, const QString &modele)
{
    if (!sessionModifiable()) return;
    bool offert = false;
    for (int i = 0; i < m_modelesSession->count(); ++i) {
        const QJsonObject ligne = m_modelesSession->itemAt(i);
        if (ligne.value(QStringLiteral("fournisseur")).toString() == fournisseur
            && ligne.value(QStringLiteral("modele")).toString() == modele) offert = true;
    }
    // Le parseur Hermes sépare sur les espaces et accepte des flags : aucun identifiant ne
    // doit introduire --global/--once ni changer le fournisseur, même depuis un catalogue malformé.
    static const QRegularExpression jeton(QStringLiteral("^[^\\s\\x00-\\x1f]+$"));
    const auto sur = [](const QString &valeur) {
        return jeton.match(valeur).hasMatch() && !valeur.startsWith(QLatin1Char('-'))
            && !(valeur.front().unicode() >= 0x2012 && valeur.front().unicode() <= 0x2015);
    };
    if (!offert || !sur(fournisseur) || !sur(modele)) {
        echouerGeste(QStringLiteral("Choisissez un modèle proposé par l'inventaire de cette discussion."));
        return;
    }
    annulerChoixModele();
    appliquerModele(fournisseur, modele, false);
}

void DiscussionViewModel::confirmerModele()
{
    if (m_confirmationModele.isEmpty() || !sessionModifiable()) return;
    const QString fournisseur = m_fournisseurAConfirmer;
    const QString modele = m_modeleAConfirmer;
    annulerChoixModele();
    appliquerModele(fournisseur, modele, true);
}

void DiscussionViewModel::appliquerModele(const QString &fournisseur, const QString &modele, bool confirme)
{
    debuterGeste();
    const quint64 generation = m_generation;
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("config.set"), QJsonObject{
        {QStringLiteral("session_id"), m_vivante}, {QStringLiteral("key"), QStringLiteral("model")},
        {QStringLiteral("value"), QStringLiteral("%1 --provider %2 --session").arg(modele, fournisseur)},
        {QStringLiteral("confirm_expensive_model"), confirme}});
    connect(appel, &AppelRpc::reussi, this, [this, generation, fournisseur, modele](const QJsonValue &valeur) {
        if (generation != m_generation) return;
        const QJsonObject resultat = valeur.toObject();
        if (resultat.value(QStringLiteral("key")) != QJsonValue(QStringLiteral("model"))
            || !resultat.value(QStringLiteral("value")).isString()) {
            echouerGeste(QStringLiteral("Réponse de Hermes illisible : le choix du modèle n'est pas confirmé."));
            return;
        }
        if (resultat.value(QStringLiteral("confirm_required")).toBool()) {
            m_confirmationModele = chaine(resultat.value(QStringLiteral("confirm_message")));
            if (m_confirmationModele.isEmpty()) m_confirmationModele = chaine(resultat.value(QStringLiteral("warning")));
            if (m_confirmationModele.isEmpty()) m_confirmationModele = QStringLiteral("Hermes demande de confirmer le coût de ce modèle.");
            m_fournisseurAConfirmer = fournisseur;
            m_modeleAConfirmer = modele;
            terminerGeste(QStringLiteral("Choix en attente de votre confirmation ; le modèle n'a pas été changé."), true);
            emit modelesChange();
            return;
        }
        const bool differe = resultat.value(QStringLiteral("deferred")).toBool();
        QString message = differe ? QStringLiteral("Choix accepté par Hermes pour le prochain tour de cette discussion.")
                                  : QStringLiteral("Choix du modèle accepté par Hermes pour cette discussion.");
        const QString avertissement = chaine(resultat.value(QStringLiteral("warning")));
        if (!avertissement.isEmpty()) message += QStringLiteral(" ") + avertissement;
        terminerGeste(message, differe || !avertissement.isEmpty());
        // L'affichage du modèle actif vient uniquement de session.info, jamais du choix soumis.
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation == m_generation) echecRpc(QStringLiteral("config.set"), erreur);
    });
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
    reinitialiserOptionsSession();
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
    reinitialiserOptionsSession();
    m_generationConsigne = m_consigneEnAttente.isEmpty() ? 0 : generation;
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
    mettreAJourInfos(info);
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
    if (m_generationConsigne == m_generation && !m_consigneEnAttente.isEmpty()) {
        const QString consigne = m_consigneEnAttente;
        m_consigneEnAttente.clear();
        m_generationConsigne = 0;
        const QString existant = brouillon();
        setBrouillon(existant.isEmpty() ? consigne : existant + QStringLiteral("\n\n") + consigne);
    }
    majTour(enCours);
    emit sessionChange();
}

void DiscussionViewModel::quitter()
{
    ++m_generation;
    reinitialiserOptionsSession();
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
    const quint64 generation = m_generation;
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("prompt.submit"),
                                                     QJsonObject{{QStringLiteral("session_id"), vivante},
                                                                 {QStringLiteral("text"), texte}});
    connect(appel, &AppelRpc::reussi, this, [this, cle, generation](const QJsonValue &resultat) {
        if (generation != m_generation) return;
        const int index = ligneDeCle(cle);
        if (index >= 0) {
            QJsonObject ligne = m_transcription->itemAt(index);
            ligne.insert(QStringLiteral("statut"), QString());
            m_transcription->setItem(index, ligne);
        }
        terminerGeste(messageEnvoi(resultat.toObject().value(QStringLiteral("status"))));
    });
    connect(appel, &AppelRpc::echoue, this, [this, cle, generation](const ErreurRpc &erreur) {
        if (generation != m_generation) return;
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
    const quint64 generation = m_generation;
    AppelRpc *appel = m_passerelle->canal()->requete(QStringLiteral("session.interrupt"),
                                                     QJsonObject{{QStringLiteral("session_id"), m_vivante}});
    connect(appel, &AppelRpc::reussi, this, [this, generation](const QJsonValue &) {
        if (generation != m_generation) return;
        terminerGeste(QStringLiteral("Arrêt demandé à Hermes."));
    });
    connect(appel, &AppelRpc::echoue, this, [this, generation](const ErreurRpc &erreur) {
        if (generation == m_generation) echecRpc(QStringLiteral("session.interrupt"), erreur);
    });
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
    } else if (type == QLatin1String("session.info")) {
        mettreAJourInfos(payload);
        if (payload.value(QStringLiteral("title")).isString()) {
            m_titre = payload.value(QStringLiteral("title")).toString();
            emit sessionChange();
        }
    } else if (type == QLatin1String("request.cancel")) {
        // DemandesAgent prend en charge le retrait.
    } else {
        ++m_ignores; // événement hors du sous-ensemble traité : compté, jamais deviné
        emit tourChange();
    }
}

} // namespace acp
