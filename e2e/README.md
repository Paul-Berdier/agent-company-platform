# Parcours Playwright réel du shell et du Studio

Ce paquet lance un navigateur Chromium contre une plateforme **déjà démarrée**. Il ne
démarre aucun faux serveur, ne simule aucune réponse applicative et n'accepte aucune
donnée de démonstration. Le parcours se connecte par l'interface, vérifie le shell, ouvre
Missions puis le Studio d'une tentative existante en lecture seule.

## Désactivé par défaut

Depuis la racine du dépôt :

```text
npm run test:e2e
```

Sans `ACP_E2E=1`, le lanceur répond `[E2E SKIPPED]` avant de résoudre Playwright. Le
paquet `e2e` est volontairement hors des workspaces npm de la racine : `npm ci`, les
tests habituels et le build n'installent donc ni Playwright ni navigateur.

## Préparer une exécution réelle

L'installation est une action séparée et explicite :

```text
npm ci --prefix e2e
npm --prefix e2e run install:chromium
```

Le paquet fixe `@playwright/test` `1.63.0`. Sur une machine qui possède déjà Chrome ou
Edge, l'installation du Chromium Playwright peut être évitée en sélectionnant le canal
correspondant ; aucune détection silencieuse n'est effectuée.

Configurer ensuite toutes les variables suivantes dans l'environnement du processus :

| Variable | Rôle |
|---|---|
| `ACP_E2E` | doit valoir exactement `1` |
| `ACP_E2E_BASE_URL` | racine publique du shell, par exemple `https://staging.example.test` |
| `ACP_E2E_ALLOWED_ORIGIN` | confirmation exacte de l'origine du shell |
| `ACP_E2E_API_ORIGIN` | origine réellement appelée par le shell pour l'API |
| `ACP_E2E_LOGIN` | compte de test existant |
| `ACP_E2E_PASSWORD` | mot de passe du compte de test, 12 à 256 caractères |
| `ACP_E2E_RUN_ID` | tentative existante et accessible à ouvrir dans le Studio |
| `ACP_E2E_BROWSER_CHANNEL` | `chromium` par défaut, ou explicitement `chrome` / `msedge` |

Puis lancer `npm run test:e2e` depuis la racine. Le compte doit déjà exister, la
plateforme ne doit plus être en phase de bootstrap et le `run_id` doit appartenir à un
projet visible par ce compte. Le test ne crée, ne modifie et n'accepte aucune mission.

## Preuve locale isolée

Le lanceur versionné crée lui-même une base, une API, un shell Vite, un compte et une
mission temporaires sur deux ports de bouclage, puis appelle exactement le même paquet :

```powershell
$env:ACP_E2E="1"
$env:ACP_E2E_BROWSER_CHANNEL="msedge" # facultatif si Chromium est installé
./.venv/Scripts/python.exe scripts/verify_live_studio_journey.py
```

Sans l'opt-in exact, il répond lui aussi `[E2E SKIPPED]`. Il n'appelle aucun fournisseur
IA, ne contacte aucune cible distante et supprime ses données temporaires. Cette preuve
a réussi avec Edge pendant la validation de `0.8.0` ; elle ne produit volontairement ni
trace ni vidéo et ne prouve pas le rendu WebGL d'un GLB.

## Garde-fous

- `http://` est accepté uniquement pour `localhost`, `127.0.0.1` ou `[::1]` ; toute
  cible distante doit utiliser HTTPS avec validation normale du certificat ;
- les identifiants intégrés, sous-chemins, query strings, fragments, `0.0.0.0` et `[::]`
  sont refusés ;
- `ACP_E2E_ALLOWED_ORIGIN` doit confirmer exactement `ACP_E2E_BASE_URL` ;
- les requêtes HTTP(S) et connexions `ws:`/`wss:` vers une origine autre que le shell
  et l'API déclarés sont bloquées au niveau du contexte navigateur et font échouer le
  test, y compris la première navigation d'une popup ; toute nouvelle fenêtre est une
  violation. Les WebSockets autorisés sont transférés intégralement au vrai serveur,
  jamais simulés. Les service workers sont bloqués et les constructeurs `Worker`,
  `SharedWorker`, `WebTransport`, `RTCPeerConnection`, `webkitRTCPeerConnection` et
  `WebSocketStream` sont neutralisés avant tout script de page ou de frame : aucun de ces
  contextes/transports applicatifs ne peut sortir de la couverture HTTP/WebSocket.
  `EventSource` est également indisponible dans ce seul harnais : le Studio utilise son
  vrai repli HTTP par polling et aucune réponse HTTP infinie ne contourne le contrôle des
  redirections. Ce parcours ne constitue donc pas une preuve du direct SSE. Les schémas
  locaux du navigateur `about:`, `blob:` et `data:` restent autorisés, tandis que tout
  autre schéma réseau ou inconnu observé par Playwright est une violation. Cette
  frontière applicative ne remplace pas un pare-feu sortant du runner et ne prétend pas
  intercepter les optimisations spéculatives internes du navigateur ;
- avant de saisir les identifiants, une requête `OPTIONS` indépendante du routage du
  contexte interroge le vrai `/auth/login` avec les en-têtes exacts du préflight. Elle ne
  suit aucune redirection et exige un statut `2xx`, l'origine exacte, les credentials,
  `POST` et `Content-Type`. Playwright peut gérer le préflight du navigateur dans son
  propre contexte ; cette preuve serveur séparée empêche de prendre ce comportement
  pour une validation CORS. Lorsque web et API partagent la même origine, aucun
  préflight CORS n'est requis ;
- toute requête HTTP admise est envoyée une fois au vrai serveur par un
  `APIRequestContext` isolé, avec `maxRedirects=0`, `maxRetries=0` et une échéance de
  30 secondes, puis sa réponse non modifiée est remise au navigateur. Les en-têtes
  `Cookie` et `Authorization` transférés
  sont exactement ceux choisis par Chromium ; un cookie omis par sa politique
  `SameSite`/tiers n'est jamais réinjecté depuis le jar Node. `Set-Cookie` n'atteint le
  contexte navigateur que par la réponse remise. Un `3xx` n'est jamais présenté au
  navigateur : aucune seconde requête de redirection ne peut donc sortir de l'allowlist.
  Les réponses API cross-origin sont contrôlées avant que Playwright puisse compléter
  leurs en-têtes CORS ;
- exactement une tentative `POST /auth/login` est permise. Toute deuxième tentative ou
  autre mutation est bloquée avant envoi ; une réponse CORS incompatible est rejetée
  avant remise au navigateur. Chaque cas fait échouer la preuve. Après la connexion,
  seules `GET`, `HEAD` et `OPTIONS` restent permises ;
- les traces et vidéos sont désactivées pour ne pas conserver le corps de connexion ;
  seule une capture d'échec locale peut être écrite sous `e2e/.artifacts/`. Le parcours
  réel n'est jamais retenté automatiquement.

Une indisponibilité, une redirection inattendue, une session refusée, un contrat API
incompatible ou un `run_id` absent fait échouer le parcours. Le test exige la réponse
réelle de lecture de la mission, vérifie qu'elle contient exactement la tentative
configurée, attend le journal initial et refuse tout panneau d'erreur dans le Studio.
Aucun de ces cas n'est converti en succès ou en données synthétiques.

## CI opt-in

Le job `Playwright E2E (opt-in)` ne s'exécute que via `workflow_dispatch` sur
`refs/heads/main`, lorsque `vars.ACP_E2E == '1'`. Cette variable d'activation doit être
définie au niveau du dépôt (ou de l'organisation), car GitHub évalue la condition du
job avant de lui ouvrir l'environnement. Le job cible ensuite l'environnement dédié
`acp-e2e-staging` : les URL et le `run_id` viennent de ses variables d'environnement,
et `ACP_E2E_LOGIN` / `ACP_E2E_PASSWORD` de ses secrets d'environnement, injectés dans
la seule étape de test après checkout et installation. Avant d'y placer ces secrets,
configurer dans GitHub un reviewer requis et limiter les branches de déploiement à
`main` ; ces protections ne vivent pas dans le YAML. Aucun push ni aucune pull request,
issue d'un fork ou non, ne peut lancer ni interrompre ce job manuel.
