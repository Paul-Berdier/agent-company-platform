// Page Routage de la station (cahier P8 § 7.7, décision D8-6), sur `GET /v1/routage` du
// greffon, relu toutes les 15 s tant que la page est affichée. Même contenu que la vue
// « Routage » de la page web (apps/interface/src/poste/Routage.tsx), gestes réduits :
//
//  - listes relevées par voie du poste : badge (Relevé du compte, Liste de secours probable,
//    Alias documentés, Périmé, Inconnu…), date, version de la CLI, modèles et efforts ;
//    « Accepter ce relevé comme celui de mon compte » quand le greffon le permet
//    (`liste_de_secours_probable` avec un `releve_id`) → `POST /v1/routage/releve-accepte` ;
//  - table par classe : état, entrées enregistrées et verdict du greffon, suggestion. La
//    station tient un BROUILLON par classe, bâti depuis la table lue et rebâti seulement quand
//    un nouveau relevé arrive (comme la page web) ; gestes du brouillon : « Appliquer la
//    suggestion », « Retirer » une entrée, « Revenir à la table enregistrée ». « Valider la
//    table » → `POST /v1/routage {releves, classes}` avec les relevés lus et les classes non
//    vides du brouillon : complète ou rien ; 409 `releve_change` dit puis relu ; 422
//    `table_refusee` : chaque refus affiché à sa ligne, rien n'est enregistré ;
//  - interdits côté Hermes et interdits du poste : lecture seule ;
//  - surcharges globales actives : « Désactiver » → `POST /v1/routage/surcharges/{id}/desactiver`.
//
// Édition libre d'une entrée, création d'une surcharge et interdits côté Hermes : « Modifier
// dans le navigateur » (page web, mêmes contrôles du greffon), décision D8-6.

#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QUrl>
#include <QVariantMap>

#include <functional>

namespace acp {

class ApiClient;
class ClientGreffonPoste;
class Sondage;

class RoutageViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(bool lue READ lue NOTIFY routageChange)
    Q_PROPERTY(JsonListModel *listes READ listes CONSTANT)
    Q_PROPERTY(JsonListModel *classes READ classes CONSTANT)
    Q_PROPERTY(JsonListModel *surcharges READ surcharges CONSTANT)
    Q_PROPERTY(QVariantMap politiqueHermes READ politiqueHermes NOTIFY routageChange)
    Q_PROPERTY(QVariantMap politiquePoste READ politiquePoste NOTIFY routageChange)
    Q_PROPERTY(bool releveFactice READ releveFactice NOTIFY routageChange)
    Q_PROPERTY(bool brouillonModifie READ brouillonModifie NOTIFY routageChange)
    Q_PROPERTY(bool brouillonVide READ brouillonVide NOTIFY routageChange)
    Q_PROPERTY(QStringList refusTable READ refusTable NOTIFY routageChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)

public:
    RoutageViewModel(ApiClient *client, ClientGreffonPoste *greffon, EventStreamService *flux,
                     QObject *parent = nullptr);
    ~RoutageViewModel() override;

    using Ouvreur = std::function<bool(const QUrl &)>;
    void setOuvreur(Ouvreur ouvreur) { m_ouvreur = std::move(ouvreur); }

    [[nodiscard]] bool lue() const { return m_lue; }
    [[nodiscard]] JsonListModel *listes() const { return m_listes; }
    [[nodiscard]] JsonListModel *classes() const { return m_classes; }
    [[nodiscard]] JsonListModel *surcharges() const { return m_surcharges; }
    [[nodiscard]] const QVariantMap &politiqueHermes() const { return m_politiqueHermes; }
    [[nodiscard]] const QVariantMap &politiquePoste() const { return m_politiquePoste; }
    [[nodiscard]] bool releveFactice() const;
    [[nodiscard]] bool brouillonModifie() const;
    [[nodiscard]] bool brouillonVide() const;
    [[nodiscard]] const QStringList &refusTable() const { return m_refusTexte; }
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] QString erreur() const;

    Q_INVOKABLE void actualiser();
    /*! Remplace le brouillon de la classe par la suggestion du greffon. */
    Q_INVOKABLE void appliquerSuggestion(const QString &classe);
    /*! Retire l'entrée de rang `rang` (0 = première) du brouillon de la classe. */
    Q_INVOKABLE void retirerEntree(const QString &classe, int rang);
    /*! Rebâtit tout le brouillon depuis la table enregistrée. */
    Q_INVOKABLE void revenir();
    Q_INVOKABLE void valider();
    Q_INVOKABLE void accepterReleve(const QString &voie);
    Q_INVOKABLE void desactiverSurcharge(const QString &identifiant);
    /*! Ouvre la vue Routage de la page Poste du tableau de bord dans le navigateur. */
    Q_INVOKABLE bool modifierDansLeNavigateur();

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construireListe(const QString &voie, const QJsonObject &catalogue);
    /*! « Poste (Codex) · gpt-x · effort medium · palier Standard » ; valeurs absentes omises. */
    [[nodiscard]] static QString texteEntree(const QJsonObject &entree);
    /*! Entrée réduite aux quatre champs du contrat : voie, modele, effort, palier (nul si absent). */
    [[nodiscard]] static QJsonObject entreePropre(const QJsonObject &entree);
    [[nodiscard]] static QStringList ordreDesClasses(const QJsonObject &classes);
    [[nodiscard]] static QVariantMap construirePolitiqueHermes(const QJsonObject &vue);
    [[nodiscard]] static QVariantMap construirePolitiquePoste(const QJsonObject &vue);
    [[nodiscard]] static QJsonArray construireSurcharges(const QJsonObject &vue);

signals:
    void routageChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lire(const QJsonObject &vue);
    void rebatirBrouillon();
    void publierClasses();
    void apresGeste();
    [[nodiscard]] QJsonArray entreesEnregistrees(const QString &classe) const;

    ApiClient *m_client = nullptr;
    ClientGreffonPoste *m_greffon = nullptr;
    Sondage *m_sondage = nullptr;
    JsonListModel *m_listes = nullptr;
    JsonListModel *m_classes = nullptr;
    JsonListModel *m_surcharges = nullptr;
    Ouvreur m_ouvreur;
    bool m_lue = false;
    bool m_rebatir = true; //!< Prochaine lecture : brouillon rebâti (nouveau relevé, 409, validation).
    QJsonObject m_vue;
    QJsonObject m_relevesDuBrouillon; //!< Relevés lus quand le brouillon a été bâti, envoyés tels quels.
    QHash<QString, QJsonArray> m_brouillon;
    QHash<QString, QHash<int, QString>> m_refus; //!< classe → rang → message du refus (422).
    QStringList m_refusTexte;
    QVariantMap m_politiqueHermes;
    QVariantMap m_politiquePoste;
};

} // namespace acp
