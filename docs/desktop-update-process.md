# Vérification des mises à jour desktop

État du 23 septembre 2026, **0.10.0 en préparation**. `UpdateService` existe dans
`apps/desktop/src/services/`. Il vérifie les publications GitHub et ouvre leur
page officielle. **Il ne télécharge ni n'installe de paquet.** La validation du
nouvel arbre est consignée dans [le relevé daté](desktop-validation-2026-09-23.md).

## Parcours disponible

La vérification part sur action de l'utilisateur depuis les réglages, sans appel
automatique au démarrage. Le canal stable est le défaut ; inclure les préversions
est une option explicite.

| Étape | Comportement |
|---|---|
| Stable | Lecture de `/repos/Paul-Berdier/agent-company-platform/releases/latest` sur `api.github.com` |
| Préversions autorisées | Lecture des 100 premières publications, choix de la version admissible la plus élevée |
| Validation | Rejet des brouillons, versions illisibles et préversions sur le canal stable |
| Comparaison | Version sémantique, suffixes de préversion et métadonnées de build |
| Affichage | Version distante et notes bornées en texte brut |
| Action | Ouvrir la publication officielle si elle est plus récente que le client |

Le canal préversion peut retenir une version stable plus récente. Il ne parcourt
pas les publications au-delà de la première page de 100.

L'URL admise est exactement une page HTTPS du dépôt
`github.com/Paul-Berdier/agent-company-platform/releases/tag/<tag>`, sans
utilisateur, port explicite, requête ou fragment. Une URL incluse dans les notes
ne remplace pas cette destination. L'ouverture passe par le navigateur système
après une action explicite.

## Transport et refus

Le client GitHub est séparé d'`ApiClient` : aucun cookie ACP, CSRF ou token GitHub.
Les cookies et redirections sont désactivés. La réponse est bornée à 2 Mio,
avec délai de transfert de 15 secondes et échéance globale de 20 secondes.
Les notes sont limitées à 100 000 caractères ; elles ne deviennent jamais une commande.

Erreur TLS, refus HTTP, absence de publication, réponse illisible ou dépassement
de taille produisent un échec explicite. Le client n'annonce pas « à jour »
lorsqu'il n'a pas pu comparer les versions. Il ne lance ni téléchargement
automatique ni rétrogradation.

## Fabrication et publication

Les workflows `desktop-ci.yml` et `desktop-release.yml` existent. Ils utilisent
`packaging/windows/toolchain.json`, MSVC/Qt et les scripts d'empaquetage Windows.
Le workflow de publication prépare un **brouillon** depuis une étiquette.
L'existence du workflow ne prouve pas qu'une nouvelle publication a été créée
ou rendue publique.

La version 0.10.0 est ouverte dans le dépôt, sans annonce de publication finalisée.
Fusion, artefact de CI, étiquette et publication GitHub sont des objets distincts.
Le journal et [le relevé de validation](desktop-validation-2026-09-23.md) suivent
les preuves finales.

Les paquets restent **non signés** sans certificat configuré. Une somme de
contrôle permet de vérifier une copie, mais ne constitue pas une signature
de l'éditeur. Le service actuel ne télécharge ni paquet ni manifeste et ne
vérifie donc aucun installateur à la place de l'utilisateur.

## Limites

Le téléchargement intégré, le manifeste de mise à jour, la vérification de
signature et le lancement contrôlé d'un installateur restent à construire si
ce parcours est retenu. L'ancienne conception les décrivait comme cible ;
ils ne font pas partie du service livré. Installation et mise à jour sur
Windows propre restent à éprouver.
