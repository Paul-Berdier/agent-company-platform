#include "viewmodels/PosteViewModel.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "services/CompatibiliteHermes.h"
#include "viewmodels/Libelles.h"

#include <QClipboard>
#include <QDateTime>
#include <QGuiApplication>
#include <QTimer>

#include <algorithm>

namespace acp {

namespace {

QString texteOuVide(const QJsonValue &valeur)
{
    return libelles::estTexte(valeur) ? valeur.toString() : QString();
}

QJsonObject machineDe(const QJsonObject &vue)
{
    return vue.value(QStringLiteral("machine")).toObject().value(QStringLiteral("machine")).toObject();
}

//! Liste de voies lisible (« Poste (Codex), Hermes »), sinon « Inconnu » : jamais devinée.
QString listeDeVoies(const QJsonValue &valeur)
{
    if (!valeur.isArray()) {
        return libelles::kInconnu;
    }
    QStringList voies;
    for (const QJsonValue &element : valeur.toArray()) {
        if (!libelles::estTexte(element)) {
            return libelles::kInconnu;
        }
        const QString libelle = libelles::voie(element);
        voies.append(libelle.isEmpty() ? element.toString() : libelle);
    }
    return voies.isEmpty() ? QStringLiteral("Aucune") : voies.join(QStringLiteral(", "));
}

/*!
    Voies fermées telles que le greffon les SERT : objet {voie: raison} (routage.voies_fermees), lu
    « Poste (Codex) : raison ; … » ; objet vide : « Aucune » ; toute autre forme ou une raison
    illisible : « Inconnu » (relecture finale de P7, constat desktop-3 : la station lisait un tableau,
    forme jamais servie, et disait toujours « Inconnu »).
*/
QString voiesFermees(const QJsonValue &valeur)
{
    if (!valeur.isObject()) {
        return libelles::kInconnu;
    }
    const QJsonObject fermees = valeur.toObject();
    QStringList lignes;
    for (auto it = fermees.constBegin(); it != fermees.constEnd(); ++it) {
        if (!libelles::estTexte(it.value())) {
            return libelles::kInconnu;
        }
        const QString libelle = libelles::voie(QJsonValue(it.key()));
        lignes.append(QStringLiteral("%1 : %2").arg(libelle.isEmpty() ? it.key() : libelle, it.value().toString()));
    }
    return lignes.isEmpty() ? QStringLiteral("Aucune") : lignes.join(QStringLiteral(" ; "));
}

QVariantMap version(const QString &nom, const QJsonObject &version)
{
    return QVariantMap{
        {QStringLiteral("nom"), nom},
        {QStringLiteral("lue"), libelles::texte(version.value(QStringLiteral("lue")))},
        {QStringLiteral("testee"), libelles::texte(version.value(QStringLiteral("testee")))},
        {QStringLiteral("conforme"), libelles::ouiNon(version.value(QStringLiteral("conforme")))},
    };
}

} // namespace

PosteViewModel::PosteViewModel(ClientGreffonPoste *greffon, CompatibiliteHermes *compatibilite, EventStreamService *flux,
                               QObject *parent)
    : PageViewModel(flux, parent)
    , m_greffon(greffon)
    , m_compatibilite(compatibilite)
    , m_sondage(new Sondage([this] { return m_greffon->poste(); }, Sondage::kIntervallePage, this))
    , m_ordres(new JsonListModel(this))
    , m_decompte(new QTimer(this))
    , m_horloge([] { return QDateTime::currentSecsSinceEpoch(); })
    , m_presse([](const QString &texte) {
        auto *application = qobject_cast<QGuiApplication *>(QCoreApplication::instance());
        if (!application || !QGuiApplication::clipboard()) {
            return false;
        }
        QGuiApplication::clipboard()->setText(texte);
        return true;
    })
{
    // Étape P7 : mêmes sujets que la page web (EtatPoste.tsx).
    m_sondage->suivre(flux->invalidation(),
                      {QStringLiteral("poste"), QStringLiteral("projets"), QStringLiteral("pause"), QStringLiteral("quotas")});
    suivreCadence(m_sondage);
    m_etat = construireEtat({});
    m_machine = construireMachine({});
    m_inventaire = construireInventaire({});
    m_depots = construireDepots({});
    m_decompte->setInterval(1000);
    connect(m_decompte, &QTimer::timeout, this, [this] {
        if (!m_code.isEmpty() && m_expireLe > 0 && secondesRestantes() == 0) {
            // Code expiré : il quitte la mémoire, la page dit d'en générer un nouveau.
            oublierCode();
            m_codeExpire = true;
            emit codeChange();
        }
        emit decompteChange();
    });
    connect(m_sondage, &Sondage::etatChange, this, &PosteViewModel::lectureChange);
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) { lire(reponse.json.object()); });
    if (m_compatibilite) {
        connect(m_compatibilite, &CompatibiliteHermes::change, this, &PosteViewModel::executantChange);
    }
    // Le code d'enrôlement ne survit ni à la page quittée ni à la session perdue.
    connect(this, &PageViewModel::pageVisibleChange, this, [this] {
        if (!pageVisible()) {
            oublierCode();
        }
    });
    // `sourcesChange` est émis à chaque ouverture et fermeture de session, même fenêtre réduite
    // (où `pagesActivesChange` ne l'est plus : les pages sont déjà inactives).
    connect(flux, &EventStreamService::sourcesChange, this, [this] {
        if (!this->flux()->sessionOuverte()) {
            oublierCode();
        }
    });
}

PosteViewModel::~PosteViewModel()
{
    oublierCode();
}

QString PosteViewModel::lecture() const { return m_sondage->libelleLuA(); }
QString PosteViewModel::erreur() const { return m_sondage->derniereErreur(); }

void PosteViewModel::surActivite(bool actif)
{
    m_sondage->setActif(actif);
}

void PosteViewModel::surLienRetabli()
{
    actualiser();
}

void PosteViewModel::surOubli()
{
    m_sondage->oublier();
    oublierCode();
    m_vue = {};
    m_etat = construireEtat({});
    m_machine = construireMachine({});
    m_inventaire = construireInventaire({});
    m_depots = construireDepots({});
    m_alertes.clear();
    m_ordres->clear();
    m_lue = false;
    emit posteChange();
}

void PosteViewModel::actualiser()
{
    m_sondage->lireMaintenant();
}

void PosteViewModel::lire(const QJsonObject &vue)
{
    m_vue = vue;
    m_etat = construireEtat(vue);
    m_machine = construireMachine(vue);
    m_inventaire = construireInventaire(vue);
    m_depots = construireDepots(vue);
    m_alertes.clear();
    for (const QJsonValue &alerte : vue.value(QStringLiteral("alertes")).toArray()) {
        m_alertes.append(libelles::texte(alerte));
    }
    m_ordres->setItems(construireOrdres(vue));
    m_lue = true;
    emit posteChange();
}

QString PosteViewModel::etatBrut() const
{
    return m_vue.value(QStringLiteral("poste")).toObject().value(QStringLiteral("etat")).toString();
}

QString PosteViewModel::etatMachine() const
{
    return machineDe(m_vue).value(QStringLiteral("etat")).toString();
}

QString PosteViewModel::machineId() const
{
    return texteOuVide(machineDe(m_vue).value(QStringLiteral("id")));
}

bool PosteViewModel::peutEnroler() const
{
    const QString etat = etatBrut();
    return m_lue
        && (etat == QLatin1String("non_configure") || etat == QLatin1String("revoque") || etat == QLatin1String("a_confirmer"));
}

bool PosteViewModel::peutConfirmer() const
{
    return m_lue && etatBrut() == QLatin1String("a_confirmer") && !machineId().isEmpty();
}

bool PosteViewModel::peutRelever() const
{
    return m_lue && etatMachine() == QLatin1String("actif");
}

bool PosteViewModel::peutRevoquer() const
{
    return m_lue && !machineId().isEmpty() && etatMachine() != QLatin1String("revoque");
}

QVariantMap PosteViewModel::executant() const
{
    if (!m_compatibilite) {
        return construireExecutant(QStringLiteral("inconnu"), {});
    }
    return construireExecutant(m_compatibilite->etatExecutant(), m_compatibilite->executant());
}

QVariantMap PosteViewModel::construireEtat(const QJsonObject &vue)
{
    const QJsonObject poste = vue.value(QStringLiteral("poste")).toObject();
    const QJsonObject machine = machineDe(vue);
    const QJsonValue etat = poste.value(QStringLiteral("etat"));
    const libelles::Libelle libelle = libelles::etatPoste(etat);
    const QString e = etat.toString();
    QString detail;
    if (e == QLatin1String("a_confirmer")) {
        detail = QStringLiteral("Empreinte annoncée : %1").arg(libelles::texte(machine.value(QStringLiteral("empreinte"))));
    } else if (e == QLatin1String("en_ligne")) {
        detail = QStringLiteral("Vu le %1").arg(libelles::date(poste.value(QStringLiteral("derniere_vue"))));
    } else if (e == QLatin1String("hors_ligne") && poste.value(QStringLiteral("hors_ligne_depuis")).isDouble()) {
        detail = QStringLiteral("Hors ligne depuis le %1").arg(libelles::date(poste.value(QStringLiteral("hors_ligne_depuis"))));
    } else if (e == QLatin1String("revoque")) {
        detail = QStringLiteral("Révoqué le %1").arg(libelles::date(machine.value(QStringLiteral("revoque_le"))));
    }
    return QVariantMap{
        {QStringLiteral("libelle"), libelle.connu() ? libelle.texte : libelles::texte(etat)},
        {QStringLiteral("cle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
        {QStringLiteral("detail"), detail},
        {QStringLiteral("message"), texteOuVide(poste.value(QStringLiteral("message")))},
        {QStringLiteral("politiqueInvalide"),
         !machine.isEmpty() && machine.value(QStringLiteral("politique_valide")) == QJsonValue(false)},
        {QStringLiteral("pauseReclamations"), poste.value(QStringLiteral("pause_reclamations")) == QJsonValue(true)},
        {QStringLiteral("cartesEnAttente"), libelles::nombre(poste.value(QStringLiteral("cartes_en_attente")))},
    };
}

QVariantMap PosteViewModel::construireMachine(const QJsonObject &vue)
{
    const QJsonObject machine = machineDe(vue);
    const bool presente = libelles::estTexte(machine.value(QStringLiteral("id")));
    return QVariantMap{
        {QStringLiteral("presente"), presente && machine.value(QStringLiteral("etat")) != QJsonValue(QStringLiteral("revoque"))},
        {QStringLiteral("nom"), libelles::texte(machine.value(QStringLiteral("nom")))},
        {QStringLiteral("empreinte"), libelles::texte(machine.value(QStringLiteral("empreinte")))},
        {QStringLiteral("versionPoste"), libelles::texte(machine.value(QStringLiteral("version_poste")))},
        {QStringLiteral("protocole"), libelles::texte(machine.value(QStringLiteral("protocole")))},
        {QStringLiteral("enroleLe"), libelles::date(machine.value(QStringLiteral("cree_le")))},
        {QStringLiteral("confirmeLe"), libelles::date(machine.value(QStringLiteral("confirme_le")))},
        {QStringLiteral("derniereRequete"), libelles::date(machine.value(QStringLiteral("derniere_requete")))},
    };
}

QVariantList PosteViewModel::construireDepots(const QJsonObject &vue)
{
    // Mesure de l'exécutant (vue_executant.depots, étape P7) ; à défaut, celle publiée dans l'inventaire.
    const QJsonValue mesures = vue.value(QStringLiteral("executant")).toObject().value(QStringLiteral("depots"));
    const bool parLeGreffon = mesures.isArray();
    const QJsonArray source = parLeGreffon ? mesures.toArray()
                                           : vue.value(QStringLiteral("inventaire")).toObject().value(QStringLiteral("contenu"))
                                                 .toObject().value(QStringLiteral("depots")).toArray();
    QVariantList depots;
    for (const QJsonValue &element : source) {
        const QJsonObject depot = element.toObject();
        const QJsonValue visibilite = depot.value(QStringLiteral("visibilite"));
        const QJsonValue lecture = depot.value(QStringLiteral("lecture"));
        const bool mesure = !(visibilite.isNull() || visibilite.isUndefined()) || !(lecture.isNull() || lecture.isUndefined());
        const QString v = visibilite.toString();
        const QString l = lecture.toString();
        const QString visibiliteLibelle = !mesure ? QStringLiteral("Jamais mesurée par l'exécutant (Codex fermé)")
            : v == QLatin1String("prive")         ? QStringLiteral("Privé")
            : v == QLatin1String("public")        ? QStringLiteral("Public")
            : v == QLatin1String("inconnue")      ? QStringLiteral("Inconnue (Codex fermé)")
                                                  : libelles::texte(visibilite);
        const QString visibiliteCle = !mesure ? QStringLiteral("degraded")
            : v == QLatin1String("prive")    ? QStringLiteral("succeeded")
            : v == QLatin1String("public")   ? QStringLiteral("pending")
            : v == QLatin1String("inconnue") ? QStringLiteral("degraded")
                                             : QStringLiteral("unknown");
        const QString lectureLibelle = !mesure                  ? libelles::kInconnu
            : l == QLatin1String("ok")       ? QStringLiteral("Réussie")
            : l == QLatin1String("refusee")  ? QStringLiteral("Refusée")
            : l == QLatin1String("inconnue") ? QStringLiteral("Inconnue")
                                             : libelles::texte(lecture);
        // Voies du poste ouvertes ou fermées POUR CE DÉPÔT (même calcul que le routage, côté greffon) : objet
        // `{voie: raison}` ; sans lui, « Inconnu » (jamais déduit par la station).
        const QJsonValue fermees = depot.value(QStringLiteral("voies_fermees"));
        QStringList voies;
        if (fermees.isObject()) {
            const QJsonObject parVoie = fermees.toObject();
            for (const QString &voie : {QStringLiteral("poste-codex"), QStringLiteral("poste-claude")}) {
                voies.append(parVoie.contains(voie)
                                 ? QStringLiteral("%1 : Fermée — %2").arg(libelles::voie(voie), libelles::texte(parVoie.value(voie)))
                                 : QStringLiteral("%1 : Ouverte").arg(libelles::voie(voie)));
            }
        }
        depots.append(QVariantMap{
            {QStringLiteral("alias"), libelles::texte(depot.value(QStringLiteral("alias")))},
            {QStringLiteral("visibilite"), visibiliteLibelle},
            {QStringLiteral("visibiliteCle"), visibiliteCle},
            {QStringLiteral("lecture"), lectureLibelle},
            {QStringLiteral("verifieLe"), libelles::dateIso(depot.value(QStringLiteral("verifie_le")))},
            {QStringLiteral("voies"), fermees.isObject() ? voies.join(QLatin1Char('\n')) : libelles::kInconnu},
        });
    }
    return depots;
}

QVariantMap PosteViewModel::construireInventaire(const QJsonObject &vue)
{
    const QJsonValue valeur = vue.value(QStringLiteral("inventaire"));
    if (!valeur.isObject()) {
        return QVariantMap{{QStringLiteral("present"), false}};
    }
    const QJsonObject inventaire = valeur.toObject();
    const QJsonObject contenu = inventaire.value(QStringLiteral("contenu")).toObject();
    const QJsonObject poste = contenu.value(QStringLiteral("poste")).toObject();
    const QJsonObject versions = contenu.value(QStringLiteral("versions")).toObject();
    const QJsonObject bac = contenu.value(QStringLiteral("bac_a_sable_codex")).toObject();
    const QJsonObject connexions = contenu.value(QStringLiteral("connexions")).toObject();

    const QString compteBrut = poste.value(QStringLiteral("compte")).toString();
    const QString compte = compteBrut == QLatin1String("dedie")         ? QStringLiteral("Compte dédié acp-poste")
                         : compteBrut == QLatin1String("proprietaire") ? QStringLiteral("Compte du propriétaire (repli déclaré)")
                                                                       : libelles::texte(poste.value(QStringLiteral("compte")));
    QStringList depots;
    for (const QJsonValue &depot : contenu.value(QStringLiteral("depots")).toArray()) {
        depots.append(libelles::texte(depot.toObject().value(QStringLiteral("alias"))));
    }
    const libelles::Libelle codex = libelles::connexionCodex(connexions.value(QStringLiteral("codex")));
    const libelles::Libelle claude = libelles::connexionClaude(connexions.value(QStringLiteral("claude")));
    return QVariantMap{
        {QStringLiteral("present"), true},
        {QStringLiteral("recuLe"), libelles::date(inventaire.value(QStringLiteral("recu_le")))},
        {QStringLiteral("releveLe"), libelles::date(inventaire.value(QStringLiteral("releve_le")))},
        {QStringLiteral("versionPoste"), libelles::texte(contenu.value(QStringLiteral("version_poste")))},
        {QStringLiteral("compte"), compte},
        {QStringLiteral("windows"), libelles::texte(poste.value(QStringLiteral("windows")))},
        {QStringLiteral("python"), libelles::texte(poste.value(QStringLiteral("python")))},
        {QStringLiteral("empreintePolitique"), libelles::texte(poste.value(QStringLiteral("politique_empreinte")))},
        {QStringLiteral("versions"),
         QVariantList{version(QStringLiteral("Codex"), versions.value(QStringLiteral("codex")).toObject()),
                      version(QStringLiteral("Claude Code"), versions.value(QStringLiteral("claude")).toObject())}},
        {QStringLiteral("readiness"), libelles::texte(bac.value(QStringLiteral("readiness")))},
        {QStringLiteral("modeLu"), libelles::texte(bac.value(QStringLiteral("mode_lu")))},
        {QStringLiteral("origineMode"), libelles::texte(bac.value(QStringLiteral("origine_mode")))},
        {QStringLiteral("palierLu"), libelles::texte(bac.value(QStringLiteral("palier_lu")))},
        {QStringLiteral("stockage"), libelles::texte(bac.value(QStringLiteral("stockage_identifiants_lu")))},
        {QStringLiteral("ecritureAdmise"), libelles::ouiNon(bac.value(QStringLiteral("ecriture_admise")))},
        {QStringLiteral("raison"), texteOuVide(bac.value(QStringLiteral("raison")))},
        {QStringLiteral("codexLibelle"), codex.connu() ? codex.texte : libelles::texte(connexions.value(QStringLiteral("codex")))},
        {QStringLiteral("codexCle"), codex.connu() ? codex.cle : QStringLiteral("unknown")},
        {QStringLiteral("offre"), libelles::texte(connexions.value(QStringLiteral("plan_codex")))},
        {QStringLiteral("claudeLibelle"),
         claude.connu() ? claude.texte : libelles::texte(connexions.value(QStringLiteral("claude")))},
        {QStringLiteral("claudeCle"), claude.connu() ? claude.cle : QStringLiteral("unknown")},
        {QStringLiteral("depots"), depots},
    };
}

QJsonArray PosteViewModel::construireOrdres(const QJsonObject &vue)
{
    QJsonArray ordres;
    for (const QJsonValue &element : vue.value(QStringLiteral("ordres")).toArray()) {
        const QJsonObject ordre = element.toObject();
        const QString genre = libelles::genreOrdre(ordre.value(QStringLiteral("genre")));
        ordres.append(QJsonObject{
            {QStringLiteral("genre"), genre.isEmpty() ? libelles::texte(ordre.value(QStringLiteral("genre"))) : genre},
            {QStringLiteral("creeLe"), libelles::date(ordre.value(QStringLiteral("cree_le")))},
            {QStringLiteral("livraison"), ordre.value(QStringLiteral("livre")) == QJsonValue(true)
                                              ? QStringLiteral("Livré au poste")
                                              : QStringLiteral("Pas encore livré")},
        });
    }
    return ordres;
}

QVariantMap PosteViewModel::construireExecutant(const QString &etat, const QJsonObject &executant)
{
    if (etat != QLatin1String("annonce")) {
        QString message;
        if (etat == QLatin1String("aucun")) {
            message = QStringLiteral("Aucun exécutant connu pour l'instant : l'étape P6 est en place sur ce serveur, "
                                     "mais aucun exécutant ne s'est encore annoncé.");
        } else if (etat == QLatin1String("absent")) {
            message = QStringLiteral("Exécutant : non disponible sur ce serveur (étape P6).");
        } else if (etat == QLatin1String("illisible")) {
            message = QStringLiteral("Exécutant : inconnu, la base du greffon est illisible.");
        } else {
            message = QStringLiteral("Exécutant : inconnu, la description du greffon n'a pas été lue.");
        }
        return QVariantMap{{QStringLiteral("present"), false}, {QStringLiteral("etat"), etat},
                           {QStringLiteral("message"), message}};
    }
    // Étape P6 : seules les clés servies sont lues ; une absence vaut « Inconnu ».
    return QVariantMap{
        {QStringLiteral("present"), true},
        {QStringLiteral("etat"), etat},
        {QStringLiteral("message"), QString()},
        {QStringLiteral("plateforme"), libelles::texte(executant.value(QStringLiteral("plateforme")))},
        {QStringLiteral("hote"), libelles::texte(executant.value(QStringLiteral("hote")))},
        {QStringLiteral("regime"), libelles::texte(executant.value(QStringLiteral("regime")))},
        {QStringLiteral("peutExecuter"), libelles::ouiNon(executant.value(QStringLiteral("peut_executer")))},
        {QStringLiteral("voiesDisponibles"), listeDeVoies(executant.value(QStringLiteral("voies_disponibles")))},
        {QStringLiteral("voiesFermees"), voiesFermees(executant.value(QStringLiteral("voies_fermees")))},
        {QStringLiteral("carteEnCours"), libelles::ouiNon(executant.value(QStringLiteral("carte_en_cours")))},
        {QStringLiteral("erreur"), texteOuVide(executant.value(QStringLiteral("erreur")))},
    };
}

// --- Gestes -------------------------------------------------------------------------------

void PosteViewModel::apresGeste()
{
    m_sondage->lireMaintenant();
    // L'état du poste de la barre d'état suit sans attendre le sondage léger.
    flux()->sondageFond()->lireMaintenant();
}

void PosteViewModel::enroler()
{
    if (gesteEnCours()) {
        return;
    }
    if (!peutEnroler()) {
        echouerGeste(QStringLiteral("Un poste est déjà enrôlé et actif : révoquez-le avant d'en enrôler un autre."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->enrolerPoste();
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const QJsonObject code = reponse.json.object();
        if (!libelles::estTexte(code.value(QStringLiteral("code")))) {
            echouerGeste(QStringLiteral("Réponse du greffon illisible : aucun code d'enrôlement rendu."));
            apresGeste();
            return;
        }
        oublierCode();
        m_code = code.value(QStringLiteral("code")).toString();
        m_commande = libelles::texte(code.value(QStringLiteral("commande")));
        const QJsonValue expire = code.value(QStringLiteral("expire_le"));
        m_expireLe = expire.isDouble() && expire.toDouble() > 0 ? static_cast<qint64>(expire.toDouble()) : 0;
        m_decompte->start();
        emit codeChange();
        emit decompteChange();
        terminerGeste(QStringLiteral("Code d'enrôlement généré : il ne s'affiche qu'une fois."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

int PosteViewModel::secondesRestantes() const
{
    if (m_code.isEmpty() || m_expireLe <= 0) {
        return -1;
    }
    return static_cast<int>(std::max<qint64>(0, m_expireLe - m_horloge()));
}

bool PosteViewModel::codeExpire() const
{
    return m_codeExpire;
}

void PosteViewModel::copierCode()
{
    if (m_code.isEmpty() || !m_presse || !m_presse(m_code)) {
        m_messageCopie = QStringLiteral("Copie impossible : sélectionnez le code à la main.");
    } else {
        m_messageCopie = QStringLiteral("Code copié : videz le presse-papiers après usage.");
    }
    emit codeChange();
}

void PosteViewModel::oublierCode()
{
    const bool avait = !m_code.isEmpty() || m_codeExpire || !m_messageCopie.isEmpty();
    // Le texte est écrasé avant d'être libéré (copie privée : détachée du partage implicite).
    m_code.fill(QLatin1Char('0'));
    m_code.clear();
    m_commande.clear();
    m_expireLe = 0;
    m_codeExpire = false;
    m_messageCopie.clear();
    if (m_decompte) {
        m_decompte->stop();
    }
    if (avait) {
        emit codeChange();
        emit decompteChange();
    }
}

void PosteViewModel::confirmer(const QString &empreinte)
{
    if (gesteEnCours()) {
        return;
    }
    const QString saisie = empreinte.trimmed();
    if (saisie.isEmpty()) {
        echouerGeste(QStringLiteral("Recopiez l'empreinte affichée par la commande d'enrôlement sur le poste."));
        return;
    }
    if (!peutConfirmer()) {
        echouerGeste(QStringLiteral("Aucun poste n'attend de confirmation : la page est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->confirmerEmpreinte(machineId(), saisie);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &) {
        terminerGeste(QStringLiteral("Poste confirmé : il compte désormais."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        // Empreinte différente (409) : le message du greffon tel quel (« révoquez-le »).
        echouerGeste(erreur);
        apresGeste();
    });
}

void PosteViewModel::revoquer(const QString &motif)
{
    if (gesteEnCours()) {
        return;
    }
    const QString texte = motif.trimmed();
    if (texte.isEmpty() || texte.size() > 200) {
        echouerGeste(QStringLiteral("Indiquez un motif de révocation (200 caractères au plus)."));
        return;
    }
    if (!peutRevoquer()) {
        echouerGeste(QStringLiteral("Aucun poste à révoquer : la page est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->revoquerPoste(machineId(), texte);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &) {
        terminerGeste(QStringLiteral("Poste révoqué."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

void PosteViewModel::relever()
{
    if (gesteEnCours()) {
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->releverPoste();
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        // « Ordre de relevé mis en file… » ou « … hors ligne : il sera livré dans N min » :
        // le message du greffon tel quel.
        const QJsonValue message = reponse.json.object().value(QStringLiteral("message"));
        terminerGeste(libelles::estTexte(message) ? message.toString() : QStringLiteral("Ordre de relevé envoyé au poste."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

} // namespace acp
