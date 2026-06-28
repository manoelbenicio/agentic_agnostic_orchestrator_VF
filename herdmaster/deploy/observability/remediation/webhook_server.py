#!/usr/bin/env python3
"""
HerdMaster Auto-Remediation Webhook Server
==========================================
Servidor HTTP leve que recebe alertas do Alertmanager e executa
ações de auto-remediation baseadas no tipo de alerta.

Porta: 9099
Endpoints:
  POST /webhook/log        → loga o alerta (todos)
  POST /webhook/remediate  → executa purge de agentes fantasmas (auto)
  POST /webhook/critical   → loga como crítico (escalação futura)
  GET  /health             → health check

Fluxo anti-falso-positivo:
  Prometheus detecta herdmaster_unlisted_agents_total > 0
  → Alertmanager FIRING → POST /webhook/remediate
  → purge_unlisted_agents() DELETE WHERE id NOT IN whitelist
  → Prometheus scrape 5s depois → herdmaster_unlisted_agents_total = 0
  → Alertmanager RESOLVED → POST /webhook/remediate (send_resolved=true)
  → loga resolução
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import time
from datetime import datetime, UTC
from pathlib import Path

# Process start time — used to expose a process uptime metric on /metrics.
_START_TIME = time.time()

# ── Configuração ──────────────────────────────────────────────────
PORT = int(os.environ.get("WEBHOOK_PORT", "9099"))
LOG_PATH = Path(os.environ.get(
    "REMEDIATION_LOG",
    Path.home() / ".config/herdmaster/remediation.log"
))

# ── HerdMaster HTTP API client ──────────────────────────────────────────
HM_API_BASE = os.environ.get("HERDMASTER_API", "http://127.0.0.1:8080")
# Token resolution order: HERDMASTER_TOKEN_FILE (kept in sync with the live
# control-plane token by AOP/ops) → HERDMASTER_TOKEN env → "admin" fallback.
# Reading from a file avoids the stale-hardcoded-token 401 trap when the
# control-plane rotates its API token on restart.
HM_API_TOKEN_FILE = os.environ.get("HERDMASTER_TOKEN_FILE", "/herdmaster-data/herdmaster.token")


def _resolve_token() -> str:
    try:
        with open(HM_API_TOKEN_FILE, encoding="utf-8") as f:
            tok = f.read().strip()
            if tok:
                return tok
    except OSError:
        pass
    return os.environ.get("HERDMASTER_TOKEN", "admin")


HM_API_TOKEN = _resolve_token()

# Whitelist canônica.
#
# Fonte de verdade DINÂMICA: o arquivo gerado de hora em hora por
# AOP/ops/agent-registry-reconcile.sh a partir do roster vivo do herdr.
# Lido a cada checagem (sem necessitar restart), de forma que a remediation
# nunca opere com nomes obsoletos. Se o arquivo não existir/for inválido,
# cai para o fallback embutido (apenas o orquestrador 'cli', para nunca
# purgar tudo por engano).
AGENT_WHITELIST_FILE = os.environ.get(
    "AGENT_WHITELIST_FILE", "/herdmaster-data/agent_whitelist.json"
)
_FALLBACK_WHITELIST: frozenset[str] = frozenset({"cli"})


def load_whitelist() -> frozenset[str]:
    """Load the canonical agent whitelist from the reconciler-managed file."""
    try:
        with open(AGENT_WHITELIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ids = {str(x) for x in data if str(x).strip()}
        if ids:
            return frozenset(ids)
        log.warning("whitelist file %s is empty; using fallback", AGENT_WHITELIST_FILE)
    except FileNotFoundError:
        log.warning("whitelist file %s not found; using fallback", AGENT_WHITELIST_FILE)
    except (json.JSONDecodeError, OSError, TypeError) as e:
        log.error("failed to load whitelist %s: %s; using fallback", AGENT_WHITELIST_FILE, e)
    return _FALLBACK_WHITELIST


# Snapshot at import for logging/metrics; purge re-reads the file each time.
AGENT_WHITELIST: frozenset[str] = load_whitelist()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s UTC [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("hm.remediation")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def _log_remediation(action: str, detail: str, result: str) -> None:
    """Appends a structured line to the remediation audit log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": _utc_now(), "action": action, "detail": detail, "result": result})
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    log.info("AUDIT | action=%s | %s | result=%s", action, detail, result)

# ── HerdMaster API helpers ────────────────────────────────────────────────────

def _hm_request(method: str, path: str, *, timeout: int = 10) -> dict:
    """Make an authenticated request to the HerdMaster HTTP API."""
    import urllib.request, urllib.error
    url = f"{HM_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        method=method,
        headers={"Authorization": f"Bearer {_resolve_token()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {path}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"Request to {path} failed: {e}") from e


def purge_unlisted_agents() -> dict:
    """
    Identifies and removes ghost agents via the HerdMaster HTTP API.

    Uses DELETE /agents/{id} for each agent not in AGENT_WHITELIST.
    This approach:
      - Avoids ALL SQLite lock contention (single DB writer = HerdMaster)
      - Is idempotent and safe to call concurrently
      - Respects HerdMaster's own transaction boundaries
    """
    try:
        # 0. Re-read the canonical whitelist (kept fresh hourly by the reconciler)
        whitelist = load_whitelist()

        # 1. Fetch current agent list from HerdMaster API
        response = _hm_request("GET", "/agents")
        agents = response.get("data", [])
        if not isinstance(agents, list):
            return {"deleted_count": 0, "deleted_ids": [], "error": "unexpected agents response format"}

        # 2. Identify unlisted agents
        unlisted = [a for a in agents if a.get("id") not in whitelist]

        if not unlisted:
            return {"deleted_count": 0, "deleted_ids": []}

        # 3. Delete each unlisted agent via API (HerdMaster owns the DB write)
        deleted = []
        errors = []
        for agent in unlisted:
            agent_id = agent.get("id", "")
            try:
                _hm_request("DELETE", f"/agents/{agent_id}")
                deleted.append({"id": agent_id, "label": agent.get("label", "")})
                log.warning("PURGED ghost agent via API: %r (%s)", agent_id, agent.get("label", ""))
            except RuntimeError as e:
                errors.append(str(e))
                log.error("Failed to delete agent %r via API: %s", agent_id, e)

        result: dict = {"deleted_count": len(deleted), "deleted_ids": deleted}
        if errors:
            result["errors"] = errors
        return result

    except RuntimeError as e:
        return {"deleted_count": 0, "deleted_ids": [], "error": str(e)}


# ── Webhook Handler ───────────────────────────────────────────────────────────

class WebhookHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # suppress default access log spam
        log.debug("HTTP %s", fmt % args)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _respond(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _respond_text(self, status: int, text: str) -> None:
        """Respond with Prometheus text exposition format (UTF-8)."""
        data = text.encode("utf-8")
        self.send_response(status)
        # version=0.0.4 is the Prometheus text exposition content type.
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _metrics_exposition(self) -> str:
        """Build the Prometheus metrics payload for this webhook server."""
        uptime = max(0.0, time.time() - _START_TIME)
        lines = [
            "# HELP herdmaster_remediation_up Remediation webhook server liveness (1 = up).",
            "# TYPE herdmaster_remediation_up gauge",
            "herdmaster_remediation_up 1",
            "# HELP herdmaster_remediation_uptime_seconds Seconds since the webhook server started.",
            "# TYPE herdmaster_remediation_uptime_seconds gauge",
            f"herdmaster_remediation_uptime_seconds {uptime:.3f}",
            "# HELP herdmaster_remediation_whitelist_size Number of whitelisted agents.",
            "# TYPE herdmaster_remediation_whitelist_size gauge",
            f"herdmaster_remediation_whitelist_size {len(load_whitelist())}",
        ]
        return "\n".join(lines) + "\n"

    def do_GET(self):
        if self.path == "/metrics":
            self._respond_text(200, self._metrics_exposition())

        elif self.path == "/health":
            self._respond(200, {"ok": True, "ts": _utc_now(), "api": HM_API_BASE})

        else:
            self._respond(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        body = self._read_body()
        alerts = body.get("alerts", [])
        status = body.get("status", "unknown")  # "firing" or "resolved"

        if self.path == "/webhook/log":
            self._handle_log(alerts, status)

        elif self.path == "/webhook/remediate":
            self._handle_remediate(alerts, status)

        elif self.path == "/webhook/critical":
            self._handle_critical(alerts, status)

        else:
            self._respond(404, {"ok": False, "error": "unknown webhook path"})

    def _handle_log(self, alerts: list, status: str) -> None:
        for alert in alerts:
            name = alert.get("labels", {}).get("alertname", "unknown")
            severity = alert.get("labels", {}).get("severity", "unknown")
            summary = alert.get("annotations", {}).get("summary", "")
            log.info("[%s] %s | %s | %s", status.upper(), name, severity, summary)
            _log_remediation("log", f"{name}:{status}", summary)
        self._respond(200, {"ok": True, "processed": len(alerts)})

    def _handle_remediate(self, alerts: list, status: str) -> None:
        """
        Core auto-remediation handler.
        On FIRING: executes whitelist purge.
        On RESOLVED: logs resolution only.
        """
        if status == "resolved":
            log.info("REMEDIATION RESOLVED — registry integrity restored")
            _log_remediation("resolved", "whitelist_purge", "alert resolved by Prometheus")
            self._respond(200, {"ok": True, "action": "resolved_logged"})
            return

        # FIRING → execute purge
        firing_names = [a.get("labels", {}).get("alertname", "") for a in alerts]
        log.warning("REMEDIATION TRIGGERED by: %s", firing_names)

        result = purge_unlisted_agents()

        if "error" in result:
            log.error("REMEDIATION FAILED: %s", result["error"])
            _log_remediation(
                "purge_failed",
                f"alerts={firing_names}",
                result["error"]
            )
            self._respond(500, {"ok": False, "error": result["error"]})
            return

        if result["deleted_count"] > 0:
            detail = f"deleted={[r['id'] for r in result['deleted_ids']]}"
            log.warning("REMEDIATION EXECUTED: %d agents purged | %s", result["deleted_count"], detail)
            _log_remediation("purge_executed", detail, f"deleted={result['deleted_count']}")
        else:
            log.info("REMEDIATION: no unlisted agents found (already clean)")
            _log_remediation("purge_noop", "no_unlisted_agents", "clean")

        self._respond(200, {
            "ok": True,
            "action": "purge_executed",
            "deleted_count": result["deleted_count"],
            "deleted_ids": result["deleted_ids"],
            "ts": _utc_now(),
        })

    def _handle_critical(self, alerts: list, status: str) -> None:
        for alert in alerts:
            name = alert.get("labels", {}).get("alertname", "unknown")
            summary = alert.get("annotations", {}).get("summary", "")
            log.critical("[CRITICAL/%s] %s | %s", status.upper(), name, summary)
            _log_remediation("critical", f"{name}:{status}", summary)
        # TODO: integrate Slack/PagerDuty/email here
        self._respond(200, {"ok": True, "processed": len(alerts), "escalation": "logged"})

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("HerdMaster Remediation Webhook Server starting on port %d", PORT)
    log.info("HerdMaster API: %s (token: %s)", HM_API_BASE, HM_API_TOKEN[:4] + "****")
    log.info("Whitelist (%d agents): %s", len(AGENT_WHITELIST), sorted(AGENT_WHITELIST))
    log.info("Audit log: %s", LOG_PATH)

    server = http.server.HTTPServer(("127.0.0.1", PORT), WebhookHandler)
    log.info("Listening on http://127.0.0.1:%d", PORT)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutdown requested")
        server.server_close()

if __name__ == "__main__":
    main()
