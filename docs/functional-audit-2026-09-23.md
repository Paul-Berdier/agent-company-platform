# Audit fonctionnel : desktop, Hermes et agents

Audit du 23 septembre 2026 sur `main`, commit `ce42ae2`. **Le socle est testé,
mais le parcours complet Hermes → Claude/Codex → livrable n'est pas prêt.**
Le propriétaire confirme qu'aucune instance Hermes ni aucun déploiement ACP
n'est installé. Cet audit porte sur le code et des essais isolés ; aucun
fournisseur payant, compte ou coffre de notes personnel n'a été utilisé.
Les défauts recensés ne sont pas corrigés par cette mise à jour documentaire.

## Capacités réellement disponibles

| Parcours | État démontré | Ce qui manque |
|---|---|---|
| Desktop → API | Connexion, projets, mission et export vérifié : parcours Qt/API locale déjà réussi | Recette visuelle complète, Windows propre, serveur installé |
| Conversations → Hermes | Admission idempotente et consultation d'un Run codées, tests HTTP simulés | Instance réelle ; traitement des approbations Hermes |
| Plusieurs tentatives concurrentes | Un worker à capacité 2 ou deux workers à capacité 1 : pic de deux jobs reproduit | Deux CLIs authentifiés exécutés réellement |
| Claude et Codex dans une même mission | Une tentative choisit exactement un exécuteur | Sous-tâches durables, dépendances, restitution et synthèse |
| Écriture de code | Codex peut recevoir une ressource en écriture ; verrou entre écritures sur une même racine | Formulaire desktop compatible ; worktrees par tentative ; isolation OS du runner |
| Claude Code | Outils de lecture autorisés | Restitution du contenu produit ; écriture non livrée par cet adaptateur |
| MCP et compétences ACP | Registre, versions, liaisons, diagnostics et export | Transmission effective aux exécuteurs pendant une mission |
| Obsidian | Compétence disponible dans Hermes amont | Installation, coffre dédié accessible au service et intégration ACP |

Les CI et les suites natives vertes établissent les scénarios testés, pas les
raccordements manquants. La définition de fin du desktop V1 inclut l'usage réel
d'Hermes, de MCP et des compétences : la présence des écrans ne la satisfait pas.

## Défauts confirmés

P1 : empêche un parcours principal ou compromet sa restitution. P2 : fonction
partiellement inaccessible ou affichage incomplet. Les reproductions simulées
ne constituent pas un essai avec un fournisseur réel.

### AF-01 — P1 : missions Claude/Codex impossibles depuis le formulaire Qt

[`creationBody`](../apps/desktop/src/viewmodels/MissionsViewModel.cpp#L445)
envoie toujours `resources=[]`, avec `bounded` par défaut. Le
[`worker`](../apps/worker/src/acp_worker/executors.py#L462) exige `supervised`
et exactement une ressource `project_workspace` correspondant au projet.
Les quatre corps bornée/supervisée × Codex/Claude passent `MissionCreate`,
puis échouent avant exécution. Choisir « Supervisée » ne suffit donc pas.

Prévoir un choix explicite d'exécuteur et d'accès au workspace selon les capacités
autorisées ; refuser les combinaisons impossibles avant admission. Le chemin
local reste configuré sur le worker, sans accès direct du desktop à ses fichiers.

### AF-02 — P1 : durée supérieure au délai local refusée avant lancement

[`_run_executor_unlocked`](../apps/worker/src/acp_worker/executors.py#L1017) et
[`run_executor` avec verrou](../apps/worker/src/acp_worker/executors.py#L1190)
rejettent la durée restante supérieure au plafond local avant le `min`.
Reproduction synthétique : 2 secondes restantes, plafond local 1 seconde →
`ExecutorConfigurationError`, zéro lancement, pour Claude et Codex.
Valider une durée positive et finie, puis borner aux échéances effectives,
en déduisant le temps passé à attendre le verrou.

### AF-03 — P1 : délais incompatibles entre worker et Hermes

[`gateway_plan` et `gateway_evaluate`](../apps/worker/src/acp_worker/main.py#L181)
imposent 15 secondes au transport ; Hermes attend jusqu'à 120 secondes par défaut.
Capture `MockTransport` : lecture, connexion, écriture et pool valent 15 secondes.
Une planification lente peut perdre son demandeur avant de finir. Recoupe
**N2-5**, déjà ouvert. Articuler bail, échéance et identifiant durable d'opération ;
augmenter seulement le timeout ne résout pas la reprise après perte de réponse.

### AF-04 — P1 : preuve perdue si le rapport budgétaire échoue

[`budgeted_effect`](../apps/worker/src/acp_worker/budget.py#L422) attend le
rapport d'usage avant de rendre le résultat. Reproduction : CLI simulé terminé
avec code 0, puis HTTP 503 sur le rapport. Le worker publie un échec et des
preuves vides, sans résultat ni évaluation. Recoupe **N2-3**, déjà ouvert.

Conserver durablement le résultat et reprendre seulement le rapprochement avec
la même clé. Ne pas rejouer l'effet externe pour réparer sa comptabilisation ;
une réservation incertaine doit rester visible.

### AF-05 — P1 : expiration Hermes sans arrêt ni reprise du même Run

[`_run`](../services/provider-gateway/src/acp_provider_gateway/providers/hermes/adapter.py#L579)
génère une nouvelle clé UUID par opération. L'expiration ne transmet pas d'arrêt.
Deux planifications identiques expirées, simulées : **deux admissions, deux clés,
zéro arrêt**. Un ancien Run pourrait continuer pendant le suivant.

Persister admission, clé et identifiant de Run par opération ; reprendre sa
consultation et rapprocher l'arrêt distant. Les conversations ont leur propre
clé durable : ce défaut vise les opérations synchrones de l'orchestrateur.

### AF-06 — P2 : approbation Hermes affichée comme une réponse en cours

[`_apply_run`](../apps/api/src/acp_api/routers/conversations.py#L92) transforme
`waiting_for_approval` en `running`, erreur vide. Reproduction directe confirmée.
Aucun contrôle ACP ne répond à cette approbation Hermes ; les approbations
métier ACP sont distinctes. Exposer cet état et un circuit de décision/arrêt,
ou un refus clair si ce type d'exécution n'est pas pris en charge.

### AF-07 — P2 : conversations générales masquées après sélection de projet

[`Application`](../apps/desktop/src/app/Application.cpp#L95) propage le projet ;
le [`filtre`](../apps/desktop/src/viewmodels/ConversationsViewModel.cpp#L248)
exclut ensuite les conversations générales. Aucun contrôle QML ne revient au
contexte général. Parcours déduit du code : conversation générale → projet →
Conversations, historique général inaccessible dans ce contexte. Ajouter une
sélection visible « Général / Projet ».

### AF-08 — P2 : actualisation des commentaires incomplète

[`refresh`](../apps/desktop/src/viewmodels/MissionsViewModel.cpp#L188) recharge
liste et détail, pas les commentaires. `loadComments` intervient à la sélection
et après une mutation locale. Un commentaire ajouté ailleurs reste absent après
« Actualiser » ; changer de mission puis revenir le recharge. Constat de code,
sans recette visuelle. Actualiser les commentaires avec protection contre les
réponses obsolètes.

## Lacunes du parcours multi-agents

Certaines restrictions sont volontaires dans le Lot G ; les retirer sans
remplacer leurs contrôles n'est pas une correction.

- **Réponse métier absente :**
  [`ExecutorResult`](../apps/worker/src/acp_worker/executors.py#L422) garde tailles,
  empreintes, compteur et code de sortie, pas la réponse finale. Une sortie Claude
  synthétique réussie contenant du texte perd ce contenu. L'évaluation reçoit
  seulement une preuve technique dans
  [`main.py`](../apps/worker/src/acp_worker/main.py#L913). Prévoir réponse bornée et
  livrables consultables ; une empreinte seule ne permet pas d'évaluer le travail.
- **Plan réduit :** seuls les titres des étapes arrivent au prompt ; rôles,
  descriptions et dépendances ne deviennent pas des sous-tâches coordonnées.
- **Extensions non injectées :** instantané ACP enregistré, mais planification
  avec `context={}` et aucune compétence transmise au CLI. Codex reçoit
  `mcp_servers={}`, désactive notamment `multi_agent` et `skill_search` ; Claude
  reçoit un MCP vide et interdit `mcp__*`.
- **Isolation partielle :** écritures Codex sérialisées par racine, sans worktree
  automatique. Une lecture concurrente peut voir un checkout en modification.
  Le comptage d'agents ne prouve que celui du CLI principal.
- **Budget non estimable :** les effets Hermes et CLI ne fournissent pas de
  borne fiable coût/jetons. Une limite sur ces dimensions entraîne un refus
  avant appel dans `budget.py`, conformément à l'échec fermé. Le formulaire Qt
  exige `max_cost` : réparer sa ressource workspace ne suffit donc pas à rendre
  le parcours exécutable. Résoudre la mesure/réservation, sans enlever
  silencieusement le plafond demandé par l'utilisateur.

Architecture conseillée : mission parent et sous-tâches persistées, assignées
par capacités. Un worktree par agent d'écriture ; chaque résultat rejoint l'API
avec preuve et consommation ; une synthèse termine la mission. Les reprises
utilisent les mêmes identifiants. Tests et revue précèdent la fusion des branches.

Hermes fournit les compétences
[Codex](https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.7/skills/autonomous-ai-agents/codex/SKILL.md)
et [Claude Code](https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.7/skills/autonomous-ai-agents/claude-code/SKILL.md)
dans le tag retenu par ACP. Les modes programmatiques sont documentés par
[OpenAI](https://developers.openai.com/codex/noninteractive/) et
[Anthropic](https://code.claude.com/docs/en/headless). La coordination est possible,
mais reste à raccorder dans ACP. Versions, authentification et capacités doivent
être éprouvées ensemble ; les exemples amont n'autorisent pas à retirer les
protections du runner.

## Outils utiles pour Hermes

**Obsidian est la première intégration de connaissances conseillée.** Sa
[compétence Hermes au tag `v2026.9.7`](https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.7/skills/note-taking/obsidian/SKILL.md)
utilise directement les fichiers Markdown : recherche, lecture, création,
édition et liens. Un serveur MCP supplémentaire n'est pas nécessaire pour cet
usage. Prévoir un coffre dédié contenant décisions, spécifications et comptes
rendus ; missions, droits et exécutions restent dans la base ACP.

Commencer par la lecture d'un dossier dédié, puis des écritures explicites dans
un sous-dossier de comptes rendus avec versions et lien vers la mission. Un
Hermes distant ne peut pas lire spontanément le coffre Windows : prévoir un
runner local ou une copie/synchronisation maîtrisée. Aucun coffre n'a été lu ici.

Le [CLI officiel Obsidian](https://obsidian.md/help/cli) peut aussi piloter
l'application, mais nécessite qu'elle soit lancée, le CLI activé et un installateur
récent. Ces prérequis ne concernent pas la lecture directe des fichiers Markdown.

| Complément | Usage proposé | Condition avant activation |
|---|---|---|
| Git et [GitHub CLI](https://cli.github.com/manual/gh_pr) | Worktree par agent, différences, tests de PR et revue | Identité dédiée, périmètre dépôt, mutations explicites |
| [Playwright CLI/MCP](https://github.com/microsoft/playwright-mcp) | Parcours web et preuves navigateur | Profil isolé et origine autorisée ; ne teste pas le desktop Qt |
| Compétences Hermes ciblées | Procédures réutilisables, validation, comptes rendus | Versions et contenu réellement transmis au worker |

Hermes sait configurer des
[serveurs MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp),
mais l'export ACP exige une application manuelle côté service. Les conversations
ne transmettent pas la sélection d'outils par projet : une liaison ACP ne prouve
pas la restriction effective d'Hermes. Commencer avec un profil et un dossier
dédiés, puis prouver les portées.

## Vérifications et limites

- CI déjà verte sur `ce42ae2` :
  [plateforme](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35807599743)
  et [desktop](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35807599645).
  Construction, paquet et parcours Qt/API : [preuves desktop](desktop-validation-2026-09-23.md).
- Audit présent : **88 tests ciblés** Hermes/listing/gateway et contrats
  d'exécuteurs réussis, transports simulés ; **11 tests ciblés** worker réussis,
  dont verrous, annulation, capacités et concurrence sur SQLite jetable.
  Ces groupes peuvent partager des tests : pas de total global annoncé.
- **6 tests de contrats desktop/API** réussis en 3,06 s, SQLite jetable ; deux
  avertissements de dépréciation Starlette/httpx/AnyIO. Aucun essai avec CLI
  authentifié, MCP tiers, Hermes réel ou Railway.
- Reproductions locales : `.test-tmp/desktop-audit-executor-contract.json`,
  `.test-tmp/worker-audit-bd2a01a14c8d45e3996f4074aa15df40/proof.log`
  et `.test-tmp/audit-20260923/`. Ces fichiers temporaires ne sont pas livrés avec
  le dépôt ; scénarios et sites de code sont décrits ci-dessus.
- Incident d'audit : un essai indépendant `qml.exe` Qt 6.8.3 offscreen a quitté
  avec `0xC0000005`, provoquant la boîte vue par l'utilisateur. Aucun lancement
  ACP ni accès réseau image n'a été démontré par cet essai. Essais arrêtés ;
  le crash n'est pas attribué au produit sans reproduction dans son exécutable.
  Journaux locaux dans `.test-tmp/desktop-audit-qml/`.

Les **26 constats ouverts du Lot H** restent dans
[leur registre](lot-h-091-review-status.md). AF-03/AF-04 recoupent N2-5/N2-3 :
ne pas additionner les deux listes. Aucun tag ni validation V1 ne résulte de l'audit.

## Ordre de réalisation proposé

1. Rendre les missions desktop exécutables, restituer les résultats, borner les
   délais et préserver les preuves après panne budgétaire ; corriger les deux
   écarts de navigation/actualisation Qt.
2. Fiabiliser admission, reprise, arrêt et approbations Hermes. Transmettre les
   compétences et outils explicitement autorisés jusqu'à l'exécution.
3. Ajouter le plan durable multi-agents et les worktrees ; tester deux tâches
   Claude/Codex simultanées, leurs dépendances, annulations et reprises.
4. Installer une instance de test dédiée et exécuter un vrai parcours borné :
   mission → Hermes → agents → livrable → évaluation → desktop.
5. Brancher un coffre Obsidian de test, puis GitHub et le navigateur si utiles.
   Rejouer la recette après redémarrage et perte réseau avant publication.
