# État d'implémentation et reprise

Date d'état : 13 septembre 2026, Europe/Paris
Portée : Lot E (version `0.6.0`) construit sur le Lot D `0.5.0`. Les Lots C et D sont
publiés (PR #3 et #4, tags annotés `v0.4.0` et `v0.5.0` ; `v0.5.0` est un ancêtre de
`origin/main`). Le Lot E **n'est pas publié** : sa branche `codex/modernization-lot-e`
est poussée, mais elle n'est pas fusionnée dans `main`, aucun tag `v0.6.0` n'existe, et
les corrections de revue comme cette documentation ne sont pas encore validées — donc
aucune exécution d'intégration continue distante ne les couvre.

## Résumé

La modernisation complète n'est pas terminée. Le Lot C livre la tranche mission :
ressource durable, tentatives explicites, arrêt et relance contrôlés, preuves,
validation technique, acceptation utilisateur, backend de processus local et CLI
`acp` utilisant la même API que le web.

Le Lot D livre la tranche extensions : coffre de secrets chiffrés à références,
politique de sortie réseau anti-SSRF, centre MCP versionné avec diagnostics HTTP et
`stdio` autorisés, bibliothèque de skills importés et relisibles, rattachements par
projet, révocation de bout en bout, import/export des configurations MCP, écrans web
et groupes CLI `acp secrets | mcp | skills`. Aucun serveur MCP réel, dépôt GitHub réel
ou runner distant réel n'a été contacté : les preuves reposent sur des transports et
programmes déterministes locaux.

Le Lot E livre la tranche observation et livrables : journal d'événements ordonné par
deux compteurs monotones, flux SSE authentifié par curseur servi par l'API métier,
reporter Playwright sans dépendance ni appel réseau, exécution de tests web sur un
runner authentifié, résultats de tests structurés, stockage privé de livrables adressé
par contenu avec liens signés bornés et révocables, Studio en lecture seule et onglet
« Livrables » de la bibliothèque, plus les commandes CLI correspondantes.
**Aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été exécuté**
pour cette version : le reporter est prouvé sur des objets Playwright synthétiques et
l'exécuteur du worker sur un programme déterministe. La reprise en main humaine du
navigateur n'est pas livrée et l'interface le dit.

Le backend réel exécute uniquement un exécutable absolu via un argv fixe configuré
par l'opérateur. Il ne prend jamais une commande dans la mission, crée un cwd neuf,
transmet un snapshot borné, filtre l'environnement, borne le temps et les sorties,
et arrête l'arbre de processus lors d'un stop, timeout ou lease perdu. Il reste un
processus avec les droits OS du compte worker : ce n'est pas une sandbox pour du
code non fiable.

Aucune instance Hermes réelle, dépense externe, migration de production ou
déploiement n'a été lancé. Les preuves locales reposent sur des programmes et
transports déterministes de test.

## Réalisé et testé dans le Lot C

### Missions et tentatives

- création atomique d'une mission et de sa première tentative avec objectif,
  résultat attendu, critères, autonomie, ressources, budget et durée ;
- `Idempotency-Key` obligatoire pour créer, arrêter et relancer ; la clé de création
  est liée au principal et à l'empreinte du payload ;
- replay d'un arrêt lié à sa tentative d'origine, sans risque d'arrêter une relance
  ultérieure ;
- états `queued`, `preparing`, `running`, `waiting_approval`, `blocked`, `stopping`,
  `succeeded`, `failed`, `cancelled` et `interrupted` ;
- numéro de tentative et fencing token monotones ; ancien worker refusé lors d'un
  renew, PATCH ou événement ;
- succès accepté seulement avec validation technique `passed` et preuve structurée ;
- décision utilisateur séparée (`pending`, `accepted`, `rejected`), commentaires et
  relance possible après rejet explicite ;
- lecture directe d'une mission par identifiant de run pour les liens profonds ;
- worker simulé exclu des missions réelles.

### Backend worker local

- configuration fail-closed par `ACP_WORKER_RUNNER_ARGV_JSON` et
  `ACP_WORKER_RUN_ROOT` ; exécutable absolu et situé hors de la racine inscriptible ;
- enveloppe `acp.local-process.request.v1` et preuve
  `acp.local-process.evidence.v1` à champs structurés allowlistés ; stdout/stderr
  sont bornés et hachés, mais leur texte non expurgé peut contenir des secrets ;
- création exclusive d'un répertoire par tentative, aucun rejeu implicite d'un cwd
  existant et aucun shell ;
- environnement minimal et allowlisté, stdout/stderr lus en continu, captures
  bornées et SHA-256 de la totalité ;
- deadline de mission, timeout, arrêt explicite, perte de lease et fencing obsolète
  reliés à l'arrêt du groupe/arbre de processus ;
- sortie du parent détectée indépendamment des pipes hérités et succès refusé si le
  nettoyage de l'arbre ne peut pas être confirmé ;
- code de sortie nul insuffisant : l'évaluateur doit répondre explicitement
  `approved: true`, sinon l'état reste non réussi et la preuve technique est gardée ;
- mode non supervisé, listes d'actions non vides, ressources en écriture et provider
  `mock` refusés avant le spawn ; verdict lié au provider réel configuré ;
- `doctor` exige liveness API/gateway, authentification worker et readiness
  authentifiée du provider.

### Web et CLI synchronisés

- écran Missions relié à l'API, avec état d'exécution, validation technique,
  acceptation, critères, preuves, arrêt, relance et commentaires ;
- lien `/missions?run=<id>` qui ouvre la mission et la tentative demandées, y compris
  une tentative historique ;
- clé de création web conservée après un timeout afin qu'un nouvel essai logique ne
  duplique pas la mission ;
- CLI installable : `login`, `logout`, `doctor`, projets, chat, création/suivi/arrêt
  de missions, approbations, artefacts, workers, ouverture web et complétion shell ;
- JSON/NDJSON, codes de sortie stables et `Ctrl+C` sur `runs watch` sans arrêt
  implicite de la mission ;
- configuration CLI atomique, session liée à l'origine API, HTTPS obligatoire hors
  loopback et aucun Cookie/CSRF réutilisé après changement d'origine ;
- commandes d'automatisations explicitement non supportées tant que le Lot F n'est
  pas livré.

## Réalisé et testé dans le Lot D

### Coffre de secrets et sorties réseau

- secrets chiffrés (Fernet) avec `key_id`, rotation de clé sans perte via
  `ACP_SECRETS_KEYS`, portées `platform`/`project`, révocation et `last_used_at` ;
  valeur jamais retournée par une route, un export, un événement ou le frontend ;
- coffre absent : état explicite `configured=false` et `503` sur les routes qui
  chiffrent ou déchiffrent, jamais de repli en clair ;
- politique de sortie appliquée côté serveur : `https` exigé hors allowlist, userinfo
  refusé, toutes les adresses résolues contrôlées (une seule bloquée suffit à
  refuser), adresse épinglée pendant la requête, redirections revalidées, corps borné,
  usage d'une allowlist privée audité.

### Centre MCP

- serveurs versionnés (révision immuable, empreinte, diff, risques), catalogue de
  trois entrées vérifiées sur documentation et jamais exécutées ;
- refus `422` d'une valeur littérale ressemblant à un secret, d'un paquet non épinglé,
  d'une commande relative ou d'une URL refusée par la politique ;
- diagnostic HTTP exécuté par l'API ; diagnostic `stdio` soumis à une autorisation
  explicite portant l'empreinte, exécuté par un runner authentifié doté de la capacité
  `mcp_stdio_probe`, avec lease, invalidation, expiration et refus hors lease ;
- expurgation des contenus renvoyés par le serveur sondé, appliquée par le runner et
  par l'API (`acp_contracts.redaction`) ;
- rattachements par projet limités à un sous-ensemble d'outils découverts, activation
  refusée sans découverte courante, désactivation réversible, révocation irréversible
  avec raison, rollback et historique conservé ;
- import Hermes/Claude/Codex avec aperçu normalisé et secrets masqués, export avec
  placeholders `${ACP_SECRET_…}` et notes de compatibilité partielle.

### Bibliothèque de skills et extensions

- import borné depuis un `SKILL.md` saisi, un dossier explicitement autorisé, une
  archive ZIP ou un commit GitHub épinglé ; traversées, liens et fichiers spéciaux
  refusés ;
- révisions avec manifeste SHA-256, frontmatter, licence, dépendances et contrôle
  automatique indicatif ; contenus affichés comme texte, jamais rendus ;
- approbation obligatoire quand une révision augmente la portée (script, réseau,
  permission) ; rattachement par projet, activation, rollback et révocation ;
- extensions résolues par projet (`GET /projects/{id}/extensions`) et instantané figé
  dans `meta["extensions"]` d'une mission : une révision ultérieure ne change pas une
  mission déjà démarrée ;
- lecture des skills et toolsets natifs Hermes dans Connexions, sans recopie dans le
  registre.

### Clôture d'arrêt du runner (correctif d'un défaut du Lot C)

- sous Windows, tout spawn du runner et de la sonde `stdio` est créé suspendu, affecté
  à un Job Object `KILL_ON_JOB_CLOSE` sans `BREAKAWAY_OK`, vérifié par `IsProcessInJob`
  puis repris : aucune instruction du programme ne s'exécute hors de sa clôture ;
- une affectation impossible devient `spawn_failed` / `job_assignment_failed`, jamais
  une exécution non bornée ;
- `process_tree_stopped` n'est vrai que si le job est vide **et** que la passe Toolhelp
  existante le confirme : la vérification native est conservée, pas remplacée ;
- ce correctif traite un défaut réel du Lot C : avec un lanceur d'environnement
  virtuel, un petit-fils survivait à l'arrêt et transformait un run réussi en
  `timed_out` / `output_stream_timeout` ;
- sur POSIX, le comportement est inchangé (`start_new_session` puis `killpg`).

## Réalisé et testé dans le Lot E

### Journal d'événements et flux authentifié

- `events` porte `schema_version`, `conversation_id`, `step_id`, `executor`,
  `emitted_by` et **deux compteurs monotones** alloués dans la transaction métier :
  `sequence` (par tentative, exposée comme `StreamEvent.sequence`) et `journal_seq`
  (le journal entier, curseur de la portée projet), chacun sous index unique partiel ;
- `GET /runs/{id}/events` et `GET /projects/{id}/events` rendent un `EventPage`
  (`next_cursor`, `has_more`, `retention_days`) ; une page ne dépasse jamais sa limite
  et `has_more` vaut exactement « il existe une ligne de rang supérieur » ;
- `GET /streams/runs/{id}` et `GET /streams/projects/{id}` servent du
  `text/event-stream` depuis l'**API métier**, avec reprise par `Last-Event-ID` ou
  `?after_seq=`, keep-alive `: ping`, rotation propre annoncée avec son curseur,
  limite de connexions par utilisateur et RBAC **revérifié à chaque page** ;
- le flux relit la base par curseur (interrogation bornée + réveil intra-processus) :
  la base est la seule source de vérité, donc une reconnexion ne duplique ni ne perd
  d'événement et plusieurs processus d'API peuvent servir la même tentative ;
- un événement écrit hors de `publish` — les producteurs du Lot C et les écritures
  d'audit MCP/skills/secrets/workers — reçoit ses numéros de façon transparente ; un
  test structurel interdit à tout autre module d'`acp_api` de construire un
  `EventModel` à la main ;
- aucun média dans un événement : le payload d'une pièce jointe ne porte que
  `artifact_id`, `content_type`, `size_bytes`, `sha256`, `stream_kind`.

### Livrables privés

- stockage adressé par contenu sur disque (`ACP_ARTIFACT_STORAGE_DIR`, clé
  `<sha256[0:2]>/<sha256>`), écriture atomique, nom d'origine jamais dans le chemin,
  derrière une interface `ArtifactStorage` prête pour un adaptateur objet non livré ;
- `POST /workers/{id}/artifacts/content` : identité worker vérifiée **avant** la
  lecture du corps, plafond par fichier et quota par tentative appliqués pendant le
  flux, idempotence par sha256 sur la même tentative ;
- `GET /artifacts`, `/artifacts/{id}`, `/artifacts/{id}/content` : lecture filtrée par
  les projets accessibles, support des requêtes `Range`, allowlist de types sans
  reniflage, `nosniff`, CSP `default-src 'none'; sandbox`, `private, no-store`, et
  `text/html` / `image/svg+xml` / archives jamais servis en ligne ;
- `POST /artifacts/{id}/link` et `DELETE /artifacts/links/{link_id}` : lien HMAC borné
  (≤ 900 s), lié à l'artefact et au demandeur, révocable, `503` explicite sans clé ;
- `python -m acp_api.retention` : purge à blanc par défaut, conservation des événements
  terminaux et des artefacts cités par une preuve de mission, comptage de références
  avant l'effacement d'un blob.

### Tests web structurés

- `packages/playwright-reporter` (`@acp/playwright-reporter`) : workspace npm **sans
  dépendance runtime**, NDJSON local dans `ACP_REPORT_FILE`, aucun appel réseau,
  statuts et `flaky` conservés distinctement, troncature à 8 000 caractères sans couper
  une paire de substituts UTF-16, séquences ANSI retirées ;
- `apps/worker/src/acp_worker/web_tests.py` : capacité `web_tests` désactivée par
  défaut, argv absolu et racine configurés par l'opérateur, lancement par
  `spawn_fenced_process` et arrêt par `terminate_process_tree`, arrêt non prouvé ⇒ pas
  de succès, NDJSON absent ou vide ⇒ échec explicite, pièce jointe hors du répertoire
  de sortie refusée, expurgation des messages et extraits, preuve `web_tests` sans
  image ;
- `apps/api/src/acp_api/testing_service.py` : ingestion idempotente sous identité
  worker, lease et fencing ; `test_runs` / `test_cases` ; événements `test.run.started`,
  `test.case.finished`, `test.run.finished` ; validation technique dérivée
  (`passed` seulement avec code de sortie nul, aucun `unexpected`/`interrupted`/
  `timedOut` et au moins un cas exécuté), jamais `succeeded` ;
- le verdict du serveur ne peut qu'**aggraver** celui du worker, et le code de sortie
  annoncé par le rapport ne peut jamais effacer celui mesuré.

### Web et CLI

- `studio-ui.ts` : bandeau de mode et de connexion en libellés textuels, chronologie
  par curseur, arbre des tests avec statuts distincts et étapes dépliables, dernière
  capture référencée par les pièces jointes, aperçus par lien signé, trace et rapport
  HTML en téléchargement explicite avec avertissement, **aucun bouton de prise de
  contrôle** ;
- `library-ui.ts` : route « Bibliothèque » à deux onglets, `Skills` (délégué tel quel
  au module du Lot D) et `Livrables` (filtres projet/mission/type, recherche, aperçu,
  téléchargement, métadonnées, provenance, taille, empreinte) ; aucun nouvel élément de
  navigation ;
- règle du Lot D conservée : client HTTP fourni par le shell, aucune lecture de
  `/auth/session`, purge d'état à la connexion et à la déconnexion — celle du Studio
  ferme aussi l'`EventSource` ;
- CLI : `acp runs events` (`--after-seq`, `--limit`, `--follow`, `--json`),
  `acp runs tests` (même dérivation que le serveur, code `4` si la validation est en
  échec), `acp artifacts list | get | link`, `acp open --run <id> --studio`.

## Hérité des Lots A et B

- shell moderne français, thèmes, responsive, états vides/erreur/hors ligne et
  pixel office historique désactivé par défaut ;
- bootstrap propriétaire unique, Argon2id, session opaque révocable/expirable,
  cookie `HttpOnly`, CSRF et rôles par projet ;
- onboarding personnel et conversations persistantes ;
- adaptateur Hermes `0.21.1` fondé sur `/health/detailed`, `/v1/capabilities` et
  `/v1/runs`, avec réponses strictes et frontière inter-services ;
- service d'événements protégé en ingestion et WebSocket anonyme fermé par défaut.

## Vérification du Lot E

Les résultats détaillés sont consignés dans
[le rapport d'acceptation](acceptance-report.md). Le Lot E a été vérifié dans le
worktree `lot-e` sous Windows 10 Pro `10.0.19045`, Node.js `v24.19.0` et npm
`11.17.0`. Les suites Python ont été exécutées avec `.venv\Scripts\python.exe`, le
**lanceur d'environnement virtuel Windows** (Python `3.12.0`). Ce choix compte : sous
Windows, ce lanceur exécute l'interpréteur réel dans un processus enfant, la topologie
même que le correctif Job Object du Lot D devait couvrir et que l'exécution de tests
web réutilise.

La suite Python compte **1 627 tests réussis, 4 ignorés et 2 avertissements de
dépréciation connus** (`751` API, `223` worker, `365` CLI, `288` en contrats,
gateway et event-service). Le web compte **262 tests Vitest sur 17 fichiers**, le
reporter Playwright **59 tests** et le moteur legacy **74 tests**. Le typecheck
TypeScript, le build Vite et `scripts/check_version.py` (toutes les versions
publiables sur `0.6.0`) réussissent ; le build n'émet que l'avertissement attendu sur
la taille du chunk Phaser.

Les quatre tests ignorés sont des limites de la machine, pas des opt-in : un contrôle
de permissions POSIX inapplicable sous Windows
(`apps/api/tests/test_artifacts_storage.py`) et trois tests de refus de lien
symbolique (`apps/worker/tests/test_web_tests.py`) que le compte de vérification ne
peut pas créer. **Aucun test n'est ignoré faute d'opt-in Playwright : cet opt-in
n'existe pas dans le dépôt.**

Le scénario d'acceptation 7 reste le seul rejoué contre des services réellement
démarrés — API métier dans son propre processus et serveur MCP Streamable HTTP sur le
bouclage — avec **24 étapes sur 24 réussies**. Son script est désormais versionné
(`scripts/verify_mcp_journey.py`). Aucun équivalent n'existe pour le Lot E.

Ces tests prouvent les invariants locaux. Ils ne prouvent pas un navigateur réel, une
exécution Playwright réelle, un serveur MCP tiers, un dépôt GitHub réel, une instance
Hermes, un fournisseur payant, PostgreSQL existant, une sandbox OS, un E2E navigateur,
un déploiement Railway, ni une CI distante sur ce travail.

## Réalisé, non testé en conditions réelles

- l'appel plan/évaluation passe par le provider-gateway et échoue fermé, mais aucune
  instance Hermes `0.21.1`, clé, modèle, mémoire ou outil réel n'a été utilisé ;
- le backend lance et arrête de vrais processus locaux dans les tests, sans lancer
  d'agent externe ni effectuer d'effet sur un projet utilisateur ;
- le web et le CLI partagent les routes et contrats testés séparément, sans E2E
  navigateur → API → worker → Hermes ;
- la compatibilité locale SQLite est un upgrade ad hoc non versionné qui peut
  reconstruire des tables ; une sauvegarde préalable est requise. La migration d'une
  base PostgreSQL existante n'est pas fournie dans ce lot ;
- l'import d'un skill depuis GitHub, l'import d'archive et les refus de traversée sont
  prouvés sur transport simulé et sources locales : aucun dépôt ni archive tierce
  réelle n'a été téléchargée ;
- la sonde `stdio` est prouvée contre un serveur MCP déterministe écrit pour les tests,
  lancé par `sys.executable` sur la machine de vérification : aucun runner distant
  enrôlé, aucun serveur MCP tiers ;
- les écrans web du centre MCP et de la bibliothèque de skills sont couverts par des
  tests Vitest sur le DOM, pas par un parcours navigateur réel ;
- **le Lot E n'a jamais rencontré Playwright** : le reporter est prouvé sur des objets
  Playwright synthétiques et l'exécuteur du worker sur
  `apps/worker/tests/fake_playwright_runner.py`, un programme déterministe lancé par
  `sys.executable`. Aucun navigateur n'a été lancé, aucune capture, vidéo ou trace
  réelle n'a été produite, téléversée ou affichée ;
- le Studio et l'onglet « Livrables » sont couverts par des tests Vitest sur le DOM et
  par un test de câblage du shell ; **aucun parcours navigateur** ne les a exercés ;
- le flux SSE n'a été éprouvé que par un client de test ASGI : aucune coupure réseau
  réelle, aucun proxy intermédiaire, aucun `EventSource` de navigateur ;
- la purge de rétention est testée, mais n'a jamais été exécutée avec `--apply` sur des
  données d'exploitation, et aucun ordonnanceur ne la déclenche ;
- la migration additive de `events.sequence` et `events.journal_seq` n'est exercée que
  sur SQLite.

## Bloqué

Ces points ne dépendent pas d'un développement supplémentaire mais d'une ressource ou
d'une décision qui manque aujourd'hui.

- **Publication du Lot E** : le code est vérifié localement, mais la branche n'est pas
  fusionnée, aucune PR n'est ouverte pour ce lot, aucune CI distante n'a tourné sur les
  corrections de revue et cette documentation, et aucun tag `v0.6.0` n'existe. C'est
  une décision, pas un travail restant.
- **Passage des scénarios 10, 11, 16 et 19 à « Accepté »** : bloqué par l'absence d'une
  installation Playwright réelle sur un runner et d'un parcours de bout en bout
  versionné pour ce lot. Le code est là ; la preuve d'exécution réelle ne l'est pas.
- **Origine d'aperçu séparée** : bloquée par l'absence d'un second domaine ou
  sous-domaine dédié. Tant que `ACP_ARTIFACT_PUBLIC_ORIGIN` est vide, les liens signés
  sont servis par l'origine de l'API.
- **Passage des scénarios 7 et 8 à « Accepté »** : bloqué par l'absence d'un serveur
  MCP tiers et d'un dépôt GitHub réel autorisés pour la vérification, et par le fait
  que le parcours versionné ne couvre que le transport `http`.
- **Vérification Hermes réelle** : bloquée par l'absence d'instance, de clé et de
  modèle ; toute la lecture native est prouvée sur transport simulé.
- **Vérification PostgreSQL, sauvegarde et restauration** : bloquée par l'absence d'une
  base existante et d'une procédure de migration versionnée. La migration des deux
  compteurs d'événements est propre à SQLite.

## Non configuré ou restant

- sandbox OS, utilisateur non privilégié dédié et politique réseau vérifiée : sous
  Windows, le Job Object livré au Lot D borne l'arbre de processus du runner et de la
  sonde `stdio`, mais il n'impose ni quota CPU/mémoire, ni politique réseau ; c'est
  une clôture d'arrêt, pas une isolation ;
- scope cgroup ou unité de service POSIX équivalente au Job Object Windows : sur
  POSIX, l'arrêt repose encore sur `start_new_session` + `killpg`, qu'un descendant
  peut quitter en changeant volontairement de session ;
- l'autorisation d'un lancement `stdio` est un objet propre au centre MCP
  (`mcp_probes.authorization`) : elle n'est **pas** reliée à `ApprovalModel` ni au
  circuit d'approbation des missions, et n'apparaît donc ni dans `/approvals` ni dans
  `acp approvals` ;
- endpoint worker d'approbation d'une action exacte et exécution sensible ;
- le contrôle automatique d'un skill est une heuristique explicitement indicative :
  aucun scan certifiant, aucune signature vérifiée, aucun bac à sable d'analyse ;
- aucune installation automatique côté Hermes : la plateforme **exporte** une
  configuration `mcp_servers` et des placeholders `ACP_SECRET_*` à appliquer
  manuellement ; aucune API HTTP d'Hermes 0.21.1 ne permet d'écrire cette
  configuration ;
- migrations PostgreSQL versionnées, rollback et restauration ;
- exécution Playwright réelle : la chaîne reporter → worker → API est livrée et testée,
  mais aucun navigateur n'a jamais été lancé, et l'opt-in de test E2E réel
  (`ACP_E2E=1`) prévu par la spécification n'existe pas dans le dépôt ;
- prise de contrôle humaine du navigateur : **non livrée**, reportée au Lot G ; le
  Studio est en lecture seule et l'interface le dit ;
- diffusion d'images de session en direct : la plateforme ne produit aucune image ; les
  seules images disponibles sont les captures téléversées par le lanceur de tests ;
- trace viewer intégré : une trace Playwright se télécharge et s'ouvre hors de la
  plateforme ;
- origine d'aperçu séparée, adaptateur de stockage objet distant et purge de rétention
  planifiée ;
- courtier d'appels d'outils MCP pendant une mission : le Lot D livre le registre, la
  découverte, l'autorisation et la résolution des extensions, pas l'appel à
  l'exécution ;
- gestion des clés du coffre par un KMS/HSM et rotation planifiée ; les secrets de
  service (`HERMES_API_KEY`, Bearers inter-services) restent hors coffre ;
- automatisations, budgets agrégés, notifications et calendrier Europe/Paris ;
- médias, image, aperçu 3D et exécuteurs complémentaires ;
- E2E navigateur, Hermes réel opt-in, Railway et observabilité de production.

## Lots

| Lot | Capacité verticale | État |
|---|---|---|
| A | audit, shell moderne, Hermes Runs strict et exécution fail-closed | **Publié : PR #1, tag `v0.2.0`** |
| B | accès propriétaire, RBAC, onboarding et conversation persistante | **Publié : PR #2, tag `v0.3.0`** |
| C | runner réel contrôlé, missions, preuves, validations et CLI | **Publié : PR #3, tag `v0.4.0`** |
| D | MCP/skills versionnés, coffre de secrets, diagnostics et révocation | **Publié : PR #4, tag `v0.5.0` ; aucun serveur MCP tiers contacté** |
| E | événements durables, flux authentifié, Playwright, livrables privés et Studio | **Implémenté et vérifié localement (`0.6.0`), non publié ; aucun navigateur réel lancé, aucun test Playwright réel exécuté ; prise de contrôle du navigateur non livrée** |
| F | automatisations, calendrier Europe/Paris, budgets et alertes | **Non commencé** |
| G | médias/3D, exécuteurs complémentaires et durcissement | **Non commencé** |
| H | migrations, Railway, sauvegarde-restauration et validation finale | **Non commencé** |

## Reprise : du Lot E au Lot F

Ordre de reprise pour la personne ou l'agent qui prend la suite.

1. **Publier le Lot E** : ouvrir la PR, obtenir une intégration continue verte sur
   Ubuntu et étiqueter `v0.6.0`. Aujourd'hui la branche est poussée mais les
   corrections de revue et la documentation ne sont pas validées, donc aucune CI ne les
   a vues. C'est une décision, pas un travail restant.
2. **Exécuter une vraie suite Playwright sur un runner réel.** C'est la preuve qui
   manque au Lot E et la seule qui fasse progresser les scénarios 10 et 11. Concrètement :
   installer Playwright sur la machine du runner, configurer `ACP_WORKER_WEBTEST_ARGV_JSON`
   et `ACP_WORKER_WEBTEST_CWD`, lancer une mission portant une ressource
   `kind == "web_test_suite"`, puis vérifier dans le Studio la chronologie, l'arbre des
   tests, la capture et la trace réellement produites.
3. **Écrire l'opt-in de test E2E réel** prévu par la spécification (`ACP_E2E=1`,
   `skipped` sinon, jamais réussi par défaut) et le raccorder à la CI en opt-in. Il
   n'existe pas : aucun fichier du dépôt ne lit cette variable.
4. **Verser dans le dépôt un parcours de bout en bout du Lot E**, comme
   `scripts/verify_mcp_journey.py` l'a fait pour le scénario 7 : services démarrés,
   worker authentifié, ingestion d'une exécution de tests, flux SSE consommé avec
   reprise par curseur, téléchargement d'un livrable par lien signé puis révocation.
   Sans lui, aucun scénario de ce lot ne peut passer à « Accepté ».
5. **Configurer une origine d'aperçu séparée** (`ACP_ARTIFACT_PUBLIC_ORIGIN`) et
   vérifier que le Studio cesse d'afficher son avertissement. C'est le prérequis de
   sécurité avant toute exposition réseau du Studio.
6. **Enchaîner sur le Lot F** (automatisations, calendrier Europe/Paris, budgets et
   alertes). Deux briques du Lot E lui servent directement : le journal ordonné par
   `journal_seq`, sur lequel une automatisation peut reprendre sans doublon, et la
   dérivation de validation technique, qui donne un déclencheur fiable. Attention : la
   purge de rétention ne supprime aujourd'hui que les événements les plus anciens, ce
   qui garantit que les rangs ne sont jamais réutilisés ; une automatisation qui
   supprimerait les rangs les plus hauts casserait cette propriété.

Deux dettes du Lot D restent ouvertes et n'ont pas été traitées par le Lot E :
raccorder un serveur MCP tiers et un dépôt GitHub réel, et construire le courtier
d'appels d'outils MCP à l'exécution d'une mission. Le sort de l'autorisation `stdio`
(circuit propre au centre MCP ou circuit d'approbation des missions) reste lui aussi à
trancher.
