"""Dispatch-side trigger: turn a lifecycle event into an exhaustion signal.

Pure, testable glue used by ``app.dependencies.collect_events`` to decide whether
a rotation should be attempted after dispatch. Looks at the places where vendors
surface a token-limit signal:

  * the event ``message`` (free text),
  * ``details["queue"]`` (HerdMaster socket record: state/error/message/usage),
  * an explicit ``details["status_code"]`` (e.g. 429/503),
  * ``details["pane_text"]`` / ``details["output"]`` (terminal pane capture).

Detection is best-effort and never raises; if nothing matches it returns a
non-exhausted signal and the normal flow continues unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .detector import ExhaustionSignal, QuotaExhaustionDetector


def _collect_text(event: Mapping[str, Any]) -> str:
    """Concatenate the textual fields of an event where a vendor message may live."""
    parts: list[str] = []
    msg = event.get("message")
    if isinstance(msg, str):
        parts.append(msg)
    details = event.get("details")
    if isinstance(details, Mapping):
        for key in ("pane_text", "output", "stdout", "error", "message", "reason"):
            value = details.get(key)
            if isinstance(value, str):
                parts.append(value)
        queue = details.get("queue")
        if isinstance(queue, Mapping):
            for key in ("state", "status", "error", "message", "detail"):
                value = queue.get(key)
                if isinstance(value, str):
                    parts.append(value)
    return "\n".join(parts)


def _status_code(event: Mapping[str, Any]) -> int | None:
    details = event.get("details")
    if not isinstance(details, Mapping):
        return None
    for source in (details, details.get("queue") if isinstance(details.get("queue"), Mapping) else {}):
        if isinstance(source, Mapping):
            code = source.get("status_code") or source.get("http_status")
            if isinstance(code, int):
                return code
            if isinstance(code, str) and code.isdigit():
                return int(code)
    return None


def exhaustion_from_event(
    detector: QuotaExhaustionDetector,
    event: Mapping[str, Any],
    *,
    vendor: str | None = None,
) -> ExhaustionSignal:
    """Return an ExhaustionSignal for a serialized lifecycle event.

    Tries status code first (429 quota / 503 overload), then text patterns. When
    ``vendor`` is known the vendor-specific pattern is used; otherwise all
    patterns are tried via ``detect_any``.
    """
    code = _status_code(event)
    if code is not None:
        signal = detector.detect_status_code(vendor or "", code)
        if signal.exhausted or signal.is_server_overload:
            return signal
    text = _collect_text(event)
    if not text:
        return ExhaustionSignal(exhausted=False, vendor=vendor or "")
    if vendor:
        return detector.detect_text(vendor, text)
    return detector.detect_any(text)
