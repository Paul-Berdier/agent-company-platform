# Direction artistique du desktop ACP

État du 23 septembre 2026 — version 0.10.0 en préparation. Le desktop natif
C++23 / Qt Quick possède désormais des écrans et un générateur de jetons. Ce
texte fixe la direction propre à ACP ; les preuves de recette restent dans les
relevés de validation. Le client web historique et Pixel Office gardent leur
apparence actuelle.

## Une identité : graphite, papier et sarcelle

ACP devient un espace où l'on peut discuter, puis construire. La direction
« Quiet Operations » évolue pour accueillir ces deux usages : des conversations
lisibles et un poste de travail précis pour les projets. Un graphite légèrement
végétal, un papier ivoire et une sarcelle mesurée donnent une identité commune aux
thèmes sombre et clair. Le repos est calme ; une couleur de statut signale une
information réelle. Les séparateurs fins et l'alignement portent la structure.

| Jeton | Sombre | Clair |
|---|---|---|
| Canevas | `#191c1a` | `#f7f6f0` |
| Navigation | `#131714` | `#eeefe7` |
| Panneau | `#1e2420` | `#ffffff` |
| Surface élevée | `#272e29` | `#f2f3eb` |
| Texte principal | `#eef2e9` | `#1f2b23` |
| Texte discret | `#9aaa9d` | `#536657` |
| Accent | `#65c6ae` | `#0a6d60` |

Les valeurs exécutables sont dans `design/tokens/`, jamais dans une palette
parallèle par page. Le générateur `apps/desktop/cmake/generate_design_tokens.py`
produit les singletons d'`Acp.Design`. Les couleurs métier restent définies dans
`semantic-status.json` : état d'exécution, validation technique et acceptation
utilisateur sont trois informations distinctes.

Pas de dégradé décoratif, de halo, de mascotte, de transparence de fenêtre ni de
compteurs fictifs. Les pictogrammes de navigation sont des tracés originaux dans
`Acp.Controls/AcpIcon.qml`, indépendants des polices de caractères et sans
ressource distante. Chaque commande conserve son nom accessible et une infobulle
lorsque la barre latérale est repliée.

## Deux portes d'entrée

L'accueil propose « Simplement discuter » et « Construire quelque chose », puis
la reprise des projets accessibles. Un nouveau chat général n'impose ni projet,
ni titre préalable. Le serveur fournit le titre initial. Un projet regroupe ses
échanges, ses missions de code, ses exécutions et ses livrables.

La barre latérale place les conversations, les projets et l'historique contextuel
avant les outils d'exploitation. Les cinq premiers projets et six premiers fils
chargés servent de raccourcis ; les pages donnent accès aux listes complètes
chargées. Ces raccourcis ne prétendent pas être un classement de récence global.
L'inspecteur facultatif donne le contexte de l'objet effectivement sélectionné.
L'historique précédent/suivant porte sur les écrans, pas sur une pile de sessions
ouvertes indépendantes.

Les références d'architecture sont les conversations et projets du
[desktop ChatGPT sous Windows](https://learn.chatgpt.com/docs/windows/windows-app)
et les sessions indépendantes de
[Claude Code desktop](https://code.claude.com/docs/en/desktop).
Les pages officielles ont été consultées le 23 septembre 2026. Elles inspirent
l'organisation de l'espace ; ACP conserve ses propres composants, contrats API
et capacités. Aucun logo, visuel ou composant propriétaire n'est reproduit.
La présence d'un parcours analogue ne signifie pas une parité fonctionnelle
exhaustive avec ces produits.

## Lecture et interaction

- Corps à 14 px logiques ; prose contenue dans 680 px, interligne de 24 px.
- Navigation confortable à 36 px ; contrôles ordinaires de 32 px, principaux de
  40 px. Les tableaux techniques peuvent conserver leur densité de 24–28 px.
- Barre latérale de 256 px par défaut ; largeurs de volets mémorisées et bornées.
  Le repli sur fenêtre étroite préserve la largeur choisie pour le retour au large.
- Titres, texte, métadonnées : trois niveaux nets. Chasse fixe pour le code,
  les chemins et les identifiants ; pas pour la conversation rédigée.
- Entrée envoie un message ; Maj+Entrée ajoute une ligne. La composition IME
  n'envoie pas accidentellement. Les brouillons restent en mémoire par contexte
  et conversation, puis sont effacés au changement d'identité ou d'origine API.
- L'historique suit une réponse uniquement si l'utilisateur était déjà en bas.
  La recherche de titres indique sa portée sur les fils chargés.
- Le texte des réponses reste inerte. Les clôtures de code produisent un bloc
  monospace copiable ; elles n'exécutent rien et ne chargent aucune image distante.
- Les actions contextuelles regroupent renommage, archivage et export. Arrêt,
  envoi incertain et erreur restent visibles, avec les protections serveur.

Le clavier ouvre la palette avec Ctrl+K, un chat avec Ctrl+N, les projets avec
Ctrl+P et la création d'un projet avec Ctrl+Maj+N. Alt+Gauche/Droite parcourt
l'historique des écrans. Les raccourcis ne contournent ni les droits ni une
soumission de message encore incertaine.

## Vérification et limites

Les contrastes calculés sur les six surfaces opaques donnent un minimum de
5,63:1 en sombre et 5,11:1 en clair pour les textes de base, 3,97:1 et 3,20:1
pour les contours interactifs, 6,19:1 et 6,23:1 pour le texte sur les états
d'accent. Ce calcul ne certifie pas les mélanges transparents ni tous les états
rendus. Les captures Qt et les interactions réelles font l'objet d'une recette
séparée après compilation.

La [matrice native](native-desktop-parity.md) fait foi pour les capacités.
Voix, pièces jointes multimodales, édition de code intégrée, terminal interactif
et aperçu navigateur ne sont pas ajoutés par cette refonte. Les missions
Claude/Codex passent par les workers ; leurs identifiants et fournisseurs
nécessitent toujours une configuration réelle. Aucun sélecteur de modèle ou
bouton de fichier ne simule une capacité absente de l'API.
