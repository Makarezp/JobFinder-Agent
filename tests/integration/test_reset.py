from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.core.database import reset_db_state, reset_workspace_state
from app.services.profile_service import ProfileService
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


async def test_reset_discovery_clears_only_discovery(pg_pool: AsyncConnectionPool, user_id: str, config: RunnableConfig) -> None:
    """
    reset_workspace_state('discovery') and reset_discovery_state() clear discovery
    checkpoints and job-related store namespaces, while leaving the profile intact.
    """
    store = AsyncPostgresStore(pg_pool)  # type: ignore[arg-type]
    profile_service = ProfileService(store)

    # 1. Seed profile data (must survive the reset)
    await update_my_profile.ainvoke({"name": "Alice", "role": "Engineer", "store": store}, config=config)
    profile_item = await store.aget((user_id, "profile"), "data")
    assert profile_item is not None, "Failed to set up profile data"

    # 2. Seed discovery store data: a pending job and a seen job
    await store.aput(
        (user_id, "pending_jobs"),
        "job_1",
        {
            "id": "job_1",
            "title": "Dev",
            "company": "Acme",
            "location": "London",
            "description": "desc",
            "apply_link": "http://x.com",
            "removed": False,
            "added_at": "2024-01-01",
        },
    )
    await store.aput((user_id, "seen_jobs"), "job_1", {"id": "job_1", "title": "Dev", "company": "Acme", "location": "London"})

    # 3. Seed a discovery checkpoint and a profile checkpoint via raw SQL
    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
                "VALUES (%s, '', gen_random_uuid(), NULL, 'empty', '{}'::jsonb, '{}'::jsonb), "
                "       (%s, '', gen_random_uuid(), NULL, 'empty', '{}'::jsonb, '{}'::jsonb);",
                (f"{user_id}_discovery", f"{user_id}_profile"),
            )

    # 4. Execute targeted discovery reset
    await reset_workspace_state("discovery", pg_pool)
    await profile_service.reset_discovery_state(user_id)

    # 5. Discovery checkpoints must be gone; profile checkpoint must remain
    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s;",
                (f"{user_id}_discovery",),
            )
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 0, "Discovery checkpoint was not deleted"

            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s;",
                (f"{user_id}_profile",),
            )
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 1, "Profile checkpoint was incorrectly deleted"

    # 6. Discovery store namespaces must be empty
    pending = await store.asearch((user_id, "pending_jobs"))
    assert len(pending) == 0, "pending_jobs was not cleared"
    seen = await store.asearch((user_id, "seen_jobs"))
    assert len(seen) == 0, "seen_jobs was not cleared"

    # 7. Profile store data must be intact
    profile_item = await store.aget((user_id, "profile"), "data")
    assert profile_item is not None, "Profile was incorrectly wiped by discovery reset"
