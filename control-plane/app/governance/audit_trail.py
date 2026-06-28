"""Immutable, tamper-evident audit trail.

Provides :class:`AuditTrail`, an append-only log of :class:`AuditEntry`
records. Each entry's ``entry_hash`` is a SHA-256 digest over a canonical
serialization of the entry plus the previous entry's hash, forming a hash
chain. :meth:`AuditTrail.verify_integrity` walks the chain and reports
any tampered, missing, or out-of-order entries.

Storage is pluggable via the :class:`AuditStorage` protocol; the default
in-memory backend is process-local and useful for tests, development, or
single-instance deployments. A Postgres-backed backend can be wired in by
implementing the protocol against the existing ``audit_events`` table.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Iterator, Protocol, runtime_checkable
from uuid import uuid4

logger = logging.getLogger(__name__)

_GENESIS_HASH = "0" * 64
_HASH_ALGORITHM = "sha256"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON encoding used for hashing.

    Sort keys, exclude the entry's own hash fields, and force separators
    so the same logical entry always serializes to the same bytes.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One immutable record in the audit trail.

    Attributes:
        entry_id: Stable identifier (UUID4 hex).
        timestamp: UTC datetime the entry was recorded.
        actor: User id (or service account) that performed the action.
        action: Action verb (e.g. ``registry.create``, ``task.delete``).
        resource: Resource affected (URL, id, dotted path).
        old_value: Pre-action value (optional).
        new_value: Post-action value (optional).
        ip: Source IP if available.
        correlation_id: Trace / request correlation id.
        metadata: Arbitrary structured context.
        prev_hash: Hash of the previous entry (``"0"*64`` for genesis).
        entry_hash: Hash of this entry, computed from canonical fields + prev_hash.
    """

    actor: str
    action: str
    resource: str
    timestamp: datetime = field(default_factory=_utcnow)
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    old_value: Any = None
    new_value: Any = None
    ip: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = _GENESIS_HASH
    entry_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (with timestamps and values coerced)."""
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class AuditQuery:
    """Filter parameters for :meth:`AuditTrail.query`."""

    actor: str | None = None
    action: str | None = None
    resource_prefix: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    correlation_id: str | None = None
    limit: int | None = None

    def matches(self, entry: AuditEntry) -> bool:
        if self.actor is not None and entry.actor != self.actor:
            return False
        if self.action is not None and entry.action != self.action:
            return False
        if self.resource_prefix is not None and not str(entry.resource).startswith(self.resource_prefix):
            return False
        if self.correlation_id is not None and entry.correlation_id != self.correlation_id:
            return False
        if self.start is not None and entry.timestamp < self.start:
            return False
        if self.end is not None and entry.timestamp > self.end:
            return False
        return True


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """Result of :meth:`AuditTrail.verify_integrity`."""

    total_entries: int
    verified_entries: int
    broken_links: tuple[int, ...] = ()
    mismatched_hashes: tuple[int, ...] = ()
    message: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.broken_links and not self.mismatched_hashes


@runtime_checkable
class AuditStorage(Protocol):
    """Pluggable storage backend for :class:`AuditTrail`.

    Implementations must guarantee ``append`` is monotonic — once an entry
    is persisted, it cannot be removed or reordered. Existing append-only
    PostgreSQL triggers satisfy this property.
    """

    def append(self, entry: AuditEntry) -> None: ...
    def iter_all(self) -> Iterable[AuditEntry]: ...
    def __len__(self) -> int: ...


class InMemoryAuditStorage:
    """Thread-safe in-memory :class:`AuditStorage` for tests and single-process use."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()

    def append(self, entry: AuditEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def iter_all(self) -> Iterable[AuditEntry]:
        # Snapshot to avoid concurrent-modification while consumers iterate.
        with self._lock:
            return list(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


def _compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    material = prev_hash + _canonical_json(payload)
    return hashlib.new(_HASH_ALGORITHM, material.encode("utf-8")).hexdigest()


class AuditTrail:
    """Append-only audit log with tamper-evident hash chain."""

    def __init__(self, storage: AuditStorage | None = None) -> None:
        self._storage: AuditStorage = storage or InMemoryAuditStorage()
        self._lock = threading.Lock()
        self._last_hash = self._bootstrap_last_hash()

    # ------------------------------------------------------------------ append
    def append(
        self,
        actor: str,
        action: str,
        resource: str,
        *,
        old_value: Any = None,
        new_value: Any = None,
        ip: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEntry:
        """Record a new audit entry and return it.

        The entry's ``prev_hash`` and ``entry_hash`` are computed by this
        method; callers must not supply them.
        """
        with self._lock:
            prev_hash = self._last_hash
            ts = timestamp or _utcnow()
            payload = {
                "entry_id": uuid4().hex,  # provisional, replaced after construction
                "timestamp": ts,
                "actor": actor,
                "action": action,
                "resource": resource,
                "old_value": old_value,
                "new_value": new_value,
                "ip": ip,
                "correlation_id": correlation_id,
                "metadata": metadata or {},
            }
            entry_id = payload["entry_id"]
            entry_hash = _compute_hash(prev_hash, payload)
            entry = AuditEntry(
                entry_id=entry_id,
                timestamp=ts,
                actor=actor,
                action=action,
                resource=resource,
                old_value=old_value,
                new_value=new_value,
                ip=ip,
                correlation_id=correlation_id,
                metadata=dict(metadata or {}),
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            self._storage.append(entry)
            self._last_hash = entry_hash
            return entry

    # ------------------------------------------------------------------- query
    def query(self, q: AuditQuery | None = None) -> list[AuditEntry]:
        """Return entries matching ``q`` (or all entries if ``q`` is ``None``)."""
        q = q or AuditQuery()
        results: list[AuditEntry] = []
        for entry in self._storage.iter_all():
            if not q.matches(entry):
                continue
            results.append(entry)
            if q.limit is not None and len(results) >= q.limit:
                break
        return results

    def query_in_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        actor: str | None = None,
        action: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEntry]:
        return self.query(
            AuditQuery(start=start, end=end, actor=actor, action=action, limit=limit)
        )

    # ------------------------------------------------------------------ export
    def export_json(self, q: AuditQuery | None = None) -> str:
        entries = [entry.to_dict() for entry in self.query(q)]
        return json.dumps(entries, indent=2, sort_keys=True, default=str)

    def export_csv(self, q: AuditQuery | None = None) -> str:
        entries = self.query(q)
        buffer = io.StringIO()
        fieldnames = [
            "entry_id",
            "timestamp",
            "actor",
            "action",
            "resource",
            "ip",
            "correlation_id",
            "prev_hash",
            "entry_hash",
            "old_value",
            "new_value",
            "metadata",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = entry.to_dict()
            row["old_value"] = _stringify(row.get("old_value"))
            row["new_value"] = _stringify(row.get("new_value"))
            row["metadata"] = json.dumps(row.get("metadata") or {}, sort_keys=True, default=str)
            writer.writerow({key: row.get(key, "") for key in fieldnames})
        return buffer.getvalue()

    # ----------------------------------------------------------- integrity
    def verify_integrity(self) -> IntegrityReport:
        """Walk the chain and report any tampered or out-of-order entries.

        Returns an :class:`IntegrityReport` describing the result. An empty
        chain is considered valid.
        """
        prev_hash = _GENESIS_HASH
        verified = 0
        broken: list[int] = []
        mismatched: list[int] = []
        for index, entry in enumerate(self._storage.iter_all()):
            if entry.prev_hash != prev_hash:
                broken.append(index)
            payload = {
                "entry_id": entry.entry_id,
                "timestamp": entry.timestamp,
                "actor": entry.actor,
                "action": entry.action,
                "resource": entry.resource,
                "old_value": entry.old_value,
                "new_value": entry.new_value,
                "ip": entry.ip,
                "correlation_id": entry.correlation_id,
                "metadata": entry.metadata,
            }
            expected = _compute_hash(prev_hash, payload)
            if expected != entry.entry_hash:
                mismatched.append(index)
            prev_hash = entry.entry_hash
            verified += 1
        message = ""
        if broken or mismatched:
            message = (
                f"audit chain integrity violation: "
                f"{len(broken)} broken link(s), {len(mismatched)} mismatched hash(es)"
            )
            logger.warning(message)
        return IntegrityReport(
            total_entries=verified,
            verified_entries=verified - len(set(broken) | set(mismatched)),
            broken_links=tuple(broken),
            mismatched_hashes=tuple(mismatched),
            message=message,
        )

    # ------------------------------------------------------------------ dunder
    def __len__(self) -> int:
        return len(self._storage)

    def __iter__(self) -> Iterator[AuditEntry]:
        return iter(self._storage.iter_all())

    # --------------------------------------------------------------- internals
    def _bootstrap_last_hash(self) -> str:
        last = _GENESIS_HASH
        for entry in self._storage.iter_all():
            last = entry.entry_hash or last
        return last


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


# --------------------------------------------------------------- convenience

_DEFAULT_TRAIL: AuditTrail | None = None
_DEFAULT_LOCK = threading.Lock()


def get_default_trail() -> AuditTrail:
    """Return a process-wide :class:`AuditTrail` instance, creating it on first use."""
    global _DEFAULT_TRAIL
    with _DEFAULT_LOCK:
        if _DEFAULT_TRAIL is None:
            _DEFAULT_TRAIL = AuditTrail()
        return _DEFAULT_TRAIL


__all__ = [
    "AuditEntry",
    "AuditQuery",
    "AuditStorage",
    "AuditTrail",
    "InMemoryAuditStorage",
    "IntegrityReport",
    "get_default_trail",
]


# Re-export timedelta/utcnow markers so the module's typecheck-time imports
# remain stable if other governance modules re-export them.
_ = (timedelta, _utcnow)
