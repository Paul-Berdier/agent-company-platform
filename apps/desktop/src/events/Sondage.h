// Lecture périodique d'une route REST, pour une page visible (cahier P8 § 6.1).
//
// Règles, les mêmes que la page web (D35) :
//  - actif seulement quand la page est affichée ET la fenêtre non réduite ET la session
//    établie : l'appelant le dit par setActif() ; inactif, aucun appel ne part ;
//  - lecture à l'activation, puis toutes les 15 s (intervalle réglable) ; la minuterie repart
//    APRÈS la fin de chaque lecture : deux lectures ne se chevauchent jamais ;
//  - lecture immédiate après un geste du propriétaire ou au retour du lien (lireMaintenant) ;
//    pendant une lecture en vol, la demande est retenue et servie une fois à sa fin ;
//  - échec : la dernière valeur lue reste à l'appelant (le signal `echec` ne vide rien),
//    l'heure de la dernière lecture réussie et l'erreur sont publiées côte à côte.

#pragma once

#include "api/ApiError.h"
#include "api/ApiRequest.h"

#include <QDateTime>
#include <QObject>
#include <QPointer>
#include <QString>

#include <chrono>
#include <functional>

class QTimer;

namespace acp {

class ApiCall;

class Sondage : public QObject
{
    Q_OBJECT

public:
    //! Émet la lecture ; rend l'appel en cours (jamais nul).
    using Lecteur = std::function<ApiCall *()>;

    static constexpr std::chrono::milliseconds kIntervallePage{15000};

    explicit Sondage(Lecteur lecteur, std::chrono::milliseconds intervalle = kIntervallePage,
                     QObject *parent = nullptr);
    ~Sondage() override;

    void setIntervalle(std::chrono::milliseconds intervalle);
    [[nodiscard]] std::chrono::milliseconds intervalle() const { return m_intervalle; }

    /*! Active (lecture immédiate puis périodique) ou suspend le sondage. */
    void setActif(bool actif);
    [[nodiscard]] bool actif() const { return m_actif; }

    /*! Lecture immédiate, actif ou non (geste du propriétaire, retour du lien). */
    void lireMaintenant();

    [[nodiscard]] bool enCours() const { return !m_appel.isNull(); }
    [[nodiscard]] const QDateTime &luA() const { return m_luA; }
    /*! « Lu à HH:MM:SS », ou « Jamais lu ». */
    [[nodiscard]] QString libelleLuA() const;
    [[nodiscard]] const QString &derniereErreur() const { return m_derniereErreur; }
    [[nodiscard]] int lectures() const { return m_lectures; }

signals:
    void lu(const acp::ApiResponse &reponse);
    void echec(const acp::ApiError &erreur);
    void etatChange();

private:
    void lancer();
    void programmer();

    Lecteur m_lecteur;
    std::chrono::milliseconds m_intervalle;
    QTimer *m_minuterie = nullptr;
    QPointer<ApiCall> m_appel;
    bool m_actif = false;
    bool m_relire = false;
    QDateTime m_luA;
    QString m_derniereErreur;
    int m_lectures = 0;
};

} // namespace acp
