"""
HerdMaster Configuration System

TOML configuration loading, validation, hot-reload, and structured logging setup.

Example TOML (equivalent to config/herdmaster.example.toml created by HM-000):

```toml
[paths]
config_dir = "~/.config/herdmaster"
db = "herdmaster.db"
socket = "herdmaster.sock"
log = "herdmaster.log"

[watchdog]
soft_timeout_s = 10.0
hard_timeout_s = 30.0
poll_interval_s = 15
max_retries = 3
tertiary_hash_interval_s = 30

[bus]
socket_path = "~/.config/herdmaster/herdmaster.sock"
message_ttl_s = 300

[herdr]
socket_path = "~/.config/herdr/herdr.sock"

[acl]
default_policy = "deny"
[[acl.roles]]
name = "admin"
agents = ["*"]
can_send_to = ["*"]
can_receive_from = ["*"]
can_dispatch_tasks = true
can_reassign_tasks = true

[[acl.roles]]
name = "worker"
agents = ["worker-*"]
can_send_to = ["admin", "worker-*"]
can_receive_from = ["admin", "worker-*"]
can_dispatch_tasks = false
can_reassign_tasks = false

[api]
bind = "127.0.0.1"
port = 8080
token = ""  # optional

[database]
url = ""  # optional; DATABASE_URL env takes precedence

[logging]
level = "INFO"
json = true
```
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""
    pass


@dataclass(frozen=True, slots=True)
class PathsConfig:
    """Filesystem paths configuration."""
    config_dir: Path
    db: Path
    socket: Path
    log: Path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PathsConfig:
        config_dir = Path(data.get("config_dir", "~/.config/herdmaster")).expanduser()
        db = Path(data.get("db", "herdmaster.db"))
        if not db.is_absolute():
            db = config_dir / db
        else:
            db = db.expanduser()
        socket = Path(data.get("socket", "herdmaster.sock"))
        if not socket.is_absolute():
            socket = config_dir / socket
        else:
            socket = socket.expanduser()
        log = Path(data.get("log", "herdmaster.log"))
        if not log.is_absolute():
            log = config_dir / log
        else:
            log = log.expanduser()
        return cls(
            config_dir=config_dir,
            db=db,
            socket=socket,
            log=log,
        )

    @classmethod
    def defaults(cls) -> PathsConfig:
        config_dir = Path("~/.config/herdmaster").expanduser()
        return cls(
            config_dir=config_dir,
            db=config_dir / "herdmaster.db",
            socket=config_dir / "herdmaster.sock",
            log=config_dir / "herdmaster.log",
        )


@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    """Watchdog timeout and retry configuration."""
    soft_timeout_s: float
    hard_timeout_s: float
    poll_interval_s: int = 15
    max_retries: int = 3
    tertiary_hash_interval_s: int = 30
    # Optional allowlist of agent IDs that the watchdog is permitted to sync/upsert.
    # When non-empty, any Herdr pane whose ID is NOT in this set is silently ignored
    # at the point of ingestion — it is never written to the DB, never health-checked,
    # and never dispatched to. This is the primary defence against auto-registration
    # of phantom agents by Herdr workspace syncs.
    # Leave empty (default) to allow all agents (backwards-compatible behaviour).
    agent_allowlist: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WatchdogConfig:
        raw_allowlist = data.get("agent_allowlist", [])
        allowlist: frozenset[str] = (
            frozenset(str(a) for a in raw_allowlist)
            if isinstance(raw_allowlist, (list, tuple, set))
            else frozenset()
        )
        return cls(
            soft_timeout_s=float(data.get("soft_timeout_s", 10.0)),
            hard_timeout_s=float(data.get("hard_timeout_s", 30.0)),
            poll_interval_s=int(data.get("poll_interval_s", 15)),
            max_retries=int(data.get("max_retries", 3)),
            tertiary_hash_interval_s=int(data.get("tertiary_hash_interval_s", 30)),
            agent_allowlist=allowlist,
        )

    @classmethod
    def defaults(cls) -> WatchdogConfig:
        return cls(soft_timeout_s=10.0, hard_timeout_s=30.0)


@dataclass(frozen=True, slots=True)
class BusConfig:
    """Message bus configuration."""
    socket_path: Path
    message_ttl_s: int = 300

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BusConfig:
        return cls(
            socket_path=Path(data.get("socket_path", "~/.config/herdmaster/herdmaster.sock")).expanduser(),
            message_ttl_s=int(data.get("message_ttl_s", 300)),
        )

    @classmethod
    def defaults(cls) -> BusConfig:
        return cls(socket_path=Path("~/.config/herdmaster/herdmaster.sock").expanduser())


@dataclass(frozen=True, slots=True)
class HerdrConfig:
    """Herdr socket integration configuration."""
    socket_path: Path
    session: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HerdrConfig:
        env_socket_path = os.environ.get("HERDR_SOCKET_PATH")
        env_session = os.environ.get("HERDR_SESSION")
        configured_socket_path = data.get("socket_path")
        configured_session = data.get("session")
        session = env_session or (str(configured_session) if configured_session else None)

        if env_socket_path:
            socket_path = Path(env_socket_path)
        elif configured_socket_path:
            socket_path = Path(str(configured_socket_path))
        elif env_session:
            socket_path = Path("~/.config/herdr/sessions").expanduser() / env_session / "herdr.sock"
        else:
            socket_path = Path("~/.config/herdr/herdr.sock")

        return cls(socket_path=socket_path.expanduser(), session=session)

    @classmethod
    def defaults(cls) -> HerdrConfig:
        return cls.from_dict({})


@dataclass(frozen=True, slots=True)
class AclRole:
    """ACL role definition."""
    name: str
    agents: list[str]
    can_send_to: list[str]
    can_receive_from: list[str]
    can_dispatch_tasks: bool
    can_reassign_tasks: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AclRole:
        return cls(
            name=str(data["name"]),
            agents=list(data.get("agents", [])),
            can_send_to=list(data.get("can_send_to", [])),
            can_receive_from=list(data.get("can_receive_from", [])),
            can_dispatch_tasks=bool(data.get("can_dispatch_tasks", False)),
            can_reassign_tasks=bool(data.get("can_reassign_tasks", False)),
        )


@dataclass(frozen=True, slots=True)
class AclConfig:
    """Access control list configuration."""
    default_policy: str
    roles: tuple[AclRole, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AclConfig:
        roles_data = data.get("roles", [])
        roles = tuple(AclRole.from_dict(r) for r in roles_data)
        return cls(
            default_policy=str(data.get("default_policy", "deny")),
            roles=roles,
        )

    @classmethod
    def defaults(cls) -> AclConfig:
        return cls(default_policy="deny", roles=())


@dataclass(frozen=True, slots=True)
class ApiConfig:
    """API server configuration."""
    bind: str = "127.0.0.1"
    port: int = 8080
    token: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApiConfig:
        return cls(
            bind=str(data.get("bind", "127.0.0.1")),
            port=int(data.get("port", 8080)),
            token=str(data.get("token", "")),
        )

    @classmethod
    def defaults(cls) -> ApiConfig:
        return cls()


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Postgres database configuration."""
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatabaseConfig:
        configured_url = str(data.get("url", ""))
        if configured_url and not os.environ.get("DATABASE_URL"):
            os.environ["DATABASE_URL"] = configured_url
        return cls(url=str(os.environ.get("DATABASE_URL") or configured_url))

    @classmethod
    def defaults(cls) -> DatabaseConfig:
        return cls.from_dict({})


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Structured logging configuration."""
    level: str = "INFO"
    json: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoggingConfig:
        return cls(
            level=str(data.get("level", "INFO")).upper(),
            json=bool(data.get("json", True)),
        )

    @classmethod
    def defaults(cls) -> LoggingConfig:
        return cls()


@dataclass(frozen=True, slots=True)
class HerdMasterConfig:
    """Root configuration object for HerdMaster."""
    paths: PathsConfig
    watchdog: WatchdogConfig
    bus: BusConfig
    acl: AclConfig
    api: ApiConfig
    logging: LoggingConfig
    database: DatabaseConfig = field(default_factory=DatabaseConfig.defaults)
    herdr: HerdrConfig = field(default_factory=HerdrConfig.defaults)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HerdMasterConfig:
        return cls(
            paths=PathsConfig.from_dict(data.get("paths", {})),
            watchdog=WatchdogConfig.from_dict(data.get("watchdog", {})),
            bus=BusConfig.from_dict(data.get("bus", {})),
            herdr=HerdrConfig.from_dict(data.get("herdr", {})),
            acl=AclConfig.from_dict(data.get("acl", {})),
            api=ApiConfig.from_dict(data.get("api", {})),
            database=DatabaseConfig.from_dict(data.get("database", {})),
            logging=LoggingConfig.from_dict(data.get("logging", {})),
        )

    @classmethod
    def defaults(cls) -> HerdMasterConfig:
        return cls(
            paths=PathsConfig.defaults(),
            watchdog=WatchdogConfig.defaults(),
            bus=BusConfig.defaults(),
            herdr=HerdrConfig.defaults(),
            acl=AclConfig.defaults(),
            api=ApiConfig.defaults(),
            database=DatabaseConfig.defaults(),
            logging=LoggingConfig.defaults(),
        )


def load_config(path: str | Path | None = None) -> HerdMasterConfig:
    """
    Load configuration from a TOML file.

    Args:
        path: Path to config.toml. If None, uses default location
              ~/.config/herdmaster/config.toml

    Returns:
        Fully populated HerdMasterConfig with defaults for missing keys.

    Raises:
        ConfigError: If the file exists but contains invalid TOML or invalid values.
    """
    if path is None:
        path = Path("~/.config/herdmaster/config.toml").expanduser()
    else:
        path = Path(path)

    if not path.exists():
        return HerdMasterConfig.defaults()

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {path}: {e}") from e

    try:
        return HerdMasterConfig.from_dict(raw)
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigError(f"Invalid config value in {path}: {e}") from e


def validate_config(cfg: HerdMasterConfig) -> None:
    """
    Validate a loaded configuration.

    Args:
        cfg: The configuration to validate.

    Raises:
        ConfigError: If validation fails, with a message naming the offending key.
    """
    # Watchdog: soft_timeout < hard_timeout
    if cfg.watchdog.soft_timeout_s >= cfg.watchdog.hard_timeout_s:
        raise ConfigError(
            f"watchdog.soft_timeout_s ({cfg.watchdog.soft_timeout_s}) "
            f"must be < hard_timeout_s ({cfg.watchdog.hard_timeout_s})"
        )

    # ACL: default_policy must be allow or deny
    if cfg.acl.default_policy not in ("allow", "deny"):
        raise ConfigError(
            f"acl.default_policy must be 'allow' or 'deny', got '{cfg.acl.default_policy}'"
        )

    # ACL: unique role names
    role_names = [r.name for r in cfg.acl.roles]
    if len(role_names) != len(set(role_names)):
        seen = set()
        for name in role_names:
            if name in seen:
                raise ConfigError(f"acl.roles: duplicate role name '{name}'")
            seen.add(name)

    # ACL: agents, can_send_to, can_receive_from must be lists of strings
    for role in cfg.acl.roles:
        for field_name in ("agents", "can_send_to", "can_receive_from"):
            value = getattr(role, field_name)
            if not isinstance(value, list):
                raise ConfigError(f"acl.roles[{role.name}].{field_name} must be a list")
            for item in value:
                if not isinstance(item, str):
                    raise ConfigError(
                        f"acl.roles[{role.name}].{field_name} must contain only strings, "
                        f"got {type(item).__name__}"
                    )

    # Watchdog: positive intervals
    if cfg.watchdog.poll_interval_s <= 0:
        raise ConfigError("watchdog.poll_interval_s must be > 0")
    if cfg.watchdog.tertiary_hash_interval_s <= 0:
        raise ConfigError("watchdog.tertiary_hash_interval_s must be > 0")
    if cfg.watchdog.max_retries < 0:
        raise ConfigError("watchdog.max_retries must be >= 0")

    # Bus: positive TTL
    if cfg.bus.message_ttl_s <= 0:
        raise ConfigError("bus.message_ttl_s must be > 0")

    # Herdr: socket path must resolve to a non-empty Path object
    if not isinstance(cfg.herdr.socket_path, Path):
        raise ConfigError("herdr.socket_path must be a pathlib.Path")
    if str(cfg.herdr.socket_path).strip() == "":
        raise ConfigError("herdr.socket_path must not be empty")
    if cfg.herdr.session is not None and str(cfg.herdr.session).strip() == "":
        raise ConfigError("herdr.session must not be empty")

    # API: valid port
    if not (1 <= cfg.api.port <= 65535):
        raise ConfigError(f"api.port must be 1-65535, got {cfg.api.port}")

    # Logging: valid level
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if cfg.logging.level not in valid_levels:
        raise ConfigError(f"logging.level must be one of {valid_levels}, got '{cfg.logging.level}'")


class ConfigWatcher:
    """
    Async configuration hot-reloader.

    Polls the config file's mtime and invokes a callback with a freshly
    loaded and validated config. Never crashes on bad reload - logs error
    and keeps the old config.
    """

    def __init__(
        self,
        config_path: str | Path,
        poll_interval_s: float = 5.0,
    ):
        self.config_path = Path(config_path).expanduser()
        self.poll_interval_s = poll_interval_s
        self._current_config: Optional[HerdMasterConfig] = None
        self._mtime: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def watch(
        self,
        on_reload: Callable[[HerdMasterConfig], Any],
        initial_config: Optional[HerdMasterConfig] = None,
    ) -> None:
        """Start watching for config changes."""
        if self._running:
            return

        self._on_reload = on_reload
        self._current_config = initial_config or load_config(self.config_path)
        validate_config(self._current_config)

        if self.config_path.exists():
            self._mtime = self.config_path.stat().st_mtime

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def start(
        self,
        on_reload: Callable[[HerdMasterConfig], Any],
        initial_config: Optional[HerdMasterConfig] = None,
    ) -> None:
        """Alias for watch()."""
        await self.watch(on_reload, initial_config)

    async def stop(self) -> None:
        """Stop watching for config changes."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval_s)
                if not self._running:
                    break

                if not self.config_path.exists():
                    continue

                mtime = self.config_path.stat().st_mtime
                if mtime <= self._mtime:
                    continue

                # File changed - attempt reload
                self._mtime = mtime
                try:
                    new_config = load_config(self.config_path)
                    validate_config(new_config)
                    self._current_config = new_config
                    if asyncio.iscoroutinefunction(self._on_reload):
                        await self._on_reload(new_config)
                    else:
                        self._on_reload(new_config)
                except ConfigError as e:
                    # Log error but keep old config - never crash
                    logging.getLogger(__name__).error(
                        "Config reload failed, keeping previous config: %s", e
                    )
                except Exception as e:
                    logging.getLogger(__name__).exception(
                        "Unexpected error during config reload: %s", e
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.getLogger(__name__).exception("Error in config watch loop: %s", e)


def setup_logging(cfg: LoggingConfig) -> "structlog.BoundLogger":
    """
    Configure structlog for JSON output with ISO timestamps.

    Args:
        cfg: LoggingConfig with level and json settings.

    Returns:
        A configured structlog.BoundLogger instance.
    """
    import structlog
    from structlog.stdlib import ProcessorFormatter

    # Determine log level
    level = getattr(logging, cfg.level, logging.INFO)

    # Configure stdlib logging
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # JSON formatter for structlog
    if cfg.json:
        formatter = ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
            ],
        )
    else:
        formatter = ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(),
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
            ],
        )

    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()
