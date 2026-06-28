"""Dynamic agent registry for the AOP control plane."""

from .models import AgentRecord, AgentStatus, DiscoveredPane, EnrollmentDecision, PaneRef
from .propagation import (
    AllowlistPropagationHook,
    CompositePropagationHook,
    ObservabilityPropagationHook,
    PropagationEvent,
    PropagationHook,
    RecordingPropagationHook,
    SchedulerPropagationHook,
    AclPropagationHook,
)
from .repository import AgentRegistryRepository
from .schema import connect, init_schema
from .service import AgentRegistryService

__all__ = [
    "AclPropagationHook",
    "AgentRecord",
    "AgentRegistryRepository",
    "AgentRegistryService",
    "AgentStatus",
    "AllowlistPropagationHook",
    "CompositePropagationHook",
    "DiscoveredPane",
    "EnrollmentDecision",
    "ObservabilityPropagationHook",
    "PaneRef",
    "PropagationEvent",
    "PropagationHook",
    "RecordingPropagationHook",
    "SchedulerPropagationHook",
    "connect",
    "init_schema",
]
