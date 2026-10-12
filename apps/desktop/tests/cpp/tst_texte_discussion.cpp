#include "services/TexteDiscussion.h"
#include <QTest>
#include <QClipboard>
#include <QGuiApplication>
using namespace acp;
class TestTexteDiscussion : public QObject
{
    Q_OBJECT
private slots:
    void blocsEtCode() {
        TexteDiscussion texte;
        const auto blocs = texte.blocs(QStringLiteral("# Résultat\n\n**Prêt**\n```cpp\nif (a < b) {\n  return 1;\n}\n```\nFin"));
        QCOMPARE(blocs.size(), 3);
        QVERIFY(blocs[0].toMap().value(QStringLiteral("html")).toString().contains(QStringLiteral("font-weight")));
        QCOMPARE(blocs[1].toMap().value(QStringLiteral("genre")).toString(), QStringLiteral("code"));
        QCOMPARE(blocs[1].toMap().value(QStringLiteral("langue")).toString(), QStringLiteral("cpp"));
        QCOMPARE(blocs[1].toMap().value(QStringLiteral("texte")).toString(), QStringLiteral("if (a < b) {\n  return 1;\n}\n"));
        QCOMPARE(blocs[2].toMap().value(QStringLiteral("texte")).toString(), QStringLiteral("Fin"));
    }
    void fluxEtCloture() {
        TexteDiscussion texte;
        auto blocs = texte.blocs(QStringLiteral("~~~python\nprint('bonjour')\n````\n"));
        QCOMPARE(blocs.size(), 1);
        QCOMPARE(blocs[0].toMap().value(QStringLiteral("genre")).toString(), QStringLiteral("code"));
        QVERIFY(blocs[0].toMap().value(QStringLiteral("texte")).toString().contains(QStringLiteral("````")));
        blocs = texte.blocs(QStringLiteral("````js\n```\n````\n"));
        QCOMPARE(blocs[0].toMap().value(QStringLiteral("texte")).toString(), QStringLiteral("```\n"));
    }
    void pasDeRessources() {
        const QString html = TexteDiscussion::htmlSur(QStringLiteral(
            "![fichier](file:///C:/secret.png)\n![distant](https://example.com/pixel.png)\n"
            "<img src=\"https://example.com/brut.png\">\n<script>alert(1)</script>\n"
            "[ouvrir](javascript:alert) [fichier](file:///C:/secret.txt) [site](https://example.com/guide)"));
        QVERIFY(!html.contains(QStringLiteral("<img"), Qt::CaseInsensitive));
        QVERIFY(!html.contains(QStringLiteral("<script"), Qt::CaseInsensitive));
        QVERIFY(!html.contains(QStringLiteral("href=\"javascript:"), Qt::CaseInsensitive));
        QVERIFY(!html.contains(QStringLiteral("href=\"file:"), Qt::CaseInsensitive));
        QVERIFY(html.contains(QStringLiteral("href=\"https://example.com/guide\"")));
    }
    void liens() {
        QVERIFY(TexteDiscussion::lienAutorise(QUrl(QStringLiteral("https://example.com/guide"))));
        QVERIFY(!TexteDiscussion::lienAutorise(QUrl(QStringLiteral("https://user:secret@example.com"))));
        for (const QString &lien : {QStringLiteral("file:///C:/x"), QStringLiteral("javascript:alert(1)"),
             QStringLiteral("data:text/html,x"), QStringLiteral("mailto:x@y.com"), QStringLiteral("/relatif")})
            QVERIFY(!TexteDiscussion::lienAutorise(QUrl(lien)));
    }
    void copieEtMessageLong() {
        TexteDiscussion texte;
        const QString contenu(200001, u'x');
        QCOMPARE(texte.blocs(contenu)[0].toMap().value(QStringLiteral("texte")).toString(), contenu);
        QVERIFY(texte.copier(QStringLiteral("a < b\n")));
        QCOMPARE(QGuiApplication::clipboard()->text(), QStringLiteral("a < b\n"));
        QGuiApplication::clipboard()->clear();
    }
};
QTEST_MAIN(TestTexteDiscussion)
#include "tst_texte_discussion.moc"
