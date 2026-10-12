# Vérification et installation des mises à jour desktop

Document actualisé le **12 octobre 2026** pour **ACP 1.1.0 — Pixel Atelier**.
Le guide utilisateur est [Mettre à jour vers 1.1](mettre-a-jour-1.1.md) ; la fabrication
est décrite dans [le processus de publication](desktop-release-process.md).

## Parcours livré

Dans **Réglages → Mises à jour**, **Vérifier les mises à jour** contacte GitHub à la
demande. **Ouvrir la publication GitHub** apparaît si une version admissible est plus
récente. Le navigateur système ouvre alors la publication : l'utilisateur choisit,
vérifie et installe son paquet. Il n'y a ni téléchargement intégré, ni installation
silencieuse, ni vérification automatique au démarrage.

| Étape | Comportement réel d'`UpdateService` |
| --- | --- |
| Canal stable | `/repos/Paul-Berdier/agent-company-platform/releases/latest` sur `api.github.com` |
| Préversions demandées | Cent premières publications, version admissible la plus élevée |
| Validation | Rejet des brouillons, versions illisibles et préversions sur le canal stable |
| Comparaison | Version sémantique ; suffixes de préversion et métadonnées de build reconnus |
| Notes | Texte brut borné, jamais interprété comme commande ou HTML |
| Action | Ouverture de la page de release officielle, sur geste de l'utilisateur |

Le canal préversion peut retenir une stable plus récente ; il ne parcourt pas les
publications au-delà des cent premières. Une étiquette sans release publique, un
brouillon ou un artefact de CI ne constituent pas une mise à jour disponible.

Relevé historique du 12 octobre 2026 : `v1.0.0` avait un
[run de fabrication réussi](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38015121231)
et un brouillon ; `v1.0.1` existait comme tag sans release. Ce relevé ne doit pas être
recopié comme preuve de publication de 1.1.0. L'état courant se lit dans les
[publications du dépôt](https://github.com/Paul-Berdier/agent-company-platform/releases).

## Transport et refus

Le client GitHub est séparé du client Hermes : aucun cookie ACP, CSRF ou token GitHub.
Cookies et redirections sont désactivés. La réponse est limitée à 2 Mio, avec 15 secondes
de délai de transfert et 20 secondes d'échéance globale. Les notes sont limitées à
100 000 caractères.

Une URL de destination doit être exactement une page HTTPS du dépôt
`github.com/Paul-Berdier/agent-company-platform/releases/tag/<tag>`, sans utilisateur,
port explicite, requête ni fragment. Une URL insérée dans les notes ne peut pas la
remplacer.

Erreur TLS, refus HTTP, absence de release, réponse illisible ou dépassement de taille
produisent un échec explicite. Une comparaison impossible n'est pas annoncée « à jour ».
Le service ne télécharge aucun installateur et n'en vérifie donc ni empreinte ni signature.

## Passage de 1.0.x à 1.1.0

L'utilisateur ferme ACP, vérifie le paquet téléchargé avec `SHA256SUMS.txt`, puis lance
le nouvel installeur avec le même compte Windows et dans le même mode d'installation.
L'`AppId` stable permet la mise à jour sur place ; désinstaller d'abord n'est pas requis.
Pour le portable, extraire dans un nouveau dossier et lancer le nouvel exécutable.

Les noms QSettings, les clés de serveur/session et le coffre Windows restent stables.
Les préférences d'apparence existantes sont conservées ; la nouvelle clé
`appearance/family`, absente des anciennes versions, prend `pixel`. Windows clair/sombre
et le mouvement réduit restent des choix indépendants. QSettings utilise ici le registre
Windows natif, pas un fichier de préférences garanti sous `%APPDATA%`.

Ce changement de client ne migre pas les projets Hermes et n'installe pas une nouvelle
image serveur. Fermer le client ne met pas automatiquement les projets en pause.
Une session non mémorisée ou expirée demande une nouvelle connexion par le navigateur.

## Paquets, décor et limites

Sans certificat de code configuré, les paquets sont non signés. Les notes de chaque
release font foi ; une empreinte correcte n'est pas une signature de l'éditeur.

Le paquet CI embarque l'illustration ACP originale versionnée. Le décor LimeZu exige
un build ayant importé localement le pack acheté ; ces sprites restent ignorés par Git.
Les deux variantes conservent les mêmes thèmes et parcours natifs.

L'installeur compilé et les tests automatisés ne prouvent pas une mise à jour effectuée
sur un Windows propre, une reconnexion personnelle ou un déploiement Railway. Rapporter
ces essais séparément lorsqu'ils sont réalisés. Le téléchargement intégré, le lancement
contrôlé d'un installateur et une restauration automatique après échec ne sont pas livrés.
