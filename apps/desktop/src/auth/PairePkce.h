// Paire PKCE (RFC 7636) et état de la connexion native (RFC 8252).
//
// Le vérificateur, son défi S256 et l'état anti-falsification sont tirés du générateur du
// système (QRandomGenerator::system(), CSPRNG), jamais d'un générateur déterministe. Les
// trois valeurs ne vivent que le temps d'un flux de connexion : elles sont effacées à sa
// fin, quelle qu'elle soit, et ne sont jamais journalisées ni publiées vers QML.
//
// Transformation S256 identique à celle de Hermes (hermes_cli/dashboard_auth/native_flow.py,
// `_s256`) : base64url(SHA-256(ASCII(vérificateur))), sans remplissage.

#pragma once

#include <QByteArray>

namespace acp {

class PairePkce
{
public:
    //! Octets aléatoires du vérificateur : 64 octets donnent 86 caractères base64url,
    //! dans la plage 43 à 128 exigée par RFC 7636 § 4.1.
    static constexpr int kOctetsVerificateur = 64;
    //! Octets aléatoires de l'état : 32 octets, 256 bits, 43 caractères base64url.
    static constexpr int kOctetsEtat = 32;

    PairePkce() = default;
    ~PairePkce();
    PairePkce(const PairePkce &) = delete;
    PairePkce &operator=(const PairePkce &) = delete;
    PairePkce(PairePkce &&other) noexcept;
    PairePkce &operator=(PairePkce &&other) noexcept;

    /*! Tire une paire neuve et son état. */
    [[nodiscard]] static PairePkce generer();

    /*! base64url(SHA-256(vérificateur)) sans remplissage (RFC 7636 § 4.2). */
    [[nodiscard]] static QByteArray defiS256(const QByteArray &verificateur);

    /*! 43 à 128 caractères parmi [A-Z] [a-z] [0-9] « - » « . » « _ » « ~ » (RFC 7636 § 4.1). */
    [[nodiscard]] static bool verificateurValide(const QByteArray &verificateur);

    /*! Encodage base64url sans remplissage d'octets quelconques. */
    [[nodiscard]] static QByteArray base64Url(const QByteArray &octets);

    [[nodiscard]] const QByteArray &verificateur() const { return m_verificateur; }
    [[nodiscard]] const QByteArray &defi() const { return m_defi; }
    [[nodiscard]] const QByteArray &etat() const { return m_etat; }
    [[nodiscard]] bool estVide() const { return m_verificateur.isEmpty(); }

    /*! Écrase les trois valeurs. Idempotent. */
    void effacer();

private:
    QByteArray m_verificateur;
    QByteArray m_defi;
    QByteArray m_etat;
};

/*!
    Comparaison d'octets à temps constant sur la longueur attendue.

    Deux longueurs différentes rendent faux ; le contenu est toujours parcouru en entier,
    sans sortie anticipée sur le premier octet différent (équivalent de hmac.compare_digest).
*/
[[nodiscard]] bool egalATempsConstant(const QByteArray &attendu, const QByteArray &recu);

} // namespace acp
