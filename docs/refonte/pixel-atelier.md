# Pixel Atelier — refonte native du workspace

État du 12 octobre 2026. Le lot **1.1.0** a été fusionné dans `main` par la
[PR #28](https://github.com/Paul-Berdier/agent-company-platform/pull/28), commit
`028eaa5d8c211bda77abc15ecb794c20b91d7eee`, portant le tag annoté `v1.1.0`.
La branche `codex/pixel-atelier` partait de `85b458b` (ACP 1.0.1). Le checkout
personnel `feat/desktop-qt-railway` et ses modifications Pixel Office ont été préservés.
Les [preuves de livraison](preuves-1.1.0.md) distinguent les quatre workflows
complets réussis sur la tête proposée, le contenu fusionné identique, les paquets
locaux et le brouillon GitHub. Le [guide de mise à jour](../mettre-a-jour-1.1.md)
décrit le remplacement de la station ; les connexions personnelles, l'installation
sur le poste du propriétaire et le déploiement Railway ne sont pas attestés ici.

## Parcours livré

L’accueil devient **Mon atelier** : reprendre un projet, en créer un, parler à
Hermes et lire les demandes qui attendent le propriétaire. L’état technique reste
accessible dans un panneau dépliable. La navigation latérale présente les projets
et rassemble les écrans d’exploitation derrière **Réglages**.

Le workspace de projet met l’objectif en tête puis organise le contenu en
**Travail**, **Résultats**, **Journal** et **Réglages**. Une sélection de carte ouvre
un inspecteur redimensionnable, placé sous la liste lorsque l’espace est étroit.
Les données, refus et actions proviennent des interfaces existantes de Hermes.
Le formulaire démarre en **Auto** : aucune sélection mémorisée de modèle ou d’effort
ne devient une surcharge implicite. Un choix manuel explicite ouvre les contrôles.
Les préférences du plan Hermes restent dans la table autorisée et ne remplacent
pas les verrous du propriétaire ([routage Auto](routage-plan-auto.md)).

L’inspecteur affiche aussi la dernière exécution vérifiée : branche, commits,
vérification, modèle observé et jetons rapportés. Une valeur absente reste inconnue.
Le nouvel écran **Assistants** décrit la machine active, guide la connexion réelle
de Codex et Claude et attend un nouvel inventaire après une demande de vérification
([parcours](assistants-1.1.md)). La récupération d’une branche signalée terminée
utilise un guide et les commandes existantes ; aucun bundle absent n’est présenté
comme téléchargeable ([récupération](../recuperer-resultat.md)).

Les pages déjà visitées restent instanciées : naviguer conserve leur état local,
leurs défilements et leurs formulaires. Les sondages des pages masquées sont
suspendus. Les brouillons de discussion sont isolés par session, en mémoire, et
supprimés par l’oubli local ; ils ne sont pas conservés après fermeture du client.
Un résumé de carte reçu après fermeture ou navigation ne rouvre pas une fenêtre.

## Direction visuelle et ressources

Deux familles indépendantes du mode système : **Pixel Atelier** (Nuit/Jour) et
**Studio** (Graphite/Papier). Elles sont définies dans
`design/tokens/desktop-palettes.json`, générées dans les singletons QML et choisies
sans redémarrage. La famille est mémorisée ; le mode clair/sombre/système et le
mouvement réduit conservent leurs préférences propres. Les palettes Hermes restent
inchangées. Une respiration lumineuse de 3 % sur huit secondes anime le décor ;
elle s’arrête en mouvement réduit, en Studio, hors page visible ou lorsque la
fenêtre est inactive/minimisée. Les transitions de contrôles existantes restent
courtes. Le brief autorise ce décor mesuré et remplace l’ancienne interdiction
générale dans les descriptions de `motion.json`.

L’emblème ACP original est présent dans le shell, l’icône de fenêtre, l’exécutable
Windows et la configuration Inno Setup. Le décor LimeZu est une illustration
d’ambiance, pas une représentation d’agents réellement actifs.

Le script `apps/desktop/tools/import-atelier-assets.ps1` extrait seulement les
sprites employés depuis l’archive fournie. Il n’exécute aucun fichier de celle-ci.
Les dérivés sous licence et leur provenance restent dans `resources/atelier-local/`,
ignoré par Git. Les crédits figurent dans les réglages. Sans import, la compilation
embarque le décor ACP original `resources/images/atelier-fallback.png` : un clone
reste constructible. Les images et l’icône originales ACP sont reproductibles avec
`apps/desktop/tools/generate-atelier-brand.ps1`.

## Besoins et limites de cette livraison

| Besoin | Existant et changement | Preuve / limite |
| --- | --- | --- |
| Retrouver et reprendre les projets | Accueil agrégé et modèle Projets réutilisés dans le nouveau shell | Harness QML natif, aucun projet créé sur le serveur réel |
| Voir le travail et les résultats | Cartes, résumés, résultats et journal existants regroupés en onglets | Tests des actions réelles du client contre serveur local de test |
| Reprendre une consigne | Pages conservées et brouillons par session en mémoire | Test de navigation ; pas de restauration après redémarrage |
| DA et thèmes | Deux familles, quatre variantes, scène LimeZu, icône Windows | Captures réelles Windows, 1280×720 et 1920×1080 |
| Accessibilité et erreurs | Focus natif, clavier, textes serveur en PlainText, erreurs conservées | Tests Qt ; pas d’audit complet par lecteur d’écran |
| Configuration des assistants | Guides Windows/Railway, état observé et demande de vérification | Connexion dans les outils officiels ; pas de connexion personnelle automatisée |
| Agents et sous-agents | Données déjà exposées par Hermes conservées | Aucun nouvel arbre d’agents, outil ou événement inventé |
| Routage explicable et économie | Auto réel, table autorisée, verrous et quotas conservés | Pas de nouveau profil de coût ni estimation de quota inventée |

Ce lot ne termine pas tous les chantiers d’orchestration du brief : le journal
durable des appels d’outils, les missions multiples, la mémoire sourcée et les
artefacts téléchargeables nécessitent des extensions serveur et exécutant dédiées. Aucun serveur concurrent, accès direct aux dépôts de l’exécutant ou
assouplissement de l’authentification n’a été ajouté.

## Références étudiées

Consultées le 12 octobre 2026 : les [panneaux de VS Code](https://code.visualstudio.com/api/ux-guidelines/panel)
réservent les vues de soutien à une zone adaptable ; les [panneaux de Qt Creator](https://doc.qt.io/qtcreator/creator-how-to-show-and-hide-sidebars.html)
présentent les vues pertinentes au contexte ; [Zed](https://zed.dev/docs/ai/parallel-agents)
regroupe les conversations par projet et distingue leur état. Ces observations
confortent la navigation par projet et les inspecteurs contextualisés ; elles
ne fournissent ni code copié ni preuve d’agents actifs dans ACP.

## Vérification locale de l’aperçu initial

Chaîne conservée : Qt 6.8.3, MSVC 2022, C++23, presets et scripts du dépôt.

```powershell
./scripts/build-desktop.ps1 -Configuration Release -QtDir <Qt-6.8.3-msvc2022_64>
./scripts/test-desktop.ps1 -Configuration Release -QtDir <Qt-6.8.3-msvc2022_64>
python -m pytest scripts/tests/test_desktop_palettes.py scripts/tests/test_generer_themes.py scripts/tests/test_check_desktop_layout.py
python apps/desktop/cmake/generate_design_tokens.py --tokens design/tokens --out apps/desktop/qml/theme/generated --check
python scripts/check_engine_frozen.py
```

Les captures du harness `tst_pages_bureau` emploient un serveur local factice et un
stockage isolé. Les noms `Test-fixture-Workspace-*` indiquent les données de test ;
elles ne démontrent aucune connexion personnelle. Sous Windows, les captures
visuelles utilisent `QT_QPA_PLATFORM=windows` et `QT_QUICK_BACKEND=software` : le
backend offscreen de cette installation ne trouve pas les polices système.

Les preuves locales sont conservées sous `apps/desktop/build/verification/pixel-atelier/`
(ignoré par Git). Résultats de l’aperçu initial, avant les ajouts fonctionnels 1.1 :

- compilation Release réussie ; **36/36 suites CTest natives réussies** ;
- **26 tests Python et 464 sous-tests réussis** ; génération des thèmes à jour ;
- captures natives Windows : quatre variantes, 1280×720 et 1920×1080 à l’échelle
  normale ; zéro avertissement QML dans le parcours du harness ;
- parcours natif à 150 % réussi, avec avertissements Windows de redimensionnement
  aux limites du moniteur 1920×1080. Ce passage ne valide pas les grandes tailles
  physiques demandées à 150 %, ni les échelles 125 % et 200 % ;
- `check_engine_frozen.py` et `git diff --check` réussis ;
- `check_layout.py` conserve un constat préexistant : origine `api.github.com`
  d’UpdateService. Les faux positifs de fixtures ont été corrigés et testés ;
- archive portable, installeur Inno Setup et sommes SHA-256 produits avec
  `package-desktop.ps1 -DryRun`, dans `dist/pixel-atelier-preview/`.

Ces binaires sont des **aperçus locaux non signés**, sans publication. Le numéro
1.0.1 de cet aperçu initial ne doit pas être confondu avec les paquets finaux 1.1.0.
L’installeur a été compilé, pas exécuté. Pour essayer sans installation, extraire
l’archive portable et lancer `AgentCompanyPlatform.exe`. Le client emploie les
réglages ACP habituels : fermer l’autre instance avant de le lancer.

Aucun objectif de 60 images/s n’est annoncé : aucun profilage QML ni validation
sur une autre machine n’a été effectué.

## Validation locale de 1.1.0

Les résultats suivants sont établis sur le lot fonctionnel 1.1.0, le 12 octobre
2026. Les journaux sont dans `apps/desktop/build/verification/pixel-atelier/`
(ignoré par Git), distincts des preuves de l’aperçu initial.

| Périmètre exécuté | Résultat local | Journal |
| --- | --- | --- |
| Moteur Pixel Office gelé | **74 tests réussis**, 7 fichiers | `engine-tests-1.1.0.log` |
| Interface web Hermes | **204 tests réussis**, 21 fichiers | `interface-tests-1.1.0.log` |
| Station native Qt | Compilation Release et **36/36 suites CTest réussies**, 102,84 s | `build-routage-final-1.1.0.log`, `desktop-tests-routage-corrige-1.1.0.log` |
| Image Hermes, routage et planification ciblés | **87 tests réussis** | `hermes-routing-1.1.0.log` |
| Image Hermes, observations et routes projet ciblées | **20 tests réussis** | `hermes-observations-1.1.0.log` |
| Contrat P4, exploration, graphe et réclamations distantes | **3 tests réussis**, 373,72 s | `contrats-routage-p4-1.1.0.log` |
| Contrat P6, mise en service et relecture | **2 tests réussis**, 136,58 s | `contrats-routage-p6-1.1.0.log` |
| Contrat P7, redéploiement pendant une question | **1 test réussi**, 176,32 s | `contrats-routage-p7-1.1.0.log` |
| Navigateur P7, parcours téléphone puis bureau | **1 test réussi**, 136,39 s ; `ACP_E2E_OBLIGATOIRE=1` | `navigateur-routage-p7-1.1.0.log` |

Les deux passages routage/planification et observations/routes de l’image Hermes
totalisent **107 tests réussis** ; ils ne constituent pas la suite complète de
cette image. Ils rapportent respectivement
34 et 22 avertissements de dépréciation dans `plugins_manifest.py` de Hermes
(argument `maxsplit` de `re.split` passé par position).

Les fixtures des contrats corrigés configurent la vraie table d’autorisation
propriétaire via les routes authentifiées. Les **6 contrats ciblés** P4, P6 et P7
et le **test navigateur P7** ci-dessus sont réussis. La suite complète Hermes sur
GitHub a depuis réussi sur `5d41008` : [run 38205074960](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205074960).
Les [preuves de livraison](preuves-1.1.0.md) détaillent les compteurs et leurs limites.

Le parcours navigateur utilise de faux comptes et un faux modèle, avec un vrai
Chromium et une véritable identité Authelia jetable. Il n’atteste aucune connexion
personnelle. Ses captures et `releve-parcours.json` sont conservés dans
`captures-navigateur-routage-1.1.0/p7/`. Le nettoyage local a été vérifié : aucun
conteneur, volume ou réseau sous le préfixe `acp-contrat-pixel110-` ; les quatre
tags d’image `acp-pixel110-*` ont été retirés.

Un passage Qt intermédiaire attendait les anciens textes de routage : les
assertions existantes ont été adaptées aux libellés clarifiés, puis les 36 suites
ont réussi en 102,84 s.

Le dernier passage Qt inclut les corrections vérifiées des réponses de formulaire
arrivées hors ordre, de l’annulation des résumés et du défilement des discussions.
La navigation conserve le brouillon ; une molette interrompt le suivi automatique
et l’ouverture d’une autre discussion retrouve ses derniers messages. Les faux
handlers du test de discussion sont restaurés même si une assertion échoue.

Les dernières captures Windows de 1.1.0 sont dans `captures-routage-1.1.0/` :
**24 vues du workspace**, soit Accueil, Projets et Travail dans les quatre variantes
`pixel-dark`, `pixel-light`, `studio-dark`, `studio-light`, chacune en 1280×720 et
1920×1080, ainsi que les pages isolées. Le harness Windows avec rendu logiciel
conclut **3 étapes réussies, aucune ignorée et aucun avertissement en 15,210 s**
(`pages-bureau-routage-1.1.0.log`). Les captures `Routage.png` et
`Projets-nouveau-projet.png` ont été inspectées : leurs aides textuelles sont
lisibles et non tronquées. Ces captures emploient les données du serveur local de
test, pas les comptes personnels du propriétaire. Les limites de l’essai à 150 %
décrites plus haut restent valables ; aucune validation supplémentaire à 125 % ou
200 %, ni aucun audit complet d’accessibilité, n’est revendiqué.

La suite Python finale et les paquets locaux sont documentés ci-dessous. Les workflows
GitHub et la publication restent des validations distinctes ; ni les logs locaux ni
les captures n’attestent une installation, une reconnexion personnelle ou un déploiement
Railway.

Pour l’installation **1.0.1 par utilisateur de Paul**, le
[guide de mise à jour 1.1](../mettre-a-jour-1.1.md) et le
[processus de mise à jour](../desktop-update-process.md) donnent le parcours
compatible : fermer ACP, vérifier le Setup et ses sommes, puis lancer l’installeur
sous le même compte Windows, dans le même mode par utilisateur. Le script Inno
conserve son `AppId` et `PrivilegesRequired=lowest`, avec le dossier par défaut
`%LOCALAPPDATA%\Programs\Agent Company Platform` ; ne pas passer à `/ALLUSERS`
pour cette mise à jour. Les préférences et le coffre Windows restent ceux du même
profil. Cette cohérence documentaire ne vaut pas essai de mise à jour déjà exécuté
sur son installation.

### Paquet local 1.1.0

La chaîne `package-desktop.ps1 -DryRun` a produit le 12 octobre 2026, dans
`dist/pixel-atelier-1.1.0/`, un installeur Inno Setup et une archive portable avec
les DLL Qt et MSVC. Le build local embarque le décor LimeZu licencié ; le paquet CI
public utilise le décor original ACP. Les binaires locaux sont **non signés** et
l'installeur n'a pas été exécuté. Le contrôle Authenticode du Setup donne
`NotSigned`. Le journal de la reconstruction est `package-routage-final-1.1.0.log`
dans le dossier de vérification. Les deux fichiers ont été relus ; leurs tailles
et SHA-256 sont consignés dans `paquets-final-1.1.0.json` :

| Fichier | Taille (octets) | SHA-256 |
| --- | ---: | --- |
| `AgentCompanyPlatform-Setup-1.1.0-x64.exe` | 24659513 | `323c9f34205e20cc5c3c84b553a8d872b443e0b9609deedd1475c10831cd708b` |
| `AgentCompanyPlatform-Portable-1.1.0-x64.zip` | 37628270 | `39e5def65b071dd97b0d5d832867100979f8cfc67aaac4ed68e90ae83a226cde` |

Ces empreintes appartiennent à ce build local uniquement. Elles ne décrivent ni les
anciens aperçus ni les artefacts GitHub fabriqués depuis les sources fusionnées.

### Suite Python finale

Le passage final détaillé `full-python-final-1.1.0.log` conclut : **1 280 tests réussis,
106 ignorés et 464 sous-tests réussis en 1 128,51 s**. Les ignorés concernent les
conditions de plateforme, de conteneur ou de privilèges indiquées par pytest ; ils
ne sont pas comptés comme réussis. Les suites Linux et les images complètes font
l’objet de validations GitHub distinctes, attachées à leur SHA. Le ciblé
runner/proof comporte **49 tests réussis en 69,05 s**
(`python-runner-final-startup-1.1.0.log`). Le budget de démarrage des Python imbriqués
est distinct du budget d'arrêt du produit, inchangé. Les échecs des passages
intermédiaires sont conservés dans leurs journaux ; ils ne servent pas de preuve verte.

### Relecture du parcours de récupération

La relecture finale a fait corriger la clôture des accès Railway dans les guides
(nouveau rappel, sans exécution ni commande de compte copiable) et la résolution
des chemins du bundle et du dossier de revue avant les commandes `git -C`.
Les 36 suites Qt ont été rejouées après ce changement : toutes réussies en 105,18 s.
Les blocs documentaires de contrôle SHA-256, d'import et de création du worktree
ont également été exécutés sous PowerShell 7 et Windows PowerShell 5.1, sur des
dépôts jetables : bundle relatif avec espaces et crochets, clone dans un autre
dossier, tête importée et emplacement du worktree vérifiés. Journaux
`recuperation-chemins-1.1.0.log` et `recuperation-chemins-powershell51-1.1.0.log`.
Aucun SSH, compte fournisseur ou accès Railway réel n'a été utilisé pour cet essai.
