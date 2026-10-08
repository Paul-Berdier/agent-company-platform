#include "viewmodels/RoutageViewModel.h"

#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/FluxInvalidation.h"
#include "events/Sondage.h"
#include "viewmodels/Libelles.h"

#include <QDesktopServices>
#include <QUrlQuery>

#include <algorithm>
#include <cmath>

namespace acp {

namespace {

QString texteOuVide(const QJsonValue &valeur)
{
    return libelles::estTexte(valeur) ? valeur.toString() : QString();
}

QJsonValue chaineOuNul(const QJsonValue &valeur)
{
    return valeur.isString() ? valeur : QJsonValue(QJsonValue::Null);
}

bool estEntier(const QJsonValue &valeur)
{
    return valeur.isDouble() && std::floor(valeur.toDouble()) == valeur.toDouble();
}

//! Liste de valeurs courtes : « a, b », « Aucun » si vide, « Inconnu » si illisible.
QString liste(const QJsonValue &valeur, const QString &vide = QStringLiteral("Aucun"))
{
    if (!valeur.isArray()) {
        return libelles::kInconnu;
    }
    QStringList valeurs;
    for (const QJsonValue &element : valeur.toArray()) {
        valeurs.append(libelles::texte(element));
    }
    return valeurs.isEmpty() ? vide : valeurs.join(QStringLiteral(", "));
}

QString listeDeVoies(const QJsonValue &valeur)
{
    if (!valeur.isArray()) {
        return libelles::kInconnu;
    }
    QStringList voies;
    for (const QJsonValue &element : valeur.toArray()) {
        const QString libelle = libelles::voie(element);
        voies.append(libelle.isEmpty() ? libelles::texte(element) : libelle);
    }
    return voies.isEmpty() ? QStringLiteral("Aucune") : voies.join(QStringLiteral(", "));
}

QString libelleClasse(const QString &classe)
{
    const QString libelle = libelles::classe(QJsonValue(classe));
    return libelle.isEmpty() ? classe : libelle;
}

} // namespace

RoutageViewModel::RoutageViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                                   QObject *parent)
    : PageViewModel(flux, parent)
    , m_client(client)
    , m_greffon(greffon)
    , m_sondage(new Sondage([this] { return m_greffon->routage(); }, Sondage::kIntervallePage, this))
    , m_listes(new JsonListModel(this))
    , m_classes(new JsonListModel(this))
    , m_surcharges(new JsonListModel(this))
    , m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); })
{
    m_politiqueHermes = construirePolitiqueHermes({});
    m_politiquePoste = construirePolitiquePoste({});
    // Étape P7 : mêmes sujets que la page web (Routage.tsx).
    m_sondage->suivre(flux->invalidation(), {QStringLiteral("quotas"), QStringLiteral("poste")});
    connect(m_sondage, &Sondage::etatChange, this, &RoutageViewModel::lectureChange);
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) { lire(reponse.json.object()); });
}

RoutageViewModel::~RoutageViewModel() = default;

QString RoutageViewModel::lecture() const { return m_sondage->libelleLuA(); }
QString RoutageViewModel::erreur() const { return m_sondage->derniereErreur(); }

void RoutageViewModel::surActivite(bool actif)
{
    m_sondage->setActif(actif);
}

void RoutageViewModel::surLienRetabli()
{
    actualiser();
}

void RoutageViewModel::surOubli()
{
    m_sondage->oublier();
    m_vue = {};
    m_relevesDuBrouillon = {};
    m_brouillon.clear();
    m_refus.clear();
    m_refusTexte.clear();
    m_rebatir = true;
    m_listes->clear();
    m_classes->clear();
    m_surcharges->clear();
    m_politiqueHermes = construirePolitiqueHermes({});
    m_politiquePoste = construirePolitiquePoste({});
    m_lue = false;
    emit routageChange();
}

void RoutageViewModel::actualiser()
{
    m_sondage->lireMaintenant();
}

bool RoutageViewModel::releveFactice() const
{
    return m_vue.value(QStringLiteral("releve_factice")) == QJsonValue(true);
}

// --- Lecture ---------------------------------------------------------------------------------

void RoutageViewModel::lire(const QJsonObject &vue)
{
    m_vue = vue;
    const QJsonObject voies = vue.value(QStringLiteral("voies")).toObject();
    QJsonArray listes;
    for (const QString &voie : {QStringLiteral("poste-codex"), QStringLiteral("poste-claude")}) {
        listes.append(construireListe(voie, voies.value(voie).toObject()));
    }
    m_listes->setItems(listes);
    m_surcharges->setItems(construireSurcharges(vue));
    m_politiqueHermes = construirePolitiqueHermes(vue);
    m_politiquePoste = construirePolitiquePoste(vue);
    // Le brouillon n'est rebâti que si un nouveau relevé arrive (ou après une validation, un
    // relevé changé) : ni à chaque sondage, ni après un geste du brouillon.
    const QJsonObject releves = vue.value(QStringLiteral("releves")).toObject();
    if (m_rebatir || releves != m_relevesDuBrouillon) {
        rebatirBrouillon();
    }
    publierClasses();
    m_lue = true;
    emit routageChange();
}

QJsonArray RoutageViewModel::entreesEnregistrees(const QString &classe) const
{
    QJsonArray entrees;
    const QJsonObject c = m_vue.value(QStringLiteral("classes")).toObject().value(classe).toObject();
    for (const QJsonValue &entree : c.value(QStringLiteral("entrees")).toArray()) {
        entrees.append(entreePropre(entree.toObject()));
    }
    return entrees;
}

void RoutageViewModel::rebatirBrouillon()
{
    m_rebatir = false;
    m_relevesDuBrouillon = m_vue.value(QStringLiteral("releves")).toObject();
    m_brouillon.clear();
    for (const QString &classe : m_vue.value(QStringLiteral("classes")).toObject().keys()) {
        m_brouillon.insert(classe, entreesEnregistrees(classe));
    }
    m_refus.clear();
    m_refusTexte.clear();
}

void RoutageViewModel::publierClasses()
{
    const QJsonObject classes = m_vue.value(QStringLiteral("classes")).toObject();
    QJsonArray items;
    for (const QString &classe : ordreDesClasses(classes)) {
        const QJsonObject c = classes.value(classe).toObject();
        const QJsonArray brouillon = m_brouillon.value(classe);
        const QJsonArray enregistrees = c.value(QStringLiteral("entrees")).toArray();
        const bool modifiee = brouillon != entreesEnregistrees(classe);
        const QHash<int, QString> refus = m_refus.value(classe);
        QJsonArray entrees;
        for (qsizetype rang = 0; rang < brouillon.size(); ++rang) {
            QString verdict;
            QString cle;
            QString message;
            if (refus.contains(static_cast<int>(rang))) {
                verdict = QStringLiteral("Refusée");
                cle = QStringLiteral("failed");
                message = refus.value(static_cast<int>(rang));
            } else if (modifiee) {
                verdict = QStringLiteral("À valider");
                cle = QStringLiteral("pending");
            } else {
                const QJsonObject jugee = enregistrees.at(rang).toObject();
                if (jugee.value(QStringLiteral("admise")) == QJsonValue(true)) {
                    verdict = QStringLiteral("Admise");
                    cle = QStringLiteral("succeeded");
                } else if (jugee.value(QStringLiteral("admise")) == QJsonValue(false)) {
                    verdict = QStringLiteral("Refusée");
                    cle = QStringLiteral("failed");
                    message = texteOuVide(jugee.value(QStringLiteral("message")));
                }
            }
            entrees.append(QJsonObject{
                {QStringLiteral("rang"), static_cast<int>(rang)},
                {QStringLiteral("texte"), texteEntree(brouillon.at(rang).toObject())},
                {QStringLiteral("verdict"), verdict},
                {QStringLiteral("verdictCle"), cle},
                {QStringLiteral("message"), message},
            });
        }
        const QJsonObject suggestion = c.value(QStringLiteral("suggestion")).toObject();
        QStringList lignesSuggestion;
        for (const QJsonValue &entree : suggestion.value(QStringLiteral("entrees")).toArray()) {
            lignesSuggestion.append(texteEntree(entree.toObject()));
        }
        QStringList remarques;
        for (const QJsonValue &remarque : suggestion.value(QStringLiteral("remarques")).toArray()) {
            remarques.append(libelles::texte(remarque));
        }
        const libelles::Libelle etat = libelles::etatTable(c.value(QStringLiteral("etat")));
        items.append(QJsonObject{
            {QStringLiteral("classe"), classe},
            {QStringLiteral("titre"), libelleClasse(classe)},
            {QStringLiteral("etatLibelle"), etat.connu() ? etat.texte : libelles::texte(c.value(QStringLiteral("etat")))},
            {QStringLiteral("etatCle"), etat.connu() ? etat.cle : QStringLiteral("unknown")},
            {QStringLiteral("valideLe"), c.value(QStringLiteral("valide_le")).isDouble()
                                             ? libelles::date(c.value(QStringLiteral("valide_le")))
                                             : QString()},
            {QStringLiteral("voies"), listeDeVoies(c.value(QStringLiteral("voies")))},
            {QStringLiteral("entrees"), entrees},
            {QStringLiteral("vide"), brouillon.isEmpty()},
            {QStringLiteral("modifiee"), modifiee},
            {QStringLiteral("aSuggestion"), !lignesSuggestion.isEmpty()},
            {QStringLiteral("suggestion"), lignesSuggestion.join(QLatin1Char('\n'))},
            {QStringLiteral("suggestionLibelle"), texteOuVide(suggestion.value(QStringLiteral("libelle")))},
            {QStringLiteral("remarques"), remarques.join(QLatin1Char('\n'))},
        });
    }
    m_classes->setItems(items);
}

bool RoutageViewModel::brouillonModifie() const
{
    for (auto it = m_brouillon.cbegin(); it != m_brouillon.cend(); ++it) {
        if (it.value() != entreesEnregistrees(it.key())) {
            return true;
        }
    }
    return false;
}

bool RoutageViewModel::brouillonVide() const
{
    return std::all_of(m_brouillon.cbegin(), m_brouillon.cend(), [](const QJsonArray &entrees) { return entrees.isEmpty(); });
}

// --- Fonctions pures -------------------------------------------------------------------------

QJsonObject RoutageViewModel::construireListe(const QString &voie, const QJsonObject &catalogue)
{
    const QJsonValue badge = catalogue.value(QStringLiteral("badge"));
    const libelles::Libelle libelle = libelles::badgeListe(badge);
    QJsonArray modeles;
    for (const QJsonValue &element : catalogue.value(QStringLiteral("modeles")).toArray()) {
        const QJsonObject modele = element.toObject();
        const QJsonValue efforts = modele.value(QStringLiteral("supportedReasoningEfforts"));
        QString texteEfforts = QStringLiteral("Efforts inconnus");
        if (efforts.isArray()) {
            texteEfforts = efforts.toArray().isEmpty() ? QStringLiteral("Aucun effort documenté")
                                                       : QStringLiteral("Efforts : %1").arg(liste(efforts));
        }
        modeles.append(QJsonObject{
            {QStringLiteral("id"), libelles::texte(modele.value(QStringLiteral("id")))},
            {QStringLiteral("parDefaut"), modele.value(QStringLiteral("isDefault")) == QJsonValue(true)},
            {QStringLiteral("efforts"), texteEfforts},
            {QStringLiteral("resolution"), texteOuVide(modele.value(QStringLiteral("resolution_documentee")))},
        });
    }
    QString aucunModele;
    if (modeles.isEmpty()) {
        aucunModele = catalogue.isEmpty() || badge == QJsonValue(QStringLiteral("inconnu"))
            ? QStringLiteral("Aucun relevé : le poste n'a encore rien publié.")
            : QStringLiteral("Aucun modèle dans ce relevé.");
    }
    const QJsonValue releve = catalogue.value(QStringLiteral("releve_id"));
    const QString titre = libelles::voie(QJsonValue(voie));
    return QJsonObject{
        {QStringLiteral("voie"), voie},
        {QStringLiteral("titre"), titre.isEmpty() ? voie : titre},
        {QStringLiteral("badgeLibelle"), libelle.connu() ? libelle.texte : libelles::texte(badge)},
        {QStringLiteral("badgeCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
        {QStringLiteral("releveLe"), catalogue.value(QStringLiteral("releve_le")).isDouble()
                                         ? libelles::date(catalogue.value(QStringLiteral("releve_le")))
                                         : QString()},
        {QStringLiteral("versionCli"), texteOuVide(catalogue.value(QStringLiteral("version_cli")))},
        {QStringLiteral("detail"), texteOuVide(catalogue.value(QStringLiteral("detail")))},
        {QStringLiteral("documentation"), texteOuVide(catalogue.value(QStringLiteral("documentation_lue_le")))},
        {QStringLiteral("modeles"), modeles},
        {QStringLiteral("aucunModele"), aucunModele},
        {QStringLiteral("peutAccepter"),
         badge == QJsonValue(QStringLiteral("liste_de_secours_probable")) && estEntier(releve) && releve.toDouble() > 0},
    };
}

QString RoutageViewModel::texteEntree(const QJsonObject &entree)
{
    QStringList parties;
    const QJsonValue voie = entree.value(QStringLiteral("voie"));
    const QString libelleVoie = libelles::voie(voie);
    parties.append(libelleVoie.isEmpty() ? libelles::texte(voie) : libelleVoie);
    const QJsonValue modele = entree.value(QStringLiteral("modele"));
    parties.append(libelles::estTexte(modele) ? modele.toString() : QStringLiteral("modèle par défaut"));
    const QJsonValue effort = entree.value(QStringLiteral("effort"));
    if (libelles::estTexte(effort)) {
        parties.append(QStringLiteral("effort %1").arg(effort.toString()));
    }
    const QJsonValue palier = entree.value(QStringLiteral("palier"));
    if (libelles::estTexte(palier)) {
        const QString libellePalier = libelles::palier(palier);
        parties.append(QStringLiteral("palier %1").arg(libellePalier.isEmpty() ? palier.toString() : libellePalier));
    }
    return parties.join(QStringLiteral(" · "));
}

QJsonObject RoutageViewModel::entreePropre(const QJsonObject &entree)
{
    return QJsonObject{
        {QStringLiteral("voie"), chaineOuNul(entree.value(QStringLiteral("voie")))},
        {QStringLiteral("modele"), chaineOuNul(entree.value(QStringLiteral("modele")))},
        {QStringLiteral("effort"), chaineOuNul(entree.value(QStringLiteral("effort")))},
        {QStringLiteral("palier"), chaineOuNul(entree.value(QStringLiteral("palier")))},
    };
}

QStringList RoutageViewModel::ordreDesClasses(const QJsonObject &classes)
{
    QStringList ordre;
    for (const QString &classe : libelles::ordreDesClasses()) {
        if (classes.contains(classe)) {
            ordre.append(classe);
        }
    }
    QStringList autres;
    for (const QString &classe : classes.keys()) {
        if (!ordre.contains(classe)) {
            autres.append(classe);
        }
    }
    autres.sort();
    return ordre + autres;
}

QVariantMap RoutageViewModel::construirePolitiqueHermes(const QJsonObject &vue)
{
    const QJsonObject politique = vue.value(QStringLiteral("politique_hermes")).toObject();
    return QVariantMap{
        {QStringLiteral("effortsInterdits"), liste(politique.value(QStringLiteral("efforts_interdits")))},
        {QStringLiteral("paliersAdmis"), liste(politique.value(QStringLiteral("paliers_admis")))},
        {QStringLiteral("horsEnveloppe"), liste(politique.value(QStringLiteral("efforts_hors_enveloppe")))},
    };
}

QVariantMap RoutageViewModel::construirePolitiquePoste(const QJsonObject &vue)
{
    const QJsonValue valeur = vue.value(QStringLiteral("politique_poste"));
    if (!valeur.isObject()) {
        return QVariantMap{{QStringLiteral("presente"), false}};
    }
    const QJsonObject politique = valeur.toObject();
    const QString tous = QStringLiteral("Tous ceux du relevé");
    return QVariantMap{
        {QStringLiteral("presente"), true},
        {QStringLiteral("executants"), liste(politique.value(QStringLiteral("executants")))},
        {QStringLiteral("effortsInterdits"), liste(politique.value(QStringLiteral("efforts_interdits")))},
        {QStringLiteral("paliersAdmis"), liste(politique.value(QStringLiteral("paliers_admis")))},
        {QStringLiteral("modelesCodex"), liste(politique.value(QStringLiteral("modeles_codex_permis")), tous)},
        {QStringLiteral("aliasClaude"), liste(politique.value(QStringLiteral("alias_claude_permis")), tous)},
        {QStringLiteral("reseau"), libelles::ouiNon(politique.value(QStringLiteral("reseau_executants")))},
    };
}

QJsonArray RoutageViewModel::construireSurcharges(const QJsonObject &vue)
{
    QJsonArray surcharges;
    for (const QJsonValue &element : vue.value(QStringLiteral("surcharges")).toArray()) {
        const QJsonObject surcharge = element.toObject();
        const QJsonValue identifiant = surcharge.value(QStringLiteral("id"));
        const QString classe = surcharge.value(QStringLiteral("classe")).toString();
        surcharges.append(QJsonObject{
            {QStringLiteral("id"), estEntier(identifiant) ? QString::number(identifiant.toInteger()) : QString()},
            {QStringLiteral("classe"), classe.isEmpty() ? libelles::kInconnu : libelleClasse(classe)},
            {QStringLiteral("entree"), texteEntree(surcharge)},
            {QStringLiteral("creeLe"), libelles::date(surcharge.value(QStringLiteral("cree_le")))},
            {QStringLiteral("motif"), libelles::texte(surcharge.value(QStringLiteral("motif")))},
        });
    }
    return surcharges;
}

// --- Gestes du brouillon (aucun appel) ---------------------------------------------------------

void RoutageViewModel::appliquerSuggestion(const QString &classe)
{
    const QJsonObject classes = m_vue.value(QStringLiteral("classes")).toObject();
    if (!classes.contains(classe)) {
        echouerGeste(QStringLiteral("Classe inconnue : la page est relue."));
        m_sondage->lireMaintenant();
        return;
    }
    QJsonArray entrees;
    const QJsonObject suggestion = classes.value(classe).toObject().value(QStringLiteral("suggestion")).toObject();
    for (const QJsonValue &entree : suggestion.value(QStringLiteral("entrees")).toArray()) {
        entrees.append(entreePropre(entree.toObject()));
    }
    if (entrees.isEmpty()) {
        echouerGeste(QStringLiteral("Le greffon ne propose aucune suggestion pour cette classe."));
        return;
    }
    effacerGeste();
    m_brouillon.insert(classe, entrees);
    m_refus.remove(classe);
    publierClasses();
    emit routageChange();
}

void RoutageViewModel::retirerEntree(const QString &classe, int rang)
{
    auto entrees = m_brouillon.find(classe);
    if (entrees == m_brouillon.end() || rang < 0 || rang >= entrees->size()) {
        return;
    }
    effacerGeste();
    entrees->removeAt(rang);
    m_refus.remove(classe); // les rangs ont bougé : les refus de cette classe ne valent plus
    publierClasses();
    emit routageChange();
}

void RoutageViewModel::revenir()
{
    effacerGeste();
    rebatirBrouillon();
    publierClasses();
    emit routageChange();
}

// --- Gestes envoyés au greffon -------------------------------------------------------------------

void RoutageViewModel::apresGeste()
{
    m_sondage->lireMaintenant();
}

void RoutageViewModel::valider()
{
    if (gesteEnCours()) {
        return;
    }
    if (!m_lue || brouillonVide()) {
        echouerGeste(QStringLiteral("La table est vide : appliquez une suggestion, ou modifiez la table dans le navigateur."));
        return;
    }
    QJsonObject classes;
    for (auto it = m_brouillon.cbegin(); it != m_brouillon.cend(); ++it) {
        if (!it.value().isEmpty()) {
            classes.insert(it.key(), it.value());
        }
    }
    debuterGeste();
    ApiCall *appel = m_greffon->validerRoutage(m_relevesDuBrouillon, classes);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        m_rebatir = true;
        const QJsonObject vue = reponse.json.object();
        if (vue.contains(QStringLiteral("classes"))) {
            lire(vue);
        }
        terminerGeste(QStringLiteral("Table validée."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        if (erreur.code() == QLatin1String("table_refusee")) {
            // Rien n'est enregistré : chaque refus est rendu à sa ligne, le brouillon reste.
            m_refus.clear();
            m_refusTexte.clear();
            for (const QJsonValue &element : erreur.refusals()) {
                const QJsonObject refus = element.toObject();
                const QString classe = refus.value(QStringLiteral("classe")).toString();
                const QString message = libelles::texte(refus.value(QStringLiteral("message")));
                const QJsonValue rang = refus.value(QStringLiteral("rang"));
                if (estEntier(rang)) {
                    m_refus[classe].insert(rang.toInt(), message);
                }
                m_refusTexte.append(QStringLiteral("%1, entrée %2 : %3")
                                        .arg(classe.isEmpty() ? libelles::kInconnu : libelleClasse(classe),
                                             estEntier(rang) ? QString::number(rang.toInt() + 1) : libelles::kInconnu,
                                             message));
            }
            publierClasses();
            emit routageChange();
            echouerGeste(erreur);
            return;
        }
        if (erreur.code() == QLatin1String("releve_change")) {
            // Un relevé a changé depuis la lecture : la table est relue et le brouillon rebâti.
            m_rebatir = true;
        }
        echouerGeste(erreur);
        apresGeste();
    });
}

void RoutageViewModel::accepterReleve(const QString &voie)
{
    if (gesteEnCours()) {
        return;
    }
    const QJsonObject catalogue = m_vue.value(QStringLiteral("voies")).toObject().value(voie).toObject();
    if (!construireListe(voie, catalogue).value(QStringLiteral("peutAccepter")).toBool()) {
        echouerGeste(QStringLiteral("Le greffon ne propose pas d'accepter ce relevé."));
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->accepterReleve(catalogue.value(QStringLiteral("releve_id")).toInteger());
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &reponse) {
        const QJsonObject vue = reponse.json.object();
        if (vue.contains(QStringLiteral("classes"))) {
            lire(vue);
        }
        terminerGeste(QStringLiteral("Relevé accepté."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

void RoutageViewModel::desactiverSurcharge(const QString &identifiant)
{
    if (gesteEnCours()) {
        return;
    }
    debuterGeste();
    ApiCall *appel = m_greffon->desactiverSurcharge(identifiant);
    connect(appel, &ApiCall::succeeded, this, [this](const ApiResponse &) {
        terminerGeste(QStringLiteral("Surcharge désactivée."));
        apresGeste();
    });
    connect(appel, &ApiCall::failed, this, [this](const ApiError &erreur) {
        echouerGeste(erreur);
        apresGeste();
    });
}

bool RoutageViewModel::modifierDansLeNavigateur()
{
    // Page Poste du tableau de bord, vue « routage » (apps/interface/src/poste/vue.ts), sous le
    // préfixe éventuel du serveur, comme l'API (ApiClient::resolve).
    QUrlQuery vue;
    vue.addQueryItem(QStringLiteral("vue"), QStringLiteral("routage"));
    const QUrl url = m_client->resolve(QStringLiteral("/poste"), vue);
    if (url.isEmpty()) {
        echouerGeste(QStringLiteral("Aucune adresse de serveur n'est configurée."));
        return false;
    }
    if (!m_ouvreur || !m_ouvreur(url)) {
        echouerGeste(QStringLiteral("Le navigateur du système n'a pas pu être ouvert : %1").arg(url.toString()));
        return false;
    }
    terminerGeste(QStringLiteral("Vue Routage du tableau de bord ouverte dans le navigateur."));
    return true;
}

} // namespace acp
