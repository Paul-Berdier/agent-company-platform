#include "viewmodels/CatalogueViewModel.h"

#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"

#include <QClipboard>
#include <QDesktopServices>
#include <QFile>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QSet>

namespace acp {
namespace {
QString texte(const QJsonObject &objet, const QString &cle, int maximum = 4000)
{
    const QJsonValue valeur = objet.value(cle);
    return valeur.isString() ? valeur.toString().trimmed().left(maximum) : QString();
}
QStringList chaines(const QJsonValue &valeur)
{
    QStringList resultat;
    for (const auto &v : valeur.toArray())
        if (v.isString() && !v.toString().trimmed().isEmpty()) resultat.append(v.toString().left(500));
    return resultat;
}
bool nomValide(const QString &nom)
{
    static const QRegularExpression forme(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9._/-]{0,149}$"));
    return forme.match(nom).hasMatch() && !nom.contains(QStringLiteral(".."));
}
QString urlSure(const QString &texte)
{
    const QUrl url(texte, QUrl::StrictMode);
    return CatalogueViewModel::urlSourceAdmise(url) ? url.toString(QUrl::FullyEncoded) : QString();
}
void etatSkill(QJsonObject &ligne, const QString &etat)
{
    QString libelle = QStringLiteral("État inconnu"), cle = QStringLiteral("unknown");
    if (etat == QLatin1String("active")) { libelle = QStringLiteral("Texte chargé"); cle = QStringLiteral("succeeded"); }
    else if (etat == QLatin1String("desactivee")) { libelle = QStringLiteral("Texte désactivé"); cle = QStringLiteral("pending"); }
    else if (etat == QLatin1String("absente")) { libelle = QStringLiteral("Texte absent"); cle = QStringLiteral("notConfigured"); }
    else if (etat == QLatin1String("ambigue")) { libelle = QStringLiteral("Collision de textes"); cle = QStringLiteral("degraded"); }
    else if (etat == QLatin1String("candidate-poste")) { libelle = QStringLiteral("Candidat exécutant"); cle = QStringLiteral("pending"); }
    else if (etat == QLatin1String("hors-v1")) { libelle = QStringLiteral("Hors périmètre installé"); cle = QStringLiteral("pending"); }
    ligne.insert(QStringLiteral("etat"), etat);
    ligne.insert(QStringLiteral("etatLibelle"), libelle);
    ligne.insert(QStringLiteral("cle"), cle);
}
QJsonObject sourceDe(const QJsonObject &catalogue, const QString &source)
{
    return catalogue.value(QStringLiteral("sources")).toObject().value(source).toObject();
}
}

CatalogueViewModel::CatalogueViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent)
    : PageViewModel(flux, parent)
    , m_sondage(new Sondage([greffon] { return greffon->catalogue(); }, std::chrono::seconds(60), this))
    , m_entrees(new JsonListModel(this))
    , m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); })
    , m_presse([](const QString &texte) {
        auto *presse = QGuiApplication::clipboard();
        if (!presse) return false;
        presse->setText(texte);
        return presse->text() == texte;
    })
{
    QFile fichier(QStringLiteral(":/integrations/sources.json"));
    if (fichier.open(QIODevice::ReadOnly)) {
        m_registre = QJsonDocument::fromJson(fichier.readAll()).object().value(QStringLiteral("sources")).toArray();
    }
    m_entrees->setCle({QStringLiteral("id")});
    m_toutes = construireEntrees({}, m_registre);
    filtrer();
    m_sondage->suivre(flux->invalidation(), {});
    suivreCadence(m_sondage);
    connect(m_sondage, &Sondage::etatChange, this, &CatalogueViewModel::lectureChange);
    connect(m_sondage, &Sondage::lu, this, [this](const ApiResponse &reponse) {
        const QJsonObject document = reponse.json.object();
        if (!catalogueValide(document)) {
            m_erreurSchema = QStringLiteral("Catalogue illisible : les derniers états connus sont conservés, sans nouvelle confirmation.");
            emit lectureChange();
            return;
        }
        m_erreurSchema.clear();
        m_lue = true;
        m_luA = QDateTime::currentDateTime();
        m_alertes = chaines(document.value(QStringLiteral("alertes")));
        m_toutes = construireEntrees(document, m_registre);
        filtrer();
        emit lectureChange();
    });
}
CatalogueViewModel::~CatalogueViewModel() = default;
bool CatalogueViewModel::chargement() const { return m_sondage->enCours(); }
QString CatalogueViewModel::lecture() const
{
    return m_luA.isValid() ? QStringLiteral("Lu à %1").arg(m_luA.toString(QStringLiteral("HH:mm:ss")))
                           : QStringLiteral("Catalogue serveur non lu");
}
QString CatalogueViewModel::erreur() const
{
    return !m_sondage->derniereErreur().isEmpty() ? m_sondage->derniereErreur() : m_erreurSchema;
}
void CatalogueViewModel::surActivite(bool actif) { m_sondage->setActif(actif); }
void CatalogueViewModel::surLienRetabli() { if (actif()) m_sondage->lireMaintenant(); }
void CatalogueViewModel::actualiser() { if (actif()) m_sondage->lireMaintenant(); }
void CatalogueViewModel::surOubli()
{
    m_sondage->setActif(false);
    m_sondage->oublier();
    m_lue = false;
    m_luA = {};
    m_alertes.clear();
    m_erreurSchema.clear();
    m_selection.clear();
    m_recherche.clear();
    m_typeFiltre = QStringLiteral("tous");
    m_toutes = construireEntrees({}, m_registre);
    filtrer();
    emit filtresChange();
    emit lectureChange();
}
void CatalogueViewModel::setRecherche(const QString &texte)
{
    const QString borne = texte.left(300);
    if (m_recherche == borne) return;
    m_recherche = borne; filtrer(); emit filtresChange();
}
void CatalogueViewModel::setTypeFiltre(const QString &type)
{
    if (type != QLatin1String("tous") && type != QLatin1String("skills")
        && type != QLatin1String("mcp") && type != QLatin1String("integrations")) return;
    if (type == m_typeFiltre) return;
    m_typeFiltre = type; filtrer(); emit filtresChange();
}
QJsonObject CatalogueViewModel::trouver(const QString &id) const
{
    for (const auto &valeur : m_toutes) {
        const auto ligne = valeur.toObject();
        if (ligne.value(QStringLiteral("id")) == id) return ligne;
    }
    return {};
}
QVariantMap CatalogueViewModel::selection() const { return trouver(m_selection).toVariantMap(); }
void CatalogueViewModel::selectionner(const QString &id)
{
    if (trouver(id).isEmpty()) return;
    m_selection = id; emit selectionChange();
}
void CatalogueViewModel::filtrer()
{
    QJsonArray visibles;
    const auto mots = m_recherche.trimmed().split(QRegularExpression(QStringLiteral("\\s+")), Qt::SkipEmptyParts);
    for (const auto &v : m_toutes) {
        const auto ligne = v.toObject();
        if (m_typeFiltre != QLatin1String("tous") && ligne.value(QStringLiteral("type")) != m_typeFiltre) continue;
        const QString corpus = texte(ligne, QStringLiteral("nom")) + QLatin1Char(' ')
            + texte(ligne, QStringLiteral("description")) + QLatin1Char(' ')
            + texte(ligne, QStringLiteral("source")) + QLatin1Char(' ')
            + texte(ligne, QStringLiteral("profils")) + QLatin1Char(' ')
            + texte(ligne, QStringLiteral("etatLibelle"));
        bool correspond = true;
        for (const auto &mot : mots) if (!corpus.contains(mot, Qt::CaseInsensitive)) { correspond = false; break; }
        if (correspond) visibles.append(ligne);
    }
    m_entrees->setItems(visibles);
    if (!m_selection.isEmpty() && trouver(m_selection).isEmpty()) m_selection.clear();
    emit selectionChange();
}
bool CatalogueViewModel::urlSourceAdmise(const QUrl &url)
{
    return url.isValid() && url.scheme() == QLatin1String("https") && !url.host().isEmpty()
        && url.userInfo().isEmpty() && !url.hasQuery() && !url.hasFragment()
        && (url.port(-1) == -1 || url.port(-1) == 443);
}
bool CatalogueViewModel::catalogueValide(const QJsonObject &catalogue)
{
    return catalogue.value(QStringLiteral("skills")).isArray()
        && catalogue.value(QStringLiteral("mcp")).isArray()
        && catalogue.value(QStringLiteral("sources")).isObject();
}
QJsonArray CatalogueViewModel::construireEntrees(const QJsonObject &catalogue, const QJsonArray &registre)
{
    QJsonArray lignes;
    QSet<QString> ids;
    const auto ajouter = [&lignes, &ids](const QJsonObject &ligne) {
        const QString id = texte(ligne, QStringLiteral("id"));
        if (!id.isEmpty() && !ids.contains(id)) { ids.insert(id); lignes.append(ligne); }
    };
    for (const auto &v : catalogue.value(QStringLiteral("skills")).toArray()) {
        const auto entree = v.toObject();
        const QString nom = texte(entree, QStringLiteral("nom"), 150);
        if (!nomValide(nom)) continue;
        const QString source = texte(entree, QStringLiteral("source"));
        const auto provenance = sourceDe(catalogue, source);
        const QString etat = texte(entree, QStringLiteral("etat"));
        const QString cible = texte(entree, QStringLiteral("cible"));
        QJsonObject ligne{{QStringLiteral("id"), QStringLiteral("skill:") + nom},
            {QStringLiteral("type"), QStringLiteral("skills")}, {QStringLiteral("genre"), QStringLiteral("Skill")},
            {QStringLiteral("nom"), nom}, {QStringLiteral("source"), source},
            {QStringLiteral("description"), texte(entree, QStringLiteral("description_fr"))},
            {QStringLiteral("raison"), texte(entree, QStringLiteral("raison"))},
            {QStringLiteral("url"), urlSure(texte(provenance, QStringLiteral("url")))},
            {QStringLiteral("licence"), texte(provenance, QStringLiteral("licence"))},
            {QStringLiteral("commit"), texte(provenance, QStringLiteral("commit"))},
            {QStringLiteral("profils"), chaines(entree.value(QStringLiteral("profils"))).join(QStringLiteral(", "))},
            {QStringLiteral("cible"), cible == QLatin1String("hermes") ? QStringLiteral("Coordinateur Hermes") : QStringLiteral("Exécutant")},
            {QStringLiteral("frontiere"), QStringLiteral("État du texte selon le catalogue Hermes. Aucun service externe ni compte fournisseur n'est confirmé par cet état.")},
            {QStringLiteral("peutConsigne"), etat == QLatin1String("active") && cible == QLatin1String("hermes")}};
        etatSkill(ligne, etat); ajouter(ligne);
    }
    for (const auto &v : catalogue.value(QStringLiteral("mcp")).toArray()) {
        const auto entree = v.toObject();
        const QString nom = texte(entree, QStringLiteral("nom"), 150);
        if (!nomValide(nom)) continue;
        const QString connexion = texte(entree, QStringLiteral("connexion"));
        const bool distant = texte(entree, QStringLiteral("cible")) == QLatin1String("hermes");
        const bool confirme = distant && connexion == QLatin1String("connecte");
        QJsonObject ligne{{QStringLiteral("id"), QStringLiteral("mcp:") + nom},
            {QStringLiteral("type"), QStringLiteral("mcp")}, {QStringLiteral("genre"), QStringLiteral("Serveur MCP")},
            {QStringLiteral("nom"), nom}, {QStringLiteral("source"), QStringLiteral("Catalogue Hermes")},
            {QStringLiteral("description"), texte(entree, QStringLiteral("description_fr"))},
            {QStringLiteral("raison"), texte(entree, QStringLiteral("raison"))},
            {QStringLiteral("url"), urlSure(texte(entree, QStringLiteral("url")))},
            {QStringLiteral("profils"), chaines(entree.value(QStringLiteral("profils"))).join(QStringLiteral(", "))},
            {QStringLiteral("cible"), distant ? QStringLiteral("Coordinateur Hermes") : QStringLiteral("Exécutant")},
            {QStringLiteral("etat"), confirme ? QStringLiteral("connecte") : QStringLiteral("inconnu")},
            {QStringLiteral("etatLibelle"), confirme ? QStringLiteral("Connexion confirmée par Hermes")
                : connexion == QLatin1String("hors_ligne") ? QStringLiteral("Hors ligne selon Hermes") : QStringLiteral("Connexion non confirmée")},
            {QStringLiteral("cle"), confirme ? QStringLiteral("succeeded") : QStringLiteral("unknown")},
            {QStringLiteral("frontiere"), QStringLiteral("Transport : %1. Outils admis : %2. La disponibilité vient de Hermes, pas du registre local.")
                .arg(texte(entree, QStringLiteral("transport")), chaines(entree.value(QStringLiteral("outils_hermes"))).join(QStringLiteral(", ")))},
            {QStringLiteral("peutConsigne"), false}};
        ajouter(ligne);
    }
    for (const auto &v : registre) {
        const auto entree = v.toObject();
        const QString id = texte(entree, QStringLiteral("id"), 150);
        if (!nomValide(id)) continue;
        const QString source = texte(entree, QStringLiteral("source"));
        const QString mode = texte(entree, QStringLiteral("mode"));
        const bool textes = mode == QLatin1String("textes");
        QStringList charges;
        for (const auto &skill : catalogue.value(QStringLiteral("skills")).toArray()) {
            const auto s = skill.toObject();
            if (texte(s, QStringLiteral("source")) == source && texte(s, QStringLiteral("etat")) == QLatin1String("active"))
                charges.append(texte(s, QStringLiteral("nom")));
        }
        QJsonObject ligne = entree;
        ligne.insert(QStringLiteral("id"), QStringLiteral("integration:") + id);
        ligne.insert(QStringLiteral("type"), QStringLiteral("integrations"));
        ligne.insert(QStringLiteral("genre"), QStringLiteral("Source externe"));
        ligne.insert(QStringLiteral("url"), urlSure(texte(entree, QStringLiteral("url"))));
        ligne.insert(QStringLiteral("etat"), textes && !charges.isEmpty() ? QStringLiteral("textes-charges") : QStringLiteral("a-configurer"));
        ligne.insert(QStringLiteral("etatLibelle"), textes && !charges.isEmpty() ? QStringLiteral("Textes chargés selon Hermes")
                     : textes ? QStringLiteral("Textes non confirmés") : QStringLiteral("À configurer"));
        ligne.insert(QStringLiteral("cle"), textes && !charges.isEmpty() ? QStringLiteral("succeeded") : QStringLiteral("pending"));
        if (mode == QLatin1String("archive") || mode == QLatin1String("reference")) {
            ligne.insert(QStringLiteral("etat"), mode);
            ligne.insert(QStringLiteral("etatLibelle"), mode == QLatin1String("archive")
                ? QStringLiteral("Archivé · non installé") : QStringLiteral("Référence · exécution exclue"));
        }
        ligne.insert(QStringLiteral("observation"), charges.isEmpty()
            ? QStringLiteral("Aucun texte de cette source confirmé actif dans le catalogue lu.")
            : QStringLiteral("Textes chargés : %1. Cela ne confirme aucun runtime externe.").arg(charges.join(QStringLiteral(", "))));
        if (mode == QLatin1String("coffre")) {
            ligne.insert(QStringLiteral("genre"), QStringLiteral("Pont ACP · application facultative"));
            ligne.insert(QStringLiteral("etat"), QStringLiteral("a-verifier"));
            ligne.insert(QStringLiteral("etatLibelle"), QStringLiteral("État à lire dans Coffre ACP"));
            ligne.insert(QStringLiteral("observation"), QStringLiteral("L’association et la disponibilité se vérifient sur la page Coffre ACP auprès de Hermes."));
        }
        ligne.insert(QStringLiteral("peutConsigne"), mode != QLatin1String("coffre"));
        ajouter(ligne);
    }
    return lignes;
}
bool CatalogueViewModel::ouvrirSource(const QString &id)
{
    const QString adresse = texte(trouver(id), QStringLiteral("url"));
    if (adresse.isEmpty() || !urlSourceAdmise(QUrl(adresse))) return false;
    if (!m_ouvreur || !m_ouvreur(QUrl(adresse))) {
        echouerGeste(QStringLiteral("Le navigateur n'a pas ouvert la source.")); return false;
    }
    terminerGeste(QStringLiteral("Source ouverte dans le navigateur.")); return true;
}
bool CatalogueViewModel::copierConfiguration(const QString &id)
{
    const QString configuration = texte(trouver(id), QStringLiteral("configuration"), 16000);
    if (configuration.isEmpty()) return false;
    if (!m_presse || !m_presse(configuration)) {
        echouerGeste(QStringLiteral("La fiche de configuration n'a pas pu être copiée.")); return false;
    }
    terminerGeste(QStringLiteral("Fiche de configuration copiée. Rien n'a été installé ni connecté.")); return true;
}
QString CatalogueViewModel::consignePour(const QString &id) const
{
    const QJsonObject entree = trouver(id);
    if (!entree.value(QStringLiteral("peutConsigne")).toBool()) return {};
    if (entree.value(QStringLiteral("type")) == QLatin1String("skills")) {
        if (!m_lue || !erreur().isEmpty() || !flux()->sessionOuverte()) return {};
        return QStringLiteral("Pour ma demande suivante, utilise la skill « %1 » du catalogue Hermes, dans son périmètre autorisé. "
                              "Distingue ce que tu observes de ce qui reste à vérifier et demande les informations manquantes avant toute action externe.")
            .arg(texte(entree, QStringLiteral("nom")));
    }
    return QStringLiteral("Prépare avec moi l'utilisation de %1 pour mon projet. Objectif à préciser : …\n"
                          "Périmètre : %2\nÉtat : %3. N'installe rien, ne connecte aucun compte et n'exécute aucun service sans un choix explicite. "
                          "Commence par les prérequis manquants et le travail réellement disponible dans le catalogue.")
        .arg(texte(entree, QStringLiteral("nom")), texte(entree, QStringLiteral("frontiere")), texte(entree, QStringLiteral("etatLibelle")));
}
} // namespace acp
