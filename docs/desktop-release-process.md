# Publier une version du client desktop Windows

Public : mainteneur du dépôt. État de ce document : 18 septembre 2026.

> **Ce mécanisme n'a jamais été exercé.** Aucune étiquette `v0.8.0` ni `v0.9.0`
> n'existe dans ce dépôt ; les derniers tags présents vont de `v0.2.0` à `v0.7.0`,
> et aucun d'eux n'a produit de binaire. Le premier passage de
> `.github/workflows/desktop-release.yml` sera aussi son premier test.

## 1. Vue d'ensemble

```text
  étiquette vX.Y.Z poussée
            │
            v
  ┌──────────────────────────────────────────────────────────────┐
  │ .github/workflows/desktop-release.yml — windows-2022         │
  │                                                              │
  │ 1. contrôle du déclenchement (étiquette ou confirmation)     │
  │ 2. VERSION == étiquette  ──────────► sinon, arrêt            │
  │ 3. image de l'exécuteur conforme à toolchain.json            │
  │ 4. présence de apps/desktop                                  │
  │ 5. Qt épinglé, avec cache                                    │
  │ 6. compilation Release                                       │
  │ 7. tests Qt Test et Qt Quick Test ──► un échec, et c'est fini│
  │ 8. windeployqt (analyse explicite du répertoire QML)         │
  │ 9. signature de l'exécutable    — SI un certificat existe    │
  │10. archive portable .zip                                     │
  │11. installeur Inno Setup                                     │
  │12. signature de l'installeur    — SI un certificat existe    │
  │13. SHA256SUMS.txt                                            │
  │14. dépôt des artefacts du job (30 jours)                     │
  │15. publication EN BROUILLON avec ses trois fichiers          │
  └──────────────────────────────────────────────────────────────┘
            │
            v
  relecture humaine, puis « Publish release » à la main
```

Chaque étape en échec interrompt le job avant la suivante : c'est le comportement
par défaut de GitHub Actions, et **aucune étape de ce workflow ne le contourne**
par `continue-on-error`. Il n'existe donc aucun chemin par lequel un brouillon
serait créé après un test rouge.

## 2. Artefacts, et leurs noms exacts

| Fichier | Contenu |
|---|---|
| `AgentCompanyPlatform-Setup-<version>-x64.exe` | programme d'installation par utilisateur |
| `AgentCompanyPlatform-Portable-<version>-x64.zip` | arbre déployé par `windeployqt`, exécutable compris |
| `SHA256SUMS.txt` | empreintes SHA-256 des deux fichiers ci-dessus |

Ces noms sont fabriqués à un seul endroit, `scripts/package-desktop.ps1`, à partir
de `packaging/windows/toolchain.json` (`product.artifactPrefix`,
`product.architectureSuffix`) et du fichier `VERSION`. Le workflow de publication
les recompose selon la même règle et **refuse de créer le brouillon** si l'un des
trois manque à l'appel.

Le format de `SHA256SUMS.txt` est celui de `sha256sum` : empreinte minuscule, deux
espaces, nom de fichier. Il est donc vérifiable aussi bien par `Get-FileHash` que
par `sha256sum -c SHA256SUMS.txt`.

## 3. Publier, pas à pas

### 3.1 Avant d'étiqueter

1. `apps/desktop` est fusionné et `.github/workflows/desktop-ci.yml` est vert sur la
   révision visée. C'est la seule preuve de compilation disponible.
2. `VERSION` porte la version à publier.
3. `CHANGELOG.md` décrit la version, avec ses rubriques « Ajouté », « Sécurité »,
   « Vérifié localement » et « Limites connues ».

### 3.2 Étiqueter

```bash
git tag v0.9.0
git push origin v0.9.0
```

L'étiquette doit avoir la forme `vX.Y.Z`. Le workflow compare `VERSION` à
l'étiquette privée de son `v` et **s'arrête sans rien fabriquer** en cas d'écart :

```text
Le fichier VERSION porte '0.9.0' alors que l'étiquette v0.9.1 annonce '0.9.1'.
Aucun artefact ne sera fabriqué.
```

### 3.3 Déclenchement manuel

Il existe pour rejouer une fabrication sur une étiquette déjà poussée, par exemple
après un incident d'exécuteur. Il exige deux saisies :

- `tag` : l'étiquette, qui doit **déjà exister** — le `checkout` porte sur
  `refs/tags/<tag>` et échoue sinon ;
- `confirmation` : exactement `PUBLIER-BROUILLON`, comparé en respectant la casse.

Il ne permet donc pas de publier depuis une branche, ni depuis une étiquette
inexistante.

Le job s'exécute dans l'environnement GitHub `desktop-release`. Y ajouter un
*required reviewer*, dans les réglages du dépôt, impose une approbation humaine
**avant** la fabrication ; sans cela, la seule barrière humaine reste le brouillon.

### 3.4 Relire le brouillon

Le workflow crée une publication **en brouillon** : elle n'est visible que des
mainteneurs et n'apparaît sur aucun flux. Avant de la publier :

1. les trois fichiers sont présents et leur taille est plausible ;
2. `SHA256SUMS.txt` correspond aux fichiers joints — retéléchargez-les et
   recalculez, ne faites pas confiance au journal du job ;
3. les notes indiquent le bon état de signature ;
4. sur un poste Windows propre, l'installeur s'installe sans élévation, crée son
   entrée de menu Démarrer, se désinstalle proprement, et l'archive portable se
   lance sans installation préalable.

Le point 4 n'a jamais été effectué pour ce produit ; il ne peut pas l'être avant
qu'un binaire existe.

### 3.5 Publier

Bouton **Publish release** sur le brouillon. Il n'existe aucune automatisation qui
le fasse à votre place, et il n'en existera pas : une publication est une décision
humaine.

## 4. Signature de code

### 4.1 État actuel

**Aucun certificat de signature de code Windows n'existe pour ce produit.** Ni
certificat, ni secret, ni procédure d'approvisionnement. C'est un délai externe,
pas une tâche de développement.

Tant que c'est le cas, la chaîne fabrique et publie des binaires **non signés**, et
le dit à trois endroits : un `::warning::` dans le journal du job, un message en
clair dans la sortie de `scripts/package-desktop.ps1`, et un paragraphe explicite
dans les notes de la publication. Rien ne prétend qu'un binaire est signé.

### 4.2 Conséquence côté Windows

Microsoft Defender SmartScreen évalue la réputation des fichiers téléchargés et de
leur signature. La documentation Microsoft l'énonce ainsi : si une URL, un fichier,
une application ou un certificat possède une réputation établie, l'utilisateur ne
voit aucun avertissement ; sans réputation, l'élément est marqué comme présentant un
risque plus élevé et un avertissement lui est présenté
([Microsoft Learn, Microsoft Defender SmartScreen](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/),
consultée le 18 septembre 2026).

Concrètement, pour un binaire non signé et nouvellement publié : écran bleu
« Windows a protégé votre ordinateur », nécessité de passer par « Informations
complémentaires », et méfiance légitime des utilisateurs. Un certificat EV établit
la réputation immédiatement ; un certificat OV standard la construit au fil des
téléchargements. Ce choix a un coût et un délai, et il n'est pas tranché.

### 4.3 Activer la signature

Deux secrets de dépôt, tous deux nécessaires :

| Secret | Contenu |
|---|---|
| `WINDOWS_SIGNING_PFX_BASE64` | certificat PKCS#12 encodé en base64 |
| `WINDOWS_SIGNING_PASSWORD` | mot de passe du PKCS#12 |

Dès que `WINDOWS_SIGNING_PFX_BASE64` est renseigné, la signature devient active
sans autre modification. Si ce secret est présent **sans** le second, le workflow
s'arrête avec le code `7` : il ne publie pas de binaire non signé en le faisant
passer pour signé.

Précautions tenues par la chaîne :

- le `.pfx` est écrit dans `RUNNER_TEMP` et supprimé dans un bloc `finally`, y
  compris en cas d'échec ;
- le mot de passe n'est **jamais** passé en argument de ligne de commande : il
  transite par la variable d'environnement `ACP_SIGNING_PASSWORD`, et l'import passe
  par `Import-PfxCertificate`, qui prend une chaîne sécurisée ;
- `signtool` est ensuite appelé avec `/sha1 <empreinte>`, jamais avec `/p` ;
- le certificat importé est retiré du magasin de l'utilisateur dans un bloc
  `finally` ;
- signature en `SHA256`, horodatage RFC 3161 par `/tr` et `/td`, conformément à la
  [documentation SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
  consultée le 18 septembre 2026, qui impose `/fd` et `/td`.

L'ordre importe : l'exécutable est signé **avant** d'être empaqueté, puis
l'installeur est signé **après** sa fabrication. Les empreintes SHA-256 sont
calculées en dernier, sur les fichiers définitivement signés.

## 5. Choix de la technologie d'installeur

Retenu : **Inno Setup 6**, script `packaging/windows/AgentCompanyPlatform.iss`.

Pourquoi pas Qt Installer Framework, qui était la piste évidente :

1. **Licence.** Le cadre d'installation de Qt est distribué sous licence
   commerciale ou sous GPL. L'installeur produit embarque son code : sous GPL, c'est
   l'installeur lui-même qui hérite des obligations correspondantes. L'audit signale
   déjà que la décision de licence Qt n'est pas prise (question ouverte n° 18) ;
   faire dépendre le format de distribution d'une décision non prise serait bâtir
   sur du sable. Inno Setup est publié sous une licence permissive qui n'impose rien
   au logiciel distribué.
2. **Machinerie.** Le cadre Qt est conçu pour des dépôts en ligne et une mise à jour
   par composants, avec un outil de maintenance résident. Nous distribuons un binaire
   unique sans mise à jour automatique — et l'audit interdit toute mise à jour
   silencieuse. C'est de la complexité sans emploi.
3. **Installation sans élévation.** Inno Setup l'obtient par une seule directive,
   `PrivilegesRequired=lowest`, documentée et éprouvée.
4. **Disponibilité.** L'image `windows-2022` des exécuteurs GitHub fournit déjà
   InnoSetup 6.7.1 ; le cadre Qt devrait être téléchargé à chaque exécution.

Ce que le script produit, et qui est vérifiable une fois un binaire disponible :

| Exigence | Mise en œuvre |
|---|---|
| Installation par utilisateur, sans élévation | `PrivilegesRequired=lowest` ; `{autopf}` se résout en `%LOCALAPPDATA%\Programs` |
| Installation pour toute la machine, si voulue | `PrivilegesRequiredOverridesAllowed=commandline`, donc `/ALLUSERS` par un administrateur |
| Entrée de menu Démarrer | `[Icons]` sur `{autoprograms}` |
| Raccourci Bureau optionnel | `[Tasks] desktopicon`, case **décochée** par défaut |
| Entrée de désinstallation | `AppId` stable et `UninstallDisplayName` |
| Désinstallation propre | `[UninstallDelete]` sur `{app}`, qui retire aussi les caches QML écrits à l'exécution |
| Configuration non sensible préservée | rien n'est supprimé sous `%APPDATA%` |
| Interface en français | `compiler:Languages\French.isl`, seule langue embarquée |

`AppId` vaut `{53810A6E-FA9C-4595-9C53-74A78EB4D1A8}` et **ne change jamais** : le
modifier ferait apparaître deux entrées de désinstallation sur les postes déjà
équipés.

Le contenu installé est exactement celui produit par `windeployqt`, qui analyse le
répertoire QML source (`--qmldir`) pour n'embarquer que les modules réellement
importés, et `--compiler-runtime` pour que l'archive portable fonctionne sur un
poste dépourvu de redistribuable MSVC. Aucun fichier n'est ajouté à la main dans le
script d'installation.

## 6. Notes de version

Elles proviennent du gabarit versionné
`packaging/windows/release-notes.template.md`, dont le workflow ne remplace que
quatre jetons : version, préfixe d'artefact, suffixe d'architecture, et le
paragraphe d'état de signature. Aucune mise en forme n'est reconstruite dans le
YAML, où l'indentation du bloc la casserait.

Le gabarit porte une section « Ce que cette publication ne prouve pas ». Elle n'est
pas décorative : elle rappelle qu'aucun serveur n'a été déployé et qu'aucune
installation n'a été vérifiée sur un poste tiers. Elle doit être mise à jour quand
ces faits changent — et pas avant.

## 7. Ce qui a été vérifié pour ce document

Exécuté le 18 septembre 2026 : validité YAML de `desktop-release.yml`, analyse
syntaxique de `scripts/package-desktop.ps1`, et exécution de ce script sur un poste
sans Qt, qui refuse avec le code `3` en nommant le répertoire de compilation absent.

Jamais exécuté, et donc jamais prouvé : `windeployqt`, `ISCC`, `signtool`, la
création d'un brouillon de publication, et le workflow dans son ensemble.

## 8. Limites connues

1. Aucun certificat de signature — section 4.1.
2. `scripts/check_version.py` ne couvre pas la version du client desktop ; seul le
   workflow de publication rapproche l'étiquette de `VERSION`.
3. L'image `windows-2022` est déclarée deux fois (`runs-on` et `toolchain.json`) ;
   une étape refuse la divergence, mais GitHub ne permet pas de supprimer le doublon.
4. Aucune vérification automatique n'atteste que l'installeur s'installe et se
   désinstalle réellement. Un test d'installation en CI (installation silencieuse,
   contrôle des raccourcis, désinstallation, contrôle des restes) est possible et
   n'est pas livré ici.
5. Le workflow ne publie que sur GitHub Releases. Aucun autre canal — ni winget, ni
   Microsoft Store, ni dépôt interne — n'est prévu.
