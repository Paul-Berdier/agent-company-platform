# ACP 1.1.1 — preuves de livraison

État au 12 octobre 2026 : sources fusionnées dans `main`, tag annoté `v1.1.1`
poussé et quatre workflows complets réussis sur la tête validée. **Desktop Release
a réussi** sur le commit de fusion : 37 suites Qt réussies, paquets téléchargés et
empreintes vérifiées. La release reste **en brouillon, non publiée**. Les paquets
n'ont pas été exécutés ; l'installation et les connexions personnelles n'ont pas
été testées. Les tests ignorés ou non sélectionnés ne sont pas des réussites.

## Sources et livraison

| Élément | Référence ou état |
| --- | --- |
| Base avant fusion | `28692ab00f2fd3940b96ebe88b1501dcb3c3fb6a` |
| Branche de travail | `codex/startup-connections` |
| Ouverture de version | `e3b8009` — 1.1.1 |
| Tête validée | `3749d39566c9c31179b2f2d60d9aa16557794c67` ; produit `09d920e2404bba9b0c9500c135cad18ac6defe65`, puis journal `3749d39` |
| PR | [#30](https://github.com/Paul-Berdier/agent-company-platform/pull/30), fusionnée le 12 octobre 2026 à 10:24:15 UTC |
| CI générale, Desktop CI, Image Hermes, Image exécutant | Quatre workflows manuels complets **réussis** sur la tête validée ; détail ci-dessous. |
| Contrôles avant fusion | Arbres de la tête, de la fusion proposée et de la fusion effective identiques : `f5dc737998e28b5d8a870be7db44ef96598d386d`. |
| Fusion | `9d6eab6883cc117d7fb356d392c1460daf187faf`, le 12 octobre 2026 à 10:24:15 UTC |
| Tag annoté `v1.1.1` | Poussé ; sa cible résolue est le commit de fusion `9d6eab6883cc117d7fb356d392c1460daf187faf`. |
| Desktop Release | [Run 38236135339](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38236135339), **success**, sur `v1.1.1` et `9d6eab6883cc117d7fb356d392c1460daf187faf` ; 37/37 suites Qt, aucun échec, 114,12 s. |
| Release GitHub | [Brouillon 1.1.1](https://github.com/Paul-Berdier/agent-company-platform/releases/tag/untagged-5b35bf8e90e495756eb2), **non publié** : `isDraft=true`, `isPrerelease=false`, `publishedAt=null`. Trois pièces jointes téléchargées sans exécution et vérifiées. |
| Installation et reprise personnelles | **Non exécutées** |

Les quatre workflows complets ont été lancés manuellement avant l'ouverture de
la PR sur la tête exacte ci-dessus. La comparaison des arbres atteste que la
fusion n'a pas changé le contenu validé. Au contrôle de livraison, `main` n'était
pas protégée et aucun ruleset n'était configuré ; aucun contrôle obligatoire n'a
été contourné.

Les exécutions automatiques déclenchées par la PR et par la fusion sont encore
en cours au dernier relevé. Elles sont supplémentaires et ne sont pas comptées
comme réussies ici. La validation avant fusion repose sur les quatre runs manuels
complets de la tête exacte et sur l'identité des arbres vérifiée ci-dessus.

Le correctif maintient un écran pendant la restauration initiale de session,
rouvre la passerelle après le retour d'un verdict compatible et présente depuis
l'accueil la configuration Hermes et les connexions observées des assistants.
Le parcours ChatGPT par code d'appareil concerne le coordinateur Hermes ; les
comptes de l'exécutant restent distincts. Voir le
[guide du correctif](connexions-1.1.1.md).

## Validations locales acquises

Les journaux cités sont dans `apps/desktop/build/verification/pixel-atelier/`.
Les métadonnées de préparation sont dans `livraison-1.1.1-en-cours.json`.

| Contrôle | Résultat acquis | Journal |
| --- | --- | --- |
| Compilation Release Qt 6.8.3 / MSVC | Réussie ; compilation finale et harmonisation des polices réalisées | `build-final-1.1.1.log`, `build-polices-1.1.1.log` |
| Suite native complète, avant la dernière retouche typographique | **37/37 suites**, 141,81 s | `qt-complet-1.1.1.log` |
| Interactions finales avec les polices Windows | **19/19 réussies**, 7,979 s, exécution directe | `interactions-polices-1.1.1.txt` |
| Pages et shell après retouche | `tst_pages_bureau` et `tst_qml_shell` réussis ; captures relues | `qt-visuel-final-1.1.1.log` |
| Interface web | **204 tests réussis** | `interface-1.1.1.log` |
| Moteur gelé | **74 tests réussis** | `engine-1.1.1.log` |
| Budget de fermeture Windows corrigé | **33 tests réussis**, 4,45 s | `windows-tree-budget-1.1.1.log` |
| Annulation réelle d'un arbre de processus, trois essais après correction | **1 test réussi par essai**, 7,56 s / 0,44 s / 7,57 s | `cancellation-budget-final-{1,2,3}-1.1.1.log` |
| Suite Python Windows complète finale | **1 289 réussis, 106 ignorés, 464 sous-tests réussis**, aucun échec, 1 149,98 s | `pytest-final-1.1.1.log` |
| Suite Qt complète finale avec polices Windows | **37/37 réussies**, 121,92 s | `qt-suite-finale-1.1.1.log` |

La suite finale Python et les 37 suites Qt ont réussi après correction. Les
workflows GitHub sont distincts. Les tests et captures utilisent des environnements isolés.

## Contrôles GitHub sur la tête finale

Tous les runs suivants ciblent `3749d39566c9c31179b2f2d60d9aa16557794c67`.

| Workflow | Conclusion acquise | Résultats |
| --- | --- | --- |
| [CI générale 38228748790](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38228748790) | **success** | Python Ubuntu : 1 339 réussis, 56 ignorés, 464 sous-tests (163,69 s). Windows : 1 286 réussis, 109 ignorés, 464 sous-tests (246,20 s). Web : 204 tests ; moteur : 74. Simulations d’installation Windows réussies. |
| [Desktop CI 38228752945](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38228752945) | **success** | Compilation, 37/37 suites Qt (113,71 s), empaquetage à blanc. |
| [Image exécutant 38228759568](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38228759568) | **success** | 45 tests image (113,74 s) ; poste/contrat en root : 851 réussis, 20 ignorés (155,63 s). |
| [Image Hermes 38228756533](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38228756533) | **success** | Image : 890 réussis, 277 avertissements (452,13 s). Contrats : 205 réussis, 19 non sélectionnés (2 753,44 s). Navigateur : 10 réussis, 1 non sélectionné (517,92 s). Restauration : 13 réussis, 211 non sélectionnés (765,04 s). Navigateur R3 : 1 réussi, 10 non sélectionnés (194,63 s). |

Journaux acquis : `ci-generale-1.1.1.log`, `ci-desktop-1.1.1.log`,
`ci-executant-1.1.1.log`, `ci-hermes-38228756533-1.1.1.log` et
`ci-restauration-38228756533-1.1.1.log` dans le dossier de preuves local ignoré.
Le bilan des tests image Hermes est aussi présent dans
`ci-hermes-job-114742712960-1.1.1.log`, ligne 4874 ; ce journal propre au job
complète le journal agrégé. Les noms des journaux locaux ne supposent pas leur
présence dans un autre checkout ; les liens des runs permettent de retrouver la CI.

## Échecs intermédiaires et corrections

La première campagne Python a rendu **2 échecs, 1 278 réussis, 106 ignorés et
464 sous-tests réussis en 881,02 s** (`pytest-1.1.1.log`). Les tests
`test_reponse_hors_contrat_refusee` et
`test_politique_devenue_invalide_ne_publie_plus` ont dépassé des attentes de
publication d'inventaire de 15/20 s, avant leurs assertions métier, pendant une
compilation Qt. La charge concurrente est suspectée, sans cause environnementale
définitivement établie. Tous deux passent dans la campagne suivante.

Cette campagne suivante s'est arrêtée sur **1 échec, 268 réussis, 23 ignorés,
910,73 s** (`pytest-seriel-1.1.1.log`) :
`test_asyncio_cancellation_terminates_the_process_tree`. L'observation
`cancellation-observe-after-verdict-1.1.1.json` montre un Job Object vide mais des
handles de processus encore non signalés au verdict, puis signalés 0,406 s plus
tard sans nouvelle terminaison. Le correctif partage le reliquat du budget
existant de **8 s** entre Job Object et arbre de processus ; l'attente distincte
de **5 s** pour vider le Proactor est conservée. Les preuves de fermeture restent
requises. Les 33 tests et trois essais réels ci-dessus valident cette correction
ciblée. La suite Windows complète finale a ensuite réussi : **1 289 tests et
464 sous-tests réussis, 106 ignorés, aucun échec en 1 149,98 s**
(`pytest-final-1.1.1.log`).

Après la retouche typographique, CTest a échoué une fois sur
`tst_pages_interactions`, sans diagnostic exploitable, tandis que les pages et
le shell passaient (`qt-visuel-final-1.1.1.log`). La reprise directe avec un
journal Qt explicite a réussi **19/19** interactions. Cet échec intermédiaire
est conservé ; aucune cause certaine n'est attribuée à son caractère transitoire.
La suite Qt complète finale avec les polices Windows a ensuite réussi :
**37/37 suites en 121,92 s** (`qt-suite-finale-1.1.1.log`).

## Desktop Release et paquets CI vérifiés

Le workflow [Desktop Release 38236135339](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38236135339)
a réussi sur le commit de fusion `9d6eab6883cc117d7fb356d392c1460daf187faf`,
porté par le tag `v1.1.1` : compilation, **37/37 suites Qt, aucun échec en
114,12 s**, empaquetage et création du brouillon. Journal local :
`apps/desktop/build/verification/pixel-atelier/release-38236135339.log`.

Le [brouillon GitHub](https://github.com/Paul-Berdier/agent-company-platform/releases/tag/untagged-5b35bf8e90e495756eb2)
est associé à `v1.1.1` : `isDraft=true`, `isPrerelease=false`, `publishedAt=null`.
Il reste **invisible dans le bouton de mise à jour du client**. Sa création ne
constitue pas une publication publique.

Les trois pièces jointes ont été téléchargées dans `dist/release-1.1.1-ci/`, sans
exécuter les paquets. Leurs tailles et SHA-256 concordent avec les métadonnées
GitHub ; les deux paquets concordent aussi avec `SHA256SUMS.txt`. Les relevés sont
`dist/release-1.1.1-ci/verification.json` et `release-metadata.json` dans le même
dossier local ignoré. Les binaires sont **non signés** ; le contrôle Authenticode
du Setup donne `NotSigned`, sans certificat signataire.

| Pièce jointe CI | Taille | SHA-256 |
| --- | ---: | --- |
| `AgentCompanyPlatform-Setup-1.1.1-x64.exe` | 24 685 712 octets | `5bb88e8c11e3a12fc46e110ce371ae275d6755bccca6dcc7f2ef8f84512cefc2` |
| `AgentCompanyPlatform-Portable-1.1.1-x64.zip` | 37 665 099 octets | `8bad4957a4e17041c3e075d39fcae8644122633de829e1a708fa6c0900f09f2f` |
| `SHA256SUMS.txt` | 217 octets | `ca6efea3f11b3e14ef66eda78df9230190c5d86ca5a3090d4a089c22536e4d56` |

Ces paquets CI utilisent le décor ACP original. Ils sont distincts des paquets
locaux licenciés LimeZu ci-dessous, dont les empreintes sont différentes.

## Paquet local préparé

Le Setup est compilé et préparé, **non signé et non installé**. Sa présence ne
prouve pas une publication. Références : `package-1.1.1.log`, métadonnées locales
et `dist/startup-1.1.1/SHA256SUMS.txt`.

| Fichier | Taille | SHA-256 |
| --- | ---: | --- |
| `dist/startup-1.1.1/AgentCompanyPlatform-Setup-1.1.1-x64.exe` | 24 689 082 octets | `ef9637ae0b62f7a7221fcafaccd5e6dc97286428fa1d3e9dbe9a5a7c6454dee6` |
| `dist/startup-1.1.1/AgentCompanyPlatform-Portable-1.1.1-x64.zip` | 37 670 804 octets | `500198261cf78818fa404b7a2a73b9c4e2566d19cea05856d3aa7c35f70b7abe` |

Le décor LimeZu reste réservé au build local licencié. Ses sources payantes ne
sont pas versionnées ; la CI et les paquets publics utilisent le décor ACP
original. Les empreintes de release sont relevées dans la section précédente :
les valeurs ci-dessus désignent uniquement les fichiers locaux licenciés LimeZu.
Le Setup local constitue la voie de mise à jour fournie au propriétaire pendant
que la release GitHub reste en brouillon.

## Limites personnelles

La fenêtre personnelle n'a pas été observée : les outils Computer Use échouent
au démarrage (`apply deny-read ACLs`). Le message d'erreur exact de l'utilisateur
reste attendu ; les défauts corrigés ne sont pas attribués à cet incident sans
preuve. La santé publique correcte de Hermes 0.21.5 ne prouve pas sa session.

Aucun compte personnel, parcours payant ou déploiement Railway n'a été utilisé
pour ces validations. Une configuration retrouvée n'atteste pas une réponse du
modèle ; un relevé d'assistants ne garantit pas quotas, routage ou exécution.
La mise à jour personnelle, sa reprise de session et la détection de la release
par l'ancien client restent **non exécutées**.
