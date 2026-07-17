# Threat model (v0 — MVP)

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

## Périmètre applicatif (MVP local)

- Authentification utilisateur : header `X-User-Id` de développement,
  permissions par workspace/projet côté API. **Pas de production sans vraie
  auth + RBAC**.
- Authentification worker : enrôlement protégé par
  `ACP_WORKER_REGISTRATION_TOKEN`, jeton aléatoire distinct par worker,
  stockage serveur SHA-256 avec pepper optionnel, comparaison constante et
  expiration à 30 jours. Réenregistrer un même nom révoque de fait son ancien
  jeton. Le jeton brut n'est jamais journalisé.
- Présence et attribution : heartbeat à 15 s, worker hors ligne après 45 s,
  lease renouvelable par task run, concurrence bornée et filtrage strict par
  `required_capabilities`.
- Exécution locale : ce socle n'expose aucun endpoint de commande arbitraire.
  Le mode réel échoue fermé tant qu'un exécuteur avec allowlist, racine projet
  canonique et audit n'est pas configuré. La simulation reste explicite.
- Le frontend ne peut déclencher aucune commande arbitraire : uniquement des
  endpoints métier typés.
- Hermes et tout orchestrateur externe : jamais d'accès direct à la base ;
  passage obligatoire par le gateway avec contrats versionnés ; le contexte
  d'un projet n'est jamais transmis à un autre.
- Secrets : variables d'environnement uniquement (`HERMES_SERVICE_TOKEN`…),
  jamais en dur ni dans les logs.

Restent requis avant une exécution réelle : allowlist de commandes, résolution
canonique empêchant `../`, verrouillage des ressources, rate limiting, audit
des commandes et approbations humaines pour les opérations sensibles.
