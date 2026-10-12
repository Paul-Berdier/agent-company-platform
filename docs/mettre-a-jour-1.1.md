# Mettre à jour ACP vers 1.1 et reprendre son travail

Ce guide concerne la **station Windows ACP 1.1.0 — Pixel Atelier**, depuis une station
1.0.0 ou 1.0.1. Deux sources sont possibles : un paquet local fourni avec ses sommes
de contrôle, ou les paquets réellement publiés sur
[la page officielle des versions](https://github.com/Paul-Berdier/agent-company-platform/releases).
Une branche fusionnée ou un tag seul ne fournit pas encore un installeur téléchargeable.

## 1. Trouver la mise à jour

**Paquet local fourni directement :** utilisez le dossier indiqué lors de la livraison,
contenant le Setup (ou le portable) et son `SHA256SUMS.txt`. Le paquet local Pixel Atelier
se trouve sous `dist/pixel-atelier-1.1.0/` dans le worktree de construction et embarque
le décor LimeZu importé avec votre licence. Passez à l'étape 2 ; sa présence sur votre PC
ne dépend pas de la publication du brouillon GitHub. Ne mélangez pas ses empreintes avec
celles d'un autre build portant la même version.

**Paquet distribué sur GitHub :**

Dans ACP, ouvrez **Réglages**, puis **Mises à jour → Vérifier les mises à jour**.
Si une version plus récente est disponible, choisissez **Ouvrir la publication GitHub**.
Le bouton ouvre le navigateur : il ne télécharge ni n'installe le logiciel.

Si votre ancienne version ne propose pas ce bouton, ouvrez directement les
[publications du dépôt](https://github.com/Paul-Berdier/agent-company-platform/releases).
Choisissez la publication **1.1.0**, puis téléchargez dans le même dossier :

- `AgentCompanyPlatform-Setup-1.1.0-x64.exe` pour mettre à jour une installation ;
- ou `AgentCompanyPlatform-Portable-1.1.0-x64.zip` pour un usage portable ;
- et `SHA256SUMS.txt`, dans les deux cas.

Si aucune publication publique n'apparaît, elle n'est pas encore disponible via ce
parcours. Un brouillon reste invisible pour le client ; retenter une vérification ne
le publiera pas.

## 2. Vérifier le fichier, sans le lancer

La commande suivante se colle dans PowerShell. Elle demande le dossier de téléchargement,
contrôle qu'une seule empreinte correspond au nom du paquet et s'arrête si elle diffère.
**Elle ne télécharge rien et ne lance pas l'installeur.** Pour le portable, remplacez
seulement la première ligne par son nom ZIP exact.

```powershell
$nomPaquetMaj = 'AgentCompanyPlatform-Setup-1.1.0-x64.exe'
$dossierMaj = Read-Host 'Dossier contenant le paquet et SHA256SUMS.txt'
$ErrorActionPreference = 'Stop'
$paquetMaj = Join-Path $dossierMaj $nomPaquetMaj
$sommesMaj = Join-Path $dossierMaj 'SHA256SUMS.txt'
$motifMaj = '^([0-9a-fA-F]{64})  ' + [regex]::Escape($nomPaquetMaj) + '$'
$lignesMaj = @(Get-Content -LiteralPath $sommesMaj | Where-Object { $_ -match $motifMaj })
if ($lignesMaj.Count -ne 1) { throw 'Empreinte absente ou ambiguë : ne pas installer.' }
$attendueMaj = $lignesMaj[0].Substring(0, 64)
$observeeMaj = (Get-FileHash -LiteralPath $paquetMaj -Algorithm SHA256).Hash
if (-not $observeeMaj.Equals($attendueMaj, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Empreinte différente : ne pas installer ce fichier.'
}
Write-Host "Empreinte vérifiée : $nomPaquetMaj. Aucun programme lancé."
```

Une empreinte correspondante confirme que votre copie correspond au fichier annoncé.
Elle ne remplace pas une signature de l'éditeur. Les paquets sont non signés tant qu'un
certificat n'est pas configuré ; la section **Signature** de la publication indique
l'état du paquet. Windows peut donc afficher un avertissement.

## 3. Remplacer l'ancienne station

**Installation classique :** fermez ACP, puis ouvrez le nouveau Setup. Gardez le même
compte Windows et le même mode d'installation que précédemment. L'installeur reconnaît
l'application existante grâce à son identifiant stable ; il n'est pas nécessaire de la
désinstaller d'abord. Si Windows demande de fermer une instance, terminez ce geste avant
de continuer.

**Version portable :** fermez ACP, décompressez le ZIP dans un **nouveau dossier**, puis
lancez `AgentCompanyPlatform.exe` depuis ce dossier. Ne copiez pas seulement l'EXE sur
les anciennes DLL. Mettez à jour votre raccourci après avoir vérifié le nouveau lancement.
Vous pouvez conserver l'ancien dossier jusqu'à cette vérification.

Ne lancez pas simultanément l'ancienne et la nouvelle station : elles partagent les
préférences du même profil Windows.

**La station et le poste ont des mises à jour séparées.** Le Setup desktop ne remplace ni le poste Windows facultatif `acp-poste`, ni ses copies de Codex et Claude Code, ni l'exécutant Railway. Pour une installation Windows existante, reportez-vous à la [procédure du poste](../apps/poste/README.md#installation-vous-seul-sous-luac), qui commence par une répétition à blanc. Le fichier `poste.toml` existant est conservé ; un changement de version des CLI demande le contrôle décrit dans cette procédure. La mise à jour de l'exécutant Railway relève du [manuel d'exploitation (§ 6.5)](exploitation.md#65-authelia-binaires-de-lexécutant-acp-lui-même).

## 4. Vérifier la reprise

1. Ouvrez **Réglages → Mises à jour** : la version affichée doit être **1.1.0**.
2. Vérifiez l'adresse de votre Hermes. Le changement d'interface ne demande pas une
   nouvelle adresse, un nouveau serveur ni un nouvel enrôlement de l'exécutant.
3. Si une connexion est demandée, utilisez le navigateur système habituel. Une session
   non mémorisée ou expirée peut nécessiter ce geste ; cela n'efface pas vos projets.
4. Depuis **Mon atelier**, ouvrez un projet connu. Retrouvez l'objectif, les cartes et
   les questions, puis **Résultats** pour la synthèse reçue et **Journal** pour les événements.
   Dans **Travail**, sélectionnez une carte pour lire ses observations d'exécution disponibles.
5. Choisissez votre apparence dans **Réglages → Apparence** : **Pixel Atelier** ou
   **Studio**, puis **Suivre Windows**, **Clair** ou **Sombre**. **Réduire les animations**
   coupe le mouvement décoratif.

La famille Pixel Atelier est le choix par défaut si l'ancienne installation ne possédait
pas encore ce réglage. Votre choix clair/sombre et l'URL du serveur sont conservés dans
les préférences Windows ; une connexion mémorisée reste dans le coffre Windows.
Les projets et leurs résultats sont relus depuis Hermes : ils ne sont pas rangés dans
le dossier de l'installeur. Un nouveau projet utilise **Auto** par défaut : Hermes choisit
l'assistant selon sa politique, les capacités relevées et les verrous du propriétaire.
Le choix manuel de l'assistant, du modèle et de l'effort reste disponible dans le formulaire.

Pour une branche terminée, **Assistants → Résultats à récupérer → Préparer la récupération**
ouvre un guide et une commande SSH à compléter avec le chemin de votre clé. Le résultat
vient du relevé de Hermes ; la présence réelle de la branche est contrôlée lors de la
génération du bundle sur l'exécutant concerné. Le transfert et la revue restent à effectuer
sur votre PC, selon [le guide de récupération](recuperer-resultat.md).

### Vérifier le serveur associé

Les observations d'exécution et les préférences du plan demandent aussi le **greffon
ACP 1.1.0 côté serveur**. Installer la station ne met pas ce serveur à jour.

1. Une fois connecté, lancez **Revérifier la compatibilité de Hermes** depuis la palette
   de commandes, puis ouvrez **Réglages → Diagnostics → Compatibilité**. Vérifiez
   **Version du greffon : 1.1.0** et **Contrat du greffon : acp-poste/1**. Le verdict
   **Compatible** seul ne garantit pas la version 1.1.0 : il contrôle les contrats.
2. Dans votre navigateur authentifié sur le même Hermes, ouvrez son adresse suivie de
   `/api/plugins/acp-poste/v1/meta`. Vérifiez `greffon.version` égal à `1.1.0`,
   `hermes.conforme` égal à `true`, puis examinez les `alertes` selon le manuel
   d'exploitation. Une valeur absente ou une lecture en erreur ne valide pas ce contrôle.
3. Dans le projet et l'environnement Railway existants, ouvrez le service **hermes**,
   son déploiement actif et ses journaux. La ligne `[acp] commit déployé : <sha>` doit
   correspondre au commit **ACP** validé pour cette livraison 1.1.0 ; vérifiez également
   `05-acp exited 0` et les workflows réussis pour ce commit. Le champ `hermes.commit`
   de `/meta` désigne l'amont Hermes, pas ce commit ACP. Hermes Agent **0.21.5** conserve
   son épinglage dans ce lot.

**ACP 1.1.0 n'introduit aucune migration de schéma du greffon** : les observations
lisent les exécutions déjà enregistrées et le routage modifie seulement la logique
de choix. Le § 6.5 impose le § 6.4 lorsqu'un lot change ce schéma ; ce n'est pas le
cas de cette version.

Si le serveur est encore ancien, le propriétaire suit la
[mise à jour d'ACP (§ 6.5)](exploitation.md#65-authelia-binaires-de-lexécutant-acp-lui-même).
Pour une mise à jour maîtrisée et un retour arrière préparé, les
[gestes de sauvegarde (§ 6.4)](exploitation.md#64-vos-gestes-et-le-point-de-non-retour)
restent la procédure de préparation : pause générale, aucune carte en main,
sauvegarde d'`executant-donnees` puis de `hermes-donnees`, export chiffré et contrôle
du déploiement attendu avant reprise.
Les sauvegardes et les actions sur le compte Railway restent ses gestes, sur les
services existants ; aucune nouvelle infrastructure ni aucun réenrôlement ne sont
nécessaires pour ce changement de version. Ce guide n'atteste aucun déploiement en
production déjà réalisé.

## 5. Reprendre demain

Avant de fermer, traitez ou identifiez les demandes dans **Questions** et notez le
projet à reprendre. Un texte non envoyé dans une discussion n'est pas un message
conservé dans Hermes : envoyez-le lorsque vous voulez réellement donner la consigne,
ou gardez-en une copie si vous n'êtes pas prêt à l'envoyer. La station garde les brouillons
séparés par discussion pendant la navigation entre ses pages ; elle les efface à la
fermeture de l'application, à la perte de session ou au changement de serveur.

Fermer la fenêtre ne met pas un projet en pause. Si vous souhaitez arrêter son avancée,
utilisez l'action de pause du projet et vérifiez l'état renvoyé. Sinon, le travail peut
continuer sur l'exécutant tant que Hermes et cet exécutant restent disponibles.

Au prochain lancement, retrouvez le projet depuis **Mon atelier** ou **Projets**, lisez
les nouvelles questions, puis son onglet **Résultats**. Un projet terminé ne signifie
pas que sa branche a été envoyée sur GitHub : suivez
[Récupérer le résultat et la branche](recuperer-resultat.md) pour obtenir les fichiers
sur votre PC et préparer leur revue.

## 6. Le décor diffère d'une capture locale

C'est attendu si la capture provenait d'un build avec votre pack LimeZu. Le paquet
GitHub CI utilise une illustration ACP originale, fournie dans le dépôt. Le décor
LimeZu nécessite un import licencié avant compilation ; le ZIP acheté et les sprites
n'accompagnent pas la release publique comme fichiers indépendants. Les thèmes et les
parcours fonctionnels restent les mêmes. Il n'est pas nécessaire d'importer le pack
pour utiliser la station.

## 7. En cas de difficulté

| Ce que vous voyez | Geste utile |
| --- | --- |
| Vérification GitHub impossible | Relire le message, puis consulter la page officielle ; une erreur réseau ne veut pas dire « à jour » |
| Aucune version proposée | Vérifier qu'une release stable publique existe et qu'elle est plus récente que la version affichée |
| Ancienne version après installation | Fermer les autres instances et vérifier le chemin du raccourci ou du portable lancé |
| Demande de connexion | Reprendre la connexion dans le navigateur, avec le même Hermes |
| « Hors ligne », « Inconnu » ou erreur de compatibilité | Consulter **Réglages → Diagnostics** ; ne pas créer un serveur ou réenrôler un exécutant pour corriger un simple affichage |
| Résultat absent | Lire l'état du projet, les cartes et les questions ; une synthèse encore absente est annoncée comme telle |
| Empreinte différente | Ne pas exécuter le fichier ; reprendre le téléchargement et le fichier de sommes depuis la même publication officielle |

La mise à jour de cette station n'applique pas un déploiement Railway, ne restaure pas
un volume et ne change pas les connexions Claude/Codex de l'exécutant. Les procédures
serveur restent dans le [manuel d'exploitation](exploitation.md).

La recette d'installation sur un Windows propre et la reconnexion personnelle ne sont
pas déduites des tests CI. Les vérifications réellement effectuées sont consignées dans
[le relevé Pixel Atelier](refonte/pixel-atelier.md).
