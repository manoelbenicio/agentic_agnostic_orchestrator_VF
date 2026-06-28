"""Models for end-to-end tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class TraceLayer(StrEnum):
    """Platform layer traversed by one trace."""

    L4_PRODUCT = "l4_product"
    L3_ORCHESTRATION = "l3_orchestration"
    L2_CONTROL_PLANE = "l2_control_plane"
    L1_EXECUTION = "l1_execution"


class TraceSignalType(StrEnum):
    """Type of data captured in the trace timeline."""

    LIFECYCLE = "lifecycle"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TOOL_CALL = "tool_call"
    STATE = "state"
    BURN = "burn"
    ERROR = "error"
    AUDIT = "audit"


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """Timeline event scoped by trace, agent, and runtime."""

    trace_id: str
    layer: TraceLayer
    signal_type: TraceSignalType
    tenant_id: str
    project_id: str
    issue_id: str
    agent_id: str
    runtime_id: str
    message: str
    event_id: str = field(default_factory=lambda: f"trace-event-{uuid4()}")
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    token_burn: int = 0
    seat_seconds: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionArtifact:
    """Reference to a PTY/session recording artifact."""

    trace_id: str
    artifact_uri: str
    runtime_id: str
    agent_id: str
    content_type: str = "text/plain"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
