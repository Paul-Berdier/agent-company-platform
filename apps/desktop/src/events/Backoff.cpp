#include "events/Backoff.h"

#include <QRandomGenerator>
#include <QtGlobal>

namespace acp {

Backoff::Backoff(std::chrono::milliseconds initial, std::chrono::milliseconds ceiling,
                 int jitterPercent)
    : m_initial(initial)
    , m_ceiling(ceiling)
    , m_jitterPercent(qBound(0, jitterPercent, 100))
{
}

std::chrono::milliseconds Backoff::baseDelayForAttempt(int attempt) const
{
    if (attempt <= 0) {
        return m_initial;
    }
    // Doublement borné à 20 crans, ce qui suffit très largement avant le plafond et
    // écarte tout débordement d'entier.
    const int exponent = qMin(attempt, 20);
    const qint64 doubled = m_initial.count() << exponent;
    return std::chrono::milliseconds(qMin<qint64>(doubled, m_ceiling.count()));
}

std::chrono::milliseconds Backoff::nextDelay()
{
    const std::chrono::milliseconds base = baseDelayForAttempt(m_attempt);
    ++m_attempt;
    if (m_jitterPercent == 0) {
        return base;
    }
    const qint64 span = base.count() * m_jitterPercent / 100;
    if (span <= 0) {
        return base;
    }
    const qint64 jitter = QRandomGenerator::global()->bounded(static_cast<int>(span) + 1);
    return std::chrono::milliseconds(base.count() + jitter);
}

void Backoff::reset()
{
    m_attempt = 0;
}

} // namespace acp
