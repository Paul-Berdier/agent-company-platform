# Image Railway d'ACP, dérivée de l'image officielle de Hermes Agent.
#
# Contexte de construction : le répertoire hermes/ du dépôt (hermes/.dockerignore).
#   docker build -f hermes/image/Dockerfile hermes
#
# Base épinglée par le condensat de l'INDEX multi-architecture de l'étiquette v2026.9.24
# (Hermes Agent 0.21.5, commit f97608f), relevé le 24 septembre 2026 par
#   docker buildx imagetools inspect nousresearch/hermes-agent:v2026.9.24
# Une montée de version change cette ligne ET hermes/contrat/HERMES_VERSION dans la même
# PR (un test vérifie qu'ils concordent). Jamais :latest, jamais hermes update.
FROM nousresearch/hermes-agent:v2026.9.24@sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7

# S6_BEHAVIOUR_IF_STAGE2_FAILS=2 : s6-overlay arrête le conteneur (code 1) si le crochet
#   ou un script cont-init échoue ; la valeur par défaut (0) poursuivrait en silence et
#   l'image officielle ne la fixe pas.
# S6_STAGE2_HOOK : gardes d'ACP exécutées avant tout service et tout script cont-init
#   (voir hermes/image/acp-gardes).
# HERMES_DASHBOARD* : le tableau de bord (service s6 docker/s6-rc.d/dashboard/run) écoute
#   sur 0.0.0.0:9119, seul port routé par Railway ; toute autre valeur est refusée.
ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_STAGE2_HOOK=/opt/acp/bin/acp-gardes \
    HERMES_DASHBOARD=1 \
    HERMES_DASHBOARD_HOST=0.0.0.0 \
    HERMES_DASHBOARD_PORT=9119

# Fichiers d'ACP, en lecture seule pour l'agent (uid 10000).
COPY contrat/ /opt/acp/contrat/
COPY gere/config.yaml /opt/acp/gere/config.yaml
COPY persona/SOUL.md /opt/acp/persona/SOUL.md
COPY theme/ /opt/acp/theme/
COPY image/acp_demarrage.py image/acp-gardes /opt/acp/bin/
# Greffon groupé : /opt/hermes/plugins est la source « bundled » de Hermes
# (hermes_cli/plugins.py:68-75), en lecture seule pour l'agent.
COPY plugins/acp-poste/ /opt/hermes/plugins/acp-poste/
# 05-acp s'exécute après 02-reconcile-profiles (ordre lexicographique de /etc/cont-init.d).
COPY image/cont-init.d/05-acp /etc/cont-init.d/05-acp

# Permissions normalisées (root ; répertoires 0755, fichiers 0644, exécutables 0755), puis
# managed scope de base (valeurs de déploiement vides) : le modèle est validé à la
# construction (un modèle invalide fait échouer le build) et les épingles s'appliquent
# même à un processus lancé hors de s6.
RUN set -eu; \
    chown -R root:root /opt/acp /opt/hermes/plugins/acp-poste /etc/cont-init.d/05-acp; \
    find /opt/acp /opt/hermes/plugins/acp-poste -type d -exec chmod 0755 {} +; \
    find /opt/acp /opt/hermes/plugins/acp-poste -type f -exec chmod 0644 {} +; \
    chmod 0755 /opt/acp/bin/acp-gardes /etc/cont-init.d/05-acp; \
    /opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py construire

# La passerelle (cron, répartiteur kanban, messagerie) est supervisée par s6 quand le
# CMD vaut « gateway run » ; l'image officielle a CMD [] (Dockerfile:513) et son service
# main-hermes n'est qu'un « sleep infinity » (docker/s6-rc.d/main-hermes/run ;
# website/docs/user-guide/docker.md:61-66). L'ENTRYPOINT officiel
# (docker/entrypoint-dispatch.sh, qui lance /init d's6 quand il est PID 1) est conservé.
CMD ["gateway", "run"]
