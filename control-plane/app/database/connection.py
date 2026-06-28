import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

logger = logging.getLogger("database.connection")

# Global singleton references decoupling structural TCP pools
engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker | None = None


def _build_database_url() -> str:
    """
    Extracts structural configuration limits safely translating standard 
    'postgresql://' strings natively into 'postgresql+asyncpg://' targets optimizing driver bounds.
    """
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/aop")
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    return url


def get_async_engine() -> AsyncEngine:
    """
    Orchestrates the deeply structural SQLAlchemy AsyncEngine bindings.
    Maps physical network pool parameters dynamically via OS Environment limits.
    """
    global engine
    if engine is None:
        db_url = _build_database_url()
        
        # Load critical connection pool constraints optimizing throughput limits
        pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        
        logger.info(f"Instantiating TCP PostgreSQL Asyncpg Matrix (PoolSize: {pool_size}, Overflow: {max_overflow})")
        
        engine = create_async_engine(
            db_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,  # Protects against load-balancer idle connection drops seamlessly
            echo=os.getenv("DB_ECHO_SQL", "false").lower() == "true"
        )
    return engine


def init_db():
    """
    Bootstraps the native FastAPI architectural logic mapping exactly bounded 
    SessionMaker variables statically bound to the physical Engine instances.
    """
    global AsyncSessionLocal
    current_engine = get_async_engine()
    
    AsyncSessionLocal = async_sessionmaker(
        bind=current_engine,
        class_=AsyncSession,
        expire_on_commit=False, # Essential protection logic mapping asynchronous execution environments
        autocommit=False,
        autoflush=False
    )
    logger.info("SQLAlchemy AsyncSessionLocal execution factory natively bootstrapped.")


async def dispose_db():
    """
    Cleanly executes TCP draining protocols terminating idle pool structures securely.
    Must be called exactly within application Shutdown lifecycle hooks.
    """
    global engine
    if engine is not None:
        logger.info("Executing massive pool drainage shutting down PostgreSQL TCP connections...")
        await engine.dispose()
        engine = None
        logger.info("PostgreSQL engine cleanly severed.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI core Dependency Injection logic.
    Yields structurally isolated transactional Sessions. Guarantees rollback behaviors on HTTP panics,
    and unconditionally executes `.close()` upon request resolution bounds.
    """
    if AsyncSessionLocal is None:
        init_db()
        
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.error(f"SQL execution constraint aborted. Transaction forcefully rolled back: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> bool:
    """
    Validates true geometric network health instantly bypassing complex ORM mappings 
    firing raw SQL ('SELECT 1') logic executing purely over the asyncpg C-extension buffers.
    """
    current_engine = engine or get_async_engine()
    try:
        async with current_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            record = result.fetchone()
            if record and record[0] == 1:
                return True
            return False
    except Exception as e:
        logger.error(f"Database structural health-check fatally compromised: {e}")
        return False
