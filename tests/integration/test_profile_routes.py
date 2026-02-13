import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import save_preference, update_profile
from app.main import app


@pytest.mark.asyncio
async def test_get_profile_page() -> None:
    # 1. Seed data
    update_profile(name="Test User", role="Test Role")
    save_preference("test_pref", "test_value", "hard")

    # 2. Request page
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/profile")

    # 3. Verify response
    assert response.status_code == 200
    assert "My Profile" in response.text
    assert "Test User" in response.text
    assert "Test Role" in response.text
    assert "test_pref" in response.text
    assert "test_value" in response.text
    assert "Hard Constraints" in response.text
