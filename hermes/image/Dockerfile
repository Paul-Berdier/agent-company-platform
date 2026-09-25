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
# PATH : l'image officielle y place /opt/data/.local/bin (Dockerfile:476), que l'agent
#   possède, AVANT /usr/bin et /bin. Or tous les scripts exécutés en root par s6 (crochet,
#   cont-init, scripts run des services) prennent ce PATH par with-contenv : un faux `id`
#   ou `sh` déposé là par l'agent tournait en root à la relance suivante du tableau de bord
#   (constaté sur 6b5a699). On le retire ; le terminal local de l'agent le rajoute de
#   lui-même, en fin de PATH, à ses propres shells (tools/environments/local.py:630-657).
#   Les gardes refusent tout autre répertoire (acp_demarrage.py, PATH_ADMIS).
ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_STAGE2_HOOK=/opt/acp/bin/acp-gardes \
    HERMES_DASHBOARD=1 \
    HERMES_DASHBOARD_HOST=0.0.0.0 \
    HERMES_DASHBOARD_PORT=9119 \
    PATH=/opt/hermes/bin:/opt/hermes/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Fichiers d'ACP, en lecture seule pour l'agent (uid 10000).
COPY contrat/ /opt/acp/contrat/
COPY gere/config.yaml /opt/acp/gere/config.yaml
COPY persona/SOUL.md /opt/acp/persona/SOUL.md
COPY theme/ /opt/acp/theme/
# Étape P3 : catalogue épinglé. Skills en texte seul (maison et vendorisées à l'octet près, avec
# LICENSE et PROVENANCE.md), hors du volume : 05-acp les fait charger par skills.external_dirs
# (/opt/data/config.yaml, que Hermes lit sans la managed scope). Verrou et licences tierces.
COPY skills/ /opt/acp/skills/
COPY catalogue/ /opt/acp/catalogue/
COPY THIRD_PARTY.md /opt/acp/THIRD_PARTY.md
COPY image/acp_demarrage.py image/acp-gardes image/acp-run-dashboard image/acp-entree /opt/acp/bin/
# Greffon groupé : /opt/hermes/plugins est la source « bundled » de Hermes
# (hermes_cli/plugins.py:68-75), en lecture seule pour l'agent.
COPY plugins/acp-poste/ /opt/hermes/plugins/acp-poste/
# Étape P3 : greffons de tableau de bord SANS code serveur (manifeste, bundle IIFE, feuille de
# style), construits depuis apps/interface et committés. Découverts en source « bundled »
# (web_server_dashboard.py:463-560), servis tant qu'ils ne sont pas dans plugins.disabled.
COPY plugins/acp-interface/ /opt/hermes/plugins/acp-interface/
COPY plugins/acp-catalogue/ /opt/hermes/plugins/acp-catalogue/
# 05-acp s'exécute après 02-reconcile-profiles (ordre lexicographique de /etc/cont-init.d).
COPY image/cont-init.d/05-acp /etc/cont-init.d/05-acp

# Permissions normalisées (root ; répertoires 0755, fichiers 0644, exécutables 0755), puis
# managed scope de base (valeurs de déploiement vides) : le modèle est validé à la
# construction (un modèle invalide fait échouer le build) et les épingles s'appliquent
# même à un processus lancé hors de s6.
RUN set -eu; \
    chown -R root:root /opt/acp /opt/hermes/plugins/acp-poste /opt/hermes/plugins/acp-interface \
        /opt/hermes/plugins/acp-catalogue /etc/cont-init.d/05-acp; \
    find /opt/acp /opt/hermes/plugins/acp-poste /opt/hermes/plugins/acp-interface \
        /opt/hermes/plugins/acp-catalogue -type d -exec chmod 0755 {} +; \
    find /opt/acp /opt/hermes/plugins/acp-poste /opt/hermes/plugins/acp-interface \
        /opt/hermes/plugins/acp-catalogue -type f -exec chmod 0644 {} +; \
    chmod 0755 /opt/acp/bin/acp-gardes /opt/acp/bin/acp-run-dashboard /opt/acp/bin/acp-entree \
        /etc/cont-init.d/05-acp; \
    /opt/hermes/.venv/bin/python -I -B /opt/acp/bin/acp_demarrage.py construire

# Enveloppe root du service s6 « dashboard » : à chaque (re)lancement, y compris quand
# l'agent le relance lui-même (s6-svc -r, la FIFO supervise/control lui restant
# accessible), la garde ACP refuse de démarrer sur un .env de volume qui porte une
# variable interdite (HERMES_MANAGED_DIR déplacerait la managed scope). Le script amont
# officiel est préservé tel quel dans /opt/acp/amont ; une montée de version le recopie
# sans que l'enveloppe change. (hermes/image/acp-run-dashboard.)
RUN set -eu; \
    mkdir -p /opt/acp/amont; \
    cp -a /etc/s6-overlay/s6-rc.d/dashboard/run /opt/acp/amont/s6-dashboard-run; \
    cp /opt/acp/bin/acp-run-dashboard /etc/s6-overlay/s6-rc.d/dashboard/run; \
    chown root:root /opt/acp/amont/s6-dashboard-run /etc/s6-overlay/s6-rc.d/dashboard/run; \
    chmod 0755 /opt/acp/amont/s6-dashboard-run /etc/s6-overlay/s6-rc.d/dashboard/run

# ENTRYPOINT (étape P2) : l'ENTRYPOINT officiel (docker/entrypoint-dispatch.sh, qui lance
# /init d's6 quand il est PID 1) est ENVELOPPÉ par acp-entree, qui refuse de démarrer hors du
# PID 1 : le repli officiel sans s6 tournerait sans aucune garde (hermes/image/acp-entree).
# Une Start Command Railway remplace l'ENTRYPOINT (rw_full.txt:29497-29507) : maintenance
# seulement, sous la forme /bin/sh -c "exec sleep infinity" (docs/refonte/railway.md §10).
# Déclarer un ENTRYPOINT remet à vide le CMD hérité : le CMD doit donc rester APRÈS.
ENTRYPOINT ["/opt/acp/bin/acp-entree"]

# La passerelle (cron, répartiteur kanban, messagerie) est supervisée par s6 quand le
# CMD vaut « gateway run » ; l'image officielle a CMD [] (Dockerfile:513) et son service
# main-hermes n'est qu'un « sleep infinity » (docker/s6-rc.d/main-hermes/run ;
# website/docs/user-guide/docker.md:61-66).
CMD ["gateway", "run"]
