# Agent Company Platform {{VERSION}} — station de travail Windows

Station de travail native du propriétaire d'ACP (C++23, Qt 6, QML, sans WebView). Elle se connecte au Hermes du
propriétaire par son fournisseur d'identité OIDC (connexion native par le navigateur du système, RFC 8252) et
n'appelle que les API de ce Hermes : tableau de bord, JSON-RPC et façade du greffon `acp-poste`. Pages : Accueil,
Projets, Questions, Discussion, Poste, Quotas, Routage, Diagnostics, Sauvegarde (export chiffré de Hermes, format
`ACPB1`, protégé par DPAPI pour l'utilisateur Windows courant) et Réglages.

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

- **Installation** : `{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe` installe pour l'utilisateur courant, sans
  élévation ; l'archive portable se décompresse où vous voulez.
- **Connexion** : au premier lancement, saisissez l'adresse de votre Hermes (HTTPS imposé ; aucune adresse n'est
  proposée par défaut), testez le lien, puis « Se connecter avec le navigateur ». La connexion se fait chez votre
  fournisseur d'identité : aucun mot de passe n'est saisi dans la station. Mémoriser la session (coffre Windows) est
  facultatif.
- **Désinstallation** : comme un programme installé pour l'utilisateur courant, depuis la liste des applications
  de Windows.

Construction, tests et architecture, dans le dépôt à l'étiquette de cette publication : `apps/desktop/README.md`,
`docs/desktop-build.md` et `docs/refonte/desktop.md`.

## Ce que cette publication ne prouve pas

Les binaires sont compilés, testés (Qt Test et Qt Quick Test) et empaquetés par le workflow Desktop Release, à
l'étiquette de cette publication, sur l'exécuteur GitHub `windows-2022`, avec les mêmes scripts que Desktop CI ;
ces tests natifs éprouvent la station contre un faux Hermes et contre les documents de référence partagés avec le
greffon. Cela ne prouve pas : une installation sur un Windows propre (jamais faite) ; une connexion à un Hermes
déployé sur Railway, avec une vraie passkey et un vrai appareil (aucun test n'en emploie) ; une revue visuelle ou un
lecteur d'écran réel. Les binaires ne sont signés que si la section « Signature de code » ci-dessus le dit. Limites
détaillées : `docs/refonte/desktop.md`, section « Non prouvé ».
