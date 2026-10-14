# ACP 2.0 — correction de l'exécution distante

Mission du propriétaire du 14 octobre 2026. Base relue : main
`e99b4968758458c73591f9f1cd7c8c6535795486`. Branche : `codex/remote-workspace`.
Version de travail : **2.0.0**, non publiée et non déployée.
La [PR 34](https://github.com/Paul-Berdier/agent-company-platform/pull/34) est
ouverte en brouillon sur `codex/remote-workspace`. Le bilan fonctionnel ci-dessous
porte sur `f3bb19df1fd5c94c7f2cc88ec21e9144fc90a2f4` ; le chantier continue.
Le retrait de l'exécution Windows constitue une rupture du contrat produit ;
les données et les identités anciennes restent conservées.

## Audit initial

| Exigence | Code concerné | État observé sur la base | Correction | Preuve attendue |
|---|---|---|---|---|
| Le PC est uniquement client | `noyau/execution.py:servir`, `noyau/routage.py`, `PostePage.qml` | Le même protocole accepte Windows et Linux ; l'UI présente les deux | Refus serveur avant attribution, infrastructure dans Paramètres | Un ancien poste Windows annonçant « prêt » ne reçoit aucune carte ; Linux reste soumis à ses gardes |
| Connexion réelle depuis le desktop | `PosteViewModel::ouvrirGuide`, `app_server.py` | Guides seuls ; méthodes login interdites ; notifications abandonnées | Opération distante explicite, compte officiel conservé sur le serveur, page Comptes | Clic → opération durable → app-server officiel → défi → vérification ; aucun secret dans les journaux |
| Mission indépendante du client | `service_executant.py`, `execution.py`, `flux.py` | La boucle Linux existe ; le flux UI invalide des vues, sans journal détaillé rejouable | Conserver IDs natifs et événements publics, curseur durable, réconciliation | Déconnexion de deux clients puis lecture du même résultat sans nouveau lancement |
| Résultat sans terminal local | `PosteViewModel::ouvrirGuideRecuperation` | SSH, bundle, SCP et Git sur PC demandés | Livraison authentifiée depuis le serveur à construire | Téléchargement du résultat et vérification de son empreinte sans CLI sur PC |
| Workspace lisible | `NavigationModel`, `SideNavigation`, `ProjectsPage` | Les comptes et l'infrastructure se mélangent ; trop de destinations principales | Projets, Activité, À valider, Comptes et modèles, Paramètres | Rendu Qt réel en 1366×768 et grand écran, gestes souris et clavier |
| Preuve de production | Workflows et relevés Railway | Les tests passés utilisent des doubles de comptes/CLI ; serveur épinglé en 1.0.1 | Séparer contrat simulé, binaire officiel sans compte et vraie inférence autorisée | Chaque preuve indique environnement, révision, compte réel ou double, résultat et limites |

Chaîne actuellement implémentée : bouton Nouveau projet →
`ProjetsViewModel::lancer` → `ClientGreffonPoste::lancerProjet` →
`POST /api/plugins/acp-poste/v1/projets` (clé idempotente) →
noyau projets de Hermes → carte kanban → réclamation HTTPS par le service
Linux → CLI officielle → issue envoyée à Hermes → invalidation et relecture
du détail dans Qt. Le navigateur utilise la même façade métier.
La présence de cette chaîne ne prouve pas son exécution avec un compte réel.

## Décisions qui remplacent les anciennes

- **R1 — PC client seulement.** Remplace le poste Windows facultatif de D74 et
  les parcours Windows D51/D55/D66. Leur code et leurs données restent lisibles
  pour migration ; ils ne constituent plus une voie d'exécution du produit.
  Aucun repli local, même si le serveur est indisponible.
- **R2 — Hermes garde l'état métier.** Aucun second orchestrateur ACP. Le moteur
  possède sa session native ; l'adaptateur conserve sa correspondance avec les
  projets, cartes et tentatives de Hermes.
- **R3 — Connexions officielles distantes.** Remplace le dépôt manuel obligatoire
  des identifiants prévu par D92 et les guides locaux. Ce remplacement n'autorise
  ni collecte des mots de passe, ni import des cookies, ni proxy d'abonnement.
  Le moteur officiel possède son magasin et ses renouvellements sur le serveur.
- **R4 — Résultats depuis le serveur.** L'interdiction absolue de publication de
  D82 devient publication uniquement après autorisation explicite, scoped au
  dépôt et à l'opération. Cette cible n'annonce pas un bouton de publication déjà
  implémenté ; les protections actuelles restent jusqu'à sa validation.
- **R5 — Événements durables.** Le flux d'invalidation existant reste utile, mais
  ne remplace pas les événements de session avec identifiants et curseur.
  Une reconnexion relit le serveur et ne relance jamais implicitement une mission.
- **R6 — Isolement conservé.** UID séparés, limites, dépôts permis, secrets minimaux
  et refus des capacités non prouvées restent obligatoires. Un worktree n'est pas
  une sandbox ; aucun socket Docker hôte n'est monté dans un agent.
- **R7 — Comptes séparés clairement.** Accès ACP, comptes des moteurs et fournisseur
  du coordinateur sont distincts. Binaire présent, compte connecté, modèle
  découvert et inférence validée sont des observations différentes.
- **R8 — Données préservées.** Projets, journaux, identités et coffre ACP ne sont
  ni supprimés ni réinitialisés. Le pont local des notes reste facultatif et
  indépendant des missions distantes.
- **R9 — Production et dépenses.** Les règles d'autorisation Railway, de sauvegarde
  avant migration et d'accord pour une nouvelle ressource payante restent en
  vigueur. Ni une CI verte ni un README ne prouvent un déploiement.

## Choix de réutilisation

La comparaison est consignée dans [remote-engines.md](remote-engines.md).
T3 reste une piste vérifiée, pas une dépendance implicitement acquise.
Le premier incrément prolonge les adaptateurs ACP et le binaire officiel épinglé
pour ne pas ajouter un second stockage de projets et une API privée non publiée.

## Environnement et outils

- Git/GitHub : lecture réelle du commit main, de l'historique et des workflows ;
  connecteur GitHub et CLI `gh`. Les commits restent sur une branche dédiée.
- Railway : connecteur en lecture seule du projet personnel ACP
  `0225ef3a-cafc-43a2-9804-ad7d9ce4827c`. Au relevé de cette mission, seul
  `production` est visible ; le service executant est encore épinglé sur
  `85b458b` (ACP 1.0.1), sans changement préparé. L'URL donnée comme environnement
  de test pointe sur ce même projet : aucune séparation de test n'est attestée.
- Documentation OpenAI officielle : contrat Codex app-server et authentification,
  comparés au binaire 0.156.1 épinglé. Aucun accès fournisseur déduit d'un catalogue.
- Qt : 6.8.3 / MSVC 2022, Qt Test et Qt Quick Test disponibles ; captures natives.
  Skills Qt lues à `a784c48445e34f126760f17ba0600a25f2d19968`,
  licence BSD-3-Clause pour les skills sélectionnées : qt-qml, qt-ui-design,
  qt-qml-review et qt-qml-test. Pas de script tiers installé.
  Le preview MCP récent exige Qt 6.12 : non retenu, Qt n'est pas monté.
- Figma est un outil de design facultatif ; aucune preuve de rendu Qt ne sera
  remplacée par une maquette.
- Les outils du développeur ne sont ni des dépendances livrées avec ACP ni des
  accès automatiquement offerts aux agents du produit.

## Validation et état de livraison

Ce document décrit le chantier en cours, pas une refonte terminée.
Les preuves distinguent le code avec données simulées, le binaire officiel,
l’authentification personnelle, l’inférence réelle, les captures, la migration
et le déploiement.
Les essais de CLI et de services de projet se font sur Linux distant jetable,
jamais en lançant un agent de projet sur le PC utilisateur.

## Budget nul et prochain parcours distant

Le propriétaire a confirmé le 14 octobre **un budget supplémentaire nul** et
ne possède aucun VPS : seul son Railway existant est disponible. Aucun achat,
nouvel environnement payant ou remplacement par une API facturée n'est prévu.
Les configurations VPS étudiées restent une piste différée, pas la prochaine
étape imposée pour utiliser ACP. Le propriétaire confirme aussi disposer d’un
abonnement Claude Pro ou Max ; ses droits, modèles, quotas et sa connexion
depuis ce serveur n’ont pas encore été vérifiés.

Le connecteur Railway confirme l'accès au projet personnel, pas l'existence
d'une préproduction. La documentation officielle
[des environnements](https://docs.railway.com/environments#create-an-environment)
indique qu'une duplication copie aussi les variables et la configuration.
Aucune duplication n'est autorisée par ces notes. Les essais de développement
continuent sur des données jetables ; la production personnelle ne devient pas
un banc de test pour éviter le coût d'une infrastructure supplémentaire.

La lecture ciblée des journaux du service executant le 14 octobre confirme
la preuve déjà consignée dans [init-plateforme.md](init-plateforme.md) : le
10 octobre à 06:41:13 et 07:42:26 UTC, la sonde a mesuré **régime B,
bubblewrap refusé, UID séparés**. Source : projet ACP, service
`49473bee-5140-4e98-8fb8-7e5cdf99402e`, dernier déploiement
`33a6951f-f577-48fc-a59c-f07caf58d316`. Lecture seulement, aucun redémarrage.
Codex reste fermé en écriture sur cet environnement. Un nouvel environnement
Railway ne constitue pas à lui seul une solution au blocage observé.

Le relevé complémentaire du 14 octobre retrouve `hermes`, `executant` et
`identite` en `SUCCESS`. Le quatrième service `agent-company-platform`
(`404d5cbb-41c6-40ea-9fb5-fb7d6a0723d8`), absent de `.railway/railway.ts`,
échoue au build sur `e99b496` : Railpack ne trouve aucune commande de démarrage
à la racine. Aucun processus applicatif n'a démarré sur ce service, sans volume.
Ce diagnostic n'a modifié aucune configuration. Les sources visent `main` ;
les [déclencheurs GitHub Railway](https://docs.railway.com/deployments/github-autodeploys)
peuvent déployer cette branche si elle est suivie. Le contrat du connecteur
`connect_service_source` précise que `commitSha` épingle une révision et arrête
le suivi de branche jusqu'à reconnexion sans SHA. Les trois services applicatifs
portent l'épingle `85b458b` dans le relevé ; le service générique n'en porte pas.
La CLI Railway 5.64.2 déjà installée donne accès à l'API publique sans extraire
de jeton : `serviceInstanceAutoDeployStatus` confirme `enabled=false` pour
Hermes, l'exécutant et l'identité, et `true` pour le service générique.
Relire la configuration avant fusion et préparer les sauvegardes avant de
changer la révision des services applicatifs.

La sonde A reste nécessaire pour ouvrir Codex en écriture avec la politique
actuelle. Cette exigence ne ferme pas toute la voie Claude : les gardes
existantes prévoient Claude Code en régime B, sous ses propres conditions,
restrictions et contrôles. Ne pas retirer une garde, désactiver globalement
AppArmor/seccomp ou monter un socket Docker dans les agents pour forcer Codex.

Le **parcours officiel Claude Code** est maintenant implémenté dans la branche,
avec validation finale en cours : API `acp-comptes/2`, contrôleur distant commun
aux deux moteurs et formulaire Qt. Le CLI officiel gère son magasin et son
rafraîchissement ; sondes et missions n'injectent plus le setup-token historique.
Ce dernier reste conservé, sans être utilisé comme remplacement du compte.
Le compte est relu avant chaque mission. Les champs `accessToken` et
`refreshToken` du magasin sont lus seulement en mémoire pour le masquage, puis
relus avant chaque publication, en conservant les anciennes valeurs déjà vues.
Aucun moteur n'est lancé sur le PC utilisateur.

Le retour de navigateur est un code temporaire pour le CLI : ce n'est ni un
mot de passe ni un jeton d'abonnement. URL et code restent en mémoire, liés au
serveur, à son instance, à l'opération et au défi. SQLite conserve seulement
les identifiants et le reçu. Un accusé signifie « écrit sur stdin », jamais
« connexion réussie ». Après perte de mémoire du serveur, le reçu `perdu`
n'autorise pas une nouvelle remise automatique : attendre la vérification ou
annuler et recommencer. Une reconnexion interrompue garde son résultat distinct
d'un ancien compte encore connecté. Un arrêt de processus non confirmé suspend
les comptes et les missions avant de rendre les verrous.

Le [témoin du vrai binaire 2.1.283, révision `5b98432`](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38588066690)
a réussi : **51 tests image**, puis **1 008 tests root et 24 ignorés Windows**.
Il confirme `auth login --claudeai`, l'URL
`https://claude.com/cai/oauth/authorize`, l'invite de retour sur pipes et PTY,
l'interruption et l'absence de descendants. Le témoin des outils impose les
permissions du produit : 18 appels réellement reçus, dont 14 refus, sans fuite
des canaris. Le fournisseur est local et factice, aucun compte personnel ni
appel d'inférence Anthropic n'est impliqué. Ces tests ne prouvent pas encore le
succès OAuth, le renouvellement ni les droits réels du compte déclaré.
La [référence officielle](https://code.claude.com/docs/en/cli-reference) précise
les états `authMethod` et le champ `configDirectory` lus par l'adaptateur.

Le client de ce lot compile avec Qt 6.8.3 : **43/43 suites natives** passent
en 171,12 secondes, dont saisie masquée, focus conservé pendant les sondages,
effacement immédiat et reprise après interruption. Les huit captures de la
page Comptes, quatre thèmes sur deux tailles, portent la mention de simulation.
Le champ et les trois boutons sont vérifiés entièrement visibles avant clic.
L'interface web passe **206 tests**, types et bundles déterministes compris.
Ces contrôles utilisent des transports factices et ne prouvent pas le compte
personnel ni la fenêtre ACP déjà installée.
La suite Python finale locale passe **1 620 tests et 464 sous-tests**, avec
**115 tests ignorés**, en 1 295,11 secondes. Les images Linux ne sont pas lancées
sur le PC ; leurs cas sont réservés à la CI. Le dernier message de conflit,
retirant l’instruction de récupération locale git bundle, est revalidé séparément
par le test d’intégration existant (1 réussi, 131,88 secondes).
Les nouvelles images et la migration depuis `85b458b` restent à valider en CI.

Le plus petit parcours utile à viser, après ces corrections, est :

1. Vérifier séparément l'accès ACP, le fournisseur de coordination Hermes et
   le compte Claude Code associé à l’abonnement déclaré, avec leur mode de
   facturation réel.
   Aucun basculement vers une API ou un dépassement payant ; l'existence d'un
   abonnement ne prouve pas les modèles accessibles ni une capacité restante.
2. Depuis Qt, accomplir le parcours Anthropic officiel exécuté sur le serveur,
   puis relever son état et les capacités admises. Le moteur officiel possède
   ses identifiants ; ACP ne collecte ni mot de passe ni jeton de navigateur.
3. Donner à Hermes une petite mission d'analyse en lecture seule sur un dépôt
   jetable explicitement autorisé, avec durée et nombre de tours bornés.
   La synthèse textuelle et le journal constituent le résultat de cet incrément.
4. Fermer le desktop pendant la tâche, lire le même projet depuis le web, puis
   rouvrir Qt et retrouver le même résultat et les mêmes identifiants, sans
   relance. Conserver les preuves du moteur et du modèle réellement observés.

Ce parcours personnel reste dans le périmètre autorisé, après préparation
et revue des sauvegardes et du déploiement compatible.
Il n'a pas eu lieu. Le budget nul n'est pas une preuve d'absence de coût :
l'essai doit rester dans les ressources et droits déjà autorisés, sinon il
s'arrête explicitement. Une mission de modification de code exige en plus la
livraison des fichiers/diffs/artefacts dans ACP, encore indisponible ; les seules
références de branche ne satisfont pas ce critère de la mission complète.

Pour le futur déploiement, l'ordre sera Hermes, puis l'exécutant, puis le desktop,
sur des révisions compatibles et après sauvegarde. Le client 2.0 indique
explicitement quand l'API des comptes manque sur un serveur ancien. Le nouveau
journal ajoute une table de reçus et les comptes ajoutent deux tables de
métadonnées dans la base ACP existante ; aucune base métier parallèle.

Le retour arrière exige d'arrêter les nouvelles missions et de conserver les
files non acquittées. Un serveur 1.x ne comprend pas les événements du protocole
2.0 : ne pas rétrograder Hermes seul pendant qu'un exécutant 2.0 travaille.
Aucun test de migration sur les volumes personnels n'a été effectué.

## Résultats consultables et limite de livraison

Les références des branches intégrées (projet, dépôt, branche, commit, date)
restent consultables. Le serveur expose un état de livraison `non_disponible`
et ne fabrique plus une commande Railway en supposant l’hôte du résultat.
Le desktop et le web n’exposent plus le parcours de récupération SSH/Git sur le
PC, y compris face à une ancienne réponse qui contient cette commande.
Le téléchargement authentifié, la vue diff et la résolution graphique des
conflits restent à construire ; aucun bouton ne prétend les effectuer.

## Paquet Windows

Le desktop n'installe pas les CLI des moteurs. Le paquet de notes facultatif
possède désormais son propre point d'entrée `acp_poste.coffre_cli` et une liste
fermée de modules : les fichiers `execution`, `service_executant`,
`app_server`, `comptes_codex`, `local_runner` et la CLI du worker sont absents.
Son runtime Python sert seulement à cette copie locale facultative des notes.

Preuve locale : `apps/desktop/build/verification/coffre-remote-only-2.0.0-r2/manifest-coffre.json`.
Le runtime isolé 3.12.10 a exécuté créer/lire/écrire/archiver/graphe sur un dossier
temporaire et le menu PowerShell 5.1 a transmis `creer --help`, sans création
personnelle ni connexion réseau. Le premier essai a révélé un double BOM
PowerShell ; corrigé puis paquet reconstruit et vérifié. Aucun Setup 2.0 n'a
été installé et aucun fichier du coffre personnel n'a été modifié.


**Déclaration d’un VPS Linux.** La politique Linux protégée accepte maintenant
`[deploiement]`, `cible = "vps"`, `distant_confirme = true`. Le producteur publie
alors `hote = "vps"` et `execution_distante_declaree = true` ; le serveur exige
ces deux valeurs sur Linux. Sans cette déclaration, un Linux hors Railway reste
`pc` et reçoit le refus d’exécution locale. Le contrat refuse cette déclaration
pour Windows. Le fragment `executant/deploiement/vps.fragment.toml` montre les
champs à intégrer à une politique complète ; ce n’est pas un installateur.

Cette déclaration provient de l’opérateur et de la machine enrôlée ; ce n’est
ni une attestation matérielle, ni une preuve d’isolation. Les gardes de sonde,
compte, modèle, quota et dépôt restent actives : un VPS en régime B ne peut pas
faire écrire Codex. L’image exige toujours Linux x86_64, son démarrage root sous
le `tini` fourni, ses UID séparés et un vrai montage `/donnees`. Le mode rootless,
ARM64, le provisionnement et la configuration d’isolation d’un VPS personnel ne
sont pas validés. Les anciennes notifications de présence peuvent encore nommer
cet exécutant « poste » ; elles n’activent aucune exécution sur le client. Les
pistes d’exploitation et leurs limites sont dans [vps-declaration.md](vps-declaration.md).

## Parcours de connexion du premier incrément

Dans le client connecté à ACP, ouvrir **Comptes et modèles**, puis
**Connecter Codex**. L’exécutant démarre le parcours officiel `chatgptDeviceCode`
de Codex 0.156.1 ; le navigateur ouvre uniquement la page officielle et
l’interface suit automatiquement la confirmation. Le compte est conservé dans
le magasin officiel sur le serveur. Fermer cette page ou le client n’annule pas
la connexion ; le bouton Annuler le fait explicitement. Aucune installation
locale de Codex et aucun collage de secret dans ACP ne sont nécessaires.

Ce parcours exige le nouveau serveur et un exécutant compatible, actif et
enrôlé. Il n’est pas disponible sur la production 1.0.1 actuelle. Le premier
incrément n’automatise pas encore l’installation et l’enrôlement de
l’infrastructure. Après connexion, un relevé distinct vérifie version, modèles
et quotas ; le statut du compte ne prouve jamais une inférence réussie.

Les codes temporaires restent dans la mémoire du processus HTTP Hermes, pas
dans SQLite. Cette version suppose le processus HTTP unique du déploiement
actuel. Un déploiement à plusieurs workers exigerait un mécanisme de remise
des défis adapté ; il n’est pas validé. Les opérations et leur réconciliation
sont persistantes, mais un code en attente peut disparaître momentanément lors du redémarrage
de Hermes ; la répétition du même relevé peut le restituer sans nouveau login. La réconciliation ne démarre aucun second login. Si le code ne revient pas,
le propriétaire peut annuler cette opération puis en demander une nouvelle.

## Preuves locales du premier incrément

- Suite Python sous Windows/Python 3.12.10 après ajout VPS : **1 523 tests réussis,
  109 ignorés, 464 sous-tests réussis**, 1 065,82 s. Les tests ignorés requièrent notamment
  Linux/root et les images jetables ; ils ne sont pas présentés comme réussis.
  Rapport : `apps/desktop/build/verification/remote-workspace-python-final.xml` et
  journal de même nom en `.log`. Deux avertissements Starlette/httpx existants.
  La correction finale de projection des comptes, apportée pendant cette suite,
  est revalidée séparément dans les 309 tests ciblés ci-dessous ; la campagne
  finale Linux décrite plus bas a vérifié ensemble tous les correctifs.
- Contrôles ciblés après relecture : comptes/contrat 312 tests réussis ; journal,
  file et contrat 279 tests réussis ; derniers contrôles défi/fixtures 15 tests
  réussis. Doubles de CLI et de réseau, vraie SQLite
  temporaire et vraie file atomique. Aucun compte personnel dans ces tests.
- Qt 6.8.3/MSVC 2022 : compilation et 43/43 suites natives réussies (163,92 s),
  dont les clics connexion/annulation et la reprise du journal. Les derniers
  libellés et le harnais de polices passent aussi leurs huit suites ciblées
  (63,30 s). Après retrait du parcours de récupération CLI, compilation et
  **43/43 suites** de nouveau réussies (172,85 s), avec test de non-présentation
  d’une ancienne commande Railway reçue du serveur.
- Captures : `apps/desktop/build/verification/remote-workspace-captures-finales/`,
  quatre thèmes × 1366×768 et 1920×1080. Le bandeau **TEST · DONNÉES SIMULÉES**
  identifie la matrice. Relecture visuelle du contrôle de comptes, travail et
  journal ; ce sont de vraies vues Qt sur données simulées, pas la fenêtre ACP
  personnelle ni une preuve d’inférence distante. Après retrait de la récupération
  CLI, les deux captures natives `resultats-distants-captures/Resultats-simules-
  {railway,vps}-1366x768.png` dans le même dossier de vérification montrent le
  panneau complet. Le harnais final passe sa suite interactions (9,29 s).
- Dernière correction des comptes : **309 tests réussis** (comptes, contrôleur,
  contrat). Le test de projection passe par le vrai réceptionnaire d’inventaire
  et SQLite : il couvre le remplacement d’un succès historique par un nouveau
  relevé déconnecté. Ce contrôle reste simulé côté fournisseur.
- Interface web finale : **205 tests réussis**, vérification TypeScript et
  bundles régénérés. Aucun bouton de récupération par CLI sur le PC n’est proposé.
- Déclaration VPS : **374 tests ciblés réussis**, deux contrôles de permissions
  POSIX ignorés sur Windows et réservés à la CI Linux. Relecture indépendante :
  96 tests réussis, les mêmes deux contrôles POSIX ignorés.
- Contrôles versions, thèmes, catalogue, verrous Python et moteur Pixel Office
  gelé réussis. Balayage des fichiers suivis et nouveaux : aucun motif de secret.

## Campagnes finales et PR en cours

La [PR 34](https://github.com/Paul-Berdier/agent-company-platform/pull/34) reste
**en brouillon, non fusionnée**. Les campagnes finales ont réussi sur
`f3bb19df1fd5c94c7f2cc88ec21e9144fc90a2f4`. Son seul écart avec
`237f25794bfc09fc7a6f19769512acf942c43e96` concerne deux fichiers de tests :
les preuves Desktop et exécutant sur 237 portent sur le même code de production.

| Campagne | Révision | Résultat |
|---|---|---|
| [CI générale 38522643484](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38522643484) | f3bb19d | Linux : 1 575 réussis, 62 ignorés ; Windows : 1 525 réussis, 112 ignorés ; 464 sous-tests par système. Interface, moteur gelé et installation simulée PowerShell 7/5.1 réussis. |
| [Image Hermes 38522640761](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38522640761) | f3bb19d | 907 tests image ; 205 contrats, 19 désélectionnés ; 10 parcours navigateur, 1 désélectionné. Restauration : 13 contrats, 211 désélectionnés, puis 1 parcours navigateur, 10 désélectionnés. Nettoyage confirmé. |
| [Migration 38525696602](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38525696602) | e99b496 → f3bb19d | 6 tests réussis, 218 désélectionnés, aucun ignoré ; volumes jetables, références Git et identité machine conservées, reprise de l'ancienne session et nouvelle mission terminées. Nettoyage confirmé. |
| [Migration 1.0.1 38584859352](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38584859352) | 85b458b → f3bb19d | 6 tests réussis, 218 désélectionnés, aucun ignoré, en 265,47 s. Lectures égales, jeton/empreinte/références conservés, session ancienne reprise puis terminée et nouvelle mission terminée ; aucun défaut. Nettoyage confirmé. |
| [Desktop CI 38517196960](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38517196960) | 237f257 | MSVC/Qt 6.8.3 : 43/43 suites en 143,20 s, empaquetage réussi. |
| [Image exécutant 38517199214](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38517199214) | 237f257 | 46 tests image, dont schéma officiel Codex 0.156.1 ; 1 008 tests root, 24 ignorés propres à Windows. Nettoyage confirmé. |

Deux témoins couvrent désormais ACP 1.2.0 (`e99b496`) et ACP 1.0.1
(`85b458bbffbfb6dffe1fc40b8c3885f11b779ac7`, révision relevée sur Railway)
vers `f3bb19df1fd5c94c7f2cc88ec21e9144fc90a2f4`. Ils utilisent des volumes
jetables peuplés par les anciennes images et des comptes/moteurs simulés.
Le [rapport du témoin 1.0.1](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38584859352/artifacts/11904767982)
contient `resume.md` et `resultat.json` (conservation trente jours) ; il confirme
le passage du greffon 1.0.1 à 2.0.0 et la reprise de la session avant création
d'une nouvelle mission, sans perte détectée dans les lectures comparées.
La version de Hermes et le schéma SQLite 4 sont inchangés : ces essais ne
prouvent pas une transformation de schéma. Ils ne valident ni les volumes
personnels Railway, ni une migration Authelia, ni un retour arrière.
Le témoin optionnel de montée de version amont Hermes n'a pas été exécuté.

Les tests image exécutent le binaire officiel sans compte personnel. La sonde
A de CI utilise un témoin aux protections desserrées ; elle ne valide pas une
configuration de production. Les parcours métier et les captures Qt restent
simulés côté fournisseur. Aucun compte personnel ni inférence réelle n'a été
validé. Les [paquets Desktop de test](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38517196960/artifacts/11872443335)
sont non signés, non installés et conservés sept jours ; aucune release ni
mise à jour des services personnels n'a été publiée par ces campagnes.

## Première campagne GitHub Actions

Révision `ef0cae2dba98da9a3a539c00822ea63e28cb299b`, campagnes lancées sans
publication ni déploiement :

- [Desktop CI](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38512588495)
  réussie : compilation MSVC/Qt 6.8.3, **43/43 suites** en 141,85 s et empaquetage
  à blanc. Paquets 2.0.0 non signés, non installés ; aucune release créée.
- [CI](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38512584643) :
  moteur et Windows réussis. Deux tests Linux de boucle étaient bloqués par un
  faux serveur sans reçu d’événements ; la vraie file attendait correctement
  l’acquittement avant l’issue. Le double applique désormais le nouveau contrat.
  L’interface exigeait aussi la régénération des dix bundles dont le bandeau de
  version restait 1.2.0 ; reconstruction puis **204 tests locaux réussis**.
- [Exécutant Linux](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38512595803) :
  45 tests image réussis, puis échec du nouveau test de schéma. Le binaire officiel
  0.156.1 déclare `loginId` facultatif dans la notification générique de fin de
  connexion. L’assertion est corrigée ; le contrôleur continue d’exiger la
  corrélation de l’identifiant pour ce parcours. La suite root n’a pas été
  exécutée sur cette campagne, elle reste à prouver.
- [Image Hermes](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38512592110) :
  première étape image, 903 tests réussis et trois échecs : ancien bandeau 1.2.0,
  métadonnée Windows attendue pour un exécutant Linux simulé, et carte créée avec
  un modèle absent de son nouvel inventaire. Les fixtures sont corrigées sans
  assouplir les gardes. Les contrats et le navigateur principaux ont été ignorés
  après cet échec. Le job parallèle restauration a réussi : **13 tests**
  de contrat (211 exclus) puis **1 test navigateur** (10 exclus), nettoyage réussi.

Les campagnes suivantes, sur les corrections et la déclaration VPS, sont suivies
dans la PR avec leur révision exacte. Aucune de ces preuves ne valide un
déploiement personnel, une connexion à un
compte fournisseur réel ou une inférence facturée.
