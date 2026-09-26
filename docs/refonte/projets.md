# Projets autonomes sur Hermes (étape P4)

État du **26 septembre 2026**, branche `refonte/hermes-p4`, version 0.11.0 inchangée. **Rien n'est
déployé.** Ce document décrit ce que P4 livre sur Railway, sans le poste Windows : le **cœur serveur**
(première partie : ce que le greffon groupé `acp-poste` fait) et la **page « Projets »** (seconde
partie : greffon d'interface `acp-projets`, § 4 bis). Références : [plan d'autonomie](autonomie.md) (§ 8, P4),
[image](image.md), [catalogue](catalogue.md), décisions **D21 à D40** ([plan](plan.md) § 1, non confirmées).

## 1. En bref

- Le greffon `acp-poste` devient le **chef de projet déterministe**. Un projet = un tableau kanban
  (`acp-<titre>-<4 hex>`) créé par le greffon, une ligne `projets` et des `demandes` dans sa base propre
  (`<HERMES_HOME>/plugin-data/acp-poste/data.db`, WAL, `BEGIN IMMEDIATE`).
- **L'agent ne crée jamais de carte** : `kanban_create` reste refusé par la garde. Le greffon crée les
  cartes lui-même (compétences, exécutant, modèle, effort) par ses **huit outils**, les seuls ajoutés à la
  liste blanche de la garde (26 → **34** noms) : `projet_lancer`, `projet_planifier`, `projet_etat`,
  `poste_etat`, `poste_catalogue`, `question_repondre`, `question_escalader`, `routage_surcharger`.
- **Graphe** : [exploration par le poste, lecture seule] → planification (Hermes) → par étape,
  implémentation (poste) puis **relecture croisée** par l'autre exécutant, ou carte Hermes → **synthèse**
  (Hermes), dont les parents sont TOUTES les cartes du tour. Plafonds : 3 tours, 30 cartes, 2 corrections.
- **Réalité de production en P4 (D25)** : sans inventaire du poste, un projet **sur dépôt** est refusé en
  français ; un projet **sans dépôt** (recherche, conception, rédaction) avance jusqu'au bout sur Railway.
- **Émetteur de notifications** dans la **passerelle** (crochet `on_kanban_dispatch_tick`), une seule
  notification par événement, canal Telegram ou ntfy, **désactivé tant que `ACP_NOTIFICATIONS` n'est pas
  posée**.
- **Page « Projets »** (onglet du tableau de bord, pensée d'abord pour le téléphone) : lancer un projet,
  suivre son avancement carte par carte, répondre aux questions, mettre en pause un projet ou tout
  Hermes. Elle n'a aucune route propre : elle appelle celles du § 4.

## 2. Code (`hermes/plugins/acp-poste/noyau/`)

| Module | Rôle |
|---|---|
| `kanban_adapter.py` | SEUL module du noyau qui importe Hermes, chaque nom depuis son module de définition (`hermes plugins compat` vert) |
| `base.py` | base du greffon : schéma v1 (5 tables du plan + 8 techniques), réglages, journal, transactions |
| `routage.py` | relevés du poste (contrat partagé `acp_poste_contrat.inventaire`, D21), table de routage, surcharges, résolution déterministe |
| `cartes.py`, `projets.py`, `graphe.py` | réservation → création kanban sous UNE transaction → rattachement ; lancement, état, pause ; tours, corrections, triage |
| `questions.py`, `presence.py`, `etrangeres.py` | questions du poste (carte « répondre », D28) ; présence ; cartes `poste-*` non émises (bloquées, D37) |
| `notifications.py`, `emetteur.py` | file et canaux ; passe de maintenance et fil d'envoi (passerelle seulement) |
| `outils.py`, `invite.py` | les huit outils ; la section de prompt « acp-projets » (parade à `KANBAN_GUIDANCE`) |

Le paquet est chargé par Hermes (`from . import noyau`) et, pour les routes, par son chemin sous le nom
`acp_poste_noyau` (D22) : deux copies, aucun état en mémoire, tout en base.

## 3. Outils de l'agent

Hermes **diffère** les outils de greffon derrière `tool_search` / `tool_describe` / `tool_call`
(tools/tool_search.py:150-162) : ils figurent dans le catalogue différé de la session, et le modèle les
appelle par le pont `tool_call` (la garde juge l'outil sous-jacent). La section de prompt le dit.

| Outil | Discussion | Worker d'une carte ACP | Effet |
|---|---|---|---|
| `projet_lancer` | oui | non | lance un projet (idempotent par session, titre, objectif, dépôt) |
| `projet_planifier` | non | carte de planification ou de synthèse | crée le tour suivant (tableau et carte lus dans l'environnement du worker) |
| `projet_etat` | oui | son projet seulement | état dérivé, cartes, questions, plafonds |
| `poste_etat`, `poste_catalogue` | oui | oui | présence ; catalogue relevé (« Inconnu » sans relevé) |
| `question_repondre`, `question_escalader` | non | carte « répondre » de la question | réponse de Hermes (commentaire + reprise) ou escalade (notification) |
| `routage_surcharger` | oui | non | surcharge projet ou carte, jamais un interdit |

**`memory` refusé dans un worker kanban** (garde, depuis P4) : mesuré au contrat, une écriture en
mémoire d'un worker `chat -q` ouvrait l'invite d'approbation en ligne du CLI (`memory.write_approval`
épinglé), qui attendait **300 s** sans personne avant de mettre l'écriture en attente : la carte restait
bloquée cinq minutes. La garde la refuse désormais tout de suite dans un worker (message français) ; en
discussion, `memory` reste admis et soumis à validation.

Visibilité par `check_fn` non mis en cache (D23), revérifiée par chaque gestionnaire. Coupés sur
`api_server` et `cron` par `known_plugin_toolsets` (D24). Chaque gestionnaire rend un JSON
`{"ok": true, …}` ou `{"ok": false, "code", "message": "Refusé par ACP : …"}` et ne lève jamais.

## 4. Routes (`/api/plugins/acp-poste/`, session du tableau de bord)

Toute route d'écriture exige `Content-Type: application/json` (415) et refuse un `Origin` différent de
`HERMES_DASHBOARD_PUBLIC_URL` (403). Erreurs : `{"detail": {"code", "message"}}` en français ; 400
(validation), 404 (inconnu), 409 (état : pause, plafonds, déjà en pause…).

| Méthode et chemin | Corps | Réponse |
|---|---|---|
| `GET /v1/projets` | — | `projets[]` (id, titre, tableau, état et état dérivé, compteurs `faites/total/en_cours/en_attente_du_poste/bloquees/triage`, dernière note, questions ouvertes), `poste`, `pause_generale`, `notifications {canal, configure, connu, message}`, `questions_ouvertes` |
| `POST /v1/projets` | `titre`, `objectif`, `profil?`, `depot?`, `reponses?`, `exploration? {voie, modele, effort}` ; en-tête `Idempotency-Key` facultatif | 201 `{projet, deja_lance}` (200 au rejeu d'une clé) |
| `GET /v1/projets/{id ou tableau}` | — | `projet` : état, plafonds, restants, tours et décisions, cartes (rôle, voie, statut, modèle demandé, effort, palier, « Modèle servi : Non observé »), questions ouvertes, journal |
| `POST /v1/projets/{id}/pause`, `/reprise` | `{}` | `{projet, cartes_planifiees}` / `{projet, cartes_reveillees}` |
| `GET /v1/questions` | — | `questions[]` ouvertes et escaladées ; cartes en `triage` et `bloquees` (`abandonnee` si le disjoncteur a abandonné) |
| `POST /v1/questions/{q}/reponse` | `reponse` | `{question, etat, carte_debloquee}` |
| `POST /v1/triage/{tableau}/{carte}/reprendre` | `consigne?` | `{carte, reprise}` |
| `POST /v1/pause` | `{"generale": true, "raison"?}` ou `{"generale": false}` | `{pause_generale}` (arrêt d'urgence de Hermes, D31) |
| `GET /v1/poste` | — | `{poste, catalogue}` |
| `POST /v1/notifications/test` | `{}` | 202 (mise en file, envoyée par la passerelle) ; 409 « Notifications non configurées. » |

`GET /v1/meta` ajoute le bloc `projets` : base, schéma, projets actifs, relevé factice présent, pause
générale, émetteur (dernière passe, processus, cartes du poste en attente par tableau, canal, file).

## 4 bis. Page « Projets » (greffon d'interface `acp-projets`)

Greffon de tableau de bord **sans code serveur** (manifeste, bundle IIFE, feuille de style), comme
`acp-interface` et `acp-catalogue` ([interface.md](interface.md) § 10) : sources
`apps/interface/src/projets/`, bundle committé `hermes/plugins/acp-projets/dashboard/dist/`. Onglet
« Projets » (`/projets`), avant « Catalogue » dans le groupe des greffons de Hermes ; raccourci sur
l'Accueil.

| Vue | Adresse | Routes appelées | Contenu et gestes |
|---|---|---|---|
| Liste | `/projets` | `GET /v1/projets` | une carte par projet : état (dérivé : exploration, planification, en cours, en attente du poste, synthèse, plafond atteint, en pause, terminé), « Cartes faites : n sur m », poste, questions en attente, dernière note ; carte « Poste Windows » ; carte « Notifications » (canal, état, notification de test) ; carte « Pause générale » |
| Nouveau projet | `?vue=nouveau` | `GET /v1/catalogue` (types de projet), `GET /v1/poste` (dépôts et relevés), `POST /v1/projets` | titre, objectif, type de projet, qui répond (Hermes d'abord ou moi), dépôt, exploration (exécutant, modèle, effort) |
| Détail | `?projet=<id>` (lien des notifications) | `GET /v1/projets/{id}`, `POST /v1/projets/{id}/pause`, `…/reprise` | état, objectif, tour et cartes au regard des plafonds, dépôt, poste ; cartes groupées par rôle (statut, exécutant, modèle demandé, effort, palier, **« Modèle servi : Non observé »** avant P6, mention, résumé replié) ; tours et décisions ; questions en attente ; journal ; **Mettre en pause** / **Reprendre** |
| Questions | `?vue=questions` | `GET /v1/questions`, `POST /v1/questions/{q}/reponse`, `POST /v1/triage/{tableau}/{carte}/reprendre` | questions ouvertes ou escaladées avec **Répondre** ; cartes en triage avec **Reprendre** et une consigne facultative ; cartes bloquées ou abandonnées **en lecture seule** (« Relancer » : P7) |

Règles, toutes testées (Vitest, image, navigateur) :

- **Aucun bouton sans route réelle et testée.** La pause générale demande une confirmation ; la
  notification de test n'est active que si un canal est configuré, sinon le bouton est désactivé et la
  page dit « Notifications non configurées (variables ACP_NOTIFICATIONS… du service Hermes sur
  Railway). ».
- **Aucune donnée inventée** : « Inconnu » pour une valeur absente, « Non configuré » pour un poste
  jamais vu, « Non observé » (servi par le greffon) pour le modèle réellement servi ; un code inconnu du
  greffon est montré tel quel, comme donnée ; une actualisation ratée garde la dernière valeur lue et le
  dit.
- **Sans inventaire du poste** (D25), le champ Dépôt est désactivé et la page dit « Aucun dépôt connu : le
  poste n'a encore publié aucun inventaire (étape P5). » ; seul « Sans dépôt » est possible. Avec un
  relevé, l'exploration se choisit **seulement** parmi les exécutants, modèles et efforts relevés, efforts
  interdits exclus (D39) ; un relevé factice est signalé comme tel.
- **Refus de l'API affichés tels quels** (message français du greffon, code HTTP) ; le formulaire reste
  rempli. Une clé d'idempotence par envoi : un double appui ne lance qu'un projet.
- **Sondage** toutes les 15 s tant que la page est visible, aucune lecture quand elle est cachée (D35) ;
  relecture immédiate après chaque geste.
- Tout texte vient du catalogue français `apps/interface/src/chaines.ts` ; ni `fetch` direct, ni
  `innerHTML`, ni stockage local.

## 5. Notifications

Variables Railway (facultatives ; validées au démarrage, refus en français) : `ACP_NOTIFICATIONS`
(`aucune` par défaut, `telegram`, `ntfy`) ; pour Telegram `ACP_TELEGRAM_JETON` et
`ACP_TELEGRAM_DISCUSSION` ; pour ntfy `ACP_NTFY_SUJET` (16 à 64 caractères) et `ACP_NTFY_JETON` (exigé,
D33), `ACP_NTFY_SERVEUR` facultatif (`https://ntfy.sh`). `register()` les lit puis les **retire de
`os.environ` dans chaque processus** ; seule la passerelle garde le canal en mémoire. Contenu minimal (D32) :
genre, titre du projet, titre de carte tronqué, lien vers `…/projets?projet=<id>` ; jamais la consigne ni le
texte d'une question.

Règles : `blocked` (hors `dependency`) → « bloquée » ; `block_loop_detected` → triage ; `gave_up` →
abandon ; synthèse du tour courant finie sans carte ouverte → « terminé » (une fois) ; question escaladée ;
poste hors ligne (une fois par passage) ; plafond atteint ; crochets shell apparus (pause générale, D34).

## 6. Managed scope et démarrage

Épingles ajoutées (57 clés) : `kanban.dispatch_in_gateway: true`, `max_in_progress: 4`,
`max_in_progress_per_profile: 2`, `review_dispatch: false`, `failure_limit: 3`, `acp_poste` dans
`platform_toolsets.cli`, `known_plugin_toolsets.{api_server,cron}: [acp_poste]`. Variable interdite :
`HERMES_KANBAN_DISPATCH_IN_GATEWAY`. Démarrage (gardes, `05-acp`) et relance (garde des scripts `run`)
**refusés** sur une clé `hooks` non vide ou un `shell-hooks-allowlist.json` à la racine du volume ou d'un
profil. Les réglages du répartiteur sont lus au démarrage de la passerelle : un changement exige une relance.

## 7. Limites dites

- La qualité d'un vrai plan n'est pas prouvée : les tests jouent un modèle factice.
- Le scénario Railway (téléphone, notification, second appareil) se prouve après le premier déploiement,
  avec « Envoyer une notification de test » ; la livraison réelle par Telegram ou ntfy n'est testée que
  contre un faux serveur.
- Poste réel (routes machine, jeton, réclamation, exécution) : P5-P6. Un poste SIMULÉ joue son rôle dans les
  tests par l'API kanban et les fonctions du greffon.
- Pendant la pause générale, aucune passe : aucune NOUVELLE notification (D31).
- Les variables de notification restent lisibles par l'uid hermes dans `/run/s6/container_environment` et
  dans l'environnement initial des processus de la passerelle et du tableau de bord (même limite que le
  secret OIDC) ; l'agent n'a aucun outil pour les lire, et les workers ne les reçoivent plus.
- Une carte `poste-*` étrangère encore `todo` n'est bloquée qu'une fois `ready` (`block_task` n'agit que
  depuis `ready`/`running`) ; elle n'est pas réclamable entre-temps.
- Les variables de notification ne sont pas déclarées dans `.railway/railway.ts` (canal non choisi) : leur
  pose passe d'abord par une PR, sinon le plan suivant les supprimerait ([railway.md](railway.md) § 9).
- **Course du contrôle d'écriture de Hermes 0.21.5** (`hermes_state_repair.py:537-573`, appelé à chaque
  connexion à un tableau) : si un autre processus referme la dernière connexion au moment du contrôle,
  le fichier `-wal` disparaît entre `is_file()` et `os.access()` et Hermes conclut à tort « read-only for
  this user ». Constatée une fois au contrat P4 (seconde partie, poste simulé, `test_pause_d_un_projet`).
  Le greffon rejoue sa connexion (3 tentatives) sur ce seul faux négatif, quand le fichier nommé n'existe
  plus (`kanban_adapter.connexion`, `test_connexion_rejoue_la_seule_course_du_controle_d_ecriture`) ; les
  processus de Hermes eux-mêmes (répartiteur, workers) n'en sont pas protégés : une carte qui la
  rencontrerait échouerait et serait relancée (`failure_limit: 3`), ce qui n'a pas été observé.
- Page « Projets » : la file Questions complète (`open_requests`, réglage par projet) et le temps réel
  (SSE) sont en P7 ; « Relancer » une carte bloquée ou abandonnée aussi (lecture seule en P4). Le rendu
  n'est prouvé que dans Chromium (390×844 émulé, pas un vrai téléphone ni Safari iOS).

## 8. Écarts au cahier de conception, justifiés

- **`memory` refusé dans un worker kanban** (décision **D40**, ajoutée, à confirmer) : le cahier prévoyait
  de prouver une écriture « mise en attente » (`test_memoire_du_worker_en_attente`). Constaté au premier
  passage du contrat (première tentative de P4) : la carte restait bloquée 300 s sur l'invite
  d'approbation en ligne avant la mise en attente, soit le délai `approvals.timeout` par défaut de Hermes
  (hermes_cli/config_defaults.py:1657, tools/approval_context.py:239-256). Non rejoué depuis : la garde
  refuse l'écriture tout de suite (`test_memoire_refusee_dans_un_worker_kanban`, et au contrat
  `test_kanban_create_et_memoire_refuses_dans_un_worker`). Le plan
  d'autonomie (§ 7) désignait cette coupure comme le repli, à décider par le propriétaire. `skill_manage`
  reste admis : une écriture de skill est toujours mise en attente sans invite
  (tools/write_approval.py:170-213).
- **Outils du greffon différés par Hermes** derrière `tool_search` (non prévu par le cahier) : le worker ne
  les voit pas dans sa liste d'outils mais dans le catalogue différé de la session, et les appelle par
  `tool_call` ; la garde juge l'outil sous-jacent. Prouvé au contrat (liste imprimée ci-dessous).
- **Module `modeles.py`** du cahier (dataclasses) non créé : les lignes de la base (`sqlite3.Row`) et le
  contrat partagé `acp_poste_contrat.inventaire` suffisent ; aucun comportement n'en dépend.
- **Variables de notification hors IaC** (§ 7) : le cahier ne traitait pas la suppression par le plan
  Railway d'une variable non déclarée.
- **Page Projets, seconde partie** :
  - icône `FolderOpen` au lieu de `FolderKanban` : Hermes 0.21.5 ne connaît pas cette dernière et
    afficherait l'icône générique (table `ICON_MAP`, `web/src/App.tsx:228-255`) ;
  - position `before:catalogue` au lieu de `after:acp` : l'onglet de l'Accueil remplace « / » et n'a pas
    d'entrée de menu (`App.tsx:265`), `after:acp` rejetterait « Projets » en fin de groupe ; la découverte
    triée par nom (`hermes_cli/web_server_dashboard.py:558`) fait voir « Catalogue » avant (prouvé :
    `test_interface.py`, et au navigateur l'ordre Kanban, Projets, Catalogue) ;
  - fichiers regroupés : cartes « Poste » et « Notifications » dans `ListeProjets.tsx` et
    `Notifications.tsx`, bandeau et commande de pause générale dans `BandeauPause.tsx`, briques
    communes dans `briques.tsx`, libellés dans `libelles.ts`, sondage dans `sondage.ts` ; le catalogue
    des chaînes reste unique (`src/chaines.ts`, bloc `T.projets`) au lieu d'un fichier par greffon ;
  - au navigateur, « Reprendre » une carte en triage et « Envoyer une notification de test » ne sont pas
    cliqués (aucune carte en triage dans le parcours ; canal non configuré dans la pile d'identité) :
    leurs requêtes sont prouvées par Vitest, leurs routes par les tests d'image
    (`test_reprise_d_un_triage_par_la_route`, `test_notification_de_test`) et, pour la notification de
    test, par le contrat (`test_notification_de_test_envoyee_par_la_passerelle` : reçue une seule fois
    par le faux ntfy).

## 9. Preuves locales (26/09/2026, Windows 10, Docker 29.5.3, Python 3.12.10, pytest 9.1.1)

Images construites depuis l'arbre de travail : `acp-hermes:p4f` et `acp-hermes-tests:p4f` (arbre de
`ab7c594`, plus les tests et la documentation alors non commités) ; `acp-identite:p4` (dossier
`identite/` inchangé depuis P3).

| Suite | Commande | Résultat |
|---|---|---|
| Dépôt | `python -m pytest -q` (venv Python 3.12.10 du verrou) | **386 réussis**, 0 ignoré (dont `test_les_choix_de_p4_se_disent_non_confirmes`) |
| Contrôles | `check_version.py`, `check_engine_frozen.py`, `verifier_catalogue.py`, `balayer_secrets.py` | 0.11.0 partout ; moteur gelé ; catalogue conforme (**21** skills livrées : 14 vendorisées, 7 maison) ; aucun motif de secret |
| Compatibilité | `hermes plugins compat /opt/hermes/plugins/acp-poste` (et le témoin) | code **0** (« No enabled plugin imports paths scheduled for removal ») ; témoin code **1** |
| Dans l'image | `docker run … acp-hermes-tests:p4f -m pytest /opt/acp-tests/image` | **491 réussis**, 0 échec (4 min 41 s) |
| Contrat complet | `python -m pytest -s -v -rA hermes/tests/contrat` (images `p4f`) | **134 réussis, 1 échec** (28 min 41 s) : `test_pid1_est_s6_et_les_gardes_ont_tourne` attendait encore « 50 clés » ; corrigé (`c14c263`), `test_contrat_image.py` rejoué : **37 réussis** (6 min 30 s). Par fichier : catalogue 10, image 37, identité 41, interface 4, **projets 17**, IaC 3, sans exécution 23 |
| Contrat P4 seul | `… hermes/tests/contrat/test_projets_contrat.py` | **17 réussis** (10 min 30 s), sur la version committée (scénarios ajoutés) ; premier passage, avant eux : 17 réussis (19 min 38 s) |
| Navigateur | `ACP_E2E_OBLIGATOIRE=1 … python -m pytest -s -v -rA hermes/tests/e2e` (Playwright 1.62.0, Chromium 1234 déjà présent, rien téléchargé) | **5 réussis** (2 min 10 s) après `a150f72` ; aux deux formats, aucune violation axe ; Catalogue au téléphone : 13 278 px capturés en entier |
| Témoins négatifs | `IMAGE=acp-hermes-tests:p4f bash scripts/temoins_negatifs_p4.sh` | **12 sur 12** : chaque protection retirée fait échouer ses tests (tableau ci-dessous) |

Relevés du contrat (images `p4f`) :

- **Outils offerts au worker de planification** (liste imprimée) : `clarify`, `kanban_attach`,
  `kanban_attach_url`, `kanban_attachments`, `kanban_block`, `kanban_comment`, `kanban_complete`,
  `kanban_create`, `kanban_heartbeat`, `kanban_link`, `kanban_request_changes`, `kanban_request_review`,
  `kanban_show`, `memory`, `skill_view`, `skills_list`, `tool_call`, `tool_describe`, `tool_search`,
  `vision_analyze`, `web_extract`, `web_search` ; catalogue différé : `projet_planifier`, `projet_etat`,
  `poste_catalogue`, `poste_etat`, `question_repondre`, `question_escalader` ; **ni** `projet_lancer`, **ni**
  `routage_surcharger`, **ni** aucun outil d'exécution. `kanban_create` et `memory` sont offerts par
  Hermes et refusés par la garde à l'appel (résultats d'outil « Refusé par ACP : … » relevés).
- En discussion, le catalogue différé porte `projet_lancer`, `projet_etat`, `poste_etat`,
  `poste_catalogue`, `routage_surcharger`, jamais `projet_planifier`.
- **Délai** fin de l'exploration (poste simulé) → planification réclamée par le répartiteur : **2,9 s**,
  **3,7 s** et **2,3 s** (trois passages mesurés, répartiteur à 5 s) ; première requête du worker au
  modèle 18,3 à 19,3 s après. Ces valeurs comparaient `started_at` de Hermes (secondes entières) à
  l'heure de l'hôte prise après le retour de `docker exec` ; la CI de `a614278` en a tiré **-0,6 s**
  (artefact de mesure : la planification était `todo` jusqu'à la fin de l'exploration et son
  `kanban_show` portait le marqueur, deux assertions du test). Depuis `1a57bf2`, fin et lancement sont
  lus sur l'horloge des conteneurs (`completed_at`, `started_at`) avec l'assertion
  `0 <= délai <= 12` : **4 s** en local (images `p4g`), première requête au modèle 20,0 s après la fin.
- **Faux ntfy** (une ligne par notification, jeton présent, jamais journalisé en clair) : « ACP — Projet
  « Veille contrat » terminé : 4 cartes faites. » (une seule, `Priority: 3`, `Click` vers
  `…/projets?projet=<id>`) ; « … « Graphe complet » : plafond de tours atteint, votre décision est
  attendue. » (une seule) ; « … « Etrangere » : la carte « Carte à la main » est bloquée. » ; « ACP — Poste
  hors ligne depuis HH:MM (Europe/Paris), 1 carte en attente. » deux fois (deux passages, `Priority: 4`).
  Aucune notification pour les fins intermédiaires.
- Au contrat complet, une notification « abandonnée après plusieurs échecs » est aussi partie : la
  planification du projet témoin « Etrangere » n'avait pas de scénario, son worker répondait sans
  `kanban_complete` et Hermes l'a abandonnée après trois échecs (règle `gave_up` prouvée au passage). Le
  test lui donne désormais un scénario, comme à la synthèse du projet « Memoire » ; rejoué ensuite :
  aucune notification d'abandon.
- **Mémoire** (`docker stats`, indicative, jamais un seuil) : 517 à 618 Mio sans worker ; pic de
  **849,7 Mio**, **805,1 Mio** et **840,4 Mio** (trois passages) avec deux workers kanban et le modèle
  factice ; aucun `ACP_*` dans l'environnement initial des workers (17, 18 et 13 lectures). `pgrep` compte
  des processus : il en a vu jusqu'à trois pour deux workers.

Témoins négatifs (`scripts/temoins_negatifs_p4.sh`, conteneur jetable de `acp-hermes-tests:p4f`) :

| Protection retirée | Tests en échec |
|---|---|
| un nom (`projet_etat`) de la liste blanche | `test_garde_liste_blanche`, `test_garde_admet_exactement_les_outils_du_greffon` |
| visibilité par contexte (`check_fn`) | `test_visibilite_discussion_worker` |
| `known_plugin_toolsets` de la managed scope | `test_outils_acp_absents_d_api_server_et_cron` (refus des épingles obligatoires ; le test porte aussi son propre témoin : sans ces épingles, les outils apparaissent sur `api_server` et `cron`) |
| balayage des cartes `poste-*` étrangères | `test_carte_poste_du_proprietaire_bloquee_avec_raison` |
| transaction kanban externe d'un tour | `test_atomique_rien_si_une_creation_leve` |
| unicité des notifications par clé | `test_envoi_unique_par_cle_meme_rejoue` |
| plafond des tours ; plafond des cartes | `test_plafond_tours_carte_de_triage_unique` ; `test_plafond_cartes_sans_creation_partielle` |
| refus des crochets shell au démarrage | `test_hooks_non_vide_refuse[racine]`, `[profil]` |
| retrait des variables de notification de `os.environ` | `test_secrets_retires_de_os_environ` |
| liaisons des corrections vers la synthèse | `test_ordre_correction_liaison_puis_fin` |
| refus de `memory` dans un worker (D40) | `test_memoire_refusee_dans_un_worker_kanban` |

### Seconde partie : page « Projets » (26/09/2026, Windows 10, Docker 29.5.3, Python 3.12.10, pytest 9.1.1, Node 24.19.0, Playwright 1.62.0 et son Chromium déjà présent)

Images `acp-hermes:p4k` et `acp-hermes-tests:p4k` (arbre final de la seconde partie, documentation
exceptée), identité `acp-identite:p4` ; le contrat de l'interface et du catalogue a tourné sur `p4i`, le même
arbre sans la correction de la course du § 7, qu'il ne touche pas.

| Suite | Commande | Résultat |
|---|---|---|
| Interface | `npm test --prefix apps/interface` puis `npm run check` | TypeScript sans erreur ; Vitest **80 réussis** (13 fichiers, dont 25 pour la page) ; 6 fichiers de greffons à jour |
| Dépôt | `python -m pytest -q` (venv Python 3.12.10 du verrou) | **386 réussis** (33,6 s) |
| Contrôles | `check_version.py`, `check_engine_frozen.py`, `verifier_catalogue.py`, `balayer_secrets.py`, `git diff --check` | 0.11.0 partout (manifeste d'`acp-projets` compris) ; moteur gelé ; 21 skills ; aucun motif de secret ; propre |
| Dans l'image | `docker run … acp-hermes-tests:p4k -m pytest /opt/acp-tests/image` | **493 réussis** (4 min 31 s) : 491 de la première partie, plus la reprise d'un triage par la route et la course du contrôle d'écriture |
| Contrat P4 | `… pytest -s -v -rA hermes/tests/contrat/test_projets_contrat.py` (images `p4k`) | **18 réussis** (10 min 21 s), dont la notification de test reçue une seule fois par le faux ntfy |
| Contrat interface et catalogue | `… test_interface_contrat.py test_catalogue_contrat.py` (images `p4i`) | **14 réussis** (2 min 14 s) : `acp-projets` servi, octet pour octet celui du dépôt ; version dans la méta |
| Navigateur | `ACP_E2E_OBLIGATOIRE=1 … python -m pytest -s -v -rA hermes/tests/e2e` (images `p4k`) | **6 réussis** (4 min 21 s) : les 5 de P2 et P3, plus `test_projets.py` |

Relevés du navigateur (`test_projets.py`) :

- vues vérifiées : 9 au téléphone, 10 au bureau ; **aucune violation axe** (ni grave, ni modérée) ; aucun
  texte hors du catalogue français ; au téléphone, 60 cibles mesurées, toutes à 44 px au moins ;
- requêtes : 193 au téléphone et 293 au bureau, **aucune** hors de l'origine du tableau de bord ;
- groupe des greffons de Hermes : `/kanban`, `/projets`, `/catalogue` ;
- sans inventaire : champ Dépôt désactivé et « Aucun dépôt connu… » ; détail : « Modèle servi : Non
  observé », « Poste : Non configuré » ; « Mettre en pause » puis « Reprendre » : `en_pause` puis `actif`
  relus par l'API ;
- avec le relevé factice : « Relevé factice… » affiché, efforts proposés `low` et `medium` (`max`,
  relevé, exclu : D39) ; question du poste simulé escaladée (« Moi »), réponse donnée depuis la page :
  question fermée et carte d'exploration `ready`, relues par l'API, aux deux formats ;
- avancement : les quatre projets (deux par format) arrivent à « Terminé » **66,1 s** après la fin des
  explorations par le poste simulé (modèle factice, répartiteur à 5 s) ; détail d'un projet sur dépôt :
  exploration, planification, étape Hermes et synthèse « Faite », « 4 sur 4 » ;
- pause générale au bureau : rien avant la confirmation, puis bandeau et « ACP : pause du propriétaire »,
  puis reprise ; état relu par l'API ;
- 21 captures pleine page (aucune tronquée ; jusqu'à 3 230 px de haut au téléphone).

## 10. Intégration continue

Branche poussée le 26/09/2026, sommet `ff5d61f` :

- `ci.yml` [36226236043](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36226236043)
  **succès** : poste Windows **386 réussis** ; poste Linux **377 réussis, 9 ignorés** (les 9 tests propres
  à Windows) ; interface **55** ; moteur **74** ; catalogue et balayage des secrets verts.
- `image.yml` [36226236009](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36226236009)
  **échec** : `hermes plugins compat` vert (témoin code 1) ; sonde réelle de context7 connectée
  (1 611 ms) ; **491** réussis dans l'image ; **135** au contrat (24 min 08 s), dont les 17 de P4
  (réclamation de la planification 3,7 s après la fin de l'exploration) ; navigateur **1 échec sur 5** :
  la capture du Catalogue au téléphone s'arrêtait à 12 000 px alors que la page, avec les cinq skills de
  P4, en compte environ 13 300 (`telephone-03-catalogue.png`, 1 808 px restants). Corrigé par `a150f72`
  (plafond de capture à 16 000 px) : témoin local à 12 000 px en échec (1 278 px restants), puis
  **5 réussis** en local à 16 000 px (2 min 10 s ; aucune violation axe).
- Relance sur `a614278`, **verte** : `ci.yml`
  [36228251683](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36228251683) (poste
  Windows 386, Linux 377 et 9 ignorés, interface 55, moteur 74) ; `image.yml`
  [36228251644](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36228251644) (491 dans
  l'image, **135** au contrat dont les 17 de P4, **5** au navigateur, compat vert, context7 connecté).
  Détail et relevés : [`reprise-poste.md`](../reprise-poste.md) § 6 quater.

- Seconde partie (page « Projets ») : CI relevée après le push de son commit de documentation, consignée
  par le commit suivant.

## 11. Non prouvé

- Le rendu de la page « Projets » sur un vrai téléphone : Chromium à 390×844 (émulation), ni Safari iOS
  ni un vrai réseau mobile.

- La qualité d'un vrai plan : les tests ne jouent qu'un modèle factice.
- Le scénario Railway (téléphone, notification, second appareil), la livraison réelle par Telegram ou
  ntfy (faux serveur seulement), le poste réel (P5-P6) et la tenue dans 2 Go avec de vrais modèles.
- La course de découverte des greffons au démarrage d'un worker (`hermes_cli/cli_init_mixin.py:214-228`)
  n'a jamais été observée ; si elle survenait, la carte échouerait et serait relancée (`failure_limit: 3`),
  visiblement.
