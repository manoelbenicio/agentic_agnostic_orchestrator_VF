"""Agent lifecycle manager + FastAPI router.

:class:`AgentRuntime` owns a thread-safe registry of agents. Each agent is
described by an immutable :class:`AgentConfig` and tracked via a mutable
:class:`AgentInfo`. The runtime is the single source of truth for active
agents; it can be queried through the FastAPI router exposed by
:func:`build_agent_runtime_router` or directly via the Python API.

The runtime is intentionally agnostic about the underlying LLM. Callers
can register a ``responder`` callable (or set ``responder=`` per agent) that
produces an :class:`AgentMessage` reply when ``send_message_to_agent`` is
called. When no responder is registered, the runtime appends the inbound
message and returns a stub reply so the surface area remains testable.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Sequence

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums + Pydantic models
# ---------------------------------------------------------------------------


class AgentRuntimeStatus(str, Enum):
    """Lifecycle states for a managed agent."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


class ToolSpec(BaseModel):
    """Declarative description of a tool the agent may invoke."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=4096)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentConstraints(BaseModel):
    """Operational limits applied to an agent at spawn time."""

    model_config = ConfigDict(extra="forbid")

    max_turns: int = Field(default=10, ge=1, le=1000)
    max_tool_calls: int = Field(default=50, ge=0, le=10_000)
    timeout_s: float = Field(default=60.0, gt=0, le=86_400)
    max_output_tokens: int = Field(default=4096, ge=1, le=128_000)
    allowed_tools: list[str] | None = None


class AgentConfig(BaseModel):
    """Immutable specification for a managed agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    system_prompt: str = Field(min_length=1, max_length=32_000)
    tools: list[ToolSpec] = Field(default_factory=tuple)  # type: ignore[assignment]
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("tools")
    @classmethod
    def _unique_tool_names(cls, value: Sequence[ToolSpec]) -> list[ToolSpec]:
        names = [tool.name for tool in value]
        if len(names) != len(set(names)):
            raise ValueError("tool names must be unique")
        return list(value)


# ---------------------------------------------------------------------------
# Mutable runtime state
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentInfo:
    """Mutable bookkeeping record kept for each managed agent."""

    agent_id: str
    config: AgentConfig
    status: AgentRuntimeStatus = AgentRuntimeStatus.PENDING
    spawned_at: datetime = field(default_factory=_utcnow)
    last_activity_at: datetime = field(default_factory=_utcnow)
    stopped_at: datetime | None = None
    message_count: int = 0
    error: str | None = None
    responder: Callable[["AgentMessage"], "AgentMessage"] | None = None
    messages: list["AgentMessage"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "config": self.config.model_dump(),
            "status": self.status.value,
            "spawned_at": self.spawned_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "message_count": self.message_count,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """A single message flowing through an agent's conversation."""

    agent_id: str
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: datetime = field(default_factory=_utcnow)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "agent_id": self.agent_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# HTTP request/response schemas
# ---------------------------------------------------------------------------


class SpawnAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: AgentConfig


class AgentSendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=128_000)
    role: str = Field(default="user")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        allowed = {"user", "system", "tool"}
        if value not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}")
        return value


class AgentRequest(BaseModel):
    """Response payload for ``GET /agents/runtime/{id}/status``."""

    model_config = ConfigDict(extra="forbid")

    agent: dict[str, Any]


class AgentResponse(BaseModel):
    """Response payload for spawn / stop / list endpoints."""

    model_config = ConfigDict(extra="forbid")

    agent: dict[str, Any] | None = None
    agents: list[dict[str, Any]] | None = None
    message: dict[str, Any] | None = None
    stopped: bool | None = None
    agent_id: str | None = None


# ---------------------------------------------------------------------------
# Runtime manager
# ---------------------------------------------------------------------------


_DEFAULT_RESPONDER: Callable[[AgentMessage], AgentMessage] | None = None


def _stub_responder(msg: AgentMessage) -> AgentMessage:
    """Fallback responder used when no callable is registered.

    Echoes the inbound content as the assistant reply. Suitable for tests
    and for environments where the actual LLM adapter is wired in later.
    """
    return AgentMessage(
        agent_id=msg.agent_id,
        role="assistant",
        content=f"[echo] {msg.content}",
        metadata={"responder": "stub"},
    )


class AgentRuntime:
    """Thread-safe registry of agent configs and their lifecycle state."""

    def __init__(
        self,
        *,
        default_responder: Callable[[AgentMessage], AgentMessage] | None = None,
        active_statuses: Iterable[AgentRuntimeStatus] | None = None,
    ) -> None:
        # NOTE: explicit `is not None` because AgentRuntimeStatus.PENDING is
        # defined and would otherwise be considered truthy by `or`.
        self._default_responder = (
            default_responder if default_responder is not None else _stub_responder
        )
        self._agents: dict[str, AgentInfo] = {}
        self._lock = threading.RLock()
        self._active_statuses: frozenset[AgentRuntimeStatus] = frozenset(
            active_statuses
            if active_statuses is not None
            else (AgentRuntimeStatus.PENDING, AgentRuntimeStatus.RUNNING)
        )

    # ----------------------------------------------------------- lifecycle
    def spawn_agent(
        self,
        config: AgentConfig,
        *,
        responder: Callable[[AgentMessage], AgentMessage] | None = None,
        agent_id: str | None = None,
    ) -> AgentInfo:
        """Register a new agent from ``config`` and return its info record.

        Raises :class:`ValueError` if ``agent_id`` is supplied and already
        in use.
        """
        with self._lock:
            new_id = agent_id or uuid.uuid4().hex
            if new_id in self._agents:
                raise ValueError(f"agent_id {new_id!r} already exists")
            info = AgentInfo(
                agent_id=new_id,
                config=config,
                status=AgentRuntimeStatus.PENDING,
                responder=responder,
            )
            self._agents[new_id] = info

        # Transition to RUNNING outside the lock so callers can observe PENDING
        # if they race; the status flip is the last thing we do.
        self._transition(info, AgentRuntimeStatus.RUNNING)
        return info

    def stop_agent(self, agent_id: str, *, reason: str | None = None) -> bool:
        """Stop the agent with id ``agent_id``.

        Returns ``True`` if the agent was running and is now stopped,
        ``False`` if it was already terminal. Raises :class:`KeyError`
        when the id is unknown.
        """
        with self._lock:
            info = self._agents.get(agent_id)
            if info is None:
                raise KeyError(agent_id)
            if info.status in {AgentRuntimeStatus.STOPPED, AgentRuntimeStatus.COMPLETED, AgentRuntimeStatus.FAILED, AgentRuntimeStatus.ERROR}:
                return False
            self._transition_unlocked(info, AgentRuntimeStatus.STOPPED)
            if reason:
                info.error = reason
            return True

    def get_agent_status(self, agent_id: str) -> AgentInfo:
        with self._lock:
            info = self._agents.get(agent_id)
            if info is None:
                raise KeyError(agent_id)
            return info

    def list_active_agents(self) -> list[AgentInfo]:
        with self._lock:
            return [
                info
                for info in self._agents.values()
                if info.status in self._active_statuses
            ]

    def list_agents(self) -> list[AgentInfo]:
        with self._lock:
            return list(self._agents.values())

    # ------------------------------------------------------------ messaging
    def send_message_to_agent(self, agent_id: str, msg: AgentMessage) -> AgentMessage:
        """Deliver ``msg`` to ``agent_id`` and return the agent's reply.

        The inbound message is recorded on the agent's history. The reply
        is produced by the agent's ``responder`` (if set) or the runtime's
        ``default_responder``. A stopped / failed agent raises
        :class:`RuntimeError`.
        """
        with self._lock:
            info = self._agents.get(agent_id)
            if info is None:
                raise KeyError(agent_id)
            if info.status in {
                AgentRuntimeStatus.STOPPED,
                AgentRuntimeStatus.FAILED,
                AgentRuntimeStatus.ERROR,
            }:
                raise RuntimeError(f"agent {agent_id} is not accepting messages (status={info.status.value})")
            info.messages.append(msg)
            info.message_count += 1
            info.last_activity_at = _utcnow()
            responder = info.responder if info.responder is not None else self._default_responder

        # Run the responder outside the lock to avoid head-of-line blocking.
        assert responder is not None
        try:
            reply = responder(msg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("responder failed for agent %s", agent_id)
            with self._lock:
                info = self._agents.get(agent_id)
                if info is not None:
                    info.error = f"responder error: {exc}"
                    self._transition_unlocked(info, AgentRuntimeStatus.ERROR)
            raise

        with self._lock:
            info = self._agents.get(agent_id)
            if info is not None:
                info.messages.append(reply)
                info.message_count += 1
                info.last_activity_at = _utcnow()
        return reply

    # --------------------------------------------------------------- internals
    def _transition(self, info: AgentInfo, new_status: AgentRuntimeStatus) -> None:
        with self._lock:
            self._transition_unlocked(info, new_status)

    def _transition_unlocked(self, info: AgentInfo, new_status: AgentRuntimeStatus) -> None:
        info.status = new_status
        info.last_activity_at = _utcnow()
        if new_status in {
            AgentRuntimeStatus.STOPPED,
            AgentRuntimeStatus.COMPLETED,
            AgentRuntimeStatus.FAILED,
            AgentRuntimeStatus.ERROR,
        }:
            info.stopped_at = info.last_activity_at


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------


def build_agent_runtime_router(runtime: AgentRuntime | None = None) -> APIRouter:
    """Build a router exposing the agent runtime under ``/agents/runtime``."""
    router = APIRouter(prefix="/agents/runtime")
    state: dict[str, AgentRuntime] = {"rt": runtime if runtime is not None else AgentRuntime()}

    def _rt() -> AgentRuntime:
        return state["rt"]

    @router.post("/spawn", response_model=AgentResponse)
    def spawn_agent(request: SpawnAgentRequest) -> AgentResponse:
        try:
            info = _rt().spawn_agent(request.config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "spawn_failed", "reason": str(exc)}) from exc
        return AgentResponse(agent=info.to_dict())

    @router.get("", response_model=AgentResponse)
    def list_agents(active_only: bool = Query(True)) -> AgentResponse:
        rt = _rt()
        agents = rt.list_active_agents() if active_only else rt.list_agents()
        return AgentResponse(agents=[info.to_dict() for info in agents])

    @router.get("/{agent_id}/status", response_model=AgentRequest)
    def get_status(agent_id: str = Path(min_length=1, max_length=128)) -> AgentRequest:
        try:
            info = _rt().get_agent_status(agent_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "agent_not_found", "agent_id": agent_id}) from exc
        return AgentRequest(agent=info.to_dict())

    @router.post("/{agent_id}/stop", response_model=AgentResponse)
    def stop_agent(
        agent_id: str = Path(min_length=1, max_length=128),
        reason: str | None = Query(None),
    ) -> AgentResponse:
        try:
            stopped = _rt().stop_agent(agent_id, reason=reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "agent_not_found", "agent_id": agent_id}) from exc
        return AgentResponse(stopped=stopped, agent_id=agent_id)

    @router.post("/{agent_id}/messages", response_model=AgentResponse)
    def send_message(
        request: AgentSendMessageRequest,
        agent_id: str = Path(min_length=1, max_length=128),
    ) -> AgentResponse:
        rt = _rt()
        try:
            inbound = AgentMessage(agent_id=agent_id, role=request.role, content=request.content, metadata=request.metadata)
            reply = rt.send_message_to_agent(agent_id, inbound)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "agent_not_found", "agent_id": agent_id}) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail={"code": "agent_unavailable", "reason": str(exc)}) from exc
        return AgentResponse(message=reply.to_dict())

    return router


__all__ = [
    "AgentRuntimeStatus",
    "AgentConfig",
    "AgentConstraints",
    "ToolSpec",
    "AgentInfo",
    "AgentMessage",
    "AgentRequest",
    "AgentResponse",
    "AgentSendMessageRequest",
    "SpawnAgentRequest",
    "AgentRuntime",
    "build_agent_runtime_router",
]
