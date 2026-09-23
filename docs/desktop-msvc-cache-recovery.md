# Réparer un cache MSVC/Ninja localisé

Un cache CMake peut contenir un préfixe `/showIncludes` mal décodé, par exemple
`Remarque┬á: inclusion du fichier┬á:`. Ninja ne reconnaît alors plus les lignes
de dépendances émises par MSVC. Une modification d’en-tête peut laisser des
objets et des tests compilés contre une ancienne disposition mémoire, même si
la compilation incrémentale annonce un succès.

`Enter-AcpMsvcEnvironment` fixe désormais la page de codes de la console à
UTF-8 (`chcp 65001`) avant la configuration CMake et la compilation, même depuis
un Developer Shell déjà chargé. Il réaffirme cette configuration après le
lanceur Visual Studio. `VSLANG=1033` préfère l'anglais lorsque ses ressources sont
installées ; un poste portant seulement le pack français reste accepté. La
correction repose sur l'encodage commun, pas sur une langue supposée disponible.
Aucune installation ni modification d'un réglage global n'est effectuée.

Sur le poste de vérification, Python héritait bien de `VSLANG=1033` mais MSVC
restait français : seul `1036/clui.dll` était présent. Le passage de la page de
codes native 850 à 65001 a permis à Ninja de suivre effectivement les en-têtes.

Cette correction ne répare pas les fichiers déjà produits. Après fermeture des
binaires issus du dossier de build, repartir d’une détection CMake fraîche et
recompiler tous les objets. Depuis la racine du worktree, avec le chemin Qt réel :

```powershell
Import-Module ./packaging/windows/DesktopToolchain.psm1 -Force
if (-not (Enter-AcpMsvcEnvironment)) { throw 'MSVC absent' }
$qtPourRebuild = Resolve-AcpQtDirectory -QtDir 'C:/Qt/6.8.3/msvc2022_64'
if (-not $qtPourRebuild) { throw 'Qt absent' }
$env:CMAKE_PREFIX_PATH = $qtPourRebuild
$env:PATH = (Join-Path $qtPourRebuild 'bin') + ';' + $env:PATH
Push-Location apps/desktop
try {
    cmake --fresh --preset windows-msvc-release
    if ($LASTEXITCODE -ne 0) { throw 'Configuration échouée' }
    cmake --build --preset windows-msvc-release --clean-first
    if ($LASTEXITCODE -ne 0) { throw 'Recompilation échouée' }
    ctest --preset windows-msvc-release --output-on-failure
    if ($LASTEXITCODE -ne 0) { throw 'Tests échoués' }
}
finally { Pop-Location }
```

Appliquer la même procédure au préréglage Debug si son cache a été créé dans
l’ancien environnement. Ne pas corriger `rules.ninja` ou le cache à la main :
cela conserverait des objets potentiellement incompatibles et serait écrasé à
la configuration suivante.

Une régression dédiée, indépendante de Qt et de Pester, vérifie le comportement :

```powershell
./packaging/windows/tests/Test-DesktopToolchainDependencies.ps1
```

Le paramètre facultatif `-NinjaPath` choisit un exécutable Ninja précis, notamment
celui livré avec Visual Studio lorsque celui de WinGet est inaccessible.

Elle crée un mini-projet neuf sous `.test-tmp/msvc-header-deps-<uuid>`, initialise
un shell puis simule une préférence française héritée. Elle compile un programme
dont le retour dépend d’un en-tête, modifie uniquement cet en-tête et exige que
la compilation incrémentale produise la nouvelle valeur. `result.json` n’est
écrit comme réussi qu’après cette vérification effective.
