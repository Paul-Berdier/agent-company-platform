# Agent Company Platform {{VERSION}} — client desktop Windows

## Contenu

| Fichier | Usage |
|---|---|
| `{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe` | Programme d'installation par utilisateur, sans élévation de privilèges. |
| `{{PREFIXE}}-Portable-{{VERSION}}-{{SUFFIXE}}.zip` | Archive portable : décompresser et lancer. Rien n'est écrit dans le registre. |
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
GitHub Windows. Ils n'ont été éprouvés contre aucun serveur réellement déployé :
aucun déploiement Railway n'a eu lieu à ce jour, et l'URL du serveur reste à saisir
par l'utilisateur. Aucune installation n'a été vérifiée sur un poste tiers.
