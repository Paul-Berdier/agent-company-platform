// Analyseur SSE : trames partielles, multilignes, commentaires, reprise.
//
// Ces tests encodent la spécification HTML « interpreting an event stream » et les
// particularités du serveur de ce produit : keep-alive « : ping », trames nommées
// `acp.event`, `acp.stream.rotate` et `acp.stream.closed`, et absence totale de champ
// `retry`.

#include "events/SseParser.h"

#include <QTest>

using namespace acp;

class TestSseParser : public QObject
{
    Q_OBJECT

private slots:
    void dispatchesSimpleEvent();
    void appliesDefaultEventType();
    void joinsMultilineData();
    void stripsExactlyOneLeadingSpace();
    void ignoresCommentLines();
    void toleratesFragmentSplitAnywhere();
    void toleratesCarriageReturnSplitAcrossChunks();
    void acceptsAllThreeLineTerminators();
    void skipsDispatchWhenDataBufferIsEmpty();
    void keepsLastEventIdAcrossEvents();
    void rejectsIdContainingNul();
    void decodesMultibyteUtf8SplitAcrossChunks();
    void stripsLeadingByteOrderMark();
    void parsesServerRotateFrame();
    void parsesServerClosedFrame();
    void readsRetryFieldOnlyWhenNumeric();
    void abandonsTruncatedBlockOnFinish();
    void keepsResumeIdentifierAcrossReset();
};

void TestSseParser::dispatchesSimpleEvent()
{
    SseParser parser;
    const QList<SseEvent> events =
        parser.consume(QByteArrayLiteral("id: 12\nevent: acp.event\ndata: {\"a\":1}\n\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).type, QStringLiteral("acp.event"));
    QCOMPARE(events.at(0).data, QStringLiteral("{\"a\":1}"));
    QCOMPARE(events.at(0).lastEventId, QStringLiteral("12"));
    QCOMPARE(parser.lastEventId(), QStringLiteral("12"));
}

void TestSseParser::appliesDefaultEventType()
{
    // Une trame sans nom DOIT être traitée comme un événement : c'est la valeur par
    // défaut de la spécification, et le CLI l'implémente ainsi.
    SseParser parser;
    const QList<SseEvent> events = parser.consume(QByteArrayLiteral("data: brut\n\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).type, QStringLiteral("message"));
    QVERIFY(events.at(0).isJournalEvent());
}

void TestSseParser::joinsMultilineData()
{
    SseParser parser;
    const QList<SseEvent> events =
        parser.consume(QByteArrayLiteral("data: ligne 1\ndata: ligne 2\ndata: ligne 3\n\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).data, QStringLiteral("ligne 1\nligne 2\nligne 3"));
}

void TestSseParser::stripsExactlyOneLeadingSpace()
{
    SseParser parser;
    // Deux espaces après le deux-points : une seule est retirée.
    const QList<SseEvent> events = parser.consume(QByteArrayLiteral("data:  deux\n\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).data, QStringLiteral(" deux"));
}

void TestSseParser::ignoresCommentLines()
{
    SseParser parser;
    // « : ping » est exactement le keep-alive du serveur, émis toutes les 15 secondes.
    QList<SseEvent> events = parser.consume(QByteArrayLiteral(": ping\n\n"));
    QCOMPARE(events.size(), 0);
    events = parser.consume(QByteArrayLiteral(": ping\ndata: utile\n\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).data, QStringLiteral("utile"));
}

void TestSseParser::toleratesFragmentSplitAnywhere()
{
    const QByteArray frame =
        QByteArrayLiteral("id: 7\nevent: acp.event\ndata: {\"clé\":\"valeur\"}\n\n");
    // Chaque point de coupure possible est éprouvé : un flux réel coupe n'importe où.
    for (qsizetype cut = 0; cut <= frame.size(); ++cut) {
        SseParser parser;
        QList<SseEvent> events = parser.consume(frame.left(cut));
        events += parser.consume(frame.mid(cut));
        QCOMPARE(events.size(), 1);
        QCOMPARE(events.at(0).data, QStringLiteral("{\"clé\":\"valeur\"}"));
        QCOMPARE(events.at(0).lastEventId, QStringLiteral("7"));
    }
}

void TestSseParser::toleratesCarriageReturnSplitAcrossChunks()
{
    // Le cas piégeux : un CRLF coupé entre le CR et le LF. Un analyseur naïf y voit une
    // ligne vide et dispatche trop tôt.
    SseParser parser;
    QList<SseEvent> events = parser.consume(QByteArrayLiteral("data: x\r"));
    QCOMPARE(events.size(), 0);
    events = parser.consume(QByteArrayLiteral("\n\r\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).data, QStringLiteral("x"));
}

void TestSseParser::acceptsAllThreeLineTerminators()
{
    {
        SseParser parser;
        const QList<SseEvent> events = parser.consume(QByteArrayLiteral("data: a\n\n"));
        QCOMPARE(events.size(), 1);
    }
    {
        SseParser parser;
        const QList<SseEvent> events = parser.consume(QByteArrayLiteral("data: b\r\r"));
        QCOMPARE(events.size(), 1);
        QCOMPARE(events.at(0).data, QStringLiteral("b"));
    }
    {
        SseParser parser;
        const QList<SseEvent> events = parser.consume(QByteArrayLiteral("data: c\r\n\r\n"));
        QCOMPARE(events.size(), 1);
        QCOMPARE(events.at(0).data, QStringLiteral("c"));
    }
}

void TestSseParser::skipsDispatchWhenDataBufferIsEmpty()
{
    SseParser parser;
    // Un bloc qui ne porte qu'un identifiant ne produit AUCUN événement, mais son
    // identifiant devient bien l'identifiant courant.
    const QList<SseEvent> events = parser.consume(QByteArrayLiteral("id: 99\n\n"));
    QCOMPARE(events.size(), 0);
    QCOMPARE(parser.lastEventId(), QStringLiteral("99"));
}

void TestSseParser::keepsLastEventIdAcrossEvents()
{
    SseParser parser;
    QList<SseEvent> events = parser.consume(QByteArrayLiteral("id: 4\ndata: un\n\n"));
    QCOMPARE(events.at(0).lastEventId, QStringLiteral("4"));
    // Deuxième trame SANS champ id : elle hérite de l'identifiant précédent.
    events = parser.consume(QByteArrayLiteral("data: deux\n\n"));
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).lastEventId, QStringLiteral("4"));
}

void TestSseParser::rejectsIdContainingNul()
{
    SseParser parser;
    QByteArray frame = QByteArrayLiteral("id: 5\ndata: a\n\nid: ");
    frame.append('\0');
    frame.append(QByteArrayLiteral("6\ndata: b\n\n"));
    QList<SseEvent> events = parser.consume(frame);
    QCOMPARE(events.size(), 2);
    // L'identifiant contenant U+0000 est écarté : l'ancien reste en place.
    QCOMPARE(events.at(1).lastEventId, QStringLiteral("5"));
}

void TestSseParser::decodesMultibyteUtf8SplitAcrossChunks()
{
    const QByteArray frame = QStringLiteral("data: éàü\n\n").toUtf8();
    for (qsizetype cut = 0; cut <= frame.size(); ++cut) {
        SseParser parser;
        QList<SseEvent> events = parser.consume(frame.left(cut));
        events += parser.consume(frame.mid(cut));
        QCOMPARE(events.size(), 1);
        QCOMPARE(events.at(0).data, QStringLiteral("éàü"));
    }
}

void TestSseParser::stripsLeadingByteOrderMark()
{
    SseParser parser;
    QByteArray frame = QByteArrayLiteral("\xEF\xBB\xBF");
    frame.append(QByteArrayLiteral("data: a\n\n"));
    const QList<SseEvent> events = parser.consume(frame);
    QCOMPARE(events.size(), 1);
    QCOMPARE(events.at(0).data, QStringLiteral("a"));
}

void TestSseParser::parsesServerRotateFrame()
{
    SseParser parser;
    const QList<SseEvent> events = parser.consume(QByteArrayLiteral(
        "id: 42\nevent: acp.stream.rotate\ndata: {\"cursor\":42,\"reason\":\"max_seconds\"}\n\n"));
    QCOMPARE(events.size(), 1);
    QVERIFY(events.at(0).isRotate());
    QVERIFY(!events.at(0).isJournalEvent());
    QCOMPARE(events.at(0).lastEventId, QStringLiteral("42"));
}

void TestSseParser::parsesServerClosedFrame()
{
    SseParser parser;
    const QList<SseEvent> events = parser.consume(
        QByteArrayLiteral("event: acp.stream.closed\ndata: {\"reason\":\"unauthorized\"}\n\n"));
    QCOMPARE(events.size(), 1);
    QVERIFY(events.at(0).isClosed());
    QVERIFY(events.at(0).data.contains(QStringLiteral("unauthorized")));
}

void TestSseParser::readsRetryFieldOnlyWhenNumeric()
{
    // Ce serveur n'émet aucun champ `retry` ; l'analyseur le gère quand même, parce que
    // la spécification l'exige et qu'un futur serveur pourrait en émettre.
    {
        SseParser parser;
        QCOMPARE(parser.consume(QByteArrayLiteral("retry: 2500\ndata: a\n\n")).size(), 1);
        QVERIFY(parser.retryMilliseconds().has_value());
        QCOMPARE(parser.retryMilliseconds().value(), 2500);
    }
    {
        SseParser parser;
        QCOMPARE(parser.consume(QByteArrayLiteral("retry: bientôt\ndata: a\n\n")).size(), 1);
        QVERIFY(!parser.retryMilliseconds().has_value());
    }
}

void TestSseParser::abandonsTruncatedBlockOnFinish()
{
    SseParser parser;
    QList<SseEvent> events = parser.consume(QByteArrayLiteral("data: incomplet\n"));
    QCOMPARE(events.size(), 0);
    // Le flux se ferme sans ligne vide : le bloc est abandonné, jamais complété par
    // hypothèse.
    events = parser.finish();
    QCOMPARE(events.size(), 0);
}

void TestSseParser::keepsResumeIdentifierAcrossReset()
{
    SseParser parser;
    QCOMPARE(parser.consume(QByteArrayLiteral("id: 314\ndata: a\n\n")).size(), 1);
    QCOMPARE(parser.lastEventId(), QStringLiteral("314"));
    // Une reconnexion réinitialise les tampons de trame mais CONSERVE l'identifiant de
    // reprise : sans cela, le client rejouerait le journal depuis le début.
    parser.resetFrameBuffers();
    QCOMPARE(parser.lastEventId(), QStringLiteral("314"));
    QCOMPARE(parser.pendingByteCount(), 0);
}

QTEST_APPLESS_MAIN(TestSseParser)

#include "tst_sse_parser.moc"
