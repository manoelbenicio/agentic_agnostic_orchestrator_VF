"""Alembic startup migration runner."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .settings import Settings

logger = logging.getLogger(__name__)

_FALSE_VALUES = {"0", "false", "no", "off"}


def run_alembic_migrations(settings: Settings) -> None:
    """Run Alembic migrations synchronously before the app accepts traffic.

    The control plane currently supports environments that have not been
    migrated to Alembic yet. In those installs, a missing default alembic.ini is
    treated as a no-op. If AOP_ALEMBIC_CONFIG is set explicitly, the file must
    exist and migration failures abort startup.
    """
    if os.environ.get("AOP_ALEMBIC_AUTO_MIGRATE", "true").lower() in _FALSE_VALUES:
        logger.info("Alembic auto-migrations disabled by AOP_ALEMBIC_AUTO_MIGRATE")
        return

    configured_path = os.environ.get("AOP_ALEMBIC_CONFIG")
    config_path = Path(configured_path) if configured_path else _default_alembic_config_path()
    if not config_path.exists():
        if configured_path:
            raise FileNotFoundError(f"AOP_ALEMBIC_CONFIG does not exist: {config_path}")
        logger.info("No alembic.ini found at %s; skipping Alembic migrations", config_path)
        return

    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:  # pragma: no cover - depends on deploy packaging
        raise RuntimeError("Alembic is required when alembic.ini is present") from exc

    logger.info("Running Alembic migrations from %s", config_path)
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    logger.info("Alembic migrations completed")


def _default_alembic_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "alembic.ini"
