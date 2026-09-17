# syntax=docker/dockerfile:1
# Image du SPA web (apps/web) : build Vite dans Node 22, service statique par nginx
# non privilégié (uid 101, port 8080, voir docker/web.nginx.conf).
#
# Les variables VITE_* sont figées au build : l'image produite n'est valable que pour
# l'API dont l'URL a été fournie. Un build sans VITE_ACP_API_URL est refusé plutôt
# que de livrer un SPA qui appellerait localhost en production.
#
# Digests relevés le 17 septembre 2026 (docker pull + docker image inspect).
ARG NODE_IMAGE=node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.27-alpine@sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0

# ---------------------------------------------------------------------------
# Étape 1 : build Vite
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS builder

ARG VITE_ACP_API_URL
ARG VITE_ACP_LEGACY_OFFICE=0
ENV VITE_ACP_API_URL=${VITE_ACP_API_URL} \
    VITE_ACP_LEGACY_OFFICE=${VITE_ACP_LEGACY_OFFICE} \
    CI=1

WORKDIR /build

# Manifestes seuls d'abord : la couche npm ci est réutilisée tant qu'ils ne changent pas.
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/contracts/package.json packages/contracts/
COPY packages/pixel-office-engine/package.json packages/pixel-office-engine/
COPY packages/playwright-reporter/package.json packages/playwright-reporter/
COPY packages/ui/package.json packages/ui/
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY apps/web apps/web
COPY packages/contracts packages/contracts
COPY packages/pixel-office-engine packages/pixel-office-engine
COPY packages/playwright-reporter packages/playwright-reporter
COPY packages/ui packages/ui

RUN if [ -z "${VITE_ACP_API_URL}" ]; then \
        echo "Build refusé : VITE_ACP_API_URL est obligatoire (--build-arg VITE_ACP_API_URL=https://api.exemple)." >&2; \
        exit 1; \
    fi \
    && npm run build:web

# ---------------------------------------------------------------------------
# Étape 2 : nginx non privilégié
# ---------------------------------------------------------------------------
FROM ${NGINX_IMAGE}

ARG ACP_VERSION=0.0.0-unversioned
LABEL org.opencontainers.image.title="agent-company-platform-web" \
      org.opencontainers.image.description="Interface web statique (Vite) de l'Agent Company Platform servie par nginx non privilégié" \
      org.opencontainers.image.version="${ACP_VERSION}" \
      org.opencontainers.image.source="https://github.com/Paul-Berdier/agent-company-platform" \
      org.opencontainers.image.base.name="docker.io/nginxinc/nginx-unprivileged:1.27-alpine"

COPY docker/web.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/apps/web/dist /usr/share/nginx/html

EXPOSE 8080
