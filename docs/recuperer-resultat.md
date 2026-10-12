# Récupérer le résultat d'un projet ACP

Un résultat peut être un texte de synthèse et, pour un projet sur dépôt, une branche Git
préparée sur l'exécutant. La synthèse se lit dans ACP. L'exécutant n'effectue aucun push :
la récupération de la branche, sa revue et sa publication restent des gestes distincts.

## Lire et conserver la synthèse

Ouvrez **Mon atelier** ou **Projets**, sélectionnez le projet, puis **Résultats**. Vous y
trouverez le résultat reçu de Hermes, l'exploration du dépôt lorsqu'elle existe et les
tours/décisions disponibles. Le texte est sélectionnable : sélectionnez la partie voulue
puis utilisez **Ctrl+C** pour la conserver dans votre document de travail.

Pour une étape particulière, ouvrez **Travail** puis sa carte. Si le résumé est tronqué,
le bouton **Lire le résumé entier** effectue la lecture complémentaire. Une absence de
résultat ou une limite de taille reste indiquée ; une carte terminée ne garantit pas
à elle seule l'existence d'un fichier téléchargeable.

L'inspecteur de la carte affiche les observations d'exécution que Hermes a enregistrées :
identifiant de l'exécution, machine, état et métadonnées disponibles. Le **résumé chiffré**
des modifications indique des comptes de fichiers et de lignes ; il ne remplace pas la
lecture du diff. Une observation absente ou illisible est annoncée comme telle.

## Retrouver la branche prête

Dans la station native, ouvrez **Assistants → Résultats à récupérer**. Le panneau
présente les branches d'intégration signalées terminées par Hermes, avec le projet,
l'alias du dépôt et le commit attendu. Trois résultats sont visibles d'abord ;
**Afficher les résultats** développe la liste lorsqu'elle en contient davantage.
Choisissez **Préparer la récupération** pour ouvrir le guide de cette branche.

L'étape de génération propose **Copier la commande à compléter** : l'alias et la branche
viennent du résultat choisi ; remplacez `<chemin-cle-SSH>` par le chemin de votre clé.
La station copie cette commande, sans ouvrir de connexion SSH ni transférer le fichier.
Les étapes suivantes expliquent comment relever le fichier effectivement créé,
le copier sur votre PC, vérifier son empreinte et importer la branche. Le guide se
ferme si le résultat change lors d'une relecture ou si vous quittez la page.

Ce relevé peut décrire une intégration terminée sur une ancienne machine. Il ne prouve
pas que la branche existe sur l'instance actuelle : retrouvez l'exécutant qui possède
le dépôt avant de générer le bundle. Une liste absente, vide ou contenant des identifiants
illisibles est signalée explicitement. Le tableau de bord navigateur propose également
**Poste → Branches prêtes**.

Notez l'alias du dépôt, la branche exacte et sa tête. Une branche de projet a la forme
`hermes/projet-<slug>`, mais utilisez la valeur effectivement affichée. Si aucune branche
n'est prête, vérifiez les questions, les revues et l'étape d'intégration du projet avant
de tenter un export.

Le parcours ci-dessous concerne l'exécutant **Railway**. Il suppose vos CLI Railway,
Git et OpenSSH disponibles sur le PC, le bon projet/environnement déjà lié et votre
clé SSH dédiée enregistrée. Ces accès appartiennent au propriétaire. La mise à jour du
client ACP ne les crée pas. Préparation : [Railway, accès SSH et récupération](refonte/railway.md#137-récupérer-une-branche-prête-git-bundle-aucun-push).

## 1. Demander le bundle à l'exécutant

Depuis PowerShell, adaptez les valeurs entre chevrons, puis exécutez la commande de
**votre** branche. Ne copiez pas une clé ni un jeton dans la commande : seul le chemin
local du fichier de clé est attendu.

```powershell
railway ssh -i '<CHEMIN_CLE_SSH>' --service executant -- acp-poste bundle <ALIAS_DEPOT> <BRANCHE_HERMES>
```

Le superviseur affiche trois informations : **Bundle écrit**, **SHA-256** et **Tête**.
Conservez-les. Il refuse l'export s'il détecte un secret dans l'historique non poussé,
même retiré depuis. Un refus n'est pas une invitation à contourner le contrôle.

## 2. Copier le fichier sur le PC

Copiez l'identifiant d'instance depuis **Copy Service Instance ID** dans Railway. Avec
OpenSSH 9 ou plus, récupérez le fichier annoncé dans un dossier de votre choix ; utilisez
un nom de destination encore absent pour ne pas remplacer un ancien résultat.

```powershell
scp -i '<CHEMIN_CLE_SSH>' '<INSTANCE>@ssh.railway.com:/donnees/acp/bundles/<NOM_BUNDLE>' '<CHEMIN_LOCAL_NOUVEAU.bundle>'
```

Si le client OpenSSH est plus ancien, la procédure d'exploitation prévoit `scp -s`.
Le fichier transféré est un bundle Git, pas un programme d'installation.

Vérifiez son empreinte avant l'import :

```powershell
$bundleAcp = Read-Host 'Chemin local du fichier .bundle'
$empreinteAcp = Read-Host 'SHA-256 affiché par acp-poste bundle'
$ErrorActionPreference = 'Stop'
if ($empreinteAcp -notmatch '^[0-9a-fA-F]{64}$') { throw 'Empreinte attendue invalide.' }
$empreinteLocaleAcp = (Get-FileHash -LiteralPath $bundleAcp -Algorithm SHA256).Hash
if (-not $empreinteLocaleAcp.Equals($empreinteAcp, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Empreinte différente : ne pas importer ce bundle.'
}
Write-Host 'Bundle reçu avec une empreinte conforme.'
```

## 3. Importer dans une nouvelle branche locale

Utilisez le clone local du **même dépôt**. Les commandes suivantes vérifient le bundle,
créent une branche locale nouvelle et comparent la tête reçue à celle annoncée. Elles ne
basculent pas votre dossier courant sur cette branche et ne fusionnent rien dans `main`.
Exécutez-les dans la même session PowerShell que la vérification précédente.

```powershell
$depotAcp = Read-Host 'Chemin du clone local du même dépôt'
$brancheDistanteAcp = Read-Host 'Branche exacte annoncée, par exemple hermes/projet-mon-projet'
$brancheLocaleAcp = Read-Host 'Nouvelle branche locale, par exemple revue/acp-mon-projet'
$teteAttendueAcp = Read-Host 'Tête Git annoncée par le panneau et la commande bundle'
$ErrorActionPreference = 'Stop'
if ($teteAttendueAcp -notmatch '^[0-9a-fA-F]{40}$') { throw 'Tête Git attendue invalide.' }
git check-ref-format --branch $brancheLocaleAcp
if ($LASTEXITCODE -ne 0) { throw 'Nom de branche locale invalide.' }
git -C $depotAcp show-ref --verify --quiet "refs/heads/$brancheLocaleAcp"
if ($LASTEXITCODE -eq 0) { throw 'Cette branche locale existe déjà : choisir un autre nom.' }
if ($LASTEXITCODE -ne 1) { throw 'Impossible de vérifier les branches du dépôt local.' }
git -C $depotAcp bundle verify $bundleAcp
if ($LASTEXITCODE -ne 0) { throw 'Bundle non vérifié : import arrêté.' }
git -C $depotAcp fetch --no-tags $bundleAcp "${brancheDistanteAcp}:refs/heads/$brancheLocaleAcp"
if ($LASTEXITCODE -ne 0) { throw 'Import Git refusé.' }
$teteLocaleAcp = (git -C $depotAcp rev-parse "refs/heads/$brancheLocaleAcp").Trim()
if ($LASTEXITCODE -ne 0 -or $teteLocaleAcp -cne $teteAttendueAcp.ToLowerInvariant()) {
    throw 'La tête importée diffère : examiner avant toute intégration.'
}
Write-Host "Branche récupérée et tête vérifiée : $brancheLocaleAcp"
```

Si la tête du panneau a changé depuis l'export, relevez pourquoi avant de comparer
à nouveau. Ne forcez pas une mise à jour de branche pour faire disparaître un écart.

## 4. Examiner les fichiers sans toucher au travail en cours

Un worktree permet d'ouvrir la branche reçue dans un nouveau dossier, en conservant
votre checkout habituel et ses modifications. Dans la même session PowerShell :

```powershell
$dossierRevueAcp = Read-Host 'Chemin d un nouveau dossier pour la revue'
if (Test-Path -LiteralPath $dossierRevueAcp) { throw 'Ce dossier existe déjà : choisir un nouveau chemin.' }
git -C $depotAcp worktree add $dossierRevueAcp $brancheLocaleAcp
if ($LASTEXITCODE -ne 0) { throw 'Création du dossier de revue refusée.' }
```

Ouvrez ce dossier dans votre éditeur, lisez le diff et exécutez les vérifications
propres au projet. Vous choisissez ensuite le push et la PR dans ce dépôt. ACP n'a
ni publié le code sur GitHub ni fusionné le résultat en effectuant cette récupération.

## Retrouver le travail demain

Conservez le nom du projet, celui de la branche locale et le dossier de revue. À la
reprise, l'onglet **Résultats** garde la synthèse enregistrée dans Hermes ; les fichiers
récupérés se trouvent dans votre worktree local.

La purge de l'exécutant retire les anciens worktrees inactifs et bundles selon sa
politique (sept jours par défaut), mais conserve leurs branches. Un bundle purgé peut
être régénéré si sa branche est toujours présente. Cette règle n'est pas une sauvegarde
du volume : conservez une copie locale du résultat que vous souhaitez garder.

Références de mise en œuvre : `apps/poste/src/acp_poste/gestes_executant.py` (`bundle`),
`apps/poste/src/acp_poste/depots.py` (`bundle`, `purger`), le guide natif
`apps/desktop/src/viewmodels/PosteViewModel.cpp` et le panneau navigateur
`apps/interface/src/poste/Executant.tsx`. Le parcours sur vos accès réels n'est pas
considéré comme exécuté par la présence de ce guide.
