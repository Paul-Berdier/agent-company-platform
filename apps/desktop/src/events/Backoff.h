// Recul progressif avec gigue.
//
// Deux raisons de l'isoler dans une classe testable plutôt que de le disperser :
//
//  1. Le serveur n'émet AUCUN champ SSE `retry` (audit, section 4.2) : toute la politique
//     de reconnexion est à la charge du client. Elle doit donc être écrite une fois et
//     éprouvée, pas improvisée à chaque site d'appel.
//  2. Le service `api` tourne à une seule réplique et subit une coupure à chaque
//     redéploiement (audit, section 10.3). Une flotte de postes qui reviendrait tous à la
//     même milliseconde transformerait un redéploiement en rafale. La gigue est une
//     obligation, pas une élégance.

#pragma once

#include <chrono>

namespace acp {

class Backoff
{
public:
    /*!
        \param initial  Attente de la première reprise.
        \param ceiling  Plafond d'attente ; jamais dépassé.
        \param jitterRatio Part d'aléa ajoutée, exprimée en centièmes de l'attente
               calculée (25 signifie « jusqu'à 25 % de plus »).
    */
    Backoff(std::chrono::milliseconds initial = std::chrono::milliseconds(1000),
            std::chrono::milliseconds ceiling = std::chrono::milliseconds(30000),
            int jitterPercent = 25);

    /*! Attente de la prochaine tentative, puis avance d'un cran. */
    std::chrono::milliseconds nextDelay();

    /*! Remet le compteur à zéro. Appelé dès qu'un flux a été ouvert ET a produit un
        premier signe de vie — jamais sur la seule ouverture de la connexion. */
    void reset();

    /*! Nombre de reculs consécutifs, pour l'écran de diagnostics. */
    [[nodiscard]] int consecutiveFailures() const { return m_attempt; }

    /*! Attente calculée sans gigue, exposée pour rendre les tests déterministes. */
    [[nodiscard]] std::chrono::milliseconds baseDelayForAttempt(int attempt) const;

private:
    std::chrono::milliseconds m_initial;
    std::chrono::milliseconds m_ceiling;
    int m_jitterPercent;
    int m_attempt = 0;
};

} // namespace acp
