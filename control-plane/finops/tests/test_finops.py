from __future__ import annotations

from decimal import Decimal

from finops import (
    Attribution,
    BillingMode,
    CostEngine,
    FinOpsEngine,
    FinOpsMetricsExporter,
    SeatUsage,
    TokenUsage,
)


def _attribution(project_id: str = "project-a") -> Attribution:
    return Attribution(
        tenant_id="tenant-a",
        project_id=project_id,
        issue_id="issue-17",
        agent_id="agent-1",
        runtime_id="runtime-1",
    )


def test_token_cost_is_calculated_and_persisted(repo):
    engine = FinOpsEngine(repo)

    record = engine.record_token_usage(
        _attribution(),
        TokenUsage(
            input_tokens=100,
            output_tokens=25,
            input_token_price_usd=Decimal("0.00001"),
            output_token_price_usd=Decimal("0.00003"),
            model="api-model",
        ),
        billing_mode=BillingMode.PAY_AS_YOU_GO,
        trace_id="trace-token",
    )

    assert record.engine == CostEngine.TOKEN
    assert record.billing_mode == BillingMode.PAY_AS_YOU_GO
    assert record.cost_usd == Decimal("0.00175000")
    assert record.usage_units["total_tokens"] == Decimal("125")
    assert record.trace_id == "trace-token"


def test_seat_cost_is_calculated_for_monthly_subscription(repo):
    engine = FinOpsEngine(repo)

    record = engine.record_seat_usage(
        _attribution(),
        SeatUsage(
            seat_id="seat-codex-1",
            vendor="codex",
            used_seconds=3600,
            period_seconds=7200,
            period_cost_usd=Decimal("40.00"),
        ),
        billing_mode=BillingMode.MONTHLY,
        trace_id="trace-seat",
    )

    assert record.engine == CostEngine.SEAT
    assert record.billing_mode == BillingMode.MONTHLY
    assert record.cost_usd == Decimal("20.00000000")
    assert record.usage_units["seat_seconds"] == Decimal("3600")
    assert record.metadata["seat_id"] == "seat-codex-1"


def test_project_rollup_sums_token_and_seat_cost(repo):
    engine = FinOpsEngine(repo)
    attr = _attribution(project_id="project-rollup")
    engine.record_token_usage(
        attr,
        TokenUsage(10, 10, Decimal("0.01"), Decimal("0.02"), "api-model"),
    )
    engine.record_seat_usage(
        attr,
        SeatUsage("seat-1", "codex", 1800, 3600, Decimal("30.00")),
    )

    rollup = repo.rollup_project("tenant-a", "project-rollup")

    assert rollup.record_count == 2
    assert rollup.token_cost_usd == Decimal("0.30000000")
    assert rollup.seat_cost_usd == Decimal("15.00000000")
    assert rollup.total_cost_usd == Decimal("15.30000000")


def test_idle_seat_detection_and_right_sizing(repo):
    engine = FinOpsEngine(repo)
    engine.record_seat_usage(
        _attribution(),
        SeatUsage("seat-idle", "codex", 60, 3600, Decimal("20.00")),
    )
    engine.record_seat_usage(
        _attribution(),
        SeatUsage("seat-active", "codex", 1800, 3600, Decimal("20.00")),
    )

    recommendations = {item.seat_id: item for item in repo.idle_seat_recommendations(tenant_id="tenant-a")}

    assert recommendations["seat-idle"].idle is True
    assert recommendations["seat-idle"].recommendation == "release_or_downsize"
    assert recommendations["seat-active"].idle is False
    assert recommendations["seat-active"].recommendation == "keep"


def test_finops_prometheus_metrics_reuse_existing_scrape_model(repo):
    engine = FinOpsEngine(repo)
    engine.record_token_usage(
        _attribution(project_id="project-metrics"),
        TokenUsage(10, 0, Decimal("0.10"), Decimal("0.10"), "api-model"),
    )

    metrics = FinOpsMetricsExporter(repo).project_metrics(
        tenant_id="tenant-a",
        project_id="project-metrics",
    )

    assert "aop_finops_project_cost_usd" in metrics
    assert 'engine="token"' in metrics
    assert "aop_finops_project_cost_records" in metrics
