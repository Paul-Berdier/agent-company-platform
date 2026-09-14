# Automatisations, budgets et alertes

Date d'état : 14 septembre 2026, Europe/Paris — version publiée `0.7.0`, complétée
par le Lot G `0.8.0` dans l'arbre de travail

Le Lot F ajoute des **routines** durables : chaque routine associe un calendrier à un
gabarit de mission. À l'échéance, le planificateur matérialise une mission normale ;
son exécution, sa validation technique, ses preuves et son acceptation restent donc
les objets du cycle de mission existant. Une routine naît désactivée et son activation
est toujours une action séparée.

La tranche est utilisable par l'API, l'interface web et le CLI `acp`. Elle est
implémentée et couverte par des suites ciblées locales. Elle ne constitue pas encore
une exploitation de production : SQLite et l'upgrade ad hoc restent le chemin local,
les migrations PostgreSQL, Railway, les sauvegardes et la restauration appartiennent
au Lot H.

## Modèle et cycle de vie

Une automatisation contient :

- un nom et une description ;
- un calendrier `cron` ou `interval`, avec un fuseau IANA explicite ;
- un gabarit complet de mission : objectif, résultat attendu, critères, autonomie,
  ressources, budget, durée, affectation, priorité et capacités requises ;
- une politique de rattrapage `skip` ou `run_once` ;
- un plafond de concurrence de 1 à 5 missions actives ;
- un curseur persistant `next_run_at` et les compteurs d'échecs nécessaires au
  planificateur.

La création exige `Idempotency-Key`, persiste l'identité du principal et l'empreinte
canonique de la requête, puis retourne la routine **désactivée**. Rejouer la même clé,
dans le même projet, avec le même principal et le même corps, retourne le même objet ;
réutiliser cette clé dans ce scope avec un autre corps répond `409`. La même clé dans
un autre projet constitue un autre scope. L'activation calcule la première occurrence
future. Une modification du calendrier recalcule ce curseur sous verrou.

Chaque traitement, y compris un refus, produit un `automation_run` durable. Les issues
sont `launched`, `skipped_concurrency`, `skipped_disabled`, `skipped_catchup` ou
`failed`. Pour une mission lancée, `completion_status` reste `null` jusqu'à la
réconciliation, puis conserve son état terminal : `blocked`, `succeeded`, `failed`,
`cancelled` ou `interrupted`. Chaque ligne conserve aussi le fuseau du calendrier au
moment du tir : modifier ensuite la routine ne réétiquette donc jamais l'heure locale
d'un historique déjà matérialisé.

## Calendrier, fuseaux et heure d'été

Le fuseau par défaut est `Europe/Paris`, mais il fait partie de chaque calendrier et
doit être un nom IANA connu. L'évaluateur refuse à l'écriture les expressions qu'il ne
sait pas calculer.

Le cron utilise cinq champs dans l'ordre `minute heure jour-du-mois mois
jour-de-semaine`. Il accepte `*`, une valeur, une liste, un intervalle et un pas. Quand
le jour du mois et le jour de semaine sont tous deux restreints, la sémantique POSIX
est une union. La recherche d'une prochaine occurrence est bornée à quatre années :
une date impossible ne bloque jamais le planificateur.

Les expressions cron sont interprétées en **heure locale** :

- au passage à l'heure d'été, une heure locale inexistante est omise ; elle n'est pas
  déplacée artificiellement ;
- au retour à l'heure d'hiver, une heure locale ambiguë ne produit qu'une occurrence,
  la première (`fold=0`) ;
- la base IANA de la machine, ou le paquet `tzdata` sous Windows, est l'autorité ;
- le calendrier renvoie l'instant UTC, l'heure locale avec son décalage et
  `utc_offset_minutes`. Le navigateur affiche ces valeurs sans réinventer les règles
  de fuseau.

Un intervalle est une durée fixe en secondes, de 60 à 31 536 000. Il ne suit pas
l'heure murale et ne subit donc pas les bascules saisonnières.

`GET /automations/calendar` couvre par défaut les 30 jours précédents et les 90 jours
suivants. La fenêtre explicite doit porter des dates avec fuseau et sa réponse est
limitée à 366 jours et 500 entrées. Une entrée passée peut porter la mission et l'issue
réellement matérialisées ; une entrée future reste `planned`.

## Rattrapage, concurrence et absence de doublon

Une occurrence planifiée est identifiée par une `fire_key` déterministe : SHA-256
tronqué de `automation_id` et de l'instant nominal normalisé en UTC. Un tir manuel y
incorpore sa clé et son principal ; un tir webhook, son `event_id`. Une contrainte
unique SQL sur `(automation_id, fire_key)` est l'arbitre final. Deux ticks, deux
requêtes ou un rejeu après réponse perdue ne peuvent donc pas créer deux missions pour
la même occurrence.

Le délai de grâce du planificateur est actuellement de 30 secondes :

- `skip` écrit un résultat `skipped_catchup`, avance directement au premier tir futur
  et ne crée aucune mission ;
- `run_once` matérialise au plus une des occurrences manquées, puis avance également
  au premier tir futur ; il ne rejoue pas tout l'historique.

Avant de lancer une mission, la plateforme compte les exécutions actives de cette
routine. Quand `max_concurrent_runs` est atteint, elle conserve un résultat
`skipped_concurrency` sans créer de mission. Les déclenchements manuels et webhook
passent par la même primitive et respectent cette limite ; un déclenchement manuel ne
décale jamais le calendrier.

## Planificateur, bail et fencing

Seuls les workers enrôlés avec le privilège explicite `global_access` concourent au
même bail `automation-scheduler`; un worker limité à un projet reçoit `403` sur les
trois routes et ne démarre pas cette boucle localement. Un seul détenteur actif traite
les échéances. Le worker ne lit jamais la base : il appelle les routes internes avec
son Bearer worker. L'enrôlement normal utilise `--project ID`; le worker global dédié
au planificateur utilise `--global-access`.

- `POST /workers/{worker_id}/automation-scheduler/lease` acquiert ou renouvelle le
  bail singleton ;
- le bail dure 45 secondes et chaque reprise après expiration ou libération augmente
  son `fencing_token` ;
- `POST /workers/{worker_id}/automation-scheduler/tick` exige
  `X-Scheduler-Fencing-Token`, réconcilie d'abord les missions terminées puis traite au
  plus 100 routines dues (`25` par tick du worker) ;
- le bail est revérifié et renouvelé entre les transactions ; un détenteur expiré ou
  un ancien fence reçoit `409` et ne peut plus écrire ;
- `POST /workers/{worker_id}/automation-scheduler/lease/release` libère proprement le
  bail. Une perte de la requête de libération reste récupérable par expiration.

Chaque occurrence est traitée dans une transaction autonome. L'ordre
`next_run_at, id`, le verrouillage de la ligne et `skip_locked` empêchent qu'une
routine invalide affame les suivantes. Une configuration persistée devenue invalide
produit un échec expurgé et reçoit un nouveau curseur défensif cinq minutes plus tard.

Après chaque réconciliation, un succès remet le compteur d'échecs consécutifs à zéro.
Les états `blocked`, `failed` et `interrupted` l'incrémentent. Au seuil persistant
actuel de trois, la routine est désactivée et une alerte durable est ouverte.

Le mode ponctuel `worker --once` ne démarre pas la boucle du planificateur. En mode
persistant, elle n'est active que pour un worker global.

## Idempotence des mutations de configuration

La création, le `PATCH`, l'activation, la désactivation, la rotation et la révocation
du webhook exigent tous un `Idempotency-Key` ASCII visible de 1 à 200 caractères.
Pour `PATCH`, `enable`, `disable` et `DELETE webhook`, la base conserve dans la même
transaction que l'effet et son événement un journal scoppé par automatisation,
principal, type de commande et clé. Le journal contient l'empreinte canonique de la
requête, sa postcondition et une révision monotone de configuration.

Un rejeu identique dont la postcondition est encore courante est sans écriture et
sans nouvel événement. Réutiliser la clé avec un autre corps répond `409`. Si une
commande ultérieure a remplacé le résultat — par exemple activation A, désactivation
B, puis rejeu de A après perte de sa réponse — le rejeu de A répond également `409`
et ne réactive jamais la routine. Les avancées de curseur du planificateur ne changent
pas cette révision et ne rendent donc pas un rejeu légitime caduc.

## Déclenchements manuels et webhooks

`POST /automations/{id}/trigger` exige un rôle membre et un `Idempotency-Key` ASCII
visible de 1 à 200 caractères. La clé est scoppée au principal et à la routine. Un
rejeu retourne le même `automation_run`; le CLI et le web conservent la clé quand le
résultat d'un appel est incertain.

Le webhook est désactivé par défaut. Un membre installe ou fait tourner un secret avec
`POST /automations/{id}/webhook`. Le client fournit un secret base64url représentant
au moins 256 bits et une clé d'idempotence. La base ne conserve que l'empreinte du
secret et un journal de rotation sans secret brut. La seule réponse de rotation
contient le secret fourni ; les lectures ultérieures ne donnent que l'état,
l'horodatage et le chemin de l'endpoint.

`POST /automations/{id}/webhook/trigger` est la seule route utilisateur de cette
tranche qui n'emploie pas une session : elle exige `Authorization: Bearer <secret>`.
Son corps contient un `event_id` stable et un `payload` JSON. L'identité de
l'occurrence vient de `event_id`, ce qui déduplique les replays de l'émetteur. Faire
tourner le secret invalide immédiatement l'ancien ; `DELETE
/automations/{id}/webhook` révoque le secret et ferme la route.

Le payload est borné à 32 niveaux et 10 000 valeurs JSON. Ces bornes s'ajoutent au
plafond du corps HTTP ; elles évitent qu'un petit corps très imbriqué monopolise le
parseur.

Ni l'API, ni l'interface, ni le CLI n'envoient de notification vers un webhook
sortant. Le webhook décrit ici est uniquement un **déclencheur entrant**.

La frontière HTTP refuse avant parsing les corps dépassant 1 Mio sur les routes
ordinaires, webhook compris. Les imports de skills gardent leur borne dédiée de
32 Mio ; le téléversement de livrables authentifie d'abord le worker, puis applique en
flux son plafond par fichier de 200 Mio par défaut et son quota par tentative. Le
webhook entrant est en plus limité localement à 120 requêtes par minute et par adresse
TCP observée, dans chaque processus API. Cette défense locale ne remplace pas une
limite distribuée au reverse proxy lors d'un déploiement multi-processus. Le cache
suit au plus 10 000 adresses ; les adresses excédentaires partagent un compartiment
borné jusqu'à l'expiration d'une fenêtre, sans croissance mémoire non bornée.

## Budgets réellement appliqués

Le budget du gabarit borne chaque mission. Une politique de projet ajoute :

- un budget journalier calculé dans le fuseau choisi ;
- jusqu'à 100 plafonds journaliers par fournisseur, sans doublon de nom ;
- un plafond de missions actives par projet ;
- un plafond de relances par mission ;
- `max_spawned_agents_per_run`, persisté et affiché. Dans le Lot F il n'existait pas
  encore de point de spawn ; l'exécuteur Lot G lance au plus une invocation CLI de
  premier niveau par tentative. Ses descendants ne sont ni comptés ni interdits : le
  plafond global n'est donc pas démontré et aucun fan-out dynamique n'est livré.

Le worker doit obtenir un permis idempotent avant chaque effet consommateur raccordé :
planification, exécution et évaluation. Il rapporte ensuite la consommation avec un
`report_id` et le `permit_id` correspondant. La phase contractuelle `tool` est prête,
mais le courtier d'appels MCP pendant une mission n'est pas livré. L'identité worker,
le lease de tentative et `X-Attempt-Fencing-Token` sont revérifiés sous transaction.

Le ledger distingue une mesure absente de zéro. Coûts, jetons et appels d'outils sont
agrégés par mission, journée comptable et fournisseur. Les montants utilisent un
décimal persistant ; une très petite valeur positive n'est pas arrondie à zéro. Le
jour comptable choisi au permis est conservé pour le rapport associé, même si la
mission franchit minuit. Après le premier permis du projet, son fuseau comptable ne
peut plus changer : les journées historiques et futures gardent ainsi une frontière
stable.

Une même capacité est imposée par Python, TypeScript et la base : au plus
`999999999999` unités monétaires et `9007199254740991` pour chacun des compteurs de
jetons ou d'appels. Le ledger immuable conserve chaque incrément accepté ; son cache
agrégé se sature à ces bornes au lieu de déborder ou de revenir à une petite valeur.
Une fois une capacité atteinte, le permis suivant est refusé avant effet.

Une mesure inconnue reste `unknown`, jamais `ok` : si un plafond exige cette mesure,
le permis est refusé. Une estimation peut produire un avertissement mais ne prouve pas
à elle seule un dépassement. La consommation rapportée après l'appel est conservée ;
si elle établit un dépassement, elle ouvre ou élève une alerte `budget.guard` et les
permis suivants sont refusés. Les rapports et réservations sont idempotents ; un même
identifiant avec un autre contenu est refusé. Si l'appel ou son rapport échoue, la
réservation non rapprochée reste comptée au lieu de devenir artificiellement zéro.
Avant de lancer l'effet, le worker valide la réponse complète
`BudgetMutationResult` (`accepted`, `idempotent`, `permit_allowed` et verdict interne
cohérent) ; un HTTP 200 incomplet ou contradictoire est indisponible et aucun effet ne
part. La même validation s'applique au rapprochement.

Hermes `0.21.1` n'expose pas de plafond dur de coût ni de jetons pour `/v1/runs`.
Avec ce provider, une mission ou une politique qui limite l'une de ces dimensions est
donc refusée explicitement **avant** l'appel (`estimation conservatrice indisponible`).
Le headroom restant n'est jamais présenté comme une borne. Les effets locaux et les
providers sans facturation déclarent au contraire des zéros explicites vérifiables ;
une mesure absente reste inconnue. Un adaptateur futur ne pourra autoriser ces budgets
qu'en imposant réellement chaque borne annoncée.

Routes utilisateur :

- `GET /projects/{project_id}/budget-policy` ;
- `PUT /projects/{project_id}/budget-policy` ;
- `GET /projects/{project_id}/budget-usage?day=YYYY-MM-DD`.

Les routes `/work/workers/.../budget/permit` et `/budget/usage` sont internes aux
workers et ne sont pas une API pour le navigateur.

## Saturation du stockage et alertes

Le Lot F rend explicites les erreurs du stockage local. Une saturation physique ou du
spool multipart répond `507`; un volume indisponible répond `503`. Si le run et le
projet ont déjà été résolus, l'API ouvre aussi une alerte `storage.saturated` ou
`storage.unavailable`. Une panne survenue avant cette résolution — par exemple si la
pièce précède les champs d'identité du multipart — ne peut pas être attribuée et ne
produit donc que la réponse HTTP. Les chemins, exceptions brutes et détails sensibles
ne sont pas recopiés dans l'alerte ou l'événement. Le quota par tentative existant
continue de répondre `413`; un rejeu d'un même contenu reste idempotent et ne consomme
pas deux fois le quota.

Les alertes sont des objets canoniques par projet. Une clé de cause stable garantit
qu'une même cause ne possède qu'une alerte ouverte, y compris sous concurrence. Une
alerte peut monter de `info` à `warning` puis `critical`, jamais redescendre. Son
acquittement est idempotent et une nouvelle réapparition de la cause peut ouvrir une
nouvelle ligne.

Le seul canal livré est `in_app`. Les préférences sont personnelles, par projet :
activation globale, sévérité minimale et catégories budget, échecs d'automatisation
et stockage. Elles filtrent la boîte du demandeur sans modifier les alertes canoniques
du projet. Leur lecture n'écrit aucune ligne et retourne des valeurs par défaut si
elles n'ont jamais été enregistrées.

Routes :

- `GET /alerts` avec filtres `project_id`, `open`, `severity`, `kind` et `limit` ;
- `POST /alerts/{alert_id}/acknowledge` ;
- `GET /projects/{project_id}/notification-preferences` ;
- `PUT /projects/{project_id}/notification-preferences`.

Aucun courriel, SMS, push système ou webhook sortant n'est implémenté.

## Routes utilisateur des automatisations

| Méthode et chemin | Rôle minimal | Effet |
|---|---|---|
| `POST /projects/{project_id}/automations` | membre | crée, désactivée ; `Idempotency-Key` obligatoire |
| `GET /automations` | lecteur | liste filtrée par projets visibles, 500 au maximum |
| `GET /automations/calendar` | lecteur | calendrier passé et futur, 500 entrées au maximum |
| `GET /automations/{id}` | lecteur | détail, gabarit et 20 exécutions récentes au maximum |
| `PATCH /automations/{id}` | membre | remplace uniquement les champs fournis ; `Idempotency-Key` obligatoire |
| `POST /automations/{id}/enable` | membre | active et calcule le prochain tir ; `Idempotency-Key` obligatoire |
| `POST /automations/{id}/disable` | membre | suspend les tirs futurs ; `Idempotency-Key` obligatoire |
| `POST /automations/{id}/trigger` | membre | tir manuel idempotent |
| `GET /automations/{id}/runs` | lecteur | historique borné à 500 lignes |
| `GET /automations/{id}/webhook` | lecteur | état sans secret |
| `POST /automations/{id}/webhook` | membre | installe/rotate un secret idempotent |
| `DELETE /automations/{id}/webhook` | membre | révoque le déclencheur entrant ; `Idempotency-Key` obligatoire |
| `POST /automations/{id}/webhook/trigger` | secret webhook | tir entrant dédupliqué par `event_id` |

Les mutations par session exigent le jeton CSRF habituel. Une ressource enfant est
résolue avant l'autorisation afin qu'un identifiant d'un autre projet ne permette pas
de choisir son scope. Une ressource inconnue répond `404`, une ressource existante
mais inaccessible `403`, et les listes omettent les projets inaccessibles. Cette
distinction `403`/`404` révèle l'existence d'un identifiant déjà connu du demandeur.

## Interface web

L'espace « Automatisations » propose quatre vues : routines, calendrier, alertes et
réglages. L'assistant de création expose le calendrier, le fuseau, le rattrapage, la
concurrence et toutes les bornes de budget du gabarit. Une routine confirmée depuis
une mission réussie, validée techniquement et acceptée peut être préremplie, mais elle
reste désactivée jusqu'à une activation explicite.

Le détail permet de modifier, activer, suspendre, déclencher, lire l'historique et
gérer le webhook. Rotation et désactivation du webhook demandent une confirmation.
Le secret est généré avec l'aléa cryptographique du navigateur. Le serveur ne le
retourne que dans la réponse de rotation ; l'interface peut le conserver dans son état
local et le réafficher dans le panneau de récupération après une réponse réseau
incertaine. Fermer le détail retire cet état visible. La même clé et le même secret
sont alors réutilisés pour un rejeu sûr.

Les réglages montrent la politique et la consommation budgétaires, avec l'origine
`reported` ou `estimated` et l'absence de mesure distincte de zéro. Ils permettent
d'éditer les plafonds journaliers et fournisseur ainsi que les préférences d'alertes.
Les listes sont volontairement bornées et l'interface l'annonce quand elle affiche le
maximum d'une page. Les tests du DOM ne remplacent pas un parcours dans un navigateur
réel.

## CLI `acp automations`

Exemples depuis la racine du dépôt :

```powershell
acp automations list --project <project-id> --enabled
acp automations create --project <project-id> `
  --name "Rapport quotidien" `
  --schedule-kind cron --expression "0 9 * * 1-5" `
  --timezone Europe/Paris `
  --template-file apps/cli/examples/automation-mission-template.json
acp automations show <automation-id>
acp automations update <automation-id> --catchup run_once --max-concurrent-runs 2
acp automations enable <automation-id>
acp automations disable <automation-id>
acp automations trigger <automation-id>
acp automations runs <automation-id> --limit 25
acp automations calendar --project <project-id> `
  --start 2026-10-01T00:00:00+02:00 --end 2026-11-01T00:00:00+01:00
acp automations webhook status <automation-id>
acp automations webhook rotate <automation-id> --secret-env ACP_WEBHOOK_SECRET
acp automations webhook disable <automation-id>
```

Le gabarit peut venir de `--template`/`--template-json` ou d'un fichier UTF-8 de 1
Mio au maximum ; un BOM est accepté. Le CLI valide les principales bornes avant
l'appel, exige les trois champs d'une modification de calendrier et normalise `15m`,
`2h` ou `1d` en secondes pour un intervalle. Le contrat serveur reste l'autorité.

Création, tir manuel et rotation utilisent une clé d'idempotence explicite ou générée.
Le résultat affiche cette clé. Une coupure réseau, un HTTP `408`/`5xx` ou une réponse
hors contrat produit un code de sortie non nul et indique exactement la clé à rejouer.
Un tir enregistré avec une issue autre que `launched` sort également en erreur : le
CLI ne confond pas persistance de l'occurrence et lancement d'une mission.

Un secret de webhook n'est jamais accepté directement sur la ligne de commande. Le
CLI en génère un par défaut avec un générateur cryptographique ; une valeur imposée
vient de `--secret-env` ou `--secret-file`, avec un fichier réservé au seul utilisateur
sur POSIX. La validation locale applique le même contrat que l'API : 43 à 200
caractères base64url qui décodent au moins 32 octets. Cette protection de mode ne peut
pas être démontrée de la même façon sur Windows ; il faut alors protéger le fichier
par ACL ou préférer une variable d'environnement éphémère.

## Vérification locale

Les tests ciblés couvrent les contrats et la base, les routes API, le planificateur,
le worker, le ledger, les alertes, le stockage, le CLI et le DOM de l'interface. Le
parcours suivant démarre l'API dans un processus séparé avec une base SQLite
temporaire :

```powershell
./.venv/Scripts/python.exe scripts/verify_automation_journey.py
```

Le 14 septembre 2026, il a rendu **62 étapes sur 62 réussies**, code `0`. Il fixe son
`PYTHONPATH`, vérifie la provenance des imports, démarre d'abord l'API avec une portée
worker globale, puis la redémarre sur la même base avec une portée projet. Il vérifie
notamment création/rejeu/conflit, activation, calendrier, bail/fence/tick, les trois
modes de tir, historique, permis/rapport de budget et acquittement d'une alerte. Il ne
lance pas un navigateur, un worker distant, Hermes, un fournisseur payant ou un
service externe.

Au démarrage SQLite, les tables du Lot F sont comparées au modèle courant. Une table
ancienne ou partiellement créée est reconstruite dans la transaction d'upgrade avec
ses colonnes, types, nullabilités, clés étrangères, unicités, index et contraintes ;
les index et triggers locaux compatibles sont préservés. L'upgrade contrôle ensuite
les clés étrangères et est rejouable. Le ledger historique n'est complété que quand
ses données permettent une mesure et une devise cohérentes ; sinon le démarrage échoue
en annulant atomiquement la reconstruction au lieu d'inventer une consommation.
`create_all()` s'exécute encore avant cette transaction : un refus peut donc avoir
créé de nouvelles tables **vides**, mais il ne remplace ni ne réécrit la table
historique refusée. Ce mécanisme reste une migration locale SQLite ; il ne remplace ni
Alembic, ni la sauvegarde/restauration du Lot H.

## Limites et travaux suivants

- Les garanties sont exercées localement avec SQLite et des clients/programmes de
  test. PostgreSQL, Alembic, Railway, sauvegarde et restauration restent Lot H.
- Aucun navigateur réel, aucune instance Hermes réelle, aucun fournisseur payant et
  aucun service externe n'est requis ou revendiqué par les preuves du Lot F.
- Le stockage d'artefacts reste un répertoire local. La saturation est détectée, mais
  aucun adaptateur objet ni volume hébergé n'a été éprouvé.
- `max_spawned_agents_per_run` est contractuel, persisté et visible. Le point de spawn
  unique du Lot G limite l'exécution à une invocation CLI de premier niveau gérée par ACP ; ses
  descendants restent hors métrique et un contrôle dynamique de fan-out est absent.
- Le planificateur crée des missions ; les limites du runner local demeurent : pas de
  sandbox OS/réseau forte et aucune action agentique tierce réellement exécutée.
- Les alertes restent dans l'application. Il n'existe ni ordonnanceur de rétention,
  ni livraison de notifications hors plateforme.
