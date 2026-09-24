"""Ligne d'état Claude Code du titulaire : relevé des limites réelles de son abonnement.

Claude Code lance la commande ``statusLine`` de ses réglages avec, sur l'entrée
standard, le JSON de la session. Pour les abonnés Pro et Max, et après la première
réponse de l'API dans la session, ce JSON contient ``rate_limits.five_hour`` et
``rate_limits.seven_day`` (``used_percentage`` de 0 à 100, ``resets_at`` en secondes
Unix). Ce module :

- recopie ces deux fenêtres, et elles seules, dans le fichier que lit le worker
  (``~/.acp/quotas/claude-code.json``, ou le chemin absolu de
  ``ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT``) : ni identifiant de session, ni chemin, ni
  modèle, ni coût, ni ``spend_limit`` (limite de dépense d'une passerelle, qui n'est
  pas un quota d'abonnement) ;
- écrit dans un fichier temporaire du même dossier puis le substitue par
  ``os.replace`` : le worker ne lit jamais un fichier à moitié écrit, même quand
  Claude Code interrompt la commande pour une mise à jour plus récente ;
- n'écrit rien tant que Claude Code n'a transmis aucune fenêtre : le dernier relevé
  garde sa date et devient « Périmé » dans la plateforme ;
- recopie une valeur illisible ou hors de 0–100 comme inconnue (``null``), jamais
  comme une estimation ;
- conserve la ligne d'état existante du titulaire : la commande donnée après ``--``
  reçoit la même entrée et son affichage est repris tel quel ; sans elle, une ligne
  courte (modèle, dossier, fenêtres) est affichée ;
- ne lève jamais et sort toujours avec le code 0 : une ligne d'état en erreur gênerait
  toute la session ; un échec se lit dans la ligne affichée.

Réglage (``~/.claude/settings.json``, chemins en barres obliques sous Windows) ::

    "statusLine": {
      "type": "command",
      "command": "C:/chemin/du/worker/.venv/Scripts/python.exe -m acp_worker.claude_statusline"
    }

Avec une ligne d'état existante, la placer après ``--`` :
``… -m acp_worker.claude_statusline -- powershell -NoProfile -File C:/…/statusline.ps1``.

Bibliothèque standard seulement : la commande tourne à chaque mise à jour de la
ligne d'état et doit démarrer vite.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_ENV = "ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT"
SNAPSHOT_SOURCE = "claude-code-statusline"
SNAPSHOT_WINDOW_MINUTES = {"five_hour": 300, "seven_day": 10_080}
"""Fenêtres d'abonnement recopiées, avec la durée que leur nom même désigne."""
WINDOW_LABELS = {"five_hour": "5 h", "seven_day": "7 j"}
MAX_INPUT_BYTES = 1024 * 1024
MAX_CHAINED_OUTPUT_BYTES = 64 * 1024
CHAINED_TIMEOUT_SECONDS = 10.0
STALE_TEMPORARY_SECONDS = 3600
REPLACE_ATTEMPTS = 3
REPLACE_RETRY_SECONDS = 0.05
"""Sous Windows, un lecteur qui tient le fichier ouvert fait échouer la substitution :
quelques essais rapprochés, puis la mise à jour suivante réessaiera."""

UNKNOWN = "Inconnu"
NOT_SENT = "quotas d'abonnement non transmis par Claude Code"
NOT_RECORDED = "relevé non enregistré"
CHAINED_FAILED = "ligne d'état existante en échec"
UNREADABLE_INPUT = "entrée de Claude Code illisible"
BAD_ARGUMENT = "argument refusé : « -- commande existante » attendu"


def default_snapshot_path() -> Path:
    return Path.home() / ".acp" / "quotas" / "claude-code.json"


def snapshot_path(environ: Mapping[str, str] | None = None) -> Path | None:
    """Fichier du relevé ; ``None`` quand le réglage n'est pas un chemin absolu."""

    value = (os.environ if environ is None else environ).get(SNAPSHOT_ENV)
    if value is None:
        return default_snapshot_path()
    if not value or value != value.strip() or not Path(value).is_absolute():
        return None
    return Path(value)


def _percentage(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return value


def _epoch(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    try:
        datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return value


def snapshot_from_session(session: Any, *, now: datetime) -> dict[str, Any] | None:
    """Relevé à écrire, ou ``None`` quand Claude Code n'a transmis aucune fenêtre."""

    limits = session.get("rate_limits") if isinstance(session, dict) else None
    if not isinstance(limits, dict):
        return None
    windows = {}
    for key in SNAPSHOT_WINDOW_MINUTES:
        window = limits.get(key)
        if isinstance(window, dict):
            windows[key] = {
                "used_percentage": _percentage(window.get("used_percentage")),
                "resets_at": _epoch(window.get("resets_at")),
            }
    if not windows:
        return None
    return {
        "source": SNAPSHOT_SOURCE,
        "observed_at": now.astimezone(UTC).isoformat(timespec="seconds"),
        "windows": windows,
    }


def _temporary_prefix(target: Path) -> str:
    return f".{target.name}."


def _remove_stale_temporaries(target: Path) -> None:
    """Retire les fichiers temporaires d'exécutions interrompues, anciens d'une heure."""

    limit = time.time() - STALE_TEMPORARY_SECONDS
    for candidate in target.parent.glob(f"{_temporary_prefix(target)}*.tmp"):
        with suppress(OSError):
            if candidate.is_file() and candidate.stat().st_mtime < limit:
                candidate.unlink()


def write_snapshot(target: Path, snapshot: dict[str, Any]) -> bool:
    """Écrit le relevé par substitution atomique ; ``False`` si rien n'a été écrit."""

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_temporaries(target)
        handle, temporary = tempfile.mkstemp(
            prefix=_temporary_prefix(target), suffix=".tmp", dir=target.parent
        )
    except OSError:
        return False
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(temporary, target)
                return True
            except PermissionError:
                if attempt + 1 == REPLACE_ATTEMPTS:
                    raise
                time.sleep(REPLACE_RETRY_SECONDS)
    except OSError:
        pass
    with suppress(OSError):
        os.unlink(temporary)
    return False


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------


def _printable(value: Any, limit: int = 80) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(character for character in value if character.isprintable()).strip()
    return text[:limit] or None


def _percent_text(value: int | float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _reset_text(epoch: int | float) -> str:
    moment = datetime.fromtimestamp(epoch, UTC).astimezone()
    now = datetime.now().astimezone()
    if moment.date() == now.date():
        return moment.strftime("%H:%M")
    return moment.strftime("%d/%m %H:%M")


def render(session: Any, snapshot: dict[str, Any] | None, *, notes: Sequence[str] = ()) -> str:
    """Ligne courte : modèle, dossier, part utilisée et remise à zéro de chaque fenêtre."""

    parts = []
    if isinstance(session, dict):
        model = session.get("model")
        name = _printable(model.get("display_name")) if isinstance(model, dict) else None
        if name:
            parts.append(name)
        workspace = session.get("workspace")
        directory = workspace.get("current_dir") if isinstance(workspace, dict) else None
        directory = _printable(directory or session.get("cwd"), 400)
        if directory:
            parts.append(os.path.basename(directory.replace("\\", "/").rstrip("/")) or directory)
    if snapshot is None:
        parts.append(NOT_SENT)
    else:
        for key, label in WINDOW_LABELS.items():
            window = snapshot["windows"].get(key)
            if window is None:
                parts.append(f"{label} : {UNKNOWN}")
                continue
            used = window["used_percentage"]
            text = f"{label} : " + (UNKNOWN if used is None else f"{_percent_text(used)} % utilisés")
            if window["resets_at"] is not None:
                with suppress(OverflowError, OSError, ValueError):
                    text += f", remise {_reset_text(window['resets_at'])}"
            parts.append(text)
    parts.extend(notes)
    return " | ".join(parts)


def run_chained(argv: Sequence[str], data: bytes) -> str | None:
    """Ligne d'état existante, lancée sans shell ; ``None`` si elle n'a rien affiché."""

    executable = shutil.which(argv[0]) or argv[0]
    try:
        completed = subprocess.run(
            [executable, *argv[1:]],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=CHAINED_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    output = completed.stdout[:MAX_CHAINED_OUTPUT_BYTES].decode("utf-8", errors="replace")
    if completed.returncode != 0 and not output.strip():
        return None
    return output


def _read_session(data: bytes) -> tuple[Any, bool]:
    if len(data) > MAX_INPUT_BYTES:
        return None, False
    try:
        session = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None, False
    return session, isinstance(session, dict)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    chained = arguments[1:] if arguments[:1] == ["--"] else []
    notes: list[str] = []
    if arguments and not chained:
        notes.append(BAD_ARGUMENT)
    try:
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError):
        data = b""
    session, readable = _read_session(data)
    if not readable:
        notes.append(UNREADABLE_INPUT)
    snapshot = None
    try:
        snapshot = snapshot_from_session(session, now=datetime.now(UTC))
        if snapshot is not None:
            target = snapshot_path()
            if target is None:
                notes.append(f"{SNAPSHOT_ENV} doit être un chemin absolu")
            if target is None or not write_snapshot(target, snapshot):
                notes.append(NOT_RECORDED)
    except Exception:  # noqa: BLE001 - la ligne d'état ne tombe jamais
        notes.append(NOT_RECORDED)
    line = run_chained(chained, data) if chained else None
    if line is None:
        if chained:
            notes.append(CHAINED_FAILED)
        line = render(session, snapshot, notes=notes)
    elif notes:
        # Affichage existant conservé ; un relevé non enregistré reste signalé.
        line = line.rstrip("\r\n") + " | " + " | ".join(notes)
    with suppress(OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
