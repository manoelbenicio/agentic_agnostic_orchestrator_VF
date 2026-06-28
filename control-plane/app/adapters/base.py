from abc import ABC, abstractmethod
from typing import Any, Dict

class NativeAgentAdapter(ABC):
    """Standard interface for native agent adapters."""

    @abstractmethod
    async def start(self) -> None:
        """Start the agent runtime/session."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the agent runtime/session."""
        pass

    @abstractmethod
    async def status(self) -> Dict[str, Any]:
        """Return the current status of the agent."""
        pass

    @abstractmethod
    async def send_task(self, task: Dict[str, Any]) -> Any:
        """Send a task to the agent for execution."""
        pass
