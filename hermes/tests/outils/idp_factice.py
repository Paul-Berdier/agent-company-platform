"""Faux fournisseur d'identité OIDC, pour les tests de contrat seulement.

Sert en HTTPS (certificat signé par l'AC de test jetable) :

- ``GET /.well-known/openid-configuration`` : document de découverte ;
- ``GET /jwks`` : clé publique RSA de signature ;
- ``GET /emettre?sub=…&aud=…[&cle=autre]`` : jeton d'identité RS256 signé, pour les
  tests (un vrai fournisseur n'a évidemment pas cette route) ; ``cle=autre`` signe avec
  une clé que le JWKS ne publie pas, pour éprouver un refus ;
- ``/authorize`` et ``/token`` : présents dans la découverte, jamais appelés (400).

Aucun appel réseau sortant. Usage :
  python idp_factice.py --emetteur https://idp.acp.test:8443 --port 8443 \\
      --certificat idp.pem --cle idp.key
"""

from __future__ import annotations

import argparse
import base64
import json
import ssl
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLE_AUTRE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "acp-test-1"


def _b64(n: int) -> str:
    brut = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(brut).rstrip(b"=").decode("ascii")


def jwks() -> dict:
    publique = CLE.public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID,
                      "n": _b64(publique.n), "e": _b64(publique.e)}]}


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--emetteur", required=True)
    arguments.add_argument("--port", type=int, default=8443)
    arguments.add_argument("--certificat", required=True)
    arguments.add_argument("--cle", required=True)
    options = arguments.parse_args()
    emetteur = options.emetteur.rstrip("/")

    class Gestionnaire(BaseHTTPRequestHandler):
        def _json(self, code: int, corps: object) -> None:
            donnees = json.dumps(corps).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def do_GET(self) -> None:  # noqa: N802 — nom imposé par http.server
            url = urllib.parse.urlsplit(self.path)
            requete = urllib.parse.parse_qs(url.query)
            if url.path == "/.well-known/openid-configuration":
                self._json(200, {
                    "issuer": emetteur,
                    "authorization_endpoint": f"{emetteur}/authorize",
                    "token_endpoint": f"{emetteur}/token",
                    "jwks_uri": f"{emetteur}/jwks",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "code_challenge_methods_supported": ["S256"],
                })
            elif url.path == "/jwks":
                self._json(200, jwks())
            elif url.path == "/emettre":
                maintenant = int(time.time())
                sujet = requete.get("sub", ["proprietaire"])[0]
                charge = {
                    "iss": requete.get("iss", [emetteur])[0],
                    "aud": requete.get("aud", ["acp-tableau"])[0],
                    "sub": sujet,
                    "email": f"{sujet}@acp.test",
                    "name": sujet,
                    "iat": maintenant,
                    "nbf": maintenant - 5,
                    "exp": maintenant + 3600,
                    "jti": uuid.uuid4().hex,
                }
                cle = CLE_AUTRE if requete.get("cle", [""])[0] == "autre" else CLE
                jeton = jwt.encode(charge, cle, algorithm="RS256", headers={"kid": KID})
                self._json(200, {"id_token": jeton})
            else:
                self._json(400, {"error": "invalid_request"})

        def do_POST(self) -> None:  # noqa: N802
            self._json(400, {"error": "invalid_request"})

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            print(f"[idp-factice] {self.command} {self.path.split('?', 1)[0]}", flush=True)

    serveur = ThreadingHTTPServer(("0.0.0.0", options.port), Gestionnaire)
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.load_cert_chain(options.certificat, options.cle)
    serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True)
    print(f"[idp-factice] émetteur {emetteur}, port {options.port}", flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
