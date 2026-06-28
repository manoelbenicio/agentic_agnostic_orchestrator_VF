"""Parsers for Herdr Socket API JSON output.

Official ``agent.list`` sample accepted by ``parse_agent_list``:

    {"id":"...","result":{"type":"agent_list","agents":[
      {"agent":"codex","agent_status":"idle","pane_id":"w4:pA","workspace_id":"w4"}
    ]}}
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


KNOWN_STATES = {"idle", "working", "blocked", "done", "unknown"}


@dataclass(frozen=True)
class HerdrAgent:
    """Agent state reported by Herdr."""

    id: str
    label: str
    type: str
    state: str
    pane_id: str
    workspace: str


@dataclass(frozen=True)
class HerdrPane:
    """Terminal pane reported by Herdr."""

    id: str
    label: str
    state: str
    workspace: str
    agent_id: str


def parse_agent_list(raw: str) -> list[HerdrAgent]:
    """Parse Herdr ``agent.list`` output.

    Official Herdr responses wrap agents in ``result.agents``. The parser also
    accepts the older flat shapes used by existing test doubles.
    """

    return [_agent_from_item(item) for item in _extract_items(raw, "agents")]


def parse_pane_list(raw: str) -> list[HerdrPane]:
    """Parse Herdr ``pane.list`` output.

    The parser tolerates missing and extra fields.
    """

    return [_pane_from_item(item) for item in _extract_items(raw, "panes")]


def output_hash(text: str) -> str:
    """Return a stable hash suitable for frozen-terminal output comparison."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_items(raw: str, preferred_key: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Herdr JSON: {exc}") from exc

    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        result = parsed.get("result")
        result_items: Any = None
        if isinstance(result, dict):
            result_items = result.get(preferred_key) or result.get("items") or result.get("data")
        value = result_items or parsed.get(preferred_key) or parsed.get("items") or parsed.get("data") or []
        items = value if isinstance(value, list) else []
    else:
        items = []

    return [item for item in items if isinstance(item, dict)]


def _agent_from_item(item: dict[str, Any]) -> HerdrAgent:
    pane = item.get("pane")
    workspace = item.get("workspace")

    pane_id = (
        _string(item.get("pane_id"))
        or _string(item.get("paneId"))
        or _nested_string(pane, "id")
    )
    workspace_name = (
        _string(item.get("workspace_id"))
        or _string(item.get("workspaceId"))
        or _string(item.get("workspace_name"))
        or _string(item.get("workspaceName"))
        or _string(workspace)
        or _nested_string(workspace, "name")
        or _nested_string(workspace, "id")
    )
    state = _state(item.get("state") or item.get("status") or item.get("agent_status"))
    agent = _string(item.get("agent"))

    return HerdrAgent(
        id=_agent_id(item, pane_id),
        label=_string(item.get("label") or item.get("name") or item.get("title")) or agent,
        type=agent or _string(item.get("type") or item.get("agent_type") or item.get("agentType")),
        state=state,
        pane_id=pane_id,
        workspace=workspace_name,
    )


def _pane_from_item(item: dict[str, Any]) -> HerdrPane:
    workspace = item.get("workspace")
    agent = item.get("agent")

    workspace_name = (
        _string(item.get("workspace_id"))
        or _string(item.get("workspaceId"))
        or _string(item.get("workspace_name"))
        or _string(item.get("workspaceName"))
        or _string(workspace)
        or _nested_string(workspace, "name")
        or _nested_string(workspace, "id")
    )
    agent_id = (
        _string(item.get("agent_id"))
        or _string(item.get("agentId"))
        or _nested_string(agent, "id")
    )
    state = _state(item.get("state") or item.get("status") or item.get("agent_status"))

    return HerdrPane(
        id=_string(item.get("pane_id") or item.get("paneId") or item.get("id")),
        label=_string(item.get("label") or item.get("name") or item.get("title")),
        state=state,
        workspace=workspace_name,
        agent_id=agent_id,
    )


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""


def _nested_string(value: Any, key: str) -> str:
    if not isinstance(value, dict):
        return ""
    return _string(value.get(key))


def _agent_id(item: dict[str, Any], pane_id: str) -> str:
    if "agent" in item:
        return pane_id
    return _string(item.get("id") or item.get("agent_id") or item.get("agentId")) or pane_id


def _state(value: Any) -> str:
    state = _string(value).lower()
    return state if state in KNOWN_STATES else "unknown"
