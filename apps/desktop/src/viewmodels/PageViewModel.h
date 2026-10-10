// Base des pages de pilotage : quand une page a le droit de lire Hermes.
//
// Une page lit seulement si elle est AFFICHÉE (la page QML le dit par `pageVisible`), si la
// fenêtre n'est pas réduite et si une session est établie (EventStreamService::pagesActives).
// La classe dérivée reçoit chaque changement par surActivite(), et le retour du lien par
// surLienRetabli() : elle relit alors tout de suite (cahier P8 § 6.1).
//
// Les gestes d'écriture publient leur résultat tel que le serveur l'a rendu : `messageGeste`
// (réussite, en français) ou `erreurGeste` (message du greffon ou de Hermes, tel quel). Une
// réponse acceptée mais sans effet (carte non relancée, non reprise) est une ALERTE
// (`alerteGeste`) : la page ne la montre jamais comme une réussite.
//
// Oubli (Application l'appelle à la session perdue, au changement de serveur et au blocage du
// greffon) : la page vide ses modèles, revient à « Jamais lu », abandonne ses lectures en vol et
// efface ses brouillons ; aucune donnée d'une session ou d'un serveur ne reste affichée ensuite.
//
// Cadence (`cadence`) : la phrase que la page affiche sur sa relecture, d'après son sondage
// principal (suivreCadence) et l'état RÉEL du flux d'invalidation — jamais une cadence écrite en
// dur dans la page (relecture de P8b, constat desktop-4).

#pragma once

#include <QObject>
#include <QPointer>
#include <QString>

namespace acp {

class ApiError;
class EventStreamService;
class Sondage;

class PageViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool pageVisible READ pageVisible WRITE setPageVisible NOTIFY pageVisibleChange)
    Q_PROPERTY(bool actif READ actif NOTIFY actifChange)
    Q_PROPERTY(bool gesteEnCours READ gesteEnCours NOTIFY gesteChange)
    Q_PROPERTY(QString messageGeste READ messageGeste NOTIFY gesteChange)
    Q_PROPERTY(bool alerteGeste READ alerteGeste NOTIFY gesteChange)
    Q_PROPERTY(QString erreurGeste READ erreurGeste NOTIFY gesteChange)
    Q_PROPERTY(QString cadence READ cadence NOTIFY cadenceChange)

public:
    explicit PageViewModel(EventStreamService *flux, QObject *parent = nullptr);

    [[nodiscard]] bool pageVisible() const { return m_pageVisible; }
    void setPageVisible(bool visible);
    [[nodiscard]] bool actif() const { return m_actif; }

    [[nodiscard]] bool gesteEnCours() const { return m_gesteEnCours; }
    [[nodiscard]] const QString &messageGeste() const { return m_messageGeste; }
    [[nodiscard]] bool alerteGeste() const { return m_alerteGeste; }
    [[nodiscard]] const QString &erreurGeste() const { return m_erreurGeste; }
    /*! Efface le dernier résultat de geste (la page l'a lu, ou change de vue). */
    Q_INVOKABLE void effacerGeste();

    /*! Message à montrer pour une erreur : celui du greffon tel quel, sinon famille et détail. */
    [[nodiscard]] static QString messageDuRefus(const ApiError &erreur);

    /*! Oublie tout ce que la page a lu ou préparé (voir l'en-tête). */
    void oublier();

    /*! Cadence réelle de relecture de la page, en une phrase ; vide sans sondage suivi. */
    [[nodiscard]] virtual QString cadence() const;

signals:
    void pageVisibleChange();
    void actifChange();
    void gesteChange();
    void cadenceChange();

protected:
    [[nodiscard]] EventStreamService *flux() const { return m_flux; }
    /*! La cadence dite est celle de ce sondage, lecture principale de la page (une fois). */
    void suivreCadence(Sondage *sondage);
    virtual void surActivite(bool actif) = 0;
    virtual void surLienRetabli() {}
    virtual void surOubli() = 0;

    void debuterGeste();
    /*! Geste accepté par le serveur ; `alerte` : accepté sans effet, le propriétaire a une suite à donner. */
    void terminerGeste(const QString &message, bool alerte = false);
    void echouerGeste(const ApiError &erreur);
    void echouerGeste(const QString &message);

private:
    void majActivite();

    EventStreamService *m_flux = nullptr;
    QPointer<Sondage> m_sondageCadence;
    bool m_pageVisible = false;
    bool m_actif = false;
    bool m_gesteEnCours = false;
    QString m_messageGeste;
    bool m_alerteGeste = false;
    QString m_erreurGeste;
};

} // namespace acp
