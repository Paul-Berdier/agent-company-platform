# Décisions de réemploi

Vérification : 11 septembre 2026. Une dépendance n'est ajoutée au produit qu'après
épinglage dans un lock et vérification de sa licence propre, de ses assets et des
modèles qu'elle télécharge.

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
