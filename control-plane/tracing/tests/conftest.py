from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql

from tracing.repository import TraceRepository
from tracing.schema import connect, init_schema


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


@pytest.fixture
def tracing_conn():
    schema_name = f"tracing_test_{uuid4().hex}"
    conn = connect(database_url=_database_url(), schema_name=schema_name)
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
        conn.commit()
        conn.close()


@pytest.fixture
def repo(tracing_conn):
    return TraceRepository(tracing_conn)
