# Rapport d'acceptation

Date d'état : 13 septembre 2026
Périmètre évalué : Lot E (version `0.6.0`) implémenté localement sur la base du
Lot D `0.5.0`, sans service externe ni dépense réelle. Le Lot E n'est ni fusionné dans
`main`, ni étiqueté : sa branche `codex/modernization-lot-e` est poussée, mais les
corrections de revue et cette documentation ne sont pas encore validées, donc aucune
intégration continue distante ne les couvre.

## Verdict

**0 scénario sur 20 est accepté de bout en bout.** Seize scénarios disposent d'une
brique réelle et de tests ciblés ; quatre restent non satisfaits (4, 15, 17 et 20).
Trois scénarios changent de statut dans cette version — 10, 11 et 16 passent de **Non
satisfait** à **Partiel** — et deux voient leurs preuves complétées sans changer de
statut (12 et 19). Le Lot E rend le
journal d'événements, le flux authentifié, les résultats de tests structurés et la
bibliothèque de livrables réellement utilisables et testés, mais :

- **aucun navigateur réel n'a été lancé** et **aucun test Playwright réel n'a été
  exécuté** pour cette version. Le reporter est prouvé sur des objets Playwright
  synthétiques ; l'exécuteur du worker est prouvé sur
  `apps/worker/tests/fake_playwright_runner.py`, un programme déterministe lancé par
  `sys.executable` qui écrit un NDJSON réaliste et des fichiers de pièces jointes ;
- aucune capture d'écran d'une session de test réelle n'existe, donc aucune image de
  session n'a jamais été affichée par le Studio ;
- aucun parcours navigateur des écrans Studio et Bibliothèque n'a été effectué : les
  deux sont couverts par des tests Vitest sur le DOM ;
- aucune origine d'aperçu séparée n'est configurée, donc les liens signés pointent vers
  l'origine de l'API ;
- aucun parcours de bout en bout du Lot E n'est versionné dans le dépôt : il n'existe
  pas d'équivalent de `scripts/verify_mcp_journey.py` pour ce lot.

Le scénario 7 reste le seul rejoué contre des services réellement démarrés (API métier
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
| 5 | Mission réellement exécutée par au moins un agent configuré | **Partiel** | Le worker lance un vrai processus local configuré, produit une preuve et échoue fermé. Seuls des programmes déterministes de test ont été lancés, pas un agent réel. |
| 6 | Isolation des fichiers, secrets et contexte entre deux projets | **Partiel** | RBAC et conversations inter-projets sont testés ; le runner filtre son enveloppe et son environnement ; le coffre du Lot D chiffre les secrets, limite une portée `project` à son projet et n'expose aucune valeur ; le Lot E ajoute un stockage de livrables privé dont la lecture est filtrée par les projets accessibles. Pas de sandbox OS. |
| 7 | Ajout, test, activation et révocation d'un MCP | **Partiel** | Parcours complet testé sur les deux transports : déclaration, refus d'un secret en clair, diagnostic HTTP épinglé, autorisation puis diagnostic `stdio` sur le runner désigné, rattachement limité à un sous-ensemble d'outils, activation, rollback, révocation et audit (`apps/api/tests/test_mcp_servers.py`, `apps/worker/tests/test_mcp_probe.py`). Le transport `http` a en outre été rejoué contre des services réellement démarrés : **24/24 étapes**, injection du secret observée côté serveur MCP et jamais republiée. Le script de ce parcours est versionné (`scripts/verify_mcp_journey.py`). Manque bloquant : aucun serveur MCP **tiers** contacté, aucun parcours navigateur, et le transport `stdio` reste prouvé par un serveur déterministe local. |
| 8 | Import d'un skill, affichage des fichiers et activation limitée | **Partiel** | Import manuel, dossier autorisé, archive et GitHub épinglé ; arborescence, `SKILL.md`, dépendances, licence et contrôle indicatif affichés ; approbation exigée quand la portée augmente ; activation sur le projet A absente des extensions du projet B ; révocation auditée (`apps/api/tests/test_skills.py`, `test_extensions.py`). Manque bloquant : aucun dépôt GitHub réel ni archive de skill tierce ; le transport GitHub est prouvé sur `httpx.MockTransport`. |
| 9 | Refus d'une installation ou d'une action non autorisée | **Partiel** | CSRF/RBAC et frontières worker sont testés ; le runner refuse avant spawn les autonomies non garanties et toute commande hors allowlist ; un opérateur ou un lecteur est refusé sur `/mcp/servers`, `/skills/import` et `/secrets`, un membre d'un autre projet sur un rattachement, un lancement `stdio` non autorisé n'est jamais distribué, et `GET /mcp/servers/{id}` ne nomme que les rattachements des projets accessibles. Manque bloquant : les refus sont prouvés sur des sources locales et un parcours API, pas sur une installation réelle ni un parcours navigateur. |
| 10 | Tests web avec résultat structuré et capture de la session réelle | **Partiel** | Le résultat structuré est livré et testé de bout en bout **sur un lanceur simulé** : reporter NDJSON sans dépendance ni appel réseau, ingestion worker authentifiée avec lease et fencing, `test_runs`/`test_cases` rattachés à la tentative, statuts `passed`/`failed`/`timedOut`/`skipped`/`interrupted` et `flaky` conservés distinctement, validation technique dérivée sans jamais forcer `succeeded`, refus de tout faux succès (rapport vide, arrêt d'arbre non prouvé, code de sortie du rapport ne pouvant pas effacer celui mesuré). **Manque bloquant : aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été exécuté ; aucune capture d'une session réelle n'existe.** |
| 11 | Consultation d'une trace et d'une capture après échec | **Partiel** | Les pièces jointes d'un cas en échec sont téléversées par le worker, stockées hors base (adressage par contenu sur disque), référencées dans l'événement par empreinte et type, listées et téléchargeables après redémarrage des services — par le Studio, la bibliothèque et `acp artifacts get`, qui vérifie le sha256. Une trace et un rapport HTML ne sont jamais servis en ligne : téléchargement forcé, `nosniff`, CSP `default-src 'none'; sandbox`. **Manque bloquant : aucune trace ni capture n'a jamais été produite par un échec Playwright réel ; aucune origine d'aperçu séparée n'est configurée ; pas de trace viewer intégré (la trace s'ouvre hors plateforme).** |
| 12 | Déconnexion/reconnexion sans perte d'historique ni double lancement | **Partiel** | Preuves complétées par le Lot E : flux SSE authentifié avec reprise par `Last-Event-ID` ou `?after_seq=` sur un compteur monotone à ordre total, sans perte ni doublon ; 300 publications sans pause sont paginées exactement une fois chacune ; une reconnexion ne relance jamais une mission ; l'interface expose `connected`/`reconnecting`/`polling`/`offline` et réconcilie par `GET` au lieu d'inventer un état ; une révocation de session ferme la connexion au plus tard à la page suivante. S'y ajoute l'idempotence durable héritée du Lot C. **Manque bloquant : aucune coupure réseau réelle, aucun `EventSource` de navigateur, aucun outbox.** |
| 13 | Approbation, refus, expiration et arrêt réel d'une exécution | **Partiel** | Acceptation/refus, empreinte et expiration d'approbation, stop et arrêt d'arbre sont couverts. Le runner local refuse les actions nécessitant approbation au lieu de les demander. |
| 14 | Runner perdu puis reprise contrôlée sans double effet | **Partiel** | Lease, fencing, worker obsolète, interruption et nouvelle tentative sont testés. Aucun effet tiers réel ne permet de prouver l'absence de double effet externe. |
| 15 | Routine planifiée sans doublon et fuseau Europe/Paris | **Non satisfait** | Reporté au Lot F. |
| 16 | Livrable téléchargeable et aperçu 3D réel | **Partiel** | La moitié « livrable téléchargeable » est livrée et testée : stockage privé adressé par contenu, téléversement worker idempotent par sha256 avec plafond par fichier et quota par tentative appliqués pendant le flux, téléchargement par session ou par lien signé borné et révocable, support des requêtes `Range`, onglet « Livrables » de la bibliothèque (filtres projet/mission/type, recherche, métadonnées, provenance, taille, empreinte) et `acp artifacts list | get | link`. **Manque bloquant : aucun aperçu 3D (reporté au Lot G), aucun livrable produit par une exécution réelle, stockage local seulement (aucun adaptateur objet), et aucune origine d'aperçu séparée configurée.** |
| 17 | Génération d'image réelle si backend configuré | **Non satisfait** | Reporté au Lot G. |
| 18 | Budget atteint, fournisseur indisponible et stockage saturé | **Partiel** | Durée globale et panne provider échouent fermées ; coûts/tokens, appels outils et saturation ne sont pas encore appliqués de bout en bout. |
| 19 | Authentification des médias, événements et fichiers privés | **Partiel** | Preuves complétées par le Lot E : flux utilisateur authentifié servi par l'API métier (session, RBAC du projet revérifié **à chaque page**, refus inter-projets, fermeture après révocation de session, connexions bornées par utilisateur) ; fichiers privés servis uniquement à un membre ou via un lien signé lié à l'artefact **et** au demandeur, borné à 900 s, révocable, `503` explicite sans clé de signature ; aucun projet rendu public ; aucun média dans un événement (référence, empreinte, type et taille seulement) ; WebSocket anonyme du service d'événements toujours fermé. **Manque bloquant : aucune origine d'aperçu séparée configurée (`ACP_ARTIFACT_PUBLIC_ORIGIN` vide ⇒ les liens signés pointent vers l'origine de l'API), aucun parcours navigateur, aucun parcours de bout en bout versionné pour ce lot.** |
| 20 | Sauvegarde/restauration et migration de données existantes | **Non satisfait** | Upgrade SQLite ad hoc et non versionné, avec reconstruction contrôlée de tables et sauvegarde préalable requise ; PostgreSQL versionné et restauration reportés au Lot H. |

## Preuves de tests du Lot E

Les résultats ci-dessous ont été obtenus le 13 septembre 2026 dans le worktree
`lot-e`, après les corrections de revue et la synchronisation des versions sur
`0.6.0`. Ils portent sur l'arbre de travail complet (branche `codex/modernization-lot-e`
plus les corrections non encore validées), sans les modifications Pixel/LimeZu du
worktree principal.

### Environnement exact

| Élément | Valeur |
|---|---|
| Système | Windows 10 Pro `10.0.19045` |
| Interpréteur des suites | `.venv\Scripts\python.exe` — **lanceur d'environnement virtuel Windows**, Python `3.12.0` |
| Node.js / npm | `v24.19.0` / `11.17.0` |
| CI GitHub Actions | `ubuntu-latest`, Python `3.12`, Node `22` (`.github/workflows/ci.yml`) — **non exécutée sur ce travail** : les corrections de revue et cette documentation ne sont pas validées |

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
| `npm exec tsc -- --noEmit -p apps/web/tsconfig.json` | **réussi** | cohérence TypeScript | pas le comportement runtime |
| `npm test --workspace @acp/web` | **262 réussis (17 fichiers)** | clients `events-api`, `artifacts-api`, `testing-api`, filtres de la bibliothèque, câblage du Studio, plus l'acquis du Lot D | DOM simulé, **pas de navigateur réel** |
| dont fichiers du Lot E (web) | **113 réussis (5 fichiers)** | `events-api`, `artifacts-api`, `testing-api`, `library-ui`, `studio-wiring` | idem |
| `npm test --workspace @acp/playwright-reporter` | **59 réussis (1 fichier)** | statuts distincts, `flaky`, troncature, ANSI retiré, NDJSON valide ligne par ligne, pièce jointe par chemin et en ligne, absence de `ACP_REPORT_FILE` | objets Playwright **synthétiques** |
| `npm test --workspace @acp/pixel-office-engine` | **74 réussis (7 fichiers)** | non-régression du moteur legacy | hors parcours principal |
| `npm run build:web` | **réussi** | bundle Vite productible | pas un déploiement |
| `./.venv/Scripts/python.exe scripts/check_version.py` | **réussi** | tous les composants publiables portent `0.6.0` | n'implique aucune publication |

Les deux avertissements Python proviennent de dépréciations dans les dépendances —
`StarletteDeprecationWarning` sur l'usage de `httpx` par `starlette.testclient`, et la
dépréciation de l'alias `anyio.abc.BlockingPortal` — et sont non bloquants. Le build
Vite se termine avec le seul avertissement attendu sur la taille du chunk Phaser
(`1 231 kB` avant compression) ; ce n'est pas un échec de compilation.

### Les quatre tests ignorés, nommés

Aucun test n'est ignoré faute d'opt-in Playwright : **cet opt-in n'existe pas**. Les
quatre `skipped` sont des limites de la machine de vérification :

| Test | Raison |
|---|---|
| `apps/api/tests/test_artifacts_storage.py:246` | permissions POSIX non applicables sous Windows |
| `apps/worker/tests/test_web_tests.py:706` | liens symboliques indisponibles sur cette machine |
| `apps/worker/tests/test_web_tests.py:745` | idem |
| `apps/worker/tests/test_web_tests.py:960` | idem |

Les trois derniers sont précisément les tests qui prouvent le refus d'une pièce jointe
atteinte par un lien symbolique : ce contrôle existe dans le code mais **n'est pas
prouvé sur cette machine**.

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

Le Lot E, lui, n'est **pas** publié : sa branche `codex/modernization-lot-e` est
poussée, mais elle n'est pas fusionnée dans `main`, aucun tag `v0.6.0` n'existe, et les
corrections de revue comme cette documentation ne sont pas encore validées — donc
aucune exécution d'intégration continue ne les couvre. Les chiffres de ce rapport
proviennent uniquement de la machine de vérification Windows.

## Vérifications explicitement non exécutées

- serveur MCP **tiers** (HTTP ou stdio) : le seul serveur MCP réellement interrogé a
  été écrit pour la vérification et tournait sur le bouclage ;
- sonde `stdio` contre un serveur MCP tiers : les tests utilisent un serveur stdio
  déterministe local, et aucun runner distant réel n'a été enrôlé ;
- dépôt GitHub réel ou archive de skill tierce ;
- instance, modèle, mémoire, outils ou clé Hermes réels ;
- exécuteur Codex/Claude réel et effet externe sur un dépôt utilisateur ;
- E2E navigateur du bootstrap, d'une conversation, d'une mission, du centre MCP ou de
  la bibliothèque de skills ;
- PostgreSQL existant, migration versionnée, sauvegarde ou restauration ;
- sandbox OS/réseau, quotas CPU/mémoire/disque ou compte non privilégié dédié : le Job
  Object borne l'arbre de processus, il n'impose ni quota ni politique réseau ;
- appel d'outil MCP pendant une mission, média, aperçu 3D et automatisation ;
- **Playwright réel** : aucun navigateur lancé, aucune suite exécutée, aucune trace ni
  capture produite par une exécution réelle ; l'opt-in `ACP_E2E=1` prévu par la
  spécification n'existe pas dans le dépôt ;
- parcours navigateur du Studio et de la bibliothèque de livrables ;
- coupure réseau réelle, proxy intermédiaire ou `EventSource` de navigateur sur le
  flux SSE ;
- origine d'aperçu séparée (`ACP_ARTIFACT_PUBLIC_ORIGIN`) et stockage d'objets distant ;
- purge de rétention réellement exécutée sur des données d'exploitation (la commande
  existe, est testée et reste à blanc sans `--apply`) ;
- CI distante, PR et tag du Lot E ;
- Railway, HTTPS public, charge ou audit offensif.

## Conditions avant exposition réseau

- terminer la matrice RBAC sur chaque ressource enfant, flux et fichier ;
- ajouter migrations PostgreSQL, sauvegarde/restauration et rotation ; le stockage privé
  des livrables existe mais reste un répertoire local, qui exige un volume persistant
  chez un hébergeur ;
- **configurer une origine d'aperçu séparée** (`ACP_ARTIFACT_PUBLIC_ORIGIN`) avant
  d'exposer le Studio : sans elle, les aperçus signés sont servis par l'origine de
  l'API, et l'avertissement affiché n'est pas un contrôle ;
- isoler le runner au niveau OS/réseau et raccorder un circuit d'approbation worker ;
- exécuter les scénarios E2E contre les services réellement démarrés, y compris une
  vraie suite Playwright sur un runner réel ;
- verser dans le dépôt un parcours de bout en bout du Lot E, comme
  `scripts/verify_mcp_journey.py` l'a fait pour le scénario 7 : c'est la condition
  nécessaire pour envisager « Accepté » sur 10, 11, 16 et 19 ;
- étendre le parcours du scénario 7 au transport `stdio` et le rejouer contre un
  serveur MCP tiers ;
- activer les tests externes uniquement par opt-in, avec secrets et budgets bornés ;
  l'opt-in Playwright réel (`ACP_E2E=1`) reste à écrire.
