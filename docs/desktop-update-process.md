# Mise à jour du client desktop depuis les publications GitHub — conception

Date d'état : 18 septembre 2026, Europe/Paris. Branche `feat/desktop-qt-railway`,
version du produit `0.9.0`.

## Ce que ce document est

Une **conception**, pas une implémentation. Le client desktop n'existe pas encore :
`apps/desktop` n'est pas créé, aucun code natif n'a été écrit ni compilé dans ce lot,
et ce poste ne dispose ni de Qt, ni de CMake, ni de compilateur C++
(`docs/desktop-railway-audit.md` §11). Rien de ce qui suit n'a été exécuté.

État réel du dépôt, vérifié le 18 septembre 2026 :

- `git tag` renvoie `v0.2.0` à `v0.7.0`. **Aucun tag `v0.8.0` ni `v0.9.0` n'existe**,
  alors que `VERSION` contient `0.9.0` : le mécanisme de publication n'a jamais été
  exercé.
- `.github/workflows/` ne contient que `ci.yml`, déclaré `permissions: contents: read`
  (ligne 11-12). **Il ne peut donc rien publier.** Un workflow de publication
  déclenché par tag, en `contents: write`, reste à créer — hors du périmètre de ce
  lot, qui n'a le droit de modifier ni `.github/**` ni `apps/**`.
- Aucun certificat de signature de code Windows, aucun secret de signature, aucune
  procédure n'existent dans le dépôt.

## 1. Source de vérité : les publications GitHub

Documentation lue le 18 septembre 2026 :
`docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28`.

| Point d'entrée | Usage |
| --- | --- |
| `GET /repos/{owner}/{repo}/releases/latest` | canal **stable** |
| `GET /repos/{owner}/{repo}/releases` | canal **préversion** (le client filtre lui-même) |

Définition officielle de « latest », citée : « The latest release is the most recent
non-prerelease, non-draft release, sorted by the `created_at` attribute. » Le canal
stable est donc obtenu **par le serveur**, pas par un tri du client.

Champs exposés par une publication : `tag_name`, `prerelease`, `draft`, `body`,
`published_at`, `assets`. Un élément d'`assets` expose `name`,
`browser_download_url`, `size` et `digest`.

**Réserve honnête sur `digest`** : le champ existe dans le schéma, mais la page lue
ne documente pas son contenu. Le client **ne doit pas s'y fier**. L'empreinte de
référence est celle du manifeste décrit en section 2, et le client la recalcule
lui-même.

**Limite de débit** : « The primary rate limit for unauthenticated requests is 60
requests per hour »
(`docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api`, lu le
18 septembre 2026). Le client interroge donc **au plus une fois par lancement et une
fois par 24 h**, lit `x-ratelimit-remaining` et `x-ratelimit-reset`, et affiche
« Vérification indisponible » — jamais « À jour » — quand la limite est atteinte.

## 2. Manifeste attendu

Chaque publication porte, en plus des paquets, **un fichier de manifeste**
`acp-desktop-<version>.manifest.json` produit par le workflow de publication et
attaché à la même publication. Le client ne télécharge jamais un paquet dont le nom
n'est pas décrit par ce manifeste.

Forme attendue (les valeurs sont illustratives et n'engagent rien) :

```json
{
  "schema": "acp.desktop.update/1",
  "product_version": "0.9.1",
  "channel": "stable",
  "published_at": "2026-10-01T09:00:00Z",
  "release_notes_url": "https://github.com/<owner>/<repo>/releases/tag/v0.9.1",
  "minimum_supported_client": "0.9.0",
  "server_contract": { "minimum": "1.0", "maximum": "1.0" },
  "packages": [
    {
      "platform": "windows-x86_64",
      "kind": "installer",
      "file_name": "acp-desktop-0.9.1-windows-x86_64-setup.exe",
      "size_bytes": 0,
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "signature": null
    }
  ]
}
```

Règles de lecture, toutes fermées :

1. `schema` inconnu ⇒ refus, message « Manifeste de mise à jour non reconnu ».
2. Un champ obligatoire absent ou d'un type inattendu ⇒ refus. Le manifeste est une
   **donnée reçue du réseau**, jamais une instruction : il ne peut porter ni commande,
   ni argument de ligne de commande, ni chemin d'installation.
3. `file_name` doit correspondre exactement au `name` d'un asset de **cette**
   publication. Le client construit l'URL de téléchargement à partir de l'asset ainsi
   retrouvé ; il n'utilise **aucune URL portée par le manifeste** pour un
   téléchargement de paquet.
4. `size_bytes` et `sha256` sont obligatoires. `sha256` est en hexadécimal minuscule,
   64 caractères.
5. `signature` vaut `null` tant qu'aucun certificat n'existe. Le jour où il existe, le
   champ devient obligatoire et sa vérification devient bloquante (section 4).

## 3. Politique stable / préversion

- **Stable par défaut**, et c'est le seul canal proposé sans action de l'utilisateur.
- **Préversion** : opt-in explicite dans les préférences, réversible, avec une
  mention permanente dans l'interface (« Canal préversion »). Le client filtre
  `prerelease == true` sur la liste des publications et ignore `draft == true`, qui
  n'est de toute façon pas servi à un lecteur anonyme.
- Un poste en canal préversion ne redescend **jamais** automatiquement vers le
  stable : une rétrogradation est une décision humaine, présentée comme telle.
- `minimum_supported_client` du manifeste ne sert qu'à **informer** : il n'autorise
  jamais le client à se mettre à jour tout seul.

## 4. Séquence exacte du client

| Étape | Comportement | En cas d'échec |
| --- | --- | --- |
| 1. Interrogation | HTTPS, validation de certificat du système, délai borné, une seule requête | « Vérification indisponible » + raison courte. **Jamais** « À jour » |
| 2. Comparaison | Version locale contre `product_version`, comparaison sémantique, pas lexicale | Version illisible ⇒ « Version inconnue », aucune proposition |
| 3. Notes de version | `body` de la publication affiché en **texte brut**, sans rendu riche, sans exécution, sans chargement de ressource distante | Notes absentes ⇒ « Notes de version indisponibles », la proposition reste valable |
| 4. Consentement | Bouton « Télécharger » explicite. Rien ne part avant | — |
| 5. Téléchargement | Dans un répertoire temporaire du poste, taille comparée à `size_bytes` pendant le transfert, abandon au dépassement | Message explicite, fichier temporaire supprimé |
| 6. Empreinte | SHA-256 recalculé sur le fichier reçu, comparé à `sha256` en temps constant | **Abandon**, fichier supprimé, message « Empreinte de la mise à jour non conforme : installation abandonnée », et **aucune nouvelle tentative automatique** |
| 7. Signature | Quand elle existera : vérification de la signature du paquet **avant** toute exécution | Abandon, même traitement qu'à l'étape 6 |
| 8. Installation | Le client **ouvre** le paquet par le mécanisme du système et se retire. Il n'exécute rien lui-même, n'élève aucun privilège, ne remplace aucun fichier de programme | L'utilisateur reste sur la version en place |

### Ce que le client ne fait jamais

- **Aucune installation silencieuse.** Aucun téléchargement automatique, aucune
  exécution automatique, aucune élévation de privilèges, à aucun moment.
- **Aucune exécution d'un binaire arbitraire.** Le seul fichier qui peut être ouvert
  est celui dont le nom figure dans le manifeste, dont l'asset appartient à la
  publication interrogée, et dont l'empreinte a été vérifiée.
- **Aucune obéissance au contenu reçu.** Ni le corps de la publication, ni le
  manifeste, ni le nom d'un asset ne peuvent déclencher une action : ce sont des
  données affichées, pas des ordres.
- **Aucun repli en HTTP.** Un échec de validation de certificat est un refus, pas un
  avertissement.
- **Aucune vérification silencieuse au démarrage sans consentement initial.** Le
  premier lancement demande si le client peut interroger GitHub ; un refus désactive
  la fonction et l'écran l'indique.

## 5. Ce que l'empreinte prouve, et ce qu'elle ne prouve pas

Le SHA-256 du manifeste protège contre une **altération en transit** et contre un
téléchargement corrompu. Il **ne prouve pas** l'authenticité de l'éditeur : le
manifeste et le paquet viennent de la même publication, donc quiconque prendrait le
contrôle du dépôt ou du compte de publication remplacerait les deux de façon
cohérente.

La seule chose qui prouve l'éditeur est une **signature de code** dont la clé n'est
pas hébergée chez le distributeur. Tant qu'aucun certificat n'existe, cette limite
doit être écrite dans l'interface : la fenêtre de mise à jour affiche « Paquet non
signé » et non une coche verte. Le certificat est un délai d'approvisionnement
externe, pas une tâche de développement (`docs/desktop-railway-audit.md` §6.3).

## 6. Ce que la publication doit produire, côté chaîne de construction

Rappel de dépendances, pour le lot qui écrira `.github/workflows/` :

1. Un workflow **déclenché par tag**, en `permissions: contents: write` ; l'actuel est
   en `contents: read` et ne peut rien publier.
2. Un job Windows (CMake, MSVC, tests natifs et QML) : **c'est la seule preuve de
   compilation possible sur ce chantier**.
3. Le calcul des empreintes et la génération du manifeste **dans le même job** que la
   construction du paquet, à partir des fichiers réellement produits — jamais
   recopiés à la main.
4. `scripts/check_version.py` étendu à la version du desktop, sans quoi le client
   dérivera silencieusement de `VERSION`.
5. Une décision de licence Qt et une technologie d'installeur : les deux décident du
   format du paquet et du contenu des notes de version.

## Ce que ce document ne prouve pas

Aucune publication GitHub n'a été créée, aucun manifeste n'a été produit, aucun
téléchargement n'a été vérifié, aucun paquet n'a été construit ni signé, et aucun
code de client n'existe. Les citations de l'API GitHub viennent des pages listées
ci-dessus, lues le 18 septembre 2026 ; elles n'ont pas été exercées contre un dépôt
réel.
