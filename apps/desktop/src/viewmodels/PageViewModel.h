// Base des pages de pilotage : quand une page a le droit de lire Hermes.
//
// Une page lit seulement si elle est AFFICHÉE (la page QML le dit par `pageVisible`), si la
// fenêtre n'est pas réduite et si une session est établie (EventStreamService::pagesActives).
// La classe dérivée reçoit chaque changement par surActivite(), et le retour du lien par
// surLienRetabli() : elle relit alors tout de suite (cahier P8 § 6.1).
//
// Les gestes d'écriture publient leur résultat tel que le serveur l'a rendu : `messageGeste`
// (réussite, en français) ou `erreurGeste` (message du greffon ou de Hermes, tel quel).

#pragma once

#include <QObject>
#include <QString>

namespace acp {

class ApiError;
class EventStreamService;

class PageViewModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool pageVisible READ pageVisible WRITE setPageVisible NOTIFY pageVisibleChange)
    Q_PROPERTY(bool actif READ actif NOTIFY actifChange)
    Q_PROPERTY(bool gesteEnCours READ gesteEnCours NOTIFY gesteChange)
    Q_PROPERTY(QString messageGeste READ messageGeste NOTIFY gesteChange)
    Q_PROPERTY(QString erreurGeste READ erreurGeste NOTIFY gesteChange)

public:
    explicit PageViewModel(EventStreamService *flux, QObject *parent = nullptr);

    [[nodiscard]] bool pageVisible() const { return m_pageVisible; }
    void setPageVisible(bool visible);
    [[nodiscard]] bool actif() const { return m_actif; }

    [[nodiscard]] bool gesteEnCours() const { return m_gesteEnCours; }
    [[nodiscard]] const QString &messageGeste() const { return m_messageGeste; }
    [[nodiscard]] const QString &erreurGeste() const { return m_erreurGeste; }
    /*! Efface le dernier résultat de geste (la page l'a lu, ou change de vue). */
    Q_INVOKABLE void effacerGeste();

    /*! Message à montrer pour une erreur : celui du greffon tel quel, sinon famille et détail. */
    [[nodiscard]] static QString messageDuRefus(const ApiError &erreur);

signals:
    void pageVisibleChange();
    void actifChange();
    void gesteChange();

protected:
    [[nodiscard]] EventStreamService *flux() const { return m_flux; }
    virtual void surActivite(bool actif) = 0;
    virtual void surLienRetabli() {}

    void debuterGeste();
    void terminerGeste(const QString &message);
    void echouerGeste(const ApiError &erreur);
    void echouerGeste(const QString &message);

private:
    void majActivite();

    EventStreamService *m_flux = nullptr;
    bool m_pageVisible = false;
    bool m_actif = false;
    bool m_gesteEnCours = false;
    QString m_messageGeste;
    QString m_erreurGeste;
};

} // namespace acp
