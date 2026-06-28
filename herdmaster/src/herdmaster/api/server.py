"""Local Control API server for HerdMaster.

The primary transport is newline-delimited JSON over a Unix domain socket.
Each request may be either a compact HTTP-like envelope::

    {"method": "GET", "path": "/status", "body": {}, "query": {}}

or a JSON-RPC-style envelope where ``method`` contains the route::

    {"jsonrpc": "2.0", "method": "GET /status", "params": {}}

The optional HTTP listener is intentionally stdlib-only and is restricted to
localhost. HTTP mode always requires a bearer token because it exposes an
unauthenticated local control plane otherwise.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formatdate
import hashlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from herdmaster.acl.engine import AclDenied, AclEngine
from herdmaster.bus.messages import MessageType, new_message
from herdmaster.bus.server import MessageBusServer
from herdmaster.config import ConfigError, HerdMasterConfig, load_config, validate_config
from herdmaster.db.repositories import AgentRepo, MessageRepo, ProjectRepo, TaskRepo
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.project.eta import EtaEstimator
from herdmaster.project.planner import ProjectPlanner
from herdmaster.telemetry import ReconcileConfig, build_board

log = logging.getLogger(__name__)

# Maximum seconds a client connection may be idle before it is closed.
# Prevents resource exhaustion from stalled or misbehaving clients.
_CLIENT_IDLE_TIMEOUT_S: float = 60.0

JsonDict = dict[str, Any]
ReloadHook = Callable[[HerdMasterConfig], Any]
RestartHook = Callable[[str], Any]


class ApiError(Exception):
    """Structured API error returned to Unix-socket and HTTP clients."""

    def __init__(self, status: int, code: str, message: str, *, details: Any = None) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

    def to_payload(self) -> JsonDict:
        payload: JsonDict = {"ok": False, "error": {"code": self.code, "message": self.message}}
        if self.details is not None:
            payload["error"]["details"] = self.details
        return payload


@dataclass(frozen=True, slots=True)
class _Request:
    method: str
    path: str
    query: dict[str, str]
    body: JsonDict
    request_id: Any = None
    stream: bool = False


class ControlApiServer:
    """Async local Control API over Unix socket plus optional localhost HTTP."""

    def __init__(
        self,
        *,
        config: HerdMasterConfig,
        planner: ProjectPlanner,
        queue: TaskQueue,
        agents: AgentRepo,
        tasks: TaskRepo,
        projects: ProjectRepo,
        messages: MessageRepo,
        bus: MessageBusServer,
        acl: AclEngine,
        socket_path: str | Path | None = None,
        http_enabled: bool = False,
        reload_config: ReloadHook | None = None,
        restart_agent: RestartHook | None = None,
    ) -> None:
        self.config = config
        self.planner = planner
        self.queue = queue
        self.agents = agents
        self.tasks = tasks
        self.projects = projects
        self.messages = messages
        self.bus = bus
        self.acl = acl
        self.socket_path = Path(socket_path or config.paths.socket).expanduser()
        self.http_enabled = http_enabled
        self.reload_config_hook = reload_config
        self.restart_agent_hook = restart_agent
        self.started_at = datetime.now(UTC)

        self._unix_server: asyncio.AbstractServer | None = None
        self._http_server: asyncio.AbstractServer | None = None
        self._running = False
        self._stream_tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start Unix socket and optional localhost HTTP listeners."""

        if self._running:
            return
        self._validate_security()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._unix_server = await asyncio.start_unix_server(self._handle_socket_client, path=str(self.socket_path))
        self._running = True
        log.info("control_api_started", extra={"transport": "unix", "socket": str(self.socket_path)})

        if self.http_enabled:
            self._http_server = await asyncio.start_server(
                self._handle_http_client,
                host=self.config.api.bind,
                port=self.config.api.port,
            )
            log.info(
                "control_api_started",
                extra={"transport": "http", "bind": self.config.api.bind, "port": self.config.api.port},
            )

    async def stop(self) -> None:
        """Stop listeners, close stream clients, and unlink the Unix socket."""

        if not self._running:
            return
        self._running = False
        for task in list(self._stream_tasks):
            task.cancel()
        if self._stream_tasks:
            await asyncio.gather(*self._stream_tasks, return_exceptions=True)
        self._stream_tasks.clear()

        for server in (self._http_server, self._unix_server):
            if server is not None:
                server.close()
                await server.wait_closed()
        self._http_server = None
        self._unix_server = None
        if self.socket_path.exists():
            self.socket_path.unlink()
        log.info("control_api_stopped")

    async def __aenter__(self) -> "ControlApiServer":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()

    def _validate_security(self) -> None:
        if self.config.api.bind not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Control API HTTP bind must be localhost-only")
        if self.http_enabled and not self.config.api.token:
            raise ValueError("HTTP Control API requires api.token")

    async def _handle_socket_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while self._running and not writer.is_closing():
                try:
                    raw = await asyncio.wait_for(reader.readline(), timeout=_CLIENT_IDLE_TIMEOUT_S)
                except asyncio.TimeoutError:
                    break
                if not raw:
                    break
                try:
                    request = _socket_request(raw.decode())
                    if request.stream and request.path == "/messages/stream":
                        await self._stream_messages(writer)
                        break
                    payload = await self._dispatch(request)
                    await _write_json_line(writer, _socket_response(payload, request.request_id))
                except ApiError as exc:
                    await _write_json_line(writer, _socket_response(exc.to_payload(), None))
                except Exception as exc:
                    log.exception("control_api_socket_error")
                    # Recover the Postgres connection from InFailedTransaction
                    # state so that subsequent requests on the same daemon are
                    # not permanently broken by a single failed SQL operation.
                    self._recover_connection()
                    err = ApiError(500, "internal_error", str(exc))
                    await _write_json_line(writer, _socket_response(err.to_payload(), None))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _handle_http_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await _read_http_request(reader)
            if request is None:
                writer.close()
                await writer.wait_closed()
                return
            if not self._authorized_http(request["headers"]):
                await _write_http_response(writer, 401, {"ok": False, "error": {"code": "unauthorized", "message": "bearer token required"}})
                return
            if request["path"] == "/messages/stream":
                if request["headers"].get("upgrade", "").lower() == "websocket":
                    await _write_websocket_handshake(writer, request["headers"])
                    await self._stream_messages(writer, websocket=True)
                else:
                    await _write_http_stream_headers(writer)
                    await self._stream_messages(writer, http=True)
                return
            api_request = _Request(
                str(request["method"]),
                str(request["path"]),
                dict(request["query"]),
                request["body"] if isinstance(request["body"], dict) else {},
            )
            payload = await self._dispatch(api_request)
            await _write_http_response(writer, 200, payload)
        except ApiError as exc:
            await _write_http_response(writer, exc.status, exc.to_payload())
        except Exception as exc:
            log.exception("control_api_http_error")
            self._recover_connection()
            err = ApiError(500, "internal_error", str(exc))
            await _write_http_response(writer, 500, err.to_payload())
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    def _authorized_http(self, headers: dict[str, str]) -> bool:
        expected = self.config.api.token
        value = headers.get("authorization", "")
        return value == f"Bearer {expected}"

    def _recover_connection(self) -> None:
        """Rollback repository connections to clear InFailedTransaction state.

        After an unhandled database error the Postgres connection may be stuck
        in an aborted transaction.  A rollback clears this state so subsequent
        API requests are not permanently broken.
        """
        for repo in (self.tasks, self.agents, self.projects, self.messages):
            try:
                repo.conn.rollback()
            except Exception:
                log.warning("connection_recovery_rollback_failed", exc_info=True)

    async def _dispatch(self, request: _Request) -> JsonDict:
        method = request.method.upper()
        parts = [part for part in request.path.strip("/").split("/") if part]
        log.info("control_api_request", extra={"method": method, "path": request.path})

        if not parts:
            raise ApiError(404, "not_found", "unknown endpoint")
        if parts[0] == "projects":
            return await self._projects(method, parts, request)
        if parts[0] == "tasks":
            return await self._tasks(method, parts, request)
        if parts[0] == "agents":
            return await self._agents(method, parts, request)
        if parts[0] == "messages":
            return await self._messages(method, parts, request)
        if parts[0] == "status":
            if len(parts) == 1 and method == "GET":
                return self._status()
            raise ApiError(405, "method_not_allowed", "unsupported status route")
        if parts[0] == "metrics":
            if len(parts) == 1 and method == "GET":
                return {"ok": True, "content_type": "text/plain; version=0.0.4", "data": self._prometheus_metrics()}
            raise ApiError(405, "method_not_allowed", "unsupported metrics route")
        if parts[0] == "observability":
            if parts == ["observability", "board"] and method == "GET":
                return {
                    "ok": True,
                    "data": build_board(
                        self.tasks,
                        self.agents,
                        messages=self.messages,
                        config=ReconcileConfig(prompt_dir=self.config.paths.config_dir / "prompts"),
                    ),
                }
            raise ApiError(405, "method_not_allowed", "unsupported observability route")
        if parts[0] == "config":
            if parts == ["config", "reload"] and method == "POST":
                return await self._reload_config(request.body)
            raise ApiError(405, "method_not_allowed", "unsupported config route")
        raise ApiError(404, "not_found", f"unknown endpoint {method} {request.path}")

    async def _projects(self, method: str, parts: list[str], request: _Request) -> JsonDict:
        if len(parts) == 1 and method == "POST":
            body = request.body
            name = _required(body, "name")
            scope = str(body.get("scope") or body.get("full_scope_prompt") or "")
            if not scope:
                raise ApiError(400, "bad_request", "scope is required")
            project = await self.planner.create_project(
                name,
                scope,
                deadline=_optional_str(body.get("deadline")),
                created_by=_optional_str(body.get("created_by")),
                template=_optional_str(body.get("template")),
                orchestrator_id=_optional_str(body.get("orchestrator_id")),
                orchestrator_output=_optional_str(body.get("orchestrator_output")),
            )
            return {"ok": True, "data": self._project_detail(str(project["id"]))}

        if len(parts) == 1 and method == "GET":
            return {"ok": True, "data": [self._project_summary(item) for item in self.projects.list(state=request.query.get("state"))]}

        if len(parts) < 2:
            raise ApiError(405, "method_not_allowed", "unsupported projects route")
        project_id = parts[1]

        if len(parts) == 2 and method == "GET":
            return {"ok": True, "data": self._project_detail(project_id)}
        if len(parts) == 2 and method == "PATCH":
            body = request.body
            if "state" in body:
                if not self.projects.update_state(project_id, str(body["state"])):
                    raise ApiError(404, "not_found", "project not found")
                return {"ok": True, "data": self._project_detail(project_id)}
            result = self.planner.approve_project(
                project_id,
                decision=str(body.get("decision") or "accept"),
                squad=body.get("squad") if isinstance(body.get("squad"), list) else None,
                eta=body.get("eta") if isinstance(body.get("eta"), dict) else None,
                assignments=body.get("assignments") if isinstance(body.get("assignments"), list) else None,
                human_notes=_optional_str(body.get("human_notes") or body.get("notes")),
            )
            return {"ok": True, "data": {"project": self._project_detail(project_id), "task_ids": result.task_ids}}
        if len(parts) == 2 and method == "DELETE":
            project = self._require_project(project_id)
            for task in self.tasks.list(project_id=project_id):
                if str(task.get("state")) not in {"done", "failed", "timeout", "cancelled"}:
                    self.queue.cancel(str(task["id"]))
            self.projects.update_state(str(project["id"]), "cancelled")
            return {"ok": True, "data": self._project_detail(project_id)}
        if len(parts) == 3 and parts[2] == "approve" and method == "POST":
            body = request.body
            result = self.planner.approve_project(
                project_id,
                decision=str(body.get("decision") or "accept"),
                squad=body.get("squad") if isinstance(body.get("squad"), list) else None,
                eta=body.get("eta") if isinstance(body.get("eta"), dict) else None,
                assignments=body.get("assignments") if isinstance(body.get("assignments"), list) else None,
                human_notes=_optional_str(body.get("human_notes") or body.get("notes")),
            )
            return {"ok": True, "data": {"project": self._project_detail(project_id), "task_ids": result.task_ids}}
        if len(parts) == 3 and parts[2] == "eta" and method == "GET":
            project = self._require_project(project_id)
            analysis = project.get("orchestrator_analysis") if isinstance(project.get("orchestrator_analysis"), dict) else {}
            estimate = EtaEstimator().estimate(
                list(analysis.get("tasks") or []),
                list(project.get("squad_approved") or project.get("squad_recommendation") or analysis.get("squad") or []),
                self.agents.list(),
                str(project.get("complexity_tier") or analysis.get("complexity_tier") or "M"),
            )
            return {
                "ok": True,
                "data": {
                    "optimistic_hours": estimate.optimistic_hours,
                    "expected_hours": estimate.expected_hours,
                    "pessimistic_hours": estimate.pessimistic_hours,
                    "rationale": estimate.rationale,
                },
            }
        if len(parts) == 3 and parts[2] == "tasks" and method == "GET":
            return {"ok": True, "data": self.tasks.list(project_id=project_id)}
        raise ApiError(405, "method_not_allowed", "unsupported projects route")

    async def _tasks(self, method: str, parts: list[str], request: _Request) -> JsonDict:
        if len(parts) == 1 and method == "POST":
            body = request.body
            task_id = self.queue.enqueue(
                _required(body, "title"),
                _required(body, "prompt"),
                project_id=_optional_str(body.get("project_id")),
                description=_optional_str(body.get("description")),
                priority=body.get("priority", "normal"),
                assigned_to=_optional_str(body.get("assigned_to") or body.get("agent")),
                depends_on=body.get("depends_on") if isinstance(body.get("depends_on"), list) else None,
                created_by=_optional_str(body.get("created_by")),
                max_retries=int(body.get("max_retries", 3)),
                timeout_seconds=int(body.get("timeout_seconds", 1800)),
                estimate_minutes=_optional_int(body.get("estimate_minutes")),
                subtasks=[str(item) for item in body.get("subtasks", [])] if isinstance(body.get("subtasks"), list) else None,
                acceptance_criteria=[str(item) for item in body.get("acceptance_criteria", [])] if isinstance(body.get("acceptance_criteria"), list) else None,
            )
            return {"ok": True, "data": self.tasks.get(task_id)}
        if len(parts) == 1 and method == "GET":
            return {
                "ok": True,
                "data": self.tasks.list(
                    state=request.query.get("state"),
                    assigned_to=request.query.get("assigned_to"),
                    project_id=request.query.get("project_id"),
                ),
            }
        if len(parts) == 3 and parts[2] == "ask" and method == "POST":
            task_id = parts[1]
            reason = str(request.body.get("reason", "No reason provided"))
            if not self.tasks.set_blocked(task_id, reason):
                raise ApiError(404, "not_found", "task not found")
            return {"ok": True, "data": self.tasks.get(task_id)}
        if len(parts) == 3 and parts[2] == "checkin" and method == "POST":
            task_id = parts[1]
            agent_id = _required(request.body, "agent_id")
            if not self.tasks.checkin(task_id, agent_id):
                raise ApiError(404, "not_found", "task not found")
            return {"ok": True, "data": self.tasks.get(task_id)}
        if len(parts) == 3 and parts[2] == "complete" and method == "POST":
            task_id = parts[1]
            agent_id = _required(request.body, "agent_id")
            evidence = _required(request.body, "evidence")
            if not self.tasks.complete(task_id, completed_by=agent_id, evidence=evidence):
                raise ApiError(404, "not_found", "task not found")
            return {"ok": True, "data": self.tasks.get(task_id)}
        if len(parts) == 3 and parts[2] == "fail" and method == "POST":
            task_id = parts[1]
            agent_id = _required(request.body, "agent_id")
            reason = _required(request.body, "reason")
            if not self.tasks.fail(task_id, reason, agent_id=agent_id):
                raise ApiError(404, "not_found", "task not found")
            return {"ok": True, "data": self.tasks.get(task_id)}
        if len(parts) == 3 and parts[2] == "progress" and method == "POST":
            task_id = parts[1]
            subtask = _required(request.body, "subtask")
            done = bool(request.body.get("done", True))
            agent_id = _optional_str(request.body.get("agent_id"))
            try:
                updated = self.tasks.progress_subtask(task_id, subtask, done=done, agent_id=agent_id)
            except IndexError as exc:
                raise ApiError(400, "bad_request", str(exc)) from exc
            if not updated:
                raise ApiError(404, "not_found", "task not found")
            return {"ok": True, "data": self.tasks.get(task_id)}
            
        if len(parts) != 2:
            raise ApiError(405, "method_not_allowed", "unsupported tasks route")
        task_id = parts[1]
        if method == "GET":
            task = self.tasks.get(task_id)
            if task is None:
                raise ApiError(404, "not_found", "task not found")
            return {"ok": True, "data": task}
        if method == "PATCH":
            return {"ok": True, "data": self._patch_task(task_id, request.body)}
        if method == "DELETE":
            return {"ok": True, "data": self.queue.cancel(task_id)}
        raise ApiError(405, "method_not_allowed", "unsupported tasks route")

    def _patch_task(self, task_id: str, body: JsonDict) -> JsonDict:
        action = str(body.get("action") or "").lower()
        if action == "cancel" or body.get("state") == "cancelled":
            return self.queue.cancel(task_id)
        if action == "reassign":
            result = self.queue.reassign(task_id)
            return {
                "task_id": result.task_id,
                "reassigned": result.reassigned,
                "escalated": result.escalated,
                "retry_count": result.retry_count,
                "max_retries": result.max_retries,
            }
        if body.get("state"):
            state = str(body["state"])
            if not self.tasks.update_state(task_id, state):
                raise ApiError(404, "not_found", "task not found")
            task = self.tasks.get(task_id)
            if task is None:
                raise ApiError(404, "not_found", "task not found")
            return task
        raise ApiError(400, "bad_request", "task patch requires action or state")

    async def _agents(self, method: str, parts: list[str], request: _Request) -> JsonDict:
        if len(parts) == 1 and method == "GET":
            return {"ok": True, "data": [self._agent_with_current_task(agent) for agent in self.agents.list()]}
        if len(parts) == 1 and method == "POST":
            agent = self.agents.upsert(
                _required(request.body, "id", aliases=("agent_id",)),
                _required(request.body, "label"),
                _required(request.body, "type", aliases=("agent_type",)),
                _required(request.body, "role"),
                herdr_pane=_optional_str(request.body.get("herdr_pane")),
                herdr_ws=_optional_str(request.body.get("herdr_ws")),
                state=str(request.body.get("state") or "unknown"),
                health=str(request.body.get("health") or "healthy"),
                strengths=request.body.get("strengths"),
            )
            return {"ok": True, "data": self._agent_with_current_task(agent)}
        if len(parts) < 2:
            raise ApiError(405, "method_not_allowed", "unsupported agents route")
        agent_id = parts[1]
        if len(parts) == 2 and method == "GET":
            agent = self.agents.get(agent_id)
            if agent is None:
                raise ApiError(404, "not_found", "agent not found")
            return {"ok": True, "data": self._agent_with_current_task(agent)}
        if len(parts) == 2 and method == "PATCH":
            body = dict(request.body)
            if "agent_type" in body and "type" not in body:
                body["type"] = body.pop("agent_type")
            agent = self.agents.update(
                agent_id,
                **{
                    key: body[key]
                    for key in (
                        "label",
                        "type",
                        "role",
                        "herdr_pane",
                        "herdr_ws",
                        "state",
                        "health",
                        "strengths",
                    )
                    if key in body
                },
            )
            if agent is None:
                raise ApiError(404, "not_found", "agent not found")
            return {"ok": True, "data": self._agent_with_current_task(agent)}
        if len(parts) == 2 and method == "DELETE":
            if not self.agents.delete(agent_id):
                raise ApiError(404, "not_found", "agent not found")
            return {"ok": True, "data": {"id": agent_id, "deleted": True}}
        if len(parts) == 3 and parts[2] == "message" and method == "POST":
            body = dict(request.body)
            body["to"] = agent_id
            return await self._send_message(body)
        if len(parts) == 3 and parts[2] == "restart" and method == "POST":
            return {"ok": True, "data": await self._restart_agent(agent_id)}
        if len(parts) == 3 and parts[2] == "health" and method == "GET":
            agent = self.agents.get(agent_id)
            if agent is None:
                raise ApiError(404, "not_found", "agent not found")
            return {"ok": True, "data": {"agent": agent_id, "state": agent.get("state"), "health": agent.get("health"), "last_heartbeat": agent.get("last_heartbeat")}}
        if len(parts) == 3 and parts[2] == "metrics" and method == "GET":
            agent = self.agents.get(agent_id)
            if agent is None:
                raise ApiError(404, "not_found", "agent not found")
            return {"ok": True, "data": self._agent_metrics(agent)}
        raise ApiError(405, "method_not_allowed", "unsupported agents route")

    async def _messages(self, method: str, parts: list[str], request: _Request) -> JsonDict:
        if len(parts) == 1 and method == "POST":
            return await self._send_message(request.body)
        if len(parts) == 1 and method == "GET":
            delivered = _bool_query(request.query.get("delivered"))
            return {"ok": True, "data": self.messages.list(to_agent=request.query.get("to_agent") or request.query.get("to"), delivered=delivered)}
        if len(parts) == 2 and parts[1] == "stream" and method in {"GET", "STREAM"}:
            return {"ok": True, "data": {"stream": "messages", "transport": "newline-json"}}
        raise ApiError(405, "method_not_allowed", "unsupported messages route")

    async def _send_message(self, body: JsonDict) -> JsonDict:
        from_agent = _required(body, "from_agent", aliases=("from",))
        to = _required(body, "to")
        message = new_message(
            body.get("type", MessageType.CHAT.value),
            from_agent,
            to,
            body.get("payload") if isinstance(body.get("payload"), dict) else {"text": str(body.get("text") or "")},
            correlation_id=_optional_str(body.get("correlation_id")),
            ttl_seconds=int(body.get("ttl_seconds", self.config.bus.message_ttl_s)),
        )
        try:
            self.acl.check_message(message)
        except AclDenied as exc:
            raise ApiError(403, "acl_denied", exc.reason, details={"from_agent": exc.from_agent, "to": exc.to_agent}) from exc
        await self.bus.send(message)
        return {"ok": True, "data": _message_to_dict(message)}

    async def _restart_agent(self, agent_id: str) -> JsonDict:
        if self.agents.get(agent_id) is None:
            raise ApiError(404, "not_found", "agent not found")
        if self.restart_agent_hook is not None:
            result = self.restart_agent_hook(agent_id)
            if inspect.isawaitable(result):
                result = await result
            return {"agent": agent_id, "state": "recovering", "result": result}
        self.agents.update_state(agent_id, "recovering")
        self.agents.update_health(agent_id, "recovering", details={"source": "control_api_restart"})
        message = new_message(
            MessageType.ALERT,
            "control-api",
            agent_id,
            {"action": "restart", "agent": agent_id},
            ttl_seconds=self.config.bus.message_ttl_s,
        )
        try:
            await self.bus.send(message)
        except Exception:
            log.exception("agent_restart_message_failed", extra={"agent": agent_id})
        return {"agent": agent_id, "state": "recovering", "message_id": message.id}

    async def _reload_config(self, body: JsonDict) -> JsonDict:
        path = body.get("path")
        try:
            new_config = load_config(_optional_str(path))
            validate_config(new_config)
        except ConfigError as exc:
            raise ApiError(400, "config_error", str(exc)) from exc
        self.config = new_config
        self.acl.swap_config(new_config.acl)
        hook_result: Any = None
        if self.reload_config_hook is not None:
            hook_result = self.reload_config_hook(new_config)
            if inspect.isawaitable(hook_result):
                hook_result = await hook_result
        return {"ok": True, "data": {"reloaded": True, "path": _optional_str(path), "hook_result": hook_result}}

    async def _stream_messages(
        self,
        writer: asyncio.StreamWriter,
        *,
        http: bool = False,
        websocket: bool = False,
    ) -> None:
        last_seen: set[str] = set()
        task = asyncio.current_task()
        if task is not None:
            self._stream_tasks.add(task)
        try:
            while self._running and not writer.is_closing():
                for row in self.messages.list():
                    message_id = str(row.get("id"))
                    if message_id in last_seen:
                        continue
                    last_seen.add(message_id)
                    payload = {"ok": True, "event": "message", "data": row}
                    if websocket:
                        writer.write(_websocket_text_frame(json.dumps(payload, separators=(",", ":"), sort_keys=True)))
                    elif http:
                        writer.write((json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode())
                    else:
                        await _write_json_line(writer, payload)
                    await writer.drain()
                await asyncio.sleep(1.0)
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if task is not None:
                self._stream_tasks.discard(task)

    def _status(self) -> JsonDict:
        agents = self.agents.list()
        tasks = self.tasks.list()
        unhealthy = [agent for agent in agents if str(agent.get("health") or "healthy") not in {"healthy", "recovering"}]
        return {
            "ok": True,
            "data": {
                "state": "running" if self._running else "stopped",
                "uptime_seconds": int((datetime.now(UTC) - self.started_at).total_seconds()),
                "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
                "agents": {"total": len(agents), "unhealthy": len(unhealthy)},
                "tasks": _task_counts(tasks),
                "projects": {"total": len(self.projects.list())},
                "transports": {
                    "unix": str(self.socket_path),
                    "http": self.http_enabled,
                    "http_bind": self.config.api.bind,
                    "http_port": self.config.api.port,
                },
            },
        }

    def _prometheus_metrics(self) -> str:
        agents = self.agents.list()
        tasks = self.tasks.list()
        projects = self.projects.list()
        counts = _task_counts(tasks)
        lines = [
            "# HELP herdmaster_agents_total Number of registered agents",
            "# TYPE herdmaster_agents_total gauge",
            f"herdmaster_agents_total {len(agents)}",
            "# HELP herdmaster_projects_total Number of projects",
            "# TYPE herdmaster_projects_total gauge",
            f"herdmaster_projects_total {len(projects)}",
            "# HELP herdmaster_tasks_total Number of tasks by state",
            "# TYPE herdmaster_tasks_total gauge",
        ]
        for state, count in sorted(counts.items()):
            lines.append(f'herdmaster_tasks_total{{state="{state}"}} {count}')
        completed = sum(int(agent.get("tasks_completed") or 0) for agent in agents)
        lines.extend([
            "# HELP herdmaster_agent_tasks_completed_total Completed tasks recorded on agents",
            "# TYPE herdmaster_agent_tasks_completed_total counter",
            f"herdmaster_agent_tasks_completed_total {completed}",
        ])

        # --- Per-agent metrics ---
        healthy = sum(1 for a in agents if a.get("health") == "healthy")
        unhealthy = len(agents) - healthy
        lines.extend([
            "# HELP herdmaster_agents_healthy Number of healthy agents",
            "# TYPE herdmaster_agents_healthy gauge",
            f"herdmaster_agents_healthy {healthy}",
            "# HELP herdmaster_agents_unhealthy Number of unhealthy agents",
            "# TYPE herdmaster_agents_unhealthy gauge",
            f"herdmaster_agents_unhealthy {unhealthy}",
        ])

        lines.extend([
            "# HELP herdmaster_agent_info Agent metadata as labels (value always 1)",
            "# TYPE herdmaster_agent_info gauge",
        ])
        for agent in agents:
            aid = agent.get("id", "")
            label = agent.get("label", "").replace('"', '\\"')
            atype = agent.get("type", "")
            role = agent.get("role", "")
            state = agent.get("state", "")
            health = agent.get("health", "")
            lines.append(
                f'herdmaster_agent_info{{agent_id="{aid}",agent_label="{label}",'
                f'agent_type="{atype}",agent_role="{role}",'
                f'agent_state="{state}",agent_health="{health}"}} 1'
            )

        lines.extend([
            "# HELP herdmaster_agent_health Agent health status (1=healthy, 0=unhealthy)",
            "# TYPE herdmaster_agent_health gauge",
        ])
        for agent in agents:
            aid = agent.get("id", "")
            label = agent.get("label", "").replace('"', '\\"')
            val = 1 if agent.get("health") == "healthy" else 0
            lines.append(f'herdmaster_agent_health{{agent_id="{aid}",agent_label="{label}"}} {val}')

        lines.extend([
            "# HELP herdmaster_agent_tasks_completed Agent-level completed task count",
            "# TYPE herdmaster_agent_tasks_completed gauge",
        ])
        for agent in agents:
            aid = agent.get("id", "")
            label = agent.get("label", "").replace('"', '\\"')
            tc = int(agent.get("tasks_completed") or 0)
            lines.append(f'herdmaster_agent_tasks_completed{{agent_id="{aid}",agent_label="{label}"}} {tc}')

        lines.extend([
            "# HELP herdmaster_agent_avg_task_seconds Agent average task duration in seconds",
            "# TYPE herdmaster_agent_avg_task_seconds gauge",
        ])
        for agent in agents:
            aid = agent.get("id", "")
            label = agent.get("label", "").replace('"', '\\"')
            avg = float(agent.get("avg_task_seconds") or 0)
            lines.append(f'herdmaster_agent_avg_task_seconds{{agent_id="{aid}",agent_label="{label}"}} {avg}')

        # --- Agent registry integrity metrics (anti-false-positive) ---
        # Canonical whitelist loaded DYNAMICALLY from the reconciler-managed file
        # (AOP/ops/agent-registry-reconcile.sh rewrites it hourly from the live
        # herdr roster). This replaces the previously hardcoded list so the
        # integrity monitor always reflects the CURRENT correct agent names and
        # never reports stale false positives. Falls back to the current DB
        # agents if the file is missing (pre-first-reconcile), to avoid spurious
        # ghost alerts.
        import json as _json
        import os as _os

        agent_ids = {a.get("id", "") for a in agents}
        _wl_file = _os.environ.get(
            "HERDMASTER_AGENT_WHITELIST_FILE",
            _os.path.expanduser("~/.config/herdmaster/agent_whitelist.json"),
        )
        try:
            with open(_wl_file, encoding="utf-8") as _f:
                _AGENT_WHITELIST = {str(x) for x in _json.load(_f) if str(x).strip()}
            if not _AGENT_WHITELIST:
                _AGENT_WHITELIST = set(agent_ids)
        except (OSError, ValueError):
            _AGENT_WHITELIST = set(agent_ids)
        _EXPECTED_AGENT_COUNT = len(_AGENT_WHITELIST)

        unlisted = agent_ids - _AGENT_WHITELIST
        unlisted_count = len(unlisted)
        whitelist_compliant = 0 if unlisted else 1

        lines.extend([
            "# HELP herdmaster_agents_expected_total Canonical number of registered agents (whitelist size)",
            "# TYPE herdmaster_agents_expected_total gauge",
            f"herdmaster_agents_expected_total {_EXPECTED_AGENT_COUNT}",
            "# HELP herdmaster_unlisted_agents_total Number of agents in DB not in the canonical whitelist (ghost/auto-registered agents). Non-zero value indicates a false-positive state.",
            "# TYPE herdmaster_unlisted_agents_total gauge",
            f"herdmaster_unlisted_agents_total {unlisted_count}",
            "# HELP herdmaster_whitelist_compliant 1 if all DB agents are in the canonical whitelist, 0 if ghost agents exist",
            "# TYPE herdmaster_whitelist_compliant gauge",
            f"herdmaster_whitelist_compliant {whitelist_compliant}",
        ])

        # Per-unlisted-agent info for Grafana drill-down
        if unlisted:
            lines.extend([
                "# HELP herdmaster_unlisted_agent_info Metadata for each ghost/unlisted agent (value always 1)",
                "# TYPE herdmaster_unlisted_agent_info gauge",
            ])
            for agent in agents:
                aid = agent.get("id", "")
                if aid not in _AGENT_WHITELIST:
                    label = agent.get("label", "").replace('"', '\\"')
                    atype = agent.get("type", "")
                    lines.append(
                        f'herdmaster_unlisted_agent_info{{agent_id="{aid}",agent_label="{label}",agent_type="{atype}"}} 1'
                    )

        return "\n".join(lines) + "\n"


    def _project_detail(self, project_id: str) -> JsonDict:
        self.projects.update_progress(project_id)
        project = self._require_project(project_id)
        tasks = self.tasks.list(project_id=project_id)
        return {
            "id": project.get("id"),
            "name": project.get("name"),
            "state": project.get("state"),
            "scope": project.get("scope"),
            "deadline": project.get("deadline"),
            "analysis": self._project_analysis(project),
            "progress": _project_progress(project, tasks),
            "tasks": tasks,
            "created_at": project.get("created_at"),
            "updated_at": project.get("updated_at"),
        }

    def _project_summary(self, project: JsonDict) -> JsonDict:
        return {
            "id": project.get("id"),
            "name": project.get("name"),
            "state": project.get("state"),
            "complexity_tier": project.get("complexity_tier"),
            "eta_expected_hours": project.get("eta_expected_hours"),
            "progress": _project_progress(project, []),
            "created_at": project.get("created_at"),
            "updated_at": project.get("updated_at"),
        }

    def _project_analysis(self, project: JsonDict) -> JsonDict:
        raw = project.get("orchestrator_analysis") if isinstance(project.get("orchestrator_analysis"), dict) else {}
        return {
            "complexity_tier": project.get("complexity_tier") or raw.get("complexity_tier"),
            "squad": project.get("squad_approved") or project.get("squad_recommendation") or raw.get("squad") or [],
            "eta": {
                "optimistic_hours": project.get("eta_optimistic_hours"),
                "expected_hours": project.get("eta_expected_hours") or raw.get("eta_hours"),
                "pessimistic_hours": project.get("eta_pessimistic_hours"),
                "rationale": project.get("eta_rationale") or raw.get("eta_rationale") or "",
            },
            "tasks_preview": raw.get("tasks") or [],
            "raw": raw.get("raw", raw),
        }

    def _require_project(self, project_id: str) -> JsonDict:
        project = self.projects.get(project_id)
        if project is None:
            raise ApiError(404, "not_found", "project not found")
        return project

    def _agent_with_current_task(self, agent: JsonDict) -> JsonDict:
        current = self.tasks.list(assigned_to=str(agent.get("id")), state="in_progress")
        payload = dict(agent)
        payload["current_task"] = current[0] if current else None
        return payload

    def _agent_metrics(self, agent: JsonDict) -> JsonDict:
        agent_id = str(agent.get("id"))
        agent_tasks = self.tasks.list(assigned_to=agent_id)
        completed = [task for task in agent_tasks if task.get("state") == "done"]
        failed = [task for task in agent_tasks if task.get("state") in {"failed", "timeout"}]
        return {
            "agent": agent_id,
            "avg_task_seconds": agent.get("avg_task_seconds"),
            "tasks_completed": agent.get("tasks_completed") or len(completed),
            "tasks_assigned": len(agent_tasks),
            "tasks_failed": len(failed),
            "failure_rate": (len(failed) / len(agent_tasks)) if agent_tasks else 0.0,
            "last_heartbeat": agent.get("last_heartbeat"),
        }


def _socket_request(raw: str) -> _Request:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "bad_json", str(exc)) from exc
    if not isinstance(payload, dict):
        raise ApiError(400, "bad_request", "request must be a JSON object")
    request_id = payload.get("id")
    method_text = str(payload.get("method") or "GET")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if " " in method_text:
        method, path = method_text.split(" ", 1)
        body = dict(params)
    else:
        method = method_text
        path = str(payload.get("path") or params.get("path") or "/")
        body = payload.get("body") if isinstance(payload.get("body"), dict) else dict(params)
    split = urlsplit(path)
    query = _query_dict(split.query)
    if isinstance(payload.get("query"), dict):
        query.update({str(key): str(value) for key, value in payload["query"].items()})
    return _Request(method.upper(), split.path or "/", query, body, request_id=request_id, stream=method.upper() == "STREAM")


def _socket_response(payload: JsonDict, request_id: Any) -> JsonDict:
    if request_id is None:
        return payload
    return {"jsonrpc": "2.0", "id": request_id, "result": payload if payload.get("ok") else None, "error": payload.get("error") if not payload.get("ok") else None}


async def _write_json_line(writer: asyncio.StreamWriter, payload: JsonDict) -> None:
    writer.write((json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode())
    await writer.drain()


async def _read_http_request(reader: asyncio.StreamReader) -> JsonDict | None:
    try:
        raw_head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=_CLIENT_IDLE_TIMEOUT_S)
    except asyncio.TimeoutError:
        return None
    head = raw_head.decode("iso-8859-1")
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        return None
    method, target, _version = lines[0].split(" ", 2)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0") or "0")
    body_raw = await reader.readexactly(length) if length else b""
    body: Any = {}
    if body_raw:
        body = json.loads(body_raw.decode())
    split = urlsplit(target)
    return {"method": method, "path": split.path, "query": _query_dict(split.query), "headers": headers, "body": body}


async def _write_http_response(writer: asyncio.StreamWriter, status: int, payload: JsonDict) -> None:
    content_type = str(payload.pop("content_type", "application/json"))
    if content_type.startswith("text/plain") and isinstance(payload.get("data"), str):
        body = payload["data"].encode()
    else:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    reason = _HTTP_REASONS.get(status, "OK")
    headers = [
        f"HTTP/1.1 {status} {reason}",
        f"Date: {formatdate(usegmt=True)}",
        "Connection: close",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "",
        "",
    ]
    writer.write("\r\n".join(headers).encode() + body)
    await writer.drain()


async def _write_http_stream_headers(writer: asyncio.StreamWriter) -> None:
    headers = [
        "HTTP/1.1 200 OK",
        f"Date: {formatdate(usegmt=True)}",
        "Connection: close",
        "Content-Type: application/x-ndjson",
        "Cache-Control: no-cache",
        "",
        "",
    ]
    writer.write("\r\n".join(headers).encode())
    await writer.drain()


async def _write_websocket_handshake(writer: asyncio.StreamWriter, headers: dict[str, str]) -> None:
    key = headers.get("sec-websocket-key")
    if not key:
        raise ApiError(400, "bad_request", "Sec-WebSocket-Key is required")
    accept_seed = f"{key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".encode()
    accept = base64.b64encode(hashlib.sha1(accept_seed).digest()).decode()
    response = [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Accept: {accept}",
        "",
        "",
    ]
    writer.write("\r\n".join(response).encode())
    await writer.drain()


def _websocket_text_frame(text: str) -> bytes:
    payload = text.encode()
    length = len(payload)
    if length < 126:
        return bytes([0x81, length]) + payload
    if length <= 0xFFFF:
        return bytes([0x81, 126]) + length.to_bytes(2, "big") + payload
    return bytes([0x81, 127]) + length.to_bytes(8, "big") + payload


def _query_dict(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _required(body: JsonDict, key: str, *, aliases: tuple[str, ...] = ()) -> str:
    value = body.get(key)
    for alias in aliases:
        if value in {None, ""}:
            value = body.get(alias)
    if value in {None, ""}:
        raise ApiError(400, "bad_request", f"{key} is required")
    return str(value)


def _optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _bool_query(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() in {"1", "true", "yes"}:
        return True
    if value.lower() in {"0", "false", "no"}:
        return False
    return None


def _task_counts(tasks: list[JsonDict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        state = str(task.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts


def _project_progress(project: JsonDict, tasks: list[JsonDict]) -> JsonDict:
    total = int(project.get("total_tasks") or len(tasks) or 0)
    completed = int(project.get("completed_tasks") or len([task for task in tasks if task.get("state") == "done"]))
    failed = int(project.get("failed_tasks") or len([task for task in tasks if task.get("state") in {"failed", "timeout"}]))
    in_progress = len([task for task in tasks if task.get("state") in {"assigned", "dispatched", "in_progress"}])
    return {
        "total_tasks": total,
        "completed": completed,
        "in_progress": in_progress,
        "failed": failed,
        "percent_complete": round((completed / total * 100.0) if total else 0.0, 2),
    }


def _message_to_dict(message: Any) -> JsonDict:
    return {
        "id": message.id,
        "type": message.type.value,
        "from_agent": message.from_agent,
        "to": message.to,
        "correlation_id": message.correlation_id,
        "timestamp": message.timestamp,
        "ttl_seconds": message.ttl_seconds,
        "payload": message.payload,
    }


_HTTP_REASONS = {
    200: "OK",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}
