#include "viewmodels/JournalExecutionViewModel.h"
#include "api/ApiClient.h"
#include "api/ClientGreffonPoste.h"
#include <QTimer>
#include <cmath>
namespace acp {
namespace {
bool entier(const QJsonValue &v) { return v.isDouble() && v.toDouble() >= 0 && v.toDouble() <= 9007199254740991.0 && std::floor(v.toDouble()) == v.toDouble(); }
QString texte(const QJsonObject &o, const char *cle, int maximum = 1000) { return o.value(QLatin1String(cle)).toString().left(maximum); }
}
JournalExecutionViewModel::JournalExecutionViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent)
    : PageViewModel(flux, parent), m_greffon(greffon), m_timer(new QTimer(this)), m_evenements(this) {
    m_evenements.setCle({QStringLiteral("id")});
    m_timer->setSingleShot(true);
    connect(m_timer, &QTimer::timeout, this, &JournalExecutionViewModel::actualiser);
}
JournalExecutionViewModel::~JournalExecutionViewModel() { abandonnerLecture(); }
void JournalExecutionViewModel::abandonnerLecture() {
    ++m_generation;
    if (m_appel) { auto appel=m_appel; m_appel=nullptr; appel->disconnect(this); appel->abort(); }
}
void JournalExecutionViewModel::choisirProjet(const QString &id) {
    if (id == m_projet) return;
    surOubli();
    if (!id.isEmpty() && !ClientGreffonPoste::identifiantValide(id)) {
        m_erreur=QStringLiteral("Identifiant du projet illisible."); emit change(); return;
    }
    m_projet=id; emit change(); actualiser();
}
void JournalExecutionViewModel::surOubli() {
    m_timer->stop(); abandonnerLecture(); m_projet.clear(); m_erreur.clear(); m_evenements.clear();
    m_ids.clear(); m_curseur=0; m_lue=false; m_historiqueBorne=false; emit change();
}
void JournalExecutionViewModel::surActivite(bool actif) {
    if (actif) actualiser(); else { m_timer->stop(); abandonnerLecture(); emit change(); }
}
void JournalExecutionViewModel::surLienRetabli() { actualiser(); }
bool JournalExecutionViewModel::lire(const QJsonObject &o, bool *encore) {
    const auto lignes=o.value(QStringLiteral("evenements"));
    const auto suivant=o.value(QStringLiteral("prochain_curseur"));
    if (texte(o,"projet_id",200)!=m_projet || !lignes.isArray() || lignes.toArray().size()>200 || !entier(suivant)
        || suivant.toInteger()<m_curseur || !o.value(QStringLiteral("encore")).isBool()) return false;
    *encore=o.value(QStringLiteral("encore")).toBool();
    if (*encore && suivant.toInteger()<=m_curseur) return false;
    QJsonArray ajouts;
    QSet<QString> ids;
    qint64 precedent=0;
    for (const auto &v:lignes.toArray()) {
        if (!v.isObject()) return false;
        const auto e=v.toObject(); const auto c=e.value(QStringLiteral("curseur"));
        const auto id=texte(e,"id",200);
        if (id.isEmpty() || !entier(c) || c.toInteger()<1 || c.toInteger()<precedent
            || c.toInteger()>suivant.toInteger() || texte(e,"projet_id",200)!=m_projet) return false;
        precedent=c.toInteger();
        if (m_ids.contains(id) || ids.contains(id) || c.toInteger()<=m_curseur) continue;
        QJsonObject ligne{{QStringLiteral("id"),id},{QStringLiteral("curseur"),c}};
        for (const char *cle:{"projet_id","carte","machine_id","agent","tentative_id","quand","moteur","session_native","modele_demande","modele_servi","parent_natif","item_natif","genre","outil"})
            ligne.insert(QLatin1String(cle),texte(e,cle));
        const auto run=e.value(QStringLiteral("run_id"));
        if (!run.isUndefined() && !run.isNull() && !entier(run)) return false;
        ligne.insert(QStringLiteral("run_id"),entier(run) ? QString::number(run.toInteger()) : QString());
        ligne.insert(QStringLiteral("texte"),texte(e,"texte",12000));
        ligne.insert(QStringLiteral("ordre"),e.value(QStringLiteral("ordre")).toInteger());
        QStringList parents;
        for (const auto &parent:e.value(QStringLiteral("parents")).toArray()) {
            if (parents.size()>=50) break;
            if (parent.isString()) parents.append(parent.toString().left(200));
        }
        ligne.insert(QStringLiteral("parents"),parents.join(QStringLiteral(" · ")));
        ids.insert(id); ajouts.append(ligne);
    }
    // La borne concerne seulement la vue en mémoire ; l'historique reste sur le serveur.
    if (m_evenements.count()+ajouts.size()>5000) {
        QJsonArray gardes;
        const int debut=qMax(0,m_evenements.count()+int(ajouts.size())-5000);
        for (int i=debut;i<m_evenements.count();++i) gardes.append(m_evenements.itemAt(i));
        for (const auto &v:ajouts) gardes.append(v);
        m_evenements.setItems(gardes); m_ids.clear();
        for (const auto &v:gardes) m_ids.insert(v.toObject().value(QStringLiteral("id")).toString());
        m_historiqueBorne=true;
    } else {
        for (const auto &v:ajouts) m_evenements.appendItem(v.toObject());
        m_ids.unite(ids);
    }
    m_curseur=suivant.toInteger(); m_lue=true; return true;
}
void JournalExecutionViewModel::actualiser() {
    if (!actif() || m_appel || m_projet.isEmpty()) return;
    m_timer->stop(); const auto generation=m_generation;
    m_appel=m_greffon->evenementsProjet(m_projet,m_curseur);
    connect(m_appel,&ApiCall::succeeded,this,[this,generation](const ApiResponse &r) {
        if (generation!=m_generation) return;
        m_appel=nullptr; bool encore=false;
        const bool valide=lire(r.json.object(),&encore);
        m_erreur=valide ? QString() : QStringLiteral("Journal illisible : le curseur a été conservé pour réessayer sans perdre la suite.");
        emit change();
        if (actif()) m_timer->start(valide && encore ? 0 : m_intervalle);
    });
    connect(m_appel,&ApiCall::failed,this,[this,generation](const ApiError &e) {
        if (generation!=m_generation) return;
        m_appel=nullptr;
        m_erreur=e.httpStatus()==404 ? QStringLiteral("Le journal d’exécution n’est pas disponible pour ce projet sur ce serveur.") : messageDuRefus(e);
        emit change(); if (actif()) m_timer->start(m_intervalle);
    });
    emit change();
}
}
