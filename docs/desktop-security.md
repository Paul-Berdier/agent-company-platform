# Sécurité du client desktop natif (station de travail)

État du 2 octobre 2026, version **0.11.0**, étape **P8** de la refonte « Hermes au centre »
(branche `refonte/hermes-p8`, non fusionnée). Ce document décrit le code, ses frontières
et ses limites ; il n'est ni une certification ni une revue de sécurité indépendante.
Architecture : [`native-desktop-architecture.md`](native-desktop-architecture.md).

## Frontière de confiance

La station appelle seulement les API de Hermes (connexion native, tableau de bord en
porteur, JSON-RPC `/api/ws`, veille du kanban, façade du greffon `acp-poste`). Hermes et
son greffon décident de tout refus ; la station affiche le refus tel quel, en français
quand le message est connu. Elle ne parle jamais au fournisseur d'identité, ni au poste
Windows, ni aux fichiers, à la base ou aux secrets du serveur. Les textes servis sont des
données affichées en texte brut (`Text.PlainText`) ; les appels d'outils de l'agent sont
résumés sans leurs arguments ni leur sortie brute.

## Où vit chaque secret

| Secret | Où | Durée |
|---|---|---|
| Jeton d'accès (ID token RS256 d'Authelia) | mémoire de `SessionHermes` seulement ; posé sur la requête au moment de l'envoi puis effacé ; jamais en propriété QML ni dans une requête conservée | 1 h |
| Jeton de rafraîchissement | Gestionnaire d'identifiants Windows, entrée `AgentCompanyPlatform:hermes.rt.v1.<sha256 du serveur canonique>`, **seulement** si « Mémoriser la connexion sur ce poste » est coché (décoché par défaut) ; sinon mémoire seulement | 7 jours chez Authelia |
| Vérificateur PKCE, état, code de rappel | mémoire de `NativeAuthFlow`, effacés à la fin du flux | ≤ 600 s |
| Ticket de WebSocket | variable locale le temps d'une ouverture, en sous-protocole (jamais dans l'URL) | 30 s, usage unique |
| Code d'enrôlement du poste | mémoire de la page Poste, affiché une fois ; effacé en quittant la page, à la perte de session (même fenêtre réduite) et à l'expiration | 10 min |
| Archive de sauvegarde (`.env`, `auth.json`) | jamais en clair sur le disque du PC : chiffrée au fil de l'eau (DPAPI, `ACPB1`) | jusqu'à suppression |

L'entrée du coffre (`ACPH`, version 1) porte serveur canonique, fournisseur, identifiant
et jeton, bornée à 2 560 octets (refus au-delà, jamais de troncature) ; relue, elle doit
viser le serveur configuré et le fournisseur `self-hosted`, sinon elle est effacée.
Changer de serveur purge l'entrée de l'ancien. Hors Windows, le coffre refuse : aucun
fichier en clair de remplacement.

## Connexion et rotation

- PKCE S256, état comparé à temps constant ; un état faux abandonne le flux (échec
  fermé). L'écouteur n'accepte que `127.0.0.1` ; Hermes refuse de toute façon une
  adresse de retour non locale.
- Rotation : nouveau jeton **écrit au coffre avant usage** ; un seul rafraîchissement en
  vol dans le processus ; une seule station par session Windows (`QLockFile`, code de
  sortie 3 au second lancement), pour qu'aucun jeton ne soit rejoué par deux processus.
- 503 au rafraîchissement : ambigu (fournisseur injoignable ou jeton rejoué) ; le jeton
  est gardé, aucun effacement automatique ; message après trois échecs consécutifs sur au
  moins deux minutes.
- Réponse 200 au rafraîchissement refusée par la station (fournisseur, identité, type de
  jeton, échéance) : Hermes a déjà fait tourner le jeton, celui du coffre est donc
  consommé ; l'entrée est **effacée** et l'écran demande de se reconnecter, pour qu'aucun
  jeton consommé ne soit rejoué au démarrage suivant (Authelia révoquerait toute la
  famille). L'échéance d'un jeton est jugée contre l'en-tête `Date` de Hermes, pas contre
  l'horloge du poste : une horloge en avance de plus d'une heure ne fait plus refuser une
  connexion ni une rotation (`tst_session_hermes`).
- Déconnexion : révocation demandée à Hermes (`POST /auth/logout` avec le cookie
  `hermes_session_rt`), puis oubli local complet, quoi que réponde le serveur ; le bilan
  de la demande est affiché dans les réglages et les diagnostics.
- Oubli local complet : à la session perdue (déconnexion, jeton refusé) et au changement
  de serveur, chaque page (`PageViewModel::oublier`) vide ses modèles, revient à « Jamais
  lu », abandonne ses lectures en vol et efface ses brouillons (réponses, consignes,
  routage, code d'enrôlement, rapport d'export) ; le résumé de la barre d'état redevient
  « Inconnu », la passerelle et la veille du kanban se ferment. Aucune ligne d'un serveur
  n'est affichée sous un autre (`tst_oubli_local`). Un greffon bloqué par le verdict de
  compatibilité fait de même oublier ses pages.

Bout en bout local du 2 octobre 2026 : après la déconnexion, le rejeu de l'ancien jeton
de rafraîchissement obtient **503** (« Auth provider 'self-hosted' unreachable » : Authelia
rend 500 pour un jeton révoqué, identite.md § 12.1). La révocation est donc effective,
mais indiscernable d'une panne du fournisseur pour le client.

## Transport

HTTPS exigé ; HTTP seulement en bouclage, sur autorisation explicite. Aucune redirection
suivie. Aucun cookie stocké (pot refusant) ; le seul cookie émis est celui de la
déconnexion. Aucun proxy implicite, et la même règle pour les WebSockets que pour le
REST. Aucun en-tête `Origin` sur les WebSockets (client natif ; la garde de Hermes ne
l'exige que s'il est présent). Corps d'écriture bornés à 64 Kio ; lecture d'archive
bornée à 4 Gio.

## Préférences (`QSettings`)

`SettingsStore` n'accepte qu'une liste blanche de clés (adresse du serveur, bouclage
autorisé, thème, mouvement, consentement de mémorisation, largeurs et repli des volets).
Les Diagnostics **contrôlent** ce qui est réellement présent : toutes les clés sont
énumérées, et une clé hors liste ou une valeur qui ressemble à un jeton (formes reconnues
par le filtre d'expurgation) est signalée par son **nom**, jamais par sa valeur.

## Journaux, rapports, écran

`redactSecrets` (filtre de `main.cpp`, rapport des diagnostics, journal des actions de
Hermes affiché par la page Sauvegarde) remplace : paramètres `token`, `code`, `state`,
`ticket`, `code_verifier` d'une URL ; en-têtes `Authorization`, `Cookie`, `Set-Cookie`,
`Sec-WebSocket-Protocol` ; jetons `Bearer`, JWT, jetons opaques d'Authelia, sous-protocole
`hermes-gateway-ticket.…`, cookies de session de Hermes, jeton de machine `acpm_…` et
code d'enrôlement `acpe_…` ; champs JSON sensibles. Toute valeur **affichée** par les
Diagnostics passe aussi par ce filtre (une alerte du serveur qui contiendrait un jeton
est expurgée à l'écran comme au rapport). Limite dite : le filtre ne reconnaît pas un
secret arbitraire ; la première protection reste de ne rien journaliser de secret.

## Sauvegarde

Format `ACPB1`, DPAPI de l'utilisateur courant (`CryptProtectData`), morceaux de 1 Mio,
entropie liée à l'identifiant d'export, au rang et au drapeau final : altération,
troncature, permutation, greffe d'une autre sauvegarde et octets en trop sont refusés.
`tst_sauvegarde` vérifie qu'aucun fichier du dossier de destination ne contient
l'octet-témoin de l'archive en clair. Limites : la sauvegarde est perdue avec le profil
Windows (la sauvegarde du volume Railway reste la principale) ; « Déchiffrer » écrit
l'archive **en clair** à l'endroit choisi, après un avertissement.

## Injections d'essai

Le produit n'a aucune option d'essai. Seul l'exécutable `acp_desktop_e2e` (compilé avec
les tests, jamais installé ni déclaré à CTest) accepte un préfixe de coffre, une portée de
préférences, un mandataire et une autorité **de test** ; il refuse de démarrer sans
`--coffre AcpDesktopE2E-…` et `--portee "ACP E2E …"`. L'empaquetage ne prend que
`AgentCompanyPlatform.exe`.

## Preuves

- `tst_pkce`, `tst_flux_natif`, `tst_session_hermes`, `tst_jetons_coffre` (aller-retour
  réel dans le coffre Windows), `tst_instance_unique`, `tst_api_porteur`,
  `tst_canal_jsonrpc`, `tst_client_passerelle`, `tst_reglages_sans_secret`,
  `tst_redaction`, `tst_diagnostics`, `tst_sauvegarde`, `tst_oubli_local`, `tst_pages_bureau` (aucune
  propriété d'aucun objet ne contient le jeton ni un ticket après le parcours).
- Bout en bout local : aucune forme de secret dans le journal de la station, l'export du
  registre de la portée de test, le journal du bord ni celui de Hermes ; entrée de coffre
  de test absente à la fin ; aucune connexion de la station hors de la pile ni vers le
  fournisseur d'identité ([`desktop-build.md`](desktop-build.md), § 12).

## Limites ouvertes

Aucune signature de code ; aucune installation sur un Windows propre ; aucun essai contre
Railway ni avec une vraie passkey (rien n'est déployé) ; fenêtre de 30 s entre la rotation
chez le fournisseur et l'écriture au coffre (au-delà, reconnexion) ; aucune revue de
sécurité indépendante de l'étape P8 à ce jour.
