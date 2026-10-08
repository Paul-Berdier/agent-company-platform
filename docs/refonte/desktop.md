# P8 — Station de travail Qt rebranchée sur Hermes

État du 2 octobre 2026. Étape P8 du [plan d'autonomie](autonomie.md) (§ 8, volet desktop),
branche `refonte/hermes-p8`, partie de `refonte/hermes` (`b3faac0`, P0 à P5 fusionnées).
**Réalisée côté dépôt, poussée, sans PR ni fusion ; rien n'est déployé.** Version 0.11.0
inchangée.

**Étape P8b (8 octobre 2026)** : station alignée sur P7, branche `refonte/hermes-p8b` (de
`refonte/hermes` `b9779f1`, P0 à P8 et P7) ; voir § « P8b » plus bas, et ses corrections
après relecture indépendante (constats desktop-1 à desktop-7). Poussée, sans PR ni fusion ;
rien n'est déployé.

Guides : [architecture](../native-desktop-architecture.md),
[sécurité](../desktop-security.md), [construction et bout en bout](../desktop-build.md).
Preuves datées et identifiants des runs : [`reprise-poste.md`](../reprise-poste.md),
§ 6 decies (P8) ; pour P8b, dans ce document (§ « P8b »).

## Ce qui est livré

- **Connexion native RFC 8252** contre le fournisseur `self-hosted` de Hermes (Authelia) :
  PKCE S256, état, écouteur `127.0.0.1` à port éphémère, échange, identité ; jeton de
  rafraîchissement au coffre Windows sur consentement (décoché par défaut), rotation
  écrite au coffre avant usage, une seule station par session Windows ; déconnexion avec
  révocation demandée à Hermes. `AuthManager`, le cookie `acp_session` et les pages de
  l'ancienne API sont retirés.
- **Porteur** sur les API du tableau de bord et la façade `acp-poste` (`ClientGreffonPoste`) ;
  **compatibilité** par `/v1/meta` (contrat, OpenRPC épinglé, Hermes testé, alertes,
  exécutant P6 s'il est annoncé) ; **santé** par `/api/health` et `/api/status`.
- **JSON-RPC** sur `/api/ws` (`JsonRpcChannel`, `GatewayClient`) : ticket en sous-protocole,
  sans `Origin`, rejeu après coupure, **-32601** pour toute requête serveur non gérée,
  réponses `approval`/`clarify` avec les seuls choix offerts.
- **Temps réel** (`EventStreamService`) : sondage des pages affichées, sondage léger de la
  barre d'état, veille du kanban qui relit le projet ouvert ; depuis P8b, flux
  d'invalidation du greffon (`GET /v1/flux`) qui fait relire les pages au changement.
- **Pages** : Accueil, Projets, Questions, Discussion, Poste, Quotas, Routage, Diagnostics,
  Sauvegarde (export chiffré DPAPI `ACPB1`, archive retirée du volume), Réglages.
- **Qt WebSockets** dans la chaîne d'outils, CMake et la Desktop CI.

## Preuves exigées par le plan, et leur état

| Exigence | État | Où |
|---|---|---|
| Tests Qt : PKCE, `state`, redirection `127.0.0.1`, rotation du jeton, -32601 | **faits** | `tst_pkce`, `tst_flux_natif`, `tst_session_hermes`, `tst_canal_jsonrpc` |
| Réponse à une question depuis le desktop | **faite, en local** : question posée par le poste simulé, réponse tapée dans le champ de la carte et envoyée par un clic réel sur « Répondre » de la page Questions, relue fermée par l'API | bout en bout local du 02/10/2026 (images `p8` et `rv8p6`), `tst_pages_interactions` |
| `QSettings` sans jeton | **fait** : test du registre de préférences après un parcours complet, contrôle des préférences dans les Diagnostics, export du registre de la portée de test balayé au bout en bout | `tst_reglages_sans_secret`, `tst_diagnostics`, bout en bout |
| Desktop CI verte sur windows-2022 | **faite** à chaque morceau poussé | runs dans `reprise-poste.md` |
| Installeur non signé, dit explicitement | **dit** : aucun certificat ; l'empaquetage à blanc de la CI le produit non signé | `desktop-release-process.md` |
| Connexion réelle à Railway, VM Windows propre | **non faites** : rien n'est déployé, aucune VM sur ce poste | — |

## Décisions appliquées

Le cahier proposait douze décisions (D8-1 à D8-12) ; leurs recommandations sont appliquées,
conformément à la règle « Hermes décide de l'exploitation, le propriétaire fournit les
comptes et tranche l'irréversible » :

| N° | Décision appliquée |
|---|---|
| D8-1 | Qt WebSockets (LGPLv3) ajouté : seule voie native pour `/api/ws` |
| D8-2 | « Mémoriser la connexion » décoché par défaut |
| D8-3 | Déconnexion par `POST /auth/logout` avec le cookie `hermes_session_rt` |
| D8-4 | Veille par le WebSocket interne du kanban, comme simple signal ; sondage gardé |
| D8-5 | Sur 503 au rafraîchissement, le jeton est gardé, jamais effacé automatiquement |
| D8-6 | Routage : validation, relevé et surcharges dans la station ; édition complète dans le navigateur |
| D8-7 | Sauvegarde au format `ACPB1` (DPAPI par morceaux), suppression de l'archive par `DELETE /api/files` |
| D8-8 | Revues de P6 en lecture seule tant que P6 n'est pas fusionnée (levée en P8b : Accepter / Refuser) |
| D8-9 | Discussion sans choix de modèle ni de profil (défaut du profil) |
| D8-10 | Bout en bout local seulement |
| D8-11 | MCP côté exécutant après la fusion de P6, hors de cette branche |
| D8-12 | Binaires non signés tant qu'aucun certificat n'existe, dit partout |

## Écarts au cahier, justifiés

- **MCP côté poste** (volet P8 du plan d'autonomie) : non construit ici ; il dépend des
  fichiers de P6 (`executant/`, `apps/poste`) que cette branche ne modifie pas (D8-11).
- **Flux SSE du greffon** : en P8, la station ne l'ouvrait pas et relisait ses pages par
  sondage ; depuis P8b, elle l'ouvre quand `/v1/meta` l'annonce (voir § « P8b »).
- **Test de contrat des documents de référence** : prévu dans
  `hermes/tests/contrat/test_fixtures_desktop.py` et `image.yml` ; fait à la place dans le
  bout en bout local (lecture en porteur, comparaison de forme de 9 documents), pour ne pas
  toucher `image.yml`, que P6 et P7 modifient aussi. Il n'est donc pas en CI.
- **Quotas** : `SubscriptionQuotasViewModel` (ancienne route) retiré puis réécrit en
  `QuotasViewModel` sur `/v1/quotas`.
- **Demandes de l'agent** : la station ne répond qu'aux demandes des discussions ouvertes
  en elle (section « Demandes de vos discussions ») ; depuis P8b, la file Questions liste
  aussi les discussions en attente de toutes les sessions vivantes (`session.active_list`)
  et « Ouvrir la discussion » les reprend dans la page Discussion, comme le navigateur.
- **`session.close`** : envoyé seulement pour une session sans tour en cours, pour ne
  jamais interrompre un travail de l'agent.
- **Proxy des WebSockets** : ils prennent désormais la même règle que le REST (aucun proxy
  implicite par défaut) ; auparavant forcés sans proxy.
- **Bout en bout** : la station y est un exécutable de test (`acp_desktop_e2e`) qui pilote
  la vraie application, avec un mandataire CONNECT local et Chromium à la place du
  navigateur du système ; le cahier ne précisait pas le mandataire.

## Corrections après relecture (2 octobre 2026)

Seize constats d'une relecture indépendante (exactitude, sécurité, produit), chacun corrigé
avec un test qui échoue sans la correction (témoin de mutation relevé), par petits commits
poussés :

| Constat (gravité) | Correction | Commit |
|---|---|---|
| Texte d'une réponse ou d'une consigne effacé à chaque relecture de 15 s et après un envoi refusé (critique) | listes mises à jour par identifiant (`JsonListModel::setCle`) ; brouillons gardés par la page, effacés seulement après réussite | `7b82c7c` |
| Liste des projets remontée en haut à chaque relecture (moyenne) | même correction | `7b82c7c` |
| Verdict « contrat d'une autre majeure » ou greffon absent non appliqué (haute) | client du greffon **bloqué** : toute route refusée localement, sans rien émettre, sauf `/v1/meta` | `54714ab` |
| Guide d'architecture : empreinte OpenRPC dite coupante (basse) | guide corrigé : seule la version d'information coupe la Discussion | `54714ab` |
| Données d'un autre serveur gardées ; déconnexion sans oubli des pages (moyenne) | `PageViewModel::oublier()` à la session perdue, au changement de serveur et au blocage du greffon | `ee70e9f` |
| Rotation acceptée par Hermes mais refusée par la station : jeton consommé gardé au coffre (moyenne, sécurité) | entrée effacée ; échéance jugée contre l'en-tête `Date` de Hermes | `da7081a` |
| `machine.executant = null` (P6 en place) confondu avec l'étape absente (moyenne) | cinq états exacts (annoncé, aucun connu, non déployé, base illisible, non lu) | `72f2a5b` |
| Liens du navigateur sans le préfixe de chemin du serveur (basse) | liens construits par `ApiClient::resolve` | `ba206b4` |
| Messages réseau anglais de Qt (moyenne) | libellés français fixes par code d'erreur | `4ac1de4` |
| Ctrl+6 à Ctrl+9 sans effet ; copie du rapport par la palette sans effet (moyenne) | un raccourci installé par raccourci déclaré ; rapport réellement copié | `c22c8b9` |
| Preuve de la réponse passant par le ViewModel (basse) | vrais champs et vrais boutons au bout en bout et dans `tst_pages_interactions` | `c22c8b9` |
| Carte « Hermes » de l'accueil jamais relue (moyenne) | `/v1/meta` relu avec la page, carte datée | `9c76c54` |
| « Cancel » dans le dialogue des réglages (basse) | boutons explicites en français | `de46e69` |
| Jauge des quotas inversée par rapport au web (basse) | part utilisée et repère du seuil, comme le web | `1f3696a` |

Preuves : 34 suites, totaux Qt sans échec ni test ignoré ; bout en bout local réussi
(0 écart) contre les images `p8` et `rv8p6` ; Desktop CI et CI vertes (runs dans
[`reprise-poste.md`](../reprise-poste.md), § 6 decies).

## P8b — station alignée sur P7 (8 octobre 2026)

P8 avait été écrite contre P6 ; la relecture finale de P7 avait laissé en limites
(constats desktop-5, desktop-7, desktop-8) les gestes de P7, l'Accueil agrégé, les
compteurs de la file, la visibilité mesurée des dépôts et le flux. La station offre
désormais au PC le même suivi et les mêmes gestes que la page web de P7. Formes et codes de
refus lus dans le code du greffon (`dashboard/plugin_api.py`, `noyau/questions.py`,
`accueil.py`, `flux.py`, `routage.py`, `execution.py`), jamais dans la documentation seule.

| Vue ou geste | Station | Commit |
|---|---|---|
| Routes P6 et P7 du greffon (`ClientGreffonPoste`) | accueil, flux (`Last-Event-ID` seulement pour une révision « n.n »), relance, qui répond, clôture, revues | `ab6d361` |
| File Questions à cinq sections | questions (qui répond, aide chez Hermes), décisions, **revues** (Accepter / Refuser avec motif de 1 à 1 000 caractères), **cartes arrêtées** (Relancer seulement si `relancable`, consigne de 1 à 4 000 caractères, jamais pour une carte d'intégration ; message d'après `relancee`, `branche_neuve`, `session_neuve`), discussions en attente ; refus 409 du greffon dits tels quels ; geste accepté sans effet montré « Attention : », jamais en réussite | `e65c1c1` |
| Détail d'un projet | **Changer qui répond** (projet sur dépôt pas encore fini ; message avec `questions_ouvertes_inchangees`), **Clore le projet** (actif ou en pause, confirmation aux quatre effets, `{confirmation: true}` ; message d'après la réponse) | `d8c1f0a` |
| Accueil agrégé | une lecture de `GET /v1/accueil` (fixture PARTAGÉE lue en place) : à traiter, projets, exécutant (voies fermées `{voie: raison}`), quotas par voie, notifications (test seulement avec un canal), pause générale ; bloc illisible dit avec sa raison | `114cc4e` |
| Badge et barre d'état | « À traiter par vous » d'après `a_traiter.total` de `/v1/accueil` | `5c37c70` |
| Dépôts | carte « Dépôts autorisés » de la page Poste (visibilité MESURÉE, lecture, date, voies ouvertes ou fermées par dépôt, d'après `executant.depots`) ; « Nouveau projet » grise l'exécutant fermé pour le dépôt choisi avec la raison du greffon, ne le retient ni ne l'envoie jamais, part sans exploration si aucun n'est ouvert | `7f42eaa` |
| Flux d'invalidation `GET /v1/flux` | `FluxInvalidation` : ouvert seulement sur l'annonce de `/v1/meta` (chemin et version attendus) et quand une page peut lire ; trame `etat` → temps réel ; `changement` → les pages qui suivent le sujet se relisent (regroupé 300 ms), sinon relecture de sûreté toutes les 2 min (1 min pour les discussions non publiées) ; `fin` → réouverture aussitôt avec `Last-Event-ID` ; chien de garde de 40 s ; reprises 1, 2, 5, 10, 30 s ; trois échecs en 2 min → sondage (15 s) et nouvel essai toutes les 5 min ; 429 jamais avant `Retry-After`. Sujets de chaque page repris de la page web. Barre d'état « Temps réel » / « Sondage… », détail dans les Diagnostics | `13b86db` |
| Discussions en attente | `DiscussionsEnAttente` : `session.active_list` par la passerelle de la station (entrées « waiting » seulement), comptées dans le badge, l'Accueil et la file quand elles sont lues, sinon le total le dit ; liste et « Ouvrir la discussion » dans la file | `eafa969` |
| Bilan quotidien | carte de l'Accueil d'après `GET /api/cron/jobs` (route native) : Actif, En pause, En erreur, Non créé ; prochaine et dernière exécution ; issue seulement si publiée ; « Créer le bilan quotidien (8 h) » (`POST /api/cron/jobs`, offert seulement s'il n'existe pas) ; page Cron dans le navigateur | `787c979` |

Décision **P8b-1** : un 401 du flux n'est jamais réessayé aussitôt ; la station passe en
sondage et retente dans 5 min (la page web, elle, s'arrête et laisse sa lecture suivante
rediriger vers la connexion ; la station n'a pas de page à recharger, et ses lectures REST
font tourner le jeton ou perdent la session, ce qui ferme le flux et oublie le repli : la
session suivante retente aussitôt).

Preuves : 36 suites déclarées à CTest (34 avant P8b ; `tst_flux_invalidation` et
`tst_discussions_attente` ajoutées), totaux Qt relevés à chaque morceau : 0 échec, 0 test
ignoré, en construction incrémentale locale (Release, Qt 6.8.3 msvc2022_64). Vrais clics et
frappes dans `tst_pages_interactions` (relance avec consigne, refus de revue, qui répond,
clôture, option grisée de l'exécutant, page Questions relue au signal du flux dans la
composition réelle, « Ouvrir la discussion »). Fixtures PARTAGÉES lues à leur place
(`hermes/tests/outils/fixtures_accueil/accueil.json`, `fixtures_flux/trames.json`,
`fixtures_poste/depots.json`) ; `desktop-ci.yml` se déclenche aussi sur elles. Chaque
correction a son témoin de mutation (tests rouges relevés, puis code restauré). Desktop CI
et CI vertes sur chaque tête poussée, sauf la Desktop CI de `e65c1c1`, annulée par le push
suivant :

| Commit | Desktop CI | CI |
|---|---|---|
| `ab6d361` | `37797832083` | `37797832021` |
| `e65c1c1` | `37799415760` (annulé) | `37799415793` |
| `d8c1f0a` | `37800559798` | `37800559846` |
| `114cc4e` | `37802314638` | `37802314574` |
| `5c37c70` | `37803549317` | `37803549388` |
| `7f42eaa` | `37826466749` | `37826466620` |
| `13b86db` | `37829503009` | `37829503089` |
| `eafa969` | `37831296270` (36 sur 36) | `37831296274` |
| `787c979` | `37832722859` (36 sur 36) | `37832722925` |
| `4e51efc` | `37833794335` (lancé à la main, 36 sur 36) | `37833112957` |
| `2bce7b8` | `37839494684` (36 sur 36) | `37839494561` |
| `9bec3e5` | `37841198696` (36 sur 36) | `37841198420` |

### Corrections après la relecture de P8b (8 octobre 2026)

Sept constats d'une relecture indépendante, chacun vérifié dans le code avant d'être
corrigé. Chaque constat de code a un test écrit d'abord et relevé rouge sans la correction
(construction incrémentale, puis témoin de mutation pour les cas que le premier échec
masquait) ; suite complète ensuite : 36 suites, 0 échec, 0 test ignoré.

| Constat | Traitement | Preuve |
|---|---|---|
| desktop-1 (moyenne) : un flux déjà ouvert restait ouvert, « Temps réel », après un verdict de `/v1/meta` bloquant le greffon (annonce inchangée) | `FluxInvalidation::setAnnonce` ferme le flux dès que le greffon est bloqué et le dit avec la raison du blocage ; rien ne se rouvre avant un verdict qui le lève | `tst_flux_invalidation` (`greffonBloqueFermeUnFluxOuvert`), `tst_oubli_local` (`fluxSuitLeVerdictApplique`, composition réelle) ; `2bce7b8` |
| desktop-2 : le repli en sondage (401, trois échecs) survivait à la perte de session ; « Temps réel indisponible () » | `oublierRepli()` à la session perdue : la session neuve retente aussitôt ; un repli en cours redit sa raison | `tst_flux_invalidation` (`sessionNeuveOublieLeRepli`) ; `2bce7b8` |
| desktop-3 : un `/v1/meta` injoignable publiait une évaluation vide (flux fermé, « /v1/meta n'a pas encore été lu ») | « Non vérifiable » garde le dernier verdict lu et ce qu'il a lu (annonce du flux, versions, disponibilités, heure de lecture) | `tst_compatibilite_hermes` (`injoignableGardeLeDernierVerdictLu`), `tst_oubli_local` ; `2bce7b8` |
| desktop-4 : « Page relue toutes les 15 (ou 60) secondes » écrit en dur, faux en temps réel | propriété `cadence` de chaque page (sondage principal et état réel du flux), affichée à la place ; l'Accueil dit la cadence de chacune de ses lectures, comme `EtatActualisation` du navigateur | `tst_pages_interactions` (texte de la page Questions en temps réel, cadence des autres pages), `tst_pages_bureau` (texte affiché sur cinq pages) ; `9bec3e5` |
| desktop-5 : le nom accessible de la pastille Questions disait toujours « (discussions non comptées) » | `Streams.descriptionATraiter` suit la lecture des discussions en attente | `tst_pages_interactions` (`pastilleDesQuestionsDitCeQuElleCompte`, nom lu sur la vraie barre de navigation), `tst_discussions_attente` ; `9bec3e5` |
| desktop-6 : « Voies fermées : Aucune » quand aucun exécutant n'est connu (le greffon sert `{}`) | objet vide : rien n'est affiché, comme `CarteExecutant.tsx` ; autre forme : « Inconnu » | `tst_accueil` (`carteExecutant`) ; `9bec3e5` |
| desktop-7 : documentation périmée (`desktop-build.md`, `questions.md`, commentaires de `meta.py`, identifiants renvoyés à un rapport hors du dépôt) | état des preuves et limites réécrits, bout en bout dit non rejoué sur P8b, identifiants des runs ci-dessus ; `autonomie.md` et l'architecture alignées aussi | ce document |

## Non prouvé

- Aucun essai contre Railway ni avec une vraie passkey (rien n'est déployé).
- Navigateur du système réel (Chromium de Playwright le remplace au bout en bout).
- Installation sur un Windows propre ; signature.
- Gestes et lectures de P7 dans la station (P8b) : prouvés contre le faux Hermes, les
  fixtures partagées avec le greffon et le contrat OpenRPC épinglé seulement. Le bout en
  bout local n'a pas été rejoué contre une image de P7 (aucune commande Docker sur ce
  poste) : flux réel derrière uvicorn, relance, clôture, revues, discussions en attente et
  bilan quotidien contre un vrai greffon et un vrai Hermes ne sont pas prouvés.
- Flux derrière le bord Railway (coupure avant 10 min, mise en tampon) et 401 du flux
  (décision P8b-1) : prouvés contre le faux Hermes seulement.
- Cadence affichée par les pages et nom accessible de la pastille Questions : textes lus
  sur les vraies pages QML hors écran ; aucun lecteur d'écran réel n'a été essayé.
- Cartes « Garde d'exécution », « Persona » et « Catalogue » de l'Accueil web (lues de
  `/v1/meta`) : non reprises par la station, qui montre la carte « Hermes ».
- Discussions en attente : seules celles du processus du tableau de bord
  (`session.active_list`) ; les questions posées dans `/chat` en terminal restent
  invisibles, comme dans le navigateur.
- Constats de la relecture finale de P7 corrigés dans la station : voies fermées de
  l'exécutant (objet `{voie: raison}` servi par le greffon, lu comme un tableau : toujours
  « Inconnu ») ; état d'une question d'après `chez` ; aide du plafond de corrections
  (prolongation refusée pour de bon par le greffon) ; titre de la carte de la machine
  d'après l'hôte publié ; textes qui promettaient des gestes « à l'étape P7 » ou
  renvoyaient au kanban de Hermes (qui débloquerait une carte sans les gardes d'ACP).
- Restauration d'une sauvegarde (étape P9) ; seul le déchiffrement à l'identique est prouvé.
- Durée réelle de la session chez Authelia (7 jours, fenêtre glissante supposée).
- Garde de transition du blocage du greffon (pages oubliées seulement au passage au
  blocage) : défensive ; son témoin ne boucle pas, le sondage se reprogrammant à 15 s.
- Écart d'horloge réel entre un poste et Railway : prouvé contre le faux Hermes (horloge du
  poste avancée de 2 h) et l'en-tête `Date` d'uvicorn au bout en bout local, pas sur Railway.
- Une réponse de `/auth/native/token` refusée par la station pour une autre raison que
  l'horloge (fournisseur, identité, type de jeton) laisse chez Authelia la session émise :
  aucune révocation n'est tentée.
- Avant le premier verdict de `/v1/meta` d'une session, les pages peuvent LIRE le greffon ;
  le blocage s'applique dès le verdict, et aucune écriture ne part sans geste.

## Commits

`530aa37`, `13f2428`, `b727da6`, `e216d6b`, `0543ae9`, `8d18f87`, `14b58f3`, `9761693`,
`3f7e56d`, `ed3735d`, `fc6c6e2`, `1987a84` (première partie : fondations) ; `22a2d90`,
`83101cf`, `22e4c42`, `9c44b7a`, `039aadb`, `857baae` (seconde partie : JSON-RPC, temps réel,
Accueil, Projets, Questions, Discussion) ; `6a068a5`, `b748194`, `b3b9e0f`, `75a73f6`,
`834a920`, `bfccf52`, `c66bc0b`, `aaf4242`, `1b28374`, `b68f645` et la documentation (troisième
partie : Poste, Quotas, Routage, Sauvegarde, Diagnostics, bout en bout) ; `7b82c7c`,
`54714ab`, `ee70e9f`, `da7081a`, `72f2a5b`, `ba206b4`, `4ac1de4`, `c22c8b9`, `9c76c54`,
`de46e69`, `1f3696a` et la documentation (corrections après relecture). P8b : `ab6d361`,
`e65c1c1`, `d8c1f0a`, `114cc4e`, `5c37c70`, `7f42eaa`, `13b86db`, `eafa969`, `787c979` et la
documentation. Aucun `Co-Authored-By`.
