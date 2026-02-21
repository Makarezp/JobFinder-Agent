import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.api.dependencies import get_store
from app.main import app


@pytest.mark.asyncio
async def test_get_profile_json() -> None:
    """GET /api/profile returns profile and preferences as JSON."""
    store = InMemoryStore()
    user_id = DEFAULT_USER_ID

    # Seed Profile
    store.put((user_id, "profile"), "data", {"name": "Test User", "role": "Test Role"})

    # Seed Preference
    store.put((user_id, "preferences"), "test_pref", {"value": "test_value", "category": "hard"})

    app.dependency_overrides[get_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/profile")

        assert response.status_code == 200
        data = response.json()

        # Profile assertions
        assert data["profile"]["name"] == "Test User"
        assert data["profile"]["role"] == "Test Role"

        # Preference assertions
        assert "test_pref" in data["preferences"]
        assert data["preferences"]["test_pref"]["value"] == "test_value"
    finally:
        app.dependency_overrides = {}
