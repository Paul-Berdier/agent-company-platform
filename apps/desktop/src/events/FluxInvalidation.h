// Flux d'invalidation du greffon acp-poste : `GET /v1/flux` (étape P7, cahier P7 § 5 ; décision
// P7-4), consommé par la station comme par la page web (apps/interface/src/flux.ts).
//
// Le flux SIGNALE qu'un sujet a changé (« projets », « questions », « poste », « quotas »,
// « notifications », « pause », « discussions ») ; la page qui suit ce sujet relit alors SA
// route REST (Sondage::suivre). Aucune donnée métier n'y passe : un signal manqué retombe sur
// l'état exact à la relecture suivante.
//
// Contrat (noyau/flux.py, route flux_d_invalidation de plugin_api.py ; trames exemples
// partagées : hermes/tests/outils/fixtures_flux/trames.json) :
//  - ouverture : `retry: 3000`, puis trame `etat` {revision, sujets, discussions_suivies,
//    illisibles?} ; `sujets` est vide quand le client revient avec `Last-Event-ID` égal à la
//    révision courante (rien de manqué), tous les sujets sinon ;
//  - trames `changement` {sujets, illisibles?} ; battement en commentaire (« : battement ») ;
//  - trame `fin` {raison: "duree_max"} au bout de la durée maximale (10 min) ;
//  - 429 `trop_de_flux` (Retry-After: 30) au-delà de `flux_max` flux ouverts.
//
// Règles, les mêmes que la page web :
//  - ouvert seulement si `/v1/meta` l'ANNONCE (clé `flux`, chemin et version attendus) et si
//    une page peut lire (session établie, fenêtre non réduite) ; fermé sinon ;
//  - mode « temps réel » dès la trame `etat` ; une page qui suit le flux relit sur signal
//    (regroupé sur 300 ms) et se contente d'une relecture de SÛRETÉ toutes les 2 min (1 min
//    pour une page qui suit les discussions quand le greffon ne publie pas leur nombre) ;
//  - chien de garde : sans AUCUN octet (trame ou battement) pendant 40 s, ouverture comprise,
//    la connexion est annulée et comptée comme un échec ;
//  - reprise : aussitôt après `fin` (avec `Last-Event-ID`) ; sinon 1 s, 2 s, 5 s, 10 s puis
//    30 s ; trois échecs en 2 min : mode « sondage » (relecture toutes les 15 s), dit, et
//    nouvel essai toutes les 5 min ; 429 : jamais avant `Retry-After` ;
//  - 401 : jamais réessayé aussitôt ; mode « sondage » et nouvel essai dans 5 min (décision
//    P8b-1 : la station n'a pas de page à recharger ; les lectures REST de la session font
//    tourner le jeton entre-temps, ou la perdent et ferment tout).
// Tant que le flux n'est pas en temps réel, les pages gardent leur sondage habituel : aucune
// fraîcheur n'est jamais supposée.

#pragma once

#include "events/SseParser.h"

#include <QDateTime>
#include <QJsonValue>
#include <QList>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QStringList>

#include <chrono>
#include <optional>

class QNetworkReply;
class QTimer;

namespace acp {

class ClientGreffonPoste;

class FluxInvalidation : public QObject
{
    Q_OBJECT

public:
    enum class Mode {
        Ferme,        //!< Aucune page ne peut lire (pas de session, fenêtre réduite).
        Indisponible, //!< Non annoncé par /v1/meta, annonce illisible ou greffon bloqué.
        Connexion,    //!< Ouverture en cours, aucune trame `etat` encore.
        TempsReel,    //!< Trame `etat` reçue.
        Sondage,      //!< Repli : trois échecs en 2 min, ou 401 ; nouvel essai planifié.
    };
    Q_ENUM(Mode)

    struct Reglages
    {
        std::chrono::milliseconds chienDeGarde{40000};
        std::chrono::milliseconds fenetreEchecs{120000};
        std::chrono::milliseconds nouvelEssai{300000};
        QList<std::chrono::milliseconds> reprises{std::chrono::milliseconds(1000), std::chrono::milliseconds(2000),
                                                  std::chrono::milliseconds(5000), std::chrono::milliseconds(10000),
                                                  std::chrono::milliseconds(30000)};
        std::chrono::milliseconds relectureSurete{120000};
        std::chrono::milliseconds relectureDiscussions{60000};
        std::chrono::milliseconds regroupement{300};
    };

    static constexpr char kChemin[] = "/api/plugins/acp-poste/v1/flux";
    static constexpr int kVersion = 1;
    static constexpr int kEchecsAvantRepli = 3;
    //! Trames gardées pour le diagnostic (noms de sujets seulement, jamais de donnée).
    static constexpr int kTramesGardees = 50;

    /*! Les sept sujets du greffon (noyau/flux.py, SUJETS), dans son ordre. */
    [[nodiscard]] static const QStringList &sujets();

    /*!
        Raison française pour laquelle la station n'ouvre pas le flux d'après l'annonce de
        /v1/meta (`etat` : CompatibiliteHermes::etatFlux ; `annonce` : l'objet `flux` servi), ou
        une chaîne vide si l'annonce est utilisable (chemin et version attendus).
    */
    [[nodiscard]] static QString raisonAnnonce(const QString &etat, const QJsonValue &annonce);

    explicit FluxInvalidation(ClientGreffonPoste *greffon, QObject *parent = nullptr);
    ~FluxInvalidation() override;

    void setReglages(const Reglages &reglages) { m_reglages = reglages; }
    [[nodiscard]] const Reglages &reglages() const { return m_reglages; }

    /*! Annonce de /v1/meta, relue à chaque verdict de compatibilité. */
    void setAnnonce(const QString &etat, const QJsonValue &annonce);
    /*! Une page peut lire (session établie ET fenêtre non réduite). */
    void setActif(bool actif);
    [[nodiscard]] bool actif() const { return m_actif; }
    /*! Retour du lien : une reprise en attente part aussitôt (le repli de 5 min reste). */
    void relancer();
    /*!
        Serveur changé : identifiant de reprise, échecs, repli et annonce oubliés ; rien ne
        s'ouvre avant le verdict de /v1/meta du nouveau serveur.
    */
    void oublier();

    [[nodiscard]] Mode mode() const { return m_mode; }
    [[nodiscard]] bool tempsReel() const { return m_mode == Mode::TempsReel; }
    /*! `discussions_suivies` de la dernière trame `etat` ; inconnu tant qu'aucune. */
    [[nodiscard]] std::optional<bool> discussionsSuivies() const { return m_discussionsSuivies; }
    [[nodiscard]] const QString &revision() const { return m_dernierId; }
    [[nodiscard]] const QString &raison() const { return m_raison; }
    [[nodiscard]] int trames() const { return m_trames; }
    [[nodiscard]] int connexions() const { return m_connexions; }
    [[nodiscard]] int tramesIllisibles() const { return m_tramesIllisibles; }
    [[nodiscard]] bool connecte() const { return !m_reponse.isNull(); }
    [[nodiscard]] const QDateTime &prochainEssai() const { return m_prochainEssai; }
    /*! Dernières trames reçues (« HH:MM:SS etat : projets, questions »), pour le diagnostic. */
    [[nodiscard]] const QStringList &journal() const { return m_journal; }

    /*! Phrase française de l'état (diagnostics, info-bulle de la barre d'état). */
    [[nodiscard]] QString libelleEtat() const;
    /*! Libellé court pour la barre d'état. */
    [[nodiscard]] QString libelleCourt() const;

    /*!
        Intervalle de relecture d'une page dont le sondage habituel est `repli` et qui suit
        `sujets` : `repli` hors temps réel ; en temps réel, la relecture de sûreté (2 min, ou
        1 min pour les discussions non publiées par le greffon), jamais plus fréquente que `repli`.
    */
    [[nodiscard]] std::chrono::milliseconds intervalleRelecture(std::chrono::milliseconds repli,
                                                                const QStringList &sujets) const;

signals:
    /*! Sujets changés (trame `etat` ou `changement`) : les pages qui les suivent relisent. */
    void invalidation(const QStringList &sujets);
    void etatChange();

private:
    void ouvrir();
    void fermer();
    void lireOctets(QNetworkReply *reponse);
    void terminer(QNetworkReply *reponse);
    void traiter(const SseEvent &trame);
    void echec(const QString &raison, std::chrono::milliseconds delaiMinimal = std::chrono::milliseconds(0));
    void planifier(std::chrono::milliseconds delai);
    void changerMode(Mode mode);
    void noter(const QString &evenement, const QStringList &sujets);

    ClientGreffonPoste *m_greffon = nullptr;
    Reglages m_reglages;
    QPointer<QNetworkReply> m_reponse;
    SseParser m_analyseur;
    QTimer *m_chien = nullptr;
    QTimer *m_reprise = nullptr;
    Mode m_mode = Mode::Indisponible;
    bool m_actif = false;
    bool m_annonceUtilisable = false;
    QString m_etatAnnonce = QStringLiteral("inconnu");
    bool m_fin = false;
    bool m_chienEchu = false;
    bool m_statutLu = false;
    bool m_statutValide = false;
    std::optional<bool> m_discussionsSuivies;
    QString m_dernierId;
    QString m_raison;
    QList<QDateTime> m_echecs;
    QDateTime m_repliJusqua;
    QDateTime m_prochainEssai;
    int m_trames = 0;
    int m_connexions = 0;
    int m_tramesIllisibles = 0;
    QStringList m_journal;
};

} // namespace acp
