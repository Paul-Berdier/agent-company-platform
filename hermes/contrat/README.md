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

Outil (étape P9) : `scripts/monter_hermes.py` (bibliothèque standard, `docker` et `git`).

- `derniere` : dernière release publiée à la fois en étiquette git amont et sur Docker Hub
  (veille mensuelle), sous l'une des deux formes de l'amont, `vAAAA.M.J[.N]` jusqu'à
  `v2026.9.24`, `vX.Y.Z` depuis v0.21.6 ; candidates (`rc.N-…`) et canaris écartés, toute
  autre forme publiée refusée ; n'écrit rien.
- `ecrire <étiquette>` : relève la release (condensats, commit, image tirée par condensat ;
  refus si l'image n'est pas construite depuis le commit de l'étiquette) et
  réécrit toutes les épingles fortes, dont ce dossier, le bloc `hermes` et
  `livrees.instantane_hermes` du verrou du catalogue, `hermes/THIRD_PARTY.md` et les fixtures
  `/v1/meta` du desktop et de l'interface ; rapporte les méthodes OpenRPC ajoutées et retirées,
  les skills livrées à classer et l'inventaire des anciennes valeurs. Ne touche jamais la borne
  `requires_hermes` du greffon.
- `verifier` : relève sans rien écrire et compare chaque épingle forte, octet pour octet ;
  `image.yml` le lance à chaque construction (répétition à blanc : « Aucun écart »).
- `inventaire` : fixtures de faux serveur et citations « Hermes X.Y.Z … fichier:ligne » à
  revérifier à la main dans la PR de montée.

La PR de montée revérifie aussi, à la main, le correctif de sécurité SECU-TUI (D156, D157)
contre la nouvelle release : fichiers d'environnement chargés avant la portée gérée, leur
ordre, leur décodage et leurs analyseurs ; règle d'activation des sources externes de
secrets ; liste des noms que l'écrivain de `.env` de Hermes refuse ; variables que l'ENV de
l'image amont fixe, face à `VALEURS_IMPOSEES`. Liste et renvois : `docs/exploitation.md`
§ 6.3, point 3. La CI voit un comportement connu qui change, une variable nouvelle dans l'ENV
de l'image et un fichier d'environnement de plus chargé depuis `HERMES_HOME` (deux gardes de
dérive) ; les autres ajouts de l'amont, non.

La concordance de toutes ces copies est vérifiée hors ligne par
`scripts/tests/test_epingles_hermes.py` (CI, Linux et Windows).
