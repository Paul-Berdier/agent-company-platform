# Reprise du travail sur un autre poste

État du **23 septembre 2026**, Europe/Paris. Lire aussi `CLAUDE.md`.
Ce relevé remplace l'état du 18 septembre : le client natif et les écrans métier
existent désormais. Le chantier courant est **0.10.0 en préparation**.

La reprise courante se poursuit dans `.claude/worktrees/desktop-completion`,
branche locale `codex/desktop-chat-projects`, à partir du lot fonctionnel
`fc12525`. Lire la [recette conversations/projets](desktop-chat-projects-2026-09-23.md)
pour la nouvelle DA, les parcours, les correctifs modaux et les preuves les
plus récentes : **3 037 tests Python réussis / 70 ignorés, 23 suites Qt,
492 tests Node**. Les deux parcours Windows à vrais clics et clavier sont verts.
Le checkout principal conserve son travail Pixel Office, hors de cette intégration.

Reprise fonctionnelle sur `codex/functional-completion`, suivie par la
[PR #11](https://github.com/Paul-Berdier/agent-company-platform/pull/11) : lire le
[bilan du 23 septembre](functional-completion-2026-09-23.md) avant les relevés
historiques ci-dessous. Missions supervisées et équipes explicites, checkpoints
d'effets, restitution métier, compétences et proxy MCP sont raccordés dans
l'arbre de travail. Suite Python complète : **3 025 réussis, 70 ignorés**, en quatre
partitions disjointes sur bases jetables. Qt : **22 suites sur 22** et parcours
Qt/API réelle **3 réussis**, avec captures d'interactions distinctes. Le web donne
**325 tests réussis**, typage et construction verts. La validation MCP ciblée donne
**36 réussis, 0 ignoré** après revue. Ces groupes ciblés recouvrent la suite complète.
Le commit fonctionnel `47de619` est validé par les CI plateforme `35856502360`
et desktop `35856502324`, toutes deux vertes. Le bilan contient les liens directs,
les empreintes du paquet local final et les limites de son installation.

La pile locale et Hermes sont installés et ont démarré sur loopback. Hermes est
joignable mais **dégradé**, sans modèle configuré ; **aucun Run génératif payant**
n'a été lancé. Voir [la procédure locale](local-runtime.md). Une équipe déjà
commencée reste bloquée à la reprise, avec preuves conservées et sans fusion
automatique. Les **26 constats Lot H** ne sont pas déclarés clos ; N2-5 conserve
son défaut de récupération d'un claim incertain malgré le correctif de délai.
La V1 reste à terminer.

## 1. État Git et preuves connues

| Élément | État relevé |
|---|---|
| Lot H 0.9.0 historique | PR #8 fusionnée au commit `94ce876`, tag `v0.9.0` posé le 18 septembre |
| Durcissement Lot H | PR #9 fusionnée dans `main` au commit `3f8e5fe` |
| CI de ce durcissement | Run `35799431367` observé vert |
| Intégration desktop | PR #10 fusionnée dans `main` au commit `0bc9dcb` ; branche validée par les CI `35806313489` et `35806313531` |
| Ouverture de version | `0.10.0`, commit `4915136` |
| Python de l'arbre combiné | 2 896 réussis, 70 ignorés, 835 secondes |
| Ancienne fondation native | 10 suites sur 10 réussies ; ce relevé précède les nouveaux écrans |
| Nouvel arbre natif | Relevé final : 21 suites sur 21, 54,82 secondes ; build Release réussi |
| Session et coffre Windows réel | 24 tests sur 24, 0 ignoré, hors sandbox |

Un parcours Qt contre une vraie API SQLite jetable a aussi réussi le 23 septembre :
cookie/CSRF, projets, conversation sans réponse fournisseur inventée, mission,
budget, automatisation en pause, export exact de 180 224 octets et déconnexion.
Rapports locaux sous `.test-tmp/desktop-journey-e9c4c89486b240f49017bb16aae70c47/` :
`result.json` annonce `passed`, Qt exécuté, code 0 ; `qt-journey.log` donne
3 réussis, 0 échec, 0 ignoré en 1 663 ms ; le lanceur complet prend 9,7 secondes.
Ce parcours reste distinct de la
suite native et ne remplace pas une recette visuelle ou Railway.

Les commits de fusion et l'ouverture de version ne prouvent pas une publication
0.10.0. Consulter `git status`, `git log` et
[le relevé final](desktop-validation-2026-09-23.md) avant de reprendre :
l'intégration peut avoir avancé depuis cette note.

Le lot fonctionnel précédent partait de `main` au commit `aa55942` ; la branche
actuelle de reprise et ses validations sont indiquées en tête de document.
Le checkout principal conserve sa branche et son chantier Pixel Office. Les autres worktrees historiques
peuvent contenir des travaux partiels ; ne pas les supprimer, réinitialiser ou
réappliquer sans examiner leurs différences. Le chantier pixel local reste
conservé hors périmètre. Indexer les fichiers explicitement.

## 2. Ce qui est implémenté et ce qui reste

L'[audit fonctionnel initial](functional-audit-2026-09-23.md) documente huit
défauts sur `ce42ae2`. Le [bilan de correction](functional-completion-2026-09-23.md)
distingue les raccordements désormais implémentés de leur validation réelle.
Hermes est maintenant installé, avec profil dédié ; son diagnostic dégradé
empêche encore d'annoncer la chaîne générative utilisable. Lire ces deux relevés
avant de brancher un coffre de notes ou de clôturer les constats.

Les viewmodels et pages natifs couvrent projets, conversations, missions,
tentatives/Studio, livrables, agents/workers/fournisseurs, MCP/compétences,
approbations, alertes, budgets et automatisations. Voir
[la matrice de parité](native-desktop-parity.md) pour les actions et omissions
précises : « écran livré » ne signifie pas toutes les routes API disponibles.

Les réglages incluent la mémorisation de session **facultative** dans le coffre
Windows. La restauration doit relire la session serveur et n'attribue aucun
droit depuis le stockage local. Les 24 tests de session passent sans ignoré
hors sandbox, dont le cycle réel lecture/écriture/suppression dans le coffre.
Sous sandbox, ce cas était ignoré car `CredWrite` refusait la session
d'exécution ; ne pas confondre cette limitation avec une preuve du coffre.

`UpdateService` vérifie les publications GitHub à la demande, compare les
versions sémantiques, affiche les notes brutes et ouvre la publication officielle.
Il n'intègre aucun téléchargement de paquet ou installateur.

Restent à achever ou prouver :

1. Compléter la recette visuelle des interactions. L'intégration dans `main` et
   les CI de la branche sont acquises ; elles ne constituent pas une publication.
2. Installer un déploiement de test, puis réaliser le parcours distant ; aucun
   déploiement ACP n'est actuellement installé sur le périmètre utilisateur.
3. Installation et mise à jour sur un Windows propre.
4. Signature Windows : aucun certificat disponible, binaires non signés.
5. Les **26 constats Lot H encore ouverts**, décrits dans
   [le registre de revue](lot-h-091-review-status.md), sans les confondre avec
   les constats déjà corrigés.
6. Publication éventuelle après preuves et recette de `CLAUDE.md` ; aucune V1
   complète ou publication 0.10.0 finalisée n'est annoncée ici.

Aucun travail Godot/pixel n'est engagé dans cette phase.

## 3. Chaîne d'outils Windows

La référence est `packaging/windows/toolchain.json` : Qt **6.8.3**
`win64_msvc2022_64`, MSVC 2022, CMake et Ninja. Les workflows desktop
existent et utilisent `windows-2022`. Inno Setup sert à l'empaquetage.

Sur le poste de reprise, Python doit venir de python.org et non de l'alias
Microsoft Store : le Python empaqueté avait empêché la clôture attendue par
les Job Objects des tests worker. Créer le venv du projet avec cet exécutable,
puis utiliser ce venv explicitement.

Installation de Qt dans un environnement d'outillage séparé :

```powershell
python -m venv "$env:USERPROFILE\.acp-tools\aqt-venv"
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m pip install aqtinstall
& "$env:USERPROFILE\.acp-tools\aqt-venv\Scripts\python.exe" -m aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 --outputdir "$env:USERPROFILE\Qt"
$env:QT_ROOT_DIR = "$env:USERPROFILE\Qt\6.8.3\msvc2022_64"
```

Les scripts du dépôt chargent l'environnement MSVC et vérifient leurs prérequis.
`setup-desktop.ps1` diagnostique les outils ; il ne les installe pas.

```powershell
./scripts/setup-desktop.ps1
./scripts/build-desktop.ps1 -Configuration Release
./scripts/test-desktop.ps1 -Configuration Release
./scripts/package-desktop.ps1 -Configuration Release -DryRun -OutputDir "$env:TEMP\acp-dist"
```

Release traite les avertissements du compilateur comme des erreurs. Un succès
Debug seul ne le remplace pas. Éviter les builds concurrents dans le même
répertoire CMake. Le répertoire local Release est
`apps/desktop/build/windows-msvc-release` ; les exécutables de tests sont
directement dans ce répertoire.

Sur ce poste, un exécutable Qt Test peut échouer sans rien écrire sur stdout.
Utiliser alors `-o <chemin-absolu-du-rapport>,txt` et lire le rapport. Un lancement
Python doit transmettre un environnement copié explicitement et ajouter
`$env:QT_ROOT_DIR\bin` au `PATH`. Cela n'autorise pas à considérer une sortie
vide comme une réussite.

## 4. API locale et bases jetables

Préparer le venv backend puis suivre [la persistance](persistence-and-backup.md)
pour le moteur et le schéma. Le desktop requiert une API déjà démarrée et un
compte existant ; le premier propriétaire s'amorce par API/web/CLI.

```powershell
./scripts/dev-desktop.ps1 -Configuration Release
```

Pour un serveur local dédié, saisir `http://127.0.0.1:8000` et activer
explicitement le bouclage HTTP dans l'interface. L'API locale utilise alors
`ACP_SESSION_COOKIE_SECURE=0` ; un déploiement distant doit employer HTTPS.

**La base `./acp.db` de la racine contient des données de développement.**
Ne jamais lancer un script ponctuel, `TestClient(app)`, un parcours ou une API de
vérification sans lui affecter une base jetable via `ACP_DATABASE_URL`.
Les tests ne doivent jamais cibler une base d'usage réel.

La suite utilise SQLite temporaire sans `ACP_TEST_DATABASE_URL`. Avec une URL
`postgresql+psycopg://` dédiée, les tests ordinaires créent des schémas éphémères.
Les tests qui remettent `public` à zéro passent par une garde : refus si la base
correspond aux variables d'application relevées au lancement, ou si `public`
est occupé sans marqueur `acp-test-database`. Une base vide peut être marquée
par l'outillage. Ne jamais marquer une base peuplée sans avoir vérifié qu'elle
est réellement jetable.

PostgreSQL 16 natif a été retrouvé sur ce poste en bouclage, port **55432**, avec
les outils sous `$env:USERPROFILE\.acp-tools\pg16\pgsql\bin`. Les bases
`acp_wf_*` et `acp_verify` sont des cibles de travail historiques, pas une
autorisation de les effacer sans contrôle. Ne pas réutiliser une base occupée
par un autre lot. Docker reste une autre possibilité documentée ; les outils
`pg_dump` et `pg_restore` ne sont plus supposés exister uniquement en conteneur.

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
```

Utiliser `--basetemp` dans un répertoire dédié du worktree si les permissions
du temporaire Windows échouent. Ne pas lancer plusieurs suites complètes
concurrentes sur le poste : elles saturent les entrées/sorties et brouillent
le diagnostic. Les ignorés restent consignés séparément des tests réussis.

## 5. Repères et pièges conservés

- La fondation du 18 septembre a déjà compilé Debug/Release et produit un
  portable/installeur local ; son CI desktop `35348431165` était vert sur
  `4b3d2a6`. C'est une preuve historique, pas celle des écrans du 23 septembre.
- L'installeur n'a pas encore été éprouvé sur un Windows propre ; l'archive
  portable historique avait démarré sans variables Qt sur le poste de travail.
- Les fins de ligne du code desktop doivent rester LF. Une redirection Windows
  peut produire du CRLF ; vérifier les fichiers avant commit.
- MSVC Release applique `/W4 /WX` et les interdictions de conversions implicites
  Qt : employer `QStringLiteral` pour les chaînes QString.
- Pour Ninja/MSVC, garder la langue des sorties `/showIncludes` cohérente entre
  configuration et compilation. Un cache configuré avec un préfixe français puis
  compilé en anglais peut laisser des dépendances incorrectes et des objets périmés.
  Le rebuild central utilise `VSLANG=1033` et une configuration propre ; ne pas
  réutiliser aveuglément le cache du poste précédent.
- Qt Quick expose les contrôles à Windows UI Automation : `ValuePattern` pour
  les champs, `InvokePattern` pour les boutons, `TogglePattern` pour les cases.
  Un processus de capture doit être conscient du DPI pour éviter une image rognée.
- Inno Setup installé par utilisateur se trouve généralement sous
  `%LOCALAPPDATA%\Programs\Inno Setup 6`.
- Un message Git de propriété douteuse peut nécessiter
  `git -c safe.directory=<chemin-du-worktree> …` pour ce worktree précis.
- Les fichiers locaux du pixel-office ne doivent pas se retrouver dans un
  commit desktop par un `git add -A`.

Documents à relire : [validation](desktop-validation-2026-09-23.md),
[parité](native-desktop-parity.md), [architecture](native-desktop-architecture.md),
[sécurité](desktop-security.md), [mise à jour](desktop-update-process.md),
[constats Lot H](lot-h-091-review-status.md) et `CHANGELOG.md`.
