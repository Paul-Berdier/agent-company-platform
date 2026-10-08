# Plan de refonte « Hermes au centre »

> Copie de référence du plan validé par le propriétaire, « Plan de refonte Hermes (corrigé après contre-vérification) »,
> recopiée dans le dépôt le 24 septembre 2026 pour qu'elle survive au brouillon de
> session où elle a été rédigée (page de synthèse privée :
> https://claude.ai/artifact/BrteQn6AwYSJ5TgW7Fkri8).
>
> Les sections 2 à 15 reprennent le plan mot pour mot ; seule la mise en forme
> Markdown (titres, listes) est ajoutée. Les références `fichier:ligne` désignent le
> clone de Hermes Agent au tag v2026.9.24 (commit f97608f), le modèle Railway lu
> localement ou l'étiquette `archive/acp-0.10.0-avant-hermes` (60a49b6).
>
> **Les décisions du propriétaire (section 1) priment sur le texte du plan** partout
> où ils divergent. La section 15 garde les recommandations d'origine pour mémoire.
>
> Depuis le 25 septembre 2026, les phases **P4 à P8** sont **remplacées** par le plan
> d'autonomie ([autonomie.md](autonomie.md)) : leur texte d'origine reste ci-dessous pour
> mémoire, chacune précédée d'un renvoi (seul ajout aux sections 2 à 15).

## 1. Décisions du propriétaire (font foi)

- **Connexion au tableau de bord : OIDC auto-hébergé** (fournisseur `self_hosted` de
  Hermes), **et non Nous Portal**. Le flux natif RFC 8252 du desktop fonctionne avec
  lui (vérifié dans `hermes_cli/dashboard_auth/routes.py:232-275`). Hermes ne tient
  aucune liste blanche : le fournisseur d'identité devra n'accepter que le
  propriétaire. Le choix du fournisseur d'identité se fait en P2.
- **Cerveau de Hermes : abonnement ChatGPT** (fournisseur `openai-codex`).
- **Rien n'est encore déployé sur Railway** : aucune migration de données.
- **Railway** : offre Hobby, 2 Go, plafond de dépense de 30 $ par mois, région
  Europe, **sans domaine personnalisé au départ**.
- **Approbations manuelles** (`approvals.mode: manual`).
- **Publication** : branche `refonte/hermes`, ouverte en **0.11.0** ; une PR par étape,
  de `refonte/hermes-pN` vers `refonte/hermes` ; étiquette **1.0.0** seulement à la
  fusion finale dans `main`.

### Conséquences sur la lecture du plan

- Là où le plan écrit « Nous », « Portail Nous », « Nous Portal », `provider=nous`,
  `HERMES_DASHBOARD_OAUTH_CLIENT_ID`/`HERMES_DASHBOARD_PORTAL_URL` ou désactive
  `dashboard_auth/self_hosted`, il faut lire le fournisseur `self_hosted` (OIDC). Le
  principe du plan est conservé : un seul fournisseur d'authentification actif,
  verrouillé par la managed scope contre toute substitution par l'agent, le fournisseur
  `basic` jamais exposé sur Internet. Les clés exactes à épingler pour `self_hosted`
  seront relevées dans le source épinglé en P1 et P2, pas supposées ici.
- Le refus d'un second compte, prouvé en P2, porte sur le fournisseur d'identité
  retenu, puisque Hermes ne filtre pas lui-même les comptes.
- Les passages sur la migration du déploiement Railway existant (préalable de la
  thèse, A13, partie Railway « Point de départ » et « Migration », livrables et
  preuves de migration de P2, risque « Migration du déploiement existant »,
  recommandation « Migration du Hermes déjà déployé ») sont **sans objet** : P2 est
  un premier déploiement, sur un volume neuf.
- Sans domaine personnalisé, le tableau de bord vit sur un sous-domaine
  `up.railway.app` : la passkey de P7 est liée à ce sous-domaine, et un renommage du
  service l'invaliderait (limite déjà notée par le plan, section Web, page `/poste`).

### Décisions du 25 septembre 2026 (étape P2)

- **Aucun outil d'exécution pour l'agent sur Railway** : ni terminal, ni fichiers, ni exécution de
  code, ni navigateur, ni cron, ni délégation, ni connexions. Trois couches : listes d'outils de la
  managed scope, épingles du `.env` géré, garde `pre_tool_call` en liste blanche (24 outils) dans
  `acp-poste`. `kanban_create` et `kanban_attach_url` sont retirés à l'agent en P2 (les projets
  passeront par les outils du greffon). `web_extract` et `vision_analyze` sont gardés, risque
  résiduel documenté. `memory.write_approval` et `skills.write_approval` à `true`. Détail :
  [image.md](image.md).
- **Hermes ne tourne jamais hors des gardes** : refus hors PID 1 (`acp-entree`), arrêt de la
  passerelle et du tableau de bord lancés hors de s6, volume Railway exigé.
- **Fournisseur d'identité : Authelia 4.39.28**, épinglé par condensat, service Railway `identite`,
  un seul utilisateur, un seul client OIDC public (`hermes-acp`) ; Pocket ID écarté. Session sans
  reconnexion : 7 jours. Détail : [identite.md](identite.md).
- **Surfaces shell du tableau de bord** (terminal, fichiers, MCP, variables) gardées sous le seul
  OIDC en P2 ; leur filtrage relève d'une phase ultérieure. Le tableau de bord authentifié reste
  donc un shell du propriétaire.
- **Railway** : branche déployée **`refonte/hermes`**, après la fusion de P2 ; IaC
  `.railway/railway.ts`, SDK `railway@3.11.0` **isolé dans `.railway/`**, appliquée par le
  propriétaire **seul** ; constructeur Dockerfile, Serverless coupé, politique de redémarrage et
  limites déclarés dans `railway.ts`. Libellés des sous-domaines `*.up.railway.app` inconnus tant
  que le propriétaire ne les a pas choisis : valeurs de gabarit qui font **échouer fermé** le plan et
  l'apply. Plafond dur 30 $, alerte à 15 $, agent Railway à 0 $ ; Hermes 2 Go et 1 vCPU ; identite
  0,5 vCPU, `ON_FAILURE` à 100 relances, mémoire fixée **après mesure** (2,5 Gio) ; sauvegardes
  quotidienne et hebdomadaire ; `railway ssh` avec une clé dédiée retirée après usage ;
  `trusted_proxies: []` tant que le bord n'est pas mesuré. Procédure : [railway.md](railway.md).
- **Tests bloquants** : les deux tests `preview.restart` (stdio `tui_gateway.entry` et `/api/ws` du
  vrai tableau de bord) conditionnent la fusion de P2 ; test navigateur Playwright en CI (Chromium
  téléchargé par la CI), en local seulement si un Chromium de Playwright est déjà présent.

### Étape P3 : choix par défaut D1 à D20, **à confirmer par le propriétaire**

Source : cahier de conception de P3 (brouillon de session `plan_p3.md`, § 13 « Décisions à
prendre », 25 septembre 2026), rédigé par l'agent. **Aucun de ces choix n'a été confirmé par le
propriétaire à ce jour** : P3 applique les recommandations par défaut du cahier pour avancer, et les
documents de P3 les citent par leur numéro. Contrairement aux blocs ci-dessus, ils **ne font pas
foi** : là où ils s'écartent du plan (§ 8, § 15), l'écart est dit ci-dessous. Consignés ici après la
relecture indépendante de P3, qui relevait des références D* sans définition. À confirmer en
priorité : **D1, D2, D5, D12 et D16**.

| N° | Question | Choix appliqué en P3 | Écart au plan ou remarque |
|---|---|---|---|
| D1 | Tutoiement ou vouvoiement de l'agent | **Vouvoiement** (`SOUL.md`, `acp-redaction`) | § 8 : « décision du propriétaire » ; § 15 recommandait le **tutoiement** : **contraire**, à confirmer |
| D2 | Liste finale du catalogue côté Hermes | Liste du cahier (16 skills livrées) | § 8 : « décision du propriétaire » ; `literature-review` non vendorisée (provenance) ; après la relecture, `claude-design` et `hermes-agent-skill-authoring` désactivées ([catalogue.md](catalogue.md) § 3) |
| D3 | Épingler ECC | Étiquette `v2.2.1` (`5064474`), licence MIT lue | — |
| D4 | Noms des skills | Noms amont conservés, provenance par la catégorie ; préfixe seulement en cas de collision future | — |
| D5 | Ajouts hors citation du propriétaire | `accessibility`, `mle-workflow`, `python-patterns` ; `literature-review` retenue par le cahier mais **non vendorisée** ; `seo`, `pytorch-patterns`, `animate-expo`, `write-swift`, `industrial-brutalist-ui` écartées | à confirmer |
| D6 | Skills livrées par Hermes inertes sur Railway | Désactivées (`skills.disabled` du volume ; 46 depuis la relecture) | — |
| D7 | Second serveur MCP distant (deepwiki) | Non en P3 : un seul MCP prouvé de bout en bout | — |
| D8 | Serveur MCP stdio ou hors catalogue dans le volume | **Refus de démarrer** (échec fermé) | remède d'un ajout par la page MCP native : [catalogue.md](catalogue.md) § 7.3 |
| D9 | Sonde réelle de context7 en CI | Non bloquante, sortie archivée | cahier : travail séparé ; appliqué comme étape d'`image.yml` |
| D10 | Français forcé une fois ou verrouillé | **Verrouillé** (retour au français à chaque changement) | — |
| D11 | Clé d'API context7 | Aucune (accès anonyme) | conditions d'utilisation à lire avant le premier déploiement ([railway.md](railway.md) § 2, point 6) |
| D12 | `anthropics/skills` (`skill-creator`, `mcp-builder`, `frontend-design`), `obra/superpowers` | **Non retenus** en P3 ; au verrou, exclus avec leur raison depuis la relecture | § 8 et § 15 les recommandaient : **à confirmer** |
| D13 | Greffon `hermes-achievements` | Désactivé | — |
| D14 | Logo | Logotype texte « ACP » ; logo dessiné plus tard, web et QML ensemble | — |
| D15 | Proposer en amont les traductions manquantes de `fr.ts` | Option hors chemin critique | — |
| D16 | Traduire les skills vendorisées | **Non** : texte amont intact, métadonnées en français, réponse en français imposée par la persona | à confirmer |
| D17 | Captures d'écran | Artefacts de la CI et empreintes dans la documentation, non committées | — |
| D18 | Thème clair | Reporté : un seul thème (sombre), épinglé | — |
| D19 | `skills.auto_load` | Aucune skill chargée d'office ; `acp-profils` à la demande | — |
| D20 | `dashboard.font` | Épinglé sur la police du thème | — |

### Étape P4 : choix par défaut D21 à D47, **à confirmer par le propriétaire**

Source : cahier de conception de P4 (brouillon de session `plan_p4.md`, § 17, 26 septembre 2026), rédigé
par l'agent, puis relecture indépendante de P4 (même jour : D41 à D47).
**Aucun de ces choix n'a été confirmé par le propriétaire à ce jour** : P4 applique les recommandations par
défaut pour avancer ; comme D1 à D20, ils **ne font pas foi**. Détail : [projets.md](projets.md). À confirmer en priorité, parce qu'ils touchent votre
parcours : **D25, D31, D39, D40 et D41** (recommandation par défaut : garder les choix appliqués). D21 à D24,
D30 et D38 sont internes : ils ne changent rien à ce que vous voyez.

| N° | Question | Choix appliqué en P4 | Autre option et conséquence pour vous | Écart au plan ou remarque |
|---|---|---|---|---|
| D21 | Contrat « inventaire du poste » | Une seule source, `acp_poste_contrat.inventaire`, importée par le greffon par son chemin | Une copie par composant : aucune différence visible, mais deux contrats qui peuvent diverger | interne |
| D22 | Code du greffon | Sous-paquet `noyau/`, chargé aussi par le tableau de bord sous le nom `acp_poste_noyau` | Un seul chargement : aucune différence visible | interne |
| D23 | Visibilité des outils | Selon le contexte (discussion ou worker) par `check_fn` non mis en cache, revérifiée par chaque gestionnaire | Tous les outils partout : la discussion verrait `projet_planifier`, refusé à l'appel | interne ; Hermes diffère les outils de greffon derrière `tool_search` : appel par `tool_call` |
| D24 | Outils sur `api_server` et `cron` | Coupés (`known_plugin_toolsets`) | Ouverts : un travail planifié (cron) pourrait lancer des projets sans vous | interne ; bilan quotidien de P7 à revoir alors |
| D25 | Projet sur dépôt sans inventaire du poste | **Refus explicite** | Accepté et mis en attente du poste : le projet resterait « en attente » jusqu'à P5 | — |
| D26 | Quota inconnu à la planification | Admis avec la mention « quota inconnu » ; le poste revalidera (P6) | Refus : aucun projet sur dépôt avant que le poste publie ses quotas | — |
| D27 | Relecture croisée impossible | **Refus**, jamais une relecture par le même exécutant | Relecture par le même exécutant : plus de projets possibles avec un seul exécutant, relecture moins sûre | — |
| D28 | Carte « répondre » et outils `question_*` | Dès P4 | En P7 : toute question vous serait transmise | le plan les rangeait en P7 |
| D29 | Corrections | `inserer_correction` préparée et testée en P4, câblée en P6 | Aucune avant P6 : rien de visible en P4 | — |
| D30 | Exécutants admis par classe de tâche | Table du cahier (§ 7.1) ; `integration` refusée jusqu'à P6 | Table libre : l'agent choisirait n'importe quel exécutant | interne |
| D31 | Pause générale | Arrêt d'urgence de Hermes : plus de nouvelle carte ni de nouvelle notification d'avancement ; la discussion reste ouverte (lancer un projet y est refusé) | Couper aussi la discussion : Hermes ne vous répondrait plus du tout pendant la pause | limite dite ; texte de la page corrigé à la relecture de P4 |
| D32 | Contenu des notifications | Minimal : genre, titre du projet, titre de carte tronqué, lien ; jamais la consigne ni la question | Texte complet : lisible sans ouvrir la page, mais le contenu passe par un service tiers | — |
| D33 | ntfy | Jeton **exigé**, sujet long, `https://ntfy.sh` par défaut | Sans jeton : plus simple, mais le fil serait lisible par quiconque devine le sujet | — |
| D34 | Crochets shell apparus en cours de route | Pause générale et notification, en plus du refus au démarrage | Refus au démarrage seulement : un crochet posé en cours de route s'exécuterait | — |
| D35 | Rafraîchissement de la page Projets | Sondage toutes les 15 s en P4, tant que la page est visible ; temps réel (SSE) en P7 | Temps réel dès P4 : plus réactif, plus de code serveur | appliqué par la page (seconde partie de P4) |
| D36 | Page Projets | Greffon d'interface séparé `acp-projets` | Page dans `acp-interface` : un seul greffon, mais tout désactivé si l'un casse | livré (seconde partie de P4) ; onglet placé avant « Catalogue », icône `FolderOpen` ([projets.md](projets.md) § 8) |
| D37 | Carte `poste-*` créée hors du greffon | **Bloquée** (`capability`), jamais archivée | Archivée : elle disparaîtrait sans que vous la voyiez | une carte encore `todo` l'est dès qu'elle devient `ready` |
| D38 | `SOUL.md` et `acp-profils` | Mis à jour (projets par `projet_lancer`, projet sur dépôt en attente du poste) | Inchangés : Hermes ignorerait les projets en discussion | interne |
| D39 | Efforts et paliers | Efforts interdits `max`, `ultra`, `ultracode` ; palier `default` seul | Tout admis : plus de puissance, dépense non bornée | plan § 11.4 : au propriétaire |
| D40 | `memory` dans un worker kanban | **Refusé par la garde** dans un worker (`HERMES_KANBAN_TASK` posée), admis en discussion | Admis : chaque écriture bloquerait la carte 300 s sur une approbation que personne ne voit | ajouté pendant P4 : constaté au contrat, l'écriture ouvrait une invite d'approbation qui attendait 300 s sans personne (`approvals.timeout`) ; le plan d'autonomie ([autonomie.md](autonomie.md) § 7) laisse ce choix au propriétaire |
| D41 | Plafond atteint, ou planification finie sans plan | Une carte de décision vous est adressée (et notifiée) : **« Prolonger »** (plafond de tours + 1, ou de cartes + 10 ; journalisé) ou **« Relancer la planification »**, avec une consigne, fait planifier la suite par Hermes depuis cette carte ; **« Conclure le projet »** l'arrête (« Terminé » s'il a au moins un tour, sinon « Abandonné »). « Clore » un projet quelconque : P7 | « Conclure » seulement : aucun moyen de prolonger un projet utile sans le relancer de zéro | ajouté à la relecture de P4 (le « Reprendre » d'avant faisait conclure Hermes et annonçait « terminé ») ; prolonger le plafond de corrections : P6 |
| D42 | « Qui répond aux questions » pour un projet sans dépôt | Choix masqué : la page dit qu'il est sans objet (aucune question ne naît sans dépôt) ; un manque se dit par une carte bloquée avec sa raison | Choix affiché : il n'aurait aucun effet | ajouté à la relecture de P4 |
| D43 | Surcharge de routage d'une carte existante | **Refusée** en P4 (message français) ; la surcharge de projet vaut pour les cartes suivantes | L'appliquer tout de suite : exige de recréer ou de relancer la carte (P6) | ajouté à la relecture de P4 : la réponse « ok » d'avant n'avait aucun effet |
| D44 | Isolation des projets dans un worker | Un worker ne touche que son tableau ; `kanban_comment` sur sa seule carte ; `kanban_link` retiré (garde : 33 noms) | Commentaires libres entre projets : un contenu web hostile lu par un projet pourrait écrire dans un autre | ajouté à la relecture de P4 ; en P6, le poste n'exécute que le corps émis par le greffon et les commentaires du propriétaire et de `hermes (acp-questions)` |
| D45 | Reprise de la pause générale engagée par la veille des crochets | **Refusée** (409) tant que les crochets existent ; la page dit comment en sortir | Reprise libre : un tour du répartiteur pourrait lancer des workers avec les crochets | ajouté à la relecture de P4 |
| D46 | Filets déterministes de l'émetteur | Planification finie sans plan → carte de décision (D41) ; question dont la carte « répondre » s'est finie sans suite → escaladée et notifiée | Compter sur le modèle : un projet ou une question pourrait rester bloqué sans que vous le sachiez | ajouté à la relecture de P4 |
| D47 | Réponse ou décision sur un projet en pause | La réponse est enregistrée, la carte reprend à la reprise du projet (la page le dit) ; une décision de triage est refusée tant que le projet est en pause | Débloquer tout de suite : la carte partirait pendant la pause | ajouté à la relecture de P4 |

Décisions du plan d'autonomie (§ 11) dont P4 dépend, **toujours ouvertes** : qui répond aux questions
(défaut : Hermes d'abord), canal de notification (défaut : aucun tant que les variables ne sont pas posées),
budgets (défauts des réglages du greffon).

### Étape P5 : choix par défaut D48 à D66, **à confirmer par le propriétaire**

Source : cahier de conception de P5 (brouillon de session `plan_p5.md`, § 17, 26 septembre 2026), rédigé par l'agent
et contre-vérifié (§ 21 du cahier). Le cahier les numérote 40 à 58 ; D40 à D47 étaient déjà pris par P4
(ci-dessus) : ils deviennent **D48 à D66**, dans le même ordre (le numéro du cahier est rappelé en remarque).
**Aucun de ces choix n'a été confirmé par le propriétaire à ce jour** : P5 applique les recommandations par défaut
pour avancer ; comme les précédents, ils **ne font pas foi**. Détail : [poste.md](poste.md). À confirmer en
priorité, parce qu'ils touchent votre parcours ou votre poste : **D48, D49, D51, D52, D58 et D60** (recommandation
par défaut : garder les choix appliqués). La première partie de P5 (côté Hermes) applique D48 à D50, D56, D58,
D59, D62, D63 et D65 ; la seconde (poste Windows, `apps/poste` et `packaging/poste`) applique D51 à D55, D57,
D60, D61, D64 et D66, et prend sa part de D48, D49, D56, D58, D59 et D65 côté poste. Les étapes qui touchent
votre PC (compte `acp-poste`, tâche planifiée, réglages système) ne sont éprouvées qu'en simulation.

| N° | Question | Choix appliqué en P5 | Autre option et conséquence pour vous | Écart au plan ou remarque |
|---|---|---|---|---|
| D48 | Enrôlement du poste | **Code à usage unique de 10 min** créé sur la page Poste et collé dans `acp-poste enroler` ; le jeton machine (256 bits) n'est jamais affiché ; Railway n'en garde que le SHA-256 | Jeton affiché une fois sur la page (`plan.md`, P5) : il passerait par l'écran et le presse-papiers | cahier : n° 40 ; écart au plan dit |
| D49 | Confirmation de l'empreinte avant que le poste compte | **Oui** : le poste reste « À confirmer » (ni présence, ni inventaire) tant que vous n'avez pas recopié son empreinte `XXXX-XXXX` | Aucune confirmation : un code volé pendant ses 10 minutes suffirait à faire compter un faux poste | cahier : n° 41 |
| D50 | Nombre de postes actifs | **Un seul** ; un nouveau exige la révocation de l'ancien (index unique en base) ; un enrôlement remplace un poste encore « À confirmer » | Plusieurs : un second PC pourrait prendre des cartes sans que vous le voyiez | cahier : n° 42 |
| D51 | Compte d'exécution du poste | **Compte Windows dédié `acp-poste`** ; repli « compte du propriétaire » seulement s'il est déclaré dans `poste.toml` | Votre compte : un exécutant mal confiné lirait votre profil | cahier : n° 43 ; appliqué par la seconde partie de P5 : `Installer-PosteAcp.ps1`, contrôle du compte au démarrage du service ; repli `compte = "proprietaire"` éprouvé par le bout en bout local |
| D52 | Emplacement de `poste.toml` | **`%ProgramData%\ACP\`, en lecture seule pour le poste** | `%LOCALAPPDATA%` du compte (plan d'autonomie) : un exécutant pourrait réécrire sa propre politique | cahier : n° 44 ; écart à `autonomie.md` ; le greffon applique déjà ses interdits (« Interdit par le poste ») ; le poste refuse de démarrer s'il peut modifier ou remplacer le fichier (`GENERIC_WRITE`, `DELETE`, `WRITE_DAC`, `WRITE_OWNER`, dossier) |
| D53 | Installation Python du poste | Sans venv, interpréteur python.org « tous utilisateurs » lancé en `-I` | venv : son lanceur laisse vivre l'interpréteur réel hors du Job Object | cahier : n° 45 ; appliqué (`lancer.py`, verrou d'exécution `requirements/poste-3.12.lock.txt`) ; sources du poste copiées plutôt que construites (setuptools absent de Python 3.12) |
| D54 | Provenance des binaires Codex et Claude | Copie de vos installations sous `Program Files`, version vérifiée, SHA-256 consignés | Installation par le poste : téléchargement non maîtrisé, binaires modifiables par le compte | cahier : n° 46 ; appliqué ; Codex copié avec la disposition du paquet npm (`outils\codex\bin\codex.exe`) |
| D55 | Ouverture du compte pour les connexions | `runas /user:acp-poste` (console) | Session Windows complète : plus lourd, mêmes gestes | cahier : n° 47 ; appliqué (gestes du README du poste) |
| D56 | Quotas Claude en P5 | Ligne d'état de **vos** sessions Claude Code, « même abonnement » déclaré par vous ; sinon « Inconnu » jusqu'à P6 | Aucun quota Claude avant P6 | cahier : n° 48 ; la page Quotas affiche la source déclarée |
| D57 | Réglages système proposés par l'installeur | Démarrage rapide coupé, veille jamais sur secteur, chacun sur confirmation | Aucun : chaque veille de plus de 3 min notifie « Poste hors ligne » | cahier : n° 49 ; appliqué : trois questions de l'installeur, aucune posée en simulation |
| D58 | « Liste de secours » de Codex | Comparaison au catalogue embarqué ; routage **refusé** sans votre acceptation explicite, par relevé (« Accepter ce relevé comme celui de mon compte ») | Acceptée d'office : le routage pourrait viser des modèles que votre compte n'a pas | cahier : n° 50 |
| D59 | Catalogue Claude | Alias et efforts **documentés**, datés, liés à une plage de versions ; `isDefault` nul (aucune suggestion Claude) ; résolution observée en P6 | Inventer une résolution : aucune donnée observée ne la fonde | cahier : n° 51 ; le contrat admet `opus[1m]` et des efforts inconnus (`null`) |
| D60 | Si `config/read` n'expose pas le mode du bac à sable | Écriture Codex **refusée** (échec fermé) ; P6 limité à Codex en lecture seule et à Claude | Déduire le mode de la readiness : elle rend `ready` aussi en mode non élevé | cahier : n° 52 ; le contrat refuse `ecriture_admise` vrai hors de ce cas ; le poste lit le mode par `config/read` (constaté en local : `elevated`, origine `sessionFlags`, sur un profil vide) |
| D61 | Client HTTP du poste | Bibliothèque standard (`http.client`, `ssl`, magasin Windows) | `httpx` : une dépendance de plus sur le poste | cahier : n° 53 ; appliqué (`client_hermes.py`) ; `cryptography` seulement pour l'autorité de test des tests |
| D62 | Pages P5 | **Un onglet « Poste »** à trois vues (état, routage, quotas), greffon `acp-poste-vues` | Trois onglets : plus visibles, navigation plus chargée au téléphone | cahier : n° 54 ; onglet après « Projets », icône `Monitor` |
| D63 | Seuils | Attente 25 s ; relevé toutes les 30 min ; hors ligne à 180 s avec grâce de redémarrage ; « Périmé » à 2 h (P4) ; code valable 10 min ; un inventaire par minute au plus, sauf ordre « releve » | Seuils plus courts : plus de trafic et de fausses alertes | cahier : n° 55 ; réglages du greffon (`longpoll_attente_s`, `enrolement_validite_s`, `inventaire_intervalle_min_s`, `ordre_expiration_s`) |
| D64 | Journal du poste | Local seulement, 5 × 1 Mio | Envoyé à Hermes : le journal sortirait du PC | cahier : n° 56 ; appliqué (`journal.py`, masquage avant écriture) |
| D65 | 401 générique de la couture de Hermes | **Jeton gardé**, plus aucun échange, arrêt (code 4), nouvel essai par le déclencheur de garde ; effacement seulement sur le 401 explicite `poste_revoque` | Effacer sur tout 401 : une panne du fournisseur côté Hermes ferait réenrôler physiquement le poste | cahier : n° 57 ; le greffon ne rend `poste_revoque` que s'il a relu la révocation |
| D66 | Relance du poste par Windows | Déclencheur de garde toutes les 15 min, en plus du démarrage | « Redémarrer en cas d'échec » seul : non prouvé sur un code de sortie non nul | cahier : n° 58 ; appliqué (`tache-poste.xml.modele` : `BootTrigger` et `TimeTrigger` répété toutes les 15 min sans fin, `IgnoreNew`) |

### Relecture de P5 : choix par défaut D67 à D73, **à confirmer par le propriétaire**

Trois relectures indépendantes de P5 (exactitude, sécurité, exploitation ; 27 septembre 2026) ont relevé seize
constats ; leurs corrections ont exigé ces choix, appliqués par défaut et **non confirmés** (ils **ne font pas foi**).
Tableau constat → traitement → preuve : [poste.md](poste.md) § 26. Recommandation par défaut : garder les choix
appliqués.

| N° | Question | Choix appliqué | Autre option et conséquence pour vous | Écart au plan ou remarque |
|---|---|---|---|---|
| D67 | Interpréteur Python modifiable par le compte du poste | **Refus** : de l'installeur (étape 1, ACL de `python.exe`, de son dossier, de `Lib`, `Lib\site-packages` et `DLLs` pour les groupes du compte) et du service au démarrage | Le laisser : un exécutant mal confiné (P6) planterait un `.pth` lu par `python -I` et lirait les jetons déchiffrés en mémoire | relecture de sécurité ; un Python installé directement sous `C:\` hérite du droit Modification des Utilisateurs authentifiés |
| D68 | Forme des commandes du poste données au propriétaire | Forme exécutable dans la console `runas` : `& 'C:\Program Files\ACP\poste\acp-poste.cmd' …` sur le poste ; `& "$env:ProgramFiles\ACP\poste\acp-poste.cmd" …` dans ce que Hermes affiche (sans lettre de lecteur, la garde « aucun identifiant » refusant les chemins) | Ajouter le dossier au PATH du compte : un réglage de plus, et la forme courte ne marcherait toujours pas dans votre session | relecture d'exploitation : « acp-poste enroler » n'était reconnu par aucune console |
| D69 | Contrôle « un fournisseur de session existe » (cahier § 20) | **Non fait dans le greffon** : le fournisseur du jeton machine s'enregistre sans condition ; l'OIDC est exigé au démarrage par `acp_demarrage gardes` (variables obligatoires) ; écart déclaré | Le subordonner à l'OIDC dans `register()` : impossible, `acp-poste` se charge avant le greffon OIDC (tri alphabétique des greffons groupés) ; tenté en 04f20bd, cela retirait le jeton machine de tout déploiement réel | [poste.md](poste.md) § 11 |
| D70 | Exécutable d'une CLI absent ou qui est un dossier | Refus « fichier introuvable » **avant** le contrôle des droits (mode dédié) ; dossier refusé dans tous les modes | Contrôle des droits sur le dossier absent : refus trompeur « binaire modifiable » | relecture d'exactitude ; cahier § 7.3 |
| D71 | Version de Claude Code à l'installation | Lue sur la source dès l'étape 1 (simulation comprise) : **refus** sous 2.1.248, **avertissement** sous 2.1.280 (voie refusée au routage, efforts inconnus) | Refus sous 2.1.280 : la voie Codex resterait inutilisable tant que Claude n'est pas à jour | relecture d'exploitation : votre Claude Code est en 2.1.239 |
| D72 | Fraîcheur des quotas | Chaque compteur est « Périmé » selon **sa** date d'observation ; la voie l'est quand tous ses compteurs le sont | La date du relevé : une ligne d'état vieille de plusieurs jours s'affichait « Relevé » | relecture d'exploitation ; contrat `SubscriptionQuotaView` |
| D73 | Modèle d'une étape poste-claude (routage, nouveau projet) | **Choix explicite exigé** : l'option « Modèle par défaut du relevé » n'est proposée que si un modèle du relevé est marqué par défaut (jamais pour Claude, D59) | La proposer quand même : un choix toujours refusé par le serveur | relecture d'exactitude |

### Étape P6 : décisions D74 à D92, **appliquées**

État livré (1er octobre 2026, côté dépôt, rien de déployé) : [executant.md](executant.md) ; gestes du propriétaire,
sonde R0 comprise : [railway.md § 13](railway.md#13-exécutant-étape-p6).

Décision du propriétaire (27 septembre et 1er octobre 2026) : l'exécution principale se fait sur un service Railway
séparé, l'« exécutant » ; le propriétaire **fournit les comptes** et laisse Hermes gérer l'exploitation. Les
recommandations du cahier de conception P6 (§ 17) sont donc **appliquées**, et non « à confirmer ».

**Numérotation.** Le cahier P6 numérote ses décisions 71 à 89 ; la relecture de P5 avait entre-temps pris
**D67 à D73** (section précédente, dette de P5 déjà inscrite). Les décisions de P6 sont donc décalées de trois :
n° 71 du cahier → **D74**, …, n° 89 du cahier → **D92**. Le code et la documentation de P6 citent les numéros de
ce tableau.

| N° | Question | Choix appliqué en P6 | Autre option et conséquence | Remarque (n° du cahier P6) |
|---|---|---|---|---|
| D74 | Hôte d'exécution principal | Service Railway `executant`, séparé de Hermes, qui garde son conteneur sans terminal | PC Windows (plan d'autonomie) : facultatif désormais | n° 71 du cahier ; décision du propriétaire du 27/09 |
| D75 | Voie de l'exécutant vers Hermes | **URL publique HTTPS**, sans changement de protocole ni de règle | Réseau privé en http : exception de la politique, nouvelle surface | n° 72 du cahier ; cahier § 10.3 |
| D76 | Client de l'exécutant | **`apps/poste` multiplateforme** (couche `plateforme/`) | Second client Linux : deux codes pour un protocole | n° 73 du cahier ; cahier § 7.1 |
| D77 | Machines actives | **Une seule, l'exécutant** ; bascule manuelle vers le PC (révocation, puis réenrôlement) | Deux machines avec affinité par carte : index unique retiré | n° 74 du cahier ; cahier § 18 |
| D78 | Politique de l'exécutant | **Fichier versionné** `executant/politique/executant.toml`, copié en lecture seule dans l'image ; toute modification passe par une PR ; Hermes ne la fournit jamais (la carte servie porte `branche_base: null`) | Variable Railway, fichier du volume : modifiables sans revue | n° 75 du cahier ; cahier § 7.2 |
| D79 | Si la sonde donne le régime B | **(c)** Claude seul en écriture, voie Codex **fermée** (« Indisponible : bac à sable Linux refusé par la plateforme ») | (b) Codex sans shell, seulement si un essai le prouve ; (a) `danger-full-access` ; (d) Railway Sandboxes, écartée | n° 76 du cahier ; cahier § 4.3 ; le greffon ferme la voie d'après l'inventaire (`isolement_linux`) |
| D80 | Vérification sans bac à sable (régime B) | **Par dépôt**, `verification_sans_bac_a_sable = false` par défaut ; la CI du dépôt reste juge | Toujours ; jamais | n° 77 du cahier ; cahier § 4.3 |
| D81 | Identifiants Codex et sauvegardes | Stockage `file` sur le volume ; sauvegardes quotidienne et hebdomadaire gardées | Sans sauvegarde : branches locales perdues au premier incident | n° 78 du cahier ; cahier § 11 |
| D82 | Push | **Aucun en P6** : récupération par `git bundle` et `railway ssh` (commande affichée par la page Poste, « Branches prêtes ») ; option B conçue, activée sur décision ultérieure | Jeton du propriétaire en écriture : contournerait les règles | n° 79 du cahier ; cahier § 12 ; aucun bouton « Pousser » |
| D83 | Codex avec le compte ChatGPT du propriétaire | **Accepté**, dépôts **privés** seulement, un seul `auth.json` créé par code d'appareil **sur** l'exécutant | Clé d'API OpenAI ; voie Codex fermée | n° 80 du cahier ; cahier § 2.1 ; date consignée dans `[conditions] codex_decide_le` de la politique, sans quoi la voie reste fermée |
| D84 | Claude Code avec l'abonnement du propriétaire (`setup-token`) | **Accepté**, garde-fous tenus par Hermes et l'exécutant : une carte à la fois, 20 cartes et 8 h d'agent par jour, arrêt à 90 % du quota | Clé d'API Console ; voie Claude fermée | n° 81 du cahier ; cahier § 2.2 ; date dans `[conditions] claude_decide_le` |
| D85 | Budget | Une carte ; 2 vCPU, 4 Gio ; 8 h d'agent et 20 cartes par jour ; alerte à 15 $, limite dure à 30 $ ; réévaluation après une semaine | Relever la limite ; fenêtres horaires | n° 82 du cahier ; cahier § 13 |
| D86 | Versions | Codex **0.156.1**, Claude Code **2.1.283** ; SHA-256 obligatoires, GPG pour Claude | Codex 0.157.1 : lot dédié | n° 83 du cahier ; cahier § 8.2 |
| D87 | Dépôt de preuve | **Jetable et privé** | Public : voie Codex fermée | n° 84 du cahier ; cahier § 2.1 |
| D88 | Sonde R0 | **Projet Railway jetable** `acp-sonde`, préparée par ACP, lancée par le propriétaire | Service temporaire dans `acp` | n° 85 du cahier ; cahier § 4.1 |
| D89 | Réseau des commandes des agents | **Coupé** en régime A ; en régime B, aucune commande Codex, vérification selon D80 | Autorisé par dépôt | n° 86 du cahier ; cahier § 4 |
| D90 | Fichiers de pilotage | **Liste étendue** (`.github/` entier, `.gitattributes`, `.gitmodules`, `.husky/`, `.mcp.json`, liens ajoutés…, et, depuis la relecture de P6, `AGENTS.override.md` et `CLAUDE.local.md`, lus par les CLI de l'image) → la carte passe **en revue** ; refus du propriétaire par `add_comment` puis `reopen_review_task` | Liste du plan d'autonomie seule | n° 87 du cahier ; cahier § 6.6, § 5.4 |
| D91 | Relecture quand la voie de l'autre exécutant est fermée | **Même voie, autre modèle** (classe « relecture »), décidé automatiquement par le routage de Hermes, et dit (mention) ; jamais le modèle de l'implémentation ; sinon refus `relecture_impossible` | Garder D27 tel quel | n° 88 du cahier ; **lève D27 dans ce cas seulement** ; réglage `relecture_repli_meme_voie` (vrai par défaut) : levé, D27 s'applique |
| D92 | Rangement du jeton Claude et du jeton GitHub de lecture | **Fichiers 0600 root sur le volume**, déposés par `railway ssh` (`acp-poste connexion … --stdin`) | Variables scellées : présentes dans l'environnement du PID 1 | n° 89 du cahier ; cahier § 11 |

### Étape P7 : décisions D93 à D120, **appliquées**

État livré (8 octobre 2026, côté dépôt, rien de déployé) : [questions.md](questions.md) (file Questions, notifications,
continuité téléphone ↔ bureau), [executant.md](executant.md) § 16 (garde « dépôt privé » mesurée, relance après un
secret ; écrit par `9235999`), [railway.md](railway.md) § 14 (canal de notification,
bilan quotidien, dépôts réels un par un) ; ce que P7 change pour l'autonomie : annexe d'[autonomie.md](autonomie.md).

Comme pour P6, le propriétaire **fournit les comptes** et laisse Hermes gérer l'exploitation : les recommandations du
cahier de conception P7 (§ 16) sont **appliquées**, et non « à confirmer », de même que les décisions prises en cours
de route et consignées au journal de P7. Seuls lui reviennent : le choix du canal et ses identifiants, le premier
dépôt réel (et chacun des suivants) avec son « oui » écrit, sa présence pour les preuves sur Railway.

**Partie E finale.** Les six commits poussés sur `refonte/hermes-p7e` après le départ de la partie F (`3b1cac9`,
`e85c7e3`, `1f2574c`, `a41952f`, `9235999`, `a516890`) sont réunis à la partie F sur `refonte/hermes-p7` par la
fusion `e2d210b` (8 octobre 2026). La remarque de D106 et de D110 à D115 nomme le commit qui apporte le code ou la
documentation de la décision.

**Numérotation.** Le cahier P7 numérote ses décisions P7-1 à P7-13 ; la partie E en a ajouté dix (P7-E-1 à P7-E-10)
et la partie F une (P7-F-1), au journal de P7. Elles prennent la suite de D92, sans trou : P7-n → **D(92 + n)** (D93 à
D105), P7-E-n → **D(105 + n)** (D106 à D115), P7-F-1 → **D116** ; la relecture finale du 8 octobre 2026 (constats
corrigés sur `refonte/hermes-p7`, journal des corrections de P7) numérote les siennes P7-R-n → **D(116 + n)**, à la
suite. P8 n'a pris aucun numéro Dnn (ses décisions,
numérotées à part, sont dans [desktop.md](desktop.md)). La documentation écrite avant cette numérotation cite
« P7-n » : la colonne « Remarque » donne la correspondance.

| N° | Question | Choix appliqué en P7 | Autre option et conséquence | Remarque (origine) |
|---|---|---|---|---|
| D93 | Branche | Parties A à D sur `refonte/hermes-p7`, empilée sur la pointe de P6 ; après la fusion de P6 et de P8 dans `refonte/hermes` (PR #19 et #20), fusion de `refonte/hermes` dans `refonte/hermes-p7e` (`c785af2`, sans conflit) pour la partie E ; partie F sur `refonte/hermes-p7f`, partie de la partie E ; branches réunies par commit de fusion avant l'unique PR vers `refonte/hermes` (`e2d210b`, 8 octobre 2026). Raison : les parties A à D n'ont aucun fichier commun avec les corrections de P6 ; la partie E touche `apps/poste`, à ne modifier qu'après la fusion de P6 | Attendre la fusion de P6 pour tout commencer : un à deux jours perdus, sans fichier à protéger | P7-1 du cahier ; cahier § 2.3 ; écart : trois branches au lieu d'une (sessions parallèles), réunies par fusion, jamais par rebase d'une branche poussée |
| D94 | Relancer une carte arrêtée | `POST /v1/cartes/{tableau}/{carte}/relancer` sur un projet **actif** seulement ; consigne facultative : commentaire du propriétaire pour une carte Hermes ; pour une carte de l'exécutant, section du propriétaire **en tête** de la consigne servie (origine gardée, tronquée et dite pour tenir dans les 16 000 caractères du contrat) et `issue = 'relancee'`, qui force une **session neuve** ; aucune carte créée, aucune notification. Raison : sans consigne, la cause ne se corrige pas ; servie en reprise, une consigne serait ignorée | Relance sans consigne : le propriétaire ne pourrait pas corriger la cause ; consigne ajoutée sans session neuve : ignorée en reprise (correction K4) | P7-2 du cahier ; cahier § 3.4 ; écart : section recomposée en tête par le greffon (et non ajoutée en fin par `construire_carte`), pour ne pas toucher `noyau/execution.py` pendant les corrections de P6 ; carte bloquée pour un secret : D111 et D114 |
| D95 | Qui répond | Modifiable à tout moment par projet (`POST /v1/projets/{id}/reponses`), effet sur les questions **suivantes** ; sans objet sans dépôt (409, D42) ; « chez Hermes » seulement pour une question ouverte dont la carte « répondre » existe. Raison : une question ouverte garde son traitement, aucune carte « répondre » arrêtée en vol | Réaffecter les questions ouvertes : plus de code, cartes « répondre » à arrêter en vol | P7-3 du cahier ; cahier § 4.2 ; correction K6 (compteur fondé sur la carte « répondre », jamais sur le réglage courant) |
| D96 | Temps réel | Flux SSE d'**invalidation** `GET /v1/flux` (noms de sujets, aucune donnée) ; veilleur toutes les 2 s, battement toutes les 15 s, fin après 600 s, 8 flux au plus ; un seul flux par onglet (`window.__ACP_FLUX__`) ; repli sur le sondage de 15 s après trois échecs en 2 min ; relecture de sûreté toutes les 120 s. Raison : les routes REST restent la seule source des données ; bornes du bord Railway (5 min sans octet, 15 min au plus) | Flux porteur des données : second format à tenir, divergence possible avec les routes ; WebSocket du greffon : authentification à refaire, pas de `Last-Event-ID` | P7-4 du cahier ; cahier § 5 ; écart : empreintes renforcées (comptes par état ; dernier identifiant du journal des gestes de pause et de politique) après l'aller-retour en moins de 2 s trouvé par la CI de `4c4282b` |
| D97 | Notifications | Liens profonds **en paramètres de requête**, chemin relatif en base, URL publique préfixée à l'envoi par la passerelle ; genre `bilan` ; canal Telegram ou ntfy fourni par le propriétaire, déclaré par `preserve()` (D116) ; pas de rappel automatique. Raison : un fragment est perdu à la connexion (téléphone à la session expirée) ; le sous-processus du cron n'a pas l'URL publique | Fragment `#q_…` : après la connexion, le lien n'ouvrirait que la liste (correction K2) ; rappel des questions sans réponse : bruit, non demandé | P7-5 du cahier ; cahier § 6.2 ; corrections K2, K3, K13 |
| D98 | Bilan quotidien | Cron **natif** `no_agent` créé par le propriétaire (bouton de l'Accueil ou page Cron), script `acp-bilan.py` sans argument ni entrée, 8 h heure de Paris (fuseau `Europe/Paris` épinglé), toujours envoyé, compteurs seulement ; garde de démarrage des `scripts/` élargie à ce **seul** fichier, root 0644, d'empreinte connue. Raison : aucun modèle ni jeton consommé ; l'agent ne peut toujours pas créer de cron | Bilan rédigé par un modèle : consomme l'enveloppe et peut inventer ; minuterie interne de l'émetteur : ce ne serait plus un cron créé par le propriétaire ; garde des `scripts/` retirée : rouvrirait l'exécution de scripts déposés par une injection | P7-6 du cahier ; cahier § 7 ; correction K1 (sans l'élargissement, tout redémarrage après le dépôt du script était refusé) |
| D99 | Accueil | Page à sept blocs dans un ordre fixe, mêmes textes à toutes les largeurs ; route agrégée `GET /v1/accueil` pour les blocs du travail (à traiter, chez Hermes, discussions, projets, exécutant, quotas, notifications, pause générale), bloc illisible `null` avec sa raison ; sessions récentes, système et bilan lus à part (`GET /api/sessions`, `GET /v1/meta`, `GET /api/cron/jobs`), discussions en attente comptées par le client (`/api/ws`). Raison : une seule lecture pour les blocs dont les états doivent concorder ; la carte « Poste » figée de P3 était devenue une donnée fausse | Une route par carte : une lecture par bloc au téléphone et des états incohérents entre cartes | P7-7 du cahier ; cahier § 8 ; écarts : `quotas` a la forme de `GET /v1/quotas`, `branche_prete` (branche réellement prête) au lieu de `branche`, liste `illisibles` ; sessions, système et bilan hors de la route agrégée (le cahier § 8.2 annonçait « une seule lecture pour la page », son § 8.3 y plaçait pourtant les cinq dernières discussions et les cartes de P3) |
| D100 | Discussion mobile | Page réduite `acp-discussion` sur le JSON-RPC natif `/api/ws` : liste, reprise, envoi, texte en flux, réponse à `clarify` (en une fois, sans `clarify.lock`), interruption ; liste blanche des méthodes **et** de leurs paramètres ; toute autre requête du serveur refusée (`-32601`), sans lien vers `/chat`. Raison : seule une session de `/api/ws` survit à la fermeture du téléphone et rejoue sa question depuis le PC | `/chat` seul : aucune continuité des questions entre appareils ; discussion complète (ancienne P4) : trop longue | P7-8 du cahier ; cahier § 9 ; correction K14 ; écarts : onglet `before:catalogue` (`before:projets` tomberait en fin : manifestes traités par ordre alphabétique), liste `/api/sessions?source=tui`, ping toutes les 30 s |
| D101 | Clore un projet | `POST /v1/projets/{id}/clore` avec confirmation : état `termine` si la synthèse du tour est faite, sinon `abandonne`, posé **en premier** et sous condition ; questions annulées ; cartes ouvertes archivées ; aucune notification ; branches rapportées listées. Raison : clore en pleine exécution n'est pas un succès ; une course avec l'émetteur ne produit jamais deux états | Règle de D41 (« terminé » dès un tour) : un projet interrompu passerait pour réussi | P7-9 du cahier ; cahier § 10 ; correction K11 (carte réclamée par l'exécutant : `valide: false` au battement suivant, travail committé puis carte rendue) |
| D102 | Dépôts réels | Un à la fois, après la preuve de P6 sur le dépôt jetable ; le propriétaire choisit le dépôt et l'ajoute à son jeton de lecture ; PR sur `executant.toml` fusionnée après son « oui » écrit **pour ce dépôt** ; preuve « aucune action accord requis sans geste » (`scripts/preuve_accord_requis.py`) avant le suivant. Raison : élargir le périmètre est un geste du propriétaire ; la politique ne change que par une PR (D78) | Ajout depuis l'interface : Hermes deviendrait la source de la politique (contraire à D78) | P7-10 du cahier ; cahier § 11.1 et § 11.3 ; procédure : [railway.md](railway.md) § 14 ; **aucun dépôt réel ajouté à ce jour** |
| D103 | Garde « dépôt privé » | **Mesurée** : accès anonyme refusé ET lecture avec le jeton réussie, sinon voie Codex fermée pour ce dépôt (échec fermé) ; mesure au démarrage, à chaque relevé et avant chaque carte Codex ; double contrôle, greffon (`routage.voies_fermees(…, depot_alias)`) et exécutant. Raison : D83 n'admet Codex avec le compte ChatGPT que sur un dépôt privé, or un dépôt public déclaré `jeton_lecture` passait | Confiance dans l'accès déclaré (`acces`) : un dépôt public déclaré privé passerait | P7-11 du cahier ; cahier § 11.2 ; corrections K24, K25 ; règles fines : D106 à D110 et D113 |
| D104 | Discussions en attente | Listées dans la file Questions (`session.active_list`, lecture seule), **sans notification** | Notifier : la passerelle ne voit pas les sessions du tableau de bord (autre processus), et une `clarify` meurt au redéploiement | P7-12 du cahier ; cahier § 3.5 |
| D105 | Telegram comme canal de discussion avec Hermes | **Hors P7** | L'ouvrir : une plateforme native de plus (outils, liste blanche) à prouver à part | P7-13 du cahier |
| D106 | Mesure de la visibilité d'un dépôt | `git ls-remote --heads` anonyme, puis avec le jeton ; seules les lignes « fatal: » composées par git lui-même (en début de ligne, code 128) valent refus ; tout le reste vaut « inconnue » (échec fermé). Raison : le serveur distant compose les lignes « remote: » et ne doit pas pouvoir forger un refus | API REST de GitHub (`private: true`) : un second canal, un jeton à portée « metadata », et une réponse qui ne prouve pas ce que git verra | P7-E-1 du journal ; [executant.md](executant.md) § 16.1 (écrit par `9235999`) ; motifs relevés sur git 2.47.3 (image) et 2.42 |
| D107 | Sens de « lecture » | La lecture que l'exécutant fera vraiment : avec le jeton pour un dépôt `jeton_lecture`, l'accès anonyme pour un dépôt déclaré `public` ; jeton absent : « inconnue » | Toujours mesurer avec le jeton : un dépôt public sans jeton déposé dirait « inconnue » alors qu'il est lu | P7-E-2 du journal |
| D108 | Moment de la mesure | Mesure **fraîche avant chaque carte Codex** et avant chaque carte d'un dépôt déclaré `public` (refus `politique` : « la politique dit public, GitHub refuse l'accès anonyme : jeton requis ») ; aucune mesure pour une carte Claude d'un dépôt `jeton_lecture` (Claude est admis public ou privé, D84) | Se fier au dernier inventaire : jusqu'à 30 min de retard sur un dépôt rendu public | P7-E-3 du journal |
| D109 | Dossier courant de la mesure | `git ls-remote` lancé depuis la **racine des clones**, jamais depuis un dépôt. Raison : la configuration d'un dépôt du dossier courant (`insteadOf`, `http.extraHeader`, mandataire) ne peut détourner ni la mesure ni le jeton | Lancer depuis le clone du dépôt : une configuration qu'un agent aurait pu écrire s'appliquerait | P7-E-4 du journal ; prouvé par `test_configuration_du_dossier_courant_jamais_lue` |
| D110 | Worktree d'une carte après un secret | Un worktree n'est repris que s'il est posé sur la branche de la carte ; branche absente alors que la carte a déjà tourné : base, session d'agent et préparation oubliées, carte repartie de son départ sur une **branche neuve**, session neuve même servie en `reprise: true` | Repartir du dernier commit sain de la quarantaine : on ne sait pas quel commit a introduit le secret (le balayage porte sur tout le diff) | P7-E-5 du journal ; correction K25 ; code de l'exécutant : `665d825` ; [executant.md](executant.md) § 16.3 (écrit par `9235999`) |
| D111 | Relance d'une carte bloquée pour un secret | **Admise** (le refus posé avant la partie E est levé) : la page dit que le travail fautif reste en quarantaine, la réponse dit `branche_neuve` | Garder le refus jusqu'à une capacité publiée par l'exécutant : un champ de contrat de plus pour une fenêtre de quelques minutes | P7-E-6 du journal ; **précisée par D114** (garde « exécutant de la partie E », ajoutée après la relecture indépendante) ; code : `e85c7e3` (greffon) et `1f2574c` (page) ; avant eux, la relance d'une carte bloquée pour un secret était toujours refusée (409 `carte_secret`) |
| D112 | Voies ouvertes par dépôt | Calculées par le greffon (`routage.depots_du_poste`, par `voies_fermees(…, depot_alias)`) et servies dans `GET /v1/poste` ; l'interface (carte « Dépôts », grisage de Codex dans « Nouveau projet ») ne recalcule rien | Déduire la fermeture côté client depuis l'inventaire : un second calcul, qui peut diverger du routage | P7-E-7 du journal ; code : `e85c7e3` (greffon) et `1f2574c` (interface) |
| D113 | Preuve du « privé » | `prive` exige **deux** refus anonymes encadrant la lecture réussie avec le jeton (un dépôt devenu lisible sans identifiant entre-temps est dit `public`) | Une seule sonde anonyme : une réponse passagère suffirait à ouvrir Codex sur un dépôt public | P7-E-8 du journal ; relecture indépendante de la partie E ; code : `3b1cac9` (avant lui, un seul refus anonyme suffisait) |
| D114 | Garde de la relance après un secret | Admise seulement si le dernier inventaire de l'exécutant actif porte la visibilité mesurée de ses dépôts (seul un exécutant de la partie E la publie) ; sinon 409 `carte_secret`, en échec fermé | Un champ de capacité de plus dans le contrat (refusé par `extra="forbid"` : nouvelle fenêtre d'inventaires refusés) ; aucune garde : un exécutant de P6, servi pendant la fenêtre de déploiement, reprendrait le worktree en quarantaine | P7-E-9 du journal ; relecture indépendante de la partie E ; code : `e85c7e3` |
| D115 | Clone nu d'un dépôt | Lié à l'URL de la politique : un alias réaffecté à une autre URL fait refuser la récupération (carte bloquée) ; le propriétaire retire l'ancien clone après en avoir récupéré les branches | `remote set-url` automatique : mêlerait les branches de deux dépôts dans un même clone | P7-E-10 du journal ; relecture indépendante de la partie E ; code : `3b1cac9` |
| D116 | Variables du canal dans l'IaC | Les **six** variables du canal (`ACP_NOTIFICATIONS`, `ACP_TELEGRAM_JETON`, `ACP_TELEGRAM_DISCUSSION`, `ACP_NTFY_SERVEUR`, `ACP_NTFY_SUJET`, `ACP_NTFY_JETON`) déclarées par `preserve()` dans le service `hermes`, Telegram **et** ntfy, avant le choix du propriétaire ; jamais un littéral (le vérificateur refuse tout littéral pour un nom de secret, et s'éprouve sur des copies altérées). Raison : le propriétaire choisit son canal et pose ses valeurs sans autre PR ; un littéral imposerait un canal et ferait refuser le démarrage avant la pose du jeton | Attendre son choix pour déclarer le seul canal retenu (cahier § 14) : une PR de plus, et d'ici là aucune variable posable sans qu'un plan la supprime | P7-F-1 du journal ; correction K13 ; repose sur une hypothèse **non vérifiée** : `preserve()` sur une variable jamais posée ne crée rien et n'est pas refusé par le plan. Plus exposée que pour l'identité : celle-ci n'est absente que jusqu'à sa pose (§ 5.2 de [railway.md](railway.md)), alors que les variables du canal non choisi restent absentes **pour toujours** (les six si aucun canal n'est choisi) ; si le plan refusait ce `preserve()`, tout plan du projet serait bloqué jusqu'à la PR de repli de [railway.md](railway.md) § 14.1 (retrait des `preserve()` des variables qui resteront absentes) |
| D117 | Relancer une carte d'intégration | La carte d'intégration n'a **pas d'agent** : l'exécutant rejoue la même fusion déterministe et ne lit aucune consigne. Une consigne y est refusée (400 `consigne_sans_objet`, rien n'est écrit) ; la file le dit (`integration` : ni champ de consigne ni « session neuve ») ; la réponse rend `session_neuve: false` ; la raison d'un conflit dit ce que le propriétaire peut réellement faire (relancer, récupérer les branches par `git bundle` pour trancher, ou clôturer). Raison : une consigne acceptée puis jamais lue est un faux succès, et la relance consomme l'unique récurrence avant le triage | Recomposer la consigne comme pour une carte d'agent (comportement de P7 avant la relecture) : la consigne est jetée en silence, la même fusion rejoue le même conflit, et la page annonce un agent qui n'existe pas ; donner un agent à l'intégration : hors du périmètre de P7 (une résolution de conflit par agent demande sa propre relecture) | P7-R-1 de la relecture finale ; constat scenario-2 ; code : greffon (`questions.relancer_carte`, `lister`), page (`Arretee`), exécutant (raison du conflit) |
| D118 | Balayage des secrets sur l'exécutant | Les lignes ajoutées par **chaque** commit absent du dépôt distant (`<tête> --not --remotes`, merges en diff combiné) sont balayées, en plus du diff cumulé : à la conclusion de chaque carte (donc à l'intégration), après chaque commit « wip » (blocage, quota, interruption : un secret y bloque la carte **pour un secret**, branche en quarantaine) et par `git bundle`, qui refuse d'emballer un tel historique. Raison : `merge --no-ff` et `git bundle` emportent tout l'historique ; un secret commité puis retiré passait le seul diff cumulé, sans aucun adversaire (un « wip » de quota est repris automatiquement) | Garder le diff cumulé et le dire (limite de P6) : la garde « rien du contenu ne sort » serait contournée sans bruit ; réécrire l'historique (squash avant intégration) : perd la trace des tentatives et complique la reprise | P7-R-2 de la relecture finale ; constat securite-1 (défaut (a) de P6) ; [executant.md](executant.md) § 16.7 ; code : `apps/poste` (`Depots.lignes_ajoutees_non_poussees`, `Execution._secret_non_pousse`, `Depots.bundle`) |
| D119 | Quarantaine impossible | Un renommage en quarantaine en échec ne change pas l'issue : la carte est **quand même** bloquée pour un secret (raison fixe, journal `secret_detecte` puis `quarantaine_impossible`) ; sa session garde `quarantaine_en_attente`, et le service suivant retente le renommage **avant tout tour d'agent**, refusant la carte pour un secret tant qu'il échoue. Raison : un blocage en « capacité » ne portait ni la notification « secret », ni la garde de relance du greffon, et la carte repartait de la branche fautive | Bloquer en « capacité » (P6) : relance sans garde, reprise du worktree fautif ; supprimer la branche fautive : détruit la preuve que le propriétaire doit examiner | P7-R-3 de la relecture finale ; constat securite-2 (défaut (b) de P6) ; [executant.md](executant.md) § 16.7 ; code : `apps/poste` (`Execution._mettre_en_quarantaine`, `_quarantaine_en_attente`) |
| D120 | Carte « répondre » dont la question a été adressée au propriétaire | **Non relançable** (409 `question_adressee`, raison dite dans la file : « répondez-y dans la section Questions ») et **non comptée** dans « À traiter par vous » (la question l'est déjà) ; la carte reste visible dans « Cartes arrêtées ». Raison : relancée, elle ne peut plus rien (`question_repondre` et `question_escalader` exigent une question `ouverte`) : un bouton qui ferait semblant et un tour de modèle perdu | L'archiver à l'escalade : retirerait du kanban une carte que le propriétaire peut vouloir lire, et ne couvre pas une question répondue ou escaladée par une autre voie ; la laisser relançable (P7 avant la relecture) | P7-R-4 de la relecture finale ; constat scenario-6 ; code : greffon (`questions.question_adressee`, `refus_de_relance`, `compteurs`) |

### Phases P4 à P8 remplacées par le plan d'autonomie

Décision du 25 septembre 2026. Le plan complet, recopié tel quel, est dans
[autonomie.md](autonomie.md) ; en résumé :

- Hermes devient un **chef de projet autonome** : un tableau kanban par projet sur Railway ; le
  greffon fait d'abord explorer le dépôt par le poste (lecture seule), une carte de planification
  Hermes découpe le projet (cartes Codex, Claude, Hermes, chacune avec exécutant, modèle et effort),
  une synthèse juge et relance dans des plafonds fixés.
- Le **poste Windows** n'est plus en lecture seule et **aucune signature n'est demandée par
  tâche** : il écrit seul, dans un worktree et une branche `hermes/<carte>` des dépôts autorisés
  par `poste.toml`, sous bac à sable (Codex *elevated* imposé, Claude `--restricted`), vérifie,
  committe en local, sans jamais pousser.
- **Accord explicite du propriétaire** pour l'irréversible et ce qui sort de chez lui : push,
  fusion, PR, publication, dépenses hors enveloppe, élargissement du périmètre, tâches cron,
  écritures de l'agent en mémoire et dans les skills.
- **Modèles** : aucun nom en dur ; catalogues relevés (`model/list` de Codex, alias et modèle
  observé pour Claude), table de routage validée une fois ; palier Fast interdit par défaut.
- **Questions** durables dans le greffon, carte mise en attente (pas bloquée), notification
  Telegram ou ntfy ; état commun au téléphone, au navigateur et au desktop Qt.
- Nouvelles phases : **P4** projets autonomes sur Hermes (sans le PC) ; **P5** poste connecté
  (présence, catalogue, quotas, sans exécution) ; **P6** exécution autonome sur un dépôt jetable ;
  **P7** questions, notifications et continuité, puis dépôts réels ; **P8** desktop Qt et MCP côté
  poste. P3 et P9 sont inchangées.
- Retirés de l'ancien plan : la P7 « Écritures validées et signées » (passkey par tentative), le
  poste en lecture comme verrou, le tableau unique `poste`, l'ancienne P4 « Discussion mobile » comme
  étape autonome (liste complète : [autonomie.md](autonomie.md) § 9).

### État d'avancement (25 septembre 2026)

- **P0** et **P1** : fusionnées dans `refonte/hermes` (PR #13 et #14, commits de fusion `29c95b5` et `21d13ee`).
- **P2** : **réalisée côté dépôt** sur `refonte/hermes-p2` (image sans outil d'exécution, fournisseur
  d'identité, IaC, procédure, CI verte) ; **rien n'est déployé** : le premier déploiement est fait par
  le propriétaire, selon [railway.md](railway.md), après la fusion. Preuves datées :
  `docs/reprise-poste.md`.
- **P3** : en cours sur `refonte/hermes-p3` (empilée sur P2). Première partie, **identité visuelle
  et français**, réalisée côté dépôt : thème `acp` généré depuis les jetons, persona française,
  greffons `acp-interface` et `acp-catalogue`, verrou du français, décompte des chaînes restées en
  anglais, captures 390×844 et 1440×900 ([interface.md](interface.md)). Seconde partie,
  **réglages prêts**, réalisée côté dépôt : 16 skills livrées (14 vendorisées à des commits
  épinglés, 2 maison), verrou et vérificateur, 46 skills livrées inertes désactivées, context7
  seul MCP côté Hermes derrière la garde, refus des serveurs MCP stdio ou hors catalogue, route
  `/v1/catalogue` ([catalogue.md](catalogue.md)). Aucune PR ni fusion à ce jour.

### Conséquences de P2 sur la lecture du plan

- § 9 « VARIABLES À DÉFINIR » et « VARIABLES INTERDITES » sont **périmées** (elles visent Nous
  Portal) : la référence est [image.md](image.md) § 4 pour Hermes, [identite.md](identite.md) § 3
  pour l'identité, [railway.md](railway.md) pour leur pose.
- § 9 « DÉCLARATION » : « Wait for CI », motifs surveillés et répertoire racine ne sont plus
  « non couverts par l'IaC » : ils sont déclarés dans `railway.ts` par des clés **typées par le SDK
  mais absentes de sa documentation** (`checkSuites`, `build.builder`, `build.watchPatterns`,
  `deploy.sleepApplication`, `deploy.restartPolicy*`, `deploy.limitOverride`) ; leur prise en compte
  se prouve par `railway config pull --json`. Répertoires racines `/hermes` et `/identite` ;
  Dockerfile de Hermes désigné par `RAILWAY_DOCKERFILE_PATH=image/Dockerfile` (relatif au répertoire
  racine, à confirmer au premier build).
- **Région** : `europe-west4-drams3a` (EU West Metal, Amsterdam, identifiant de la page « Regions ») ;
  la référence de l'IaC montre aussi `europe-west4` : ambiguïté documentée
  ([railway.md](railway.md) § 3).
- § 9 « DERRIÈRE LE PROXY » et P2 « cookie `Secure` » : tant que `trusted_proxies` reste vide, les
  cookies de Hermes n'ont **pas** l'attribut `Secure` (mesuré derrière un bord factice) ; la mesure du
  bord réel est au § 8 de [railway.md](railway.md). La lecture brute de `X-Forwarded-For` par
  `client_ip` est bien à `hermes_cli/dashboard_auth/request_utils.py:19-21` (revérifié le 25/09).
- P2 « Wait for CI activé ; tableau de bord enregistré sur Nous » : lire « identité Authelia, client
  `hermes-acp` ».

## 2. Thèse

Hermes Agent 0.21.5 devient le seul serveur, le seul orchestrateur et la seule source de vérité. Référence : tag v2026.9.24, commit f97608f, vérifié par `git log -1` dans le clone.

ACP n'a plus de backend : pas d'API, pas de base, pas de bus d'événements, pas de CLI. Il ne reste que quatre pièces.
1. **Une image Railway dérivée de l'image officielle**, épinglée par condensat, avec `CMD ["gateway","run"]`. Elle n'utilise que des points d'extension documentés de Hermes :
   - une managed scope /etc/hermes : `config.yaml` livré dans l'image, `.env` régénéré à chaque démarrage par le script root `05-acp` à partir de variables Railway validées (identifiant OAuth Nous, URL publique, hôte de l'api_server) — jamais depuis /opt/data ;
   - deux greffons « groupés » (livrés dans l'image), en lecture seule dans /opt/hermes/plugins : `acp-interface` (identité, pages, discussion mobile) et `acp-poste` (outils de délégation, jeton machine, routes du poste, quotas) ;
   - des skills vendorisées, en lecture seule, sans collision de nom avec les skills livrées par Hermes ;
   - une persona française.
2. **Le poste Windows** (ancien apps/worker).
   - Il n'écoute sur aucun port. Il récupère le travail en HTTPS sortant, sur une voie kanban non-profil que Hermes prévoit : « control-plane lanes that pull via claim_task » (kanban_db_dispatch.py:2011-2017 ; skipped_nonspawnable :123-127), sur un tableau kanban dédié `poste` toujours nommé explicitement.
   - Il ne sert que les demandes créées par l'outil `poste_deleguer` (table `demandes` du greffon), jamais une carte libre.
   - Il lance Codex et Claude Code avec les connexions du propriétaire, de préférence sous un compte Windows local dédié qui n'a pas accès au profil du propriétaire (décision du propriétaire).
3. **Le client Qt natif existant**, rebranché sur Hermes : flux natif RFC 8252, JSON-RPC sur /api/ws, façade versionnée du greffon.
4. **Le navigateur et le téléphone** : le tableau de bord Hermes habillé, plus les pages du greffon, sur la même URL.

Préalable nouveau : **le déploiement Railway existant (modèle mazshakibaii) contient des données** sur un volume monté en /root/.hermes, écrites en root par un Hermes cloné sur `main` sans épinglage. Le passage à l'image officielle (/opt/data, uid 10000) est une migration outillée, pas un simple changement d'image (voir A13).

Point de départ : la proposition « natif ». Deux jurys sur trois l'ont retenue ; elle est à égalité avec « plugin » (46/60) mais devant sur la fidélité à la vision et sur le coût. Sa faiblesse, la sécurité et la tenue face aux montées de version, est corrigée par les garde-fous de « plugin », renforcés après lecture du source (A2, A4, A6, A12). S'y ajoutent trois idées de « bff ».

**ARBITRAGES**

**A1. Délégation : voie kanban.** Écartées : la file maison de « plugin » et la passerelle MCP de « bff ».
- Raisons :
  - c'est la primitive d'orchestration de Hermes ;
  - les cartes sont visibles dans l'onglet Kanban natif ;
  - Hermes fournit la reprise après expiration du délai de réclamation (DEFAULT_CLAIM_TTL_SECONDS, 15 min, kanban_db.py:276 ; reprise des réclamations non locales, kanban_db.py:2409-2470), le verrou expected_run_id, idempotency_key, le statut triage (kanban_db.py:103 et 1249-1270) et le signal « stranded_in_ready » (kanban-worker-lanes.md:135).
- Coût accepté : on importe des fonctions internes, **chacune depuis son module de définition** :
  - `hermes_cli.kanban_db` : create_task :1249, get_task, list_tasks, claim_task :2263, heartbeat_claim :2383, complete_task :2723, block_task :3208, request_review :3346 ;
  - `hermes_cli.kanban_db_connect.connect` :668 et `hermes_cli.kanban_db_dispatch.heartbeat_worker` :610. Dans `kanban_db`, `connect` et `heartbeat_worker` ne sont que des pointeurs PLUGIN-COMPAT (kanban_db.py:4520-4573) : depuis le 2026-09-14, un greffon qui les résout par l'ancien chemin est **désactivé** (COMPAT_MANIFEST.md:15-19 ; plugin_compat.py:32). Le bloc est encore présent à f97608f, mais inutilisable.
- Pourquoi c'est tenable : tous ces imports sont isolés dans kanban_adapter.py, couverts par `hermes plugins compat <chemin>` (plugins_cmd.py:2429, sortie 1 tant qu'un ancien chemin reste) et par des tests de contrat dans l'image épinglée ; `plugins.allow_deprecated_imports: false` est épinglé.
- Sûretés ajoutées, établies par le source :
  - `kanban.auto_decompose: false` épinglé. Par défaut (config_defaults.py:1907-1912), la passerelle décompose toute carte en triage par un LLM auxiliaire et la promeut (gateway/kanban_watchers.py:298-301 ; kanban_decompose.py:303-333). Sans ce réglage, la « validation avant exécution » serait contournée et le cerveau consommé ;
  - `kanban.dispatch_profiles` épinglé sur la liste des vrais profils (défaut None = tout profil existant, config_defaults.py:1901-1906 ; filtre fail-closed, kanban_db_dispatch.py:1633-1658) : un profil nommé plus tard « poste-windows » ne pourra pas être lancé sur Railway ;
  - `review_dispatch` n'a pas à être coupé : les cartes en revue d'un assignee non-profil tombent dans le même contrôle (kanban_db_dispatch.py:2006-2017 et 2248-2253) ;
  - `max_runtime_seconds` n'est **pas** appliqué par Hermes à un réclamant distant (enforce_max_runtime ne traite que worker_pid non nul et le préfixe d'hôte local, kanban_db_dispatch.py:648-672) : la durée maximale est appliquée par le poste (Job Object) et contrôlée par le greffon ;
  - une réclamation expirée compte comme un échec (kanban_db.py:2409-2416) et `failure_limit: 2` bloque la carte (config_defaults.py:1870-1872) : deux mises en veille du PC en cours de carte la bloquent. C'est affiché, pas masqué ;
  - `detect_stale_running` reprend toute carte en cours depuis plus de `dispatch_stale_timeout_seconds` (14 400 s) sans `last_heartbeat_at` récent, quel que soit l'hôte (kanban_db_dispatch.py:748-790) ; `heartbeat_claim` ne touche que `claim_expires` (kanban_db.py:2383-2399). Le poste appelle donc les deux battements.
- Plan B, écrit mais pas construit : une file propre au greffon dans plugin_db (plugin_storage.py:36-47), activée seulement si une montée de version casse le contrat.

**A2. Greffons groupés dans /opt/hermes**, arbre root en lecture seule, et **/opt/data/plugins et /opt/data/dashboard-themes rendus propriété de root (0755) à chaque démarrage** par `05-acp`.
- La source « user » est lue en premier et masque un homonyme groupé (web_server_dashboard.py:464-494). Le dédoublonnage du tableau de bord se fait sur le champ `name` du manifeste, pas sur le nom du dossier (web_server_dashboard.py:546-563) : n'importe quel dossier peut se déclarer `acp-poste`.
- L'API Python d'un greffon « user » est importée s'il figure dans `plugins.enabled` (web_server_dashboard.py:790-795). Or `acp-poste` y figure : un homonyme utilisateur serait exécuté. La garde par nom de dossier `/opt/data/plugins/acp-*` ne suffit donc pas.
- Les thèmes sont relus à chaque requête (web_server_dashboard.py:414-431) : un `customCSS` modifié à chaud pourrait maquiller les boutons d'approbation.
- L'agent tourne en uid 10000 sans sudo (Dockerfile:81, 167-168, 351-353) ; un répertoire root 0755 lui est inaccessible en écriture. Le propriétaire renonce aux greffons installés à chaud : tout greffon passe par l'image.

**A3. Profil racine, sans distribution de profil.** Inchangé : une distribution ne peut pas viser « default » (profile_distribution.py:337-341) ; chaque profil nommé a son créneau de passerelle s6 (docker/cont-init.d/02-reconcile-profiles) ; plugin_data_dir suit le profil actif (plugin_storage.py:27-33) ; thèmes, greffons et fournisseurs d'authentification dépendent du HERMES_HOME de lancement (web_server_dashboard.py:414-490 ; plugins.py:747-770). Réglages prêts : managed scope (fusion feuille par feuille, managed-scope.md:75-91), `skills.external_dirs` en lecture seule (config_defaults.py:1426), semence de SOUL.md avec marqueur d'empreinte (voir architecture).

**A4. Authentification : fournisseur Nous Portal**, sans code d'authentification maison, **verrouillé contre la substitution**.
- Côté Hermes, le fournisseur Nous ne tient aucune liste d'utilisateurs : il vérifie la signature, `aud` = client_id, l'émetteur et `agent_instance_id` (nous/__init__.py:91-110). « Every login is verified against your Nous account » (web-dashboard.md:630, 658) signifie que l'autorisation est déléguée au Portail. À prouver en P2 par un refus d'un second compte Nous.
- Le `.env` de /opt/data est chargé avec override=True et gagne sur les variables Railway (env_loader.py:433-435) ; la managed scope est appliquée en dernier (env_loader.py:473 et 503-517). `config.yaml` est modifiable par l'agent (agent/file_safety.py:191-194) et son terminal peut écrire `.env`. Sans verrou, un agent victime d'une injection pourrait, au redémarrage suivant, changer `HERMES_DASHBOARD_OAUTH_CLIENT_ID` ou `HERMES_DASHBOARD_PORTAL_URL` (nous/__init__.py:127-131), ou ajouter un mot de passe (`dashboard.basic_auth`, basic/__init__.py:213-243) ou un émetteur OIDC (`dashboard.oauth.self_hosted`, self_hosted/__init__.py:281-302). D'où :
  - `/etc/hermes/.env` régénéré par `05-acp` avec l'identifiant client, l'URL du Portail, l'URL publique, et des valeurs vides pour HERMES_DASHBOARD_BASIC_AUTH_*, HERMES_DASHBOARD_OIDC_* et HERMES_DASHBOARD_DRAIN_SECRET ;
  - dans le `config.yaml` géré : les mêmes clés `dashboard.oauth.*` et `dashboard.basic_auth.*` épinglées, et `plugins.disabled: [dashboard_auth/basic, dashboard_auth/self_hosted, dashboard_auth/drain]` (clés : plugins_cmd.py:1206).
- Repli : self_hosted (OIDC) sur un tenant dédié à inscription fermée ; il n'a pas non plus de liste blanche locale (self_hosted/__init__.py:258-270). Le fournisseur basic reste écarté (web-dashboard.md:629).

**A5. Discussion : JSON-RPC sur /api/ws**, et non /v1/runs.
- api_server est classé « sans surveillance » : commandes dangereuses refusées d'office (tools/approval_context.py:131-133).
- L'image **génère elle-même** une API_SERVER_KEY dans /opt/data/.env à chaque démarrage si elle manque (stage2-hook.sh:459-540), et toute clé utilisable active l'api_server (gateway/config_env.py:307-315). On ne peut donc pas l'éteindre sans forker l'amorçage : on le garde **en boucle locale** (API_SERVER_HOST=127.0.0.1 épinglé dans le `.env` géré), non exposé, non utilisé par ACP.
- /chat, le TUI, est conservé.

**A6. Écritures sur le PC : double contrôle, garantie reformulée.**
- Validation AVANT l'exécution : la carte naît en triage (auto-décomposition coupée, A1) ; la table `demandes` du greffon porte les paramètres structurés.
- Signature WebAuthn vérifiée par le poste, **une par tentative** : le défi couvre la demande, la consigne, le numéro de tentative et un nonce ; le poste garde les nonces consommés. « Demander des changements » (request_changes, kanban_db.py:3495) exige une nouvelle signature ; le poste n'injecte jamais un commentaire kanban non signé dans l'exécutant.
- Revue du diff APRÈS l'exécution ; rien n'est poussé ni fusionné ; la fusion reste un geste local du propriétaire.
- Garantie exacte : un Railway compromis ne peut pas déclencher d'écriture **sans un geste du propriétaire**. Il peut en revanche afficher une carte A et faire signer l'empreinte d'une carte B, car la page de signature est servie par Railway ; et la comparaison d'empreinte à l'enrôlement passe par une page Railway. D'où : dépôts jetables d'abord, liste blanche locale, revue du diff, et option de confirmation locale sur le PC pour les dépôts réels.

**A7. Quotas : jamais `hermes usage` ni /usage pour les abonnements.** Inchangé : wham/usage en « codex-cli » (account_usage.py:376), oauth/usage en « claude-code/2.1.0 » (:597). On garde leur schéma (hermes_cli/subcommands/usage.py:15-35).

**A8. Déploiement : Railway construit le Dockerfile dérivé**, avec « Wait for CI » (rw_full.txt:29670-29694), ce qui marche sur l'offre Hobby. Un registre GHCR privé exige l'offre Pro (rw_full.txt:29272). Option : image GHCR publique déployée par condensat.

**A9. Notifications : abonnement kanban natif** (route home-subscribe, plugins/kanban/dashboard/plugin_api.py:1185 ; notify_in_gateway, config_defaults.py:1861) vers un DM Telegram limité au propriétaire. Web Push reporté.

**A10. Desktop : on garde SseParser et EventStreamService** (adaptés au bearer). Le client refuse une majeure de contrat incompatible ; simple avertissement si Hermes n'est pas la version testée. Le bundle web vérifie `window.__HERMES_PLUGIN_SDK__.sdkVersion` (1.1.0, web/src/plugins/registry.ts:106 et 121).

**A11. Nom : « ACP » reste la marque du propriétaire.** Identifiants `acp-interface` et `acp-poste` ; pas de collision avec `hermes acp` (hermes_cli/main.py:2803) ni avec acp_adapter.

**A12. Lectures sur le PC : risque d'exfiltration traité.**
- Hermes lit le web ; une injection peut lui faire déléguer « lis tel fichier et résume-le ». La consigne d'une carte en lecture est exécutée sans validation, et le résultat remonte sur Railway.
- Rien ne prouve que le bac à sable read-only de Codex ou l'outil Read de Claude empêchent de lire hors du dépôt sous Windows natif : à prouver en P5, sans le supposer.
- `--ignore-user-config` (executors.py:611-613) annule un réglage `cli_auth_credentials_store = "keyring"` écrit dans config.toml : il faut le passer en `-c` sur la ligne de commande, sinon les jetons restent dans auth.json en clair (valeurs possibles : file, keyring, auto, ephemeral ; research.json, clé codex-quotas).
- Parades : compte Windows local dédié au poste, sans accès au profil du propriétaire ; identifiants des CLI dans le coffre Windows ; balayage de secrets des sorties avant envoi, en échec fermé ; taille de résultat bornée ; au départ, lectures validées aussi (décision du propriétaire).

**A13. Migration du déploiement existant.**
- Le modèle monte son volume sur /root/.hermes (hermes-railway/RAILWAY.md:45, auth_proxy.py:15), tourne en root, et clone `main` à chaque construction (Dockerfile:12), avec `git pull` au démarrage (entrypoint.sh:4-16). Les données peuvent donc venir d'une version **plus récente** que v2026.9.24.
- L'image officielle utilise /opt/data (Dockerfile:428) en uid 10000. Son amorçage ne re-possède que la racine, une liste de sous-dossiers (stage2-hook.sh:228-254) et une liste de fichiers (:345-359) : `kanban.db`, `SOUL.md`, `plugins/`, `dashboard-themes/` resteraient en root, donc non inscriptibles.
- Le service est aujourd'hui géré par Config as Code (railway.toml du modèle, `startCommand = "/entrypoint.sh"`). Un service ne peut pas être géré par les deux systèmes (rw_infrastructure-as-code.md:40-44), et un fichier IaC de projet entier supprime toute ressource omise (:333).
- D'où une étape dédiée en P2 : sauvegarde, contrôle de versions, import IaC par `railway config pull`, plan sans destruction, même volume remonté sur /opt/data, reprise de propriété unique, commande de démarrage vidée.

## 3. Architecture

**COMPOSANTS**

**1. Service Railway « hermes »** : une réplique, le volume existant remonté sur /opt/data.
- **Image** : `FROM nousresearch/hermes-agent:v2026.9.24@sha256:<condensat relevé en P1>`. Tags de release : docker.yml:336-343 (`:latest` et `:main` suivent main, proscrits).
- **`CMD ["gateway","run"]`** dans le Dockerfile dérivé. L'image de base a `CMD []` (Dockerfile:513) ; le service s6 `main-hermes` n'est qu'un `sleep infinity` (docker/s6-rc.d/main-hermes/run) ; c'est le CMD `gateway run` qui fait superviser la passerelle par s6 (docker.md:56-62). Aucune Start Command Railway.
- **PID 1** : si la plateforme n'attribue pas le PID 1 à l'ENTRYPOINT, entrypoint-dispatch saute /init, donc cont-init.d et le tableau de bord (entrypoint-dispatch.sh:17-26 ; docker.md:517). À prouver sur Railway en P2 (`/proc/1/cmdline`).
- **`ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2`** : avec la valeur par défaut, s6 continue en silence quand un script cont-init échoue ; l'image ne la fixe pas (Dockerfile:126-147).
- **Processus** :
  - `gateway run`, supervisé par s6 via le CMD, qui porte le cron, le dispatcher kanban (dispatch_in_gateway, config_defaults.py:1864) et la messagerie ;
  - le tableau de bord (HERMES_DASHBOARD=1, 0.0.0.0:9119), service s6 (docker/s6-rc.d/dashboard/run), derrière le portail Nous ;
  - l'api_server de la passerelle, **en boucle locale seulement** (clé générée par l'image, stage2-hook.sh:459-540), non exposé : Railway ne route que le port 9119.
- **Ajouts de l'image dérivée** :
  - /etc/hermes/config.yaml : managed scope, root 0644, aucun secret ;
  - /opt/hermes/plugins/{acp-interface, acp-poste} ;
  - /opt/acp/skills, /opt/acp/{persona, theme}, en lecture seule ;
  - /etc/cont-init.d/05-acp, avec l'en-tête `#!/command/with-contenv sh` (sans lui, le script ne voit pas l'environnement du conteneur ; même motif que 01-hermes-setup, Dockerfile:402-405).
- **Script 05-acp** : root, après 01-hermes-setup, 015-supervise-perms et 02-reconcile-profiles (ordre lexicographique), idempotent.
  - (a) Refus de démarrer, message en français, si :
    - un manifeste sous /opt/data/plugins (`plugin.yaml` ou `dashboard/manifest.json`) porte un nom `acp-*` ;
    - HERMES_MANAGED_DIR est défini ;
    - une variable interdite est présente dans l'environnement du conteneur (liste dans la partie Railway) ;
    - HERMES_DASHBOARD_PUBLIC_URL n'est pas en https, ou l'identifiant client n'a pas la forme `agent:…` ;
    - /etc/hermes/config.yaml ne se parse pas (un fichier géré invalide est ignoré en silence, managed_scope.py:73-93).
  - (b) Génère /etc/hermes/.env (root 0644) depuis les variables Railway validées : HERMES_DASHBOARD_OAUTH_CLIENT_ID, HERMES_DASHBOARD_PORTAL_URL=https://portal.nousresearch.com, HERMES_DASHBOARD_PUBLIC_URL, API_SERVER_HOST=127.0.0.1, HERMES_LANGUAGE=fr, et des valeurs vides pour HERMES_DASHBOARD_BASIC_AUTH_*, HERMES_DASHBOARD_OIDC_* et HERMES_DASHBOARD_DRAIN_SECRET. Aucun secret.
  - (c) Rend /opt/data/plugins et /opt/data/dashboard-themes propriété de root (0755), puis y dépose le thème `acp` (root 0644).
  - (d) SOUL.md : pose le SOUL livré si le fichier est identique au SOUL de l'image officielle (seed_one, stage2-hook.sh:457) ou à la dernière version déposée (empreinte dans /opt/data/acp/soul.sha256). Sinon il ne touche à rien et le signale dans /v1/meta.
  - (e) Migration unique : si /opt/data/acp/migration-faite est absent, `chown -R hermes:hermes /opt/data` (sauf les répertoires rendus root en c), puis pose du marqueur.

**2. Greffon `acp-interface`** (tableau de bord seulement) : manifeste et bundle IIFE ; React vient de `window.__HERMES_PLUGIN_SDK__` ; vérification de la majeure de `sdkVersion`.

**3. Greffon `acp-poste`** (agent et tableau de bord), activé par `plugins.enabled`, épinglé.
- **`register(ctx)`** (exécuté dans chaque processus Hermes, sous `plugins.load_timeout_seconds`) enregistre :
  - les outils `poste_*` (ctx.register_tool, plugins.py:456) ;
  - le fournisseur de jeton machine (register_dashboard_auth_provider, plugins.py:747 ; supports_token et verify_token, base.py:105-147 ; comparaison `hmac.compare_digest`) ;
  - des routes à jeton en chemin exact (register_token_route, token_auth.py:31-40), sur le modèle de drain (drain/__init__.py:138-156).
- **`dashboard/plugin_api.py`** monté au démarrage sous /api/plugins/acp-poste/ (web_server_dashboard.py:798-872) ; toute opération SQLite ou kanban en `run_in_threadpool`, le long-poll en attente asynchrone : le ping WebSocket tourne sur la boucle de l'agent (web_server.py:1158-1164).
- **`kanban_adapter.py`**, seul module qui importe l'interne kanban (modules de définition, A1), toujours avec `board="poste"`.
- **Données** : `ACP_DATA_DIR=/opt/data/acp`, SQLite en WAL : `demandes` (paramètres structurés, id de session, tentative), postes (SHA-256 du jeton), approbations signées, relevés de quotas, battements. Inscriptible par l'agent (même frontière que /opt/data) : l'intégrité de ces données n'est pas garantie contre un Railway compromis, et le poste ne s'y fie pas pour autoriser une écriture.

**4. Poste Windows** (apps/poste)
- Recommandé : tâche planifiée « exécuter même si l'utilisateur n'est pas connecté » sous un compte Windows local standard dédié ; CLI connectées dans ce compte par le propriétaire ; dépôts clonés dans ce compte. Repli : compte du propriétaire, risque d'exfiltration accepté par écrit.
- venv sur le Python de python.org. Aucune écoute réseau. HTTPS sortant uniquement, vers /api/plugins/acp-poste/machine/v1/*.

**5. Client Qt** (apps/desktop) : HTTPS et WSS sortants ; écoute 127.0.0.1, port éphémère, le temps d'une connexion RFC 8252.

**6. Navigateur et téléphone** : même domaine.

**FLUX**

**a) Discussion** (web et Qt)
1. POST /api/auth/ws-ticket : ticket de 30 s, en mémoire (routes.py:458-467).
2. WSS /api/ws, sous-protocoles `hermes-gateway-v1` et `hermes-gateway-ticket.<t>` (web_server_chat.py:202-217).
3. `gateway.ready`, puis `client.capabilities {server_requests:true}` (programmatic-integration.md:98). Réponse -32601 aux requêtes serveur non gérées (secret, sudo, vault.*, terminal.read…) (:96).
4. session.*, prompt.submit, événements, approval.respond, réponses clarify.
5. Reprise : `session.events.since` (epoch, truncated, open_requests). OpenRPC `info.version` « 1 », 237 méthodes (apps/shared/src/gateway-contract.openrpc.json).
L'agent tourne dans le processus du tableau de bord (chat_ws.py:583-600).

**b) Délégation**
1. `poste_deleguer` lit l'identifiant de session côté serveur (gateway.session_context, session_context.py:82-92), enregistre la demande dans `demandes`, puis crée la carte (board `poste`, assignee `poste-windows`, idempotency_key). Lecture : `ready` (ou `triage` tant que les lectures sont validées). Écriture : `triage`. Le dispatcher la range en skipped_nonspawnable.
2. Validation : le propriétaire signe en WebAuthn le défi (demande, consigne canonique, tentative, nonce, expiration) sur /travaux ; la route stocke l'assertion et passe la carte en `ready`.
3. Le poste réclame en long-poll (25 s au plus), seulement les cartes présentes dans `demandes`. Réclamant `poste-windows:<id>:<uuid>`, non local à l'hôte : reprise à expiration (kanban_db.py:2409-2470).
4. Le poste vérifie sa politique locale, la signature, le nonce non consommé, puis exécute les **paramètres structurés** de la demande, jamais le corps libre de la carte ni ses commentaires.
5. Toutes les 60 s : `heartbeat_claim` et `heartbeat_worker(expected_run_id)`. Si l'un renvoie faux, il tue l'arbre de processus.
6. Fin : lecture par `complete_task(expected_run_id)` après balayage de secrets ; écriture par `request_review` (sans `reviewer`), avec le diff ; échec par `block_task`, raison en français.
7. Le propriétaire valide dans /travaux ou dans l'onglet Kanban natif (`review → done`, complete_task accepte ce passage, kanban_db.py:2729-2744) ; la fusion de la branche locale reste un geste manuel sur le PC.

**c) Retour dans la conversation** : tâche courte, `poste_suivre` attend dans une limite ; tâche longue, bannière et notification puis bouton « Reprendre » vers la session d'origine enregistrée dans `demandes`.

**d) Quotas** : le poste pousse au schéma de `hermes usage --json` vers /machine/v1/quotas ; web, Qt et `poste_quotas` lisent cette source.

**e) Montée de version** : uniquement par une PR qui change le condensat. Jamais de `git pull`, jamais de `hermes update`.

**FRONTIÈRES DE CONFIANCE**
- **Accéder au tableau de bord revient à exécuter du code dans le conteneur** (/api/env/reveal, PTY, serveurs MCP stdio). D'où un seul utilisateur, Nous verrouillé (A4), `approvals.mode: manual`.
- **L'agent Railway a un terminal non isolé et écrit dans /opt/data** (config.yaml, .env par le terminal, /opt/data/acp). Aucune clé de sécurité n'y vit : elles sont dans la managed scope, régénérée par root à chaque démarrage. Aucun identifiant d'abonnement du PC n'est sur Railway ; seul le SHA-256 du jeton du poste y est.
- **Railway ne décide d'aucun effet sur le PC sans geste du propriétaire.** La politique locale `%LOCALAPPDATA%\ACP\poste.toml` fait autorité ; toute écriture exige une signature par tentative. Limite assumée : la page de signature est servie par Railway (A6).
- **Les routes machine vérifient `request.state.token_principal.provider == "acp-poste"`.** Seuls les fournisseurs `supports_token` sont essayés (registry.py:83-87) : aujourd'hui drain, s'il est activé. Le bearer de session Nous du propriétaire n'y est pas accepté ; la vérification reste une défense en profondeur.
- **IP client** : `client_ip` lit `X-Forwarded-For` brut, sans tenir compte de `trusted_proxies` (request_utils.py:18-21) ; les IP des journaux sont usurpables.
- **Une seule réplique** : flux natif et tickets WS en mémoire (native_flow.py:11-12), état en SQLite.

**CE QUI A ÉTÉ VÉRIFIÉ**
Aucune commande Hermes n'a été exécutée. Le plan repose sur la lecture du clone f97608f (code et docs), du modèle Railway local, de l'étiquette d'archive 60a49b6 et des documents Railway locaux. Context7 a servi pour les sous-protocoles QWebSocket (Qt 6.4+) et S6_BEHAVIOUR_IF_STAGE2_FAILS.

## 4. Interface web

**Principe**
- ACP n'a pas d'application web propre.
- On ne surcharge pas HERMES_WEB_DIST : l'image le fixe déjà sur le bundle livré (Dockerfile:410 ; lu par web_server.py:59). Le changer serait un fork.
- On habille et on étend le tableau de bord uniquement par les couches que Hermes supporte.

**1. Thème `acp`**
- `scripts/generer_themes.py` le génère depuis `design/tokens/*.json`, même source que le QML (`apps/desktop/cmake/generate_design_tokens.py`, étendu).
- Palette, typographie, mise en page, logo, componentStyles, customCSS ≤ 32 Kio (extending-the-dashboard.md:279).
- Déposé par `05-acp` dans un /opt/data/dashboard-themes root 0755 (A2), épinglé actif (`dashboard.theme: acp`, défaut config_defaults.py:977).

**2. Greffon `acp-interface`**
- **Accueil** : remplace « / » (tab.override, extending-the-dashboard.md:461-480), pensé d'abord pour le téléphone : état de Hermes (/api/status), poste et dernier battement, quotas, cartes à valider, dernières sessions.
- **/discussion** : chat tactile en JSON-RPC.
  - Liste et reprise des sessions ; affichage progressif de `message.delta` ; cartes d'outils repliables.
  - Approbations et clarify en feuilles plein écran, avec les choix fournis par l'hôte.
  - Requêtes serveur non gérées (secret, sudo, vault.*, terminal.read, preview.act…) : réponse -32601 et message « Non pris en charge ici, utilisez /chat ». Aucune saisie de secret sur le téléphone.
  - Bouton « Interrompre ».
  - Retour de veille : `session.events.since`, puis `session.history` si `truncated`.
  - Markdown par marked, assaini par DOMPurify, embarqués ; le tableau de bord n'envoie aucune CSP, l'assainissement est la seule barrière.
  - Cibles tactiles ≥ 44 px, `env(safe-area-inset-*)`, saisie fixée en bas.
- **/travaux** : cartes du tableau `poste`, filtrées par état.
  - Actions : « Valider et signer » (WebAuthn), « Refuser », « Annuler ».
  - Affichage : résumé, consigne canonique exacte signée, diff tronqué, journal, numéro de tentative.
  - « Demander des changements » ouvre une nouvelle signature.
  - Bouton « Reprendre dans la discussion ».
- **/quotas** : une jauge par fenêtre, source, âge du relevé, heure de remise à zéro ; « Périmé », « Inconnu », « même enveloppe ».
- **/poste** : associer le poste (jeton affiché une seule fois), enregistrer la passkey et afficher son empreinte, révoquer, dernier battement, politique déclarée. rpId = domaine du service ; `up.railway.app` étant un suffixe public (psl.dat:15441), un domaine personnalisé stable est recommandé, sinon un renommage du service invalide la passkey.
- **/catalogue** : compare `catalogue.lock.json` à l'installé (GET /api/skills, GET /api/mcp/servers, test des MCP), signale les collisions de noms. Pas de bouton « installer ».
- **Emplacements** (web/src/plugins/slots.ts:24-26 ; App.tsx:577, 617, 728) : header-left (marque), header-banner (poste hors ligne, quota ≥ 90 %, carte à valider, greffon masqué, SOUL divergent), header-right (badge de quota). `analytics:top` n'est pas utilisé : la page Analytics est masquée tant que `dashboard.show_token_analytics` est faux (défaut, config_defaults.py:983-987 ; App.tsx:414-468).
- **/chat n'est pas remplacé** (web/src/App.tsx:431-450).

**3. Français**
- Le SPA démarre en anglais tant que `hermes-locale` est vide (web/src/i18n/context.tsx:50-64). Un composant invisible appelle une fois `SDK.useI18n().setLocale('fr')` (useI18n exposé, registry.ts:190).
- Nos pages sont entièrement en français, catalogue de chaînes unique ; un test fait échouer le build si une chaîne visible est hors catalogue. Les messages d'erreur de l'API Hermes (`detail` en anglais) sont enveloppés dans un message français, le détail brut restant repliable.
- Pages natives en partie en anglais : `fr.ts` 785 lignes contre 921 pour `en.ts`. Décompte publié ; ajouts proposés en amont (MIT).
- Côté agent : `HERMES_LANGUAGE=fr` (.env géré) et `display.language: fr` ne traduisent que les messages statiques (approbations, quelques réponses de passerelle), pas les réponses de l'agent (config_defaults.py:875-877 ; agent/i18n.py:1-5). Les réponses en français viennent de SOUL.md. Le TUI de /chat reste en anglais : limite publiée.

**4. Temps réel du greffon**
- SSE `GET /api/plugins/acp-poste/v1/flux` : travaux, quotas, poste.
- Keepalive 15 s ; fermeture serveur avant 14 min ; reprise par Last-Event-ID. Railway coupe une requête HTTP à 15 min ou après 5 min sans données ; WebSocket exemptés (rw_full.txt:33402).
- Pas de WebSocket de greffon : le middleware HTTP ne s'applique pas aux WebSocket (web_server_chat.py:167-169).

**5. Téléphone** : même URL, connexion Nous (jeton de rafraîchissement tournant de 24 h, nous/__init__.py:1-8 : après 24 h d'inactivité, nouvelle connexion). Ni PWA ni Web Push en v1 ; notifications par Telegram.

**6. Fabrication et tests**
- TypeScript, esbuild en IIFE ; Vitest ; axe.
- Playwright en 390×844 et 1440×900 contre l'image épinglée lancée en CI, HERMES_HOME jetable, modèle factice compatible OpenAI.
- Routes du greffon montées au démarrage seulement (extending-the-dashboard.md:916) : chaque livraison passe par un redéploiement.

## 5. Client desktop

On garde le client Qt 6.8 / C++23 / QML (CMakeLists.txt:50), sans WebView ni Electron. Le desktop officiel de Hermes est en Electron : on ne le reprend pas.

Le client ne parle qu'aux API de Hermes et du greffon. Jamais aux fichiers ni à la base de Railway.

**AUTHENTIFICATION** (flux natif RFC 8252 de Hermes)
1. `QTcpServer` sur 127.0.0.1:0 ; Hermes refuse `localhost` (routes.py:217-229).
2. Paire PKCE S256, navigateur système (`QDesktopServices`) sur `GET /auth/native/authorize?provider=nous&code_challenge=…&code_challenge_method=S256&redirect_uri=http://127.0.0.1:<port>/rappel&state=…`.
3. Code valable 120 s (native_flow.py:28) ; `POST /auth/native/token {code, code_verifier}` rend access_token, refresh_token, expires_at, provider, user_id (routes.py:475-490).
4. Bearer accepté partout (middleware.py:150-170). Rafraîchissement : `POST /auth/native/refresh` ; 401 `session_expired` déclenche une nouvelle connexion (routes.py:496-519).

**Stockage des jetons**
- Jeton d'accès en mémoire.
- Jeton de rafraîchissement dans le Gestionnaire d'identification Windows (`WindowsCredentialVault`).
- Nous fait tourner ce jeton toutes les 24 h avec détection de réutilisation (nous/__init__.py:1-8) : écriture atomique, une seule instance, un seul rafraîchissement à la fois ; après 24 h sans usage, nouvelle connexion.

**TRANSPORT**
- **REST en bearer** : /api/status, /api/sessions*, lecture de /api/skills, /api/mcp/servers, /api/cron/jobs, et /api/plugins/acp-poste/v1/*.
- **Discussion en QWebSocket** (`Qt6::WebSockets`, pas WebEngine) : `QWebSocket::open(url, QWebSocketHandshakeOptions)` avec `setSubprotocols({"hermes-gateway-v1", "hermes-gateway-ticket.<t>"})` (Qt 6.4+). Sans en-tête Origin, accepté (web_server_chat.py:165-189) ; l'en-tête Host doit correspondre à l'URL publique. Ticket par `POST /api/auth/ws-ticket` avec le bearer.
- **Client JSON-RPC** (`JsonRpcChannel`, C++) limité aux méthodes utiles ; -32601 pour les requêtes serveur non gérées ; tests de conformité contre l'OpenRPC épinglé ; fixtures générées depuis les modèles Pydantic du greffon.
- **Flux du greffon** : `SseParser` et `EventStreamService`, adaptés au bearer (la gestion de cookie actuelle est retirée).

**COMPATIBILITÉ**
`CompatibiliteHermes` remplace `CompatibilityService` et l'ancien contrat /meta d'ACP.
- Il lit `/api/status` (publique) et `/api/plugins/acp-poste/v1/meta` : contrat « acp-poste/1 », version du greffon, version de Hermes, info.version de l'OpenRPC, condensat de l'image, alerte de greffon masqué, état de la managed scope, SOUL divergent.
- Refus en français si la majeure du contrat ou la version OpenRPC diffère ; simple avertissement si Hermes n'est pas la version testée.
- États : Hermes injoignable « Hors ligne » ; quotas trop vieux « Périmé » puis « Inconnu ».

**PAGES**
- **Discussion.**
- **Travaux.** « Valider » ouvre le navigateur système sur /travaux/<id> (la cérémonie WebAuthn exige une origine web).
- **Quotas** : `QuotasPage`, `SubscriptionQuotasViewModel`, `QuotaGauge`, branchés sur la nouvelle source.
- **Poste** : état et battement. « Associer ce poste » crée le jeton et l'affiche une fois ; l'enrôlement se fait dans le compte du poste (invite masquée de `acp-poste enroler`). Si le poste tourne dans le compte du propriétaire, le jeton peut être passé par stdin.
- **Réglages**, en lecture seule, renvoi vers le web.
- **Diagnostics.**
- **Sauvegarde** : export chiffré par DPAPI (voir Railway).
- La route office reste `OutOfScope` (NavigationModel.cpp:51-52).

**CONSERVÉ**
- src/api : ApiClient, ApiError, ApiRequest, Cursors, IdempotencyKey (en-têtes cookie et CSRF retirés).
- src/events : SseParser, EventStreamService, Backoff, StreamScope.
- src/storage : CredentialVault, WindowsCredentialVault, SettingsStore (sans aucun secret).
- SystemAppearance, CommandRegistry, NavigationModel, Redaction, JsonListModel, UpdateService, ArtifactDownload (pièces jointes kanban).
- HealthService **adapté** : il interroge aujourd'hui /health et /ready d'ACP (HealthService.cpp:157 et 185) ; il passe sur /api/health et /api/status, /ready disparaît.
- QML : controls, components, shell, thème généré. Tests génériques.
- desktop-ci.yml (windows-2022), desktop-release.yml, packaging/windows ; `WebSockets` ajouté à `find_package(Qt6 …)` et qtwebsockets à toolchain.json.

**RETIRÉ** (consultable sous l'étiquette d'archive)
- AuthManager (amorçage, cookie, CSRF), SessionCookieJar, CompatibilityService.
- ViewModels Missions, Operations, Artifacts, Platform, Workspace, Conversations.
- Pages Studio, Run, Operations, Extensions, Missions, Platform, Projects.

**BINAIRES** : non signés, et on le dit explicitement.

## 6. Abonnements et délégation

**POURQUOI UN POSTE WINDOWS**
- Hermes exécute ses délégations sur son propre hôte (configuration.md:269-280).
- Ses voies vers une autre machine (ssh, MCP HTTP, A2A, peer) exigent une connexion entrante vers le PC.
- L'OAuth Claude de Hermes ne consomme que des crédits Max supplémentaires achetés ; Pro exclu (providers.md:142-148).
- Emprunter `~/.claude/.credentials.json` ou `~/.codex/auth.json` invalide les jetons tournants (security.md:671-677) ; `auth.adopt_external_logins` vaut `true` par défaut (config_defaults.py:1724) : épinglé à `false`.

**VOIE KANBAN `poste-windows`, tableau `poste`**
- **Outils de l'agent** (`ctx.register_tool`) :
  - `poste_deleguer(executeur: codex|claude, depot: alias, consigne, mode: lecture|ecriture, delai_max_s, cle_idempotence)` : enregistre la demande (paramètres structurés et session lue côté serveur), puis `create_task(board="poste", assignee="poste-windows", idempotency_key, triage=…)` (kanban_db.py:1249-1270). `max_runtime_seconds` n'est posé que pour l'affichage : Hermes ne l'applique pas à un réclamant distant (kanban_db_dispatch.py:648-672) ;
  - `poste_suivre(carte, attente ≤ 240 s)`, `poste_etat`, `poste_annuler`, `poste_quotas`.
- **Cartes hors greffon** : l'agent dispose aussi des outils kanban natifs (tools/kanban_tools.py) et peut créer une carte `poste-windows` sans passer par `poste_deleguer`. Le poste ne sert que les cartes présentes dans `demandes` ; les autres sont bloquées avec « Carte non émise par acp-poste ».
- **Skill maison `acp-delegation`**, en français, chargée automatiquement (`skills.auto_load`, config_defaults.py:1440) : choix entre Codex, Claude Code et Hermes lui-même selon la tâche et `poste_quotas` ; clé d'idempotence obligatoire. L'identifiant de session n'est plus confié au modèle.
- **Garde de quota** : au-delà de 90 % de la fenêtre de 5 h de l'exécutant (seuil réglable), refus en français avec l'heure de remise à zéro ; quota inconnu : avertissement explicite, sans refus ; une carte à la fois par exécutant.
- **Routes machine** : chemins exacts, jeton seulement (token_auth.py:31-40) : `/api/plugins/acp-poste/machine/v1/{reclamer, battement, evenements, terminer, revue, bloquer, quotas}` ; chaque gestionnaire vérifie le fournisseur ; long-poll ≤ 25 s.
- **Jeton machine** : 256 bits, affiché une fois ; Railway ne garde que son SHA-256, comparé à temps constant ; le PC le garde sous DPAPI (credentials_protection.py:52) ; révocation = 401 immédiat.
- **Cycle d'une carte** :
  - Lecture : (`triage` → signature, tant que les lectures sont validées) → `ready` → `running` → balayage de secrets → `done` par `complete_task(expected_run_id)`.
  - Écriture : `triage` → signature → `ready` → `running` → `review` (`request_review`, sans `reviewer`, avec le diff) → `done`. Changements demandés : nouvelle consigne, nouvelle signature.
  - Échec : `block_task`, raison en français. Après `BLOCK_RECURRENCE_LIMIT` blocages identiques, Hermes renvoie la carte en `triage` (kanban_db.py:3317-3327) : sans auto-décomposition, elle y attend le propriétaire.
  - Battement : `heartbeat_claim` et `heartbeat_worker(expected_run_id)` toutes les 60 s.
  - Poste absent : `stranded_in_ready` au bout de 30 min (kanban-worker-lanes.md:135 ; kanban_diagnostics.py:682-726), bannière « Poste hors ligne ». Deux expirations de réclamation bloquent la carte (failure_limit 2).

**VALIDATION SIGNÉE DES ÉCRITURES**
- **Enregistrement de la passkey** : sur /poste, `navigator.credentials.create` (rpId = domaine) ; le poste récupère la clé publique à l'enrôlement, la garde localement et en affiche l'empreinte. Confiance au premier usage, consignée : la comparaison passe par une page servie par Railway et ne protège pas contre un Railway déjà compromis à ce moment.
- **Validation d'une tentative** : défi = SHA-256 du JSON canonique (id de demande, exécutant, dépôt, mode, consigne, délai, tentative, nonce, expiration) ; `navigator.credentials.get` ; la route stocke l'assertion et passe la carte en `ready`.
- **Vérification par le poste** : défi recalculé depuis la demande, origine `https://<domaine>`, rpIdHash, UP et UV, signature avec la clé locale, compteur, expiration, nonce jamais vu. Échec : `block_task` « Approbation signée absente ou invalide ». Une carte passée en `ready` depuis l'onglet Kanban natif sans signature est donc refusée.
- **Limite** : la page de signature est servie par Railway ; un Railway compromis peut montrer un contenu et en faire signer un autre. D'où les dépôts jetables d'abord, la revue du diff, et l'option de confirmation locale sur le PC pour les dépôts réels.

**EXÉCUTION SUR LE PC** (code ACP conservé)
- **Compte** : recommandé, compte Windows local standard dédié (`acp-poste`), sans accès à C:\Users\<propriétaire> ; tâche planifiée « exécuter même si l'utilisateur n'est pas connecté ». Repli : compte du propriétaire.
- **Politique locale** `%LOCALAPPDATA%\ACP\poste.toml` du compte du poste, jamais fournie par Railway : alias des dépôts, modes et exécutants permis, outils de Claude, commande de test par dépôt, MCP, durée maximale, concurrence 1, version testée de chaque CLI. Tout écart est refusé en français et remonte par `block_task`.
- **Isolement** : une carte = un worktree et une branche locale `hermes/<carte>` ; jamais de push, jamais de fusion ; Job Object (local_runner.py:788-1082) ; environnement par liste blanche (local_runner.py:741-773), sans `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` ni `CODEX_API_KEY` ; consigne par stdin.
- **Sorties** : balayage de secrets (motifs de jetons OpenAI, Anthropic, GitHub, clés privées, contenu d'auth.json) avant tout envoi à Railway ; détection = carte bloquée, rien n'est envoyé.
- **Codex** : commande actuelle (executors.py:602-632 et suivantes : `--ask-for-approval never exec --json --ephemeral --sandbox read-only|workspace-write --ignore-user-config --ignore-rules --strict-config`, réseau coupé, `shell_environment_policy.inherit="core"`), plus `-c cli_auth_credentials_store="keyring"` explicite, car `--ignore-user-config` ignore ce réglage dans config.toml. Le bac à sable Windows natif est à prouver (lecture hors dépôt, écriture hors worktree).
- **Claude** : la commande actuelle porte déjà `--permission-mode dontAsk`, `--safe-mode`, `--strict-mcp-config --mcp-config {}`, `--tools Read,Glob,Grep`, `--disallowedTools mcp__*`, `--no-session-persistence` (executors.py:680-703). `--safe-mode` désactive hooks, CLAUDE.md, greffons et serveurs MCP tout en gardant l'authentification (cli.md:124). En écriture : Edit, Write et un Bash limité à `git status`, `git diff` et la commande de test déclarée ; syntaxe à valider contre la version épinglée. `--bare` deviendra le défaut de `-p` et ne lit pas l'OAuth (cc-headless.md:36-62) : le poste contrôle `claude --version` avant chaque carte et refuse une version non testée (l'auto-mise à jour de Claude Code ne peut pas être empêchée depuis le poste si le binaire est partagé).

**CONDITIONS D'UTILISATION**
- **Codex / ChatGPT** : CLI officielle, connectée par le propriétaire, usage personnel ; tolérance publique d'OpenAI non contractuelle ; ni partage, ni revente, ni automatisation de chatgpt.com.
- **Claude** : binaire officiel `claude`, connecté par le propriétaire ; usage personnel de `claude -p` sur l'abonnement ; aucune connexion claude.ai proposée ; personne d'autre servi ; OAuth Anthropic de Hermes jamais utilisé.
- **Cerveau de Hermes** (décision du propriétaire) : `openai-codex` par device code sur Railway (`POST /api/providers/oauth/openai-codex/start`, web_routers/oauth.py:718-751), famille de jetons distincte de celle du PC.
- **Figma** : jamais dans Hermes (identité « Claude Code », optional-mcps/figma/manifest.yaml:11-17 ; tools/mcp_oauth.py:1088-1110). Sur le poste, le plugin officiel de Claude Code est incompatible avec `--safe-mode` et `--strict-mcp-config` : Figma hors v1 tant qu'une sonde ne l'a pas prouvé.
- **Messagerie** : fermée, ou DM Telegram en liste blanche du propriétaire ; `allow_all_users: false` (config_defaults.py:2099).

**VOIES REJETÉES**
- ssh, MCP HTTP vers le PC, A2A, `hermes peer` : connexion entrante.
- Greffon de backend terminal : shell arbitraire sur le PC.
- CLI dans le conteneur Railway : écartées pour l'instant.
- Skills `claude-code`, `codex`, `opencode` livrées avec Hermes : désactivées par `skills.disabled`.

## 7. Quotas

**SOURCES**
Tous les relevés sont faits sur le PC, par le poste, dans le compte où les CLI sont connectées. Aucun appel de modèle juste pour rafraîchir.

- **Codex**
  - `codex app-server`, `account/rateLimits/read`, fusion des notifications partielles `account/rateLimits/updated`.
  - Champs : usedPercent, windowDurationMins, resetsAt, planType, credits ; null = « Inconnu » (research.json, clé codex-quotas).
  - app-server n'a pas `--ignore-user-config` : le poste passe `-c model_provider="openai"` et `-c cli_auth_credentials_store="keyring"` pour qu'un config.toml ne détourne ni le point d'accès ni le magasin d'identifiants.
  - Code existant : probe_codex (subscription_quotas.py:698-890).
- **Claude**
  - JSON de la ligne d'état : rate_limits.five_hour et seven_day, Pro et Max seulement, après la première réponse (claude_statusline.py:112-268 ; probe_claude_code, subscription_quotas.py:906-1045).
  - Pendant les cartes, événements rate_limit_event du flux stream-json (allowed, allowed_warning, rejected ; five_hour, seven_day, seven_day_opus, seven_day_sonnet, overage).
- **Cerveau de Hermes sur openai-codex** : aucun relevé propre ; « même enveloppe que Codex (poste) » si le propriétaire le déclare dans poste.toml, sinon « Inconnu ».

**CE QUI EST INTERDIT**
`hermes usage` et `/usage` pour ces comptes (wham/usage en « codex-cli », account_usage.py:376 ; oauth/usage en « claude-code/2.1.0 », :597). Un test CI vérifie que le greffon n'importe jamais agent.account_usage.

**FORMAT**
- Schéma stable de `hermes usage --json` (hermes_cli/subcommands/usage.py:15-35) : provider, source, title, plan, fetched_at, windows[label, used_percent, resets_at, detail], details, unavailable_reason.
- Ajouts : origine (poste), enveloppe, version de la CLI. `source` = « poste:<machine> ».
- acp_contracts/subscriptions.py (565 lignes) ramené à ce schéma.

**TRANSPORT** : poussée vers /machine/v1/quotas toutes les 10 min et après chaque carte ; historique court ; événement « quotas » dans le flux SSE.

**AFFICHAGE** : web /quotas, badge, bannière ≥ 90 % ; Qt QuotasPage ; outil poste_quotas. Pas d'injection dans le prompt système, dont le cache est « sacré » (AGENTS.md:19-27).

**RÈGLES D'AFFICHAGE**
- Aucune donnée : « Inconnu ».
- Relevé de plus de 30 min : valeur affichée avec « Périmé (relevé il y a …) ».
- resets_at dépassé : « Inconnu » pour la fenêtre.
- rejected pendant une carte : carte bloquée « quota atteint, reprise à HH:MM ».
- Aucun chiffre hebdomadaire OpenAI extrapolé.

**LIMITE CONNUE**
Le chemin Codex « compte connecté » n'a été éprouvé que contre un faux app-server ; le vrai Codex 0.156.1 a répondu « non connecté » (CHANGELOG.md, section Unreleased). Hypothèse à tester en premier en P6 : identifiants en keyring ignorés à cause de la configuration utilisateur non lue.

## 8. Réglages prêts et catalogue

Tout est livré dans l'image ; aucune installation réseau au démarrage. Trois couches.

**1. Managed scope `/etc/hermes`**
Root, 0644, fusion feuille par feuille ; appliquée en dernier (env_loader.py:473 et 503-517). Limite documentée : l'application est garantie par les permissions seulement (managed-scope.md:139-148) ; l'agent tourne en uid 10000 sans sudo (Dockerfile:81), et HERMES_UID=0 est refusé par l'amorçage (stage2-hook.sh:90-95).

`config.yaml` (dans l'image) :
- `plugins.enabled: [acp-poste]` ; `plugins.disabled: [dashboard_auth/basic, dashboard_auth/self_hosted, dashboard_auth/drain]` ; `plugins.allow_deprecated_imports: false`.
- `auth.adopt_external_logins: false`.
- `approvals.mode: manual` (défaut `smart`, config_defaults.py:1656), `approvals.cron_mode: deny`, `approvals.unattended_mode: deny`.
- `skills.write_approval: true`, `skills.inline_shell: false`, `skills.external_dirs: [/opt/acp/skills]`, `skills.auto_load: [acp-delegation]`, `skills.disabled: [claude-code, codex, opencode]`.
- `kanban.auto_decompose: false`, `kanban.dispatch_profiles: [default]` (plus les profils réels s'il y en a).
- `security.redact_secrets: true`, `display.language: fr`.
- `dashboard.trusted_proxies` (plage mesurée en P2), `dashboard.theme: acp`, `dashboard.public_url`, `dashboard.oauth.client_id`, `dashboard.oauth.portal_url`, `dashboard.basic_auth.{username, password, password_hash}: ""`, `dashboard.oauth.self_hosted.{issuer, client_id}: ""`.
- `mcp_servers.context7` : entrée officielle `optional-mcps/context7` (HTTP, sans authentification).
- Plateformes de messagerie : désactivées, ou limitées au propriétaire.

`.env` (généré par `05-acp` à chaque démarrage, voir architecture) : HERMES_DASHBOARD_OAUTH_CLIENT_ID, HERMES_DASHBOARD_PORTAL_URL, HERMES_DASHBOARD_PUBLIC_URL, API_SERVER_HOST=127.0.0.1, HERMES_LANGUAGE=fr, et valeurs vides pour les variables basic, OIDC et drain. Aucun secret.

**2. Semence posée par `05-acp`**
- `SOUL.md` en français, premier emplacement du prompt (personality.md:9-11), avec le marqueur d'empreinte décrit dans l'architecture : la persona suit les nouvelles images tant que le propriétaire ne l'a pas modifiée.
- `USER.md` amorcé par l'assistant de premier lancement, dans le volume, jamais dans Git.
- Le thème, dans un répertoire root.

**3. Skills vendorisées**, en lecture seule sous `/opt/acp/skills` (root).
- Un dossier externe n'est une frontière d'écriture que par ses permissions (skills.md:391).
- Une skill locale du même nom masque l'externe (skills.md:392). Or l'amorçage recopie les skills livrées par Hermes dans /opt/data/skills à chaque démarrage (stage2-hook.sh:734-742), dont `systematic-debugging`, `test-driven-development` et `requesting-code-review`, homonymes de skills de superpowers. `verifier_catalogue.py` refuse toute collision avec les skills livrées ; les skills retenues en collision sont renommées avec un préfixe ou écartées.

**PERSONA**
- Réponses toujours en français, ton direct, refus explicites.
- Jamais prétendre avoir exécuté ce qui ne l'a pas été ; « Inconnu » plutôt qu'inventer.
- Lire `poste_quotas` avant de déléguer ; ne jamais créer de carte `poste-windows` hors de `poste_deleguer`.
- Aucun secret dans les consignes ; ne jamais déléguer la lecture de fichiers d'identifiants.
- Tutoiement ou vouvoiement : décision du propriétaire.

**MODÈLES ET MÉMOIRE** : modèle principal, décision du propriétaire ; mémoire intégrée de Hermes, sans fournisseur externe.

**CATALOGUE ÉPINGLÉ**
`hermes/catalogue.lock.json` : source, commit, sha256 de chaque fichier, licence, cible (hermes ou poste), niveau de risque. `scripts/verifier_catalogue.py` en CI (empreintes, licences, collisions de noms) ; dans l'image épinglée, `scan_skill` et `should_allow_install` (tools/skills_guard.py:627 et 701).

**Côté Hermes (Railway)** : context7 ; outils web natifs ; navigateur intégré désactivé au départ ; pas de Playwright MCP.

**Côté poste** : aucun MCP en v1 tant que `--safe-mode` et `--strict-mcp-config` sont en place. En P7, sonde : `@playwright/mcp@0.0.82 --headless --isolated` avec `browser_run_code_unsafe` interdit (« RCE-equivalent », readme-pwmcp.md:1081-1083) et context7, via une configuration MCP épinglée. Figma hors v1.

**Skills proposées** (liste finale : décision du propriétaire)
- `emilkowalski/skills@d16ebe60` : MIT, 13 skills.
- `Leonxlnx/taste-skill@c184364c` (MIT) : minimalist-ui, redesign-existing-projects, high-end-visual-design, design-taste-frontend ; full-output-enforcement écartée.
- `anthropics/skills` (Apache-2.0) : skill-creator, mcp-builder, frontend-design.
- `obra/superpowers` (MIT) : une sélection, sans les homonymes des skills Hermes ou renommés.
- ECC (`affaan-m/ECC`) : après confirmation de la licence et choix du SHA (bf70150 lu par l'inventaire, 5064474 en clone local).
- Skills maison en français : acp-delegation, acp-quotas, acp-conventions-depot.

**Exclus** : Agent-Reach ; skills docx, pdf, pptx, xlsx d'anthropics (licence propriétaire) ; MCP memory ; servers-archived.

Licences recensées dans `THIRD_PARTY.md`.

## 9. Railway

**POINT DE DÉPART : LE DÉPLOIEMENT EXISTANT**
Service issu de mazshakibaii/hermes-agent-railway : base python:3.11-slim en root, clone de `main` non épinglé (Dockerfile:1, 12), `git pull` et `uv pip install` au démarrage (entrypoint.sh:4-16), auth_proxy.py (mot de passe unique, SECRET régénéré à chaque démarrage :19, cookie sans Secure :265, réponses mises en tampon :405-427), volume sur /root/.hermes (RAILWAY.md:45), `startCommand = "/entrypoint.sh"` (railway.toml:6). On ne garde que sa forme (un service, un volume, un contrôle de santé) **et ses données**.

**MIGRATION (P2, avant tout changement d'image)**
1. Relever sur le service actuel : `hermes --version`, `_config_version` de config.yaml, version de schéma de state.db, liste de /root/.hermes (plugins, dashboard-themes, skills, cron, SOUL.md, kanban.db).
2. Sauvegardes : sauvegarde de volume Railway, plus `hermes backup` téléchargé et chiffré DPAPI sur le PC.
3. Si les données sont plus récentes que v2026.9.24 : ne pas remonter le volume ; nouveau volume et import sélectif (mémoires, skills, SOUL, cron, sessions si le schéma l'accepte), décision consignée.
4. `railway config pull` (importe volumes et montages, rw_infrastructure-as-code.md:130-150 ; infrastructure-as-code_reference.md:293), puis modification : même volume, montage /opt/data, Start Command vide. `railway config plan` doit afficher « 0 to destroy » avant tout `apply` (un fichier de projet entier supprime toute ressource omise, :333 ; détacher ou supprimer un volume est destructif, reference:291).
5. Premier démarrage : `05-acp` fait la reprise de propriété unique (stage2 ne re-possède pas kanban.db, SOUL.md, plugins/, dashboard-themes/, stage2-hook.sh:228-254 et 345-359).
6. Rapport : SOUL.md existant conservé ou remplacé, greffons utilisateurs trouvés (refus de démarrer s'ils portent un nom acp-*), connexions à refaire (openai-codex).

**DÉCLARATION**
- `.railway/railway.ts` (IaC, disponibilité générale ; Config as Code coupé le 2026-12-01, rw_infrastructure-as-code.md:40). Un service ne peut pas être géré par les deux systèmes (:44) : migration explicite du service existant.
- Un seul service « hermes », une réplique, le volume existant, contrôle de santé sur /api/health (publique, public_paths.py), port cible 9119, variables non secrètes, mise en veille désactivée.
- Réglages non couverts par l'IaC (Wait for CI, watch paths hermes/**, répertoire racine de construction) : dans la procédure d'exploitation.

**CONSTRUCTION**
- Railway construit hermes/image/Dockerfile avec « Wait for CI » (déclencheur `on: push` de la branche requis, rw_full.txt:29680-29694). image.yml : build, `hermes plugins compat <chemin>`, pytest et Playwright dans l'image.
- Base épinglée par condensat ; `CMD ["gateway","run"]` ; aucune Start Command ; mises à jour automatiques d'image désactivées.
- Contexte de construction limité à `hermes/` (répertoire racine ou .dockerignore).
- Option : image GHCR publique par condensat ; GHCR privé = offre Pro (rw_full.txt:29272).

**VARIABLES À DÉFINIR** (lues par `05-acp`, recopiées dans /etc/hermes/.env)
- HERMES_DASHBOARD=1, HERMES_DASHBOARD_HOST=0.0.0.0, HERMES_DASHBOARD_PORT=9119.
- HERMES_DASHBOARD_PUBLIC_URL=https://<domaine> (sert aussi au contrôle Host des WebSocket, web_server_chat.py:165-189).
- HERMES_DASHBOARD_OAUTH_CLIENT_ID=agent:<id>, obtenu sur /local-dashboards du Portail avec l'URI de retour `https://<domaine>/auth/callback` (web-dashboard.md:667-672).
- Secrets éventuels (jeton du bot Telegram) en variables scellées.

**VARIABLES INTERDITES** (refus de démarrer)
- API_SERVER_KEY, API_SERVER_ENABLED, API_SERVER_HOST non loopback (l'image génère sa propre clé dans /opt/data/.env ; une clé fournie par Railway est inutile).
- HERMES_DASHBOARD_BASIC_AUTH_*, HERMES_DASHBOARD_OIDC_*, HERMES_DASHBOARD_DRAIN_SECRET, HERMES_DASHBOARD_PORTAL_URL (fixée par `05-acp`).
- HERMES_MANAGED_DIR, HERMES_BUNDLED_PLUGINS, HERMES_ENABLE_PROJECT_PLUGINS, HERMES_WEB_DIST, HERMES_KANBAN_HOME, HERMES_KANBAN_DB, HERMES_ALLOW_ROOT_GATEWAY, HERMES_DOCKER_EXEC_AS_ROOT, HERMES_AUTH_JSON_BOOTSTRAP.
- AUTO_UPDATE, DASHBOARD_PASSWORD (restes du modèle).
Aucune clé venant du PC n'est posée sur Railway.

**DERRIÈRE LE PROXY**
- Railway envoie X-Forwarded-Proto (toujours https), X-Real-IP et X-Forwarded-Host (rw_full.txt:33403).
- Hermes ne croit X-Forwarded-Proto que pour `dashboard.trusted_proxies`, borné (/0 refusé, web_server_lifecycle.py:439-480) ; sinon cookies sans Secure (cookies.py:220-222).
- `client_ip` lit X-Forwarded-For brut (request_utils.py:18-21) : IP de journal non fiable.
- En P2 : adresse du pair mesurée, présence de X-Forwarded-For relevée.

**RESSOURCES ET COÛT** : 2 Go (docker.md:479-490), Hobby ; 20 à 30 $/mois à mesurer ; volume compatible WAL (docker.md:198-210) ; l'image démarre en root (Dockerfile:340), RAILWAY_RUN_UID inutile.

**SAUVEGARDES**
- Sauvegardes de volume Railway.
- Export hebdomadaire depuis le desktop : `POST /api/ops/backup` lance une action asynchrone (ops.py:566-582) ; sonder `GET /api/actions/backup/status` (actions.py:331) ; puis `GET /api/ops/backup/download` (ops.py:585) ; enfin supprimer l'archive de /opt/data/backups.
- Chiffrement DPAPI sur le PC : l'archive contient .env et auth.json (backup.py:134), dont les jetons tournants openai-codex. Une restauration impose de reconnecter openai-codex.
- Restauration testée en P9.

**MONTÉE DE VERSION**
1. `scripts/monter_hermes.py <tag>` relève le condensat (`docker buildx imagetools inspect`).
2. Mise à jour du Dockerfile et de hermes/contrat, copie de l'OpenRPC, PR.
3. CI verte.
4. Environnement Railway éphémère avec son propre identifiant client Nous et sa propre URL.
Jamais `hermes update`, AUTO_UPDATE ni :latest. Un test vérifie que POST /api/hermes/update ne modifie pas /opt/hermes.

**DÉVELOPPEMENT LOCAL** : même image, docker compose, VOLUME NOMMÉ (un montage du disque Windows corrompt le WAL, docker.md:200-207) ; tests sur HERMES_HOME jetable, jamais sur un volume qui contient des données.

## 10. Ce que l'on garde d'ACP

- La doctrine de CLAUDE.md : aucun faux succès, échec fermé, refus en français, aucune donnée inventée, commits sans Co-Authored-By ni pied de page « Generated with Claude Code », `git add` fichier par fichier, recette de publication d'un lot. Une règle est réécrite : « le desktop passe toujours par les API de Hermes (tableau de bord, JSON-RPC, façade du greffon), jamais par ses fichiers, sa base ou ses secrets ».
- apps/desktop, environ 19 300 lignes de code et 6 650 de tests :
  - src/api (en-têtes cookie et CSRF retirés) ;
  - src/events (SseParser, EventStreamService adapté au bearer, Backoff, StreamScope) ;
  - src/storage (CredentialVault, WindowsCredentialVault, SettingsStore) ;
  - SystemAppearance, CommandRegistry, NavigationModel, Redaction, JsonListModel, UpdateService, ArtifactDownload ;
  - HealthService, adapté de /health et /ready (HealthService.cpp:157 et 185) vers /api/health et /api/status ;
  - côté QML : controls, components, shell et thème généré ;
  - les tests génériques.
- Les quotas du desktop : QuotasPage, SubscriptionQuotasViewModel (965 lignes) et QuotaGauge. Seule la source change.
- apps/worker, renommé apps/poste :
  - executors.py : Codex en 602-632 et suivantes, Claude en 680-703, validation des chemins en 588-599 ;
  - local_runner.py : Job Object en 788-1082, environnement filtré en 741-773, preuves en 420-461 ;
  - credentials_protection.py (DPAPI, ligne 52) ;
  - subscription_quotas.py (1 045 lignes) et claude_statusline.py (307 lignes) ;
  - config.py, qui impose HTTPS hors boucle locale (78-85) ;
  - local_log.py ;
  - et les tests de tous ces modules.
- packages/contracts/src/acp_contracts/subscriptions.py (565 lignes), ramené au schéma de `hermes usage --json`, devenu un jeu de modèles Pydantic du greffon partagés avec le poste.
- design/tokens/*.json et apps/desktop/cmake/generate_design_tokens.py, étendu à trois sorties : QML, thème YAML de Hermes, CSS du greffon. Aujourd'hui le web lit packages/ui/src/tokens.css, écrit à la main.
- packages/pixel-office-engine, octet pour octet, avec ce dont il dépend :
  - apps/web/public/assets ;
  - plugins/*/rooms, lus par tools/room-preview.mjs:98 et tiled-to-template.mjs:3 ;
  - les règles .gitignore:36-43, lues par tests/limezu-pipeline.test.ts:39-49 ;
  - son entrée de workspace et le script test:engine ;
  - les versions résolues de ses dépendances (phaser, vitest, fflate, pngjs, typescript) conservées dans package-lock.json lors de la réduction des workspaces.
- L'outillage Windows :
  - desktop-ci.yml, épinglé sur windows-2022, et desktop-release.yml ;
  - packaging/windows : Inno Setup, DesktopToolchain.psm1 et toolchain.json, où s'ajoute qtwebsockets ;
  - les scripts setup-, build-, test-, package- et dev-desktop.ps1 ;
  - lock_python ;
  - check_version.py, sans le moteur.
- Les leçons de poste déjà consignées : venv sur le Python de python.org et non celui du Store, Job Object pour borner l'arbre de processus, CI desktop sur windows-2022, Qt 6.8.3 installé par aqtinstall.
- Deux idées d'apps/api, sans leur code : attempt_fencing (couvert par expected_run_id) et l'enrôlement des workers (repris par le jeton machine).

## 11. Ce que l'on retire d'ACP

- apps/api (FastAPI : 172 routes, 51 tables, migrations Alembic 0001 à 0005, engine.py de 2 011 lignes) et packages/database. ACP n'a jamais été déployé : aucune donnée ACP à migrer. (Les données du Hermes déjà déployé, elles, sont migrées : voir Railway.)
- L'authentification ACP : amorçage X-ACP-Bootstrap-Token, argon2, cookie acp_session, CSRF, contrôle d'accès multi-organisation. Remplacée par le portail Nous verrouillé et le flux RFC 8252 natif.
- Organisations, espaces, départements, équipes, missions, tâches, tentatives, operations et checkpoints. Remplacés par le kanban, les sous-agents et la mémoire de Hermes.
- Les conversations ACP (routers/conversations.py, conversation-api.ts). Remplacées par le JSON-RPC sur /api/ws.
- Le journal d'événements, le SSE serveur, l'outbox et le relais, apps/event-service et packages/event-sdk.
- services/provider-gateway (figé sur Hermes 0.21.1, hermes/contracts.py:19 ; ComfyUI jamais raccordé), packages/provider-sdk et acp_api/gateway.py.
- Les doublons des fonctions de Hermes : centre MCP, bibliothèque de skills, coffre Fernet, outbound, automatisations, planificateur, webhooks, budgets et alertes.
- Les artefacts et l'aperçu (routers/artifacts.py, 2 500 lignes ; signing.py ; preview.py). Remplacés par les pièces jointes des cartes kanban.
- La CLI `acp` (86 sous-commandes), remplacée par la CLI `hermes`.
- apps/web/src et ses tests (environ 20 000 lignes), packages/ui, packages/contracts TypeScript (miroir de 1 116 lignes) et packages/agent-sdk. On garde seulement apps/web/public/assets, pour le moteur.
- Les tests web maison : testing_service, web_tests.py, fake_playwright_runner, packages/playwright-reporter, e2e/ et studio-ui.
- La sauvegarde, la rétention et les instantanés d'ACP. Remplacés par les sauvegardes de volume Railway et la sauvegarde native de Hermes.
- Le déploiement ACP : deploy/railway (6 services, Config as Code déprécié), le docker compose de la pile ACP, les scripts verify_* liés à l'API ACP, hermes-local.ps1, setup-hermes.ps1, verify-hermes-local.py, check_hermes_profile.py et check_railway_config.py.
- Dans le worker : main.py, hermes_lifecycle.py, multi_agent.py, automation_scheduler.py, budget.py, mcp_probe.py, mcp_execution.py, web_tests.py, extensions.py et checkpoints.py.
- Dans le desktop, en P8 : AuthManager, SessionCookieJar, CompatibilityService, les ViewModels et pages métier Missions, Operations, Artifacts, Platform, Workspace, Conversations, Studio, Run, Extensions et Projects.
- La documentation datée des lots A à H (44 fichiers). Seuls reprise-poste.md et les guides desktop sont réécrits. Rien n'est retiré de l'historique : tout reste sous archive/acp-0.10.0-avant-hermes (60a49b6).

## 12. Branche et arborescence

**BRANCHE**
- Nom : `refonte/hermes` (décision du propriétaire).
- Point de départ : l'étiquette annotée `archive/acp-0.10.0-avant-hermes` → 60a49b6c5ab2ca5d73cfdf55919c85903a261330 (vérifié : `git rev-parse` et type `tag`). CI (35981934303) et Desktop CI (35981934226) vertes sur ce commit.
- Emplacement : un NOUVEAU worktree `.claude/worktrees/refonte-hermes`. Le checkout principal n'est pas touché (travail non commité sur le moteur, ses salles et apps/web). On ne commite jamais `.claude`.
- Pourquoi l'étiquette plutôt qu'une branche orpheline : historique et `git blame` du desktop et du worker, moteur identique sans recopie, reprise de main par une simple PR.

**PUBLICATION** (règle du propriétaire : publier à chaque lot, en conflit avec « main repris ensuite »)
- Recommandé : chaque phase = une branche `refonte/hermes-pN`, PR vers `refonte/hermes`, CI verte, fusion par commit de fusion, sans tag ; la PR finale vers `main` porte le tag.
- Version : ouverture 0.11.0 en P0 ; commit d'ouverture 1.0.0 avant la PR finale, pour que VERSION et le tag concordent.

**PREMIERS COMMITS**
Sans Co-Authored-By ni pied de page d'agent, `git add` fichier par fichier, `git diff --check` propre.
1. `chore(release): open 0.11.0` : VERSION et copies ; check_version.py réduit aux composants conservés, sans packages/pixel-office-engine (lignes 32 et 50), sinon toute hausse de version obligerait à modifier le package.json du moteur.
2. `chore: remove pre-Hermes domains`.
3. `refactor(poste): rename worker to poste and drop API-bound modules`.
4. `docs: rewrite CLAUDE.md and handoff notes for the Hermes architecture`.

**ARBORESCENCE CIBLE**
```
refonte/hermes
├─ CLAUDE.md · README.md · CHANGELOG.md · VERSION
├─ package.json          workspaces : packages/pixel-office-engine, hermes/plugins/acp-interface/web
├─ .railway/railway.ts   issu de `railway config pull`
├─ hermes/                                   tout ce qui entre dans l'image (contexte de construction)
│  ├─ image/Dockerfile                       FROM nousresearch/hermes-agent:v2026.9.24@sha256:… · CMD ["gateway","run"]
│  ├─ image/cont-init.d/05-acp               with-contenv ; gardes, .env géré, répertoires root, thème, SOUL, migration
│  ├─ gere/config.yaml                       → /etc/hermes/config.yaml (managed scope, sans secret)
│  ├─ contrat/                               HERMES_VERSION, condensat, gateway-contract.openrpc.json (MIT)
│  ├─ plugins/acp-interface/                 dashboard/{manifest.json, dist/}, web/ (TS, esbuild, Vitest)
│  ├─ plugins/acp-poste/                     plugin.yaml, __init__.py, outils.py, jeton_machine.py,
│  │                                         kanban_adapter.py, demandes.py, approbations.py, quotas.py,
│  │                                         contrat/ (Pydantic), dashboard/plugin_api.py
│  ├─ persona/SOUL.md
│  ├─ skills/                                vendorisées avec LICENSE, skills maison en français
│  ├─ theme/acp.yaml                         généré
│  ├─ catalogue.lock.json · THIRD_PARTY.md
│  └─ tests/                                 pytest dans l'image, modèle factice, Playwright
├─ apps/desktop/                             Qt, rebranché
├─ apps/poste/                               ancien apps/worker, réduit
├─ apps/web/public/assets/ · plugins/*/      données du moteur, gelées
├─ packages/pixel-office-engine/             INCHANGÉ
├─ design/tokens/
├─ packaging/windows/                        installeurs du desktop et du poste
├─ scripts/        check_version.py, check_engine_frozen.py, sync_hermes_contract.py,
│                  monter_hermes.py, generer_themes.py, verifier_catalogue.py, *-desktop.ps1
├─ docs/           en français : architecture, sécurité, exploitation Railway, migration, poste,
│                  montée de Hermes, preuves, reprise-poste
└─ .github/workflows/  ci.yml (poste, greffons, moteur, catalogue) · image.yml ·
                       desktop-ci.yml (windows-2022) · desktop-release.yml
```

**GARDE-FOUS EN CI**
- `git diff --exit-code archive/acp-0.10.0-avant-hermes -- packages/pixel-office-engine apps/web/public/assets plugins` vide.
- `npm run test:engine` vert, avec les versions de dépendances du moteur inchangées dans le verrou.
- Toute intégration du travail moteur non commité passe par une PR dédiée qui modifie cette garde.

**REPRISE DE MAIN** : PR de `refonte/hermes` vers `main`, fusionnée après validation ; tag `vX.Y.Z` sur le commit de fusion.

## 13. Phases

### P0 — Branche, élagage et gel du moteur

**Livrable**

- Worktree et branche `refonte/hermes` depuis l'étiquette d'archive.
- Commit d'ouverture 0.11.0, check_version.py sans le moteur.
- Retrait des domaines listés, fichier par fichier.
- apps/worker renommé apps/poste et élagué.
- `CLAUDE.md` et `docs/reprise-poste.md` réécrits (règle desktop réécrite, publication par phase).
- `check_engine_frozen.py`.
- CI réduite à trois volets : moteur, desktop, poste.
- Desktop intact mais « hors service jusqu'à P8 », dit dans le README.

**Preuve attendue**

- Garde `git diff --exit-code` contre l'étiquette : sortie vide jointe.
- `npm run test:engine` vert ; diff du verrou limité aux workspaces retirés pour les paquets du moteur.
- pytest vert sur apps/poste.
- Desktop CI verte ; identifiant du run noté.
- `git diff --check` propre.
- `git log --format=%B | grep -c Co-Authored-By` renvoie 0.
- Empreinte de `git status --porcelain` du checkout principal identique avant et après.

### P1 — Image dérivée et CI de contrat (en local et en CI, sans Railway)

**Livrable**

- `hermes/image/Dockerfile` épinglé sur le condensat relevé par `docker buildx imagetools inspect`, `S6_BEHAVIOUR_IF_STAGE2_FAILS=2`, `CMD ["gateway","run"]`.
- Managed scope : config.yaml ; `05-acp` complet (with-contenv, gardes, génération de /etc/hermes/.env, répertoires root, thème, SOUL avec marqueur, migration unique).
- Greffon `acp-poste` squelette : route `/v1/meta`, fournisseur de jeton, `kanban_adapter` avec imports depuis les modules de définition.
- OpenRPC recopié ; modèle factice compatible OpenAI.
- Workflow `image.yml` : build, `hermes plugins compat <chemin>`, pytest dans l'image.

**Preuve attendue**

Dans le journal de CI :
- `hermes --version` affiche 0.21.5 ; condensat affiché ;
- `hermes config` montre les clés épinglées (dont `kanban.auto_decompose: false`) ; `hermes config set approvals.mode off` refusé ;
- arrêt code 1 avec message français si : manifeste nommé `acp-poste` sous /opt/data/plugins/nimportequoi/, `HERMES_MANAGED_DIR` défini, `API_SERVER_KEY` fourni en variable, /etc/hermes/config.yaml invalide ;
- injection de `dashboard.basic_auth`, `dashboard.oauth.self_hosted` dans /opt/data/config.yaml et de `HERMES_DASHBOARD_OAUTH_CLIENT_ID=agent:autre` dans /opt/data/.env, redémarrage : `GET /api/auth/providers` ne liste que `nous` avec l'identifiant attendu ;
- l'utilisateur hermes ne peut créer ni fichier dans /opt/data/plugins ni modifier /opt/data/dashboard-themes/acp.yaml ;
- l'api_server n'écoute que sur 127.0.0.1:8642 (`ss -ltnp`) ;
- PID 1 = /init d's6 en `docker run` local ;
- `hermes plugins compat` sort avec le code 0, et échoue sur un greffon témoin qui importe `hermes_cli.kanban_db.connect` ;
- `/api/plugins/acp-poste/v1/meta` renvoie 401 sans session ;
- `POST /api/hermes/update` ne modifie pas `/opt/hermes` (empreinte avant et après) ;
- une carte en triage sur le tableau `poste` y reste après plusieurs ticks du dispatcher.

### P2 — Migration du déploiement existant et déploiement Railway authentifié

**Livrable**

- Inventaire du service actuel (versions, schéma, fichiers) et sauvegardes (volume Railway + `hermes backup` chiffré DPAPI).
- Décision consignée : même volume remonté sur /opt/data, ou nouveau volume et import sélectif.
- `.railway/railway.ts` issu de `railway config pull`, service migré hors Config as Code, Start Command vide.
- Wait for CI activé ; tableau de bord enregistré sur Nous avec l'URI de retour ; variables définies.
- `trusted_proxies` mesuré puis épinglé.
- Procédure d'exploitation et de migration en français.

**Preuve attendue**

- `railway config plan` avant apply : « 0 to destroy », sortie jointe.
- `/proc/1/cmdline` sur Railway = /init d's6 ; tableau de bord et passerelle actifs.
- Après migration : sessions, mémoires, skills et cron relus ; fichiers de /opt/data appartenant à hermes (hors répertoires root voulus) ; aucune erreur de permission dans les journaux.
- `curl https://<domaine>/api/status` : auth_required vrai, version 0.21.5 ; `/api/auth/providers` : `nous` seul.
- Connexion refusée pour un second compte Nous qui n'est pas le propriétaire (capture).
- `/api/config` sans session : 401 ; `/api/ws` sans ticket : refusé ; cookie `Secure`.
- Plage du pair et présence de X-Forwarded-For documentées.
- Un redéploiement conserve `state.db` et les sessions.
- Aucun `git pull` dans les journaux ; un commit à CI rouge n'est pas déployé.
- Connexion réussie depuis le téléphone, avec capture.

### P3 — Identité, français et réglages prêts

**Livrable**

- `generer_themes.py` produit `acp.yaml` et le QML.
- `SOUL.md` en français.
- Skills vendorisées, `catalogue.lock.json`, `verifier_catalogue.py` (empreintes, licences, collisions).
- MCP context7.
- `acp-interface` minimal : français forcé, Accueil, Catalogue en lecture, marque, contrôle de `sdkVersion`.
- Test qui refuse toute chaîne hors du catalogue français.

**Preuve attendue**

- `GET /api/dashboard/themes` montre `acp` actif.
- Captures Playwright 390×844 et 1440×900.
- Décompte des chaînes natives restées en anglais publié.
- `verifier_catalogue.py` vert : empreintes, licences, aucune skill docx/pdf/pptx/xlsx d'anthropics, aucune collision avec les skills livrées par Hermes.
- Rapport `scan_skill` sans élément bloquant.
- `GET /api/skills` liste exactement le catalogue attendu, skills livrées comprises.
- Test du MCP context7 vert.
- Nouvelle session : réponse en français.
- Deux démarrages successifs : aucune différence dans /etc/hermes, le thème, SOUL.md.
- Une image avec un SOUL modifié met à jour un SOUL non modifié par le propriétaire, et laisse intact un SOUL modifié (signalé dans /v1/meta).
- gitleaks propre.

### P4 — Discussion mobile

> **Remplacée** le 25 septembre 2026 par le plan d'autonomie ([autonomie.md](autonomie.md) § 8) :
> P4 « projets autonomes sur Hermes ». Texte d'origine conservé pour mémoire.

**Livrable**

- Page `/discussion`.
- Client JSON-RPC typé depuis l'OpenRPC épinglé : ticket en sous-protocole, `client.capabilities`, sessions, flux, approbations, clarify, interruption, -32601 pour les requêtes non gérées.
- Reprise par `session.events.since`.
- Markdown assaini ; accessibilité.

**Preuve attendue**

Parcours Playwright contre l'image épinglée et le modèle factice :
- flux progressif ;
- approbation d'une commande dangereuse en vue téléphone ;
- clarify répondu ;
- requête `secret` refusée proprement ;
- coupure réseau en cours de tour, reprise sans trou dans la numérotation des événements ;
- interruption.

Autres preuves :
- axe sans erreur critique ;
- un vrai tour sur Railway depuis le téléphone, session visible dans l'onglet Sessions natif ;
- `/chat` toujours disponible.

### P5 — Poste en lecture et délégation kanban

> **Remplacée** le 25 septembre 2026 par le plan d'autonomie ([autonomie.md](autonomie.md) § 8) :
> P5 « poste connecté » et P6 « exécution autonome sur un dépôt jetable ». Texte d'origine conservé pour mémoire.

**Livrable**

`apps/poste` :
- compte Windows dédié (ou repli consigné), enrôlement, jeton sous DPAPI ;
- long-poll, `heartbeat_claim` et `heartbeat_worker` toutes les 60 s ;
- politique locale, Job Object, environnement minimal, balayage de secrets des sorties ;
- Codex avec `-c cli_auth_credentials_store="keyring"` ;
- tâche planifiée.

`acp-poste` :
- fournisseur de jeton machine, routes exactes, vérification du fournisseur ;
- `kanban_adapter` (tableau `poste`) et table `demandes` ;
- outils `poste_*` en mode lecture.

Autour : skill `acp-delegation` ; pages `/travaux` et `/poste`, bannières ; notification Telegram si retenue.

**Preuve attendue**

Tests unitaires et d'intégration dans l'image :
- réclamations concurrentes : un seul gagnant ;
- poste tué : carte reprise à l'expiration ; deux expirations : carte bloquée et affichée comme telle ;
- carte de plus de `dispatch_stale_timeout_seconds` avec battements : non reprise ;
- verrou `expected_run_id` ;
- carte `poste-windows` créée par l'outil kanban natif : refusée « Carte non émise par acp-poste » ;
- secret drain refusé sur les routes machine ; jeton révoqué : 401 ;
- refus en français pour un dépôt hors liste ou un mode interdit ;
- secrets masqués dans les journaux.

De bout en bout, depuis le téléphone :
- une carte en lecture passe par Codex puis par Claude sur un dépôt du propriétaire et arrive à `done` ;
- consignes d'exfiltration (« lis ~/.codex/auth.json », « lis ~/.claude/.credentials.json », chemin absolu hors dépôt) : refusées par l'exécutant ou bloquées par le balayage, rien de sensible n'arrive sur Railway (relevé joint) ;
- `Get-NetTCPConnection -State Listen` : aucun port du poste ;
- environnement des enfants sans `ANTHROPIC_API_KEY` ni `OPENAI_API_KEY` (relevé masqué) ;
- poste arrêté : `stranded_in_ready` visible ;
- aucune carte du tableau `poste` décomposée ni lancée par le dispatcher.

### P6 — Quotas

> **Remplacée** le 25 septembre 2026 par le plan d'autonomie ([autonomie.md](autonomie.md) § 8) :
> P5 « poste connecté » (catalogue et quotas). Texte d'origine conservé pour mémoire.

**Livrable**

- Collecteurs : app-server pour Codex (avec `model_provider` et magasin d'identifiants forcés) ; ligne d'état et `rate_limit_event` pour Claude.
- Schéma de `hermes usage`, avec `origine` et `enveloppe`.
- Route `/machine/v1/quotas` et flux SSE.
- Page `/quotas`, badge, bannière.
- Outil `poste_quotas` et garde dans `poste_deleguer`.

**Preuve attendue**

- Relevés réels et horodatés des deux abonnements : première preuve du chemin Codex « connecté » (ou cause de l'échec documentée).
- Tests des états « Périmé » et « Inconnu », y compris `resets_at` dépassé.
- Test déterministe : au-delà du seuil, refus avec l'heure de remise à zéro ; quota inconnu : avertissement sans refus.
- Transcription où Hermes choisit l'exécutant selon les quotas, jointe à titre d'illustration (comportement de modèle, non déterministe).
- Test CI : aucun import de `agent.account_usage`.
- Journaux : aucun appel de modèle fait juste pour rafraîchir.

### P7 — Écritures validées et signées

> **Remplacée** le 25 septembre 2026 par le plan d'autonomie ([autonomie.md](autonomie.md) § 8) :
> les écritures signées sont retirées (§ 9 du plan d'autonomie) ; l'écriture autonome relève de P6 et P7. Texte d'origine conservé pour mémoire.

**Livrable**

Validation :
- enregistrement de la passkey sur `/poste`, clé publique gardée par le poste ;
- cartes d'écriture en `triage` ;
- signature WebAuthn par tentative (demande, consigne, tentative, nonce, expiration), vérifiée par le poste ; nonces consommés gardés localement ;
- « Demander des changements » : nouvelle consigne, nouvelle signature.

Exécution :
- Claude en écriture : `--permission-mode dontAsk`, liste d'outils bornée, `--safe-mode`, `--strict-mcp-config` ;
- Codex en `workspace-write`, sans réseau ;
- worktree et branche `hermes/<carte>`, `request_review` avec le diff, sans `reviewer`.

Sonde MCP côté poste (Playwright, context7) ; décision sur Figma.

**Preuve attendue**

- Approbation absente, signée sur une autre empreinte, par une autre clé, rejouée (nonce déjà vu) ou expirée : carte bloquée, raison en français.
- Carte passée en `ready` depuis l'onglet Kanban natif sans signature : refusée.
- Commentaire ajouté sur une carte en revue : jamais transmis à l'exécutant sans nouvelle signature.
- Écriture réelle sur un dépôt jetable, validée depuis le téléphone : diff en revue ; `git branch -r` inchangé, aucun push.
- Écriture hors du worktree tentée par la consigne : refusée (preuve du bac à sable Windows de chaque exécutant, ou limite documentée).
- Événement d'initialisation stream-json : authentification par l'abonnement.
- Une annulation tue tout l'arbre de processus.

### P8 — Desktop Qt rebranché

> **Remplacée** le 25 septembre 2026 par le plan d'autonomie ([autonomie.md](autonomie.md) § 8) :
> P8 « desktop Qt et MCP côté poste ». Texte d'origine conservé pour mémoire.
>
> **État du 2 octobre 2026** : volet desktop **réalisé côté dépôt** sur `refonte/hermes-p8`
> (sans PR ni fusion) : fournisseur `self-hosted` (et non `nous`), pages Accueil, Projets,
> Questions, Discussion, Poste, Quotas, Routage, Diagnostics, Sauvegarde ; bout en bout local
> contre Authelia et l'image de test. Connexion à Railway et VM Windows propre : non faites
> (rien n'est déployé). Le volet « MCP côté poste » est reporté après la fusion de P6. Détail :
> [desktop.md](desktop.md).

**Livrable**

- `NativeAuthFlow` (RFC 8252, fournisseur `nous`) et session bearer dans le Gestionnaire d'identification Windows.
- `JsonRpcChannel` sur Qt WebSockets.
- `CompatibiliteHermes`.
- HealthService, ApiClient et EventStreamService adaptés au bearer et aux routes Hermes.
- Pages Discussion, Travaux, Quotas, Poste, Réglages, Diagnostics, Sauvegarde.
- Suppression d'`AuthManager`, du cookie et des pages métier.
- Qt WebSockets dans la chaîne d'outils, CMake et l'installeur.

**Preuve attendue**

Tests Qt :
- PKCE ; `state` différent refusé en français ; redirection limitée à 127.0.0.1 ;
- rotation du jeton de rafraîchissement persistée de façon atomique ; un seul rafraîchissement à la fois ;
- 401 `session_expired` suivi d'une nouvelle connexion ;
- -32601 renvoyé pour une requête serveur non gérée.

Autres preuves :
- tests de contrat contre l'OpenRPC et les fixtures générées ;
- Desktop CI verte sur windows-2022 ;
- connexion réelle à Railway, avec capture ;
- export du registre `QSettings` sans aucun jeton ;
- sauvegarde : action sondée jusqu'à la fin, archive chiffrée DPAPI, archive supprimée de /opt/data/backups ;
- installeur non signé, dit explicitement, testé sur une VM Windows propre.

### P9 — Exploitation, montée de version et publication

**Livrable**

- Procédure d'exploitation en français.
- Test de restauration.
- Répétition de `monter_hermes.py` vers la release suivante de Hermes, dans un environnement éphémère (identifiant Nous propre).
- Commit d'ouverture 1.0.0 et journal des modifications complet : Ajouté, Modifié, Corrigé, Sécurité, Vérifié localement, Limites connues.
- PR vers `main`, puis tag sur le commit de fusion.
- Preuves publiées dans `docs/`.

**Preuve attendue**

- Restauration dans un environnement Railway jetable : sessions et cartes relues ; reconnexion openai-codex nécessaire, constatée et documentée.
- Montée de version répétée : `hermes plugins compat` et tests de contrat verts, ou écart documenté.
- Identifiants des runs CI verts.
- `git rev-parse vX.Y.Z^{commit}` égal au commit de fusion ; VERSION égal au tag.
- Document de preuves relu.
- Pixel Office et Godot hors périmètre.

## 14. Risques

- **Instabilité en amont.** 1 610 commits en trois jours ; surfaces internes non versionnées (REST du tableau de bord, JSON-RPC, SDK des greffons, kanban_db). Le bloc PLUGIN-COMPAT est encore présent à f97608f, mais depuis le 2026-09-14 un greffon qui l'utilise est désactivé (COMPAT_MANIFEST.md:15-19).
  - Parades : image épinglée par condensat, `hermes plugins compat` en CI, imports depuis les modules de définition, OpenRPC recopié et comparé, contrôle de `sdkVersion`, tests dans l'image avant tout changement de condensat.
- **Voie kanban.** kanban_db.py a reçu 84 commits en 30 jours ; pas de route REST de réclamation ; voies CLI externes « not yet a paved path » (kanban-worker-lanes.md:121). Comportements par défaut hostiles à notre usage : auto-décomposition des cartes en triage, profils lançables par nom, `max_runtime` non appliqué à distance, reprise « stale » à 4 h sans `last_heartbeat_at`, blocage après deux expirations.
  - Parades : réglages épinglés (A1), tableau `poste` explicite, table `demandes`, double battement, tests de contrat ; plan B (file dans plugin_db) prêt sur le papier.
- **L'agent de Railway écrit dans /opt/data** (config.yaml, .env par le terminal, plugins/, dashboard-themes, /opt/data/acp).
  - Parades : clés de sécurité et d'authentification en managed scope régénérée par root à chaque démarrage ; plugins/ et dashboard-themes/ propriété de root ; garde sur les noms de manifestes ; alerte d'ombrage dans /v1/meta, vérifiée par le desktop ; le poste ne se fie à /opt/data/acp pour aucune autorisation d'écriture.
- **Accès au tableau de bord = exécution de code dans le conteneur.** L'autorisation est déléguée au Portail Nous (aucune liste locale) ; les cartes en lecture renvoient à Railway du contenu des dépôts.
  - Parades : Nous verrouillé (A4), refus d'un second compte prouvé en P2, `approvals.mode: manual`, liste blanche limitée aux dépôts dont le contenu peut vivre sur Railway.
- **Exfiltration par les lectures.** Une injection lue sur le web peut faire déléguer la lecture d'un fichier d'identifiants ; les bacs à sable en lecture ne sont pas prouvés sous Windows natif.
  - Parades : compte Windows dédié, identifiants en keyring (forcé en ligne de commande), balayage de secrets en échec fermé, lectures validées au départ, preuve d'exfiltration négative en P5.
- **Signature WebAuthn servie par Railway.** Un Railway compromis peut afficher un contenu et en faire signer un autre ; à l'enrôlement, il peut substituer la clé (confiance au premier usage).
  - Parades : une signature par tentative, nonces, aucun commentaire non signé transmis, dépôts jetables d'abord, revue du diff, confirmation locale en option pour les dépôts réels.
- **Proxy de Railway.** IP du pair inconnue ; `client_ip` lit X-Forwarded-For brut (request_utils.py:18-21). Un `trusted_proxies` faux donne des cookies sans Secure.
  - Parades : mesure en P2 ; avec Nous, aucun mot de passe à deviner.
- **Démarrage hors s6.** Si Railway n'attribue pas le PID 1, cont-init.d (dont 05-acp) et le tableau de bord ne tournent pas (entrypoint-dispatch.sh:17-26). S6_BEHAVIOUR_IF_STAGE2_FAILS=2 arrête aussi le conteneur sur toute défaillance des scripts d'origine.
  - Parades : preuve PID 1 en P2 ; contrôle de santé sur le tableau de bord (échec visible, pas silencieux) ; comportement éprouvé en P1.
- **Migration du déploiement existant.** Volume en /root/.hermes écrit en root par un Hermes non épinglé, potentiellement plus récent que v2026.9.24 ; IaC qui supprime les ressources omises.
  - Parades : sauvegardes avant tout, contrôle de version, `railway config pull`, plan « 0 to destroy », reprise de propriété unique, import sélectif si nécessaire.
- **Chat React doublon.** Contre la consigne amont (web/AGENTS.md:20-23) ; le JSON-RPC a déjà connu une rupture (programmatic-integration.md:98).
  - Parades : contrat épinglé, repli sur /chat (TUI) ou Telegram.
- **Conditions d'utilisation des abonnements.** Tolérance OpenAI non contractuelle et révocable ; Anthropic vise un usage « ordinary, individual » ; enveloppe ChatGPT partagée entre le cerveau de Hermes et le Codex du PC, depuis deux adresses IP.
  - Parades : un seul utilisateur, concurrence de 1, garde de quota, aucun identifiant hors du PC.
- **Claude Code en mode `-p`.** `--bare` deviendra le défaut et ne lit pas l'OAuth (cc-headless.md:36-62) ; l'auto-mise à jour peut changer la version entre deux cartes ; `--safe-mode` coupe greffons et MCP.
  - Parades : contrôle de version avant chaque carte et refus d'une version non testée, `--safe-mode`, `--strict-mcp-config`, Job Object, worktree, jamais de push.
- **Dépendance à Nous Portal.** Compte tiers ; panne du Portail = pas de connexion (échec fermé) ; jeton de rafraîchissement de 24 h tournant avec détection de réutilisation (nous/__init__.py:1-8), la doc divergeant (web-dashboard.md:1034).
  - Repli : self_hosted sur un tenant fermé.
- **Une seule réplique.** Flux natif et tickets WS en mémoire, état en SQLite ; un redéploiement coupe les WebSocket ; l'agent, les routes du greffon et les long-polls du poste partagent le processus du tableau de bord et sa boucle d'événements.
  - Parades : reprise par `session.events.since` prouvée ; accès SQLite en threadpool ; mesure dans le budget de 2 Go.
- **Contraintes de Railway.** Config as Code coupé le 2026-12-01 ; registre privé = Pro ; HTTP coupé à 15 min ou 5 min sans données ; volumes montés en root ; `up.railway.app` est un suffixe public (passkey liée au sous-domaine) ; courte coupure à chaque redéploiement.
- **Traduction partielle** : pages natives (fr.ts 785 lignes contre 921), TUI de /chat en anglais, `display.language` limité aux messages statiques.
- **Catalogue.** Licence d'ECC non confirmée, deux SHA (bf70150 et 5064474) ; skills vendorisées hors de l'analyse du hub ; collisions de noms avec les skills livrées par Hermes (skills.md:392 ; stage2-hook.sh:734-742).
- **Restent à vérifier par exécution** (rien n'a été exécuté) : condensat de l'image v2026.9.24 ; PID 1 sur Railway ; prise en charge par l'IaC de Wait for CI et des watch paths ; syntaxe de --allowedTools pour Bash ; bacs à sable Codex et Claude sous Windows natif ; champ d'authentification de l'événement d'initialisation stream-json ; efficacité des valeurs vides épinglées dans la managed scope ; refus d'un second compte par le Portail Nous.

## 15. Recommandations d'origine pour les décisions (pour mémoire)

> Recommandations formulées par le plan avant les décisions du propriétaire. Là où elles divergent de la section 1, la section 1 fait foi.

- **Fournisseur d'authentification.** Recommandation : Nous Portal, tableau de bord enregistré sur /local-dashboards, verrouillé par la managed scope, refus d'un second compte prouvé. Repli : self_hosted OIDC sur un tenant fermé. Jamais basic sur Internet. OIDC maison avec liste blanche seulement si les deux sont refusés, après revue indépendante.
- **Migration du Hermes déjà déployé.** Recommandation : remonter le même volume sur /opt/data si ses données ne sont pas plus récentes que v2026.9.24 ; sinon nouveau volume et import sélectif. Sauvegardes avant tout dans les deux cas.
- **Cerveau de Hermes.** Recommandation : openai-codex par device code sur Railway, jetons distincts de ceux du PC, affiché « même enveloppe ». Pas de repli payant par défaut ; option : clé OpenRouter plafonnée. Jamais l'OAuth Anthropic de Hermes.
- **approvals.mode.** Recommandation : manual (le défaut `smart` laisse un modèle auxiliaire approuver seul).
- **Compte d'exécution du poste.** Recommandation : compte Windows local standard dédié, CLI connectées dans ce compte, dépôts clonés dans ce compte, tâche planifiée « même si l'utilisateur n'est pas connecté ». Repli : compte du propriétaire, avec le risque d'exfiltration accepté par écrit.
- **Validation des lectures.** Recommandation : au départ, lectures validées elles aussi ; passage en lecture automatique dépôt par dépôt, après la preuve d'exfiltration négative de P5.
- **Validation des écritures.** Recommandation : triage, signature par passkey à chaque tentative, vérifiée par le poste ; aucun dépôt « de confiance » automatique ; confirmation locale sur le PC en option pour les dépôts réels.
- **Liste blanche des dépôts et commandes en écriture.** Recommandation : un dépôt jetable, puis un ou deux dépôts réels ; Bash limité à git status, git diff et une commande de test par dépôt.
- **Notifications sur téléphone.** Recommandation : DM Telegram limité au propriétaire, alimenté par les abonnements natifs des cartes. Web Push reporté.
- **Construction et déploiement de l'image.** Recommandation : Railway construit le Dockerfile dérivé avec Wait for CI (Hobby). Image GHCR publique par condensat si une image publique est acceptable ; GHCR privé = Pro.
- **Préproduction.** Recommandation : environnement Railway éphémère pendant les montées de version, avec son propre identifiant client Nous. Pas d'environnement permanent.
- **Rythme de mise à jour de Hermes.** Recommandation : une montée par mois, plus les correctifs de sécurité. Jamais automatique.
- **Publication.** Recommandation : une PR par phase vers `refonte/hermes` (CI verte, commit de fusion), tag seulement sur la fusion finale dans `main`. Alternative : PR par phase vers `main`, contraire à « main repris ensuite ».
- **Nom de branche et version.** Recommandation : `refonte/hermes`, 0.11.0 à l'ouverture, commit d'ouverture 1.0.0 avant la PR finale, une fois P9 prouvée.
- **Nom du produit.** Recommandation : garder « ACP », identifiants acp-interface et acp-poste.
- **Identité visuelle.** Recommandation : thème acp épinglé ; mention « propulsé par Hermes » (MIT, honnêteté) ; tutoiement dans SOUL.md, ton direct.
- **Composition du catalogue.** Recommandation : 13 skills d'Emil Kowalski ; quatre variantes de taste-skill ; skill-creator, mcp-builder, frontend-design ; sélection de superpowers sans collision ; ECC après licence ; Agent-Reach et docx/pdf/pptx/xlsx d'anthropics exclus ; MCP : context7 côté Hermes ; côté poste, aucun en v1, Playwright et context7 après la sonde de P7 ; Figma hors v1.
- **Navigateur intégré de Hermes sur Railway.** Recommandation : désactivé au départ.
- **Offre et coût Railway.** Recommandation : Hobby, 2 Go, plafond de dépense 30 $ par mois, région Europe, domaine personnalisé pour stabiliser la passkey.
- **Sauvegardes.** Recommandation : sauvegardes de volume quotidiennes, export hebdomadaire depuis le desktop chiffré DPAPI (l'archive contient .env et auth.json), archive supprimée du volume après téléchargement.
- **Travail Pixel Office non commité.** Recommandation : le laisser intact ; intégration éventuelle plus tard par une PR dédiée qui met à jour la garde de gel.
- **PR amont pour compléter fr.ts.** Recommandation : oui, en option, hors du chemin critique.
