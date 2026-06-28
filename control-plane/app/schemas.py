"""HTTP request and response schemas for the control-plane API."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


OperationModeText = Literal["terminal", "socket"]


class TaskCreateRequest(BaseModel):
    task_id: str
    tenant_id: str
    project_id: str
    issue_id: str = "issue-default"
    assignee_runtime: str
    prompt: str
    credential_ref: str = "seat://local"
    operation_mode: OperationModeText
    seat_seconds: int = 0
    timeout_seconds: int | None = None
    account_id: str | None = None


class TaskDispatchResponse(BaseModel):
    task_id: str
    operation_mode: OperationModeText
    events: list[dict[str, Any]]


class AgentCreateRequest(BaseModel):
    tenant_id: str
    label: str
    vendor: str
    role: str
    workspace_id: str | None = None
    pane_id: str | None = None
    stable_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopologySaveRequest(BaseModel):
    nodes: list[dict[str, str]]
    edges: list[dict[str, str]]


class TokenCostRequest(BaseModel):
    tenant_id: str
    project_id: str
    issue_id: str
    agent_id: str
    runtime_id: str
    input_tokens: int
    output_tokens: int
    input_token_price_usd: Decimal
    output_token_price_usd: Decimal
    model: str
    trace_id: str | None = None


class SeatCostRequest(BaseModel):
    tenant_id: str
    project_id: str
    issue_id: str
    agent_id: str
    runtime_id: str
    seat_id: str
    vendor: str
    used_seconds: int
    period_seconds: int
    period_cost_usd: Decimal
    trace_id: str | None = None


class TraceEventRequest(BaseModel):
    trace_id: str
    layer: str
    signal_type: str
    tenant_id: str
    project_id: str
    issue_id: str
    agent_id: str
    runtime_id: str
    message: str
    token_burn: int = 0
    seat_seconds: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class TraceArtifactRequest(BaseModel):
    trace_id: str
    artifact_uri: str
    runtime_id: str
    agent_id: str
    content_type: str = "text/plain"
    metadata: dict[str, Any] = Field(default_factory=dict)
