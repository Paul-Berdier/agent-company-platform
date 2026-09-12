"""Vérification de bout en bout du parcours MCP, contre des services réellement lancés.

Ce script n'est pas un test unitaire et ne tourne pas en intégration continue : il démarre
l'API métier dans un processus séparé avec une base isolée et une clé de coffre éphémère,
lance un **vrai** serveur MCP Streamable HTTP sur le bouclage, puis rejoue le scénario
d'acceptation « Ajout, test, activation et révocation d'un MCP » : déclarer, refuser un
secret en clair, découvrir, rattacher à un projet avec un sous-ensemble d'outils, activer,
vérifier l'isolation entre deux projets, exporter sans valeur de secret, révoquer.

Il vérifie aussi, côté serveur MCP, que la valeur du secret a réellement été injectée : la
sonde n'est donc pas simulée. Aucune donnée réelle, aucun appel sortant vers Internet,
aucune dépense.

La politique de sortie n'est pas désactivée : l'hôte de bouclage est inscrit dans
``ACP_OUTBOUND_PRIVATE_ALLOWLIST``, ce qui exerce le chemin d'allowlist auditée.

Usage, depuis la racine du dépôt, avec l'environnement installé par ``scripts/setup`` :

```
.venv/Scripts/python.exe scripts/verify_mcp_journey.py      # Windows
.venv/bin/python scripts/verify_mcp_journey.py              # Linux/macOS
```

Sortie : une ligne par étape, puis un VERDICT. Code de retour 0 si toutes les étapes
passent, 1 sinon.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

# Le script vit dans ``scripts/`` : la racine du dépôt est son parent. L'API est lancée
# avec l'interpréteur courant, donc celui de l'environnement qui exécute ce script.
WORKTREE = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable).resolve()

API_PORT = 8123
MCP_PORT = 8124
API = f"http://127.0.0.1:{API_PORT}"

steps: list[tuple[str, bool, str]] = []


def step(label: str, ok: bool, detail: str = "") -> None:
    steps.append((label, ok, detail))
    mark = "OK  " if ok else "ECHEC"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""), flush=True)


# --- serveur MCP local réel (Streamable HTTP, spec 2025-06-18) ----------------

TOOLS = [
    {
        "name": "search_docs",
        "description": "Recherche dans la documentation interne.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "delete_everything",
        "description": "Outil dangereux qui ne doit jamais être autorisé implicitement.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

received_headers: list[dict[str, str]] = []


class McpHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        received_headers.append({k.lower(): v for k, v in self.headers.items()})
        method = body.get("method")
        if method == "initialize":
            payload = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "serveur-de-verification", "version": "1.0.0"},
                },
            }
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Mcp-Session-Id", "session-verification-1")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "tools/list":
            payload = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": TOOLS}}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(400)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def start_mcp_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", MCP_PORT), McpHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --- API métier ---------------------------------------------------------------

def start_api(verify_dir: Path) -> subprocess.Popen:
    env = dict(os.environ)
    key = subprocess.run(
        [str(PYTHON), "-c", "from acp_api.secrets_vault import generate_key; print(generate_key())"],
        cwd=WORKTREE, capture_output=True, text=True, check=True,
    ).stdout.strip()
    env.update({
        "ACP_DATABASE_URL": f"sqlite:///{(verify_dir / 'verify.db').as_posix()}",
        "ACP_BOOTSTRAP_TOKEN": secrets.token_urlsafe(32),
        "ACP_SESSION_COOKIE_SECURE": "0",
        "ACP_SECRETS_KEYS": key,
        # L'hôte de bouclage est explicitement autorisé : c'est le chemin d'allowlist
        # auditée, pas une désactivation de la politique.
        "ACP_OUTBOUND_PRIVATE_ALLOWLIST": "127.0.0.1",
        "ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP": "1",
        "ACP_SKILLS_STORAGE_DIR": str(verify_dir / "skills"),
    })
    process = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "acp_api.main:app", "--port", str(API_PORT), "--host", "127.0.0.1"],
        cwd=WORKTREE, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    process._bootstrap_token = env["ACP_BOOTSTRAP_TOKEN"]  # type: ignore[attr-defined]
    return process


def wait_for_api(process: subprocess.Popen) -> bool:
    for _ in range(120):
        if process.poll() is not None:
            return False
        try:
            if httpx.get(f"{API}/health", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.5)
    return False


def main() -> int:
    verify_dir = Path(tempfile.mkdtemp(prefix="acp-e2e-"))
    mcp_server = start_mcp_server()
    api = start_api(verify_dir)
    try:
        if not wait_for_api(api):
            output = api.stdout.read() if api.stdout else ""
            step("API démarrée", False, output[-2000:])
            return 1
        step("API démarrée", True, API)

        client = httpx.Client(base_url=API, timeout=30.0, trust_env=False, follow_redirects=False)

        # 1. Bootstrap du propriétaire
        response = client.post(
            "/auth/bootstrap",
            headers={"X-ACP-Bootstrap-Token": api._bootstrap_token},  # type: ignore[attr-defined]
            json={"login": "verif", "display_name": "Vérification", "password": "correct horse battery staple"},
        )
        ok = response.status_code == 201
        step("Bootstrap du propriétaire", ok, f"HTTP {response.status_code}")
        if not ok:
            return 1
        csrf = response.json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf

        # 2. Deux projets, pour prouver l'isolation
        org = client.post("/organizations", json={"name": "Org vérif"}).json()
        workspace = client.post("/workspaces", json={"organization_id": org["id"], "name": "WS vérif"}).json()
        project_a = client.post("/projects", json={"workspace_id": workspace["id"], "name": "Projet A"}).json()
        project_b = client.post("/projects", json={"workspace_id": workspace["id"], "name": "Projet B"}).json()
        step("Deux projets créés", True, f"A={project_a['id'][:8]} B={project_b['id'][:8]}")

        # 3. Un secret (valeur jamais relue)
        response = client.post(
            "/secrets",
            json={"name": "VERIF_MCP_TOKEN", "value": "valeur-de-coffre-ultra-secrete", "scope_type": "platform",
                  "description": "Jeton de vérification"},
        )
        ok = response.status_code == 201
        step("Secret créé", ok, f"HTTP {response.status_code}")
        if not ok:
            print(response.text)
            return 1
        secret_id = response.json()["id"]
        leaked = "valeur-de-coffre-ultra-secrete" in response.text
        step("La réponse de création ne contient pas la valeur", not leaked)

        listing = client.get("/secrets").text
        step("La liste des secrets ne contient pas la valeur",
             "valeur-de-coffre-ultra-secrete" not in listing)

        # 4. Serveur MCP HTTP référençant le secret en en-tête
        response = client.post(
            "/mcp/servers",
            json={
                "name": "serveur-verification",
                "display_name": "Serveur de vérification",
                "description": "Serveur MCP local lancé par le script de vérification",
                "source_kind": "manual",
                "config": {
                    "transport": "http",
                    "http": {
                        "url": f"http://127.0.0.1:{MCP_PORT}/mcp",
                        "headers": {"X-Client": "agent-company-platform"},
                        "header_secrets": {"Authorization": {"secret_id": secret_id}},
                        "timeout_seconds": 15,
                    },
                },
            },
        )
        ok = response.status_code == 201
        step("Serveur MCP ajouté (brouillon)", ok, f"HTTP {response.status_code}")
        if not ok:
            print(response.text)
            return 1
        server = response.json()
        server_id = server["id"]
        step("La configuration renvoyée ne contient pas la valeur du secret",
             "valeur-de-coffre-ultra-secrete" not in response.text)

        # 5. Refus d'un secret en clair
        response = client.post(
            "/mcp/servers",
            json={
                "name": "serveur-refuse",
                "display_name": "Refusé",
                "config": {
                    "transport": "http",
                    "http": {"url": "https://exemple.test/mcp",
                             "headers": {"Authorization": "Bearer valeur-en-clair"}},
                },
            },
        )
        step("Un secret en clair dans un en-tête est refusé", response.status_code == 422,
             f"HTTP {response.status_code}")

        # 6. Activation refusée avant découverte
        response = client.post(f"/mcp/servers/{server_id}/activate")
        step("Activation refusée sans découverte à jour", response.status_code == 409,
             f"HTTP {response.status_code}")

        # 7. Sonde réelle contre le serveur MCP local
        response = client.post(f"/mcp/servers/{server_id}/probe")
        ok = response.status_code in (200, 201)
        probe = response.json() if ok else {}
        step("Sonde HTTP exécutée", ok and probe.get("status") == "succeeded",
             f"HTTP {response.status_code} statut={probe.get('status')} erreur={probe.get('error')}")
        if probe.get("status") != "succeeded":
            print(json.dumps(probe, ensure_ascii=False, indent=2)[:2000])
            return 1

        tools = [tool["name"] for tool in probe.get("result", {}).get("tools", [])]
        step("Outils réellement découverts", set(tools) == {"search_docs", "delete_everything"}, str(tools))

        sent = received_headers[0] if received_headers else {}
        step("Le secret a bien été injecté vers le serveur MCP",
             sent.get("authorization") == "valeur-de-coffre-ultra-secrete",
             "en-tête Authorization transmis")

        # 8. Rattachement au projet A avec un sous-ensemble d'outils
        response = client.post(f"/mcp/servers/{server_id}/activate")
        step("Activation après découverte", response.status_code == 200, f"HTTP {response.status_code}")

        response = client.post(
            f"/mcp/servers/{server_id}/bindings",
            json={"project_id": project_a["id"], "allowed_tools": ["search_docs"]},
        )
        ok = response.status_code == 201
        step("Rattachement au projet A limité à un outil", ok, f"HTTP {response.status_code}")
        if not ok:
            print(response.text)

        response = client.post(
            f"/mcp/servers/{server_id}/bindings",
            json={"project_id": project_b["id"], "allowed_tools": ["outil_inconnu"]},
        )
        step("Un outil non découvert est refusé", response.status_code == 422, f"HTTP {response.status_code}")

        # 9. Isolation entre projets
        ext_a = client.get(f"/projects/{project_a['id']}/extensions").json()
        ext_b = client.get(f"/projects/{project_b['id']}/extensions").json()
        names_a = [item["name"] for item in ext_a.get("mcp", [])]
        names_b = [item["name"] for item in ext_b.get("mcp", [])]
        step("Le projet A voit le serveur", names_a == ["serveur-verification"], str(names_a))
        step("Le projet B ne le voit pas", names_b == [], str(names_b))

        # 10. Export sans valeur de secret
        response = client.get("/mcp/export", params={"format": "hermes"})
        export = response.json() if response.status_code == 200 else {}
        content = export.get("content", "")
        step("Export Hermes produit", response.status_code == 200, f"HTTP {response.status_code}")
        step("L'export ne contient pas la valeur du secret",
             "valeur-de-coffre-ultra-secrete" not in content)
        step("L'export utilise une référence de secret", "ACP_SECRET" in content,
             content.strip().splitlines()[0] if content else "")

        # 11. Révocation
        response = client.post(f"/mcp/servers/{server_id}/revoke", json={"reason": "Fin de la vérification"})
        step("Révocation", response.status_code == 200, f"HTTP {response.status_code}")
        ext_a = client.get(f"/projects/{project_a['id']}/extensions").json()
        step("Le projet A ne voit plus le serveur après révocation",
             [item["name"] for item in ext_a.get("mcp", [])] == [])

        detail = client.get(f"/mcp/servers/{server_id}")
        step("L'historique du serveur reste consultable", detail.status_code == 200,
             f"statut={detail.json().get('status') if detail.status_code == 200 else ''}")

        failures = [label for label, ok, _ in steps if not ok]
        print()
        print(f"VERDICT : {len(steps) - len(failures)}/{len(steps)} étapes réussies")
        if failures:
            print("Étapes en échec : " + ", ".join(failures))
        return 1 if failures else 0
    finally:
        mcp_server.shutdown()
        api.terminate()
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()


if __name__ == "__main__":
    raise SystemExit(main())
