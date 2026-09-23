// Recul progressif de reconnexion.
//
// Le serveur n'émet AUCUN champ SSE `retry` : toute la politique de reconnexion est à la
// charge du client. Ces tests éprouvent la partie déterministe — la progression et le
// plafond — et vérifient que la gigue reste bornée, sans jamais dépendre d'un tirage
// particulier.

#include "events/Backoff.h"

#include <QTest>

using namespace acp;

class TestBackoff : public QObject
{
    Q_OBJECT

private slots:
    void baseDelayDoublesUntilCeiling();
    void nextDelayStaysWithinJitterBand();
    void resetReturnsToInitialDelay();
    void countsConsecutiveFailures();
    void zeroJitterIsDeterministic();
    void ceilingIsNeverExceededEvenAfterManyFailures();
};

void TestBackoff::baseDelayDoublesUntilCeiling()
{
    const Backoff backoff(std::chrono::milliseconds(1000), std::chrono::milliseconds(8000), 0);
    QCOMPARE(backoff.baseDelayForAttempt(0).count(), 1000);
    QCOMPARE(backoff.baseDelayForAttempt(1).count(), 2000);
    QCOMPARE(backoff.baseDelayForAttempt(2).count(), 4000);
    QCOMPARE(backoff.baseDelayForAttempt(3).count(), 8000);
    QCOMPARE(backoff.baseDelayForAttempt(4).count(), 8000);
}

void TestBackoff::nextDelayStaysWithinJitterBand()
{
    Backoff backoff(std::chrono::milliseconds(1000), std::chrono::milliseconds(30000), 25);
    for (int attempt = 0; attempt < 6; ++attempt) {
        const auto base = backoff.baseDelayForAttempt(attempt);
        const auto delay = backoff.nextDelay();
        QVERIFY(delay.count() >= base.count());
        QVERIFY(delay.count() <= base.count() + base.count() / 4 + 1);
    }
}

void TestBackoff::resetReturnsToInitialDelay()
{
    Backoff backoff(std::chrono::milliseconds(500), std::chrono::milliseconds(8000), 0);
    backoff.nextDelay();
    backoff.nextDelay();
    QCOMPARE(backoff.consecutiveFailures(), 2);
    backoff.reset();
    QCOMPARE(backoff.consecutiveFailures(), 0);
    QCOMPARE(backoff.nextDelay().count(), 500);
}

void TestBackoff::countsConsecutiveFailures()
{
    Backoff backoff;
    QCOMPARE(backoff.consecutiveFailures(), 0);
    backoff.nextDelay();
    backoff.nextDelay();
    backoff.nextDelay();
    // Le service bascule en interrogation périodique à partir de quatre échecs : ce
    // compteur est ce qui déclenche l'aveu « Interrogation périodique » plutôt qu'un
    // « Reconnexion » perpétuel.
    QCOMPARE(backoff.consecutiveFailures(), 3);
}

void TestBackoff::zeroJitterIsDeterministic()
{
    Backoff first(std::chrono::milliseconds(100), std::chrono::milliseconds(1000), 0);
    Backoff second(std::chrono::milliseconds(100), std::chrono::milliseconds(1000), 0);
    for (int index = 0; index < 5; ++index) {
        QCOMPARE(first.nextDelay().count(), second.nextDelay().count());
    }
}

void TestBackoff::ceilingIsNeverExceededEvenAfterManyFailures()
{
    Backoff backoff(std::chrono::milliseconds(1000), std::chrono::milliseconds(30000), 25);
    for (int index = 0; index < 60; ++index) {
        const auto delay = backoff.nextDelay();
        // Plafond plus la gigue maximale : aucun débordement d'entier, aucune attente
        // absurde après une longue coupure.
        QVERIFY(delay.count() <= 30000 + 30000 / 4 + 1);
    }
}

QTEST_APPLESS_MAIN(TestBackoff)

#include "tst_backoff.moc"
