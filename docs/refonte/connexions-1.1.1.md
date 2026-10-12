# Connexions et reprise de session — correctif 1.1.1

État au 12 octobre 2026 : correctif compilé et paquet local préparé ; validations locales réussies, CI GitHub à terminer.
Ce document décrit les changements du code et le parcours. La publication GitHub
et la reprise de l’installation personnelle restent à confirmer.

## Ce qui change au démarrage

ACP conserve un écran explicite pendant la reprise d'une session mémorisée :
« Reprise de votre session… », puis le résultat de la vérification. Une reprise
inachevée permet de retenter depuis cet écran. Le passage au bureau dépend de
l'état de la session ; une attente ne doit plus laisser une page vide.

La liaison avec Hermes attend une session authentifiée et un verdict de
compatibilité utilisable. Si un premier verdict l'a fermée, un nouveau verdict
compatible permet de la rouvrir. Cette reprise ne force pas une nouvelle liaison
lorsqu'une connexion ou une reconnexion est déjà en cours, ni après une
déconnexion volontaire ou l'arrêt d'ACP.

Ces défauts ont été identifiés dans le code. Le message d'erreur exact rencontré
sur l'installation personnelle reste attendu : leur responsabilité dans cet
incident n'est donc pas établie.

## Lire les connexions depuis l'accueil

L'accueil présente deux cartes qui répondent à des questions différentes.

| Carte | Ce qu'elle vérifie | Prochaine étape proposée |
| --- | --- | --- |
| **Hermes · coordinateur** | La configuration du fournisseur et du modèle utilisés par Hermes, dès que sa liaison est disponible. | Retrouver une configuration existante, vérifier Hermes, connecter ChatGPT ou ouvrir son tableau de bord selon le résultat. |
| **Vos assistants de codage** | L'état de la machine et les connexions Codex / Claude Code rapportées par son dernier relevé. | Voir la machine, vérifier ses connexions, configurer un assistant manquant ou relire les modèles autorisés selon l'état observé. |

Une configuration Hermes retrouvée ne prouve pas qu'une réponse du modèle a été
produite : la prochaine discussion confirmera cet accès. Le contrôle automatique
ne lance pas une conversation de test et ne remplace pas un fournisseur déjà
configuré.

Pour les assistants, le relevé est daté. Une machine hors ligne, une lecture
impossible ou un état inconnu restent indiqués comme tels. Une connexion déjà
repérée peut être conservée ; il n'est pas nécessaire de reconnecter les deux
assistants. Leur accès aux modèles, les quotas, le routage et le dépôt restent à
contrôler au lancement du travail. Ces cartes ne signifient pas « tout est
connecté et prêt à exécuter ».

## Connecter ChatGPT au coordinateur Hermes

Si cette connexion manque, le bouton **Connecter ChatGPT à Hermes** démarre le
parcours depuis ACP. L'application affiche un code temporaire, sa durée de
validité et **Ouvrir OpenAI**. L'autorisation se termine dans le navigateur sur
`https://auth.openai.com/codex/device` ; **Copier le code** aide à saisir ce code
sur cette page. ACP suit le résultat et permet d'annuler la demande.

Après l'autorisation, ACP vérifie à nouveau la configuration Hermes. Une
confirmation OpenAI seule ne suffit pas à afficher le coordinateur comme prêt.
Si le choix du modèle reste à régler, la carte propose le tableau de bord et une
nouvelle vérification.

Ce compte sert au **coordinateur Hermes**. Il est distinct des connexions Codex
et Claude Code de **l'exécutant**, qui restent visibles dans l'autre carte. Une
connexion ChatGPT du coordinateur ne connecte pas automatiquement l'exécutant.
Aucun mot de passe, jeton ou fichier de compte n'est à recopier dans ACP ; seul
le code temporaire affiché est destiné au parcours d'autorisation OpenAI.

## Mise à jour depuis une ancienne version

L'installateur local **Setup 1.1.1** est compilé et préparé dans ce checkout.
Il est **non signé et n'a pas été installé**. La validation locale est réussie ; la CI finale
reste à terminer. Ce paquet local n'atteste pas une publication GitHub.

| Paquet local | Valeur |
| --- | --- |
| Chemin depuis la racine du dépôt | [`dist/startup-1.1.1/AgentCompanyPlatform-Setup-1.1.1-x64.exe`](../../dist/startup-1.1.1/AgentCompanyPlatform-Setup-1.1.1-x64.exe) |
| Taille | 24 689 082 octets |
| SHA-256 | `ef9637ae0b62f7a7221fcafaccd5e6dc97286428fa1d3e9dbe9a5a7c6454dee6` |
| Fichier de référence local | [`dist/startup-1.1.1/SHA256SUMS.txt`](../../dist/startup-1.1.1/SHA256SUMS.txt) |

Après la validation finale, la mise à jour se fait ainsi :

1. Fermer ACP. Cela ne met pas automatiquement les projets Hermes en pause.
2. Vérifier l'empreinte du Setup avec `Get-FileHash -Algorithm SHA256` et la
   comparer à la valeur ci-dessus. Une empreinte correspondante n'est pas une
   signature de l'éditeur.
3. Ouvrir cet installateur avec le même compte Windows et dans le même mode
   d'installation que la version existante. La mise à jour sur place ne demande
   pas de désinstallation préalable : conserver les réglages et le coffre
   Windows, sans effacer les données d'ACP ni recopier des identifiants.
4. Relancer ACP : l'adresse du serveur et la session mémorisée sont reprises
   lorsque ces données existent et que la session reste valide. Si la session
   n'a pas été mémorisée ou a expiré, reprendre la connexion dans le navigateur.
5. Lire les deux cartes de l'accueil et suivre la prochaine action indiquée.

Le Setup met à jour le client desktop ; il ne remplace ni Hermes ni l'exécutant
séparé. Le [guide de mise à jour et de récupération](../mettre-a-jour-1.1.md)
explique les vérifications des paquets et la récupération du travail. Ces étapes
n'ont pas été exécutées sur l'installation personnelle.

## Vérifications et limites actuelles

| Vérification | État acquis |
| --- | --- |
| Reprise de session, compatibilité de la liaison, préparation Hermes et états des assistants | 37/37 suites Qt réussies sur le client final avec les polices Windows (121,92 s). Les 19 interactions passent aussi en exécution directe ; captures et comptes isolés. |
| Santé publique du serveur Hermes 0.21.5 | Réponse de santé correcte. Elle ne prouve ni la session personnelle, ni la connexion à un fournisseur, ni l'exécution d'un modèle. |
| Fenêtre de l'installation personnelle | Non contrôlée : les outils Computer Use ne démarrent pas, avec une erreur `deny-read ACLs`. Aucun état de cet écran n'a été observé. |
| Erreur personnelle exacte | Encore attendue ; aucun diagnostic de cet incident n'est confirmé. |
| Setup local 1.1.1 | Paquet préparé ; taille et empreinte relevées dans les métadonnées locales et `SHA256SUMS.txt`. Non signé, non installé. |
| Validation Python Windows | 1 289 tests et 464 sous-tests réussis, 106 ignorés pour leurs conditions de plateforme ou conteneur ; aucun échec (1 149,98 s). |
| CI finale | À terminer ; aucune réussite GitHub revendiquée à ce stade. |
| Installation et reprise personnelles avec Setup 1.1.1 | Non réalisées. |

La prochaine étape est de terminer les validations et la publication, puis de vérifier
la reprise réelle après mise à jour à partir du message affiché dans ACP. Aucune
connexion personnelle ou exécution payante n'est attestée par les tests isolés.
