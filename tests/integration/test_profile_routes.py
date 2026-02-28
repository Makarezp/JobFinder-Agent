import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.api.dependencies import get_store
from app.main import app


@pytest.mark.asyncio
async def test_get_profile_json() -> None:
    """GET /api/profile returns profile, preferences, and an empty decisions list."""
    store = InMemoryStore()
    user_id = DEFAULT_USER_ID

    # Seed Profile
    store.put((user_id, "profile"), "data", {"name": "Test User", "role": "Test Role"})

    # Seed Preference
    store.put((user_id, "preferences"), "test_pref", {"key": "test_pref", "label": "Test preference label", "sentiment": "positive"})

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
        assert data["preferences"]["test_pref"]["label"] == "Test preference label"

        # Decisions key present even when empty
        assert data["decisions"] == []
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_get_profile_includes_decisions_sorted() -> None:
    """GET /api/profile returns decisions sorted by timestamp descending."""
    store = InMemoryStore()
    user_id = DEFAULT_USER_ID

    store.put(
        (user_id, "decisions"),
        "key-1",
        {
            "job_title": "Backend Dev",
            "company": "Alpha",
            "action": "pass",
            "description": None,
            "reason": "Too junior",
            "timestamp": "2026-02-22T10:00:00+00:00",
        },
    )
    store.put(
        (user_id, "decisions"),
        "key-2",
        {
            "job_title": "ML Engineer",
            "company": "Beta",
            "action": "pursue",
            "description": None,
            "reason": None,
            "timestamp": "2026-02-22T12:00:00+00:00",
        },
    )

    app.dependency_overrides[get_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/profile")

        assert response.status_code == 200
        data = response.json()

        assert "decisions" in data
        assert len(data["decisions"]) == 2
        # Most recent first
        assert data["decisions"][0]["job_title"] == "ML Engineer"
        assert data["decisions"][1]["job_title"] == "Backend Dev"
    finally:
        app.dependency_overrides = {}
