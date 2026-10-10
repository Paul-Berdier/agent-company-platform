# Image d'ESSAIS de l'exécutant (cahier P6 § 14.1) : l'image construite, plus pytest (verrou haché) et les tests du
# poste, pour lancer la suite apps/poste EN ROOT dans l'environnement réel de l'image (setpriv, git, bubblewrap,
# comptes 10001-10003, /etc/gitconfig) : les tests propres à root, ignorés par la CI Linux sans root, y tournent.
# Jamais déployée ; Railway construit executant/Dockerfile.
#
#   docker build -f executant/tests/Dockerfile --build-arg IMAGE_EXECUTANT=acp-executant:ci -t acp-executant-essais:ci .
#   docker run --rm --entrypoint /usr/bin/tini acp-executant-essais:ci -- python3.12 -m pytest -q -rs \
#       apps/poste/tests hermes/plugins/acp-poste/contrat/tests
ARG IMAGE_EXECUTANT=acp-executant:ci
FROM ${IMAGE_EXECUTANT}
# Verrou haché du dépôt installé dans l'interpréteur de l'IMAGE D'ESSAIS seulement (jamais dans l'image déployée) :
# certains tests lancent « python3.12 -I » et attendent pydantic dans son site-packages, comme sur la CI.
COPY requirements/python-3.12.lock.txt /opt/acp-essais/python-3.12.lock.txt
RUN python3.12 -m pip install --no-cache-dir --require-hashes --no-deps -r /opt/acp-essais/python-3.12.lock.txt
COPY pytest.ini VERSION /opt/acp-essais/depot/
COPY apps/poste/ /opt/acp-essais/depot/apps/poste/
COPY hermes/plugins/acp-poste/ /opt/acp-essais/depot/hermes/plugins/acp-poste/
COPY scripts/balayer_secrets.py /opt/acp-essais/depot/scripts/balayer_secrets.py
COPY hermes/tests/outils/fixtures_machine/ /opt/acp-essais/depot/hermes/tests/outils/fixtures_machine/
COPY executant/ /opt/acp-essais/depot/executant/
COPY packaging/poste/ /opt/acp-essais/depot/packaging/poste/
COPY .railway/railway.ts /opt/acp-essais/depot/.railway/railway.ts
WORKDIR /opt/acp-essais/depot
