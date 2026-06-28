from __future__ import annotations

import logging
from uuid import uuid4

import psycopg
from psycopg import sql

from app.dependencies import _pooled_connection, _pool_reconnect_failed

from conftest import _database_url


def test_pool_check_replaces_broken_connection_before_checkout():
    database_url = _database_url()
    schema_name = f"app_pool_test_{uuid4().hex}"
    pool, held_conn = _pooled_connection(database_url, schema_name=schema_name, init_schema=lambda conn: None)
    try:
        with pool.connection() as candidate:
            pid = candidate.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]

        with psycopg.connect(database_url) as killer:
            killer.execute("SELECT pg_terminate_backend(%s)", (pid,))

        with pool.connection() as checked:
            assert checked.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    finally:
        held_conn.close()
        pool.close()
        with psycopg.connect(database_url) as cleanup:
            cleanup.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))


def test_held_connection_rolls_back_after_statement_error():
    database_url = _database_url()
    schema_name = f"app_pool_rollback_test_{uuid4().hex}"
    pool, held_conn = _pooled_connection(database_url, schema_name=schema_name, init_schema=lambda conn: None)
    try:
        try:
            with held_conn.cursor() as cur:
                cur.execute("SELECT * FROM table_that_does_not_exist")
        except psycopg.Error:
            pass

        with held_conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            assert cur.fetchone()["ok"] == 1
    finally:
        held_conn.close()
        pool.close()
        with psycopg.connect(database_url) as cleanup:
            cleanup.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))


def test_held_connection_reconnects_after_backend_termination():
    database_url = _database_url()
    schema_name = f"app_pool_reconnect_test_{uuid4().hex}"
    pool, held_conn = _pooled_connection(database_url, schema_name=schema_name, init_schema=lambda conn: None)
    try:
        with held_conn.cursor() as cur:
            cur.execute("SELECT pg_backend_pid() AS pid")
            pid = cur.fetchone()["pid"]

        with psycopg.connect(database_url) as killer:
            killer.execute("SELECT pg_terminate_backend(%s)", (pid,))

        with held_conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            assert cur.fetchone()["ok"] == 1
    finally:
        held_conn.close()
        pool.close()
        with psycopg.connect(database_url) as cleanup:
            cleanup.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))


def test_reconnect_failed_callback_logs_critical(caplog):
    database_url = _database_url()
    schema_name = f"app_pool_log_test_{uuid4().hex}"
    pool, held_conn = _pooled_connection(database_url, schema_name=schema_name, init_schema=lambda conn: None)
    try:
        with caplog.at_level(logging.CRITICAL):
            _pool_reconnect_failed(pool)
        assert "control-plane DB pool reconnect FAILED" in caplog.text
    finally:
        held_conn.close()
        pool.close()
        with psycopg.connect(database_url) as cleanup:
            cleanup.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
