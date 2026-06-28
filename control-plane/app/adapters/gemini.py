import logging
from typing import Any, Dict
from .base import NativeAgentAdapter

logger = logging.getLogger(__name__)

class GeminiAdapter(NativeAgentAdapter):
    """Adapter for Gemini agent."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._running = False

    async def start(self) -> None:
        logger.info("Starting Gemini adapter")
        self._running = True

    async def stop(self) -> None:
        logger.info("Stopping Gemini adapter")
        self._running = False

    async def status(self) -> Dict[str, Any]:
        return {
            "agent": "gemini",
            "status": "running" if self._running else "stopped"
        }

    async def send_task(self, task: Dict[str, Any]) -> Any:
        if not self._running:
            raise RuntimeError("Gemini adapter is not running")
        logger.info(f"Gemini received task: {task}")
        return {"result": "gemini_task_acknowledged", "task_id": task.get("id")}
