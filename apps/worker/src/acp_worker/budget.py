"""Client fail-closed du ledger budgétaire du worker réel.

Chaque effet observable obtient d'abord un permis idempotent. Une réservation
non rapprochée reste comptée si l'effet échoue, est annulé ou si son rapport ne
peut pas atteindre l'API : aucune consommation inconnue ne devient zéro.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from hashlib import sha256
from math import inf, isfinite, nextafter
from typing import Any, Literal, TypeVar

import httpx
from acp_contracts import BudgetMutationResult
from pydantic import ValidationError

from .config import WorkerConfig
from .state import WorkerCredentials

_T = TypeVar("_T")
BudgetPhase = Literal["planning", "execution", "evaluation", "tool"]
_LEDGER_COST_QUANTUM = Decimal("0.000001")


class BudgetDenied(RuntimeError):
    """Le ledger a refusé l'effet avant son exécution."""


class BudgetUnavailable(RuntimeError):
    """L'API ne permet pas de prouver la réservation ou le rapprochement."""


@dataclass(frozen=True)
class EffectBudgetBounds:
    """Bornes de consommation garanties avant un effet.

    ``None`` signifie bien « aucune borne disponible », jamais zéro. Les zéros
    explicites sont réservés aux effets dont l'implémentation garantit qu'ils ne
    consomment pas la métrique (runner local, Playwright, provider simulé ou
    manuel). Une valeur positive doit être un plafond dur imposé par l'adaptateur,
    et non une moyenne historique ou le budget restant.
    """

    cost: Decimal | float | int | None = None
    currency: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    tool_calls: int | None = 1


def non_consuming_effect_bounds(currency: str) -> EffectBudgetBounds:
    """Déclare les zéros vérifiables d'un effet local sans modèle facturé."""

    return EffectBudgetBounds(
        cost=0,
        currency=currency,
        tokens_input=0,
        tokens_output=0,
        tool_calls=1,
    )


def gateway_effect_bounds(provider: str, currency: str) -> EffectBudgetBounds:
    """Retourne seulement les garanties réellement offertes par le provider.

    Hermes 0.21.1 ne propose aucun plafond coût/jetons sur ``POST /v1/runs``.
    Ces dimensions restent donc absentes et une mission qui les limite échouera
    explicitement *avant* l'appel. ``manual`` et ``mock`` ne lancent aucun modèle
    facturé et peuvent annoncer des zéros exacts.
    """

    if provider in {"manual", "mock"}:
        return non_consuming_effect_bounds(currency)
    return EffectBudgetBounds(tool_calls=1)


def _stable_identifier(kind: str, attempt_id: str, effect_key: str) -> str:
    digest = sha256(f"{attempt_id}\0{effect_key}".encode("utf-8")).hexdigest()
    return f"worker-{kind}-{digest}"


def _fencing_headers(fencing_token: int) -> dict[str, str]:
    if (
        not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 1
    ):
        raise BudgetUnavailable("fencing_token positif requis pour le budget")
    return {"X-Attempt-Fencing-Token": str(fencing_token)}


def _response_body(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BudgetUnavailable(f"{operation} budgétaire indisponible") from exc
    if not isinstance(body, dict):
        raise BudgetUnavailable(f"réponse de {operation} budgétaire invalide")
    return body


def _mutation_result(
    body: dict[str, Any], operation: Literal["permis", "rapport"]
) -> BudgetMutationResult:
    """Valide toute la preuve renvoyée par le ledger avant de lui faire confiance.

    Une réponse HTTP 200 n'est pas une preuve suffisante. Le contrat strict rend
    notamment obligatoires le marqueur d'idempotence et un verdict cohérent. Les
    relations propres à l'opération sont ensuite vérifiées ici : un permis accordé
    ne peut pas annoncer une mesure inconnue/dépassée, et le rapport d'usage doit
    avoir été accepté sans tenter de requalifier le permis après l'effet.
    """

    try:
        result = BudgetMutationResult.model_validate(body)
    except ValidationError as exc:
        raise BudgetUnavailable(
            f"réponse de {operation} budgétaire incomplète ou incohérente"
        ) from exc
    if result.accepted is not True:
        raise BudgetUnavailable(f"{operation} budgétaire non accepté")
    # Chaque requête worker contient au moins une borne explicite (actuellement
    # ``tool_calls``). Le service doit donc confirmer un verdict fondé sur une
    # quantité connue. Accepter le default ``measured=False`` d'un objet verdict
    # minimal reviendrait à refaire confiance à un simple booléen HTTP 200.
    if result.verdict.measured is not True:
        raise BudgetUnavailable(
            f"réponse de {operation} budgétaire sans mesure vérifiable"
        )
    if operation == "permis":
        if result.permit_allowed and result.verdict.state in {"unknown", "exceeded"}:
            raise BudgetUnavailable(
                "réponse de permis budgétaire incohérente avec son verdict"
            )
        if not result.permit_allowed and result.verdict.state == "ok":
            raise BudgetUnavailable(
                "réponse de permis budgétaire incohérente avec son verdict"
            )
    elif result.permit_allowed is not True:
        raise BudgetUnavailable("rapport budgétaire refusé après l'effet")
    return result


def _nonnegative_integer(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BudgetUnavailable(f"borne conservatrice {label} invalide")
    return value


def _conservative_json_cost(value: Decimal | float | int) -> float:
    """Encode un plafond Decimal en nombre JSON sans jamais l'abaisser.

    Le contrat HTTP refuse les chaînes et la bibliothèque JSON standard ne sait
    pas encoder ``Decimal``. On arrondit donc d'abord vers le haut au quantum du
    ledger, puis on avance d'un ULP si la conversion binaire est descendante.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise BudgetUnavailable("borne conservatrice de coût invalide")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise BudgetUnavailable("borne conservatrice de coût invalide")
        rounded = amount.quantize(_LEDGER_COST_QUANTUM, rounding=ROUND_CEILING)
        transported = float(rounded)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise BudgetUnavailable("borne conservatrice de coût invalide") from exc
    if not isfinite(transported):
        raise BudgetUnavailable("borne conservatrice de coût invalide")
    if Decimal(str(transported)) < rounded:
        transported = nextafter(transported, inf)
    if not isfinite(transported) or Decimal(str(transported)) < rounded:
        raise BudgetUnavailable("borne conservatrice de coût non transportable")
    return transported


def _reservation_measurements(
    budget: Mapping[str, Any] | None,
    bounds: EffectBudgetBounds,
    *,
    provider: str,
) -> dict[str, Any]:
    """Valide et matérialise les bornes avant toute requête ou tout effet."""

    measurements: dict[str, Any] = {}
    if bounds.cost is not None:
        if (
            not isinstance(bounds.currency, str)
            or len(bounds.currency) != 3
            or not bounds.currency.isascii()
            or not bounds.currency.isalpha()
        ):
            raise BudgetUnavailable("devise de la borne conservatrice invalide")
        measurements["cost"] = _conservative_json_cost(bounds.cost)
        measurements["currency"] = bounds.currency.upper()
    elif bounds.currency is not None:
        raise BudgetUnavailable("une devise sans borne de coût est interdite")

    if bounds.tokens_input is not None:
        measurements["tokens_input"] = _nonnegative_integer(
            bounds.tokens_input, label="de jetons d'entrée"
        )
    if bounds.tokens_output is not None:
        measurements["tokens_output"] = _nonnegative_integer(
            bounds.tokens_output, label="de jetons de sortie"
        )
    if bounds.tool_calls is not None:
        measurements["tool_calls"] = _nonnegative_integer(
            bounds.tool_calls, label="d'appels d'outils"
        )

    limits = budget or {}
    missing: list[str] = []
    if limits.get("max_cost") is not None and "cost" not in measurements:
        missing.append("coût")
    if limits.get("max_tokens") is not None and not {
        "tokens_input",
        "tokens_output",
    }.issubset(measurements):
        missing.append("jetons d'entrée/sortie")
    if limits.get("max_tool_calls") is not None and "tool_calls" not in measurements:
        missing.append("appels d'outils")
    if missing:
        raise BudgetUnavailable(
            "estimation conservatrice indisponible avant effet pour "
            f"{provider}: {', '.join(missing)}"
        )
    if not measurements:
        raise BudgetUnavailable("aucune borne conservatrice disponible avant effet")
    return measurements


async def request_permit(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    *,
    attempt_id: str,
    fencing_token: int,
    effect_key: str,
    provider: str,
    phase: BudgetPhase,
    budget: Mapping[str, Any] | None = None,
    bounds: EffectBudgetBounds | None = None,
) -> tuple[str, dict[str, Any]]:
    """Réserve toutes les dimensions limitées avant le moindre effet."""

    permit_id = _stable_identifier("permit", attempt_id, effect_key)
    measurements = _reservation_measurements(
        budget,
        bounds or EffectBudgetBounds(),
        provider=provider,
    )
    response = await client.post(
        (
            f"{config.api_url}/work/workers/{credentials.worker_id}/runs/"
            f"{attempt_id}/budget/permit"
        ),
        headers=_fencing_headers(fencing_token),
        json={
            "permit_id": permit_id,
            "provider": provider,
            "phase": phase,
            **measurements,
        },
    )
    result = _mutation_result(_response_body(response, "permis"), "permis")
    if result.permit_allowed is not True:
        state = result.verdict.state
        suffix = (
            " (unknown: estimation conservatrice indisponible pour une "
            "politique active)"
            if state == "unknown"
            else f" ({state})" if isinstance(state, str) else ""
        )
        raise BudgetDenied(f"effet refusé par le budget{suffix}")
    return permit_id, measurements


def _provider_measurements(result: object) -> dict[str, Any]:
    """Copie seulement les mesures provider présentes et correctement typées."""

    if not isinstance(result, dict) or not isinstance(result.get("usage"), dict):
        return {}
    usage = result["usage"]
    measurements: dict[str, Any] = {}
    cost = usage.get("cost")
    currency = usage.get("currency")
    if (
        isinstance(cost, (int, float))
        and not isinstance(cost, bool)
        and isfinite(float(cost))
        and cost >= 0
        and isinstance(currency, str)
        and len(currency) == 3
        and currency.isascii()
        and currency.isalpha()
    ):
        measurements["cost"] = cost
        measurements["currency"] = currency.upper()
    for field in ("tokens_input", "tokens_output"):
        value = usage.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            measurements[field] = value
    estimated = usage.get("estimated")
    if isinstance(estimated, bool):
        measurements["estimated"] = estimated
    return measurements


async def report_usage(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    *,
    attempt_id: str,
    fencing_token: int,
    effect_key: str,
    permit_id: str,
    provider: str,
    phase: BudgetPhase,
    result: object,
    reservation: Mapping[str, Any],
) -> bool:
    """Rapproche une réservation seulement avec un usage provider complet.

    Si une dimension réservée n'est pas rapportée, aucune ligne d'usage n'est
    écrite : la réservation conservatrice demeure active dans le ledger. Le
    résultat booléen indique si le rapprochement a effectivement eu lieu.
    """

    measurements = _provider_measurements(result)
    provider_dimensions = ("cost", "tokens_input", "tokens_output")
    reserved_provider_dimensions = [
        name for name in provider_dimensions if name in reservation
    ]
    if reserved_provider_dimensions and (
        measurements.get("estimated") is True
        or any(name not in measurements for name in reserved_provider_dimensions)
        or (
            "cost" in reservation
            and measurements.get("currency") != reservation.get("currency")
        )
    ):
        return False

    exceeded_bound = any(
        Decimal(str(measurements[name])) > Decimal(str(reservation[name]))
        for name in reserved_provider_dimensions
    )
    source = "provider" if any(
        name in measurements for name in ("cost", "tokens_input", "tokens_output")
    ) else "platform"
    # Une source plateforme n'est autorisée à affirmer que ce que le worker sait
    # réellement : l'effet a été lancé une fois. Les coûts/jetons restent absents.
    if source == "platform":
        measurements = {}
    response = await client.post(
        (
            f"{config.api_url}/work/workers/{credentials.worker_id}/runs/"
            f"{attempt_id}/budget/usage"
        ),
        headers=_fencing_headers(fencing_token),
        json={
            "report_id": _stable_identifier("usage", attempt_id, effect_key),
            "permit_id": permit_id,
            "provider": provider,
            "phase": phase,
            "source": source,
            "tool_calls": reservation.get("tool_calls", 1),
            **measurements,
        },
    )
    result = _mutation_result(_response_body(response, "rapport"), "rapport")
    if exceeded_bound:
        raise BudgetUnavailable(
            "usage provider supérieur à la borne conservatrice réservée"
        )
    if result.verdict.state == "exceeded":
        raise BudgetDenied("usage provider au-delà du budget après rapprochement")
    return True


async def budgeted_effect(
    client: httpx.AsyncClient,
    config: WorkerConfig,
    credentials: WorkerCredentials,
    *,
    attempt_id: str,
    fencing_token: int,
    effect_key: str,
    provider: str,
    phase: BudgetPhase,
    operation: Callable[[], Awaitable[_T]],
    budget: Mapping[str, Any] | None = None,
    bounds: EffectBudgetBounds | None = None,
) -> _T:
    """Exécute un effet seulement entre sa réservation et son rapport.

    En cas d'exception ou d'annulation de l'effet, la réservation volontairement
    non rapprochée reste active dans le ledger. C'est le comportement sûr lorsque
    le worker ignore si le système externe a réellement facturé l'appel.
    """

    permit_id, reservation = await request_permit(
        client,
        config,
        credentials,
        attempt_id=attempt_id,
        fencing_token=fencing_token,
        effect_key=effect_key,
        provider=provider,
        phase=phase,
        budget=budget,
        bounds=bounds,
    )
    result = await operation()
    await report_usage(
        client,
        config,
        credentials,
        attempt_id=attempt_id,
        fencing_token=fencing_token,
        effect_key=effect_key,
        permit_id=permit_id,
        provider=provider,
        phase=phase,
        result=result,
        reservation=reservation,
    )
    return result
