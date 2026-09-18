// Portée d'un abonnement au journal.
//
// Deux portées existent, et l'audit insiste : leurs curseurs sont « deux entiers
// indiscernables » dans le champ SSE `id:`. La portée n'est donc jamais une chaîne libre
// ni un booléen : c'est un type qui EMBARQUE son curseur, de sorte qu'il soit impossible
// de passer un curseur de tentative à une route de projet.

#pragma once

#include "api/Cursors.h"

#include <QString>

#include <variant>

namespace acp {

/*! Abonnement à une tentative : curseur EventModel.sequence. */
struct RunScope
{
    QString runId;
    RunCursor cursor;
};

/*! Abonnement à un projet : curseur EventModel.journal_seq. */
struct ProjectScope
{
    QString projectId;
    ProjectCursor cursor;
};

using StreamScope = std::variant<RunScope, ProjectScope>;

/*! Clé d'unicité d'un abonnement. Le préfixe empêche toute collision entre un
    identifiant de tentative et un identifiant de projet. */
[[nodiscard]] inline QString scopeKey(const StreamScope &scope)
{
    if (const auto *run = std::get_if<RunScope>(&scope)) {
        return QStringLiteral("run:") + run->runId;
    }
    const auto &project = std::get<ProjectScope>(scope);
    return QStringLiteral("project:") + project.projectId;
}

/*! Chemin du flux SSE de la portée. */
[[nodiscard]] inline QString scopeStreamPath(const StreamScope &scope)
{
    if (const auto *run = std::get_if<RunScope>(&scope)) {
        return QStringLiteral("/streams/runs/") + run->runId;
    }
    return QStringLiteral("/streams/projects/") + std::get<ProjectScope>(scope).projectId;
}

/*! Chemin du journal durable paginé de la portée. C'est le repli obligatoire : la
    reprise se fait par curseur de lecture, jamais par réémission. */
[[nodiscard]] inline QString scopeJournalPath(const StreamScope &scope)
{
    if (const auto *run = std::get_if<RunScope>(&scope)) {
        return QStringLiteral("/runs/") + run->runId + QStringLiteral("/events");
    }
    return QStringLiteral("/projects/") + std::get<ProjectScope>(scope).projectId
        + QStringLiteral("/events");
}

/*! Valeur numérique du curseur de la portée. Le seul endroit du code où un curseur
    redevient un entier nu ; il est immédiatement sérialisé dans une requête. */
[[nodiscard]] inline qint64 scopeCursorValue(const StreamScope &scope)
{
    if (const auto *run = std::get_if<RunScope>(&scope)) {
        return run->cursor.value();
    }
    return std::get<ProjectScope>(scope).cursor.value();
}

/*! Avance le curseur de la portée. Le type construit dépend de la portée : il est
    impossible d'écrire un curseur de projet dans une portée de tentative. */
inline void advanceScopeCursor(StreamScope &scope, qint64 rawCursor)
{
    if (auto *run = std::get_if<RunScope>(&scope)) {
        if (rawCursor > run->cursor.value()) {
            run->cursor = RunCursor{rawCursor};
        }
        return;
    }
    auto &project = std::get<ProjectScope>(scope);
    if (rawCursor > project.cursor.value()) {
        project.cursor = ProjectCursor{rawCursor};
    }
}

/*! Libellé français de la portée, pour les messages d'erreur et les diagnostics. */
[[nodiscard]] inline QString scopeLabel(const StreamScope &scope)
{
    if (const auto *run = std::get_if<RunScope>(&scope)) {
        return QStringLiteral("tentative %1").arg(run->runId);
    }
    return QStringLiteral("projet %1").arg(std::get<ProjectScope>(scope).projectId);
}

} // namespace acp
