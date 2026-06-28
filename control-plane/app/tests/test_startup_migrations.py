from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as app_main
from app.settings import Settings


class _FakeState:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def close(self) -> None:
        self._events.append("close")


def test_lifespan_runs_alembic_migrations_before_building_state(monkeypatch):
    events: list[str] = []

    def fake_run_migrations(settings: Settings) -> None:
        assert settings.database_url == "postgresql://example/aop"
        events.append("migrations")

    def fake_build_state(settings: Settings) -> _FakeState:
        assert events == ["migrations"]
        events.append("build_state")
        return _FakeState(events)

    monkeypatch.setattr(app_main, "run_alembic_migrations", fake_run_migrations)
    monkeypatch.setattr(app_main, "build_state", fake_build_state)

    settings = Settings(database_url="postgresql://example/aop", redis_url="redis://example/0")
    with TestClient(app_main.create_app(settings)):
        assert events == ["migrations", "build_state"]

    assert events == ["migrations", "build_state", "close"]


def test_lifespan_skips_alembic_migrations_when_state_is_injected(monkeypatch):
    events: list[str] = []

    def fail_run_migrations(settings: Settings) -> None:
        raise AssertionError("migrations should not run for injected state")

    def fail_build_state(settings: Settings) -> _FakeState:
        raise AssertionError("build_state should not run for injected state")

    monkeypatch.setattr(app_main, "run_alembic_migrations", fail_run_migrations)
    monkeypatch.setattr(app_main, "build_state", fail_build_state)

    settings = Settings(database_url="postgresql://example/aop", redis_url="redis://example/0")
    with TestClient(app_main.create_app(settings, state=_FakeState(events))):
        assert events == []

    assert events == ["close"]
