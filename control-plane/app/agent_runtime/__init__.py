"""Agent runtime and sandboxed execution for the AOP control plane.

Exposes:
  * :class:`AgentRuntime`    - lifecycle manager (spawn / stop / list / message)
  * :class:`AgentSandbox`    - resource-limited isolated executor
  * Pydantic models         - :class:`AgentConfig`, :class:`AgentConstraints`,
                                :class:`ToolSpec`, plus request/response schemas
  * FastAPI router factory  - :func:`build_agent_runtime_router`

Modules:
    runtime    - lifecycle manager + FastAPI router
    sandbox    - resource-limited subprocess execution
"""

from __future__ import annotations

from .runtime import (
    AgentConfig,
    AgentConstraints,
    AgentInfo,
    AgentMessage,
    AgentRequest,
    AgentResponse,
    AgentRuntime,
    AgentRuntimeStatus,
    AgentSendMessageRequest,
    SpawnAgentRequest,
    ToolSpec,
    build_agent_runtime_router,
)
from .sandbox import (
    AgentSandbox,
    ResourceLimits,
    ResourceLimitError,
    SandboxResult,
)

__all__ = [
    # Runtime
    "AgentRuntime",
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
    "build_agent_runtime_router",
    # Sandbox
    "AgentSandbox",
    "ResourceLimits",
    "ResourceLimitError",
    "SandboxResult",
]
