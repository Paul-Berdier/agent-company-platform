# ACP 1.2.0 — preuves de livraison

Relevé du **14 octobre 2026**. Les quatre workflows finaux ont réussi sur
`abbedc4abb9c4dd468759414ce09c3243f45b33c`. La [PR 32](https://github.com/Paul-Berdier/agent-company-platform/pull/32)
est fusionnée depuis **01:44:35 UTC**, commit **`2ceea1bc7db901dcbe99a5bd049bb44c2799ed54`**.
Le tag annoté **`v1.2.0`** est poussé sur cette fusion. Les arbres de la tête,
de la proposition et de la fusion sont identiques.
[Desktop Release 38497373160](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38497373160)
a réussi sur le tag. La [release GitHub](https://github.com/Paul-Berdier/agent-company-platform/releases),
ID **412263602**, reste **en brouillon, non publiée** ; ses trois fichiers ont été
téléchargés et vérifiés, sans exécuter les paquets. La fusion, le tag et ces
validations ne prouvent aucune installation personnelle ni aucun déploiement Railway.
Les cas ignorés ou désélectionnés ne sont pas des réussites.
Les noms de journaux et de JSON sous `apps/desktop/build/verification/pixel-atelier/`
sont des **chemins de provenance locale**, non des fichiers publiés sur GitHub.
Les liens GitHub pointent uniquement vers les workflows ou jobs réellement consultés.

## Références du lot

| Élément | Référence |
| --- | --- |
| Branche | `codex/hermes-workspace-integrations` |
| Base | `ff1b71a83f9c598936391b6dfc026abd55f0ac42` |
| Tête finale | `abbedc4abb9c4dd468759414ce09c3243f45b33c` |
| Arbre final | `2c30003854e8f4963b1020cd8de36cc2c804506a` |
| Correctifs finaux pont, Discussion et bancs de test | `76c9f34f12b8079ca7d3445db0e180393e686e1a` |
| Produit initial / journal initial | `6d4161e` / `7ea6181` |
| Correction de collecte et catalogue | `f1e11ec48ec82a49d2e92e6f2b599b33c3467b91` |
| Correction des attentes navigateur et portée agents | `98f16929d1a58bd4c45f659bc64f05ff6e9078d4` |
| PR | [32](https://github.com/Paul-Berdier/agent-company-platform/pull/32), fusionnée le 14 octobre 2026 à 01:44:35 UTC |
| Fusion | `2ceea1bc7db901dcbe99a5bd049bb44c2799ed54` |
| Identité des arbres tête / proposition / fusion | `2c30003854e8f4963b1020cd8de36cc2c804506a`, identiques |
| Tag annoté `v1.2.0` | objet `165e49b90e7b32a680ef8ab78aeb8ca8aa726b9f`, cible `2ceea1bc7db901dcbe99a5bd049bb44c2799ed54`, poussé |
| Desktop Release | [38497373160](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38497373160), **success** sur le tag et la fusion ; **41/41 suites Qt, 0 échec, 143,80 s** |
| Release GitHub | [Page des releases](https://github.com/Paul-Berdier/agent-company-platform/releases), ID `412263602`, tag `v1.2.0` ; `draft=true`, `prerelease=false`, `published_at=null` ; trois fichiers vérifiés |

Le lot enrichit Discussion, livre six méthodes Addy et trois méthodes Ponytail en
texte seul, présente dix fiches d’intégration et ajoute le Coffre ACP Markdown
compatible Obsidian. La boucle du chef conserve le graphe déterministe, les
budgets et les gardes existants. Lire le [guide du workspace](workspace-1.2.0.md)
et le [parcours de mise à jour en trois étapes](../mettre-a-jour-1.2.md).

## CI de la tête finale

Tous les runs ci-dessous ciblent `abbedc4abb9c4dd468759414ce09c3243f45b33c`.

| Workflow | Verdict et bilan acquis |
| --- | --- |
| [CI générale 38491197721](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38491197721) | **success** — Linux : **1 466 réussis, 60 ignorés, 464 sous-tests, 174,65 s** ; Windows : **1 417 réussis, 109 ignorés, 464 sous-tests, 275,14 s** ; interface web **204**, moteur **74** |
| [Desktop CI 38491200817](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38491200817) | **success** — **41/41 suites, 135,60 s** ; **627 cas Qt réussis, aucun échec ni ignoré**, initialisations/nettoyages inclus |
| [Image Hermes 38491204647](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38491204647) | **success** — image **895 réussis, 277 avertissements, 450,14 s** ; contrats **205 réussis, 19 désélectionnés, 2 742,04 s** ; navigateur **10 réussis, 1 désélectionné, 523,87 s** ; restauration **13 réussis, 211 désélectionnés, 758,29 s** ; R3 **1 réussi, 10 désélectionnés, 146,35 s** |
| [Image exécutant 38491207456](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38491207456) | **success** — image : **45 réussis, 114,87 s** ; poste/contrat en root : **933 réussis, 24 ignorés, 158,49 s** |

Journaux et métadonnées acquis, dans `apps/desktop/build/verification/pixel-atelier/` :
`ci-generale-1.2.0-abbedc4-20261014.log` / `.json` et
`ci-executant-1.2.0-abbedc4-20261014.log` / `.json`.
La preuve Desktop `ci-desktop-38491200817-preuves.json` relève l’archive
`desktop-ci-ctest-38491200817` (ID `11861817974`, 12 563 octets), dont le SHA-256
`06c1bcdbe6029f0e4078add4bfe1339b08dd05b2570c48609a2bcabbc0cc8936` concorde avec
le digest GitHub. Son `LastTest.log` contient les 41 résumés Qt. Les huit
avertissements recensés sont quatre contrepreuves volontaires et quatre messages
de répertoire de polices Qt absent sur le runner ; aucun n’est compté comme échec
ou test ignoré. Le succès CI ne vaut pas test de la fenêtre personnelle.
Les 24 cas ignorés dans l’image concernent Windows : cette suite Linux ne prouve
pas DPAPI ni les protections de partage Windows. La sonde de l’exécutant mesure
le runner et les régimes d’isolation autorisés, pas l’instance Railway personnelle.

Le job [restauration 115616556020](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38491204647/job/115616556020)
a réussi sur la même tête, du 14 octobre 00:37:18 à 00:54:53 UTC (1 055 s).
Son journal brut `ci-hermes-restauration-38491204647-20261014.log` (226 037 octets),
ses métadonnées `.json` et son récapitulatif `-bilan.json` sont archivés.
Le job principal 115616556197 et le workflow complet ont maintenant réussi ;
les compteurs principaux et empreintes des journaux bruts/nettoyés sont dans
`ci-hermes-38491204647-final-preuves.json` / `.md`. La sonde Context7 officielle
du 14 octobre à 00:39:31 UTC a confirmé la connexion HTTP en 2 032 ms et découvert
deux outils : `resolve-library-id` et `query-docs`. Son ZIP de 566 octets a une
empreinte concordante avec GitHub. Cette sonde non bloquante ne prouve pas
l’exécution d’une recherche ni une authentification personnelle.

## Validations locales finales

| Contrôle | Résultat | Provenance locale |
| --- | --- | --- |
| Compilation native complète puis incrémental final | Qt 6.8.3 / MSVC Release réussis, produit et tests reliés | `build-desktop-coffre-discussion-final-1.2.0.log`, `build-desktop-coffre-discussion-gel-1.2.0.log` |
| Qt complet | **41/41 suites, 140,76 s** ; **627 réussis, 0 échec, 0 ignoré, 0 blacklisted**, initialisations/nettoyages Qt Test inclus | `desktop-tests-coffre-discussion-gel-1.2.0.log`, `ctest-coffre-discussion-gel-1.2.0.log`, `diagnostic-coffre-ci-38487516698.md` |
| Python Windows complet | **1 419 réussis, 107 ignorés, 464 sous-tests réussis, 909,31 s** | `python-1.2.0-reprise-20261014.log` |
| Pont après purge serveur | **38 réussis, 5,92 s** | `coffre-reprise-purge-20261014.log` |
| Discussion, navigation/refus/coupure/oubli | **30 réussis, 0 échec, 0 ignoré, 4,397 s** | `discussion-envoi-incertain-20261014.log` |
| Répétitions du geste Coffre corrigé | **10/10 processus**, chacun 3 réussis, 0 ignoré, 674–735 ms | `coffre-ci-38487516698-repetitions.json` |
| Répétitions de la fixture des interactions | **5/5 processus**, chacun 21 réussis, 0 ignoré, 8 699–8 965 ms | `pages-ci-38487516698-fixture-repetitions.json` |
| Captures du vrai QML avec faux Hermes | Quatre thèmes, 1280×720 et 1920×1080, coffre/graphe inclus ; **3 réussis, 0 ignoré, 23,431 s** | `captures-1.2.0-final/`, `captures-1.2.0-final.txt` |
| Garde des captures PNG | **3 réussis, 0,02 s** ; ne prouve pas le parcours navigateur | `e2e-captures-20261014.log` |
| Ciblé image Hermes du 12 octobre | **30 réussis, 2 avertissements, 47,07 s**, coffre/machine/catalogue | `docker-coffre-machine-catalogue-20261012-b.log` |

Les quatre avertissements Qt finaux viennent de contrepreuves existantes : trois
trames JSON volontairement invalides et une famille de thème inconnue. Aucun
test ignoré n’est compté comme réussi. Le premier ciblé Discussion, avant la
distinction « Envoi non confirmé », reste conservé : 29 réussis en 4,278 s,
`discussion-refus-20261014.log`.

Le ciblé Docker du 12 octobre utilise `/opt/data` en tmpfs, sans réseau ni volume
personnel ; ses conteneurs et trois images dédiées sont nettoyés
(`docker-coffre-resultat-20261012.json`). Il ne remplace pas la CI Hermes complète.
Les trois images du parcours E2E identifiées précédemment, distinctes de ce
ciblé, restent un nettoyage à reprendre ; **leur présence actuelle n’a pas pu être
inspectée**. La tentative unique du 14 octobre à 01:24:32 UTC atteint son délai
strict de 12 s après 12,078 s (`docker-e2e-nettoyage-20261014T012432Z.json`). Aucune
inspection, suppression ni relance n’a suivi ; le tableau `images: []` de cette
preuve ne signifie donc pas qu’aucune image n’existe. La disponibilité du moteur
n’est pas établie. Le précédent démarrage normal après WSL n’avait pas non plus
confirmé de disponibilité au délai de 50 s ; aucune reconfiguration du système.
Cette limite de nettoyage local est **non bloquante pour les validations GitHub**
et ne transforme aucun nettoyage restant en succès.

## Paquets locaux finaux

Dossier : `dist/workspace-1.2.0-livraison/`. Preuve complète :
`livraison-1.2.0-20261014-final/verification-paquets.json`.
Les paquets locaux utilisent le décor LimeZu licencié ; les paquets du brouillon
GitHub utilisent le décor ACP original et ont leurs propres empreintes.

| Fichier local | Taille | SHA-256 |
| --- | ---: | --- |
| `AgentCompanyPlatform-Portable-1.2.0-x64.zip` | 53 152 849 octets | `e8afca2f9208b76e12f111995f62ba2907d9bc7a6d023faa000e426dba52ace5` |
| `AgentCompanyPlatform-Setup-1.2.0-x64.exe` | 34 879 820 octets | `5bb072b8bfb4314cf50f18272c173df15fdd053d0b81391d03b3c909a7a8a9dc` |
| `SHA256SUMS.txt` | 217 octets | `8679b780c9bdc1c476b399f6a2704ed04e4e3f0c769f3d4c29b232d18dba55d0` |

Les deux paquets correspondent à `SHA256SUMS.txt`. Le Setup est **NotSigned**.
Les **854 fichiers** du pont correspondent en taille et SHA-256 dans le stage et
le ZIP, sans fichier supplémentaire, et restent inchangés après la sonde.
Le runtime **Python 3.12.10 embarqué et isolé** passe sur coffre jetable : création,
coupure, résultat non acquitté archivé après le 404 `operation_inconnue`, aucune
mutation rejouée, édition locale préservée et lecture suivante réussie. L’identité
est en mémoire, sans appel réseau réel ; le coffre jetable est nettoyé.

**Ni Setup ni desktop empaqueté exécuté, aucune installation personnelle.**
Les paquets de `7ea6181` et `dist/workspace-1.2.0-final` restent historiques ;
ce dernier ne contient pas le correctif Discussion et **ne doit pas être livré**.
Le coffre personnel avait été créé avec un précédent bundle local, sans association.
## Paquets du brouillon GitHub

Le [workflow Desktop Release](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38497373160)
a réussi sur `v1.2.0` / `2ceea1bc7db901dcbe99a5bd049bb44c2799ed54` : compilation,
**41/41 suites Qt, aucun échec en 143,80 s**, empaquetage et création du brouillon.
La [release GitHub](https://github.com/Paul-Berdier/agent-company-platform/releases)
porte l’ID `412263602`, `draft=true`, `prerelease=false`, `published_at=null`.
Elle n’apparaît donc pas dans le bouton de mise à jour. Son URL de brouillon peut
changer ; l’ID et le tag identifient le relevé.

Les trois fichiers téléchargés dans `dist/release-1.2.0-ci/` concordent avec les
tailles et les digests GitHub ; les deux paquets concordent aussi avec `SHA256SUMS.txt`.
Ils utilisent le décor ACP original, distinct du décor LimeZu local.

| Fichier CI | Taille | SHA-256 |
| --- | ---: | --- |
| `AgentCompanyPlatform-Portable-1.2.0-x64.zip` | 53 148 613 octets | `bb40eb1fbd474a0e59baaea871737bf49a1b8e4707f628e3db8dad6d17b0a014` |
| `AgentCompanyPlatform-Setup-1.2.0-x64.exe` | 34 864 998 octets | `12835d15fb6ba73b327ff799ba347783bd5a142f06c3f6408383807d12eac9be` |
| `SHA256SUMS.txt` | 217 octets | `46722c71f76d0e0dca0b19539dee65571a4b7a91b09d409f80222747de2933f1` |

Le Setup est **NotSigned**. Les **859 fichiers** du manifeste du pont sont présents
et vérifiés en taille/SHA-256 dans le ZIP, sans fichier supplémentaire. La preuve
de fabrication relève Python **3.12.10** isolé, les opérations créer/lire/écrire/
archiver/graphe sur coffre jetable et l’acheminement de `creer --help` par le menu
PowerShell. Le runtime téléchargé n’a pas été exécuté localement.

Le correctif de reprise après purge et son guide de récupération sont présents.
Pour `obsidian_bridge.py` et `LISEZ-MOI.txt`, le contenu correspond au tag après
normalisation des **seuls CRLF** : la CI produit des fins de ligne CRLF, les sources
sont en LF. L’identité brute octet pour octet n’est donc pas revendiquée ; les
tailles et empreintes brutes distinctes sont conservées dans la preuve.

Provenance locale dans `dist/release-1.2.0-ci/` : `verification.json`,
`verification.md`, `desktop-release-38497373160.log` et l’artefact `ctest/LastTest.log`.
**Aucun Setup ni desktop téléchargé exécuté ; aucune donnée personnelle utilisée.**
La publication GitHub reste une étape distincte, non effectuée à ce relevé.

## Campagnes précédentes et corrections

Les résultats suivants concernent leurs propres têtes ; aucun ancien succès
n’est transféré à `abbedc4`.

| Tête et campagne | Résultat historique |
| --- | --- |
| `42ee7b8` — CI [38487514247](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38487514247), Exécutant [38487522401](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38487522401) | Succès ; Linux 1 454/60 ignorés/464 sous-tests/176,76 s ; Windows 1 405/109/464/280,73 s ; web 204, moteur 74 ; image exécutant 45/115,69 s puis root 922/24 ignorés/160,65 s |
| `42ee7b8` — Desktop [38487516698](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38487516698) | **Échec : 40/41 suites, 135,90 s**, `tst_coffre_interactions` ; paquet non construit. Aucune assertion Qt dans les logs agrégé/brut, aucun artefact de diagnostic |
| `42ee7b8` — Hermes [38487519487](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38487519487) | **success** ; image **895 réussis/277 avertissements/441,06 s** ; contrats **205 réussis/19 désélectionnés/2 816,12 s** ; navigateur **10 réussis/1 désélectionné/520,36 s** ; restauration **13 réussis/211 désélectionnés/767,03 s** ; R3 **1 réussi/10 désélectionnés/147,02 s** |
| `ad6bf27` — CI [38305498810](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38305498810), Desktop [38305502651](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38305502651), Exécutant [38305509839](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38305509839) | Succès ; Python Linux 1 454/60/464/182,85 s, Windows 1 405/109/464/286,03 s ; Qt 41/41/138,39 s ; exécutant 45/116,60 s puis 922/24/162,94 s |
| `ad6bf27` — Hermes [38305506115](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38305506115) | **Échec navigateur** : image 895 réussis/277 avertissements/457,65 s ; contrats 205 réussis/19 désélectionnés/2 741,23 s ; navigateur 1 échec/9 réussis/1 désélectionné/440,02 s ; restauration 13/211 désélectionnés/716,70 s ; navigateur R3 1/10 désélectionnés/182,62 s |
| `7ea6181` — CI [38303958148](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38303958148), Hermes [38303965340](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38303965340) | **Échecs** : collecte Python FastAPI sur Linux 2,78 s et Windows 2,85 s ; image Hermes 1 échec/891 réussis/277 avertissements/395,77 s. Web 204 et moteur 74 passent |
| `7ea6181` — Desktop [38303961662](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38303961662), Exécutant [38303969252](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38303969252) | Relevé Qt 41/41/136,41 s ; exécutant success, image 45/114,53 s puis root 922/24 ignorés/158,83 s |

Archives : `ci-*-1.2.0-premier*.log`, `ci-*-1.2.0-final.log` pour `ad6bf27`,
`ci-*-1.2.0-20261014.log` pour `42ee7b8`. Le bilan image Hermes d’`ad6bf27`
est conservé dans `ci-hermes-job-114998455704-1.2.0-brut.log`, car l’agrégateur
omet la fin du bloc après une ligne très longue. Le brut Desktop historique est
`ci-desktop-job-115604636062-20261014-brut.log`.
Le succès Hermes historique sur `42ee7b8` est détaillé dans
`ci-hermes-38487519487-historique-preuves.json` / `.md`, avec les empreintes des
journaux bruts. Les deux jobs optionnels de montée n’ont pas été exécutés dans ce
run ; ils sont marqués skipped. Ce succès reste distinct de la validation finale
d’Image Hermes `38491204647` sur `abbedc4`, réussie séparément.

Corrections établies, sans suppression d’assertions :

- **Collecte FastAPI et catalogue :** `f1e11ec` déplace trois tests HTTP dans
  l’image Hermes, où le serveur est réellement disponible, et complète l’ensemble
  strict Addy/Ponytail attendu. Aucun test HTTP n’est rendu facultatif.
- **Navigateur :** l’attente 21/21 était périmée face au DOM 31/31. `98f1692`
  vérifie strictement le verrou : 31 textes Hermes, 10 candidats poste, 41 noms
  uniques. Le plafond de captures passe à 20 000 px CSS sans accepter de troncature.
- **Coffre Qt :** reproduction locale du bouton à y=1 044 dans une fenêtre de
  hauteur 1 000 ; la hauteur évoluait 1196→1292 après la mesure. Le helper attend
  maintenant le polish Qt avant mesure et après défilement. Cela ne reconstitue
  pas l’assertion absente du runner historique. `QT_FORCE_STDERR_LOGGING=1` et
  les artefacts `Testing/Temporary/*.log` conservent désormais les diagnostics.
- **Fixture des interactions :** une campagne locale intermédiaire passe 40/41
  en 165,34 s, Coffre vert ; les boutons Questions sont masqués. La fixture normale
  rend maintenant `/meta` 200 avec le vrai fichier et attend `Questions.lue`.
  La trace ne prouve pas la réception tardive précise du 404 ; aucune cause plus
  détaillée n’est affirmée. Les répétitions puis la suite 41/41 finale passent.
- **Pont et Discussion :** un résultat local après purge serveur est archivé sans
  écrasement avant libération de la file ; collision, saturation ou échec gardent
  le blocage. Un texte refusé ou non confirmé rejoint son brouillon en préservant
  la saisie récente, même après navigation, mais jamais après oubli. Aucune
  mutation ni aucun prompt n’est rejoué automatiquement.

Les premiers essais Qt du lot (3 échecs sur 39 : `implicitHeight` interdit, module
`Acp.Runtime` absent du banc, géométrie des bulles) restent dans `qt-1.2.0.log`.
La suite locale du 12 octobre 41/41 en 143,16 s et les campagnes Python 1 407/107/464
en 431,08 puis 443,99 s restent historiques, distinctes de la validation finale.

La sonde Context7 non bloquante du 12 octobre a découvert deux outils
(`resolve-library-id`, `query-docs`) en 1 489 ms depuis le runner. Ce n’est ni une
preuve d’inférence, ni un appel applicatif, ni une connexion personnelle.

## Mise à jour et préservation des données

Les montées sur `7ea6181` depuis [1.1.1, run 38303973193](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38303973193)
et [1.0.1, run 38304130634](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38304130634)
réussissent chacune **6 tests, 218 désélectionnés**, en 265,14 s et 246,47 s.
Sur volumes jetables : anciennes données et références d’identité préservées,
exécutant enrôlé/prêt, projet B repris avec `--resume` et terminé, projet E terminé,
sans compte réel ni push. Journaux `ci-montee-1.1.1-1.2.0-premier.log` et
`ci-montee-1.0.1-1.2.0-premier.log`.

Leur constat « migration : non, version 4→4 » ne couvre pas l’API Coffre : ses
**trois tables et un index sont créés au premier appel**, pas au démarrage.
`preservation-schema-coffre-1.0.1-1.2.0.json` prouve séparément deux initialisations
SQLite : les 20 anciennes tables, leurs lignes et compteurs restent identiques ;
seules `coffres_codes`, `coffres_identites`, `coffres_operations` et leur index
s’ajoutent, les nouvelles données survivent au second appel, intégrité valide.
Ce n’est pas une restauration complète ni un déploiement réel. Appliquer les
sauvegardes et la procédure propriétaire du [manuel § 6.4](../exploitation.md#64-vos-gestes-et-le-point-de-non-retour)
et du [§ 6.5](../exploitation.md#65-authelia-binaires-de-lexécutant-acp-lui-même).
Hermes amont reste épinglé à **0.21.5**, sans mise à jour upstream.

## Instance personnelle et limites

Les lectures seules des **12 et 14 octobre** observent `hermes` et `executant` sur
ACP **1.0.1**, source `85b458bbffbfb6dffe1fc40b8c3885f11b779ac7`, `staged=null`
pour les deux au 14. Le déploiement Hermes relevé était `8a36ac9d-6a60-4900-8b33-6e8e32aa5de9`
du 10 octobre 07:42:08.197 UTC, statut SUCCESS. **Aucun déploiement, changement de
configuration ou compte personnel effectué.** Le Setup ne met pas ces services à jour.
Le schéma Railway `connect_service_source` consulté par l’orchestrateur confirme
que `source.commitSha` épingle le déploiement à ce commit : les pushes sur `main`
ne déplacent pas cette épingle. Les sauvegardes précèdent donc le futur déploiement
manuel ; cette étape personnelle est distincte de la fusion Git déjà autorisée.

Le coffre `C:/Users/Paul/Documents/ACP-notes` est **déjà créé, non associé** :
ne pas le recréer. Ses notes n’ont servi à aucun test de mutation. L’association
nécessite le serveur 1.2.0, un code temporaire et la comparaison d’empreinte.
Le pont DPAPI reste distinct de l’exécutant ; sa fenêtre doit rester ouverte,
sans service ni démarrage automatique implicite.

Les **neuf actions Coffre appartiennent au propriétaire dans le desktop**.
Aucun outil de lecture ou d’écriture Coffre n’est exposé aux agents Hermes ni à
Discussion. Le pont traite des notes UTF-8 jusqu’à 128 Kio ; graphe/recherche sont
bornés, le renommage ne réécrit pas les liens, et Bases, Canvas, plugins et CLI
Obsidian ne sont pas intégrés. Les notes demandées transitent par Hermes ; purge
applicative et scan par motifs ne garantissent ni effacement cryptographique
ni détection de tout secret. Les sauvegardes SQLite peuvent garder des copies.

CRM, REA, Douyin/TikTok, ML Intern, Hackingtool, Graphify et OmniRoute restent les
**sept services documentés, non installés/connectés**. ML Intern est archivé.
Addy/Ponytail sont des textes adaptés, sans programmes ni hooks upstream.
La présence d’une fiche au catalogue ne confirme pas une installation ni une authentification personnelle.

La fenêtre native et la session web personnelles restent **non observées** :
les tentatives du 14 octobre échouent avant accès (Sky/Node réinitialisé deux fois,
puis sandbox CUA en échec d’ACL `helper_unknown_error`). Les captures utilisent
un faux Hermes et ne prouvent pas ce parcours. Discussion reste globale ;
brouillons en mémoire seulement. Pièces jointes, terminal web, missions multiples,
mémoire sourcée et journal durable des appels d’outils restent hors de ce lot.
