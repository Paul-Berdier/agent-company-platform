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
bool ComptesViewModel::peutConnecter() const { return peutConnecterMoteur(QStringLiteral("codex")); }
bool ComptesViewModel::peutConnecterClaude() const { return peutConnecterMoteur(QStringLiteral("claude_code")); }
bool ComptesViewModel::peutConnecterMoteur(const QString &moteur) const {
    if (!actif() || !m_lue || !m_erreur.isEmpty() || !m_serveur.value(QStringLiteral("disponible")).toBool()
        || attente() || gesteEnCours()) return false;
    for (const auto &v : m_comptes) {
        const auto c=v.toMap();
        if (c.value(QStringLiteral("moteur")) == moteur)
            return c.value(QStringLiteral("implementation")) == QStringLiteral("disponible");
    }
    return false;
}
bool ComptesViewModel::peutOuvrirVerification() const {
    return actif() && m_erreur.isEmpty() && !gesteEnCours() && attente()
        && texte(m_connexion,"etat")!=QLatin1String("annulation_demandee")
        && m_connexion.value(QStringLiteral("limiteEpoch")).toInteger()>QDateTime::currentSecsSinceEpoch()
        && urlVerificationAdmise(m_verificationUrl,texte(m_connexion,"moteur"));
}
bool ComptesViewModel::peutSaisirCode() const {
    if (!peutOuvrirVerification() || texte(m_connexion,"moteur")!=QLatin1String("claude_code")
        || texte(m_connexion,"etat")!=QLatin1String("code_disponible")
        || texte(m_connexion,"defiType")!=QLatin1String("claude_oauth_code")) return false;
    const auto reception=texte(m_connexion,"receptionCodeEtat");
    return m_soumission.isEmpty() || reception==QLatin1String("non_recue");
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
        {QStringLiteral("en_attente"),QStringLiteral("Préparation de la connexion")},
        {QStringLiteral("demarrage"),QStringLiteral("Préparation de la connexion")},
        {QStringLiteral("code_disponible"),QStringLiteral("Autorisation attendue dans votre navigateur")},
        {QStringLiteral("verification"),QStringLiteral("Vérification du compte")},
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
bool ComptesViewModel::urlVerificationAdmise(const QUrl &url, const QString &moteur) {
    if (!url.isValid() || url.toEncoded().size()>8192 || url.scheme()!=QLatin1String("https")
        || !url.userInfo().isEmpty() || url.hasFragment() || (url.port(-1)!=-1 && url.port(-1)!=443)) return false;
    if (moteur==QLatin1String("codex"))
        return url.host()==QLatin1String("auth.openai.com") && url.path(QUrl::FullyEncoded)==QLatin1String("/codex/device") && !url.hasQuery();
    if (moteur==QLatin1String("claude_code"))
        return url.host()==QLatin1String("claude.com") && url.path(QUrl::FullyEncoded)==QLatin1String("/cai/oauth/authorize")
            && url.hasQuery() && !url.query().isEmpty();
    return false;
}
bool ComptesViewModel::lireConnexion(const QJsonObject &o, const QString &identifiantAttendu) {
    const QString id=texte(o,"id"), etat=texte(o,"etat"), moteur=texte(o,"moteur");
    if (!identifiantConnexionValide(id) || (!identifiantAttendu.isEmpty() && id!=identifiantAttendu)
        || !QStringList{QStringLiteral("codex"),QStringLiteral("claude_code")}.contains(moteur)
        || (!enAttente(etat) && !QStringList{QStringLiteral("connecte"),QStringLiteral("annulee"),QStringLiteral("expiree"),QStringLiteral("interrompue"),QStringLiteral("erreur")}.contains(etat))) return false;
    if (etat==QLatin1String("connecte") && o.value(QStringLiteral("compte_connecte"))!=QJsonValue(true)) return false;
    if (id==texte(m_connexion,"id") && moteur!=texte(m_connexion,"moteur")) return false;
    QJsonObject c{{QStringLiteral("id"),id},{QStringLiteral("moteur"),moteur},{QStringLiteral("etat"),etat},
        {QStringLiteral("libelle"),libelleEtat(etat)}};
    // Les messages du défi Claude ne transportent jamais une sortie brute du CLI.
    if (moteur==QLatin1String("codex")) c.insert(QStringLiteral("message"),texte(o,"message"));
    else if (etat==QLatin1String("code_disponible")) c.insert(QStringLiteral("message"),QStringLiteral("Autorisez Claude dans votre navigateur, puis collez le code temporaire affiché par Anthropic."));
    else if (etat==QLatin1String("erreur")) c.insert(QStringLiteral("message"),QStringLiteral("La connexion n’a pas été confirmée. Vous pouvez recommencer la procédure."));
    else if (etat==QLatin1String("annulee")) c.insert(QStringLiteral("message"),QStringLiteral("La procédure a été annulée. Un compte déjà connecté peut rester disponible."));
    else if (etat==QLatin1String("expiree") || etat==QLatin1String("interrompue")) c.insert(QStringLiteral("message"),QStringLiteral("Cette procédure ne peut plus continuer. Recommencez la connexion pour obtenir un nouveau lien."));
    c.insert(QStringLiteral("limite"), o.value(QStringLiteral("limite_attente_le")).isDouble()
        ? QDateTime::fromSecsSinceEpoch(o.value(QStringLiteral("limite_attente_le")).toInteger()).toLocalTime().toString(QStringLiteral("HH:mm:ss"))
        : QStringLiteral("Inconnue"));
    c.insert(QStringLiteral("limiteEpoch"),o.value(QStringLiteral("limite_attente_le")));
    QUrl url;
    const QString defi=texte(o,"defi_id"), type=texte(o,"defi_type");
    if (id==texte(m_connexion,"id") && !defi.isEmpty() && !texte(m_connexion,"defiId").isEmpty() && defi!=texte(m_connexion,"defiId")) return false;
    if (enAttente(etat) && etat!=QLatin1String("annulation_demandee") && !defi.isEmpty()) {
        if (!identifiantConnexionValide(defi) || type!=(moteur==QLatin1String("codex")?QStringLiteral("codex_device"):QStringLiteral("claude_oauth_code"))) return false;
        const auto brute=o.value(QStringLiteral("verification_url"));
        if (!brute.isString() || brute.toString().toUtf8().size()>8192) return false;
        url=QUrl(brute.toString(),QUrl::StrictMode);
        if (!urlVerificationAdmise(url,moteur)) return false;
        c.insert(QStringLiteral("defiId"),defi); c.insert(QStringLiteral("defiType"),type);
        if (moteur==QLatin1String("codex")) {
            c.insert(QStringLiteral("url"),url.toString()); c.insert(QStringLiteral("code"),texte(o,"code_utilisateur",64));
        } else if (!o.value(QStringLiteral("code_utilisateur")).isNull() && !o.value(QStringLiteral("code_utilisateur")).isUndefined()) return false;
    } else if (etat==QLatin1String("code_disponible")) {
        // Après redémarrage, l'opération subsiste mais son lien en RAM peut manquer.
        if (!type.isEmpty() || !o.value(QStringLiteral("verification_url")).toString().isEmpty()
            || !o.value(QStringLiteral("code_utilisateur")).toString().isEmpty()) return false;
        c.insert(QStringLiteral("libelle"),QStringLiteral("Lien de connexion indisponible"));
        c.insert(QStringLiteral("message"),QStringLiteral("Le lien n’est plus disponible. Attendez la vérification du compte, ou annulez cette procédure puis recommencez la connexion."));
    }
    QString soumission=m_soumission, defiSoumission=m_defiSoumission;
    if (id!=texte(m_connexion,"id") || (!defi.isEmpty() && !defiSoumission.isEmpty() && defi!=defiSoumission)) { soumission.clear(); defiSoumission.clear(); }
    const auto recu=o.value(QStringLiteral("reception_code"));
    if (!recu.isNull() && !recu.isUndefined()) {
        if (!recu.isObject() || moteur!=QLatin1String("claude_code")) return false;
        const auto r=recu.toObject(); const auto sr=texte(r,"soumission_id"), dr=texte(r,"defi_id"), er=texte(r,"etat");
        if (!identifiantConnexionValide(sr) || (!soumission.isEmpty() && sr!=soumission)
            || (!dr.isEmpty() && (!identifiantConnexionValide(dr) || (!defi.isEmpty() && dr!=defi) || (!defiSoumission.isEmpty() && dr!=defiSoumission)))
            || !QStringList{QStringLiteral("non_recue"),QStringLiteral("en_attente"),QStringLiteral("transmis"),QStringLiteral("perdu")}.contains(er)) return false;
        soumission=sr; if (defiSoumission.isEmpty()) defiSoumission=dr.isEmpty()?defi:dr;
        if (!identifiantConnexionValide(defiSoumission)) return false;
        c.insert(QStringLiteral("receptionCodeEtat"),er);
    }
    const bool changer=id!=texte(m_connexion,"id") || defi!=texte(m_connexion,"defiId") || !enAttente(etat);
    m_connexion=c; m_verificationUrl=url;
    m_soumission=soumission; m_defiSoumission=defiSoumission;
    if (!enAttente(etat)) { m_cle.clear(); m_moteurCle.clear(); m_soumission.clear(); m_defiSoumission.clear(); }
    if (changer) emit effacerCodeTemporaire();
    return true;
}
bool ComptesViewModel::lireComptes(const QJsonObject &o) {
    if (texte(o,"protocole")!=QLatin1String("acp-comptes/2") || !o.value(QStringLiteral("serveur")).isObject()
        || !o.value(QStringLiteral("comptes")).isArray()) return false;
    const auto serveur=o.value(QStringLiteral("serveur")).toObject();
    if (!serveur.value(QStringLiteral("disponible")).isBool()) return false;
    QVariantList comptes;
    QJsonObject connexion;
    int connexionsActives=0;
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
        QVariantList alias;
        if (moteur==QLatin1String("claude_code")) {
            for (const auto &aliasLu:c.value(QStringLiteral("alias_documentes")).toArray()) {
                if (alias.size()>=100) break;
                const QString nom=aliasLu.isObject()?texte(aliasLu.toObject(),"id",200):aliasLu.toString().left(200);
                if (!nom.isEmpty()) alias.append(nom);
            }
        }
        comptes.append(QVariantMap{{QStringLiteral("moteur"),moteur},{QStringLiteral("nom"),texte(c,"nom",100)},
            {QStringLiteral("implementation"),texte(c,"implementation")},{QStringLiteral("etat"),etat},
            {QStringLiteral("libelle"),libelleEtat(etat)},{QStringLiteral("version"),texte(c,"version",100)},
            {QStringLiteral("message"),texte(c,"message")},{QStringLiteral("modeles"),modeles},{QStringLiteral("aliasDocumentes"),alias},
            {QStringLiteral("observation"),libelleObservation},{QStringLiteral("observationEtat"),etatObservation},
            {QStringLiteral("quotasRapportes"),etatObservation==QLatin1String("a_jour") ? observation.value(QStringLiteral("quotas")).toArray().size() : 0},
            {QStringLiteral("compteConnecte"),c.value(QStringLiteral("compte_connecte")).isBool()
                ? QVariant(c.value(QStringLiteral("compte_connecte")).toBool()) : QVariant()},
            {QStringLiteral("inferenceVerifiee"),c.value(QStringLiteral("inference_verifiee"))==QJsonValue(true)}});
        if (c.value(QStringLiteral("connexion")).isObject()) {
            const auto candidate=c.value(QStringLiteral("connexion")).toObject();
            if (texte(candidate,"moteur")!=moteur) return false;
            if (enAttente(texte(candidate,"etat"))) {
                if (++connexionsActives>1) return false;
                connexion=candidate;
            } else if (connexionsActives==0 && (connexion.isEmpty() || texte(candidate,"id")==texte(m_connexion,"id")
                       || (texte(connexion,"id")!=texte(m_connexion,"id") && candidate.value(QStringLiteral("actualise_le")).toInteger()>connexion.value(QStringLiteral("actualise_le")).toInteger()))) connexion=candidate;
        }
    }
    if (comptes.isEmpty()) return false;
    if (!connexion.isEmpty() && !lireConnexion(connexion)) return false;
    if (connexion.isEmpty()) { m_connexion={}; m_verificationUrl={}; m_soumission.clear(); m_defiSoumission.clear(); emit effacerCodeTemporaire(); }
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
    if (active) actualiser(); else { m_timer->stop(); abandonnerLecture(); emit effacerCodeTemporaire(); emit change(); }
}
void ComptesViewModel::surLienRetabli() { actualiser(); }
void ComptesViewModel::surOubli() {
    ++m_generation; m_timer->stop(); abandonnerLecture();
    if (m_mutation) { auto appel=m_mutation; m_mutation=nullptr; appel->disconnect(this); appel->abort(); }
    m_comptes.clear(); m_serveur.clear(); m_connexion={}; m_cle.clear(); m_moteurCle.clear(); m_erreur.clear(); m_lue=false;
    m_verificationUrl={}; m_soumission.clear(); m_defiSoumission.clear(); emit effacerCodeTemporaire();
    terminerGeste({}); emit change();
}
void ComptesViewModel::actualiser() {
    if (!actif() || m_appel || m_mutation) return;
    m_timer->stop(); const auto generation=m_generation; const bool suivi=attente();
    const QString id=suivi?texte(m_connexion,"id"):QString();
    m_appel=suivi ? m_greffon->connexionCompte(id,m_defiSoumission,m_soumission) : m_greffon->comptes();
    connect(m_appel,&ApiCall::succeeded,this,[this,generation,suivi,id](const ApiResponse &r) {
        if (generation!=m_generation) return;
        m_appel=nullptr;
        const bool valide=suivi ? lireConnexion(r.json.object(),id) : lireComptes(r.json.object());
        m_erreur=valide ? QString() : QStringLiteral("Réponse des comptes incompatible ou illisible. Actualisez avant de poursuivre.");
        if (!suivi && texte(r.json.object(),"protocole")!=QLatin1String("acp-comptes/2"))
            m_erreur=QStringLiteral("Les versions de connexion ne correspondent pas. Mettez ACP à jour avant de connecter un compte.");
        if (!valide) emit effacerCodeTemporaire();
        else if (suivi && (!texte(m_connexion,"receptionCodeEtat").isEmpty() || !attente())) effacerGeste();
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
void ComptesViewModel::connecterCodex() { if(peutConnecter()) geste(false,QStringLiteral("codex")); }
void ComptesViewModel::connecterClaude() { if(peutConnecterClaude()) geste(false,QStringLiteral("claude_code")); }
void ComptesViewModel::annulerConnexion() { if(actif() && attente() && !gesteEnCours()) geste(true); }
void ComptesViewModel::geste(bool annulation, const QString &moteur) {
    abandonnerLecture(); m_timer->stop(); const auto generation=m_generation;
    if (!annulation && (m_cle.isEmpty() || m_moteurCle!=moteur)) {
        m_cle=QUuid::createUuid().toString(QUuid::WithoutBraces); m_moteurCle=moteur;
    }
    const QString id=annulation?texte(m_connexion,"id"):QString();
    if (annulation) emit effacerCodeTemporaire();
    debuterGeste();
    m_mutation=annulation ? m_greffon->annulerConnexionCompte(id) : moteur==QLatin1String("claude_code")
        ? m_greffon->connecterCompteClaude(m_cle) : m_greffon->connecterCompteCodex(m_cle);
    connect(m_mutation,&ApiCall::succeeded,this,[this,generation,annulation,id](const ApiResponse &r) {
        if(generation!=m_generation) return; m_mutation=nullptr;
        if(!lireConnexion(r.json.object(),id)) echouerGeste(QStringLiteral("Réponse de connexion illisible. Actualisez pour retrouver son état."));
        else terminerGeste(annulation ? QStringLiteral("Annulation demandée. L’état sera actualisé automatiquement.") : QStringLiteral("Procédure lancée. Continuez dans votre navigateur."));
        emit change(); programmer();
    });
    connect(m_mutation,&ApiCall::failed,this,[this,generation](const ApiError &) {
        if(generation!=m_generation) return; m_mutation=nullptr;
        echouerGeste(QStringLiteral("La demande n’a pas été confirmée. Actualisez son état avant de réessayer.")); emit change(); programmer();
    }); emit change();
}
void ComptesViewModel::soumettreCode(const QString &code) {
    // La page a déjà vidé son champ ; aucune copie n'est conservée dans le ViewModel.
    emit effacerCodeTemporaire();
    if (!peutSaisirCode()) { echouerGeste(QStringLiteral("Ce code ne peut pas être envoyé maintenant. Actualisez la connexion.")); return; }
    if (!ClientGreffonPoste::codeConnexionValide(code)) { echouerGeste(QStringLiteral("Collez le code temporaire sur une seule ligne, de 1 à 2 048 octets.")); return; }
    abandonnerLecture(); m_timer->stop(); const auto generation=m_generation; const QString id=texte(m_connexion,"id");
    if (m_soumission.isEmpty()) { m_soumission=QUuid::createUuid().toString(QUuid::WithoutBraces); m_defiSoumission=texte(m_connexion,"defiId"); }
    m_connexion.remove(QStringLiteral("receptionCodeEtat"));
    debuterGeste();
    m_mutation=m_greffon->soumettreCodeCompte(id,m_defiSoumission,m_soumission,code);
    connect(m_mutation,&ApiCall::succeeded,this,[this,generation,id](const ApiResponse &r) {
        if (generation!=m_generation) return; m_mutation=nullptr;
        if (!lireConnexion(r.json.object(),id) || !QStringList{QStringLiteral("en_attente"),QStringLiteral("transmis")}.contains(texte(m_connexion,"receptionCodeEtat")))
            echouerGeste(QStringLiteral("Réception du code non confirmée. ACP vérifie l’état de la demande."));
        else terminerGeste(QStringLiteral("Code reçu pour transmission. La connexion reste à confirmer."));
        emit change(); actualiser();
    });
    connect(m_mutation,&ApiCall::failed,this,[this,generation](const ApiError &) {
        if (generation!=m_generation) return; m_mutation=nullptr;
        echouerGeste(QStringLiteral("Réception du code non confirmée. ACP vérifie l’état avant toute nouvelle saisie."));
        emit change(); actualiser();
    }); emit change();
}
bool ComptesViewModel::ouvrirVerification() {
    if (!peutOuvrirVerification()) {
        echouerGeste(QStringLiteral("Ce lien ne peut pas être ouvert maintenant. Actualisez l’état de la connexion.")); return false;
    }
    if(m_ouvreur(m_verificationUrl)) return true;
    echouerGeste(QStringLiteral("Le navigateur n’a pas pu être ouvert. Vérifiez votre navigateur par défaut, puis réessayez.")); return false;
}
}
