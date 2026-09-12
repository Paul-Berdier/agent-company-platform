# Centre MCP et bibliothèque de skills

Date d'état : 12 septembre 2026 — version `0.5.0`
Statut : livré au Lot D et couvert par des tests locaux déterministes. Le transport
`http` a été rejoué contre un serveur MCP Streamable HTTP réellement démarré sur le
bouclage ; aucun serveur MCP **tiers**, aucun dépôt GitHub réel et aucun runner distant
réel n'ont été contactés.

## Objet et limites

Ce document décrit ce que la plateforme fait aujourd'hui des serveurs MCP, des skills
et des extensions de projet : les objets persistés, les parcours réellement exposés
par l'API, le web et le CLI, les contrôles appliqués côté serveur et côté runner, et
ce qui reste hors périmètre.

Trois objets restent distincts :

- un **serveur MCP** expose des outils via un transport supporté (`http` Streamable
  HTTP 2025-06-18/2025-03-26, ou `stdio` lancé sur un runner autorisé) ;
- un **skill** contient un `SKILL.md`, des références et, parfois, des scripts ;
- un **plugin natif** charge du code dans un processus de confiance. Un manifeste ne
  constitue pas une sandbox : ce type est signalé comme non isolé dans l'interface.

L'activation d'un de ces objets n'accorde aucun droit implicite. Les droits
appartiennent au rattachement à un projet (`binding`) et à l'instantané figé dans la
mission qui les utilise.

## Architecture livrée

```text
Interface web (Connexions, Bibliothèque)   CLI acp (secrets | mcp | skills)
                    │                                │
                    └──────────────┬─────────────────┘
                                   ▼
                      API plateforme (FastAPI, RBAC)
                                   │
     ┌───────────────┬─────────────┼───────────────┬───────────────────┐
     ▼               ▼             ▼               ▼                   ▼
coffre de       politique de   registre MCP     registre skills    extensions
secrets Fernet  sortie SSRF    (révisions,      (révisions,        résolues par
(références)    + client épinglé diagnostics)   fichiers, scan)    projet
                     │               │
                     ▼               ▼
              serveur MCP http   runner autorisé (probe stdio)
```

Le registre conserve métadonnées, révisions immuables, découvertes et rattachements.
Hermes reste l'autorité pour ses skills et toolsets natifs : ils sont **lus** et
affichés dans Connexions (`docs/hermes-integration.md`), jamais recopiés dans le
registre.

### Modèle de données

| Table | Rôle |
|---|---|
| `secrets` | valeur chiffrée (Fernet), portée `platform` ou `project`, `key_id`, rotation, révocation, `last_used_at` |
| `mcp_servers` | identité, transport, lieu d'exécution, statut, révision courante, runner désigné |
| `mcp_server_revisions` | configuration immuable (références de secrets uniquement), empreinte, découverte, risques, diff, approbation requise |
| `mcp_probes` | diagnostic : autorisation, décision, lease runner, résultat, erreur, expiration |
| `mcp_bindings` | projet, révision résolue, sous-ensemble d'outils, activation, révocation |
| `skills` / `skill_revisions` / `skill_bindings` | mêmes règles pour les skills : manifeste de fichiers avec SHA-256, frontmatter, licence, dépendances, findings de contrôle |

Une révision est immuable. Une mission fige les extensions résolues au démarrage dans
`TaskModel.meta["extensions"]` : une révision ultérieure ne modifie pas une mission en
cours.

## Parcours MCP

1. **Déclarer** un serveur depuis le catalogue vérifié (`GET /mcp/catalog`, trois
   entrées documentées, jamais exécutées pour vérification), une URL, un import
   Hermes/Claude/Codex ou une commande absolue.
2. **Contrôles d'enregistrement** (`POST /mcp/servers`, propriétaire uniquement) :
   URL `https` sauf allowlist explicite, pas d'userinfo, commande stdio absolue,
   paquet `npx`/`uvx`/`pipx run` épinglé, et refus `422` d'une valeur littérale qui
   ressemble à un secret (`*TOKEN*`, `*KEY*`, `Authorization`…) avec le message
   « utilisez une référence de secret ».
3. **Diagnostiquer** (`POST /mcp/servers/{id}/probe`) :
   - `http` : exécuté immédiatement par l'API à travers le client épinglé
     (validation, résolution DNS, adresse épinglée, redirections revalidées, corps
     borné) ; résultat `succeeded` ou `failed` avec un message exploitable ;
   - `stdio` : rien n'est lancé. Une autorisation est créée (`pending_approval`) avec
     l'action, la cible `commande + arguments`, les conséquences, la portée (runner
     désigné), l'empreinte de la révision et une expiration d'une heure. Après
     `POST /mcp/probes/{id}/decision`, seul un runner authentifié annonçant la
     capacité `mcp_stdio_probe` et non simulé peut réclamer le lancement ; le lease
     dure 180 secondes et un résultat hors lease est refusé (`409`).
4. **Choisir** les outils découverts et **rattacher** à un projet
   (`POST /mcp/servers/{id}/bindings`). Un outil inconnu de la révision courante est
   refusé (`422`) ; un secret de portée projet ne peut servir qu'à son projet (`403`).
5. **Activer** : refusé (`409`) tant que la découverte n'est pas courante pour
   l'empreinte de la révision, et, en `stdio`, tant qu'aucun diagnostic réussi ne
   porte cette empreinte.
6. **Suivre** : révision, diff, rollback, désactivation réversible, révocation
   irréversible avec raison obligatoire (les rattachements sont révoqués, l'historique
   reste lisible), événements d'audit `mcp.*` sans aucune valeur de secret.

Une configuration `localhost` est résolue dans le contexte d'exécution : elle est
signalée comme telle et ne rend pas un MCP local joignable depuis un service distant.

### Import et export

- `POST /mcp/import/preview` normalise un fichier Hermes (`mcp_servers`), Claude
  (`mcpServers`) ou Codex (`[mcp_servers.*]`), détecte le format, liste les entrées
  importables, les incompatibilités et des **candidats de secrets masqués**
  (`***` + deux derniers caractères). Le contenu est envoyé par le client : le serveur
  ne lit jamais un chemin fourni par l'utilisateur.
- `POST /mcp/import/apply` crée les serveurs choisis en reliant chaque candidat à un
  secret existant du coffre.
- `GET /mcp/export?format=hermes|claude|codex` produit une configuration utilisable
  avec des placeholders `${ACP_SECRET_<NOM>}` ; aucune valeur n'est exportée, et les
  écarts de compatibilité sont listés dans `partial_compatibility`.

La compatibilité partielle est explicite, format par format :

| Format | Ce qui n'est pas exprimable dans le fichier |
|---|---|
| Hermes | pas de portée projet native : la restriction repose sur `tools.include` et sur la plateforme ; statut, révisions et autorisations de lancement restent gérés par la plateforme |
| Claude Code | pas de sélection d'outils par serveur : tous les outils découverts seront exposés au client ; portée projet et révisions restent côté plateforme |
| Codex | un seul secret d'en-tête par serveur via `bearer_token_env_var`, les autres passent par `env_http_headers` ; portée projet et révisions restent côté plateforme |

Chaque export porte aussi ses notes d'application : où définir les variables
`ACP_SECRET_*` (`~/.hermes/.env` pour Hermes, l'environnement du client pour Claude ou
Codex, jamais dans le fichier de configuration), et comment faire relire la
configuration (rechargement Hermes sous ~30 s ou `/reload-mcp` ; relance du client pour
Claude et Codex). Un export restreint à un projet le signale : les serveurs non liés à
ce projet sont absents du fichier.

Aucune installation automatique n'est faite côté Hermes : la plateforme exporte, c'est
l'opérateur qui applique. Aucune API HTTP d'Hermes 0.21.1 ne permet d'écrire cette
configuration.

### Bornes de découverte

| Transport | Pages | Outils | Dépassement |
|---|---:|---:|---|
| `http` (API) | 10 | 500 | `truncated=true` dans la découverte |
| `stdio` (runner) | 20 | 500 | échec explicite `too_many_tools` |

La sonde stdio refuse aussi une **page unique** plus grande que sa capacité : une
liste tronquée annoncée comme complète serait un faux succès. Les descriptions
d'outils sont bornées à 2 000 caractères et un `inputSchema` de plus de 50 000
caractères sérialisés est remplacé par `{"truncated": true}`.

## Parcours skills

1. **Importer** une révision explicite depuis une source contrôlée :
   `SKILL.md` saisi, dossier local **explicitement autorisé**
   (`ACP_SKILLS_ALLOWED_DIRS`, sinon `403`), archive ZIP, ou GitHub `owner/repo@SHA`
   (opt-in `ACP_SKILLS_GITHUB_ENABLED`, sinon `503` ; commit épinglé obligatoire).
   Bornes : 500 fichiers, 20 Mio au total, 2 Mio par fichier, 25 Mio pour une archive
   GitHub ; traversées `../`, liens et fichiers spéciaux refusés.
2. **Relire** : arborescence, contenu affiché **comme texte** (jamais rendu),
   frontmatter, licence, dépendances (variables d'environnement requises, toolsets,
   scripts, indicateurs réseau) et findings du contrôle automatique.
3. **Approuver** quand la portée augmente : une révision qui ajoute un script, un
   accès réseau ou une permission exige une approbation propriétaire avant activation
   (`409` sinon).
4. **Rattacher** à un projet, **activer**, **désactiver**, **revenir en arrière** ou
   **révoquer** avec raison.

Le contrôle automatique (`skills/scan.py`) signale des risques — script, `eval`,
`curl | sh`, chemins sensibles, caractères Unicode invisibles, formulations
d'injection de prompt — et le dit explicitement : il est **indicatif** et ne certifie
aucune source.

## Secrets, réseau et expurgation

- **Coffre** : `ACP_SECRETS_KEYS` contient des clés Fernet séparées par des virgules ;
  la première chiffre, les suivantes déchiffrent encore (rotation sans perte). Sans
  clé, `GET /secrets/status` répond `configured=false` et les routes `/secrets` qui
  chiffrent ou déchiffrent répondent `503` avec l'action à effectuer. Une valeur n'est jamais retournée : ni
  dans une réponse, ni dans un export, ni dans un événement, ni dans le frontend.
- **Injection au dernier moment** : une valeur n'est déchiffrée que pour le probe HTTP
  (en-têtes, côté API) ou pour le claim d'un probe stdio par un runner authentifié
  (variables d'environnement, réponse `Cache-Control: no-store`). Un secret révoqué ou
  illisible produit un échec explicite, jamais un appel sans en-tête.
- **Expurgation symétrique** : tout ce qu'un serveur MCP renvoie (`serverInfo`,
  capacités, noms, descriptions et schémas d'outils, `stderr`, messages d'erreur) est
  du contenu non fiable. Les valeurs injectées y sont remplacées par `***` avant
  écriture en base, par le runner **et** par l'API — `acp_contracts.redaction` est la
  seule définition de cette règle, appliquée au transport HTTP comme au résultat posté
  par un runner.
- **Politique de sortie** (`outbound.py`) : `http` refusé hors allowlist, userinfo
  refusé, résolution DNS contrôlée (une seule adresse bloquée suffit à refuser),
  adresse épinglée pendant la requête, redirections revalidées entièrement (3 au
  maximum), corps borné à 2 000 000 octets. Loopback, réseaux privés, link-local dont
  `169.254.169.254`, CGNAT, ULA IPv6, IPv4-mapped, 6to4 et Teredo sont bloqués ; une
  allowlist ciblée reste possible et **chaque usage produit un événement d'audit**
  `outbound.private_allowlist_used`.
- **Runner stdio** : capacité désactivée par défaut, allowlist d'exécutables absolus
  obligatoire, comparaison après résolution du chemin, aucun shell, environnement
  minimal (aucune variable du worker n'est héritée), durée et sorties bornées, arrêt
  de l'arbre de processus.

## Catalogues vérifiés

Les deux catalogues sont des fichiers statiques versionnés. Chaque entrée porte une
date et la nature exacte de la vérification : **documentation publique lue**, jamais
« exécuté » ni « audité ».

- MCP (`apps/api/src/acp_api/mcp/catalog.json`, 3 entrées) : `context7` et
  `github-remote` en transport `http` avec le secret d'en-tête attendu, `filesystem` en
  `stdio` avec un paquet épinglé, le prérequis Node sur le runner et le risque d'accès
  disque.
- Skills (`apps/api/src/acp_api/skills/catalog.json`, 4 entrées) : dépôts
  `anthropics/skills`, `openai/skills`, `huggingface/skills` et `NVIDIA/skills`, cités
  par la documentation Hermes comme sources GitHub de confiance par défaut. Leur
  contenu n'est pas audité par la plateforme, et chaque entrée rappelle d'épingler un
  commit avant installation.

Sélectionner une entrée de catalogue pré-remplit un formulaire et liste les secrets
requis. Cela ne crée rien : la déclaration, le diagnostic et l'activation suivent le
parcours normal.

## Écrans web et commandes CLI

Les deux surfaces utilisent la même API, les mêmes contrats et le même modèle de
session ; aucun contrôle n'existe seulement dans l'interface.

**Web** — deux routes du shell :

- « Connexions » rend le centre MCP et le panneau des secrets : liste des serveurs avec
  état, transport, lieu d'exécution et fraîcheur de la découverte ; formulaire d'ajout
  (valeur littérale ou référence de secret, runner cible pour `stdio`) ; catalogue ;
  détail avec configuration masquée, outils découverts et cases à cocher par projet,
  révisions et diff, autorisations en attente (action, cible, conséquences, portée,
  expiration) avec Approuver/Refuser, activation, désactivation, révocation avec raison
  obligatoire, export copiable et import avec aperçu.
- « Bibliothèque » rend la bibliothèque de skills : recherche des installés et du
  catalogue, import par onglets (SKILL.md, archive, dossier autorisé, GitHub), détail
  avec frontmatter, licence, badge « plugin natif : non sandboxé », dépendances,
  findings marqués indicatifs, arborescence et visionneuse en texte brut, révisions,
  approbation, rollback, rattachements et révocation.

Les états chargement, vide, erreur, hors ligne, refus (`403` ⇒ « réservé au
propriétaire ») et non configuré (coffre absent ⇒ formulaires de secret désactivés avec
l'action à effectuer) sont distincts. Le shell fournit son client HTTP et son jeton
CSRF aux deux modules : un seul jeton CSRF est en circulation.

**CLI** — trois groupes, décrits en détail dans
[Missions, runner local et CLI](missions-and-cli.md) et `apps/cli/README.md` :

```text
acp secrets status | list | set NAME --value-stdin | rotate ID --value-stdin | revoke ID
acp mcp catalog | add | list | show | tools | update | test [--wait] | probes … | bind
acp mcp bindings | unbind | activate | disable | revoke --reason | rollback | export | import
acp skills search | catalog | list | show | files | cat | install | update | approve
acp skills activate | disable | revoke --reason | rollback | bind | bindings | unbind
acp projects extensions PROJECT_ID
```

Une valeur de secret n'est jamais acceptée en argument : seule l'entrée standard est
lue. `acp mcp import` lit le fichier localement et n'envoie que son contenu ; le serveur
ne lit jamais un chemin fourni par le client.

## Droits

| Action | Exigence |
|---|---|
| lire le catalogue, les serveurs, les skills, les diagnostics | session authentifiée |
| voir les rattachements d'un serveur ou d'un skill | accès au projet concerné (les autres sont masqués ; le compteur reste global) |
| créer, réviser, diagnostiquer, activer, désactiver, révoquer, approuver | propriétaire de la plateforme |
| créer ou supprimer un rattachement | membre du projet visé, ou propriétaire |
| créer, tourner, révoquer un secret | propriétaire ; portée `project` limitée à son projet |
| réclamer un lancement stdio | runner authentifié, non simulé, capacité `mcp_stdio_probe`, probe approuvé et non expiré |

Les mutations web exigent le jeton CSRF. Les contenus importés (configurations,
`SKILL.md`, schémas d'outils) sont des données : ils n'altèrent jamais une politique,
un droit ni une instruction système.

## Ce qui reste hors périmètre

- Aucun serveur MCP **tiers**, dépôt GitHub réel ou runner distant réel n'a été
  contacté : les preuves reposent sur `httpx.MockTransport`, un résolveur DNS injecté,
  un serveur MCP stdio déterministe local et un serveur MCP Streamable HTTP écrit pour
  la vérification, lancé sur le bouclage.
- L'autorisation d'un lancement `stdio` n'est pas reliée au circuit d'approbation des
  missions : ce sont deux mécanismes distincts, avec des journaux distincts.
- Le probe stdio s'exécute avec les droits OS du compte worker : ce n'est pas une
  sandbox, seulement un lancement borné et autorisé.
- Les skills sont stockés sur le système de fichiers local (`ACP_SKILLS_STORAGE_DIR`) :
  pas de stockage privé partagé, d'URL signée ni de rétention.
- Un plugin natif n'est pas isolé ; l'interface l'affiche, elle ne le sécurise pas.
- Aucun appel d'outil MCP n'est encore exécuté par une mission : le Lot D livre le
  registre, la découverte, l'autorisation et la résolution des extensions, pas le
  courtier d'appels à l'exécution.
- Le contrôle automatique des skills est indicatif ; il ne remplace pas une relecture.

## Correspondance avec les critères d'acceptation

Les scénarios 7 (MCP), 8 (skills) et 9 (refus d'une action non autorisée) sont
couverts de bout en bout par des tests locaux : `apps/api/tests/test_mcp_servers.py`,
`test_mcp_client.py`, `test_mcp_importers.py`, `test_skills.py`, `test_extensions.py`,
`test_secrets.py`, `test_outbound_policy.py`, `apps/worker/tests/test_mcp_probe.py`,
`apps/cli/tests/test_cli_mcp_skills.py` et les tests Vitest `mcp-*`/`skills-*`.

Le scénario 7 a de plus été rejoué contre des services réellement démarrés — API métier
dans son propre processus, serveur MCP Streamable HTTP sur le bouclage inscrit dans
l'allowlist auditée — avec 24 étapes sur 24 réussies. Le statut retenu dans
`docs/acceptance-report.md` reste **Partiel** : le script de ce parcours n'est pas
versionné dans le dépôt, il ne couvre que le transport `http`, et aucun serveur MCP
tiers n'a été raccordé.
