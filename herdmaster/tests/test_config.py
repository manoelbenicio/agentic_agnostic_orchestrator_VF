from __future__ import annotations

import logging
from pathlib import Path

import pytest

from herdmaster.config import (
    AclConfig,
    AclRole,
    ApiConfig,
    ConfigError,
    ConfigWatcher,
    HerdMasterConfig,
    LoggingConfig,
    PathsConfig,
    WatchdogConfig,
    load_config,
    setup_logging,
    validate_config,
)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def test_load_config_populates_all_sections_and_resolves_relative_paths(tmp_path):
    config_dir = tmp_path / "runtime"
    path = _write_config(
        tmp_path,
        f"""
        [paths]
        config_dir = "{config_dir.as_posix()}"
        db = "state/herdmaster.db"
        socket = "run/herdmaster.sock"
        log = "logs/herdmaster.log"

        [watchdog]
        soft_timeout_s = 7.5
        hard_timeout_s = 21.0
        poll_interval_s = 3
        max_retries = 4
        tertiary_hash_interval_s = 9

        [bus]
        socket_path = "{(tmp_path / "bus.sock").as_posix()}"
        message_ttl_s = 45

        [acl]
        default_policy = "allow"

        [[acl.roles]]
        name = "orchestrator"
        agents = ["A1"]
        can_send_to = ["*"]
        can_receive_from = ["*"]
        can_dispatch_tasks = true
        can_reassign_tasks = true

        [api]
        bind = "127.0.0.1"
        port = 9090
        token = "local-token"

        [logging]
        level = "DEBUG"
        json = false
        """,
    )

    cfg = load_config(path)

    assert isinstance(cfg, HerdMasterConfig)
    assert cfg.paths.config_dir == config_dir
    assert cfg.paths.db == config_dir / "state/herdmaster.db"
    assert cfg.paths.socket == config_dir / "run/herdmaster.sock"
    assert cfg.paths.log == config_dir / "logs/herdmaster.log"
    assert cfg.watchdog.soft_timeout_s == 7.5
    assert cfg.watchdog.hard_timeout_s == 21.0
    assert cfg.watchdog.poll_interval_s == 3
    assert cfg.watchdog.max_retries == 4
    assert cfg.watchdog.tertiary_hash_interval_s == 9
    assert cfg.bus.socket_path == tmp_path / "bus.sock"
    assert cfg.bus.message_ttl_s == 45
    assert cfg.acl.default_policy == "allow"
    assert cfg.acl.roles == (
        AclRole(
            name="orchestrator",
            agents=["A1"],
            can_send_to=["*"],
            can_receive_from=["*"],
            can_dispatch_tasks=True,
            can_reassign_tasks=True,
        ),
    )
    assert cfg.api == ApiConfig(bind="127.0.0.1", port=9090, token="local-token")
    assert cfg.logging == LoggingConfig(level="DEBUG", json=False)


def test_missing_file_and_missing_sections_use_documented_defaults(tmp_path):
    missing = tmp_path / "missing.toml"
    defaults = load_config(missing)

    assert defaults == HerdMasterConfig.defaults()

    config_dir = tmp_path / "only-paths"
    partial = _write_config(
        tmp_path,
        f"""
        [paths]
        config_dir = "{config_dir.as_posix()}"
        """,
    )

    cfg = load_config(partial)

    assert cfg.paths.config_dir == config_dir
    assert cfg.paths.db == config_dir / "herdmaster.db"
    assert cfg.paths.socket == config_dir / "herdmaster.sock"
    assert cfg.paths.log == config_dir / "herdmaster.log"
    assert cfg.watchdog == WatchdogConfig.defaults()
    assert cfg.acl == AclConfig.defaults()
    assert cfg.api == ApiConfig.defaults()
    assert cfg.logging == LoggingConfig.defaults()


@pytest.mark.parametrize(
    ("config", "match"),
    [
        (
            HerdMasterConfig(
                paths=PathsConfig.defaults(),
                watchdog=WatchdogConfig(soft_timeout_s=30.0, hard_timeout_s=30.0),
                bus=HerdMasterConfig.defaults().bus,
                acl=AclConfig.defaults(),
                api=ApiConfig.defaults(),
                logging=LoggingConfig.defaults(),
            ),
            "soft_timeout_s",
        ),
        (
            HerdMasterConfig(
                paths=PathsConfig.defaults(),
                watchdog=WatchdogConfig.defaults(),
                bus=HerdMasterConfig.defaults().bus,
                acl=AclConfig(default_policy="maybe", roles=()),
                api=ApiConfig.defaults(),
                logging=LoggingConfig.defaults(),
            ),
            "default_policy",
        ),
        (
            HerdMasterConfig(
                paths=PathsConfig.defaults(),
                watchdog=WatchdogConfig.defaults(),
                bus=HerdMasterConfig.defaults().bus,
                acl=AclConfig(
                    default_policy="deny",
                    roles=(
                        AclRole("worker", ["A2"], [], [], False, False),
                        AclRole("worker", ["A3"], [], [], False, False),
                    ),
                ),
                api=ApiConfig.defaults(),
                logging=LoggingConfig.defaults(),
            ),
            "duplicate role name",
        ),
        (
            HerdMasterConfig(
                paths=PathsConfig.defaults(),
                watchdog=WatchdogConfig.defaults(),
                bus=HerdMasterConfig.defaults().bus,
                acl=AclConfig.defaults(),
                api=ApiConfig(port=70000),
                logging=LoggingConfig.defaults(),
            ),
            "api.port",
        ),
        (
            HerdMasterConfig(
                paths=PathsConfig.defaults(),
                watchdog=WatchdogConfig.defaults(),
                bus=HerdMasterConfig.defaults().bus,
                acl=AclConfig.defaults(),
                api=ApiConfig.defaults(),
                logging=LoggingConfig(level="TRACE"),
            ),
            "logging.level",
        ),
    ],
)
def test_validate_config_rejects_invalid_values(config, match):
    with pytest.raises(ConfigError, match=match):
        validate_config(config)


def test_acl_toml_shape_parses_roles_with_wildcards_and_groups(tmp_path):
    path = _write_config(
        tmp_path,
        """
        [acl]
        default_policy = "deny"

        [[acl.roles]]
        name = "orchestrator"
        agents = ["A1"]
        can_send_to = ["*"]
        can_receive_from = ["*"]
        can_dispatch_tasks = true
        can_reassign_tasks = true

        [[acl.roles]]
        name = "worker"
        agents = ["A2", "A3", "worker-*"]
        can_send_to = ["orchestrator", "group:reviewers"]
        can_receive_from = ["orchestrator"]
        can_dispatch_tasks = false
        can_reassign_tasks = false

        [[acl.roles]]
        name = "peer_reviewer"
        agents = ["group:reviewers", "A[45]"]
        can_send_to = ["orchestrator", "peer_reviewer"]
        can_receive_from = ["orchestrator", "worker-*"]
        can_dispatch_tasks = false
        can_reassign_tasks = false
        """,
    )

    cfg = load_config(path)

    assert cfg.acl.default_policy == "deny"
    assert [role.name for role in cfg.acl.roles] == [
        "orchestrator",
        "worker",
        "peer_reviewer",
    ]
    orchestrator, worker, reviewer = cfg.acl.roles
    assert orchestrator.agents == ["A1"]
    assert orchestrator.can_send_to == ["*"]
    assert orchestrator.can_dispatch_tasks is True
    assert worker.agents == ["A2", "A3", "worker-*"]
    assert worker.can_send_to == ["orchestrator", "group:reviewers"]
    assert reviewer.agents == ["group:reviewers", "A[45]"]
    assert reviewer.can_receive_from == ["orchestrator", "worker-*"]


def test_setup_logging_returns_working_structlog_logger(capsys):
    logger = setup_logging(LoggingConfig(level="INFO", json=True))

    logger.info("config-test-event", answer=42)

    captured = capsys.readouterr().out
    assert "config-test-event" in captured
    assert '"answer": 42' in captured
    assert logging.getLogger().level == logging.INFO


@pytest.mark.asyncio
async def test_config_watcher_loads_and_validates_initial_config(tmp_path):
    path = _write_config(
        tmp_path,
        """
        [watchdog]
        soft_timeout_s = 2.0
        hard_timeout_s = 5.0

        [acl]
        default_policy = "deny"
        """,
    )
    watcher = ConfigWatcher(path, poll_interval_s=0.01)

    try:
        await watcher.start(lambda cfg: None)

        assert watcher._running is True
        assert watcher._current_config is not None
        assert watcher._current_config.watchdog.soft_timeout_s == 2.0
        assert watcher._current_config.watchdog.hard_timeout_s == 5.0
        assert watcher._current_config.acl.default_policy == "deny"
    finally:
        await watcher.stop()
