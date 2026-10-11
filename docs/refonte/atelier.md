# Chantier « atelier » : espace de travail, Pixel Atelier, agents et routage

État du 11 octobre 2026. Branche `claude/wonderful-brahmagupta-rlbkuj`, partie de `main` (`85b458b`, ACP 1.0.1).
Décisions du chantier : D165 à D169, dans le [plan](plan.md) § 1, sous-section « Chantier « atelier » ». Ce document
tient l'état réel, les points d'audit, la matrice des écarts, le vocabulaire et le plan des lots. La section 7 dit où
en est le travail.

**Convention de preuve.** Sauf mention contraire, chaque `chemin:ligne` se lit sur le commit `85b458b`
(`git show 85b458b:<chemin>`), point de départ du chantier. L'arbre de travail change pendant le chantier : ses
numéros de ligne ne font pas foi ici. Chaque référence a été relue dans le fichier le 11 octobre 2026. « Section n »
renvoie à ce document ; « § n du brief » renvoie au brief.

## 1. Objet et brief

Le brief est le prompt maître du propriétaire du 11 octobre 2026. En huit lignes :

- La station Qt devient un espace de travail de codage : projets, missions, agents, activité.
- Disposition : projets et missions à gauche, mission au centre avec saisie persistante, agents à droite, volet bas.
- Direction artistique **Pixel Atelier** par défaut (Nuit, Jour), **Studio** en alternative sobre (Graphite, Papier).
- Mouvement en trois profils (Complet, Discret, Réduit) et mode Concentration ; aucune fausse activité.
- Emblème, icône Windows, police pixel et assets originaux, tirés de sources texte versionnées.
- Routage « Auto » respecté par défaut ; modes Économe, Équilibré, Approfondi ; supervision sans donnée inventée.
- Les § 6 à 20 du brief couvrent aussi comptes, onboarding, événements durables, Git, outils, extensions et tests.
- Six lots, A à F : ce chantier porte A, B et le point « Auto par défaut » du lot C ; le reste attend (section 6).

Décisions : D165 (direction artistique et mouvement, décision du propriétaire), D166 (vocabulaire), D167
(agencement), D168 (Auto par défaut), D169 (version). D166 à D169 sont des choix de conception, à confirmer par le
propriétaire. Texte complet : [plan.md](plan.md) § 1.

## 2. État réel au 11 octobre 2026

### 2.1 Dépôt

| Élément | Constat | Commande ou preuve |
|---|---|---|
| Branche de travail | `claude/wonderful-brahmagupta-rlbkuj`, présente sur `origin` au même commit | `git branch --show-current` ; `git rev-parse --short origin/claude/wonderful-brahmagupta-rlbkuj` |
| Point de départ | `85b458b` : même commit pour `HEAD`, `main` et `origin/main` | `git rev-parse --short HEAD`, puis `main`, puis `origin/main` |
| Commit `85b458b` | Fusion à deux parents (`f76e7c5`, `a3d0422`) du 10 octobre 2026, 09:41 (+02:00) : « fix(runtime): release ACP 1.0.1 with Railway init support (#27) » | `git log -1 --format='%H %P %ad %s' 85b458b` |
| Commits de 1.0.1 | `990a289` (ouverture), `824cf0e`, `61f4b9f`, `25328c5`, `a3d0422`, puis la fusion | `git log --oneline f76e7c5..85b458b` |
| Version | `VERSION` vaut `1.0.1` | `cat VERSION` |
| Étiquettes | `v1.0.1` annotée (objet `d74dd90`) sur `85b458b` ; `v1.0.0` (objet `8c60b78`) sur `f76e7c5`. Aucune étiquette rapatriée dans ce clone | `git ls-remote --tags origin` ; `git tag -l` (vide) |
| Worktrees | Un seul : `/home/user/agent-company-platform`, `85b458b`, branche de travail | `git worktree list` |
| Fichiers modifiés au démarrage | Aucun. Les fichiers non suivis vus pendant la cartographie (`scripts/generer_assets_pixel.py`, puis `design/pixel/`) sont des livrables de ce chantier (lot B) | `git status --short` |
| Plan | D165 à D169 ajoutées par ce chantier au plan, § 1 | `docs/refonte/plan.md` (arbre de travail) |

### 2.2 Environnement de la session

Relevé de l'agent qui code, repris de la spécification du chantier. La présence des outils a été vérifiée ; les
suites n'ont pas été rejouées par ce document.

- Session cloud Linux, sans Windows : ni MSVC, ni Inno Setup, ni installation de test de l'icône.
- Qt 6.8.3 installé hors dépôt depuis conda-forge (`qt6-main 6.8.3 hb82b983_5`) dans `/opt/acp-outils/qt683`, par
  py-rattler 0.27.1 ; download.qt.io est bloqué par le mandataire de la session.
- GCC 13.3, CMake 3.28.3, Ninja 1.11.1 ; préréglage `linux-gcc-debug` (`apps/desktop/CMakePresets.json:75`).
- Base avant chantier, plateforme offscreen : 35 suites vertes sur 36. `tst_pages_bureau` échoue à l'étape
  « Sauvegarde, export réel (DPAPI) » : DPAPI n'existe que sous Windows, limite connue du préréglage Linux.
- La preuve qui fait foi reste la Desktop CI sur `windows-2022` (`.github/workflows/desktop-ci.yml:70`).
- Bloqués par le réseau : github.com (dont les Qt Agentic Tools), qt-docs-mcp.qt.io, doc.qt.io, download.qt.io,
  fonts.google.com, developers.openai.com ; le MCP Figma échoue à la connexion (mandataire, 403).
- Accessibles : raw.githubusercontent.com, code.claude.com, pypi.org, registry.npmjs.org, conda.anaconda.org.

### 2.3 Contradictions datées entre documents

La date est celle de l'état annoncé par le texte, ou du dernier commit qui touche le fichier. Ce document ne corrige
aucun de ces textes.

| N° | Ce qui est écrit (date) | Ce qui est vérifié | Suite |
|---|---|---|---|
| 1 | `CLAUDE.md:24` (texte de P9, 9 octobre) : « Fin de la refonte… (en cours, étape P9) » | `main` porte 1.0.0 puis 1.0.1 (`README.md:4-6` ; `85b458b`) | La recette « Après 1.0.0 » s'applique (`CLAUDE.md:45-56`) ; D169 en tire 1.1.0 |
| 2 | `docs/refonte/plan.md:457` (état du 9 octobre) : « Rien n'est déployé » ; même constat dans `docs/reprise-poste.md:35` | `README.md:8-11` (10 octobre) : Authelia démarré sur Railway, Hermes 1.0.0 refusé en PID 2, exécutant limité à sa sonde | `docs/reprise-poste.md:8` déclare historiques les paragraphes du 9 octobre ; `plan.md` ne le dit pas |
| 3 | `docs/reprise-poste.md:3-8` (10 octobre) : correctif 1.0.1 demandé, branche `fix/railway-init-1.0.1` | `main` n'a aucun commit après `85b458b`, et aucun de ses documents ne cite `v1.0.1` (`git grep 'v1\.0\.1' 85b458b` vide) ; seuls les runs de la PR #27 avant fusion sont consignés (`docs/refonte/ci-1.0.1-correctifs.md:5-6`) | Étape 6 de la recette (preuves publiées) non faite pour 1.0.1 |
| 4 | `CHANGELOG.md:8-29` (10 octobre) : section 1.0.1 avec « Corrigé » (ligne 10) et « Vérification et limites » (ligne 23) | La recette veut six rubriques et un commit `chore(release): prepare X changelog` (`CLAUDE.md:50-51`) ; `git log --oneline f76e7c5..85b458b` n'en montre aucun | À tenir pour 1.1.0 |
| 5 | `docs/desktop-build.md:4` (état du 9 octobre), `docs/native-desktop-architecture.md:3` et `docs/desktop-security.md:3` (état du 2 octobre) : version 0.11.0 | `VERSION` vaut `1.0.1` | Non corrigé ici |
| 6 | `docs/desktop-security.md:137-139` (état du 2 octobre) : « aucune revue de sécurité indépendante de l'étape P8 à ce jour » | `docs/refonte/desktop.md:97-99` (2 octobre) : seize constats d'une relecture indépendante « exactitude, sécurité, produit » | `docs/desktop-security.md:9-10` dit ne pas avoir été modifié par P8b |
| 7 | `design/tokens/motion.json:12` (18 septembre) : la préférence système de mouvement est « exposée par la couche C++ » | `apps/desktop/src/system/SystemAppearance.cpp:100-103` : « system » donne toujours `standard`. Le commentaire y affirme que l'écran de préférences le dit ; `apps/desktop/qml/pages/SettingsPage.qml:62-66` n'offre qu'une case « Réduire les animations », sans cette mention ni retour à « system » | Lot B (profils Complet, Discret, Réduit) |
| 8 | `docs/refonte/image.md:748` (fichier touché le 10 octobre par `61f4b9f`) : `plugin.yaml` en version 0.11.0 | `hermes/plugins/acp-poste/plugin.yaml:16` : `version: 1.0.1` | Non corrigé ici |
| 9 | `docs/refonte/projets.md:40` (8 octobre) : `base.py`, « schéma v1 » | `hermes/plugins/acp-poste/noyau/base.py:56` : `VERSION_SCHEMA = "4"` | Le lot C prévoit une v5 (section 6) |
| 10 | `docs/refonte/plan.md:762` (plan d'origine) : « Réglages, en lecture seule, renvoi vers le web » | La page livrée règle serveur, session, apparence et mises à jour (`apps/desktop/qml/pages/SettingsPage.qml:16-81`) ; le plan d'autonomie remplace P4 à P8 (`docs/refonte/plan.md:16-18`) | D167 regroupe les pages techniques sous Réglages |
| 11 | `apps/desktop/src/storage/SettingsStore.h:4-6` (2 octobre) : la liste blanche couvre un « dernier projet ouvert » | Aucune clé de ce nom parmi les huit (`apps/desktop/src/storage/SettingsStore.cpp:26-36`) | D167 : brouillons en mémoire seulement |
| 12 | `apps/desktop/cmake/generate_design_tokens.py:188` (18 septembre) : thème « écrit par la couche C++ (ThemeController) » | Aucune classe `ThemeController` ; `apps/desktop/qml/theme/ThemeBridge.qml:15-27` écrit le thème | Lot B modifie ce générateur |
| 13 | `apps/desktop/CMakeLists.txt:8` : « préréglages version 6 » | `apps/desktop/CMakePresets.json:2` : `"version": 5` | Non corrigé ici |
| 14 | `CLAUDE.md:132-133` : le checkout principal porte un chantier Pixel Office non commité | Ce clone n'a qu'un worktree, sans changement au démarrage (section 2.1) | Rien de tel dans ce clone ; la règle vise le poste du propriétaire |

## 3. Points d'audit antérieurs revérifiés

Sept points, ceux du brief, relus dans le code à `85b458b`.

| Point | Verdict | Preuve |
|---|---|---|
| 1. Navigation centrée sur Projets, Questions, Discussion, Poste, Quotas et Routage | Confirmé | Onze destinations plates, dont « office » hors périmètre (`apps/desktop/src/navigation/NavigationModel.cpp:29-55`) ; section « PILOTAGE » de la barre latérale (`apps/desktop/qml/shell/SideNavigation.qml:132-143`) ; un `Loader` et un `switch` détruisent la page quittée (`apps/desktop/qml/shell/WorkArea.qml:19-36`) ; inspecteur figé vide (`apps/desktop/qml/shell/ShellRoot.qml:15`). Aucune hiérarchie projet, puis mission : le mot « mission » n'apparaît que dans un exemple de commentaire (`apps/desktop/src/commands/Command.h:60`) |
| 2. Aucun parcours graphique de configuration des assistants | Confirmé | La station affiche l'état des connexions Codex et Claude Code en lecture seule (`apps/desktop/qml/pages/PostePage.qml:304-314`) ; le greffon n'a aucune route de compte (`hermes/plugins/acp-poste/dashboard/plugin_api.py`, routes des lignes 127 à 1243) ; les connexions sont des gestes du propriétaire en `railway ssh` (`apps/poste/src/acp_poste/gestes_executant.py:1-15` ; D83, D84, D92) ; seuls des états observés remontent (`hermes/plugins/acp-poste/contrat/acp_poste_contrat/inventaire.py:640-653`) |
| 3. Délégation native de Codex désactivée, outils de délégation de Claude non autorisés | Confirmé, avec une nuance | `multi_agent` figure dans les fonctions coupées de Codex (`apps/poste/src/acp_poste/commandes_agents.py:48-50`), passées en `--disable` (`:99-100`) ; Claude ne reçoit que `Read,Glob,Grep[,Edit,Write]` par `--tools` (`:51-52`, `:116`). Testé contre les binaires de l'image de l'exécutant : fonctions coupées à `false` (`executant/tests/test_image.py:290-304`), outils de l'init réel limités aux outils demandés plus `StructuredOutput` (`:452-455`). Nuance : la liste noire du contrôle d'init contient `Task` mais pas `Agent` (`apps/poste/src/acp_poste/evenements.py:33`) ; la garantie vient de la liste blanche `--tools` |
| 4. Flux des CLI réduits aux résultats, sessions, erreurs et consommation | Confirmé, et plus restrictif encore | Rien n'est journalisé ni transmis brut (`apps/poste/src/acp_poste/evenements.py:4-5`). Vers Hermes : un battement générique (`apps/poste/src/acp_poste/execution.py:884-889`) et, à la fin, résumé et métadonnées (`:706-717`), la session réduite au booléen `session_locale` (`:711`). La sortie d'erreur est lue puis jetée (`:860-866`). Le texte d'erreur de la CLI est capté (`:933`, `:937`) et n'est lu nulle part ailleurs (`git grep '\.erreur\b' 85b458b -- apps/poste/src`) |
| 5. SSE employé comme signal d'invalidation | Confirmé | Le flux ne porte aucune donnée métier (`hermes/plugins/acp-poste/noyau/flux.py:3-5`) et n'est pas rejouable : révision en mémoire (`:31-33`). La station ne retient que les noms de sujets connus, puis émet `invalidation` (`apps/desktop/src/events/FluxInvalidation.h:4-7` ; `apps/desktop/src/events/FluxInvalidation.cpp:342-387`). Décision D96 |
| 6. Formulaire de création qui impose un exécutant ou un modèle et contourne Auto | Confirmé, pour la carte d'exploration | La voie retenue d'office est la première voie relevée (`apps/desktop/src/viewmodels/ProjetsViewModel.cpp:865-867`) ; l'exploration vaut dès qu'un dépôt est choisi et qu'une voie est relevée (`:894`) ; `exploration.voie` part alors toujours (`:995-1005`). Aucune entrée « Auto » dans la liste (`apps/desktop/qml/pages/ProjectsPage.qml:669-671`). Un test fige l'envoi sans choix (`apps/desktop/tests/cpp/tst_projets.cpp:794-802`). Côté greffon, ce champ fait passer par `choix_explicite` (`hermes/plugins/acp-poste/noyau/projets.py:141-149` ; `hermes/plugins/acp-poste/noyau/routage.py:530-546`), sans repli sur la table (`:550-557`). Correction : D168 (section 6) |
| 7. Charte de mouvement qui interdit le décor animé | Confirmé ; la source n'est pas une décision numérotée | « Jamais décoratif », 240 ms au plus (`design/tokens/motion.json:3`) et règles (`:56-61`) ; seul l'état `running` s'anime (`design/tokens/semantic-status.json:43`) ; DA « QUIET OPERATIONS », sans décor (`apps/desktop/resources/images/README.md:7-8`) ; plafond testé (`apps/desktop/tests/qml/tst_design_tokens.qml:147-153`). Remplacée par D165, qui garde le profil réduit complet et l'interdiction de toute fausse activité |

## 4. Matrice besoin, existant, écart

Une ligne par section du brief, du § 6 au § 20. « Livré dans ce chantier » dit le périmètre engagé (lots A et B,
point « Auto par défaut ») ; la preuve de livraison est dans la section 7 et dans la CI.

| Besoin (§ du brief) | Existant à `85b458b` | Écart | Fichiers | Tests | Risques | Lot | Livré dans ce chantier ? |
|---|---|---|---|---|---|---|---|
| § 6 Projets, missions, exécutions | Un projet du greffon porte objectif, état, tours, plafonds et un tableau kanban (`hermes/plugins/acp-poste/noyau/base.py:60-78`) ; ses cartes sont des `demandes` (`base.py:94`) ; le run est le `current_run_id` du kanban (`hermes/plugins/acp-poste/noyau/execution.py:325`) ; `depot` est servi par `GET /v1/projets` (`hermes/plugins/acp-poste/noyau/projets.py:215`, `361`) | Aucun regroupement durable au-dessus d'un projet ; aucun niveau « mission » (seul un exemple de commentaire : `apps/desktop/src/commands/Command.h:60`) | `hermes/plugins/acp-poste/noyau/base.py`, `projets.py` ; `apps/desktop/src/viewmodels/ProjetsViewModel.*` ; `apps/desktop/qml/shell/` | `apps/desktop/tests/cpp/tst_projets.cpp` ; `hermes/tests/image/test_projets_base.py`, `test_projets_lancer.py` | L'API dit « projets » là où l'interface dit « missions » (D166) ; `projets_actifs_max` vaut 3 (`base.py:343`) ; tout ajout serveur étend `acp-poste/1` (D130) | B (regroupement par dépôt) ; C (projet durable) | Partiel : regroupement par dépôt dans la station, rien côté serveur |
| § 7 Agencement de l'espace de travail | Barre latérale plate (`apps/desktop/qml/shell/SideNavigation.qml:132-143`) ; centre chargé par un `Loader` qui détruit la page quittée (`apps/desktop/qml/shell/WorkArea.qml:19-36`) ; inspecteur jamais affiché (`apps/desktop/qml/shell/ShellRoot.qml:15`) ; huit clés de préférences (`apps/desktop/src/storage/SettingsStore.cpp:26-36`) | Ni barre projets et missions, ni saisie persistante, ni panneau des agents, ni volet bas ; Poste, Quotas, Routage, Sauvegarde et Diagnostics au premier niveau | `apps/desktop/qml/shell/` ; `apps/desktop/src/navigation/NavigationModel.*` ; `apps/desktop/src/app/Application.cpp:335-454` (commandes, raccourcis) ; `apps/desktop/src/storage/SettingsStore.*` | `tst_pages_bureau`, `tst_pages_interactions` (`chaqueRaccourciDeLaPaletteAgit`, ligne 974), `tst_command_registry`, `tst_reglages_sans_secret`, `tst_oubli_local` | Les tests lisent les `objectName` et les raccourcis Ctrl+1 à Ctrl+9 ; un brouillon écrit sur disque romprait l'oubli local (D167) ; l'Accueil garde ses sept blocs (D99) | B | Oui (disposition, état conservé) ; contenu des onglets : lignes § 14 et § 15 |
| § 8 Onboarding | `FirstRunPage` tant qu'une connexion est requise (`apps/desktop/qml/App.qml:40-53`) ; enrôlement du poste par code de 10 min, confirmation d'empreinte, révocation (`hermes/plugins/acp-poste/dashboard/plugin_api.py:980-1024` ; D48, D49) | Aucun parcours guidé : exécutant, comptes, premier projet, notifications | `apps/desktop/qml/pages/FirstRunPage.qml` ; `apps/desktop/src/viewmodels/ShellViewModel.*`, `PosteViewModel.*` | `tst_poste`, `tst_pages_bureau` | Les connexions restent des gestes du propriétaire en `railway ssh` (`apps/poste/src/acp_poste/gestes_executant.py:1-15`) : l'onboarding les décrit, il ne les fait pas | C | Non |
| § 9 Direction artistique | DA « QUIET OPERATIONS », sans décor (`apps/desktop/resources/images/README.md:7-8`) ; palette « graphite végétal, papier ivoire et sarcelle » (`design/tokens/colors.json:3`) ; logotype texte (D14) ; pictogrammes Canvas originaux (`apps/desktop/qml/controls/AcpIcon.qml`) ; aucune police embarquée (`apps/desktop/resources/fonts/README.md:3`) | Ni Pixel Atelier, ni famille Studio nommée, ni emblème, ni police pixel | `design/tokens/` ; `design/pixel/` ; `apps/desktop/cmake/generate_design_tokens.py` ; `apps/desktop/qml/pixel/` ; `scripts/generer_themes.py` | `apps/desktop/tests/qml/tst_design_tokens.qml` ; `scripts/tests/test_generer_themes.py` | Les jetons font aussi le thème web : `hermes/theme/acp.yaml` régénéré, `image.yml` relancé, Hermes redéployé à la fusion (D169) ; aucun asset sous licence ni chemin gelé (`scripts/check_engine_frozen.py:36`) | B | Oui (D165) |
| § 10 Thèmes et animations | Deux thèmes, `dark` et `light`, en dur (`apps/desktop/cmake/generate_design_tokens.py:209`, `241`, `611` ; `apps/desktop/src/storage/SettingsStore.cpp:92-101`) ; deux profils, `standard` et `reduced` (`generate_design_tokens.py:542` ; `SettingsStore.cpp:108-117`) ; bascule à chaud par liaisons (`apps/desktop/qml/theme/ThemeBridge.qml:15-27`) | Ni quatre thèmes en deux familles, ni Complet, Discret, Réduit, ni Concentration. Un nom de thème inconnu retombe sur le sombre (`isDark: theme !== "light"`, `generate_design_tokens.py:191`). Seul le sombre est contrôlé en contraste par un script (`scripts/generer_themes.py:49`, `52-53`) ; le clair garde des mesures du 23 septembre, non recalculées (`design/tokens/colors.json:19-29`) | `design/tokens/colors.json`, `motion.json`, `spacing.json`, `typography.json` ; `apps/desktop/qml/theme/` ; `apps/desktop/src/system/SystemAppearance.*` ; `apps/desktop/src/storage/SettingsStore.*` ; `apps/desktop/qml/pages/SettingsPage.qml` | `tst_design_tokens.qml` (240 ms au plus : lignes 147-153 ; profil réduit : 155-164) ; `tst_reglages_sans_secret` ; `test_generer_themes.py` | Le profil réduit doit rester complet (`design/tokens/motion.json:60`) ; la fluidité n'est pas mesurée ici (lot F) | B | Oui |
| § 11 Icône et assets | Aucune icône d'application : ni `.ico`, ni `.rc`, ni `setWindowIcon` (`git grep` vide à `85b458b`) ; exécutable sans ressource (`apps/desktop/CMakeLists.txt:284`) ; installeur sans `SetupIconFile`, icône de désinstallation prise dans l'exécutable (`packaging/windows/AgentCompanyPlatform.iss:50`) ; seuls PNG pixel du dépôt dans un chemin gelé (`apps/web/public/assets`) | Emblème, icône multirésolution, portraits, pictogrammes et police pixel à créer, tous originaux | `design/pixel/` ; `scripts/generer_assets_pixel.py` ; `apps/desktop/qml/pixel/` ; `apps/desktop/resources/windows/` ; `apps/desktop/CMakeLists.txt` ; `apps/desktop/src/main.cpp` ; `packaging/windows/AgentCompanyPlatform.iss` | Tests pytest du générateur, `--check` pixel par pixel ; aucune installation Windows possible dans cette session | Rendu de l'icône dans l'Explorateur, la barre des tâches et l'installeur non vu sans Windows ; `SourceDir` d'Inno Setup (`AgentCompanyPlatform.iss:53`) | B ; F pour la preuve sous Windows | Oui, non vérifié sous Windows |
| § 12 Validation visuelle | `tst_pages_bureau` charge chaque page et refuse les textes anglais ou cassés (`apps/desktop/tests/cpp/tst_pages_bureau.cpp:52-58`) ; captures non committées (D17) ; Desktop CI sur `windows-2022` (`.github/workflows/desktop-ci.yml:70`) | Aucune référence visuelle par thème, aucune comparaison avant et après, aucune mesure de cadence | `apps/desktop/tests/` ; ce document | `tst_pages_bureau`, `tst_pages_interactions`, `tst_qml_shell` | Rendu offscreen sous Linux, différent de Windows ; captures hors dépôt (D17) | A (référence) ; F (profilage, accessibilité) | Partiel : 17 captures « avant » prises dans cette session, hors dépôt |
| § 13 Comptes | États observés par l'inventaire, sans identifiant : Codex (`compte_chatgpt`, `cle_api`, `autre`, `non_connecte`, `inconnu`) et Claude (`jeton_reconnu`, `jeton_present_non_verifie`, `refuse`, `jeton_absent`, `inconnu`) (`hermes/plugins/acp-poste/contrat/acp_poste_contrat/inventaire.py:640-653`) ; affichés en lecture (`apps/desktop/qml/pages/PostePage.qml:304-314`) | Aucune page Comptes ; aucun parcours de connexion piloté par Hermes ; aucune route de compte dans le greffon | `apps/desktop/qml/pages/` (Réglages, Comptes) ; `apps/desktop/src/viewmodels/PosteViewModel.*` | `tst_poste`, `tst_pages_bureau` | Aucun code d'appareil ni jeton par la station ou par Hermes (D83, D84, D92) ; l'échéance du jeton Claude est estimée, jamais vérifiée (`inventaire.py:643-645`) | B (états observés, gestes décrits) ; C (parcours piloté par Hermes) | Partiel |
| § 14 Supervision des agents | Carte en main de l'exécutant : rôle, voie, modèle demandé et servi, dernier battement (`hermes/plugins/acp-poste/noyau/execution.py:771-794`) ; une carte à la fois (`executant/politique/executant.toml:49`) ; un seul poste actif (`hermes/plugins/acp-poste/noyau/base.py:177`) ; session remontée en booléen (`apps/poste/src/acp_poste/execution.py:711`) | Aucun arbre d'agents, aucune session d'agent observée, aucun sous-agent (délégation coupée, section 3) | `apps/desktop/qml/shell/` (panneau des agents) ; `apps/desktop/src/viewmodels/ProjetsViewModel.*`, `PosteViewModel.*` | `tst_projets`, `tst_poste` ; `hermes/tests/image/test_execution_p6.py` | Des agents parallèles ou des sous-agents affichés seraient une donnée inventée : « Non observé » | B (panneau sur les données servies) ; D (données par carte) | Partiel |
| § 15 Événements durables | Table `journal` durable, à identifiant croissant (`hermes/plugins/acp-poste/noyau/base.py:159`), détail tronqué à 2000 caractères (`base.py:543`) ; 100 dernières lignes servies par projet (`hermes/plugins/acp-poste/noyau/projets.py:324-327`) ; flux sans rejeu (`hermes/plugins/acp-poste/noyau/flux.py:31-33`) | Ni identifiant d'événement, ni source, ni route paginée, ni sujet de flux pour l'activité | `hermes/plugins/acp-poste/noyau/base.py`, `emetteur.py`, `flux.py` ; `hermes/plugins/acp-poste/dashboard/plugin_api.py` ; `hermes/plugins/acp-poste/meta.py` ; `apps/desktop/src/events/` | `hermes/tests/image/test_flux.py` ; `tst_flux_invalidation`, `tst_temps_reel` | Schéma v5 (`base.py:56`) et procédure de `docs/exploitation.md` ; un sujet de flux nouveau reste compatible, la station ignorant un sujet inconnu (`apps/desktop/src/events/FluxInvalidation.cpp:367-368`) | D | Non |
| § 16 Routage | Résolution déterministe : surcharge, choix explicite, profil Hermes, puis table (`hermes/plugins/acp-poste/noyau/routage.py:524-557`), refus exact sans repli silencieux ; table non versionnée (`routage.py:189-192`) ; le formulaire impose la voie d'exploration (section 3, point 6) | « Auto » contourné au lancement ; aucun mode Économe, Équilibré, Approfondi ; aucun critère tracé, aucun banc d'évaluation | `apps/desktop/src/viewmodels/ProjetsViewModel.cpp` ; `apps/desktop/qml/pages/ProjectsPage.qml` ; `apps/desktop/qml/pages/RoutagePage.qml:77-84` ; `hermes/plugins/acp-poste/noyau/routage.py` | `apps/desktop/tests/cpp/tst_projets.cpp:794-802` (fige l'envoi d'office) ; `tst_routage` ; `hermes/tests/image/test_routage.py` et suivants | Un choix manuel refusé fait refuser le lancement (`hermes/plugins/acp-poste/noyau/projets.py:147-149`) ; efforts interdits (D39) ; choix explicite du modèle Claude (D73) ; aucun mode offert avant son annonce dans `/v1/meta` (D168) | C (Auto par défaut) ; E (modes, critères versionnés, banc) | Partiel : Auto par défaut seulement |
| § 17 Contexte, mémoire et Git | Branches `hermes/projet-<slug>` ou `hermes/<carte>` sur l'exécutant, récupérées par `git bundle` (`apps/poste/src/acp_poste/gestes_executant.py:10-11`) ; aucun push (D82 ; `hermes/plugins/acp-poste/noyau/execution.py:797-799`) ; ne remontent que diffstat, base, tête, vérification et chemins de pilotage (`apps/poste/src/acp_poste/execution.py:704-712`) ; mémoire de l'agent sous validation (`hermes/plugins/acp-poste/garde_execution.py:73-74`) | Ni diff, ni liste des fichiers, ni contexte d'une carte lisible dans la station | `apps/poste/src/acp_poste/execution.py` ; `hermes/plugins/acp-poste/noyau/execution.py` ; `hermes/plugins/acp-poste/contrat/acp_poste_contrat/machine.py` | `hermes/tests/image/test_execution_p6.py` ; `apps/poste/tests/test_gestes_executant.py` | `acp-machine/1` refuse tout champ inconnu des deux côtés (`machine.py:17-18`) : un champ nouveau impose de livrer ensemble greffon et exécutant | D (diffstat et vérifications par carte) ; le reste n'est classé dans aucun lot | Non |
| § 18 Outils et skills du produit | 33 outils nommés pour l'agent sur Railway (`hermes/plugins/acp-poste/garde_execution.py:63-86`) ; catalogue verrouillé (`hermes/catalogue/catalogue.lock.json`, `scripts/verifier_catalogue.py`) ; route `/v1/catalogue` (`hermes/plugins/acp-poste/dashboard/plugin_api.py:134`), lue par le formulaire de nouveau projet (`apps/desktop/src/viewmodels/ProjetsViewModel.cpp:738`) | Aucun écran des skills ni des outils dans la station | `hermes/plugins/acp-poste/garde_execution.py` ; `hermes/catalogue/` ; `apps/desktop/src/viewmodels/` | `hermes/tests/image/test_sans_shell.py`, `test_catalogue_route.py` ; `scripts/tests/test_verifier_catalogue.py` | Aucun outil d'exécution pour l'agent sur Railway (`CLAUDE.md`) ; un MCP n'est admis que distant et inscrit au catalogue | Aucun lot de la spécification | Non |
| § 19 Extensions | Bilan quotidien créé depuis l'Accueil comme tâche planifiée de Hermes (`apps/desktop/src/viewmodels/AccueilViewModel.cpp:294`, `POST /api/cron/jobs`) ; « Bureau de département » hors périmètre (`apps/desktop/src/navigation/NavigationModel.cpp:50-54`) ; moteur Pixel Office gelé (`scripts/check_engine_frozen.py:36`) | Ni missions récurrentes, ni services au sens du § 19, ni Pixel Office dans la station | Aucun dans ce chantier | `scripts/tests/test_check_engine_frozen.py` | Moteur gelé octet pour octet ; aucun travail Godot avant la dernière phase (`CLAUDE.md`) | Backlog, hors lots A à F | Non |
| § 20 Tests | 35 suites Qt Test et une suite Qt Quick Test de cinq fichiers QML (`apps/desktop/tests/CMakeLists.txt`) ; preuve qui fait foi : Desktop CI sur `windows-2022` (`.github/workflows/desktop-ci.yml:70`) ; jetons contrôlés par `ci.yml` seulement (`.github/workflows/ci.yml:139-140`) ; préréglage `linux-gcc-debug` hors CI (`apps/desktop/CMakePresets.json:75`) | Aucun test des quatre thèmes, des assets pixel, de l'espace de travail, du thème à chaud sans recréation ni des brouillons conservés | `apps/desktop/tests/cpp/` ; `apps/desktop/tests/qml/` ; `scripts/tests/` | Objet de la ligne | DPAPI absent sous Linux (`tst_pages_bureau` rouge à l'étape Sauvegarde) ; CTest compte « Passed » un `QSKIP` (`docs/desktop-build.md:163`) ; bout en bout local hors CI (D8-10) | A et B | Partiel : tests des lots A et B ; la preuve Windows reste la CI |

## 5. Vocabulaire (D166)

| Mot du brief | Sens dans ACP | Source réelle |
|---|---|---|
| Projet (durable) | Regroupement de missions. Côté greffon au lot C : table de regroupement et colonne de rattachement, annoncées dans `/v1/meta`. D'ici là, la station regroupe les missions par dépôt autorisé, ou « Sans dépôt » | champ `depot` servi (`hermes/plugins/acp-poste/noyau/projets.py:215`) |
| Mission | Un projet du greffon : objectif, cycle de vie, tours, plafonds, tableau kanban. Les routes gardent le nom `projets` : le contrat `acp-poste/1` ne change pas | table `projets` (`hermes/plugins/acp-poste/noyau/base.py:60-78`) |
| Tâche | Une carte kanban, née d'une demande | table `demandes` (`base.py:94`) |
| Exécution | Le run kanban d'une carte | `current_run_id` (`hermes/plugins/acp-poste/noyau/execution.py:325`) |
| Session d'agent | L'exécution d'une carte par une CLI. Son identifiant reste sur l'exécutant : la station dit « Non observée » | booléen `session_locale` (`apps/poste/src/acp_poste/execution.py:711`) |
| Sous-agent natif | Non observé : la délégation est coupée | section 3, point 3 |
| Discussion (précision de ce document) | Une session de Hermes par JSON-RPC `/api/ws`, distincte d'une session d'agent, sans choix de modèle (D8-9) | `apps/desktop/src/viewmodels/DiscussionViewModel.h:23` |

D166 amende le § 11 du plan, qui retirait les missions de l'ancienne API (`docs/refonte/plan.md:1029`) : le mot
revient dans l'interface, sans table redondante.

## 6. Plan des lots

Les lots A et B et le point « Auto par défaut » relèvent de ce chantier. Pour les lots C à F, les critères de sortie
sont proposés par ce document ; ils restent à valider avec le propriétaire.

### Lot A : état réel, matrice, outillage, contrats, référence visuelle (ce chantier)

Périmètre :

- ce document : état du dépôt, contradictions, points d'audit, matrice, vocabulaire ;
- décisions D165 à D169 inscrites au plan ;
- outillage hors dépôt : Qt 6.8.3, GCC, CMake, Ninja (section 2.2) ;
- contrats lus, sans changement : `acp-poste/1` et `acp-machine/1` ;
- référence visuelle : captures « avant », gardées hors dépôt (D17).

Critères de sortie :

- chaque `chemin:ligne` relu à `85b458b` ;
- `scripts/tests/test_decisions_documentees.py` vert : toute décision citée est définie au plan ;
- `git diff --check` propre, fins de ligne LF.

### Lot B : espace de travail natif et Pixel Atelier (ce chantier)

Périmètre, repris de la spécification du chantier :

- jetons : quatre thèmes (`atelier-nuit`, `atelier-jour`, `studio-graphite`, `studio-papier`) en deux familles ;
  trois profils de mouvement et Concentration ; densités ; taille du texte ; disposition de l'espace de travail ;
- assets pixel : `design/pixel/manifeste.json` ; sources texte `sources/embleme.txt`, `portraits.txt`, `police.txt`,
  `pictogrammes.txt` ; générateur `scripts/generer_assets_pixel.py` (bibliothèque standard, `--check` par pixels) ;
  sorties `apps/desktop/qml/pixel/assets/*.png` ; icône `apps/desktop/resources/windows/AgentCompanyPlatform.ico`
  (16, 20, 24, 32, 40, 48, 64, 128 et 256 px) ; métadonnées `design/pixel/generes/*.json` ; singleton QML
  `Acp.Pixel/PlanchesPixel` ;
- station : module QML `Acp.Pixel` ; nouveau shell (D167) ; Réglages regroupés (Apparence, Comptes, Exécutants,
  Modèles et budgets, Sauvegarde, Diagnostics, Connexion) ; page Apparence avec aperçu ; page Comptes (états
  observés, gestes officiels décrits) ; icône de fenêtre, ressource Windows, icône d'installeur.

Critères de sortie :

- contrastes vérifiés par `apps/desktop/cmake/generate_design_tokens.py` pour les quatre thèmes : refus sous 4,5:1
  pour le texte et sous 3:1 pour les bordures interactives ;
- `python scripts/generer_themes.py --check` et `python scripts/generer_assets_pixel.py --check` verts ;
- tests : jetons des quatre thèmes, assets (pytest), espace de travail (C++), thème changé à chaud sans recréer les
  pages, brouillons conservés, navigation ;
- suites locales vertes, hors la limite DPAPI connue, puis Desktop CI Windows verte ;
- aucune clé de préférences hors liste blanche, aucun secret, aucune donnée inventée ;
- version 1.1.0 ouverte au moment de la PR (D169) ; fusion et étiquette sur accord du propriétaire.

### Point « Auto par défaut » du lot C (ce chantier)

Périmètre : D168, côté station seulement. Le greffon accepte déjà un corps sans `exploration` et résout alors seul
(`hermes/plugins/acp-poste/noyau/projets.py:141-149`).

Critères de sortie :

- sans choix manuel, `POST /v1/projets` ne porte pas de champ `exploration` ;
- un choix manuel envoie `exploration.voie`, et le modèle ou l'effort s'ils sont choisis : verrou explicite ;
- `tst_projets` réécrit : l'ancien cas attendait l'envoi d'office (`apps/desktop/tests/cpp/tst_projets.cpp:794-802`) ;
- le texte de `apps/desktop/qml/pages/RoutagePage.qml:77-84` suit le nouveau comportement.

### Lot C : projet durable, onboarding, comptes (backlog)

Périmètre : regroupement durable côté greffon (D166) ; onboarding complet ; parcours de connexion des comptes
piloté par Hermes.

Critères de sortie proposés :

- schéma v5 additif, avec ses tests de migration ;
- capacité annoncée dans `/v1/meta` et vérifiée par la station avant toute écriture : le greffon refuse un champ
  inconnu (`hermes/plugins/acp-poste/dashboard/plugin_api.py:245-247`) ;
- aucun code d'appareil ni jeton par la station ou par Hermes (D83, D84, D92) ; Railway reste au propriétaire.

### Lot D : activité durable (backlog)

Périmètre : `journal` étendu, route paginée et sujet de flux ; diffstat et vérifications servis par carte ;
commandes confirmées.

Critères de sortie proposés :

- rejeu sans trou par la route paginée ; le flux reste une invalidation (D96) ;
- ingestion idempotente des événements du kanban ;
- `acp-machine/1` inchangé, ou greffon et exécutant livrés ensemble.

### Lot E : routage enrichi (backlog)

Périmètre : modes Économe, Équilibré, Approfondi ; critères de routage versionnés ; banc d'évaluation.

Critères de sortie proposés :

- modes annoncés par le greffon dans `/v1/meta` avant d'être offerts (D168) ;
- correspondance d'un mode vers effort et palier conforme à la politique (D39) ;
- table versionnée, raisons des entrées écartées gardées.

### Lot F : preuves sous Windows (backlog)

Périmètre : empaquetage prouvé sous Windows ; profilage à 60 images par seconde sur une machine de référence ;
accessibilité complète.

Critères de sortie proposés :

- installeur construit puis installé ; icône vue dans l'Explorateur, la barre des tâches et le menu Démarrer.
  `.github/workflows/desktop-release.yml:11-13` se dit jamais exercé au 9 octobre 2026 ; aucun run n'est vérifié ici ;
- cadence mesurée et publiée, en profil Complet et en profil Réduit ;
- parcours complet au clavier et au lecteur d'écran.

### Hors lots

- § 18 du brief (outils et skills du produit) : classé dans aucun lot par la spécification.
- § 19 du brief (missions récurrentes, services, Pixel Office secondaire) : backlog.

## 7. Reprise

État au 11 octobre 2026, fin de session.

**Git.** Branche `claude/wonderful-brahmagupta-rlbkuj`, ouverte depuis `main` (`85b458b`, 1.0.1) et poussée. Le
code des lots A et B est dans `067acd0` (`feat(desktop): add pixel atelier workspace, themes and generated assets`) ;
la documentation du chantier et les correctifs de relecture viennent dans les commits suivants de la même branche.
Aucune PR, aucune version ouverte (1.1.0 au moment de la PR, D169), aucune étiquette, rien sur Railway. Les captures
ne sont pas committées (D17) : elles se régénèrent par la commande ci-dessous.

**Commandes rejouées** (Linux, Qt 6.8.3 de conda-forge installé par `scripts/installer_qt_linux.py`, voir
[atelier-outillage.md](atelier-outillage.md)) :

```text
export QT_ROOT_DIR=/opt/acp-outils/qt683
cmake --preset linux-gcc-debug -DCMAKE_CXX_COMPILER=g++ && cmake --build --preset linux-gcc-debug -j4
LANG=C.UTF-8 LC_ALL=C.UTF-8 QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=$QT_ROOT_DIR/fonts \
  ctest --test-dir build/linux-gcc-debug -j3                     # 37 sur 37
ACP_CAPTURES_DIR=<dossier> ./build/linux-gcc-debug/tests/tst_pages_bureau   # captures, quatre thèmes
python scripts/generer_themes.py --check && python scripts/generer_assets_pixel.py --check
python -m pytest -q scripts/tests/test_generer_assets_pixel.py scripts/tests/test_generer_themes.py
```

La suite Python complète (`python -m pytest -q -rs`, 1 264 réussis) montre 30 échecs dans
`apps/poste/tests/contrat` : l'autorité de test TLS du faux Hermes y est refusée par le Python 3.13 du conteneur
(« Certificat de Hermes refusé ») ; la CI utilise 3.12 et ce chantier ne touche pas `apps/poste`.

**Jamais exécuté.** Compilation MSVC et tests sous Windows (`desktop-ci.yml` ne tourne qu'en PR vers `main` ou
`refonte/hermes` et sur `main` et `refonte/**`), empaquetage Inno Setup et icône installée, rendu à 125 et 150 %
sous Windows (seulement `QT_SCALE_FACTOR` hors écran), bouts en bout Docker, Figma (connecteur indisponible).

**Prochaine action.** Ouvrir la PR vers `main` quand le propriétaire le décide : commit d'ouverture 1.1.0 puis
journal (recette de `CLAUDE.md`, D169), quatre workflows verts, preuves sous Windows (lot F). Puis lot C (projet
durable, [atelier-contrats.md](atelier-contrats.md) § 2).
