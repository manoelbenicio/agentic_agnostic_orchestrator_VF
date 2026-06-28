"""Wiring helpers that select real Herdr/HerdMaster adapters with graceful fallback."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from executors import HerdMasterHttpQueueClient, SocketExecutor, TerminalExecutor

from .hm_client import HerdMasterAuthClient, herdmaster_authenticated_probe
from .models import CouplingPhase, CouplingStatus


@dataclass(frozen=True, slots=True)
class CoupledExecutors:
    """Executors plus the coupling status observed during wiring."""

    terminal: TerminalExecutor
    socket: SocketExecutor
    status: CouplingStatus


def build_coupled_executors(
    *,
    fallback_terminal_adapter: Any,
    fallback_queue_client: Any,
    herdmaster_url: str = "http://127.0.0.1:8080",
    herdmaster_token: str | None = None,
    herdr_socket_path: str | Path | None = None,
    socket_poll_interval_s: float = 0.5,
    socket_max_polls: int = 1,
) -> CoupledExecutors:
    """Use each real adapter when available; gracefully degrade unavailable sides.

    When *herdmaster_token* is provided the probe and queue client carry
    an ``Authorization: Bearer <token>`` header — required by
    HerdMaster's HTTP mode.  Without a token the probe returns False
    (HerdMaster answers 401) and the fallback queue client is used
    (ADR-001 / NFR-009 graceful degradation).
    """
    errors: list[str] = []
    herdr_available = herdr_socket_probe(herdr_socket_path)

    # Use the token-aware probe when a token is provided.
    if herdmaster_token:
        herdmaster_available = herdmaster_authenticated_probe(
            herdmaster_url, token=herdmaster_token
        )
    else:
        herdmaster_available = herdmaster_http_probe(herdmaster_url)

    if herdr_available:
        terminal = _terminal_executor(fallback_terminal_adapter, herdr_socket_path, errors)
    else:
        errors.append("terminal degraded: Herdr socket unavailable")
        terminal = TerminalExecutor(adapter=fallback_terminal_adapter)

    if herdmaster_available:
        socket_exec = _socket_executor(
            fallback_queue_client,
            herdmaster_url,
            errors,
            token=herdmaster_token,
            poll_interval_s=socket_poll_interval_s,
            max_polls=socket_max_polls,
        )
    else:
        if herdmaster_token:
            errors.append("socket degraded: HerdMaster HTTP unavailable (token set but probe failed)")
        else:
            errors.append("socket degraded: HerdMaster HTTP unavailable")
        socket_exec = SocketExecutor(
            queue_client=fallback_queue_client,
            poll_interval_s=socket_poll_interval_s,
            max_polls=socket_max_polls,
        )

    phase = CouplingPhase.CONNECTED if not errors else CouplingPhase.DEGRADED
    return CoupledExecutors(
        terminal=terminal,
        socket=socket_exec,
        status=CouplingStatus(phase=phase, last_error="; ".join(errors) or None, attempts=1),
    )


def herdmaster_http_probe(base_url: str = "http://127.0.0.1:8080", timeout_s: float = 1.0) -> bool:
    """Return True when HerdMaster's HTTP status endpoint is reachable."""
    req = request.Request(f"{base_url.rstrip('/')}/status", method="GET")
    try:
        with request.urlopen(req, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, error.URLError):
        return False
    return isinstance(payload, dict) and bool(payload.get("ok", True))


def herdr_socket_probe(socket_path: str | Path | None = None, timeout_s: float = 1.0) -> bool:
    """Return True when the Herdr socket responds to a lightweight agent.list request."""
    path = Path(socket_path or os.environ.get("HERDR_SOCKET_PATH", "~/.config/herdr/herdr.sock")).expanduser()
    if not path.exists() or not hasattr(socket, "AF_UNIX"):
        return False

    request_payload = {
        "jsonrpc": "2.0",
        "id": "aop-coupling-probe",
        "method": "agent.list",
        "params": {},
    }
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout_s)
            client.connect(str(path))
            client.sendall(json.dumps(request_payload).encode("utf-8") + b"\n")
            response = _recv_json_line(client)
    except (OSError, TimeoutError, ValueError):
        return False
    return isinstance(response, dict) and "result" in response and "error" not in response


def _recv_json_line(client: socket.socket, max_bytes: int = 1_000_000) -> dict[str, Any]:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = client.recv(4096)
        if not chunk:
            raise ValueError("Herdr probe socket closed before response")
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("Herdr probe response exceeded size limit")
        if b"\n" in chunk:
            line = b"".join(chunks).split(b"\n", 1)[0]
            decoded = json.loads(line.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("Herdr probe response is not an object")
            return decoded


def _terminal_executor(
    fallback_terminal_adapter: Any,
    herdr_socket_path: str | Path | None,
    errors: list[str],
) -> TerminalExecutor:
    try:
        from herdmaster.herdr.adapter import HerdrAdapter
        from executors import HerdrRuntimeAdapter

        if not herdr_socket_probe(herdr_socket_path):
            raise RuntimeError("Herdr socket unavailable")
        return TerminalExecutor(adapter=HerdrRuntimeAdapter(HerdrAdapter(socket_path=herdr_socket_path)))
    except Exception as exc:
        errors.append(f"terminal degraded: {exc}")
        return TerminalExecutor(adapter=fallback_terminal_adapter)


def _socket_executor(
    fallback_queue_client: Any,
    herdmaster_url: str,
    errors: list[str],
    *,
    token: str | None = None,
    poll_interval_s: float = 0.5,
    max_polls: int = 1,
) -> SocketExecutor:
    try:
        if token:
            # Token present → use the authenticated client that injects
            # Authorization: Bearer <token> into every request.
            client: Any = HerdMasterAuthClient(
                base_url=herdmaster_url, token=token
            )
        else:
            # No token → use the original unauthenticated client.
            client = HerdMasterHttpQueueClient(base_url=herdmaster_url)
        return SocketExecutor(
            queue_client=client,
            poll_interval_s=poll_interval_s,
            max_polls=max_polls,
        )
    except Exception as exc:
        errors.append(f"socket degraded: {exc}")
        return SocketExecutor(
            queue_client=fallback_queue_client,
            poll_interval_s=poll_interval_s,
            max_polls=max_polls,
        )
