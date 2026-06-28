"""Dual FinOps cost engine."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from .models import (
    Attribution,
    BillingMode,
    CostEngine,
    CostRecord,
    SeatUsage,
    TokenUsage,
    utc_now,
)
from .repository import FinOpsRepository


class FinOpsEngine:
    """Compute and persist token-based and seat-utilization-based costs."""

    def __init__(self, repository: FinOpsRepository) -> None:
        self.repository = repository

    def record_token_usage(
        self,
        attribution: Attribution,
        usage: TokenUsage,
        *,
        billing_mode: BillingMode = BillingMode.PAY_AS_YOU_GO,
        trace_id: str | None = None,
    ) -> CostRecord:
        """Compute API-backed token cost and persist it."""
        cost = (
            Decimal(usage.input_tokens) * usage.input_token_price_usd
            + Decimal(usage.output_tokens) * usage.output_token_price_usd
        )
        record = CostRecord(
            cost_id=f"cost-{uuid4()}",
            engine=CostEngine.TOKEN,
            billing_mode=billing_mode,
            attribution=attribution,
            cost_usd=cost,
            usage_units={
                "input_tokens": Decimal(usage.input_tokens),
                "output_tokens": Decimal(usage.output_tokens),
                "total_tokens": Decimal(usage.total_tokens),
            },
            occurred_at=utc_now(),
            trace_id=trace_id,
            metadata={"model": usage.model, **usage.metadata},
        )
        return self.repository.insert_cost(record)

    def record_seat_usage(
        self,
        attribution: Attribution,
        usage: SeatUsage,
        *,
        billing_mode: BillingMode = BillingMode.MONTHLY,
        trace_id: str | None = None,
    ) -> CostRecord:
        """Compute flat-subscription seat utilization cost and persist it."""
        if usage.period_seconds <= 0:
            raise ValueError("period_seconds must be greater than zero")
        share = Decimal(usage.used_seconds) / Decimal(usage.period_seconds)
        cost = usage.period_cost_usd * share
        self.repository.insert_seat_observation(
            tenant_id=attribution.tenant_id,
            seat_id=usage.seat_id,
            vendor=usage.vendor,
            used_seconds=usage.used_seconds,
            period_seconds=usage.period_seconds,
            period_cost_usd=usage.period_cost_usd,
        )
        record = CostRecord(
            cost_id=f"cost-{uuid4()}",
            engine=CostEngine.SEAT,
            billing_mode=billing_mode,
            attribution=attribution,
            cost_usd=cost,
            usage_units={
                "seat_seconds": Decimal(usage.used_seconds),
                "period_seconds": Decimal(usage.period_seconds),
                "utilization_share": share,
            },
            occurred_at=utc_now(),
            trace_id=trace_id,
            metadata={"seat_id": usage.seat_id, "vendor": usage.vendor, **usage.metadata},
        )
        return self.repository.insert_cost(record)
