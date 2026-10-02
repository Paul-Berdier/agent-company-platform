// Page Quotas de la station (cahier P8 § 7.6), sur `GET /v1/quotas` du greffon, relu toutes
// les 60 s tant que la page est affichée (les relevés vivent en heures). Même contenu que la
// vue « Quotas » de la page web (apps/interface/src/poste/Quotas.tsx) :
//
//  - par voie du poste (`poste-codex`, `poste-claude`) : état du relevé (Relevé, Périmé,
//    Inconnu), date, seuil du routage, source déclarée, détail, et chaque compteur avec ses
//    fenêtres (part utilisée, part restante, remise à zéro, offre, limite atteinte) ;
//  - Hermes : le libellé rendu par le greffon (« Même enveloppe que Codex » seulement si le
//    poste le déclare), sinon « Inconnu ».
//
// Rien n'est estimé : une part absente reste « Inconnu », une jauge n'est dessinée que pour
// une part RESTANTE rendue par le serveur. « Relever maintenant » → `POST /v1/poste/releve`.

#pragma once

#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"

#include <QJsonObject>
#include <QString>

#include <chrono>

namespace acp {

class ClientGreffonPoste;
class Sondage;

class QuotasViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(bool lue READ lue NOTIFY quotasChange)
    Q_PROPERTY(JsonListModel *voies READ voies CONSTANT)
    Q_PROPERTY(QString hermes READ hermes NOTIFY quotasChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY lectureChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY lectureChange)

public:
    static constexpr std::chrono::milliseconds kIntervalle{60000};

    QuotasViewModel(ClientGreffonPoste *greffon, EventStreamService *flux, QObject *parent = nullptr);
    ~QuotasViewModel() override;

    [[nodiscard]] bool lue() const { return m_lue; }
    [[nodiscard]] JsonListModel *voies() const { return m_voies; }
    [[nodiscard]] const QString &hermes() const { return m_hermes; }
    [[nodiscard]] QString lecture() const;
    [[nodiscard]] QString erreur() const;
    [[nodiscard]] Sondage *sondage() const { return m_sondage; }

    Q_INVOKABLE void actualiser();
    Q_INVOKABLE void relever();

    // --- Fonctions pures (tests) ------------------------------------------------------------
    [[nodiscard]] static QJsonObject construireVoie(const QString &voie, const QJsonObject &quotas);
    [[nodiscard]] static QJsonObject construireCompteur(const QJsonObject &compteur, const QJsonValue &seuil);
    [[nodiscard]] static QJsonObject construireFenetre(const QJsonObject &fenetre, const QJsonValue &seuil);

signals:
    void quotasChange();
    void lectureChange();

protected:
    void surActivite(bool actif) override;
    void surLienRetabli() override;
    void surOubli() override;

private:
    void lire(const QJsonObject &vue);

    ClientGreffonPoste *m_greffon = nullptr;
    Sondage *m_sondage = nullptr;
    JsonListModel *m_voies = nullptr;
    bool m_lue = false;
    QString m_hermes;
};

} // namespace acp
