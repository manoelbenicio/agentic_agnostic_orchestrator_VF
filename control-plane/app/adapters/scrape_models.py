"""Data models for the screen-scrape fallback detection system.

These models capture the result of parsing raw terminal output from agents
that do not expose a structured API.  Each ``ParsedSignal`` represents one
detected event (status change, error, progress, token usage, etc.)
extracted via regex patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SignalKind(StrEnum):
    """Classification of a signal extracted from terminal output."""

    # Lifecycle
    AGENT_READY = "agent_ready"
    AGENT_IDLE = "agent_idle"
    AGENT_WORKING = "agent_working"
    AGENT_BLOCKED = "agent_blocked"
    AGENT_DONE = "agent_done"
    AGENT_EXIT = "agent_exit"

    # Errors & warnings
    ERROR = "error"
    FATAL_ERROR = "fatal_error"
    WARNING = "warning"
    RATE_LIMIT = "rate_limit"
    AUTH_FAILURE = "auth_failure"
    TIMEOUT = "timeout"

    # Progress
    TASK_ACCEPTED = "task_accepted"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    COMMAND_RUN = "command_run"
    TOOL_CALL = "tool_call"

    # Metering
    TOKEN_USAGE = "token_usage"
    COST_REPORT = "cost_report"

    # Raw / unclassified
    PROMPT_DETECTED = "prompt_detected"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    """How confident the parser is in the extracted signal."""

    HIGH = "high"      # Exact match on well-known pattern
    MEDIUM = "medium"  # Partial match or heuristic
    LOW = "low"        # Fuzzy match, may be a false positive


@dataclass(frozen=True, slots=True)
class ParsedSignal:
    """A single event detected from terminal output."""

    kind: SignalKind
    confidence: Confidence
    raw_line: str
    line_number: int
    extracted: dict[str, Any] = field(default_factory=dict)
    vendor: str = ""
    pattern_id: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_error(self) -> bool:
        return self.kind in {
            SignalKind.ERROR,
            SignalKind.FATAL_ERROR,
            SignalKind.AUTH_FAILURE,
            SignalKind.RATE_LIMIT,
            SignalKind.TIMEOUT,
        }

    @property
    def is_lifecycle(self) -> bool:
        return self.kind.value.startswith("agent_")

    @property
    def is_progress(self) -> bool:
        return self.kind in {
            SignalKind.TASK_ACCEPTED,
            SignalKind.TASK_STARTED,
            SignalKind.TASK_COMPLETED,
            SignalKind.FILE_CREATED,
            SignalKind.FILE_MODIFIED,
            SignalKind.COMMAND_RUN,
            SignalKind.TOOL_CALL,
        }


@dataclass(frozen=True, slots=True)
class TerminalSnapshot:
    """Parsed result of a block of terminal output."""

    raw_output: str
    line_count: int
    signals: list[ParsedSignal] = field(default_factory=list)
    vendor: str = ""
    parsed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def has_errors(self) -> bool:
        return any(s.is_error for s in self.signals)

    @property
    def errors(self) -> list[ParsedSignal]:
        return [s for s in self.signals if s.is_error]

    @property
    def lifecycle_signals(self) -> list[ParsedSignal]:
        return [s for s in self.signals if s.is_lifecycle]

    @property
    def progress_signals(self) -> list[ParsedSignal]:
        return [s for s in self.signals if s.is_progress]

    @property
    def latest_state(self) -> SignalKind | None:
        """Return the most recent lifecycle signal kind, if any."""
        lifecycle = self.lifecycle_signals
        return lifecycle[-1].kind if lifecycle else None

    @property
    def high_confidence_signals(self) -> list[ParsedSignal]:
        return [s for s in self.signals if s.confidence == Confidence.HIGH]


@dataclass(frozen=True, slots=True)
class ScrapeDetectionConfig:
    """Configuration for the screen-scrape detection engine."""

    max_lines: int = 5_000
    max_line_length: int = 4_096
    vendors: tuple[str, ...] = (
        "claude",
        "codex",
        "gemini",
        "antigravity",
        "kiro",
        "generic",
    )
    include_low_confidence: bool = False
    enable_vendor_autodetect: bool = True
