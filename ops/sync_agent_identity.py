#!/usr/bin/env python3
"""
sync_agent_identity.py — Single source of truth for agent identity, applied
DYNAMICALLY everywhere. NOTHING is maintained by hand.

Derives the canonical roster from the LIVE herdr workspace and propagates it to
every place that needs it:

  1. Whitelist JSON   (~/.config/herdmaster/agent_whitelist.json)
       consumed by the herdmaster metrics exporter and the remediation purge.
  2. Control-plane API token mirror (~/.config/herdmaster/herdmaster.token)
       so the remediation webhook authenticates without a stale token.
  3. `agent_allowlist` in every herdmaster config.toml (live runtime + ~/.config)
       inserted/updated idempotently under [watchdog].
  4. A managed pane→label map comment block in each config.toml (between markers).

Idempotent and safe to run on a timer. Run standalone or import `sync()`.

Usage:
    python3 sync_agent_identity.py [--print]
Env overrides:
    HERDR_BIN, AGENT_WHITELIST_FILE, HERDMASTER_TOKEN_SRC, HM_CONFIG_TARGETS
    (HM_CONFIG_TARGETS = ':'-separated list of config.toml paths)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERDR_BIN = os.environ.get("HERDR_BIN", "herdr")
WHITELIST_FILE = Path(os.environ.get(
    "AGENT_WHITELIST_FILE",
    os.path.expanduser("~/.config/herdmaster/agent_whitelist.json"),
))
TOKEN_SRC = Path(os.environ.get("HERDMASTER_TOKEN_SRC", "/tmp/aop-ops-runtime/herdmaster.token"))
TOKEN_DST = WHITELIST_FILE.parent / "herdmaster.token"

_DEFAULT_TARGETS = [
    "/tmp/aop-ops-runtime/herdmaster.config.toml",
    os.path.expanduser("~/.config/herdmaster/config.toml"),
]
CONFIG_TARGETS = [
    p for p in (os.environ.get("HM_CONFIG_TARGETS", "").split(":") or [])
    if p
] or _DEFAULT_TARGETS

MAP_BEGIN = "# >>> managed agent map (sync_agent_identity.py) >>>"
MAP_END = "# <<< managed agent map (sync_agent_identity.py) <<<"


def live_roster() -> list[dict]:
    """Return [{'id','label','type'}] from the live herdr workspace + cli."""
    out = subprocess.check_output([HERDR_BIN, "pane", "list"], text=True, stderr=subprocess.DEVNULL)
    panes = json.loads(out).get("result", {}).get("panes", [])
    roster = [
        {"id": p["pane_id"], "label": p.get("label") or p["pane_id"], "type": p.get("agent") or "unknown"}
        for p in panes
    ]
    roster.append({"id": "cli", "label": "CLI Operator", "type": "system"})
    return roster


def _toml_array(ids: list[str]) -> str:
    body = ",\n".join(f'  "{i}"' for i in ids)
    return f"agent_allowlist = [\n{body},\n]"


def _managed_map_block(roster: list[dict]) -> str:
    lines = [MAP_BEGIN, "# Auto-gerado do roster vivo do herdr — NÃO editar à mão."]
    for a in roster:
        if a["id"] == "cli":
            continue
        lines.append(f'#   {a["id"]:8} -> {a["label"]} ({a["type"]})')
    lines.append(MAP_END)
    return "\n".join(lines)


def _update_config(path: Path, ids: list[str], roster: list[dict]) -> str:
    """Idempotently set agent_allowlist + managed map block in one config.toml."""
    if not path.exists():
        return f"skip (absent): {path}"
    text = path.read_text(encoding="utf-8")
    original = text
    allowlist = _toml_array(ids)

    # 1. agent_allowlist: replace if present, else insert under [watchdog], else add section
    if re.search(r"(?m)^\s*agent_allowlist\s*=\s*\[", text):
        text = re.sub(r"(?ms)^\s*agent_allowlist\s*=\s*\[.*?\]", allowlist, text, count=1)
    elif re.search(r"(?m)^\[watchdog\]\s*$", text):
        text = re.sub(r"(?m)^(\[watchdog\]\s*)$", r"\1\n" + allowlist, text, count=1)
    else:
        text = text.rstrip() + f"\n\n[watchdog]\n{allowlist}\n"

    # 2. managed map comment block: replace if present, else append
    block = _managed_map_block(roster)
    if MAP_BEGIN in text and MAP_END in text:
        text = re.sub(re.escape(MAP_BEGIN) + r".*?" + re.escape(MAP_END), block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"

    if text == original:
        return f"unchanged: {path}"
    path.write_text(text, encoding="utf-8")
    return f"updated: {path}"


def sync() -> dict:
    roster = live_roster()
    ids = sorted({a["id"] for a in roster})

    # 1. whitelist json
    WHITELIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    WHITELIST_FILE.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")

    # 2. token mirror
    token_result = "no token source"
    if TOKEN_SRC.is_file():
        if not TOKEN_DST.exists() or TOKEN_DST.read_text() != TOKEN_SRC.read_text():
            shutil.copyfile(TOKEN_SRC, TOKEN_DST)
            token_result = f"synced -> {TOKEN_DST}"
        else:
            token_result = "token current"

    # 3 + 4. config.toml files
    config_results = [_update_config(Path(p), ids, roster) for p in CONFIG_TARGETS]

    return {
        "roster_ids": ids,
        "count": len(ids),
        "whitelist_file": str(WHITELIST_FILE),
        "token": token_result,
        "configs": config_results,
    }


if __name__ == "__main__":
    result = sync()
    if "--print" in sys.argv or True:
        print(json.dumps(result, indent=2, ensure_ascii=False))
