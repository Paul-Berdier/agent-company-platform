# Quotas réels d'abonnement (Codex CLI, Claude Code)

Date d'état : 24 septembre 2026 — phase 1 : contrats, stockage, API, worker et
écran « Quotas » du client desktop, qui consomme la route décrite ici (§ 6).

## 1. Ce que la plateforme montre, et ce qu'elle refuse de montrer

Les exécuteurs locaux du worker utilisent des abonnements personnels : **Codex CLI**
connecté par un compte ChatGPT (offre relevée sur le poste de référence : `prolite`)
et **Claude Code** (offres Pro ou Max). La plateforme affiche le **reste réel** de ces
abonnements, tel que la source officielle le donne :

- aucune estimation, aucune extrapolation, aucun calcul à partir des jetons consommés ;
- le seul calcul fait est `reste = 100 − part utilisée`, fenêtre par fenêtre ;
- une valeur que la source ne donne pas reste `null` et s'affiche **« Inconnu »** ;
- un relevé plus ancien que le seuil de fraîcheur s'affiche **« Périmé »**, jamais
  comme actuel.

Chaque relevé porte un état :

| `status` | Sens | Libellé attendu |
|---|---|---|
| `ok` | la source a répondu ; les fenêtres portent les valeurs reçues | valeurs, ou « Inconnu » par valeur absente |
| `not_signed_in` | profil Codex dédié absent, non connecté, ou connecté hors compte ChatGPT | « Non connecté » |
| `cli_missing` | Codex CLI introuvable ou impossible à lancer sur le poste du worker | « CLI absente » |
| `cli_too_old` | Codex CLI antérieur à 0.100.0 | « CLI trop ancienne » |
| `unavailable` | réponse mal formée, délai dépassé, erreur du serveur, fichier absent ou illisible | « Indisponible » |

Un état autre que `ok` ne porte **aucune mesure** (ni fenêtre, ni crédit, ni limite
atteinte) et porte toujours une explication française dans `detail` (300 caractères
au plus). Le contrat le refuse autrement.

Un état autre que `ok` décrit une **lecture en échec**, pas un compteur : il porte
toujours `limit_id = "probe"`, identifiant réservé que la plateforme n'attribue à
aucun compteur de la source (valeur par défaut d'un échec quand le champ est omis ;
refusée en 422 sur un relevé `ok`, et tout autre identifiant est refusé sur un échec).
Un échec ne peut donc jamais remplacer le dernier relevé réussi d'un compteur.

## 2. Réservé au propriétaire, usage personnel

Les conditions des fournisseurs réservent l'usage d'un abonnement à son titulaire :
les conditions d'OpenAI interdisent de rendre un compte accessible à autrui, et un
abonnement Claude est de même personnel. En conséquence :

- `GET /subscription-quotas` n'est lisible **que par le propriétaire de la plateforme**
  (`platform_role = "owner"`). Tout autre rôle reçoit un **403** explicite :
  « Quotas d'abonnement réservés au propriétaire de la plateforme : l'usage d'un
  abonnement est personnel à son titulaire. » ;
- le profil Codex dédié et la ligne d'état Claude Code sont ceux du titulaire, sur
  son poste ; la plateforme ne se connecte jamais à sa place et ne copie jamais ses
  identifiants ;
- ce relevé n'autorise pas à faire servir d'autres personnes par l'abonnement du
  titulaire : un usage multi-utilisateur passe par des clés d'API ou une offre
  d'entreprise, hors de ce document.

## 3. Sources officielles

### 3.1 Codex CLI : `codex app-server`

Le worker lance `codex app-server` (JSON-RPC 2.0, une ligne JSON par message sur
stdio, sans l'en-tête `jsonrpc`) et conduit, dans cet ordre :

1. `codex --version` : **0.100.0 au minimum** (première version qui publie
   `rateLimitsByLimitId`), sinon `cli_too_old` ; CLI introuvable : `cli_missing` ;
2. `initialize` puis la notification `initialized` ;
3. `account/read` : sans compte, `not_signed_in` ; compte par clé d'API ou autre type
   que `chatgpt`, `not_signed_in` avec l'explication correspondante ;
4. `account/rateLimits/read` : un relevé par compteur de `rateLimitsByLimitId`, ou à
   défaut un seul relevé depuis la vue historique `rateLimits`.

Le processus tourne avec `CODEX_HOME` = **profil dédié du worker**, dans un
environnement minimal recopié variable par variable : `OPENAI_API_KEY`,
`CODEX_API_KEY` et `CODEX_ACCESS_TOKEN` n'y figurent jamais, pas plus que les jetons
du worker. La lecture se fait donc en mode compte. Il est lancé sans shell dans la
clôture du runner local (Job Object sous Windows, session sous POSIX), avec un délai
global de 20 secondes ; son arbre de processus est arrêté à la fin, y compris après un
délai dépassé ou une annulation. Un arrêt non confirmé écarte le relevé.

Correspondance des champs (schéma publié par Codex CLI 0.156.1) :

| Source (`RateLimitSnapshot`) | Relevé | Remarque |
|---|---|---|
| clé de `rateLimitsByLimitId`, sinon `limitId` | `limit_id` | `default` si la source n'en donne pas |
| `primary`, `secondary` | `windows[].key` = `primary`, `secondary` | fenêtre nulle : omise |
| `usedPercent` | `windows[].used_percent` | entier arrondi par le serveur ; hors 0–100 : lecture `unavailable` |
| `windowDurationMins` | `windows[].window_minutes` | nul : « Inconnu » ; la durée nomme la fenêtre, pas sa position |
| `resetsAt` (secondes Unix) | `windows[].resets_at` (UTC) | nul : « Inconnu » |
| `planType` (sinon celui de `account/read`) | `plan` | texte de la source, par exemple `prolite` |
| `credits` | `credits` (`has_credits`, `unlimited`, `balance`) | `balance` reste le texte de la source |
| `rateLimitReachedType` | `limit_reached`, `reached_type` | présent et nul : `false` ; présent : `true` et son type ; absent : `null` |

Un seul compteur hors contrat (part utilisée hors 0–100, offre trop longue…) fait
échouer **toute** la lecture Codex, avec le nom du compteur et du champ refusés : un lot
partiel retirerait à tort les derniers relevés réussis du compteur écarté.

Ne sont **pas** repris : `limitName`, `rateLimitResetCredits`,
`ordinaryUsageAllowed`, `individualLimit`, `spendControlReached`, les notifications
`account/rateLimits/updated`, l'adresse électronique et l'identifiant du compte (lus
par le CLI, jamais conservés ni transmis), ni les messages d'erreur du serveur (seul
leur code numérique est cité).

### 3.2 Claude Code : la ligne d'état

Aucune API ne donne les limites d'un compte individuel Pro ou Max. Claude Code
transmet en revanche à sa **ligne d'état** un JSON qui contient
`rate_limits.five_hour` et `rate_limits.seven_day` (`used_percentage` de 0 à 100,
`resets_at` en secondes Unix), pour les abonnés Pro et Max, après la première réponse
de l'API dans la session. La ligne d'état livrée avec le worker
(`python -m acp_worker.claude_statusline`, § 5.2) recopie ces valeurs dans un fichier,
que le worker lit :

```json
{
  "source": "claude-code-statusline",
  "observed_at": "2026-09-24T08:00:00+00:00",
  "windows": {
    "five_hour": {"used_percentage": 12.5, "resets_at": 1790000000},
    "seven_day": {"used_percentage": null, "resets_at": null}
  }
}
```

`five_hour` devient une fenêtre de 300 minutes et `seven_day` une fenêtre de
10 080 minutes, d'après le nom même que leur donne Claude Code ; toute autre clé garde
une durée inconnue. `observed_at` est l'instant d'écriture par la ligne d'état. Un
fichier absent, illisible, trop volumineux (plus de 64 Kio), mal formé ou hors
contrat donne un relevé `unavailable` avec son explication ; la sonde ne lève jamais.
Le format est défini à un seul endroit, `apps/worker/src/acp_worker/claude_statusline.py`,
que la sonde importe.

## 4. Contrat de l'API

Les contrats Pydantic sont dans `packages/contracts/src/acp_contracts/subscriptions.py`,
leur miroir TypeScript dans `packages/contracts/typescript/index.ts`. Ils sont
stricts : champ inconnu ou manquant, type inattendu (un booléen n'est jamais un
nombre), borne dépassée ou incohérence sont refusés en **422**, avec un message en
français par champ.

### 4.1 Dépôt par le worker : `POST /work/workers/{worker_id}/subscription-quotas`

Authentification identique aux autres routes worker (`Authorization: Bearer <jeton du
worker>`) ; **interdite aux clients humains**, desktop compris. Corps
`SubscriptionQuotaBatch` : de 1 à 16 relevés, un seul par couple
(`provider`, `limit_id`). Pour un fournisseur, un lot porte soit les compteurs d'une
lecture réussie, soit un seul relevé d'échec (`probe`), jamais les deux. Un relevé dont
`observed_at` est plus de cinq minutes dans le futur est refusé (horloge du poste
déréglée).

Écriture sous le verrou de la ligne du worker, donc sérialisée pour un même worker :

- un relevé **plus ancien** que celui déjà stocké pour le même compteur est ignoré et
  compté dans `ignored_older` ;
- un relevé au moins aussi récent le remplace (un rejeu à l'identique est sans effet
  sur les valeurs) et compte dans `stored` ;
- une lecture réussie fait foi pour la liste des compteurs : si le lot contient des
  relevés `ok` pour un fournisseur, les compteurs du même worker et du même fournisseur
  qu'il ne rapporte plus, s'ils sont plus anciens que lui, sont retirés et comptés dans
  `removed` ;
- la même lecture réussie retire l'échec (`probe`) de ce fournisseur, **quelle que
  soit sa date d'observation** (par exemple l'état « non connecté » une fois le profil
  connecté) : cet échec a été reçu avant elle, l'écriture étant sérialisée par worker.
  C'est nécessaire pour Claude Code : le fichier de la ligne d'état est daté de son
  écriture, souvent avant l'échec de lecture qu'il suit ;
- un échec de lecture ne retire rien : les derniers relevés réussis restent visibles
  avec leur date, à côté de l'échec qui explique pourquoi ils ne sont plus relus, et
  deviennent « Périmé » avec le temps.

Réponse : `{"stored": 2, "ignored_older": 0, "removed": 1}`.

### 4.2 Lecture par le propriétaire : `GET /subscription-quotas`

Session du propriétaire (cookie `acp_session`) ; `401` sans session, `403` pour tout
autre rôle, `503` si `ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS` est invalide. Réponse
`SubscriptionQuotaList`, servie avec `Cache-Control: private, no-store` :

```json
{
  "items": [
    {
      "provider": "claude_code",
      "status": "ok",
      "source": "claude_code_statusline",
      "plan": null,
      "limit_id": "default",
      "windows": [
        {"key": "five_hour", "used_percent": 12.5, "window_minutes": 300,
         "resets_at": null, "remaining_percent": 87.5},
        {"key": "seven_day", "used_percent": null, "window_minutes": 10080,
         "resets_at": null, "remaining_percent": null}
      ],
      "credits": null,
      "limit_reached": null,
      "reached_type": null,
      "observed_at": "2026-09-24T08:00:00Z",
      "detail": null,
      "worker_id": "5b1f7a52-3c1e-4d3a-9d1e-0c2f6a7b8c9d",
      "worker_name": "poste-principal",
      "received_at": "2026-09-24T08:00:02Z",
      "stale": false
    },
    {
      "provider": "codex",
      "status": "ok",
      "source": "codex_app_server",
      "plan": "prolite",
      "limit_id": "codex",
      "windows": [
        {"key": "primary", "used_percent": 42, "window_minutes": 300,
         "resets_at": "2026-09-24T12:00:00Z", "remaining_percent": 58},
        {"key": "secondary", "used_percent": 7, "window_minutes": 10080,
         "resets_at": "2026-09-29T00:00:00Z", "remaining_percent": 93}
      ],
      "credits": {"has_credits": false, "unlimited": false, "balance": null},
      "limit_reached": false,
      "reached_type": null,
      "observed_at": "2026-09-24T08:00:00Z",
      "detail": null,
      "worker_id": "5b1f7a52-3c1e-4d3a-9d1e-0c2f6a7b8c9d",
      "worker_name": "poste-principal",
      "received_at": "2026-09-24T08:00:02Z",
      "stale": false
    }
  ],
  "stale_after_seconds": 1800,
  "generated_at": "2026-09-24T08:00:05Z"
}
```

- `items` : le dernier relevé de chaque compteur de chaque worker, triés par
  `provider`, `limit_id`, `worker_name` puis `worker_id` (ordre des points de code,
  identique sous SQLite et PostgreSQL) ;
- `remaining_percent` = 100 − `used_percent`, `null` quand la part utilisée est
  inconnue ;
- `stale` est vrai quand `observed_at` est plus ancien que `stale_after_seconds`
  (`ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS`, 1 800 s par défaut, de 60 à 604 800) ;
  `received_at` dit seulement quand l'API a reçu le relevé ;
- pour un même worker et un même fournisseur, le relevé dont `observed_at` est le
  plus récent donne l'état courant (par exemple « Indisponible » après un délai
  dépassé) ; les compteurs plus anciens restent affichés avec leur date ;
- une ligne ne fait jamais tomber la lecture des autres : des mesures stockées
  illisibles donnent un relevé `unavailable` (« Relevé enregistré illisible ») avec
  l'identité réelle de la ligne ; une identité elle-même hors contrat (par exemple le
  nom vide d'un worker enrôlé avant que l'enrôlement ne refuse les noms vides) écarte
  la ligne, signalée au journal de l'API par l'identifiant du worker et le nom des champs
  refusés, jamais par leur valeur ;
- un serveur antérieur à cette version répond `404` : le client affiche alors
  « Non disponible sur ce serveur ».

La forme exacte est figée par `apps/desktop/tests/fixtures/subscription-quotas.json`,
comparée à la réponse réelle par `apps/api/tests/test_subscription_quotas.py`.

### 4.3 Stockage

Table `subscription_quota_snapshots` (révision Alembic **0005**) : une ligne par
worker, fournisseur et compteur, fenêtres et crédits en JSON, instants en UTC. Les
lignes disparaissent avec leur worker (`ON DELETE CASCADE`). Elles ne sont qu'un cache
du dernier état lu : la descente de 0005 vers 0004 les supprime sans garde-fou.

## 5. Mise en place sur le poste du titulaire

### 5.1 Profil Codex dédié

Le worker n'utilise jamais le profil personnel `~/.codex`. Par défaut, son profil dédié
est `%USERPROFILE%\.acp\codex-home`. Si l'exécuteur Codex du worker est activé
(`ACP_WORKER_CODEX_ENABLED=1`), c'est son profil `ACP_WORKER_CODEX_HOME` qui est
réutilisé, afin que le quota affiché soit celui du compte réellement utilisé par les
missions.

La connexion est faite **par le titulaire lui-même**, jamais par la plateforme :

```powershell
New-Item -ItemType Directory -Force "$HOME\.acp\codex-home" | Out-Null
# Recommandé : identifiants dans le coffre du système plutôt qu'en clair (auth.json).
if (-not (Test-Path "$HOME\.acp\codex-home\config.toml")) {
  Set-Content "$HOME\.acp\codex-home\config.toml" 'cli_auth_credentials_store = "keyring"'
}
$env:CODEX_HOME="$HOME\.acp\codex-home"; codex login
```

Ne jamais copier `auth.json` dans la base, un journal, Git ou `QSettings`. Chaque
lecture lance `codex app-server` sur ce profil : le CLI y écrit ses propres fichiers
d'état (bases SQLite, journaux), comme lors de tout usage de Codex.

### 5.2 Ligne d'état Claude Code

Le worker livre sa ligne d'état : `acp_worker.claude_statusline`, bibliothèque standard
seulement, lancée par l'interpréteur Python du worker. Dans `~/.claude/settings.json`
du titulaire (chemins en barres obliques sous Windows) :

```json
{
  "statusLine": {
    "type": "command",
    "command": "C:/chemin/du/worker/.venv/Scripts/python.exe -m acp_worker.claude_statusline"
  }
}
```

Claude Code n'accepte qu'**une** commande `statusLine`. Si le titulaire en a déjà une, il
la place après `--` : elle reçoit la même entrée standard et son affichage est repris
tel quel, par exemple
`… -m acp_worker.claude_statusline -- powershell -NoProfile -File C:/Users/titulaire/.claude/statusline.ps1`.
La commande chaînée est lancée sans shell (le shell de Claude Code a déjà découpé la
ligne), avec un délai de 10 s ; si elle échoue ou ne répond pas, la ligne courte du
module s'affiche, suivie de « ligne d'état existante en échec ». Sans commande chaînée,
la ligne affiche le modèle, le dossier et chaque fenêtre (« 5 h : 23,5 % utilisés,
remise 14:00 »).

À chaque mise à jour de la ligne d'état, le module :

- ne recopie que `rate_limits.five_hour` et `rate_limits.seven_day` ; ni identifiant de
  session, ni chemin, ni modèle, ni coût, ni `spend_limit` (limite de dépense d'une
  passerelle, qui n'est pas un quota d'abonnement, et peut dépasser 100 %) ;
- écrit dans un fichier temporaire du même dossier (`.claude-code.json.*.tmp`), puis le
  substitue par `os.replace` : le worker ne lit jamais un fichier à moitié écrit, même
  quand Claude Code interrompt la commande pour une mise à jour plus récente. Les
  fichiers temporaires d'une exécution interrompue sont retirés après une heure. Sous
  Windows, un lecteur qui tient le fichier ouvert fait échouer la substitution : trois
  essais, puis la ligne affiche « relevé non enregistré » et la mise à jour suivante
  réessaie ;
- n'écrit rien tant que Claude Code n'a transmis aucune de ces fenêtres (avant la
  première réponse, ou hors abonnement Pro ou Max) : la ligne affiche « quotas
  d'abonnement non transmis par Claude Code » et le relevé précédent garde sa date ;
- recopie une part utilisée hors de 0–100, non numérique ou booléenne, et un instant de
  remise à zéro illisible, comme **inconnus** (`null`) ;
- ne lève jamais et sort avec le code 0 ; une entrée illisible ou un argument autre que
  `-- commande` est signalé dans la ligne affichée.

Chemin écrit et lu par défaut : `%USERPROFILE%\.acp\quotas\claude-code.json` (hors de
`%LOCALAPPDATA%`, que l'application Claude Desktop redirige vers un dossier privé).
`ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT`, chemin absolu, le remplace pour le worker **et**
pour la ligne d'état : la définir dans les deux environnements (par exemple dans le bloc
`env` des réglages de Claude Code). Une valeur non absolue est refusée : rien n'est écrit
et la ligne le dit.

Preuves : `apps/worker/tests/test_claude_statusline.py` (vrai processus alimenté par le
JSON de session documenté par Claude Code, fichier relu par la sonde du worker, ligne
existante conservée ou en échec, écriture atomique) et, de bout en bout jusqu'à la vue du
propriétaire, `test_a_real_status_line_reading_reaches_the_owner_view` dans
`apps/api/tests/test_subscription_quotas.py`.

### 5.3 Variables du worker

| Variable | Défaut | Rôle |
|---|---:|---|
| `ACP_WORKER_SUBSCRIPTION_QUOTAS` | `0` | `1` active la boucle de relevé ; toute autre valeur que `0`/`1` est refusée |
| `ACP_WORKER_QUOTA_INTERVAL_SECONDS` | `300` | intervalle entre deux relevés, entier de 60 à 86 400 |
| `ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT` | `%USERPROFILE%\.acp\quotas\claude-code.json` | fichier de la ligne d'état, chemin absolu |
| `ACP_WORKER_QUOTA_CODEX_HOME` | `%USERPROFILE%\.acp\codex-home` | profil Codex dédié, si l'exécuteur Codex n'est pas activé |
| `ACP_WORKER_QUOTA_CODEX_EXECUTABLE` | `codex` trouvé dans le `PATH` | exécutable absolu, si l'exécuteur Codex n'est pas activé |

Avec l'exécuteur Codex activé, `ACP_WORKER_QUOTA_CODEX_HOME` et
`ACP_WORKER_QUOTA_CODEX_EXECUTABLE` sont **refusés** : un seul profil Codex par worker.
La recherche dans le `PATH` ne regarde que les dossiers absolus, jamais le dossier
courant. Côté API, `ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS` règle le seuil de fraîcheur.

La boucle est indépendante de celle des missions : elle ne retarde jamais un claim.
Elle relève Codex et Claude Code en parallèle, envoie un lot, puis attend l'intervalle.
Une erreur (sonde, réseau, refus de l'API) est journalisée par son type ou son code
HTTP seulement, jamais par son message, et la boucle reprend à l'intervalle suivant.
`agent-company-worker doctor` affiche `subscription_quotas` (`enabled`/`disabled`) et
l'intervalle, jamais les chemins.

## 6. Affichage dans le client desktop

L'écran **« Quotas »** du client natif (entrée « Quotas » de la barre latérale, commande
`navigation.quotas`) lit `GET /subscription-quotas` par le client d'API partagé, avec le
cookie de session ; il ne lit jamais le poste du worker, un fichier local ni la base.
Code : `apps/desktop/src/viewmodels/SubscriptionQuotasViewModel.*`,
`apps/desktop/qml/pages/QuotasPage.qml`, `apps/desktop/qml/components/QuotaGauge.qml`.

- **Réservé au propriétaire** : une session d'un autre rôle n'envoie aucune requête et
  affiche « Réservé au propriétaire de la plateforme » ; un 403 du serveur produit le
  même état, sans relecture automatique. Une mention visible rappelle en tête d'écran
  « Abonnements personnels du propriétaire — usage personnel uniquement ».
- **Échec fermé** : la réponse est validée champ par champ (champs attendus exactement,
  types, énumérations, bornes, horodatages avec fuseau, cohérence `source`/`provider`,
  `remaining_percent` = 100 − `used_percent` à l'arrondi de l'API près, absence de mesure
  hors `ok`, doublons). Au moindre écart, toute la réponse est refusée avec sa raison en
  français et les valeurs précédentes disparaissent.
- **Une carte par relevé** : fournisseur (« Codex (compte ChatGPT) », « Claude Code »),
  worker, offre, état de la sonde (Connecté, Non connecté, CLI absente, CLI trop
  ancienne, Indisponible), source (« relevé officiel app-server », « ligne d'état Claude
  Code »), compteur, fraîcheur (« relevé il y a 3 min »), badge « Périmé », crédits et
  alerte « Limite atteinte ». Pour un même worker et un même fournisseur, le relevé le plus
  récent donne l'état courant ; un compteur plus ancien porte la mention « Relevé
  antérieur ».
- **Une jauge par fenêtre**, dessinée en Qt Quick (Qt Charts est exclu pour licence) :
  « Fenêtre 5 h » (300 min), « Semaine » (10 080 min), sinon « Fenêtre de N min », ou la
  clé de la source quand la durée est inconnue. La barre montre la part restante ; les
  parts restante et utilisée sont écrites en toutes lettres, avec l'heure locale de remise
  à zéro et son compte à rebours (« dans 2 h 14 », « déjà passée »). Une part inconnue
  n'est jamais dessinée comme zéro : « Inconnu ».
- **Actualisation** : bouton « Actualiser » et relecture automatique toutes les 60 s,
  seulement pendant l'affichage de l'écran, fenêtre non réduite ; quitter l'écran ou
  réduire la fenêtre arrête la lecture, et revenir relit l'API au lieu de montrer des
  valeurs d'avant. Un serveur sans la route (404) donne « Non disponible sur ce
  serveur » ; un serveur injoignable, « Hors ligne ».

Preuves : `apps/desktop/tests/cpp/tst_subscription_quotas.cpp` (fixture de référence,
liste vide, 403, rôle non propriétaire, charges malformées, relevé périmé, valeurs nulles,
limite atteinte, horodatages fractionnaires, hors ligne, 404, actualisation liée à
l'écran, session changée), `tst_quotas_ui.cpp` (vraie page, noms accessibles, jauge
dessinée, fenêtre réduite puis restaurée, actualisation, 403, navigation par la barre
latérale) et
`tests/qml/tst_quota_gauge.qml`.

## 7. Limites connues

- **Non mesurés** : l'usage et les limites de **Figma**, et les **crédits d'API**
  (clés OpenAI ou Anthropic facturées à l'usage) : aucune source n'est relevée ici.
- **Journaux de session Codex non utilisés** (`CODEX_HOME/sessions/**/rollout-*.jsonl`) :
  leur format n'est pas un contrat public, ils peuvent être compressés, absents avec
  `--ephemeral`, et `rate_limits` y vaut parfois `null`.
- **Chemin connecté non éprouvé avec un vrai compte** : au 24 septembre 2026, le profil
  dédié du poste de référence n'est pas connecté. Avec le vrai Codex CLI 0.156.1, seul
  le chemin « non connecté » a été exécuté, sur un `CODEX_HOME` temporaire portant la
  même configuration que le profil dédié (réponse `not_signed_in` en 1 s, aucun
  processus Codex résiduel). Les réponses d'un compte connecté sont éprouvées par un faux
  app-server dont les réponses sont validées contre le schéma publié par la même
  version (`apps/worker/tests/fixtures/codex_app_server_0_156_1`).
- **Compteurs Codex** : `limitName` n'est pas transmis ; au-delà de 15 compteurs, le
  relevé Codex devient `unavailable` plutôt que tronqué ; un `usedPercent` hors 0–100
  rend toute la lecture `unavailable` (les derniers compteurs réussis restent affichés).
- **Ligne d'état non éprouvée dans un vrai Claude Code** : le module est exercé par un
  vrai processus alimenté par le JSON de session documenté, pas encore lancé par Claude
  Code lui-même sur le poste de référence. Il ne tourne que pendant l'usage de Claude
  Code : sans session ouverte, rien n'est relevé.
- **Claude Code** : rien n'est relevé tant que Claude Code n'a pas répondu une fois
  dans une session ; sans usage, le relevé vieillit et devient « Périmé ». Une erreur
  de lecture passagère apparaît comme l'état courant (« Indisponible ») jusqu'à la
  lecture réussie suivante, qui la retire ; le dernier relevé réussi reste affiché
  entre-temps, avec sa date.
- **Ordre de réception** : le retrait d'un échec suppose que les lots d'un worker
  arrivent dans l'ordre de leurs lectures, ce que garantit la boucle du worker (un lot à
  la fois, sans renvoi). Un lot réussi rejoué plus tard retirerait un échec plus récent.
- **Pas de temps réel** : la vue se relit périodiquement ; aucun événement SSE n'est
  émis pour un nouveau relevé.
- **Worker révoqué** : ses derniers relevés restent listés, deviennent « Périmé », et
  ne disparaissent qu'avec la suppression du worker.
- **Worker au nom vide** : l'enrôlement refuse désormais un nom vide ou fait de seuls
  espaces (le NUL l'était déjà). Un worker enrôlé avant cette règle sous un tel nom n'a
  plus de relevé visible dans l'écran « Quotas » (ligne écartée, signalée au seul
  journal de l'API) : le réenrôler sous un nom lisible.
- **Horloges** : la fraîcheur compare l'horloge de l'API à `observed_at`, fixé par le
  poste du worker (Codex) ou par la ligne d'état (Claude Code) ; un écart de plus de
  cinq minutes dans le futur est refusé.
- Les conditions et les limites des fournisseurs évoluent : les revérifier avant chaque
  version, avec leurs sources et leur date.
