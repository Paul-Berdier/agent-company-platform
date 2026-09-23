# Agent Company Platform {{VERSION}} — client desktop Windows

## Contenu

| Fichier | Usage |
|---|---|
| `{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe` | Programme d'installation par utilisateur, sans élévation de privilèges. |
| `{{PREFIXE}}-Portable-{{VERSION}}-{{SUFFIXE}}.zip` | Archive portable : décompresser et lancer. Les préférences non sensibles utilisent le profil Windows ; la session peut être mémorisée dans le coffre sur consentement. |
| `SHA256SUMS.txt` | Sommes de contrôle SHA-256 des deux fichiers ci-dessus. |

## Signature de code

{{SIGNATURE}}

## Vérifier les sommes de contrôle avant d'exécuter

```powershell
Get-FileHash .\{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe -Algorithm SHA256
```

Comparez l'empreinte obtenue à la ligne correspondante de `SHA256SUMS.txt`. Le
fichier suit le format de `sha256sum` : `<empreinte>  <nom de fichier>`.

## Installation, connexion, désinstallation

Voir `docs/desktop-installation.md`.

## Ce que cette publication ne prouve pas

Les binaires sont compilés et testés par l'intégration continue, sur un exécuteur
GitHub Windows. Les preuves locales comprennent un parcours Qt contre une vraie API
SQLite jetable et une installation/désinstallation isolée. Cela ne prouve pas une
recette Railway, un fournisseur réel, une revue visuelle ou un poste Windows propre.
L'URL du serveur reste à saisir par l'utilisateur. Voir les résultats précis dans
`docs/desktop-validation-2026-09-23.md` et la surface livrée dans
`docs/native-desktop-parity.md`.
