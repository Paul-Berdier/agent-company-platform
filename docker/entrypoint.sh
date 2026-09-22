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
# Il doit aussi se trouver sur un volume monté : l'image crée /data elle-même, si bien
# que sans volume le répertoire existe, reste inscriptible, et tout ce qui y est écrit
# disparaît au redéploiement pendant que la base continue de le référencer. Sans
# montage, le service refuse de démarrer (code 3), sauf dérogation explicite
# ``ACP_DATA_DIR_EPHEMERAL=1`` pour un usage jetable assumé. ``check-data`` vérifie
# tout cela sans lancer de service.
set -eu

PORT="${PORT:-8000}"
ACP_DATA_DIR="${ACP_DATA_DIR:-/data}"

# Vrai si le chemin (existant ou non) se trouve sous un point de montage autre que la
# racine du système de fichiers : volume Docker ou Railway, montage lié.
on_mounted_volume() {
    python - "$1" <<'PY'
import os
import sys

path = os.path.realpath(sys.argv[1])
while os.path.dirname(path) != path:
    if os.path.ismount(path):
        sys.exit(0)
    path = os.path.dirname(path)
sys.exit(1)
PY
}

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
    if [ "${ACP_DATA_DIR_EPHEMERAL:-}" = "1" ]; then
        echo "Attention : ACP_DATA_DIR_EPHEMERAL=1, les livrables et les skills ne survivront pas au redéploiement." >&2
        return
    fi
    for directory in "$ACP_DATA_DIR" "$ACP_ARTIFACT_STORAGE_DIR" "$ACP_SKILLS_STORAGE_DIR"; do
        if ! on_mounted_volume "$directory"; then
            echo "Refus de démarrer : $directory n'est sur aucun volume monté ; ses fichiers seraient perdus au redéploiement alors que la base les référencerait encore. Monter un volume sur $ACP_DATA_DIR, ou poser ACP_DATA_DIR_EPHEMERAL=1 pour un usage jetable assumé." >&2
            exit 3
        fi
    done
}

command="${1:-api}"
if [ "$#" -gt 0 ]; then
    shift
fi

case "$command" in
    api)
        require_data_dir
        exec python -m uvicorn acp_api.main:app --host 0.0.0.0 --port "$PORT" "$@"
        ;;
    preview)
        require_data_dir
        exec python -m uvicorn acp_api.preview:app --host 0.0.0.0 --port "$PORT" "$@"
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
    check-data)
        require_data_dir
        echo "Répertoire de données conforme : $ACP_DATA_DIR (livrables : $ACP_ARTIFACT_STORAGE_DIR, skills : $ACP_SKILLS_STORAGE_DIR)."
        ;;
    *)
        exec "$command" "$@"
        ;;
esac
