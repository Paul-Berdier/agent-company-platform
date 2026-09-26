# Projets autonomes sur Hermes (étape P4)

État du **26 septembre 2026**, branche `refonte/hermes-p4`, version 0.11.0 inchangée. **Rien n'est
déployé.** Ce document décrit le **cœur serveur** livré par P4 : ce que le greffon groupé `acp-poste`
fait sur Railway, sans le poste Windows. Références : [plan d'autonomie](autonomie.md) (§ 8, P4),
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
- La page « Projets » (greffon d'interface `acp-projets`) est livrée par la seconde partie de P4 ; ce
  document couvre le cœur serveur, dont elle n'appelle que les routes du § 4.

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
  modèle 18,3 à 19,3 s après.
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

## 10. Intégration continue

Branche poussée après le commit de documentation ; runs consignés dans
[`reprise-poste.md`](../reprise-poste.md) § 6 quater par le commit suivant.

## 11. Non prouvé

- La qualité d'un vrai plan : les tests ne jouent qu'un modèle factice.
- Le scénario Railway (téléphone, notification, second appareil), la livraison réelle par Telegram ou
  ntfy (faux serveur seulement), le poste réel (P5-P6) et la tenue dans 2 Go avec de vrais modèles.
- La course de découverte des greffons au démarrage d'un worker (`hermes_cli/cli_init_mixin.py:214-228`)
  n'a jamais été observée ; si elle survenait, la carte échouerait et serait relancée (`failure_limit: 3`),
  visiblement.
