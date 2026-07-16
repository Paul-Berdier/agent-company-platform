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

- Authentification : header `X-User-Id` de développement, permissions par
  workspace/projet côté API. **Pas de production sans vraie auth + RBAC**
  (prévu Phase 9 avec les workers distants : tokens hachés, expiration,
  allowlist de commandes, protection `../`, rate limiting, audit).
- Le frontend ne peut déclencher aucune commande arbitraire : uniquement des
  endpoints métier typés.
- Hermes et tout orchestrateur externe : jamais d'accès direct à la base ;
  passage obligatoire par le gateway avec contrats versionnés ; le contexte
  d'un projet n'est jamais transmis à un autre.
- Secrets : variables d'environnement uniquement (`HERMES_SERVICE_TOKEN`…),
  jamais en dur ni dans les logs.

Ce document sera étendu à chaque phase (workers, locks, approbations).
