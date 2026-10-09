# Preuves de 1.0.0

État du **9 octobre 2026**, fin de l'étape P9, sur `refonte/hermes-p9`. Écrit à la part E (8 octobre 2026,
`refonte/hermes-p9e`), complété le 9 octobre 2026 par les preuves des parts B et C, du correctif SECU-TUI et de la
station P8b, après la réunion des branches, puis corrigé après la relecture indépendante de toute P9 (§ 3). Les deux
derniers commits de P9 (ouverture de 1.0.0, journal daté), la PR de P9 et la publication (fusion, runs sur `main`,
`Desktop Release`) sont relevés par la PR de documentation d'après l'étiquette (§ 3 et § 4, D163). Ce document ne prouve rien par
lui-même : il range des preuves publiées (runs de la CI du dépôt public, commits) et dit lesquelles manquent.

Conventions :
- **lieu** : *local* (poste de travail Windows, ou banc local sans Docker), *local (Docker)* (piles Docker du poste
  de travail, de nouveau permises depuis le 9 octobre 2026 : D160 ; preuve d'appoint), *CI* (GitHub Actions du dépôt
  public : la preuve qui fait foi), *Railway* (rien n'y est déployé au 9 octobre 2026) ;
- **date** : jour, à l'heure de Paris, des runs cités (`gh run view <id> --json createdAt`) ou, sans run, des commits
  cités ; au § 1, la date de chaque fusion ;
- **à relever** : preuve d'une étape à venir (ouverture 1.0.0, PR de P9, PR vers `main`, étiquette), dite comme
  telle ; aucune valeur n'est mise à sa place ;
- chaque nombre vient d'une source citée : notes de reprise et journal des changements recopiés dans
  [historique.md](historique.md) (« B, § n » : partie B ; « C, P n » : partie C), journaux des corrections de P7, de
  P8b, de SECU-TUI et de P9 (brouillon de session, non versionné) ou `gh` (PR et runs, relevés les 8 et 9 octobre
  2026 ; conclusions par `gh run view` et par l'API des jobs ; compteurs lus dans le journal du run, ou celui du job
  par l'API des jobs) ; « job » désigne l'identifiant d'un job de l'API.

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
| SECU-TUI (correctif de sécurité, D156 et D157) | #23 | `6a37a8c` | CI `37882628793` (Windows 1 011 et 87 ignorés, Linux 1 044 et 54 ignorés, interface 203, moteur 74), `37877696357` ; Image Hermes `37882628800` (846 dans l'image, 191 au contrat, 10 au navigateur) | `5026a70`, 09/10/2026 | CI `37894912135` ; Image Hermes `37894912140` (846 dans l'image, 191 au contrat, 10 au navigateur) |
| P8b (station alignée sur P7, D158 et D159) | #22 | `afcb8b3` | CI `37894932818` (Windows 1 011 et 87 ignorés, Linux 1 044 et 54 ignorés, interface 203, moteur 74), `37894929143` ; Image Hermes `37894932956` (846 dans l'image, 191 au contrat, 10 au navigateur), `37894929205` ; Desktop CI `37894932850` (36 suites CTest sur 36) | `8583642`, 09/10/2026 | CI `37900882829` ; Desktop CI `37900882827` ; Image Hermes `37900882826` (846 dans l'image, 191 au contrat, 10 au navigateur) |

Un workflow absent d'une ligne n'a aucun run relevé sur ce commit (filtres de chemins des workflows) ; la CI de
`29c95b5` a été annulée. Les arbres des commits de fusion de SECU-TUI et de P8b sont identiques à ceux de leurs têtes
testées (`git rev-parse <commit>^{tree}`).

## 2. Relevés par étape (preuves publiées)

Pour chaque étape, le **dernier** relevé publié sur sa branche avant l'ouverture de sa PR, donc après les
corrections de sa relecture indépendante. Entre ce relevé et la tête de la PR, seuls des commits de documentation
(P4 : plus un commentaire d'`image.yml` ; P8 : plus la fusion de P6 dans sa branche ; P8b : plus la fusion du
correctif SECU-TUI, `5026a70`, par `afcb8b3`, qui apporte du code et des tests, dont les runs de la tête sont au
§ 1) ; les runs de la tête de la PR sont au § 1, et leurs compteurs, quand
ils sont donnés ici, sont lus par `gh` (« relevé par `gh` »). Les relevés antérieurs restent dans la source citée.

| Étape | Relecture indépendante | Derniers relevés avant la PR | Date | Source |
|---|---|---|---|---|
| P0 | 5 défauts confirmés, corrigés | local, sur `ce91bbb` (après les corrections) : pytest Windows 240 réussis ; Linux (conteneur) 231 réussis, 9 ignorés ; moteur 74 tests ; desktop Debug 25 suites sur 25 ; CI : aucune dans les notes, écrites avant le push ; tête `b8f55d2`, poussée avant l'ouverture de la PR : CI `36017128209` (Windows 240, Linux 231 et 9 ignorés, moteur 74) et Desktop CI `36017128107` (25 tests CTest sur 25), relevés par `gh` | 24/09/2026 | B, § 4 ; C, P0 ; `gh` |
| P1 | 5 constats : 4 corrigés, 1 en limite dite (port 9119 pris sous le même uid, non corrigeable en P1, paré depuis P2 par l'absence d'outil d'exécution) ; plus l'élévation par le `PATH`, trouvée à la vérification finale et corrigée | local, après les corrections : 108 dans l'image, 37 au contrat ; tête de la PR `d76d021` : Image Hermes `36039794517` (108 dans l'image, 37 au contrat) et CI `36039794414` (Windows 240, Linux 231 et 9 ignorés, moteur 74), relevés par `gh` | 24/09/2026 | B, § 5 ; `gh` |
| P2 | 21 constats (trois relectures), tous réels ; deux traités par la documentation seule (`vision_analyze`, gardé par décision du propriétaire ; sauvegardes absentes de l'IaC) | sommet des corrections `5e77686` : Image Hermes `36104820150` : 242 dans l'image, 103 au contrat, 1 au navigateur ; mémoire d'Authelia 1,287 Gio à 20 (51,5 % de la limite de 2,5 Gio) ; CI `36104820007` : Windows 282, Linux 273 et 9 ignorés, moteur 74 ; puis CI `36105959556` (`d391158`, documentation seule) **rouge** : 2 tests Windows sur 282, échecs de création ou de nettoyage de processus sur le runner, non relancé ; tête de la PR `120b15c` : CI `36106167277` verte (Windows 282, Linux 273 et 9 ignorés, relevé par `gh`) | 25/09/2026 | B, § 6 (relecture) ; C, P2 ; `gh` |
| P3 | 14 constats (4 moyens, 10 bas) | sommet des corrections `0334320` : Image Hermes `36150973272` : 326 dans l'image, 118 au contrat, 5 au navigateur ; CI `36150973461` : Windows 368, Linux 359 et 9 ignorés, interface 55, moteur 74, balayage des secrets sans motif | 25/09/2026 | B, § 6 ter (relecture) ; C, P3 |
| P4 | 21 constats, tous réels | Image Hermes `36257679694` (`8aeee20`) : 511 dans l'image, 139 au contrat, 6 au navigateur ; CI `36257679667` : Windows 387, Linux 378 et 9 ignorés, interface 93, moteur 74 ; 24 témoins négatifs | 26/09/2026 | B, § 6 quater ; C, P4 |
| P5 | 16 constats (un haut, quatre moyens, onze bas) | après les corrections (1er octobre 2026) : Image Hermes `36803742778` (`c5cb6dc`, dernier état de `hermes/` et de l'interface) : 629 dans l'image, 150 au contrat, 7 au navigateur ; CI `36803850929` (`a6b62ff`) : Windows 616 réussis et 6 ignorés, installeur en simulation 56 vérifications, Linux 602 réussis et 20 ignorés, interface 112, moteur 74 | 01/10/2026 | B, § 6 quinquies (relecture) ; [poste.md](poste.md) § 26 ; C, P5 |
| P6 | 19 constats, plus 3 défauts trouvés en les vérifiant | sur `815ae6f` : CI `36925637152` (Windows 927 et 86 ignorés, Linux 959 et 54 ignorés, interface 120, moteur 74) ; Image de l'exécutant `36925637270` (43 tests de l'image, 777 en root) ; Image Hermes `36925637269` (682 dans l'image, 165 au contrat dont les 7 du bout en bout, 8 au navigateur) | 01/10/2026 | B, § 6 sexies à § 6 nonies ; C, P6 |
| P8 | 16 constats, chacun avec un test qui échoue sans la correction | 34 suites Qt, 0 échec, 0 ignoré (totaux Qt, local) ; Desktop CI verte sur chaque commit poussé, sauf quatre runs annulés par une poussée suivante (dernier relevé : `36987435638`, `1f3696a`) ; bout en bout local contre Authelia et l'image de test | 02/10/2026 | B, § 6 decies ; C, P8 |
| P7 | relecture finale : 37 constats retenus (dont 14 vérifiés par un sceptique) ; 33 corrigés, 3 en limite dite, 1 de procédure | tête de la PR `0a1ab98` : CI `37749086751` (Windows 1 011 et 87 ignorés, Linux 1 044 et 54 ignorés, Vitest 203, moteur 74) ; Image Hermes `37749086760` (798 dans l'image, 183 au contrat, 10 au navigateur) ; Image de l'exécutant `37749096235` (43 tests de l'image, 831 en root) ; Desktop CI `37749099809` (34 suites) ; juste avant, Image Hermes **rouge** sur `a16f00b` (`37742327967` : course du test, corrigée par `201066e`) | 08/10/2026 | B, § 6 undecies ; C, P7 ; journal des corrections de P7 |
| SECU-TUI | contre-vérification d'un sceptique (failles traitées par D156 et D157 ; l'écriture d'une clé épinglée par `PUT /api/env`, en partie réfutée par la mesure : Hermes la refuse) et audit défensif du 9 octobre 2026 (variables d'emplacement et d'exécution comme `HERMES_HOME`, lecture des `.env` comme Hermes : deux manques prouvés rouges, corrigés) | rouge d'abord, puis vert, sur des branches jetables : tests seuls `4c3647e` sur le code de P7, run `37831355746` **rouge attendu** (dans l'image 12 échecs et 1 réussi, au contrat 3 échecs et 2 réussis) ; correctif SECU-1 et SECU-2 `373b047`, run `37832691849` **vert** (834 dans l'image, 64 au contrat) ; audit : tests seuls `e5e3f3c`, run `37873430373` **rouge attendu** (dans l'image 7 échecs et 240 réussis, au contrat 3 échecs et 2 réussis) ; correctif `2c4e2d4`, run `37873804340` **vert** (846 dans l'image, 68 au contrat) ; tête de la branche `6a37a8c` : CI `37877696357`, Image Hermes `37877723138` (846 dans l'image, 191 au contrat, 10 au navigateur), relevés par `gh` | 08/10/2026 et 09/10/2026 | [image.md](image.md) § 4.3 bis, § 4.3 ter, § 9 et § 10 ; journal de SECU-TUI ; `gh` |
| P8b | deux relectures, 12 constats (desktop-1 à desktop-12), chacun vérifié dans le code puis traité ; les constats de code avec un test relevé rouge sans la correction | totaux Qt locaux sur `ac31836` : 36 suites, 513 réussis, 0 échec, 0 ignoré ; Desktop CI `37876255274` (36 suites CTest sur 36) et CI `37876255273` (Windows 1 011 et 87 ignorés, Linux 1 044 et 54 ignorés, interface 203, moteur 74) ; documentation `9adc706` : CI `37876926305`, Desktop CI `37876937821` (lancée à la main, 36 sur 36) | 09/10/2026 | [desktop.md](desktop.md), « P8b » ; journal de P8b ; `gh` |

## 3. Étape P9 (exigences du plan → preuve)

Exigences du plan validé pour P9 ([plan](plan.md) § 13, « P9 ») et du cahier de conception de P9 ; décisions D122 à
D155 et D160 à D163 ([plan](plan.md) § 1). Les parts A à E sont closes au 9 octobre 2026 ; les lignes **à relever** sont
celles d'étapes à venir. Restauration et montée : chaque vérification des quatre fichiers de test (R1 et R2, R3, R4,
montée de données), vue rouge pour sa raison ou non, avec la raison, est rangée dans
[exploitation.md](../exploitation.md) § 6.6 et § 10, d'après un inventaire mécanique de ces fichiers (journal de P9) :
63 vues rouges, 12 impossibles à rendre rouges seules (raison écrite), 6 jamais montrées, 5 mesures non exigées,
72 préconditions, 9 outils et 4 appels de contrôles partagés. Les fichiers de test n'ont pas changé depuis cet
inventaire (`83394a9`).

| Exigence | Preuve | Lieu | Date | Commit, run | Résultat |
|---|---|---|---|---|---|
| Outil de montée de version de Hermes (`scripts/monter_hermes.py` : `verifier`, `ecrire`, `inventaire`, `derniere`) | tests de l'outil (exécuteur injecté) ; `verifier` réel : « Aucun écart » ; `derniere` réel : « Aucune release plus récente que celle épinglée » | local + CI | 02/10/2026 ; `derniere` aussi le 09/10/2026 | `ff33ea6` (outil) ; relecture : `11276d6` et suivants ; relecture finale : `6ee8871` | fait (journal de P9, part A et relecture) ; suite du dépôt verte à chaque commit, sauf `cdc8593` : CI `37016933709` **rouge** (test instable `apps/poste/tests/contrat/test_enrolement.py:78`, § 5), non relancée. `derniere` réel du 9 octobre 2026 **faux** : « Aucune release plus récente que celle épinglée », alors que v0.21.6 était publiée depuis la veille (filtre sur la seule forme `vAAAA.M.J`) ; corrigé par `6ee8871` (11 tests rouges d'abord : formes `vAAAA.M.J[.N]` et `vX.Y.Z`, candidates et canaris écartés, forme inconnue publiée refusée), puis relevé réel : « Dernière release publiée (git et Docker Hub) : v0.21.6 », « Une release plus récente existe » ; `verifier --etiquette v0.21.6` (local, Docker) : **refus**, l'image n'est pas construite depuis le commit de l'étiquette (D161) |
| Répétition à blanc de la montée sur l'épinglée, à chaque construction (D122) | étape `verifier` d'`image.yml` : « Aucun écart : l'épinglage de v2026.9.24 est reproduit à l'octet près » | CI | 02/10/2026 ; 09/10/2026 | `9a4d6ad`, Image Hermes `37004128839` (image 682, contrat 165, navigateur 8) ; `2243923`, Image Hermes `37028491959` ; tête réunie `90102b1`, Image Hermes `37908787791`, job `113768708907` | **vert** à chaque construction relevée |
| Concordance statique de toutes les épingles de Hermes | `scripts/tests/test_epingles_hermes.py` (rouge d'abord : 7 valeurs figées trouvées) | local + CI | 02/10/2026 | `985ea68` | fait (journal de P9, part A) |
| Toute copie versionnée vérifiée par `scripts/check_version.py` | `scripts/tests/test_version_complete.py` (rouge d'abord : verrou de l'interface comparé à rien) | local + CI | 02/10/2026 | `49ee6ef` | fait |
| Décisions à trois chiffres contrôlées (D132) | `scripts/tests/test_decisions_documentees.py` (rouge d'abord) | local + CI | 02/10/2026 | `3c47033` | fait |
| Procédure d'exploitation en français | [exploitation.md](../exploitation.md) ; [railway.md](railway.md) § 4.11 bis, § 9, § 10 d, § 10 g et § 12 | dépôt | 02/10/2026 (ébauche) ; 08/10/2026 (mesures de B et C) ; 09/10/2026 (relevé complet des témoins, réunion, version finale) | ébauche `80481af`, `c10192d`, `8fa69fb` (CI `37011986945`, `37012625374`, `37013142812`) ; vérification factuelle, 19 constats recoupés et corrigés : `2243923` ; mesures de B et C : `d34b7a7`, `9ea2b6e`, `e448b7a`, `58f3a31`, `5107934`, `b6f2ada` ; réunion avec SECU-TUI : `05c6686`, `f613873` ; version finale : `83c0467` (avec [railway.md](railway.md) § 12) | fait ; chaque statut tranché (vérifié, mesuré avec sa preuve, supposé, ou sur Railway seulement) ; relecture de la version finale : faite avec celle de toute P9 (ligne « Relecture indépendante de toute P9 ») |
| Test de restauration ; identité des données (R1 : trois volumes restaurés au même instant ; R2 : à des instants différents) | job `restauration` d'`image.yml` : couches 1 (octets) et 2 (contenu des bases), lectures par l'API, cartes et jetons de l'exécutant, marqueurs postérieurs absents, travail repris ; R2 : règle d'ordre mesurée (D136) | CI (D125) ; local (Docker, D160) | 08/10/2026 ; 09/10/2026 | premier passage `d34b7a7`, run `37760142007`, job `113254280526` **rouge** (5 échecs, 8 réussis : quatre défauts des tests, corrigés par `916a4f0`, `46cc13e`, `bdbe930` et `b8b64b4` ; R3 ensuite par `59c793e` et `27d2123`) ; premier vert `27d2123`, run `37768789724`, job `113282884939` (13 réussis, 184 désélectionnés) ; tests enrichis, verts : `58f3a31` (`37827848241`, job `113485190650`), `8e58ac9` (`37831745518`, job `113498563899`), `83394a9` (`37843294142`, job `113537817083` : 13 réussis, 190 désélectionnés) ; après la réunion de P9 avec SECU-TUI et P8b, `90102b1` : run `37908787791`, job `113748621950` (13 réussis, 198 désélectionnés) ; en local (Docker), sur l'arbre de `90102b1` : R1, R2 et R4, 13 réussis | **vert** ; mesures : [exploitation.md](../exploitation.md) § 4 ; limites : § 10 |
| « Sessions et cartes relues » après restauration ; reconnexion du propriétaire (R3) | R1 et R4 : sessions, cartes de l'exécutant (`acp-poste cartes`) et cartes des projets relues par l'API ; R3 dans un navigateur : jeton d'accès d'avant accepté, 400 d'Authelia au jeton de rafraîchissement tourné, renvoi à la connexion sans 503, passkey d'avant acceptée, passkey d'après refusée | CI | 08/10/2026 ; 09/10/2026 | R3 mesuré en entier pour la première fois : `59c793e`, run `37766187654` (rouge pour un défaut du test, corrigé par `27d2123`) ; vert : `37768789724` (1 réussi) et chaque run de la ligne précédente ; tête réunie : job `113748621950` (R3 1 réussi) | **vert** ; consigne de reconnexion écrite d'après R3 et exigée par le test (D138) ; reconnexion d'openai-codex : **non prouvé** (Railway) |
| Restauration de Hermes depuis son propre export (R4) | job `restauration` : export de 402 fichiers, inventaire de l'archive, import sur un volume neuf vide et à root (`volume-nocopy`), démarrage, lectures égales, travail repris | CI ; local (Docker, D160) | 08/10/2026 ; 09/10/2026 | geste du cahier mesuré **en échec silencieux** (code 0, 0 restauré, 400 ignorés) dès le premier passage (`37760142007`, pris alors pour un succès : défaut du test corrigé par `bdbe930`) ; forme retenue (D137), mesurée complète dès `37763664941` : `chown 10000:10000 /opt/data`, import, 400 restaurés et 2 gardés = 402 ; démarrage refusé puis accepté après le retrait du script du bilan ; vert dans les runs de la ligne « Test de restauration » | **vert** (geste mesuré : D137) |
| Témoins de mutation des tests de restauration (D140) | branches jetables, une mutation ciblée par fonction de test et par branche, supprimées ensuite ; chaque run vu rouge pour sa raison | CI | 08/10/2026 ; 09/10/2026 | 20 runs, jobs « restauration » tous en échec : `37768810187`, `37768815524`, `37768823436`, `37771453643`, `37827864047` (run annulé après le relevé de son job `113485245964`, en échec), `37827867735`, `37843377826`, `37843382904`, `37843389881`, `37843394067`, `37843400261`, `37843405627`, `37843412029`, `37873903805`, `37873907527`, `37873911870`, `37873919895`, `37873923797`, `37874263493`, `37875859984` | **fait** ; jamais montrées rouges : dans R4, la forme d'import sans `hermes update` et la réponse de la route de reprise ; impossibles seules, champs jamais altérés seuls et préconditions : [exploitation.md](../exploitation.md) § 10 |
| Montée de version répétée ; `hermes plugins compat` et contrat verts, ou écart documenté | témoin `v2026.9.21` (job `temoin`, tableau des écarts) et son contrôle sur `v2026.9.24` ; station Qt sur l'épinglage 9.21 | CI (D141) ; local (station, D145) | 08/10/2026 | `54a5632` : run `37769347253`, job `113284760187` **rouge attendu** (« Verdict : 5 écart(s) ou anomalie(s) sur 16 contrôles comptés ») ; contrôle : run `37769357764`, job `113284791411` **vert** (« Verdict : aucun écart : les 16 contrôles comptés ont réussi ») ; les deux runs sont rouges par leur job « restauration » (tests R1 à R4 d'avant leurs corrections) ; station Qt : 33 suites sur 34 | **écarts documentés** ([exploitation.md](../exploitation.md) § 6.6) : borne `requires_hermes`, image d'ACP qui ne démarre pas sur 0.21.4, contrat de 219 méthodes ; la seule différence que rien n'attrapait (`config.yaml` sans `_config_version`) est attrapée par un test nouveau (`d07753b`) |
| Montée de données d'une version d'ACP à la suivante (« migration de schéma : oui », lignes d'avant identiques, travail repris) | job `montee` (`ref_avant`), comparaison ligne à ligne de chaque base contre un contrôle | CI (D148) | 08/10/2026 ; 09/10/2026 | `ref_avant=b715edb` (fin de P8, schéma 3) : `711eb61`, run `37780726989` **rouge** (travail en cours à l'arrêt : D150) ; `70fc372`, run `37782764948`, job `113329768783` **rouge** sur un défaut réel (compteur `AUTOINCREMENT` ramené de 7 à 5), corrigé par `fdb41c9` (D153) ; `fdb41c9`, run `37784839347`, job `113336832227` **vert** (6 réussis, 197 désélectionnés, « migration de schéma : oui ») ; `8e58ac9`, run `37831896582`, job `113499085619` **vert** (exécutant d'après revu par Hermes) ; après la réunion, `90102b1` : run `37908841650`, job `113748806867` (6 réussis, 205 désélectionnés, « oui », 3 → 4) et, `ref_avant=8583642` (tête de la branche déployée), run `37908855369`, job `113748851939` (6 réussis, « non ») ; test d'image du compteur rouge sur le code d'avant le correctif (`37827867735`, job `113485259873`, « 2 == 4 ») | **vert** ; détail : [exploitation.md](../exploitation.md) § 6.6 |
| Témoins de mutation de la montée de données (D155) | branches jetables, supprimées ensuite : une hors `refonte/**` (`essai/p9c-montee-mutation`, run `37782832188`), puis douze `refonte/hermes-jetable-p9bc-mut-*`, **écart à D155** : leurs pushes ont lancé CI (verte ou annulée) et Image Hermes (annulée, ou rouge et retenue comme témoin de restauration, D140 : `37827864047`, `37843377826`, `37843382904`, `37843389881`) ; chaque run vu rouge pour sa raison | CI | 08/10/2026 ; 09/10/2026 | 13 runs, jobs « montee » tous en échec : `37782832188`, `37827971930`, `37827976940`, `37827981834`, `37827986497`, `37831900759`, `37831905352`, `37831910158`, `37843421400`, `37843424899`, `37843429082`, `37873974079`, `37874288049` | **fait** ; jamais montrées rouges : la version de schéma relue après la montée, « contrôle mesuré » (raisonné), et, dans ce fichier, « requêtes GET ou HEAD seulement » et « aucun chemin receive-pack » (vus rouges dans le test de restauration) : [exploitation.md](../exploitation.md) § 6.6 |
| Runs de la tête de `refonte/hermes-p9` après la réunion des branches | quatre workflows sur la tête poussée, et la montée de données | CI | 09/10/2026 | `90102b1` : CI `37908787830` (Windows 1 171 réussis et 87 ignorés, Linux 1 204 et 54 ignorés, interface 203, moteur 74, aucun motif de secret) ; Image de l'exécutant `37908787759` (43 tests de l'image, 831 réussis et 20 ignorés en root) ; Desktop CI `37908787797` (36 suites CTest sur 36) ; Image Hermes `37908787791` : job « restauration » vert à la 1re tentative, job « image » **rouge à la 1re tentative** (job `113748621786` : 874 dans l'image, 192 au contrat, navigateur 1 échec et 9 réussis, `test_connexion_navigateur.py::test_connexion_complete_rafraichissement_et_refus`, « Execution context was destroyed ») puis **vert à la 2e** (job `113768708907` : 874, 192, 10, « Aucun écart ») ; montées de la ligne précédente ; `f613873` (documentation) : CI `37911451671`, mêmes compteurs | **vert**, avec une relance dite : course du test avec la relecture périodique du tableau de bord de Hermes, qui renvoie la page à la connexion après la déconnexion (source épinglée de Hermes, `web/src/hooks/useSidebarStatus.ts`, `web/src/lib/api.ts`) ; test inchangé, non corrigé ; runs des têtes suivantes : avec la PR de P9 |
| Suites locales sur Docker, une pile à la fois (D160) | images construites depuis le worktree de la réunion ; préfixe `acp-contrat-p9f-`, aucune ressource restante | local (Docker) | 09/10/2026 | arbre de `90102b1` : pytest dans l'image 874 réussis ; contrat de sécurité (`test_sans_shell_contrat.py`, `test_contrat_image.py`) 68 réussis ; contrat de restauration (R1, R2, R4) 13 réussis ; R3 non lancé (Playwright absent du venv) | vert ; preuve d'appoint, la CI fait foi |
| Restauration « dans un environnement Railway jetable » | remplacée par la répétition en production avant données (D124) | Railway | — | procédure écrite ([exploitation.md](../exploitation.md) § 5) | **non prouvé** : geste du propriétaire, après le premier déploiement |
| « Reconnexion openai-codex nécessaire, constatée et documentée » | constat c de la répétition de restauration | Railway | — | — | **non prouvé** tant que la répétition n'a pas eu lieu |
| « Dans un environnement éphémère (identifiant propre) » | remplacé par la porte de CI, la sauvegarde manuelle et le retour arrière (D123) | — | — | décision écrite | décision, sans preuve d'exécution |
| Documentation finale (README, `CLAUDE.md`, notes de reprise remises à plat, historique, ce document) | relecture indépendante | dépôt | 08/10/2026 et 09/10/2026 | part E, `refonte/hermes-p9e` : `bdd0f3d` (décisions D122 à D155), `4a46022` (historique), `6b37aa2` (ce document), `478f065` (notes de reprise), `81a349a` (README, `CLAUDE.md`), `611cc58` (journal 1.0.0 préparé), `3f367a8` (runs de la fusion de P7, constat du § 5) ; relecture indépendante de cette préparation : 5 constats, tous vérifiés et corrigés (`3449287` : derniers relevés du § 2 ; `aa3d1ee` : constat du § 5 dans le README ; `ec37ac4` : place de l'ouverture 1.0.0 dans `CLAUDE.md` ; `ae1f881` : cinquième correction de P0 dans le journal ; `bf05a7f` : têtes des branches de P9 dans les notes de reprise), plus `46e57f1` (constats de P1 et P2 laissés en limites, trouvé en les vérifiant) ; seconde relecture : 8 constats, tous vérifiés et corrigés (`34f8c90` : venv complété par le verrou haché, mesuré sur un clone neuf ; `e35fc23` : scripts à Docker qui ne tournent plus nulle part ; `a3eba55` : chantier SECU-TUI cité ; `a9a2033` : « prêt à déployer » retiré ; `c5f1ac0` : runs des PR renvoyés hors du journal 1.0.0 ; `2757d18` : liens réécrits de la ligne 0.10 dits ; `14b7d99` : jobs du témoin dans D143 ; `e19367b` : dates de ce document) ; CI verte sur chaque commit poussé, de `bdd0f3d` (`37798492510`) à `e19367b` (`37879198392` : Windows 1 171 réussis et 87 ignorés, Linux 1 204 et 54 ignorés, interface 203, moteur 74) ; réunion du 9 octobre 2026 : `07a72f4`, `05c6686`, `9729c73`, `90102b1`, `f613873` ; version finale : `7042677` (D160, plan, `CLAUDE.md`, historique), `83c0467` (manuel), puis ce document et les commits qui le suivent sur la branche | faite ; relecture de la préparation faite (deux passes) ; relecture de la version finale : faite avec celle de toute P9 (ligne suivante) |
| Relecture indépendante de toute P9 (relecture finale) | 34 constats retenus par cinq lentilles (publication, documentation, preuves, sécurité, produit), dont 11 contre-vérifiés par un sceptique ; chacun vérifié, puis corrigé (test rouge d'abord pour le code) ou réfuté avec sa preuve ; tableau constat → traitement → preuve : journal de P9 | dépôt ; local (Docker, D160) ; CI | 09/10/2026 | corrections à partir de `6ee8871` (outil de montée) ; décisions D161 à D163 | **fait** ; runs de la tête corrigée : avec ceux de la PR de P9 (D163) |
| Commit d'ouverture 1.0.0 (D129), journal 1.0.0 complet | `chore(release): open 1.0.0`, `chore(release): prepare 1.0.0 changelog`, les deux derniers commits de P9 | dépôt ; CI | **à relever** | — | **à relever** par la PR de documentation d'après l'étiquette (D163) : SHA des deux commits et leurs runs ; d'ici là, cités par le corps de la PR vers `main` |
| PR de P9 vers `refonte/hermes`, quatre workflows verts, fusion | — | CI | **à relever** | — | **à relever** par la même PR de documentation (D163) ; d'ici là, cités par le corps de la PR vers `main` |
| Pixel Office et Godot hors périmètre | `scripts/check_engine_frozen.py` vert ; aucune ligne sous `packages/pixel-office-engine` | CI | chaque run | chaque run de `ci.yml` | vérifié à chaque push ; derniers relevés sur cette branche : CI `37908787830` (`90102b1`) et `37911451671` (`f613873`), job du moteur vert |

## 4. Publication (après l'accord du propriétaire)

Ces lignes viennent avec la PR de `refonte/hermes` vers `main`, sa fusion et l'étiquette (part F) : elles restent
**à relever** jusque-là, puis sont complétées, avec les deux dernières lignes « à relever » du § 3, par une PR de
documentation seule (D163).

| Exigence | Preuve attendue | Date | Résultat |
|---|---|---|---|
| PR de `refonte/hermes` vers `main`, quatre workflows verts (CI, Image Hermes avec ses jobs, Image de l'exécutant, Desktop CI) | identifiants des runs de la PR | **à relever** | **à relever** |
| `git diff --check origin/main...origin/refonte/hermes` vide ; balayage des secrets sur la plage | sorties des deux commandes | **à relever** | **à relever** |
| Fusion par commit de fusion sur la tête testée | `M^1` = ancienne tête de `main`, `M^2` = tête testée, arbre fusionné = arbre testé | **à relever** | **à relever** |
| `git rev-parse v1.0.0^{commit}` = commit de fusion ; `VERSION` = 1.0.0 | sorties des commandes | **à relever** | **à relever** |
| Workflows sur `main` après la fusion | identifiants | **à relever** | **à relever** |
| Premier run de `Desktop Release` (brouillon non signé, D131) | identifiant du run, état du brouillon | **à relever** | **à relever** |

## 5. Non prouvé (dit)

État au 9 octobre 2026 ; détail : [exploitation.md](../exploitation.md) § 10, [railway.md](railway.md) § 12 et
§ 14.7, [desktop.md](desktop.md).
- **Rien n'est déployé sur Railway** : tout ce qui ne se constate que sur Railway (PID 1 et bord réels, cookies
  `Secure` et `trusted_proxies`, clés non documentées de l'IaC, sonde R0 et régime de l'exécutant, sauvegardes
  réelles et leur atomicité, contradiction de la documentation sur les sauvegardes postérieures, reconnexion
  d'openai-codex, notification réelle, parcours téléphone réel, premier dépôt réel, bilan à 8 h, coût réel).
- La répétition de restauration en production et les reconnexions réelles ; la chaîne complète export chiffré →
  déchiffrement → import sur Railway (prouvée par morceaux : déchiffrement à l'identique par la station Qt, import
  sur un volume vide à root par R4).
- La station Qt après une restauration de l'identité (même règle que le navigateur, non rejouée) ; la station Qt
  alignée sur P7 (P8b) face à un vrai greffon P7 : son flux et ses gestes ne sont éprouvés que contre le faux Hermes
  de ses tests natifs et les fixtures partagées ([desktop.md](desktop.md), « Non prouvé »).
- Une montée de Hermes vers une release postérieure à `v2026.9.24` : v0.21.6 est publiée depuis le 8 octobre 2026,
  mais `scripts/monter_hermes.py verifier --etiquette v0.21.6` la refuse (son image est construite depuis
  `a28a5d03`, 39 commits avant celui de l'étiquette, `818c13be`) ; 1.0.0 reste sur 0.21.5 (D161) ; la montée de
  données depuis `v2026.9.21` (l'image d'ACP sur 0.21.4 ne démarre pas) ; la montée d'Authelia ; un retour arrière
  par Rollback ; un vrai agent à la place de l'agent factice.
- Le premier run de `Desktop Release` tant que l'étiquette n'est pas posée. Chaque Desktop CI fabrique l'installeur
  et l'archive portable, **non signés** (empaquetage « à blanc » : produits réellement, ni signés ni publiés). Relevé
  dans le journal du job, plus durable que l'artefact : Desktop CI `37927394068` (tête `7a428ce`), job
  `113809511372`, « Mode à blanc : les artefacts sont produits, rien n'est signé, rien n'est publié. », « Produit :
  …\dist\desktop\AgentCompanyPlatform-Setup-0.11.0-x64.exe », SHA-256 `2ff32242b99d800f…` ; l'artefact
  `desktop-ci-37927394068` lui-même expire le 16 octobre 2026 (conservation de 7 jours). Ils n'ont jamais été
  installés ni lancés sur un Windows propre ; aucun certificat de signature de code.
- Test de restauration, hors Railway : il ne prouve ni le second arrêt brutal d'une même carte (lu dans le code), ni
  un fichier de root illisible par Hermes dans le volume exporté, ni l'identité et Hermes restaurés à des instants
  différents (supposé) ([exploitation.md](../exploitation.md) § 10) ; la station Qt après une restauration de
  l'identité : ci-dessus.
- Signature cosign de Codex non vérifiée (identité non établie).
- `preserve()` sur une variable jamais posée : supposé sans effet (D116).
- Les bouts en bout locaux du poste Windows (`scripts/e2e-poste-windows.ps1`, dernier passage relevé : P5) et de la
  station Qt (`scripts/e2e-desktop-windows.ps1`, dernier passage relevé : P8), et les témoins négatifs de P4 à P6
  (`scripts/temoins_negatifs_p4.sh` à `_p6.sh`) : scripts à Docker local qu'aucun workflow n'appelle. Docker local
  est de nouveau permis depuis le 9 octobre 2026 (D160), mais ils n'ont été rejoués ni sur le code de P7 ni sur
  celui de P9. Le verrou Python n'a pas été recompilé depuis D134 (`scripts/lock_python.ps1` lance Docker).
- Tests instables connus, verts sur la tête au moment du relevé : le test navigateur de la connexion (course avec la
  relecture périodique du tableau de bord : Image Hermes `37908787791`, tentative 1, § 3) ; sous Windows,
  `apps/poste/tests/contrat/test_enrolement.py:78` (`ssl.SSLEOFError` du faux serveur TLS : CI `37016933709` et
  `37763665065`) ; en local, des tests temporisés du poste sous charge (le 9 octobre 2026,
  `apps/poste/tests/test_local_runner.py::test_stop_event_terminates_the_real_process`, rouge une fois sur
  `916bf7a`, vert seul et dans les suites suivantes).
- **Constat de sécurité, corrigé et fusionné le 9 octobre 2026 (PR #23, `5026a70` ; § 1 et § 2), avec une limite** :
  Image Hermes `37784838264` (`fdb41c9`), tentative 1, job `113336818423` rouge sur `hermes/tests/contrat/test_sans_shell_contrat.py::test_volume_piege_apres_relance` :
  après le redémarrage du conteneur sur un volume piégé, la session du tableau de bord (`/api/ws`) listait `terminal`,
  `write_file`, `execute_code`… (les jeux posés par le `.env` piégé), alors que l'api_server répondait « Tool
  'terminal' does not exist » ; deuxième des trois couches de la défense de P2 ([image.md](image.md) § 5, épingles du
  `.env` géré) vue en défaut **une fois**. Tentative 2 verte, comme ce test dans les autres runs relevés pendant P9.
  **Instruit hors de P9** par le chantier SECU-TUI : branche `refonte/hermes-secu-tui` (partie de `b9779f1`), sa
  propre PR vers `refonte/hermes` (#23, tête `6a37a8c`, fusion `5026a70`). D'après sa documentation
  ([image.md](image.md) § 4.3 bis, § 4.3 ter, § 5, § 9 et § 10) :
  cause racine prouvée sans course (Hermes publie la valeur du `.env` du volume dans `os.environ`, puis applique la
  portée gérée par une écriture séparée ; un fil concurrent du tableau de bord lit l'entre-deux), par un point fixe
  dans le vrai conteneur ; troisième couche mesurée : une session qui a reçu exactement ces outils se voit refuser
  `terminal` par la garde `pre_tool_call` ; seconde faille trouvée en chemin, hors des trois couches : une source
  externe de secrets (`secrets.command`) du `config.yaml` du volume, lancée par `/bin/sh` avant la portée gérée.
  Preuves relevées par `gh` (§ 2) : tests seuls (`4c3647e`) sur le code de P7, run jetable `37831355746` (8 octobre
  2026), **rouge attendu** ; correctif SECU-1 (retrait par root des clés épinglées des `.env` du volume) et refus
  SECU-2 (`373b047`), run jetable `37832691849` (8 octobre 2026), **vert** ; `208ecd7` (documentation de la
  branche) : Image Hermes `37835575233` et CI `37835575491`, **verts** ; audit défensif du 9 octobre 2026 : tests
  seuls (`e5e3f3c`, sur `d5d8b73`), run jetable `37873430373`, **rouge attendu** ; correctif `2c4e2d4`, run jetable
  `37873804340`, **vert**. Décisions SECU-1 et SECU-2 numérotées **D156** et **D157** ([plan](plan.md) § 1) ; runs
  de la PR et de la fusion au § 1, verts. Depuis la réunion, la restauration et la montée de P9 ont été rejouées avec
  ce correctif (§ 3) : aucun `.env` des volumes du banc ne porte de clé épinglée (lu dans l'image), et les journaux de
  démarrage que ces jobs affichent n'ont aucune ligne `SECU-1`. **Reste non corrigé** ([image.md](image.md) § 10) : une écriture **directe** d'un `.env` du volume
  pendant la vie d'un service (faille de Hermes, ou shell du propriétaire) rouvrirait la fenêtre jusqu'à la relance
  suivante ; quelques variables ni épinglées ni refusées dans le volume restent non mesurées ; le retrait des clés
  épinglées n'a lieu qu'au démarrage et aux relances.
