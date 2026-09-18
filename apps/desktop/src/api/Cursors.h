// Curseurs de journal : deux espaces distincts, jamais convertibles l'un vers l'autre.
//
// L'audit (docs/desktop-railway-audit.md, section 4.1) établit que le serveur transporte
// DEUX curseurs différents dans le même champ SSE `id:` :
//
//   - portée tentative — GET /streams/runs/{id} et GET /runs/{id}/events : le curseur est
//     EventModel.sequence, monotone PAR RUN ;
//   - portée projet   — GET /streams/projects/{id} et GET /projects/{id}/events : le
//     curseur est EventModel.journal_seq, monotone à l'échelle du journal.
//
// Ce sont deux entiers indiscernables au niveau du protocole. Un client qui réutilise
// l'un pour l'autre saute ou rejoue des événements SANS AUCUNE ERREUR VISIBLE. C'est le
// défaut le plus coûteux du protocole, et le seul garde-fou possible est dans le langage :
// deux types forts, sans conversion implicite, sans constructeur commun, sans opérateur
// de comparaison croisé. Un `qint64` nu est interdit dans tout le code de flux.

#pragma once

#include <QtGlobal>

#include <compare>
#include <type_traits>

namespace acp {

/*!
    Curseur de la portée « tentative » (EventModel.sequence).

    Le type est explicite à la construction : `RunCursor{42}` est écrit, `42` ne se
    convertit jamais tout seul. La valeur nulle (zéro) signifie « depuis le début »,
    exactement comme le paramètre `after_seq` du serveur, qui est exclusif.
*/
class RunCursor
{
public:
    constexpr RunCursor() = default;
    constexpr explicit RunCursor(qint64 value) : m_value(value) {}

    [[nodiscard]] constexpr qint64 value() const { return m_value; }
    [[nodiscard]] constexpr bool isBeginning() const { return m_value <= 0; }

    friend constexpr auto operator<=>(RunCursor, RunCursor) = default;
    friend constexpr bool operator==(RunCursor, RunCursor) = default;

private:
    qint64 m_value = 0;
};

/*!
    Curseur de la portée « projet » (EventModel.journal_seq).

    Volontairement dépourvu de toute conversion vers RunCursor : le compilateur refuse
    `ProjectCursor{c.value()}` seulement si on ne l'écrit pas, mais il refuse
    `ProjectCursor p = runCursor;` et toute comparaison croisée, ce qui couvre les erreurs
    réellement commises en pratique (passer un curseur au mauvais appel).
*/
class ProjectCursor
{
public:
    constexpr ProjectCursor() = default;
    constexpr explicit ProjectCursor(qint64 value) : m_value(value) {}

    [[nodiscard]] constexpr qint64 value() const { return m_value; }
    [[nodiscard]] constexpr bool isBeginning() const { return m_value <= 0; }

    friend constexpr auto operator<=>(ProjectCursor, ProjectCursor) = default;
    friend constexpr bool operator==(ProjectCursor, ProjectCursor) = default;

private:
    qint64 m_value = 0;
};

// Vérifications à la compilation : la confusion des deux espaces ne doit pas compiler.
static_assert(!std::is_convertible_v<RunCursor, ProjectCursor>,
              "RunCursor ne doit jamais se convertir en ProjectCursor.");
static_assert(!std::is_convertible_v<ProjectCursor, RunCursor>,
              "ProjectCursor ne doit jamais se convertir en RunCursor.");
static_assert(!std::is_convertible_v<qint64, RunCursor>,
              "Un entier nu ne doit jamais devenir un RunCursor sans intention explicite.");
static_assert(!std::is_convertible_v<qint64, ProjectCursor>,
              "Un entier nu ne doit jamais devenir un ProjectCursor sans intention explicite.");

} // namespace acp
