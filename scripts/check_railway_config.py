"""Vérifie les fichiers Railway « config as code » de ``deploy/railway/<service>/railway.json``.

Railway lit ces fichiers tels quels et une clé inconnue est ignorée sans erreur : une
faute de frappe dans ``healthcheckPath`` ou ``preDeployCommand`` produirait un
déploiement sans readiness ou sans migration, en silence. Ce script refuse donc tout
ce qui sort du schéma officiel et des règles du Lot H :

- seules les clés lues dans ``https://railway.com/railway.schema.json`` (redirigé vers
  ``backboard.railway.app``, lecture du 17 septembre 2026) sont admises ;
- ``preDeployCommand`` (migration exclusive) n'existe que sur ``api`` ;
- chaque service a le constructeur ``DOCKERFILE``, un ``dockerfilePath`` existant, le
  chemin de readiness attendu et une politique de redémarrage ``ON_FAILURE`` ;
- ``api``, ``artifact-preview`` et ``relay`` restent à une seule réplique (volume ou
  relais exclusif).

Code de sortie 0 si tout est conforme, 1 sinon (motifs en français sur stderr).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "deploy" / "railway"
SCHEMA_URL = "https://railway.com/railway.schema.json"

# Clés relevées dans le schéma officiel (17 septembre 2026). Toute autre clé est refusée.
TOP_LEVEL_KEYS = frozenset({"$schema", "build", "deploy", "environments"})
BUILD_KEYS = frozenset(
    {
        "builder",
        "watchPatterns",
        "buildCommand",
        "dockerfilePath",
        "nixpacksConfigPath",
        "nixpacksPlan",
        "nixpacksVersion",
        "railpackVersion",
    }
)
DEPLOY_KEYS = frozenset(
    {
        "startCommand",
        "preDeployCommand",
        "preDeployTimeoutSeconds",
        "numReplicas",
        "healthcheckPath",
        "healthcheckTimeout",
        "sleepApplication",
        "runtime",
        "registryCredentials",
        "restartPolicyType",
        "restartPolicyMaxRetries",
        "cronSchedule",
        "region",
        "multiRegionConfig",
        "limitOverride",
        "requiredMountPath",
        "overlapSeconds",
        "drainingSeconds",
        "ipv6EgressEnabled",
    }
)
BUILDERS = frozenset({"NIXPACKS", "DOCKERFILE", "RAILPACK", "HEROKU", "PAKETO"})
RESTART_POLICIES = frozenset({"ON_FAILURE", "ALWAYS", "NEVER"})

# Règles du Lot H par service : readiness attendue, réplique unique, migration.
SERVICES: dict[str, dict[str, Any]] = {
    "api": {"healthcheck": "/ready", "single_replica": True, "pre_deploy": True},
    "artifact-preview": {"healthcheck": "/ready", "single_replica": True, "pre_deploy": False},
    "provider-gateway": {"healthcheck": "/health", "single_replica": False, "pre_deploy": False},
    "event-service": {"healthcheck": "/health", "single_replica": False, "pre_deploy": False},
    "relay": {"healthcheck": None, "single_replica": True, "pre_deploy": False},
    "web": {"healthcheck": "/", "single_replica": False, "pre_deploy": False},
}
ENTRYPOINT = "/app/docker/entrypoint.sh"


def _unknown_keys(section: dict[str, Any], allowed: frozenset[str], prefix: str) -> list[str]:
    return [f"clé inconnue du schéma Railway : {prefix}{key}" for key in sorted(set(section) - allowed)]


def validate_config(data: Any, service: str, root: Path = ROOT) -> list[str]:
    """Retourne les écarts d'un document ``railway.json`` pour ``service`` (vide si conforme)."""

    rules = SERVICES.get(service)
    if rules is None:
        return [f"service inconnu : {service} (attendus : {', '.join(sorted(SERVICES))})"]
    if not isinstance(data, dict):
        return ["le document doit être un objet JSON"]

    errors: list[str] = []
    errors.extend(_unknown_keys(data, TOP_LEVEL_KEYS, ""))
    if data.get("$schema") != SCHEMA_URL:
        errors.append(f"$schema doit valoir {SCHEMA_URL}")
    if "environments" in data:
        errors.append("environments n'est pas utilisé par le Lot H : un fichier par service, sans surcharge")

    build = data.get("build")
    if not isinstance(build, dict):
        errors.append("build est obligatoire et doit être un objet")
        build = {}
    errors.extend(_unknown_keys(build, BUILD_KEYS, "build."))
    builder = build.get("builder")
    if builder not in BUILDERS:
        errors.append(f"build.builder inconnu : {builder!r} (valeurs du schéma : {', '.join(sorted(BUILDERS))})")
    elif builder != "DOCKERFILE":
        errors.append(f"build.builder doit être DOCKERFILE (trouvé : {builder})")
    dockerfile = build.get("dockerfilePath")
    if not isinstance(dockerfile, str) or not dockerfile:
        errors.append("build.dockerfilePath est obligatoire")
    elif not (root / dockerfile).is_file():
        errors.append(f"build.dockerfilePath introuvable dans le dépôt : {dockerfile}")
    patterns = build.get("watchPatterns")
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) and p for p in patterns):
        errors.append("build.watchPatterns doit être une liste non vide de motifs")

    deploy = data.get("deploy")
    if not isinstance(deploy, dict):
        errors.append("deploy est obligatoire et doit être un objet")
        deploy = {}
    errors.extend(_unknown_keys(deploy, DEPLOY_KEYS, "deploy."))

    start = deploy.get("startCommand")
    if service == "web":
        if start is not None:
            errors.append("deploy.startCommand est interdit sur web : l'image nginx fournit sa commande")
    elif not isinstance(start, str) or not start.startswith(ENTRYPOINT + " "):
        errors.append(f"deploy.startCommand doit passer par {ENTRYPOINT} <commande>")

    pre_deploy = deploy.get("preDeployCommand")
    if rules["pre_deploy"]:
        if isinstance(pre_deploy, str):
            ok = pre_deploy == f"{ENTRYPOINT} migrate"
        elif isinstance(pre_deploy, list):
            ok = pre_deploy == [ENTRYPOINT, "migrate"]
        else:
            ok = False
        if not ok:
            errors.append(f"deploy.preDeployCommand doit valoir « {ENTRYPOINT} migrate » sur {service}")
    elif pre_deploy is not None:
        errors.append(
            f"deploy.preDeployCommand est interdit sur {service} : la migration est exclusive au service api"
        )

    expected_path = rules["healthcheck"]
    actual_path = deploy.get("healthcheckPath")
    if expected_path is None:
        if actual_path is not None:
            errors.append(f"deploy.healthcheckPath est interdit sur {service} (aucun serveur HTTP)")
    elif actual_path != expected_path:
        errors.append(f"deploy.healthcheckPath doit valoir {expected_path} sur {service} (trouvé : {actual_path!r})")
    timeout = deploy.get("healthcheckTimeout")
    if expected_path is not None and (not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0):
        errors.append("deploy.healthcheckTimeout doit être un nombre de secondes strictement positif")

    if deploy.get("restartPolicyType") != "ON_FAILURE":
        errors.append("deploy.restartPolicyType doit valoir ON_FAILURE")
    retries = deploy.get("restartPolicyMaxRetries")
    if retries is not None and (not isinstance(retries, int) or isinstance(retries, bool) or retries < 1):
        errors.append("deploy.restartPolicyMaxRetries doit être un entier >= 1")

    replicas = deploy.get("numReplicas")
    if rules["single_replica"]:
        if replicas != 1:
            errors.append(f"deploy.numReplicas doit valoir 1 sur {service} (volume ou relais exclusif)")
    elif replicas is not None and (not isinstance(replicas, int) or isinstance(replicas, bool) or not 1 <= replicas <= 200):
        errors.append("deploy.numReplicas doit être un entier entre 1 et 200")

    return errors


def validate_file(path: Path, service: str, root: Path = ROOT) -> list[str]:
    """Charge ``path`` puis applique :func:`validate_config` ; un JSON illisible est un écart."""

    if not path.is_file():
        return [f"fichier introuvable : {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"JSON illisible ({exc})"]
    return validate_config(data, service, root)


def check_directory(config_dir: Path = CONFIG_DIR, root: Path = ROOT) -> dict[str, list[str]]:
    """Vérifie les six services attendus ; retourne les écarts par service (clés sans écart omises)."""

    report: dict[str, list[str]] = {}
    for service in SERVICES:
        errors = validate_file(config_dir / service / "railway.json", service, root)
        if errors:
            report[service] = errors
    return report


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : code 0 si les six fichiers sont conformes, 1 sinon."""

    parser = argparse.ArgumentParser(description="Vérifie deploy/railway/*/railway.json")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--root", type=Path, default=ROOT, help="racine du dépôt pour résoudre dockerfilePath")
    args = parser.parse_args(argv)

    report = check_directory(args.config_dir, args.root)
    if report:
        print("Configuration Railway non conforme :", file=sys.stderr)
        for service, errors in report.items():
            for error in errors:
                print(f"- {service}: {error}", file=sys.stderr)
        return 1
    print(f"Configuration Railway conforme pour {len(SERVICES)} services ({args.config_dir}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
