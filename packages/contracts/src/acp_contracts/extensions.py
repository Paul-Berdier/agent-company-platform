"""Instantané des extensions (serveurs MCP et skills) résolues pour un projet.

Cet instantané est figé dans ``TaskModel.meta["extensions"]`` à la création d'une
mission : une révision ultérieure ne modifie pas une mission déjà créée.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .mcp import McpServerStatus
from .skills import SkillStatus


class ProjectMcpExtension(BaseModel):
    server_id: str
    name: str
    revision_number: int
    allowed_tools: list[str] = Field(default_factory=list)
    enabled: bool = True
    server_status: McpServerStatus


class ProjectSkillExtension(BaseModel):
    skill_id: str
    name: str
    revision_number: int
    enabled: bool = True
    skill_status: SkillStatus


class ProjectExtensions(BaseModel):
    project_id: str
    mcp: list[ProjectMcpExtension] = Field(default_factory=list)
    skills: list[ProjectSkillExtension] = Field(default_factory=list)
    resolved_at: datetime
