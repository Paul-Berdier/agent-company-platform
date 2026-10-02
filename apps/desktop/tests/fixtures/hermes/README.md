# Documents de référence du greffon acp-poste et de Hermes pour les tests natifs

## `meta.json`

`meta.json` reproduit la FORME de `GET /api/plugins/acp-poste/v1/meta` telle que la
construit `hermes/plugins/acp-poste/meta.py` (`construire_meta`) à `refonte/hermes` b3faac0 :
mêmes clés de premier niveau, mêmes sous-clés pour `hermes`, `openrpc`, `greffon` et
`machine`. Les VALEURS sont synthétiques, alignées sur `hermes/contrat/HERMES_VERSION`
(Hermes 0.21.5, OpenRPC version 1 et son empreinte, contrat `acp-poste/1`).

Limite dite : ce document n'est pas encore capturé sur l'image de test. Le test de contrat
qui comparera la forme servie à ce fichier (`hermes/tests/contrat/test_fixtures_desktop.py`,
cahier P8 § 9.3) arrive avec le bout en bout local de la station.

## Documents des pages de pilotage

Les fichiers suivants sont une conversion MÉCANIQUE en JSON des réponses que les tests de
l'interface web utilisent déjà (même dépôt, aucune valeur retouchée par la station) :

| Fichier | Source | Route |
|---|---|---|
| `projets-vide.json` | `apps/interface/tests/fixtures-projets.ts`, `LISTE_VIDE` | `GET /v1/projets` |
| `projets.json` | `fixtures-projets.ts`, `LISTE` | `GET /v1/projets` |
| `projet-detail.json` | `fixtures-projets.ts`, `DETAIL` | `GET /v1/projets/{id}` |
| `questions.json` | `fixtures-projets.ts`, `QUESTIONS` | `GET /v1/questions` |
| `poste-vide.json`, `poste-releve.json` | `fixtures-projets.ts`, `POSTE_VIDE`, `POSTE_RELEVE` | `GET /v1/poste` |
| `catalogue-profils.json` | `fixtures-projets.ts`, `CATALOGUE_PROFILS` | `GET /v1/catalogue` |
| `lancement.json` | `fixtures-projets.ts`, `LANCEMENT` | `POST /v1/projets` |
| `pause-generale.json` | `fixtures-projets.ts`, `PAUSE_GENERALE` | `pause_generale` de `GET /v1/projets` |
| `refus-aucun-inventaire.json` | `fixtures-projets.ts`, `REFUS_AUCUN_INVENTAIRE` | refus 400 de `POST /v1/projets` |
| `quotas.json`, `quotas-vides.json` | `apps/interface/tests/fixtures-poste.ts`, `FORMES.quotas`, `FORMES.quotas_vides` | `GET /v1/quotas` |
| `sessions.json` | `apps/interface/tests/fixtures.ts`, `SESSIONS` | `GET /api/sessions` de Hermes |

Provenance de ces sources, telle que leurs en-têtes la décrivent : `fixtures-projets.ts` est
relevé le 26/09/2026 sur l'image `acp-hermes-tests:p4g` puis réduit, avec des retouches DITES
dans son en-tête (avancement du second projet, entrées `triage` et `bloquees`, champs ajoutés
par la relecture de P4, écrits d'après le greffon corrigé) ; `fixtures-poste.ts` est capturé
dans l'image construite depuis `39ad0cd` (seul le code d'enrôlement y est factice) ;
`SESSIONS` de `fixtures.ts` est écrit d'après les types du tableau de bord de Hermes.

Conversion : `node --experimental-strip-types` importe les trois modules et écrit chaque
constante telle quelle (`JSON.stringify(valeur, null, 2)`). Le test de contrat sur l'image
(§ 9.3 du cahier) remplacera ces copies par des captures directes.
