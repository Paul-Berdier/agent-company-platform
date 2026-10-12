# Agent Company Platform {{VERSION}} — Pixel Atelier pour Windows

Station de travail native C++23 / Qt 6 / QML. **Mon atelier** rassemble les projets à
reprendre et les demandes en attente. Chaque projet organise son contenu en **Travail**,
**Résultats**, **Journal** et **Réglages**. Les familles **Pixel Atelier** et **Studio**
sont disponibles en clair et sombre ; les préférences de mouvement sont conservées.

La station se connecte au Hermes du propriétaire via son fournisseur d'identité, avec
le navigateur système. Les états, questions et résultats proviennent de ce Hermes.
Le décor est une illustration, pas une visualisation d'agents réellement actifs.

## Fichiers

| Fichier | Usage |
| --- | --- |
| `{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe` | Installation ou mise à jour par utilisateur |
| `{{PREFIXE}}-Portable-{{VERSION}}-{{SUFFIXE}}.zip` | Extraire dans un dossier, puis lancer `AgentCompanyPlatform.exe` |
| `SHA256SUMS.txt` | Empreintes des deux paquets |

Les paquets du workflow public utilisent le décor ACP original. La scène LimeZu est
réservée aux builds ayant importé le pack local sous licence ; ses sources ne sont pas
publiées dans Git ni jointes séparément à la release.

## Signature

{{SIGNATURE}}

## Installer ou mettre à jour

1. Téléchargez le paquet voulu et `SHA256SUMS.txt` depuis cette publication.
2. Comparez l'empreinte du fichier à sa ligne dans `SHA256SUMS.txt` :

   ```powershell
   Get-FileHash .\{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe -Algorithm SHA256
   ```

3. Fermez ACP. Pour une installation existante, lancez le nouveau Setup avec le même
   compte Windows, sans désinstaller l'ancienne version. Pour le portable, utilisez un
   nouveau dossier et ne mélangez pas les DLL de deux versions.
4. Relancez et vérifiez la version dans **Réglages → Mises à jour**. Reconnectez-vous
   par le navigateur si la session le demande.

Les préférences utilisent le profil Windows ; la session mémorisée, avec consentement,
reste dans son coffre. Les projets sont conservés côté Hermes. La mise à jour du client
ne remplace pas un déploiement du serveur. L'application vérifie les releases à la demande
et ouvre leur page ; elle n'installe rien automatiquement.

Guide complet : [mettre à jour et reprendre son travail](https://github.com/Paul-Berdier/agent-company-platform/blob/v{{VERSION}}/docs/mettre-a-jour-1.1.md).
Pour le code produit par un projet : [récupérer le résultat](https://github.com/Paul-Berdier/agent-company-platform/blob/v{{VERSION}}/docs/recuperer-resultat.md).

## Validation et limites

Desktop Release compile, teste et empaquette cette étiquette sur `windows-2022`, avec
la chaîne épinglée du dépôt. Les tests utilisent notamment un faux Hermes ; ils ne
prouvent pas une vraie passkey, une connexion personnelle à Railway ni une installation
sur Windows propre. Les captures et essais locaux de Pixel Atelier sont décrits dans
[le relevé du lot](https://github.com/Paul-Berdier/agent-company-platform/blob/v{{VERSION}}/docs/refonte/pixel-atelier.md)
avec leurs limites. Ne considérer le paquet comme signé que si la section Signature le dit.
