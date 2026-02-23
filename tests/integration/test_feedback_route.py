import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.memory_schema import DecisionLog
from app.api.dependencies import get_store
from app.main import app


@pytest.mark.asyncio
async def test_post_feedback_stores_decision_log() -> None:
    """POST /api/feedback persists a DecisionLog entry under (default_user, decisions)."""
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/feedback",
                json={
                    "job_title": "Dev",
                    "company": "Acme",
                    "action": "pass",
                    "description": "A Python role building internal tooling.",
                    "reason": "Too corporate",
                    "job_id": "abc123def456",
                },
            )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        # Verify store contains a DecisionLog under the correct namespace
        items = store.search((DEFAULT_USER_ID, "decisions"))
        assert len(items) == 1

        entry = DecisionLog(**items[0].value)
        assert entry.job_title == "Dev"
        assert entry.company == "Acme"
        assert entry.action == "pass"
        assert entry.description == "A Python role building internal tooling."
        assert entry.reason == "Too corporate"
        # Timestamp must be a non-empty ISO 8601 string
        assert entry.timestamp and "T" in entry.timestamp
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_post_feedback_without_reason() -> None:
    """POST /api/feedback accepts a null reason field."""
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/feedback",
                json={"job_title": "Engineer", "company": "StartupX", "action": "pursue", "job_id": "def456abc789"},
            )

        assert response.status_code == 200
        items = store.search((DEFAULT_USER_ID, "decisions"))
        assert len(items) == 1
        assert items[0].value["description"] is None
        assert items[0].value["reason"] is None
        assert items[0].value["action"] == "pursue"
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_post_feedback_rejects_invalid_action() -> None:
    """POST /api/feedback returns 422 for an invalid action value."""
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/feedback",
                json={"job_title": "Dev", "company": "Acme", "action": "maybe"},
            )

        assert response.status_code == 422
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_post_feedback_each_entry_gets_unique_key() -> None:
    """Multiple POST /api/feedback calls produce separate entries (uuid keys, no overwrite)."""
    store = InMemoryStore()
    app.dependency_overrides[get_store] = lambda: store

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/api/feedback", json={"job_title": "Job A", "company": "Corp1", "action": "pass", "job_id": "aaabbbccc111"})
            await ac.post("/api/feedback", json={"job_title": "Job B", "company": "Corp2", "action": "pursue", "job_id": "dddeeefff222"})

        items = store.search((DEFAULT_USER_ID, "decisions"))
        assert len(items) == 2
    finally:
        app.dependency_overrides = {}
