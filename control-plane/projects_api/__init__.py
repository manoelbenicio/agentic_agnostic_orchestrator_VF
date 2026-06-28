"""Projects API module for the AOP control plane."""

from .models import ProjectRecord, ProjectStatus
from .repository import ProjectRepository
from .router import build_projects_router
from .schema import connect, init_schema

__all__ = [
    "ProjectRecord",
    "ProjectRepository",
    "ProjectStatus",
    "build_projects_router",
    "connect",
    "init_schema",
]
