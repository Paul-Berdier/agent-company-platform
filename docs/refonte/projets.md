# Projets autonomes sur Hermes (étape P4)

État du **26 septembre 2026**, branche `refonte/hermes-p4`, version 0.11.0 inchangée. **Rien n'est
déployé.** Ce document décrit ce que P4 livre sur Railway, sans le poste Windows : le **cœur serveur**
(première partie : ce que le greffon groupé `acp-poste` fait) et la **page « Projets »** (seconde
partie : greffon d'interface `acp-projets`, § 4 bis). Références : [plan d'autonomie](autonomie.md) (§ 8, P4),
[image](image.md), [catalogue](catalogue.md), décisions **D21 à D47** ([plan](plan.md) § 1, non confirmées).
Corrections de la relecture indépendante de P4 : § 12.

## 1. En bref

- Le greffon `acp-poste` devient le **chef de projet déterministe**. Un projet = un tableau kanban
  (`acp-<titre>-<4 hex>`) créé par le greffon, une ligne `projets` et des `demandes` dans sa base propre
  (`<HERMES_HOME>/plugin-data/acp-poste/data.db`, WAL, `BEGIN IMMEDIATE`).
- **L'agent ne crée jamais de carte** : `kanban_create` reste refusé par la garde. Le greffon crée les
  cartes lui-même (compétences, exécutant, modèle, effort) par ses **huit outils**, les seuls ajoutés à la
  liste blanche de la garde (26 → 34 noms, puis **33** : `kanban_link` retiré à la relecture, D44) :
  `projet_lancer`, `projet_planifier`, `projet_etat`, `poste_etat`, `poste_catalogue`, `question_repondre`,
  `question_escalader`, `routage_surcharger`. Dans un worker, un outil `kanban_*` ne touche que le tableau de
  son projet, et `kanban_comment` que sa propre carte (D44).
- **Graphe** : [exploration par le poste, lecture seule] → planification (Hermes) → par étape,
  implémentation (poste) puis **relecture croisée** par l'autre exécutant, ou carte Hermes → **synthèse**
  (Hermes), dont les parents sont TOUTES les cartes du tour. Plafonds : 3 tours, 30 cartes, 2 corrections.
  Au plafond, ou quand la planification finit sans plan, une **carte de décision** vous est adressée :
  « Prolonger » / « Relancer la planification » (Hermes planifie la suite depuis elle) ou « Conclure » (D41).
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
| `projet_planifier` | non | carte de planification ou de synthèse ; carte de décision prolongée ou relancée par le propriétaire (D41) | crée le tour suivant (tableau et carte lus dans l'environnement du worker) |
| `projet_etat` | oui | son projet seulement | état dérivé, cartes, questions, plafonds |
| `poste_etat`, `poste_catalogue` | oui | oui | présence ; catalogue relevé (« Inconnu » sans relevé) |
| `question_repondre`, `question_escalader` | non | carte « répondre » de la question | réponse de Hermes (commentaire + reprise) ou escalade (notification) |
| `routage_surcharger` | oui | non | surcharge d'un projet (ses prochaines cartes), jamais un interdit ; portée « carte » refusée jusqu'à P6 (D43) |

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
| `GET /v1/projets` | — | `projets[]` (id, titre, tableau, état et état dérivé — dont `a_decider` —, compteurs `faites/total/en_cours/en_attente_du_poste/bloquees/triage`, dernière note et `derniere_note_tronquee`, questions ouvertes), `poste`, `pause_generale`, `notifications {canal, configure, connu, message}` (« état du canal inconnu » tant que la passerelle ne l'a pas publié), `questions_ouvertes` |
| `POST /v1/projets` | `titre`, `objectif`, `profil?`, `depot?`, `reponses?`, `exploration? {voie, modele, effort}` ; en-tête `Idempotency-Key` facultatif | 201 `{projet, deja_lance}` (200 au rejeu d'une clé) |
| `GET /v1/projets/{id ou tableau}` | — | `projet` : état, plafonds, restants, `resultat` (synthèse faite du dernier tour, EN ENTIER), tours et décisions, cartes (rôle, voie, statut, modèle demandé, effort, palier, « Modèle servi : Non observé », résumé de 500 caractères avec `resume_longueur` et `resume_tronque`), questions ouvertes, journal |
| `GET /v1/projets/{id}/cartes/{carte}` | — | `carte` : résumé ENTIER (masqué, borné à 100 000 caractères, `tronque` le dit) ; 404 hors du projet |
| `POST /v1/projets/{id}/pause`, `/reprise` | `{}` | `{projet, cartes_planifiees}` / `{projet, cartes_reveillees}` ; reprise refusée (409) au plafond de projets actifs |
| `GET /v1/questions` | — | `questions[]` ouvertes et escaladées (titre de la carte, contexte) ; cartes en `triage` (`genre`, `actions` offertes) et `bloquees` (`abandonnee` si le disjoncteur a abandonné), avec leur `raison` connue |
| `POST /v1/questions/{q}/reponse` | `reponse` | `{question, etat, carte_debloquee, reprise_differee}` (projet en pause : la carte reprendra à la reprise, D47) |
| `POST /v1/triage/{tableau}/{carte}/reprendre` | `consigne?` | `{carte, reprise, action, plafond}` : « prolongation » (plafond relevé), « relance_planification » ou « reprise » ; 409 sur un projet en pause ou au plafond de corrections (P6) |
| `POST /v1/triage/{tableau}/{carte}/conclure` | `{}` | `{carte, conclu, projet}` : carte de décision archivée, projet « termine » (ou « abandonne » sans aucun tour) ; 409 tant qu'une autre carte est ouverte (D41) |
| `POST /v1/pause` | `{"generale": true, "raison"?}` ou `{"generale": false}` | `{pause_generale}` (arrêt d'urgence de Hermes, D31) ; la reprise est refusée (409) tant que des crochets shell sont déclarés (D45) |
| `GET /v1/poste` | — | `{poste, catalogue}` |
| `POST /v1/notifications/test` | `{}` | 202 (mise en file, envoyée par la passerelle) ; 409 « Notifications non configurées. », ou « état du canal inconnu » tant que la passerelle ne l'a pas publié |

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
| Nouveau projet | `?vue=nouveau` | `GET /v1/catalogue` (types de projet), `GET /v1/poste` (dépôts et relevés), `POST /v1/projets` | titre, objectif, type de projet, dépôt, qui répond (Hermes d'abord ou moi : avec un dépôt seulement, D42), exploration (exécutant, modèle, effort) |
| Détail | `?projet=<id>` (lien des notifications) | `GET /v1/projets/{id}`, `GET /v1/projets/{id}/cartes/{carte}`, `POST /v1/projets/{id}/pause`, `…/reprise` | état, objectif, **résultat du projet** (synthèse du dernier tour, en entier), tour et cartes au regard des plafonds, dépôt, poste ; cartes groupées par rôle (statut, exécutant, modèle demandé, effort, palier « Standard », **« Modèle servi : Non observé »** avant P6, mention, résumé replié : un extrait le dit et **Lire le résumé en entier**) ; tours et décisions ; questions en attente ; journal en français (détail technique replié) ; **Mettre en pause** / **Reprendre** |
| Questions | `?vue=questions` | `GET /v1/questions`, `POST /v1/questions/{q}/reponse`, `POST /v1/triage/{tableau}/{carte}/reprendre`, `…/conclure` | questions ouvertes ou escaladées (titre de la carte, contexte) avec **Répondre** ; cartes en triage avec les gestes offerts : **Prolonger** ou **Relancer la planification** (consigne facultative) et **Conclure le projet**, ou **Reprendre** ; cartes bloquées ou abandonnées **en lecture seule** avec leur raison (« Relancer » : P7) ; le compteur de l'onglet compte questions ET décisions |

Règles, toutes testées (Vitest, image, navigateur) :

- **Aucun bouton sans route réelle et testée.** La pause générale demande une confirmation, et dit ce
  qu'elle arrête vraiment (la discussion reste ouverte) ; engagée par la veille des crochets shell, elle
  n'offre pas « Reprendre » (refusé tant qu'ils existent) mais la marche à suivre. La notification de test
  n'est active que si un canal est configuré ; sinon le bouton est désactivé et la page dit « Notifications
  non configurées : leur activation passe par une PR… (railway.md, § 9) », ou « État du canal inconnu »
  tant que la passerelle ne l'a pas publié.
- **Une réussite suit la réponse de l'API** : « la carte reprend », « reprendra à la reprise du projet » ou
  « n'a pas été relancée » ; « Plafond relevé », « Planification relancée », « Carte reprise » ou « n'a pas
  été reprise ».
- **Historique** : chaque changement de vue voulu par le propriétaire ajoute une entrée (`pushState`) ; le
  geste « retour » du téléphone ramène à la vue précédente de la page (relecture de P4).
- **Aucune donnée inventée** : « Inconnu » pour une valeur absente, « Non configuré » pour un poste
  jamais vu, « Non observé » (servi par le greffon) pour le modèle réellement servi ; un code inconnu du
  greffon est montré tel quel, comme donnée ; une actualisation ratée garde la dernière valeur lue et le
  dit.
- **Sans inventaire du poste** (D25), le champ Dépôt est désactivé et la page dit « Aucun dépôt connu : le
  poste n'a encore publié aucun inventaire (étape P5). » (« Dépôts inconnus » si l'inventaire est illisible)
  ; seul « Sans dépôt » est possible, et « Qui répond » y est dit sans objet (D42). Avec un
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
poste hors ligne (une fois par passage) ; plafond atteint (une fois par valeur du plafond : une prolongation
puis un nouveau plafond en redemandent une) ; crochets shell apparus (pause générale, D34). Filets
déterministes de la relecture (D46) : planification finie sans plan → carte de décision et notification
(« …la planification s'est terminée sans plan, votre décision est attendue. ») ; question dont la carte
« répondre » s'est finie sans suite → escaladée, notification « question ». Aucune notification quand le
propriétaire conclut lui-même. L'envoi ne suit **aucune redirection** (le jeton ntfy ne part que vers
l'URL configurée) ; un 3xx est un échec réessayé vers la même URL.

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
- Pendant la pause générale, aucune passe : aucune NOUVELLE notification d'avancement (D31) ; celles déjà
  en file et la notification de test partent encore. La **discussion** avec Hermes reste ouverte (l'arrêt
  d'urgence de Hermes n'est lu que par cron, le répartiteur kanban, la passerelle de messagerie et
  `api_server`) ; lancer un projet y est refusé par ACP.
- « Clore » un projet quelconque (le passer « abandonné » et archiver ses cartes) n'existe pas en P4 : une
  carte abandonnée par le disjoncteur laisse le projet « en cours » ; seule parade, la pause (qui libère une
  place de projet actif). « Conclure » n'existe que sur une carte de décision (D41). P7.
- Surcharge de routage d'une carte existante : refusée jusqu'à P6 (D43). Prolonger le plafond de
  corrections : P6 (les corrections y sont câblées).
- Un résumé de carte n'est rendu qu'en extrait (500 caractères) dans le détail, et le dit ; « Lire le
  résumé en entier » le lit par la route de la carte, bornée à 100 000 caractères (dit aussi).
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
- Sans dépôt, aucune question ne peut naître (seules les cartes du poste en posent) : un manque se dit par
  une carte bloquée avec sa raison, que la page Questions montre en lecture seule (D42).

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
  - au navigateur, « Reprendre » une carte en triage (et, depuis la relecture, « Prolonger », « Relancer la
    planification » et « Conclure le projet ») et « Envoyer une notification de test » ne sont pas
    cliqués (aucune carte en triage dans le parcours ; canal non configuré dans la pile d'identité) ; les
    décisions sont prouvées par Vitest, les tests d'image et le contrat (§ 12) ;
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
| Contrôles | `check_version.py`, `check_engine_frozen.py`, `verifier_catalogue.py`, `balayer_secrets.py`, `git diff --check` | 0.11.0 partout (manifeste d'`acp-projets` compris) ; moteur gelé ; 21 skills ; aucun motif de secret ; « propre » était **faux** : `git diff --check refonte/hermes-p3..HEAD` signalait deux lignes vides en fin de fichier (79afb4b, 609b96c), relevées par la relecture et corrigées (§ 12) |
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

- Seconde partie (page « Projets »), sommet poussé `4d8265a`, **verte** :
  - `ci.yml` [36244812181](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36244812181) :
    poste Windows **386 réussis** ; poste Linux **377 réussis, 9 ignorés** (les 9 tests propres à Windows) ;
    interface **80** (13 fichiers) et trois bundles identiques aux sources ; moteur **74** ;
  - `image.yml` [36244812049](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36244812049)
    (35 min) : `hermes plugins compat` greffon vert, témoin code 1 ; sonde réelle de context7 connectée
    (1 940 ms) ; **493 réussis** dans l'image (4 min 15 s) ; **136 réussis** au contrat (24 min 24 s), dont
    les 18 de P4 (notification de test reçue une fois par le faux ntfy ; planification réclamée 4 s après
    la fin de l'exploration) ; navigateur **6 réussis** (4 min 25 s), dont `test_projets.py` : quatre
    projets « Terminé » 71,1 s après la fin des explorations, groupe des greffons Kanban, Projets,
    Catalogue, aucune requête hors de l'origine ; aucun conteneur, volume ni réseau de test restant.
  - Poussés ensuite : `5002285` (la page remonte en haut à chaque changement de vue ; Vitest 80 et
    navigateur `test_projets.py` et `test_interface_fr.py` rejoués en local : 2 réussis, 3 min 53 s),
    `8532ee2` (citation des lignes de Hermes) et `463db67` : CI de `463db67` **verte** (`ci.yml`
    [36246916733](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36246916733),
    `image.yml` [36246916752](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/36246916752)).

## 11. Non prouvé

- Le rendu de la page « Projets » sur un vrai téléphone : Chromium à 390×844 (émulation), ni Safari iOS
  ni un vrai réseau mobile.

- La qualité d'un vrai plan : les tests ne jouent qu'un modèle factice.
- Le scénario Railway (téléphone, notification, second appareil), la livraison réelle par Telegram ou
  ntfy (faux serveur seulement), le poste réel (P5-P6) et la tenue dans 2 Go avec de vrais modèles.
- La course de découverte des greffons au démarrage d'un worker (`hermes_cli/cli_init_mixin.py:214-228`)
  n'a jamais été observée ; si elle survenait, la carte échouerait et serait relancée (`failure_limit: 3`),
  visiblement.

## 12. Relecture indépendante de P4 : traitement (26/09/2026)

Trois relectures de `463db67` (scénario du propriétaire, garde, produit) ont relevé 21 constats (deux
identiques : `git diff --check`). Chacun a été vérifié : **tous sont réels** ; aucun n'est réfuté. Chaque
correction a un test qui échoue sans elle (preuves en fin de section). Décisions ajoutées : **D41 à D47**
([plan](plan.md) § 1, non confirmées).

| # | Constat (lentille, gravité) | Traitement | Preuve |
|---|---|---|---|
| 1 | Planification finie sans `projet_planifier` : projet arrêté, affiché « en cours », sans carte ni notification (scénario, haute) | Filet de l'émetteur (`planifications_sans_plan`, D46) : UNE carte de décision « Planification sans plan » et UNE notification ; état dérivé `a_decider` (dès la fin de la carte) ; « Relancer la planification » fait planifier le tour 1 par cette carte ; « Conclure » → « abandonné ». **Écart** : la garde ne refuse pas `kanban_complete` sur une planification sans tour (complément proposé) : le modèle se rabattrait sur `kanban_block`, et une carte bloquée ne se relance pas depuis la page en P4 ; le filet couvre toutes les fins | image `test_planification_finie_sans_plan_adresse_une_decision`, `test_conclure_une_planification_sans_plan_abandonne_le_projet` ; contrat `test_planification_sans_plan_puis_relance` ; témoin |
| 2 | « Reprendre » une carte de triage de plafond : Hermes ne peut pas planifier (refus `contexte`), le projet passe « terminé » avec sa notification (scénario, haute) | Option (a), D41 : « Prolonger » relève le plafond (tours + 1, cartes + `prolongation_cartes` = 10), journalisé ; la carte de décision peut alors appeler `projet_planifier` (tour courant + 1), jamais avant la décision ; carte, section de prompt (rôle « triage ») et skill `acp-orchestration` alignées (empreinte du verrou mise à jour) ; une carte de décision par VALEUR du plafond | image `test_prolonger_au_plafond_de_tours_planifie_un_tour_de_plus` ; contrat `test_prolonger_au_plafond_puis_conclure` ; témoin |
| 3 | Plafond de cartes atteint quand la synthèse veut un tour : refus sans triage ni notification, puis « terminé » (scénario, moyenne) | Quand moins de deux cartes restent (aucun plan ne tient) : carte de décision « cartes » et notification « plafond » ; sinon le refus « Réduisez le plan » reste | image `test_plafond_de_cartes_sans_plan_possible_adresse_une_decision` ; témoin |
| 4 | Question « hermes_d_abord » dont la carte « répondre » finit sans réponse ni escalade : bloquée en silence (scénario, moyenne) | Filet de l'émetteur (`questions_sans_suite`, D46) : escalade (motif dit), notification « question ». **Écart** : pas de refus de `kanban_complete` sur la carte « répondre » (même raison qu'au n° 1) | image `test_question_sans_suite_escaladee` ; contrat `test_question_sans_suite_escaladee_par_la_passerelle` ; témoin |
| 5 | `routage_surcharger` de portée « carte » répond « ok » sans effet (scénario, moyenne) | Refus explicite `surcharge_carte` (D43), schéma réduit à la portée « projet » | image `test_surcharge_d_une_carte_refusee_tant_qu_elle_ne_s_applique_pas` ; témoin |
| 6 | La reprise d'un projet en pause dépasse `projets_actifs_max` (scénario, basse) | Contrôle à la reprise, 409 `projets_actifs` | image `test_reprise_respecte_le_plafond_de_projets_actifs` ; témoin |
| 7 | `git diff --check` pas propre (lignes vides en fin de fichier), et § 9 disait « propre » (scénario et garde, basse) | Lignes retirées ; § 9 corrigé ; test du dépôt `test_aucun_fichier_suivi_ne_finit_par_une_ligne_vide` | test en échec avant, réussi après ; `git diff --check refonte/hermes-p3..HEAD` : code 0 |
| 8 | Isolation des projets non garantie : `kanban_comment` et `kanban_link` acceptent un `board` et un `task_id` choisis par le modèle (garde, moyenne) | Garde (D44) : dans un worker, tout `kanban_*` sur un autre tableau refusé ; `kanban_comment` sur sa seule carte ; `kanban_link` retiré (33 noms). En P6 : le poste n'exécute que le corps émis par le greffon et les commentaires du propriétaire et de `hermes (acp-questions)` (décision à tenir) | image `test_un_worker_ne_touche_que_son_tableau_et_sa_carte`, `test_garde_liste_blanche` ; témoin |
| 9 | Le transport suit une redirection et y transmet le jeton ntfy (garde, basse) | Ouvreur sans redirection ; un 3xx est un échec « HTTP 3xx », réessayé vers la même URL | image `test_transport_ne_suit_aucune_redirection` (sur le greffon de `463db67` : code 200, jeton reçu par l'autre hôte) ; témoin |
| 10 | « Reprendre » lève une pause générale engagée par la veille des crochets encore présents (garde, basse) | 409 `crochets` (D45) ; le bandeau n'offre pas « Reprendre » pour cette raison et dit la marche à suivre | image `test_reprise_generale_refusee_tant_que_des_crochets_existent` ; Vitest ; témoin |
| 11 | Résultat coupé à 500 (détail) et 200 (liste) caractères sans le dire ni moyen de le lire (produit, haute) | `resume_longueur`, `resume_tronque`, `derniere_note_tronquee` ; route `GET /v1/projets/{id}/cartes/{carte}` (entier, borné à 100 000 et dit) ; `resultat` du projet (synthèse du dernier tour, en entier) ; page : « Extrait : 500 caractères sur N », « Lire le résumé en entier », « Résultat du projet » | image `test_resume_coupe_le_dit_et_se_lit_en_entier`, `test_resultat_du_projet_en_entier` ; Vitest ×2 ; navigateur (résultat affiché) ; témoin |
| 12 | Raison d'une carte bloquée « Inconnu » alors qu'elle est dans l'événement (produit, haute) | Raison du dernier `blocked`/`block_loop_detected`, erreur du disjoncteur pour un abandon, détail de la décision pour une carte de décision | image `test_raison_connue_des_cartes_bloquees_et_en_triage` ; Vitest ; témoin |
| 13 | « Qui répond » proposé sans dépôt, sans effet possible (produit, moyenne) | Choix masqué et note « sans objet » (D42), champ placé après le dépôt ; limite au § 7 | Vitest ; navigateur (aucun bouton radio sans dépôt) |
| 14 | Texte de la pause générale inexact : la discussion continue (produit, moyenne) | Vérifié dans la source de Hermes (`agent.estop` lu par cron, `kanban_watchers_common`, `api_server`, `run_busy`, `run_inbound`, `status`, `pause` seulement) ; texte, D31 et § 7 corrigés | Vitest |
| 15 | Réussite annoncée sans lire la réponse de l'API (produit, moyenne) ; en plus, une réponse sur un projet en pause rendait la carte « prête », donc réclamable, jusqu'à la passe suivante | Messages d'après `carte_debloquee`/`reprise_differee` et `reprise`/`action` ; sur un projet en pause, la carte reste planifiée et reprend à la reprise du projet ; décision de triage refusée pendant la pause (D47) | Vitest ×2 ; image `test_reponse_pendant_la_pause_reprend_a_la_reprise_du_projet`, `test_decision_de_triage_refusee_sur_un_projet_en_pause` ; témoin |
| 16 | Ni prolonger ni clore un projet ; `abandonne` jamais posé ; compteur sans les décisions (produit, moyenne) | D41 : « Prolonger », « Relancer la planification », « Conclure le projet » (pose `termine` ou `abandonne`) ; compteur = questions + décisions ; « Clore » un projet quelconque : P7 (limite dite) | image (n° 1 et 2), `test_conclure_au_plafond_termine_sans_notification`, `test_conclure_par_la_route` ; Vitest |
| 17 | Le « retour » du téléphone quitte la page (produit, moyenne) | `history.pushState` pour les gestes, relecture sur `popstate` | Vitest ; navigateur (`go_back`, `go_forward`) |
| 18 | « Non configurées » affirmé quand l'état est inconnu ; « aucun inventaire » quand `/v1/poste` a échoué (produit, basse) | « État du canal inconnu… » (page et 409), « Dépôts inconnus… » ; renvoi à [railway.md](railway.md) § 9 (PR d'abord) | image `test_liste_vide_et_etats_inconnus`, `test_notification_de_test` ; Vitest ×2 |
| 19 | Affichages techniques : journal brut, « Palier : default », question sans titre de carte ni contexte (produit, basse) | Journal en français (action, acteur), détail technique replié ; « Standard » ; titre de la carte et contexte rendus par `/v1/questions` et affichés. **Gardé** : les efforts `low`/`medium` sont des valeurs du relevé du poste, montrées telles quelles (donnée) | image `test_question_listee_avec_le_titre_de_sa_carte_et_son_contexte` ; Vitest |
| 20 | Décisions de P4 moins bien posées que P3 (produit, basse) | Priorité (D25, D31, D39, D40, D41), colonne « Autre option et conséquence pour vous », D41 à D47 | `test_les_choix_de_p4_se_disent_non_confirmes` |

**Chaque test échoue sans sa correction** (26/09/2026) :

- les **18** nouveaux tests d'image, lancés sur le greffon de `463db67` (`git archive`, monté à la place de
  celui de l'image `acp-hermes-tests:p4r`) : **18 échecs sur 18** (`en_cours` au lieu de `a_decider`,
  question restée `ouverte`, code 200 et jeton reçu par l'hôte de redirection, « Réduisez le plan » sans
  décision, 200 au lieu de 409 sur les crochets, raison `None`, surcharge « ok »…) ;
- les **13** tests Vitest de `projets-relecture.test.tsx`, lancés sur les sources de `463db67` : **13 échecs
  sur 13** ;
- `test_aucun_fichier_suivi_ne_finit_par_une_ligne_vide` : en échec avant le retrait des deux lignes ;
  `test_les_choix_de_p4_se_disent_non_confirmes` : en échec sur l'ancien tableau ;
- `scripts/temoins_negatifs_p4.sh` : **12 témoins de plus** (24 en tout), chaque protection de la
  relecture retirée fait échouer son test.

Commits (aucun `Co-Authored-By`) : `3ebba83` style (lignes vides en fin de fichier), `8f9762f` garde et
transport, `4ef7e9e` cœur du greffon, `353a843` page « Projets », puis cette documentation.

### Preuves locales de la relecture (26/09/2026, Windows 10, Docker 29.5.3, Python 3.12.10, pytest 9.1.1, Node 24.19.0, Playwright 1.62.0 et son Chromium déjà présent)

Images `acp-hermes:p4r` et `acp-hermes-tests:p4r` construites depuis l'arbre corrigé (greffons, bundles et
tests d'image identiques à `353a843`, empreintes SHA-256 comparées fichier par fichier) ; identité
`acp-identite:p4` (dossier `identite/` inchangé).

| Suite | Commande | Résultat |
|---|---|---|
| Dépôt | `python -m pytest -q` (venv Python 3.12.10 du verrou) | **387 réussis** (39 s) : les 386 d'avant et `test_aucun_fichier_suivi_ne_finit_par_une_ligne_vide` |
| Contrôles | `check_version.py`, `check_engine_frozen.py`, `verifier_catalogue.py`, `balayer_secrets.py --plage refonte/hermes-p3..HEAD`, `git diff --check refonte/hermes-p3..HEAD` | code 0 chacun : 0.11.0 ; moteur gelé ; 21 skills (empreinte d'`acp-orchestration` mise à jour dans le verrou) ; aucun motif de secret ; aucune erreur d'espace |
| Interface | `npm test --prefix apps/interface` puis `npm run check` | TypeScript sans erreur ; Vitest **93 réussis** (14 fichiers, dont les 13 de `projets-relecture.test.tsx`) ; 6 fichiers de greffons à jour |
| Dans l'image | `docker run … acp-hermes-tests:p4r -m pytest /opt/acp-tests/image` | **511 réussis** (5 min 28 s) : 493 d'avant et 18 nouveaux |
| Témoins négatifs | `IMAGE=acp-hermes-tests:p4r bash scripts/temoins_negatifs_p4.sh` | **24 sur 24** (82 s) |
| Contrat complet | `python -m pytest -s -v -rA hermes/tests/contrat` (images `p4r`) | **139 réussis** (32 min 48 s) : les 136 d'avant et 3 nouveaux ; puis `test_routes_sans_session_401` étendu aux 13 routes P4 : **1 réussi** (401 partout) |
| Navigateur | `ACP_E2E_OBLIGATOIRE=1 … python -m pytest -s -v -rA hermes/tests/e2e` (images `p4r`) | **6 réussis** (5 min 01 s) |

Relevés du contrat (pile complète : passerelle, répartiteur, workers kanban réels, modèle factice, faux
ntfy, poste simulé) :

- **planification sans plan** : carte de décision « Planification sans plan — votre décision est
  attendue » (gestes `relancer`, `conclure` ; raison « carte … finie sans appel réussi à
  projet_planifier ») ; liste `actif` / `a_decider` ; UNE notification ; après « Relancer la
  planification », le worker de la carte de décision planifie le tour 1 (`"ok": true, "tour": 1`) et le
  projet va au bout (planification, décision, étape Hermes, synthèse : « Faite ») ; notifications :
  « sans plan » puis « terminé : 4 cartes faites » ;
- **question sans suite** : escaladée par la passerelle (« Hermes n'a ni répondu ni escaladé… (done) »),
  UNE notification « question », carte reprise après la réponse depuis la route ;
- **prolonger puis conclure** : au plafond de 1 tour, « Prolonger » relève le plafond à 2 ; le worker de la
  carte de décision planifie le tour 2 (`"ok": true, "tour": 2`) ; au nouveau plafond, UNE nouvelle
  décision et sa notification ; « Conclure » termine le projet ; notifications : deux « plafond de tours
  atteint », aucune « terminé ».

Relevés du navigateur (`test_projets.py`, 390×844 et 1440×900) : aux deux formats, « Qui répond » absent
sans dépôt et la note affichée ; « retour » ramène au formulaire de la page Projets et « avancer » au
détail ; résultat du projet affiché en entier (« Conclusion : la recherche est faite. ») ; quatre projets
« Terminé » 76,5 s après la fin des explorations ; aucune violation axe ; aucun texte hors du catalogue ;
aucune requête hors de l'origine (202 au téléphone, 307 au bureau). Aucun
conteneur, volume ni réseau de test restant (liste des volumes identique avant et après).

Intégration continue de ces corrections : poussée après ce commit, consignée ensuite.
