// Analyseur SSE incrémental.
//
// Il implémente l'algorithme « interpreting an event stream » de la spécification HTML
// (https://html.spec.whatwg.org/multipage/server-sent-events.html, consultée le
// 18 septembre 2026), et rien de plus :
//
//  - séparateurs de ligne CRLF, LF seul, CR seul ;
//  - une marque d'ordre des octets UTF-8 en tête de flux est retirée ;
//  - une ligne commençant par « : » est un commentaire et est ignorée — c'est la forme
//    exacte du keep-alive du serveur, « : ping », émis toutes les 15 s ;
//  - découpe au PREMIER deux-points ; une seule espace suivant le deux-points est
//    retirée de la valeur ;
//  - une ligne sans deux-points est un nom de champ à valeur vide ;
//  - « data » s'accumule, chaque occurrence suivie d'un saut de ligne ;
//  - « id » alimente le tampon d'identifiant SAUF si la valeur contient U+0000 ;
//  - « retry » n'est accepté que s'il ne contient que des chiffres ASCII — le serveur de
//    ce produit n'en émet jamais (audit, section 4.2), le champ est donc analysé mais
//    n'a, à ce jour, aucune source ;
//  - une ligne vide déclenche le dispatch : le tampon d'identifiant devient l'identifiant
//    courant et PERSISTE ; si le tampon de données est vide, rien n'est émis et les
//    tampons sont remis à zéro ; sinon le dernier saut de ligne est retiré.
//
// L'analyseur ne connaît NI les curseurs, NI les portées, NI la reconnexion : il rend des
// trames. La discipline des deux espaces de curseurs vit dans EventStreamService, sur des
// types forts (voir api/Cursors.h).

#pragma once

#include "events/SseEvent.h"

#include <QByteArray>
#include <QList>
#include <QString>

#include <optional>

namespace acp {

class SseParser
{
public:
    SseParser() = default;

    /*!
        Injecte un fragment d'octets et renvoie les événements complets qu'il termine.

        Un fragment peut couper n'importe où : au milieu d'une ligne, entre le CR et le
        LF d'un CRLF, au milieu d'un caractère UTF-8 multi-octets. Les trois cas sont
        tenus : le décodage UTF-8 est incrémental et les octets incomplets restent dans
        le tampon jusqu'au fragment suivant.
    */
    [[nodiscard]] QList<SseEvent> consume(const QByteArray &chunk);

    /*!
        Termine le flux. Un dernier événement n'est émis QUE si le flux s'achève sur une
        ligne vide en bonne et due forme ; un bloc tronqué est abandonné, jamais complété
        par hypothèse.
    */
    [[nodiscard]] QList<SseEvent> finish();

    /*! Identifiant du dernier événement dispatché, à renvoyer en `Last-Event-ID`. */
    [[nodiscard]] const QString &lastEventId() const { return m_lastEventId; }

    /*! Pose l'identifiant de reprise avant l'ouverture d'un flux. */
    void setLastEventId(const QString &id) { m_lastEventId = id; }

    /*! Délai de reconnexion demandé par le serveur, s'il en a demandé un. */
    [[nodiscard]] const std::optional<int> &retryMilliseconds() const { return m_retry; }

    /*! Remet à zéro les tampons de trame, en CONSERVANT l'identifiant de reprise : une
        reconnexion repart du dernier événement reçu, pas du début du journal. */
    void resetFrameBuffers();

    /*! Nombre d'octets encore en attente, pour l'écran de diagnostics. */
    [[nodiscard]] int pendingByteCount() const { return static_cast<int>(m_pending.size()); }

private:
    void handleLine(const QString &line, QList<SseEvent> &out);
    void handleField(const QString &field, const QString &value);
    void dispatch(QList<SseEvent> &out);

    QByteArray m_pending;      //!< Octets non encore consommés (ligne ou UTF-8 incomplets).
    bool m_bomChecked = false; //!< La marque d'ordre des octets n'est cherchée qu'en tête de flux.

    QString m_eventType;        //!< Tampon « event type ».
    QString m_dataBuffer;       //!< Tampon « data ».
    QString m_idBuffer;         //!< Tampon « last event ID » ; il n'est jamais vidé au dispatch.
    QString m_lastEventId;      //!< Identifiant du dernier événement dispatché.
    std::optional<int> m_retry; //!< Dernier `retry` accepté ; ce serveur n'en émet aucun.
};

} // namespace acp
