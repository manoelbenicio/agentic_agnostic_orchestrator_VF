import logging
from typing import Any, Dict
from .base import NativeAgentAdapter

logger = logging.getLogger(__name__)

class CodexAdapter(NativeAgentAdapter):
    """Adapter for Codex agent."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._running = False

    async def start(self) -> None:
        logger.info("Starting Codex adapter")
        self._running = True

    async def stop(self) -> None:
        logger.info("Stopping Codex adapter")
        self._running = False

    async def status(self) -> Dict[str, Any]:
        return {
            "agent": "codex",
            "status": "running" if self._running else "stopped"
        }

    async def send_task(self, task: Dict[str, Any]) -> Any:
        if not self._running:
            raise RuntimeError("Codex adapter is not running")
        logger.info(f"Codex received task: {task}")
        return {"result": "codex_task_acknowledged", "task_id": task.get("id")}
