"""Additional config tests covering environment variable precedence and edge cases.

Gap coverage:
- HERDR_SOCKET_PATH env var takes precedence over [herdr].socket_path
- HERDR_SESSION env var resolves to ~/.config/herdr/sessions/<n>/herdr.sock
- [herdr] section absent in TOML → default socket path used
- socket_path with ~ expands correctly
- HERDR_SOCKET_PATH takes precedence even when both env vars are set
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from herdmaster.config import HerdrConfig, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_toml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# HerdrConfig.from_dict / _resolve_socket_path tests
# ---------------------------------------------------------------------------

class TestHerdrSocketPathEnvPrecedence:
    """HERDR_SOCKET_PATH env var must win over any TOML value."""

    def test_socket_path_env_overrides_toml(self, tmp_path, monkeypatch):
        env_path = str(tmp_path / "env_socket.sock")
        monkeypatch.setenv("HERDR_SOCKET_PATH", env_path)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        cfg = HerdrConfig.from_dict({"socket_path": str(tmp_path / "toml_socket.sock")})

        assert cfg.socket_path == Path(env_path)

    def test_socket_path_env_overrides_session_env(self, tmp_path, monkeypatch):
        """HERDR_SOCKET_PATH beats HERDR_SESSION when both are set."""
        env_path = str(tmp_path / "explicit.sock")
        monkeypatch.setenv("HERDR_SOCKET_PATH", env_path)
        monkeypatch.setenv("HERDR_SESSION", "my-session")

        cfg = HerdrConfig.from_dict({})

        assert cfg.socket_path == Path(env_path)

    def test_socket_path_env_with_tilde_expands(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERDR_SOCKET_PATH", "~/some/path/herdr.sock")
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        cfg = HerdrConfig.from_dict({})

        assert "~" not in str(cfg.socket_path)
        assert cfg.socket_path == Path("~/some/path/herdr.sock").expanduser()

    def test_no_env_uses_toml_socket_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)
        toml_path = str(tmp_path / "custom.sock")

        cfg = HerdrConfig.from_dict({"socket_path": toml_path})

        assert cfg.socket_path == Path(toml_path)


class TestHerdrSessionEnvVar:
    """HERDR_SESSION env var should resolve to the session-namespaced socket."""

    def test_session_env_resolves_socket_path(self, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.setenv("HERDR_SESSION", "42")

        cfg = HerdrConfig.from_dict({})

        expected = Path("~/.config/herdr/sessions/42/herdr.sock").expanduser()
        assert cfg.socket_path == expected

    def test_session_env_stored_on_config(self, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.setenv("HERDR_SESSION", "dev")

        cfg = HerdrConfig.from_dict({})

        assert cfg.session == "dev"

    def test_no_session_env_no_toml_session_gives_none(self, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        cfg = HerdrConfig.from_dict({})

        assert cfg.session is None

    def test_toml_session_used_when_no_env(self, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        cfg = HerdrConfig.from_dict({"session": "toml-session"})

        assert cfg.session == "toml-session"


class TestHerdrSectionAbsent:
    """[herdr] section absent in TOML uses documented defaults."""

    def test_missing_herdr_section_uses_default_socket(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        path = _write_toml(tmp_path, "[watchdog]\nsoft_timeout_s = 2.0\nhard_timeout_s = 5.0\n")
        cfg = load_config(path)

        expected_default = Path("~/.config/herdr/herdr.sock").expanduser()
        assert cfg.herdr.socket_path == expected_default

    def test_missing_file_herdr_section_is_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        cfg = load_config(tmp_path / "nonexistent.toml")

        expected_default = Path("~/.config/herdr/herdr.sock").expanduser()
        assert cfg.herdr.socket_path == expected_default

    def test_herdr_section_present_overrides_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        sock = tmp_path / "custom.sock"
        path = _write_toml(tmp_path, f'[herdr]\nsocket_path = "{sock.as_posix()}"\n')
        cfg = load_config(path)

        assert cfg.herdr.socket_path == sock


class TestSocketPathTildeExpansion:
    """~-prefixed paths must be fully expanded (no literal ~ in result)."""

    def test_toml_socket_path_tilde_expands(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        path = _write_toml(tmp_path, "[herdr]\nsocket_path = \"~/my/herdr.sock\"\n")
        cfg = load_config(path)

        assert "~" not in str(cfg.herdr.socket_path)
        assert cfg.herdr.socket_path == Path("~/my/herdr.sock").expanduser()

    def test_default_herdr_path_has_no_tilde(self, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        cfg = HerdrConfig.defaults()

        assert "~" not in str(cfg.socket_path)

    def test_session_socket_path_has_no_tilde(self, monkeypatch):
        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.setenv("HERDR_SESSION", "99")

        cfg = HerdrConfig.from_dict({})

        assert "~" not in str(cfg.socket_path)


# ---------------------------------------------------------------------------
# Adapter-level _resolve_socket_path integration
# (tests the adapter's own env-var resolution, separate from HerdrConfig)
# ---------------------------------------------------------------------------

class TestAdapterSocketPathResolution:
    """HerdrAdapter._resolve_socket_path reads the same env vars."""

    def test_adapter_uses_herdr_socket_path_env(self, tmp_path, monkeypatch):
        from herdmaster.herdr.adapter import HerdrAdapter

        sock = str(tmp_path / "env.sock")
        monkeypatch.setenv("HERDR_SOCKET_PATH", sock)
        monkeypatch.delenv("HERDR_SESSION", raising=False)

        adapter = HerdrAdapter()  # no explicit socket_path
        assert adapter.socket_path == Path(sock)

    def test_adapter_uses_herdr_session_env(self, monkeypatch):
        from herdmaster.herdr.adapter import HerdrAdapter

        monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
        monkeypatch.setenv("HERDR_SESSION", "5")

        adapter = HerdrAdapter()
        expected = Path("~/.config/herdr/sessions/5/herdr.sock").expanduser()
        assert adapter.socket_path == expected

    def test_adapter_explicit_path_overrides_env(self, tmp_path, monkeypatch):
        from herdmaster.herdr.adapter import HerdrAdapter

        monkeypatch.setenv("HERDR_SOCKET_PATH", str(tmp_path / "env.sock"))
        explicit = tmp_path / "explicit.sock"

        adapter = HerdrAdapter(socket_path=explicit)
        assert adapter.socket_path == explicit
