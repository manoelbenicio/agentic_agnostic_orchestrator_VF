"""Fallback screen-scrape adapter for agents without native API support.

``ScreenScrapeAdapter`` wraps any ``NativeAgentAdapter`` and intercepts
the ``status()`` and ``send_task()`` calls.  When the underlying adapter
returns raw terminal output (or raises), the screen-scrape parser extracts
structured signals to infer agent state, detect errors, and report progress.

Usage::

    base = CodexAdapter(config)
    adapter = ScreenScrapeAdapter(base, vendor="codex")

    await adapter.start()
    result = await adapter.send_task(task)

    # result now includes parsed signals alongside the raw adapter result
    print(result["scrape_snapshot"]["signals"])
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .base import NativeAgentAdapter
from .scrape_models import (
    Confidence,
    ScrapeDetectionConfig,
    SignalKind,
    TerminalSnapshot,
)
from .scrape_parser import TerminalOutputParser

logger = logging.getLogger(__name__)


class ScreenScrapeAdapter(NativeAgentAdapter):
    """Fallback adapter that wraps a native adapter with screen-scrape detection.

    The scrape layer is transparent: all calls are forwarded to the inner
    adapter, and the results are augmented with parsed terminal signals.
    When the inner adapter's ``status()`` or ``send_task()`` return string
    output, the parser extracts structured data.

    If the inner adapter raises an exception, the scrape layer catches it,
    parses any partial output in the exception message, and returns a
    degraded result instead of crashing.
    """

    def __init__(
        self,
        inner: NativeAgentAdapter,
        *,
        vendor: str = "",
        config: ScrapeDetectionConfig | None = None,
    ) -> None:
        self.inner = inner
        self.vendor = vendor
        self.config = config or ScrapeDetectionConfig()
        self.parser = TerminalOutputParser(self.config)
        self._last_snapshot: TerminalSnapshot | None = None
        self._accumulated_lines: list[str] = []
        self._line_offset: int = 1

    async def start(self) -> None:
        """Start the underlying adapter."""
        await self.inner.start()

    async def stop(self) -> None:
        """Stop the underlying adapter."""
        await self.inner.stop()

    async def status(self) -> Dict[str, Any]:
        """Return the inner adapter status, augmented with scrape signals.

        If the inner status contains ``terminal_output`` or ``output``
        keys, the text is parsed for signals.
        """
        try:
            raw_status = await self.inner.status()
        except Exception as exc:
            logger.warning("inner adapter status() failed: %s", exc)
            snapshot = self.parser.parse(str(exc), vendor=self.vendor)
            self._last_snapshot = snapshot
            return {
                "agent": self.vendor or "unknown",
                "status": "degraded",
                "scrape_fallback": True,
                "inferred_state": self.parser.extract_state(snapshot),
                "errors": self.parser.extract_errors(snapshot),
                "scrape_snapshot": _snapshot_summary(snapshot),
            }

        # Try to extract terminal output from the status dict
        output = _extract_output(raw_status)
        if output:
            snapshot = self.parser.parse(output, vendor=self.vendor)
            self._last_snapshot = snapshot
            raw_status["scrape_fallback"] = True
            raw_status["inferred_state"] = self.parser.extract_state(snapshot)
            raw_status["scrape_snapshot"] = _snapshot_summary(snapshot)
            if snapshot.has_errors:
                raw_status["scrape_errors"] = self.parser.extract_errors(snapshot)

        return raw_status

    async def send_task(self, task: Dict[str, Any]) -> Any:
        """Send a task to the inner adapter and parse the result.

        If the inner adapter returns raw text or a dict with terminal
        output, the parser extracts signals.  On failure, the exception
        message is parsed as terminal output.
        """
        try:
            result = await self.inner.send_task(task)
        except Exception as exc:
            logger.warning("inner adapter send_task() failed: %s", exc)
            snapshot = self.parser.parse(str(exc), vendor=self.vendor)
            self._last_snapshot = snapshot
            return {
                "result": "scrape_fallback_error",
                "task_id": task.get("id") or task.get("task_id"),
                "scrape_fallback": True,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "inferred_state": self.parser.extract_state(snapshot),
                "errors": self.parser.extract_errors(snapshot),
                "scrape_snapshot": _snapshot_summary(snapshot),
            }

        # Augment structured result with scrape data
        output = ""
        if isinstance(result, str):
            output = result
        elif isinstance(result, dict):
            output = _extract_output(result)

        if output:
            snapshot = self.parser.parse(output, vendor=self.vendor)
            self._last_snapshot = snapshot
            if isinstance(result, str):
                result = {
                    "raw_output": result,
                    "task_id": task.get("id") or task.get("task_id"),
                }
            if isinstance(result, dict):
                result["scrape_fallback"] = True
                result["inferred_state"] = self.parser.extract_state(snapshot)
                result["scrape_snapshot"] = _snapshot_summary(snapshot)
                result["token_usage"] = self.parser.extract_token_usage(snapshot)
                result["files_touched"] = self.parser.extract_files_touched(snapshot)
                if snapshot.has_errors:
                    result["scrape_errors"] = self.parser.extract_errors(snapshot)

        return result

    # ── Streaming / incremental support ──────────────────────────────

    def feed_lines(self, new_lines: list[str]) -> list[dict[str, Any]]:
        """Feed new terminal lines for incremental parsing.

        Returns a list of newly detected signals (as dicts).
        Useful when the adapter streams output line-by-line.
        """
        self._accumulated_lines.extend(new_lines)
        signals = self.parser.parse_incremental(
            new_lines,
            start_line=self._line_offset,
            vendor=self.vendor,
        )
        self._line_offset += len(new_lines)
        return [_signal_to_dict(s) for s in signals]

    def reset_accumulator(self) -> None:
        """Reset the line accumulator for a new task."""
        self._accumulated_lines.clear()
        self._line_offset = 1
        self._last_snapshot = None

    @property
    def last_snapshot(self) -> TerminalSnapshot | None:
        """Return the most recently parsed terminal snapshot."""
        return self._last_snapshot

    @property
    def last_inferred_state(self) -> str:
        """Return the last inferred agent state, or 'unknown'."""
        if self._last_snapshot is None:
            return "unknown"
        return self.parser.extract_state(self._last_snapshot)


# ── Helpers ──────────────────────────────────────────────────────────────


def _extract_output(data: dict[str, Any] | Any) -> str:
    """Try to extract raw terminal output from a dict."""
    if not isinstance(data, dict):
        return ""
    for key in ("terminal_output", "output", "stdout", "raw_output", "text", "log"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _snapshot_summary(snapshot: TerminalSnapshot) -> dict[str, Any]:
    """Summarize a TerminalSnapshot as a JSON-safe dict."""
    return {
        "vendor": snapshot.vendor,
        "line_count": snapshot.line_count,
        "signal_count": len(snapshot.signals),
        "error_count": len(snapshot.errors),
        "has_errors": snapshot.has_errors,
        "latest_state": snapshot.latest_state.value if snapshot.latest_state else None,
        "signals": [_signal_to_dict(s) for s in snapshot.signals],
    }


def _signal_to_dict(signal: Any) -> dict[str, Any]:
    """Convert a ParsedSignal to a JSON-safe dict."""
    return {
        "kind": signal.kind.value,
        "confidence": signal.confidence.value,
        "line_number": signal.line_number,
        "vendor": signal.vendor,
        "pattern_id": signal.pattern_id,
        "extracted": signal.extracted,
        "raw_line": signal.raw_line[:200],  # truncate for safety
    }
