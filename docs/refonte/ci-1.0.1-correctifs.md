# Correctifs de la CI de 1.0.1 — 10 octobre 2026

## Résultat initial, avant correction

PR #27, commit `61f4b9fae33ab3484dc590aec8c80ddf20c323f7`, workflow
`38023100275`, job `114128131855` : **2 échecs, 202 réussites, 19 tests désélectionnés**
dans la suite de contrat. Les images se construisent. Les tests navigateur de ce job
ne sont pas exécutés après l'échec. Le job séparé de restauration est vert.

1. `test_version_de_hermes_et_condensat_epingle` compare la dernière ligne de
   `acp-entree` à l'exec historique PID 1. La branche init externe avait déplacé
   cette ligne. L'ordre est reformulé, sans changer le comportement : la voie non-PID-1
   fait son exec dans le `if`, la voie PID 1 garde son exec historique en dernière ligne.
   Un contrat supplémentaire compare l'empreinte de l'entrée livrée à la source entière.
2. `test_carte_servie_seulement_a_peut_executer` échoue dans le prévol SQLite amont :
   `kanban.db-shm is read-only for this user`. Ce message ne prouve pas le propriétaire
   réel du fichier : ses attributs n'ont pas été capturés lors de cet échec.

## Course reproduite, correction bornée

Dans Hermes épinglé (`f97608f178d1ffeca59860195ab7da295f7c8e5f`),
`preflight_db_writability` capture les fichiers annexes existants, puis teste leurs
permissions. Si SQLite retire `-shm` ou `-wal` entre les deux, `os.access` échoue,
le `stat/chmod` échoue aussi et le prévol l'annonce à tort comme « read-only ».
Le témoin déterministe retire le fichier précisément lors du premier `access` :
la fonction amont échoue alors que le fichier n'existe plus. La version corrigée passe.
Cela établit cette course ; cela ne remplace pas un relevé des attributs du fichier
du run initial pour exclure toute autre cause possible de ce message.

L'adaptateur de construction contrôle le SHA-256 du segment AST **entier** de la
fonction amont, puis ajoute un dernier `lstat` pour les deux annexes uniquement.
Seule `FileNotFoundError` est admise. Une permission refusée, une autre erreur,
un lien cassé encore présent ou la disparition de la base principale ne sont pas
convertis en succès. Aucun fichier n'est supprimé par le correctif, aucun droit
n'est élargi par celui-ci ; les contrôles et réparations déjà prévus par l'amont
restent identiques. Le reste du module est conservé. Une dérive de fonction ou une
seconde application arrête le build.

## Validation

Les **12 tests unitaires ciblés** ont été exécutés avec succès avant publication du
correctif. Ils comprennent les deux témoins amont en échec attendu, les courses
WAL/SHM corrigées, les permissions réellement refusées, la base principale disparue,
l'intégrité du reste du module et les refus de dérive. La syntaxe shell est vérifiée.
Sept tests supplémentaires ciblent la vraie fonction importée dans l'image Docker.
Ils doivent être exécutés par la CI, ainsi que le contrat complet et les navigateurs.
Aucun résultat Docker local n'est revendiqué : Docker n'est pas disponible dans
l'environnement de correction.

**Pas de fusion ni d'étiquette 1.0.1 avant CI complète verte sur le correctif.**
Aucune modification de Railway, d'Authelia, des volumes ou des connexions du propriétaire
n'est effectuée par ce lot. Codex reste fermé en régime B.
