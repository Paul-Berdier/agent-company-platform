// Une trame SSE décodée.

#pragma once

#include <QByteArray>
#include <QString>

#include <optional>

namespace acp {

//! Noms de trame émis par l'API. Relevés dans apps/api/src/acp_api/streams.py.
inline constexpr char kSseEventName[] = "acp.event";
inline constexpr char kSseRotateEventName[] = "acp.stream.rotate";
inline constexpr char kSseClosedEventName[] = "acp.stream.closed";

/*!
    Événement SSE tel que la spécification le définit après « dispatch the event ».

    `type` vaut « message » quand le serveur n'a nommé aucun événement : c'est la valeur
    par défaut de la spécification, et l'audit rappelle que le CLI l'implémente ainsi.
    `lastEventId` porte la valeur courante du tampon d'identifiant, qui PERSISTE d'un
    événement à l'autre : une trame sans champ `id:` hérite de l'identifiant précédent.
*/
struct SseEvent
{
    QString type = QStringLiteral("message");
    QString data;
    QString lastEventId;

    [[nodiscard]] bool isJournalEvent() const
    {
        return type == QLatin1String(kSseEventName) || type == QLatin1String("message");
    }
    [[nodiscard]] bool isRotate() const { return type == QLatin1String(kSseRotateEventName); }
    [[nodiscard]] bool isClosed() const { return type == QLatin1String(kSseClosedEventName); }
};

} // namespace acp
