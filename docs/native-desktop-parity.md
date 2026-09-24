# Surface métier du desktop natif

État du 23 septembre 2026, **0.10.0 en préparation**. La matrice décrit les écrans
et appels implémentés dans `apps/desktop`, sans promettre une équivalence
exhaustive au web/CLI. Les preuves locales et l'état de leur intégration figurent
dans [le relevé daté](desktop-validation-2026-09-23.md).

Le [bilan fonctionnel complémentaire](functional-completion-2026-09-23.md)
remplace les constats AF01/AF07/AF08 de l'audit initial : les missions portent
leur workspace, le contexte général reste accessible et les commentaires se
rechargent. Les exécuteurs utilisent les compétences approuvées et le proxy MCP
HTTP contrôlé ; un serveur MCP tiers réel reste à valider. La
[direction artistique](design-reference-study.md) organise désormais l'accueil
autour des conversations libres et des projets.

Complément du 24 septembre 2026 : l'écran « Quotas » affiche les quotas réels
d'abonnement (Codex par compte ChatGPT, Claude Code) relevés par les workers, au seul
propriétaire de la plateforme. Détail et contrat dans
[les quotas d'abonnement](subscription-quotas.md).

| Domaine | Implémenté en natif | Limite ou dépendance |
|---|---|---|
| Cadre de travail | Accueil chat/projet, barre latérale contextuelle, palette, raccourcis, précédent/suivant, inspecteur de sélection, volets adaptatifs | Historique de 32 écrans en mémoire ; pas d'onglets indépendants ni de terminal intégré |
| Connexion et diagnostic | Adresse configurable, session, `/meta`, `/ready` | Premier propriétaire à amorcer par API/web/CLI ; déploiement de test à installer |
| Organisations et projets | Consultation, création d'organisation/espace/projet, sélection | Création selon le rôle et l'appartenance à l'espace ; aucune administration exhaustive des membres |
| Conversations | Chat général ou de projet sans titre préalable, historique et recherche des titres chargés, brouillons en mémoire par fil, Entrée/Maj+Entrée, code copiable, renommage, archivage, export, arrêt et envoi incertain | Hermes doit être configuré ; polling, pas de streaming token par token ; pas de fichiers/voix ni édition/régénération des messages |
| Missions | Création, liste/détail, commentaires, arrêt, relance, acceptation et équipe Codex/Claude explicite | Workspace requis pour le code ; deux étapes parallèles maximum, branches à intégrer explicitement ; la demande n'atteste pas l'exécution réelle du fournisseur |
| Tentatives et Studio | Tentatives, événements, preuves, rapports/cas de test, suivi du flux | Lecture des preuves reçues ; aucun navigateur distant intégré |
| Livrables | Pagination, filtres, détail, destination, téléchargement annulable et vérifié | 512 Mio maximum ; aucun rendu HTML/SVG/GLB/vidéo intégré |
| Agents | Inventaire, état, rôle, module et capacités | Aucun appel direct ni édition arbitraire de configuration |
| Workers | État, capacités, charge et dernier contact | Réservé aux owner/operator ; pas d'enrôlement depuis cet écran |
| Fournisseurs | Diagnostic Hermes et capacités Codex/Claude déclarées par les workers | Capacité annoncée ne signifie pas fournisseur sain |
| MCP | Liste/détail, versions, outils, liaison, modification des outils, activation de liaison et retrait | Version épinglée conservée ; rôle membre du projet ou de son espace requis ; création/import et sondes via API/web/CLI |
| Compétences | Liste/détail, versions, liaison de la version courante et retrait | Même contrôle des appartenances ; import, fichiers, approbation et rollback hors de cet écran |
| Administration d'extensions | Activation/désactivation globale avec confirmation | Propriétaire uniquement ; prérequis vérifiés par l'API |
| Approbations et alertes | Consultation, décision commentée et acquittement | Droits requis ; aucun canal externe ajouté |
| Budgets | Politique/consommation et limites du formulaire | Surface ciblée, sans éditeur libre de politique JSON |
| Quotas d'abonnement | Écran « Quotas » : reste réel par fenêtre (5 h, semaine) relevé par l'app-server Codex et la ligne d'état Claude Code, jauges, heure locale de remise à zéro et compte à rebours, fraîcheur, « Périmé », crédits, « Limite atteinte », mention d'usage personnel ; actualisation manuelle et toutes les 60 s pendant l'affichage | Propriétaire uniquement : autre rôle sans requête, 403 affiché « Réservé au propriétaire de la plateforme » ; lecture seule, aucune estimation (« Inconnu ») ; réponse hors contrat refusée en entier ; relevés d'un worker opt-in, sans temps réel ; chemin « compte connecté » non éprouvé avec un vrai compte |
| Automatisations | Liste/détail, création, activation/désactivation et historique | Les opérations avancées du web/CLI ne sont pas toutes reprises |
| Réglages/session | Préférences et mémorisation facultative dans le coffre Windows | Coffre réel éprouvé hors sandbox ; installation sur Windows propre encore à vérifier ; aucun repli en clair |
| Mises à jour | Vérification GitHub, stable/préversions, comparaison, notes brutes, ouverture officielle | Pas de téléchargeur/installateur intégré ; signature absente |

## Règles communes

Les données ACP passent par les routes de l'API métier. Les refus sont visibles
en français. Un écran vide, un fournisseur inconnu ou un worker de simulation
ne devient pas un succès supposé. Les secrets restent hors des propriétés QML
et l'affichage en texte brut est la règle ; sa couverture complète reste à vérifier.
Les changements de projet,
session et origine invalident l'ancien contexte.

La liaison utilise les outils réellement découverts. L'API rattache une nouvelle
extension à sa version courante ; l'interface ne prétend pas choisir librement
une version ancienne. Modifier les outils d'un rattachement MCP ne migre pas
sa version épinglée.

## Preuves et reste à faire

Les validations de la base fonctionnelle comptent **22 suites Qt** et un
parcours Qt/API réelle **3 réussis, 0 ignoré en 2 002 ms**. Les 24 cas de session
ont également éprouvé le coffre Windows hors sandbox. Les CI du commit
fonctionnel `47de619` donnent 3 031 tests SQLite réussis (64 ignorés) et
3 041 PostgreSQL réussis (54 ignorés). Les nombres détaillés et les limites
figurent dans le [bilan daté](functional-completion-2026-09-23.md).

L'écran « Quotas » ajoute deux suites Qt (`tst_subscription_quotas`,
`tst_quotas_ui`) et un test Qt Quick (`tst_quota_gauge.qml`) ; le relevé local du
24 septembre 2026 en Debug donne **25 suites sur 25**. La page a été rendue contre un
serveur local qui sert la fixture de référence, jamais contre un compte réel.

La refonte conversations/projets ajoute une suite de véritables interactions
QML : création sans titre, saisie, copie de code, brouillons, recherche et
défilement. Son relevé distinct est dans
[la recette de l'interface](desktop-chat-projects-2026-09-23.md). Une capture
utilise des données de test identifiées ; elle ne prouve pas une réponse de
modèle réel. L'API réelle de recette utilise une base SQLite jetable.

Restent Windows propre, signature, services réels, écarts de parité ci-dessus
et **26 constats ouverts du Lot H** dans [le suivi](lot-h-091-review-status.md).
Le bureau pixel historique reste conservé hors périmètre. Cette version en
préparation n'est ni une V1 complète ni une publication déjà finalisée.
