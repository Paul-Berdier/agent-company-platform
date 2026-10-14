// Coffre jetable en mémoire derrière le faux Hermes ; aucun fichier personnel ni bridge réseau.
#pragma once
#include "support/FauxHermes.h"
#include <QCryptographicHash>
#include <QDateTime>
#include <QJsonArray>
#include <QMap>
#include <algorithm>

namespace acp::test {
inline QString coffreEmpreinte(const QString &texte)
{ return QString::fromLatin1(QCryptographicHash::hash(texte.toUtf8(),QCryptographicHash::Sha256).toHex()); }
struct FauxCoffre {
    const QString prefixe=QStringLiteral("/api/plugins/acp-poste/v1/coffre");
    const QString id=QStringLiteral("12345678-1234-4123-8123-123456789abc");
    QString etat=QStringLiteral("pret");
    QMap<QString,QString> fichiers{{QStringLiteral("Accueil.md"),QStringLiteral("# Accueil\n[[Projet]]")},
                                  {QStringLiteral("Projet.md"),QStringLiteral("# Projet\nUne note distante.")}};
    QHash<QString,QJsonObject> operations;
    QList<QJsonObject> demandes;
    bool attendre=false;
    int delai=0;
    QJsonObject statut() const {
        return {{QStringLiteral("protocole"),QStringLiteral("acp-coffre/1")},{QStringLiteral("etat"),etat},
            {QStringLiteral("coffre"),etat==QLatin1String("non_configure") ? QJsonValue(QJsonValue::Null) : QJsonValue(QJsonObject{
                {QStringLiteral("coffre_id"),id},{QStringLiteral("alias"),QStringLiteral("acp")},
                {QStringLiteral("empreinte"),QStringLiteral("ABCD-1234")},{QStringLiteral("etat"),QStringLiteral("actif")},
                {QStringLiteral("derniere_vue"),QDateTime::currentSecsSinceEpoch()},
                {QStringLiteral("capacites"),QJsonArray{QStringLiteral("lister"),QStringLiteral("lire"),QStringLiteral("rechercher"),
                    QStringLiteral("creer"),QStringLiteral("ecrire"),QStringLiteral("archiver"),QStringLiteral("renommer"),
                    QStringLiteral("backlinks"),QStringLiteral("graphe")}}})}};
    }
    void terminer(const QString &operationId) {
        auto &op=operations[operationId];
        if (op.value(QStringLiteral("etat"))==QLatin1String("reussie") || op.value(QStringLiteral("etat"))==QLatin1String("refusee")) return;
        const auto requete=*std::find_if(demandes.cbegin(),demandes.cend(),[&](const QJsonObject &d){return d.value(QStringLiteral("id_operation"))==operationId;});
        const auto p=requete.value(QStringLiteral("parametres")).toObject();
        const QString action=requete.value(QStringLiteral("action")).toString(), chemin=p.value(QStringLiteral("chemin")).toString();
        QJsonObject resultat; QString refus;
        if (action==QLatin1String("lister")) {
            QJsonArray notes; for (auto i=fichiers.cbegin();i!=fichiers.cend();++i) notes.append(QJsonObject{{QStringLiteral("chemin"),i.key()},{QStringLiteral("octets"),i.value().toUtf8().size()}});
            resultat={{QStringLiteral("notes"),notes},{QStringLiteral("tronque"),false}};
        } else if (action==QLatin1String("rechercher")) {
            QJsonArray notes; for (auto i=fichiers.cbegin();i!=fichiers.cend();++i)
                if (i.value().contains(p.value(QStringLiteral("texte")).toString(),Qt::CaseInsensitive))
                    notes.append(QJsonObject{{QStringLiteral("chemin"),i.key()},{QStringLiteral("ligne"),1},{QStringLiteral("extrait"),i.value()}});
            resultat={{QStringLiteral("resultats"),notes},{QStringLiteral("tronque"),false}};
        } else if (action==QLatin1String("graphe")) {
            QJsonArray noeuds; for (auto i=fichiers.cbegin();i!=fichiers.cend();++i) noeuds.append(QJsonObject{{QStringLiteral("chemin"),i.key()}});
            resultat={{QStringLiteral("noeuds"),noeuds},{QStringLiteral("liens"),QJsonArray{QJsonObject{{QStringLiteral("source"),QStringLiteral("Accueil.md")},{QStringLiteral("cible"),QStringLiteral("Projet.md")}}}},
                {QStringLiteral("non_resolus"),QJsonArray{}},{QStringLiteral("tronque"),false},{QStringLiteral("portee"),QStringLiteral("Liens Markdown et wikiliens ; extensions Obsidian non interprétées.")}};
        } else if (action==QLatin1String("backlinks")) {
            resultat={{QStringLiteral("chemin"),chemin},{QStringLiteral("liens"),QJsonArray{QJsonObject{{QStringLiteral("source"),QStringLiteral("Accueil.md")},{QStringLiteral("cible"),chemin}}}},{QStringLiteral("tronque"),false}};
        } else if (action==QLatin1String("creer")) {
            if (fichiers.contains(chemin)) refus=QStringLiteral("deja_existant");
            else { fichiers[chemin]=p.value(QStringLiteral("contenu")).toString(); resultat={{QStringLiteral("chemin"),chemin},{QStringLiteral("empreinte"),coffreEmpreinte(fichiers[chemin])}}; }
        } else if (!fichiers.contains(chemin)) refus=QStringLiteral("absent");
        else if (action==QLatin1String("lire")) resultat={{QStringLiteral("chemin"),chemin},{QStringLiteral("contenu"),fichiers[chemin]},
            {QStringLiteral("empreinte"),coffreEmpreinte(fichiers[chemin])},{QStringLiteral("octets"),fichiers[chemin].toUtf8().size()}};
        else if (p.value(QStringLiteral("empreinte_attendue"))!=coffreEmpreinte(fichiers[chemin])) refus=QStringLiteral("conflit");
        else if (action==QLatin1String("ecrire")) { fichiers[chemin]=p.value(QStringLiteral("contenu")).toString(); resultat={{QStringLiteral("chemin"),chemin},{QStringLiteral("empreinte"),coffreEmpreinte(fichiers[chemin])}}; }
        else if (action==QLatin1String("archiver")) { fichiers.remove(chemin); resultat={{QStringLiteral("chemin"),chemin},{QStringLiteral("archive_id"),QStringLiteral("archive-test")}}; }
        else if (action==QLatin1String("renommer")) {
            const auto destination=p.value(QStringLiteral("destination")).toString();
            if (fichiers.contains(destination)) refus=QStringLiteral("deja_existant");
            else { fichiers[destination]=fichiers.take(chemin); resultat={{QStringLiteral("chemin"),chemin},{QStringLiteral("destination"),destination},
                {QStringLiteral("empreinte"),coffreEmpreinte(fichiers[destination])},{QStringLiteral("liens_modifies"),false}}; }
        }
        op.insert(QStringLiteral("etat"),refus.isEmpty()?QStringLiteral("reussie"):QStringLiteral("refusee"));
        op.insert(QStringLiteral("resultat"),resultat);
        op.insert(QStringLiteral("erreur"),refus.isEmpty()?QJsonValue(QJsonValue::Null):QJsonValue(QJsonObject{{QStringLiteral("code"),refus},{QStringLiteral("message"),QStringLiteral("Refus du coffre : ")+refus}}));
    }
    void installer(FauxHermes &serveur) {
        serveur.route("GET",prefixe,[this](const RequeteRecue&){return ReponseFaux::json(200,statut());});
        serveur.route("POST",prefixe+QStringLiteral("/enrolement"),[](const RequeteRecue&){return ReponseFaux::json(201,QJsonObject{
            {QStringLiteral("protocole"),QStringLiteral("acp-coffre/1")},{QStringLiteral("code"),QStringLiteral("acpce_")+QString(43,QLatin1Char('x'))},
            {QStringLiteral("expire_le"),QDateTime::currentSecsSinceEpoch()+2},{QStringLiteral("validite_s"),600}});});
        serveur.route("POST",prefixe+QStringLiteral("/confirmer"),[this](const RequeteRecue&){etat=QStringLiteral("pret");return ReponseFaux::json(200,statut());});
        serveur.route("POST",prefixe+QStringLiteral("/revoquer"),[this](const RequeteRecue&){etat=QStringLiteral("revoque");return ReponseFaux::json(200,statut());});
        serveur.route("POST",prefixe+QStringLiteral("/operations"),[this,&serveur](const RequeteRecue &r){
            const auto d=r.json(); demandes.append(d); const auto cle=d.value(QStringLiteral("id_operation")).toString();
            operations[cle]={{QStringLiteral("id_operation"),cle},{QStringLiteral("coffre_id"),id},{QStringLiteral("action"),d.value(QStringLiteral("action"))},
                {QStringLiteral("etat"),QStringLiteral("en_attente")},{QStringLiteral("cree_le"),QDateTime::currentSecsSinceEpoch()},
                {QStringLiteral("expire_le"),QDateTime::currentSecsSinceEpoch()+120},{QStringLiteral("resultat"),QJsonValue::Null},{QStringLiteral("erreur"),QJsonValue::Null}};
            if (!attendre) terminer(cle);
            serveur.route("GET",prefixe+QStringLiteral("/operations/")+cle,[this,cle](const RequeteRecue&){return ReponseFaux::json(200,operations.value(cle));});
            auto reponse=ReponseFaux::json(202,operations[cle]); reponse.delaiMs=delai; return reponse;
        });
    }
};
}
