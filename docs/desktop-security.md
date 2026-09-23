# Sécurité du client desktop natif

État du 23 septembre 2026, **0.10.0 en préparation**. Ce document décrit le code Qt
existant, ses frontières et ses limites. Les preuves exécutées sont consignées
dans [le relevé de validation](desktop-validation-2026-09-23.md). Il ne constitue
ni une certification ni l'annonce d'une V1 complète.

## Frontière de confiance

Le desktop appelle l'API métier pour les données ACP. Il n'accède directement
ni à la base, ni aux agents, ni aux workers, ni au provider-gateway. Les
autorisations locales améliorent l'interface ; l'API reste responsable du refus final.

Les textes serveur restent des données, affichées en texte brut sans
WebView/WebEngine. Les configurations d'agents/MCP et métadonnées privées de
workers ne sont pas remises globalement à QML. Le diagnostic Hermes vient du
serveur ; une capacité Codex/Claude annoncée par un worker ne prouve pas la santé
du fournisseur.

## Authentification et transport

L'authentification humaine utilise le cookie opaque `acp_session`. Le desktop ne
demande ni bearer utilisateur, ni compte GitHub, ni secret de provider. Le pot
de cookies est en C++ ; `ApiClient` injecte le CSRF sur les mutations. Les routes
qui le renouvellent sont sérialisées.

HTTPS est requis. L'exception HTTP est explicite et limitée au bouclage.
Une erreur TLS ne provoque aucun repli en HTTP ; les redirections sont refusées.
Le proxy système est désactivé par défaut. L'adresse Railway réelle reste à
fournir et aucun domaine n'est inventé dans les réglages.

L'invalidation de session annule les appels en attente et change leur génération.
Les cookies des réponses tardives sont contrôlés avant leur enregistrement.
Les écrans invalident aussi leur contexte de projet et de sélection.
Un refus doit rester visible ; une erreur réseau ne prouve ni la révocation
d'une session ni l'absence d'effet d'une mutation.

Les mutations sans contrat d'idempotence ne sont pas automatiquement rejouées.
Conversations et missions utilisent les clés prévues par leurs routes lorsque
le rejeu est admissible. Un résultat incertain appelle un rapprochement avec
l'état serveur.

## Mémorisation facultative

| Donnée | Emplacement autorisé |
|---|---|
| Cookie en cours | Pot de cookies C++ en mémoire |
| Cookie mémorisé, portée et échéance | Coffre Windows après consentement explicite |
| CSRF | Mémoire C++, jamais une propriété QML |
| Mot de passe | Saisie et requête de connexion ; aucune persistance |
| URL, thème, mouvement, consentement | Préférences non secrètes `QSettings` |
| Configurations privées et secrets de plateforme | Serveur ; aucune exposition globale en QML |

`SessionPersistence` utilise une clé dérivée de l'adresse canonique, avec son
schéma, hôte, port et préfixe de chemin. Il refuse une portée différente, un
document invalide ou expiré. La restauration remet seulement le cookie au
transport ; `/auth/session` doit confirmer l'identité, les droits et le CSRF.
Le coffre ne restaure aucun rôle.

Désactiver l'option efface la copie mémorisée. Changement de serveur,
déconnexion, expiration et invalidation déclenchent les purges prévues.
Un échec d'effacement est visible et désactive le consentement pour empêcher
une restauration involontaire. Un coffre indisponible ne mène jamais à un
fichier en clair de remplacement.

Les 24 tests de session passent sans ignoré hors sandbox, dont le cycle réel
lecture/écriture/suppression dans le coffre Windows. Sous sandbox, ce cas était
ignoré lorsque `CredWrite` refusait la session d'exécution. Cette preuve sur le
poste de développement ne valide pas une installation sur Windows propre ;
voir [le relevé central](desktop-validation-2026-09-23.md).

## Contenus produits par les agents

Les textes serveur utilisent `Text.PlainText` ou `TextEdit.PlainText`. Une
balise image reste du texte et ne charge pas de ressource distante. L'export
de conversation est consultable en texte brut.

Le téléchargement de livrable est explicite vers un fichier choisi, borné à
512 Mio et à la taille annoncée. Le SHA-256 annoncé est contrôlé avant validation
atomique ; erreur et annulation ne valident pas un fichier partiel. Le transfert
utilise la session API, sans jeton signé exposé à QML.

Le client n'exécute ni ne rend les livrables comme HTML, SVG, GLB ou vidéo.
L'enregistrement ne garantit pas qu'un fichier est sûr à ouvrir ailleurs.
Le desktop n'ajoute aucune isolation OS aux processus worker.

## Journaux et mises à jour

`src/diagnostics/Redaction.*` filtre des formes connues de secrets. Il ne peut
pas reconnaître un secret arbitraire dans un texte libre : la première protection
reste de ne pas journaliser cookies, CSRF, corps de connexion ou configurations
privées. Des données métier sensibles ne deviennent pas sans risque parce
qu'elles ont traversé un expurgateur.

`UpdateService` utilise un transport GitHub séparé. La vérification est explicite,
les notes restent brutes et l'URL doit correspondre au dépôt officiel et au tag.
Il ne télécharge pas d'installateur et ne vérifie pas de signature Authenticode.
Voir [le processus réel](desktop-update-process.md).

## Limites ouvertes

La signature Windows est absente, l'installation sur Windows propre n'a pas été
réalisée et le parcours Railway réel reste non éprouvé. Les **26 constats du Lot H
ouverts** sont suivis dans [le registre](lot-h-091-review-status.md) ; l'ajout
d'écrans ne les clôture pas. Les preuves historiques ne remplacent pas les tests
de l'arbre final ni une revue de sécurité indépendante.
