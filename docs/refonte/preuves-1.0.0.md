# Preuves de 1.0.0

**Squelette en préparation**, écrit le 8 octobre 2026 à l'étape P9 (part E), sur `refonte/hermes-p9e`. Il n'est
**pas encore relu** : la relecture indépendante, ligne à ligne contre les sources citées, est prévue avant la PR de
`refonte/hermes` vers `main` ; le document est complété après l'étiquette (fusion, runs sur `main`, `Desktop
Release`). Tant que ce bandeau est là, ce document ne prouve rien par lui-même : il range des preuves déjà publiées
et dit lesquelles manquent.

Conventions :
- **lieu** : *local* (poste de travail Windows, ou banc local), *CI* (GitHub Actions du dépôt public), *Railway*
  (rien n'y est déployé au 8 octobre 2026) ;
- **à relever** : preuve attendue, pas encore produite, ou produite par une part encore ouverte et pas encore
  arrêtée ; aucune valeur n'est mise à sa place ;
- chaque nombre vient d'une source citée : notes de reprise et journal des changements recopiés dans
  [historique.md](historique.md) (« B, § n » : partie B ; « C, P n » : partie C), journal de P9 (brouillon de
  session, non versionné) ou `gh` (PR et runs, relevés le 8 octobre 2026).

Sommaire : § 1 étapes fusionnées · § 2 relevés par étape · § 3 étape P9 · § 4 publication · § 5 non prouvé.

---

## 1. Étapes fusionnées dans `refonte/hermes`

Runs de la PR : vérifications de la tête de la PR (`gh pr view <n> --json statusCheckRollup`). Runs de la fusion :
workflows déclenchés par le push du commit de fusion sur `refonte/hermes` (`gh run list --branch refonte/hermes`).
Tous verts, sauf mention.

| Étape | PR | Tête de la PR | Runs de la PR | Fusion | Runs de la fusion |
|---|---|---|---|---|---|
| P0 | #13 | `b8f55d2` | CI `36017128209`, `36018143912` ; Desktop CI `36017128107`, `36018143728` | `29c95b5`, 25/09/2026 | Desktop CI `36071485618` ; CI `36071485637` **annulée** (aucun run vert de CI sur ce commit) |
| P1 | #14 | `d76d021` | CI `36039794414` ; Image Hermes `36039794517` | `21d13ee`, 25/09/2026 | CI `36071527007` ; Image Hermes `36071527039` |
| P2 | #15 | `120b15c` | CI `36106167277`, `36108333970` ; Image Hermes `36108333899` | `21ac337`, 27/09/2026 | CI `36276361863` ; Image Hermes `36276361866` |
| P3 | #16 | `e5e8032` | CI `36153585709` | `f59f384`, 27/09/2026 | CI `36276381120` ; Image Hermes `36276381102` |
| P4 | #17 | `4419915` | CI `36263127585` ; Image Hermes `36263127567` | `6c31522`, 27/09/2026 | CI `36276392459` ; Image Hermes `36276392425` |
| P5 | #18 | `4f351bc` | CI `36807365648`, `36853018686` ; Image Hermes `36853018700` | `b3faac0`, 01/10/2026 | CI `36857299903` ; Image Hermes `36857299872` |
| P6 | #19 | `69ddab8` | CI `36947828829`, `36957872826` ; Image Hermes `36957872837` ; Image de l'exécutant `36947828939`, `36957872822` | `7697a1c`, 02/10/2026 | CI `36969374167` ; Image Hermes `36969374083` ; Image de l'exécutant `36969374198` |
| P8 | #20 | `efef0d8` | CI `36990645230`, `36990681150` ; Image Hermes `36990645262` ; Image de l'exécutant `36990645130` ; Desktop CI `36990681257` | `b715edb`, 02/10/2026 | CI `36995236395` ; Desktop CI `36995236331` |
| P7 | #21 | `0a1ab98` | CI `37749086751`, `37757254413` ; Image Hermes `37749086760`, `37757254372` ; Image de l'exécutant `37757254309` ; Desktop CI `37757254376` | `b9779f1`, 08/10/2026 | CI `37795932683` ; Image de l'exécutant `37795932983` ; Desktop CI `37795932742` ; Image Hermes `37795932814` (verte, relevée à la fin de la part E de P9) |

Un workflow absent d'une ligne n'a aucun run relevé sur ce commit (filtres de chemins des workflows) ; la CI de
`29c95b5` a été annulée.

## 2. Relevés par étape (preuves publiées)

| Étape | Relecture indépendante | Derniers relevés publiés avant la PR | Source |
|---|---|---|---|
| P0 | 5 défauts confirmés, corrigés | pytest Windows 240 réussis ; Linux (conteneur) 231 réussis, 9 ignorés ; moteur 74 tests ; desktop Debug 25 suites sur 25 ; aucune CI avant la PR (rien n'était poussé) | B, § 4 ; C, P0 |
| P1 | 5 constats, corrigés | Image Hermes `36025999003` (`860fc04`) : 89 dans l'image, 32 au contrat ; CI `36025998703` verte à la deuxième tentative (test temporisé de P0 sous Windows) ; Desktop CI `36026018926` | B, § 5 |
| P2 | 21 constats (trois relectures) | Image Hermes `36098262650` (`fb4c442`) : 216 dans l'image, 99 au contrat, 1 au navigateur ; CI `36098262486` : Windows 279, Linux 270 et 9 ignorés, moteur 74 ; mémoire d'Authelia mesurée (limite 2,5 Gio) | B, § 6 ; C, P2 |
| P3 | 14 constats (4 moyens, 10 bas) | Image Hermes `36136507335` (`ec43987`) : 323 dans l'image, 117 au contrat, 2 au navigateur ; CI `36136507298` : Windows 342, Linux 333 et 9 ignorés, interface 55, moteur 74 | B, § 6 bis et § 6 ter ; C, P3 |
| P4 | 21 constats, tous réels | Image Hermes `36257679694` (`8aeee20`) : 511 dans l'image, 139 au contrat, 6 au navigateur ; CI `36257679667` : Windows 387, Linux 378 et 9 ignorés, interface 93, moteur 74 ; 24 témoins négatifs | B, § 6 quater ; C, P4 |
| P5 | 16 constats (un haut, quatre moyens, onze bas) | côté Hermes : Image Hermes `36271372764` (`0a458cd`) : 619 dans l'image, 150 au contrat, 7 au navigateur ; poste Windows : CI `36284025243` (`4988ba4`) : Windows 592 réussis et 5 ignorés, installeur en simulation 19, Linux 578 réussis et 19 ignorés | B, § 6 quinquies ; C, P5 |
| P6 | 19 constats, plus 3 défauts trouvés en les vérifiant | sur `815ae6f` : CI `36925637152` (Windows 927 et 86 ignorés, Linux 959 et 54 ignorés, interface 120, moteur 74) ; Image de l'exécutant `36925637270` (43 tests de l'image, 777 en root) ; Image Hermes `36925637269` (682 dans l'image, 165 au contrat dont les 7 du bout en bout, 8 au navigateur) | B, § 6 sexies à § 6 nonies ; C, P6 |
| P8 | 16 constats, chacun avec un test qui échoue sans la correction | 34 suites Qt, 0 échec, 0 ignoré (totaux Qt, local) ; Desktop CI verte sur chaque commit poussé, sauf quatre runs annulés par une poussée suivante (dernier relevé : `36987435638`, `1f3696a`) ; bout en bout local contre Authelia et l'image de test | B, § 6 decies ; C, P8 |
| P7 | relecture finale : 37 constats retenus (dont 14 vérifiés par un sceptique) ; 33 corrigés, 3 en limite dite, 1 de procédure | tête réunie `486b285` : CI `37723784897`, Image Hermes `37723784889` (789 dans l'image, 183 au contrat, 10 au navigateur), Image de l'exécutant `37723784888` (823 en root), Desktop CI `37723784893` (34 suites) ; relecture finale : Image Hermes verte sur `87102af` et `cd4c3e6` (798, 183, 10), **rouge** sur `a16f00b` (course du test, corrigée par `201066e`) ; runs de la tête de la PR : § 1 | B, § 6 undecies ; C, P7 |

## 3. Étape P9 (exigences du plan → preuve)

Exigences du plan validé pour P9 ([plan](plan.md) § 13, « P9 ») et du cahier de conception de P9 ; décisions D122 à
D155 ([plan](plan.md) § 1). Les parts B et C sont **encore ouvertes** au 8 octobre 2026 : leurs lignes restent
**à relever**, même quand des mesures intermédiaires sont déjà consignées dans le manuel (renvoi donné).

| Exigence | Preuve | Lieu | Commit, run | Résultat |
|---|---|---|---|---|
| Outil de montée de version de Hermes (`scripts/monter_hermes.py` : `verifier`, `ecrire`, `inventaire`, `derniere`) | tests de l'outil (exécuteur injecté) ; `verifier` réel : « Aucun écart » | local + CI | `ff33ea6` (outil) ; relecture : `11276d6` et suivants | fait (journal de P9, part A et relecture) ; suite du dépôt verte à chaque commit |
| Répétition à blanc de la montée sur l'épinglée, à chaque construction (D122) | étape `verifier` d'`image.yml` : « Aucun écart : l'épinglage de v2026.9.24 est reproduit à l'octet près » | CI | `9a4d6ad`, Image Hermes `37004128839` (image 682, contrat 165, navigateur 8) | **vert** ; de nouveau vert sur la tête de la relecture, `2243923` (Image Hermes `37028491959`, CI `37028494538`) |
| Concordance statique de toutes les épingles de Hermes | `scripts/tests/test_epingles_hermes.py` (rouge d'abord : 7 valeurs figées trouvées) | local + CI | `985ea68` | fait (journal de P9, part A) |
| Toute copie versionnée vérifiée par `scripts/check_version.py` | `scripts/tests/test_version_complete.py` (rouge d'abord : verrou de l'interface comparé à rien) | local + CI | `49ee6ef` | fait |
| Décisions à trois chiffres contrôlées (D132) | `scripts/tests/test_decisions_documentees.py` (rouge d'abord) | local + CI | `3c47033` | fait |
| Procédure d'exploitation en français | [exploitation.md](../exploitation.md) ; [railway.md](railway.md) § 4.11 bis, § 9, § 10 d, § 10 g | dépôt | ébauche `80481af`, `c10192d`, `8fa69fb` (CI `37011986945`, `37012625374`, `37013142812`) ; corrections après vérification factuelle (19 constats recoupés) ; mesures de B et C versées (`9ea2b6e`, `e448b7a`) | **à relever** : version finale et relecture, après la fin des parts B et C |
| Test de restauration ; identité des données (R1, R2 : trois volumes au même instant et à des instants différents) | job `restauration` d'`image.yml` | CI (D134) | **à relever** | **à relever** (mesures intermédiaires : [exploitation.md](../exploitation.md) § 4 et § 10) |
| « Sessions et cartes relues » après restauration ; reconnexion du propriétaire (R3) | R1 et R4 (lectures, travail repris) ; R3 au navigateur | CI | **à relever** | **à relever** |
| Restauration de Hermes depuis son propre export (R4) | job `restauration` | CI | **à relever** | **à relever** (geste mesuré : D137) |
| Témoins de mutation des tests de restauration (D140) | branches jetables, runs rouges pour la bonne raison | CI | **à relever** | **à relever** |
| Montée de version répétée ; `hermes plugins compat` et contrat verts, ou écart documenté | témoin `v2026.9.21` (job `temoin`, tableau des écarts) et son contrôle sur `v2026.9.24` | CI (D141) | **à relever** | **à relever** (relevé intermédiaire : [exploitation.md](../exploitation.md) § 6.6) |
| Montée de données d'une version d'ACP à la suivante (« migration de schéma : oui », lignes d'avant identiques, travail repris) | job `montee`, `ref_avant` = fin de P8 | CI (D148) | **à relever** | **à relever** (relevé intermédiaire : [exploitation.md](../exploitation.md) § 6.6) |
| Restauration « dans un environnement Railway jetable » | remplacée par la répétition en production avant données (D124) | Railway | procédure écrite ([exploitation.md](../exploitation.md) § 5) | **non prouvé** : geste du propriétaire, après le premier déploiement |
| « Reconnexion openai-codex nécessaire, constatée et documentée » | constat c de la répétition de restauration | Railway | — | **non prouvé** tant que la répétition n'a pas eu lieu |
| « Dans un environnement éphémère (identifiant propre) » | remplacé par la porte de CI, la sauvegarde manuelle et le retour arrière (D123) | — | décision écrite | décision, sans preuve d'exécution |
| Documentation finale (README, `CLAUDE.md`, notes de reprise remises à plat, historique figé, ce document) | relecture indépendante | dépôt | part E, `refonte/hermes-p9e` : `bdd0f3d` (décisions D122 à D155), `4a46022` (historique), `6b37aa2` (ce document), `478f065` (notes de reprise), `81a349a` (README, `CLAUDE.md`), `611cc58` (journal 1.0.0 préparé) ; CI verte sur `bdd0f3d`, `4a46022`, `6b37aa2` et `478f065` (`37798492510`, `37799420440`, `37800504780`, `37801841085`) | **à relever** : relecture indépendante, puis mise à jour après la fin des parts B et C |
| Relecture indépendante de toute P9 | constats et traitement | dépôt | — | **à relever** |
| Commit d'ouverture 1.0.0 (D129), journal 1.0.0 complet | `chore(release): open 1.0.0`, `chore(release): prepare 1.0.0 changelog` | dépôt | — | **à relever** (`VERSION` : 0.11.0 au 8 octobre 2026 ; section 1.0.0 du journal préparée, non datée : `611cc58`) |
| PR de P9 vers `refonte/hermes`, quatre workflows verts, fusion | — | CI | — | **à relever** |
| Pixel Office et Godot hors périmètre | `scripts/check_engine_frozen.py` vert ; aucune ligne sous `packages/pixel-office-engine` | CI | chaque run de `ci.yml` | vérifié à chaque push (dernier relevé de cette branche : **à relever** à la fin de la part E) |

## 4. Publication (après l'accord du propriétaire)

| Exigence | Preuve attendue | Résultat |
|---|---|---|
| PR de `refonte/hermes` vers `main`, quatre workflows verts (CI, Image Hermes avec ses jobs, Image de l'exécutant, Desktop CI) | identifiants des runs de la PR | **à relever** |
| `git diff --check origin/main...origin/refonte/hermes` vide ; balayage des secrets sur la plage | sorties des deux commandes | **à relever** |
| Fusion par commit de fusion sur la tête testée | `M^1` = ancienne tête de `main`, `M^2` = tête testée, arbre fusionné = arbre testé | **à relever** |
| `git rev-parse v1.0.0^{commit}` = commit de fusion ; `VERSION` = 1.0.0 | sorties des commandes | **à relever** |
| Workflows sur `main` après la fusion | identifiants | **à relever** |
| Premier run de `Desktop Release` (brouillon non signé, D131) | identifiant du run, état du brouillon | **à relever** |

## 5. Non prouvé (dit)

État au 8 octobre 2026 ; détail : [exploitation.md](../exploitation.md) § 10, [railway.md](railway.md) § 12 et
§ 14.7, [desktop.md](desktop.md).
- **Rien n'est déployé sur Railway** : tout ce qui ne se constate que sur Railway (PID 1 et bord réels, cookies
  `Secure` et `trusted_proxies`, clés non documentées de l'IaC, sonde R0 et régime de l'exécutant, sauvegardes
  réelles et leur atomicité, contradiction de la documentation sur les sauvegardes postérieures, reconnexion
  d'openai-codex, notification réelle, parcours téléphone réel, premier dépôt réel, bilan à 8 h, coût réel).
- La répétition de restauration en production et les reconnexions réelles ; la chaîne complète export chiffré →
  déchiffrement → import sur Railway (prouvée par morceaux).
- La station Qt après une restauration de l'identité (même règle que le navigateur, non rejouée) ; la station Qt
  face aux gestes et au flux de P7.
- Une montée de Hermes vers une release future ; la montée d'Authelia ; un retour arrière par Rollback ; un vrai agent
  à la place de l'agent factice.
- Le premier run de `Desktop Release` tant que l'étiquette n'est pas posée ; un installeur réel sur un Windows
  propre ; binaires **non signés** (aucun certificat).
- `preserve()` sur une variable jamais posée : supposé sans effet (D116).
- **Constat intermittent, à instruire avant la publication** : Image Hermes `37784838264` (`fdb41c9`), tentative 1,
  job `113336818423` rouge sur `hermes/tests/contrat/test_sans_shell_contrat.py::test_volume_piege_apres_relance` :
  après le redémarrage du conteneur sur un volume piégé, la session du tableau de bord (`/api/ws`) listait `terminal`,
  `write_file`, `execute_code`… (les jeux posés par le `.env` piégé), alors que l'api_server répondait « Tool
  'terminal' does not exist » ; deuxième des trois couches de la défense de P2 ([image.md](image.md) § 5, épingles du
  `.env` géré) vue en défaut **une fois**. Tentative 2 verte, comme ce test dans les autres runs relevés pendant P9.
  Non reproduit, non expliqué, non corrigé ; la garde `pre_tool_call` (troisième couche) n'a pas été mesurée pour
  cette session dans ce run.
