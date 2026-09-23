# Surface métier du desktop natif

État du 23 septembre 2026, **0.10.0 en préparation**. La matrice décrit les écrans
et appels implémentés dans `apps/desktop`, sans promettre une équivalence
exhaustive au web/CLI. Les preuves locales et l'état de leur intégration figurent
dans [le relevé daté](desktop-validation-2026-09-23.md).

| Domaine | Implémenté en natif | Limite ou dépendance |
|---|---|---|
| Connexion et diagnostic | Adresse configurable, session, `/meta`, `/ready` | Premier propriétaire à amorcer par API/web/CLI ; URL Railway inconnue |
| Organisations et projets | Consultation, création d'organisation/espace/projet, sélection | Création selon le rôle et l'appartenance à l'espace ; aucune administration exhaustive des membres |
| Conversations | Liste/création, historique, tours, clé stable, polling, renommage, archivage, export lisible | Hermes doit être configuré ; export affiché en texte |
| Missions | Création, liste/détail, commentaires, arrêt, relance et acceptation | La demande n'atteste pas l'exécution d'un worker |
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
| Automatisations | Liste/détail, création, activation/désactivation et historique | Les opérations avancées du web/CLI ne sont pas toutes reprises |
| Réglages/session | Préférences et mémorisation facultative dans le coffre Windows | Coffre réel éprouvé hors sandbox ; installation sur Windows propre encore à vérifier ; aucun repli en clair |
| Mises à jour | Vérification GitHub, stable/préversions, comparaison, notes brutes, ouverture officielle | Pas de téléchargeur/installateur intégré ; signature absente |

## Règles communes

Les données ACP passent par les routes de l'API métier. Les refus sont visibles
en français. Un écran vide, un fournisseur inconnu ou un worker de simulation
ne devient pas un succès supposé. Les secrets restent hors des propriétés QML
et les textes serveur s'affichent en texte brut. Les changements de projet,
session et origine invalident l'ancien contexte.

La liaison utilise les outils réellement découverts. L'API rattache une nouvelle
extension à sa version courante ; l'interface ne prétend pas choisir librement
une version ancienne. Modifier les outils d'un rattachement MCP ne migre pas
sa version épinglée.

## Preuves et reste à faire

Le relevé natif final donne **21 suites sur 21 en 54,82 secondes**. Les tests
transport utilisent des serveurs HTTP locaux. Les **24 tests de session passent
sans ignoré hors sandbox**, y compris le vrai coffre Windows ; sous sandbox,
ce cas était ignoré lorsque `CredWrite` refusait la session d'exécution.
La suite Python combinée a donné **2 896 réussis, 70 ignorés en 835 secondes**.
Cela ne prouve pas un fournisseur réel ou Railway.

Le parcours Qt/API réelle sur SQLite jetable du 23 septembre a réussi :
connexion, projets, conversation avec fournisseur indisponible, mission,
budget, automatisation, export authentifié exact du livrable et déconnexion.
Le dernier rapport indique **3 réussis, 0 échec, 0 ignoré en 1 663 ms**,
avec un lanceur complet de 9,7 secondes. Il ne
remplace pas la recette visuelle des pages. La branche desktop n'est pas encore
fusionnée dans `main` au moment de ce relevé.

Restent Windows propre, signature, services réels, écarts de parité ci-dessus
et **26 constats ouverts du Lot H** dans [le suivi](lot-h-091-review-status.md).
Le bureau pixel historique reste conservé hors périmètre. Cette version en
préparation n'est ni une V1 complète ni une publication déjà finalisée.
