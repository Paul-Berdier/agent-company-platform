# Threat model — état du Lot D

Date d'état : 12 septembre 2026 — version `0.5.0`. Ce document décrit les menaces
par actif et les mesures **réellement en place**. Les mesures qui n'existent pas sont
nommées comme telles ; la vue d'ensemble des frontières est dans
[docs/security.md](../security.md).

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
