# Phase 0 — Audit complet du dépôt et plan de migration

> Statut : audit terminé, **aucun code applicatif modifié** (seul ajout : entrées
> `.gitignore` protégeant les assets sous licence, mesure de sécurité immédiate).
> Prochaine étape sur validation : `Lance la Phase 1 — Pipeline d'assets.`

---

## 1. État réel du dépôt (vérifié dans le code, pas dans le README)

### 1.1 Constat majeur : le dépôt est déjà au-delà de la « Phase 2 » du cahier des charges

Le cahier des charges suppose un moteur Canvas procédural à remplacer par Phaser.
**C'est déjà fait.** L'état réel :

| Composant du cahier des charges | État réel | Fichiers |
|---|---|---|
| Phaser 3 (`pixelArt`, `roundPixels`) | ✅ en place, v3.90, import dynamique | `packages/pixel-office-engine/src/phaser/phaser-renderer.ts` |
| Tilemaps / atlas / spritesheets / animations | ✅ data-driven via manifests v1.0 | `phaser/scenes/OfficeScene.ts`, `phaser/assets/manifest-loader.ts` |
| Pathfinding + collisions | ✅ A* 4-directions sur grille 32 px, testé | `phaser/grid/pathfinding.ts` (+ tests) |
| Réservation des stations | ✅ un siège par agent, capacité, testé | `phaser/grid/reservations.ts` (+ tests) |
| Caméra, zoom, sélection, surbrillance | ✅ pan drag, paliers 0.5/1/2/3×, focus salle | `phaser/camera/camera-controller.ts` |
| Couches de profondeur | ✅ 6 couches + tri Y (cible : 14, voir §8) | `phaser/layers.ts` |
| Effets d'état / bulles | ✅ émotes sprites + compat glyphes texte | `OfficeScene.showEmote` |
| Chargement de manifests | ✅ validation, héritage `extends`, fusion | `manifest-loader.ts` (13 tests) |
| Galerie d'assets | ✅ `?gallery=1` (cible : `/dev/assets`, voir §11) | `phaser/scenes/GalleryScene.ts` |
| Fallback sans Phaser | ✅ renderer Canvas gelé + bascule auto + timeout | `legacy/canvas-renderer.ts`, `fallback.ts` |
| Placeholders originaux | ✅ 100 % générés par script (aucun asset tiers) | `tools/generate-placeholders.mjs` |
| Campus extérieur | ✅ herbe, allées, arbres, Lounge/Réception/Meeting | `apps/web/src/scene.ts` |
| Vues Company/Workspace/Project/Department | ✅ navigation + clic salle + WebSocket temps réel | `apps/web/src/main.ts` |
| HUD dashboard | ✅ sidebar, 6 KPI réels, rail droit (santé, files, approbations, incidents, événements) | `apps/web/src/{main.ts,style.css}` |

### 1.2 Backend (inchangé par la refonte graphique, conforme au cahier des charges)

- **Hiérarchie** Organization → Workspace → Department → Project → Team →
  AgentInstance → Task → TaskRun : `packages/database/src/acp_database/models.py`.
  Sessions (4 scopes) et mémoire (6 scopes, TTL, classification, sharing policy) incluses.
- **OrchestratorProvider** : abstraction exacte du cahier des charges dans
  `packages/provider-sdk` ; implémentations `mock`, `manual`, `hermes` dans
  `services/provider-gateway/src/acp_provider_gateway/providers/`.
- **Hermes** : totalement isolé (client + contrat versionné 1.0 + adaptateur + 6 tests
  d'intégration simulés dans `providers/hermes/`). Le cœur n'importe rien d'Hermes ;
  indisponible ⇒ 503, plateforme fonctionnelle. Conforme §5.
- **Worker simulé** : claim → plan via gateway → étapes → évaluation → done, avec
  session d'exécution isolée par run. `apps/worker/src/acp_worker/main.py`.
- **Événements** : journalisés (PostgreSQL/SQLite) + diffusés WebSocket
  (`apps/event-service`). Isolation mémoire inter-projets vérifiée.
- **Plugins** : 4 modules `plugins/*/plugin.json` (+ core intégré), validés par
  `acp_agent_sdk.ModuleManifest`.

---

## 2. Audit du moteur Canvas (legacy)

Confiné dans `legacy/canvas-renderer.ts` (~430 lignes), **déjà rétrogradé en fallback**.
Primitives qui doivent disparaître *du chemin par défaut* (elles n'y sont déjà plus) :

| Primitive | Où | Statut |
|---|---|---|
| `drawRoom()` damier + murs plats | legacy uniquement | remplacé (tilemaps Phaser) |
| `drawStation()` `switch(kind)` + `fillRect` | legacy uniquement | remplacé (atlas + manifests) |
| `drawEntity()` personnages en blocs | legacy uniquement | remplacé (sprites 32×48 animés) |
| Palettes `THEMES/SKIN/HAIR/SHIRT` codées en dur | legacy uniquement | remplacé (thèmes de packs) |
| Emojis de statut (`⌨ ☕ 📖…`) | legacy uniquement | remplacé (effets sprites) |
| Errance aléatoire sans collision | legacy uniquement | remplacé (A* + réservations) |

Décision conforme §43 : le legacy reste le fallback tant que la parité Phaser n'a pas
tourné plusieurs semaines en conditions réelles ; il est gelé (bugfix only).

## 3. Audit du frontend

- `apps/web/src/main.ts` (~450 l.) : orchestration vues/UI/WS. Sain, mais monolithique —
  à découper en composants lors de la Phase 6 (HUD).
- `apps/web/src/scene.ts` : traduction Overview → SceneSpec (campus, espaces communs,
  enseignes). C'est **la** couche d'adaptation métier→moteur ; à conserver telle quelle.
- `apps/web/src/api.ts` : REST + WS + gateway (approbations manuelles). RAS.
- Dette identifiée : pas de routeur (vues en état interne — bloquant pour `/ambient`,
  `/dev/assets` → à introduire en Phase 1/8, léger, sans framework) ; `X-User-Id`
  non envoyé par le front (permissions inactives en mode dev).

## 4. Audit des contrats de scènes

`SceneSpec/RoomSpec/StationSpec/EntitySpec` (dans
`packages/pixel-office-engine/src/contracts/scene.ts`) **servent déjà d'adaptateur
Phaser** via `adapter/scene-adapter.ts` (module pur, résolution assets, signature de
layout pour le diff). Extensions déjà présentes (toutes optionnelles) : `assetId`,
`footprint`, `capacity`, `facing`, `characterId`, `subtitle`, `groundThemeId`, `paths`,
`decorations`, `assetPackIds`, `gridTile`. **Aucune rupture nécessaire pour LimeZu.**

## 5. Audit des plugins

`plugins/<module>/plugin.json` fournit : départements (type, thème, stations,
animations, `status_mapping`), rôles+capacités (avec `required_providers`), workflows
avec validateurs, indicateurs, adaptateurs déclarés (Blender/Unreal `planned`).
Chargés par l'API (`GET /modules`), consommés par le front via
`GET /departments/{id}/office-config`. Conforme §35. Manque pour les phases futures :
**templates de salles** et **mappings d'assets par module** (extension du schéma,
pas de refonte).

## 6. Audit du système d'événements

Types émis aujourd'hui : `task.created/queued/status_changed/plan_ready/progress/
completed/failed`, `agent.status_changed`. Champs : ids complets de la hiérarchie +
payload. Données réellement disponibles dans `GET /overview` : organizations,
workspaces, departments, projects, teams, team_members, agents (avec statuts), tasks
(statuts, priorité, workflow_step, assignation). **Manquent** pour le cahier des
charges : événements workers (aucun worker distant), artefacts (pas de table
Artifact), locks, approbations formelles (seule la file du provider `manual` existe),
progression pondérée (§10 : `workflow_step` est un libellé, pas un poids). → phases 9+.

## 7. Audit worker & providers

- Distinction orchestrateurs / exécuteurs / outils : **partielle**. Les orchestrateurs
  sont réels (gateway) ; exécuteurs et outils ne sont que des entrées catalogue en base
  (`ProviderModel`, seed). Le worker est local et simulé, sans enregistrement, token,
  heartbeat, lease ni capacités (§8) — prévu Phase 9, rien à casser d'ici là.
- Approbations : `ManualOrchestratorProvider` a une vraie file `pending/resolve`
  (déjà affichée dans le HUD). Servira de base au système WAITING_APPROVAL (§38).
- Locks (§9) : inexistants. Sans worker réel ni exécution concurrente sur mêmes
  ressources, non bloquant avant Phase 9.

---

## 8. Architecture cible Phaser — deltas restants

L'essentiel existe. Écarts avec le cahier des charges :

1. **Couches** : 6 actuelles (`floor, walls, furniture-back, entities,
   furniture-front, effects` + UI) contre 14 cibles. Le tri-Y actuel couvre déjà
   back/front correctement. Ajouts nécessaires (Phase 3) : `ground` (fait de facto via
   campus), `floor_details`, `windows`, `wall_front`, `labels` (fait : enseignes),
   `interaction`, `debug`. → extension de `layers.ts` en bandes supplémentaires,
   pas de refonte.
2. **Portes / transitions entre salles** : non implémentées (agents confinés à leur
   salle). Nécessaires Phase 3 (salle pilote) et 7 (campus→bâtiment).
3. **Tilemaps Tiled par salle** : contrat `RoomSpec.tilemapId` existe, rendu partiel
   (galerie). Le workflow Tiled complet est en Phase 5.
4. **File d'attente devant station occupée** (§21) : aujourd'hui repli en errance ;
   à améliorer Phase 4.
5. **États de déplacement** (`waiting_for_path`…) : implicites ; à formaliser si besoin
   d'affichage.

## 9. Stratégie de compatibilité

Déjà en place et à conserver telle quelle :
`createOfficeRenderer({mode})` → Phaser par défaut, `?renderer=canvas` en secours,
timeout 20 s + `onRendererFallback`. Contrats uniquement étendus par champs optionnels.
**Deux assouplissements nécessaires pour LimeZu (Phase 1)** :

- le validateur de manifests impose `grid.character = 32×48` ; les personnages LimeZu
  16×32 importés en ×2 font **32×64** → valider par la taille déclarée du personnage
  (32×48 ET 32×64 acceptés) ;
- `grid.tile = 32` reste inchangé (voir §16 : les packs existent nativement en 32×32).

---

## 10. Pipeline d'import LimeZu (conception, Phase 1)

### 10.1 Inventaire réel des archives (vérifié dans `Limzu/`, 262 Mo)

| Archive | Contenu | Grille | Licence (lue dans le zip) |
|---|---|---|---|
| `Modern_Office_Revamped_v1.2.zip` | 1 047 PNG : Room_Builder (sols/murs/portes/fenêtres) + mobilier (ombres/sans ombre/singles) | **16, 32 et 48 px natifs** | ✅ commercial OK, ❌ redistribution, crédits appréciés |
| `modernexteriors-win.zip` | 39 138 PNG : terrains, routes, végétation, bâtiments, véhicules… | **16, 32, 48 px natifs** | payante (PDF) — mêmes termes LimeZu |
| `modernuserinterface-win.zip` | 912 PNG : cadres, boutons, onglets, icônes, curseurs + Portrait Generator | 16/32/48 | ✅ commercial OK **sauf NFT**, ❌ redistribution, **crédits requis** |
| `Modern_Interiors_Free_v2.2.zip` | 64 PNG : 4 personnages (Adam, Alex, Amelia, Bob) + tuiles de base | 16 px | ⚠ **NON-COMMERCIAL UNIQUEMENT** (~1 % du pack complet) |
| `Portrait_Generator_Setup.exe` | outil de portraits | — | outil, pas un asset |

**Conséquence heureuse** : Office/Exteriors/UI en 32×32 natif ⇒ import direct sur notre
grille, aucun rescaling, moteur inchangé. Seuls les personnages (16×32) seront
upscalés ×2 (nearest-neighbor) vers 32×64 par le script.

### 10.2 Script `npm run assets:import-limezu -- "<dossier>"`

(`tools/import-limezu.mjs`, mêmes bibliothèques que le générateur de placeholders)

1. vérifie la présence/version de chaque archive (échec propre + rapport si absente) ;
2. extrait en zone temporaire, sélectionne uniquement le nécessaire (jamais 40 000 PNG :
   sous-ensembles configurés par un fichier de mapping committé) ;
3. découpe/assemble en atlas ≤ 2048×2048 + JSON hash TexturePacker ;
4. renomme selon la **nomenclature logique** (§34) : `office.desk.basic`,
   `character.adam.walk-down`, `exterior.tree.small`, `ui.panel.dark`… —
   aucune dépendance aux noms de fichiers LimeZu hors du fichier de mapping ;
5. écrit dans `apps/web/public/assets/licensed/limezu/` (**gitignoré**, jamais suivi) ;
6. génère les manifests packs `limezu-core / limezu-office / limezu-characters /
   limezu-exterior / limezu-ui` (`extends` des packs placeholders → fallback naturel) ;
7. vérifie dimensions (multiples de 16/32), doublons de frames, frames manquantes ;
8. écrit `import-report.json` + `PROVENANCE.md` (pack, version, date, licence, crédits) ;
9. met à jour `packs.json` (section `licensed`, résolue dynamiquement : absente ⇒
   les manifests placeholders restent actifs).

## 11. Manifests & galerie — extensions Phase 1

Format actuel conservé (`manifest_version` 1.0). Ajouts rétro-compatibles :
`provenance {source, license, credit_url}`, `logical_aliases` (id logique → frame),
tailles de personnages par déclaration. La galerie gagne : route dédiée `/dev/assets`
(alias de `?gallery=1`, désactivable en prod via env), recherche/filtre par pack,
affichage id logique + dimensions + origine, bandeau
« Licensed assets not installed. Run: npm run assets:import-limezu … » quand seuls
les placeholders sont chargés.

## 12. Templates de salles (Phase 5 — conception)

Nouveau concept `RoomTemplate` (JSON versionné, exemple §18 du cahier des charges) :
couches floor/walls/furnitureBack/stations/furnitureFront/collisions + `capacity` +
`upgradeTo`. Fournis par les **plugins** (`plugins/<module>/rooms/*.json`).
`scene.ts` choisira un template selon département + effectif au lieu de poser les
stations une à une. Workflow Tiled documenté : Tiled → export `.tmj` → validation
(script) → import Phaser. Pas d'éditeur navigateur avant longtemps (§33).

## 13. Personnages modulaires (Phase 4 — conception)

LimeZu livre les personnages en couches (corps/tenues/cheveux). Deux options :

- **retenue : bake à l'import** — le script compose N variantes (peau × cheveux ×
  tenue-par-rôle) en spritesheets plats → simple, performant, atlas propres ;
- runtime layering (5-6 sprites superposés par agent) : rejeté pour le MVP (complexité
  profondeur/synchro animations).

Le **seed stable par agent existe déjà** (`hashCode(entity.id)` dans le resolver de
personnages) : même agent ⇒ même apparence entre sessions. Animations cibles §19
mappées via `animation_aliases` (mécanisme existant) ; les manquantes retombent sur
`idle`/`sit` proprement (testé).

## 14. Campus / croissance (Phase 7 — conception)

Vue campus primitive déjà là (bâtiments = salles avec enseignes, allées, arbres).
Cible : `CampusLayout/BuildingDefinition/BuildingInstance/UpgradeRule/UnlockCondition`
en **données** (`packs` + config), niveaux 1→5 calculés backend à partir de métriques
réelles (`project_count`, `agent_count`, `completed_task_count`…) exposées via un
`GET /company/level` (petit endpoint, phase 7). Transition campus→bâtiment : zoom
caméra + swap de scène (le diff de scène existant rend ça naturel). Rien de
pay-to-win : purement symbolique.

## 15. Ambient / Wallpaper (Phase 8 — conception)

- Routes `/ambient`, `/projects/:id/ambient` via le mini-routeur de Phase 1.
- Profils `performance/balanced/cinematic` : cap FPS via `game.loop.targetFps` +
  réduction des wanders ; suspension onglet caché déjà gérée (watchdog + forceTimeout).
- Distinction **REAL / DECORATIVE** : déjà séparée dans le moteur (statuts backend =
  réels ; errance = décorative) — à exposer comme drapeau interne + option d'affichage.
- Version autonome (Wallpaper Engine plus tard) : build Vite séparé `ambient.html`
  avec données mock embarquées si backend absent — architecture seulement, pas
  d'implémentation avant Phase 8.

---

## 16. Risques de licence (vérifiés)

1. ✅ **Réglé aujourd'hui** : `Limzu/` était DANS le dépôt, non tracké — désormais
   gitignoré (avec `local-assets/`, `licensed/`, `*.aseprite`). Jamais commité (vérifié
   `git log --all -- Limzu`). *Recommandation* : déplacer quand même hors du repo
   (ex. `C:\AgentCompanyAssets\LimeZu\`) — le script d'import prendra le chemin en
   argument.
2. ⚠ **Modern Interiors Free = non-commercial only + 4 personnages.** Si le projet a la
   moindre vocation commerciale, il faut la version complète (~2 $) avant d'importer
   les personnages. **Question bloquante n° 1.**
3. ⚠ Modern UI : crédits **obligatoires** (lien LimeZu) → à ajouter au footer/README,
   et interdiction NFT (non concerné).
4. Les builds de prod embarquent `public/assets/licensed/` : servir les assets dans
   l'app est un usage normal ; ne jamais publier le dossier `dist/` dans le dépôt ni
   en artefact téléchargeable public. À noter dans `docs/security/threat-model.md`.
5. Les tests CI ne doivent jamais dépendre des assets licenciés (déjà le cas :
   tests sur placeholders et mocks).

## 17. Risques techniques & performance

| Risque | Impact | Mitigation |
|---|---|---|
| Modern Exteriors = 39 138 PNG | import ingérable | mapping explicite de sous-ensembles ; jamais d'import « tout » |
| Atlas trop grands (>4096 px) | crash WebGL mobile | packer ≤2048×2048, plusieurs atlas par pack |
| Personnages 32×64 vs validateur 32×48 | échec de chargement | assouplissement validateur (Phase 1, §9) |
| Beaucoup plus de frames d'animation LimeZu | mémoire/anims | n'enregistrer que les clips référencés par manifests |
| `main.ts` monolithique | vélocité Phase 6 | découpage HUD différé, pas dans Phase 1 |
| Mode wallpaper = rendu permanent | batterie | profils FPS + pause onglet caché (base déjà présente) |
| Import ×2 nearest des personnages 16 px | mélange d'échelles si erreur | vérification dimensions dans le rapport d'import |

## 18. Contradictions cahier des charges ↔ existant (arbitrages proposés)

| Cahier des charges | Existant | Arbitrage |
|---|---|---|
| Grille 16 px source, affichage ×2 (§13) | grille 32 px native | **garder 32 natif** : les packs LimeZu existent en 32×32 ; zéro rescaling, zéro changement moteur |
| `pnpm assets:import-limezu` (§15) | monorepo **npm** workspaces | `npm run assets:import-limezu -- "<chemin>"` (passer à pnpm = chantier séparé, non justifié ici) |
| Phase 2 « installer Phaser » (§45) | déjà fait (+pathfinding, +galerie…) | re-baser les phases (voir §19) : Phase 2 devient « compléments fondation » |
| Manifest `schemaVersion/displayScale` (§16) | `manifest_version`, pas de scale | garder notre format, ajouter provenance + alias logiques ; `displayScale` inutile en 32 natif |
| Galerie `/dev/assets` (§32) | `?gallery=1` | ajouter la route + enrichissements (Phase 1) |
| 14 couches (§17) | 6 couches + tri-Y | extension progressive en Phase 3 (salle pilote) |
| Hiérarchie §3 : `Artifact` sous Project | table absente | création en Phase 9 (workers réels) — rien ne la consomme avant |
| Progression pondérée (§10) | `workflow_step` libre | endpoint + colonnes en Phase 3-bis backend (petit lot dédié, après la salle pilote) |

## 19. Plan de migration re-basé (phases du cahier des charges → réalité)

- **Phase 0 — Audit** : ✅ ce document.
- **Phase 1 — Pipeline d'assets** : import LimeZu, manifests licensed + provenance,
  assouplissement validateur (32×64), route `/dev/assets` enrichie, fallback +
  messages, docs, tests. *(détails §21)*
- **Phase 2 — Compléments fondation** (ex-« Phaser Foundation », déjà 80 % fait) :
  couches supplémentaires (floor_details, windows, wall_front), portes/transitions
  intra-bâtiment, file d'attente stations.
- **Phase 3 — Salle pilote Software Engineering** : template dédié room-builder LimeZu
  (sol, murs, portes, 6 bureaux, écrans, plantes, café), 4+ personnages animés,
  validation visuelle par Paul avant généralisation.
- **Phase 4 — Personnages** : bake de variantes modulaires, animations étendues
  (talk, celebrate, error…), file d'attente devant stations.
- **Phase 5 — Templates de salles** : schéma RoomTemplate, fourniture par plugins,
  variantes, workflow Tiled documenté et outillé.
- **Phase 6 — HUD Modern UI** : design system hybride (9-slice pixel + HTML/CSS pour
  texte/tableaux/formulaires), découpage de `main.ts`.
- **Phase 7 — Campus Modern Exteriors** : bâtiments, routes, croissance data-driven
  (CompanyLevel + UnlockRules backend), transitions campus↔bureaux.
- **Phase 8 — Ambient/Wallpaper** : routes, profils de performance, caméra auto,
  build autonome.
- **Phase 9 — Providers réels** : Claude Code/Codex exécuteurs, worker Windows
  enregistré (token, heartbeat, lease), locks, approbations formelles, Artifact,
  progression pondérée, Railway control plane.
- **Phase 10 — Game Development** : Blender MCP, Unreal MCP, nanos world, validation
  d'assets, build & cook (worker local uniquement).

## 20. Fichiers à modifier

### Phase 1 (exhaustif)

| Fichier | Action |
|---|---|
| `.gitignore` | ✅ fait (protection licensed) |
| `packages/pixel-office-engine/tools/import-limezu.mjs` | **créer** — le pipeline complet |
| `packages/pixel-office-engine/tools/limezu-mapping.json` | **créer** — sélection + nomenclature logique (committé, sans pixel LimeZu) |
| `packages/pixel-office-engine/src/contracts/assets.ts` | + `provenance`, `logical_aliases` (optionnels) |
| `packages/pixel-office-engine/src/phaser/assets/manifest-loader.ts` | validateur : tailles personnages déclarées (48/64), packs `licensed` optionnels ignorés si absents |
| `packages/pixel-office-engine/src/phaser/scenes/GalleryScene.ts` | provenance, message « licensed absents », recherche/filtre |
| `apps/web/src/main.ts` | mini-routeur hash (`#/dev/assets`, base pour `#/ambient`), flag env pour désactiver la galerie en prod |
| `apps/web/public/assets/packs.json` | section `licensed` (générée par l'import, tolérée absente) |
| `package.json` (racine) | script `assets:import-limezu` |
| `packages/pixel-office-engine/tests/import-limezu.test.ts` | **créer** — mapping, rapport, dimensions, fallback sans packs |
| `docs/assets/limezu-installation.md`, `docs/assets/asset-manifest.md`, `docs/security/threat-model.md` | **créer** |

### Phase 2 (prévision)

`phaser/layers.ts` (bandes supplémentaires), `OfficeScene.ts` (windows/wall_front/
portes, file d'attente), `scene.ts` (portes entre salles), tests scènes.

## 21. Critères d'acceptation — Phase 1

1. `npm run assets:import-limezu -- "<dossier>"` importe Office + Exteriors + UI
   (+ Interiors si licence résolue) vers `assets/licensed/limezu/` **gitignoré**,
   avec `import-report.json` (compte, dimensions, doublons, manquants) et
   `PROVENANCE.md` ; échec propre et explicite si une archive manque.
2. `git status` reste vierge après import (aucun fichier licencié suivi) ; un test
   l'affirme (chemins générés ⊂ chemins ignorés).
3. Sans import : l'app démarre sur placeholders, galerie affiche le bandeau
   « Licensed assets not installed » + la commande à lancer.
4. Avec import : les packs `limezu-*` remplacent les placeholders via `packs.json`
   sans changement de code ; visibles et filtrables dans `#/dev/assets` avec id
   logiques, dimensions et provenance.
5. Personnages 32×64 acceptés par le validateur ; 38 tests existants toujours verts +
   nouveaux tests import verts ; `npm run build:web` OK.
6. Docs d'installation et threat-model licence publiées.

---

## 22. Questions réellement bloquantes

1. **Modern Interiors** : la version Free est *non-commerciale* et ne contient que
   4 personnages. Achètes-tu la version complète (~2 $) ? Sinon : Phase 1 importe
   Office/Exteriors/UI, et les personnages restent nos placeholders (ou les 4 persos
   Free si — et seulement si — le projet reste non commercial).
2. **Emplacement des zips** : je recommande de déplacer `Limzu/` hors du repo
   (ex. `C:\AgentCompanyAssets\LimeZu\`). Confirmes-tu (le script prendra le chemin en
   argument de toute façon) ?
3. **npm vs pnpm** : le monorepo est en npm workspaces ; je garde `npm run …` sauf avis
   contraire.
4. **Crédit LimeZu** (obligatoire pour Modern UI) : où l'afficher — footer de l'app +
   README ?
