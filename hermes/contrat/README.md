# Contrat épinglé de Hermes Agent

Ce dossier fige ce qu'ACP attend de la version de Hermes Agent qu'il embarque.

| Fichier | Rôle |
|---|---|
| `HERMES_VERSION` | Version, étiquette, commit et condensats de l'image officielle épinglée, empreinte de l'OpenRPC, nom du contrat `acp-poste/1`. |
| `gateway-contract.openrpc.json` | Copie exacte du contrat JSON-RPC de la passerelle (`/api/ws`) de Hermes. |
| `LICENSE-hermes-agent.txt` | Licence MIT de Hermes Agent, qui couvre la copie ci-dessus. |

## Provenance

- `gateway-contract.openrpc.json` : fichier `apps/shared/src/gateway-contract.openrpc.json`
  de Hermes Agent, étiquette `v2026.9.24`, commit
  `f97608f178d1ffeca59860195ab7da295f7c8e5f`, extrait **de l'image officielle
  épinglée** (`/opt/hermes/apps/shared/src/gateway-contract.openrpc.json`) le
  24 septembre 2026. SHA-256 `c89a203e853c285c4af204a229d4d804a36847efdcb6d223da8d3d22017f184d`,
  `info.version` = `1`, 237 méthodes. Généré en amont par
  `scripts/gen_gateway_contracts.py` depuis `tui_gateway/contracts`.
- `LICENSE-hermes-agent.txt` : fichier `LICENSE` de la même image
  (`/opt/hermes/LICENSE`), MIT, © 2025 Nous Research.

Aucune modification n'est apportée à ces copies. Le workflow `image.yml` vérifie à
chaque construction que la copie est identique, octet pour octet, au fichier présent
dans l'image construite, et que `HERMES_VERSION` concorde avec la ligne `FROM` du
Dockerfile et avec `hermes --version`.

## Montée de version

Une montée de Hermes change, dans une seule PR : la ligne `FROM` de
`hermes/image/Dockerfile`, `HERMES_VERSION` et la copie de l'OpenRPC (relevée dans la
nouvelle image). Jamais de `hermes update`, de `git pull` de Hermes, d'étiquette
`:latest` ni d'`AUTO_UPDATE`.
