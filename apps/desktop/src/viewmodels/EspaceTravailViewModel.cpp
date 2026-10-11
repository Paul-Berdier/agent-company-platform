#include "viewmodels/EspaceTravailViewModel.h"

#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "events/Sondage.h"
#include "models/JsonListModel.h"
#include "navigation/NavigationModel.h"
#include "viewmodels/Libelles.h"
#include "viewmodels/ProjetsViewModel.h"

#include <QJsonDocument>
#include <QMap>

#include <algorithm>
#include <functional>

namespace acp {

namespace {

const QString kSansDepot = QStringLiteral("Sans dépôt");

//! Rang d'affichage d'une mission dans son groupe : active, en pause, puis archivée.
int rangEtat(const QString &etat)
{
    if (etat == QLatin1String("actif") || etat == QLatin1String("creation")) return 0;
    if (etat == QLatin1String("en_pause")) return 1;
    return 2;
}

bool archivee(const QString &etat)
{
    return etat == QLatin1String("termine") || etat == QLatin1String("abandonne");
}

//! Comparaison sans casse ni accents, pour la recherche.
QString plier(const QString &texte)
{
    QString normal = texte.normalized(QString::NormalizationForm_D).toCaseFolded();
    normal.removeIf([](QChar c) { return c.category() == QChar::Mark_NonSpacing; });
    return normal;
}

//! Rang d'une carte dans la mission (même ordre que la page Projets).
int rangRole(const QString &role)
{
    static const QStringList ordre = {QStringLiteral("exploration"), QStringLiteral("planification"),
                                      QStringLiteral("implementation"), QStringLiteral("correction"),
                                      QStringLiteral("integration"), QStringLiteral("relecture"),
                                      QStringLiteral("hermes"), QStringLiteral("repondre"),
                                      QStringLiteral("triage"), QStringLiteral("synthese")};
    const auto rang = ordre.indexOf(role);
    return rang < 0 ? static_cast<int>(ordre.size()) : static_cast<int>(rang);
}

QJsonObject objetDuDetail(const QJsonValue &detail)
{
    if (detail.isObject()) return detail.toObject();
    if (!detail.isString()) return {};
    const QJsonDocument document = QJsonDocument::fromJson(detail.toString().toUtf8());
    return document.isObject() ? document.object() : QJsonObject();
}

//! FNV-1a 32 bits : stable d'une exécution à l'autre (qHash est salé par processus).
quint32 empreinte(const QString &cle)
{
    quint32 h = 2166136261u;
    for (const char octet : cle.toUtf8()) {
        h ^= static_cast<quint8>(octet);
        h *= 16777619u;
    }
    return h;
}

} // namespace

EspaceTravailViewModel::EspaceTravailViewModel(ClientGreffonPoste *greffon, EventStreamService *flux,
                                               ProjetsViewModel *projets, NavigationModel *navigation,
                                               QObject *parent)
    : PageViewModel(flux, parent)
    , m_projets(projets)
    , m_navigation(navigation)
    , m_liste(new Sondage([greffon] { return greffon->projets(); }, Sondage::kIntervallePage, this))
    , m_arbre(new JsonListModel(this))
    , m_agents(new JsonListModel(this))
    , m_essais(new JsonListModel(this))
    , m_sorties(new JsonListModel(this))
{
    // Lignes relues par clé : la barre garde son défilement, ses délégués et ses dépliages.
    m_arbre->setCle({QStringLiteral("cle")});
    m_agents->setCle({QStringLiteral("cle")});
    m_essais->setCle({QStringLiteral("cle")});
    m_sorties->setCle({QStringLiteral("cle")});
    // Mêmes sujets que la liste de la page Projets (le flux ne porte que des noms de sujets).
    m_liste->suivre(flux->invalidation(), {QStringLiteral("projets"), QStringLiteral("questions"),
                                           QStringLiteral("poste"), QStringLiteral("pause")});
    suivreCadence(m_liste);
    connect(m_liste, &Sondage::etatChange, this, &EspaceTravailViewModel::lectureChange);
    connect(m_liste, &Sondage::lu, this, [this](const ApiResponse &reponse) { lireListe(reponse.json.object()); });
    connect(m_projets, &ProjetsViewModel::detailChange, this, &EspaceTravailViewModel::lireDetail);
    connect(m_projets, &ProjetsViewModel::vueChange, this, [this] {
        // La page Projets peut ouvrir une autre mission (lien, palette) : la sélection la suit.
        const QString ouvert = m_projets->vue() == QLatin1String("detail") ? m_projets->projetOuvert() : QString();
        if (ouvert != m_missionSelectionnee) {
            m_missionSelectionnee = ouvert;
            reconstruireArbre();
            emit selectionChange();
        }
    });
}

EspaceTravailViewModel::~EspaceTravailViewModel() = default;

QString EspaceTravailViewModel::lecture() const { return m_liste->libelleLuA(); }
QString EspaceTravailViewModel::erreur() const { return m_liste->derniereErreur(); }

void EspaceTravailViewModel::surActivite(bool actif)
{
    m_liste->setActif(actif);
}

void EspaceTravailViewModel::surLienRetabli()
{
    m_liste->lireMaintenant();
}

void EspaceTravailViewModel::surOubli()
{
    m_liste->oublier();
    m_projetsLus = {};
    m_listeLue = false;
    m_nombreMissions = 0;
    m_nombreProjets = 0;
    m_recherche.clear();
    m_replies.clear();
    m_archivesOuvertes.clear();
    m_missionSelectionnee.clear();
    m_mission.clear();
    m_agentSelectionne.clear();
    m_brouillons.clear();
    m_arbre->clear();
    m_agents->clear();
    m_essais->clear();
    m_sorties->clear();
    emit arbreChange();
    emit selectionChange();
    emit missionChange();
    emit agentChange();
    emit brouillonChange(QString());
}

void EspaceTravailViewModel::setRecherche(const QString &recherche)
{
    if (recherche == m_recherche) return;
    m_recherche = recherche;
    reconstruireArbre();
}

void EspaceTravailViewModel::lireListe(const QJsonObject &liste)
{
    QJsonArray projets;
    for (const QJsonValue &element : liste.value(QStringLiteral("projets")).toArray()) {
        if (ClientGreffonPoste::identifiantValide(element.toObject().value(QStringLiteral("id")).toString())) {
            projets.append(element);
        }
    }
    m_projetsLus = projets;
    m_listeLue = true;
    reconstruireArbre();
}

void EspaceTravailViewModel::reconstruireArbre()
{
    const QJsonArray lignes = construireArbre(m_projetsLus, m_recherche, m_replies, m_archivesOuvertes,
                                              m_missionSelectionnee);
    m_arbre->setItems(lignes);
    QSet<QString> depots;
    for (const QJsonValue &projet : std::as_const(m_projetsLus)) {
        const QJsonValue depot = projet.toObject().value(QStringLiteral("depot"));
        depots.insert(libelles::estTexte(depot) ? depot.toString() : QString());
    }
    m_nombreMissions = static_cast<int>(m_projetsLus.size());
    m_nombreProjets = static_cast<int>(depots.size());
    emit arbreChange();
}

QJsonArray EspaceTravailViewModel::construireArbre(const QJsonArray &projets, const QString &recherche,
                                                   const QSet<QString> &replies,
                                                   const QSet<QString> &archivesOuvertes, const QString &selection)
{
    const QString filtre = plier(recherche.trimmed());
    struct Groupe
    {
        QString depot;
        QList<QJsonObject> missions;
        double recent = 0;
        bool actif = false;
    };
    QMap<QString, Groupe> groupes;
    for (const QJsonValue &element : projets) {
        const QJsonObject projet = element.toObject();
        const QJsonValue depotBrut = projet.value(QStringLiteral("depot"));
        const QString depot = libelles::estTexte(depotBrut) ? depotBrut.toString() : QString();
        const QString titre = libelles::texte(projet.value(QStringLiteral("titre")));
        if (!filtre.isEmpty() && !plier(titre).contains(filtre)
            && !plier(depot.isEmpty() ? kSansDepot : depot).contains(filtre)) {
            continue;
        }
        Groupe &groupe = groupes[depot];
        groupe.depot = depot;
        groupe.missions.append(projet);
        groupe.recent = std::max(groupe.recent, projet.value(QStringLiteral("cree_le")).toDouble());
        groupe.actif = groupe.actif || rangEtat(projet.value(QStringLiteral("etat")).toString()) == 0;
    }
    QList<Groupe> ordonnes = groupes.values();
    // Groupes ayant une mission active d'abord, puis du plus récent au plus ancien ; « Sans dépôt » à rang égal.
    std::stable_sort(ordonnes.begin(), ordonnes.end(), [](const Groupe &a, const Groupe &b) {
        if (a.actif != b.actif) return a.actif;
        return a.recent > b.recent;
    });

    QJsonArray lignes;
    for (Groupe &groupe : ordonnes) {
        std::stable_sort(groupe.missions.begin(), groupe.missions.end(), [](const QJsonObject &a, const QJsonObject &b) {
            const int ra = rangEtat(a.value(QStringLiteral("etat")).toString());
            const int rb = rangEtat(b.value(QStringLiteral("etat")).toString());
            if (ra != rb) return ra < rb;
            return a.value(QStringLiteral("cree_le")).toDouble() > b.value(QStringLiteral("cree_le")).toDouble();
        });
        const QString cleGroupe = QStringLiteral("g:") + groupe.depot;
        const QString cleArchives = QStringLiteral("a:") + groupe.depot;
        int actives = 0;
        int questions = 0;
        int archives = 0;
        for (const QJsonObject &mission : std::as_const(groupe.missions)) {
            const QString etat = mission.value(QStringLiteral("etat")).toString();
            actives += rangEtat(etat) == 0 ? 1 : 0;
            archives += archivee(etat) ? 1 : 0;
            questions += std::max(0, mission.value(QStringLiteral("questions_ouvertes")).toInt());
        }
        // Une recherche déplie tout : ce qui correspond doit se voir.
        const bool deplie = !filtre.isEmpty() || !replies.contains(cleGroupe);
        const QVariantMap picto = pictogramme(cleGroupe);
        lignes.append(QJsonObject{
            {QStringLiteral("cle"), cleGroupe},
            {QStringLiteral("type"), QStringLiteral("groupe")},
            {QStringLiteral("niveau"), 0},
            {QStringLiteral("depot"), groupe.depot},
            {QStringLiteral("libelle"), groupe.depot.isEmpty() ? kSansDepot : groupe.depot},
            {QStringLiteral("missions"), static_cast<int>(groupe.missions.size())},
            {QStringLiteral("actives"), actives},
            {QStringLiteral("questions"), questions},
            {QStringLiteral("deplie"), deplie},
            {QStringLiteral("motif"), picto.value(QStringLiteral("motif")).toString()},
            {QStringLiteral("teinte"), picto.value(QStringLiteral("teinte")).toString()},
        });
        if (!deplie) {
            continue;
        }
        const bool archivesVisibles = !filtre.isEmpty() || archivesOuvertes.contains(cleArchives);
        bool ligneArchivesPosee = false;
        for (const QJsonObject &mission : std::as_const(groupe.missions)) {
            const QString etat = mission.value(QStringLiteral("etat")).toString();
            if (archivee(etat) && !ligneArchivesPosee) {
                ligneArchivesPosee = true;
                lignes.append(QJsonObject{
                    {QStringLiteral("cle"), cleArchives},
                    {QStringLiteral("type"), QStringLiteral("archives")},
                    {QStringLiteral("niveau"), 1},
                    {QStringLiteral("depot"), groupe.depot},
                    {QStringLiteral("libelle"), archives == 1 ? QStringLiteral("1 mission archivée")
                                                              : QStringLiteral("%1 missions archivées").arg(archives)},
                    {QStringLiteral("deplie"), archivesVisibles},
                });
            }
            if (archivee(etat) && !archivesVisibles) {
                continue;
            }
            const QString identifiant = mission.value(QStringLiteral("id")).toString();
            const libelles::Libelle libelle = libelles::etatProjet(mission.value(QStringLiteral("etat")),
                                                                   mission.value(QStringLiteral("etat_derive")));
            const QJsonObject compteurs = mission.value(QStringLiteral("compteurs")).toObject();
            const QVariantMap pictoMission = pictogramme(identifiant);
            const QJsonValue faites = compteurs.value(QStringLiteral("faites"));
            const QJsonValue total = compteurs.value(QStringLiteral("total"));
            lignes.append(QJsonObject{
                {QStringLiteral("cle"), QStringLiteral("m:") + identifiant},
                {QStringLiteral("type"), QStringLiteral("mission")},
                {QStringLiteral("niveau"), 1},
                {QStringLiteral("id"), identifiant},
                {QStringLiteral("depot"), groupe.depot},
                {QStringLiteral("libelle"), libelles::texte(mission.value(QStringLiteral("titre")))},
                {QStringLiteral("etat"), etat},
                {QStringLiteral("etatLibelle"), libelle.connu() ? libelle.texte : libelles::texte(mission.value(QStringLiteral("etat")))},
                {QStringLiteral("etatCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
                {QStringLiteral("questions"), std::max(0, mission.value(QStringLiteral("questions_ouvertes")).toInt())},
                {QStringLiteral("bloquees"), std::max(0, compteurs.value(QStringLiteral("bloquees")).toInt())},
                {QStringLiteral("progression"), libelles::estNombre(faites) && libelles::estNombre(total)
                                                    ? QStringLiteral("%1/%2").arg(faites.toInteger()).arg(total.toInteger())
                                                    : QString()},
                {QStringLiteral("archivee"), archivee(etat)},
                {QStringLiteral("selectionnee"), identifiant == selection},
                {QStringLiteral("motif"), pictoMission.value(QStringLiteral("motif")).toString()},
                {QStringLiteral("teinte"), pictoMission.value(QStringLiteral("teinte")).toString()},
            });
        }
    }
    return lignes;
}

void EspaceTravailViewModel::basculer(const QString &cle)
{
    if (cle.startsWith(QStringLiteral("g:"))) {
        if (!m_replies.remove(cle)) m_replies.insert(cle);
    } else if (cle.startsWith(QStringLiteral("a:"))) {
        if (!m_archivesOuvertes.remove(cle)) m_archivesOuvertes.insert(cle);
    } else {
        return;
    }
    reconstruireArbre();
}

void EspaceTravailViewModel::selectionnerMission(const QString &identifiant)
{
    if (!ClientGreffonPoste::identifiantValide(identifiant)) {
        return;
    }
    m_navigation->setCurrentRoute(QStringLiteral("projects"));
    m_projets->ouvrirProjet(identifiant);
    if (m_missionSelectionnee != identifiant) {
        m_missionSelectionnee = identifiant;
        m_agentSelectionne.clear();
        reconstruireArbre();
        emit selectionChange();
        emit agentChange();
    }
    lireDetail();
}

void EspaceTravailViewModel::nouvelleMission(const QString &depot)
{
    m_navigation->setCurrentRoute(QStringLiteral("projects"));
    m_projets->afficherNouveau();
    if (!depot.isEmpty()) {
        m_projets->choisirDepot(depot);
    }
}

QString EspaceTravailViewModel::brouillon(const QString &contexte) const
{
    return m_brouillons.value(contexte);
}

void EspaceTravailViewModel::noterBrouillon(const QString &contexte, const QString &texte)
{
    if (contexte.isEmpty() || m_brouillons.value(contexte) == texte) return;
    if (texte.isEmpty()) {
        m_brouillons.remove(contexte);
    } else {
        m_brouillons.insert(contexte, texte);
    }
    emit brouillonChange(contexte);
}

QVariantMap EspaceTravailViewModel::pictogramme(const QString &cle)
{
    // Mêmes listes que design/pixel/manifeste.json (listes.motifs, planche pictogrammes).
    static const QStringList motifs = {QStringLiteral("fusee"), QStringLiteral("cristal"), QStringLiteral("feuille"),
                                       QStringLiteral("livre"), QStringLiteral("eclair"), QStringLiteral("planete"),
                                       QStringLiteral("engrenage")};
    static const QStringList teintes = {QStringLiteral("lavande"), QStringLiteral("menthe"), QStringLiteral("ambre"),
                                        QStringLiteral("rose"), QStringLiteral("ciel")};
    const quint32 h = empreinte(cle);
    return {{QStringLiteral("motif"), motifs.at(static_cast<int>(h % motifs.size()))},
            {QStringLiteral("teinte"), teintes.at(static_cast<int>((h / motifs.size()) % teintes.size()))}};
}

// --- Détail de la mission ouverte -----------------------------------------------------------

void EspaceTravailViewModel::lireDetail()
{
    const QJsonObject projet = m_projets->detailLu() ? m_projets->projetBrut() : QJsonObject();
    const bool memeMission = projet.value(QStringLiteral("id")).toString() == m_missionSelectionnee;
    const QJsonObject lu = memeMission ? projet : QJsonObject();
    m_agents->setItems(construireAgents(lu));
    m_essais->setItems(construireEssais(lu));
    m_sorties->setItems(construireSorties(lu));
    QVariantMap mission;
    if (!lu.isEmpty()) {
        const libelles::Libelle libelle = libelles::etatProjet(lu.value(QStringLiteral("etat")),
                                                               lu.value(QStringLiteral("etat_derive")));
        const QJsonValue depot = lu.value(QStringLiteral("depot"));
        mission = {
            {QStringLiteral("id"), lu.value(QStringLiteral("id")).toString()},
            {QStringLiteral("titre"), libelles::texte(lu.value(QStringLiteral("titre")))},
            {QStringLiteral("depot"), libelles::estTexte(depot) ? depot.toString() : kSansDepot},
            {QStringLiteral("etatLibelle"), libelle.connu() ? libelle.texte : libelles::texte(lu.value(QStringLiteral("etat")))},
            {QStringLiteral("etatCle"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")},
            {QStringLiteral("agents"), m_agents->count()},
        };
    }
    m_mission = mission;
    emit missionChange();
    if (!m_agentSelectionne.isEmpty()) {
        bool present = false;
        for (int rang = 0; rang < m_agents->count() && !present; ++rang) {
            present = m_agents->itemAt(rang).value(QStringLiteral("cle")).toString() == m_agentSelectionne;
        }
        if (!present) m_agentSelectionne.clear();
    }
    emit agentChange();
}

void EspaceTravailViewModel::setAgentSelectionne(const QString &cle)
{
    if (cle == m_agentSelectionne) return;
    m_agentSelectionne = cle;
    emit agentChange();
}

QVariantMap EspaceTravailViewModel::agent() const
{
    for (int rang = 0; rang < m_agents->count(); ++rang) {
        if (m_agents->itemAt(rang).value(QStringLiteral("cle")).toString() == m_agentSelectionne) {
            return m_agents->get(rang);
        }
    }
    return {};
}

QJsonObject EspaceTravailViewModel::etatAgent(const QString &statut)
{
    // Correspondance des statuts kanban servis (Libelles.cpp, statutCarte) vers les états
    // d'agent du brief ; ce qui n'est pas observé (outil en cours, annulation demandée) n'apparaît pas.
    struct Etat { const char *cle; const char *libelle; const char *sprite; };
    static const QHash<QString, Etat> table = {
        {QStringLiteral("todo"), {"en_file", "En file", "repos"}},
        {QStringLiteral("ready"), {"en_file", "Prête, en file", "repos"}},
        {QStringLiteral("a_creer"), {"en_file", "À créer", "repos"}},
        {QStringLiteral("scheduled"), {"suspendue", "Suspendue (quota ou horaire)", "attente"}},
        {QStringLiteral("running"), {"execute", "Exécute", "travail"}},
        {QStringLiteral("review"), {"attend_decision", "Attend votre relecture", "attente"}},
        {QStringLiteral("triage"), {"attend_decision", "Attend votre décision", "attente"}},
        {QStringLiteral("blocked"), {"bloquee", "Bloquée", "echec"}},
        {QStringLiteral("done"), {"terminee", "Terminée", "termine"}},
        {QStringLiteral("archived"), {"arretee", "Archivée", "arrete"}},
    };
    const auto trouve = table.constFind(statut);
    const libelles::Libelle libelle = libelles::statutCarte(QJsonValue(statut));
    if (trouve == table.constEnd()) {
        return {{QStringLiteral("etat"), QStringLiteral("inconnu")},
                {QStringLiteral("etatLibelle"), statut.isEmpty() ? libelles::kInconnu : QStringLiteral("Inconnu (%1)").arg(statut)},
                {QStringLiteral("sprite"), QStringLiteral("repos")},
                {QStringLiteral("statusKey"), QStringLiteral("unknown")}};
    }
    return {{QStringLiteral("etat"), QString::fromLatin1(trouve->cle)},
            {QStringLiteral("etatLibelle"), QString::fromUtf8(trouve->libelle)},
            {QStringLiteral("sprite"), QString::fromLatin1(trouve->sprite)},
            {QStringLiteral("statusKey"), libelle.connu() ? libelle.cle : QStringLiteral("unknown")}};
}

QString EspaceTravailViewModel::portraitDuRole(const QString &role)
{
    if (role == QLatin1String("exploration")) return QStringLiteral("explorateur");
    if (role == QLatin1String("implementation") || role == QLatin1String("correction")
        || role == QLatin1String("integration")) {
        return QStringLiteral("developpeur");
    }
    if (role == QLatin1String("relecture")) return QStringLiteral("relecteur");
    if (role == QLatin1String("planification") || role == QLatin1String("synthese") || role == QLatin1String("hermes")
        || role == QLatin1String("repondre") || role == QLatin1String("triage")) {
        return QStringLiteral("coordinateur");
    }
    return QStringLiteral("inconnu");
}

QString EspaceTravailViewModel::libelleSourceRoutage(const QString &source)
{
    if (source == QLatin1String("table")) return QStringLiteral("Auto : table de routage");
    if (source == QLatin1String("profil")) return QStringLiteral("Auto : profil de Hermes");
    if (source == QLatin1String("choix_explicite")) return QStringLiteral("Choix manuel (verrou)");
    if (source == QLatin1String("surcharge_carte")) return QStringLiteral("Surcharge de la carte");
    if (source == QLatin1String("surcharge_projet")) return QStringLiteral("Surcharge de la mission");
    if (source == QLatin1String("surcharge_globale")) return QStringLiteral("Surcharge globale");
    if (source == QLatin1String("sans_objet")) return QStringLiteral("Sans objet");
    return source.isEmpty() ? libelles::kInconnu : source;
}

QJsonArray EspaceTravailViewModel::construireAgents(const QJsonObject &projet)
{
    if (projet.isEmpty()) {
        return {};
    }
    QList<QJsonObject> cartes;
    QSet<QString> identifiants;
    for (const QJsonValue &element : projet.value(QStringLiteral("cartes")).toArray()) {
        const QJsonObject carte = element.toObject();
        cartes.append(carte);
        const QString id = carte.value(QStringLiteral("carte")).toString();
        if (!id.isEmpty()) identifiants.insert(id);
    }
    std::stable_sort(cartes.begin(), cartes.end(), [](const QJsonObject &a, const QJsonObject &b) {
        const int ta = a.value(QStringLiteral("tour")).toInt();
        const int tb = b.value(QStringLiteral("tour")).toInt();
        if (ta != tb) return ta < tb;
        return rangRole(a.value(QStringLiteral("role")).toString()) < rangRole(b.value(QStringLiteral("role")).toString());
    });

    const QString etatMission = projet.value(QStringLiteral("etat")).toString();
    const libelles::Libelle libelleMission = libelles::etatProjet(projet.value(QStringLiteral("etat")),
                                                                  projet.value(QStringLiteral("etat_derive")));
    QString spriteMission = QStringLiteral("repos");
    if (etatMission == QLatin1String("termine")) spriteMission = QStringLiteral("termine");
    else if (etatMission == QLatin1String("en_pause") || etatMission == QLatin1String("abandonne")) spriteMission = QStringLiteral("arrete");

    QJsonArray lignes;
    // Racine : Hermes coordonne la mission (architecture : seul orchestrateur). Son état est celui de la mission.
    lignes.append(QJsonObject{
        {QStringLiteral("cle"), QStringLiteral("hermes")},
        {QStringLiteral("niveau"), 0},
        {QStringLiteral("parent"), QString()},
        {QStringLiteral("carte"), QString()},
        {QStringLiteral("titre"), QStringLiteral("Hermes")},
        {QStringLiteral("role"), QStringLiteral("coordination")},
        {QStringLiteral("roleLibelle"), QStringLiteral("Coordination de la mission")},
        {QStringLiteral("portrait"), QStringLiteral("coordinateur")},
        {QStringLiteral("etat"), etatMission.isEmpty() ? QStringLiteral("inconnu") : etatMission},
        {QStringLiteral("etatLibelle"), libelleMission.connu() ? libelleMission.texte : libelles::kInconnu},
        {QStringLiteral("statusKey"), libelleMission.connu() ? libelleMission.cle : QStringLiteral("unknown")},
        {QStringLiteral("sprite"), spriteMission},
        {QStringLiteral("voie"), QStringLiteral("hermes")},
        {QStringLiteral("voieLibelle"), libelles::voie(QJsonValue(QStringLiteral("hermes")))},
        {QStringLiteral("modele"), QString()},
        {QStringLiteral("modeleServi"), QString()},
        {QStringLiteral("effort"), QString()},
        {QStringLiteral("sourceRoutage"), QString()},
        {QStringLiteral("mention"), QString()},
        {QStringLiteral("tour"), QString()},
        {QStringLiteral("resume"), QString()},
    });

    const auto ligneCarte = [](const QJsonObject &carte, int niveau, const QString &parent, int rang) {
        const QString role = carte.value(QStringLiteral("role")).toString();
        const QString id = carte.value(QStringLiteral("carte")).toString();
        const QJsonObject etat = etatAgent(carte.value(QStringLiteral("statut")).toString());
        const QJsonValue effort = carte.value(QStringLiteral("effort"));
        const QJsonValue resume = carte.value(QStringLiteral("resume"));
        const QString source = carte.value(QStringLiteral("source_routage")).toString();
        // Une carte encore sans identifiant kanban (« à créer ») garde une clé stable : référence et tour.
        const QString cle = id.isEmpty() ? QStringLiteral("ref:%1:%2:%3")
                                               .arg(carte.value(QStringLiteral("ref")).toString())
                                               .arg(carte.value(QStringLiteral("tour")).toInt())
                                               .arg(rang)
                                         : id;
        QJsonObject ligne{
            {QStringLiteral("cle"), cle},
            {QStringLiteral("niveau"), niveau},
            {QStringLiteral("parent"), parent},
            {QStringLiteral("carte"), id},
            {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
            {QStringLiteral("role"), role},
            {QStringLiteral("roleLibelle"), libelles::role(QJsonValue(role)).isEmpty() ? role : libelles::role(QJsonValue(role))},
            {QStringLiteral("portrait"), portraitDuRole(role)},
            {QStringLiteral("voie"), carte.value(QStringLiteral("voie")).toString()},
            {QStringLiteral("voieLibelle"), libelles::voie(carte.value(QStringLiteral("voie"))).isEmpty()
                                                ? libelles::texte(carte.value(QStringLiteral("voie")))
                                                : libelles::voie(carte.value(QStringLiteral("voie")))},
            {QStringLiteral("modele"), libelles::texte(carte.value(QStringLiteral("modele")))},
            {QStringLiteral("modeleServi"), libelles::texte(carte.value(QStringLiteral("modele_servi")))},
            {QStringLiteral("effort"), libelles::estTexte(effort) ? effort.toString() : QStringLiteral("Par défaut")},
            {QStringLiteral("sourceRoutage"), libelleSourceRoutage(source)},
            {QStringLiteral("mention"), libelles::estTexte(carte.value(QStringLiteral("mention")))
                                            ? carte.value(QStringLiteral("mention")).toString() : QString()},
            {QStringLiteral("tour"), libelles::nombre(carte.value(QStringLiteral("tour")))},
            {QStringLiteral("resume"), libelles::estTexte(resume) ? resume.toString() : QString()},
        };
        for (auto it = etat.constBegin(); it != etat.constEnd(); ++it) {
            ligne.insert(it.key(), it.value());
        }
        return ligne;
    };

    // Relectures rangées sous la carte relue (observée par le greffon : champ `relue`).
    QHash<QString, QList<int>> relectures;
    for (int rang = 0; rang < cartes.size(); ++rang) {
        const QString relue = cartes.at(rang).value(QStringLiteral("relue")).toString();
        if (!relue.isEmpty() && identifiants.contains(relue)) {
            relectures[relue].append(rang);
        }
    }
    QSet<int> placees;
    // Une relecture peut elle-même être relue : chaque carte suit sa carte relue, à toute profondeur.
    std::function<void(int, int, const QString &)> placer = [&](int rang, int niveau, const QString &parent) {
        placees.insert(rang);
        lignes.append(ligneCarte(cartes.at(rang), niveau, parent, rang));
        const QString id = cartes.at(rang).value(QStringLiteral("carte")).toString();
        for (const int enfant : relectures.value(id)) {
            if (!placees.contains(enfant)) placer(enfant, niveau + 1, id);
        }
    };
    for (int rang = 0; rang < cartes.size(); ++rang) {
        if (placees.contains(rang)) continue;
        const QString relue = cartes.at(rang).value(QStringLiteral("relue")).toString();
        if (!relue.isEmpty() && identifiants.contains(relue)) continue; // placée sous sa carte relue
        placer(rang, 1, QStringLiteral("hermes"));
    }
    // Filet : des relectures qui se relisent l'une l'autre (cycle servi) restent visibles, sous Hermes.
    for (int rang = 0; rang < cartes.size(); ++rang) {
        if (!placees.contains(rang)) placer(rang, 1, QStringLiteral("hermes"));
    }
    return lignes;
}

QJsonArray EspaceTravailViewModel::construireEssais(const QJsonObject &projet)
{
    QJsonArray lignes;
    QHash<QString, QString> titres;
    for (const QJsonValue &element : projet.value(QStringLiteral("cartes")).toArray()) {
        const QJsonObject carte = element.toObject();
        titres.insert(carte.value(QStringLiteral("carte")).toString(), libelles::texte(carte.value(QStringLiteral("titre"))));
    }
    int rang = 0;
    for (const QJsonValue &element : projet.value(QStringLiteral("journal")).toArray()) {
        const QJsonObject entree = element.toObject();
        if (entree.value(QStringLiteral("action")).toString() != QLatin1String("carte_terminee")) continue;
        const QJsonObject detail = objetDuDetail(entree.value(QStringLiteral("detail")));
        const QString verification = detail.value(QStringLiteral("verification")).toString();
        const QString carte = entree.value(QStringLiteral("cible")).toString();
        QString libelle;
        QString statusKey;
        if (verification == QLatin1String("reussie")) {
            libelle = QStringLiteral("Vérification réussie");
            statusKey = QStringLiteral("succeeded");
        } else if (verification == QLatin1String("echouee")) {
            libelle = QStringLiteral("Vérification échouée");
            statusKey = QStringLiteral("failed");
        } else if (verification == QLatin1String("non_executee")) {
            libelle = QStringLiteral("Vérification non exécutée");
            statusKey = QStringLiteral("notConfigured");
        } else {
            libelle = QStringLiteral("Vérification non rapportée");
            statusKey = QStringLiteral("unknown");
        }
        lignes.append(QJsonObject{
            {QStringLiteral("cle"), QStringLiteral("%1#%2").arg(carte).arg(rang++)},
            {QStringLiteral("carte"), carte},
            {QStringLiteral("titre"), titres.value(carte, carte.isEmpty() ? libelles::kInconnu : carte)},
            {QStringLiteral("quand"), libelles::date(entree.value(QStringLiteral("quand")))},
            {QStringLiteral("libelle"), libelle},
            {QStringLiteral("statusKey"), statusKey},
            {QStringLiteral("role"), libelles::role(detail.value(QStringLiteral("role")))},
        });
    }
    return lignes;
}

QJsonArray EspaceTravailViewModel::construireSorties(const QJsonObject &projet)
{
    QJsonArray lignes;
    int rang = 0;
    for (const QJsonValue &element : projet.value(QStringLiteral("cartes")).toArray()) {
        const QJsonObject carte = element.toObject();
        const QJsonValue resume = carte.value(QStringLiteral("resume"));
        if (!libelles::estTexte(resume)) continue;
        const QString id = carte.value(QStringLiteral("carte")).toString();
        lignes.append(QJsonObject{
            {QStringLiteral("cle"), id.isEmpty() ? QStringLiteral("sortie:%1").arg(rang) : id},
            {QStringLiteral("carte"), id},
            {QStringLiteral("titre"), libelles::texte(carte.value(QStringLiteral("titre")))},
            {QStringLiteral("role"), libelles::role(carte.value(QStringLiteral("role")))},
            {QStringLiteral("resume"), resume.toString()},
            {QStringLiteral("tronque"), carte.value(QStringLiteral("resume_tronque")).toBool()},
            {QStringLiteral("longueur"), libelles::nombre(carte.value(QStringLiteral("resume_longueur")))},
        });
        ++rang;
    }
    return lignes;
}

} // namespace acp
