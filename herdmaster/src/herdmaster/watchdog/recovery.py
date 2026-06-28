"""Recovery workflow for unhealthy HerdMaster agents."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any
import uuid

from herdmaster.bus.messages import Message, MessageType
from herdmaster.config import WatchdogConfig
from herdmaster.db.repositories import AgentRepo
from herdmaster.herdr.adapter import HerdrAdapter, HerdrError


class RecoveryManager:
    """Kill, respawn, wait, and replay work for unhealthy agents.

    The manager deliberately depends on injected collaborators for bus publishing
    and task replay. It does not import dispatch internals and it never starts or
    kills processes directly; all terminal interaction goes through HerdrAdapter.
    """

    def __init__(
        self,
        adapter: HerdrAdapter,
        agent_repo: AgentRepo,
        config: WatchdogConfig,
        *,
        bus_publisher: Any | None = None,
        task_replayer: Any | None = None,
        command_resolver: Any | None = None,
        system_agent_id: str = "watchdog",
        wait_timeout_s: int = 60,
        manage_health_events: bool = True,
    ) -> None:
        self.adapter = adapter
        self.agent_repo = agent_repo
        self.config = config
        self.bus_publisher = bus_publisher
        self.task_replayer = task_replayer
        self.command_resolver = command_resolver
        self.system_agent_id = system_agent_id
        self.wait_timeout_s = wait_timeout_s
        self._failures: dict[str, int] = {}
        self.manage_health_events = manage_health_events

    def failure_count(self, agent_id: str) -> int:
        """Return consecutive recovery failures for an agent."""

        return self._failures.get(agent_id, 0)

    def reset(self, agent_id: str) -> None:
        """Clear consecutive recovery failure accounting for an agent."""

        self._failures.pop(agent_id, None)

    async def recover(
        self,
        agent_id: str,
        *,
        pane_id: str | None = None,
        command: str | None = None,
    ) -> bool:
        """Run the recovery procedure and emit escalation after retry exhaustion."""

        agent = self.agent_repo.get(agent_id) or {}
        resolved_pane = pane_id or _string(agent.get("herdr_pane"))
        resolved_command = command or await self._resolve_command(agent_id, agent)

        try:
            if not resolved_pane:
                raise HerdrError(f"cannot recover {agent_id}: missing Herdr pane")
            if not resolved_command:
                raise HerdrError(f"cannot recover {agent_id}: missing spawn command")

            self._record_health(
                agent_id,
                "recovering",
                details={"event": "recovery_attempt", "pane_id": resolved_pane},
            )
            await self._kill_hung_process(agent_id, resolved_pane)
            await self._respawn_agent(agent_id, resolved_pane, resolved_command)
            await self.adapter.agent_wait(agent_id, "idle", timeout=self.wait_timeout_s)
            await self._replay_last_task(agent_id)
            self.reset(agent_id)
            self._record_health(
                agent_id,
                "healthy",
                details={"event": "recovery_success", "pane_id": resolved_pane},
            )
            return True
        except Exception as exc:
            print(f"RECOVERY EXCEPTION: {exc}")
            failures = self._failures.get(agent_id, 0) + 1
            self._failures[agent_id] = failures
            self._record_health(
                agent_id,
                "unhealthy",
                details={
                    "event": "recovery_failed",
                    "failures": failures,
                    "error": str(exc),
                },
            )
            if failures >= self.config.max_retries:
                await self._emit_alert(agent_id, failures, str(exc))
            return False

    def _record_health(self, agent_id: str, health: str, *, details: object | None = None) -> None:
        if not self.manage_health_events:
            return
        current = self.agent_repo.get(agent_id) or {}
        if _string(current.get("health")) == health:
            return
        self.agent_repo.update_health(agent_id, health, details=details)

    async def _kill_hung_process(self, agent_id: str, pane_id: str) -> None:
        del agent_id
        # Send Ctrl-C via pane_send to interrupt the hung process without destroying the pane.
        await self.adapter.pane_send(pane_id, "\x03")

    async def _respawn_agent(self, agent_id: str, pane_id: str, command: str) -> None:
        for method_name in ("agent_start", "start_agent"):
            method = getattr(self.adapter, method_name, None)
            if method is None:
                continue
            await _maybe_await(method(agent_id, command))
            return

        await self.adapter.spawn_agent(pane_id, command)

    async def _resolve_command(self, agent_id: str, agent: dict[str, object]) -> str | None:
        if self.command_resolver is not None:
            try:
                value = self.command_resolver(agent_id, agent)
            except TypeError:
                value = self.command_resolver(agent_id)
            return _string(await _maybe_await(value)) or None

        for key in ("spawn_command", "command", "herdr_command"):
            value = _string(agent.get(key))
            if value:
                return value
        return None

    async def _replay_last_task(self, agent_id: str) -> None:
        if self.task_replayer is None:
            raise RuntimeError("cannot replay task: no task replayer was injected")

        for method_name in (
            "replay_last_task",
            "replay_last",
            "retry_last_task",
            "inject_last_task",
            "requeue_last_task",
        ):
            method = getattr(self.task_replayer, method_name, None)
            if method is None:
                continue
            await _maybe_await(method(agent_id))
            return

        if callable(self.task_replayer):
            await _maybe_await(self.task_replayer(agent_id))
            return

        raise RuntimeError("task replayer exposes no supported public replay method")

    async def _emit_alert(self, agent_id: str, failures: int, error: str) -> None:
        await _publish(
            self.bus_publisher,
            _message(
                MessageType.ALERT,
                self.system_agent_id,
                "broadcast",
                {
                    "agent_id": agent_id,
                    "health": "unhealthy",
                    "event": "escalation",
                    "failures": failures,
                    "max_retries": self.config.max_retries,
                    "error": error,
                },
            ),
        )


async def _publish(publisher: Any | None, message: Message) -> None:
    if publisher is None:
        return
    publish = getattr(publisher, "publish", None)
    if publish is not None:
        await _maybe_await(publish(message))
        return
    if callable(publisher):
        await _maybe_await(publisher(message))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _message(message_type: MessageType, from_agent: str, to: str, payload: dict[str, object]) -> Message:
    return Message(
        id=f"{int(datetime.now(UTC).timestamp() * 1000):013d}-{uuid.uuid4()}",
        type=message_type,
        from_agent=from_agent,
        to=to,
        correlation_id=None,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        payload=payload,
    )


def _string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""
