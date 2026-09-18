#!/bin/sh
# Point d'entrée de l'image Python (docker/python.Dockerfile).
#
# Le premier argument choisit le processus ; toute autre valeur est exécutée telle
# quelle (``docker run acp-python:… python -c …``). Les commandes sont celles fixées
# par le Lot H : elles peuvent référencer des modules livrés par d'autres lots
# (migrations H1, relais H3, sauvegarde H4) ; si le module manque, Python échoue
# explicitement (« No module named … »), jamais en silence.
#
# Le répertoire de données (``ACP_DATA_DIR``, défaut ``/data``) porte les livrables et
# les skills. S'il n'est pas inscriptible par l'utilisateur courant, le service refuse
# de démarrer (code 3) : aucun ``chown`` n'est tenté, car changer silencieusement le
# propriétaire d'un volume masquerait une erreur de montage ou d'identité.
#
# Les deux services HTTP destinés à vivre derrière une terminaison TLS en amont
# (``api`` et ``preview``) déclarent explicitement à uvicorn quelles adresses ont le
# droit de poser ``X-Forwarded-Proto`` et ``X-Forwarded-For`` : voir
# ``trusted_proxy_ips`` et ``docs/railway-architecture.md``.
set -eu

PORT="${PORT:-8000}"
ACP_DATA_DIR="${ACP_DATA_DIR:-/data}"

require_data_dir() {
    if [ ! -d "$ACP_DATA_DIR" ]; then
        echo "Refus de démarrer : le répertoire de données $ACP_DATA_DIR n'existe pas (monter un volume ou définir ACP_DATA_DIR)." >&2
        exit 3
    fi
    if [ ! -w "$ACP_DATA_DIR" ]; then
        echo "Refus de démarrer : $ACP_DATA_DIR n'est pas inscriptible par l'utilisateur $(id -u):$(id -g) ; aucun chown n'est tenté. Corriger le propriétaire du volume côté hôte ou l'identité d'exécution." >&2
        exit 3
    fi
    # Les stockages locaux de l'API pointent par défaut sur ./acp-data, c'est-à-dire
    # la couche éphémère du conteneur : on les ancre explicitement dans le volume
    # sauf réglage contraire de l'opérateur.
    export ACP_ARTIFACT_STORAGE_DIR="${ACP_ARTIFACT_STORAGE_DIR:-$ACP_DATA_DIR/artifacts}"
    export ACP_SKILLS_STORAGE_DIR="${ACP_SKILLS_STORAGE_DIR:-$ACP_DATA_DIR/skills}"
}

# Adresses autorisées à porter les en-têtes du proxy, écrites sur la sortie standard.
#
# uvicorn active ``--proxy-headers`` par défaut mais ne fait confiance qu'à
# ``127.0.0.1`` tant que ``--forwarded-allow-ips`` n'est pas fourni, et retombe sinon
# sur la variable d'environnement ambiante ``FORWARDED_ALLOW_IPS``. Derrière une
# terminaison TLS en amont, le résultat est un schéma vu comme « http » et une adresse
# client égale à celle du proxy pour tout le trafic. On fixe donc la valeur ici, à
# partir de la seule variable du produit (``ACP_TRUSTED_PROXY_IPS``), pour que ni un
# changement de défaut d'uvicorn ni une variable étrangère ne puisse la déplacer en
# silence.
#
# Défaut fermé : boucle locale seulement. L'opérateur qui met le service derrière un
# proxy déclare explicitement l'adresse, le réseau, ou ``*`` s'il accepte d'en croire
# n'importe quelle valeur — auquel cas un avertissement est écrit sur stderr, car
# uvicorn retient alors la **première** entrée de ``X-Forwarded-For``, c'est-à-dire une
# valeur entièrement choisie par l'appelant.
trusted_proxy_ips() {
    trusted="${ACP_TRUSTED_PROXY_IPS:-}"
    if [ -z "$trusted" ]; then
        trusted="127.0.0.1,::1"
    elif [ "$trusted" = "*" ]; then
        echo "Avertissement : ACP_TRUSTED_PROXY_IPS=* fait confiance à tout X-Forwarded-For reçu ; l'adresse client et le schéma deviennent falsifiables par l'appelant." >&2
    fi
    printf '%s' "$trusted"
}

command="${1:-api}"
if [ "$#" -gt 0 ]; then
    shift
fi

case "$command" in
    api)
        require_data_dir
        exec python -m uvicorn acp_api.main:app --host 0.0.0.0 --port "$PORT" \
            --proxy-headers --forwarded-allow-ips "$(trusted_proxy_ips)" "$@"
        ;;
    preview)
        require_data_dir
        exec python -m uvicorn acp_api.preview:app --host 0.0.0.0 --port "$PORT" \
            --proxy-headers --forwarded-allow-ips "$(trusted_proxy_ips)" "$@"
        ;;
    gateway)
        exec python -m uvicorn acp_provider_gateway.main:app --host 0.0.0.0 --port "$PORT" "$@"
        ;;
    event-service)
        exec python -m uvicorn acp_event_service.main:app --host 0.0.0.0 --port "$PORT" "$@"
        ;;
    relay)
        exec python -m acp_api.outbox_relay --follow "$@"
        ;;
    migrate)
        exec python -m acp_database.migrate upgrade "$@"
        ;;
    backup)
        require_data_dir
        exec python -m acp_api.backup "$@"
        ;;
    *)
        exec "$command" "$@"
        ;;
esac
