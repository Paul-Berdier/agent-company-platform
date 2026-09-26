# Poste connecté côté Hermes (étape P5, première partie)

État du **26 septembre 2026**, branche `refonte/hermes-p5` (empilée sur `refonte/hermes-p4`), version 0.11.0
inchangée. **Rien n'est déployé.** Ce document décrit la **première partie** de P5 : ce que Hermes sait faire
d'un poste Windows connecté (greffon groupé `acp-poste`, contrat partagé, greffon d'interface
`acp-poste-vues`). La **seconde partie** (programme du poste `apps/poste`, installation, compte dédié, sondes
Codex et Claude) est livrée à part ; ici, le poste est joué par un **faux poste** qui parle le vrai protocole.
Références : [plan d'autonomie](autonomie.md) (§ 8, P5), [projets](projets.md) (P4), [image](image.md),
[interface](interface.md), décisions **D48 à D66** ([plan](plan.md) § 1, **non confirmées**) ; cahier de
conception de P5 (brouillon de session `plan_p5.md`, cité « cahier P5 § n »).

## 1. En bref

- **Enrôlement** (D48 à D50) : la page « Poste » crée un **code à usage unique** valable 10 minutes
  (`acpe_…`), affiché une seule fois ; le poste l'échange contre un **jeton machine** (`acpm_…`, 256 bits) que
  Hermes ne rend qu'une fois, dans la réponse d'enrôlement, et dont il ne garde que le SHA-256. Le poste
  reste « À confirmer » (ni présence, ni inventaire, ni ordre) tant que vous n'avez pas recopié son
  **empreinte** `XXXX-XXXX` sur la page. Un seul poste actif (index unique en base).
- **Authentification** : un fournisseur de jeton du tableau de bord de Hermes (`acp-poste-machine`), sur
  **trois chemins exacts** seulement (`/api/plugins/acp-poste/machine/v1/{enrolement,reclamer,inventaire}`) ;
  chaque gestionnaire revérifie le fournisseur et la portée. Le reste du tableau de bord ne l'accepte pas.
- **Long-poll** `reclamer` (25 s) : présence, ordres (`releve`, `pause`, `reprise`), révocation vue en moins
  d'une seconde par un poste en attente ; `carte` toujours `null` en P5 (l'exécution arrive en P6).
- **Inventaire** du poste (contrat `acp_poste_contrat.inventaire` étendu, P4 intact) : relevés Codex et
  Claude, quotas, versions, connexions, bac à sable, politique de `poste.toml`, dépôts ; tout ou rien, un
  par minute au plus, jamais d'identifiant de compte.
- **Routage** : seulement sur le dernier relevé **et** la politique du poste ; « Liste de secours » de Codex
  refusée tant que vous ne l'avez pas acceptée (D58) ; efforts Claude inconnus refusés avant usage (D59) ;
  table validée tout ou rien.
- **Pages** : un onglet « Poste » à trois vues (état, routage, quotas), pensé d'abord pour le téléphone
  (D62), sans aucun bouton qui fasse semblant.
- **Présence** persistée, avec une **grâce de redémarrage** : un redémarrage de Hermes ne notifie pas
  « Poste hors ligne ».

## 2. Protocole `acp-machine/1`

Contrat partagé : `hermes/plugins/acp-poste/contrat/acp_poste_contrat/machine.py` (modèles pydantic,
`extra="forbid"`, messages français), importé par le greffon **et** par le poste ; exemples de référence dans
`hermes/tests/outils/fixtures_machine/` (jeton et empreinte en gabarits `__JETON_MACHINE__`,
`__EMPREINTE__`, jamais une valeur réelle).

| Route (POST, JSON) | Porteur | Réponse |
|---|---|---|
| `…/machine/v1/enrolement` | code `acpe_…` (portée `enrolement`) | 201 : `machine_id`, `jeton` (la seule fois), `empreinte`, `etat` (`a_confirmer`), `protocole` |
| `…/machine/v1/reclamer` | jeton `acpm_…` (portée `machine`) | 200 : `etat_machine`, `pause_reclamations`, `ordres`, `carte: null`, `remplace`, `prochaine_attente_s` |
| `…/machine/v1/inventaire` | jeton `acpm_…` | 200 : `recu_le`, relevés enregistrés par voie, alertes ; 429 avec `Retry-After` avant une minute |

- **Jetons** : `acpm_` ou `acpe_` suivi de 43 caractères base64url (`secrets.token_urlsafe(32)`). Empreinte
  courte affichée : les 8 premiers chiffres hexadécimaux du SHA-256, `XXXX-XXXX`.
- **Vérification** (`noyau/jeton_machine.py`, sur le modèle du greffon `drain` de Hermes) : forme d'abord (un
  jeton OIDC n'ouvre jamais la base), SHA-256, lecture **seule** de la base du greffon (`mode=ro`, 0,25 s),
  `hmac.compare_digest` sur **chaque** ligne candidate sans sortie anticipée. Toute exception de lecture
  devient `ProviderError` (503) : laissée à la couture, elle deviendrait un 401 que le poste prendrait pour
  une révocation.
- **Gardes de chaque gestionnaire** : principal présent, fournisseur `acp-poste-machine` (403
  `mauvais_fournisseur`), portée (403 `code_enrolement_seulement` ou `jeton_machine_ici`), JSON exigé (415),
  taille (4 Kio pour l'enrôlement et `reclamer`, 256 Kio pour l'inventaire : 413), majeure du protocole (409
  `protocole_incompatible`), modèle du contrat (422 `requete_refusee`, message français). Réponses
  `Cache-Control: no-store`.
- **Erreurs** : `{"detail": {"code", "message"}}` en français, codes fermés (`CODES_ERREUR` du contrat).
  Seule exception : le 401 **de la couture de Hermes** (`{"error": "unauthenticated", "detail":
  "Unauthorized"}`, en anglais, avant le greffon), ambigu par nature (jeton inconnu, révoqué hors ligne, ou
  fournisseur absent) ; le poste le traite selon D65 (jeton gardé, arrêt, nouvel essai). Le greffon ne rend
  le 401 explicite `poste_revoque` que s'il a lui-même relu la révocation (attente en cours, ou révocation
  entre la couture et le gestionnaire).
- **Long-poll** : un `asyncio.Event` par poste, dans le seul module des routes ; la plus récente attente
  gagne (l'ancienne rend `remplace: true` ; plus de 5 remplacements par minute ajoutent à la méta l'alerte
  « Deux processus semblent utiliser le même jeton machine. ») ; réveil depuis un fil par
  `call_soon_threadsafe` (ordre, révocation, pause générale) ; relecture de la base toutes les 2 s dans un fil
  (un autre processus peut avoir écrit) ; aucun fil tenu pendant l'attente. Déconnexion du poste : lecture
  bornée à 50 ms de `request.receive()`, parce que `request.is_disconnected()` ne voit rien derrière les
  intergiciels de Hermes (§ 11).
- **Ordres** : `releve` (« Relever maintenant »), `pause` et `reprise` (pause générale de P4) ; livrés par
  `reclamer`, acquittés au passage suivant (ou par l'inventaire qui sert un `releve`), abandonnés après 60 min.
- **Routes réservées à P6** (battements, cartes) : **non enregistrées** ; un appel rend le 401 de la couture.

## 3. Base du greffon : schéma v2

`noyau/base.py`, migration **idempotente** de v1 (P4) sous `BEGIN IMMEDIATE` : colonnes ajoutées après lecture
de `PRAGMA table_info`, puis version `1` → `2`. Tables ajoutées : `machines` (identifiant `m` + 11 hex, nom,
SHA-256 du jeton, état `a_confirmer`/`actif`/`revoque`, confirmation et révocation datées et signées, dernière
requête, politique annoncée), `enrolements` (SHA-256 du code, expiration, usage), `ordres`, `inventaires`
(contenu validé, empreinte). `releves` gagne `machine_id`, `accepte_le`, `accepte_par`. Index unique partiel
`un_seul_poste_actif`. Réglages ajoutés (D63) : `longpoll_attente_s` 25, `enrolement_validite_s` 600,
`inventaire_intervalle_min_s` 60, `ordre_expiration_s` 3600 ; `seuil_hors_ligne_s` (180) et `releve_perime_s`
(7 200) viennent de P4. Les fonctions `…_dans(conn)` n'ouvrent jamais de transaction : la route en ouvre une.

## 4. Inventaire

Contrat `acp_poste_contrat.inventaire` **étendu sans rien casser de P4** (un relevé de P4 en base se relit) :

- `ModeleReleve` : `modele` admis avec crochets (`opus[1m]`), `cache`, `remplace_par`, `retrait_le`, `nature`,
  `resolution_documentee`, `source_efforts` ; `isDefault` et `supportedReasoningEfforts` peuvent être `null`
  (inconnu, jamais inventé) ;
- `Releve` : compteurs (16 au plus), `origine_liste`, `etat`, `detail`, `documentation_lue_le`,
  `resolutions_observees` (réservé à P6) ; un relevé de source `poste` exige origine et état ; liste de
  modèles vide seulement pour un relevé en échec ;
- `InventairePoste` : protocole `acp-machine/1`, relevés (source `poste`), `BacASableCodex` (`ecriture_admise` vrai seulement
  si le mode est prouvé : D60), `Connexions`, `VersionCli`, `PolitiquePoste`, `InfosPoste`, dépôts ;
- `identifiant_trouve()` : garde « aucun identifiant » (adresse, identifiant de compte, jeton) appliquée
  **à la réception** aussi ; les motifs de secrets (`motifs_secrets.py`, jetons `acpm_`/`acpe_` compris) sont
  désormais dans le contrat, partagés avec `scripts/balayer_secrets.py` (test de parité).

Réception (`noyau/inventaire.py`) : poste actif seulement (403 `poste_a_confirmer` sinon), une par minute sauf
ordre `releve` livré (429 et `Retry-After`), validation par le contrat, alertes françaises, relevés rangés par
voie (purge qui épargne les relevés cités par une table ou une surcharge), le tout sous **une** transaction.

## 5. Présence

`noyau/presence.py` : seuls les postes **actifs** comptent (un poste révoqué perd sa ligne de présence ; le
poste simulé de P4 reste admis). État du poste : `non_configure`, `a_confirmer`, `en_ligne`, `hors_ligne`,
`revoque`. **Grâce de redémarrage** : l'absence se compte depuis le plus récent de la dernière vue, du
démarrage du tableau de bord (écrit à l'import des routes) et du démarrage de la passerelle ; l'émetteur de P4
n'envoie qu'**une** notification « Poste hors ligne » par absence.

## 6. Routage

Ce que P5 ajoute à la résolution de P4 (`noyau/routage.py`, cahier P5 § 12.4), dans cet ordre, chacun avec un
refus français :

1. `voie_indisponible` : le dernier relevé de la voie est en échec (il remplace le précédent, qui ne reste
   jamais routable) ;
2. `voie_non_connectee` : la CLI n'est pas connectée au compte de l'abonnement ;
3. `liste_de_secours` (Codex) : liste de secours, sauf relevé `identique_au_catalogue_embarque` **accepté**
   par vous, relevé par relevé (D58) ;
4. `cli_hors_version` : version de la CLI hors de la version testée ;
5. `interdit_par_le_poste` : exécutant, modèle ou alias, effort ou palier refusé par `poste.toml` ; Hermes ne
   peut pas le lever ;
6. `efforts_inconnus` : efforts non documentés (Claude) refusés avant usage.

Badges par voie : « Relevé du compte », « Liste de secours », « Liste de secours probable », « Relevé accepté
par vous », « Alias documentés », « Inconnu ». Table de routage : suggestion construite sur les seuls champs
relevés (aucune pour Claude : `isDefault` nul, D59), validation **tout ou rien** (422 `table_refusee` avec la
liste des refus, 409 `releve_change` si le relevé a changé depuis l'affichage), état `non_validee`,
`validee`, `a_revalider`. Politique de Hermes : lever un interdit exige la phrase « J'accepte une dépense hors
enveloppe ». Surcharges globales créées, listées, désactivées.

## 7. Quotas

`noyau/quotas.py`, `GET /v1/quotas` : par voie, les compteurs du **dernier** relevé servis sous la forme
`SubscriptionQuotaView` du contrat (rien d'estimé), `inconnu` sans relevé, `perime` au-delà de 2 h, le détail
d'un relevé en échec, la source (Codex : app-server ; Claude : ligne d'état de vos sessions, D56) ; Hermes :
« même enveloppe que Codex » seulement si `poste.toml` le déclare, sinon « Inconnu ».

## 8. Routes du propriétaire

Session du tableau de bord et règles d'écriture de P4 (JSON exigé, `Origin` contrôlé), `/api/plugins/acp-poste` :

| Route | Rôle |
|---|---|
| `GET /v1/poste` | état, poste courant, dernier inventaire, alertes, ordres en attente (remplace la route de P4) |
| `POST /v1/poste/enrolement` | 201, code rendu une fois (`no-store`) ; 409 si un poste est actif |
| `POST /v1/poste/confirmation` | empreinte recopiée (casse indifférente) ; 409 `empreinte_differente` |
| `POST /v1/poste/revocation` | motif obligatoire ; réveille l'attente du poste |
| `POST /v1/poste/releve` | 202, ordre `releve` (« en attente du poste » s'il est hors ligne) |
| `GET`/`POST /v1/routage` | vue ; validation de la table |
| `POST /v1/routage/politique` | efforts et paliers de Hermes (phrase de confirmation pour lever) |
| `POST /v1/routage/surcharges`, `…/{id}/desactiver` | surcharges globales |
| `POST /v1/routage/releve-accepte` | acceptation d'un relevé `identique_au_catalogue_embarque` |
| `GET /v1/quotas` | § 7 |

La pause générale (`/v1/pause`, P4) envoie aussi l'ordre `pause` ou `reprise` au poste actif. Bloc `machine` de
`/v1/meta` : fournisseur et chemins à jeton **dans le processus du tableau de bord**, fournisseurs de connexion,
postes par état, codes utilisables, dernier inventaire ; alertes (fournisseur ou chemins absents, aucun
fournisseur de session, hôte nommé `acp-poste`, deux processus du poste).

## 9. Onglet « Poste » (greffon d'interface `acp-poste-vues`)

Sources `apps/interface/src/poste/`, bundle committé dans `hermes/plugins/acp-poste-vues/dashboard/dist/` ;
onglet « Poste » après « Projets », icône `Monitor` (D62) ; détail : [interface.md](interface.md) § 11.

- **Poste** : état (en ligne, hors ligne depuis, à confirmer, révoqué), « Générer un code d'enrôlement »
  (code, « Copier », commande `acp-poste enroler`, compte à rebours ; gardé seulement dans l'état du
  composant, jamais stocké), confirmation de l'empreinte, révocation avec motif, « Relever maintenant »,
  cartes de l'inventaire (compte d'exécution, bac à sable, connexions, versions, dépôts, politique) ;
- **Routage** : badges par voie, classes avec leur état, suggestion appliquée puis validée, refus rendus tels
  quels, politique, surcharges, acceptation d'un relevé ;
- **Quotas** : jauges, seuil de 90 %, source, « Inconnu » ou « Périmé » sinon.

Toute valeur venue de l'API est marquée `data-acp-donnee` ; tout autre texte vient du catalogue français
(`src/chaines.ts`). Sondage de 15 s tant que la page est visible ; aucun `fetch` direct, aucun stockage local.

## 10. Limites dites

- Le poste réel n'existe pas encore de ce côté : tout est prouvé avec un **faux poste**
  (`hermes/tests/outils/faux_poste.py`) qui parle le vrai protocole au vrai tableau de bord.
- Le 401 de la couture de Hermes est en anglais et ambigu : c'est le comportement de Hermes 0.21.5, avant le
  greffon ; le poste doit s'en accommoder (D65).
- L'exécution (cartes, battements, résolutions observées) est réservée à P6 : `carte` vaut toujours `null`.
- Les quotas Claude restent « Inconnu » tant que la ligne d'état de vos sessions n'est pas relevée par le
  poste (D56).
- Un seul poste actif (D50).
- La persona (`SOUL.md`) et la skill `acp-profils` disent encore que le poste « n'est pas encore branché » et
  qu'un projet sur dépôt attend « un poste connecté (étape P5) » : c'est vrai tant que le poste réel n'est pas
  livré ; à revoir avec la seconde partie de P5.

## 11. Écarts au cahier, justifiés

| Écart | Raison |
|---|---|
| Décisions numérotées **D48 à D66** au lieu de D40 à D58 | D40 à D47 existent déjà (P4) ; même ordre, correspondance dans [plan.md](plan.md) § 1 |
| Exemples du protocole sous `hermes/tests/outils/fixtures_machine/` | lus par les tests de l'image **et** du contrat ; le poste les lira depuis le même dépôt |
| Faux poste en HTTP sur la boucle locale du conteneur, pas derrière le bord TLS | le chemin TLS est déjà prouvé par la connexion de P2 ; le faux poste prouve le protocole et la couture de Hermes |
| Déconnexion par une lecture bornée de `request.receive()` | `request.is_disconnected()` ne voit rien derrière les `BaseHTTPMiddleware` de Hermes (constaté : attente non libérée) |
| Un témoin « suppression de la présence **et** filtre des postes actifs » | chacune seule est rattrapée par l'autre ; le témoin retire les deux |
| Captures du navigateur avec un code d'enrôlement jetable visible | code de la pile de test, expiré et détruit avec elle |

## 12. Preuves locales (26/09/2026, Windows 10, Docker 29.5.3, Python 3.12.10 python.org, pytest 9.1.1, Node 24.19.0, Chromium de Playwright déjà présent)

Suite dans l'image de test (`acp-hermes-tests`) au fil des commits de travail. Pour les deux premiers, l'image a
été construite depuis l'arbre de travail validé juste avant le commit ; à partir de `9a03014`, depuis le commit
lui-même (`git archive`) :

| Commit | Image construite depuis | Suite dans l'image |
|---|---|---|
| `e51c6a1` contrat | arbre avant le commit | 511 réussis (5 min 11 s) ; le contrat a ses tests au dépôt |
| `8972503` schéma v2 | arbre avant le commit | 538 réussis (5 min 24 s) |
| `9a03014` jeton machine | le commit | 555 réussis (5 min 38 s) |
| `200b579` routes du poste | le commit | 582 réussis (6 min 10 s) |
| `74f65e9` routage | le commit | 602 réussis (6 min 24 s) |
| `39ad0cd` routes du propriétaire | le commit | 619 réussis (6 min 24 s) |
| `4cf6795` pages | le commit | 619 réussis (6 min 31 s) |

Les commits suivants (corrections de l'interface, contrat, navigateur, témoins) sont couverts par la validation
finale (§ 12 bis), faite sur l'arbre complet.

Autres relevés :

- **Vitest** (`npm test --prefix apps/interface`) : **110 réussis** (16 fichiers), dont 17 pour les vues
  du poste (formes relevées sur l'image de `39ad0cd`) ;
- **contrat du protocole** (`test_machine_contrat.py`, pile s6 complète, faux poste) : **11 réussis**
  (2 min 15 s) : 401 de la couture sans jeton, avec un jeton OIDC ou un jeton mal formé ; bloc `machine` de la
  méta ; enrôlement, empreinte, confirmation ; route de P6 non enregistrée ; inventaire visible dans les trois
  vues ; projet sur dépôt accepté après inventaire ; ordre `releve` → inventaire en **0,41 s** ; révocation vue
  par le poste en attente en **0,38 s** (le faux poste efface alors son jeton), puis, avec une copie de ce
  jeton, 401 de la couture ; **une** notification
  « Poste hors ligne » par absence ; redémarrage de la pile : absence de **15 s** au-delà d'un seuil de 10 s,
  **aucune** notification ; aucun jeton, aucun code ni préfixe `acpm_`/`acpe_` dans les journaux de la pile
  (10 818 caractères), la base (18 561) ni le journal du faux poste (1 140) ;
- **dans l'image** : `verify_token` p50 **0,391 ms**, p99 **0,926 ms** sur 1 000 appels ; réveil d'une
  attente par un ordre : **34 à 82 ms** ; attente libérée **2,01 s** après la coupure du poste ;
- **navigateur** (`test_poste.py`) : **1 réussi** (55 s), bureau puis téléphone, 10 captures ;
- **témoins négatifs** (`IMAGE=acp-hermes-tests:<étiquette> bash scripts/temoins_negatifs_p5.sh`) : **28
  protections** retirées une à une, **28 fois** des tests en échec, 0 anomalie ;
- suite du dépôt, contrôles de version, de gel du moteur, du catalogue et des secrets, contrat complet et
  navigateur complet : § 12 bis.

### 12 bis. Validation finale

Sur l'arbre final (du 26/09/2026, 22 h 03 à 22 h 51, heure de Paris), images reconstruites depuis cet arbre :
`acp-hermes:p5o` (`sha256:0a1f62f5…`), `acp-hermes-tests:p5o` (`sha256:91b32179…`), `acp-identite:p5o`
(`sha256:5bc21919…`).

```sh
docker build -f hermes/image/Dockerfile -t acp-hermes:p5o hermes
docker build -f hermes/tests/Dockerfile --build-arg IMAGE_ACP=acp-hermes:p5o -t acp-hermes-tests:p5o hermes/tests
docker build -t acp-identite:p5o identite
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site   acp-hermes-tests:p5o -m pytest -q -rA -p no:cacheprovider /opt/acp-tests/image
PYTHONUTF8=1 MSYS_NO_PATHCONV=1 ACP_IMAGE=acp-hermes:p5o ACP_IMAGE_TESTS=acp-hermes-tests:p5o   ACP_IMAGE_IDENTITE=acp-identite:p5o python -m pytest -p no:cacheprovider -s -v -rA hermes/tests/contrat
PYTHONUTF8=1 MSYS_NO_PATHCONV=1 ACP_IMAGE_TESTS=acp-hermes-tests:p5o ACP_IMAGE_IDENTITE=acp-identite:p5o   ACP_E2E_OBLIGATOIRE=1 ACP_E2E_CAPTURES=<dossier> python -m pytest -p no:cacheprovider -s -v -rA hermes/tests/e2e
python -m pytest -q -p no:cacheprovider
python scripts/check_version.py ; python scripts/check_engine_frozen.py
python scripts/verifier_catalogue.py ; python scripts/balayer_secrets.py
npm test --prefix apps/interface ; npm run check --prefix apps/interface ; git diff --check
```

| Suite | Résultat |
|---|---|
| Dans l'image | **619 réussis**, 0 échec (6 min 03 s) ; `verify_token` p50 0,405 ms, p99 1,037 ms ; réveil par un ordre 88 ms ; attente libérée 2,01 s après la coupure |
| Contrat complet | **150 réussis**, 0 échec (35 min 58 s) : image 37, identité 41, sans shell 23, projets 21, **protocole du poste 11**, catalogue 10, interface 4, IaC Railway 3 ; ordre `releve` → inventaire 0,41 s ; révocation vue en 0,37 s ; redémarrage : absence de 16 s (seuil 10 s), aucune notification ; aucun jeton ni code (10 819 caractères de journaux, 18 561 de base, 1 137 de journal du faux poste) |
| Navigateur | **7 réussis** (5 min 24 s), dont `test_poste.py` |
| Dépôt | **437 réussis** (37 s) ; version, gel du moteur, catalogue (21 skills), secrets (12 motifs) : code 0 |
| Interface | Vitest **110 réussis** (16 fichiers, dont 17 pour l'onglet Poste) ; `npm run check` : 8 fichiers de greffons à jour |
| Hygiène | `git diff --check` propre ; LF ; aucun `Co-Authored-By` ; aucun fichier `.claude` |

Captures de `test_poste.py` (pleine page, non committées : D17), SHA-256 :

| Capture | Taille | SHA-256 |
|---|---|---|
| `bureau-01-poste-non-configure.png` | 1440 × 1041 | `c8d4d809b201c445…` |
| `bureau-02-routage-inconnu.png` | 1440 × 4275 | `784736a0f07c015e…` |
| `bureau-03-poste-code.png` | 1440 × 1041 | `fc8af965b2e904fb…` |
| `bureau-04-poste-a-confirmer.png` | 1440 × 1539 | `b807d5f65fde8a35…` |
| `bureau-05-poste-en-ligne.png` | 1440 × 1674 | `3ba6dc5d5abd2cbc…` |
| `bureau-06-routage.png` | 1440 × 5051 | `1cb430fa96aed541…` |
| `bureau-07-quotas.png` | 1440 × 1041 | `42cd631c2e9bfc29…` |
| `telephone-01-poste-en-ligne.png` | 390 × 2467 | `a4b2c654fa8eaa42…` |
| `telephone-02-routage.png` | 390 × 6639 | `247cf2c5129b75e8…` |
| `telephone-03-quotas.png` | 390 × 1440 | `b5dbf98ecd673f32…` |

L'arbre final est celui de `f3eec31` plus les commentaires de code qui citent les décisions sous leur numéro du
plan (D48 à D66) ; le commit de documentation n'ajoute que de la documentation et le test des décisions de P5
(compris dans les 437 du dépôt).

## 13. Intégration continue

Branche `refonte/hermes-p5` poussée le 26/09/2026, sommet `0a458cd`, **verte** :

- `ci.yml` [36271372881](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36271372881) **succès** : poste Windows (windows-2022) **437 réussis** ; poste
  Linux **428 réussis, 9 ignorés** (les 9 tests propres à Windows) ; interface **110** (16 fichiers), bundles à
  jour ; moteur **74**, gel du moteur et balayage des secrets verts ;
- `image.yml` [36271372764](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36271372764) **succès** (37 min) : `hermes plugins compat` vert (témoin code 1) ;
  sonde réelle de context7 connectée (1 478 ms) ; **619** réussis dans l'image (3 min 57 s ; `verify_token` p50
  0,213 ms, p99 0,245 ms ; réveil par un ordre 57 ms ; attente libérée 2,00 s après la coupure) ; **150** au
  contrat (26 min 54 s), dont les 11 du protocole du poste (ordre `releve` → inventaire 0,14 s ; révocation
  vue en 0,13 s ; redémarrage : absence de 22 s au-delà d'un seuil de 10 s, aucune notification ; aucun jeton
  ni code dans 10 949 caractères de journaux) ; **7** au navigateur (4 min 13 s), dont `test_poste.py`.

## 14. Non prouvé

- Un **vrai poste** Windows (seconde partie de P5), un vrai Codex, un vrai Claude Code, de vrais comptes :
  aucun ; les relevés viennent d'exemples manifestement factices.
- Les routes machine **derrière le bord TLS** de Railway (en-têtes, délais du proxy sur un long-poll de 25 s) :
  à mesurer au premier déploiement.
- Railway : rien n'est déployé.
- Le comportement de la couture de Hermes au-delà de la version épinglée (0.21.5).

## 15. Décisions restantes

D48 à D66 ([plan.md](plan.md) § 1), **non confirmées**. Recommandation par défaut : garder les choix appliqués.
À confirmer en priorité : **D48** (code d'enrôlement plutôt que jeton affiché), **D49** (empreinte à
recopier), **D58** (liste de secours refusée sans votre acceptation), **D60** (écriture Codex refusée sans
preuve du mode) ; puis **D51** et **D52**, qui touchent votre PC (seconde partie).
