# Threat model — état du Lot C

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
