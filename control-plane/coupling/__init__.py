"""Soft coupling between AOP, Herdr, and HerdMaster."""

from .hm_client import HerdMasterAuthClient, herdmaster_authenticated_probe
from .manager import CouplingManager
from .models import CouplingPhase, CouplingStatus
from .wiring import CoupledExecutors, build_coupled_executors

__all__ = [
    "CoupledExecutors",
    "CouplingManager",
    "CouplingPhase",
    "CouplingStatus",
    "HerdMasterAuthClient",
    "build_coupled_executors",
    "herdmaster_authenticated_probe",
]
