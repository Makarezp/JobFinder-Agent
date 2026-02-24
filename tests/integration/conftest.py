from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url() -> Generator[str, None, None]:
    """
    Starts a throwaway Postgres container for the entire test session.
    Torn down automatically when the session ends.
    """
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url(driver=None)


@pytest.fixture
async def pg_pool(pg_url: str) -> AsyncGenerator[AsyncConnectionPool, None]:
    """
    Opens a fresh connection pool per test and initialises the LangGraph schema.
    Each test gets a clean setup() but shares the same container.
    """
    async with AsyncConnectionPool(conninfo=pg_url, max_size=5, kwargs={"autocommit": True}) as pool:
        checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await checkpointer.setup()
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()
        yield pool
