# Workspace Hermes — ACP 1.2.0

## Ce que ce lot change

Discussion reste un client Qt natif de Hermes. Le lot reprend des usages utiles de
son interface web : recherche dans les discussions chargées, chargement progressif
jusqu’à 500 entrées, renommage, copie d’une discussion avec son historique, choix du
modèle pour la session, modèle effectif et consommation de contexte lorsqu’ils sont
communiqués par Hermes. Les réponses acceptent un Markdown contrôlé, avec copie des
messages et des blocs de code. Les détails des outils se déplient à la demande.

Le choix du modèle vient de l’inventaire de Hermes et respecte sa confirmation de
coût. Il utilise la portée `--session` : le modèle par défaut du serveur n’est pas
modifié. Un choix accepté ou différé n’est pas une preuve du modèle effectivement
utilisé ; l’affichage suit les informations de session renvoyées par Hermes.
Les brouillons sont conservés en mémoire par discussion pendant la navigation.
Ils ne sont pas restaurés après fermeture ou perte de session.

La page **Outils** réunit le catalogue du serveur et dix fiches d’intégration. Elle
permet de rechercher, lire les conditions d’utilisation, consulter la provenance,
copier une fiche et préparer un brouillon de consigne. Ce dernier geste n’envoie
aucun message et ne démarre aucune installation. La présence d’une fiche locale
ne signifie ni installation, ni connexion, ni autorisation d’exécuter son logiciel.

## La boucle du chef

Le chef est Hermes : il prépare un plan, délègue aux assistants disponibles,
organise une relecture croisée et synthétise les résultats quand les étapes sont
terminées. Les corrections repartent en relecture. Les budgets du projet bornent
les tours, cartes et corrections ; atteindre un plafond pose une question de
prolongation ou de conclusion. Le détail natif expose les compteurs réellement lus
et explique ce fonctionnement. Ce lot conserve le graphe déterministe existant.

Les méthodes Addy et Ponytail sont des textes sous licence MIT, épinglés et
vérifiés, avec des adaptations ACP pour les assistants. Les originaux restent
consultables avec leurs licences et leurs références. Les profils sélectionnent
les applications par rôle et classe de tâche ; `base` garde son fonctionnement
sans ajout tiers. Aucun hook ou programme de ces dépôts n’est installé. Lire le
[contrat du catalogue](../../hermes/catalogue/README.md) pour l’injection effective
et les profils concernés.

## Portée des intégrations

| Source | Livré par ce lot | Ce qui demande encore une mise en place |
|---|---|---|
| [Addy Agent Skills](https://github.com/addyosmani/agent-skills) | Six textes et adaptations par tâche | Mettre à jour le serveur, puis choisir le profil adapté |
| [Ponytail](https://github.com/DietrichGebert/ponytail) | Trois textes et adaptations de travail, revue et audit | Mettre à jour le serveur ; aucun hook upstream installé |
| [CRM](https://github.com/trycompai/crm) | Fiche API, authentification et périmètre de lecture | Instance, compte et adaptateur ACP |
| [REA](https://github.com/morluto/rea) | Fiche d’exécutant isolé et prérequis | Image exécutant et adaptateur de tâche vérifiés |
| [Douyin / TikTok API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) | Fiche MCP HTTP et droits de lecture | Service distinct et admission des outils dans la garde |
| [ML Intern](https://github.com/huggingface/ml-intern) | État du dépôt archivé et piste officielle Hugging Face | Alternative maintenue à choisir ; aucune installation de ML Intern |
| [Hackingtool](https://github.com/Z4nzu/hackingtool) | Référence descriptive | Choisir un outil précis et un périmètre autorisé avant toute intégration |
| [Graphify](https://github.com/Graphify-Labs/graphify) | Fiche d’extraction de code et conditions MCP | Exécutant ou service isolé par projet |
| [Obsidian](https://obsidian.md) | Coffre Markdown ACP, pont Windows autonome et éditeur natif avec recherche, liens, graphe et archives | Associer le coffre à Hermes après mise à jour du serveur ; aucune extension Obsidian nécessaire |
| [OmniRoute](https://github.com/diegosouzapw/OmniRoute) | Fiche API/MCP et conditions d’authentification | Service distinct et adaptateur respectant le routage ACP |

Les versions, commits, licences et configurations étudiés sont dans
[`sources.json`](../../apps/desktop/resources/integrations/sources.json).
Les clés de services ne doivent pas être collées dans Discussion. Chaque compte
reste connecté par son propre parcours d’authentification ; aucun compte personnel
n’a été connecté au cours des tests de ce lot.

## Nouveau coffre ACP pour Obsidian

Le paquet comprend **Coffre ACP - Obsidian**, un lanceur distinct du desktop et de
l’exécutant. Son Python et ses dépendances sont embarqués : aucun téléchargement
ni installation de Python n’est demandé au destinataire. Son identité ne remplace
pas celle des assistants Railway. La liaison sortante utilise uniquement l’origine
HTTPS de Hermes et n’ouvre aucun port local.

1. Mettre à jour Hermes vers l’image ACP 1.2.0 selon le manuel d’exploitation.
2. Ouvrir **Coffre ACP - Obsidian** depuis le menu Démarrer (ou
   `coffre/Lancer-Coffre-ACP.cmd` dans le paquet portable).
3. Choisir **Créer mon nouveau coffre ACP** et conserver le dossier proposé
   `Documents/ACP-notes`, ou choisir un autre dossier neuf. Un coffre déjà créé
   reste conservé : ne pas répéter cette étape pour une mise à jour du logiciel.
4. Dans la barre latérale du desktop, ouvrir **Coffre ACP**, puis le guide
   d’association et générer un code temporaire. Le copier avec le bouton prévu.
5. Dans le lanceur, choisir **Associer ce coffre à Hermes**, indiquer la même
   origine HTTPS que dans ACP et coller le code dans la saisie masquée.
6. Comparer l’empreinte affichée par le lanceur, la saisir dans ACP et confirmer.
   Le jeton du pont reste protégé par DPAPI dans la session Windows habituelle.
7. Choisir **Démarrer le bridge** et laisser cette fenêtre ouverte. Dans ACP,
   actualiser l’état puis lister les notes. Fermer le lanceur arrête la liaison.
8. Dans Obsidian, choisir **Ouvrir un dossier comme coffre** et sélectionner le
   même dossier. Le pont peut lire et écrire quand Obsidian est fermé.

En cas de réassociation après révocation, le menu du lanceur permet d’oublier
uniquement l’identité locale après confirmation. Les notes et le dossier choisi
restent conservés ; générer ensuite un nouveau code dans ACP.

ACP peut lister, rechercher, lire, créer, modifier, archiver et renommer les notes
Markdown UTF-8 de 128 Kio au plus. Il affiche les liens entrants et un graphe
construit à partir des liens réellement trouvés. Le graphe dessiné montre un
sous-ensemble borné ; la liste des liens reste consultable. Les résultats limités
ou non résolus sont signalés.

Ces neuf actions sont déclenchées par le propriétaire dans le desktop. Aucun outil
de lecture ou d’écriture du coffre n’est exposé aux agents Hermes ni à Discussion
dans cette version.

Les notes demandées transitent par Hermes. Ses paramètres et résultats ont une
rétention bornée, avec purge lors des accès au coffre ; les sauvegardes SQLite
peuvent conserver des copies plus longtemps. Voir le
[contrat technique](../../hermes/plugins/acp-poste/contrat/README.md).

Chaque sauvegarde compare l’empreinte de la version lue. Une modification faite
dans Obsidian entre-temps provoque un conflit : le brouillon reste disponible,
la version du coffre peut être relue et comparée avant de choisir le texte à
garder. Les versions remplacées et notes archivées restent dans `.acp/archives` ;
leur fichier JSON voisin indique le chemin d’origine. Pour récupérer une archive,
copier son Markdown vers un nouveau nom de note. Ne pas supprimer le journal
`.acp/operations`, qui évite de répéter une mutation interrompue.

Le renommage ne réécrit pas automatiquement les liens des autres notes. Le pont
interprète les liens Markdown et wikiliens textuels, pas l’ensemble des extensions,
Bases, Canvas ou du cache interne d’Obsidian. L’application Obsidian reste un
logiciel distinct ; aucun plugin tiers ni clé API Obsidian n’est installé.
La [CLI officielle Obsidian](https://obsidian.md/help/cli) est une autre interface,
plus large, qui doit être activée dans Obsidian et exige son application : elle
n’est pas présentée comme connectée par ce paquet.

## Comparaison et limites

La comparaison s’appuie sur les sources publiques de Hermes Agent 0.21.5,
commit `f97608f178d1ffeca59860195ab7da295f7c8e5f`. La session personnelle à l’URL
Railway indiquée n’a pas pu être inspectée : le navigateur et l’automatisation de
fenêtre ont échoué avant accès. Les validations graphiques utilisent le vrai QML
avec un faux Hermes et des données jetables. Elles ne prouvent pas le bon
fonctionnement de la session personnelle ouverte.

Le terminal web, le dépôt de pièces jointes, la gestion des fichiers distants et la
parité complète avec l’interface web ne sont pas fournis par ce lot. Les nouveaux
contrôles s’appuient sur les contrats JSON-RPC du Hermes épinglé. Le catalogue ne
transforme pas les neuf dépôts en services déjà déployés.

## Mettre à jour une ancienne installation

Cette version étend la base du greffon avec trois tables `coffres_*` et un index,
créés à la première utilisation du coffre. Elle ne modifie pas les tables existantes
et ne change pas l’épingle amont de Hermes. Pour une instance déployée depuis `main`,
la fusion peut déclencher sa mise à jour : appliquer la pause, les sauvegardes des
volumes et l’export chiffré décrits au [§ 6.4 du manuel](../exploitation.md#64-vos-gestes-et-le-point-de-non-retour)
avant cette transition. Ces gestes sur l’instance personnelle restent ceux du propriétaire.

1. Sauvegarder les brouillons utiles hors d’ACP, puis fermer le desktop et le lanceur du coffre s’il est ouvert.
2. Exécuter le Setup 1.2.0 fourni à la livraison ; conserver l’URL Hermes habituelle.
3. Rouvrir ACP. Si la session d’identité a expiré, suivre **Se connecter**. Les
   comptes du coordinateur Hermes et des assistants de l’exécutant sont distincts ;
   leur état est indiqué dans l’accueil et la page Poste.
4. La mise à jour du desktop suffit aux améliorations de Discussion. Pour le
   coffre et les nouvelles compétences des projets, mettre aussi à jour l’image Hermes selon le
   [manuel d’exploitation](../exploitation.md), puis utiliser un profil approprié
   pour les nouveaux tours. Les tâches déjà composées ne sont pas réécrites.
5. Ouvrir **Outils**, actualiser et examiner les compétences réellement annoncées
   par le serveur. Une fiche de source seule ne confirme pas une connexion.

Le Setup local avec les ressources LimeZu licenciées reste distinct du paquet CI
avec les ressources ACP originales. Les signatures, empreintes, validations et
liens de livraison sont rapportés avec leurs résultats mesurés dans les preuves
de version ; ce document ne préjuge pas de leur réussite.
