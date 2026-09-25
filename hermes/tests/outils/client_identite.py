"""Client HTTP de TEST du fournisseur d'identité, lancé DANS un conteneur du réseau de test
(image de test : httpx de Hermes, AC jetable). Toutes les requêtes passent par le bord factice
(https://identite-acp.test), jamais directement par Authelia.

Deux sous-commandes, résultat en JSON sur la sortie standard :

- ``autoriser --utilisateur U --mot-de-passe P`` : début d'un parcours OIDC du client hermes-acp
  (PKCE S256), premier facteur au nom de U, puis la redirection que rend Authelia. Sert à prouver la
  politique d'autorisation du client (refus de tout autre sujet que le propriétaire) sans navigateur.
- ``rafale --n N --utilisateur U --mot-de-passe P`` : N premiers facteurs SIMULTANÉS (barrière),
  pour mesurer la mémoire d'Authelia (argon2id, 64 Mio par vérification).

Usage : python client_identite.py <sous-commande> [options]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse

import httpx

AC = "/opt/acp-tests/ac/ac.pem"
EMETTEUR = "https://identite-acp.test"
CLIENT = "hermes-acp"
RETOUR = "https://hermes-acp.test/auth/callback"


def _url_autorisation() -> str:
    verificateur = secrets.token_urlsafe(64)
    defi = base64.urlsafe_b64encode(hashlib.sha256(verificateur.encode("ascii")).digest()).rstrip(b"=").decode()
    parametres = {"response_type": "code", "client_id": CLIENT, "redirect_uri": RETOUR,
                  "scope": "openid profile email offline_access", "state": secrets.token_urlsafe(16),
                  "code_challenge": defi, "code_challenge_method": "S256"}
    return f"{EMETTEUR}/api/oidc/authorization?{urllib.parse.urlencode(parametres)}"


def autoriser(utilisateur: str, mot_de_passe: str) -> dict:
    with httpx.Client(verify=AC, follow_redirects=False, timeout=60) as client:
        depart = client.get(_url_autorisation())
        emplacement = depart.headers.get("location", "")
        requete = urllib.parse.parse_qs(urllib.parse.urlsplit(emplacement).query)
        flux = (requete.get("flow_id") or [""])[0]
        premier = client.post(f"{EMETTEUR}/api/firstfactor", json={
            "username": utilisateur, "password": mot_de_passe, "keepMeLoggedIn": False,
            "flow": "openid_connect", "flowID": flux})
        try:
            corps = premier.json()
        except ValueError:
            corps = {"brut": premier.text[:300]}
        redirection = ((corps.get("data") or {}) if isinstance(corps, dict) else {}).get("redirect")
        finale = None
        if redirection:
            suite = client.get(redirection)
            finale = {"statut": suite.status_code, "location": suite.headers.get("location")}
        return {"depart": {"statut": depart.status_code, "location": emplacement},
                "premier_facteur": {"statut": premier.status_code, "corps": corps},
                "redirection": redirection, "finale": finale}


def rafale(n: int, utilisateur: str, mot_de_passe: str) -> dict:
    barriere = threading.Barrier(n)
    resultats: list = [None] * n

    def une(i: int) -> None:
        with httpx.Client(verify=AC, timeout=300) as client:
            barriere.wait()
            debut = time.monotonic()
            try:
                reponse = client.post(f"{EMETTEUR}/api/firstfactor",
                                      json={"username": utilisateur, "password": mot_de_passe})
                resultats[i] = {"statut": reponse.status_code, "duree_s": round(time.monotonic() - debut, 3)}
            except httpx.HTTPError as exc:
                resultats[i] = {"statut": None, "erreur": type(exc).__name__,
                                "duree_s": round(time.monotonic() - debut, 3)}

    fils = [threading.Thread(target=une, args=(i,)) for i in range(n)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()
    return {"n": n, "resultats": resultats}


def main() -> int:
    arguments = argparse.ArgumentParser()
    sous = arguments.add_subparsers(dest="commande", required=True)
    a = sous.add_parser("autoriser")
    a.add_argument("--utilisateur", required=True)
    a.add_argument("--mot-de-passe", required=True)
    r = sous.add_parser("rafale")
    r.add_argument("--n", type=int, required=True)
    r.add_argument("--utilisateur", required=True)
    r.add_argument("--mot-de-passe", required=True)
    options = arguments.parse_args()
    if options.commande == "autoriser":
        resultat = autoriser(options.utilisateur, options.mot_de_passe)
    else:
        resultat = rafale(options.n, options.utilisateur, options.mot_de_passe)
    print(json.dumps(resultat, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
