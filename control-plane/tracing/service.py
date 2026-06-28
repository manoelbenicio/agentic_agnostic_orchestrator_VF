"""Trace service for propagation across product, brain, control plane, and execution."""

from __future__ import annotations

from uuid import uuid4

from .models import SessionArtifact, TraceEvent, TraceLayer, TraceSignalType
from .repository import TraceRepository


class TraceService:
    """Create and query trace timelines scoped by agent/runtime."""

    def __init__(self, repository: TraceRepository) -> None:
        self.repository = repository

    def new_trace_id(self) -> str:
        """Create a trace identifier that can be propagated L4 to L1."""
        return f"trace-{uuid4()}"

    def record(
        self,
        *,
        trace_id: str,
        layer: TraceLayer,
        signal_type: TraceSignalType,
        tenant_id: str,
        project_id: str,
        issue_id: str,
        agent_id: str,
        runtime_id: str,
        message: str,
        token_burn: int = 0,
        seat_seconds: int = 0,
        details: dict | None = None,
    ) -> TraceEvent:
        """Append an event to an existing propagated trace."""
        return self.repository.insert_event(
            TraceEvent(
                trace_id=trace_id,
                layer=layer,
                signal_type=signal_type,
                tenant_id=tenant_id,
                project_id=project_id,
                issue_id=issue_id,
                agent_id=agent_id,
                runtime_id=runtime_id,
                message=message,
                token_burn=token_burn,
                seat_seconds=seat_seconds,
                details=dict(details or {}),
            )
        )

    def record_session_artifact(
        self,
        *,
        trace_id: str,
        artifact_uri: str,
        runtime_id: str,
        agent_id: str,
        content_type: str = "text/plain",
        metadata: dict | None = None,
    ) -> SessionArtifact:
        """Attach a session recording reference to a trace."""
        return self.repository.add_session_artifact(
            SessionArtifact(
                trace_id=trace_id,
                artifact_uri=artifact_uri,
                runtime_id=runtime_id,
                agent_id=agent_id,
                content_type=content_type,
                metadata=dict(metadata or {}),
            )
        )

    def timeline(self, trace_id: str) -> list[TraceEvent]:
        return self.repository.by_trace(trace_id)

    def timeline_for_agent(self, agent_id: str) -> list[TraceEvent]:
        return self.repository.by_agent(agent_id)

    def timeline_for_runtime(self, runtime_id: str) -> list[TraceEvent]:
        return self.repository.by_runtime(runtime_id)
