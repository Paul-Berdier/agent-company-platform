# Architecture du client desktop natif

État du 23 septembre 2026, **0.10.0 en préparation**. Le client existe sous
`apps/desktop` et comprend les écrans métier. La fondation a été compilée,
testée et empaquetée sur Windows avant cette extension ; la validation de l'arbre
0.10.0 est suivie dans [le relevé daté](desktop-validation-2026-09-23.md).
L'implémentation d'un écran ne constitue pas à elle seule une preuve de parcours réel.

## Architecture et responsabilité

Le client utilise **C++23, Qt 6.8.3 et QML**, avec les composants Qt Quick natifs.
Il ne contient ni Electron, ni Tauri, ni WebEngine, ni WebView. Le desktop parle à
l'API métier et ne se connecte directement ni à PostgreSQL, ni à Hermes, ni aux
workers, ni au provider-gateway. Les droits, baux, budgets et décisions finales
des mutations restent côté serveur.

| Couche | Code | Responsabilité |
|---|---|---|
| Assemblage | `src/app/Application.*` | Services, singletons QML et propagation du projet sélectionné |
| Transport | `src/api/` | URL, TLS, cookies, CSRF, annulation, réponses et réessais |
| Session | `src/auth/`, `src/services/SessionPersistence.*` | Identité serveur, expiration et mémorisation facultative |
| Stockage local | `src/storage/` | Préférences non secrètes et coffre système |
| Temps réel | `src/events/` | Analyse SSE, portées, curseurs, reconnexion |
| Métier | `src/viewmodels/`, `src/models/JsonListModel.*` | Contrats, validation des réponses et état des écrans |
| Présentation | `qml/pages/`, `qml/shell/` | Formulaires, listes, navigation, confirmations et accessibilité |
| Distribution | `packaging/windows/`, `scripts/*desktop.ps1` | Construction, tests, portable et installeur Windows |

`Acp.Runtime` expose les singletons C++ ; QML ne construit pas de client réseau.
Les modules visuels sont `Acp.Design`, `Acp.Theme`, `Acp.Controls`,
`Acp.Components`, `Acp.Pages`, `Acp.Station` et `Acp.Desktop`. Les jetons
partagés viennent de `design/tokens/` via `cmake/generate_design_tokens.py`.

## Surface métier

La [matrice de parité](native-desktop-parity.md) décrit les actions et leurs limites.

- `WorkspaceViewModel` : organisations, espaces, création et sélection de projets.
- `ConversationsViewModel` : historique, création, tours, renommage, archivage et export consultable.
- `MissionsViewModel` : composition, détail, tentatives, arrêt, relance, commentaires, acceptation et Studio.
- `ArtifactsViewModel` : liste paginée, filtres, détail et téléchargement explicite.
- `PlatformViewModel` : agents/workers, fournisseurs, MCP, compétences et liaisons au projet.
- `OperationsViewModel` : approbations, alertes, budgets, automatisations et historique.

Les listes utilisent `JsonListModel`. Les configurations d'agents, métadonnées
privées de workers, secrets et cookies ne doivent pas être transmis globalement
à QML. Les textes serveur sont présentés en texte brut.

## Transport et changements de contexte

`ApiClient` normalise l'adresse de base. HTTPS est requis ; HTTP est limité au
bouclage après activation explicite. Les redirections sont refusées. Le proxy
système est une option explicite, désactivée par défaut. Un seul gestionnaire
réseau et un seul pot de cookies portent la session API et ses flux métier.

Le CSRF est injecté en C++ sur les mutations non publiques ; les appels qui le
renouvellent sont sérialisés. Les lectures peuvent être retentées ; une mutation
n'est rejouée automatiquement que si sa clé d'idempotence correspond au contrat
serveur. Les mutations MCP/skills ne portent pas artificiellement une telle clé.

Une génération de session invalide les appels et réessais anciens. Les réponses
tardives ne doivent pas rétablir de cookies après déconnexion ou changement
d'origine. Les viewmodels invalident aussi le projet et la sélection. Une reprise
transitoire de session et une perte d'identité sont des situations distinctes.

Une conversation conserve le `client_request_id` de l'envoi incertain et se
rapproche de l'historique avec cette même clé. Le polling d'un tour est séquentiel,
lié à l'écran actif et borné ; atteindre sa limite demande une actualisation
sans inventer un état terminal.

## Studio et fichiers

Le suivi des tentatives lit l'historique et les flux authentifiés de l'API.
Les curseurs de projet et de tentative restent séparés. La fin d'un flux ne
prouve pas la fin d'une mission. Le Studio consulte événements, preuves et tests ;
il ne lance ni navigateur distant, ni agent, ni moteur 3D dans la fenêtre.

`ArtifactDownload` reçoit des blocs, écrit dans `QSaveFile`, contrôle la taille
et l'empreinte annoncées, puis valide le fichier atomiquement. La limite locale
est de 512 Mio. Annulation et erreur conservent la destination précédente.
Le contenu n'est pas exécuté ni rendu comme HTML/SVG dans l'application.

Le réseau repose sur les signaux Qt. L'écriture et l'empreinte des blocs restent
sur le fil d'interface : la mémoire est bornée, mais la fluidité sur un disque
lent ou sur le fichier maximal reste à mesurer séparément.

## Session mémorisée et mise à jour

Par défaut la session ne survit pas à la fermeture. L'option explicite de
mémorisation confie le cookie, sa portée et son échéance au coffre Windows.
`QSettings` ne conserve que des préférences, dont le consentement. Le cookie
restauré ne fournit aucun droit local : `/auth/session` confirme l'identité,
les permissions et un nouveau CSRF. Un coffre indisponible refuse la mémorisation,
sans fichier en clair de remplacement. Voir [la sécurité](desktop-security.md).

`VERSION` fournit la version du produit, vérifiée avec les copies du dépôt par
`scripts/check_version.py`. `UpdateService` possède un transport GitHub séparé,
sans identifiants ACP. Sur demande, il compare les publications, affiche leurs
notes brutes et ouvre la publication officielle admissible. Il ne télécharge
ni n'installe de paquet. Voir [le processus de mise à jour](desktop-update-process.md).

## Construction, preuves et limites

Les scripts lisent `packaging/windows/toolchain.json` : Qt 6.8.3, MSVC 2022,
CMake/Ninja et exécuteur Windows CI épinglé. Release traite les avertissements
du compilateur comme des erreurs. Les tests Qt Test exercent services et modèles ;
Qt Quick Test contrôle les composants QML. Les nouveaux tests métier utilisent
des échanges HTTP sur des serveurs locaux de test, sans prouver Hermes ou Railway.

Le relevé final 0.10.0 donne **21 suites natives sur 21 en 54,82 s**. Les
**24 tests de session passent sans ignoré hors sandbox**, y compris le cycle
réel du coffre Windows.
La suite Python combinée a donné **2 896 réussis, 70 ignorés, 835 s**.
Les preuves finales appartiennent au [relevé daté](desktop-validation-2026-09-23.md).

Le parcours Qt du 23 septembre contre l'API réelle sur SQLite jetable a réussi :
cookie/CSRF, projets, conversation sans réponse fournisseur inventée, mission,
budget, automatisation en pause et export authentifié exact de 180 224 octets.
Le rapport Qt donne 3 réussis, 0 échec, 0 ignoré en 1 663 ms ; le lanceur complet
a pris 9,7 secondes. Les rapports sont sous
`.test-tmp/desktop-journey-e9c4c89486b240f49017bb16aae70c47/` dans le worktree.
Ce parcours ne remplace ni la suite complète ni la recette visuelle.

Restent l'installation sur Windows propre, la signature, le parcours sur l'URL
Railway réelle non fournie et les **26 constats ouverts du Lot H** dans
[le suivi de revue](lot-h-091-review-status.md). Une CI antérieure verte ne valide
pas automatiquement le nouvel arbre. Le bureau pixel reste conservé hors périmètre.
