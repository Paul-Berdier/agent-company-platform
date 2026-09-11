# ACP CLI

Client en ligne de commande de l'Agent Company Platform.

```console
acp login --login owner
acp doctor
acp projects list
acp run --project PROJECT_ID --goal "Livrer la fonctionnalité"
acp runs watch MISSION_ID
acp pending show
```

Le mot de passe n'est jamais accepté comme argument. Utilisez l'invite masquée ou
`--password-stdin` dans un environnement non interactif. `--json` peut être placé
avant ou après la commande. La configuration (URL, cookie de session et jeton
CSRF) est écrite atomiquement avec des permissions restreintes au mieux du système.
HTTP n'est accepté que pour `localhost`, le réseau `127.0.0.0/8` et `::1`. Les
credentials sont liés à l'origine API qui les a émis et sont ignorés dès qu'une
surcharge d'URL change cette origine.

`acp runs watch` peut être interrompu avec `Ctrl+C` sans arrêter la mission. La
commande `acp open --run ...` affiche seulement l'URL ; ajoutez `--browser` pour
demander explicitement l'ouverture du navigateur.

`acp run` et `acp runs stop` réservent leur clé d'idempotence avant l'appel. Les
mutations de configuration sont sérialisées par un verrou interprocessus, puis
écrites par remplacement atomique. Un second verrou, détenu jusqu'à la fin de
l'appel HTTP, refuse immédiatement tout dispatch concurrent afin qu'une seule
requête puisse utiliser la réservation active. Si le réseau, un 5xx, une
redirection ou une réponse métier invalide laisse le résultat incertain, le CLI
conserve une
opération `pending`, liée à la base API exacte (chemin compris), au principal (ou
à la session) et à l'empreinte canonique de la requête. Relancer exactement la
même commande réutilise automatiquement la clé, également affichée dans l'erreur
et dans la réponse réussie. Une commande ou une clé divergente est refusée tant
que cette reprise n'a pas reçu de résultat certain.

`acp pending show` inspecte localement cette reprise sans afficher de credential.
`acp pending discard` demande une confirmation explicite et avertit qu'un effet
déjà appliqué pourrait être dupliqué ; en mode non interactif ou JSON, `--yes`
est obligatoire. Le payload, le cookie, le jeton CSRF et l'identifiant du
principal ne sont pas copiés dans l'enregistrement `pending`.
`--idempotency-key` reste disponible pour fournir explicitement une clé stable.
