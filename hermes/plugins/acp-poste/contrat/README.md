# Contrat partagé `acp_poste_contrat`

Modèles Pydantic partagés par le **poste** (`apps/poste` : poste Windows de P5, exécutant Railway Linux de P6)
et le greffon Hermes **`acp-poste`** (`hermes/plugins/acp-poste`). Une seule source, jamais de copie : le poste
l'installe comme distribution locale (`pip install -e hermes/plugins/acp-poste/contrat`) ;
l'image Hermes le reçoit avec le greffon, puisque tout `hermes/` forme le contexte de
construction de l'image.

## Pourquoi ici

- Le plan (docs/refonte/plan.md) range les modèles Pydantic du greffon dans
  `hermes/plugins/acp-poste/contrat/`. Le contexte de construction de l'image est
  limité à `hermes/` : un contrat laissé dans `packages/` devrait être recopié dans
  l'image, et deux copies finissent par diverger.
- Le poste en dépend comme d'une distribution ordinaire ; le greffon n'a pas à
  dépendre de `apps/poste`.
- Dans l'image, le greffon l'importe **par son chemin** (`noyau/routage.py` et
  `noyau/motifs_secrets.py` ajoutent `contrat/` à `sys.path`) : rien n'est installé dans
  l'environnement de Hermes.

## Contenu

- `acp_poste_contrat.quotas` : relevés de quotas d'abonnement (Codex CLI, Claude
  Code), repris de `acp_contracts.subscriptions` (étiquette
  `archive/acp-0.10.0-avant-hermes`) ; P6 admet une seconde source Claude,
  `claude_code_rate_limit_event` (exécutions `claude -p` de l'exécutant, une fenêtre à la fois),
  par l'ensemble `QUOTA_SOURCES_BY_PROVIDER`.
- `acp_poste_contrat.inventaire` (P4, décision D21 ; **étendu en P5 sans rien
  restreindre**) : relevé d'une voie (`Releve`, `ModeleReleve`, `Quotas`, `Depot`),
  inventaire complet du poste (`InventairePoste` : relevés, bac à sable Codex,
  connexions, versions des CLI, politique de `poste.toml`), résumé des quotas calculé
  par le greffon (`resume_quotas`) et garde « aucun identifiant »
  (`identifiant_trouve` : motifs de secrets, `@`, chemins de lecteur, UNC ou de profil,
  jetons d'ACP). Tout relevé que P4 acceptait reste accepté (relevés factices et lignes
  déjà en base). **Étendu en P6** (cahier P6 § 7.3) : variante Linux de l'exécutant
  (`InfosPoste.plateforme`, `hote`, `noyau`, compte `uid_dedie`, `IsolementLinux` à la place de
  `BacASableCodex`, un seul bloc par plateforme), conditions d'usage et bornes d'exécution de la
  politique, résolutions observées admises. Tout inventaire de P5 reste valide. **Étendu en P7** (cahier P7
  § 11.2) : visibilité MESURÉE de chaque dépôt (`Depot.visibilite`, `lecture`, `verifie_le`, facultatifs ; un dépôt
  non mesuré se sérialise toujours `{"alias": …}`, forme inchangée pour un greffon de P6) ; le greffon ne prête la
  voie Codex qu'à un dépôt mesuré `prive` et lu `ok`.
- `acp_poste_contrat.machine` (P5, **étendu en P6**) : protocole `acp-machine/1` — requêtes et
  réponses des neuf routes machine (`enrolement`, `reclamer`, `inventaire` ; en P6 `battement`,
  `terminer`, `question`, `bloquer`, `reprendre`, `arret`, chacune avec un `id_envoi` idempotent),
  carte servie par `reclamer` (`DemandeCarte`, 60 Kio au plus), bornes des corps (4, 8, 32 et 256 Kio),
  balayage des secrets d'un corps (`secret_trouve`), forme des jetons
  (`acpm_…`, `acpe_…`), empreintes (SHA-256 gardé par le greffon, `XXXX-XXXX` affiché),
  forme des erreurs et corps exact du 401 de la couture de Hermes (ambigu, jamais
  une révocation certaine).
- `acp_poste_contrat.motifs_secrets` (déplacé du noyau du greffon en P5) : motifs de
  secrets refusés, une seule copie pour le greffon, le poste et
  `scripts/balayer_secrets.py` (parité testée).
- `acp_poste_contrat._validation` : refus des NUL et des instants hors plage UTC,
  seule partie de `acp_contracts.limits` dont ces modèles avaient besoin.

Les exemples de requêtes et de réponses du protocole machine
(`hermes/tests/outils/fixtures_machine/`) servent à la fois aux tests de ce contrat, aux
tests du greffon dans l'image et au faux Hermes des tests du poste : une divergence fait
échouer l'un d'eux.

Tests : `python -m pytest hermes/plugins/acp-poste/contrat/tests` depuis la racine.

## Coffre Markdown distinct (`acp-coffre/1`, ACP 1.2.0)

`acp_poste_contrat.coffre` définit une file de notes indépendante de `acp-machine/1`.
Le bridge Windows fonctionne sous le compte propriétaire, en HTTPS sortant vers la même
origine Hermes ; il n'écoute aucun port. Ni Hermes ni le desktop n'ouvrent les fichiers
locaux. Le coffre `acp` a son propre UUID, son jeton DPAPI et ses tables `coffres_*` :
il ne remplace jamais l'exécutant Railway et ne reçoit aucune commande ou tâche LLM.
`/v1/meta` annonce `capacites.coffre = "acp-coffre/1"` ; un serveur ancien peut répondre
404, ce qui exige sa mise à jour avant usage.

### Identité et autorisation

Toutes les routes ci-dessous sont relatives à `/api/plugins/acp-poste`.
Les routes `/v1/coffre*` exigent la session propriétaire ; les écritures refusent un
`Origin` présent différent de l'origine publique. Les trois routes `/coffre/v1/*`
exigent le fournisseur `acp-coffre` et la portée exacte `coffre_enrolement` ou `coffre`.
Un cookie ne suffit pas au bridge ; un jeton de machine ne vaut pas pour le coffre,
et réciproquement. Aucun outil générique ni route d'exécution n'est ajouté à Hermes.

| Geste propriétaire | Corps / réponse |
| --- | --- |
| `GET /v1/coffre` | Protocole, état `non_configure`, `a_confirmer`, `hors_ligne`, `pret` ou `revoque` ; identité, empreinte, dernière présence et capacités réellement annoncées. |
| `POST /v1/coffre/enrolement` | `{}` → code à usage unique, durée et échéance. |
| `POST /v1/coffre/confirmer` | `coffre_id`, empreinte `XXXX-XXXX` comparée avec celle du bridge. |
| `POST /v1/coffre/revoquer` | `coffre_id`, motif de 1 à 200 caractères ; arrête les nouvelles opérations. |
| `POST /v1/coffre/operations` | UUID `id_operation`, `coffre_id`, `action`, `parametres` → 202 et état réel. |
| `GET /v1/coffre/operations/{UUID}` | État, dates, résultat ou erreur ; aucun succès déduit de la seule livraison. |

`POST /coffre/v1/enrolement` reçoit protocole, version du bridge, UUID local et alias
`acp`. Le porteur est le code `acpce_…` de 256 bits valable **600 secondes**, rendu
une fois ; le serveur ne conserve que son SHA-256. Le jeton `acpct_…`, également de
256 bits, est remis une fois ; seul son SHA-256 est stocké côté Hermes. Sa portée est
celle du coffre et il reste valable jusqu'à révocation. Il ne devient actif qu'après
confirmation de l'empreinte par le propriétaire. Un nouveau code permet de réassocier
le même coffre **non actif**, avec rotation du jeton et nouvelle confirmation ; les
notes restent en place. Une association active doit d'abord être révoquée. Le principal
du bridge porte aussi l’empreinte de la génération du jeton reconnue à l’authentification ;
chaque tick du long-poll et chaque résultat la revérifient sous transaction. Une requête
antérieure à la rotation ne retrouve donc aucun droit après réassociation du même UUID.

`POST /coffre/v1/reclamer` reçoit protocole, UUID, capacités et attente de 0 à 25 secondes.
Il rend `a_confirmer` sans opération, ou `actif` avec une opération éventuelle.
`POST /coffre/v1/resultat` reçoit protocole, UUID du coffre et de l'opération, état
`reussie`, `refusee` ou `indeterminee`, et soit résultat, soit erreur. L'accusé
`{ok:true,id_operation,deja:bool}` confirme sa réception, pas une réussite de la note.
Une révocation certaine rend 401 `coffre_revoque` ; un 401 sans ce code reste ambigu
et ne justifie pas l'effacement automatique du jeton.

### Périmètre, résultats et reprise

Actions fermées : `lister`, `lire`, `rechercher`, `creer`, `ecrire`, `archiver`,
`renommer`, `backlinks`, `graphe`. Les chemins sont relatifs POSIX, Markdown `.md`,
au plus 240 caractères ; aucun lecteur, UNC, traversée, fichier caché ou nom réservé.
Le bridge refuse aussi liens, jonctions et fichiers à liens physiques multiples.
Une note est UTF-8, au plus **128 Kio** ; chaque corps JSON complet reste sous
**192 Kio**, y compris l'échappement. Les routes propriétaire hors création d'opération
gardent leur limite de **64 Kio**. Liste : 200 notes ; recherche : 100 extraits ;
graphe : 500 nœuds et 2 000 liens au plus. Les projections signalent `tronque`.

Une lecture donne chemin, contenu, SHA-256 et nombre d'octets. `ecrire`, `archiver`
et `renommer` exigent l'empreinte attendue ; un conflit refuse la mutation et exige
une relecture, sans écraser le brouillon. Une création refuse un fichier existant.
Une écriture garde une archive locale de l'ancienne version ; archiver ne supprime
jamais définitivement la note. Renommer déplace sans écraser et rend
`liens_modifies:false` : aucun lien entre notes n'est réécrit silencieusement.
Le graphe couvre les liens Markdown et wikiliens textuels ; les extensions Obsidian
ne sont pas interprétées.

La file est limitée à **32 opérations en attente ou en cours**. L'UUID est la clé
d'idempotence, sans en-tête supplémentaire : même demande, même réponse ; corps
différent pour le même UUID, refus 409. La livraison répétée garde la même enveloppe,
y compris l'échéance. Le bridge conserve un journal avant mutation et son résultat
avant envoi ; une mutation commencée sans preuve finale reste indéterminée et n'est
jamais répétée aveuglément. Même résultat rejoué, même accusé ; résultat différent,
refus 409. Les motifs de secrets connus sont refusés ; un résultat ainsi filtré est
conservé uniquement comme verdict `refusee` / `secret`, sans son contenu. Ce contrôle
par motifs n'est pas une garantie contre toutes les formes de secrets.

### Délais et rétention

L'opération expire **600 secondes après sa création**. Non livrée, elle devient
`expiree` ; déjà livrée, `indeterminee`, car une modification locale peut avoir eu
lieu. Un résultat tardif est accepté tant que l'identité reste active et que la ligne
est encore conservée. La révocation empêche toute nouvelle livraison mais ne peut
annuler une écriture locale déjà commencée.

Les paramètres (donc un éventuel contenu à écrire) restent en base jusqu'au résultat
ou à l'échéance. Les résultats textuels sont purgés après **échéance + 1 heure** ;
la projection devient alors `expiree`, sans prétendre disposer encore d'une preuve
consultable. Les métadonnées et empreintes d'idempotence sont supprimées après
**échéance + 24 heures**. Cette purge est déclenchée par les accès au coffre, sans
planificateur dédié ; une file inactive peut donc rester plus longtemps en base.
Les textes transitent par la base SQLite Hermes : WAL, pages libérées et sauvegardes
du volume peuvent conserver des copies au-delà de ces délais. Ce mécanisme n'est
pas un effacement cryptographique et ne remplace pas la politique de sauvegarde.
Les archives et le journal local du bridge ont leur propre rétention locale.

Si le bridge conserve un résultat après cette purge, seul le refus **404** avec
`detail.code=operation_inconnue` sur `POST /coffre/v1/resultat` lui permet de reprendre
la file. Il déplace d'abord le résultat intact, sans écrasement, vers
`%LOCALAPPDATA%/ACP/coffre-notes/resultats-non-acquittes/<UUID>.json`, puis annonce
**« Résultat non acquitté »**. Ce n'est ni une confirmation par Hermes ni une
réexécution de la mutation : relire la note et ses archives avant de la modifier.
Ces copies locales restent récupérables jusqu'à leur rangement par le propriétaire.
Le dossier est limité à 128 fichiers ; une copie déjà présente, un dossier plein ou
un échec de déplacement conserve l'outbox et bloque la reprise avec un refus explicite.
Tout autre refus HTTP conserve aussi le résultat en attente. Après réassociation,
confirmer l'empreinte dans ACP avant de redémarrer le bridge ; une identité encore
`a_confirmer` ne donne pas le droit de transmettre l'ancien résultat.

La présence est périmée après **75 secondes**. Le bridge utilise un long-poll de
25 secondes puis une pause d'une seconde ; les erreurs réseau temporaires déclenchent
une attente progressive de 2 à 60 secondes. Aucun démarrage automatique d'Obsidian,
service Windows ni connexion à un coffre personnel n'est démontré par ces mécanismes.

### Validation du lot

Tests purs sur base SQLite jetable, contrat et adaptateur d’authentification simulé,
sans dépendance FastAPI dans la suite commune Linux/Windows :

```text
python -m pytest scripts/tests/test_coffre_backend.py hermes/plugins/acp-poste/contrat/tests/test_coffre.py hermes/plugins/acp-poste/contrat/tests/test_motifs_parite.py -q
```

**42 tests réussis** le 12 octobre 2026 (1,92 s), couvrant notamment confirmation,
rotation après révocation ou réponse perdue, séparation des identités, bornes, secrets,
rejeux, expirations, réponse tardive et purge. Les **21 tests du scanner**
`scripts/tests/test_balayer_secrets.py` ont aussi réussi dans le passage précédent.

Les **cinq tests** `hermes/tests/image/test_jeton_coffre.py` appartiennent à la suite
obligatoire de l’image Hermes, où FastAPI et l’authentification du serveur épinglé sont
disponibles. Ils couvrent le vrai fournisseur, la couture machine/coffre, les droits
HTTP, les bornes des corps et la contrepreuve d’une rotation pendant un long-poll déjà
authentifié. Aucun test HTTP n’est ignoré ni rendu facultatif en l’absence de FastAPI
sur l’hôte ; son exécution relève de la validation centralisée de l’image. Ces tests
n’associent aucun coffre ou compte personnel.
