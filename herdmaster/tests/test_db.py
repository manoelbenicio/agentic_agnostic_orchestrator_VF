from __future__ import annotations

import hashlib
import json

import pytest

from herdmaster.db import schema
from herdmaster.db.repositories import AgentRepo, MessageRepo, ProjectRepo, TaskRepo


def test_schema_creates_expected_tables_indexes(temp_db):
    tables = {
        row["table_name"]
        for row in temp_db.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        )
    }
    indexes = {
        row["indexname"]
        for row in temp_db.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema() AND indexname LIKE 'idx_%'
            """
        )
    }

    assert tables == {
        "agents",
        "projects",
        "tasks",
        "task_audit_log",
        "task_alerts",
        "messages",
        "health_events",
        "project_history",
    }
    assert indexes == {
        "idx_tasks_state",
        "idx_tasks_assigned",
        "idx_tasks_priority",
        "idx_tasks_project",
        "idx_messages_to",
        "idx_health_agent",
        "idx_projects_state",
        "idx_project_history_complexity",
        "idx_audit_task",
        "idx_audit_agent",
        "idx_task_alerts_type",
        "idx_task_alerts_task",
    }


def test_agent_foreign_keys_use_expected_delete_rules(temp_db):
    rules = {
        (row["table_name"], row["column_name"]): row["delete_rule"]
        for row in temp_db.execute(
            """
            SELECT tc.table_name, kcu.column_name, rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_schema = kcu.constraint_schema
             AND tc.constraint_name = kcu.constraint_name
            JOIN information_schema.referential_constraints rc
              ON rc.constraint_schema = tc.constraint_schema
             AND rc.constraint_name = tc.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_schema = tc.constraint_schema
             AND ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = current_schema()
              AND ccu.table_name = 'agents'
            """
        )
    }

    assert rules[("health_events", "agent_id")] == "CASCADE"
    assert rules[("tasks", "assigned_to")] == "SET NULL"
    assert rules[("tasks", "created_by")] == "SET NULL"
    assert rules[("tasks", "completed_by")] == "SET NULL"
    assert rules[("task_audit_log", "agent_id")] == "SET NULL"
    assert rules[("messages", "from_agent")] == "SET NULL"


def test_deleting_agent_cascades_health_events_and_preserves_tasks(repos, temp_db):
    repos.agents.upsert("A1", "Codex 1", "codex", "worker")
    repos.agents.update_health("A1", "suspect", details={"reason": "test"})
    task_id = repos.tasks.create("T1", "Prompt", assigned_to="A1", created_by="A1")

    assert repos.agents.delete("A1") is True

    assert temp_db.execute("SELECT COUNT(*) AS count FROM health_events WHERE agent_id = ?", ("A1",)).fetchone()["count"] == 0
    task = repos.tasks.get(task_id)
    assert task["assigned_to"] is None
    assert task["created_by"] is None


def test_cleanup_orphan_hm_schemas_drops_inactive_hash_schema(tmp_path):
    active_schema = "hm_test_" + hashlib.sha1(str(tmp_path / "active").encode("utf-8")).hexdigest()[:16]
    orphan_schema = "hm_orphan_fk_fix"
    conn = schema.connect(tmp_path / "active.db", schema_name=active_schema)
    try:
        schema.init_db(conn)
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {orphan_schema}")
        conn.commit()

        dropped = schema.cleanup_orphan_hm_schemas(conn)

        assert orphan_schema in dropped
        exists = conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = ?",
            (orphan_schema,),
        ).fetchone()
        assert exists is None
    finally:
        conn.close()


def test_repository_crud_and_json_round_trips(repos):
    agent = repos.agents.upsert(
        "A1",
        "Codex 1",
        "codex",
        "worker",
        herdr_pane="pane-1",
        strengths=["tests", "python"],
    )
    assert agent["strengths"] == ["tests", "python"]
    assert repos.agents.update_state("A1", "working") is True
    assert repos.agents.record_heartbeat("A1", last_output_hash="abc") is True
    assert repos.agents.get("A1")["last_output_hash"] == "abc"

    project_id = repos.projects.create("Foundation", "Build test foundation", complexity_tier="S")
    assert repos.projects.set_analysis(project_id, {"risk": "low"}, squad_recommendation=[{"agent": "A1"}])
    assert repos.projects.get(project_id)["orchestrator_analysis"] == {"risk": "low"}

    task_id = repos.tasks.create(
        "T1",
        "Prompt",
        project_id=project_id,
        depends_on=["dep-1", "dep-2"],
        created_by="A1",
    )
    assert repos.tasks.get(task_id)["depends_on"] == ["dep-1", "dep-2"]
    assert repos.tasks.claim(task_id, "A1", expected_version=1) is True
    assert repos.tasks.complete(task_id, duration_seconds=7) is True

    msg_id = repos.messages.insert(
        "chat",
        {"nested": {"ok": True}, "items": [1, 2]},
        from_agent="A1",
        to_agent="A2",
    )
    assert repos.messages.list(to_agent="A2")[0]["payload"] == {"nested": {"ok": True}, "items": [1, 2]}
    assert repos.messages.mark_delivered(msg_id) is True
    assert repos.messages.mark_acknowledged(msg_id) is True

    repos.projects.update_progress(project_id)
    assert repos.projects.get(project_id)["completed_tasks"] == 1


def test_sql_error_rolls_back_before_connection_reuse(tmp_path):
    schema_name = "rollback_test_" + hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:16]
    conn = schema.connect(tmp_path / "rollback.db", schema_name=schema_name)
    try:
        with conn._conn.cursor() as cur:
            cur.execute(schema.sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema.sql.Identifier(schema_name)))
            cur.execute(schema.sql.SQL("SET search_path TO {}, public").format(schema.sql.Identifier(schema_name)))
        conn._conn.commit()
        conn.execute("CREATE TABLE rollback_items (id TEXT PRIMARY KEY, label TEXT NOT NULL)")
        conn.commit()
        conn.execute("INSERT INTO rollback_items (id, label) VALUES (?, ?)", ("one", "before-error"))
        conn.commit()

        with pytest.raises(Exception):
            conn.execute("SELECT * FROM missing_table_for_rollback_test")

        assert conn.execute("SELECT label FROM rollback_items WHERE id = ?", ("one",)).fetchone()["label"] == "before-error"
        assert conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    finally:
        with conn._conn.cursor() as cur:
            cur.execute(schema.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(schema.sql.Identifier(schema_name)))
        conn._conn.commit()
        conn.close()


def test_cas_claim_is_single_winner_under_concurrency(tmp_path):
    db_path = tmp_path / "cas.db"
    schema_name = "hm_test_" + hashlib.sha1(str(db_path).encode("utf-8")).hexdigest()[:16]
    conn = schema.connect(db_path, schema_name=schema_name)
    schema.init_db(conn)
    AgentRepo(conn).upsert("A1", "Agent 1", "codex", "worker")
    AgentRepo(conn).upsert("A2", "Agent 2", "codex", "worker")
    task_id = TaskRepo(conn).create("Race", "claim once")
    conn.close()

    contender_1 = schema.connect(db_path, schema_name=schema_name)
    contender_2 = schema.connect(db_path, schema_name=schema_name)
    version_1 = TaskRepo(contender_1).get(task_id)["version"]
    version_2 = TaskRepo(contender_2).get(task_id)["version"]
    contender_2.close()

    try:
        assert version_1 == version_2 == 1
        assert TaskRepo(contender_1).claim(task_id, "A1", expected_version=version_1) is True
    finally:
        contender_1.close()

    stale_contender = schema.connect(db_path, schema_name=schema_name)
    try:
        assert TaskRepo(stale_contender).claim(task_id, "A2", expected_version=version_2) is False
    finally:
        stale_contender.close()

    conn = schema.connect(db_path, schema_name=schema_name)
    try:
        task = TaskRepo(conn).get(task_id)
        assert task["state"] == "assigned"
        assert task["assigned_to"] == "A1"
        assert task["version"] == 2
    finally:
        conn.close()


def test_list_ready_respects_done_dependencies(repos):
    dep_done = repos.tasks.create("done dependency", "finish first", task_id="dep-done")
    dep_open = repos.tasks.create("open dependency", "still queued", task_id="dep-open")
    ready = repos.tasks.create("ready", "go", task_id="ready", depends_on=[dep_done])
    blocked = repos.tasks.create("blocked", "wait", task_id="blocked", depends_on=[dep_open])
    missing = repos.tasks.create("missing", "wait", task_id="missing", depends_on=["no-such-task"])
    independent = repos.tasks.create("independent", "go", task_id="independent")

    repos.tasks.complete(dep_done)

    ready_ids = {task["id"] for task in repos.tasks.list_ready()}
    assert {ready, independent}.issubset(ready_ids)
    assert blocked not in ready_ids
    assert missing not in ready_ids
