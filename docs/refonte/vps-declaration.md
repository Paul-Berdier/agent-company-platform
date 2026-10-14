# Déclaration d’un futur exécutant VPS

État au 14 octobre 2026 : support de déclaration préparé, aucun VPS configuré, acheté ou testé. Paul ne possède que Railway. Il n’existe pas encore d’installateur VPS validé. La déclaration ci-dessous ne constitue ni une preuve d’hébergement physique distant, ni une preuve d’isolation.

## Configuration unique et protégée

Le fragment [vps.fragment.toml](../../executant/deploiement/vps.fragment.toml) est à intégrer à une copie révisée de la politique [executant.toml](../../executant/politique/executant.toml), lorsque la machine cible aura été identifiée et autorisée. Il ne duplique pas la politique complète et n’est pas chargé automatiquement. L’origine HTTPS Hermes, les dépôts admis, les conditions d’usage et toutes les restrictions de cette politique restent applicables. Donner aussi un nom explicite au serveur dans `[poste] nom` (le nom livré par défaut mentionne Railway).

Le futur déploiement devra présenter la politique complète sur `/etc/acp/executant.toml`, appartenant à root, non modifiable par groupe/autres ni remplaçable par les UID agents ; montage en lecture seule recommandé. Les vérifications existantes de propriétaire, droits et liens restent actives. `[deploiement]` n’existe que dans le schéma Linux et exige exactement `cible = "vps"` et `distant_confirme = true`. Une section incomplète, un booléen converti depuis une chaîne/un entier ou une clé inconnue provoque un refus.

L’inventaire ne publie `hote = "vps"` et `execution_distante_declaree = true` qu’à partir de cette politique. Sans déclaration, le détecteur conserve son comportement : Railway détecté, sinon PC, y compris sous Linux. Un libellé VPS seul ou une variable d’environnement inventée ne suffit pas. Ne pas forger une variable Railway. Le contrat partagé refuse les combinaisons incohérentes et Hermes vérifie le dernier inventaire de la machine active. L’enrôlement et sa confirmation restent requis. Hermes et l’exécutant doivent tous deux utiliser le contrat qui connaît ce champ ; aucune migration SQL supplémentaire n’est nécessaire. Ce mécanisme repose sur l’opérateur qui contrôle la politique root, pas sur une attestation indépendante de la machine.

## Conditions d’entrée déjà présentes

L’image actuelle exige Linux amd64, le superviseur root et son vrai parent direct `/usr/bin/tini -s -- /opt/acp/bin/acp-entree-executant`, un `/proc` lisible et un point de montage persistant `/donnees`. Ce volume peut être un montage Docker générique ; aucun nom de volume Railway n’est exigé. Il doit assurer les propriétaires et modes POSIX pour les UID agents 10001/10002/10003 et le groupe 10100. Les contrôles de secrets, liens symboliques et binaires root restent inchangés. Aucun port entrant n’est exposé par l’image. La seule variable Railway utilisée par l’entrée sert à afficher le commit ; son absence affiche « inconnu ».

Ces constats sont issus de la lecture des fichiers d’entrée et des tests d’image existants, pas d’une installation VPS. Les déploiements rootless, avec remappage d’UID, sur un système de fichiers sans droits POSIX ou sur arm64 ne sont pas validés. Il manque encore une procédure VPS de montage, mise à jour, sauvegarde et exploitation vérifiée sur la machine retenue.

## Preuve obligatoire avant Codex

Le label VPS ne change aucun verdict. Docker par défaut a donné le régime B dans les essais CI ; les sondes Railway du 10 octobre ont aussi donné B malgré les UID séparés. Un VPS avec Docker par défaut ne résout donc pas automatiquement l’isolation. Codex reste fermé avec `sans_bac_a_sable = "refuse"` tant que la sonde réelle ne confirme pas le régime A. Claude conserve ses propres conditions, sondes et restrictions. Les quotas Claude sont lus dans ses événements Linux, quel que soit l’hébergeur.

La prochaine preuve attendue est la sonde de plateforme exécutée sur le serveur autorisé, dans les conditions exactes du déploiement, montrant notamment bubblewrap fonctionnel, réseau coupé et UID séparés. Elle doit être complétée par les contrôles de comptes, dépôts et exécution distante de bout en bout. Les témoins CI qui desserrent des restrictions du conteneur sont des expériences jetables, pas une configuration de production. Aucun `--privileged` ni désactivation générale seccomp/AppArmor n’est proposé pour la production.

## Validation préparée

Tests purs : politique, droits POSIX sous Linux, production d’inventaire à partir de relevés simulés, contrat strict, garde relisant SQLite et fermeture après retrait de déclaration. Test dans l’image Hermes : Railway et VPS simulés reçoivent une carte autorisée, Codex reste fermé en régime B et la source de quotas est Linux. Ces tests n’authentifient aucun vrai compte et ne prouvent aucune capacité d’un VPS non installé.

## Piste d’exploitation à éprouver

Une VM Linux amd64 dédiée avec exécutant natif sous systemd et le `tini` attendu
est la première piste à vérifier. Elle évite d’empiler le confinement Docker avec
celui de bubblewrap. Elle impose toutefois de reproduire les versions, chemins,
montages et permissions de l’image : aucun service systemd ni installateur natif
n’est livré dans cet incrément. Le superviseur tourne en root et son arrêt balaie
les processus des UID agents ; réserver la VM et ces UID à ACP.

L’alternative conserve l’image Docker et exige des profils seccomp/AppArmor
propres au conteneur ACP, conçus et validés avec la sonde. Les profils par défaut
restreignent les appels de namespace/montage nécessaires. Ce travail reste à
faire ; ne pas remplacer ces profils par une désactivation générale.
Sources officielles : [bubblewrap](https://github.com/containers/bubblewrap),
[seccomp Docker](https://docs.docker.com/engine/security/seccomp/),
[AppArmor Docker](https://docs.docker.com/engine/security/apparmor/).

Sur Ubuntu, la restriction des espaces de noms utilisateur peut nécessiter une
permission `userns` limitée à l’application ; conserver AppArmor actif.
[Description Ubuntu](https://ubuntu.com/blog/ubuntu-23-10-restricted-unprivileged-user-namespaces).
Les options systemd doivent préserver les correspondances d’UID et la supervision
des processus ; `PrivateUsers` ne peut pas être ajouté sans vérification.
[Contrat systemd.exec](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml).

La sonde actuelle mesure `proc_neuf` séparément : ce champ n’entre pas dans le
calcul du régime A. Un résultat A ne permet donc pas d’affirmer à lui seul que
`/proc` a été recréé. Relever les champs détaillés, puis vérifier aussi l’arrêt,
le redémarrage et le parcours complet avant toute activation avec un compte.
