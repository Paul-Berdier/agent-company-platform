"""Faux runner Playwright déterministe pour les tests du worker.

Ce programme est lancé par ``sys.executable`` exactement comme le ferait la
configuration d'un opérateur : aucun navigateur, aucun réseau, aucun shell. Il
écrit un NDJSON réaliste dans ``ACP_REPORT_FILE`` et, selon le mode demandé, des
fichiers de pièces jointes dans le répertoire de sortie.

Le mode est le premier argument ; les suivants sont propres au mode.

=============  ==================================================================
Mode           Comportement
=============  ==================================================================
``full``       rapport complet couvrant ``passed``, ``failed``, ``timedOut``,
               ``skipped``, ``interrupted`` et une reprise ``flaky`` ; pièces
               jointes réelles (capture, vidéo, trace) et rapport HTML ; sort 1.
``green``      suite entièrement verte avec une capture ; sort 0.
``corrupt``    rapport dont trois lignes sont inexploitables (JSON tronqué,
               texte libre, clé inconnue refusée par ``extra="forbid"``) ; sort 1.
``empty``      crée le NDJSON et n'écrit rien ; sort 0.
``missing``    n'écrit aucun NDJSON ; sort 0.
``escape``     référence une pièce jointe dont le chemin sort du répertoire de
               sortie, et écrit réellement le fichier cible à l'extérieur ; sort 1.
``symlink``    référence une pièce jointe au chemin relatif irréprochable, mais
               qui est un lien symbolique vers un fichier extérieur ; sort 1.
``ghost``      annonce une pièce jointe au chemin relatif valide qui n'existe
               pas sur le disque ; sort 1.
``huge``       écrit une pièce jointe de ``taille`` octets (argument suivant).
``secret``     recopie ``E2E_PASSWORD`` dans un message d'erreur, un extrait de
               code, un titre d'étape et une annotation ; sort 1.
``hang``       écrit son PID et celui d'un petit-fils, puis ne sort jamais.
=============  ==================================================================
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


RUNNER_VERSION = "1.44.2"
STARTED_AT = "2026-09-12T08:00:00Z"
FINISHED_AT = "2026-09-12T08:00:42Z"
CONFIG = {
    "projects": ["chromium", "firefox"],
    "workers": 2,
    "base_url": "http://127.0.0.1:4173",
    "shard": None,
}


def _report_path() -> Path:
    """``ACP_REPORT_FILE`` est le seul canal de sortie structurée du reporter."""

    raw = os.environ.get("ACP_REPORT_FILE")
    if not raw:
        # Comportement du vrai reporter : une ligne sur stderr, jamais un échec.
        print("ACP_REPORT_FILE absent", file=sys.stderr)
        raise SystemExit(0)
    return Path(raw)


def _write(report: Path, lines: list[str]) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(line + "\n")


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _run_begin() -> str:
    return _json(
        {
            "kind": "run_begin",
            "started_at": STARTED_AT,
            "runner_version": RUNNER_VERSION,
            "config": dict(CONFIG),
        }
    )


def _case(
    *,
    test_id: str,
    title: str,
    status: str,
    outcome: str,
    attempt: int = 1,
    duration_ms: int = 120,
    line: int = 12,
    error_message: str = "",
    error_snippet: str = "",
    steps: list[dict] | None = None,
    annotations: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> str:
    return _json(
        {
            "kind": "test_end",
            "test_id": test_id,
            "title": title,
            "suite_path": ["panier.spec.ts", "Panier"],
            "location": {"file": "tests/panier.spec.ts", "line": line, "column": 3},
            "project_name": "chromium",
            "attempt": attempt,
            "expected_status": "passed",
            "status": status,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "error_snippet": error_snippet,
            "steps": steps or [],
            "annotations": annotations or [],
            "attachments": attachments or [],
        }
    )


def _run_end(
    *,
    totals: dict,
    run_status: str,
    exit_code: int,
    report_path: str | None = None,
) -> str:
    payload = {
        "kind": "run_end",
        "finished_at": FINISHED_AT,
        "totals": totals,
        "run_status": run_status,
        "exit_code": exit_code,
    }
    if report_path is not None:
        payload["report_path"] = report_path
    return _json(payload)


def _attachment(name: str, content_type: str, path: str) -> dict:
    return {
        "name": name,
        "content_type": content_type,
        "path": path,
        "sha256": "",
        "size_bytes": 0,
    }


def _materialize(output: Path, relative: str, payload: bytes) -> None:
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _mode_full(report: Path, output: Path) -> int:
    _materialize(output, "attachments/panier-echec.png", b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    _materialize(output, "attachments/panier-echec.webm", b"\x1a\x45\xdf\xa3" + b"v" * 48)
    _materialize(output, "attachments/trace.zip", b"PK\x03\x04" + b"z" * 32)
    _materialize(output, "playwright-report/index.html", b"<html>rapport</html>")
    lines = [
        _run_begin(),
        _case(
            test_id="panier-ajoute",
            title="ajoute un article",
            status="passed",
            outcome="expected",
            steps=[
                {"title": "goto /panier", "category": "pw:api", "duration_ms": 40},
                {"title": "expect visible", "category": "expect", "duration_ms": 12},
            ],
            attachments=[_attachment("trace", "application/zip", "attachments/trace.zip")],
        ),
        _case(
            test_id="panier-vide",
            title="vide le panier",
            status="failed",
            outcome="unexpected",
            line=31,
            duration_ms=900,
            error_message="expect(received).toHaveText(expected)\nAttendu: 0 article",
            error_snippet="  30 |   await page.click('#vider');\n> 31 |   await expect(total).toHaveText('0');",
            steps=[
                {
                    "title": "click #vider",
                    "category": "pw:api",
                    "duration_ms": 30,
                    "error": True,
                }
            ],
            annotations=[{"type": "issue", "description": "PANIER-42"}],
            attachments=[
                _attachment("screenshot", "image/png", "attachments/panier-echec.png"),
                _attachment("video", "video/webm", "attachments/panier-echec.webm"),
            ],
        ),
        _case(
            test_id="panier-paiement",
            title="expire au paiement",
            status="timedOut",
            outcome="unexpected",
            line=48,
            duration_ms=30000,
            error_message="Test timeout of 30000ms exceeded.",
        ),
        _case(
            test_id="panier-hors-ci",
            title="ignore hors CI",
            status="skipped",
            outcome="skipped",
            line=60,
            duration_ms=0,
            annotations=[{"type": "skip", "description": "hors CI"}],
        ),
        _case(
            test_id="panier-interrompu",
            title="interrompu par l'arrêt de la suite",
            status="interrupted",
            outcome="unexpected",
            line=72,
            duration_ms=15,
        ),
        _case(
            test_id="panier-instable",
            title="instable au premier essai",
            status="passed",
            outcome="flaky",
            attempt=2,
            line=85,
            duration_ms=210,
        ),
        _run_end(
            totals={
                "expected": 2,
                "unexpected": 3,
                "flaky": 1,
                "skipped": 1,
                "interrupted": 1,
                "timedOut": 1,
            },
            run_status="failed",
            exit_code=1,
            report_path="playwright-report/index.html",
        ),
    ]
    _write(report, lines)
    return 1


def _mode_green(report: Path, output: Path) -> int:
    _materialize(output, "attachments/accueil.png", b"\x89PNG\r\n\x1a\n" + b"g" * 16)
    lines = [
        _run_begin(),
        _case(
            test_id="accueil-affiche",
            title="affiche la page d'accueil",
            status="passed",
            outcome="expected",
            attachments=[
                _attachment("screenshot", "image/png", "attachments/accueil.png")
            ],
        ),
        _case(
            test_id="accueil-navigue",
            title="navigue vers le catalogue",
            status="passed",
            outcome="expected",
            line=24,
        ),
        _run_end(
            totals={
                "expected": 2,
                "unexpected": 0,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="completed",
            exit_code=0,
        ),
    ]
    _write(report, lines)
    return 0


def _mode_corrupt(report: Path, output: Path) -> int:
    lines = [
        _run_begin(),
        _case(
            test_id="corrompu-avant",
            title="cas lisible avant la corruption",
            status="passed",
            outcome="expected",
        ),
        '{"kind": "test_end", "test_id": "tronque", "status": "pas',
        "ceci n'est pas du JSON",
        _json(
            {
                "kind": "test_end",
                "test_id": "cle-inconnue",
                "title": "cas avec une clé hors contrat",
                "status": "passed",
                "outcome": "expected",
                "champ_inconnu": True,
            }
        ),
        _case(
            test_id="corrompu-apres",
            title="cas lisible après la corruption",
            status="failed",
            outcome="unexpected",
            line=44,
            error_message="assertion réelle en échec",
        ),
        _run_end(
            totals={
                "expected": 1,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="failed",
            exit_code=1,
        ),
    ]
    _write(report, lines)
    return 1


def _mode_empty(report: Path, output: Path) -> int:
    _write(report, [])
    return 0


def _mode_missing(report: Path, output: Path) -> int:
    return 0


def _mode_escape(report: Path, output: Path) -> int:
    evade = output.parent / "evasion.txt"
    evade.write_bytes(b"contenu hors du repertoire de sortie")
    lines = [
        _run_begin(),
        _case(
            test_id="evasion",
            title="pièce jointe hors du répertoire de sortie",
            status="failed",
            outcome="unexpected",
            error_message="capture hors périmètre",
            attachments=[
                _attachment("evasion", "text/plain", "../evasion.txt"),
            ],
        ),
        _case(
            test_id="evasion-voisin",
            title="cas lisible malgré la pièce jointe refusée",
            status="passed",
            outcome="expected",
            line=20,
        ),
        _run_end(
            totals={
                "expected": 1,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="failed",
            exit_code=1,
        ),
    ]
    _write(report, lines)
    return 1


def _mode_symlink(report: Path, output: Path) -> int:
    """Chemin relatif impeccable, mais lien symbolique vers l'extérieur."""

    cible = output.parent / "cible-externe.txt"
    cible.write_bytes(b"contenu atteint par un lien")
    lien = output / "attachments" / "lien.txt"
    lien.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(cible, lien)
    lines = [
        _run_begin(),
        _case(
            test_id="lien",
            title="pièce jointe atteinte par un lien symbolique",
            status="failed",
            outcome="unexpected",
            error_message="capture derrière un lien",
            attachments=[_attachment("lien", "text/plain", "attachments/lien.txt")],
        ),
        _run_end(
            totals={
                "expected": 0,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="failed",
            exit_code=1,
        ),
    ]
    _write(report, lines)
    return 1


def _mode_ghost(report: Path, output: Path) -> int:
    """Pièce jointe annoncée puis jamais écrite (processus tué, disque plein…)."""

    lines = [
        _run_begin(),
        _case(
            test_id="fantome",
            title="annonce une pièce jointe absente",
            status="failed",
            outcome="unexpected",
            error_message="capture jamais écrite",
            attachments=[
                _attachment("screenshot", "image/png", "attachments/fantome.png")
            ],
        ),
        _run_end(
            totals={
                "expected": 0,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="failed",
            exit_code=1,
        ),
    ]
    _write(report, lines)
    return 1


def _mode_huge(report: Path, output: Path, size: int) -> int:
    _materialize(output, "attachments/enorme.bin", b"h" * size)
    _materialize(output, "attachments/petite.png", b"\x89PNG\r\n\x1a\n")
    lines = [
        _run_begin(),
        _case(
            test_id="volumineux",
            title="produit une pièce jointe trop volumineuse",
            status="failed",
            outcome="unexpected",
            error_message="échec avec trace volumineuse",
            attachments=[
                _attachment("trace", "application/zip", "attachments/enorme.bin"),
                _attachment("screenshot", "image/png", "attachments/petite.png"),
            ],
        ),
        _run_end(
            totals={
                "expected": 0,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="failed",
            exit_code=1,
        ),
    ]
    _write(report, lines)
    return 1


def _mode_secret(report: Path, output: Path) -> int:
    secret = os.environ.get("E2E_PASSWORD", "")
    lines = [
        _run_begin(),
        _case(
            test_id="fuite",
            title="imprime une variable d'environnement",
            status="failed",
            outcome="unexpected",
            error_message=f"connexion refusée avec le mot de passe {secret}",
            error_snippet=f"  12 |   await page.fill('#password', '{secret}');",
            steps=[
                {
                    "title": f"fill #password {secret}",
                    "category": "pw:api",
                    "duration_ms": 5,
                    "error": True,
                }
            ],
            annotations=[{"type": "debug", "description": f"env={secret}"}],
            # Pièce jointe jamais écrite : son refus est signalé dans la preuve,
            # donc son chemin doit lui aussi être expurgé.
            attachments=[
                _attachment(
                    f"capture-{secret}",
                    "image/png",
                    f"attachments/{secret}.png",
                )
            ],
        ),
        _run_end(
            totals={
                "expected": 0,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            run_status="failed",
            exit_code=1,
        ),
    ]
    _write(report, lines)
    return 1


def _mode_hang(report: Path, output: Path) -> int:
    """Lance un petit-fils qui survivrait au parent, puis ne sort jamais."""

    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            "import time\nwhile True:\n    time.sleep(1)\n",
        ]
    )
    (output / "pids.json").write_text(
        json.dumps({"parent": os.getpid(), "child": child.pid}),
        encoding="utf-8",
    )
    while True:
        time.sleep(0.5)


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "full"
    report = _report_path()
    output = report.parent
    output.mkdir(parents=True, exist_ok=True)
    if mode == "full":
        return _mode_full(report, output)
    if mode == "green":
        return _mode_green(report, output)
    if mode == "corrupt":
        return _mode_corrupt(report, output)
    if mode == "empty":
        return _mode_empty(report, output)
    if mode == "missing":
        return _mode_missing(report, output)
    if mode == "escape":
        return _mode_escape(report, output)
    if mode == "symlink":
        return _mode_symlink(report, output)
    if mode == "ghost":
        return _mode_ghost(report, output)
    if mode == "huge":
        return _mode_huge(report, output, int(argv[1]))
    if mode == "secret":
        return _mode_secret(report, output)
    if mode == "hang":
        return _mode_hang(report, output)
    print(f"mode inconnu: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
