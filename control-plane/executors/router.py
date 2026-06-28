"""Factory for the core ModeRouter wired to dual executors."""

from __future__ import annotations

from core import ModeRouter, OperationMode

from .socket import SocketExecutor
from .terminal import TerminalExecutor


def build_mode_router(
    terminal_executor: TerminalExecutor,
    socket_executor: SocketExecutor,
) -> ModeRouter:
    """Return a ModeRouter with terminal and socket executors registered."""
    return ModeRouter(
        {
            OperationMode.TERMINAL: terminal_executor,
            OperationMode.SOCKET: socket_executor,
        }
    )

