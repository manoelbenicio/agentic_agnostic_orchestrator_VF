from __future__ import annotations

import json
import logging

import structlog
from fastapi.testclient import TestClient

from app.logging_config import CORRELATION_ID_HEADER, configure_logging, get_logger
from app.main import create_app


def test_correlation_id_header_is_generated_and_returned() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER]


def test_existing_correlation_id_is_preserved() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={CORRELATION_ID_HEADER: "trace-123"})

    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "trace-123"


def test_structlog_outputs_json_with_correlation_id(capsys) -> None:
    configure_logging()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id="trace-json")

    get_logger("test").info("structured.event", custom="value")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "structured.event"
    assert payload["correlation_id"] == "trace-json"
    assert payload["custom"] == "value"
    assert payload["level"] == "info"


def test_log_level_is_configured_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AOP_LOG_LEVEL", "DEBUG")

    configure_logging()

    assert logging.getLogger().level == logging.DEBUG
