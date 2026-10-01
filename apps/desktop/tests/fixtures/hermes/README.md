# Documents de référence du greffon acp-poste pour les tests natifs

`meta.json` reproduit la FORME de `GET /api/plugins/acp-poste/v1/meta` telle que la
construit `hermes/plugins/acp-poste/meta.py` (`construire_meta`) à `refonte/hermes` b3faac0 :
mêmes clés de premier niveau, mêmes sous-clés pour `hermes`, `openrpc`, `greffon` et
`machine`. Les VALEURS sont synthétiques, alignées sur `hermes/contrat/HERMES_VERSION`
(Hermes 0.21.5, OpenRPC version 1 et son empreinte, contrat `acp-poste/1`).

Limite dite : ce document n'est pas encore capturé sur l'image de test. Le test de contrat
qui comparera la forme servie à ce fichier (`hermes/tests/contrat/test_fixtures_desktop.py`,
cahier P8 § 9.3) arrive avec le bout en bout local de la station.
