"""Unix-socket message bus server for HerdMaster (asyncio).

The server supports:
- Newline-delimited JSON-RPC 2.0 frames
- Pub/sub: per-agent channels, broadcast, and group multicast
- Persistent message logging via ``MessageRepo``
- TTL-based message expiry with periodic sweep
- Backpressure-safe per-subscriber queues with non-blocking writes
- A file-based fallback bus when the socket is unavailable
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import TracebackType
from typing import Any, Type

from herdmaster.db.repositories import MessageRepo
from herdmaster.config import BusConfig
from herdmaster.bus.messages import (
    Message,
    is_broadcast,
    is_group,
    new_message,
)

from herdmaster.db import connect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol helpers
# ---------------------------------------------------------------------------


async def _write_json_line(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> bool:
    """Write a newline-terminated JSON frame if the socket is open.

    Returns ``True`` when the write reached the downstream queue or ``False``
    if the transport is already closed.  This keeps the delivery path
    non-blocking and safe for broadcasts to many subscribers.
    """
    if writer.is_closing():
        return False
    frame = json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    try:
        writer.write(frame.encode())
        await writer.drain()
        return True
    except (ConnectionResetError, BrokenPipeError, OSError):
        return False


async def _read_json_lines(reader: asyncio.StreamReader) -> Message | None:
    """Read exactly one newline-delimited JSON-RPC 2.0 ``Message``.

    Returns ``None`` on EOF or unparseable frame.
    """
    try:
        raw = await reader.readline()
    except ConnectionResetError:
        return None
    if not raw:
        return None
    try:
        return Message.from_json(raw.decode())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Discarding unparseable bus frame: %s", exc)
        return None


# ---------------------------------------------------------------------------
# FileFallbackBus
# ---------------------------------------------------------------------------

class FileFallbackBus:
    """Graceful degradation bus that appends newline-JSON to a file.

    Used when the Unix domain socket cannot be bound or served, so agents can
    still exchange messages via a shared filesystem sink rather than losing
    them completely.
    """

    def __init__(self, fallback_path: str | Path, *, max_size_mb: float = 10.0) -> None:
        self.fallback_path = Path(fallback_path).expanduser().resolve()
        self._max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._lock = asyncio.Lock()

    async def write(self, message: Message) -> None:
        """Append a single message to the fallback file.

        Truncates the file when the size limit is exceeded to keep the
        footprint bounded.
        """
        async with self._lock:
            try:
                self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
                # Check size and trim if necessary
                if self.fallback_path.exists() and self.fallback_path.stat().st_size > self._max_size_bytes:
                    logger.warning("Fallback file exceeded %s MB—truncating.", self._max_size_bytes)
                    self.fallback_path.write_text("", encoding="utf-8")
                with self.fallback_path.open("a", encoding="utf-8") as f:
                    f.write(message.to_json() + "\n")
            except OSError:
                logger.exception("FileFallbackBus.write failed; message lost.")

    async def read_messages(self) -> list[Message]:
        """Return all messages currently stored in the fallback file."""
        messages: list[Message] = []
        if not self.fallback_path.exists():
            return messages
        try:
            lines = self.fallback_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if not line:
                    continue
                try:
                    messages.append(Message.from_json(line))
                except (json.JSONDecodeError, ValueError):
                    continue
        except OSError:
            logger.warning("Could not read fallback file contents.")
        return messages


# ---------------------------------------------------------------------------
# MessageBusServer
# ---------------------------------------------------------------------------

class MessageBusServer:
    """Asyncio Unix-socket message bus with pub/sub, persistence, TTL, and file fallback.

    Parameters
    ----------
    bus_config:
        ``BusConfig`` used to drive socket path, TTL, and fallback path.
    repo:
        An optional ``MessageRepo`` instance.  If ``None``, one is created
        lazily from an on-disk database at *bus_config.socket_path* sibling
        ``herdmaster.db``.
    max_queue_size:
        Per-subscriber backpressure threshold.  Queues that exceed this
        size silently drop the oldest messages (FR-105 + <500ms target).
    """

    def __init__(
        self,
        bus_config: BusConfig,
        *,
        repo: MessageRepo | None = None,
        max_queue_size: int = 1024,
    ) -> None:
        self.config = bus_config
        self.socket_path = Path(bus_config.socket_path).expanduser().resolve()
        self.ttl_seconds = bus_config.message_ttl_s

        # Per-subscriber queues: agent_id -> asyncio.Queue[task]
        self._queues: dict[str, asyncio.Queue[Message]] = {}
        # Agent metadata: agent_id -> asyncio.StreamWriter (optional, for tracking)
        self._writers: dict[str, asyncio.StreamWriter] = {}
        # Registered group members: group_name -> set(agent_id)
        self._group_members: dict[str, set[str]] = {}

        self._server: asyncio.AbstractServer | None = None
        self._running = False
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()

        # TTL sweep
        self._sweep_task: asyncio.Task | None = None
        self._sweep_interval_s = 30

        # Persistence
        self._repo = repo
        self._conn: Any | None = None

        # Fallback
        fallback_path = self.socket_path.with_suffix(".fallback")
        self._fallback = FileFallbackBus(fallback_path)
        self._using_fallback = False
        self._max_queue_size = max_queue_size

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def _db_path(self) -> Path:
        return self.socket_path.parent / "herdmaster.db"

    def _get_repo(self) -> MessageRepo:
        if self._repo is None:
            self._conn = connect(self._db_path)
            from herdmaster.db.schema import init_db
            init_db(self._conn)
            self._repo = MessageRepo(self._conn)
        return self._repo

    async def start(self) -> None:
        """Start the bus server, unlinking any existing socket first."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()

        # Unlink stale socket
        if self.socket_path.exists():
            self.socket_path.unlink()

        # Attempt socket server
        try:
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=str(self.socket_path),
            )
        except OSError as exc:
            logger.error("Unix socket bind/serve failed: %s. Activating file fallback.", exc)
            self._using_fallback = True
            self._server = None

        # Ensure parent dir exists
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Start TTL sweep
        self._sweep_task = asyncio.create_task(self._ttl_sweep_loop())

    async def stop(self) -> None:
        """Stop the server, close all connections, and unlink the socket."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()

        # Stop TTL sweep
        if self._sweep_task:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
            self._sweep_task = None

        # Close all writers
        for writer in list(self._writers.values()):
            if not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

        # Close server
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Unlink socket
        if self.socket_path.exists():
            self.socket_path.unlink()

        if self._conn is not None:
            self._conn.close()

    # ------------------------------------------------------------------
    # Client handling
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection on the Unix socket."""
        agent_id: str | None = None
        try:
            while self._running:
                # Read message envelope
                raw = await reader.readline()
                if not raw:
                    break

                # Try to parse as JSON-RPC envelope first
                try:
                    envelope = json.loads(raw.decode())
                except json.JSONDecodeError:
                    continue

                # Handle registration command (first message sent by a client)
                if envelope.get("jsonrpc") == "2.0" and envelope.get("method") == "register":
                    params = envelope.get("params", {})
                    agent_id = str(params.get("agent_id", ""))
                    if not agent_id:
                        continue
                    async with self._lock:
                        self._writers[agent_id] = writer
                        self._queues[agent_id] = asyncio.Queue(maxsize=self._max_queue_size)
                    logger.debug("Registered agent: %s", agent_id)
                    await _write_json_line(
                        writer,
                        {"jsonrpc": "2.0", "result": "registered", "id": envelope.get("id")},
                    )
                    # Start a task to pump messages to this subscriber
                    asyncio.create_task(self._pump_to_subscriber(agent_id, writer))
                    continue

                # Handle normal bus messages
                try:
                    msg = Message.from_json(raw.decode())
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning("Discarding unparseable frame: %s", exc)
                    continue

                if agent_id is None:
                    # first frame was not a register—ignore
                    continue

                # Persist
                try:
                    repo = self._get_repo()
                    repo.insert(
                        message_type=msg.type.value,
                        payload=msg.to_json(),
                        message_id=msg.id,
                        from_agent=msg.from_agent,
                        to_agent=msg.to if not is_broadcast(msg.to) else None,
                        correlation_id=msg.correlation_id,
                        ttl_seconds=msg.ttl_seconds,
                    )
                except Exception:
                    logger.exception("Failed to persist message %s", msg.id)

                # Route
                await self._route(msg)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Client connection error: %s", exc)
        finally:
            if agent_id is not None:
                async with self._lock:
                    self._writers.pop(agent_id, None)
                    self._queues.pop(agent_id, None)
                logger.debug("Unregistered agent: %s", agent_id)
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Delivery plumbing
    # ------------------------------------------------------------------

    async def _pump_to_subscriber(self, agent_id: str, writer: asyncio.StreamWriter) -> None:
        """Background task that pumps queued messages to one subscriber."""
        queue = self._queues.get(agent_id)
        if queue is None:
            return
        try:
            while self._running and not writer.is_closing():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                success = await _write_json_line(writer, json.loads(msg.to_json()))
                if success:
                    try:
                        repo = self._get_repo()
                        repo.mark_delivered(msg.id)
                    except Exception:
                        logger.exception("Failed to mark message %s delivered", msg.id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Pump error for subscriber %s", agent_id)

    async def _route(self, msg: Message) -> None:
        """Route a Message to its target(s) using the address field ``to``."""
        if msg.is_expired():
            logger.debug("Dropping expired message %s", msg.id)
            return

        if self._using_fallback:
            await self._fallback.write(msg)
            return

        target = msg.to
        if is_broadcast(target):
            await self._broadcast(msg)
        elif is_group(target):
            group = target.split(":", 1)[1]
            await self._multicast(group, msg)
        else:
            # Unicast
            await self._unicast(target, msg)

    async def _unicast(self, target: str, msg: Message) -> None:
        """Send a message to a single subscriber."""
        async with self._lock:
            queue = self._queues.get(target)
            if queue is None:
                logger.debug("No subscriber for unicast target %s", target)
                return
            # Backpressure: if queue full, drop oldest to keep <500ms target
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    async def _broadcast(self, msg: Message) -> None:
        """Send a message to every registered subscriber."""
        async with self._lock:
            queues = list(self._queues.values())
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    async def _multicast(self, group: str, msg: Message) -> None:
        """Send a message to every member of an agent group."""
        async with self._lock:
            members = self._group_members.get(group, set())
            queues = [q for aid, q in self._queues.items() if aid in members]
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # TTL sweep
    # ------------------------------------------------------------------

    async def _ttl_sweep_loop(self) -> None:
        """Periodic task that deletes expired undelivered messages."""
        while self._running:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._sweep_interval_s)
                # stop() has been called
                break
            except asyncio.TimeoutError:
                try:
                    repo = self._get_repo()
                    count = repo.expire()
                    if count:
                        logger.debug("TTL sweep removed %d expired messages", count)
                except Exception:
                    logger.exception("TTL sweep failed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, agent_id: str) -> None:
        """Programmatically register an agent so that it can receive messages.

        This is a no-op if the socket connection is used; subscribers register
        by sending a ``register`` JSON-RPC request over the socket.  Provided
        here for testing and programmatic server control.
        """
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue(maxsize=self._max_queue_size)

    def subscribe_to_group(self, agent_id: str, group: str) -> None:
        """Subscribe ``agent_id`` to a named multicast group."""
        if group not in self._group_members:
            self._group_members[group] = set()
        self._group_members[group].add(agent_id)

    def unsubscribe_from_group(self, agent_id: str, group: str) -> None:
        """Unsubscribe ``agent_id`` from a named multicast group."""
        members = self._group_members.get(group)
        if members is None:
            return
        members.discard(agent_id)
        if not members:
            del self._group_members[group]

    async def send(self, msg: Message) -> None:
        """Publish a message through the bus, persisting and routing it.

        This is the primary API for producers that cannot or do not want
        to connect to the Unix socket directly.
        """
        if not msg.id:
            msg = new_message(
                type=msg.type,
                from_agent=msg.from_agent,
                to=msg.to,
                payload=msg.payload,
                correlation_id=msg.correlation_id,
                ttl_seconds=msg.ttl_seconds,
            )

        # Persist
        try:
            repo = self._get_repo()
            repo.insert(
                message_type=msg.type.value,
                payload=msg.to_json(),
                message_id=msg.id,
                from_agent=msg.from_agent,
                to_agent=msg.to if not is_broadcast(msg.to) else None,
                correlation_id=msg.correlation_id,
                ttl_seconds=msg.ttl_seconds,
            )
        except Exception:
            logger.exception("Failed to persist message %s", msg.id)

        # Route
        await self._route(msg)

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> MessageBusServer:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.stop()
