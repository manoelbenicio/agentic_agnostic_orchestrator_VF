"""Bridge that records FinOps cost from executor lifecycle events.

This closes the loop between the dual executors and the FinOps engine: when an
executor emits a lifecycle event whose ``details`` carry a ``finops`` payload
(token usage and/or seat usage reported by the underlying runtime), the cost is
recorded automatically with the task's attribution chain.

Design contract (no fabrication): cost is only recorded when an executor
actually surfaces usage. With the current stub adapters that report no usage,
nothing is recorded — exactly the honest behavior documented in
``docs/30-COMPONENTES/34-EXECUCAO-DUAL-MODE.md``. When real per-vendor adapters
(or HerdMaster) start reporting usage, FinOps is fed with zero extra wiring.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from .engine import FinOpsEngine
from .models import Attribution, CostRecord, SeatUsage, TokenUsage

logger = logging.getLogger(__name__)


def _decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def record_event_costs(
    engine: FinOpsEngine,
    *,
    tenant_id: str,
    project_id: str,
    issue_id: str,
    agent_id: str,
    runtime_id: str,
    trace_id: str | None,
    details: Mapping[str, Any] | None,
) -> list[CostRecord]:
    """Record any FinOps cost described in a lifecycle event's details.

    Returns the list of persisted ``CostRecord`` (possibly empty). Never raises
    on bad/missing payloads — it logs and skips so dispatch is never broken by
    a metering issue.
    """
    finops = (details or {}).get("finops")
    if not isinstance(finops, Mapping):
        return []

    attribution = Attribution(
        tenant_id=tenant_id,
        project_id=project_id,
        issue_id=issue_id,
        agent_id=agent_id,
        runtime_id=runtime_id,
    )
    records: list[CostRecord] = []

    token = finops.get("token")
    if isinstance(token, Mapping) and token:
        try:
            records.append(
                engine.record_token_usage(
                    attribution,
                    TokenUsage(
                        input_tokens=int(token.get("input_tokens", 0)),
                        output_tokens=int(token.get("output_tokens", 0)),
                        input_token_price_usd=_decimal(token.get("input_token_price_usd")),
                        output_token_price_usd=_decimal(token.get("output_token_price_usd")),
                        model=str(token.get("model", "unknown")),
                    ),
                    trace_id=trace_id,
                )
            )
        except Exception:  # pragma: no cover - defensive: never break dispatch
            logger.warning("FinOps token bridge failed for task attribution %s", attribution, exc_info=True)

    seat = finops.get("seat")
    if isinstance(seat, Mapping) and seat:
        try:
            records.append(
                engine.record_seat_usage(
                    attribution,
                    SeatUsage(
                        seat_id=str(seat.get("seat_id", runtime_id)),
                        vendor=str(seat.get("vendor", "unknown")),
                        used_seconds=int(seat.get("used_seconds", 0)),
                        period_seconds=int(seat.get("period_seconds", 0)),
                        period_cost_usd=_decimal(seat.get("period_cost_usd")),
                    ),
                    trace_id=trace_id,
                )
            )
        except Exception:  # pragma: no cover - defensive: never break dispatch
            logger.warning("FinOps seat bridge failed for task attribution %s", attribution, exc_info=True)

    return records
