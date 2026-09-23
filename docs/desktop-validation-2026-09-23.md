# Validation du desktop natif — 23 septembre 2026

Périmètre : durcissement Lot H et client C++23 / Qt 6.8.3. Le chantier Pixel Office
du checkout principal est conservé séparément, conformément au choix du propriétaire.
Ce relevé distingue développement intégré, tests exécutés et recette de distribution.

## Historique d'intégration

- Lot H : [PR #9](https://github.com/Paul-Berdier/agent-company-platform/pull/9)
  fusionnée dans `main` au commit `3f8e5fe` ; [CI verte du commit de fusion](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35799431367).
- `main` intégrée dans `codex/desktop-completion` par `887fb72`, puis ouverture
  de la version 0.10.0 par `4915136`. Ces deux commits ne constituent pas une
  publication ni la fusion du desktop dans `main`.
- Desktop : [PR #10](https://github.com/Paul-Berdier/agent-company-platform/pull/10)
  fusionnée dans `main` au commit `0bc9dcb7f0e95c699d9d1610b76d2324940fe2b7`,
  après validation de `52dc4761` sur la même base `3f8e5fe`. Le worktree desktop
  suit désormais `main` ; le checkout Pixel Office est conservé séparément.

## Intégration continue du desktop

Sur `52dc4761ba1400709a6c6549838c12603b5bd0e3`, la
[CI Windows 35806313489](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35806313489)
est verte : build Release, 21 suites natives (54,59 s), parcours Qt/API réelle
effectivement exécuté sans saut, puis fabrication des deux paquets. Le CRT
déployé comprend 10 DLL VC143 x64 14.44.35211.0. L'artefact d'inspection
`desktop-ci-35806313489` contient les paquets et les rapports autorisés.
Il ne s'agit pas d'une publication GitHub Release.

La [CI plateforme 35806313531](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/35806313531)
est également verte sur le même commit : Node/web, suite SQLite, suite PostgreSQL 16,
parcours événements et automatisations, sauvegarde/restauration PostgreSQL.
Décomptes des rapports : **2 903 réussis, 63 ignorés** sur SQLite (246,92 s) ;
**2 913 réussis, 53 ignorés** sur PostgreSQL (669,80 s), avec deux avertissements
de dépendances dans chaque suite. Les écarts avec Windows viennent des cas
conditionnés par la plateforme et le moteur ; les cas ignorés restent explicites.
Le job Playwright E2E opt-in est **ignoré** ; aucun passage n'est revendiqué pour lui.
L'ouverture de la PR et sa fusion relancent automatiquement les workflows ; les
preuves ci-dessus identifient précisément les exécutions terminées avant fusion.

## Preuves exécutées localement

| Vérification | Résultat observé |
|---|---|
| Backend combiné, SQLite, Python 3.12.10 | 2 896 réussis, 70 ignorés, 2 avertissements ; 835,34 s |
| Contrats API/fixtures desktop après ouverture 0.10.0 | 6 réussis ; 2 avertissements de dépendances |
| Cohérence des versions | Toutes les copies vérifiées portent 0.10.0 |
| Projection du verrou Python Windows | 4 tests unitaires réussis ; verrou Linux conservé |
| Compilation finale MSVC Release / Qt 6.8.3 | 50 étapes incrémentales réussies après la reconstruction propre de 404 étapes |
| Suite native finale | 21 suites sur 21 réussies, 54,82 s ; chargement des pages QML inclus |
| Parcours Qt contre API réelle jetable | 3 réussis, 0 échec, 0 ignoré ; code de sortie 0 |
| Coffre Windows, session utilisateur locale | 24 cas réussis, 0 échec, 0 ignoré, dont écriture/lecture/suppression d'une entrée UUID synthétique |
| Dépendances MSVC/Ninja après correction UTF-8 | Modification d'un en-tête détectée ; objet recompilé, résultat 42 → 43 |

La suite CTest ordinaire ignore le cas API sans environnement dédié et le coffre
réel dans la session réseau du bac à sable. Ces deux cas ont été exécutés
séparément avec succès, comme détaillé dans le tableau ; les 21 suites ne doivent
pas être interprétées comme une absence de cas ignorés dans ce lancement ordinaire.

Le parcours API utilise la vraie application FastAPI du worktree, une base SQLite
et des racines de stockage créées sous un nom unique. Il vérifie le login cookie/CSRF,
les organisations/espaces/projets, une conversation avec refus honnête d'un fournisseur
non configuré, une mission et sa tentative, le budget, une automatisation en pause,
le téléchargement authentifié et la déconnexion. Aucun fournisseur de production n'est
appelé. Le décor worker est synthétique et déclaré tel ; il ne prouve pas une exécution
d'Hermes ou d'un worker distant.

Livrable testé : **180 224 octets**, SHA-256
`f3892d09e466289becaba76e700d44b85afa060e59d589a7b0c73b791fe9d907`.

Journaux locaux conservés (ignorés par Git, sans promesse de disponibilité sur un autre poste) :

- `.test-tmp/merge-baseline-sqlite.xml` et `.log` ;
- `.test-tmp/desktop-contracts.xml` ;
- `.test-tmp/native-final-scoped-build.log` et `native-final-scoped.log` ;
- `.test-tmp/desktop-journey-e9c4c89486b240f49017bb16aae70c47/` : `result.json`,
  `qt-journey.log`, `qt-journey.xml`, `api.log` ;
- `.test-tmp/tst_session_persistence-detail.log` : reprise explicite dans la session
  Windows locale, entrée de coffre de test supprimée ;
- `.test-tmp/msvc-header-deps-8561d27671674058893ffc4f775e3814/result.json`.

## Incidents conservés et corrections

Les premières compilations ont relevé des conversions implicites de chaînes Qt,
des bornes numériques ambiguës sous MSVC et des assertions HTTP sensibles à la casse.
Ces erreurs ne sont pas présentées comme des passages réussis.

Un cache CMake contenait un préfixe français de `/showIncludes` mal décodé. Ninja
ne voyait alors plus certaines dépendances aux en-têtes : plusieurs anciens objets
se liaient à une bibliothèque modifiée et provoquaient des plantages. Une reconstruction
complète a supprimé ces plantages. L'initialisation MSVC impose maintenant une console
UTF-8 ; le test dédié prouve la recompilation après modification d'un en-tête.
Voir [la récupération de cache](desktop-msvc-cache-recovery.md).

La revue a aussi corrigé la conservation des commandes incertaines pendant une
relecture de session, l'invalidation des réponses d'une ancienne origine, le terminal
réentrant des erreurs 401/403 et le refus des faux flux SSE (HTML, redirections).
Les suites natives utilisent de vrais serveurs HTTP loopback pour ces scénarios.
Les créations de projets et les liaisons d'extensions vérifient aussi les rôles
effectifs dans le projet ou son espace, avec refus explicite pour les lecteurs.

Le premier test du coffre sous une session Windows de type réseau a été **ignoré**
avec le refus explicite de `CredWriteW`. Sa reprise dans la session utilisateur locale
a réussi ; le saut initial ne vaut pas preuve du coffre.

## Paquets Windows locaux

Le paquet final est conservé dans `.test-tmp/package-0.10.0-verified-20260923/`.
L'archive embarque les DLL VC143 x64 redistribuables ; le premier paquet, qui ne
contenait qu'un installateur VC Redist, a été écarté. Les tests du helper vérifient
le déploiement réel et le refus d'un CRT ancien, incomplet ou x86.

| Fichier | SHA-256 |
|---|---|
| `AgentCompanyPlatform-Setup-0.10.0-x64.exe` | `6c41e7c7f2cc90c021d13b3aa59f5b4b34c19938db55f11084f8bbf7cd7d233d` |
| `AgentCompanyPlatform-Portable-0.10.0-x64.zip` | `e6e52aab3abc9c2a3e630a82853fb6e8d72266f2c3c2bf9543cb3bd1b5292278` |

Les 1 387 fichiers extraits ont été vérifiés et l'exécutable correspond au build
final. Le portable reste actif après huit secondes avec un `PATH` limité aux
dossiers Windows, sans variables Qt/QML héritées. Cela prouve ce démarrage local,
pas une inspection visuelle ni l'absence de SDK sur la machine. Les DLL effectivement
chargées n'ont pas été inventoriées. Les paquets sont **non signés** et ne sont pas
publiés sur GitHub Releases.

La première installation de test a été refusée par l'accès au registre du bac à
sable ; Inno Setup a effectué son rollback. Le test a aussi révélé que `/NOICONS`
ne suffisait pas pour les raccourcis déclarés avec `{autoprograms}` : les entrées
respectent désormais explicitement `WizardNoIcons`.

La reprise hors bac à sable a installé les 1 387 fichiers dans une cible neuve
sous `.test-tmp`, sans élévation et sans raccourci (`/CURRENTUSER /NOICONS`).
Installation et désinstallation : **code 0** ; empreintes des fichiers conformes,
entrée AppId et cible absentes après désinstallation. Les préférences du profil
réel étant déjà présentes, l'application installée n'a pas été lancée et leur
contenu n'a pas été lu. Cette recette locale ne vaut pas test d'un Windows propre.
Les preuves sont `inventory.json`, `portable-startup.json`, `install.json`,
`uninstall.json`, `file-metadata.json` et leurs journaux dans le dossier du paquet.

## Recette encore à distinguer

La capture visuelle de la fenêtre Qt n'a pas abouti : l'autorisation de l'outil
Computer Use a expiré. La prévisualisation native s'est ouverte sur le poste, puis
a été fermée par la limite de dix minutes du harnais. Cela ne remplace pas une
recette visuelle des interactions. Le test QML vérifie séparément le chargement des
pages et l'absence d'erreurs de bindings.

L'URL Railway de test reste à fournir. Aucune preuve de connexion Railway,
d'exécution d'Hermes/worker de production, de poste Windows propre ou de signature
de code n'est déduite des tests locaux. Les [26 constats ouverts du Lot H](lot-h-091-review-status.md)
et les [écarts de parité](native-desktop-parity.md) restent explicites.
La définition complète de « Desktop V1 terminé » n'est donc pas déclarée atteinte.
