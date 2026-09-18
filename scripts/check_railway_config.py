"""Vérifie les fichiers Railway « config as code » de ``deploy/railway/<service>/railway.json``.

Railway lit ces fichiers tels quels et une clé inconnue est ignorée sans erreur : une
faute de frappe dans ``healthcheckPath`` ou ``preDeployCommand`` produirait un
déploiement sans readiness ou sans migration, en silence. Ce script refuse donc tout
ce qui sort du schéma officiel et des règles du Lot H :

- seules les clés lues dans ``https://railway.com/railway.schema.json`` (redirigé vers
  ``backboard.railway.app``, lectures du 17 septembre 2026 et du 18 septembre 2026)
  sont admises ;
- ``preDeployCommand`` (migration exclusive) n'existe que sur ``api`` ;
- chaque service a le constructeur ``DOCKERFILE``, un ``dockerfilePath`` existant, le
  chemin de readiness attendu et une politique de redémarrage ``ON_FAILURE`` ;
- ``api``, ``artifact-preview`` et ``relay`` restent à une seule réplique (volume ou
  relais exclusif) ;
- ``sleepApplication`` vaut explicitement ``false`` partout : un service endormi rompt
  les flux SSE d'un client distant, et « Configuration defined in code will always
  override values from the dashboard » — le déclarer ici empêche qu'un réglage du
  tableau de bord l'active en silence ;
- ``cronSchedule`` est interdit sur ces six services de longue durée : la clé
  transformerait le service en tâche planifiée sans que rien n'échoue bruyamment ;
- aucune commande de démarrage versionnée ne fait confiance à tout ``X-Forwarded-For``
  (``--forwarded-allow-ips *``) : cette décision appartient à l'exploitation, par la
  variable ``ACP_TRUSTED_PROXY_IPS`` lue par ``docker/entrypoint.sh`` ;
- ``deploy/railway`` ne contient aucun répertoire de service inconnu, qu'aucune règle
  ne vérifierait.

L'option ``--exposure`` imprime l'exposition publique **voulue** par le dépôt. Railway
n'applique rien de cela : les domaines se génèrent au tableau de bord et ne sont
déclarables dans aucun fichier. C'est une liste à comparer à la main, pas une preuve.

Code de sortie 0 si tout est conforme, 1 sinon (motifs en français sur stderr).
"""

from __future__ import annotations

import argparse
import json
import re
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

# Règles par service : readiness attendue, réplique unique, migration, et exposition
# publique voulue (« exposure », informative : voir --exposure et le module).
SERVICES: dict[str, dict[str, Any]] = {
    "api": {
        "healthcheck": "/ready",
        "single_replica": True,
        "pre_deploy": True,
        "exposure": "public",
        "exposure_reason": "seul point d'entrée des clients (desktop, CLI, web) : HTTPS et SSE",
    },
    "artifact-preview": {
        "healthcheck": "/ready",
        "single_replica": True,
        "pre_deploy": False,
        "exposure": "privé",
        "exposure_reason": "sans volume partagé il ne lit aucun livrable : un domaine public ne publierait qu'une surface inutile",
    },
    "provider-gateway": {
        "healthcheck": "/health",
        "single_replica": False,
        "pre_deploy": False,
        "exposure": "privé",
        "exposure_reason": "joignable par l'API seule, avec un jeton de service",
    },
    "event-service": {
        "healthcheck": "/health",
        "single_replica": False,
        "pre_deploy": False,
        "exposure": "privé",
        "exposure_reason": "relais interne ; le flux utilisateur est servi par l'API",
    },
    "relay": {
        "healthcheck": None,
        "single_replica": True,
        "pre_deploy": False,
        "exposure": "privé",
        "exposure_reason": "aucun serveur HTTP : un domaine public n'aurait rien à servir",
    },
    "web": {
        "healthcheck": "/",
        "single_replica": False,
        "pre_deploy": False,
        "exposure": "public si déployé",
        "exposure_reason": "interface navigateur ; inutile si seul le client desktop est servi",
    },
}
ENTRYPOINT = "/app/docker/entrypoint.sh"
UNKNOWN_SERVICES_KEY = "(répertoires)"

# ``--forwarded-allow-ips *`` fait retenir à uvicorn la première entrée de
# ``X-Forwarded-For``, c'est-à-dire une valeur choisie par l'appelant : cette décision
# ne peut pas être figée dans le dépôt.
WILDCARD_PROXY_TRUST = re.compile(r"--forwarded-allow-ips[=\s]+['\"]?\*")


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
    if isinstance(start, str) and WILDCARD_PROXY_TRUST.search(start):
        errors.append(
            "deploy.startCommand ne doit pas figer « --forwarded-allow-ips * » : la liste "
            "des proxys de confiance se déclare à l'exploitation par ACP_TRUSTED_PROXY_IPS"
        )

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

    if deploy.get("sleepApplication") is not False:
        errors.append(
            "deploy.sleepApplication doit valoir false : un service endormi coupe les flux "
            "SSE et la livraison de la boîte d'envoi, et le déclarer ici prime sur le "
            "tableau de bord"
        )

    if "cronSchedule" in deploy:
        errors.append(
            f"deploy.cronSchedule est interdit sur {service} : ce service tourne en continu ; "
            "une rétention ou une sauvegarde planifiée demande un service dédié"
        )

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


def unknown_service_dirs(config_dir: Path = CONFIG_DIR) -> list[str]:
    """Répertoires de ``deploy/railway`` qui ne correspondent à aucun service connu.

    Un tel répertoire ne serait vérifié par aucune règle : il passerait pour une
    configuration valide alors que personne ne l'a relu.
    """

    try:
        entries = sorted(entry.name for entry in config_dir.iterdir() if entry.is_dir())
    except OSError:
        return []
    return [name for name in entries if name not in SERVICES]


def check_directory(config_dir: Path = CONFIG_DIR, root: Path = ROOT) -> dict[str, list[str]]:
    """Vérifie les six services attendus ; retourne les écarts par service (clés sans écart omises)."""

    report: dict[str, list[str]] = {}
    for service in SERVICES:
        errors = validate_file(config_dir / service / "railway.json", service, root)
        if errors:
            report[service] = errors
    unknown = unknown_service_dirs(config_dir)
    if unknown:
        report[UNKNOWN_SERVICES_KEY] = [
            f"répertoire de service inconnu, vérifié par aucune règle : {name} "
            f"(services attendus : {', '.join(sorted(SERVICES))})"
            for name in unknown
        ]
    return report


def exposure_lines() -> list[str]:
    """Exposition publique voulue, service par service (intention du dépôt)."""

    name_width = max(len(name) for name in SERVICES)
    exposure_width = max(len(rules["exposure"]) for rules in SERVICES.values())
    return [
        f"{name.ljust(name_width)}  {rules['exposure'].ljust(exposure_width)}  {rules['exposure_reason']}"
        for name, rules in SERVICES.items()
    ]


def _force_utf8_streams() -> None:
    """Écrit en UTF-8 quelle que soit la console : la sortie est lue par des tests
    et des scripts qui la décodent en UTF-8, et une console Windows en cp1252
    rendrait sinon les accents illisibles ou fatals au décodage."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : code 0 si les six fichiers sont conformes, 1 sinon."""
    _force_utf8_streams()

    parser = argparse.ArgumentParser(description="Vérifie deploy/railway/*/railway.json")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--root", type=Path, default=ROOT, help="racine du dépôt pour résoudre dockerfilePath")
    parser.add_argument(
        "--exposure",
        action="store_true",
        help="imprime l'exposition publique voulue puis sort (Railway n'applique rien de cela)",
    )
    args = parser.parse_args(argv)

    if args.exposure:
        print("Exposition publique voulue (intention du dépôt, à comparer au tableau de bord) :")
        for line in exposure_lines():
            print(f"- {line}")
        print(
            "Aucun domaine n'est déclarable dans ces fichiers : cette liste ne prouve rien, "
            "elle sert de relecture."
        )
        return 0

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
