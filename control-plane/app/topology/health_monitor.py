import asyncio
import logging
from enum import Enum
from typing import Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger("topology.health_monitor")

class HealthStatus(str, Enum):
    """Enumeration of possible topology agent health states."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"

class AgentHealthRecord(BaseModel):
    """Pydantic model representing the last known health state of a single agent."""
    agent_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None

class TopologyHealthMonitor:
    """
    Manages periodic health checks across all known topology agents,
    storing their statuses and calculating aggregate topology health.
    """
    
    def __init__(self):
        # In-memory mapping of agent_id -> AgentHealthRecord
        self._records: Dict[str, AgentHealthRecord] = {}
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    def register_agent(self, agent_id: str):
        """Register an agent for health monitoring if it's not already tracked."""
        if agent_id not in self._records:
            self._records[agent_id] = AgentHealthRecord(agent_id=agent_id)
            logger.debug(f"Agent {agent_id} registered for health monitoring.")

    def mark_agent_status(self, agent_id: str, status: HealthStatus, latency_ms: Optional[float] = None, error: Optional[str] = None):
        """Manually force an update to an agent's health status."""
        if agent_id not in self._records:
            self.register_agent(agent_id)
            
        record = self._records[agent_id]
        record.status = status
        record.last_check = datetime.utcnow()
        record.latency_ms = latency_ms
        record.error_message = error
        
        logger.debug(f"Agent {agent_id} status updated to {status.value} (latency: {latency_ms}ms)")

    async def _ping_agent(self, agent_id: str) -> AgentHealthRecord:
        """
        Internal stub representing an actual network ping/health-check
        to a remote topology agent node.
        """
        # In a real environment, this utilizes a gRPC check, HTTP ping, or WebSocket probe.
        await asyncio.sleep(0.02)  # Simulate network latency
        return AgentHealthRecord(
            agent_id=agent_id,
            status=HealthStatus.HEALTHY,
            latency_ms=20.5,
            last_check=datetime.utcnow()
        )

    async def check_all_agents(self):
        """
        Concurrently pings all registered agents and updates their 
        individual health records.
        """
        if not self._records:
            return
            
        logger.info(f"Running topology health check for {len(self._records)} agents...")
        
        # Dispatch concurrent ping tasks
        tasks = [self._ping_agent(agent_id) for agent_id in self._records.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for agent_id, result in zip(self._records.keys(), results):
            if isinstance(result, Exception):
                self.mark_agent_status(
                    agent_id, 
                    HealthStatus.UNREACHABLE, 
                    error=str(result)
                )
            else:
                self.mark_agent_status(
                    agent_id, 
                    result.status, 
                    latency_ms=result.latency_ms,
                    error=result.error_message
                )

    def get_topology_health_score(self) -> float:
        """
        Calculate an aggregate health score from 0.0 to 1.0 for the entire topology network.
        Weights: HEALTHY = 1.0, DEGRADED = 0.5, UNREACHABLE/UNKNOWN = 0.0.
        """
        if not self._records:
            return 1.0
            
        total_score = 0.0
        for record in self._records.values():
            if record.status == HealthStatus.HEALTHY:
                total_score += 1.0
            elif record.status == HealthStatus.DEGRADED:
                total_score += 0.5
                
        return total_score / len(self._records)

    async def _monitor_loop(self, interval_seconds: int):
        """Infinite background loop executing check_all_agents periodically."""
        logger.info(f"Topology health monitor started (interval: {interval_seconds}s)")
        
        while self._is_running:
            try:
                await self.check_all_agents()
            except Exception as e:
                logger.error(f"Critical error during topology health monitoring: {e}")
                
            # Sleep until the next interval
            await asyncio.sleep(interval_seconds)

    def start_monitoring(self, interval_seconds: int = 30):
        """Starts the background monitoring task."""
        if self._is_running:
            return
            
        self._is_running = True
        self._task = asyncio.create_task(self._monitor_loop(interval_seconds))

    def stop_monitoring(self):
        """Gracefully halts the background monitoring task."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Topology health monitor stopped.")
