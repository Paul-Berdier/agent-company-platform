# Publier le client desktop Windows

Procédure mainteneur mise à jour le **12 octobre 2026**, pour le lot **1.1.0 — Pixel Atelier**.
Pour installer une version existante, lire [Mettre à jour vers 1.1](mettre-a-jour-1.1.md).

## État vérifié et portée

Le [run Desktop Release de v1.0.0](https://github.com/Paul-Berdier/agent-company-platform/actions/runs/38015121231)
a réussi le 10 octobre 2026 et a produit l'installeur, le portable et leurs sommes de contrôle.
Lors du relevé du 12 octobre, cette publication était encore en brouillon ; le tag `v1.0.1`
existait sur `85b458b`, sans run Desktop Release correspondant. Ce relevé historique ne décrit
pas l'état d'une publication ultérieure : consulter les [publications GitHub](https://github.com/Paul-Berdier/agent-company-platform/releases)
et le run de l'étiquette que l'on veut distribuer.

Une fusion, une étiquette, un artefact CI et une publication publique sont quatre étapes
distinctes. Le bouton de mise à jour du client ne voit pas les brouillons. La ligne 0.10 reste
archivée sous `archive/acp-0.10.0-avant-hermes` ; les preuves anciennes n'établissent pas la
validité du paquet courant.

## Avant le tag

1. Suivre `CLAUDE.md` : branche issue de `main`, commit d'ouverture de version, copies
   synchronisées, commits de travail, changelog complet et contrôles verts. Ne pas modifier
   le moteur Pixel Office gelé pour lui donner la version du produit.
2. Vérifier `python scripts/check_version.py`, `python scripts/generer_themes.py --check`,
   les tests du lot et les workflows attendus : CI, Desktop CI, Image Hermes et Image de
   l'exécutant. Les preuves doivent identifier le commit réellement proposé.
3. Les déclencheurs `push` ciblent `main` et `refonte/**`. Une branche `codex/**` nécessite
   un lancement manuel des workflows pour obtenir leurs résultats avant ouverture de PR ;
   une PR vers `main` déclenche ensuite les contrôles applicables à ses chemins.
4. Préparer `CHANGELOG.md` : Ajouté, Modifié, Corrigé, Sécurité, Vérifié localement,
   Limites connues. Relire le gabarit `packaging/windows/release-notes.template.md`.
5. Fusionner la PR validée par **commit de fusion**. Le tag annoté porte sur ce commit,
   jamais sur une tête antérieure ni sur une branche non fusionnée.

La hausse globale de version touche aussi les manifestes Hermes et le poste. Une fusion
sur la branche surveillée par Railway peut déclencher une reconstruction serveur ; la
publication du desktop ne remplace pas les contrôles du [manuel d'exploitation](exploitation.md).
Aucune action de compte Railway n'est réalisée par les workflows desktop.

## Déclencher la fabrication

Exemple pour 1.1.0, après fusion validée, en remplaçant le SHA :

```powershell
git tag -a v1.1.0 <SHA_DU_COMMIT_DE_FUSION> -m "Agent Company Platform 1.1.0 - Pixel Atelier"
git push origin v1.1.0
```

`.github/workflows/desktop-release.yml` se déclenche au push d'un tag `v*` et exige que
`VERSION` corresponde exactement au tag privé de son `v`. Il utilise l'environnement
GitHub `desktop-release` ; un éventuel reviewer obligatoire est défini dans les réglages
GitHub, pas dans le YAML.

Pour rejouer la fabrication d'une étiquette existante sans publication existante :

```powershell
gh workflow run desktop-release.yml --ref main -f tag=v1.1.0 -f confirmation=PUBLIER-BROUILLON
```

Le workflow checkout l'étiquette demandée. Ce geste ne fabrique pas depuis la tête de
`main`. Sa dernière étape emploie `gh release create` : il n'est pas conçu pour remplacer
silencieusement un brouillon déjà présent. Examiner celui-ci avant tout rejeu ; ne pas
déplacer un tag publié pour contourner un échec.

## Ce que construit le workflow

La chaîne est épinglée dans `packaging/windows/toolchain.json` : runner Windows,
MSVC, Qt et Inno Setup. Le workflow vérifie l'image du runner, compile en Release,
exécute les tests Qt Test/Qt Quick Test, puis appelle `scripts/package-desktop.ps1`.
Un échec interrompt la fabrication avant la création du brouillon.

Le packaging analyse les imports avec `windeployqt --qmldir`, puis copie les DLL VC143
x64 de l'installation Visual Studio correspondant au cache CMake. Il ne dépend pas
d'un VC Redist laissé à exécuter dans l'archive portable. L'exécutable final, les
bibliothèques Qt et les modules QML constituent le même contenu pour les deux formats.

| Fichier | Usage |
| --- | --- |
| `AgentCompanyPlatform-Setup-<version>-x64.exe` | Installation Windows par utilisateur |
| `AgentCompanyPlatform-Portable-<version>-x64.zip` | Dossier autonome à extraire |
| `SHA256SUMS.txt` | SHA-256 des deux fichiers finaux |

Les noms proviennent de `VERSION` et du préfixe/suffixe dans `toolchain.json`. Les trois
fichiers sont exigés avant la création du brouillon. Les artefacts du job restent 30 jours ;
ceux d'un Desktop CI à blanc restent 7 jours. Une durée de rétention CI n'est pas une
publication durable.

## Pixel Atelier et ressources graphiques

Le checkout public contient les thèmes, l'emblème et l'illustration ACP originale.
Une CI propre embarque `apps/desktop/resources/images/atelier-fallback.png` sous l'alias
`qrc:/atelier/atelier.png`. Elle ne reçoit ni le ZIP de l'utilisateur ni ses fichiers ignorés.

Un build local ayant exécuté `apps/desktop/tools/import-atelier-assets.ps1` peut embarquer
la scène LimeZu présente dans `resources/atelier-local/`. Ce dossier reste exclu de Git.
Le build local et le build CI peuvent donc présenter un décor différent avec le même code.
Les notes d'un paquet construit localement doivent préciser ce choix ; ne pas remplacer
un artefact CI par un binaire différent en conservant son ancienne empreinte.

Les licences permettent l'emploi dans un projet mais pas la republication des ressources
comme pack. Ne joindre aucun ZIP source, atlas ou PNG LimeZu séparé à une release. Pour un
paquet utilisant ces ressources, conserver le crédit **Pixel art : LimeZu — limezu.itch.io**.
La page officielle actuelle de Modern Office exige le crédit ; le ZIP fourni contient
un texte plus ancien qui l'apprécie. Le crédit commun couvre les deux sélections.
Détails : [provenance et import](../apps/desktop/resources/images/README.md),
[Modern Office](https://limezu.itch.io/modernoffice),
[Modern Interiors](https://limezu.itch.io/moderninteriors).

## Signature et installation

Sans certificat configuré, les paquets sont **non signés**. `-DryRun` produit également
des paquets non signés. Le journal et les notes doivent le dire ; SHA-256 contrôle
l'intégrité de la copie, pas l'identité cryptographique de l'éditeur.

La signature utilise les secrets `WINDOWS_SIGNING_PFX_BASE64` et
`WINDOWS_SIGNING_PASSWORD`, tous deux requis lorsqu'elle est activée. Le PFX temporaire
et son import sont retirés dans `finally`. Le mot de passe n'est pas un argument de
commande. L'exécutable est signé avant l'empaquetage, l'installeur ensuite, puis les sommes
sont calculées. Windows peut afficher un avertissement pour un paquet sans réputation ;
ne pas promettre que les sommes de contrôle le supprimeront.

Inno Setup conserve `AppId={53810A6E-FA9C-4595-9C53-74A78EB4D1A8}` : une nouvelle version
peut mettre à jour l'installation existante. Ce GUID ne change pas. Installation par
utilisateur, sans élévation ; `/ALLUSERS` reste un choix explicite de l'administrateur.
`CloseApplications=yes` et `RestartApplications=no` sont conservés.

Les préférences ne résident pas dans le répertoire du programme. Le code utilise
`QSettings` natif : sous Windows, il s'agit du registre utilisateur, avec les noms
`Agent Company Platform` / `Station de travail`, inchangés. La session mémorisée utilise
le Gestionnaire d'identifiants Windows, avec consentement. Une désinstallation ne doit
pas être présentée comme nécessaire à la mise à jour.

## Vérifier le brouillon, puis publier

1. Relever tag, SHA du commit de fusion et URL du run Desktop Release réussi.
2. Vérifier les trois pièces jointes et recalculer les empreintes des fichiers téléchargés.
3. Relire les notes : version, contenu, décor utilisé, signature et limites exacts.
4. Éprouver le portable et l'installeur sur un Windows propre, puis la mise à jour depuis
   1.0.x avec préférences existantes. Tant que ce parcours n'a pas été exécuté, le dire.
5. Après décision de publication, rendre le brouillon public. Le workflow lui-même ne
   le fait pas. Vérifier ensuite que la release stable est accessible sans authentification
   et que l'ancien client la propose.
6. Consigner séparément les preuves CI, packaging, publication et essai d'installation.

Les tests contre un faux Hermes ne prouvent pas une vraie passkey, une session personnelle
ou le fonctionnement de Railway. Les contrôles réellement effectués pour Pixel Atelier
figurent dans [le relevé du lot](refonte/pixel-atelier.md).
