# Image Railway du fournisseur d'identité d'ACP (service « identite ») : Authelia, un seul
# utilisateur, client OIDC unique « hermes-acp » (tableau de bord Hermes).
#
# Contexte de construction : le répertoire identite/ du dépôt (répertoire racine du service
# Railway ; identite/.dockerignore).
#   docker build -t acp-identite:ci identite
#
# Base épinglée par le condensat de l'INDEX multi-architecture de l'étiquette 4.39.28, relevé le
# 25 septembre 2026 par
#   docker buildx imagetools inspect docker.io/authelia/authelia:4.39.28
# (manifeste linux/amd64 : sha256:a9931f4443882fcc43bc368bffd40b51ff1867045d46c8dc2e87fb2b03a32178).
# La CI (image.yml) relève à chaque exécution le condensat publié de l'étiquette de cette ligne et
# refuse s'il diffère. Une montée de version ne change que cette ligne (étiquette ET condensat).
FROM docker.io/authelia/authelia:4.39.28@sha256:bd97cff4fcbf715b5ff1f9ae286afbe6033afce385302520b0368122d43a6f54

# Valeurs FIXES, revérifiées par acp-identite-entree (toute autre valeur est refusée) :
# - configuration figée en lecture seule, rendue comme gabarit (secrets lus dans /config/secrets,
#   variables ACP_* par mustEnv) ;
# - Authelia tourne sous l'uid/gid 1000, jamais root (l'image amont vaut 0:0 par défaut).
ENV X_AUTHELIA_CONFIG=/etc/authelia/configuration.yml \
    X_AUTHELIA_CONFIG_FILTERS=template \
    PUID=1000 \
    PGID=1000

COPY configuration.yml /etc/authelia/configuration.yml
COPY acp-identite-entree acp-identite-admin /opt/acp-identite/

# - fichiers d'ACP à root, en lecture seule pour Authelia ;
# - /app/.healthcheck.env retiré : l'image amont le livre en 0666, Authelia (uid 1000) le réécrit et
#   /app/healthcheck.sh le SOURCE en root (HEALTHCHECK Docker) ; la santé Railway est une requête
#   HTTP sur /api/health, le HEALTHCHECK Docker est donc désactivé (voir aussi
#   server.disable_healthcheck dans la configuration).
RUN set -eu; \
    chown -R root:root /etc/authelia /opt/acp-identite; \
    chmod 0755 /etc/authelia /opt/acp-identite \
        /opt/acp-identite/acp-identite-entree /opt/acp-identite/acp-identite-admin; \
    chmod 0644 /etc/authelia/configuration.yml; \
    rm -f /app/.healthcheck.env

HEALTHCHECK NONE

EXPOSE 9091

# Garde root (variables, volume, secrets, utilisateur unique), puis /app/entrypoint.sh amont
# (chown de /config, su-exec 1000:1000 authelia). Aucun CMD : la garde refuse tout argument.
ENTRYPOINT ["/opt/acp-identite/acp-identite-entree"]
