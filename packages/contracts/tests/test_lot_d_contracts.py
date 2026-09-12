"""Validateurs des contrats du Lot D (MCP, skills, secrets, extensions)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import acp_contracts
from acp_contracts import (
    McpBindingCreate,
    McpBindingPatch,
    McpDiscoveredTool,
    McpHttpConfig,
    McpProbeResult,
    McpServerConfig,
    McpServerCreate,
    McpStdioConfig,
    ProjectExtensions,
    SecretCreate,
    SecretRef,
    SecretRotate,
    SkillImportRequest,
    SkillSourceGithub,
    SkillSourceManual,
    WorkerCapability,
)

HTTP_CONFIG = {"transport": "http", "http": {"url": "https://mcp.example/mcp"}}
STDIO_CONFIG = {"transport": "stdio", "stdio": {"command": "/usr/bin/mcp-server"}}


def _server(name: str, config: dict | None = None) -> McpServerCreate:
    return McpServerCreate(name=name, display_name="Serveur", config=config or HTTP_CONFIG)


# --- slug -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["context7", "github-remote", "a", "s1-2-3", "x" * 63])
def test_server_name_accepts_slugs(name: str):
    assert _server(name).name == name


@pytest.mark.parametrize(
    "name",
    ["", "-leading", "Upper", "with space", "under_score", "x" * 64, "é", "a/b"],
)
def test_server_name_rejects_invalid_slugs(name: str):
    with pytest.raises(ValidationError) as excinfo:
        _server(name)
    assert "slug" in str(excinfo.value)


# --- transport <-> bloc de configuration -----------------------------------


def test_http_transport_requires_http_block_only():
    config = McpServerConfig.model_validate(HTTP_CONFIG)
    assert config.http is not None and config.stdio is None
    assert config.http.timeout_seconds == 15
    with pytest.raises(ValidationError):
        McpServerConfig(transport="http")
    with pytest.raises(ValidationError):
        McpServerConfig(
            transport="http",
            http=McpHttpConfig(url="https://mcp.example/mcp"),
            stdio=McpStdioConfig(command="/usr/bin/mcp-server"),
        )


def test_stdio_transport_requires_stdio_block_only():
    config = McpServerConfig.model_validate(STDIO_CONFIG)
    assert config.stdio is not None and config.http is None
    assert config.stdio.timeout_seconds == 20
    with pytest.raises(ValidationError):
        McpServerConfig(transport="stdio")
    with pytest.raises(ValidationError):
        McpServerConfig(transport="stdio", http=McpHttpConfig(url="https://mcp.example/mcp"))


def test_unknown_transport_is_rejected():
    with pytest.raises(ValidationError):
        McpServerConfig.model_validate({"transport": "sse", "http": {"url": "https://x"}})


@pytest.mark.parametrize("timeout", [0, 121])
def test_timeouts_are_bounded(timeout: int):
    with pytest.raises(ValidationError):
        McpHttpConfig(url="https://mcp.example/mcp", timeout_seconds=timeout)
    with pytest.raises(ValidationError):
        McpStdioConfig(command="/usr/bin/mcp-server", timeout_seconds=timeout)


def test_secret_references_never_carry_values():
    config = McpHttpConfig(
        url="https://mcp.example/mcp",
        header_secrets={"Authorization": {"secret_id": "secret-1"}},
    )
    assert config.header_secrets["Authorization"] == SecretRef(secret_id="secret-1")
    assert "value" not in SecretRef.model_fields
    with pytest.raises(ValidationError):
        SecretRef(secret_id="")


# --- bindings ---------------------------------------------------------------


def test_binding_create_requires_at_least_one_tool():
    binding = McpBindingCreate(project_id="project-a", allowed_tools=["search"])
    assert binding.allowed_tools == ["search"]
    with pytest.raises(ValidationError):
        McpBindingCreate(project_id="project-a", allowed_tools=[])


def test_binding_patch_rejects_empty_tool_list_but_allows_absence():
    assert McpBindingPatch().allowed_tools is None
    assert McpBindingPatch(enabled=False).enabled is False
    with pytest.raises(ValidationError):
        McpBindingPatch(allowed_tools=[])


# --- bornes de texte --------------------------------------------------------


def test_discovered_tool_description_is_truncated():
    tool = McpDiscoveredTool(name="search", description="x" * 5000)
    assert len(tool.description) == 2000


def test_probe_result_keeps_only_the_stderr_tail():
    result = McpProbeResult(stderr_tail="a" * 100 + "b" * 4096)
    assert len(result.stderr_tail) == 4096
    assert result.stderr_tail == "b" * 4096
    assert result.tools == [] and result.error is None


# --- secrets ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["API_KEY", "A1", "CONTEXT7_API_KEY", "X" * 63])
def test_secret_name_accepts_upper_snake_case(name: str):
    assert SecretCreate(name=name, value="v").name == name


@pytest.mark.parametrize(
    "name", ["", "A", "api_key", "1KEY", "_KEY", "KEY-1", "KEY 1", "X" * 64, "ÉTÉ"]
)
def test_secret_name_rejects_other_forms(name: str):
    with pytest.raises(ValidationError):
        SecretCreate(name=name, value="v")


def test_secret_value_is_bounded_and_hidden_from_repr():
    with pytest.raises(ValidationError):
        SecretCreate(name="API_KEY", value="")
    with pytest.raises(ValidationError):
        SecretCreate(name="API_KEY", value="x" * 8193)
    secret = SecretCreate(name="API_KEY", value="hunter2-secret-value")
    assert "hunter2" not in repr(secret)
    assert "hunter2" not in repr(SecretRotate(value="hunter2-secret-value"))
    with pytest.raises(ValidationError):
        SecretRotate(value="")


def test_secret_scope_must_match_project_presence():
    assert SecretCreate(name="API_KEY", value="v").scope_type == "platform"
    project = SecretCreate(name="API_KEY", value="v", scope_type="project", project_id="p1")
    assert project.project_id == "p1"
    with pytest.raises(ValidationError):
        SecretCreate(name="API_KEY", value="v", scope_type="project")
    with pytest.raises(ValidationError):
        SecretCreate(name="API_KEY", value="v", scope_type="platform", project_id="p1")


# --- skills -----------------------------------------------------------------


def test_github_source_requires_owner_repo_and_full_sha():
    source = SkillSourceGithub(repository="anthropics/skills", ref="A" * 40, path="skills/pdf")
    assert source.ref == "a" * 40
    for ref in ["a" * 39, "a" * 41, "g" * 40, "", "main"]:
        with pytest.raises(ValidationError):
            SkillSourceGithub(repository="anthropics/skills", ref=ref)
    for repository in ["anthropics", "anthropics/", "/skills", "a/b/c", "a b/c", ""]:
        with pytest.raises(ValidationError):
            SkillSourceGithub(repository=repository, ref="a" * 40)


def test_skill_source_is_discriminated_by_kind():
    request = SkillImportRequest.model_validate(
        {"source": {"kind": "github", "repository": "o/r", "ref": "b" * 40}}
    )
    assert isinstance(request.source, SkillSourceGithub)
    assert request.name is None and request.note == ""
    manual = SkillImportRequest.model_validate(
        {
            "source": {"kind": "manual", "files": [{"path": "SKILL.md", "content": "---\nname: x\n---"}]},
            "name": "my-skill",
        }
    )
    assert isinstance(manual.source, SkillSourceManual)
    with pytest.raises(ValidationError):
        SkillImportRequest.model_validate({"source": {"kind": "ftp", "path": "/x"}})
    with pytest.raises(ValidationError):
        SkillImportRequest.model_validate({"source": {"repository": "o/r", "ref": "b" * 40}})


def test_manual_source_requires_skill_md_at_root():
    with pytest.raises(ValidationError) as excinfo:
        SkillSourceManual(files=[{"path": "README.md", "content": "x"}])
    assert "SKILL.md" in str(excinfo.value)
    with pytest.raises(ValidationError):
        SkillSourceManual(files=[{"path": "nested/SKILL.md", "content": "x"}])
    with pytest.raises(ValidationError):
        SkillSourceManual(files=[])


def test_skill_import_name_must_be_a_slug_when_given():
    with pytest.raises(ValidationError):
        SkillImportRequest.model_validate(
            {"source": {"kind": "directory", "path": "/skills/x"}, "name": "Not A Slug"}
        )


# --- extensions et énumérations --------------------------------------------


def test_project_extensions_default_to_empty_lists():
    extensions = ProjectExtensions(project_id="p1", resolved_at=datetime.now(timezone.utc))
    assert extensions.mcp == [] and extensions.skills == []
    payload = extensions.model_dump(mode="json")
    assert payload["project_id"] == "p1" and isinstance(payload["resolved_at"], str)


def test_worker_capability_exposes_stdio_probe():
    assert WorkerCapability.MCP_STDIO_PROBE.value == "mcp_stdio_probe"
    assert WorkerCapability("mcp_stdio_probe") is WorkerCapability.MCP_STDIO_PROBE


@pytest.mark.parametrize(
    "symbol",
    [
        "McpServerSummary", "McpServerDetail", "McpServerRevision", "McpProbe", "McpProbeDecision",
        "McpBinding", "McpDiscovery", "McpRevisionDiff", "McpRiskFlag", "McpCatalogEntry",
        "McpImportPreviewRequest", "McpImportPreview", "McpImportApplyRequest", "McpImportApplyResult",
        "McpExport", "McpRevokeRequest", "McpRollbackRequest", "McpProbeAuthorization",
        "SecretSummary", "SecretsStatus", "SkillSummary", "SkillDetail", "SkillRevision", "SkillFile",
        "SkillFileContent", "SkillBinding", "SkillBindingCreate", "SkillDependencies", "SkillScanFinding",
        "SkillRevisionDiff", "SkillSource", "SkillSourceDirectory", "SkillSourceArchive",
        "SkillRevisionCreate", "SkillRevokeRequest", "SkillRollbackRequest", "SkillApproveRequest",
        "SkillSearchResult", "SkillCatalogEntry", "ProjectMcpExtension", "ProjectSkillExtension",
    ],
)
def test_lot_d_models_are_reexported(symbol: str):
    assert hasattr(acp_contracts, symbol), symbol
