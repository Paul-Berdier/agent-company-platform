# Contrats proposés du chantier « atelier » : lots C, D et E

État du 11 octobre 2026. **Rien de ce document n'est implémenté côté serveur dans ce chantier.** Le greffon
`acp-poste`, son contrat partagé, l'exécutant et `apps/poste` sont identiques au commit `85b458b` (ACP 1.0.1) :
`git diff --stat 85b458b -- hermes/plugins/acp-poste apps/poste executant hermes/tests` est vide le 11 octobre 2026,
arbre de travail compris. Ce document propose des formes de données, de routes et de protocole pour les lots C, D et
E ; chacune attend la validation du propriétaire. Il ne crée aucune décision numérotée.

Contexte : état réel, matrice des écarts et plan des lots dans [atelier.md](atelier.md) ; décisions D165 à D169 dans
[plan.md](plan.md), § 1, sous-section « Chantier « atelier », 11 octobre 2026 ». D166 (vocabulaire) et D168 (« Auto »
par défaut) sont des choix de conception, à confirmer.

**Convention de preuve.** Chaque `chemin:ligne` a été relu le 11 octobre 2026 ; il vaut à `85b458b` et dans l'arbre de
travail, ces fichiers n'ayant pas changé. Préfixes abrégés :

| Préfixe écrit ici | Chemin réel |
|---|---|
| `noyau/`, `dashboard/`, `meta.py`, `garde_execution.py` | `hermes/plugins/acp-poste/…` |
| `contrat/` | `hermes/plugins/acp-poste/contrat/acp_poste_contrat/` |
| `poste/` | `apps/poste/src/acp_poste/` |
| `tests-image/` | `hermes/tests/image/` |

Tout autre chemin part de la racine du dépôt. Vocabulaire (D166) : **mission** = un projet du greffon (table
`projets`) ; **projet durable** = le regroupement proposé au § 2 ; **tâche** = carte kanban ; **exécution** = run
kanban.

Sommaire : § 1 règles communes · § 2 projet durable · § 3 missions · § 4 journal d'activité · § 5 états d'agent ·
§ 6 routage enrichi · § 7 comptes · § 8 sous-agents natifs · § 9 extensions du § 19 du brief · § 10 ordre de livraison.

---

## 1. Règles communes

### 1.1 `acp-poste/1` : ajouts annoncés dans `/v1/meta`

- Le contrat s'appelle `acp-poste/1` (`meta.py:21`). Les ajouts des étapes P3, P4, P5 et P7 y sont commentés
  « contrat acp-poste/1 inchangé » (`meta.py:537-549`), par exemple `"accueil": True` (`meta.py:546`) et le bloc `flux`
  (`meta.py:549`).
- La station lit la clé `accueil` avant d'appeler les routes de P7. Sans elle, elle dit « Non disponible sur ce
  serveur » (`apps/desktop/src/api/ClientGreffonPoste.cpp:39-52`, `124-130` ; D159).
- Le lancement refuse tout champ inconnu, en 400 (`dashboard/plugin_api.py:245-247`), comme les routes qui passent par
  `_champs` (`dashboard/plugin_api.py:933-937`). D'autres routes d'écriture ignorent un champ en trop : pause, reprise,
  réponse, triage, pause générale (`dashboard/plugin_api.py:276-338`). Un client n'envoie donc un champ nouveau
  qu'après l'avoir vu annoncé.
- Ajouter un champ à une réponse reste compatible. Renommer ou retirer un champ est une rupture : 2.0.0 (D130).
- Règle proposée : **une clé par capacité** dans `/v1/meta` (`regroupements`, `missions`, `activite`, `modes_routage`).
  Clé absente : capacité non offerte. Clé illisible : « Inconnu ».

### 1.2 `acp-machine/1` : jamais un champ ajouté en silence

- Les deux côtés valident avec `extra="forbid"` (`contrat/machine.py:17-18` ; `contrat/inventaire.py:101-119`). Un
  champ nouveau dans une réponse ferait refuser cette réponse par un exécutant déjà déployé.
- Le greffon refuse en 409 `protocole_incompatible` tout protocole d'une autre majeure que 1
  (`dashboard/plugin_api.py:482-484`). L'exécutant en fait un refus définitif et s'arrête
  (`poste/protocole.py:83`, `143` ; `poste/service_executant.py:187-189`).
- Toute extension passe donc par une **négociation de version** (`acp-machine/2`, § 4.8). Le greffon est livré d'abord ;
  l'exécutant ensuite.

### 1.3 Schéma v5 : additif, dans l'ordre K21

- Aujourd'hui : `VERSION_SCHEMA = "4"` (`noyau/base.py:56`). `migrer()` fait tout sous une seule transaction
  `BEGIN IMMEDIATE`, de façon idempotente (`noyau/base.py:478-509`).
- Ordre K21 : les colonnes s'ajoutent **après** les reconstructions (`noyau/base.py:33-40`, `306`, `500`). Une
  reconstruction ne recopie que les colonnes de sa forme explicite (`DEMANDES_V3`, `noyau/base.py:258-284`). Toute
  reconstruction v5 listerait donc les colonnes v1 à v5.
- Une contrainte `CHECK` élargie impose une reconstruction (`noyau/base.py:27-31`). Les propositions des § 2 à § 6
  l'évitent : tables nouvelles, colonnes sans contrainte resserrée. Seule l'origine `recurrence` du § 9 en exigerait
  une.
- Mécanique : `SCHEMA_V5` et `COLONNES_V5` placés après `RECONSTRUCTIONS_V4` (`noyau/base.py:504-506`) ;
  `VERSION_SCHEMA = "5"` ; `'4'` ajouté à l'`UPDATE` de version (`noyau/base.py:508-509`) ; tables nouvelles dans
  `TABLES` (`noyau/base.py:328-333`) ; réglages nouveaux dans `REGLAGES_PAR_DEFAUT` (`noyau/base.py:337-373`), sans
  quoi `poser_reglage` les refuse (`noyau/base.py:528-530`).
- SQLite : `ALTER TABLE … ADD COLUMN` ne porte pas `UNIQUE` ; on passe par un index unique partiel, comme
  `un_seul_poste_actif` (`noyau/base.py:177`). Une colonne `REFERENCES` ajoutée vaut `NULL` par défaut. La connexion,
  ouverte par Hermes (`ka.plugin_db`, `noyau/base.py:397`), tourne en `foreign_keys=ON`
  (`tests-image/test_migration_v2.py:128` ; `noyau/routage.py:130-132`).
- Retour arrière : une version antérieure du greffon ne refuse pas un schéma plus récent
  (`docs/exploitation.md:447-449`). Le v5 doit donc rester lisible par le code v4 : aucune colonne renommée ni
  retirée, aucune contrainte resserrée.
- Si les lots C, D et E sont livrés séparément : une version de schéma par lot (v5, v6, v7), chacune additive.
- Tests à mettre à jour : la version `"4"` est figée dans `tests-image/test_migration_v2.py:53`, `57`, `100`,
  `test_migration_v3.py:69`, `134`, `test_migration_v4.py:75`, `151`, `176` et `test_projets_base.py:16`, `27`.
  `test_empreinte_volume.py:239` pose aussi `'4'` à la main. Base neuve et bases migrées doivent
  garder le même schéma (`tests-image/test_migration_v4.py:134-153`). Un `test_migration_v5.py` reprend les trois
  motifs de v4 : idempotence, deux processus concurrents (`:156`), compteurs `AUTOINCREMENT` gardés (`:102`).
- Montée de données : job « montee » d'`image.yml` (entrée `ref_avant`, `.github/workflows/image.yml:107`, `123`)
  depuis `85b458b` (schéma 4). Résultat attendu : « migration de schéma : oui ».
- Les tests du noyau ne tournent que dans l'image de test (`tests-image/conftest.py:1-11`) ; la CI fait foi.

### 1.4 Ce qui ne change pas

- Aucun outil nouveau pour l'agent. La garde admet 33 noms exacts (`garde_execution.py:63-86`) ; l'égalité avec les
  outils du greffon est testée (`tests-image/test_sans_shell.py:444-451`). Chaque geste nouveau est une route du
  propriétaire, derrière la session et la garde d'écriture (`dashboard/plugin_api.py:174-199`).
- Le flux reste une invalidation : aucune donnée métier n'y passe (`noyau/flux.py:3-5` ; D96).
- Comptes et Railway restent des gestes du propriétaire (D83, D84, D92 ; § 7).

---

## 2. Projet durable (lot C, D166)

### 2.1 Forme proposée

Une mission est déjà une ligne `projets` complète : objectif, état, tours, plafonds, tableau propre
(`noyau/base.py:60-78`). Le projet durable est un **regroupement au-dessus**, sans copie de ces champs. Le nom
technique évite « projets », déjà pris par les missions.

```sql
CREATE TABLE IF NOT EXISTS regroupements (
  id          TEXT PRIMARY KEY CHECK (length(id) = 14 AND substr(id, 1, 2) = 'g_'
                                      AND substr(id, 3) NOT GLOB '*[^0-9a-f]*'),
  titre       TEXT NOT NULL CHECK (length(titre) BETWEEN 1 AND 120),
  description TEXT CHECK (description IS NULL OR length(description) <= 4000),
  depot_alias TEXT,
  provenance  TEXT NOT NULL CHECK (provenance IN ('proprietaire', 'regroupement_automatique_par_depot')),
  etat        TEXT NOT NULL CHECK (etat IN ('ouvert', 'archive')),
  auteur      TEXT NOT NULL, cree_le INTEGER NOT NULL, maj_le INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS regroupement_auto_par_depot
  ON regroupements (depot_alias) WHERE provenance = 'regroupement_automatique_par_depot';
-- COLONNES_V5 :
--   ("projets", "regroupement_id", "TEXT REFERENCES regroupements(id)")
-- puis : CREATE INDEX IF NOT EXISTS projets_par_regroupement ON projets (regroupement_id, cree_le);
```

- Préfixe `g_` : distinct des préfixes existants (`p_`, `q_`, `t_`, `m`, `acpm_`, `acpe_` : `contrat/machine.py:58-60`,
  `226-228` ; `acp:` : `noyau/kanban_adapter.py:92`).
- Le dépôt d'un regroupement n'impose rien aux missions : chacune garde le sien (`projets.depot_alias`,
  `noyau/base.py:66`). Il sert au regroupement automatique et à l'affichage.
- Le plafond de missions actives reste compté par mission (`projets_actifs_max`, `noyau/base.py:343` ; contrôle :
  `noyau/projets.py:118-121`).

Routes proposées, toutes derrière la garde d'écriture ou la porte de session :

| Route | Corps ou paramètres | Effet |
|---|---|---|
| `GET /v1/regroupements` | — | Liste : `id`, `titre`, `depot`, `provenance`, `etat`, missions comptées par état, `cree_le` ; plus le nombre de missions sans regroupement |
| `POST /v1/regroupements` | `titre`, `description?`, `depot?` ; `Idempotency-Key` | 201 ; provenance `proprietaire` ; journal `regroupement_cree` |
| `POST /v1/regroupements/{id}/modifier` | `titre?`, `description?` | Journal `regroupement_modifie` |
| `POST /v1/regroupements/{id}/archiver` | `{}` | Refusé (409) tant qu'une mission rattachée est ouverte |
| `POST /v1/projets/{id}/regroupement` | `regroupement` : `g_…` ou `null` | Rattache ou détache une mission ; journal `rattachement` (avant, après) |
| `POST /v1/projets` | champ `regroupement` admis, facultatif | Mission lancée dans ce regroupement |
| `GET /v1/projets`, `GET /v1/projets/{id}` | — | Champ `regroupement` ajouté au résumé (`noyau/projets.py:211-216`) |

Sans champ `regroupement` au lancement, deux règles possibles, **à trancher** :

- (a) la mission rejoint le regroupement automatique de son dépôt s'il existe, ligne `rattachement` au journal avec la
  provenance « regroupement automatique par dépôt » ; sinon `NULL`. La station garde alors le regroupement par dépôt
  qu'elle fait depuis le lot B ;
- (b) toujours `NULL` : la station range la mission sous « Sans projet ».

La règle (a) est recommandée. Une mission lancée en discussion par l'outil `projet_lancer` suit la même règle :
l'outil ne change pas.

### 2.2 Compatibilité

- Annonce : `"regroupements": true` dans `/v1/meta`. Sans elle, la station regroupe par dépôt comme au lot B (D166) et
  n'envoie jamais `regroupement`.
- Le champ `regroupement` des résumés est un ajout de réponse : compatible.
- `acp-machine/1` inchangé : l'exécutant ne voit que `projet_id` (`contrat/machine.py:227`). Le regroupement se retrouve
  côté serveur par jointure.

### 2.3 Migration

- Une seule fois, lors du passage de v4 à v5. `migrer()` lirait la version en début de transaction, avant l'`UPDATE`
  de version. La fonction de lecture existe (`version_schema`, `noyau/base.py:512-514`) ; `migrer()` ne l'appelle pas
  aujourd'hui (`noyau/base.py:478-509`).
- Pour chaque `depot_alias` non nul des missions existantes : une ligne `regroupements`, titre = alias (32 caractères au
  plus : `contrat/inventaire.py:56`), provenance `regroupement_automatique_par_depot`, auteur `acp-poste:migration`,
  `cree_le` = plus ancienne mission du dépôt. Puis `projets.regroupement_id` pour ces missions.
- Croquis, dans la transaction de `migrer()` :

```sql
INSERT OR IGNORE INTO regroupements (id, titre, depot_alias, provenance, etat, auteur, cree_le, maj_le)
  SELECT 'g_' || lower(hex(randomblob(6))), depot_alias, depot_alias, 'regroupement_automatique_par_depot',
         'ouvert', 'acp-poste:migration', MIN(cree_le), MAX(maj_le)
  FROM projets WHERE depot_alias IS NOT NULL GROUP BY depot_alias;
UPDATE projets SET regroupement_id = (SELECT r.id FROM regroupements r WHERE r.depot_alias = projets.depot_alias
                                      AND r.provenance = 'regroupement_automatique_par_depot')
  WHERE regroupement_id IS NULL AND depot_alias IS NOT NULL;
```

- Une ligne de journal par regroupement créé (`projet_id` nul, action `regroupement_automatique`, détail : dépôt,
  nombre de missions).
- Les missions sans dépôt restent à `NULL` : aucun regroupement inventé.
- **Aucune exécution inventée** : ni carte, ni run, ni événement, ni ligne d'activité qui prétendrait un travail passé.
- Idempotence : index unique partiel, clause `regroupement_id IS NULL`, transaction `IMMEDIATE` ; un second processus
  trouve la version 5 et ne refait rien.

### 2.4 Tests exigés

- `test_migration_v5.py` : base v4 avec des missions sur deux dépôts et une sans dépôt. Attendus : deux regroupements
  automatiques, missions rattachées, la mission sans dépôt à `NULL`, une ligne de journal par regroupement, seconde
  migration sans effet, deux processus concurrents, base neuve égale à base migrée.
- Routes : création idempotente, rattachement journalisé, archivage refusé avec une mission ouverte, champ inconnu
  refusé, refus en français.
- `test_meta.py` : clé `regroupements` présente.
- Montée de données depuis `85b458b` : missions d'avant intactes sur leurs colonnes d'avant.
- Station : sans l'annonce, aucun champ `regroupement` émis ; avec elle, barre latérale par regroupement.

### 2.5 Risques

- Deux mots pour une chose : l'API dit « projets » là où l'interface dit « missions » (D166). La documentation des
  routes devra le dire.
- Après un retour à une image v4, les missions lancées entre-temps restent à `NULL`, et la migration ne repasse pas.
  La règle (a) ne les rattache qu'à leur création : un geste « Rattacher » reste nécessaire.
- Le titre automatique est l'alias du dépôt : vrai, mais sec. Le propriétaire peut le renommer
  (`POST /v1/regroupements/{id}/modifier`).

---

## 3. Missions : reprendre, continuer, réessayer, nouvelle mission (lot C)

### 3.1 Correspondance exacte avec les gestes existants

| Geste du brief | Geste existant | Route et code | Effet exact | Limites |
|---|---|---|---|---|
| Nouvelle mission | Lancer un projet | `POST /v1/projets` (`dashboard/plugin_api.py:239-256` ; `noyau/projets.py:94-203`) | Nouveau tableau kanban, carte d'exploration si dépôt, puis carte de planification | Refus en pause générale (`noyau/projets.py:116-117`) ou au-delà de `projets_actifs_max` missions actives, 3 par défaut (`:118-121`) |
| Reprendre une mission en pause | Reprise du projet | `POST /v1/projets/{id}/reprise` (`dashboard/plugin_api.py:285-291` ; `noyau/projets.py:411-442`) | Réveille les cartes planifiées par la pause (raison exacte, `:436`) et celles dont la question a reçu sa réponse | Projet `en_pause` seulement (`:416-417`) ; plafond des actives revérifié (`:418-422`) |
| Reprendre une tâche (même session) | Aucun geste : automatique | `noyau/execution.py:48`, `340` | Reprise du fil local si l'issue est `question`, `bloquee:quota`, `arret`, `rendue` ou `revue_refusee`, sur la même machine | Le propriétaire ne choisit pas |
| Réessayer une tâche | Relancer une carte | `POST /v1/cartes/{tableau}/{carte}/relancer` (`dashboard/plugin_api.py:1173-1188` ; `noyau/questions.py:461-534` ; D94) | Carte de l'exécutant : `issue = 'relancee'`, **session neuve**, consigne recomposée en tête (`:510-515`, `534`) ; carte Hermes : consigne en commentaire ; intégration : sans consigne (D117) | Carte `blocked` d'une mission active seulement (`noyau/questions.py:325-337`) |
| Continuer au plafond | « Prolonger » ou « Relancer la planification » | `POST /v1/triage/{tableau}/{carte}/reprendre` (`dashboard/plugin_api.py:310-317` ; `noyau/questions.py:556-590` ; D41) | Plafond relevé (tours + 1 ou cartes + 10), consigne du propriétaire, journal `prolongation` ou `relance_planification` | Exige une carte de décision ; le journal sert de preuve à `graphe.planifier` (`noyau/graphe.py:329-334`) |
| Arrêter | « Conclure » ou « Clore » | `POST /v1/triage/{tableau}/{carte}/conclure` (`dashboard/plugin_api.py:320-327` ; `noyau/questions.py:593-615`) ; `POST /v1/projets/{id}/clore` (`dashboard/plugin_api.py:1205-1216` ; `noyau/projets.py:490-544`) | « Conclure » : `termine` si la mission a au moins un tour (`noyau/questions.py:607`) ; « Clore » : `termine` si la synthèse du tour est faite (`noyau/projets.py:509`), sinon `abandonne` | États finaux |

### 3.2 Ce qui manque

- **Continuer une mission terminée ou abandonnée.** Aucune route ne rouvre un état final : la relance refuse
  `projet_fini` (`noyau/questions.py:327-330`) et la reprise exige `en_pause` (`noyau/projets.py:416-417`).
- **Réessayer une mission entière.** Même cause.
- **Réessayer une tâche finie** (`done`) dont le résultat déplaît : la relance exige `blocked`
  (`noyau/questions.py:333`). La voie existante reste la correction au tour suivant.
- **Choisir « reprendre la session » ou « session neuve »** à la relance : non offert. D94 impose la session neuve, qui
  seule lit la consigne. Proposition : garder ce choix.

### 3.3 Forme proposée

- Pas de réouverture. Une **mission à la suite** : `POST /v1/projets` admet `suite_de: "p_…"` et
  `relation: "suite" | "nouvel_essai"`.
- Conditions : mission d'origine `termine` ou `abandonne`. Dépôt, profil et regroupement copiés ; titre et objectif
  écrits par le propriétaire.
- `suite` : le corps de la planification reçoit le résultat de la mission d'origine (la synthèse servie par
  `noyau/projets.py:278-282`), masqué, borné, et dit tronqué s'il l'est. `nouvel_essai` : objectif d'origine proposé,
  sans résultat.
- Nouveau tableau, nouveaux plafonds, mêmes contrôles que tout lancement. Journal `suite_de` sur les deux missions.
- Colonnes v5 : `projets.suite_de TEXT REFERENCES projets(id)` et `projets.relation TEXT`, `NULL` pour l'existant.

### 3.4 Compatibilité, migration, tests, risques

- Annonce : `"missions": {"suite_de": true}`. Sans elle, la station n'offre que « Nouvelle mission ».
- Migration : deux colonnes nulles ; aucune relation devinée entre missions anciennes.
- Tests : `suite_de` inconnue (404) ; d'une mission ouverte (409) ; corps de planification masqué et borné ;
  idempotence par `Idempotency-Key` ; plafond des actives ; motif de secret dans le résultat d'origine refusé.
- Risques : chaque suite consomme un tour de planification et jusqu'à `plafond_cartes` cartes
  (`noyau/base.py:338-340`). Un résultat d'origine très long coûte en contexte : borne à fixer.

---

## 4. Journal d'activité durable (lot D)

### 4.1 Existant

- Table `journal` durable, identifiant `AUTOINCREMENT` (`noyau/base.py:159-160`), index `(projet_id, id)` (`:165`).
- `journaliser()` s'appelle dans la transaction de l'appelant ; le détail est masqué puis tronqué à 2 000 caractères
  (`noyau/base.py:538-545`).
- Aucun `DELETE FROM journal` dans le greffon. Le journal sert aussi de preuve (`noyau/graphe.py:329-334`) et
  d'empreinte au flux (`noyau/flux.py:150-153`, `163`).
- Seules les 100 dernières lignes d'une mission sont servies, dans `GET /v1/projets/{id}` (`noyau/projets.py:324-327`).
- Les événements kanban (`task_events`, un fichier SQLite par tableau) sont lus par l'émetteur depuis un curseur par
  tableau, par lots de 500 ; le curseur avance dans la même transaction que les notifications
  (`noyau/emetteur.py:116-165`). Ils ne sont ni copiés ni servis.

### 4.2 Forme proposée : colonnes ajoutées à `journal`

| Colonne | Type | Rôle |
|---|---|---|
| `evenement_id` | `TEXT` | UUID stable ; index unique partiel `WHERE evenement_id IS NOT NULL` |
| `source` | `TEXT` | `acp` (geste ou décision du greffon), `kanban` (copie d'un `task_events`) ; plus tard `executant` (§ 4.8) |
| `source_id` | `TEXT` | Kanban : `<tableau>#<task_events.id>` ; index unique partiel `(source, source_id) WHERE source_id IS NOT NULL` |
| `carte` | `TEXT` | Carte kanban concernée (`t_…`), si connue |
| `run_id` | `INTEGER` | Run kanban, si connu |
| `genre` | `TEXT` | Type normalisé : `acp.<action>`, `kanban.<kind>` |
| `survenu_le` | `INTEGER` | Instant du fait. Kanban : `task_events.created_at` ; geste d'ACP : `quand` |

- `survenu_le` s'ajoute aux six autres colonnes : `quand` donne l'instant de réception, pas celui du fait.
- `journaliser()` gagne des paramètres facultatifs (`carte`, `run_id`). Ses appelants restent valides. Pour un geste
  d'ACP : `evenement_id` UUID v4, `source = 'acp'`, `genre = 'acp.' || action`.
- La carte n'est jamais devinée depuis `cible` à l'écriture : chaque appelant la passe s'il la connaît, comme
  `execution._journal` (`noyau/execution.py:565-567`).

### 4.3 Ingestion idempotente des événements kanban

- Lieu : `emetteur.lire_evenements`, dans la transaction qui avance déjà le curseur (`noyau/emetteur.py:152-161`).
  Chaque événement lu donne au plus une ligne : `INSERT OR IGNORE`, `source = 'kanban'`,
  `source_id = '<tableau>#<id>'`.
- `evenement_id` d'une copie : UUID v5 dérivé de `source_id`. Une copie refaite garde la même identité.
- `ka.evenements_apres` ne lit pas `run_id` (`noyau/kanban_adapter.py:217-222`), alors que la colonne existe
  (`tests-image/test_kanban_adapter.py:65-70`). Il faut l'ajouter à la lecture et au test du schéma.
- Charge utile : liste blanche de clés par genre, seulement pour les genres dont le greffon lit déjà la forme :
  `blocked` (`kind`, `reason` : `noyau/emetteur.py:135-138`), `scheduled` (`reason` : `noyau/projets.py:405-407`). Pour
  tout autre genre, le genre seul, et la ligne le dit (« détail non copié »). Chaque autre forme se vérifie d'abord sur
  Hermes 0.21.5 par un test d'image, comme `test_schema_des_evenements_attendu`.
- Genres déjà nommés par le code : `created` (`tests-image/test_kanban_adapter.py:74`), `blocked`, `review_requested`,
  `block_loop_detected`, `gave_up` (`noyau/emetteur.py:135-149`), `completed`, `claimed`, `promoted`
  (`noyau/emetteur.py:23-24`), `scheduled` (`noyau/projets.py:406`).
- **Non vérifié ici** : Hermes range-t-il un événement par battement ? Si oui, une ligne par minute et par carte en
  cours. La copie de ce genre serait alors coupée ou réduite.

### 4.4 Route `GET /v1/activite`

| Paramètre | Valeurs | Règle |
|---|---|---|
| `apres` | entier ≥ 0 | Lignes d'identifiant strictement supérieur, ordre croissant |
| `avant` | entier ≥ 1 | Page précédente : lignes d'identifiant strictement inférieur ; exclusif avec `apres` |
| `limite` | 1 à 500, défaut 100 | Au-delà : 400 en français |
| `mission` | `p_…` | Filtre ; index `journal_par_projet` (`noyau/base.py:165`) |
| `regroupement` | `g_…` | Filtre par jointure (§ 2) |

Sans `apres` ni `avant` : les `limite` lignes les plus récentes, rendues en ordre croissant.

Réponse :

```json
{
  "schema_version": 1,
  "evenements": [],
  "dernier_id": 1234,
  "plus": false,
  "plus_ancien_id": 1,
  "suivi_kanban_depuis": "2026-10-11T00:00:00Z"
}
```

- `plus` : il reste des lignes au-delà de la page.
- `plus_ancien_id` : plus petit identifiant encore conservé (§ 4.7).
- `suivi_kanban_depuis` : instant de la migration, gardé dans `meta_schema`. Avant lui, aucune copie kanban (§ 4.7).
- Lecture seule, derrière la porte de session comme toute route de lecture (`dashboard/plugin_api.py:7-9`).
- La station garde son curseur (le dernier `sequence` reçu). Sur un signal `activite`, elle relit `apres=<curseur>`
  jusqu'à `plus: false`.
- Annonce : `"activite": {"chemin": "/api/plugins/acp-poste/v1/activite", "schema_version": 1, "limite_max": 500}`.
- `GET /v1/projets/{id}` garde ses 100 lignes de journal : `acp-poste/1` ne change pas. Sa requête prend les 100
  dernières lignes de la mission, quelle que soit leur nature (`noyau/projets.py:326-327`) : elle devra exclure
  `source = 'kanban'`, sinon les copies chasseraient les gestes d'ACP de ces 100 lignes.

### 4.5 Sujet de flux `activite`

- `SUJETS` gagne `activite` (`noyau/flux.py:53`) ; son lecteur rend `MAX(id)` du journal (`LECTEURS`, `:214-217`).
- La station ignore un sujet inconnu (`apps/desktop/src/events/FluxInvalidation.cpp:367-368`). La page web aussi
  (`apps/interface/src/flux.ts:144`, `368`). L'ajout est donc compatible avec les clients actuels.
- Le sujet `projets` lit `MAX(id)` des lignes rattachées à une mission (`noyau/flux.py:163`). Les copies kanban le
  feraient changer à chaque événement, et `GET /v1/projets` ouvre chaque tableau (`noyau/projets.py:331-338`). Son
  empreinte exclurait donc `source = 'kanban'`.
- À mettre à jour : `SUJETS` figé dans `tests-image/test_flux.py:29` ; trames partagées avec la station
  (`hermes/tests/outils/fixtures_flux/trames.json`, lues par `test_flux.py:304`) ; bloc `flux` de `/v1/meta`
  (`tests-image/test_meta.py:315`, `328`) ; liste de la page web (`apps/interface/src/flux.ts:24`).
- Le flux reste une invalidation (D96) : il ne porte que le nom du sujet.

### 4.6 Schéma d'événement du brief (§ 15), colonne par colonne

| Champ du brief | Source proposée | Remarque |
|---|---|---|
| `schema_version` | Constante de la route : 1 | Change seulement par une version nouvelle de la route |
| `event_id` | `journal.evenement_id` | Lignes d'avant v5 : UUID v4 posé par la migration |
| `source_id` | `journal.source_id` | `null` pour un geste d'ACP : le journal en est la source |
| `sequence` | `journal.id` | Curseur du client ; jamais un compte |
| `project_id` | `projets.regroupement_id`, par jointure à la lecture | `null` sans regroupement ; suit un rattachement ultérieur |
| `mission_id` | `journal.projet_id` | `p_…` |
| `run_id` | `journal.run_id` | Run kanban ; `null` s'il est inconnu |
| `task_id` | `journal.carte` | `t_…` |
| `agent_id` | Déduit : voie de la demande (`demandes`, unique par carte : `noyau/base.py:117`) et machine (acteur `poste:<m>`) | Jamais un identifiant de session de CLI : il reste sur l'exécutant (`poste/execution.py:711`) |
| `occurred_at` | `journal.survenu_le` | Kanban : horloge de Hermes |
| `received_at` | `journal.quand` | Horloge du greffon |
| `type` | `journal.genre` | `acp.<action>`, `kanban.<kind>` |
| `payload` | `journal.detail` | Masqué, 2 000 caractères au plus ; objet JSON si le texte en est un |
| `provenance` | `journal.source` | `acp`, `kanban` ; `executant` avec `acp-machine/2` |
| niveau d'observation | Déduit de la source et du préfixe d'acteur | Voir ci-dessous |

Niveau d'observation, par règle fixe :

- `observe` : constaté par Hermes ou reçu par une route du greffon. Copies kanban ; gestes `proprietaire:<id>`
  (`dashboard/plugin_api.py:160-163`) et `discussion:<session>`.
- `rapporte` : dit par un tiers, non vérifiable par Hermes. Acteurs `poste:<machine>` (`noyau/execution.py:565-567`),
  `poste` seul (question et correction reçues de l'exécutant : `noyau/questions.py:83`, `noyau/graphe.py:482`),
  `carte:<t>` (outil de l'agent, `noyau/questions.py:142`), `releve:<source>` (`noyau/routage.py:117`).
- `deduit` : calculé par le greffon. Acteurs `acp-poste` et `acp-poste:<rôle>` : émetteur (`noyau/emetteur.py:227`,
  `266`), plan (`noyau/graphe.py:259`), bilan (`noyau/bilan.py:122`), enrôlement (`noyau/machines.py:125`).

L'acteur reste servi tel quel, champ `acteur`.

### 4.7 Déduplication, trous, curseur, rétention, rédaction

- **Déduplication.** Clé unique `(source, source_id)` et même transaction que le curseur. Si une ligne de même
  `source_id` existe avec un genre ou un instant différents (tableau revenu en arrière par une restauration partielle),
  la passe ne l'écrase pas : elle écrit une ligne `acp.activite_conflit`, niveau `deduit`.
- **Numérotation.** Toute écriture passe par `BEGIN IMMEDIATE` (`noyau/base.py:424-435`) : un seul écrivain à la fois.
  Un identifiant n'est visible qu'après son commit, et aucun identifiant plus petit ne peut apparaître ensuite. Le
  curseur `apres` ne saute donc aucune ligne. Condition à garder : toute écriture du journal sous `transaction`.
- **Trous de numérotation normaux.** Un `INSERT OR IGNORE` ignoré consomme un numéro (`noyau/base.py:459-462`). Le
  client ne lit jamais un trou comme une perte.
- **Trous réels, dits par la route :**
  - avant la migration, aucun événement kanban copié (`suivi_kanban_depuis`). Une reprise de l'historique serait une
    option à part, avec son propre curseur et la provenance « reprise » ;
  - une mission `abandonne` n'est plus lue (`noyau/emetteur.py:120`). Ses derniers événements, par exemple
    l'archivage de `clore`, ne sont pas copiés ; la ligne `cloture` du greffon les résume (`noyau/projets.py:537-539`) ;
  - pendant la pause générale, aucune passe (`noyau/emetteur.py:33-34` ; D31) : retard, pas de perte, le curseur
    n'avançant pas ;
  - ce que l'exécutant garde pour lui (étapes locales, outils, sorties) n'existe pas dans la source (§ 4.8).
- **Rétention.** Les lignes `acp` sont gardées sans limite, comme aujourd'hui : certaines servent de preuve. Les copies
  `kanban` pourraient être purgées après une durée réglable (`activite_kanban_conservation_s`, `null` par défaut :
  aucune purge tant que le volume n'est pas mesuré). `plus_ancien_id` dit alors le trou.
- **Rédaction.** Tout texte copié passe par `ka.masquer` en mode forcé (`noyau/kanban_adapter.py:246-253`) puis par
  `motif_trouve` ; un motif trouvé remplace le détail par « détail retiré : motif de secret ». Borne de 2 000
  caractères (`noyau/base.py:543`). Jamais de consigne ni de corps de carte dans une copie.

### 4.8 Limites de `acp-machine/1`, et proposition `acp-machine/2`

Impossible sans étendre le protocole :

| Donnée du brief | Pourquoi elle manque |
|---|---|
| Sorties en direct | Le stdout de l'agent est gardé en mémoire (`poste/execution.py:851`), analysé après la fin du processus (`:921-939`), hors le contrôle de l'`init` de Claude, fait en cours de route (`:853-858`) ; le stderr est lu puis jeté (`:860-866`) ; rien n'est transmis brut (`poste/evenements.py:4-5`) |
| Outils en cours | Claude : seuls `system/init`, `rate_limit_event` et `result` sont lus (`poste/evenements.py:229-263`). Codex : les commandes sont comptées (`:174-175`), et ce compte n'est lu que par un test (`apps/poste/tests/test_evenements_gardes.py:43`) |
| Fichiers touchés | Seuls le diffstat chiffré et les chemins de pilotage remontent (`poste/execution.py:704-712` ; `contrat/machine.py:857-866`, `914-936`) |
| Sous-agents | Délégation coupée (§ 8) ; `parent_tool_use_id` n'est lu nulle part dans `apps/poste` |
| Étapes locales | Préparation, vérification, commit et contrôles sont écrits dans un fichier local (`poste/execution.py:271-279`), jamais envoyés |
| Session de la CLI | Réduite au booléen `session_locale` (`poste/execution.py:711`) |

Amélioration possible **sans** changer de protocole : l'exécutant n'envoie de battement que pendant que l'agent tourne
(`poste/execution.py:884-895`), toutes les 60 s (`:65`). Envoyer aussi des battements pendant la préparation et la
vérification ne touche que l'exécutant : même route, même forme, note libre de 500 caractères au plus
(`contrat/machine.py:817-825`). Cela réduit aussi un risque : `verification_max_s` peut atteindre 7 200 s
(`poste/politique.py:824`) pour une réclamation de 2 700 s (`noyau/base.py:361`). Le greffon ne range pas la note dans
sa base : il la transmet, masquée, au battement du worker de Hermes (`ka.heartbeat_worker`, `noyau/execution.py:472`).
Elle reste du texte libre.

Proposition `acp-machine/2`, négociée :

1. **Annonce.** L'exécutant envoie `protocole: "acp-machine/2"` dans `reclamer` (`contrat/machine.py:563-580`).
2. **Greffon prêt pour 2.** Il admet les majeures 1 et 2 (changement de `dashboard/plugin_api.py:482-484`). Il répond à
   chaque exécutant dans la forme de la version annoncée : un exécutant en version 1 ne voit jamais un champ de la
   version 2.
3. **Greffon en version 1.** Il répond 409 `protocole_incompatible`. L'exécutant en version 2 repasse alors en version 1
   et le dit dans son journal. Aujourd'hui, ce refus l'arrête (`poste/service_executant.py:187-189`) : comportement à
   changer.
4. **Trace.** `machines.protocole` existe (`noyau/base.py:171`), écrit à l'enrôlement seulement
   (`noyau/machines.py:131-133`). Il serait mis à jour à chaque réclamation, puis servi par `/v1/poste` : la station
   saurait quel niveau d'observation attendre.
5. **Route nouvelle** `POST /machine/v2/evenements`. Les chemins à jeton sont enregistrés un par un depuis `ROUTES`
   (`noyau/jeton_machine.py:149-158` ; `contrat/machine.py:54-56`) : la route s'y ajoute. Corps :
   `{id_envoi, tableau, carte, run_id, evenements: [{seq, genre, le, donnees}]}`, 32 Kio et 50 événements au plus.
   Preuve de propriété comme les autres routes (`noyau/execution.py:117-119`).
6. **Genres.** `etape`, `outil_debut`, `outil_fin` (nom de l'outil et statut, jamais les arguments), `fichier_modifie`
   (chemin relatif au worktree, masqué, 300 caractères au plus), `sous_agent_debut`, `sous_agent_fin`, et `sortie`
   (extrait de 500 caractères au plus). `sortie` est **désactivé par défaut** : la doctrine « rien de brut »
   (`poste/evenements.py:4-5`) ne se relâche que par une décision du propriétaire.
7. **Idempotence.** Par le journal : `source = 'executant'`, `source_id = '<machine>#<carte>#<run>#<seq>'`. La table
   `envois` n'est pas touchée : sa contrainte `route IN (…)` (`noyau/base.py:215`) imposerait une reconstruction.
8. **Balayage.** Côté exécutant avant l'envoi, et côté greffon avant tout effet, comme aujourd'hui
   (`dashboard/plugin_api.py:811-813`).
9. **Ordre de livraison.** Greffon prêt pour 1 et 2 d'abord ; image de l'exécutant ensuite. Un retour arrière de
   l'exécutant reste admis.

Tests exigés : contrat des deux côtés (`hermes/plugins/acp-poste/contrat/tests/`) ; exécutant en version 1 contre
greffon prêt pour 2 (aucun champ de la version 2 reçu) ; exécutant en version 2 contre greffon en version 1 (repli) ;
fixtures `hermes/tests/outils/fixtures_machine` ; bout en bout `hermes/tests/contrat/test_executant_bout_en_bout.py`.

### 4.9 Compatibilité, migration, tests, risques du lot D

- Compatibilité : route et sujet nouveaux, annoncés ; `GET /v1/projets/{id}` inchangé.
- Migration :
  - colonnes de § 4.2 ajoutées ; aucune reconstruction de `journal` ;
  - lignes existantes : `source = 'acp'`, `genre = 'acp.' || action`, `survenu_le = quand`, `evenement_id` UUID v4 ;
  - `carte` reprise de `cible` pour les seules actions dont les appelants passent la carte en `cible`, et si elle a la
    forme `t_…` (`contrat/machine.py:226`) ;
  - aucun événement kanban passé n'est recopié ; `suivi_kanban_depuis` est posé.
- Tests exigés :
  - copie idempotente : deux passes, une seule ligne ; curseur et lignes dans la même transaction, sur le modèle de
    `tests-image/test_emetteur.py:80` ;
  - conflit de `source_id` signalé ; masquage et motif de secret ;
  - route : bornes de `limite`, `apres` et `avant` exclusifs, ordre, `plus`, filtre par mission ;
  - flux : sujet `activite` publié ; sujet `projets` insensible aux copies ;
  - migration v5 ; montée de données ;
  - station : `tst_flux_invalidation` (sujet inconnu ignoré), lecture paginée sans trou ni doublon, sur une fixture
    partagée `hermes/tests/outils/fixtures_activite/`, à créer.
- Risques :
  - volume du journal, et durée de la migration sur un gros journal : mesurer dans le job « montee » ;
  - relectures provoquées par l'empreinte `projets` : l'exclusion des copies l'évite ;
  - une restauration partielle d'un tableau : ligne de conflit, jamais une perte muette.

---

## 5. États d'agent

### 5.1 Statuts kanban servis aujourd'hui

Libellés de la station : `apps/desktop/src/viewmodels/Libelles.cpp:116-130`.

| Statut | Libellé actuel | Sens observé |
|---|---|---|
| `triage` | En triage | Décision du propriétaire attendue (`noyau/projets.py:242-246`) |
| `todo` | En attente | Parents non finis : la planification reste `todo` jusqu'à la fin de l'exploration (`docs/refonte/projets.md:406`) |
| `scheduled` | Suspendue | Planifiée : pause de la mission (`noyau/projets.py:398-399`), question (`noyau/execution.py:574-575`), quota (`noyau/execution.py:602-606`) |
| `ready` | Prête | Réclamable ; carte de l'exécutant non prise : « en attente du poste » (`noyau/projets.py:258-260`) |
| `running` | En cours | Réclamée ; pour l'exécutant, preuve de propriété (`noyau/execution.py:117-119`) |
| `blocked` | Bloquée | Raison lue dans les événements (`noyau/questions.py:372-385`) |
| `review` | En relecture | Revue des fichiers de pilotage (`noyau/execution.py:524-533`) |
| `done` | Faite | Terminée |
| `archived` | Archivée | Archivée par « Conclure » (`noyau/questions.py:606`) ou « Clore » (`noyau/projets.py:529-534`) |
| `a_creer` | À créer | Demande réservée, carte pas encore créée (`noyau/projets.py:286`) |

### 5.2 États du brief

| État du brief | Source aujourd'hui | Observable ? |
|---|---|---|
| En file | `ready` | Oui |
| Attend une dépendance | `todo` | Oui pour l'état ; le parent attendu est dans `demandes.parents` (`noyau/base.py:114`), non servi par la liste des cartes (`noyau/projets.py:283-295`) |
| Exécute | `running` ; carte annoncée par l'exécutant, modèle demandé et servi, dernier battement (`noyau/execution.py:771-794`) | Oui |
| Outil en cours | Rien : outils ignorés (§ 4.8) ; battement générique (`poste/execution.py:887-888`) | **Non** sans `acp-machine/2` |
| Attend une décision | `triage` ; `review` ; question ouverte ou escaladée et sa règle `chez` (`noyau/projets.py:302-305`) | Oui |
| Attend un quota | `scheduled` et une ligne `attentes` (`noyau/execution.py:619-624`) | **Partiel** : `attentes` n'est servie par aucune route ; seuls l'émetteur, pour débloquer (`noyau/attentes.py:33`), et l'empreinte du flux (`noyau/flux.py:193`) la lisent |
| Annulation demandée | Le battement répond `annuler: true` si la mission n'est plus active (`noyau/execution.py:485`) | **Déduit** seulement : la réponse n'est pas gardée |
| Arrêt confirmé | Route `arret` : journal `carte_rendue` avec son motif, `presence.arret_propre_le` (`noyau/execution.py:647-648`, `659-661`) ; motifs `sigterm`, `pause_locale`, `annulee` (`contrat/machine.py:759`) | Oui, par le journal |
| Terminé | `done` | Oui |
| Échec | `blocked` avec raison ; `gave_up` notifié `abandon` (`noyau/emetteur.py:148-149`) ; vérification `echouee` dans `demandes.verification` (`noyau/execution.py:521`) | Oui pour le statut ; la vérification n'est pas servie par la liste des cartes |
| Télémétrie interrompue | Présence hors ligne au seuil de 180 s (`noyau/base.py:346`) ; dernier battement | **Déduit**, avec faux positifs : aucun battement pendant la préparation et la vérification (§ 4.8) |

Propositions :

- Lot D : servir pour chaque carte `issue`, `parents`, la raison d'une carte `scheduled` et l'échéance d'une attente de
  quota. Ces champs existent en base ; leur ajout aux réponses est compatible.
- Ne dire « télémétrie interrompue » que sur une présence hors ligne ou une réclamation perdue, tant que les battements
  ne couvrent pas toutes les étapes.
- « Outil en cours » reste « Non observé » jusqu'à `acp-machine/2`.
- Lot D : servir pour chaque carte `relue_carte`, l'identifiant kanban de la carte relue, à côté de `relue` (la clé
  de demande, inchangée). Aujourd'hui la station rapproche la clé `acp:<mission>:t<tour>:<ref>:<suffixe>`
  (`noyau/graphe.py`, `_cle`) des champs servis `tour`, `ref` et `role`, au rang de la carte dans l'ordre servi
  (`noyau/cartes.py`, `cartes_du_projet` : `tour, cree_le, rowid`) pour `relecture2` ou `correction1`
  (`EspaceTravailViewModel::construireAgents`) ; le champ servi rendrait ce rapprochement inutile. Un rapprochement
  impossible laisse la relecture à plat sous Hermes ; aucune relation n'est inventée.
- Lot D : servir la raison d'une carte `scheduled` (question, pause de la mission, quota). D'ici là, la station dit
  « Suspendue (question, pause ou quota) » sans choisir la cause.

---

## 6. Routage enrichi (lot E)

### 6.1 Existant

- Ordre : surcharge, choix explicite, profil Hermes, puis table ; sinon refus exact (`noyau/routage.py:514-566`).
- Table non versionnée : une ligne par classe, écrasée (`noyau/routage.py:189-192`). L'historique n'est que dans le
  journal, tronqué à 2 000 caractères.
- Critères gardés par demande : voie, modèle, effort, palier, `source_routage`, relevé, mention
  (`noyau/base.py:102-112`). Le rang retenu et les raisons des entrées écartées sont perdus (liste `raisons`,
  `noyau/routage.py:551-557`).
- Le plan de Hermes peut fixer voie, modèle et effort par étape (champs facultatifs, `noyau/graphe.py:103-104`).
  `composer` les passe à `resoudre` (`noyau/graphe.py:163-164`), qui en fait un choix explicite
  (`noyau/routage.py:530-546`) : il passe avant la table. La part des étapes ainsi fixées dans les plans réels n'est
  pas mesurée ici.

### 6.2 Forme proposée

- **Historique de la table.** Table `routage_versions` (`id AUTOINCREMENT`, `classe`, `entrees`, `valide_le`,
  `valide_par`, `source`, `motif`), en ajout seulement. Colonne `routage.version`. `enregistrer_routage`
  (`noyau/routage.py:177-193`) écrit l'historique puis la ligne courante.
- **Modes.** Table `routage_modes` (`mode`, `classe`, `version`, `entrees`, `valide_le`, `valide_par`), clé
  `(mode, classe)`. Modes `econome` et `approfondi`. **Équilibré = la table validée actuelle**, c'est-à-dire l'« Auto »
  d'aujourd'hui. Pas de table de plus pour lui.
- **Validation.** Comme `valider_table` : tout ou rien, 409 si un relevé a changé (`noyau/routage.py:832-859`). Chaque
  entrée passe `admission` (`:731-739`). Un mode doit couvrir toutes les classes de la table : aucun repli au moment de
  résoudre.
- **Mission.** `projets.mode_routage` (`NULL` = Auto), choisi au lancement par le champ `mode`.
- **Résolution.** Même ordre ; à l'étape de la table, celle du mode de la mission. Le mode **borne aussi les choix
  explicites** du plan : entrées admises et effort plafond. Un choix hors mode est refusé avec la raison exacte.
  La consigne de planification dit le mode.
- **Critères enregistrés par demande.** `demandes.mode_routage`, `demandes.routage_version` et `demandes.criteres`
  (JSON : rang retenu, entrées écartées avec rang, code et message de 300 caractères au plus, pourcentage de quota lu).
  `Resolution` (`noyau/routage.py:68-81`) gagne `rang` et `ecartees`, avec valeurs par défaut.
- **Suggestion.** Comme `suggestion()` (`noyau/routage.py:742-770`), tirée des seuls champs lus. L'ordre des efforts
  n'est pas supposé : il est déclaré dans la politique et validé par le propriétaire.

### 6.3 Garde-fous tenus

- D39 : efforts `max`, `ultra`, `ultracode` interdits, palier `default` seul. `admission` les refuse
  (`noyau/routage.py:443-446`, `496-497`) ; la politique du poste aussi (`:278-305`).
- Aucune dépense hors enveloppe sans la phrase « J'accepte une dépense hors enveloppe » (`noyau/textes.py:344` ;
  `noyau/routage.py:882-897`). Un mode ne lève rien : il faut d'abord changer la politique avec la phrase.
- D58 : liste de secours de Codex refusée sans acceptation explicite (`noyau/routage.py:267-270`).
- D59 et D73 : aucun modèle Claude suggéré par défaut (`noyau/routage.py:756-760`) ; le modèle Claude d'un mode vient
  d'une entrée validée.
- D91 : repli de la relecture inchangé (`noyau/routage.py:569-638`).
- D168 : aucun mode offert par la station tant que `/v1/meta` ne l'annonce pas.

### 6.4 Banc d'évaluation

- Métrique : **coût du résultat accepté**. Numérateur : jetons d'entrée, de sortie et de cache rapportés par
  l'exécutant pour toutes les cartes de la mission, corrections et relances comprises. Ils sont rangés sur le run
  (`noyau/execution.py:555` ; `contrat/machine.py:846-849`, `948`). `ka.list_runs` est importé mais inutilisé
  (`noyau/kanban_adapter.py:53`) ; qu'il rende ces métadonnées n'est pas vérifié ici (code de Hermes absent de la
  session). Seule l'issue `terminer` porte des jetons (`contrat/machine.py:997-1006`) : un run fini par une question,
  un blocage, une reprise ou un arrêt n'en rapporte aucun (`contrat/machine.py:1053-1160`). Le numérateur sous-compte
  donc ces runs, et doit le dire. Dénominateur : 1 si le résultat est accepté ; sinon la mission ne compte pas, et le
  taux d'acceptation est publié à côté.
- Mesures publiées à côté, jamais fondues dans le nombre : heures d'agent, cartes, corrections, relances, écart de
  quota entre deux relevés.
- Les jetons des cartes Hermes ne sont pas relevés par le greffon : « non mesuré ». Aucun prix en euros : aucune donnée
  de prix n'est relevée.
- « Accepté » n'existe pas aujourd'hui : seule une revue des fichiers de pilotage s'accepte
  (`noyau/execution.py:680-694`). Proposition : un verdict du propriétaire, `POST /v1/projets/{id}/verdict`
  (`accepte` ou `refuse`, motif). Pour le banc, des critères écrits d'avance : tests du dépôt jetable.
- Lieu : dépôt jetable, comme en P6 ; jamais un Hermes ni un volume avec des données. Le banc consomme le quota réel
  des comptes : chaque campagne est un geste du propriétaire, hors CI.

### 6.5 Compatibilité, migration, tests, risques

- Annonce : `"modes_routage": {"version": n, "modes": ["econome", "equilibre", "approfondi"]}`. Routes
  `GET` et `POST /v1/routage/modes`. Champ `mode` de `POST /v1/projets`. Ajouts à `vue_routage` : compatibles.
- Migration : `routage_versions` reçoit une ligne par ligne de `routage` existante (source et `valide_le` gardés) ;
  colonnes nulles pour l'existant ; aucun critère reconstitué pour les demandes passées.
- L'empreinte du sujet `quotas` lit la table `routage` (`noyau/flux.py:191-198`) : elle lirait aussi `routage_modes`.
- Tests : rang et raisons écartées enregistrés ; refus exact sans repli ; mode avec effort interdit refusé à la
  validation ; phrase exigée ; 409 `releve_change` ; choix explicite hors mode refusé ; flux ; station sans annonce.
- Risques : `composer` s'arrête au premier refus (`noyau/graphe.py:156-163`) : un mode trop étroit bloque tout le tour.
  Un banc mal borné dépense l'enveloppe.

---

## 7. Comptes (lot C)

### 7.1 Gestes officiels, inchangés

- **Codex (D83).** Code d'appareil **sur l'exécutant** : `acp-poste connexion codex` dans une session `railway ssh`,
  après `acp-poste pause` (`poste/gestes_executant.py:69-71`). La commande lance
  `codex … login --device-auth` sous l'UID `acp-codex`, en héritant de la console. Le code ne passe ni par Hermes ni
  par le journal (`poste/gestes_executant.py:6-8`, `98`).
- **Claude (D84, D92).** `claude setup-token` sur le PC du propriétaire, puis `acp-poste connexion claude --stdin` dans
  `railway ssh`. Le jeton est rangé en fichier 0600 de root ; seule une empreinte de 12 caractères s'affiche
  (`poste/gestes_executant.py:3-5`, `41-57`).
- Poste Windows facultatif : mêmes gestes en console locale, coffre DPAPI ou trousseau (`poste/connexions.py:1-15`).

### 7.2 Ce que la station peut afficher

Source : `GET /v1/poste`, dernier inventaire avec `recu_le` et `releve_le` (`dashboard/plugin_api.py:960-972` ;
`noyau/inventaire.py:170-185`).

| Donnée | Valeurs | Origine |
|---|---|---|
| `connexions.codex` | `compte_chatgpt`, `cle_api`, `autre`, `non_connecte`, `inconnu` | `contrat/inventaire.py:647` ; `account/read`, adresse jetée (`poste/sondes_codex.py:175-193`) |
| `connexions.plan_codex` | Texte de 40 caractères au plus, ou `null` | `contrat/inventaire.py:651` |
| `connexions.claude` | `jeton_reconnu`, `jeton_present_non_verifie`, `refuse`, `jeton_absent`, `inconnu` | `contrat/inventaire.py:648` ; code de sortie de `claude auth status`, sorties jetées (`poste/sondes_claude.py:5-9`) |
| `connexions.claude_echeance` | Date **estimée** : dépôt du jeton plus 365 jours | `contrat/inventaire.py:653` ; `poste/service_executant.py:67`, `419-429` ; alerte à 30 jours (`noyau/inventaire.py:109-111`) |
| Voies fermées et leur raison | `{voie: raison}` calculé par le greffon depuis le dernier inventaire ; voies annoncées par l'exécutant | `noyau/routage.py:347-369` ; bloc `executant` de `/v1/poste` (`noyau/execution.py:839`, `841`). La raison locale de l'exécutant (`poste/service_executant.py:202-226`, `239-268`) n'est pas transmise |
| Conditions d'usage décidées | Date, ou `null` : voie fermée | `contrat/inventaire.py:731` ; alerte `noyau/inventaire.py:106-108` |

Libellés à tenir : « Jeton reconnu », jamais « valide » (`poste/sondes_claude.py:7`) ; « échéance estimée », jamais
« vérifiée ». Sans inventaire : « Inconnu ».

### 7.3 Ce que la station ne doit jamais faire

- Collecter, afficher, copier ou transmettre un jeton, un code d'appareil ou une clé.
- Proposer un champ de saisie de secret, même masqué.
- Ranger un secret dans les préférences, un JSON, le QML ou un journal.
- Agir sur Railway : session `railway ssh`, variables, clés. C'est un geste du propriétaire seul.

### 7.4 Parcours guidé proposé

1. Page Comptes : état observé de chaque voie, date du dernier inventaire, raison d'une voie fermée.
2. Pour une voie à connecter : le geste officiel, commande par commande, sans aucun secret dans le texte, à faire dans
   la console du propriétaire.
3. Bouton « Vérifier » : `POST /v1/poste/releve` (`dashboard/plugin_api.py:1026-1048`). L'exécutant relance ses sondes
   puis publie un inventaire (`poste/service.py:309-311`, `336-390`).
4. Succès affiché seulement quand un inventaire plus récent que le clic montre le nouvel état. Sinon « En attente de
   l'exécutant », puis le délai d'expiration de l'ordre.
5. Codex : rappeler `acp-poste reprise` après la connexion. En pause locale, aucune sonde ne tourne
   (`poste/gestes_executant.py:12-13`).

Aucune route nouvelle n'est nécessaire. Une route de compte qui recevrait un secret est exclue.

### 7.5 Tests et risques

- Tests : rendu de chaque valeur des deux énumérations ; « Inconnu » sans inventaire ; aucun succès avant un
  inventaire plus récent ; aucune clé de préférence nouvelle (`tst_reglages_sans_secret`) ; balayage des textes de la
  page (`scripts/balayer_secrets.py`).
- Risque : une commande affichée qui devient fausse après une montée de version des CLI. Les textes viennent des
  documents de l'exécutant ([executant.md](executant.md)) et se relisent à chaque montée.

---

## 8. Sous-agents natifs : fermés aujourd'hui

État :

- Codex : `multi_agent` parmi les fonctions coupées (`poste/commandes_agents.py:48-50`), passées en `--disable`
  (`:99-100`).
- Claude : liste blanche `--tools` de lecture et d'écriture de fichiers seulement (`poste/commandes_agents.py:51-52`,
  `116`). La liste noire du contrôle d'init contient `Task` mais pas `Agent` (`poste/evenements.py:33`) : la garantie
  vient de la liste blanche.
- Hermes sur Railway : aucune délégation. Le jeu d'outils `delegation` est coupé
  (`hermes/image/acp_demarrage.py:584-585`) et la garde n'admet aucun outil de délégation (`garde_execution.py:63-86`).

Conditions avant toute ouverture, toutes exigées :

1. **Événements.** Début et fin de chaque sous-agent remontés et journalisés (`acp-machine/2`, § 4.8), avec le lien au
   parent. Sans eux, un sous-agent serait invisible : donnée cachée.
2. **Permissions égales ou plus restreintes.** Même UID, même profil de permissions, réseau coupé, aucun MCP, aucun
   outil au-delà de la liste blanche du parent. Preuve sur les vrais binaires de l'image, comme
   `executant/tests/test_image.py:290-304`.
3. **Budgets.** Jetons des sous-agents comptés dans ceux de la carte ; durée bornée par `duree_max_s` de la carte ;
   heures d'agent par jour comptées (D84).
4. **Arrêt de l'arbre.** L'arrêt actuel couvre le groupe puis tout processus de l'UID
   (`poste/plateforme/linux.py:19-22`, `476-486`). Un test doit prouver qu'un sous-agent ne survit pas à l'arrêt de la
   carte.
5. **Bornes.** Profondeur 1 ; nombre maximal par carte ; aucun push (D82).
6. **Décision du propriétaire**, inscrite au plan avant tout code.

Jusque-là, la station affiche « Non observé » (D166).

---

## 9. Extensions du § 19 du brief : backlog

- **Missions récurrentes**, désactivées par défaut.
  - Fait établi : l'agent ne peut pas créer de tâche cron. Les outils sur `cron` sont coupés (D24) ; le jeu d'outils
    `cronjob` est coupé (`hermes/image/acp_demarrage.py:584-585`, rappelé en `1930`) et absent de la liste
    blanche (`garde_execution.py:63-86`).
  - Seul modèle existant : le bilan quotidien, tâche native `no_agent` créée par le propriétaire (D98 ;
    `apps/desktop/src/viewmodels/AccueilViewModel.cpp:294`). La garde des scripts n'admet que `acp-bilan.py`,
    d'empreinte connue (`hermes/image/acp_demarrage.py:1932-1937`).
  - Proposition en deux temps. D'abord une tâche native du propriétaire qui **notifie** « mission à relancer »,
    sans dépense. Ensuite seulement, sur décision : un second script admis par la garde, qui lance une mission depuis
    un modèle enregistré, soumis aux plafonds, à la pause générale et aux quotas.
  - Une origine `recurrence` élargirait la contrainte de `projets.origine` (`noyau/base.py:74`) : reconstruction, dans
    l'ordre K21. Elle serait plus délicate que celles de v3 et v4 : `tours`, `demandes` et `questions` référencent
    `projets` (`noyau/base.py:87`, `96`, `121`), alors que la mécanique existante suppose qu'aucune table ne référence
    la table reconstruite (`noyau/base.py:27-31`).
- **Services.** Aujourd'hui, l'onglet ne peut montrer que l'exécutant : présence, inventaire, ordres (`GET /v1/poste`).
  L'exécutant n'écoute aucun port (`CLAUDE.md`), et le réseau des agents est coupé
  (`executant/politique/executant.toml:53`). Un service lancé par une mission demanderait une décision du propriétaire.
- **Pixel Office secondaire.** Le moteur reste gelé (`scripts/check_engine_frozen.py:36` ; `CLAUDE.md`) ; aucun travail
  Godot avant la dernière phase. S'il revient, il lit les mêmes événements que la station (`GET /v1/activite`), sans
  source propre. La destination « Bureau de département » reste hors périmètre
  (`apps/desktop/src/navigation/NavigationModel.cpp:50-54`).

---

## 10. Ordre de livraison proposé

| Étape | Contenu | Schéma | Annonce dans `/v1/meta` | Protocole |
|---|---|---|---|---|
| 1 | Lot C : regroupements, suite d'une mission ; page Comptes sur l'existant | v5 | `regroupements`, `missions` | `acp-machine/1` |
| 2 | Lot D : journal étendu, copie kanban, route, sujet `activite` ; champs de carte servis (§ 5) | v6, ou v5 avec le lot C | `activite` | `acp-machine/1` |
| 3 | Exécutant seul : battements pendant toutes les étapes | aucun | aucune | `acp-machine/1` |
| 4 | Lot E : historique de la table, modes, critères, verdict | v7, ou avec les précédents | `modes_routage` | `acp-machine/1` |
| 5 | `acp-machine/2` : greffon prêt pour 1 et 2, puis image de l'exécutant | colonnes de l'étape 2 | niveau d'observation par machine | `acp-machine/2` négocié |

Chaque étape est un lot au sens de `CLAUDE.md` : branche depuis `main`, suite complète verte, CI verte, PR, fusion et
étiquette sur accord du propriétaire. Un ajout sans rupture reste dans `acp-poste/1` (D130).
