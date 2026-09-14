# Sécurité et frontières de confiance

Date d'état : 14 septembre 2026 — version publiée `0.7.0`, Lot G `0.8.0`
implémenté dans l'arbre de travail et non publié
Statut : frontières utilisateur/inter-services fermées et runner local contrôlé au
Lot C ; coffre de secrets, politique de sortie anti-SSRF, expurgation des retours
tiers, clôture d'arrêt Windows et révocation des extensions ajoutés au Lot D ; flux
utilisateur authentifié par curseur, stockage privé de livrables, liens signés bornés
et révocables, expurgation des sorties de tests ajoutés au Lot E ; clés de tir uniques,
bail/fencing du planificateur, webhooks entrants à secrets hachés, budgets fail-closed
et alertes in-app ajoutés au Lot F ; validation GLB, origine d'aperçu obligatoire,
connecteur ComfyUI borné, harnais E2E et exécuteurs CLI fencés ajoutés au Lot G. La
production reste interdite sans isolation OS/réseau, origine d'aperçu séparée déployée
et exploitation PostgreSQL sauvegardée.

Le modèle de menace par actif est tenu à part dans
[docs/security/threat-model.md](security/threat-model.md).

## Conclusion

Le Lot C conserve le bootstrap propriétaire, les sessions serveur révocables et
expirables, une protection CSRF et des rôles appliqués aux routes utilisateur. Les
frontières API → provider-gateway et API → event-service utilisent des secrets
inter-services distincts ; les surfaces sans secret configuré échouent fermées.

Le Lot D ajoute un coffre de secrets chiffrés à références, une politique de sortie
réseau appliquée côté serveur (SSRF, DNS rebinding, redirections, taille de réponse),
un registre MCP et une bibliothèque de skills versionnés avec autorisation explicite
de tout lancement `stdio` et révocation de bout en bout. Ces contrôles sont prouvés
par des tests locaux déterministes : aucun serveur MCP, dépôt GitHub ou runner distant
réel n'a été contacté.

Le worker réel est un opt-in : un exécutable absolu via un argv local fixe, ou un
exécuteur Codex/Claude avec profil séparé et racines projet allowlistées, doit être
entièrement configuré. Tous passent par tentative/fencing, environnement minimal,
durée et sorties bornées. Le Job Object vérifie la vidange sous Windows ; sous POSIX,
la terminaison du groupe connu reste best effort face à un descendant qui change de
session. Une politique d'autonomie que le backend sélectionné ne peut pas appliquer
est refusée avant le spawn.

Le Lot E ajoute une voie temps réel **authentifiée** servie par l'API métier elle-même
(session, RBAC revérifié à chaque page, reprise par curseur), un stockage de livrables
privé adressé par contenu, des liens de téléchargement signés bornés et révocables, et
une règle claire sur le contenu produit par un test : il est traité comme non fiable et
n'est jamais exécuté dans l'origine de la plateforme. Ces contrôles sont prouvés par
des tests déterministes : **aucun navigateur réel n'a été lancé et aucun test
Playwright réel n'a été exécuté** pour cette version.

Le Lot F conserve toutes les décisions de planification et de budget côté API. Une
contrainte unique SQL arbitre les occurrences concurrentes, le planificateur écrit
uniquement avec un bail vivant et le fence courant, et le worker doit présenter son
identité, son lease de tentative et son fence avant un permis ou un rapport de budget.
Le webhook entrant exige au moins 256 bits fournis par le client ; seule son empreinte
est persistée et la comparaison est faite en temps constant. Les alertes sont
dédupliquées par cause et les préférences personnelles ne modifient pas leur état
canonique. Les tests restent locaux : aucun webhook Internet ni service tiers n'a été
contacté.

Le Lot G ferme trois nouvelles frontières. Un GLB doit être structurellement validé et
scellé par son sha256 avant aperçu, lequel exige une origine distincte ou échoue en
`424`. ComfyUI reçoit uniquement un prompt dans un workflow local fixé par l'opérateur,
avec réseau, corps et types de sortie bornés. Codex/Claude ne reçoivent qu'une mission
supervisée et une racine projet ; ACP refuse un second CLI, désactive les fonctions
intégrées connues de multi-agent, d'approbation interactive, de MCP et de navigateur,
mais ne peut empêcher un binaire de créer un processus descendant. Le paquet E2E nominal
est isolé et ne résout Playwright que sous `ACP_E2E=1` exact ; le script de collecte
directe peut charger le framework, mais la spec reste ignorée et aucun navigateur n'est
lancé sans cet opt-in. Lorsque le parcours est activé, sa politique couvre tout le
contexte navigateur, refuse les popups, neutralise `Worker`/`SharedWorker`, prouve le
préflight CORS par une vraie requête `OPTIONS` séparée et autorise exactement un login
sans redirection ni retry ; ensuite seuls `GET`/`HEAD`/`OPTIONS` restent possibles.
`EventSource` est désactivé dans ce parcours afin que le Studio utilise son polling réel
et que chaque réponse HTTP puisse être refusée avant toute redirection ; le SSE reste à
éprouver séparément.
Aucun de ces quatre chemins n'a été exercé contre un service ou navigateur réel pendant
cette validation.

Ces garanties ne rendent pas encore la plateforme exploitable sur Internet. Il
reste notamment à compléter la matrice d'autorisation exhaustive, les en-têtes web
de production, l'isolation OS/réseau du runner, l'origine d'aperçu séparée, les
migrations PostgreSQL, une limitation de débit distribuée en bordure, la rotation des
secrets de service et la restauration.

L'infrastructure pcIA et les systèmes Prooftag sont hors périmètre. Ils ne doivent
être ni découverts, ni configurés, ni proposés comme runner ou ressource personnelle.

## Actifs et frontières

Les actifs principaux sont les identités et sessions, secrets de fournisseurs,
sources des projets, mémoire et conversations, permissions, runs et approbations,
événements, preuves, artefacts et identités de runners.

```text
Navigateur / CLI
      │ frontière utilisateur non fiable
      ▼
API de contrôle ── base métier ── stockage privé
      │
      ├── frontière de service ── Hermes
      ├── frontière de service ── événements
      └── frontière d'exécution ── runner ── projet et outils non fiables
```

Un `project_id`, une instruction de prompt, un worktree Git ou un manifest de plugin
n'est pas une frontière de sécurité. Chaque contrôle doit être appliqué par l'API,
le stockage ou le runner qui détient effectivement la ressource.

## Corrections critiques héritées du Lot A

- Les échecs HTTP, réponses non JSON, plans vides et verdicts absents ou invalides
  du gateway échouent fermés ; aucun plan ou verdict positif n'est inventé.
- Le provider manuel conserve une évaluation en attente et non approuvée.
- La terminaison nominale d'une simulation worker est bloquée, avec validation
  technique non exécutée et acceptation utilisateur en attente ; une erreur de
  préparation peut échouer, mais une simulation ne peut jamais annoncer un succès.
- Le client HTTP de la plateforme et celui du provider-gateway sont séparés : le
  Bearer du worker n'est plus envoyé au gateway.
- La mise à jour d'un task run par un worker exige son Bearer, `X-Worker-Id` et un
  lease actif et non expiré sur le run.
- Un statut `succeeded` exige `technical_validation=passed` et au moins une preuve ;
  l'API met à jour tâche/agent, libère le lease et persiste elle-même l'événement
  terminal dans la transaction, au lieu d'accepter un succès séparé du worker.
- L'ingestion publique d'un événement de tâche exige l'identité worker, un lease
  actif, un scope canonique dérivé du run et un type non terminal explicitement
  autorisé.
- Lorsqu'une expiration de lease est réconciliée par l'API, le run devient
  `interrupted`, la tâche et l'agent `blocked`, la capacité est libérée et
  `task.interrupted` est persisté ; la plateforme n'effectue aucun replay
  automatique et refuse de réanimer le lease après son échéance.
- Les trois services HTTP n'acceptent plus `*` par défaut pour CORS ; leurs seules
  origines par défaut sont les deux URLs de développement du web.

Ces garanties ont des tests ciblés. Le Lot C ajoute un fencing token par tentative
et protège les transitions de la machine d'états mission ; toutes les routes enfant,
les effets tiers et le flux WebSocket utilisateur ne sont pas encore couverts.

## Accès utilisateur et frontière Hermes (Lot B)

- Le bootstrap n'est disponible qu'avant la création du premier propriétaire et
  exige `ACP_BOOTSTRAP_TOKEN` ; aucune inscription publique n'est exposée.
- Les mots de passe sont hachés avec Argon2id. Seul le SHA-256 d'un jeton de session
  opaque est stocké ; la session expire, peut être révoquée et voyage dans un cookie
  `HttpOnly` `SameSite=Strict` (`Secure` exigé derrière HTTPS).
- Le jeton CSRF est tourné lors de la restauration de session et exigé sur les
  mutations web. Les réponses d'authentification sont `no-store`.
- `X-User-Id` n'établit aucune identité. Les ressources utilisateur sont résolues à
  partir de la session puis filtrées par projet/workspace et rôle propriétaire,
  opérateur/membre ou lecteur.
- Le navigateur ne reçoit ni `HERMES_API_KEY`, ni Bearer worker ou gateway. Hors
  `GET /health`, le provider-gateway exige `ACP_GATEWAY_SERVICE_TOKEN`.
- Conversations et tours sont persistés avant l'appel provider ; les répétitions
  conservent une clé d'idempotence durable et une conversation générale reste privée
  à son créateur, sauf pouvoir d'administration global explicitement testé.

## Durcissement du service d'événements (lot B)

- `POST /internal/events` échoue fermé lorsque `ACP_EVENT_SERVICE_TOKEN` est absent,
  et exige un Bearer comparé en temps constant lorsqu'il est configuré. L'API ne
  transmet ce secret que dans l'en-tête `Authorization`, jamais dans l'URL.
- Le WebSocket navigateur anonyme est fermé par défaut avec le code applicatif
  `4403`. Seul l'opt-in explicitement dangereux
  `ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET=1` rétablit le comportement historique
  pour un développement local isolé.
- Ce verrouillage ne constitue pas encore un flux temps réel utilisateur : une voie
  authentifiée et scoppée, avec reprise par curseur, reste à construire avant toute
  exposition réseau.

## Coffre de secrets, sorties réseau et extensions (Lot D)

### Coffre de secrets

- Les valeurs sont chiffrées au repos avec Fernet. `ACP_SECRETS_KEYS` liste les clés
  séparées par des virgules : la première chiffre, les suivantes déchiffrent encore,
  ce qui permet une rotation de clé sans perte. Sans clé configurée, l'état est
  explicite (`configured=false`) et les routes qui chiffrent ou déchiffrent répondent
  `503` avec l'action à effectuer — jamais un stockage en clair de repli.
- Une valeur n'est jamais retournée : ni par une route de lecture, ni dans un export,
  ni dans un événement, ni dans une URL, ni dans le frontend. Le CLI refuse
  `--value` en argument et n'accepte que `--value-stdin`.
- Les portées sont minimales : un secret `project` ne peut servir qu'à son projet, y
  compris lors d'une activation ultérieure qui tenterait de faire dériver un
  rattachement existant. La création, la rotation et la révocation sont réservées au
  propriétaire et produisent un événement d'audit sans valeur.
- Le déchiffrement n'a lieu que pour un appel autorisé : en-têtes du diagnostic HTTP
  exécuté par l'API, ou variables d'environnement remises à un runner authentifié lors
  du claim d'un diagnostic `stdio` approuvé (réponse `Cache-Control: no-store`). Un
  secret révoqué, absent ou illisible (clé retirée) produit un échec explicite.

### Expurgation des contenus renvoyés par un tiers

Un serveur MCP peut réécrire la valeur qu'on lui a transmise dans `serverInfo`, dans
une capacité, dans la description ou le schéma d'un outil, sur `stderr` ou dans un
message d'erreur. Ce contenu est persisté puis servi à tout utilisateur authentifié :
il est donc expurgé — les valeurs injectées sont remplacées par `***` — avant écriture
en base. La règle est écrite une seule fois (`acp_contracts.redaction`) et appliquée
par les deux chemins : le runner sur son résultat, **et** l'API sur la découverte
HTTP comme sur le résultat posté par un runner. Toute valeur non vide est expurgée,
sans plancher de longueur.

### Politique de sortie réseau

- Schémas `http`/`https` uniquement, pas d'userinfo, pas de fragment, hôte normalisé
  IDNA ; `http` refusé sauf hôte explicitement allowlisté (ou bouclage avec
  `ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP=1`).
- Toutes les adresses résolues sont contrôlées et **une seule adresse bloquée suffit
  à refuser** (réponses DNS mixtes). Sont bloqués : bouclage, réseaux privés,
  link-local dont la métadonnée cloud `169.254.169.254`, multicast, réservé, CGNAT
  `100.64.0.0/10`, ULA `fc00::/7`, `fe80::/10`, IPv4-mapped, 6to4 et Teredo.
- L'adresse retenue est épinglée pendant la requête (`Host` + SNI conservés), les
  redirections sont revalidées intégralement (3 au maximum) et le corps est borné à
  2 000 000 octets. Les variables proxy de l'environnement sont ignorées.
- Une allowlist privée ciblée reste possible ; chaque usage produit l'événement
  d'audit `outbound.private_allowlist_used` avec l'hôte, l'adresse et le motif.

### Lancement `stdio` et révocation

- Aucun lancement `stdio` sans autorisation explicite portant l'action, la cible
  (commande et arguments), les conséquences, la portée (runner désigné), l'empreinte
  exacte de la révision et une expiration d'une heure. Une révision modifiée invalide
  l'autorisation ; un lease perdu refuse le résultat au lieu de supposer un succès.
- Côté runner, la capacité est désactivée par défaut et exige une allowlist
  d'exécutables absolus, comparée après résolution du chemin. Aucun shell,
  environnement minimal sans héritage des variables du worker, durée et sorties
  bornées, arrêt de l'arbre de processus.
- La révocation d'un serveur MCP ou d'un skill est irréversible, exige une raison,
  révoque les rattachements, retire l'objet des extensions résolues d'un projet et
  produit un événement d'audit sans supprimer l'historique.
- Les contenus importés (configurations, `README`, `SKILL.md`, schémas d'outils) sont
  traités comme des données : bornés, affichés comme texte, jamais rendus, et sans
  effet sur une politique, un droit ou une instruction système.

### Clôture d'arrêt des processus lancés

- Sous Windows, tout processus lancé par le runner — exécution de mission comme sonde
  MCP `stdio` — est créé **suspendu**, affecté à un Job Object
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` sans `BREAKAWAY_OK`, vérifié par
  `IsProcessInJob`, puis repris. Aucune instruction du programme ne s'exécute hors de
  sa clôture ; une affectation impossible devient `spawn_failed` /
  `job_assignment_failed` au lieu d'une exécution non bornée.
- L'arrêt termine le job puis attend que son compteur de processus actifs tombe à
  zéro ; la passe d'énumération native existante est conservée comme vérification
  indépendante. Un arbre dont l'arrêt n'est pas prouvé ne produit pas un succès.
- Ce contrôle répare un défaut réel : l'énumération par filiation ne rattache pas un
  petit-fils dont le parent intermédiaire — un **lanceur** comme
  `.venv\Scripts\python.exe`, `npx.cmd` ou `uvx` — a déjà quitté. Le descendant
  survivait alors avec les tubes hérités.
- Ce n'est **pas** une sandbox : le job ne limite ni CPU, ni mémoire, ni réseau, et il
  n'existe pas d'équivalent POSIX dans ce lot (`start_new_session` puis `killpg`, qu'un
  descendant peut quitter en changeant volontairement de session).

## Flux, livrables et tests web (Lot E)

### Flux utilisateur authentifié

- Le flux temps réel est servi par l'**API métier** (`GET /streams/runs/{id}`,
  `GET /streams/projects/{id}`), pas par `apps/event-service` : c'est l'API qui détient
  la base, les sessions et le RBAC. Le WebSocket anonyme du service d'événements reste
  fermé par défaut ; il n'a pas été rouvert.
- L'autorisation n'est pas résolue une seule fois à l'ouverture : elle est **revérifiée
  à chaque page**. Une révocation de session ou une perte de membership ferme la
  connexion au plus tard à l'interrogation suivante, avec une trame de fermeture
  explicite. Un `project_id` fourni par le client n'élargit jamais la portée : le
  projet est résolu côté serveur à partir de la tentative.
- La reprise se fait par curseur (`Last-Event-ID` ou `?after_seq=`) sur un compteur
  monotone à ordre total, jamais sur un horodatage. Une reconnexion ne relance jamais
  une mission et ne duplique aucun événement ; une coupure n'invente aucun état
  (`connected`, `reconnecting`, `polling`, `offline` sont exposés tels quels).
- Le nombre de connexions simultanées par utilisateur est borné
  (`ACP_STREAM_MAX_CONNECTIONS_PER_USER`, défaut 4), la connexion est rotée après
  `ACP_STREAM_MAX_SECONDS` (défaut 900 s) et les réponses portent
  `Cache-Control: no-store` et `X-Accel-Buffering: no`.
- Aucun média ne transite dans un événement : le payload ne porte qu'une référence
  d'artefact, une empreinte, un type MIME et une taille.

### Contenu actif produit par un test : jamais servi sur l'origine de contrôle

- Le type servi est décidé par une **allowlist serveur** construite sur l'extension et
  le type déclaré. Aucun reniflage de contenu : un fichier `piege.html` annoncé
  `image/png` reste un piège, pas une image, et un type non reconnu devient
  `application/octet-stream`.
- `text/html`, `image/svg+xml` et les archives — dont la trace Playwright — ne sont
  **jamais** servis en ligne : `Content-Disposition: attachment` est imposé.
- Toute réponse de contenu porte `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox` et
  `Cache-Control: private, no-store`.
- Une session ou un lien `purpose=download` reçoit toujours
  `Content-Disposition: attachment`. Seul un jeton `purpose=preview`, signé pour cet
  usage et présenté sur `ACP_ARTIFACT_PUBLIC_ORIGIN`, peut produire une réponse
  `inline` pour un type allowlisté ; son rejeu sur l'origine API répond `403`.
- Le Studio n'utilise ni `iframe`, ni `srcdoc`, ni `innerHTML` pour un contenu venu de
  l'API : messages d'erreur, extraits de code, noms de fichiers et payloads sont
  insérés en `textContent`.
- Écart assumé et affiché : `ACP_ARTIFACT_PUBLIC_ORIGIN` n'est configurée nulle part
  aujourd'hui. Une demande `purpose=preview` répond donc `424` avant création du jeton ;
  elle ne retombe plus sur l'origine de l'API. Le téléchargement reste disponible.

### Liens de téléchargement signés, bornés et révocables

- Un lien est un jeton HMAC-SHA256
  `v2.<artifact_id>.<exp>.<purpose>.<nonce>.<sig>` lié à **l'artefact, au demandeur et
  à l'usage**. Le nonce rend deux émissions de la même seconde distinctes. Le lien est
  borné à `ttl_seconds` ≤ 900 (défaut 300), enregistré par empreinte (`token_hash`) et
  révocable par `DELETE /artifacts/links/{link_id}` — par son titulaire, ou par un
  owner du projet du livrable. Les anciens jetons `v1` déjà émis restent lisibles
  jusqu'à leur expiration mais sont traités uniquement comme téléchargements. Ni
  l'existence du lien ni celle du livrable ne sont énumérables : un appelant sans droit
  reçoit `404`.
- Les clés viennent de `ACP_ARTIFACT_SIGNING_KEYS` (liste : la première signe, les
  suivantes vérifient encore, ce qui permet la rotation). Sans clé configurée, la
  création de lien répond `503` avec l'action à effectuer ; le téléchargement
  authentifié par session reste possible. Aucun projet ne devient public.
- La clé de stockage est dérivée du sha256 : un nom fourni par le client n'entre jamais
  dans un chemin, et la traversée de répertoire n'a pas de surface.
- Le téléversement worker vérifie l'identité **avant** de lire le corps, borne chaque
  fichier (`ACP_ARTIFACT_MAX_BYTES`, défaut 200 Mio) et le cumul par tentative
  (`ACP_ARTIFACT_MAX_BYTES_PER_RUN`, défaut 1 Gio) pendant le flux, et rend le même
  artefact pour un même sha256 sur la même tentative.

### Expurgation des sorties de tests

- Le processus de test **ne reçoit aucun credential de la plateforme** : le reporter
  écrit un fichier NDJSON local et n'effectue aucun appel réseau ; c'est le worker
  authentifié qui ingère ce fichier avec sa propre identité.
- Messages d'erreur et extraits de code produits par la suite de tests passent par
  `redact_text` / `redact_data` avec les valeurs injectées dans l'environnement du
  processus comme liste d'expurgation, avant d'être envoyés à l'API : une suite qui
  imprime une variable ne la republie pas.
- Le reporter ne journalise ni l'environnement ni les en-têtes de requête, tronque
  messages et extraits à 8 000 caractères, retire les séquences ANSI et ne coupe pas
  une paire de substituts UTF-16.
- Écart restant : comme pour un serveur MCP bavard, l'expurgation porte sur les valeurs
  connues de la plateforme ; une valeur dérivée (encodée, tronquée, hachée) n'est pas
  couverte. Et un filtre de texte ne masque pas des pixels sur une capture d'écran.

### Clôture de processus d'une exécution de tests

- L'exécution de tests web réutilise les deux points d'entrée publics du runner du
  Lot D — `spawn_fenced_process` puis `terminate_process_tree` — donc la clôture Job
  Object s'applique aussi à un navigateur Playwright et à toute sa descendance. Jamais
  de shell, jamais de spawn direct.
- Un arrêt d'arbre non prouvé (`terminate_process_tree` renvoie `False`) **interdit**
  le verdict `passed` : un succès de test n'est jamais accepté quand des processus
  peuvent avoir survécu.
- Un rapport absent, vide ou dont une pièce jointe a été refusée ne peut pas produire
  un `passed`. Le verdict que l'API dérive des totaux fusionnés ne peut qu'**aggraver**
  le verdict local, jamais le repeindre en vert, et le code de sortie annoncé par le
  rapport ne peut jamais effacer celui mesuré par le worker.

### Rétention

- `python -m acp_api.retention` est une purge **à blanc par défaut** : sans `--apply`,
  elle décrit ce qu'elle supprimerait et ne supprime rien.
- Elle conserve les événements terminaux d'une tentative, ne supprime jamais un blob
  encore référencé par un autre artefact (adressage par contenu ⇒ comptage de
  références) ni un artefact cité par une preuve de mission. La citation est détectée
  en balayant **toutes** les chaînes de `evidence.data` à profondeur bornée plutôt
  qu'une liste de noms de clés : une liste de clés finit toujours par rater le
  producteur suivant.

## Automatisations, budgets et alertes (Lot F)

### Déduplication et planificateur

- Création de routine, déclenchement manuel et rotation de webhook exigent une clé
  d'idempotence ASCII visible et bornée. Une clé est scoppée au principal quand
  l'identité utilisateur compte ; sa réutilisation avec un autre corps répond `409`.
- Une occurrence planifiée est identifiée par une `fire_key` dérivée de la routine et
  de l'instant nominal UTC. L'index unique en base décide entre deux écritures
  concurrentes ; une vérification en mémoire n'est jamais la garantie finale.
- Le bail singleton du planificateur dure 45 secondes. Son `fencing_token` augmente à
  chaque reprise et est revérifié sous verrou entre les transactions. Un détenteur
  expiré ne peut pas continuer à matérialiser des missions.
- Le rattrapage `skip` écrit un refus durable et `run_once` lance au plus une
  occurrence. La limite de concurrence se traduit également par un résultat durable
  sans mission, afin que l'absence d'effet soit auditable.
- Une configuration illisible produit un message générique, avance son curseur et ne
  bloque pas les routines suivantes. Après trois échecs terminaux consécutifs, la
  routine est désactivée et une alerte est ouverte.

### Webhook entrant

- Le secret est généré côté client, encodé en base64url et doit représenter au moins
  256 bits. Le serveur persiste SHA-256 et compare les empreintes en temps constant ;
  le secret brut n'entre ni dans le journal de rotation, ni dans les événements.
- Le secret n'est présent que dans la réponse de rotation qui le reçoit. Une lecture
  ultérieure expose uniquement l'état, la date et le chemin ; une nouvelle rotation
  ou une désactivation invalide la précédente.
- Le déclenchement transporte le secret dans `Authorization: Bearer`, jamais dans
  l'URL. Le corps `payload` et l'`event_id` ne sont pas recopiés dans les événements ;
  l'identifiant sert uniquement à la déduplication.
- Le processus API limite cette route à 120 requêtes par minute et par adresse TCP.
  Ce compteur local, borné à 10 000 clients, réduit les abus accidentels mais ne se
  coordonne pas entre réplicas et ne remplace pas une politique distribuée en bordure.
- Tous les corps HTTP sont plafonnés à 1 Mio avant désérialisation, sauf import ou
  révision de skill (32 Mio) et téléversement de livrable, qui est lu en flux puis
  soumis à son propre plafond de 200 Mio et au quota de tentative. Les longueurs
  contradictoires ou invalides sont refusées.
- La route ne dispose pas encore d'une allowlist d'émetteurs ni d'une signature du
  corps. Elle ne doit pas être exposée directement sur Internet sans contrôle de
  bordure et HTTPS.

### Budget et stockage

- Le permis et le rapport de consommation exigent le Bearer worker, le lease actif et
  `X-Attempt-Fencing-Token`. Le ledger déduplique `permit_id` et `report_id` et refuse
  qu'un identifiant stable change de contenu.
- L'absence d'une mesure exigée par un plafond reste `unknown` et refuse le permis.
  Une estimation ne suffit pas à prouver un dépassement ; un dépassement mesuré après
  l'appel reste compté et bloque les permis suivants. Les coûts sont stockés en
  décimal et le jour comptable du permis est conservé jusqu'au rapport.
- L'exécuteur du Lot G possède un point de spawn unique : demander les deux CLIs est
  refusé et ACP lance au plus une invocation CLI de premier niveau. La preuve
  `spawned_agents=1` ne mesure pas les processus ou agents descendants ; elle ne peut
  donc pas démontrer le plafond global `max_spawned_agents_per_run`. Aucun fan-out
  dynamique n'est fourni.
- Une saturation du disque ou du spool répond `507`; une indisponibilité répond
  `503`. L'alerte et l'événement associés ne révèlent ni chemin local ni exception
  brute. Le stockage reste néanmoins un répertoire local sans quota OS réservé, sans
  réplication et sans adaptateur objet éprouvé.

### Frontières du Lot G : GLB, ComfyUI, agents et E2E

- Un GLB ne devient affichable que si le type, l'extension, la signature, la version,
  les longueurs et l'ordre des chunks concordent. Le JSON est strict et borné ; URI
  externes, chunks inconnus et décodeurs Draco/Meshopt/Basisu sont refusés. Le marqueur
  de validation est le sha256 du contenu exact, donc une ancienne métadonnée ne suffit
  pas à promouvoir un blob historique. Le blob n'est pas re-haché à chaque requête
  `Range`, afin qu'une plage minuscule ne déclenche pas jusqu'à 200 Mio de lecture :
  après l'ingestion atomique, l'intégrité du répertoire privé reste donc dans la base
  de confiance opérationnelle et doit être surveillée par le stockage.
- Les buffers/vues/accessors sont vérifiés jusque dans leurs offsets absolus et spans
  stridés, avec budgets cumulés de décodage et de copies ; le sparse est refusé. Les
  images PNG/JPEG/WebP ont une source unique, un MIME/conteneur cohérent, des dimensions
  lues sans décompression, puis des plafonds cumulés compressés, pixels et RGBA+mipmaps.
  Ces limites n'isolent toutefois pas le décodeur ou le GPU du navigateur.
- L'origine d'aperçu est comparée à une `ACP_API_URL` obligatoirement explicite et à
  toutes les origines CORS. Une absence, collision ou URL dangereuse échoue avant
  insertion du lien signé. Le client revérifie encore HTTPS/loopback et la différence
  avec l'application.
- ComfyUI est joignable seulement côté gateway authentifié. Son origine et son workflow
  sont des configurations opérateur, jamais des entrées de requête. Le client refuse
  HTTP distant, redirections et proxies ambiants ; il borne workflow, JSON, polls,
  timeout et image, puis vérifie les métadonnées de chemin et la signature binaire.
  L'idempotence LRU/TTL n'est pas durable : elle réduit les rejeux process-local sans
  garantir l'exactly-once après redémarrage. À capacité simultanée maximale, une
  nouvelle clé est refusée en `429` avec `Retry-After` avant tout appel `/prompt` ; le
  rejeu d'une clé déjà en vol continue à partager le même résultat.
- Une racine projet peut contenir du texte hostile destiné à détourner un agent. La
  défense est capacitaire : mission supervisée et bornée, exactement une racine de cwd,
  configuration/règles utilisateur ignorées côté Codex, outils Claude limités,
  web/MCP/plugins/multi-agent coupés, aucun secret ambiant et aucun dialogue
  d'approbation. Ce contrôle réduit l'impact ; il ne rend pas le contenu fiable et ne
  restreint pas les autres fichiers lisibles par le compte worker.
- Exécutables, dossiers d'authentification, `PATH` d'outils et racines projet doivent
  être absolus, existants et sans chevauchement. Le profil Codex refuse tout
  `AGENTS.md`; le prompt passe par stdin et les sorties brutes ne sont pas persistées.
  Leur identité n'est toutefois pas épinglée entre validation et spawn : leurs ACL et
  répertoires parents doivent interdire toute substitution concurrente.
- Une capacité Codex/Claude explicitement annoncée ou déjà persistée doit encore avoir
  son backend actif, un scope projet et sa racine allowlistée avant tout accès à l'API ;
  le scope global agent est refusé. Les capacités génériques exigent le runner fixe et
  un scope hérité absent échoue également avant réseau. Les écritures Codex visant une
  même racine sont sérialisées entre processus par un verrou adjacent dont l'attente
  consomme la deadline. Un nettoyage incertain publie une quarantaine `.poison` atomique
  et jamais levée automatiquement. Ce mécanisme reste coopératif : protéger son parent
  par ACL et valider la sémantique des partages réseau, ou fournir des worktrees séparés.
- Le lanceur nominal du harnais E2E sort avant de résoudre Playwright sans opt-in exact.
  Le script de collecte directe peut charger le framework, mais la spec reste ignorée
  et aucun navigateur n'est lancé. Sous opt-in, le parcours refuse HTTP distant,
  origines inattendues et toute redirection : chaque requête admise est envoyée une fois
  par un contexte HTTP isolé et borné à 30 secondes, avec retries et suivi coupés, et tout
  `3xx` est bloqué avant le navigateur. Le forwarder reprend les en-têtes de cookies réellement décidés par
  Chromium ; son jar Node ne peut donc pas contourner `SameSite` ni la politique tiers.
  Le vrai
  `POST /auth/login` n'est donc ni retenté ni suivi et une seconde tentative est bloquée ;
  sa réponse non modifiée est remise après contrôle de ses propres en-têtes CORS. Une vraie `OPTIONS`,
  hors du routage du contexte, vérifie séparément la réponse CORS credentialed du serveur
  lorsque les origines diffèrent.
  Les service workers et les constructeurs `Worker`/`SharedWorker`, `WebTransport`,
  `RTCPeerConnection`/`webkitRTCPeerConnection` et `WebSocketStream` sont bloqués avant
  le code applicatif. `EventSource` est également neutralisé : le Studio exerce son vrai
  repli par polling, ce qui permet d'envoyer chaque requête HTTP via un transfert réel
  sans redirection ni retry, mais laisse le SSE hors de cette preuve. Trace/vidéo sont
  coupées. Ces choix signifient que ce parcours ne valide pas le comportement fonctionnel
  d'une application dépendant de workers ou de son direct SSE. La route Playwright reste
  une frontière applicative, pas un pare-feu OS : les optimisations spéculatives internes
  du navigateur doivent être contenues par la politique réseau externe du runner.
  Les identifiants de test restent néanmoins des secrets vivants : ils doivent désigner
  un compte dédié, à privilèges minimaux et à durée limitée.

### Alertes et préférences

- Une contrainte unique partielle autorise une seule alerte ouverte par cause et par
  projet, y compris sous concurrence. La sévérité ne peut que monter ; un acquittement
  compare-et-échange et ne produit pas deux événements au rejeu.
- Les préférences appartiennent au couple projet/utilisateur. Elles filtrent la boîte
  personnelle au niveau de la requête sans masquer la cause pour les autres membres
  ni modifier l'alerte canonique.
- Le seul canal est `in_app`. Aucun courriel, SMS, notification système ou webhook
  sortant n'est implicitement promis.

Les routes, contrats et limites fonctionnelles sont détaillés dans
[Automatisations, budgets et alertes](automations.md).

## Écarts bloquants

### Identité et autorisation

- Les routes utilisateur principales sont protégées et scoppées, mais aucune matrice
  exhaustive ne couvre encore chaque relation enfant, événement, fichier, export et
  future route de plugin.
- Le propriétaire global possède volontairement un pouvoir d'administration large ;
  sa journalisation, les changements de membership et les actions sensibles doivent
  encore recevoir un audit d'autorisation complet.
- Le CLI ouvre et conserve sa propre session cookie/CSRF ; il n'existe pas encore de
  jeton utilisateur court et scoppé dédié aux usages non interactifs.
- La limitation des tentatives de connexion, la récupération de compte et une
  politique de mot de passe d'exploitation ne sont pas livrées.

### Réseau, événements et navigateur

- La configuration CORS de production, les méthodes/en-têtes permis et le modèle
  d'authentification restent à tester ; CORS ne constitue pas un contrôle d'accès.
- Le flux navigateur authentifié, scoppé, séquencé et rejouable existe depuis le
  Lot E, mais il est servi par l'API métier : le service d'événements conserve ses
  sockets en mémoire, son ingestion interne reste authentifiée et son WebSocket
  anonyme reste fermé par défaut. Ces deux voies coexistent ; la seconde n'est pas une
  voie utilisateur.
- Aucune origine séparée n'est **configurée** pour les aperçus de contenu non fiable.
  `ACP_ARTIFACT_PUBLIC_ORIGIN` existe et est lue par le code ; tant qu'elle est vide ou
  invalide, l'API refuse l'aperçu en `424` avant de signer. Il reste à déployer et
  vérifier réellement cette seconde origine avant toute exposition réseau du Studio.
- Le CSRF et la politique de cookie sont couverts localement ; CSP, HSTS, autres
  en-têtes de sécurité, valeurs de plafonds et configuration HTTPS restent à valider
  en déploiement.

### Exécution, secrets et stockage

- Le jeton d'enrôlement worker est lié côté API à **un seul** périmètre configuré :
  `ACP_WORKER_REGISTRATION_PROJECT_ID` ou
  `ACP_WORKER_REGISTRATION_GLOBAL_ACCESS=1`. Le corps doit annoncer exactement ce
  périmètre ; une configuration absente/ambiguë répond `503` et une tentative
  d'élévation répond `403`. Le jeton reste toutefois réutilisable tant que
  l'opérateur le laisse configuré : il faut le retirer ou le faire tourner après les
  enrôlements prévus. Une ancienne identité sans périmètre est mise en quarantaine.
- Le périmètre projet est inclus dans la requête SQL avant le claim d'une tâche et
  revérifié dans la réservation atomique de capacité. Seul un worker global peut
  prendre le bail du planificateur. Pour les probes MCP `stdio`, une cible choisie
  explicitement est réservée à ce worker exact ; la file non ciblée est réservée aux
  workers globaux. Le passage `queued` → `claimed` est arbitré avant toute résolution
  de secret et ne divulgue le payload qu'à un seul claimant.
- Le backend local réel est configuré, borné et testable, mais il conserve les droits
  du compte worker et n'impose ni sandbox OS ni politique réseau forte. Il refuse
  tout mode non supervisé et toute liste d'actions non vide. Le backend à commande
  fixe refuse les ressources en écriture, faute de pouvoir appliquer cette promesse ;
  l'exécuteur Codex peut accepter une racine `write` explicitement déclarée, tandis
  que Claude reste limité à `Read,Glob,Grep`. Le Job Object Windows borne l'arbre de
  processus ; il ne borne ni les droits, ni le réseau, ni les quotas, et n'a pas
  d'équivalent livré sur POSIX.
- `spawned_agents=1` signifie qu'ACP a lancé une seule invocation CLI de premier niveau ;
  `spawned_agents_scope=worker_managed_top_level_cli_only` encode cette limite et la
  métrique ne voit pas ses descendants. La racine projet fixe le cwd et non les
  droits OS : des projets non mutuellement fiables doivent utiliser des workers,
  comptes, conteneurs ou VM séparés avec un filtrage réseau externe.
- L'autorisation d'un lancement `stdio` vit dans le centre MCP
  (`mcp_probes.authorization`) et n'est pas reliée au circuit d'approbation des
  missions : deux mécanismes d'approbation coexistent, avec des journaux distincts.
- Les sorties stdout/stderr persistées comme preuves sont bornées mais non expurgées.
  La racine des runs doit être protégée et aucun secret ne doit être allowlisté vers
  un programme susceptible de l'imprimer.
- Les origines qui reçoivent les Bearers gateway, événements, Hermes ou worker sont
  validées : HTTP uniquement sur loopback, HTTPS ailleurs, sans userinfo, chemin,
  query ni fragment. Ces clients internes ignorent aussi les variables proxy de
  l'environnement afin qu'un Bearer loopback ne soit pas détourné par `HTTP_PROXY`.
- Le coffre du Lot D couvre les secrets d'extensions (MCP), pas les secrets de
  service : `HERMES_API_KEY`, `ACP_GATEWAY_SERVICE_TOKEN` et `ACP_EVENT_SERVICE_TOKEN`
  restent des variables d'environnement. Les clés Fernet elles-mêmes vivent dans
  `ACP_SECRETS_KEYS` : il n'y a ni KMS, ni HSM, ni rotation planifiée, et la procédure
  de rotation est manuelle.
- Le stockage privé des livrables, les URLs signées bornées et révocables et le
  contrôle de téléchargement existent depuis le Lot E, mais le stockage est un
  **répertoire local** : sur un hébergeur il exige un volume persistant, et aucun
  adaptateur de stockage objet n'est livré. Les clés de signature vivent dans
  `ACP_ARTIFACT_SIGNING_KEYS`, comme les clés du coffre : ni KMS, ni HSM, ni rotation
  planifiée.
- Les sorties stdout/stderr d'une exécution de tests sont expurgées des valeurs
  injectées ; celles du runner de mission du Lot C ne le sont toujours pas.
- Les migrations PostgreSQL, sauvegardes, restaurations et procédures de rotation
  ne sont pas livrées. La migration additive de `events.sequence` et
  `events.journal_seq` est propre à SQLite : une base PostgreSQL **existante** ne la
  reçoit pas.

## Politique cible

### Sessions et rôles

Le premier démarrage crée un propriétaire par un secret à usage unique ou un flux
local explicitement borné ; aucune inscription publique n'est ouverte. Les sessions
sont stockées côté serveur, révocables, expirables et renouvelées avec rotation.
Les cookies web sont `HttpOnly`, `Secure` en production et `SameSite` adapté ; les
clients non navigateur utilisent des jetons courts et scoppés.

| Rôle | Portée cible |
|---|---|
| Propriétaire | configuration de l'espace, connexions, membres, politiques et actions sensibles |
| Opérateur | projets autorisés, missions, approbations permises et artefacts associés |
| Lecture seule | consultation des objets explicitement autorisés, aucune exécution ni secret |

Le contrôle porte sur l'organisation/espace et le projet à chaque requête, flux et
objet. Une ressource enfant est résolue côté serveur avant la décision ; le client
ne choisit pas librement son scope.

### Autonomie et approbations

Trois niveaux sont visibles : lecture, travail en environnement isolé, actions
sensibles sur validation. Une approbation contient l'action canonique, la cible, les
conséquences, la portée, l'empreinte des paramètres et une expiration. Toute
modification invalide l'approbation. Un refus, une expiration et un arrêt produisent
un état durable et un événement d'audit.

### Runners et événements

- enrôlement par jeton limité et à usage borné, identité propre, révocation et
  rotation ;
- connexion sortante authentifiée, lease par tentative, renouvellement et fencing
  token monotone ;
- utilisateur non privilégié, répertoire canonique, limites de temps/ressources et
  politique réseau ; aucun socket Docker hôte ;
- enveloppe d'événement signée ou authentifiée, schéma versionné, séquence,
  idempotence et vérification run/tentative/projet ;
- transaction métier et outbox, puis diffusion authentifiée et reprise par curseur.

### Contenus et intégrations non fiables

- Les fichiers, dépôts, README, skills, réponses MCP et sorties de modèle sont des
  données non fiables et ne peuvent modifier les politiques.
- Les chemins sont résolus dans une racine autorisée ; archives, liens et fichiers
  spéciaux sont contrôlés avant extraction.
- Les contenus HTML, SVG et traces restent en téléchargement forcé. Les seuls aperçus
  image, vidéo et GLB validé utilisent une origine séparée avec les en-têtes appropriés.
- Les connexions sortantes contrôlent SSRF, redirections, DNS rebinding, adresses
  privées et métadonnées cloud côté serveur et runner.
- Les secrets sont référencés, injectés au dernier moment et absents des URL, logs,
  événements, réponses frontend et exports.

## Validation restant requise avant exposition réseau

- E2E navigateur de bootstrap, reconnexion, expiration, révocation et CSRF sur les
  services réellement démarrés ;
- matrice RBAC exhaustive par route, projet, flux et fichier, en complément des tests
  inter-projets négatifs déjà présents ;
- compléter les tests de concurrence lease/fencing par une validation multi-processus ;
- placer le webhook entrant derrière HTTPS, une limitation de débit distribuée et une
  politique de bordure, puis tester rotation et rejeu depuis un émetteur réel ;
- rejouer les contrôles SSRF, traversée de chemins et archive malveillante contre un
  serveur MCP, un dépôt et une archive réels (les suites actuelles utilisent des
  transports simulés et des sources locales), et compléter par XSS et limites
  d'upload ;
- rotation des clés de service, révocation runner et absence de secrets dans les
  journaux ;
- rejouer les contrôles de livrables et de liens signés derrière une **origine
  d'aperçu séparée réellement configurée** : les tests prouvent le refus `424`, la
  séparation d'origine, les GLB invalides et les liens expirés/révoqués, mais aucun
  navigateur ni second domaine n'a servi le contenu ;
- exécuter une vraie suite Playwright sur un runner réel : la chaîne reporter → worker
  → API est prouvée sur un programme déterministe, jamais sur un navigateur ;
- éprouver la reprise du flux sur une coupure réseau réelle et depuis un `EventSource`
  de navigateur : la reprise par curseur sans perte ni doublon est couverte par la
  suite API (`apps/api/tests/test_events_stream.py`), pas par un parcours réel ;
- analyse statique, audit de dépendances et revue de configuration de production ;
- restauration testée sur une copie de données.

## État réel

### Réalisé/vérifié

- Les comportements fail-closed historiques du worker/gateway et du provider manuel,
  ainsi que les écritures worker critiques, restent couverts ; les nombres de la
  release courante sont consignés dans le rapport d'acceptation.
- La réconciliation d'un lease expiré, le fencing par tentative et l'arrêt de
  l'arbre d'un processus local réel sont couverts par des tests déterministes ;
  l'absence de double effet externe sur un outil tiers n'est pas démontrée.
- La séparation des clients empêche la transmission accidentelle du Bearer worker au
  provider-gateway.
- Le bootstrap, les sessions, l'expiration/révocation, le CSRF, l'isolation de
  conversations et les rôles projet sont couverts dans la suite propre du Lot B.
- Les frontières gateway/event-service refusent un appel sans Bearer interne valide,
  et le WebSocket anonyme est fermé par défaut.
- Le lockfile Node versionné utilise Vite `8.3.0` et Vitest `5.0.0` ; un `npm ci`
  propre suivi de `npm audit` ne signale aucune vulnérabilité connue au moment de la
  préparation de `0.3.0`.
- Le coffre (chiffrement, rotation de clé, portées, absence de valeur dans les
  réponses et les événements), la politique de sortie (loopback, réseaux privés,
  métadonnée cloud, IPv6, réponses DNS mixtes, redirections, corps trop grand,
  épinglage) et l'expurgation des contenus renvoyés par un serveur MCP bavard sont
  couverts par des tests déterministes côté API et côté worker.
- Le parcours MCP complet (déclaration, diagnostic HTTP et `stdio` autorisé,
  rattachement limité à un sous-ensemble d'outils, activation, révocation) et le
  parcours skills (import borné, relecture, approbation d'une portée accrue,
  rattachement, révocation) sont testés, y compris les refus RBAC inter-projets.
- Le transport `http` a été rejoué contre des services réellement démarrés (API dans
  son propre processus, serveur MCP Streamable HTTP sur le bouclage inscrit dans
  l'allowlist auditée) : le secret déchiffré atteint bien le serveur, et n'apparaît ni
  dans les réponses d'API, ni dans la découverte persistée, ni dans l'export.
- L'arrêt d'un arbre de processus sous Windows est prouvé par des tests qui échouaient
  auparavant avec un lanceur d'environnement virtuel, et qui passent désormais sur
  trois exécutions consécutives.
- Le flux SSE authentifié (RBAC revérifié à chaque page, fermeture après révocation de
  session, refus inter-projets, reprise par `Last-Event-ID` sans perte ni doublon,
  limite de connexions par utilisateur) est couvert par
  `apps/api/tests/test_events_stream.py`.
- Le contrôle des livrables (idempotence par sha256, quota par tentative, taille
  maximale, `Range`, en-têtes de sécurité, HTML/SVG/archives forcés en téléchargement,
  lien expiré, révoqué ou étranger refusé, absence de clé ⇒ `503`) est couvert par
  `apps/api/tests/test_artifacts_content.py` et `test_artifact_signing.py`.
- Le refus d'un faux succès de tests (rapport vide, fencing obsolète, arrêt d'arbre non
  prouvé, pièce jointe hors répertoire, code de sortie du rapport ne pouvant pas
  effacer celui mesuré) est couvert par `apps/api/tests/test_testing_service.py` et
  `apps/worker/tests/test_web_tests.py`.
- Les suites ciblées du Lot F couvrent les bascules DST, la contrainte unique de tir
  sous concurrence SQLite, les baux/fences, le rattrapage, la concurrence des
  routines, l'idempotence des webhooks, le ledger budgétaire et la déduplication des
  alertes. Le total global final de `0.7.0` n'est pas anticipé dans ce document.
- Les erreurs physiques du stockage sont classées `saturated` ou `unavailable`, sans
  chemin dans les réponses, alertes ou événements ; un blob adressé par contenu dont
  les octets ne correspondent plus à sa clé est réparé atomiquement au rejeu.

### Réalisé, non testé réel

- L'adaptateur Hermes conserve son secret côté serveur par conception, mais aucune
  connexion Hermes réelle n'a été effectuée.
- Le web utilise une session cookie/CSRF réelle dans les tests API et TypeScript,
  mais le parcours complet n'a pas encore été rejoué dans un navigateur contre les
  services et une instance Hermes réellement lancés.
- **Aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été exécuté**
  pour cette version : le reporter/worker est prouvé sur des objets et un programme
  synthétiques, tandis que le harnais E2E réel est resté désactivé. Les contrôles sur
  le contenu produit par un test n'ont donc jamais rencontré un fichier Playwright réel.
- Le validateur GLB et `model-viewer` sont couverts séparément sans rendu WebGL ni
  origine d'aperçu déployée. ComfyUI est couvert par un transport simulé. Les chemins
  Codex/Claude lancent des exécutables contrôlés, pas un CLI authentifié.
- Le flux SSE n'a été exercé que par un client de test : aucune coupure réseau réelle,
  aucun proxy intermédiaire, aucun `EventSource` de navigateur.
- Les trois tests de refus de lien symbolique du Lot E étaient **ignorés** dans la
  vérification Windows publiée de `0.6.0` (privilège de création indisponible) : ce
  contrôle n'y était donc pas prouvé.
- Le planificateur, les budgets et les webhooks ont été exercés avec des composants de
  test locaux ; aucun worker distant, webhook Internet, fournisseur payant ni effet
  externe n'a été utilisé.

### Non configuré

- matrice RBAC exhaustive et journal d'administration ;
- gestion des clés du coffre **et des clés de signature de liens** par un KMS/HSM, et
  rotation planifiée ;
- CORS de production, HTTPS/HSTS, CSP de l'application et **origine d'aperçu séparée**
  (`ACP_ARTIFACT_PUBLIC_ORIGIN` reste vide ; les en-têtes de contenu d'artefact, eux,
  sont livrés et testés) ;
- sandbox OS et politique réseau du runner, endpoint worker pour les approbations ;
  la clôture d'arrêt Windows est livrée, l'isolation ne l'est pas, et POSIX n'a pas
  d'équivalent au Job Object ;
- rattachement de l'autorisation `stdio` au circuit d'approbation des missions ;
- certification d'un skill : le contrôle automatique reste une heuristique indicative,
  sans signature vérifiée ni analyse en bac à sable ;
- adaptateur de stockage objet distant : l'interface `ArtifactStorage` existe, seul
  l'adaptateur disque local est livré ;
- purge de rétention planifiée : la commande existe et est testée, aucun ordonnanceur
  ne l'exécute ;
- runner de tests web réel : `ACP_WORKER_WEBTEST_*` n'est configuré sur aucune machine,
  et la capacité `web_tests` n'a jamais été annoncée par un worker réel ;
- cible et secrets du harnais `ACP_E2E=1`, instance ComfyUI, profils agents de test et
  origine d'aperçu réellement routée ;
- outbox : le flux relit la base par curseur au lieu de s'appuyer sur un relais, mais
  aucune outbox transactionnelle n'a été livrée.
- limitation de débit distribuée et signature de corps pour le webhook entrant ; le
  compteur local par processus, le secret aléatoire et la déduplication ne remplacent
  pas ces contrôles de bordure ;
- PostgreSQL/Alembic, sauvegarde/restauration, supervision et déploiement Railway ;
- fan-out et comptabilité multi-agent dynamiques ; le Lot G borne seulement à une
  l'invocation CLI de premier niveau gérée par ACP, sans observer ses descendants.

### Restant

Les prochaines tranches doivent isoler plus fortement le runner et raccorder ses
demandes d'approbation. Elles doivent aussi compléter la matrice de scopes, déployer et
vérifier une origine d'aperçu séparée, exécuter une vraie suite Playwright, ComfyUI et
un CLI agent sur des cibles jetables, livrer le courtier d'appels d'outils MCP pendant
une mission, les migrations et la restauration. Tant que ces points ne sont pas
testés, le produit reste réservé au développement local sur une machine de confiance.
