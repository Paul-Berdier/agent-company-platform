# Image Railway de l'EXÉCUTANT d'ACP (service « executant », cahier P6 § 8) : le client apps/poste en mode Linux
# (superviseur root sous tini), Codex CLI 0.156.1 et Claude Code 2.1.283 vérifiés, un UID par agent.
#
# Contexte de construction : la RACINE du dépôt (l'image embarque apps/poste et le contrat du greffon) ;
# liste blanche du contexte : executant/Dockerfile.dockerignore (lue par BuildKit à côté de ce fichier).
#   docker build -f executant/Dockerfile -t acp-executant:ci .                    (cible finale, celle de Railway)
#   docker build -f executant/Dockerfile --target factice -t acp-executant:factice .   (tests : CLI factices)
#
# Aucun EXPOSE, aucun HEALTHCHECK, aucun ARG ni ENV qui porte un secret (scripts/tests/test_railway_iac.py) : les
# jetons sont déposés sur le volume par « railway ssh » (cahier § 11, décision D92 du dépôt). Versions, adresses et
# empreintes : executant/binaires.toml (une montée de version change ce fichier ET les lignes épinglées ci-dessous,
# dans la même PR ; executant/tests/test_dockerfile.py vérifie qu'ils concordent).

# Base Debian trixie avec Python 3.12, épinglée par le condensat de l'INDEX multi-architecture, relevé le
# 1er octobre 2026 par « docker buildx imagetools inspect python:3.12-slim-trixie » (Python 3.12.14). Railway
# construit en linux/amd64.
FROM python:3.12-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS base
# Paquets des dépôts SIGNÉS de Debian, versions fixées ([apt] de binaires.toml). bubblewrap : le seul bwrap de
# l'image (Codex prend celui du PATH, cahier § 4.1 point 6) ; util-linux : setpriv, unshare, mountpoint ; procps :
# kill et /proc ; tini : PID 1 (récolte des processus orphelins des agents) ; ripgrep et socat : outils des CLI.
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git=1:2.47.3-0+deb13u1 \
        bubblewrap=0.12.0-1~deb13u1 \
        socat=1.8.0.3-1+deb13u1 \
        ripgrep=14.1.1-1+b4 \
        tini=0.19.0-3+b8 \
        util-linux=2.41.5-0+deb13u1 \
        ca-certificates=20250419 \
        procps=2:4.0.4-9; \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------------------------------------------
# Binaires des agents : téléchargés, puis contrôlés par verifier-binaires (tailles, SHA-256, signature GPG du
# manifeste de Claude Code par la clé du dépôt). Toute différence fait échouer le build, en français.
FROM base AS binaires
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends gnupg=2.4.7-21+deb13u1; \
    rm -rf /var/lib/apt/lists/*
COPY executant/binaires.toml /opt/acp/construction/binaires.toml
COPY executant/cles/ /opt/acp/construction/cles/
COPY executant/bin/verifier-binaires /opt/acp/construction/bin/verifier-binaires
RUN python3 -I /opt/acp/construction/bin/verifier-binaires --telecharger --sortie /opt/acp/outils \
        --binaires /opt/acp/construction/binaires.toml

# ---------------------------------------------------------------------------------------------------------------
# Roues de pydantic (contrat partagé, décision D61) : le verrou du poste, haché, tel quel (mêmes versions que le
# poste Windows par construction) ; roues binaires seulement, puis installation HORS LIGNE.
FROM base AS roues
COPY requirements/poste-3.12.lock.txt /opt/acp/construction/poste-3.12.lock.txt
RUN python -m pip download --no-cache-dir --no-deps --only-binary=:all: --require-hashes \
        -r /opt/acp/construction/poste-3.12.lock.txt -d /opt/acp/roues

# ---------------------------------------------------------------------------------------------------------------
# Tout sauf les binaires des agents : comptes, bibliothèques, sources du poste, configuration, entrée.
FROM base AS commun
# useradd -g exige un groupe existant : les groupes d'abord. UID et GID fixes (cahier § 3.3), shell nologin,
# dossier personnel 0700 à l'agent.
RUN set -eu; \
    groupadd -g 10100 acp-travail; \
    groupadd -g 10001 acp-codex; \
    groupadd -g 10002 acp-claude; \
    groupadd -g 10003 acp-verif; \
    useradd -u 10001 -g 10001 -G acp-travail -m -d /home/acp-codex -s /usr/sbin/nologin acp-codex; \
    useradd -u 10002 -g 10002 -G acp-travail -m -d /home/acp-claude -s /usr/sbin/nologin acp-claude; \
    useradd -u 10003 -g 10003 -G acp-travail -m -d /home/acp-verif -s /usr/sbin/nologin acp-verif; \
    chmod 0700 /home/acp-codex /home/acp-claude /home/acp-verif
COPY requirements/poste-3.12.lock.txt /opt/acp/construction/poste-3.12.lock.txt
COPY --from=roues /opt/acp/roues /opt/acp/roues
RUN set -eu; \
    python -m pip install --no-cache-dir --no-index --no-deps --require-hashes --find-links /opt/acp/roues \
        --target /opt/acp/lib -r /opt/acp/construction/poste-3.12.lock.txt; \
    rm -rf /opt/acp/roues /opt/acp/construction
# Sources COPIÉES, pas construites (comme le poste P5, décision D53 : setuptools absent de Python 3.12, et
# --no-index interdit de télécharger un moteur de construction). Le lanceur de P5 place /opt/acp/lib en tête de
# sys.path sous « python -I » (qui ignore PYTHONPATH) : il vit donc à côté de lib, en /opt/acp/lancer.py.
COPY apps/poste/src/acp_poste/ /opt/acp/lib/acp_poste/
COPY hermes/plugins/acp-poste/contrat/acp_poste_contrat/ /opt/acp/lib/acp_poste_contrat/
COPY packaging/poste/lancer.py /opt/acp/lancer.py
COPY executant/binaires.toml /opt/acp/binaires.toml
COPY executant/cles/ /opt/acp/cles/
COPY executant/bin/acp-entree-executant executant/bin/acp-askpass executant/bin/verifier-binaires executant/bin/verifier-superviseur /opt/acp/bin/
COPY executant/bin/acp-poste /usr/local/bin/acp-poste
COPY executant/politique/executant.toml /etc/acp/executant.toml
COPY executant/claude-settings.json /etc/acp/claude-settings.json
COPY executant/gitconfig /etc/gitconfig
# Tout ce que lit ou exécute le superviseur root appartient à root et n'est inscriptible par aucun agent
# (transposition de D67 : acp_poste.politique.verifier_interpreteur refuse de démarrer sinon). Bytecode compilé
# ici : à l'exécution, PYTHONDONTWRITEBYTECODE=1, rien n'est écrit sous /opt/acp.
RUN set -eu; \
    python -m compileall -q /opt/acp/lib /opt/acp/lancer.py; \
    chown -R root:root /opt/acp /etc/acp /etc/gitconfig /usr/local/bin/acp-poste; \
    find /opt/acp -type d -exec chmod 0755 {} +; \
    find /opt/acp -type f -exec chmod 0644 {} +; \
    chmod 0755 /opt/acp/bin/acp-entree-executant /opt/acp/bin/acp-askpass /opt/acp/bin/verifier-binaires \
        /usr/local/bin/acp-poste; \
    chmod 0755 /etc/acp; \
    chmod 0444 /etc/acp/executant.toml /etc/acp/claude-settings.json /etc/gitconfig
# DISABLE_* : aucune mise à jour ni télémétrie de Claude Code (le superviseur les repose dans l'environnement CALCULÉ
# de chaque agent ; ici pour un « claude » lancé à la main dans railway ssh).
ENV PYTHONDONTWRITEBYTECODE=1 \
    DISABLE_UPDATES=1 \
    DISABLE_AUTOUPDATER=1 \
    DISABLE_TELEMETRY=1
# tini en PID 1 (exigé par l'entrée), puis l'entrée root qui prépare le volume et lance le superviseur. Une Start
# Command Railway remplace cet ENTRYPOINT : réservée à la sonde R0 dans le projet jetable « acp-sonde » (cahier § 4.1).
ENTRYPOINT ["/usr/bin/tini", "-s", "--", "/opt/acp/bin/acp-entree-executant"]

# ---------------------------------------------------------------------------------------------------------------
# Cible de TEST « factice » (cahier § 14.3) : deux programmes Python remplacent Codex et Claude Code. Jamais
# construite par Railway (qui construit la dernière cible, « finale ») ; elle ne prouve que la plomberie.
FROM commun AS factice
COPY executant/factice/faux-codex /opt/acp/outils/codex/codex
COPY executant/factice/faux-claude /opt/acp/outils/claude/claude
COPY executant/factice/scenarios.json /opt/acp/outils/scenarios-factices.json
RUN set -eu; \
    chown -R root:root /opt/acp/outils; \
    chmod 0755 /opt/acp/outils /opt/acp/outils/codex /opt/acp/outils/claude /opt/acp/outils/codex/codex \
        /opt/acp/outils/claude/claude; \
    chmod 0444 /opt/acp/outils/scenarios-factices.json; \
    install -d -m 1777 /var/tmp/acp-factice

# ---------------------------------------------------------------------------------------------------------------
# Cible FINALE, celle que Railway construit et déploie : binaires vérifiés, root, 0755, non inscriptibles.
FROM commun AS finale
COPY --from=binaires /opt/acp/outils /opt/acp/outils
RUN set -eu; \
    chown -R root:root /opt/acp/outils; \
    find /opt/acp/outils -type d -exec chmod 0755 {} +; \
    chmod 0644 /opt/acp/outils/PROVENANCE.json; \
    python3 -I /opt/acp/bin/verifier-binaires --controler /opt/acp/outils
