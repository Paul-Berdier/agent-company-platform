"""CLI d'installation et d'exploitation du worker."""

import argparse
import asyncio
import json
import sys

import httpx
from pydantic import ValidationError

from acp_contracts import WorkerCapability, WorkerRegistrationResponse

from .capabilities import detect_capabilities
from .config import WorkerConfig, WorkerConfigurationError
from .executors import ExecutorCleanupError
from .local_runner import RunnerConfigurationError
from .local_log import tail_logs
from .mcp_probe import McpProbeConfigurationError
from .main import run_forever
from .web_tests import WebTestConfigurationError
from .state import (
    CredentialStateError,
    WorkerCredentials,
    load_credentials,
    save_credentials,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-company-worker")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="Enregistrer ou renouveler ce worker")
    register.add_argument("--name")
    register.add_argument(
        "--capability",
        action="append",
        choices=[capability.value for capability in WorkerCapability],
        dest="capabilities",
    )
    register.add_argument("--max-concurrency", type=int)
    register.add_argument("--real", action="store_true", help="Désactiver la simulation")
    scope = register.add_mutually_exclusive_group()
    scope.add_argument(
        "--project",
        dest="project_id",
        help="Limiter les claims à cet identifiant de projet",
    )
    scope.add_argument(
        "--global-access",
        action="store_true",
        default=None,
        help="Autoriser explicitement les claims de tous les projets et le planificateur",
    )
    commands.add_parser("doctor", help="Vérifier l'environnement et la connectivité")
    start = commands.add_parser("start", help="Démarrer la boucle du worker")
    start.add_argument("--once", action="store_true", help="Faire un seul claim puis quitter")
    commands.add_parser("capabilities", help="Afficher les capacités détectées")
    logs = commands.add_parser("logs", help="Afficher le journal local")
    logs.add_argument("--tail", type=int, default=100)
    return parser


def _register(config: WorkerConfig, args: argparse.Namespace) -> int:
    if not config.registration_token:
        print("ACP_WORKER_REGISTRATION_TOKEN est requis", file=sys.stderr)
        return 2
    simulation = config.simulation and not args.real
    try:
        config.validate_execution_mode(simulation=simulation)
    except WorkerConfigurationError as exc:
        print(f"Mode réel refusé: {exc}.", file=sys.stderr)
        return 2
    # Le mode annoncé est celui qui sera enregistré : `--real` doit rendre
    # annonçables les capacités réservées au mode réel, sans dépendre d'une
    # seconde lecture de ACP_WORKER_SIMULATION.
    capabilities = sorted(
        set(
            args.capabilities
            or detect_capabilities(
                simulation=simulation,
                local_runner_configured=config.local_runner is not None,
            )
        )
    )
    max_concurrency = (
        config.max_concurrency
        if args.max_concurrency is None
        else args.max_concurrency
    )
    if not 1 <= max_concurrency <= 32:
        print("max-concurrency doit être compris entre 1 et 32", file=sys.stderr)
        return 2
    if args.project_id is not None:
        project_id = args.project_id.strip()
        global_access = False
        if not project_id or len(project_id) > 36:
            print(
                "project doit contenir entre 1 et 36 caractères",
                file=sys.stderr,
            )
            return 2
    elif args.global_access is True:
        project_id = None
        global_access = True
    else:
        project_id = config.project_id
        global_access = config.global_access
    if project_id is None and not global_access:
        print(
            "Périmètre worker requis: utilisez --project ID (recommandé) ou "
            "--global-access pour un worker d'administration.",
            file=sys.stderr,
        )
        return 2
    try:
        config.validate_advertised_capabilities(
            capabilities,
            simulation=simulation,
            project_id=project_id,
            global_access=global_access,
        )
    except WorkerConfigurationError as exc:
        print(f"Capacités refusées: {exc}.", file=sys.stderr)
        return 2
    try:
        response = httpx.post(
            f"{config.api_url}/workers/register",
            headers={"X-Worker-Registration-Token": config.registration_token},
            json={
                "name": args.name or config.name,
                "capabilities": capabilities,
                "max_concurrency": max_concurrency,
                "simulation": simulation,
                "project_id": project_id,
                "global_access": global_access,
                "metadata": config.metadata,
            },
            timeout=15.0,
            trust_env=False,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            print(
                "Enregistrement refusé: le périmètre demandé ne correspond pas "
                "à ACP_WORKER_REGISTRATION_PROJECT_ID/"
                "ACP_WORKER_REGISTRATION_GLOBAL_ACCESS sur l'API.",
                file=sys.stderr,
            )
        else:
            print(f"Enregistrement impossible: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"Enregistrement impossible: {exc}", file=sys.stderr)
        return 1
    try:
        result = WorkerRegistrationResponse.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        print(f"Réponse d'enregistrement invalide: {exc}", file=sys.stderr)
        return 1
    if result.project_id != project_id or result.global_access is not global_access:
        print(
            "Résultat d'enregistrement incertain: le périmètre renvoyé diffère; "
            "réenregistrez seulement après vérification côté API.",
            file=sys.stderr,
        )
        return 1
    credentials = WorkerCredentials(
        worker_id=result.worker_id,
        token=result.token,
        api_origin=config.api_url,
        name=args.name or config.name,
        capabilities=capabilities,
        max_concurrency=max_concurrency,
        simulation=simulation,
        token_expires_at=result.token_expires_at.isoformat(),
        heartbeat_interval_seconds=result.heartbeat_interval_seconds,
        project_id=result.project_id,
        global_access=result.global_access,
    )
    path = save_credentials(config.state_dir, credentials)
    print(
        json.dumps(
            {
                "worker_id": credentials.worker_id,
                "state": str(path),
                "capabilities": capabilities,
                "project_id": credentials.project_id,
                "global_access": credentials.global_access,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _web_tests_state(config: WorkerConfig, capabilities: list[str]) -> str:
    """État des tests web tel qu'il sera réellement annoncé, sans le contredire.

    Une configuration complète en mode simulé est activée sans être annonçable :
    la publier ``enabled`` laisserait croire qu'une mission ``web_test_suite``
    sera exécutée par la suite Playwright, alors qu'elle repartirait vers le
    programme local du Lot C — un faux succès dont ``doctor`` serait la source.
    """

    status = config.web_tests.status()
    if status == "enabled" and WorkerCapability.WEB_TESTS.value not in capabilities:
        return "enabled_not_announced"
    return status


def _api_readiness(config: WorkerConfig, checks: dict[str, object]) -> None:
    """Interroge ``/ready`` et publie ``api_readiness`` sans jamais l'inventer.

    « ready » exige un 200 ; un 503 donne « degraded » avec la liste des contrôles
    en échec extraite du corps ; un 404 (API antérieure au Lot H2a) donne
    « unavailable » : une readiness absente n'est pas une readiness acquise.
    Tout autre statut ou une erreur réseau sont publiés tels quels.
    """

    try:
        response = httpx.get(f"{config.api_url}/ready", timeout=5.0, trust_env=False)
    except httpx.HTTPError:
        checks["api_readiness"] = "unreachable"
        return
    if response.status_code == 200:
        checks["api_readiness"] = "ready"
        return
    if response.status_code == 404:
        checks["api_readiness"] = "unavailable"
        return
    if response.status_code != 503:
        checks["api_readiness"] = f"http_{response.status_code}"
        return
    checks["api_readiness"] = "degraded"
    failed: list[str] = []
    try:
        body = response.json()
    except ValueError:
        body = None
    reported = body.get("checks") if isinstance(body, dict) else None
    if isinstance(reported, dict):
        failed = sorted(
            name
            for name, check in reported.items()
            if isinstance(check, dict) and check.get("ok") is False
        )
    checks["api_readiness_failed"] = failed


def _doctor(config: WorkerConfig) -> int:
    credential_error: str | None = None
    try:
        credentials = load_credentials(config.state_dir, config.api_url)
    except CredentialStateError as exc:
        credentials = None
        credential_error = str(exc)
    # Mode effectif : celui du worker déjà enregistré s'il existe, sinon celui
    # que l'environnement produirait au prochain `register`.
    simulation = (
        credentials.simulation if credentials is not None else config.simulation
    )
    capabilities = detect_capabilities(
        simulation=simulation,
        local_runner_configured=config.local_runner is not None,
    )
    checks: dict[str, object] = {
        "state": (
            "invalid" if credential_error else ("ok" if credentials else "missing")
        ),
        "capabilities": capabilities,
        "local_runner": "configured" if config.local_runner is not None else "missing",
        "agent_executors": sorted(config.executors.enabled_executors),
        "executor_project_roots": len(config.executors.project_roots),
        "mcp_stdio_probe": config.mcp_probe.status(),
        "web_tests": _web_tests_state(config, capabilities),
        "api": "unreachable",
        "api_readiness": "unchecked",
        "gateway": "unreachable",
        "provider": "unchecked",
        "scope": (
            "global"
            if (credentials.global_access if credentials else config.global_access)
            else (
                f"project:{credentials.project_id if credentials else config.project_id}"
                if (credentials.project_id if credentials else config.project_id)
                else "missing"
            )
        ),
    }
    if config.mcp_probe.status() == "enabled":
        # Le nombre d'entrées suffit au diagnostic : les chemins autorisés ne
        # sont pas imprimés.
        checks["mcp_stdio_allowed_executables"] = len(
            config.mcp_probe.allowed_executables
        )
    if config.web_tests.status() == "enabled":
        # Argv, racine de projet et délai : ce que l'opérateur doit pouvoir
        # vérifier avant d'autoriser un lancement. Aucune **valeur**
        # d'environnement n'est publiée, seulement le nombre de noms allowlistés.
        checks.update(config.web_tests.doctor_report())
    if credential_error:
        checks["state_error"] = credential_error
    execution_error: str | None = None
    if credentials is not None:
        try:
            config.validate_advertised_capabilities(
                credentials.capabilities,
                simulation=credentials.simulation,
                project_id=credentials.project_id,
                global_access=credentials.global_access,
            )
        except WorkerConfigurationError as exc:
            execution_error = str(exc)
            checks["execution"] = "invalid"
            checks["execution_error"] = execution_error
        else:
            checks["execution"] = "ok"
    if execution_error is not None:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 1
    try:
        response = httpx.get(
            f"{config.api_url}/health", timeout=5.0, trust_env=False
        )
        checks["api"] = "ok" if response.status_code < 400 else f"http_{response.status_code}"
    except httpx.HTTPError:
        pass
    if checks["api"] == "ok":
        # La readiness n'est interrogée que sur une API vivante : sinon le
        # diagnostic « unreachable » de la liveness suffit.
        _api_readiness(config, checks)
    try:
        response = httpx.get(
            f"{config.gateway_url}/health", timeout=5.0, trust_env=False
        )
        checks["gateway"] = "ok" if response.status_code < 400 else f"http_{response.status_code}"
    except httpx.HTTPError:
        pass
    if not config.gateway_service_token:
        checks["provider"] = "missing_service_token"
    else:
        try:
            response = httpx.get(
                f"{config.gateway_url}/v1/providers/{config.provider_id}/health",
                headers={
                    "Authorization": f"Bearer {config.gateway_service_token}"
                },
                timeout=5.0,
                trust_env=False,
            )
            if response.status_code >= 400:
                checks["provider"] = f"http_{response.status_code}"
            else:
                provider_health = response.json()
                checks["provider"] = (
                    "ok"
                    if isinstance(provider_health, dict)
                    and provider_health.get("provider_id") == config.provider_id
                    and provider_health.get("available") is True
                    else "unavailable"
                )
        except (httpx.HTTPError, ValueError):
            checks["provider"] = "unreachable"
    if credentials and checks["api"] == "ok":
        try:
            response = httpx.post(
                f"{config.api_url}/workers/{credentials.worker_id}/heartbeat",
                headers={"Authorization": f"Bearer {credentials.token}"},
                json={},
                timeout=5.0,
                trust_env=False,
            )
            checks["authentication"] = (
                "ok" if response.status_code < 400 else f"http_{response.status_code}"
            )
        except httpx.HTTPError:
            checks["authentication"] = "unreachable"
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    required_ok = (
        checks["state"] == "ok"
        and checks["scope"] != "missing"
        and checks["api"] == "ok"
        and checks["api_readiness"] == "ready"
        and checks["gateway"] == "ok"
        and checks["provider"] == "ok"
    )
    execution_ok = credentials is not None and execution_error is None
    return 0 if required_ok and execution_ok and checks.get("authentication") == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = WorkerConfig.from_env()
    except (
        RunnerConfigurationError,
        WorkerConfigurationError,
        McpProbeConfigurationError,
        WebTestConfigurationError,
    ) as exc:
        print(f"Configuration worker refusée: {exc}", file=sys.stderr)
        return 2
    if args.command == "register":
        return _register(config, args)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "capabilities":
        print(
            json.dumps(
                detect_capabilities(
                    simulation=config.simulation,
                    local_runner_configured=config.local_runner is not None,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "logs":
        for line in tail_logs(config.state_dir, max(1, args.tail)):
            print(line)
        return 0
    try:
        credentials = load_credentials(config.state_dir, config.api_url)
    except CredentialStateError as exc:
        print(f"Credentials worker refusés: {exc}", file=sys.stderr)
        return 2
    if credentials is None:
        print("Worker non enregistré. Exécutez agent-company-worker register.", file=sys.stderr)
        return 2
    if credentials.project_id is None and not credentials.global_access:
        print(
            "Credentials worker sans périmètre; réenregistrez avec --project ID "
            "ou --global-access.",
            file=sys.stderr,
        )
        return 2
    try:
        config.validate_advertised_capabilities(
            credentials.capabilities,
            simulation=credentials.simulation,
            project_id=credentials.project_id,
            global_access=credentials.global_access,
        )
    except WorkerConfigurationError as exc:
        print(f"Mode d'exécution refusé: {exc}.", file=sys.stderr)
        return 2
    try:
        asyncio.run(run_forever(config, credentials, once=args.once))
    except ExecutorCleanupError:
        print(
            "Worker arrêté par sécurité: nettoyage d'un exécuteur non confirmé.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
