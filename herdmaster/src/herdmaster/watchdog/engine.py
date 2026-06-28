"""Tri-layer watchdog engine for HerdMaster agents."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
import fnmatch
import inspect
import logging
from typing import Any
import uuid

from herdmaster.bus.messages import Message, MessageType
from herdmaster.config import AclConfig, WatchdogConfig
from herdmaster.db.repositories import AgentRepo
from herdmaster.herdr.adapter import HerdrAdapter, HerdrError
from herdmaster.herdr.parser import output_hash

from .recovery import RecoveryManager

log = logging.getLogger(__name__)


_HEALTHY = "healthy"
_SUSPECT = "suspect"
_UNHEALTHY = "unhealthy"
_RECOVERING = "recovering"
_ACTIVE_STATES = {"working", "blocked", "unknown"}
_RESTING_STATES = {"idle", "done"}


@dataclass(slots=True)
class _Monitor:
    agent_id: str
    pane_id: str = ""
    state: str = "unknown"
    health: str = _HEALTHY
    last_seen_at: float = 0.0
    last_progress_at: float = 0.0
    last_hash_at: float = 0.0
    last_output_hash: str | None = None
    recovery_task: asyncio.Task[None] | None = None


def _role_for_agent(
    agent_id: str,
    acl_config: AclConfig | None,
    existing: dict[str, object] | None = None,
) -> str:
    """Resolve the persisted agent role, preferring explicit ACL role membership."""
    if acl_config is not None:
        for role in acl_config.roles:
            for pattern in role.agents:
                if pattern == "*" or fnmatch.fnmatchcase(agent_id, pattern):
                    return role.name
    if existing is not None:
        return str(existing.get("role") or "worker")
    return "worker"


class WatchdogEngine:
    """Async tri-layer health monitor.

    Layer 1 consumes an adapter-provided state-change stream when available.
    Layer 2 polls Herdr agent state and pane output. Layer 3 compares output
    hashes on a slower interval to detect frozen terminals. Polling remains active
    even if the primary event source is missing or fails.
    """

    def __init__(
        self,
        adapter: HerdrAdapter,
        agent_repo: AgentRepo,
        config: WatchdogConfig,
        *,
        bus_publisher: Any | None = None,
        recovery_manager: RecoveryManager | None = None,
        system_agent_id: str = "watchdog",
        command_resolver: Any | None = None,
        task_replayer: Any | None = None,
        acl_config: AclConfig | None = None,
        now: Any | None = None,
    ) -> None:
        self.adapter = adapter
        self.agent_repo = agent_repo
        self.config = config
        self.bus_publisher = bus_publisher
        self.recovery_manager = recovery_manager
        self.system_agent_id = system_agent_id
        self.command_resolver = command_resolver
        self.task_replayer = task_replayer
        self.acl_config = acl_config
        self._now = now
        self._monitors: dict[str, _Monitor] = {}
        self._task: asyncio.Task[None] | None = None
        self._primary_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self.primary_available = False
        self.primary_failed = False
        self._primary_reconnect_attempts = 0
        self._RECONNECT_BACKOFF_S = (5, 10, 30)

    async def start(self) -> None:
        """Start the watchdog as an asyncio background task."""

        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        """Stop the watchdog and any active primary listener."""

        self._stopped.set()
        tasks = [task for task in (self._primary_task, self._task) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run(self) -> None:
        """Run until stopped or cancelled."""

        self._primary_task = asyncio.create_task(self._run_primary())
        try:
            while not self._stopped.is_set():
                await self.poll_once()
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=self.config.poll_interval_s
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            if self._primary_task is not None:
                self._primary_task.cancel()
                try:
                    await self._primary_task
                except asyncio.CancelledError:
                    pass

    async def poll_once(self) -> None:
        """Execute one secondary polling and tertiary hash evaluation pass."""

        now = self._seconds()
        try:
            agents = await self.adapter.agent_list()
        except HerdrError:
            await self._evaluate_all(now)
            return

        for agent in agents:
            self._sync_agent(agent)
            await self.observe_agent(
                agent.id,
                state=agent.state,
                pane_id=agent.pane_id,
                layer="secondary",
                now=now,
            )

            monitor = self._monitors[agent.id]
            if agent.pane_id and (
                monitor.last_output_hash is None
                or now - monitor.last_hash_at >= self.config.tertiary_hash_interval_s
            ):
                await self._check_output_hash(agent.id, agent.pane_id, now)

        await self._evaluate_all(now)

    def _sync_agent(self, agent: Any) -> None:
        # ── Allowlist guard ──────────────────────────────────────────────────
        # When agent_allowlist is configured, only registered agent IDs may be
        # synced to the DB. Any Herdr pane not in the list (e.g. auto-registered
        # phantom panes from workspace syncs) is silently dropped here — it
        # never reaches the DB, the dispatcher, or the health monitor.
        if self.config.agent_allowlist and agent.id not in self.config.agent_allowlist:
            log.debug(
                "allowlist: ignoring unregistered Herdr pane %r (not in agent_allowlist)",
                agent.id,
            )
            return
        existing = self.agent_repo.get(agent.id)
        role = _role_for_agent(agent.id, self.acl_config, existing)
        health = str(existing.get("health") or _HEALTHY) if existing is not None else _HEALTHY
        # Preserve existing label if the DB already has a richer name
        # (Herdr agent list only reports the agent type, not the pane label)
        incoming_label = agent.label or agent.id
        if existing is not None:
            existing_label = str(existing.get("label") or "")
            if existing_label and existing_label != incoming_label:
                incoming_label = existing_label
        self.agent_repo.upsert(
            agent.id,
            incoming_label,
            agent.type or "unknown",
            role,
            herdr_pane=agent.pane_id or None,
            herdr_ws=agent.workspace or None,
            state=agent.state or "unknown",
            health=health,
        )

    async def observe_agent(
        self,
        agent_id: str,
        *,
        state: str | None = None,
        pane_id: str | None = None,
        output: str | None = None,
        layer: str = "primary",
        now: float | None = None,
    ) -> None:
        """Record state/output observed from any watchdog layer."""

        if not agent_id:
            return
        current = self._seconds() if now is None else now
        monitor = self._monitor(agent_id, current)
        monitor.last_seen_at = current
        if pane_id:
            monitor.pane_id = pane_id

        progressed = False
        if state:
            normalized_state = state.lower()
            if normalized_state != monitor.state:
                monitor.state = normalized_state
                progressed = True
            self.agent_repo.update_state(agent_id, normalized_state)

        if output is not None:
            new_hash = output_hash(output)
            monitor.last_hash_at = current
            if new_hash != monitor.last_output_hash:
                monitor.last_output_hash = new_hash
                progressed = True
                self.agent_repo.update_state(agent_id, monitor.state, last_output_hash=new_hash)

        if progressed or monitor.state in _RESTING_STATES:
            monitor.last_progress_at = current
            self.agent_repo.record_heartbeat(agent_id, last_output_hash=monitor.last_output_hash)
            if monitor.health != _HEALTHY:
                reason = "agent_resting" if monitor.state in _RESTING_STATES else "agent_progress"
                await self._transition(monitor, _HEALTHY, reason, layer)

    async def _run_primary(self) -> None:
        subscribe_status = getattr(self.adapter, "subscribe_status", None)
        if subscribe_status is not None:
            # FR-AC-05/06: retry subscribe_status with backoff before
            # falling back to polling permanently.
            while True:
                self.primary_available = True
                try:
                    result = subscribe_status(self._handle_primary_event)
                    if inspect.isawaitable(result):
                        await result
                    # Success — reset reconnection counter.
                    self._primary_reconnect_attempts = 0
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if self._primary_reconnect_attempts >= len(self._RECONNECT_BACKOFF_S):
                        log.warning(
                            "watchdog_primary_reconnect_exhausted",
                            extra={"attempts": self._primary_reconnect_attempts},
                        )
                        self.primary_failed = True
                        self.primary_available = False
                        break
                    delay = self._RECONNECT_BACKOFF_S[
                        self._primary_reconnect_attempts
                    ]
                    self._primary_reconnect_attempts += 1
                    log.info(
                        "watchdog_primary_reconnect_attempt",
                        extra={
                            "attempt": self._primary_reconnect_attempts,
                            "delay_s": delay,
                        },
                    )
                    await asyncio.sleep(delay)

        source = await self._primary_source()
        if source is None:
            self.primary_available = False
            return

        self.primary_available = True
        try:
            async for event in source:
                await self._handle_primary_event(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("watchdog_primary_source_failed")
            self.primary_failed = True
            self.primary_available = False

    async def _primary_source(self) -> AsyncIterator[Any] | None:
        for method_name in (
            "subscribe_state_changes",
            "state_changes",
            "watch_state_changes",
            "watch_agents",
        ):
            method = getattr(self.adapter, method_name, None)
            if method is None:
                continue
            try:
                value = method()
            except Exception:
                self.primary_failed = True
                continue
            if inspect.isawaitable(value):
                value = await value
            if inspect.isasyncgen(value) or hasattr(value, "__aiter__"):
                return value
        return None

    async def _handle_primary_event(self, event: Any) -> None:
        payload = _event_payload(event)
        event_type = _event_value(payload, "type", "event_type")
        if event_type and event_type != "pane.agent_status_changed":
            return

        pane_id = _event_value(payload, "pane_id", "paneId", "pane")
        state = _event_value(payload, "agent_status", "state", "status")
        agent_id = _event_value(payload, "agent_id", "agentId", "id") or pane_id
        if not agent_id:
            return

        agent_label = _event_value(payload, "agent", "label", "name") or agent_id
        workspace = _event_value(payload, "workspace_id", "workspaceId", "workspace")
        if state or pane_id:
            self._sync_primary_agent(
                agent_id,
                label=agent_label,
                agent_type=agent_label,
                state=state or "unknown",
                pane_id=pane_id,
                workspace=workspace,
            )

        output = _event_value(payload, "output", "text")
        await self.observe_agent(
            agent_id,
            state=state or None,
            pane_id=pane_id or None,
            output=output if output != "" else None,
            layer="primary",
        )
        await self._evaluate_all(self._seconds())

    def _sync_primary_agent(
        self,
        agent_id: str,
        *,
        label: str,
        agent_type: str,
        state: str,
        pane_id: str,
        workspace: str,
    ) -> None:
        # ── Allowlist guard (mirrors _sync_agent) ────────────────────────────
        if self.config.agent_allowlist and agent_id not in self.config.agent_allowlist:
            log.debug(
                "allowlist: ignoring primary event for unregistered pane %r",
                agent_id,
            )
            return
        existing = self.agent_repo.get(agent_id)
        role = _role_for_agent(agent_id, self.acl_config, existing)
        health = str(existing.get("health") or _HEALTHY) if existing is not None else _HEALTHY
        self.agent_repo.upsert(
            agent_id,
            label,
            agent_type or "unknown",
            role,
            herdr_pane=pane_id or None,
            herdr_ws=workspace or None,
            state=state or "unknown",
            health=health,
        )

    async def _check_output_hash(self, agent_id: str, pane_id: str, now: float) -> None:
        try:
            output = await self.adapter.pane_read(pane_id)
        except HerdrError:
            return
        await self.observe_agent(agent_id, output=output, layer="tertiary", now=now)

    async def _evaluate_all(self, now: float) -> None:
        for monitor in list(self._monitors.values()):
            await self._evaluate(monitor, now)

    async def _evaluate(self, monitor: _Monitor, now: float) -> None:
        if monitor.health == _RECOVERING:
            return
        if monitor.state in _RESTING_STATES:
            if monitor.health != _HEALTHY:
                await self._transition(monitor, _HEALTHY, "agent_resting", "fsm")
            return
        if monitor.state not in _ACTIVE_STATES:
            return

        elapsed = now - monitor.last_progress_at
        if elapsed >= self.config.hard_timeout_s:
            if monitor.health == _HEALTHY:
                await self._transition(monitor, _SUSPECT, "soft_timeout", "fsm")
            if monitor.health != _UNHEALTHY:
                await self._transition(monitor, _UNHEALTHY, "hard_timeout", "fsm")
            await self._begin_recovery(monitor)
        elif elapsed >= self.config.soft_timeout_s and monitor.health == _HEALTHY:
            await self._transition(monitor, _SUSPECT, "soft_timeout", "fsm")

    async def _begin_recovery(self, monitor: _Monitor) -> None:
        if monitor.recovery_task is not None and not monitor.recovery_task.done():
            return
        await self._transition(monitor, _RECOVERING, "recovery_started", "recovery")
        monitor.recovery_task = asyncio.create_task(self._recover(monitor.agent_id))

    async def _recover(self, agent_id: str) -> None:
        monitor = self._monitors[agent_id]
        manager = self.recovery_manager or RecoveryManager(
            self.adapter,
            self.agent_repo,
            self.config,
            bus_publisher=self.bus_publisher,
            command_resolver=self.command_resolver,
            task_replayer=self.task_replayer,
            system_agent_id=self.system_agent_id,
            manage_health_events=False,
        )
        command = await self._resolve_command(agent_id)
        success = await manager.recover(agent_id, pane_id=monitor.pane_id, command=command)
        now = self._seconds()
        monitor.last_seen_at = now
        monitor.last_progress_at = now
        if success:
            await self._transition(monitor, _HEALTHY, "recovery_success", "recovery")
        else:
            await self._transition(monitor, _UNHEALTHY, "recovery_failed", "recovery")

    async def _resolve_command(self, agent_id: str) -> str | None:
        if self.command_resolver is None:
            return None
        agent = self.agent_repo.get(agent_id) or {}
        try:
            value = self.command_resolver(agent_id, agent)
        except TypeError:
            value = self.command_resolver(agent_id)
        if inspect.isawaitable(value):
            value = await value
        if value is None:
            return None
        return str(value)

    async def _transition(self, monitor: _Monitor, health: str, reason: str, layer: str) -> None:
        previous = monitor.health
        if previous == health:
            return
        monitor.health = health
        details = {
            "from": previous,
            "to": health,
            "reason": reason,
            "layer": layer,
            "state": monitor.state,
            "pane_id": monitor.pane_id,
        }
        self.agent_repo.update_health(monitor.agent_id, health, details=details)
        await self._emit_state_change(monitor.agent_id, previous, health, details)

    async def _emit_state_change(
        self,
        agent_id: str,
        previous: str,
        health: str,
        details: dict[str, object],
    ) -> None:
        await _publish(
            self.bus_publisher,
            _message(
                MessageType.STATE_CHANGE,
                self.system_agent_id,
                "broadcast",
                {
                    "agent_id": agent_id,
                    "previous_health": previous,
                    "health": health,
                    **details,
                },
            ),
        )

    def _monitor(self, agent_id: str, now: float) -> _Monitor:
        monitor = self._monitors.get(agent_id)
        if monitor is None:
            monitor = _Monitor(
                agent_id=agent_id,
                last_seen_at=now,
                last_progress_at=now,
                last_hash_at=0.0,
            )
            existing = self.agent_repo.get(agent_id)
            if existing is not None:
                monitor.state = _string(existing.get("state")) or "unknown"
                monitor.health = _string(existing.get("health")) or _HEALTHY
                monitor.pane_id = _string(existing.get("herdr_pane"))
                monitor.last_output_hash = _string(existing.get("last_output_hash")) or None
            self._monitors[agent_id] = monitor
        return monitor

    def _seconds(self) -> float:
        if self._now is not None:
            return float(self._now())
        return asyncio.get_running_loop().time()


async def _publish(publisher: Any | None, message: Message) -> None:
    if publisher is None:
        return
    publish = getattr(publisher, "publish", None)
    if publish is not None:
        value = publish(message)
    elif callable(publisher):
        value = publisher(message)
    else:
        return
    if inspect.isawaitable(value):
        await value


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


def _event_value(event: Any, *names: str) -> str:
    for name in names:
        value = ""
        if isinstance(event, dict):
            value = _string(event.get(name))
        else:
            value = _string(getattr(event, name, None))
        if value:
            return value
    return ""


def _event_payload(event: Any) -> Any:
    if not isinstance(event, dict):
        return event

    payload: Any = event
    for key in ("event", "result"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, dict):
            payload = value

    value = payload.get("event") if isinstance(payload, dict) else None
    if isinstance(value, dict):
        payload = value

    return payload


def _string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""
