#pragma once
#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
namespace acp::test {
inline QString connexionTestId() { return QStringLiteral("d41e9599-bc00-4581-9f46-00e134668c30"); }
inline QJsonObject connexionTest(const QString &etat=QStringLiteral("code_disponible")) {
    return {{QStringLiteral("id"),connexionTestId()},{QStringLiteral("moteur"),QStringLiteral("codex")},
        {QStringLiteral("etat"),etat},{QStringLiteral("message"),QStringLiteral("Données simulées pour vérifier l’interface ; aucun compte personnel connecté.")},
        {QStringLiteral("limite_attente_le"),QDateTime::currentSecsSinceEpoch()+300},
        {QStringLiteral("verification_url"),QStringLiteral("https://auth.openai.com/codex/device")},
        {QStringLiteral("code_utilisateur"),QStringLiteral("TEST-ACP")},
        {QStringLiteral("compte_connecte"),etat==QStringLiteral("connecte")},{QStringLiteral("inference_verifiee"),false}};
}
inline QJsonObject comptesTest(const QJsonObject &connexion={}) {
    const bool connecte=connexion.value(QStringLiteral("etat"))==QStringLiteral("connecte");
    return {{QStringLiteral("protocole"),QStringLiteral("acp-comptes/1")},
        {QStringLiteral("serveur"),QJsonObject{{QStringLiteral("disponible"),true},{QStringLiteral("nom"),QStringLiteral("Serveur distant — simulation graphique")},{QStringLiteral("raison"),QJsonValue::Null}}},
        {QStringLiteral("comptes"),QJsonArray{
            QJsonObject{{QStringLiteral("moteur"),QStringLiteral("codex")},{QStringLiteral("nom"),QStringLiteral("Codex")},{QStringLiteral("implementation"),QStringLiteral("disponible")},
                {QStringLiteral("etat"),connecte?QStringLiteral("connecte"):connexion.isEmpty()?QStringLiteral("non_configure"):QStringLiteral("connexion_en_attente")},
                {QStringLiteral("version"),QStringLiteral("Version simulée")},{QStringLiteral("compte_connecte"),connecte},
                {QStringLiteral("inference_verifiee"),false},{QStringLiteral("modeles"),QJsonArray{}},{QStringLiteral("connexion"),connexion.isEmpty()?QJsonValue::Null:QJsonValue(connexion)},
                {QStringLiteral("message"),QStringLiteral("Connexion officielle exécutée sur le serveur distant.")}},
            QJsonObject{{QStringLiteral("moteur"),QStringLiteral("claude_code")},{QStringLiteral("nom"),QStringLiteral("Claude Code")},{QStringLiteral("implementation"),QStringLiteral("non_implemente")},
                {QStringLiteral("etat"),QStringLiteral("moteur_indisponible")},{QStringLiteral("modeles"),QJsonArray{}},{QStringLiteral("message"),QStringLiteral("Le parcours distant Claude Code n’est pas encore disponible.")}},
            QJsonObject{{QStringLiteral("moteur"),QStringLiteral("mistral_vibe")},{QStringLiteral("nom"),QStringLiteral("Mistral / Vibe")},{QStringLiteral("implementation"),QStringLiteral("non_implemente")},
                {QStringLiteral("etat"),QStringLiteral("moteur_indisponible")},{QStringLiteral("modeles"),QJsonArray{}},{QStringLiteral("message"),QStringLiteral("Le parcours distant Vibe n’est pas encore disponible.")}}}}};
}
}
