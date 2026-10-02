# Contrat partagé `acp_poste_contrat`

Modèles Pydantic partagés par le **poste** (`apps/poste` : poste Windows de P5, exécutant Railway Linux de P6)
et le greffon Hermes **`acp-poste`** (`hermes/plugins/acp-poste`). Une seule source, jamais de copie : le poste
l'installe comme distribution locale (`pip install -e hermes/plugins/acp-poste/contrat`) ;
l'image Hermes le reçoit avec le greffon, puisque tout `hermes/` forme le contexte de
construction de l'image.

## Pourquoi ici

- Le plan (docs/refonte/plan.md) range les modèles Pydantic du greffon dans
  `hermes/plugins/acp-poste/contrat/`. Le contexte de construction de l'image est
  limité à `hermes/` : un contrat laissé dans `packages/` devrait être recopié dans
  l'image, et deux copies finissent par diverger.
- Le poste en dépend comme d'une distribution ordinaire ; le greffon n'a pas à
  dépendre de `apps/poste`.
- Dans l'image, le greffon l'importe **par son chemin** (`noyau/routage.py` et
  `noyau/motifs_secrets.py` ajoutent `contrat/` à `sys.path`) : rien n'est installé dans
  l'environnement de Hermes.

## Contenu

- `acp_poste_contrat.quotas` : relevés de quotas d'abonnement (Codex CLI, Claude
  Code), repris de `acp_contracts.subscriptions` (étiquette
  `archive/acp-0.10.0-avant-hermes`) ; P6 admet une seconde source Claude,
  `claude_code_rate_limit_event` (exécutions `claude -p` de l'exécutant, une fenêtre à la fois),
  par l'ensemble `QUOTA_SOURCES_BY_PROVIDER`.
- `acp_poste_contrat.inventaire` (P4, décision D21 ; **étendu en P5 sans rien
  restreindre**) : relevé d'une voie (`Releve`, `ModeleReleve`, `Quotas`, `Depot`),
  inventaire complet du poste (`InventairePoste` : relevés, bac à sable Codex,
  connexions, versions des CLI, politique de `poste.toml`), résumé des quotas calculé
  par le greffon (`resume_quotas`) et garde « aucun identifiant »
  (`identifiant_trouve` : motifs de secrets, `@`, chemins de lecteur, UNC ou de profil,
  jetons d'ACP). Tout relevé que P4 acceptait reste accepté (relevés factices et lignes
  déjà en base). **Étendu en P6** (cahier P6 § 7.3) : variante Linux de l'exécutant
  (`InfosPoste.plateforme`, `hote`, `noyau`, compte `uid_dedie`, `IsolementLinux` à la place de
  `BacASableCodex`, un seul bloc par plateforme), conditions d'usage et bornes d'exécution de la
  politique, résolutions observées admises. Tout inventaire de P5 reste valide. **Étendu en P7** (cahier P7
  § 11.2) : visibilité MESURÉE de chaque dépôt (`Depot.visibilite`, `lecture`, `verifie_le`, facultatifs ; un dépôt
  non mesuré se sérialise toujours `{"alias": …}`, forme inchangée pour un greffon de P6) ; le greffon ne prête la
  voie Codex qu'à un dépôt mesuré `prive` et lu `ok`.
- `acp_poste_contrat.machine` (P5, **étendu en P6**) : protocole `acp-machine/1` — requêtes et
  réponses des neuf routes machine (`enrolement`, `reclamer`, `inventaire` ; en P6 `battement`,
  `terminer`, `question`, `bloquer`, `reprendre`, `arret`, chacune avec un `id_envoi` idempotent),
  carte servie par `reclamer` (`DemandeCarte`, 60 Kio au plus), bornes des corps (4, 8, 32 et 256 Kio),
  balayage des secrets d'un corps (`secret_trouve`), forme des jetons
  (`acpm_…`, `acpe_…`), empreintes (SHA-256 gardé par le greffon, `XXXX-XXXX` affiché),
  forme des erreurs et corps exact du 401 de la couture de Hermes (ambigu, jamais
  une révocation certaine).
- `acp_poste_contrat.motifs_secrets` (déplacé du noyau du greffon en P5) : motifs de
  secrets refusés, une seule copie pour le greffon, le poste et
  `scripts/balayer_secrets.py` (parité testée).
- `acp_poste_contrat._validation` : refus des NUL et des instants hors plage UTC,
  seule partie de `acp_contracts.limits` dont ces modèles avaient besoin.

Les exemples de requêtes et de réponses du protocole machine
(`hermes/tests/outils/fixtures_machine/`) servent à la fois aux tests de ce contrat, aux
tests du greffon dans l'image et au faux Hermes des tests du poste : une divergence fait
échouer l'un d'eux.

Tests : `python -m pytest hermes/plugins/acp-poste/contrat/tests` depuis la racine.
