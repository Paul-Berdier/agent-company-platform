from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import MemoryClassification, MemoryScope, SharingPolicy


class MemoryItem(BaseModel):
    id: str = ""
    scope: MemoryScope
    owner_id: str  # id de l'entité propriétaire du scope (projet, agent, ...)
    source: str = ""  # provider, agent, humain...
    classification: MemoryClassification = MemoryClassification.INTERNAL
    sharing_policy: SharingPolicy = SharingPolicy.SCOPE_ONLY
    ttl_seconds: int | None = None  # None = permanent
    content: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
