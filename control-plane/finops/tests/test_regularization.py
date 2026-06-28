"""Tests for the FinOps regularization: multidimensional rollups, dynamic
exporter, and the executor->engine cost bridge."""

from __future__ import annotations

from decimal import Decimal

from finops import (
    Attribution,
    FinOpsEngine,
    FinOpsMetricsExporter,
    TokenUsage,
    record_event_costs,
)


def _attr(project_id: str = "project-dim", agent_id: str = "agent-1", issue_id: str = "issue-1") -> Attribution:
    return Attribution(
        tenant_id="tenant-dim",
        project_id=project_id,
        issue_id=issue_id,
        agent_id=agent_id,
        runtime_id="runtime-1",
    )


def _token(model: str, in_tokens: int = 100, out_tokens: int = 50) -> TokenUsage:
    return TokenUsage(
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        input_token_price_usd=Decimal("0.00001"),
        output_token_price_usd=Decimal("0.00002"),
        model=model,
    )


def test_rollup_by_model_groups_metadata(repo):
    engine = FinOpsEngine(repo)
    engine.record_token_usage(_attr(), _token("gpt-x"))
    engine.record_token_usage(_attr(), _token("gpt-x"))
    engine.record_token_usage(_attr(), _token("gemini-y"))

    buckets = {b.key: b for b in repo.rollup_by_dimension("tenant-dim", "project-dim", "model")}

    assert set(buckets) == {"gpt-x", "gemini-y"}
    assert buckets["gpt-x"].record_count == 2
    assert buckets["gemini-y"].record_count == 1
    assert buckets["gpt-x"].total_cost_usd > Decimal("0")


def test_rollup_by_agent_dimension(repo):
    engine = FinOpsEngine(repo)
    engine.record_token_usage(_attr(agent_id="agent-a"), _token("m1"))
    engine.record_token_usage(_attr(agent_id="agent-b"), _token("m1"))

    buckets = {b.key: b for b in repo.rollup_by_dimension("tenant-dim", "project-dim", "agent_id")}
    assert set(buckets) == {"agent-a", "agent-b"}


def test_rollup_rejects_unknown_dimension(repo):
    try:
        repo.rollup_by_dimension("tenant-dim", "project-dim", "drop_table")
    except ValueError as exc:
        assert "unsupported rollup dimension" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown dimension")


def test_rollup_rejects_sql_injection_dimension(repo):
    engine = FinOpsEngine(repo)
    engine.record_token_usage(_attr(), _token("safe-model"))

    malicious = "agent_id); DROP TABLE finops_cost_records; --"
    try:
        repo.rollup_by_dimension("tenant-dim", "project-dim", malicious)
    except ValueError as exc:
        assert "unsupported rollup dimension" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for SQL injection dimension")

    assert repo.rollup_project("tenant-dim", "project-dim").record_count == 1


def test_list_projects_returns_distinct_pairs(repo):
    engine = FinOpsEngine(repo)
    engine.record_token_usage(_attr(project_id="proj-1"), _token("m1"))
    engine.record_token_usage(_attr(project_id="proj-2"), _token("m1"))

    pairs = repo.list_projects()
    assert ("tenant-dim", "proj-1") in pairs
    assert ("tenant-dim", "proj-2") in pairs


def test_dynamic_exporter_emits_model_series(repo):
    engine = FinOpsEngine(repo)
    engine.record_token_usage(_attr(), _token("gpt-x"))
    engine.record_token_usage(_attr(), _token("gemini-y"))

    text = FinOpsMetricsExporter(repo).all_project_metrics()

    assert "aop_finops_project_cost_usd" in text
    assert "aop_finops_model_cost_usd" in text
    assert "aop_finops_vendor_cost_usd" in text
    assert 'model="gpt-x"' in text
    assert 'model="gemini-y"' in text
    assert 'tenant_id="tenant-dim"' in text


def test_bridge_records_token_cost_from_event_details(repo):
    engine = FinOpsEngine(repo)
    details = {
        "queue": {"state": "done"},
        "finops": {
            "token": {
                "input_tokens": 1000,
                "output_tokens": 500,
                "input_token_price_usd": "0.000003",
                "output_token_price_usd": "0.000015",
                "model": "gpt-bridge",
            }
        },
    }
    records = record_event_costs(
        engine,
        tenant_id="tenant-dim",
        project_id="project-bridge",
        issue_id="issue-1",
        agent_id="agent-1",
        runtime_id="runtime-1",
        trace_id="trace-bridge",
        details=details,
    )
    assert len(records) == 1
    rollup = repo.rollup_project("tenant-dim", "project-bridge")
    assert rollup.record_count == 1
    assert rollup.total_cost_usd > Decimal("0")


def test_bridge_is_noop_without_finops_payload(repo):
    engine = FinOpsEngine(repo)
    records = record_event_costs(
        engine,
        tenant_id="tenant-dim",
        project_id="project-empty",
        issue_id="issue-1",
        agent_id="agent-1",
        runtime_id="runtime-1",
        trace_id=None,
        details={"queue": {"state": "done"}},
    )
    assert records == []
    assert repo.rollup_project("tenant-dim", "project-empty").record_count == 0
