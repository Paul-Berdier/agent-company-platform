# ACP 1.1.0 — preuves de livraison

État au 12 octobre 2026 : sources fusionnées, tag annoté `v1.1.0` poussé et
paquets Windows construits puis vérifiés. La release GitHub reste un **brouillon**
(`isDraft=true`, `isPrerelease=false`) ; les paquets sont **non signés et non
exécutés**. Les preuves sont attachées aux révisions et aux runs nommés ci-dessous.

## Sources validées et état de livraison

| Élément | Référence ou état |
| --- | --- |
| Base ACP 1.0.1 | `85b458b` |
| Branche vérifiée | `codex/pixel-atelier` |
| Tête validée avant fusion | `5d410086c30c6c7f74913a2968a04a4e9f86fceb` |
| Contrôles manuels de la tête | **completed / success** : CI générale, Desktop CI, Image Hermes et Image exécutant, tous sur `5d410086c30c6c7f74913a2968a04a4e9f86fceb` |
| PR | [#28 — MERGED](https://github.com/Paul-Berdier/agent-company-platform/pull/28), le 12 octobre 2026 à 05:50:30 UTC |
| Contrôle avant fusion | `main` inchangé à `85b458bbffbfb6dffe1fc40b8c3885f11b779ac7` ; arbre de la tête et de `refs/pull/28/merge` identique : `1e1c2342bb12c5faea8f4f88897a3f13f03d6fa2`. Aucune protection de `main` et liste des règles applicables vide vérifiées ; aucun contrôle obligatoire contourné |
| Base de la fusion | Quatre workflows manuels complets réussis et identité des arbres vérifiée. Les workflows automatiques de PR/merge sont des validations supplémentaires ; aucun résultat encore inconnu n’est présumé |
| Fusion dans `main` | `028eaa5d8c211bda77abc15ecb794c20b91d7eee`, le 12 octobre 2026 à 05:50:30 UTC ; parents vérifiés après fetch : `85b458b` et `5d41008` ; arbre identique `1e1c2342bb12c5faea8f4f88897a3f13f03d6fa2` |
| Tag | `v1.1.0` annoté, créé et poussé ; `git cat-file` confirme le type `tag` et le peel vers `028eaa5d8c211bda77abc15ecb794c20b91d7eee` |
| Desktop Release | [Run 38209746642](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38209746642) **success** sur `v1.1.0` / `028eaa5d8c211bda77abc15ecb794c20b91d7eee` ; compilation et packaging réussis, 36/36 suites CTest en 102,64 s |
| Release GitHub | [Release 1.1.0 en brouillon](https://github.com/Paul-Berdier/agent-company-platform/releases/tag/untagged-0db5c280ae9ed6509391), tag `v1.1.0` ; `isDraft=true`, `isPrerelease=false` ; non publiée au dernier relevé |
| Paquets téléchargés de la release | Trois fichiers récupérés dans `dist/release-1.1.0-ci/` ; SHA-256 des deux paquets recalculés et conformes à `SHA256SUMS.txt` |
| Installation et mise à jour depuis 1.0.x | **Non exécuté** : livraison de l’installeur sans le lancer sur le poste du propriétaire |
| Détection de la mise à jour par l'ancien client | **Non exécuté** sur l’installation personnelle |

Les runs manuels ci-dessous ciblent `5d41008`. Le commit de fusion et le tag ont
un arbre identique vérifié ; aucun résultat de run automatique encore inconnu
n’est présenté comme acquis.
Les commits n'introduisent pas de changement de schéma du greffon ni de montée des
versions épinglées Hermes, Codex ou Claude Code.

## Quatre workflows manuels réussis sur la tête validée

Les quatre workflows suivants ciblent
`5d410086c30c6c7f74913a2968a04a4e9f86fceb` et ont conclu **completed / success**.
Les ignorés et les tests non sélectionnés ne sont pas comptés comme réussis.
Les workflows automatiques lancés lors de la création de la PR sont distincts.

| Workflow | Run | État attesté | Journal local acquis |
| --- | --- | --- | --- |
| CI générale | [38205070212](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205070212) | **success** | `ci-38205070212.log` |
| Desktop CI | [38205072486](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205072486) | **success** | `ci-desktop-38205072486.log` |
| Image Hermes | [38205074960](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205074960) | **success** | `ci-hermes-38205074960.log`, `ci-restauration-38205074960.log` |
| Image exécutant | [38205077405](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205077405) | **success** | `ci-executant-38205077405.log` |

| Workflow / job sur `5d41008` | Réussis | Ignorés | Sous-tests réussis | Durée | Preuve |
| --- | ---: | ---: | ---: | --- | --- |
| CI — Python 3.12 Windows 2022 | 1 277 | 109 | 464 | 245,59 s | [Job Windows 114666634418](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205070212/job/114666634418) |
| CI — Python 3.12 Ubuntu | 1 330 | 56 | 464 | 163,32 s | [Job Ubuntu 114666634538](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205070212/job/114666634538) |
| Image exécutant — image construite et sonde locale | 45 | 0 | — | 113,46 s | [Job exécutant 114666654365](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205077405/job/114666654365) |
| Image exécutant — poste et contrat partagé en root | 842 | 20 | — | 154,00 s | [Job exécutant 114666654365](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205077405/job/114666654365) |
| Desktop CI — suites Qt | 36/36 | — | — | 105,79 s | [Job Desktop 114666638991](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205072486/job/114666638991) |

Les jobs [moteur 114666634291](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205070212/job/114666634291)
et [UI 114666634380](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205070212/job/114666634380)
ont également conclu **success**, ainsi que les simulations et le nettoyage.
Le packaging Desktop `DryRun` **non signé** a réussi. L’artefact
`desktop-ci-38205072486`, ID `11726534838`, mesure **61 203 389 octets** et expire
le **19 octobre 2026 à 04:53:42 UTC** (`2026-10-19T04:53:42Z`). Ce succès de
packaging ne constitue ni une installation personnelle ni une release publiée.

### Image Hermes : bilan final acquis

Le [job principal 114666650409](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205074960/job/114666650409)
et le [job Restauration 114666650714](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38205074960/job/114666650714)
ont réussi. Les compteurs sont lus dans les journaux acquis ; le résumé image
provient de la copie directe du journal du job détaillée ci-dessous. Le journal de
restauration nettoyé est aussi conservé dans
`ci-restauration-38205074960.log`.

| Périmètre Hermes sur `5d41008` | Réussis | Non sélectionnés | Durée |
| --- | ---: | ---: | --- |
| Suite exécutée dans l’image | 890 | — | 458,05 s |
| Contrats complets du job principal | 205 | 19 | 2 627,43 s |
| Navigateur du job principal | 10 | 1 | 498,18 s |
| Restauration | 13 | 211 | 744,85 s |
| Navigateur R3 après restauration | 1 | 10 | 151,80 s |

Le résumé de la suite image a été récupéré par une lecture directe de l’API du
job : **890 réussis et 277 avertissements en 458,05 s**. Le journal brut est
`ci-hermes-job-114666650409-raw.log` ; sa copie débarrassée des séquences ANSI/OSC
est `ci-hermes-job-114666650409-clean.log` (résumé ligne 4 878). Cette récupération
complète le journal fourni par `gh run view`, qui ne conservait pas ce résumé.

## Paquets CI de la release `v1.1.0`

Le [job Desktop Release 114681030886](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38209746642/job/114681030886)
a réussi sur le commit fusionné `028eaa5d8c211bda77abc15ecb794c20b91d7eee` :
compilation, **36/36 suites CTest en 102,64 s** et packaging. Journal :
`release-38209746642.log`.

Les trois assets — Setup, portable et `SHA256SUMS.txt` — ont été téléchargés dans
`dist/release-1.1.0-ci/`. Les empreintes recalculées des deux paquets correspondent
à celles de `SHA256SUMS.txt`. Métadonnées et relevé :
`release-1.1.0-github.json`, `paquets-ci-1.1.0.json`.

| Paquet CI téléchargé | Taille (octets) | SHA-256 vérifié |
| --- | ---: | --- |
| `AgentCompanyPlatform-Setup-1.1.0-x64.exe` | 24 657 261 | `1c25879c1beab5bbdb8e7c00fb393017c9a6c40cf540c29c273e3bd71b8bf3e0` |
| `AgentCompanyPlatform-Portable-1.1.0-x64.zip` | 37 622 984 | `eae0168d396244648012a3dc6dd571a7e81df6119ee1497cbadbf22fffa6ce01` |

Ces paquets embarquent le décor **original ACP**, sont **non signés** et n’ont
**pas été exécutés**. Windows SmartScreen peut afficher un avertissement. Une
empreinte vérifiée atteste l’intégrité de la copie, pas une signature d’éditeur.
La [release au dernier relevé](https://github.com/Paul-Berdier/agent-company-platform/releases/tag/untagged-0db5c280ae9ed6509391)
reste un brouillon associé à `v1.1.0` ; elle n’est ni publiée ni marquée prerelease.

### Validations supplémentaires sur le commit fusionné

| Workflow sur `028eaa5d8c211bda77abc15ecb794c20b91d7eee` | État au dernier relevé |
| --- | --- |
| [CI générale 38209720742](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38209720742) | **success** |
| [Desktop CI 38209720754](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38209720754) | **success** |
| [Image exécutant 38209720753](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38209720753) | **success** |
| [Image Hermes 38209720747](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38209720747) | **En cours** ; aucune conclusion présumée |

La preuve ayant fondé la fusion reste celle des **quatre workflows manuels complets
réussis sur `5d41008`**, dont l’arbre est identique à celui du commit fusionné et du
tag. Le second passage Hermes encore en cours est distinct de cette preuve acquise.

## Vérifications locales acquises

Journaux sous `apps/desktop/build/verification/pixel-atelier/`, ignorés par Git.
Les nombres de sous-tests et de tests ignorés sont séparés des tests réussis.

| Périmètre | Résultat | Durée | Journal |
| --- | --- | --- | --- |
| Python Windows complet | **1 280 réussis**, **464 sous-tests réussis**, **106 ignorés**, aucun échec | 1 128,51 s | `full-python-final-1.1.0.log` |
| Runner Windows et contrepreuves de fermeture | **49 réussis**, aucun échec | 69,05 s | `python-runner-final-startup-1.1.0.log` |
| Qt 6.8.3 / MSVC 2022 | Compilation Release et **36/36 suites CTest réussies** | 102,84 s pour CTest | `build-routage-final-1.1.0.log`, `desktop-tests-routage-corrige-1.1.0.log` |
| Guide de récupération, PowerShell 7 et Windows PowerShell 5.1 | Parcours **réussi** : empreinte, import Git et worktree ; chemins relatifs avec espaces et crochets, dépôt de test distinct | — | `recuperation-chemins-1.1.0.log`, `recuperation-chemins-powershell51-1.1.0.log` |
| Moteur Pixel Office gelé | **74 tests réussis**, 7 fichiers | — | `engine-tests-1.1.0.log` |
| Greffons web Hermes | **204 tests réussis**, 21 fichiers | — | `interface-tests-1.1.0.log` |
| Image Hermes épinglée, routage et planification ciblés | **87 tests réussis** | — | `hermes-routing-1.1.0.log` |
| Image Hermes épinglée, observations et routes projet ciblées | **20 tests réussis** | — | `hermes-observations-1.1.0.log` |
| Contrat P4, exploration, graphe et réclamations distantes | **3 tests réussis** | 373,72 s | `contrats-routage-p4-1.1.0.log` |
| Contrat P6, mise en service et relecture | **2 tests réussis** | 136,58 s | `contrats-routage-p6-1.1.0.log` |
| Contrat P7, redéploiement pendant une question | **1 test réussi** | 176,32 s | `contrats-routage-p7-1.1.0.log` |
| Navigateur P7, parcours téléphone puis bureau | **1 test réussi**, `ACP_E2E_OBLIGATOIRE=1` | 136,39 s | `navigateur-routage-p7-1.1.0.log` |

Les **6 contrats ciblés** et le **test navigateur P7** sont réussis. Le navigateur
emploie de faux comptes et un faux modèle, avec un vrai Chromium et une véritable
identité Authelia jetable ; il ne démontre aucune connexion personnelle. Les
captures et `releve-parcours.json` sont dans `captures-navigateur-routage-1.1.0/p7/`.
Le nettoyage local est vérifié : aucun conteneur, volume ou réseau sous le préfixe
`acp-contrat-pixel110-` ; les quatre tags d’image `acp-pixel110-*` ont été retirés.

Les deux passages Hermes routage/planification et observations/routes totalisent
**107 tests ciblés** ; ce total ne désigne pas
une suite complète de l'image. Les ignorés Python relèvent des conditions de
plateforme, de conteneur ou de privilèges indiquées dans le journal. Les délais de
démarrage des faux processus ont été distingués du budget d'arrêt produit, inchangé.

Les dernières captures, dans `captures-routage-1.1.0/`, comportent **24 vues du
workspace** sous Windows : Accueil, Projets et Travail, quatre variantes, chacune
en 1280×720 et 1920×1080, ainsi que les pages isolées. Le harness Windows avec rendu
logiciel conclut **3 étapes réussies, 0 ignorée et aucun avertissement en 15,210 s**
(`pages-bureau-routage-1.1.0.log`). `Routage.png` et `Projets-nouveau-projet.png`
ont été inspectées : aides textuelles lisibles et non tronquées. Ces captures
emploient un serveur factice et un stockage isolé ; elles ne démontrent aucun
compte personnel. Aucune preuve à 125 % ou 200 %, aucun profilage à 60 images/s
et aucun audit complet par lecteur d’écran ne sont revendiqués.

## Paquets locaux licenciés

Paquets reconstruits après les clarifications de routage, par
`package-desktop.ps1 -DryRun` dans `dist/pixel-atelier-1.1.0/`, journal
`package-routage-final-1.1.0.log`. Les deux fichiers ont été relus ; les tailles et
empreintes ci-dessous proviennent de `paquets-final-1.1.0.json` et remplacent celles
du lot précédent.
Le Setup a été compilé ; **il n’a pas été installé sur le poste du propriétaire**.
Ces deux paquets locaux sont **non signés** ; le contrôle Authenticode du Setup
rapporte `NotSigned`.

| Fichier | Taille (octets) | SHA-256 vérifié |
| --- | ---: | --- |
| `AgentCompanyPlatform-Setup-1.1.0-x64.exe` | 24 659 513 | `323c9f34205e20cc5c3c84b553a8d872b443e0b9609deedd1475c10831cd708b` |
| `AgentCompanyPlatform-Portable-1.1.0-x64.zip` | 37 628 270 | `39e5def65b071dd97b0d5d832867100979f8cfc67aaac4ed68e90ae83a226cde` |

Ces empreintes concernent uniquement ce build local avec le décor **LimeZu**.
La CI sans pack embarque le décor **original ACP** ; les empreintes des paquets
CI téléchargés sont consignées dans la section release ci-dessus. Les sources et dérivés LimeZu
restent dans le dossier local ignoré ; aucun ZIP, atlas ou PNG sous licence n'est
joint séparément à la release. Le build qui les incorpore conserve le crédit
« Pixel art : LimeZu — limezu.itch.io ». Une somme SHA-256 vérifie l'intégrité de
la copie ; elle ne remplace pas une signature d'éditeur.

## Portée et limites

| Sujet | Livré ou observé | Limite exacte |
| --- | --- | --- |
| Connexions personnelles | Guides et demande de nouvel inventaire de la même machine | Ni passkey, ni connexion réelle Codex/Claude, ni exécution payante testées ; un HTTP 202 signifie seulement demande en file |
| Railway | Images, procédures et tests isolés | Ce lot n'atteste aucune action de compte, aucun déploiement et aucune recette réelle Railway |
| Machines et comptes | Machine active et états rapportés par Hermes | Une seule machine active Windows ou Linux/Railway ; aucun multi-compte ni plusieurs machines actives ajoutés |
| Discussion et missions successives | Conversation Hermes globale | La Discussion n’est pas automatiquement rattachée au projet ; les missions successives au sein d’un même projet ne sont pas livrées |
| Missions multiples | Projets, cartes et données déjà exposées par Hermes | Les missions multiples du brief restent une extension serveur distincte ; aucun arbre d'agents ou travail simulé |
| Journal durable des outils | Journal existant et métadonnées vérifiées d'une exécution | Aucun journal détaillé durable des appels d'outils ajouté ; les observations sont bornées et n'exposent pas les sorties brutes |
| Mémoire et reprise | Pages et brouillons conservés pendant la navigation | Brouillons en mémoire jusqu'à fermeture ; pas de restauration au redémarrage, ni mémoire sourcée du brief ajoutée |
| Sources et diff | Résumés, branche, commits et comptes de fichiers/lignes disponibles | Ces métadonnées ne remplacent pas la lecture du code ou du diff ; aucun accès arbitraire aux fichiers distants |
| Récupération d'une branche | Guide de génération SSH/bundle, copie, SHA-256 et import Git | Transfert, revue et publication restent manuels ; aucune pièce jointe absente ni téléchargement direct simulé ; une ancienne observation ne prouve pas la présence sur l'exécutant actuel |
| Mise à jour 1.0.x | AppId et réglages conservés, guide pour le même compte et le même mode d'installation | Compatibilité préparée ; installation, mise à jour et détection par l'ancien client non exécutées sur le poste du propriétaire |

Documentation associée : [Pixel Atelier](pixel-atelier.md),
[Assistants](assistants-1.1.md), [mise à jour 1.1](../mettre-a-jour-1.1.md),
[récupération du résultat](../recuperer-resultat.md),
[processus de release](../desktop-release-process.md) et
[processus de mise à jour](../desktop-update-process.md).

## Historique condensé des validations antérieures

Ces résultats conservent leur SHA d’origine ; ils ne remplacent pas les validations
finales de `5d41008`. Les nombres ci-dessous distinguent réussis, ignorés et non
sélectionnés ; aucun échec intermédiaire ne constitue une preuve verte.

| Révision / contrôle | Résultat acquis | Preuve |
| --- | --- | --- |
| `8936dc6` — CI Windows | 1 277 réussis, 109 ignorés, 464 sous-tests, 222,80 s | [Job Windows](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38201805968/job/114656637914) |
| `8936dc6` — CI Ubuntu | 1 330 réussis, 56 ignorés, 464 sous-tests, 175,74 s ; UI, moteur, simulations PowerShell 7/5.1 réussis | [Job Ubuntu](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38201805968/job/114656637842) |
| `8936dc6` — Desktop CI | **success**, 36/36 suites Qt en 100,43 s ; artefact `desktop-ci-38201807959`, ID `11725429165`, 61 204 329 octets | [Run 38201807959](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38201807959) |
| `f54a2c9` — Image exécutant | **success** ; image : 45 réussis en 114,56 s ; root : 842 réussis, 20 ignorés en 157,36 s ; nettoyage validé | [Job exécutant](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38198690654/job/114647015322) |
| `f54a2c9` — Image Hermes | **failure** ; image : 890 réussis ; contrats : 200 réussis, 5 échecs, 19 non sélectionnés en 3 297,83 s | [Run 38198687975](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38198687975) |
| `f54a2c9` — Restauration Hermes | **success** ; 13 réussis, 211 non sélectionnés en 726,62 s ; navigateur : 1 réussi, 10 non sélectionnés en 187,86 s | [Job 114647004002](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38198687975/job/114647004002) |
| `6b0349a` — autres workflows | CI, Desktop et exécutant **success** ; Desktop : 36/36 suites Qt en 101,37 s, paquets produits | [CI](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38197618706), [Desktop](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38197621532), [Exécutant](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38197626161) |
| `6b0349a` — Image Hermes | **failure** ; image : 887 réussis, 3 échecs d’assertions de version ; restauration, navigateur et nettoyage réussis | [Run 38197623916](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38197623916) |

Les trois assertions de version restées à 1.0.1 ont été corrigées par `47e222d`
(journal `f54a2c9`, sans changement produit). Les cinq contrats en échec omettaient
la table d’autorisation propriétaire : `1f4bb8b` configure leurs fixtures via les
véritables routes authentifiées, puis `5d41008` consigne les preuves locales.
Les contrats complets et le navigateur du nouveau run `38205074960` ont depuis
réussi ; son bilan final figure plus haut.

Le précédent contrôle Qt après les guides comptait 36/36 suites en **105,18 s**
(`build-guides-final-1.1.0.log`, `desktop-tests-guides-final-1.1.0.log`). Le passage
intermédiaire suivant attendait les anciens textes de routage ; les assertions
existantes ont été adaptées aux libellés clarifiés, avant les **36/36 en 102,84 s**
rapportés dans le tableau local.

### Commits du lot

| Commit du lot | Objet |
| --- | --- |
| `d3185d9` | Ouverture de 1.1.0 |
| `b7e5b35` | Preuve de terminaison concurrente des processus Windows du poste |
| `45c0691` | Routage du plan Hermes et observations d'exécution contrôlées |
| `c40e4b8` | Workspace Pixel Atelier, guides et parcours natifs |
| `6b0349a` | Journal de la livraison 1.1.0 |
| `47e222d` | Assertions de version des tests Hermes alignées sur la version publiée |
| `f54a2c9` | Journal après correction des assertions, sans changement produit |
| `870b92b` | Correction finale des guides et de la récupération de résultat |
| `8936dc6` | Journal après validation finale des guides |
| `1f4bb8b` | Correction des fixtures de routage et clarifications du parcours |
| `5d41008` | Documentation des validations finales et tête proposée à la livraison |
