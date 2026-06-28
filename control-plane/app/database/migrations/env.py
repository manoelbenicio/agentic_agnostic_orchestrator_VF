import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import os

# Intercept and map the SQLAlchemy Base containing all the active Declarative mapped metadata natively
from app.database.models import Base

# Alembic Config object, which provides access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging logic bounds
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Mounts the ORM topology natively resolving diff computations natively 
target_metadata = Base.metadata

def _build_database_url() -> str:
    """Safely extracts and formats the structural PostgreSQL asyncpg DSN."""
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/aop")
    # Forces absolute TCP mapping explicitly utilizing asyncpg C-extension
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Outputs strict absolute SQL scripts executing physically without opening network sockets.
    """
    url = _build_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Synchronous execution bound actively within the `run_sync` event loop constraint."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Primary executing engine natively mapping Alembic logic over `asyncpg` bindings.
    """
    configuration = config.get_section(config.config_ini_section, {})
    # Override URL from the dynamic OS ENV block instead of statically relying on alembic.ini
    configuration["sqlalchemy.url"] = _build_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Spawn an explicit connection and execute synchronous alembic binds inside the async wrap
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    # Cleanly sever the database TCP socket pool structurally
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode natively invoking the Asyncio Loop execution."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
