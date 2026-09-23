"""Chargement borné des compétences épinglées par la mission."""

import hashlib
from typing import Any

import httpx

from .config import WorkerConfig


async def load_extensions(client: httpx.AsyncClient, config: WorkerConfig, worker_id: str,
                          attempt_id: str, fencing_token: int, snapshot: Any) -> dict:
    if not isinstance(snapshot, dict):
        raise RuntimeError("snapshot d'extensions invalide")
    if not snapshot.get("skills") and not snapshot.get("mcp"):
        return {"skills": [], "mcp": []}
    response = await client.get(f"{config.api_url}/work/workers/{worker_id}/runs/{attempt_id}/extensions",
                                headers={"X-Attempt-Fencing-Token": str(fencing_token)})
    response.raise_for_status()
    if len(response.content) > 200_000:
        raise RuntimeError("contenu d'extensions trop volumineux")
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list) or not isinstance(data.get("mcp"), list):
        raise RuntimeError("réponse d'extensions invalide")
    expected_mcp = {(item["server_id"], item["revision_number"]) for item in snapshot.get("mcp", [])}
    returned_mcp = {(item["server_id"], item["revision_number"]) for item in data["mcp"]}
    if returned_mcp != expected_mcp:
        raise RuntimeError("liaisons MCP de la mission incohérentes")
    expected = {(item["skill_id"], item["revision_number"]) for item in snapshot.get("skills", [])}
    actual = set()
    remaining = 24_000
    for skill in data["skills"]:
        if not isinstance(skill, dict) or not isinstance(skill.get("content"), str) or not isinstance(skill.get("name"), str):
            raise RuntimeError("compétence d'exécution invalide")
        content = skill["content"]
        key = (skill.get("skill_id"), skill.get("revision_number"))
        if key not in expected or key in actual or hashlib.sha256(content.encode()).hexdigest() != skill.get("sha256"):
            raise RuntimeError("révision de compétence ou empreinte discordante")
        remaining -= len(content)
        if remaining < 0:
            raise RuntimeError("contenu de compétences supérieur à 24000 caractères")
        actual.add(key)
    if actual != expected:
        raise RuntimeError("une compétence épinglée manque à l'exécution")
    return data
