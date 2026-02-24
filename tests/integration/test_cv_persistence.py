import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.postgres import AsyncPostgresStore

from app.api.dependencies import get_store
from app.core.database import get_connection_pool
from app.main import app


@pytest.mark.asyncio
async def test_cv_persistence() -> None:
    """Test that profile with cv_summary is persisted and visible via GET /api/profile."""
    user_id = "default_user"
    namespace = (user_id, "profile")

    # Simulate a profile with structured cv_summary (as stored by the onboarding agent)
    data = {
        "name": "Persistence Test",
        "role": "Senior Python Developer",
        "cv_summary": "Experienced Python developer with 5 years of backend work.",
        "cv_uploaded": True,
    }

    # Seed the store directly and override the dependency so the app uses the same store
    async with get_connection_pool() as pool:
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()
        await store.aput(namespace, "data", data)

        app.dependency_overrides[get_store] = lambda: store
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/profile")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data_response = response.json()
    assert data_response["profile"]["name"] == "Persistence Test"
    assert data_response["profile"]["role"] == "Senior Python Developer"
