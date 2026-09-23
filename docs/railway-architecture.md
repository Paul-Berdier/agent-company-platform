# Exposition Railway pour un client desktop distant

Date d'état : 18 septembre 2026, Europe/Paris.
Branche : `feat/desktop-qt-railway`. Version du produit : `0.9.0`.
Source de vérité en amont : `docs/desktop-railway-audit.md`, section 5.2.

## Ce que ce document engage

Il traite un seul sujet : ce qu'il faut pour qu'un client **installé sur un poste
distant** puisse parler à ce backend hébergé, et ce qu'il ne faut surtout pas
relâcher pour y arriver. Chaque affirmation sur le produit a été vérifiée en lisant
le code de cette branche ; chaque affirmation sur l'hébergeur cite la page lue et sa
date de lecture.

## Ce que ce document n'engage pas

**Aucun déploiement n'a eu lieu.** Aucun projet n'a été créé, aucun domaine n'a été
généré, aucune image n'a été construite ailleurs que sur un poste de développement,
aucun conteneur n'a été lancé dans ce lot. Les fichiers de `deploy/railway/` et de
`docker/` sont une configuration relue, pas une installation observée. Aucun code
natif n'a été compilé : ce lot n'en contient pas.

---

## 1. Exposition publique minimale

### 1.1 Règle

**Un seul service porte un domaine public : `api`.** Un second, `web`, n'en porte un
que si l'interface navigateur est réellement servie. Tout le reste vit sur le réseau
privé de l'hébergeur et n'est joignable que par les services du projet.

| Service | Exposition | Pourquoi |
| --- | --- | --- |
| `api` | **public** | Seul point d'entrée des clients : HTTPS pour la surface REST, SSE pour le journal. Le desktop, le CLI et le web ne parlent qu'à lui. |
| `web` | public **si déployé** | Interface navigateur. Inutile si seul le client desktop est servi. Lire d'abord la section 3.3 : deux domaines générés par l'hébergeur ne suffisent pas à la faire fonctionner. |
| `artifact-preview` | **privé** — et de préférence non déployé | Sans volume partagé, il ne lit aucun livrable (section 4). Un domaine public ne publierait qu'une surface d'attaque connectée à la base, incapable de servir un octet. |
| `provider-gateway` | **privé** | Joignable par l'API seule, avec un jeton de service. Il détient les identifiants Hermes et ComfyUI. |
| `event-service` | **privé** | Relais interne. Le flux temps réel de l'utilisateur est servi par l'API (`GET /streams/**`), jamais par lui. |
| `relay` | **privé** | Aucun serveur HTTP : `docker/entrypoint.sh relay` lance `python -m acp_api.outbox_relay --follow`. Un domaine n'aurait rien à servir. |
| base PostgreSQL | **privé** | Ressource managée de l'hébergeur, jamais exposée. |

Relecture : `python scripts/check_railway_config.py --exposure` imprime ce tableau
depuis le code du vérificateur. **Cette commande ne prouve rien** : un domaine se
génère au tableau de bord et n'est déclarable dans aucun fichier du dépôt. C'est une
liste de contrôle à comparer à la main avec l'interface de l'hébergeur.

### 1.2 Ce que la configuration livrée contenait, et ce qui a été corrigé

Les six manifestes `deploy/railway/<service>/railway.json` ne déclaraient — et ne
peuvent déclarer — aucun domaine. La consigne d'installation, elle, était fausse :
`deploy/railway/README.md` demandait d'« ajouter les domaines publics (`api`,
`artifact-preview`, `web`) ». Cette étape a été corrigée : `artifact-preview` ne
reçoit aucun domaine.

Deux clés ont été ajoutées aux six manifestes ou au vérificateur :

- `"sleepApplication": false` sur les six services. La clé ne crée rien ; elle
  empêche qu'un réglage du tableau de bord endorme un service, puisque
  « Configuration defined in code will always override values from the dashboard »
  (`docs.railway.com/reference/config-as-code`, cité dans
  `deploy/railway/README.md`). Un service endormi couperait les flux SSE d'un poste
  distant et suspendrait la livraison de la boîte d'envoi. La page d'app sleeping
  précise qu'« Once a service stops sending packets it is considered inactive after
  5 minutes » et que « Serverless is applied to a container when that container is
  created » (`docs.railway.com/reference/app-sleeping`, lu le 18 septembre 2026).
- `deploy.cronSchedule` est désormais **refusé** par `scripts/check_railway_config.py`
  sur ces six services. La clé était admise et inutilisée ; posée par erreur sur un
  service de longue durée, elle le transformerait en tâche planifiée sans qu'aucune
  erreur ne soit levée. Une rétention ou une sauvegarde planifiée demande un service
  dédié, qui n'existe pas dans ce lot.

### 1.3 Le réseau privé

Les services d'un même projet se joignent par un nom interne : « Reference other
services using their internal DNS name: `SERVICE_NAME.railway.internal` », et « No
port exposure or configuration required »
(`docs.railway.com/guides/private-networking`, lu le 18 septembre 2026). Un service
sans domaine public reste donc parfaitement joignable par ses pairs ; retirer le
domaine ne casse rien.

Ce qui doit rester sur ce réseau, et pourquoi c'est vérifiable dans le code :

- `ACP_EVENT_SERVICE_URL` et `ACP_PROVIDER_GATEWAY_URL` doivent viser
  `<service>.railway.internal`. Les deux services refusent toute requête sans leur
  jeton de service, et répondent **503** si le jeton n'est pas configuré du tout —
  `services/provider-gateway/src/acp_provider_gateway/main.py:67-72` et
  `apps/event-service/src/acp_event_service/main.py:91-96`. Seule `/health` reste
  publique sur le gateway. C'est une défense en profondeur, pas une autorisation à
  les exposer.
- `ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET` doit rester à `0`. Son nom dit ce
  qu'elle fait.
- Le desktop ne doit **jamais** joindre `event-service` ni `provider-gateway`, même
  s'ils étaient accessibles : l'audit le pose comme règle d'architecture
  (`docs/desktop-railway-audit.md`, section 2.2).

---

## 2. Origine de l'API et en-têtes de proxy

### 2.1 Le problème réel

Derrière une terminaison TLS en amont, le conteneur reçoit du HTTP en clair et voit
l'adresse du proxy. uvicorn active `--proxy-headers` par défaut mais ne fait
confiance qu'à `127.0.0.1` et `::1` tant que `--forwarded-allow-ips` n'est pas
fourni, et retombe sinon sur la variable d'environnement ambiante
`FORWARDED_ALLOW_IPS` (« Defaults to `$FORWARDED_ALLOW_IPS` if set. Otherwise,
`127.0.0.1` and `::1` are trusted », `docs/settings.md` du dépôt `encode/uvicorn`,
lu le 18 septembre 2026 ; comportement relu dans le code d'uvicorn 0.51.0 installé
sur le poste, `uvicorn/config.py` et `uvicorn/middleware/proxy_headers.py`. Le
verrou de production épingle uvicorn 0.53.0, non installé ici).

Aucun manifeste ne passait ces options. Deux effets **mesurables dans ce code** :

1. `RequestIngressGuardMiddleware` compte les déclenchements webhook par
   `scope["client"][0]` (`apps/api/src/acp_api/webhook_ingress.py:101-103`). Sans
   confiance accordée au proxy, tout le trafic public partage un seul seau : un
   appelant bruyant provoque des 429 pour tous les autres.
2. `_require_preview_request_origin` reconstruit l'origine de la requête à partir de
   `request.url.scheme` (`apps/api/src/acp_api/routers/artifacts.py:1678-1690`). Vu
   en `http`, l'origine ne peut pas correspondre à une origine d'aperçu HTTPS et le
   lien est refusé.

### 2.2 Ce que ce lot fait

`docker/entrypoint.sh` passe désormais, sur les commandes `api` et `preview`,
`--proxy-headers --forwarded-allow-ips "$(trusted_proxy_ips)"`. La valeur vient
d'une seule variable du produit, `ACP_TRUSTED_PROXY_IPS` :

- vide (défaut) : `127.0.0.1,::1`. Défaut fermé, et surtout **indépendant** de la
  variable ambiante `FORWARDED_ALLOW_IPS`, qu'une configuration étrangère au produit
  pourrait sinon élargir sans qu'aucun fichier du dépôt ne le montre ;
- une adresse ou un réseau : uvicorn parcourt `X-Forwarded-For` de droite à gauche et
  retient la première adresse hors de la liste. C'est le comportement correct ;
- `*` : uvicorn retient la **première** entrée de `X-Forwarded-For`, c'est-à-dire une
  valeur entièrement choisie par l'appelant. L'entrypoint écrit un avertissement sur
  stderr, et `scripts/check_railway_config.py` refuse qu'une commande de démarrage
  versionnée fige cette valeur : la décision appartient à l'exploitation, pas au
  dépôt.

**Quelle valeur mettre ?** La documentation de l'hébergeur lue le 18 septembre 2026
ne publie aucune plage d'adresses pour son proxy. Il n'existe donc pas de valeur
juste connue d'avance, et ce lot n'en invente pas. Deux conduites honnêtes :
laisser le défaut fermé et accepter les deux effets de la section 2.1, ou relever
l'adresse observée au premier déploiement (journal d'accès de l'API, champ client)
et la renseigner. `*` ne doit être choisi qu'en connaissance de cause, et seulement
si le port du conteneur n'est atteignable que par ce proxy — ce qui n'a pas été
vérifié.

### 2.3 Ce qui relève du code de l'API, pour un autre lot

Hors du périmètre de ce lot, listé pour être traité ailleurs :

1. **Origine de l'API configurable côté web.** `docker/web.Dockerfile` refuse de
   construire sans `VITE_ACP_API_URL` et fige la valeur dans le bundle : une image
   par environnement. Rendre l'origine configurable à l'exécution suppose que
   `apps/web` lise un fichier de configuration servi à côté de l'application ; c'est
   une modification de `apps/web`, pas de l'image. Le client desktop, lui, n'a pas ce
   problème : son origine est saisie par l'utilisateur (voir `docs/desktop-security.md`).
2. **Validation de `ACP_CORS_ORIGINS` sur l'API.** `apps/api/src/acp_api/main.py:70-78`
   fait un `split(",")` brut, sans nettoyage ni contrôle. L'aperçu, lui, valide
   strictement (`apps/api/src/acp_api/preview.py:28-56`). La même validation doit
   être portée sur l'API — voir section 3.
3. **Limitation de débit sur `POST /auth/login`.** Le seul limiteur existant ne
   couvre que les déclenchements webhook (`webhook_ingress.py:201`). Publier l'API
   rend cette absence exploitable.
4. **`/docs`, `/redoc` et `/openapi.json` publics.** `main.py:59-63` ne les coupe
   pas, alors que `preview.py:80-82` les coupe explicitement. Dès la génération d'un
   domaine, toute la surface — y compris les chemins worker — est publiée sans
   authentification. C'est un choix à trancher, pas un oubli à reconduire.
5. **Point d'entrée de compatibilité.** Aucun `/meta`, `/version` ni `/capabilities`
   n'existe. Un client installé sur un poste ne peut pas refuser proprement une
   version de serveur incompatible. C'est le premier changement bloquant listé par
   l'audit (section 9.1).

---

## 3. CORS et origines

### 3.1 Ce qu'un client natif change

**Rien à assouplir, et rien à ajouter.** Un client Qt n'est pas un navigateur : il
n'envoie pas d'en-tête `Origin`, et le middleware CORS de Starlette se retire dès
cette constatation — `if origin is None: await self.app(...)`
(`starlette/middleware/cors.py`, relu dans la version installée sur le poste, 1.3.1 ;
le verrou de production épingle 1.6.0, non installé ici). Il n'y a donc **ni
préflight `OPTIONS`, ni négociation d'origine** pour le desktop.

Ce que le client natif doit néanmoins respecter, parce que ce sont des contrôles
serveur et non des contrôles de navigateur :

- le cookie `acp_session` doit être porté par ses requêtes courtes **et** par ses
  flux SSE, depuis le même pot de cookies (`routers/streams.py:86` et `:112` ne
  lisent que ce cookie) ;
- l'en-tête `X-CSRF-Token` reste obligatoire sur `POST`, `PUT`, `PATCH` et `DELETE`
  (`deps.py:48-68`), même sans navigateur. Le CLI le fait déjà
  (`apps/cli/src/acp_cli/client.py:83-104`).

### 3.2 Ce qu'il ne faut surtout pas relâcher

`ACP_CORS_ORIGINS=*` est le piège. L'API passe la liste telle quelle à Starlette avec
`allow_credentials=True` (`main.py:70-78`). Dans ce cas, Starlette ne renvoie pas
`*` : il **renvoie l'origine de l'appelant** et ajoute
`Access-Control-Allow-Credentials: true` (« If credentials are allowed, then we must
respond with the specific origin instead of `*` », `CORSMiddleware.send`). Autrement
dit, toute page web du monde se verrait autorisée à lire les réponses de l'API.

Le cookie de session, posé en `SameSite=strict` (`security.py:137-146`), limite les
dégâts : un navigateur ne l'enverrait pas depuis un autre site. Mais la protection
tient alors à un seul attribut de cookie, et non à la configuration. **Le desktop
n'a besoin d'aucune origine CORS : ce n'est donc jamais lui qui justifie un
élargissement.**

Deux règles :

1. `ACP_CORS_ORIGINS` ne contient que des origines exactes, en HTTPS, sans chemin ni
   joker. Le service d'aperçu applique déjà exactement cette règle et refuse le
   joker (`preview.py:41-56`) ; l'API doit la recevoir (section 2.3, point 2).
2. Ne jamais élargir pour « débloquer » le desktop. Un 401, un 403 ou un flux SSE qui
   ne s'ouvre pas ne se règlent pas par CORS : ils viennent du cookie, du jeton CSRF
   ou du RBAC.

### 3.3 Le piège décisif : deux domaines générés ne sont pas le même site

`up.railway.app` figure dans la **Public Suffix List** (ligne 15421 de
`public_suffix_list.dat`, téléchargé le 18 septembre 2026 depuis
`raw.githubusercontent.com/publicsuffix/list/main/public_suffix_list.dat`, sous le
commentaire « Railway Corporation »).

Conséquence, et elle est lourde : `api-xxxx.up.railway.app` et
`web-yyyy.up.railway.app` sont **deux sites différents** pour un navigateur. Le
cookie `acp_session`, posé en `SameSite=strict`, ne sera donc **pas envoyé** par
l'interface web vers l'API, alors même que `apps/web/src/workspace-api.ts:481`
demande `credentials: "include"`. Aucune configuration CORS ne corrige cela : le
navigateur retire le cookie avant même la question de l'origine.

Il en découle, pour une coexistence web + desktop :

- l'interface web exige que l'API et le web soient **sur le même site** — par exemple
  `api.exemple.fr` et `app.exemple.fr`, deux domaines personnalisés sous un même
  domaine enregistrable. Deux domaines générés par l'hébergeur ne conviennent pas ;
- le client desktop n'est pas concerné : il gère son propre pot de cookies, sans
  règle `SameSite` de navigateur, exactement comme le CLI le fait déjà en
  production ;
- si aucun domaine personnalisé n'est disponible, la conclusion honnête est de ne
  pas déployer l'interface web et de servir uniquement le desktop et le CLI.

**Non prouvé** : ce raisonnement découle de la Public Suffix List et du code du
produit. Il n'a été vérifié dans aucun navigateur réel, aucun déploiement n'ayant eu
lieu. C'est la première chose à confirmer au premier déploiement d'une interface web.

### 3.4 Configuration correcte, par profil

**Profil « desktop seul »** — recommandé pour la première mise en ligne :

- domaine public sur `api` uniquement ;
- `ACP_CORS_ORIGINS` : aucune origine navigateur n'est nécessaire. Ne pas laisser la
  variable **absente**, car le défaut du code est `http://localhost:5173,http://127.0.0.1:5173`
  (`main.py:71-73`), c'est-à-dire une origine de développement en production. La
  renseigner avec l'origine web réelle, ou, si l'interface web n'est pas déployée, la
  supprimer du service seulement après avoir vérifié qu'aucun appel d'aperçu n'en
  dépend (section 4 : sans `ACP_ARTIFACT_PUBLIC_ORIGIN`, l'aperçu est refusé avant de
  lire `ACP_CORS_ORIGINS`) ;
- `ACP_SESSION_COOKIE_SECURE=1`. Le défaut du code est `0` (`security.py:71`), ce qui
  est faux dès qu'il y a du HTTPS.

**Profil « web + desktop »** :

- domaines personnalisés **du même site** pour `api` et `web` (section 3.3) ;
- `ACP_CORS_ORIGINS` = l'origine exacte du web, une seule entrée, en HTTPS ;
- `VITE_ACP_API_URL` = l'origine exacte de l'API, figée au build de l'image web ;
- `ACP_SESSION_COOKIE_SECURE=1`.

---

## 4. Stockage persistant des livrables

### 4.1 Les faits

- « Each service can only have a single volume » et « Replicas cannot be used with
  volumes » (`docs.railway.com/reference/volumes`, cité dans
  `deploy/railway/README.md`, lecture du 17 septembre 2026). La documentation lue ne
  dit nulle part qu'un volume peut être partagé entre deux services.
- L'API écrit les livrables et les skills sous `/data` : `docker/entrypoint.sh`
  ancre `ACP_ARTIFACT_STORAGE_DIR` et `ACP_SKILLS_STORAGE_DIR` sous `ACP_DATA_DIR`.
- `artifact-preview` est un service distinct. Sur l'hébergeur, il aurait au mieux son
  propre volume vide : **il ne peut pas lire celui de l'API**.
- L'image tourne en uid 10001 et l'entrypoint refuse de démarrer avec le **code 3**
  si `/data` n'est pas inscriptible, sans tenter de changer le propriétaire
  (`docker/entrypoint.sh:19-33`). La seule réponse documentée par l'hébergeur est
  `RAILWAY_RUN_UID=0`, c'est-à-dire exécuter le conteneur en root. Le comportement
  réel n'a **pas** été testé.

### 4.2 Les options réelles

**Option A — volume unique sur `api`, aperçu servi par l'API.** Un seul volume, monté
sur `api` ; `artifact-preview` n'est pas déployé ; le contenu d'aperçu serait servi
par l'API elle-même. Ce que cela coûte : le service d'aperçu existe précisément pour
qu'aucun contenu produit par un agent ne soit rendu dans l'origine de la plateforme.
Le code défend cette séparation activement — `_require_preview_request_origin`
refuse un jeton d'aperçu présenté à l'API de contrôle
(`routers/artifacts.py:1678-1690`), et `_configured_preview_origin` refuse une
origine d'aperçu égale à celle de l'API ou à une origine navigateur autorisée
(`:1745-1761`). Servir l'aperçu depuis l'API **annulerait** cette protection et
exigerait de modifier `apps/api`. Ce lot ne le fait pas et ne le recommande pas.

**Option B — stockage objet.** Un magasin externe, adressé par contenu, lisible par
les deux services. C'est la seule option qui rétablit l'aperçu sans affaiblir la
séparation d'origines. Ce que cela coûte : un **adaptateur de stockage qui n'existe
pas** dans le dépôt (l'audit le liste au point 19 de sa section 9.4), un fournisseur
à budgéter, et une migration des livrables déjà écrits. Tant que cet adaptateur n'est
pas livré, promettre l'aperçu serait un faux succès.

**Option C — renoncement documenté à l'aperçu sur cet hébergement.** Un seul volume,
sur `api` ; `artifact-preview` n'est pas déployé ; `ACP_ARTIFACT_PUBLIC_ORIGIN` reste
absente. Le téléchargement authentifié par session reste entier, y compris la reprise
par `Range` (206) et les liens signés de téléchargement, qui ne dépendent que de
`ACP_API_URL` (`_configured_download_origin`, `routers/artifacts.py:1764-1777`).

### 4.3 Recommandation

**Option C pour la première mise en ligne.** Raisons vérifiables :

- elle suffit au client natif : le desktop télécharge, vérifie l'empreinte, puis
  ouvre le fichier avec l'application du système. Il n'a aucun besoin d'un aperçu
  servi par une origine web, et l'audit l'écrit explicitement (section 5.2, point 4) ;
- elle échoue proprement : sans `ACP_ARTIFACT_PUBLIC_ORIGIN`,
  `POST /artifacts/{id}/link?purpose=preview` répond **424** avec « Aperçu désactivé :
  ACP_ARTIFACT_PUBLIC_ORIGIN doit désigner une origine HTTPS distincte de l'API. »
  (`routers/artifacts.py:1697-1706`). Rien ne fait semblant de fonctionner ;
- elle ne dégrade aucune sécurité et ne demande aucune modification de `apps/api`.

Ce qu'elle coûte, sans détour : **l'aperçu en ligne n'existe pas sur cet
hébergement.** L'interface web affichera le refus 424 ci-dessus sur le bouton
d'aperçu. Le desktop ne doit pas proposer ce bouton tant que la capacité n'est pas
annoncée par le serveur — et comme aucun point d'entrée de capacités n'existe encore
(section 2.3, point 5), il doit le présenter comme « Indisponible pour l'instant »
plutôt que le masquer.

Si l'aperçu devient une exigence, la seule voie propre est l'option B, avec son
adaptateur à écrire.

### 4.4 Ce qui reste non prouvé sur le stockage

- L'inscriptibilité du volume par l'uid 10001 n'a **pas** été testée. L'échec serait
  net (code 3, message français) mais surviendrait au premier déploiement.
- Le volume oblige `numReplicas: 1` sur `api`, ce qui impose une brève interruption à
  chaque redéploiement. Pour le desktop, **la reconnexion par curseur est un chemin
  nominal, pas un cas d'erreur**.
- `numReplicas: 1` est aussi ce qui fait tenir la borne de quatre flux SSE simultanés
  par utilisateur, qui vit dans un dictionnaire local au processus
  (`apps/api/src/acp_api/streams.py:204-236`). Monter en répliques casserait cette
  borne sans qu'aucune erreur ne le signale.

---

## 5. Ce que ce lot ne résout pas

1. Aucun domaine n'est décidé : `ACP_API_URL`, `ACP_ARTIFACT_PUBLIC_ORIGIN`,
   `ACP_CORS_ORIGINS`, `VITE_ACP_API_URL` et l'URL par défaut du desktop restent
   indéterminés tant qu'aucun projet n'existe.
2. La valeur de `ACP_TRUSTED_PROXY_IPS` n'est pas connue : l'hébergeur ne publie pas
   l'adresse de son proxy dans la documentation lue.
3. `pg_dump` et `pg_restore` restent absents de l'image (aucun `apt-get` dans
   `docker/python.Dockerfile`) : la sauvegarde refusera proprement sur PostgreSQL,
   sauf à fournir les variables de substitution prévues.
4. Aucune rétention ni sauvegarde n'est planifiée ; le vérificateur interdit désormais
   d'y arriver par erreur en posant `cronSchedule` sur un service de longue durée.
5. `.railway/railway.ts` n'est toujours pas livré, alors que Config as Code est
   déprécié avec une échéance citée dans `deploy/railway/README.md`. Passé cette
   date, des services démarreraient sans migration et sans sonde, en silence. C'est
   le risque de faux succès le plus grave de ce chantier et il reste entier.
6. `docs/deployment-railway.md` est périmé (daté du 14 septembre 2026, version
   `0.8.0`) et hors du périmètre de ce lot. Il ne doit pas servir de référence.

## 6. Sources

| Source | Lue le | Ce qui en est tiré |
| --- | --- | --- |
| `docs.railway.com/guides/private-networking` | 18/09/2026 | `SERVICE_NAME.railway.internal`, « No port exposure or configuration required » |
| `docs.railway.com/guides/public-networking` | 18/09/2026 | Un domaine public se génère à la main (« Click **Generate Domain** ») |
| `docs.railway.com/reference/app-sleeping` | 18/09/2026 | Inactivité après 5 minutes sans trafic sortant ; « Serverless is applied to a container when that container is created » |
| `backboard.railway.app/railway.schema.json` | 18/09/2026 | `sleepApplication` (booléen) et `cronSchedule` (chaîne) sont bien des clés du schéma |
| `docs/settings.md` du dépôt `encode/uvicorn` | 18/09/2026 | Défauts de `--proxy-headers` et `--forwarded-allow-ips` |
| `public_suffix_list.dat` (publicsuffix/list) | 18/09/2026 | `up.railway.app` est un suffixe public (ligne 15421) |
| `deploy/railway/README.md` | — | Citations de la documentation de l'hébergeur relevées le 17/09/2026 par le lot précédent |
| Code de cette branche | 18/09/2026 | Toutes les références de fichier et de ligne ci-dessus |
