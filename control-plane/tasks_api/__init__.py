"""OTTL task tracker API package.

Provides a Postgres-backed task trail (TD5-OTTL) that mirrors the
squad-tasks.json ledger and the HerdMaster task lifecycle into a
queryable store with progress/ETA for the dashboard board.
"""

from .models import TaskPriority, TaskRecord, TaskStatus
from .reconciler import TaskReconciler
from .repository import TaskRepository
from .router import build_tasks_router
from .schema import _schema_name as tasks_api_schema_name
from .schema import init_schema as init_tasks_api_schema

__all__ = [
    "TaskPriority",
    "TaskRecord",
    "TaskReconciler",
    "TaskRepository",
    "TaskStatus",
    "build_tasks_router",
    "init_tasks_api_schema",
    "tasks_api_schema_name",
]
