"""FastAPI routes for the OTTL task trail and HerdMaster task proxy.

Exposes:
- ``GET    /api/tasks``            — list tasks (optional filters)
- ``GET    /api/tasks/{task_id}``  — get a single task
- ``PATCH  /api/tasks/{task_id}``  — update status/progress/eta
- ``POST   /api/tasks/reconcile``  — reconcile from squad-tasks.json + HerdMaster
- ``GET    /api/tasks/board``       — aggregate board with progress % and ETA
- ``GET    /api/tasks/herdmaster``  — proxy: list tasks from HerdMaster live
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .models import TaskPriority, TaskRecord, TaskStatus


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    eta_min: int | None = Field(default=None, ge=0)
    progress: int | None = Field(default=None, ge=0, le=100)
    herdmaster_task_id: str | None = None
    herdmaster_state: str | None = None
    metadata: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    task_id: str
    title: str
    priority: TaskPriority
    agent: str
    pane: str
    status: TaskStatus
    eta_min: int
    progress: int
    herdmaster_task_id: str | None
    herdmaster_state: str | None
    metadata: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None
    last_seen_at: datetime | None


class ReconcileResponse(BaseModel):
    file: dict[str, Any]
    herdmaster: dict[str, Any]
    timestamp: str


class BoardResponse(BaseModel):
    total_tasks: int
    done: int
    overall_progress: float
    total_eta_min: int
    by_status: dict[str, Any]


def build_tasks_router(
    get_state: Callable[[], Any],
    *,
    prefix: str = "/api/tasks",
) -> APIRouter:
    """Build the OTTL tasks router using app state."""
    router = APIRouter(prefix=prefix, tags=["tasks"])

    def repository(state: Any = Depends(get_state)) -> Any:
        repo = getattr(state, "tasks_repo", None)
        if repo is None:
            raise HTTPException(status_code=503, detail="tasks repository unavailable")
        return repo

    @router.get("", response_model=list[TaskResponse])
    def list_tasks(
        task_status: TaskStatus | None = Query(default=None, alias="status"),
        agent: str | None = None,
        priority: TaskPriority | None = None,
        repo: Any = Depends(repository),
    ) -> list[TaskResponse]:
        return [
            _task(t)
            for t in repo.list(status=task_status, agent=agent, priority=priority)
        ]

    @router.get("/board", response_model=BoardResponse)
    def get_board(repo: Any = Depends(repository)) -> BoardResponse:
        data = repo.board()
        return BoardResponse(**data)

    @router.post("/reconcile", response_model=ReconcileResponse)
    def reconcile_tasks(
        state: Any = Depends(get_state),
        repo: Any = Depends(repository),
    ) -> ReconcileResponse:
        """Reconcile from squad-tasks.json and HerdMaster into Postgres."""
        reconciler = getattr(state, "tasks_reconciler", None) or getattr(state, "task_reconciler", None)
        if reconciler is None:
            # Build an ad-hoc reconciler if not wired in state
            from .reconciler import TaskReconciler

            squad_path = _default_squad_tasks_path(state)
            hm_client = getattr(state, "message_bus", None)
            reconciler = TaskReconciler(
                repo,
                squad_tasks_path=squad_path,
                herdmaster_client=hm_client,
            )
        result = reconciler.reconcile_all()
        return ReconcileResponse(**result)

    @router.get("/herdmaster")
    async def list_herdmaster_tasks(
        state: Any = Depends(get_state),
        assigned_to: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Proxy: list tasks directly from HerdMaster's live API.

        Uses HerdMaster's REST API so this endpoint remains a read-only proxy
        instead of submitting a claim/dispatch operation through the message bus.
        """
        settings = getattr(state, "settings", None)
        token = getattr(settings, "herdmaster_token", None)
        base_url = getattr(settings, "herdmaster_url", None)
        if not token or not base_url:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "herdmaster_unavailable",
                    "reason": "HerdMaster REST credentials are not configured",
                },
            )

        query = parse.urlencode(
            {
                key: value
                for key, value in {
                    "assigned_to": assigned_to,
                    "project_id": project_id,
                }.items()
                if value
            }
        )
        url = f"{str(base_url).rstrip('/')}/tasks"
        if query:
            url = f"{url}?{query}"

        herdmaster_request = request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="GET",
        )
        try:
            with request.urlopen(herdmaster_request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "herdmaster_error",
                    "status": exc.code,
                    "reason": body or exc.reason,
                },
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "herdmaster_error", "reason": str(exc)},
            ) from exc

        tasks = payload.get("data", payload) if isinstance(payload, dict) else payload
        return {"ok": True, "tasks": tasks}

    @router.get("/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str, repo: Any = Depends(repository)) -> TaskResponse:
        task = repo.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return _task(task)

    @router.patch("/{task_id}", response_model=TaskResponse)
    def update_task(
        task_id: str,
        request: TaskUpdateRequest,
        repo: Any = Depends(repository),
    ) -> TaskResponse:
        task = repo.update(
            task_id,
            status=request.status,
            eta_min=request.eta_min,
            progress=request.progress,
            herdmaster_task_id=request.herdmaster_task_id,
            herdmaster_state=request.herdmaster_state,
            metadata=request.metadata,
        )
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return _task(task)

    return router


def _default_squad_tasks_path(state: Any) -> Path | None:
    """Resolve the default ops/squad-tasks.json path relative to the AOP repo."""
    # state.settings has database_url but not a repo path; derive from CWD
    import os

    candidate = Path(os.environ.get("AOP_SQUAD_TASKS_PATH", "ops/squad-tasks.json"))
    return candidate if candidate.exists() else None


def _task(rec: TaskRecord) -> TaskResponse:
    return TaskResponse(
        task_id=rec.task_id,
        title=rec.title,
        priority=rec.priority,
        agent=rec.agent,
        pane=rec.pane,
        status=rec.status,
        eta_min=rec.eta_min,
        progress=rec.progress,
        herdmaster_task_id=rec.herdmaster_task_id,
        herdmaster_state=rec.herdmaster_state,
        metadata=rec.metadata or {},
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        last_seen_at=rec.last_seen_at,
    )
