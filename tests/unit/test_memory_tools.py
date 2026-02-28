from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.store.memory import InMemoryStore

from app.tools.memory import delete_preference, finalize_profile, save_preference, update_my_profile


class FailingPutStore(InMemoryStore):
    async def aput(self, *args: Any, **kwargs: Any) -> None:
        raise Exception("Database error")

    def put(self, *args: Any, **kwargs: Any) -> None:
        raise Exception("Database error")


class FailingDeleteStore(InMemoryStore):
    async def adelete(self, *args: Any, **kwargs: Any) -> None:
        raise Exception("Delete error")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise Exception("Delete error")


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def config() -> RunnableConfig:
    return {"configurable": {"user_id": "test_user"}}


@pytest.mark.asyncio
async def test_update_my_profile_success(store: InMemoryStore, config: RunnableConfig) -> None:
    # Act
    result = await update_my_profile.ainvoke({"name": "Test User", "role": "Tester", "store": store}, config=config)

    # Assert
    assert "Profile updated successfully" in result

    # Verify store content
    namespace = ("test_user", "profile")
    item = store.get(namespace, "data")
    assert item is not None
    assert item.value["name"] == "Test User"
    assert item.value["role"] == "Tester"


@pytest.mark.asyncio
async def test_update_my_profile_with_cv_summary(store: InMemoryStore, config: RunnableConfig) -> None:
    """Test that update_my_profile accepts and stores a cv_summary."""
    cv_text = "Experienced Senior Backend Dev with 5 years experience in Python."
    result = await update_my_profile.ainvoke({"name": "CV User", "cv_summary": cv_text, "store": store}, config=config)

    assert "Profile updated successfully" in result

    namespace = ("test_user", "profile")
    item = store.get(namespace, "data")
    assert item is not None
    assert item.value["cv_uploaded"] is True
    assert item.value["cv_summary"] == cv_text


@pytest.mark.asyncio
async def test_save_preference_success(store: InMemoryStore, config: RunnableConfig) -> None:
    # Act
    result = await save_preference.ainvoke({"key": "loc", "label": "Remote only", "store": store}, config=config)

    # Assert
    assert "Preference saved" in result

    # Verify store content
    namespace = ("test_user", "preferences")
    item = store.get(namespace, "loc")
    assert item is not None
    assert item.value["key"] == "loc"
    assert item.value["label"] == "Remote only"
    assert item.value["sentiment"] == "positive"


@pytest.mark.asyncio
async def test_delete_preference_success(store: InMemoryStore, config: RunnableConfig) -> None:
    # Arrange
    namespace = ("test_user", "preferences")
    store.put(namespace, "loc", {"value": "rem", "category": "hard"})

    # Act
    result = await delete_preference.ainvoke({"key": "loc", "store": store}, config=config)

    # Assert
    assert "deleted" in result

    # Verify store content
    item = store.get(namespace, "loc")
    assert item is None


@pytest.mark.asyncio
async def test_delete_preference_not_found(store: InMemoryStore, config: RunnableConfig) -> None:
    # Act
    result = await delete_preference.ainvoke({"key": "non_existent", "store": store}, config=config)

    # Assert
    assert "not found" in result


@pytest.mark.asyncio
async def test_update_my_profile_error(config: RunnableConfig) -> None:
    # Arrange
    failing_store = FailingPutStore()

    # Act
    result = await update_my_profile.ainvoke({"role": "Simulated Error", "store": failing_store}, config=config)
    # Assert
    assert "Error updating profile" in result
    assert "Database error" in result


@pytest.mark.asyncio
async def test_save_preference_error(config: RunnableConfig) -> None:
    # Arrange
    failing_store = FailingPutStore()

    # Act
    result = await save_preference.ainvoke({"key": "fail", "label": "Failing preference", "store": failing_store}, config=config)
    # Assert
    assert "Error saving preference" in result
    assert "Database error" in result


@pytest.mark.asyncio
async def test_delete_preference_error(config: RunnableConfig) -> None:
    # Arrange
    failing_store = FailingDeleteStore()
    # Ensure it passes the "exists" check first
    namespace = ("test_user", "preferences")
    # Use super put to seed without raising error
    InMemoryStore.put(failing_store, namespace, "error_key", {"value": "exists", "category": "soft"})

    # Act
    result = await delete_preference.ainvoke({"key": "error_key", "store": failing_store}, config=config)
    # Assert
    assert "Error deleting preference" in result
    assert "Delete error" in result


@pytest.mark.asyncio
async def test_finalize_profile_success(store: InMemoryStore, config: RunnableConfig) -> None:
    """Test finalize_profile succeeds when profile has name/role."""
    # Arrange: seed a profile with name and role
    namespace = ("test_user", "profile")
    store.put(namespace, "data", {"id": 1, "name": "Alice", "role": "Dev"})

    # Act
    result = await finalize_profile.ainvoke({"store": store}, config=config)

    # Assert
    assert "Onboarding complete" in result


@pytest.mark.asyncio
async def test_finalize_profile_rejects_empty(store: InMemoryStore, config: RunnableConfig) -> None:
    """Test finalize_profile rejects when no name or role is set."""
    # Act — no profile seeded
    result = await finalize_profile.ainvoke({"store": store}, config=config)

    # Assert
    assert "Cannot finalize" in result
