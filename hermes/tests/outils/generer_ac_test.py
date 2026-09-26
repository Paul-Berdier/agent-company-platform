"""Autorité de certification JETABLE pour l'image de test : jamais dans l'image Railway.

Crée, dans le répertoire donné :
- ``ac.pem`` (autorité) ;
- ``idp.pem`` et ``idp.key`` : certificat du faux fournisseur d'identité ``idp.acp.test`` ;
- ``bord.pem`` et ``bord.key`` : certificat du bord factice (``bord_factice.py``), qui imite le
  bord TLS de Railway pour ``hermes-acp.test`` et ``identite-acp.test``. Ces deux noms ont des
  domaines enregistrables DISTINCTS, comme deux sous-domaines de ``up.railway.app`` (suffixe
  public) : le navigateur les traite en sites différents, exactement comme sur Railway ;
- ``mcp.pem`` et ``mcp.key`` (étape P3) : certificat du faux serveur context7 (``mcp_factice.py``)
  pour ``mcp.context7.com``, le nom épinglé par la managed scope ; les tests le font résoudre vers
  le faux serveur, jamais vers le vrai.

Utilisé à la construction de l'image de test, qui ajoute ``ac.pem`` au magasin du système pour que
le tableau de bord fasse confiance au faux fournisseur et au bord, exactement comme à de vrais.

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
HOTES_BORD = ("hermes-acp.test", "identite-acp.test")
HOTE_MCP = "mcp.context7.com"


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

    def feuille(hotes) -> tuple:
        cle = ec.generate_private_key(ec.SECP256R1())
        certificat = (
            x509.CertificateBuilder()
            .subject_name(_nom(hotes[0]))
            .issuer_name(ac.subject)
            .public_key(cle.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(maintenant - dt.timedelta(minutes=5))
            .not_valid_after(maintenant + dt.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in hotes]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cle_ac.public_key()), critical=False)
            .sign(cle_ac, hashes.SHA256())
        )
        return certificat, cle

    idp, cle_idp = feuille((HOTE_IDP,))
    bord, cle_bord = feuille(HOTES_BORD)
    mcp, cle_mcp = feuille((HOTE_MCP,))

    (sortie / "ac.pem").write_bytes(ac.public_bytes(serialization.Encoding.PEM))
    (sortie / "idp.pem").write_bytes(idp.public_bytes(serialization.Encoding.PEM))
    (sortie / "idp.key").write_bytes(cle_idp.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (sortie / "bord.pem").write_bytes(bord.public_bytes(serialization.Encoding.PEM))
    (sortie / "bord.key").write_bytes(cle_bord.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (sortie / "mcp.pem").write_bytes(mcp.public_bytes(serialization.Encoding.PEM))
    (sortie / "mcp.key").write_bytes(cle_mcp.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    print(f"AC de test et certificats {HOTE_IDP}, {', '.join(HOTES_BORD)}, {HOTE_MCP} écrits dans {sortie}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage : generer_ac_test.py <répertoire>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
