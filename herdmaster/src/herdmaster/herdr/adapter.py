"""Async Herdr Socket API adapter.

This module is the sole Herdr I/O boundary for HerdMaster. It talks to the
official Herdr newline-delimited JSON Socket API.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import inspect
import json
import os
from pathlib import Path
from typing import Any

from .parser import HerdrAgent, HerdrPane, parse_agent_list, parse_pane_list


class HerdrError(RuntimeError):
    """Raised when Herdr fails, times out, or returns invalid output."""


StatusCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class HerdrAdapter:
    """Small async wrapper around Herdr's raw Socket API."""

    def __init__(
        self,
        socket_path: str | Path | None = None,
        timeout: float = 30.0,
        *,
        herdr_bin: str | None = None,
    ) -> None:
        # Accepted as a no-op compatibility keyword for older callers/tests.
        del herdr_bin
        self.socket_path = _resolve_socket_path(socket_path)
        self.timeout = timeout
        self._next_id = 0

    async def agent_list(self, *, timeout: float | None = None) -> list[HerdrAgent]:
        response = await self._request("agent.list", timeout=timeout)
        try:
            return parse_agent_list(json.dumps(_parser_payload(response)))
        except ValueError as exc:
            raise HerdrError(str(exc)) from exc

    async def pane_read(self, pane_id: str, *, timeout: float | None = None) -> str:
        response = await self._request(
            "pane.read",
            {"pane_id": pane_id, "source": "recent", "lines": 2000},
            timeout=timeout,
        )
        result = _result(response)
        read_obj = result.get("read", {})
        if isinstance(read_obj, dict):
            text = read_obj.get("text", "")
        else:
            text = read_obj
        return _string(text or result.get("output") or result.get("text"))

    async def pane_send(
        self,
        pane_id: str,
        text: str,
        *,
        confirm: bool = True,
        timeout: float | None = None,
    ) -> None:
        if not confirm:
            raise HerdrError("pane_send requires confirm=True because it injects raw keystrokes")
        await self._request(
            "pane.send_text",
            {"pane_id": pane_id, "text": text},
            timeout=timeout,
        )

    async def agent_wait(
        self,
        agent_id: str,
        state: str = "idle",
        timeout: float | None = 30.0,
        *,
        command_timeout: float | None = None,
    ) -> bool:
        wait_timeout = command_timeout if command_timeout is not None else timeout
        agents = await self.agent_list(timeout=wait_timeout)
        target = _agent_by_id_or_pane(agents, agent_id)
        pane_id = target.pane_id if target is not None and target.pane_id else agent_id
        if target is not None and target.state == state:
            return True

        async def wait_for_event() -> bool:
            reader, writer = await self._connect(wait_timeout)
            request = self._build_request(
                "events.subscribe",
                {
                    "subscriptions": [
                        {
                            "type": "pane.agent_status_changed",
                            "pane_id": pane_id,
                            "agent_status": state,
                        }
                    ]
                },
            )
            try:
                await self._send(writer, request)
                await self._read_response(reader, request["id"], wait_timeout)
                while True:
                    event = await self._read_json_line(reader, wait_timeout)
                    if _event_matches_agent_status(event, pane_id, state):
                        return True
            finally:
                writer.close()
                await writer.wait_closed()

        try:
            return await asyncio.wait_for(wait_for_event(), timeout=wait_timeout)
        except asyncio.TimeoutError as exc:
            raise HerdrError(
                f"timed out waiting for agent {agent_id!r} to reach {state!r}"
            ) from exc

    async def pane_list(self, *, timeout: float | None = None) -> list[HerdrPane]:
        response = await self._request("pane.list", timeout=timeout)
        try:
            return parse_pane_list(json.dumps(_parser_payload(response)))
        except ValueError as exc:
            raise HerdrError(str(exc)) from exc

    async def workspace_list(self, *, timeout: float | None = None) -> object:
        response = await self._request("workspace.list", timeout=timeout)
        return response.get("result", response)

    async def spawn_agent(
        self,
        pane_id: str,
        command: str,
        *,
        timeout: float | None = None,
    ) -> None:
        if not command.endswith("\n"):
            command += "\n"
        await self._request(
            "pane.send_text",
            {"pane_id": pane_id, "text": command},
            timeout=timeout,
        )

    async def pane_close(self, pane_id: str, *, timeout: float | None = None) -> None:
        """Close (destroy) a Herdr pane.

        Uses the ``pane.close`` Socket API method to cleanly close a pane,
        killing any running process inside it.
        """
        await self._request(
            "pane.close",
            {"pane_id": pane_id},
            timeout=timeout,
        )

    async def subscribe_status(self, callback: StatusCallback) -> None:
        """Subscribe to Herdr agent-status events until cancelled or disconnected."""
        agents = await self.agent_list()
        subscriptions = [
            {"type": "pane.agent_status_changed", "pane_id": a.pane_id}
            for a in agents if a.pane_id
        ]
        if not subscriptions:
            await asyncio.sleep(self.timeout or 5.0)
            return

        reader, writer = await self._connect(None)
        request = self._build_request(
            "events.subscribe",
            {"subscriptions": subscriptions},
        )
        try:
            await self._send(writer, request)
            await self._read_response(reader, request["id"], self.timeout)
            while True:
                event = await self._read_json_line(reader, None)
                result = callback(event)
                if inspect.isawaitable(result):
                    await result
        finally:
            writer.close()
            await writer.wait_closed()

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        effective_timeout = self.timeout if timeout is None else timeout
        backoff_delays = (0.5, 1.0, 2.0)
        last_exc: Exception | None = None
        for attempt in range(len(backoff_delays) + 1):
            try:
                reader, writer = await self._connect(effective_timeout)
            except HerdrError as exc:
                last_exc = exc
                if attempt < len(backoff_delays):
                    await asyncio.sleep(backoff_delays[attempt])
                    continue
                raise HerdrError(
                    f"failed to connect to Herdr after {attempt + 1} attempts: {exc}"
                ) from exc
            request = self._build_request(method, params)
            try:
                await self._send(writer, request)
                return await self._read_response(reader, request["id"], effective_timeout)
            finally:
                writer.close()
                await writer.wait_closed()
        # Unreachable, but satisfies type checkers.
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    async def _connect(
        self,
        timeout: float | None,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        connect = asyncio.open_unix_connection(str(self.socket_path))
        try:
            if timeout is None:
                return await connect
            return await asyncio.wait_for(connect, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise HerdrError(f"timed out connecting to Herdr socket {self.socket_path}") from exc
        except OSError as exc:
            raise HerdrError(f"failed to connect to Herdr socket {self.socket_path}: {exc}") from exc

    async def _send(self, writer: asyncio.StreamWriter, request: dict[str, Any]) -> None:
        line = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        writer.write(line)
        try:
            await writer.drain()
        except (ConnectionError, OSError) as exc:
            raise HerdrError(f"failed to write Herdr request {request['id']}: {exc}") from exc

    async def _read_response(
        self,
        reader: asyncio.StreamReader,
        request_id: str,
        timeout: float | None,
    ) -> dict[str, Any]:
        response = await self._read_json_line(reader, timeout)
        response_id = response.get("id")
        if response_id != request_id:
            raise HerdrError(f"Herdr response id mismatch: expected {request_id!r}, got {response_id!r}")
        if "error" in response:
            raise _error_from_response(response)
        if "result" not in response:
            raise HerdrError(f"Herdr response missing result for {request_id!r}")
        return response

    async def _read_json_line(
        self,
        reader: asyncio.StreamReader,
        timeout: float | None,
    ) -> dict[str, Any]:
        try:
            if timeout is None:
                line = await reader.readline()
            else:
                line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise HerdrError("timed out waiting for Herdr response") from exc

        if not line:
            raise HerdrError("Herdr socket closed without a response")
        try:
            response = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HerdrError(f"invalid Herdr JSON: {exc}") from exc
        if not isinstance(response, dict):
            raise HerdrError("invalid Herdr response: expected JSON object")
        return response

    def _build_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._next_id += 1
        return {
            "id": f"herdmaster-{self._next_id}",
            "method": method,
            "params": params or {},
        }


def _resolve_socket_path(socket_path: str | Path | None) -> Path:
    if socket_path is not None:
        return Path(socket_path).expanduser()

    env_socket = os.environ.get("HERDR_SOCKET_PATH")
    if env_socket:
        return Path(env_socket).expanduser()

    session = os.environ.get("HERDR_SESSION")
    if session:
        return Path("~/.config/herdr/sessions").expanduser() / session / "herdr.sock"

    return Path("~/.config/herdr/herdr.sock").expanduser()


def _result(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    if not isinstance(result, dict):
        raise HerdrError("invalid Herdr response: result must be an object")
    return result


def _parser_payload(response: dict[str, Any]) -> dict[str, Any]:
    return {"result": _result(response)}


def _error_from_response(response: dict[str, Any]) -> HerdrError:
    error = response.get("error")
    if not isinstance(error, dict):
        return HerdrError(f"Herdr error: {error!r}")
    code = _string(error.get("code")) or "error"
    message = _string(error.get("message")) or "Herdr request failed"
    return HerdrError(f"{code}: {message}")


def _agent_by_id_or_pane(agents: list[HerdrAgent], value: str) -> HerdrAgent | None:
    for agent in agents:
        if agent.id == value or agent.pane_id == value:
            return agent
    return None


def _event_matches_agent_status(event: dict[str, Any], pane_id: str, state: str) -> bool:
    payload = event.get("event") if isinstance(event.get("event"), dict) else event
    result = payload.get("result")
    if isinstance(result, dict):
        payload = result.get("event") if isinstance(result.get("event"), dict) else result
    data = payload.get("data")
    if isinstance(data, dict):
        payload = {**data, "type": payload.get("event") or data.get("type")}

    event_type = _string(payload.get("type") or payload.get("event_type"))
    event_pane_id = _string(payload.get("pane_id") or payload.get("target") or payload.get("id"))
    event_state = _string(
        payload.get("agent_status")
        or payload.get("status")
        or payload.get("state")
    )
    return (
        event_type == "pane.agent_status_changed"
        and event_pane_id == pane_id
        and event_state == state
    )


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""
