from acp_contracts import EvaluationRequest
from acp_contracts.sessions import SessionContext

from acp_provider_gateway.providers.manual import ManualOrchestratorProvider


async def test_pending_manual_review_is_never_an_approval():
    provider = ManualOrchestratorProvider()
    result = await provider.evaluate_result(
        EvaluationRequest(
            session=SessionContext(
                session_id="session-1",
                workspace_id="workspace-1",
                project_id="project-1",
                provider_id="manual",
            ),
            task_summary="Livrable sans preuve",
        )
    )
    assert result.approved is False
    assert result.score == 0.0
    assert len(provider.pending) == 1
