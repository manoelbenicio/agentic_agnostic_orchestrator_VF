"""Tests for HerdMaster authenticated HTTP client and token-aware wiring.

Covers:
- Probe returns True when token is valid and /status replies 200.
- Probe returns False on 401 (no/wrong token) or connection error.
- HerdMasterAuthClient injects Authorization header correctly.
- build_coupled_executors uses auth client when token present.
- build_coupled_executors degrades gracefully when token absent.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

import pytest

from coupling import CouplingPhase, build_coupled_executors
from coupling import wiring
from coupling.hm_client import HerdMasterAuthClient, herdmaster_authenticated_probe


# ---------------------------------------------------------------------------
# Fake HerdMaster HTTP server that enforces bearer-token auth
# ---------------------------------------------------------------------------

VALID_TOKEN = "test-secret-token-42"


class _FakeHerdMasterHandler(BaseHTTPRequestHandler):
    """Minimal HerdMaster HTTP mock: checks bearer token, returns 200 or 401."""

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {VALID_TOKEN}"

    def _send_json(self, code: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if not self._check_auth():
            self._send_json(401, {"ok": False, "error": {"code": "unauthorized", "message": "bearer token required"}})
            return
        if self.path == "/status":
            self._send_json(200, {"ok": True, "data": {"running": True}})
            return
        if self.path.startswith("/tasks"):
            self._send_json(200, {"ok": True, "data": {"task_id": "t-1", "state": "done"}})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self._check_auth():
            self._send_json(401, {"ok": False, "error": {"code": "unauthorized", "message": "bearer token required"}})
            return
        content_length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_length)
        self._send_json(200, {"ok": True, "data": {"task_id": "t-1", "state": "queued"}})

    def do_PATCH(self) -> None:
        if not self._check_auth():
            self._send_json(401, {"ok": False, "error": {"code": "unauthorized", "message": "bearer token required"}})
            return
        content_length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_length)
        self._send_json(200, {"ok": True, "data": {"task_id": "t-1", "state": "in_progress"}})

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Silence server logs during tests


class _MetricsOnlyHerdMasterHandler(_FakeHerdMasterHandler):
    """HerdMaster-compatible mock for builds that expose /metrics but not /status."""

    def do_GET(self) -> None:
        if not self._check_auth():
            self._send_json(401, {"ok": False, "error": {"code": "unauthorized", "message": "bearer token required"}})
            return
        if self.path == "/status":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if self.path == "/metrics":
            payload = b"# HELP herdmaster_up HerdMaster is up\nherdmaster_up 1\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._send_json(404, {"ok": False, "error": "not found"})


@pytest.fixture(scope="module")
def fake_hm_server():
    """Start a fake HerdMaster HTTP server on an ephemeral port."""
    server = HTTPServer(("127.0.0.1", 0), _FakeHerdMasterHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="module")
def metrics_only_hm_server():
    """Start a fake HerdMaster server where /metrics is the available probe."""
    server = HTTPServer(("127.0.0.1", 0), _MetricsOnlyHerdMasterHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Probe tests
# ---------------------------------------------------------------------------

class TestAuthenticatedProbe:
    """herdmaster_authenticated_probe with a real HTTP server."""

    def test_probe_succeeds_with_valid_token(self, fake_hm_server: str) -> None:
        assert herdmaster_authenticated_probe(fake_hm_server, token=VALID_TOKEN) is True

    def test_probe_fails_without_token(self, fake_hm_server: str) -> None:
        """Without a token, HerdMaster returns 401 → probe returns False."""
        assert herdmaster_authenticated_probe(fake_hm_server, token=None) is False

    def test_probe_fails_with_wrong_token(self, fake_hm_server: str) -> None:
        assert herdmaster_authenticated_probe(fake_hm_server, token="wrong-token") is False

    def test_probe_fails_on_unreachable_host(self) -> None:
        assert herdmaster_authenticated_probe("http://127.0.0.1:1", token=VALID_TOKEN, timeout_s=0.1) is False

    def test_probe_falls_back_to_metrics_when_status_is_absent(self, metrics_only_hm_server: str) -> None:
        assert herdmaster_authenticated_probe(metrics_only_hm_server, token=VALID_TOKEN) is True

    def test_metrics_fallback_still_requires_valid_token(self, metrics_only_hm_server: str) -> None:
        assert herdmaster_authenticated_probe(metrics_only_hm_server, token="wrong-token") is False


# ---------------------------------------------------------------------------
# Auth client tests
# ---------------------------------------------------------------------------

class TestHerdMasterAuthClient:
    """HerdMasterAuthClient against the fake server."""

    def test_request_with_valid_token(self, fake_hm_server: str) -> None:
        client = HerdMasterAuthClient(base_url=fake_hm_server, token=VALID_TOKEN)
        result = client._request("GET", "/status")
        assert result.get("running") is True

    def test_request_without_token_raises_401(self, fake_hm_server: str) -> None:
        client = HerdMasterAuthClient(base_url=fake_hm_server, token="")
        with pytest.raises(RuntimeError, match="401"):
            client._request("GET", "/status")

    def test_request_with_wrong_token_raises_401(self, fake_hm_server: str) -> None:
        client = HerdMasterAuthClient(base_url=fake_hm_server, token="bad")
        with pytest.raises(RuntimeError, match="401"):
            client._request("GET", "/status")

    def test_post_with_valid_token(self, fake_hm_server: str) -> None:
        client = HerdMasterAuthClient(base_url=fake_hm_server, token=VALID_TOKEN)
        result = client._request("POST", "/tasks", {"title": "test"})
        assert result.get("state") == "queued"

    def test_patch_with_valid_token(self, fake_hm_server: str) -> None:
        client = HerdMasterAuthClient(base_url=fake_hm_server, token=VALID_TOKEN)
        result = client._request("PATCH", "/tasks/t-1", {"state": "in_progress"})
        assert result.get("state") == "in_progress"


# ---------------------------------------------------------------------------
# Wiring integration tests (token-aware)
# ---------------------------------------------------------------------------

class FallbackTerminalAdapter:
    pass


class FallbackQueueClient:
    pass


class TestBuildCoupledExecutorsWithToken:
    """build_coupled_executors with herdmaster_token parameter."""

    def test_uses_auth_client_when_token_and_hm_available(self, fake_hm_server: str, monkeypatch) -> None:
        """With valid token + reachable HM → auth client is injected."""
        monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)

        coupled = build_coupled_executors(
            fallback_terminal_adapter=FallbackTerminalAdapter(),
            fallback_queue_client=FallbackQueueClient(),
            herdmaster_url=fake_hm_server,
            herdmaster_token=VALID_TOKEN,
        )

        # Socket executor should use the authenticated client
        assert type(coupled.socket.queue_client).__name__ == "HerdMasterAuthClient"
        # Terminal is degraded (no herdr socket), so phase is DEGRADED
        assert coupled.status.phase == CouplingPhase.DEGRADED
        assert "terminal degraded" in str(coupled.status.last_error)
        # But socket should NOT be degraded
        assert "socket degraded" not in str(coupled.status.last_error)

    def test_fallback_when_token_absent(self, fake_hm_server: str, monkeypatch) -> None:
        """Without token → probe fails (401) → falls back to queue client."""
        monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)

        fallback_qc = FallbackQueueClient()
        coupled = build_coupled_executors(
            fallback_terminal_adapter=FallbackTerminalAdapter(),
            fallback_queue_client=fallback_qc,
            herdmaster_url=fake_hm_server,
            herdmaster_token=None,
        )

        assert coupled.status.phase == CouplingPhase.DEGRADED
        assert "socket degraded" in str(coupled.status.last_error)
        assert coupled.socket.queue_client is fallback_qc

    def test_fallback_when_token_wrong(self, fake_hm_server: str, monkeypatch) -> None:
        """Wrong token → probe fails (401) → falls back."""
        monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)

        fallback_qc = FallbackQueueClient()
        coupled = build_coupled_executors(
            fallback_terminal_adapter=FallbackTerminalAdapter(),
            fallback_queue_client=fallback_qc,
            herdmaster_url=fake_hm_server,
            herdmaster_token="wrong-token",
        )

        assert coupled.status.phase == CouplingPhase.DEGRADED
        assert "socket degraded" in str(coupled.status.last_error)
        assert coupled.socket.queue_client is fallback_qc

    def test_fallback_when_hm_unreachable_with_token(self, monkeypatch) -> None:
        """Token set but HM unreachable → falls back with descriptive message."""
        monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)

        fallback_qc = FallbackQueueClient()
        coupled = build_coupled_executors(
            fallback_terminal_adapter=FallbackTerminalAdapter(),
            fallback_queue_client=fallback_qc,
            herdmaster_url="http://127.0.0.1:1",
            herdmaster_token=VALID_TOKEN,
        )

        assert coupled.status.phase == CouplingPhase.DEGRADED
        assert "token set but probe failed" in str(coupled.status.last_error)
        assert coupled.socket.queue_client is fallback_qc

    def test_no_token_no_hm_old_behavior_preserved(self, monkeypatch) -> None:
        """Without token + HM unavailable → classic ADR-001 fallback (backward compat)."""
        monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)
        monkeypatch.setattr(wiring, "herdmaster_http_probe", lambda base_url, timeout_s=1.0: False)

        fallback_qc = FallbackQueueClient()
        coupled = build_coupled_executors(
            fallback_terminal_adapter=FallbackTerminalAdapter(),
            fallback_queue_client=fallback_qc,
            herdmaster_url="http://127.0.0.1:8080",
            herdmaster_token=None,
        )

        assert coupled.status.phase == CouplingPhase.DEGRADED
        assert "socket degraded: HerdMaster HTTP unavailable" in str(coupled.status.last_error)
        assert coupled.socket.queue_client is fallback_qc
