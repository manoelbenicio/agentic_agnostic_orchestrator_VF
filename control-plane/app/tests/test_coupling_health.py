from __future__ import annotations

from types import SimpleNamespace

from app.dependencies import refresh_message_bus
from app.main import _coupling_health
from app.settings import Settings


def test_refresh_message_bus_degrades_when_probe_raises(monkeypatch) -> None:
    import coupling.hm_client as hm_client

    def broken_probe(*args, **kwargs):
        raise TimeoutError("probe timed out")

    monkeypatch.setattr(hm_client, "herdmaster_authenticated_probe", broken_probe)
    state = SimpleNamespace(
        settings=Settings(herdmaster_url="http://127.0.0.1:1", herdmaster_token="token"),
        message_bus=object(),
        message_bus_status={"status": "connected", "last_error": None},
    )

    status = refresh_message_bus(state)

    assert status["status"] == "degraded"
    assert "probe failed" in str(status["last_error"])
    assert state.message_bus is None


def test_coupling_health_reconnects_message_bus_when_probe_recovers(monkeypatch) -> None:
    import coupling.hm_client as hm_client

    monkeypatch.setattr(hm_client, "herdmaster_authenticated_probe", lambda *args, **kwargs: True)
    state = SimpleNamespace(
        settings=Settings(herdmaster_url="http://127.0.0.1:8080", herdmaster_token="token"),
        message_bus=None,
        message_bus_status={"status": "degraded", "last_error": "previous outage"},
    )

    health = _coupling_health(state)

    assert health == {
        "status": "connected",
        "last_error": None,
        "message_bus_status": "connected",
        "message_bus_error": None,
    }
    assert state.message_bus is not None


def test_refresh_message_bus_recovers_from_rotated_runtime_token(monkeypatch, tmp_path) -> None:
    import coupling.hm_client as hm_client

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "herdmaster.token").write_text("fresh-token\n", encoding="utf-8")
    monkeypatch.setenv("AOP_OPS_RUNTIME_DIR", str(runtime_dir))

    probes: list[str] = []

    def probe(_url: str, *, token: str, **_kwargs) -> bool:
        probes.append(token)
        return token == "fresh-token"

    monkeypatch.setattr(hm_client, "herdmaster_authenticated_probe", probe)
    state = SimpleNamespace(
        settings=Settings(herdmaster_url="http://127.0.0.1:8085", herdmaster_token="stale-token"),
        message_bus=None,
        message_bus_status={"status": "degraded", "last_error": "old token rejected"},
    )

    status = refresh_message_bus(state)

    assert probes[:2] == ["stale-token", "fresh-token"]
    assert status == {"status": "connected", "last_error": None}
    assert state.message_bus is not None


def test_coupling_health_uses_runtime_token_when_settings_token_missing(monkeypatch, tmp_path) -> None:
    import coupling.hm_client as hm_client

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "herdmaster.token").write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("AOP_OPS_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setattr(hm_client, "herdmaster_authenticated_probe", lambda _url, *, token, **_kwargs: token == "file-token")
    state = SimpleNamespace(
        settings=Settings(herdmaster_url="http://127.0.0.1:8085", herdmaster_token=None),
        message_bus=None,
        message_bus_status={"status": "degraded", "last_error": "missing token"},
    )

    health = _coupling_health(state)

    assert health["status"] == "connected"
    assert health["message_bus_status"] == "connected"
    assert state.message_bus is not None
