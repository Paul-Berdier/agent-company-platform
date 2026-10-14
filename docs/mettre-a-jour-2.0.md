# Préparer la mise à jour vers ACP 2.0

**Statut : préparation, non déployée.**
Un candidat Windows 2.0 a été construit, mais il n’est pas encore prêt à installer.
Ce guide décrit le parcours prévu après les dernières validations et
l’autorisation applicable. Il ne demande aucune action de production maintenant.
Le commit exact validé (SHA) et le futur installateur devront être indiqués
avant de commencer. N’utilisez pas le paquet 1.2.0 pour suivre ce parcours.

Aucune connexion personnelle, mise à jour de vos services ni mission avec votre
compte n’a été validée pendant cette préparation. Les preuves et limites sont
détaillées dans [le bilan 2.0](refonte/remote-only.md).

Votre PC reste un client graphique : aucun agent, terminal ou outil de codage
local n’est nécessaire. Ce parcours utilise les ressources déjà autorisées ;
il ne prévoit ni nouvel abonnement ni remplacement par une API payante.

## 1. Sauvegarder avant la mise à jour

Ces gestes Railway restent ceux du propriétaire, après préparation du déploiement.
Les [sauvegardes Railway](https://docs.railway.com/volumes/backups) peuvent être
facturées selon le stockage incrémental. Vérifiez leur prise en charge dans votre
budget existant ; aucun coût supplémentaire n'est autorisé par ce guide.

1. Mettez les projets en pause et attendez qu’aucune tâche ne soit en cours.
2. Dans Railway, sauvegardez **`executant-donnees` puis `hermes-donnees`**,
   dans cet ordre. Notez les heures et les références des sauvegardes.
3. Faites l’**export chiffré** depuis ACP et conservez le fichier ainsi que le
   profil Windows qui l’a créé. L’export est protégé par Windows (DPAPI), sans
   mot de passe distinct : perdre ce profil peut rendre le fichier inutilisable.
   La sauvegarde de volume Railway reste la sauvegarde principale.
   Vérifiez que les sauvegardes et l’export sont disponibles.
4. Préparez le retour arrière avec le
   [manuel, § 6.4](exploitation.md#64-vos-gestes-et-le-point-de-non-retour).
   Revenir à une ancienne image ne remet pas automatiquement les données d’avant.

Conservez l’identité ACP, les volumes, les projets et le coffre existant
`C:/Users/Paul/Documents/ACP-notes`. Aucun compte ni coffre n’est à recréer.

## 2. Mettre à jour le serveur, puis le client

Utilisez la révision exacte couverte par les preuves finales, dont la migration
depuis la version réellement installée. La seule mention « 2.0 » ne suffit pas.

1. Mettez à jour **Hermes** vers le SHA validé. Vérifiez sa santé et sa version.
2. Mettez à jour **l’exécutant** vers la révision compatible validée et vérifiez
   son retour en ligne. Gardez son identité existante : aucun nouvel enrôlement
   de machine n’est prévu. Le service d’identité et vos moyens de connexion
   restent conservés. Gardez la pause jusqu’au retour de l’inventaire de
   l’exécutant 2.0 : Hermes peut refuser temporairement l’ancien relevé Claude.
3. Seulement ensuite, fermez ACP et installez le **futur client desktop 2.0**
   validé, avec le même compte Windows et le même mode d’installation.
   Le lien et l’empreinte du paquet doivent avoir été fournis avant cette étape.
4. Rouvrez ACP avec votre adresse habituelle. Vérifiez la compatibilité dans
   les diagnostics et l’état du serveur dans **Comptes et modèles**.

La mise à jour du client ne met pas à jour les services Railway. Si une étape
échoue, gardez les projets en pause et suivez le retour arrière préparé.
Ne supprimez aucun volume pour corriger une erreur.

## 3. Connecter Claude depuis ACP

Trois connexions ont des rôles différents :

- **Accès ACP** : vous permet d’ouvrir vos projets et vos réglages.
- **Coordinateur Hermes** : permet à Hermes de planifier et de suivre le travail.
- **Moteur Claude Code** : exécute les tâches sur le serveur avec votre compte.

Connecter Claude ne connecte pas automatiquement le coordinateur Hermes.
Vérifiez séparément que les deux sont disponibles avec les droits déjà autorisés.

1. Ouvrez **Comptes et modèles**, puis **Connecter Claude**.
2. Choisissez **Ouvrir Anthropic dans le navigateur** et suivez l’autorisation
   officielle avec votre compte Claude Pro ou Max.
3. Si Anthropic affiche un code temporaire de retour, collez-le uniquement dans
   le champ **Code temporaire de connexion Claude** d’ACP, puis choisissez
   **Valider le code**. Ne le collez jamais dans Discussion, une note ou ce chat.
   Ce champ ne demande ni mot de passe ni jeton d’abonnement.
4. Attendez la confirmation du compte dans ACP. **« Code transmis » ne signifie
   pas encore « compte connecté ».** Le champ est effacé après l’envoi.
5. Si le lien ou la remise du code devient indisponible, attendez la vérification.
   Si elle ne peut aboutir, utilisez **Annuler la connexion**, puis recommencez
   pour obtenir une nouvelle autorisation. Fermer ACP n’annule pas la procédure.

Les noms de modèles documentés ne prouvent pas leur disponibilité pour votre
compte, ni un quota restant. La déconnexion d’un moteur depuis cette interface
n’est pas encore disponible. **Codex reste bloqué en écriture sur le Railway
actuel, en régime B** ; connecter son compte ne retire pas cette restriction.

## 4. Faire un premier essai simple

La mise à jour et la connexion Claude ne suffisent pas à rendre un premier
projet prêt. Avant l’essai, un alias de dépôt autorisé doit être déclaré dans
la politique déployée sur le serveur, puis apparaître dans son inventaire récent.
L’ajout d’un dépôt depuis ACP n’est pas encore disponible : cette préparation
fait partie du déploiement revu, sans terminal demandé au propriétaire. Aucun
dépôt personnel n’est ajouté automatiquement.

Avant toute inférence, vérifiez **Settings > Usage** sur le site officiel Claude
et désactivez **Usage credits** pour cet essai sans supplément. Un abonnement
Pro ou Max ne garantit pas à lui seul l’absence de frais : ces crédits peuvent
facturer l’usage au-delà du forfait, y compris Claude Code. ACP ne connaît pas
ce réglage ; son statut « connecté » ne prouve rien sur la facturation.
Voir [la gestion officielle des crédits d’usage](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans).
Aucun achat ni activation de crédits n’est prévu.

Vérifiez aussi que le coordinateur Hermes fonctionne avec son fournisseur déjà
autorisé : il doit planifier et produire la synthèse après l’exploration Claude.
Dans **Nouveau projet**, choisissez l’alias déclaré, activez **Choisir manuellement
l’assistant, le modèle et l’effort**, puis choisissez Claude Code pour
l’exploration et un modèle proposé explicitement. Les alias documentés ne
prouvent pas les droits du compte : seule une exécution réelle les confirmera.
Le routage des étapes suivantes doit également être vérifié ; la carte
Architecture peut rester confiée à Hermes pour ce premier essai en lecture seule.
Codex reste fermé en écriture sur le Railway actuel.

Après ces contrôles, levez la pause pour une petite analyse en lecture seule du
dépôt autorisé, avec un périmètre et des limites serveur préparés. Attendez une
synthèse textuelle et un journal indiquant le moteur réellement utilisé. Si les
droits existants ne suffisent pas, arrêtez l’essai sans activer de dépense
supplémentaire. Sans dépôt déclaré, **Lancer avec Hermes (sans dépôt)** reste un
parcours distinct : il ne vérifie pas l’exécution de Claude sur un dépôt.

Pendant la tâche, fermez le desktop, suivez le même projet dans le web ACP,
puis rouvrez le desktop. Vérifiez que vous retrouvez la même tâche et son
résultat sans la relancer. Ce parcours personnel reste à mesurer.

La livraison des fichiers, des différences de code et des artefacts dans ACP
reste à compléter. Ce premier essai ne valide donc pas encore un parcours
complet de modification et de livraison de code.
