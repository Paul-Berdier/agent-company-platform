# Routage des plans en mode Auto

Un modèle, une voie ou un effort proposés dans le plan de Hermes sont des **préférences**.
Ils ne constituent pas un verrou du propriétaire. La composition du graphe appelle désormais
`resoudre(..., preference_plan=True)` et `resoudre_relecture(..., preference_plan=True)`.
Le défaut `False` conserve les choix explicites des appels manuels existants, dont l'exploration.

## Résolution d'une étape

1. Une surcharge applicable du propriétaire (carte, projet, globale, dans cet ordre) passe en premier.
   Elle est revérifiée contre la politique et le relevé actuels. Si elle échoue, la résolution refuse :
   aucune autre voie ne remplace ce verrou en silence.
2. Les classes réservées à Hermes et les tâches de conception/rédaction sans dépôt conservent son
   profil. Les hints du plan ne changent pas son fournisseur ou son modèle. Une intégration reste
   déterministe, sans modèle ni effort.
3. Pour une étape exécutée sur dépôt, seuls les candidats présents dans la table autorisée sont
   considérés. Chaque entrée est entièrement résolue et validée : classe, dépôt, voies fermées,
   compte, version, modèle, effort, politique locale, palier et quota connu sous le seuil.
4. Parmi les candidats encore valides, le serveur retient celui qui correspond au plus grand nombre
   d'indices voie/modèle/effort du plan. À égalité, l'ordre de la table est conservé. Aucune valeur du
   plan ne remplace l'effort, le palier ou le modèle d'une entrée.

Une préférence inconnue n'interrompt donc plus un plan disposant d'une entrée autorisée valide.
Un quota épuisé écarte un candidat ; l'entrée suivante doit elle aussi appartenir à la table et
respecter les gardes. Une table vide refuse l'étape même si le modèle demandé existe au relevé.
La provenance reste `table` ; ce changement n'ajoute aucune valeur au contrat machine.

## Relecture

La relecture d'un plan reste croisée : elle cherche uniquement les entrées autorisées de l'autre
voie. Elle n'utilise plus le modèle par défaut du relevé comme autorisation implicite lorsqu'aucune
entrée de table ne convient.

D91 permet la même voie seulement si l'autre voie est **fermée** et si ce repli est autorisé par le
réglage du propriétaire. Le modèle de relecture doit alors différer de celui de l'implémentation,
y compris après résolution d'un modèle par défaut. Le manque de quota sur l'autre voie ne permet
pas d'activer D91. La mention de repli est conservée. Une surcharge incompatible avec la voie de
relecture requise ou avec le modèle distinct échoue sans être remplacée.

## Vérifications et portée

`scripts/tests/test_routage_plan_auto.py` utilise le vrai routage, le vrai schéma SQLite en mémoire,
le contrat partagé et la composition du graphe. Seul l'adaptateur externe Hermes est remplacé.
Les tests couvrent préférences inconnues, candidats autorisés, quotas, politique modifiée, verrou
propriétaire, absence de table, relecture croisée, D91, graphe et maintien du profil Hermes.

Les tests d'image existants de planification installent désormais une table factice explicitement
validée par le propriétaire dans `lancer_sur_depot`. Une table déjà définie reste intacte ;
`routage_valide=False` garde les cas d'absence d'autorisation. Les tests négatifs vérifient que
le plan ne peut pas remplacer cette table. L'effort hors énumération est testé uniquement après
son autorisation explicite par la fixture propriétaire.

La suite d'image demeure nécessaire pour vérifier l'adaptateur et les vrais tableaux Hermes.
Les tests locaux ne constituent ni une exécution distante, ni un usage d'un compte personnel.
Les routes et l'outil historique qui créent les surcharges sont inchangés par ce lot ; ce changement
porte sur les préférences transmises par `graphe.composer`, pas sur cette frontière d'administration.
