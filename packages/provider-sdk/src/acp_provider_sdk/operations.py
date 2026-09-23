"""État d'une opération durable : l'admission ne signifie pas son achèvement."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrchestratorOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["hermes"] = "hermes"
    operation: Literal["plan", "evaluate"]
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    status: Literal[
        "started", "queued", "running", "waiting_for_approval", "stopping",
        "completed", "failed", "cancelled", "interrupted",
    ]
    replayed: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
