"""Autorité de certification JETABLE pour l'image de test : jamais dans l'image Railway.

Crée, dans le répertoire donné : ``ac.pem`` (autorité), ``idp.pem`` et ``idp.key``
(certificat du faux fournisseur d'identité ``idp.acp.test``). Utilisé à la construction de
l'image de test, qui ajoute ``ac.pem`` au magasin certifi de Hermes pour que le tableau de
bord fasse confiance au faux fournisseur, exactement comme à un vrai.

Usage : python generer_ac_test.py <répertoire>
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

HOTE_IDP = "idp.acp.test"


def _nom(texte: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, texte)])


def main(repertoire: str) -> int:
    sortie = Path(repertoire)
    sortie.mkdir(parents=True, exist_ok=True)
    maintenant = dt.datetime.now(dt.timezone.utc)

    cle_ac = ec.generate_private_key(ec.SECP256R1())
    ac = (
        x509.CertificateBuilder()
        .subject_name(_nom("AC de test ACP (jetable)"))
        .issuer_name(_nom("AC de test ACP (jetable)"))
        .public_key(cle_ac.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - dt.timedelta(minutes=5))
        .not_valid_after(maintenant + dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(cle_ac.public_key()), critical=False)
        .sign(cle_ac, hashes.SHA256())
    )

    cle_idp = ec.generate_private_key(ec.SECP256R1())
    idp = (
        x509.CertificateBuilder()
        .subject_name(_nom(HOTE_IDP))
        .issuer_name(ac.subject)
        .public_key(cle_idp.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - dt.timedelta(minutes=5))
        .not_valid_after(maintenant + dt.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOTE_IDP)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cle_ac.public_key()), critical=False)
        .sign(cle_ac, hashes.SHA256())
    )

    (sortie / "ac.pem").write_bytes(ac.public_bytes(serialization.Encoding.PEM))
    (sortie / "idp.pem").write_bytes(idp.public_bytes(serialization.Encoding.PEM))
    (sortie / "idp.key").write_bytes(cle_idp.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    print(f"AC de test et certificat {HOTE_IDP} écrits dans {sortie}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage : generer_ac_test.py <répertoire>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
