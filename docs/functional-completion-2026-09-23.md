# Complétion fonctionnelle : état et preuves du 23 septembre 2026

La refonte suivante de l’accueil, du chat et des projets est documentée dans
[la recette UI distincte](desktop-chat-projects-2026-09-23.md). Les preuves de
ce relevé restent celles de la base fonctionnelle indiquée ci-dessous.

Le chantier `codex/functional-completion` raccorde les missions natives aux
exécuteurs locaux, aux compétences et au proxy MCP, et ajoute une coordination
Claude/Codex explicite. **La V1 n'est pas terminée.** Les validations ci-dessous
prouvent des comportements locaux précis ; elles ne prouvent pas une mission
générative complète avec des comptes Claude, Codex et Hermes authentifiés.

Ce relevé complète l'[audit initial sur `ce42ae2`](functional-audit-2026-09-23.md),
conservé comme photographie des défauts avant correction. Les nouvelles sources
ont passé la validation locale complète. La fusion et la publication restent
des preuves distinctes ; les CI de la base précédente ne valident pas le présent lot.

## Intégration continue du code publié

Le commit fonctionnel est `47de619fe8a8f108d68f37c7b4276ba74baacfc4`.
La [CI desktop Windows](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35856502324)
est **verte** : compilation Release, **22 suites Qt sur 22** en 63,64 secondes,
parcours Qt/API jetable et création des paquets. Les artefacts de ce workflow
servent à l'inspection ; il ne signe ni ne publie de version.

La [CI plateforme](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35856502360)
est également **verte** sur ce même commit : suites Python SQLite et PostgreSQL 16,
parcours d'événements, automatisations et sauvegarde/restauration, puis tests,
typage et build Node 22. Playwright distant reste volontairement ignoré hors
d'un lancement explicite configuré. Le suivi de l'intégration et les contrôles de
sa révision finale sont accessibles dans la
[PR #11](https://github.com/Paul-Berdier/agent-company-platform/pull/11).

Les journaux de cette CI donnent **3 031 réussis, 64 ignorés** sous SQLite
(258,99 s) et **3 041 réussis, 54 ignorés** sous PostgreSQL (790,79 s). Le parcours
d'automatisation SQLite réussit 62 contrôles ; PostgreSQL réussit 77 contrôles
d'événements, 65 d'automatisation et 48 de sauvegarde/restauration. Les nombres
diffèrent de Windows selon le dialecte et les prérequis du système ; un cas ignoré
n'est jamais compté comme réussi. Copie locale :
`.test-tmp/ci-35856502360/{platform.log,test-summary.json}`.

## Corrections et comportements livrés dans l'arbre de travail

| Constat initial | Changement et limite de la preuve |
|---|---|
| AF-01 : formulaire incompatible avec les CLI | Choix d'exécuteur, mission supervisée et ressource workspace explicites ; équipe Claude/Codex possible. Un plafond monétaire peut être désactivé explicitement dans le formulaire. Un plafond demandé reste opposable : aucune borne de coût/jetons fiable n'est inventée. |
| AF-02 : durée restante supérieure au plafond local refusée | Délai effectif borné au minimum du plafond local et de la durée restante, attente du verrou comprise ; régressions worker vertes. |
| AF-03 et AF-05 : Hermes synchrone, admission/arrêt incertains | Opérations `plan`/`evaluate` asynchrones, clé et corps stables, checkpoint d'admission et `run_id`, suivi et demande d'arrêt. Les états terminaux sont vérifiés ; un arrêt non confirmé devient une erreur explicite. Tests de transport simulé. |
| AF-04 : résultat perdu après échec de comptabilisation | Preuve et réponse métier conservées avant le rapport d'usage ; trois essais bornés avec les mêmes identifiants. Une panne persistante bloque la tentative, conserve la réservation et ne rejoue pas l'effet. Le rapprochement manuel reste nécessaire. |
| AF-06 : approbation Hermes masquée | État `waiting_for_approval` conservé et visible. ACP n'expose pas encore de décision d'approbation Hermes ; le worker demande l'arrêt si cette décision est nécessaire. |
| AF-07 : conversations générales masquées | Sélection visible du contexte général ou projet ; scénario d'interaction Qt couvert. |
| AF-08 : commentaires incomplets après actualisation | Actualisation du fil avec invalidation des réponses obsolètes ; tests natifs ciblés et suite Qt. |

La réponse finale Claude ou Codex, limitée à 16 000 caractères, rejoint les preuves
et l'évaluation avec ses marqueurs de terminaison et de troncature. Les mesures
d'usage absentes restent inconnues. La sortie brute, le prompt et les jetons ne
sont pas publiés comme résultat métier.

## Équipes, compétences et MCP

Une équipe est un DAG de huit étapes au maximum, également limité par la politique
du projet, avec deux étapes indépendantes au plus en parallèle. Chaque étape
reçoit un exécuteur autorisé, un worktree et une branche Git distincts. Les
dépendances transmettent leurs résultats et diffs bornés. Les références de
branches, chemins et différences sont conservées pour revue : **aucune fusion
automatique** n'est effectuée.

Les checkpoints rendent les effets visibles et empêchent leur réexécution
silencieuse. **Une équipe partiellement exécutée reste bloquée après reprise**,
même si certaines étapes sont terminées. Examiner les preuves et le ledger avant
une nouvelle tentative ; la reprise automatique des seules étapes restantes
n'est pas livrée. Les checkpoints Hermes ne constituent pas davantage une
récupération d'un claim API dont la réponse a été perdue.

L'API relit les liaisons de compétences, leurs approbations, révisions et
empreintes avant de fournir les documents au worker. Celui-ci borne le contenu
cumulé et le transmet à la planification et aux CLI sans élargir leurs droits.
Les MCP Streamable HTTP passent par un proxy ACP : délégations éphémères,
révocation vivante, outils autorisés, secrets amont conservés côté API, permis
budgétaire avant effet et déduplication durable par étape et identifiant RPC.
Un résultat d'outil incertain n'est pas rejoué. MCP stdio reste refusé dans ce
parcours. Les régressions MCP ciblées et la suite Python locale complète sont
vertes ; la validation PostgreSQL distante reste distincte.

La concurrence des processus ne fournit pas une sandbox OS. Les droits du compte
worker, les profils dédiés, les ACL et le filtrage réseau restent nécessaires.
Claude demeure en lecture seule ; une écriture Codex doit être explicitement
autorisée. Voir le [contrat des exécuteurs](providers-local-executors.md).

## Preuves locales observables

Les chemins sont relatifs à la racine du worktree. Les journaux et données de test
sous `.test-tmp/` et `apps/desktop/build/` sont ignorés par Git ; ils ne sont pas
des livrables à publier tels quels. Les groupes se recouvrent : leurs nombres ne
doivent pas être additionnés en un total global.

| Vérification | Résultat observé | Preuve locale |
|---|---|---|
| Suite Python complète, quatre partitions disjointes | **3 025 réussis, 70 ignorés, aucun échec**, soit **3 095 cas** ; bases SQLite jetables et chemins temporaires courts | `.test-tmp/functional-final-summary.json` et les quatre rapports XML référencés |
| Suite worker avant ajout DPAPI | **335 réussis, 3 ignorés**, 27,96 s | `.test-tmp/worker-final-full-1.log` |
| État worker et sécurité CLI après DPAPI | **35 réussis**, 1,24 s ; cycle DPAPI Windows réel inclus | `.test-tmp/worker-state-dpapi-proof.log` |
| Hermes/gateway/API, transports simulés | **192 réussis**, 23,26 s ; deux avertissements de dépréciation | `.test-tmp/hermes-fixes/targeted-complete.log` |
| MCP, ciblés après revue | **36 réussis, 0 ignoré**, 136,36 s ; deux avertissements de dépréciation | `.test-tmp/mcp-execution/expiry-final.log` |
| MCP, migrations et API sur PostgreSQL 16 neuf | **95 réussis**, dont les 36 MCP, **1 ignoré** propre à SQLite ; deux assertions historiques de révision corrigées, puis **2 réussis, 0 ignoré** en 8,64 s | `.test-tmp/functional-postgres-04514124c9a9420aac814d904a8f1f0c/report.xml` et `.test-tmp/mcp-rollback-pg-fc76dd5735e047afbcdacd712108f99e/report.xml` |
| Construction native Release | Réussie après compatibilité du gabarit d'automatisation | `apps/desktop/build/operations-compat-build.log` |
| Suite native Qt | **22 suites sur 22**, 33,72 s ; Operations **18 tests** dont cinq cas de confirmation | `apps/desktop/build/operations-compat-ctest.log` et `operations-compat-detail.log` |
| Interactions par les vrais contrôles Qt | **3 réussis, 0 ignoré**, 3 946 ms ; transport métier de test | `apps/desktop/build/functional-interactions-final.log` et captures `apps/desktop/build/qa-functional/01-…` à `08-…` |
| Qt contre une vraie API locale SQLite jetable | **3 réussis, 0 ignoré**, 2 002 ms ; export vérifié de 180 224 octets | `.test-tmp/desktop-journey-afb6961e4c274d909820de57fa6bd134/{result.json,qt-journey.log}` |
| Garde des profils Hermes | **10 réussis**, 0,21 s ; refus des clés réservées et des NUL normalisés par Hermes | `.test-tmp/profile-guard-final.log` |
| Régressions Node | Web **325**, reporter **59**, garde-fous E2E **34**, moteur historique **74** réussis ; typage et build web verts | `.test-tmp/functional-web-final-{1,2,3}.log` et `.test-tmp/functional-node-{3,4,5}.log` |
| Pile locale avec Hermes | Démarrage confirmé, diagnostic Hermes dégradé explicitement | `.test-tmp/local-stack-with-hermes-final.log` |
| Enrôlement worker contre API réelle jetable | HTTP **201**, capacités `agent_team`/`claude_code`/`codex_cli`, portée projet, DPAPI relu et heartbeat **200** ; aucun claim ni modèle lancé | `.test-tmp/worker-local-journey-da2c1d12ac2b4aa188b3802dd1dc9acf/result.json` |
| Contrats et automatisations après intégration d'équipe | **322 réussis**, 63,52 s ; conservation du mode équipe jusqu'à la tentative et refus d'un workspace hors projet | `.test-tmp/automation-contract-final.xml` |
| Premier paquet desktop du lot, avant le dernier correctif Operations | ZIP et installateur 0.10.0 produits, **1 387 fichiers extraits vérifiés par SHA-256**, non signés et non publiés ; installation annulée proprement par sandbox. Ce paquet ne représente pas le dernier code Qt. | `dist/desktop-functional-20260923/{package-validation.json,install-validation.json,SHA256SUMS.txt}` |
| Paquet final depuis `47de619` | Release Qt 6.8.3 / version 0.10.0 ; **1 394 entrées ZIP, 1 387 fichiers extraits**, tous identiques au staging par SHA-256 ; sources propres avant/après | `dist/desktop-functional-final-20260923/{package-validation.json,source-provenance.json,SHA256SUMS.txt}` |

Les 70 cas ignorés de la passe SQLite comprennent 60 tests PostgreSQL, quatre
tests POSIX non applicables sous Windows, trois tests d'entrypoint nécessitant
`sh` et trois tests de liens symboliques indisponibles sur ce poste. Le détail
provient des rapports XML, conservé dans `.test-tmp/functional-skips.json` ; aucun
paquet Python manquant n'est signalé par ces motifs.

Le paquet final local reste **non signé et non publié**, sans installation ni
lancement par le harnais de packaging. Il ne prouve pas une installation Windows :

| Fichier | Octets | SHA-256 |
|---|---:|---|
| `AgentCompanyPlatform-Setup-0.10.0-x64.exe` | 24 326 708 | `6808f7631800709aa5f97dbd2f4752b08ba77ca5b54706598d325508b99fcc6c` |
| `AgentCompanyPlatform-Portable-0.10.0-x64.zip` | 37 007 629 | `dc6b5c381d819388e09f2936cd3ec19bfae2bee1bcdb4b6328c2e8384e079591` |

Le parcours API couvre session/cookie/CSRF, projet, mission avec tentative réelle
en file, budget, automatisation en pause, export dont octets et SHA-256 sont
vérifiés, puis déconnexion. Il ne lance pas la mission sur un modèle payant.
Les captures Qt montrent notamment la création de projet, le formulaire
d'équipe, le titre de mission en texte brut et le retour aux conversations
générales ; elles ne remplacent pas une recette exhaustive de tous les écrans.

Deux contrôles natifs des adaptateurs complètent les fixtures Python :

- Claude Code **2.1.267** a démarré avec un profil isolé, initialisé un MCP HTTP
  loopback et reçu une réponse d'un modèle simulé localement. Code 0 et trois
  événements, preuve `.test-tmp/claude-mcp-native/result.json`. Cela ne démontre
  pas un appel d'outil métier ni une génération Anthropic réelle.
- Codex CLI a accepté la configuration MCP HTTP et son jeton référencé par
  variable d'environnement via `mcp list --json`, preuve
  `.test-tmp/codex-mcp-native/config-validation.log`. Aucun modèle ni outil
  distant n'a été invoqué par ce contrôle.

La revue MCP a aussi reproduit une expiration de délégation pendant l'attente
SQL et relevé une autorisation synchrone dans une route asynchrone. Les contrôles
de délégation et du worker sont relus après attente ; l'autorisation initiale
s'exécute désormais dans le pool de threads. Les cinq régressions d'expiration,
révocation, rotation et blocage de la boucle ASGI ont d'abord échoué, puis réussi
avec les corrections ; voir `.test-tmp/mcp-execution/expiry-red.log` et le relevé
final de 36 tests.

Les deux échecs PostgreSQL initiaux étaient des attentes de tests de la migration
0003 : depuis l'ajout de 0004, une descente échouant dans 0003 reste à 0003, car
chaque révision possède sa transaction. Les tests de conservation des valeurs et
types commencent désormais explicitement à 0003 ; leurs garde-fous sont inchangés.
Voir [les règles de retour arrière](persistence-and-backup.md).

La première passe Python complète a donné 3 013 réussites, 70 cas ignorés et
cinq échecs. Quatre échecs provenaient des chemins temporaires trop longs sous
Windows (CreateProcess et métadonnées Git), reproduits puis revalidés avec des
répertoires courts. Le cinquième a révélé le champ d'exécution manquant dans les
gabarits de routine : le mode équipe est maintenant validé, conservé et matérialisé
dans la mission. La nouvelle passe complète utilise des lots indépendants et des
chemins courts : **3 025 réussis et 70 ignorés**. Un test d'arrêt Hermes dépendait
aussi d'un délai réel de 50 ms et échouait sous charge ; une horloge contrôlée
vérifie maintenant les mêmes appels, l'arrêt confirmé et le checkpoint sans cette
course. Son lot complet a été relancé et donne **1 715 réussis, 40 ignorés**.

Le parcours Qt/API a ensuite détecté une comparaison trop stricte du gabarit
retourné : l'ajout serveur d'`execution: null` était présenté comme une confirmation
incertaine. Qt tolère désormais ce seul défaut optionnel ; une équipe ajoutée,
un budget différent ou un champ inconnu restent refusés. Les nouveaux états Hermes
sont également pris en charge par le web, avec arrêt authentifié et suivi de la
confirmation ; les routines copient la configuration d'équipe sans la perdre.

La recette du paquet a révélé la limite Windows des chemins longs dans une cible
de test à nom UUID très long. Une cible courte permet l'extraction, mais l'écriture
de l'entrée de désinstallation HKCU est refusée dans la sandbox. La revue automatique
a également refusé la relance hors sandbox. Les deux essais ont été intégralement
annulés par Inno Setup ; les cibles et l'entrée de désinstallation sont absentes.
Le cycle installation/désinstallation de ce paquet reste donc **non validé**,
en attente d'autorisation explicite pour cette entrée temporaire ou d'un hôte dédié.
Le binaire portable n'a pas été lancé par ce harnais, qui n'isole pas le registre
QSettings ; les tests Qt et le parcours API natifs sont des preuves distinctes.

## Poste local et état réel d'Hermes

Les lanceurs préparent une base ACP dédiée et des profils séparés ; les secrets
techniques de la pile et le document de credentials worker sont protégés par
DPAPI sous Windows, sans repli en JSON clair. La migration d'un ancien état worker
vérifie d'abord son origine. Les fichiers chiffrés restent liés au compte Windows.

Hermes **0.21.1**, tag `v2026.9.7`, a réellement répondu sur loopback à la santé
et aux capacités. La preuve
`.test-tmp/hermes-local-3c3cc49c98ff41319b6bd6693ee53f31/result.json` indique
`server_reachable`, profil isolé et **zéro soumission de Run**. Son diagnostic
reste **dégradé** : modèle non configuré et disque utilisé à environ 98 %.
L'idempotence durable annoncée vaut 86 400 secondes ; cela ne valide pas une
génération. Aucun compte ou modèle payant n'a été activé pendant ces essais.

La garde du lanceur refuse un `.env` dans le checkout Hermes et les réglages de
profil susceptibles d'écraser ses bornes de réseau ou ses chemins réservés,
y compris `.op.env` et la configuration gérée. Les sources de secrets externes
non prises en charge sont refusées explicitement. Procédure et limites :
[poste local](local-runtime.md), [garde de profil](../scripts/check_hermes_profile.py).

## Ce qui reste à terminer

- Procédure de publication de `CLAUDE.md` après clôture des limites ; une CI verte
  ne constitue pas une publication 0.10.0 ni une fin de V1.
- Recette autorisée avec authentifications et modèle réellement disponibles :
  Hermes → Claude/Codex → résultat, puis MCP métier et compétences sur un projet
  dédié. L'installation des binaires et la santé HTTP ne suffisent pas.
- Reprise après claim incertain, publication terminale et rapprochement complet
  après panne. **N2-5 n'est pas clos : seul le volet délai est corrigé** ; la
  récupération de l'attribution n'est pas livrée.
- Les **26 constats Lot H** restent dans le
  [registre de revue](lot-h-091-review-status.md). Les recouvrements AF/N2 et les
  corrections partielles de ce lot ne diminuent pas ce décompte sans revue de
  clôture de chaque constat.
- Recette distante Railway, installation et mise à jour sur Windows propre,
  signature des binaires, recette visuelle complète et publication V1. Aucun
  travail Godot/pixel ni fusion automatique de branches d'agents n'est annoncé.
