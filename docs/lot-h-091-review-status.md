# Reprise du durcissement Lot H — 0.9.1

Reprise du 22 septembre 2026 sur `fix/lot-h-hardening` : corrections intégrées et
validation locale complète avec reprises ciblées, détaillée plus bas. La préparation
de 0.9.1 reste ouverte : 26 constats ne sont pas corrigés, aucun déploiement Railway
n'est validé. L'inventaire historique ci-dessous ne constitue pas, à lui seul, une
preuve de résolution.

## Sources et preuves disponibles

- Mémoire locale `lot-progress.md` : K1–K5, R1–R6 et R43 annoncés corrigés jusqu'à
  `df248cc`. R32 est couvert par la garde du volume déjà présente. Ces corrections
  doivent rester couvertes par la validation finale.
- Revue `wf_d3e19e79-ff5`, export `review_result_v2.json` dans le scratchpad de la
  session `eaafbbf5-28c5-4744-abde-205a3bfddd64` : constats et votes contradictoires.
  Les emplacements décrivent initialement v0.9.0 et doivent être relus.
- R44 est déjà corrigé selon la reprise historique (marqueurs de dialecte et CI
  PostgreSQL). R42 et R47 sont réfutés ; aucun correctif à inventer sans nouveau cas.
- Workflow initial `wf_e6e3a104-a75`, puis reprise `wf_64a7fddc-128` : les huit
  implémenteurs ont atteint la limite de session. Le second résultat contient huit
  valeurs nulles ; les huit erreurs mentionnent la limite hebdomadaire. Aucune revue
  contradictoire ni passe de correction de ces implémentations n'a abouti.
- État Git initial : intégration `lot-h-hardening` à `df248cc`, correction budgétaire
  et test PostgreSQL non commités ; relay, schema, retention et tooling contiennent
  des partiels ; deploy contient `1668bdd` (R34 seulement) ; backup, worker et async
  sont propres à `df248cc`.
- État distant vérifié le 22 septembre : la
  [CI de `df248cc`](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35411850694)
  est verte et aucune PR n'est ouverte pour `fix/lot-h-hardening`. Cette preuve
  porte sur la base de départ, pas sur les modifications de cette reprise.

## Répartition à la reprise

Les worktrees sont sous `.claude/worktrees/`. Les branches sont
`fix/lot-h-091-<lot>`. Un partiel ou commit isolé n'est pas déclaré résolu avant
relecture et validation.

| Lot | Worktree | Base PostgreSQL réservée | État initial |
|---|---|---|---|
| relay | `wf_e6e3a104-a75-1` | `acp_wf_c` | code et tests partiels |
| schema | `wf_e6e3a104-a75-2` | `acp_wf_d` | tests partiels |
| backup | `wf_e6e3a104-a75-3` | `acp_wf_e` | aucune correction |
| retention | `wf_e6e3a104-a75-4` | `acp_wf_f` | tests rouges R28 |
| deploy | `wf_e6e3a104-a75-5` | `acp_wf_g` | R34 commité, reste ouvert |
| worker | `lot-h-091-worker` | `acp_wf_h` | aucune correction |
| async | `lot-h-091-async` | `acp_wf_i` | aucune correction |
| tooling | `lot-h-091-tooling` | `acp_wf_j` | correction et tests R45 partiels |

## Défauts et actions attendues

| Constat | Lot | Défaut et correction à vérifier |
|---|---|---|
| R7 | relay | Exception hors transport empoisonnant la tête d'outbox ; isoler le message, borner les essais déterministes, sécuriser l'identifiant d'en-tête. |
| R8 | relay | HTTP privé refusé par `normalize_service_origin` ; autorisation explicite et bornée des hôtes internes, maintien du TLS public. |
| R10 | relay | Panne consommateur comptée comme défaut du message ; recul sans épuiser les essais pour transport, 5xx et authentification du service. |
| R11 | relay | Verrou SQLite tenu pendant HTTP ; terminer la transaction avant l'appel, conserver l'exclusivité et l'ordre du relais. |
| R12 | relay | Relais démarrant avant la migration ; attente bornée du schéma avec sortie explicite, reprise documentée. |
| R9 | schema | Horodatage valide localement mais UTC hors plage Python ; normaliser et valider à l'entrée. |
| R14 | schema | INTEGER PostgreSQL trop petit pour codes Windows, tailles et durées ; BigInteger/migration ou bornes contractuelles, aller-retour de migration. |
| R15 | schema | NUL et chaînes trop longues acceptés par SQLite ; validation commune et DataError traduit en 422 français sans SQL. |
| R16 | schema | `stamp` peut déclarer prête une base sans tables ; garde de conformité et présence du schéma au démarrage. |
| R17 | schema | Vérification de dérive ignorant CHECK et prédicats partiels ; les comparer ou annoncer exactement la limite. |
| R18 | schema | Base en avance présentée comme en retard ; distinction explicite, pas de downgrade implicite. |
| R13 | backup | Restauration faisant reculer les curseurs SSE ; époque ou marqueur empêchant une reprise silencieusement incomplète. |
| R19 | backup | Substitution d'URL des outils comparant seulement le nom de base ; vérifier identité complète et cohérence de la sauvegarde. |
| R20 | backup | Répertoires non remis en place après échec de restauration ; rollback des fichiers et état final explicite. |
| R21 | backup | Garde de la base source fondée sur texte d'URL ; identité normalisée complète, protection des répertoires source. |
| R22 | backup | Archive déclarée conforme malgré blobs/révisions référencés absents ; contrôler couverture et empreintes create/verify. |
| R23 | backup | Image sans outils PostgreSQL utilisables ; client de même version majeure ou refus explicite documenté. |
| R24 | backup | Mot de passe dans argv des outils ; entrée par environnement/fichier protégé et expurgation des erreurs. |
| R25 | backup | Sauvegardes lisibles par tous ; permissions 0600/0700, temporaires compris. |
| R26 | backup | Remplacement d'une cible en service ; refus/option explicite et protection contre écritures concurrentes. |
| R27 | backup | URI SQLite concaténée interprétant #, ? ou % ; `Path.as_uri()` et ouverture en lecture seule. |
| R28 | retention | Chemins de révisions 0.8.0 mal résolus ; compatibilité héritée confinée sous la racine, sans migration. |
| R29 | retention | Purge avec délais applicatifs et sans verrou ; moteur maintenance, verrou partagé et lots bornés. |
| R30 | retention | Suppression d'un blob réutilisé par upload concurrent ; coordination/verrou ou période de grâce. |
| R31 | retention | Compteur de suppressions fictif sur racine incorrecte ; refus explicite et compte des fichiers réellement supprimés. |
| R33 | deploy | `/ready` public coûteux et trop détaillé ; réponse minimale, cache à calcul unique, détail protégé. |
| R34 | deploy | Assets sous licence et fichiers sensibles imbriqués dans contexte Docker ; exclusions récursives vérifiées sur liste effective. Commit `1668bdd` à revoir. |
| R35 | deploy | Services en superutilisateur et secrets partagés ; rôles migration/application/lecture, environnement minimal et limites documentées. |
| R36 | deploy | Proxy Railway non reconnu et quotas par IP faussés ; confiance proxy bornée, pas de joker injustifié. |
| R37 | deploy | Origine d'aperçu reconstruite en HTTP derrière TLS et configuration absente ; origine publique fiable et procédure complète. |
| R38 | deploy | Cache immutable sur assets sans empreinte ; limiter aux noms versionnés, revalidation des autres. |
| R39 | deploy | Cookie Strict incompatible web/API inter-sites ; domaine enregistrable commun exigé, avertissement de configuration, aperçu distinct. |
| R40 | deploy | Vérificateur acceptant mauvais processus ; commande effective exacte, montage et couverture des sources. |
| R41 | deploy | Volume root incompatible uid 10001 ; procédure et contrôle des droits sans chmod 777. |
| N2-1 | worker | Renouvellement transitoirement refusé arrêtant une tentative saine ; réessais jusqu'à échéance locale monotone du bail. |
| N2-2 | worker | PATCH terminal/événement 503 transformant un succès en échec ; rejouer même corps et préserver preuve. |
| N2-3 | worker | Rapport budgétaire refusé jetant résultat d'effet réussi ; identifiants stables, réessais et rapprochement en attente explicite. |
| N2-4 | worker | Dépôt/ingestion 503 faisant échouer suite verte ; rejouer uploads fichier rouvert et lot idempotent. |
| N2-5 | worker | Délai client inférieur aux attentes serveur, claim orphelin ; délai adapté et récupération d'attribution après résultat incertain. |
| N2-8 | async | Session SQLAlchemy, verrous et fichiers sur boucle async ; phases courtes en threadpool, aucune transaction pendant réseau. |
| R45 | tooling | Moteur de tests SQLite sans FK ; écouteur partagé production/tests, corriger fixtures et défauts révélés sans désactiver contraintes. |
| R46 | tooling | CI sans verrou effectif et vérificateur incomplet ; hashes/no-deps, pip check, couverture dépendances pyproject/.in/verrou. |

Tous ces constats ont trois votes de confirmation, sauf R10, R16 et R39
(deux confirmations et une réfutation). R42 a trois réfutations ; R47 a deux
réfutations contre une confirmation. Les désaccords restent consultables dans
l'export original ; un vote n'est pas une preuve de correction.

## Travail local sur le journal

- **N2-6**, confirmé 3/3 : les deux `FOR UPDATE` sur `projects` dans
  `budget_service.py` bloquent les `KEY SHARE` implicites des insertions filles.
  Le journal pris en dernier rompt déjà le cycle décrit à v0.9.0 ; passer à
  `FOR NO KEY UPDATE` conserve la sérialisation et permet les insertions filles.
  Le test PostgreSQL initial était rouge et le correctif non commité.
- **N2-7**, confirmé 3/3 : l'ingestion de milliers de cas gardait le verrou global
  depuis `run_started` jusqu'au commit final, avec de nombreux allers-retours par
  cas. Les autres publications dépassaient leur délai et répondaient 503.
  `df248cc` numérote déjà au commit : vérifier ce code avant de conclure. Préparer
  les événements avant verrou puis les écrire en lot et allouer un bloc de
  séquences ; tester un gros rapport contre un permis budgétaire concurrent.
  Préserver l'atomicité métier/journal et l'ordre des curseurs.

## Validation et intégration restantes

- Python 3.12 : `.claude/worktrees/lot-h-hardening/.venv/Scripts/python.exe`.
  Les sous-processus exigent un PYTHONPATH vers les sources du worktree testé,
  car les installations éditables pointent vers un autre worktree.
- PostgreSQL 16 portable : `%USERPROFILE%/.acp-tools/pg16/pgsql/bin`, données
  `%USERPROFILE%/.acp-tools/pgdata16`, hôte `127.0.0.1`, port `55432`.
  Employer uniquement les bases réservées ; suffixes `_guard` et `_restore`
  utilisés par les tests. Aucun secret n'est consigné ici.
- PostgreSQL : `ACP_TEST_DATABASE_REQUIRED=1` ; sauvegardes :
  `ACP_TEST_PG_TOOLS=native` et binaires dans PATH.
- Sandbox Windows : `--basetemp` neuf sous le worktree, parent créé au préalable.
  Conserver les sorties et signaler les tests ignorés.
- Seul schema ajoute une migration Alembic. Conflits prévisibles : schema/tooling
  dans `engine.py` ; schema/deploy dans `readiness.py` ; backup/retention pour
  skills et documentation ; async/retention pour les uploads et le stockage.
- Après intégration : suites complètes SQLite et PostgreSQL, contrôles du dépôt et
  du déploiement, revue contradictoire, journal 0.9.1, PR et CI verte. Fusion et tag
  uniquement après validation explicite de l'utilisateur. Préserver le chantier
  desktop/pixel-office du dépôt principal.

## Reprise du 22 septembre — intégration et preuves ciblées

Les changements ci-dessous sont réunis dans `fix/lot-h-hardening`, depuis
`df248cc`. Les worktrees de lot conservent leurs fichiers de reprise ; leurs
modifications ont été appliquées et relues dans l'intégration. Les preuves
ciblées ne remplacent pas les suites complètes décrites plus bas.
Les corrections issues des dernières contre-revues sont dans cette intégration :
repartir de sa tête pour les prochains lots, plutôt que de réappliquer les anciens
diffs des worktrees conservés.

- N2-6 : correction des deux verrous de projet dans `lot-h-hardening` ; trois tests
  PostgreSQL passent (insertion fille pendant une décision et pendant un PUT de
  politique, sérialisation des décisions conservée). Relecture indépendante sans
  défaut bloquant confirmé.
- N2-7 : le code du journal de `df248cc` couvre déjà le défaut ; nouveau test réel
  avec 2 000 cas, un permis concurrent sous `lock_timeout=1000ms`, relais activé et
  vérification des séquences après commit. Test réussi ; aucune modification
  supplémentaire du journal nécessaire pour ce scénario.
- R27 : `wf_e6e3a104-a75-3`, `_quick_check` utilise `Path.as_uri()` et conserve
  `mode=ro`. Régression reproduite avant correction (échec avec `%20`, création
  indue d'un fichier avec `%23#`) ; 20 tests `test_snapshot.py` réussis après.
  Aucun autre constat backup n'est déclaré corrigé.
- R34 : commit préexistant `1668bdd` relu ; 27 tests de contexte Docker et de
  configuration du déploiement réussis. Pas de construction d'image exécutée.
- R7, R8, R10, R11, R12 : messages illisibles isolés et diagnostics expurgés,
  autorisation exacte des hôtes HTTP internes, pannes du consommateur sans
  épuisement des essais, verrou SQLite rendu avant HTTP avec réservation persistée, attente bornée du
  schéma au démarrage. 110 tests PostgreSQL réussis et 6 tests SQLite ignorés dans
  le lot ; les 19 tests du relais passent sur chaque dialecte après le dernier
  correctif de recul. Livraison toujours au moins une fois, une réplique requise
  pour conserver l'ordre global.
- R9, R14–R18 : validation des NUL, bornes numériques et textuelles, UTC lisible ;
  migration 0003 vers BIGINT/TEXT sous PostgreSQL ; adoption du schéma et démarrage
  refusés si la révision est inconnue ou les tables absentes. Le contrôle compare
  les noms des CHECK et les prédicats partiels, mais pas le corps SQL des CHECK.
  582 tests de contrats, 27 tests SQLite de migration/limites, 51 tests PostgreSQL
  HTTP/readiness et les 20 tests Alembic PostgreSQL ont été exercés avec succès.
- R28 : stockage résolu par `<racine>/<skill_id>/<numéro>`, y compris pour les
  anciennes adresses absolues ou relatives ; confinement conservé. Le diagnostic
  de restauration contrôle ce chemin canonique. Les quatre régressions du
  diagnostic ont été reproduites puis corrigées ; module complet de restauration :
  29 tests réussis. Les lots de compétences passent aussi (57 SQLite, 6 PostgreSQL).
- R45–R46 : clés étrangères SQLite activées par un écouteur commun aux moteurs
  de production et de test ; fixtures corrigées. CI Python avec verrou haché,
  `--no-deps`, `--no-build-isolation` et `pip check` ; vérificateur couvrant
  dépendances runtime, extras et construction, dont les contraintes de `.in`.
  59 tests SQLite et 31 PostgreSQL réussis dans le lot (3 propres à SQLite ignorés).
  Les 43 versions du verrou sont cohérentes ; `pip check` local réussit.
- Les relectures ont identifié
  deux corrections supplémentaires : recul du relais remis à zéro sur un lot
  temporairement vide, et garde de migration empruntant une seconde connexion
  alors que le pool peut être limité à une seule. Les deux sont corrigées et
  couvertes. La fixture d'outbox orpheline utilise une connexion séparée pour
  fabriquer une corruption historique, puis vérifie les FK réactivées avant le
  relais ; cinq tests ciblés de l'intégration passent.
- Dernière revue de l'intégration : les alias Alembic `heads` et les préfixes de
  révision sont résolus avant le contrôle d'adoption, sans contournement de la
  garde de tête ; 27 tests Alembic PostgreSQL passent après trois échecs reproduits.
  Les sorties NUL du runner local sont adaptées sur la copie du DTO seulement,
  avec conservation des preuves brutes et de leurs empreintes ; les entrées
  utilisateur et les secrets ne sont pas normalisés. Le contexte Docker exclut
  également les fichiers auxiliaires SQLite, et les classes de motifs sont
  confrontées à la sémantique de Moby.
- Les premières suites complètes ont été interrompues pour arrêter la concurrence
  disque entre lots, puis corriger les interactions de fixtures : elles ne sont
  **pas** des preuves de réussite. Journaux conservés sous `.test-tmp/`.
- Le serveur PostgreSQL natif est disponible ; Docker n'a pas de daemon actif.
  Les preuves locales Windows ne couvrent pas l'installation exacte du verrou
  Linux dans un environnement neuf. Les résultats distants (suites Linux,
  dépendances verrouillées et construction web) sont à consulter dans la PR
  associée à `fix/lot-h-hardening` et dans le
  [workflow de la branche](https://github.com/Paul-Berdier/agent-company-platform/actions?query=branch%3Afix%2Flot-h-hardening).

## Constats restant ouverts après cette intégration

R13, R19–R26, R29–R31, R33, R35–R41, N2-1–N2-5 et N2-8 ne sont pas déclarés
corrigés. Leurs objectifs restent ceux de l'inventaire ci-dessus. Cette reprise ne
constitue ni la publication de 0.9.1 ni une validation d'exploitation Railway.

## Validation complète de l'intégration

Python 3.12.10, PostgreSQL 16 natif ; base de test marquée `acp_verify`, port local
55432, exclusivement. Les deux dialectes couvrent les mêmes **2 922 tests distincts**.
Les empreintes des 65 fichiers de code et de tests modifiés ont été contrôlées avant
les commits ; les reprises ciblées ci-dessous n'ont modifié aucune source produit.

SQLite : **2 852 réussis, 70 ignorés** après recoupement par identité de test :

- `full-final-4-sqlite.xml` : 2 850 réussis, 70 ignorés et 2 échecs en 856 s ;
- `final-sqlite-cli.xml` : les 26 tests de configuration CLI réussissent en 2 s
  avec l'entrée standard `python -m pytest`. Le lanceur local temporaire appelait
  pytest lors de son import par les sous-processus Windows ; sa garde `__main__`
  manquait. Ce lanceur a été corrigé, sans changement du produit ni de ses tests.

Les 70 ignorés SQLite sont 60 tests PostgreSQL et 10 limitations Windows. Le rapport
initial reste conservé avec ses deux échecs : validation avec reprise ciblée, pas
une exécution unique sans incident.

PostgreSQL : **2 862 réussis, 60 ignorés** après recoupement par identité de test
des deux rapports suivants (2 922 tests distincts) :

- `full-final-4-postgres.xml` : 2 850 réussis, 60 ignorés et 2 erreurs de préparation
  dues aux outils PG absents du PATH vu par Python, en 1 481 s ;
- `final-postgres-backup.xml` : 12 réussis en 26 s, dont les deux tests concernés
  et dix nouvelles vérifications de contraintes. Le PATH a été préfixé dans Python.
  Le helper de comparaison a été adapté aux tuples structurels ; aucune source
  produit n'a changé entre les deux exécutions (empreintes contrôlées).

Les 60 ignorés PostgreSQL sont 50 tests propres à SQLite et les 10 limitations
Windows détaillées plus bas. Les rapports originaux conservent les erreurs initiales :
il s'agit d'une validation complète avec reprise ciblée, pas d'une exécution unique
sans incident.

Parcours sur de vraies API locales, tous réussis avec les sources finales :

| Parcours | SQLite 3.49.1 | PostgreSQL 16.15 |
|---|---:|---:|
| Journal, événements et reprise SSE | 74/74 | 77/77 |
| Automatisations | 62/62 | 65/65 |
| Sauvegarde/restauration et relecture HTTP | 42/42 | 48/48 |

Journaux : `.test-tmp/journey-<dialecte>-<parcours>.log`. Les bases dédiées
`acp_resume_20260922_{events,automation,backup,restore}` ont été créées vides et
marquées avant exécution ; les parcours ont remis leurs schémas à zéro à la fin.
Les outils PG ont été fournis par chemins absolus aux sous-processus Windows.
Ces parcours couvrent l'API locale, pas un navigateur ni Railway.

Construction locale réussie des roues `acp-contracts`, `acp-database` et `acp-api`
0.9.1, avec `pip wheel --no-index --no-deps --no-build-isolation` depuis des copies
isolées des sources finales. Présence et identité des nouveaux modules de validation,
de la migration 0003 et du relais vérifiées dans les archives produites. Journal
local : `.test-tmp/package-build.log` ; cette preuve ne vaut pas construction Docker.

Première exécution complète SQLite (`full-final-3-sqlite.xml`) : 2 837 réussis,
70 ignorés, 2 échecs en 756 s. Elle a identifié une assertion MCP devenue obsolète
(NUL refusé plus tôt, toujours en 422) et un contenu binaire de compétence refusé
à tort comme une donnée de base. Ces résultats précèdent leur correction et ne
constituent pas une validation finale. Les 70 ignorés comprennent 60 tests
PostgreSQL et 10 dépendant de possibilités POSIX, de liens symboliques ou de `sh`.

## Ordre conseillé pour les prochains lots

1. **Restauration** : R19/R21 (identité réelle des bases et chemins) → R22
   (couverture et empreintes des fichiers depuis le même instantané) → R26
   (cible inactive pendant toute l'opération) → R20 (récupération SQL et fichiers
   après échec). Réutiliser `test_snapshot.py`, les fixtures et empreintes de
   `test_backup_restore.py`, puis `verify_backup_restore.py` sur les deux dialectes.
2. **Worker** : socle de réessais bornés par l'échéance monotone du bail, puis N2-1
   (renouvellement), N2-5 (claim incertain et délais), N2-2 (publication terminale
   idempotente), N2-3 (rapprochement budgétaire sans rejouer l'effet) et N2-4
   (téléversement/ingestion). Étendre `test_real_worker.py`, `test_budget.py` et
   `test_web_tests.py`. Les réponses perdues après commit exigent une garantie API.
3. **Déploiement** : R35 (rôles/secrets) → R41 (droits des volumes) → R33
   (readiness) → R36 (proxy) → R39 (domaines/cookies) → R37 (aperçu), puis R40
   (configuration effective). R38 (cache nginx) est indépendant. Les permissions
   des volumes, l'IP du proxy, DNS/TLS, les cookies et la persistance après
   redéploiement exigent une preuve Railway réelle. Le partage du stockage entre
   API et aperçu demeure un point distinct à résoudre.
4. **Rétention** : R29 (moteur maintenance/lots bornés) → R30 (exclusion par clé
   de contenu entre purge et upload jusqu'au commit) → R31 (racine vérifiée et
   compte des suppressions effectives). Le verrou actuel par run ne protège pas
   les blobs partagés. Coordonner ce protocole avec R22/R26 et conserver l'ordre
   des verrous. Étendre `test_retention.py`, `test_artifacts_storage.py` et
   `test_artifact_quota_concurrency.py`.
5. **N2-8** : isoler les phases SQL/fichiers synchrones dans les routes uploads
   (`operations.py`, `artifacts.py`), conversations et contrôles initiaux SSE.
   Le générateur SSE délègue déjà ses lectures à `asyncio.to_thread`. Prouver la
   réactivité simultanée pendant verrou SQL ou spool lent, sans perdre fencing,
   idempotence ni isolation des sessions ; réutiliser les tests de conversations,
   de contenu des artefacts et d'événements.
6. **R13** : époque ou invalidation explicite commune aux curseurs globaux et de
   runs, à la pagination, au SSE et à `apps/web/src/events-api.ts`. Le marqueur
   ne doit apparaître qu'après restauration réussie, avant réouverture (R20/R26).
   Étendre les round-trips backup, `test_events_stream.py` et
   `apps/web/tests/events-api.test.ts` : sauvegarder, avancer, restaurer, publier,
   puis vérifier une reprise explicitement réinitialisée sans perte silencieuse.
