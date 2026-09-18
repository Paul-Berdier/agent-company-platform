# Installer Agent Company Platform sur Windows

Public : utilisateur de la station de travail. Aucune connaissance technique
requise, aucune ligne de commande obligatoire.

> **État au 18 septembre 2026 : aucune version n'a encore été publiée.** Aucune
> étiquette `v0.9.0` n'existe et aucun binaire n'a jamais été fabriqué. Ce document
> décrit ce qui se passera dès la première publication ; il ne décrit pas un
> téléchargement disponible aujourd'hui.

## Ce dont vous avez besoin

- Windows 10 ou Windows 11, 64 bits.
- L'adresse du serveur Agent Company Platform de votre organisation, et un compte
  sur ce serveur. L'application ne fonctionne pas seule.
- Aucun droit administrateur : l'installation se fait dans votre profil.

## 1. Télécharger

Ouvrez la page des versions du projet sur GitHub et prenez la plus récente. Deux
fichiers vous concernent :

| Fichier | Quand le choisir |
|---|---|
| `AgentCompanyPlatform-Setup-<version>-x64.exe` | cas normal : installation avec menu Démarrer et désinstallation propre |
| `AgentCompanyPlatform-Portable-<version>-x64.zip` | poste verrouillé, clé USB, essai sans rien installer |

Un troisième fichier, `SHA256SUMS.txt`, sert à vérifier que le téléchargement n'a
pas été altéré.

### Vérifier le téléchargement (recommandé)

Dans PowerShell, dans votre dossier de téléchargements :

```powershell
Get-FileHash .\AgentCompanyPlatform-Setup-<version>-x64.exe -Algorithm SHA256
```

Comparez l'empreinte affichée avec la ligne correspondante de `SHA256SUMS.txt`.
Si elles diffèrent, **n'exécutez pas le fichier** et signalez-le.

### Un avertissement de Windows est attendu

Tant qu'aucun certificat de signature de code n'est en place pour ce produit, les
binaires ne sont **pas signés**. Windows affichera « Windows a protégé votre
ordinateur » au premier lancement : sans réputation établie, Microsoft Defender
SmartScreen présente un fichier comme un risque plus élevé et avertit l'utilisateur.

Vous pouvez passer outre par **Informations complémentaires** puis **Exécuter quand
même** — mais faites-le seulement après avoir vérifié la somme de contrôle
ci-dessus. Les notes de chaque version disent explicitement si ses binaires sont
signés ou non ; elles ne prétendent jamais l'inverse.

## 2. Installer

Double-cliquez sur `AgentCompanyPlatform-Setup-<version>-x64.exe`.

- Aucune demande d'élévation de privilèges : l'application s'installe pour vous
  seul, sous `%LOCALAPPDATA%\Programs\Agent Company Platform`.
- Une entrée est ajoutée au menu Démarrer.
- Le raccourci sur le Bureau est **optionnel** : la case est décochée par défaut.

Pour l'archive portable, décompressez le `.zip` où vous voulez et lancez
`AgentCompanyPlatform.exe`. Rien n'est écrit dans le registre, il n'y a pas
d'entrée au menu Démarrer, et la mise à jour consiste à remplacer le dossier.

## 3. Connecter l'application à votre serveur

Au premier lancement, l'application demande l'adresse du serveur, puis vos
identifiants. Elle ne devine aucune adresse et n'en embarque aucune par défaut.

Si l'adresse ou le compte sont refusés, l'application le dit en clair : elle
n'affiche jamais un état inventé ni un écran vide à la place d'une erreur.

## 4. Mettre à jour

Téléchargez la nouvelle version et relancez le programme d'installation par-dessus
l'ancienne. Vos préférences et l'adresse de votre serveur sont conservées.

L'application **ne se met jamais à jour toute seule** et ne télécharge rien en
arrière-plan.

## 5. Désinstaller

**Paramètres** > **Applications** > **Applications installées** > *Agent Company
Platform* > **Désinstaller**.

Ce qui est supprimé : le programme et tous les fichiers posés par l'installation,
le raccourci du menu Démarrer, celui du Bureau, et l'entrée de désinstallation.

Ce qui est **conservé** : vos préférences non sensibles, sous
`%APPDATA%\Agent Company Platform`. Réinstaller ne vous fait donc pas ressaisir
l'adresse du serveur. Pour repartir de zéro, supprimez ce dossier vous-même après
la désinstallation.

Pour l'archive portable : supprimez le dossier décompressé.

## 6. Si quelque chose ne va pas

| Symptôme | Ce que cela veut dire |
|---|---|
| « Windows a protégé votre ordinateur » | binaire non signé, attendu — voir section 1 |
| L'application indique « Hors ligne » | le serveur n'est pas joignable depuis ce poste |
| L'application indique « Non configuré » | une fonction dépend d'un réglage absent côté serveur |
| La connexion est refusée après une longue session | la session serveur expire ; il faut se reconnecter |

En cas de doute sur l'origine d'un fichier téléchargé, revérifiez d'abord sa somme
de contrôle.

## Ce que ce document ne promet pas

Aucune installation n'a jamais été réalisée sur un poste tiers, aucun binaire n'a
jamais été fabriqué, et aucun serveur n'a jamais été déployé pour ce produit. Les
écrans et les libellés cités ici décrivent le comportement attendu de la première
version, pas un logiciel observé en fonctionnement.
