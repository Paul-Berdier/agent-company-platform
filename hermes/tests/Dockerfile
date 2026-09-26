# Image de TEST : l'image ACP construite, plus les outils de test. Jamais déployée.
#
#   docker build -f hermes/tests/Dockerfile --build-arg IMAGE_ACP=acp-hermes:ci \
#       -t acp-hermes-tests:ci hermes/tests
#
# Différences avec l'image Railway, toutes limitées aux tests :
# - pytest et ses dépendances (hachés vérifiés) dans /opt/acp-tests/site, hors de
#   l'environnement virtuel de Hermes ;
# - les tests, le modèle factice, le faux fournisseur d'identité, le bord TLS factice et le
#   greffon témoin dans /opt/acp-tests ;
# - une autorité de certification JETABLE ajoutée au magasin du système
#   (/etc/ssl/certs/ca-certificates.crt, celui qu'épingle la managed scope), pour que le
#   tableau de bord fasse confiance au faux fournisseur d'identité idp.acp.test et au bord
#   factice (hermes-acp.test, identite-acp.test) devant le vrai fournisseur Authelia.
ARG IMAGE_ACP=acp-hermes:ci
FROM ${IMAGE_ACP}

COPY requirements-tests.txt /opt/acp-tests/requirements-tests.txt
# --no-config et cd /tmp : ignorer la configuration uv du projet Hermes (/opt/hermes).
RUN cd /tmp && uv pip install --no-config --python /opt/hermes/.venv/bin/python \
        --target /opt/acp-tests/site --require-hashes --no-deps \
        -r /opt/acp-tests/requirements-tests.txt

COPY image/ /opt/acp-tests/image/
COPY outils/ /opt/acp-tests/outils/
RUN set -eu; \
    /opt/hermes/.venv/bin/python -I -B /opt/acp-tests/outils/generer_ac_test.py /opt/acp-tests/ac; \
    chmod 0644 /opt/acp-tests/ac/idp.key /opt/acp-tests/ac/bord.key; \
    cp /opt/acp-tests/ac/ac.pem /usr/local/share/ca-certificates/acp-test-jetable.crt; \
    update-ca-certificates; \
    chown -R root:root /opt/acp-tests; \
    find /opt/acp-tests -type d -exec chmod 0755 {} +
