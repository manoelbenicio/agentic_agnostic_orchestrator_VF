"""Authenticated HTTP client for HerdMaster's control API.

HerdMaster's HTTP mode always requires a bearer token (see
HerdMaster/src/herdmaster/api/server.py L13-14, L257-260).
Without the token every request returns 401.

This module provides:
- ``HerdMasterAuthClient``: a thin wrapper that injects the bearer token
  into ``HerdMasterHttpQueueClient`` requests AND the probe.
- ``herdmaster_authenticated_probe``: a probe function that includes
  the bearer token in the ``/status`` health-check.

When the env var ``HERDMASTER_TOKEN`` is absent the coupling layer
must fall back to the in-memory queue client (NFR-009 graceful
degradation via ADR-001).
"""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request


def herdmaster_authenticated_probe(
    base_url: str = "http://127.0.0.1:8080",
    token: str | None = None,
    timeout_s: float = 1.0,
) -> bool:
    """Return True when HerdMaster's HTTP API is reachable.

    When *token* is provided the request carries an ``Authorization:
    Bearer <token>`` header — required by HerdMaster HTTP mode.
    When *token* is ``None`` the request is unauthenticated and
    HerdMaster will return 401, making the probe return ``False``.

    The primary probe is ``/status``. Some HerdMaster builds expose only
    authenticated ``/metrics`` during early startup or older HTTP modes, so a
    missing ``/status`` falls back to ``/metrics`` before declaring the HTTP side
    unavailable.
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    status = _probe_status_endpoint(base_url, headers, timeout_s)
    if status is not None:
        return status
    return _probe_metrics_endpoint(base_url, headers, timeout_s)


def _probe_status_endpoint(base_url: str, headers: dict[str, str], timeout_s: float) -> bool | None:
    """Probe /status.

    ``None`` means the endpoint is absent and the caller may try a secondary
    endpoint. ``False`` means HerdMaster rejected the request or was unavailable.
    """
    url = f"{base_url.rstrip('/')}/status"
    req = request.Request(url, method="GET", headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        return None if exc.code in {404, 405} else False
    except (OSError, ValueError, error.URLError):
        return False

    return isinstance(payload, dict) and bool(payload.get("ok", True))


def _probe_metrics_endpoint(base_url: str, headers: dict[str, str], timeout_s: float) -> bool:
    """Probe authenticated /metrics as the startup-compatible fallback."""
    req = request.Request(f"{base_url.rstrip('/')}/metrics", method="GET", headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_s) as response:
            response.read(1)
            return 200 <= response.status < 300
    except (OSError, error.URLError):
        return False


class HerdMasterAuthClient:
    """``HerdMasterHttpQueueClient`` wrapper that injects bearer token.

    The underlying ``_request`` method in ``HerdMasterHttpQueueClient``
    builds ``urllib.request.Request`` objects with ``Content-Type: application/json``.
    This client extends that by adding ``Authorization: Bearer <token>``
    to every outbound request.

    If the token is empty or ``None``, the client is still constructable
    but every HTTP call will fail with 401 at runtime — callers should
    gate usage on ``token is not None`` before constructing.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        token: str = "",
        timeout_s: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s

    # --- internal --------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from urllib import parse

        query_text = f"?{parse.urlencode(query)}" if query else ""
        body = None if payload is None else json.dumps(payload).encode("utf-8")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = request.Request(
            f"{self.base_url}{path}{query_text}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(
                f"HerdMaster API returned HTTP {exc.code}: {exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"HerdMaster API request failed: {exc}") from exc

        if not isinstance(decoded, dict) or not decoded.get("ok", False):
            raise RuntimeError(f"HerdMaster API returned an error: {decoded!r}")

        data = decoded.get("data", {})
        return data if isinstance(data, dict) else {"data": data}

    # --- SocketQueueClient protocol --------------------------------------

    async def enqueue(self, task: Any) -> dict[str, Any]:
        import asyncio

        payload = {
            "title": task.task_id,
            "prompt": task.prompt,
            "task_id": task.task_id,
            "project_id": task.project_id,
            "assigned_to": task.assignee_runtime,
            "created_by": task.tenant_id,
            "timeout_seconds": task.budget.timeout_seconds or 1800,
        }
        return await asyncio.to_thread(self._request, "POST", "/tasks", payload)

    async def claim(self, task: Any) -> dict[str, Any]:
        import asyncio
        from urllib import parse

        return await asyncio.to_thread(
            self._request,
            "GET",
            "/tasks",
            None,
            {"assigned_to": task.assignee_runtime, "project_id": task.project_id},
        )

    async def mark_running(self, task: Any) -> dict[str, Any]:
        import asyncio
        from urllib import parse

        return await asyncio.to_thread(
            self._request,
            "PATCH",
            f"/tasks/{parse.quote(task.task_id)}",
            {"state": "in_progress"},
        )

    async def poll(self, task: Any) -> dict[str, Any]:
        import asyncio
        from urllib import parse

        return await asyncio.to_thread(
            self._request,
            "GET",
            f"/tasks/{parse.quote(task.task_id)}",
        )
