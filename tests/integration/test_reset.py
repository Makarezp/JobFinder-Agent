from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.store.postgres import AsyncPostgresStore

from app.core.database import get_connection_pool, init_db
from app.services.admin_service import AdminService
from app.tools.memory import update_my_profile

# Mark as integration test
pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_id() -> str:
    return f"test_user_{uuid4()}"


@pytest.fixture
def config(user_id: str) -> RunnableConfig:
    return RunnableConfig(configurable={"user_id": user_id})


async def test_reset_functionality(user_id: str, config: RunnableConfig) -> None:
    """
    Test that reset_db_state() correctly truncates all data.
    """
    # 1. Setup Data
    await init_db()
    async with get_connection_pool() as pool:
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()

        # Add profile data
        await update_my_profile.ainvoke({"name": "Delete Me", "role": "Temporary", "store": store}, config=config)

        # Verify data exists
        item = await store.aget((user_id, "profile"), "data")
        assert item is not None, "Failed to set up test data"

    # 2. Execute Reset
    # Use AdminService to verify the service layer wrapper works
    service = AdminService()
    await service.reset_system()

    # 3. Verify Empty
    async with get_connection_pool() as pool:
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]

        # Verify profile is gone
        item = await store.aget((user_id, "profile"), "data")
        assert item is None, "Profile data persist after reset"

        # Verify SQL count
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM store;")
                row = await cur.fetchone()
                assert row is not None
                count = row[0]
                assert count == 0, f"Store table still has {count} rows"
