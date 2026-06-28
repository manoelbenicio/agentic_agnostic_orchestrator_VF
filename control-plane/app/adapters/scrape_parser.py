"""Terminal output parser engine for screen-scrape fallback detection.

The parser takes raw terminal text and a vendor hint, then applies the
matching regex patterns line-by-line to extract structured signals.

Usage::

    parser = TerminalOutputParser()
    snapshot = parser.parse(raw_output, vendor="claude")

    for signal in snapshot.signals:
        print(signal.kind, signal.confidence, signal.extracted)

    # Or with auto-detection:
    snapshot = parser.parse(raw_output)
    print(f"Detected vendor: {snapshot.vendor}")
"""

from __future__ import annotations

import logging
from typing import Any

from .scrape_models import (
    Confidence,
    ParsedSignal,
    ScrapeDetectionConfig,
    SignalKind,
    TerminalSnapshot,
)
from .scrape_patterns import (
    TerminalPattern,
    detect_vendor,
    get_patterns,
)

logger = logging.getLogger(__name__)


class TerminalOutputParser:
    """Parse raw terminal output into structured signals via regex patterns.

    The parser:
    1. Optionally auto-detects the vendor from the output.
    2. Loads vendor-specific + generic patterns.
    3. Iterates lines, applying each pattern.
    4. De-duplicates overlapping matches on the same line.
    5. Returns a ``TerminalSnapshot`` with all detected signals.
    """

    def __init__(self, config: ScrapeDetectionConfig | None = None) -> None:
        self.config = config or ScrapeDetectionConfig()

    def parse(
        self,
        raw_output: str,
        *,
        vendor: str = "",
    ) -> TerminalSnapshot:
        """Parse raw terminal output and return a snapshot of detected signals."""
        if not raw_output or not raw_output.strip():
            return TerminalSnapshot(
                raw_output=raw_output,
                line_count=0,
                vendor=vendor or "generic",
            )

        # Auto-detect vendor if not specified
        effective_vendor = vendor
        if not effective_vendor and self.config.enable_vendor_autodetect:
            effective_vendor = detect_vendor(raw_output)
        effective_vendor = effective_vendor or "generic"

        patterns = get_patterns(effective_vendor)
        lines = raw_output.splitlines()

        # Enforce max_lines
        if len(lines) > self.config.max_lines:
            logger.warning(
                "terminal output has %d lines, truncating to %d",
                len(lines),
                self.config.max_lines,
            )
            lines = lines[: self.config.max_lines]

        signals: list[ParsedSignal] = []
        for line_number, line in enumerate(lines, start=1):
            # Enforce max line length
            if len(line) > self.config.max_line_length:
                line = line[: self.config.max_line_length]

            line_signals = self._match_line(
                line, line_number, patterns, effective_vendor
            )
            signals.extend(line_signals)

        # Filter low-confidence signals if configured
        if not self.config.include_low_confidence:
            signals = [s for s in signals if s.confidence != Confidence.LOW]

        return TerminalSnapshot(
            raw_output=raw_output,
            line_count=len(lines),
            signals=signals,
            vendor=effective_vendor,
        )

    def parse_incremental(
        self,
        new_lines: list[str],
        *,
        start_line: int = 1,
        vendor: str = "generic",
    ) -> list[ParsedSignal]:
        """Parse a batch of new lines (for streaming / incremental detection).

        Returns only the new signals — the caller is responsible for
        accumulating them.
        """
        patterns = get_patterns(vendor)
        signals: list[ParsedSignal] = []
        for offset, line in enumerate(new_lines):
            line_number = start_line + offset
            if len(line) > self.config.max_line_length:
                line = line[: self.config.max_line_length]
            line_signals = self._match_line(line, line_number, patterns, vendor)
            signals.extend(line_signals)

        if not self.config.include_low_confidence:
            signals = [s for s in signals if s.confidence != Confidence.LOW]
        return signals

    def extract_state(self, snapshot: TerminalSnapshot) -> str:
        """Derive a normalized agent state string from a snapshot.

        Maps the latest lifecycle signal to the ``AgentState`` values used
        by the executor layer (idle, working, blocked, done, unknown).
        """
        latest = snapshot.latest_state
        if latest is None:
            return "unknown"

        state_map = {
            SignalKind.AGENT_READY: "idle",
            SignalKind.AGENT_IDLE: "idle",
            SignalKind.AGENT_WORKING: "working",
            SignalKind.AGENT_BLOCKED: "blocked",
            SignalKind.AGENT_DONE: "done",
            SignalKind.AGENT_EXIT: "done",
        }
        return state_map.get(latest, "unknown")

    def extract_errors(self, snapshot: TerminalSnapshot) -> list[dict[str, Any]]:
        """Return structured error summaries from a snapshot."""
        return [
            {
                "kind": signal.kind.value,
                "confidence": signal.confidence.value,
                "message": signal.extracted.get("message", signal.raw_line.strip()),
                "line_number": signal.line_number,
                "pattern_id": signal.pattern_id,
            }
            for signal in snapshot.errors
        ]

    def extract_token_usage(self, snapshot: TerminalSnapshot) -> int:
        """Sum all detected token usage counters from a snapshot."""
        total = 0
        for signal in snapshot.signals:
            if signal.kind == SignalKind.TOKEN_USAGE:
                raw = signal.extracted.get("tokens", "0")
                try:
                    total += int(str(raw).replace(",", ""))
                except (ValueError, TypeError):
                    pass
        return total

    def extract_files_touched(self, snapshot: TerminalSnapshot) -> list[dict[str, str]]:
        """Return file paths detected as created or modified."""
        files: list[dict[str, str]] = []
        seen: set[str] = set()
        for signal in snapshot.signals:
            if signal.kind in {SignalKind.FILE_CREATED, SignalKind.FILE_MODIFIED}:
                path = signal.extracted.get("path", "")
                if path and path not in seen:
                    seen.add(path)
                    files.append({
                        "path": path,
                        "action": "created" if signal.kind == SignalKind.FILE_CREATED else "modified",
                        "line_number": str(signal.line_number),
                    })
        return files

    # ── Internal ─────────────────────────────────────────────────────

    def _match_line(
        self,
        line: str,
        line_number: int,
        patterns: list[TerminalPattern],
        vendor: str,
    ) -> list[ParsedSignal]:
        """Apply all patterns to a single line and de-duplicate."""
        if not line.strip():
            return []

        signals: list[ParsedSignal] = []
        seen_kinds: set[SignalKind] = set()

        for pattern in patterns:
            match = pattern.regex.search(line)
            if match is None:
                continue

            # De-duplicate: only one signal per kind per line,
            # preferring higher confidence and vendor-specific over generic
            if pattern.kind in seen_kinds:
                # Check if existing is lower confidence, replace it
                existing_idx = next(
                    (i for i, s in enumerate(signals) if s.kind == pattern.kind),
                    None,
                )
                if existing_idx is not None:
                    existing = signals[existing_idx]
                    # Vendor-specific wins over generic
                    if not existing.vendor and pattern.vendor:
                        signals[existing_idx] = self._build_signal(
                            pattern, match, line, line_number, vendor
                        )
                    # Higher confidence wins
                    elif (
                        _confidence_rank(pattern.confidence)
                        > _confidence_rank(existing.confidence)
                    ):
                        signals[existing_idx] = self._build_signal(
                            pattern, match, line, line_number, vendor
                        )
                continue

            seen_kinds.add(pattern.kind)
            signals.append(
                self._build_signal(pattern, match, line, line_number, vendor)
            )

        return signals

    def _build_signal(
        self,
        pattern: TerminalPattern,
        match: Any,
        line: str,
        line_number: int,
        vendor: str,
    ) -> ParsedSignal:
        """Build a ParsedSignal from a regex match."""
        extracted: dict[str, Any] = {}
        for field_name in pattern.extract_fields:
            try:
                value = match.group(field_name)
                if value is not None:
                    extracted[field_name] = value
            except IndexError:
                pass

        return ParsedSignal(
            kind=pattern.kind,
            confidence=pattern.confidence,
            raw_line=line,
            line_number=line_number,
            extracted=extracted,
            vendor=pattern.vendor or vendor,
            pattern_id=pattern.pattern_id,
        )


def _confidence_rank(confidence: Confidence) -> int:
    return {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}.get(
        confidence, 0
    )
