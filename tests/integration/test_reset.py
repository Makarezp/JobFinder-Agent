from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.core.database import reset_db_state
from app.tools.memory import update_my_profile

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
def user_id() -> str:
    return f"test_user_{uuid4()}"


@pytest.fixture
def config(user_id: str) -> RunnableConfig:
    return RunnableConfig(configurable={"user_id": user_id})


async def test_reset_functionality(pg_pool: AsyncConnectionPool, user_id: str, config: RunnableConfig) -> None:
    """
    Test that reset_db_state() correctly truncates all data.
    Uses an isolated Postgres container — never touches the dev database.
    """
    store = AsyncPostgresStore(pg_pool)  # type: ignore[arg-type]

    # 1. Seed data
    await update_my_profile.ainvoke({"name": "Delete Me", "role": "Temporary", "store": store}, config=config)
    item = await store.aget((user_id, "profile"), "data")
    assert item is not None, "Failed to set up test data"

    # 2. Execute reset against the container pool
    await reset_db_state(pg_pool)

    # 3. Verify empty
    item = await store.aget((user_id, "profile"), "data")
    assert item is None, "Profile data persisted after reset"

    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM store;")
            row = await cur.fetchone()
            assert row is not None
            count = row[0]
            assert count == 0, f"Store table still has {count} rows"
