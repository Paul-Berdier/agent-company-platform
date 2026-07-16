# Installation des assets LimeZu (sous licence)

Les packs LimeZu sont payants et **ne sont jamais présents dans ce dépôt**
(licence : redistribution interdite). Le dépôt public démarre sur des
placeholders libres ; les assets premium s'installent localement.

## 1. Acheter et télécharger les packs

Sur [limezu.itch.io](https://limezu.itch.io/) :

| Pack | Archive attendue | Utilisé pour |
|---|---|---|
| Modern Interiors (complet) | `moderninteriors-win.zip` | personnages |
| Modern Office Revamped | `Modern_Office_Revamped_*.zip` | mobilier de bureau, room builder |
| Modern Exteriors | `modernexteriors-win.zip` | campus (arbres, bancs, props) |
| Modern User Interface | `modernuserinterface-win.zip` | HUD (Phase 6) |

## 2. Les déposer dans un dossier HORS du dépôt

```text
C:\AgentCompanyAssets\LimeZu\
├── moderninteriors-win.zip
├── Modern_Office_Revamped_v1.2.zip
├── modernexteriors-win.zip
└── modernuserinterface-win.zip
```

## 3. Lancer l'import

```powershell
npm run assets:import-limezu -- "C:\AgentCompanyAssets\LimeZu"
```

Le script :

- vérifie la présence des archives (échec explicite si l'une manque) ;
- extrait **uniquement** les éléments listés dans
  [`tools/limezu-mapping.json`](../../packages/pixel-office-engine/tools/limezu-mapping.json) ;
- découpe et repack en atlas ≤ 2048×2048 avec des identifiants logiques
  (`office.single.*`, `exterior.*`, `limezu-adam/walk-down/0`…) ;
- écrit tout sous `apps/web/public/assets/licensed/limezu/` (**gitignoré**) ;
- génère les manifests `limezu-*`, un `PROVENANCE.md` par pack et
  `import-report.json` (comptes, avertissements, dimensions, doublons) ;
- ajoute les packs à `packs.json` en **optional_packs** : absents ⇒ l'app
  retombe automatiquement sur les placeholders.

## 4. Vérifier

- ouvrir `http://localhost:5173/#/dev/assets` : les packs `limezu-*`
  apparaissent avec leur provenance ; sans import, un bandeau
  « Licensed assets not installed » s'affiche ;
- les agents utilisent les personnages LimeZu (mapping rôle → personnage
  défini dans `limezu-mapping.json`).

## Licences (résumé, vérifié dans chaque archive)

- usage commercial et non commercial autorisé (sauf NFT pour Modern UI) ;
- **redistribution interdite** → jamais dans git, jamais dans un artefact
  téléchargeable public ;
- **crédits requis** : voir la section Crédits du README.

## Adapter la sélection

Modifier `packages/pixel-office-engine/tools/limezu-mapping.json`
(personnages, filtres Exteriors, mapping rôle→personnage) puis relancer
l'import. Ce fichier est committé : il ne contient aucun pixel LimeZu,
seulement des chemins et des noms.
