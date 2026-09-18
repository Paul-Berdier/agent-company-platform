# Modèle de sécurité du client desktop — conception

Date d'état : 18 septembre 2026, Europe/Paris. Branche `feat/desktop-qt-railway`,
version du produit `0.9.0`.

## Ce que ce document est, et n'est pas

Une **conception**, écrite avant le code. `apps/desktop` n'existe pas, aucune ligne de
C++ ni de QML n'a été écrite dans ce lot, et rien n'a été compilé : ce poste ne
dispose ni de Qt, ni de CMake, ni de compilateur C++
(`docs/desktop-railway-audit.md` §11). Aucune affirmation d'exécution n'est faite.

Les faits serveur cités viennent de la lecture du code de cette branche. Le client
CLI (`apps/cli`) sert de référence exécutable : c'est déjà un client non-navigateur en
production, et son transport est le modèle à reproduire
(`apps/cli/src/acp_cli/client.py:83-104`).

---

## 1. Session et jeton anti-rejeu

### 1.1 Ce que le serveur impose

Il n'existe **aucun bearer utilisateur, aucune clé d'API personnelle, aucun OAuth**.
L'authentification humaine passe par un seul mécanisme : le cookie `acp_session`,
`HttpOnly`, `SameSite=strict`, `Secure` conditionné par `ACP_SESSION_COOKIE_SECURE`
(`apps/api/src/acp_api/security.py:137-146`). Les deux routes SSE ne lisent que ce
cookie (`routers/streams.py:86` et `:112`).

Sur `POST`, `PUT`, `PATCH` et `DELETE`, l'en-tête `X-CSRF-Token` est **obligatoire**
et son absence donne un 403 « Requête refusée » (`deps.py:48-68`). Ce n'est pas une
protection de navigateur : c'est un contrôle serveur, que le client natif doit
satisfaire comme le CLI le fait déjà.

### 1.2 Règles du client

1. **Un seul jeton CSRF pour tout le processus.** `GET /auth/session` fait **tourner**
   le jeton (`routers/auth.py:137`). Deux appels concurrents produisent des 403
   sporadiques, indiscernables d'un vrai refus de droits. L'appel qui renouvelle le
   jeton est donc strictement sérialisé, en un seul point du code, et le jeton est
   injecté par l'intercepteur réseau — jamais recopié par un écran.
2. **Un seul pot de cookies**, partagé entre les requêtes courtes et les flux longs.
   Un pot séparé donnerait des 401 sur les seules routes SSE pendant que le reste de
   l'application fonctionne : c'est le mode de panne le plus coûteux à diagnostiquer.
3. **Aucune prolongation silencieuse.** `expires_at` est figé à la création
   (`security.py:90`), avec 43 200 s (12 h) par défaut, et `GET /auth/session` ne met
   à jour que `last_seen_at`. Le client affiche donc une échéance honnête et
   **verrouille** l'interface à l'expiration ; il ne se reconnecte jamais tout seul
   avec un identifiant mémorisé.
4. **Une fermeture de flux n'est pas une déconnexion.** Une trame
   `acp.stream.closed` avec `reason=unauthorized` est une révocation de session ou
   d'appartenance et doit conduire à l'écran de connexion ; une coupure réseau conduit
   à une reprise par curseur. Les deux ne se confondent pas.

### 1.3 Discipline de transport, reprise du CLI

`trust_env=False` — **aucun proxy implicite**, aucune variable d'environnement ne
détourne le trafic. `follow_redirects=False` — une redirection est un refus, pas un
chemin. Délai explicite et généreux : le CLI est à 20 s, le web à 8 000 ms, et
l'audit note que ce dernier produira de faux « hors ligne » contre un hébergement
distant à démarrage à froid (`docs/desktop-railway-audit.md` §10.3). Le desktop
retient l'ordre de grandeur du CLI.

---

## 2. Coffre d'identifiants du système

| Donnée | Où elle vit | Où elle ne vit jamais |
| --- | --- | --- |
| Cookie `acp_session` | Coffre d'identifiants du système d'exploitation | `QSettings`, un JSON, une base non chiffrée, QML, un journal, Git |
| Jeton CSRF | Mémoire du processus uniquement, jamais écrit | Partout ailleurs |
| Jeton d'amorçage (`X-ACP-Bootstrap-Token`) | **Nulle part** : saisi dans un champ masqué, utilisé, oublié | Toute forme de persistance, y compris « se souvenir de moi » |
| Valeur d'un secret du coffre serveur | Mémoire du processus, le temps de l'envoi | argv, journal, cache disque, rapport de plantage, presse-papiers persistant |
| Jeton signé de livrable (`?token=`) | Mémoire, le temps du téléchargement | Journal, historique d'URL, rapport de diagnostic |
| URL du serveur, identifiant de connexion | Préférences locales du poste | — (ce ne sont pas des secrets) |

Deux remarques qui ne sont pas des détails :

- **Le coffre serveur ne renvoie jamais une valeur** (`routers/secrets.py`). Le
  desktop ne détient donc aucun secret de plateforme ; il n'en manipule un que
  pendant la fraction de seconde d'une création ou d'une rotation.
- **Le serveur expurge déjà le paramètre `token` de son propre journal d'accès**
  (`apps/api/src/acp_api/access_logging.py`). **Rien ne protège les journaux, les
  rapports de plantage et les fichiers de diagnostic du poste client.** C'est au
  client de faire cette expurgation à la source, pas au moment de l'affichage.

---

## 3. Ce qui ne doit jamais atteindre QML

QML est une surface de script : toute propriété exposée au moteur devient lisible par
tout ce qui s'y exécute, apparaît dans un inspecteur d'objets et peut se retrouver
dans une capture d'état ou un rapport de plantage. Règle :

- **La couche C++ expose des états et des identifiants opaques, jamais des
  identifiants d'authentification.** Le cookie, le jeton CSRF, le jeton d'amorçage, un
  jeton signé de livrable et une valeur de secret ne sont jamais des propriétés d'un
  modèle, jamais des arguments de signal, jamais des champs de contexte.
- **Le réseau ne se fait pas depuis QML.** Aucun composant QML n'ouvre de connexion :
  il demande une action à un objet C++, qui décide seul quelle requête part et avec
  quels en-têtes. C'est ce qui rend l'intercepteur unique du §1.2 possible.
- **Un champ de saisie de secret est masqué, ne propose pas de complétion, ne passe
  pas par le presse-papiers persistant, et n'est jamais restauré à la réouverture de
  la fenêtre.**
- **Les fichiers de skills ne sont jamais rendus en riche.** Le serveur les sert en
  texte brut, explicitement jamais rendus (`docs/desktop-railway-audit.md` §3.3). Un
  composant de rendu riche réintroduirait le risque que le serveur a écarté.
- **Le contenu d'un livrable est une donnée produite par un agent.** En natif il n'y a
  plus d'origine web, mais il y a un décodeur d'image ou de vidéo exposé à un fichier
  hostile. La politique doit être repensée, pas recopiée du web : ouverture par
  l'application du système après téléchargement et vérification d'empreinte, plutôt
  que décodage dans le processus de l'application.

---

## 4. Journalisation

Catégories `QLoggingCategory`, désactivées au niveau `debug` par défaut :

| Catégorie | Contenu autorisé | Interdit absolu |
| --- | --- | --- |
| `acp.net` | Méthode, chemin **sans chaîne de requête**, code de statut, durée, taille | En-têtes, cookies, corps, `?token=`, `X-CSRF-Token` |
| `acp.sse` | Portée, type de trame, **valeur du curseur**, motif de `rotate` et de `closed`, tentative de reconnexion | Contenu des événements, cookie |
| `acp.auth` | Transitions d'état (connecté, expiré, verrouillé, révoqué), horodatage d'expiration | Identifiant de connexion, mot de passe, cookie, jeton CSRF, jeton d'amorçage |
| `acp.update` | Version locale, version distante, canal, verdict d'empreinte | Contenu du paquet, chemin temporaire complet |
| `acp.store` | Clé de préférence écrite, succès ou échec | Valeur d'une entrée du coffre |
| `acp.ui` | Écran ouvert, action déclenchée | Toute donnée métier saisie |
| `acp.exec` | Identifiant de tentative, code de sortie, durée, troncature de sortie | Environnement transmis, contenu de sortie non borné |

Règles transverses :

- **Aucune chaîne de requête n'est journalisée**, jamais, sur aucune catégorie : c'est
  la seule règle qui protège le jeton signé de livrable de façon fiable.
- **Le journal est local, borné et rotatif.** Il n'est jamais envoyé automatiquement.
- **Un rapport de diagnostic est un acte volontaire** : son contenu est affiché
  intégralement avant tout envoi, et il ne contient ni coffre, ni cookie, ni chaîne de
  requête. Aucun envoi automatique de rapport de plantage.

---

## 5. Surface réseau

Le client n'ouvre de connexion que vers :

1. **l'origine de l'API**, saisie par l'utilisateur et mémorisée ;
2. **l'API des publications GitHub**, uniquement si la vérification de mise à jour a
   été acceptée (`docs/desktop-update-process.md`).

Et vers rien d'autre. En particulier **jamais** vers `event-service`, **jamais** vers
`provider-gateway`, **jamais** vers la base de données : ce sont des règles
d'architecture posées par l'audit (§2.2), pas des recommandations.

Discipline :

- **HTTPS obligatoire hors bouclage.** C'est déjà la règle que le serveur applique à
  ses propres origines (`packages/contracts/src/acp_contracts/service_urls.py:63-66` :
  « doit utiliser HTTPS hors loopback »). Le client l'applique à l'URL saisie.
  L'acceptation d'un HTTP en bouclage, pour une pile locale, doit être un choix
  explicite et visible, pas un repli silencieux — c'est une question ouverte de
  l'audit (§10.4, question 14).
- **Validation de certificat obligatoire**, sans exception, sans « ignorer cette
  fois ». Aucune épingle de certificat n'est prévue : l'hébergeur renouvelle les
  siens.
- **Aucune redirection suivie**, aucun proxy implicite (§1.3).
- **Au plus une connexion SSE par portée réellement affichée**, réutilisée par tous
  les panneaux. La borne serveur est de **4 flux simultanés par utilisateur**, un
  dépassement donnant un 429 avec `Retry-After: 5` (`streams.py:99`,
  `routers/streams.py:62-68`). La libération dépend d'un bloc `finally` : **un flux
  mal fermé reste compté jusqu'à 900 s**. La fermeture propre est donc une exigence
  de sécurité de service, pas une élégance.
- **Aucune mutation rejouée à la reconnexion.** La reprise se fait par curseur de
  lecture. Une mission relancée deux fois est un dégât réel.

---

## 6. Mises à jour

Le détail est dans `docs/desktop-update-process.md`. Les invariants de sécurité, en
une ligne chacun :

- vérification **sur consentement**, jamais automatique au premier lancement ;
- **empreinte SHA-256 obligatoire**, recalculée par le client, comparée en temps
  constant ; divergence ⇒ abandon et suppression du fichier ;
- **signature vérifiée dès qu'elle existera**, et affichage honnête « Paquet non
  signé » tant qu'aucun certificat n'existe ;
- **aucune installation silencieuse**, aucune élévation de privilèges, aucune
  exécution d'un binaire non décrit par le manifeste de la publication interrogée ;
- le manifeste et les notes de version sont des **données affichées**, jamais des
  instructions.

---

## 7. Exécuteur local — le cas particulier

Un jour, la station pourra exécuter un processus sur le poste. Ce jour-là, les règles
ci-dessous s'appliquent. Elles reprennent celles déjà en vigueur dans le worker
(`apps/worker/src/acp_worker/local_runner.py`), qui est la seule implémentation
éprouvée du dépôt.

1. **Désactivé par défaut.** L'activation est un acte explicite, par projet, avec un
   indicateur permanent dans l'interface. Aucune mise à jour du client ne peut
   l'activer.
2. **Racines autorisées explicites.** L'exécution n'a lieu que sous une racine de
   travail déclarée par l'utilisateur. Le chemin est canonisé, puis vérifié comme
   descendant de cette racine ; un lien symbolique qui en sort est un refus. Le worker
   applique déjà ce contrôle (`local_runner.py:452` : « le répertoire de tentative
   sort de la racine des runs »).
3. **Jamais la racine d'un disque**, jamais le dossier personnel nu, jamais le dossier
   d'installation du client, jamais un dossier système. Une racine refusée est refusée
   avec sa raison, pas corrigée en silence.
4. **L'exécutable ne vit pas dans la racine inscriptible des runs.** Sinon une
   tentative pourrait déposer le binaire qu'une autre exécutera. Le worker refuse déjà
   ce cas (`local_runner.py:128-139`).
5. **Le serveur ne choisit jamais la commande.** Une charge utile de mission qui
   contient un champ de commande (`argv`, `command`, `executable`, `shell`…) est
   refusée : c'est exactement ce que fait `_task_requests_command`
   (`local_runner.py:462-474`). Le client natif hérite de cette règle sans
   négociation.
6. **Jamais de shell.** Un tableau d'arguments, jamais une chaîne interprétée.
7. **Environnement sur liste blanche**, et **jamais** les secrets de plateforme. Le
   worker interdit nommément `ACP_BOOTSTRAP_TOKEN`, `ACP_EVENT_SERVICE_TOKEN`,
   `ACP_GATEWAY_SERVICE_TOKEN`, `ACP_WORKER_REGISTRATION_TOKEN`, `HERMES_API_KEY` et
   `HERMES_SERVICE_TOKEN` (`local_runner.py`, `_FORBIDDEN_PLATFORM_ENVIRONMENT`). Le
   cookie de session du desktop rejoint cette liste.
8. **Délai et sortie bornés**, arbre de processus terminé à l'arrêt, sortie tronquée
   avec mention explicite de la troncature.
9. **Aucune preuve fabriquée.** Si l'exécution n'a pas eu lieu, l'interface dit
   « Non exécuté », pas « Réussi ».

---

## 8. Ce que ce document ne prouve pas

Il ne prouve rien d'exécuté. Aucun client Qt n'existe, donc **le couple cookie +
jeton CSRF n'a jamais été éprouvé depuis un client Qt**, les flux SSE n'ont jamais été
éprouvés derrière la passerelle d'un hébergeur ni contre une coupure réseau réelle, et
aucun exécuteur local desktop n'a été écrit. Les règles ci-dessus sont dérivées du
code serveur, du CLI et du worker de cette branche, lus le 18 septembre 2026 ; leur
respect devra être vérifié par des tests natifs, qui n'existent pas encore et dont la
seule preuve possible viendra d'un job d'intégration continue Windows
(`docs/desktop-railway-audit.md` §11.2).
