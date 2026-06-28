"""Postgres data layer for HerdMaster."""

from .schema import (
    DEFAULT_SCHEMA_NAME,
    SCHEMA_SQL,
    SCHEMA_VERSION,
    cleanup_orphan_hm_schemas,
    connect,
    connect_pool,
    init_db,
    migrate_agent_foreign_keys,
    migrate_all_agent_foreign_keys,
    pool_get_stats,
)
from .repositories import AgentRepo, MessageRepo, ProjectRepo, TaskRepo, new_id

__all__ = [
    "AgentRepo",
    "DEFAULT_SCHEMA_NAME",
    "MessageRepo",
    "ProjectRepo",
    "SCHEMA_SQL",
    "SCHEMA_VERSION",
    "TaskRepo",
    "cleanup_orphan_hm_schemas",
    "connect",
    "connect_pool",
    "init_db",
    "migrate_agent_foreign_keys",
    "migrate_all_agent_foreign_keys",
    "new_id",
    "pool_get_stats",
]
