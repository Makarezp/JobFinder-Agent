import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_db_connection_uri() -> str:
    """Externalized for scalability and testing."""
    if settings.DATABASE_URL:
        # If full URL is provided in env var (e.g. production)
        return settings.DATABASE_URL

    # Construct from components
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


@asynccontextmanager
async def get_connection_pool() -> AsyncGenerator[AsyncConnectionPool, None]:
    """
    Yields an async connection pool.
    Usage:
        async with get_connection_pool() as pool:
            checkpointer = AsyncPostgresSaver(pool)
    """
    connection_uri = get_db_connection_uri()
    # autocommit=True is generally recommended for LangGraph usage to avoid manual commit management
    # unless specific transactional logic is needed.
    # kwargs={"autocommit": True} passes this to the underlying connection.

    async with AsyncConnectionPool(conninfo=connection_uri, max_size=20, kwargs={"autocommit": True}) as pool:
        yield pool


async def init_db() -> None:
    """
    Idempotent initialization of the database.
    Creates necessary tables for:
    1. AsyncPostgresSaver (checkpoints, writes)
    2. PostgresStore (store)
    """
    logger.info("Initializing database...")
    async with get_connection_pool() as pool:
        # 1. Initialize Checkpointer tables
        checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await checkpointer.setup()
        logger.info("Checkpointer tables initialized.")

        # 2. Initialize Store tables
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()
        logger.info("Store tables initialized.")

    logger.info("Database initialization complete.")


async def reset_db_state(pool: AsyncConnectionPool | None = None) -> None:
    """
    CRITICAL: Completely wipes the database state.
    Used for the 'Reset Application' feature.
    Accepts an optional pool for testing against isolated containers.
    """
    logger.warning("EXECUTING HARD RESET: Wiping all database tables.")

    async def _truncate(p: AsyncConnectionPool) -> None:
        async with p.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE store, checkpoints, checkpoint_blobs, checkpoint_writes RESTART IDENTITY CASCADE;")

    if pool is not None:
        await _truncate(pool)
    else:
        async with get_connection_pool() as p:
            await _truncate(p)

    logger.info("Database reset complete.")
