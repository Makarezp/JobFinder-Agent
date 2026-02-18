import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from langchain_core.runnables import RunnableConfig
from langgraph.store.postgres import AsyncPostgresStore

from app.core.database import get_connection_pool, init_db
from app.tools.memory import delete_preference, save_preference, update_my_profile

# Mock config
USER_ID = f"test_user_{uuid4()}"
CONFIG = RunnableConfig(configurable={"user_id": USER_ID})


async def get_test_store() -> AsyncPostgresStore:
    # Quick dirty way to get a store instance for verification
    async with get_connection_pool() as pool:
        return AsyncPostgresStore(pool)  # type: ignore[arg-type]


async def verify_memory_system() -> None:
    print(f"--- 0. Setup (User: {USER_ID}) ---")
    await init_db()

    # We need a store instance to pass to the tools manually for this script,
    # or rely on the tool's injection if we were running via graph.
    # The tools in memory.py take `store: Annotated[BaseStore, InjectedStore]`.
    # When calling manually, we must pass `store`.

    async with get_connection_pool() as pool:
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()

        print("\n--- 1. Testing Profile Update ---")
        # Call tool directly
        res = await update_my_profile.ainvoke({"name": "Alice Code", "role": "Senior Architect", "store": store}, config=CONFIG)
        print(f"Update Result: {res}")

        # Verify
        namespace = (USER_ID, "profile")
        item = await store.aget(namespace, "data")
        print(f"Fetched Profile Item: {item}")
        assert item is not None
        assert item.value["name"] == "Alice Code"
        assert item.value["role"] == "Senior Architect"

        print("\n--- 2. Testing Preferences ---")
        res = await save_preference.ainvoke({"key": "location", "value": "Berlin", "category": "hard", "store": store}, config=CONFIG)
        print(f"Save Result: {res}")

        res = await save_preference.ainvoke({"key": "salary", "value": 120000, "category": "hard", "store": store}, config=CONFIG)
        print(f"Save Result: {res}")

        # Verify
        namespace_prefs = (USER_ID, "preferences")
        pref_item = await store.aget(namespace_prefs, "location")
        print(f"Fetched Preference: {pref_item}")
        assert pref_item is not None
        assert pref_item.value["value"] == "Berlin"

        print("\n--- 3. Testing Preference Deletion ---")
        res = await delete_preference.ainvoke({"key": "location", "store": store}, config=CONFIG)
        print(f"Delete Result: {res}")

        pref_item = await store.aget(namespace_prefs, "location")
        print(f"Fetched Preference after delete: {pref_item}")
        assert pref_item is None

        print("\n--- Verification Successful ---")


if __name__ == "__main__":
    asyncio.run(verify_memory_system())
