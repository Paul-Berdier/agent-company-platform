# Rapport d'acceptation

Date d'état : 14 septembre 2026
Périmètre évalué : Lot G `0.8.0` dans l'arbre de travail, construit sur le Lot F publié
`0.7.0`, sans service externe ni dépense réelle. Le Lot G n'est ni fusionné, ni taggé,
et aucune CI distante de cet arbre n'est revendiquée.

## Verdict

**0 scénario sur 20 est accepté de bout en bout.** Dix-huit scénarios disposent d'une
brique réelle et de tests ciblés ; deux restent non satisfaits (4 et 20). Le connecteur
ComfyUI fait passer le scénario 17 à **Partiel** et l'aperçu GLB renforce le scénario 16,
mais les preuves externes restent incomplètes :

- **aucun navigateur réel n'a été lancé** et **aucun test Playwright réel n'a été
  exécuté** pour cette version. Le reporter est prouvé sur des objets Playwright
  synthétiques ; l'exécuteur du worker est prouvé sur
  `apps/worker/tests/fake_playwright_runner.py`, un programme déterministe lancé par
  `sys.executable` qui écrit un NDJSON réaliste et des fichiers de pièces jointes ;
- aucune capture d'écran d'une session de test réelle n'existe, donc aucune image de
  session n'a jamais été affichée par le Studio ;
- aucun parcours navigateur des écrans Studio et Bibliothèque n'a été effectué : les
  deux sont couverts par des tests Vitest sur le DOM ;
- aucune origine d'aperçu séparée n'est configurée ; une demande d'aperçu échoue donc
  en `424` avant création du jeton, sans repli sur l'origine de l'API ;
- le parcours du Lot F démarre une API et une base SQLite temporaires ; il ne lance ni
  worker distant, ni Hermes, ni fournisseur payant, ni navigateur ;
- le harnais E2E, l'aperçu 3D, ComfyUI et les points de spawn Codex/Claude sont livrés,
  mais n'ont été exercés contre aucun navigateur, GPU, service ou modèle réel ;
- les migrations PostgreSQL, Railway et la restauration restent au Lot H.

Le scénario 7 du Lot D a été rejoué contre des services réellement démarrés (API métier
dans son propre processus, serveur MCP Streamable HTTP sur le bouclage) : **24 étapes
sur 24 réussies**, par un script versionné (`scripts/verify_mcp_journey.py`). Il n'est
pas retenu comme « Accepté » : il ne couvre que le transport `http`, le serveur
interrogé a été écrit pour la vérification — ce n'est pas un serveur MCP tiers — et il
n'exerce aucun parcours navigateur.

Statuts : **Accepté** exige le parcours complet et reproductible ; **Partiel**
signifie qu'une brique réelle existe mais qu'un élément bloquant manque ; **Non
satisfait** signifie que le parcours principal n'est pas livré.

## Matrice des vingt scénarios

| # | Scénario | Statut | Preuve disponible et manque bloquant |
|---:|---|---|---|
| 1 | Première connexion sécurisée et reconnexion | **Partiel** | Bootstrap unique, Argon2id, session révocable/expirable, cookie `HttpOnly`, CSRF, restauration web et login CLI sont testés. Pas d'E2E navigateur sur services démarrés. |
| 2 | Connexion Hermes avec diagnostic d'échec exploitable | **Partiel** | Diagnostic typé et frontière serveur testés avec transports simulés. Aucune instance ni clé Hermes réelle. |
| 3 | Conversation persistante et reprise depuis web/CLI | **Partiel** | Conversations et tours sont persistés ; web et CLI reprennent par `GET`. Pas de streaming ni E2E Hermes réel. |
| 4 | Import d'un projet sans écrasement du travail existant | **Non satisfait** | Création de projet disponible, mais pas d'import de dépôt/dossier ni test produit de conflit. |
| 5 | Mission réellement exécutée par au moins un agent configuré | **Partiel** | Le worker lance un vrai processus local configuré et le Lot G raccorde les capacités `codex_cli` / `claude_code` à la boucle réelle avec cwd projet, profil séparé, fencing, budget, événement terminal obligatoire et preuve expurgée. Seuls des exécutables déterministes de test ont été lancés : aucun CLI agent authentifié, modèle ni effet sur un dépôt utilisateur. |
| 6 | Isolation des fichiers, secrets et contexte entre deux projets | **Partiel** | RBAC et conversations inter-projets sont testés ; le runner filtre son enveloppe et son environnement ; le coffre du Lot D chiffre les secrets, limite une portée `project` à son projet et n'expose aucune valeur ; le Lot E ajoute un stockage de livrables privé dont la lecture est filtrée par les projets accessibles. La racine d'exécution ne limite pas les lectures du compte OS : deux projets non mutuellement fiables ne doivent pas partager le même worker. |
| 7 | Ajout, test, activation et révocation d'un MCP | **Partiel** | Parcours complet testé sur les deux transports : déclaration, refus d'un secret en clair, diagnostic HTTP épinglé, autorisation puis diagnostic `stdio` sur le runner désigné, rattachement limité à un sous-ensemble d'outils, activation, rollback, révocation et audit (`apps/api/tests/test_mcp_servers.py`, `apps/worker/tests/test_mcp_probe.py`). Le transport `http` a en outre été rejoué contre des services réellement démarrés : **24/24 étapes**, injection du secret observée côté serveur MCP et jamais republiée. Le script de ce parcours est versionné (`scripts/verify_mcp_journey.py`). Manque bloquant : aucun serveur MCP **tiers** contacté, aucun parcours navigateur, et le transport `stdio` reste prouvé par un serveur déterministe local. |
| 8 | Import d'un skill, affichage des fichiers et activation limitée | **Partiel** | Import manuel, dossier autorisé, archive et GitHub épinglé ; arborescence, `SKILL.md`, dépendances, licence et contrôle indicatif affichés ; approbation exigée quand la portée augmente ; activation sur le projet A absente des extensions du projet B ; révocation auditée (`apps/api/tests/test_skills.py`, `test_extensions.py`). Manque bloquant : aucun dépôt GitHub réel ni archive de skill tierce ; le transport GitHub est prouvé sur `httpx.MockTransport`. |
| 9 | Refus d'une installation ou d'une action non autorisée | **Partiel** | CSRF/RBAC et frontières worker sont testés ; le runner refuse avant spawn les autonomies non garanties et toute commande hors allowlist ; un opérateur ou un lecteur est refusé sur `/mcp/servers`, `/skills/import` et `/secrets`, un membre d'un autre projet sur un rattachement, un lancement `stdio` non autorisé n'est jamais distribué, et `GET /mcp/servers/{id}` ne nomme que les rattachements des projets accessibles. Manque bloquant : les refus sont prouvés sur des sources locales et un parcours API, pas sur une installation réelle ni un parcours navigateur. |
| 10 | Tests web avec résultat structuré et capture de la session réelle | **Partiel** | Le résultat structuré est livré et testé de bout en bout **sur un lanceur simulé** : reporter NDJSON, ingestion worker authentifiée, statuts distincts et faux succès refusés. Le Lot G ajoute un paquet `@playwright/test` isolé et un parcours réel opt-in, mais celui-ci ouvre une tentative existante et ne remplace pas l'exécution reporter → worker. **Manque bloquant : l'opt-in n'a jamais été activé, aucun navigateur ni test Playwright réel n'a été lancé et aucune capture de session réelle n'existe.** |
| 11 | Consultation d'une trace et d'une capture après échec | **Partiel** | Les pièces jointes d'un cas en échec sont téléversées par le worker, stockées hors base, référencées par empreinte et type, puis listées et téléchargeables par le Studio, la bibliothèque et `acp artifacts get`. Une trace et un rapport HTML restent en téléchargement forcé avec `nosniff` et CSP. **Manque bloquant : aucune trace ni capture n'a été produite par un échec Playwright réel ; pas de trace viewer intégré.** |
| 12 | Déconnexion/reconnexion sans perte d'historique ni double lancement | **Partiel** | Le Lot E fournit le flux SSE authentifié avec reprise par curseur et le Lot F ajoute des clés stables pour créer une routine, déclencher manuellement ou faire tourner un webhook. Une `fire_key` unique en base arbitre deux matérialisations concurrentes ; le web et le CLI conservent la clé après une réponse incertaine. **Manque bloquant : aucune coupure réseau réelle, aucun `EventSource` de navigateur, aucun effet tiers permettant d'observer l'absence de double effet externe et aucun outbox.** |
| 13 | Approbation, refus, expiration et arrêt réel d'une exécution | **Partiel** | Acceptation/refus, empreinte et expiration d'approbation, stop et arrêt d'arbre sont couverts. Le runner local refuse les actions nécessitant approbation au lieu de les demander. |
| 14 | Runner perdu puis reprise contrôlée sans double effet | **Partiel** | Lease, fencing, worker obsolète, interruption et nouvelle tentative sont testés. Aucun effet tiers réel ne permet de prouver l'absence de double effet externe. |
| 15 | Routine planifiée sans doublon et fuseau Europe/Paris | **Partiel** | Routine durable créée désactivée, cron en heure locale IANA et intervalles, heures inexistantes omises et première heure ambiguë retenue, calendrier UTC/local/décalage, rattrapage `skip`/`run_once`, limite de concurrence, bail singleton/fencing et contrainte unique de `fire_key`. La concurrence est testée sur une base SQLite fichier et les bascules Europe/Paris sur plusieurs années. Web, CLI et parcours HTTP local existent. **Manque bloquant : aucun worker distant, aucune exécution Hermes réelle, aucun navigateur réel, aucune validation PostgreSQL/multi-processus de production.** |
| 16 | Livrable téléchargeable et aperçu 3D réel | **Partiel** | Stockage privé, téléversement idempotent, quotas, `Range`, liens signés, bibliothèque et CLI sont livrés. Le Lot G valide strictement et scelle les `.glb` v2 auto-contenus, y compris buffers/vues/accessors/strides et en-têtes/dimensions/budgets cumulés des images, garde `.gltf` en téléchargement et charge `@google/model-viewer` à la demande dans Studio/Bibliothèque. **Manque bloquant : aucun GLB n'a été rendu dans un navigateur réel, aucune origine d'aperçu séparée n'est déployée, aucun livrable ne provient d'une exécution réelle et le stockage reste local. Les limites applicatives ne remplacent pas l'isolation du décodeur/GPU.** |
| 17 | Génération d'image réelle si backend configuré | **Partiel** | Le gateway privé expose un diagnostic et une génération ComfyUI à workflow local fixe, prompt seul injecté, appels `/prompt`/`history`/`view` bornés, image PNG/JPEG/WebP vérifiée, concurrence/cache bornés et tombstone après soumission incertaine. **Manque bloquant : aucun ComfyUI/GPU/modèle réel contacté, aucune idempotence durable entre redémarrages ou réplicas, aucun raccordement au worker ni versement en artefact.** |
| 18 | Budget atteint, fournisseur indisponible et stockage saturé | **Partiel** | Permis avant planification/exécution/évaluation, ledger idempotent, coûts/jetons/appels et saturation sont appliqués localement. Le Lot G obtient un permis avant l'invocation CLI, refuse capacité/backend/scope incompatibles et refuse une mission exigeant une borne de coût/jetons inconnue. Les écritures Codex concurrentes d'une même racine sont sérialisées par un verrou interprocessus coopératif ; un nettoyage incertain place la racine en quarantaine durable jusqu'à levée opérateur. ACP lance au plus un processus CLI de premier niveau ; `spawned_agents=1` et son scope explicite ne comptent aucun descendant et ne démontrent donc pas le plafond global `max_spawned_agents_per_run`. **Manque bloquant : aucun fournisseur payant, stockage objet externe, volume hébergé ni incident disque réel n'a été éprouvé ; verrou/quarantaine exigent des ACL parent et des garanties de partage réseau opérateur.** |
| 19 | Authentification des médias, événements et fichiers privés | **Partiel** | Flux utilisateur authentifié, RBAC par page, fichiers privés, liens signés liés au demandeur, événements sans média et WebSocket anonyme fermé restent en place. Le Lot G exige une origine d'aperçu distincte de l'API et des origines CORS : absente ou invalide, la route répond `424` avant jeton, sans repli même origine. **Manque bloquant : aucune origine séparée déployée, aucun parcours navigateur ni parcours de bout en bout versionné pour cette chaîne.** |
| 20 | Sauvegarde/restauration et migration de données existantes | **Non satisfait** | Upgrade SQLite ad hoc et non versionné, avec reconstruction contrôlée de tables et sauvegarde préalable requise ; PostgreSQL versionné et restauration reportés au Lot H. |

## Preuves locales du Lot G

Les résultats ciblés obtenus sur l'arbre de travail sont : 33 tests unitaires des
garde-fous E2E, sortie par défaut `[E2E SKIPPED]`, spec Playwright collectée puis
ignorée ; 311 tests web sur 24 fichiers ; 237 tests API livrables/signatures/GLB ;
58 tests ciblés du connecteur ComfyUI et sa suite gateway de 145 tests ; 299 tests
worker ; 59 tests reporter et 74 tests du moteur. Le typecheck TypeScript, le build
Vite et la compilation Python réussissent.
La syntaxe de la commande Codex a été contrôlée contre l'aide du CLI installé sans
exécuter de mission ni appeler un modèle.

Ces sous-ensembles se recouvrent avec les suites historiques et ne doivent pas être
additionnés en un total global. Aucun de ces résultats ne prouve une cible E2E, un
rendu GLB, un ComfyUI ou un agent externe réel. Une passe Python complète intermédiaire,
antérieure aux derniers correctifs de sécurité ensuite rejoués sur toutes les suites
affectées ci-dessus, donne **2 418 réussis, 4 ignorés, 1 avertissement de dépréciation
Starlette connu** en Python 3.13.3 local ; la CI cible Python 3.12 et n'a pas été
exécutée à distance.

## Référence publiée du Lot E

Les résultats ci-dessous ont été obtenus le 13 septembre 2026 dans le worktree
`lot-e`, après les corrections de revue et la synchronisation des versions sur
`0.6.0`. Cette version a ensuite été fusionnée par la PR #5 au commit `b7d8a44` et
étiquetée `v0.6.0`, après observation d'une CI verte. Ces nombres ne sont pas réutilisés
comme preuve de l'arbre de travail du Lot F.

### Environnement exact

| Élément | Valeur |
|---|---|
| Système | Windows 10 Pro `10.0.19045` |
| Interpréteur des suites | `.venv\Scripts\python.exe` — **lanceur d'environnement virtuel Windows**, Python `3.12.0` |
| Node.js / npm | `v24.19.0` / `11.17.0` |
| CI GitHub Actions | `ubuntu-latest`, Python `3.12`, Node `22` (`.github/workflows/ci.yml`) — verte observée sur la PR #5 avant fusion |

L'interpréteur retenu n'est pas un détail : sous Windows, le `python.exe` d'un
environnement virtuel est un **lanceur** qui exécute l'interpréteur réel dans un
processus enfant. C'est exactement la topologie que le correctif Job Object du Lot D
devait couvrir, et que l'exécution de tests web du Lot E réutilise telle quelle.

### Suites exécutées

| Commande ou suite | Résultat | Ce que cela prouve | Limite |
|---|---:|---|---|
| `./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **1 627 réussis, 4 ignorés ; 2 avertissements de dépréciation connus** | API, worker, CLI, services et contrats Python | aucun service externe, aucun navigateur |
| tests API (`apps/api/tests`) | **751 réussis, 1 ignoré** | curseur et flux SSE, RBAC du flux, livrables et liens signés, ingestion de tests, rétention, plus tout l'acquis des Lots B à D | client de test ASGI, transports simulés |
| tests worker (`apps/worker/tests`) | **223 réussis, 3 ignorés** | exécution de tests web, arrêt d'arbre, refus de pièce jointe hors périmètre, NDJSON absent ou corrompu, quota, expurgation | lanceur déterministe, jamais Playwright |
| tests CLI (`apps/cli/tests`) | **365 réussis** | `runs events`, `runs tests`, `artifacts list/get/link`, `open --studio`, codes de sortie | client HTTP simulé |
| contrats, gateway et event-service | **288 réussis** (192 contrats, 87 gateway, 9 event-service) | contrats partagés `StreamEvent`/`EventPage`/`testing`/`operations`, règle d'expurgation, adaptateur Hermes | transports simulés |
| fichiers de test propres au Lot E (Python) | **509 tests collectés** | `test_events_stream`, `test_artifacts_content`, `test_testing_service`, `test_retention`, `test_artifact_signing`, `test_artifacts_storage`, `test_lot_e_models`, `test_web_tests`, `test_cli_events_artifacts` | sous-ensemble du total ci-dessus |
| `npm run typecheck --workspace @acp/web` | **réussi** | cohérence TypeScript | pas le comportement runtime |
| `npm test --workspace @acp/web` | **262 réussis (17 fichiers)** | clients `events-api`, `artifacts-api`, `testing-api`, filtres de la bibliothèque, câblage du Studio, plus l'acquis du Lot D | DOM simulé, **pas de navigateur réel** |
| dont fichiers du Lot E (web) | **113 réussis (5 fichiers)** | `events-api`, `artifacts-api`, `testing-api`, `library-ui`, `studio-wiring` | idem |
| `npm test --workspace @acp/playwright-reporter` | **59 réussis (1 fichier)** | statuts distincts, `flaky`, troncature, ANSI retiré, NDJSON valide ligne par ligne, pièce jointe par chemin et en ligne, absence de `ACP_REPORT_FILE` | objets Playwright **synthétiques** |
| `npm test --workspace @acp/pixel-office-engine` | **74 réussis (7 fichiers)** | non-régression du moteur legacy | hors parcours principal |
| `npm run build:web` | **réussi** | bundle Vite productible | pas un déploiement |
| `./.venv/Scripts/python.exe scripts/check_version.py` | **réussi** | tous les composants publiables portent `0.6.0` | n'implique aucune publication |

### Preuves ciblées du Lot F

Le Lot F possède des tests ciblés dans les suites suivantes :

| Domaine | Fichiers principaux | Propriété visée |
|---|---|---|
| contrats et fuseaux | `packages/contracts/tests/test_schedule.py`, `test_automations_contracts.py` | cron/intervalle stricts, DST, cohérence UTC/local/décalage |
| base | `packages/database/tests/test_automation_models.py`, `test_lot_f_schema_extensions.py` | contraintes, clés étrangères, `fire_key` unique et upgrade SQLite |
| API | `apps/api/tests/test_automations.py`, `test_scheduler.py`, `test_budgets.py`, `test_alerts.py` | RBAC/CSRF, rejeu, bail/fence, rattrapage, budgets et alertes |
| stockage | `apps/api/tests/test_artifacts_content.py`, `test_artifact_quota_concurrency.py` | `507`/`503`, alerte expurgée, réparation et quota concurrent |
| worker | `apps/worker/tests/test_automation_scheduler.py`, `test_budget.py`, `test_real_worker.py` | boucle de tick et permis autour des phases réelles |
| CLI | `apps/cli/tests/test_cli_automations.py`, `test_cli.py` | commandes, validation, secret hors argv, codes de sortie et rejeu |
| web | `apps/web/tests/automation-*.test.ts`, `mission-routine.test.ts` | contrats, écrans, états, idempotence et proposition de routine |

Le relevé final local du Lot F a été produit le 14 septembre 2026 dans le worktree
`lot-f`, sous Windows 10 Pro `10.0.19045`, avec `.venv\Scripts\python.exe` (Python
`3.12.0`), Node `v24.19.0` et npm `11.17.0` :

| Commande ou suite | Résultat |
|---|---:|
| `python -m pytest -q -p no:cacheprovider` | **2 291 réussis, 7 ignorés, 2 avertissements** en 408,18 s |
| API | **867 réussis, 1 ignoré** |
| worker | **253 réussis, 3 ignorés** |
| CLI | **430 réussis, 3 ignorés** |
| contrats / base / event-sdk / gateway / event-service | **741 réussis** (`574 / 66 / 5 / 87 / 9`) |
| `npm run typecheck --workspace @acp/web` | **réussi** |
| `npm test --workspace @acp/web` | **295 réussis, 23 fichiers** |
| `npm test --workspace @acp/playwright-reporter` | **59 réussis** |
| `npm test --workspace @acp/pixel-office-engine` | **74 réussis** |
| `npm run build:web` | **réussi** |
| `python scripts/check_version.py` | **réussi**, tous les composants sur `0.7.0` |
| `python scripts/verify_automation_journey.py` | **62/62 étapes réussies**, code `0` |

Le parcours impose son `PYTHONPATH`, vérifie que ses imports proviennent du worktree,
puis démarre l'API en portée worker globale et la redémarre sur la même base en portée
projet. Il prouve ainsi séparément le planificateur et l'exécuteur sans relâcher la
politique d'enrôlement.

Les deux avertissements Python proviennent de dépréciations dans les dépendances —
`StarletteDeprecationWarning` sur l'usage de `httpx` par `starlette.testclient`, et la
dépréciation de l'alias `anyio.abc.BlockingPortal` — et sont non bloquants. Le build
Vite signale six URL d'assets LimeZu sous licence, non distribués et résolus au runtime
après installation locale, ainsi que la taille du chunk Phaser (`1 231,27 kB` avant
compression) ; ces avertissements n'empêchent pas le bundle.

### Les sept tests ignorés du relevé Lot F, nommés

Dans l'état Lot F, aucun test n'était ignoré faute d'opt-in Playwright : cet opt-in
n'existait pas. Le Lot G l'ajoute, désactivé par défaut. Les sept `skipped` du relevé
Lot F sont des limites POSIX de la machine Windows de vérification :

| Test | Raison |
|---|---|
| `apps/api/tests/test_artifacts_storage.py:291` | permissions POSIX non applicables sous Windows |
| `apps/cli/tests/test_cli_automations.py:710` | permissions privées POSIX du fichier secret |
| `apps/cli/tests/test_cli_automations.py:737` | mode POSIX `0600` lu depuis le descripteur ouvert |
| `apps/cli/tests/test_cli_automations.py:776` | refus d'un lien symbolique POSIX avant appel HTTP |
| `apps/worker/tests/test_web_tests.py:712` | liens symboliques indisponibles sur cette machine |
| `apps/worker/tests/test_web_tests.py:749` | idem |
| `apps/worker/tests/test_web_tests.py:964` | idem |

Les quatre tests de liens symboliques et les trois tests de permissions existent dans
le code mais ne sont donc **pas prouvés par cette exécution Windows**. La CI Ubuntu les
rejouera avant toute fusion ; son résultat n'est pas anticipé ici.

### Ce que le Lot E ne prouve pas

- **Aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été
  exécuté.** Le reporter n'a jamais reçu un objet Playwright authentique, et le worker
  n'a jamais lancé un vrai `@playwright/test`.
- Aucune capture ni trace produite par une exécution réelle n'a été téléversée,
  affichée ou téléchargée.
- Aucun parcours navigateur du Studio ni de la bibliothèque.
- Aucun `EventSource` de navigateur, aucune coupure réseau réelle, aucun proxy.
- Aucun PostgreSQL : la migration de `sequence` et `journal_seq` est propre à SQLite.
- Aucun stockage d'objets distant, aucune origine d'aperçu séparée.
- Aucune instance Hermes réelle, aucun serveur MCP tiers, aucun fournisseur payant,
  aucun déploiement Railway.

### Parcours de bout en bout contre des services réellement démarrés

`scripts/verify_mcp_journey.py` démarre l'API métier dans un processus séparé (base
SQLite isolée, clé de coffre éphémère) et un **serveur MCP Streamable HTTP réel** sur
le bouclage, puis rejoue le scénario 7 : **24 étapes sur 24 réussies**. Il n'est pas
exécuté en intégration continue ; il se lance à la demande :

```text
.venv/Scripts/python.exe scripts/verify_mcp_journey.py
```

Il prouve notamment que le serveur MCP a bien reçu l'en-tête `Authorization` portant
la valeur déchiffrée — l'injection n'est donc pas simulée — que cette valeur
n'apparaît ni dans la réponse de création du secret, ni dans la liste, ni dans la
configuration relue, ni dans l'export Hermes ; qu'un secret en clair dans un en-tête
est refusé (`422`) ; que l'activation est refusée sans découverte à jour (`409`) ;
qu'un outil non découvert est refusé (`422`) ; que le projet B ne voit pas le serveur
rattaché au projet A ; et qu'après révocation le projet A ne le voit plus alors que
l'historique reste consultable.

La politique de sortie n'a pas été désactivée pour ce test : l'hôte de bouclage a été
explicitement inscrit dans `ACP_OUTBOUND_PRIVATE_ALLOWLIST` et
`ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP=1` a été posé, ce qui exerce le chemin d'allowlist
auditée et l'opt-in `http` documentés, au lieu de contourner le contrôle. Ces deux
variables restent vides ou à `0` par défaut.

Ce script est désormais versionné (`scripts/verify_mcp_journey.py`), donc rejouable par
un tiers. Le scénario 7 reste néanmoins **Partiel** : il ne couvre que le transport
`http`, le serveur interrogé a été écrit pour la vérification, et il n'exerce aucun
parcours navigateur.

Aucun équivalent n'existe pour le Lot E : il n'y a pas de script versionné qui démarre
les services et rejoue une exécution de tests web, un flux SSE et un téléchargement de
livrable. C'est l'une des raisons pour lesquelles les scénarios 10, 11, 16 et 19
restent **Partiel**.

Le Lot F possède en revanche `scripts/verify_automation_journey.py`. Le 14 septembre
2026, ce script a démarré l'API dans un processus séparé sur une base SQLite
temporaire et rendu **62/62 étapes réussies**, code `0`. Il exerce la création et son
rejeu, le conflit d'idempotence, l'activation, le calendrier, le bail et le tick du
planificateur, les tirs manuel et webhook, l'historique, le permis/rapport de budget
et l'alerte. Il reste un parcours de bouclage déterministe : ni navigateur, ni worker
distant, ni Hermes, ni fournisseur payant, ni PostgreSQL.

### Correctif Job Object et tests d'arbre de processus

Avec le lanceur d'environnement virtuel,
`apps/worker/tests/test_local_runner.py::test_normal_parent_exit_cannot_leave_a_background_child`
échouait **systématiquement** et
`::test_asyncio_cancellation_terminates_the_process_tree` par intermittence : un
petit-fils survivait, conservait les tubes hérités et le résultat devenait
`timed_out` / `output_stream_timeout`. L'énumération par filiation (Toolhelp,
`th32ParentProcessID`) ne rattache plus un petit-fils dont le parent intermédiaire —
le lanceur — a déjà quitté.

Le Lot D enferme désormais tout spawn du runner, et de la sonde MCP `stdio`, dans un
Job Object Windows : création suspendue, affectation revérifiée, `KILL_ON_JOB_CLOSE`
sans `BREAKAWAY_OK`, vacuité du job contrôlée à l'arrêt, et échec fermé en
`spawn_failed` / `job_assignment_failed` si l'affectation échoue. Les deux tests
passent désormais ; trois exécutions consécutives de
`apps/worker/tests/test_local_runner.py` ont rendu **34 tests réussis** à chaque fois.

Ces preuves sont locales, sur Windows. L'intégration continue les rejoue sur Ubuntu
avec Python `3.12` et Node `22` à chaque poussée ; c'est elle qui avait révélé une
assertion d'environnement trop stricte, invisible sous Windows. Les Lots C et D sont
publiés (PR #3 et #4, tags `v0.4.0` et `v0.5.0` ; `v0.5.0` est bien un ancêtre de
`origin/main`).

Le Lot E a été publié par la PR #5 : fusion `b7d8a44`, tag `v0.6.0`, après observation
d'une CI verte. Les chiffres détaillés ci-dessus proviennent de la vérification
Windows ; la CI confirme la branche publiée mais ne transforme pas les simulations en
services externes réels.

## Vérifications explicitement non exécutées

- serveur MCP **tiers** (HTTP ou stdio) : le seul serveur MCP réellement interrogé a
  été écrit pour la vérification et tournait sur le bouclage ;
- sonde `stdio` contre un serveur MCP tiers : les tests utilisent un serveur stdio
  déterministe local, et aucun runner distant réel n'a été enrôlé ;
- dépôt GitHub réel ou archive de skill tierce ;
- instance, modèle, mémoire, outils ou clé Hermes réels ;
- exécuteur Codex/Claude authentifié et effet externe sur un dépôt utilisateur ; le
  câblage worker est prouvé uniquement avec un exécutable contrôlé ;
- E2E navigateur du bootstrap, d'une conversation, d'une mission, du centre MCP ou de
  la bibliothèque de skills ;
- PostgreSQL existant, migration versionnée, sauvegarde ou restauration ;
- sandbox OS/réseau, quotas CPU/mémoire/disque ou compte non privilégié dédié : le Job
  Object Windows borne et vidange son groupe, sans imposer quota ni politique réseau ;
  sous POSIX, `killpg` ne voit pas un descendant ayant changé de session ; une racine
  projet ne limite pas les fichiers lisibles par le compte worker ;
- appel d'outil MCP pendant une mission ou génération ComfyUI raccordée au worker ;
- rendu GLB par un navigateur sur une origine d'aperçu réellement déployée ;
- planificateur sur plusieurs hôtes, webhook Internet, fournisseur payant et fan-out
  multi-agent ;
- **Playwright réel** : aucun navigateur lancé, aucune suite exécutée, aucune trace ni
  capture produite par une exécution réelle ; l'opt-in `ACP_E2E=1` existe mais n'a pas
  reçu de cible, compte ni tentative de test ;
- parcours navigateur du Studio et de la bibliothèque de livrables ;
- coupure réseau réelle, proxy intermédiaire ou `EventSource` de navigateur sur le
  flux SSE ;
- origine d'aperçu séparée (`ACP_ARTIFACT_PUBLIC_ORIGIN`) et stockage d'objets distant ;
- purge de rétention réellement exécutée sur des données d'exploitation (la commande
  existe, est testée et reste à blanc sans `--apply`) ;
- déploiement ou test d'un service externe pour le Lot F ;
- Railway, HTTPS public, charge ou audit offensif.

## Conditions avant exposition réseau

- terminer la matrice RBAC sur chaque ressource enfant, flux et fichier ;
- ajouter migrations PostgreSQL, sauvegarde/restauration et rotation ; le stockage privé
  des livrables existe mais reste un répertoire local, qui exige un volume persistant
  chez un hébergeur ;
- **configurer et router une origine d'aperçu séparée**
  (`ACP_ARTIFACT_PUBLIC_ORIGIN`) avant d'exposer le Studio : sans elle, l'API refuse
  l'aperçu en `424` et n'émet aucun jeton ;
- isoler le runner au niveau OS/réseau et raccorder un circuit d'approbation worker ;
- placer le webhook entrant derrière HTTPS et une limitation distribuée au reverse
  proxy — la limite locale est par processus — puis éprouver rotation, révocation et
  rejeu avec un émetteur réel ;
- exécuter les scénarios E2E contre les services réellement démarrés, y compris une
  vraie suite Playwright sur un runner réel ;
- verser dans le dépôt un parcours de bout en bout du Lot E, comme
  `scripts/verify_mcp_journey.py` l'a fait pour le scénario 7 : c'est la condition
  nécessaire pour envisager « Accepté » sur 10, 11, 16 et 19 ;
- étendre le parcours du scénario 7 au transport `stdio` et le rejouer contre un
  serveur MCP tiers ;
- activer les tests externes uniquement par opt-in, avec secrets et budgets bornés ;
  `ACP_E2E=1` reste à exécuter uniquement contre une cible de test autorisée.
