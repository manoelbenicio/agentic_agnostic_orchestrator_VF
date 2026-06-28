from __future__ import annotations

import pytest

from app.settings import DEFAULT_CORS_ORIGINS, Settings


def test_settings_rejects_wildcard_cors_with_credentials(monkeypatch):
    monkeypatch.setenv("AOP_CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="cannot contain '\\*'"):
        Settings.from_env()


def test_settings_accepts_explicit_cors_origins(monkeypatch):
    monkeypatch.setenv("AOP_CORS_ORIGINS", "http://127.0.0.1:13000,http://localhost:13000")

    settings = Settings.from_env()

    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
