# Architecture de la station de travail native (C++23 / Qt 6 / Qt Quick)

Date de rédaction : 18 septembre 2026, Europe/Paris
Branche : `feat/desktop-qt-railway`
Version du produit : `0.9.0` (fichier `VERSION` de la racine, lu par CMake)
Périmètre décrit : `apps/desktop/` dans son intégralité.

Ce document s'appuie sur `docs/desktop-railway-audit.md` comme source de vérité pour tout
ce qui concerne l'API, ses modes d'authentification, le contrat SSE et les limites du
produit. Quand il cite un fait de l'API, il cite l'audit ; quand il tranche, il dit
pourquoi.

---

## 0. Ce qui n'a pas été compilé — à lire avant tout le reste

**Aucune ligne de code natif décrite dans ce document n'a été compilée, liée ou
exécutée.** Aucun test n'a été lancé. Aucune fenêtre n'a été rendue. Aucune couleur n'a
été observée à l'écran.

Le relevé de la chaîne d'outils du poste, exécuté le 18 septembre 2026 (audit, section
11.1), donne : `qmake`/`qmake6` absent, `cmake` absent, `ninja` absent, `cl` et `msbuild`
absents, `gcc`/`g++`/`clang` absents. Seuls Python 3.13.3 et Node 22.15.0 sont présents.

Conséquences, énoncées une fois et valables pour tout le document :

| Affirmation | Statut |
|---|---|
| « Le code compile » | **Non prouvé.** Jamais tenté. |
| « Les tests passent » | **Non prouvé.** Jamais exécutés. |
| « L'interface s'affiche » | **Non prouvé.** Aucune scène rendue. |
| « Les contrastes tiennent à l'écran » | **Non prouvé.** Calculés sur paires de couleurs, jamais observés. |
| « Le flux SSE se reprend après coupure » | **Non prouvé.** Aucune coupure réelle éprouvée. |
| « Le coffre Windows fonctionne » | **Non prouvé.** Aucun appel à `CredWriteW` exécuté. |
| Cohérence des chemins et des URI de modules | **Vérifié localement** par `apps/desktop/cmake/check_layout.py`. |
| Validité JSON des jetons et fraîcheur de leur projection QML | **Vérifié localement.** |
| Absence de secret, de chemin absolu, d'origine codée en dur, de fin de ligne CRLF | **Vérifié localement.** |

La **seule** preuve de compilation recevable viendra d'un job d'intégration continue
Windows qui configure, compile et exécute `ctest`. Ce job **n'existe pas** : l'audit
constate que `.github/workflows/ci.yml` « ne contient rien de natif : pas de runner
Windows, pas de CMake, pas de MSVC, pas de Qt, pas de `ctest` » (section 6.2, point 6).
Tant qu'il n'existe pas, tout ce répertoire est **du texte non vérifié**.

---

## 1. Partage des responsabilités : C++ contre QML

La règle est unique et sans exception :

> **Le C++ décide. QML montre.**

Concrètement :

| Responsabilité | Où | Pourquoi là |
|---|---|---|
| Transport HTTP, cookies, jeton CSRF, réessai | C++ (`src/api/`) | Un secret ne doit jamais traverser vers la scène graphique, et la politique de réessai doit être éprouvable sans interface. |
| États de session et transitions | C++ (`src/auth/`) | Une machine à états dispersée dans des liaisons QML est indéboguable et intestable. |
| Analyse SSE, curseurs, reconnexion | C++ (`src/events/`) | La confusion des curseurs est le défaut le plus coûteux du protocole ; elle se prévient par des types, pas par de la vigilance. |
| Coffre de secrets | C++ (`src/storage/`) | Appels système, et surtout : rien ne doit être exposable depuis QML. |
| Disponibilité d'une action | C++ (`src/commands/`) | Un seul calcul de disponibilité alimente le bouton, le raccourci et la palette. |
| Composition visuelle, animations, mise en page | QML (`qml/`) | C'est ce que QML fait le mieux, et la présentation évolue plus vite que la logique. |
| Choix du thème appliqué | C++ (`SystemAppearance`), **appliqué** par QML (`ThemeBridge`) | La préférence et le thème système sont des faits du poste ; leur projection sur les singletons est une opération de scène. |

### Ce que QML ne peut pas atteindre

Vérifiable en lisant les propriétés déclarées dans les en-têtes :

- le mot de passe n'est **jamais** stocké : `AuthManager::logIn()` le transmet et le
  champ QML est vidé immédiatement après l'envoi ;
- le jeton CSRF n'est **pas** une propriété : `ApiClient` n'expose que
  `hasCsrfToken` (booléen) ;
- le cookie de session n'est **pas** exposé : `SessionCookieJar` publie
  `hasSessionCookie()` et `cookieCount()`, jamais une valeur ;
- le corps brut d'une erreur (`ApiError::body()`) n'est **pas** une `Q_PROPERTY`, pour
  qu'il ne traverse pas par inadvertance ;
- aucun objet C++ n'est instancié depuis QML : les services sont enregistrés comme
  **singletons d'instance**, et les énumérations comme types **non instanciables**.

---

## 2. Modules Qt retenus, et pourquoi chacun

`find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2 Network)`

| Module | Ce qu'il apporte ici | Pourrait-on s'en passer ? |
|---|---|---|
| **Core** | `QObject`, `QString`, `QJsonDocument`, `QTimer`, `QSettings`, `QUuid`, `QRegularExpression` | Non. |
| **Gui** | `QGuiApplication` ; `QStyleHints::colorScheme()` pour suivre le thème système | Non : requis par Quick, et seul moyen portable de lire le thème système. |
| **Qml** | moteur, `qmlRegisterSingletonInstance`, `qmlRegisterUncreatableType`, `QQmlApplicationEngine` | Non. |
| **Quick** | scène graphique déclarative, `TapHandler`, `HoverHandler`, `ListView` | Non. |
| **QuickControls2** | `ApplicationWindow`, `SplitView`, `ToolTip`, `CheckBox`, `TextEdit` du style `Basic` | `SplitView` et `ToolTip` n'ont pas d'équivalent raisonnable à réécrire. |
| **Network** | `QNetworkAccessManager`, `QNetworkCookieJar`, `QNetworkReply` lu au fil de l'eau pour le SSE | Non. |

### Modules volontairement absents

- **Widgets** : aucune fenêtre classique n'est employée ; l'inclure alourdirait le paquet
  et changerait le comportement de `QTEST_MAIN`.
- **WebEngine / WebView** : interdits par le cahier des charges. L'audit explique aussi
  pourquoi ce n'est pas qu'une question de goût : « la règle web "aucun contenu
  d'artefact rendu dans l'origine de la plateforme" est une parade au XSS de navigateur.
  En natif, il n'y a plus d'origine, mais il y a un décodeur d'image ou de vidéo exposé à
  un fichier produit par un agent » (section 10.3).
- **Charts, Data Visualization, Virtual Keyboard** : non utilisés. Ils ne sont pas
  publiés sous LGPL dans l'offre open source, ce qui les rendrait incompatibles avec une
  distribution binaire propriétaire. Aucun n'est lié, et aucun graphique n'est dessiné :
  l'étude de direction artistique note d'ailleurs qu'« aucune palette de visualisation de
  données n'a été décidée » — elle n'est donc pas inventée ici.
- **Concurrent**, **Sql**, **Multimedia** : aucun besoin.

### Licence — ce qui est su, et ce qui ne l'est pas

Les six modules retenus sont des modules **essentiels** de Qt. Qt les publie sous LGPLv3
ou sous licence commerciale. Une distribution binaire sous LGPLv3 impose, d'après la page
d'obligations de Qt (consultée le 18 septembre 2026,
<https://www.qt.io/licensing/open-source-lgpl-obligations>) :

- la **liaison dynamique** de Qt, faute de quoi l'application elle-même serait couverte ;
- la fourniture du code source complet de la bibliothèque employée, ou une offre écrite ;
- la possibilité pour l'utilisateur de **modifier et relier** la bibliothèque, ce qui
  interdit un binaire verrouillé ;
- la remise du texte de la LGPL et la mention de son usage.

Aucune liaison statique de Qt n'est configurée dans `CMakeLists.txt`, et les modules
statiques déclarés par `qt_add_qml_module` sont les modules **de ce produit**, pas Qt.

**Ce qui n'est pas su** : la page d'obligations n'énumère pas les modules GPL-seulement ;
elle renvoie à la page des fonctionnalités de Qt. Le classement de Charts, Data
Visualization et Virtual Keyboard rapporté ci-dessus **n'a pas été vérifié sur une page
officielle** au moment de la rédaction — il est donné comme la raison de ne pas les
utiliser, pas comme un fait établi. Aucune validation juridique n'a eu lieu pour ce
produit, et la question de la licence Qt reste explicitement ouverte (audit, question 18).

---

## 3. Version unique

`VERSION` à la racine du dépôt est la **seule** source. `apps/desktop/cmake/AcpVersion.cmake`
le lit, refuse une valeur mal formée, en fait une dépendance de configuration, et la
projette dans `src/app/BuildConfig.h.in`. Aucun numéro n'est saisi deux fois.

L'audit demandait exactement cela : « `scripts/check_version.py` devra couvrir la version
du desktop, sans quoi le client dérivera silencieusement de `VERSION` » (section 6.3,
point 7). Ce lot ne modifie pas `scripts/check_version.py` — c'est hors de son périmètre —
mais il rend la couverture triviale : il n'y a aucune constante à comparer, seulement la
lecture de `VERSION` par CMake.

---

## 4. Modèle de threads

**Tout vit sur le fil d'interface, et rien ne le bloque.** C'est un choix, pas une
facilité.

Justification : la totalité des entrées-sorties de cette station est du réseau asynchrone.
`QNetworkAccessManager` est non bloquant par construction : `get()` rend immédiatement un
`QNetworkReply`, et les données arrivent par `readyRead()`. Aucun appel synchrone
(`waitForReadyRead`, `QEventLoop` imbriqué, `QThread::msleep`) n'apparaît dans le code.

| Travail | Fil | Justification |
|---|---|---|
| Requêtes HTTP courtes | interface, asynchrone | Aucune attente ; la réponse arrive par signal. |
| Flux SSE | interface, asynchrone | `readyRead()` livre des fragments ; l'analyseur est incrémental et traite quelques kilooctets au plus. |
| Analyse JSON d'un événement | interface | Un `StreamEvent` est petit. Si un jour une charge le rendait sensible, la parade est de déplacer l'analyse, pas d'ajouter un fil partout. |
| Coffre Windows (`CredWriteW`) | interface | Appel local au gestionnaire d'identifiants, de l'ordre de la milliseconde. |
| Lecture et écriture de `QSettings` | interface | Quelques valeurs scalaires. |

**Ce qui interdirait ce modèle et n'existe pas ici** : téléchargement d'un livrable
volumineux, vérification d'empreinte SHA-256 sur plusieurs mégaoctets, décodage d'image
produit par un agent. Ces trois usages viendront avec les écrans de la bibliothèque ; ils
devront alors être portés par un fil dédié, et ce document devra être mis à jour. Les
écrire aujourd'hui sur le fil d'interface serait une dette, pas un raccourci.

**Ce qui n'est pas prouvé** : rien de ce modèle n'a été observé en exécution. L'absence de
blocage est établie par lecture du code et par les garanties documentées de Qt, pas par
une mesure.

---

## 5. Gestion d'état

### 5.1 Où vit l'état

- **État serveur** : nulle part en cache durable. La station lit, elle ne réplique pas.
  L'audit pose la question ouverte « le desktop stocke-t-il des données hors ligne ? »
  (question 13) ; tant qu'elle n'est pas tranchée, la réponse de cette fondation est
  **non**, et c'est dit plutôt que contourné.
- **État de session** : `AuthManager`, six états explicites — déconnecté, en cours,
  connecté, expiré, révoqué, hors ligne. Aucun état implicite.
- **État de lien** : `HealthService`, cinq états — inconnu, vérification, en ligne,
  dégradé, hors ligne. « Inconnu » est l'état initial, jamais « en ligne ».
- **État de flux** : un `StreamSubscription` par portée, sept états publiés.
- **Préférences** : `SettingsStore`, avec une **liste blanche de clés** appliquée à
  l'exécution. Une clé hors liste est refusée. C'est ce qui empêche `QSettings` de
  devenir, un jour, un coffre par accident.

### 5.2 Les deux espaces de curseurs

C'est le point le plus dangereux du protocole, et l'audit le dit ainsi : les deux curseurs
« voyagent dans le même champ SSE `id:` et sont deux entiers indiscernables. Rien, au
niveau du protocole, n'empêche de réutiliser l'un pour l'autre ; un client qui le fait
saute ou rejoue des événements **sans aucune erreur visible** » (section 4.1).

La parade est dans le langage, pas dans la vigilance :

- `api/Cursors.h` définit `RunCursor` et `ProjectCursor`, tous deux à constructeur
  **explicite**, sans conversion mutuelle, sans comparaison croisée. Quatre `static_assert`
  fixent ces propriétés à la compilation ;
- `events/StreamScope.h` définit `RunScope` et `ProjectScope`, qui **embarquent** leur
  curseur. Une portée sait donc construire ses propres chemins — `/streams/runs/{id}`
  contre `/streams/projects/{id}`, `/runs/{id}/events` contre `/projects/{id}/events` —
  et il n'existe aucune fonction prenant un identifiant et un entier nus ;
- `advanceScopeCursor()` est le **seul** point où un entier redevient un curseur, et il
  construit le type correspondant à la portée. Il refuse aussi de reculer.

### 5.3 Séquence de flux, telle que l'audit l'impose

1. **Rattrapage** — `StreamSubscription::requestJournalPage()` lit la route paginée de la
   portée jusqu'à `has_more == false`, en retenant `next_cursor`. Un événement dépourvu de
   `sequence` — ligne antérieure au Lot E — lève `journalHasGaps`, que l'interface doit
   montrer : « une base ancienne montre des trous, que l'interface doit présenter
   honnêtement plutôt que masquer » (audit, limite 9).
2. **Ouverture** — `Last-Event-ID` est posé quand l'analyseur en détient un ; `after_seq`
   est envoyé en plus, au cas où une passerelle absorberait l'en-tête.
3. **Consommation** — `acp.event` est rendu tel quel ; `acp.stream.rotate` reconnecte au
   curseur **porté par la trame** ; `acp.stream.closed` **arrête** l'abonnement et
   l'annonce — une fermeture de flux n'est pas un arrêt de mission, et `reason=unauthorized`
   est traité comme une déconnexion, pas comme une erreur réseau.
4. **Coupure** — aucune mutation n'est jamais rejouée. Ce n'est pas seulement une règle :
   `EventStreamService` **n'émet structurellement aucune méthode non sûre**. Il ne peut
   pas relancer une mission.
5. **Multiplexage** — une connexion par portée, réutilisée par tous les panneaux. Au-delà
   de la borne annoncée, l'abonnement est refusé **localement**, avec un message français,
   plutôt que d'aller chercher un 429 qui bloquerait ensuite cinq secondes.

### 5.4 Fermeture propre, et pourquoi elle est obligatoire

« La libération du jeton dépend d'un bloc `finally` sur le générateur : un flux que le
client n'a pas fermé proprement reste compté jusqu'à 900 s » (audit, section 4.3).
`Application::shutdown()` ferme donc tous les flux **avant** toute autre opération, et
`ShellViewModel` les ferme dès qu'une session est perdue.

### 5.5 Bornes : annoncées ou supposées, et la différence est affichée

`StreamLimits` porte les valeurs relevées par l'audit (4 connexions, 15 s de keep-alive,
900 s de durée maximale, 400 ms de pas d'interrogation, 500 par page). Dès que le point
d'entrée de compatibilité les annonce, elles sont **remplacées**. `limitsAreAnnounced()`
distingue les deux cas, et l'écran de diagnostics affiche « Valeurs relevées lors de
l'audit, non annoncées » quand c'est le cas. Une hypothèse n'est jamais présentée comme un
fait.

---

## 6. Transport : ce que `ApiClient` garantit

| Garantie | Mise en œuvre | Fait d'API qui l'impose |
|---|---|---|
| URL de base configurable, jamais codée en dur | `setBaseUrl()` ; refus explicite tant qu'elle est absente | « Aucun domaine n'est décidé » (audit, 5.2) |
| HTTPS imposé | schéma refusé sauf `https`, ou `http` sur bouclage avec accord explicite | Question ouverte 14 : à trancher explicitement, pas en repli silencieux |
| Un seul pot de cookies, partagé avec les flux longs | `SessionCookieJar` porté par l'unique `QNetworkAccessManager` | « Si le pot n'est pas partagé, les routes SSE répondront 401 pendant que le reste fonctionne » (10.3) |
| `X-CSRF-Token` sur les seules méthodes non sûres et non publiques | `startAttempt()` | `require_csrf` (`deps.py:48-68`) |
| Appel rotatif du jeton CSRF strictement sérialisé | `sendCsrfRotating()` : un seul en vol, les mutations attendent | « Deux appels concurrents à `GET /auth/session` produisent des 403 sporadiques » (10.3) |
| Réessai sémantique | `plannedAttempts()` / `shouldRetry()` | « Une mission relancée deux fois est un dégât réel » (10.3) |
| Aucune redirection suivie | `ManualRedirectPolicy` ; une 3xx devient `InvalidResponse` | `follow_redirects=False` côté CLI (`client.py:83-104`) |
| Aucun proxy implicite | `QNetworkProxy::NoProxy` par défaut | `trust_env=False` côté CLI |
| Délai calibré pour un hébergement distant | 20 s par défaut | « 8 000 ms côté web… produira de faux hors ligne » (10.3) |
| Erreurs typées avec message français | `ApiError`, quinze familles, titres distincts | Doctrine : refus explicites en français |

### La politique de réessai, énoncée sans ambiguïté

- méthode **sûre** (GET, HEAD, OPTIONS) : jusqu'à trois tentatives ;
- méthode **non sûre avec** clé d'idempotence : jusqu'à trois tentatives, parce que le
  serveur reconnaît le rejeu et refuse un corps différent ;
- méthode **non sûre sans** clé : **exactement une**. Aucune exception, aucun drapeau
  pour la contourner. `tst_api_errors.cpp` l'inscrit comme un test.

Le recul est exponentiel avec gigue, et `Retry-After` prime toujours sur le calcul.

---

## 7. Sécurité

### 7.1 Coffre de secrets

`CredentialVault` est une abstraction à deux implémentations :

- **Windows** — gestionnaire d'identifiants du système, via `CredWriteW`, `CredReadW`,
  `CredDeleteW` et `CredFree` (en-tête `wincred.h`, bibliothèque `Advapi32.lib`). Type
  `CRED_TYPE_GENERIC`, persistance `CRED_PERSIST_LOCAL_MACHINE` — l'entrée survit à la
  fermeture de session, reste visible des seules sessions du même utilisateur sur cette
  machine, et n'est pas itinérante. `CRED_PERSIST_ENTERPRISE` est écarté : un secret de
  station n'a pas à suivre l'utilisateur d'un poste à l'autre. La taille est bornée à
  `CRED_MAX_CREDENTIAL_BLOB_SIZE`, soit 5 × 512 = 2560 octets, et le dépassement est
  refusé **avant** l'appel ;
- **partout ailleurs** — `RefusingCredentialVault`, qui **refuse** de stocker et le dit en
  français. Il n'écrit nulle part. Un secret non mémorisé oblige à ressaisir un mot de
  passe ; un secret écrit en clair oblige à changer de mot de passe, et à ne pas savoir
  qui l'a lu.

Interdits tenus : ni `QSettings`, ni JSON, ni fichier d'environnement, ni QML, ni base non
chiffrée, ni journal, ni Git. `SettingsStore` applique en plus une liste blanche de clés,
pour que la porte reste fermée dans le temps.

### 7.2 Expurgation

`diagnostics/Redaction.h` filtre le paramètre `token=` d'une URL, les en-têtes
`X-CSRF-Token`, `X-ACP-Bootstrap-Token`, `X-Worker-Registration-Token`, `Authorization`,
`Cookie` et `Set-Cookie`, le cookie `acp_session` et les champs JSON sensibles. Il est
installé comme **gestionnaire de messages Qt** dans `main.cpp` : tout ce qui sort par
`qDebug`, `qWarning` ou `qCritical` y passe. Le rapport de diagnostic y passe aussi.

Motif : « le jeton de téléchargement voyage en paramètre de requête. Un filtre de
journalisation existe côté serveur ; **rien** ne protège les journaux, les rapports de
plantage et les fichiers de diagnostic du poste client » (audit, 10.3).

**Limite assumée, et inscrite dans les tests** : le filtre reconnaît des **formes**
connues, pas un secret quelconque dans un texte quelconque. La vraie garantie est qu'aucun
secret n'est passé à la journalisation ; le filtre est une défense en profondeur.

### 7.3 Contenus produits par des agents

La politique web « aucun contenu d'artefact rendu dans l'origine de la plateforme » est une
parade au XSS de navigateur ; en natif la menace change de nature. Cette fondation ne
décode **aucun** contenu produit par un agent : ni image, ni vidéo, ni document, ni fichier
de skill. Quand les écrans de la bibliothèque viendront, la politique devra être
**repensée**, pas recopiée — et surtout pas relâchée.

### 7.4 Ce qui reste hors de portée du client

Le cookie de session est `HttpOnly` : la station ne le lit jamais, elle le porte. Sa valeur
n'existe que dans le pot de cookies en mémoire. **Cette fondation ne persiste pas la
session** : au lancement, `AuthManager::resumeSession()` constate l'absence de cookie et
retourne immédiatement en « Déconnecté », sans appel réseau. Persister le cookie de session
dans le coffre est possible et sera un lot ultérieur ; le faire aujourd'hui sans l'avoir
conçu et documenté serait précisément le genre de raccourci que ce document refuse.

---

## 8. Interface : ce que la coquille garantit

- **Aucune donnée inventée.** « Inconnu », « Non configuré », « Hors ligne »,
  « Chargement », « Erreur », « Vide » sont des valeurs légitimes et affichées telles
  quelles. La barre basse affiche « Runs actifs : Inconnu » parce qu'aucune route consommée
  par cette fondation ne les compte.
- **Aucun bouton qui fait semblant.** Un bouton relié à une commande tire sa disponibilité
  du registre ; désactivé, il reste **lisible** (`text.muted`, jamais plus pâle) et porte sa
  raison en infobulle. Le champ de recherche globale est présent, désactivé, et dit
  qu'aucune route de recherche n'existe côté serveur.
- **Aucune destination masquée.** Les écrans non livrés apparaissent dans la navigation,
  désactivés, avec leur explication. `NavigationModel` **refuse** de naviguer vers eux et
  émet la raison, que la barre basse affiche.
- **La couleur n'est jamais seule.** Chaque état porte un libellé français, un nom de
  glyphe et un repli ASCII ; trois états — inconnu, non configuré, hors ligne — ajoutent
  une bordure pointillée. `StatusChip` expose le repli ASCII à `Accessible.name`.
- **Clavier.** `Ctrl+K` ouvre la palette, `Ctrl+1` et `Ctrl+2` naviguent, `Ctrl+R` sonde le
  serveur, `Échap` ferme la palette. Tous exécutent des **commandes du registre**, jamais
  une action câblée : la disponibilité est calculée au même endroit que pour un bouton.
  L'anneau de focus n'est jamais supprimé.
- **Mouvement.** Aucune transition ne dépasse 240 ms. Le survol et le redimensionnement de
  volet sont instantanés. Le seul mouvement en boucle est la pulsation de « En cours », et
  le profil réduit la remplace par le libellé et un glyphe fixe.

### Jetons de design

`apps/desktop/cmake/generate_design_tokens.py` transforme `design/tokens/*.json` en sept
singletons QML du module `Acp.Design`. La sortie est **versionnée** ; la cible CMake
`acp_check_design_tokens` échoue si elle est périmée. Aucune couleur, aucune taille, aucune
durée n'est recopiée à la main dans un fichier QML — `check_layout.py` le vérifie
indirectement en contrôlant que tout fichier `pragma Singleton` est bien marqué
`QT_QML_SINGLETON_TYPE`, et le générateur refuse tout jeton hors contrat.

### Modules QML

Un module par répertoire, un URI par module :

| URI | Répertoire | Contenu |
|---|---|---|
| `Acp.Design` | `qml/theme/generated` | Sept singletons **engendrés** |
| `Acp.Theme` | `qml/theme` | `ThemeBridge` : applique le thème aux singletons |
| `Acp.Controls` | `qml/controls` | Bouton, bouton à glyphe, champ de saisie |
| `Acp.Components` | `qml/components` | Pastille d'état, état vide, en-tête, ligne clé/valeur |
| `Acp.Pages` | `qml/pages` | Première ouverture, accueil, diagnostics |
| `Acp.Station` | `qml/shell` | Barres, navigation, zone de travail, inspecteur, palette |
| `Acp.Desktop` | `qml` | `App.qml` seul |
| `Acp.Runtime` | — | Types C++, enregistrés **impérativement** |

C'est plus verbeux qu'un module unique à sous-répertoires, mais sans ambiguïté : chaque
`import` désigne exactement un répertoire du dépôt, et `check_layout.py` vérifie que tout
`import Acp.*` correspond à un URI réellement déclaré.

`Acp.Runtime` est enregistré par `Application::registerQmlTypes()` avec
`qmlRegisterSingletonInstance` et `qmlRegisterUncreatableType`, et non par des macros
`QML_ELEMENT`. **Raison** : les macros exigent que le fichier appartienne aux `SOURCES` d'un
`qt_add_qml_module`, ce qui rendrait `acp_core` dépendant du module QML ; les cibles de test
pourraient alors difficilement lier la logique sans embarquer la scène. **Prix assumé** :
`qmllint` n'a pas d'informations de type sur ces objets.

---

## 9. Tests

Huit exécutables Qt Test et un exécutable Qt Quick Test. **Aucun n'a été compilé ni
exécuté.**

| Cible | Ce qu'elle éprouve |
|---|---|
| `tst_sse_parser` | Coupure de fragment en tout point, CRLF coupé en deux, UTF-8 multi-octets coupé, BOM, trois terminateurs de ligne, commentaire `: ping`, données multilignes, une seule espace retirée, `id` avec U+0000 rejeté, identifiant persistant, bloc tronqué abandonné, trames `rotate` et `closed`. |
| `tst_api_errors` | Correspondance code HTTP → famille, `detail` FastAPI simple et de validation, corps illisible, titres français distincts, **réessai jamais accordé à une mutation sans clé**, `Retry-After` prioritaire, validation de clé d'idempotence. |
| `tst_cursors` | Chemins construits par portée, clés d'abonnement qui ne collisionnent jamais, curseur qui n'avance que vers l'avant, portée conservée. |
| `tst_command_registry` | Refus des doublons et des commandes incomplètes, **commande indisponible jamais exécutée**, réévaluation au changement de contexte, commandes indisponibles restant visibles, cohérence de la table d'index après retrait. |
| `tst_session_state` | Refus du HTTP en clair hors bouclage, purge de la session au changement de serveur, reprise sans cookie **sans appel réseau**, libellés d'états distincts, présence du cookie sans divulgation de valeur. |
| `tst_compatibility` | Comparaison de versions, **absence du point d'entrée ≠ compatible**, bornes par défaut égales aux valeurs de l'audit, capacité inconnue distinguée de capacité désactivée, seule une incompatibilité de version est bloquante. |
| `tst_redaction` | Jeton signé, en-têtes, cookie de session, champs JSON ; et la **limite** du filtre, inscrite comme un test. |
| `tst_backoff` | Doublement jusqu'au plafond, gigue bornée, remise à zéro, absence de débordement après soixante échecs. |
| `tst_qml_shell` | `tst_status_chip.qml` : libellé et repli ASCII pour les dix états, bordure pointillée des trois états sans mesure, seul « en cours » animé. `tst_design_tokens.qml` : bascule de thème atteignant tous les singletons, résolution des états serveur, rôles typographiques complets, aucune transition au-dessus de 240 ms, profil réduit sans déplacement. |

Ce que les tests **ne** couvrent **pas**, et il faut le dire : aucun test de transport
réel, aucun serveur simulé, aucune coupure réseau, aucun rendu observé. `ApiClient` et
`EventStreamService` ne sont éprouvés que sur leurs décisions prises **avant** tout envoi.
Un simulateur de serveur HTTP local est le complément nécessaire, et il n'est pas livré ici.

---

## 10. Ce qui manque et qui bloquera

1. **Le job d'intégration continue Windows.** Sans lui, rien de ce répertoire n'est
   vérifié. C'est une dépendance de la fondation, pas un raffinement ultérieur.
2. **Le point d'entrée de compatibilité côté serveur.** `CompatibilityService` sonde
   `/meta`, `/capabilities` puis `/version` et gère proprement leur absence, mais tant
   qu'aucun n'existe la station ne connaît ni la version du contrat, ni les bornes réelles,
   ni les capacités calculées.
3. **La version de Qt épinglée et son provisionnement en CI.** Le projet épingle tout le
   reste ; Qt doit l'être aussi. Rien n'est décidé (audit, question 17).
4. **La décision de licence Qt**, qui commande le format du paquet et la liaison.
5. **Le certificat de signature de code Windows** : délai d'approvisionnement externe.
6. **La persistance de session**, à concevoir avant d'être implémentée.
7. **Un simulateur de serveur** pour éprouver le transport et la reprise SSE.

---

## 11. Sources officielles consultées

Toutes consultées le **18 septembre 2026**.

| Source | Ce qui en a été tiré |
|---|---|
| <https://doc.qt.io/qt-6/qt-add-qml-module.html> | Signature de `qt_add_qml_module` ; règle des singletons (`pragma Singleton` **et** `QT_QML_SINGLETON_TYPE`) ; préfixe de ressource `/qt/qml/` sous QTP0001 ; chemin de ressource déterminé par le chemin relatif à `CMAKE_CURRENT_SOURCE_DIR` ; `qmldir` de sous-répertoire depuis Qt 6.8 sous QTP0004. |
| <https://doc.qt.io/qt-6/qt-standard-project-setup.html> | Signature, arguments `REQUIRES` et `SUPPORTS_UP_TO`, effets (`CMAKE_AUTOMOC`, `GNUInstallDirs`, RPATH) ; introduit en Qt 6.3. |
| <https://doc.qt.io/qt-6/qnetworkaccessmanager.html> | Signatures de `get`, `post`, `put`, `deleteResource`, `sendCustomRequest`, `setCookieJar` (**le gestionnaire prend la propriété du pot**), `setAutoDeleteReplies`, `setTransferTimeout`. |
| <https://doc.qt.io/qt-6/qnetworkcookiejar.html> | `cookiesForUrl`, `setCookiesFromUrl`, `insertCookie`, `updateCookie`, `deleteCookie` sont **virtuelles** ; `allCookies` et `setAllCookies` sont **protégées** — d'où leur élargissement dans `SessionCookieJar`. |
| <https://doc.qt.io/qt-6/qnetworkrequest.html> | `setTransferTimeout(int)` et la surcharge `std::chrono::milliseconds` depuis Qt 6.7 ; défaut de 30 000 ms ; `RedirectPolicyAttribute` ; `HttpStatusCodeAttribute`. |
| <https://doc.qt.io/qt-6/qtest-overview.html> | Motif CMake d'un test Qt : `find_package(Qt6 COMPONENTS Test)`, `enable_testing()`, `qt_add_executable`, `add_test`, liaison à `Qt::Test`. |
| <https://doc.qt.io/qt-6/qtquicktest-index.html> | `QUICK_TEST_MAIN` et `QUICK_TEST_MAIN_WITH_SETUP` ; composants `QuickTest` et `Qml` ; `QUICK_TEST_SOURCE_DIR` ; balayage récursif des fichiers `tst_*.qml` ; rappels `applicationAvailable()` et `qmlEngineAvailable()`. |
| <https://doc.qt.io/qt-6/qtqml-cppintegration-definetypes.html> | Rôles de `QML_ELEMENT`, `QML_NAMED_ELEMENT`, `QML_SINGLETON`, `QML_UNCREATABLE`, `QML_ANONYMOUS` ; instances de singleton possédées par le moteur. |
| <https://doc.qt.io/qt-6/qqmlengine-obsolete.html> | Confirmation que `qmlRegisterSingletonInstance` **n'est pas obsolète** en Qt 6 (seuls `importPlugin()` et `urlInterceptor()` le sont). |
| <https://html.spec.whatwg.org/multipage/server-sent-events.html> | Algorithme « interpreting an event stream » : terminateurs CRLF / LF / CR, retrait du BOM, ligne de commentaire, découpe au premier deux-points, retrait d'**une** espace, accumulation de `data`, rejet d'un `id` contenant U+0000, `retry` uniquement numérique, non-dispatch si le tampon de données est vide, retrait du saut de ligne final, persistance de l'identifiant. |
| <https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew> | Signature `BOOL CredWriteW(PCREDENTIALW, DWORD)` ; en-tête `wincred.h` ; bibliothèque `Advapi32.lib` ; erreurs `ERROR_NO_SUCH_LOGON_SESSION`, `ERROR_INVALID_PARAMETER`, `ERROR_INVALID_FLAGS`, `ERROR_BAD_USERNAME`, `ERROR_NOT_FOUND`. |
| <https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw> | Champs de `CREDENTIALW` ; `CRED_TYPE_GENERIC` = 1 ; `CRED_PERSIST_SESSION` = 1, `CRED_PERSIST_LOCAL_MACHINE` = 2, `CRED_PERSIST_ENTERPRISE` = 3 ; `CRED_MAX_CREDENTIAL_BLOB_SIZE` = 5 × 512 ; `CRED_MAX_GENERIC_TARGET_NAME_LENGTH` = 32767 ; `CredentialBlob` sans caractère nul final ; `UserName` ignoré pour `CRED_TYPE_GENERIC`. |
| <https://www.qt.io/licensing/open-source-lgpl-obligations> | Obligations LGPLv3 pour une distribution binaire : liaison dynamique, fourniture du source ou offre écrite, possibilité de relier, remise du texte de licence. La page **n'énumère pas** les modules GPL-seulement et renvoie à la page des fonctionnalités. |

Sources internes au dépôt : `docs/desktop-railway-audit.md` (surface d'API, modes
d'authentification, contrat SSE, bornes, limites, questions ouvertes),
`docs/design-reference-study.md` (direction artistique, règles de densité, d'états vides et
d'erreurs), `design/tokens/*.json` (jetons et leur bloc `$qml`),
`apps/cli/src/acp_cli/client.py` (modèle de transport non-navigateur déjà en production),
`packages/contracts/src/acp_contracts/events.py` (`StreamEvent`, `EventPage`,
`EVENT_SCHEMA_VERSION`).

---

## 12. Ce que ce document ne prouve pas

Il décrit du code **écrit**, pas du code **éprouvé**. Il ne prouve pas que la station
compile, ni qu'elle démarre, ni qu'elle affiche quoi que ce soit, ni qu'elle parle
correctement à l'API — aucun serveur n'a été contacté depuis un client Qt, aucun client Qt
n'existant. Il ne prouve pas que les valeurs de densité sont lisibles à l'écran, ni que le
repli de police tient quand `Inter` est absente. Il ne prouve pas que le coffre Windows
accepte les entrées décrites, ni que `CRED_PERSIST_LOCAL_MACHINE` se comporte comme
documenté sur les postes visés. Il ne prouve pas que les flux SSE tiennent derrière la
passerelle d'un hébergeur, ni qu'une coupure réseau réelle est correctement reprise. Toutes
les mentions « à vérifier », « inconnu » ou « non décidé » de ce document doivent être
traitées comme des tâches, pas comme des réserves de style.
