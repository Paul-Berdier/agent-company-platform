# Architecture du client desktop natif (station de travail)

État du 2 octobre 2026, version **0.11.0**, refonte « Hermes au centre », étape **P8**
(branche `refonte/hermes-p8`, fusionnée dans `refonte/hermes` par la PR #20, `b715edb`, le
2 octobre 2026), complété par l'étape **P8b**, station alignée sur P7 (branche
`refonte/hermes-p8b`, fusionnée par la PR #22, `8583642`, le 9 octobre 2026 ;
[`refonte/desktop.md`](refonte/desktop.md), § « P8b »). Cahier de l'étape et journal d'avancement :
voir [l'historique de la refonte](refonte/historique.md), partie B, § 6 decies. Le client d'avant la refonte
(cookie `acp_session`, ancienne API ACP) reste consultable sous l'étiquette
`archive/acp-0.10.0-avant-hermes`.

## Rôle et frontière

La station est un client natif **C++23, Qt 6.8.3 et QML** (Qt Quick, contrôles Basic
habillés par les jetons du produit). Elle n'embarque ni Electron, ni Tauri, ni Chromium,
ni Qt WebEngine, ni WebView.

Elle ne parle **qu'au Hermes du propriétaire**, par ses API :

| Surface | Routes | Authentification |
|---|---|---|
| Connexion native (RFC 8252) | `GET /auth/native/authorize` (navigateur), `POST /auth/native/token`, `POST /auth/native/refresh`, `POST /auth/logout` | publiques ; jeton de rafraîchissement dans le corps, cookie seulement pour la déconnexion |
| Santé | `GET /api/health`, `GET /api/status` | publiques |
| Tableau de bord | `GET /api/auth/me`, `POST /api/auth/ws-ticket`, `POST /api/ops/backup`, `GET /api/actions/backup/status`, `GET /api/ops/backup/download`, `DELETE /api/files` | porteur |
| JSON-RPC | `wss://…/api/ws` (contrat épinglé `hermes/contrat/gateway-contract.openrpc.json`) | ticket à usage unique en sous-protocole |
| Veille du kanban | `wss://…/api/plugins/kanban/events` | ticket en sous-protocole |
| Greffon `acp-poste` | `/api/plugins/acp-poste/v1/*` (méta, projets, questions, triage, poste, routage, quotas, pause) | porteur |

Elle ne parle **jamais** au fournisseur d'identité (Authelia) : seul le navigateur du
système le fait pendant la connexion. Le bout en bout local le prouve (aucune connexion de
la station vers `identite-acp.test`). Elle ne touche ni le poste Windows, ni les fichiers,
la base ou les secrets du serveur. Le seul autre transport est `UpdateService` (GitHub, à
la demande, sans identifiant ACP).

## Couches

| Couche | Code | Responsabilité |
|---|---|---|
| Assemblage | `src/app/Application.*`, `GardeInstance.*` | composition des services, singletons QML (`Acp.Runtime`), commandes, instance unique (code de sortie 3) |
| Connexion | `src/auth/` : `PairePkce`, `EcouteurBouclage`, `NativeAuthFlow`, `JetonsHermes`, `SessionHermes` | flux RFC 8252, jetons, rotation, déconnexion, états de session |
| Transport REST | `src/api/` : `ApiClient`, `ApiError`, `ClientGreffonPoste`, `IdempotencyKey` | porteur, réémission après rafraîchissement, trois formes d'erreur, routes du greffon |
| JSON-RPC | `src/gateway/` : `JsonRpcChannel`, `GatewayClient`, `DemandesAgent`, `DiscussionsEnAttente` | canal sans réseau testable seul, passerelle `/api/ws`, demandes `approval`/`clarify`, discussions en attente (`session.active_list`) |
| Temps réel | `src/events/` : `EventStreamService`, `Sondage`, `FluxInvalidation`, `VeilleKanban`, `Backoff`, `SseParser` | sondages, flux d'invalidation du greffon (`GET /v1/flux`), invalidation par le kanban, état des sources |
| Services | `src/services/` : `CompatibiliteHermes`, `HealthService`, `TelechargementFlux`, `UpdateService` | `/v1/meta`, santé du lien, lecture en flux, mises à jour |
| Stockage | `src/storage/` : `WindowsCredentialVault`, `JetonsCoffre`, `SettingsStore`, `ChiffrementSauvegarde` | coffre Windows, préférences sans secret et leur contrôle, sauvegarde `ACPB1` |
| Métier | `src/viewmodels/`, `src/models/JsonListModel.*` | une `PageViewModel` par page, libellés français (`Libelles`) |
| Présentation | `qml/pages`, `qml/shell`, `qml/components`, `qml/controls`, `qml/theme` | pages, coquille, composants, jetons générés depuis `design/tokens/` |
| Distribution | `packaging/windows/`, `scripts/*desktop.ps1` | compilation, tests, archive portable et installeur |

QML ne construit aucun client réseau et ne reçoit aucun secret : ni jeton, ni ticket, ni
vérificateur PKCE, ni état (seule exception assumée : le code d'enrôlement du poste,
affiché une fois et effacé en quittant la page ou à la perte de session).

## Connexion native (RFC 8252)

1. Prérequis lus sans session : `/api/health` (`auth_required` exigé) et la liste des
   fournisseurs (`self-hosted` choisi explicitement).
2. Paire PKCE (vérificateur de 64 octets aléatoires, défi S256) et état de 32 octets,
   effacés à la fin du flux quelle qu'elle soit.
3. Écouteur `QTcpServer` sur **127.0.0.1** (jamais `localhost` ni `::1`), port éphémère,
   chemin `/rappel`, 600 s au plus ; un état différent ou absent abandonne le flux ; la
   page rendue est statique (`Content-Security-Policy: default-src 'none'`) et ne recopie
   aucun paramètre.
4. Navigateur du système sur `/auth/native/authorize` ; « Copier le lien » s'il ne
   s'ouvre pas (le lien ne contient ni code ni vérificateur).
5. Échange `POST /auth/native/token {code, code_verifier}`, contrôles du type, du
   fournisseur et de l'échéance, puis identité par `/api/auth/me`.

**Rotation.** `POST /auth/native/refresh` : le nouveau jeton de rafraîchissement est
écrit au coffre **avant** le signal de session renouvelée ; un seul rafraîchissement en
vol ; 401 `session_expired` efface l'entrée ; 503 (fournisseur injoignable ou jeton
rejoué, indiscernables) garde le jeton et réessaie avec recul, jamais d'effacement
automatique. Une seule station par session Windows (verrou), pour ne jamais rejouer le
même jeton.

**Déconnexion.** `POST /auth/logout` avec l'en-tête `Cookie: hermes_session_rt=…` (la
route par laquelle Hermes révoque chez le fournisseur ; 302 attendu), puis coffre vidé,
jetons effacés, WebSockets fermés, sondages arrêtés, discussion et demandes oubliées.

## Porteur, erreurs, compatibilité

`ApiClient` pose `Authorization: Bearer` au moment de chaque tentative puis efface sa
copie ; un 401 de la porte de Hermes déclenche un rafraîchissement et une seule
réémission (mutation comprise) ; un 401 du greffon n'est jamais réémis. Écritures en
JSON, plafond de 64 Kio ; aucune redirection suivie ; aucun cookie hors déconnexion ;
aucun proxy implicite, et la même règle pour les WebSockets. `ApiError` lit les trois
formes de refus (porte, greffon, table de routage) et traduit les messages fixes connus
de Hermes ; un message inconnu est rendu tel quel.

`CompatibiliteHermes` lit `/v1/meta` : contrat `acp-poste/1` exigé ; une autre majeure,
ou un `/v1/meta` en 404 (greffon absent), **bloque le client du greffon** :
`ClientGreffonPoste` refuse alors toute lecture et toute écriture sans rien émettre, avec
l'explication du verdict, et seul `/v1/meta` reste lisible pour revérifier (seules la
Discussion et les Diagnostics restent utilisables). Contrat JSON-RPC : une **version
d'information** (`openrpc.info_version`) différente de celle épinglée coupe la
Discussion ; une **empreinte** différente ne donne qu'un avertissement, la Discussion
restant ouverte. Hermes testé (`hermes/contrat/HERMES_VERSION`, 0.21.5) : une autre version
avertit. Alertes publiées telles quelles ; l'exécutant de l'étape P6 seulement s'il est
annoncé. L'étape P7 se détecte de même, par la clé `accueil` (née dans le même commit du
greffon que `/v1/accueil`, la relance, « qui répond » et la clôture) : sans elle, l'Accueil
agrégé et le sondage léger ne lisent rien, « Qui répond » et « Clore » ne sont pas offerts,
la page et le badge disent « Non disponible sur ce serveur », et le client du greffon refuse
ces quatre routes sans rien émettre (décision P8b-2, D159 du [plan](refonte/plan.md) § 1 ; [`refonte/desktop.md`](refonte/desktop.md)).

## JSON-RPC et temps réel

`GatewayClient` demande un ticket (`/api/auth/ws-ticket`, porteur), ouvre
`wss://<serveur>/api/ws` avec les sous-protocoles `hermes-gateway-v1` et
`hermes-gateway-ticket.<ticket>` (le ticket ne passe jamais dans l'URL) et **sans en-tête
Origin** ; attend `gateway.ready`, rejoue `session.events.since` après une coupure ;
4401 ⇒ un nouveau ticket, 4403 ⇒ refus définitif. `JsonRpcChannel` répond **-32601** à
toute requête serveur sans gestionnaire (`secret`, `sudo`, méthode inconnue), répond
aux demandes `approval` et `clarify` avec le même identifiant et seulement par les choix
offerts, bat toutes les 15 s (échéance 45 s), n'en rejoue aucune requête.

`EventStreamService` : sondage des pages affichées, seulement fenêtre non réduite et
session ouverte ; sondage léger de `GET /v1/accueil` pour la barre d'état et le badge
(60 s, seulement sur l'annonce de l'étape P7) ;
`VeilleKanban` suit le tableau du projet ouvert (`since=latest_event_id`, regroupement
d'1 s) et déclenche une relecture du détail. `FluxInvalidation` (étape P8b) ouvre le flux
d'invalidation du greffon (`GET /v1/flux`) quand `/v1/meta` l'annonce : chaque page
(`Sondage::suivre`) se relit au signal de SES sujets (les mêmes que la page web), regroupé
sur 300 ms, et ne garde en temps réel qu'une relecture de sûreté (2 min) ; hors temps réel,
son sondage habituel : 15 s pour les pages, 60 s pour la page Quotas, pour le détail d'un
projet tant que la veille du kanban est prête et pour le sondage léger du badge et de la
barre d'état. Chien de garde de 40 s, reprise avec `Last-Event-ID`, repli
en sondage après trois échecs en 2 min, nouvel essai toutes les 5 min ; la perte de session
oublie ce repli. Le flux suit le verdict APPLIQUÉ de `/v1/meta` : un verdict qui bloque le
greffon le ferme, même déjà ouvert, et se dit avec sa raison (« Aucun flux (greffon
bloqué) » : ses pages ne lisent rien), quelle que soit l'annonce ; un `/v1/meta` injoignable
garde le dernier verdict lu, et le flux. Chaque page affiche sa cadence réelle (propriété
`cadence` de son ViewModel), jamais une cadence écrite en dur.

## Pages

| Route | Page | Ce qu'elle fait |
|---|---|---|
| `home` | Accueil | Accueil agrégé `GET /v1/accueil`, lu seulement sur l'annonce de l'étape P7 (sinon « Non disponible sur ce serveur ») : à traiter par vous (discussions en attente comprises quand elles sont lues), projets en cours, exécutant, quotas par voie, notifications (test), bilan quotidien (tâche cron native, création), pause générale avec confirmation ; sessions récentes ; carte Hermes |
| `projects` | Projets | liste, détail (cartes dans l'ordre du graphe, journal, carte entière), pause et reprise, qui répond, clôture, nouveau projet (mêmes règles que la page web, exécutant fermé pour le dépôt grisé, clé d'idempotence gardée après un refus), kanban dans le navigateur |
| `questions` | Questions | file à cinq sections : questions (répondre, 1 à 4 000 caractères), décisions construites depuis `actions`, revues (accepter, refuser avec motif), cartes arrêtées (relancer avec consigne), discussions en attente (ouvrir) ; demandes de l'agent des discussions ouvertes |
| `chat` | Discussion | sessions (« En attente d'une réponse » marqué d'après `session.active_list`, comme le navigateur ; état illisible dit), transcription, tour en flux, outils sans arguments ni sortie bruts, demandes `approval`/`clarify` |
| `station` | Poste | enrôlement (code affiché une fois), empreinte, révocation, relevé, inventaire, dépôts (visibilité mesurée, voies par dépôt), alertes, exécutant P6 s'il est annoncé |
| `quotas` | Quotas | voies, compteurs, fenêtres ; jauge seulement sur une part restante servie |
| `routing` | Routage | table par classe, brouillon, validation, relevé de secours, surcharges ; édition complète dans le navigateur |
| `diagnostics` | Diagnostics | versions, lien, session, compatibilité, passerelle et compteurs, temps réel, coffre, contrôle des préférences ; rapport copiable expurgé |
| `backup` | Sauvegarde | export chiffré (ci-dessous) et déchiffrement pour une restauration |
| `settings` | Réglages | thème, mouvement, mémorisation, déconnexion |

`office` (bureau de département) reste hors périmètre, visible et jamais navigable.
Chaque valeur jamais lue dit « Inconnu » ou « Non configuré » ; aucun geste ne fait
semblant.

## Sauvegarde chiffrée

`POST /api/ops/backup` puis suivi de `/api/actions/backup/status` toutes les 2 s (30 min
au plus) ; l'archive est lue en flux (`TelechargementFlux`, statut 200 seul livré,
plafond 4 Gio) et **chiffrée au fil de l'eau** par DPAPI pour l'utilisateur Windows
courant, au format `ACPB1` : en-tête (`ACPB1`, version, identifiant d'export de 16 octets
aléatoires), puis des morceaux de 1 Mio, chacun avec son drapeau final et sa longueur ;
l'entropie de chaque bloc lie l'identifiant, le rang et le drapeau, si bien qu'un morceau
déplacé, retiré, rejoué d'une autre sauvegarde ou tronqué est refusé au déchiffrement.
`QSaveFile` : un échec, une annulation ou une perte de session ne laissent aucun fichier.
Puis `DELETE /api/files {path}` retire l'archive en clair du volume ; un refus est dit
avec le chemin restant. L'archive contient `.env` et `auth.json` : la page le dit, et
dit que le fichier chiffré est lié au profil Windows.

## Tests et preuves

- **36 suites** déclarées à CTest (Qt Test et Qt Quick Test), totaux Qt relevés en local :
  0 échec, 0 ignoré (la Desktop CI ne relève que le compte de CTest, qui range un `QSKIP`
  parmi les réussites). Le banc `tests/cpp/support/FauxHermes` sert HTTP et WebSocket sur le
  même port de bouclage (flux natif, rotation, passerelle, kanban, routes du greffon, flux
  d'invalidation en `text/event-stream`).
- **Desktop CI** sur `windows-2022` : compilation Release (`/W4 /WX`), suites, empaquetage
  à blanc ; installeur **non signé** (aucun certificat), et dit tel quel.
- **Bout en bout local** (`scripts/e2e-desktop-windows.ps1`, jamais en CI) contre la pile
  de test (vrai Authelia, Hermes de test, bord TLS) : connexion native par Chromium et
  passkey virtuelle, rotation, discussion JSON-RPC, projet lancé et **question répondue
  depuis la station**, veille du kanban, sauvegarde, reprise de session au redémarrage,
  déconnexion, hygiène, et forme des documents de référence comparée à l'image. Détail et
  chiffres : [`docs/desktop-build.md`](desktop-build.md), § 12. Relevé de P8 (2 octobre
  2026), non rejoué sur P8b.

## Limites connues

- Rien n'est déployé : aucun essai contre Railway ni avec une vraie passkey.
- Le jeton de rafraîchissement rejoué après la déconnexion obtient **503** (Authelia
  rend 500 pour un jeton révoqué) : indiscernable d'une panne, d'où la règle « 503 garde
  le jeton ».
- Les gestes et lectures de P7 (flux, relance, clôture, revues, discussions en attente,
  bilan quotidien) ne sont prouvés que contre le faux Hermes et les fixtures partagées :
  le bout en bout local n'a pas été rejoué contre une image de P7.
- Installation sur un Windows propre et signature : non faites.
- Face à un greffon antérieur à P7, la station ne reprend pas l'Accueil de P8 (projets et
  quotas lus séparément) : elle le dit « Non disponible sur ce serveur » et renvoie aux
  pages ; prouvé contre le faux Hermes seulement.
