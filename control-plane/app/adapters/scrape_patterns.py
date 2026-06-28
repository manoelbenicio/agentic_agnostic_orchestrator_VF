"""Regex pattern library for screen-scrape detection across agent vendors.

Each pattern is a ``TerminalPattern`` — a compiled regex with metadata
describing what kind of signal it detects, the vendor it belongs to,
and the confidence level of the match.

Patterns are grouped by vendor and loaded lazily via ``get_patterns()``.
The ``GENERIC_PATTERNS`` list matches common terminal output regardless of
vendor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .scrape_models import Confidence, SignalKind


@dataclass(frozen=True, slots=True)
class TerminalPattern:
    """A single regex pattern for detecting a terminal signal."""

    pattern_id: str
    regex: re.Pattern[str]
    kind: SignalKind
    confidence: Confidence
    vendor: str  # "" means generic (any vendor)
    extract_fields: tuple[str, ...] = ()  # named groups to pull from match
    description: str = ""


def _p(
    pattern_id: str,
    regex: str,
    kind: SignalKind,
    confidence: Confidence = Confidence.HIGH,
    vendor: str = "",
    extract_fields: tuple[str, ...] = (),
    description: str = "",
) -> TerminalPattern:
    """Helper to build a TerminalPattern with a compiled regex."""
    return TerminalPattern(
        pattern_id=pattern_id,
        regex=re.compile(regex, re.IGNORECASE | re.MULTILINE),
        kind=kind,
        confidence=confidence,
        vendor=vendor,
        extract_fields=extract_fields,
        description=description,
    )


# ═════════════════════════════════════════════════════════════════════════
#  Generic patterns (any CLI agent)
# ═════════════════════════════════════════════════════════════════════════

GENERIC_PATTERNS: list[TerminalPattern] = [
    # ── Lifecycle ────────────────────────────────────────────────────
    _p(
        "gen_ready",
        r"(?:agent|session|runtime)\s+(?:is\s+)?(?:ready|started|initialized)",
        SignalKind.AGENT_READY,
        Confidence.HIGH,
        description="Agent reports it is ready",
    ),
    _p(
        "gen_idle",
        r"(?:waiting\s+for\s+(?:input|prompt|instructions)|idle|no\s+(?:pending|active)\s+tasks)",
        SignalKind.AGENT_IDLE,
        Confidence.MEDIUM,
        description="Agent appears idle / waiting for input",
    ),
    _p(
        "gen_exit",
        r"(?:agent|session|process)\s+(?:exited?|terminated|shutdown|stopped)(?:\s+with\s+code\s+(?P<exit_code>\d+))?",
        SignalKind.AGENT_EXIT,
        Confidence.HIGH,
        extract_fields=("exit_code",),
        description="Agent process has exited",
    ),

    # ── Errors ───────────────────────────────────────────────────────
    _p(
        "gen_error",
        r"(?:^|\s)(?:error|exception|traceback|panic|fatal)[\s:]+(?P<message>.+)",
        SignalKind.ERROR,
        Confidence.MEDIUM,
        extract_fields=("message",),
        description="Generic error detected",
    ),
    _p(
        "gen_fatal",
        r"(?:FATAL|CRITICAL|unrecoverable)\s*(?:error)?[\s:]+(?P<message>.+)",
        SignalKind.FATAL_ERROR,
        Confidence.HIGH,
        extract_fields=("message",),
        description="Fatal / unrecoverable error",
    ),
    _p(
        "gen_rate_limit",
        r"(?:rate\s*limit(?:ed)?|429|too\s+many\s+requests|quota\s+exceeded|throttl(?:ed|ing))",
        SignalKind.RATE_LIMIT,
        Confidence.HIGH,
        description="Rate limiting / 429 detected",
    ),
    _p(
        "gen_auth_fail",
        r"(?:auth(?:entication|orization)?\s+(?:failed|denied|error)|401\s+unauthorized|403\s+forbidden|invalid\s+(?:api[_\s]?key|token|credentials))",
        SignalKind.AUTH_FAILURE,
        Confidence.HIGH,
        description="Authentication / authorization failure",
    ),
    _p(
        "gen_timeout",
        r"(?:timed?\s*out|timeout|deadline\s+exceeded|context\s+deadline|read\s+tcp.*timeout)",
        SignalKind.TIMEOUT,
        Confidence.HIGH,
        description="Operation timeout detected",
    ),

    # ── Progress ─────────────────────────────────────────────────────
    _p(
        "gen_file_created",
        r"(?:creat(?:ed?|ing)|wrote?|writ(?:ten|ing))\s+(?:file\s+)?(?P<path>[^\s]+\.\w+)",
        SignalKind.FILE_CREATED,
        Confidence.MEDIUM,
        extract_fields=("path",),
        description="File creation detected",
    ),
    _p(
        "gen_file_modified",
        r"(?:modif(?:ied|ying)|updat(?:ed|ing)|edit(?:ed|ing)|chang(?:ed|ing))\s+(?:file\s+)?(?P<path>[^\s]+\.\w+)",
        SignalKind.FILE_MODIFIED,
        Confidence.MEDIUM,
        extract_fields=("path",),
        description="File modification detected",
    ),
    _p(
        "gen_command_run",
        r"(?:running|executing|exec|ran|run(?:ning)?)\s*(?:command\s*)?[:\s]+(?P<command>.+)",
        SignalKind.COMMAND_RUN,
        Confidence.MEDIUM,
        extract_fields=("command",),
        description="Command execution detected",
    ),
    _p(
        "gen_tool_call",
        r"(?:calling|invoking|using)\s+(?:tool|function)\s*(?::\s*)?(?P<tool_name>\S+)",
        SignalKind.TOOL_CALL,
        Confidence.MEDIUM,
        extract_fields=("tool_name",),
        description="Tool / function call detected",
    ),

    # ── Token usage ──────────────────────────────────────────────────
    _p(
        "gen_token_usage",
        r"(?:tokens?\s*(?:used|consumed|total|count))\s*[:=]\s*(?P<tokens>\d[\d,]*)",
        SignalKind.TOKEN_USAGE,
        Confidence.MEDIUM,
        extract_fields=("tokens",),
        description="Token usage counter detected",
    ),
    _p(
        "gen_cost_report",
        r"(?:cost|price|billing|charge)\s*[:=]\s*\$?\s*(?P<cost>[\d,.]+)",
        SignalKind.COST_REPORT,
        Confidence.LOW,
        extract_fields=("cost",),
        description="Cost / billing amount detected",
    ),

    # ── Prompt / input marker ────────────────────────────────────────
    _p(
        "gen_prompt",
        r"(?:^[>$#%]\s|(?:>>>\s)|(?:\.\.\.\s))",
        SignalKind.PROMPT_DETECTED,
        Confidence.LOW,
        description="Interactive prompt character detected",
    ),
]

# ═════════════════════════════════════════════════════════════════════════
#  Claude / Anthropic patterns
# ═════════════════════════════════════════════════════════════════════════

CLAUDE_PATTERNS: list[TerminalPattern] = [
    _p(
        "claude_ready",
        r"(?:claude|anthropic)\s+(?:cli\s+)?(?:is\s+)?(?:ready|initialized|started)",
        SignalKind.AGENT_READY,
        Confidence.HIGH,
        vendor="claude",
        description="Claude CLI ready",
    ),
    _p(
        "claude_working",
        r"(?:claude|anthropic)\s+(?:is\s+)?(?:thinking|processing|working|generating)",
        SignalKind.AGENT_WORKING,
        Confidence.HIGH,
        vendor="claude",
        description="Claude is actively processing",
    ),
    _p(
        "claude_done",
        r"(?:claude|anthropic)\s+(?:has\s+)?(?:finished|completed|done)",
        SignalKind.AGENT_DONE,
        Confidence.HIGH,
        vendor="claude",
        description="Claude task completed",
    ),
    _p(
        "claude_task_accept",
        r"(?:task|prompt)\s+(?:accepted|received|acknowledged)\s+by\s+(?:claude|anthropic)",
        SignalKind.TASK_ACCEPTED,
        Confidence.HIGH,
        vendor="claude",
        description="Claude accepted a task",
    ),
    _p(
        "claude_tool",
        r"(?:claude|anthropic)\s+(?:is\s+)?(?:calling|using|invoking)\s+(?:tool\s+)?(?P<tool_name>\S+)",
        SignalKind.TOOL_CALL,
        Confidence.HIGH,
        vendor="claude",
        extract_fields=("tool_name",),
        description="Claude tool call",
    ),
    _p(
        "claude_tokens",
        r"(?:input|output|total)\s+tokens?\s*[:=]\s*(?P<tokens>\d[\d,]*)",
        SignalKind.TOKEN_USAGE,
        Confidence.HIGH,
        vendor="claude",
        extract_fields=("tokens",),
        description="Claude token usage report",
    ),
    _p(
        "claude_cost",
        r"(?:session\s+)?cost\s*[:=]\s*\$\s*(?P<cost>[\d,.]+)",
        SignalKind.COST_REPORT,
        Confidence.HIGH,
        vendor="claude",
        extract_fields=("cost",),
        description="Claude session cost",
    ),
    _p(
        "claude_overloaded",
        r"(?:claude|anthropic)\s+(?:is\s+)?(?:overloaded|unavailable|at\s+capacity)",
        SignalKind.RATE_LIMIT,
        Confidence.HIGH,
        vendor="claude",
        description="Claude overloaded / at capacity",
    ),
]

# ═════════════════════════════════════════════════════════════════════════
#  Codex (OpenAI) patterns
# ═════════════════════════════════════════════════════════════════════════

CODEX_PATTERNS: list[TerminalPattern] = [
    _p(
        "codex_ready",
        r"(?:codex|openai)\s+(?:cli\s+)?(?:is\s+)?(?:ready|initialized|started|connected)",
        SignalKind.AGENT_READY,
        Confidence.HIGH,
        vendor="codex",
        description="Codex CLI ready",
    ),
    _p(
        "codex_working",
        r"(?:codex|openai)\s+(?:is\s+)?(?:thinking|processing|working|reasoning)",
        SignalKind.AGENT_WORKING,
        Confidence.HIGH,
        vendor="codex",
        description="Codex is actively processing",
    ),
    _p(
        "codex_done",
        r"(?:codex|openai)\s+(?:has\s+)?(?:finished|completed|done)",
        SignalKind.AGENT_DONE,
        Confidence.HIGH,
        vendor="codex",
        description="Codex task completed",
    ),
    _p(
        "codex_sandbox",
        r"(?:sandbox|container)\s+(?:created|started|running|ready)",
        SignalKind.AGENT_READY,
        Confidence.MEDIUM,
        vendor="codex",
        description="Codex sandbox ready",
    ),
    _p(
        "codex_apply_patch",
        r"(?:applying?\s+patch|patch\s+applied)\s*(?:to\s+)?(?P<path>\S+)?",
        SignalKind.FILE_MODIFIED,
        Confidence.HIGH,
        vendor="codex",
        extract_fields=("path",),
        description="Codex applied a file patch",
    ),
]

# ═════════════════════════════════════════════════════════════════════════
#  Gemini / Google patterns
# ═════════════════════════════════════════════════════════════════════════

GEMINI_PATTERNS: list[TerminalPattern] = [
    _p(
        "gemini_ready",
        r"(?:gemini|google)\s+(?:cli\s+)?(?:is\s+)?(?:ready|initialized|started|connected)",
        SignalKind.AGENT_READY,
        Confidence.HIGH,
        vendor="gemini",
        description="Gemini CLI ready",
    ),
    _p(
        "gemini_working",
        r"(?:gemini|google)\s+(?:is\s+)?(?:thinking|processing|working|generating)",
        SignalKind.AGENT_WORKING,
        Confidence.HIGH,
        vendor="gemini",
        description="Gemini is actively processing",
    ),
    _p(
        "gemini_done",
        r"(?:gemini|google)\s+(?:has\s+)?(?:finished|completed|done)",
        SignalKind.AGENT_DONE,
        Confidence.HIGH,
        vendor="gemini",
        description="Gemini task completed",
    ),
    _p(
        "gemini_tool",
        r"✦\s+(?P<tool_name>\S+)\s*(?:\(|$)",
        SignalKind.TOOL_CALL,
        Confidence.HIGH,
        vendor="gemini",
        extract_fields=("tool_name",),
        description="Gemini tool call (✦ marker)",
    ),
    _p(
        "gemini_safety",
        r"(?:safety\s+filter|content\s+blocked|safety\s+rating)",
        SignalKind.WARNING,
        Confidence.HIGH,
        vendor="gemini",
        description="Gemini safety filter triggered",
    ),
]

# ═════════════════════════════════════════════════════════════════════════
#  Antigravity patterns
# ═════════════════════════════════════════════════════════════════════════

ANTIGRAVITY_PATTERNS: list[TerminalPattern] = [
    _p(
        "agy_ready",
        r"(?:antigravity|agy)\s+(?:cli\s+)?(?:is\s+)?(?:ready|initialized|started|connected)",
        SignalKind.AGENT_READY,
        Confidence.HIGH,
        vendor="antigravity",
        description="Antigravity CLI ready",
    ),
    _p(
        "agy_working",
        r"(?:antigravity|agy)\s+(?:is\s+)?(?:thinking|processing|working|generating)",
        SignalKind.AGENT_WORKING,
        Confidence.HIGH,
        vendor="antigravity",
        description="Antigravity is actively processing",
    ),
    _p(
        "agy_done",
        r"(?:antigravity|agy)\s+(?:has\s+)?(?:finished|completed|done)",
        SignalKind.AGENT_DONE,
        Confidence.HIGH,
        vendor="antigravity",
        description="Antigravity task completed",
    ),
    _p(
        "agy_subagent",
        r"(?:spawning|invoking|launching)\s+(?:sub\s*agent|subagent)\s*(?::\s*)?(?P<subagent>\S+)?",
        SignalKind.TOOL_CALL,
        Confidence.HIGH,
        vendor="antigravity",
        extract_fields=("subagent",),
        description="Antigravity subagent spawn",
    ),
]

# ═════════════════════════════════════════════════════════════════════════
#  Kiro / AWS patterns
# ═════════════════════════════════════════════════════════════════════════

KIRO_PATTERNS: list[TerminalPattern] = [
    _p(
        "kiro_ready",
        r"(?:kiro|aws)\s+(?:cli\s+)?(?:is\s+)?(?:ready|initialized|started|connected)",
        SignalKind.AGENT_READY,
        Confidence.HIGH,
        vendor="kiro",
        description="Kiro CLI ready",
    ),
    _p(
        "kiro_working",
        r"(?:kiro|aws)\s+(?:is\s+)?(?:thinking|processing|working|steering|planning)",
        SignalKind.AGENT_WORKING,
        Confidence.HIGH,
        vendor="kiro",
        description="Kiro is actively processing",
    ),
    _p(
        "kiro_done",
        r"(?:kiro|aws)\s+(?:has\s+)?(?:finished|completed|done)",
        SignalKind.AGENT_DONE,
        Confidence.HIGH,
        vendor="kiro",
        description="Kiro task completed",
    ),
    _p(
        "kiro_spec",
        r"(?:spec\s+(?:generated|created|updated)|steering\s+(?:applied|complete))",
        SignalKind.TASK_COMPLETED,
        Confidence.HIGH,
        vendor="kiro",
        description="Kiro spec or steering completed",
    ),
]

# ═════════════════════════════════════════════════════════════════════════
#  Vendor auto-detection patterns (used to identify which vendor is active)
# ═════════════════════════════════════════════════════════════════════════

VENDOR_DETECT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("claude", re.compile(r"(?:claude|anthropic|sonnet|haiku|opus)", re.IGNORECASE)),
    ("codex", re.compile(r"(?:codex|openai|gpt-4|chatgpt)", re.IGNORECASE)),
    ("gemini", re.compile(r"(?:gemini|google|bard|palm)", re.IGNORECASE)),
    ("antigravity", re.compile(r"(?:antigravity|agy|deepmind)", re.IGNORECASE)),
    ("kiro", re.compile(r"(?:kiro|aws|bedrock|amazon)", re.IGNORECASE)),
]


# ═════════════════════════════════════════════════════════════════════════
#  Public API
# ═════════════════════════════════════════════════════════════════════════

_VENDOR_REGISTRY: dict[str, list[TerminalPattern]] = {
    "claude": CLAUDE_PATTERNS,
    "codex": CODEX_PATTERNS,
    "gemini": GEMINI_PATTERNS,
    "antigravity": ANTIGRAVITY_PATTERNS,
    "kiro": KIRO_PATTERNS,
    "generic": GENERIC_PATTERNS,
}


def get_patterns(vendor: str = "") -> list[TerminalPattern]:
    """Return patterns for a vendor, always including generic patterns.

    If vendor is empty or unknown, returns only generic patterns.
    """
    result: list[TerminalPattern] = []
    if vendor and vendor in _VENDOR_REGISTRY and vendor != "generic":
        result.extend(_VENDOR_REGISTRY[vendor])
    result.extend(GENERIC_PATTERNS)
    return result


def get_all_patterns() -> list[TerminalPattern]:
    """Return all patterns across all vendors."""
    result: list[TerminalPattern] = []
    for vendor_patterns in _VENDOR_REGISTRY.values():
        result.extend(vendor_patterns)
    return result


def detect_vendor(text: str) -> str:
    """Auto-detect the most likely vendor from raw terminal output.

    Returns the vendor key, or "generic" if no vendor detected.
    """
    scores: dict[str, int] = {}
    for vendor, regex in VENDOR_DETECT_PATTERNS:
        count = len(regex.findall(text))
        if count > 0:
            scores[vendor] = count
    if not scores:
        return "generic"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def list_vendors() -> list[str]:
    """Return all registered vendor keys."""
    return sorted(_VENDOR_REGISTRY.keys())
