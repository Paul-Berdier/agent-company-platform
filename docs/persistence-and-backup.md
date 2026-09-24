# Persistance, sauvegarde et restauration

Date d'état : 17 septembre 2026 — version en développement `0.9.0` (Lot H)
Statut : **brouillon**. Les commandes décrites ici sont livrées et prouvées par des
tests SQLite, des tests PostgreSQL 16 (via `docker exec`) et le parcours
`scripts/verify_backup_restore.py` sur les deux dialectes ; aucune sauvegarde de
production n'a encore été exécutée ni planifiée.

## Ce que contient l'état persistant

| Composant | Emplacement | Variable |
| --- | --- | --- |
| Base de données | SQLite fichier (défaut `./acp.db`) ou PostgreSQL 16 | `ACP_DATABASE_URL` |
| Livrables (blobs adressés par contenu) | `./acp-data/artifacts/<sha256[0:2]>/<sha256>` | `ACP_ARTIFACT_STORAGE_DIR` |
| Révisions de skills | `./acp-data/skills/<skill_id>/<numéro>/` | `ACP_SKILLS_STORAGE_DIR` |
| Clés du coffre de secrets | jamais sur disque : variable d'environnement seulement | `ACP_SECRETS_KEYS` |

La base cite les fichiers (`artifacts.storage_key`, `skill_revisions.storage_path`)
mais ne les contient pas ; les secrets sont chiffrés en base avec une clé Fernet
que la sauvegarde **ne copie jamais**. Une sauvegarde restaurée sans les mêmes
clés dans `ACP_SECRETS_KEYS` garde des secrets indéchiffrables : c'est signalé,
et refusé avec `--require-secret-keys`.

## Commandes

```text
python -m acp_api.backup create --output DIR [--database-url URL]
        [--artifacts-dir D] [--skills-dir D] [--label TXT]
python -m acp_api.backup verify DIR
python -m acp_api.backup inspect DIR
python -m acp_api.backup restore DIR --into URL [--artifacts-dir D] [--skills-dir D]
        [--replace --pre-restore-backup DIR2] [--require-secret-keys]
```

Codes de sortie : `0` succès ; `1` échec d'exécution (outil `pg_dump`/`pg_restore`
en échec, base injoignable) ; `2` usage ; `3` refus explicite ou écart constaté.
Sans option, `--database-url` vaut `ACP_DATABASE_URL` et les répertoires viennent
de `ACP_ARTIFACT_STORAGE_DIR` et `ACP_SKILLS_STORAGE_DIR`. Les moteurs ouverts par la
commande sont en mode maintenance (aucun `statement_timeout`).

### `create`

Ordre imposé et non configurable : **la base d'abord, les fichiers ensuite**.
L'API écrit toujours un blob avant la ligne qui le cite ; l'instantané de base
pris en premier ne peut donc citer qu'un blob déjà présent quand l'archive est
constituée. L'ordre inverse pourrait archiver un état des fichiers antérieur à une
ligne de la base.

- SQLite : copie `VACUUM INTO` sur une connexion dédiée, cohérente même si l'API
  écrit pendant la sauvegarde (une transaction en cours n'y figure pas), contrôlée
  par `PRAGMA quick_check` puis renommée atomiquement. Révision, comptages et
  références sont lus **dans la copie** : le manifeste décrit exactement le fichier
  livré.
- PostgreSQL : `pg_dump --format=custom --no-owner --no-privileges` dont la sortie
  standard est capturée dans `database.pgdump` (jamais `-f`, pour fonctionner dans
  un conteneur). Révision et comptages sont lus sur la base après le dump ; si un
  comptage a bougé entre le début et la fin, le manifeste le dit dans `warnings`.
- `artifacts.tar` : les fichiers de `ACP_ARTIFACT_STORAGE_DIR` sauf `tmp/` et les
  fragments `*.part` ; `skills.tar` : tout `ACP_SKILLS_STORAGE_DIR`. Un répertoire
  absent donne une archive vide et un avertissement. Les liens symboliques sont
  ignorés avec avertissement, jamais suivis.

Le répertoire de sortie doit être absent ou vide : une sauvegarde n'écrase jamais
une sauvegarde.

### Manifeste (`manifest.json`, `format_version` 1)

```json
{
  "format_version": 1,
  "created_at": "2026-09-17T10:12:41+00:00",
  "product_version": "0.9.0",
  "label": "nuit",
  "database": {
    "dialect": "postgresql",
    "alembic_current": "0002",
    "file": "database.pgdump",
    "sha256": "…", "bytes": 123456,
    "row_counts": {"artifacts": 3, "events": 12, "…": 0}
  },
  "directories": [
    {"name": "artifacts", "archive": "artifacts.tar", "sha256": "…", "bytes": 20480, "entries": 2},
    {"name": "skills", "archive": "skills.tar", "sha256": "…", "bytes": 10240, "entries": 1}
  ],
  "artifact_storage_keys_referenced": ["ab/ab12…"],
  "secrets_key_ids": ["e6e17260e38b"],
  "source_url_fingerprint": "sha256 de l'URL sans mot de passe",
  "warnings": []
}
```

`secrets_key_ids` liste les identifiants publics (jamais les clés) des clés ayant
chiffré un secret non révoqué. `source_url_fingerprint` identifie la base d'origine
(chemin absolu pour SQLite, URL masquée pour PostgreSQL) : c'est elle qui interdit
de restaurer une sauvegarde sur sa propre source.

### `verify`

Recalcule empreintes et tailles, exige la présence de chaque fichier annoncé,
contrôle l'en-tête de l'instantané (`SQLite format 3` ou `PGDMP`), refuse tout
membre d'archive hostile (chemin absolu, `..`, séparateur Windows, lien, périphérique)
et vérifie que la révision Alembic est connue de la chaîne du code courant. Tous les
écarts sont listés dans un seul refus (code 3). Un `product_version` différent du
code courant n'est qu'un avertissement.

### `inspect`

Résumé lisible du manifeste sans recalcul (tables et comptages, archives, clés de
secrets requises, empreinte de la source, avertissements).

### `restore`

1. `verify` implicite ; rien n'est touché si la sauvegarde est refusée.
2. Refus si le dialecte de `--into` diffère de celui de la sauvegarde.
3. Refus si `--into` est la base d'origine (même empreinte).
4. Refus si la cible contient une table ou si un répertoire cible n'est pas vide,
   **sauf** `--replace --pre-restore-backup DIR2` : la cible est d'abord sauvegardée
   (`create`) puis vérifiée (`verify`) dans `DIR2` ; rien n'est vidé si cette étape
   échoue. Ensuite : `DROP SCHEMA public CASCADE; CREATE SCHEMA public` (PostgreSQL)
   ou remplacement atomique du fichier (SQLite) ; les répertoires ne sont jamais
   supprimés mais mis à l'écart sous `<dir>.pre-restore-<horodatage>`.
5. Restauration de la base (`os.replace` du fichier SQLite après `quick_check` ;
   `pg_restore --exit-on-error --single-transaction` alimenté par l'entrée standard),
   puis extraction des archives avec double barrière (contrôle propre + filtre
   `data` de `tarfile`).
6. Contrôles post-restauration, chaque écart listé (code 3, restauration effectuée
   mais à corriger) : `alembic_version` égale au manifeste ; comptages par table
   égaux ; chaque livrable non supprimé a son blob et chaque blob a une ligne ;
   chaque `skill_revisions` a son dossier `<skills-dir>/<skill_id>/<numéro>` ;
   chaque `secrets.key_id` non révoqué est dérivable de `ACP_SECRETS_KEYS`
   (avertissement, refus avec `--require-secret-keys`).
7. Révision restaurée antérieure à la tête : message « exécutez
   `python -m acp_database.migrate upgrade` » (PostgreSQL) ou rappel que `init_db()`
   met SQLite à niveau au démarrage. **Aucune migration n'est jamais lancée par la
   restauration.**

## Outils PostgreSQL et conteneurs

| Variable | Rôle |
| --- | --- |
| `ACP_BACKUP_PG_DUMP_COMMAND` | argv JSON remplaçant `["pg_dump","--format=custom","--no-owner","--no-privileges","--dbname","{url}"]` |
| `ACP_BACKUP_PG_RESTORE_COMMAND` | argv JSON remplaçant `["pg_restore","--no-owner","--no-privileges","--exit-on-error","--single-transaction","--dbname","{url}"]` |
| `ACP_BACKUP_DATABASE_URL_FOR_TOOLS` | URL libpq substituée au jeton `{url}` à la place de l'URL SQLAlchemy (pilote `+psycopg` retiré) |

Les binaires client peuvent être absents du poste : un binaire introuvable est un
refus qui cite la commande Docker équivalente. Exemple avec le conteneur `acp-pg` :

```text
ACP_BACKUP_PG_DUMP_COMMAND='["docker","exec","acp-pg","pg_dump","--format=custom","--no-owner","--no-privileges","--dbname","{url}"]'
ACP_BACKUP_PG_RESTORE_COMMAND='["docker","exec","-i","acp-pg","pg_restore","--no-owner","--no-privileges","--exit-on-error","--single-transaction","--dbname","{url}"]'
ACP_BACKUP_DATABASE_URL_FOR_TOOLS='postgresql://acp:acp@127.0.0.1:5432/acp_h4'
```

`ACP_BACKUP_DATABASE_URL_FOR_TOOLS` désigne le serveur **tel que le conteneur le
voit** (`127.0.0.1:5432` à l'intérieur, alors que l'opérateur parle à `55432`). Une
seule valeur vaut pour toute l'exécution de la commande : une restauration avec
`--replace` sur PostgreSQL dumpe puis restaure la même base cible, ce qui est
cohérent ; pour sauvegarder A puis restaurer vers B depuis un conteneur, lancez deux
commandes avec deux valeurs. La substitution doit ne changer que le **chemin d'accès** au
serveur : si le nom de base qu'elle porte diffère de celui de l'URL sur laquelle la
commande travaille, la commande refuse avant d'appeler le moindre outil, en citant
les deux noms. Ce contrôle ne compare pas l'identité du serveur : deux serveurs
hébergeant une base de même nom passent encore (R19 ouvert). Vérifier manuellement
que les deux adresses atteignent la même base. Sans ce contrôle de nom, une variable oubliée d'une exécution précédente
faisait vider une base et restaurer dans une autre. L'URL passée en argument aux outils contient le mot de
passe et reste visible dans la liste des processus le temps de la commande ; les
messages et les journaux de la commande, eux, ne le contiennent jamais.

`restore --replace` met d'abord les répertoires à l'écart, **puis** vide la base cible,
puis restaure. Leur remise en place automatique couvre les échecs pendant le
déplacement et le vidage ; un échec ultérieur de restauration ou d'extraction les
laisse à l'écart et exige une récupération manuelle (R20 ouvert). Si la restauration
échoue après le vidage, la commande imprime l'état exact
(« base VIDÉE et non restaurée ») et le chemin de la sauvegarde préalable vérifiée.

## Ordre opérateur recommandé

1. Arrêter l'API (et les workers) : la copie SQLite est cohérente même sous
   écriture, mais **les fichiers et la base ne sont pas figés au même instant** ;
   seul un arrêt garantit qu'aucun livrable n'arrive entre les deux.
2. `create --output <dossier daté> --label <motif>` puis `verify` immédiatement ;
   déposer le dossier hors du serveur (le manifeste permet de le revérifier plus
   tard sans le restaurer).
3. Pour restaurer : cible **vide et distincte de la source** (nouvelle base,
   nouveaux répertoires), `restore … --require-secret-keys` avec le même
   `ACP_SECRETS_KEYS`, lecture du compte rendu (écarts, révision), puis bascule de
   `ACP_DATABASE_URL`, `ACP_ARTIFACT_STORAGE_DIR` et `ACP_SKILLS_STORAGE_DIR` vers la
   cible et redémarrage.
4. Si la révision restaurée est antérieure à la tête : `python -m
   acp_database.migrate upgrade` (PostgreSQL) avant de démarrer l'API.

## Preuves disponibles

- `packages/database/tests/test_snapshot.py` : copie `VACUUM INTO` sous écriture
  ouverte, remplacement atomique et retrait des fichiers `-wal`/`-shm`, argv JSON,
  substitution `{url}`, binaire introuvable, sortie standard capturée, entrée
  standard alimentée, aucun mot de passe dans les messages.
- `apps/api/tests/test_backup_restore.py` (SQLite fichier) : aller-retour avec
  empreintes de lignes par table identiques, blob manquant et dossier de skill
  manquant détectés, manifeste altéré refusé, cible non vide refusée, `--replace
  --pre-restore-backup` avec second manifeste vérifiable, clé de secret différente
  (avertissement puis refus), cinq formes de chemin hostile refusées avant toute
  écriture, révision antérieure signalée sans migration.
- `apps/api/tests/test_backup_restore_postgresql.py` (marqueur `postgres`, outils
  via `docker exec`) : aller-retour `acp_h4` → `acp_h4_restore`, `compare_metadata`
  vide, `check_schema_current.ok`, remplacement avec sauvegarde préalable.
- `scripts/verify_backup_restore.py` : API réelle, données créées par HTTP, arrêt,
  `create`/`verify`/`inspect`/`restore`, seconde restauration refusée, API relancée
  sur la cible, reconnexion par mot de passe et relectures identiques (42 étapes sur
  SQLite, 47 sur PostgreSQL 16 avec les deux remises à zéro).

## Ce qui n'est pas livré

- **Import SQLite → PostgreSQL** : une sauvegarde ne se restaure que dans son
  dialecte. Le passage d'un poste SQLite à une base hébergée reste à outiller.
- **Instantané atomique base + fichiers** : sans arrêt de l'API, un livrable peut
  être écrit entre l'instantané de base et l'archive (il apparaît alors comme blob
  sans ligne après restauration, ce qui est signalé, jamais masqué).
- **Restauration sur la source** : interdite par conception ; restaurer à côté puis
  basculer la configuration. La garde PostgreSQL compare actuellement une empreinte
  d'URL masquée, pas l'identité réelle du serveur : un autre alias ou utilisateur
  peut désigner la même base sans être reconnu (R21 ouvert). Vérifier que la cible
  est réellement distincte avant restauration.
- **Chemins de `skill_revisions.storage_path`** : les nouvelles lignes portent
  `<skill_id>/<numéro>`, relatif à la racine configurée. Les chemins hérités de
  0.8.0 (absolus ou préfixés par `acp-data/skills`) restent inchangés dans la base ;
  la lecture utilise le dossier `<ACP_SKILLS_STORAGE_DIR>/<skill_id>/<numéro>`.
  Un déplacement ou une restauration du volume ne demande donc pas de migration
  de données. Aucun repli vers un chemin extérieur n'est autorisé si ce dossier
  manque. La vérification après restauration contrôle ce dossier canonique et son
  confinement ; une ancienne adresse de stockage ne produit pas de faux avertissement.
- **Données d'exploitation** : journaux applicatifs, caches, état natif Hermes,
  fichiers de prévisualisation ou de médias hors des deux répertoires ci-dessus ne
  sont pas sauvegardés.
- **Planification, chiffrement et dépôt distant** des sauvegardes : à définir par
  l'hébergement (Railway ne fournit pas de volume partagé entre services).
- **Rendu des CHECK sur PostgreSQL** : après `pg_dump`/`pg_restore`, PostgreSQL
  réécrit `x IN ('a','b')` en `ANY (ARRAY['a'::character varying::text, …])` au lieu
  de `ANY (ARRAY[…]::text[])`. Les contraintes sont équivalentes et
  `compare_metadata` est vide, mais ne compare pas le corps des CHECK : cette
  observation ne prouve pas leur équivalence. Le catalogue doit être revu si
  une dérive de contrainte est suspectée.


### Adoption et retour arrière d'un schéma (0.9.1)

Sous PostgreSQL, `migrate stamp head` refuse une base vide ou différente du modèle :
créez le schéma avec `migrate upgrade`. L'adoption d'une base préexistante exige une
sauvegarde vérifiée et un schéma déjà conforme aux contrôles de `migrate check`.
Une estampille intermédiaire exige `--allow-unverified-revision` et une vérification
manuelle du schéma correspondant ; elle n'exécute aucune migration.

Le démarrage et `/ready` vérifient la présence de toutes les tables attendues, en
plus de l'estampille. Une révision inconnue peut venir d'une version plus récente :
le code refuse de la modifier, y compris en SQLite. `upgrade` ne réalise jamais un
retour arrière implicite. Pour revenir à une image antérieure, conserver la version
qui connaît le schéma courant, vérifier la sauvegarde, arrêter les écritures puis
exécuter avec cette version `migrate downgrade --to <révision> --yes-i-understand-data-loss`.
Vérifier ensuite `migrate check` avec le code cible avant de le redémarrer. Certaines
valeurs nouvelles rendent la descente impossible : 0003 refuse les entiers hors
32 bits et les références dépassant 500 caractères, sans tronquer les données.

La révision **0004** ajoute les délégations MCP et les preuves durables d'appels
(`mcp_execution_grants`, `mcp_execution_calls`). Son retour arrière refuse de
supprimer ces preuves lorsqu'une tentative associée est encore active. Arrêter
les services et résoudre les tentatives avant toute descente ; ne pas contourner
le refus en supprimant des lignes. Les migrations sont transactionnelles **par
révision** : si une descente de 0004 à 0002 échoue dans 0003, le passage préalable
de 0004 à 0003 peut déjà être validé. Lire `migrate current` et vérifier le schéma
effectif avant toute reprise, sans présumer un retour global à l'état initial.

La révision **0005** ajoute `subscription_quota_snapshots`, le dernier relevé des
quotas réels d'abonnement transmis par chaque worker (voir
[les quotas d'abonnement](subscription-quotas.md)). Une ligne par worker, fournisseur
et compteur ; elle disparaît avec son worker (`ON DELETE CASCADE`). Ces lignes sont un
cache recréé au passage suivant du worker : la descente de 0005 vers 0004 les supprime
sans garde-fou de données.

**Portée des contrôles :** `migrate check` compare les tables, colonnes, types,
valeurs par défaut, index, prédicats d'index partiels et noms des contraintes CHECK.
Il ne compare pas l'expression SQL des CHECK : un CHECK de même nom dont le corps a
été modifié nécessite une revue manuelle. Une sortie sans dérive ne prouve donc pas
l'équivalence complète du schéma. L'inventaire des tests conserve le groupement
booléen et la casse des littéraux, au lieu de supprimer toutes les parenthèses.
