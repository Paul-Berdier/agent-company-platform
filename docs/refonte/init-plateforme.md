# ACP 1.0.1 — démarrage sous un init de plateforme

Correction de l'issue [#26](https://github.com/Paul-Berdier/agent-company-platform/issues/26),
autorisée par le propriétaire le **10 octobre 2026** (code, commit, push, PR, fusion et version corrective).
Il s'agit d'une correction de compatibilité d'exécution, sans modification des protocoles `acp-poste/1`,
`acp-machine/1`, des formats persistants ni des variables publiques : **1.0.1**, pas 1.1.0.

## Constat et périmètre

Le premier déploiement de 1.0.0 sur Railway construisait l'image Hermes, puis la lançait en **PID 2**,
sans Start Command personnalisée. `acp-entree` refusait alors tout démarrage. Authelia a démarré ;
la sonde de l'exécutant a mesuré le régime B, avec séparation par UID et bubblewrap refusé.
L'identité du processus PID 1 de Railway n'a pas été déduite de son seul numéro.

Deux parcours sont désormais définis dans les images, jamais dans une Start Command :

| Image | Init propre en PID 1 | Init de la plateforme en PID 1 |
|---|---|---|
| Hermes | `acp-entree` exécute le dispatcher amont, puis s6-overlay, comme en 1.0.0 | Bootstrap root explicite, puis `exec s6-svscan /run/service` ; s6 devient sous-récolteur d'orphelins |
| Exécutant | Le vrai `/usr/bin/tini -s -- …` supervise l'entrée | Le même Tini, avec `-s`, supervise sous l'init externe |

**Ne jamais lancer directement le serveur, retirer ses gardes ou activer le repli amont sans s6.**
Authelia, ses secrets, son mot de passe et ses passkeys ne nécessitent aucun changement pour ce correctif.

## Hermes : ordre de démarrage

`hermes/image/acp_init_plateforme.py` ne remplace pas s6 par une boucle Python. Il ne s'occupe que de
l'initialisation, puis disparaît par `exec` au profit du superviseur natif :

1. Vérification root et CMD exact `gateway run` ; refus de `S6_KEEP_ENV` et d'un répertoire de supervision
   dérogatoires. Exécution des **mêmes gardes** `commande_gardes` sur l'environnement réel, avant toute réécriture.
2. Verrou exclusif ; refus d'une seconde chaîne s6 attestée vivante. Recréation sûre des deux répertoires
   éphémères `/run/service` et `/run/s6/container_environment`, sans suivre les liens symboliques.
3. Capture root de l'environnement pour `with-contenv`, puis exécution synchrone des scripts amont épinglés
   `01-hermes-setup`, `015-supervise-perms`, `02-reconcile-profiles`, puis de `05-acp`.
   Aucun service ne tourne avant la fin de cette séquence. Dans cette version amont, le rapprochement des
   profils **enregistre** les passerelles ; il ne les lance pas avant le superviseur.
4. Les scripts `run` et `finish`, les contrôles de relance d'ACP et les permissions de `05-acp` sont conservés.
   Les agents peuvent demander une relance par les FIFO autorisées, mais ne peuvent modifier les scripts root.
5. Activation et relecture du statut Linux `PR_SET_CHILD_SUBREAPER` ; création d'une attestation root,
   puis `exec` de s6. Ce statut est conservé à travers `exec`.

L'adaptation de `hermes_cli.service_manager._s6_running` permet aux commandes de contrôle amont de reconnaître
la chaîne externe attestée. `adapter_amont.py` vérifie d'abord les empreintes des scripts amont dont le parcours
dépend : **une évolution de l'image amont qui les change fait échouer le build**, et nécessite une revue de
l'adaptateur. La mise à jour automatisée de Hermes ne dispense pas de cette revue.

## Preuve de supervision et refus

`/run/acp-supervision/etat.json` est un fichier **root, 0444**, dans une chaîne de répertoires root non
inscriptibles par les agents. Le vérificateur refuse les liens symboliques, les permissions incorrectes, les
fichiers spéciaux et les preuves mal formées. La preuve lie le PID au démarrage Linux du processus, à l'identité
du boot, à son UID root et à l'argv exact de s6. Un PID réutilisé n'est donc pas une preuve vivante.

Pour un serveur de production, le greffon exige également une **ascendance effective** jusqu'à ce superviseur.
Une variable d'environnement, un fichier périmé ou un serveur lancé par `docker exec` à côté de la chaîne ne
suffit pas. Les commandes ponctuelles et les bancs qui n'utilisent pas le home de production restent hors du
périmètre de cette sentinelle, comme précédemment. Il ne s'agit pas d'une protection contre root : root contrôle
les images, les attestations et les volumes. L'authentification du tableau de bord reste essentielle.

Le diagnostic en lecture seule reconnaît la preuve vivante et utilise l'environnement s6, pas celui d'une
session SSH et pas l'environnement de l'init externe. Les protections contre les `.env` du volume, les sources
externes de secrets et les outils d'exécution sont conservées avant les services et lors des relances prévues.

## Arrêt et orphelins

Les services disposent d'un délai d'arrêt de 15 secondes avant terminaison forcée de leur groupe. Le `finish`
nettoie le **groupe de processus du service terminé**, fourni par s6, avant d'appeler le `finish` amont ; son code
125 reste significatif. s6, sous-récolteur, récupère les orphelins. Cela ne promet pas l'arrêt sélectif d'un
processus qui aurait volontairement quitté ce groupe avec `setsid` ; la fin du conteneur arrête son espace de
processus. Les tests distinguent la relance d'un service de l'arrêt du conteneur.

L'exécutant garde ses propres mécanismes d'arrêt, de commit WIP et de drainage. Son vérificateur contrôle le
parent réel de l'entrée, l'inode du **binaire Tini livré**, son UID root, son argv exact avec `-s` et la stabilité
du lien de parenté ; le seul nom `tini` dans `/proc/1/comm` n'est plus accepté comme preuve. Les contrôles du
volume `/donnees`, des propriétaires, des modes et des liens restent inchangés.

## Tests et portée des résultats

- `scripts/tests/test_supervision_plateforme.py` : preuves falsifiées, obsolètes, permissions, liens,
  identité du processus, ascendance et ordre des gardes.
- `hermes/tests/contrat/test_init_plateforme.py` : vrai Docker `--init`, diagnostic, OIDC factice, routes privées,
  outils interdits, agent caché de preview, volumes piégés, relances, redémarrage, sous-récolteur, orphelins et arrêt.
- Les tests négatifs d'entrée de `test_sans_shell_contrat.py` continuent de refuser toute configuration invalide,
  tout volume Railway non déclaré et les serveurs lancés hors chaîne.
- `executant/tests/test_init_plateforme.py` : vrai Tini sous `--init`, attente non enrôlée, permissions et arrêt ;
  refus du vrai Tini lancé sans `-s`.
- Les suites existantes continuent d'éprouver le parcours normal PID 1. Les fixtures de clients **1.0.0** sont
  conservées quand elles vérifient la rétrocompatibilité ; les assertions de la version courante passent à 1.0.1.

Les premiers essais du commit `824cf0e` ont observé le démarrage et les protections Hermes ainsi que l'arrêt
sans zombies ; les six tests sélectionnés de l'exécutant sont passés. Le run
[38022032561](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38022032561) est toutefois **rouge** :
un test neuf attendait un libellé d'erreur différent, des assertions attendaient encore 1.0.0 et un ancien test
altérait un octet aléatoire par « X », parfois déjà présent. Ce dernier emploie désormais XOR pour garantir
l'altération, sans modifier le vérificateur de signatures. Les résultats finaux sont ceux de la PR et de `main`.

`docker run --init` reproduit un init parent, **pas l'ensemble de Railway**. Aucune connexion réelle du
propriétaire, consommation d'abonnement, passkey ni exécution d'un dépôt personnel n'est prouvée par ces tests.

## Déploiement du correctif

Les constantes sont alignées sur **ACP**, environnement `production`, et les domaines du propriétaire :
`hermes-production-2d4e.up.railway.app` et `identite-production.up.railway.app`.
L'origine de l'exécutant est mise à jour dans la même correction.

Ne pas appliquer l'IaC entière aveuglément : le service initial `agent-company-platform` existe encore en plus
des trois services prévus. Aucun volume ni service n'est à supprimer pour corriger ce problème. Cibler le nouveau
commit fusionné (les sources Railway ont été épinglées à `f76e7c5`), conserver les variables et les volumes,
laisser la Start Command vide, vérifier santé et instance réellement active. Pour l'exécutant, il faut en plus
un volume `/donnees`, retirer la commande de sonde et rétablir la politique de redémarrage normale.

La connexion OIDC du propriétaire, les passkeys et l'enrôlement viennent ensuite. **Codex exécutant reste fermé
en régime B** : le correctif de PID ne change pas les capacités de sandbox de Railway.

Références primaires : [s6 sous un autre init](https://skarnet.org/software/s6/overview.html),
[services et finish](https://skarnet.org/software/s6/servicedir.html),
[Tini subreaper](https://github.com/krallin/tini#subreaping),
[PR_SET_CHILD_SUBREAPER](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html).
