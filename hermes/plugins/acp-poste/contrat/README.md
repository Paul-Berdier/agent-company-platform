# Contrat partagé `acp_poste_contrat`

Modèles Pydantic partagés par le **poste Windows** (`apps/poste`) et le futur
greffon Hermes **`acp-poste`** (`hermes/plugins/acp-poste`, construit à partir de P1).
Une seule source, jamais de copie : le poste l'installe comme distribution locale
(`pip install -e hermes/plugins/acp-poste/contrat`) ; l'image Hermes le reçoit avec
le greffon, puisque tout `hermes/` forme le contexte de construction de l'image.

## Pourquoi ici

- Le plan (docs/refonte/plan.md) range les modèles Pydantic du greffon dans
  `hermes/plugins/acp-poste/contrat/`. Le contexte de construction de l'image est
  limité à `hermes/` : un contrat laissé dans `packages/` devrait être recopié dans
  l'image, et deux copies finissent par diverger.
- Le poste en dépend comme d'une distribution ordinaire ; le greffon n'a pas à
  dépendre de `apps/poste`.
- La manière dont le greffon l'importera dans l'image (installation dans
  l'environnement de Hermes ou chemin ajouté par le greffon) se décide en P1, avec
  l'image réelle ; rien n'est supposé ici.

## Contenu

- `acp_poste_contrat.quotas` : relevés de quotas d'abonnement (Codex CLI, Claude
  Code), repris **tels quels** de `acp_contracts.subscriptions` (étiquette
  `archive/acp-0.10.0-avant-hermes`). Leur réduction au schéma de
  `hermes usage --json` est l'objet de P6.
- `acp_poste_contrat._validation` : refus des NUL et des instants hors plage UTC,
  seule partie de `acp_contracts.limits` dont ces modèles avaient besoin.

Tests : `python -m pytest hermes/plugins/acp-poste/contrat/tests` depuis la racine.
