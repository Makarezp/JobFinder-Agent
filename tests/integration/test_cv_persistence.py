import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.api.dependencies import get_store
from app.main import app

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_cv_persistence(pg_pool: AsyncConnectionPool) -> None:
    """Test that profile with cv_summary is persisted and visible via GET /api/profile.
    Uses an isolated Postgres container — never touches the dev database.
    """
    user_id = "default_user"
    namespace = (user_id, "profile")

    data = {
        "name": "Persistence Test",
        "role": "Senior Python Developer",
        "cv_summary": "Experienced Python developer with 5 years of backend work.",
        "cv_uploaded": True,
    }

    store = AsyncPostgresStore(pg_pool)  # type: ignore[arg-type]
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
