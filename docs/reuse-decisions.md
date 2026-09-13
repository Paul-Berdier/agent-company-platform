# Décisions de réemploi

Vérification : 11 septembre 2026, complétée le 12 septembre 2026 pour le Lot D. Une
dépendance n'est ajoutée au produit qu'après épinglage dans un lock et vérification de
sa licence propre, de ses assets et des modèles qu'elle télécharge.

| Composant | Révision/surface évaluée | Licence du code | Maintenance | Décision et coût d'intégration |
|---|---|---|---|---|
| Hermes Agent | v0.21.1, tag `v2026.9.7` ; API Runs, sessions, jobs, skills/toolsets, dashboard et extensions | MIT | version publiée le 7 septembre 2026 | **Retenu comme runtime principal séparé.** Coût moyen : adaptateur, mapping d'identifiants, persistance SSE, auth de service et stockage natif Hermes |
| Dashboard Hermes | extensions drop-in, thèmes et plugins UI/backend | inclus dans Hermes (MIT) | même cycle que Hermes | **Non retenu comme shell principal.** Utilisable plus tard comme console native ; pas d'iframe ni de fork massif |
| Codex App Server | protocole JSON-RPC, stdio stable ; WebSocket documenté expérimental | composant open source Codex, licence à conserver avec la distribution choisie | surface générable depuis la version locale | **Retenu pour une future UX riche** (threads, événements, approbations). Pour les jobs simples, préférer le SDK. Aucun branchement produit dans le Lot A |
| Claude Agent SDK | sessions, outils, permissions et hooks officiels | à revérifier au moment de l'ajout du paquet | actif | **Retenu comme futur adaptateur**, pas comme orchestrateur Hermes. Coût moyen/fort : approbations, coût, reprise et sandbox |
| Playwright | reporter, screenshots, vidéos, trace viewer | Apache-2.0 | actif, multi-navigateur | **Retenu pour le Studio et les E2E.** Coût moyen : runner navigateur isolé, stockage privé des traces et normalisation des statuts |
| xterm.js | API terminal web 6.x | MIT | actif | **Retenu conditionnellement.** Seulement après création d'un PTY authentifié à contrôle exclusif. La documentation xterm rappelle qu'un terminal web expose les frappes et hérite des risques XSS |
| `<model-viewer>` | visualiseur glTF/GLB web | Apache-2.0 | actif | **Retenu pour l'aperçu 3D**, car plus petit et plus spécialisé que Three.js pour le besoin de base |
| Three.js | moteur 3D général | MIT, à revérifier lors du pin | actif | **Non retenu pour le premier aperçu.** À ajouter seulement si mesures, annotations ou rendu avancé dépassent model-viewer |
| ComfyUI | `/prompt`, `/ws`, historique, vues et interruption | GPL-3.0 | actif | **Connecteur de service optionnel**, jamais bibliothèque liée au cœur. Coût fort : auth réseau, files GPU, modèles/nœuds et licences de chaque workflow |
| noVNC | client VNC web | MPL-2.0, à revérifier lors du pin | actif | **Différé.** Pertinent uniquement pour un runner graphique isolé ; ce n'est pas un substitut au Studio Playwright |
| OpenHands | plateforme agentique complète | licence/version à réauditer si le besoin apparaît | actif | **Écarté pour l'instant.** Dupliquerait orchestration, UI et sandbox sans besoin démontré |
| Phaser/pixel-office-engine | Phaser 3.90.0 déjà verrouillé ; moteur local | Phaser MIT ; assets LimeZu sous licence distincte | existant | **Conservé derrière une fonctionnalité legacy désactivée.** Aucun chargement dans le parcours principal |

## Ajouts du Lot D

| Composant | Révision/surface évaluée | Licence | Maintenance | Décision et coût d'intégration |
|---|---|---|---|---|
| `cryptography` | Fernet et `MultiFernet` uniquement ; contrainte `>=45,<48`, version installée `47.0.0` | `Apache-2.0 OR BSD-3-Clause` (métadonnée du paquet) | projet PyCA, publications régulières | **Retenu pour le coffre de secrets.** Coût faible : chiffrement authentifié éprouvé plutôt qu'un montage maison. `MultiFernet` donne la rotation de clé sans perte. Plafond majeur épinglé pour ne pas subir une rupture d'API |
| `pyyaml` | `safe_load` du frontmatter d'un `SKILL.md` et `safe_dump` de l'export Hermes ; contrainte `>=6,<7`, version installée `6.0.3` | MIT | stable, largement diffusé | **Retenu.** Format imposé par Hermes et par `SKILL.md` : écrire un parseur maison serait un risque, pas une économie. `safe_load` exclusivement — jamais `load` — et entrée bornée avant analyse |
| MCP Streamable HTTP | spécification 2025-06-18 (et acceptation de 2025-03-26) : POST JSON-RPC sur un endpoint unique, `Mcp-Session-Id`, réponse `application/json` ou `text/event-stream`, `DELETE` de fin de session | spécification ouverte ; aucune dépendance ajoutée | révision datée | **Client minimal écrit dans le produit** plutôt qu'un SDK : la surface utilisée est petite (initialize, notifications/initialized, tools/list paginé) et doit passer par notre client à destination épinglée, ce qu'un SDK tiers ne ferait pas. L'ancien transport HTTP+SSE 2024-11-05 est refusé explicitement |
| Job Object Windows | `CreateJobObjectW`, `AssignProcessToJobObject`, `IsProcessInJob`, `TerminateJobObject`, `QueryInformationJobObject` via `ctypes` | API du système ; aucune dépendance ajoutée | API stable depuis Windows 8 / Server 2012 pour les jobs imbriqués | **Retenu comme clôture d'arrêt.** Seul mécanisme qui survit à la disparition d'un parent intermédiaire, contrairement à l'énumération par filiation. `ctypes` évite d'ajouter `pywin32` au worker. Limite assumée : c'est une clôture d'arrêt, pas un quota ni une sandbox, et il n'a pas d'équivalent POSIX livré |

Aucune autre dépendance n'a été ajoutée au Lot D : rien côté web, CLI ou worker.

## Ajouts du Lot E

| Composant | Révision/surface évaluée | Licence | Maintenance | Décision et coût d'intégration |
|---|---|---|---|---|
| Interface Reporter de Playwright | `onBegin`, `onTestBegin`, `onStepBegin`, `onStepEnd`, `onTestEnd`, `onError`, `onEnd` ; statuts `passed`/`failed`/`timedOut`/`skipped`/`interrupted`, `result.retry`, pièces jointes | Apache-2.0 (Playwright) ; **aucune dépendance ajoutée au dépôt** | projet actif, multi-navigateur | **Interface implémentée, paquet non ajouté.** `packages/playwright-reporter` implémente le contrat sans importer `@playwright/test` : la plateforme n'installe jamais Playwright et ne l'impose pas au dépôt. C'est l'opérateur qui l'installe sur son runner (≥ 1.44). Coût faible, et le dépôt reste installable sans navigateur. Limite assumée : sans le paquet, aucun typage n'est vérifié contre la vraie interface — la conformité repose sur des objets synthétiques, et **aucune exécution Playwright réelle ne l'a encore confirmée** |
| SSE (`text/event-stream`) plutôt qu'un WebSocket | corps SSE natif de Starlette/FastAPI, `EventSource` natif du navigateur avec `withCredentials`, `Last-Event-ID` | standard HTML ; aucune dépendance ajoutée | stable | **Retenu pour le flux utilisateur.** Un sens unique suffit (le Studio observe, il ne pilote pas), `EventSource` gère la reconnexion et `Last-Event-ID` donne la reprise par curseur sans protocole maison. Un WebSocket aurait imposé une couche d'authentification et de reprise à écrire ; le WebSocket anonyme du service d'événements reste fermé. Limite assumée : une rotation de connexion est nécessaire (`ACP_STREAM_MAX_SECONDS`) et le flux n'a jamais été consommé par un vrai navigateur |
| Tail de base par curseur plutôt qu'un courtier | interrogation bornée (`ACP_STREAM_POLL_INTERVAL_MS`) réveillée par un hub intra-processus | aucune dépendance ajoutée | — | **Retenu.** Redis ou un courtier auraient ajouté un service à exploiter et un second état à réconcilier ; ici la base reste la seule source de vérité, donc une reconnexion ne duplique ni ne perd, et plusieurs processus d'API peuvent servir la même tentative. Coût assumé : une latence nominale bornée par l'intervalle d'interrogation, documentée comme telle |
| Stockage disque adressé par contenu plutôt qu'un SDK S3 | `write` / `open` / `delete` / `exists`, écriture atomique par `os.replace` | aucune dépendance ajoutée | — | **Retenu pour ce lot.** L'interface `ArtifactStorage` est explicite pour accueillir un adaptateur objet ; l'ajouter maintenant aurait imposé une dépendance et un compte de stockage sans besoin démontré. Limite assumée : sur un hébergeur, ce répertoire exige un volume persistant, et **aucun adaptateur objet n'est livré** |
| HMAC-SHA256 de la bibliothèque standard plutôt qu'un JWT | `hmac` + `hashlib` + base64url, format `v1.<artifact_id>.<exp>.<sig>`, clés en liste pour la rotation | aucune dépendance ajoutée | — | **Retenu pour les liens de téléchargement.** Le jeton ne porte que trois champs et n'est jamais lu par un tiers : une bibliothèque JWT aurait apporté un format extensible, des algorithmes à exclure et une surface d'attaque, sans bénéfice. Le lien est en plus enregistré en base, donc révocable — ce qu'un JWT autoporteur ne permet pas |

Aucune dépendance runtime n'a été ajoutée au Lot E : ni en Python, ni côté web, CLI,
worker ou reporter. Le seul ajout au `package.json` racine est le workspace
`packages/playwright-reporter`, qui ne déclare aucune dépendance.

## Sources officielles consultées

- [Hermes API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
- [Extensions du dashboard Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard)
- [Releases Hermes](https://github.com/NousResearch/hermes-agent/releases)
- [Codex App Server](https://developers.openai.com/codex/app-server/)
- [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)
- [Playwright Trace Viewer](https://playwright.dev/docs/trace-viewer)
- [Sécurité xterm.js](https://xtermjs.org/docs/guides/security/)
- [model-viewer](https://modelviewer.dev/)
- [API serveur ComfyUI](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [Transports MCP — Streamable HTTP, révision 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [Job Objects Windows](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Fernet et MultiFernet (`cryptography`)](https://cryptography.io/en/latest/fernet/)

## Notices et contenu tiers

- Conserver les fichiers LICENSE/NOTICE exigés par chaque paquet distribué.
- Une licence de code ne couvre pas automatiquement un modèle, un checkpoint, une
  police, une image, un son ou un asset 3D.
- Les assets LimeZu locaux restent hors Git et hors artefact public. Leur code de
  chargement ne doit jamais transformer une licence d'utilisation en autorisation de
  redistribution.
- Un skill, plugin ou nœud ComfyUI installé depuis un dépôt tiers suit sa propre
  licence et sa propre analyse de sécurité ; l'étiquette d'un catalogue ne vaut pas
  certification.
