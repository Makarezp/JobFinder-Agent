import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.postgres import AsyncPostgresStore

from app.core.database import get_connection_pool
from app.main import app


@pytest.mark.asyncio
async def test_cv_persistence() -> None:
    """Test that profile with cv_summary is persisted and visible on /profile."""
    user_id = "default_user"
    namespace = (user_id, "profile")

    # Simulate a profile with structured cv_summary (as stored by the onboarding agent)
    data = {
        "name": "Persistence Test",
        "role": "Senior Python Developer",
        "cv_summary": "Experienced Python developer with 5 years of backend work.",
        "cv_uploaded": True,
    }

    # Seed the store directly
    async with get_connection_pool() as pool:
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()
        await store.aput(namespace, "data", data)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/profile")

    assert response.status_code == 200
    assert "Persistence Test" in response.text
