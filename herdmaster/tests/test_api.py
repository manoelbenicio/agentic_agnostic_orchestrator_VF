from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from herdmaster.acl.engine import AclEngine
from herdmaster.api.server import ApiError, ControlApiServer, _Request
from herdmaster.config import AclConfig, AclRole
from herdmaster.dispatch.injector import DispatchInjector, DispatchInjectorConfig
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.project.planner import ProjectPlanner


class FakeBus:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


def _request(method: str, path: str, *, body=None, query=None) -> _Request:
    return _Request(method, path, query or {}, body or {})


def _analysis_payload(*, assigned_to: str = "A2") -> str:
    return json.dumps(
        {
            "complexity_tier": "M",
            "squad": [
                {"agent": "A1", "role": "orchestrator", "rationale": "plans work"},
                {"agent": assigned_to, "role": "implementer", "rationale": "executes work"},
            ],
            "eta_hours": 1.5,
            "eta_rationale": "two small tasks with one worker",
            "tasks": [
                {
                    "title": "Implement API",
                    "description": "Build the route",
                    "prompt": "Implement the API route",
                    "assigned_to": assigned_to,
                    "priority": "high",
                    "depends_on": [],
                },
                {
                    "title": "Verify API",
                    "description": "Add verification",
                    "prompt": "Verify the API route",
                    "assigned_to": assigned_to,
                    "priority": "normal",
                    "depends_on": ["Implement API"],
                },
            ],
        }
    )


@pytest.fixture
def api_config(test_config):
    roles = (
        AclRole(
            name="orchestrator",
            agents=["A1", "control-api"],
            can_send_to=["*"],
            can_receive_from=["*"],
            can_dispatch_tasks=True,
            can_reassign_tasks=True,
        ),
        AclRole(
            name="worker",
            agents=["A2"],
            can_send_to=["orchestrator"],
            can_receive_from=["orchestrator", "control-api"],
            can_dispatch_tasks=False,
            can_reassign_tasks=False,
        ),
    )
    return replace(test_config, acl=AclConfig(default_policy="deny", roles=roles))


@pytest.fixture
def api_server(repos, mock_herdr_adapter, api_config, tmp_path):
    queue = TaskQueue(repos.tasks, repos.agents)
    injector = DispatchInjector(
        mock_herdr_adapter,
        queue,
        repos.agents,
        DispatchInjectorConfig(
            idle_timeout_s=1,
            max_chunk_chars=10_000,
            file_fallback_threshold_chars=1_000_000,
            chunk_pace_s=0.0,
            retry_attempts=1,
            base_backoff_s=0.0,
            max_backoff_s=0.0,
            fallback_dir=tmp_path / "prompts",
        ),
    )
    planner = ProjectPlanner(
        repos.projects,
        repos.tasks,
        repos.agents,
        queue,
        injector,
        mock_herdr_adapter,
        api_config,
    )
    bus = FakeBus()
    server = ControlApiServer(
        config=api_config,
        planner=planner,
        queue=queue,
        agents=repos.agents,
        tasks=repos.tasks,
        projects=repos.projects,
        messages=repos.messages,
        bus=bus,
        acl=AclEngine(api_config.acl),
        socket_path=api_config.paths.socket,
        reload_config=lambda cfg: {"path": str(cfg.paths.config_dir)},
    )
    server._running = True
    return SimpleNamespace(server=server, bus=bus)


@pytest.mark.asyncio
async def test_get_status_reports_runtime_counts(api_server, make_agent):
    make_agent("A1", role="orchestrator", state="idle")
    make_agent("A2", state="working")
    api_server.server.queue.enqueue("Queued", "Do queued work")

    payload = await api_server.server._dispatch(_request("GET", "/status"))

    assert payload["ok"] is True
    assert payload["data"]["state"] == "running"
    assert payload["data"]["agents"] == {"total": 2, "unhealthy": 0}
    assert payload["data"]["tasks"]["queued"] == 1
    assert payload["data"]["transports"]["unix"].endswith("herdmaster.sock")


@pytest.mark.asyncio
async def test_get_metrics_returns_prometheus_text(api_server, make_agent):
    make_agent("A1", role="orchestrator")
    make_agent("A2")
    api_server.server.queue.enqueue("Metric task", "Measure it")

    payload = await api_server.server._dispatch(_request("GET", "/metrics"))

    assert payload["ok"] is True
    assert payload["content_type"].startswith("text/plain")
    assert "herdmaster_agents_total 2" in payload["data"]
    assert 'herdmaster_tasks_total{state="queued"} 1' in payload["data"]


@pytest.mark.asyncio
async def test_projects_create_get_and_approve(api_server, make_agent):
    make_agent("A1", role="orchestrator", state="idle")
    make_agent("A2", state="idle")

    created = await api_server.server._dispatch(
        _request(
            "POST",
            "/projects",
            body={
                "name": "Control API",
                "scope": "Build and verify the API",
                "orchestrator_output": _analysis_payload(),
            },
        )
    )
    project_id = created["data"]["id"]

    fetched = await api_server.server._dispatch(_request("GET", f"/projects/{project_id}"))
    assert fetched["data"]["state"] == "awaiting_approval"
    assert fetched["data"]["analysis"]["complexity_tier"] == "M"
    assert [task["title"] for task in fetched["data"]["analysis"]["tasks_preview"]] == [
        "Implement API",
        "Verify API",
    ]

    approved = await api_server.server._dispatch(
        _request("POST", f"/projects/{project_id}/approve", body={"decision": "accept"})
    )

    assert approved["ok"] is True
    assert approved["data"]["project"]["state"] == "in_progress"
    assert len(approved["data"]["task_ids"]) == 2
    assert [task["project_id"] for task in api_server.server.tasks.list(project_id=project_id)] == [
        project_id,
        project_id,
    ]


@pytest.mark.asyncio
async def test_tasks_create_list_and_cancel(api_server, make_agent):
    make_agent("A2", state="idle")

    created = await api_server.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Write tests", "prompt": "Cover the API", "assigned_to": "A2", "priority": "high"},
        )
    )
    task_id = created["data"]["id"]

    listed = await api_server.server._dispatch(_request("GET", "/tasks", query={"assigned_to": "A2"}))
    assert [task["id"] for task in listed["data"]] == [task_id]

    cancelled = await api_server.server._dispatch(_request("DELETE", f"/tasks/{task_id}"))
    assert cancelled["data"]["state"] == "cancelled"
    assert api_server.server.tasks.get(task_id)["state"] == "cancelled"


@pytest.mark.asyncio
async def test_agents_list_and_detail_include_current_task(api_server, make_agent):
    make_agent("A1", role="orchestrator", state="idle")
    make_agent("A2", state="idle")
    task_id = api_server.server.queue.enqueue("Current", "In progress", assigned_to="A2")
    api_server.server.tasks.update_state(task_id, "in_progress")

    listed = await api_server.server._dispatch(_request("GET", "/agents"))
    detail = await api_server.server._dispatch(_request("GET", "/agents/A2"))

    assert [agent["id"] for agent in listed["data"]] == ["A1", "A2"]
    assert detail["data"]["id"] == "A2"
    assert detail["data"]["current_task"]["id"] == task_id


@pytest.mark.asyncio
async def test_agents_create_edit_delete_via_api(api_server):
    created = await api_server.server._dispatch(
        _request(
            "POST",
            "/agents",
            body={
                "id": "A3",
                "label": "Codex 3",
                "type": "codex",
                "role": "worker",
                "state": "idle",
                "strengths": ["api", "tests"],
            },
        )
    )
    assert created["data"]["id"] == "A3"
    assert created["data"]["strengths"] == ["api", "tests"]

    listed = await api_server.server._dispatch(_request("GET", "/agents"))
    assert [agent["id"] for agent in listed["data"]] == ["A3"]

    patched = await api_server.server._dispatch(
        _request(
            "PATCH",
            "/agents/A3",
            body={"label": "Codex III", "agent_type": "gpt", "role": "orchestrator", "health": "suspect"},
        )
    )
    assert patched["data"]["label"] == "Codex III"
    assert patched["data"]["type"] == "gpt"
    assert patched["data"]["role"] == "orchestrator"
    assert patched["data"]["health"] == "suspect"
    assert api_server.server.agents.get("A3")["label"] == "Codex III"

    deleted = await api_server.server._dispatch(_request("DELETE", "/agents/A3"))
    assert deleted["data"] == {"id": "A3", "deleted": True}
    assert api_server.server.agents.get("A3") is None


@pytest.mark.asyncio
async def test_agent_message_acl_allow_sends_to_bus(api_server, make_agent):
    make_agent("A1", role="orchestrator")
    make_agent("A2")

    payload = await api_server.server._dispatch(
        _request(
            "POST",
            "/agents/A2/message",
            body={"from_agent": "A1", "type": "chat", "text": "hello"},
        )
    )

    assert payload["ok"] is True
    assert payload["data"]["from_agent"] == "A1"
    assert payload["data"]["to"] == "A2"
    assert len(api_server.bus.sent) == 1
    assert api_server.bus.sent[0].payload == {"text": "hello"}


@pytest.mark.asyncio
async def test_agent_message_acl_deny_returns_403(api_server, make_agent):
    make_agent("A2")

    with pytest.raises(ApiError) as exc_info:
        await api_server.server._dispatch(
            _request(
                "POST",
                "/agents/A2/message",
                body={"from_agent": "stranger", "type": "chat", "text": "nope"},
            )
        )

    assert exc_info.value.status == 403
    assert exc_info.value.code == "acl_denied"
    assert api_server.bus.sent == []


@pytest.mark.asyncio
async def test_restart_existing_agent_marks_recovering(api_server, make_agent):
    make_agent("A2", state="idle", health="healthy")

    payload = await api_server.server._dispatch(_request("POST", "/agents/A2/restart"))

    assert payload["ok"] is True
    assert payload["data"]["agent"] == "A2"
    assert payload["data"]["state"] == "recovering"
    assert api_server.server.agents.get("A2")["state"] == "recovering"
    assert api_server.server.agents.get("A2")["health"] == "recovering"
    assert api_server.bus.sent[0].payload == {"action": "restart", "agent": "A2"}


@pytest.mark.asyncio
async def test_restart_unknown_agent_returns_404(api_server):
    with pytest.raises(ApiError) as exc_info:
        await api_server.server._dispatch(_request("POST", "/agents/missing/restart"))

    assert exc_info.value.status == 404
    assert exc_info.value.code == "not_found"


@pytest.mark.asyncio
async def test_config_reload_loads_path_and_invokes_hook(api_server, tmp_path):
    config_dir = tmp_path / "runtime"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
        [paths]
        config_dir = "{config_dir.as_posix()}"
        db = "herdmaster.db"
        socket = "herdmaster.sock"
        log = "herdmaster.log"

        [watchdog]
        soft_timeout_s = 3
        hard_timeout_s = 9
        poll_interval_s = 1
        max_retries = 1
        tertiary_hash_interval_s = 2

        [bus]
        socket_path = "{(config_dir / "bus.sock").as_posix()}"
        message_ttl_s = 7

        [acl]
        default_policy = "allow"

        [api]
        bind = "127.0.0.1"
        port = 9090
        token = ""

        [logging]
        level = "INFO"
        json = false
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    payload = await api_server.server._dispatch(
        _request("POST", "/config/reload", body={"path": str(config_path)})
    )

    assert payload["ok"] is True
    assert payload["data"]["reloaded"] is True
    assert payload["data"]["path"] == str(config_path)
    assert payload["data"]["hook_result"] == {"path": str(config_dir)}
    assert api_server.server.config.paths.config_dir == config_dir
    assert api_server.server.config.bus.message_ttl_s == 7


@pytest.mark.asyncio
async def test_unsupported_known_route_returns_405(api_server):
    with pytest.raises(ApiError) as exc_info:
        await api_server.server._dispatch(_request("PUT", "/tasks"))

    assert exc_info.value.status == 405
    assert exc_info.value.code == "method_not_allowed"

    with pytest.raises(ApiError) as status_exc:
        await api_server.server._dispatch(_request("DELETE", "/status"))

    assert status_exc.value.status == 405
    assert status_exc.value.code == "method_not_allowed"
