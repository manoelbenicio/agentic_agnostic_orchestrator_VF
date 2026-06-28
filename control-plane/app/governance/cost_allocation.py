"""Cost allocation, aggregation, and budget alerting.

Records per-tenant / per-project / per-agent cost events, supports
aggregation by ``tenant``, ``project``, ``agent``, ``model``, or ``day``,
emits :class:`BudgetAlert` records when configured thresholds are
exceeded, and exposes a FastAPI router with
``GET /governance/costs?groupBy=...``.

Storage is in-memory by default (process-local). The :class:`CostAggregator`
is thread-safe; if you need persistence, swap the ``_events`` list for a
Postgres-backed implementation that satisfies the same interface.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Literal, Sequence
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

GroupBy = Literal["tenant", "project", "agent", "model", "day"]

_VALID_GROUP_BY: tuple[GroupBy, ...] = ("tenant", "project", "agent", "model", "day")

_TWO_PLACES = Decimal("0.01")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal | float | int | str) -> Decimal:
    """Coerce a numeric value to a 2-dp :class:`Decimal`."""
    if isinstance(value, Decimal):
        return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostEvent:
    """One cost-incurring event recorded against an attribution tuple.

    ``cost_usd`` is the authoritative cost; tokens + model are kept for
    audit and re-pricing scenarios. All Decimal arithmetic goes through
    :class:`decimal.Decimal` to avoid float drift.
    """

    tenant_id: str
    project_id: str
    agent_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    timestamp: datetime = field(default_factory=_utcnow)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    runtime_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate / normalize at construction so downstream code can trust shape.
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        object.__setattr__(self, "cost_usd", _money(self.cost_usd))


@dataclass(frozen=True, slots=True)
class CostBucket:
    """Aggregated cost totals for a single grouping key."""

    group_by: GroupBy
    key: str
    total_cost_usd: Decimal
    token_cost_usd: Decimal
    event_count: int
    input_tokens: int
    output_tokens: int
    window_start: datetime
    window_end: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_by": self.group_by,
            "key": self.key,
            "total_cost_usd": str(self.total_cost_usd),
            "token_cost_usd": str(self.token_cost_usd),
            "event_count": self.event_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BudgetAlert:
    """Notification that a cost threshold was exceeded for a grouping key."""

    group_by: GroupBy
    key: str
    threshold_usd: Decimal
    observed_usd: Decimal
    exceeded_by_usd: Decimal
    triggered_at: datetime
    window_start: datetime
    window_end: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_by": self.group_by,
            "key": self.key,
            "threshold_usd": str(self.threshold_usd),
            "observed_usd": str(self.observed_usd),
            "exceeded_by_usd": str(self.exceeded_by_usd),
            "triggered_at": self.triggered_at.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BudgetThreshold:
    """Threshold config: group by ``dimension`` over ``window``; alert if ``limit`` exceeded."""

    dimension: GroupBy
    limit_usd: Decimal
    window: timedelta = field(default_factory=lambda: timedelta(days=30))


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class CostAggregator:
    """Thread-safe in-memory aggregator with budget alerting.

    Args:
        thresholds: Optional iterable of :class:`BudgetThreshold` to enforce.
    """

    def __init__(self, thresholds: Iterable[BudgetThreshold] | None = None) -> None:
        self._events: list[CostEvent] = []
        self._alerts: list[BudgetAlert] = []
        self._thresholds: dict[GroupBy, list[BudgetThreshold]] = {
            "tenant": [],
            "project": [],
            "agent": [],
            "model": [],
            "day": [],
        }
        for t in thresholds or ():
            self._thresholds[t.dimension].append(t)
        self._lock = threading.RLock()

    # ----------------------------------------------------------- thresholds
    def set_threshold(self, threshold: BudgetThreshold) -> None:
        with self._lock:
            self._thresholds[threshold.dimension].append(threshold)

    def thresholds_for(self, dimension: GroupBy) -> Sequence[BudgetThreshold]:
        return tuple(self._thresholds.get(dimension, ()))

    # ------------------------------------------------------------- record
    def record(self, event: CostEvent) -> list[BudgetAlert]:
        """Record ``event`` and return any budget alerts it triggered."""
        with self._lock:
            self._events.append(event)
            triggered: list[BudgetAlert] = []
            for dimension in _VALID_GROUP_BY:
                for threshold in self._thresholds.get(dimension, ()):
                    alert = self._maybe_alert(event, dimension, threshold)
                    if alert is not None:
                        self._alerts.append(alert)
                        triggered.append(alert)
            return triggered

    def record_many(self, events: Iterable[CostEvent]) -> list[BudgetAlert]:
        triggered: list[BudgetAlert] = []
        for event in events:
            triggered.extend(self.record(event))
        return triggered

    # ------------------------------------------------------------- query
    def events(
        self,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[CostEvent]:
        with self._lock:
            snapshot = list(self._events)
        results: list[CostEvent] = []
        for event in snapshot:
            if tenant_id is not None and event.tenant_id != tenant_id:
                continue
            if project_id is not None and event.project_id != project_id:
                continue
            if agent_id is not None and event.agent_id != agent_id:
                continue
            if model is not None and event.model != model:
                continue
            if start is not None and event.timestamp < start:
                continue
            if end is not None and event.timestamp > end:
                continue
            results.append(event)
            if limit is not None and len(results) >= limit:
                break
        return results

    # ----------------------------------------------------------- aggregate
    def aggregate(
        self,
        group_by: GroupBy,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CostBucket]:
        """Group recorded events by ``group_by`` and return totals."""
        if group_by not in _VALID_GROUP_BY:
            raise ValueError(
                f"unsupported group_by: {group_by!r} "
                f"(valid: {', '.join(_VALID_GROUP_BY)})"
            )

        with self._lock:
            snapshot = list(self._events)

        filtered: list[CostEvent] = []
        for event in snapshot:
            if tenant_id is not None and event.tenant_id != tenant_id:
                continue
            if project_id is not None and event.project_id != project_id:
                continue
            if agent_id is not None and event.agent_id != agent_id:
                continue
            if model is not None and event.model != model:
                continue
            if start is not None and event.timestamp < start:
                continue
            if end is not None and event.timestamp > end:
                continue
            filtered.append(event)

        if not filtered:
            window_start = start or _utcnow()
            window_end = end or _utcnow()
            return [
                CostBucket(
                    group_by=group_by,
                    key="<none>",
                    total_cost_usd=_money(0),
                    token_cost_usd=_money(0),
                    event_count=0,
                    input_tokens=0,
                    output_tokens=0,
                    window_start=window_start,
                    window_end=window_end,
                )
            ]

        window_start = min(e.timestamp for e in filtered)
        window_end = max(e.timestamp for e in filtered)

        buckets: dict[str, dict[str, Any]] = {}
        for event in filtered:
            key = _key_for(event, group_by)
            slot = buckets.setdefault(
                key,
                {
                    "total": _money(0),
                    "token": _money(0),
                    "count": 0,
                    "input": 0,
                    "output": 0,
                },
            )
            slot["total"] += event.cost_usd
            slot["token"] += event.cost_usd  # all current events are token-based
            slot["count"] += 1
            slot["input"] += event.input_tokens
            slot["output"] += event.output_tokens

        return [
            CostBucket(
                group_by=group_by,
                key=key,
                total_cost_usd=_money(slot["total"]),
                token_cost_usd=_money(slot["token"]),
                event_count=slot["count"],
                input_tokens=slot["input"],
                output_tokens=slot["output"],
                window_start=window_start,
                window_end=window_end,
            )
            for key, slot in sorted(buckets.items())
        ]

    # ----------------------------------------------------------- budgets
    def check_budgets(self, *, now: datetime | None = None) -> list[BudgetAlert]:
        """Re-evaluate every configured threshold against the current state.

        Returns all alerts (including previously-emitted ones within the
        same window) so callers can re-render dashboards.
        """
        with self._lock:
            snapshot = list(self._events)
        current = now or _utcnow()
        alerts: list[BudgetAlert] = []
        for dimension in _VALID_GROUP_BY:
            for threshold in self._thresholds.get(dimension, ()):
                window_start = current - threshold.window
                bucket_by_key: dict[str, dict[str, Any]] = {}
                for event in snapshot:
                    if event.timestamp < window_start or event.timestamp > current:
                        continue
                    key = _key_for(event, dimension)
                    slot = bucket_by_key.setdefault(
                        key,
                        {"total": _money(0), "start": event.timestamp, "end": event.timestamp},
                    )
                    slot["total"] += event.cost_usd
                    if event.timestamp < slot["start"]:
                        slot["start"] = event.timestamp
                    if event.timestamp > slot["end"]:
                        slot["end"] = event.timestamp
                for key, slot in bucket_by_key.items():
                    if slot["total"] > threshold.limit_usd:
                        alerts.append(
                            BudgetAlert(
                                group_by=dimension,
                                key=key,
                                threshold_usd=_money(threshold.limit_usd),
                                observed_usd=_money(slot["total"]),
                                exceeded_by_usd=_money(slot["total"] - threshold.limit_usd),
                                triggered_at=current,
                                window_start=slot["start"],
                                window_end=slot["end"],
                            )
                        )
        return alerts

    def alerts(self) -> list[BudgetAlert]:
        with self._lock:
            return list(self._alerts)

    # -------------------------------------------------------------- totals
    def total_cost(self) -> Decimal:
        with self._lock:
            return _money(sum((e.cost_usd for e in self._events), _money(0)))

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    # ----------------------------------------------------------- helpers
    def _maybe_alert(
        self,
        event: CostEvent,
        dimension: GroupBy,
        threshold: BudgetThreshold,
    ) -> BudgetAlert | None:
        window_start = event.timestamp - threshold.window
        key = _key_for(event, dimension)
        total = _money(0)
        earliest = event.timestamp
        latest = event.timestamp
        for prior in self._events:
            if prior.timestamp < window_start or prior.timestamp > event.timestamp:
                continue
            if _key_for(prior, dimension) != key:
                continue
            total += prior.cost_usd
            if prior.timestamp < earliest:
                earliest = prior.timestamp
            if prior.timestamp > latest:
                latest = prior.timestamp
        if total > threshold.limit_usd:
            return BudgetAlert(
                group_by=dimension,
                key=key,
                threshold_usd=_money(threshold.limit_usd),
                observed_usd=_money(total),
                exceeded_by_usd=_money(total - threshold.limit_usd),
                triggered_at=event.timestamp,
                window_start=earliest,
                window_end=latest,
            )
        return None


def _key_for(event: CostEvent, group_by: GroupBy) -> str:
    if group_by == "tenant":
        return event.tenant_id
    if group_by == "project":
        return f"{event.tenant_id}/{event.project_id}"
    if group_by == "agent":
        return event.agent_id
    if group_by == "model":
        return event.model
    if group_by == "day":
        return event.timestamp.astimezone(timezone.utc).date().isoformat()
    raise ValueError(f"unsupported group_by: {group_by!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------


def build_governance_costs_router(
    aggregator: CostAggregator | None = None,
) -> APIRouter:
    """Build a router exposing ``GET /governance/costs``.

    Query parameters:
        groupBy: one of ``tenant``, ``project``, ``agent``, ``model``, ``day``.
        tenant_id, project_id, agent_id, model: optional filters.
        start, end: ISO-8601 timestamps; inclusive window.
        format: ``json`` (default) or ``csv``.
    """
    router = APIRouter()
    state_holder: dict[str, CostAggregator] = {"agg": aggregator or CostAggregator()}

    @router.get("/governance/costs")
    def get_governance_costs(
        groupBy: GroupBy = Query("tenant", description="Aggregation dimension"),
        tenant_id: str | None = Query(None),
        project_id: str | None = Query(None),
        agent_id: str | None = Query(None),
        model: str | None = Query(None),
        start: str | None = Query(None, description="ISO-8601 lower bound (inclusive)"),
        end: str | None = Query(None, description="ISO-8601 upper bound (inclusive)"),
        limit: int | None = Query(None, ge=1, le=10_000),
        format: Literal["json", "csv"] = Query("json"),
    ) -> Any:
        agg = state_holder["agg"]
        if groupBy not in _VALID_GROUP_BY:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "unsupported_group_by",
                    "valid": list(_VALID_GROUP_BY),
                    "received": groupBy,
                },
            )
        start_dt = _parse_iso(start, "start")
        end_dt = _parse_iso(end, "end")
        if start_dt and end_dt and start_dt > end_dt:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_range", "reason": "start must be <= end"},
            )

        buckets = agg.aggregate(
            group_by=groupBy,
            tenant_id=tenant_id,
            project_id=project_id,
            agent_id=agent_id,
            model=model,
            start=start_dt,
            end=end_dt,
        )
        if limit is not None:
            buckets = buckets[:limit]

        if format == "csv":
            return _buckets_to_csv(buckets)

        return {
            "group_by": groupBy,
            "filters": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "agent_id": agent_id,
                "model": model,
                "start": start_dt.isoformat() if start_dt else None,
                "end": end_dt.isoformat() if end_dt else None,
            },
            "total_cost_usd": str(sum((b.total_cost_usd for b in buckets), _money(0))),
            "bucket_count": len(buckets),
            "buckets": [bucket.to_dict() for bucket in buckets],
        }

    @router.get("/governance/costs/alerts")
    def list_alerts() -> dict[str, Any]:
        agg = state_holder["agg"]
        return {"alerts": [alert.to_dict() for alert in agg.alerts()]}

    @router.post("/governance/costs")
    def record_cost_event(payload: dict[str, Any]) -> dict[str, Any]:
        agg = state_holder["agg"]
        try:
            event = _event_from_payload(payload)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail={"code": "invalid_event", "reason": str(exc)}) from exc
        triggered = agg.record(event)
        return {
            "event_id": event.event_id,
            "cost_usd": str(event.cost_usd),
            "alerts": [alert.to_dict() for alert in triggered],
        }

    return router


def _parse_iso(value: str | None, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_timestamp", "field": field_name, "reason": str(exc)},
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _event_from_payload(payload: dict[str, Any]) -> CostEvent:
    required = ("tenant_id", "project_id", "agent_id", "model", "input_tokens", "output_tokens", "cost_usd")
    missing = [field for field in required if field not in payload]
    if missing:
        raise KeyError(f"missing fields: {', '.join(missing)}")
    timestamp = payload.get("timestamp")
    if isinstance(timestamp, str):
        timestamp = _parse_iso(timestamp, "timestamp")
    return CostEvent(
        tenant_id=str(payload["tenant_id"]),
        project_id=str(payload["project_id"]),
        agent_id=str(payload["agent_id"]),
        model=str(payload["model"]),
        input_tokens=int(payload["input_tokens"]),
        output_tokens=int(payload["output_tokens"]),
        cost_usd=payload["cost_usd"],
        timestamp=timestamp or _utcnow(),
        runtime_id=payload.get("runtime_id"),
        trace_id=payload.get("trace_id"),
        metadata=dict(payload.get("metadata") or {}),
    )


def _buckets_to_csv(buckets: Sequence[CostBucket]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "group_by",
            "key",
            "total_cost_usd",
            "token_cost_usd",
            "event_count",
            "input_tokens",
            "output_tokens",
            "window_start",
            "window_end",
        ]
    )
    for bucket in buckets:
        writer.writerow(
            [
                bucket.group_by,
                bucket.key,
                str(bucket.total_cost_usd),
                str(bucket.token_cost_usd),
                bucket.event_count,
                bucket.input_tokens,
                bucket.output_tokens,
                bucket.window_start.isoformat(),
                bucket.window_end.isoformat(),
            ]
        )
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "CostEvent",
    "CostBucket",
    "BudgetAlert",
    "BudgetThreshold",
    "CostAggregator",
    "GroupBy",
    "build_governance_costs_router",
]


_ = (asdict, json, timedelta, date, logger)
