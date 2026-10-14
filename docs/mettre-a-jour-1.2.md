# Mettre à jour ACP vers 1.2.0 et associer le coffre existant

Ce guide part de votre installation Windows et du coffre déjà créé
`C:\Users\Paul\Documents\ACP-notes`. Il n’est pas encore associé à Hermes.
Les services personnels `hermes` et `executant` étaient toujours sur ACP 1.0.1
lors du relevé du 14 octobre 2026. Aucune installation, mise à jour de ces services
ou connexion personnelle n’a été exécutée pendant la préparation.

Le produit est validé et fusionné par la [PR 32](https://github.com/Paul-Berdier/agent-company-platform/pull/32),
tag `v1.2.0`, commit `2ceea1bc7db901dcbe99a5bd049bb44c2799ed54`.
Le paquet local ci-dessous est prêt : **il n’est pas nécessaire d’attendre la
release publique** pour l’installer ou, après mise à jour du serveur, associer le coffre.
Le [workflow Desktop Release](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38497373160)
a réussi, mais la [release GitHub](https://github.com/Paul-Berdier/agent-company-platform/releases)
(ID `412263602`, tag `v1.2.0`) reste **en brouillon, non publiée** au 14 octobre 2026.
Elle n’apparaît pas dans le bouton de mise à jour. Les [preuves de 1.2.0](refonte/preuves-1.2.0.md)
distinguent les paquets locaux et ceux construits par la CI.

## 1. Installer le client Windows

1. Sauvegardez les brouillons utiles hors d’ACP : ils restent en mémoire seulement.
   Fermez ACP et le lanceur du coffre s’il est ouvert.
2. Ouvrez le [Setup local 1.2.0](../dist/workspace-1.2.0-livraison/AgentCompanyPlatform-Setup-1.2.0-x64.exe),
   dans le dossier `dist/workspace-1.2.0-livraison` du worktree de livraison.
   Ce fichier local n’est pas un téléchargement présent dans le dépôt public.
3. Installez avec **le même compte Windows et le même mode d’installation**, sans
   désinstaller l’ancienne version. Si l’installeur demande de fermer ACP, faites-le
   avant de continuer. Ne lancez pas les deux versions en même temps.
4. Rouvrez ACP. Dans **Réglages → Mises à jour**, vérifiez la version **1.2.0**.
   Conservez l’URL habituelle de Hermes. Si la session a expiré, suivez **Se connecter**.

Le Setup local a été vérifié et n’est **pas signé** ; Windows peut afficher un
avertissement. Son empreinte SHA-256 est :

```text
5bb072b8bfb4314cf50f18272c173df15fdd053d0b81391d03b3c909a7a8a9dc
```

Son dossier contient aussi `SHA256SUMS.txt`. Les paquets du brouillon GitHub ont
leurs propres empreintes : ne les mélangez pas avec celles de ce paquet local.
Le Setup met à jour le client et le pont du coffre. Il ne met à jour ni Hermes,
ni l’exécutant Railway, ni un poste exécutant installé séparément. Les notes
restent dans Documents, en dehors du dossier du logiciel.

## 2. Mettre à jour Hermes et l’exécutant après sauvegardes

Les deux services Railway sont épinglés au commit ACP 1.0.1
`85b458bbffbfb6dffe1fc40b8c3885f11b779ac7`. Le champ `source.commitSha` fixe
cette version : les pushes sur `main` et la fusion de la PR 32 ne déplacent pas
cette épingle. Il reste donc un déploiement manuel à effectuer.

1. Dans ACP, mettez les projets en pause et attendez que l’exécutant n’ait plus de
   carte en cours. Sauvegardez **`executant-donnees` puis `hermes-donnees`**, dans
   cet ordre, faites l’export chiffré depuis la station et notez l’heure.
   Suivez le [manuel § 6.4](exploitation.md#64-vos-gestes-et-le-point-de-non-retour)
   et le [§ 6.5 pour ACP et l’exécutant](exploitation.md#65-authelia-binaires-de-lexécutant-acp-lui-même).
2. Dans Railway, projet **ACP**, environnement **production**, mettez à jour la
   source de **hermes**, puis de **executant**, vers le commit validé
   **`2ceea1bc7db901dcbe99a5bd049bb44c2799ed54`** (`v1.2.0`), puis déployez ces versions.
   Gardez les variables, volumes, domaine, identité de machine et Start Command vide.
   Aucun nouvel enrôlement de l’exécutant n’est nécessaire.
3. Vérifiez le commit réellement annoncé dans les journaux de chaque déploiement.
   Dans ACP, ouvrez **Réglages → Diagnostics** : serveur **1.2.0**, compatibilité
   conforme. Vérifiez aussi le retour de l’exécutant dans **Poste**.
4. Reprenez les projets après ces contrôles. En cas d’échec, gardez la pause et
   suivez le retour arrière du manuel ; ne supprimez ni service ni volume.

**Redeploy** d’un ancien déploiement reprend son ancien code. **Deploy Latest
Commit** choisit la tête de la branche GitHub par défaut, pas nécessairement le
commit du tag si `main` a avancé. Vérifiez toujours la référence proposée et
le commit réellement démarré ; ne supposez pas qu’un bouton sélectionne `v1.2.0`.
Voir les [actions Railway officielles](https://docs.railway.com/deployments/deployment-actions).

ACP 1.2.0 ajoute trois tables de coffre au premier appel et conserve les tables
existantes. Ces sauvegardes restent nécessaires. L’épingle amont de Hermes ne
change pas. Les connexions aux comptes Codex/Claude restent distinctes : la mise
à jour ne connecte pas un compte absent.

## 3. Associer le coffre déjà créé

**Ne choisissez pas « Créer mon nouveau coffre ACP ».** Le dossier
`C:\Users\Paul\Documents\ACP-notes` et sa configuration locale existent déjà.

1. Dans ACP, ouvrez **Coffre ACP → Créer un code d’association**, puis **Copier le code**.
2. Dans le menu Démarrer de Windows, ouvrez **Coffre ACP - Obsidian**, puis choisissez
   **2 — Associer ce coffre à Hermes**. Entrez la même origine HTTPS que dans ACP,
   puis collez le code dans la saisie masquée.
3. Comparez l’empreinte affichée par le lanceur avec celle d’ACP. Dans ACP,
   saisissez l’empreinte du lanceur et choisissez **Confirmer l’empreinte**.
4. Dans le lanceur, choisissez **3 — Démarrer le bridge** et laissez cette fenêtre
   ouverte. Dans ACP, actualisez le coffre et vérifiez que vous pouvez lire une note.
5. Dans Obsidian, choisissez **Ouvrir un dossier comme coffre**, puis
   `C:\Users\Paul\Documents\ACP-notes`.

Le pont a sa propre identité ; il ne remplace pas l’exécutant et n’ajoute aucun
démarrage automatique. Les neuf actions du coffre sont déclenchées par vous dans
le desktop : **aucun accès aux notes n’est donné aux agents Hermes ni à Discussion**.
Le pont travaille sur les notes Markdown ; il n’intègre pas les plugins, Bases,
Canvas ou toute la CLI Obsidian, et un renommage ne réécrit pas les autres liens.
Les notes demandées transitent par Hermes. Voir le [guide du workspace 1.2.0](refonte/workspace-1.2.0.md)
pour les archives récupérables, les conflits et les limites.
