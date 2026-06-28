import logging
from typing import Any, Dict
from .base import NativeAgentAdapter

logger = logging.getLogger(__name__)

class AntigravityAdapter(NativeAgentAdapter):
    """Adapter for Antigravity agent."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._running = False

    async def start(self) -> None:
        logger.info("Starting Antigravity adapter")
        self._running = True

    async def stop(self) -> None:
        logger.info("Stopping Antigravity adapter")
        self._running = False

    async def status(self) -> Dict[str, Any]:
        return {
            "agent": "antigravity",
            "status": "running" if self._running else "stopped"
        }

    async def send_task(self, task: Dict[str, Any]) -> Any:
        if not self._running:
            raise RuntimeError("Antigravity adapter is not running")
        logger.info(f"Antigravity received task: {task}")
        return {"result": "antigravity_task_acknowledged", "task_id": task.get("id")}
