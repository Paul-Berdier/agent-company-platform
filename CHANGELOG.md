# Journal des modifications

Les changements notables d'Agent Company Platform sont consignés dans ce fichier.
Le projet suit le versionnage sémantique ; tant que la version majeure reste à zéro,
les interfaces peuvent encore évoluer entre deux versions mineures.

## [1.0.0] - date à relever — refonte « Hermes au centre »

> **Section préparée, version non ouverte.** Écrite le 8 octobre 2026 à l'étape P9 (part E), complétée le 9 octobre
> 2026 (parts B et C closes, SECU-TUI et P8b fusionnées, branches de P9 réunies) : `VERSION` vaut encore 0.11.0. La
> date sera celle du commit `chore(release): prepare 1.0.0 changelog`, après la relecture indépendante de toute P9
> et le commit d'ouverture (D129). Les runs de la PR de `refonte/hermes-p9` et de
> celle vers `main` n'y figureront pas : le commit du journal les précède (un commit ne peut citer les runs que son
> propre push déclenche, et le compléter après la fusion déplacerait l'étiquette hors du commit de fusion). Ils vont
> dans `docs/refonte/preuves-1.0.0.md` : § 3 pour la PR de `refonte/hermes-p9`, § 4 pour celle vers `main`
> (complété après l'étiquette par une PR de documentation seule).

1.0.0 achève la refonte « Hermes au centre » (étapes P0 à P9). Hermes Agent 0.21.5, épinglé par le condensat de
l'image `v2026.9.24`, est le seul serveur, le seul orchestrateur et la seule source de vérité ; ACP n'a plus de
backend propre et fournit l'image dérivée et ses greffons, l'identité (Authelia), l'exécutant Railway, le poste
Windows facultatif, la station Qt et l'interface française du tableau de bord. L'ancienne plateforme (ligne 0.10,
ci-dessous) reste entière sous l'étiquette `archive/acp-0.10.0-avant-hermes`. **Rien n'est déployé sur Railway** :
la publication précède le premier déploiement, geste du propriétaire (`docs/refonte/railway.md` § 4). Le journal de
chaque étape, mot pour mot, est dans `docs/refonte/historique.md` (partie C) ; les preuves dans
`docs/refonte/preuves-1.0.0.md`.

À partir de 1.0.0, le versionnage sémantique porte sur **nos** interfaces (D130) : contrat `acp-poste/1` (routes
`/api/plugins/acp-poste/v1/*`), protocole `acp-machine/1`, format `ACPB1`, commandes `acp-poste`, formats de
`poste.toml` et d'`executant.toml`, variables Railway documentées (`docs/refonte/image.md` § 4). Les surfaces de
Hermes (API du tableau de bord, JSON-RPC, SDK des greffons) suivent la version épinglée, hors de cet engagement. Une
rupture de nos interfaces appellera 2.0.0.

| Étape | Objet | PR | Commit de fusion |
|---|---|---|---|
| P0 | branche, élagage, gel du moteur | #13 | `29c95b5` |
| P1 | image dérivée et CI de contrat | #14 | `21d13ee` |
| P2 | agent sans outil d'exécution, identité, Railway en code | #15 | `21ac337` |
| P3 | identité visuelle, français, catalogue | #16 | `f59f384` |
| P4 | projets autonomes | #17 | `6c31522` |
| P5 | poste connecté | #18 | `b3faac0` |
| P6 | exécutant Railway | #19 | `7697a1c` |
| P8 | station Qt rebranchée | #20 | `b715edb` |
| P7 | questions, notifications, continuité ; dépôts réels | #21 | `b9779f1` |
| SECU-TUI | correctif de sécurité : `.env` et sources de secrets du volume (D156, D157) | #23 | `5026a70` |
| P8b | station Qt alignée sur P7 (D158, D159) | #22 | `8583642` |
| P9 | exploitation, montée de version, publication | postérieure à ce journal (preuves, § 3) | postérieur à ce journal (preuves, § 3) |

### Ajouté

- **Image Hermes d'ACP** (P1, P2) : image Railway dérivée de `nousresearch/hermes-agent:v2026.9.24` épinglée par
  condensat ; gardes de démarrage dans le crochet s6 `S6_STAGE2_HOOK` et refus en français ; managed scope
  `/etc/hermes` régénérée et relue à chaque démarrage ; agent **sans outil d'exécution** sur Railway (managed scope,
  `.env` géré, garde `pre_tool_call` en liste blanche) ; gardes de plateforme (PID 1, s6, volume) ; commande de
  maintenance `diagnostiquer` ; contrat épinglé (`hermes/contrat/HERMES_VERSION`, OpenRPC de la passerelle).
- **Identité** (P2) : `identite/`, Authelia 4.39.28 épinglé, un seul utilisateur, un seul client OIDC public, passkeys,
  garde root en français, limite mémoire mesurée.
- **Infrastructure Railway en code** (P2, P6, P7) : `.railway/railway.ts` (trois services, trois volumes, échec fermé
  sur les libellés en gabarit), `verifier.mjs`, procédure du propriétaire `docs/refonte/railway.md` ; variables du
  canal de notification déclarées par `preserve()` (D116).
- **Interface** (P3, P4, P5, P7) : thème `acp` généré depuis `design/tokens`, persona française, greffons d'interface
  `acp-interface` (Accueil), `acp-catalogue`, `acp-projets` (Projets et file Questions), `acp-poste-vues` (Poste,
  Routage, Quotas) et `acp-discussion` (discussion réduite sur `/api/ws`), sources dans `apps/interface`, bundles
  committés et vérifiés en CI ; décompte des chaînes de Hermes restées en anglais.
- **Catalogue** (P3, P4) : 14 skills vendorisées à des commits épinglés, sous licence MIT, et 7 skills maison en
  français (deux en P3, cinq pour les projets en P4) ; verrou `hermes/catalogue/catalogue.lock.json` et
  `scripts/verifier_catalogue.py` ; context7, seul serveur MCP côté Hermes, distant ; refus de démarrer sur un
  serveur MCP stdio ou hors catalogue (D8).
- **Projets autonomes** (P4, P7) : greffon `acp-poste` : un tableau kanban par projet, graphe déterministe
  (exploration, planification, implémentation et relecture croisée, synthèse), plafonds et cartes de décision,
  routage des modèles, outils de l'agent, routes du propriétaire, émetteur de notifications (Telegram ou ntfy) ; en
  P7 : file Questions à cinq sections, relancer une carte, qui répond, clore un projet, flux d'invalidation
  `GET /v1/flux`, liens profonds des notifications, bilan quotidien par cron natif, Accueil agrégé ; base du greffon
  au schéma 4.
- **Machines** (P5, P6) : protocole `acp-machine/1` (enrôlement par code, réclamation en attente longue,
  inventaire ; en P6 : `battement`, `terminer`, `question`, `bloquer`, `reprendre`, `arret`), fournisseur de
  jeton machine ; client `apps/poste` : poste Windows (`poste.toml`, coffre DPAPI, sondes Codex et Claude Code,
  installation `packaging/poste`) et exécutant Linux (un UID par agent, dépôts et worktrees, quarantaine des secrets,
  `git bundle`, file de sortie persistante, purge) ; image `executant/` (Codex CLI 0.156.1 et Claude Code 2.1.283
  vérifiés au build) ; visibilité des dépôts mesurée et outil `scripts/preuve_accord_requis.py` (P7).
- **Station de travail Qt** (P8) : connexion native RFC 8252, porteur sur les API du tableau de bord et la façade du
  greffon, JSON-RPC sur Qt WebSockets, pages Accueil, Projets, Questions, Discussion, Poste, Quotas, Routage,
  Diagnostics et Sauvegarde (export chiffré `ACPB1`), bout en bout local `scripts/e2e-desktop-windows.ps1` ; en
  P8b, alignée sur P7 : flux d'invalidation `GET /v1/flux` (D158), Accueil agrégé, file Questions à cinq sections et
  ses gestes (relancer, revues, qui répond, clore), discussions en attente, bilan quotidien, étape P7 détectée par
  `/v1/meta` avant d'être lue (D159).
- **Exploitation** (P9) : `scripts/monter_hermes.py` (`verifier`, `ecrire`, `inventaire`, `derniere`) et sa
  répétition à blanc à chaque construction ; concordance de toutes les épingles de Hermes
  (`scripts/tests/test_epingles_hermes.py`) ; toute copie versionnée contrôlée (`scripts/tests/test_version_complete.py`) ;
  tests de restauration de trois volumes, R1 à R4 (job `restauration` d'`image.yml`, à chaque construction : trois
  volumes au même instant et à des instants différents, reconnexion du propriétaire, Hermes réimporté depuis son
  export) ; témoin d'une release antérieure de Hermes (job `temoin`, `scripts/temoin_hermes.py`) ; montée de données
  d'une version d'ACP à la suivante (job `montee`, chaque ligne d'avant comparée à un contrôle) ; manuel du
  propriétaire `docs/exploitation.md` ; `docs/refonte/historique.md` et `docs/refonte/preuves-1.0.0.md`.
- **CI** : `ci.yml` (moteur gelé, suites sous Linux et Windows, installeur du poste en simulation, interface,
  balayage des secrets), `image.yml`, `executant.yml`, `desktop-ci.yml` ; `desktop-release.yml` crée à l'étiquette
  un brouillon non signé (D131).

### Modifié

- Architecture : Hermes seul serveur et seule source de vérité ; ACP sans API, sans base, sans bus d'événements ni
  CLI propres (P0 à P2) ; exécution principale sur le service Railway `executant`, poste Windows facultatif (P6,
  D74).
- `apps/worker` devient `apps/poste` (commande `acp-poste`), contrat des quotas dans
  `hermes/plugins/acp-poste/contrat` (P0) ; `poste.toml` remplace les réglages `ACP_WORKER_*` (P5).
- Station Qt : rebranchée sur Hermes, ancien client retiré (P8) ; pages relues sur signal du flux, comme le
  navigateur (P8b).
- Pages relues sur signal du flux au lieu du sondage de 15 s (gardé en repli) ; voie Codex ouverte seulement sur un
  dépôt prouvé privé (P7, D103).
- Contrôle des décisions documentées à trois chiffres (P7, P9 : D132).
- Docker sur le poste de travail : arrêté le 8 octobre 2026 (D134), de nouveau permis avec sobriété le 9 octobre
  2026 (D160 : une seule pile à la fois, ressources nommées et retirées) ; l'intégration continue reste la preuve qui
  fait foi.

**Retiré de l'ancienne plateforme** (tout reste sous l'étiquette `archive/acp-0.10.0-avant-hermes`) : en P0, API
FastAPI, base et migrations, bus d'événements, passerelle de fournisseurs, CLI `acp`, interface web Vite (hors
`apps/web/public/assets`), `packages/ui`, contrats TypeScript et Python (hors quotas), `agent-sdk`,
`playwright-reporter`, `e2e`, déploiement Railway multi-services et scripts liés, documentation datée des lots A à
H ; en P5, les réglages `ACP_WORKER_*` du poste (sauf `ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT`) et
`PosteConfig.from_env` ; en P8, l'ancien client Qt (`AuthManager`, cookie `acp_session`, `SessionPersistence`,
`CompatibilityService`, ancien `EventStreamService`, `ArtifactDownload`, pages de l'ancienne API).

### Corrigé

Corrections des relectures indépendantes, une ligne par étape (détail : `docs/refonte/historique.md`, partie B) :
- P0 : 5 défauts confirmés et corrigés (refus des NUL sans l'octet NUL, tests DPAPI réels rétablis, commande
  `journal` sans source retirée, `acp-poste quotas` refusé sans accord avec le retrait d'un réglage sans effet,
  « aucune connexion réseau » rectifié : Codex CLI, que lance `acp-poste quotas`, interroge le serveur d'OpenAI) ;
- P1 : 5 constats, dont deux critiques (`/run/service` laissé à l'agent, `.env` du volume hors managed scope) :
  4 corrigés, 1 en limite dite (port 9119 pris sous le même uid, paré depuis P2 par l'absence d'outil d'exécution) ;
  plus l'élévation par le `PATH` des scripts root, trouvée à la vérification finale et corrigée ;
- P2 : 21 constats de trois relectures (sécurité offensive, exactitude, exploitation), dont les `hooks/` et
  `scripts/` de chaque profil rendus à root ; deux traités par la documentation seule (`vision_analyze`, qui lit
  toute image locale, gardé par décision du propriétaire ; sauvegardes absentes de l'IaC) ;
- P3 : 14 constats (4 moyens, 10 bas) ;
- P4 : 21 constats, tous réels (projets qui s'arrêtaient en silence ou se disaient terminés à tort, redirections
  suivies par les notifications) ;
- P5 : 16 constats (un haut, quatre moyens, onze bas), décisions D67 à D73 ;
- P6 : 19 constats (un critique, quatre hauts), tous réels, plus trois défauts trouvés en les vérifiant ; parmi
  les corrections, l'`auth.json` de Codex n'est plus lisible par une commande de l'agent en régime A ;
- P8 : 16 constats, chacun avec un test qui échoue sans la correction ;
- P7 : relecture finale, 37 constats retenus : 33 corrigés, 3 en limite dite, 1 de procédure (D117 à D121) ;
- SECU-TUI : contre-vérification d'un sceptique (failles traitées par D156 et D157 ; l'écriture d'une clé épinglée
  par `PUT /api/env`, en partie réfutée par la mesure : Hermes la refuse) et audit défensif du 9 octobre 2026
  (variables d'emplacement et d'exécution comme `HERMES_HOME`, lecture des `.env` comme Hermes : deux manques
  prouvés rouges, corrigés par `2c4e2d4`) ;
- P8b : deux relectures, 12 constats (desktop-1 à desktop-12), chacun vérifié dans le code puis traité, les
  constats de code avec un test relevé rouge sans la correction ;
- P9 : relecture de l'outillage de version (six constats sur `scripts/monter_hermes.py` et `image.yml`, chacun avec
  un test rouge d'abord) et vérification factuelle du manuel (19 constats recoupés et corrigés) ; défaut du produit
  trouvé par la montée de données : la reconstruction d'une table du greffon (`notifications`, schéma 4) ramenait
  son compteur `AUTOINCREMENT` (de 7 à 5), corrigé (`fdb41c9`, D153, test d'image rouge sur le code d'avant) ;
  défauts des tests trouvés à leur premier passage en CI, corrigés avant le premier vert (dont un import de l'export
  réputé réussi qui n'avait rien restauré : le test refuse désormais tout import incomplet) ; une attente qui passait
  avec un exécutant non enrôlé (vue que Hermes garde de l'exécutant d'avant) dans la montée, puis la même lecture
  sans attente dans R1, corrigées (`8e58ac9`, `83394a9`) ; la seule différence de la release témoin que rien
  n'attrapait (`config.yaml` sans `_config_version`) attrapée par un test nouveau (`d07753b`) ; critique et
  contre-vérification d'un sceptique des preuves de B et C : listes « jamais vu rouge » complétées, 33 runs de
  témoins de mutation au total (20 pour la restauration, 13 pour la montée) et un inventaire mécanique des
  vérifications (`docs/exploitation.md` § 6.6 et § 10) ; relecture indépendante de toute P9, qui précède le commit
  de ce journal : **à relever** (constats et traitement : `docs/refonte/preuves-1.0.0.md` § 3).

### Sécurité

- Agent sans outil d'exécution sur Railway, garde en liste blanche ; `PATH` des scripts root sans répertoire du
  volume ; managed scope régénérée à chaque démarrage ; Hermes jamais hors de s6 en PID 1.
- Chantier SECU-TUI (PR #23) : toute clé que la managed scope épingle est retirée par root des `.env` et `.op.env`
  du volume, au démarrage et à chaque relance d'un service, noms journalisés, valeurs jamais (D156) ; variables
  d'emplacement et d'exécution (`HERMES_HOME`, valeurs imposées par l'image, noms que Hermes refuse d'écrire)
  refusées dans ces fichiers ; source externe de secrets activée dans un `config.yaml` du volume : refus de démarrer
  et de relancer (D157).
- Connexion par OIDC auto-hébergé seulement (Authelia, un utilisateur, passkeys) ; aucun fournisseur `basic` ni Nous.
- Jetons : coffres Windows (DPAPI, Gestionnaire d'identification) sur le poste et la station ; fichiers 0600 de root
  sur le volume de l'exécutant, jamais en variable (D92) ; aucun secret dans Git (balayage en CI).
- Exécutant : un UID par agent, bac à sable, binaires vérifiés au build, crochets git coupés, `https` seul, **aucun
  push** (D82) ; fichiers de pilotage soumis à revue ; secret détecté : quarantaine, y compris dans chaque commit non
  poussé (D118, D119).
- Hermes et Authelia épinglés par condensat ; montée de version par PR seulement, répétée à blanc à chaque
  construction.

### Vérifié localement

Et en intégration continue : chaque étape a été fusionnée sur des runs verts ; identifiants, compteurs et relectures
dans `docs/refonte/preuves-1.0.0.md`.
- P0 à P8 et P7 : runs des PR #13 à #21 et des commits de fusion (preuves, § 1 et § 2) ; SECU-TUI et P8b : runs
  des PR #23 et #22 et de leurs commits de fusion (preuves, § 1).
- P9, parts A et D : outillage de version vert en CI (répétition à blanc « Aucun écart », Image Hermes
  `37004128839` puis `37028491959`) ; ébauche du manuel relue contre le code et la documentation de Railway.
- P9, part B : test de restauration (job `restauration` d'`image.yml`, R1 à R4) vert depuis `27d2123` (run
  `37768789724`) et sur la tête réunie `90102b1` (run `37908787791`) ; 20 runs de témoins de mutation, chacun rouge
  pour sa raison.
- P9, part C : témoin `v2026.9.21` rouge comme attendu (5 écarts, tous attrapés) et son contrôle sur `v2026.9.24`
  vert (runs `37769347253` et `37769357764`, jobs « temoin ») ; montée de données de la fin de P8 (schéma 3) au
  schéma 4 verte (run `37784839347`), rejouée sur la tête réunie depuis `b715edb` et depuis `8583642` (runs
  `37908841650`, « migration de schéma : oui », et `37908855369`, « non ») ; 13 runs de témoins de mutation.
- Réunion de P9 avec SECU-TUI et P8b (9 octobre 2026), tête `90102b1` : CI, Image de l'exécutant, Desktop CI et
  Image Hermes verts (le job « image » à sa seconde tentative, voir « Limites connues ») ; en local, sur Docker de
  nouveau permis (D160) : pytest dans l'image 874 réussis, contrat de sécurité 68, contrat de restauration 13.
- PR de `refonte/hermes-p9` vers `refonte/hermes`, puis de `refonte/hermes` vers `main` (quatre workflows) :
  postérieures à ce journal ; leurs runs sont relevés dans `docs/refonte/preuves-1.0.0.md`, § 3 et § 4.

### Limites connues

- **Rien n'est déployé sur Railway** : tout ce qui ne se prouve que là reste non prouvé (`docs/refonte/railway.md`
  § 12 et § 14.7, `docs/exploitation.md` § 10) : bord et PID 1 réels, sonde R0 (régime de l'exécutant, donc ouverture
  de la voie Codex), sauvegardes réelles, répétition de restauration et reconnexions réelles, notification et
  parcours réels sur le téléphone, premier dépôt réel, coût réel. **Aucun vrai compte** n'a servi (abonnement ChatGPT
  de Hermes, Codex, Claude Code, GitHub, canal de notification) : tous les tests emploient un agent, des CLI et des
  comptes factices.
- **Constat de sécurité corrigé, avec une limite** : une fois, après un redémarrage du conteneur sur un volume
  piégé, la session du tableau de bord a reçu les outils d'exécution posés par le `.env` du volume (deuxième des
  trois couches de la défense de P2, `docs/refonte/image.md` § 5), alors que l'api_server les refusait (Image Hermes
  `37784838264`, tentative 1, test `test_volume_piege_apres_relance`). Le chantier SECU-TUI en a prouvé la cause sans
  course : Hermes publie la valeur du `.env` du volume avant d'appliquer la portée gérée (run jetable `37831355746`,
  rouge attendu sur le code de P7) ; il y mesure que la garde `pre_tool_call` aurait refusé l'appel. Correctif et
  refus d'une seconde faille hors des trois couches (D156, D157, rubrique « Sécurité ») fusionnés par la PR #23
  (`5026a70`, 9 octobre 2026). Reste, non corrigée : root ne retire les clés épinglées des `.env` du volume qu'au
  démarrage et à chaque relance d'un service ; une écriture **directe** d'un `.env` du volume pendant la vie d'un
  service (faille de Hermes, ou shell du propriétaire) rouvrirait donc la fenêtre jusqu'à la relance suivante ;
  quelques variables ni épinglées ni refusées dans le volume restent non mesurées (`docs/refonte/image.md` § 10).
- Binaires de la station **non signés** (aucun certificat) : l'installeur et l'archive portable sont fabriqués par
  chaque Desktop CI (empaquetage « à blanc » : produits, ni signés ni publiés), jamais installés ni lancés sur un
  Windows propre ; `Desktop Release` n'a jamais tourné (premier run à l'étiquette, brouillon non signé : D131).
- Les bouts en bout locaux du poste (dernier passage : P5) et de la station (P8), les témoins négatifs de P4 à P6 et
  la recompilation du verrou Python sont des scripts à Docker local qu'aucun workflow n'appelle : arrêtés avec Docker
  le 8 octobre 2026 (D134), ils peuvent de nouveau tourner depuis le 9 octobre 2026 (D160), mais n'ont été rejoués
  ni sur le code de P7 ni sur celui de P9.
- Tests instables connus, verts sur la tête : le test navigateur de la connexion (course avec la relecture
  périodique du tableau de bord de Hermes, qui renvoie la page à la connexion après la déconnexion : rouge une fois,
  Image Hermes `37908787791`, tentative 1) ; sous Windows, `apps/poste/tests/contrat/test_enrolement.py:78` (faux
  serveur TLS) ; des tests temporisés du poste sous forte charge locale.
- Cookies de Hermes sans `Secure` tant que `trusted_proxies` est vide ; jeton de rafraîchissement rejoué : 503
  persistant jusqu'à la déconnexion ou l'effacement des cookies (`docs/refonte/identite.md` § 12).
- Pages natives de Hermes en partie en anglais ; rendu éprouvé dans Chromium seulement.
- Station Qt : flux et gestes de P7 (P8b) prouvés contre le faux Hermes de ses tests natifs et les fixtures
  partagées seulement, jamais face à un vrai greffon P7 (`docs/refonte/desktop.md`, « Non prouvé ») ; MCP côté
  exécutant reporté.
- `preserve()` sur une variable jamais posée : supposé sans effet (D116).
- Aucune montée vers une release de Hermes postérieure à `v2026.9.24` (aucune n'existe au 9 octobre 2026, mesuré par
  `scripts/monter_hermes.py derniere`) ; montée de données depuis `v2026.9.21` non lancée (D147) ; montée d'Authelia
  non prouvée (D152) ; retour arrière par Rollback non prouvé ; un vrai agent jamais employé.
- Signature cosign de Codex non vérifiée (identité non établie).
- Moteur Pixel Office gelé ; Godot hors périmètre.

## 0.10 — ligne archivée, jamais étiquetée

Ancienne plateforme (API, base, interface web Vite, CLI `acp`, client Qt d'avant la refonte) : ses trois sections,
autrefois « [Unreleased] », « 0.10.0 (préparation) » et « 0.9.1 (préparation) », sont gardées telles quelles, à
deux retouches près : titres abaissés d'un niveau, et **trois liens réécrits** (`docs/subscription-quotas.md`,
`docs/desktop-chat-projects-2026-09-23.md` et `docs/functional-completion-2026-09-23.md`, retirés de l'arbre
depuis P0), qui mènent désormais à ces fichiers sous l'étiquette `archive/acp-0.10.0-avant-hermes`
(`blob/60a49b6…`). Aucune n'a été publiée ni étiquetée ; leurs fonctions n'existent plus depuis P0, et les autres
documents qu'elles citent restent consultables sous la même étiquette.

### [Unreleased]

#### Quotas réels d'abonnement

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
dans [`docs/subscription-quotas.md`](https://github.com/Paul-Berdier/agent-company-platform/blob/60a49b6c5ab2ca5d73cfdf55919c85903a261330/docs/subscription-quotas.md).

#### Interface conversations et projets

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
  [`docs/desktop-chat-projects-2026-09-23.md`](https://github.com/Paul-Berdier/agent-company-platform/blob/60a49b6c5ab2ca5d73cfdf55919c85903a261330/docs/desktop-chat-projects-2026-09-23.md).

#### Intégration fonctionnelle desktop et poste local

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
[`docs/functional-completion-2026-09-23.md`](https://github.com/Paul-Berdier/agent-company-platform/blob/60a49b6c5ab2ca5d73cfdf55919c85903a261330/docs/functional-completion-2026-09-23.md).
Hermes répond localement, mais son diagnostic est dégradé ; aucune génération réelle
payante, reprise automatique d'équipe interrompue, fusion automatique des branches
produites ou publication finale 0.10.0 n'est annoncée.

### 0.10.0 (préparation) - 2026-09-23

Client natif Qt : intégration du Lot H et parcours métier reliés à l'API.
Cette version reste en préparation ; elle n'annonce pas une recette Railway achevée.

#### Ajouté

- écrans natifs de projets, conversations, missions/tentatives, Studio et livrables ;
- inventaire des agents, workers et fournisseurs, liaisons MCP et compétences ;
- décisions d'approbation, alertes, budgets et automatisations avec formulaires typés ;
- réglages d'apparence, vérification explicite des publications GitHub et session
  mémorisée sur consentement dans le coffre Windows ;
- tests HTTP loopback, chargement QML et parcours du client Qt contre une vraie API
  SQLite jetable ; projection hachée du verrou Python pour cette recette en CI Windows.

#### Modifié

- contexte de projet partagé par les écrans, navigation et palette de commandes ;
- arrêt, relance et envois incertains rapprochés avec la même clé pendant la session ;
- README, documentation de parité, sécurité, construction, installation et reprise
  alignés sur les fonctions présentes et les limites observées.

#### Corrigé

- réponses et réessais d'une ancienne origine annulés après changement de serveur ;
- reprise de session préservant le contexte connu, refus 401/403 terminaux uniques,
  et absence de boucle de renouvellement sur un refus métier ;
- fermeture des services dans l'ordre de leurs dépendances et dialogues QML sans
  boucle de dimensionnement ;
- encodage des sorties MSVC stabilisé pour que Ninja détecte les changements d'en-têtes.
- droits effectifs de création de projet et de liaison d'extensions vérifiés avant envoi ;
- DLL redistribuables MSVC x64 embarquées dans le paquet portable, avec contrôle de version.

#### Sécurité

- aucun cookie ACP transmis à GitHub ; notes de publication et contenus métier rendus
  en texte brut, liens de publication limités au dépôt officiel ;
- cookie mémorisé lié à l'URL complète et à son expiration ; aucun repli en stockage clair ;
- téléchargement de livrable atomique et borné, contrôles de taille/SHA-256, redirections refusées ;
- un corps HTML ou une redirection ne peut plus apparaître comme un flux SSE en direct.

#### Vérifié localement

- backend combiné : 2 896 tests réussis, 70 ignorés ; contrats desktop : 6 réussis ;
- compilation MSVC Release et 21 suites natives réussies en 54,82 secondes ;
- parcours Qt/API réelle : 3 réussis, 0 ignoré, livrable de 180 224 octets vérifié ;
- session/coffre dans la session Windows locale : 24 réussis, aucun ignoré ;
- projection du verrou Windows : 4 tests réussis ; dépendance incrémentale MSVC prouvée ;
- portable démarré avec PATH Windows seul ; installation/désinstallation isolées sans élévation,
  codes 0, 1 387 fichiers vérifiés ; application installée non lancée pour préserver le profil ;
- résultats finaux de compilation, CI et empaquetage dans
  `docs/desktop-validation-2026-09-23.md` ; les tentatives échouées y restent distinguées.

#### Limites connues

- recette Railway, fournisseur/worker réels, Windows propre et signature de code non prouvés ;
- première revue visuelle interrompue par l'expiration de l'autorisation de capture ;
  recette Qt complétée ensuite avec le harnais natif décrit dans la validation fonctionnelle ;
- mise à jour manuelle depuis la publication GitHub ; aucune installation automatique ;
- import/administration avancée de MCP et compétences encore partiellement réservés au web/CLI ;
- aucune publication 0.10.0 ni fin de la Desktop V1 annoncée ; Pixel Office conservé à part ;
- les 26 constats ouverts du Lot H demeurent suivis dans `docs/lot-h-091-review-status.md`.

### 0.9.1 (préparation) - 2026-09-22

Durcissement du Lot H en cours. L'inventaire des constats, des corrections reprises
et des travaux encore ouverts figure dans `docs/lot-h-091-review-status.md`.

#### Ajouté

- migration PostgreSQL 0003 pour les tailles, durées, codes de sortie et séquences
  sur 64 bits, ainsi que les références longues ; schéma SQLite historique conservé ;
- tests de contention budgétaire et d'ingestion d'un rapport de 2 000 cas avec
  réservation concurrente ; suites et parcours PostgreSQL dans l'intégration continue ;
- validation commune des bornes de stockage, des horodatages UTC et des NUL.

#### Modifié

- événements métier numérotés et journalisés au commit ; verrous de projet
  budgétaires compatibles avec les insertions filles tout en sérialisant les décisions ;
- relais SQLite avec réservation persistante courte et verrou libéré avant l'appel HTTP ;
  attente bornée des migrations au démarrage et recul en cas de panne du consommateur ;
- installation CI Python depuis le verrou haché, sans résolution des dépendances
  locales, puis vérification de cohérence des distributions et des déclarations.

#### Corrigé

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

#### Sécurité

- diagnostics de messages illisibles expurgés de leur contenu et des détails SQL ;
- exclusions Docker récursives des données locales, secrets et éléments sous licence,
  avec contrôle du contexte et défense supplémentaire dans l'image web ;
- les garde-fous de schéma ne déclarent pas une base utilisable sur la seule présence
  d'une estampille Alembic.

#### Vérifié localement

- SQLite : 2 852 tests réussis et 70 ignorés ; PostgreSQL : 2 862 réussis et 60 ignorés,
  après suites complètes et reprises ciblées documentées, sans modification du produit ;
- six parcours API réussis sur les deux dialectes, et construction des roues
  `acp-contracts`, `acp-database` et `acp-api` ;
- rapports initiaux, incidents de validation et limitations détaillés dans
  `docs/lot-h-091-review-status.md` ; les exécutions interrompues n'y valent pas succès.

#### Limites connues

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
