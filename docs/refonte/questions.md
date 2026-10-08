# File Questions, notifications et continuité téléphone ↔ bureau (étape P7)

État du **8 octobre 2026**. Étape P7 du [plan d'autonomie](autonomie.md) : « questions, notifications et continuité ;
passage aux dépôts réels ». Décisions appliquées : **D93 à D116** ([plan.md](plan.md)). Ce document rassemble ce que
le propriétaire trouve dans la file Questions et autour d'elle ; le détail technique reste dans les documents de
chaque zone : routes et flux dans [projets.md](projets.md) (§ 4, § 4 bis, § 4 ter, § 5), pages dans
[interface.md](interface.md) (§ 13 à § 15), garde « dépôt privé » dans [executant.md](executant.md) (§ 16), gestes sur
Railway dans [railway.md](railway.md) (§ 14).

Ce document décrit l'état **réuni** de P7 (parties A à F, fusion `e2d210b` du 8 octobre 2026) ; `executant.md` § 16
est écrit par `9235999`, la relance d'une carte bloquée pour un secret (§ 4) arrive avec `e85c7e3` et `1f2574c`.

**Rien n'est déployé** : tout ce qui suit est prouvé en local et en CI, avec le modèle factice, le faux exécutant, le
faux fournisseur d'identité et un faux serveur ntfy (§ 13). Ce qui exige Railway, un vrai téléphone ou un vrai canal
est marqué **sur Railway seulement** ou **non prouvé**.

---

## 1. En bref

- **Une seule file** de ce qui attend le propriétaire, à la même adresse au téléphone et au bureau :
  `/projets?vue=questions` (page Projets, greffon d'interface `acp-projets`), en **cinq sections** (§ 2).
- **Qui répond** se règle par projet à tout moment (Hermes d'abord, ou vous), pour les questions **suivantes** (§ 3).
- Une carte bloquée ou abandonnée se **relance** depuis la file, avec une consigne facultative (§ 4) ; un projet se
  **clôt** depuis son détail (§ 5).
- Les **discussions** ouvertes par la page Discussion qui attendent une réponse sont listées, en lecture seule (§ 6).
- Les pages se mettent à jour **sur signal** d'un flux SSE d'invalidation, avec repli sur le sondage de 15 s (§ 7).
- Chaque **notification** ouvre ce qu'elle annonce (lien en paramètres de requête, gardé à travers la connexion) (§ 8) ;
  un **bilan quotidien** facultatif est créé par le propriétaire en cron, sans modèle (§ 9).
- L'**Accueil** lit une seule route agrégée, le même ordre et les mêmes textes à toutes les largeurs (§ 10).

---

## 2. Les cinq sections

| Section | Source | Gestes | Cible d'un lien profond |
|---|---|---|---|
| 1. **Questions** | table `questions` du greffon (ouvertes, escaladées) | **Répondre** | `?vue=questions&q=<question>` |
| 2. **Décisions** | cartes en `triage` des tableaux de projet | **Prolonger**, **Relancer la planification** (consigne facultative), **Conclure le projet**, ou **Reprendre** | `?vue=questions&carte=<tableau>/<carte>` |
| 3. **Revues** (P6) | cartes en revue (fichiers de pilotage, D90) | **Accepter**, **Refuser** (motif) | idem |
| 4. **Cartes arrêtées** | cartes `blocked`, dont abandonnées (`gave_up`) | **Relancer** (consigne facultative) ou la raison du refus | idem |
| 5. **Discussions en attente** | sessions du JSON-RPC natif `/api/ws` au statut `waiting` | **Ouvrir la discussion** (`/discussion?session=<clé>`) | — |

En tête de la file : **À traiter par vous : n** et **Chez Hermes : m**. Les noms ci-dessus sont les titres des
sections de la page comme les lignes de l'Accueil (relecture finale de P7 : la page disait « Cartes en triage »,
« Revues des fichiers de pilotage », « Cartes bloquées ou abandonnées »).

- **Règle unique « chez »** (correction K6 du cahier) : une question est **chez Hermes** si elle est `ouverte` **et**
  que sa carte « répondre » existe ; sinon elle est **à vous** (escaladée, ou carte « répondre » jamais créée). Jamais
  d'après le réglage courant du projet : une question ouverte garde son traitement quand le réglage change (§ 3). Le
  détail d'un projet sert aussi `chez` (relecture finale de P7) : une question ouverte « à vous » se lit « Votre
  réponse est attendue » dans la file comme dans le détail, jamais « Hermes cherche la réponse » ; le réglage du
  projet se lit « Vous » (« Moi » reste le choix du formulaire).
- **« À traiter par vous »** = questions à vous + décisions + revues + cartes arrêtées (compteurs servis par le
  greffon, `compteurs` de `GET /v1/questions`), **plus** les discussions en attente quand elles ont pu être lues.
  Sinon la page dit « discussions : état inconnu » : jamais zéro. L'Accueil fait de même (total suivi de « discussions
  en attente : état inconnu, non comptées », jamais « Rien n'attend votre décision ») ; la liste de la page Discussion
  dit que l'état d'attente est inconnu (relecture finale de P7).
- Une cible de lien profond est défilée et marquée (`aria-current`) ; une cible déjà traitée le dit (« Cette demande a
  déjà été traitée »), sans erreur. Une cible que la page vient de traiter n'est pas « déjà traitée » : le message tiré
  de la réponse de l'API (« la carte reprend », « reprendra à la reprise du projet », « n'a pas été relancée »…) est
  annoncé par la section et reste visible quand la demande quitte la file (relecture finale de P7). Une cible d'un
  tableau illisible a un état « inconnu », jamais « traitée ».

---

## 3. Qui répond (réglage par projet, D95)

- Au lancement : « Hermes d'abord » (défaut) ou « Moi » (formulaire « Nouveau projet », avec un dépôt seulement : sans
  dépôt, aucune question ne peut naître, D42).
- **À tout moment** : détail du projet → **Changer qui répond** → `POST /v1/projets/{id}/reponses`
  `{"reponses": "hermes_d_abord" | "proprietaire"}`. La page ne change rien avant la réponse de l'API.
- **Effet** : sur les questions **suivantes** seulement. Les questions ouvertes gardent leur traitement ; le
  propriétaire peut toujours répondre lui-même à une question encore chez Hermes (la carte « répondre » qui arriverait
  après lui voit la question fermée et se termine). La réponse dit combien de questions ouvertes ne sont pas touchées
  (`questions_ouvertes_inchangees`). Journal `reglage_reponses` (avant, après, auteur).
- **Hermes d'abord** : une carte « répondre » (skill `acp-questions`) répond si les décisions du projet couvrent la
  question, sinon escalade. La skill escalade toujours : périmètre, dépense, push, fusion, publication, déploiement,
  suppression hors projet et, depuis P7, accès à un compte ou à un jeton, nouveau dépôt, réseau des exécutants,
  suppression d'une branche. La vraie borne n'est pas la skill mais l'absence d'outil : l'exécutant n'a qu'un jeton de
  lecture et ne pousse jamais (P6).
- Refus : projet inconnu (404 `projet_inconnu`), terminé ou abandonné (409 `projet_fini`), sans dépôt (409
  `reponses_sans_objet`), valeur inconnue (400 `reponses`).

---

## 4. Relancer une carte arrêtée (D94)

`POST /v1/cartes/{tableau}/{carte}/relancer`, corps `{"consigne": "…"}` facultatif (1 à 4 000 caractères, balayée par
les motifs de secrets : un jeton collé par erreur est refusé). Contrôles, dans l'ordre, chacun avec son refus :

1. projet ACP connu (404 `projet_inconnu`), carte connue (404 `carte_inconnue`), carte émise par le greffon (403
   `carte_non_acp`) ;
2. projet **actif** : en pause → 409 `projet_en_pause` (« reprenez d'abord le projet ») ; terminé, abandonné ou en
   création → 409 `projet_fini` (une carte débloquée sur un projet fini ne serait jamais servie) ;
3. carte en **revue** → 409 `carte_en_revue` (Accepter ou Refuser) ; carte qui n'est pas `blocked` → 409
   `carte_non_arretee` (statut lu dit).

**Effet.** Aucune carte n'est créée : le plafond de cartes du projet n'est pas touché. Puis `unblock_task` (compteur
d'échecs remis à zéro ; `block_recurrences` gardé : une carte relancée qui rebloque pour la même raison repart en
triage au second blocage). Journal `relance` ; **aucune notification** (c'est votre geste).

- **Carte Hermes** : la consigne devient un commentaire du propriétaire, que le worker lit avec le contexte de la carte.
- **Carte de l'exécutant** : `issue = 'relancee'` force une **session neuve** de l'agent (une consigne envoyée en
  reprise serait ignorée : correction K4), sur la branche déjà commencée (worktree gardé). Avec une consigne, la
  consigne servie est recomposée : section « Consigne du propriétaire (relance du JJ/MM à HH:MM) » **en tête**, puis
  la consigne d'origine, tronquée et dite telle pour que le tout tienne dans la borne du contrat (16 000 caractères) ;
  l'origine est gardée (`demandes.consigne_initiale`) : une seconde relance repart d'elle.
- **Carte d'intégration** (relecture finale de P7, D117) : elle n'a **pas d'agent**. L'exécutant rejoue la même fusion
  déterministe des branches et ne lit aucune consigne : une consigne est refusée (400 `consigne_sans_objet`, rien
  n'est écrit), la file le dit (`integration`, ni champ de consigne ni « session neuve »), et la réponse rend
  `session_neuve: false`. Un conflit revient donc tant qu'aucune branche ne change : la raison du blocage et la page
  disent ce que vous pouvez réellement faire — relancer (utile après un échec passager), récupérer les branches sur
  l'exécutant (`git bundle`) pour trancher vous-même, ou clôturer le projet.
- Réponse : `{"carte", "relancee", "statut_apres", "session_neuve"}` ; la page dit « La carte repart » ou « La carte
  n'a pas été relancée (statut : …) » d'après cette réponse seulement ; le statut est traduit (« Prête », « Bloquée »),
  jamais le code kanban brut (relecture finale de P7).

**Relance après un secret (D111, D114 ; [executant.md](executant.md) § 16.3).** Une carte bloquée parce qu'un secret a
été trouvé dans son travail a sa branche renommée `quarantaine/<carte>`. L'exécutant de la partie E ne reprend plus
jamais ce travail : la carte repart de son départ sur une **branche neuve**, sans la session d'agent qui l'avait vu
(D110). La relance n'est donc **admise que si le dernier inventaire de l'exécutant actif porte la visibilité mesurée de
ses dépôts** (seul un exécutant de la partie E la publie) ; sinon 409 `carte_secret` (« relance possible dès que
l'exécutant à jour a publié son inventaire »), en échec fermé. La file dit que le travail fautif reste en quarantaine
(`quarantaine`), la réponse dit `branche_neuve`. Ce comportement arrive avec les commits `e85c7e3` (greffon) et
`1f2574c` (page) de la partie E ; avant eux, la relance d'une carte bloquée pour un secret était refusée dans tous
les cas (409 `carte_secret`).

---

## 5. Clore un projet (D101)

Détail du projet → **Clore le projet** → dialogue qui dit les quatre effets → `POST /v1/projets/{id}/clore`
`{"confirmation": true}` (422 `confirmation` sinon ; projet actif ou en pause, 409 `projet_fini` sinon).

1. état `termine` si la synthèse du tour courant est faite, sinon `abandonne` (clore en pleine exécution n'est pas un
   succès ; « Conclure » reste propre aux cartes de décision, D41) ; mise à jour **conditionnelle** faite en premier :
   si l'émetteur termine le projet au même instant, une seule des deux gagne et le refus le dit (rien n'est fait) ;
2. questions ouvertes ou escaladées du projet → `annulee` ;
3. toute carte ouverte du projet → archivée (un worker Hermes en cours est arrêté par Hermes ; une carte réclamée par
   l'exécutant perd sa réclamation : au battement suivant, l'exécutant arrête l'agent, committe le travail en cours et
   rend la carte) ;
4. aucune notification. Les branches déjà rapportées restent sur l'exécutant jusqu'à la purge de 7 jours : la réponse
   les liste (`branches_rapportees`), pour une récupération éventuelle par `git bundle` ([railway.md](railway.md)
   § 13.7).

---

## 6. Discussions en attente (D104)

- **Seules les sessions ouvertes par `/api/ws`** (page Discussion, D100 ; station Qt de P8) vivent dans le processus du
  tableau de bord, et donc survivent à la fermeture du téléphone. Les questions d'une discussion en terminal (`/chat`)
  vivent dans le processus de son PTY : **non listées**, et la page le dit. C'est une limite de Hermes, pas un oubli.
- Lecture : `jsonrpc/discussions.ts`, par le canal commun `jsonrpc/canal.ts` (liste blanche des méthodes émises) :
  ticket neuf (`buildWsUrl`), `gateway.ready`, la seule méthode `session.active_list`, sans annoncer de capacité
  (aucune requête ne lui est adressée, aucune session n'est rattachée), entrées `waiting` gardées, connexion fermée ;
  délai 5 s, échec : « état inconnu ».
- Affichage : titre (ou « Sans titre »), depuis quand, aperçu de 160 caractères, **Ouvrir la discussion** ; la page de
  discussion reprend la session (`session.resume`) et rejoue la question ouverte. Le genre de la demande n'est pas
  exposé par Hermes : la ligne dit « en attente d'une réponse », sans deviner.
- **Aucune notification** pour une discussion en attente : la passerelle ne voit pas les sessions du tableau de bord
  (autre processus), et une `clarify` vit une heure en mémoire puis disparaît au redéploiement. Ce qui doit attendre le
  propriétaire passe par un **projet**.

---

## 7. Temps réel : flux d'invalidation, repli sur le sondage (D96)

Contrat complet : [projets.md](projets.md) § 4 ter ; client : [interface.md](interface.md) § 13.

- `GET /api/plugins/acp-poste/v1/flux` (même porte d'authentification que toute route de lecture) **signale** qu'un
  sujet a changé (`projets`, `questions`, `poste`, `quotas`, `notifications`, `pause`, `discussions`) ; la page relit
  alors la route REST du sujet. Aucune donnée métier dans le flux : une trame ratée se rattrape à la relecture suivante.
- Veilleur toutes les 2 s (seulement si une page est ouverte), battement toutes les 15 s (le bord Railway coupe une
  requête après 5 min sans octet), fin propre après 600 s et réouverture aussitôt avec `Last-Event-ID` (le bord coupe à
  15 min), au plus 8 flux (429 `trop_de_flux`). Annoncé par `GET /v1/meta`, clé `flux`.
- **Un seul flux par onglet**, partagé par les bundles (`window.__ACP_FLUX__`) ; relecture regroupée sur 300 ms ;
  relecture de sûreté toutes les 120 s ; page cachée : flux fermé, aucune lecture.
- **Repli** : trois échecs de suite en 2 minutes → sondage de 15 s (« Temps réel indisponible : actualisation toutes les
  15 secondes »), nouvel essai du flux toutes les 5 min ; un 401 n'est jamais réessayé (la lecture suivante redirige vers
  la connexion). La page ne dit « actualisée en temps réel » qu'après une trame reçue. **Chien de garde** (relecture
  finale de P7) : sans aucun octet (trame ou battement) pendant 40 s, ouverture comprise, la connexion est annulée et
  comptée comme un échec (veille du PC, réseau changé, connexion à moitié ouverte) : une connexion muette n'est jamais
  « temps réel », et trois flux muets en 2 minutes font le repli.

---

## 8. Notifications et liens profonds (D97)

Canal Telegram **ou** ntfy, fourni par le propriétaire (variables posées par lui dans Railway, déclarées par
`preserve()` dans `.railway/railway.ts` : [railway.md](railway.md) § 14, D116). Contenu minimal (D32), aucune donnée de
la question dans le lien. Chaque lien est **en paramètres de requête, jamais en fragment** : la porte d'authentification
de Hermes ne garde, pour le retour après la connexion, que le chemin et la requête ; au téléphone, dont la session a
souvent expiré, un fragment serait perdu.

| Genre | Ouvre |
|---|---|
| `question` | `/projets?vue=questions&q=<question>` |
| `bloquee`, `triage`, `abandon`, `revue`, `secret`, `conflit`, `plafond` | `/projets?vue=questions&carte=<tableau>/<carte>` |
| `termine`, `integration` | `/projets?projet=<id>` |
| `hors_ligne`, `isolement` | `/poste` |
| `bilan` | `/` (Accueil) |
| `test`, `crochets`, carte hors tableau de projet | `/projets` |

La base garde le **chemin relatif** ; l'URL publique n'est préfixée qu'à l'envoi, par la passerelle. Pas de rappel
automatique d'une question sans réponse (bruit, non demandé). Telegram n'est **pas** un canal de discussion avec Hermes
en P7 (D105).

---

## 9. Bilan quotidien facultatif (D98)

- **Créé par le propriétaire seul**, avec sa session : Accueil, carte « Bilan quotidien », bouton **Créer le bilan
  quotidien (8 h)** (route native `POST /api/cron/jobs`, tâche `no_agent`, script `acp-bilan.py`, `0 8 * * *`,
  livraison `local`), ou la page Cron de Hermes. L'agent ne le peut pas (`cronjob` coupé) et un cron ne peut pas lancer
  de projet (D24).
- **Aucun modèle, aucun jeton** : le script de l'image, déposé par root dans `/opt/data/scripts/` (seul fichier admis
  par la garde de démarrage, à empreinte connue), lit la base et enfile **une** notification `bilan:<date de Paris>`,
  compteurs seulement, même quand rien n'a bougé (« ACP — Bilan du 02/10 : 2 projets en cours (5 cartes faites sur 12),
  1 question et 1 décision pour vous, exécutant en ligne. »). Fuseau épinglé `Europe/Paris`.
- La carte dit « Actif » et la prochaine exécution, « En pause », « En erreur » ou « Non créé », puis la dernière
  exécution et son issue (`last_status` ≠ `ok` : « Dernière exécution en échec », détail replié ; relecture finale de
  P7 : jamais « envoi », Hermes date `last_run_at` même en échec) ; canal absent : « Le bilan ne partira pas ».
  Pause et suppression : page Cron de Hermes.

---

## 10. Accueil agrégé (D99)

Page à sept blocs, **dans cet ordre à toutes les largeurs** (une colonne à 390 px, trois au bureau) : **À traiter
par vous** (total et trois premières demandes en liens profonds), **Projets en cours**, **Exécutant** (état réel, carte
en cours, voies fermées et leur raison), **Quotas**, **Notifications et bilan**, **Sessions récentes**, **Système**.

La route agrégée `GET /api/plugins/acp-poste/v1/accueil` sert, en une lecture, la même au téléphone, dans le
navigateur du PC et, s'il le veut, pour le desktop (fixture partagée `hermes/tests/outils/fixtures_accueil/accueil.json`),
les blocs du travail : `a_traiter`, `chez_hermes`, `discussions`, `projets`, `executant`, `quotas`, `notifications`
et `pause_generale`, avec `genere_le` et `illisibles`. Un bloc illisible y vaut `null` avec sa raison
(`illisibles`), jamais une valeur par défaut. Le reste de la page a ses propres lectures : le bilan lit
`GET /api/cron/jobs` (route native), les **Sessions récentes** `GET /api/sessions` (route native, cinq dernières), le
**Système** `GET /api/plugins/acp-poste/v1/meta` ; les discussions en attente du bloc « À traiter » sont comptées par
le client sur `/api/ws` (`session.active_list`). La carte « Poste » figée sur « Non configuré » depuis P3 a
disparu (c'était devenu une donnée fausse).

---

## 11. Routes et codes de refus

Routes du greffon sous `/api/plugins/acp-poste/`, session du tableau de bord exigée. Toute écriture : `Content-Type:
application/json` (415 `json`), `Origin` égal à l'URL publique (403 `origine`), corps de 64 Kio au plus (413), champ
inconnu refusé (400 `arguments`). Erreurs : `{"detail": {"code", "message"}}`, message en français.

| Méthode et chemin | Corps | Réponse | Refus propres |
|---|---|---|---|
| `GET /v1/questions` | — | `questions[]` (dont `chez`, `carte_repondre_statut`), `triage[]`, `revues[]`, `bloquees[]` (dont `relancable`, `refus_relance`, `executant`, `integration`, `quarantaine`), `discussions` (`suivies`, `requetes_ouvertes`), `compteurs` (`a_traiter`, `chez_hermes`, `questions`, `decisions`, `revues`, `arretees`) | — |
| `POST /v1/questions/{q}/reponse` | `reponse` | `{question, etat, carte_debloquee, reprise_differee}` | 404 `question_inconnue`, 409 `question_fermee` |
| `POST /v1/cartes/{tableau}/{carte}/relancer` | `consigne?` | `{carte, relancee, statut_apres, session_neuve}` | 404 `projet_inconnu` / `carte_inconnue`, 403 `carte_non_acp`, 409 `projet_en_pause` / `projet_fini` / `carte_en_revue` / `carte_non_arretee` / `carte_secret`, 400 `arguments` / `secret` / `consigne_sans_objet` (carte d'intégration) |
| `POST /v1/projets/{id}/reponses` | `reponses` | `{projet, avant, apres, questions_ouvertes_inchangees}` | 404 `projet_inconnu`, 409 `projet_fini` / `reponses_sans_objet`, 400 `reponses` |
| `POST /v1/projets/{id}/clore` | `{"confirmation": true}` | `{projet, clos, etat, cartes_archivees, cartes_non_archivees, questions_annulees, branches_rapportees}` | 422 `confirmation`, 404 `projet_inconnu`, 409 `projet_fini` |
| `GET /v1/accueil` | — | `a_traiter`, `chez_hermes`, `discussions`, `projets`, `executant`, `quotas`, `notifications`, `pause_generale`, `genere_le`, `illisibles` (ni sessions, ni système, ni bilan : § 10) | — |
| `GET /v1/flux` | — | `text/event-stream` (trames `etat`, `changement`, battement, `fin`) | 401 sans session, 429 `trop_de_flux` (`Retry-After: 30`) |
| `GET /v1/meta` | — | dont `flux` et `accueil` | — |

Routes **natives** de Hermes employées par l'interface, jamais par l'agent : `GET /api/cron/jobs` et `POST
/api/cron/jobs` (bilan, avec la session du propriétaire), `GET /api/sessions` et le JSON-RPC `/api/ws` (discussions).

---

## 12. Ce que voit le propriétaire

**Au téléphone (390×844).** Il lance un projet depuis « Nouveau projet », ferme la page, verrouille le téléphone. Une
carte de l'exécutant pose une question qu'Hermes ne sait pas trancher : la question est escaladée, la notification
arrive (« question »), son lien ouvre `…/projets?vue=questions&q=…`. Session expirée : la porte d'authentification
demande la connexion (passkey), puis ramène **sur la question**, mise en évidence. Il répond (ou laisse pour plus tard).

**Au bureau (1440×900).** Le même lien, ou l'onglet Questions, ou l'Accueil (« À traiter par vous ») mène à la même
question, au même état : tout l'état vit sur Railway (tables du greffon, tableaux kanban, sessions). Une réponse donnée
au bureau fait repartir la carte (`reprise: true`, la réponse dans la carte servie) ; la page du téléphone, rouverte,
montre le nouvel état sans rechargement ni sondage (signal du flux). Une discussion commencée au téléphone sur la page
Discussion et restée sur une question se reprend au bureau par **Ouvrir la discussion**, la question rejouée.

**La station Qt (P8)** lit les mêmes routes de lecture (`GET /v1/questions`, `/v1/projets`…) ; elle n'ouvre pas encore
le flux ni les gestes ajoutés par P7 (Relancer, Qui répond, Clore) : [desktop.md](desktop.md). **Non prouvé** : la
station face à un greffon P7 au-delà de la compatibilité de lecture déjà testée en P8.

---

## 13. Preuves et limites

**Prouvé en local** (Windows 10, Docker, images construites depuis les branches de P7 ; journal de P7) **et en CI**
(workflow « Image Hermes ») : relevés datés et identifiants de runs dans [`docs/reprise-poste.md`](../reprise-poste.md)
§ 6 undecies.

| Preuve | Tests |
|---|---|
| file à cinq sections, règle `chez`, compteurs, relance (refus, carte Hermes, carte de l'exécutant, consigne longue, carte abandonnée), qui répond, clôture | image : `test_file_questions.py`, `test_relance.py`, `test_reponses_reglage.py`, `test_cloture.py`, `test_routes_p7.py` ; contrat : `test_projets_contrat.py`, `test_execution_contrat.py` |
| flux : chaque mutation publie son sujet, aller-retour entre deux passes, `Last-Event-ID`, battement, fin, 429, place rendue après déconnexion, délai réponse → trame à travers les six intergiciels du vrai tableau de bord | image : `test_flux.py` ; contrat : `test_flux_contrat.py` ; Vitest : `flux.test.tsx` |
| liens profonds en requête, relatifs en base, préfixés à l'envoi | image : `test_notifications_liens.py` |
| bilan : cron natif `no_agent` créé avec la session du propriétaire, déclenché, une seule ligne par jour de Paris, reçue par le faux ntfy, prochaine exécution 08:00 heure de Paris, second démarrage admis | image : `test_bilan.py`, `test_demarrage.py` ; contrat : `test_bilan_contrat.py` |
| redémarrage de Hermes pendant une question (même volume) : question intacte, aucune notification en double, réponse puis reprise, projet terminé par l'intégration | contrat : `test_parcours_p7_contrat.py` |
| parcours 390×844 → notification → 1440×900 **sans session** (connexion par passkey virtuelle) → arrivée sur la question → réponse → « Terminé » sans rechargement, chaque relecture suivant une trame | navigateur : `test_parcours_p7.py` |
| discussion : question survivant à la déconnexion, `waiting` vue par un second client, même requête rejouée, réponse | contrat : `test_discussion_contrat.py` ; navigateur : `test_discussion.py` ; Vitest : `discussion.test.tsx` |
| Accueil égal à la fixture partagée ; bloc illisible dit | image : `test_accueil.py` ; Vitest : `accueil.test.tsx` |

**Sur Railway seulement** (cahier P7 § 13.6, après la fusion et le déploiement ; gestes du propriétaire,
[railway.md](railway.md) § 14) : notification de test reçue sur le vrai téléphone ; parcours réel (vrai téléphone, vrai
canal, vrai exécutant) ; redéploiement réel pendant une question ; flux à travers le vrai bord Railway (délai mesuré,
`fin` à 10 min, reconnexion) ; bilan reçu à 8 h ; transcriptions **illustratives** de la carte « répondre » (jamais
une garantie de la qualité des réponses de Hermes).

**Limites, dites.**
- Les questions d'une discussion `/chat` (terminal) ne sont pas dans la file (§ 6) ; une `clarify` de la page
  Discussion vit une heure au plus et disparaît au redémarrage de Hermes.
- Le signal `discussions` n'est qu'un compteur global : la section est relue par `session.active_list`.
- Le flux ne contrôle la session qu'à l'ouverture : un flux ouvert survit au plus 10 min à l'expiration de la session
  (il ne porte que des noms de sujets). Un aller-retour de l'arrêt d'urgence fait hors d'ACP dans le même intervalle
  de 2 s n'est vu qu'à la relecture de sûreté.
- Le bilan part du fil d'envoi de la passerelle : après un redémarrage pendant une pause générale, il reste en file
  jusqu'à la reprise.
- Rendu prouvé dans Chromium seulement (390×844 émulé) : ni vrai téléphone, ni Safari iOS.
- La livraison réelle par Telegram ou ntfy n'est prouvée que contre un faux serveur.
