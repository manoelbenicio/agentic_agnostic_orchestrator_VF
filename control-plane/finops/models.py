"""Domain models for cost attribution and utilization analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any


class CostEngine(StrEnum):
    """Cost calculation engine used for one metering record."""

    TOKEN = "token"
    SEAT = "seat"


class BillingMode(StrEnum):
    """Tenant billing mode."""

    PAY_AS_YOU_GO = "pay_as_you_go"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class Attribution:
    """Hierarchical cost attribution chain."""

    tenant_id: str
    project_id: str
    issue_id: str
    agent_id: str
    runtime_id: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """API-backed token usage and unit pricing."""

    input_tokens: int
    output_tokens: int
    input_token_price_usd: Decimal
    output_token_price_usd: Decimal
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class SeatUsage:
    """Subscription-seat usage for amortized utilization accounting."""

    seat_id: str
    vendor: str
    used_seconds: int
    period_seconds: int
    period_cost_usd: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CostRecord:
    """Persisted cost/utilization unit tagged along the hierarchy."""

    cost_id: str
    engine: CostEngine
    billing_mode: BillingMode
    attribution: Attribution
    cost_usd: Decimal
    usage_units: dict[str, Decimal]
    occurred_at: datetime
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectRollup:
    """Aggregated cost for one project."""

    tenant_id: str
    project_id: str
    total_cost_usd: Decimal
    token_cost_usd: Decimal
    seat_cost_usd: Decimal
    record_count: int


@dataclass(frozen=True, slots=True)
class DimensionRollup:
    """Aggregated cost grouped by an arbitrary attribution dimension.

    ``dimension`` names the grouping (e.g. ``"model"``, ``"issue_id"``,
    ``"agent_id"``) and ``key`` is the concrete value for this bucket.
    """

    tenant_id: str
    project_id: str
    dimension: str
    key: str
    total_cost_usd: Decimal
    token_cost_usd: Decimal
    seat_cost_usd: Decimal
    record_count: int


@dataclass(frozen=True, slots=True)
class RightSizingRecommendation:
    """Seat utilization signal for idle-seat detection and right-sizing."""

    seat_id: str
    tenant_id: str
    vendor: str
    utilization_pct: Decimal
    idle: bool
    recommendation: str


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0)
