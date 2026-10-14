# Journal public des exécutions distantes

Implémentation du premier parcours distant, 14 octobre 2026. Hermes reste propriétaire des projets, cartes et résultats. L’exécutant Linux transmet des faits publics du moteur par le protocole machine existant. Le bureau Qt ne lance aucun moteur et peut fermer sa connexion sans arrêter le travail distant.

## Identités et contenu

Chaque événement porte un `id` UUID v4, un `tentative_id` UUID v4 nouveau à chaque invocation CLI, un `ordre` croissant dans cette invocation et une date UTC `quand`. Hermes ajoute les identifiants vérifiés `projet_id`, `tableau`, `carte`, `run_id`, `machine_id`, le rôle `agent`, les identifiants réels des cartes `parents` et `modele_demande`.

Les champs `session_native`, `modele_servi`, `parent_natif` et `item_natif` proviennent du flux CLI lorsqu’il les rapporte. Une valeur absente reste `null`. Le modèle demandé ne devient jamais un modèle observé. Le flux JSON actuel de `codex exec` fournit un identifiant de thread mais ne garantit pas le modèle servi ; cette information demeure inconnue sans observation du moteur. Une session native n’est pas une carte ACP ni un identifiant de tentative.

Les seuls genres admis sont `session`, `message`, `outil`, `fichier`, `termine`, `erreur`, `limite`. Le texte est limité à 500 caractères par fragment. Les messages publics, noms d’outils, identifiants et chemins de fichiers passent par le masquage des valeurs exactes connues du coffre distant et des motifs de secrets avant le découpage. Les arguments et sorties brutes d’outils, les événements de raisonnement, les blocs Claude `thinking`, stderr et les erreurs brutes ne sont pas transmis. Hermes refait son contrôle de motifs sur chaque lot.

`termine` signifie que le tour du moteur est terminé ; la vérification, le commit et l’issue ACP peuvent suivre. Son texte le précise. L’état de la carte reste la source de vérité du résultat ACP.

## Écriture durable et renvoi

`POST /machine/v1/battement` reçoit le champ optionnel `evenements`, limité à quatre événements et 6 Kio dans le corps historique borné à 8 Kio. Le jeton machine, l’état d’enrôlement, la carte, le run et la réclamation sont vérifiés avant toute insertion. Le moteur doit correspondre à la voie de la carte.

Les événements sont d’abord écrits atomiquement dans la **file de sortie existante** de l’exécutant. Un heartbeat sans événement reste direct. Aucun journal brut, service supplémentaire ni nouvelle base n’est ajouté.

Dans SQLite Hermes, une même transaction insère les événements publics dans `journal` (`action = execution_publique`) et leur reçu dans `evenements_execution_recus`. Le reçu contient l’empreinte du contenu canonique et de sa provenance. Un renvoi identique rend le même acquittement ; un identifiant déjà associé à un autre contenu, ou un rang déjà occupé dans la même tentative, refuse et annule le lot. Les reçus survivent au redémarrage.

La réponse ajoute `evenements_recus`. Le fichier local n’est retiré qu’après acquittement exact de tous ses identifiants. Une réponse perdue après commit permet donc un renvoi sans doublon. Une ancienne version Hermes n’acquittant pas ce champ laisse les événements en file : mettre à jour Hermes et l’exécutant ensemble. Les envois concurrents du long-poll et du battement sont sérialisés dans leurs threads ; le lecteur stdout peut continuer ses dépôts pendant une attente réseau. Les événements précèdent l’issue `terminer` dans la même file ; celle-ci est rejouée au démarrage avant toute nouvelle réclamation.

Pendant une invocation, une file non vide est examinée au plus toutes les deux secondes, avec quatre lots maximum par passage. Une panne retrouve l’intervalle normal de battement (60 secondes par défaut). La file réserve cinq places aux issues : à 995 fichiers d’attente, la collecte arrête explicitement l’invocation et la carte est bloquée au lieu de continuer sans journal. Le dernier stdout est drainé après la sortie du processus, avec délai borné.

Si la réclamation est perdue, Hermes refuse les nouveaux faits de ce run. Les fichiers concernés sont conservés dans `sortie/refusees` pour diagnostic ; ils ne sont pas présentés comme un historique reçu. Avant toute émission `terminer`, ces refus persistants sont vérifiés pour le même run. Un refus impose une transformation atomique en `bloquer`, même après redémarrage ; le résultat initial est conservé pour diagnostic. Une nouvelle panne laisse ce blocage dans la même file avec le même identifiant idempotent. Cette limite concerne une rupture entre exécutant et Hermes dépassant les garanties de réclamation. Une fermeture du bureau seul n’interrompt pas leur communication distante. Le volume distant doit persister ; une destruction du volume avant acquittement n’est pas récupérable par ce mécanisme.

## Lecture propriétaire et reconnexion

`GET /api/plugins/acp-poste/v1/projets/{id}/evenements?apres=0&limite=100` exige une session propriétaire Hermes et un projet existant. `limite` est comprise entre 1 et 200. La réponse est :

```json
{
  "projet_id": "p_exemple",
  "evenements": [],
  "prochain_curseur": 0,
  "encore": false
}
```

Chaque événement lu contient les champs ci-dessus et `curseur`, entier global issu de `journal.id`. Il peut présenter des trous (autres actions et projets). La requête ne lit que le projet demandé, en ordre croissant après le curseur fourni. `prochain_curseur` vaut le dernier événement retourné, ou le curseur demandé lorsque la page est vide. `encore` indique qu’une page suivante existe.

Cette route est strictement en lecture : elle ne crée, ne reprend et ne relance ni carte ni processus. Le client garde son curseur pendant une reconnexion et déduplique les `id`; après fermeture complète, une nouvelle lecture peut repartir de zéro. Les événements restent consultables après la fin de la carte. Le mécanisme d’invalidation existant observe déjà le maximum de `journal.id` : il signale les changements sans véhiculer de texte secret ou de flux brut.

## Vérifications

Les tests `apps/poste/tests/test_evenements_distants.py` utilisent des flux synthétiques et un transport fonctionnel explicitement factice, une vraie base SQLite issue du schéma ACP et la vraie file atomique. Ils couvrent réouverture, réponse perdue, renvoi, absence d’acquittement, conflits d’identifiant/rang et rollback du lot, pagination, séparation des projets, masquage avant découpage, exclusion du raisonnement et saturation. Avec les tests existants du protocole et du contrat, 279 tests ciblés ont passé le 14 octobre 2026, sans moteur ni service lancé sur le PC.

Deux tests supplémentaires dans `hermes/tests/image/test_execution_p6.py` exercent le vrai HTTP, le vrai journal, la réclamation et les refus de session/run, avec événements synthétiques ; ils doivent tourner dans l’image Linux jetable. Leur préparation n’est pas une preuve qu’ils ont passé. Aucun compte réel, aucun moteur tiers ni serveur de production n’a été utilisé pour ces preuves unitaires.
