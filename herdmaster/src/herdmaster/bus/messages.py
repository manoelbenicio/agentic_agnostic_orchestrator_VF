"""Dependency-free message schemas for HerdMaster's JSON-RPC bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import json
from typing import Any, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from herdmaster.bus.server import MessageBusServer as MessageBus

__all__ = [
    "Message",
    "MessageBus",
    "MessageType",
    "group_name",
    "is_broadcast",
    "is_group",
    "new_message",
]


class MessageType(StrEnum):
    """Supported HerdMaster message types."""

    TASK_ASSIGN = "task_assign"
    TASK_ASSIGNED = "task_assign"
    TASK_UPDATE = "task_update"
    HEARTBEAT = "heartbeat"
    CHAT = "chat"
    ALERT = "alert"
    STATE_CHANGE = "state_change"


@dataclass(slots=True)
class Message:
    """A typed message carried in a JSON-RPC 2.0 envelope."""

    id: str
    type: MessageType
    from_agent: str
    to: str
    correlation_id: str | None
    timestamp: str
    ttl_seconds: int = 300
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type, MessageType):
            self.type = MessageType(self.type)

    def validate(self) -> None:
        """Raise ValueError when required schema fields are invalid."""

        if not isinstance(self.type, MessageType):
            try:
                MessageType(self.type)
            except ValueError as exc:
                raise ValueError(f"invalid message type: {self.type!r}") from exc
        if not self.from_agent:
            raise ValueError("from_agent must not be empty")
        if not self.to:
            raise ValueError("to must not be empty")
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")

    def to_json(self) -> str:
        """Serialize this message as a JSON-RPC 2.0 envelope."""

        self.validate()
        envelope = {
            "jsonrpc": "2.0",
            "method": self.type.value,
            "params": {
                "type": self.type.value,
                "from": self.from_agent,
                "to": self.to,
                "correlation_id": self.correlation_id,
                "timestamp": self.timestamp,
                "ttl_seconds": self.ttl_seconds,
                "payload": self.payload,
            },
            "id": self.id,
        }
        return json.dumps(envelope, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "Message":
        """Deserialize a Message from a JSON-RPC 2.0 envelope."""

        try:
            envelope = json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON message") from exc

        if not isinstance(envelope, dict):
            raise ValueError("JSON-RPC envelope must be an object")
        if envelope.get("jsonrpc") != "2.0":
            raise ValueError("JSON-RPC envelope must declare jsonrpc='2.0'")

        params = envelope.get("params")
        if not isinstance(params, dict):
            raise ValueError("JSON-RPC params must be an object")

        method = envelope.get("method")
        msg_type = params.get("type", method)
        if method is not None and msg_type != method:
            raise ValueError("JSON-RPC method and params.type must match")

        try:
            message = cls(
                id=str(envelope["id"]),
                type=MessageType(msg_type),
                from_agent=str(params["from"]),
                to=str(params["to"]),
                correlation_id=params.get("correlation_id"),
                timestamp=str(params["timestamp"]),
                ttl_seconds=int(params.get("ttl_seconds", 300)),
                payload=params.get("payload", {}),
            )
        except KeyError as exc:
            raise ValueError(f"missing message field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid message field: {exc}") from exc

        message.validate()
        return message

    def is_expired(self, now: datetime | str | None = None) -> bool:
        """Return True when timestamp + ttl_seconds is earlier than now."""

        created_at = _parse_utc(self.timestamp)
        current = _parse_utc(now) if isinstance(now, str) else now
        if current is None:
            current = datetime.now(UTC)
        elif current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current >= created_at + timedelta(seconds=self.ttl_seconds)


def is_broadcast(to: str) -> bool:
    """Return True when an address targets every agent."""

    return to == "broadcast"


def is_group(to: str) -> bool:
    """Return True when an address targets a named group."""

    return to.startswith("group:") and len(to) > len("group:")


def group_name(to: str) -> str | None:
    """Return the group name for group addresses, otherwise None."""

    if not is_group(to):
        return None
    return to.split(":", 1)[1]


def new_message(
    type: MessageType | str,
    from_agent: str | dict | None = None,
    to: str | None = None,
    payload: dict | None = None,
    *,
    sender: str | None = None,
    recipient: str | None = None,
    correlation_id: str | None = None,
    ttl_seconds: int = 300,
) -> Message:
    """Create a validated message with a time-ordered id and UTC timestamp.

    ``sender`` and ``recipient`` are compatibility aliases for
    ``from_agent`` and ``to``.
    """

    if isinstance(from_agent, dict) and payload is None and to is None:
        payload = from_agent
        from_agent = None
    if sender is not None:
        if from_agent is not None and from_agent != sender:
            raise ValueError("sender conflicts with from_agent")
        from_agent = sender
    if recipient is not None:
        if to is not None and to != recipient:
            raise ValueError("recipient conflicts with to")
        to = recipient
    if from_agent is None:
        raise ValueError("from_agent must not be empty")
    if to is None:
        raise ValueError("to must not be empty")

    message = Message(
        id=_new_time_ordered_id(),
        type=MessageType(type),
        from_agent=str(from_agent),
        to=str(to),
        correlation_id=correlation_id,
        timestamp=_utc_now_iso(),
        ttl_seconds=ttl_seconds,
        payload={} if payload is None else payload,
    )
    message.validate()
    return message


def __getattr__(name: str) -> Any:
    """Expose MessageBus as a lazy compatibility alias for MessageBusServer."""

    if name == "MessageBus":
        from herdmaster.bus.server import MessageBusServer

        globals()[name] = MessageBusServer
        return MessageBusServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _new_time_ordered_id() -> str:
    """Return a sortable, UUID-backed identifier."""

    millis = int(datetime.now(UTC).timestamp() * 1000)
    return f"{millis:013d}-{uuid.uuid4()}"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
