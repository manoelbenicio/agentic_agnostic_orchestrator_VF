from __future__ import annotations

import psycopg
import redis
from fastapi.testclient import TestClient

from app import main as app_main
from app.main import create_app
from app.settings import Settings


class _FakeCursor:
    def __init__(self, *, fails: bool = False) -> None:
        self._fails = fails

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str) -> None:
        if self._fails:
            raise psycopg.OperationalError("postgres probe failed")

    def fetchone(self) -> dict[str, int]:
        return {"ok": 1}


class _FakePostgresConnection:
    def __init__(self, *, fails: bool = False) -> None:
        self._fails = fails

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(fails=self._fails)


class _FakeRedis:
    def __init__(self, *, fails: bool = False) -> None:
        self._fails = fails

    def ping(self) -> bool:
        if self._fails:
            raise redis.RedisError("redis probe failed")
        return True


class _FakeState:
    def __init__(self, *, postgres_fails: bool = False, redis_fails: bool = False) -> None:
        self.postgres_connections = [_FakePostgresConnection(fails=postgres_fails)]
        self.redis_client = _FakeRedis(fails=redis_fails)

    def close(self) -> None:
        return None


def _client(monkeypatch, state: _FakeState) -> TestClient:
    monkeypatch.setattr(
        app_main,
        "_coupling_health",
        lambda state: {
            "status": "connected",
            "last_error": None,
            "message_bus_status": "connected",
            "message_bus_error": None,
        },
    )
    settings = Settings(database_url="postgresql://example/aop", redis_url="redis://example/0")
    return TestClient(create_app(settings, state=state))


def test_health_liveness_returns_ok_without_dependency_probes(monkeypatch):
    with _client(monkeypatch, _FakeState(postgres_fails=True, redis_fails=True)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"] == {"liveness": True}


def test_health_ready_checks_postgres_and_redis(monkeypatch):
    with _client(monkeypatch, _FakeState()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {"postgres": True, "redis": True}


def test_health_ready_returns_503_when_postgres_fails(monkeypatch):
    with _client(monkeypatch, _FakeState(postgres_fails=True)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "not_ready"
    assert response.json()["detail"]["checks"] == {"postgres": False, "redis": True}


def test_health_ready_returns_503_when_redis_fails(monkeypatch):
    with _client(monkeypatch, _FakeState(redis_fails=True)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "not_ready"
    assert response.json()["detail"]["checks"] == {"postgres": True, "redis": False}
