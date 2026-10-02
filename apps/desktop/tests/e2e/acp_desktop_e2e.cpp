// Pilote du bout en bout LOCAL de la station (cahier P8 § 10). Jamais installé, jamais lancé
// par CTest ni en CI : seul apps/desktop/tests/e2e/e2e_desktop_windows.py le lance, contre la
// pile locale (vrai Authelia, Hermes de test, bord TLS factice).
//
// C'est la VRAIE station (acp::Application, ses services, ses ViewModels et ses pages QML),
// avec quatre injections d'essai passées en arguments, jamais en réglages du produit :
//   --coffre   préfixe des entrées du coffre Windows (AcpDesktopE2E-<uuid>), pour ne jamais
//              toucher l'entrée réelle du poste ;
//   --portee   portée QSettings (HKCU\Software\<portée>) jetable ;
//   --mandataire  mandataire HTTP CONNECT local du script (seuls les deux noms de la pile y
//              mènent) : la station n'a aucun autre moyen de joindre « hermes-acp.test » ;
//   --autorite autorité de test du bord, ajoutée aux autorités de confiance du processus.
//
// Protocole : une commande JSON par ligne sur l'entrée standard ; chaque réponse ou événement
// est une ligne « ACPE2E {json} » sur la sortie standard. Aucune réponse ne contient de jeton :
// seulement des empreintes (16 premiers caractères hexadécimaux du SHA-256). L'URL
// d'autorisation (défi PKCE et état, jamais le vérificateur) est émise une fois, pour que le
// script l'ouvre dans Chromium à la place du navigateur du système.

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "app/Application.h"
#include "auth/NativeAuthFlow.h"
#include "auth/SessionHermes.h"
#include "diagnostics/Redaction.h"
#include "events/EventStreamService.h"
#include "gateway/GatewayClient.h"
#include "models/JsonListModel.h"
#include "storage/CredentialVault.h"
#include "storage/JetonsCoffre.h"
#include "storage/SettingsStore.h"
#include "viewmodels/DiscussionViewModel.h"
#include "viewmodels/ProjetsViewModel.h"
#include "viewmodels/QuestionsViewModel.h"
#include "viewmodels/SauvegardeViewModel.h"
#include "viewmodels/ShellViewModel.h"

#include <QCommandLineParser>
#include <QCryptographicHash>
#include <QDeadlineTimer>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QFont>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMutex>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSettings>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QTimer>

#include <atomic>
#include <cstdio>
#include <deque>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

using namespace acp;

namespace {

// --- Journal de la station : expurgé comme celui du produit, et gardé pour l'hygiène -------

QMutex g_verrouJournal;
QStringList g_journal;

void journaliser(QtMsgType type, const QMessageLogContext &, const QString &message)
{
    const QString sur = redactSecrets(message);
    const char *niveau = type == QtWarningMsg ? "AVERTISSEMENT" : type == QtCriticalMsg ? "CRITIQUE"
                       : type == QtFatalMsg   ? "FATAL"
                                              : "INFO";
    {
        QMutexLocker verrou(&g_verrouJournal);
        g_journal.append(sur);
    }
    std::fprintf(stderr, "%s : %s\n", niveau, sur.toUtf8().constData());
    std::fflush(stderr);
}

void emettre(const QJsonObject &objet)
{
    const QByteArray ligne = QByteArrayLiteral("ACPE2E ") + QJsonDocument(objet).toJson(QJsonDocument::Compact)
        + QByteArrayLiteral("\n");
    std::fwrite(ligne.constData(), 1, static_cast<size_t>(ligne.size()), stdout);
    std::fflush(stdout);
}

QString empreinte(const QByteArray &secret)
{
    return QString::fromLatin1(QCryptographicHash::hash(secret, QCryptographicHash::Sha256).toHex().left(16));
}

void patienter(int millisecondes)
{
    QEventLoop boucle;
    QTimer::singleShot(millisecondes, &boucle, &QEventLoop::quit);
    boucle.exec();
}

bool attendre(const std::function<bool()> &condition, int millisecondes)
{
    const QDeadlineTimer limite(millisecondes);
    while (!condition()) {
        if (limite.hasExpired()) {
            return false;
        }
        patienter(25);
    }
    return true;
}

struct Lecture
{
    bool ok = false;
    int statut = 0;
    QJsonObject json;
    QString erreur;
};

Lecture lireSync(ApiCall *appel, int millisecondes = 30000)
{
    Lecture lecture;
    bool fini = false;
    QObject::connect(appel, &ApiCall::succeeded, appel, [&](const ApiResponse &reponse) {
        lecture.ok = true;
        lecture.statut = reponse.httpStatus;
        lecture.json = reponse.json.object();
        fini = true;
    });
    QObject::connect(appel, &ApiCall::failed, appel, [&](const ApiError &erreur) {
        lecture.statut = erreur.httpStatus();
        lecture.erreur = redactSecrets(erreur.message());
        fini = true;
    });
    if (!attendre([&] { return fini; }, millisecondes)) {
        lecture.erreur = QStringLiteral("délai dépassé");
    }
    return lecture;
}

// --- Pilote ----------------------------------------------------------------------------------

class Pilote : public QObject
{
public:
    Pilote(Application &application, const QString &nomCoffre, const QString &captures)
        : m_application(application)
        , m_coffre(makeCredentialVault(nomCoffre))
        , m_captures(captures)
    {
        m_client = application.findChild<ApiClient *>();
        m_session = application.findChild<SessionHermes *>();
        m_shell = application.findChild<ShellViewModel *>();
        m_flux = application.findChild<EventStreamService *>();
        m_passerelle = application.findChild<GatewayClient *>();
        m_projets = application.findChild<ProjetsViewModel *>();
        m_questions = application.findChild<QuestionsViewModel *>();
        m_discussion = application.findChild<DiscussionViewModel *>();
        m_sauvegarde = application.findChild<SauvegardeViewModel *>();
        m_reglages = application.findChild<SettingsStore *>();
        m_greffon = std::make_unique<ClientGreffonPoste>(m_client);
        m_chrono.start();

        // Le navigateur du système est remplacé par le script : l'URL lui est émise, une fois.
        m_session->flux()->setOuvreurNavigateur([](const QUrl &url) {
            emettre(QJsonObject{{QStringLiteral("evenement"), QStringLiteral("autorisation")},
                                {QStringLiteral("url"), url.toString(QUrl::FullyEncoded)}});
            return true;
        });
        connect(m_flux, &EventStreamService::tableauChange, this, [this](const QString &tableau) {
            m_tableauxVus.append({tableau, m_chrono.elapsed()});
        });
        connect(m_projets, &ProjetsViewModel::detailChange, this,
                [this] { m_detailsLus.append(m_chrono.elapsed()); });

        m_lecteur = std::thread([this] {
            std::string ligne;
            while (std::getline(std::cin, ligne)) {
                std::lock_guard<std::mutex> verrou(m_verrou);
                m_commandes.push_back(QString::fromStdString(ligne));
            }
            m_finEntree = true;
        });
        m_lecteur.detach();
        auto *pompe = new QTimer(this);
        connect(pompe, &QTimer::timeout, this, &Pilote::pomper);
        pompe->start(50);
        emettre(QJsonObject{{QStringLiteral("evenement"), QStringLiteral("pret")},
                            {QStringLiteral("coffre"), m_coffre->backendName()},
                            {QStringLiteral("preferences"), m_reglages->location()}});
    }

private:
    void pomper()
    {
        if (m_occupe) {
            return;
        }
        QString ligne;
        {
            std::lock_guard<std::mutex> verrou(m_verrou);
            if (m_commandes.empty()) {
                if (m_finEntree) {
                    QCoreApplication::exit(4);
                }
                return;
            }
            ligne = m_commandes.front();
            m_commandes.pop_front();
        }
        const QJsonObject commande = QJsonDocument::fromJson(ligne.toUtf8()).object();
        const QString nom = commande.value(QStringLiteral("commande")).toString();
        m_occupe = true;
        QJsonObject reponse;
        try {
            reponse = traiter(nom, commande);
        } catch (const std::exception &erreur) {
            reponse = {{QStringLiteral("ok"), false}, {QStringLiteral("erreur"), QString::fromUtf8(erreur.what())}};
        }
        reponse.insert(QStringLiteral("commande"), nom);
        reponse.insert(QStringLiteral("ms"), static_cast<double>(m_chrono.elapsed()));
        emettre(reponse);
        m_occupe = false;
        if (nom == QLatin1String("quitter")) {
            QCoreApplication::exit(0);
        }
    }

    QJsonObject traiter(const QString &nom, const QJsonObject &c)
    {
        if (nom == QLatin1String("configurer")) return configurer(c);
        if (nom == QLatin1String("connecter")) return connecter();
        if (nom == QLatin1String("attendre_session")) return attendreSession(c);
        if (nom == QLatin1String("rafraichir")) return rafraichir();
        if (nom == QLatin1String("discussion")) return discuter(c);
        if (nom == QLatin1String("projet")) return lancerProjet(c);
        if (nom == QLatin1String("marquer_veille")) return marquerVeille();
        if (nom == QLatin1String("attendre_veille")) return attendreVeille(c);
        if (nom == QLatin1String("questions_attendre")) return attendreQuestion(c);
        if (nom == QLatin1String("repondre")) return repondre(c);
        if (nom == QLatin1String("sauvegarde")) return sauvegarder(c);
        if (nom == QLatin1String("capture")) return capturerCommande(c);
        if (nom == QLatin1String("lire")) return lireRoute(c);
        if (nom == QLatin1String("deconnecter")) return deconnecter();
        if (nom == QLatin1String("hygiene")) return hygiene(c);
        if (nom == QLatin1String("quitter")) return {{QStringLiteral("ok"), true}};
        return {{QStringLiteral("ok"), false}, {QStringLiteral("erreur"), QStringLiteral("commande inconnue")}};
    }

    // --- Session ---------------------------------------------------------------------------

    QUrl serveur() const { return m_client->baseUrl(); }

    std::optional<QByteArray> jetonAuCoffre()
    {
        JetonsCoffre jetons(m_coffre.get());
        EntreeJetons entree;
        bool introuvable = false;
        const VaultResult resultat = jetons.relire(serveur(), QString::fromLatin1(NativeAuthFlow::kFournisseur), entree,
                                                   &introuvable);
        if (!resultat.ok || introuvable) {
            return std::nullopt;
        }
        const QByteArray jeton = entree.jeton;
        entree.effacer();
        noterSecret(jeton);
        return jeton;
    }

    void noterSecret(const QByteArray &secret)
    {
        if (!secret.isEmpty() && !m_secrets.contains(secret)) {
            m_secrets.append(secret);
        }
    }

    QJsonObject etatSession() const
    {
        return {{QStringLiteral("etat"), m_session->libelleEtat()},
                {QStringLiteral("connectee"), m_session->estConnectee()},
                {QStringLiteral("erreur"), redactSecrets(m_session->derniereErreur())},
                {QStringLiteral("identite"), m_session->identifiant()},
                {QStringLiteral("nom"), m_session->nomAffiche()},
                {QStringLiteral("fournisseur"), m_session->fournisseur()},
                {QStringLiteral("entree_au_coffre"), m_session->entreeAuCoffre()},
                {QStringLiteral("avis_coffre"), m_session->avisCoffre()}};
    }

    QJsonObject configurer(const QJsonObject &c)
    {
        const QString refus = m_shell->applyServerUrl(c.value(QStringLiteral("serveur")).toString(), false);
        if (!refus.isEmpty()) {
            return {{QStringLiteral("ok"), false}, {QStringLiteral("erreur"), refus}};
        }
        m_session->setMemoriser(c.value(QStringLiteral("memoriser")).toBool(true));
        return {{QStringLiteral("ok"), true}, {QStringLiteral("serveur"), serveur().toString()},
                {QStringLiteral("memoriser"), m_session->memoriser()}};
    }

    QJsonObject connecter()
    {
        m_session->seConnecter();
        const bool fini = attendre(
            [this] {
                const auto etat = m_session->etat();
                return etat == SessionStatus::Connectee || etat == SessionStatus::Refusee
                    || etat == SessionStatus::Deconnectee || etat == SessionStatus::Expiree;
            },
            600000);
        QJsonObject reponse = etatSession();
        reponse.insert(QStringLiteral("ok"), fini && m_session->estConnectee());
        if (const auto jeton = jetonAuCoffre()) {
            reponse.insert(QStringLiteral("empreinte_rt"), empreinte(*jeton));
        }
        return reponse;
    }

    QJsonObject attendreSession(const QJsonObject &c)
    {
        const bool ok = attendre([this] { return m_session->estConnectee(); },
                                 c.value(QStringLiteral("delai_ms")).toInt(60000));
        QJsonObject reponse = etatSession();
        reponse.insert(QStringLiteral("ok"), ok);
        if (const auto jeton = jetonAuCoffre()) {
            reponse.insert(QStringLiteral("empreinte_rt"), empreinte(*jeton));
        }
        return reponse;
    }

    QJsonObject rafraichir()
    {
        const auto avant = jetonAuCoffre();
        bool renouvele = false;
        const auto lien = connect(m_session, &SessionHermes::jetonsRenouveles, this, [&renouvele] { renouvele = true; });
        m_session->rafraichir();
        const bool ok = attendre([&renouvele] { return renouvele; }, 60000);
        disconnect(lien);
        // L'écriture au coffre précède le signal : relu juste après, c'est déjà le nouveau.
        const auto apres = jetonAuCoffre();
        QJsonObject reponse = etatSession();
        reponse.insert(QStringLiteral("ok"), ok && m_session->estConnectee());
        reponse.insert(QStringLiteral("empreinte_avant"), avant ? empreinte(*avant) : QString());
        reponse.insert(QStringLiteral("empreinte_rt"), apres ? empreinte(*apres) : QString());
        reponse.insert(QStringLiteral("tourne"), avant && apres && *avant != *apres);
        return reponse;
    }

    QJsonObject deconnecter()
    {
        std::optional<QByteArray> ancien = jetonAuCoffre();
        m_session->seDeconnecter();
        attendre([this] { return !m_session->bilanDeconnexion().isEmpty() && !m_session->estConnectee(); }, 30000);
        QJsonObject reponse = etatSession();
        reponse.insert(QStringLiteral("ok"), !m_session->estConnectee());
        reponse.insert(QStringLiteral("bilan"), m_session->bilanDeconnexion());
        reponse.insert(QStringLiteral("entree_au_coffre_apres"), m_coffre->contains(JetonsCoffre::cleDe(serveur())));
        // Rejeu de l'ancien jeton APRÈS la déconnexion : résultat consigné tel quel.
        if (ancien) {
            QNetworkAccessManager reseau;
            reseau.setProxy(m_client->proxyDesSockets());
            QNetworkRequest requete(serveur().resolved(QUrl(QStringLiteral("/auth/native/refresh"))));
            requete.setHeader(QNetworkRequest::ContentTypeHeader, QByteArrayLiteral("application/json"));
            const QByteArray corps = QJsonDocument(QJsonObject{
                {QStringLiteral("refresh_token"), QString::fromLatin1(*ancien)},
                {QStringLiteral("provider"), QString::fromLatin1(NativeAuthFlow::kFournisseur)}}).toJson(QJsonDocument::Compact);
            QNetworkReply *retour = reseau.post(requete, corps);
            attendre([retour] { return retour->isFinished(); }, 60000);
            reponse.insert(QStringLiteral("rejeu_apres_deconnexion_statut"),
                           retour->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt());
            reponse.insert(QStringLiteral("rejeu_apres_deconnexion_corps"),
                           redactSecrets(QString::fromUtf8(retour->readAll().left(300))));
            retour->deleteLater();
            CredentialVault::wipe(*ancien);
        }
        return reponse;
    }

    // --- Discussion (JSON-RPC sur /api/ws) ------------------------------------------------

    QJsonObject discuter(const QJsonObject &c)
    {
        QJsonObject reponse;
        const bool prete = attendre([this] { return m_passerelle->etat() == GatewayClient::Etat::Pret; }, 90000);
        reponse.insert(QStringLiteral("passerelle"), m_passerelle->libelleEtat());
        reponse.insert(QStringLiteral("sous_protocole"), m_passerelle->sousProtocoleRetenu());
        if (!prete) {
            reponse.insert(QStringLiteral("ok"), false);
            reponse.insert(QStringLiteral("erreur"), m_passerelle->raison());
            return reponse;
        }
        m_discussion->setPageVisible(true);
        m_discussion->nouvelle();
        const bool ouverte = attendre([this] { return !m_discussion->sessionOuverte().isEmpty()
                                                      || !m_discussion->erreurSession().isEmpty(); }, 60000);
        reponse.insert(QStringLiteral("session"), m_discussion->sessionOuverte());
        if (!ouverte || m_discussion->sessionOuverte().isEmpty()) {
            reponse.insert(QStringLiteral("ok"), false);
            reponse.insert(QStringLiteral("erreur"), m_discussion->erreurSession());
            return reponse;
        }
        const bool envoye = m_discussion->envoyer(c.value(QStringLiteral("texte")).toString());
        const auto reponseRendue = [this]() -> QString {
            JsonListModel *lignes = m_discussion->transcription();
            for (int rang = lignes->count() - 1; rang >= 0; --rang) {
                const QJsonObject ligne = lignes->itemAt(rang);
                if (ligne.value(QStringLiteral("role")).toString() == QLatin1String("assistant")
                    && !ligne.value(QStringLiteral("enCours")).toBool()
                    && !ligne.value(QStringLiteral("texte")).toString().isEmpty()) {
                    return ligne.value(QStringLiteral("texte")).toString();
                }
            }
            return {};
        };
        const bool rendu = envoye && attendre([&] { return !m_discussion->tourEnCours() && !reponseRendue().isEmpty(); },
                                              120000);
        reponse.insert(QStringLiteral("ok"), rendu);
        reponse.insert(QStringLiteral("reponse"), reponseRendue());
        reponse.insert(QStringLiteral("erreur"), m_discussion->erreurSession());
        reponse.insert(QStringLiteral("evenements_ignores"), m_discussion->evenementsIgnores());
        reponse.insert(QStringLiteral("lignes"), m_discussion->transcription()->count());
        capturer(QStringLiteral("DiscussionPage"), QStringLiteral("discussion"));
        m_discussion->setPageVisible(false);
        return reponse;
    }

    // --- Projets, veille, questions --------------------------------------------------------

    QJsonObject lancerProjet(const QJsonObject &c)
    {
        m_projets->setPageVisible(true);
        m_projets->afficherNouveau();
        const auto formulaire = [this](const QString &cle) { return m_projets->formulaire().value(cle); };
        if (!attendre([&] { return formulaire(QStringLiteral("pret")).toBool(); }, 60000)) {
            return {{QStringLiteral("ok"), false}, {QStringLiteral("erreur"), QStringLiteral("formulaire jamais prêt")}};
        }
        const QString depot = c.value(QStringLiteral("depot")).toString();
        if (!depot.isEmpty()) {
            if (!attendre([&] { return formulaire(QStringLiteral("depots")).toStringList().contains(depot); }, 60000)) {
                return {{QStringLiteral("ok"), false},
                        {QStringLiteral("erreur"), QStringLiteral("dépôt absent du formulaire")},
                        {QStringLiteral("depots"), QJsonArray::fromStringList(formulaire(QStringLiteral("depots")).toStringList())}};
            }
            m_projets->choisirDepot(depot);
            m_projets->choisirVoie(c.value(QStringLiteral("voie")).toString());
        }
        capturer(QStringLiteral("ProjectsPage"), QStringLiteral("projets-nouveau"));
        m_projets->setPageVisible(true);
        m_projets->lancer(c.value(QStringLiteral("titre")).toString(), c.value(QStringLiteral("objectif")).toString(),
                          c.value(QStringLiteral("profil")).toString(), c.value(QStringLiteral("reponses")).toString(),
                          QString());
        attendre([this] { return !m_projets->gesteEnCours(); }, 60000);
        QJsonObject reponse{{QStringLiteral("message"), m_projets->messageGeste()},
                            {QStringLiteral("erreur"), m_projets->erreurGeste()},
                            {QStringLiteral("projet"), m_projets->projetOuvert()}};
        const QString identifiant = m_projets->projetOuvert();
        if (identifiant.isEmpty() || !m_projets->erreurGeste().isEmpty()) {
            reponse.insert(QStringLiteral("ok"), false);
            return reponse;
        }
        attendre([this] { return m_projets->detailLu(); }, 60000);
        // Relecture INDÉPENDANTE par l'API (porteur de la station), hors du ViewModel.
        const Lecture projet = lireSync(m_greffon->projet(identifiant));
        const QJsonObject corps = projet.json.value(QStringLiteral("projet")).isObject()
            ? projet.json.value(QStringLiteral("projet")).toObject()
            : projet.json;
        reponse.insert(QStringLiteral("tableau"), corps.value(QStringLiteral("tableau")));
        reponse.insert(QStringLiteral("etat"), corps.value(QStringLiteral("etat")));
        reponse.insert(QStringLiteral("reponses"), corps.value(QStringLiteral("reponses")));
        reponse.insert(QStringLiteral("depot"), corps.value(QStringLiteral("depot")));
        reponse.insert(QStringLiteral("origine"), corps.value(QStringLiteral("origine")));
        for (const QJsonValue &carte : corps.value(QStringLiteral("cartes")).toArray()) {
            if (carte.toObject().value(QStringLiteral("role")).toString() == QLatin1String("exploration")) {
                reponse.insert(QStringLiteral("exploration"), carte.toObject().value(QStringLiteral("carte")));
                reponse.insert(QStringLiteral("exploration_statut"), carte.toObject().value(QStringLiteral("statut")));
            }
        }
        reponse.insert(QStringLiteral("ok"), projet.ok);
        reponse.insert(QStringLiteral("veille"), m_projets->etatVeille());
        m_projetOuvert = identifiant;
        m_tableauOuvert = corps.value(QStringLiteral("tableau")).toString();
        return reponse;
    }

    QJsonObject marquerVeille()
    {
        m_projets->setPageVisible(true);
        if (m_projets->projetOuvert() != m_projetOuvert) {
            m_projets->ouvrirProjet(m_projetOuvert);
        }
        attendre([this] { return m_projets->detailLu(); }, 30000);
        m_marque = m_chrono.elapsed();
        return {{QStringLiteral("ok"), true}, {QStringLiteral("veille"), m_projets->etatVeille()},
                {QStringLiteral("marque_ms"), static_cast<double>(m_marque)}};
    }

    QJsonObject attendreVeille(const QJsonObject &c)
    {
        const qint64 debutAttente = m_chrono.elapsed();
        const auto tableauApres = [this]() -> qint64 {
            for (const auto &[tableau, instant] : m_tableauxVus) {
                if (tableau == m_tableauOuvert && instant >= m_marque) {
                    return instant;
                }
            }
            return -1;
        };
        const auto relectureApres = [&](qint64 depuis) -> qint64 {
            for (const qint64 instant : m_detailsLus) {
                if (depuis >= 0 && instant >= depuis) {
                    return instant;
                }
            }
            return -1;
        };
        const bool ok = attendre([&] { return relectureApres(tableauApres()) >= 0; },
                                 c.value(QStringLiteral("delai_ms")).toInt(10000));
        const qint64 tableau = tableauApres();
        const qint64 relecture = relectureApres(tableau);
        return {{QStringLiteral("ok"), ok},
                {QStringLiteral("veille"), m_projets->etatVeille()},
                {QStringLiteral("evenement_apres_marque_ms"), tableau < 0 ? -1.0 : static_cast<double>(tableau - m_marque)},
                {QStringLiteral("relecture_apres_marque_ms"), relecture < 0 ? -1.0 : static_cast<double>(relecture - m_marque)},
                {QStringLiteral("relecture_apres_attente_ms"),
                 relecture < 0 ? -1.0 : static_cast<double>(std::max<qint64>(0, relecture - debutAttente))}};
    }

    QJsonObject attendreQuestion(const QJsonObject &c)
    {
        const QString identifiant = c.value(QStringLiteral("question")).toString();
        m_questions->setPageVisible(true);
        const auto presente = [&]() -> QJsonObject {
            JsonListModel *liste = m_questions->questions();
            for (int rang = 0; rang < liste->count(); ++rang) {
                if (liste->itemAt(rang).value(QStringLiteral("id")).toString() == identifiant) {
                    return liste->itemAt(rang);
                }
            }
            return {};
        };
        QElapsedTimer chrono;
        chrono.start();
        const bool vue = attendre([&] {
            if (presente().isEmpty() && chrono.elapsed() > 2000) {
                m_questions->actualiser();
                chrono.restart();
            }
            return !presente().isEmpty();
        }, 90000);
        QJsonObject reponse{{QStringLiteral("ok"), vue}, {QStringLiteral("question"), presente()}};
        reponse.insert(QStringLiteral("capture"), capturer(QStringLiteral("QuestionsPage"), QStringLiteral("questions-avant")));
        m_questions->setPageVisible(true);
        return reponse;
    }

    QJsonObject repondre(const QJsonObject &c)
    {
        const QString question = c.value(QStringLiteral("question")).toString();
        m_questions->setPageVisible(true);
        m_questions->repondre(question, c.value(QStringLiteral("reponse")).toString());
        attendre([this] { return !m_questions->gesteEnCours(); }, 60000);
        QJsonObject reponse{{QStringLiteral("message"), m_questions->messageGeste()},
                            {QStringLiteral("erreur"), m_questions->erreurGeste()}};
        // Relecture indépendante : la question n'est plus ouverte, la carte est reprise.
        const Lecture questions = lireSync(m_greffon->questions());
        bool encoreOuverte = false;
        for (const QJsonValue &q : questions.json.value(QStringLiteral("questions")).toArray()) {
            if (q.toObject().value(QStringLiteral("id")).toString() == question) {
                encoreOuverte = true;
            }
        }
        reponse.insert(QStringLiteral("encore_ouverte"), encoreOuverte);
        reponse.insert(QStringLiteral("relecture_ok"), questions.ok);
        if (!m_projetOuvert.isEmpty()) {
            const Lecture projet = lireSync(m_greffon->projet(m_projetOuvert));
            const QJsonObject corps = projet.json.value(QStringLiteral("projet")).isObject()
                ? projet.json.value(QStringLiteral("projet")).toObject()
                : projet.json;
            for (const QJsonValue &carte : corps.value(QStringLiteral("cartes")).toArray()) {
                if (carte.toObject().value(QStringLiteral("role")).toString() == QLatin1String("exploration")) {
                    reponse.insert(QStringLiteral("exploration_statut"), carte.toObject().value(QStringLiteral("statut")));
                }
            }
        }
        reponse.insert(QStringLiteral("capture"), capturer(QStringLiteral("QuestionsPage"), QStringLiteral("questions-apres")));
        reponse.insert(QStringLiteral("ok"), m_questions->erreurGeste().isEmpty() && !encoreOuverte && questions.ok);
        return reponse;
    }

    // --- Sauvegarde ----------------------------------------------------------------------------

    QJsonObject sauvegarder(const QJsonObject &c)
    {
        const QString destination = c.value(QStringLiteral("destination")).toString();
        const QString archive = c.value(QStringLiteral("archive")).toString();
        m_sauvegarde->setPageVisible(true);
        m_sauvegarde->exporter(destination);
        attendre([this] {
            return m_sauvegarde->phase() == SauvegardeViewModel::Phase::Termine
                || m_sauvegarde->phase() == SauvegardeViewModel::Phase::Echec;
        }, 900000);
        const QVariantMap resultat = m_sauvegarde->resultat();
        QJsonObject reponse{
            {QStringLiteral("phase"), m_sauvegarde->etape()},
            {QStringLiteral("message"), m_sauvegarde->messageGeste()},
            {QStringLiteral("erreur"), m_sauvegarde->erreurGeste()},
            {QStringLiteral("journal"), m_sauvegarde->journal()},
            {QStringLiteral("taille_chiffre"), resultat.value(QStringLiteral("taille")).toString()},
            {QStringLiteral("taille_archive"), resultat.value(QStringLiteral("tailleArchive")).toString()},
            {QStringLiteral("empreinte_chiffre"), resultat.value(QStringLiteral("empreinte")).toString()},
            {QStringLiteral("suppression"), resultat.value(QStringLiteral("suppression")).toString()},
            {QStringLiteral("archive_restante"), resultat.value(QStringLiteral("archiveRestante")).toString()},
            {QStringLiteral("duree"), resultat.value(QStringLiteral("duree")).toString()},
        };
        reponse.insert(QStringLiteral("capture"), capturer(QStringLiteral("SauvegardePage"), QStringLiteral("sauvegarde")));
        const bool termine = m_sauvegarde->phase() == SauvegardeViewModel::Phase::Termine;
        bool conforme = false;
        if (termine) {
            const QByteArray attendue = m_sauvegarde->empreinteArchive();
            m_sauvegarde->effacerGeste();
            m_sauvegarde->dechiffrer(destination, archive);
            reponse.insert(QStringLiteral("dechiffrement"), m_sauvegarde->messageGeste().isEmpty()
                                                               ? m_sauvegarde->erreurGeste()
                                                               : QStringLiteral("Archive déchiffrée"));
            QFile zip(archive);
            if (zip.open(QIODevice::ReadOnly)) {
                QCryptographicHash hachage(QCryptographicHash::Sha256);
                hachage.addData(&zip);
                const QByteArray lue = hachage.result().toHex();
                conforme = lue == attendue;
                reponse.insert(QStringLiteral("sha256_archive"), QString::fromLatin1(lue));
                zip.seek(0);
                reponse.insert(QStringLiteral("zip_commence_par_PK"), zip.read(2) == QByteArrayLiteral("PK"));
                zip.close();
            }
            // L'archive en clair (données de la pile de test) ne reste pas sur le disque.
            reponse.insert(QStringLiteral("archive_claire_supprimee"), QFile::remove(archive));
        }
        reponse.insert(QStringLiteral("sha256_conforme"), conforme);
        reponse.insert(QStringLiteral("ok"), termine && conforme);
        m_sauvegarde->reinitialiser();
        return reponse;
    }

    // --- Lecture brute d'une route du greffon (forme servie, pour comparer les fixtures) -------

    QJsonObject lireRoute(const QJsonObject &c)
    {
        ApiRequest requete;
        requete.path = ClientGreffonPoste::chemin(c.value(QStringLiteral("chemin")).toString());
        const Lecture lecture = lireSync(m_client->send(requete));
        return {{QStringLiteral("ok"), lecture.ok}, {QStringLiteral("statut"), lecture.statut},
                {QStringLiteral("erreur"), lecture.erreur}, {QStringLiteral("corps"), lecture.json}};
    }

    // --- Captures hors écran des vraies pages ---------------------------------------------------

    QJsonObject capturerCommande(const QJsonObject &c)
    {
        const QString chemin = capturer(c.value(QStringLiteral("page")).toString(), c.value(QStringLiteral("nom")).toString());
        return {{QStringLiteral("ok"), !chemin.isEmpty()}, {QStringLiteral("capture"), chemin}};
    }

    QString capturer(const QString &page, const QString &nom)
    {
        if (m_captures.isEmpty()) {
            return {};
        }
        if (!m_moteur) {
            m_application.registerQmlTypes();
            m_moteur = std::make_unique<QQmlApplicationEngine>();
            // Fenêtre hôte construite comme App.qml (fond de la zone de travail, palette des
            // contrôles Basic, pont du thème) : la page y est posée comme dans l'application,
            // et non dans une fenêtre nue dont les contrôles Basic garderaient leurs couleurs
            // par défaut.
            QQmlComponent hote(m_moteur.get());
            hote.setData(QByteArrayLiteral("import QtQuick\nimport QtQuick.Controls.Basic\nimport Acp.Design\n"
                                           "import Acp.Theme\n"
                                           "ApplicationWindow { width: 1280; height: 860; visible: true;\n"
                                           "  color: Colors.surfaceCanvas; palette: NativePalette {}\n"
                                           "  ThemeBridge {} }\n"),
                         QUrl::fromLocalFile(QDir::temp().filePath(QStringLiteral("HoteCapture.qml"))));
            attendre([&hote] { return hote.status() != QQmlComponent::Loading; }, 10000);
            m_fenetre.reset(hote.isReady() ? qobject_cast<QQuickWindow *>(hote.create()) : nullptr);
            if (!m_fenetre) {
                qWarning("fenêtre des captures indisponible : %s", qPrintable(hote.errorString()));
                m_moteur.reset();
                return {};
            }
        }
        QQmlComponent composant(m_moteur.get());
        composant.loadFromModule(QStringLiteral("Acp.Pages"), page);
        attendre([&composant] { return composant.status() != QQmlComponent::Loading; }, 10000);
        if (!composant.isReady()) {
            qWarning("capture %s impossible : %s", qPrintable(page), qPrintable(composant.errorString()));
            return {};
        }
        std::unique_ptr<QObject> objet(composant.create());
        auto *element = qobject_cast<QQuickItem *>(objet.get());
        if (!element) {
            return {};
        }
        element->setParentItem(m_fenetre->contentItem());
        element->setSize(QSizeF(1280, 860));
        patienter(1500);
        QDir().mkpath(m_captures);
        const QString chemin = QDir(m_captures).filePath(QStringLiteral("%1-%2.png")
                                                              .arg(++m_numeroCapture, 2, 10, QLatin1Char('0'))
                                                              .arg(nom));
        const bool ecrite = m_fenetre->grabWindow().save(chemin);
        objet.reset();
        patienter(50);
        return ecrite ? chemin : QString();
    }

    // --- Hygiène --------------------------------------------------------------------------------

    QJsonObject hygiene(const QJsonObject &c)
    {
        m_reglages->flush();
        const SettingsStore::Controle controle = m_reglages->controler();
        int secretsDansPreferences = 0;
        QSettings portee;
        for (const QString &cle : portee.allKeys()) {
            const QByteArray valeur = portee.value(cle).toString().toUtf8();
            for (const QByteArray &secret : std::as_const(m_secrets)) {
                if (valeur.contains(secret)) {
                    ++secretsDansPreferences;
                }
            }
        }
        QStringList journal;
        {
            QMutexLocker verrou(&g_verrouJournal);
            journal = g_journal;
        }
        int secretsDansJournal = 0;
        for (const QString &ligne : std::as_const(journal)) {
            for (const QByteArray &secret : std::as_const(m_secrets)) {
                if (ligne.toUtf8().contains(secret)) {
                    ++secretsDansJournal;
                }
            }
        }
        const QString chemin = c.value(QStringLiteral("journal")).toString();
        if (!chemin.isEmpty()) {
            QFile fichier(chemin);
            if (fichier.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                fichier.write(journal.join(QLatin1Char('\n')).toUtf8());
            }
        }
        // Les jetons connus du pilote (lus au coffre de test) quittent sa mémoire.
        for (QByteArray &secret : m_secrets) {
            CredentialVault::wipe(secret);
        }
        const int connus = static_cast<int>(m_secrets.size());
        m_secrets.clear();
        return {{QStringLiteral("ok"), controle.conforme() && secretsDansPreferences == 0 && secretsDansJournal == 0},
                {QStringLiteral("cles"), controle.cles},
                {QStringLiteral("hors_liste"), QJsonArray::fromStringList(controle.horsListe)},
                {QStringLiteral("suspectes"), QJsonArray::fromStringList(controle.suspectes)},
                {QStringLiteral("jetons_connus"), connus},
                {QStringLiteral("secrets_dans_preferences"), secretsDansPreferences},
                {QStringLiteral("secrets_dans_journal"), secretsDansJournal},
                {QStringLiteral("lignes_journal"), static_cast<int>(journal.size())},
                {QStringLiteral("entree_au_coffre"), m_coffre->contains(JetonsCoffre::cleDe(serveur()))}};
    }

    Application &m_application;
    std::unique_ptr<CredentialVault> m_coffre;
    QString m_captures;
    ApiClient *m_client = nullptr;
    SessionHermes *m_session = nullptr;
    ShellViewModel *m_shell = nullptr;
    EventStreamService *m_flux = nullptr;
    GatewayClient *m_passerelle = nullptr;
    ProjetsViewModel *m_projets = nullptr;
    QuestionsViewModel *m_questions = nullptr;
    DiscussionViewModel *m_discussion = nullptr;
    SauvegardeViewModel *m_sauvegarde = nullptr;
    SettingsStore *m_reglages = nullptr;
    std::unique_ptr<ClientGreffonPoste> m_greffon;
    std::unique_ptr<QQmlApplicationEngine> m_moteur;
    std::unique_ptr<QQuickWindow> m_fenetre;
    int m_numeroCapture = 0;
    QElapsedTimer m_chrono;
    QList<QPair<QString, qint64>> m_tableauxVus;
    QList<qint64> m_detailsLus;
    qint64 m_marque = 0;
    QString m_projetOuvert;
    QString m_tableauOuvert;
    QList<QByteArray> m_secrets;
    std::thread m_lecteur;
    std::mutex m_verrou;
    std::deque<QString> m_commandes;
    std::atomic<bool> m_finEntree{false};
    bool m_occupe = false;
};

} // namespace

int main(int argc, char *argv[])
{
    qInstallMessageHandler(journaliser);
    QGuiApplication application(argc, argv);
    QCommandLineParser options;
    options.addOption({QStringLiteral("coffre"), QStringLiteral("Préfixe du coffre de test."), QStringLiteral("nom")});
    options.addOption({QStringLiteral("portee"), QStringLiteral("Portée QSettings de test."), QStringLiteral("nom")});
    options.addOption({QStringLiteral("mandataire"), QStringLiteral("Mandataire CONNECT local."), QStringLiteral("hote:port")});
    options.addOption({QStringLiteral("autorite"), QStringLiteral("Autorité de test (PEM)."), QStringLiteral("fichier")});
    options.addOption({QStringLiteral("captures"), QStringLiteral("Dossier des captures."), QStringLiteral("dossier")});
    options.process(application);
    const QString coffre = options.value(QStringLiteral("coffre"));
    const QString portee = options.value(QStringLiteral("portee"));
    // Échec fermé : sans coffre ni portée DE TEST, le pilote toucherait les réglages réels.
    if (!coffre.startsWith(QLatin1String("AcpDesktopE2E-")) || !portee.startsWith(QLatin1String("ACP E2E "))) {
        std::fprintf(stderr, "Refusé : --coffre AcpDesktopE2E-… et --portee \"ACP E2E …\" sont exigés.\n");
        return 2;
    }
    QGuiApplication::setOrganizationName(portee);
    QGuiApplication::setApplicationName(QStringLiteral("Station E2E"));
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    // La plateforme « offscreen » des captures prend la première police venue de
    // QT_QPA_FONTDIR ; la plateforme Windows du produit donne Segoe UI aux contrôles Basic
    // qui n'utilisent pas les jetons typographiques. Les captures reprennent ce défaut.
    if (QGuiApplication::platformName() == QLatin1String("offscreen")) {
        QGuiApplication::setFont(QFont(QStringLiteral("Segoe UI"), 9));
    }

    const QStringList mandataire = options.value(QStringLiteral("mandataire")).split(QLatin1Char(':'));
    if (mandataire.size() != 2 || mandataire.constFirst() != QLatin1String("127.0.0.1")) {
        std::fprintf(stderr, "Refusé : --mandataire 127.0.0.1:<port> est exigé.\n");
        return 2;
    }
    QNetworkProxy::setApplicationProxy(QNetworkProxy(QNetworkProxy::HttpProxy, mandataire.constFirst(),
                                                     static_cast<quint16>(mandataire.constLast().toUInt())));
    const QList<QSslCertificate> autorites = QSslCertificate::fromPath(options.value(QStringLiteral("autorite")));
    if (autorites.isEmpty()) {
        std::fprintf(stderr, "Refusé : autorité de test illisible (--autorite).\n");
        return 2;
    }
    QSslConfiguration configuration = QSslConfiguration::defaultConfiguration();
    configuration.addCaCertificates(autorites);
    QSslConfiguration::setDefaultConfiguration(configuration);

    Application station(nullptr, coffre);
    // La station passe par le mandataire du script (REST et WebSockets, même règle).
    station.findChild<ApiClient *>()->setUseSystemProxy(true);
    station.start();
    Pilote pilote(station, coffre, options.value(QStringLiteral("captures")));
    const int code = QGuiApplication::exec();
    station.shutdown();
    return code;
}
