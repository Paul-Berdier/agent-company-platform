# Rapport d'acceptation

Date d'état : 11 septembre 2026
Périmètre évalué : candidat de release local du Lot C `0.4.0`, sans service
externe ni dépense réelle. La publication GitHub — PR, CI distante et tag — n'a
pas encore été effectuée.

## Verdict

**0 scénario sur 20 est encore accepté de bout en bout.** Onze scénarios disposent
d'une brique réelle et de tests ciblés ; neuf restent non satisfaits. Le Lot C rend
la mission, le processus local et le CLI testables, mais un programme déterministe
de test n'est pas une exécution Hermes réelle, et un cwd dédié n'est pas une sandbox.

Statuts : **Accepté** exige le parcours complet et reproductible ; **Partiel**
signifie qu'une brique réelle existe mais qu'un élément bloquant manque ; **Non
satisfait** signifie que le parcours principal n'est pas livré.

## Matrice des vingt scénarios

| # | Scénario | Statut | Preuve disponible et manque bloquant |
|---:|---|---|---|
| 1 | Première connexion sécurisée et reconnexion | **Partiel** | Bootstrap unique, Argon2id, session révocable/expirable, cookie `HttpOnly`, CSRF, restauration web et login CLI sont testés. Pas d'E2E navigateur sur services démarrés. |
| 2 | Connexion Hermes avec diagnostic d'échec exploitable | **Partiel** | Diagnostic typé et frontière serveur testés avec transports simulés. Aucune instance ni clé Hermes réelle. |
| 3 | Conversation persistante et reprise depuis web/CLI | **Partiel** | Conversations et tours sont persistés ; web et CLI reprennent par `GET`. Pas de streaming ni E2E Hermes réel. |
| 4 | Import d'un projet sans écrasement du travail existant | **Non satisfait** | Création de projet disponible, mais pas d'import de dépôt/dossier ni test produit de conflit. |
| 5 | Mission réellement exécutée par au moins un agent configuré | **Partiel** | Le worker lance un vrai processus local configuré, produit une preuve et échoue fermé. Seuls des programmes déterministes de test ont été lancés, pas un agent réel. |
| 6 | Isolation des fichiers, secrets et contexte entre deux projets | **Partiel** | RBAC et conversations inter-projets sont testés ; le runner filtre son enveloppe et son environnement. Pas de sandbox OS, coffre ou stockage privé. |
| 7 | Ajout, test, activation et révocation d'un MCP | **Non satisfait** | Reporté au Lot D. |
| 8 | Import d'un skill, affichage des fichiers et activation limitée | **Non satisfait** | Reporté au Lot D. |
| 9 | Refus d'une installation ou d'une action non autorisée | **Partiel** | CSRF/RBAC et frontières worker sont testés ; le runner local refuse avant spawn les autonomies non garanties. Pas encore de parcours MCP/skill. |
| 10 | Tests web avec résultat structuré et capture de la session réelle | **Non satisfait** | Reporté au Lot E ; les captures du shell ne sont pas une session Playwright observée. |
| 11 | Consultation d'une trace et d'une capture après échec | **Non satisfait** | Reporté au Lot E. |
| 12 | Déconnexion/reconnexion sans perte d'historique ni double lancement | **Partiel** | Idempotence durable des conversations et missions, commandes liées aux tentatives et reprise par lecture sont testées. Pas d'E2E de coupure réelle ni d'outbox. |
| 13 | Approbation, refus, expiration et arrêt réel d'une exécution | **Partiel** | Acceptation/refus, empreinte et expiration d'approbation, stop et arrêt d'arbre sont couverts. Le runner local refuse les actions nécessitant approbation au lieu de les demander. |
| 14 | Runner perdu puis reprise contrôlée sans double effet | **Partiel** | Lease, fencing, worker obsolète, interruption et nouvelle tentative sont testés. Aucun effet tiers réel ne permet de prouver l'absence de double effet externe. |
| 15 | Routine planifiée sans doublon et fuseau Europe/Paris | **Non satisfait** | Reporté au Lot F. |
| 16 | Livrable téléchargeable et aperçu 3D réel | **Non satisfait** | Métadonnées de preuve seulement ; reporté aux Lots E/G. |
| 17 | Génération d'image réelle si backend configuré | **Non satisfait** | Reporté au Lot G. |
| 18 | Budget atteint, fournisseur indisponible et stockage saturé | **Partiel** | Durée globale et panne provider échouent fermées ; coûts/tokens, appels outils et saturation ne sont pas encore appliqués de bout en bout. |
| 19 | Authentification des médias, événements et fichiers privés | **Partiel** | Écritures worker et ingestion d'événements sont authentifiées ; WebSocket anonyme fermé. Pas encore de média/fichier privé ou flux utilisateur. |
| 20 | Sauvegarde/restauration et migration de données existantes | **Non satisfait** | Upgrade SQLite ad hoc et non versionné, avec reconstruction contrôlée de tables et sauvegarde préalable requise ; PostgreSQL versionné et restauration reportés au Lot H. |

## Preuves de tests du candidat de release

Les résultats ci-dessous proviennent d'un worktree détaché au commit de code
`5ff6aa78a232a721ae14353e907baefc548b4ccb`, arbre Git
`e697087938aa7ba0247b39cf00b4a3ed9266fcb7`, sans les modifications
Pixel/LimeZu locales non commitées.

Environnement : Windows `10.0.19045`, Python `3.12.14`, Node.js `v24.19.0` et
npm `11.17.0`.

| Commande ou suite | Résultat | Ce que cela prouve | Limite |
|---|---:|---|---|
| `python -m pytest -q` | **323/323 réussis ; 2 avertissements de dépréciation connus** | API, worker, CLI, services et contrats Python | pas de service externe |
| tests worker et CLI | **192/192 réussis** (`122` worker, `70` CLI) | processus réel, arrêt, deadline, fencing, client CLI, origines et idempotence | programmes et transports de test |
| `npm run test:web` | **29/29 réussis** | clients et logique du shell moderne | pas de navigateur réel |
| `npm run test:engine` | **74/74 réussis** | non-régression du moteur legacy versionné | mode legacy hors parcours principal |
| `npm exec tsc -- --noEmit -p apps/web/tsconfig.json` | **réussi** | cohérence TypeScript | pas le comportement runtime |
| `npm run build:web` | **réussi** | bundle Vite productible | pas un déploiement |
| `python scripts/check_version.py` | **réussi ; versions publiables synchronisées sur `0.4.0`** | cohérence du versionnage | pas le contenu du futur tag |
| `bash -n scripts/setup.sh scripts/dev.sh` | **réussi** | syntaxe des scripts POSIX | pas leur exécution sur chaque distribution |
| `git ls-files --eol scripts/setup.sh scripts/dev.sh` | **index et worktree en LF** | fins de ligne compatibles POSIX | pas le comportement runtime |

Les deux avertissements Python proviennent de dépréciations Starlette/AnyIO dans
les dépendances et sont non bloquants. Le build Vite termine avec les avertissements
attendus sur six ressources LimeZu sous licence absentes localement et sur la taille
du chunk Phaser ; ils ne constituent pas des échecs de compilation.

Ces preuves sont locales. Aucune PR du Lot C, CI distante ni tag `v0.4.0` n'est
encore créé ou publié.

## Vérifications explicitement non exécutées

- instance, modèle, mémoire, outils ou clé Hermes réels ;
- exécuteur Codex/Claude réel et effet externe sur un dépôt utilisateur ;
- E2E navigateur du bootstrap, d'une conversation ou d'une mission ;
- PostgreSQL existant, migration versionnée, sauvegarde ou restauration ;
- sandbox OS/réseau, quotas CPU/mémoire/disque ou compte non privilégié dédié ;
- MCP, skill, Playwright, trace, stockage privé, média, 3D et automatisation ;
- Railway, HTTPS public, charge ou audit offensif.

## Conditions avant exposition réseau

- terminer la matrice RBAC sur chaque ressource enfant, flux et fichier ;
- ajouter migrations PostgreSQL, stockage privé, sauvegarde/restauration et rotation ;
- isoler le runner au niveau OS/réseau et raccorder un circuit d'approbation worker ;
- exécuter les scénarios E2E contre les services réellement démarrés ;
- activer les tests externes uniquement par opt-in, avec secrets et budgets bornés.
