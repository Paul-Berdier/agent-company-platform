# P8 — Station de travail Qt rebranchée sur Hermes

État du 2 octobre 2026. Étape P8 du [plan d'autonomie](autonomie.md) (§ 8, volet desktop),
branche `refonte/hermes-p8`, partie de `refonte/hermes` (`b3faac0`, P0 à P5 fusionnées).
**Réalisée côté dépôt, poussée, sans PR ni fusion ; rien n'est déployé.** Version 0.11.0
inchangée.

Guides : [architecture](../native-desktop-architecture.md),
[sécurité](../desktop-security.md), [construction et bout en bout](../desktop-build.md).
Preuves datées et identifiants des runs : [`reprise-poste.md`](../reprise-poste.md),
§ 6 sexies.

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
| Desktop CI verte sur windows-2022 | **faite** à chaque morceau poussé | runs dans `reprise-poste.md` |
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
- **Flux SSE du greffon** : aucun contrat de flux n'est fusionné ; la station n'ouvre rien
  et affiche « Non disponible sur ce serveur (étape P7) ». `SseParser` est gardé pour lui.
- **Test de contrat des documents de référence** : prévu dans
  `hermes/tests/contrat/test_fixtures_desktop.py` et `image.yml` ; fait à la place dans le
  bout en bout local (lecture en porteur, comparaison de forme de 9 documents), pour ne pas
  toucher `image.yml`, que P6 et P7 modifient aussi. Il n'est donc pas en CI.
- **Quotas** : `SubscriptionQuotasViewModel` (ancienne route) retiré puis réécrit en
  `QuotasViewModel` sur `/v1/quotas`.
- **Demandes de l'agent** : seules celles des discussions ouvertes dans la station sont
  affichées ; l'agrégat de toutes les sessions vivantes attend P7.
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
[`reprise-poste.md`](../reprise-poste.md), § 6 sexies).

## Non prouvé

- Aucun essai contre Railway ni avec une vraie passkey (rien n'est déployé).
- Navigateur du système réel (Chromium de Playwright le remplace au bout en bout).
- Installation sur un Windows propre ; signature.
- Gestes des revues de P6, flux SSE et agrégat des demandes de P7 (contrats non fusionnés).
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
