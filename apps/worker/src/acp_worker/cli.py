"""CLI d'installation et d'exploitation du worker."""

import argparse
import asyncio
import json
import sys

import httpx

from acp_contracts import WorkerCapability

from .capabilities import detect_capabilities
from .config import WorkerConfig
from .local_log import tail_logs
from .main import run_forever
from .state import WorkerCredentials, load_credentials, save_credentials


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
    capabilities = sorted(set(args.capabilities or detect_capabilities()))
    max_concurrency = args.max_concurrency or config.max_concurrency
    if not 1 <= max_concurrency <= 32:
        print("max-concurrency doit être compris entre 1 et 32", file=sys.stderr)
        return 2
    try:
        response = httpx.post(
            f"{config.api_url}/workers/register",
            headers={"X-Worker-Registration-Token": config.registration_token},
            json={
                "name": args.name or config.name,
                "capabilities": capabilities,
                "max_concurrency": max_concurrency,
                "simulation": not args.real and config.simulation,
                "metadata": config.metadata,
            },
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"Enregistrement impossible: {exc}", file=sys.stderr)
        return 1
    result = response.json()
    credentials = WorkerCredentials(
        worker_id=result["worker_id"],
        token=result["token"],
        name=args.name or config.name,
        capabilities=capabilities,
        max_concurrency=max_concurrency,
        simulation=not args.real and config.simulation,
        token_expires_at=result["token_expires_at"],
        heartbeat_interval_seconds=result["heartbeat_interval_seconds"],
    )
    path = save_credentials(config.state_dir, credentials)
    print(json.dumps({"worker_id": credentials.worker_id, "state": str(path), "capabilities": capabilities}, ensure_ascii=False, indent=2))
    return 0


def _doctor(config: WorkerConfig) -> int:
    credentials = load_credentials(config.state_dir)
    checks: dict[str, object] = {
        "state": "ok" if credentials else "missing",
        "capabilities": detect_capabilities(),
        "api": "unreachable",
        "gateway": "unreachable",
    }
    try:
        response = httpx.get(f"{config.api_url}/health", timeout=5.0)
        checks["api"] = "ok" if response.status_code < 400 else f"http_{response.status_code}"
    except httpx.HTTPError:
        pass
    try:
        response = httpx.get(f"{config.gateway_url}/health", timeout=5.0)
        checks["gateway"] = "ok" if response.status_code < 400 else f"http_{response.status_code}"
    except httpx.HTTPError:
        pass
    if credentials and checks["api"] == "ok":
        try:
            response = httpx.post(
                f"{config.api_url}/workers/{credentials.worker_id}/heartbeat",
                headers={"Authorization": f"Bearer {credentials.token}"},
                json={},
                timeout=5.0,
            )
            checks["authentication"] = "ok" if response.status_code < 400 else f"http_{response.status_code}"
        except httpx.HTTPError:
            checks["authentication"] = "unreachable"
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    required_ok = checks["state"] == "ok" and checks["api"] == "ok"
    return 0 if required_ok and checks.get("authentication") == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = WorkerConfig.from_env()
    if args.command == "register":
        return _register(config, args)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "capabilities":
        print(json.dumps(detect_capabilities(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "logs":
        for line in tail_logs(config.state_dir, max(1, args.tail)):
            print(line)
        return 0
    credentials = load_credentials(config.state_dir)
    if credentials is None:
        print("Worker non enregistré. Exécutez agent-company-worker register.", file=sys.stderr)
        return 2
    if not credentials.simulation:
        print(
            "Aucun exécuteur réel sécurisé n'est encore configuré; démarrage refusé.",
            file=sys.stderr,
        )
        return 2
    asyncio.run(run_forever(config, credentials, once=args.once))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
