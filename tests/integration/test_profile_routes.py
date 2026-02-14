import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.api.dependencies import get_store
from app.main import app


@pytest.mark.asyncio
async def test_get_profile_page() -> None:
    # 1. Setup Store with Seed Data
    store = InMemoryStore()
    user_id = DEFAULT_USER_ID

    # Seed Profile
    store.put((user_id, "profile"), "data", {"name": "Test User", "role": "Test Role"})

    # Seed Preference
    store.put((user_id, "preferences"), "test_pref", {"value": "test_value", "category": "hard"})

    # 2. Override Dependency
    app.dependency_overrides[get_store] = lambda: store

    try:
        # 3. Request page
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/profile")

        # 4. Verify response
        assert response.status_code == 200
        assert "My Profile" in response.text
        assert "Test User" in response.text
        assert "Test Role" in response.text
        assert "test_pref" in response.text
        assert "test_value" in response.text
        assert "Hard Constraints" in response.text
    finally:
        app.dependency_overrides = {}
