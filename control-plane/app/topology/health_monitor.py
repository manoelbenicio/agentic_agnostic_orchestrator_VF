import asyncio
import logging
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Callable, Awaitable, List
from fastapi import APIRouter, BackgroundTasks

# Safely import the WebSocket manager we generated recently to push live state updates
try:
    from app.websocket.manager import manager as ws_manager
except ImportError:
    # Synthetic mock preventing boot crashes if executed out of order
    class MockManager:
        async def broadcast(self, msg: dict, room: str = None): pass
    ws_manager = MockManager()

logger = logging.getLogger("topology.health_monitor")


class Status(str, Enum):
    """Normalized structural state enumeration."""
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class HealthMonitor:
    """
    Advanced asynchronous daemon managing dynamic component tracking, 
    cascading failure heuristics, and live WebSocket alert broadcasting.
    """
    def __init__(self):
        # Operational graph: component_name -> async function yielding (bool, latency_ms)
        self.components: Dict[str, Callable[[], Awaitable[tuple[bool, float]]]] = {}
        
        # State tracker matrix
        self.state: Dict[str, Dict[str, Any]] = {}
        
        # Historical sliding window for cascade heuristics
        self.failure_history: List[Dict[str, Any]] = []

    def track_component(self, name: str, check_fn: Callable[[], Awaitable[tuple[bool, float]]]):
        """
        Dynamically registers an asynchronous probe function into the topology matrix.
        Allows for infinite extensibility of new adapters, databases, and microservices.
        """
        self.components[name] = check_fn
        self.state[name] = {
            "status": Status.UP,
            "latency_ms": 0.0,
            "last_check": datetime.utcnow().isoformat(),
            "failures_in_row": 0
        }
        logger.info(f"Registered topology component target: {name}")

    async def _evaluate_single(self, name: str, check_fn: Callable) -> tuple[str, bool, float]:
        """Safely executes an isolated probe wrapping it in strict operational timeouts."""
        try:
            # Enforce a strict 5.0s timeout to prevent thread locks from cascading
            is_healthy, latency = await asyncio.wait_for(check_fn(), timeout=5.0)
            return name, is_healthy, latency
        except asyncio.TimeoutError:
            return name, False, 5000.0
        except Exception as e:
            logger.debug(f"Topology Probe Hard-Failure on '{name}': {e}")
            return name, False, -1.0

    async def run_health_sweep(self):
        """
        Executes concurrent network probes against all tracked components.
        Calculates state deltas and broadcasts real-time anomaly alerts natively.
        """
        if not self.components:
            return
            
        logger.debug(f"Initiating full topology sweep across {len(self.components)} targets...")
        
        # Execute sweeps concurrently scaling perfectly regardless of node count
        tasks = [self._evaluate_single(name, fn) for name, fn in self.components.items()]
        results = await asyncio.gather(*tasks)
        
        newly_failed = []

        for name, is_healthy, latency in results:
            old_status = self.state[name]["status"]
            
            # Algorithmic State Determination
            if not is_healthy or latency == -1.0:
                new_status = Status.DOWN
                self.state[name]["failures_in_row"] += 1
            elif latency > 1000.0:  # Degradation boundary threshold
                new_status = Status.DEGRADED
                self.state[name]["failures_in_row"] = 0
            else:
                new_status = Status.UP
                self.state[name]["failures_in_row"] = 0

            # Commit State Updates
            self.state[name]["status"] = new_status
            self.state[name]["latency_ms"] = round(latency, 2)
            self.state[name]["last_check"] = datetime.utcnow().isoformat()

            # Handle State Transitions via WebSocket Pipeline
            if old_status != new_status:
                logger.warning(f"Topology Delta: '{name}' transitioned {old_status.value} -> {new_status.value}")
                
                # Push exclusively to clients opted into the 'health' room
                await ws_manager.broadcast(
                    payload={
                        "event": "topology_state_transition", 
                        "component": name, 
                        "status": new_status.value, 
                        "latency_ms": latency
                    },
                    room="health"
                )
                
            if new_status == Status.DOWN:
                newly_failed.append(name)
                
        # Heuristic Cascade Detection
        if newly_failed:
            self.failure_history.append({"time": datetime.utcnow(), "components": newly_failed})
            await self.detect_cascading_failures()

    async def detect_cascading_failures(self):
        """
        Analyzes historical node drops. If an abnormal density of components 
        fail simultaneously, trigger emergency systemic alerts.
        """
        now = datetime.utcnow()
        # Filter sliding window to the last 60 seconds
        recent_failures = [f for f in self.failure_history if (now - f["time"]).total_seconds() < 60]
        
        # Aggregate unique failing entities
        failing_components = set()
        for f in recent_failures:
            failing_components.update(f["components"])
            
        # Threshold Logic: 3 independent systems failing is a systemic cascade
        if len(failing_components) >= 3:
            logger.error(f"🚨 CASCADING FAILURE DETECTED: {list(failing_components)}")
            await self._trigger_alert("CRITICAL_CASCADE", list(failing_components))
            
        # Memory cleanup
        self.failure_history = recent_failures

    async def _trigger_alert(self, severity: str, details: Any):
        """Dispatches automated operational alerts globally."""
        alert_payload = {
            "severity": severity,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
        # Push immediately to live dashboards
        await ws_manager.broadcast({"event": "critical_alert", "data": alert_payload}, room="health")

    def get_health_summary(self) -> Dict[str, Any]:
        """Provides static state materializations for HTTP polling endpoints."""
        up = sum(1 for c in self.state.values() if c["status"] == Status.UP)
        down = sum(1 for c in self.state.values() if c["status"] == Status.DOWN)
        degraded = sum(1 for c in self.state.values() if c["status"] == Status.DEGRADED)
        
        return {
            "total_components": len(self.components),
            "summary": {"UP": up, "DEGRADED": degraded, "DOWN": down},
            "components": self.state
        }


# --- API Routes ---

monitor = HealthMonitor()
router = APIRouter(prefix="/topology/health", tags=["topology", "health"])

@router.get("")
async def get_topology_health():
    """
    GET /topology/health
    Retrieves the materialized real-time health matrix of all tracked topology targets.
    """
    return monitor.get_health_summary()


@router.post("/sweep")
async def trigger_manual_sweep(background_tasks: BackgroundTasks):
    """
    POST /topology/health/sweep
    Initiates an asynchronous health sweep sequence immediately.
    """
    background_tasks.add_task(monitor.run_health_sweep)
    return {"message": "Background topology sweep dispatched successfully."}
