# Interface d'ACP — étape P3, identité visuelle et français

État du **25 septembre 2026**. Étape P3 du [plan de la refonte](plan.md), **première partie**
(identité visuelle et français) : thème `acp` généré depuis `design/tokens`, persona française,
greffons de tableau de bord `acp-interface` et `acp-catalogue`, verrou du français, décompte des
chaînes de Hermes restées en anglais, test navigateur aux formats téléphone et bureau. La seconde
partie de P3 (catalogue de skills vendorisées, verrou `catalogue.lock.json`, MCP context7, route
`/v1/catalogue` du greffon `acp-poste`) est décrite par [catalogue.md](catalogue.md) ; ce qui la
relie à l'interface est fixé ici au § 6 (contrat, désormais servi). **Rien n'est déployé.**

**Étape P4** (seconde partie, 26 septembre 2026) : troisième greffon d'interface, `acp-projets`, page
« Projets » (§ 10 ; référence : [projets.md](projets.md) § 4 bis).

Les références `fichier:ligne` sans préfixe désignent le source de Hermes Agent 0.21.5
(étiquette `v2026.9.24`, commit `f97608f`).

## 1. En bref

| Élément | Dépôt | Image |
|---|---|---|
| Générateur du thème | `scripts/generer_themes.py` (+ `scripts/tests/test_generer_themes.py`) | — |
| Thème `acp` (généré) | `hermes/theme/acp.yaml` | `/opt/acp/theme/acp.yaml` → `/opt/data/dashboard-themes/acp.yaml` (05-acp) |
| Persona française | `hermes/persona/SOUL.md` | `/opt/acp/persona/SOUL.md` → `/opt/data/SOUL.md` (05-acp, `gerer_soul`) |
| Sources des greffons d'interface | `apps/interface/` (TypeScript, esbuild, Vitest) | — |
| Greffon `acp-interface` | `hermes/plugins/acp-interface/dashboard/` (manifeste, bundle, style) | `/opt/hermes/plugins/acp-interface/` |
| Greffon `acp-catalogue` | `hermes/plugins/acp-catalogue/dashboard/` | `/opt/hermes/plugins/acp-catalogue/` |
| Greffon `acp-projets` (P4, page « Projets ») | `hermes/plugins/acp-projets/dashboard/` | `/opt/hermes/plugins/acp-projets/` |
| Épingles de P3 (managed scope) | `hermes/gere/config.yaml`, `EPINGLES_OBLIGATOIRES` | `/etc/hermes/config.yaml` (42 clés à la première partie ; 50 depuis la seconde : [catalogue.md](catalogue.md) § 7) |
| Décompte des chaînes anglaises | `apps/interface/outils/decompte-traductions.mjs` | mesuré sur les fichiers extraits de l'image |
| Test navigateur de l'interface | `hermes/tests/e2e/test_interface_fr.py` (connexion et vérifications communes : `parcours.py`) | — |
| Test navigateur de la page Projets (P4) | `hermes/tests/e2e/test_projets.py` | — |

## 2. Thème `acp`

`scripts/generer_themes.py` (bibliothèque standard seulement) charge `design/tokens/*.json` **par
le module du générateur QML du desktop** (`apps/desktop/cmake/generate_design_tokens.py`,
`load_tokens`, `public_tokens`) : une seule source et un seul chargeur pour le tableau de bord et
le client natif. `--check` échoue si `hermes/theme/acp.yaml` ne correspond plus aux jetons **et**
appelle le générateur du desktop en `--check` sur `apps/desktop/qml/theme/generated` ; la CI
(`ci.yml`, travail « Poste ») le lance sous Linux et sous Windows.

Correspondance (thème sombre, `$defaultTheme` des jetons ; le thème clair est reporté, D18) :

| Champ de Hermes | Jeton | Valeur |
|---|---|---|
| `palette.background` / `midground` | `surface.canvas` / `text.primary` | `#191c1a` / `#eef2e9` |
| `palette.foreground`, `warmGlow`, `noiseOpacity` | — | couche invisible, aucun halo, aucun grain (`elevation.json`) |
| `typography.fontSans` / `fontMono` | `family.interface` / `family.mono` | piles de polices du système, **aucune `fontUrl`** |
| `typography.baseSize` / `lineHeight` / `letterSpacing` | `size.body` / `lineHeight.body` / `letterSpacing.normal` | `14px` / `1.43` / `0` |
| `layout.radius` / `density` | `radius.md` / — | `8px` / `comfortable` |
| `colorOverrides.card`, `popover`, `secondary`, `muted` | `surface.panel`, `surface.overlay`, `surface.panelRaised` | |
| `colorOverrides.primary` / `primaryForeground` | `accent.primary` / `text.onAccent` | `#65c6ae` / `#07271c` |
| `colorOverrides.accent`, `mutedForeground` | `accent.muted`, `text.muted` | |
| `colorOverrides.destructive`, `success`, `warning` | `status.failed`, `status.succeeded`, `status.degraded` (avant-plans) | |
| `colorOverrides.destructiveForeground` | `surface.canvas` | encre sombre : le blanc par défaut de Hermes n'atteint pas 4,5:1 sur le corail |
| `colorOverrides.border`, `input`, `ring` | `border.default`, `border.interactive`, `border.focus` | |
| `componentStyles` | — / `surface.sidebar` | cartes sans ombre ; en-tête et colonne sur `surface.sidebar` |
| `customCSS` | `border.focus`, `layout.focusRing*`, `motion.json` | anneau `:focus-visible` de 2 px ; profil « mouvement réduit » ; 501 octets |

Refus explicites (code 1, rien d'écrit) : jeton manquant, URL externe (`fontUrl`, `url(`,
`@import`, `http…`), `customCSS` au-delà de 2 Kio (budget d'ACP) ou de 32 Kio (plafond de Hermes),
contraste recalculé (WCAG 2.1) inférieur à 4,5:1 pour un texte ou à 3:1 pour une bordure
interactive ou l'anneau de focus. Vingt-deux contrastes sont recalculés et inscrits en tête du
fichier généré ; le plus faible est 4,57:1 (bordure interactive sur une carte, seuil 3:1), le plus
faible des textes 5,71:1 (texte atténué sur la surface atténuée).

Dans l'image, la normalisation **réelle** de Hermes (`_normalise_theme_definition`,
`hermes_cli/web_server_dashboard.py:317-411`) garde toutes les clés du fichier
(`hermes/tests/image/test_theme.py`) ; en contrat, `GET /api/dashboard/themes` sert exactement
cette définition, et un `PUT` d'un autre thème (réponse 200) ne change rien au thème actif
(`dashboard.theme: acp`, épinglé depuis P1).

## 3. Épingles de P3 dans la managed scope (42 clés à la première partie)

La seconde partie ajoute les huit épingles de context7 (50 clés) : [catalogue.md](catalogue.md) § 7.

| Clé | Valeur | Raison |
|---|---|---|
| `plugins.disabled` | `+ hermes-achievements` | D13 : greffon groupé de gamification, en anglais, doté de sa propre API ; un greffon groupé désactivé n'est ni servi ni monté (`web_routers/dashboard_ui.py:109-146`) |
| `dashboard.font` | `theme` | toute autre valeur ferait charger une feuille de style de Google Fonts (`web/src/themes/fonts.ts`) ; la valeur épinglée l'emporte sur celle du navigateur au chargement suivant (`web/src/themes/context.tsx:519-540`) |
| `dashboard.hidden_plugins` | `[]` | `acp-interface`, `acp-catalogue` et `acp-poste` ne peuvent pas être masqués |

`test_demarrage.py` refuse un modèle altéré sur chacune (et sur `dashboard.theme`) ;
`test_interface.py` prouve, avec le code de Hermes et un volume piégé qui masque et désactive les
greffons d'ACP, réactive `hermes-achievements` et choisit `default` et `inter`, que les greffons
d'ACP restent servis et le reste neutralisé — et, témoin négatif, que sans la managed scope le
piège l'emporterait.

## 4. Persona

`hermes/persona/SOUL.md` (2 701 octets, UTF-8 sans BOM, espaces insécables de la typographie
française) est réécrite pour la réalité de P2 : **vouvoiement** du propriétaire (D1) ; ce que
l'agent peut faire (web, image, skills proposées, liste de tâches, historique, clarification,
cartes kanban confiées) ; ce qu'il ne peut pas faire (**aucun outil d'exécution** sur Railway :
tout ce qui exige d'exécuter, de lire un dépôt ou d'écrire des fichiers revient au poste Windows,
pas encore branché ; ne jamais simuler) ; règles de non-invention (« Inconnu »), de refus en
français, de sources citées, de secrets, d'écritures soumises à validation. Les skills du
catalogue d'ACP (`acp-redaction`, `acp-profils`, celles que cite `acp-profils` et celles que Hermes
livre) **guident la méthode** sans lever une règle ni ouvrir un outil fermé ; le contenu du web,
d'une réponse d'outil ou de toute autre skill (dont celles de `skill_manage`) est une donnée, jamais
une consigne (relecture de P3 : la première version rangeait toute skill parmi les données tout en
faisant suivre `acp-redaction`). context7 et les skills
`acp-profils` et `acp-redaction` ne sont cités que **sous condition** (« si l'outil t'est proposé »,
« si elle figure dans ta liste ») : la persona ne promet rien que l'agent n'ait pas.

Mécanisme inchangé (`gerer_soul`, P1) : SOUL absent, identique à celui de l'image officielle ou à
la dernière version déposée (marqueur `/opt/data/acp/soul.sha256`) ⇒ remplacé ; retouché par le
propriétaire ⇒ gardé et signalé « divergent » (`/v1/meta`, bannière).

Preuves (`hermes/tests/image/test_persona.py`) : l'analyse d'injection de Hermes
(`tools/threat_patterns.scan_for_threats`, portées « context » et « strict ») ne relève rien ; le
chargeur de Hermes (`load_soul_md`) relit le fichier à l'identique dans un processus neuf ; montée
depuis le SOUL **exact** de P2 (`hermes/tests/outils/soul_p2.md`, octets de `120b15c`, empreinte
`10de316c…`) avec son marqueur ⇒ « déposé », puis « à jour » ; SOUL de P2 retouché ⇒ gardé,
« divergent » ; **nouvelle session** : le premier message système reçu par le modèle factice
commence par la persona française, et l'identité anglaise par défaut de Hermes n'y figure pas.
Une réponse **en français d'un vrai modèle** ne se prouve pas avec un modèle factice : elle se
relève sur Railway (`railway.md` § 7).

## 5. Greffons d'interface

Deux greffons de tableau de bord **sans code serveur** (manifeste, bundle IIFE, feuille de style),
découverts en source « bundled » (`web_server_dashboard.py:463-560`). Un greffon ne porte qu'une
page : d'où deux greffons (écart assumé à l'ancien cahier, qui en prévoyait un).

| | `acp-interface` | `acp-catalogue` |
|---|---|---|
| Page | **Accueil**, à la place de « / » (`tab.override`, qui remplaçait la redirection vers `/sessions`) | onglet **Catalogue**, dans le groupe « Plugins » que Hermes place **sous** son menu natif |
| Emplacements | `header-left` (logotype « ACP », lien vers l'Accueil), `header-banner` (alertes), `overlay` (verrou du français) | — |
| Données | `/api/plugins/acp-poste/v1/meta`, `/api/sessions` | `/api/plugins/acp-poste/v1/catalogue`, `/api/skills` |

**Où est l'onglet Catalogue** (relecture de P3 : la première version le disait « après Skills ») :
Hermes range **tous** les onglets de greffons dans un groupe « Plugins » à part, sous les 17 entrées
de son menu (`web/src/App.tsx`, `partitionSidebarNav`, groupe `t.app.pluginNavSection`) ;
`tab.position` (`after:skills` au manifeste d'`acp-catalogue`) ne les ordonne qu'entre eux (Kanban,
puis Catalogue). À 1440×900, ce groupe est sous le pli de la colonne ; au téléphone, il faut
ouvrir le menu et le faire défiler. **Limite de découvrabilité, dite** : l'Accueil (carte
Catalogue et raccourci) y mène. Le test navigateur exige le lien dans ce groupe
(`[aria-labelledby="hermes-sidebar-plugin-nav-heading"]`).

**Accueil** (pensé d'abord pour le téléphone : une colonne, cibles de 44 px) : Hermes (version en
service et testée, conformité, condensat de l'image, commit déployé ou « Inconnu ») ; garde
d'exécution (présente ou absente dans le processus du tableau de bord, nombre d'outils admis) ;
persona (à jour, déposée, **modifiée par le propriétaire**, fichier non ordinaire) ; catalogue
(résumé du bloc `catalogue` de `/v1/meta` s'il existe, sinon « Inconnu ») ; cinq dernières
sessions ; poste Windows **« Non configuré »** (P5) ; raccourcis Discussion, Sessions, Kanban,
Catalogue ; pied « ACP <version> · propulsé par Hermes Agent <version> (licence MIT) ». Aucune
carte « projets » ni « quotas » avant P4 et P5.

**Catalogue** : filtres Profil, Source, Cible ; par entrée : nom, description française, source
(`dépôt@commit`), licence, cible (« Hermes (Railway) » ou « Poste Windows »), profils, état (côté poste :
« Candidate pour le poste, non planifiée », « Prévu au poste (P8) » ou « Hors v1 ») ;
section « Écarts » ; serveurs MCP ; et, toujours, **ce que voit le tableau de bord de Hermes**
(`/api/skills` : installées, activées, désactivées, liste repliée). **Aucun bouton** : le
catalogue change par une PR. Sans `/v1/catalogue`, la page le dit (« Catalogue ACP indisponible »,
code HTTP et détail repliés) et montre quand même la vue de Hermes.

**Bannière** (toutes les pages) : les alertes de `/v1/meta`, déjà rédigées en français par
`acp-poste` (SOUL divergent, garde absente, Hermes hors de la version testée, schéma vu en http…),
rendues comme données ; `/v1/meta` injoignable : dit.

**Verrou du français** (D10) : Hermes ne fixe aucune langue côté serveur ; la sienne vient de
`localStorage["hermes-locale"]`, anglais par défaut (`web/src/i18n/context.tsx:50-64`). Le
composant de l'emplacement `overlay` appelle `useI18n().setLocale("fr")` au chargement et à chaque
changement de langue ; `<html lang="fr">` suit (`applyDocumentLocale`).

**Contrôle du SDK** : `window.__HERMES_PLUGIN_SDK__.sdkVersion` doit être une version `1.x.y`
(« 1.1.0 » en 0.21.5) exposant React et `fetchJSON` ; sinon chaque greffon s'enregistre comme un
refus explicite (« Interface ACP désactivée : SDK du tableau de bord incompatible », version
attendue et trouvée) dans sa page et la bannière.

**Sûreté** : React vient du SDK (rien d'embarqué ; la construction refuse tout fichier hors de
`src/`) ; ni `dangerouslySetInnerHTML`, ni `innerHTML`, ni `eval`, ni `new Function`, ni `fetch`
direct, ni stockage local, ni URL externe, dans les sources **et** les bundles
(`tests/statique.test.ts`). Toute erreur de l'API (l'`ApiError` de Hermes, message anglais) est
enveloppée dans un message français ; le détail brut reste replié, comme donnée.

**Bundles** : `apps/interface/esbuild.mjs` écrit des bundles IIFE déterministes (aucun horodatage,
aucun chemin absolu) sous `hermes/plugins/<greffon>/dashboard/dist/`, **committés** (exception
dans `.gitignore`) ; le travail « Interface ACP » de `ci.yml` les reconstruit et refuse toute
différence. `scripts/check_version.py` couvre les deux manifestes et `apps/interface/package.json`.

## 6. Contrat du greffon `acp-poste` (servi depuis la seconde partie de P3)

Servi par `hermes/plugins/acp-poste/catalogue.py` ([catalogue.md](catalogue.md) § 8), qui ajoute
aux champs ci-dessous `verrou`, `racine_skills`, `livrees`, `exclus`, `external_dirs`,
`external_dirs_conforme` et `desactivations_conformes` (non lus par l'interface), et, par entrée
MCP côté Hermes, `statut_hermes` et `outils_exposes`. L'interface lit, sans jamais rien supposer
d'autre :

- **`GET /api/plugins/acp-poste/v1/catalogue`** : objet JSON ; champs lus s'ils existent —
  `sources` (`{"<dépôt>": {"url", "commit", "licence", "auteur"}}`), `skills` (liste de
  `{"nom", "source", "cible": "hermes"|"poste", "etat", "profils": [...], "description_fr",
  "raison"}`), `mcp` (liste de `{"nom", "cible", "etat", "connexion": "connecte"|"hors_ligne"|
  "inconnu", "outils_hermes": [...], "raison"}`), `profils` (objet dont les clés sont les
  profils), `hors_catalogue`, `collisions`, `desactivations_non_appliquees` (listes de noms ou
  d'objets `{"nom"}`), `alertes` (liste de phrases françaises). États reconnus : `active`/`actif`,
  `desactivee`/`desactive`, `absente`/`absent`, `candidate-poste`, `reporte-p8`/`reportee-p8`,
  `hors-v1`, `ambigue`,
  `livree`, `connecte`, `hors_ligne` ; tout autre état s'affiche « Inconnu » **avec** sa valeur
  brute. Profils nommés en français : `base`, `web`, `recherche`, `donnees`.
- **bloc `catalogue` de `/v1/meta`** (facultatif) : `{"skills_actives": n, "skills_attendues": n,
  "context7": "connecte"|"hors_ligne"|"inconnu"}` ; les écarts à signaler vont dans `alertes`
  (en français), que la bannière affiche telles quelles.

Sans la route (greffon ancien, erreur), l'onglet le dit (« Catalogue ACP indisponible ») ; depuis
la seconde partie de P3, le test navigateur **exige** la route servie (`catalogue_route_v1:
"servie"`), les 26 entrées du catalogue (16 livrées, 10 candidates pour le poste) et, sur l'Accueil,
16 / 16 skills d'ACP actives.

## 7. Français

- **Catalogue unique** `apps/interface/src/chaines.ts` (99 chaînes, typographie française).
  `tests/chaines.test.ts` parcourt l'**arbre syntaxique TypeScript** de chaque composant : un texte
  JSX, une chaîne en enfant JSX ou un attribut lisible (`title`, `aria-label`, `placeholder`,
  `alt`, `label`…) écrit en dur est refusé ; témoins négatifs compris. Au navigateur, chaque nœud de
  texte sous `[data-acp-racine]` appartient au catalogue (exporté par
  `outils/exporter-chaines.mjs`) ou à un élément `data-acp-donnee` (valeur venue de l'API).
- **Dates et nombres** par `Intl` en `fr-FR`, fuseau `Europe/Paris` (jamais `SDK.utils.timeAgo`,
  qui produit « 5m ago »).
- **Agent** : persona française (§ 4) ; messages statiques par `display.language: fr` et
  `HERMES_LANGUAGE=fr` (P2).
- **Natif, compté et publié, pas traduit** : mesure de `apps/interface/outils/decompte-traductions.mjs`
  sur les fichiers **extraits de l'image** (`docker create`, `docker cp` de `/opt/hermes/web/src`
  entier et de `/opt/hermes/locales/{en,fr}.yaml`), Hermes 0.21.5 :

| Mesure | Valeur |
|---|---|
| Clés de `en.ts` | 746 |
| … présentes dans `fr.ts` | 641 |
| … absentes de `fr.ts` (affichées en anglais) | **105** |
| Clés de `fr.ts` identiques à l'anglais (souvent des noms propres) | 65 |
| Libellés de navigation sans `labelKey` (toujours en anglais) | **6** : Files, MCP, Channels, Webhooks, Pairing, System |
| Textes JSX et attributs écrits en dur dans **tout** `web/src`, hors `i18n` et tests (approximation lexicale) | **615 dans 31 fichiers** : `pages` 548, `components` 62, `App.tsx` 5 (« Loading chat… » trois fois, « Restart all », « Restart the shared gateway? ») ; `contexts`, `plugins`, `themes`, `main.tsx` : 0 |
| Clés de `locales/en.yaml` (messages statiques de l'agent) | 374 |
| … absentes de `locales/fr.yaml` | **0** |

Clés absentes de `fr.ts`, par section : `profiles` 30, `kanban` 21, `pluginsPage` 14, `app` 12,
`cron` 6, `skills` 6, `status` 6, `theme` 6, `common` 4. L'estimation lexicale du cahier (84 sur
684, sur le clone) est remplacée par cette mesure. L'extraction des clés YAML est contrôlée contre
PyYAML dans l'image (374 et 374 clés, 0 écart). Relecture de P3 : la première mesure (610 dans 30
fichiers) ne lisait que `pages` et `components` et laissait `App.tsx`, `contexts` et `plugins` hors
du compte sans le dire ; elle lit désormais tout `web/src` (test Vitest `decompte.test.ts`).
**Non mesuré** : bundles des greffons `kanban` et `hermes-achievements`, TUI de `/chat`, pages
`/auth/*` du serveur, documentation `/docs` (iframe distante), chaînes des modules `.ts`
(`web/src/lib`, `web/src/hooks`) et textes calculés par une expression (ainsi « Updates don't
apply from this dashboard. » de `contexts/SystemActions.tsx:96`, repli d'un `??`). En CI, `image.yml` refait la mesure et la publie en artefact (`decompte-traductions`).
Proposer ces traductions en amont (MIT) reste une option hors chemin critique (D15).

## 8. Tests et preuves

### Commandes

```sh
# Hôte (dépôt)
python scripts/generer_themes.py --check && python scripts/check_version.py && python scripts/check_engine_frozen.py
python -m pytest -q                                          # poste, contrat Python, outillage (dont le générateur)
npm ci --ignore-scripts --prefix apps/interface
npm test --prefix apps/interface && npm run check --prefix apps/interface
# Images
docker build -f hermes/image/Dockerfile -t acp-hermes:p3 hermes
docker build -f hermes/tests/Dockerfile --build-arg IMAGE_ACP=acp-hermes:p3 -t acp-hermes-tests:p3 hermes/tests
docker build -t acp-identite:p3 identite
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint /opt/hermes/.venv/bin/python \
  -e PYTHONPATH=/opt/acp-tests/site acp-hermes-tests:p3 -m pytest -v -rA /opt/acp-tests/image
npm ci --ignore-scripts --prefix .railway     # prérequis des 3 tests IaC du contrat (« SDK absent » sinon)
PYTHONUTF8=1 MSYS_NO_PATHCONV=1 ACP_IMAGE=acp-hermes:p3 ACP_IMAGE_TESTS=acp-hermes-tests:p3 \
  ACP_IMAGE_IDENTITE=acp-identite:p3 python -m pytest -s -v -rA hermes/tests/contrat
PYTHONUTF8=1 MSYS_NO_PATHCONV=1 ACP_IMAGE_TESTS=acp-hermes-tests:p3 ACP_IMAGE_IDENTITE=acp-identite:p3 \
  ACP_E2E_CAPTURES=<dossier> python -m pytest -s -v -rA hermes/tests/e2e
# Décompte (fichiers extraits de l'image)
id=$(docker create acp-hermes:p3); mkdir -p x/web x/locales
for c in web/src locales/en.yaml locales/fr.yaml; do
  docker cp "$id:/opt/hermes/$c" "x/$(dirname $c)/"; done; docker rm "$id"
node apps/interface/outils/decompte-traductions.mjs x --json decompte.json
```

### Preuves locales (25 septembre 2026 ; Windows 10, Docker 29.5.3, Python 3.12.10, pytest 9.1.1, Node 24.19.0)

Images reconstruites depuis le worktree au dernier état des sources (`acp-hermes:p3d`,
`acp-hermes-tests:p3d`, `acp-identite:p3d`) :

- **dépôt** (`python -m pytest -q`) : **297 réussis**, 0 échec, 0 ignoré, dont les 15 tests du
  générateur de thème ; `generer_themes.py --check` (thème et 8 fichiers QML), `check_version.py`
  et `check_engine_frozen.py` : code 0 ;
- **interface** (`npm test`) : `tsc --noEmit` sans erreur, Vitest **55 réussis** dans 11 fichiers ;
  `npm run check` : 4 fichiers de greffons à jour ;
- **dans l'image** : **259 réussis**, 0 échec, 0 ignoré (1 min 50 s), dont `test_theme.py` 4,
  `test_persona.py` 6, `test_interface.py` 3, et dans `test_demarrage.py` les 4 altérations
  nouvelles et le décompte de 42 clés ;
- **contrat** : **107 réussis**, 0 échec, 0 ignoré (12 min 19 s) : 37 image, 40 identité, 4 interface,
  3 IaC, 23 sans outil d'exécution. Relevés : `GET /api/dashboard/plugins` sert `acp-catalogue`,
  `acp-interface`, `acp-poste` et `kanban`, jamais `hermes-achievements` ; `PUT` du thème
  `midnight` et de la police `inter` : réponses 200, relus `acp` et `{"font": "theme"}` ;
  empreintes de `/etc/hermes/*`, du thème, de `SOUL.md`, du marqueur et des arbres
  `/opt/hermes/plugins/acp-*` et `/opt/acp` identiques avant et après redémarrage ;
- **navigateur** : **2 réussis** (1 min 51 s ; connexion de P2 et interface française), Chromium
  de Playwright révision 1234 **déjà présent**, rien téléchargé. Aux deux formats : aucun texte
  hors du catalogue sur l'Accueil ni le Catalogue, **aucune violation axe** (toutes gravités), 6
  et 2 cibles, aucune sous 44 px au téléphone, 376 requêtes et **aucune hors de l'origine**,
  `--color-primary` = `#65c6ae`, verrou vérifié (« en » forcé ⇒ retour à « fr »), route
  `/v1/catalogue` « indisponible » (seconde partie de P3 non livrée), bannière « SOUL.md a été
  modifié par le propriétaire » après retouche et redémarrage ;
- aucun conteneur, volume ni réseau `acp-contrat-*` restant.

Une première exécution du navigateur avait relevé une violation axe **modérée**
(`landmark-no-duplicate-banner`, format téléphone : notre `<header>` doublait le repère de la
barre de Hermes) : corrigée (plus de `<header>` ni de `<footer>` dans nos pages), puis revérifiée.

Captures (19, `ACP_E2E_CAPTURES/interface/`, images `p3d`), empreintes SHA-256 :

| Capture | SHA-256 |
|---|---|
| `bureau-01-portail-authelia.png` | `d0a7b221adffb1c3872d662ded5ca9c4529cfa5760a01dc777321e0522e799db` |
| `bureau-02-accueil.png` | `19936dbd8b2627f335755b754d614439e77d3d993e3e9c015c5bb4205a8c8b6b` |
| `bureau-03-catalogue.png` | `643c419cce61ac398c15bc2bdc7747d65eb5c0f96a93d838404fe15dcd23edec` |
| `bureau-04-sessions.png` | `dba6275925b357812063758efefea3363d794b362db005a3b7d072cf947a23b7` |
| `bureau-05-discussion.png` | `a211acd33f9939ee24a8a2f5a7a2fc4a67218e0ac41e1d0e8d4a6ebc1992715e` |
| `bureau-06-skills.png` | `aee5e8e1099403eab978637731789ebc77c7116e73c43188c13197edbb39ac6e` |
| `bureau-07-mcp.png` | `12355b39f58598590f8d91062f05dce88207b3827b88eaff88c0d190b61bb736` |
| `bureau-08-kanban.png` | `03205ff214c46822f841d73b891c4f2a5a547b2da0e8792fc9b008d0e31278c8` |
| `bureau-09-configuration.png` | `aa1da55889356baec754c90a634825b5abbdb5cbf9730b0829e2e89314c8b8a2` |
| `bureau-10-banniere-persona-divergente.png` | `887b3fbcaf016127563e1b0a0cdd253c387ab88ad26bdea8f0fe7d805a1269c5` |
| `telephone-01-portail-authelia.png` | `df038459503e03b2fc278cbd88b87f5f5bf99f9de318ef3faabfe62520ad55f3` |
| `telephone-02-accueil.png` | `8477c7b6fc32f7d71238a2beb2c8780986078d29526395995e28ab625b8856bc` |
| `telephone-03-catalogue.png` | `c4e378f1d32fd7bc40566cb87cc68a3ea39bb550e06638c631b7e74a2011c51d` |
| `telephone-04-sessions.png` | `a381a5bfd289a9bbe3936dcfcfe195db3fc38c47f0f2cb092151fc79e26cede8` |
| `telephone-05-discussion.png` | `2e360fcc2ed29e770d5a49f927ac662ab4fe7942a94b81e5dd10c4e5b3e02754` |
| `telephone-06-skills.png` | `880cb5dc9e654c65020d47387b0e3b25022d4c47d77afa1e6656d57fb6ab522b` |
| `telephone-07-mcp.png` | `50b0c41601130f551216d6b1a2a39a2fba6a3044573dc1ea2799aa5184564ad7` |
| `telephone-08-kanban.png` | `8265680e3458d2ee1db947e078426c5f2ae2a09c326cd23029efcb1b876ebcbc` |
| `telephone-09-configuration.png` | `ee7166c35b8a17803038468819e8c7ca38527614f9ccfea3345969e7fb492ad8` |

Les captures ne sont pas committées (décision D17) : la CI les publie en artefact
(`captures-navigateur`). Les pages natives y montrent le reste d'anglais compté au § 7 (menu :
Files, MCP, Channels, Webhooks, Pairing, System).

### Protections retirées une à une

| Protection retirée (copie ou témoin) | Ce qui échoue |
|---|---|
| Verrou du français retiré du bundle d'une image de test (`acp-hermes:p3mut`) | `test_interface_fr.py` : `wait_for_function(lang === 'fr')` expire (60 s) ; 1 échec |
| Managed scope absente, volume piégé | `test_interface.py` (témoin) : greffons d'ACP masqués et désactivés, `hermes-achievements` servi, thème `default`, police `inter` |
| Bundle servi différent de celui du dépôt (bundles reconstruits après l'image `p3b`) | `test_bundles_servis_identiques_au_depot` : 1 échec (constaté, puis images reconstruites) |
| Une des épingles de P3 absente ou changée dans le modèle | `test_un_modele_altere_est_refuse` : refus à la construction (4 cas) |
| SDK en version 2.0.0, absent ou incomplet | Vitest : refus explicite enregistré, jamais la page (9 cas) |
| Texte, gabarit ou attribut lisible écrit en dur ; `innerHTML`, `eval`, `fetch` direct, URL externe | Vitest : témoins négatifs de `chaines.test.ts` et `statique.test.ts` |
| Jeton manquant, contraste insuffisant, URL externe, CSS trop lourd, sortie ou QML périmés | `test_generer_themes.py` (9 tests rouges) |

Intégration continue (détail : `docs/reprise-poste.md` § 6 bis) : `image.yml` 36120533900 et
`ci.yml` 36120533812, sur `b237912`, **succès** (259 dans l'image, 107 au contrat, 2 au navigateur,
Vitest 55 ; décompte identique à la mesure locale ; captures en artefact).

## 9. Limites connues et ce qui n'est pas prouvé

- **Titre de la barre du tableau de bord** : sur « / », Hermes affiche toujours « Sessions »
  (`web/src/lib/resolve-page-title.ts:37-39`) ; le SDK ne donne aucun accès à ce titre. La page
  porte son propre titre « Accueil ».
- **Marque au téléphone** : Hermes ne rend l'emplacement `header-left` que dans la colonne latérale
  (`App.tsx:617`) ; au téléphone, « ACP » n'apparaît qu'en ouvrant le menu, la barre du haut
  affiche « Hermes Agent » (`t.app.brand`).
- **`footer-right`** : annoncé par la documentation des greffons mais **pas rendu** par `App.tsx`
  en 0.21.5 : l'attribution « propulsé par Hermes Agent (licence MIT) » est donc dans le pied de
  l'Accueil (écart au cahier).
- **SDK « SPIKE »** : `sdk.d.ts` décrit `registerSlot(emplacement, nom)` et des erreurs
  « <statut>: <corps> » ; le code 0.21.5 fait `registerSlot(greffon, emplacement)` et lève une
  `ApiError` : les greffons suivent le code (testés contre les deux formes d'erreur).
- **Sélecteurs natifs** : le sélecteur de langue reste visible (tout autre choix est aussitôt
  annulé) ; ceux du thème et de la police restent utilisables et s'appliquent **jusqu'au
  rechargement** (les épingles serveur l'emportent au chargement suivant) : une police de Google
  Fonts choisie à la main serait donc chargée pendant la session. Le test navigateur ne prouve
  l'absence de requête externe qu'à l'usage normal. Au tout premier chargement d'un navigateur
  neuf, la page peut s'afficher brièvement en anglais avant que le greffon ne s'enregistre (non
  mesuré).
- **Pages natives** : restent en partie en anglais ; comptées au § 7, pas traduites.
- **Accueil et Catalogue** : rendus sur les vraies données de `/v1/meta` et `/v1/catalogue`
  depuis la seconde partie de P3 (test navigateur) ; context7 y apparaît « Inconnu » tant que la
  discussion du tableau de bord n'a pas été ouverte (Hermes ne découvre les serveurs MCP qu'à la
  première connexion `/api/ws`), et « Hors ligne » dans les tests, où son nom est résolu vers le
  bouclage local.
- **Non prouvé** : une réponse en français d'un **vrai** modèle (Railway seulement) ; le rendu sur un
  **vrai téléphone** (390×844 est une émulation Chromium, pas Safari iOS) ; l'accessibilité des
  pages **natives** de Hermes sous le thème `acp` (axe n'est lancé que sur nos deux pages) ; le
  thème clair (reporté, D18) ; un logo dessiné (D14).

## 10. Page « Projets » (étape P4, greffon `acp-projets`)

Référence fonctionnelle, vues et routes : [projets.md](projets.md) § 4 bis. Ce qui touche l'interface :

- **Troisième greffon, même forme** que les deux premiers : manifeste, bundle IIFE et feuille de style,
  sans code serveur ; sources `apps/interface/src/projets/` ; `esbuild.mjs` construit trois bundles,
  tous déterministes et vérifiés par la CI (`npm run check`, `git diff`). Onglet « Projets »
  (`/projets`, icône `FolderOpen`), placé **avant** « Catalogue » dans le groupe des greffons de Hermes
  (`before:catalogue` ; l'onglet de l'Accueil remplace « / » et n'a pas d'entrée de menu, donc
  `after:acp` le rejetterait en fin de groupe : `App.tsx:258-291`). Raccourci « Projets » ajouté à
  l'Accueil.
- **Règle des boutons** : le Catalogue reste en lecture seule ; la page Projets a des boutons, et
  **chacun appelle une route réelle et testée** (lancer, mettre en pause, reprendre, répondre,
  reprendre un triage, pause générale confirmée, notification de test). Rien d'autre : les cartes
  bloquées ou abandonnées restent en lecture seule (« Relancer » relève de P7), et le bouton de
  notification de test est désactivé, avec sa raison, tant que le canal n'est pas configuré.
- **Français** : le catalogue unique compte désormais **329** chaînes (291 distinctes), dont 220 pour la
  page Projets (274, 241 et 165 avant la relecture de P4) ; mêmes contrôles (arbre syntaxique,
  typographie, verrou du navigateur). Les champs de
  saisie portent `data-acp-donnee` : ce que le propriétaire tape est une donnée, pas un libellé.
- **Écriture** : `POST` en JSON par le `fetchJSON` du SDK (jamais un `fetch` direct : garde statique) ;
  le refus du greffon (`{"detail": {"code", "message"}}`) est affiché tel quel ; clé d'idempotence par
  envoi du formulaire.
- **Adresse** : le SDK n'expose pas le routeur de Hermes ; la page change de vue par son état. Depuis la
  relecture de P4, chaque changement de vue voulu par le propriétaire AJOUTE une entrée d'historique
  (`history.pushState`, état du routeur et `?profile=` gardés) et la page relit sa vue sur `popstate` :
  au téléphone, le geste « retour » ramène à la vue précédente au lieu de quitter la page (avant :
  `history.replaceState`, et « retour » quittait la page Projets). Le lien des notifications
  (`…/projets?projet=<id>`) ouvre le détail.
- **Sondage** : 15 s tant que la page est visible (`visibilitychange`), aucune lecture quand elle est
  cachée (D35) ; une actualisation ratée garde la dernière valeur lue et le dit.
- **Tests** : Vitest **93** (14 fichiers), dont `projets.test.tsx`, `projets-relecture.test.tsx` (13, les
  corrections de la relecture de P4) et `api-projets.test.ts` sur les formes relevées sur l'image ; navigateur `test_projets.py` (parcours complet aux deux formats, axe,
  cibles de 44 px, chaînes du catalogue seulement, aucune requête hors de l'origine). Les tests Vitest
  démontent désormais toute racine React restée montée après un test (ses minuteries de sondage
  couraient sinon dans le test suivant).
