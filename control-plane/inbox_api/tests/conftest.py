from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from inbox_api.schema import connect, init_schema


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    postgres_port = os.environ.get("POSTGRES_PORT", "5432")
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{postgres_port}/{values['POSTGRES_DB']}"
    )


@pytest.fixture
def inbox_conn():
    database_url = _database_url()
    schema_name = f"inbox_test_{uuid4().hex}"
    conn = connect(database_url=database_url, schema_name=schema_name)
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()
        with psycopg.connect(database_url) as cleanup:
            with cleanup.cursor() as cur:
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
