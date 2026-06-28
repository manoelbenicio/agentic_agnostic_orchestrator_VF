from __future__ import annotations

from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from app.provisioning import init_schema
from conftest import _database_url


def test_provisioning_schema_initialization():
    database_url = _database_url()
    schema_name = f"provisioning_test_{uuid4().hex}"
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        try:
            # Initialize schema
            init_schema(conn, schema_name=schema_name)
            
            # Verify tables exist and we can insert
            with conn.cursor() as cur:
                # Set search path to verify insertion works without qualifying table names
                cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))
                
                # Insert provisioning record
                cur.execute(
                    "INSERT INTO provisioning_records (record_id, target, status) VALUES (%s, %s, %s)",
                    ("record-1", "host-a", "running")
                )
                
                # Insert step result
                cur.execute(
                    "INSERT INTO step_results (step_id, record_id, step_name, status, duration_seconds) VALUES (%s, %s, %s, %s, %s)",
                    ("step-1", "record-1", "install-dependencies", "success", 4.2)
                )
                
                # Query them back
                cur.execute("SELECT target, status FROM provisioning_records WHERE record_id = %s", ("record-1",))
                record = cur.fetchone()
                assert record is not None
                assert record["target"] == "host-a"
                assert record["status"] == "running"
                
                cur.execute("SELECT step_name, status, duration_seconds FROM step_results WHERE step_id = %s", ("step-1",))
                step = cur.fetchone()
                assert step is not None
                assert step["step_name"] == "install-dependencies"
                assert step["status"] == "success"
                assert step["duration_seconds"] == 4.2
                
            conn.commit()
        finally:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
            conn.commit()
