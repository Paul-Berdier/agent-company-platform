# Hermes autonome : conception corrigée (P4 à P8)

> Copie de référence du plan d'autonomie **retenu par le propriétaire le 25 septembre 2026** pour
> remplacer les phases P4 à P8 du [plan de la refonte](plan.md) (voir son § 1). Recopiée dans le dépôt
> le même jour, **telle quelle** : le texte ci-dessous est celui du plan, sans ajout ni retouche ;
> seule cette note et l'annexe finale, séparée, sont propres au dépôt.
>
> Les références `fichier:ligne` désignent le clone de Hermes Agent 0.21.5 (`f97608f`), la source
> partielle de Codex 0.156.1 et, pour « le dépôt », le worktree `refonte-hermes-p2` **au moment de la
> rédaction** (`21d13ee`, avant les commits de P2) : certaines lignes du dépôt ont bougé depuis.
>
> Rien de ce plan n'est implémenté, hors les épingles de la managed scope déjà posées par P2 (annexe).
> Les décisions de son § 11 restent à prendre ; elles seront consignées au fil des phases.

Date : 25 septembre 2026. Références : clone Hermes 0.21.5 `f97608f` (chemins relatifs à ce clone sauf mention), source Codex 0.156.1 partielle (`codex-src-0156/codex-rs`), worktree `refonte-hermes-p2` (noté « dépôt »). **V** = vérifié dans le code ou la doc ; **S** = supposé, à prouver dans la phase indiquée.

Cette version intègre les 18 corrections des deux relectures. Toutes ont été recoupées dans les sources et sont exactes ; aucune n'est rejetée. Les nuances figurent dans « Risques », à la fin.

---

## 1. Résumé pour le propriétaire

- **Le poste n'est plus en lecture seule, et aucune signature n'est demandée par tâche.** Hermes devient un chef de projet autonome. Vos gestes ne portent que sur l'irréversible et sur ce qui sort de chez vous : push, fusion, publication, dépenses, élargissement du périmètre.
- **Où vit un projet.** Dans le kanban de Hermes sur Railway, avec un tableau par projet. Pas dans la conversation, ni dans le téléphone.
- **Comment il avance sans vous.** Le répartiteur de Hermes parcourt tous les tableaux toutes les 60 s, sans aucun client connecté (V).
  1. Le greffon `acp-poste` fait d'abord **explorer le dépôt** par le poste, en lecture seule.
  2. Une carte de **planification** Hermes, sans terminal, découpe ensuite le projet à partir de cette exploration. Elle crée des cartes Codex, Claude et Hermes, chacune avec son exécutant, son modèle et son effort.
  3. Une **synthèse** juge le résultat et relance si besoin, dans des plafonds fixés.
- **Le poste Windows.** Il réclame ses cartes en HTTPS sortant et écrit seul dans un worktree, sur une branche `hermes/<carte>`, et seulement dans les dépôts autorisés. Deux exécutants :
  - Codex sous bac à sable Windows *elevated*, imposé et vérifié ;
  - Claude en `--restricted`.

  Il vérifie le travail, committe en local et rend compte.
- **Modèles.** Aucun nom n'est écrit en dur.
  - Codex : la liste vient de `model/list` sur votre compte. « sol » désigne `gpt-6-sol` ou `gpt-5.6-sol`. « artra » désigne `gpt-6-astra` ou `gpt-5.6-terra`. Le relevé de votre compte et votre réponse trancheront.
  - Claude : on utilise les alias documentés, et le modèle réellement servi est observé à chaque exécution. Aucune liste n'est lisible par une voie autorisée.
  - Une table de routage fait le choix ; vous la validez une fois. Le palier Fast est interdit par défaut.
- **Questions.** Elles sont durables dans le greffon. La carte concernée est *mise en attente*, pas *bloquée* : bloquée, elle partirait en triage dès la deuxième question. Hermes répond s'il le peut. Sinon, le greffon vous envoie une notification (Telegram ou ntfy), et vous répondez depuis n'importe quel appareil.
- **Retour sur le PC.** Le navigateur ou le desktop Qt montrent le même état, puisque tout est stocké sur Railway.
- **Limites dites honnêtement :**
  - sans signature, un Railway compromis ou un Hermes victime d'une injection peut faire écrire le poste. Ces écritures restent bornées par `poste.toml`, les plafonds et l'absence de push ;
  - PC éteint, les cartes du poste attendent. Aucun avancement n'est simulé.

---

## 2. Scénario téléphone → Hermes → poste → PC

1. **Lancement depuis le téléphone.** Vous ouvrez ACP (tableau de bord Hermes habillé, connexion OIDC, P2 et P3). Deux entrées possibles :
   - le formulaire « Nouveau projet », qui appelle `POST /api/plugins/acp-poste/v1/projets` ;
   - la discussion, où l'agent appelle l'outil de greffon `projet_lancer`. Les toolsets de greffon sont actifs par défaut (`hermes_cli/tools_config.py:538-545`, V).

   Le greffon, de façon déterministe :
   - crée le tableau du projet (`create_board`, `hermes_cli/kanban_db.py:611`, V) et enregistre le projet (alias du dépôt, objectif, politique) ;
   - pour un projet sur un dépôt, crée une carte **« exploration »** de la voie `poste-claude` ou `poste-codex`, selon la classe « exploration » de la table de routage ;
   - crée une carte **« planification »** : assignee `default`, skills `acp-orchestration` et `acp-routage`, parent = l'exploration (`create_task`, `kanban_db.py:1249`, V). Sans dépôt (recherche pure), la planification part seule.
   - n'utilise **aucun abonnement natif** de notification (voir §5).

   Les cartes Hermes ne portent de `model_override` que si la table de routage en fixe un, et si cet identifiant figure dans le relevé brut `model/list` du poste. Sinon, le worker prend le modèle par défaut du profil, celui que vous avez choisi dans Hermes.

2. **Vous fermez le téléphone.** Rien ne dépend de la page.
   - Un tour de discussion en cours continue tant qu'il produit : il s'arrête après 600 s sans activité (`tui_gateway/server.py:131-137`, V).
   - Une session détachée et inactive est libérée après 20 s ; son historique reste dans `state.db` (V ; historique relisible, S).
   - Le projet, lui, vit dans le tableau.

3. **Exploration par le poste**, si le PC est allumé.
   - Le poste attend en long-poll sur `/machine/v1/reclamer`. Le greffon appelle `claim_task(ttl=2700, claimer="acp-poste:<id machine>")`. Le claimer est **stable** et vaut aussi pour `heartbeat_claim` (`kanban_db.py:2263-2296` et `2383-2398`, V).
   - Exécution en **lecture seule**, au choix :
     - `claude -p --restricted --tools Read,Glob,Grep …` ;
     - `codex exec --sandbox read-only …`.
   - Produit : une carte du dépôt (structure, fichiers clés, commandes de vérification détectées), puis `complete_task`.
   - PC éteint : l'exploration attend, et l'interface affiche « Planification en attente de l'exploration par le poste ».

4. **Planification sur Railway**, au plus 60 s après.
   - Le répartiteur lance `hermes -p default --cli --accept-hooks --skills … [-m …] [--reasoning …] --toolsets <liste résolue> chat -q "work kanban task <id>"` (`hermes_cli/kanban_db_dispatch.py:2676-2708`, V ; `--accept-hooks` est systématique).
   - Les outils du worker sont résolus sur la plateforme `cli`, puis `agent.disabled_toolsets` est retiré en dernier (`kanban_db_dispatch.py:2620-2645` ; `tools_config.py:622-628`, V). Le worker n'a donc ni terminal, ni fichiers, ni exécution de code, ni navigateur, ni **cronjob**, ni **delegation**, ni **connections** (managed scope, §7 ; V dans le code, S sur Railway).
   - Le résumé de l'exploration lui parvient par le contexte natif des parents terminés (`build_worker_context`, `kanban_db.py:3983`, V).
   - Il lit `poste_catalogue` (exécutants, modèles lus, quotas, table de routage) et `projet_etat`, puis appelle `projet_planifier(étapes)`. Le greffon crée alors, sur le tableau lu dans `HERMES_KANBAN_BOARD` et jamais choisi par le modèle :
     - les cartes `poste-codex` et `poste-claude` d'implémentation. Le `model_override` vaut l'identifiant lu. L'effort exact est rangé dans la table `demandes`, et `reasoning_effort` n'est posé que si la valeur appartient à l'énumération Hermes (`kanban_db.py:115-127`, V) ;
     - une carte de relecture croisée par carte d'implémentation, confiée à l'autre exécutant ;
     - la synthèse, dont les parents sont toutes les autres cartes (`website/docs/user-guide/features/kanban.md:724-751`, V).
   - Le worker termine ensuite par `kanban_complete`.

5. **Réclamation.** `claim_task` revérifie les parents (V). Le greffon renvoie au poste une demande structurée : exécutant, modèle, effort, palier, alias du dépôt, consigne, résumés des parents.

6. **Exécution sur le poste.**
   - **Revalidation** contre `poste.toml` et le dernier catalogue. En cas d'écart : échec fermé, puis `block_task(kind="capability")` avec une raison en français.
   - **Worktree** `C:\ACP\espaces\<alias>\<carte>`, branche `hermes/<carte>`, créée depuis la branche de la carte parente quand le dépôt est le même.
   - **Codex** : `codex exec --json -m <id> -c model_reasoning_effort=<effort> -c service_tier="default" -c windows.sandbox="elevated" --sandbox workspace-write --output-schema <termine|question|echec>`, avec le réseau coupé et le keyring imposé. Le palier `default` n'envoie aucun palier au serveur (`protocol/src/openai_models.rs:900-905`, V). Le mode *elevated* est imposé en ligne de commande, jamais déduit (§4).
   - **Claude** : `claude -p --restricted --model <alias|id> --effort <effort> --tools Read,Glob,Grep,Edit,Write --permission-mode acceptEdits --permission-prompts none --settings <fichier du poste : availableModels> --json-schema … --output-format stream-json`. Le poste lit le modèle réellement servi dans l'événement `system/init` (`cc-headless.md:218`, V). S'il diffère du modèle demandé, il arrête l'exécution et refuse en français.
   - **Battements toutes les 60 s** : `heartbeat_claim(claimer)` et `heartbeat_worker(note)`. La note est un résumé d'avancement, borné et balayé. Si `heartbeat_claim` renvoie `False`, la réclamation est perdue (redéploiement ou expiration). Le poste arrête alors l'exécutant, committe le travail en cours sur la branche et repasse par la route `reprendre` (§6).

7. **Fin de tentative.**
   - **Vérification** par la commande déclarée du dépôt, sous `codex sandbox windows`, avec l'utilisateur hors ligne (S). En cas d'échec, reprise du fil (`codex exec resume` ou `claude --resume`) avec la sortie, N fois au plus.
   - **Commit** par le poste, git lancé sans crochets. Calcul du diff, puis deux contrôles :
     - **fichiers de pilotage des agents** : `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.codex/`, `.agents/`, `.github/workflows`, `hermes/gere`, à toute profondeur, casse ignorée, séparateurs normalisés, liens et jonctions résolus, renommages suivis. Si l'un est touché, la carte passe en revue au lieu de done ;
     - **balayage des secrets** : valeurs exactes et motifs, en échec fermé.
   - **Issue « termine »** : `complete_task(expected_run_id, summary, metadata)`, avec dans les métadonnées le modèle demandé, le modèle servi, le palier servi, les jetons, la branche et le diffstat (`kanban_db.py:2723`, V).
   - **Issue « question »** : route `question`. Le greffon enregistre la question dans sa table `questions`, puis appelle `schedule_task(expected_run_id)`. La carte passe en `scheduled`, un état qui ne compte pas comme un blocage et que rien ne réveille seul (`kanban_db.py:3952-3978`, V). Il crée enfin une carte « répondre » pour Hermes, ou escalade selon la politique du projet.
   - **Quota atteint** : `schedule_task`. Le greffon débloque la carte à l'heure de remise à zéro.
   - **Refus de capacité** : `block_task(kind=capability)`. À la deuxième occurrence du même type, la carte passe en **triage** (`kanban_db.py:111` et `3302-3328`, V). La page Questions liste alors les cartes en triage avec une action « Reprendre », qui appelle `specify_triage_task` (`kanban_db.py:3819-3875`, V).

8. **Relecture croisée.** La relecture tourne en lecture seule sur la même branche. Sur un verdict « corrections », la route `terminer` suit un ordre précis :
   1. créer la carte de correction ;
   2. la lier comme parente de la synthèse (`link_tasks`, qui repasse la synthèse en `todo`) ;
   3. appeler `complete_task` sur la relecture.

   Cet ordre compte : `complete_task` recalcule de façon synchrone les cartes prêtes (`kanban_db.py:2821`, V), et `link_tasks` refuse un enfant déjà lancé (`kanban_db.py:1652-1656`, V). Deux tours de correction au plus.

9. **Synthèse.** Elle part sur Railway quand tous ses parents sont terminés, et juge à partir de leurs résumés. Deux issues :
   - de nouvelles cartes, dans la limite du plafond de tours ;
   - la conclusion, éventuellement avec une carte d'intégration qui fusionne les branches en local dans `hermes/projet-<slug>`, sans push.

   L'émetteur du greffon envoie ensuite « Projet terminé ».

10. **Une question surgit.** La carte « répondre » tourne sous `default` avec la skill `acp-questions`.
    - Si les décisions du projet couvrent la question, Hermes appelle `question_repondre` : `add_comment`, puis `unblock_task` (`kanban_db.py:1763` et `3644`, V).
    - Sinon, il appelle `question_escalader` : notification et entrée dans la file Questions.

11. **Retour sur le PC.** Même compte OIDC, dans le navigateur ou le desktop Qt (P8).
    - L'accueil montre les projets (cartes faites sur le total, dernières notes, branches), les questions (cartes en attente de réponse ET cartes en triage), le poste (en ligne ou hors ligne) et les quotas.
    - Vous répondez : le greffon ajoute le commentaire, puis `unblock_task` remet la carte en `ready`. Le poste la réclame et reprend le fil local de l'exécutant avec votre réponse.

12. **Fin.** La branche `hermes/projet-<slug>` vous attend sur le PC. Push, PR, fusion et publication se font sur votre geste.

---

## 3. Routage des modèles

### Trois catalogues, rien d'écrit en dur

**Codex (poste).** `model/list {includeHidden:false}` de l'app-server 0.156.1, dans le compte `acp-poste` connecté à votre ChatGPT.
- Champs relevés : `id`, `displayName`, `description`, `isDefault`, `defaultReasoningEffort`, `supportedReasoningEfforts`, `serviceTiers`, `defaultServiceTier`, `upgrade` et `upgradeInfo.retirementAt`. La pagination suit `nextCursor` (`codex-appserver-schema/v2/ModelListResponse.json`, V).
- La liste dépend du compte : elle est téléchargée puis gardée en cache (models-manager, V).
- Catalogue embarqué, sans compte (`codex-bundled-models.json`, V) :
  - `gpt-6-astra` : palier par défaut aucun, efforts `low` à `ultra` ;
  - `gpt-6-sol` et `gpt-6-luna` : **palier par défaut `priority`, c'est-à-dire « Fast »** ;
  - `gpt-5.6-sol` : paliers `priority` et `ultrafast` ;
  - aussi `gpt-5.6-terra`, `gpt-5.6-luna` et `gpt-5.5`.
- Donc « sol » désigne `gpt-6-sol` ou `gpt-5.6-sol`, et « artra » désigne `gpt-6-astra` ou `gpt-5.6-terra`. **À trancher** par le relevé de votre compte (P5) et par votre réponse. Aucun candidat n'est « probable ».

**Claude (poste). Aucune lecture de liste par une voie autorisée.**
- `get_server_info()` du SDK Python n'est documenté que pour les commandes et les styles de sortie (`py.md:472`, V). Seul le SDK TypeScript documente `supportedModels()`.
- La recherche du projet consigne qu'on ne peut pas utiliser l'Agent SDK avec une connexion OAuth grand public (`research.json`, clé `claude-quotas`, source support.claude.com 11145838). La page juridique réserve l'Agent SDK à l'authentification par clé d'API (`cc-legal-and-compliance.md:48-50`, V).
- Le catalogue Claude se compose donc de trois éléments :
  1. les **alias documentés** : `opus`, `sonnet`, `haiku`, `fable`, `best`, `opus[1m]`, `sonnet[1m]`, `opusplan` (`cli.md:105` ; code.claude.com/docs/en/model-config, V) ;
  2. la **table documentée des efforts par modèle**. Un effort non pris en charge retombe en silence au niveau inférieur : cette retombée est à détecter (model-config, V) ;
  3. la **résolution observée** : le modèle servi, lu dans `system/init` à chaque exécution et gardé avec sa date (« observé le … » ; « Non observé » avant la première exécution).
- `availableModels`, passé dans `--settings`, restreint les modèles à ceux de `poste.toml`. Attention : un modèle refusé est remplacé au démarrage par le modèle par défaut, avec un simple avertissement (model-config, V). Le poste compare donc `system/init` à la demande et refuse tout écart.
- La voie par le SDK reste une **décision explicite** de votre part, avec le risque sur les conditions d'utilisation écrit noir sur blanc.

**Hermes, le cerveau** (cartes planification, synthèse, recherche, « répondre »).
- `/api/model/options` n'est **pas** une liste lue du compte :
  - Hermes y ajoute des modèles synthétiques de compatibilité ascendante et des variantes `-900k` (`hermes_cli/codex_models.py:42-52` et `59-94`, appliqué aussi en direct à `168` et `203`, V) ;
  - sans jeton, il retombe sur une liste écrite en dur (`codex_models.py:204-207` ; `hermes_cli/models.py:1299-1314`, V).
- Règle retenue : par défaut, le modèle du profil, choisi par vous. Un `model_override` n'est admis que si l'identifiant figure dans le **relevé brut `model/list` du poste**, sur le même compte ChatGPT, ce que vous confirmez une fois. Une variante `-900k` n'est admise que si son modèle de base y figure, et seulement par un choix explicite de votre part.
- Épingler `agent.service_tier: ""` (mode normal) dans la managed scope (`hermes_cli/config_defaults.py:134-136`, V).

### Relevé et publication

- Le poste relève les modèles au démarrage, toutes les 30 min, et après tout changement de version de CLI ou de compte. Il publie `{voie, version CLI, relevé_le, modèles, quotas, résolutions Claude observées}` sur `/machine/v1/inventaire`.
- Affichage : « Inconnu » sans relevé ; « Périmé (relevé il y a …) » quand le relevé est trop vieux ; « Liste de secours » si une source retombe sur une liste écrite en dur.
- Quotas :
  - Codex : `account/rateLimits/read {excludeResetCreditDetails:true}`, complété par `account/rateLimits/updated` ;
  - Claude : la ligne d'état (`five_hour`, `seven_day`), puis `rate_limit_event` pendant les cartes.

### Table de routage

Elle vit dans le greffon et se modifie depuis le web et le desktop. Chaque classe porte une liste **ordonnée** d'entrées (voie, identifiant, effort, palier).

Classes proposées : exploration (lecture seule), planification et synthèse (Hermes), recherche web (Hermes), architecture, implémentation, débogage et tests, relecture croisée, documentation, petite tâche mécanique.

Après le premier relevé, la page Routage montre les listes lues et une suggestion calculée sur les seuls champs lus. Vous validez ou corrigez une fois. Tant que la table n'est pas validée, la planification choisit un triplet présent dans le catalogue, guidée par la skill `acp-routage`, et le greffon vérifie ce choix.

### Résolution déterministe

Elle s'applique dans `projet_planifier` et `poste_deleguer`.

1. Surcharge du propriétaire : sur la carte, sinon sur le projet, sinon globale.
2. Choix explicite de la planification, s'il figure dans le catalogue et si la classe l'autorise.
3. Première entrée de la classe qui réunit toutes ces conditions :
   - modèle au catalogue ;
   - effort pris en charge ;
   - palier autorisé ;
   - quota sous le seuil (90 %) ;
   - voie autorisée.
4. Sinon, selon votre ordre de repli : refus en français (« Aucun modèle disponible pour la classe … : … »), ou attente de la remise à zéro par `schedule_task`. **Jamais de repli silencieux.**

Au moment de réclamer, le poste revalide le modèle, l'effort, le palier et la version de CLI.

### Effort et palier

- L'effort exact va dans la table `demandes`. Le `reasoning_effort` de la carte n'est posé que si la valeur appartient à l'énumération Hermes, sinon Hermes lève `ValueError` (`kanban_db.py:115-127`, V).
- **Palier Codex : `-c service_tier="default"` à chaque `exec` et à chaque `exec resume`** (`config/src/config_toml.rs:396-398`, V). Le palier servi est lu dans les événements de session et consigné ; un palier `priority` non autorisé est refusé en français.
- Interdits par défaut, et levables par vous seul :
  - les efforts `ultra` et multi-agents, et `ultracode` ;
  - les paliers `priority`, `ultrafast` et Fast (2,5 fois le tarif, `pricing.md:578-579`) ;
  - la consommation de crédits de remise à zéro ;
  - le mode rapide de Claude Code (clé de réglage à relever, S).

### Surcharge et traçabilité

- Trois chemins de surcharge :
  - dans la discussion, par l'outil `routage_surcharger`, journalisé avec l'auteur et la date ;
  - dans l'interface, par projet ou par carte ;
  - dans `poste.toml`, pour ce que le PC refuse toujours.
- Chaque carte affiche le modèle demandé et le modèle servi, et, pour Codex, le palier servi. Un écart est signalé.
- Concurrence : une carte à la fois par exécutant, file par priorité.

---

## 4. Politique d'autonomie

### Recommandée : option A, autonomie dans les espaces de projet, sans signature par tâche

**Ce que Hermes et le poste font seuls :**
- planifier et découper, créer des cartes et des dépendances ;
- choisir l'exécutant, le modèle et l'effort selon la table de routage ;
- explorer et lire les dépôts autorisés ;
- écrire dans le worktree de la carte ;
- lancer la vérification dans le bac à sable ;
- committer en local et fusionner en local vers `hermes/projet-<slug>` ;
- relire en croisé, corriger, relancer ;
- répondre aux questions couvertes par les décisions du projet ;
- attendre la remise à zéro d'un quota ;
- faire des recherches web (Hermes) ;
- archiver.

**Ce qui exige votre accord explicite**, par un geste dans ACP et jamais par une signature :
1. Tout push, y compris des branches `hermes/*`, et toute écriture dans la branche par défaut.
2. Toute fusion, PR, étiquette ou release.
3. Tout contenu visible par des tiers : issues, commentaires, messages, e-mails, paquets, déploiements.
4. Toute dépense hors enveloppe :
   - palier Fast ou `priority` ;
   - crédits de remise à zéro ;
   - dépassement payant de Claude ;
   - clé d'API payante ;
   - changement d'offre Railway.
5. Toute suppression hors de l'espace de la carte : autres branches, fichiers hors du worktree, historique réécrit.
6. Tout élargissement du périmètre :
   - nouveau dépôt ;
   - exécutant ou modèle interdit ;
   - réseau pour les exécutants ;
   - MCP, skill ou greffon hors catalogue ;
   - compte, OAuth ou secret ;
   - changement de managed scope.
7. **Toute tâche planifiée (cron).** Elle se crée par vous, depuis la page Cron du tableau de bord (`hermes_cli/web_routers/cron.py`), jamais par l'agent : le toolset `cronjob` est coupé.
8. **Les écritures de l'agent dans sa mémoire et dans les skills.** Elles sont mises en attente de votre validation (`memory.write_approval` et `skills.write_approval`, §7).
9. L'intégration de modifications des fichiers de pilotage des agents : la carte passe en revue.
10. Les efforts `ultra`, `max` multi-agents et `ultracode`, sauf autorisation dans la table.

### Autres options

- **B.** A, plus le push des seules branches `hermes/*` et l'ouverture de PR en brouillon, par une clé de déploiement propre à chaque dépôt. La fusion reste manuelle.
- **C.** A, plus un seul geste de votre part sur le plan de chaque projet, avant la première exécution.
- **D.** Écriture autonome seulement sur les dépôts jetables. Sur un dépôt réel, la carte passe en revue avant le commit d'intégration.
- **E (déconseillée).** Fusion automatique quand la CI est verte.

### Garde-fous techniques

**Sur le PC**

- **`%LOCALAPPDATA%\ACP\poste.toml`.** Il fait autorité et n'est jamais fourni par Railway. Il fixe :
  - les dépôts (alias vers chemin) ;
  - les exécutants, modèles, efforts et paliers permis ;
  - la commande de vérification de chaque dépôt ;
  - la durée maximale par carte, la concurrence et le nombre de cartes par jour ;
  - le réseau ;
  - les versions de CLI testées.
- **Compte Windows standard dédié `acp-poste`.** Tâche planifiée `TASK_LOGON_PASSWORD`. Aucun port en écoute : uniquement du HTTPS sortant.
- **Bac à sable Codex.**
  - **Le mode *elevated* est imposé par `-c windows.sandbox="elevated"`** à chaque `exec`, `exec resume`, `sandbox` et sonde (`config/src/types.rs:163-175`, V).
  - L'écriture n'est autorisée que si `windowsSandbox/readiness` vaut `Ready` ET si `config/read`, lancé avec les mêmes surcharges, rend le mode `elevated`.
  - Pourquoi ne jamais déduire *elevated* de la seule readiness : la réponse n'a qu'un champ `status` (`app-server-protocol/src/protocol/v2/windows_sandbox.rs:61-66`, V), et le mode *unelevated* (`RestrictedToken`) répond toujours `Ready` (`app-server/src/request_processors/windows_sandbox_processor.rs:319-337` ; `core/src/windows_sandbox.rs:62-75`, V).
  - Réglages imposés :
    - `approval never` ;
    - `workspace-write` avec le réseau coupé ;
    - `web_search disabled` ;
    - apps, plugins, `browser_use*`, `computer_use`, hooks et `multi_agent` coupés ;
    - keyring ;
    - `service_tier="default"`.
- **Claude.**
  - `--restricted` : sans outil de commande, les outils de fichiers restent confinés aux dossiers de travail, et seuls les réglages gérés et `--settings` sont chargés (`cli.md:122`, V).
  - Le reste : `--tools Read,Glob,Grep,Edit,Write`, `acceptEdits`, `--permission-prompts none`, `availableModels` et comparaison avec `system/init`.
  - C'est un contrôle appliqué dans le processus, pas une frontière du système.
- **Protection des fichiers de pilotage : assurée par le POSTE, pas par Claude Code.**
  - La liste des chemins protégés de Claude Code ne contient ni `CLAUDE.md`, ni `AGENTS.md`, ni `.github`, ni `.codex/`, ni `.agents/`. En `acceptEdits`, `Write` les modifie sans invite. Seul `.claude/` est protégé, donc refusé sous `--permission-prompts none` (code.claude.com/docs/en/permission-modes, section « Protected paths », V).
  - La détection des chemins dans le diff par le poste est donc la protection réelle. Elle doit être robuste : casse ignorée, séparateurs `\` et `/`, occurrences imbriquées, noms courts 8.3, jonctions et liens symboliques résolus, renommages et suppressions suivis.
- **Aucun code du dépôt n'est exécuté hors du bac à sable Codex.** La vérification tourne sous `codex sandbox windows` (S).
- **Git.**
  - Un worktree et une branche `hermes/<carte>` par carte.
  - `.git` est en lecture seule pour Codex.
  - Le poste committe lui-même, avec les crochets coupés.
  - Aucun push sans accord.
- **Balayage des secrets, en échec fermé**, sur la réponse finale, les notes et le diff.
  - Il cherche d'abord les **valeurs exactes** : jeton machine, `CLAUDE_CODE_OAUTH_TOKEN`, jetons Codex s'ils sont lisibles par le poste depuis le magasin effectif (gardés en mémoire seulement, S).
  - Ensuite les motifs : `sk-`, `sk-ant-`, `ghp_`, `github_pat_`, `AKIA`, en-têtes PEM, JWT.
  - En cas de détection, `block_task`, et rien n'est envoyé.
  - Un jeton de rafraîchissement ChatGPT n'a pas de motif reconnaissable : d'où la liste exacte, ET la preuve que le bac à sable ne peut pas lire le magasin.
- **Magasins d'identifiants réels.** Les chemins effectifs sont `CODEX_HOME` et `CLAUDE_CONFIG_DIR`, qui valent le `auth_directory` configuré (`apps/poste/src/acp_poste/executors.py:167-190` et `727-732` du dépôt, V). S'y ajoutent l'entrée keyring Codex du compte `acp-poste` et `%LOCALAPPDATA%\ACP`. **Ce sont eux que visent les tests d'exfiltration**, pas `~/.codex` ni `~/.claude`.
- **Environnement.** Il est calculé, jamais hérité : TEMP propre à la tentative, aucune variable `*_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` pour Claude seul.
- **Arrêt et veille.** Job Object `KILL_ON_JOB_CLOSE`, durée maximale par carte, `SetThreadExecutionState` pendant une carte.
- **Double contrôle** du quadruplet exécutant, modèle, effort, palier : par le greffon à la création, par le poste à la réclamation.
- **Garde de quota** : seuil de 90 %, puis `schedule_task`.
- **Plafonds par projet** : 3 tours de synthèse, 30 cartes, 2 corrections. Au-delà, la carte passe en triage pour vous.
- **Pause.**
  - Générale : l'arrêt d'urgence de Hermes (`hermes pause`, `gateway/kanban_watchers_common.py:100-110`, V), plus un drapeau du greffon qui suspend les réclamations.
  - Locale : `acp-poste pause`.
- **Jeton machine** de 256 bits : Railway n'en garde que le SHA-256, le PC le garde sous DPAPI. Révocation par 401.
- **Refus** de toute carte `poste-*` non émise par le greffon.

**Sur Railway**

- **Toolsets coupés** : `terminal`, `file`, `code_execution`, `browser`, `cronjob`, `delegation`, `connections`.
- **Mémoire et skills écrits par l'agent** : mis en attente de votre validation.
- **Crochets shell** : refusés au démarrage (§7).

---

## 5. Continuité entre appareils

- **Tout l'état vit sur Railway** :
  - un SQLite par tableau ;
  - `state.db` pour les sessions ;
  - les tables du greffon : projets, demandes, questions, catalogue, quotas, présence, curseur de notifications.
- **Vues identiques** sur le téléphone (390×844), le navigateur du PC et le desktop Qt (P8) :
  - accueil ;
  - projets (détails par les routes natives `/api/plugins/kanban/tasks/:id`) ;
  - questions : questions du greffon, cartes en triage, `open_requests` des sessions vivantes ;
  - discussion (`/api/sessions`, `session.resume`, `session.events.since`) ;
  - poste ;
  - quotas.
- **Temps réel** : flux SSE du greffon avec keepalive toutes les 15 s et reprise par `Last-Event-ID`. Sur le desktop : `QWebSocket` et `SseParser`.
- **Durable** : les cartes, commentaires et résumés, **les questions (table du greffon et carte `scheduled`)**, l'historique des sessions.
- **Non durable** : `clarify` (1 h) et les approbations (5 min), gardés en mémoire du processus et perdus à un redéploiement. D'où la règle : toute question qui doit attendre votre réponse passe par le greffon.

### Notifications : un émetteur du greffon, pas les abonnements natifs

Les abonnements natifs ne filtrent pas par type d'événement :
- le notificateur livre tous les types de `TERMINAL_KINDS` ;
- en notify+wake, il fait prendre un tour à Hermes à chaque `completed` (`gateway/kanban_watchers_notifier.py:36` et `39` ; table sans filtre, `kanban_db.py:1049-1064`, V) ;
- ils se recopient sur les cartes enfants (`kanban_db.py:1456-1491`, V).

L'émetteur retenu :
- **Où il tourne.** Dans le processus de la **passerelle**, sur le crochet `on_kanban_dispatch_tick` (`hermes_cli/plugins.py:177-181` ; `kanban_db_dispatch.py:1318-1320`, V). Le greffon est un backend groupé, chargé dans tout processus Hermes (`plugins_discovery.py:264-266`, V ; enregistrement du crochet dans la passerelle, S).
- **Ce qu'il fait.** Il lit les événements des tableaux et les tables du greffon depuis un curseur persistant, puis n'envoie que la liste retenue :
  - question qui vous est adressée ;
  - blocage ou triage ;
  - abandon ;
  - projet terminé ;
  - poste hors ligne (une seule fois par passage hors ligne).
- **Comment il envoie.** Par un appel HTTP direct à l'API Bot Telegram ou à ntfy. Le secret est en variable Railway, et l'envoi passe par un fil d'arrière-plan pour ne pas ralentir le répartiteur (S).
- **Pas de réveil de Hermes par défaut.**
- **Pourquoi pas `inject_message`.** Le tableau de bord et la passerelle sont deux processus distincts (`hermes/image/Dockerfile:18-31` et `71-75` du dépôt, V). `ctx.inject_message` échoue hors de la passerelle (« no live gateway ») et exige `allow_gateway_injection` (`hermes_cli/plugins.py:603-634` et `1245-1257`, V). Il est donc écarté.

Telegram permet aussi de discuter avec Hermes ; ses sessions apparaissent dans la liste des sessions sur le PC.

---

## 6. PC éteint

**Ce qui continue sur Railway :**
- le répartiteur, les cartes Hermes et l'émetteur de notifications ;
- une question qui vous est adressée vous parvient toujours.

**Ce qui attend :**
- les cartes `poste-*` restent `ready` et sont rangées en `skipped_nonspawnable`, sans échec (`kanban_db_dispatch.py:2011-2017`, V) ;
- **la planification d'un projet sur dépôt attend l'exploration par le poste** : l'interface le dit, et rien n'est simulé ;
- la synthèse attend ses parents.

**Présence du poste :**
- le tableau de bord la **persiste en base** à chaque long-poll ou battement ;
- la passerelle l'**évalue** sur `on_kanban_dispatch_tick` ;
- elle notifie une seule fois (« Poste hors ligne depuis HH:MM, N cartes en attente ») et l'expose par l'outil `poste_etat` ;
- `stranded_in_ready` n'émet aucun événement de carte (V).

**PC éteint pendant une carte : deux cas.**

- **Retour avant l'expiration de la réclamation.** Le poste appelle la route `reprendre`. La carte étant encore `running` avec son claimer, le greffon appelle `reclaim_task`, qui remet le compteur d'échecs à zéro (`kanban_db.py:2558-2591`, V). Le poste réclame ensuite de nouveau et reprend le fil local.
- **Retour après l'expiration.** `release_stale_claims` a déjà remis la carte à `ready` en **comptant un échec** (`kanban_db.py:2409-2512`, V), et `reclaim_task` renverrait `False` (`kanban_db.py:2567-2570`, V). Le poste réclame alors de nouveau et reprend son fil local. Le compteur ne revient à zéro qu'au succès suivant (`complete_task`, `kanban_db.py:2820`, V).
  - Avec `failure_limit: 3`, il faut trois coupures consécutives sur la même carte pour qu'elle soit abandonnée.
  - Une carte abandonnée apparaît dans Questions avec « Relancer », qui appelle `unblock_task` : cette fonction publique remet `consecutive_failures` à 0 (`kanban_db.py:3665-3672`, V).
  - Relance automatique par le greffon : seulement si toutes les tentatives ont échoué par expiration du claimer `acp-poste` ET si le poste prouve la reprise du fil. Au plus 3 fois par carte, et seulement sur votre décision.

**Réduire les expirations :**
- TTL explicite de **45 min**, passé à `claim_task` et à `heartbeat_claim`. Un redémarrage de mise à jour de Windows ne compte donc pas.
- Remise propre de la carte à l'arrêt de Windows, par `CTRL_SHUTDOWN_EVENT` ou par une fenêtre cachée qui reçoit `WM_QUERYENDSESSION` (S, à prouver en P6).

**Redéploiement de Railway pendant une carte.** Le claimer stable `acp-poste:<id>` garde les battements valides : sans lui, le verrou valait « hôte:PID » du tableau de bord (`kanban_db.py:1086-1093`, V).

**Mise en route et veille :**
- tâche planifiée au démarrage, « exécuter même si l'utilisateur n'est pas connecté », `TASK_LOGON_PASSWORD` ; S4U est exclu ;
- avec le démarrage rapide de Windows, le déclencheur pourrait ne pas se redéclencher (S) ;
- ce PC ne se met jamais en veille sur secteur, et `SetThreadExecutionState` protège une carte en cours ;
- réveil à distance impossible. En option : une fenêtre de réveil nocturne par `WakeToRun`. Codex Cloud comme relais reste hors v1.

---

## 7. Changements de la managed scope (`hermes/gere/config.yaml`)

### À garder

- **`kanban.auto_decompose: false`.** Le décomposeur ne connaît que les profils existants.
- **`kanban.dispatch_profiles: [default]`.**
- **`approvals`** : `mode manual`, et `cron_mode`, `single_query_mode` et `unattended_mode` à `deny`.
- **`plugins.enabled: []`, `plugins.allow_deprecated_imports: false`, `auth.adopt_external_logins: false`.**

### À ajouter

- **`agent.disabled_toolsets: [browser, terminal, file, code_execution, cronjob, delegation, connections]`.**
  - Pourquoi `cronjob` : le worker `chat -q` exporte `HERMES_INTERACTIVE=1`, donc `check_cronjob_requirements` est vrai (`tools/cronjob_tools.py:1059-1071` ; `cli.py:1719`, V). `single_query_mode` ne s'applique qu'aux approbations d'exécution (`tools/approval_context.py:281-298`, V). Et `cron.allow_agent_scheduling` ne retire `cronjob` qu'à l'agent lancé **par** cron (`cron/scheduler.py:446-460`, V).
  - Le risque : un Hermes victime d'une injection planterait sinon une tâche planifiée durable qui relance des projets en boucle.
  - `delegation` : des sous-agents invisibles dans le kanban, et de la mémoire consommée.
  - `connections` : des connecteurs et des autorisations de comptes.
  - Portée : la coupure vaut aussi pour la discussion, puisque le tableau de bord résout ses outils sur la plateforme `cli` (`tui_gateway/server.py:1939`, V). Les tâches planifiées se créent donc par vous, depuis la page Cron.
- **`memory.write_approval: true` et `skills.write_approval: true`** (`config_defaults.py:1292-1295` et `1455-1459`, V).
  - La mémoire est injectée dans le prompt de toutes les sessions. `skill_manage` crée des skills que d'autres cartes chargeront. Ce sont deux surfaces de ré-injection durable.
  - Le comportement d'une écriture mise en attente dans un worker `-q` est à prouver en P4 (S). À défaut, couper `memory` et restreindre `skills` : c'est une décision de votre part.
- **Crochets shell.** `_worker_argv` ajoute toujours `--accept-hooks` (`kanban_db_dispatch.py:2687-2688`, V), et les crochets s'exécutent hors des toolsets (`agent/shell_hooks.py:141` et `597-599`, V).
  - Épingler `hooks_auto_accept: false`.
  - Faire refuser le démarrage par `00-acp-gardes` si `hooks` n'est pas vide dans `/opt/data/config.yaml` ou dans la configuration d'un profil, ou si `shell-hooks-allowlist.json` existe. La managed scope fusionne feuille par feuille (`hermes_cli/managed_scope.py:125-147`, V) : épingler `hooks: {}` ne viderait probablement rien (S).
- **`agent.service_tier: ""`** : le mode rapide de Hermes reste coupé (`config_defaults.py:134-136`, V).
- **`kanban.max_in_progress: 4`.** `count_running_tasks` compte aussi les réclamations distantes (`kanban_db_dispatch.py:1846-1860` et `2160-2195`, V). Valeur à mesurer dans les 2 Go.
- **`kanban.max_in_progress_per_profile: 2`.**
- **`kanban.review_dispatch: false`** (`config_defaults.py:1866-1867`, V).
- **`kanban.failure_limit: 3`** (défaut 2, `config_defaults.py:1872`, V).
- **`skills.disabled: [claude-code, codex, opencode]`**, et `skills.external_dirs` pour les skills françaises `acp-exploration`, `acp-orchestration`, `acp-routage`, `acp-synthese` et `acp-questions`.
- **Notifications.** Aucune plateforme native n'est nécessaire pour l'émetteur. Les secrets Telegram (jeton du bot, identifiant de discussion) ou ntfy (`NTFY_TOPIC` privé, `NTFY_TOKEN`) sont en variables Railway, lues par le greffon. Si Telegram sert aussi de discussion avec Hermes : liste blanche du seul propriétaire et `allow_all_users: false` (clés exactes à relever).

### À ne pas changer

- **`dashboard.ws_orphan_reap_grace_s`** (20 s).
- **Aucun toolset `kanban` natif pour la discussion.** Les outils du greffon suffisent. Les workers gardent les outils kanban de cycle de vie (`tools/kanban_tools.py:83-100`, V).

### Hors managed scope

Désactiver la mise en veille propre à Railway pour le service.

---

## 8. Phases

### P4 : projets autonomes sur Hermes (Railway, sans le PC)

**Prérequis.** Les preuves P2 couvrent les workers `chat -q` et la veille Railway désactivée.

**Livrable.**
- Greffon `acp-poste` :
  - un tableau par projet ;
  - tables projets, demandes, questions, présence et curseur ;
  - outils `projet_lancer` (exploration puis planification), `projet_planifier` (graphe déterministe, dont la relecture et la synthèse), `projet_etat`, `poste_etat`, `poste_catalogue`, `question_repondre`, `question_escalader`, `routage_surcharger` ;
  - routes REST `/v1/projets` et `/v1/questions` ;
  - plafonds, pause, et refus des cartes `poste-*` non émises par lui ;
  - émetteur de notifications dans la passerelle.
- `kanban_adapter` étendu, chaque fonction importée depuis son module de définition sous `hermes plugins compat` : `create_board`, `link_tasks`, `add_comment`, `unblock_task`, `schedule_task`, `reclaim_task`, `specify_triage_task`. `add_notify_sub` n'est pas nécessaire : aucun abonnement natif.
- Skills françaises.
- Managed scope du §7.
- Page mobile « Projets ».

**Preuve.** Dans l'image épinglée, avec le modèle factice `hermes/tests/outils/modele_factice.py` et un **catalogue de test daté, étiqueté « relevé factice »** :
- `projet_lancer` crée l'exploration et la planification. Un poste simulé termine l'exploration ; la planification est lancée en deux passages au plus et reçoit le résumé.
- Graphe complet créé ; synthèse lancée seulement quand ses parents sont terminés ; plafond de tours respecté.
- **Liste des outils du worker `default` imprimée :** sans `terminal`, fichiers, `execute_code`, `browser_*`, `cronjob_manage`, `delegate_task` ni `manage_connections`.
- Aucun crochet enregistré. Le démarrage est refusé si un `hooks` non vide est déposé.
- Écriture en mémoire par un worker : mise en attente, pas appliquée.
- Cartes `poste-*` : `skipped_nonspawnable`. Une carte `poste-*` créée hors du greffon est refusée.
- **Deux réclamations distantes simulées sur un AUTRE projet** n'empêchent pas le lancement d'une planification ou d'une synthèse d'un projet tiers, avec `max_in_progress` à 4.
- Effort hors énumération : carte créée sans `reasoning_effort`.
- Pause : aucun worker lancé.
- Routes sans session : 401.
- Émetteur : un seul message par événement retenu ; aucun message pour `completed` des cartes intermédiaires ; une seule notification « hors ligne ».
- Sur Railway : projet lancé depuis le téléphone, téléphone fermé, notification reçue, projet relu depuis un second appareil.

### P5 : poste connecté (présence, catalogue, quotas ; sans exécution)

**Livrable.**
- `apps/poste` :
  - client HTTPS et enrôlement ;
  - jeton sous DPAPI ;
  - long-poll ;
  - compte `acp-poste` et tâche planifiée ;
  - mutex, `poste.toml`, journal masqué, diagnostic.
- Connexions faites par vous : `codex login --device-auth` (keyring) et `claude setup-token`.
- Sondes Codex, lancées avec `-c windows.sandbox="elevated"` : `initialize`, `model/list` (avec `serviceTiers` et `defaultServiceTier`), `account/rateLimits/read`, `windowsSandbox/readiness`, `config/read`.
- Claude : version, alias documentés et ligne d'état. La résolution sera observée à la première exécution, faute de voie autorisée sans SDK.
- Greffon : jeton machine, `/machine/v1/inventaire`, présence persistée, pages Routage et Quotas.

**Preuve.**
- Relevé réel de `model/list` de votre compte, archivé sans identifiant : il tranche « sol » et « artra » et montre les paliers par défaut.
- Mode *elevated* lu par `config/read`.
- Redémarrage de Windows sans ouvrir de session : le poste est en ligne.
- Aucun port en écoute ; jeton révoqué : 401.
- « Inconnu », « Périmé » et « Liste de secours » testés ; identifiant ou effort non listé refusé en français.
- PC éteint : une seule notification.

### P6 : exécution autonome sur un dépôt jetable

**Livrable.**
- Réclamation avec claimer stable et TTL de 45 min.
- Battements ; routes `terminer`, `question`, `bloquer`, `reprendre`.
- File de sortie persistante ; worktree, commit, diff.
- Détection robuste des fichiers de pilotage ; balayage avec valeurs exactes.
- Codex elevated imposé, avec `service_tier` à `default`.
- Claude `--restricted` avec comparaison à `system/init`.
- Boucle de vérification, relecture croisée et correction dans le bon ordre.
- Garde de quota.

**Preuve.**
- Projet complet lancé depuis le téléphone : exploration, puis un **plan qui cite des fichiers réels** du dépôt jetable, implémentation, relecture, synthèse. Branche locale `hermes/*` créée ; `git branch -r` inchangé.
- Modèle servi égal au modèle demandé pour chaque carte ; **palier servi différent de `priority`**.
- **Exfiltration visant les vrais chemins** (`CODEX_HOME` et `CLAUDE_CONFIG_DIR` effectifs, keyring d'`acp-poste`, `%LOCALAPPDATA%\ACP`) : refusée par le bac à sable ou bloquée par le balayage, et rien de sensible sur Railway.
- **Compte configuré en *unelevated*** : readiness `Ready`, écriture refusée en français.
- **Écriture Claude dans `.github/workflows/x.yml`**, et variantes de casse et d'imbrication : la carte passe en revue au lieu de done.
- **Deux questions successives sur la même carte** : aucune n'envoie la carte en triage ; les deux réponses reprennent le fil.
- **Coupure de plus de 15 min, puis de plus de 45 min, pendant une carte** : reprise, et compteur conforme au §6.
- **Redéploiement de Railway pendant une carte** : les battements restent valides.
- Verdict « corrections » : la synthèse n'est pas lancée entre la fin de la relecture et la correction.
- Quota simulé : attente puis reprise. `acp-poste pause` : l'arbre de processus est tué et la carte rendue.

### P7 : questions, notifications et continuité ; passage aux dépôts réels

**Livrable.**
- File Questions (questions du greffon, triage, `open_requests`).
- Carte « répondre » ; réglage par projet.
- Émetteur complet ; bilan quotidien en option, créé par vous en cron.
- Discussion mobile réduite.
- Accueil identique partout.
- Dépôts réels ajoutés un par un.

**Preuve.**
- Parcours complet : lancé en 390×844, téléphone fermé, question notifiée, réponse depuis le PC en 1440×900, fil repris, projet terminé. Captures et relevé des événements.
- Transcriptions illustratives, non déterministes : Hermes répond à une question couverte par les décisions du projet et escalade une question non couverte.
- Redéploiement pendant une question : question intacte.
- Premier dépôt réel : aucune action « accord requis » sans votre geste (journal).

### P8 : desktop Qt et MCP côté poste

**Livrable.**
- Desktop :
  - `NativeAuthFlow` (RFC 8252) avec le fournisseur `self_hosted` ;
  - `JsonRpcChannel`, `EventStreamService` ;
  - pages Accueil, Projets, Questions, Discussion, Poste, Quotas, Routage, Diagnostics et Sauvegarde ;
  - suppression d'`AuthManager` et du cookie.
- MCP côté poste : `context7`, puis Playwright avec `browser_run_code_unsafe` interdit, sous `--strict-mcp-config`. Compatibilité avec `--restricted` à établir.

**Preuve.**
- Tests Qt : PKCE, `state`, redirection limitée à `127.0.0.1`, rotation du jeton de rafraîchissement, `-32601` pour une requête serveur non gérée.
- Réponse à une question depuis le desktop.
- Registre `QSettings` sans jeton.
- CI verte sur windows-2022 ; connexion réelle à Railway.
- Installeur non signé, dit explicitement.
- Résultat de la sonde MCP.

---

## 9. Retiré de l'ancien plan

- P5 « Poste en lecture » comme verrou, et « lectures validées au départ ».
- Toute la P7 « Écritures validées et signées » : passkey, WebAuthn, signature par tentative, nonces, domaine imposé, « Valider et signer ».
- Les cartes d'écriture en triage en attente de signature.
- La garantie « Railway ne décide d'aucun effet sur le PC sans geste ». Elle est remplacée par une formulation honnête : écritures bornées par la politique locale.
- Le tableau unique `poste` et l'assigné `poste-windows`.
- `request_review` à chaque écriture.
- L'outil `poste_suivre`, une attente bloquante de 240 s.
- `--ephemeral` et `--no-session-persistence` pour les cartes qui peuvent poser une question.
- Claude avec un Bash limité.
- Les plafonds fatals de 2 Mio et de 3 600 s.
- Le desktop qui ouvre le navigateur pour WebAuthn, et la page `/travaux`.
- Le fournisseur `nous` dans `NativeAuthFlow`.
- L'ancienne P4 « Discussion mobile » comme étape autonome.
- **Ajouts de cette révision :**
  - la carte racine d'orchestration qui planifiait sans voir le dépôt ;
  - `block_task(needs_input)` pour les questions ;
  - les abonnements natifs et le mode notify+wake ;
  - `ctx.inject_message` pour notifier ;
  - `claim_task` et `heartbeat_claim` sans claimer ;
  - « rendre remet toujours le compteur à zéro » ;
  - `/api/model/options` présenté comme la liste lue du compte ;
  - la lecture du catalogue Claude par le SDK Python présentée comme « voie documentée » ;
  - la déduction du mode *elevated* à partir de la readiness ;
  - le test d'exfiltration sur `~/.codex` et `~/.claude` ;
  - « sol existe bien » et « artra très probablement Astra ».

---

## 10. Risques

- **Frontière de confiance sans signature.** Un Railway compromis, ou un Hermes victime d'une injection, peut faire écrire le poste. Ces écritures restent bornées par `poste.toml`, les plafonds, l'absence de push, le compte dédié et le bac à sable. Les surfaces de **persistance** côté Railway sont fermées : `cronjob` coupé, mémoire et skills en écriture validée, crochets refusés. Cette fermeture n'est prouvée qu'en P4.
- **Claude n'a pas de bac à sable système sous Windows.** La protection des fichiers de pilotage repose sur le **poste** : les chemins protégés de Claude Code ne les couvrent pas. Un fichier de workflow empoisonné et committé localement deviendrait un vecteur d'exécution après une fusion, si la détection échouait.
- **Bac à sable Codex.**
  - En « Best effort » sous Windows 10 19045.
  - L'installation *elevated* demande l'UAC : `prepare_elevated_sandbox` la lance à la première commande si elle n'est pas faite (`core/src/windows_sandbox.rs:132-153`, V).
  - L'usage depuis `acp-poste` et la lecture refusée des magasins d'identifiants sont à prouver.
- **Conditions d'utilisation.**
  - Anthropic : un usage « ordinary, individual » ; connecter soi-même le binaire Claude Code non modifié est admis (`cc-legal-and-compliance.md:43` et `52`). L'Agent SDK avec une connexion d'abonnement n'est pas autorisé d'après la recherche du projet. La même page mentionne l'Agent SDK dans la phrase sur les limites Pro et Max : c'est ambigu, d'où la décision laissée au propriétaire.
  - OpenAI : tolérance non contractuelle ; enveloppe ChatGPT partagée entre le cerveau et le Codex du poste.
- **Catalogue Claude non lisible sans SDK.** Le routage Claude repose sur des alias et une résolution observée. Un alias peut changer de cible à une mise à jour ; c'est détecté par `system/init`, mais cela bloque la carte.
- **Palier Fast par défaut sur `gpt-6-sol` et `gpt-6-luna`.** Que Codex applique ce palier quand aucun n'est configuré n'est pas traçable dans le clone partiel (S). Imposer `service_tier="default"` ne coûte rien et se vérifie par les événements.
- **Plafond Hermes.** Les réclamations distantes consomment `max_in_progress`. Le garde de pression mémoire bloque tout lancement au niveau critique.
- **Orchestration par un modèle.** Plans de qualité variable. Parades : exploration préalable, graphe déterministe, plafonds.
- **Instructions kanban injectées.** Elles demandent `hermes profile list` (`agent/prompt_builder.py:326-340`) et contredisent nos voies non-profil. Parades : `projet_planifier` et la skill.
- **Surfaces internes instables** : kanban interne de Hermes, app-server Codex « experimental ». Parades : épinglage, `hermes plugins compat`, tests de contrat, `codex exec` pour l'exécution.
- **Coupures.** Au-delà du TTL, chaque coupure compte comme un échec. Parades : TTL de 45 min, remise à l'arrêt (S), `failure_limit: 3`, « Relancer ».
- **Triage.** Deux refus de capacité du même type envoient la carte en triage. Elle est visible dans Questions, et « Reprendre » la relance. Le compteur de récurrence persiste jusqu'au prochain succès.
- **Claude Code.** `--bare` deviendra le défaut de `-p`, et le jeton `setup-token` dure un an. Parades : binaire épinglé et vérifié, alerte avant l'expiration.
- **Catalogue vide ou compte déconnecté** : la voie concernée est bloquée par construction, et c'est visible.
- **Mémoire Railway** de 2 Go : à mesurer.
- **Secrets des notifications** en variables Railway. Un topic ntfy sans jeton serait lisible par des tiers.
- **Réseau coupé pour les exécutants** : les dépendances doivent être préparées par le poste.
- **Démarrage rapide de Windows** ; `git worktree` sous le bac à sable non éprouvé. Repli : un clone par carte.
- **Corrections : aucune rejetée.** Les 18 ont été recoupées dans les sources. Quatre nuances :
  - `session_search`, évalué, reste actif : il est en lecture seule ;
  - `add_notify_sub` devient inutile, puisque les abonnements natifs sont abandonnés ;
  - l'application automatique du palier par défaut reste supposée ;
  - la parade du mode *elevated* est renforcée : imposé par `-c windows.sandbox="elevated"`, en plus de sa lecture par `config/read`.

---

## 11. Décisions à vous demander

1. **Politique d'autonomie** : A (recommandée), B, C ou D.
2. **Qui répond aux questions** : Hermes d'abord (recommandé), ou toujours vous. Réglable par projet.
3. **Canal de notification** : Telegram, message privé réservé au propriétaire (recommandé) ; ntfy avec un topic privé et un jeton ; ou aucun.
4. **« sol » et « artra »** : lesquels, après le relevé P5.
   - Table de routage à valider.
   - Efforts `max`, `ultra` et `ultracode` : autorisés ou non.
   - **Paliers `priority`, `ultrafast` et Fast : interdits (recommandé) ou autorisés par classe.**
   - Ordre de repli.
5. **Catalogue Claude** : alias et résolution observée (recommandé), ou le SDK, avec le risque sur les conditions d'utilisation accepté par écrit.
6. **Mémoire et skills de Hermes** : écriture validée par vous (recommandé), ou mémoire coupée.
7. **Budgets** :
   - concurrence ;
   - cartes par jour ;
   - durée maximale par carte ;
   - seuil de quota ;
   - plafonds par projet ;
   - TTL de réclamation (45 min proposé) ;
   - relance automatique après coupure, oui ou non.
8. **Compte Windows** : `acp-poste` dédié (recommandé) ; accord pour l'installation *elevated* (UAC).
9. **Réseau des exécutants** : coupé (recommandé), ou autorisé par dépôt.
10. **Dépôts** : lequel est jetable pour P6 ; quels dépôts réels ensuite.
11. **Relecture croisée** : systématique (recommandé), ou au-delà d'une taille de diff.
12. **PC éteint** : réveil nocturne par `WakeToRun`, oui ou non ; Codex Cloud évalué plus tard, oui ou non.
13. **Orchestrateur** : profil `default` (v1), ou profil dédié restreint.


---

## Annexe (hors plan) : état du dépôt au 25 septembre 2026

Constat factuel, établi sur `hermes/gere/config.yaml` et `hermes/image/acp_demarrage.py` de P2 ; il
ne modifie pas le plan ci-dessus.

- **Déjà posé par P2** (managed scope, [image.md](image.md) § 5) : `agent.disabled_toolsets` avec
  `browser`, `terminal`, `file`, `code_execution`, `cronjob`, `delegation`, `connections` (plus
  `computer_use` et `setup`) ; `memory.write_approval: true` et `skills.write_approval: true` ;
  `hooks_auto_accept: false` ; `agent.service_tier: ""` ; `kanban.auto_decompose: false`,
  `kanban.dispatch_profiles: [default]`, `approvals` (`manual`, `deny`), `plugins.enabled: []`,
  `plugins.allow_deprecated_imports: false`, `auth.adopt_external_logins: false`. `kanban_create` et
  `kanban_attach_url` sont refusés à l'agent par la garde d'exécution d'`acp-poste`.
- **Pas encore posé** (phases P4 et suivantes) : refus de démarrer sur une clé `hooks` non vide de
  `config.yaml` ou sur `shell-hooks-allowlist.json` (P2 les inventorie seulement par
  `diagnostiquer`) ; `kanban.max_in_progress`, `kanban.max_in_progress_per_profile`,
  `kanban.review_dispatch`, `kanban.failure_limit` ; `skills.disabled` et `skills.external_dirs` ;
  les outils, routes, tables, skills et l'émetteur de notifications du greffon.
- **Mise en veille Railway coupée** (« Hors managed scope » du § 7) : déclarée dans
  `.railway/railway.ts` (`sleepApplication: false`), prise en compte à constater sur Railway
  ([railway.md](railway.md) § 3).
