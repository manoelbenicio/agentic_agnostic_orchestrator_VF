import pytest
from topology.mapper import TopologyMapper, CanvasNode, CanvasEdge
from topology.repository import TopologyRepository
import sys
import os
from pathlib import Path
from uuid import uuid4

from psycopg import sql
import psycopg

# Try to import AclEngine. Since the project includes HerdMaster at root, it should be reachable if PYTHONPATH is set.
try:
    from herdmaster.acl.engine import AclEngine
except ImportError:
    AclEngine = None

def test_default_hub_and_spoke():
    # Setup Hub-and-Spoke: 1 TL, 2 workers
    nodes = [
        CanvasNode("tl_1", "orchestrator"),
        CanvasNode("worker_1", "worker"),
        CanvasNode("worker_2", "worker")
    ]
    edges = [
        # TL to workers
        CanvasEdge("tl_1", "worker_1"),
        CanvasEdge("tl_1", "worker_2"),
        # Workers back to TL
        CanvasEdge("worker_1", "tl_1"),
        CanvasEdge("worker_2", "tl_1")
    ]
    
    config = TopologyMapper.map_to_acl(nodes, edges)
    
    # Verify mapping output
    assert config.default_policy == "deny"
    tl_role = next(r for r in config.roles if "tl_1" in r.agents)
    assert tl_role.can_dispatch_tasks is True
    assert "worker_1" in tl_role.can_send_to
    assert "worker_1" in tl_role.can_receive_from
    
    w1_role = next(r for r in config.roles if "worker_1" in r.agents)
    assert w1_role.can_dispatch_tasks is False
    assert "tl_1" in w1_role.can_send_to
    assert "worker_2" not in w1_role.can_send_to  # Cannot talk to other worker laterally
    
    # If HerdMaster is available, test with the actual engine
    if AclEngine:
        engine = AclEngine(config)
        assert engine.can_send("tl_1", "worker_1") is True
        assert engine.can_send("worker_1", "tl_1") is True
        # Lateral denied by default
        assert engine.can_send("worker_1", "worker_2") is False
        assert engine.can_dispatch("tl_1") is True
        assert engine.can_dispatch("worker_1") is False

def test_lateral_concession():
    # Setup Hub-and-Spoke + Lateral edge
    nodes = [
        CanvasNode("tl_1", "orchestrator"),
        CanvasNode("w_1", "worker"),
        CanvasNode("w_2", "worker")
    ]
    edges = [
        CanvasEdge("tl_1", "w_1"), CanvasEdge("w_1", "tl_1"),
        CanvasEdge("tl_1", "w_2"), CanvasEdge("w_2", "tl_1"),
        # Explicit lateral edge w_1 -> w_2
        CanvasEdge("w_1", "w_2")
    ]
    
    config = TopologyMapper.map_to_acl(nodes, edges)
    w1_role = next(r for r in config.roles if "w_1" in r.agents)
    assert "w_2" in w1_role.can_send_to
    
    if AclEngine:
        engine = AclEngine(config)
        assert engine.can_send("w_1", "w_2") is True
        # The reverse is still denied
        assert engine.can_send("w_2", "w_1") is False

def test_isolated_worker_validation():
    nodes = [
        CanvasNode("tl_1", "orchestrator"),
        CanvasNode("worker_1", "worker")
    ]
    # No edges -> worker is unreachable
    edges = []
    
    with pytest.raises(ValueError, match="worker_1 is unreachable"):
        TopologyMapper.map_to_acl(nodes, edges)


def test_repository_persists_topology_in_postgres():
    schema_name = f"topology_test_{uuid4().hex}"
    database_url = _database_url()
    try:
        repo = TopologyRepository(database_url, schema_name=schema_name)
        repo.save_topology(
            "squad-a",
            [CanvasNode("tl_1", "orchestrator"), CanvasNode("worker_1", "worker")],
            [CanvasEdge("tl_1", "worker_1"), CanvasEdge("worker_1", "tl_1")],
        )

        persisted_repo = TopologyRepository(database_url, schema_name=schema_name)

        assert persisted_repo.get_topology("squad-a") == {
            "nodes": [
                {"id": "tl_1", "role": "orchestrator"},
                {"id": "worker_1", "role": "worker"},
            ],
            "edges": [
                {"source": "tl_1", "target": "worker_1"},
                {"source": "worker_1", "target": "tl_1"},
            ],
        }
    finally:
        _drop_schema(database_url, schema_name)


def test_repository_upserts_and_returns_none_for_missing_squad():
    schema_name = f"topology_test_{uuid4().hex}"
    database_url = _database_url()
    try:
        repo = TopologyRepository(database_url, schema_name=schema_name)
        assert repo.get_topology("missing") is None

        repo.save_topology("squad-a", [{"id": "old", "role": "worker"}], [])
        repo.save_topology(
            "squad-a",
            [CanvasNode("tl_1", "orchestrator"), CanvasNode("worker_1", "worker")],
            [CanvasEdge("tl_1", "worker_1")],
        )

        assert repo.get_topology("squad-a") == {
            "nodes": [
                {"id": "tl_1", "role": "orchestrator"},
                {"id": "worker_1", "role": "worker"},
            ],
            "edges": [{"source": "tl_1", "target": "worker_1"}],
        }
    finally:
        _drop_schema(database_url, schema_name)


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:5432/{values['POSTGRES_DB']}"
    )


def _drop_schema(database_url: str, schema_name: str) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
