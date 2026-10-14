#include "viewmodels/ComptesViewModel.h"
#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include "events/EventStreamService.h"
#include <QDateTime>
#include <QDesktopServices>
#include <QJsonArray>
#include <QRegularExpression>
#include <QTimer>
#include <QUuid>
namespace acp {
namespace {
QString texte(const QJsonObject &o, const char *key, int max = 2000) {
    return o.value(QLatin1String(key)).toString().left(max);
}
bool enAttente(const QString &e) {
    return QStringList{QStringLiteral("en_attente"), QStringLiteral("demarrage"), QStringLiteral("code_disponible"),
        QStringLiteral("verification"), QStringLiteral("annulation_demandee")}.contains(e);
}
}
ComptesViewModel::ComptesViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent)
    : PageViewModel(flux, parent), m_greffon(greffon), m_timer(new QTimer(this)),
      m_ouvreur([](const QUrl &url) { return QDesktopServices::openUrl(url); }) {
    m_timer->setSingleShot(true);
    connect(m_timer, &QTimer::timeout, this, &ComptesViewModel::actualiser);
}
ComptesViewModel::~ComptesViewModel() {
    ++m_generation;
    if (m_appel) { m_appel->disconnect(this); m_appel->abort(); }
    if (m_mutation) { m_mutation->disconnect(this); m_mutation->abort(); }
}
bool ComptesViewModel::attente() const { return enAttente(texte(m_connexion, "etat")); }
bool ComptesViewModel::peutConnecter() const {
    if (!actif() || !m_lue || !m_erreur.isEmpty() || !m_serveur.value(QStringLiteral("disponible")).toBool()
        || attente() || gesteEnCours()) return false;
    for (const auto &v : m_comptes) {
        const auto c=v.toMap();
        if (c.value(QStringLiteral("moteur")) == QStringLiteral("codex"))
            return c.value(QStringLiteral("implementation")) == QStringLiteral("disponible");
    }
    return false;
}
QString ComptesViewModel::libelleEtat(const QString &e) {
    static const QHash<QString,QString> labels{
        {QStringLiteral("inconnu"),QStringLiteral("État du compte inconnu")},
        {QStringLiteral("non_configure"),QStringLiteral("Non configuré")},
        {QStringLiteral("connexion_en_attente"),QStringLiteral("Connexion en attente")},
        {QStringLiteral("connecte"),QStringLiteral("Compte connecté")},
        {QStringLiteral("expire"),QStringLiteral("Session expirée")},
        {QStringLiteral("moteur_indisponible"),QStringLiteral("Moteur indisponible")},
        {QStringLiteral("erreur"),QStringLiteral("Erreur de connexion")},
        {QStringLiteral("en_attente"),QStringLiteral("Demande reçue par Hermes")},
        {QStringLiteral("demarrage"),QStringLiteral("Démarrage sur le serveur")},
        {QStringLiteral("code_disponible"),QStringLiteral("Autorisation attendue dans votre navigateur")},
        {QStringLiteral("verification"),QStringLiteral("Vérification du compte sur le serveur")},
        {QStringLiteral("annulation_demandee"),QStringLiteral("Annulation demandée")},
        {QStringLiteral("annulee"),QStringLiteral("Connexion annulée")},
        {QStringLiteral("expiree"),QStringLiteral("Délai de connexion dépassé")},
        {QStringLiteral("interrompue"),QStringLiteral("Connexion interrompue")}};
    return labels.value(e,QStringLiteral("État inconnu"));
}
bool ComptesViewModel::identifiantConnexionValide(const QString &id) {
    static const QRegularExpression re(QStringLiteral("\\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\z"));
    return re.match(id).hasMatch();
}
bool ComptesViewModel::urlVerificationAdmise(const QUrl &url) {
    return url.isValid() && url.scheme()==QLatin1String("https") && url.host()==QLatin1String("auth.openai.com")
        && url.path()==QLatin1String("/codex/device") && !url.hasQuery() && url.userInfo().isEmpty() && !url.hasFragment() && (url.port(-1)==-1 || url.port(-1)==443);
}
bool ComptesViewModel::lireConnexion(const QJsonObject &o) {
    const QString id=texte(o,"id"), etat=texte(o,"etat");
    if (!identifiantConnexionValide(id) || texte(o,"moteur")!=QLatin1String("codex")
        || (!enAttente(etat) && !QStringList{QStringLiteral("connecte"),QStringLiteral("annulee"),QStringLiteral("expiree"),QStringLiteral("interrompue"),QStringLiteral("erreur")}.contains(etat))) return false;
    QJsonObject c{{QStringLiteral("id"),id},{QStringLiteral("etat"),etat},
        {QStringLiteral("libelle"),libelleEtat(etat)},{QStringLiteral("message"),texte(o,"message")}};
    c.insert(QStringLiteral("limite"), o.value(QStringLiteral("limite_attente_le")).isDouble()
        ? QDateTime::fromSecsSinceEpoch(o.value(QStringLiteral("limite_attente_le")).toInteger()).toLocalTime().toString(QStringLiteral("HH:mm:ss"))
        : QStringLiteral("Inconnue"));
    const QUrl url(texte(o,"verification_url",2048),QUrl::StrictMode);
    if (enAttente(etat) && etat!=QLatin1String("annulation_demandee") && urlVerificationAdmise(url)) {
        c.insert(QStringLiteral("url"),url.toString());
        c.insert(QStringLiteral("code"),texte(o,"code_utilisateur",64));
    }
    c.insert(QStringLiteral("limiteEpoch"),o.value(QStringLiteral("limite_attente_le")));
    m_connexion=c;
    if (!enAttente(etat)) m_cle.clear();
    return true;
}
bool ComptesViewModel::lireComptes(const QJsonObject &o) {
    if (texte(o,"protocole")!=QLatin1String("acp-comptes/1") || !o.value(QStringLiteral("serveur")).isObject()
        || !o.value(QStringLiteral("comptes")).isArray()) return false;
    const auto serveur=o.value(QStringLiteral("serveur")).toObject();
    if (!serveur.value(QStringLiteral("disponible")).isBool()) return false;
    QVariantList comptes;
    QJsonObject connexion;
    for (const auto &v:o.value(QStringLiteral("comptes")).toArray()) {
        const auto c=v.toObject(); const auto moteur=texte(c,"moteur");
        if (!QStringList{QStringLiteral("codex"),QStringLiteral("claude_code"),QStringLiteral("mistral_vibe")}.contains(moteur)) continue;
        const auto etat=texte(c,"etat");
        const auto observation=c.value(QStringLiteral("observation")).toObject();
        const QString etatObservation=texte(observation,"etat");
        const QString origine=texte(observation,"origine_modeles");
        QString libelleObservation=QStringLiteral("Aucune observation actuelle du compte.");
        if(etatObservation==QLatin1String("a_jour")) libelleObservation=QStringLiteral("Relevé actuel du serveur");
        else if(etatObservation==QLatin1String("perime")) libelleObservation=QStringLiteral("Relevé périmé : état et modèles à reconfirmer");
        else if(etatObservation==QLatin1String("actualisation_en_attente")) libelleObservation=QStringLiteral("Actualisation du relevé en attente");
        if(observation.value(QStringLiteral("recu_le")).isDouble())
            libelleObservation+=QStringLiteral(" · ")+QDateTime::fromSecsSinceEpoch(observation.value(QStringLiteral("recu_le")).toInteger()).toLocalTime().toString(QStringLiteral("dd/MM/yyyy HH:mm"));
        QVariantList modeles;
        for (const auto &modele:c.value(QStringLiteral("modeles")).toArray()) {
            if (modeles.size()>=100) break;
            if (modele.isObject()) { const auto m=modele.toObject(); if (!texte(m,"id",200).isEmpty()) modeles.append(texte(m,"id",200)); }
            else if (modele.isString()) modeles.append(modele.toString().left(200));
        }
        if(etatObservation!=QLatin1String("a_jour") || origine!=QLatin1String("compte") || c.value(QStringLiteral("compte_connecte"))!=QJsonValue(true)) modeles.clear();
        comptes.append(QVariantMap{{QStringLiteral("moteur"),moteur},{QStringLiteral("nom"),texte(c,"nom",100)},
            {QStringLiteral("implementation"),texte(c,"implementation")},{QStringLiteral("etat"),etat},
            {QStringLiteral("libelle"),libelleEtat(etat)},{QStringLiteral("version"),texte(c,"version",100)},
            {QStringLiteral("message"),texte(c,"message")},{QStringLiteral("modeles"),modeles},
            {QStringLiteral("observation"),libelleObservation},{QStringLiteral("observationEtat"),etatObservation},
            {QStringLiteral("quotasRapportes"),etatObservation==QLatin1String("a_jour") ? observation.value(QStringLiteral("quotas")).toArray().size() : 0},
            {QStringLiteral("compteConnecte"),c.value(QStringLiteral("compte_connecte")).isBool()
                ? QVariant(c.value(QStringLiteral("compte_connecte")).toBool()) : QVariant()},
            {QStringLiteral("inferenceVerifiee"),c.value(QStringLiteral("inference_verifiee"))==QJsonValue(true)}});
        if (moteur==QLatin1String("codex") && c.value(QStringLiteral("connexion")).isObject()) connexion=c.value(QStringLiteral("connexion")).toObject();
    }
    if (comptes.isEmpty()) return false;
    if (!connexion.isEmpty() && !lireConnexion(connexion)) return false;
    if (connexion.isEmpty()) m_connexion={};
    m_comptes=comptes;
    m_serveur={{QStringLiteral("disponible"),serveur.value(QStringLiteral("disponible")).toBool()},
        {QStringLiteral("nom"),texte(serveur,"nom",200)},{QStringLiteral("raison"),texte(serveur,"raison")}};
    m_lue=true;
    return true;
}
void ComptesViewModel::programmer() { if (actif()) m_timer->start(m_intervalleTest>0 ? m_intervalleTest : attente()?2500:15000); }
void ComptesViewModel::abandonnerLecture() {
    if (m_appel) { auto appel=m_appel; m_appel=nullptr; appel->disconnect(this); appel->abort(); }
}
void ComptesViewModel::surActivite(bool active) {
    if (active) actualiser(); else { m_timer->stop(); abandonnerLecture(); emit change(); }
}
void ComptesViewModel::surLienRetabli() { actualiser(); }
void ComptesViewModel::surOubli() {
    ++m_generation; m_timer->stop(); abandonnerLecture();
    if (m_mutation) { auto appel=m_mutation; m_mutation=nullptr; appel->disconnect(this); appel->abort(); }
    m_comptes.clear(); m_serveur.clear(); m_connexion={}; m_cle.clear(); m_erreur.clear(); m_lue=false;
    terminerGeste({}); emit change();
}
void ComptesViewModel::actualiser() {
    if (!actif() || m_appel || m_mutation) return;
    m_timer->stop(); const auto generation=m_generation; const bool suivi=attente();
    m_appel=suivi ? m_greffon->connexionCompte(texte(m_connexion,"id")) : m_greffon->comptes();
    connect(m_appel,&ApiCall::succeeded,this,[this,generation,suivi](const ApiResponse &r) {
        if (generation!=m_generation) return;
        m_appel=nullptr;
        const bool valide=suivi ? lireConnexion(r.json.object()) : lireComptes(r.json.object());
        m_erreur=valide ? QString() : QStringLiteral("Réponse des comptes illisible. Actualisez avant de poursuivre.");
        emit change();
        if (valide && suivi && !attente()) actualiser(); else programmer();
    });
    connect(m_appel,&ApiCall::failed,this,[this,generation](const ApiError &e) {
        if(generation!=m_generation) return;
        m_appel=nullptr;
        m_erreur=e.httpStatus()==404 ? QStringLiteral("Ce serveur ne propose pas encore la connexion distante des comptes. Mettez Hermes à jour.") : messageDuRefus(e);
        emit change(); programmer();
    }); emit change();
}
void ComptesViewModel::connecterCodex() { if(peutConnecter()) geste(false); }
void ComptesViewModel::annulerConnexion() { if(actif() && attente() && !gesteEnCours()) geste(true); }
void ComptesViewModel::geste(bool annulation) {
    abandonnerLecture(); m_timer->stop(); const auto generation=m_generation;
    if(m_cle.isEmpty()) m_cle=QUuid::createUuid().toString(QUuid::WithoutBraces);
    debuterGeste();
    m_mutation=annulation ? m_greffon->annulerConnexionCompte(texte(m_connexion,"id")) : m_greffon->connecterCompteCodex(m_cle);
    connect(m_mutation,&ApiCall::succeeded,this,[this,generation,annulation](const ApiResponse &r) {
        if(generation!=m_generation) return; m_mutation=nullptr;
        if(!lireConnexion(r.json.object())) echouerGeste(QStringLiteral("Réponse de connexion illisible. Actualisez pour retrouver son état serveur."));
        else terminerGeste(annulation ? QStringLiteral("Demande d’annulation transmise au serveur.") : QStringLiteral("Procédure lancée sur le serveur. Votre autorisation se fait dans le navigateur."));
        emit change(); programmer();
    });
    connect(m_mutation,&ApiCall::failed,this,[this,generation](const ApiError &e) {
        if(generation!=m_generation) return; m_mutation=nullptr; echouerGeste(e); emit change(); programmer();
    }); emit change();
}
bool ComptesViewModel::ouvrirVerification() {
    const QUrl url(texte(m_connexion,"url"),QUrl::StrictMode);
    if(!actif() || !attente() || !urlVerificationAdmise(url)) return false;
    if(m_connexion.value(QStringLiteral("limiteEpoch")).toInteger()<=QDateTime::currentSecsSinceEpoch()) {
        echouerGeste(QStringLiteral("Le délai de cette connexion est dépassé. Actualisez son état avant de recommencer.")); return false;
    }
    if(m_ouvreur(url)) return true;
    echouerGeste(QStringLiteral("Le navigateur n’a pas pu être ouvert. Ouvrez le lien affiché manuellement.")); return false;
}
}
