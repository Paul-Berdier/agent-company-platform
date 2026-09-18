#include "events/SseParser.h"

namespace acp {

namespace {

//! Marque d'ordre des octets UTF-8. Retirée une seule fois, en tête de flux.
const QByteArray kUtf8Bom = QByteArrayLiteral("\xEF\xBB\xBF");

bool isAsciiDigits(const QString &text)
{
    if (text.isEmpty()) {
        return false;
    }
    for (const QChar character : text) {
        if (character < QLatin1Char('0') || character > QLatin1Char('9')) {
            return false;
        }
    }
    return true;
}

} // namespace

QList<SseEvent> SseParser::consume(const QByteArray &chunk)
{
    QList<SseEvent> out;
    m_pending.append(chunk);

    if (!m_bomChecked) {
        if (m_pending.size() >= kUtf8Bom.size()) {
            if (m_pending.startsWith(kUtf8Bom)) {
                m_pending.remove(0, kUtf8Bom.size());
            }
            m_bomChecked = true;
        } else if (kUtf8Bom.startsWith(m_pending)) {
            // Les octets reçus pourraient être le début d'une marque d'ordre : on attend
            // le fragment suivant plutôt que de décider trop tôt.
            return out;
        } else {
            m_bomChecked = true;
        }
    }

    qsizetype index = 0;
    while (true) {
        qsizetype terminator = -1;
        for (qsizetype position = index; position < m_pending.size(); ++position) {
            const char byte = m_pending.at(position);
            if (byte == '\n' || byte == '\r') {
                terminator = position;
                break;
            }
        }
        if (terminator < 0) {
            break;
        }
        if (m_pending.at(terminator) == '\r' && terminator == m_pending.size() - 1) {
            // Un retour chariot en dernière position : impossible de savoir encore s'il
            // est suivi d'un saut de ligne. On le garde pour le fragment suivant, sans
            // quoi un CRLF coupé en deux produirait une ligne vide fantôme — donc un
            // dispatch prématuré.
            break;
        }

        // Une ligne complète ne peut pas couper une séquence UTF-8 multi-octets : les
        // octets de continuation valent au moins 0x80 et ne peuvent donc jamais être
        // confondus avec CR ou LF. Le décodage par ligne est sûr.
        const QByteArray lineBytes = m_pending.mid(index, terminator - index);
        qsizetype next = terminator + 1;
        if (m_pending.at(terminator) == '\r' && next < m_pending.size()
            && m_pending.at(next) == '\n') {
            ++next;
        }
        handleLine(QString::fromUtf8(lineBytes), out);
        index = next;
    }

    if (index > 0) {
        m_pending.remove(0, index);
    }
    return out;
}

QList<SseEvent> SseParser::finish()
{
    QList<SseEvent> out;
    if (m_pending.endsWith('\r')) {
        // Le retour chariot retenu attendait un éventuel saut de ligne ; le flux est clos,
        // il ne viendra pas. C'était donc bien un terminateur de ligne.
        const QByteArray lineBytes = m_pending.left(m_pending.size() - 1);
        handleLine(QString::fromUtf8(lineBytes), out);
    }
    // Tout bloc tronqué est abandonné : un événement partiel n'est jamais complété par
    // hypothèse. L'identifiant de reprise, lui, est conservé.
    m_pending.clear();
    m_bomChecked = false;
    m_eventType.clear();
    m_dataBuffer.clear();
    return out;
}

void SseParser::resetFrameBuffers()
{
    m_pending.clear();
    m_bomChecked = false;
    m_eventType.clear();
    m_dataBuffer.clear();
    // m_idBuffer et m_lastEventId survivent : une reconnexion repart du dernier
    // événement reçu, jamais du début du journal.
}

void SseParser::handleLine(const QString &line, QList<SseEvent> &out)
{
    if (line.isEmpty()) {
        dispatch(out);
        return;
    }
    if (line.startsWith(QLatin1Char(':'))) {
        // Commentaire. C'est la forme du keep-alive du serveur, « : ping », émis toutes
        // les 15 secondes. Il ne produit aucun événement ; il prouve seulement que le
        // lien est vivant, ce dont EventStreamService tient compte séparément.
        return;
    }
    const qsizetype colon = line.indexOf(QLatin1Char(':'));
    if (colon < 0) {
        // Ligne sans deux-points : nom de champ, valeur vide.
        handleField(line, QString());
        return;
    }
    QString value = line.mid(colon + 1);
    if (value.startsWith(QLatin1Char(' '))) {
        // Une seule espace, et une seule.
        value.remove(0, 1);
    }
    handleField(line.left(colon), value);
}

void SseParser::handleField(const QString &field, const QString &value)
{
    if (field == QLatin1String("event")) {
        m_eventType = value;
        return;
    }
    if (field == QLatin1String("data")) {
        m_dataBuffer.append(value);
        m_dataBuffer.append(QLatin1Char('\n'));
        return;
    }
    if (field == QLatin1String("id")) {
        // La spécification écarte explicitement un identifiant contenant U+0000.
        if (!value.contains(QChar(u'\0'))) {
            m_idBuffer = value;
        }
        return;
    }
    if (field == QLatin1String("retry")) {
        if (isAsciiDigits(value)) {
            bool converted = false;
            const int milliseconds = value.toInt(&converted);
            if (converted) {
                m_retry = milliseconds;
            }
        }
        return;
    }
    // Tout autre champ est ignoré, sans erreur : c'est ce que la spécification impose,
    // et c'est ce qui permet au serveur d'ajouter un champ sans casser ce client.
}

void SseParser::dispatch(QList<SseEvent> &out)
{
    // L'identifiant courant est posé AVANT toute décision d'émission : il persiste même
    // quand le bloc ne produit aucun événement.
    m_lastEventId = m_idBuffer;

    if (m_dataBuffer.isEmpty()) {
        m_eventType.clear();
        return;
    }
    if (m_dataBuffer.endsWith(QLatin1Char('\n'))) {
        m_dataBuffer.chop(1);
    }

    SseEvent event;
    event.type = m_eventType.isEmpty() ? QStringLiteral("message") : m_eventType;
    event.data = m_dataBuffer;
    event.lastEventId = m_lastEventId;
    out.append(event);

    m_dataBuffer.clear();
    m_eventType.clear();
}

} // namespace acp
