import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_cv_persistence() -> None:
    # 1. Simulate CV Upload
    # We can't easily mock the PDF upload here without a real file,
    # but we can rely on `ChatService` logic if we could invoke it.
    # Instead, let's verify `fetch_profile` logic directly by seeding DB.

    from app.core.database import update_profile

    test_cv = "I am a skilled Python enthusiast."
    update_profile(name="Persistence Test", cv_text=test_cv)

    # 2. Check Profile Route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/profile")

    assert response.status_code == 200
    assert "Uploaded" in response.text
    assert "I am a skilled Python enthusiast" in response.text

    # 3. (Optional) We could also test the chat endpoint to see if it picks up the CV context,
    # but that involves mocking the LLM which is complex here.
    # The profile route check confirms DB persistence and read.
