// Espace de travail de la station (chantier « atelier », D166 et D167).
//
// Ce modèle de vue ne lit rien de plus que ce que le greffon sert déjà :
//
// - la barre latérale : GET /v1/projets, relu par son propre sondage (mêmes sujets
//   d'invalidation que la page Projets), et REGROUPÉ PAR DÉPÔT. Un « projet » du greffon est
//   une MISSION dans le vocabulaire du brief ; le projet durable n'existe pas encore côté
//   serveur (lot C) : le regroupement par dépôt est une projection d'un champ servi, jamais
//   une donnée inventée ;
// - le panneau des agents, les tests et les sorties : le détail de la mission ouverte, tel que
//   ProjetsViewModel l'a lu (GET /v1/projets/{id}, cartes et journal). Un agent est une carte
//   kanban ; une relecture est rangée sous la carte qu'elle relit (champ `relue`). Les
//   sessions des CLI et les sous-agents natifs ne sont pas remontés par l'exécutant : le
//   panneau le dit, il ne les simule pas ;
// - les brouillons de la saisie : en mémoire seulement, oubliés avec la session (oubli local,
//   docs/desktop-security.md) ; jamais dans QSettings.

#pragma once

#include "viewmodels/PageViewModel.h"

#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QSet>
#include <QString>
#include <QVariantMap>

namespace acp {

class ClientGreffonPoste;
class JsonListModel;
class NavigationModel;
class ProjetsViewModel;
class Sondage;

class EspaceTravailViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *arbre READ arbre CONSTANT)
    Q_PROPERTY(bool listeLue READ listeLue NOTIFY arbreChange)
    Q_PROPERTY(int nombreMissions READ nombreMissions NOTIFY arbreChange)
    Q_PROPERTY(int nombreProjets READ nombreProjets NOTIFY arbreChange)
    Q_PROPERTY(QString recherche READ recherche WRITE setRecherche NOTIFY arbreChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)
    Q_PROPERTY(QString missionSelectionnee READ missionSelectionnee NOTIFY selectionChange)
    Q_PROPERTY(QVariantMap mission READ mission NOTIFY missionChange)
    Q_PROPERTY(JsonListModel *agents READ agents CONSTANT)
    Q_PROPERTY(QString agentSelectionne READ agentSelectionne WRITE setAgentSelectionne NOTIFY agentChange)
    Q_PROPERTY(QVariantMap agent READ agent NOTIFY agentChange)
    Q_PROPERTY(JsonListModel *essais READ essais CONSTANT)
    Q_PROPERTY(JsonListModel *sorties READ sorties CONSTANT)

public:
    EspaceTravailViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, ProjetsViewModel *projets,
                           NavigationModel *navigation, QObject *parent = nullptr);
    ~EspaceTravailViewModel() override;

    [[nodiscard]] JsonListModel *arbre() const { return m_arbre; }
    [[nodiscard]] bool listeLue() const { return m_listeLue; }
    [[nodiscard]] int nombreMissions() const { return m_nombreMissions; }
    [[nodiscard]] int nombreProjets() const { return m_nombreProjets; }
    [[nodiscard]] const QString &recherche() const { return m_recherche; }
    void setRecherche(const QString &recherche);
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] QString erreur() const;
    [[nodiscard]] const QString &missionSelectionnee() const { return m_missionSelectionnee; }
    [[nodiscard]] const QVariantMap &mission() const { return m_mission; }
    [[nodiscard]] JsonListModel *agents() const { return m_agents; }
    [[nodiscard]] const QString &agentSelectionne() const { return m_agentSelectionne; }
    void setAgentSelectionne(const QString &cle);
    [[nodiscard]] QVariantMap agent() const;
    [[nodiscard]] JsonListModel *essais() const { return m_essais; }
    [[nodiscard]] JsonListModel *sorties() const { return m_sorties; }

    /*! Déplie ou replie un groupe (« g:<dépôt> ») ou les missions archivées d'un groupe (« a:<dépôt> »). */
    Q_INVOKABLE void basculer(const QString &cle);

    /*! Affiche une mission au centre. Lecture seule : aucun geste n'est envoyé au serveur. */
    Q_INVOKABLE void selectionnerMission(const QString &identifiant);

    /*! Ouvre le formulaire de nouvelle mission, dépôt présélectionné (vide : au choix). */
    Q_INVOKABLE void nouvelleMission(const QString &depot);

    /*! Brouillon de la saisie pour un contexte (« mission:<id> », « projet:<dépôt> »…), en mémoire. */
    Q_INVOKABLE QString brouillon(const QString &contexte) const;
    Q_INVOKABLE void noterBrouillon(const QString &contexte, const QString &texte);

    /*! Pictogramme décoratif d'une clé : {motif, teinte}, stable d'une exécution à l'autre. */
    Q_INVOKABLE static QVariantMap pictogramme(const QString &cle);

    // Constructions pures, publiques pour les tests.
    [[nodiscard]] static QJsonArray construireArbre(const QJsonArray &projets, const QString &recherche,
                                                    const QSet<QString> &replies, const QSet<QString> &archivesOuvertes,
                                                    const QString &selection);
    [[nodiscard]] static QJsonArray construireAgents(const QJsonObject &projet);
    [[nodiscard]] static QJsonArray construireEssais(const QJsonObject &projet);
    [[nodiscard]] static QJsonArray construireSorties(const QJsonObject &projet);
    [[nodiscard]] static QJsonObject etatAgent(const QString &statut);
    [[nodiscard]] static QString portraitDuRole(const QString &role);
    [[nodiscard]] static QString libelleSourceRoutage(const QString &source);

signals:
    void arbreChange();
    void lectureChange();
    void selectionChange();
    void missionChange();
    void agentChange();
    void brouillonChange(const QString &contexte);

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lireListe(const QJsonObject &liste);
    void reconstruireArbre();
    void lireDetail();

    ProjetsViewModel *m_projets = nullptr;
    NavigationModel *m_navigation = nullptr;
    Sondage *m_liste = nullptr;
    JsonListModel *m_arbre = nullptr;
    JsonListModel *m_agents = nullptr;
    JsonListModel *m_essais = nullptr;
    JsonListModel *m_sorties = nullptr;
    QJsonArray m_projetsLus;
    bool m_listeLue = false;
    int m_nombreMissions = 0;
    int m_nombreProjets = 0;
    QString m_recherche;
    QSet<QString> m_replies;
    QSet<QString> m_archivesOuvertes;
    QString m_missionSelectionnee;
    QVariantMap m_mission;
    QString m_agentSelectionne;
    QHash<QString, QString> m_brouillons;
};

} // namespace acp
