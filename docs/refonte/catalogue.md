# Catalogue d'ACP — étape P3, skills et serveurs MCP épinglés

État du **25 septembre 2026**. Étape P3 du [plan de la refonte](plan.md), **seconde partie** : les
réglages prêts. Skills vendorisées à des commits épinglés (licences, provenance), skills maison en
français, verrou `catalogue.lock.json` et son vérificateur, chargement par Hermes, skills livrées
inertes désactivées, un seul serveur MCP côté Hermes (context7, distant), refus de démarrer sur un
serveur MCP local ou hors catalogue, route `/v1/catalogue` et blocs `catalogue` et `interface` de
`/v1/meta`. La première partie (thème, persona, greffons d'interface) est décrite par
[interface.md](interface.md). **Rien n'est déployé.**

Les références `fichier:ligne` sans préfixe désignent le source de Hermes Agent 0.21.5 (étiquette
`v2026.9.24`, commit `f97608f`).

## 1. En bref

| Élément | Dépôt | Image |
|---|---|---|
| Skills livrées (16 : 14 vendorisées, 2 maison) | `hermes/skills/<catégorie>/<skill>/` | `/opt/acp/skills` (root, lecture seule) |
| Licences et provenance par source | `hermes/skills/<catégorie>/{LICENSE,PROVENANCE.md}` | idem |
| Verrou du catalogue (`acp-catalogue/1`) | `hermes/catalogue/catalogue.lock.json` | `/opt/acp/catalogue/catalogue.lock.json` |
| Licences tierces, texte intégral | `hermes/THIRD_PARTY.md` | `/opt/acp/THIRD_PARTY.md` |
| Vérificateur | `scripts/verifier_catalogue.py` (+ `scripts/tests/test_verifier_catalogue.py`) | — |
| Réglages de skills et entrée MCP du volume | `hermes/image/acp_demarrage.py` (`appliquer_reglages_skills`) | écrits dans `/opt/data/config.yaml` par `05-acp` |
| Refus d'un serveur MCP stdio ou hors catalogue (D8) | `acp_demarrage.py` (`problemes_mcp_du_volume`) | `acp-gardes`, `05-acp`, relance du tableau de bord |
| context7 (serveur MCP distant) | `hermes/gere/config.yaml`, `EPINGLES_OBLIGATOIRES`, `garde_execution.py` | `/etc/hermes/config.yaml` (50 clés) |
| Route `/v1/catalogue`, blocs `catalogue` et `interface` de `/v1/meta` | `hermes/plugins/acp-poste/catalogue.py` | `/opt/hermes/plugins/acp-poste` |
| Faux context7 de test (TLS, SDK `mcp` 2.0.0) | `hermes/tests/outils/mcp_factice.py` | image de test seulement |

## 2. Ce que Hermes 0.21.5 impose (mesuré dans l'image épinglée)

- **Les listes de skills ne passent pas par la managed scope.** `skills.external_dirs` et
  `skills.disabled` sont lus dans `/opt/data/config.yaml` **brut** (`agent/skill_utils.py:250-385`,
  `_load_raw_config`) par le chargeur, l'index du prompt et la synchronisation. Témoin
  (`test_temoin_c1_external_dirs_en_managed_scope_est_ignore`) : posées **seulement** dans
  `/etc/hermes/config.yaml`, elles sont dans la config fusionnée mais le chargeur ne les voit pas.
  Une clé épinglée serait de plus **retirée** du volume à chaque sauvegarde de Hermes
  (`hermes_cli/config.py:2379-2390`). D'où leur écriture par `05-acp` dans le volume, **hors**
  managed scope (§ 6) ; le vérificateur refuse qu'elles soient épinglées.
- **Le tableau de bord ne découvre les serveurs MCP que si la config brute du volume en déclare
  un** (`hermes_cli/mcp_startup.py:53-65`, `read_raw_config`). Constaté en contrat : context7
  épinglé seulement dans la managed scope, la passerelle s'y connectait mais la discussion du
  tableau de bord, jamais. `05-acp` écrit donc aussi une entrée **vide** `mcp_servers.context7: {}`
  dans le volume ; tout son contenu vient de la managed scope, qui l'emporte feuille par feuille, et
  une sauvegarde de Hermes n'en retire que les feuilles épinglées, jamais l'entrée
  (`hermes_cli/config.py:1526-1537`).
- **Les outils MCP sont différés** : ils ne figurent pas parmi les outils offerts au modèle ; il les
  trouve par `tool_search` et les appelle par le pont `tool_call`, que Hermes déballe **avant** la
  garde d'exécution (P2) : la garde juge `mcp__context7__query_docs`, pas `tool_call`.
- **Nom des outils** : `mcp__<serveur>__<outil>`, tirets remplacés par « _ »
  (`tools/mcp_tool_schema.py:147-185`) : `mcp__context7__resolve_library_id`,
  `mcp__context7__query_docs`, relevés dans l'image et sur le vrai serveur.
- **Une liste de plateforme qui nomme un serveur MCP est une liste blanche** des serveurs
  (`hermes_cli/tools_config.py:678-690`) ; `no_mcp` les coupe tous.
- **La découverte lance tous les serveurs configurés** (`tools/mcp_tool_discovery.py:552-605`) :
  un serveur `command` (stdio) du volume est un processus lancé dans le conteneur. D'où D8 (§ 7).
- **Collisions** : deux skills de même nom (dossier local et dossier externe) font refuser
  `skill_view` (« Ambiguous skill name ») ; aucun nom du catalogue n'est pris par Hermes (§ 3).
- **GET /api/skills** calcule `enabled` depuis la config fusionnée et **filtre** une skill dont le
  frontmatter porte `environments: [kanban]` hors d'un worker kanban : `sdlc-review` (désactivée par
  ACP de toute façon) n'y figure pas.

## 3. Skills

### 3.1 Livrées dans l'image, côté Hermes (16)

Toutes **texte seul** : Markdown uniquement, aucun `scripts/`, aucun bit exécutable, aucun
`` !`cmd` `` (Hermes n'en exécute de toute façon aucun : `skills.inline_shell: false`). Les exemples
de code qu'elles contiennent sont du texte : sur Railway, l'agent n'a aucun outil pour les exécuter.
Texte amont **en anglais, intact** (D16) ; la persona impose la réponse en français.

| Skill | Source (commit) | Profil | Raison |
|---|---|---|---|
| `acp-redaction` | maison | base | Conventions de rédaction françaises (vouvoiement, typographie, « Inconnu », refus, comptes rendus, cartes) |
| `acp-profils` | maison | base | Réglages prêts par type de projet ; ce qui relève du poste |
| `emil-design-eng` | emilkowalski/skills `d16ebe60` | web | Finition d'interface |
| `animation-vocabulary` | idem | web | Nommer un effet de mouvement |
| `apple-design` | idem | web | Interaction et mouvement physiques |
| `mobile-native` | idem | web | Sites utilisés au téléphone |
| `pick-ui-library` | idem | web | Choisir une bibliothèque front |
| `animate` (+ `RECIPES.md`) | idem | web | Ordre des décisions d'une animation |
| `ask-sonner` (+ `API.md`) | idem | web | Notifications « toast » (Sonner) |
| `design-taste-frontend` | leonxlnx/taste-skill `c184364c` (`skills/taste-skill`) | web | Direction visuelle |
| `minimalist-ui` | idem (`skills/minimalist-skill`) | web | Style sobre |
| `high-end-visual-design` | idem (`skills/soft-skill`) | web | Style soigné |
| `security-review` (+ `cloud-infrastructure-security.md`) | affaan-m/ECC `5064474` (`v2.2.1`) | web | Solidité : sécurité |
| `accessibility` | idem | web | Solidité : WCAG 2.2 AA |
| `mle-workflow` | idem | données | Démarche d'apprentissage automatique |
| `python-patterns` | idem | données | Conventions Python |

Licences : **MIT** pour les trois dépôts (© 2026 Emil Kowalski, Leonxlnx, Affaan Mustafa), lues dans
leurs `LICENSE` au commit épinglé ; aucun `NOTICE` amont (vérifié par `--amont`). Les fichiers sont
recopiés **à l'octet près depuis les blobs git** (`git cat-file blob`), jamais depuis un arbre de
travail Windows ; seul le **dossier** de chaque skill suit le champ `name` de son frontmatter
(`taste-skill` → `design-taste-frontend`…), que Hermes utilise pour la nommer. Deux fichiers amont
portent des espaces en fin de ligne : `.gitattributes` les garde tels quels sans que `git diff
--check` les signale.

Analyse de sécurité de Hermes (`tools/skills_guard.py`, `scan_skill`, source « community »), sur
l'image : **16 verdicts « safe »**, installation admise ; constats de gravité moyenne seulement pour
`design-taste-frontend` (10 × `unpinned_npm_install`, exemples `npm install` du texte) et
`python-patterns` (1 × `unpinned_pip_install`).

### 3.2 Reportées au poste (étape P8), inscrites au verrou, non livrées

`find-animation-opportunities`, `improve-animations`, `review-animations`, `prototype` (Emil
Kowalski), `redesign-existing-projects` (taste-skill), `production-audit`, `browser-qa`,
`e2e-testing`, `canary-watch`, `benchmark` (ECC) : elles lisent le code d'un dépôt, écrivent des
fichiers, pilotent un navigateur ou mesurent un site déployé. Le Catalogue les montre « Poste —
reporté à P8 ».

### 3.3 Exclues (au verrou, avec leur raison)

- `agent-reach` : exclu côté Hermes par le propriétaire.
- `docx`, `pdf`, `pptx`, `xlsx` d'`anthropics/skills` : licence propriétaire, jamais vendorisées
  (le vérificateur exige ces quatre exclusions). Les skills `docx`, `pdf`, `powerpoint`, `xlsx`
  **livrées par Hermes** sont de Nous Research (MIT) : ce ne sont pas les mêmes.
- **`literature-review`** (ECC, `skills/scientific-thinking-literature-review`) : **écart au
  cahier**, qui la retenait (D5). Son historique amont la dit « salvaged » (commit `df32d6be`,
  « docs: salvage scientific research skills ») et son frontmatter porte `origin: community` :
  l'auteur et la licence d'origine ne sont pas établis. Dépôt public : non vendorisée tant qu'ils ne
  le sont pas. Le profil « recherche » repose donc sur `arxiv` et `competitor-news-monitor` (livrées
  par Hermes) et context7.
- Non retenues (D5, D12) : `animate-expo`, `write-swift`, `full-output-enforcement`, `gpt-taste`,
  `image-to-code`, `imagegen-frontend-web`, `imagegen-frontend-mobile`, `brandkit`,
  `stitch-design-taste`, `design-taste-frontend-v1`, `industrial-brutalist-ui`, `seo`,
  `pytorch-patterns`, `deep-research`.

### 3.4 Skills livrées par Hermes (58)

Classées une par une au verrou (`livrees`), le vérificateur exige que chacune le soit exactement une
fois :

- **44 désactivées par ACP** (écrites dans `skills.disabled` du volume) : leur flux principal
  documenté passe par un outil fermé sur Railway (terminal, fichiers, code, navigateur, cron,
  délégation) ou par un script. Écarts au cahier : `grounded-citations` (registre des sources tenu
  par `scripts/sources.py`), `email-inbox-triage` (dépend de `himalaya` et `google-workspace`,
  désactivées) et `spike` (écrit et exécute des prototypes) sont **désactivées**, le cahier les
  gardait ou les laissait « à confirmer ». Le recensement de l'image (`test_recensement_…`) imprime,
  pour chaque skill, ses scripts et les outils fermés qu'elle cite.
- **10 gardées** : `hermes-agent` (essentielle, jamais désactivable), `hermes-agent-skill-authoring`,
  `arxiv` (lecture par `web_extract`, documentée), `competitor-news-monitor`, `product-price-monitor`
  (la planification reste refusée), `claude-design`, `songwriting-and-ai-music`,
  `document-to-action-items`, `meeting-action-items`, `weekly-review-planning`.
- **4 réservées à macOS**, filtrées par Hermes sous Linux : `apple-notes`, `apple-reminders`,
  `findmy`, `imessage`.

Les 150 skills optionnelles de Hermes ne sont pas installées ; leurs noms sont au verrou pour le
contrôle des collisions.

## 4. Profils de projet

Dans le verrou (`profils`), affichés par le Catalogue, cités par la skill `acp-profils` (le
vérificateur exige qu'elle nomme chacun) ; `projet_lancer` (P4) les appliquera aux cartes.

| Profil | Skills côté Hermes | MCP côté Hermes | Poste (P8, reporté) |
|---|---|---|---|
| `base` | `acp-redaction`, `acp-profils`, `hermes-agent` | context7 | — |
| `web` | base + `emil-design-eng`, `apple-design`, `mobile-native`, `animate`, `animation-vocabulary`, `pick-ui-library`, `ask-sonner`, `design-taste-frontend`, `minimalist-ui`, `high-end-visual-design`, `claude-design`, `security-review`, `accessibility` | context7 | skills du § 3.2, Playwright MCP, Figma |
| `recherche` | base + `arxiv`, `competitor-news-monitor` | context7 | — |
| `donnees` | base + `mle-workflow`, `python-patterns` | context7 | — |

## 5. Verrou et vérificateur

`hermes/catalogue/catalogue.lock.json` : `hermes` (version, étiquette, commit, condensat de l'image) ;
`sources` (URL, commit, date, licence, auteur, catégorie) ; `categories` (SHA-256 de `DESCRIPTION.md`,
`LICENSE`, `PROVENANCE.md`) ; `skills` (nom, source, chemin amont, cible `hermes` ou `poste`, état,
fichiers avec SHA-256 et blob git, profils, description et raison en français) ; `livrees` ; `mcp` ;
`profils` ; `exclus`.

`python scripts/verifier_catalogue.py` (bibliothèque standard, code 1 et message français) vérifie :
empreintes (et blobs git) de chaque fichier, dans les deux sens ; licences libres admises, `LICENSE`
exact, `PROVENANCE.md` et `THIRD_PARTY.md` cohérents ; nom du frontmatter = dossier = verrou ;
collisions (catalogue, 58 livrées, 150 optionnelles, exclus) ; exclusions obligatoires ; texte seul
pour la cible Hermes ; outils MCP = noms que Hermes leur donne, présents dans `OUTILS_ADMIS` de la
garde (AST) et épingles de `EPINGLES_OBLIGATOIRES` (AST) ; `skills.*` jamais épinglés ; classement
des 58 livrées ; profils. `--amont` télécharge chaque fichier au commit épinglé
(`raw.githubusercontent.com`) et le compare octet pour octet, et exige qu'aucun `NOTICE` n'existe.

**Changer le catalogue** passe par une PR : fichiers recopiés depuis le blob du commit épinglé
(`git -C <clone> cat-file blob <commit>:<chemin> > hermes/skills/<catégorie>/<skill>/<fichier>`),
verrou mis à jour (le vérificateur affiche l'empreinte et le blob attendus en cas d'écart),
`PROVENANCE.md` et `THIRD_PARTY.md` complétés, `--amont` vert.

## 6. Au démarrage (`05-acp`)

`appliquer_reglages_skills` garantit dans `/opt/data/config.yaml` : `skills.external_dirs` =
`/opt/acp/skills` en tête (entrées du propriétaire gardées), `skills.disabled` ⊇ les 44 skills
désactivées (entrées du propriétaire gardées), `mcp_servers.context7` présent (vide). Écriture
**seulement si quelque chose change**, atomique, propriétaire et mode conservés (`hermes:hermes
0640`), par le même chargeur « aller-retour » que Hermes (`ruamel.yaml`) : les commentaires restent ;
avant d'écrire, le résultat relu par PyYAML ne doit différer de l'original **que** par ces clés.
États publiés dans `/run/acp/etat-demarrage.json` (schéma 3, bloc `catalogue`) : `conforme`,
`applique`, `cree`, `illisible` (YAML invalide ou forme inattendue : **rien n'est écrit**, alerte
dans `/v1/meta`) ; un lien symbolique à la place du fichier refuse le démarrage.

Conséquence assumée : le propriétaire peut modifier ces listes depuis le tableau de bord (réactiver
`codex`, retirer le dossier du catalogue) ; `/v1/meta` et `/v1/catalogue` le signalent aussitôt et le
démarrage suivant les rétablit. L'agent, sans outil de fichiers, ne le peut pas.

## 7. MCP

### 7.1 Côté Hermes : context7 seulement

Serveur **distant** en HTTP (`https://mcp.context7.com/mcp`, entrée officielle
`optional-mcps/context7/manifest.yaml`, sans authentification) : **aucun processus lancé dans le
conteneur**. Trois couches, chacune avec son témoin négatif :

1. **Managed scope** (8 clés, 42 → 50) : `url`, `enabled: true`, `ssl_verify: true`,
   `sampling.enabled: false` (le serveur ne peut pas faire générer le modèle de Hermes),
   `elicitation.enabled: false` (aucune saisie demandée), `tools.include: [resolve-library-id,
   query-docs]`, `tools.resources: false`, `tools.prompts: false`. Un volume hostile
   (autre URL, désactivé, échantillonnage rallumé, outil piège inclus) ne change rien.
2. **Liste de la plateforme cli** : `context7` à la place de `no_mcp` (tableau de bord, workers
   kanban, `hermes -z`) ; `api_server` et `cron` gardent `no_mcp`.
3. **Garde d'exécution** : deux noms exacts de plus, **26 outils admis** ; tout autre outil MCP,
   d'un autre serveur ou du même, est refusé.

Risques dits : la sortie et la description des outils viennent d'un tiers (Hermes l'encadre comme
« donnée non fiable », `<untrusted_tool_result>`) ; les questions envoyées révèlent le sujet du
projet à Upstash ; limites de débit anonymes partagées par l'adresse de sortie de Railway ; la
version du serveur distant n'est pas épinglable (noms d'outils vérifiés par la sonde) ; **les
conditions d'utilisation du service n'ont pas été lues**. Aucune clé d'API (D11). La première
connexion au vrai serveur a pris **2,46 s** ; le tableau de bord n'attend la découverte que
1,5 s (`mcp_discovery_timeout`) avant de figer les outils d'une session : context7 peut manquer au
premier tour d'une toute première session et rejoindre la suivante (rafraîchissement de Hermes
entre les tours) ; non épinglé, pour ne pas retarder chaque première réponse quand le service est
en panne.

### 7.2 Reportés au poste (P8) ou refusés

| MCP | Côté Hermes | Côté poste |
|---|---|---|
| Playwright (`@playwright/mcp`, 0.0.82 relevé au registre) | refusé : lance un navigateur local | P8, sans `browser_run_code_unsafe` |
| Figma (`https://mcp.figma.com/mcp`) | refusé : OAuth par enregistrement dynamique sous l'identité « Claude Code » usurpée par Hermes, jetons dans le volume | P8, après sonde |
| deepwiki (HTTP, sans authentification) | non retenu en P3 (D7) : un seul MCP prouvé de bout en bout | — |
| Agent-Reach | exclu par le propriétaire | hors v1 |
| tout serveur `command` (stdio) | **refus de démarrer** (D8) | selon `poste.toml` (P8) |

### 7.3 Refus d'un serveur MCP local ou hors catalogue (décision D8)

`acp-gardes` (avant tout service), `05-acp` et la garde de relance du tableau de bord et des
passerelles refusent, en français, tout `mcp_servers.<nom>` du `config.yaml` du volume ou d'un
profil qui porte un `command`, ou dont le nom n'est pas un serveur actif du catalogue. Un fichier
illisible est seulement signalé (Hermes ne le lirait pas non plus). `diagnostiquer` (maintenance)
les liste. Retrait : procédure de maintenance de [railway.md](railway.md) § 10 b.

## 8. Route `/v1/catalogue` et `/v1/meta`

`GET /api/plugins/acp-poste/v1/catalogue` (session obligatoire, `401` sinon) : le verrou et, pour
chaque skill côté Hermes, l'état vu par le chargeur du tableau de bord (`active`, `desactivee`,
`absente`, `ambigue`) ; côté poste, `reportee-p8` ; pour context7, `connexion`
(`connecte`, `hors_ligne`, `inconnu` avant la première découverte), statut de Hermes et nombre
d'outils exposés ; `hors_catalogue`, `collisions`, `desactivations_non_appliquees`, alertes en
français (dossier du catalogue retiré, skills livrées réactivées, collision, serveur MCP hors
catalogue ou absent du volume). `catalogue.py` est le seul module du greffon qui importe les
internes des skills et des MCP de Hermes, chacun depuis son module de définition.

`/v1/meta` gagne `catalogue` (`verrou_sha256`, `skills_actives`, `skills_attendues`, `context7`,
conformité, nombre d'écarts), `interface` (versions des deux greffons d'interface, `sdk_attendu:
"1.x"`) et les alertes du catalogue ; contrat `acp-poste/1` inchangé (ajouts seulement).

## 9. Tests et preuves

Commandes (en plus de celles de [interface.md](interface.md) § 8) :

```sh
python scripts/verifier_catalogue.py            # hors ligne
python scripts/verifier_catalogue.py --amont    # réseau : comparaison avec les dépôts amont
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint /opt/hermes/.venv/bin/hermes acp-hermes:p3 mcp test context7   # sonde réelle
```

Preuves locales du 25 septembre 2026, chaque commit vérifié sur son propre arbre (détail :
`docs/reprise-poste.md` § 6 ter) : dépôt **342** réussis ; dans l'image **323** ; contrat **117**
(dont 10 du catalogue) ; navigateur **2** ; vérificateur hors ligne et `--amont` : code 0 ; aucun
échec, aucun test ignoré. En CI (`image.yml` 36136507335 et `ci.yml` 36136507298, sommet `ec43987`) :
mêmes nombres (323, 117, 2 ; dépôt 342 sous Windows, 333 et 9 ignorés sous Linux), `--amont` vert,
sonde réelle de context7 connectée (1 600 ms, 2 outils) ; détail : `docs/reprise-poste.md` § 6 ter.

Tests nouveaux :

- dépôt : `scripts/tests/test_verifier_catalogue.py` (45 : dépôt conforme, un témoin rouge par
  règle, `--amont` simulé : conforme, différent, absent, `NOTICE`, réseau coupé) ;
- image : `test_catalogue.py` (fichiers = verrou, root, texte seul ; noms lus par Hermes ; aucune
  collision avec les listes RÉELLES ; `scan_skill` ; recensement des 58 ; réglages du volume : absent,
  semé par l'image avec commentaires, entrées du propriétaire, chaîne `hermes config set`, 5 formes
  illisibles, lien refusé, idempotence ; témoin C1 ; chargeur = catalogue ; témoin sans réglages ;
  `GET /api/skills` exact ; `skill_view` ; index des skills d'une nouvelle session),
  `test_mcp.py` (SDK, noms, config fusionnée contre un volume hostile, surfaces après découverte
  contre le faux context7, tour cli complet, api_server jamais, garde contre `piege`, témoins : sans
  la liste cli, sans `tools.include`, sans la garde, échantillonnage rallumé ; D8),
  `test_catalogue_route.py` (conforme, context7 connecté puis hors ligne, skill réactivée,
  `external_dirs` retiré, collision et hors catalogue, serveur hors catalogue, verrou illisible,
  chargeur illisible, route montée) ; tests de P2 et P3 ajustés sans être affaiblis (50 clés,
  26 outils, schéma 3) ;
- contrat : `test_catalogue_contrat.py` (réglages écrits par `05-acp`, `GET /api/skills` exact par
  le vrai tableau de bord, route authentifiée, **discussion `/api/ws` → faux context7 dans un autre
  conteneur** sans processus lancé, basculement depuis le tableau de bord puis redémarrage,
  `external_dirs` retiré puis rétabli, deux démarrages successifs sans écriture, relance refusée sur
  un serveur stdio, démarrage refusé sur un serveur stdio ou hors catalogue) ; tout conteneur Hermes de test résout `mcp.context7.com` vers son
  bouclage local (aucun appel au vrai serveur) ;
- navigateur : l'Accueil affiche 16 / 16 skills actives, le Catalogue sert la route et ses 26
  entrées.

Protections et leurs témoins négatifs (chaque test prouve ce qui se passerait sans la protection,
dans l'image épinglée ; aucune image altérée n'a été construite pour cette seconde partie) :

| Protection | Témoin : sans elle… |
|---|---|
| Réglages écrits par `05-acp` dans le volume | `test_temoin_sans_les_reglages_les_skills_acp_sont_absentes` : aucune skill d'ACP chargée, les 44 inertes offertes |
| Réglages hors managed scope | `test_temoin_c1_external_dirs_en_managed_scope_est_ignore` : épinglés, le chargeur ne les voit pas |
| `context7` dans `platform_toolsets.cli` | `test_temoin_sans_context7_dans_la_liste_cli_aucun_outil` : aucune surface n'offre context7 |
| `tools.include` | `test_temoin_sans_tools_include_l_outil_piege_est_offert` : l'outil piège est offert |
| Garde (noms exacts) | `test_temoin_sans_la_garde_l_outil_mcp_non_admis_s_execute` : l'outil piège s'exécute sur le serveur |
| `sampling.enabled: false` | `test_temoin_echantillonnage_active_la_demande_atteint_hermes` : le serveur fait générer le modèle de Hermes |
| Refus D8 | `test_temoin_d8_sans_refus_un_serveur_stdio_du_volume_est_lance` : la découverte lance le processus |
| Entrée `mcp_servers.context7` du volume | constaté en contrat avant correction (non automatisé) : la discussion du tableau de bord n'obtient pas context7 (`tool_call` refusé par la garde) |
| Règles du vérificateur | un test rouge par règle (`scripts/tests/test_verifier_catalogue.py`) |

Sonde **réelle** de context7 (image `acp-hermes:p3e`, 25/09/2026 11:05 UTC, `hermes mcp test
context7`) : connecté en 2 459 ms, **2 outils** `resolve-library-id` et `query-docs`. En CI : étape
non bloquante de `image.yml`, sortie en artefact `sonde-context7`.

## 10. Limites et ce qui n'est pas prouvé

- context7 **depuis Railway** (sortie réseau, limites de débit), et son usage réel par un vrai
  modèle : à relever ([railway.md](railway.md) § 7) ; conditions du service non lues.
- Premier tour d'une première session du tableau de bord : context7 peut manquer (§ 7.1).
- La qualité des plans avec les skills vendorisées : non mesurable avant P4. Hermes pousse le
  modèle à charger toute skill « même partiellement pertinente » ; `design-taste-frontend` fait
  87 Kio.
- `GET /api/skills` classe les skills d'ACP en provenance « agent » (ni livrées ni du hub : mesuré),
  provenance pour laquelle le tableau de bord propose l'édition et la suppression. L'uid de Hermes ne
  peut rien écrire sous `/opt/acp` (prouvé) ; ce qu'affichent alors ces boutons n'a pas été relevé.
- Profils de `/opt/data/profiles/*` : seul le `config.yaml` racine reçoit les réglages ; un profil
  nommé ne voit pas le catalogue (seul `default` est lançable : `kanban.dispatch_profiles`).
- L'effet de `skills.disabled` sur les workers kanban : même chargeur (surface sondée), non prouvé
  par un vrai worker en P3.
