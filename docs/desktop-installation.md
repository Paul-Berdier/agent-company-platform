# Installer Agent Company Platform sur Windows

Public : utilisateur de la station de travail. Aucune connaissance technique
requise, aucune ligne de commande obligatoire.

> **État au 23 septembre 2026 : 0.10.0 est en préparation.** Des binaires et paquets
> de la fondation ont été fabriqués ; cela n'annonce pas une publication desktop
> 0.10.0 disponible. L'installation sur un Windows propre reste à vérifier.
> Consulter les notes de la publication réellement proposée avant téléchargement.

## Ce dont vous avez besoin

- Windows 10 ou Windows 11, 64 bits.
- L'adresse du serveur Agent Company Platform de votre organisation, et un compte
  sur ce serveur. L'application ne fonctionne pas seule.
- Aucun droit administrateur : l'installation se fait dans votre profil.

## 1. Télécharger

Ouvrez [les publications officielles](https://github.com/Paul-Berdier/agent-company-platform/releases)
et vérifiez qu'une publication propose les paquets desktop pour votre canal.
Une simple étiquette ou une archive du code source n'est pas un installeur.
Deux fichiers vous concernent lorsqu'ils sont joints :

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
binaires ne sont **pas signés**. Windows peut afficher un avertissement comme
« Windows a protégé votre ordinateur », selon la politique du poste.

La somme de contrôle vérifie la copie, pas l'identité cryptographique de l'éditeur.
Respectez la politique de votre poste et vérifiez l'origine de la publication.
Les notes doivent annoncer explicitement l'état de signature.

## 2. Installer

Double-cliquez sur `AgentCompanyPlatform-Setup-<version>-x64.exe`.

- Aucune demande d'élévation de privilèges : l'application s'installe pour vous
  seul, sous `%LOCALAPPDATA%\Programs\Agent Company Platform`.
- Une entrée est ajoutée au menu Démarrer.
- Le raccourci sur le Bureau est **optionnel** : la case est décochée par défaut.

Pour l'archive portable, décompressez le `.zip` et lancez
`AgentCompanyPlatform.exe`. Elle ne crée pas d'entrée d'installation au menu
Démarrer ; l'application utilise toutefois les mêmes préférences utilisateur
et, sur consentement, le même coffre de session que la version installée.

## 3. Connecter l'application à votre serveur

Au premier lancement, l'application demande l'adresse du serveur, puis vos
identifiants. Elle ne devine aucune adresse et n'en embarque aucune par défaut.

Si l'adresse ou le compte sont refusés, l'application le dit en clair : elle
n'affiche jamais un état inventé ni un écran vide à la place d'une erreur.

Le premier propriétaire doit être amorcé par l'API, le web ou le CLI.
L'adresse Railway réelle n'est pas fournie par défaut. La mémorisation de session
est facultative et utilise le coffre Windows ; aucun mot de passe n'est conservé.
La session reste soumise à son expiration et à la validation du serveur.

## 4. Mettre à jour

Téléchargez la nouvelle version et relancez le programme d'installation par-dessus
l'ancienne. Vos préférences et l'adresse de votre serveur sont conservées.

Les réglages permettent une vérification GitHub explicite, stable ou avec
préversions. Elle affiche les notes en texte brut et peut ouvrir la publication
officielle dans votre navigateur. Le client n'intègre aucun téléchargeur ou
installateur. Voir [le fonctionnement exact](desktop-update-process.md).

L'application **ne se met jamais à jour toute seule** et ne télécharge rien en
arrière-plan.

## 5. Désinstaller

**Paramètres** > **Applications** > **Applications installées** > *Agent Company
Platform* > **Désinstaller**.

Ce qui est supprimé : le programme et tous les fichiers posés par l'installation,
le raccourci du menu Démarrer, celui du Bureau, et l'entrée de désinstallation.

Ce qui est **conservé** : les préférences non sensibles gérées par `QSettings`
(sur Windows, généralement dans le registre utilisateur). L'emplacement réel est
fourni par les diagnostics ; ne supposez pas qu'un dossier `%APPDATA%` les contient.
Avant de désinstaller, déconnectez-vous et désactivez la mémorisation de session
pour effacer la copie du coffre. La désinstallation des fichiers ne constitue
pas une révocation de session sur le serveur.

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

Le client a été compilé, lancé et exercé contre une vraie API locale jetable.
L'installation sur Windows propre, la signature et le parcours Railway restent
non prouvés. Les 21 suites natives et les 24 tests de session, dont le vrai
coffre Windows hors sandbox, passent. Consulter
[le relevé daté](desktop-validation-2026-09-23.md) pour les preuves de paquet
et d'installation. Cette documentation
n'annonce ni une V1 complète ni une publication 0.10.0 finalisée.
