"""FastAPI routes for issue tracker records and dispatch."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Literal

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from core import OperationMode, TaskBudget, TaskEnvelope

from .models import IssuePriority, IssueRecord, IssueStatus


class IssueCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str | None = Field(default=None, min_length=1)
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str | None = None
    status: IssueStatus = IssueStatus.BACKLOG
    priority: IssuePriority = IssuePriority.MEDIUM
    assignee_runtime: str | None = None
    operation_mode: OperationMode = OperationMode.TERMINAL
    due_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IssueUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    assignee_runtime: str | None = None
    operation_mode: OperationMode | None = None
    due_date: date | None = None
    metadata: dict[str, Any] | None = None


class IssueDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str | None = None
    assignee_runtime: str | None = None
    operation_mode: OperationMode | None = None
    credential_ref: str | None = None
    seat_seconds: int | None = Field(default=None, ge=1)


class IssueResponse(BaseModel):
    issue_id: str
    tenant_id: str
    project_id: str
    title: str
    description: str | None
    status: IssueStatus
    priority: IssuePriority
    assignee_runtime: str | None
    operation_mode: OperationMode
    due_date: date | None
    metadata: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None = None


def build_issues_router(
    get_state: Callable[[], Any],
    collect_events: Callable[[TaskEnvelope, Any], Any],
    *,
    prefix: str = "/issues",
) -> APIRouter:
    """Build the issues router using app state and task dispatch dependencies."""
    router = APIRouter(prefix=prefix, tags=["issues"])

    def repository(state: Any = Depends(get_state)) -> Any:
        repo = getattr(state, "issues_repo", None)
        if repo is None:
            raise HTTPException(status_code=503, detail="issues repository unavailable")
        return repo

    @router.post("", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
    def create_issue(
        request: IssueCreateRequest,
        x_agent_id: str | None = Header(default=None),
        repo: Any = Depends(repository),
    ) -> IssueResponse:
        metadata = dict(request.metadata)
        if x_agent_id and not metadata.get("created_by"):
            metadata["created_by"] = x_agent_id
        try:
            issue = repo.create(
                issue_id=request.issue_id,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                title=request.title,
                description=request.description,
                status=request.status,
                priority=request.priority,
                assignee_runtime=request.assignee_runtime,
                operation_mode=request.operation_mode.value,
                due_date=request.due_date,
                metadata=metadata,
            )
        except psycopg.errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="issue already exists") from exc
        return _issue(issue)

    @router.get("", response_model=list[IssueResponse])
    def list_issues(
        tenant_id: str | None = None,
        project_id: str | None = None,
        status: IssueStatus | None = None,
        assignee_runtime: str | None = None,
        repo: Any = Depends(repository),
    ) -> list[IssueResponse]:
        return [
            _issue(issue)
            for issue in repo.list(
                tenant_id=tenant_id,
                project_id=project_id,
                status=status,
                assignee_runtime=assignee_runtime,
            )
        ]

    @router.get("/my", response_model=list[IssueResponse])
    def list_my_issues(
        scope: Literal["all", "assigned", "created", "my-agents"] = "all",
        agent_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        issue_status: IssueStatus | None = None,
        x_agent_id: str | None = Header(default=None),
        repo: Any = Depends(repository),
    ) -> list[IssueResponse]:
        """Return issues relevant to the calling agent/user.

        Identity is resolved from the ``X-Agent-Id`` header first, falling
        back to the ``agent_id`` query parameter.
        """
        resolved_agent = x_agent_id or agent_id
        if not resolved_agent:
            raise HTTPException(
                status_code=400,
                detail="agent identity required: set X-Agent-Id header or agent_id query param",
            )
        return [
            _issue(issue)
            for issue in repo.list_my(
                agent_id=resolved_agent,
                scope=scope,
                tenant_id=tenant_id,
                project_id=project_id,
                status=issue_status,
            )
        ]

    @router.get("/{issue_id}", response_model=IssueResponse)
    def get_issue(issue_id: str, repo: Any = Depends(repository)) -> IssueResponse:
        issue = repo.get(issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="issue not found")
        return _issue(issue)

    @router.patch("/{issue_id}", response_model=IssueResponse)
    def update_issue(
        issue_id: str,
        request: IssueUpdateRequest,
        repo: Any = Depends(repository),
    ) -> IssueResponse:
        issue = repo.update(
            issue_id,
            title=request.title,
            description=request.description,
            status=request.status,
            priority=request.priority,
            assignee_runtime=request.assignee_runtime,
            operation_mode=request.operation_mode.value if request.operation_mode else None,
            due_date=request.due_date,
            metadata=request.metadata,
        )
        if issue is None:
            raise HTTPException(status_code=404, detail="issue not found")
        return _issue(issue)

    @router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_issue(issue_id: str, repo: Any = Depends(repository)) -> Response:
        issue = repo.delete(issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="issue not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{issue_id}/dispatch")
    async def dispatch_issue(
        issue_id: str,
        request: IssueDispatchRequest,
        state: Any = Depends(get_state),
        repo: Any = Depends(repository),
    ) -> dict[str, Any]:
        issue = repo.get(issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="issue not found")
        operation_mode = request.operation_mode.value if request.operation_mode else issue.operation_mode
        assignee_runtime = request.assignee_runtime or issue.assignee_runtime
        if not assignee_runtime:
            raise HTTPException(status_code=422, detail="assignee_runtime is required to dispatch an issue")
        prompt = request.prompt or issue.description or issue.title
        task = TaskEnvelope(
            task_id=f"task-{issue.issue_id}",
            tenant_id=issue.tenant_id,
            project_id=issue.project_id,
            assignee_runtime=assignee_runtime,
            prompt=prompt,
            credential_ref=request.credential_ref or f"credential:{issue.tenant_id}:{assignee_runtime}",
            operation_mode=OperationMode(operation_mode),
            budget=TaskBudget(
                seat_seconds=request.seat_seconds or None,
                metadata={"issue_id": issue.issue_id},
            ),
        )
        started = repo.update(
            issue.issue_id,
            status=IssueStatus.IN_PROGRESS,
            assignee_runtime=assignee_runtime,
            operation_mode=operation_mode,
            metadata={**issue.metadata, "last_task_id": task.task_id},
        )
        events = await collect_events(task, state)
        final_status = _status_from_events(events)
        completed = repo.update(
            issue.issue_id,
            status=final_status,
            metadata={
                **(started.metadata if started else issue.metadata),
                "last_task_id": task.task_id,
                "last_dispatch_status": events[-1]["status"] if events else "unknown",
            },
        )
        return {
            "issue": _issue(completed or started or issue).model_dump(mode="json"),
            "task_id": task.task_id,
            "operation_mode": operation_mode,
            "events": events,
        }

    return router


def _status_from_events(events: list[dict[str, Any]]) -> IssueStatus:
    if not events:
        return IssueStatus.BLOCKED
    final = events[-1].get("status")
    if final == "done":
        return IssueStatus.DONE
    if final in {"blocked", "failed"}:
        return IssueStatus.BLOCKED
    return IssueStatus.IN_PROGRESS


def _issue(issue: IssueRecord) -> IssueResponse:
    return IssueResponse(
        issue_id=issue.issue_id,
        tenant_id=issue.tenant_id,
        project_id=issue.project_id,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        priority=issue.priority,
        assignee_runtime=issue.assignee_runtime,
        operation_mode=OperationMode(issue.operation_mode),
        due_date=issue.due_date,
        metadata=issue.metadata,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        deleted_at=issue.deleted_at,
    )
