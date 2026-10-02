// Page Poste de la station (cahier P8 § 7.5), sur `GET /v1/poste` du greffon, relu toutes les
// 15 s tant que la page est affichée. Même contenu que la vue « Poste » de la page web
// (apps/interface/src/poste/EtatPoste.tsx) :
//
//  - bandeau d'état : Non configuré, À confirmer (avec l'empreinte annoncée), En ligne (vu à),
//    Hors ligne (depuis), Révoqué (le) ; message du greffon, politique locale invalide, pause
//    générale, cartes du poste en attente ;
//  - poste enrôlé, dernier inventaire (compte, versions des CLI, bac à sable Codex, connexions,
//    dépôts), alertes, ordres en attente ;
//  - exécutant Railway (étape P6) : lu de `machine.executant` de `/v1/meta` SEULEMENT s'il y
//    figure, sinon « Non disponible sur ce serveur ».
//
// Gestes, chacun sur une route réelle du greffon, résultat rendu tel que le serveur l'a dit :
//  - « Générer un code d'enrôlement » → `POST /v1/poste/enrolement {}`. Le code est rendu UNE
//    fois : il vit dans cet objet seulement (jamais écrit, jamais journalisé), avec la commande
//    et un décompte, et il est effacé quand la page est quittée ou la session perdue ;
//  - « Confirmer le poste » → `POST /v1/poste/confirmation {machine_id, empreinte}` ;
//  - « Révoquer » → `POST /v1/poste/revocation {machine_id, motif}` (confirmation de la page) ;
//  - « Relever maintenant » → `POST /v1/poste/releve {}` (message du greffon tel quel).

#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QVariantMap>

#include <functional>

class QTimer;

namespace acp {

class ClientGreffonPoste;
class CompatibiliteHermes;
class Sondage;

class PosteViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(bool lue READ lue NOTIFY posteChange)
    Q_PROPERTY(QVariantMap etat READ etat NOTIFY posteChange)
    Q_PROPERTY(QVariantMap machine READ machine NOTIFY posteChange)
    Q_PROPERTY(QVariantMap inventaire READ inventaire NOTIFY posteChange)
    Q_PROPERTY(QStringList alertes READ alertes NOTIFY posteChange)
    Q_PROPERTY(JsonListModel *ordres READ ordres CONSTANT)
    Q_PROPERTY(bool peutEnroler READ peutEnroler NOTIFY posteChange)
    Q_PROPERTY(bool peutConfirmer READ peutConfirmer NOTIFY posteChange)
    Q_PROPERTY(bool peutRelever READ peutRelever NOTIFY posteChange)
    Q_PROPERTY(bool peutRevoquer READ peutRevoquer NOTIFY posteChange)
    Q_PROPERTY(QVariantMap executant READ executant NOTIFY executantChange)
    // Code d'enrôlement : la seule valeur sensible exposée, assumée (cahier P8 § 8).
    Q_PROPERTY(QString code READ code NOTIFY codeChange)
    Q_PROPERTY(QString commande READ commande NOTIFY codeChange)
    Q_PROPERTY(int secondesRestantes READ secondesRestantes NOTIFY decompteChange)
    Q_PROPERTY(bool codeExpire READ codeExpire NOTIFY decompteChange)
    Q_PROPERTY(QString messageCopie READ messageCopie NOTIFY codeChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)

public:
    PosteViewModel(ClientGreffonPoste *greffon, CompatibiliteHermes *compatibilite, EventStreamService *flux,
                   QObject *parent = nullptr);
    ~PosteViewModel() override;

    using Horloge = std::function<qint64()>;
    //! Secondes depuis l'époque (décompte du code) ; injectable par les tests.
    void setHorloge(Horloge horloge) { m_horloge = std::move(horloge); }
    using Presse = std::function<bool(const QString &)>;
    //! Écriture dans le presse-papiers ; injectable par les tests.
    void setPressePapiers(Presse presse) { m_presse = std::move(presse); }

    [[nodiscard]] bool lue() const { return m_lue; }
    [[nodiscard]] const QVariantMap &etat() const { return m_etat; }
    [[nodiscard]] const QVariantMap &machine() const { return m_machine; }
    [[nodiscard]] const QVariantMap &inventaire() const { return m_inventaire; }
    [[nodiscard]] const QStringList &alertes() const { return m_alertes; }
    [[nodiscard]] JsonListModel *ordres() const { return m_ordres; }
    [[nodiscard]] bool peutEnroler() const;
    [[nodiscard]] bool peutConfirmer() const;
    [[nodiscard]] bool peutRelever() const;
    [[nodiscard]] bool peutRevoquer() const;
    [[nodiscard]] QVariantMap executant() const;
    [[nodiscard]] const QString &code() const { return m_code; }
    [[nodiscard]] const QString &commande() const { return m_commande; }
    [[nodiscard]] int secondesRestantes() const;
    [[nodiscard]] bool codeExpire() const;
    [[nodiscard]] const QString &messageCopie() const { return m_messageCopie; }
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] QString erreur() const;

    Q_INVOKABLE void actualiser();
    Q_INVOKABLE void enroler();
    Q_INVOKABLE void confirmer(const QString &empreinte);
    Q_INVOKABLE void revoquer(const QString &motif);
    Q_INVOKABLE void relever();
    /*! Copie le code d'enrôlement dans le presse-papiers (jamais ailleurs). */
    Q_INVOKABLE void copierCode();
    /*! Efface le code d'enrôlement de la mémoire (page quittée, session perdue). */
    Q_INVOKABLE void oublierCode();

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QVariantMap construireEtat(const QJsonObject &vue);
    [[nodiscard]] static QVariantMap construireMachine(const QJsonObject &vue);
    [[nodiscard]] static QVariantMap construireInventaire(const QJsonObject &vue);
    [[nodiscard]] static QJsonArray construireOrdres(const QJsonObject &vue);
    [[nodiscard]] static QVariantMap construireExecutant(bool present, const QJsonObject &executant);

signals:
    void posteChange();
    void executantChange();
    void codeChange();
    void decompteChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lire(const QJsonObject &vue);
    void apresGeste();
    [[nodiscard]] QString etatBrut() const;
    [[nodiscard]] QString etatMachine() const;
    [[nodiscard]] QString machineId() const;

    ClientGreffonPoste *m_greffon = nullptr;
    CompatibiliteHermes *m_compatibilite = nullptr;
    Sondage *m_sondage = nullptr;
    JsonListModel *m_ordres = nullptr;
    QTimer *m_decompte = nullptr;
    Horloge m_horloge;
    Presse m_presse;
    bool m_lue = false;
    QJsonObject m_vue;
    QVariantMap m_etat;
    QVariantMap m_machine;
    QVariantMap m_inventaire;
    QStringList m_alertes;
    QString m_code;
    QString m_commande;
    qint64 m_expireLe = 0;
    bool m_codeExpire = false;
    QString m_messageCopie;
};

} // namespace acp
