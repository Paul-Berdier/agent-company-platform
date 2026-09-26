# Journal des modifications

Les changements notables d'Agent Company Platform sont consignés dans ce fichier.
Le projet suit le versionnage sémantique ; tant que la version majeure reste à zéro,
les interfaces peuvent encore évoluer entre deux versions mineures.

## 0.11.0 (en cours) — refonte « Hermes au centre »

Branche `refonte/hermes`, ouverte depuis l'étiquette `archive/acp-0.10.0-avant-hermes`
(plan : `docs/refonte/plan.md`). La section complète (Ajouté, Modifié, Corrigé,
Sécurité, Vérifié localement, Limites connues) sera rédigée avant la PR finale vers
`main`, en 1.0.0.

### P0 — branche, élagage et gel du moteur

- retirés : API FastAPI, base et migrations, bus d'événements, passerelle de
  fournisseurs, CLI `acp`, interface web Vite (hors `apps/web/public/assets`),
  `packages/ui`, contrats TypeScript et Python (hors quotas), `agent-sdk`,
  `playwright-reporter`, `e2e`, déploiement Railway multi-services et scripts liés,
  documentation datée des lots A à H ;
- `apps/worker` devient `apps/poste` (commande `acp-poste` : `diagnostic`, local, et
  `quotas`, sur accord `ACP_WORKER_SUBSCRIPTION_QUOTAS=1`, qui lance Codex CLI, lequel
  interroge le serveur d'OpenAI ; le poste n'ouvre lui-même aucune connexion),
  élagué des modules liés à l'API ; le contrat des quotas passe dans
  `hermes/plugins/acp-poste/contrat` ; la ligne d'état Claude Code devient
  `python -m acp_poste.claude_statusline` ;
- `scripts/check_engine_frozen.py` : garde du gel du moteur Pixel Office ; CI en trois
  volets (moteur, poste sous Linux et Windows, desktop) ;
- corrections de la relecture indépendante : le refus des NUL du contrat ne contient
  plus l'octet NUL ; tests DPAPI réels rétablis ; commande `journal`, qu'aucun
  composant n'alimentait, et `ACP_POSTE_STATE_DIR` retirées ; `acp-poste quotas`
  refusé (code 2) sans l'accord `ACP_WORKER_SUBSCRIPTION_QUOTAS=1` ;
  `ACP_WORKER_QUOTA_INTERVAL_SECONDS`, sans effet, retiré ;
- les sections « Unreleased » et « 0.10.0 (préparation) » ci-dessous décrivent la ligne
  archivée : leurs fonctions côté API, web et CLI n'existent plus sur cette branche, et
  les documents qu'elles citent restent consultables sous l'étiquette d'archive.

### P1 — image dérivée et CI de contrat (sans Railway)

- `hermes/image/Dockerfile` : image Railway dérivée de
  `nousresearch/hermes-agent:v2026.9.24` épinglée par le condensat de son index
  (`sha256:fca358f1…`), `S6_BEHAVIOUR_IF_STAGE2_FAILS=2`, `CMD ["gateway","run"]`,
  `ENTRYPOINT` officiel conservé ;
- gardes de démarrage dans le crochet s6 `S6_STAGE2_HOOK` (`acp-gardes`), avant tout
  script cont-init : refus en français, code 1, de toute variable interdite ou invalide
  (émetteur OIDC non https, `API_SERVER_KEY`, `HERMES_MANAGED_DIR`, fournisseurs Nous,
  basic et drain, mandataires…) et de tout greffon utilisateur qui déclare un nom
  `acp-*` ; `05-acp` refait ces contrôles, verrouille `/opt/data/plugins`,
  `/opt/data/dashboard-themes` et `/opt/data/acp` (root 0755), dépose le thème et
  `SOUL.md` selon son empreinte ;
- managed scope `/etc/hermes` régénérée et relue à chaque démarrage : connexion au
  tableau de bord par OIDC auto-hébergé seulement, approbations manuelles,
  auto-décomposition du kanban coupée, profils lançables épinglés, aucun greffon
  utilisateur activable, anciens chemins d'import refusés, api_server en boucle locale,
  magasin de certificats et mandataires fixés ;
- greffon groupé `acp-poste` en squelette : route `GET /api/plugins/acp-poste/v1/meta`
  (contrat `acp-poste/1`) et adaptateur kanban qui importe chaque fonction depuis son
  module de définition ;
- contrat épinglé (`hermes/contrat/`) : `HERMES_VERSION` et copie de l'OpenRPC de la
  passerelle (MIT, provenance) ;
- tests dans l'image et tests de contrat pilotés depuis l'hôte, avec un modèle factice
  compatible OpenAI et un faux fournisseur d'identité ; workflow `image.yml` ;
- documentation : `docs/refonte/image.md`.

### P2 — premier déploiement Railway authentifié, agent sans terminal (préparé, non déployé)

Tout est prouvé en local et en CI ; **rien n'est déployé** : le premier déploiement est fait par le
propriétaire, selon `docs/refonte/railway.md`.

- **agent sans outil d'exécution sur Railway** (ni terminal, ni fichiers, ni code, ni navigateur,
  ni cron, ni délégation, ni connexions), en trois couches : managed scope à 40 clés (jeux
  d'outils coupés, `platform_toolsets` explicites pour api_server, CLI et cron,
  `coding_context "off"`, `service_tier ""`, `write_approval` des skills et de la mémoire,
  `hooks_auto_accept: false`, réseau privé et installations paresseuses fermés), `.env` géré à
  38 variables, et garde `pre_tool_call` en **liste blanche de 24 outils** dans `acp-poste`
  (`garde_execution.py`) ; `kanban_create` et `kanban_attach_url` refusés avec leur propre
  message ; `preview.restart` fermé dans le processus réel (deux tests bloquants : stdio
  `tui_gateway.entry` et `/api/ws` du vrai tableau de bord) ;
- **gardes de plateforme** : `acp-entree` refuse de démarrer hors du PID 1 ; le greffon arrête
  (code 78) une passerelle ou un tableau de bord lancés hors de s6 ; `/opt/data/hooks` et
  `/opt/data/scripts` exigés vides puis rendus à root ; sur Railway, volume exigé sur `/opt/data`
  (variable et point de montage réel) ; `RAILWAY_RUN_UID` absente ou `0` ; treize variables
  interdites et cinq valeurs imposées de plus ; domaine privé `*.railway.internal` refusé pour
  l'URL publique et l'émetteur ; commit déployé journalisé ;
- `diagnostiquer` : commande de maintenance en lecture seule (environnement du PID 1, clés
  exécutables de `config.yaml`, `lazy-packages`) ; `/v1/meta` gagne les blocs `garde_execution`,
  `reseau` et `deploiement` ;
- **fournisseur d'identité** `identite/` : Authelia 4.39.28 épinglé par condensat, un seul
  utilisateur réécrit à chaque démarrage, un seul client OIDC public `hermes-acp`, politique
  `deny` par défaut, passkeys (WebAuthn), secrets générés une fois dans le volume, garde root en
  français (`acp-identite-entree`), administration en maintenance (`acp-identite-admin`),
  HEALTHCHECK Docker de l'image amont retiré (élévation possible) ; limite mémoire **mesurée**
  (2,5 Gio) ;
- **infrastructure Railway** `.railway/railway.ts` : projet entier (services `hermes` et
  `identite`, deux volumes), branche `refonte/hermes`, Wait for CI, constructeur Dockerfile,
  santé, région EU West, limites, redémarrage, Serverless coupé, aucune Start Command, variables
  du propriétaire en `preserve()` ; libellés des sous-domaines en gabarit qui font **échouer
  fermé** plan et apply ; SDK `railway@3.11.0` isolé dans `.railway/` et épinglé par son verrou
  haché ; `verifier.mjs` évalue le fichier comme la CLI ;
- **procédure** du propriétaire (`docs/refonte/railway.md`) : premier déploiement pas à pas,
  identité et enrôlement, openai-codex, preuves à relever, `trusted_proxies`, exploitation,
  maintenance `/bin/sh -c "exec sleep infinity"`, restauration, sécurité du compte (clé SSH dédiée
  retirée après usage) ;
- **CI** : `image.yml` suit aussi `identite/**` et `.railway/**`, relève le condensat d'Authelia,
  construit l'image d'identité, type et évalue l'IaC, lance les tests d'identité et le test
  navigateur (Playwright, WebAuthn virtuel) ; hors PR, un groupe de concurrence **par
  exécution** : aucun run poussé n'est annulé ni remplacé ;
- tests : dans l'image (216), contrat depuis l'hôte (Hermes, identité, IaC), navigateur, et
  contrôle statique de l'IaC dans la suite du dépôt ;
- documentation : `docs/refonte/image.md`, `identite.md`, `railway.md` ; phases P4 à P8 du plan
  remplacées par le plan d'autonomie (`docs/refonte/autonomie.md`) ;
- corrections de la relecture indépendante (sécurité, exactitude, exploitation) :
  - **sécurité** : les `hooks/` et `scripts/` de **chaque profil** de `/opt/data/profiles` sont
    exigés vides puis rendus à root, comme ceux de la racine (un script cron de profil tournait
    sous l'uid 10000 sans refus) ; un lien symbolique sous `profiles/` refuse le démarrage ;
    `diagnostiquer` signale aussi les tâches cron à script ;
  - `diagnostiquer` lit `/run/s6/container_environment` comme `with-contenv` (un « \n » final
    retiré) : il rendait 29 faux constats sur un conteneur sain ;
  - sentinelle hors s6 : options globales à valeur relevées dans l'analyseur de Hermes (et
    comparées à lui par un test), `HERMES_HOME` normalisé (profils compris), `gateway` nu et
    `serve` visés ;
  - pont `tool_call` décrit tel que Hermes le traite (déballé avant la garde, qui juge l'outil
    sous-jacent) et prouvé dans les deux sens ; `kanban_create` n'est plus annoncé « en P5 » :
    les projets passent par les outils du greffon (P4) ;
  - `acp-entree` renvoie, sur Railway, à la procédure de refus PID 1 ; `identite` ne journalise
    plus l'identifiant du propriétaire (dépôt public) ;
  - `railway.ts` refuse tout projet lié autre que `acp` ; Node ≥ 22.6 exigé pour `.railway/` ;
  - CI : `ci.yml` n'annule plus de run hors PR (« Wait for CI ») ; l'étape finale d'`image.yml`
    échoue s'il restait des ressources de test ; le modèle factice doit répondre avant tout test
    qui conclut « aucune requête » ;
  - procédure Railway exécutable dans l'ordre écrit : CLI installée sans configuration d'agent,
    prérequis WSL et Node, compte GitHub relié, limites de dépense, clé SSH (mode opératoire),
    sauvegardes hors IaC contrôlées au plan, Rollback et 72 h de rétention sur Hobby, 503 et
    session de 7 jours décrits exactement, libellés publics et identifiant masqué, refus PID 1.

Limites connues de P2 (détail : `image.md` § 10, `identite.md` § 12, `railway.md` § 12) : le
tableau de bord authentifié reste un shell du propriétaire ; cookies de Hermes sans `Secure` tant
que `trusted_proxies` est vide ; jeton de rafraîchissement rejoué → 503 persistant ; rafale de
premiers facteurs non bornée ; `vision_analyze` peut faire décrire toute image locale lisible par
l'agent ; PID 1, bord, clés IaC non documentées, sort des sauvegardes posées hors IaC et coûts réels
ne se prouvent que sur Railway.

### P3 — identité, français et réglages prêts (réalisée côté dépôt, non fusionnée)

Première partie : identité visuelle et français.

- thème `acp` du tableau de bord généré depuis `design/tokens` (`scripts/generer_themes.py`, même
  chargeur que le QML du desktop, `--check` pour les deux), contrastes recalculés, aucune police
  téléchargée ;
- persona `SOUL.md` réécrite en français pour un agent sans outil d'exécution, avec vouvoiement ;
- greffons de tableau de bord `acp-interface` (Accueil à la place de « / », logotype « ACP »,
  bannière d'alertes, français verrouillé, contrôle du SDK) et `acp-catalogue` (onglet en lecture
  seule), sans code serveur, sources dans `apps/interface`, bundles committés et vérifiés en CI ;
- managed scope à 42 clés : `hermes-achievements` désactivé, police du thème et aucun greffon masqué
  épinglés ;
- décompte des chaînes de Hermes restées en anglais, mesuré sur l'image (105 clés du tableau de bord
  sur 746, 6 libellés de navigation, messages de l'agent complets) ;
- test navigateur de l'interface aux formats 390×844 et 1440×900 (catalogue des chaînes, axe,
  cibles tactiles, aucune requête externe) ; connexion factorisée avec le test de P2.

Limites connues (détail : `interface.md` § 9) : titre « Sessions » sur « / » imposé par Hermes ;
logotype visible au téléphone seulement dans le menu ; sélecteurs de thème et de police actifs
jusqu'au rechargement ; pages natives en partie en anglais (comptées, non traduites).

Seconde partie : réglages prêts (`docs/refonte/catalogue.md`).

- catalogue épinglé livré dans l'image sous `/opt/acp/skills` : 14 skills vendorisées à l'octet
  près depuis les blobs git de `emilkowalski/skills` (`d16ebe60`), `leonxlnx/taste-skill`
  (`c184364c`) et `affaan-m/ECC` (`v2.2.1`, `5064474`), toutes sous licence MIT, avec `LICENSE`,
  `PROVENANCE.md` et `hermes/THIRD_PARTY.md` ; 2 skills maison en français (`acp-redaction`,
  `acp-profils`) ; 10 skills candidates pour le poste (non planifiées) ; exclusions motivées (dont
  `literature-review`, de provenance incertaine, et les `docx`/`pdf`/`pptx`/`xlsx`
  d'`anthropics/skills`) ;
- verrou `hermes/catalogue/catalogue.lock.json` (empreintes, blobs git, licences, profils base, web,
  recherche, données) et `scripts/verifier_catalogue.py` (empreintes, licences, noms, collisions avec
  les 58 skills livrées et les 150 optionnelles de Hermes, texte seul, cohérence avec la garde et la
  managed scope ; `--amont` compare chaque fichier au dépôt amont), en CI ;
- au démarrage, `05-acp` écrit dans `/opt/data/config.yaml` (Hermes les lit sans la managed scope)
  `skills.external_dirs`, `skills.disabled` (46 skills livrées inertes sur Railway) et une entrée
  `mcp_servers.context7`, en gardant commentaires, propriétaire et mode ;
- context7, seul serveur MCP côté Hermes, **distant** : huit épingles (managed scope à 50 clés),
  `context7` dans `platform_toolsets.cli`, deux outils de plus dans la garde (26) ; échantillonnage
  et élicitation coupés ; `api_server` et cron sans MCP ; Playwright MCP prévu au poste en P8,
  Figma hors v1 ;
- refus de démarrer, et de relancer le tableau de bord, sur un serveur MCP stdio ou hors catalogue
  dans la configuration du volume (décision D8) ; `diagnostiquer` le signale ;
- `GET /api/plugins/acp-poste/v1/catalogue` et blocs `catalogue` et `interface` de `/v1/meta` ;
  l'Accueil et le Catalogue affichent l'état réel.

Limites connues (détail : `catalogue.md` § 10) : context7 non éprouvé depuis Railway et ses
conditions d'utilisation non lues ; il peut manquer au premier tour d'une première session du
tableau de bord ; profils nommés du volume sans réglages ; effet sur les workers kanban non prouvé
par un vrai worker.

Corrections de la relecture indépendante de P3 (exactitude et conformité, 14 constats ; détail :
`docs/reprise-poste.md` § 6 ter, « Relecture indépendante de P3 ») :

- `claude-design` et `hermes-agent-skill-authoring` **désactivées** (leur livrable exige un outil
  fermé sur Railway) : 46 skills livrées désactivées, 8 gardées, chacune avec une raison qui dit ce
  qui reste fermé (recherche d'`arxiv` par `curl`, fichier d'état, planification) ; un test de
  l'image relit leur texte ;
- côté poste, plus rien d'annoncé hors du plan d'autonomie : skills « candidates, non
  planifiées », Figma « hors v1 », Playwright seul « prévu en P8 » (vérificateur, route, onglet
  Catalogue, `acp-profils`) ;
- `skill-creator`, `mcp-builder`, `frontend-design` et `obra/superpowers` classés aux exclus
  (D12) ; le vérificateur exige que toute skill recommandée par le plan soit classée ;
- persona et `acp-redaction` : les skills du catalogue guident la méthode sans lever une règle ; le
  web, les réponses d'outils et toute autre skill restent des données ;
- test d'identité : une rafale ne compte que si elle a chargé les trois quarts de n vérifications
  argon2id simultanées, sinon elle est refaite (trois essais au plus) ;
- alerte d'un serveur MCP hors catalogue : le remède est dit (le supprimer depuis la page MCP
  avant tout redémarrage) et prouvé par les routes de Hermes ;
- captures du navigateur : rendu attendu, page blanche refusée, contenu défilant capturé en
  entier ; onglet Catalogue situé dans le groupe « Plugins » de Hermes (test et documentation) ;
- décompte des chaînes restées en anglais étendu à tout `web/src` (615 textes dans 31 fichiers) ;
- `scripts/balayer_secrets.py` (fichiers suivis et lignes ajoutées par la branche), en CI ;
- choix par défaut D1 à D20 de P3 consignés dans `plan.md` § 1, **non confirmés** par le
  propriétaire ; lecture des conditions de context7 exigée avant le premier déploiement.

### P4 — projets autonomes sur Hermes, cœur serveur (réalisé côté dépôt, non fusionné, non déployé)

Référence : `docs/refonte/projets.md`.

- greffon `acp-poste`, sous-paquet `noyau/` : un tableau kanban par projet, base propre
  (`plugin-data/acp-poste/data.db` : projets, demandes, questions, présence, curseurs et tables
  techniques), graphe déterministe [exploration par le poste] → planification → implémentation et
  relecture croisée par l'autre exécutant, ou carte Hermes → synthèse gardée par tout le tour ; un tour
  créé sous une seule transaction ; plafonds (3 tours, 30 cartes, 2 corrections) avec carte de triage ;
  corrections préparées (câblées en P6) ;
- routage déterministe contre le relevé du poste (contrat partagé `acp_poste_contrat.inventaire`) :
  surcharge, choix explicite, table ; efforts interdits (`max`, `ultra`, `ultracode`), palier
  `default` seul, effort hors énumération de Hermes gardé dans la demande et jamais posé sur la carte ;
- huit outils de l'agent (`projet_lancer`, `projet_planifier`, `projet_etat`, `poste_etat`,
  `poste_catalogue`, `question_repondre`, `question_escalader`, `routage_surcharger`), seuls ajouts à
  la garde (26 → 34 noms) ; `kanban_create` toujours refusé ; `memory` refusé dans un worker kanban
  (l'invite d'approbation attendait 300 s sans personne ; décision D40, à confirmer) ; section de prompt
  « acp-projets » ; Hermes diffère ces outils derrière `tool_search`, le modèle les appelle par
  `tool_call` ;
- routes `/v1/projets`, `/v1/questions`, `/v1/triage/…/reprendre`, `/v1/pause`, `/v1/poste`,
  `/v1/notifications/test` derrière la session du tableau de bord (JSON exigé, `Origin` contrôlé) ;
  bloc `projets` de `/v1/meta` ;
- émetteur de notifications dans la passerelle (crochet `on_kanban_dispatch_tick`) : une notification
  par événement, Telegram ou ntfy, désactivé sans `ACP_NOTIFICATIONS` ; variables retirées de
  `os.environ` par `register()` ; cartes `poste-*` étrangères bloquées ; présence du poste ; pause
  d'un projet et pause générale ; veille des crochets shell ;
- managed scope à 57 clés (répartiteur dans la passerelle, `max_in_progress` 4 et 2 par profil,
  `review_dispatch: false`, `failure_limit` 3, `known_plugin_toolsets`) ; démarrage refusé sur une clé
  `hooks` ou un `shell-hooks-allowlist.json` ; `HERMES_KANBAN_DISPATCH_IN_GATEWAY` interdite ;
- cinq skills maison des projets (`acp-exploration`, `acp-orchestration`, `acp-routage`,
  `acp-synthese`, `acp-questions`), persona et `acp-profils` mis à jour ;
- tests : poste simulé, faux serveur ntfy, modèle factice à scénarios ; contrat de bout en bout ;
  douze témoins négatifs (`scripts/temoins_negatifs_p4.sh`) ;
- corrigé en cours de route : accord de « carte » dans les notifications (« 1 carte », « 0 carte ») ;
- notifications : variables non déclarées dans `.railway/railway.ts` (canal non choisi), procédure
  d'activation par PR dans `railway.md` § 9 ;
- page « Projets » de l'interface : seconde partie de P4 (ci-dessous) ;
- choix par défaut D21 à D40 consignés dans `plan.md` § 1, **non confirmés** par le propriétaire.

### P4 — page « Projets » (seconde partie ; réalisée côté dépôt, non fusionnée, non déployée)

Référence : `docs/refonte/projets.md` § 4 bis, `docs/refonte/interface.md` § 10.

- greffon d'interface `acp-projets` (sans code serveur ; sources `apps/interface/src/projets/`, bundle
  déterministe committé) : onglet « Projets » avant « Catalogue », pensé d'abord pour le téléphone ;
  liste des projets (état, cartes faites, poste, questions, dernière note), formulaire « Nouveau
  projet » (dépôt désactivé et expliqué sans inventaire du poste ; exploration choisie seulement dans
  le relevé, efforts interdits exclus ; relevé factice signalé), détail (cartes par rôle, « Modèle
  servi : Non observé », tours et décisions, journal, pause et reprise), questions (réponse du
  propriétaire, reprise d'un triage ; cartes bloquées en lecture seule jusqu'à P7), notifications
  (test actif seulement avec un canal configuré), pause générale confirmée et son bandeau ;
- règle des boutons : aucun bouton sans route réelle et testée ; refus du greffon affichés tels quels ;
  clé d'idempotence par lancement ; sondage de 15 s tant que la page est visible (D35) ;
- raccourci « Projets » sur l'Accueil ; catalogue français à 274 chaînes ; les trois bundles portent le
  catalogue entier ;
- image : `acp-projets` copié et normalisé (root, 0644), version vérifiée par `check_version.py`,
  versions des greffons dans le bloc `interface` de la méta ; CI « Interface » : trois bundles vérifiés ;
- tests : Vitest 80 (dont 25 pour la page, sur des formes relevées sur l'image) ; route de reprise d'un
  triage et notification de test envoyée par la passerelle au faux ntfy ; navigateur
  `test_projets.py` : parcours « lancer un projet → questions → avancement » aux formats 390×844 et
  1440×900 avec le modèle factice et le poste simulé (axe sans violation grave, cibles de 44 px,
  chaînes du catalogue seulement, aucune requête hors de l'origine) ;
- corrigé en cours de route : les tests Vitest démontent toute racine React restée montée (des
  minuteries de sondage couraient dans le test suivant) ; espaces conservées dans les pastilles et les
  replis (conteneurs flex) ; le greffon rejoue une connexion à un tableau refusée à tort par le contrôle
  d'écriture de Hermes 0.21.5 (un `-wal` supprimé par un autre processus pendant le contrôle ; constaté
  une fois au contrat, trois tentatives, jamais sur un fichier vraiment illisible) ;
- écarts dits : icône `FolderOpen` (Hermes ne connaît pas `FolderKanban`), position `before:catalogue`
  (`after:acp` serait sans effet).

## [Unreleased]

### Quotas réels d'abonnement

- écran desktop « Quotas », réservé au propriétaire de la plateforme : une jauge
  par fenêtre de limite (utilisé et restant), remise à zéro en heure locale avec
  compte à rebours, fraîcheur du relevé, badge « Périmé », « Inconnu » pour toute
  valeur absente et mention « usage personnel » des abonnements ;
- relevé par le worker, en opt-in : Codex CLI connecté par compte ChatGPT via
  `codex app-server` (`account/rateLimits/read`, version minimale 0.100.0), et
  Claude Code via la ligne d'état fournie (`python -m acp_worker.claude_statusline`) ;
  environnement de Codex expurgé de toute clé d'API, arbre de processus borné ;
- `POST /work/workers/{id}/subscription-quotas` (worker) et `GET /subscription-quotas`
  (propriétaire seulement), relevés monotones ; un échec de lecture ne remplace
  jamais les derniers compteurs réussis ; migration `0005` ;
- schémas officiels du protocole `app-server` 0.156.1 épinglés comme contrat de test ;
- suite Python complète : 3 221 réussis, 68 ignorés ; tests PostgreSQL touchés :
  191 réussis ; 25 suites Qt vertes en Debug ;
- vérification réelle sur le poste : relevé de la ligne d'état lu par la sonde du
  worker, et Codex CLI 0.156.1 réel répondant « non connecté » sur le profil dédié.

Le chemin « compte connecté » de Codex n'est éprouvé qu'avec un faux `app-server`
validé contre les schémas officiels : le profil dédié attend la connexion du
titulaire. Figma et les crédits d'API ne sont pas mesurés. Détails et mise en place
dans [`docs/subscription-quotas.md`](docs/subscription-quotas.md).

### Interface conversations et projets

- accueil à deux entrées : chat libre sans titre préalable ou projet à créer/reprendre ;
- identité native graphite/ivoire/sarcelle et pictogrammes originaux ;
- sidebar avec projets et historique contextuel, inspecteur réel, précédent/suivant,
  volets adaptatifs et préférences de largeur conservées ;
- brouillons en mémoire par fil, recherche des titres chargés, code copiable,
  Entrée/Maj+Entrée et suivi du défilement respectant la lecture ;
- clics des fenêtres modales isolés de la navigation sous-jacente et largeur réelle du champ de saisie bornée ;
- notification immédiate de la création en cours, actualisation accessible pour
  rapprocher un envoi incertain et contexte général conservé au renommage d'un projet ;
- étapes dépendantes d’une équipe admises après la preuve Git finale, et nettoyage Windows fondé sur les handles épinglés ;
- suite Python complète : 3 037 réussis, 70 ignorés ; 492 tests Node réussis, typage et build verts ;
- 23 suites Qt vertes, deux parcours UI Windows et parcours Qt/API réelle avec création sans titre ;
- recette de l'interface et limites dans
  [`docs/desktop-chat-projects-2026-09-23.md`](docs/desktop-chat-projects-2026-09-23.md).

### Intégration fonctionnelle desktop et poste local

- formulaires Qt Standard, Codex, Claude et équipe ; conversations générales ou
  de projet, arrêt visible et commentaires actualisés ;
- focus clavier de la palette corrigé, contrôles natifs lisibles dans les deux
  thèmes, contenus métier rendus en texte brut ;
- états d'approbation et d'arrêt Hermes compris par le web, configuration d'équipe
  conservée dans les routines et confirmation Qt compatible avec le champ optionnel ;
- équipes supervisées dans des worktrees distincts, dépendances et concurrence
  bornées, checkpoints de résultats et rapports idempotents ;
- cycle asynchrone des Runs Hermes avec arrêt confirmé et reprise d'admission
  sous la même clé ; compétences épinglées et proxy MCP HTTP par délégation ;
- migration `0004` pour la déduplication MCP et garde de rollback pendant un appel ;
- outils Hermes/Claude épinglés, lanceurs ACP et worker locaux, coffre de notes
  Markdown dédié et secrets techniques/credentials worker protégés par DPAPI Windows ;
- refus des profils Hermes qui remplacent les bornes du lanceur via `.env` ;
- 3 025 tests Python réussis, 70 ignorés, 325 tests web réussis avec typage/build ;
- 22 suites Qt vertes, interactions réelles avec captures et parcours API jetable.

Les preuves détaillées et limites sont dans
[`docs/functional-completion-2026-09-23.md`](docs/functional-completion-2026-09-23.md).
Hermes répond localement, mais son diagnostic est dégradé ; aucune génération réelle
payante, reprise automatique d'équipe interrompue, fusion automatique des branches
produites ou publication finale 0.10.0 n'est annoncée.

## 0.10.0 (préparation) - 2026-09-23

Client natif Qt : intégration du Lot H et parcours métier reliés à l'API.
Cette version reste en préparation ; elle n'annonce pas une recette Railway achevée.

### Ajouté

- écrans natifs de projets, conversations, missions/tentatives, Studio et livrables ;
- inventaire des agents, workers et fournisseurs, liaisons MCP et compétences ;
- décisions d'approbation, alertes, budgets et automatisations avec formulaires typés ;
- réglages d'apparence, vérification explicite des publications GitHub et session
  mémorisée sur consentement dans le coffre Windows ;
- tests HTTP loopback, chargement QML et parcours du client Qt contre une vraie API
  SQLite jetable ; projection hachée du verrou Python pour cette recette en CI Windows.

### Modifié

- contexte de projet partagé par les écrans, navigation et palette de commandes ;
- arrêt, relance et envois incertains rapprochés avec la même clé pendant la session ;
- README, documentation de parité, sécurité, construction, installation et reprise
  alignés sur les fonctions présentes et les limites observées.

### Corrigé

- réponses et réessais d'une ancienne origine annulés après changement de serveur ;
- reprise de session préservant le contexte connu, refus 401/403 terminaux uniques,
  et absence de boucle de renouvellement sur un refus métier ;
- fermeture des services dans l'ordre de leurs dépendances et dialogues QML sans
  boucle de dimensionnement ;
- encodage des sorties MSVC stabilisé pour que Ninja détecte les changements d'en-têtes.
- droits effectifs de création de projet et de liaison d'extensions vérifiés avant envoi ;
- DLL redistribuables MSVC x64 embarquées dans le paquet portable, avec contrôle de version.

### Sécurité

- aucun cookie ACP transmis à GitHub ; notes de publication et contenus métier rendus
  en texte brut, liens de publication limités au dépôt officiel ;
- cookie mémorisé lié à l'URL complète et à son expiration ; aucun repli en stockage clair ;
- téléchargement de livrable atomique et borné, contrôles de taille/SHA-256, redirections refusées ;
- un corps HTML ou une redirection ne peut plus apparaître comme un flux SSE en direct.

### Vérifié localement

- backend combiné : 2 896 tests réussis, 70 ignorés ; contrats desktop : 6 réussis ;
- compilation MSVC Release et 21 suites natives réussies en 54,82 secondes ;
- parcours Qt/API réelle : 3 réussis, 0 ignoré, livrable de 180 224 octets vérifié ;
- session/coffre dans la session Windows locale : 24 réussis, aucun ignoré ;
- projection du verrou Windows : 4 tests réussis ; dépendance incrémentale MSVC prouvée ;
- portable démarré avec PATH Windows seul ; installation/désinstallation isolées sans élévation,
  codes 0, 1 387 fichiers vérifiés ; application installée non lancée pour préserver le profil ;
- résultats finaux de compilation, CI et empaquetage dans
  `docs/desktop-validation-2026-09-23.md` ; les tentatives échouées y restent distinguées.

### Limites connues

- recette Railway, fournisseur/worker réels, Windows propre et signature de code non prouvés ;
- première revue visuelle interrompue par l'expiration de l'autorisation de capture ;
  recette Qt complétée ensuite avec le harnais natif décrit dans la validation fonctionnelle ;
- mise à jour manuelle depuis la publication GitHub ; aucune installation automatique ;
- import/administration avancée de MCP et compétences encore partiellement réservés au web/CLI ;
- aucune publication 0.10.0 ni fin de la Desktop V1 annoncée ; Pixel Office conservé à part ;
- les 26 constats ouverts du Lot H demeurent suivis dans `docs/lot-h-091-review-status.md`.

## 0.9.1 (préparation) - 2026-09-22

Durcissement du Lot H en cours. L'inventaire des constats, des corrections reprises
et des travaux encore ouverts figure dans `docs/lot-h-091-review-status.md`.

### Ajouté

- migration PostgreSQL 0003 pour les tailles, durées, codes de sortie et séquences
  sur 64 bits, ainsi que les références longues ; schéma SQLite historique conservé ;
- tests de contention budgétaire et d'ingestion d'un rapport de 2 000 cas avec
  réservation concurrente ; suites et parcours PostgreSQL dans l'intégration continue ;
- validation commune des bornes de stockage, des horodatages UTC et des NUL.

### Modifié

- événements métier numérotés et journalisés au commit ; verrous de projet
  budgétaires compatibles avec les insertions filles tout en sérialisant les décisions ;
- relais SQLite avec réservation persistante courte et verrou libéré avant l'appel HTTP ;
  attente bornée des migrations au démarrage et recul en cas de panne du consommateur ;
- installation CI Python depuis le verrou haché, sans résolution des dépendances
  locales, puis vérification de cohérence des distributions et des déclarations.

### Corrigé

- messages d'outbox illisibles isolés en lettre morte ; une panne du consommateur
  n'épuise plus les essais d'un message valide ; hôtes HTTP internes autorisés explicitement ;
- gardes d'adoption du schéma, refus d'une révision inconnue et contrôle des tables
  attendues ; réutilisation de la connexion de migration avec un pool de taille un ;
- ouverture SQLite en lecture seule avec URI encodée, y compris pour les chemins
  contenant des caractères réservés ; résolution confinée des anciennes révisions
  de compétences après déplacement ou restauration du volume ;
- activation des clés étrangères dans les tests SQLite, avec correction des fixtures ;
- protection contre la remise à zéro d'une base de tests non identifiée, diagnostic
  de volume absent, déduplication des livraisons concurrentes et refus temporaires 503
  pour les interblocages et l'épuisement du pool.

### Sécurité

- diagnostics de messages illisibles expurgés de leur contenu et des détails SQL ;
- exclusions Docker récursives des données locales, secrets et éléments sous licence,
  avec contrôle du contexte et défense supplémentaire dans l'image web ;
- les garde-fous de schéma ne déclarent pas une base utilisable sur la seule présence
  d'une estampille Alembic.

### Vérifié localement

- SQLite : 2 852 tests réussis et 70 ignorés ; PostgreSQL : 2 862 réussis et 60 ignorés,
  après suites complètes et reprises ciblées documentées, sans modification du produit ;
- six parcours API réussis sur les deux dialectes, et construction des roues
  `acp-contracts`, `acp-database` et `acp-api` ;
- rapports initiaux, incidents de validation et limitations détaillés dans
  `docs/lot-h-091-review-status.md` ; les exécutions interrompues n'y valent pas succès.

### Limites connues

- 0.9.1 n'est pas publiée ; plusieurs constats de sauvegarde, rétention, déploiement,
  reprise du worker et routes asynchrones restent ouverts dans l'inventaire ;
- aucun déploiement Railway ni construction Docker pendant cette reprise ;
- garanties de restauration annoncées en 0.9.0 à restreindre : le rollback des
  répertoires ne couvre pas tous les échecs, et les gardes d'URL ne prouvent pas
  l'identité réelle des bases ; R19–R21 restent ouverts ;
- la comparaison de schéma contrôle les noms des contraintes CHECK, pas leur corps SQL ;
- livraison au moins une fois et réplique unique du relais nécessaires pour l'ordre global.

## [0.9.0] - 2026-09-18

Lot H : PostgreSQL et migrations versionnées, outbox transactionnelle avec reprise,
sauvegarde-restauration, images de services, configuration Railway et validation
finale.

### Ajouté

- chaîne de migrations **Alembic** versionnée (`packages/database/src/acp_database/migrations/`)
  avec une révision de base strictement identique au schéma du modèle et une révision
  additive pour la table d'outbox ; commande `python -m acp_database.migrate`
  (`upgrade`, `downgrade`, `current`, `check`, `history`, `stamp`) en français, avec des
  codes de sortie distincts pour le succès, l'usage, l'échec et le refus. Sous
  PostgreSQL, toute migration prend un verrou consultatif de session : deux
  pré-déploiements simultanés sont refusés au lieu d'être mis en file ;
- moteur PostgreSQL configuré et validé au démarrage : pilote `postgresql+psycopg`
  exigé, pool avec vérification préalable et recyclage, délais de connexion, de verrou,
  d'instruction et de transaction inactive, fuseau de session forcé à UTC, et refus
  explicite d'une variable d'environnement illisible plutôt qu'un repli silencieux ;
- `acp_database.locking` : verrou d'écriture unique à deux dialectes (transaction
  immédiate sous SQLite, verrou consultatif de transaction sous PostgreSQL) et verrou
  consultatif de session borné pour les opérations de maintenance ;
- **endpoint de disponibilité `GET /ready`** sur l'API et sur l'aperçu, distinct de la
  sonde de vivacité `/health` : base joignable avec sa latence, révision de schéma
  courante contre attendue, stockages inscriptibles, retard du relais. Réponse 503 dès
  qu'un contrôle bloquant échoue, sans chemin absolu ni secret dans le corps ;
- **outbox transactionnelle** : chaque écriture du journal insère, dans la même
  transaction, une ligne de livraison ; le relais `python -m acp_api.outbox_relay`
  (`--once`, `--follow`, `--list-dead`, `--requeue-dead`) livre dans l'ordre du journal
  et reprend après coupure. Sémantique au moins une fois, jamais exactement une fois ;
  lettres mortes après un nombre d'essais borné ; le consommateur déduplique par
  identifiant dans une fenêtre bornée ;
- **sauvegarde et restauration** : `python -m acp_api.backup` (`create`, `verify`,
  `inspect`, `restore`) couvrant la base et les répertoires de données, avec un
  manifeste porteur des empreintes, des comptages par table, de la révision de schéma et
  des identifiants de clés de coffre. La restauration refuse une cible non vide, refuse
  la base d'origine, refuse un dialecte différent, et contrôle l'état obtenu ;
- images de services non privilégiées, piles `compose` locales avec PostgreSQL,
  verrou de dépendances Python avec empreintes, et configuration Railway déclarative
  par service avec migration en pré-déploiement sur l'API seule ;
- trois parcours de vérification versionnés, exécutables sur SQLite et sur PostgreSQL :
  journal et flux d'événements, automatisations, sauvegarde et restauration ;
- outillage de test à deux dialectes : fabrique de moteurs, schémas éphémères,
  marqueurs `sqlite`, `postgres` et `concurrency`, et neutralisation de la base globale
  pendant les tests de l'API.

### Modifié

- `init_db()` suit désormais une politique propre à chaque dialecte : sous SQLite,
  création puis mise à niveau puis estampillage ; sous tout autre dialecte, **jamais**
  de création implicite, mais une vérification de révision qui refuse le démarrage si la
  base n'est pas à jour. Aucune variable n'active une migration implicite ;
- le démarrage de l'API et de l'aperçu échoue désormais fermé si la base est
  injoignable ou hors version : le serveur ne répond à aucune requête ;
- la commande de démonstration refuse de s'exécuter hors SQLite sans autorisation
  explicite ;
- le diagnostic du worker distingue la vivacité de la disponibilité et ne considère
  l'API prête que sur une réponse positive de `/ready`.

### Corrigé

- comparaison d'acceptation de mission portable, l'opérateur d'égalité de document
  n'existant pas sous PostgreSQL ;
- réservation de tâche qui ne verrouille plus tous les candidats, un second worker ne
  recevant plus « aucune tâche compatible » à tort ;
- expiration et renouvellement de bail par comparaison-et-échange, sans double
  événement d'interruption ni renouvellement d'un bail déjà expiré ;
- compteur de capacité d'un worker recalculé depuis les baux réellement actifs à la fin
  d'une tentative, au lieu d'être décrémenté depuis une lecture périmée qui écrasait la
  réservation d'une prise concurrente ;
- diagnostic HTTP validé avant l'appel réseau, puis résultat écrit par
  comparaison-et-échange, pour ne plus tenir une transaction pendant tout un appel ;
- collision d'allocation de numéro de journal reconnue par le code d'erreur structuré
  du pilote et non par le texte du message ;
- sortie des commandes de contrôle et des sous-processus de parcours forcée en UTF-8,
  une console régionale rendant auparavant les messages illisibles.

### Sécurité

- **la restauration ne vide plus la base cible avant les opérations réversibles** :
  les répertoires sont mis à l'écart d'abord, remis en place si la suite échoue, et la
  base n'est vidée qu'ensuite. Un échec après le vidage annonce explicitement l'état de
  la cible et l'emplacement de la sauvegarde préalable vérifiée ;
- une substitution d'outils de sauvegarde qui désigne une autre base que la cible est
  **refusée avant tout appel externe**, en citant les deux noms : une variable oubliée
  faisait auparavant vider une base et restaurer dans une autre ;
- les trois parcours de vérification **refusent une base PostgreSQL non vide** au lieu
  d'en effacer le schéma : ils ne remettent à zéro que ce qu'ils ont eux-mêmes migré
  depuis une base vide ;
- une erreur de verrou indisponible ou de délai dépassé est traduite en refus temporaire
  explicite, sans divulguer le SQL.

### Vérifié localement

- suite Python complète sur SQLite : **2 707 réussis, 32 ignorés**, aucun échec ;
- tests marqués PostgreSQL sur un serveur 16.15 réel : **28 réussis**, aucun échec ;
- parcours réels contre PostgreSQL 16.15 : journal et flux **77 étapes sur 77**,
  automatisations **64 sur 64**, sauvegarde et restauration **47 sur 47** ; les mêmes
  parcours passent sur SQLite ;
- refus prouvé : un parcours lancé sur une base contenant une table témoin la refuse et
  la table survit ;
- suites JavaScript inchangées : **311 tests web**, **59 du rapporteur**, **74 du
  moteur**, **34 des garde-fous E2E** ; vérification de types, construction et contrôle
  de synchronisation des versions réussis.

### Limites connues

- **aucun déploiement Railway réel n'a eu lieu** : la configuration, les images et les
  sondes sont écrites et construites localement, jamais observées en service ;
- l'import d'une base SQLite existante vers PostgreSQL n'est pas livré ; la sauvegarde
  et la restauration n'ont jamais été exécutées sur des données d'exploitation ;
- le relais d'événements exige une réplique unique : deux relais ne livrent jamais la
  même ligne, mais l'ordre entre eux n'est pas garanti. Sans la variable d'activation,
  le comportement historique sans reprise est conservé ;
- la déduplication du consommateur d'événements vit en mémoire : un redémarrage du
  service peut rediffuser un lot ;
- un volume d'hébergeur appartient à un seul service : l'origine d'aperçu ne peut pas
  lire les livrables de l'API sans stockage objet, non livré ;
- l'intégration continue n'exécute encore aucune suite PostgreSQL ni construction
  d'image : ces preuves sont locales ;
- des constats de revue de sévérité moyenne restent ouverts, notamment deux ordres de
  verrous inverses pouvant produire un interblocage sous forte concurrence, et une sonde
  de stockage qui ne distingue pas un volume absent d'un volume vide.

## [0.8.0] - 2026-09-14

Lot G : connecteurs médias et 3D, exécuteurs complémentaires, harnais de preuve E2E
réelle activé explicitement et durcissement des surfaces d'aperçu.

### Ajouté

- paquet Playwright `e2e/` isolé des workspaces et verrouillé sur `1.63.0` : opt-in
  exact `ACP_E2E=1`, connexion réelle, ouverture de Missions puis du Studio d'une
  tentative existante, frontière réseau au niveau du contexte et des popups, mutations
  refusées après la connexion, exactement une tentative de login, préflight CORS réel
  séparé et contrôle CORS de la réponse ; chaque HTTP est non retenté/non redirigé et
  tout `3xx` est bloqué avant le navigateur. `Worker`, `SharedWorker`, `WebTransport`,
  `RTCPeerConnection`, `webkitRTCPeerConnection`, `WebSocketStream` et `EventSource` sont
  neutralisés ; le Studio exerce son polling réel. Mono-worker Chromium headless,
  capture uniquement sur échec ; canal strict `chromium`, `chrome` ou `msedge` ;
- lanceur `scripts/verify_live_studio_journey.py`, lui-même opt-in, qui démarre une API
  et un Vite isolés, crée compte/projet/mission via l'API, puis exécute le vrai parcours
  navigateur sans fournisseur externe ni dépense ;
- job CI séparé, exécutable seulement via `workflow_dispatch` sur `refs/heads/main`
  avec `vars.ACP_E2E == '1'` déclaré au niveau dépôt ou organisation, puis dans
  l'environnement dédié `acp-e2e-staging` ; les secrets ne sont injectés que dans
  l'étape de preuve, isolée des installations. Avant d'y placer les identifiants,
  l'opérateur doit lui imposer un reviewer et limiter les branches de déploiement à
  `main` ; un push ne partage pas son groupe de concurrence ;
- aperçu GLB dans le Studio et la bibliothèque avec `@google/model-viewer` `4.3.1`
  chargé à la demande, contrôles caméra accessibles, sans AR ni autorotation ;
- connecteur ComfyUI privé : diagnostic `/v1/providers/comfyui/diagnostic` et génération
  `/v1/providers/comfyui/images`, workflow API local fixé par l'opérateur, prompt seul
  injecté, sortie PNG/JPEG/WebP validée ;
- capacités worker `codex_cli` et `claude_code` raccordées à la boucle de mission :
  exécutable et profil d'authentification absolus, racines projet allowlistées, un seul
  processus CLI de premier niveau par tentative, prompt transmis par stdin et preuve
  réduite aux tailles, empreintes et nombre d'événements JSONL ; un succès exige aussi
  l'événement terminal reconnu du CLI concerné.

### Sécurité

- un aperçu signé exige désormais une `ACP_API_URL` explicite et
  `ACP_ARTIFACT_PUBLIC_ORIGIN`, distincte de l'API et des origines web ; une
  configuration absente ou invalide répond `424` avant création du jeton, tandis que
  le téléchargement authentifié reste disponible ;
- l'origine d'aperçu dispose de l'application ASGI minimale `acp_api.preview:app` :
  uniquement santé et contenu signé `purpose=preview`, aucune session, route métier ou
  documentation, CORS exact sans credentials ;
- les deux routes d'écriture d'artefact worker exigent le fencing token courant. Le
  téléversement de contenu le revérifie sous verrou après lecture du corps et avant
  quota, déduplication, stockage ou insertion ;
- un `.glb` n'est promu en aperçu qu'après validation GLB 2 stricte au téléversement et
  scellement par sha256 ; `.gltf`, URI externes, chunks inconnus et extensions
  Draco/Meshopt/Basisu sont refusés pour l'aperçu. Buffers, vues, offsets/strides et
  accessors sont contrôlés sous budgets cumulés ; sparse est refusé. Les en-têtes et
  dimensions PNG/JPEG/WebP ainsi que les budgets compressés, pixels et RGBA+mipmaps
  sont validés sans décompression serveur ;
- le client ComfyUI refuse HTTP hors loopback, redirections et proxies ambiants, borne
  workflow, réponses, polls, durée et image, puis vérifie type, extension et signature ;
  générations, waiters et cache sont bornés séparément/en octets, et une tentative
  `/prompt` incertaine réserve un tombstone non évictable avant sa TTL. Le connecteur
  se met aussi en quarantaine, réconcilie `/history` et `/queue`, supprime seulement son
  prompt encore en attente et n'utilise `/interrupt` que sur une instance explicitement
  exclusive avec concurrence fixée à un ;
- Codex et Claude ne sont jamais détectés implicitement dans le `PATH`. L'exécution
  réutilise la clôture Job Object/session POSIX, un environnement minimal et une
  deadline ; le worker demande à Codex de désactiver web, MCP, plugins et multi-agent,
  et demande à Claude de se limiter à `Read,Glob,Grep` en lecture seule. Les capacités
  explicites/persistées sont revérifiées contre backend, scope projet et racine avant
  tout appel API ; scope global agent, scope absent et capacité générique sans runner
  sont refusés. Les écritures Codex d'une même racine sont sérialisées par un verrou
  interprocessus coopératif adjacent au projet ; une clôture incertaine publie une
  quarantaine `.poison` durable et jamais levée automatiquement ;
- l'exécuteur lance au plus un processus CLI de premier niveau par tentative.
  `spawned_agents=1` décrit cette seule invocation gérée par ACP : les processus ou
  agents que le binaire créerait ensuite ne sont ni bloqués ni comptés.

### Vérifié localement

- passe Python complète finale : **2 498 réussis, 7 ignorés et 2 avertissements de
  dépréciation connus** sous Python 3.12.0 ;
- **34 tests** unitaires des garde-fous E2E, **311 tests web sur 24 fichiers**, **59
  tests reporter** et **74 tests moteur** ;
- **263 tests API/worker ciblés réussis, 3 ignorés** pour le fencing des tentatives,
  les livrables et l'aperçu, ainsi que **62 tests ciblés ComfyUI** ; typecheck
  TypeScript, compilation Python, build Vite et synchronisation de version réussis ;
- parcours d'automatisation **62/62** réussi et parcours shell/Studio dans un vrai
  Edge : **1 test réussi en 11,6 s** ;
- la commande Codex générée a été vérifiée contre l'aide du CLI local ; aucun run agent
  ni appel réseau payant n'a été déclenché.

### Limites connues

- le parcours shell/Studio a été exécuté dans un vrai Edge local, mais aucun rendu GLB
  WebGL, serveur ComfyUI réel, Codex CLI authentifié, Claude Code authentifié ni chaîne
  reporter → worker avec capture/vidéo/trace réelle n'a été exécuté ;
- l'idempotence ComfyUI est bornée à la mémoire d'un processus : redémarrage ou réplica
  peuvent rejouer un effet, les succès LRU peuvent être évincés avant leur TTL, et il
  n'existe ni file durable, ni reprise, ni stockage d'artefact, ni raccordement aux missions ;
- aucune origine d'aperçu séparée n'est configurée dans le dépôt ; les aperçus restent
  donc désactivés par défaut, sans affecter le téléchargement ;
- le verrou d'écriture Codex ne remplace ni les ACL du parent ni l'isolation OS ; sa
  sémantique doit être validée sur un partage réseau, sinon chaque worker doit recevoir
  un checkout/worktree distinct ;
- la reprise en main humaine du navigateur, la sandbox OS/réseau forte, le stockage
  objet, PostgreSQL, Railway et la sauvegarde/restauration ne sont pas livrés.
- une racine projet fixe le cwd mais n'isole pas les fichiers accessibles au compte
  worker. Deux projets non mutuellement fiables exigent des comptes, conteneurs ou VM
  distincts ; sous POSIX, `killpg` ne détecte pas un descendant ayant appelé `setsid()` ;
  les chemins autorisés sont résolus mais leur identité n'est pas épinglée contre un
  remplacement concurrent, donc leurs répertoires parents doivent être protégés.

## [0.7.0] - 2026-09-14

Lot F : automatisations, calendrier IANA, budgets appliqués, saturation du stockage,
alertes in-app et surfaces web/CLI.

### Ajouté

- contrats Python et miroir TypeScript stricts pour les routines, calendriers,
  déclenchements, webhooks, budgets, consommations et alertes ;
- cron à cinq champs interprété dans un fuseau IANA et intervalles fixes de 60 secondes
  à un an ; une heure locale inexistante est omise, une heure ambiguë ne produit que sa
  première occurrence, et la recherche est bornée à quatre ans ;
- modèles persistants `automations`, `automation_runs`,
  `automation_webhook_rotations`, `automation_commands`, `scheduler_leases`,
  `project_budget_policies`, `budget_usage`, `budget_usage_reports`, `alerts` et
  `notification_preferences` ;
- extension de la table existante `workers` avec une portée d'enrôlement globale ou
  limitée à un projet, exclusive et explicite ;
- routes de création, liste, détail, modification, activation, suspension, tir manuel,
  historique et calendrier des routines ; création et tir manuel idempotents ;
- webhook entrant avec secret fourni par le client, 256 bits au minimum, empreinte
  seule en base, rotation idempotente, révocation et déduplication par `event_id` ;
- planificateur worker à bail singleton de 45 secondes, fencing monotone, traitement
  transactionnel, rattrapage `skip`/`run_once`, plafond de concurrence et
  réconciliation des missions terminales ;
- permis de budget avant les phases de planification, exécution et évaluation, ledger
  idempotent et lecture de consommation par mission, jour et fournisseur ;
- alertes durables, dédupliquées par cause, escalade monotone, acquittement et
  préférences personnelles ; canal `in_app` uniquement ;
- détection explicite de la saturation (`507`) et de l'indisponibilité (`503`) du
  stockage local, avec alerte expurgée lorsque le projet et le run sont déjà résolus ;
  réparation atomique d'un blob adressé par contenu devenu incohérent ;
- écran Automatisations à quatre vues — routines, calendrier, alertes, réglages — avec
  assistant de création, historique, webhook, politique et consommation budgétaires ;
- proposition de routine préremplie depuis une mission réussie, techniquement validée
  et acceptée ; elle reste désactivée jusqu'à activation explicite ;
- groupe CLI `acp automations` : `list`, `create`, `show`, `update`, `enable`,
  `disable`, `trigger`, `runs`, `calendar` et `webhook status|rotate|disable`, plus un
  gabarit de mission d'exemple ;
- parcours `scripts/verify_automation_journey.py` démarrant une API réelle sur SQLite
  temporaire : **62/62 étapes réussies** localement, sans Internet ni dépense.

### Modifié

- seuls les workers enrôlés avec un privilège global explicite concourent au
  planificateur ; les workers ordinaires sont limités au projet autorisé côté API et
  le mode `--once` ne démarre pas la boucle ;
- les créations et rotations pouvant avoir abouti malgré une réponse perdue conservent
  leur clé d'idempotence côté web et CLI afin de rejouer la même opération ;
- les budgets conservent la différence entre mesure absente et zéro, utilisent des
  montants décimaux, figent le jour comptable d'un permis jusqu'à son rapport et
  interdisent de changer le fuseau après la première ligne du ledger ;
- l'upgrade SQLite reconstruit transactionnellement tout schéma partiel des dix
  nouvelles tables et de la table `workers` étendue vers la parité du modèle, préserve
  les index/triggers locaux compatibles et refuse de reconstruire un ledger historique
  impossible à compléter honnêtement ;
- l'interface annonce les limites de page et les mesures inconnues, sans inventer un
  total global ou un coût nul ; les compteurs agrégés au-delà de l'entier sûr sont
  plafonnés sur le wire et nommés dans `saturated_metrics`, tandis que le ledger reste
  exact.

### Sécurité

- la `fire_key` déterministe et une contrainte unique SQL arbitrent les tirs
  concurrents ; le verrouillage ne dépend pas d'une vérification en mémoire ;
- le bail et le `fencing_token` sont revérifiés entre les transactions ; un détenteur
  expiré ne peut ni lancer une occurrence ni libérer le bail d'un successeur ;
- trois échecs terminaux consécutifs désactivent la routine et ouvrent une alerte ; une
  routine invalide produit un verdict durable expurgé au lieu d'affamer la file ;
- les mutations de session restent protégées par CSRF et RBAC ; le webhook entrant
  transporte son secret uniquement dans `Authorization: Bearer`, jamais dans l'URL ;
- les préférences filtrent la boîte personnelle sans supprimer ni modifier l'alerte
  canonique du projet ;
- les rapports de budget exigent l'identité worker, un lease actif et le fence de la
  tentative, et les dépassements échouent fermés ; les compteurs et coûts partagent
  les mêmes bornes Python/TypeScript/SQL et le cache agrégé sature sans perdre le
  ledger exact ;
- les relances verrouillent et relisent tentative, policy et compteur avant un CAS ;
  un fence futur inventé est refusé, et les workers historiques sans portée explicite
  restent en quarantaine ;
- une borne de coût worker est arrondie vers le haut avant son transport JSON : une
  conversion binaire ne peut jamais sous-réserver le montant décimal ;
- les corps HTTP sont bornés avant parsing (1 Mio en général, 32 Mio pour les sources
  de skills), avec `Content-Length` décimal strict et limites multipart appliquées
  même en chunk monobloc ; le téléversement de livrable reste authentifié et borné en
  flux, et le webhook entrant est limité à 120 requêtes/minute par adresse TCP et
  processus ;
- les sondes MCP non ciblées exigent un worker global ; une sonde ciblée ne peut être
  réclamée que par le worker nommé, avec transition atomique et TTL relu après verrou
  avant divulgation de ses références de secrets ; expiration, claim et rapport final
  s'arbitrent par transitions conditionnelles.

### Limites connues

- `max_spawned_agents_per_run` est validé, persisté et affiché, mais son application
  attend le point de spawn des exécuteurs du Lot G ;
- aucun navigateur réel, fournisseur payant, Hermes réel ou service externe n'a été
  utilisé pour les preuves de ce lot ;
- le stockage reste local ; aucun adaptateur objet externe n'a été testé ;
- PostgreSQL, Alembic, Railway, sauvegarde et restauration restent au Lot H.

## [0.6.0] - 2026-09-13

Lot E : événements durables, flux authentifié, tests web structurés, livrables privés
et Studio en lecture seule. Vérifié localement le 13 septembre 2026, puis publié par
la PR #5 après observation d'une CI verte ; commit de fusion `b7d8a44`, tag `v0.6.0`.

**Aucun navigateur réel n'a été lancé et aucun test Playwright réel n'a été exécuté** :
le reporter est prouvé sur des objets Playwright synthétiques, et l'exécuteur du worker
sur un programme déterministe (`apps/worker/tests/fake_playwright_runner.py`). La
reprise en main humaine du navigateur n'est pas livrée et l'interface le dit.

### Ajouté

- journal d'événements durable : `events` gagne `schema_version`, `conversation_id`,
  `step_id`, `executor`, `emitted_by`, une séquence monotone **par tentative** et un
  compteur monotone **du journal** (`journal_seq`), tous deux alloués dans la
  transaction métier et protégés par un index unique partiel ;
- lecture par curseur `GET /runs/{id}/events` et `GET /projects/{id}/events`
  (`EventPage` avec `next_cursor`, `has_more`, `retention_days`) ;
- flux SSE authentifié servi par l'API métier : `GET /streams/runs/{id}` et
  `GET /streams/projects/{id}`, reprise par `Last-Event-ID` ou `?after_seq=`,
  keep-alive `: ping`, rotation propre annoncée avec son curseur, limite de connexions
  par utilisateur, `Cache-Control: no-store` et `X-Accel-Buffering: no` ;
- stockage de livrables adressé par contenu sur disque (`ACP_ARTIFACT_STORAGE_DIR`,
  clé `<sha256[0:2]>/<sha256>`) derrière une interface `ArtifactStorage`, avec
  téléversement worker `POST /workers/{id}/artifacts/content` (multipart, idempotent
  par sha256, plafond par fichier et quota par tentative appliqués pendant le flux) ;
- routes de bibliothèque `GET /artifacts`, `GET /artifacts/{id}` et
  `GET /artifacts/{id}/content` (support des requêtes `Range`), liens signés
  `POST /artifacts/{id}/link` et révocation `DELETE /artifacts/links/{link_id}` ;
- résultats de tests structurés : tables `test_runs` et `test_cases`, ingestion
  worker `POST /workers/{id}/test-runs`, lectures `GET /runs/{id}/test-run` et
  `GET /test-runs/{id}`, événements `test.run.started`, `test.case.finished` et
  `test.run.finished` ;
- workspace npm `@acp/playwright-reporter` : reporter Playwright **sans dépendance
  runtime** et sans appel réseau, qui écrit un NDJSON local dans `ACP_REPORT_FILE` ;
- capacité worker `web_tests` (désactivée par défaut) et module
  `acp_worker/web_tests.py` : lancement de l'argv configuré par l'opérateur dans la
  clôture d'arrêt du runner, ingestion du NDJSON, téléversement des pièces jointes et
  preuve de mission `web_tests` résumant totaux, code de sortie et identifiant du
  `test_run` ;
- commande de rétention `python -m acp_api.retention` (purge à blanc par défaut,
  `--apply` pour supprimer) ;
- Studio web en lecture seule dans le détail d'une mission et sur
  `/missions?run=<id>&vue=studio`, et onglet « Livrables » de la bibliothèque ;
- commandes CLI `acp runs events`, `acp runs tests`, `acp artifacts list | get | link`
  et `acp open --run <id> --studio` ;
- contrats partagés `StreamEvent`, `EventPage`, `TestRunSummary`, `TestRunDetail`,
  `TestCaseResult`, `TestStep`, `TestTotals`, `ArtifactSummary`, `ArtifactLink`,
  `ArtifactPage`, en Python et en TypeScript.

### Modifié

- le flux temps réel utilisateur est servi par l'**API métier**, pas par
  `apps/event-service` : l'API détient la base, les sessions et le RBAC. Le service
  d'événements reste un relais interne, son ingestion reste authentifiée et son
  WebSocket anonyme reste fermé par défaut ;
- `events_bus.store_event` n'effectue plus de `commit()` implicite quand l'appelant
  fournit sa transaction ; les appelants existants passent `commit=True` et conservent
  le comportement du Lot C ;
- quatre écritures directes d'`EventModel` (`routers/secrets.py`, `routers/workers.py`,
  `mcp/service.py`, `skills/service.py`) passent par `events_bus.store_event` : sans
  numéro, ces lignes sortaient de la page projet et du flux projet ;
- la route web « Bibliothèque » devient un écran à deux onglets, `Skills` (délégué tel
  quel au module du Lot D) et `Livrables` ; aucun élément de navigation n'est ajouté ;
- `GET /artifacts` est servi par le nouveau routeur paginé ; la version « liste
  complète » qui vivait dans `routers/operations.py` est supprimée plutôt que dupliquée ;
- les versions des composants publiables sont synchronisées sur `0.6.0`, y compris le
  nouveau workspace `packages/playwright-reporter` ;
- aucune dépendance runtime n'a été ajoutée : ni en Python, ni côté web, CLI, worker ou
  reporter.

### Sécurité

- un contenu produit par un test est traité comme non fiable : le type servi vient
  d'une allowlist serveur (extension + type déclaré) sans aucun reniflage, `text/html`,
  `image/svg+xml` et les archives — dont la trace Playwright — ne sont **jamais**
  servis en ligne, et toute réponse porte `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox` et
  `Cache-Control: private, no-store` ; le Studio n'utilise ni `iframe`, ni `srcdoc`, ni
  `innerHTML` pour un contenu venu de l'API ;
- les liens de téléchargement sont signés (HMAC-SHA256), bornés à 900 secondes au
  maximum, liés à l'artefact **et** au demandeur, enregistrés par empreinte et
  révocables ; sans `ACP_ARTIFACT_SIGNING_KEYS`, la création répond `503` explicite et
  le téléchargement par session reste possible ; aucun projet ne devient public ;
- le processus de test ne reçoit **aucun credential de la plateforme** : le reporter
  écrit un fichier local et n'appelle jamais le réseau ; messages d'erreur et extraits
  de code sont expurgés (`redact_text` / `redact_data`) avec les valeurs injectées dans
  son environnement avant d'être envoyés à l'API ;
- l'exécution de tests web réutilise `spawn_fenced_process` et
  `terminate_process_tree` : jamais de shell, jamais de spawn direct, et un arrêt
  d'arbre non prouvé interdit tout verdict `passed` ;
- une pièce jointe n'est téléversée que si sa résolution canonique reste sous le
  répertoire de sortie de la tentative ; liens et `..` sont refusés, comptés et
  signalés, et un refus interdit le verdict `passed` ;
- le nom d'origine d'un fichier n'entre jamais dans un chemin de stockage : la clé est
  dérivée du sha256 ;
- le RBAC d'un flux est revérifié **à chaque page**, pas seulement à l'ouverture : une
  révocation de session ou une perte de membership ferme la connexion au plus tard à
  l'interrogation suivante ;
- la rétention ne supprime jamais un événement terminal de tentative, ni un blob encore
  référencé par un autre artefact, ni un artefact cité par une preuve de mission — la
  citation est détectée en balayant toutes les chaînes de `evidence.data`, pas une
  liste de noms de clés ;
- écart assumé et affiché : `ACP_ARTIFACT_PUBLIC_ORIGIN` n'est configurée nulle part.
  Les aperçus signés sont donc servis par l'origine de l'API, et le Studio l'annonce.
  Une instance dans cet état ne doit pas être exposée sur Internet.

### Corrigé

- **la page projet du journal perdait des événements.** Son curseur dérivait de
  `created_at` en microsecondes ; la granularité réelle de l'horloge (environ 1,5 ms
  sur la machine de vérification) rend les égalités courantes, une page pouvait donc
  dépasser la limite annoncée **et** avancer au-delà de lignes jamais rendues, tout en
  annonçant `has_more: false`. Le compteur `journal_seq` donne un ordre total : une
  page ne dépasse plus sa limite, `has_more` est exact, et 300 publications sans pause
  sortent exactement une fois chacune. Les `time.sleep` que les tests inséraient pour
  éviter l'égalité — et qui masquaient le défaut — sont retirés ;
- **le journal et le flux de tentative perdaient tous les événements du Lot C.** Seul
  `publish` allouait une séquence de tentative, alors que les producteurs du Lot C
  écrivent par `store_event` : leurs événements terminaux n'entraient ni dans
  `GET /runs/{id}/events` ni dans le flux SSE ;
- **le reporter pouvait annoncer un faux succès** : ses totaux étaient indexés par une
  identité de test pouvant entrer en collision, et un test réussi écrasait un test
  échoué ;
- une pièce jointe fournie en ligne produisait une forme que le contrat d'ingestion
  refusait, et le worker écartait alors toute la ligne du test — donc son statut et son
  erreur ;
- une troncature tombant au milieu d'une paire de substituts UTF-16 produisait un
  caractère isolé que le contrat rejetait ensuite ;
- **le worker écrivait un second verdict par-dessus celui de l'API** : un rapport qui
  sous-déclarait ses échecs transformait un `failed` serveur en `passed` mission.
  L'adoption du verdict serveur est désormais à sens unique — elle ne peut
  qu'aggraver ;
- **le code de sortie annoncé par le rapport écrasait celui mesuré par le worker** :
  n'importe quelle ligne NDJSON ajoutée par le processus de test obtenait une
  validation technique verte pour un processus réellement sorti en `1` ;
- une seconde ingestion ne portant qu'un `run_end` à code de sortie nul écrasait le
  code non nul déjà enregistré d'une exécution terminale ;
- la rétention effaçait le rapport Playwright cité par une preuve `web_tests` ;
- `payload.attachments[]` n'était jamais lu par le Studio : le panneau « dernière
  capture » affichait toujours « aucune capture », même pour une exécution qui en
  téléversait une ;
- un en-tête `Range` de plus de 4 300 chiffres provoquait un `500` au lieu d'être
  ignoré comme le demande la RFC 9110 ;
- `acp runs tests` annonçait « validation technique : réussie » et sortait `0` pour une
  exécution que la plateforme considère en échec ; `acp open --studio` émettait un
  paramètre que l'interface n'interprète pas ; `acp artifacts list --kind` filtrait le
  mauvais champ ;
- la disponibilité de la capacité `web_tests` lisait la variable d'environnement de
  simulation au lieu du mode d'exécution effectif ;
- un `Content-Disposition` contenant un point-virgule dans le nom de fichier déviait
  l'analyse, et un type déclaré « jamais en ligne » pouvait encore être servi avec une
  disposition d'affichage.

## [0.5.0] - 2026-09-12

Lot D : extensions contrôlées (centre MCP, bibliothèque de skills, coffre de
secrets). Vérifié localement le 12 septembre 2026, puis publié après intégration
continue verte. Aucun serveur MCP tiers, dépôt GitHub réel ni runner distant réel
n'a été contacté : les preuves reposent sur des transports simulés, des programmes
déterministes locaux et un parcours de bout en bout joué contre des services
réellement démarrés sur le bouclage.

### Ajouté

- coffre de secrets chiffrés (Fernet) à références : portées `platform`/`project`,
  `key_id`, rotation de clé sans perte par `ACP_SECRETS_KEYS`, révocation, dernier
  usage, routes `/secrets` et groupe CLI `acp secrets` (valeur uniquement par
  `--value-stdin`) ;
- politique de sortie réseau `outbound.py` : `https` exigé hors allowlist, blocage du
  bouclage, des réseaux privés, de la métadonnée cloud, du CGNAT et des plages IPv6
  équivalentes, contrôle de toutes les adresses résolues, épinglage de l'adresse
  pendant la requête, revalidation des redirections, corps borné et audit de chaque
  usage d'une allowlist privée ;
- centre MCP : catalogue vérifié, serveurs versionnés (empreinte, diff, risques,
  rollback), diagnostic HTTP exécuté par l'API et diagnostic `stdio` soumis à une
  autorisation explicite exécutée par un runner authentifié, rattachements par projet
  limités à un sous-ensemble d'outils, activation, désactivation et révocation
  auditées, import Hermes/Claude/Codex et export avec placeholders
  `${ACP_SECRET_…}` ;
- bibliothèque de skills : import borné depuis un `SKILL.md`, un dossier autorisé, une
  archive ZIP ou un commit GitHub épinglé, révisions avec manifeste SHA-256,
  frontmatter, licence, dépendances et contrôle automatique indicatif, approbation
  d'une portée accrue, rattachements par projet, rollback et révocation ;
- extensions résolues par projet (`GET /projects/{id}/extensions`) et instantané figé
  dans `meta["extensions"]` d'une mission ;
- capacité worker `mcp_stdio_probe` (désactivée par défaut, allowlist d'exécutables
  absolus obligatoire) et sonde MCP stdio sans shell, à environnement minimal, durée
  et sorties bornées ;
- écrans web du centre MCP et de la bibliothèque de skills, groupes CLI `acp mcp`,
  `acp skills` et `acp projects extensions`, lecture des skills et toolsets natifs
  Hermes dans Connexions.

### Modifié

- la route web « Bibliothèque » devient une capacité configurée et « Connexions »
  accueille le centre MCP et le panneau des secrets ; les helpers d'interface partagés
  sont extraits dans `apps/web/src/ui-primitives.ts` sans changement de comportement ;
- le shell web transmet son client HTTP et son jeton CSRF aux modules Connexions et
  Bibliothèque au lieu de les laisser ouvrir leur propre session : un seul jeton CSRF
  est en circulation, réinitialisé à la connexion comme à la déconnexion ;
- les groupes CLI `mcp` et `skills`, jusqu'ici des stubs « non supporté », sont
  raccordés à l'API ; le script de complétion liste `secrets`, `mcp` et `skills`
  (`automations` reste explicitement non supporté) ;
- la création d'une mission fige les extensions résolues du projet dans
  `TaskModel.meta["extensions"]` ; le contrat `MissionSummary` est inchangé ;
- le provider-gateway expose `GET /v1/providers/hermes/native-listing` et l'API métier
  la relaie en lecture seule sur `GET /connections/hermes/native-listing` ;
- `apps/api` dépend désormais de `cryptography>=45,<48` et `pyyaml>=6,<7` ; aucune
  dépendance ajoutée côté web, CLI ou worker ;
- les versions des composants publiables sont synchronisées sur `0.5.0`.

### Corrigé

- arrêt déterministe d'un arbre de processus sous Windows : tout spawn du runner et de
  la sonde MCP `stdio` est créé suspendu, affecté à un Job Object
  `KILL_ON_JOB_CLOSE` sans `BREAKAWAY_OK`, puis repris ; l'affectation est revérifiée
  et un échec devient `spawn_failed` / `job_assignment_failed` au lieu d'une exécution
  hors clôture. L'énumération par filiation ne suffisait pas lorsqu'un **lanceur**
  (`.venv\Scripts\python.exe`, `npx.cmd`, `uvx`) quittait avant son descendant : le
  petit-fils survivait avec les tubes hérités et un run réussi devenait
  `timed_out` / `output_stream_timeout`. Les deux tests concernés
  (`test_normal_parent_exit_cannot_leave_a_background_child`, systématiquement en
  échec, et `test_asyncio_cancellation_terminates_the_process_tree`, intermittent)
  passent désormais, y compris sur trois exécutions consécutives ;
- la sonde `stdio` refuse une page unique d'outils plus grande que sa capacité au lieu
  de la tronquer silencieusement ;
- un diagnostic HTTP ne réclame plus le coffre lorsque la configuration ne référence
  aucun secret ; il échoue explicitement, avec l'action à effectuer, seulement quand un
  secret est référencé et que le coffre est absent ;
- l'aperçu d'import Hermes ne recopie plus la valeur d'un bloc `auth` ou `timeout` dans
  la liste des éléments non supportés, et un document YAML multiple n'est plus
  diagnostiqué comme « étiquette ou ancre ».

### Sécurité

- aucune valeur de secret ne sort du serveur : ni réponse d'API, ni export, ni
  événement, ni URL, ni frontend ; le déchiffrement n'a lieu que pour un diagnostic
  HTTP ou le claim d'un diagnostic `stdio` approuvé par un runner authentifié, avec
  `Cache-Control: no-store` ;
- tout ce qu'un serveur MCP renvoie (`serverInfo`, capacités, outils, `stderr`,
  messages d'erreur) est expurgé des valeurs injectées avant écriture en base, par le
  runner **et** par l'API, selon une règle unique `acp_contracts.redaction` ;
- une valeur littérale ressemblant à un secret, un paquet non épinglé, une commande
  relative ou une URL refusée par la politique sont rejetés à l'enregistrement ;
- un lancement `stdio` exige une autorisation portant l'empreinte exacte de la
  révision ; une révision modifiée l'invalide, une expiration ou un lease perdu
  produisent un état explicite, jamais un succès supposé ;
- une liste d'outils tronquée n'est jamais présentée comme complète : la sonde stdio
  refuse aussi bien une pagination sans fin qu'une page unique surdimensionnée ;
- un rattachement n'est visible que des utilisateurs ayant accès au projet concerné ;
  le compteur global reste affiché sans nommer les projets.

## [0.4.0] - 2026-09-11

### Ajouté

- ressource mission durable et atomique, avec objectif, résultat attendu, critères,
  autonomie, ressources, budget, durée et première tentative ;
- machine d'états explicite, arrêt et relance idempotents par tentative, fencing
  monotone, commentaires, preuves structurées et acceptation utilisateur séparée ;
- backend worker local opt-in à argv configuré, cwd neuf, environnement minimal,
  capture bornée et hachée, timeout et arrêt de l'arbre de processus ;
- CLI `acp` installable pour l'accès, les diagnostics, projets, conversations,
  missions, suivi/arrêt, approbations, artefacts, workers et ouverture d'un run ;
- écran Missions raccordé aux tentatives, preuves, validations, commentaires et
  liens directs de run.

### Modifié

- le claim worker transporte une identité de tentative, un fencing token et un
  snapshot de mission explicitement autorisé ;
- la CI installe et teste le CLI, et le contrôle de version inclut son paquet et son
  module Python ;
- les versions des composants publiables sont synchronisées sur `0.4.0`.

### Sécurité

- aucun argv de mission n'est interprété et aucun shell n'est utilisé par le backend
  local ; une politique d'autonomie non garantie est refusée avant le spawn ;
- perte de lease, arrêt, timeout, fencing obsolète, évaluateur indisponible ou sortie
  mal formée échouent fermés sans perdre la preuve technique déjà produite ;
- les workers simulés ne peuvent pas voler les missions réelles ;
- le mode réel refuse le provider `mock` avant enrôlement ou démarrage et vérifie
  que chaque verdict provient du provider non simulé configuré ;
- `worker doctor` exige l'API, le gateway, l'identité worker et la readiness
  authentifiée du provider configuré avant de rendre un succès ;
- les credentials worker sont liés à l'origine API normalisée, et les clients qui
  portent les Bearers gateway, événements ou Hermes refusent une origine ambiguë ou
  HTTP hors loopback avant toute requête et ignorent les proxies d'environnement ;
- le CLI refuse HTTP hors loopback et ne réutilise pas une session sur une autre
  origine API ; un verrou interprocessus sérialise ses mutations incertaines, qui
  sont reprises avec la même clé d'idempotence.

## [0.3.0] - 2026-09-11

### Ajouté

- bootstrap unique du propriétaire, mots de passe Argon2id et sessions opaques
  révocables/expirables avec cookie `HttpOnly` et protection CSRF ;
- rôles propriétaire, opérateur/membre et lecteur, avec filtrage des ressources par
  projet et espace accessible ;
- onboarding personnel reprenable et création du premier projet ;
- conversations privées ou rattachées à un projet, tours persistés, recherche,
  renommage, archivage, réactivation et export JSON ;
- diagnostic Hermes typé côté serveur et Runs conversationnels asynchrones avec clé
  d'idempotence persistée et reprise par consultation de statut ;
- interfaces web de bootstrap, connexion, onboarding, Connexions et Conversations.

### Modifié

- le navigateur utilise exclusivement la session API et ne transmet plus de Bearer
  métier ni de secret provider ;
- la reprise d'un tour conversationnel conserve son identifiant de requête et sa clé
  d'idempotence après une admission réseau incertaine ;
- les versions des composants publiables sont synchronisées sur `0.3.0`.

### Sécurité

- les routes métier échouent fermées sans session et les mutations exigent un jeton
  CSRF ainsi qu'un rôle suffisant ;
- seul le liveness du provider-gateway reste public, sa surface `/v1/*` exigeant un
  Bearer inter-services distinct ;
- l'ingestion event-service exige son propre Bearer et le WebSocket anonyme est fermé
  par défaut ;
- l'en-tête `X-User-Id` ne peut plus forger une identité utilisateur.

## [0.2.0] - 2026-09-11

### Ajouté

- shell web professionnel français, responsive et accessible, chargé par défaut ;
- client web relié aux projets et à la création/mise en file des missions ;
- adaptateur Hermes Agent `0.21.1` fondé sur l'API Runs officielle ;
- tests de contrats Hermes, de fermeture en cas d'échec et d'identité worker ;
- audit, décisions d'architecture, rapport d'acceptation et captures navigateur ;
- CI GitHub pour Python, TypeScript, Vitest et le build Vite.

### Modifié

- bureau pixel historique conservé derrière un opt-in explicite ;
- configuration locale sans secret ou provider de secours implicite ;
- versions des composants internes synchronisées sur la version produit.
- Vite `8.3.0` et Vitest `5.0.0`, versions corrigées vérifiées par `npm audit`.

### Sécurité

- une simulation ne peut plus produire un succès ;
- les écritures worker exigent une identité et un lease actif ;
- un succès exige une validation technique et une preuve ;
- un lease expiré ne peut pas être réanimé et interrompt durablement le run ;
- les événements terminaux sont produits par l'API métier ;
- CORS n'accepte plus toutes les origines par défaut.

Les tags `v0.2.0` à `v0.8.0` existent sur `origin` ; le Lot G a été finalisé par la PR #7
(fusion `e71ebf6`) après observation d'une CI verte, et son tag annoté `v0.8.0` a été posé
sur ce commit le 18 septembre 2026. Le tag `v0.9.0` ne sera posé qu'après fusion du Lot H.

[Unreleased]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Paul-Berdier/agent-company-platform/compare/5887603...v0.2.0
