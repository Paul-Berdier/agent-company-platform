# Images et piles Docker (Lot H5)

Ce dossier contient les deux images de services, leur configuration et deux piles
compose. Tout est construit depuis la racine du dépôt (`context: ..`) ; le contexte
est filtré par `.dockerignore` (aucun `.env*`, aucun venv, aucune base SQLite).

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `python.Dockerfile` | Image commune des services Python (`api`, `preview`, `gateway`, `event-service`, `relay`, `migrate`, `backup`). Multi-étapes, base `python:3.12-slim-bookworm` épinglée par digest, dépendances installées uniquement depuis `requirements/python-3.12.lock.txt` avec `--require-hashes`, utilisateur `acp` (uid/gid 10001). |
| `entrypoint.sh` | Sélecteur de commande (premier argument) ; toute autre valeur est exécutée telle quelle. Refuse de démarrer `api`, `preview` et `backup` si `/data` n'est pas inscriptible (code 3, sans `chown`). Passe à uvicorn, sur `api` et `preview`, la liste des proxys de confiance (`ACP_TRUSTED_PROXY_IPS`). |
| `web.Dockerfile` | Build Vite du SPA dans `node:22-bookworm-slim`, servi par `nginxinc/nginx-unprivileged:1.27-alpine` sur le port 8080. `VITE_ACP_API_URL` est obligatoire au build. |
| `web.nginx.conf` | Repli SPA vers `index.html`, `Cache-Control: no-store` sur `index.html`, `X-Content-Type-Options: nosniff`. |
| `compose.yml` | Pile complète locale (PostgreSQL 16, migration one-shot, api, aperçu, gateway, event-service, relais, web). |
| `compose.test.yml` | PostgreSQL seul sur `127.0.0.1:5433`, données en tmpfs, identifiants `acp/acp/acp_test`, pour `ACP_TEST_DATABASE_URL`. |
| `.env.compose.example` | Modèle des variables de la pile ; à copier en `.env.compose` (ignoré par git via `docker/.gitignore`). |

## Commandes de l'image Python

```text
docker run --rm acp-python:<tag> api             # uvicorn acp_api.main:app sur $PORT (défaut 8000)
docker run --rm acp-python:<tag> preview         # uvicorn acp_api.preview:app
docker run --rm acp-python:<tag> gateway         # uvicorn acp_provider_gateway.main:app
docker run --rm acp-python:<tag> event-service   # uvicorn acp_event_service.main:app
docker run --rm acp-python:<tag> relay           # python -m acp_api.outbox_relay --follow
docker run --rm acp-python:<tag> migrate         # python -m acp_database.migrate upgrade
docker run --rm acp-python:<tag> backup …        # python -m acp_api.backup …
docker run --rm acp-python:<tag> python -c "…"   # toute autre commande, telle quelle
```

Les modules `acp_database.migrate`, `acp_api.outbox_relay` et `acp_api.backup` sont
livrés par d'autres lots (H1, H3, H4). Si l'image est construite depuis un arbre qui
ne les contient pas encore, la commande échoue explicitement avec
`No module named …` : l'entrypoint ne masque rien.

Le volume de données (`ACP_DATA_DIR`, défaut `/data`) doit appartenir à l'uid 10001
ou être inscriptible par lui. Un volume nommé Docker monté sur `/data` hérite du
propriétaire fixé dans l'image ; un montage hôte (`-v ./dossier:/data`) ne l'hérite
pas et sera refusé avec un message explicite si le dossier n'est pas inscriptible.
L'entrypoint ancre `ACP_ARTIFACT_STORAGE_DIR` et `ACP_SKILLS_STORAGE_DIR` sous
`/data` quand elles ne sont pas définies, pour ne jamais écrire dans la couche
éphémère du conteneur.

## En-têtes de proxy (`ACP_TRUSTED_PROXY_IPS`)

Les commandes `api` et `preview` passent toujours `--proxy-headers` et
`--forwarded-allow-ips <valeur>` à uvicorn. La valeur vient de la seule variable
`ACP_TRUSTED_PROXY_IPS` ; vide, elle vaut `127.0.0.1,::1`.

| Valeur | Effet |
| --- | --- |
| vide (défaut) | Seule la boucle locale est crue. Derrière une terminaison TLS en amont, l'API voit le schéma `http` et l'adresse du proxy pour tout le trafic. |
| `10.0.0.0/8`, `1.2.3.4`, liste séparée par des virgules | uvicorn parcourt `X-Forwarded-For` **de droite à gauche** et retient la première adresse hors de cette liste : c'est le comportement correct. |
| `*` | uvicorn retient la **première** entrée de `X-Forwarded-For`, donc une valeur entièrement choisie par l'appelant. L'entrypoint écrit un avertissement sur stderr. |

Pourquoi c'est fixé ici plutôt que laissé au défaut : uvicorn active
`--proxy-headers` par défaut mais retombe sur la variable d'environnement ambiante
`FORWARDED_ALLOW_IPS` si `--forwarded-allow-ips` n'est pas fourni. Une variable
étrangère au produit pourrait donc élargir la confiance sans qu'aucun fichier du
dépôt ne le montre. Vérifié le 18 septembre 2026 dans le code d'uvicorn 0.51.0
installé sur le poste (`uvicorn/config.py`, `uvicorn/middleware/proxy_headers.py`) ;
le verrou de production épingle uvicorn 0.53.0, dont la documentation officielle
décrit les mêmes défauts (« Defaults to `$FORWARDED_ALLOW_IPS` if set. Otherwise,
`127.0.0.1` and `::1` are trusted », `docs/settings.md` du dépôt `encode/uvicorn`,
lecture du 18 septembre 2026).

Ce que cela change réellement dans ce produit, vérifié dans le code :
`RequestIngressGuardMiddleware` (`apps/api/src/acp_api/webhook_ingress.py:101-103`)
compte les déclenchements webhook par `scope["client"][0]`, et
`_require_preview_request_origin` (`apps/api/src/acp_api/routers/artifacts.py:1678`)
reconstruit l'origine à partir de `request.url.scheme`. Les deux sont réécrits par la
couche proxy d'uvicorn — et par elle seule.

## Pile complète

```text
cp docker/.env.compose.example docker/.env.compose      # renseigner secrets et mot de passe
docker compose -f docker/compose.yml --env-file docker/.env.compose up --build
```

- `--env-file` est obligatoire : il alimente les interpolations `${…}` ; les
  variables marquées `:?` font échouer la commande avec un message en français.
- `ACP_VERSION` (étiquette OCI et tag des images) est copiée à la main depuis le
  fichier `VERSION` : compose ne sait pas lire un fichier. Sans valeur, les images
  portent `0.0.0-unversioned`, ce qui est volontairement visible.
- `migrate` s'exécute une fois (`restart: "no"`) après `pg_isready` ; `api`,
  `artifact-preview` et `relay` attendent sa réussite (`service_completed_successfully`).
- `api` et `artifact-preview` partagent le volume `acp-data`. **C'est possible avec
  compose, pas sur Railway** (un volume par service, non partageable) : voir
  `deploy/railway/README.md`.
- Les ports ne sont publiés que sur `127.0.0.1`.
- Les sondes `healthcheck` interrogent `/ready` (api, aperçu — livré par le Lot H2a)
  ou `/health` (gateway, event-service) avec l'interpréteur Python de l'image, car
  l'image slim n'embarque pas `curl`.

## Base de test PostgreSQL

```text
docker compose -f docker/compose.test.yml up -d --wait
set ACP_TEST_DATABASE_URL=postgresql+psycopg://acp:acp@127.0.0.1:5433/acp_test
set ACP_TEST_DATABASE_REQUIRED=1
python -m pytest -q
docker compose -f docker/compose.test.yml down
```

## Limites connues

- La confiance accordée aux en-têtes `X-Forwarded-*` reste une décision
  d'exploitation : sans `ACP_TRUSTED_PROXY_IPS`, seule la boucle locale est crue et le
  schéma vu par l'API derrière un proxy est `http` (voir la section ci-dessus). Aucune
  valeur par défaut ne peut être juste, car l'adresse du proxy dépend de
  l'hébergement ; Railway ne publie aucune plage d'adresses de son proxy dans la
  documentation lue le 18 septembre 2026.
- Ce comportement n'a été exercé par **aucun test et aucune exécution** : la
  construction de l'image et le lancement des conteneurs n'ont pas eu lieu dans ce
  lot. Seules la syntaxe du script (`sh -n docker/entrypoint.sh`) et la fonction
  `trusted_proxy_ips` extraite du fichier ont été exécutées.
- L'image web fige `VITE_ACP_API_URL` : une image par environnement.
- nginx écoute sur 8080 fixe et ne lit pas `PORT`.
- Aucune image n'a été publiée dans un registre. Tailles mesurées le 17 septembre
  2026 sur le poste de développement (`docker image ls`) : `acp-python` 389 Mo,
  `acp-web` 77,4 Mo.
- `/ready` n'existe que si le Lot H2a est présent dans l'arbre construit ; sinon
  l'API répond 404 sur ce chemin et la sonde compose reste « unhealthy » (constaté
  sur l'image construite depuis ce lot seul : `/health` 200, `/ready` 404).
