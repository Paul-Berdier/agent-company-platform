# Tests sur PostgreSQL

La suite Python tourne par défaut sur SQLite. Avec `ACP_TEST_DATABASE_URL`, elle tourne
**entièrement** sur PostgreSQL : chaque test reçoit un schéma éphémère `t_<hex12>`,
détruit à la fin, et les tests marqués `postgres` s'exécutent au lieu d'être ignorés.
Production et intégration continue utilisent PostgreSQL : un comportement qui ne passe
que sous SQLite n'est pas prouvé.

## Variables

| Variable | Rôle |
|---|---|
| `ACP_TEST_DATABASE_URL` | URL `postgresql+psycopg://` de la base de test. Absente : SQLite. |
| `ACP_TEST_DATABASE_REQUIRED=1` | Un test PostgreSQL dont la base est injoignable **échoue** au lieu d'être ignoré. Posée en CI. |
| `ACP_TEST_PG_TOOLS` | `native` ou `docker` : d'où viennent `pg_dump`/`pg_restore` pour les tests de sauvegarde. Absente : natifs s'ils sont sur le `PATH`, sinon Docker. |
| `ACP_TEST_DOCKER_CONTAINER` | Conteneur des outils en mode Docker (défaut `acp-pg`). |

## La base de test est protégée

Les tests Alembic, de disponibilité et de sauvegarde vident le schéma `public`
(`reset_public_schema`). Depuis 0.9.1, ils **refusent**, sans rien effacer :

- une base identique à `ACP_DATABASE_URL` ou `DATABASE_URL` telles qu'elles valaient au
  lancement de la suite ;
- une base dont `public` contient déjà des tables, vues ou séquences et qui ne porte pas
  le commentaire témoin `acp-test-database`.

Une base vide est marquée à sa première remise à zéro : une base de CI neuve ou une base
créée pour les tests ne demande aucune étape manuelle. Une base déjà peuplée, et
réellement jetable, se marque à la main :

```sql
COMMENT ON DATABASE acp IS 'acp-test-database';
```

Le marqueur est un commentaire de base et non un schéma : `pg_dump` sans `--create` ne
l'exporte pas, et une sauvegarde de la base de test ne le transporte donc pas ailleurs.

Les parcours de vérification (`scripts/verify_*.py --database-url …`) ont leur propre
garde : ils refusent toute base dont `public` n'est pas vide, et la vident à la fin.

## Lancer les tests sur un poste

Avec les binaires PostgreSQL 16 installés (paquet de la distribution, installeur, ou
archive de binaires officielle), sur le port 55432 :

```sh
initdb -D ~/.acp-tools/pgdata16 -U acp --auth=scram-sha-256 --pwprompt
pg_ctl -D ~/.acp-tools/pgdata16 -o "-p 55432 -c listen_addresses=127.0.0.1" -l ~/.acp-tools/pg16.log start
createdb -h 127.0.0.1 -p 55432 -U acp acp
export ACP_TEST_DATABASE_URL=postgresql+psycopg://acp:acp@127.0.0.1:55432/acp
export ACP_TEST_DATABASE_REQUIRED=1
python -m pytest -q
```

Avec Docker à la place :

```sh
docker run -d --name acp-pg -e POSTGRES_USER=acp -e POSTGRES_PASSWORD=acp -e POSTGRES_DB=acp -p 55432:5432 postgres:16-alpine
export ACP_TEST_PG_TOOLS=docker
```

`pg_dump` refuse un serveur d'une version majeure plus récente que lui : les outils
clients doivent être en version 16.

## Parcours de vérification

Chaque parcours veut une base **vide** et dédiée :

```sh
createdb -h 127.0.0.1 -p 55432 -U acp acp_journey_events
python scripts/verify_events_journey.py --database-url postgresql+psycopg://acp:acp@127.0.0.1:55432/acp_journey_events
```

De même pour `verify_automation_journey.py` et, avec deux bases,
`verify_backup_restore.py --database-url … --restore-database-url …`.

## Intégration continue

Le job **Python 3.12 — PostgreSQL 16** de `.github/workflows/ci.yml` lance un service
`postgres:16-alpine`, installe les outils clients de la même version majeure, exécute la
suite complète avec `ACP_TEST_DATABASE_REQUIRED=1`, puis les parcours d'événements,
d'automatisation et de sauvegarde-restauration, chacun sur sa base.
