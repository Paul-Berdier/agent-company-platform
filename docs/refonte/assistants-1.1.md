# Assistants guidés — 1.1

La page **Assistants et machine** (route historique `station`, entrée Poste) sépare trois
configurations : l'identité ACP qui donne accès au workspace, Hermes coordinateur, et les
assistants Codex/Claude de la machine d'exécution. Elle ne change pas le protocole machine.

## Ce qui est livré

- Machine active nommée avec sa plateforme observée, sa présence et la date du relevé.
  Le serveur accepte actuellement **une seule machine active**, Windows **ou** Linux/Railway.
- Cartes Codex et Claude : mode et état observés, version, offre quand elle est connue.
  L'identité personnelle du compte n'est pas inventée : elle n'est pas transmise par les sondes.
- Guides de configuration/reconnexion adaptés à la plateforme ; commandes statiques copiables,
  jamais exécutées par la station. Aucun formulaire ne recueille de jeton fournisseur.
- Vérification par le vrai `POST /api/plugins/acp-poste/v1/poste/releve`, puis lecture de
  `GET /api/plugins/acp-poste/v1/poste`. Les diagnostics restent disponibles dans un panneau
  replié : enrôlement, compte système, versions, isolement, dépôts, ordres et révocation.
- Accès aux pages existantes Quotas et Routage ; leurs mesures restent les sources de vérité.

## Connexion propriétaire

Sur Windows, ouvrir PowerShell **dans le compte qui fait tourner le poste ACP**. Pour le compte
dédié, le guide fournit `runas /user:acp-poste "powershell -NoProfile"`. Les commandes ACP utilisent
`& "$env:ProgramFiles\ACP\poste\acp-poste.cmd"`, puis `connexion codex`, `connexion claude` ou
`diagnostic`. Codex utilise le flux officiel par code d'appareil. Le bac à sable se prépare avec
`connexion bac-a-sable`, dans cette même console, et sa demande UAC.

Pour Claude, lancer d'abord `claude setup-token` dans la session personnelle autorisée, puis
coller le résultat **uniquement dans la saisie masquée** de `connexion claude` dans le compte du
poste. Vider ensuite le presse-papiers et son historique. Le dépôt confirme le stockage, pas
l'authentification distante. Procédure existante : [poste, installation et connexions](../../apps/poste/README.md).

Sur Railway, le propriétaire ouvre une session SSH du bon projet et du service **executant**,
avec sa clé dédiée selon [le manuel Railway, § 13.4–13.5](railway.md). Ne pas ajouter `--session`.
Dans cette console : `acp-poste pause`, attendre l'arrêt propre de la carte en cours, effectuer
`acp-poste connexion codex` ou `acp-poste connexion claude`, puis `acp-poste reprise` et
`acp-poste diagnostic`. Les commandes de connexion lancent les CLI sous leurs UID dédiés.
À la fin de l'opération, même en cas d'échec, quitter la session SSH avec `exit`. Dans la
console d'administration Railway, retirer la clé dédiée avec
`railway ssh keys remove --2fa-code <code>` (remplacer `<code>` par le code de second facteur),
vérifier que `railway ssh keys` est vide, puis lancer `railway logout`, selon le
[§ 11 du manuel Railway](railway.md#11-sécurité-du-compte-railway). Une déconnexion seule
ne retire pas la clé. Ce rappel ne concerne que Railway, pas le poste Windows ni un autre
hôte Linux. Le guide n'exécute jamais ces gestes, `railway login`, `railway link` ni une
opération d'administration.

Hermes coordinateur se configure dans son propre tableau de bord : **Clés → Connexions
fournisseurs (OAuth) → openai-codex → Connexion**, puis **Modèles** pour son modèle par défaut.
C'est le parcours existant de [Railway, § 6](railway.md). Le compte Codex de l'exécutant ne
configure pas ce coordinateur ; les identifiants restent gérés par Hermes.

## Vérification sans faux succès

Le HTTP 202 signifie « demande en file ». Il ne confirme aucune connexion. La station garde
l'identifiant de machine et, à réception du 202, l'identifiant/date du dernier inventaire visible.
Elle attend ensuite un inventaire de **la même machine**, d'identifiant strictement supérieur,
dont la date du relevé est ultérieure et dont le bloc connexions est présent. Elle affiche alors
« Nouveau relevé reçu » ; les cartes peuvent toujours dire Non connecté, Refusé ou Inconnu.
L'acquittement ou la disparition de l'ordre ne servent jamais de preuve.

Le protocole ne relie pas directement un ordre à un inventaire : le texte confirme une nouvelle
observation, pas une causalité certaine avec cet ordre. Après trois minutes sans nouveau relevé,
le suivi local signale le retard ; il **n'annule pas** l'ordre distant, qui peut rester en file.
Actualiser peut encore recevoir le nouveau relevé. Les réponses tardives d'une session perdue ou
oubliée sont ignorées ; changer de machine invalide la vérification précédente. Une erreur réseau
ne transforme pas l'ancien état des cartes en état actuel : la date et l'erreur de lecture restent
visibles ensemble.

## Frontières conservées et limites

- Le desktop parle seulement au Hermes authentifié. Il n'accède ni aux fichiers d'identifiants,
  ni au coffre de l'exécutant, ni à ses processus. La copie utilise le presse-papiers existant.
- L'app-server des **sondes** conserve sa liste blanche : login/logout restent interdits. Aucun
  outil d'exécution ou de gestion de compte n'est ajouté à Hermes l'agent.
- `jeton_reconnu` décrit le code de sortie de `claude auth status`, sans promettre une vérification
  certaine auprès d'Anthropic. Une échéance déduite du dépôt ne devient pas une échéance garantie.
- Le guide réutilise les gestes déjà documentés pour les binaires épinglés. Il ne suppose pas que
  les mécanismes des versions Claude plus récentes sont disponibles ici.
- Ni authentification distante intégrée, ni déconnexion fournisseur distante, ni multi-compte,
  ni plusieurs machines actives ne sont ajoutés. Révoquer une machine coupe son accès ACP ; cela
  ne révoque pas ses comptes chez OpenAI/Anthropic.
- Le schéma vendorié Codex 0.156.1 déclare `chatgptDeviceCode`, mais une future connexion intégrée
  devra avoir son propre cycle propriétaire (défi, attente, annulation, expiration, confirmation),
  distinct de la sonde en lecture seule. Aucun rafraîchissement de jetons ne passe par le desktop.

## Vérification du lot

`apps/desktop/tests/cpp/tst_poste.cpp` couvre les plateformes, le filtrage d'un inventaire d'une
ancienne machine, les seules commandes copiables, le refus des fournisseurs inconnus, le 202
sans nouveau relevé, un nouveau relevé encore non connecté, le retard, la réponse illisible,
le remplacement de machine et la réponse tardive après perte de session. Fixture Linux explicite :
`poste-assistants-railway.json`, synthétique, dérivée de la forme réelle de `/v1/poste`.

La compilation et l'exécution des tests Qt sont centralisées avec les autres changements du lot.
Aucune connexion à un compte personnel n'est effectuée par ces tests ; la recette réelle de compte
reste un geste du propriétaire.
