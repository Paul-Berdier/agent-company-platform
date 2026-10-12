#include "services/TexteDiscussion.h"
#include <QClipboard>
#include <QDesktopServices>
#include <QGuiApplication>
#include <QRegularExpression>
#include <QTextDocument>
#include <QVariantMap>

namespace acp {
namespace {
// Même une référence à un fichier local n'est jamais résolue pendant le rendu.
class DocumentSansRessource final : public QTextDocument
{
protected:
    QVariant loadResource(int, const QUrl &) override { return {}; }
};
}

bool TexteDiscussion::lienAutorise(const QUrl &url)
{
    return url.isValid() && !url.host().isEmpty() && url.userInfo().isEmpty()
        && (url.scheme() == QLatin1String("https") || url.scheme() == QLatin1String("http"));
}

QString TexteDiscussion::htmlSur(const QString &texte)
{
    DocumentSansRessource document;
    document.setMarkdown(texte, QTextDocument::MarkdownNoHTML);
    QString html = document.toHtml();
    // QML rend le HTML obtenu dans un second document : aucune image ne doit y
    // déclencher une nouvelle lecture réseau, locale ou embarquée.
    static const QRegularExpression images(QStringLiteral("<img\\b[^>]*>"), QRegularExpression::CaseInsensitiveOption);
    html.replace(images, QStringLiteral("[Image non chargée]"));
    static const QRegularExpression liens(QStringLiteral("<a\\s+href=\"([^\"]*)\"[^>]*>(.*?)</a>"),
        QRegularExpression::CaseInsensitiveOption | QRegularExpression::DotMatchesEverythingOption);
    auto it = liens.globalMatch(html);
    QList<QRegularExpressionMatch> matches;
    while (it.hasNext()) matches.append(it.next());
    for (auto i = matches.crbegin(); i != matches.crend(); ++i) {
        const QString href = i->captured(1);
        if (!lienAutorise(QUrl(href, QUrl::StrictMode))) html.replace(i->capturedStart(), i->capturedLength(), i->captured(2));
    }
    static const QRegularExpression corps(QStringLiteral("<body[^>]*>(.*)</body>"),
        QRegularExpression::CaseInsensitiveOption | QRegularExpression::DotMatchesEverythingOption);
    const auto contenu = corps.match(html);
    return contenu.hasMatch() ? contenu.captured(1) : html;
}

QVariantList TexteDiscussion::blocs(const QString &texte) const
{
    QVariantList resultat;
    // Sur un historique inhabituellement grand, conserver le texte intégral en
    // évitant le coût du parseur Markdown. La copie n'est jamais tronquée.
    if (texte.size() > 200000) {
        resultat.append(QVariantMap{{QStringLiteral("genre"), QStringLiteral("brut")},
            {QStringLiteral("texte"), texte}, {QStringLiteral("langue"), QString()}, {QStringLiteral("html"), QString()}});
        return resultat;
    }
    const QStringList lignes = QString(texte).replace(QStringLiteral("\r\n"), QStringLiteral("\n")).split(u'\n');
    static const QRegularExpression debut(QStringLiteral("^ {0,3}(`{3,}|~{3,})(.*)$"));
    QString prose, code, langue;
    QChar marque;
    int longueur = 0;
    auto ajouter = [&](const QString &genre, const QString &contenu, const QString &langage) {
        if (contenu.isEmpty() && genre != QLatin1String("code")) return;
        resultat.append(QVariantMap{{QStringLiteral("genre"), genre}, {QStringLiteral("texte"), contenu},
            {QStringLiteral("langue"), langage}, {QStringLiteral("html"), genre == QLatin1String("prose") ? htmlSur(contenu) : QString()}});
    };
    for (qsizetype index = 0; index < lignes.size(); ++index) {
        const QString &ligne = lignes.at(index);
        const QRegularExpressionMatch m = debut.match(ligne);
        const bool derniere = index + 1 == lignes.size();
        if (longueur == 0 && m.hasMatch()
            && !(m.captured(1).startsWith(u'`') && m.captured(2).contains(u'`'))) {
            ajouter(QStringLiteral("prose"), prose, {}); prose.clear();
            marque = m.captured(1).at(0); longueur = m.captured(1).size();
            langue = m.captured(2).trimmed().section(u' ', 0, 0).left(40);
        } else if (longueur > 0 && m.hasMatch() && m.captured(1).at(0) == marque
            && m.captured(1).size() >= longueur && m.captured(2).trimmed().isEmpty()) {
            ajouter(QStringLiteral("code"), code, langue); code.clear(); langue.clear(); longueur = 0;
        } else {
            QString &cible = longueur > 0 ? code : prose;
            cible += ligne;
            if (!derniere) cible += u'\n';
        }
    }
    if (longueur > 0) ajouter(QStringLiteral("code"), code, langue);
    else ajouter(QStringLiteral("prose"), prose, {});
    return resultat;
}

bool TexteDiscussion::copier(const QString &texte) const
{
    if (!QGuiApplication::instance() || !QGuiApplication::clipboard()) return false;
    QGuiApplication::clipboard()->setText(texte);
    return true;
}

bool TexteDiscussion::ouvrirLien(const QString &lien) const
{
    const QUrl url(lien, QUrl::StrictMode);
    return lienAutorise(url) && QDesktopServices::openUrl(url);
}
} // namespace acp
