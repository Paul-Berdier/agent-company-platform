# Médias, aperçu 3D et ComfyUI

Date d'état : 14 septembre 2026 — Lot G `0.8.0` en préparation

Le Lot G ajoute deux surfaces séparées : l'aperçu de modèles 3D déjà stockés comme
livrables, et un connecteur d'image ComfyUI dans le provider-gateway. Elles ne se
raccordent pas implicitement : ComfyUI retourne aujourd'hui une pièce jointe HTTP et
ne crée ni mission, ni événement, ni artefact.

## Aperçu GLB

Seul un fichier portant à la fois l'extension `.glb` et le type
`model/gltf-binary` peut devenir affichable. Lors du téléversement, l'API valide le
conteneur GLB 2, le chunk JSON UTF-8, l'ordre et la taille des chunks, puis scelle le
contenu exact avec son sha256 dans une métadonnée réservée. Les anciennes lignes non
scellées restent téléchargeables jusqu'à un nouveau téléversement validé. Le stockage
adressé par contenu vérifie l'empreinte lors de l'écriture atomique ; il ne re-hache pas
les 200 Mio potentiels avant chaque requête `Range`. Le répertoire privé et son
intégrité après ingestion restent donc une responsabilité opérationnelle explicite.

Le validateur refuse notamment :

- une signature, une version, une longueur ou un alignement incohérent ;
- plus d'un chunk JSON ou BIN, un chunk inconnu et un JSON supérieur à 4 Mio ;
- une URI externe ; seules certaines `data:` binaires en base64, déjà comprises dans
  la taille globale admise, sont acceptées ;
- les extensions nécessitant un décodeur externe
  `KHR_draco_mesh_compression`, `EXT_meshopt_compression` et `KHR_texture_basisu` ;
- un BIN qui ne correspond pas exactement à `buffers[0]`, une vue hors buffer, un
  offset absolu désaligné, un stride invalide ou tout accessor sparse ;
- une image qui ne choisit pas exactement `uri` ou `bufferView`, dont le MIME et le
  conteneur PNG/JPEG/WebP divergent, ou dont les en-têtes/dimensions sont invalides.

Avant aperçu, la somme des `bufferViews`, celle des spans physiques stridés et celle des
données d'accessors décodées sont chacune bornées à 128 Mio au maximum ; le budget
décodé est en plus limité à 8× la taille du GLB, avec plancher 1 Mio. Les images sont
bornées à 32 Mio compressés, 8 192 pixels par dimension, 32 mégapixels cumulés et
128 Mio RGBA incluant les mipmaps. Les parseurs lisent uniquement les en-têtes et ne
décompressent jamais une image côté API.

Le web charge `@google/model-viewer` `4.3.1` seulement à l'ouverture du premier modèle.
Il fournit les contrôles caméra, un état de chargement et un état d'erreur accessibles,
sans mode AR, lecture automatique ni autorotation. Un `.gltf` multi-fichiers reste en
téléchargement explicite avec avertissement.

## Origine d'aperçu obligatoire

La route `POST /artifacts/{id}/link?purpose=preview` exige à la fois
`ACP_ARTIFACT_PUBLIC_ORIGIN` et une `ACP_API_URL` explicite. Ces valeurs doivent être
des origines HTTP(S) canoniques, HTTPS hors loopback, et l'origine d'aperçu doit être
différente à la fois de l'API et de chaque origine déclarée dans `ACP_CORS_ORIGINS`.
L'URL est aussi revérifiée côté navigateur.

Si la variable est absente, invalide ou non séparée, l'API répond `424` **avant** de
créer le jeton signé. Il n'existe plus de repli d'aperçu sur l'origine de l'API. Le
téléchargement par session ou par lien `purpose=download` reste disponible.

Le `purpose` et un nonce aléatoire font partie du jeton HMAC v2. Une session et un
jeton `download` forcent toujours `Content-Disposition: attachment`. Un jeton
`preview` n'autorise `inline` que lorsque la requête arrive réellement sur l'origine
configurée ; son rejeu sur l'API de contrôle est refusé. Un reverse proxy doit donc
conserver le schéma et l'hôte publics jusqu'à l'application.

L'application expurge le paramètre `token` du journal `uvicorn.access`, y compris si
le nom du paramètre est encodé. Cette protection ne couvre pas les journaux produits
avant Uvicorn : le reverse proxy, le load balancer et l'hébergeur doivent eux aussi
supprimer ou masquer la query string `token` sur `/artifacts/*/content`. Ces journaux
ne doivent jamais être considérés comme un emplacement acceptable pour un bearer.

Cette séparation d'URL ne déploie pas à elle seule un serveur de contenu : l'opérateur
doit réellement router cette origine vers la route de contenu et appliquer HTTPS et les
en-têtes attendus avant toute exposition réseau.

## Connecteur ComfyUI

Toutes les routes, sauf `/health`, restent derrière `ACP_GATEWAY_SERVICE_TOKEN` :

- `GET /v1/providers/comfyui/diagnostic` vérifie la configuration, le workflow local et
  `/system_stats`, sans renvoyer origine, chemin, workflow ni jeton ;
- `POST /v1/providers/comfyui/images` accepte uniquement `{ "prompt": "…" }` et un
  en-tête `Idempotency-Key` ASCII visible de 1 à 255 caractères.

L'opérateur fournit un workflow ComfyUI **API format** JSON de 2 Mio maximum, le nœud
et l'entrée texte à remplacer, ainsi que le nœud de sortie. La requête ne peut jamais
choisir un workflow, un checkpoint, un nœud, une URL ou un chemin. Le connecteur appelle
successivement `/prompt`, `/history/{prompt_id}` et `/view` ; il ne déclenche jamais
l'interruption globale d'une file partagée.

Configuration minimale :

```text
ACP_COMFYUI_ENABLED=1
ACP_COMFYUI_ORIGIN=http://127.0.0.1:8188
ACP_COMFYUI_WORKFLOW_PATH=C:\comfyui\workflows\acp-image-api.json
ACP_COMFYUI_PROMPT_NODE_ID=6
ACP_COMFYUI_PROMPT_INPUT=text
ACP_COMFYUI_OUTPUT_NODE_ID=9
ACP_COMFYUI_MAX_INFLIGHT_GENERATIONS=4
ACP_COMFYUI_MAX_INFLIGHT_WAITERS=16
ACP_COMFYUI_IDEMPOTENCY_MAX_BYTES=67108864
```

Un Bearer amont optionnel se configure avec `ACP_COMFYUI_API_TOKEN`. Les durées,
polls, taille d'image et cache sont bornés par les variables détaillées dans
[`.env.example`](../.env.example). HTTP est réservé au loopback ; ailleurs HTTPS est
obligatoire. Le client ignore les proxies d'environnement, ne suit aucune redirection,
borne les corps JSON et l'image, puis accepte uniquement PNG, JPEG ou WebP dont le type,
l'extension et la signature binaire concordent.

L'idempotence déduplique les appels simultanés et les rejeux dans un cache LRU/TTL borné
par entrées et par octets. Les générations propriétaires et leurs attentes coalescées
ont des limites distinctes ; une nouvelle clé reçoit `429` avant tout effet `/prompt`
lorsque la capacité est atteinte, tandis qu'une clé déjà en vol partage son résultat
sans que l'annulation d'un waiter annule le travail commun. Après toute tentative
`/prompt` susceptible d'avoir été acceptée, un tombstone expurgé reste réservé jusqu'à
sa TTL : timeout, annulation ou réponse ambiguë ne resoumettent donc pas le même job dans
ce processus. Une saturation de tombstones renvoie volontairement `429` jusqu'à leur
expiration.

Les valeurs par défaut autorisent 4 générations, 16 waiters et 64 Mio d'images en cache.
Les bornes codées sont 32 générations, 64 waiters, 256 Mio de cache et 128 Mio pour le
produit taille-image × générations. Cette garantie reste **process-local et non
durable** : redémarrage ou autre réplica peuvent rejouer un effet, et une image réussie
peut être évincée du LRU avant sa TTL. La réponse est forcée en pièce jointe avec
`no-store` et `nosniff`.

## Ce qui n'est pas prouvé ou livré

- aucun GLB n'a été rendu dans un vrai navigateur et aucune origine d'aperçu séparée n'a
  été déployée pour cette validation ; ces budgets réduisent l'exposition mais ne
  remplacent pas l'isolation et les limites du processus graphique ;
- aucun serveur ComfyUI, GPU, modèle ou nœud tiers n'a été contacté ; les tests utilisent
  un transport déterministe ;
- les licences des modèles, checkpoints, LoRA et nœuds d'un workflow restent à la charge
  de l'opérateur ;
- ComfyUI n'est pas encore un backend de mission worker et sa réponse n'est pas versée
  automatiquement dans la bibliothèque de livrables.
