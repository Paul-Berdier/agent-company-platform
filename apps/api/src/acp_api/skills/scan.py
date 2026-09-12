"""Contrôle automatique **indicatif** du contenu d'un skill (jamais une certification).

Les heuristiques ci-dessous produisent des constats (``SkillScanFinding``) destinés à la
relecture humaine avant approbation. Elles ne bloquent rien par elles-mêmes : elles
alimentent l'exigence d'approbation (`danger` ⇒ approbation requise) et l'affichage.

Un constat ``advisory_only`` de niveau ``info`` est toujours ajouté pour rappeler que le
contrôle est indicatif et non certifiant.
"""

from __future__ import annotations

import json
import posixpath
import re
from typing import Any, Iterable, Sequence

from acp_contracts import SkillScanFinding

# Fichiers considérés comme exécutables : sous « scripts/ » ou avec une extension de script.
SCRIPT_DIRECTORY = "scripts/"
SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".ps1", ".psm1", ".py", ".js", ".mjs", ".cjs", ".cmd", ".bat")

# Caractères invisibles ou de contrôle bidirectionnel : ils masquent le contenu réel.
HIDDEN_UNICODE = re.compile("[­​‌‍⁠﻿‪-‮⁦-⁩]")

URL_PATTERN = re.compile(r"https?://[^\s'\"<>)\]}\\`]+")

PIPE_TO_SHELL = re.compile(
    r"\b(?:curl|wget|iwr|invoke-webrequest|invoke-restmethod)\b[^\n|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|dash|ksh|pwsh|powershell)\b",
    re.IGNORECASE,
)
BASE64_DECODE = re.compile(r"\bbase64\b[^\n]{0,80}?(?:-d|-D|--decode)\b|\b(?:frombase64string|b64decode)\s*\(", re.IGNORECASE)
BASE64_EXECUTION = re.compile(
    r"\|\s*(?:sudo\s+)?(?:sh|bash|zsh|dash|python[0-9.]*|node|pwsh|powershell)\b|\b(?:eval|iex|invoke-expression|exec)\b",
    re.IGNORECASE,
)
EVAL_USAGE = re.compile(r"(?<![\w.])(?:eval|iex|invoke-expression)\s*[\"'(\$]", re.IGNORECASE)

SENSITIVE_PATHS = (
    (re.compile(r"~[/\\]\.ssh\b"), "~/.ssh"),
    (re.compile(r"\bid_rsa\b"), "id_rsa"),
    (re.compile(r"~[/\\]\.aws\b"), "~/.aws"),
    (re.compile(r"~[/\\]\.hermes[/\\]\.env\b"), "~/.hermes/.env"),
    (re.compile(r"(?<![\w.-])\.env(?![\w-])"), ".env"),
)

INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "disregard all previous instructions",
    "ignore les instructions précédentes",
    "ignore toutes les instructions précédentes",
    "oublie les instructions précédentes",
    "system prompt",
    "prompt système",
)

ADVISORY_MESSAGE = (
    "Contrôle automatique indicatif, non certifiant : relisez le contenu importé "
    "avant d'approuver puis d'activer ce skill."
)


def is_script(path: str) -> bool:
    """Vrai si le chemin désigne un fichier exécutable (dossier « scripts/ » ou extension connue)."""

    normalized = path.replace("\\", "/")
    if normalized.startswith(SCRIPT_DIRECTORY):
        return True
    return normalized.lower().endswith(SCRIPT_SUFFIXES)


def script_paths(files: Sequence[tuple[str, bytes]]) -> list[str]:
    """Chemins exécutables du skill, triés."""

    return sorted({path for path, _ in files if is_script(path)})


def decode_text(data: bytes) -> str | None:
    """Texte UTF-8 du fichier, ou ``None`` si le contenu est binaire (octet nul ou décodage impossible)."""

    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def collect_network_indicators(files: Sequence[tuple[str, bytes]]) -> list[str]:
    """URL http(s) trouvées dans les fichiers exécutables (indice de sortie réseau)."""

    indicators: set[str] = set()
    for path, data in files:
        if not is_script(path):
            continue
        text = decode_text(data)
        if text is None:
            continue
        for match in URL_PATTERN.finditer(text):
            indicators.add(match.group(0).rstrip(".,;:"))
    return sorted(indicators)


def _plugin_manifest(files: Sequence[tuple[str, bytes]]) -> bool:
    """Vrai si un manifeste de plugin natif est présent à la racine."""

    for path, data in files:
        if path == "plugin.json":
            return True
        if path == "manifest.json":
            text = decode_text(data)
            if text is None:
                continue
            try:
                manifest = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(manifest, dict) and ("entry" in manifest or "main" in manifest):
                return True
    return False


def _finding(level: str, code: str, message: str, path: str | None = None) -> SkillScanFinding:
    return SkillScanFinding(level=level, code=code, message=message, path=path)


def _scan_text(path: str, text: str) -> list[SkillScanFinding]:
    """Heuristiques appliquées au texte d'un fichier ; un constat par motif et par fichier."""

    findings: list[SkillScanFinding] = []
    lowered = text.lower()

    if PIPE_TO_SHELL.search(text):
        findings.append(
            _finding(
                "danger",
                "pipe_to_shell",
                "Téléchargement redirigé vers un interpréteur (« curl … | sh ») : "
                "le code exécuté n'est pas vérifiable.",
                path,
            )
        )
    for line in text.splitlines():
        if BASE64_DECODE.search(line) and BASE64_EXECUTION.search(line):
            findings.append(
                _finding(
                    "danger",
                    "base64_execution",
                    "Contenu décodé depuis base64 puis exécuté : charge utile masquée.",
                    path,
                )
            )
            break
    if EVAL_USAGE.search(text):
        findings.append(
            _finding(
                "danger",
                "eval_usage",
                "Évaluation dynamique de code (« eval ») : le contenu exécuté dépend de l'environnement.",
                path,
            )
        )
    for pattern, label in SENSITIVE_PATHS:
        if pattern.search(text):
            findings.append(
                _finding(
                    "danger",
                    "sensitive_path",
                    f"Accès à un emplacement sensible (« {label} ») : identifiants ou secrets locaux.",
                    path,
                )
            )
    if HIDDEN_UNICODE.search(text):
        findings.append(
            _finding(
                "danger",
                "hidden_unicode",
                "Caractères Unicode invisibles ou bidirectionnels : le texte affiché peut "
                "différer du texte réel.",
                path,
            )
        )
    for phrase in INJECTION_PHRASES:
        if phrase in lowered:
            findings.append(
                _finding(
                    "danger",
                    "prompt_injection",
                    f"Formulation d'injection d'instructions détectée (« {phrase} ») : "
                    "contenu traité comme donnée, jamais comme consigne.",
                    path,
                )
            )
            break
    if is_script(path):
        for match in URL_PATTERN.finditer(text):
            findings.append(
                _finding(
                    "caution",
                    "network_indicator",
                    f"Sortie réseau possible depuis un script : {match.group(0).rstrip('.,;:')}",
                    path,
                )
            )
            break
    return findings


def scan_files(
    files: Sequence[tuple[str, bytes]],
    *,
    frontmatter: dict[str, Any] | None = None,
    license: str | None = None,
    kind: str | None = None,
) -> list[SkillScanFinding]:
    """Analyse indicative de l'ensemble des fichiers d'une révision.

    ``frontmatter``, ``license`` et ``kind`` sont facultatifs : ils n'ajoutent que les
    constats de niveau ``info``/``caution`` sur les métadonnées et l'étiquetage.
    """

    findings: list[SkillScanFinding] = []
    for path, data in sorted(files):
        text = decode_text(data)
        if text is None:
            findings.append(
                _finding(
                    "caution",
                    "binary_file",
                    "Fichier binaire : contenu non analysé et jamais rendu comme texte.",
                    path,
                )
            )
            continue
        findings.extend(_scan_text(path, text))

    for path in script_paths(files):
        findings.append(
            _finding(
                "caution",
                "executable_script",
                "Fichier exécutable : son contenu doit être relu avant activation.",
                path,
            )
        )

    metadata = frontmatter or {}
    variables = _environment_variable_names(metadata)
    if variables:
        findings.append(
            _finding(
                "caution",
                "requires_environment",
                "Variables d'environnement exigées par le skill : " + ", ".join(variables) + ".",
            )
        )
    if kind == "native_plugin" or (kind is None and _plugin_manifest(files)):
        findings.append(
            _finding(
                "caution",
                "native_plugin",
                "Extension native détectée : la plateforme l'étiquette mais ne la charge jamais.",
            )
        )
    if not license:
        findings.append(
            _finding("info", "license_missing", "Aucune licence déclarée : origine et droits d'usage inconnus.")
        )
    if not metadata.get("name") or not metadata.get("description"):
        findings.append(
            _finding(
                "info",
                "frontmatter_incomplete",
                "Frontmatter incomplet : « name » et « description » sont attendus dans SKILL.md.",
            )
        )
    findings.append(_finding("info", "advisory_only", ADVISORY_MESSAGE))
    return findings


def _environment_variable_names(frontmatter: dict[str, Any]) -> list[str]:
    """Noms des variables d'environnement déclarées, quel que soit le style d'écriture."""

    names: list[str] = []
    for entry in _as_list(frontmatter.get("required_environment_variables")):
        if isinstance(entry, str) and entry.strip():
            names.append(entry.strip())
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return names


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def has_danger(findings: Iterable[SkillScanFinding]) -> bool:
    return any(finding.level == "danger" for finding in findings)


def relative_name(path: str) -> str:
    """Nom de fichier sans dossier (utilitaire partagé avec ``service``)."""

    return posixpath.basename(path)
