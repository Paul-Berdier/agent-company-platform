# Documents de référence du greffon acp-poste et de Hermes pour les tests natifs

## `meta.json`

`meta.json` reproduit la FORME de `GET /api/plugins/acp-poste/v1/meta` telle que la
construit `hermes/plugins/acp-poste/meta.py` (`construire_meta`) à `refonte/hermes` b3faac0 :
mêmes clés de premier niveau, mêmes sous-clés pour `hermes`, `openrpc`, `greffon` et
`machine`. Les VALEURS sont synthétiques, alignées sur `hermes/contrat/HERMES_VERSION`
(Hermes 0.21.5, OpenRPC version 1 et son empreinte, contrat `acp-poste/1`).

Sa forme est comparée à celle que sert l'image de test par le bout en bout local de la
station (voir « Forme vérifiée sur l'image » plus bas).

## Documents des pages de pilotage

Les fichiers suivants sont une conversion MÉCANIQUE en JSON des réponses que les tests de
l'interface web utilisent déjà (même dépôt, aucune valeur retouchée par la station) :

| Fichier | Source | Route |
|---|---|---|
| `projets-vide.json` | `apps/interface/tests/fixtures-projets.ts`, `LISTE_VIDE` | `GET /v1/projets` |
| `projets.json` | `fixtures-projets.ts`, `LISTE` | `GET /v1/projets` |
| `projet-detail.json` | `fixtures-projets.ts`, `DETAIL` | `GET /v1/projets/{id}` |
| `questions.json` | `fixtures-projets.ts`, `QUESTIONS` | `GET /v1/questions` |
| `poste-vide.json`, `poste-releve.json` | `fixtures-projets.ts`, `POSTE_VIDE`, `POSTE_RELEVE` | `GET /v1/poste` (forme de l'étape P4 : `poste` et `catalogue` seulement) |
| `catalogue-profils.json` | `fixtures-projets.ts`, `CATALOGUE_PROFILS` | `GET /v1/catalogue` |
| `lancement.json` | `fixtures-projets.ts`, `LANCEMENT` | `POST /v1/projets` |
| `pause-generale.json` | `fixtures-projets.ts`, `PAUSE_GENERALE` | `pause_generale` de `GET /v1/projets` |
| `refus-aucun-inventaire.json` | `fixtures-projets.ts`, `REFUS_AUCUN_INVENTAIRE` | refus 400 de `POST /v1/projets` |
| `quotas.json`, `quotas-vides.json` | `apps/interface/tests/fixtures-poste.ts`, `FORMES.quotas`, `FORMES.quotas_vides` | `GET /v1/quotas` |
| `poste-non-configure.json`, `poste-a-confirmer.json`, `poste-en-ligne.json` | `fixtures-poste.ts`, `FORMES.poste_non_configure`, `FORMES.poste_a_confirmer`, `FORMES.poste_en_ligne` | `GET /v1/poste` (forme de l'étape P5) |
| `code-enrolement.json` | `fixtures-poste.ts`, `FORMES.code` (code factice) | `POST /v1/poste/enrolement` |
| `refus-empreinte.json` | `fixtures-poste.ts`, `FORMES.refus_empreinte` | refus 409 de `POST /v1/poste/confirmation` |
| `releve-demande.json` | `fixtures-poste.ts`, `FORMES.releve_demande` | `POST /v1/poste/releve` |
| `routage.json`, `routage-vide.json`, `routage-secours.json` | `fixtures-poste.ts`, `FORMES.routage`, `FORMES.routage_vide`, `FORMES.routage_secours` | `GET /v1/routage` |
| `refus-table.json` | `fixtures-poste.ts`, `FORMES.refus_table` | refus 422 de `POST /v1/routage` |
| `sessions.json` | `apps/interface/tests/fixtures.ts`, `SESSIONS` | `GET /api/sessions` de Hermes |

Provenance de ces sources, telle que leurs en-têtes la décrivent : `fixtures-projets.ts` est
relevé le 26/09/2026 sur l'image `acp-hermes-tests:p4g` puis réduit, avec des retouches DITES
dans son en-tête (avancement du second projet, entrées `triage` et `bloquees`, champs ajoutés
par la relecture de P4, écrits d'après le greffon corrigé) ; `fixtures-poste.ts` est capturé
dans l'image construite depuis `39ad0cd` (seul le code d'enrôlement y est factice) ;
`SESSIONS` de `fixtures.ts` est écrit d'après les types du tableau de bord de Hermes.

Conversion : `node --experimental-strip-types` importe les trois modules et écrit chaque
constante telle quelle (`JSON.stringify(valeur, null, 2)`).

## Forme vérifiée sur l'image

Le bout en bout local de la station (`apps/desktop/tests/e2e/e2e_desktop_windows.py`,
étape 9) lit chaque route avec le porteur de la station, aux états où la pile de test
ressemble au document, et exige que CHAQUE clé du document soit servie par l'image avec le
même type JSON (un `null` d'un côté ou de l'autre est accepté ; pour un tableau, le premier
élément est comparé). Les clés en plus côté serveur ne sont pas des écarts.

| Document | État de la pile | Route |
|---|---|---|
| `meta.json`, `projets-vide.json`, `poste-non-configure.json`, `quotas-vides.json`, `routage-vide.json`, `catalogue-profils.json` | au départ, aucun projet ni relevé | `/v1/meta`, `/v1/projets`, `/v1/poste`, `/v1/quotas`, `/v1/routage`, `/v1/catalogue` |
| `projets.json`, `projet-detail.json` | après le lancement d'un projet sur dépôt | `/v1/projets`, `/v1/projets/{id}` |
| `questions.json` | une question ouverte | `/v1/questions` |

Relevé du 02/10/2026 sur `acp-hermes-tests:p8` (construite depuis cette branche) : 9 documents,
434 clés comparées, aucun écart. Limites dites : ce contrôle n'est pas en CI (les exécuteurs
Windows ne font pas tourner les conteneurs Linux) ; il compare des FORMES, pas des valeurs ; les
documents des états qu'il ne monte pas (poste à confirmer ou en ligne, relevé, routage rempli ou
de secours, quotas relevés, refus, code d'enrôlement, sessions) restent ceux des tests de
l'interface web, capturés sur l'image par eux.
