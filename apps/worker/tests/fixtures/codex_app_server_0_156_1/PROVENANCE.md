# Provenance des schémas de l'app-server Codex 0.156.1

Ces fichiers JSON Schema (draft-07) décrivent le protocole JSON-RPC de
`codex app-server`. Ils servent **uniquement aux tests** du worker
(`apps/worker/tests/test_subscription_quotas.py`) : le faux app-server de test doit
répondre exactement dans la forme que publie la version réelle du CLI, et les
requêtes envoyées par la sonde doivent respecter les paramètres attendus.

- **Projet d'origine** : [openai/codex](https://github.com/openai/codex), sous licence
  **Apache-2.0** (texte des conditions dans `LICENSE-APACHE-2.0.txt`, recopié à
  l'identique ; le paquet npm `@openai/codex` 0.156.1 déclare la même licence).
- **Génération** : `codex app-server generate-json-schema --out <dossier>`, Codex CLI
  **0.156.1** (`codex-cli 0.156.1`, paquet npm `@openai/codex`), le 24 septembre 2026
  sur le poste de développement. La commande a été rejouée le même jour avec un
  `CODEX_HOME` vide et temporaire : les onze fichiers ci-dessous sont identiques
  octet pour octet à cette seconde génération. Aucune connexion à un compte n'est
  nécessaire pour générer ces schémas.
- **Sélection** : seuls les fichiers nécessaires aux trois échanges de la sonde sont
  copiés, **sans aucune modification** (octets identiques à la sortie générée) :

| Fichier | Rôle dans la sonde | SHA-256 |
|---|---|---|
| `v1/InitializeParams.json` | paramètres de `initialize` envoyés par la sonde | `6f0094be9a65242ec779a40794cbd4fdfa32fca1e45084a16adfb50501d33ea2` |
| `v1/InitializeResponse.json` | réponse de `initialize` | `62ad689c2cb6379913c1d72749cfd8de5089d35760214123518eb92eef11acc9` |
| `ClientNotification.json` | notification `initialized` | `706cf248d75027c84a3c63348d0ed507182e8eba40069dd17541793de029145a` |
| `v2/GetAccountParams.json` | paramètres de `account/read` | `30b545275f60975b55bd6fbaafd70f15505801d14168ee82d3931b6e93c78aab` |
| `v2/GetAccountResponse.json` | réponse de `account/read` | `220a9c4d2e157cf3d80046739e6fd0f57de032a9fdc86ae07b88af63e053fb21` |
| `v2/GetAccountRateLimitsResponse.json` | réponse de `account/rateLimits/read` | `76bc91758269a89f57cd16c618b91c1fba76aca3e9d2b6186205e6f107d6b28c` |
| `JSONRPCRequest.json` | enveloppe d'une requête (sans en-tête `jsonrpc`) | `31bd6f360b2dd8a7ceaf682708105d40d38cb0b9d0821357a04da67028438f73` |
| `JSONRPCResponse.json` | enveloppe d'une réponse | `4796738c04c74288213a08fb8d820c7b4df19e0977cdcd35b65ffcb43cfc93ab` |
| `JSONRPCError.json` | enveloppe d'une erreur | `d7ea353d4875ae204625da5a00a1ecb5afc69101d5778b9acc253a49f8932992` |
| `JSONRPCErrorError.json` | corps d'une erreur | `12cc5cd5d9df9246defa609c472375020fe5250f3aeabd7d529076cecd9f541e` |
| `JSONRPCNotification.json` | enveloppe d'une notification | `c2b43f26880db331393fe09f34bdd76dfeb4dc30d8418d1c26e18db166d6c8c8` |

Les noms de méthodes `initialize`, `account/read` et `account/rateLimits/read`
proviennent du fichier généré `ClientRequest.json` de la même version (environ
200 Ko), qui n'est pas recopié ici ; la notification `initialized` est dans
`ClientNotification.json`.

Pour mettre à jour : régénérer les schémas avec la nouvelle version du CLI dans un
dossier temporaire, recopier les mêmes fichiers dans un nouveau dossier
`codex_app_server_<version>`, mettre à jour ce tableau et relancer les tests. Un
champ disparu ou renommé fait alors échouer le test de contrat, jamais la sonde en
production sans que personne ne le voie.
