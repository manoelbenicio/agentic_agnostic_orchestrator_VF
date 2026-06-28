"""FastAPI routes for project CRUD."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .models import ProjectRecord, ProjectStatus


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, min_length=1)
    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProjectStatus | None = None
    metadata: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    project_id: str
    tenant_id: str
    name: str
    description: str | None
    status: ProjectStatus
    metadata: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None = None


def build_projects_router(get_state: Callable[[], Any]) -> APIRouter:
    """Build the projects router using the app state dependency."""
    router = APIRouter(prefix="/projects", tags=["projects"])

    def repository(state: Any = Depends(get_state)) -> Any:
        repo = getattr(state, "projects_repo", None)
        if repo is None:
            raise HTTPException(status_code=503, detail="projects repository unavailable")
        return repo

    @router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
    def create_project(
        request: ProjectCreateRequest,
        repo: Any = Depends(repository),
    ) -> ProjectResponse:
        try:
            project = repo.create(
                project_id=request.project_id,
                tenant_id=request.tenant_id,
                name=request.name,
                description=request.description,
                status=request.status,
                metadata=request.metadata,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "UniqueViolation":
                raise HTTPException(status_code=409, detail="project already exists") from exc
            raise
        return _project(project)

    @router.get("", response_model=list[ProjectResponse])
    def list_projects(
        tenant_id: str | None = None,
        repo: Any = Depends(repository),
    ) -> list[ProjectResponse]:
        return [_project(project) for project in repo.list(tenant_id=tenant_id)]

    @router.get("/{project_id}", response_model=ProjectResponse)
    def get_project(project_id: str, repo: Any = Depends(repository)) -> ProjectResponse:
        project = repo.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return _project(project)

    @router.patch("/{project_id}", response_model=ProjectResponse)
    def update_project(
        project_id: str,
        request: ProjectUpdateRequest,
        repo: Any = Depends(repository),
    ) -> ProjectResponse:
        project = repo.update(
            project_id,
            name=request.name,
            description=request.description,
            status=request.status,
            metadata=request.metadata,
        )
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return _project(project)

    @router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_project(project_id: str, repo: Any = Depends(repository)) -> Response:
        project = repo.delete(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _project(project: ProjectRecord) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.project_id,
        tenant_id=project.tenant_id,
        name=project.name,
        description=project.description,
        status=project.status,
        metadata=project.metadata,
        created_at=project.created_at,
        updated_at=project.updated_at,
        deleted_at=project.deleted_at,
    )
