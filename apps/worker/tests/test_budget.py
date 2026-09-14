"""Frontière budgétaire du worker : permis avant effet, usage après effet."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from acp_worker.budget import (
    BudgetDenied,
    BudgetUnavailable,
    EffectBudgetBounds,
    budgeted_effect,
    non_consuming_effect_bounds,
)
from acp_worker.config import WorkerConfig
from acp_worker.state import WorkerCredentials


def config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        api_url="https://api.test",
        gateway_url="https://gateway.test",
        gateway_service_token="gateway-secret",
        provider_id="hermes",
        poll_interval=0.01,
        step_seconds=0,
        state_dir=tmp_path,
        name="budget-worker",
        max_concurrency=1,
        simulation=False,
        registration_token=None,
        local_runner=None,
    )


def credentials() -> WorkerCredentials:
    return WorkerCredentials(
        worker_id="worker-1",
        token="secret",
        api_origin="https://api.test",
        name="budget-worker",
        capabilities=[],
        max_concurrency=1,
        simulation=False,
        token_expires_at="2030-01-01T00:00:00Z",
    )


def mutation_result(
    *, permit_allowed: bool = True, state: str = "ok", idempotent: bool = False
) -> dict:
    # Même un verdict ``unknown`` réel confirme le compteur d'appel transmis ;
    # seule la dimension plafonnée (coût/jetons) demeure alors inconnue.
    measured = True
    return {
        "accepted": True,
        "idempotent": idempotent,
        "permit_allowed": permit_allowed,
        "verdict": {
            "state": state,
            "measured": measured,
            "limit_reached": (
                "max_tool_calls" if state in {"warning", "exceeded"} else None
            ),
            "cost": None,
            "currency": "EUR",
            "tokens_input": None,
            "tokens_output": None,
            "tool_calls": 1,
            "usage_reported": False,
            "estimated": False,
        },
    }


async def test_denied_permit_prevents_the_effect(tmp_path: Path):
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/budget/permit")
        return httpx.Response(
            200,
            json=mutation_result(permit_allowed=False, state="unknown"),
        )

    async def effect() -> dict:
        nonlocal called
        called = True
        return {}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BudgetDenied, match="unknown"):
            await budgeted_effect(
                client,
                config(tmp_path),
                credentials(),
                attempt_id="run-1",
                fencing_token=7,
                effect_key="plan",
                provider="hermes",
                phase="planning",
                operation=effect,
            )
    assert called is False


async def test_effect_is_bracketed_and_unknown_usage_is_not_invented(tmp_path: Path):
    requests: list[tuple[str, dict]] = []
    sequence: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        sequence.append(request.url.path.rsplit("/", 1)[-1])
        assert request.headers["x-attempt-fencing-token"] == "7"
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async def effect() -> dict:
        sequence.append("effect")
        return {"result": "ok"}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await budgeted_effect(
            client,
            config(tmp_path),
            credentials(),
            attempt_id="run-1",
            fencing_token=7,
            effect_key="plan",
            provider="hermes",
            phase="planning",
            operation=effect,
        )

    assert result == {"result": "ok"}
    assert sequence == ["permit", "effect", "usage"]
    permit = requests[0][1]
    usage = requests[1][1]
    assert permit == {
        "permit_id": permit["permit_id"],
        "provider": "hermes",
        "phase": "planning",
        "tool_calls": 1,
    }
    assert usage == {
        "report_id": usage["report_id"],
        "permit_id": permit["permit_id"],
        "provider": "hermes",
        "phase": "planning",
        "source": "platform",
        "tool_calls": 1,
    }


async def test_provider_usage_is_copied_only_when_reported(tmp_path: Path):
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async def effect() -> dict:
        return {
            "usage": {
                "cost": 0.0000004,
                "currency": "usd",
                "tokens_input": 3,
                "tokens_output": 5,
            }
        }

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await budgeted_effect(
            client,
            config(tmp_path),
            credentials(),
            attempt_id="run-1",
            fencing_token=7,
            effect_key="evaluation",
            provider="hermes",
            phase="evaluation",
            operation=effect,
        )

    usage = payloads[-1]
    assert usage["source"] == "provider"
    assert usage["cost"] == 0.0000004
    assert usage["currency"] == "USD"
    assert usage["tokens_input"] == 3
    assert usage["tokens_output"] == 5
    assert usage["tool_calls"] == 1


async def test_failed_effect_leaves_the_reservation_unreconciled(tmp_path: Path):
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async def effect() -> dict:
        raise RuntimeError("provider down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="provider down"):
            await budgeted_effect(
                client,
                config(tmp_path),
                credentials(),
                attempt_id="run-1",
                fencing_token=7,
                effect_key="plan",
                provider="hermes",
                phase="planning",
                operation=effect,
            )
    assert paths == [
        "/work/workers/worker-1/runs/run-1/budget/permit"
    ]


async def test_invalid_permit_response_fails_closed(tmp_path: Path):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    ) as client:
        with pytest.raises(BudgetUnavailable, match="incomplète"):
            await budgeted_effect(
                client,
                config(tmp_path),
                credentials(),
                attempt_id="run-1",
                fencing_token=7,
                effect_key="plan",
                provider="hermes",
                phase="planning",
                operation=lambda: pytest.fail("effet interdit"),
            )


async def test_incomplete_or_incoherent_permit_never_reaches_the_effect(
    tmp_path: Path,
):
    missing_idempotent = mutation_result()
    missing_idempotent.pop("idempotent")
    missing_verdict = mutation_result()
    missing_verdict.pop("verdict")
    minimal_unmeasured_verdict = mutation_result()
    minimal_unmeasured_verdict["verdict"] = {"state": "ok"}
    allowed_unknown = mutation_result(state="unknown")
    internally_invalid = mutation_result()
    internally_invalid["verdict"]["measured"] = False
    malformed_boolean = mutation_result()
    malformed_boolean["idempotent"] = 0

    for payload in (
        missing_idempotent,
        missing_verdict,
        minimal_unmeasured_verdict,
        allowed_unknown,
        internally_invalid,
        malformed_boolean,
    ):
        called = False

        async def effect() -> dict:
            nonlocal called
            called = True
            return {}

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request, response=payload: httpx.Response(200, json=response)
            )
        ) as client:
            with pytest.raises(
                BudgetUnavailable, match="incomplète|incohérente|sans mesure"
            ):
                await budgeted_effect(
                    client,
                    config(tmp_path),
                    credentials(),
                    attempt_id="run-invalid-permit",
                    fencing_token=7,
                    effect_key="plan",
                    provider="hermes",
                    phase="planning",
                    operation=effect,
                )
        assert called is False


async def test_incomplete_usage_result_is_never_accepted_as_reconciled(
    tmp_path: Path,
):
    responses = iter((mutation_result(), {"accepted": True, "permit_allowed": True}))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BudgetUnavailable, match="rapport.*incomplète"):
            await budgeted_effect(
                client,
                config(tmp_path),
                credentials(),
                attempt_id="run-invalid-report",
                fencing_token=7,
                effect_key="plan",
                provider="hermes",
                phase="planning",
                operation=lambda: _async_result({"status": "succeeded"}),
            )


async def test_limited_provider_dimensions_without_hard_bounds_fail_before_io(
    tmp_path: Path,
):
    requested = False
    effected = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(500)

    async def effect() -> dict:
        nonlocal effected
        effected = True
        return {}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(
            BudgetUnavailable,
            match="estimation conservatrice indisponible.*coût.*jetons",
        ):
            await budgeted_effect(
                client,
                config(tmp_path),
                credentials(),
                attempt_id="run-limited",
                fencing_token=7,
                effect_key="hermes-plan",
                provider="hermes",
                phase="planning",
                budget={
                    "max_cost": 1,
                    "currency": "EUR",
                    "max_tokens": 100,
                    "max_tool_calls": 5,
                },
                bounds=EffectBudgetBounds(tool_calls=1),
                operation=effect,
            )

    assert requested is False
    assert effected is False


async def test_hard_bounds_are_reserved_then_replaced_by_complete_real_usage(
    tmp_path: Path,
):
    requests: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (request.url.path.rsplit("/", 1)[-1], json.loads(request.content))
        )
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async def effect() -> dict:
        return {
            "usage": {
                "cost": 0.25,
                "currency": "EUR",
                "tokens_input": 20,
                "tokens_output": 30,
            }
        }

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await budgeted_effect(
            client,
            config(tmp_path),
            credentials(),
            attempt_id="run-bounded",
            fencing_token=7,
            effect_key="bounded-provider-call",
            provider="bounded-provider",
            phase="planning",
            budget={
                "max_cost": 2,
                "currency": "EUR",
                "max_tokens": 500,
                "max_tool_calls": 5,
            },
            bounds=EffectBudgetBounds(
                cost=1,
                currency="EUR",
                tokens_input=100,
                tokens_output=100,
                tool_calls=1,
            ),
            operation=effect,
        )

    assert result["usage"]["tokens_output"] == 30
    assert [kind for kind, _ in requests] == ["permit", "usage"]
    permit = requests[0][1]
    assert permit["cost"] == 1
    assert permit["currency"] == "EUR"
    assert permit["tokens_input"] == permit["tokens_output"] == 100
    usage = requests[1][1]
    assert usage["cost"] == 0.25
    assert usage["tokens_input"] == 20
    assert usage["tokens_output"] == 30
    assert usage["source"] == "provider"


async def test_decimal_cost_bound_is_rounded_up_before_json_transport(tmp_path: Path):
    requests: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (request.url.path.rsplit("/", 1)[-1], json.loads(request.content))
        )
        return httpx.Response(200, json=mutation_result())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await budgeted_effect(
            client,
            config(tmp_path),
            credentials(),
            attempt_id="run-decimal-bound",
            fencing_token=7,
            effect_key="decimal-provider-call",
            provider="bounded-provider",
            phase="planning",
            budget={"max_cost": 1, "currency": "EUR"},
            bounds=EffectBudgetBounds(
                cost=Decimal("0.100000000000000005"),
                currency="EUR",
                tool_calls=1,
            ),
            operation=lambda: _async_result(
                {"usage": {"cost": 0.1, "currency": "EUR"}}
            ),
        )

    assert [kind for kind, _ in requests] == ["permit", "usage"]
    assert Decimal(str(requests[0][1]["cost"])) >= Decimal("0.100001")


async def test_usage_above_a_declared_hard_bound_is_reported_then_fails(
    tmp_path: Path,
):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BudgetUnavailable, match="supérieur à la borne"):
            await budgeted_effect(
                client,
                config(tmp_path),
                credentials(),
                attempt_id="run-broken-bound",
                fencing_token=7,
                effect_key="provider-call",
                provider="bounded-provider",
                phase="planning",
                budget={"max_tokens": 500},
                bounds=EffectBudgetBounds(
                    tokens_input=10,
                    tokens_output=10,
                    tool_calls=1,
                ),
                operation=lambda: _async_result(
                    {"usage": {"tokens_input": 11, "tokens_output": 10}}
                ),
            )

    # L'usage réel est d'abord envoyé au ledger : le défaut de l'adaptateur ne
    # transforme jamais le dépassement en consommation invisible.
    assert requests == ["permit", "usage"]


async def test_missing_real_usage_keeps_the_conservative_reservation_pending(
    tmp_path: Path,
):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await budgeted_effect(
            client,
            config(tmp_path),
            credentials(),
            attempt_id="run-missing-usage",
            fencing_token=7,
            effect_key="bounded-provider-call",
            provider="bounded-provider",
            phase="planning",
            budget={"max_cost": 2, "currency": "EUR", "max_tokens": 500},
            bounds=EffectBudgetBounds(
                cost=1,
                currency="EUR",
                tokens_input=100,
                tokens_output=100,
                tool_calls=1,
            ),
            operation=lambda: _async_result({"result": "usage omitted"}),
        )

    assert result == {"result": "usage omitted"}
    assert requests == ["permit"]


async def test_exact_zero_bounds_make_a_local_effect_budgetable_without_invention(
    tmp_path: Path,
):
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=mutation_result(),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await budgeted_effect(
            client,
            config(tmp_path),
            credentials(),
            attempt_id="run-local",
            fencing_token=7,
            effect_key="local-program",
            provider="local-runner",
            phase="execution",
            budget={"max_cost": 0, "currency": "EUR", "max_tokens": 0},
            bounds=non_consuming_effect_bounds("EUR"),
            operation=lambda: _async_result({"status": "succeeded"}),
        )

    assert result == {"status": "succeeded"}
    # L'absence de rapport provider conserve la réservation exacte à zéro ; elle
    # n'est jamais transformée en un usage prétendument mesuré par la plateforme.
    assert len(payloads) == 1
    assert payloads[0]["cost"] == 0
    assert payloads[0]["tokens_input"] == payloads[0]["tokens_output"] == 0


async def _async_result(value: dict) -> dict:
    return value
