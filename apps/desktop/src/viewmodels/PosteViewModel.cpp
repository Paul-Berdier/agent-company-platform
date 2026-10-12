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
#include <QRegularExpression>
#include <QTimer>

#include <algorithm>

namespace acp {

namespace {

QString texteOuVide(const QJsonValue &valeur)
{
    return libelles::estTexte(valeur) ? valeur.toString() : QString();
}

QString clotureRailway()
{
    return QStringLiteral("À la fin de l'opération, même si elle a échoué, quittez la session SSH. Dans votre console d'administration Railway, retirez la clé dédiée avec railway ssh keys remove --2fa-code <code> (remplacez <code> par votre code de second facteur). Vérifiez que railway ssh keys est vide, puis exécutez railway logout. Une déconnexion seule ne retire pas la clé. Ces gestes restent les vôtres, selon le guide Railway (§ 11).");
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
    m_verificationTimer = new QTimer(this);
    m_verificationTimer->setInterval(1000);
    connect(m_verificationTimer, &QTimer::timeout, this, &PosteViewModel::evaluerVerification);
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
    connect(this, &PosteViewModel::posteChange, this, &PosteViewModel::preparationChange);
    connect(this, &PosteViewModel::lectureChange, this, &PosteViewModel::preparationChange);
    connect(flux, &EventStreamService::pagesActivesChange, this, &PosteViewModel::majSondage);
    connect(flux, &EventStreamService::lienRetabli, this, [this] {
        if (!actif() && m_resumeVisible && this->flux()->pagesActives()) {
            actualiser();
        }
    });
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) { lire(reponse.json.object()); });
    if (m_compatibilite) {
        connect(m_compatibilite, &CompatibiliteHermes::change, this, &PosteViewModel::executantChange);
    }
    // Le code d'enrôlement ne survit ni à la page quittée ni à la session perdue.
    connect(this, &PageViewModel::pageVisibleChange, this, [this] {
        if (!pageVisible()) {
            fermerGuide();
            oublierCode();
        }
    });
    // `sourcesChange` est émis à chaque ouverture et fermeture de session, même fenêtre réduite
    // (où `pagesActivesChange` ne l'est plus : les pages sont déjà inactives).
    connect(flux, &EventStreamService::sourcesChange, this, [this] {
        if (!this->flux()->sessionOuverte()) {
            oublierVerification();
            fermerGuide();
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

void PosteViewModel::surActivite(bool)
{
    majSondage();
}

void PosteViewModel::majSondage()
{
    m_sondage->setActif(actif() || (m_resumeVisible && flux()->pagesActives()));
}

void PosteViewModel::setResumeVisible(bool visible)
{
    if (m_resumeVisible == visible) return;
    m_resumeVisible = visible;
    emit resumeVisibleChange();
    // Comme pageVisible : la construction de la page précède le départ de sa lecture.
    QTimer::singleShot(0, this, &PosteViewModel::majSondage);
}

QVariantMap PosteViewModel::preparation() const
{
    return construirePreparation(m_vue, m_lue, erreur());
}

void PosteViewModel::surLienRetabli()
{
    actualiser();
}

void PosteViewModel::surOubli()
{
    m_sondage->oublier();
    oublierVerification();
    fermerGuide();
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
    evaluerVerification();
    m_sondage->lireMaintenant();
}

void PosteViewModel::lire(const QJsonObject &vue)
{
    if (machineId() != texteOuVide(machineDe(vue).value(QStringLiteral("id")))
        || m_vue.value(QStringLiteral("executant")).toObject().value(QStringLiteral("plateforme"))
            != vue.value(QStringLiteral("executant")).toObject().value(QStringLiteral("plateforme"))) {
        fermerGuide();
    }
    if (!m_machineVerifiee.isEmpty() && m_machineVerifiee != texteOuVide(machineDe(vue).value(QStringLiteral("id")))
        && m_verificationEtat != QLatin1String("repos")) {
        ++m_generationVerification;
        if (m_verificationEtat == QLatin1String("envoi")) {
            terminerGeste({});
        }
        poserVerification(QStringLiteral("interrompue"), QStringLiteral("La machine active a changé. Relancez la vérification."));
        m_machineVerifiee.clear();
    }
    if (m_guide.value(QStringLiteral("type")).toString() == QLatin1String("recuperation")
        && !construireResultats(vue).contains(m_guide.value(QStringLiteral("resultat")))) {
        fermerGuide();
    }
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
    evaluerVerification();
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

QVariantList PosteViewModel::construireResultats(const QJsonObject &vue)
{
    const QJsonArray branches = vue.value(QStringLiteral("executant")).toObject()
                                   .value(QStringLiteral("branches_pretes")).toArray();
    // Identifiants fermés du contrat partagé. Le texte « commande » distant n'est jamais copié.
    static const QRegularExpression projetValide(QStringLiteral("\\Ap_[0-9a-f]{12}\\z"));
    static const QRegularExpression aliasValide(QStringLiteral("\\A[a-z0-9][a-z0-9-]{0,31}\\z"));
    static const QRegularExpression brancheValide(QStringLiteral("\\Ahermes/projet-[a-z0-9][a-z0-9-]{0,62}\\z"));
    static const QRegularExpression teteValide(QStringLiteral("\\A[0-9a-f]{40}\\z"));
    QVariantList resultat;
    for (const QJsonValue &element : branches) {
        const QJsonObject b = element.toObject();
        const QString projet = texteOuVide(b.value(QStringLiteral("projet")));
        const QString alias = texteOuVide(b.value(QStringLiteral("depot")));
        const QString branche = texteOuVide(b.value(QStringLiteral("branche")));
        const QString tete = texteOuVide(b.value(QStringLiteral("tete")));
        if (!projetValide.match(projet).hasMatch() || !aliasValide.match(alias).hasMatch()
            || !brancheValide.match(branche).hasMatch() || !teteValide.match(tete).hasMatch()) {
            continue;
        }
        resultat.append(QVariantMap{{QStringLiteral("projet"), projet},
            {QStringLiteral("titre"), libelles::texte(b.value(QStringLiteral("projet_titre"))).left(200)},
            {QStringLiteral("depot"), alias}, {QStringLiteral("branche"), branche}, {QStringLiteral("tete"), tete},
            {QStringLiteral("termineLe"), libelles::date(b.value(QStringLiteral("termine_le")))}});
        if (resultat.size() == 20) break; // Même borne que la projection du greffon.
    }
    return resultat;
}

QVariantList PosteViewModel::resultats() const
{
    return construireResultats(m_vue);
}

QString PosteViewModel::resultatsMessage() const
{
    const QJsonValue branches = m_vue.value(QStringLiteral("executant")).toObject().value(QStringLiteral("branches_pretes"));
    if (!branches.isArray()) return QStringLiteral("Hermes ne publie pas de liste de branches terminées pour cet exécutant.");
    if (branches.toArray().isEmpty()) return QStringLiteral("Aucune branche signalée terminée pour le moment.");
    if (resultats().size() < branches.toArray().size())
        return QStringLiteral("Certaines branches publiées sont incomplètes ou illisibles ; leur récupération ne peut pas être préparée.");
    return {};
}

void PosteViewModel::ouvrirGuideRecuperation(const QString &projet, const QString &branche, const QString &tete)
{
    fermerGuide();
    if (!m_lue || !pageVisible() || !flux()->sessionOuverte() || !erreur().isEmpty()) return;
    QVariantMap resultat;
    for (const QVariant &candidat : resultats()) {
        const QVariantMap b = candidat.toMap();
        if (b.value(QStringLiteral("projet")).toString() == projet
            && b.value(QStringLiteral("branche")).toString() == branche
            && b.value(QStringLiteral("tete")).toString() == tete) {
            resultat = b;
            break;
        }
    }
    if (resultat.isEmpty()) return;
    QVariantList etapes;
    const auto ajouter = [&etapes](const QString &titre, const QString &texte, const QString &commande = {}, bool aCompleter = false) {
        etapes.append(QVariantMap{{QStringLiteral("titre"), titre}, {QStringLiteral("texte"), texte},
                                 {QStringLiteral("commande"), commande}, {QStringLiteral("aCompleter"), aCompleter}});
    };
    ajouter(QStringLiteral("Retrouver l'exécutant qui porte la branche"),
            QStringLiteral("Hermes a enregistré cette branche comme terminée. Ce relevé ne prouve pas qu'elle est encore présente sur la machine actuelle. Dans votre session Railway, vérifiez le projet ACP, l'environnement et le service executant qui ont produit ce résultat. Gardez votre clé SSH dédiée dans votre console."));
    ajouter(QStringLiteral("Générer le bundle de cette branche"),
            QStringLiteral("Depuis votre PC, remplacez <chemin-cle-SSH> par le chemin réel de votre clé. Cette commande vérifie la branche et balaie les secrets avant de créer le bundle sur l'exécutant. Relevez le nom de fichier, le SHA-256 et la tête réellement affichés ; aucun téléchargement n'a encore eu lieu."),
            QStringLiteral("railway ssh -i \"<chemin-cle-SSH>\" --service executant -- acp-poste bundle %1 %2")
                .arg(resultat.value(QStringLiteral("depot")).toString(), branche), true);
    ajouter(QStringLiteral("Transférer le fichier indiqué"),
            QStringLiteral("Copiez l'identifiant réel de l'instance depuis Railway (« Copy Service Instance ID »). Utilisez scp avec votre clé dédiée pour rapatrier le fichier exact annoncé, dans /donnees/acp/bundles/. Le nom du bundle et l'identifiant d'instance ne sont pas transmis à ACP : suivez le guide d'exploitation Railway, § 13.7, avec ces valeurs réelles."));
    ajouter(QStringLiteral("Vérifier le fichier et son historique"),
            QStringLiteral("Sur votre PC, calculez le SHA-256 du fichier et comparez-le à celui affiché par l'exécutant. Dans votre dépôt local, lancez git bundle verify avec le chemin réel du bundle. Si l'empreinte ou la vérification ne concorde pas, ne récupérez pas la branche."));
    ajouter(QStringLiteral("Importer puis comparer le commit"),
            QStringLiteral("Dans votre dépôt local, git fetch suivi du chemin du bundle et de %1:%1 importe la branche sans la fusionner. Vérifiez avec git rev-parse %1 que la tête importée est exactement %2. La revue et une éventuelle publication restent vos actions explicites.").arg(branche, tete));
    // Ce parcours récupère une branche sur Railway, même si la machine active a changé depuis.
    ajouter(QStringLiteral("Clore l'accès Railway"), clotureRailway());
    m_guide = {{QStringLiteral("type"), QStringLiteral("recuperation")}, {QStringLiteral("resultat"), resultat},
               {QStringLiteral("titre"), QStringLiteral("Récupérer %1").arg(resultat.value(QStringLiteral("titre")).toString())},
               {QStringLiteral("etapes"), etapes}};
    emit guideChange();
}

QVariantMap PosteViewModel::construirePreparation(const QJsonObject &vue, bool lue, const QString &erreur)
{
    QVariantMap resultat{{QStringLiteral("connectes"), QStringList{}},
                         {QStringLiteral("manquants"), QStringList{}},
                         {QStringLiteral("aVerifier"), QStringList{}},
                         {QStringLiteral("fournisseur"), QString()}};
    const auto resumer = [&resultat](const QString &etat, const QString &cle, const QString &libelle,
                                    const QString &detail, const QString &action, const QString &actionLibelle) {
        resultat.insert(QStringLiteral("etat"), etat);
        resultat.insert(QStringLiteral("cle"), cle);
        resultat.insert(QStringLiteral("libelle"), libelle);
        resultat.insert(QStringLiteral("detail"), detail);
        resultat.insert(QStringLiteral("action"), action);
        resultat.insert(QStringLiteral("actionLibelle"), actionLibelle);
        return resultat;
    };
    if (!erreur.isEmpty()) {
        return resumer(QStringLiteral("erreur"), QStringLiteral("degraded"), QStringLiteral("Préparation non vérifiable"),
                       erreur, QStringLiteral("actualiser"), QStringLiteral("Vérifier les assistants"));
    }
    if (!lue) {
        return resumer(QStringLiteral("inconnu"), QStringLiteral("unknown"), QStringLiteral("Lecture des assistants…"),
                       QStringLiteral("En attente de l'état de votre machine et de ses connexions."),
                       QStringLiteral("actualiser"), QStringLiteral("Voir les assistants"));
    }
    const QJsonObject poste = vue.value(QStringLiteral("poste")).toObject();
    const QJsonObject machine = machineDe(vue);
    const QString etat = poste.value(QStringLiteral("etat")).toString();
    if (etat == QLatin1String("non_configure") || etat == QLatin1String("revoque")) {
        return resumer(QStringLiteral("machine_absente"), QStringLiteral("notConfigured"), QStringLiteral("Machine à configurer"),
                       QStringLiteral("Aucune machine active confirmée. Retrouvez l'exécutant prévu avant d'enrôler un nouveau poste."),
                       QStringLiteral("machine"), QStringLiteral("Préparer la machine"));
    }
    if (etat == QLatin1String("a_confirmer")) {
        return resumer(QStringLiteral("a_confirmer"), QStringLiteral("approvalRequired"), QStringLiteral("Machine à confirmer"),
                       QStringLiteral("Comparez l'empreinte avec celle affichée sur la machine avant de la confirmer."),
                       QStringLiteral("confirmer"), QStringLiteral("Vérifier l'empreinte"));
    }
    if (etat == QLatin1String("hors_ligne")) {
        return resumer(QStringLiteral("hors_ligne"), QStringLiteral("offline"), QStringLiteral("Machine hors ligne"),
                       QStringLiteral("Les connexions déjà relevées ne prouvent pas sa présence actuelle. Vérifiez l'exécutant ; une demande de relevé peut rester en file."),
                       QStringLiteral("machine"), QStringLiteral("Voir la machine"));
    }
    if (etat != QLatin1String("en_ligne") || machine.value(QStringLiteral("etat")) != QJsonValue(QStringLiteral("actif"))
        || !libelles::estTexte(machine.value(QStringLiteral("id")))) {
        return resumer(QStringLiteral("inconnu"), QStringLiteral("unknown"), QStringLiteral("État de la machine inconnu"),
                       QStringLiteral("Le serveur ne fournit pas un état de machine utilisable. Actualisez les observations."),
                       QStringLiteral("actualiser"), QStringLiteral("Vérifier les assistants"));
    }
    if (machine.value(QStringLiteral("politique_valide")) == QJsonValue(false)
        || poste.value(QStringLiteral("pause_reclamations")) == QJsonValue(true)) {
        return resumer(QStringLiteral("bloque"), QStringLiteral("blocked"), QStringLiteral("Exécution suspendue"),
                       machine.value(QStringLiteral("politique_valide")) == QJsonValue(false)
                           ? QStringLiteral("La politique locale est invalide. Une reconnexion des assistants ne résout pas ce blocage.")
                           : QStringLiteral("La pause générale empêche les nouvelles exécutions. Les connexions existantes peuvent être conservées."),
                       QStringLiteral("machine"), QStringLiteral("Voir l'état de la machine"));
    }
    const QJsonObject inventaire = vue.value(QStringLiteral("inventaire")).toObject();
    const QJsonValue connexions = inventaire.value(QStringLiteral("contenu")).toObject().value(QStringLiteral("connexions"));
    if (inventaire.value(QStringLiteral("machine_id")) != machine.value(QStringLiteral("id")) || !connexions.isObject()) {
        return resumer(QStringLiteral("releve_manquant"), QStringLiteral("unknown"), QStringLiteral("Connexions à relever"),
                       QStringLiteral("Aucun relevé de connexions exploitable pour cette machine. Vérifiez ses comptes avant de les reconfigurer."),
                       QStringLiteral("relever"), QStringLiteral("Vérifier les connexions"));
    }
    QStringList connectes, manquants, aVerifier, observations;
    for (const QString &fournisseur : {QStringLiteral("codex"), QStringLiteral("claude")}) {
        const QJsonValue valeur = connexions.toObject().value(fournisseur);
        const bool codex = fournisseur == QLatin1String("codex");
        const QString nom = codex ? QStringLiteral("Codex") : QStringLiteral("Claude Code");
        const auto libelle = codex ? libelles::connexionCodex(valeur) : libelles::connexionClaude(valeur);
        observations.append(nom + QStringLiteral(" : ") + (libelle.connu() ? libelle.texte : libelles::kInconnu));
        if (valeur == QJsonValue(codex ? QStringLiteral("compte_chatgpt") : QStringLiteral("jeton_reconnu"))) {
            connectes.append(fournisseur);
        } else if (valeur == QJsonValue(codex ? QStringLiteral("non_connecte") : QStringLiteral("jeton_absent"))
                   || valeur == QJsonValue(codex ? QStringLiteral("cle_api") : QStringLiteral("refuse"))) {
            manquants.append(fournisseur);
        } else {
            aVerifier.append(fournisseur);
        }
    }
    resultat.insert(QStringLiteral("connectes"), connectes);
    resultat.insert(QStringLiteral("manquants"), manquants);
    resultat.insert(QStringLiteral("aVerifier"), aVerifier);
    const QString detail = observations.join(QStringLiteral(" · "))
        + QStringLiteral(". Relevé : %1. Une connexion observée ne garantit pas l'accès aux modèles ni la disponibilité d'exécution.")
              .arg(libelles::date(inventaire.value(QStringLiteral("releve_le"))));
    if (connectes.isEmpty()) {
        if (!aVerifier.isEmpty()) {
            return resumer(QStringLiteral("a_verifier"), QStringLiteral("unknown"), QStringLiteral("Connexions à vérifier"),
                           detail, QStringLiteral("relever"), QStringLiteral("Vérifier les connexions"));
        }
        resultat.insert(QStringLiteral("fournisseur"), manquants.size() == 1 ? manquants.first() : QString());
        return resumer(QStringLiteral("connexion_manquante"), QStringLiteral("notConfigured"), QStringLiteral("Assistant à configurer"),
                       detail, QStringLiteral("configurer"), QStringLiteral("Configurer un assistant"));
    }
    if (!manquants.isEmpty() || !aVerifier.isEmpty()) {
        resultat.insert(QStringLiteral("fournisseur"), manquants.size() == 1 ? manquants.first() : QString());
        return resumer(QStringLiteral("connexion_partielle"), QStringLiteral("pending"), QStringLiteral("Connexion existante repérée"),
                       detail + QStringLiteral(" Conservez cet accès ; configurez l'autre assistant seulement si votre travail le demande."),
                       QStringLiteral("assistants"), QStringLiteral("Voir les connexions existantes"));
    }
    const QJsonValue tableValide = vue.value(QStringLiteral("catalogue")).toObject()
                                      .value(QStringLiteral("routage")).toObject().value(QStringLiteral("valide"));
    if (tableValide == QJsonValue(false)) {
        return resumer(QStringLiteral("routage_a_valider"), QStringLiteral("pending"), QStringLiteral("Connexions observées, routage à vérifier"),
                       detail + QStringLiteral(" Relisez les suggestions dans Modèles d'exécution, puis validez les entrées que vous autorisez."),
                       QStringLiteral("routage"), QStringLiteral("Vérifier les modèles autorisés"));
    }
    return resumer(QStringLiteral("connexions_observees"), QStringLiteral("succeeded"), QStringLiteral("Connexions existantes repérées"),
                   detail + QStringLiteral(" Inutile de les reconnecter pour ouvrir votre projet. Hermes contrôlera le routage, les quotas et le dépôt au lancement."),
                   QStringLiteral("assistants"), QStringLiteral("Voir les assistants"));
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
        {QStringLiteral("noyau"), libelles::texte(poste.value(QStringLiteral("noyau")))},
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
    if (gesteEnCours() || verificationEnCours()) {
        return;
    }
    if (!flux()->sessionOuverte() || !peutRelever() || machineId().isEmpty()) {
        echouerGeste(QStringLiteral("Aucune machine active à vérifier : actualisez son état."));
        return;
    }
    const auto generation = ++m_generationVerification;
    m_machineVerifiee = machineId();
    m_verificationDebut = m_horloge();
    poserVerification(QStringLiteral("envoi"), QStringLiteral("Demande de vérification en cours…"));
    debuterGeste();
    ApiCall *appel = m_greffon->releverPoste();
    connect(appel, &ApiCall::succeeded, this, [this, generation](const ApiResponse &reponse) {
        if (generation != m_generationVerification) {
            return; // Session ou serveur changés : une réponse tardive ne recrée aucun état.
        }
        if (machineId() != m_machineVerifiee || !peutRelever()) {
            poserVerification(QStringLiteral("interrompue"), QStringLiteral("La machine active a changé. Relancez la vérification."));
            terminerGeste(QStringLiteral("Demande reçue pour la machine précédente."), true);
            return;
        }
        const QJsonObject corps = reponse.json.object();
        if (reponse.httpStatus != 202 || !corps.value(QStringLiteral("ordre")).isDouble()
            || corps.value(QStringLiteral("ordre")).toDouble() <= 0) {
            poserVerification(QStringLiteral("echec"), QStringLiteral("Réponse de vérification illisible. Actualisez avant de réessayer."));
            echouerGeste(m_verificationMessage);
            return;
        }
        // Borne prise APRÈS le 202 : ni un ancien inventaire ni la disparition de l'ordre
        // ne valent vérification. Le protocole ne relie pas directement ordre et inventaire.
        const QJsonObject inventaire = m_vue.value(QStringLiteral("inventaire")).toObject();
        m_inventaireAvant = inventaire.value(QStringLiteral("id")).toInteger();
        m_releveAvant = inventaire.value(QStringLiteral("releve_le")).toInteger();
        m_verificationDebut = m_horloge();
        const QJsonValue message = corps.value(QStringLiteral("message"));
        terminerGeste(libelles::estTexte(message) ? message.toString() : QStringLiteral("Ordre de relevé envoyé au poste."));
        poserVerification(QStringLiteral("attente"), corps.value(QStringLiteral("en_attente_du_poste")) == QJsonValue(true)
            ? QStringLiteral("Machine hors ligne : demande en file. Aucun nouveau relevé reçu pour l'instant.")
            : QStringLiteral("Demande acceptée. En attente d'un nouveau relevé de cette machine…"));
        m_verificationTimer->start();
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this, generation](const ApiError &erreur) {
        if (generation != m_generationVerification) {
            return;
        }
        poserVerification(QStringLiteral("echec"), messageDuRefus(erreur));
        echouerGeste(erreur);
        apresGeste();
    });
}

bool PosteViewModel::verificationEnCours() const
{
    return m_verificationEtat == QLatin1String("envoi") || m_verificationEtat == QLatin1String("attente");
}

void PosteViewModel::poserVerification(const QString &etat, const QString &message)
{
    m_verificationEtat = etat;
    m_verificationMessage = message;
    if (etat != QLatin1String("attente")) {
        m_verificationTimer->stop();
    }
    emit verificationChange();
}

void PosteViewModel::oublierVerification()
{
    ++m_generationVerification;
    m_machineVerifiee.clear();
    // Termine aussi le geste local si sa réponse a été invalidée par la perte de session.
    if (m_verificationEtat == QLatin1String("envoi")) {
        terminerGeste({});
    }
    poserVerification(QStringLiteral("repos"), {});
}

void PosteViewModel::evaluerVerification()
{
    if (m_verificationEtat != QLatin1String("attente") && m_verificationEtat != QLatin1String("retard")) {
        return;
    }
    if (machineId() != m_machineVerifiee || !peutRelever()) {
        poserVerification(QStringLiteral("interrompue"), QStringLiteral("La machine active a changé ou a été révoquée. Relancez la vérification."));
        return;
    }
    const QJsonObject inventaire = m_vue.value(QStringLiteral("inventaire")).toObject();
    const QJsonObject connexions = inventaire.value(QStringLiteral("contenu")).toObject()
                                      .value(QStringLiteral("connexions")).toObject();
    if (inventaire.value(QStringLiteral("machine_id")).toString() == m_machineVerifiee
        && inventaire.value(QStringLiteral("id")).toInteger() > m_inventaireAvant
        && inventaire.value(QStringLiteral("releve_le")).toInteger() > m_releveAvant
        && !connexions.isEmpty()) {
        poserVerification(QStringLiteral("recu"), QStringLiteral("Nouveau relevé reçu. Consultez les états Codex et Claude des cartes : ils peuvent encore indiquer une connexion absente ou refusée."));
    } else if (m_horloge() - m_verificationDebut >= 180) {
        poserVerification(QStringLiteral("retard"), QStringLiteral("Aucun nouveau relevé reçu après trois minutes. La demande peut rester en file sur le serveur. Vérifiez la présence et la pause de la machine, puis actualisez."));
    }
}

QVariantMap PosteViewModel::assistantMachine() const
{
    const QJsonObject executant = m_vue.value(QStringLiteral("executant")).toObject();
    const QJsonObject inventaire = m_vue.value(QStringLiteral("inventaire")).toObject();
    const bool correspond = !machineId().isEmpty()
        && inventaire.value(QStringLiteral("machine_id")).toString() == machineId();
    const QJsonObject contenu = correspond ? inventaire.value(QStringLiteral("contenu")).toObject() : QJsonObject{};
    const QJsonObject poste = contenu.value(QStringLiteral("poste")).toObject();
    QString plateforme = texteOuVide(machineDe(m_vue).value(QStringLiteral("plateforme")));
    if (plateforme.isEmpty()) {
        plateforme = texteOuVide(executant.value(QStringLiteral("plateforme")));
    }
    if (plateforme.isEmpty()) {
        plateforme = texteOuVide(poste.value(QStringLiteral("plateforme")));
    }
    if (plateforme.isEmpty() && libelles::estTexte(poste.value(QStringLiteral("windows")))) {
        plateforme = QStringLiteral("windows"); // Champ effectivement publié par un ancien poste Windows.
    }
    QString hote = texteOuVide(machineDe(m_vue).value(QStringLiteral("hote")));
    if (hote.isEmpty()) {
        hote = texteOuVide(executant.value(QStringLiteral("hote")));
    }
    const QString type = plateforme == QLatin1String("windows") ? QStringLiteral("Poste Windows")
                         : plateforme == QLatin1String("linux") && hote == QLatin1String("railway")
                             ? QStringLiteral("Exécutant Railway")
                         : plateforme == QLatin1String("linux") ? QStringLiteral("Exécutant Linux")
                                                                 : QStringLiteral("Plateforme inconnue");
    return {{QStringLiteral("id"), machineId()},
            {QStringLiteral("nom"), libelles::texte(machineDe(m_vue).value(QStringLiteral("nom")))},
            {QStringLiteral("type"), type}, {QStringLiteral("plateforme"), plateforme},
            {QStringLiteral("hote"), hote}, {QStringLiteral("compte"), texteOuVide(poste.value(QStringLiteral("compte")))},
            {QStringLiteral("guideDisponible"), peutRelever() && (plateforme == QLatin1String("windows") || plateforme == QLatin1String("linux"))},
            {QStringLiteral("releve"), correspond ? libelles::date(inventaire.value(QStringLiteral("releve_le"))) : libelles::kInconnu}};
}

QVariantList PosteViewModel::assistants() const
{
    const QJsonObject inventaire = m_vue.value(QStringLiteral("inventaire")).toObject();
    // Un inventaire d'une ancienne machine ne devient pas celui du nouvel enrôlement.
    const bool correspond = !machineId().isEmpty()
        && inventaire.value(QStringLiteral("machine_id")).toString() == machineId();
    const QJsonObject contenu = correspond ? inventaire.value(QStringLiteral("contenu")).toObject() : QJsonObject{};
    const QJsonObject connexions = contenu.value(QStringLiteral("connexions")).toObject();
    const QJsonObject versions = contenu.value(QStringLiteral("versions")).toObject();
    QVariantList resultat;
    for (const QString &fournisseur : {QStringLiteral("codex"), QStringLiteral("claude")}) {
        const bool codex = fournisseur == QLatin1String("codex");
        const auto valeur = connexions.value(fournisseur);
        const auto libelle = codex ? libelles::connexionCodex(valeur) : libelles::connexionClaude(valeur);
        QString mode = libelles::kInconnu;
        if (codex && valeur == QJsonValue(QStringLiteral("compte_chatgpt"))) {
            mode = QStringLiteral("Compte ChatGPT via Codex CLI");
        } else if (codex && valeur == QJsonValue(QStringLiteral("cle_api"))) {
            mode = QStringLiteral("Clé API détectée — voie non prise en charge");
        } else if (!codex && (valeur == QJsonValue(QStringLiteral("jeton_reconnu"))
                             || valeur == QJsonValue(QStringLiteral("jeton_present_non_verifie"))
                             || valeur == QJsonValue(QStringLiteral("refuse")))) {
            mode = QStringLiteral("Jeton Claude Code du coffre de la machine");
        }
        resultat.append(QVariantMap{
            {QStringLiteral("fournisseur"), fournisseur},
            {QStringLiteral("nom"), codex ? QStringLiteral("Codex") : QStringLiteral("Claude Code")},
            {QStringLiteral("etat"), libelle.connu() ? libelle.texte : libelles::texte(valeur)},
            {QStringLiteral("cle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
            {QStringLiteral("mode"), mode},
            {QStringLiteral("version"), libelles::texte(versions.value(fournisseur).toObject().value(QStringLiteral("lue")))},
            {QStringLiteral("offre"), codex ? libelles::texte(connexions.value(QStringLiteral("plan_codex"))) : libelles::kInconnu},
            {QStringLiteral("detail"), codex
                ? QStringLiteral("État déclaré par le CLI sur cette machine. L'identité personnelle du compte n'est pas transmise à ACP.")
                : QStringLiteral("« Jeton reconnu » décrit le résultat de auth status, pas une garantie de validité distante. Le dépôt d'un jeton ne suffit pas à confirmer la connexion.")}});
    }
    return resultat;
}

void PosteViewModel::ouvrirGuide(const QString &fournisseur)
{
    fermerGuide();
    QVariantList etapes;
    const auto ajouter = [&etapes](const QString &titre, const QString &texte, const QString &commande = {}, bool aCompleter = false) {
        etapes.append(QVariantMap{{QStringLiteral("titre"), titre}, {QStringLiteral("texte"), texte},
                                 {QStringLiteral("commande"), commande}, {QStringLiteral("aCompleter"), aCompleter}});
    };
    if (fournisseur == QLatin1String("hermes")) {
        ajouter(QStringLiteral("Ouvrir votre Hermes"), QStringLiteral("Dans votre navigateur, ouvrez l'adresse Hermes enregistrée dans Réglages et connectez-vous avec votre identité ACP."));
        ajouter(QStringLiteral("Connecter le coordinateur"), QStringLiteral("Dans le tableau de bord : Clés → Connexions fournisseurs (OAuth) → openai-codex → Connexion. Ouvrez l'adresse officielle affichée et saisissez le code d'appareil avec votre compte ChatGPT."));
        ajouter(QStringLiteral("Choisir le modèle"), QStringLiteral("Dans Modèles, choisissez le modèle par défaut de Hermes. Revenez ensuite dans Discussion pour lui parler. Les comptes de Codex et Claude sur la machine d'exécution sont configurés séparément."));
        ajouter(QStringLiteral("Gérer cette connexion"), QStringLiteral("La reconnexion et la déconnexion du coordinateur se font dans ce même tableau de bord. Une déconnexion empêche ses prochaines réponses ; elle ne déconnecte pas les assistants de la machine."));
        m_guide = {{QStringLiteral("titre"), QStringLiteral("Configurer Hermes coordinateur")}, {QStringLiteral("etapes"), etapes}};
        emit guideChange();
        return;
    }
    if (fournisseur != QLatin1String("codex") && fournisseur != QLatin1String("claude")) {
        return;
    }
    const QVariantMap machine = assistantMachine();
    if (!machine.value(QStringLiteral("guideDisponible")).toBool()) {
        return;
    }
    const bool codex = fournisseur == QLatin1String("codex");
    const bool windows = machine.value(QStringLiteral("plateforme")).toString() == QLatin1String("windows");
    const QString prefixe = windows ? QStringLiteral("& \"$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd\" ") : QStringLiteral("acp-poste ");
    if (!codex) {
        ajouter(QStringLiteral("Préparer Claude Code dans votre session"), QStringLiteral("Sur votre PC, lancez le binaire officiel connecté à votre compte autorisé. Le jeton reste dans votre terminal : ne le collez pas dans ACP ni dans une discussion."), QStringLiteral("claude setup-token"));
    }
    if (windows) {
        const QString compte = machine.value(QStringLiteral("compte")).toString();
        if (compte == QLatin1String("dedie")) {
            ajouter(QStringLiteral("Ouvrir la console du compte dédié"), QStringLiteral("Sur le PC affiché ci-dessus, depuis votre session Windows. La connexion de votre compte utilisateur habituel n'est pas celle du poste ACP."), QStringLiteral("runas /user:acp-poste \"powershell -NoProfile\""));
        } else {
            ajouter(QStringLiteral("Ouvrir la console du compte d'exécution"), compte == QLatin1String("proprietaire")
                ? QStringLiteral("Ce poste publie un fonctionnement dans le compte du propriétaire. Utilisez sa console PowerShell sur le PC indiqué.")
                : QStringLiteral("Le compte Windows d'exécution est inconnu. Vérifiez le compte de la tâche Poste ACP avant de poursuivre ; n'utilisez pas une autre session par défaut."));
        }
    } else {
        ajouter(QStringLiteral("Ouvrir la console de l'exécutant"), machine.value(QStringLiteral("hote")).toString() == QLatin1String("railway")
            ? QStringLiteral("Depuis votre session d'administration Railway déjà reliée au bon projet ACP, ouvrez le service executant. L'accès Railway et sa clé SSH restent réservés au propriétaire ; vérifiez le projet et l'environnement avant de continuer. Utilisez votre clé SSH dédiée selon le guide Railway (§ 13.4) ; n'ajoutez pas --session.")
            : QStringLiteral("Ouvrez votre console d'administration sur la machine Linux affichée. N'exécutez pas ces commandes dans le conteneur Hermes."),
            machine.value(QStringLiteral("hote")).toString() == QLatin1String("railway") ? QStringLiteral("railway ssh -i \"<chemin-cle-SSH>\" --service executant") : QString(), machine.value(QStringLiteral("hote")).toString() == QLatin1String("railway"));
        ajouter(QStringLiteral("Suspendre les travaux"), QStringLiteral("La pause ferme les nouvelles cartes et les sondes. Attendez que la carte en cours s'arrête proprement avant de connecter le compte."), QStringLiteral("acp-poste pause"));
    }
    ajouter(codex ? QStringLiteral("Connecter ou reconnecter Codex") : QStringLiteral("Déposer le jeton dans le coffre"), codex
        ? QStringLiteral("Dans cette console, le CLI officiel affiche l'adresse et le code d'appareil. Autorisez la connexion dans votre navigateur. Si nécessaire, activez l'authentification par code d'appareil dans les paramètres de sécurité ChatGPT. Attendez le résultat du CLI.")
        : QStringLiteral("Collez le jeton uniquement dans la saisie masquée de cette commande. Le message de dépôt confirme son stockage, pas sa validité. Videz ensuite le presse-papiers et son historique Windows (Win+V)."),
        prefixe + QStringLiteral("connexion ") + fournisseur);
    if (codex && windows) {
        ajouter(QStringLiteral("Préparer le bac à sable si nécessaire"), QStringLiteral("Si le diagnostic indique que le bac à sable n'est pas prêt, exécutez cette commande dans la même console. La demande UAC nécessite les droits administrateur."), prefixe + QStringLiteral("connexion bac-a-sable"));
    }
    if (!windows) {
        ajouter(QStringLiteral("Reprendre les travaux"), QStringLiteral("Une fois la connexion terminée, reprenez l'exécutant pour réautoriser les sondes et les nouvelles cartes."), QStringLiteral("acp-poste reprise"));
    }
    ajouter(QStringLiteral("Contrôler la machine"), QStringLiteral("Lisez le diagnostic, puis revenez ici et choisissez Vérifier maintenant. Un nouveau relevé peut demander une à deux minutes ; les états refusé ou inconnu restent affichés tels quels."), prefixe + QStringLiteral("diagnostic"));
    ajouter(QStringLiteral("Comprendre les effets"), QStringLiteral("Reconnecter remplace l'accès de cet assistant sur cette machine et peut interrompre les prochaines missions qui l'utilisent. ACP ne propose pas encore de déconnexion distante du compte. Révoquer la machine dans les diagnostics coupe son lien avec ACP, sans déconnecter son compte fournisseur."));
    if (!windows && machine.value(QStringLiteral("hote")).toString() == QLatin1String("railway")) {
        ajouter(QStringLiteral("Clore l'accès Railway"), clotureRailway());
    }
    m_guide = {{QStringLiteral("titre"), QStringLiteral("Configurer %1 · %2").arg(codex ? QStringLiteral("Codex") : QStringLiteral("Claude Code"), machine.value(QStringLiteral("nom")).toString())},
               {QStringLiteral("etapes"), etapes}};
    emit guideChange();
}

void PosteViewModel::fermerGuide()
{
    if (m_guide.isEmpty() && m_copieGuide.isEmpty()) {
        return;
    }
    m_guide.clear();
    m_copieGuide.clear();
    emit guideChange();
}

void PosteViewModel::copierEtape(int index)
{
    if (m_guide.value(QStringLiteral("type")).toString() == QLatin1String("recuperation")
        && (!pageVisible() || !flux()->sessionOuverte() || !erreur().isEmpty())) {
        fermerGuide();
        return;
    }
    const QVariantList etapes = m_guide.value(QStringLiteral("etapes")).toList();
    if (index < 0 || index >= etapes.size()) {
        return;
    }
    const QString commande = etapes.at(index).toMap().value(QStringLiteral("commande")).toString();
    if (commande.isEmpty()) {
        return;
    }
    const bool aCompleter = etapes.at(index).toMap().value(QStringLiteral("aCompleter")).toBool();
    m_copieGuide = m_presse && m_presse(commande)
        ? (aCompleter ? QStringLiteral("Commande copiée : complétez le chemin de votre clé SSH avant de l'exécuter.")
                     : QStringLiteral("Commande copiée. Exécutez-la dans la console indiquée à cette étape."))
        : QStringLiteral("Copie impossible : sélectionnez la commande à la main.");
    emit guideChange();
}
} // namespace acp
