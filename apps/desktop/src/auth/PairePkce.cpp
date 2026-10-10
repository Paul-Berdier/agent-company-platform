#include "auth/PairePkce.h"

#include "storage/CredentialVault.h"

#include <QCryptographicHash>
#include <QRandomGenerator>

#include <array>
#include <cstring>

namespace acp {

namespace {

QByteArray octetsAleatoires(int nombre)
{
    // QRandomGenerator::system() puise dans le générateur cryptographique du système
    // (RtlGenRandom / BCryptGenRandom sous Windows) : c'est celui qu'exige RFC 7636 § 7.1.
    constexpr int kMots = 32;
    std::array<quint32, kMots> mots{};
    const int motsUtiles = (nombre + 3) / 4;
    Q_ASSERT(motsUtiles <= kMots);
    QRandomGenerator::system()->fillRange(mots.data(), static_cast<qsizetype>(motsUtiles));
    QByteArray resultat(reinterpret_cast<const char *>(mots.data()), nombre);
    std::memset(mots.data(), 0, sizeof(mots));
    return resultat;
}

} // namespace

PairePkce::~PairePkce()
{
    effacer();
}

PairePkce::PairePkce(PairePkce &&other) noexcept
    : m_verificateur(std::move(other.m_verificateur))
    , m_defi(std::move(other.m_defi))
    , m_etat(std::move(other.m_etat))
{
}

PairePkce &PairePkce::operator=(PairePkce &&other) noexcept
{
    if (this != &other) {
        effacer();
        m_verificateur = std::move(other.m_verificateur);
        m_defi = std::move(other.m_defi);
        m_etat = std::move(other.m_etat);
    }
    return *this;
}

PairePkce PairePkce::generer()
{
    PairePkce paire;
    QByteArray brut = octetsAleatoires(kOctetsVerificateur);
    paire.m_verificateur = base64Url(brut);
    CredentialVault::wipe(brut);
    paire.m_defi = defiS256(paire.m_verificateur);
    QByteArray brutEtat = octetsAleatoires(kOctetsEtat);
    paire.m_etat = base64Url(brutEtat);
    CredentialVault::wipe(brutEtat);
    return paire;
}

QByteArray PairePkce::base64Url(const QByteArray &octets)
{
    return octets.toBase64(QByteArray::Base64UrlEncoding | QByteArray::OmitTrailingEquals);
}

QByteArray PairePkce::defiS256(const QByteArray &verificateur)
{
    return base64Url(QCryptographicHash::hash(verificateur, QCryptographicHash::Sha256));
}

bool PairePkce::verificateurValide(const QByteArray &verificateur)
{
    if (verificateur.size() < 43 || verificateur.size() > 128) {
        return false;
    }
    for (const char caractere : verificateur) {
        const bool lettre = (caractere >= 'A' && caractere <= 'Z')
            || (caractere >= 'a' && caractere <= 'z');
        const bool chiffre = caractere >= '0' && caractere <= '9';
        const bool reserveNon = caractere == '-' || caractere == '.' || caractere == '_'
            || caractere == '~';
        if (!lettre && !chiffre && !reserveNon) {
            return false;
        }
    }
    return true;
}

void PairePkce::effacer()
{
    CredentialVault::wipe(m_verificateur);
    CredentialVault::wipe(m_defi);
    CredentialVault::wipe(m_etat);
}

bool egalATempsConstant(const QByteArray &attendu, const QByteArray &recu)
{
    if (attendu.isEmpty() || attendu.size() != recu.size()) {
        return false;
    }
    unsigned char difference = 0;
    for (qsizetype index = 0; index < attendu.size(); ++index) {
        difference |= static_cast<unsigned char>(attendu.at(index) ^ recu.at(index));
    }
    return difference == 0;
}

} // namespace acp
