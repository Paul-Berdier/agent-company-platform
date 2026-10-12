# Images de Pixel Atelier

`atelier-fallback.png` est une illustration originale ACP, dessinée par rectangles
sur une grille de 240 × 120 puis agrandie exactement ×2 sans lissage. Elle ne
contient aucun pixel de LimeZu. Elle est versionnable et permet de construire le
desktop sans pack acheté. La source reproductible est
`../../tools/generate-atelier-brand.ps1` ; elle produit aussi l'emblème ACP.

La scène d'accueil est décorative : ses personnages et ses écrans ne représentent
ni des agents connectés, ni des sessions actives, ni l'état du moteur Hermes.
Les valeurs opérationnelles restent du texte et des contrôles natifs distincts.

## Sélection LimeZu locale

À la racine du dépôt, sous Windows PowerShell :

```powershell
./apps/desktop/tools/import-atelier-assets.ps1 -Archive (Join-Path $env:USERPROFILE 'Downloads/LimeZu.zip')
```

L'import lit les sous-archives en mémoire, sans lancer les générateurs `.exe` et
sans extraire les packs complets. Il emploie seulement onze objets de
`Modern_Office_Revamped_v1.2.zip` et quatre personnages de
`moderninteriors-win.zip`. Aucun accès réseau ni paquet Python/Node n'est requis.

Les résultats sont écrits dans `../atelier-local/`, dossier ignoré par Git :

- `atelier-scene.png` : scène transparente, 480 × 240 ;
- `agent-adam.png`, `agent-alex.png`, `agent-amelia.png`, `agent-bob.png` :
  personnages de face, 32 × 64 ;
- `provenance.json` : noms exacts des fichiers sources utilisés ;
- `office-license.txt` et `interiors-license.txt` : licences originales.

Afficher à une échelle entière avec `smooth: false`. Ne pas déformer les
personnages pour les remplir dans un carré. La sélection est facultative ;
le fallback original assure le fonctionnement d'un checkout vierge.

## Attribution et distribution

Les licences incluses autorisent l'utilisation et la modification dans des
projets commerciaux ou non commerciaux. Elles interdisent de redistribuer ou
revendre les assets eux-mêmes. Cela se distingue de leur emploi comme éléments
d'une application finie : l'interdiction de republier le pack ne signifie pas
que toute application qui emploie son illustration est interdite.

Les PNG LimeZu, les atlases, les archives et leurs dérivés ne doivent pas être
committés ni publiés comme bibliothèque de ressources téléchargeable. Les
produits locaux utilisés par l'application restent séparés des sources
versionnées. Les copies originales des licences accompagnent l'import pour
vérifier les conditions du pack effectivement acheté.

Modern Interiors exige le crédit de LimeZu ; Modern Office indique que le
crédit est apprécié. Crédit à conserver dans l'application utilisant cette
sélection : **Pixel art : LimeZu — https://limezu.itch.io/**.

Références éditeur consultées le 12 octobre 2026 :
[Modern Interiors](https://limezu.itch.io/moderninteriors) et
[Modern Office](https://limezu.itch.io/modernoffice).
