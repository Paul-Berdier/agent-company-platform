# Mises à jour de la station

> **Depuis le 11 octobre 2026 (D170, demande du propriétaire), la station se met à jour seule.**
> Les relevés antérieurs (vérification à la demande seulement, 0.10.0) restent consultables sous
> l'étiquette `archive/acp-0.10.0-avant-hermes`. Rien de ce qui suit n'a encore été éprouvé sous
> Windows : la preuve viendra de la première publication installée ainsi.

## Ce que fait la station

| Étape | Comportement |
|---|---|
| Quand | 30 secondes après le démarrage, puis toutes les six heures ; ou « Vérifier les mises à jour » |
| Où | `https://api.github.com/repos/Paul-Berdier/agent-company-platform/releases/latest` (canal stable) ; avec les préversions, les 100 premières publications |
| Quoi | La dernière publication **publiée** plus récente que la station. Un brouillon n'est jamais retenu |
| Fichiers | `AgentCompanyPlatform-Setup-<version>-x64.exe` et `SHA256SUMS.txt`, à l'adresse exacte `https://github.com/Paul-Berdier/agent-company-platform/releases/download/<tag>/<nom>` |
| Transport | Client séparé d'`ApiClient` : aucun cookie ni jeton ACP. Redirections suivies vers `github.com`, `objects.githubusercontent.com` et `release-assets.githubusercontent.com` seulement, en HTTPS |
| Vérification | Taille égale à l'annonce de GitHub, SHA-256 égal à la ligne de `SHA256SUMS.txt` (et à l'empreinte que GitHub annonce, s'il la sert). Sinon le fichier est supprimé et rien n'est installé |
| Installation | Au démarrage suivant, avant toute fenêtre, ou tout de suite par « Installer maintenant » : installeur lancé avec `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /ACPRELANCER=1`, la station s'arrête, l'installeur remplace ses fichiers puis la relance |
| Sécurité anti-boucle | Une seule tentative automatique par version : si la station n'a pas changé de version au démarrage suivant, elle le dit et attend « Installer maintenant » |

Le fichier téléchargé est relu juste avant son lancement : une copie modifiée depuis le
téléchargement est supprimée. L'état (`attente.json` : version, nom, empreinte, tentatives) et
l'installeur vivent dans `%LOCALAPPDATA%\Agent Company Platform\Station de travail\mises-a-jour`.
Ils sont effacés dès que la station tourne dans la version téléchargée.

Préférence : **Réglages › Connexion et mises à jour › « Installer automatiquement les mises à
jour »**, cochée par défaut (`updates/autoInstall`, liste blanche de `SettingsStore`). Décochée,
la station ne contacte plus GitHub d'elle-même ; la vérification et « Télécharger et installer »
restent possibles à la main.

Seulement sous Windows, pour une station posée par son installeur (présence de `unins000.exe`
à côté de l'exécutable). La version portable et Linux vérifient, mais n'installent rien.

## Ce qu'il faut pour qu'une version arrive

1. Une étiquette `vX.Y.Z` poussée lance « Desktop Release », qui prépare un **brouillon** avec
   l'installeur, l'archive portable et `SHA256SUMS.txt`.
2. Le propriétaire relit le brouillon et clique « Publish release ». C'est le seul geste humain :
   dès qu'elle est publiée, chaque station la trouve dans les six heures (ou au démarrage).

## Mise à jour à la main

1. Ouvrir https://github.com/Paul-Berdier/agent-company-platform/releases et télécharger
   `AgentCompanyPlatform-Setup-<version>-x64.exe`.
2. Fermer la station, puis lancer l'installeur. Il remplace l'installation en place ; réglages
   (registre) et jeton (Gestionnaire d'identification) sont conservés. Binaire non signé :
   SmartScreen avertit (« Informations complémentaires », puis « Exécuter quand même »).

## Limites

- Paquets **non signés** : aucun certificat. L'empreinte vient de la même publication que le
  binaire ; elle prouve l'intégrité du fichier, pas l'identité de l'éditeur. Un compte GitHub
  compromis pourrait publier un installeur que la station installerait.
- Rien n'a été éprouvé sous Windows : installation silencieuse, fermeture par `/CLOSEAPPLICATIONS`,
  relance par `/ACPRELANCER=1` (section `[Code]` de `packaging/windows/AgentCompanyPlatform.iss`).
  Les tests (`apps/desktop/tests/cpp/tst_updates.cpp`) éprouvent le téléchargement, les refus et
  l'installation au démarrage contre un faux GitHub de bouclage, avec un lanceur simulé.
- Une station antérieure à D170 n'a pas ce mécanisme : la première mise à jour vers une version
  qui l'a se fait à la main, une seule fois.
- Aucune rétrogradation automatique.
