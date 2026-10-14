#include "viewmodels/ObsidianViewModel.h"
#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include "diagnostics/Redaction.h"
#include <QClipboard>
#include <QDateTime>
#include <QGuiApplication>
#include <QJsonArray>
#include <QRegularExpression>
#include <QUuid>

namespace acp {
namespace {
QString txt(const QJsonObject &o, const char *k) { return o.value(QLatin1String(k)).toString(); }
bool uuid(const QString &s) { return !QUuid(s).isNull() && QUuid(s).toString(QUuid::WithoutBraces) == s.toLower(); }
constexpr int kNoteOctets = 128 * 1024;
}
ObsidianViewModel::ObsidianViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent)
    : PageViewModel(flux, parent), m_greffon(greffon), m_notes(new JsonListModel(this)), m_backlinks(new JsonListModel(this))
{
    m_notes->setCle({QStringLiteral("id")});
    m_backlinks->setCle({QStringLiteral("id")});
    m_presse = [](const QString &s) { auto *p = QGuiApplication::clipboard(); if (!p) return false; p->setText(s); return p->text() == s; };
    m_suivi.setInterval(2000); m_suivi.setSingleShot(true);
    m_presence.setInterval(30000);
    m_horlogeCode.setInterval(1000);
    connect(&m_suivi, &QTimer::timeout, this, &ObsidianViewModel::sonderOperation);
    connect(&m_presence, &QTimer::timeout, this, &ObsidianViewModel::actualiser);
    connect(&m_horlogeCode, &QTimer::timeout, this, [this] {
        if (codeSecondes() == 0) effacerCode(); else emit codeChange();
    });
}
ObsidianViewModel::~ObsidianViewModel() { ++m_generation; if (m_appel) m_appel->abort(); effacerCode(); }
QString ObsidianViewModel::etatLibelle() const
{
    if (m_etat == QLatin1String("pret")) return QStringLiteral("Coffre disponible");
    if (m_etat == QLatin1String("non_configure")) return QStringLiteral("Coffre à associer");
    if (m_etat == QLatin1String("a_confirmer")) return QStringLiteral("Empreinte à confirmer");
    if (m_etat == QLatin1String("hors_ligne")) return QStringLiteral("Bridge hors ligne");
    if (m_etat == QLatin1String("revoque")) return QStringLiteral("Association révoquée");
    return QStringLiteral("État du coffre inconnu");
}
QString ObsidianViewModel::lecture() const { return m_luA.isValid() ? QStringLiteral("État lu à %1").arg(m_luA.toString(QStringLiteral("HH:mm:ss"))) : QStringLiteral("État non lu"); }
QString ObsidianViewModel::brouillon() const { return m_brouillons.value(m_selection).texte; }
bool ObsidianViewModel::noteLue() const { return empreinteValide(m_brouillons.value(m_selection).empreinte); }
bool ObsidianViewModel::modifie() const { const auto n=m_brouillons.value(m_selection); return noteOuverte() && (n.neuve || n.texte != n.origine); }
bool ObsidianViewModel::nouvelle() const { return m_brouillons.value(m_selection).neuve; }
bool ObsidianViewModel::conflit() const { return m_brouillons.value(m_selection).conflit; }
QString ObsidianViewModel::versionServeur() const { return m_brouillons.value(m_selection).distant; }
bool ObsidianViewModel::versionServeurDisponible() const { return !m_brouillons.value(m_selection).empreinteDistante.isEmpty(); }
int ObsidianViewModel::codeSecondes() const { return int(qMax<qint64>(0, m_codeExpire-QDateTime::currentSecsSinceEpoch())); }
void ObsidianViewModel::setRecherche(const QString &s) { if (m_recherche!=s.left(200)) {m_recherche=s.left(200); emit rechercheChange();} }
void ObsidianViewModel::setBrouillon(const QString &s)
{
    if (!noteOuverte() || brouillon()==s) return;
    m_brouillons[m_selection].texte=s; emit noteChange();
}
bool ObsidianViewModel::empreinteValide(const QString &s)
{
    static const QRegularExpression r(QStringLiteral("^[a-f0-9]{64}$")); return r.match(s).hasMatch();
}
bool ObsidianViewModel::cheminValide(const QString &s)
{
    if (s.isEmpty() || s.size()>240 || s!=s.trimmed() || !s.endsWith(QLatin1String(".md"), Qt::CaseInsensitive)
        || s.startsWith(QLatin1Char('/')) || s.contains(QRegularExpression(QStringLiteral("[\\\\:*?\"<>|\\x00-\\x1f]")))) return false;
    static const QRegularExpression reserve(QStringLiteral("^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\\.|$)"), QRegularExpression::CaseInsensitiveOption);
    for (const auto &p : s.split(QLatin1Char('/'))) {
        if (p.isEmpty() || p.startsWith(QLatin1Char('.')) || p.endsWith(QLatin1Char('.')) || p.endsWith(QLatin1Char(' ')) || reserve.match(p).hasMatch()) return false;
    }
    return true;
}
bool ObsidianViewModel::capacite(const QString &s) const { return m_coffre.value(QStringLiteral("capacites")).toArray().contains(s); }
void ObsidianViewModel::surActivite(bool active)
{
    if (active) { m_presence.start(); if (!m_operationId.isEmpty()) sonderOperation(); else actualiser(); }
    else { m_presence.stop(); m_suivi.stop(); }
}
void ObsidianViewModel::surLienRetabli() { if (actif()) { if (!m_operationId.isEmpty()) sonderOperation(); else actualiser(); } }
void ObsidianViewModel::viderNotes()
{
    m_brouillons.clear(); m_selection.clear(); m_notes->clear(); m_backlinks->clear(); m_graphe={};
    m_tronque=false; emit noteChange(); emit grapheChange();
}
void ObsidianViewModel::surOubli()
{
    ++m_generation; m_suivi.stop(); m_presence.stop();
    if (m_appel) m_appel->abort(); m_appel.clear();
    m_operationId.clear(); m_action.clear(); m_operationEtat.clear(); m_parametres={}; m_coffreOperation.clear();
    effacerCode(); viderNotes(); m_coffre={}; m_etat=QStringLiteral("inconnu"); m_erreur.clear();
    m_luA={}; m_recherche.clear(); emit rechercheChange(); emit etatChange();
}
void ObsidianViewModel::appeler(ApiCall *appel, std::function<void(const QJsonObject &)> suite, bool suivi, bool lectureStatut, bool creationOperation)
{
    m_appel=appel; const auto generation=m_generation; emit etatChange();
    connect(appel, &ApiCall::succeeded, this, [this,generation,suite](const ApiResponse &r) {
        if (generation!=m_generation) return;
        m_appel.clear(); m_erreur.clear(); suite(r.json.object()); emit etatChange();
    });
    connect(appel, &ApiCall::failed, this, [this,generation,suivi,lectureStatut,creationOperation](const ApiError &e) {
        if (generation!=m_generation) return;
        m_appel.clear(); m_erreur=messageDuRefus(e);
        if (lectureStatut && e.httpStatus()==404) {
            // La route absente ne prouve rien sur la présence du bridge local.
            m_etat=QStringLiteral("inconnu");
            m_erreur=QStringLiteral("Ce serveur ne fournit pas la fonction Coffre ACP (HTTP 404). Mettez à jour le serveur ACP vers 1.2.0 ou ultérieur, puis actualisez cet état.");
        }
        // Ces refus précèdent toute acceptation de la nouvelle opération. Un 409,
        // une coupure ou un 5xx restent incertains : conserver leur identifiant.
        const bool refusCertain = e.kind()==ApiFailure::ClientRefusal
            || QList<int>{400,401,403,413,415,422}.contains(e.httpStatus());
        if (creationOperation && refusCertain) {
            m_suivi.stop(); m_operationId.clear(); m_action.clear(); m_parametres={};
            m_operationEtat=QStringLiteral("Demande refusée avant acceptation · brouillon conservé");
        } else if (suivi && !m_operationId.isEmpty()) {
            m_operationEtat=QStringLiteral("Résultat non confirmé · suivi conservé");
            if (actif()) m_suivi.start();
        }
        emit etatChange();
    });
}
void ObsidianViewModel::actualiser()
{
    if (!actif() || occupe()) return;
    appeler(m_greffon->coffre(), [this](const QJsonObject &r) { adopterStatut(r); }, false, true);
}
void ObsidianViewModel::fermerSuivi(bool confirmation)
{
    if (!confirmation || m_appel || m_operationId.isEmpty()) return;
    if (m_action==QLatin1String("ecrire") || m_action==QLatin1String("creer") || m_action==QLatin1String("archiver") || m_action==QLatin1String("renommer")) {
        m_brouillons[txt(m_parametres,"chemin")].conflit=true; emit noteChange();
    }
    m_suivi.stop(); m_operationId.clear(); m_action.clear(); m_parametres={};
    m_operationEtat=QStringLiteral("Suivi fermé localement · résultat non confirmé, relire avant toute écriture"); emit etatChange();
}
void ObsidianViewModel::adopterStatut(const QJsonObject &r)
{
    const QString etat=txt(r,"etat"); const auto c=r.value(QStringLiteral("coffre")).toObject();
    if (txt(r,"protocole")!=QLatin1String("acp-coffre/1")
        || !QStringList{QStringLiteral("non_configure"),QStringLiteral("a_confirmer"),QStringLiteral("hors_ligne"),QStringLiteral("pret"),QStringLiteral("revoque")}.contains(etat)
        || (etat!=QLatin1String("non_configure") && (!uuid(txt(c,"coffre_id")) || !c.value(QStringLiteral("capacites")).isArray()))) {
        m_erreur=QStringLiteral("État du coffre illisible ; aucune disponibilité confirmée."); m_etat=QStringLiteral("inconnu"); return;
    }
    if (!m_coffre.isEmpty() && txt(m_coffre,"coffre_id")!=txt(c,"coffre_id")) viderNotes();
    m_coffre=c; m_etat=etat; m_luA=QDateTime::currentDateTime();
    if (etat==QLatin1String("pret") || etat==QLatin1String("a_confirmer")) effacerCode();
}
void ObsidianViewModel::lancer(const QString &action, const QJsonObject &parametres)
{
    if (!actif() || occupe() || m_etat!=QLatin1String("pret") || !capacite(action)) {
        m_erreur=QStringLiteral("Cette action attend un coffre disponible et sa capacité annoncée."); emit etatChange(); return;
    }
    m_operationId=QUuid::createUuid().toString(QUuid::WithoutBraces); m_action=action; m_parametres=parametres;
    m_coffreOperation=txt(m_coffre,"coffre_id"); m_operationEtat=QStringLiteral("Demande envoyée · résultat attendu");
    const QJsonObject corps{{QStringLiteral("id_operation"),m_operationId},{QStringLiteral("coffre_id"),m_coffreOperation},
        {QStringLiteral("action"),action},{QStringLiteral("parametres"),parametres}};
    appeler(m_greffon->creerOperationCoffre(corps), [this](const QJsonObject &r) { adopterOperation(r); }, true, false, true);
}
void ObsidianViewModel::sonderOperation()
{
    if (!actif() || m_appel || m_operationId.isEmpty()) return;
    appeler(m_greffon->operationCoffre(m_operationId), [this](const QJsonObject &r) { adopterOperation(r); }, true);
}
void ObsidianViewModel::adopterOperation(const QJsonObject &r)
{
    if (txt(r,"id_operation")!=m_operationId || txt(r,"coffre_id")!=m_coffreOperation || txt(r,"action")!=m_action) {
        m_erreur=QStringLiteral("Réponse d’opération incohérente ; aucun résultat appliqué.");
        if (actif()) m_suivi.start(); return;
    }
    const QString etat=txt(r,"etat");
    if (etat==QLatin1String("en_attente") || etat==QLatin1String("en_cours")) {
        m_operationEtat=etat==QLatin1String("en_attente") ? QStringLiteral("En attente du bridge") : QStringLiteral("Opération en cours sur le coffre");
        if (actif()) m_suivi.start(); return;
    }
    if (etat==QLatin1String("reussie")) {
        if (appliquerResultat(r.value(QStringLiteral("resultat")).toObject())) m_operationEtat=QStringLiteral("Opération confirmée par le bridge");
        else { m_erreur=QStringLiteral("Résultat illisible ; le brouillon reste conservé. Relisez la note avant une nouvelle écriture."); m_operationEtat=QStringLiteral("Résultat non exploitable"); }
    } else if (QStringList{QStringLiteral("refusee"),QStringLiteral("expiree"),QStringLiteral("indeterminee")}.contains(etat)) {
        const auto e=r.value(QStringLiteral("erreur")).toObject();
        m_erreur=redactSecrets(txt(e,"message")).left(1000);
        if (m_erreur.isEmpty()) m_erreur=QStringLiteral("Opération %1. Aucun succès confirmé ; le brouillon est conservé.").arg(etat);
        m_operationEtat=QStringLiteral("Opération %1").arg(etat);
        if (txt(e,"code")==QLatin1String("conflit")) {
            m_brouillons[txt(m_parametres,"chemin")].conflit=true; emit noteChange();
        }
    } else {
        m_erreur=QStringLiteral("État d’opération inconnu ; résultat encore non confirmé."); if (actif()) m_suivi.start(); return;
    }
    m_suivi.stop(); m_operationId.clear(); m_action.clear(); m_parametres={};
}
bool ObsidianViewModel::appliquerResultat(const QJsonObject &r)
{
    const QString p=txt(m_parametres,"chemin");
    if (m_action==QLatin1String("lire")) {
        if (txt(r,"chemin")!=p || !r.value(QStringLiteral("contenu")).isString() || !empreinteValide(txt(r,"empreinte")) || txt(r,"contenu").toUtf8().size()>kNoteOctets) return false;
        auto &n=m_brouillons[p];
        if (n.neuve || n.texte!=n.origine || n.conflit) {
            n.distant=txt(r,"contenu"); n.empreinteDistante=txt(r,"empreinte"); n.conflit=n.empreinte!=n.empreinteDistante;
        } else { n.texte=txt(r,"contenu"); n.origine=n.texte; n.empreinte=txt(r,"empreinte"); }
        emit noteChange(); return true;
    }
    if (m_action==QLatin1String("creer") || m_action==QLatin1String("ecrire")) {
        if (txt(r,"chemin")!=p || !empreinteValide(txt(r,"empreinte"))) { m_brouillons[p].conflit=true; emit noteChange(); return false; }
        auto &n=m_brouillons[p]; n.origine=txt(m_parametres,"contenu"); n.empreinte=txt(r,"empreinte"); n.neuve=false; n.conflit=false; n.distant.clear(); n.empreinteDistante.clear();
        emit noteChange(); return true; // Une frappe pendant la sauvegarde reste différente de l'origine envoyée.
    }
    if (m_action==QLatin1String("archiver")) {
        if (txt(r,"chemin")!=p || txt(r,"archive_id").isEmpty()) return false;
        auto &n=m_brouillons[p];
        if (n.texte!=n.origine) { n.neuve=true; n.origine.clear(); n.empreinte.clear(); }
        else { m_brouillons.remove(p); if (m_selection==p) m_selection.clear(); }
        m_notes->clear(); m_backlinks->clear(); emit noteChange(); return true;
    }
    if (m_action==QLatin1String("renommer")) {
        const QString destination=txt(m_parametres,"destination");
        if (txt(r,"destination")!=destination || !empreinteValide(txt(r,"empreinte")) || r.value(QStringLiteral("liens_modifies"))!=QJsonValue(false)) return false;
        auto n=m_brouillons.take(p); n.empreinte=txt(r,"empreinte"); m_brouillons.insert(destination,n); m_selection=destination;
        m_notes->clear(); m_backlinks->clear(); emit noteChange(); return true;
    }
    if (m_action==QLatin1String("lister") || m_action==QLatin1String("rechercher")) {
        const QString cle=m_action==QLatin1String("lister") ? QStringLiteral("notes") : QStringLiteral("resultats");
        if (!r.value(cle).isArray()) return false;
        QJsonArray notes; int i=0;
        for (const auto &v:r.value(cle).toArray()) { auto n=v.toObject(); if (!cheminValide(txt(n,"chemin"))) return false; n.insert(QStringLiteral("id"),txt(n,"chemin")+QStringLiteral(":%1").arg(i++)); notes.append(n); }
        m_notes->setItems(notes); m_tronque=r.value(QStringLiteral("tronque")).toBool(); return true;
    }
    if (m_action==QLatin1String("backlinks")) {
        if (txt(r,"chemin")!=p || !r.value(QStringLiteral("liens")).isArray()) return false;
        QJsonArray liens; int i=0;
        for (const auto &v:r.value(QStringLiteral("liens")).toArray()) { auto l=v.toObject(); if (!cheminValide(txt(l,"source")) || !cheminValide(txt(l,"cible"))) return false; l.insert(QStringLiteral("id"),QString::number(i++)); liens.append(l); }
        m_backlinks->setItems(liens); return true;
    }
    if (m_action==QLatin1String("graphe")) {
        if (!r.value(QStringLiteral("noeuds")).isArray() || !r.value(QStringLiteral("liens")).isArray() || !r.value(QStringLiteral("non_resolus")).isArray()) return false;
        for (const auto &v:r.value(QStringLiteral("noeuds")).toArray()) if (!cheminValide(txt(v.toObject(),"chemin"))) return false;
        for (const auto &v:r.value(QStringLiteral("liens")).toArray()) if (!cheminValide(txt(v.toObject(),"source")) || !cheminValide(txt(v.toObject(),"cible"))) return false;
        m_graphe=r; emit grapheChange(); return true;
    }
    return false;
}
void ObsidianViewModel::lister() { lancer(QStringLiteral("lister"),{{QStringLiteral("limite"),200}}); }
void ObsidianViewModel::chercher() { if (m_recherche.trimmed().isEmpty()) lister(); else lancer(QStringLiteral("rechercher"),{{QStringLiteral("texte"),m_recherche.trimmed()},{QStringLiteral("limite"),100}}); }
void ObsidianViewModel::ouvrirNote(const QString &p)
{
    if (occupe() || !cheminValide(p)) return;
    m_selection=p; m_backlinks->clear(); emit noteChange();
    if (!m_brouillons.contains(p)) { m_brouillons.insert(p,{}); relire(); }
}
void ObsidianViewModel::nouvelleNote(const QString &p)
{
    if (occupe() || !cheminValide(p)) { m_erreur=QStringLiteral("Choisissez un chemin relatif Markdown valide, par exemple Projets/Idees.md."); emit etatChange(); return; }
    m_selection=p;
    if (!m_brouillons.contains(p)) { Note n; n.neuve=true; m_brouillons.insert(p,n); }
    m_backlinks->clear(); emit noteChange();
}
void ObsidianViewModel::relire() { if (noteOuverte()) lancer(QStringLiteral("lire"),{{QStringLiteral("chemin"),m_selection}}); }
void ObsidianViewModel::sauvegarder()
{
    if (!noteOuverte()) return;
    const auto n=m_brouillons.value(m_selection);
    if (n.texte.toUtf8().size()>kNoteOctets) { m_erreur=QStringLiteral("La note dépasse 128 Kio UTF-8 ; réduisez-la avant de sauvegarder."); emit etatChange(); return; }
    if (n.conflit || (!n.neuve && !empreinteValide(n.empreinte))) { m_erreur=QStringLiteral("Relisez la version du coffre et comparez-la au brouillon avant de sauvegarder."); emit etatChange(); return; }
    QJsonObject p{{QStringLiteral("chemin"),m_selection},{QStringLiteral("contenu"),n.texte}};
    if (!n.neuve) p.insert(QStringLiteral("empreinte_attendue"),n.empreinte);
    lancer(n.neuve ? QStringLiteral("creer") : QStringLiteral("ecrire"),p);
}
void ObsidianViewModel::archiver(bool confirmation)
{
    if (!confirmation || !noteOuverte() || modifie() || conflit() || !empreinteValide(m_brouillons.value(m_selection).empreinte)) return;
    lancer(QStringLiteral("archiver"),{{QStringLiteral("chemin"),m_selection},{QStringLiteral("empreinte_attendue"),m_brouillons.value(m_selection).empreinte}});
}
void ObsidianViewModel::renommer(const QString &destination, bool confirmation)
{
    if (!confirmation || !noteOuverte() || modifie() || conflit() || !cheminValide(destination) || !empreinteValide(m_brouillons.value(m_selection).empreinte)) return;
    const auto cible=m_brouillons.value(destination);
    if (destination!=m_selection && m_brouillons.contains(destination) && (cible.neuve || cible.texte!=cible.origine)) {
        m_erreur=QStringLiteral("Un brouillon existe déjà à cette destination ; il reste conservé."); emit etatChange(); return;
    }
    lancer(QStringLiteral("renommer"),{{QStringLiteral("chemin"),m_selection},{QStringLiteral("destination"),destination},{QStringLiteral("empreinte_attendue"),m_brouillons.value(m_selection).empreinte}});
}
void ObsidianViewModel::lireBacklinks() { if (noteOuverte() && !nouvelle()) lancer(QStringLiteral("backlinks"),{{QStringLiteral("chemin"),m_selection},{QStringLiteral("limite"),500}}); }
void ObsidianViewModel::lireGraphe() { lancer(QStringLiteral("graphe"),{{QStringLiteral("limite"),500}}); }
void ObsidianViewModel::utiliserVersionServeur(bool confirmation)
{
    if (!confirmation || !versionServeurDisponible() || occupe()) return;
    auto &n=m_brouillons[m_selection]; n.texte=n.distant; n.origine=n.distant; n.empreinte=n.empreinteDistante; n.conflit=false; n.neuve=false; n.distant.clear(); n.empreinteDistante.clear(); emit noteChange();
}
void ObsidianViewModel::garderBrouillonSurVersionServeur(bool confirmation)
{
    if (!confirmation || !versionServeurDisponible() || occupe()) return;
    auto &n=m_brouillons[m_selection]; n.origine=n.distant; n.empreinte=n.empreinteDistante; n.conflit=false; n.neuve=false; n.distant.clear(); n.empreinteDistante.clear(); emit noteChange();
}
void ObsidianViewModel::effacerCode()
{
    if (m_code.isEmpty() && m_codeExpire==0) return;
    if (auto *presse=QGuiApplication::clipboard(); presse && presse->text()==m_code) presse->clear();
    m_code.fill(QChar()); m_code.clear(); m_codeExpire=0; m_horlogeCode.stop(); emit codeChange();
}
void ObsidianViewModel::creerCode()
{
    if (!actif() || occupe()) return;
    effacerCode();
    appeler(m_greffon->enrolerCoffre(), [this](const QJsonObject &r) {
        const auto code=txt(r,"code"); const auto expire=r.value(QStringLiteral("expire_le")).toInteger();
        const auto maintenant=QDateTime::currentSecsSinceEpoch();
        if (txt(r,"protocole")!=QLatin1String("acp-coffre/1") || !QRegularExpression(QStringLiteral("^acpce_[A-Za-z0-9_-]{43}$")).match(code).hasMatch() || expire<=maintenant) {
            m_erreur=QStringLiteral("Code d’association illisible ou expiré."); return;
        }
        m_code=code; m_codeExpire=qMin(expire,maintenant+600); m_horlogeCode.start(); emit codeChange();
    });
}
bool ObsidianViewModel::copierCode()
{
    if (codeSecondes()==0 || m_code.isEmpty() || !m_presse || !m_presse(m_code)) return false;
    terminerGeste(QStringLiteral("Code temporaire copié. Collez-le dans la saisie masquée du bridge local.")); return true;
}
void ObsidianViewModel::confirmerEmpreinte(const QString &s)
{
    if (!actif() || occupe() || m_etat!=QLatin1String("a_confirmer") || s.trimmed().isEmpty() || s.trimmed()!=txt(m_coffre,"empreinte")) {
        m_erreur=QStringLiteral("Comparez et saisissez l’empreinte affichée par la commande locale."); emit etatChange(); return;
    }
    appeler(m_greffon->confirmerCoffre(txt(m_coffre,"coffre_id"),s.trimmed()),[this](const QJsonObject &r){ adopterStatut(r); });
}
void ObsidianViewModel::revoquer(bool confirmation)
{
    if (!confirmation || !actif() || occupe() || !uuid(txt(m_coffre,"coffre_id"))) return;
    appeler(m_greffon->revoquerCoffre(txt(m_coffre,"coffre_id"),QStringLiteral("Révocation demandée depuis le desktop")),[this](const QJsonObject &r){ adopterStatut(r); });
}
}
