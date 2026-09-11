# Centre MCP et bibliothèque de skills

Date d'état : 11 septembre 2026
Statut : architecture cible du lot D ; fonctionnalité non livrée

## Objet et limites

Ce document définit l'intégration cible des serveurs MCP, des skills et des
extensions dans Agent Company Platform. Il ne décrit pas une fonctionnalité déjà
disponible. Au 11 septembre 2026, il n'existe ni centre MCP/skills utilisable dans
l'interface, ni installation contrôlée, ni affectation à un projet, ni révocation
de bout en bout.

Trois objets doivent rester distincts :

- un **serveur MCP** expose des outils et éventuellement des ressources via un
  transport réellement supporté ;
- un **skill** contient des instructions, des références et, parfois, des scripts ;
- un **plugin natif** charge du code dans un processus de confiance. Un manifeste
  ne constitue pas une sandbox.

L'activation d'un de ces objets ne lui accorde aucun droit implicite. Les droits
appartiennent à une politique de projet et à une mission donnée.

## Architecture cible

```text
Interface / CLI acp
        │
        ▼
API plateforme ── registre versionné ── stockage privé des sources
        │                   │
        │                   └── révisions, diffs, licences, diagnostics
        │
        ├── coffre de références de secrets
        ├── moteur de politiques et approbations
        └── courtier MCP
              ├── distant : proxy sortant filtré et authentifié
              └── stdio : processus isolé sur un runner autorisé
```

Le registre de la plateforme conserve les métadonnées, les révisions et les
affectations. Hermes reste l'autorité pour ses skills et toolsets natifs. Un mapping
explicite référence l'identifiant et la révision Hermes ; il n'en maintient pas une
copie silencieusement divergente.

### Modèle minimal

- `source` : catalogue vérifié, dépôt et commit explicites, archive contrôlée,
  dossier autorisé ou configuration importée ;
- `revision` : contenu immuable, empreinte, licence déclarée, dépendances et date de
  vérification ;
- `connection` : transport, lieu d'exécution, méthode d'authentification et
  référence de secret ;
- `discovery` : outils et ressources réellement annoncés, schémas conservés comme
  données non fiables ;
- `binding` : projet, révision, sous-ensemble d'outils et politique d'autorisation ;
- `installation` : environnement isolé, versions épinglées, journal, état et
  possibilité de retour à la révision précédente.

Un changement de révision ne modifie jamais une mission en cours. Celle-ci conserve
la révision résolue au démarrage.

## Parcours cible

### MCP

1. Ajouter une source depuis le catalogue, une URL distante, un import compatible
   ou une commande avancée.
2. Afficher origine, révision, prérequis, transport, lieu d'exécution et risques.
3. Recueillir les secrets dans un formulaire dédié, sous forme de références
   serveur ; aucun secret ne revient au navigateur.
4. Demander une autorisation avant tout téléchargement, installation ou lancement
   stdio.
5. Tester la connexion dans l'environnement prévu, avec délai, limites et réseau
   bornés.
6. Présenter les outils découverts, puis sélectionner les outils et projets permis.
7. Activer, diagnostiquer, désactiver, mettre à jour, revenir en arrière ou révoquer.

Une configuration `localhost` est résolue dans le contexte où le serveur tourne :
elle ne rend pas un MCP local accessible à un service Railway.

### Skills

1. Rechercher ou importer une révision explicite.
2. Afficher l'arborescence, le `SKILL.md`, les scripts, les dépendances, la licence
   connue et les permissions demandées.
3. Valider les chemins et l'archive, analyser les fichiers, puis présenter le diff.
4. Installer dans un environnement versionné sans réinstallation globale.
5. Affecter à des projets et capacités précises.
6. Activer après approbation ; conserver la version précédente.

Un skill proposé par Hermes après un travail réussi reste un brouillon relisible.
Il n'est ni installé ni privilégié automatiquement.

## Menaces et contrôles requis

| Menace | Contrôle côté serveur ou runner |
|---|---|
| SSRF, métadonnées cloud, redirection vers un réseau privé | résolution DNS avant et après connexion, blocage des adresses réservées et de la métadonnée cloud, validation de chaque redirection, allowlist explicite pour les réseaux privés nécessaires |
| DNS rebinding et changement de destination | épinglage de la destination résolue pendant la requête, contrôle de l'adresse réellement connectée |
| Commande stdio hostile | approbation avant lancement, exécutable et arguments structurés, environnement minimal, utilisateur non privilégié, limites CPU/mémoire/temps/réseau |
| Paquet mutable ou compromis | révision ou version épinglée, empreinte enregistrée, registre autorisé, aucun `latest` implicite |
| Archive ou dépôt malveillant | limite de taille et de nombre de fichiers, rejet des traversées, liens et fichiers spéciaux, extraction dans un répertoire neuf |
| Script d'installation ou post-install | exécution isolée, journalisée et explicitement autorisée ; pas d'installation globale |
| Schéma d'outil trompeur | traiter noms, descriptions et annotations comme non fiables ; appliquer une politique indépendante |
| Exfiltration de secrets | références de secrets à portée réduite, injection à l'appel seulement, masquage des logs, interdiction dans URL, frontend et export |
| Escalade lors d'une mise à jour | diff de code, dépendances, réseau et permissions ; nouvelle approbation si la portée augmente |
| Injection de prompt via source ou README | les contenus importés n'altèrent jamais la politique, les droits ou les instructions système |
| Plugin natif | sources approuvées seulement, avertissement explicite, processus séparé lorsque possible, procédure de désactivation et restauration |

Un contrôle automatique signale des risques ; il ne certifie pas la sûreté d'une
source.

## Critères d'acceptation du lot D

- Un MCP distant et un MCP stdio de test suivent le parcours ajout, diagnostic,
  sélection limitée, activation et révocation.
- Le test stdio ne démarre rien avant l'autorisation et s'exécute sur le runner
  désigné.
- Les tests SSRF couvrent loopback, réseaux privés, métadonnée cloud, redirection et
  rebinding ; une allowlist ciblée est auditée.
- Un import Hermes/Claude/Codex affiche un aperçu normalisé, masque les secrets et
  signale toute compatibilité partielle.
- Un skill de test affiche tous ses fichiers, sa révision et ses dépendances ; son
  activation sur le projet A ne le rend pas disponible dans le projet B.
- Une mise à jour ajoutant un script ou un accès réseau exige une nouvelle
  approbation et ne change pas un run déjà démarré.
- La révocation invalide les appels futurs et produit un événement d'audit sans
  supprimer l'historique.
- Les refus et erreurs ont un diagnostic exploitable dans le web et le CLI.

Ces critères correspondent notamment aux scénarios d'acceptation 7, 8 et 9. Aucun
n'est satisfait à ce jour.

## État réel

### Réalisé/vérifié

- La séparation de responsabilités plateforme/Hermes est décidée dans
  `docs/architecture.md`.
- Les risques MCP/skills et les critères d'acceptation sont spécifiés dans le
  présent document.

### Réalisé, non testé réel

- L'adaptateur Hermes officiel détecte les capacités nécessaires aux Runs synchrones.
  Cela ne constitue ni un centre MCP, ni une détection des outils natifs, ni une
  installation de skill ou une affectation à un projet.

### Non configuré

- catalogue, registres et dépôts approuvés ;
- coffre de secrets et rotation ;
- proxy sortant et politique SSRF ;
- environnement stdio isolé ;
- registre versionné, analyse et retour arrière ;
- mapping des skills/toolsets Hermes et politiques par projet.

### Restant

- modèles de données, migrations, API et audit durable ;
- interface web et commandes `acp mcp` / `acp skills` ;
- découverte, installation, activation et révocation réelles ;
- tests unitaires, intégration, sécurité et E2E des critères ci-dessus.
