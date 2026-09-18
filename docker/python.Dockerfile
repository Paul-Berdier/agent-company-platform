# syntax=docker/dockerfile:1
# Image Python commune aux services api, artifact-preview, provider-gateway,
# event-service, relay, migrate et backup (voir docker/entrypoint.sh).
#
# Reproductibilité : base épinglée par digest, dépendances tierces installées
# uniquement depuis le verrou haché requirements/python-3.12.lock.txt, distributions
# locales installées sans résolution (--no-deps) et sans isolation de build (le
# setuptools du verrou sert de backend). Aucun secret, aucune variable d'environnement
# de production n'est cuite dans l'image.
#
# Digest relevé le 17 septembre 2026 par ``docker pull python:3.12-slim-bookworm`` puis
# ``docker image inspect --format '{{index .RepoDigests 0}}'``.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

# ---------------------------------------------------------------------------
# Étape 1 : construction du venv /opt/acp
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/acp
ENV PATH="/opt/acp/bin:${PATH}"

COPY requirements/python-3.12.lock.txt /tmp/python-3.12.lock.txt
RUN pip install --require-hashes --no-deps -r /tmp/python-3.12.lock.txt

# Distributions locales : copie des sources puis installation non éditable, sans
# dépendances (toutes viennent du verrou) et sans isolation (setuptools/wheel verrouillés).
COPY packages/contracts /src/packages/contracts
COPY packages/database /src/packages/database
COPY packages/provider-sdk /src/packages/provider-sdk
COPY packages/event-sdk /src/packages/event-sdk
COPY packages/agent-sdk /src/packages/agent-sdk
COPY apps/api /src/apps/api
COPY apps/cli /src/apps/cli
COPY apps/event-service /src/apps/event-service
COPY apps/worker /src/apps/worker
COPY services/provider-gateway /src/services/provider-gateway
RUN pip install --no-deps --no-build-isolation \
        /src/packages/contracts \
        /src/packages/database \
        /src/packages/provider-sdk \
        /src/packages/event-sdk \
        /src/packages/agent-sdk \
        /src/apps/api \
        /src/apps/cli \
        /src/apps/event-service \
        /src/apps/worker \
        /src/services/provider-gateway \
    && rm -rf /src

# ---------------------------------------------------------------------------
# Étape 2 : image finale, sans outils de construction ni sources
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE}

# Version du produit lue du fichier VERSION par compose/CI (--build-arg ACP_VERSION=…).
ARG ACP_VERSION=0.0.0-unversioned
LABEL org.opencontainers.image.title="agent-company-platform-python" \
      org.opencontainers.image.description="Services Python de l'Agent Company Platform (api, artifact-preview, provider-gateway, event-service, relay, migrate, backup)" \
      org.opencontainers.image.version="${ACP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Paul-Berdier/agent-company-platform" \
      org.opencontainers.image.base.name="docker.io/library/python:3.12-slim-bookworm"

# Utilisateur non privilégié fixe (uid/gid 10001). /data est le point de montage du
# volume de données : il appartient à acp dans l'image, mais l'entrypoint refuse de
# démarrer si le volume monté par-dessus n'est pas inscriptible (aucun chown).
RUN groupadd --gid 10001 acp \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin acp \
    && mkdir -p /app/docker /data \
    && chown acp:acp /data

COPY --from=builder /opt/acp /opt/acp
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
COPY plugins /app/plugins
COPY VERSION /app/VERSION
RUN chmod 0755 /app/docker/entrypoint.sh

ENV PATH="/opt/acp/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACP_PLUGINS_DIR=/app/plugins \
    ACP_DATA_DIR=/data

WORKDIR /app
USER acp:acp
EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["api"]
