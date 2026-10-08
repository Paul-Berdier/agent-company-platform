# P8 — Station de travail Qt rebranchée sur Hermes

État du 2 octobre 2026. Étape P8 du [plan d'autonomie](autonomie.md) (§ 8, volet desktop),
branche `refonte/hermes-p8`, partie de `refonte/hermes` (`b3faac0`, P0 à P5 fusionnées).
**Réalisée côté dépôt, poussée, sans PR ni fusion ; rien n'est déployé.** Version 0.11.0
inchangée.

Guides : [architecture](../native-desktop-architecture.md),
[sécurité](../desktop-security.md), [construction et bout en bout](../desktop-build.md).
Preuves datées et identifiants des runs : [`historique.md`](historique.md),
partie B, § 6 decies.

## Ce qui est livré

- **Connexion native RFC 8252** contre le fournisseur `self-hosted` de Hermes (Authelia) :
  PKCE S256, état, écouteur `127.0.0.1` à port éphémère, échange, identité ; jeton de
  rafraîchissement au coffre Windows sur consentement (décoché par défaut), rotation
  écrite au coffre avant usage, une seule station par session Windows ; déconnexion avec
  révocation demandée à Hermes. `AuthManager`, le cookie `acp_session` et les pages de
  l'ancienne API sont retirés.
- **Porteur** sur les API du tableau de bord et la façade `acp-poste` (`ClientGreffonPoste`) ;
  **compatibilité** par `/v1/meta` (contrat, OpenRPC épinglé, Hermes testé, alertes,
  exécutant P6 s'il est annoncé) ; **santé** par `/api/health` et `/api/status`.
- **JSON-RPC** sur `/api/ws` (`JsonRpcChannel`, `GatewayClient`) : ticket en sous-protocole,
  sans `Origin`, rejeu après coupure, **-32601** pour toute requête serveur non gérée,
  réponses `approval`/`clarify` avec les seuls choix offerts.
- **Temps réel** (`EventStreamService`) : sondage des pages affichées, sondage léger de la
  barre d'état, veille du kanban qui relit le projet ouvert.
- **Pages** : Accueil, Projets, Questions, Discussion, Poste, Quotas, Routage, Diagnostics,
  Sauvegarde (export chiffré DPAPI `ACPB1`, archive retirée du volume), Réglages.
- **Qt WebSockets** dans la chaîne d'outils, CMake et la Desktop CI.

## Preuves exigées par le plan, et leur état

| Exigence | État | Où |
|---|---|---|
| Tests Qt : PKCE, `state`, redirection `127.0.0.1`, rotation du jeton, -32601 | **faits** | `tst_pkce`, `tst_flux_natif`, `tst_session_hermes`, `tst_canal_jsonrpc` |
| Réponse à une question depuis le desktop | **faite, en local** : question posée par le poste simulé, réponse tapée dans le champ de la carte et envoyée par un clic réel sur « Répondre » de la page Questions, relue fermée par l'API | bout en bout local du 02/10/2026 (images `p8` et `rv8p6`), `tst_pages_interactions` |
| `QSettings` sans jeton | **fait** : test du registre de préférences après un parcours complet, contrôle des préférences dans les Diagnostics, export du registre de la portée de test balayé au bout en bout | `tst_reglages_sans_secret`, `tst_diagnostics`, bout en bout |
| Desktop CI verte sur windows-2022 | **faite** à chaque morceau poussé | runs dans `historique.md`, partie B |
| Installeur non signé, dit explicitement | **dit** : aucun certificat ; l'empaquetage à blanc de la CI le produit non signé | `desktop-release-process.md` |
| Connexion réelle à Railway, VM Windows propre | **non faites** : rien n'est déployé, aucune VM sur ce poste | — |

## Décisions appliquées

Le cahier proposait douze décisions (D8-1 à D8-12) ; leurs recommandations sont appliquées,
conformément à la règle « Hermes décide de l'exploitation, le propriétaire fournit les
comptes et tranche l'irréversible » :

| N° | Décision appliquée |
|---|---|
| D8-1 | Qt WebSockets (LGPLv3) ajouté : seule voie native pour `/api/ws` |
| D8-2 | « Mémoriser la connexion » décoché par défaut |
| D8-3 | Déconnexion par `POST /auth/logout` avec le cookie `hermes_session_rt` |
| D8-4 | Veille par le WebSocket interne du kanban, comme simple signal ; sondage gardé |
| D8-5 | Sur 503 au rafraîchissement, le jeton est gardé, jamais effacé automatiquement |
| D8-6 | Routage : validation, relevé et surcharges dans la station ; édition complète dans le navigateur |
| D8-7 | Sauvegarde au format `ACPB1` (DPAPI par morceaux), suppression de l'archive par `DELETE /api/files` |
| D8-8 | Revues de P6 en lecture seule tant que P6 n'est pas fusionnée |
| D8-9 | Discussion sans choix de modèle ni de profil (défaut du profil) |
| D8-10 | Bout en bout local seulement |
| D8-11 | MCP côté exécutant après la fusion de P6, hors de cette branche |
| D8-12 | Binaires non signés tant qu'aucun certificat n'existe, dit partout |

## Écarts au cahier, justifiés

- **MCP côté poste** (volet P8 du plan d'autonomie) : non construit ici ; il dépend des
  fichiers de P6 (`executant/`, `apps/poste`) que cette branche ne modifie pas (D8-11).
- **Flux SSE du greffon** : la station ne l'ouvre pas et relit ses pages par sondage ;
  `SseParser` est gardé pour lui. Depuis la relecture finale de P7, le diagnostic dit ce que
  `/v1/meta` annonce (clé `flux`) : « Annoncé par le serveur ; non utilisé par cette
  station », « Non disponible sur ce serveur » (clé absente), ou « Inconnu » tant que rien
  n'est lu — jamais une étape à venir.
- **Test de contrat des documents de référence** : prévu dans
  `hermes/tests/contrat/test_fixtures_desktop.py` et `image.yml` ; fait à la place dans le
  bout en bout local (lecture en porteur, comparaison de forme de 9 documents), pour ne pas
  toucher `image.yml`, que P6 et P7 modifient aussi. Il n'est donc pas en CI.
- **Quotas** : `SubscriptionQuotasViewModel` (ancienne route) retiré puis réécrit en
  `QuotasViewModel` sur `/v1/quotas`.
- **Demandes de l'agent** : seules celles des discussions ouvertes dans la station sont
  affichées ; l'agrégat de toutes les sessions vivantes, servi depuis P7 (section
  `discussions` de `GET /v1/questions`, `session.active_list`), n'est pas lu par la station,
  qui le dit (« la page Questions du navigateur les compte »).
- **`session.close`** : envoyé seulement pour une session sans tour en cours, pour ne
  jamais interrompre un travail de l'agent.
- **Proxy des WebSockets** : ils prennent désormais la même règle que le REST (aucun proxy
  implicite par défaut) ; auparavant forcés sans proxy.
- **Bout en bout** : la station y est un exécutable de test (`acp_desktop_e2e`) qui pilote
  la vraie application, avec un mandataire CONNECT local et Chromium à la place du
  navigateur du système ; le cahier ne précisait pas le mandataire.

## Corrections après relecture (2 octobre 2026)

Seize constats d'une relecture indépendante (exactitude, sécurité, produit), chacun corrigé
avec un test qui échoue sans la correction (témoin de mutation relevé), par petits commits
poussés :

| Constat (gravité) | Correction | Commit |
|---|---|---|
| Texte d'une réponse ou d'une consigne effacé à chaque relecture de 15 s et après un envoi refusé (critique) | listes mises à jour par identifiant (`JsonListModel::setCle`) ; brouillons gardés par la page, effacés seulement après réussite | `7b82c7c` |
| Liste des projets remontée en haut à chaque relecture (moyenne) | même correction | `7b82c7c` |
| Verdict « contrat d'une autre majeure » ou greffon absent non appliqué (haute) | client du greffon **bloqué** : toute route refusée localement, sans rien émettre, sauf `/v1/meta` | `54714ab` |
| Guide d'architecture : empreinte OpenRPC dite coupante (basse) | guide corrigé : seule la version d'information coupe la Discussion | `54714ab` |
| Données d'un autre serveur gardées ; déconnexion sans oubli des pages (moyenne) | `PageViewModel::oublier()` à la session perdue, au changement de serveur et au blocage du greffon | `ee70e9f` |
| Rotation acceptée par Hermes mais refusée par la station : jeton consommé gardé au coffre (moyenne, sécurité) | entrée effacée ; échéance jugée contre l'en-tête `Date` de Hermes | `da7081a` |
| `machine.executant = null` (P6 en place) confondu avec l'étape absente (moyenne) | cinq états exacts (annoncé, aucun connu, non déployé, base illisible, non lu) | `72f2a5b` |
| Liens du navigateur sans le préfixe de chemin du serveur (basse) | liens construits par `ApiClient::resolve` | `ba206b4` |
| Messages réseau anglais de Qt (moyenne) | libellés français fixes par code d'erreur | `4ac1de4` |
| Ctrl+6 à Ctrl+9 sans effet ; copie du rapport par la palette sans effet (moyenne) | un raccourci installé par raccourci déclaré ; rapport réellement copié | `c22c8b9` |
| Preuve de la réponse passant par le ViewModel (basse) | vrais champs et vrais boutons au bout en bout et dans `tst_pages_interactions` | `c22c8b9` |
| Carte « Hermes » de l'accueil jamais relue (moyenne) | `/v1/meta` relu avec la page, carte datée | `9c76c54` |
| « Cancel » dans le dialogue des réglages (basse) | boutons explicites en français | `de46e69` |
| Jauge des quotas inversée par rapport au web (basse) | part utilisée et repère du seuil, comme le web | `1f3696a` |

Preuves : 34 suites, totaux Qt sans échec ni test ignoré ; bout en bout local réussi
(0 écart) contre les images `p8` et `rv8p6` ; Desktop CI et CI vertes (runs dans
[`historique.md`](historique.md), partie B, § 6 decies).

## Non prouvé

- Aucun essai contre Railway ni avec une vraie passkey (rien n'est déployé).
- Navigateur du système réel (Chromium de Playwright le remplace au bout en bout).
- Installation sur un Windows propre ; signature.
- Gestes et lectures servis par P6 et P7 que la station n'emploie pas : les contrats sont
  désormais sur la branche (P6 fusionnée, P7 sur `refonte/hermes-p7`), mais ces gestes
  restent dans le navigateur, hors du périmètre de P7 (cahier P7 § 5.5 : « aucune
  dépendance ») : **Relancer** une carte arrêtée, **Qui répond**, **Clore le projet**,
  **Accepter / Refuser** une revue de fichiers de pilotage (la station renvoie au
  navigateur et le dit) ; ouverture du flux SSE ; Accueil agrégé `GET /v1/accueil`
  (« À traiter par vous », « Chez Hermes », canal de notifications : la carte Questions de
  l'Accueil de la station le dit) ; compteurs de `GET /v1/questions` (le badge Questions et
  la barre d'état comptent les questions ouvertes de `/v1/projets`, sans les décisions,
  revues ni cartes arrêtées) ; section des discussions en attente de la file ; visibilité
  mesurée des dépôts (`executant.depots`) : la page Poste n'en montre que les alias, et
  « Nouveau projet » propose Codex même pour un dépôt non prouvé privé, que le greffon
  refuse alors (`voie_fermee`, sans faux succès).
- Constats de la relecture finale de P7 corrigés dans la station : voies fermées de
  l'exécutant (objet `{voie: raison}` servi par le greffon, lu comme un tableau : toujours
  « Inconnu ») ; état d'une question d'après `chez` ; aide du plafond de corrections
  (prolongation refusée pour de bon par le greffon) ; titre de la carte de la machine
  d'après l'hôte publié ; textes qui promettaient des gestes « à l'étape P7 » ou
  renvoyaient au kanban de Hermes (qui débloquerait une carte sans les gardes d'ACP).
- Restauration d'une sauvegarde (étape P9) ; seul le déchiffrement à l'identique est prouvé.
- Durée réelle de la session chez Authelia (7 jours, fenêtre glissante supposée).
- Garde de transition du blocage du greffon (pages oubliées seulement au passage au
  blocage) : défensive ; son témoin ne boucle pas, le sondage se reprogrammant à 15 s.
- Écart d'horloge réel entre un poste et Railway : prouvé contre le faux Hermes (horloge du
  poste avancée de 2 h) et l'en-tête `Date` d'uvicorn au bout en bout local, pas sur Railway.
- Une réponse de `/auth/native/token` refusée par la station pour une autre raison que
  l'horloge (fournisseur, identité, type de jeton) laisse chez Authelia la session émise :
  aucune révocation n'est tentée.
- Avant le premier verdict de `/v1/meta` d'une session, les pages peuvent LIRE le greffon ;
  le blocage s'applique dès le verdict, et aucune écriture ne part sans geste.

## Commits

`530aa37`, `13f2428`, `b727da6`, `e216d6b`, `0543ae9`, `8d18f87`, `14b58f3`, `9761693`,
`3f7e56d`, `ed3735d`, `fc6c6e2`, `1987a84` (première partie : fondations) ; `22a2d90`,
`83101cf`, `22e4c42`, `9c44b7a`, `039aadb`, `857baae` (seconde partie : JSON-RPC, temps réel,
Accueil, Projets, Questions, Discussion) ; `6a068a5`, `b748194`, `b3b9e0f`, `75a73f6`,
`834a920`, `bfccf52`, `c66bc0b`, `aaf4242`, `1b28374`, `b68f645` et la documentation (troisième
partie : Poste, Quotas, Routage, Sauvegarde, Diagnostics, bout en bout) ; `7b82c7c`,
`54714ab`, `ee70e9f`, `da7081a`, `72f2a5b`, `ba206b4`, `4ac1de4`, `c22c8b9`, `9c76c54`,
`de46e69`, `1f3696a` et la documentation (corrections après relecture). Aucun
`Co-Authored-By`.
