"""Token-exhaustion detector (reactive signal).

Patterns researched from real vendor messages (doc 36 §2.1). Override at runtime
via ``AOP_QUOTA_PATTERNS_JSON`` so the squad can correct the exact on-screen
phrase at deploy time without code changes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

# Default detection patterns per vendor (case-insensitive). These are the
# researched phrases; confirm against the live screen at first deploy.
DEFAULT_PATTERNS: dict[str, str] = {
    "codex": r"you've hit your usage limit",
    "opus": r"usage limit reached|5-hour limit reached|hit your limit for claude",
    "claude": r"usage limit reached|5-hour limit reached|hit your limit for claude",
    "glm": r"exceeded quota|usage limit|token limit reached",
    "antigravity": r"reached the quota limit for this model",
}

# Reset-time hints embedded in the message ("resets at 2pm", "resume ... at 3:36 PM",
# "try again in 4 days 2 hours"). Used to compute cooldown_until precisely.
_RESET_AT = re.compile(r"(?:reset[s]?|resume|try again)\s+(?:by|at|using this model at)?\s*([0-9][^.\n·]*)", re.I)


@dataclass(frozen=True, slots=True)
class ExhaustionSignal:
    """Outcome of a detection check."""

    exhausted: bool
    vendor: str
    reset_hint: str | None = None     # raw reset text, if present (parse later)
    is_server_overload: bool = False  # e.g. Antigravity 503 high-traffic: do NOT rotate
    raw: str | None = None


class QuotaExhaustionDetector:
    """Detects token exhaustion from pane text or HTTP-like status codes."""

    def __init__(self, patterns: dict[str, str] | None = None) -> None:
        merged = dict(DEFAULT_PATTERNS)
        merged.update(self._patterns_from_env())
        if patterns:
            merged.update(patterns)
        self._patterns = {v: re.compile(p, re.I) for v, p in merged.items()}

    @staticmethod
    def _patterns_from_env() -> dict[str, str]:
        raw = os.environ.get("AOP_QUOTA_PATTERNS_JSON")
        if not raw:
            return {}
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("AOP_QUOTA_PATTERNS_JSON must be a JSON object {vendor: regex}")
        return {str(k): str(v) for k, v in decoded.items()}

    def detect_text(self, vendor: str, text: str) -> ExhaustionSignal:
        """Detect exhaustion in terminal/pane output for a vendor."""
        pattern = self._patterns.get(vendor.lower())
        if pattern is None or not pattern.search(text or ""):
            return ExhaustionSignal(exhausted=False, vendor=vendor, raw=text)
        reset = _RESET_AT.search(text or "")
        return ExhaustionSignal(
            exhausted=True,
            vendor=vendor,
            reset_hint=reset.group(1).strip() if reset else None,
            raw=text,
        )

    def detect_any(self, text: str) -> ExhaustionSignal:
        """Detect exhaustion trying ALL vendor patterns (vendor unknown).

        Returns the first matching vendor. Useful at the dispatch trigger where
        the originating vendor isn't known up front.
        """
        for vendor, pattern in self._patterns.items():
            if pattern.search(text or ""):
                reset = _RESET_AT.search(text or "")
                return ExhaustionSignal(
                    exhausted=True,
                    vendor=vendor,
                    reset_hint=reset.group(1).strip() if reset else None,
                    raw=text,
                )
        return ExhaustionSignal(exhausted=False, vendor="", raw=text)

    def detect_status_code(self, vendor: str, status_code: int) -> ExhaustionSignal:
        """Map an HTTP-like status to an exhaustion signal.

        429 → quota exhaustion (rotate). 503 → server overload (do NOT rotate;
        retry/switch model — doc 36 §2.1).
        """
        if status_code == 429:
            return ExhaustionSignal(exhausted=True, vendor=vendor)
        if status_code == 503:
            return ExhaustionSignal(exhausted=False, vendor=vendor, is_server_overload=True)
        return ExhaustionSignal(exhausted=False, vendor=vendor)

    def parse_reset_time(self, reset_hint: str | None, *, now: datetime) -> datetime | None:
        """Parse a vendor reset hint into an absolute UTC timestamp.

        Handles the three shapes seen across vendors (doc 36 §2.1):
          * relative  — "in 4 days 2 hours 46 minutes"
          * clock     — "3:51 PM", "6am", "2pm" (next occurrence after ``now``)
          * datetime  — "2/1/2026, 3:36:33 PM"

        Timezone qualifiers in the message (e.g. "(America/New_York)") are
        stripped and the time is interpreted in ``now``'s timezone (UTC in
        production). Returns ``None`` when nothing parseable is found, so callers
        fall back to ``window_seconds`` (default 5h).
        """
        if not reset_hint:
            return None
        text = reset_hint.strip()

        # 1) relative: "in 4 days 2 hours 46 minutes" / "4 days 2 hours"
        rel = re.findall(r"(\d+)\s*(day|hour|minute|min|hr)s?", text, re.I)
        if rel:
            days = hours = minutes = 0
            for value, unit in rel:
                u = unit.lower()
                if u.startswith("day"):
                    days = int(value)
                elif u.startswith("h"):
                    hours = int(value)
                else:
                    minutes = int(value)
            return now + timedelta(days=days, hours=hours, minutes=minutes)

        # strip timezone parenthetical, e.g. "6am (Asia/Seoul)"
        clean = re.sub(r"\(.*?\)", "", text).strip().rstrip(".·").strip()

        # 2) absolute datetime: "2/1/2026, 3:36:33 PM" (try a few formats)
        for fmt in ("%m/%d/%Y, %I:%M:%S %p", "%m/%d/%Y, %I:%M %p", "%m/%d/%Y %I:%M %p"):
            try:
                parsed = datetime.strptime(clean, fmt)
                return parsed.replace(tzinfo=now.tzinfo)
            except ValueError:
                continue

        # 3) clock time: "3:51 PM" / "6am" / "2pm" → next occurrence after now
        m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?$", clean, re.I)
        if m:
            hour = int(m.group(1)) % 12
            minute = int(m.group(2) or 0)
            if m.group(3).lower() == "p":
                hour += 12
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        return None
