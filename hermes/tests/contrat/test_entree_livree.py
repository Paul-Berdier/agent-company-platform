"""L'entrée effectivement livrée correspond à la source versionnée et vérifiée."""
import hashlib
from conftest import RACINE_HERMES, docker


def test_entree_livree_identique_a_la_source(image):
    source = (RACINE_HERMES / 'image' / 'acp-entree').read_bytes()
    somme = docker('run', '--rm', '--entrypoint', 'sha256sum', image,
                   '/opt/acp/bin/acp-entree').stdout.split()[0]
    assert somme == hashlib.sha256(source).hexdigest()
