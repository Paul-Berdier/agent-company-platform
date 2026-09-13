# Threat model — état du Lot E

Date d'état : 13 septembre 2026 — version `0.6.0`. Ce document décrit les menaces
par actif et les mesures **réellement en place**. Les mesures qui n'existent pas sont
nommées comme telles ; la vue d'ensemble des frontières est dans
[docs/security.md](../security.md).

Avertissement valable pour toute la section « Lot E » : **aucun navigateur réel n'a
été lancé et aucun test Playwright réel n'a été exécuté** pour cette version. Les
mesures décrites sont prouvées sur des objets synthétiques et un programme
déterministe, jamais contre une vraie exécution de navigateur.

## Assets sous licence (LimeZu)

**Risque** : redistribution involontaire d'assets payants via le dépôt public,
un build publié ou un artefact CI.

Mesures en place :

- `.gitignore` couvre `Limzu/`, `local-assets/`, `licensed-assets/`,
  `apps/web/public/assets/licensed/`, `*.aseprite` ;
- le script d'import **refuse d'écrire** vers une cible non couverte par le
  `.gitignore` (vérification `isPathIgnored`, testée) ;
- test automatisé : les chemins d'import sont ignorés par git, les
  placeholders ne le sont pas ;
- les archives sources vivent hors du dépôt (`C:\AgentCompanyAssets\LimeZu`) ;
- `PROVENANCE.md` + `import-report.json` tracent origine, licence et date.

Règles opérationnelles :

- ne jamais committer `dist/` ni publier de build en artefact téléchargeable
  public ; servir l'app est un usage normal, offrir les fichiers au
  téléchargement n'en est pas un ;
- la CI et les tests ne dépendent que des placeholders libres.

## Périmètre applicatif local

- Authentification utilisateur : bootstrap propriétaire unique, mot de passe
  Argon2id, session serveur opaque révocable/expirable, cookie `HttpOnly`, CSRF et
  rôles par projet. La matrice RBAC de toutes les ressources enfant et les contrôles
  d'exploitation restent à compléter avant la production.
- Authentification worker : enrôlement protégé par
  `ACP_WORKER_REGISTRATION_TOKEN`, jeton aléatoire distinct par worker,
  stockage serveur SHA-256 avec pepper optionnel, comparaison constante et
  expiration à 30 jours. Réenregistrer un même nom révoque de fait son ancien
  jeton. Le jeton brut n'est jamais journalisé.
- Présence et attribution : heartbeat à 15 s, worker hors ligne après 45 s,
  lease renouvelable par task run, concurrence bornée et filtrage strict par
  `required_capabilities`.
- Exécution locale : le mode réel n'accepte qu'un exécutable absolu via un argv
  fixe configuré par l'opérateur, sans shell ni commande provenant d'une mission.
  Chaque tentative a un cwd neuf, une enveloppe allowlistée, un environnement
  minimal, des limites et un fencing token. Le processus conserve toutefois les
  droits OS et réseau du compte worker : ce backend n'est pas une sandbox.
- Le frontend ne peut déclencher aucune commande arbitraire : uniquement des
  endpoints métier typés.
- Hermes et tout orchestrateur externe : jamais d'accès direct à la base ;
  passage obligatoire par le gateway avec contrats versionnés ; le contexte
  d'un projet n'est jamais transmis à un autre.
- Secrets de service : variables d'environnement (`HERMES_API_KEY`, Bearers
  inter-services) et fichiers d'état locaux à protéger. Les clients refusent HTTP hors
  loopback et les origines ambiguës avant d'envoyer un secret, et ignorent les
  variables proxy de l'environnement. Les secrets ne sont pas volontairement
  journalisés, mais stdout/stderr du programme enfant sont des contenus arbitraires,
  persistés et non expurgés : aucun secret ne doit lui être allowlisté.

Restent requis avant l'exécution de code non fiable : isolation OS et réseau, compte
non privilégié, verrouillage des ressources, quotas, rate limiting, audit complet et
approbations humaines pour les opérations sensibles.

## Extensions contrôlées (Lot D)

### Valeur d'un secret d'extension

**Risque** : une clé d'API confiée à la plateforme fuit par une réponse d'API, un
export, un événement, un journal ou l'interface.

Mesures en place :

- chiffrement au repos (Fernet) et stockage d'une **référence** dans la configuration
  d'un serveur MCP ; le contrat lui-même ne sait pas porter une valeur ;
- déchiffrement limité à deux appels autorisés : en-têtes d'un diagnostic HTTP exécuté
  par l'API, variables d'environnement remises à un runner authentifié lors du claim
  d'un diagnostic `stdio` approuvé (réponse `Cache-Control: no-store`) ;
- rotation de clé sans perte par `ACP_SECRETS_KEYS` ; coffre absent ⇒ état explicite
  `configured=false` et `503`, jamais un stockage en clair de repli ;
- le CLI refuse `--value` en argument et n'accepte que `--value-stdin` ;
- une valeur littérale ressemblant à un secret est refusée (`422`) à l'enregistrement
  d'un serveur, avec l'action à effectuer.

Écart restant : les clés Fernet vivent dans une variable d'environnement (pas de
KMS/HSM, pas de rotation planifiée), et les secrets de service (`HERMES_API_KEY`,
Bearers inter-services) restent hors coffre.

### Serveur MCP bavard

**Risque** : un serveur interrogé réécrit la valeur qu'on lui a transmise dans
`serverInfo`, une capacité, la description ou le schéma d'un outil, sur `stderr` ou
dans un message d'erreur — contenu ensuite persisté et servi à tout utilisateur
authentifié.

Mesures en place : expurgation des valeurs injectées avant écriture en base, par le
runner **et** par l'API, selon une règle unique (`acp_contracts.redaction`) appliquée
aux deux transports ; toute valeur non vide est masquée, sans plancher de longueur ;
au-delà d'une profondeur bornée, la branche non examinée est remplacée par le marqueur
plutôt que retournée telle quelle.

Écart restant : l'expurgation porte sur les valeurs connues de la plateforme. Un
serveur qui dérive une valeur (encodage, troncature, hachage) n'est pas couvert.

### Sortie réseau de l'API (SSRF)

**Risque** : une URL fournie par un utilisateur fait interroger un service interne, la
métadonnée d'instance cloud ou un hôte privé.

Mesures en place : schémas `http`/`https` seulement, `http` refusé hors allowlist,
userinfo refusé, contrôle de **toutes** les adresses résolues (une seule bloquée suffit
à refuser, ce qui couvre les réponses DNS mixtes), épinglage de l'adresse pendant la
requête (`Host` et SNI conservés), revalidation intégrale des redirections (3 au
maximum), corps borné, variables proxy de l'environnement ignorées. Bouclage, réseaux
privés, link-local dont `169.254.169.254`, multicast, réservé, CGNAT, ULA IPv6,
`fe80::/10`, IPv4-mapped, 6to4 et Teredo sont bloqués. Une allowlist privée ciblée
reste possible et **chaque usage produit un événement d'audit**.

Écart restant : les contrôles sont prouvés sur transports simulés et résolveur injecté,
pas contre un serveur tiers réel ; le runner applique sa propre allowlist d'exécutables
mais pas de politique réseau.

### Lancement d'un programme `stdio` sur un runner

**Risque** : la déclaration d'un serveur MCP devient une exécution de code arbitraire
sur la machine d'un runner.

Mesures en place : rien n'est lancé sans une autorisation explicite portant l'action,
la cible (commande et arguments), les conséquences, la portée (runner désigné),
l'empreinte exacte de la révision et une expiration d'une heure ; une révision modifiée
invalide l'autorisation ; côté runner la capacité est désactivée par défaut et exige
une allowlist d'exécutables absolus comparée après résolution du chemin ; aucun shell ;
environnement minimal sans héritage des variables du worker ; durée et sorties bornées ;
arbre de processus enfermé dans un Job Object Windows dès la création.

Écarts restants : le programme conserve les droits OS du compte worker — le job est une
clôture d'arrêt, pas une isolation ; POSIX n'a pas d'équivalent livré ; cette
autorisation n'est pas reliée au circuit d'approbation des missions.

### Contenu importé (configuration MCP, skill, schéma d'outil)

**Risque** : un contenu importé se comporte comme une instruction (injection de prompt)
ou sort de son répertoire (traversée d'archive).

Mesures en place : contenus bornés, affichés **comme texte** et jamais rendus ; aucun
effet sur une politique, un droit ou une instruction système ; extraction contrôlée
(chemins relatifs normalisés, `..` refusé, liens et fichiers spéciaux refusés, limites
en nombre et en taille) ; dossier local importable seulement s'il est explicitement
allowlisté ; import GitHub opt-in avec commit épinglé par SHA ; lecture de fichier
validée contre le manifeste de la révision, jamais construite depuis l'entrée
utilisateur.

Écart restant : le contrôle automatique d'un skill est une **heuristique indicative** —
il signale `eval`, `curl | sh`, chemins sensibles, caractères Unicode invisibles et
formulations d'injection, mais il ne certifie rien et ne remplace pas une relecture.

## Flux, livrables et tests web (Lot E)

### Journal d'événements et flux temps réel

**Risque** : un utilisateur lit le flux ou le journal d'un projet auquel il n'a pas
accès ; une session révoquée continue de recevoir des événements sur une connexion déjà
ouverte ; une reconnexion perd, duplique ou réordonne des événements et fait croire à un
état qui n'existe pas.

Mesures en place :

- le flux est servi par l'**API métier**, seule détentrice de la base, des sessions et
  du RBAC ; `apps/event-service` reste un relais interne et son WebSocket anonyme reste
  fermé par défaut ;
- le projet est résolu **côté serveur** à partir de la tentative : un `project_id`
  fourni par le client n'élargit jamais la portée ;
- l'autorisation n'est pas résolue une seule fois à l'ouverture, elle est revérifiée à
  chaque page : une révocation de session ou une perte de membership ferme la connexion
  au plus tard à l'interrogation suivante, avec une trame de fermeture explicite ;
- la reprise se fait sur un compteur monotone à **ordre total** (`sequence` par
  tentative, `journal_seq` pour le journal), alloué dans la transaction métier — pas sur
  un horodatage, dont la granularité réelle mesurée (environ 1,5 ms) rend les égalités
  courantes et faisait perdre des lignes ;
- une reconnexion ne relance jamais une mission ; l'interface expose
  `connected` / `reconnecting` / `polling` / `offline` et réconcilie par `GET` au lieu
  de supposer « à jour » ;
- connexions simultanées bornées par utilisateur, rotation propre de la connexion et
  en-têtes `no-store` / `X-Accel-Buffering: no`.

Écarts restants : aucune coupure réseau réelle ni `EventSource` de navigateur n'a été
éprouvé ; la migration additive des deux compteurs est propre à SQLite, et une base
PostgreSQL existante ne la reçoit pas.

### Contenu produit par une exécution de tests

**Risque** : un test visite un site tiers hostile, en rapporte un HTML, un SVG, une
trace ou une capture, et ce contenu s'exécute ensuite dans l'origine de la plateforme
avec le cookie de session de l'utilisateur.

Mesures en place :

- le type servi vient d'une **allowlist serveur** (extension + type déclaré), sans
  aucun reniflage : un type non reconnu devient `application/octet-stream` ;
- `text/html`, `image/svg+xml` et les archives — dont la trace Playwright — ne sont
  **jamais** servis en ligne ; `Content-Disposition: attachment` est imposé ;
- toute réponse de contenu porte `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox` et
  `Cache-Control: private, no-store` ;
- le Studio n'utilise ni `iframe`, ni `srcdoc`, ni `innerHTML` pour un contenu venu de
  l'API ; une trace et un rapport HTML sont proposés en téléchargement explicite, avec
  l'avertissement de les ouvrir hors de la plateforme.

Écart restant, le plus important de ce lot : `ACP_ARTIFACT_PUBLIC_ORIGIN` n'est
configurée nulle part. Les aperçus image et vidéo passent donc par un lien signé servi
sur **l'origine de l'API**. Le Studio affiche cet écart, mais un avertissement n'est pas
un contrôle : une telle instance ne doit pas être exposée sur Internet.

### Lien de téléchargement d'un livrable

**Risque** : une URL de fichier partagée ou conservée donne un accès durable, ou donne
accès au livrable d'un autre projet.

Mesures en place : jeton HMAC-SHA256 lié à **l'artefact et au demandeur**, borné à
900 secondes au maximum (300 par défaut), enregistré par empreinte et révocable par son
titulaire ou par un owner du projet du livrable ; clés en liste
(`ACP_ARTIFACT_SIGNING_KEYS`) pour la rotation ; sans clé, la création de lien répond
`503` explicite et le téléchargement par session reste possible ; ni l'existence du lien
ni celle du livrable ne sont énumérables (`404` uniforme) ; aucun projet ne devient
public.

Écarts restants : les clés de signature vivent dans une variable d'environnement (pas de
KMS/HSM, pas de rotation planifiée) ; le compteur d'usage d'un lien est incrémenté mais
n'est exposé par aucune route, donc il n'existe pas de journal de consultation.

### Stockage d'un livrable

**Risque** : un nom de fichier fourni par le processus de test sort du répertoire de
stockage, ou un téléversement sature le disque.

Mesures en place : clé de stockage dérivée du sha256 (`<sha256[0:2]>/<sha256>`) — le nom
d'origine n'entre jamais dans un chemin ; écriture atomique par fichier temporaire du
même volume puis `os.replace` ; identité du worker vérifiée **avant** la lecture du
corps ; plafond par fichier et quota cumulé par tentative appliqués **pendant** le flux,
donc le premier morceau qui dépasse interrompt la lecture ; côté worker, une pièce
jointe n'est téléversée que si sa résolution canonique reste sous le répertoire de
sortie de la tentative, et un refus interdit le verdict `passed`.

Écarts restants : le stockage est un répertoire local, sans quota par projet ni alerte de
saturation ; les trois tests de refus de lien symbolique sont **ignorés** sur la machine
de vérification, faute de privilège de création.

### Secret imprimé par une suite de tests

**Risque** : une suite de tests imprime une variable d'environnement ou un en-tête dans
un message d'erreur, et la plateforme republie cette valeur à tout utilisateur autorisé.

Mesures en place : le processus de test ne reçoit **aucun credential de la plateforme**
— le reporter écrit un NDJSON local et n'effectue aucun appel réseau, et c'est le worker
authentifié qui ingère ce fichier ; messages et extraits passent par `redact_text` /
`redact_data` avec les valeurs injectées par l'opérateur comme liste d'expurgation ; le
reporter ne journalise ni l'environnement ni les en-têtes, tronque à 8 000 caractères et
retire les séquences ANSI.

Écarts restants : comme pour un serveur MCP bavard, une valeur **dérivée** (encodée,
tronquée, hachée) n'est pas couverte ; et un filtre de texte ne masque pas des pixels sur
une capture d'écran — une suite qui saisit un mot de passe à l'écran le montrera.

### Faux succès d'une exécution de tests

**Risque** : une exécution est présentée comme réussie alors qu'elle a échoué, expiré,
laissé des processus vivants, ou n'a rien exécuté du tout.

Mesures en place : le verdict est dérivé des codes de sortie et des compteurs, jamais
d'une image ni d'un résumé ; `passed` exige un code de sortie nul, zéro cas
`unexpected`, `interrupted` et `timedOut`, **et** au moins un cas réellement exécuté ; un
rapport absent ou vide est un échec explicite ; un arrêt d'arbre non prouvé interdit le
succès ; le verdict que l'API dérive des totaux fusionnés ne peut qu'**aggraver** le
verdict local ; le code de sortie annoncé par le rapport ne peut que **signaler** un
échec, jamais effacer celui mesuré par le worker ; `flaky` et `skipped` restent distincts
et affichés, jamais convertis en réussite ou en échec générique. La validation technique
dérivée ne vaut jamais `succeeded` : l'acceptation utilisateur reste séparée.

Écart restant : toute cette chaîne est prouvée sur un lanceur déterministe
(`apps/worker/tests/fake_playwright_runner.py`). Aucune exécution Playwright réelle ne
l'a encore validée, et l'opt-in de test E2E réel prévu par la spécification (`ACP_E2E=1`)
n'existe pas dans le dépôt.

### Reprise en main humaine du navigateur

**Risque** : une prise de contrôle concurrente, non journalisée ou non exclusive perturbe
un test automatisé et fausse son résultat.

Mesure en place : **la capacité n'est pas livrée**. Le Studio est en lecture seule et un
panneau le dit explicitement ; aucun bouton ne laisse croire qu'une action est possible,
et aucune route de contrôle n'existe côté serveur. Le lease exclusif, la suspension de
l'automate et le marquage d'un résultat perturbé restent à concevoir (Lot G).
