from __future__ import annotations

from tracing import TraceLayer, TraceService, TraceSignalType, TracingMetricsExporter


def _record(service: TraceService, *, trace_id: str, agent_id: str, runtime_id: str, layer, signal, message, token_burn=0, seat_seconds=0):
    return service.record(
        trace_id=trace_id,
        layer=layer,
        signal_type=signal,
        tenant_id="tenant-a",
        project_id="project-a",
        issue_id="issue-1",
        agent_id=agent_id,
        runtime_id=runtime_id,
        message=message,
        token_burn=token_burn,
        seat_seconds=seat_seconds,
    )


def test_trace_id_propagates_across_l4_to_l1(repo):
    service = TraceService(repo)
    trace_id = service.new_trace_id()

    _record(service, trace_id=trace_id, agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L4_PRODUCT, signal=TraceSignalType.LIFECYCLE, message="issue opened")
    _record(service, trace_id=trace_id, agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L3_ORCHESTRATION, signal=TraceSignalType.TOOL_CALL, message="plan created")
    _record(service, trace_id=trace_id, agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L2_CONTROL_PLANE, signal=TraceSignalType.STATE, message="task claimed")
    _record(service, trace_id=trace_id, agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.CHAIN_OF_THOUGHT, message="runtime step")

    timeline = service.timeline(trace_id)

    assert [event.layer for event in timeline] == [
        TraceLayer.L4_PRODUCT,
        TraceLayer.L3_ORCHESTRATION,
        TraceLayer.L2_CONTROL_PLANE,
        TraceLayer.L1_EXECUTION,
    ]
    assert {event.trace_id for event in timeline} == {trace_id}


def test_trace_is_filterable_by_agent_and_runtime(repo):
    service = TraceService(repo)
    trace_id = "trace-filter"
    _record(service, trace_id=trace_id, agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.BURN, message="agent a burn", token_burn=10)
    _record(service, trace_id=trace_id, agent_id="agent-b", runtime_id="runtime-b", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.BURN, message="agent b burn", token_burn=20)
    _record(service, trace_id=trace_id, agent_id="agent-a", runtime_id="runtime-c", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.TOOL_CALL, message="agent a other runtime")

    agent_timeline = service.timeline_for_agent("agent-a")
    runtime_timeline = service.timeline_for_runtime("runtime-b")

    assert [event.agent_id for event in agent_timeline] == ["agent-a", "agent-a"]
    assert [event.runtime_id for event in runtime_timeline] == ["runtime-b"]
    assert runtime_timeline[0].message == "agent b burn"


def test_session_recording_reference_is_queryable(repo):
    service = TraceService(repo)

    artifact = service.record_session_artifact(
        trace_id="trace-session",
        artifact_uri="s3://sessions/trace-session.pty",
        runtime_id="runtime-a",
        agent_id="agent-a",
        metadata={"sha256": "abc123"},
    )

    stored = repo.artifacts_for_trace("trace-session")
    assert stored == [artifact]
    assert stored[0].metadata["sha256"] == "abc123"


def test_tracing_prometheus_metrics_are_per_agent_and_runtime(repo):
    service = TraceService(repo)
    _record(service, trace_id="trace-metrics", agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.BURN, message="burn", token_burn=7, seat_seconds=30)
    _record(service, trace_id="trace-metrics", agent_id="agent-a", runtime_id="runtime-a", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.BURN, message="burn", token_burn=8, seat_seconds=15)
    _record(service, trace_id="trace-metrics", agent_id="agent-b", runtime_id="runtime-b", layer=TraceLayer.L1_EXECUTION, signal=TraceSignalType.BURN, message="burn", token_burn=3, seat_seconds=5)

    metrics = TracingMetricsExporter(repo).burn_metrics()

    assert 'aop_trace_token_burn_total{agent_id="agent-a",runtime_id="runtime-a"} 15' in metrics
    assert 'aop_trace_seat_seconds_total{agent_id="agent-a",runtime_id="runtime-a"} 45' in metrics
    assert 'agent_id="agent-b",runtime_id="runtime-b"' in metrics
